use super::{EventSink, KernelHost, lock};
use crate::{
    Result,
    connectors::ConnectorManager,
    mcp,
    plugins::{PluginLease, PluginStore},
};
use reverie_protocol::{ActivatePluginRequest, PluginControlRequest, PreparePluginRequest, Reply};
use serde_json::{Map, Value, json};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    sync::Arc,
};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

pub struct PendingExtension {
    pub operation_id: String,
    action: String,
    payload: Value,
    app: PathBuf,
    root: PathBuf,
    configuration: Value,
    settings: Value,
    cancel: CancellationToken,
}

pub(super) struct McpAuthorization {
    pub servers: Vec<mcp::ServerConfig>,
    pub headers: mcp::AuthorizationHeaders,
    pub diagnostics: Vec<Value>,
}

fn string<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("{key} is required.").into())
}
fn plugin_id(value: &Value) -> Result<&str> {
    value["pluginId"]
        .as_str()
        .or(value["plugin_id"].as_str())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "pluginId is required.".into())
}
fn public_servers(servers: &[mcp::ServerConfig]) -> Result<Vec<Value>> {
    servers
        .iter()
        .map(|server| {
            let mut result = server.public();
            result["fingerprint"] = json!(server.fingerprint()?);
            let record: reverie_protocol::McpServerRecord = serde_json::from_value(result)?;
            Ok(serde_json::to_value(record)?)
        })
        .collect()
}
fn substitute(value: &Value, root: &Path) -> Value {
    match value {
        Value::String(value) => json!(
            value
                .replace("${CLAUDE_PLUGIN_ROOT}", &root.to_string_lossy())
                .replace("${CODEX_PLUGIN_ROOT}", &root.to_string_lossy())
                .replace("${REVERIE_PLUGIN_ROOT}", &root.to_string_lossy())
        ),
        Value::Array(items) => json!(
            items
                .iter()
                .map(|value| substitute(value, root))
                .collect::<Vec<_>>()
        ),
        Value::Object(items) => Value::Object(
            items
                .iter()
                .map(|(key, value)| (key.clone(), substitute(value, root)))
                .collect(),
        ),
        _ => value.clone(),
    }
}
pub(super) fn plugin_mcp(leases: &[Arc<PluginLease>]) -> Result<BTreeMap<String, Value>> {
    let mut plugins = BTreeMap::new();
    for lease in leases {
        let mut servers = Map::new();
        for component in &lease.metadata().components {
            if component.kind != "mcp" {
                continue;
            }
            let mut configuration = substitute(&component.configuration, &lease.root);
            configuration["trust"] = json!(true);
            if configuration["command"].as_str().is_some_and(|command| {
                Path::new(command).is_relative() && command.contains(['/', '\\'])
            }) {
                let path = crate::plugins::package::checked_path(
                    &lease.root,
                    configuration["command"].as_str().unwrap(),
                )?;
                configuration["command"] = json!(path);
            }
            servers.insert(component.name.clone(), configuration);
        }
        if !servers.is_empty() {
            plugins.insert(format!("plugin/{}", lease.id), Value::Object(servers));
        }
    }
    Ok(plugins)
}
pub(super) fn mcp_configuration(
    app: &Path,
    configuration: &Value,
    leases: &[Arc<PluginLease>],
) -> Result<mcp::config::ConfigRead> {
    Ok(mcp::McpConfigStore::new(app)
        .read_all(&plugin_mcp(leases)?)?
        .effective(
            configuration["mode"].as_str().unwrap_or("reverie"),
            configuration.get("mcp"),
        ))
}

