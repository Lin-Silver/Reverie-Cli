//! Plugin manifest and lifecycle primitives.
//!
//! The Python runtime owns the richer plugin execution path today. This crate
//! keeps the Rust workspace buildable while providing typed structures for the
//! next migration step: discovery, validation, and lifecycle orchestration.

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PluginManifest {
    pub name: String,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub entrypoint: Option<String>,
    #[serde(default)]
    pub permissions: Vec<PluginPermission>,
    #[serde(default)]
    pub tools: Vec<PluginTool>,
    #[serde(default)]
    pub metadata: BTreeMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PluginPermission {
    FileSystem,
    Network,
    Shell,
    Environment,
    Desktop,
    Custom(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PluginTool {
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub schema: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PluginStatus {
    Discovered,
    Loaded,
    Enabled,
    Disabled,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginRecord {
    pub manifest: PluginManifest,
    pub root: PathBuf,
    pub status: PluginStatus,
    pub updated_at: DateTime<Utc>,
    #[serde(default)]
    pub last_error: Option<String>,
}

impl PluginRecord {
    pub fn discovered(manifest: PluginManifest, root: impl Into<PathBuf>) -> Self {
        Self {
            manifest,
            root: root.into(),
            status: PluginStatus::Discovered,
            updated_at: Utc::now(),
            last_error: None,
        }
    }

    pub fn mark_failed(&mut self, error: impl Into<String>) {
        self.status = PluginStatus::Failed;
        self.updated_at = Utc::now();
        self.last_error = Some(error.into());
    }
}

pub fn load_manifest(path: impl AsRef<Path>) -> Result<PluginManifest> {
    let path = path.as_ref();
    let content = fs::read_to_string(path)
        .with_context(|| format!("failed to read plugin manifest {}", path.display()))?;
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();

    match extension.as_str() {
        "json" => serde_json::from_str(&content)
            .with_context(|| format!("failed to parse JSON plugin manifest {}", path.display())),
        "toml" => toml::from_str(&content)
            .with_context(|| format!("failed to parse TOML plugin manifest {}", path.display())),
        _ => anyhow::bail!(
            "unsupported plugin manifest extension for {}",
            path.display()
        ),
    }
}

pub fn validate_manifest(manifest: &PluginManifest) -> Result<()> {
    if manifest.name.trim().is_empty() {
        anyhow::bail!("plugin manifest name is required");
    }

    for tool in &manifest.tools {
        if tool.name.trim().is_empty() {
            anyhow::bail!("plugin tool name is required");
        }
    }

    Ok(())
}
