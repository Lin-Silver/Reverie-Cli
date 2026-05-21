//! Skill discovery mechanism.
//!
//! Discovers skills from multiple scopes in order of specificity.

use crate::types::*;
use anyhow::{Context, Result};
use std::path::{Path, PathBuf};
use tracing::{debug, info, warn};

/// Default directories to skip during skill scanning
const SKIP_DIRS: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".agents",
];

/// Skill discovery engine
pub struct SkillDiscovery {
    /// Project root
    project_root: PathBuf,
    /// User home directory
    user_home: PathBuf,
}

impl SkillDiscovery {
    /// Create a new skill discovery engine
    pub fn new(project_root: impl AsRef<Path>) -> Result<Self> {
        let project_root = project_root.as_ref().canonicalize()?;
        let user_home = dirs::home_dir()
            .ok_or_else(|| anyhow::anyhow!("Could not determine user home directory"))?;

        Ok(Self {
            project_root,
            user_home,
        })
    }

    /// Discover all skills from all scopes
    pub async fn discover_all(&self) -> SkillDiscoveryResult {
        let mut skills = Vec::new();
        let mut errors = Vec::new();

        // Define scopes in order of specificity
        let scopes = [
            SkillScope::Current,
            SkillScope::Parent,
            SkillScope::Repository,
            SkillScope::User,
            SkillScope::System,
        ];

        for scope in scopes {
            match self.discover_from_scope(scope, &mut skills, &mut errors).await {
                Ok(count) => {
                    info!("Discovered {} skills from {:?}", count, scope);
                }
                Err(e) => {
                    warn!("Error discovering skills from {:?}: {}", scope, e);
                }
            }
        }

        // Add built-in skills
        self.discover_builtin(&mut skills);

        SkillDiscoveryResult { skills, errors }
    }

    /// Discover skills from a specific scope
    async fn discover_from_scope(
        &self,
        scope: SkillScope,
        skills: &mut Vec<Skill>,
        errors: &mut Vec<String>,
    ) -> Result<usize> {
        let base_path = match scope.path(&self.project_root, &self.user_home) {
            Some(path) => path,
            None => return Ok(0),
        };

        if !base_path.exists() {
            debug!("Skill directory does not exist: {:?}", base_path);
            return Ok(0);
        }

        let mut count = 0;

        // Walk the skill directory
        for entry in walkdir::WalkDir::new(&base_path)
            .into_iter()
            .filter_entry(|e| !SKIP_DIRS.contains(&e.file_name().to_str().unwrap_or("")))
        {
            let entry = entry?;
            let path = entry.path();

            if path.file_name().map(|n| n == "SKILL.md").unwrap_or(false) {
                match self.load_skill(path, scope.clone()) {
                    Ok(skill) => {
                        if !skills.iter().any(|s| s.name == skill.name) {
                            skills.push(skill);
                            count += 1;
                        } else {
                            debug!("Skipping duplicate skill: {}", skill.name);
                        }
                    }
                    Err(e) => {
                        errors.push(format!("Failed to load skill at {:?}: {}", path, e));
                    }
                }
            }
        }

        Ok(count)
    }

    /// Load a single skill from a SKILL.md file
    fn load_skill(&self, path: &Path, scope: SkillScope) -> Result<Skill> {
        let content = tokio::fs::read_to_string(path).await?;
        
        let (frontmatter, body) = parse_frontmatter(&content)
            .context("Failed to parse skill frontmatter")?;

        let skill = Skill {
            name: frontmatter.name,
            description: frontmatter.description,
            content: body,
            path: path.to_path_buf(),
            directory: path.parent().map(|p| p.to_path_buf()).unwrap_or_default(),
            builtin: scope == SkillScope::BuiltIn,
        };

        Ok(skill)
    }

    /// Discover built-in skills
    fn discover_builtin(&self, skills: &mut Vec<Skill>) {
        debug!("Built-in skills discovery (placeholder)");
    }

    /// Find a skill by name
    pub fn find_skill(&self, name: &str, result: &SkillDiscoveryResult) -> Option<&Skill> {
        result.skills.iter().find(|s| s.name == name)
    }

    /// Get skills matching a pattern
    pub fn find_by_pattern(&self, pattern: &str, result: &SkillDiscoveryResult) -> Vec<&Skill> {
        result.skills.iter()
            .filter(|s| s.name.contains(pattern) || s.description.contains(pattern))
            .collect()
    }
}

/// Parse YAML frontmatter from a skill file
fn parse_frontmatter(content: &str) -> Result<(SkillFrontmatter, String)> {
    // Look for frontmatter delimiters
    let pattern = regex::Regex::new(r"(?m)^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)").unwrap();
    
    if let Some(caps) = pattern.captures(content) {
        let frontmatter_yaml = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let body = &content[caps.get(0).map(|m| m.end()).unwrap_or(0)..];

        // Parse YAML using yaml-rust
        let docs = yaml_rust::YamlLoader::load_from_str(frontmatter_yaml)
            .context("Failed to parse YAML frontmatter")?;
        
        let frontmatter_doc = docs.into_iter().next()
            .ok_or_else(|| anyhow::anyhow!("Empty frontmatter"))?;
        
        let hash = frontmatter_doc.as_hash()
            .ok_or_else(|| anyhow::anyhow!("Frontmatter is not a hash"))?;

        let name = extract_string(hash, "name")?;
        let description = extract_string(hash, "description")?;
        let tags = extract_vec_string(hash, "tags");
        let version = extract_string_opt(hash, "version");
        let author = extract_string_opt(hash, "author");
        let dependencies = extract_vec_string_opt(hash, "dependencies");

        let frontmatter = SkillFrontmatter {
            name,
            description,
            tags,
            version,
            author,
            dependencies,
        };

        Ok((frontmatter, body.to_string()))
    } else {
        let name = path::Path::new(content)
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_else(|| "unnamed".to_string());
        
        let frontmatter = SkillFrontmatter {
            name: name.clone(),
            description: name.clone(),
            tags: None,
            version: None,
            author: None,
            dependencies: None,
        };

        Ok((frontmatter, content.to_string()))
    }
}

fn extract_string(hash: &yaml_rust::yaml::Hash, key: &str) -> Result<String> {
    hash.get(&yaml_rust::yaml::Yaml::String(key.to_string()))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| anyhow::anyhow!("Missing required field: {}", key))
}

fn extract_string_opt(hash: &yaml_rust::yaml::Hash, key: &str) -> Option<String> {
    hash.get(&yaml_rust::yaml::Yaml::String(key.to_string()))
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn extract_vec_string(hash: &yaml_rust::yaml::Hash, key: &str) -> Option<Vec<String>> {
    hash.get(&yaml_rust::yaml::Yaml::String(key.to_string()))
        .and_then(|v| v.as_vec())
        .map(|vec| {
            vec.iter()
                .filter_map(|v| v.as_str())
                .map(|s| s.to_string())
                .collect()
        })
}

fn extract_vec_string_opt(hash: &yaml_rust::yaml::Hash, key: &str) -> Option<Vec<String>> {
    extract_vec_string(hash, key)
}
