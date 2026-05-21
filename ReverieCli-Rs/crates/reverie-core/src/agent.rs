use crate::cli_commands::{render_help, render_mode_list, render_tool_list};
use crate::config::{project_data_dir, Config, ConfigManager, ModelConfig};
use crate::llm::{
    build_openai_tool_definitions, extract_anthropic_tool_calls, extract_openai_tool_calls,
    sanitize_prompt_output_text, send_model_compatible, ChatMessage, ChatRequest,
};
use crate::modes::{normalize_mode, Mode};
use crate::providers::{
    codex_catalog, modelscope_catalog, normalize_reasoning_effort, nvidia_catalog, ProviderModel,
};
use crate::session::PromptRunResult;
use crate::session::{CheckpointStore, OperationStore, SessionStore};
use crate::settings_catalog::{apply_setting, setting_items};
use crate::{ReverieError, ReverieResult};
use reverie_context::CodebaseIndexer;
use reverie_tools::{execute_builtin_tool, ToolInvocation, ToolRegistry};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentOptions {
    pub mode: Mode,
    pub no_index: bool,
}

#[derive(Debug)]
pub struct ReverieAgent {
    project_root: PathBuf,
    options: AgentOptions,
}

impl ReverieAgent {
    pub fn new(project_root: impl AsRef<Path>, options: AgentOptions) -> Self {
        Self {
            project_root: project_root.as_ref().to_path_buf(),
            options,
        }
    }

    pub async fn run_prompt_once(&self, prompt: &str) -> ReverieResult<PromptRunResult> {
        let mut events = Vec::new();
        if !self.options.no_index {
            let indexer = CodebaseIndexer::new(&self.project_root)
                .with_cache_dir(project_data_dir(&self.project_root).join("context_cache"));
            let result = indexer.full_index()?;
            events.push(serde_json::json!({
                "type": "index",
                "files_scanned": result.files_scanned,
                "symbols_extracted": result.symbols_extracted
            }));
        }

        let trimmed = prompt.trim();
        let output = if let Some(command) = trimmed.strip_prefix('/') {
            self.handle_command(command).await?
        } else if let Some(invocation) = parse_inline_tool_invocation(trimmed) {
            let result = execute_builtin_tool(&self.project_root, invocation)
                .await
                .map_err(|err| ReverieError::Unsupported(err.to_string()))?;
            serde_json::to_string_pretty(&result)?
        } else {
            self.run_model_or_local_fallback(trimmed).await?
        };

        Ok(PromptRunResult {
            success: true,
            output_text: sanitize_prompt_output_text(&output),
            error: None,
            mode: self.options.mode.canonical().to_string(),
            project_root: self.project_root.clone(),
            events,
        })
    }

    async fn run_model_or_local_fallback(&self, prompt: &str) -> ReverieResult<String> {
        let config = ConfigManager::new(&self.project_root, false).load()?;
        let Some(model) = config.active_model.clone() else {
            return Ok(format!(
                "Reverie Rust agent received prompt in {} mode.\n\n{}",
                self.options.mode.display_name(),
                prompt
            ));
        };
        let visible_tools = ToolRegistry::builtin().visible_for_mode(self.options.mode.canonical());
        let tool_definitions = build_openai_tool_definitions(&visible_tools);
        let mut messages = vec![ChatMessage::new("user", serde_json::json!(prompt))];
        let response = send_model_compatible(
            &config,
            ChatRequest {
                model: model.clone(),
                messages: messages.clone(),
                tools: tool_definitions.clone(),
                stream: false,
                extra_body: serde_json::json!({}),
            },
        )
        .await?;
        let mut tool_calls = extract_openai_tool_calls(&response.raw);
        if tool_calls.is_empty() {
            tool_calls = extract_anthropic_tool_calls(&response.raw);
        }
        if tool_calls.is_empty() {
            return Ok(response.output_text);
        }

        messages.push(ChatMessage::assistant_with_tool_calls(
            tool_calls.iter().map(|call| call.raw.clone()).collect(),
        ));
        for call in tool_calls {
            let result = match execute_builtin_tool(
                &self.project_root,
                ToolInvocation {
                    name: call.name.clone(),
                    arguments: call.arguments.clone(),
                },
            )
            .await
            {
                Ok(result) => result,
                Err(err) => reverie_tools::ToolResult {
                    success: false,
                    output: serde_json::Value::Null,
                    error: Some(err.to_string()),
                },
            };
            messages.push(ChatMessage::tool_result(
                call.id,
                serde_json::json!(serde_json::to_string(&result)?),
            ));
        }
        let follow_up = send_model_compatible(
            &config,
            ChatRequest {
                model,
                messages,
                tools: tool_definitions,
                stream: false,
                extra_body: serde_json::json!({}),
            },
        )
        .await?;
        Ok(follow_up.output_text)
    }

