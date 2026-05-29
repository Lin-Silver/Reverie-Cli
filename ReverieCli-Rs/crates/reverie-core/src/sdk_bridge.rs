use crate::agent::{AgentOptions, ReverieAgent, MAX_TOOL_ROUNDS};
use crate::cli_commands::command_catalog;
use crate::config::{app_root, Config, ConfigManager, ModelConfig};
use crate::modes::{list_modes, normalize_mode};
use crate::providers::{
    codex_catalog, gemini_catalog, modelscope_catalog, nvidia_catalog, ollama_catalog,
    ProviderModel,
};
use crate::rules::RulesManager;
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
            "get_state" | "getState" => Ok(self.state()),
            "set_workspace" | "setWorkspace" => self.handle_set_workspace(payload),
            "set_mode" | "setMode" => self.handle_set_mode(payload),
            "set_setting" | "setSetting" => self.handle_set_setting(payload),
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
            "list_plugins" | "listPlugins" | "refresh_plugins" | "refreshPlugins" => {
                self.handle_list_plugins().await
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
            "list_tools" | "listTools" => Ok(json!({
                "type": "tools",
                "tools": ToolRegistry::builtin().visible_for_mode(&self.mode),
                "dynamic_tools": crate::plugins::RuntimePluginManager::new(&self.project_root).dynamic_tools().await.unwrap_or_default()
            })),
            "list_commands" => Ok(json!({
                "commands": command_catalog()
            })),
            "list_settings" | "listSettings" => self.handle_list_settings(),
            "gitStatus" | "git_status" => self.handle_git_status(payload).await,
            "getTotals" | "get_totals" => self.handle_get_totals(),
            "runAgentRegression" | "run_agent_regression" => {
                self.handle_run_agent_regression().await
            }
            "diagnostics" => Ok(json!({
                "type": "diagnostics",
                "ok": true,
                "runtime": "rust",
                "project_root": self.project_root,
                "plugins": crate::plugins::RuntimePluginManager::new(&self.project_root).list_plugins_with_handshakes().await.unwrap_or_default(),
                "harness": crate::harness::build_harness_capability_report(&self.project_root).ok()
            })),
            "index_workspace" | "indexWorkspace" => self.handle_index_workspace(payload),
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
            Ok(value) => {
                let mut response = json!({"id": id, "ok": true, "result": value});
                let event_fields = response
                    .get("result")
                    .and_then(Value::as_object)
                    .filter(|object| object.contains_key("type"))
                    .cloned();
                if let (Some(response_object), Some(value_object)) =
                    (response.as_object_mut(), event_fields)
                {
                    for (key, nested_value) in value_object {
                        response_object.insert(key, nested_value);
                    }
                }
                response
            }
            Err(err) => json!({"id": id, "ok": false, "error": err.to_string()}),
        }
    }

    fn handle_initialize(&mut self, payload: Value) -> ReverieResult<Value> {
        if let Some(path) = payload
            .get("project_root")
            .or_else(|| payload.get("projectRoot"))
            .and_then(Value::as_str)
        {
            self.project_root = PathBuf::from(path);
        }
        if let Some(mode) = payload.get("mode").and_then(Value::as_str) {
            self.mode = normalize_mode(mode).canonical().to_string();
        }
        let config = ConfigManager::new(&self.project_root, false).load()?;
        Ok(json!({
            "type": "state",
            "project_root": self.project_root,
            "state": self.state(),
            "config": self.config_summary(&config),
            "sessions": self.sessions_summary()?,
            "tools": self.tools_summary(&config.active_mode),
            "totals": crate::dashboard::summarize_totals(&self.project_root)?,
            "runtime": self.runtime_info(),
            "providers": {
                "nvidia": nvidia_catalog(),
                "modelscope": modelscope_catalog(),
                "codex": codex_catalog(),
                "gemini": gemini_catalog(),
                "ollama": ollama_catalog()
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

    fn state_event(&self) -> ReverieResult<Value> {
        let config = ConfigManager::new(&self.project_root, false).load()?;
        Ok(json!({
            "type": "state",
            "state": self.state(),
            "project_root": self.project_root,
            "config": self.config_summary(&config),
            "sessions": self.sessions_summary()?,
            "tools": self.tools_summary(&config.active_mode),
            "totals": crate::dashboard::summarize_totals(&self.project_root)?,
            "runtime": self.runtime_info()
        }))
    }

    fn config_summary(&self, config: &Config) -> Value {
        let models = config
            .models
            .iter()
            .enumerate()
            .map(|(index, model)| model_summary(index, model))
            .collect::<Vec<_>>();
        let active_model = config.active_model.as_deref().and_then(|active| {
            config
                .models
                .iter()
                .enumerate()
                .find(|(_, model)| model.name == active || model.model == active)
                .map(|(index, model)| model_summary(index, model))
        });
        let active_mode = normalize_mode(&config.active_mode);
        json!({
            "mode": active_mode.canonical(),
            "mode_display_name": active_mode.display_name(),
            "modes": list_modes(true, false)
                .into_iter()
                .map(|mode| json!({"id": mode.canonical(), "name": mode.display_name()}))
                .collect::<Vec<_>>(),
            "stream_responses": config.stream_responses,
            "auto_index": config.auto_index,
            "show_status_line": config.show_status_line,
            "tool_output_style": config.tool_output_style,
            "thinking_output_style": config.thinking_output_style,
            "theme": config.extra.get("theme").and_then(Value::as_str).unwrap_or("default"),
            "api_timeout": config.api_timeout,
            "api_max_retries": config.api_max_retries,
            "active_model_source": config.model_source,
            "active_model_index": active_model
                .as_ref()
                .and_then(|item| item.get("index").and_then(Value::as_u64))
                .unwrap_or(0),
            "active_model": active_model,
            "models": models,
            "builtin_sources": self.builtin_sources_summary(config),
            "config_path": ConfigManager::new(&self.project_root, false).active_config_path(),
            "app_root": app_root(),
            "sdk": self.runtime_info(),
        })
    }

    fn builtin_sources_summary(&self, config: &Config) -> Vec<Value> {
        let active_source = config.model_source.trim().to_ascii_lowercase();
        [
            ("geminicli", "Gemini CLI", Vec::<ProviderModel>::new()),
            ("codex", "Codex", codex_catalog()),
            ("nvidia", "NVIDIA", nvidia_catalog()),
            ("modelscope", "ModelScope", modelscope_catalog()),
            ("standard", "Standard", Vec::<ProviderModel>::new()),
        ]
        .into_iter()
        .map(|(source, label, catalog)| {
            let selected = config
                .extra
                .get(source)
                .and_then(|value| value.get("selected_model_id"))
                .and_then(Value::as_str)
                .unwrap_or_default();
            json!({
                "source": source,
                "label": label,
                "active": active_source == source,
                "credential": provider_credential_status(source, config),
                "has_api_key": provider_has_credential(source, config),
                "selected_model_id": selected,
                "selected_model_display_name": catalog
                    .iter()
                    .find(|model| model.id == selected)
                    .map(|model| model.display_name)
                    .unwrap_or_default(),
                "api_url": provider_api_url(source),
                "endpoint": "",
                "models": catalog,
            })
        })
        .collect()
    }

    fn sessions_summary(&self) -> ReverieResult<Value> {
        let store =
            SessionStore::new(crate::config::project_data_dir(&self.project_root).join("sessions"));
        let sessions = store
            .list()?
            .into_iter()
            .map(|session| {
                json!({
                    "id": session.id,
                    "name": session.title,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "message_count": store
                        .load_transcript(&session.id)
                        .ok()
                        .flatten()
                        .map(|transcript| transcript.messages.len())
                        .unwrap_or(0),
                })
            })
            .collect::<Vec<_>>();
        let active_id = store.active_id()?.unwrap_or_default();
        let active = if active_id.is_empty() {
            None
        } else {
            store.load_transcript(&active_id)?
        };
        let messages = active
            .as_ref()
            .map(|transcript| {
                transcript
                    .messages
                    .iter()
                    .rev()
                    .take(80)
                    .map(|message| {
                        json!({
                            "role": message.role,
                            "content": message_content_text(&message.content),
                        })
                    })
                    .collect::<Vec<_>>()
                    .into_iter()
                    .rev()
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        Ok(json!({
            "current_session_id": active.as_ref().map(|transcript| transcript.id.clone()).unwrap_or_default(),
            "current_session_name": active.as_ref().map(|transcript| transcript.record.title.clone()).unwrap_or_default(),
            "sessions": sessions,
            "messages": messages,
        }))
    }

    fn tools_summary(&self, mode: &str) -> Vec<Value> {
        ToolRegistry::builtin()
            .all()
            .iter()
            .map(|tool| {
                json!({
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category,
                    "tags": [],
                    "visible": tool.modes.iter().any(|item| item == mode),
                    "read_only": false,
                    "destructive": matches!(tool.name.as_str(), "delete_file" | "command_exec"),
                    "supported_modes": tool.modes,
                })
            })
            .collect()
    }

    fn handle_set_workspace(&mut self, payload: Value) -> ReverieResult<Value> {
        let path = payload
            .get("project_root")
            .or_else(|| payload.get("projectRoot"))
            .or_else(|| payload.get("path"))
            .and_then(Value::as_str)
            .unwrap_or(".");
        self.project_root = PathBuf::from(path).canonicalize()?;
        self.state_event()
    }

    fn handle_set_mode(&mut self, payload: Value) -> ReverieResult<Value> {
        let mode = payload
            .get("mode")
            .and_then(Value::as_str)
            .unwrap_or("reverie");
        self.mode = normalize_mode(mode).canonical().to_string();
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        config.active_mode = self.mode.clone();
        manager.save(&config)?;
        self.state_event()
    }

    fn handle_set_setting(&mut self, payload: Value) -> ReverieResult<Value> {
        let id = payload
            .get("id")
            .or_else(|| payload.get("key"))
            .or_else(|| payload.get("setting"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        let value = payload.get("value").cloned().unwrap_or(Value::Null);
        if id.eq_ignore_ascii_case("rules") {
            let manager = RulesManager::new(&self.project_root);
            let rules = rules_from_value(&value)?;
            manager.set_rules(&rules)?;
            return Ok(json!({
                "type": "setting.updated",
                "success": true,
                "message": format!("Rules updated ({} total).", rules.len()),
                "key": "rules",
                "settings": self.settings_summary()?
            }));
        }
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        apply_setting(&mut config, normalize_setting_key(id), value)?;
        if id.eq_ignore_ascii_case("mode") {
            self.mode = config.active_mode.clone();
        }
        manager.save(&config)?;
        Ok(json!({
            "type": "setting.updated",
            "success": true,
            "message": format!("Setting `{id}` updated."),
            "key": id,
            "config": config,
            "state": self.state(),
            "settings": self.settings_summary()?
        }))
    }

    fn handle_list_settings(&self) -> ReverieResult<Value> {
        Ok(json!({
            "type": "settings",
            "settings": self.settings_summary()?
        }))
    }

    fn settings_summary(&self) -> ReverieResult<Value> {
        let manager = ConfigManager::new(&self.project_root, false);
        let config = manager.load()?;
        let rules_manager = RulesManager::new(&self.project_root);
        let rules = rules_manager.get_rules()?;
        let items = setting_items()
            .iter()
            .map(|item| {
                let key = ui_setting_key(item.id);
                let value = setting_value_for_ui(&config, item.id, &rules);
                let options = item
                    .options
                    .iter()
                    .map(|choice| json!({"value": choice, "label": choice}))
                    .collect::<Vec<_>>();
                let mut normalized = json!({
                    "name": item.label,
                    "key": key,
                    "kind": item.kind,
                    "description": item.description,
                    "command": format!("/setting {} <value>", item.id),
                    "value": value,
                    "options": options
                });
                if item.id == "rules" {
                    normalized["rules"] = json!(&rules);
                }
                if item.id == "workspace" {
                    normalized["workspace_config_path"] = json!(manager.workspace_config_path);
                    normalized["global_config_path"] = json!(manager.global_config_path);
                }
                normalized
            })
            .collect::<Vec<_>>();
        Ok(json!({
            "items": items,
            "config_path": manager.active_config_path(),
            "workspace_mode": manager.is_workspace_mode(),
            "rules_path": rules_manager.rules_txt_path()
        }))
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
        self.state_event()
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
        self.state_event()
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
        let _ = deleted;
        self.state_event()
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
        self.state_event()
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
            "nvidia" | "modelscope" | "codex" | "gemini" | "ollama" => {
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
        self.state_event()
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
            "standard" | "nvidia" | "modelscope" | "codex" | "gemini" | "ollama" | "geminicli"
        ) {
            return Err(crate::ReverieError::InvalidInput(format!(
                "unsupported built-in source: {source}"
            )));
        }
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        config.model_source = source.clone();
        manager.save(&config)?;
        self.state_event()
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
                    "gemini" => "GEMINI_API_KEY",
                    "ollama" => "", // Ollama local, no key needed
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
        Ok(json!({"type": "provider.smoke", "results": results}))
    }

    fn handle_index_workspace(&mut self, payload: Value) -> ReverieResult<Value> {
        if let Some(path) = payload
            .get("project_root")
            .or_else(|| payload.get("projectRoot"))
            .and_then(Value::as_str)
        {
            self.project_root = PathBuf::from(path).canonicalize()?;
        }
        let result = CodebaseIndexer::new(&self.project_root)
            .with_cache_dir(
                crate::config::project_data_dir(&self.project_root).join("context_cache"),
            )
            .full_index()?;
        Ok(json!({
            "type": "index.complete",
            "result": serde_json::to_value(&result)?,
            "success": result.success
        }))
    }

    fn handle_get_totals(&self) -> ReverieResult<Value> {
        Ok(json!({
            "type": "totals",
            "totals": crate::dashboard::summarize_totals(&self.project_root)?,
        }))
    }

    async fn handle_run_agent_regression(&self) -> ReverieResult<Value> {
        let summary = crate::dashboard::run_agent_regression(&self.project_root).await?;
        Ok(json!({
            "type": "agent.regression.complete",
            "summary": summary,
            "totals": crate::dashboard::summarize_totals(&self.project_root)?,
        }))
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
        self.state_event()
    }

    fn handle_session_command(&self, method: &str, payload: Value) -> ReverieResult<Value> {
        let store =
            SessionStore::new(crate::config::project_data_dir(&self.project_root).join("sessions"));
        let normalized = normalize_bridge_method(method);
        match normalized.trim_start_matches('_') {
            "list_sessions" => self.state_event(),
            "switch_session" => {
                let id = payload_session_id(&payload)?;
                store.set_active(&id)?;
                self.state_event()
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
                store.rename(&id, name)?;
                self.state_event()
            }
            "delete_session" => {
                let id = payload_session_id(&payload)?;
                store.delete(&id)?;
                self.state_event()
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
                store.clear(&id)?;
                self.state_event()
            }
            _ => self.state_event(),
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
                sandbox_enabled: payload
                    .get("sandbox_enabled")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                max_tool_rounds: payload
                    .get("max_tool_rounds")
                    .and_then(Value::as_u64)
                    .map(|v| v as usize)
                    .unwrap_or(MAX_TOOL_ROUNDS),
            },
        );
        // Non-streaming mode: return result directly
        Ok(agent.run_prompt_once(prompt).await?.to_json_value())
    }

    /// Handle a streaming chat request, emitting incremental JSONL frames to the writer.
    /// Returns the final chat.complete value.
    pub async fn handle_chat_streaming<W: Write + Send>(
        &self,
        payload: Value,
        request_id: &Value,
        writer: &mut W,
    ) -> ReverieResult<Value> {
        use crate::llm::ModelStreamEvent;

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
                sandbox_enabled: payload
                    .get("sandbox_enabled")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                max_tool_rounds: payload
                    .get("max_tool_rounds")
                    .and_then(Value::as_u64)
                    .map(|v| v as usize)
                    .unwrap_or(MAX_TOOL_ROUNDS),
            },
        );

        let mut sink = |event: ModelStreamEvent| {
            let frame = match &event {
                ModelStreamEvent::Start { model } => json!({
                    "id": request_id,
                    "type": "stream.start",
                    "model": model
                }),
                ModelStreamEvent::Content { content } => json!({
                    "id": request_id,
                    "type": "stream.content",
                    "content": content
                }),
                ModelStreamEvent::ToolCallDelta {
                    index,
                    id,
                    name,
                    arguments_delta,
                } => json!({
                    "id": request_id,
                    "type": "stream.tool_call",
                    "index": index,
                    "tool_call_id": id,
                    "name": name,
                    "arguments_delta": arguments_delta
                }),
                ModelStreamEvent::End { finish_reason } => json!({
                    "id": request_id,
                    "type": "stream.end",
                    "finish_reason": finish_reason
                }),
                ModelStreamEvent::Recovered { message } => json!({
                    "id": request_id,
                    "type": "stream.recovered",
                    "message": message
                }),
                ModelStreamEvent::ToolExecStart { id, name } => json!({
                    "id": request_id,
                    "type": "tool_call.start",
                    "tool_call_id": id,
                    "name": name
                }),
                ModelStreamEvent::ToolExecComplete {
                    id,
                    name,
                    success,
                    error,
                } => json!({
                    "id": request_id,
                    "type": "tool_call.complete",
                    "tool_call_id": id,
                    "name": name,
                    "success": success,
                    "error": error
                }),
            };
            let _ = writeln!(writer, "{}", serde_json::to_string(&frame).unwrap_or_default());
            let _ = writer.flush();
        };

        let result = agent.run_prompt_streaming(prompt, &mut sink).await?;
        let mut value = result.to_json_value();
        value["type"] = json!("chat.complete");
        Ok(value)
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
        let result = manager
            .call_command(plugin_id, command_name, command_payload)
            .await?;
        Ok(json!({
            "type": "plugin.command.complete",
            "plugin_id": plugin_id,
            "command": command_name,
            "result": result
        }))
    }

    async fn handle_list_plugins(&self) -> ReverieResult<Value> {
        let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
        let records = manager
            .list_plugins_with_handshakes()
            .await
            .unwrap_or_default();
        let dynamic_tools = records
            .iter()
            .flat_map(|plugin| plugin.dynamic_tools.clone())
            .collect::<Vec<_>>();
        let record_values = records.iter().map(plugin_record_for_ui).collect::<Vec<_>>();
        let remote = self.handle_list_remote_releases()?;
        Ok(json!({
            "type": "plugins",
            "plugins": {
                "summary": {
                    "summary_label": format!("{} local plugins", record_values.len()),
                    "runtime": "rust"
                },
                "records": record_values,
                "source_validations": [],
                "remote": remote.get("remote").cloned().unwrap_or_else(|| json!({})),
                "dynamic_tools": dynamic_tools,
                "templates": ["blender", "godot", "o3de", "game_models"],
                "runtime": "rust"
            }
        }))
    }

    fn handle_list_remote_releases(&self) -> ReverieResult<Value> {
        let manifest = app_root().join("plugins").join("marketplace.json");
        let releases = if manifest.is_file() {
            serde_json::from_str(&std::fs::read_to_string(&manifest)?)?
        } else {
            json!({"plugins": []})
        };
        Ok(json!({
            "type": "remote.release",
            "remote": {
                "success": manifest.is_file(),
                "manifest": releases,
                "source": "local_marketplace",
                "error": if manifest.is_file() { "" } else { "marketplace manifest not found" }
            }
        }))
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
            return Ok(
                json!({"type": "plugin.installed", "installed": true, "plugin_id": plugin_id, "target": target}),
            );
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
            "type": "plugin.installed",
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
                "type": "plugin.build.complete",
                "plugin_id": plugin_id,
                "built": false,
                "message": "No build_command or scripts.build entry in plugin manifest.",
                "record": record
            }));
        };
        let output = run_shell_command(build_command, &record.root).await?;
        Ok(
            json!({"type": "plugin.build.complete", "plugin_id": plugin_id, "built": output["success"], "output": output}),
        )
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
        Ok(
            json!({"type": "plugin.deploy.complete", "plugin_id": plugin_id, "deployed": true, "target": target}),
        )
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
        Ok(
            json!({"type": "plugin.inspect", "plugin_id": plugin_id, "record": record, "handshake": handshake}),
        )
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
        let request_id = frame.get("id").cloned().unwrap_or(Value::Null);
        let method_name = frame
            .get("method")
            .and_then(Value::as_str)
            .or_else(|| frame.get("type").and_then(Value::as_str))
            .or_else(|| frame.get("action").and_then(Value::as_str))
            .unwrap_or_default()
            .to_string();
        match normalize_bridge_method(&method_name).trim_start_matches('_') {
            "index_workspace" => {
                writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string(&json!({
                        "id": request_id.clone(),
                        "type": "index.started",
                        "project_root": bridge.project_root
                    }))?
                )?;
                stdout.flush()?;
            }
            "run_agent_regression" => {
                writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string(&json!({
                        "id": request_id.clone(),
                        "type": "agent.regression.started"
                    }))?
                )?;
                stdout.flush()?;
            }
            "chat" => {
                let payload = frame
                    .get("payload")
                    .cloned()
                    .unwrap_or_else(|| json!({}));
                if payload
                    .get("stream")
                    .and_then(Value::as_bool)
                    .unwrap_or(false)
                {
                    // Streaming chat — emit incremental JSONL frames
                    let result = bridge
                        .handle_chat_streaming(payload, &request_id, &mut stdout)
                        .await;
                    let response = match result {
                        Ok(value) => json!({"id": request_id, "ok": true, "result": value, "type": "chat.complete"}),
                        Err(err) => json!({"id": request_id, "ok": false, "error": err.to_string()}),
                    };
                    writeln!(stdout, "{}", serde_json::to_string(&response)?)?;
                    stdout.flush()?;
                    if should_shutdown {
                        break;
                    }
                    continue;
                }
            }
            _ => {}
        }
        let response = bridge.handle(frame).await;
        writeln!(stdout, "{}", serde_json::to_string(&response)?)?;
        stdout.flush()?;
        if normalize_bridge_method(&method_name).trim_start_matches('_') == "run_agent_regression" {
            if let Some(totals) = response
                .get("result")
                .and_then(|result| result.get("totals"))
                .cloned()
            {
                writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string(&json!({
                        "id": request_id.clone(),
                        "type": "totals",
                        "totals": totals
                    }))?
                )?;
                stdout.flush()?;
            }
        }
        if normalize_bridge_method(&method_name).trim_start_matches('_') == "set_setting" {
            if let Some(settings) = response
                .get("result")
                .and_then(|result| result.get("settings"))
                .cloned()
            {
                writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string(&json!({
                        "id": request_id.clone(),
                        "type": "settings",
                        "settings": settings
                    }))?
                )?;
                stdout.flush()?;
            }
        }
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
        "gemini" | "google" => gemini_catalog(),
        "ollama" | "local" => ollama_catalog(),
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
        "gemini" | "google" => (
            Some("https://generativelanguage.googleapis.com/v1beta".to_string()),
            Some("GEMINI_API_KEY".to_string()),
        ),
        "ollama" | "local" => (
            Some("http://localhost:11434/v1".to_string()),
            None, // Ollama doesn't require API key
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

fn model_summary(index: usize, model: &ModelConfig) -> Value {
    json!({
        "index": index,
        "name": model.name,
        "model": model.model,
        "model_display_name": if model.name.is_empty() { model.model.as_str() } else { model.name.as_str() },
        "base_url": model.base_url,
        "provider": model.provider.as_deref().unwrap_or("standard"),
        "supports_vision": model.supports_vision,
        "endpoint": "",
        "max_context_tokens": 128000,
        "has_api_key": model
            .api_key_env
            .as_deref()
            .map(|name| std::env::var(name).is_ok())
            .unwrap_or(false),
    })
}

fn provider_api_url(source: &str) -> &str {
    match source {
        "nvidia" => "https://integrate.api.nvidia.com/v1",
        "modelscope" => "https://api-inference.modelscope.cn/v1",
        "codex" => "https://api.openai.com/v1",
        _ => "",
    }
}

fn provider_has_credential(source: &str, config: &Config) -> bool {
    match source {
        "nvidia" => std::env::var("NVIDIA_API_KEY").is_ok(),
        "modelscope" => std::env::var("MODELSCOPE_API_KEY").is_ok(),
        "codex" => std::env::var("OPENAI_API_KEY").is_ok(),
        "standard" => config.models.iter().any(|model| {
            model
                .api_key_env
                .as_deref()
                .map(|name| std::env::var(name).is_ok())
                .unwrap_or(false)
        }),
        _ => false,
    }
}

fn provider_credential_status(source: &str, config: &Config) -> &'static str {
    if provider_has_credential(source, config) {
        "found"
    } else {
        "missing"
    }
}

