use crate::config::Config;
use crate::providers::resolve_model;
use crate::{ReverieError, ReverieResult};
use regex::Regex;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::time::Duration;
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
                "query_type": {"type": "string", "enum": ["search", "outline", "symbol"]},
                "query": {"type": "string"}
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
                "operation": {"type": "string"},
                "tasks": {"type": "array", "items": {"type": "object"}},
                "title": {"type": "string"}
            },
            "required": []
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

pub async fn send_openai_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    let model = request.model;
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;
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
        "messages": request.messages,
        "tools": request.tools,
        "stream": false
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
        if let Some(extra) = request.extra_body.as_object() {
            for (key, value) in extra {
                object.insert(key.clone(), value.clone());
            }
        }
    }
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(config.api_timeout))
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
    })
}

pub async fn send_anthropic_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
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
    let key = selected
        .api_key_env
        .as_deref()
        .and_then(|name| std::env::var(name).ok())
        .ok_or_else(|| {
            ReverieError::InvalidInput(format!(
                "API key env var is not configured or not set for {model}"
            ))
        })?;
    let payload = build_anthropic_payload(&selected.model, request);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(config.api_timeout))
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
    })
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
        if transport.contains("anthropic") {
            send_anthropic_compatible(config, request).await
        } else {
            send_openai_compatible(config, request).await
        }
    }
}

/// Send request to NVIDIA API
pub async fn send_nvidia_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to NVIDIA API");

    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;

    let api_key = provider_api_key(config, "nvidia", "NVIDIA_API_KEY")?;

    let base_url = selected
        .base_url
        .as_deref()
        .unwrap_or("https://integrate.api.nvidia.com/v1");

    let mut payload = validate_and_sanitize_payload(json!({
        "model": selected.model,
        "messages": request.messages,
        "tools": request.tools,
        "stream": false
    }))?;

    // Add NVIDIA-specific defaults
    if let Some(object) = payload.as_object_mut() {
        // NVIDIA-specific parameters
        object.entry("temperature").or_insert(json!(0.7));

        if let Some(extra) = request.extra_body.as_object() {
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
    })
}

/// Send request to ModelScope API
pub async fn send_modelscope_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to ModelScope API");

    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;

    let api_key = provider_api_key(config, "modelscope", "MODELSCOPE_API_KEY")?;

    let base_url = selected
        .base_url
        .as_deref()
        .unwrap_or("https://api-inference.modelscope.cn/v1");

    let payload = build_anthropic_payload(&selected.model, request);

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
    })
}

/// Send request to Codex API
pub async fn send_codex_compatible(
    config: &Config,
    request: ChatRequest,
) -> ReverieResult<ChatResponse> {
    info!("Sending request to Codex API");

    let model = request.model.clone();
    let selected = config
        .models
        .iter()
        .find(|item| item.name == model || item.model == model)
        .ok_or_else(|| ReverieError::InvalidInput(format!("model not configured: {model}")))?;

    let api_key = provider_api_key(config, "codex", "OPENAI_API_KEY")?;

    let base_url = selected
        .base_url
        .as_deref()
        .unwrap_or("https://api.openai.com/v1");

    let payload = validate_and_sanitize_payload(json!({
        "model": selected.model,
        "messages": request.messages,
        "tools": request.tools,
        "stream": false,
        "reasoning_effort": request.extra_body.get("reasoning_effort")
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
    })
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
}
