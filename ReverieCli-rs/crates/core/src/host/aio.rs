use super::{EventSink, KernelHost, RunControl, lock};
use crate::{Result, models, modes::aio};
use reverie_protocol::Reply;
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{Arc, Mutex, MutexGuard},
    time::Instant,
};
use uuid::Uuid;

pub enum PendingAioDecision {
    Finished(Value),
    Model(Box<AioModelDecision>),
}
pub struct AioModelDecision {
    id: String,
    root: PathBuf,
    observation: Value,
    workspaces: Vec<String>,
    context: Value,
    revision: u64,
    snapshot: Value,
    configuration: Value,
    model: Value,
    urgent: bool,
    control: Arc<RunControl>,
}

impl KernelHost {
    pub(super) fn is_aio_action(action: &str) -> bool {
        matches!(
            action,
            "aioState"
                | "aioControl"
                | "aioObserve"
                | "aioMessages"
                | "aioPendingSignals"
                | "aioAcknowledgeSignal"
                | "aioPendingTasks"
                | "aioRecoverHost"
                | "aioMessageState"
                | "aioReply"
                | "aioTaskState"
                | "aioMemory"
        )
    }
    fn aio_store(&self) -> Result<MutexGuard<'_, Option<aio::AioStore>>> {
        let app = lock(&self.kernel)?.app_root.clone();
        let mut store = lock(&self.aio)?;
        if store.is_none() {
            *store = Some(aio::AioStore::open(&app)?);
        }
        Ok(store)
    }
    pub(super) fn aio_action(
        &self,
        action: &str,
        payload: &Value,
    ) -> Result<(&'static str, Value)> {
        if payload["assistantId"] != "aio" {
            return Err("AiO requests require assistantId=aio.".into());
        }
        let snapshot = if action == "aioControl" && payload["enable"] == true {
            let mut kernel = lock(&self.kernel)?;
            if let Some(root) = payload["projectRoot"].as_str() {
                kernel.configure_project(root)?;
            }
            Some(models::capture(&kernel.config.effective()?))
        } else {
            None
        };
        let result = {
            let mut store = self.aio_store()?;
            let store = store.as_mut().expect("aio_store initializes the store");
            if let Some(snapshot) = snapshot {
                Ok(("aio.state", json!({"aio":store.enable(&snapshot)?})))
            } else {
                store.handle(action, payload)
            }
        }?;
        if action == "aioControl"
            && (result.1["aio"]["enabled"] == false || result.1["aio"]["paused"] == true)
        {
            let disable = result.1["aio"]["enabled"] == false;
            for control in lock(&self.active)?.values().filter(|control| {
                control.assistant && (disable || control.session_id == aio::MAINLINE)
            }) {
                control.request_cancel()?;
            }
        }
        Ok(result)
    }
    pub fn begin_aio_decision(&self, payload: &Value) -> Result<PendingAioDecision> {
        if payload["assistantId"] != "aio" {
            return Err("AiO decisions require assistantId=aio.".into());
        }
        let observation = payload["observation"]
            .as_object()
            .cloned()
            .map(Value::Object)
            .ok_or("AiO observation must be an object.")?;
        let event = observation["event_id"]
            .as_str()
            .filter(|id| !id.is_empty())
            .ok_or("AiO decisions require a stable observation event_id.")?;
        let workspaces = payload["workspaces"]
            .as_array()
            .ok_or("AiO decisions require an explicit workspace list.")?
            .iter()
            .map(|value| {
                let path = value.as_str().ok_or("AiO workspace must be text.")?;
                Ok(
                    crate::config::canonical_project(std::path::Path::new(path))?
                        .to_string_lossy()
                        .into_owned(),
                )
            })
            .collect::<Result<Vec<_>>>()?;
        let urgent = payload["urgent"].as_bool().unwrap_or(false);
        let mut active = lock(&self.active)?;
        if active
            .values()
            .any(|control| control.assistant && control.session_id == aio::MAINLINE)
        {
            return Err("An AiO mainline operation is already active.".into());
        }
        let (root, defaults) = {
            let kernel = lock(&self.kernel)?;
            (
                kernel.project_root.clone(),
                crate::config::ConfigStore::new(&kernel.app_root).effective()?,
            )
        };
        let (state, snapshot, context) = {
            let mut store = self.aio_store()?;
            let store = store.as_mut().unwrap();
            if store.accepted(event)? {
                return Ok(PendingAioDecision::Finished(
                    json!({"speech":"","tasks":[],"memories":[],"skipped":"already_accepted"}),
                ));
            }
            let state = store.state()?;
            if state["enabled"] != true
                || state["paused"] == true
                || (!urgent && state["proactive"] != true)
            {
                return Ok(PendingAioDecision::Finished(
                    json!({"speech":"","tasks":[],"memories":[],"skipped":"disabled_or_paused"}),
                ));
            }
            (state, store.configuration()?, store.context(&observation)?)
        };
        if !urgent
            && lock(&self.aio_last_decision)?
                .as_ref()
                .is_some_and(|last| last.elapsed().as_secs() < 60)
        {
            return Ok(PendingAioDecision::Finished(
                json!({"speech":"","tasks":[],"memories":[],"skipped":"throttled"}),
            ));
        }
        let configuration = models::resolve(&defaults, &snapshot)?;
        let mut model = models::active(&configuration)
            .cloned()
            .ok_or("Select an available AiO model before making a decision.")?;
        let maximum = model["max_output_tokens"]
            .as_u64()
            .or(model["max_tokens"].as_u64())
            .unwrap_or(4096)
            .min(4096);
        model["max_output_tokens"] = json!(maximum);
        model["max_tokens"] = json!(maximum);
        let id = format!("aio-decision-{}", Uuid::new_v4().simple());
        let control = Arc::new(RunControl {
            commit_gate: Default::default(),
            cancel: self.context_cancel.child_token(),
            session_id: aio::MAINLINE.into(),
            project_root: root.clone(),
            assistant: true,
            approval_ready: Default::default(),
            approvals: Mutex::new(HashMap::new()),
            questions: Mutex::new(HashMap::new()),
        });
        let revision = state["native_revision"]
            .as_u64()
            .ok_or("AiO state revision is missing.")?;
        active.insert(id.clone(), control.clone());
        *lock(&self.aio_last_decision)? = Some(Instant::now());
        Ok(PendingAioDecision::Model(Box::new(AioModelDecision {
            id,
            root,
            observation,
            workspaces,
            context,
            revision,
            snapshot,
            configuration,
            model,
            urgent,
            control,
        })))
    }
    pub async fn complete_aio_decision(
        &self,
        id: Value,
        pending: PendingAioDecision,
        sink: EventSink,
    ) -> Reply {
        let result = match pending {
            PendingAioDecision::Finished(value) => Ok(value),
            PendingAioDecision::Model(pending) => {
                let result = self.aio_model(&pending, sink).await;
                if let Ok(mut active) = self.active.lock() {
                    active.remove(&pending.id);
                }
                result
            }
        };
        match result {
            Ok(decision) => Reply::new(
                Some(id),
                "aio.decision",
                serde_json::Map::from_iter([("decision".into(), decision)]),
            ),
            Err(error) => Reply::error(id, error),
        }
    }
    async fn aio_model(&self, pending: &AioModelDecision, sink: EventSink) -> Result<Value> {
        let emit = |mut event: Value| {
            event["assistant_id"] = json!("aio");
            event["project_root"] = json!(pending.root);
            event["session_id"] = json!(aio::MAINLINE);
            event["run_id"] = json!(pending.id);
            sink(event);
        };
        emit(json!({"type":"aio.decision.started","event_id":pending.observation["event_id"]}));
        let user = json!({"observation":pending.observation,"workspaces":pending.workspaces,"context":pending.context,"capabilities":{"desktop_observation":false,"desktop_execution":false,"desktop_capability_status":"native_observation_not_migrated","decision_tools":false,"available_task_modes":["reverie","reverie-atlas","writer"]}});
        let mut messages = vec![
            json!({"role":"system","content":aio::decision_rules()}),
            json!({"role":"user","content":serde_json::to_string(&user)?}),
        ];
        for attempt in 0..=2 {
            let raw = self
                .text_model(
                    &pending.model,
                    &pending.configuration,
                    &messages,
                    &pending.control.cancel,
                    &emit,
                )
                .await?;
            if pending.control.cancel.is_cancelled() {
                return Err("AiO decision cancelled before persistent effects.".into());
            }
            match aio::parse_decision(&raw) {
                Ok(decision)=>{
                    if decision["tasks"].as_array().into_iter().flatten().any(|task|crate::modes::normalize(task["mode"].as_str().unwrap_or("reverie")).is_ok_and(|mode|matches!(mode,"aio"|"reverie-gamer"))) {
                        return Err("This decision requires a native desktop or Gamer runtime that is not yet available; no task was queued.".into());
                    }
                    let result={let mut store=self.aio_store()?;store.as_mut().unwrap().accept_decision(&decision,&pending.observation,&pending.workspaces,&pending.snapshot,pending.revision,pending.urgent)?};
                    emit(json!({"type":"aio.decision.finished","event_id":pending.observation["event_id"]}));return Ok(result);
                }
                Err(error) if attempt<2=>{
                    messages.push(json!({"role":"assistant","content":raw}));messages.push(json!({"role":"user","content":format!("Return one valid decision JSON object matching the declared speech/tasks/memories contract. No tool calls. Validation error: {error}")}));
                }
                Err(error)=>return Err(format!("AiO decision remained invalid after two JSON repair attempts; no tasks or memories were committed: {error}").into()),
            }
        }
        unreachable!("the bounded decision loop always returns")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        sync::{TryLockError, mpsc},
        thread,
        time::Duration,
    };

    #[test]
    fn aio_control_pause_and_disable_wait_for_the_active_context_commit() {
        for changes in [json!({"paused":true}), json!({"enabled":false})] {
            let directory = tempfile::Builder::new()
                .prefix("aio-commit-")
                .tempdir_in(env!("CARGO_MANIFEST_DIR"))
                .unwrap();
            let kernel = crate::Kernel::with_app_root(
                directory.path().to_owned(),
                directory.path().to_owned(),
            )
            .unwrap();
            let host = Arc::new(KernelHost::new(kernel));
            host.aio_action("aioControl", &json!({"assistantId":"aio","enable":true}))
                .unwrap();
            let control = Arc::new(RunControl {
                cancel: tokio_util::sync::CancellationToken::new(),
                commit_gate: Default::default(),
                session_id: aio::MAINLINE.into(),
                project_root: host.project_root().unwrap(),
                assistant: true,
                approval_ready: Default::default(),
                approvals: Mutex::new(HashMap::new()),
                questions: Mutex::new(HashMap::new()),
            });
            lock(&host.active)
                .unwrap()
                .insert("active-aio-context".into(), control.clone());
            let commit = lock(&control.commit_gate).unwrap();
            let (started_sender, started_receiver) = mpsc::channel();
            let (finished_sender, finished_receiver) = mpsc::channel();
            let worker_host = host.clone();
            let request = reverie_protocol::Request {
                id: json!("aio-control-commit-check"),
                action: "aioControl".into(),
                payload: json!({"assistantId":"aio","changes":changes.clone()}),
            };
            let worker = thread::spawn(move || {
                let runtime = tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()
                    .unwrap();
                started_sender.send(()).unwrap();
                let reply = runtime.block_on(worker_host.dispatch(request, Arc::new(|_| {})));
                finished_sender.send(reply).unwrap();
            });
            started_receiver
                .recv_timeout(Duration::from_secs(5))
                .unwrap();
            let deadline = Instant::now() + Duration::from_secs(5);
            let mut premature_reply = None;
            let entered_cancel = loop {
                if let Ok(reply) = finished_receiver.try_recv() {
                    premature_reply = Some(reply);
                    break false;
                }
                if control.cancel.is_cancelled() || Instant::now() >= deadline {
                    break false;
                }
                match host.active.try_lock() {
                    Err(TryLockError::WouldBlock) => break true,
                    Err(TryLockError::Poisoned(_)) => break false,
                    Ok(active) => drop(active),
                }
                thread::yield_now();
            };
            let waited_for_commit = if entered_cancel {
                match finished_receiver.recv_timeout(Duration::from_millis(50)) {
                    Err(mpsc::RecvTimeoutError::Timeout) => true,
                    Ok(reply) => {
                        premature_reply = Some(reply);
                        false
                    }
                    Err(mpsc::RecvTimeoutError::Disconnected) => false,
                }
            } else {
                false
            };
            let unchanged_during_commit = !control.cancel.is_cancelled();
            drop(commit);
            let reply = premature_reply
                .map(Ok)
                .unwrap_or_else(|| finished_receiver.recv_timeout(Duration::from_secs(5)));
            worker.join().unwrap();
            let reply = reply.unwrap();
            assert!(
                entered_cancel,
                "The actual aioControl did not reach cancellation: {reply:?}"
            );
            assert!(
                waited_for_commit,
                "aioControl completed while the commit was still locked"
            );
            assert!(
                unchanged_during_commit,
                "AiO cancellation changed before commit release"
            );
            assert_eq!(reply.kind, "aio.state");
            for (key, expected) in changes.as_object().unwrap() {
                assert_eq!(&reply.fields["aio"][key], expected);
            }
            assert!(control.cancel.is_cancelled());
        }
    }
}
