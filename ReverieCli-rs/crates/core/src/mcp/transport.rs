use super::{
    config::{PROTOCOL_VERSION, ServerConfig, Transport, endpoint, expand_env},
    sse::{Decoder, MESSAGE_LIMIT},
};
use crate::Result;
use reverie_platform::command::ProcessTree;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    process::Stdio,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, Command},
    sync::{Mutex, mpsc},
    task::JoinHandle,
};
use tokio_util::sync::CancellationToken;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
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

#[derive(Debug)]
pub struct Failure {
    pub message: String,
    pub delivery: Delivery,
    pub authorization: Option<String>,
}
impl std::fmt::Display for Failure {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}
impl std::error::Error for Failure {}
fn failed(
    message: impl Into<String>,
    delivery: Delivery,
) -> Box<dyn std::error::Error + Send + Sync> {
    Box::new(Failure {
        message: message.into(),
        delivery,
        authorization: None,
    })
}

pub type Notify = Arc<dyn Fn(Value) + Send + Sync>;

#[derive(Clone, Copy)]
pub struct RequestContext<'a> {
    pub config: &'a ServerConfig,
    pub project: &'a Path,
    pub auth: &'a BTreeMap<String, String>,
    pub protocol: &'a str,
    pub dirty: &'a AtomicBool,
    pub notify: &'a Notify,
}

fn server_reply(message: &Value, project: &Path) -> Option<Value> {
    let id = message.get("id")?;
    let method = message["method"].as_str()?;
    Some(match method {
        "ping" => json!({"jsonrpc":"2.0","id":id,"result":{}}),
        "roots/list" => match reqwest::Url::from_file_path(project) {
            Ok(uri) => {
                json!({"jsonrpc":"2.0","id":id,"result":{"roots":[{"uri":uri.as_str(),"name":project.file_name().unwrap_or_default().to_string_lossy()}]}})
            }
            Err(_) => {
                json!({"jsonrpc":"2.0","id":id,"error":{"code":-32603,"message":"Workspace root cannot be represented as a file URI."}})
            }
        },
        _ => {
            json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"This client capability is not available."}})
        }
    })
}

fn notification(message: &Value, dirty: &AtomicBool, notify: &Notify) -> bool {
    if message.get("id").is_some() || !message["method"].is_string() {
        return false;
    }
    match message["method"].as_str().unwrap() {
        "notifications/tools/list_changed"
        | "notifications/resources/list_changed"
        | "notifications/prompts/list_changed" => dirty.store(true, Ordering::Release),
        "notifications/progress" => {
            notify(json!({"type":"mcp.progress","progress":message["params"]}))
        }
        _ => {}
    }
    true
}

async fn line(reader: &mut BufReader<tokio::process::ChildStdout>) -> Result<Option<Value>> {
    let mut bytes = Vec::new();
    loop {
        let available = reader.fill_buf().await?;
        if available.is_empty() {
            if bytes.is_empty() {
                return Ok(None);
            }
            return Err("MCP stdout ended before its JSONL message boundary.".into());
        }
        let end = available.iter().position(|byte| *byte == b'\n');
        let length = end.map_or(available.len(), |end| end + 1);
        if bytes.len() + length > MESSAGE_LIMIT {
            return Err("MCP stdout message exceeds 16 MiB.".into());
        }
        bytes.extend_from_slice(&available[..length]);
        reader.consume(length);
        if end.is_some() {
            let message: Value = serde_json::from_slice(&bytes)?;
            if !message.is_object() || message["jsonrpc"] != "2.0" {
                return Err("MCP stdout must contain JSON-RPC 2.0 objects.".into());
            }
            return Ok(Some(message));
        }
    }
}

async fn write_stdin(writer: &Mutex<ChildStdin>, message: &Value) -> Result<()> {
    let mut bytes = serde_json::to_vec(message)?;
    bytes.push(b'\n');
    let mut writer = writer.lock().await;
    writer.write_all(&bytes).await?;
    writer.flush().await?;
    Ok(())
}

