use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use ts_rs::TS;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const KERNEL_SCHEMA: &str = "reverie.kernel.v1";
pub const BRIDGE_PROTOCOL: &str = "sdk-bridge.v1";

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SessionPage {
    pub id: String,
    pub name: String,
    pub created_at: String,
    pub updated_at: String,
    pub metadata: Map<String, Value>,
    #[ts(type = "number")]
    pub revision: i64,
    pub messages: Vec<Value>,
    #[ts(type = "number")]
    pub total: i64,
    #[ts(type = "number | null")]
    pub before: Option<i64>,
    pub interrupted_streams: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SessionInfo {
    pub id: String,
    pub name: String,
    pub created_at: String,
    pub updated_at: String,
    #[ts(type = "number")]
    pub message_count: i64,
}

#[derive(Debug, Serialize, Deserialize, TS)]
pub struct PromptResult {
    pub success: bool,
    pub prompt: String,
    pub output_text: String,
    pub thinking_text: String,
    pub error: String,
    pub mode: String,
    pub model_display_name: String,
    pub provider_label: String,
    pub session_id: String,
    pub session_name: String,
    pub run_id: String,
    pub state: String,
    pub duration_seconds: f64,
    pub ui_events: Vec<Value>,
    pub activity_events: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct UserQuestion {
    pub question_id: String,
    pub question: String,
    pub reason: String,
    pub options: Vec<String>,
    pub custom_answer: bool,
    pub multiple: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SkillRecord {
    pub key: String,
    pub name: String,
    pub description: String,
    pub summary: String,
    pub path: String,
    pub scope: String,
    pub root: String,
    pub plugin_id: String,
    pub allow_implicit_invocation: bool,
    pub pinned: bool,
    pub shadowed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SkillIssue {
    pub name: String,
    pub path: String,
    pub scope: String,
    pub root: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SkillShadow {
    pub name: String,
    pub scope: String,
    pub root: String,
    pub path: String,
    pub winner_scope: String,
    pub winner_root: String,
    pub winner_path: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct PinnedSkillsState {
    pub max: usize,
    pub keys: Vec<String>,
    pub names: Vec<String>,
    pub unresolved: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SkillsState {
    #[ts(optional)]
    pub mode: Option<String>,
    pub count: usize,
    pub invalid_count: usize,
    pub shadowed_count: usize,
    pub records: Vec<SkillRecord>,
    pub pinned: PinnedSkillsState,
    pub errors: Vec<SkillIssue>,
    pub shadowed: Vec<SkillShadow>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum SkillLookupOperation {
    List,
    Search,
    Inspect,
    ReadResource,
}
#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SkillLookupRequest {
    pub operation: SkillLookupOperation,
    #[ts(optional)]
    pub query: Option<String>,
    #[ts(optional)]
    pub skill_name: Option<String>,
    #[ts(optional)]
    pub resource_path: Option<String>,
    #[ts(optional)]
    pub max_results: Option<usize>,
    #[ts(optional)]
    pub max_body_chars: Option<usize>,
    #[ts(optional)]
    pub body_offset: Option<usize>,
    #[ts(optional)]
    pub force_refresh: Option<bool>,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
pub enum SemanticDevice {
    #[default]
    Cpu,
    Cuda,
    DirectMl,
    CoreMl,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, TS)]
#[serde(deny_unknown_fields)]
pub struct SemanticSelection {
    pub manifest_sha256: String,
    pub version: String,
    pub device: SemanticDevice,
    pub threads: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SemanticResourceRecord {
    pub manifest_sha256: String,
    pub version: String,
    pub platform: String,
    pub architecture: String,
    #[ts(type = "number")]
    pub bytes: u64,
    pub active: bool,
    pub removal_pending: bool,
    pub integrity: String,
}
#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct ContextOperation {
    pub operation_id: String,
    pub action: String,
    pub project_root: String,
    pub phase: String,
    pub completed: usize,
    pub total: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct ContextWatchState {
    pub enabled: bool,
    pub status: String,
    pub backend: String,
    pub project_root: String,
    #[ts(type = "number")]
    pub revision: i64,
    #[ts(type = "number")]
    pub semantic_revision: i64,
    pub manifest_sha256: Option<String>,
    pub operation: Option<ContextOperation>,
    pub error: String,
}
#[derive(Debug, Clone, Serialize, Deserialize, TS)]
pub struct SemanticResourcesState {
    pub available: bool,
    pub status: String,
    #[ts(optional, type = "number")]
    pub revision: Option<u64>,
    pub active: Option<SemanticSelection>,
    pub previous: Option<SemanticSelection>,
    pub models: Value,
    pub error: String,
    pub pending_restart: Vec<String>,
    #[ts(optional)]
    pub records: Option<Vec<SemanticResourceRecord>>,
    #[ts(optional)]
    pub inventory_errors: Option<Vec<String>>,
    #[ts(optional)]
    pub operations: Option<Vec<ContextOperation>>,
}

pub fn typescript_types() -> String {
    let definitions = [
        Value::decl(),
        SessionPage::decl(),
        SessionInfo::decl(),
        PromptResult::decl(),
        UserQuestion::decl(),
        SkillRecord::decl(),
        SkillIssue::decl(),
        SkillShadow::decl(),
        PinnedSkillsState::decl(),
        SkillsState::decl(),
        SkillLookupOperation::decl(),
        SkillLookupRequest::decl(),
        SemanticDevice::decl(),
        SemanticSelection::decl(),
        SemanticResourceRecord::decl(),
        ContextOperation::decl(),
        ContextWatchState::decl(),
        SemanticResourcesState::decl(),
    ];
    format!(
        "// Generated by the Rust protocol crate. Do not edit.\n{}\n",
        definitions
            .into_iter()
            .map(|definition| format!("export {definition}"))
            .collect::<Vec<_>>()
            .join("\n")
    )
}

#[derive(Debug, Deserialize)]
pub struct Request {
    #[serde(default)]
    pub id: Value,
    #[serde(default)]
    pub action: String,
    #[serde(default)]
    pub payload: Value,
}

#[derive(Debug, Serialize)]
pub struct Reply {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<Value>,
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(flatten)]
    pub fields: Map<String, Value>,
}

impl Reply {
    pub fn new(id: Option<Value>, kind: &str, fields: Map<String, Value>) -> Self {
        Self {
            id,
            kind: kind.into(),
            fields,
        }
    }

    pub fn error(id: Value, error: impl ToString) -> Self {
        Self::new(
            Some(id),
            "error",
            Map::from_iter([("error".into(), Value::String(error.to_string()))]),
        )
    }
}

#[derive(Debug, Serialize)]
pub struct KernelInfo {
    pub schema: &'static str,
    pub version: &'static str,
    pub bridge_protocol: &'static str,
    pub interface_version: &'static str,
    pub platform: &'static str,
    pub arch: &'static str,
    pub frozen: bool,
    pub implementation: &'static str,
    pub release_status: &'static str,
    pub context_engine: ContextIdentity,
}

#[derive(Debug, Serialize)]
pub struct ContextIdentity {
    pub backend: &'static str,
    pub execution: &'static str,
    pub available: bool,
}

pub fn kernel_info() -> KernelInfo {
    KernelInfo {
        schema: KERNEL_SCHEMA,
        version: VERSION,
        bridge_protocol: BRIDGE_PROTOCOL,
        interface_version: "1.0",
        platform: match std::env::consts::OS {
            "windows" => "win32",
            "macos" => "darwin",
            other => other,
        },
        arch: match std::env::consts::ARCH {
            "x86_64" => "x64",
            "aarch64" => "arm64",
            "x86" => "ia32",
            other => other,
        },
        frozen: true,
        implementation: "rust",
        release_status: "development",
        context_engine: ContextIdentity {
            backend: "rust",
            execution: "in-process",
            available: true,
        },
    }
}
