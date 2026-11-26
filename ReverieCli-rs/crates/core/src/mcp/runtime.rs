use super::{
    config::{DISCOVERY_TIMEOUT_MS, PROTOCOL_VERSION, ServerConfig, hash},
    privacy::Redactor,
    transport::{Connection, Delivery, Failure, Notify, RequestContext},
};
use crate::Result;
use reverie_platform::ToolResult;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, HashMap, HashSet},
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex, Weak,
        atomic::{AtomicBool, Ordering},
    },
    time::Duration,
};
use tokio::sync::Mutex as AsyncMutex;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

type Headers = BTreeMap<String, String>;
pub type AuthorizationHeaders = BTreeMap<String, Headers>;

#[derive(Clone)]
pub struct McpTool {
    pub name: String,
    pub server_id: String,
    pub tool_name: String,
    pub generation: String,
    pub definition: Value,
    pub metadata: Value,
}

#[derive(Clone)]
struct Catalogue {
    generation: String,
    protocol: String,
    server_info: Value,
    capabilities: Value,
    tools: Vec<Value>,
    resources: Vec<Value>,
    templates: Vec<Value>,
    prompts: Vec<Value>,
    errors: Vec<String>,
}

struct State {
    connection: Option<Connection>,
    protocol: String,
    next_id: u64,
    catalogue: Option<Catalogue>,
    handshake: Option<Value>,
}
pub struct McpClient {
    config: ServerConfig,
    project: PathBuf,
    state: AsyncMutex<State>,
    dirty: Arc<AtomicBool>,
    notify: Notify,
    redactor: Redactor,
    authorization: Mutex<Option<String>>,
    validators: Mutex<HashMap<String, Arc<jsonschema::Validator>>>,
    shutdown: CancellationToken,
}

impl State {
    async fn rpc(
        &mut self,
        client: &McpClient,
        method: &str,
        params: Value,
        auth: &Headers,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        self.next_id = self
            .next_id
            .checked_add(1)
            .ok_or("MCP request identity overflow.")?;
        let notification = method.starts_with("notifications/");
        let mut message = json!({"jsonrpc":"2.0","method":method,"params":params});
        if !notification {
            message["id"] = json!(self.next_id);
        }
        let connection = self
            .connection
            .as_mut()
            .ok_or("MCP connection is not initialized.")?;
        let context = RequestContext {
            config: &client.config,
            project: &client.project,
            auth,
            protocol: &self.protocol,
            dirty: &client.dirty,
            notify: &client.notify,
        };
        connection.request(context, message, cancel).await
    }
    async fn pages(
        &mut self,
        client: &McpClient,
        method: &str,
        field: &str,
        auth: &Headers,
        cancel: &CancellationToken,
    ) -> Result<Vec<Value>> {
        let mut cursor = None;
        let mut seen = HashSet::new();
        let mut items = Vec::new();
        loop {
            let page = self
                .rpc(
                    client,
                    method,
                    cursor
                        .as_ref()
                        .map_or_else(|| json!({}), |cursor: &String| json!({"cursor":cursor})),
                    auth,
                    cancel,
                )
                .await?;
            let entries = page[field]
                .as_array()
                .ok_or("MCP discovery page does not contain its expected array.")?;
            if items.len() + entries.len() > 100_000 {
                return Err("MCP discovery exceeds 100000 entries.".into());
            }
            if entries.iter().any(|item| !item.is_object()) {
                return Err("MCP discovery entries must be objects.".into());
            }
            items.extend(entries.iter().cloned());
            match page.get("nextCursor") {
                None | Some(Value::Null) => break,
                Some(Value::String(value)) if value.is_empty() => break,
                Some(Value::String(value)) if seen.insert(value.clone()) => {
                    cursor = Some(value.clone())
                }
                _ => return Err("MCP discovery returned an invalid or repeated cursor.".into()),
            }
        }
        Ok(items)
    }
}

