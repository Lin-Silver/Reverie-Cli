use crate::modes::{normalize_mode, Mode};
use crate::ReverieResult;
use anyhow::{Context, Result, anyhow};
use serde::{Deserialize, Serialize};
use sha1::{Digest as Sha1Digest, Sha1};
use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};
use std::fs;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
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
            api_max_retries: 2,
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
        "summary" | "summarized" => "summary".to_string(),
        _ => "full".to_string(),
    }
}

pub fn app_root() -> PathBuf {
    if let Ok(value) = std::env::var("REVERIE_HOME") {
        return PathBuf::from(value);
    }
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Reverie")
}

pub fn project_data_dir(project_root: &Path) -> PathBuf {
    project_root.join(".reverie")
}

/// Configuration manager for loading and saving configuration
pub struct ConfigManager {
    project_root: PathBuf,
    use_workspace_config: bool,
    config_path: PathBuf,
}

impl ConfigManager {
    /// Create a new config manager
    pub fn new(project_root: impl AsRef<Path>, use_workspace_config: bool) -> Self {
        let project_root = project_root.as_ref().to_path_buf();
        let config_path = if use_workspace_config {
            project_root.join(".reverie/config.json")
        } else {
            app_root().join("config.json")
        };

        Self {
            project_root,
            use_workspace_config,
            config_path,
        }
    }

    /// Get the active config path
    pub fn active_config_path(&self) -> PathBuf {
        self.config_path.clone()
    }

    /// Load configuration from disk
    pub fn load(&self) -> Result<Config> {
        info!("Loading configuration from: {}", self.config_path.display());

        if !self.config_path.exists() {
            debug!("Config file not found, using defaults");
            return Ok(Config::default().normalized());
        }

        let content = fs::read_to_string(&self.config_path)
            .context("Failed to read config file")?;

        let mut config: Config = serde_json::from_str(&content)
            .context("Failed to parse config JSON")?;

        // Normalize the config
        config = config.normalized();

        info!("Loaded configuration: mode={}, model={:?}", 
              config.active_mode, config.active_model);

        Ok(config)
    }

    /// Save configuration to disk
    pub fn save(&self, config: &Config) -> Result<()> {
        info!("Saving configuration to: {}", self.config_path.display());

        // Create directory if needed
        if let Some(parent) = self.config_path.parent() {
            fs::create_dir_all(parent)?;
        }

        // Write with secure permissions
        let content = serde_json::to_string_pretty(config)?;
        fs::write(&self.config_path, content)?;

        info!("Configuration saved successfully");
        Ok(())
    }

    /// Update a specific setting
    pub fn update_setting(&self, key: &str, value: serde_json::Value) -> Result<Config> {
        let mut config = self.load()?;

        match key {
            "active_model" => config.active_model = value.as_str().map(|s| s.to_string()),
            "active_mode" => config.active_mode = value.as_str()
                .map(|s| normalize_mode(s).canonical().to_string())
                .unwrap_or(config.active_mode),
            "stream_responses" => config.stream_responses = value.as_bool().unwrap_or(config.stream_responses),
            "api_timeout" => config.api_timeout = value.as_u64().unwrap_or(config.api_timeout),
            "tool_output_style" => config.tool_output_style = value.as_str()
                .map(|s| normalize_tool_output_style(s))
                .unwrap_or(config.tool_output_style),
            "thinking_output_style" => config.thinking_output_style = value.as_str()
                .map(|s| normalize_thinking_output_style(s))
                .unwrap_or(config.thinking_output_style),
            _ => {
                config.extra.insert(key.to_string(), value);
            }
        }

        self.save(&config)?;
        Ok(config)
    }
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

    fn load_from(&self, path: &Path) -> ReverieResult<Config> {
        let raw = std::fs::read_to_string(path)?;
        let repaired = escape_invalid_json_string_control_chars(&raw);
        let parsed: Config = serde_json::from_str(&repaired)?;
        Ok(parsed.normalized())
    }

    fn load_toml_from(&self, path: &Path) -> ReverieResult<Config> {
        let raw = std::fs::read_to_string(path)?;
        let repaired = escape_invalid_json_string_control_chars(&raw);
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
