use crate::config::{Config, ModelConfig};
use crate::providers::resolve_model;
use crate::{ReverieError, ReverieResult};
use base64::{engine::general_purpose, Engine as _};
use futures::StreamExt;
use regex::Regex;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{Duration, Instant};
use tracing::info;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tool_calls: Vec<Value>,
}

impl ChatMessage {
    pub fn new(role: impl Into<String>, content: Value) -> Self {
        Self {
            role: role.into(),
            content,
            tool_call_id: None,
            tool_calls: Vec::new(),
        }
    }

    pub fn assistant_with_tool_calls(tool_calls: Vec<Value>) -> Self {
        Self {
            role: "assistant".to_string(),
            content: Value::Null,
            tool_call_id: None,
            tool_calls,
        }
    }

    pub fn tool_result(tool_call_id: impl Into<String>, content: Value) -> Self {
        Self {
            role: "tool".to_string(),
            content,
            tool_call_id: Some(tool_call_id.into()),
            tool_calls: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct InlineImage {
    pub path: PathBuf,
    pub media_type: String,
    pub data_base64: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatRequest {
    pub model: String,
    pub messages: Vec<ChatMessage>,
    #[serde(default)]
    pub tools: Vec<Value>,
    #[serde(default)]
    pub stream: bool,
    #[serde(default)]
    pub extra_body: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatResponse {
    pub output_text: String,
    #[serde(default)]
    pub raw: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub usage: Option<TokenUsage>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct TokenUsage {
    pub prompt_tokens: u32,
    pub completion_tokens: u32,
    pub total_tokens: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "type")]
pub enum ModelStreamEvent {
    Start {
        model: String,
    },
    Content {
        content: String,
    },
    ToolCallDelta {
        index: usize,
        id: Option<String>,
        name: Option<String>,
        arguments_delta: String,
    },
    End {
        finish_reason: Option<String>,
    },
    Recovered {
        message: String,
    },
    RetryScheduled {
        message: String,
        attempt: u8,
        max_attempts: u8,
        retry_after_seconds: u64,
    },
    ToolExecStart {
        id: String,
        name: String,
    },
    ToolExecComplete {
        id: String,
        name: String,
        success: bool,
        error: Option<String>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ToolCallRequest {
    pub id: String,
    pub name: String,
    pub arguments: Value,
    pub raw: Value,
}

pub fn validate_and_sanitize_payload(mut payload: Value) -> ReverieResult<Value> {
    let object = payload
        .as_object_mut()
        .ok_or_else(|| ReverieError::InvalidInput("chat payload must be an object".to_string()))?;
    if !object.contains_key("model") {
        return Err(ReverieError::InvalidInput(
            "chat payload missing model".to_string(),
        ));
    }
    if !object.get("messages").map(Value::is_array).unwrap_or(false) {
        return Err(ReverieError::InvalidInput(
            "chat payload missing messages array".to_string(),
        ));
    }
    if object.get("tools").map(Value::is_null).unwrap_or(false) {
        object.remove("tools");
    }
    Ok(payload)
}

pub fn compact_payload_for_plain_chat(payload: &Value) -> Value {
    let mut cloned = payload.clone();
    if let Some(object) = cloned.as_object_mut() {
        object.remove("tools");
        object.remove("tool_choice");
        if let Some(messages) = object.get_mut("messages").and_then(Value::as_array_mut) {
            for message in messages {
                if let Some(obj) = message.as_object_mut() {
                    obj.remove("tool_calls");
                    if obj.get("role").and_then(Value::as_str) == Some("tool") {
                        obj.insert("role".to_string(), json!("user"));
                    }
                }
            }
        }
    }
    cloned
}

pub fn encode_stream_event(event_type: &str, payload: Value) -> String {
    json!({
        "type": event_type,
        "payload": payload
    })
    .to_string()
}

pub fn decode_stream_event(chunk: &str) -> Option<Value> {
    let trimmed = chunk.trim();
    if trimmed.is_empty() {
        return None;
    }
    if let Some(rest) = trimmed.strip_prefix("data:") {
        let rest = rest.trim();
        if rest == "[DONE]" {
            return Some(json!({"type": "done"}));
        }
        return serde_json::from_str(rest).ok();
    }
    serde_json::from_str(trimmed).ok()
}

pub fn parse_tool_arguments(raw: &str) -> Value {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return json!({});
    }
    if let Ok(value) = serde_json::from_str::<Value>(trimmed) {
        return value;
    }
    // Salvage common provider output with trailing text after a JSON object.
    if let Some(end) = trimmed.rfind('}') {
        if let Ok(value) = serde_json::from_str::<Value>(&trimmed[..=end]) {
            return value;
        }
    }
    json!({"raw": raw})
}

pub fn user_content_with_inline_images(project_root: &Path, prompt: &str) -> ReverieResult<Value> {
    let images = resolve_inline_images(project_root, prompt)?;
    if images.is_empty() {
        return Ok(json!(prompt));
    }
    let mut blocks = vec![json!({"type": "text", "text": prompt})];
    for image in images {
        blocks.push(json!({
            "type": "image_url",
            "image_url": {
                "url": format!("data:{};base64,{}", image.media_type, image.data_base64),
                "detail": "auto"
            },
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": image.data_base64
            },
            "path": image.path
        }));
    }
    Ok(Value::Array(blocks))
}

pub fn resolve_inline_images(project_root: &Path, prompt: &str) -> ReverieResult<Vec<InlineImage>> {
    let markdown_re =
        Regex::new(r"!\[[^\]]*\]\((?P<path>[^)\s]+(?:\s+[^)]*)?)\)").expect("static regex");
    let at_re = Regex::new(r"(?i)(?:^|\s)@(?P<path>[^\s]+?\.(?:png|jpe?g|gif|webp))")
        .expect("static regex");
    let mut raw_paths = Vec::new();
    for capture in markdown_re.captures_iter(prompt) {
        if let Some(path) = capture.name("path") {
            raw_paths.push(path.as_str().trim().trim_matches('"').to_string());
        }
    }
    for capture in at_re.captures_iter(prompt) {
        if let Some(path) = capture.name("path") {
            raw_paths.push(path.as_str().trim().trim_matches('"').to_string());
        }
    }

    let mut images = Vec::new();
    for raw in raw_paths {
        if raw.starts_with("http://") || raw.starts_with("https://") || raw.starts_with("data:") {
            continue;
        }
        let path = if Path::new(&raw).is_absolute() {
            PathBuf::from(&raw)
        } else {
            project_root.join(&raw)
        };
        if !path.is_file() {
            continue;
        }
        let Some(media_type) = media_type_for_path(&path) else {
            continue;
        };
        let bytes = std::fs::read(&path)?;
        images.push(InlineImage {
            path,
            media_type: media_type.to_string(),
            data_base64: general_purpose::STANDARD.encode(bytes),
        });
    }
    Ok(images)
}

pub fn build_openai_tool_definitions(tools: &[reverie_tools::ToolSpec]) -> Vec<Value> {
    tools
        .iter()
        .map(|tool| {
            json!({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": builtin_tool_parameter_schema(&tool.name)
                }
            })
        })
        .collect()
}

fn builtin_tool_parameter_schema(name: &str) -> Value {
    match name {
        "file_ops" => json!({
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["read", "list", "exists", "info", "mkdir"]},
                "path": {"type": "string"}
            },
            "required": []
        }),
        "create_file" => json!({
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"}
            },
            "required": ["path"]
        }),
        "delete_file" => json!({
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "confirm_delete": {"type": "boolean"}
            },
            "required": ["path", "confirm_delete"]
        }),
        "str_replace_editor" => json!({
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": ["view", "create", "str_replace", "insert"]},
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
                "insert_line": {"type": "integer", "minimum": 1},
                "overwrite": {"type": "boolean"}
            },
            "required": ["command", "path"]
        }),
        "command_exec" => json!({
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "working_dir": {"type": "string"}
            },
            "required": ["command"]
        }),
        "codebase-retrieval" => json!({
            "type": "object",
            "properties": {
                "query_type": {"type": "string", "enum": ["search", "outline", "symbol", "dependencies"]},
                "query": {"type": "string"}
            },
            "required": []
        }),
        "git-commit-retrieval" => json!({
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "branch": {"type": "string"}
            },
            "required": []
        }),
        "count_tokens" => json!({
            "type": "object",
            "properties": {
                "text": {"type": "string"}
            },
            "required": ["text"]
        }),
        "switch_mode" => json!({
            "type": "object",
            "properties": {
                "mode": {"type": "string"}
            },
            "required": ["mode"]
        }),
        "web_fetch" => json!({
            "type": "object",
            "properties": {
                "url": {"type": "string"}
            },
            "required": ["url"]
        }),
        "web_search" => json!({
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "q": {"type": "string"}
            },
            "required": []
        }),
        "task_manager" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "delete", "list", "status", "clear"]},
                "operation": {"type": "string"},
                "tasks": {"type": "array", "items": {"type": "object"}},
                "name": {"type": "string"},
                "title": {"type": "string"},
                "target": {"type": "string"},
                "task_id": {"type": "string"},
                "id": {"type": "string"},
                "status": {"type": "string"},
                "state": {"type": "string"}
            },
            "required": []
        }),
        "skill_lookup" => json!({
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["search", "get", "execute", "list"]},
                "query": {"type": "string"},
                "skill_name": {"type": "string"}
            },
            "required": []
        }),
        "list_mcp_resources" => json!({
            "type": "object",
            "properties": {
                "server": {"type": "string"}
            },
            "required": []
        }),
        "read_mcp_resource" => json!({
            "type": "object",
            "properties": {
                "uri": {"type": "string"}
            },
            "required": ["uri"]
        }),
        "text_to_image" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["generate", "list_models", "status"]},
                "prompt": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "model": {"type": "string"}
            },
            "required": []
        }),
        "subagent" => json!({
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The task for the subagent to execute."},
                "task": {"type": "string"},
                "subagent_id": {"type": "string"},
                "name": {"type": "string"}
            },
            "required": ["prompt"]
        }),
        "userInput" => json!({
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The question to ask the user."},
                "options": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["prompt"]
        }),
        "tool_catalog" => json!({
            "type": "object",
            "properties": {
                "mode": {"type": "string"},
                "category": {"type": "string"}
            },
            "required": []
        }),
        "game_design_orchestrator" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["compile_request", "add_system", "advance_stage", "set_runtime_target", "verify", "status"]},
                "prompt": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "target": {"type": "string"},
                "check_name": {"type": "string"},
                "score": {"type": "number"}
            },
            "required": []
        }),
        "game_gdd_manager" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update_section", "add_system", "add_content_pillar", "status"]},
                "content": {"type": "string"},
                "title": {"type": "string"},
                "section_id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": "string"}
            },
            "required": []
        }),
        "story_design" | "level_design" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "status"]},
                "content": {"type": "string"},
                "brief": {"type": "string"},
                "title": {"type": "string"}
            },
            "required": []
        }),
        "game_project_scaffolder" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "inspect", "status"]},
                "engine": {"type": "string"},
                "project_name": {"type": "string"},
                "template": {"type": "string"}
            },
            "required": []
        }),
        "reverie_engine" | "reverie_engine_lite" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "inspect", "add_scene", "add_entity", "register_asset", "validate", "scaffold"]},
                "project_name": {"type": "string"},
                "scene_name": {"type": "string"},
                "entity_name": {"type": "string"},
                "asset_path": {"type": "string"}
            },
            "required": []
        }),
        "game_playtest_lab" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create_test_plan", "add_check", "run_check", "add_quality_gate", "status"]},
                "test_name": {"type": "string"},
                "check_name": {"type": "string"},
                "result": {"type": "string"},
                "gate_name": {"type": "string"},
                "threshold": {"type": "number"}
            },
            "required": []
        }),
        "game_asset_manager" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "update", "list", "set_notes", "status"]},
                "name": {"type": "string"},
                "asset_type": {"type": "string"},
                "path": {"type": "string"},
                "notes": {"type": "string"},
                "filter_type": {"type": "string"}
            },
            "required": []
        }),
        "game_asset_packer" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["inspect", "pack", "list"]},
                "directory": {"type": "string"},
                "output": {"type": "string"}
            },
            "required": []
        }),
        "game_config_editor" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "update", "list"]},
                "path": {"type": "string"},
                "key": {"type": "string"},
                "value": {}
            },
            "required": []
        }),
        "game_balance_analyzer" | "game_math_simulator" | "game_stats_analyzer" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["analyze", "add_dataset", "simulate", "status"]},
                "data": {},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "parameters": {"type": "object"}
            },
            "required": []
        }),
        "game_modeling_workbench" | "blender_modeling_workbench" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "list", "export", "status"]},
                "brief": {"type": "string"},
                "name": {"type": "string"},
                "format": {"type": "string"}
            },
            "required": []
        }),
        "atlas_delivery_orchestrator" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "add_slice", "update_slice", "add_blocker", "resolve_blocker", "checkpoint", "add_milestone", "register_document"]},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string"},
                "blocker_id": {"type": "string"},
                "document_type": {"type": "string"},
                "path": {"type": "string"}
            },
            "required": []
        }),
        "ask_clarification" => json!({
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "context": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["question"]
        }),
        "novel_context_manager" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add_character", "update_character", "add_location", "add_timeline_event", "add_thread", "resolve_thread", "add_chapter", "update_chapter", "search", "summary"]},
                "name": {"type": "string"},
                "description": {"type": "string"},
                "traits": {"type": "array", "items": {"type": "string"}},
                "chapter_number": {"type": "integer"},
                "query": {"type": "string"}
            },
            "required": []
        }),
        "consistency_checker" => json!({
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["all", "characters", "threads", "timeline", "locations"]}
            },
            "required": []
        }),
        "plot_analyzer" => json!({
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["all", "arcs", "pacing", "tension", "threads"]}
            },
            "required": []
        }),
        "task_boundary" => json!({
            "type": "object",
            "properties": {
                "phase": {"type": "string"},
                "status": {"type": "string"},
                "summary": {"type": "string"}
            },
            "required": ["phase"]
        }),
        "notify_user" => json!({
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "level": {"type": "string", "enum": ["info", "warning", "error", "success"]}
            },
            "required": ["message"]
        }),
        "computer_control" => json!({
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["screenshot", "click", "type", "key", "scroll", "move"]},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "text": {"type": "string"},
                "key": {"type": "string"}
            },
            "required": ["action"]
        }),
        _ => json!({"type": "object", "properties": {}, "required": []}),
    }
}

