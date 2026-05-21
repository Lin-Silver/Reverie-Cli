use crate::config::{project_data_dir, ConfigManager};
use crate::plugins::RuntimePluginManager;
use crate::session::{CheckpointStore, OperationStore, SessionStore};
use crate::ReverieResult;
use reverie_context::CodebaseIndexer;
use reverie_tools::ToolRegistry;
use serde::Serialize;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize)]
pub struct HarnessCapabilityReport {
    pub project_root: PathBuf,
    pub config_path: PathBuf,
    pub active_mode: String,
    pub tool_count: usize,
    pub plugin_count: usize,
    pub session_count: usize,
    pub checkpoint_count: usize,
    pub operation_count: usize,
    pub cached_index_available: bool,
    pub risks: Vec<String>,
}

pub fn build_harness_capability_report(
    project_root: impl AsRef<Path>,
) -> ReverieResult<HarnessCapabilityReport> {
    let project_root = project_root.as_ref().to_path_buf();
    let manager = ConfigManager::new(&project_root, false);
    let config = manager.load()?;
    let data_dir = project_data_dir(&project_root);
    let cached_index_available = CodebaseIndexer::new(&project_root)
        .with_cache_dir(data_dir.join("context_cache"))
        .load_cached_index()?
        .is_some();
    let plugin_count = RuntimePluginManager::new(&project_root)
        .list_plugins()?
        .len();
    let session_count = SessionStore::new(data_dir.join("sessions")).list()?.len();
    let checkpoint_count = CheckpointStore::new(data_dir.join("checkpoints"))
        .list()?
        .len();
    let operation_count = OperationStore::new(data_dir.join("operations"))
        .list()?
        .len();
    let tool_count = ToolRegistry::builtin().all().len();
    let mut risks = Vec::new();
    if config.models.is_empty()
        && !matches!(
            config.model_source.as_str(),
            "codex" | "nvidia" | "modelscope"
        )
    {
        risks.push("No standard model presets are configured.".to_string());
    }
    if !cached_index_available {
        risks.push("No cached Context Engine index is available yet.".to_string());
    }
    Ok(HarnessCapabilityReport {
        project_root,
        config_path: manager.active_config_path(),
        active_mode: config.active_mode,
        tool_count,
        plugin_count,
        session_count,
        checkpoint_count,
        operation_count,
        cached_index_available,
        risks,
    })
}