struct StdioConnection {
    child: Child,
    tree: ProcessTree,
    writer: Arc<Mutex<ChildStdin>>,
    receiver: mpsc::Receiver<Result<Value>>,
    reader: JoinHandle<()>,
    stderr: JoinHandle<()>,
}
impl StdioConnection {
    fn spawn(
        config: &ServerConfig,
        project: &Path,
        dirty: Arc<AtomicBool>,
        notify: Notify,
    ) -> Result<Self> {
        let mut command = Command::new(&config.command);
        command.args(&config.args);
        let cwd = if config.cwd.is_empty() {
            project.to_owned()
        } else {
            let expanded = expand_env(&config.cwd, &config.env);
            let path = PathBuf::from(expanded);
            if path.is_absolute() {
                path
            } else {
                project.join(path)
            }
        };
        command
            .current_dir(cwd)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        for (name, value) in &config.env {
            command.env(name, expand_env(value, &config.env));
        }
        let (mut child, tree) = ProcessTree::spawn(&mut command)?;
        let writer = Arc::new(Mutex::new(
            child
                .stdin
                .take()
                .ok_or("MCP child stdin is unavailable.")?,
        ));
        let stdout = child
            .stdout
            .take()
            .ok_or("MCP child stdout is unavailable.")?;
        let mut stderr_pipe = child
            .stderr
            .take()
            .ok_or("MCP child stderr is unavailable.")?;
        let stderr = tokio::spawn(async move {
            let mut bytes = [0; 8192];
            while matches!(stderr_pipe.read(&mut bytes).await,Ok(count) if count>0) {}
        });
        let (sender, receiver) = mpsc::channel(64);
        let reply_writer = writer.clone();
        let project = project.to_owned();
        let reader = tokio::spawn(async move {
            let mut stdout = BufReader::new(stdout);
            loop {
                match line(&mut stdout).await {
                    Ok(Some(message)) => {
                        if notification(&message, &dirty, &notify) {
                            continue;
                        }
                        if let Some(reply) = server_reply(&message, &project) {
                            if write_stdin(&reply_writer, &reply).await.is_err() {
                                break;
                            }
                        } else if sender.send(Ok(message)).await.is_err() {
                            break;
                        }
                    }
                    Ok(None) => break,
                    Err(_) => {
                        let _ = sender
                            .send(Err(
                                "MCP stdout contained an invalid or oversized message.".into()
                            ))
                            .await;
                        break;
                    }
                }
            }
        });
        Ok(Self {
            child,
            tree,
            writer,
            receiver,
            reader,
            stderr,
        })
    }
    async fn close(&mut self) {
        let _ = tokio::time::timeout(Duration::from_millis(200), async {
            self.writer.lock().await.shutdown().await
        })
        .await;
        let _ = tokio::time::timeout(Duration::from_millis(200), self.child.wait()).await;
        let _ = self.tree.stop();
        let _ = tokio::time::timeout(Duration::from_secs(1), self.child.wait()).await;
        self.reader.abort();
        self.stderr.abort();
    }
}

async fn read_http(
    mut response: reqwest::Response,
    id: &Value,
    client: &reqwest::Client,
    url: &str,
    headers: reqwest::header::HeaderMap,
    context: RequestContext<'_>,
) -> Result<Value> {
    let RequestContext {
        project,
        dirty,
        notify,
        ..
    } = context;
    let streaming = response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.starts_with("text/event-stream"));
    let mut decoder = Decoder::default();
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|error| {
        failed(
            format!("MCP response disconnected: {}", error.without_url()),
            Delivery::Unknown,
        )
    })? {
        if streaming {
            for event in decoder.push(&chunk)? {
                let message: Value = serde_json::from_str(&event.data)?;
                if notification(&message, dirty, notify) {
                    continue;
                }
                if let Some(reply) = server_reply(&message, project) {
                    let response = client
                        .post(url)
                        .headers(headers.clone())
                        .json(&reply)
                        .send()
                        .await
                        .map_err(|error| {
                            failed(
                                format!("MCP client reply failed: {}", error.without_url()),
                                Delivery::Unknown,
                            )
                        })?;
                    status(&response, Delivery::Unknown)?;
                } else if message.get("id") == Some(id) {
                    return rpc_response(message, id);
                }
            }
        } else {
            if body.len() + chunk.len() > MESSAGE_LIMIT {
                return Err(failed("MCP response exceeds 16 MiB.", Delivery::Unknown));
            }
            body.extend_from_slice(&chunk);
        }
    }
    if streaming {
        Err(failed(
            "MCP event stream ended before its response; request was not replayed.",
            Delivery::Unknown,
        ))
    } else {
        rpc_response(serde_json::from_slice(&body)?, id)
    }
}

