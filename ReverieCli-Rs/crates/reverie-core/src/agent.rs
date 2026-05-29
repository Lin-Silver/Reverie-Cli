use crate::cli_commands::{render_help, render_mode_list, render_tool_list};
use crate::config::{project_data_dir, Config, ConfigManager, ModelConfig};
use crate::llm::{
    build_openai_tool_definitions, build_request_extra_body,
    extract_anthropic_tool_calls, extract_openai_tool_calls,
    sanitize_prompt_output_text, send_model_compatible, send_model_streaming_compatible,
    user_content_with_inline_images, ChatMessage, ChatRequest, ModelStreamEvent,
};
use crate::modes::{normalize_mode, Mode};
use crate::providers::{
    codex_catalog, modelscope_catalog, normalize_reasoning_effort, nvidia_catalog, ProviderModel,
};
use crate::rules::{render_rules, RulesManager};
use crate::session::{
    CheckpointStore, OperationStore, PromptRunResult, SessionMessage, SessionStore,
};
use crate::settings_catalog::{apply_setting, setting_items};
use crate::{ReverieError, ReverieResult};
use reverie_context::CodebaseIndexer;
use reverie_mcp::{McpRegistry, McpServerConfig};
use reverie_sandbox::SandboxManager;
use reverie_skills::SkillLoader;
use reverie_subagents::{SubagentManager, SubagentSpawnRequest};
use reverie_tools::{execute_builtin_tool, ToolInvocation, ToolRegistry};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

/// Maximum number of tool-call rounds before forcing a text response.
pub const MAX_TOOL_ROUNDS: usize = 25;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentOptions {
    pub mode: Mode,
    pub no_index: bool,
    #[serde(default)]
    pub sandbox_enabled: bool,
    #[serde(default = "default_max_tool_rounds")]
    pub max_tool_rounds: usize,
}

fn default_max_tool_rounds() -> usize {
    MAX_TOOL_ROUNDS
}

pub struct ReverieAgent {
    project_root: PathBuf,
    options: AgentOptions,
    mcp_registry: McpRegistry,
    skill_loader: Option<SkillLoader>,
    subagent_manager: std::sync::Mutex<SubagentManager>,
    sandbox_manager: SandboxManager,
}

impl ReverieAgent {
    pub fn new(project_root: impl AsRef<Path>, options: AgentOptions) -> Self {
        let project_root = project_root.as_ref().to_path_buf();
        let mcp_registry = McpRegistry::new(&project_root);
        let skill_loader = SkillLoader::new(&project_root).ok();
        let subagent_manager = SubagentManager::default();
        let mut sandbox_manager = SandboxManager::new();
        if options.sandbox_enabled {
            let mut policy = reverie_sandbox::SandboxPolicy {
                name: "agent".to_string(),
                ..Default::default()
            };
            let project_str = project_root.to_string_lossy().to_string();
            policy.file_rules.insert(
                0,
                reverie_sandbox::policy::FileRule::allow_read_write(&project_str),
            );
            sandbox_manager.set_default_policy(policy);
        }
        Self {
            project_root,
            options,
            mcp_registry,
            skill_loader,
            subagent_manager: std::sync::Mutex::new(subagent_manager),
            sandbox_manager,
        }
    }

    /// Initialize MCP servers from config. Call once after construction.
    pub async fn initialize_mcp(&mut self) -> ReverieResult<()> {
        let config = ConfigManager::new(&self.project_root, false).load()?;
        if let Some(mcp_config) = config.extra.get("mcp_servers") {
            if let Ok(servers) = serde_json::from_value::<Vec<McpServerConfig>>(mcp_config.clone())
            {
                for server in servers {
                    if let Err(err) = self.mcp_registry.add_server(server).await {
                        tracing::warn!("Failed to add MCP server: {}", err);
                    }
                }
            }
        }
        if let Err(err) = self.mcp_registry.initialize_all().await {
            tracing::warn!("MCP initialization errors: {}", err);
        }
        Ok(())
    }

    /// Initialize skill loader cache. Call once after construction.
    pub async fn initialize_skills(&mut self) -> ReverieResult<()> {
        if let Some(loader) = &self.skill_loader {
            if let Err(err) = loader.reload().await {
                tracing::warn!("Skill reload error: {}", err);
            }
        }
        Ok(())
    }