    async fn handle_command(&self, command: &str) -> ReverieResult<String> {
        let mut parts = command.trim().splitn(2, char::is_whitespace);
        let name = parts.next().unwrap_or_default();
        let args = parts.next().unwrap_or_default().trim();
        match name {
            "help" => Ok(render_help()),
            "status" => Ok(format!(
                "Project: {}\nMode: {}\nRuntime: Rust\n{}",
                self.project_root.display(),
                self.options.mode.display_name(),
                self.render_model_status()?
            )),
            "clear" => Ok("\x1b[2J\x1b[H".to_string()),
            "exit" | "quit" => Ok("Exit requested.".to_string()),
            "clean" => self.handle_clean(args),
            "mode" if args.is_empty() => Ok(render_mode_list(self.options.mode)),
            "mode" => Ok(format!(
                "Requested mode: {}",
                normalize_mode(args).canonical()
            )),
            "tools" => Ok(render_tool_list(self.options.mode)),
            "search" => {
                self.tool_json("web_search", json!({"query": args, "q": args}))
                    .await
            }
            "skills" => {
                let arguments = if args.is_empty() {
                    json!({})
                } else {
                    json!({"query": args})
                };
                self.tool_json("skill_lookup", arguments).await
            }
            "mcp" => self.handle_mcp(args).await,
            "setting" | "settings" => self.handle_setting(args),
            "workspace" => self.handle_workspace(args),
            "rules" => self.handle_rules(args),
            "subagent" | "subagents" => self.handle_subagent(args).await,
            "tti" => self.handle_tti(args).await,
            "index" => {
                let result = CodebaseIndexer::new(&self.project_root)
                    .with_cache_dir(project_data_dir(&self.project_root).join("context_cache"))
                    .full_index()?;
                Ok(format!(
                    "Files scanned: {}\nFiles parsed: {}\nSymbols extracted: {}\nDependencies: {}",
                    result.files_scanned,
                    result.files_parsed,
                    result.symbols_extracted,
                    result.dependencies_extracted
                ))
            }
            "tool" => {
                let invocation: ToolInvocation = serde_json::from_str(args)?;
                let result = execute_builtin_tool(&self.project_root, invocation)
                    .await
                    .map_err(|err| ReverieError::Unsupported(err.to_string()))?;
                Ok(serde_json::to_string_pretty(&result)?)
            }
            "doctor" | "harness" => Ok(serde_json::to_string_pretty(
                &crate::harness::build_harness_capability_report(&self.project_root)?,
            )?),
            "plugins" => {
                let manager = crate::plugins::RuntimePluginManager::new(&self.project_root);
                let records = manager.list_plugins()?;
                Ok(serde_json::to_string_pretty(&records)?)
            }
            "codex" | "nvidia" | "modelscope" | "geminicli" => {
                self.handle_builtin_provider(name, args)
            }
            "model" => self.handle_model(args),
            "sessions" | "history" => {
                let store =
                    SessionStore::new(project_data_dir(&self.project_root).join("sessions"));
                self.handle_sessions(args, &store)
            }
            "checkpoints" => {
                let store =
                    CheckpointStore::new(project_data_dir(&self.project_root).join("checkpoints"));
                Ok(serde_json::to_string_pretty(&store.list()?)?)
            }
            "rollback" | "undo" | "redo" => {
                let store =
                    CheckpointStore::new(project_data_dir(&self.project_root).join("checkpoints"));
                if args.is_empty() {
                    return Ok("Usage: /rollback <checkpoint-id>".to_string());
                }
                let checkpoint = store.restore(&self.project_root, args)?;
                Ok(format!(
                    "Restored checkpoint {} ({} files)",
                    checkpoint.id,
                    checkpoint.files.len()
                ))
            }
            "operations" => {
                let store =
                    OperationStore::new(project_data_dir(&self.project_root).join("operations"));
                Ok(serde_json::to_string_pretty(&store.list()?)?)
            }
            "gdd" | "assets" | "blueprint" | "bp" | "scaffold" | "engine" | "modeling"
            | "blender" | "playtest" | "pt" => self.handle_gamer_command(name, args).await,
            other => Err(ReverieError::Unsupported(format!(
                "unknown Rust agent command: /{other}. Use /help to list available commands."
            ))),
        }
    }

