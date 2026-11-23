use crate::{
    Kernel, Result, models,
    provider::{ProviderClient, ToolCall},
};
use reverie_platform::ToolResult;
use reverie_protocol::{PromptResult, Reply, Request};
use serde_json::{Map, Value, json};
use std::{
    collections::{HashMap, HashSet},
    path::PathBuf,
    sync::{Arc, Mutex, MutexGuard},
    time::Instant,
};
use tokio::sync::oneshot;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

pub type EventSink = Arc<dyn Fn(Value) + Send + Sync>;
type SessionGrants = Arc<Mutex<HashSet<String>>>;

fn lock<T>(value: &Mutex<T>) -> Result<MutexGuard<'_, T>> {
    value
        .lock()
        .map_err(|_| "Kernel state lock was poisoned.".into())
}

struct Waiter {
    sender: oneshot::Sender<Value>,
}

pub struct RunControl {
    pub cancel: CancellationToken,
    pub session_id: String,
    pub project_root: PathBuf,
    approvals: Mutex<HashMap<String, Waiter>>,
    questions: Mutex<HashMap<String, Waiter>>,
    approved: SessionGrants,
}

struct Run {
    session: String,
    session_name: String,
    id: String,
    root: PathBuf,
    execution_root: PathBuf,
    data: PathBuf,
    model: Value,
    config: Value,
    messages: Vec<Value>,
    prompt: String,
    no_index: bool,
    history_count: usize,
    rules: String,
    store: Mutex<crate::session::SessionStore>,
    context: Option<Arc<Mutex<reverie_context::ContextEngine>>>,
    context_key: PathBuf,
    semantic: Option<Arc<crate::semantic_resources::ModelVersion>>,
    semantic_error: Option<String>,
    reasoning: String,
    activities: Vec<Value>,
}

pub struct PendingRun {
    run: Run,
    control: Arc<RunControl>,
}

pub struct KernelHost {
    pub(crate) kernel: Mutex<Kernel>,
    active: Mutex<HashMap<String, Arc<RunControl>>>,
    clients: Mutex<HashMap<String, Arc<ProviderClient>>>,
    grants: Mutex<HashMap<(PathBuf, String), SessionGrants>>,
    pub(crate) context_jobs: Mutex<HashMap<String, Arc<crate::context_jobs::ContextControl>>>,
}

impl KernelHost {
    pub fn new(kernel: Kernel) -> Self {
        Self {
            kernel: Mutex::new(kernel),
            active: Mutex::new(HashMap::new()),
            clients: Mutex::new(HashMap::new()),
            grants: Mutex::new(HashMap::new()),
            context_jobs: Mutex::new(HashMap::new()),
        }
    }

    pub fn cancel_all(&self) {
        if let Ok(active) = self.active.lock() {
            for control in active.values() {
                control.cancel.cancel();
            }
        }
        if let Ok(jobs) = self.context_jobs.lock() {
            for job in jobs.values() {
                job.cancel.cancel();
            }
        }
    }

    pub fn project_root(&self) -> Result<PathBuf> {
        Ok(lock(&self.kernel)?.project_root.clone())
    }