impl McpClient {
    fn new(
        config: ServerConfig,
        project: PathBuf,
        notify: Notify,
        redactor: Redactor,
        shutdown: CancellationToken,
    ) -> Self {
        Self {
            config,
            project,
            state: AsyncMutex::new(State {
                connection: None,
                protocol: PROTOCOL_VERSION.into(),
                next_id: 0,
                catalogue: None,
                handshake: None,
            }),
            dirty: Arc::new(AtomicBool::new(true)),
            notify,
            redactor,
            authorization: Mutex::new(None),
            validators: Mutex::new(HashMap::new()),
            shutdown,
        }
    }
    pub fn configuration(&self) -> &ServerConfig {
        &self.config
    }
    fn input_validator(&self, schema: &Value) -> Result<Arc<jsonschema::Validator>> {
        let key = hash(&serde_json::to_vec(schema)?);
        let mut validators = self
            .validators
            .lock()
            .map_err(|_| "MCP validator cache lock was poisoned.")?;
        if let Some(validator) = validators.get(&key) {
            return Ok(validator.clone());
        }
        let validator = Arc::new(compile_input_schema(schema)?);
        validators.insert(key, validator.clone());
        Ok(validator)
    }
    async fn discover(&self, auth: &Headers, cancel: &CancellationToken) -> Result<Catalogue> {
        self.redactor.headers(auth);
        let operation = async {
            let mut state = tokio::select! {_=cancel.cancelled()=>return Err("MCP discovery cancelled before execution.".into()),state=self.state.lock()=>state};
            if let Some(catalogue) = state.catalogue.clone()
                && !self.dirty.load(Ordering::Acquire)
                && state.connection.as_mut().is_some_and(Connection::live)
            {
                return Ok(catalogue);
            }
            if state
                .connection
                .as_mut()
                .is_none_or(|connection| !connection.live())
            {
                if let Some(mut previous) = state.connection.take() {
                    previous.close(&self.config, auth, &state.protocol).await;
                }
                state.catalogue = None;
                state.handshake = None;
                state.protocol = PROTOCOL_VERSION.into();
                state.connection = Some(
                    Connection::open(
                        &self.config,
                        &self.project,
                        auth,
                        self.dirty.clone(),
                        self.notify.clone(),
                        cancel,
                    )
                    .await?,
                );
            }
            self.dirty.store(false, Ordering::Release);
            let handshake = if let Some(handshake) = state.handshake.clone() {
                handshake
            } else {
                let handshake=state.rpc(self,"initialize",json!({"protocolVersion":PROTOCOL_VERSION,"clientInfo":{"name":"Reverie CLI","version":reverie_protocol::VERSION},"capabilities":{"roots":{"listChanged":false}}}),auth,cancel).await?;
                state.handshake = Some(handshake.clone());
                handshake
            };
            let protocol = handshake["protocolVersion"]
                .as_str()
                .ok_or("MCP initialize response lacks protocolVersion.")?;
            if !["2025-06-18", "2025-11-25"].contains(&protocol) {
                return Err("Unsupported negotiated MCP protocol version.".into());
            }
            state.protocol = protocol.into();
            let capabilities = handshake["capabilities"]
                .as_object()
                .ok_or("MCP initialize response lacks its capabilities object.")?
                .clone();
            if state.catalogue.is_none() {
                state
                    .rpc(self, "notifications/initialized", json!({}), auth, cancel)
                    .await?;
            }
            let mut catalogue = Catalogue {
                generation: Uuid::new_v4().simple().to_string(),
                protocol: protocol.into(),
                server_info: handshake["serverInfo"].clone(),
                capabilities: Value::Object(capabilities.clone()),
                tools: Vec::new(),
                resources: Vec::new(),
                templates: Vec::new(),
                prompts: Vec::new(),
                errors: Vec::new(),
            };
            for (capability, method, field) in [
                ("tools", "tools/list", "tools"),
                ("resources", "resources/list", "resources"),
                ("resources", "resources/templates/list", "resourceTemplates"),
                ("prompts", "prompts/list", "prompts"),
            ] {
                if !capabilities.contains_key(capability) {
                    continue;
                }
                match state.pages(self, method, field, auth, cancel).await {
                    Ok(items) => match field {
                        "tools" => catalogue.tools = items,
                        "resources" => catalogue.resources = items,
                        "resourceTemplates" => catalogue.templates = items,
                        _ => catalogue.prompts = items,
                    },
                    Err(error) => {
                        if cancel.is_cancelled()
                            || error
                                .downcast_ref::<Failure>()
                                .is_some_and(|failure| failure.delivery != Delivery::Completed)
                        {
                            return Err(error);
                        }
                        catalogue
                            .errors
                            .push(self.redactor.text(&format!("{method}: {error}")));
                    }
                }
            }
            state.catalogue = Some(catalogue.clone());
            self.validators
                .lock()
                .map_err(|_| "MCP validator cache lock was poisoned.")?
                .clear();
            *self
                .authorization
                .lock()
                .unwrap_or_else(|error| error.into_inner()) = None;
            Ok(catalogue)
        };
        let result = tokio::select! {
            _=self.shutdown.cancelled()=>Err("MCP runtime is stopping.".into()),
            result=tokio::time::timeout(Duration::from_millis(DISCOVERY_TIMEOUT_MS),operation)=>result.unwrap_or_else(|_|Err("MCP discovery exceeded its total 15-second budget.".into())),
        };
        if result.is_err() {
            self.dirty.store(true, Ordering::Release);
            let mut state = self.state.lock().await;
            if let Some(mut connection) = state.connection.take() {
                connection.close(&self.config, auth, &state.protocol).await;
            }
            state.catalogue = None;
            state.handshake = None;
        }
        result
    }
    async fn invoke(
        &self,
        generation: &str,
        method: &str,
        params: Value,
        auth: &Headers,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        self.redactor.headers(auth);
        let operation = async {
            let mut state = tokio::select! {_=cancel.cancelled()=>return Err(Box::new(Failure {message:"MCP call cancelled before execution.".into(),delivery:Delivery::NotStarted,authorization:None}) as Box<dyn std::error::Error+Send+Sync>),state=self.state.lock()=>state};
            if self.dirty.load(Ordering::Acquire)
                || state
                    .catalogue
                    .as_ref()
                    .is_none_or(|catalogue| catalogue.generation != generation)
                || state
                    .connection
                    .as_mut()
                    .is_none_or(|connection| !connection.live())
            {
                return Err(Box::new(Failure {
                    message: "MCP connection or catalogue changed; this call was not replayed."
                        .into(),
                    delivery: Delivery::NotStarted,
                    authorization: None,
                })
                    as Box<dyn std::error::Error + Send + Sync>);
            }
            state.rpc(self, method, params, auth, cancel).await
        };
        let result = tokio::select! {
            _=self.shutdown.cancelled()=>Err(Box::new(Failure {message:"MCP runtime stopped during the call; delivery is uncertain.".into(),delivery:Delivery::Unknown,authorization:None}) as Box<dyn std::error::Error+Send+Sync>),
            result=operation=>result,
        };
        if let Some(challenge) = result
            .as_ref()
            .err()
            .and_then(|error| error.downcast_ref::<Failure>())
            .and_then(|failure| failure.authorization.as_ref())
        {
            *self
                .authorization
                .lock()
                .unwrap_or_else(|error| error.into_inner()) = Some(challenge.clone());
        }
        result.map_err(|error| self.redactor.error(error))
    }
    pub async fn close(&self) {
        let mut state = self.state.lock().await;
        if let Some(mut connection) = state.connection.take() {
            connection
                .close(&self.config, &Headers::new(), &state.protocol)
                .await;
        }
        self.dirty.store(true, Ordering::Release);
        state.catalogue = None;
        state.handshake = None;
        if let Ok(mut validators) = self.validators.lock() {
            validators.clear();
        }
    }
}

