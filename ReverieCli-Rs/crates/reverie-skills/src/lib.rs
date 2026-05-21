//! Skill discovery and execution system for Reverie CLI.
//!
//! Skills are Codex-style reusable workflow definitions stored in SKILL.md files
//! with YAML frontmatter. They provide structured guidance for multi-step tasks.

pub mod discovery;
pub mod executor;
pub mod loader;
pub mod types;

pub use discovery::SkillDiscovery;
pub use executor::SkillExecutor;
pub use loader::SkillLoader;
pub use types::*;
