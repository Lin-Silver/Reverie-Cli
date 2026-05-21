use crate::agent::{AgentOptions, ReverieAgent};
use crate::cli_commands::command_catalog;
use crate::config::{app_root, ConfigManager};
use crate::modes::normalize_mode;
use crate::providers::{codex_catalog, modelscope_catalog, nvidia_catalog};
use crate::session::{CheckpointStore, OperationStore, SessionStore};
use crate::settings_catalog::{apply_setting, setting_items};
use crate::version::{version_line, VERSION};
use crate::ReverieResult;
use reverie_context::{CodebaseIndexer, ContextQuery};
use reverie_tools::ToolRegistry;
use serde_json::{json, Value};
use std::io::{BufRead, Write};
use std::path::PathBuf;
use std::time::Duration;
use tokio::process::Command;
use tokio::time::timeout;

pub fn normalize_jsonl_input(raw: &str) -> &str {
    raw.trim_start_matches('\u{feff}').trim()
}

pub struct ReverieUiBridge {
    project_root: PathBuf,
    mode: String,
}

impl Default for ReverieUiBridge {
    fn default() -> Self {
        Self {
            project_root: std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
            mode: "reverie".to_string(),
        }
    }
}

impl ReverieUiBridge {
    pub fn runtime_info(&self) -> Value {
        json!({
            "runtime": "rust",
            "version": VERSION,
            "version_line": version_line(),
            "app_root": app_root(),
            "project_root": self.project_root,
            "mode": self.mode,
            "python_runtime": false
        })
    }

    pub async fn handle(&mut self, frame: Value) -> Value {
        let id = frame.get("id").cloned().unwrap_or(Value::Null);
        let method = frame
            .get("method")
            .and_then(Value::as_str)
            .or_else(|| frame.get("type").and_then(Value::as_str))
            .or_else(|| frame.get("action").and_then(Value::as_str))
            .unwrap_or_default();
        let payload = frame.get("payload").cloned().unwrap_or_else(|| json!({}));

        let result = match method {
            "hello" | "runtime_info" | "locate_runtime" => Ok(self.runtime_info()),
            "initialize" => self.handle_initialize(payload),
            "get_state" => Ok(self.state()),
            "set_workspace" => self.handle_set_workspace(payload),
            "set_mode" => self.handle_set_mode(payload),
            "set_setting" => self.handle_set_setting(payload),
            "save_preferences" => self.handle_save_preferences(payload),
            "save_model"
            | "delete_model"
            | "select_model"
            | "save_builtin_source"
            | "select_builtin_source"
            | "test_providers" => Ok(json!({
                "accepted": true,
                "provider_catalogs": {
                    "nvidia": nvidia_catalog(),
                    "modelscope": modelscope_catalog(),
                    "codex": codex_catalog()
                }
            })),
            "new_session" => self.handle_new_session(payload),
            "list_sessions" | "switch_session" | "rename_session" | "delete_session"
            | "clear_session" => self.handle_session_command(method, payload),
            "create_checkpoint" | "list_checkpoints" | "restore_checkpoint" => {
                self.handle_checkpoint_command(method, payload)
            }
            "list_operations" => self.handle_operation_command(),
            "list_plugins" | "refresh_plugins" => {
                let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
                let plugins = manager
                    .list_plugins_with_handshakes()
                    .await
                    .unwrap_or_default();
                let dynamic_tools = plugins
                    .iter()
                    .flat_map(|plugin| plugin.dynamic_tools.clone())
                    .collect::<Vec<_>>();
                Ok(json!({
                    "plugins": plugins,
                    "dynamic_tools": dynamic_tools,
                    "templates": ["blender", "godot", "o3de", "game_models"],
                    "runtime": "rust"
                }))
            }
            "list_remote_releases" => Ok(json!({
                "releases": [],
                "message": "Remote release lookup is reserved for the Rust plugin manager."
            })),
            "install_remote_plugin" | "build_plugin" | "deploy_plugin" | "inspect_plugin" => {
                Ok(json!({
                    "accepted": true,
                    "message": "Plugin command accepted by compatibility bridge; execution is reserved for plugin manager parity."
                }))
            }
            "call_plugin_command" => self.handle_call_plugin_command(payload).await,
            "list_tools" => Ok(json!({
                "tools": ToolRegistry::builtin().visible_for_mode(&self.mode),
                "dynamic_tools": crate::plugins::RuntimePluginManager::new(&self.project_root).dynamic_tools().await.unwrap_or_default()
            })),
            "list_commands" => Ok(json!({
                "commands": command_catalog()
            })),
            "list_settings" => Ok(json!({
                "settings": setting_items()
            })),
            "gitStatus" | "git_status" => self.handle_git_status(payload).await,
            "diagnostics" => Ok(json!({
                "ok": true,
                "runtime": "rust",
                "project_root": self.project_root,
                "plugins": crate::plugins::RuntimePluginManager::new(&self.project_root).list_plugins_with_handshakes().await.unwrap_or_default(),
                "harness": crate::harness::build_harness_capability_report(&self.project_root).ok()
            })),
            "index_workspace" => self.handle_index_workspace(),
            "query_context" | "context_query" => self.handle_context_query(payload),
            "chat" => self.handle_chat(payload).await,
            "shutdown" => Ok(json!({"shutdown": true})),
            _ if method.starts_with("rc_") => {
                self.handle_dynamic_plugin_tool(method, payload).await
            }
            _ => Ok(json!({
                "ok": false,
                "unsupported": method,
                "message": "Handler is reserved for Rust parity work."
            })),
        };

        match result {
            Ok(value) => json!({"id": id, "ok": true, "result": value}),
            Err(err) => json!({"id": id, "ok": false, "error": err.to_string()}),
        }
    }

