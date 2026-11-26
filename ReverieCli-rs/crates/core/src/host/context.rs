use super::{EventSink, KernelHost, Result, Run, RunControl, lock, models};
use crate::{
    compaction::{self, CompactionKind, CompactionOptions, CompactionOutcome, CompactionResponse},
    provider::ProviderClient,
    session::{SessionStore, context::ContextSource},
};
use reverie_protocol::Reply;
use serde_json::{Value, json};
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

pub(super) struct ResumedUser {
    pub source: ContextSource,
    pub sequence: i64,
    pub message: Value,
}

pub struct PendingCompaction {
    id: String,
    project: PathBuf,
    session: String,
    store: Mutex<SessionStore>,
    model: Value,
    config: Value,
    context_engine: Value,
    focus: String,
    control: Arc<RunControl>,
}

struct ReductionTarget<'a> {
    store: &'a Mutex<SessionStore>,
    model: &'a Value,
    config: &'a Value,
    control: &'a RunControl,
    run_id: &'a str,
    current_task: bool,
    system: &'a str,
}

pub(super) fn capacity(config: &Value) -> usize {
    config["max_context_tokens"]
        .as_u64()
        .filter(|value| *value > 0)
        .and_then(|value| usize::try_from(value).ok())
        .unwrap_or(128_000)
}

pub(crate) fn usage(messages: &[Value], config: &Value) -> Value {
    let counted = compaction::count_messages(messages);
    let max = capacity(config);
    json!({"basis":"saved_native_context_estimate","tokenizer":counted.tokenizer,
        "total_tokens":counted.tokens,"max_tokens":max,"remaining_tokens":max.saturating_sub(counted.tokens),
        "percentage":counted.tokens as f64 / max as f64 * 100.0,"overhead_tokens":0,
        "segments":[{"key":"history","tokens":counted.tokens,"messages":messages.len(),"share":100.0}],
        "reasoning_tokens":0,"payload_message_count":messages.len(),"history_message_count":messages.len(),
        "history_limit":messages.len(),"compaction_tokens":(max as u128 * 70 / 100) as usize,"rotation_tokens":(max as u128 * 82 / 100) as usize,
        "text_exact":counted.text_exact,"envelope_estimated":counted.envelope_estimated,
        "media_estimated":counted.media_estimated,"fallback_reason":counted.fallback_reason})
}

impl KernelHost {
    pub(super) fn resumed_user(&self, payload: &Value) -> Result<ResumedUser> {
        if payload["promptAlreadySaved"] == true {
            return Err("Ordinary resume cannot use the AiO saved-prompt flag.".into());
        }
        let session = payload["sessionId"]
            .as_str()
            .filter(|id| !id.is_empty())
            .ok_or("Resuming requires a conversation identity.")?;
        let mut kernel = lock(&self.kernel)?;
        kernel.configure_assistant(payload)?;
        if kernel.assistant_mode {
            return Err("Use the AiO task control to resume an AiO branch.".into());
        }
        if let Some(root) = payload["projectRoot"].as_str() {
            kernel.configure_project(root)?;
        }
        let snapshot = kernel.session_store()?.context_snapshot(session)?;
        let user = snapshot
            .active
            .iter()
            .rev()
            .find(|entry| entry.message["role"] == "user")
            .ok_or("The conversation has no saved user request to resume.")?;
        let text = user.message["content"].as_str().filter(|text| !text.trim().is_empty())
            .ok_or("The saved request is not a text prompt; multimodal resume has not yet been migrated.")?;
        for field in ["prompt", "message"] {
            if let Some(value) = payload.get(field)
                && value != text
            {
                return Err("The resumed request must match the complete saved user text.".into());
            }
        }
        Ok(ResumedUser {
            source: snapshot.source.clone(),
            sequence: user.sequence,
            message: user.message.clone(),
        })
    }