    pub async fn dispatch(&self, request: Request, sink: EventSink) -> Reply {
        if Self::is_context_action(&request.action) {
            return match self.begin_context_job(&request.action, &request.payload) {
                Ok(job) => self.complete_context_job(request.id, job, sink).await,
                Err(error) => Reply::error(request.id, error),
            };
        }
        let id = request.id.clone();
        let result = match request.action.as_str() {
            "getSemanticResources" => self.semantic_inventory(),
            "stopContextOperation" => self.stop_context_job(&request.payload),
            "runPrompt" => match self.begin_prompt(&request.payload) {
                Ok(pending) => return self.complete_prompt(id, pending, sink).await,
                Err(error) => return Reply::error(id, error),
            },
            "stopPrompt" => self.stop(&request.payload),
            "resolveApproval" => self.resolve(&request.payload, false),
            "resolveUserInput" => self.resolve(&request.payload, true),
            "recoverConversationRuns" => {
                let active = match lock(&self.active) {
                    Ok(active) => active,
                    Err(error) => return Reply::error(id, error),
                };
                let mut kernel = match lock(&self.kernel) {
                    Ok(kernel) => kernel,
                    Err(error) => return Reply::error(id, error),
                };
                let recovered = (|| -> Result<Value> {
                    if let Some(root) = request.payload["projectRoot"].as_str() {
                        kernel.configure_project(root)?;
                    }
                    Ok(
                        json!({"runs":kernel.session_store()?.recover_runs(&active.keys().cloned().collect::<Vec<_>>())?}),
                    )
                })();
                recovered.map(|value| ("conversation.runs", value))
            }
            "listTools" => Ok((
                "tools",
                json!({"mode":"reverie","tools":tool_catalog().into_iter().map(|tool|json!({"name":tool["function"]["name"],"description":tool["function"]["description"],"parameters":tool["function"]["parameters"],"kind":"built-in","category":if tool["function"]["name"]=="userInput"{"interaction"}else{"files"},"aliases":[],"tags":[],"traits":[],"supported_modes":["reverie"],"required":tool["function"]["parameters"]["required"],"properties":tool["function"]["parameters"]["properties"].as_object().map(|properties|properties.keys().collect::<Vec<_>>()).unwrap_or_default()})).collect::<Vec<_>>()}),
            )),
            _ => match lock(&self.kernel) {
                Ok(mut kernel) => return kernel.dispatch(request),
                Err(error) => return Reply::error(id, error),
            },
        };
        match result {
            Ok((kind, fields)) => Reply::new(
                Some(id),
                kind,
                fields.as_object().cloned().unwrap_or_default(),
            ),
            Err(error) => Reply::error(id, error),
        }
    }

    fn stop(&self, payload: &Value) -> Result<(&'static str, Value)> {
        let active = lock(&self.active)?;
        let run = payload["runId"].as_str();
        let session = payload["sessionId"].as_str();
        if run.is_none() && session.is_none() {
            return Err("Stopping a prompt requires a run or conversation identity.".into());
        }
        let project = payload["projectRoot"]
            .as_str()
            .map(|root| crate::config::canonical_project(std::path::Path::new(root)))
            .transpose()?;
        for (id, control) in active.iter() {
            if run.is_none_or(|run| run == id)
                && session.is_none_or(|session| session == control.session_id)
                && project
                    .as_ref()
                    .is_none_or(|project| project == &control.project_root)
            {
                control.cancel.cancel();
                return Ok((
                    "run.control",
                    json!({"state":"stopping","run_id":id,"session_id":control.session_id,"project_root":control.project_root}),
                ));
            }
        }
        Err("The selected run is no longer active.".into())
    }

    fn resolve(&self, payload: &Value, question: bool) -> Result<(&'static str, Value)> {
        let key = if question { "questionId" } else { "approvalId" };
        let id = payload[key]
            .as_str()
            .ok_or("Decision identity is required.")?;
        if question {
            if payload["cancelled"] != true
                && payload["answer"]
                    .as_str()
                    .is_none_or(|answer| answer.trim().is_empty())
            {
                return Err("Explicit user answer is required.".into());
            }
        } else {
            if !payload["decision"]
                .as_str()
                .is_some_and(|decision| ["once", "session", "deny", "message"].contains(&decision))
            {
                return Err("Invalid approval decision.".into());
            }
            if payload["decision"] == "message"
                && payload["message"]
                    .as_str()
                    .is_none_or(|message| message.trim().is_empty())
            {
                return Err("A message decision requires the user's text.".into());
            }
        }
        let project = payload["projectRoot"]
            .as_str()
            .map(|root| crate::config::canonical_project(std::path::Path::new(root)))
            .transpose()?;
        for (run_id, control) in lock(&self.active)?.iter() {
            if payload["sessionId"]
                .as_str()
                .is_some_and(|session| session != control.session_id)
            {
                continue;
            }
            if project
                .as_ref()
                .is_some_and(|project| project != &control.project_root)
                || payload["runId"].as_str().is_some_and(|run| run != run_id)
                || control.cancel.is_cancelled()
            {
                continue;
            }
            let waiting = if question {
                &control.questions
            } else {
                &control.approvals
            };
            if let Some(waiter) = lock(waiting)?.remove(id) {
                waiter
                    .sender
                    .send(payload.clone())
                    .map_err(|_| "Decision request is no longer active.")?;
                return Ok((
                    if question {
                        "user.resolved"
                    } else {
                        "approval.resolved"
                    },
                    json!({if question{"question_id"}else{"approval_id"}:id,"decision":payload["decision"]}),
                ));
            }
        }
        Err("Decision identity is unknown or no longer pending.".into())
    }

