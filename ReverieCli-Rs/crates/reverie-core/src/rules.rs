use crate::config::{app_root, project_data_dir};
use crate::{ReverieError, ReverieResult};
use serde_json::Value;
use std::path::{Path, PathBuf};

const EXAMPLE_RULES: &str = r#"# Reverie Custom Rules
# Each line is a separate rule that will be added to the system prompt
# Lines starting with # are comments and will be ignored
# Empty lines are also ignored

# Example rules (uncomment to use):
# Always use type hints in function definitions
# Follow PEP 8 style guidelines
# Prefer concise final summaries unless I ask for a deep walkthrough
# Use detailed implementation explanations only when I explicitly ask for them
# Add unit tests for new features
"#;

#[derive(Debug, Clone)]
pub struct RulesManager {
    project_root: PathBuf,
    app_root: PathBuf,
}

#[derive(Debug, Clone)]
struct RulePaths {
    rules_txt: PathBuf,
    rules_json: PathBuf,
    legacy_rules_txt: PathBuf,
    legacy_rules_json: PathBuf,
    workspace_rules_txt: PathBuf,
}

impl RulesManager {
    pub fn new(project_root: impl AsRef<Path>) -> Self {
        Self::new_with_app_root(project_root, app_root())
    }

    pub fn new_with_app_root(project_root: impl AsRef<Path>, app_root: impl AsRef<Path>) -> Self {
        Self {
            project_root: project_root.as_ref().to_path_buf(),
            app_root: app_root.as_ref().to_path_buf(),
        }
    }

    pub fn rules_txt_path(&self) -> PathBuf {
        self.paths().rules_txt
    }

    pub fn get_rules(&self) -> ReverieResult<Vec<String>> {
        let paths = self.paths();
        if paths.rules_txt.is_file() {
            return read_rules_text_file(&paths.rules_txt);
        }
        if paths.legacy_rules_txt.is_file() {
            let rules = read_rules_text_file(&paths.legacy_rules_txt)?;
            self.save_rules(&rules)?;
            return Ok(rules);
        }
        if paths.rules_json.is_file() {
            let rules = read_rules_json_file(&paths.rules_json)?;
            self.save_rules(&rules)?;
            return Ok(rules);
        }
        if paths.legacy_rules_json.is_file() {
            let rules = read_rules_json_file(&paths.legacy_rules_json)?;
            self.save_rules(&rules)?;
            return Ok(rules);
        }
        if paths.workspace_rules_txt.is_file() {
            let rules = read_rules_text_file(&paths.workspace_rules_txt)?;
            self.save_rules(&rules)?;
            return Ok(rules);
        }

        self.create_example_file()?;
        Ok(Vec::new())
    }

    pub fn get_rules_text(&self) -> ReverieResult<String> {
        Ok(self.get_rules()?.join("\n"))
    }

    pub fn set_rules(&self, rules: &[String]) -> ReverieResult<()> {
        self.save_rules(&normalize_rules(rules.iter().map(String::as_str)))
    }

    pub fn add_rule(&self, rule: &str) -> ReverieResult<Vec<String>> {
        let mut rules = self.get_rules()?;
        let normalized = rule.trim();
        if !normalized.is_empty() && !rules.iter().any(|item| item == normalized) {
            rules.push(normalized.to_string());
            self.save_rules(&rules)?;
        }
        Ok(rules)
    }

    pub fn remove_rule(&self, one_based_index: usize) -> ReverieResult<(String, Vec<String>)> {
        let mut rules = self.get_rules()?;
        if one_based_index == 0 || one_based_index > rules.len() {
            return Err(ReverieError::InvalidInput(format!(
                "rule index out of range: {one_based_index}"
            )));
        }
        let removed = rules.remove(one_based_index - 1);
        self.save_rules(&rules)?;
        Ok((removed, rules))
    }

    fn create_example_file(&self) -> ReverieResult<()> {
        let path = self.rules_txt_path();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        if !path.exists() {
            std::fs::write(path, EXAMPLE_RULES)?;
        }
        Ok(())
    }

    fn save_rules(&self, rules: &[String]) -> ReverieResult<()> {
        let path = self.rules_txt_path();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let content = if rules.is_empty() {
            String::new()
        } else {
            format!("{}\n", rules.join("\n"))
        };
        std::fs::write(path, content)?;
        Ok(())
    }

