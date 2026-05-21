use crate::config::app_root;
use crate::{ReverieError, ReverieResult};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio::process::Command;
use tokio::time::timeout;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimePluginCommandSpec {
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub parameters: Value,
    #[serde(default)]
    pub expose_as_tool: bool,
    #[serde(default)]
    pub include_modes: Vec<String>,
    #[serde(default)]
    pub exclude_modes: Vec<String>,
    #[serde(default)]
    pub guidance: String,
    #[serde(default)]
    pub example: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimePluginSpec {
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub entry: Option<String>,
    #[serde(default)]
    pub commands: Vec<RuntimePluginCommandSpec>,
    #[serde(default)]
    pub raw: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimePluginRecord {
    pub spec: RuntimePluginSpec,
    pub root: PathBuf,
    pub manifest_path: PathBuf,
    pub entry_path: Option<PathBuf>,
    pub ready: bool,
    pub dynamic_tools: Vec<RuntimePluginDynamicTool>,
    #[serde(default)]
    pub handshake: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimePluginDynamicTool {
    pub name: String,
    pub plugin_id: String,
    pub command: String,
    pub description: String,
    pub parameters: Value,
    #[serde(default)]
    pub include_modes: Vec<String>,
    #[serde(default)]
    pub exclude_modes: Vec<String>,
    #[serde(default)]
    pub guidance: String,
    #[serde(default)]
    pub example: String,
    #[serde(default)]
    pub qualified_name: String,
}

#[derive(Debug, Clone)]
pub struct RuntimePluginManager {
    roots: Vec<PathBuf>,
}

impl RuntimePluginManager {
    pub fn new(project_root: impl AsRef<Path>) -> Self {
        let project_root = project_root.as_ref();
        Self {
            roots: vec![
                project_root.join(".reverie").join("plugins"),
                app_root().join("plugins"),
                project_root
                    .parent()
                    .unwrap_or(project_root)
                    .join("plugins"),
            ],
        }
    }

    pub fn roots(&self) -> &[PathBuf] {
        &self.roots
    }

    pub fn list_plugins(&self) -> ReverieResult<Vec<RuntimePluginRecord>> {
        let mut records = Vec::new();
        for root in &self.roots {
            if !root.is_dir() {
                continue;
            }
            for entry in std::fs::read_dir(root)? {
                let entry = entry?;
                let plugin_root = entry.path();
                if !plugin_root.is_dir() {
                    continue;
                }
                let manifest_path = plugin_root.join("plugin.json");
                if !manifest_path.is_file() {
                    continue;
                }
                let raw_text = std::fs::read_to_string(&manifest_path)?;
                let raw: Value = serde_json::from_str(&raw_text)?;
                let spec = RuntimePluginSpec {
                    id: raw
                        .get("id")
                        .or_else(|| raw.get("name"))
                        .and_then(Value::as_str)
                        .unwrap_or_else(|| {
                            plugin_root
                                .file_name()
                                .and_then(|v| v.to_str())
                                .unwrap_or("plugin")
                        })
                        .to_string(),
                    name: raw
                        .get("name")
                        .or_else(|| raw.get("display_name"))
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    version: raw
                        .get("version")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    description: raw
                        .get("description")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    entry: resolve_entry_value(&raw),
                    commands: parse_commands(&raw),
                    raw,
                };
                let entry_path = spec.entry.as_ref().map(|entry| plugin_root.join(entry));
                let ready = entry_path
                    .as_ref()
                    .map(|path| path.exists())
                    .unwrap_or(true);
                let dynamic_tools = dynamic_tools_for_commands(
                    &spec.id,
                    if spec.name.is_empty() {
                        &spec.id
                    } else {
                        &spec.name
                    },
                    &spec.commands,
                    &mut HashSet::new(),
                );
                records.push(RuntimePluginRecord {
                    spec,
                    root: plugin_root,
                    manifest_path,
                    entry_path,
                    ready,
                    dynamic_tools,
                    handshake: None,
                });
            }
        }
        records.sort_by(|a, b| a.spec.id.cmp(&b.spec.id));
        Ok(records)
    }

    pub async fn list_plugins_with_handshakes(&self) -> ReverieResult<Vec<RuntimePluginRecord>> {
        let mut records = self.list_plugins()?;
        for record in &mut records {
            if !record.ready || record.entry_path.is_none() {
                continue;
            }
            let handshake = self.handshake(&record.spec.id).await?;
            let commands = commands_from_handshake(&handshake);
            if !commands.is_empty() {
                record.dynamic_tools = dynamic_tools_for_commands(
                    &record.spec.id,
                    if record.spec.name.is_empty() {
                        &record.spec.id
                    } else {
                        &record.spec.name
                    },
                    &commands,
                    &mut HashSet::new(),
                );
            }
            record.handshake = Some(handshake);
        }
        Ok(records)
    }

    pub fn find_plugin(&self, plugin_id: &str) -> ReverieResult<Option<RuntimePluginRecord>> {
        Ok(self
            .list_plugins()?
            .into_iter()
            .find(|record| record.spec.id == plugin_id || record.spec.name == plugin_id))
    }

    pub async fn call_command(
        &self,
        plugin_id: &str,
        command_name: &str,
        payload: Value,
    ) -> ReverieResult<Value> {
        let record = self
            .find_plugin(plugin_id)?
            .ok_or_else(|| ReverieError::InvalidInput(format!("plugin not found: {plugin_id}")))?;
        let entry = record.entry_path.clone().ok_or_else(|| {
            ReverieError::InvalidInput(format!("plugin has no executable entry: {plugin_id}"))
        })?;
        if !entry.is_file() {
            return Err(ReverieError::InvalidInput(format!(
                "plugin entry is missing: {}",
                entry.display()
            )));
        }

        let output = timeout(
            Duration::from_secs(60),
            plugin_command(&entry, &record.root, &record.spec.id)
                .arg("-RC-CALL")
                .arg(command_name)
                .arg(serde_json::to_string(&payload)?)
                .output(),
        )
        .await
        .map_err(|_| {
            ReverieError::InvalidInput(format!(
                "plugin command timed out: {plugin_id}.{command_name}"
            ))
        })??;
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let parsed_stdout = serde_json::from_str::<Value>(stdout.trim()).unwrap_or_else(|_| {
            json!({
                "stdout": stdout
            })
        });
        Ok(json!({
            "plugin_id": plugin_id,
            "command": command_name,
            "success": output.status.success(),
            "exit_code": output.status.code(),
            "stdout": parsed_stdout,
            "stderr": stderr
        }))
    }

    pub async fn handshake(&self, plugin_id: &str) -> ReverieResult<Value> {
        let record = self
            .find_plugin(plugin_id)?
            .ok_or_else(|| ReverieError::InvalidInput(format!("plugin not found: {plugin_id}")))?;
        let entry = record.entry_path.clone().ok_or_else(|| {
            ReverieError::InvalidInput(format!("plugin has no executable entry: {plugin_id}"))
        })?;
        let output = timeout(
            Duration::from_secs(10),
            plugin_command(&entry, &record.root, &record.spec.id)
                .arg("-RC")
                .output(),
        )
        .await
        .map_err(|_| {
            ReverieError::InvalidInput(format!("plugin handshake timed out: {plugin_id}"))
        })??;
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        if !output.status.success() {
            return Ok(json!({
                "success": false,
                "exit_code": output.status.code(),
                "stdout": stdout,
                "stderr": stderr
            }));
        }
        Ok(serde_json::from_str(stdout.trim()).unwrap_or_else(|_| {
            json!({
                "success": true,
                "stdout": stdout,
                "stderr": stderr
            })
        }))
    }

    pub async fn dynamic_tools(&self) -> ReverieResult<Vec<RuntimePluginDynamicTool>> {
        let mut tools = Vec::new();
        let mut used_names = HashSet::new();
        for record in self.list_plugins_with_handshakes().await? {
            for mut tool in record.dynamic_tools {
                if used_names.contains(&tool.name) {
                    tool.name = unique_name(&tool.name, &mut used_names);
                } else {
                    used_names.insert(tool.name.clone());
                }
                tools.push(tool);
            }
        }
        Ok(tools)
    }
}

fn parse_commands(raw: &Value) -> Vec<RuntimePluginCommandSpec> {
    raw.get("commands")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|item| {
            if let Some(name) = item.as_str() {
                return Some(RuntimePluginCommandSpec {
                    name: name.to_string(),
                    description: String::new(),
                    parameters: json!({"type": "object", "properties": {}, "required": []}),
                    expose_as_tool: true,
                    include_modes: Vec::new(),
                    exclude_modes: Vec::new(),
                    guidance: String::new(),
                    example: String::new(),
                });
            }
            Some(RuntimePluginCommandSpec {
                name: sanitize_identifier(item.get("name")?.as_str()?),
                description: item
                    .get("description")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                parameters: item
                    .get("parameters")
                    .cloned()
                    .unwrap_or_else(|| json!({"type": "object", "properties": {}, "required": []})),
                expose_as_tool: item
                    .get("expose_as_tool")
                    .and_then(Value::as_bool)
                    .unwrap_or(true),
                include_modes: parse_mode_list(item.get("include_modes")),
                exclude_modes: parse_mode_list(item.get("exclude_modes")),
                guidance: item
                    .get("guidance")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                example: item
                    .get("example")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
            })
        })
        .collect()
}

fn resolve_entry_value(raw: &Value) -> Option<String> {
    let entry = raw.get("entry").or_else(|| raw.get("main"))?;
    if let Some(value) = entry.as_str() {
        return Some(value.to_string());
    }
    let os_key = if cfg!(windows) {
        "windows"
    } else if cfg!(target_os = "macos") {
        "darwin"
    } else {
        "linux"
    };
    entry
        .pointer(&format!("/preferred/{os_key}"))
        .or_else(|| entry.pointer("/preferred/default"))
        .or_else(|| entry.pointer(&format!("/fallbacks/{os_key}")))
        .or_else(|| entry.pointer("/fallbacks/default"))
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn commands_from_handshake(handshake: &Value) -> Vec<RuntimePluginCommandSpec> {
    handshake
        .get("commands")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|item| {
            Some(RuntimePluginCommandSpec {
                name: sanitize_identifier(
                    item.get("name")
                        .or_else(|| item.get("id"))
                        .and_then(Value::as_str)?,
                ),
                description: item
                    .get("description")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                parameters: normalize_parameters(item.get("parameters").cloned()),
                expose_as_tool: item
                    .get("expose_as_tool")
                    .and_then(Value::as_bool)
                    .unwrap_or(true),
                include_modes: parse_mode_list(item.get("include_modes")),
                exclude_modes: parse_mode_list(item.get("exclude_modes")),
                guidance: item
                    .get("guidance")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                example: item
                    .get("example")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
            })
        })
        .collect()
}

fn dynamic_tools_for_commands(
    plugin_id: &str,
    plugin_display_name: &str,
    commands: &[RuntimePluginCommandSpec],
    used_names: &mut HashSet<String>,
) -> Vec<RuntimePluginDynamicTool> {
    commands
        .iter()
        .filter(|command| command.expose_as_tool)
        .map(|command| {
            let name = build_runtime_tool_name(plugin_id, &command.name, used_names);
            RuntimePluginDynamicTool {
                name,
                plugin_id: plugin_id.to_string(),
                command: command.name.clone(),
                description: format!(
                    "{} [plugin={}, runtime={}, protocol=RC]",
                    command.description, plugin_id, plugin_display_name
                )
                .trim()
                .to_string(),
                parameters: command.parameters.clone(),
                include_modes: command.include_modes.clone(),
                exclude_modes: command.exclude_modes.clone(),
                guidance: command.guidance.clone(),
                example: command.example.clone(),
                qualified_name: format!("{}.{}", plugin_id, command.name),
            }
        })
        .collect()
}

fn normalize_parameters(raw: Option<Value>) -> Value {
    let Some(Value::Object(mut map)) = raw else {
        return json!({"type": "object", "properties": {}, "required": []});
    };
    if !matches!(map.get("type").and_then(Value::as_str), Some("object")) {
        map.insert("type".to_string(), Value::String("object".to_string()));
    }
    if !matches!(map.get("properties"), Some(Value::Object(_))) {
        map.insert("properties".to_string(), json!({}));
    }
    if !matches!(map.get("required"), Some(Value::Array(_))) {
        map.insert("required".to_string(), json!([]));
    }
    Value::Object(map)
}

fn parse_mode_list(raw: Option<&Value>) -> Vec<String> {
    raw.and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect()
}

fn sanitize_identifier(value: &str) -> String {
    let mut out = String::new();
    let mut last_was_sep = false;
    for ch in value.trim().to_lowercase().chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch);
            last_was_sep = false;
        } else if !last_was_sep {
            out.push('_');
            last_was_sep = true;
        }
    }
    let trimmed = out.trim_matches('_').to_string();
    if trimmed.is_empty() {
        "plugin".to_string()
    } else {
        trimmed
    }
}