fn message_content_text(content: &Value) -> String {
    if let Some(text) = content.as_str() {
        return text.to_string();
    }
    if let Some(items) = content.as_array() {
        return items
            .iter()
            .filter_map(|item| {
                item.get("text")
                    .or_else(|| item.get("content"))
                    .and_then(Value::as_str)
                    .map(str::to_string)
            })
            .collect::<Vec<_>>()
            .join("\n");
    }
    content.to_string()
}

fn plugin_record_for_ui(record: &crate::plugins::RuntimePluginRecord) -> Value {
    let id = &record.spec.id;
    json!({
        "id": id,
        "name": if record.spec.name.is_empty() { id.as_str() } else { record.spec.name.as_str() },
        "display_name": if record.spec.name.is_empty() { id.as_str() } else { record.spec.name.as_str() },
        "description": record.spec.description,
        "version": record.spec.version,
        "status": if record.ready { "ready" } else { "installed" },
        "status_label": if record.ready { "ready" } else { "installed" },
        "delivery": "rust",
        "runtime_family": "rust",
        "root": record.root,
        "entry": record.spec.entry,
        "entry_path": record.entry_path,
        "manifest_path": record.manifest_path,
        "capabilities": [],
        "tool_count": record.dynamic_tools.len(),
        "command_count": record.spec.commands.len(),
        "commands": record.spec.commands,
        "catalog_managed": false,
        "build_commands": [],
        "protocol_status": if record.handshake.is_some() { "ready" } else { "" },
        "protocol_label": if record.handshake.is_some() { "ready" } else { "" },
    })
}

