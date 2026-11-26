use serde::{Deserialize, Serialize};
use serde_json::Value;
use ts_rs::TS;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum PluginSourceKind {
    Directory,
    Archive,
    Git,
    Market,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct PluginSourceRequest {
    pub kind: PluginSourceKind,
    #[ts(optional)]
    pub location: Option<String>,
    #[ts(optional)]
    pub revision: Option<String>,
    #[ts(optional)]
    pub subdirectory: Option<String>,
    #[ts(optional)]
    pub entry_id: Option<String>,
    #[ts(optional)]
    pub sha256: Option<String>,
    #[ts(optional)]
    pub signing_key: Option<String>,
    #[ts(optional)]
    pub require_signature: Option<bool>,
}

#[derive(Debug, Clone, Deserialize, TS)]
pub struct PreparePluginRequest {
    pub source: PluginSourceRequest,
    #[ts(optional)]
    pub plugin_id: Option<String>,
    #[ts(optional)]
    pub operation_id: Option<String>,
    #[ts(optional, type = "number")]
    pub expected_revision: Option<u64>,
}

#[derive(Debug, Clone, Deserialize, TS)]
pub struct ActivatePluginRequest {
    pub plugin_id: String,
    pub candidate_sha256: String,
    #[ts(optional)]
    pub approved_sha256: Option<String>,
    #[ts(optional)]
    pub approved_profile_sha256: Option<String>,
    #[ts(optional, type = "number")]
    pub expected_revision: Option<u64>,
}

#[derive(Debug, Clone, Deserialize, TS)]
pub struct PluginControlRequest {
    #[serde(rename = "pluginId")]
    pub plugin_id: String,
    #[serde(rename = "projectRoot")]
    #[ts(optional)]
    pub project_root: Option<String>,
    #[ts(optional)]
    pub candidate_sha256: Option<String>,
    #[ts(optional)]
    pub approval_profile_sha256: Option<String>,
    #[ts(optional)]
    pub enabled: Option<bool>,
    #[ts(optional)]
    pub trusted: Option<bool>,
    #[ts(optional)]
    pub hooks_enabled: Option<bool>,
    #[ts(optional)]
    pub auto_update: Option<bool>,
    #[ts(optional)]
    pub confirmed: Option<bool>,
    #[ts(optional, type = "number")]
    pub expected_revision: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct PluginComponent {
    pub kind: String,
    pub name: String,
    pub path: String,
    pub description: String,
    pub policy: Value,
    pub requires_platform: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct PluginCandidate {
    pub sha256: String,
    pub name: String,
    pub version: String,
    pub source: Value,
    #[ts(type = "number")]
    pub bytes: u64,
    pub signing_key: Option<String>,
    pub verification: String,
    pub approval_profile_sha256: String,
    pub approval_required: bool,
    pub components: Vec<PluginComponent>,
    pub license: String,
    pub license_files: Vec<String>,
    pub approval: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct PluginRecord {
    pub id: String,
    pub name: String,
    pub family: String,
    pub version: String,
    pub status: String,
    pub status_label: String,
    pub enabled: bool,
    pub trusted: bool,
    pub protocol_status: String,
    pub protocol_label: String,
    pub tool_count: usize,
    pub command_count: usize,
    pub skill_count: usize,
    pub entry_path: String,
    pub install_dir: String,
    pub active_sha256: String,
    pub approval_profile_sha256: String,
    pub hooks_enabled: bool,
    pub auto_update: bool,
    pub previous_sha256: String,
    pub source: Value,
    pub candidates: Vec<PluginCandidate>,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct PluginsState {
    #[ts(type = "number")]
    pub revision: u64,
    pub summary: Value,
    pub records: Vec<PluginRecord>,
}

pub(crate) fn typescript() -> Vec<String> {
    vec![
        PluginSourceKind::decl(),
        PluginSourceRequest::decl(),
        PreparePluginRequest::decl(),
        ActivatePluginRequest::decl(),
        PluginControlRequest::decl(),
        PluginComponent::decl(),
        PluginCandidate::decl(),
        PluginRecord::decl(),
        PluginsState::decl(),
    ]
}
