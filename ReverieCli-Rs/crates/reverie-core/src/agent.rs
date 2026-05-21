use crate::cli_commands::{render_help, render_mode_list, render_tool_list};
use crate::config::{project_data_dir, ConfigManager};
use crate::llm::{
    build_openai_tool_definitions, extract_anthropic_tool_calls, extract_openai_tool_calls,
    sanitize_prompt_output_text, send_model_compatible, ChatMessage, ChatRequest,
};
use crate::modes::{normalize_mode, Mode};
use crate::session::PromptRunResult;
use crate::session::{CheckpointStore, OperationStore, SessionStore};
use crate::{ReverieError, ReverieResult};
use reverie_context::CodebaseIndexer;
use reverie_tools::{execute_builtin_tool, ToolInvocation, ToolRegistry};
use serde::{Deserialize, Serialize};
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
        if config.model_source != "standard" {
            return Ok(format!(
                "Rust runtime recognized model source `{}` with active model `{}`. Native provider transport for this source is still migrating.\n\n{}",
                config.model_source, model, prompt
            ));
        }
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
                "Project: {}\nMode: {}\nRuntime: Rust",
                self.project_root.display(),
                self.options.mode.display_name()
            )),
            "mode" if args.is_empty() => Ok(render_mode_list(self.options.mode)),
            "mode" => Ok(format!(
                "Requested mode: {}",
                normalize_mode(args).canonical()
            )),
            "tools" => Ok(render_tool_list(self.options.mode)),
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
            "codex" | "nvidia" | "modelscope" | "geminicli" | "model" => Ok(format!(
                "/{name} provider command is recognized; interactive credential and selector flows are migrating to Rust."
            )),
            "sessions" | "history" => {
                let store = SessionStore::new(project_data_dir(&self.project_root).join("sessions"));
                Ok(serde_json::to_string_pretty(&store.list()?)?)
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
            "gdd" | "assets" | "blueprint" | "bp" | "scaffold" | "engine" | "modeling" | "blender"
            | "playtest" | "pt" => Ok(format!(
                "/{name} Gamer command is recognized; engine-lite and runtime artifact generation are migrating."
            )),
            other => Err(ReverieError::Unsupported(format!(
                "command /{other} is not implemented yet in the Rust agent"
            ))),
        }
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