    fn prepare(&self, payload: &Value, id: String) -> Result<Run> {
        let prompt = payload["prompt"]
            .as_str()
            .or_else(|| payload["message"].as_str())
            .filter(|prompt| !prompt.trim().is_empty())
            .ok_or("Prompt must contain text.")?
            .to_owned();
        let mut kernel = lock(&self.kernel)?;
        if let Some(root) = payload["projectRoot"].as_str() {
            kernel.configure_project(root)?;
        }
        if payload["freshSession"] == true
            || payload["attachments"]
                .as_array()
                .is_some_and(|items| !items.is_empty())
        {
            return Err(
                "Fresh-session overrides and attachments have not yet been migrated.".into(),
            );
        }
        let defaults = kernel.config.effective()?;
        let session = if let Some(id) = payload["sessionId"].as_str().filter(|id| !id.is_empty()) {
            id.to_owned()
        } else {
            kernel
                .session_store()?
                .create(
                    None,
                    Map::from_iter([("runtime_config".into(), models::capture(&defaults))]),
                )?
                .id
        };
        let page = kernel.session_store()?.page(&session, None, 1)?;
        let snapshot = payload
            .get("configuration")
            .cloned()
            .or_else(|| page.metadata.get("runtime_config").cloned())
            .unwrap_or_else(|| models::capture(&defaults));
        let mut config = models::resolve(&defaults, &snapshot)?;
        if let Some(mode) = payload["mode"].as_str().filter(|mode| !mode.is_empty()) {
            config["mode"] = json!(mode);
        }
        if let Some(stream) = payload["stream"].as_bool() {
            config["stream_responses"] = json!(stream);
        }
        if config["mode"].as_str().unwrap_or("reverie") != "reverie" {
            return Err("This mode's full workflow has not yet been migrated.".into());
        }
        let model = models::active(&config)
            .ok_or("Select a configured model before running a prompt.")?
            .clone();
        let root = kernel.project_root.clone();
        let execution_root = match payload["executionRoot"].as_str() {
            Some(root) => crate::config::canonical_project(std::path::Path::new(root))?,
            None => root.clone(),
        };
        let data = kernel.project_data_dir.clone();
        let mut store = crate::session::SessionStore::open(&data, &root)?;
        let mut messages = store.history(&session)?;
        let history_count = messages.len();
        let no_index = payload["noIndex"].as_bool().unwrap_or(false);
        let context_key = kernel.context_key_for(&execution_root);
        let context = if !no_index && config["auto_index"].as_bool().unwrap_or(true) {
            Some(kernel.shared_context_for(&execution_root)?)
        } else {
            None
        };
        let (semantic, semantic_error) = match kernel.semantic.capture() {
            Ok(version) => (version, None),
            Err(error) => (None, Some(error.to_string())),
        };
        let user = json!({"role":"user","content":prompt});
        store.begin_run(
            &session,
            &id,
            &models::without_secrets(&snapshot),
            page.revision,
            &models::without_secrets(payload),
            &user,
        )?;
        messages.push(user);
        Ok(Run {
            session,
            session_name: page.name,
            id,
            root,
            execution_root,
            data,
            model,
            config,
            messages,
            prompt,
            no_index,
            history_count,
            rules: [
                snapshot["rules"].as_str().unwrap_or_default(),
                payload["goalContext"].as_str().unwrap_or_default(),
            ]
            .into_iter()
            .filter(|text| !text.is_empty())
            .collect::<Vec<_>>()
            .join("\n\n"),
            store: Mutex::new(store),
            context,
            context_key,
            semantic,
            semantic_error,
            reasoning: String::new(),
            activities: Vec::new(),
        })
    }