    pub async fn run_prompt_once(&self, prompt: &str) -> ReverieResult<PromptRunResult> {
        self.run_prompt_internal(prompt, None).await
    }

    pub async fn run_prompt_streaming(
        &self,
        prompt: &str,
        stream_sink: &mut (dyn FnMut(ModelStreamEvent) + Send),
    ) -> ReverieResult<PromptRunResult> {
        self.run_prompt_internal(prompt, Some(stream_sink)).await
    }

    async fn run_prompt_internal(
        &self,
        prompt: &str,
        stream_sink: Option<&mut (dyn FnMut(ModelStreamEvent) + Send)>,
    ) -> ReverieResult<PromptRunResult> {
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
        let store = self.session_store();
        let session = store.ensure_active(
            "Rust Session",
            self.project_root.clone(),
            self.options.mode.canonical().to_string(),
        )?;

        let run = if let Some(command) = trimmed.strip_prefix('/') {
            let output = self.handle_command(command).await?;
            AgentRunOutput::simple(prompt, &output)
        } else if let Some(invocation) = parse_inline_tool_invocation(trimmed) {
            let result = execute_builtin_tool(&self.project_root, invocation)
                .await
                .map_err(|err| ReverieError::Unsupported(err.to_string()))?;
            let output = serde_json::to_string_pretty(&result)?;
            AgentRunOutput {
                text: output.clone(),
                transcript_messages: vec![
                    SessionMessage::new("user", json!(prompt)),
                    SessionMessage::new("tool", serde_json::to_value(&result)?),
                    SessionMessage::new("assistant", json!(output)),
                ],
                events: vec![json!({
                    "type": "inline_tool",
                    "success": result.success,
                    "error": result.error
                })],
            }
        } else {
            match stream_sink {
                Some(sink) => {
                    self.run_model_or_local_fallback(trimmed, &session.id, Some(sink))
                        .await?
                }
                None => {
                    self.run_model_or_local_fallback(trimmed, &session.id, None)
                        .await?
                }
            }
        };
        events.extend(run.events);
        store.append_messages(&session.id, &run.transcript_messages, &events)?;
        let output_text = sanitize_prompt_output_text(&run.text);

        Ok(PromptRunResult {
            success: true,
            output_text,
            error: None,
            mode: self.options.mode.canonical().to_string(),
            project_root: self.project_root.clone(),
            events,
        })
    }