    pub fn begin_compaction(&self, payload: &Value) -> Result<PendingCompaction> {
        let mut active = lock(&self.active)?;
        let mut kernel = lock(&self.kernel)?;
        kernel.configure_assistant(payload)?;
        if let Some(root) = payload["projectRoot"].as_str() {
            kernel.configure_project(root)?;
        }
        let session = payload["sessionId"]
            .as_str()
            .filter(|id| !id.is_empty())
            .ok_or("Compacting requires a conversation identity.")?
            .to_owned();
        let id = payload["runId"]
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| Uuid::new_v4().simple().to_string());
        if id.is_empty()
            || id.len() > 128
            || !id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
        {
            return Err("Invalid compaction operation identity.".into());
        }
        if active.contains_key(&id)
            || active.values().any(|control| {
                control.session_id == session
                    && control.assistant == kernel.assistant_mode
                    && (control.assistant || control.project_root == kernel.project_root)
            })
        {
            return Err("A run is already active for this conversation.".into());
        }
        let page = kernel.session_store()?.page(&session, None, 1)?;
        let defaults = kernel.config.effective()?;
        let snapshot = page
            .metadata
            .get("runtime_config")
            .cloned()
            .unwrap_or_else(|| models::capture(&defaults));
        let config = models::resolve(&defaults, &snapshot)?;
        let model = models::active(&config)
            .ok_or("Select a configured model before compacting context.")?
            .clone();
        let store = if kernel.assistant_mode {
            SessionStore::open_assistant(&super::modes::aio::data_directory(&kernel.app_root))?
        } else {
            SessionStore::open(&kernel.project_data_dir, &kernel.project_root)?
        };
        store.ensure_reduction_run(&session, None)?;
        let control = Arc::new(RunControl {
            cancel: CancellationToken::new(),
            commit_gate: Mutex::new(()),
            session_id: session.clone(),
            project_root: kernel.project_root.clone(),
            assistant: kernel.assistant_mode,
            approval_ready: Default::default(),
            approvals: Mutex::new(Default::default()),
            questions: Mutex::new(Default::default()),
        });
        active.insert(id.clone(), control.clone());
        Ok(PendingCompaction {
            id,
            project: kernel.project_root.clone(),
            session,
            store: Mutex::new(store),
            model,
            config,
            context_engine: kernel.context_status(),
            focus: payload["focus"].as_str().unwrap_or_default().to_owned(),
            control,
        })
    }

    pub async fn complete_compaction(
        &self,
        request_id: Value,
        pending: PendingCompaction,
        sink: EventSink,
    ) -> Reply {
        let result = self
            .reduce_context(
                ReductionTarget {
                    store: &pending.store,
                    model: &pending.model,
                    config: &pending.config,
                    control: &pending.control,
                    run_id: &pending.id,
                    current_task: false,
                    system: "",
                },
                CompactionKind::Compression,
                &pending.focus,
                &sink,
            )
            .await;
        if let Ok(mut active) = self.active.lock() {
            active.remove(&pending.id);
        }
        let committed = result
            .as_ref()
            .is_ok_and(|(_, report)| report["changed"] == true);
        let state = if committed {
            "completed"
        } else if pending.control.cancel.is_cancelled() {
            "cancelled"
        } else if result.is_err() {
            "failed"
        } else {
            "completed"
        };
        sink(
            json!({"type":"run.finished","state":state,"project_root":pending.project,"session_id":pending.session,"run_id":pending.id}),
        );
        let fields = (|| -> Result<Value> {
            let (messages, report) = result?;
            let mut store = lock(&pending.store)?;
            Ok(
                json!({"success":report["changed"],"message":report["message"],"compaction":report,
                "session":store.page(&pending.session,None,200)?,"sessions":store.list()?,
                "usage":usage(&messages,&pending.config),"session_id":pending.session,"run_id":pending.id,"project_root":pending.project,
                "recovery":{"available":false,"status":"migration_pending","summary":{"available":false},"operations":[],"checkpoints":[]},
                "context_engine":pending.context_engine}),
            )
        })();
        match fields {
            Ok(fields) => Reply::new(
                Some(request_id),
                "context.compacted",
                fields.as_object().cloned().unwrap_or_default(),
            ),
            Err(error) => Reply::error(request_id, error),
        }
    }

    async fn reduce_context(
        &self,
        target: ReductionTarget<'_>,
        kind: CompactionKind,
        focus: &str,
        sink: &EventSink,
    ) -> Result<(Vec<Value>, Value)> {
        if target.control.cancel.is_cancelled() {
            return Err("Context reduction was cancelled.".into());
        }
        let (snapshot, checkpoint) = {
            let store = lock(target.store)?;
            store.ensure_reduction_run(
                &target.control.session_id,
                target.current_task.then_some(target.run_id),
            )?;
            let snapshot = store.context_snapshot(&target.control.session_id)?;
            let checkpoint = store.checkpoint_context(&snapshot)?;
            (snapshot, checkpoint)
        };
        let options = CompactionOptions {
            focus: focus.into(),
            system_context: target.system.into(),
            max_tokens: capacity(target.config),
            reason: "native context capacity".into(),
            ..Default::default()
        };
        let Some(mut request) = compaction::prepare(&snapshot, &checkpoint, kind, &options)? else {
            return Ok((
                snapshot.messages(),
                json!({"changed":false,"message":"No complete older context needs reduction."}),
            ));
        };
        let proxy = target.config["api_proxy"].as_str().unwrap_or_default();
        let client = {
            let mut clients = lock(&self.clients)?;
            if !clients.contains_key(proxy) {
                clients.insert(proxy.into(), Arc::new(ProviderClient::new(Some(proxy))?));
            }
            clients[proxy].clone()
        };
        let mut configuration = target.config.clone();
        configuration["stream_responses"] = json!(false);
        let quiet = |_: Value| {};
        loop {
            if target.control.cancel.is_cancelled() {
                return Err("Context reduction was cancelled.".into());
            }
            sink(
                json!({"type":"context.compaction.started","kind":kind,"attempt":request.attempt,
                "session_id":target.control.session_id,"project_root":target.control.project_root,"run_id":target.run_id}),
            );
            let response = client
                .chat(
                    target.model,
                    &configuration,
                    &request.messages,
                    &[],
                    &target.control.cancel,
                    &quiet,
                )
                .await;
            if target.control.cancel.is_cancelled() {
                return Err("Context reduction was cancelled before switching context.".into());
            }
            let response = match response {
                Ok(turn) if turn.tool_calls.is_empty() => CompactionResponse::Text(turn.content),
                Ok(_) => CompactionResponse::Failed(
                    "The summary model attempted tool execution; no tools were run.".into(),
                ),
                Err(_) => CompactionResponse::Failed("The summary model request failed.".into()),
            };
            match compaction::complete(&request, response, target.model)? {
                CompactionOutcome::Repair(repair) => {
                    request = repair;
                }
                CompactionOutcome::Unchanged { reason } => {
                    return Ok((
                        snapshot.messages(),
                        json!({"changed":false,"message":reason,"kind":kind}),
                    ));
                }
                CompactionOutcome::Ready(prepared) => {
                    if target.control.cancel.is_cancelled() {
                        return Err(
                            "Context reduction was cancelled before switching context.".into()
                        );
                    }
                    let current = lock(target.store)?.segment_context_checked(
                        &snapshot,
                        &checkpoint,
                        &prepared,
                        &format!(
                            "{}:context:{kind:?}:{}",
                            target.run_id, snapshot.source.revision
                        ),
                        target.current_task.then_some(target.run_id),
                        || {
                            let gate = lock(&target.control.commit_gate)?;
                            if target.control.cancel.is_cancelled() {
                                return Err("Context reduction was cancelled before commit.".into());
                            }
                            Ok(gate)
                        },
                    )?;
                    let report = json!({"changed":true,"message":"Context reduced; complete source transcript retained in a verified checkpoint.",
                        "kind":kind,"origin":prepared.origin,"fallback_reason":prepared.fallback_reason,
                        "source":prepared.source,"checkpoint":checkpoint,"usage_before":prepared.usage_before,"usage_after":prepared.usage_after});
                    sink(
                        json!({"type":"context.compaction.finished","compaction":report,"session_id":target.control.session_id,
                        "project_root":target.control.project_root,"run_id":target.run_id}),
                    );
                    return Ok((current.messages(), report));
                }
            }
        }
    }

    pub(super) async fn adjust_run_context(
        &self,
        run: &mut Run,
        control: &RunControl,
        sink: &EventSink,
    ) -> Result<()> {
        let max = capacity(&run.config);
        if !compaction::needs_compression(compaction::count_messages(&run.messages).tokens, max) {
            let mut current = usage(&run.messages, &run.config);
            current["basis"] = json!("native_next_request_estimate");
            sink(
                json!({"type":"context.usage","usage":current,"session_id":run.session,"project_root":run.root,"run_id":run.id}),
            );
            return Ok(());
        }
        let system = run
            .messages
            .first()
            .filter(|message| message["role"] == "system")
            .cloned();
        let text = system
            .as_ref()
            .and_then(|message| message["content"].as_str())
            .unwrap_or_default();
        let target = ReductionTarget {
            store: &run.store,
            model: &run.model,
            config: &run.config,
            control,
            run_id: &run.id,
            current_task: true,
            system: text,
        };
        let (mut messages, report) = self
            .reduce_context(target, CompactionKind::Compression, "", sink)
            .await?;
        if let Some(system) = system.clone() {
            messages.insert(0, system);
        }
        if report["changed"] == true {
            run.messages = messages;
            run.activities
                .push(json!({"event":"context_compaction","compaction":report}));
        }
        if compaction::needs_handoff(compaction::count_messages(&run.messages).tokens, max) {
            let target = ReductionTarget {
                store: &run.store,
                model: &run.model,
                config: &run.config,
                control,
                run_id: &run.id,
                current_task: true,
                system: text,
            };
            let (mut messages, report) = self
                .reduce_context(target, CompactionKind::Handoff, "", sink)
                .await?;
            if report["changed"] != true {
                return Err(report["message"]
                    .as_str()
                    .unwrap_or("Context handoff did not succeed.")
                    .to_owned()
                    .into());
            }
            if let Some(system) = system {
                messages.insert(0, system);
            }
            run.messages = messages;
            run.activities
                .push(json!({"event":"context_handoff","compaction":report}));
        }
        if compaction::count_messages(&run.messages).tokens >= max {
            return Err(
                "The preserved request and instructions exceed the configured context capacity."
                    .into(),
            );
        }
        let mut current = usage(&run.messages, &run.config);
        current["basis"] = json!("native_next_request_estimate");
        sink(
            json!({"type":"context.usage","usage":current,"session_id":run.session,"project_root":run.root,"run_id":run.id}),
        );
        Ok(())
    }
}