    async fn tool_json(&self, name: &str, arguments: Value) -> ReverieResult<String> {
        let result = execute_builtin_tool(
            &self.project_root,
            ToolInvocation {
                name: name.to_string(),
                arguments,
            },
        )
        .await
        .map_err(|err| ReverieError::Unsupported(err.to_string()))?;
        Ok(serde_json::to_string_pretty(&result)?)
    }

    fn render_model_status(&self) -> ReverieResult<String> {
        let config = ConfigManager::new(&self.project_root, false).load()?;
        Ok(format!(
            "Model source: {}\nActive model: {}",
            config.model_source,
            config.active_model.unwrap_or_else(|| "(none)".to_string())
        ))
    }

    fn handle_clean(&self, args: &str) -> ReverieResult<String> {
        let force = args
            .split_whitespace()
            .any(|part| part.eq_ignore_ascii_case("force"));
        let data = project_data_dir(&self.project_root);
        let targets = [
            data.join("sessions"),
            data.join("context_cache"),
            data.join("checkpoints"),
            data.join("archives"),
            data.join("operations"),
            data.join("mcp_resources"),
            self.project_root.join(".reverie").join("tool_audit.json"),
        ];
        if !force {
            let preview = targets
                .iter()
                .filter(|path| path.exists())
                .map(|path| format!("  - {}", path.display()))
                .collect::<Vec<_>>();
            return Ok(if preview.is_empty() {
                "Nothing to clean.".to_string()
            } else {
                format!(
                    "This will delete:\n{}\nRun /clean force to confirm.",
                    preview.join("\n")
                )
            });
        }
        let mut removed = Vec::new();
        for target in targets {
            if target.is_dir() {
                std::fs::remove_dir_all(&target)?;
                removed.push(target);
            } else if target.is_file() {
                std::fs::remove_file(&target)?;
                removed.push(target);
            }
        }
        ConfigManager::new(&self.project_root, false).initialize()?;
        Ok(format!(
            "Cleaned {} Reverie runtime path(s).",
            removed.len()
        ))
    }

    fn handle_setting(&self, args: &str) -> ReverieResult<String> {
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let parts = args.split_whitespace().collect::<Vec<_>>();
        if parts.is_empty() || matches!(parts[0], "list" | "ls") {
            return Ok(serde_json::to_string_pretty(&json!({
                "settings": setting_items(),
                "config": config
            }))?);
        }
        if parts.len() < 2 {
            return Ok("Usage: /setting <id> <value>".to_string());
        }
        let id = parts[0];
        let raw_value = parts[1..].join(" ");
        let value = parse_setting_value(&raw_value);
        apply_setting(&mut config, id, value)?;
        manager.save(&config)?;
        Ok(format!("Updated setting `{id}`."))
    }