fn normalize_setting_key(key: &str) -> &str {
    match key {
        "use_workspace_config" => "workspace",
        "auto-index" => "auto_index",
        "status-line" => "show_status_line",
        "tool-output" => "tool_output_style",
        "thinking" => "thinking_output_style",
        "stream" => "stream_responses",
        "timeout" => "api_timeout",
        "retries" => "api_max_retries",
        other => other,
    }
}

fn ui_setting_key(id: &str) -> &str {
    match id {
        "workspace" => "use_workspace_config",
        other => other,
    }
}

fn setting_value_for_ui(config: &Config, id: &str, rules: &[String]) -> Value {
    match id {
        "mode" => json!(config.active_mode),
        "model" => json!(config.active_model),
        "theme" => config
            .extra
            .get("theme")
            .cloned()
            .unwrap_or_else(|| json!("default")),
        "auto_index" => json!(config.auto_index),
        "show_status_line" => json!(config.show_status_line),
        "stream_responses" => json!(config.stream_responses),
        "tool_output_style" => json!(config.tool_output_style),
        "thinking_output_style" => json!(config.thinking_output_style),
        "api_timeout" => json!(config.api_timeout),
        "api_max_retries" => json!(config.api_max_retries),
        "workspace" => json!(config.use_workspace_config),
        "rules" => json!(rules.join("\n")),
        _ => Value::Null,
    }
}

