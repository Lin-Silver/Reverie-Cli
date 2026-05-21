//! Spawn helpers for callers that do not need to own a manager.

use crate::manager::SubagentManager;
use crate::types::{SubagentSpawnRequest, SubagentSpawnResult};
use anyhow::Result;

pub fn spawn_subagent(request: SubagentSpawnRequest) -> Result<SubagentSpawnResult> {
    let mut manager = SubagentManager::default();
    manager.spawn(request)
}