async fn open_sse(
    config: &ServerConfig,
    project: &Path,
    auth: &BTreeMap<String, String>,
    dirty: Arc<AtomicBool>,
    notify: Notify,
    cancel: &CancellationToken,
) -> Result<SseConnection> {
    let client = http_client()?;
    let base = endpoint(&config.endpoint)?;
    let mut headers = request_headers(config, auth, PROTOCOL_VERSION, None)?;
    headers.insert(
        "accept",
        reqwest::header::HeaderValue::from_static("text/event-stream"),
    );
    let response = tokio::select! {
        _=cancel.cancelled()=>return Err(failed("MCP SSE connection cancelled before execution.",Delivery::NotStarted)),
        response=tokio::time::timeout(Duration::from_secs(15),client.get(base.clone()).headers(headers.clone()).send())=>response.map_err(|_|failed("MCP SSE connection timed out.",Delivery::NotStarted))?.map_err(|error|failed(format!("MCP SSE connection failed: {}",error.without_url()),Delivery::NotStarted))?,
    };
    status(&response, Delivery::NotStarted)?;
    if !response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.starts_with("text/event-stream"))
    {
        return Err(failed(
            "The MCP legacy SSE endpoint did not return an event stream.",
            Delivery::NotStarted,
        ));
    }
    let (sender, receiver) = mpsc::channel(64);
    let (endpoint_sender, endpoint_receiver) = tokio::sync::oneshot::channel();
    let stream_cancel = CancellationToken::new();
    let stream_token = stream_cancel.clone();
    let post_client = client.clone();
    let project = project.to_owned();
    let reader = tokio::spawn(async move {
        let read = async {
            let mut response = response;
            let mut decoder = Decoder::default();
            let mut endpoint_sender = Some(endpoint_sender);
            let mut post_endpoint = None;
            while let Some(chunk) = response
                .chunk()
                .await
                .map_err(|error| format!("MCP SSE stream disconnected: {}", error.without_url()))?
            {
                for event in decoder.push(&chunk)? {
                    if event.kind == "endpoint" {
                        let address = base.join(event.data.trim())?;
                        if address.origin() != base.origin()
                            || address.scheme() != base.scheme()
                            || !address.username().is_empty()
                            || address.password().is_some()
                        {
                            return Err(
                                "MCP SSE message endpoint changed origin or included credentials."
                                    .into(),
                            );
                        }
                        if let Some(sender) = endpoint_sender.take() {
                            let _ = sender.send(address.clone());
                            post_endpoint = Some(address);
                        }
                        continue;
                    }
                    let message: Value = serde_json::from_str(&event.data)?;
                    if notification(&message, &dirty, &notify) {
                        continue;
                    }
                    if let Some(reply) = server_reply(&message, &project) {
                        let address=post_endpoint.as_ref().ok_or("MCP SSE requested client capabilities before its endpoint was advertised.")?;
                        let response = post_client
                            .post(address.clone())
                            .headers(headers.clone())
                            .json(&reply)
                            .send()
                            .await
                            .map_err(|error| {
                                format!("MCP SSE client reply failed: {}", error.without_url())
                            })?;
                        status(&response, Delivery::Unknown)?;
                    } else if sender.send(Ok(message)).await.is_err() {
                        return Ok(());
                    }
                }
            }
            Err::<(), Box<dyn std::error::Error + Send + Sync>>("MCP SSE stream closed.".into())
        };
        let result = tokio::select! {_=stream_token.cancelled()=>Ok(()),result=read=>result};
        if let Err(error) = result {
            let _ = sender.send(Err(error)).await;
        }
    });
    let result = tokio::select! {
        _=cancel.cancelled()=>Err(failed("MCP SSE endpoint discovery cancelled.",Delivery::NotStarted)),
        endpoint=tokio::time::timeout(Duration::from_secs(15),endpoint_receiver)=>match endpoint {
            Ok(Ok(endpoint))=>Ok(endpoint),
            _=>Err(failed("MCP SSE server did not advertise its message endpoint.",Delivery::NotStarted)),
        },
    };
    match result {
        Ok(endpoint) => Ok(SseConnection {
            client,
            endpoint,
            receiver,
            reader,
            cancel: stream_cancel,
        }),
        Err(error) => {
            stream_cancel.cancel();
            reader.abort();
            Err(error)
        }
    }
}
impl Drop for StdioConnection {
    fn drop(&mut self) {
        self.reader.abort();
        self.stderr.abort();
        let _ = self.tree.stop();
        let _ = self.child.start_kill();
    }
}

