//! Skill loader for loading and caching skills.

use crate::discovery::SkillDiscovery;
use crate::types::*;
use anyhow::Result;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::sync::RwLock;
use tracing::info;

/// Skill loader with caching
pub struct SkillLoader {
    /// Discovery engine
    discovery: SkillDiscovery,
    /// Cached skills
    cache: RwLock<HashMap<String, Skill>>,
    /// Last discovery result
    last_result: RwLock<Option<SkillDiscoveryResult>>,
}

impl SkillLoader {
    /// Create a new skill loader
    pub fn new(project_root: impl AsRef<Path>) -> Result<Self> {
        Ok(Self {
            discovery: SkillDiscovery::new(project_root)?,
            cache: RwLock::new(HashMap::new()),
            last_result: RwLock::new(None),
        })
    }

    /// Reload all skills from disk
    pub async fn reload(&self) -> Result<usize> {
        info!("Reloading skills from disk");

        let result = self.discovery.discover_all().await;
        let count = result.skills.len();

        let mut cache = self.cache.write().await;
        cache.clear();
        for skill in result.skills.iter() {
            cache.insert(skill.name.clone(), skill.clone());
        }

        *self.last_result.write().await = Some(result);

        info!("Reloaded {} skills", count);
        Ok(count)
    }

    /// Get a skill by name
    pub async fn get(&self, name: &str) -> Option<Skill> {
        let cache = self.cache.read().await;
        cache.get(name).cloned()
    }

    /// Get all skills
    pub async fn list_all(&self) -> Vec<Skill> {
        let cache = self.cache.read().await;
        cache.values().cloned().collect()
    }

    /// Search skills by pattern
    pub async fn search(&self, pattern: &str) -> Vec<Skill> {
        let cache = self.cache.read().await;
        cache
            .values()
            .filter(|s| s.name.contains(pattern) || s.description.contains(pattern))
            .cloned()
            .collect()
    }

    /// Check if a skill exists
    pub async fn exists(&self, name: &str) -> bool {
        let cache = self.cache.read().await;
        cache.contains_key(name)
    }

    /// Get the last discovery result
    pub async fn last_discovery(&self) -> Option<SkillDiscoveryResult> {
        self.last_result.read().await.clone()
    }
}

impl Default for SkillLoader {
    fn default() -> Self {
        Self::new(PathBuf::from(".")).unwrap()
    }
}