pub fn extract_openai_output_text(response: &Value) -> String {
    if let Some(text) = response
        .pointer("/choices/0/message/content")
        .and_then(Value::as_str)
    {
        return text.to_string();
    }
    if let Some(text) = response.pointer("/output_text").and_then(Value::as_str) {
        return text.to_string();
    }
    response
        .get("choices")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|choice| choice.pointer("/delta/content").and_then(Value::as_str))
        .collect::<Vec<_>>()
        .join("")
}

pub fn extract_openai_tool_calls(response: &Value) -> Vec<ToolCallRequest> {
    response
        .pointer("/choices/0/message/tool_calls")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|call| {
            let name = call.pointer("/function/name").and_then(Value::as_str)?;
            let id = call
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or(name)
                .to_string();
            let raw_args = call
                .pointer("/function/arguments")
                .and_then(Value::as_str)
                .unwrap_or("{}");
            Some(ToolCallRequest {
                id,
                name: name.to_string(),
                arguments: parse_tool_arguments(raw_args),
                raw: call.clone(),
            })
        })
        .collect()
}

pub fn extract_anthropic_output_text(response: &Value) -> String {
    response
        .get("content")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|block| block.get("type").and_then(Value::as_str) == Some("text"))
        .filter_map(|block| block.get("text").and_then(Value::as_str))
        .collect::<Vec<_>>()
        .join("")
}

pub fn extract_anthropic_tool_calls(response: &Value) -> Vec<ToolCallRequest> {
    response
        .get("content")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|block| block.get("type").and_then(Value::as_str) == Some("tool_use"))
        .filter_map(|block| {
            let name = block.get("name").and_then(Value::as_str)?;
            let id = block
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or(name)
                .to_string();
            Some(ToolCallRequest {
                id,
                name: name.to_string(),
                arguments: block.get("input").cloned().unwrap_or_else(|| json!({})),
                raw: block.clone(),
            })
        })
        .collect()
}

pub fn build_anthropic_payload(model: &str, request: ChatRequest) -> Value {
    let messages = request
        .messages
        .into_iter()
        .filter(|message| message.role != "system")
        .map(|message| {
            let role = if message.role == "assistant" {
                "assistant"
            } else {
                "user"
            };
            let content = if message.role == "assistant" && !message.tool_calls.is_empty() {
                Value::Array(message.tool_calls)
            } else if message.role == "tool" {
                json!([{
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id.unwrap_or_default(),
                    "content": content_to_text(&message.content)
                }])
            } else if message.content.is_array() {
                openai_content_to_anthropic(&message.content)
            } else {
                json!(content_to_text(&message.content))
            };
            json!({
                "role": role,
                "content": content
            })
        })
        .collect::<Vec<_>>();
    let tools = request
        .tools
        .into_iter()
        .filter_map(openai_tool_to_anthropic_tool)
        .collect::<Vec<_>>();
    let mut payload = json!({
        "model": model,
        "max_tokens": request
            .extra_body
            .get("max_tokens")
            .and_then(Value::as_u64)
            .unwrap_or(4096),
        "messages": messages
    });
    if !tools.is_empty() {
        payload["tools"] = Value::Array(tools);
    }
    if let Some(object) = payload.as_object_mut() {
        if let Some(extra) = request.extra_body.as_object() {
            for (key, value) in extra {
                if key != "max_tokens" {
                    object.insert(key.clone(), value.clone());
                }
            }
        }
    }
    payload
}

fn openai_tool_to_anthropic_tool(tool: Value) -> Option<Value> {
    let function = tool.get("function")?;
    Some(json!({
        "name": function.get("name")?.clone(),
        "description": function.get("description").cloned().unwrap_or_else(|| json!("")),
        "input_schema": function
            .get("parameters")
            .cloned()
            .unwrap_or_else(|| json!({"type": "object", "properties": {}, "required": []}))
    }))
}

fn content_to_text(content: &Value) -> String {
    match content {
        Value::String(text) => text.clone(),
        Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn openai_content_to_anthropic(content: &Value) -> Value {
    let blocks = content
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|block| match block.get("type").and_then(Value::as_str) {
            Some("text") => Some(json!({
                "type": "text",
                "text": block.get("text").and_then(Value::as_str).unwrap_or_default()
            })),
            Some("image_url") => {
                if let Some(source) = block.get("source") {
                    return Some(json!({
                        "type": "image",
                        "source": source
                    }));
                }
                let url = block
                    .pointer("/image_url/url")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                let (media_type, data) = parse_data_url(url)?;
                Some(json!({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data
                    }
                }))
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    Value::Array(blocks)
}

fn parse_data_url(url: &str) -> Option<(&str, &str)> {
    let rest = url.strip_prefix("data:")?;
    let (media_type, data) = rest.split_once(";base64,")?;
    Some((media_type, data))
}

fn media_type_for_path(path: &Path) -> Option<&'static str> {
    match path
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "png" => Some("image/png"),
        "jpg" | "jpeg" => Some("image/jpeg"),
        "gif" => Some("image/gif"),
        "webp" => Some("image/webp"),
        _ => None,
    }
}

pub fn should_retry_without_tooling(status_code: u16) -> bool {
    matches!(status_code, 400 | 404 | 422)
}

pub fn is_recoverable_stream_exception(message: &str) -> bool {
    let lower = message.to_ascii_lowercase();
    lower.contains("incomplete")
        || lower.contains("connection reset")
        || lower.contains("unexpected eof")
        || lower.contains("stream")
}

pub fn sanitize_prompt_output_text(value: &str) -> String {
    let mut text = value.to_string();
    let think_re = Regex::new(r"(?is)<think>.*?</think>").expect("static regex");
    text = think_re.replace_all(&text, "").into_owned();
    let fenced_re = Regex::new(r"(?is)```thinking.*?```").expect("static regex");
    text = fenced_re.replace_all(&text, "").into_owned();
    for prefix in [
        "Reasoning:",
        "Thinking:",
        "We need answer.",
        "We need respond.",
    ] {
        if text.trim_start().starts_with(prefix) {
            text = text.replacen(prefix, "", 1);
        }
    }
    text.trim().to_string()
}

const RETRY_DELAYS_SECONDS: [u64; 5] = [1, 3, 5, 7, 15];
const REQUEST_RETRY_ATTEMPTS: u8 = RETRY_DELAYS_SECONDS.len() as u8;
const NVIDIA_MIN_REQUEST_INTERVAL: Duration = Duration::from_millis(1500);

static NVIDIA_LAST_REQUEST_AT: OnceLock<tokio::sync::Mutex<Option<Instant>>> = OnceLock::new();

fn is_retryable_error(err: &ReverieError) -> bool {
    match err {
        ReverieError::Http(e) => e
            .status()
            .map(|s| matches!(s.as_u16(), 429 | 500 | 502 | 503 | 504))
            .unwrap_or(true),
        _ => false,
    }
}

async fn wait_for_nvidia_rate_limit() {
    let limiter = NVIDIA_LAST_REQUEST_AT.get_or_init(|| tokio::sync::Mutex::new(None));
    let mut last_request_at = limiter.lock().await;
    if let Some(last) = *last_request_at {
        let elapsed = last.elapsed();
        if elapsed < NVIDIA_MIN_REQUEST_INTERVAL {
            tokio::time::sleep(NVIDIA_MIN_REQUEST_INTERVAL - elapsed).await;
        }
    }
    *last_request_at = Some(Instant::now());
}

/// Retry an async request with fixed backoff capped at five retries.
async fn with_retry<F, Fut>(_max_retries: u8, mut f: F) -> ReverieResult<ChatResponse>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = ReverieResult<ChatResponse>>,
{
    let mut last_err = None;
    let max_retries = REQUEST_RETRY_ATTEMPTS;
    for attempt in 0..=max_retries {
        match f().await {
            Ok(resp) => return Ok(resp),
            Err(err) => {
                if !is_retryable_error(&err) || attempt == max_retries {
                    return Err(err);
                }
                let delay_seconds = RETRY_DELAYS_SECONDS[attempt as usize];
                tracing::warn!(
                    "Request attempt {} failed (retrying in {}s): {}",
                    attempt + 1,
                    delay_seconds,
                    err
                );
                tokio::time::sleep(Duration::from_secs(delay_seconds)).await;
                last_err = Some(err);
            }
        }
    }
    Err(last_err.unwrap_or_else(|| ReverieError::InvalidInput("retry exhausted".to_string())))
}

pub async fn send_openai_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    let config = config.clone();
    let request_model = request.model.clone();
    let request_messages = request.messages.clone();
    let request_tools = request.tools.clone();
    let request_extra = request.extra_body.clone();

    with_retry(REQUEST_RETRY_ATTEMPTS, || {
        let config = config.clone();
        let model = request_model.clone();
        let messages = request_messages.clone();
        let tools = request_tools.clone();
        let extra_body = request_extra.clone();
        async move {
            let selected = config
                .models
                .iter()
                .find(|item| item.name == model || item.model == model)
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!("model not configured: {model}"))
                })?;
            let base_url = selected
                .base_url
                .clone()
                .unwrap_or_else(|| "https://api.openai.com/v1".to_string());
            let key = selected
                .api_key_env
                .as_deref()
                .and_then(|name| std::env::var(name).ok())
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!(
                        "API key env var is not configured or not set for {model}"
                    ))
                })?;
            let mut payload = validate_and_sanitize_payload(json!({
                "model": selected.model,
                "messages": messages,
                "tools": tools,
                "stream": false
            }))?;
            if let Some(object) = payload.as_object_mut() {
                if object
                    .get("tools")
                    .and_then(Value::as_array)
                    .map(|t| t.is_empty())
                    .unwrap_or(false)
                {
                    object.remove("tools");
                } else {
                    object.insert("tool_choice".to_string(), json!("auto"));
                }
                if let Some(extra) = extra_body.as_object() {
                    for (key, value) in extra {
                        object.insert(key.clone(), value.clone());
                    }
                }
            }
            let client = reqwest::Client::builder()
                .timeout(Duration::from_secs(config.api_timeout))
                .build()?;
            let response: Value = client
                .post(format!(
                    "{}/chat/completions",
                    base_url.trim_end_matches('/')
                ))
                .bearer_auth(key)
                .json(&payload)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            let output_text = extract_openai_output_text(&response);
            Ok(ChatResponse {
                output_text,
                raw: response,
                usage: None,
            })
        }
    })
    .await
}