    async fn run_model_or_local_fallback(
        &self,
        prompt: &str,
        session_id: &str,
        mut stream_sink: Option<&mut (dyn FnMut(ModelStreamEvent) + Send)>,
    ) -> ReverieResult<AgentRunOutput> {
        let config = ConfigManager::new(&self.project_root, false).load()?;
        let Some(model) = config.active_model.clone() else {
            let output = format!(
                "Reverie Rust agent received prompt in {} mode.\n\n{}",
                self.options.mode.display_name(),
                prompt
            );
            return Ok(AgentRunOutput::simple(prompt, &output));
        };
        let visible_tools = ToolRegistry::builtin().visible_for_mode(self.options.mode.canonical());
        let mut tool_definitions = build_openai_tool_definitions(&visible_tools);

        // Inject MCP tools from connected servers
        if let Ok(mcp_tools) = self.mcp_registry.list_all_tools().await {
            for (server_name, tools) in &mcp_tools {
                for tool in tools {
                    let mcp_tool_name = format!("mcp_{}_{}", server_name, tool.name);
                    let description = tool
                        .description
                        .clone()
                        .unwrap_or_else(|| format!("MCP tool from {}", server_name));
                    let schema = serde_json::to_value(&tool.input_schema).unwrap_or(json!({"type":"object","properties":{}}));
                    tool_definitions.push(json!({
                        "type": "function",
                        "function": {
                            "name": mcp_tool_name,
                            "description": description,
                            "parameters": schema
                        }
                    }));
                }
            }
        }

        let mut events = Vec::new();
        let mut messages = self.context_messages(session_id)?;
        // Inject mode-specific system prompt as the first message
        let mode_prompt = self.options.mode.system_prompt();
        messages.insert(
            0,
            ChatMessage::new("system", json!(mode_prompt)),
        );
        let rules_text = RulesManager::new(&self.project_root).get_rules_text()?;
        if !rules_text.trim().is_empty() {
            messages.insert(
                1,
                ChatMessage::new(
                    "system",
                    json!(format!(
                        "Additional user rules for this Reverie session:\n{}",
                        rules_text
                    )),
                ),
            );
        }
        let user_content = user_content_with_inline_images(&self.project_root, prompt)?;
        messages.push(ChatMessage::new("user", user_content.clone()));

        let mut transcript_messages = vec![SessionMessage::new("user", user_content)];
        let use_streaming = config.stream_responses && stream_sink.is_some();
        let max_rounds = self.options.max_tool_rounds.min(MAX_TOOL_ROUNDS);
        let extra_body = build_request_extra_body(&config, &model);

        // Multi-turn tool execution loop
        for _round in 0..max_rounds {
            let response = if use_streaming {
                let mut captured_events = Vec::new();
                let response = send_model_streaming_compatible(
                    &config,
                    ChatRequest {
                        model: model.clone(),
                        messages: messages.clone(),
                        tools: tool_definitions.clone(),
                        stream: true,
                        extra_body: extra_body.clone(),
                    },
                    |event| {
                        captured_events.push(json!({
                            "type": "stream",
                            "event": event.clone()
                        }));
                        if let Some(sink) = stream_sink.as_deref_mut() {
                            sink(event);
                        }
                    },
                )
                .await?;
                events.extend(captured_events);
                response
            } else {
                send_model_compatible(
                    &config,
                    ChatRequest {
                        model: model.clone(),
                        messages: messages.clone(),
                        tools: tool_definitions.clone(),
                        stream: false,
                        extra_body: extra_body.clone(),
                    },
                )
                .await?
            };

            let mut tool_calls = extract_openai_tool_calls(&response.raw);
            if tool_calls.is_empty() {
                tool_calls = extract_anthropic_tool_calls(&response.raw);
            }

            // No tool calls — final text response, exit loop
            if tool_calls.is_empty() {
                transcript_messages.push(SessionMessage::new(
                    "assistant",
                    json!(response.output_text.clone()),
                ));
                return Ok(AgentRunOutput {
                    text: response.output_text,
                    transcript_messages,
                    events,
                });
            }

            // Process tool calls
            transcript_messages.push(SessionMessage::with_tool_calls(
                "assistant",
                json!(response.output_text.clone()),
                tool_calls.iter().map(|call| call.raw.clone()).collect(),
            ));
            messages.push(ChatMessage::assistant_with_tool_calls(
                tool_calls.iter().map(|call| call.raw.clone()).collect(),
            ));

            for call in tool_calls {
                events.push(json!({
                    "type": "tool_call",
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments
                }));

                if let Some(sink) = stream_sink.as_deref_mut() {
                    sink(ModelStreamEvent::ToolExecStart {
                        id: call.id.clone(),
                        name: call.name.clone(),
                    });
                }

                let result = self
                    .execute_tool_with_integrations(&call.name, call.arguments.clone())
                    .await;

                if let Some(sink) = stream_sink.as_deref_mut() {
                    sink(ModelStreamEvent::ToolExecComplete {
                        id: call.id.clone(),
                        name: call.name.clone(),
                        success: result.success,
                        error: result.error.clone(),
                    });
                }

                let result_text = serde_json::to_string(&result)?;
                transcript_messages.push(SessionMessage::tool_result(
                    call.id.clone(),
                    json!(result_text.clone()),
                ));
                events.push(json!({
                    "type": "tool_result",
                    "id": call.id,
                    "name": call.name,
                    "success": result.success,
                    "error": result.error
                }));
                messages.push(ChatMessage::tool_result(call.id, json!(result_text)));
            }
            // Loop back for the next model call with tool results
        }

        // Exhausted tool rounds — force a final call without tools
        let final_response = send_model_compatible(
            &config,
            ChatRequest {
                model,
                messages,
                tools: Vec::new(),
                stream: false,
                extra_body: extra_body.clone(),
            },
        )
        .await?;
        transcript_messages.push(SessionMessage::new(
            "assistant",
            json!(final_response.output_text.clone()),
        ));
        Ok(AgentRunOutput {
            text: final_response.output_text,
            transcript_messages,
            events,
        })
    }