struct HttpConnection {
    client: reqwest::Client,
    session: Option<String>,
    headers: reqwest::header::HeaderMap,
}
struct SseConnection {
    client: reqwest::Client,
    endpoint: reqwest::Url,
    receiver: mpsc::Receiver<Result<Value>>,
    reader: JoinHandle<()>,
    cancel: CancellationToken,
}
impl Drop for SseConnection {
    fn drop(&mut self) {
        self.cancel.cancel();
        self.reader.abort();
    }
}

pub struct Connection {
    kind: Kind,
    invalid: bool,
}
enum Kind {
    Stdio(StdioConnection),
    Http(HttpConnection),
    Sse(SseConnection),
}

fn http_client() -> Result<reqwest::Client> {
    Ok(reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .retry(reqwest::retry::never())
        .build()?)
}
fn request_headers(
    config: &ServerConfig,
    auth: &BTreeMap<String, String>,
    protocol: &str,
    session: Option<&str>,
) -> Result<reqwest::header::HeaderMap> {
    use reqwest::header::{HeaderName, HeaderValue};
    let mut headers = reqwest::header::HeaderMap::new();
    for (name, value) in &config.headers {
        headers.insert(
            HeaderName::from_bytes(name.as_bytes())?,
            HeaderValue::from_str(&expand_env(value, &config.env))?,
        );
    }
    for (name, value) in auth {
        headers.insert(
            HeaderName::from_bytes(name.as_bytes())?,
            HeaderValue::from_str(value)?,
        );
    }
    headers.insert(
        "accept",
        HeaderValue::from_static("application/json, text/event-stream"),
    );
    headers.insert("content-type", HeaderValue::from_static("application/json"));
    headers.insert("mcp-protocol-version", HeaderValue::from_str(protocol)?);
    if let Some(session) = session {
        headers.insert("mcp-session-id", HeaderValue::from_str(session)?);
    }
    Ok(headers)
}
fn status(response: &reqwest::Response, delivery: Delivery) -> Result<()> {
    let challenge = response
        .headers()
        .get_all("www-authenticate")
        .iter()
        .filter_map(|value| value.to_str().ok())
        .collect::<Vec<_>>()
        .join(", ");
    if response.status() == reqwest::StatusCode::UNAUTHORIZED
        || (response.status() == reqwest::StatusCode::FORBIDDEN && !challenge.is_empty())
    {
        return Err(Box::new(Failure {
            message: "MCP authorization or additional scope is required.".into(),
            delivery: Delivery::NotStarted,
            authorization: Some(if challenge.len() <= 16384 {
                challenge
            } else {
                String::new()
            }),
        }));
    }
    if !response.status().is_success() {
        return Err(failed(
            format!("MCP HTTP request failed with status {}.", response.status()),
            delivery,
        ));
    }
    Ok(())
}
fn rpc_response(message: Value, id: &Value) -> Result<Value> {
    if !message.is_object() || message["jsonrpc"] != "2.0" || message.get("id") != Some(id) {
        return Err(failed(
            "MCP returned a response with the wrong JSON-RPC identity.",
            Delivery::Unknown,
        ));
    }
    if let Some(error) = message.get("error") {
        if message.get("result").is_some()
            || !error["code"].is_i64()
            || !error["message"].is_string()
        {
            return Err(failed(
                "MCP returned an invalid JSON-RPC error response.",
                Delivery::Unknown,
            ));
        }
        return Err(failed(
            format!(
                "MCP JSON-RPC error {}: {}",
                error["code"],
                error["message"].as_str().unwrap_or("Unknown server error")
            ),
            Delivery::Completed,
        ));
    }
    message.get("result").cloned().ok_or_else(|| {
        failed(
            "MCP response has neither a result nor an error.",
            Delivery::Unknown,
        )
    })
}