pub async fn send_anthropic_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    let config = config.clone();
    let request_model = request.model.clone();
    let request_messages = request.messages.clone();
    let request_tools = request.tools.clone();
    let request_extra = request.extra_body.clone();

    with_retry(REQUEST_RETRY_ATTEMPTS, || {
        let config = config.clone();
        let model = request_model.clone();
        let messages = request_messages.clone();
        let tools = request_tools.clone();
        let extra_body = request_extra.clone();
        async move {
            let selected = config
                .models
                .iter()
                .find(|item| item.name == model || item.model == model)
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!("model not configured: {model}"))
                })?;
            let base_url = selected
                .base_url
                .clone()
                .unwrap_or_else(|| "https://api.anthropic.com/v1".to_string());
            let key = selected
                .api_key_env
                .as_deref()
                .and_then(|name| std::env::var(name).ok())
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!(
                        "API key env var is not configured or not set for {model}"
                    ))
                })?;
            let cloned_request = ChatRequest {
                model: model.clone(),
                messages,
                tools,
                stream: false,
                extra_body,
            };
            let payload = build_anthropic_payload(&selected.model, cloned_request);
            let client = reqwest::Client::builder()
                .timeout(Duration::from_secs(config.api_timeout))
                .build()?;
            let response: Value = client
                .post(format!("{}/messages", base_url.trim_end_matches('/')))
                .header("x-api-key", key)
                .header("anthropic-version", "2023-06-01")
                .json(&payload)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            let output_text = extract_anthropic_output_text(&response);
            Ok(ChatResponse {
                output_text,
                raw: response,
                usage: None,
            })
        }
    })
    .await
}

/// Send a request to the model using the appropriate transport
pub async fn send_model_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;

    // Resolve model from provider catalog if available
    let provider = selected.provider.as_deref().unwrap_or("standard");
    let model_id = selected.model.as_str();

    if let Some(provider_model) = resolve_model(provider, model_id) {
        info!(
            "Using provider catalog model: {} (transport: {})",
            provider_model.display_name, provider_model.transport
        );

        match provider_model.transport {
            "nvidia" => send_nvidia_compatible(config, request).await,
            "modelscope" => send_modelscope_compatible(config, request).await,
            "codex" => send_codex_compatible(config, request).await,
            "gemini" => send_gemini_compatible(config, request).await,
            "ollama" => send_ollama_compatible(config, request).await,
            _ => {
                let transport = selected.transport.as_deref().unwrap_or("openai");
                if transport.contains("anthropic") {
                    send_anthropic_compatible(config, request).await
                } else {
                    send_openai_compatible(config, request).await
                }
            }
        }
    } else {
        let transport = selected.transport.as_deref().unwrap_or("openai");
        match transport {
            t if t.contains("anthropic") => send_anthropic_compatible(config, request).await,
            "gemini" | "google" => send_gemini_compatible(config, request).await,
            "ollama" | "local" => send_ollama_compatible(config, request).await,
            "nvidia" => send_nvidia_compatible(config, request).await,
            "modelscope" => send_modelscope_compatible(config, request).await,
            "codex" => send_codex_compatible(config, request).await,
            _ => send_openai_compatible(config, request).await,
        }
    }
}

pub async fn send_model_streaming_compatible<F>(
    config: &Config,
    request: ChatRequest,
    mut on_event: F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;

    let provider = selected.provider.as_deref().unwrap_or("standard");
    let transport = selected.transport.as_deref().unwrap_or("openai");

    // Determine effective transport from catalog or config
    let effective_transport = resolve_model(provider, &selected.model)
        .map(|m| m.transport)
        .unwrap_or(transport);

    on_event(ModelStreamEvent::Start {
        model: selected.model.clone(),
    });

    let result = stream_with_retry(
        config,
        request,
        provider,
        effective_transport,
        &mut on_event,
    )
    .await;

    match result {
        Ok(response) => Ok(response),
        Err(err) if is_recoverable_stream_exception(&err.to_string()) => {
            on_event(ModelStreamEvent::Recovered {
                message: err.to_string(),
            });
            Err(err)
        }
        Err(err) => Err(err),
    }
}

async fn stream_with_retry<F>(
    config: &Config,
    request: ChatRequest,
    provider: &str,
    effective_transport: &str,
    on_event: &mut F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    let max_retries = REQUEST_RETRY_ATTEMPTS;
    let mut last_err = None;
    for attempt in 0..=max_retries {
        match stream_once_compatible(
            config,
            request.clone(),
            provider,
            effective_transport,
            on_event,
        )
        .await
        {
            Ok(response) => return Ok(response),
            Err(err) => {
                if !is_retryable_error(&err) || attempt == max_retries {
                    return Err(err);
                }
                let delay_seconds = RETRY_DELAYS_SECONDS[attempt as usize];
                on_event(ModelStreamEvent::RetryScheduled {
                    message: err.to_string(),
                    attempt: attempt + 1,
                    max_attempts: max_retries,
                    retry_after_seconds: delay_seconds,
                });
                tokio::time::sleep(Duration::from_secs(delay_seconds)).await;
                last_err = Some(err);
            }
        }
    }
    Err(last_err.unwrap_or_else(|| ReverieError::InvalidInput("retry exhausted".to_string())))
}

async fn stream_once_compatible<F>(
    config: &Config,
    request: ChatRequest,
    provider: &str,
    effective_transport: &str,
    on_event: &mut F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    if provider.eq_ignore_ascii_case("nvidia") {
        wait_for_nvidia_rate_limit().await;
        return stream_openai_compatible(config, request, on_event).await;
    }

    match effective_transport {
        t if t.contains("anthropic") || t == "modelscope" => {
            stream_anthropic_compatible(config, request, on_event).await
        }
        "gemini" | "google" => stream_gemini_compatible(config, request, on_event).await,
        "ollama" | "local" => stream_openai_compatible(config, request, on_event).await,
        _ => stream_openai_compatible(config, request, on_event).await,
    }
}

async fn stream_openai_compatible<F>(
    config: &Config,
    request: ChatRequest,
    on_event: &mut F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;
    let base_url = selected
        .base_url
        .clone()
        .unwrap_or_else(|| "https://api.openai.com/v1".to_string());
    let key = api_key_for_model(config, selected)?;
    let mut payload = validate_and_sanitize_payload(json!({
        "model": selected.model,
        "messages": request.messages,
        "tools": request.tools,
        "stream": true
    }))?;
    if let Some(object) = payload.as_object_mut() {
        if object
            .get("tools")
            .and_then(Value::as_array)
            .map(|tools| tools.is_empty())
            .unwrap_or(false)
        {
            object.remove("tools");
        } else {
            object.insert("tool_choice".to_string(), json!("auto"));
        }
        if selected.provider.as_deref() == Some("codex") {
            object.insert(
                "reasoning_effort".to_string(),
                json!(request
                    .extra_body
                    .get("reasoning_effort")
                    .and_then(Value::as_str)
                    .unwrap_or("medium")),
            );
        }
        if let Some(extra) = request.extra_body.as_object() {
            for (key, value) in extra {
                object.insert(key.clone(), value.clone());
            }
        }
    }

    let response = Client::builder()
        .timeout(Duration::from_secs(config.api_timeout))
        .build()?
        .post(format!(
            "{}/chat/completions",
            base_url.trim_end_matches('/')
        ))
        .bearer_auth(key)
        .header("Accept", "text/event-stream")
        .json(&payload)
        .send()
        .await?
        .error_for_status()?;

    parse_openai_sse_response(response, on_event).await
}