struct Registry {
    active: HashMap<String, Arc<McpClient>>,
    retired: Vec<Weak<McpClient>>,
}
pub struct McpRuntime {
    clients: Mutex<Registry>,
    shutdown: CancellationToken,
}
impl Default for McpRuntime {
    fn default() -> Self {
        Self::new()
    }
}
impl McpRuntime {
    pub fn new() -> Self {
        Self {
            clients: Mutex::new(Registry {
                active: HashMap::new(),
                retired: Vec::new(),
            }),
            shutdown: CancellationToken::new(),
        }
    }
    fn client(
        &self,
        config: &ServerConfig,
        project: &Path,
        notify: &Notify,
    ) -> Result<Arc<McpClient>> {
        let key = format!(
            "{}\0{}\0{}",
            project.display(),
            config.id(),
            config.fingerprint()?
        );
        let mut clients = self
            .clients
            .lock()
            .map_err(|_| "MCP client registry lock was poisoned.")?;
        let prefix = format!("{}\0{}\0", project.display(), config.id());
        let previous = clients
            .active
            .keys()
            .filter(|name| name.starts_with(&prefix) && **name != key)
            .cloned()
            .collect::<Vec<_>>();
        for name in previous {
            if let Some(client) = clients.active.remove(&name) {
                clients.retired.push(Arc::downgrade(&client));
            }
        }
        clients.retired.retain(|client| client.strong_count() > 0);
        Ok(clients
            .active
            .entry(key)
            .or_insert_with(|| {
                let id = config.id();
                let sink = notify.clone();
                let redactor = Redactor::for_server(config);
                let event_redactor = redactor.clone();
                let notification: Notify = Arc::new(move |mut event| {
                    event["server_id"] = json!(id);
                    sink(event_redactor.value(&event));
                });
                Arc::new(McpClient::new(
                    config.clone(),
                    project.to_owned(),
                    notification,
                    redactor,
                    self.shutdown.child_token(),
                ))
            })
            .clone())
    }
    /// Pass the complete configuration here, before mode filtering. Existing task leases remain valid.
    pub fn retain_configurations(&self, project: &Path, servers: &[ServerConfig]) -> Result<()> {
        let project = crate::config::canonical_project(project)?;
        let fingerprints = servers
            .iter()
            .filter(|server| server.enabled)
            .map(|server| Ok((server.id(), server.fingerprint()?)))
            .collect::<Result<HashMap<_, _>>>()?;
        let mut clients = self
            .clients
            .lock()
            .map_err(|_| "MCP client registry lock was poisoned.")?;
        let obsolete = clients
            .active
            .iter()
            .filter_map(|(key, client)| {
                (client.project == project
                    && fingerprints
                        .get(&client.config.id())
                        .is_none_or(|fingerprint| {
                            client.config.fingerprint().as_ref().ok() != Some(fingerprint)
                        }))
                .then_some(key.clone())
            })
            .collect::<Vec<_>>();
        for key in obsolete {
            if let Some(client) = clients.active.remove(&key) {
                clients.retired.push(Arc::downgrade(&client));
            }
        }
        clients.retired.retain(|client| client.strong_count() > 0);
        Ok(())
    }
    pub async fn discover(
        &self,
        servers: &[ServerConfig],
        project: &Path,
        auth: &AuthorizationHeaders,
        notify: Notify,
        cancel: &CancellationToken,
    ) -> Result<McpSnapshot> {
        let project = crate::config::canonical_project(project)?;
        let mut snapshot = McpSnapshot {
            tools: Vec::new(),
            servers: Vec::new(),
            bindings: HashMap::new(),
            resources: Vec::new(),
            templates: Vec::new(),
            prompts: Vec::new(),
            clients: BTreeMap::new(),
            authorization_challenges: BTreeMap::new(),
        };
        let mut used = HashSet::new();
        for server in servers
            .iter()
            .filter(|server| server.enabled && !server.trusted)
        {
            let mut public = Redactor::for_server(server).value(&server.public());
            public["status"] = json!("trust_required");
            public["error"] =
                json!("Trust this MCP configuration before starting or connecting it.");
            snapshot.servers.push(public);
        }
        let enabled = servers
            .iter()
            .filter(|server| server.enabled && server.trusted)
            .collect::<Vec<_>>();
        let mut discovered = Vec::new();
        for batch in enabled.chunks(4) {
            if cancel.is_cancelled() || self.shutdown.is_cancelled() {
                return Err("MCP discovery cancelled.".into());
            }
            let mut jobs = tokio::task::JoinSet::new();
            for (index, server) in batch.iter().enumerate() {
                let server = (*server).clone();
                let client = self.client(&server, &project, &notify)?;
                let authorization = auth.get(&server.id()).cloned();
                let cancel = cancel.clone();
                jobs.spawn(async move {
                    let result = if server.credential_ref.is_some() && authorization.is_none() {
                        Err(Box::new(Failure {
                            message: "MCP credential is not available; authorization is required."
                                .into(),
                            delivery: Delivery::NotStarted,
                            authorization: None,
                        })
                            as Box<dyn std::error::Error + Send + Sync>)
                    } else {
                        client
                            .discover(&authorization.unwrap_or_default(), &cancel)
                            .await
                    };
                    (index, server, client, result)
                });
            }
            let mut results = Vec::new();
            while let Some(result) = jobs.join_next().await {
                results.push(result?);
            }
            results.sort_by_key(|(index, ..)| *index);
            discovered.extend(results);
        }
        if cancel.is_cancelled() || self.shutdown.is_cancelled() {
            return Err("MCP discovery cancelled.".into());
        }
        for (_, server, client, result) in discovered {
            let mut public = client.redactor.value(&server.public());
            match result {
                Ok(catalogue) => {
                    public["status"] = json!(if catalogue.errors.is_empty() {
                        "ready"
                    } else {
                        "partial"
                    });
                    public["generation"] = json!(catalogue.generation);
                    public["protocol_version"] = json!(catalogue.protocol);
                    public["server_info"] = client.redactor.value(&catalogue.server_info);
                    public["capabilities"] = client.redactor.value(&catalogue.capabilities);
                    public["errors"] = json!(catalogue.errors);
                    public["discovered_tools_count"] = json!(catalogue.tools.len());
                    public["tools_count"] = json!(0);
                    for item in &catalogue.tools {
                        let Some(tool_name) = item["name"].as_str().filter(|name| !name.is_empty())
                        else {
                            continue;
                        };
                        if !server.tool_enabled(tool_name) || !model_visible(item) {
                            continue;
                        }
                        let name = tool_name_for(&server, tool_name, &mut used);
                        let Some(schema) =
                            item["inputSchema"].as_object().cloned().map(Value::Object)
                        else {
                            public["errors"]
                                .as_array_mut()
                                .unwrap()
                                .push(json!(format!("Tool {tool_name} has no valid inputSchema.")));
                            public["status"] = json!("partial");
                            continue;
                        };
                        let tool = McpTool {
                            name: name.clone(),
                            server_id: server.id(),
                            tool_name: tool_name.into(),
                            generation: catalogue.generation.clone(),
                            definition: client.redactor.value(&json!({"type":"function","function":{"name":name,"description":item["description"].as_str().unwrap_or("MCP tool"),"parameters":schema}})),
                            metadata: client.redactor.value(item),
                        };
                        let validator = match client.input_validator(&schema) {
                            Ok(validator) => validator,
                            Err(error) => {
                                public["errors"].as_array_mut().unwrap().push(json!(
                                    client.redactor.text(&format!("Tool {tool_name}: {error}"))
                                ));
                                public["status"] = json!("partial");
                                continue;
                            }
                        };
                        snapshot.bindings.insert(
                            name,
                            McpCallLease {
                                client: client.clone(),
                                tool: tool.clone(),
                                validator,
                            },
                        );
                        snapshot.tools.push(tool);
                        public["tools_count"] =
                            json!(public["tools_count"].as_u64().unwrap_or(0) + 1);
                    }
                    append_resources(
                        &mut snapshot.resources,
                        &catalogue.resources,
                        &server,
                        &catalogue.generation,
                        &client.redactor,
                    );
                    append_resources(
                        &mut snapshot.templates,
                        &catalogue.templates,
                        &server,
                        &catalogue.generation,
                        &client.redactor,
                    );
                    append_resources(
                        &mut snapshot.prompts,
                        &catalogue.prompts,
                        &server,
                        &catalogue.generation,
                        &client.redactor,
                    );
                    snapshot
                        .clients
                        .insert(server.id(), (client, catalogue.generation));
                }
                Err(error) => {
                    let failure = error.downcast_ref::<Failure>();
                    public["status"] = json!(if failure
                        .is_some_and(|failure| failure.authorization.is_some())
                        || server.credential_ref.is_some()
                    {
                        "authorization_required"
                    } else {
                        "error"
                    });
                    public["error"] = json!(client.redactor.text(&error.to_string()));
                    if let Some(challenge) =
                        failure.and_then(|failure| failure.authorization.as_ref())
                    {
                        public["has_authorization_challenge"] = json!(true);
                        snapshot
                            .authorization_challenges
                            .insert(server.id(), challenge.clone());
                    }
                }
            }
            snapshot.servers.push(public);
        }
        snapshot
            .servers
            .sort_by(|left, right| left["id"].as_str().cmp(&right["id"].as_str()));
        Ok(snapshot)
    }
    pub fn invalidate(&self, project: &Path, server: Option<&str>) -> Result<()> {
        let project = crate::config::canonical_project(project)?;
        let clients = self
            .clients
            .lock()
            .map_err(|_| "MCP client registry lock was poisoned.")?;
        for client in clients.active.values() {
            if client.project == project && server.is_none_or(|server| client.config.id() == server)
            {
                client.dirty.store(true, Ordering::Release);
            }
        }
        Ok(())
    }
    /// Private transport challenge, tied to the active project/server configuration.
    pub fn authorization_challenge(
        &self,
        project: &Path,
        server_id: &str,
    ) -> Result<Option<String>> {
        let project = crate::config::canonical_project(project)?;
        let clients = self
            .clients
            .lock()
            .map_err(|_| "MCP client registry lock was poisoned.")?;
        Ok(clients
            .active
            .values()
            .find(|client| client.project == project && client.config.id() == server_id)
            .and_then(|client| {
                client
                    .authorization
                    .lock()
                    .unwrap_or_else(|error| error.into_inner())
                    .clone()
            }))
    }
    pub fn cancel_all(&self) {
        self.shutdown.cancel();
    }
    pub async fn close(&self) {
        self.shutdown.cancel();
        let clients = self
            .clients
            .lock()
            .map(|mut clients| {
                let mut current = clients
                    .active
                    .drain()
                    .map(|(_, client)| client)
                    .collect::<Vec<_>>();
                current.extend(
                    clients
                        .retired
                        .drain(..)
                        .filter_map(|client| client.upgrade()),
                );
                current
            })
            .unwrap_or_default();
        for client in clients {
            client.close().await;
        }
    }
}