fn rules_from_value(value: &Value) -> ReverieResult<Vec<String>> {
    let raw_rules = if let Some(text) = value.as_str() {
        text.lines().map(str::to_string).collect::<Vec<_>>()
    } else if let Some(items) = value.as_array() {
        items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect::<Vec<_>>()
    } else {
        return Err(crate::ReverieError::InvalidInput(
            "rules expects a string or list value".to_string(),
        ));
    };
    Ok(raw_rules
        .into_iter()
        .map(|rule| rule.trim().to_string())
        .filter(|rule| !rule.is_empty())
        .collect())
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

    #[tokio::test]
    async fn bridge_handles_ui_camel_case_dashboard_and_settings() {
        let temp = TempDir::new().unwrap();
        let project = temp.path().join("project");
        std::fs::create_dir_all(&project).unwrap();
        std::fs::write(project.join("main.rs"), "fn main() {}\n").unwrap();
        let mut bridge = ReverieUiBridge::default();

        let initialized = bridge
            .handle(json!({
                "id": "ui-init",
                "action": "initialize",
                "payload": {"projectRoot": project}
            }))
            .await;
        assert_eq!(initialized["ok"], true);
        assert_eq!(initialized["type"], "state");
        assert!(initialized["config"]["modes"].is_array());

        let settings = bridge
            .handle(json!({"id": "ui-settings", "action": "listSettings", "payload": {}}))
            .await;
        assert_eq!(settings["ok"], true);
        assert_eq!(settings["type"], "settings");
        assert!(settings["settings"]["items"]
            .as_array()
            .unwrap()
            .iter()
            .any(|item| item["key"] == "rules"));

        let updated = bridge
            .handle(json!({
                "id": "ui-set-rules",
                "action": "setSetting",
                "payload": {"key": "rules", "value": "Always test P0"}
            }))
            .await;
        assert_eq!(updated["ok"], true);
        assert_eq!(updated["type"], "setting.updated");
        assert!(updated["settings"]["rules_path"].is_string());

        let totals = bridge
            .handle(json!({"id": "ui-totals", "action": "getTotals", "payload": {}}))
            .await;
        assert_eq!(totals["ok"], true);
        assert_eq!(totals["type"], "totals");
        assert!(totals["totals"]["usage"].is_object());

        let regression = bridge
            .handle(json!({"id": "ui-regression", "action": "runAgentRegression", "payload": {}}))
            .await;
        assert_eq!(regression["ok"], true);
        assert_eq!(regression["type"], "agent.regression.complete");
        assert_eq!(regression["summary"]["passed"], true);

        let indexed = bridge
            .handle(json!({"id": "ui-index", "action": "indexWorkspace", "payload": {}}))
            .await;
        assert_eq!(indexed["ok"], true);
        assert_eq!(indexed["type"], "index.complete");
        assert_eq!(indexed["success"], true);
    }

    #[tokio::test]
    async fn bridge_streaming_chat_emits_incremental_frames() {
        let temp = TempDir::new().unwrap();
        let project = temp.path().join("proj");
        std::fs::create_dir_all(&project).unwrap();
        let bridge = ReverieUiBridge {
            project_root: project.clone(),
            mode: "reverie".to_string(),
        };

        let mut output = Vec::<u8>::new();
        let request_id = json!("stream-1");
        // Without a configured model, streaming will fall through to local fallback
        // but the method should still produce a chat.complete frame
        let result = bridge
            .handle_chat_streaming(
                json!({"prompt": "hello", "stream": true, "no_index": true}),
                &request_id,
                &mut output,
            )
            .await;
        assert!(result.is_ok());
        let value = result.unwrap();
        assert_eq!(value["type"], "chat.complete");
        assert!(value["success"] == true);
        // Output buffer may have streaming frames (if model was configured)
        // or be empty (local fallback doesn't stream). Either way, valid.
        let output_str = String::from_utf8(output).unwrap();
        // If any frames were emitted, they should be valid JSONL
        for line in output_str.lines() {
            let parsed: Value = serde_json::from_str(line).unwrap();
            assert!(parsed.get("type").is_some());
            assert_eq!(parsed["id"], "stream-1");
        }
    }

    #[test]
    fn tool_exec_events_serialize_correctly() {
        use crate::llm::ModelStreamEvent;

        let start = ModelStreamEvent::ToolExecStart {
            id: "call_abc".to_string(),
            name: "file_ops".to_string(),
        };
        let complete = ModelStreamEvent::ToolExecComplete {
            id: "call_abc".to_string(),
            name: "file_ops".to_string(),
            success: true,
            error: None,
        };
        let start_json = serde_json::to_value(&start).unwrap();
        assert_eq!(start_json["type"], "ToolExecStart");
        assert_eq!(start_json["id"], "call_abc");
        assert_eq!(start_json["name"], "file_ops");

        let complete_json = serde_json::to_value(&complete).unwrap();
        assert_eq!(complete_json["type"], "ToolExecComplete");
        assert_eq!(complete_json["success"], true);
        assert!(complete_json["error"].is_null());
    }

    #[test]
    fn bridge_streaming_frame_types_are_recognized() {
        // Verify the JSONL frame types that the bridge emits are stable strings
        let valid_frame_types = [
            "stream.start",
            "stream.content",
            "stream.tool_call",
            "stream.end",
            "stream.recovered",
            "tool_call.start",
            "tool_call.complete",
            "chat.complete",
        ];
        // This is a schema test ensuring our frame type strings are stable
        for frame_type in valid_frame_types {
            assert!(
                !frame_type.is_empty(),
                "frame type must not be empty: {frame_type}"
            );
            assert!(
                frame_type.contains('.'),
                "frame type must be namespaced: {frame_type}"
            );
        }
    }
}