async fn stream_anthropic_compatible<F>(
    config: &Config,
    request: ChatRequest,
    on_event: &mut F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;
    let base_url = selected
        .base_url
        .clone()
        .unwrap_or_else(|| "https://api.anthropic.com/v1".to_string());
    let key = api_key_for_model(config, selected)?;
    let mut payload = build_anthropic_payload(&selected.model, request);
    if let Some(object) = payload.as_object_mut() {
        object.insert("stream".to_string(), json!(true));
    }

    let response = Client::builder()
        .timeout(Duration::from_secs(config.api_timeout))
        .build()?
        .post(format!("{}/messages", base_url.trim_end_matches('/')))
        .header("x-api-key", key)
        .header("anthropic-version", "2023-06-01")
        .header("Accept", "text/event-stream")
        .json(&payload)
        .send()
        .await?
        .error_for_status()?;

    parse_anthropic_sse_response(response, on_event).await
}

async fn parse_openai_sse_response<F>(
    response: reqwest::Response,
    on_event: &mut F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    let mut content = String::new();
    let mut finish_reason = None;
    let mut tool_calls: BTreeMap<usize, StreamingToolCall> = BTreeMap::new();
    let mut buffer = String::new();
    let mut stream = response.bytes_stream();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));
        while let Some(index) = buffer.find('\n') {
            let line = buffer[..index].trim_end_matches('\r').to_string();
            buffer = buffer[index + 1..].to_string();
            let Some(data) = line.strip_prefix("data:") else {
                continue;
            };
            let data = data.trim();
            if data.is_empty() {
                continue;
            }
            if data == "[DONE]" {
                on_event(ModelStreamEvent::End {
                    finish_reason: finish_reason.clone(),
                });
                return Ok(stream_response(content, tool_calls, finish_reason));
            }
            let event: Value = serde_json::from_str(data)?;
            let Some(choice) = event
                .get("choices")
                .and_then(Value::as_array)
                .and_then(|choices| choices.first())
            else {
                continue;
            };
            if let Some(reason) = choice.get("finish_reason").and_then(Value::as_str) {
                finish_reason = Some(reason.to_string());
            }
            if let Some(delta) = choice.get("delta") {
                if let Some(piece) = delta.get("content").and_then(Value::as_str) {
                    content.push_str(piece);
                    on_event(ModelStreamEvent::Content {
                        content: piece.to_string(),
                    });
                }
                if let Some(items) = delta.get("tool_calls").and_then(Value::as_array) {
                    for item in items {
                        let index = item.get("index").and_then(Value::as_u64).unwrap_or(0) as usize;
                        let current = tool_calls.entry(index).or_default();
                        if let Some(id) = item.get("id").and_then(Value::as_str) {
                            current.id = Some(id.to_string());
                        }
                        if let Some(name) = item.pointer("/function/name").and_then(Value::as_str) {
                            current.name = Some(name.to_string());
                        }
                        let arguments_delta = item
                            .pointer("/function/arguments")
                            .and_then(Value::as_str)
                            .unwrap_or_default();
                        current.arguments.push_str(arguments_delta);
                        on_event(ModelStreamEvent::ToolCallDelta {
                            index,
                            id: current.id.clone(),
                            name: current.name.clone(),
                            arguments_delta: arguments_delta.to_string(),
                        });
                    }
                }
            }
        }
    }

    if !content.is_empty() || !tool_calls.is_empty() {
        on_event(ModelStreamEvent::Recovered {
            message: "stream ended without a terminal [DONE] event".to_string(),
        });
        return Ok(stream_response(content, tool_calls, finish_reason));
    }
    Err(ReverieError::InvalidInput(
        "stream ended without content".to_string(),
    ))
}

async fn parse_anthropic_sse_response<F>(
    response: reqwest::Response,
    on_event: &mut F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    let mut content = String::new();
    let mut tool_calls: BTreeMap<usize, StreamingToolCall> = BTreeMap::new();
    let mut current_tool_index: Option<usize> = None;
    let mut buffer = String::new();
    let mut stream = response.bytes_stream();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));
        while let Some(index) = buffer.find('\n') {
            let line = buffer[..index].trim_end_matches('\r').to_string();
            buffer = buffer[index + 1..].to_string();
            let Some(data) = line.strip_prefix("data:") else {
                continue;
            };
            let data = data.trim();
            if data.is_empty() || data == "[DONE]" {
                continue;
            }
            let event: Value = serde_json::from_str(data)?;
            match event.get("type").and_then(Value::as_str) {
                Some("content_block_delta") => {
                    if let Some(piece) = event.pointer("/delta/text").and_then(Value::as_str) {
                        content.push_str(piece);
                        on_event(ModelStreamEvent::Content {
                            content: piece.to_string(),
                        });
                    }
                    if let Some(delta) =
                        event.pointer("/delta/partial_json").and_then(Value::as_str)
                    {
                        let index = current_tool_index.unwrap_or(0);
                        let current = tool_calls.entry(index).or_default();
                        current.arguments.push_str(delta);
                        on_event(ModelStreamEvent::ToolCallDelta {
                            index,
                            id: current.id.clone(),
                            name: current.name.clone(),
                            arguments_delta: delta.to_string(),
                        });
                    }
                }
                Some("content_block_start")
                    if event.pointer("/content_block/type").and_then(Value::as_str)
                        == Some("tool_use") =>
                {
                    let index = event.get("index").and_then(Value::as_u64).unwrap_or(0) as usize;
                    current_tool_index = Some(index);
                    let current = tool_calls.entry(index).or_default();
                    current.id = event
                        .pointer("/content_block/id")
                        .and_then(Value::as_str)
                        .map(str::to_string);
                    current.name = event
                        .pointer("/content_block/name")
                        .and_then(Value::as_str)
                        .map(str::to_string);
                }
                Some("message_stop") => {
                    on_event(ModelStreamEvent::End {
                        finish_reason: Some("stop".to_string()),
                    });
                    return Ok(stream_response(
                        content,
                        tool_calls,
                        Some("stop".to_string()),
                    ));
                }
                _ => {}
            }
        }
    }

    if !content.is_empty() || !tool_calls.is_empty() {
        on_event(ModelStreamEvent::Recovered {
            message: "stream ended without message_stop".to_string(),
        });
        return Ok(stream_response(content, tool_calls, None));
    }
    Err(ReverieError::InvalidInput(
        "stream ended without content".to_string(),
    ))
}

async fn stream_gemini_compatible<F>(
    config: &Config,
    request: ChatRequest,
    on_event: &mut F,
) -> ReverieResult<ChatResponse>
where
    F: FnMut(ModelStreamEvent) + Send,
{
    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;
    let api_key = provider_api_key(config, "gemini", "GEMINI_API_KEY")
        .or_else(|_| provider_api_key(config, "google", "GOOGLE_API_KEY"))?;
    let base_url = selected
        .base_url
        .as_deref()
        .unwrap_or("https://generativelanguage.googleapis.com/v1beta");
    let payload = build_gemini_payload(
        &selected.model,
        &request.messages,
        &request.tools,
        &request.extra_body,
    );

    let response = Client::builder()
        .timeout(Duration::from_secs(config.api_timeout))
        .build()?
        .post(format!(
            "{}/models/{}:streamGenerateContent?alt=sse&key={}",
            base_url.trim_end_matches('/'),
            selected.model,
            api_key
        ))
        .header("Content-Type", "application/json")
        .header("Accept", "text/event-stream")
        .json(&payload)
        .send()
        .await?
        .error_for_status()?;

    let mut content = String::new();
    let mut tool_calls: BTreeMap<usize, StreamingToolCall> = BTreeMap::new();
    let mut buffer = String::new();
    let mut stream = response.bytes_stream();
    let mut tool_index = 0usize;

    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;
        buffer.push_str(&String::from_utf8_lossy(&chunk));
        while let Some(index) = buffer.find('\n') {
            let line = buffer[..index].trim_end_matches('\r').to_string();
            buffer = buffer[index + 1..].to_string();
            let Some(data) = line.strip_prefix("data:") else {
                continue;
            };
            let data = data.trim();
            if data.is_empty() || data == "[DONE]" {
                continue;
            }
            let Ok(event) = serde_json::from_str::<Value>(data) else {
                continue;
            };
            if let Some(parts) = event
                .pointer("/candidates/0/content/parts")
                .and_then(Value::as_array)
            {
                for part in parts {
                    if let Some(text) = part.get("text").and_then(Value::as_str) {
                        content.push_str(text);
                        on_event(ModelStreamEvent::Content {
                            content: text.to_string(),
                        });
                    }
                    if let Some(fc) = part.get("functionCall") {
                        let name = fc.get("name").and_then(Value::as_str).unwrap_or_default();
                        let args = serde_json::to_string(&fc.get("args").unwrap_or(&json!({})))
                            .unwrap_or_default();
                        let id = format!("gemini_call_{name}");
                        let current = tool_calls.entry(tool_index).or_default();
                        current.id = Some(id.clone());
                        current.name = Some(name.to_string());
                        current.arguments = args.clone();
                        on_event(ModelStreamEvent::ToolCallDelta {
                            index: tool_index,
                            id: Some(id),
                            name: Some(name.to_string()),
                            arguments_delta: args,
                        });
                        tool_index += 1;
                    }
                }
            }
            if let Some(reason) = event
                .pointer("/candidates/0/finishReason")
                .and_then(Value::as_str)
            {
                if reason == "STOP" || reason == "MAX_TOKENS" {
                    on_event(ModelStreamEvent::End {
                        finish_reason: Some(reason.to_lowercase()),
                    });
                    return Ok(stream_response(
                        content,
                        tool_calls,
                        Some(reason.to_lowercase()),
                    ));
                }
            }
        }
    }

    if !content.is_empty() || !tool_calls.is_empty() {
        on_event(ModelStreamEvent::Recovered {
            message: "Gemini stream ended without finishReason".to_string(),
        });
        return Ok(stream_response(content, tool_calls, None));
    }
    Err(ReverieError::InvalidInput(
        "Gemini stream ended without content".to_string(),
    ))
}

