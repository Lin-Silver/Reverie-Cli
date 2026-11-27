use crate::{
    Kernel, Result, models, modes,
    provider::{ProviderClient, ToolCall},
};
use reverie_platform::ToolResult;
use reverie_protocol::{PromptResult, Reply, Request};
use serde_json::{Map, Value, json};
use std::{
    collections::{HashMap, VecDeque},
    path::PathBuf,
    sync::{Arc, Mutex, MutexGuard},
    time::Instant,
};
use tokio::sync::oneshot;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

mod extensions;
pub use extensions::PendingExtension;
mod catalog;
pub use catalog::{tool_catalog, tool_catalog_for};
mod aio;
pub use aio::PendingAioDecision;
mod approval;
mod browser;
mod context;
mod pending;
pub use context::PendingCompaction;
pub(crate) use context::usage as describe_context_usage;

pub type EventSink = Arc<dyn Fn(Value) + Send + Sync>;

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
    commit_gate: Mutex<()>,
    pub session_id: String,
    pub project_root: PathBuf,
    assistant: bool,
    approvals: Mutex<HashMap<String, Waiter>>,
    approval_ready: tokio::sync::Notify,
    questions: Mutex<HashMap<String, Waiter>>,
}

impl RunControl {
    fn request_cancel(&self) -> Result<()> {
        let _commit = lock(&self.commit_gate)?;
        self.cancel.cancel();
        Ok(())
    }
}

struct Run {
    session: String,
    session_name: String,
    id: String,
    root: PathBuf,
    execution_root: PathBuf,
    data: PathBuf,
    grants: Mutex<Option<crate::permissions::Grants>>,
    app: PathBuf,
    model: Value,
    config: Value,
    messages: Vec<Value>,
    prompt: String,
    no_index: bool,
    history_count: usize,
    rules: String,
    store: Arc<Mutex<crate::session::SessionStore>>,
    context: Option<Arc<Mutex<reverie_context::ContextEngine>>>,
    context_key: PathBuf,
    monitor_configuration: PathBuf,
    skills: Mutex<Arc<crate::skills::SkillCatalog>>,
    pinned_skills: Vec<String>,
    writer_project: Mutex<Option<Value>>,
    wstyle_snapshot: Mutex<Value>,
    assistant: bool,
    plugins: Vec<Arc<crate::plugins::PluginLease>>,
    mcp_servers: Vec<crate::mcp::ServerConfig>,
    mcp_diagnostics: Vec<Value>,
    mcp: Mutex<Option<Arc<crate::mcp::McpSnapshot>>>,
    local_browser: tokio::sync::OnceCell<browser::Component>,
    semantic: Option<Arc<crate::semantic_resources::ModelVersion>>,
    semantic_error: Option<String>,
    reasoning: String,
    activities: Vec<Value>,
}

impl Run {
    fn command_cwd(&self, args: &Value) -> PathBuf {
        let cwd = std::path::Path::new(args["cwd"].as_str().unwrap_or("."));
        let relative = if self.root != self.execution_root {
            cwd.strip_prefix(&self.root).unwrap_or(cwd)
        } else {
            cwd
        };
        self.execution_root.join(relative)
    }
}

pub struct PendingRun {
    run: Run,
    control: Arc<RunControl>,
}

pub struct KernelHost {
    pub(crate) kernel: Mutex<Kernel>,
    active: Mutex<HashMap<String, Arc<RunControl>>>,
    clients: Mutex<HashMap<String, Arc<ProviderClient>>>,
    market_jobs: Mutex<HashMap<String, CancellationToken>>,
    plugin_jobs: Mutex<HashMap<String, CancellationToken>>,
    mcp: Arc<crate::mcp::McpRuntime>,
    browsers: browser::Browsers,
    browser_component: Option<PathBuf>,
    connectors: Mutex<Option<Arc<crate::connectors::ConnectorManager>>>,
    aio: Mutex<Option<modes::aio::AioStore>>,
    aio_last_decision: Mutex<Option<Instant>>,
    pub(crate) context_jobs: Mutex<HashMap<String, Arc<crate::context_jobs::ContextControl>>>,
    pub(crate) context_cancel: CancellationToken,
}

impl KernelHost {
    pub fn new(kernel: Kernel) -> Self {
        Self {
            kernel: Mutex::new(kernel),
            active: Mutex::new(HashMap::new()),
            clients: Mutex::new(HashMap::new()),
            market_jobs: Mutex::new(HashMap::new()),
            plugin_jobs: Mutex::new(HashMap::new()),
            mcp: Arc::new(crate::mcp::McpRuntime::new()),
            browsers: browser::Browsers::default(),
            browser_component: None,
            connectors: Mutex::new(None),
            aio: Mutex::new(None),
            aio_last_decision: Mutex::new(None),
            context_jobs: Mutex::new(HashMap::new()),
            context_cancel: CancellationToken::new(),
        }
    }