    pub fn begin_prompt(&self, payload: &Value) -> Result<PendingRun> {
        let mut active = lock(&self.active)?;
        let id = payload["runId"]
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| Uuid::new_v4().simple().to_string());
        if id.is_empty()
            || id.len() > 128
            || !id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
        {
            return Err("Invalid run identifier.".into());
        }
        if active.contains_key(&id) {
            return Err("A run with this identity is already active.".into());
        }
        let project = payload["projectRoot"]
            .as_str()
            .map(|root| crate::config::canonical_project(std::path::Path::new(root)))
            .transpose()?
            .unwrap_or(lock(&self.kernel)?.project_root.clone());
        if payload["sessionId"].as_str().is_some_and(|id| {
            active
                .values()
                .any(|control| control.session_id == id && control.project_root == project)
        }) {
            return Err("A run is already active for this conversation.".into());
        }
        let run = self.prepare(payload, id)?;
        let approved = lock(&self.grants)?
            .entry((run.root.clone(), run.session.clone()))
            .or_default()
            .clone();
        let control = Arc::new(RunControl {
            cancel: CancellationToken::new(),
            session_id: run.session.clone(),
            project_root: run.root.clone(),
            approvals: Mutex::new(HashMap::new()),
            questions: Mutex::new(HashMap::new()),
            approved,
        });
        active.insert(run.id.clone(), control.clone());
        Ok(PendingRun { run, control })
    }

    pub async fn complete_prompt(&self, id: Value, pending: PendingRun, sink: EventSink) -> Reply {
        match self.run_prompt(pending, sink).await {
            Ok(fields) => Reply::new(
                Some(id),
                "prompt.result",
                fields.as_object().cloned().unwrap_or_default(),
            ),
            Err(error) => Reply::error(id, error),
        }
    }

    async fn run_prompt(&self, pending: PendingRun, sink: EventSink) -> Result<Value> {
        let PendingRun { mut run, control } = pending;
        let started = Instant::now();
        let emit = |mut event: Value| {
            event["project_root"] = json!(run.root);
            event["session_id"] = json!(run.session);
            event["run_id"] = json!(run.id);
            sink(event);
        };
        emit(
            json!({"type":"run.started","prompt":run.prompt,"history_message_count":run.history_count}),
        );
        let execution = self.execute(&mut run, &control, &sink).await;
        let state = if execution.is_ok() {
            "completed"
        } else if control.cancel.is_cancelled() {
            "cancelled"
        } else {
            "failed"
        };
        let (output_text, error) = match execution {
            Ok(output) => (output, String::new()),
            Err(error) => (String::new(), error.to_string()),
        };
        let result = serde_json::to_value(PromptResult {
            success: state == "completed",
            prompt: run.prompt.clone(),
            output_text,
            thinking_text: run.reasoning.clone(),
            error,
            state: state.into(),
            mode: run.config["mode"].as_str().unwrap_or("reverie").into(),
            model_display_name: run.model["model_display_name"]
                .as_str()
                .or_else(|| run.model["model"].as_str())
                .unwrap_or_default()
                .into(),
            provider_label: run.model["provider"]
                .as_str()
                .unwrap_or("openai-chat")
                .into(),
            session_id: run.session.clone(),
            session_name: run.session_name.clone(),
            run_id: run.id.clone(),
            duration_seconds: started.elapsed().as_secs_f64(),
            ui_events: run.activities.clone(),
            activity_events: run.activities.clone(),
        })?;
        let finalized = lock(&run.store)
            .and_then(|mut store| store.finish_run(&run.session, &run.id, state, &result));
        lock(&self.active)?.remove(&run.id);
        finalized?;
        sink(
            json!({"type":"run.finished","state":state,"project_root":run.root,"session_id":run.session,"run_id":run.id}),
        );
        let (sessions, revision) = {
            let store = lock(&run.store)?;
            (store.list()?, store.run_revision(&run.session, &run.id)?)
        };
        Ok(
            json!({"result":result,"sessions":sessions,"recovery":{"summary":{"available":false},"operations":[],"checkpoints":[],"available":false},"run_revision":revision,"session_id":run.session,"run_id":run.id,"project_root":run.root}),
        )
    }

    async fn execute(
        &self,
        run: &mut Run,
        control: &RunControl,
        sink: &EventSink,
    ) -> Result<String> {
        let proxy = run.config["api_proxy"]
            .as_str()
            .unwrap_or_default()
            .to_owned();
        let client = {
            let mut clients = lock(&self.clients)?;
            if !clients.contains_key(&proxy) {
                clients.insert(proxy.clone(), Arc::new(ProviderClient::new(Some(&proxy))?));
            }
            clients[&proxy].clone()
        };
        let stream_error = Mutex::new(None::<String>);
        let emit = |mut event: Value| {
            let kind = match event["type"].as_str() {
                Some("assistant.delta") => Some("assistant"),
                Some("reasoning.delta") => Some("reasoning"),
                _ => None,
            };
            if let Some(kind) = kind {
                let saved = lock(&run.store).and_then(|store| {
                    store.write_stream(
                        &run.session,
                        &run.id,
                        kind,
                        event["text"].as_str().unwrap_or_default(),
                    )
                });
                if let Err(error) = saved {
                    if let Ok(mut failure) = stream_error.lock() {
                        *failure = Some(error.to_string());
                    }
                    control.cancel.cancel();
                }
            }
            event["project_root"] = json!(run.root);
            event["session_id"] = json!(run.session);
            event["run_id"] = json!(run.id);
            sink(event);
        };
        let mut context = String::new();
        if !run.no_index
            && let Some(engine) = &run.context
        {
            let engine = engine.clone();
            let cancel = control.cancel.clone();
            let prompt = run.prompt.clone();
            let semantic = run.semantic.clone();
            let (hits, mut retrieval) = tokio::task::spawn_blocking(move || {
                let engine = {
                    let mut engine = lock(&engine)?;
                    engine.index_with_cancel(false, &|| cancel.is_cancelled())?;
                    engine.fork()?
                };
                if cancel.is_cancelled() {
                    return Err("Run cancelled during context retrieval.".into());
                }
                crate::context_jobs::retrieve(
                    &engine,
                    semantic.as_deref(),
                    &prompt,
                    10,
                    12000,
                    "auto",
                    &|| cancel.is_cancelled(),
                )
            })
            .await??;
            if let Some(error) = run.semantic_error.as_ref() {
                retrieval["semantic_unavailable"] = json!(error);
            }
            emit(
                json!({"type":"context.retrieved","retrieval":retrieval,"evidence_count":hits.len()}),
            );
            for hit in hits {
                context.push_str(&format!(
                    "\n{}:{}-{} [sha256:{} revision:{}]\n{}\n",
                    hit.file_path,
                    hit.start_line,
                    hit.end_line,
                    hit.content_hash,
                    hit.revision,
                    hit.content
                ));
            }
        }
        run.messages.insert(0,json!({"role":"system","content":format!("You are Reverie, an assistant working in {}. Execute workspace tools in {}. Use the supplied workspace tools. Respect configured permissions, preserve files and report actual results. Ask a concise question with up to three options and a custom answer when required information is missing.\n{}\nWorkspace evidence:{}",run.root.display(),run.execution_root.display(),run.rules,context)}));
        let catalog = tool_catalog();
        for iteration in 0..64 {
            if control.cancel.is_cancelled() {
                return Err("Run cancelled.".into());
            }
            let turn = client
                .chat(
                    &run.model,
                    &run.config,
                    &run.messages,
                    &catalog,
                    &control.cancel,
                    &emit,
                )
                .await;
            if let Some(error) = lock(&stream_error)?.take() {
                return Err(format!("Could not preserve streamed output: {error}").into());
            }
            let turn = turn?;
            if control.cancel.is_cancelled() {
                return Err("Run cancelled.".into());
            }
            run.reasoning.push_str(&turn.reasoning);
            let calls=turn.tool_calls.values().map(|call|json!({"id":call.id,"type":"function","function":{"name":call.name,"arguments":call.arguments}})).collect::<Vec<_>>();
            let mut assistant = json!({"role":"assistant","content":turn.content});
            if !calls.is_empty() {
                assistant["tool_calls"] = json!(calls);
            }
            if !turn.reasoning.is_empty() {
                assistant["reasoning_content"] = json!(turn.reasoning);
            }
            if let Some(native) = turn.native {
                assistant["provider_content"] = native;
            }
            lock(&run.store)?.append(
                &run.session,
                &format!("{}:assistant:{iteration}", run.id),
                std::slice::from_ref(&assistant),
            )?;
            lock(&run.store)?.clear_stream(&run.session, &run.id)?;
            run.messages.push(assistant);
            if !turn.usage.is_null() {
                emit(json!({"type":"model.usage","usage":turn.usage}));
            }
            if turn.tool_calls.is_empty() {
                return Ok(turn.content);
            }
            for (index, call) in turn.tool_calls {
                let mut result = if control.cancel.is_cancelled() {
                    ToolResult::not_started("Run cancelled before this tool started.")
                } else {
                    match serde_json::from_str::<Value>(&call.arguments) {
                        Ok(arguments) => {
                            emit(
                                json!({"type":"ui.event","event":{"event":"tool_start","type":"tool_start","tool_name":call.name,"tool_call_id":call.id,"arguments":arguments}}),
                            );
                            match self.tool(run, control, &call, &arguments, &emit).await {
                                Ok(result) => result,
                                Err(error) if control.cancel.is_cancelled() => {
                                    ToolResult::not_started(error)
                                }
                                Err(error) => ToolResult::fail(error),
                            }
                        }
                        Err(_) => ToolResult::fail("Tool arguments must be valid JSON."),
                    }
                };
                if reverie_platform::command::is_command(&call.name)
                    && result.data["delivery"].is_null()
                {
                    result.data["delivery"] = json!("not_started");
                    let arguments =
                        serde_json::from_str::<Value>(&call.arguments).unwrap_or(Value::Null);
                    if let Err(error) = reverie_platform::command::audit(
                        &run.data,
                        json!({"event":"command_blocked","allowed":false,"command":arguments["command"],"cwd":arguments["cwd"],"run_id":run.id,"session_id":run.session,"reason":result.error,"delivery":"not_started"}),
                    ) {
                        result.data["audit_error"] = json!(error.to_string());
                    }
                }
                let activity = json!({"event":"tool_result","type":"tool_result","tool_name":call.name,"tool_call_id":call.id,"success":result.success,"output":result.output,"error":result.error,"status":result.status,"data":result.data});
                emit(json!({"type":"ui.event","event":activity}));
                run.activities.push(activity);
                let tool = json!({"role":"tool","tool_call_id":call.id,"name":call.name,"content":serde_json::to_string(&result)?});
                lock(&run.store)?.append(
                    &run.session,
                    &format!("{}:tool:{iteration}:{index}", run.id),
                    std::slice::from_ref(&tool),
                )?;
                run.messages.push(tool);
            }
        }
        Err("Run reached the supported tool-iteration limit without a final response.".into())
    }

    async fn tool(
        &self,
        run: &Run,
        control: &RunControl,
        call: &ToolCall,
        args: &Value,
        emit: &impl Fn(Value),
    ) -> Result<ToolResult> {
        if !args.is_object() {
            return Err("Tool arguments must be an object.".into());
        }
        if call.name == "userInput" {
            let question = args["question"]
                .as_str()
                .filter(|question| !question.trim().is_empty())
                .ok_or("A question is required.")?;
            let options = args["options"].as_array().cloned().unwrap_or_default();
            if options.len() > 3
                || options
                    .iter()
                    .any(|option| option.as_str().is_none_or(|text| text.trim().is_empty()))
            {
                return Err("Use at most three options plus a custom answer.".into());
            }
            let id = Uuid::new_v4().simple().to_string();
            let (sender, receiver) = oneshot::channel();
            lock(&control.questions)?.insert(id.clone(), Waiter { sender });
            lock(&run.store)?.set_running_state(&run.session, &run.id, "waiting_user")?;
            emit({
                let mut event = serde_json::to_value(reverie_protocol::UserQuestion {
                    question_id: id.clone(),
                    question: question.into(),
                    reason: args["reason"].as_str().unwrap_or_default().into(),
                    options: options
                        .into_iter()
                        .map(|option| option.as_str().unwrap().to_owned())
                        .collect(),
                    custom_answer: true,
                    multiple: args["multiple"].as_bool().unwrap_or(false),
                })?;
                event["type"] = json!("user.question");
                event
            });
            let answer = tokio::select! {_=control.cancel.cancelled()=>Err("Run cancelled while waiting for user input."),answer=receiver=>answer.map_err(|_|"User question is no longer active.")};
            lock(&control.questions)?.remove(&id);
            let answer = answer?;
            lock(&run.store)?.set_running_state(&run.session, &run.id, "running")?;
            emit(json!({"type":"run.control","state":"running"}));
            if answer["cancelled"] == true {
                return Err("User cancelled the question.".into());
            }
            let response = answer["answer"]
                .as_str()
                .filter(|answer| !answer.trim().is_empty())
                .ok_or("Explicit user answer is required.")?
                .to_owned();
            return Ok(ToolResult::ok(response, answer));
        }
        let read_only = reverie_platform::is_read_only(&call.name, args);
        let level = run.config["security"]["permission_level"]
            .as_str()
            .unwrap_or("full_control");
        if level == "read_only" && !read_only {
            return Err("Configured permission level does not allow this write tool.".into());
        }
        if !["read_only", "workspace_write", "developer", "full_control"].contains(&level) {
            return Err("Invalid configured permission level.".into());
        }
        let mode = run.config["security"]["permission_mode"]
            .as_str()
            .unwrap_or("default");
        if mode == "auto_check" {
            return Err("Automatic model approval review has not yet been migrated.".into());
        }
        if mode == "strict"
            && !(read_only && run.config["security"]["strict_allow_read_only"] == true)
            && !lock(&control.approved)?.contains(&call.name)
        {
            let id = Uuid::new_v4().simple().to_string();
            let (sender, receiver) = oneshot::channel();
            lock(&control.approvals)?.insert(id.clone(), Waiter { sender });
            lock(&run.store)?.set_running_state(&run.session, &run.id, "waiting_user")?;
            emit(
                json!({"type":"approval.request","approval_id":id,"tool":call.name,"arguments":args,"read_only":read_only,"permission_mode":mode,"scopes":["once","session"],"paths":[args["path"]]}),
            );
            let answer = tokio::select! {_=control.cancel.cancelled()=>Err("Run cancelled while waiting for approval."),answer=receiver=>answer.map_err(|_|"Approval is no longer active.")};
            lock(&control.approvals)?.remove(&id);
            let answer = answer?;
            lock(&run.store)?.set_running_state(&run.session, &run.id, "running")?;
            emit(json!({"type":"run.control","state":"running"}));
            match answer["decision"].as_str() {
                Some("once") => {}
                Some("session") => {
                    lock(&control.approved)?.insert(call.name.clone());
                }
                Some("message") => {
                    return Err(format!(
                        "The user declined this {} call and replied: {}",
                        call.name,
                        answer["message"].as_str().unwrap_or_default()
                    )
                    .into());
                }
                _ => return Err("User denied the tool request.".into()),
            }
        } else if mode != "default" && mode != "strict" {
            return Err("Invalid configured permission mode.".into());
        }
        if control.cancel.is_cancelled() {
            return Err("Run cancelled before tool execution.".into());
        }
        if [
            "codebase-retrieval",
            "codebase_retrieval",
            "retrieve_codebase",
            "repo_context",
        ]
        .contains(&call.name.as_str())
        {
            let engine = match &run.context {
                Some(engine) => engine.clone(),
                None => {
                    lock(&self.kernel)?.shared_context_at(&run.execution_root, &run.context_key)?
                }
            };
            let arguments = args.clone();
            let cancel = control.cancel.clone();
            let semantic = run.semantic.clone();
            let details = tokio::task::spawn_blocking(move || -> Result<Value> {
                let engine = {
                    let mut engine = lock(&engine)?;
                    engine.index_with_cancel(false, &|| cancel.is_cancelled())?;
                    engine.fork()?
                };
                if cancel.is_cancelled() {
                    return Err("Run cancelled during context lookup.".into());
                }
                if ["task", "explore"]
                    .contains(&arguments["query_type"].as_str().unwrap_or_default())
                    && let Some(version) = semantic.as_ref()
                    && engine
                        .semantic_status_for(&version.selection.manifest_sha256)?
                        .is_some()
                {
                    let models = version.models(&|| cancel.is_cancelled())?;
                    engine.lookup_hybrid(&models, &arguments, &|| cancel.is_cancelled())
                } else {
                    engine.lookup(&arguments)
                }
            })
            .await??;
            let metadata = json!({"backend":"rust","query_type":details["query_type"],"revision":details["revision"],"symbol":details["symbol"]["qualified_name"],"file":details["file"].as_str().or_else(||details["symbol"]["file_path"].as_str()),"line":details["symbol"]["start_line"]});
            return Ok(ToolResult::ok(
                serde_json::to_string_pretty(&details)?,
                metadata,
            ));
        }
        let mut arguments = args.clone();
        if run.root != run.execution_root
            && let Some(path) = args["path"]
                .as_str()
                .and_then(|path| std::path::Path::new(path).strip_prefix(&run.root).ok())
        {
            arguments["path"] = json!(run.execution_root.join(path));
        }
        if reverie_platform::command::is_command(&call.name) {
            if run.root != run.execution_root
                && let Some(path) = args["cwd"]
                    .as_str()
                    .and_then(|path| std::path::Path::new(path).strip_prefix(&run.root).ok())
            {
                arguments["cwd"] = json!(run.execution_root.join(path));
            }
            return Ok(reverie_platform::command::execute(
                &arguments,
                &run.execution_root,
                &run.data,
                &control.cancel,
                &|stream, text| emit(json!({"type":"ui.event","event":{"event":"tool_progress","kind":"tool_progress","type":"tool_progress","tool_name":call.name,"tool_call_id":call.id,"stream":stream,"text":text}})),
            ).await);
        }
        Ok(reverie_platform::execute(
            &call.name,
            &arguments,
            &run.execution_root,
            &run.data.join("tools/file-backups").join(&run.id),
        ))
    }
}