/// Process a sequence of OpenAI-format SSE lines and produce a ChatResponse + events.
/// Used for testing the streaming logic without a real HTTP connection.
#[cfg(test)]
fn process_openai_sse_lines(
    lines: &[&str],
) -> ReverieResult<(ChatResponse, Vec<ModelStreamEvent>)> {
    let mut content = String::new();
    let mut finish_reason = None;
    let mut tool_calls: BTreeMap<usize, StreamingToolCall> = BTreeMap::new();
    let mut events = Vec::new();

    for raw_line in lines {
        let line = raw_line.trim_end_matches('\r');
        let Some(data) = line.strip_prefix("data:") else {
            continue;
        };
        let data = data.trim();
        if data.is_empty() {
            continue;
        }
        if data == "[DONE]" {
            events.push(ModelStreamEvent::End {
                finish_reason: finish_reason.clone(),
            });
            return Ok((stream_response(content, tool_calls, finish_reason), events));
        }
        let event: Value = serde_json::from_str(data)?;
        let Some(choice) = event
            .get("choices")
            .and_then(Value::as_array)
            .and_then(|choices| choices.first())
        else {
            continue;
        };
        if let Some(reason) = choice.get("finish_reason").and_then(Value::as_str) {
            finish_reason = Some(reason.to_string());
        }
        if let Some(delta) = choice.get("delta") {
            if let Some(piece) = delta.get("content").and_then(Value::as_str) {
                content.push_str(piece);
                events.push(ModelStreamEvent::Content {
                    content: piece.to_string(),
                });
            }
            if let Some(items) = delta.get("tool_calls").and_then(Value::as_array) {
                for item in items {
                    let index = item.get("index").and_then(Value::as_u64).unwrap_or(0) as usize;
                    let current = tool_calls.entry(index).or_default();
                    if let Some(id) = item.get("id").and_then(Value::as_str) {
                        current.id = Some(id.to_string());
                    }
                    if let Some(name) = item.pointer("/function/name").and_then(Value::as_str) {
                        current.name = Some(name.to_string());
                    }
                    let arguments_delta = item
                        .pointer("/function/arguments")
                        .and_then(Value::as_str)
                        .unwrap_or_default();
                    current.arguments.push_str(arguments_delta);
                    events.push(ModelStreamEvent::ToolCallDelta {
                        index,
                        id: current.id.clone(),
                        name: current.name.clone(),
                        arguments_delta: arguments_delta.to_string(),
                    });
                }
            }
        }
    }
    Ok((stream_response(content, tool_calls, finish_reason), events))
}

/// Process a sequence of Anthropic-format SSE lines and produce a ChatResponse + events.
#[cfg(test)]
fn process_anthropic_sse_lines(
    lines: &[&str],
) -> ReverieResult<(ChatResponse, Vec<ModelStreamEvent>)> {
    let mut content = String::new();
    let mut tool_calls: BTreeMap<usize, StreamingToolCall> = BTreeMap::new();
    let mut current_tool_index: Option<usize> = None;
    let mut events = Vec::new();

    for raw_line in lines {
        let line = raw_line.trim_end_matches('\r');
        let Some(data) = line.strip_prefix("data:") else {
            continue;
        };
        let data = data.trim();
        if data.is_empty() || data == "[DONE]" {
            continue;
        }
        let event: Value = serde_json::from_str(data)?;
        match event.get("type").and_then(Value::as_str) {
            Some("content_block_delta") => {
                if let Some(piece) = event.pointer("/delta/text").and_then(Value::as_str) {
                    content.push_str(piece);
                    events.push(ModelStreamEvent::Content {
                        content: piece.to_string(),
                    });
                }
                if let Some(delta) = event.pointer("/delta/partial_json").and_then(Value::as_str) {
                    let index = current_tool_index.unwrap_or(0);
                    let current = tool_calls.entry(index).or_default();
                    current.arguments.push_str(delta);
                    events.push(ModelStreamEvent::ToolCallDelta {
                        index,
                        id: current.id.clone(),
                        name: current.name.clone(),
                        arguments_delta: delta.to_string(),
                    });
                }
            }
            Some("content_block_start")
                if event.pointer("/content_block/type").and_then(Value::as_str)
                    == Some("tool_use") =>
            {
                let index = event.get("index").and_then(Value::as_u64).unwrap_or(0) as usize;
                current_tool_index = Some(index);
                let current = tool_calls.entry(index).or_default();
                current.id = event
                    .pointer("/content_block/id")
                    .and_then(Value::as_str)
                    .map(str::to_string);
                current.name = event
                    .pointer("/content_block/name")
                    .and_then(Value::as_str)
                    .map(str::to_string);
            }
            Some("message_stop") => {
                events.push(ModelStreamEvent::End {
                    finish_reason: Some("stop".to_string()),
                });
                return Ok((
                    stream_response(content, tool_calls, Some("stop".to_string())),
                    events,
                ));
            }
            _ => {}
        }
    }
    Ok((stream_response(content, tool_calls, None), events))
}

/// Process a sequence of Gemini-format SSE lines and produce a ChatResponse + events.
#[cfg(test)]
fn process_gemini_sse_lines(
    lines: &[&str],
) -> ReverieResult<(ChatResponse, Vec<ModelStreamEvent>)> {
    let mut content = String::new();
    let mut tool_calls: BTreeMap<usize, StreamingToolCall> = BTreeMap::new();
    let mut tool_index = 0usize;
    let mut events = Vec::new();

    for raw_line in lines {
        let line = raw_line.trim_end_matches('\r');
        let Some(data) = line.strip_prefix("data:") else {
            continue;
        };
        let data = data.trim();
        if data.is_empty() || data == "[DONE]" {
            continue;
        }
        let Ok(event) = serde_json::from_str::<Value>(data) else {
            continue;
        };
        if let Some(parts) = event
            .pointer("/candidates/0/content/parts")
            .and_then(Value::as_array)
        {
            for part in parts {
                if let Some(text) = part.get("text").and_then(Value::as_str) {
                    content.push_str(text);
                    events.push(ModelStreamEvent::Content {
                        content: text.to_string(),
                    });
                }
                if let Some(fc) = part.get("functionCall") {
                    let name = fc.get("name").and_then(Value::as_str).unwrap_or_default();
                    let args = serde_json::to_string(&fc.get("args").unwrap_or(&json!({})))
                        .unwrap_or_default();
                    let id = format!("gemini_call_{name}");
                    let current = tool_calls.entry(tool_index).or_default();
                    current.id = Some(id.clone());
                    current.name = Some(name.to_string());
                    current.arguments = args.clone();
                    events.push(ModelStreamEvent::ToolCallDelta {
                        index: tool_index,
                        id: Some(id),
                        name: Some(name.to_string()),
                        arguments_delta: args,
                    });
                    tool_index += 1;
                }
            }
        }
        if let Some(reason) = event
            .pointer("/candidates/0/finishReason")
            .and_then(Value::as_str)
        {
            if reason == "STOP" || reason == "MAX_TOKENS" {
                events.push(ModelStreamEvent::End {
                    finish_reason: Some(reason.to_lowercase()),
                });
                return Ok((
                    stream_response(content, tool_calls, Some(reason.to_lowercase())),
                    events,
                ));
            }
        }
    }
    Ok((stream_response(content, tool_calls, None), events))
}

#[derive(Debug, Clone, Default)]
struct StreamingToolCall {
    id: Option<String>,
    name: Option<String>,
    arguments: String,
}

fn stream_response(
    content: String,
    tool_calls: BTreeMap<usize, StreamingToolCall>,
    finish_reason: Option<String>,
) -> ChatResponse {
    let tool_calls = tool_calls
        .into_values()
        .filter_map(|call| {
            let name = call.name?;
            Some(json!({
                "id": call.id.unwrap_or_else(|| format!("call_{name}")),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": call.arguments
                }
            }))
        })
        .collect::<Vec<_>>();
    ChatResponse {
        output_text: content.clone(),
        raw: json!({
            "choices": [{
                "message": {
                    "content": content,
                    "tool_calls": tool_calls
                },
                "finish_reason": finish_reason
            }]
        }),
        usage: None,
    }
}

/// Send request to NVIDIA API
pub async fn send_nvidia_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to NVIDIA API");
    let config = config.clone();
    let request_model = request.model.clone();
    let request_messages = request.messages.clone();
    let request_tools = request.tools.clone();
    let request_extra = request.extra_body.clone();

    with_retry(REQUEST_RETRY_ATTEMPTS, || {
        let config = config.clone();
        let model = request_model.clone();
        let messages = request_messages.clone();
        let tools = request_tools.clone();
        let extra_body = request_extra.clone();
        async move {
            wait_for_nvidia_rate_limit().await;
            let selected = config
                .models
                .iter()
                .find(|item| item.name == model || item.model == model)
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!("model not configured: {model}"))
                })?;
            let api_key = provider_api_key(&config, "nvidia", "NVIDIA_API_KEY")?;
            let base_url = selected
                .base_url
                .as_deref()
                .unwrap_or("https://integrate.api.nvidia.com/v1");
            let mut payload = validate_and_sanitize_payload(json!({
                "model": selected.model,
                "messages": messages,
                "tools": tools,
                "stream": false
            }))?;
            if let Some(object) = payload.as_object_mut() {
                object.entry("temperature").or_insert(json!(0.7));
                if let Some(extra) = extra_body.as_object() {
                    for (key, value) in extra {
                        object.insert(key.clone(), value.clone());
                    }
                }
            }
            let client = Client::builder()
                .timeout(Duration::from_secs(config.api_timeout))
                .build()?;
            let response: Value = client
                .post(format!(
                    "{}/chat/completions",
                    base_url.trim_end_matches('/')
                ))
                .bearer_auth(api_key)
                .json(&payload)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            let output_text = extract_openai_output_text(&response);
            Ok(ChatResponse {
                output_text,
                raw: response,
                usage: None,
            })
        }
    })
    .await
}

/// Send request to ModelScope API
pub async fn send_modelscope_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to ModelScope API");
    let config = config.clone();
    let request_model = request.model.clone();
    let request_messages = request.messages.clone();
    let request_tools = request.tools.clone();
    let request_extra = request.extra_body.clone();

    with_retry(REQUEST_RETRY_ATTEMPTS, || {
        let config = config.clone();
        let model = request_model.clone();
        let messages = request_messages.clone();
        let tools = request_tools.clone();
        let extra_body = request_extra.clone();
        async move {
            let selected = config
                .models
                .iter()
                .find(|item| item.name == model || item.model == model)
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!("model not configured: {model}"))
                })?;
            let api_key = provider_api_key(&config, "modelscope", "MODELSCOPE_API_KEY")?;
            let base_url = selected
                .base_url
                .as_deref()
                .unwrap_or("https://api-inference.modelscope.cn/v1");
            let cloned_request = ChatRequest {
                model: model.clone(),
                messages,
                tools,
                stream: false,
                extra_body,
            };
            let payload = build_anthropic_payload(&selected.model, cloned_request);
            let client = Client::builder()
                .timeout(Duration::from_secs(config.api_timeout))
                .build()?;
            let response: Value = client
                .post(format!("{}/messages", base_url.trim_end_matches('/')))
                .header("x-api-key", api_key)
                .header("anthropic-version", "2023-06-01")
                .json(&payload)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            let output_text = extract_anthropic_output_text(&response);
            Ok(ChatResponse {
                output_text,
                raw: response,
                usage: None,
            })
        }
    })
    .await
}

