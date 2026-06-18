use crate::modes::{normalize_mode, Mode};
use crate::ReverieResult;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha1::{Digest as Sha1Digest, Sha1};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ModelConfig {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub model: String,
    #[serde(default)]
    pub base_url: Option<String>,
    #[serde(default)]
    pub api_key_env: Option<String>,
    #[serde(default)]
    pub provider: Option<String>,
    #[serde(default)]
    pub transport: Option<String>,
    #[serde(default)]
    pub supports_vision: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub active_mode: String,
    pub active_model: Option<String>,
    pub model_source: String,
    pub models: Vec<ModelConfig>,
    pub auto_index: bool,
    pub stream_responses: bool,
    pub show_status_line: bool,
    pub api_timeout: u64,
    pub api_max_retries: u8,
    pub tool_output_style: String,
    pub thinking_output_style: String,
    pub use_workspace_config: bool,
    #[serde(default, flatten)]
    pub extra: BTreeMap<String, serde_json::Value>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            active_mode: Mode::Reverie.canonical().to_string(),
            active_model: None,
            model_source: "standard".to_string(),
            models: Vec::new(),
            auto_index: true,
            stream_responses: true,
            show_status_line: true,
            api_timeout: 300,
            api_max_retries: 5,
            tool_output_style: "compact".to_string(),
            thinking_output_style: "full".to_string(),
            use_workspace_config: false,
            extra: BTreeMap::new(),
        }
    }
}

impl Config {
    pub fn normalized(mut self) -> Self {
        self.active_mode = normalize_mode(&self.active_mode).canonical().to_string();
        self.tool_output_style = normalize_tool_output_style(&self.tool_output_style);
        self.thinking_output_style = normalize_thinking_output_style(&self.thinking_output_style);
        if self.api_timeout < 10 {
            self.api_timeout = 10;
        }
        self
    }
}

pub fn normalize_tool_output_style(value: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "full" | "expanded" => "full".to_string(),
        "hidden" | "off" => "hidden".to_string(),
        _ => "compact".to_string(),
    }
}

pub fn normalize_thinking_output_style(value: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "hidden" | "off" | "none" => "hidden".to_string(),
        "compact" | "summary" | "summarized" => "compact".to_string(),
        _ => "full".to_string(),
    }
}

pub fn app_root() -> PathBuf {
    if let Ok(value) = std::env::var("REVERIE_APP_ROOT") {
        return PathBuf::from(value);
    }
    if let Ok(value) = std::env::var("REVERIE_HOME") {
        return PathBuf::from(value);
    }

    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for candidate in cwd.ancestors() {
        if candidate.join("ReverieCli-Rs").exists() && candidate.join(".git").exists() {
            return candidate.join("dist");
        }
        if candidate.file_name().and_then(|name| name.to_str()) == Some("ReverieCli-Rs") {
            if let Some(parent) = candidate.parent() {
                if parent.join(".git").exists() {
                    return parent.join("dist");
                }
            }
        }
    }

    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Reverie")
}

pub fn project_data_name(project_path: &Path) -> String {
    let resolved = project_path
        .canonicalize()
        .unwrap_or_else(|_| project_path.to_path_buf());
    let mut text = resolved.to_string_lossy().to_string();
    for ch in ['<', '>', ':', '"', '/', '\\', '|', '?', '*'] {
        text = text.replace(ch, "_");
    }
    while text.contains("__") {
        text = text.replace("__", "_");
    }
    let text = text.trim_matches('_').to_string();
    if text.is_empty() {
        "root".to_string()
    } else {
        text
    }
}

pub fn project_data_dir(project_path: &Path) -> PathBuf {
    app_root()
        .join(".reverie")
        .join("projects")
        .join(project_data_name(project_path))
}

pub fn legacy_hashed_project_data_name(project_path: &Path) -> String {
    let resolved = project_path
        .canonicalize()
        .unwrap_or_else(|_| project_path.to_path_buf());
    let safe_name = project_data_name(&resolved);
    let mut hasher = Sha1::new();
    hasher.update(resolved.to_string_lossy().as_bytes());
    let hash = format!("{:x}", hasher.finalize());
    if safe_name.is_empty() {
        hash[..12].to_string()
    } else {
        format!("{}_{}", safe_name, &hash[..12])
    }
}

pub fn legacy_project_cache_dir(project_path: &Path) -> PathBuf {
    app_root()
        .join(".reverie")
        .join("cache")
        .join(legacy_hashed_project_data_name(project_path))
}

pub fn migrate_legacy_project_cache(project_path: &Path) -> ReverieResult<Option<PathBuf>> {
    let legacy = legacy_project_cache_dir(project_path);
    let canonical = project_data_dir(project_path);
    if !legacy.exists() || canonical.exists() {
        return Ok(None);
    }
    if let Some(parent) = canonical.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::rename(&legacy, &canonical)?;
    Ok(Some(canonical))
}

