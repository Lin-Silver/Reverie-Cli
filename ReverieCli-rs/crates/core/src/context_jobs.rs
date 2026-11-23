use crate::{
    Result,
    host::{EventSink, KernelHost},
    semantic_resources::{ModelVersion, SemanticResources},
};
use reverie_context::{ContextEngine, Evidence, inference::Device};
use reverie_protocol::Reply;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicUsize, Ordering},
    },
};
use tokio_util::sync::CancellationToken;

pub(crate) struct ContextControl {
    pub cancel: CancellationToken,
    action: String,
    root: PathBuf,
    phase: Mutex<String>,
    completed: AtomicUsize,
    total: AtomicUsize,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ContextPayload {
    project_root: Option<String>,
    operation_id: Option<String>,
    expected_revision: Option<u64>,
    directory: Option<String>,
    manifest_sha256: Option<String>,
    device: Option<Device>,
    threads: Option<usize>,
    confirmed: Option<bool>,
    force: Option<bool>,
    query: Option<String>,
    strategy: Option<String>,
    limit: Option<usize>,
    estimated_tokens: Option<usize>,
}
pub struct PendingContextJob {
    id: String,
    control: Arc<ContextControl>,
    payload: ContextPayload,
    engine: Option<Arc<Mutex<ContextEngine>>>,
    version: Option<Arc<ModelVersion>>,
    semantic_error: Option<String>,
    resources: Arc<SemanticResources>,
    expected: u64,
    workspace: Value,
    monitor_key: PathBuf,
    monitor_configuration: PathBuf,
}
fn lock<T>(mutex: &Mutex<T>) -> Result<std::sync::MutexGuard<'_, T>> {
    mutex
        .lock()
        .map_err(|_| "Context operation state lock was poisoned.".into())
}

pub fn retrieve(
    engine: &ContextEngine,
    version: Option<&ModelVersion>,
    query: &str,
    limit: usize,
    budget: usize,
    strategy: &str,
    cancelled: &impl Fn() -> bool,
) -> Result<(Vec<Evidence>, Value)> {
    if !["auto", "basic", "hybrid"].contains(&strategy) {
        return Err("Context strategy must be auto, basic or hybrid.".into());
    }
    if cancelled() {
        return Err("Context retrieval cancelled.".into());
    }
    if strategy != "basic" {
        let attempt = (|| -> Result<Option<Vec<Evidence>>> {
            let Some(version) = version else {
                return Ok(None);
            };
            if engine
                .semantic_status_for(&version.selection.manifest_sha256)?
                .is_none()
            {
                return Ok(None);
            }
            let models = version.models(cancelled)?;
            Ok(Some(
                engine.query_hybrid(&models, query, limit, budget, cancelled)?,
            ))
        })();
        match attempt {
            Ok(Some(hits))=>return Ok((hits,json!({"strategy":"hybrid","manifest_sha256":version.map(|version|&version.selection.manifest_sha256),"rerank_candidates":limit.clamp(1,200).max(16)}))),
            Err(error) if strategy=="hybrid"||cancelled()=>return Err(error),
            Ok(None) if strategy=="hybrid"=>return Err("Install local semantic resources and build their semantic index before requesting hybrid retrieval.".into()),
            Err(error)=>return Ok((engine.query(query,limit,budget)?,json!({"strategy":"basic","semantic_unavailable":error.to_string()}))),
            Ok(None)=>{},
        }
    }
    Ok((
        engine.query(query, limit, budget)?,
        json!({"strategy":"basic","semantic_unavailable":if strategy=="basic"{"disabled_for_query"}else{"resource_or_index_missing"}}),
    ))
}

