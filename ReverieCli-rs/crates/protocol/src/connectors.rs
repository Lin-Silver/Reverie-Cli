use serde::{Deserialize, Serialize};
use serde_json::Value;
use ts_rs::TS;

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct McpServerRecord {
    pub id: String,
    pub name: String,
    pub origin: String,
    #[serde(rename = "type")]
    pub transport: String,
    pub enabled: bool,
    pub trust: bool,
    pub command: String,
    pub args_count: usize,
    pub url: String,
    pub cwd: String,
    #[ts(type = "number")]
    pub timeout: u64,
    pub env_keys: Vec<String>,
    pub header_keys: Vec<String>,
    pub credential_configured: bool,
    #[serde(rename = "includeTools")]
    pub include_tools: Vec<String>,
    #[serde(rename = "excludeTools")]
    pub exclude_tools: Vec<String>,
    #[serde(rename = "includeModes")]
    pub include_modes: Vec<String>,
    #[serde(rename = "excludeModes")]
    pub exclude_modes: Vec<String>,
    pub fingerprint: String,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct McpConfigurationState {
    pub path: String,
    #[ts(type = "number | null")]
    pub revision: Option<u64>,
    // Invalid entries remain inspectable, but never become executable servers.
    pub servers: Vec<Value>,
    pub diagnostics: Vec<Value>,
    pub readable: bool,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct McpSnapshotState {
    pub servers: Vec<Value>,
    pub tools: Vec<Value>,
    pub resources: Vec<Value>,
    pub resource_templates: Vec<Value>,
    pub prompts: Vec<Value>,
    pub client_capabilities: Value,
}

#[derive(Deserialize, TS)]
pub struct McpConfigurationRequest {
    pub name: String,
    pub configuration: Value,
    #[ts(optional, type = "number")]
    pub expected_revision: Option<u64>,
}

#[derive(Deserialize, TS)]
pub struct McpControlRequest {
    pub name: String,
    #[ts(optional)]
    pub trusted: Option<bool>,
    #[ts(optional)]
    pub enabled: Option<bool>,
    #[ts(optional)]
    pub fingerprint: Option<String>,
    #[ts(optional)]
    pub confirmed: Option<bool>,
    #[ts(optional, type = "number")]
    pub expected_revision: Option<u64>,
}

#[derive(Deserialize, TS)]
pub struct McpResourceRequest {
    pub server_id: String,
    pub uri: String,
}

#[derive(Deserialize, TS)]
pub struct McpPromptRequest {
    pub server_id: String,
    pub name: String,
    #[ts(optional)]
    pub arguments: Option<Value>,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct ConnectorRecord {
    pub server_id: String,
    pub status: String,
    #[ts(optional)]
    pub credential_configured: Option<bool>,
    #[ts(optional)]
    pub credential_storage: Option<String>,
    #[serde(rename = "type")]
    #[ts(optional)]
    pub kind: Option<String>,
    #[ts(optional)]
    pub resource: Option<String>,
    #[ts(optional, type = "string | null")]
    pub issuer: Option<String>,
    #[ts(optional, type = "string | null")]
    pub client_id: Option<String>,
    #[ts(optional)]
    pub scopes: Option<Vec<String>>,
    #[ts(optional, type = "number | null")]
    pub expires_at: Option<i64>,
    #[ts(optional, type = "number")]
    pub approved_at: Option<i64>,
    #[ts(optional, type = "string | null")]
    pub api_header: Option<String>,
    #[ts(optional)]
    pub authorization_required: Option<bool>,
    #[ts(optional)]
    pub configuration_current: Option<bool>,
    #[ts(optional)]
    pub enabled: Option<bool>,
    #[ts(optional)]
    pub trust: Option<bool>,
    #[ts(optional)]
    pub current_target: Option<String>,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct PendingConnectorAuthorization {
    pub authorization_id: String,
    pub server_id: String,
    pub resource: String,
    pub issuer: String,
    pub scopes: Vec<String>,
    pub status: String,
    #[ts(optional)]
    pub configuration_current: Option<bool>,
    #[ts(type = "number")]
    pub expires_at: i64,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct StartedConnectorAuthorization {
    pub authorization_id: String,
    pub server_id: String,
    // Returned only to the control surface that explicitly starts authorization.
    pub authorization_url: String,
    pub resource: String,
    pub issuer: String,
    pub client_id: String,
    pub scopes: Vec<String>,
    pub redirect_uri: String,
    pub status: String,
    #[ts(type = "number")]
    pub expires_at: i64,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct ConnectorsState {
    pub connectors: Vec<ConnectorRecord>,
    pub pending: Vec<PendingConnectorAuthorization>,
    pub pending_credential_cleanup: usize,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct ConnectorAuthorizationServer {
    pub issuer: String,
    pub authorization_endpoint: String,
    pub token_endpoint: String,
    pub registration_endpoint: Option<String>,
    pub revocation_endpoint: Option<String>,
    pub token_endpoint_auth_methods_supported: Vec<String>,
    pub pkce: String,
}

#[derive(Clone, Serialize, Deserialize, TS)]
pub struct ConnectorDiscovery {
    pub discovery_id: String,
    pub server_id: String,
    pub resource: String,
    pub metadata_url: String,
    #[ts(type = "number")]
    pub created_at: i64,
    #[ts(type = "number")]
    pub expires_at: i64,
    pub required_scopes: Vec<String>,
    pub supported_scopes: Vec<String>,
    pub authorization_servers: Vec<ConnectorAuthorizationServer>,
}

// These fields are transport inputs, never public Connector state or drafts.
#[derive(Deserialize, TS)]
pub struct ConnectorAuthorizationChoice {
    pub issuer: String,
    #[serde(default)]
    pub scopes: Vec<String>,
    #[ts(optional)]
    pub client_id: Option<String>,
    #[ts(optional)]
    pub client_secret: Option<String>,
    #[ts(optional)]
    pub client_auth_method: Option<String>,
    #[ts(optional)]
    pub redirect_uri: Option<String>,
    #[ts(optional)]
    pub registration_token: Option<String>,
    #[serde(default)]
    pub confirmed: bool,
}

#[derive(Deserialize, TS)]
pub struct ConnectorRequest {
    pub server_id: String,
}

#[derive(Deserialize, TS)]
pub struct AuthorizeConnectorRequest {
    pub server_id: String,
    pub discovery_id: String,
    pub choice: ConnectorAuthorizationChoice,
}

#[derive(Deserialize, TS)]
pub struct CompleteConnectorAuthorizationRequest {
    pub server_id: String,
    pub authorization_id: String,
}

#[derive(Deserialize, TS)]
pub struct CancelConnectorAuthorizationRequest {
    pub authorization_id: String,
}

#[derive(Deserialize, TS)]
pub struct ConnectorApiKeyRequest {
    pub server_id: String,
    pub expected_fingerprint: String,
    pub header: String,
    pub secret: String,
    pub confirmed: bool,
}

#[derive(Deserialize, TS)]
pub struct ClearConnectorCredentialsRequest {
    pub server_id: String,
    pub confirmed: bool,
}

pub(crate) fn typescript() -> Vec<String> {
    vec![
        McpServerRecord::decl(),
        McpConfigurationState::decl(),
        McpSnapshotState::decl(),
        McpConfigurationRequest::decl(),
        McpControlRequest::decl(),
        McpResourceRequest::decl(),
        McpPromptRequest::decl(),
        ConnectorRecord::decl(),
        PendingConnectorAuthorization::decl(),
        StartedConnectorAuthorization::decl(),
        ConnectorsState::decl(),
        ConnectorAuthorizationServer::decl(),
        ConnectorDiscovery::decl(),
        ConnectorAuthorizationChoice::decl(),
        ConnectorRequest::decl(),
        AuthorizeConnectorRequest::decl(),
        CompleteConnectorAuthorizationRequest::decl(),
        CancelConnectorAuthorizationRequest::decl(),
        ConnectorApiKeyRequest::decl(),
        ClearConnectorCredentialsRequest::decl(),
    ]
}
