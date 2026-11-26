use super::{
    Action, Notify, Query,
    config::ServerConfig,
    evidence::{self, Document, Position},
    protocol::{self, Connection, Delivery, FailureKind, lock},
};
use crate::Result;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex, Weak,
        atomic::{AtomicBool, AtomicU32, AtomicUsize, Ordering},
    },
};
use tokio::sync::{Mutex as AsyncMutex, Notify as Drained};
use tokio_util::sync::CancellationToken;

struct LanguageServer {
    project: PathBuf,
    config: ServerConfig,
    executable: Option<PathBuf>,
    fingerprint: String,
    generation: u64,
    notify: Mutex<Notify>,
    connection: AsyncMutex<Option<Connection>>,
    active: AtomicUsize,
    drained: Drained,
    retired: AtomicBool,
    shutdown: CancellationToken,
    state: AtomicU32,
    pid: AtomicU32,
    last_error: Mutex<Option<String>>,
}
struct QueryLease {
    server: Arc<LanguageServer>,
}
impl Drop for QueryLease {
    fn drop(&mut self) {
        if self.server.active.fetch_sub(1, Ordering::AcqRel) == 1 {
            self.server.drained.notify_waiters();
        }
    }
}

impl LanguageServer {
    fn new(
        project: &Path,
        config: ServerConfig,
        executable: Option<PathBuf>,
        generation: u64,
        notify: Notify,
    ) -> Result<Self> {
        let fingerprint = config.fingerprint()?;
        Ok(Self {
            project: project.to_owned(),
            config,
            executable,
            fingerprint,
            generation,
            notify: Mutex::new(notify),
            connection: AsyncMutex::new(None),
            active: AtomicUsize::new(0),
            drained: Drained::new(),
            retired: AtomicBool::new(false),
            shutdown: CancellationToken::new(),
            state: AtomicU32::new(0),
            pid: AtomicU32::new(0),
            last_error: Mutex::new(None),
        })
    }
    fn version(&self) -> &str {
        if self.config.source_version.is_empty() {
            &self.fingerprint
        } else {
            &self.config.source_version
        }
    }
    fn lease(self: &Arc<Self>) -> QueryLease {
        self.active.fetch_add(1, Ordering::AcqRel);
        QueryLease {
            server: self.clone(),
        }
    }
    fn public(&self) -> Value {
        let state = if !self.config.enabled {
            "disabled"
        } else if !self.config.trusted {
            "untrusted"
        } else if self.config.extension_to_language.is_empty() {
            "needs_configuration"
        } else if self.executable.is_none() {
            "missing_executable"
        } else if self.retired.load(Ordering::Acquire) {
            "retiring"
        } else {
            match self.state.load(Ordering::Acquire) {
                1 => "starting",
                2 => "ready",
                3 => "failed",
                4 => "closed",
                _ => "configured",
            }
        };
        json!({"id":self.config.id(),"name":self.config.name,"origin":self.config.origin,
            "source_version":self.version(),"configuration_sha256":self.fingerprint,"generation":self.generation,
            "project_root":self.project,"transport":"stdio","enabled":self.config.enabled,"trusted":self.config.trusted,
            "extensionToLanguage":self.config.extension_to_language,"executable":self.executable,"status":state,
            "pid":match self.pid.load(Ordering::Acquire) {0=>None,pid=>Some(pid)},"position_encoding":"utf-16",
            "error":self.last_error.lock().ok().and_then(|value|value.clone())})
    }
    fn callback(self: &Arc<Self>) -> Notify {
        let weak = Arc::downgrade(self);
        Arc::new(move |mut event| {
            if let Some(server) = weak.upgrade() {
                if event["type"] == "lsp.disconnected" {
                    server.state.store(3, Ordering::Release);
                    server.pid.store(0, Ordering::Release);
                }
                event["source_version"] = json!(server.version());
                event["generation"] = json!(server.generation);
                let notify = server.notify.lock().ok().map(|notify| notify.clone());
                if let Some(notify) = notify {
                    notify(event);
                }
            }
        })
    }
    async fn invoke(self: &Arc<Self>, query: Query, cancel: CancellationToken) -> Result<Value> {
        let mut slot = tokio::select! {
            biased;
            _ = cancel.cancelled() => return Err(protocol::failed(FailureKind::Cancelled,Delivery::NotStarted,"Language-service query was cancelled before execution.")),
            _ = self.shutdown.cancelled() => return Err(protocol::failed(FailureKind::Unavailable,Delivery::NotStarted,"Language service has been closed.")),
            slot = self.connection.lock() => slot,
        };
        if slot
            .as_ref()
            .is_some_and(|connection| !connection.shared.alive.load(Ordering::Acquire))
        {
            if let Some(mut connection) = slot.take() {
                connection
                    .close(self.config.shutdown_timeout_ms, &self.config)
                    .await;
            }
            self.state.store(3, Ordering::Release);
            self.pid.store(0, Ordering::Release);
            return Err(protocol::failed(
                FailureKind::Unavailable,
                Delivery::NotStarted,
                "Language server disconnected; refresh the language service before retrying.",
            ));
        }
        if slot.is_none() {
            if self.state.load(Ordering::Acquire) == 3 {
                return Err(protocol::failed(
                    FailureKind::Unavailable,
                    Delivery::NotStarted,
                    "Refresh the failed language service before another startup attempt.",
                ));
            }
            let executable = self.executable.as_ref().ok_or_else(|| {
                protocol::failed(
                    FailureKind::Unavailable,
                    Delivery::NotStarted,
                    "Language-server executable was not found.",
                )
            })?;
            self.state.store(1, Ordering::Release);
            let starting = Connection::start(
                &self.config,
                executable,
                &self.project,
                self.callback(),
                &cancel,
            );
            let started = tokio::select! {
                biased;
                _ = self.shutdown.cancelled() => Err(protocol::failed(FailureKind::Cancelled,Delivery::Unknown,"Language-server startup was stopped.")),
                result = starting => result,
            };
            match started {
                Ok(connection) => {
                    self.pid
                        .store(connection.pid().unwrap_or(0), Ordering::Release);
                    *slot = Some(connection);
                    self.state.store(2, Ordering::Release);
                    *lock(&self.last_error)? = None;
                }
                Err(error) => {
                    self.state.store(3, Ordering::Release);
                    *lock(&self.last_error)? = Some(self.config.redacted(&error.to_string()));
                    return Err(error);
                }
            }
        }
        let connection = slot.as_mut().unwrap();
        let query_future = self.perform(connection, &query, &cancel);
        let result = tokio::select! {
            biased;
            _ = self.shutdown.cancelled() => Err(protocol::failed(FailureKind::Cancelled,Delivery::Unknown,"Language-service query was stopped during shutdown.")),
            result = query_future => result,
        };
        if let Err(error) = &result {
            *lock(&self.last_error)? = Some(self.config.redacted(&error.to_string()));
            if !connection.shared.alive.load(Ordering::Acquire) || self.shutdown.is_cancelled() {
                if let Some(mut connection) = slot.take() {
                    connection
                        .close(self.config.shutdown_timeout_ms, &self.config)
                        .await;
                }
                self.state.store(3, Ordering::Release);
                self.pid.store(0, Ordering::Release);
            }
        }
        result
    }
    async fn perform(
        &self,
        connection: &mut Connection,
        query: &Query,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        let document = if query.action == Action::WorkspaceSymbols {
            None
        } else {
            let path = evidence::checked_path(&self.project, &query.query, true)?;
            let language = self.config.language(&path).ok_or_else(|| {
                protocol::failed(
                    FailureKind::Unavailable,
                    Delivery::NotStarted,
                    "No configured language mapping applies to this file.",
                )
            })?;
            Some(
                connection
                    .ensure_document(&self.project, &query.query, language)
                    .await?,
            )
        };
        let mut diagnostic_status = Value::Null;
        let (mut items, dropped) = match query.action {
            Action::WorkspaceSymbols => {
                if !connection.supports("workspaceSymbolProvider") {
                    return Err(protocol::failed(
                        FailureKind::Unavailable,
                        Delivery::NotStarted,
                        "Language server does not advertise workspace symbols.",
                    ));
                }
                let raw = connection
                    .request(
                        "workspace/symbol",
                        json!({"query":query.query}),
                        self.config.request_timeout_ms,
                        &self.config,
                        cancel,
                    )
                    .await?;
                evidence::symbols(&self.project, &self.config, &raw, None, query.limit)
            }
            Action::DocumentSymbols => {
                if !connection.supports("documentSymbolProvider") {
                    return Err(protocol::failed(
                        FailureKind::Unavailable,
                        Delivery::NotStarted,
                        "Language server does not advertise document symbols.",
                    ));
                }
                let document = document.as_ref().unwrap();
                let raw = connection
                    .request(
                        "textDocument/documentSymbol",
                        json!({"textDocument":{"uri":document.uri}}),
                        self.config.request_timeout_ms,
                        &self.config,
                        cancel,
                    )
                    .await?;
                evidence::symbols(
                    &self.project,
                    &self.config,
                    &raw,
                    Some(document),
                    query.limit,
                )
            }
            Action::Definitions => {
                if !connection.supports("definitionProvider") {
                    return Err(protocol::failed(
                        FailureKind::Unavailable,
                        Delivery::NotStarted,
                        "Language server does not advertise definitions.",
                    ));
                }
                let document = document.as_ref().unwrap();
                Position {
                    line: query.line,
                    character: query.character,
                }
                .utf8_offset(&document.text)?;
                let raw = connection.request("textDocument/definition",json!({"textDocument":{"uri":document.uri},"position":{"line":query.line,"character":query.character}}),self.config.request_timeout_ms,&self.config,cancel).await?;
                evidence::definitions(&self.project, &self.config, &raw, query.limit)
            }
            Action::Diagnostics => {
                let document = document.as_ref().unwrap();
                let batch = connection.diagnostic_batch(document, cancel).await?;
                diagnostic_status = match batch.as_ref() {
                    Some(batch) => {
                        json!({"received":true,"version":batch.version,"version_verified":batch.verified,
                        "version_status":if batch.verified{"matched"}else{"unverified"},"content_sha256":batch.sha256,
                        "discarded_version_mismatch":connection.shared.discarded_diagnostics.load(Ordering::Relaxed)})
                    }
                    None => {
                        json!({"received":false,"version_verified":false,"version_status":"not_received", "wait_ms":1500})
                    }
                };
                let items = batch
                    .map(|batch| {
                        let mut items = batch.items;
                        for item in &mut items {
                            item["diagnostic_version"] = json!(batch.version);
                            item["version_verified"] = json!(batch.verified);
                        }
                        items
                    })
                    .unwrap_or_default();
                (items.into_iter().take(query.limit).collect(), 0)
            }
            Action::Status => unreachable!("Status is handled without starting a server."),
        };
        let stale = document.as_ref().is_some_and(|document| {
            Document::read(&self.project, &query.query)
                .map_or(true, |current| current.sha256 != document.sha256)
        });
        let stale_count = if stale {
            let count = items.len();
            items.clear();
            count
        } else {
            0
        };
        for item in &mut items {
            item["source"] = json!("lsp");
            item["source_version"] = json!(self.version());
            item["configuration_sha256"] = json!(self.fingerprint);
            item["generation"] = json!(self.generation);
            item["project_root"] = json!(self.project);
        }
        Ok(
            json!({"source":"lsp","action":query.action,"server_id":self.config.id(),"project_root":self.project,
            "source_version":self.version(),"configuration_sha256":self.fingerprint,"generation":self.generation,
            "position_encoding":"utf-16","items":items,"count":items.len(),"dropped_invalid_or_outside_project":dropped,
            "document":document.as_ref().map(Document::public),"diagnostics":diagnostic_status,"stale":stale,"discarded_stale_items":stale_count,
            "evidence_kind":"language_server_signal","static_index_updated":false}),
        )
    }
    async fn close(&self) {
        self.shutdown.cancel();
        let mut slot = self.connection.lock().await;
        if let Some(mut connection) = slot.take() {
            connection
                .close(self.config.shutdown_timeout_ms, &self.config)
                .await;
        }
        self.state.store(4, Ordering::Release);
        self.pid.store(0, Ordering::Release);
    }
    async fn retire(&self) {
        self.retired.store(true, Ordering::Release);
        loop {
            let drained = self.drained.notified();
            if self.active.load(Ordering::Acquire) == 0 {
                break;
            }
            drained.await;
        }
        self.close().await;
    }
}