    /// Execute a single tool invocation routing through MCP, subagents, skills, and sandbox.
    fn execute_tool_with_integrations<'a>(
        &'a self,
        name: &'a str,
        arguments: Value,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = reverie_tools::ToolResult> + 'a>> {
        Box::pin(async move {
        // Route MCP tool calls to the appropriate server
        if let Some(rest) = name.strip_prefix("mcp_") {
            return self.execute_mcp_tool(rest, &arguments).await;
        }

        // Subagent tool — use the real SubagentManager
        if name == "subagent" {
            return self.execute_subagent_tool(&arguments).await;
        }

        // Skill execution — if the tool is skill_lookup with execute action
        if name == "skill_lookup" {
            if let Some("execute") = arguments.get("operation").and_then(Value::as_str) {
                return self.execute_skill_tool(&arguments).await;
            }
        }

        // Sandbox enforcement for file/command operations
        if self.options.sandbox_enabled {
            if let Some(violation) = self.check_sandbox(name, &arguments) {
                return reverie_tools::ToolResult {
                    success: false,
                    output: Value::Null,
                    error: Some(violation),
                };
            }
        }

        // Default: execute as builtin tool
        match execute_builtin_tool(
            &self.project_root,
            ToolInvocation {
                name: name.to_string(),
                arguments,
            },
        )
        .await
        {
            Ok(result) => result,
            Err(err) => reverie_tools::ToolResult {
                success: false,
                output: Value::Null,
                error: Some(err.to_string()),
            },
        }
        })
    }

    /// Route a tool call to an MCP server.
    async fn execute_mcp_tool(&self, rest: &str, arguments: &Value) -> reverie_tools::ToolResult {
        // rest = "{server_name}_{tool_name}", split on first '_'
        let (server_name, tool_name) = match rest.split_once('_') {
            Some(pair) => pair,
            None => {
                return reverie_tools::ToolResult {
                    success: false,
                    output: Value::Null,
                    error: Some(format!("Invalid MCP tool name format: mcp_{rest}")),
                };
            }
        };
        let args_map: std::collections::HashMap<String, Value> =
            serde_json::from_value(arguments.clone()).unwrap_or_default();
        match self
            .mcp_registry
            .call_tool(server_name, tool_name, args_map)
            .await
        {
            Ok(result) => {
                let text = result
                    .content
                    .iter()
                    .filter_map(|c| match c {
                        reverie_mcp::ToolContent::Text { text } => Some(text.as_str()),
                        _ => None,
                    })
                    .collect::<Vec<_>>()
                    .join("\n");
                reverie_tools::ToolResult {
                    success: !result.is_error,
                    output: json!({"text": text, "content": result.content}),
                    error: if result.is_error {
                        Some(text)
                    } else {
                        None
                    },
                }
            }
            Err(err) => reverie_tools::ToolResult {
                success: false,
                output: Value::Null,
                error: Some(err.to_string()),
            },
        }
    }

    /// Execute a subagent via the SubagentManager.
    async fn execute_subagent_tool(&self, arguments: &Value) -> reverie_tools::ToolResult {
        let task = arguments
            .get("prompt")
            .or_else(|| arguments.get("task"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let name = arguments
            .get("subagent_id")
            .or_else(|| arguments.get("name"))
            .and_then(Value::as_str)
            .unwrap_or("default")
            .to_string();

        let request = SubagentSpawnRequest {
            name: name.clone(),
            task: task.clone(),
            project_root: self.project_root.clone(),
            cwd: self.project_root.clone(),
            parent_id: None,
            depth: 0,
            timeout: Some(std::time::Duration::from_secs(300)),
            inherit_env: true,
        };

        // Register the run in the SubagentManager
        let spawn_result = {
            let mut mgr = self.subagent_manager.lock().unwrap();
            mgr.spawn(request)
        };

        let run_id = match spawn_result {
            Ok(result) if result.success => result.run_id,
            Ok(result) => {
                return reverie_tools::ToolResult {
                    success: false,
                    output: Value::Null,
                    error: Some(
                        result
                            .error
                            .unwrap_or_else(|| "Failed to spawn subagent".to_string()),
                    ),
                };
            }
            Err(err) => {
                return reverie_tools::ToolResult {
                    success: false,
                    output: Value::Null,
                    error: Some(format!("SubagentManager error: {err}")),
                };
            }
        };

        // Execute the subagent as a nested single-shot agent prompt
        let sub_agent = ReverieAgent::new(
            &self.project_root,
            AgentOptions {
                mode: normalize_mode("reverie"),
                no_index: true,
                sandbox_enabled: self.options.sandbox_enabled,
                max_tool_rounds: self.options.max_tool_rounds.min(10), // limit sub-depth
            },
        );

        let sub_result = sub_agent.run_prompt_once(&task).await;

        match sub_result {
            Ok(result) => {
                // Mark completed in manager
                {
                    let mut mgr = self.subagent_manager.lock().unwrap();
                    let _ = mgr.complete(&run_id, &result.output_text);
                }

                // Persist the run record
                let artifact_dir = self.project_root.join(".reverie").join("artifacts");
                let _ = std::fs::create_dir_all(&artifact_dir);
                let run_record = json!({
                    "schema": "reverie.subagent_run.v1",
                    "run_id": run_id,
                    "name": name,
                    "task": task,
                    "status": "completed",
                    "output": result.output_text
                });
                let artifact_path = artifact_dir.join("subagent_last_run.json");
                let _ = std::fs::write(
                    &artifact_path,
                    serde_json::to_string_pretty(&run_record).unwrap_or_default(),
                );

                reverie_tools::ToolResult {
                    success: true,
                    output: json!({
                        "run_id": run_id,
                        "name": name,
                        "status": "completed",
                        "output": result.output_text
                    }),
                    error: None,
                }
            }
            Err(err) => {
                // Mark failed in manager
                {
                    let mut mgr = self.subagent_manager.lock().unwrap();
                    let _ = mgr.fail(&run_id, err.to_string());
                }

                reverie_tools::ToolResult {
                    success: false,
                    output: json!({
                        "run_id": run_id,
                        "name": name,
                        "status": "failed",
                        "error": err.to_string()
                    }),
                    error: Some(err.to_string()),
                }
            }
        }
    }

    /// Execute a skill via the SkillLoader/Executor.
    async fn execute_skill_tool(&self, arguments: &Value) -> reverie_tools::ToolResult {
        let skill_name = arguments
            .get("query")
            .or_else(|| arguments.get("skill_name"))
            .and_then(Value::as_str)
            .unwrap_or_default();

        let Some(loader) = &self.skill_loader else {
            return reverie_tools::ToolResult {
                success: false,
                output: Value::Null,
                error: Some("Skill loader not initialized".to_string()),
            };
        };

        match loader.get(skill_name).await {
            Some(skill) => {
                let context = reverie_skills::SkillInvocationContext {
                    project_root: self.project_root.clone(),
                    cwd: self.project_root.clone(),
                    skill_name: skill.name.clone(),
                    arguments: std::collections::HashMap::new(),
                };
                let executor = reverie_skills::SkillExecutor::new(
                    SkillLoader::new(&self.project_root).unwrap(),
                );
                match executor.execute(&skill.name, context).await {
                    Ok(result) => reverie_tools::ToolResult {
                        success: result.success,
                        output: json!({
                            "skill": skill.name,
                            "output": result.output,
                            "errors": result.errors
                        }),
                        error: if result.success {
                            None
                        } else {
                            Some(result.errors.join("; "))
                        },
                    },
                    Err(err) => reverie_tools::ToolResult {
                        success: false,
                        output: Value::Null,
                        error: Some(err.to_string()),
                    },
                }
            }
            None => reverie_tools::ToolResult {
                success: false,
                output: json!({"available_skills": loader.list_all().await.iter().map(|s| &s.name).collect::<Vec<_>>()}),
                error: Some(format!("Skill not found: {skill_name}")),
            },
        }
    }

    /// Check sandbox policy before executing a file/command tool.
    fn check_sandbox(&self, tool_name: &str, arguments: &Value) -> Option<String> {
        // Create a temporary sandbox instance for checking
        let policy = self.sandbox_manager.get_default_policy().clone();
        let mut instance =
            reverie_sandbox::manager::SandboxInstance::new("check".to_string(), policy);

        match tool_name {
            "file_ops" | "create_file" | "str_replace_editor" => {
                if let Some(path_str) = arguments
                    .get("path")
                    .or_else(|| arguments.get("file_path"))
                    .and_then(Value::as_str)
                {
                    let target = self.project_root.join(path_str);
                    let mode = if tool_name == "file_ops"
                        && arguments
                            .get("action")
                            .and_then(Value::as_str)
                            .unwrap_or("read")
                            == "read"
                    {
                        reverie_sandbox::policy::FileAccessMode::Read
                    } else {
                        reverie_sandbox::policy::FileAccessMode::ReadWrite
                    };
                    if let Err(err) = instance.check_file_access(&target, mode) {
                        return Some(format!("Sandbox: {err}"));
                    }
                }
            }
            "delete_file" => {
                if let Some(path_str) = arguments.get("path").and_then(Value::as_str) {
                    let target = self.project_root.join(path_str);
                    if let Err(err) = instance
                        .check_file_access(&target, reverie_sandbox::policy::FileAccessMode::Write)
                    {
                        return Some(format!("Sandbox: {err}"));
                    }
                }
            }
            "command_exec" => {
                if let Some(cmd) = arguments.get("command").and_then(Value::as_str) {
                    if let Err(err) = instance.check_command(cmd) {
                        return Some(format!("Sandbox: {err}"));
                    }
                }
            }
            _ => {}
        }
        None
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

    fn session_store(&self) -> SessionStore {
        SessionStore::new(project_data_dir(&self.project_root).join("sessions"))
    }

    fn context_messages(&self, session_id: &str) -> ReverieResult<Vec<ChatMessage>> {
        use crate::context_compaction::{compact_session_messages, compaction_config_from_extras};

        let store = self.session_store();
        let config = ConfigManager::new(&self.project_root, false).load()?;

        // Load full transcript from session store
        let raw_messages = store.compacted_messages_for_context(session_id, usize::MAX)?;
        // Apply context compaction if configured (default: enabled, sliding window)
        let compacted = match compaction_config_from_extras(&config.extra) {
            Some(cc) => compact_session_messages(&raw_messages, &cc),
            None => raw_messages, // compaction disabled
        };

        let mut messages = Vec::new();
        for message in compacted {
            match message.role.as_str() {
                "assistant" if !message.tool_calls.is_empty() => {
                    messages.push(ChatMessage::assistant_with_tool_calls(message.tool_calls));
                }
                "tool" => messages.push(ChatMessage {
                    role: "tool".to_string(),
                    content: message.content,
                    tool_call_id: message.tool_call_id,
                    tool_calls: Vec::new(),
                }),
                "user" | "assistant" | "system" => {
                    messages.push(ChatMessage::new(message.role, message.content));
                }
                _ => {}
            }
        }
        Ok(messages)
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
        let manager = RulesManager::new(&self.project_root);
        let rules = manager.get_rules()?;
        let mut parts = args.trim().splitn(2, char::is_whitespace);
        let action = parts.next().unwrap_or_default();
        let rest = parts.next().unwrap_or_default().trim();
        match action {
            "" | "list" | "ls" => Ok(render_rules(&rules)),
            "add" => {
                if rest.is_empty() {
                    return Ok("Usage: /rules add <text>".to_string());
                }
                let updated = manager.add_rule(rest)?;
                Ok(format!("Rule added. {} rule(s) active.", updated.len()))
            }
            "remove" | "delete" => {
                let index = rest.parse::<usize>().map_err(|_| {
                    ReverieError::InvalidInput("rule index must be a number".to_string())
                })?;
                let (removed, _updated) = manager.remove_rule(index)?;
                Ok(format!("Removed rule {index}: {removed}"))
            }
            "path" | "edit" => {
                let path = manager.rules_txt_path();
                if !path.exists() {
                    manager.set_rules(&[])?;
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

struct AgentRunOutput {
    text: String,
    transcript_messages: Vec<SessionMessage>,
    events: Vec<Value>,
}

impl AgentRunOutput {
    fn simple(prompt: &str, output: &str) -> Self {
        Self {
            text: output.to_string(),
            transcript_messages: vec![
                SessionMessage::new("user", json!(prompt)),
                SessionMessage::new("assistant", json!(output)),
            ],
            events: Vec::new(),
        }
    }
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