impl KernelHost {
    pub fn is_context_action(action: &str) -> bool {
        [
            "indexWorkspace",
            "queryContext",
            "indexSemanticWorkspace",
            "installSemanticResources",
            "selectSemanticResources",
            "rollbackSemanticResources",
            "disableSemanticResources",
            "removeSemanticResources",
            "warmSemanticResources",
            "unloadSemanticModels",
        ]
        .contains(&action)
    }
    pub fn begin_context_job(&self, action: &str, payload: &Value) -> Result<PendingContextJob> {
        if !Self::is_context_action(action) {
            return Err("Unsupported background Context Engine action.".into());
        }
        let payload: ContextPayload = serde_json::from_value(payload.clone())?;
        if action == "removeSemanticResources" && payload.confirmed != Some(true) {
            return Err(
                "Explicit confirmation is required to remove managed semantic resources.".into(),
            );
        }
        let mut kernel = lock(&self.kernel)?;
        if let Some(root) = payload.project_root.as_deref() {
            kernel.configure_project(root)?;
        }
        let root = kernel.project_root.clone();
        let resources = kernel.semantic.clone();
        let expected = if [
            "installSemanticResources",
            "selectSemanticResources",
            "rollbackSemanticResources",
            "disableSemanticResources",
            "removeSemanticResources",
        ]
        .contains(&action)
        {
            payload
                .expected_revision
                .map(Ok)
                .unwrap_or_else(|| resources.revision())?
        } else {
            0
        };
        let engine =
            if ["indexWorkspace", "queryContext", "indexSemanticWorkspace"].contains(&action) {
                Some(kernel.shared_context()?)
            } else {
                None
            };
        let (version, semantic_error) = if [
            "queryContext",
            "indexSemanticWorkspace",
            "warmSemanticResources",
        ]
        .contains(&action)
            && !(action == "queryContext" && payload.strategy.as_deref() == Some("basic"))
        {
            match resources.capture() {
                Ok(version) => (version, None),
                Err(error)
                    if action == "queryContext"
                        && payload.strategy.as_deref() != Some("hybrid") =>
                {
                    (None, Some(error.to_string()))
                }
                Err(error) => return Err(error),
            }
        } else {
            (None, None)
        };
        if ["indexSemanticWorkspace", "warmSemanticResources"].contains(&action)
            && version.is_none()
        {
            return Err("No local semantic resource is selected.".into());
        }
        let config = kernel.effective_config(None)?;
        let workspace = kernel.workspace(&config);
        let monitor_key = kernel.project_data_dir.clone();
        let monitor_configuration = kernel.config.path.clone();
        drop(kernel);
        let id = payload
            .operation_id
            .clone()
            .unwrap_or_else(|| uuid::Uuid::new_v4().simple().to_string());
        if id.trim().is_empty() {
            return Err("Context operation identity must not be empty.".into());
        }
        let control = Arc::new(ContextControl {
            cancel: CancellationToken::new(),
            action: action.into(),
            root,
            phase: Mutex::new("queued".into()),
            completed: AtomicUsize::new(0),
            total: AtomicUsize::new(0),
        });
        let mut jobs = lock(&self.context_jobs)?;
        if jobs.contains_key(&id) {
            return Err("A Context Engine operation already uses this identity.".into());
        }
        jobs.insert(id.clone(), control.clone());
        Ok(PendingContextJob {
            id,
            control,
            payload,
            engine,
            version,
            semantic_error,
            resources,
            expected,
            workspace,
            monitor_key,
            monitor_configuration,
        })
    }
    pub async fn complete_context_job(
        &self,
        id: Value,
        job: PendingContextJob,
        sink: EventSink,
    ) -> Reply {
        let operation = job.id.clone();
        let control = job.control.clone();
        let monitor = job.engine.clone().map(|engine| {
            (
                job.monitor_key.clone(),
                control.root.clone(),
                engine,
                job.monitor_configuration.clone(),
            )
        });
        let resource_changed = [
            "installSemanticResources",
            "selectSemanticResources",
            "rollbackSemanticResources",
            "disableSemanticResources",
            "removeSemanticResources",
        ]
        .contains(&control.action.as_str());
        let job_sink = sink.clone();
        let result = tokio::task::spawn_blocking(move || job.execute(&job_sink)).await;
        if let Ok(mut jobs) = self.context_jobs.lock() {
            jobs.remove(&operation);
        }
        match result {
            Ok(Ok((kind, mut value))) => {
                if let Ok(mut kernel) = self.kernel.lock() {
                    if let Some((key, root, engine, configuration)) = monitor {
                        if let Err(error) = kernel.ensure_monitor_at(
                            &key,
                            &root,
                            engine,
                            &configuration,
                            &self.context_cancel,
                            sink,
                        ) {
                            value["watcher_error"] = json!(error.to_string());
                        }
                        if let Some(monitor) = kernel.monitors.get(&key)
                            && value.get("context_engine").is_some()
                        {
                            value["context_engine"]["watcher"] = monitor.status();
                        }
                    }
                    if resource_changed {
                        for monitor in kernel.monitors.values() {
                            monitor.wake();
                        }
                    }
                }
                value["operation_id"] = json!(operation);
                Reply::new(
                    Some(id),
                    kind,
                    value.as_object().cloned().unwrap_or_default(),
                )
            }
            Ok(Err(error)) => Reply::error(
                id,
                if control.cancel.is_cancelled() {
                    format!("Context operation cancelled: {error}")
                } else {
                    error.to_string()
                },
            ),
            Err(error) => Reply::error(id, error),
        }
    }
    pub(crate) fn semantic_inventory(&self) -> Result<(&'static str, Value)> {
        let resources = lock(&self.kernel)?.semantic.clone();
        let mut semantic = resources.inventory();
        let mut operations = lock(&self.context_jobs)?.iter().map(|(id,control)|json!({"operation_id":id,"action":control.action,"project_root":control.root,"phase":lock(&control.phase).map(|phase|phase.clone()).unwrap_or_else(|_|"error".into()),"completed":control.completed.load(Ordering::Relaxed),"total":control.total.load(Ordering::Relaxed)})).collect::<Vec<_>>();
        operations.extend(
            lock(&self.kernel)?
                .monitors
                .values()
                .filter_map(|monitor| monitor.operation())
                .map(|operation| json!(operation)),
        );
        semantic["operations"] = json!(operations);
        Ok(("context.resources", json!({"semantic":semantic})))
    }
    pub(crate) fn stop_context_job(&self, payload: &Value) -> Result<(&'static str, Value)> {
        let id = payload["operationId"]
            .as_str()
            .ok_or("Context operation identity is required.")?;
        let jobs = lock(&self.context_jobs)?;
        let Some(control) = jobs.get(id) else {
            drop(jobs);
            let kernel = lock(&self.kernel)?;
            let project = payload["projectRoot"]
                .as_str()
                .map(|root| crate::config::canonical_project(std::path::Path::new(root)))
                .transpose()?;
            let monitor = kernel.monitors.values().find(|monitor| {
                monitor.operation().is_some_and(|operation| {
                    operation.operation_id == id
                        && project
                            .as_ref()
                            .is_none_or(|root| root.to_string_lossy() == operation.project_root)
                })
            });
            if monitor.is_some_and(|monitor| monitor.cancel_operation(id)) {
                return Ok((
                    "context.control",
                    json!({"operation_id":id,"state":"stopping"}),
                ));
            }
            return Err("Context operation is no longer active.".into());
        };
        if payload["projectRoot"]
            .as_str()
            .map(|root| crate::config::canonical_project(std::path::Path::new(root)))
            .transpose()?
            .is_some_and(|root| root != control.root)
        {
            return Err("Context operation belongs to another project.".into());
        }
        control.cancel.cancel();
        Ok((
            "context.control",
            json!({"operation_id":id,"state":"stopping"}),
        ))
    }
}

