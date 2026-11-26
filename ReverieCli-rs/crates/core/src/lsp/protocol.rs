use super::{
    Notify,
    config::ServerConfig,
    evidence::{self, Document},
};
use crate::Result;
use reverie_platform::command::ProcessTree;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    path::Path,
    process::Stdio,
    sync::{
        Arc, Mutex, MutexGuard,
        atomic::{AtomicBool, AtomicU32, Ordering},
    },
    time::Duration,
};
use tokio::{
    io::{AsyncBufRead, AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, Command},
    sync::{Mutex as AsyncMutex, Notify as Changed, oneshot},
    task::JoinHandle,
};
use tokio_util::sync::CancellationToken;

const MESSAGE_LIMIT: usize = 16 * 1024 * 1024;
const HEADER_LIMIT: usize = 8192;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Delivery {
    NotStarted,
    Completed,
    Unknown,
}
impl Delivery {
    pub fn name(self) -> &'static str {
        match self {
            Self::NotStarted => "not_started",
            Self::Completed => "completed",
            Self::Unknown => "unknown",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FailureKind {
    Invalid,
    Unavailable,
    Cancelled,
    Timeout,
    Protocol,
    Server,
}

#[derive(Debug)]
pub struct Failure {
    pub kind: FailureKind,
    pub delivery: Delivery,
    pub message: String,
}
impl std::fmt::Display for Failure {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}
impl std::error::Error for Failure {}

pub(super) fn failed(
    kind: FailureKind,
    delivery: Delivery,
    message: impl Into<String>,
) -> Box<dyn std::error::Error + Send + Sync> {
    Box::new(Failure {
        kind,
        delivery,
        message: message.into(),
    })
}

pub(super) fn lock<T>(value: &Mutex<T>) -> Result<MutexGuard<'_, T>> {
    value
        .lock()
        .map_err(|_| "Language-service state lock was poisoned.".into())
}

async fn frame_line<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    total: &mut usize,
) -> Result<Option<Vec<u8>>> {
    let mut line = Vec::new();
    loop {
        let available = reader.fill_buf().await?;
        if available.is_empty() {
            if line.is_empty() {
                return Ok(None);
            }
            return Err("Language-server header ended before CRLF.".into());
        }
        let end = available.iter().position(|byte| *byte == b'\n');
        let count = end.map_or(available.len(), |end| end + 1);
        *total += count;
        if *total > HEADER_LIMIT {
            return Err("Language-server headers exceed 8 KiB.".into());
        }
        line.extend_from_slice(&available[..count]);
        reader.consume(count);
        if end.is_some() {
            if !line.ends_with(b"\r\n") {
                return Err("Language-server headers must use CRLF.".into());
            }
            line.truncate(line.len() - 2);
            return Ok(Some(line));
        }
    }
}

pub(super) async fn read_frame<R: AsyncBufRead + Unpin>(reader: &mut R) -> Result<Option<Value>> {
    let mut total = 0;
    let mut length = None;
    loop {
        let Some(line) = frame_line(reader, &mut total).await? else {
            if total == 0 {
                return Ok(None);
            }
            return Err("Language-server stream ended during its header.".into());
        };
        if line.is_empty() {
            break;
        }
        if !line.is_ascii() {
            return Err("Language-server headers must be ASCII.".into());
        }
        let line = std::str::from_utf8(&line)?;
        let (name, value) = line
            .split_once(':')
            .ok_or("Language-server header has no separator.")?;
        if name.eq_ignore_ascii_case("content-length") {
            if length.is_some() {
                return Err("Language-server message has duplicate Content-Length.".into());
            }
            let parsed = value.trim().parse::<usize>()?;
            if parsed == 0 || parsed > MESSAGE_LIMIT {
                return Err("Language-server message length is invalid or exceeds 16 MiB.".into());
            }
            length = Some(parsed);
        } else if name.eq_ignore_ascii_case("content-type") {
            for parameter in value.split(';').skip(1) {
                if let Some((name, value)) = parameter.trim().split_once('=')
                    && name.eq_ignore_ascii_case("charset")
                    && !matches!(
                        value.trim().trim_matches('"').to_lowercase().as_str(),
                        "utf-8" | "utf8"
                    )
                {
                    return Err("Language-server content encoding must be UTF-8.".into());
                }
            }
        }
    }
    let mut bytes = vec![0; length.ok_or("Language-server message lacks Content-Length.")?];
    reader.read_exact(&mut bytes).await?;
    let message: Value = serde_json::from_slice(&bytes)?;
    if !message.is_object() || message["jsonrpc"] != "2.0" {
        return Err("Language-server content must be a JSON-RPC 2.0 object.".into());
    }
    Ok(Some(message))
}

