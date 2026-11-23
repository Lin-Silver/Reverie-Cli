use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const KERNEL_SCHEMA: &str = "reverie.kernel.v1";
pub const BRIDGE_PROTOCOL: &str = "sdk-bridge.v1";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionPage {
    pub id: String,
    pub name: String,
    pub created_at: String,
    pub updated_at: String,
    pub metadata: Map<String, Value>,
    pub revision: i64,
    pub messages: Vec<Value>,
    pub total: i64,
    pub before: Option<i64>,
    pub interrupted_streams: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub id: String,
    pub name: String,
    pub created_at: String,
    pub updated_at: String,
    pub message_count: i64,
}

#[derive(Debug, Serialize, Deserialize)]
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