    fn handle_initialize(&mut self, payload: Value) -> ReverieResult<Value> {
        if let Some(path) = payload.get("project_root").and_then(Value::as_str) {
            self.project_root = PathBuf::from(path);
        }
        if let Some(mode) = payload.get("mode").and_then(Value::as_str) {
            self.mode = normalize_mode(mode).canonical().to_string();
        }
        let config = ConfigManager::new(&self.project_root, false).load()?;
        Ok(json!({
            "state": self.state(),
            "config": config,
            "providers": {
                "nvidia": nvidia_catalog(),
                "modelscope": modelscope_catalog(),
                "codex": codex_catalog()
            }
        }))
    }

    fn state(&self) -> Value {
        json!({
            "project_root": self.project_root,
            "mode": self.mode,
            "runtime": "rust",
            "version": VERSION
        })
    }

    fn handle_set_workspace(&mut self, payload: Value) -> ReverieResult<Value> {
        let path = payload
            .get("project_root")
            .or_else(|| payload.get("path"))
            .and_then(Value::as_str)
            .unwrap_or(".");
        self.project_root = PathBuf::from(path).canonicalize()?;
        Ok(self.state())
    }

    fn handle_set_mode(&mut self, payload: Value) -> ReverieResult<Value> {
        let mode = payload
            .get("mode")
            .and_then(Value::as_str)
            .unwrap_or("reverie");
        self.mode = normalize_mode(mode).canonical().to_string();
        Ok(self.state())
    }