async fn write_frame(writer: &AsyncMutex<ChildStdin>, message: &Value) -> Result<()> {
    let bytes = serde_json::to_vec(message)?;
    if bytes.len() > MESSAGE_LIMIT {
        return Err("Language-service message exceeds 16 MiB.".into());
    }
    let mut writer = writer.lock().await;
    writer
        .write_all(format!("Content-Length: {}\r\n\r\n", bytes.len()).as_bytes())
        .await?;
    writer.write_all(&bytes).await?;
    writer.flush().await?;
    Ok(())
}

#[derive(Clone)]
pub(super) struct DiagnosticBatch {
    pub items: Vec<Value>,
    pub version: Option<i32>,
    pub sha256: String,
    pub verified: bool,
}

pub(super) struct Shared {
    pending: Mutex<BTreeMap<u32, oneshot::Sender<Result<Value>>>>,
    pub documents: Mutex<BTreeMap<String, Document>>,
    pub diagnostics: Mutex<BTreeMap<String, DiagnosticBatch>>,
    pub changed: Changed,
    pub alive: AtomicBool,
    pub discarded_diagnostics: AtomicU32,
}
impl Shared {
    fn disconnect(&self) {
        self.alive.store(false, Ordering::Release);
        if let Ok(mut pending) = self.pending.lock() {
            for (_, sender) in std::mem::take(&mut *pending) {
                let _ = sender.send(Err(failed(
                    FailureKind::Protocol,
                    Delivery::Unknown,
                    "Language-server connection ended before a response.",
                )));
            }
        }
        self.changed.notify_waiters();
    }
}

fn configuration_value(settings: &Value, section: Option<&str>) -> Value {
    let Some(section) = section.filter(|section| !section.is_empty()) else {
        return settings.clone();
    };
    if let Some(value) = settings.get(section) {
        return value.clone();
    }
    let mut found = settings;
    for segment in section.split('.') {
        let Some(value) = found.get(segment) else {
            return Value::Null;
        };
        found = value;
    }
    found.clone()
}

fn server_request(project: &Path, config: &ServerConfig, message: &Value) -> Value {
    let id = &message["id"];
    let result = match message["method"].as_str().unwrap_or("") {
        "workspace/workspaceFolders" => {
            json!([{"uri":evidence::file_uri(project).ok(),"name":project.file_name().unwrap_or_default().to_string_lossy()}])
        }
        "workspace/configuration" => {
            let items = message["params"]["items"].as_array();
            if items.is_none_or(|items| items.len() > 256) {
                return json!({"jsonrpc":"2.0","id":id,"error":{"code":-32602,"message":"Configuration items must be an array of at most 256 entries."}});
            }
            json!(
                items
                    .unwrap()
                    .iter()
                    .map(|item| {
                        if let Some(uri) = item["scopeUri"].as_str()
                            && evidence::checked_path(project, uri, false).is_err()
                            && evidence::file_uri(project).as_deref().ok() != Some(uri)
                        {
                            return Value::Null;
                        }
                        configuration_value(&config.settings, item["section"].as_str())
                    })
                    .collect::<Vec<_>>()
            )
        }
        "window/workDoneProgress/create" | "window/showMessageRequest" => Value::Null,
        "workspace/applyEdit" => {
            json!({"applied":false,"failureReason":"Language services cannot approve workspace edits."})
        }
        _ => {
            return json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"This read-only language-service client does not provide that capability."}});
        }
    };
    json!({"jsonrpc":"2.0","id":id,"result":result})
}