    fn handle_workspace(&self, args: &str) -> ReverieResult<String> {
        let manager = ConfigManager::new(&self.project_root, true);
        let mut config = manager.load()?;
        match args.trim().to_ascii_lowercase().as_str() {
            "" | "status" => Ok(serde_json::to_string_pretty(&json!({
                "project_root": self.project_root,
                "workspace_config_path": manager.workspace_config_path,
                "use_workspace_config": config.use_workspace_config
            }))?),
            "enable" | "on" => {
                config.use_workspace_config = true;
                manager.save(&config)?;
                Ok(format!(
                    "Workspace config enabled: {}",
                    manager.workspace_config_path.display()
                ))
            }
            "disable" | "off" => {
                let global = ConfigManager::new(&self.project_root, false);
                let mut global_config = global.load()?;
                global_config.use_workspace_config = false;
                global.save(&global_config)?;
                Ok("Workspace config disabled for global config.".to_string())
            }
            "init" => {
                let report = manager.initialize()?;
                Ok(serde_json::to_string_pretty(&report)?)
            }
            _ => Ok("Usage: /workspace [status|init|enable|disable]".to_string()),
        }
    }

    fn handle_rules(&self, args: &str) -> ReverieResult<String> {
        let path = self.project_root.join(".reverie").join("rules.txt");
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let rules = read_rules(&path)?;
        let mut parts = args.trim().splitn(2, char::is_whitespace);
        let action = parts.next().unwrap_or_default();
        let rest = parts.next().unwrap_or_default().trim();
        match action {
            "" | "list" | "ls" => Ok(render_rules(&rules)),
            "add" => {
                if rest.is_empty() {
                    return Ok("Usage: /rules add <text>".to_string());
                }
                let mut updated = rules;
                updated.push(rest.to_string());
                write_rules(&path, &updated)?;
                Ok(format!("Rule added. {} rule(s) active.", updated.len()))
            }
            "remove" | "delete" => {
                let index = rest.parse::<usize>().map_err(|_| {
                    ReverieError::InvalidInput("rule index must be a number".to_string())
                })?;
                let mut updated = rules;
                if index == 0 || index > updated.len() {
                    return Err(ReverieError::InvalidInput(format!(
                        "rule index out of range: {index}"
                    )));
                }
                let removed = updated.remove(index - 1);
                write_rules(&path, &updated)?;
                Ok(format!("Removed rule {index}: {removed}"))
            }
            "path" | "edit" => {
                if !path.exists() {
                    std::fs::write(&path, "")?;
                }
                Ok(format!("Rules file: {}", path.display()))
            }
            _ => Ok("Usage: /rules [list|add <text>|remove <number>|path]".to_string()),
        }
    }