    pub fn cancel_all(&self) {
        self.browsers.close();
        self.context_cancel.cancel();
        self.mcp.cancel_all();
        if let Ok(connectors) = self.connectors.lock()
            && let Some(connectors) = connectors.as_ref()
        {
            connectors.cancel_all();
        }
        if let Ok(active) = self.active.lock() {
            for control in active.values() {
                let _ = control.request_cancel();
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
        if Self::is_extension_async_action(&request.action) {
            return match self.begin_plugin_operation(&request.action, &request.payload) {
                Ok(pending) => {
                    Box::pin(self.complete_plugin_operation(request.id, pending, sink)).await
                }
                Err(error) => Reply::error(request.id, error),
            };
        }
        if Self::is_context_action(&request.action) {
            return match self.begin_context_job(&request.action, &request.payload) {
                Ok(job) => Box::pin(self.complete_context_job(request.id, job, sink)).await,
                Err(error) => Reply::error(request.id, error),
            };
        }
        let id = request.id.clone();
        let result = match request.action.as_str() {
            action @ ("registerBrowserHost"
            | "unregisterBrowserHost"
            | "completeBrowserRequest"
            | "invalidateBrowserTab") => self.browsers.control(action, &request.payload, sink),
            "refreshMarket" => {
                let refresh = self.refresh_market(&request.payload).await;
                refresh.map(|value| ("market.entries", value))
            }
            "stopMarketRefresh" => (|| -> Result<_> {
                let name = request.payload["market_id"]
                    .as_str()
                    .ok_or("market_id is required.")?;
                let jobs = lock(&self.market_jobs)?;
                let job = jobs
                    .get(name)
                    .ok_or("Marketplace refresh is no longer active.")?;
                job.cancel();
                Ok(("market.control", json!({"market_id":name,"cancelled":true})))
            })(),
            "stopPluginOperation" => self.stop_plugin_operation(&request.payload),
            "cancelConnectorAuthorization" => (|| -> Result<_> {
                let id = request.payload["authorization_id"]
                    .as_str()
                    .ok_or("authorization_id is required.")?;
                self.connector_manager()?.cancel_authorization(id)?;
                Ok((
                    "connector.control",
                    json!({"authorization_id":id,"cancelled":true}),
                ))
            })(),
            "shutdown" => {
                self.browsers.close();
                self.close_extensions().await;
                return lock(&self.kernel)
                    .map(|mut kernel| kernel.dispatch(request))
                    .unwrap_or_else(|error| Reply::error(id, error));
            }
            "getSemanticResources" => self.semantic_inventory(),
            "stopContextOperation" => self.stop_context_job(&request.payload),
            "runPrompt" => match self.begin_prompt(&request.payload) {
                Ok(pending) => return Box::pin(self.complete_prompt(id, pending, sink)).await,
                Err(error) => return Reply::error(id, error),
            },
            "resumePrompt" => match self.begin_resume(&request.payload) {
                Ok(pending) => return Box::pin(self.complete_prompt(id, pending, sink)).await,
                Err(error) => return Reply::error(id, error),
            },
            "compactContext" => match self.begin_compaction(&request.payload) {
                Ok(pending) => return Box::pin(self.complete_compaction(id, pending, sink)).await,
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
            "wstyleCommand" => match Box::pin(self.wstyle_command(&request.payload, sink)).await {
                Ok(result) => Ok(("wstyle.result", result)),
                Err(error) => Ok((
                    "wstyle.result",
                    json!({"success":false,"output":"","error":error.to_string(),"data":{},"session_id":request.payload["sessionId"].as_str().unwrap_or("")}),
                )),
            },
            "aioDecision" => match self.begin_aio_decision(&request.payload) {
                Ok(pending) => {
                    return Box::pin(self.complete_aio_decision(request.id, pending, sink)).await;
                }
                Err(error) => return Reply::error(request.id, error),
            },
            action if Self::is_aio_action(action) => self.aio_action(action, &request.payload),
            _ => match lock(&self.kernel) {
                Ok(mut kernel) => {
                    let action = request.action.clone();
                    let mut reply = kernel.dispatch(request);
                    if reply.kind != "error" && action != "shutdown" {
                        if let Err(error) = kernel.sync_current_monitor(&self.context_cancel, sink)
                        {
                            reply
                                .fields
                                .insert("watcher_error".into(), json!(error.to_string()));
                        }
                        let watcher = kernel
                            .monitors
                            .get(&kernel.project_data_dir)
                            .map(|monitor| monitor.status());
                        if let Some(watcher) = watcher {
                            if let Some(target) = reply.fields.get_mut("context_engine") {
                                target["watcher"] = watcher.clone();
                            }
                            if let Some(target) = reply
                                .fields
                                .get_mut("workspace")
                                .and_then(|workspace| workspace.get_mut("context_engine"))
                            {
                                target["watcher"] = watcher.clone();
                            }
                            if let Some(target) = reply
                                .fields
                                .get_mut("state")
                                .and_then(|state| state.get_mut("workspace"))
                                .and_then(|workspace| workspace.get_mut("context_engine"))
                            {
                                target["watcher"] = watcher;
                            }
                        }
                    }
                    return reply;
                }
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

    async fn refresh_market(&self, payload: &Value) -> Result<Value> {
        let pending = self.begin_market_refresh(payload)?;
        self.finish_market_refresh(pending).await
    }

    pub fn begin_market_refresh(
        &self,
        payload: &Value,
    ) -> Result<(PathBuf, reverie_protocol::MarketRequest, CancellationToken)> {
        let request: reverie_protocol::MarketRequest = serde_json::from_value(payload.clone())?;
        let app = lock(&self.kernel)?.app_root.clone();
        let token = self.context_cancel.child_token();
        {
            let mut jobs = lock(&self.market_jobs)?;
            if jobs.contains_key(&request.market_id) {
                return Err("This marketplace is already refreshing.".into());
            }
            jobs.insert(request.market_id.clone(), token.clone());
        }
        Ok((app, request, token))
    }

    async fn finish_market_refresh(
        &self,
        (app, request, token): (PathBuf, reverie_protocol::MarketRequest, CancellationToken),
    ) -> Result<Value> {
        let id = request.market_id.clone();
        let result = crate::markets::refresh(&app, request, &token).await;
        lock(&self.market_jobs)?.remove(&id);
        result
    }

    pub async fn complete_market_refresh(
        &self,
        id: Value,
        pending: (PathBuf, reverie_protocol::MarketRequest, CancellationToken),
    ) -> Reply {
        match self.finish_market_refresh(pending).await {
            Ok(value) => Reply::new(
                Some(id),
                "market.entries",
                value.as_object().cloned().unwrap_or_default(),
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
                control.request_cancel()?;
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
            if !payload["decision"].as_str().is_some_and(|decision| {
                ["once", "session", "project", "global", "deny", "message"].contains(&decision)
            }) {
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
                if !question {
                    control.approval_ready.notify_one();
                }
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

    pub fn is_mode_async_action(action: &str) -> bool {
        matches!(action, "wstyleCommand" | "aioDecision")
    }

    async fn text_model(
        &self,
        model: &Value,
        configuration: &Value,
        messages: &[Value],
        cancel: &CancellationToken,
        emit: &impl Fn(Value),
    ) -> Result<String> {
        let proxy = configuration["api_proxy"].as_str().unwrap_or("").to_owned();
        let client = {
            let mut clients = lock(&self.clients)?;
            if !clients.contains_key(&proxy) {
                clients.insert(proxy.clone(), Arc::new(ProviderClient::new(Some(&proxy))?));
            }
            clients[&proxy].clone()
        };
        let mut configuration = configuration.clone();
        configuration["stream_responses"] = json!(false);
        let result = client
            .chat(model, &configuration, messages, &[], cancel, emit)
            .await?;
        if !result.tool_calls.is_empty() {
            return Err(
                "This model decision/review has no execution tools; no calls were dispatched."
                    .into(),
            );
        }
        Ok(result.content)
    }

    async fn wstyle_command(&self, payload: &Value, sink: EventSink) -> Result<Value> {
        let (app, root, session, offline_configuration, defaults, snapshot, mut selected) = {
            let active = lock(&self.active)?;
            let mut kernel = lock(&self.kernel)?;
            if let Some(root) = payload["projectRoot"].as_str() {
                kernel.configure_project(root)?;
            }
            let session = payload["sessionId"]
                .as_str()
                .map(str::to_owned)
                .or_else(|| kernel.view_session.clone())
                .unwrap_or_default();
            if active.values().any(|control| {
                control.project_root == kernel.project_root
                    && (session.is_empty() || control.session_id == session)
            }) {
                return Err(
                    "Stop the active conversation run before executing a WStyle command.".into(),
                );
            }
            let defaults = kernel.config.effective()?;
            let page = if session.is_empty() {
                None
            } else {
                Some(kernel.session_store()?.page(&session, None, 1)?)
            };
            let snapshot = page
                .as_ref()
                .and_then(|page| page.metadata.get("runtime_config"))
                .cloned();
            let mut configuration = defaults.clone();
            if let Some(snapshot) = &snapshot {
                for key in ["mode", "max_context_tokens"] {
                    if let Some(value) = snapshot["settings"].get(key) {
                        configuration[key] = value.clone();
                    }
                }
            }
            if modes::normalize(configuration["mode"].as_str().unwrap_or("reverie"))? != "writer" {
                return Err("/wstyle is available only in Writer mode.".into());
            }
            let selected = page
                .as_ref()
                .and_then(|page| page.metadata.get("writer_project"))
                .cloned()
                .or(modes::infer_writer_binding(&kernel.project_root)?);
            (
                kernel.app_root.clone(),
                kernel.project_root.clone(),
                session,
                configuration,
                defaults,
                snapshot,
                selected,
            )
        };
        let command = modes::wstyle::command(payload["args"].as_str().unwrap_or(""))?;
        modes::wstyle::select_binding(&root, &mut selected, &command)?;
        let result = if let Some(result) = modes::wstyle::offline(
            &app,
            &root,
            &offline_configuration,
            selected.as_ref(),
            &command,
        )? {
            result
        } else {
            let configuration = if let Some(snapshot) = snapshot {
                models::resolve(&defaults, &snapshot)?
            } else {
                defaults
            };
            let mut model = models::active(&configuration)
                .cloned()
                .ok_or("Select an available model before WStyle review/extraction.")?;
            let request =
                modes::wstyle::model_request(&app, &root, &configuration, &mut selected, &command)?;
            let budget = model["max_output_tokens"]
                .as_u64()
                .or_else(|| model["max_tokens"].as_u64())
                .unwrap_or(request.max_tokens)
                .min(request.max_tokens);
            model["max_output_tokens"] = json!(budget);
            model["max_tokens"] = json!(budget);
            let id = format!("wstyle-{}", Uuid::new_v4().simple());
            let control = Arc::new(RunControl {
                cancel: self.context_cancel.child_token(),
                commit_gate: Mutex::new(()),
                session_id: session.clone(),
                project_root: root.clone(),
                assistant: false,
                approval_ready: Default::default(),
                approvals: Mutex::new(HashMap::new()),
                questions: Mutex::new(HashMap::new()),
            });
            {
                let mut active = lock(&self.active)?;
                if active.values().any(|control| {
                    control.project_root == root
                        && (session.is_empty() || control.session_id == session)
                }) {
                    return Err(
                        "Stop the active conversation run before executing a WStyle command."
                            .into(),
                    );
                }
                active.insert(id.clone(), control.clone());
            }
            let emit = |mut event: Value| {
                event["project_root"] = json!(root);
                event["session_id"] = json!(session);
                event["run_id"] = json!(id);
                sink(event);
            };
            emit(
                json!({"type":"wstyle.started","action":command.action,"diagnostics_path":request.folder}),
            );
            let messages = vec![
                json!({"role":"system","content":request.system}),
                json!({"role":"user","content":serde_json::to_string(&request.user)?}),
            ];
            let execution = self
                .text_model(&model, &configuration, &messages, &control.cancel, &emit)
                .await;
            lock(&self.active)?.remove(&id);
            let result = match execution {
                Ok(raw) if !control.cancel.is_cancelled() => {
                    modes::wstyle::model_result(&request, &raw, &model)
                }
                Ok(_) => Err(
                    "WStyle operation was cancelled; source and diagnostics were preserved.".into(),
                ),
                Err(error) => Err(error),
            };
            let result = match result {
                Ok(result) => result,
                Err(error) => {
                    modes::wstyle::failure(&request, &error.to_string())?;
                    return Err(format!(
                        "WStyle failed: {error}. Sources and diagnostics: {}",
                        request.folder.display()
                    )
                    .into());
                }
            };
            emit(json!({"type":"wstyle.finished","action":command.action,"success":true}));
            result
        };
        if !session.is_empty()
            && let Some(binding) = selected
        {
            let mut kernel = lock(&self.kernel)?;
            kernel.configure_project(root.to_str().ok_or("Project root is not UTF-8.")?)?;
            let store = kernel.session_store()?;
            let page = store.page(&session, None, 1)?;
            if page.metadata.get("writer_project") != Some(&binding) {
                store.update_metadata(
                    &session,
                    Map::from_iter([("writer_project".into(), binding)]),
                    page.revision,
                )?;
            }
        }
        Ok(
            json!({"success":result["success"],"output":result["output"],"error":"","data":result["data"],"session_id":session}),
        )
    }

    fn prepare(
        &self,
        payload: &Value,
        id: String,
        resumed: Option<&context::ResumedUser>,
    ) -> Result<Run> {
        let prompt = payload["prompt"]
            .as_str()
            .or_else(|| payload["message"].as_str())
            .filter(|prompt| !prompt.trim().is_empty())
            .ok_or("Prompt must contain text.")?
            .to_owned();
        let mut kernel = lock(&self.kernel)?;
        kernel.configure_assistant(payload)?;
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
            let pins = kernel.pinned_skills(None)?;
            let mut snapshot = models::capture(&defaults);
            snapshot["pinned_skills"] = json!(pins);
            kernel
                .session_store()?
                .create(
                    None,
                    Map::from_iter([
                        ("runtime_config".into(), snapshot),
                        ("pinned_skills".into(), json!(pins)),
                    ]),
                )?
                .id
        };
        let mut page = kernel.session_store()?.page(&session, None, 1)?;
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
        let mode = modes::normalize(config["mode"].as_str().unwrap_or("reverie"))?;
        config["mode"] = json!(mode);
        let model = models::active(&config)
            .ok_or("Select a configured model before running a prompt.")?
            .clone();
        let root = kernel.project_root.clone();
        let execution_root = match payload["executionRoot"].as_str() {
            Some(root) => crate::config::canonical_project(std::path::Path::new(root))?,
            None => root.clone(),
        };
        let mode_guidance = modes::guidance(mode, &execution_root, &config)?;
        let pinned_skills = kernel.pinned_skills(Some(&session))?;
        if pinned_skills.len() > crate::skills::MAX_PINNED {
            return Err("A conversation can pin at most four skills.".into());
        }
        let skills = kernel.skill_catalog_at(
            &execution_root,
            config["mode"].as_str().unwrap_or("reverie"),
            true,
        )?;
        let assistant = kernel.assistant_mode;
        let data = if assistant {
            modes::aio::data_directory(&kernel.app_root)
        } else {
            kernel.project_data_dir.clone()
        };
        let mut store = if assistant {
            crate::session::SessionStore::open_assistant(&data)?
        } else {
            crate::session::SessionStore::open(&data, &root)?
        };
        let writer_project = if mode == "writer" {
            page.metadata
                .get("writer_project")
                .cloned()
                .or(modes::infer_writer_binding(&execution_root)?)
        } else {
            None
        };
        let mut resumed_source = resumed.map(|saved| saved.source.clone());
        if mode == "writer"
            && let Some(binding) = writer_project.as_ref()
            && page.metadata.get("writer_project") != Some(binding)
        {
            if let Some(source) = resumed_source.as_ref() {
                resumed_source = Some(store.bind_resumed_writer(source, binding)?.source);
            } else {
                store.update_metadata(
                    &session,
                    Map::from_iter([("writer_project".into(), binding.clone())]),
                    page.revision,
                )?;
            }
            page = store.page(&session, None, 1)?;
        }
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
        let user = resumed
            .map(|saved| saved.message.clone())
            .unwrap_or_else(|| json!({"role":"user","content":prompt}));
        let mut saved_request = models::without_secrets(payload);
        saved_request["executionRoot"] = json!(execution_root);
        let plugins = skills.plugin_leases();
        let mcp_configuration = extensions::mcp_configuration(&kernel.app_root, &config, &plugins)?;
        if let Some(saved) = resumed {
            store.begin_resumed_run(
                resumed_source.as_ref().unwrap(),
                saved.sequence,
                &id,
                &models::without_secrets(&snapshot),
                &saved_request,
                &user,
            )?;
        } else {
            store.begin_run(
                &session,
                &id,
                &models::without_secrets(&snapshot),
                page.revision,
                &saved_request,
                &user,
            )?;
        }
        if resumed.is_none() && payload["promptAlreadySaved"] != true {
            messages.push(user);
        }
        Ok(Run {
            session,
            session_name: page.name,
            id,
            root,
            execution_root,
            data,
            app: kernel.app_root.clone(),
            grants: Mutex::new(None),
            model,
            config,
            messages,
            prompt,
            no_index,
            history_count,
            rules: [
                snapshot["rules"].as_str().unwrap_or_default(),
                payload["goalContext"].as_str().unwrap_or_default(),
                mode_guidance.as_str(),
            ]
            .into_iter()
            .filter(|text| !text.is_empty())
            .collect::<Vec<_>>()
            .join("\n\n"),
            store: Arc::new(Mutex::new(store)),
            context,
            context_key,
            monitor_configuration: kernel.config.path.clone(),
            skills: Mutex::new(skills),
            pinned_skills,
            writer_project: Mutex::new(writer_project),
            wstyle_snapshot: Mutex::new(json!({"cards":[],"source":"base_writer"})),
            assistant,
            plugins,
            mcp_servers: mcp_configuration.servers,
            mcp_diagnostics: mcp_configuration.diagnostics,
            mcp: Mutex::new(None),
            local_browser: tokio::sync::OnceCell::new(),
            semantic,
            semantic_error,
            reasoning: String::new(),
            activities: Vec::new(),
        })
    }

    pub fn begin_prompt(&self, payload: &Value) -> Result<PendingRun> {
        self.begin_prompt_kind(payload, false)
    }

    pub fn begin_resume(&self, payload: &Value) -> Result<PendingRun> {
        self.begin_prompt_kind(payload, true)
    }

    fn begin_prompt_kind(&self, payload: &Value, resume: bool) -> Result<PendingRun> {
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
            active.values().any(|control| {
                control.session_id == id
                    && control.assistant == (payload["assistantId"] == "aio")
                    && (control.assistant || control.project_root == project)
            })
        }) {
            return Err("A run is already active for this conversation.".into());
        }
        let resumed = if resume {
            Some(self.resumed_user(payload)?)
        } else {
            None
        };
        let mut request = payload.clone();
        if let Some(saved) = resumed.as_ref() {
            request["prompt"] = saved.message["content"].clone();
        }
        let run = self.prepare(&request, id, resumed.as_ref())?;
        let control = Arc::new(RunControl {
            cancel: CancellationToken::new(),
            commit_gate: Mutex::new(()),
            session_id: run.session.clone(),
            project_root: run.root.clone(),
            assistant: run.assistant,
            approval_ready: Default::default(),
            approvals: Mutex::new(HashMap::new()),
            questions: Mutex::new(HashMap::new()),
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
        let execution = Box::pin(self.execute(&mut run, &control, &sink)).await;
        if let Some(component) = run.local_browser.take() {
            component.close().await;
        }
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
        let stream_store = run.store.clone();
        let event_session = run.session.clone();
        let event_run = run.id.clone();
        let event_project = run.root.clone();
        let emit = |mut event: Value| {
            let kind = match event["type"].as_str() {
                Some("assistant.delta") => Some("assistant"),
                Some("reasoning.delta") => Some("reasoning"),
                _ => None,
            };
            if let Some(kind) = kind {
                let saved = lock(&stream_store).and_then(|store| {
                    store.write_stream(
                        &event_session,
                        &event_run,
                        kind,
                        event["text"].as_str().unwrap_or_default(),
                    )
                });
                if let Err(error) = saved {
                    if let Ok(mut failure) = stream_error.lock() {
                        *failure = Some(error.to_string());
                    }
                    let _ = control.request_cancel();
                }
            }
            event["project_root"] = json!(event_project);
            event["session_id"] = json!(event_session);
            event["run_id"] = json!(event_run);
            sink(event);
        };
        let (skill_guidance, loaded_skills) =
            lock(&run.skills)?.guidance(&run.pinned_skills, &run.prompt)?;
        if !loaded_skills.is_empty() {
            let names = loaded_skills
                .iter()
                .filter_map(|record| record["name"].as_str())
                .collect::<Vec<_>>()
                .join(", ");
            let activity = json!({"event":"skills_loaded","type":"skills_loaded","category":"Skills","message":"Required Skills loaded for this turn","detail":names,"meta":serde_json::to_string(&loaded_skills)?,"records":loaded_skills,"status":"completed"});
            emit(json!({"type":"ui.event","event":activity}));
            run.activities.push(activity);
        }
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
        if !run.no_index
            && let Some(engine) = run.context.as_ref()
        {
            lock(&self.kernel)?.ensure_monitor_at(
                &run.context_key,
                &run.execution_root,
                engine.clone(),
                &run.monitor_configuration,
                &self.context_cancel,
                sink.clone(),
            )?;
        }
        let system = format!(
            "You are Reverie, an assistant working in {}. Execute workspace tools in {}. Use the supplied workspace tools. Respect configured permissions, preserve files and report actual results. Ask a concise question with up to three options and a custom answer when required information is missing.\n{}\n{}\nWorkspace evidence:{}",
            run.root.display(),
            run.execution_root.display(),
            run.rules,
            skill_guidance,
            context
        );
        run.messages
            .insert(0, json!({"role":"system","content":system}));
        let mut pending = VecDeque::new();
        let outcome = async {
        'iterations: for iteration in 0..64 {
            if control.cancel.is_cancelled() {
                return Err("Run cancelled.".into());
            }
            if run.config["mode"] == "writer" {
                let selected = lock(&run.writer_project)?.clone();
                let (style, snapshot) = modes::writer_style(
                    &run.app,
                    &run.execution_root,
                    &run.config,
                    selected.as_ref(),
                )?;
                *lock(&run.wstyle_snapshot)? = snapshot;
                run.messages[0]["content"] = json!(format!("{system}\n{style}"));
            }
            if !pending.is_empty() {
                let must_wait = iteration == 63 || crate::compaction::needs_compression(
                    crate::compaction::count_messages(&run.messages).tokens, context::capacity(&run.config));
                self.advance_approvals(run, control, &mut pending, must_wait, &emit).await?;
            }
            self.adjust_run_context(run, control, sink).await?;
            let mut catalog = tool_catalog_for(run.config["mode"].as_str().unwrap_or("reverie"));
            if run.config["mode"] != "writer" && (self.browser_component.is_some() || self.browsers.available()?) {
                catalog.push(browser::definition());
            }
            let auth = self
                .mcp_authorization(&run.mcp_servers, &control.cancel)
                .await?;
            self.mcp
                .retain_configurations(&run.execution_root, &run.mcp_servers)?;
            let snapshot = Arc::new(
                self.mcp
                    .discover(
                        &auth.servers,
                        &run.execution_root,
                        &auth.headers,
                        Self::mcp_notify(&run.root, sink.clone()),
                        &control.cancel,
                    )
                    .await?,
            );
            catalog.extend(
                snapshot
                    .tools
                    .iter()
                    .filter(|tool| {
                        run.config["mode"] != "writer"
                            || tool.metadata["annotations"]["readOnlyHint"] == true
                    })
                    .map(|tool| tool.definition.clone()),
            );
            if (iteration == 0 && (!snapshot.servers.is_empty() || !run.mcp_diagnostics.is_empty()))
                || !auth.diagnostics.is_empty()
            {
                emit(
                    json!({"type":"mcp.status","servers":snapshot.servers,"diagnostics":run.mcp_diagnostics,"authorization_diagnostics":auth.diagnostics}),
                );
            }
            *lock(&run.mcp)? = Some(snapshot);
            let awaiting = !pending.is_empty();
            let model_event = |event: Value| {
                if !awaiting || !matches!(event["type"].as_str(), Some("assistant.delta" | "reasoning.delta")) { emit(event); }
            };
            let turn = if awaiting {
                let (model, config, messages)=(run.model.clone(),run.config.clone(),run.messages.clone());
                let request=client.chat(&model,&config,&messages,&catalog,&control.cancel,&model_event);
                tokio::pin!(request);
                loop {tokio::select! {biased;
                    _=control.approval_ready.notified(), if !pending.is_empty()=> {
                        let before=pending.len();
                        self.advance_approvals(run,control,&mut pending,false,&emit).await?;
                        if before != pending.len() { continue 'iterations; }
                    },
                    response=&mut request=>break response,
                }}
            } else { client
                .chat(
                    &run.model,
                    &run.config,
                    &run.messages,
                    &catalog,
                    &control.cancel,
                    &model_event,
                )
                .await };
            if let Some(error) = lock(&stream_error)?.take() {
                return Err(format!("Could not preserve streamed output: {error}").into());
            }
            let turn = turn?;
            if control.cancel.is_cancelled() {
                return Err("Run cancelled.".into());
            }
            if awaiting && turn.tool_calls.is_empty() {
                // The model has finished its independent work. Collect the actual tool
                // results before asking for its final answer.
                self.advance_approvals(run, control, &mut pending, true, &emit).await?;
                continue;
            }
            let mut ids=std::collections::HashSet::new();
            if turn.tool_calls.values().any(|c|c.id.is_empty() || !ids.insert(&c.id)) {
                return Err("The model returned missing or duplicate tool call IDs.".into());
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
            let review = self
                .review_tools(run, control, &turn.tool_calls, &client)
                .await?;
            if let Some(outcome) = review.as_ref() {
                let activity = json!({"event":"permission_review","type":"permission_review","review":outcome});
                emit(json!({"type":"ui.event","event":activity}));
                run.activities.push(activity);
            }
            for (index, call) in turn.tool_calls {
                let ready = if call.name == "userInput" && !pending.is_empty() {
                    self.advance_approvals(run,control,&mut pending,true,&emit).await
                } else { Ok(()) };
                let event_id = format!("{}:tool:{iteration}:{index}", run.id);
                let result = match ready.and_then(|()| serde_json::from_str::<Value>(&call.arguments).map_err(|_|"Tool arguments must be valid JSON.".into())) {
                    Ok(args) => {
                        emit(json!({"type":"ui.event","event":{"event":"tool_start","type":"tool_start","tool_name":call.name,"tool_call_id":call.id,"arguments":args}}));
                        self.start_tool(run,control,&call,&args,review.as_ref(),&mut pending,&emit).await
                    }
                    Err(error) => Err(error),
                };
                let mut result=result;
                if let Ok(provisional)=&mut result && provisional.status=="pending_approval" {
                    provisional.data["approval_event"]=json!(event_id);
                }
                let (tool, activity) = Self::tool_message(run, control, &call, result)?;
                if let Some(last) = pending.back_mut().filter(|p| p.event_id.is_empty()) {
                    last.event_id = event_id.clone();
                    last.message = tool.clone();
                }
                lock(&run.store)?.append(
                    &run.session,
                    &event_id,
                    std::slice::from_ref(&tool),
                )?;
                run.messages.push(tool);
                run.tool_activity(activity,&emit);
            }
        }
        Err("Run reached the supported tool-iteration limit without a final response.".into())
        }.await;
        if outcome.is_err() {
            for waiting in pending {
                lock(&control.approvals)?.remove(&waiting.approval_id());
                if !waiting.message.is_null() {
                    let result = ToolResult::not_started(
                        "Run ended before the pending approval could be executed.",
                    );
                    let (message, activity) =
                        Self::tool_message(run, control, waiting.call(), Ok(result))?;
                    lock(&run.store)?.resolve_pending_tool(
                        &run.session,
                        &waiting.event_id,
                        &waiting.message,
                        &message,
                    )?;
                    run.tool_activity(activity, &emit);
                }
            }
        }
        outcome
    }

    async fn tool(
        &self,
        run: &Run,
        control: &RunControl,
        call: &ToolCall,
        args: &Value,
        emit: &impl Fn(Value),
    ) -> Result<ToolResult> {
        if control.cancel.is_cancelled() {
            return Err("Run cancelled before tool execution.".into());
        }
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
        if call.name == "browser" {
            return self.browser_tool(run, control, args).await;
        }
        let mcp_snapshot = { lock(&run.mcp)?.clone() };
        let mcp_tool = mcp_snapshot
            .as_ref()
            .and_then(|snapshot| snapshot.prepare_tool(&call.name).ok());
        let mcp_read = matches!(
            call.name.as_str(),
            "mcp-catalog" | "mcp-resources-read" | "mcp-prompts-get"
        );
        let mode_tool = modes::is_read_only(&call.name, args);
        let mode_name = run.config["mode"].as_str().unwrap_or("reverie");
        if control.cancel.is_cancelled() {
            return Err("Run cancelled before tool execution.".into());
        }
        if let Some(lease) = mcp_tool {
            let headers = self
                .connector_manager()?
                .headers(lease.configuration(), &control.cancel)
                .await?;
            return Ok(lease
                .call_approved(args.clone(), &headers, &control.cancel)
                .await);
        }
        if mcp_read {
            let snapshot = mcp_snapshot.ok_or("MCP discovery is not available in this task.")?;
            if call.name == "mcp-catalog" {
                let result = catalog::mcp_catalog(&snapshot, args)?;
                return Ok(ToolResult::ok(
                    serde_json::to_string_pretty(&result)?,
                    result,
                ));
            }
            let server = args["server_id"]
                .as_str()
                .ok_or("MCP server_id is required.")?;
            let target = if call.name == "mcp-resources-read" {
                args["uri"]
                    .as_str()
                    .ok_or("MCP resource URI is required.")?
            } else {
                args["name"]
                    .as_str()
                    .ok_or("MCP prompt name is required.")?
            };
            let prompt_arguments = if call.name == "mcp-prompts-get" {
                match args.get("arguments") {
                    None | Some(Value::Null) => json!({}),
                    Some(value) if value.is_object() => value.clone(),
                    _ => return Err("MCP prompt arguments must be an object.".into()),
                }
            } else {
                json!({})
            };
            let configuration = snapshot
                .server_configuration(server)
                .ok_or("MCP server was not discovered for this task.")?;
            let headers = self
                .connector_manager()?
                .headers(configuration, &control.cancel)
                .await?;
            let result = if call.name == "mcp-resources-read" {
                snapshot
                    .read_resource(server, target, &headers, &control.cancel)
                    .await
            } else {
                snapshot
                    .get_prompt(server, target, prompt_arguments, &headers, &control.cancel)
                    .await
            };
            return match result {
                Ok(value) => Ok(ToolResult::ok(serde_json::to_string_pretty(&value)?, value)),
                Err(error) => match error.downcast::<crate::mcp::Failure>() {
                    Ok(failure) => {
                        let mut result = ToolResult::fail(failure.message.clone());
                        result.data =
                            json!({"server_id":server,"delivery":failure.delivery.name()});
                        Ok(result)
                    }
                    Err(error) => Err(error),
                },
            };
        }
        if mode_tool.is_some() {
            let name = call.name.clone();
            let arguments = args.clone();
            let root = run.execution_root.clone();
            let cancel = control.cancel.clone();
            let style = lock(&run.wstyle_snapshot)?.clone();
            let result = tokio::task::spawn_blocking(move || {
                if cancel.is_cancelled() {
                    return Err("Run cancelled before mode tool execution.".into());
                }
                modes::execute(&name, &arguments, &root, &style)
            })
            .await??
            .ok_or("Mode tool did not return a result.")?;
            if mode_name == "writer"
                && let Some(binding) = modes::writer_binding(&run.execution_root, &result["data"])?
            {
                let mut store = lock(&run.store)?;
                let page = store.page(&run.session, None, 1)?;
                if page.metadata.get("writer_project") != Some(&binding) {
                    store.update_metadata(
                        &run.session,
                        Map::from_iter([("writer_project".into(), binding.clone())]),
                        page.revision,
                    )?;
                }
                *lock(&run.writer_project)? = Some(binding);
            }
            return Ok(ToolResult::ok(
                result["output"].as_str().unwrap_or_default().to_owned(),
                result["data"].clone(),
            ));
        }
        if ["skill_lookup", "skill_search", "skills_help"].contains(&call.name.as_str()) {
            let request: reverie_protocol::SkillLookupRequest =
                serde_json::from_value(args.clone())?;
            if request.force_refresh == Some(true) {
                *lock(&run.skills)? = Arc::new(crate::skills::SkillCatalog::discover_with_plugins(
                    &run.execution_root,
                    &run.app,
                    run.config["mode"].as_str().unwrap_or("reverie"),
                    run.plugins.clone(),
                )?);
            }
            let catalog = lock(&run.skills)?.clone();
            let details = catalog.model_lookup(&request, &run.pinned_skills, &run.prompt)?;
            return Ok(ToolResult::ok(
                serde_json::to_string_pretty(&details)?,
                details,
            ));
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
            arguments["cwd"] = json!(run.command_cwd(args));
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