impl PendingContextJob {
    pub fn operation_id(&self) -> &str {
        &self.id
    }
    fn progress(&self, sink: &EventSink, phase: &str, completed: usize, total: usize) {
        if let Ok(mut value) = self.control.phase.lock() {
            *value = phase.into();
        }
        self.control.completed.store(completed, Ordering::Relaxed);
        self.control.total.store(total, Ordering::Relaxed);
        sink(
            json!({"type":"context.progress","operation_id":self.id,"project_root":self.control.root,"action":self.control.action,"phase":phase,"completed":completed,"total":total}),
        );
    }
    fn execute(mut self, sink: &EventSink) -> Result<(&'static str, Value)> {
        let cancelled = || self.control.cancel.is_cancelled();
        if cancelled() {
            return Err("Context operation cancelled before starting.".into());
        }
        self.progress(sink, "working", 0, 0);
        let result = match self.control.action.as_str() {
            "indexWorkspace" | "indexSemanticWorkspace" => {
                let engine = self.engine.as_ref().ok_or("Missing Context Engine.")?;
                self.progress(sink, "structure", 0, 0);
                let (result, fork) = {
                    let mut engine = lock(engine)?;
                    let result = engine
                        .index_with_cancel(self.payload.force.unwrap_or(false), &cancelled)?;
                    (result, engine.fork()?)
                };
                if self.control.action == "indexSemanticWorkspace" {
                    let version = self.version.as_ref().ok_or("Missing semantic models.")?;
                    self.progress(sink, "loading", 0, 0);
                    let models = version.models(&cancelled)?;
                    let semantic = fork.index_semantic(&models, &cancelled, &|done, total| {
                        self.progress(sink, "embedding", done, total)
                    })?;
                    let mut status = fork.status()?;
                    status["semantic"] = self.resources.status();
                    (
                        "context.semantic-indexed",
                        json!({"result":semantic,"context_engine":status,"semantic":self.resources.inventory()}),
                    )
                } else {
                    self.workspace["context_engine"] = fork.status()?;
                    self.workspace["context_engine"]["semantic"] = self.resources.status();
                    self.workspace["index_ready"] =
                        self.workspace["context_engine"]["ready"].clone();
                    (
                        "workspace.indexed",
                        json!({"result":result,"workspace":self.workspace}),
                    )
                }
            }
            "queryContext" => {
                let fork = lock(self.engine.as_ref().ok_or("Missing Context Engine.")?)?.fork()?;
                let query = self
                    .payload
                    .query
                    .as_deref()
                    .ok_or("Context query is required.")?;
                let (hits, mut retrieval) = retrieve(
                    &fork,
                    self.version.as_deref(),
                    query,
                    self.payload.limit.unwrap_or(10),
                    self.payload.estimated_tokens.unwrap_or(12000),
                    self.payload.strategy.as_deref().unwrap_or("auto"),
                    &cancelled,
                )?;
                if let Some(error) = self.semantic_error.as_ref() {
                    retrieval["semantic_unavailable"] = json!(error);
                }
                let mut status = fork.status()?;
                status["semantic"] = self.resources.status();
                (
                    "context.results",
                    json!({"results":hits,"retrieval":retrieval,"context_engine":status}),
                )
            }
            action => {
                let digest = self.payload.manifest_sha256.as_deref().unwrap_or_default();
                let device = self.payload.device.unwrap_or_default();
                let threads = self.payload.threads.unwrap_or(6);
                let result = match action {
                    "installSemanticResources" => {
                        self.progress(sink, "verifying_and_loading", 0, 0);
                        self.resources.install(
                            std::path::Path::new(
                                self.payload
                                    .directory
                                    .as_deref()
                                    .ok_or("Offline bundle directory is required.")?,
                            ),
                            digest,
                            device,
                            threads,
                            self.expected,
                            &cancelled,
                        )?
                    }
                    "selectSemanticResources" => {
                        self.resources
                            .select(digest, device, threads, self.expected, &cancelled)?
                    }
                    "rollbackSemanticResources" => {
                        self.resources.rollback(self.expected, &cancelled)?
                    }
                    "disableSemanticResources" => {
                        self.resources.disable(self.expected, &cancelled)?
                    }
                    "removeSemanticResources" => {
                        self.resources.remove(digest, self.expected, &cancelled)?
                    }
                    "unloadSemanticModels" => self.resources.unload()?,
                    "warmSemanticResources" => {
                        let version = self.version.as_ref().ok_or("Missing semantic resources.")?;
                        let models = version.models(&cancelled)?;
                        json!({"health":models.probe_with_cancel(&cancelled)?,"semantic":self.resources.inventory()})
                    }
                    _ => return Err("Unsupported Context Engine operation.".into()),
                };
                ("context.resources", result)
            }
        };
        self.progress(sink, "finished", 1, 1);
        Ok(result)
    }
}