pub struct McpSnapshot {
    pub tools: Vec<McpTool>,
    pub servers: Vec<Value>,
    pub resources: Vec<Value>,
    pub templates: Vec<Value>,
    pub prompts: Vec<Value>,
    bindings: HashMap<String, McpCallLease>,
    clients: BTreeMap<String, (Arc<McpClient>, String)>,
    authorization_challenges: BTreeMap<String, String>,
}
impl McpSnapshot {
    pub fn public(&self) -> Value {
        json!({"servers":self.servers,"tools":self.tools.iter().map(|tool|json!({"name":tool.name,"server_id":tool.server_id,"tool_name":tool.tool_name,"generation":tool.generation,"definition":tool.definition,"metadata":tool.metadata})).collect::<Vec<_>>(),"resources":self.resources,"resource_templates":self.templates,"prompts":self.prompts,"client_capabilities":{"roots":{"listChanged":false}}})
    }
    /// Resolving a lease does not execute it. The host must apply its ordinary approval gate.
    pub fn prepare_tool(&self, name: &str) -> Result<McpCallLease> {
        self.bindings
            .get(name)
            .cloned()
            .ok_or_else(|| "MCP tool is absent from this task's frozen catalogue.".into())
    }
    pub async fn read_resource(
        &self,
        server: &str,
        uri: &str,
        auth: &Headers,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        let (client, generation) = self
            .clients
            .get(server)
            .ok_or("MCP server has not passed discovery.")?;
        if uri.is_empty() {
            return Err("MCP resource URI is required.".into());
        }
        client
            .invoke(
                generation,
                "resources/read",
                json!({"uri":uri}),
                auth,
                cancel,
            )
            .await
            .map(|value| client.redactor.value(&value))
    }
    pub async fn get_prompt(
        &self,
        server: &str,
        name: &str,
        arguments: Value,
        auth: &Headers,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        let (client, generation) = self
            .clients
            .get(server)
            .ok_or("MCP server has not passed discovery.")?;
        if !self
            .prompts
            .iter()
            .any(|prompt| prompt["server_id"] == server && prompt["name"] == name)
        {
            return Err("MCP prompt was not discovered.".into());
        }
        if !arguments.is_object() {
            return Err("MCP prompt arguments must be an object.".into());
        }
        client
            .invoke(
                generation,
                "prompts/get",
                json!({"name":name,"arguments":arguments}),
                auth,
                cancel,
            )
            .await
            .map(|value| client.redactor.value(&value))
    }
    pub fn server_configuration(&self, id: &str) -> Option<&ServerConfig> {
        self.clients
            .get(id)
            .map(|(client, _)| client.configuration())
    }
    /// Authentication headers are private to the kernel and must not be sent to model or UI logs.
    pub fn authorization_challenge(&self, id: &str) -> Option<&str> {
        self.authorization_challenges.get(id).map(String::as_str)
    }
}