/// Send request to Codex API
pub async fn send_codex_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to Codex API");
    let config = config.clone();
    let request_model = request.model.clone();
    let request_messages = request.messages.clone();
    let request_tools = request.tools.clone();
    let request_extra = request.extra_body.clone();

    with_retry(REQUEST_RETRY_ATTEMPTS, || {
        let config = config.clone();
        let model = request_model.clone();
        let messages = request_messages.clone();
        let tools = request_tools.clone();
        let extra_body = request_extra.clone();
        async move {
            let selected = config
                .models
                .iter()
                .find(|item| item.name == model || item.model == model)
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!("model not configured: {model}"))
                })?;
            let api_key = provider_api_key(&config, "codex", "OPENAI_API_KEY")?;
            let base_url = selected
                .base_url
                .as_deref()
                .unwrap_or("https://api.openai.com/v1");
            let payload = validate_and_sanitize_payload(json!({
                "model": selected.model,
                "messages": messages,
                "tools": tools,
                "stream": false,
                "reasoning_effort": extra_body.get("reasoning_effort")
                    .and_then(|v| v.as_str())
                    .unwrap_or("medium")
            }))?;
            let client = Client::builder()
                .timeout(Duration::from_secs(config.api_timeout))
                .build()?;
            let response: Value = client
                .post(format!(
                    "{}/chat/completions",
                    base_url.trim_end_matches('/')
                ))
                .bearer_auth(api_key)
                .json(&payload)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            let output_text = extract_openai_output_text(&response);
            Ok(ChatResponse {
                output_text,
                raw: response,
                usage: None,
            })
        }
    })
    .await
}

/// Send request to Google Gemini API
pub async fn send_gemini_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to Google Gemini API");
    let config = config.clone();
    let request_model = request.model.clone();
    let request_messages = request.messages.clone();
    let request_tools = request.tools.clone();
    let request_extra = request.extra_body.clone();

    with_retry(REQUEST_RETRY_ATTEMPTS, || {
        let config = config.clone();
        let model = request_model.clone();
        let messages = request_messages.clone();
        let tools = request_tools.clone();
        let extra_body = request_extra.clone();
        async move {
            let selected = config
                .models
                .iter()
                .find(|item| item.name == model || item.model == model)
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!("model not configured: {model}"))
                })?;
            let api_key = provider_api_key(&config, "gemini", "GEMINI_API_KEY")
                .or_else(|_| provider_api_key(&config, "google", "GOOGLE_API_KEY"))?;
            let base_url = selected
                .base_url
                .as_deref()
                .unwrap_or("https://generativelanguage.googleapis.com/v1beta");
            let payload = build_gemini_payload(&selected.model, &messages, &tools, &extra_body);
            let client = Client::builder()
                .timeout(Duration::from_secs(config.api_timeout))
                .build()?;
            let response: Value = client
                .post(format!(
                    "{}/models/{}:generateContent?key={}",
                    base_url.trim_end_matches('/'),
                    selected.model,
                    api_key
                ))
                .header("Content-Type", "application/json")
                .json(&payload)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            let output_text = extract_gemini_output_text(&response);
            Ok(ChatResponse {
                output_text,
                raw: response,
                usage: None,
            })
        }
    })
    .await
}

/// Send request to Ollama local API
pub async fn send_ollama_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to Ollama API");
    let config = config.clone();
    let request_model = request.model.clone();
    let request_messages = request.messages.clone();
    let request_tools = request.tools.clone();
    let request_extra = request.extra_body.clone();

    with_retry(REQUEST_RETRY_ATTEMPTS, || {
        let config = config.clone();
        let model = request_model.clone();
        let messages = request_messages.clone();
        let tools = request_tools.clone();
        let extra_body = request_extra.clone();
        async move {
            let selected = config
                .models
                .iter()
                .find(|item| item.name == model || item.model == model)
                .ok_or_else(|| {
                    ReverieError::InvalidInput(format!("model not configured: {model}"))
                })?;
            let base_url = selected
                .base_url
                .as_deref()
                .unwrap_or("http://localhost:11434/v1");
            let mut payload = validate_and_sanitize_payload(json!({
                "model": selected.model,
                "messages": messages,
                "tools": tools,
                "stream": false
            }))?;
            if let Some(object) = payload.as_object_mut() {
                if object
                    .get("tools")
                    .and_then(Value::as_array)
                    .map(|t| t.is_empty())
                    .unwrap_or(false)
                {
                    object.remove("tools");
                }
                if let Some(extra) = extra_body.as_object() {
                    for (key, value) in extra {
                        object.insert(key.clone(), value.clone());
                    }
                }
            }
            let client = Client::builder()
                .timeout(Duration::from_secs(config.api_timeout))
                .build()?;
            let response: Value = client
                .post(format!(
                    "{}/chat/completions",
                    base_url.trim_end_matches('/')
                ))
                .json(&payload)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            let output_text = extract_openai_output_text(&response);
            Ok(ChatResponse {
                output_text,
                raw: response,
                usage: None,
            })
        }
    })
    .await
}

/// Build a Gemini API request payload from messages and tools.
fn build_gemini_payload(
    _model: &str,
    messages: &[ChatMessage],
    tools: &[Value],
    extra_body: &Value,
) -> Value {
    let contents: Vec<Value> = messages
        .iter()
        .filter(|m| m.role != "system")
        .map(|m| {
            let role = match m.role.as_str() {
                "assistant" => "model",
                "tool" => "function",
                _ => "user",
            };
            if m.role == "tool" {
                let fn_name = m.tool_call_id.as_deref().unwrap_or("unknown");
                json!({
                    "role": role,
                    "parts": [{
                        "functionResponse": {
                            "name": fn_name,
                            "response": {"result": content_to_text(&m.content)}
                        }
                    }]
                })
            } else if m.role == "assistant" && !m.tool_calls.is_empty() {
                let parts: Vec<Value> = m
                    .tool_calls
                    .iter()
                    .filter_map(|tc| {
                        let name = tc.pointer("/function/name").and_then(Value::as_str)?;
                        let args_str = tc
                            .pointer("/function/arguments")
                            .and_then(Value::as_str)
                            .unwrap_or("{}");
                        let args = serde_json::from_str::<Value>(args_str).unwrap_or(json!({}));
                        Some(json!({"functionCall": {"name": name, "args": args}}))
                    })
                    .collect();
                json!({"role": "model", "parts": parts})
            } else {
                json!({
                    "role": role,
                    "parts": [{"text": content_to_text(&m.content)}]
                })
            }
        })
        .collect();

    let system_instruction = messages
        .iter()
        .find(|m| m.role == "system")
        .map(|m| json!({"parts": [{"text": content_to_text(&m.content)}]}));

    let gemini_tools: Vec<Value> = if tools.is_empty() {
        Vec::new()
    } else {
        let declarations: Vec<Value> = tools
            .iter()
            .filter_map(|t| {
                let func = t.get("function")?;
                Some(json!({
                    "name": func.get("name")?,
                    "description": func.get("description").cloned().unwrap_or(json!("")),
                    "parameters": func.get("parameters").cloned().unwrap_or(json!({"type":"object","properties":{}}))
                }))
            })
            .collect();
        vec![json!({"functionDeclarations": declarations})]
    };

    let mut payload = json!({"contents": contents});
    if let Some(si) = system_instruction {
        payload["systemInstruction"] = si;
    }
    if !gemini_tools.is_empty() {
        payload["tools"] = Value::Array(gemini_tools);
    }
    let max_tokens = extra_body
        .get("max_tokens")
        .and_then(Value::as_u64)
        .unwrap_or(8192);
    payload["generationConfig"] = json!({
        "maxOutputTokens": max_tokens,
        "temperature": extra_body.get("temperature").and_then(Value::as_f64).unwrap_or(0.7)
    });
    if let Some(thinking) = extra_body.get("thinking") {
        payload["generationConfig"]["thinkingConfig"] = json!({"thinkingBudget": thinking});
    }
    payload
}

/// Extract output text from a Gemini API response.
pub fn extract_gemini_output_text(response: &Value) -> String {
    response
        .pointer("/candidates/0/content/parts")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|part| part.get("text").and_then(Value::as_str))
        .collect::<Vec<_>>()
        .join("")
}

/// Extract tool calls from a Gemini API response.
pub fn extract_gemini_tool_calls(response: &Value) -> Vec<ToolCallRequest> {
    response
        .pointer("/candidates/0/content/parts")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|part| {
            let fc = part.get("functionCall")?;
            let name = fc.get("name").and_then(Value::as_str)?;
            Some(ToolCallRequest {
                id: format!("gemini_call_{name}"),
                name: name.to_string(),
                arguments: fc.get("args").cloned().unwrap_or(json!({})),
                raw: json!({
                    "id": format!("gemini_call_{name}"),
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": serde_json::to_string(&fc.get("args").unwrap_or(&json!({}))).unwrap_or_default()
                    }
                }),
            })
        })
        .collect()
}

/// Extract token usage from a provider's raw JSON response.
/// Handles OpenAI (`usage.prompt_tokens`), Anthropic (`usage.input_tokens`),
/// and Gemini (`usageMetadata.promptTokenCount`) formats.
pub fn extract_token_usage(raw: &Value) -> Option<TokenUsage> {
    // OpenAI / Codex / NVIDIA / Ollama format
    if let Some(u) = raw.get("usage") {
        let prompt = u.get("prompt_tokens").and_then(Value::as_u64).unwrap_or(0) as u32;
        let completion = u
            .get("completion_tokens")
            .and_then(Value::as_u64)
            .unwrap_or(0) as u32;
        let total = u
            .get("total_tokens")
            .and_then(Value::as_u64)
            .unwrap_or((prompt + completion) as u64) as u32;
        if prompt > 0 || completion > 0 {
            return Some(TokenUsage {
                prompt_tokens: prompt,
                completion_tokens: completion,
                total_tokens: total,
            });
        }
    }
    // Anthropic format
    if let Some(u) = raw.get("usage") {
        let input = u.get("input_tokens").and_then(Value::as_u64).unwrap_or(0) as u32;
        let output = u.get("output_tokens").and_then(Value::as_u64).unwrap_or(0) as u32;
        if input > 0 || output > 0 {
            return Some(TokenUsage {
                prompt_tokens: input,
                completion_tokens: output,
                total_tokens: input + output,
            });
        }
    }
    // Gemini format
    if let Some(u) = raw.get("usageMetadata") {
        let prompt = u
            .get("promptTokenCount")
            .and_then(Value::as_u64)
            .unwrap_or(0) as u32;
        let completion = u
            .get("candidatesTokenCount")
            .and_then(Value::as_u64)
            .unwrap_or(0) as u32;
        let total = u
            .get("totalTokenCount")
            .and_then(Value::as_u64)
            .unwrap_or((prompt + completion) as u64) as u32;
        if prompt > 0 || completion > 0 {
            return Some(TokenUsage {
                prompt_tokens: prompt,
                completion_tokens: completion,
                total_tokens: total,
            });
        }
    }
    None
}