    fn handle_sessions(&self, args: &str, store: &SessionStore) -> ReverieResult<String> {
        let mut parts = args.trim().splitn(2, char::is_whitespace);
        let action = parts.next().unwrap_or_default();
        let rest = parts.next().unwrap_or_default().trim();
        match action {
            "" | "list" | "ls" => Ok(serde_json::to_string_pretty(&json!({
                "active_session_id": store.active_id()?,
                "sessions": store.list()?
            }))?),
            "new" | "create" => {
                let title = if rest.is_empty() { "Session" } else { rest };
                let session = store.create(
                    title,
                    self.project_root.clone(),
                    self.options.mode.canonical().to_string(),
                )?;
                store.set_active(&session.id)?;
                Ok(serde_json::to_string_pretty(&json!({
                    "session": session,
                    "sessions": store.list()?
                }))?)
            }
            "switch" | "use" => {
                let session = store.set_active(rest)?;
                Ok(format!("Active session: {} ({})", session.id, session.title))
            }
            "rename" => {
                let mut fields = rest.splitn(2, char::is_whitespace);
                let id = fields.next().unwrap_or_default();
                let title = fields.next().unwrap_or_default().trim();
                if id.is_empty() || title.is_empty() {
                    return Ok("Usage: /sessions rename <id> <title>".to_string());
                }
                let session = store.rename(id, title)?;
                Ok(format!("Renamed {} to {}", session.id, session.title))
            }
            "delete" | "remove" => {
                if rest.is_empty() {
                    return Ok("Usage: /sessions delete <id>".to_string());
                }
                let removed = store.delete(rest)?;
                Ok(format!("Deleted session `{rest}`: {removed}"))
            }
            "clear" => {
                let id = if rest.is_empty() {
                    store.active_id()?.unwrap_or_default()
                } else {
                    rest.to_string()
                };
                if id.is_empty() {
                    return Ok("Usage: /sessions clear <id>".to_string());
                }
                let session = store.clear(&id)?;
                Ok(format!("Cleared session {}", session.id))
            }
            _ => Ok("Usage: /sessions [list|new <title>|switch <id>|rename <id> <title>|delete <id>|clear <id>]".to_string()),
        }
    }

    fn handle_model(&self, args: &str) -> ReverieResult<String> {
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let mut parts = args.trim().splitn(2, char::is_whitespace);
        let action = parts.next().unwrap_or_default();
        let rest = parts.next().unwrap_or_default().trim();
        match action {
            "" | "list" | "ls" => Ok(serde_json::to_string_pretty(&json!({
                "active_model": config.active_model,
                "model_source": config.model_source,
                "models": config.models
            }))?),
            "select" | "use" => {
                let selected = select_model_name(&config, rest)?;
                config.active_model = Some(selected.clone());
                config.model_source = config
                    .models
                    .iter()
                    .find(|model| model.name == selected || model.model == selected)
                    .and_then(|model| model.provider.clone())
                    .unwrap_or_else(|| "standard".to_string());
                manager.save(&config)?;
                Ok(format!("Active model: {selected}"))
            }
            "delete" | "remove" => {
                let selected = select_model_name(&config, rest)?;
                config
                    .models
                    .retain(|model| model.name != selected && model.model != selected);
                if config.active_model.as_deref() == Some(selected.as_str()) {
                    config.active_model = config.models.first().map(|model| model.name.clone());
                }
                manager.save(&config)?;
                Ok(format!("Deleted model: {selected}"))
            }
            "add" | "save" => {
                let model = parse_model_config(rest)?;
                upsert_model(&mut config, model.clone());
                config.active_model = Some(model.name.clone());
                config.model_source = model.provider.clone().unwrap_or_else(|| "standard".to_string());
                manager.save(&config)?;
                Ok(format!("Saved model: {}", model.name))
            }
            _ => Ok("Usage: /model [list|select <name/index>|delete <name/index>|add name=<name> model=<id> base_url=<url> api_key_env=<env>]".to_string()),
        }
    }

    fn handle_builtin_provider(&self, provider: &str, args: &str) -> ReverieResult<String> {
        if provider == "geminicli" {
            return self.handle_geminicli(args);
        }
        let catalog = provider_catalog(provider);
        let mut parts = args.trim().splitn(2, char::is_whitespace);
        let action = parts.next().unwrap_or_default();
        let rest = parts.next().unwrap_or_default().trim();
        if args.trim().is_empty() || matches!(action, "list" | "ls") {
            return Ok(serde_json::to_string_pretty(&catalog)?);
        }
        let model_id = if matches!(action, "select" | "use") {
            rest
        } else {
            args.trim()
        };
        let selected = catalog
            .iter()
            .find(|item| {
                item.id.eq_ignore_ascii_case(model_id)
                    || item.display_name.eq_ignore_ascii_case(model_id)
            })
            .or_else(|| catalog.first())
            .ok_or_else(|| {
                ReverieError::InvalidInput(format!("provider has no models: {provider}"))
            })?;
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let model = provider_model_config(provider, selected);
        upsert_model(&mut config, model.clone());
        config.active_model = Some(model.name.clone());
        config.model_source = provider.to_string();
        if provider == "codex" {
            config.extra.insert(
                "codex".to_string(),
                json!({
                    "selected_model_id": selected.id,
                    "reasoning_effort": normalize_reasoning_effort(rest)
                }),
            );
        }
        manager.save(&config)?;
        Ok(format!(
            "Active {provider} model: {} ({})",
            selected.display_name, model.name
        ))
    }