struct Project {
    generation: u64,
    servers: Vec<Arc<LanguageServer>>,
}
#[derive(Default)]
pub struct LspRuntime {
    projects: Mutex<BTreeMap<PathBuf, Project>>,
    retired: Mutex<Vec<Weak<LanguageServer>>>,
    closed: AtomicBool,
}
impl LspRuntime {
    pub fn new() -> Self {
        Self::default()
    }
    fn retire(&self, server: Arc<LanguageServer>) -> Result<()> {
        server.retired.store(true, Ordering::Release);
        let mut retired = lock(&self.retired)?;
        retired.retain(|server| server.strong_count() > 0);
        retired.push(Arc::downgrade(&server));
        tokio::spawn(async move {
            server.retire().await;
        });
        Ok(())
    }
    /// Configuration order is priority. This does not start or approve an executable.
    pub async fn configure(
        &self,
        project: &Path,
        configurations: Vec<ServerConfig>,
        notify: Notify,
    ) -> Result<Value> {
        if self.closed.load(Ordering::Acquire) {
            return Err("Language-service runtime is closed.".into());
        }
        let project = crate::config::canonical_project(project)?;
        let mut seen = BTreeMap::new();
        let mut prepared = Vec::new();
        for config in configurations {
            let fingerprint = config.fingerprint()?;
            if let Some(existing) = seen.insert(config.id(), fingerprint.clone()) {
                if existing != fingerprint {
                    return Err("Conflicting versions of the same language-server identity.".into());
                }
                continue;
            }
            let executable = config.executable(&project)?.map(evidence::normalized);
            prepared.push((config, fingerprint, executable));
        }
        let retired = {
            let mut projects = lock(&self.projects)?;
            if self.closed.load(Ordering::Acquire) {
                return Err("Language-service runtime is closed.".into());
            }
            let previous = projects.remove(&project);
            let unchanged = previous.as_ref().is_some_and(|previous| {
                previous.servers.len() == prepared.len()
                    && previous.servers.iter().zip(&prepared).all(
                        |(server, (_, hash, executable))| {
                            server.fingerprint == *hash && server.executable == *executable
                        },
                    )
            });
            let generation = previous
                .as_ref()
                .map_or(1, |previous| previous.generation + u64::from(!unchanged));
            let mut remaining: BTreeMap<_, _> = previous
                .into_iter()
                .flat_map(|previous| previous.servers)
                .map(|server| (server.config.id(), server))
                .collect();
            let mut servers = Vec::new();
            for (config, fingerprint, executable) in prepared {
                if let Some(server) = remaining.get(&config.id())
                    && server.fingerprint == fingerprint
                    && server.executable == executable
                {
                    let server = remaining.remove(&config.id()).unwrap();
                    *lock(&server.notify)? = notify.clone();
                    servers.push(server);
                } else {
                    servers.push(Arc::new(LanguageServer::new(
                        &project,
                        config,
                        executable,
                        generation,
                        notify.clone(),
                    )?));
                }
            }
            projects.insert(
                project.clone(),
                Project {
                    generation,
                    servers,
                },
            );
            remaining.into_values().collect::<Vec<_>>()
        };
        for server in retired {
            self.retire(server)?;
        }
        self.status(&project)
    }
    pub fn status(&self, project: &Path) -> Result<Value> {
        let project = crate::config::canonical_project(project)?;
        let projects = lock(&self.projects)?;
        let state = projects.get(&project);
        let servers: Vec<_> = state
            .into_iter()
            .flat_map(|state| state.servers.iter())
            .map(|server| server.public())
            .collect();
        let available = servers.iter().any(|server| {
            matches!(
                server["status"].as_str(),
                Some("configured" | "starting" | "ready")
            )
        });
        Ok(
            json!({"source":"lsp","project_root":project,"generation":state.map_or(0,|state|state.generation),"available":available,
            "servers":servers,"position_encoding":"utf-16","closed":self.closed.load(Ordering::Acquire)}),
        )
    }
    pub async fn query(
        &self,
        project: &Path,
        query: Query,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        if query.action == Action::Status {
            return self.status(project);
        }
        if cancel.is_cancelled() {
            return Err(protocol::failed(
                FailureKind::Cancelled,
                Delivery::NotStarted,
                "Language-service query was cancelled before execution.",
            ));
        }
        if query.limit == 0 || query.limit > 200 || query.query.len() > 64 * 1024 {
            return Err(protocol::failed(
                FailureKind::Invalid,
                Delivery::NotStarted,
                "Language-service query requires a limit of 1..200 and at most 64 KiB of query text.",
            ));
        }
        if self.closed.load(Ordering::Acquire) {
            return Err(protocol::failed(
                FailureKind::Unavailable,
                Delivery::NotStarted,
                "Language-service runtime is closed.",
            ));
        }
        let project = crate::config::canonical_project(project)?;
        let path = if query.action == Action::WorkspaceSymbols {
            None
        } else {
            let path = evidence::checked_path(&project, &query.query, true)?;
            if query.action == Action::Definitions {
                Position {
                    line: query.line,
                    character: query.character,
                }
                .utf8_offset(&Document::read(&project, &query.query)?.text)?;
            }
            Some(path)
        };
        let (generation, leases) = {
            let projects = lock(&self.projects)?;
            let state = projects.get(&project).ok_or_else(|| {
                protocol::failed(
                    FailureKind::Unavailable,
                    Delivery::NotStarted,
                    "Language services have not been configured for this project.",
                )
            })?;
            let mut leases = Vec::new();
            for server in &state.servers {
                if query
                    .server_id
                    .as_ref()
                    .is_some_and(|id| *id != server.config.id())
                {
                    continue;
                }
                if !server.config.enabled
                    || !server.config.trusted
                    || server.config.extension_to_language.is_empty()
                    || server.executable.is_none()
                {
                    continue;
                }
                if path
                    .as_ref()
                    .is_some_and(|path| server.config.language(path).is_none())
                {
                    continue;
                }
                leases.push(server.lease());
                if path.is_some() {
                    break;
                }
            }
            (state.generation, leases)
        };
        if leases.is_empty() {
            return Err(protocol::failed(
                FailureKind::Unavailable,
                Delivery::NotStarted,
                "No enabled, trusted, configured language server applies to this query.",
            ));
        }
        if path.is_some() {
            let lease = leases.into_iter().next().unwrap();
            return lease.server.invoke(query, cancel.clone()).await;
        }
        let mut tasks = tokio::task::JoinSet::new();
        let mut waiting = leases.into_iter().enumerate();
        for _ in 0..4 {
            if let Some((index, lease)) = waiting.next() {
                let query = query.clone();
                let cancel = cancel.clone();
                tasks.spawn(async move {
                    (
                        index,
                        lease.server.config.id(),
                        lease.server.invoke(query, cancel).await,
                    )
                });
            }
        }
        let mut results = BTreeMap::new();
        while let Some(completed) = tasks.join_next().await {
            let (index, id, result) =
                completed.map_err(|_| "Language-service query task ended unexpectedly.")?;
            results.insert(index, (id, result));
            if let Some((index, lease)) = waiting.next() {
                let query = query.clone();
                let cancel = cancel.clone();
                tasks.spawn(async move {
                    (
                        index,
                        lease.server.config.id(),
                        lease.server.invoke(query, cancel).await,
                    )
                });
            }
        }
        if cancel.is_cancelled() {
            let delivery = if results.values().any(|(_, result)| {
                result
                    .as_ref()
                    .err()
                    .and_then(|error| error.downcast_ref::<super::Failure>())
                    .is_some_and(|error| error.delivery == Delivery::Unknown)
            }) {
                Delivery::Unknown
            } else {
                Delivery::NotStarted
            };
            return Err(protocol::failed(
                FailureKind::Cancelled,
                delivery,
                "Language-service workspace query was cancelled; pending requests are not replayed.",
            ));
        }
        let mut items = Vec::new();
        let mut errors = Vec::new();
        let mut servers = Vec::new();
        let mut seen = BTreeSet::new();
        for (_, (id, result)) in results {
            match result {
                Ok(result) => {
                    servers.push(json!({"id":id,"source_version":result["source_version"],"configuration_sha256":result["configuration_sha256"],"count":result["count"],"dropped":result["dropped_invalid_or_outside_project"]}));
                    for item in result["items"].as_array().into_iter().flatten() {
                        let identity =
                            json!({"name":item["name"],"uri":item["uri"],"range":item["range"]})
                                .to_string();
                        if seen.insert(identity) && items.len() < query.limit {
                            items.push(item.clone());
                        }
                    }
                }
                Err(error) => {
                    let delivery = error
                        .downcast_ref::<super::Failure>()
                        .map(|error| error.delivery.name())
                        .unwrap_or("not_started");
                    errors.push(
                        json!({"server_id":id,"message":error.to_string(),"delivery":delivery}),
                    );
                }
            }
        }
        Ok(
            json!({"source":"lsp","action":query.action,"project_root":project,"generation":generation,
            "position_encoding":"utf-16","items":items,"count":items.len(),"servers":servers,"errors":errors,
            "complete":errors.is_empty(),"evidence_kind":"language_server_signal","static_index_updated":false}),
        )
    }
    pub async fn close_document(&self, project: &Path, path: &str) -> Result<()> {
        let project = crate::config::canonical_project(project)?;
        let uri = evidence::file_uri(&evidence::checked_path(&project, path, false)?)?;
        let servers = {
            lock(&self.projects)?
                .get(&project)
                .map(|project| project.servers.clone())
                .unwrap_or_default()
        };
        for server in servers {
            let mut slot = server.connection.lock().await;
            if let Some(connection) = slot.as_mut() {
                connection.close_document(&uri).await?;
            }
        }
        Ok(())
    }
    pub async fn invalidate(&self, project: &Path, server_id: Option<&str>) -> Result<()> {
        let project = crate::config::canonical_project(project)?;
        let retired = {
            let mut projects = lock(&self.projects)?;
            let Some(state) = projects.get_mut(&project) else {
                return Ok(());
            };
            state.generation += 1;
            let mut retired = Vec::new();
            for server in &mut state.servers {
                if server_id.is_none_or(|id| server.config.id() == id) {
                    let replacement = Arc::new(LanguageServer::new(
                        &project,
                        server.config.clone(),
                        server
                            .config
                            .executable(&project)?
                            .map(evidence::normalized),
                        state.generation,
                        lock(&server.notify)?.clone(),
                    )?);
                    retired.push(std::mem::replace(server, replacement));
                }
            }
            retired
        };
        for server in retired {
            self.retire(server)?;
        }
        Ok(())
    }
    pub async fn close_project(&self, project: &Path) -> Result<()> {
        let project = crate::config::canonical_project(project)?;
        let mut servers = lock(&self.projects)?
            .remove(&project)
            .map(|project| project.servers)
            .unwrap_or_default();
        lock(&self.retired)?.retain(|weak| {
            if let Some(server) = weak.upgrade() {
                if server.project == project {
                    servers.push(server);
                    return false;
                }
                return true;
            }
            false
        });
        for server in &servers {
            server.shutdown.cancel();
        }
        for server in servers {
            server.close().await;
        }
        Ok(())
    }
    pub async fn close(&self) {
        self.closed.store(true, Ordering::Release);
        let mut servers = self
            .projects
            .lock()
            .ok()
            .map(|mut projects| {
                std::mem::take(&mut *projects)
                    .into_values()
                    .flat_map(|project| project.servers)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        if let Ok(mut retired) = self.retired.lock() {
            servers.extend(retired.drain(..).filter_map(|server| server.upgrade()));
        }
        for server in &servers {
            server.shutdown.cancel();
        }
        for server in servers {
            server.close().await;
        }
    }
}