fn provider_api_key(config: &Config, provider: &str, env_name: &str) -> ReverieResult<String> {
    if let Ok(value) = std::env::var(env_name) {
        if !value.trim().is_empty() {
            return Ok(value);
        }
    }
    if let Some(value) = config
        .extra
        .get(provider)
        .and_then(|value| value.get("api_key"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return Ok(value.to_string());
    }
    Err(ReverieError::InvalidInput(format!(
        "{env_name} environment variable is not set and {provider}.api_key is not configured"
    )))
}

fn api_key_for_model(config: &Config, selected: &ModelConfig) -> ReverieResult<String> {
    if let Some(env_name) = selected.api_key_env.as_deref() {
        if let Ok(value) = std::env::var(env_name) {
            if !value.trim().is_empty() {
                return Ok(value);
            }
        }
    }
    match selected.provider.as_deref() {
        Some("nvidia") => provider_api_key(config, "nvidia", "NVIDIA_API_KEY"),
        Some("modelscope") => provider_api_key(config, "modelscope", "MODELSCOPE_API_KEY"),
        Some("codex") | Some("openai") => provider_api_key(config, "codex", "OPENAI_API_KEY"),
        Some("gemini") | Some("google") => provider_api_key(config, "gemini", "GEMINI_API_KEY")
            .or_else(|_| provider_api_key(config, "google", "GOOGLE_API_KEY")),
        Some("anthropic") => provider_api_key(config, "anthropic", "ANTHROPIC_API_KEY"),
        Some("ollama") | Some("local") => Ok(String::new()), // Ollama doesn't require auth
        _ => Err(ReverieError::InvalidInput(format!(
            "API key env var is not configured or not set for {}",
            selected.name
        ))),
    }
}

/// Build `extra_body` for a `ChatRequest` by merging provider catalog
/// defaults, user config preferences, and per-model overrides.
///
/// The resulting value is consumed by each provider's payload builder
/// (OpenAI, Anthropic, Gemini, etc.) to inject the correct API-specific
/// fields such as `max_tokens`, `temperature`, `tool_choice`, and
/// provider-specific thinking/reasoning parameters.
pub fn build_request_extra_body(config: &Config, model_name: &str) -> Value {
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model_name || item.model == model_name);

    let provider = selected
        .and_then(|m| m.provider.as_deref())
        .unwrap_or("standard");
    let model_id = selected.map(|m| m.model.as_str()).unwrap_or(model_name);
    let catalog_model = resolve_model(provider, model_id);

    let mut extra = serde_json::Map::new();

    // --- max_tokens / max_output_tokens ---
    // Priority: config.extra["max_tokens"] > catalog output_limit > default 4096
    let max_tokens = config
        .extra
        .get("max_tokens")
        .and_then(Value::as_u64)
        .or_else(|| {
            config
                .extra
                .get("max_output_tokens")
                .and_then(Value::as_u64)
        })
        .or_else(|| catalog_model.as_ref().map(|m| m.output_limit as u64))
        .unwrap_or(4096);
    extra.insert("max_tokens".to_string(), json!(max_tokens));

    // --- temperature ---
    if let Some(temp) = config.extra.get("temperature").and_then(Value::as_f64) {
        extra.insert("temperature".to_string(), json!(temp));
    }

    // --- top_p ---
    if let Some(top_p) = config.extra.get("top_p").and_then(Value::as_f64) {
        extra.insert("top_p".to_string(), json!(top_p));
    }

    // --- tool_choice ---
    if let Some(tool_choice) = config.extra.get("tool_choice") {
        extra.insert("tool_choice".to_string(), tool_choice.clone());
    }

    // --- reasoning_effort (OpenAI/Codex) ---
    if let Some(effort) = config.extra.get("reasoning_effort").and_then(Value::as_str) {
        extra.insert(
            "reasoning_effort".to_string(),
            json!(crate::providers::normalize_reasoning_effort(effort)),
        );
    }

    // --- thinking / thinking_budget (Gemini) ---
    let supports_thinking = catalog_model
        .as_ref()
        .map(|m| m.supports_thinking)
        .unwrap_or(false);
    if supports_thinking {
        if let Some(budget) = config
            .extra
            .get("thinking_budget")
            .or_else(|| config.extra.get("thinking"))
        {
            extra.insert("thinking".to_string(), budget.clone());
        }
    }

    Value::Object(extra)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compacts_tool_payload() {
        let payload =
            json!({"model":"x","messages":[{"role":"tool","tool_calls":[{}]}],"tools":[]});
        let compact = compact_payload_for_plain_chat(&payload);
        assert!(compact.get("tools").is_none());
        assert_eq!(compact["messages"][0]["role"], "user");
    }

    #[test]
    fn stream_event_accepts_sse_data() {
        let event = decode_stream_event("data: {\"type\":\"x\"}").unwrap();
        assert_eq!(event["type"], "x");
    }

    #[test]
    fn tool_argument_salvage_keeps_object() {
        let value = parse_tool_arguments("{\"path\":\"a\"} trailing");
        assert_eq!(value["path"], "a");
    }

    #[test]
    fn extracts_anthropic_text_blocks() {
        let value = json!({"content":[{"type":"text","text":"hello"},{"type":"tool_use"}]});
        assert_eq!(extract_anthropic_output_text(&value), "hello");
    }

    #[test]
    fn extracts_anthropic_tool_calls() {
        let value = json!({
            "content": [{
                "type": "tool_use",
                "id": "toolu_1",
                "name": "count_tokens",
                "input": {"text": "abcd"}
            }]
        });
        let calls = extract_anthropic_tool_calls(&value);
        assert_eq!(calls[0].id, "toolu_1");
        assert_eq!(calls[0].name, "count_tokens");
        assert_eq!(calls[0].arguments["text"], "abcd");
    }

    #[test]
    fn extracts_openai_tool_calls() {
        let value = json!({
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "count_tokens",
                            "arguments": "{\"text\":\"abcd\"}"
                        }
                    }]
                }
            }]
        });
        let calls = extract_openai_tool_calls(&value);
        assert_eq!(calls[0].id, "call_1");
        assert_eq!(calls[0].name, "count_tokens");
        assert_eq!(calls[0].arguments["text"], "abcd");
    }

    #[test]
    fn openai_tool_definitions_include_parameters() {
        let definitions = build_openai_tool_definitions(&[reverie_tools::ToolSpec {
            name: "str_replace_editor".to_string(),
            description: "edit".to_string(),
            category: "editing".to_string(),
            modes: vec!["reverie".to_string()],
        }]);
        assert_eq!(
            definitions[0]["function"]["parameters"]["required"][0],
            "command"
        );
        assert!(definitions[0]["function"]["parameters"]["properties"]
            .get("new_str")
            .is_some());
    }

    #[test]
    fn anthropic_payload_converts_openai_tool_schema() {
        let tools = build_openai_tool_definitions(&[reverie_tools::ToolSpec {
            name: "count_tokens".to_string(),
            description: "count".to_string(),
            category: "context".to_string(),
            modes: vec!["reverie".to_string()],
        }]);
        let payload = build_anthropic_payload(
            "claude-compatible",
            ChatRequest {
                model: "claude-compatible".to_string(),
                messages: vec![ChatMessage::new("user", json!("hello"))],
                tools,
                stream: false,
                extra_body: json!({"max_tokens": 1024}),
            },
        );
        assert_eq!(payload["max_tokens"], 1024);
        assert_eq!(payload["tools"][0]["name"], "count_tokens");
        assert_eq!(payload["tools"][0]["input_schema"]["required"][0], "text");
    }

    #[test]
    fn anthropic_payload_preserves_tool_result_blocks() {
        let payload = build_anthropic_payload(
            "claude-compatible",
            ChatRequest {
                model: "claude-compatible".to_string(),
                messages: vec![
                    ChatMessage::assistant_with_tool_calls(vec![json!({
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "count_tokens",
                        "input": {"text": "abcd"}
                    })]),
                    ChatMessage::tool_result("toolu_1", json!("{\"success\":true}")),
                ],
                tools: Vec::new(),
                stream: false,
                extra_body: json!({}),
            },
        );
        assert_eq!(payload["messages"][0]["content"][0]["type"], "tool_use");
        assert_eq!(payload["messages"][1]["content"][0]["type"], "tool_result");
    }

    #[test]
    fn inline_images_become_multimodal_content_blocks() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("shot.png"), [137, 80, 78, 71]).unwrap();
        let content =
            user_content_with_inline_images(temp.path(), "inspect ![](shot.png)").unwrap();
        assert_eq!(content[0]["type"], "text");
        assert_eq!(content[1]["type"], "image_url");
        assert!(content[1]["image_url"]["url"]
            .as_str()
            .unwrap()
            .starts_with("data:image/png;base64,"));
    }

    #[test]
    fn anthropic_payload_converts_inline_image_blocks() {
        let content = json!([
            {"type": "text", "text": "inspect"},
            {
                "type": "image_url",
                "source": {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}
            }
        ]);
        let payload = build_anthropic_payload(
            "claude-compatible",
            ChatRequest {
                model: "claude-compatible".to_string(),
                messages: vec![ChatMessage::new("user", content)],
                tools: Vec::new(),
                stream: false,
                extra_body: json!({}),
            },
        );
        assert_eq!(payload["messages"][0]["content"][1]["type"], "image");
        assert_eq!(
            payload["messages"][0]["content"][1]["source"]["media_type"],
            "image/png"
        );
    }

    #[test]
    fn gemini_payload_builds_contents_and_system_instruction() {
        let messages = vec![
            ChatMessage::new("system", json!("You are a helpful assistant.")),
            ChatMessage::new("user", json!("Hello")),
        ];
        let tools = build_openai_tool_definitions(&[reverie_tools::ToolSpec {
            name: "count_tokens".to_string(),
            description: "count".to_string(),
            category: "context".to_string(),
            modes: vec!["reverie".to_string()],
        }]);
        let payload = build_gemini_payload("gemini-2.5-pro", &messages, &tools, &json!({}));
        // System message should become systemInstruction, not a content entry
        assert_eq!(payload["contents"].as_array().unwrap().len(), 1);
        assert_eq!(payload["contents"][0]["role"], "user");
        assert_eq!(
            payload["systemInstruction"]["parts"][0]["text"],
            "You are a helpful assistant."
        );
        // Tools should be converted to functionDeclarations
        assert!(!payload["tools"][0]["functionDeclarations"]
            .as_array()
            .unwrap()
            .is_empty());
    }

    #[test]
    fn gemini_extracts_text_from_candidates() {
        let response = json!({
            "candidates": [{
                "content": {
                    "parts": [
                        {"text": "Hello "},
                        {"text": "world"}
                    ]
                }
            }]
        });
        assert_eq!(extract_gemini_output_text(&response), "Hello world");
    }

    #[test]
    fn gemini_extracts_function_calls() {
        let response = json!({
            "candidates": [{
                "content": {
                    "parts": [{
                        "functionCall": {
                            "name": "count_tokens",
                            "args": {"text": "abcd"}
                        }
                    }]
                }
            }]
        });
        let calls = extract_gemini_tool_calls(&response);
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].name, "count_tokens");
        assert_eq!(calls[0].arguments["text"], "abcd");
        assert!(calls[0].id.starts_with("gemini_call_"));
    }

    #[test]
    fn gemini_payload_converts_tool_results() {
        let messages = vec![
            ChatMessage::new("user", json!("Count this")),
            ChatMessage::assistant_with_tool_calls(vec![json!({
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "count_tokens",
                    "arguments": "{\"text\":\"hello\"}"
                }
            })]),
            ChatMessage::tool_result("count_tokens", json!("5 tokens")),
        ];
        let payload = build_gemini_payload("gemini-2.5-pro", &messages, &[], &json!({}));
        let contents = payload["contents"].as_array().unwrap();
        assert_eq!(contents.len(), 3);
        // Tool result should become functionResponse
        assert_eq!(contents[2]["role"], "function");
        assert!(contents[2]["parts"][0]["functionResponse"].is_object());
    }

    #[test]
    fn build_extra_body_uses_catalog_output_limit() {
        let config = Config {
            models: vec![ModelConfig {
                name: "test".to_string(),
                model: "gemini-2.5-pro".to_string(),
                provider: Some("gemini".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        let extra = build_request_extra_body(&config, "test");
        // gemini-2.5-pro catalog output_limit = 65536
        assert_eq!(extra["max_tokens"], json!(65536));
    }

    #[test]
    fn build_extra_body_config_overrides_catalog() {
        let mut config = Config {
            models: vec![ModelConfig {
                name: "test".to_string(),
                model: "gemini-2.5-pro".to_string(),
                provider: Some("gemini".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        config.extra.insert("max_tokens".to_string(), json!(1024));
        config.extra.insert("temperature".to_string(), json!(0.3));
        config.extra.insert("top_p".to_string(), json!(0.9));
        config
            .extra
            .insert("reasoning_effort".to_string(), json!("high"));
        let extra = build_request_extra_body(&config, "test");
        assert_eq!(extra["max_tokens"], json!(1024));
        assert_eq!(extra["temperature"], json!(0.3));
        assert_eq!(extra["top_p"], json!(0.9));
        assert_eq!(extra["reasoning_effort"], json!("high"));
    }

    #[test]
    fn build_extra_body_defaults_when_no_catalog() {
        let config = Config {
            models: vec![ModelConfig {
                name: "custom".to_string(),
                model: "custom-model".to_string(),
                ..Default::default()
            }],
            ..Default::default()
        };
        let extra = build_request_extra_body(&config, "custom");
        assert_eq!(extra["max_tokens"], json!(4096));
        // no temperature key unless explicitly set
        assert!(extra.get("temperature").is_none());
    }

    #[test]
    fn build_extra_body_thinking_budget_for_gemini() {
        let mut config = Config {
            models: vec![ModelConfig {
                name: "test".to_string(),
                model: "gemini-2.5-pro".to_string(),
                provider: Some("gemini".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        config
            .extra
            .insert("thinking_budget".to_string(), json!(32768));
        let extra = build_request_extra_body(&config, "test");
        assert_eq!(extra["thinking"], json!(32768));
    }

    #[test]
    fn build_extra_body_tool_choice_passthrough() {
        let mut config = Config {
            models: vec![ModelConfig {
                name: "test".to_string(),
                model: "gpt-5.5".to_string(),
                provider: Some("codex".to_string()),
                ..Default::default()
            }],
            ..Default::default()
        };
        config
            .extra
            .insert("tool_choice".to_string(), json!("required"));
        let extra = build_request_extra_body(&config, "test");
        assert_eq!(extra["tool_choice"], json!("required"));
    }

    #[test]
    fn anthropic_payload_uses_extra_max_tokens() {
        let request = ChatRequest {
            model: "claude-3-5-sonnet".to_string(),
            messages: vec![ChatMessage::new("user", json!("Hello"))],
            tools: Vec::new(),
            stream: false,
            extra_body: json!({"max_tokens": 8192, "temperature": 0.5}),
        };
        let payload = build_anthropic_payload("claude-3-5-sonnet", request);
        assert_eq!(payload["max_tokens"], json!(8192));
        assert_eq!(payload["temperature"], json!(0.5));
    }

    #[test]
    fn gemini_payload_uses_extra_body_values() {
        let messages = vec![ChatMessage::new("user", json!("Hello"))];
        let extra = json!({"max_tokens": 16384, "temperature": 0.2, "thinking": 8192});
        let payload = build_gemini_payload("gemini-2.5-pro", &messages, &[], &extra);
        assert_eq!(payload["generationConfig"]["maxOutputTokens"], json!(16384));
        assert_eq!(payload["generationConfig"]["temperature"], json!(0.2));
        assert_eq!(
            payload["generationConfig"]["thinkingConfig"]["thinkingBudget"],
            json!(8192)
        );
    }

    // ===== Mock SSE streaming tests =====

    #[test]
    fn openai_sse_text_only_stream() {
        let lines = vec![
            r#"data: {"choices":[{"delta":{"content":"Hello"},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{"content":" world"},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}"#,
            "data: [DONE]",
        ];
        let (response, events) = process_openai_sse_lines(&lines).unwrap();
        assert_eq!(response.output_text, "Hello world");
        assert!(
            matches!(events[0], ModelStreamEvent::Content { ref content } if content == "Hello")
        );
        assert!(
            matches!(events[1], ModelStreamEvent::Content { ref content } if content == " world")
        );
        assert!(matches!(
            events.last().unwrap(),
            ModelStreamEvent::End { .. }
        ));
    }

    #[test]
    fn openai_sse_tool_call_delta_accumulation() {
        let lines = vec![
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc","function":{"name":"web_fetch","arguments":""}}]},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"ur"}}]},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"l\":\"https://example.com\"}"}}]},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{},"index":0,"finish_reason":"tool_calls"}]}"#,
            "data: [DONE]",
        ];
        let (response, events) = process_openai_sse_lines(&lines).unwrap();
        // Should have accumulated the tool call arguments
        let raw_tool_calls = response.raw["choices"][0]["message"]["tool_calls"]
            .as_array()
            .unwrap();
        assert_eq!(raw_tool_calls.len(), 1);
        assert_eq!(raw_tool_calls[0]["function"]["name"], "web_fetch");
        let args_str = raw_tool_calls[0]["function"]["arguments"].as_str().unwrap();
        let args: Value = serde_json::from_str(args_str).unwrap();
        assert_eq!(args["url"], "https://example.com");
        // Verify ToolCallDelta events were emitted
        let delta_events: Vec<_> = events
            .iter()
            .filter(|e| matches!(e, ModelStreamEvent::ToolCallDelta { .. }))
            .collect();
        assert_eq!(delta_events.len(), 3);
    }

    #[test]
    fn anthropic_sse_text_stream() {
        let lines = vec![
            r#"data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi "}}"#,
            r#"data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"there"}}"#,
            r#"data: {"type":"message_stop"}"#,
        ];
        let (response, events) = process_anthropic_sse_lines(&lines).unwrap();
        assert_eq!(response.output_text, "Hi there");
        assert!(matches!(&events[0], ModelStreamEvent::Content { content } if content == "Hi "));
        assert!(matches!(&events[1], ModelStreamEvent::Content { content } if content == "there"));
        assert!(matches!(
            events.last().unwrap(),
            ModelStreamEvent::End { .. }
        ));
    }

    #[test]
    fn anthropic_sse_tool_call_partial_json() {
        let lines = vec![
            r#"data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_01","name":"file_ops"}}"#,
            r#"data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"oper"}}"#,
            r#"data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"ation\":\"read\",\"path\":\"src\"}"}}"#,
            r#"data: {"type":"message_stop"}"#,
        ];
        let (response, events) = process_anthropic_sse_lines(&lines).unwrap();
        let raw_tool_calls = response.raw["choices"][0]["message"]["tool_calls"]
            .as_array()
            .unwrap();
        assert_eq!(raw_tool_calls.len(), 1);
        assert_eq!(raw_tool_calls[0]["function"]["name"], "file_ops");
        let args_str = raw_tool_calls[0]["function"]["arguments"].as_str().unwrap();
        let args: Value = serde_json::from_str(args_str).unwrap();
        assert_eq!(args["operation"], "read");
        assert_eq!(args["path"], "src");
        // Check delta events
        let delta_events: Vec<_> = events
            .iter()
            .filter(|e| matches!(e, ModelStreamEvent::ToolCallDelta { .. }))
            .collect();
        assert_eq!(delta_events.len(), 2);
    }

    #[test]
    fn gemini_sse_text_and_function_call() {
        let lines = vec![
            r#"data: {"candidates":[{"content":{"parts":[{"text":"Let me check."}]},"finishReason":null}]}"#,
            r#"data: {"candidates":[{"content":{"parts":[{"functionCall":{"name":"web_fetch","args":{"url":"https://x.com"}}}]},"finishReason":"STOP"}]}"#,
        ];
        let (response, events) = process_gemini_sse_lines(&lines).unwrap();
        assert_eq!(response.output_text, "Let me check.");
        let raw_tool_calls = response.raw["choices"][0]["message"]["tool_calls"]
            .as_array()
            .unwrap();
        assert_eq!(raw_tool_calls.len(), 1);
        assert_eq!(raw_tool_calls[0]["function"]["name"], "web_fetch");
        // Verify events
        assert!(
            matches!(&events[0], ModelStreamEvent::Content { content } if content == "Let me check.")
        );
        assert!(
            matches!(&events[1], ModelStreamEvent::ToolCallDelta { name, .. } if name.as_deref() == Some("web_fetch"))
        );
        assert!(matches!(
            events.last().unwrap(),
            ModelStreamEvent::End { .. }
        ));
    }

    #[test]
    fn openai_sse_multiple_tool_calls() {
        let lines = vec![
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"file_ops","arguments":""}}]},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":1,"id":"call_2","function":{"name":"web_search","arguments":""}}]},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{"tool_calls":[{"index":1,"function":{"arguments":"{\"query\":\"rust\"}"}}]},"index":0,"finish_reason":null}]}"#,
            r#"data: {"choices":[{"delta":{},"index":0,"finish_reason":"tool_calls"}]}"#,
            "data: [DONE]",
        ];
        let (response, _events) = process_openai_sse_lines(&lines).unwrap();
        let raw_tool_calls = response.raw["choices"][0]["message"]["tool_calls"]
            .as_array()
            .unwrap();
        assert_eq!(raw_tool_calls.len(), 2);
        assert_eq!(raw_tool_calls[0]["function"]["name"], "file_ops");
        assert_eq!(raw_tool_calls[1]["function"]["name"], "web_search");
        let args: Value =
            serde_json::from_str(raw_tool_calls[1]["function"]["arguments"].as_str().unwrap())
                .unwrap();
        assert_eq!(args["query"], "rust");
    }
}