    fn handle_geminicli(&self, args: &str) -> ReverieResult<String> {
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let model = if args.trim().is_empty() {
            "gemini-cli"
        } else {
            args.trim()
        };
        config.model_source = "geminicli".to_string();
        config.active_model = Some(model.to_string());
        config.extra.insert(
            "geminicli".to_string(),
            json!({"selected_model_id": model, "transport": "external-cli"}),
        );
        manager.save(&config)?;
        Ok(format!("Configured Gemini CLI source: {model}"))
    }

    async fn handle_mcp(&self, args: &str) -> ReverieResult<String> {
        let mut parts = args.trim().splitn(2, char::is_whitespace);
        let action = parts.next().unwrap_or_default();
        let rest = parts.next().unwrap_or_default().trim();
        match action {
            "" | "list" | "resources" => self.tool_json("list_mcp_resources", json!({})).await,
            "read" => {
                self.tool_json("read_mcp_resource", json!({"uri": rest}))
                    .await
            }
            _ => Ok("Usage: /mcp [list|resources|read <uri>]".to_string()),
        }
    }

    async fn handle_tti(&self, args: &str) -> ReverieResult<String> {
        let raw = args.trim();
        if raw.is_empty() {
            return Ok(
                "Usage: /tti [models|source [local]|add <name> <path>|<prompt>]".to_string(),
            );
        }
        if raw == "models" {
            return self
                .tool_json("text_to_image", json!({"action": "list_models"}))
                .await;
        }
        if raw == "source" || raw.starts_with("source ") {
            let source = raw.strip_prefix("source").unwrap_or_default().trim();
            let manager = ConfigManager::new(&self.project_root, false);
            let mut config = manager.load()?;
            let value = if source.is_empty() { "local" } else { source };
            config
                .extra
                .insert("text_to_image".to_string(), json!({"active_source": value}));
            manager.save(&config)?;
            return Ok(format!("TTI source: {value}"));
        }
        if let Some(rest) = raw.strip_prefix("add ") {
            return self.handle_tti_add(rest);
        }
        self.tool_json(
            "text_to_image",
            json!({"action": "generate", "prompt": raw}),
        )
        .await
    }

