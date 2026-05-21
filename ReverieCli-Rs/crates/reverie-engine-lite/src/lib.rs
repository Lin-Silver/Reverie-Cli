use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum EngineLiteError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineProject {
    pub name: String,
    pub runtime_version: String,
    #[serde(default = "default_schema")]
    pub schema: String,
    #[serde(default)]
    pub created_at: Option<String>,
    pub scenes: Vec<Scene>,
    pub assets: Vec<AssetRef>,
    #[serde(default)]
    pub systems: Vec<SystemSpec>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Scene {
    pub id: String,
    pub title: String,
    pub entities: Vec<Entity>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entity {
    pub id: String,
    pub kind: String,
    pub transform: Transform,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Transform {
    pub position: [f32; 3],
    pub rotation: [f32; 3],
    pub scale: [f32; 3],
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssetRef {
    pub id: String,
    pub path: PathBuf,
    pub kind: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemSpec {
    pub id: String,
    pub kind: String,
    #[serde(default)]
    pub enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeSummary {
    pub name: String,
    pub scene_count: usize,
    pub entity_count: usize,
    pub asset_count: usize,
    pub system_count: usize,
    pub issues: Vec<String>,
}

impl EngineProject {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            runtime_version: env!("CARGO_PKG_VERSION").to_string(),
            schema: default_schema(),
            created_at: Some(chrono::Utc::now().to_rfc3339()),
            scenes: vec![Scene {
                id: "main".to_string(),
                title: "Main".to_string(),
                entities: Vec::new(),
            }],
            assets: Vec::new(),
            systems: vec![
                SystemSpec {
                    id: "input".to_string(),
                    kind: "input".to_string(),
                    enabled: true,
                },
                SystemSpec {
                    id: "save_load".to_string(),
                    kind: "persistence".to_string(),
                    enabled: true,
                },
            ],
        }
    }

    pub fn validate(&self) -> Vec<String> {
        let mut issues = Vec::new();
        if self.name.trim().is_empty() {
            issues.push("project name is empty".to_string());
        }
        if self.scenes.is_empty() {
            issues.push("project has no scenes".to_string());
        }
        let mut scene_ids = HashSet::new();
        for scene in &self.scenes {
            if scene.id.trim().is_empty() {
                issues.push("scene id is empty".to_string());
            }
            if !scene_ids.insert(scene.id.clone()) {
                issues.push(format!("duplicate scene id: {}", scene.id));
            }
            let mut entity_ids = HashSet::new();
            for entity in &scene.entities {
                if entity.id.trim().is_empty() {
                    issues.push(format!("entity id is empty in scene {}", scene.id));
                }
                if !entity_ids.insert(entity.id.clone()) {
                    issues.push(format!(
                        "duplicate entity id in scene {}: {}",
                        scene.id, entity.id
                    ));
                }
                if entity.transform.scale.contains(&0.0) {
                    issues.push(format!("entity {} has zero scale", entity.id));
                }
            }
        }
        let mut asset_ids = HashSet::new();
        for asset in &self.assets {
            if asset.id.trim().is_empty() {
                issues.push("asset id is empty".to_string());
            }
            if !asset_ids.insert(asset.id.clone()) {
                issues.push(format!("duplicate asset id: {}", asset.id));
            }
            if asset.path.as_os_str().is_empty() {
                issues.push(format!("asset {} has empty path", asset.id));
            }
        }
        issues
    }

    pub fn summary(&self) -> RuntimeSummary {
        RuntimeSummary {
            name: self.name.clone(),
            scene_count: self.scenes.len(),
            entity_count: self.scenes.iter().map(|scene| scene.entities.len()).sum(),
            asset_count: self.assets.len(),
            system_count: self.systems.len(),
            issues: self.validate(),
        }
    }

    pub fn add_scene(&mut self, id: impl Into<String>, title: impl Into<String>) {
        self.scenes.push(Scene {
            id: id.into(),
            title: title.into(),
            entities: Vec::new(),
        });
    }

    pub fn add_entity(&mut self, scene_id: &str, entity: Entity) -> bool {
        if let Some(scene) = self.scenes.iter_mut().find(|scene| scene.id == scene_id) {
            scene.entities.push(entity);
            true
        } else {
            false
        }
    }

    pub fn register_asset(&mut self, asset: AssetRef) {
        self.assets.push(asset);
    }

    pub fn load_from(dir: &Path) -> Result<Self, EngineLiteError> {
        let text = std::fs::read_to_string(dir.join("reverie.project.json"))?;
        Ok(serde_json::from_str(&text)?)
    }

    pub fn save_to(&self, dir: &Path) -> Result<(), EngineLiteError> {
        std::fs::create_dir_all(dir)?;
        std::fs::write(
            dir.join("reverie.project.json"),
            serde_json::to_string_pretty(self)?,
        )?;
        Ok(())
    }

    pub fn scaffold_to(&self, dir: &Path) -> Result<(), EngineLiteError> {
        self.save_to(dir)?;
        for child in ["assets", "scenes", "scripts", "runtime", "artifacts"] {
            std::fs::create_dir_all(dir.join(child))?;
        }
        std::fs::write(
            dir.join("runtime").join("README.md"),
            format!(
                "# {}\n\nGenerated Reverie Engine Lite runtime scaffold.\n",
                self.name
            ),
        )?;
        std::fs::write(
            dir.join("scenes").join("main.scene.json"),
            serde_json::to_string_pretty(&self.scenes[0])?,
        )?;
        Ok(())
    }
}

impl Default for Transform {
    fn default() -> Self {
        Self {
            position: [0.0, 0.0, 0.0],
            rotation: [0.0, 0.0, 0.0],
            scale: [1.0, 1.0, 1.0],
        }
    }
}

impl Entity {
    pub fn new(id: impl Into<String>, kind: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            kind: kind.into(),
            transform: Transform::default(),
        }
    }
}

fn default_schema() -> String {
    "reverie.engine_lite.project.v1".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn project_scaffold_round_trips_and_validates() {
        let temp = tempfile::tempdir().unwrap();
        let mut project = EngineProject::new("Slice");
        project.add_entity("main", Entity::new("player", "character"));
        project.register_asset(AssetRef {
            id: "hero".to_string(),
            path: PathBuf::from("assets/hero.png"),
            kind: "texture".to_string(),
        });
        project.scaffold_to(temp.path()).unwrap();
        let loaded = EngineProject::load_from(temp.path()).unwrap();
        assert!(loaded.validate().is_empty());
        assert_eq!(loaded.summary().entity_count, 1);
        assert!(temp.path().join("scenes/main.scene.json").is_file());
    }
}