    fn handle_set_setting(&mut self, payload: Value) -> ReverieResult<Value> {
        let id = payload
            .get("id")
            .or_else(|| payload.get("setting"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        let value = payload.get("value").cloned().unwrap_or(Value::Null);
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        apply_setting(&mut config, id, value)?;
        if id.eq_ignore_ascii_case("mode") {
            self.mode = config.active_mode.clone();
        }
        manager.save(&config)?;
        Ok(json!({"config": config, "state": self.state()}))
    }

    fn handle_save_preferences(&mut self, payload: Value) -> ReverieResult<Value> {
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        if let Some(object) = payload.as_object() {
            for (id, value) in object {
                let _ = apply_setting(&mut config, id, value.clone());
            }
        }
        self.mode = config.active_mode.clone();
        manager.save(&config)?;
        Ok(json!({"config": config, "state": self.state()}))
    }

    fn handle_index_workspace(&self) -> ReverieResult<Value> {
        let result = CodebaseIndexer::new(&self.project_root)
            .with_cache_dir(
                crate::config::project_data_dir(&self.project_root).join("context_cache"),
            )
            .full_index()?;
        Ok(serde_json::to_value(result)?)
    }

    fn handle_context_query(&self, payload: Value) -> ReverieResult<Value> {
        let query = ContextQuery {
            query_type: payload
                .get("query_type")
                .and_then(Value::as_str)
                .unwrap_or("search")
                .to_string(),
            query: payload
                .get("query")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            limit: payload
                .get("limit")
                .and_then(Value::as_u64)
                .map(|value| value as usize),
        };
        let result = CodebaseIndexer::new(&self.project_root)
            .with_cache_dir(
                crate::config::project_data_dir(&self.project_root).join("context_cache"),
            )
            .query(query)?;
        Ok(serde_json::to_value(result)?)
    }

    fn handle_new_session(&self, payload: Value) -> ReverieResult<Value> {
        let title = payload
            .get("title")
            .or_else(|| payload.get("name"))
            .and_then(Value::as_str)
            .unwrap_or("Session");
        let store =
            SessionStore::new(crate::config::project_data_dir(&self.project_root).join("sessions"));
        let record = store.create(title, self.project_root.clone(), self.mode.clone())?;
        Ok(json!({"session": record, "sessions": store.list()?}))
    }

    fn handle_session_command(&self, method: &str, _payload: Value) -> ReverieResult<Value> {
        let store =
            SessionStore::new(crate::config::project_data_dir(&self.project_root).join("sessions"));
        Ok(json!({
            "method": method,
            "sessions": store.list()?,
            "message": "Rust session index is available; mutation command parity is still migrating."
        }))
    }

    fn handle_checkpoint_command(&self, method: &str, payload: Value) -> ReverieResult<Value> {
        let store = CheckpointStore::new(
            crate::config::project_data_dir(&self.project_root).join("checkpoints"),
        );
        match method {
            "create_checkpoint" => {
                let label = payload
                    .get("label")
                    .and_then(Value::as_str)
                    .unwrap_or("Checkpoint");
                let paths = payload
                    .get("paths")
                    .and_then(Value::as_array)
                    .map(|items| {
                        items
                            .iter()
                            .filter_map(Value::as_str)
                            .map(PathBuf::from)
                            .collect::<Vec<_>>()
                    })
                    .unwrap_or_default();
                let checkpoint = store.create(&self.project_root, label, &paths)?;
                Ok(json!({"checkpoint": checkpoint, "checkpoints": store.list()?}))
            }
            "restore_checkpoint" => {
                let id = payload
                    .get("id")
                    .or_else(|| payload.get("checkpoint_id"))
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                let checkpoint = store.restore(&self.project_root, id)?;
                Ok(json!({"restored": checkpoint}))
            }
            _ => Ok(json!({"checkpoints": store.list()?})),
        }
    }

    fn handle_operation_command(&self) -> ReverieResult<Value> {
        let store = OperationStore::new(
            crate::config::project_data_dir(&self.project_root).join("operations"),
        );
        Ok(json!({"operations": store.list()?}))
    }

    async fn handle_chat(&self, payload: Value) -> ReverieResult<Value> {
        let prompt = payload
            .get("prompt")
            .or_else(|| payload.get("message"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        let agent = ReverieAgent::new(
            &self.project_root,
            AgentOptions {
                mode: normalize_mode(&self.mode),
                no_index: payload
                    .get("no_index")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
            },
        );
        Ok(agent.run_prompt_once(prompt).await?.to_json_value())
    }

    async fn handle_git_status(&mut self, payload: Value) -> ReverieResult<Value> {
        let root = payload
            .get("projectRoot")
            .or_else(|| payload.get("project_root"))
            .or_else(|| payload.get("path"))
            .and_then(Value::as_str)
            .map(PathBuf::from);
        if let Some(root) = root {
            if root.is_dir() {
                self.project_root = root.canonicalize()?;
            }
        }
        Ok(json!({"git": git_status_summary(&self.project_root).await}))
    }

    async fn handle_call_plugin_command(&self, payload: Value) -> ReverieResult<Value> {
        let plugin_id = payload
            .get("plugin_id")
            .or_else(|| payload.get("pluginId"))
            .or_else(|| payload.get("id"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        let command_name = payload
            .get("command")
            .or_else(|| payload.get("command_name"))
            .or_else(|| payload.get("commandName"))
            .and_then(Value::as_str)
            .unwrap_or("run_task");
        let command_payload = payload
            .get("payload")
            .or_else(|| payload.get("arguments"))
            .cloned()
            .unwrap_or_else(|| json!({}));
        let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
        manager
            .call_command(plugin_id, command_name, command_payload)
            .await
    }

    async fn handle_dynamic_plugin_tool(
        &self,
        tool_name: &str,
        payload: Value,
    ) -> ReverieResult<Value> {
        let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
        let tools = manager.dynamic_tools().await?;
        let tool = tools
            .into_iter()
            .find(|item| item.name == tool_name)
            .ok_or_else(|| {
                crate::ReverieError::InvalidInput(format!("dynamic tool not found: {tool_name}"))
            })?;
        manager
            .call_command(&tool.plugin_id, &tool.command, payload)
            .await
    }
}

pub async fn git_status_summary(root: &std::path::Path) -> Value {
    let output = timeout(
        Duration::from_secs(5),
        Command::new("git")
            .arg("-C")
            .arg(root)
            .arg("status")
            .arg("--short")
            .arg("--branch")
            .output(),
    )
    .await;
    let output = match output {
        Ok(Ok(output)) => output,
        Ok(Err(err)) => {
            return json!({"available": false, "branch": "", "changes": [], "error": err.to_string()});
        }
        Err(_) => {
            return json!({"available": false, "branch": "", "changes": [], "error": "git status timed out"});
        }
    };
    if !output.status.success() {
        let error = String::from_utf8_lossy(if output.stderr.is_empty() {
            &output.stdout
        } else {
            &output.stderr
        })
        .trim()
        .to_string();
        return json!({"available": false, "branch": "", "changes": [], "error": error});
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let lines = stdout
        .lines()
        .map(str::trim_end)
        .filter(|line| !line.trim().is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    let branch = lines
        .first()
        .map(|line| line.strip_prefix("##").unwrap_or(line).trim().to_string())
        .unwrap_or_default();
    let changes = lines.into_iter().skip(1).collect::<Vec<_>>();
    json!({
        "available": true,
        "branch": branch,
        "changes": changes.iter().take(200).collect::<Vec<_>>(),
        "change_count": changes.len(),
        "dirty": !changes.is_empty()
    })
}

pub async fn run_sdk_bridge() -> ReverieResult<i32> {
    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout();
    let mut bridge = ReverieUiBridge::default();
    writeln!(
        stdout,
        "{}",
        serde_json::to_string(&json!({
            "type": "ready",
            "ok": true,
            "result": bridge.runtime_info()
        }))?
    )?;
    stdout.flush()?;
    for line in stdin.lock().lines() {
        let line = line?;
        let normalized = normalize_jsonl_input(&line);
        if normalized.is_empty() {
            continue;
        }
        let frame: Value = serde_json::from_str(normalized)?;
        let should_shutdown = frame
            .get("method")
            .and_then(Value::as_str)
            .or_else(|| frame.get("type").and_then(Value::as_str))
            .or_else(|| frame.get("action").and_then(Value::as_str))
            .map(|method| method == "shutdown")
            .unwrap_or(false);
        let response = bridge.handle(frame).await;
        writeln!(stdout, "{}", serde_json::to_string(&response)?)?;
        stdout.flush()?;
        if should_shutdown {
            break;
        }
    }
    Ok(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn jsonl_normalizer_accepts_bom() {
        assert_eq!(normalize_jsonl_input("\u{feff}{\"id\":1}"), "{\"id\":1}");
    }

    #[tokio::test]
    async fn bridge_handles_initialize_and_git_status() {
        let mut bridge = ReverieUiBridge::default();
        let initialized = bridge
            .handle(json!({
                "id": 1,
                "method": "initialize",
                "payload": {"project_root": std::env::current_dir().unwrap()}
            }))
            .await;
        assert_eq!(initialized["ok"], true);

        let git = bridge
            .handle(json!({"id": 2, "method": "gitStatus", "payload": {}}))
            .await;
        assert_eq!(git["ok"], true);
        assert!(git["result"]["git"].is_object());
    }

    #[tokio::test]
    async fn bridge_lists_manifest_dynamic_plugin_tools() {
        let temp = TempDir::new().unwrap();
        let plugin_root = temp.path().join(".reverie/plugins/sample");
        std::fs::create_dir_all(&plugin_root).unwrap();
        std::fs::write(
            plugin_root.join("plugin.json"),
            serde_json::to_string(&json!({
                "id": "sample-runtime",
                "display_name": "Sample Runtime",
                "commands": [{
                    "name": "status",
                    "description": "Return status.",
                    "expose_as_tool": true
                }]
            }))
            .unwrap(),
        )
        .unwrap();
        let mut bridge = ReverieUiBridge {
            project_root: temp.path().to_path_buf(),
            mode: "reverie".to_string(),
        };
        let response = bridge
            .handle(json!({"id": 3, "method": "list_tools", "payload": {}}))
            .await;
        assert_eq!(response["ok"], true);
        let dynamic_tools = response["result"]["dynamic_tools"].as_array().unwrap();
        assert!(dynamic_tools
            .iter()
            .any(|tool| tool["name"] == "rc_sample_runtime_status"));
    }
}