impl Connection {
    pub async fn open(
        config: &ServerConfig,
        project: &Path,
        auth: &BTreeMap<String, String>,
        dirty: Arc<AtomicBool>,
        notify: Notify,
        cancel: &CancellationToken,
    ) -> Result<Self> {
        let kind = match config.transport {
            Transport::Stdio => {
                Kind::Stdio(StdioConnection::spawn(config, project, dirty, notify)?)
            }
            Transport::Http => Kind::Http(HttpConnection {
                client: http_client()?,
                session: None,
                headers: reqwest::header::HeaderMap::new(),
            }),
            Transport::Sse => {
                Kind::Sse(open_sse(config, project, auth, dirty, notify, cancel).await?)
            }
        };
        Ok(Self {
            kind,
            invalid: false,
        })
    }
    pub fn live(&mut self) -> bool {
        if self.invalid {
            return false;
        }
        match &mut self.kind {
            Kind::Stdio(connection) => {
                matches!(connection.child.try_wait(), Ok(None)) && !connection.reader.is_finished()
            }
            Kind::Http(_) => true,
            Kind::Sse(connection) => !connection.reader.is_finished(),
        }
    }
    pub async fn request(
        &mut self,
        context: RequestContext<'_>,
        message: Value,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        let RequestContext {
            config,
            auth,
            protocol,
            ..
        } = context;
        if cancel.is_cancelled() {
            return Err(failed(
                "MCP request cancelled before execution.",
                Delivery::NotStarted,
            ));
        }
        let operation = async {
            match &mut self.kind {
                Kind::Stdio(connection) => {
                    write_stdin(&connection.writer, &message)
                        .await
                        .map_err(|_| {
                            failed(
                                "MCP request could not be written; delivery is uncertain.",
                                Delivery::Unknown,
                            )
                        })?;
                    let Some(id) = message.get("id") else {
                        return Ok(json!({}));
                    };
                    while let Some(response) = connection.receiver.recv().await {
                        let response = response?;
                        if response.get("id") == Some(id) {
                            return rpc_response(response, id);
                        }
                    }
                    Err(failed(
                        "MCP child disconnected while awaiting its response.",
                        Delivery::Unknown,
                    ))
                }
                Kind::Http(connection) => {
                    let headers =
                        request_headers(config, auth, protocol, connection.session.as_deref())?;
                    let response = connection
                        .client
                        .post(&config.endpoint)
                        .headers(headers.clone())
                        .json(&message)
                        .send()
                        .await
                        .map_err(|error| {
                            failed(
                                format!("MCP HTTP request failed: {}", error.without_url()),
                                Delivery::Unknown,
                            )
                        })?;
                    status(&response, Delivery::Unknown)?;
                    if let Some(session) = response.headers().get("mcp-session-id") {
                        let session = session.to_str()?;
                        if connection
                            .session
                            .as_deref()
                            .is_some_and(|previous| previous != session)
                        {
                            return Err(failed(
                                "MCP session identity changed during the call; delivery is uncertain.",
                                Delivery::Unknown,
                            ));
                        }
                        connection.session = Some(session.into());
                    }
                    connection.headers =
                        request_headers(config, auth, protocol, connection.session.as_deref())?;
                    let Some(id) = message.get("id") else {
                        return Ok(json!({}));
                    };
                    read_http(
                        response,
                        id,
                        &connection.client,
                        &config.endpoint,
                        request_headers(config, auth, protocol, connection.session.as_deref())?,
                        context,
                    )
                    .await
                }
                Kind::Sse(connection) => {
                    let headers = request_headers(config, auth, protocol, None)?;
                    let response = connection
                        .client
                        .post(connection.endpoint.clone())
                        .headers(headers)
                        .json(&message)
                        .send()
                        .await
                        .map_err(|error| {
                            failed(
                                format!("MCP SSE POST failed: {}", error.without_url()),
                                Delivery::Unknown,
                            )
                        })?;
                    status(&response, Delivery::Unknown)?;
                    let Some(id) = message.get("id") else {
                        return Ok(json!({}));
                    };
                    if response.status() != reqwest::StatusCode::ACCEPTED
                        && response.content_length() != Some(0)
                    {
                        return read_http(
                            response,
                            id,
                            &connection.client,
                            connection.endpoint.as_str(),
                            request_headers(config, auth, protocol, None)?,
                            context,
                        )
                        .await;
                    }
                    while let Some(response) = connection.receiver.recv().await {
                        let response = response?;
                        if response.get("id") == Some(id) {
                            return rpc_response(response, id);
                        }
                    }
                    Err(failed(
                        "MCP SSE stream disconnected while awaiting its response.",
                        Delivery::Unknown,
                    ))
                }
            }
        };
        let (result, interrupted) = tokio::select! {
            _=cancel.cancelled()=>(Err(failed("MCP request cancelled after transmission; delivery is uncertain.",Delivery::Unknown)),true),
            result=tokio::time::timeout(Duration::from_millis(config.timeout_ms),operation)=>match result {Ok(result)=>(result,false),Err(_)=>(Err(failed("MCP request timed out; delivery is uncertain.",Delivery::Unknown)),true)},
        };
        if interrupted
            && message["method"] != "initialize"
            && let Some(id) = message.get("id")
        {
            self.cancel_request(context, id).await;
        }
        if result.as_ref().err().is_some_and(|error| {
            error.downcast_ref::<Failure>().is_none_or(|failure| {
                failure.delivery == Delivery::Unknown || failure.authorization.is_some()
            })
        }) {
            self.invalid = true;
        }
        result
    }
    async fn cancel_request(&mut self, context: RequestContext<'_>, id: &Value) {
        let message = json!({"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":id,"reason":"Client stopped waiting; delivery remains uncertain."}});
        let send = async {
            match &mut self.kind {
                Kind::Stdio(connection) => {
                    let _ = write_stdin(&connection.writer, &message).await;
                }
                Kind::Http(connection) => {
                    if let Ok(headers) = request_headers(
                        context.config,
                        context.auth,
                        context.protocol,
                        connection.session.as_deref(),
                    ) {
                        let _ = connection
                            .client
                            .post(&context.config.endpoint)
                            .headers(headers)
                            .json(&message)
                            .send()
                            .await;
                    }
                }
                Kind::Sse(connection) => {
                    if let Ok(headers) =
                        request_headers(context.config, context.auth, context.protocol, None)
                    {
                        let _ = connection
                            .client
                            .post(connection.endpoint.clone())
                            .headers(headers)
                            .json(&message)
                            .send()
                            .await;
                    }
                }
            }
        };
        let _ = tokio::time::timeout(Duration::from_millis(500), send).await;
    }
    pub async fn close(
        &mut self,
        config: &ServerConfig,
        auth: &BTreeMap<String, String>,
        protocol: &str,
    ) {
        match &mut self.kind {
            Kind::Stdio(connection) => connection.close().await,
            Kind::Http(connection) => {
                if let Some(session) = connection.session.take()
                    && let Ok(headers) = if auth.is_empty() {
                        Ok(connection.headers.clone())
                    } else {
                        request_headers(config, auth, protocol, Some(&session))
                    }
                {
                    let _ = tokio::time::timeout(
                        Duration::from_secs(3),
                        connection
                            .client
                            .delete(&config.endpoint)
                            .headers(headers)
                            .send(),
                    )
                    .await;
                }
            }
            Kind::Sse(connection) => {
                connection.cancel.cancel();
                connection.reader.abort();
            }
        }
    }
}
