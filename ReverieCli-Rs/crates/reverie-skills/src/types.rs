//! Skill types and data structures.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// A skill definition loaded from a SKILL.md file
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Skill {
    /// Unique skill identifier (from frontmatter)
    pub name: String,
    /// Human-readable description (from frontmatter)
    pub description: String,
    /// Full skill content (markdown body)
    pub content: String,
    /// Path to the SKILL.md file
    pub path: PathBuf,
    /// Parent directory of the skill
    pub directory: PathBuf,
    /// Whether this is a built-in skill
    #[serde(default)]
    pub builtin: bool,
}

/// Frontmatter extracted from SKILL.md
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillFrontmatter {
    /// Skill name
    pub name: String,
    /// Skill description
    pub description: String,
    /// Optional tags
    #[serde(default)]
    pub tags: Option<Vec<String>>,
    /// Optional version
    #[serde(default)]
    pub version: Option<String>,
    /// Optional author
    #[serde(default)]
    pub author: Option<String>,
    /// Optional dependencies on other skills
    #[serde(default)]
    pub dependencies: Option<Vec<String>>,
}

/// Skill discovery scope
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SkillScope {
    /// Current directory: ./.agents/skills/
    Current,
    /// Parent directory: ../.agents/skills/
    Parent,
    /// Repository root: $REPO_ROOT/.agents/skills/
    Repository,
    /// User home: $HOME/.agents/skills/
    User,
    /// System-wide: /etc/codex/skills/
    System,
    /// Built-in bundled with Reverie
    BuiltIn,
}

impl SkillScope {
    /// Get the directory path for this scope
    pub fn path(&self, project_root: &Path, user_home: &Path) -> Option<PathBuf> {
        match self {
            SkillScope::Current => Some(PathBuf::from("./.agents/skills")),
            SkillScope::Parent => Some(PathBuf::from("../.agents/skills")),
            SkillScope::Repository => Some(project_root.join(".agents/skills")),
            SkillScope::User => Some(user_home.join(".agents/skills")),
            SkillScope::System => Some(PathBuf::from("/etc/codex/skills")),
            SkillScope::BuiltIn => None,
        }
    }
}

/// Result of skill discovery
#[derive(Debug, Clone)]
pub struct SkillDiscoveryResult {
    /// Discovered skills
    pub skills: Vec<Skill>,
    /// Errors encountered during discovery
    pub errors: Vec<String>,
}

/// Skill invocation context
#[derive(Debug, Clone)]
pub struct SkillInvocationContext {
    /// Project root path
    pub project_root: PathBuf,
    /// Current working directory
    pub cwd: PathBuf,
    /// Skill name being invoked
    pub skill_name: String,
    /// Arguments passed to the skill
    pub arguments: std::collections::HashMap<String, String>,
}