fn server_notification(
    project: &Path,
    config: &ServerConfig,
    fingerprint: &str,
    shared: &Shared,
    notify: &Notify,
    message: &Value,
) -> Result<()> {
    match message["method"].as_str().unwrap_or("") {
        "textDocument/publishDiagnostics" => {
            let params = &message["params"];
            let Some(uri) = params["uri"].as_str() else {
                return Ok(());
            };
            let Ok(mut observed) = Document::read(project, uri) else {
                return Ok(());
            };
            let Some(items) = params["diagnostics"].as_array() else {
                return Ok(());
            };
            let version = params["version"]
                .as_i64()
                .and_then(|value| i32::try_from(value).ok());
            let current = lock(&shared.documents)?.get(&observed.uri).cloned();
            if let Some(current) = current.as_ref() {
                observed.version = current.version;
                observed.opened = current.opened;
            }
            if let Some(current) = current.as_ref().filter(|document| document.opened)
                && version.is_some_and(|version| version != current.version)
            {
                shared.discarded_diagnostics.fetch_add(1, Ordering::Relaxed);
                return Ok(());
            }
            let verified = current.as_ref().is_some_and(|current| {
                current.opened
                    && version == Some(current.version)
                    && current.sha256 == observed.sha256
            });
            let (items, dropped) = evidence::diagnostics(project, config, &observed, items, 200);
            let count = items.len();
            lock(&shared.diagnostics)?.insert(
                observed.uri.clone(),
                DiagnosticBatch {
                    items,
                    version,
                    sha256: observed.sha256.clone(),
                    verified,
                },
            );
            shared.changed.notify_waiters();
            notify(
                json!({"type":"lsp.diagnostics","source":"lsp","server_id":config.id(),
                "source_version":config.source_version,"configuration_sha256":fingerprint,"project_root":project,
                "document":observed.public(),"diagnostic_version":version,"version_verified":verified,
                "count":count,"dropped":dropped}),
            );
        }
        "$/progress" => {
            let value = &message["params"]["value"];
            if matches!(value["kind"].as_str(), Some("begin" | "report" | "end")) {
                notify(
                    json!({"type":"lsp.progress","source":"lsp","server_id":config.id(),
                    "source_version":config.source_version,"configuration_sha256":fingerprint,"project_root":project,
                    "kind":value["kind"],"title":config.redacted(value["title"].as_str().unwrap_or("")),
                    "message":config.redacted(value["message"].as_str().unwrap_or("")),
                    "percentage":value["percentage"].as_u64().filter(|value|*value<=100)}),
                );
            }
        }
        _ => {}
    }
    Ok(())
}

enum Phase {
    Pending,
    Writing,
    Sent,
    Finished,
}
struct PendingRequest {
    id: u32,
    shared: Arc<Shared>,
    writer: Arc<AsyncMutex<ChildStdin>>,
    tree: Arc<Mutex<ProcessTree>>,
    phase: Phase,
}
impl Drop for PendingRequest {
    fn drop(&mut self) {
        if let Ok(mut pending) = self.shared.pending.lock() {
            pending.remove(&self.id);
        }
        match self.phase {
            Phase::Writing => {
                self.shared.disconnect();
                if let Ok(mut tree) = self.tree.lock() {
                    let _ = tree.stop();
                }
            }
            Phase::Sent => {
                let writer = self.writer.clone();
                let id = self.id;
                if let Ok(handle) = tokio::runtime::Handle::try_current() {
                    handle.spawn(async move {
                        let _ = tokio::time::timeout(Duration::from_millis(200), write_frame(&writer, &json!({"jsonrpc":"2.0","method":"$/cancelRequest","params":{"id":id}}))).await;
                    });
                }
            }
            _ => {}
        }
    }
}