#[derive(Debug, Clone)]
pub struct ConfigManager {
    pub project_root: PathBuf,
    pub global_config_path: PathBuf,
    pub workspace_config_path: PathBuf,
    pub force_workspace_config: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigInitReport {
    pub app_root: PathBuf,
    pub data_root: PathBuf,
    pub project_root: PathBuf,
    pub project_data_dir: PathBuf,
    pub global_config_path: PathBuf,
    pub workspace_config_path: PathBuf,
    pub active_config_path: PathBuf,
    pub created_paths: Vec<PathBuf>,
}

impl ConfigManager {
    pub fn new(project_root: impl AsRef<Path>, force_workspace_config: bool) -> Self {
        let project_root = project_root.as_ref().to_path_buf();
        Self {
            global_config_path: app_root().join(".reverie").join("config.json"),
            workspace_config_path: project_data_dir(&project_root).join("config.json"),
            project_root,
            force_workspace_config,
        }
    }

    pub fn is_workspace_mode(&self) -> bool {
        self.force_workspace_config
            || self
                .workspace_config_path
                .exists()
                .then(|| self.load_from(&self.workspace_config_path).ok())
                .flatten()
                .map(|config| config.use_workspace_config)
                .unwrap_or(false)
    }

    pub fn active_config_path(&self) -> PathBuf {
        if self.force_workspace_config || self.is_workspace_mode() {
            self.workspace_config_path.clone()
        } else {
            self.global_config_path.clone()
        }
    }

    pub fn load(&self) -> ReverieResult<Config> {
        let _ = migrate_legacy_project_cache(&self.project_root);
        self.ensure_dirs()?;
        let path = self.active_config_path();
        if !path.exists() {
            let legacy_toml = path.with_extension("toml");
            if legacy_toml.exists() {
                return self.load_toml_from(&legacy_toml);
            }
        }
        if !path.exists() {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let config = Config::default();
            self.save_to(&path, &config)?;
            return Ok(config);
        }
        self.load_from(&path)
    }

    pub fn save(&self, config: &Config) -> ReverieResult<()> {
        self.save_to(&self.active_config_path(), config)
    }

    pub fn data_root(&self) -> PathBuf {
        app_root().join(".reverie")
    }

    pub fn project_data_dir(&self) -> PathBuf {
        project_data_dir(&self.project_root)
    }

    pub fn ensure_dirs(&self) -> ReverieResult<Vec<PathBuf>> {
        let mut created = Vec::new();
        for path in [
            self.data_root(),
            app_root().join(".reverie").join("projects"),
            self.project_data_dir(),
            self.project_data_dir().join("context_cache"),
            self.project_data_dir().join("specs"),
            self.project_data_dir().join("steering"),
            self.project_data_dir().join("sessions"),
            self.project_data_dir().join("archives"),
            self.project_data_dir().join("checkpoints"),
            self.project_data_dir().join("mcp_resources"),
            self.project_root.join(".reverie"),
        ] {
            if !path.exists() {
                std::fs::create_dir_all(&path)?;
                created.push(path);
            }
        }

        let metadata_path = self.project_data_dir().join("project_metadata.json");
        if !metadata_path.exists() {
            let metadata = json!({
                "schema": "reverie.project_data.v2",
                "project_path": self.project_root.to_string_lossy(),
                "project_data_name": project_data_name(&self.project_root),
                "hash_suffix_used": false,
                "updated_at": chrono::Utc::now().to_rfc3339(),
            });
            std::fs::write(&metadata_path, serde_json::to_string_pretty(&metadata)?)?;
            created.push(metadata_path);
        }

        Ok(created)
    }

    pub fn initialize(&self) -> ReverieResult<ConfigInitReport> {
        let mut created_paths = self.ensure_dirs()?;
        let active_config_path = self.active_config_path();
        let config_existed = active_config_path.exists();
        let config = self.load()?;
        if !config_existed {
            created_paths.push(active_config_path.clone());
        } else if !active_config_path.exists() {
            self.save_to(&active_config_path, &config)?;
            created_paths.push(active_config_path.clone());
        }

        Ok(ConfigInitReport {
            app_root: app_root(),
            data_root: self.data_root(),
            project_root: self.project_root.clone(),
            project_data_dir: self.project_data_dir(),
            global_config_path: self.global_config_path.clone(),
            workspace_config_path: self.workspace_config_path.clone(),
            active_config_path,
            created_paths,
        })
    }

    fn load_from(&self, path: &Path) -> ReverieResult<Config> {
        let raw = std::fs::read_to_string(path)?;
        let repaired = escape_invalid_json_string_control_chars(raw.trim_start_matches('\u{feff}'));
        let parsed: Config = serde_json::from_str(&repaired)?;
        Ok(parsed.normalized())
    }

    fn load_toml_from(&self, path: &Path) -> ReverieResult<Config> {
        let raw = std::fs::read_to_string(path)?;
        let repaired = escape_invalid_json_string_control_chars(raw.trim_start_matches('\u{feff}'));
        let parsed: Config = toml::from_str(&repaired)?;
        Ok(parsed.normalized())
    }

    fn save_to(&self, path: &Path, config: &Config) -> ReverieResult<()> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(path, serde_json::to_string_pretty(config)?)?;
        Ok(())
    }
}

pub fn escape_invalid_json_string_control_chars(raw: &str) -> String {
    raw.chars()
        .map(|ch| match ch {
            '\u{0000}'..='\u{0008}' | '\u{000B}' | '\u{000C}' | '\u{000E}'..='\u{001F}' => ' ',
            _ => ch,
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn project_data_name_is_stable_and_safe() {
        let name = project_data_name(Path::new("C:/repo/app"));
        assert!(!name.contains(':'));
        assert!(!name.contains("__"));
    }
}