pub fn tool_catalog() -> Vec<Value> {
    let mut tools = reverie_platform::tools();
    tools.push(json!({"type":"function","function":{"name":"codebase-retrieval","description":"Inspect the active workspace before repository-dependent answers or edits. Use task for a broad bounded evidence workset, then symbol, file, search, outline or dependencies. Evidence includes content hashes and at most 72 source lines. Dependency targets distinguish lexical matches, inference, ambiguity and unresolved names. Memory and LSP queries are still being migrated.","parameters":{"type":"object","properties":{"query_type":{"type":"string","enum":["symbol","file","search","dependencies","outline","explore","task"]},"query":{"type":"string"},"include_source":{"type":"boolean","default":true},"include_dependencies":{"type":"boolean","default":true},"max_depth":{"type":"integer","minimum":0,"default":2},"filter_kind":{"type":"string","default":"all"},"direction":{"type":"string","enum":["incoming","outgoing","both"]},"limit":{"type":"integer","default":20},"max_files":{"type":"integer","default":6},"max_symbols":{"type":"integer","default":12},"max_tokens":{"type":"integer","default":12000},"include_history":{"type":"boolean"},"include_memory":{"type":"boolean"},"active_files":{"type":"array","items":{"type":"string"}},"changed_files":{"type":"array","items":{"type":"string"}}},"required":["query_type","query"]}}}));
    tools.push(json!({"type":"function","function":{"name":"userInput","description":"Ask a concise clarification with up to three options and a custom answer. Wait for the user's explicit response; this does not approve workspace tools.","parameters":{"type":"object","properties":{"question":{"type":"string"},"reason":{"type":"string"},"options":{"type":"array","items":{"type":"string"},"maxItems":3},"multiple":{"type":"boolean"}},"required":["question","reason"]}}}));
    tools
}