pub(super) struct Connection {
    child: Child,
    tree: Arc<Mutex<ProcessTree>>,
    writer: Arc<AsyncMutex<ChildStdin>>,
    reader: JoinHandle<()>,
    stderr: JoinHandle<()>,
    next_id: u32,
    pub shared: Arc<Shared>,
    pub capabilities: Value,
    pub open_close: bool,
    pub sync_kind: u64,
}
impl Connection {
    pub async fn start(
        config: &ServerConfig,
        executable: &Path,
        project: &Path,
        notify: Notify,
        cancel: &CancellationToken,
    ) -> Result<Self> {
        if cancel.is_cancelled() {
            return Err(failed(
                FailureKind::Cancelled,
                Delivery::NotStarted,
                "Language-server startup was cancelled.",
            ));
        }
        if !config.enabled || !config.trusted {
            return Err(failed(
                FailureKind::Unavailable,
                Delivery::NotStarted,
                "Language server is disabled or untrusted.",
            ));
        }
        let mut command = Command::new(executable);
        command
            .args(&config.args)
            .envs(&config.env)
            .current_dir(config.working_directory(project)?)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let (mut child, tree) = ProcessTree::spawn(&mut command)?;
        let tree = Arc::new(Mutex::new(tree));
        let writer = Arc::new(AsyncMutex::new(
            child
                .stdin
                .take()
                .ok_or("Language-server stdin is unavailable.")?,
        ));
        let stdout = child
            .stdout
            .take()
            .ok_or("Language-server stdout is unavailable.")?;
        let mut error_pipe = child
            .stderr
            .take()
            .ok_or("Language-server stderr is unavailable.")?;
        let shared = Arc::new(Shared {
            pending: Mutex::new(BTreeMap::new()),
            documents: Mutex::new(BTreeMap::new()),
            diagnostics: Mutex::new(BTreeMap::new()),
            changed: Changed::new(),
            alive: AtomicBool::new(true),
            discarded_diagnostics: AtomicU32::new(0),
        });
        let stderr = tokio::spawn(async move {
            let mut buffer = [0; 8192];
            while matches!(error_pipe.read(&mut buffer).await, Ok(count) if count>0) {}
        });
        let reader_writer = writer.clone();
        let reader_shared = shared.clone();
        let reader_tree = tree.clone();
        let reader_project = project.to_owned();
        let reader_config = config.clone();
        let fingerprint = config.fingerprint()?;
        let reader = tokio::spawn(async move {
            let mut reader = BufReader::new(stdout);
            loop {
                let message = match read_frame(&mut reader).await {
                    Ok(Some(message)) => message,
                    _ => break,
                };
                if message["method"].is_string() {
                    if message.get("id").is_some() {
                        let response = server_request(&reader_project, &reader_config, &message);
                        if !matches!(
                            tokio::time::timeout(
                                Duration::from_secs(1),
                                write_frame(&reader_writer, &response)
                            )
                            .await,
                            Ok(Ok(()))
                        ) {
                            break;
                        }
                    } else if server_notification(
                        &reader_project,
                        &reader_config,
                        &fingerprint,
                        &reader_shared,
                        &notify,
                        &message,
                    )
                    .is_err()
                    {
                        break;
                    }
                } else if let Some(id) =
                    message["id"].as_u64().and_then(|id| u32::try_from(id).ok())
                {
                    let sender = reader_shared
                        .pending
                        .lock()
                        .ok()
                        .and_then(|mut pending| pending.remove(&id));
                    if let Some(sender) = sender {
                        let _ = sender.send(Ok(message));
                    }
                }
            }
            reader_shared.disconnect();
            notify(
                json!({"type":"lsp.disconnected","source":"lsp","server_id":reader_config.id(),"source_version":reader_config.source_version,"configuration_sha256":fingerprint,"project_root":reader_project}),
            );
            if let Ok(mut tree) = reader_tree.lock() {
                let _ = tree.stop();
            }
        });
        let mut connection = Self {
            child,
            tree,
            writer,
            reader,
            stderr,
            next_id: 0,
            shared,
            capabilities: Value::Null,
            open_close: false,
            sync_kind: 0,
        };
        let params = json!({"processId":std::process::id(),"clientInfo":{"name":"Reverie CLI","version":reverie_protocol::VERSION},
            "rootUri":evidence::file_uri(project)?,"workspaceFolders":[{"uri":evidence::file_uri(project)?,"name":project.file_name().unwrap_or_default().to_string_lossy()}],
            "initializationOptions":config.initialization_options,
            "capabilities":{"general":{"positionEncodings":["utf-16"]},"window":{"workDoneProgress":true},
                "workspace":{"configuration":true,"workspaceFolders":true,"applyEdit":false,"symbol":{"dynamicRegistration":false}},
                "textDocument":{"synchronization":{"dynamicRegistration":false,"didSave":false},
                    "definition":{"dynamicRegistration":false,"linkSupport":true},
                    "documentSymbol":{"dynamicRegistration":false,"hierarchicalDocumentSymbolSupport":true},
                    "publishDiagnostics":{"relatedInformation":true,"versionSupport":true,"dataSupport":false}}}});
        let initialized = connection
            .request(
                "initialize",
                params,
                config.startup_timeout_ms,
                config,
                cancel,
            )
            .await;
        let initialized = match initialized {
            Ok(value) => value,
            Err(error) => {
                connection.close(config.shutdown_timeout_ms, config).await;
                return Err(error);
            }
        };
        let capabilities = initialized
            .get("capabilities")
            .filter(|value| value.is_object())
            .cloned();
        if capabilities.as_ref().is_none_or(|value| {
            value["positionEncoding"]
                .as_str()
                .is_some_and(|value| value != "utf-16")
        }) {
            connection.close(config.shutdown_timeout_ms, config).await;
            return Err(failed(
                FailureKind::Protocol,
                Delivery::Completed,
                "Language server did not negotiate valid UTF-16 capabilities.",
            ));
        }
        connection.capabilities = capabilities.unwrap();
        let sync = &connection.capabilities["textDocumentSync"];
        connection.sync_kind = sync
            .as_u64()
            .or_else(|| sync["change"].as_u64())
            .unwrap_or(0);
        if connection.sync_kind > 2 {
            connection.close(config.shutdown_timeout_ms, config).await;
            return Err(failed(
                FailureKind::Protocol,
                Delivery::Completed,
                "Language server advertised an invalid document synchronization kind.",
            ));
        }
        connection.open_close = sync.as_u64().is_some_and(|kind| kind > 0)
            || sync["openClose"].as_bool().unwrap_or(false);
        if let Err(error) = connection.notify("initialized", json!({})).await {
            connection.close(config.shutdown_timeout_ms, config).await;
            return Err(error);
        }
        if !config.settings.is_null() {
            connection
                .notify(
                    "workspace/didChangeConfiguration",
                    json!({"settings":config.settings}),
                )
                .await?;
        }
        Ok(connection)
    }
    pub fn pid(&self) -> Option<u32> {
        self.child.id()
    }
    pub fn supports(&self, capability: &str) -> bool {
        self.capabilities[capability]
            .as_bool()
            .unwrap_or_else(|| self.capabilities[capability].is_object())
    }
    pub async fn notify(&self, method: &str, params: Value) -> Result<()> {
        let result = tokio::time::timeout(
            Duration::from_secs(1),
            write_frame(
                &self.writer,
                &json!({"jsonrpc":"2.0","method":method,"params":params}),
            ),
        )
        .await;
        if !matches!(result, Ok(Ok(()))) {
            self.shared.disconnect();
            if let Ok(mut tree) = self.tree.lock() {
                let _ = tree.stop();
            }
            return Err(failed(
                FailureKind::Protocol,
                Delivery::Unknown,
                "Language-service notification could not be completely written.",
            ));
        }
        Ok(())
    }
    pub async fn request(
        &mut self,
        method: &str,
        params: Value,
        timeout_ms: u64,
        config: &ServerConfig,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        if cancel.is_cancelled() {
            return Err(failed(
                FailureKind::Cancelled,
                Delivery::NotStarted,
                "Language-service request was cancelled before transmission.",
            ));
        }
        if !self.shared.alive.load(Ordering::Acquire) {
            return Err(failed(
                FailureKind::Unavailable,
                Delivery::NotStarted,
                "Language-server connection is unavailable.",
            ));
        }
        self.next_id = self
            .next_id
            .checked_add(1)
            .filter(|value| *value <= i32::MAX as u32)
            .ok_or("Language-service request identity exhausted.")?;
        let id = self.next_id;
        let (sender, receiver) = oneshot::channel();
        lock(&self.shared.pending)?.insert(id, sender);
        let mut pending = PendingRequest {
            id,
            shared: self.shared.clone(),
            writer: self.writer.clone(),
            tree: self.tree.clone(),
            phase: Phase::Pending,
        };
        let bytes =
            serde_json::to_vec(&json!({"jsonrpc":"2.0","id":id,"method":method,"params":params}))?;
        if bytes.len() > MESSAGE_LIMIT {
            return Err(failed(
                FailureKind::Invalid,
                Delivery::NotStarted,
                "Language-service request exceeds 16 MiB.",
            ));
        }
        let deadline = tokio::time::Instant::now() + Duration::from_millis(timeout_ms);
        let mut writer = tokio::select! {
            biased;
            _ = cancel.cancelled() => return Err(failed(FailureKind::Cancelled,Delivery::NotStarted,"Language-service request was cancelled before transmission.")),
            _ = tokio::time::sleep_until(deadline) => return Err(failed(FailureKind::Timeout,Delivery::NotStarted,"Language-service request timed out before transmission.")),
            writer = self.writer.lock() => writer,
        };
        pending.phase = Phase::Writing;
        let writing = async {
            writer
                .write_all(format!("Content-Length: {}\r\n\r\n", bytes.len()).as_bytes())
                .await?;
            writer.write_all(&bytes).await?;
            writer.flush().await
        };
        let sent = tokio::select! {
            biased;
            _ = cancel.cancelled() => Err(failed(FailureKind::Cancelled,Delivery::Unknown,"Language-service request was cancelled during transmission.")),
            _ = tokio::time::sleep_until(deadline) => Err(failed(FailureKind::Timeout,Delivery::Unknown,"Language-service request timed out during transmission.")),
            result = writing => result.map_err(|_|failed(FailureKind::Protocol,Delivery::Unknown,"Language-service request could not be completely written.")),
        };
        drop(writer);
        sent?;
        pending.phase = Phase::Sent;
        let response = tokio::select! {
            biased;
            _ = cancel.cancelled() => return Err(failed(FailureKind::Cancelled,Delivery::Unknown,"Language-service query was cancelled; cancellation was requested and its result is unknown.")),
            _ = tokio::time::sleep_until(deadline) => return Err(failed(FailureKind::Timeout,Delivery::Unknown,"Language-service query timed out; it will not be automatically replayed.")),
            response = receiver => response.map_err(|_|failed(FailureKind::Protocol,Delivery::Unknown,"Language-server response channel ended."))??,
        };
        pending.phase = Phase::Finished;
        if let Some(error) = response.get("error") {
            return Err(failed(
                FailureKind::Server,
                Delivery::Completed,
                format!(
                    "Language-server error {}: {}",
                    error["code"].as_i64().unwrap_or(-32603),
                    config.redacted(error["message"].as_str().unwrap_or("Request failed."))
                ),
            ));
        }
        response.get("result").cloned().ok_or_else(|| {
            failed(
                FailureKind::Protocol,
                Delivery::Completed,
                "Language-server response has no result.",
            )
        })
    }
    pub async fn ensure_document(
        &self,
        project: &Path,
        input: &str,
        language: &str,
    ) -> Result<Document> {
        let mut document = Document::read(project, input)?;
        let old = lock(&self.shared.documents)?.get(&document.uri).cloned();
        if let Some(old) = old.as_ref() {
            document.version = old.version;
            document.opened = old.opened;
            if old.sha256 == document.sha256 {
                return Ok(document);
            }
            if old.opened && self.sync_kind == 0 {
                return Err(failed(
                    FailureKind::Unavailable,
                    Delivery::NotStarted,
                    "Language server cannot synchronize the changed open document.",
                ));
            }
            document.version = old
                .version
                .checked_add(1)
                .ok_or("Language-service document revision exhausted.")?;
            lock(&self.shared.diagnostics)?.remove(&document.uri);
        }
        if old.is_none() && self.open_close {
            document.opened = true;
        }
        lock(&self.shared.documents)?.insert(document.uri.clone(), document.clone());
        if old.is_none() && self.open_close {
            self.notify("textDocument/didOpen",json!({"textDocument":{"uri":document.uri,"languageId":language,"version":document.version,"text":document.text}})).await?;
        } else if let Some(old) = old.filter(|old| old.opened) {
            let change = if self.sync_kind == 2 {
                json!({"range":{"start":{"line":0,"character":0},"end":evidence::Position::from_utf8_offset(&old.text,old.text.len())?},"text":document.text})
            } else {
                json!({"text":document.text})
            };
            self.notify("textDocument/didChange",json!({"textDocument":{"uri":document.uri,"version":document.version},"contentChanges":[change]})).await?;
        }
        Ok(document)
    }
    pub async fn diagnostic_batch(
        &self,
        document: &Document,
        cancel: &CancellationToken,
    ) -> Result<Option<DiagnosticBatch>> {
        let deadline = tokio::time::Instant::now() + Duration::from_millis(1500);
        loop {
            let changed = self.shared.changed.notified();
            if let Some(batch) = lock(&self.shared.diagnostics)?.get(&document.uri).cloned()
                && batch.sha256 == document.sha256
                && (!document.opened
                    || batch.version.is_none()
                    || batch.version == Some(document.version))
            {
                return Ok(Some(batch));
            }
            tokio::select! {
                biased;
                _ = cancel.cancelled() => return Err(failed(FailureKind::Cancelled,Delivery::Completed,"Waiting for language-service diagnostics was cancelled.")),
                _ = tokio::time::sleep_until(deadline) => return Ok(None),
                _ = changed => {},
            }
            if !self.shared.alive.load(Ordering::Acquire) {
                return Err(failed(
                    FailureKind::Unavailable,
                    Delivery::Unknown,
                    "Language server ended before current diagnostics arrived.",
                ));
            }
        }
    }
    pub async fn close_document(&self, uri: &str) -> Result<()> {
        let removed = lock(&self.shared.documents)?.remove(uri);
        lock(&self.shared.diagnostics)?.remove(uri);
        if removed.is_some_and(|document| document.opened) {
            self.notify("textDocument/didClose", json!({"textDocument":{"uri":uri}}))
                .await?;
        }
        Ok(())
    }
    pub async fn close(&mut self, timeout_ms: u64, config: &ServerConfig) {
        if self.shared.alive.load(Ordering::Acquire) {
            let _ = self
                .request(
                    "shutdown",
                    Value::Null,
                    timeout_ms,
                    config,
                    &CancellationToken::new(),
                )
                .await;
            let _ = tokio::time::timeout(
                Duration::from_millis(200),
                write_frame(
                    &self.writer,
                    &json!({"jsonrpc":"2.0","method":"exit","params":Value::Null}),
                ),
            )
            .await;
        }
        let _ = tokio::time::timeout(Duration::from_millis(300), self.child.wait()).await;
        if let Ok(mut tree) = self.tree.lock() {
            let _ = tree.stop();
        }
        let _ = tokio::time::timeout(Duration::from_secs(1), self.child.wait()).await;
        self.shared.disconnect();
        self.reader.abort();
        self.stderr.abort();
    }
}
impl Drop for Connection {
    fn drop(&mut self) {
        self.shared.disconnect();
        if let Ok(mut tree) = self.tree.lock() {
            let _ = tree.stop();
        }
        self.reader.abort();
        self.stderr.abort();
    }
}