    fn handle_tti_add(&self, args: &str) -> ReverieResult<String> {
        let mut parts = args.split_whitespace();
        let display_name = parts.next().unwrap_or_default();
        let path = parts.next().unwrap_or_default();
        if display_name.is_empty() || path.is_empty() {
            return Ok("Usage: /tti add <display-name> <model-path>".to_string());
        }
        let manager = ConfigManager::new(&self.project_root, false);
        let mut config = manager.load()?;
        let mut tti = config
            .extra
            .get("text_to_image")
            .cloned()
            .unwrap_or_else(|| json!({"active_source": "local", "models": []}));
        let models = tti
            .get_mut("models")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| {
                ReverieError::InvalidInput("text_to_image.models is not an array".to_string())
            })?;
        models.push(json!({"display_name": display_name, "path": path}));
        config.extra.insert("text_to_image".to_string(), tti);
        manager.save(&config)?;
        Ok(format!("Added TTI model `{display_name}`."))
    }

    async fn handle_subagent(&self, args: &str) -> ReverieResult<String> {
        let path = self.project_root.join(".reverie").join("subagents.json");
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let mut specs = read_json_array(&path)?;
        let mut parts = args.trim().splitn(3, char::is_whitespace);
        let action = parts.next().unwrap_or_default();
        match action {
            "" | "list" | "ls" => Ok(serde_json::to_string_pretty(&json!({"subagents": specs}))?),
            "create" => {
                let model = parts.next().unwrap_or("default");
                let id = format!("subagent-{}", chrono::Utc::now().timestamp_millis());
                let spec = json!({
                    "id": id,
                    "model_ref": {"source": "standard", "model": model, "display_name": model},
                    "enabled": true,
                    "created_at": chrono::Utc::now().to_rfc3339()
                });
                specs.push(spec.clone());
                write_json_array(&path, &specs)?;
                Ok(serde_json::to_string_pretty(&spec)?)
            }
            "delete" | "remove" => {
                let id = parts.next().unwrap_or_default();
                let before = specs.len();
                specs.retain(|item| item.get("id").and_then(Value::as_str) != Some(id));
                write_json_array(&path, &specs)?;
                Ok(format!("Deleted subagent `{id}`: {}", specs.len() != before))
            }
            "model" => {
                let id = parts.next().unwrap_or_default();
                let model = parts.next().unwrap_or_default();
                if id.is_empty() || model.is_empty() {
                    return Ok("Usage: /subagent model <id> <model>".to_string());
                }
                for spec in &mut specs {
                    if spec.get("id").and_then(Value::as_str) == Some(id) {
                        spec["model_ref"] = json!({
                            "source": "standard",
                            "model": model,
                            "display_name": model
                        });
                    }
                }
                write_json_array(&path, &specs)?;
                Ok(format!("Updated subagent `{id}` model to `{model}`."))
            }
            "run" => {
                let id = parts.next().unwrap_or_default();
                let task = parts.next().unwrap_or_default();
                if id.is_empty() || task.is_empty() {
                    return Ok("Usage: /subagent run <id> <task>".to_string());
                }
                self.tool_json("subagent", json!({"subagent_id": id, "prompt": task}))
                    .await
            }
            _ => Ok("Usage: /subagent [list|create [model]|model <id> <model>|run <id> <task>|delete <id>]".to_string()),
        }
    }

    async fn handle_gamer_command(&self, name: &str, args: &str) -> ReverieResult<String> {
        let (tool, arguments) = match name {
            "gdd" => ("game_gdd_manager", json!({"content": args})),
            "assets" => ("game_asset_manager", json!({"notes": args})),
            "blueprint" | "bp" => ("game_design_orchestrator", json!({"prompt": args})),
            "scaffold" => ("game_project_scaffolder", parse_action_args(args, "create")),
            "engine" => ("reverie_engine", parse_action_args(args, "inspect")),
            "modeling" | "blender" => ("game_modeling_workbench", json!({"brief": args})),
            "playtest" | "pt" => (
                "game_playtest_lab",
                json!({"action": if args.is_empty() { "create_test_plan" } else { args }}),
            ),
            _ => ("game_design_orchestrator", json!({"prompt": args})),
        };
        self.tool_json(tool, arguments).await
    }
}

fn parse_setting_value(value: &str) -> Value {
    if let Ok(parsed) = serde_json::from_str::<Value>(value) {
        return parsed;
    }
    Value::String(value.to_string())
}

fn read_rules(path: &Path) -> ReverieResult<Vec<String>> {
    if !path.is_file() {
        return Ok(Vec::new());
    }
    Ok(std::fs::read_to_string(path)?
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect())
}

fn write_rules(path: &Path, rules: &[String]) -> ReverieResult<()> {
    std::fs::write(path, format!("{}\n", rules.join("\n")))?;
    Ok(())
}