impl KernelHost {
    pub fn is_extension_async_action(action: &str) -> bool {
        matches!(
            action,
            "preparePlugin"
                | "updatePlugin"
                | "activatePlugin"
                | "setPluginEnabled"
                | "setPluginTrust"
                | "setPluginHooks"
                | "setPluginAutoUpdate"
                | "rollbackPlugin"
                | "removePlugin"
                | "listMcp"
                | "refreshMcp"
                | "configureMcp"
                | "removeMcp"
                | "setMcpTrust"
                | "setMcpEnabled"
                | "readMcpResource"
                | "getMcpPrompt"
                | "listConnectors"
                | "discoverConnector"
                | "authorizeConnector"
                | "completeConnectorAuthorization"
                | "revokeConnector"
                | "clearConnectorCredentials"
                | "setConnectorApiKey"
                | "listTools"
        )
    }
    pub fn begin_plugin_operation(
        &self,
        action: &str,
        payload: &Value,
    ) -> Result<PendingExtension> {
        if !Self::is_extension_async_action(action) {
            return Err("Unsupported background extension action.".into());
        }
        match action {
            "preparePlugin" => {
                serde_json::from_value::<PreparePluginRequest>(payload.clone())?;
            }
            "activatePlugin" => {
                serde_json::from_value::<ActivatePluginRequest>(payload.clone())?;
            }
            "setPluginEnabled"
            | "setPluginTrust"
            | "setPluginHooks"
            | "setPluginAutoUpdate"
            | "rollbackPlugin"
            | "removePlugin" => {
                serde_json::from_value::<PluginControlRequest>(payload.clone())?;
            }
            "configureMcp" => {
                serde_json::from_value::<reverie_protocol::McpConfigurationRequest>(
                    payload.clone(),
                )?;
            }
            "removeMcp" | "setMcpTrust" | "setMcpEnabled" => {
                serde_json::from_value::<reverie_protocol::McpControlRequest>(payload.clone())?;
            }
            "discoverConnector" | "revokeConnector" => {
                serde_json::from_value::<reverie_protocol::ConnectorRequest>(payload.clone())?;
            }
            "authorizeConnector" => {
                serde_json::from_value::<reverie_protocol::AuthorizeConnectorRequest>(
                    payload.clone(),
                )?;
            }
            "completeConnectorAuthorization" => {
                serde_json::from_value::<reverie_protocol::CompleteConnectorAuthorizationRequest>(
                    payload.clone(),
                )?;
            }
            "setConnectorApiKey" => {
                serde_json::from_value::<reverie_protocol::ConnectorApiKeyRequest>(
                    payload.clone(),
                )?;
            }
            "clearConnectorCredentials" => {
                serde_json::from_value::<reverie_protocol::ClearConnectorCredentialsRequest>(
                    payload.clone(),
                )?;
            }
            "readMcpResource" => {
                serde_json::from_value::<reverie_protocol::McpResourceRequest>(payload.clone())?;
            }
            "getMcpPrompt" => {
                let request =
                    serde_json::from_value::<reverie_protocol::McpPromptRequest>(payload.clone())?;
                if request
                    .arguments
                    .as_ref()
                    .is_some_and(|arguments| !arguments.is_object())
                {
                    return Err("MCP prompt arguments must be an object.".into());
                }
            }
            _ => {}
        }
        let operation_id = payload["operation_id"]
            .as_str()
            .or(payload["operationId"].as_str())
            .map(str::to_owned)
            .unwrap_or_else(|| format!("extension-{}", Uuid::new_v4().simple()));
        if operation_id.is_empty()
            || operation_id.len() > 128
            || operation_id.chars().any(char::is_control)
        {
            return Err("Invalid extension operation identity.".into());
        }
        let (app, root, configuration, settings) = {
            let mut kernel = lock(&self.kernel)?;
            kernel.configure_assistant(payload)?;
            if let Some(root) = payload["projectRoot"].as_str() {
                kernel.configure_project(root)?;
            }
            let configuration = kernel.effective_config(payload["sessionId"].as_str())?;
            let settings =
                crate::models::settings(&configuration, &kernel.config.path, kernel.workspace_mode);
            (
                kernel.app_root.clone(),
                kernel.project_root.clone(),
                configuration,
                settings,
            )
        };
        let cancel = self.context_cancel.child_token();
        {
            let mut jobs = lock(&self.plugin_jobs)?;
            if jobs.contains_key(&operation_id) {
                return Err("This extension operation is already active.".into());
            }
            jobs.insert(operation_id.clone(), cancel.clone());
        }
        Ok(PendingExtension {
            operation_id,
            action: action.into(),
            payload: payload.clone(),
            app,
            root,
            configuration,
            settings,
            cancel,
        })
    }
    pub async fn complete_plugin_operation(
        &self,
        id: Value,
        pending: PendingExtension,
        sink: EventSink,
    ) -> Reply {
        sink(
            json!({"type":"extension.progress","operation_id":pending.operation_id,"project_root":pending.root,"phase":"started"}),
        );
        let result = self.extension(&pending, sink.clone()).await;
        if let Ok(mut jobs) = self.plugin_jobs.lock() {
            jobs.remove(&pending.operation_id);
        }
        sink(
            json!({"type":"extension.progress","operation_id":pending.operation_id,"project_root":pending.root,"phase":if result.is_ok(){"completed"}else if pending.cancel.is_cancelled(){"cancelled"}else{"failed"}}),
        );
        match result {
            Ok((kind, mut fields)) => {
                fields["operation_id"] = json!(pending.operation_id);
                Reply::new(
                    Some(id),
                    kind,
                    fields.as_object().cloned().unwrap_or_default(),
                )
            }
            Err(error) => Reply::error(id, error),
        }
    }
    pub(super) fn stop_plugin_operation(&self, payload: &Value) -> Result<(&'static str, Value)> {
        let id = payload["operation_id"]
            .as_str()
            .or(payload["operationId"].as_str())
            .ok_or("operation_id is required.")?;
        let jobs = lock(&self.plugin_jobs)?;
        if let Some(job) = jobs.get(id) {
            job.cancel();
        }
        Ok((
            "plugin.control",
            json!({"operation_id":id,"cancelled":jobs.contains_key(id)}),
        ))
    }
    pub(super) fn connector_manager(&self) -> Result<Arc<ConnectorManager>> {
        let app = lock(&self.kernel)?.app_root.clone();
        let mut manager = lock(&self.connectors)?;
        if let Some(manager) = manager.as_ref() {
            return Ok(manager.clone());
        }
        let created = Arc::new(ConnectorManager::new(&app)?);
        *manager = Some(created.clone());
        Ok(created)
    }
    pub async fn close_extensions(&self) {
        self.mcp.close().await;
        let connectors = self
            .connectors
            .lock()
            .ok()
            .and_then(|connectors| connectors.clone());
        if let Some(connectors) = connectors {
            connectors.close().await;
        }
    }
    pub(super) fn mcp_notify(root: &Path, sink: EventSink) -> mcp::Notify {
        let root = root.to_owned();
        Arc::new(move |mut event| {
            event["type"] = json!("mcp.notification");
            event["automatic"] = json!(true);
            event["project_root"] = json!(root);
            sink(event);
        })
    }
    pub(super) async fn mcp_authorization(
        &self,
        servers: &[mcp::ServerConfig],
        cancel: &CancellationToken,
    ) -> Result<McpAuthorization> {
        let manager = self.connector_manager()?;
        let mut headers = BTreeMap::new();
        let mut available = Vec::new();
        let mut diagnostics = Vec::new();
        for server in servers {
            if server.enabled && server.trusted {
                match manager.headers(server, cancel).await {
                    Ok(authorization) => {
                        if !authorization.is_empty() {
                            headers.insert(server.id(), authorization);
                        }
                    }
                    Err(error) if cancel.is_cancelled() || self.context_cancel.is_cancelled() => {
                        return Err(error);
                    }
                    Err(_) => {
                        diagnostics.push(json!({"scope":"authorization","server_id":server.id(),
                            "name":server.name,"status":"authorization_unavailable",
                            "error":"Connector credentials are unavailable for this target; inspect or reauthorize it before connecting.",
                            "connector":manager.status(server).unwrap_or_else(|_|json!({"server_id":server.id(),"status":"configuration_unreadable"}))}));
                        continue;
                    }
                }
            }
            available.push(server.clone());
        }
        Ok(McpAuthorization {
            servers: available,
            headers,
            diagnostics,
        })
    }
    async fn extension(
        &self,
        pending: &PendingExtension,
        sink: EventSink,
    ) -> Result<(&'static str, Value)> {
        if pending.cancel.is_cancelled() {
            return Err("Extension operation cancelled before execution.".into());
        }
        let store = PluginStore::new(&pending.app)?;
        let action = pending.action.as_str();
        let payload = &pending.payload;
        if matches!(action, "preparePlugin" | "updatePlugin") {
            let mut result = if action == "preparePlugin" {
                store
                    .prepare(
                        &pending.app,
                        serde_json::from_value(payload.clone())?,
                        &pending.cancel,
                    )
                    .await?
            } else {
                store
                    .prepare_update(
                        &pending.app,
                        plugin_id(payload)?,
                        payload["expected_revision"].as_u64(),
                        &pending.cancel,
                    )
                    .await?
            };
            result["plugins"] = serde_json::to_value(store.state(Some(&pending.root))?)?;
            return Ok(("plugin.prepared", result));
        }
        if matches!(
            action,
            "activatePlugin"
                | "setPluginEnabled"
                | "setPluginTrust"
                | "setPluginHooks"
                | "setPluginAutoUpdate"
                | "rollbackPlugin"
                | "removePlugin"
        ) {
            let action = action.to_owned();
            let payload = payload.clone();
            let target = store.clone();
            let mut result = tokio::task::spawn_blocking(move || {
                if action == "activatePlugin" {
                    target.activate(serde_json::from_value(payload)?)
                } else {
                    target.control(&action, serde_json::from_value(payload)?)
                }
            })
            .await??;
            result["plugins"] = serde_json::to_value(store.state(Some(&pending.root))?)?;
            result["settings"] = pending.settings.clone();
            lock(&self.kernel)?.skill_catalogs.clear();
            return Ok(("plugin.updated", result));
        }
        let project = pending.root.clone();
        let target = store.clone();
        let cancel = pending.cancel.clone();
        let leases =
            tokio::task::spawn_blocking(move || target.leases(&project, &|| cancel.is_cancelled()))
                .await??;
        let configuration = mcp::McpConfigStore::new(&pending.app);
        let plugins = plugin_mcp(&leases)?;
        let mut configured = configuration.read_all(&plugins)?;
        if matches!(
            action,
            "configureMcp" | "removeMcp" | "setMcpTrust" | "setMcpEnabled"
        ) {
            let revision = payload["expected_revision"].as_u64();
            let name = string(payload, "name")?;
            let result = match action {
                "configureMcp" => {
                    let mut raw = payload["configuration"].clone();
                    if !raw.is_object() {
                        return Err("MCP configuration must be an object.".into());
                    }
                    if raw["trust"] == true {
                        return Err("Save MCP configuration without trust, then approve its inspected execution identity separately.".into());
                    }
                    raw["trust"] = json!(false);
                    mcp::ServerConfig::parse(name, "manual", &raw)?;
                    configuration.upsert(name, raw, revision)?
                }
                "removeMcp" => {
                    if payload["confirmed"] != true {
                        return Err("Confirm removal of this MCP configuration.".into());
                    }
                    configuration.remove(name, revision)?
                }
                _ => configuration.update(revision, |document| {
                    let raw = document["mcpServers"]
                        .get_mut(name)
                        .ok_or("Manual MCP configuration was not found.")?;
                    let server = mcp::ServerConfig::parse(name, "manual", raw)?;
                    if action == "setMcpTrust"
                        && payload["trusted"] == true
                        && payload["fingerprint"].as_str() != Some(&server.fingerprint()?)
                    {
                        return Err(
                            "MCP trust must bind the inspected configuration fingerprint.".into(),
                        );
                    }
                    let (key, input) = if action == "setMcpTrust" {
                        ("trust", "trusted")
                    } else {
                        ("enabled", "enabled")
                    };
                    raw[key] = json!(
                        payload[input]
                            .as_bool()
                            .ok_or_else(|| format!("{input} is required."))?
                    );
                    Ok(())
                })?,
            };
            configured = configuration.read_all(&plugins)?;
            self.mcp
                .retain_configurations(&pending.root, &configured.servers)?;
            return Ok((
                "mcp.updated",
                json!({"mcp":configuration.public(&result),"servers":public_servers(&configured.servers)?,
                    "effective_server_ids":configured.clone().effective(pending.configuration["mode"].as_str().unwrap_or("reverie"), pending.configuration.get("mcp")).servers.iter().map(mcp::ServerConfig::id).collect::<Vec<_>>()}),
            ));
        }
        if action == "listMcp" {
            return Ok((
                "mcp",
                json!({"mcp":configuration.public_read(&configured),"servers":public_servers(&configured.servers)?,
                    "effective_server_ids":configured.clone().effective(pending.configuration["mode"].as_str().unwrap_or("reverie"), pending.configuration.get("mcp")).servers.iter().map(mcp::ServerConfig::id).collect::<Vec<_>>()}),
            ));
        }
        if action == "listConnectors" {
            return Ok((
                "connectors",
                json!({"connectors":self.connector_manager()?.list_configured(&configured.servers)?,"mcp_diagnostics":configured.diagnostics}),
            ));
        }
        if action == "clearConnectorCredentials" {
            let server_id = string(payload, "server_id")?;
            let manager = self.connector_manager()?;
            let result = manager
                .clear_local_credentials(server_id, payload["confirmed"] == true, &pending.cancel)
                .await?;
            self.mcp.invalidate(&pending.root, Some(server_id))?;
            return Ok((
                "connector.updated",
                json!({"connector":result,"connectors":manager.list_configured(&configured.servers)?}),
            ));
        }
        if action.ends_with("Connector")
            || matches!(
                action,
                "setConnectorApiKey" | "completeConnectorAuthorization"
            )
        {
            let server_id = string(payload, "server_id")?;
            let server = configured
                .servers
                .iter()
                .find(|server| server.id() == server_id)
                .ok_or("MCP connector configuration is not available in this workspace.")?;
            let manager = self.connector_manager()?;
            let result = match action {
                "discoverConnector" => {
                    let challenge = self.mcp.authorization_challenge(&pending.root, server_id)?;
                    manager
                        .discover_with_challenge(server, challenge.as_deref(), &pending.cancel)
                        .await?
                        .public()
                }
                "authorizeConnector" => {
                    manager
                        .begin_authorization(
                            server,
                            string(payload, "discovery_id")?,
                            serde_json::from_value(payload["choice"].clone())?,
                            Self::mcp_notify(&pending.root, sink),
                            &pending.cancel,
                        )
                        .await?
                }
                "completeConnectorAuthorization" => {
                    manager
                        .complete_authorization(
                            server,
                            string(payload, "authorization_id")?,
                            &pending.cancel,
                        )
                        .await?
                }
                "revokeConnector" => manager.revoke(server, &pending.cancel).await?,
                "setConnectorApiKey" => {
                    if payload["expected_fingerprint"].as_str() != Some(&server.fingerprint()?) {
                        return Err("MCP target or configuration changed; inspect and confirm it again before storing a credential.".into());
                    }
                    manager
                        .set_api_key(
                            server,
                            string(payload, "header")?,
                            string(payload, "secret")?,
                            payload["confirmed"] == true,
                            &pending.cancel,
                        )
                        .await?
                }
                _ => return Err("Unsupported Connector operation.".into()),
            };
            self.mcp.invalidate(&pending.root, Some(server_id))?;
            return Ok((
                "connector.updated",
                json!({"connector":result,"connectors":manager.list_configured(&configured.servers)?}),
            ));
        }
        self.mcp
            .retain_configurations(&pending.root, &configured.servers)?;
        let effective = configured.effective(
            pending.configuration["mode"].as_str().unwrap_or("reverie"),
            pending.configuration.get("mcp"),
        );
        let servers = effective.servers;
        let auth = self.mcp_authorization(&servers, &pending.cancel).await?;
        if action == "refreshMcp" {
            self.mcp
                .invalidate(&pending.root, payload["server_id"].as_str())?;
        }
        let snapshot = self
            .mcp
            .discover(
                &auth.servers,
                &pending.root,
                &auth.headers,
                Self::mcp_notify(&pending.root, sink),
                &pending.cancel,
            )
            .await?;
        let result = match action {
            "listTools" => {
                let mode = crate::modes::normalize(
                    payload["mode"]
                        .as_str()
                        .unwrap_or(pending.configuration["mode"].as_str().unwrap_or("reverie")),
                )?;
                let mut tools = super::tool_catalog_for(mode)
                    .iter()
                    .map(|tool| {
                        super::catalog::describe(
                            tool,
                            "built-in",
                            if tool["function"]["name"] == "userInput" {
                                "interaction"
                            } else if crate::modes::definitions(mode)
                                .iter()
                                .any(|entry| entry["function"]["name"] == tool["function"]["name"])
                            {
                                "mode"
                            } else {
                                "files"
                            },
                            mode,
                        )
                    })
                    .collect::<Vec<_>>();
                tools.extend(
                    super::computer::definitions(mode, &pending.configuration)
                        .iter()
                        .map(|tool| super::catalog::describe(tool, "built-in", "desktop", mode)),
                );
                tools.extend(snapshot.tools.iter().map(|tool| {
                    super::catalog::describe(&tool.definition, "mcp", "extensions", mode)
                }));
                return Ok((
                    "tools",
                    json!({"mode":mode,"tools":tools,"mcp":snapshot.public(),"mcp_diagnostics":effective.diagnostics,
                            "authorization_diagnostics":auth.diagnostics}),
                ));
            }
            "refreshMcp" => snapshot.public(),
            "readMcpResource" => {
                let server = string(payload, "server_id")?;
                snapshot
                    .read_resource(
                        server,
                        string(payload, "uri")?,
                        &auth.headers.get(server).cloned().unwrap_or_default(),
                        &pending.cancel,
                    )
                    .await?
            }
            "getMcpPrompt" => {
                let server = string(payload, "server_id")?;
                snapshot
                    .get_prompt(
                        server,
                        string(payload, "name")?,
                        payload["arguments"]
                            .as_object()
                            .cloned()
                            .map(Value::Object)
                            .unwrap_or_else(|| json!({})),
                        &auth.headers.get(server).cloned().unwrap_or_default(),
                        &pending.cancel,
                    )
                    .await?
            }
            _ => return Err("Unsupported extension operation.".into()),
        };
        Ok((
            "mcp.result",
            json!({"mcp":result,"mcp_diagnostics":effective.diagnostics,"authorization_diagnostics":auth.diagnostics}),
        ))
    }
}
