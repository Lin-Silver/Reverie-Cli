//! Native MCP connections shared by manual and plugin configuration.
pub mod config;
pub(crate) mod privacy;
mod runtime;
mod sse;
mod transport;

pub use config::{McpConfigStore, ServerConfig, Transport, effective_servers};
pub use runtime::{AuthorizationHeaders, McpCallLease, McpRuntime, McpSnapshot, McpTool};
pub use transport::{Delivery, Failure, Notify};

#[cfg(test)]
mod tests;