fn build_runtime_tool_name(
    plugin_id: &str,
    command_name: &str,
    used_names: &mut HashSet<String>,
) -> String {
    let base = format!(
        "rc_{}_{}",
        sanitize_identifier(plugin_id),
        sanitize_identifier(command_name)
    );
    unique_name(&base, used_names)
}

fn unique_name(base: &str, used_names: &mut HashSet<String>) -> String {
    if used_names.insert(base.to_string()) {
        return base.to_string();
    }
    let mut suffix = 2;
    loop {
        let candidate = format!("{base}_{suffix}");
        if used_names.insert(candidate.clone()) {
            return candidate;
        }
        suffix += 1;
    }
}

fn plugin_command(entry: &Path, cwd: &Path, plugin_id: &str) -> Command {
    if entry
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.eq_ignore_ascii_case("py"))
        .unwrap_or(false)
    {
        let mut command = Command::new("python");
        command.arg(entry);
        command.current_dir(cwd);
        configure_plugin_env(&mut command, cwd, plugin_id);
        command
    } else if entry
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.eq_ignore_ascii_case("cmd") || ext.eq_ignore_ascii_case("bat"))
        .unwrap_or(false)
    {
        let mut command = Command::new("cmd.exe");
        command.arg("/d").arg("/c").arg(entry);
        command.current_dir(cwd);
        configure_plugin_env(&mut command, cwd, plugin_id);
        command
    } else if entry
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.eq_ignore_ascii_case("ps1"))
        .unwrap_or(false)
    {
        let mut command = Command::new("powershell");
        command
            .arg("-NoProfile")
            .arg("-ExecutionPolicy")
            .arg("Bypass")
            .arg("-File")
            .arg(entry);
        command.current_dir(cwd);
        configure_plugin_env(&mut command, cwd, plugin_id);
        command
    } else {
        let mut command = Command::new(entry);
        command.current_dir(cwd);
        configure_plugin_env(&mut command, cwd, plugin_id);
        command
    }
}

