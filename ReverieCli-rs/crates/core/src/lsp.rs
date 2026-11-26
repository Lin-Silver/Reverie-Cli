//! Project-bound, read-only language services. Trust is supplied by the host.
mod config;
mod evidence;
mod protocol;
mod runtime;

pub use config::{ServerConfig, builtin_definitions, load_manual};
pub use evidence::Position;
pub use protocol::{Delivery, Failure, FailureKind};
pub use runtime::LspRuntime;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;

pub type Notify = Arc<dyn Fn(Value) + Send + Sync>;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    #[default]
    WorkspaceSymbols,
    DocumentSymbols,
    Definitions,
    Diagnostics,
    Status,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Query {
    pub action: Action,
    /// A symbol search, or a project-relative/absolute file for document queries.
    pub query: String,
    /// Zero-based line and UTF-16 code-unit column, never a UTF-8 byte offset.
    pub line: u32,
    pub character: u32,
    pub limit: usize,
    pub server_id: Option<String>,
}
impl Default for Query {
    fn default() -> Self {
        Self {
            action: Action::WorkspaceSymbols,
            query: String::new(),
            line: 0,
            character: 0,
            limit: 20,
            server_id: None,
        }
    }
}

#[cfg(test)]
mod tests;