#[derive(Clone)]
pub struct McpCallLease {
    client: Arc<McpClient>,
    pub tool: McpTool,
    validator: Arc<jsonschema::Validator>,
}
impl McpCallLease {
    pub fn configuration(&self) -> &ServerConfig {
        self.client.configuration()
    }
    /// This is a transport operation, not a permission decision. Call only after approval.
    pub async fn call_approved(
        &self,
        arguments: Value,
        auth: &Headers,
        cancel: &CancellationToken,
    ) -> ToolResult {
        if !arguments.is_object() {
            let mut result = ToolResult::fail("MCP tool arguments must be an object.");
            result.status = "not_started".into();
            result.data = json!({"delivery":"not_started"});
            return result;
        }
        if let Err(error) = self.validator.validate(&arguments) {
            let mut result = ToolResult::fail(format!(
                "MCP arguments do not satisfy inputSchema at {}.",
                self.client
                    .redactor
                    .text(&error.instance_path().to_string())
            ));
            result.status = "not_started".into();
            result.data = json!({"delivery":"not_started","server_id":self.tool.server_id,"generation":self.tool.generation});
            return result;
        }
        match self
            .client
            .invoke(
                &self.tool.generation,
                "tools/call",
                json!({"name":self.tool.tool_name,"arguments":arguments}),
                auth,
                cancel,
            )
            .await
        {
            Ok(result) => {
                let public = self.client.redactor.value(&result);
                let output = public["content"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|block| block["text"].as_str())
                    .collect::<Vec<_>>()
                    .join("\n");
                let mut outcome = if public["isError"] == true {
                    let mut outcome = ToolResult::fail(&output);
                    outcome.output = output;
                    outcome
                } else {
                    ToolResult::ok(output, Value::Null)
                };
                outcome.data = json!({"mcp":public,"server_id":self.tool.server_id,"generation":self.tool.generation,"delivery":"completed"});
                outcome
            }
            Err(error) => {
                let mut outcome = ToolResult::fail(error.to_string());
                let delivery = error
                    .downcast_ref::<Failure>()
                    .map_or(Delivery::Unknown, |failure| failure.delivery);
                if delivery != Delivery::Completed {
                    outcome.status = delivery.name().into();
                }
                outcome.error = Some(self.client.redactor.text(&error.to_string()));
                outcome.data = json!({"server_id":self.tool.server_id,"generation":self.tool.generation,"delivery":delivery.name()});
                if error
                    .downcast_ref::<Failure>()
                    .is_some_and(|failure| failure.authorization.is_some())
                {
                    outcome.data["authorization_required"] = json!(true);
                }
                outcome
            }
        }
    }
}