fn configure_plugin_env(command: &mut Command, cwd: &Path, plugin_id: &str) {
    command.env("REVERIE_PLUGIN_ROOT", cwd);
    let normalized = sanitize_identifier(plugin_id);
    if !normalized.is_empty() {
        command.env(
            format!("REVERIE_{}_PLUGIN_ROOT", normalized.to_uppercase()),
            cwd,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn handshake_commands_become_dynamic_tools() {
        let handshake = json!({
            "commands": [{
                "name": "Status Check",
                "description": "Return runtime health.",
                "parameters": {"type": "string"},
                "expose_as_tool": true,
                "include_modes": ["reverie-gamer"],
                "guidance": "Use after deploy."
            }]
        });
        let commands = commands_from_handshake(&handshake);
        let tools = dynamic_tools_for_commands(
            "sample-runtime",
            "Sample Runtime",
            &commands,
            &mut HashSet::new(),
        );
        assert_eq!(tools[0].name, "rc_sample_runtime_status_check");
        assert_eq!(tools[0].parameters["type"], "object");
        assert_eq!(tools[0].include_modes, vec!["reverie-gamer"]);
    }

    #[tokio::test]
    async fn manifest_plugin_commands_are_listed_without_handshake() {
        let temp = TempDir::new().unwrap();
        let plugin_root = temp.path().join(".reverie/plugins/sample");
        std::fs::create_dir_all(&plugin_root).unwrap();
        std::fs::write(
            plugin_root.join("plugin.json"),
            serde_json::to_string(&json!({
                "id": "sample",
                "commands": [{
                    "name": "ping",
                    "description": "Ping.",
                    "expose_as_tool": true
                }]
            }))
            .unwrap(),
        )
        .unwrap();
        let tools = RuntimePluginManager::new(temp.path())
            .dynamic_tools()
            .await
            .unwrap();
        assert!(tools.iter().any(|tool| tool.name == "rc_sample_ping"));
    }
}