    fn paths(&self) -> RulePaths {
        let project_data = project_data_dir_with_app_root(&self.project_root, &self.app_root);
        let legacy_dir = self.app_root.join(".reverie");
        RulePaths {
            rules_txt: project_data.join("rules.txt"),
            rules_json: project_data.join("rules.json"),
            legacy_rules_txt: legacy_dir.join("rules.txt"),
            legacy_rules_json: legacy_dir.join("rules.json"),
            workspace_rules_txt: self.project_root.join(".reverie").join("rules.txt"),
        }
    }
}

fn project_data_dir_with_app_root(project_root: &Path, app_root: &Path) -> PathBuf {
    if app_root == crate::config::app_root() {
        return project_data_dir(project_root);
    }
    app_root
        .join(".reverie")
        .join("projects")
        .join(crate::config::project_data_name(project_root))
}

fn read_rules_text_file(path: &Path) -> ReverieResult<Vec<String>> {
    Ok(normalize_rules(
        std::fs::read_to_string(path)?
            .lines()
            .map(str::trim)
            .filter(|line| !line.starts_with('#')),
    ))
}

fn read_rules_json_file(path: &Path) -> ReverieResult<Vec<String>> {
    let raw = std::fs::read_to_string(path)?;
    let value: Value = serde_json::from_str(&raw)?;
    let Some(items) = value.as_array() else {
        return Ok(Vec::new());
    };
    Ok(normalize_rules(items.iter().filter_map(Value::as_str)))
}

fn normalize_rules<'a>(rules: impl IntoIterator<Item = &'a str>) -> Vec<String> {
    let mut normalized = Vec::new();
    for rule in rules {
        let trimmed = rule.trim();
        if trimmed.is_empty() || normalized.iter().any(|item| item == trimmed) {
            continue;
        }
        normalized.push(trimmed.to_string());
    }
    normalized
}

pub fn render_rules(rules: &[String]) -> String {
    if rules.is_empty() {
        return "No custom rules defined.".to_string();
    }
    rules
        .iter()
        .enumerate()
        .map(|(index, rule)| format!("{}. {}", index + 1, rule))
        .collect::<Vec<_>>()
        .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn creates_example_without_activating_comment_rules() {
        let temp = TempDir::new().unwrap();
        let project = temp.path().join("project");
        std::fs::create_dir_all(&project).unwrap();
        let app = temp.path().join("app-root");
        let manager = RulesManager::new_with_app_root(&project, &app);

        let rules = manager.get_rules().unwrap();

        assert!(rules.is_empty());
        assert!(manager.rules_txt_path().is_file());
        assert!(std::fs::read_to_string(manager.rules_txt_path())
            .unwrap()
            .contains("Reverie Custom Rules"));
    }

    #[test]
    fn migrates_legacy_json_rules_to_project_data_txt() {
        let temp = TempDir::new().unwrap();
        let project = temp.path().join("project");
        std::fs::create_dir_all(&project).unwrap();
        let app = temp.path().join("app-root");
        let legacy_dir = app.join(".reverie");
        std::fs::create_dir_all(&legacy_dir).unwrap();
        std::fs::write(
            legacy_dir.join("rules.json"),
            serde_json::to_string(&vec!["Run tests", "Keep summaries short"]).unwrap(),
        )
        .unwrap();
        let manager = RulesManager::new_with_app_root(&project, &app);

        let rules = manager.get_rules().unwrap();

        assert_eq!(rules, vec!["Run tests", "Keep summaries short"]);
        assert_eq!(
            std::fs::read_to_string(manager.rules_txt_path()).unwrap(),
            "Run tests\nKeep summaries short\n"
        );
    }

    #[test]
    fn add_and_remove_rules_are_persisted() {
        let temp = TempDir::new().unwrap();
        let project = temp.path().join("project");
        std::fs::create_dir_all(&project).unwrap();
        let app = temp.path().join("app-root");
        let manager = RulesManager::new_with_app_root(&project, &app);

        manager.add_rule("Run tests").unwrap();
        manager.add_rule("Run tests").unwrap();
        let (removed, rules) = manager.remove_rule(1).unwrap();

        assert_eq!(removed, "Run tests");
        assert!(rules.is_empty());
        assert_eq!(manager.get_rules().unwrap(), Vec::<String>::new());
    }
}
