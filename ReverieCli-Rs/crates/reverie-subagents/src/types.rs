//! Subagent types and data structures.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::Duration;

/// Subagent definition (loaded from TOML)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubagentDefinition {
    /// Subagent name
    pub name: String,
    /// Human-readable description
    pub description: String,
    /// Nickname candidates for identification
    #[serde(default)]
    pub nickname_candidates: Vec<String>,
    /// Developer instructions (system prompt)
    pub developer_instructions: String,
    /// Model to use
    #[serde(default = "default_model")]
    pub model: String,
    /// Sandbox mode
    #[serde(default)]
    pub sandbox_mode: SandboxMode,
    /// Maximum runtime in seconds
    #[serde(default = "default_max_runtime")]
    pub job_max_runtime_seconds: u64,
}

fn default_model() -> String {
    "default".to_string()
}

fn default_max_runtime() -> u64 {
    300
}

/// Sandbox mode for subagent execution
#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum SandboxMode {
    #[default]
    ReadOnly,
    WorkspaceWrite,
    DangerFullAccess,
}

/// Subagent configuration (global settings)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubagentConfig {
    /// Maximum concurrent subagents
    #[serde(default = "default_max_threads")]
    pub max_threads: usize,
    /// Maximum nesting depth
    #[serde(default = "default_max_depth")]
    pub max_depth: usize,
    /// Default max runtime
    #[serde(default = "default_max_runtime")]
    pub job_max_runtime_seconds: u64,
}

fn default_max_threads() -> usize {
    6
}

fn default_max_depth() -> usize {
    1
}

/// A running subagent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubagentRun {
    /// Unique run ID
    pub id: String,
    /// Subagent name
    pub name: String,
    /// Task description
    pub task: String,
    /// Parent run ID (if spawned by another subagent)
    pub parent_id: Option<String>,
    /// Depth in spawn chain
    pub depth: usize,
    /// Status
    pub status: SubagentStatus,
    /// Start time
    pub started_at: chrono::DateTime<chrono::Utc>,
    /// End time (if completed)
    pub completed_at: Option<chrono::DateTime<chrono::Utc>>,
    /// Output
    pub output: Option<String>,
    /// Error (if failed)
    pub error: Option<String>,
}

/// Subagent status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SubagentStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Cancelled,
}

/// Subagent spawn request
#[derive(Debug, Clone)]
pub struct SubagentSpawnRequest {
    /// Subagent name or definition
    pub name: String,
    /// Task to perform
    pub task: String,
    /// Project root
    pub project_root: PathBuf,
    /// Working directory
    pub cwd: PathBuf,
    /// Parent run ID
    pub parent_id: Option<String>,
    /// Depth in spawn chain
    pub depth: usize,
    /// Timeout
    pub timeout: Option<Duration>,
    /// Inherit environment
    pub inherit_env: bool,
}

/// Subagent spawn result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubagentSpawnResult {
    /// Run ID
    pub run_id: String,
    /// Whether spawn was successful
    pub success: bool,
    /// Error message (if failed)
    pub error: Option<String>,
}

/// Built-in subagent types
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "lowercase")]
pub enum BuiltInSubagentType {
    #[default]
    Default,
    Worker,
    Explorer,
}

impl BuiltInSubagentType {
    pub fn default_instructions(&self) -> &'static str {
        match self {
            BuiltInSubagentType::Default => "You are a general-purpose coding assistant.",
            BuiltInSubagentType::Worker => {
                "You are an execution-focused worker. Focus on implementing changes."
            }
            BuiltInSubagentType::Explorer => {
                "You are a read-heavy exploration agent. Focus on understanding codebases."
            }
        }
    }
}