fn render_rules(rules: &[String]) -> String {
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

fn provider_catalog(provider: &str) -> Vec<ProviderModel> {
    match provider {
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

fn select_model_name(config: &Config, query: &str) -> ReverieResult<String> {
    if query.trim().is_empty() {
        return Err(ReverieError::InvalidInput(
            "model name or index is required".to_string(),
        ));
    }
    if let Ok(index) = query.parse::<usize>() {
        return config
            .models
            .get(index)
            .map(|model| model.name.clone())
            .ok_or_else(|| {
                ReverieError::InvalidInput(format!("model index out of range: {index}"))
            });
    }
    config
        .models
        .iter()
        .find(|model| model.name == query || model.model == query)
        .map(|model| model.name.clone())
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not found: {query}")))
}

fn parse_model_config(args: &str) -> ReverieResult<ModelConfig> {
    if args.trim_start().starts_with('{') {
        return Ok(serde_json::from_str(args)?);
    }
    let mut map = serde_json::Map::new();
    for part in args.split_whitespace() {
        if let Some((key, value)) = part.split_once('=') {
            map.insert(key.to_string(), Value::String(value.to_string()));
        }
    }
    let model_id = map
        .get("model")
        .and_then(Value::as_str)
        .ok_or_else(|| ReverieError::InvalidInput("model=<id> is required".to_string()))?
        .to_string();
    let name = map
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or(&model_id)
        .to_string();
    Ok(ModelConfig {
        name,
        model: model_id,
        base_url: map
            .get("base_url")
            .and_then(Value::as_str)
            .map(str::to_string),
        api_key_env: map
            .get("api_key_env")
            .and_then(Value::as_str)
            .map(str::to_string),
        provider: map
            .get("provider")
            .and_then(Value::as_str)
            .map(str::to_string)
            .or_else(|| Some("standard".to_string())),
        transport: map
            .get("transport")
            .and_then(Value::as_str)
            .map(str::to_string)
            .or_else(|| Some("openai".to_string())),
        supports_vision: map
            .get("supports_vision")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    })
}

fn read_json_array(path: &Path) -> ReverieResult<Vec<Value>> {
    if !path.is_file() {
        return Ok(Vec::new());
    }
    Ok(serde_json::from_str(&std::fs::read_to_string(path)?)?)
}

fn write_json_array(path: &Path, values: &[Value]) -> ReverieResult<()> {
    std::fs::write(path, serde_json::to_string_pretty(values)?)?;
    Ok(())
}

fn parse_action_args(args: &str, default_action: &str) -> Value {
    if args.trim_start().starts_with('{') {
        serde_json::from_str(args).unwrap_or_else(|_| json!({"action": default_action}))
    } else if args.trim().is_empty() {
        json!({"action": default_action})
    } else {
        json!({"action": args.trim()})
    }
}

pub fn command_help() -> String {
    render_help()
}

fn parse_inline_tool_invocation(prompt: &str) -> Option<ToolInvocation> {
    let trimmed = prompt.trim();
    let raw = trimmed
        .strip_prefix("tool:")
        .or_else(|| trimmed.strip_prefix("TOOL:"))
        .unwrap_or(trimmed);
    let value = serde_json::from_str::<serde_json::Value>(raw).ok()?;
    if value.get("name").is_some() {
        return serde_json::from_value(value).ok();
    }
    let name = value.get("tool")?.as_str()?.to_string();
    let arguments = value
        .get("arguments")
        .cloned()
        .or_else(|| value.get("args").cloned())
        .unwrap_or_else(|| serde_json::json!({}));
    Some(ToolInvocation { name, arguments })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_inline_tool_invocation() {
        let parsed =
            parse_inline_tool_invocation(r#"tool:{"tool":"count_tokens","args":{"text":"abcd"}}"#)
                .expect("tool invocation");
        assert_eq!(parsed.name, "count_tokens");
        assert_eq!(parsed.arguments["text"], "abcd");
    }
}
