//! Subagent management for Reverie CLI.
//!
//! Subagents delegate bounded tasks to focused workers that run in parallel.
//! Based on Codex-style subagent architecture.

pub mod manager;
pub mod types;
pub mod spawn;

pub use manager::SubagentManager;
pub use types::*;
pub use spawn::spawn_subagent;
