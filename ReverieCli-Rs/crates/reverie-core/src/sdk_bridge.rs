use crate::agent::{AgentOptions, ReverieAgent};
use crate::cli_commands::command_catalog;
use crate::config::{app_root, Config, ConfigManager, ModelConfig};
use crate::modes::normalize_mode;
use crate::providers::{codex_catalog, modelscope_catalog, nvidia_catalog, ProviderModel};
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
            "save_model" | "saveModel" => self.handle_save_model(payload),
            "delete_model" | "deleteModel" => self.handle_delete_model(payload),
            "select_model" | "selectModel" => self.handle_select_model(payload),
            "save_builtin_source" | "saveBuiltinSource" => self.handle_save_builtin_source(payload),
            "select_builtin_source" | "selectBuiltinSource" => {
                self.handle_select_builtin_source(payload)
            }
            "test_providers" | "testProviders" => self.handle_test_providers(payload),
            "new_session" | "newSession" => self.handle_new_session(payload),
            "list_sessions" | "listSessions" | "switch_session" | "switchSession"
            | "rename_session" | "renameSession" | "delete_session" | "deleteSession"
            | "clear_session" | "clearSession" => self.handle_session_command(method, payload),
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
            "list_remote_releases" | "listRemoteReleases" => self.handle_list_remote_releases(),
            "install_remote_plugin" | "installRemotePlugin" => {
                self.handle_install_remote_plugin(payload).await
            }
            "build_plugin" | "buildPlugin" => self.handle_build_plugin(payload).await,
            "deploy_plugin" | "deployPlugin" => self.handle_deploy_plugin(payload),
            "inspect_plugin" | "inspectPlugin" => self.handle_inspect_plugin(payload).await,
            "call_plugin_command" | "callPluginCommand" => {
                self.handle_call_plugin_command(payload).await
            }
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
                "message": "Unsupported Rust bridge method."
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

    fn handle_save_model(&mut self, payload: Value) -> ReverieResult<Value> {
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let model = model_from_payload(&payload)?;
        let index = payload.get("index").and_then(Value::as_i64);
        if let Some(index) = index.filter(|index| *index >= 0) {
            let index = index as usize;
            if index < config.models.len() {
                config.models[index] = model.clone();
            } else {
                config.models.push(model.clone());
            }
        } else if let Some(existing) = config
            .models
            .iter_mut()
            .find(|item| item.name == model.name || item.model == model.model)
        {
            *existing = model.clone();
        } else {
            config.models.push(model.clone());
        }
        config.active_model = Some(model.name.clone());
        config.model_source = model
            .provider
            .clone()
            .unwrap_or_else(|| "standard".to_string());
        manager.save(&config)?;
        Ok(json!({"config": config, "model": model, "state": self.state()}))
    }

    fn handle_delete_model(&mut self, payload: Value) -> ReverieResult<Value> {
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let selected = select_model_key(&config, &payload)?;
        let before = config.models.len();
        config
            .models
            .retain(|item| item.name != selected && item.model != selected);
        let deleted = config.models.len() != before;
        if config.active_model.as_deref() == Some(selected.as_str()) {
            config.active_model = config.models.first().map(|item| item.name.clone());
        }
        manager.save(&config)?;
        Ok(json!({"deleted": deleted, "model": selected, "config": config}))
    }

    fn handle_select_model(&mut self, payload: Value) -> ReverieResult<Value> {
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let selected = select_model_key(&config, &payload)?;
        config.active_model = Some(selected.clone());
        config.model_source = config
            .models
            .iter()
            .find(|item| item.name == selected || item.model == selected)
            .and_then(|item| item.provider.clone())
            .unwrap_or_else(|| "standard".to_string());
        manager.save(&config)?;
        Ok(json!({"selected": selected, "config": config, "state": self.state()}))
    }

    fn handle_save_builtin_source(&mut self, payload: Value) -> ReverieResult<Value> {
        let source = payload
            .get("source")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase();
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let selected_model_id = payload
            .get("selected_model_id")
            .or_else(|| payload.get("model"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        match source.as_str() {
            "nvidia" | "modelscope" | "codex" => {
                let catalog = provider_catalog(&source);
                let selected = catalog
                    .iter()
                    .find(|model| model.id == selected_model_id)
                    .or_else(|| catalog.first())
                    .ok_or_else(|| {
                        crate::ReverieError::InvalidInput(format!("unknown source: {source}"))
                    })?;
                let model = provider_model_config(&source, selected);
                upsert_model(&mut config, model.clone());
                config.extra.insert(source.clone(), payload.clone());
                if payload
                    .get("activate")
                    .and_then(Value::as_bool)
                    .unwrap_or(true)
                {
                    config.model_source = source.clone();
                    config.active_model = Some(model.name.clone());
                }
            }
            "geminicli" => {
                config.extra.insert(source.clone(), payload.clone());
                if payload
                    .get("activate")
                    .and_then(Value::as_bool)
                    .unwrap_or(true)
                {
                    config.model_source = source.clone();
                    config.active_model = Some(if selected_model_id.is_empty() {
                        "gemini-cli".to_string()
                    } else {
                        selected_model_id.to_string()
                    });
                }
            }
            _ => {
                return Err(crate::ReverieError::InvalidInput(format!(
                    "unsupported built-in source: {source}"
                )))
            }
        }
        manager.save(&config)?;
        Ok(json!({"source": source, "config": config, "state": self.state()}))
    }

    fn handle_select_builtin_source(&mut self, payload: Value) -> ReverieResult<Value> {
        let source = payload
            .get("source")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase();
        if !matches!(
            source.as_str(),
            "standard" | "nvidia" | "modelscope" | "codex" | "geminicli"
        ) {
            return Err(crate::ReverieError::InvalidInput(format!(
                "unsupported built-in source: {source}"
            )));
        }
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        config.model_source = source.clone();
        manager.save(&config)?;
        Ok(json!({"source": source, "config": config, "state": self.state()}))
    }

    fn handle_test_providers(&self, payload: Value) -> ReverieResult<Value> {
        let wanted = provider_names_from_payload(&payload);
        let config = ConfigManager::new(&self.project_root, false).load()?;
        let results = wanted
            .into_iter()
            .map(|provider| {
                let required_env = match provider.as_str() {
                    "nvidia" => "NVIDIA_API_KEY",
                    "modelscope" => "MODELSCOPE_API_KEY",
                    "codex" => "OPENAI_API_KEY",
                    "standard" => config
                        .models
                        .iter()
                        .find(|item| {
                            config
                                .active_model
                                .as_ref()
                                .map(|active| item.name == *active || item.model == *active)
                                .unwrap_or(false)
                        })
                        .and_then(|item| item.api_key_env.as_deref())
                        .unwrap_or(""),
                    _ => "",
                };
                let env_present = required_env.is_empty() || std::env::var(required_env).is_ok();
                json!({
                    "provider": provider,
                    "success": env_present,
                    "required_env": required_env,
                    "message": if env_present { "configuration is ready" } else { "required API key env var is not set" }
                })
            })
            .collect::<Vec<_>>();
        Ok(json!({"results": results}))
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
        store.set_active(&record.id)?;
        Ok(json!({"session": record, "sessions": store.list()?}))
    }

    fn handle_session_command(&self, method: &str, payload: Value) -> ReverieResult<Value> {
        let store =
            SessionStore::new(crate::config::project_data_dir(&self.project_root).join("sessions"));
        let normalized = normalize_bridge_method(method);
        match normalized.trim_start_matches('_') {
            "list_sessions" => Ok(json!({
                "active_session_id": store.active_id()?,
                "sessions": store.list()?
            })),
            "switch_session" => {
                let id = payload_session_id(&payload)?;
                let session = store.set_active(&id)?;
                Ok(
                    json!({"session": session, "active_session_id": session.id, "sessions": store.list()?}),
                )
            }
            "rename_session" => {
                let id = payload_session_id(&payload)?;
                let name = payload
                    .get("name")
                    .or_else(|| payload.get("title"))
                    .and_then(Value::as_str)
                    .ok_or_else(|| {
                        crate::ReverieError::InvalidInput("session name is required".to_string())
                    })?;
                let session = store.rename(&id, name)?;
                Ok(json!({"session": session, "sessions": store.list()?}))
            }
            "delete_session" => {
                let id = payload_session_id(&payload)?;
                let deleted = store.delete(&id)?;
                Ok(json!({"deleted": deleted, "session_id": id, "sessions": store.list()?}))
            }
            "clear_session" => {
                let id = payload
                    .get("sessionId")
                    .or_else(|| payload.get("session_id"))
                    .and_then(Value::as_str)
                    .map(str::to_string)
                    .or_else(|| store.active_id().ok().flatten())
                    .ok_or_else(|| {
                        crate::ReverieError::InvalidInput("session id is required".to_string())
                    })?;
                let session = store.clear(&id)?;
                Ok(json!({"session": session, "sessions": store.list()?}))
            }
            _ => Ok(json!({"sessions": store.list()?})),
        }
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

    fn handle_list_remote_releases(&self) -> ReverieResult<Value> {
        let manifest = app_root().join("plugins").join("marketplace.json");
        let releases = if manifest.is_file() {
            serde_json::from_str(&std::fs::read_to_string(manifest)?)?
        } else {
            json!({"plugins": []})
        };
        Ok(json!({"releases": releases, "source": "local_marketplace"}))
    }

    async fn handle_install_remote_plugin(&self, payload: Value) -> ReverieResult<Value> {
        let plugin_id = payload
            .get("pluginId")
            .or_else(|| payload.get("id"))
            .and_then(Value::as_str)
            .unwrap_or("plugin")
            .trim();
        let install_root = app_root().join("plugins");
        std::fs::create_dir_all(&install_root)?;
        if let Some(source) = payload
            .get("source_path")
            .or_else(|| payload.get("path"))
            .and_then(Value::as_str)
        {
            let source = PathBuf::from(source);
            let target = install_root.join(plugin_id);
            if source.is_dir() {
                copy_dir_all(&source, &target)?;
            } else if source.is_file() {
                std::fs::create_dir_all(&target)?;
                std::fs::copy(&source, target.join(source.file_name().unwrap_or_default()))?;
            } else {
                return Err(crate::ReverieError::InvalidInput(format!(
                    "plugin source path not found: {}",
                    source.display()
                )));
            }
            return Ok(json!({"installed": true, "plugin_id": plugin_id, "target": target}));
        }

        let download_url = payload
            .get("downloadUrl")
            .or_else(|| payload.get("download_url"))
            .and_then(Value::as_str)
            .ok_or_else(|| {
                crate::ReverieError::InvalidInput(
                    "downloadUrl or source_path is required".to_string(),
                )
            })?;
        let asset_name = payload
            .get("assetName")
            .or_else(|| payload.get("asset_name"))
            .and_then(Value::as_str)
            .filter(|name| !name.trim().is_empty())
            .unwrap_or(plugin_id);
        let bytes = reqwest::get(download_url).await?.bytes().await?;
        let target = install_root.join(asset_name);
        std::fs::write(&target, &bytes)?;
        Ok(json!({
            "installed": true,
            "plugin_id": plugin_id,
            "target": target,
            "bytes": bytes.len()
        }))
    }

    async fn handle_build_plugin(&self, payload: Value) -> ReverieResult<Value> {
        let plugin_id = payload
            .get("pluginId")
            .or_else(|| payload.get("id"))
            .and_then(Value::as_str)
            .ok_or_else(|| {
                crate::ReverieError::InvalidInput("plugin id is required".to_string())
            })?;
        let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
        let record = manager.find_plugin(plugin_id)?.ok_or_else(|| {
            crate::ReverieError::InvalidInput(format!("plugin not found: {plugin_id}"))
        })?;
        let build_command = record
            .spec
            .raw
            .get("build_command")
            .or_else(|| record.spec.raw.pointer("/scripts/build"))
            .and_then(Value::as_str);
        let Some(build_command) = build_command else {
            return Ok(json!({
                "plugin_id": plugin_id,
                "built": false,
                "message": "No build_command or scripts.build entry in plugin manifest.",
                "record": record
            }));
        };
        let output = run_shell_command(build_command, &record.root).await?;
        Ok(json!({"plugin_id": plugin_id, "built": output["success"], "output": output}))
    }

    fn handle_deploy_plugin(&self, payload: Value) -> ReverieResult<Value> {
        let plugin_id = payload
            .get("pluginId")
            .or_else(|| payload.get("id"))
            .and_then(Value::as_str)
            .ok_or_else(|| {
                crate::ReverieError::InvalidInput("plugin id is required".to_string())
            })?;
        let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
        let record = manager.find_plugin(plugin_id)?.ok_or_else(|| {
            crate::ReverieError::InvalidInput(format!("plugin not found: {plugin_id}"))
        })?;
        let target = app_root().join("plugins").join(plugin_id);
        copy_dir_all(&record.root, &target)?;
        Ok(json!({"plugin_id": plugin_id, "deployed": true, "target": target}))
    }

    async fn handle_inspect_plugin(&self, payload: Value) -> ReverieResult<Value> {
        let plugin_id = payload
            .get("pluginId")
            .or_else(|| payload.get("id"))
            .and_then(Value::as_str)
            .ok_or_else(|| {
                crate::ReverieError::InvalidInput("plugin id is required".to_string())
            })?;
        let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
        let record = manager.find_plugin(plugin_id)?;
        let handshake = if record
            .as_ref()
            .and_then(|item| item.entry_path.as_ref())
            .map(|path| path.is_file())
            .unwrap_or(false)
        {
            Some(manager.handshake(plugin_id).await?)
        } else {
            None
        };
        Ok(json!({"plugin_id": plugin_id, "record": record, "handshake": handshake}))
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

fn normalize_bridge_method(method: &str) -> String {
    let mut out = String::new();
    for (index, ch) in method.chars().enumerate() {
        if ch.is_ascii_uppercase() {
            if index > 0 {
                out.push('_');
            }
            out.push(ch.to_ascii_lowercase());
        } else {
            out.push(ch);
        }
    }
    out
}

fn model_from_payload(payload: &Value) -> ReverieResult<ModelConfig> {
    let model_id = payload
        .get("model")
        .or_else(|| payload.get("model_id"))
        .and_then(Value::as_str)
        .ok_or_else(|| crate::ReverieError::InvalidInput("model is required".to_string()))?
        .trim()
        .to_string();
    let name = payload
        .get("name")
        .or_else(|| payload.get("model_display_name"))
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(&model_id)
        .trim()
        .to_string();
    let provider = payload
        .get("provider")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("standard")
        .to_string();
    Ok(ModelConfig {
        name,
        model: model_id,
        base_url: payload
            .get("base_url")
            .or_else(|| payload.get("api_url"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string),
        api_key_env: payload
            .get("api_key_env")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string),
        provider: Some(provider),
        transport: payload
            .get("transport")
            .or_else(|| payload.get("endpoint"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
            .or_else(|| Some("openai".to_string())),
        supports_vision: payload
            .get("supports_vision")
            .or_else(|| payload.get("vision"))
            .and_then(Value::as_bool)
            .unwrap_or(false),
    })
}

fn select_model_key(config: &Config, payload: &Value) -> ReverieResult<String> {
    if let Some(index) = payload.get("index").and_then(Value::as_i64) {
        if index >= 0 {
            return config
                .models
                .get(index as usize)
                .map(|model| model.name.clone())
                .ok_or_else(|| {
                    crate::ReverieError::InvalidInput(format!("model index out of range: {index}"))
                });
        }
    }
    let query = payload
        .get("name")
        .or_else(|| payload.get("model"))
        .or_else(|| payload.get("id"))
        .and_then(Value::as_str)
        .ok_or_else(|| crate::ReverieError::InvalidInput("model name is required".to_string()))?;
    config
        .models
        .iter()
        .find(|item| item.name == query || item.model == query)
        .map(|item| item.name.clone())
        .ok_or_else(|| crate::ReverieError::InvalidInput(format!("model not found: {query}")))
}

fn provider_catalog(source: &str) -> Vec<ProviderModel> {
    match source {
        "nvidia" => nvidia_catalog(),
        "modelscope" => modelscope_catalog(),
        "codex" => codex_catalog(),
        _ => Vec::new(),
    }
}

fn provider_model_config(provider: &str, selected: &ProviderModel) -> ModelConfig {
    let (base_url, api_key_env) = match provider {
        "nvidia" => (
            Some("https://integrate.api.nvidia.com/v1".to_string()),
            Some("NVIDIA_API_KEY".to_string()),
        ),
        "modelscope" => (
            Some("https://api-inference.modelscope.cn/v1".to_string()),
            Some("MODELSCOPE_API_KEY".to_string()),
        ),
        "codex" => (
            Some("https://api.openai.com/v1".to_string()),
            Some("OPENAI_API_KEY".to_string()),
        ),
        _ => (None, None),
    };
    ModelConfig {
        name: format!("{provider}:{}", selected.id),
        model: selected.id.to_string(),
        base_url,
        api_key_env,
        provider: Some(provider.to_string()),
        transport: Some(selected.transport.to_string()),
        supports_vision: selected.supports_vision,
    }
}

fn upsert_model(config: &mut Config, model: ModelConfig) {
    if let Some(existing) = config
        .models
        .iter_mut()
        .find(|item| item.name == model.name || item.model == model.model)
    {
        *existing = model;
    } else {
        config.models.push(model);
    }
}

fn provider_names_from_payload(payload: &Value) -> Vec<String> {
    if let Some(text) = payload.get("providers").and_then(Value::as_str) {
        return text
            .split(',')
            .map(str::trim)
            .filter(|item| !item.is_empty())
            .map(|item| item.to_ascii_lowercase())
            .collect();
    }
    if let Some(items) = payload.get("providers").and_then(Value::as_array) {
        return items
            .iter()
            .filter_map(Value::as_str)
            .map(str::trim)
            .filter(|item| !item.is_empty())
            .map(|item| item.to_ascii_lowercase())
            .collect();
    }
    vec![
        "standard".to_string(),
        "nvidia".to_string(),
        "modelscope".to_string(),
        "codex".to_string(),
    ]
}

fn payload_session_id(payload: &Value) -> ReverieResult<String> {
    payload
        .get("sessionId")
        .or_else(|| payload.get("session_id"))
        .or_else(|| payload.get("id"))
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| crate::ReverieError::InvalidInput("session id is required".to_string()))
}

fn copy_dir_all(source: &std::path::Path, target: &std::path::Path) -> ReverieResult<()> {
    if !source.is_dir() {
        return Err(crate::ReverieError::InvalidInput(format!(
            "source is not a directory: {}",
            source.display()
        )));
    }
    std::fs::create_dir_all(target)?;
    for entry in std::fs::read_dir(source)? {
        let entry = entry?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if source_path.is_dir() {
            copy_dir_all(&source_path, &target_path)?;
        } else {
            if let Some(parent) = target_path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::copy(&source_path, &target_path)?;
        }
    }
    Ok(())
}

async fn run_shell_command(command: &str, cwd: &std::path::Path) -> ReverieResult<Value> {
    let output = if cfg!(windows) {
        Command::new("powershell")
            .arg("-NoProfile")
            .arg("-Command")
            .arg(command)
            .current_dir(cwd)
            .output()
            .await?
    } else {
        Command::new("sh")
            .arg("-lc")
            .arg(command)
            .current_dir(cwd)
            .output()
            .await?
    };
    Ok(json!({
        "success": output.status.success(),
        "exit_code": output.status.code(),
        "stdout": String::from_utf8_lossy(&output.stdout),
        "stderr": String::from_utf8_lossy(&output.stderr)
    }))
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