fn model_visible(tool: &Value) -> bool {
    tool["_meta"]["ui"]["visibility"]
        .as_array()
        .is_none_or(|visibility| visibility.iter().any(|item| item == "model"))
}
fn compile_input_schema(schema: &Value) -> Result<jsonschema::Validator> {
    fn local_references(value: &Value) -> bool {
        match value {
            Value::Object(entries) => entries.iter().all(|(name, value)| {
                if ["$ref", "$dynamicRef", "$recursiveRef"].contains(&name.as_str()) {
                    value
                        .as_str()
                        .is_some_and(|reference| reference.is_empty() || reference.starts_with('#'))
                } else {
                    local_references(value)
                }
            }),
            Value::Array(values) => values.iter().all(local_references),
            _ => true,
        }
    }
    if !local_references(schema) {
        return Err("inputSchema may only reference this schema document; external file/HTTP references are disabled.".into());
    }
    jsonschema::options()
        .offline()
        .build(schema)
        .map_err(|_| "inputSchema could not be compiled and validated offline.".into())
}
fn append_resources(
    target: &mut Vec<Value>,
    items: &[Value],
    server: &ServerConfig,
    generation: &str,
    redactor: &Redactor,
) {
    for item in items {
        let mut item = redactor.value(item);
        item["server_id"] = json!(server.id());
        item["generation"] = json!(generation);
        target.push(item);
    }
}
fn identifier(text: &str) -> String {
    let mut value = String::new();
    for ch in text.to_ascii_lowercase().chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' {
            value.push(ch);
        } else if !value.ends_with('_') {
            value.push('_');
        }
    }
    let value = value.trim_matches('_');
    if value.is_empty() {
        "item".into()
    } else {
        value.into()
    }
}
fn tool_name_for(server: &ServerConfig, tool: &str, used: &mut HashSet<String>) -> String {
    let identity = format!("{}\0{tool}", server.id());
    let digest = hash(identity.as_bytes());
    let source = if server.origin == "manual" {
        server.name.clone()
    } else {
        format!("{}_{}", server.origin, server.name)
    };
    let base = format!("mcp_{}_{}", identifier(&source), identifier(tool));
    if base.len() <= 64 && used.insert(base.clone()) {
        return base;
    }
    let name = format!(
        "{}_{}",
        base.chars()
            .take(53)
            .collect::<String>()
            .trim_end_matches('_'),
        &digest[..10]
    );
    used.insert(name.clone());
    name
}

#[cfg(test)]
mod schema_tests {
    use super::*;
    #[test]
    fn validates_required_types_local_refs_and_rejects_external_refs() {
        let schema = json!({"type":"object","required":["amount"],"$defs":{"amount":{"type":"integer"}},
            "properties":{"amount":{"$ref":"#/$defs/amount"}}});
        let validator = compile_input_schema(&schema).unwrap();
        assert!(validator.is_valid(&json!({"amount":4})));
        assert!(!validator.is_valid(&json!({})));
        assert!(!validator.is_valid(&json!({"amount":"4"})));
        for reference in [
            "https://example.test/schema",
            "file:///etc/passwd",
            "../external.json",
        ] {
            assert!(
                compile_input_schema(
                    &json!({"type":"object","properties":{"value":{"$ref":reference}}})
                )
                .is_err()
            );
        }
        assert!(compile_input_schema(&json!({"type":"unknown"})).is_err());
    }
}
