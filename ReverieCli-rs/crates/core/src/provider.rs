use crate::Result;
use serde_json::{Value, json};
use std::{collections::BTreeMap, time::Duration};
use tokio_util::sync::CancellationToken;

#[derive(Debug, Clone)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: String,
}

#[derive(Default, Debug)]
pub struct ModelTurn {
    pub content: String,
    pub reasoning: String,
    pub tool_calls: BTreeMap<usize, ToolCall>,
    pub usage: Value,
    pub finish_reason: Option<String>,
}

impl ModelTurn {
    fn delta(&mut self, value: &Value, emit: &impl Fn(Value)) -> Result<()> {
        if let Some(error) = value.get("error") {
            return Err(format!(
                "Provider stream error: {}",
                error["type"].as_str().unwrap_or("unknown")
            )
            .into());
        }
        if let Some(usage) = value.get("usage").filter(|usage| !usage.is_null()) {
            self.usage = usage.clone();
        }
        let choice = &value["choices"][0];
        if let Some(reason) = choice["finish_reason"].as_str() {
            self.finish_reason = Some(reason.into());
        }
        let delta = choice.get("delta").unwrap_or(&choice["message"]);
        if let Some(content) = delta["content"].as_str().filter(|text| !text.is_empty()) {
            self.content.push_str(content);
            emit(json!({"type":"assistant.delta","text":content}));
        }
        if let Some(reasoning) = delta
            .get("reasoning_content")
            .or_else(|| delta.get("reasoning"))
            .and_then(Value::as_str)
            .filter(|text| !text.is_empty())
        {
            self.reasoning.push_str(reasoning);
            emit(json!({"type":"reasoning.delta","text":reasoning}));
        }
        if let Some(calls) = delta["tool_calls"].as_array() {
            for (position, call) in calls.iter().enumerate() {
                let index = call["index"].as_u64().unwrap_or(position as u64) as usize;
                let entry = self.tool_calls.entry(index).or_insert(ToolCall {
                    id: String::new(),
                    name: String::new(),
                    arguments: String::new(),
                });
                if let Some(id) = call["id"].as_str() {
                    entry.id.push_str(id);
                }
                if let Some(name) = call["function"]["name"].as_str() {
                    entry.name.push_str(name);
                }
                if let Some(args) = call["function"]["arguments"].as_str() {
                    entry.arguments.push_str(args);
                }
            }
        }
        Ok(())
    }
}

#[derive(Default)]
struct Events {
    pending: Vec<u8>,
    data: Vec<String>,
    data_bytes: usize,
    after_cr: bool,
    finished: bool,
}

impl Events {
    fn line(&mut self, line: &[u8], turn: &mut ModelTurn, emit: &impl Fn(Value)) -> Result<()> {
        let line = std::str::from_utf8(line)?.trim_end_matches('\r');
        if line.is_empty() {
            if !self.data.is_empty() {
                let data = self.data.join("\n");
                self.data.clear();
                self.data_bytes = 0;
                if data.trim() == "[DONE]" {
                    self.finished = true;
                } else {
                    turn.delta(&serde_json::from_str::<Value>(&data)?, emit)?;
                }
            }
        } else if let Some(data) = line.strip_prefix("data:") {
            self.data_bytes += data.len() + 1;
            if self.data_bytes > 16 * 1024 * 1024 {
                return Err("Provider stream event exceeds the supported size.".into());
            }
            self.data
                .push(data.strip_prefix(' ').unwrap_or(data).to_owned());
        }
        Ok(())
    }

    fn push(&mut self, bytes: &[u8], turn: &mut ModelTurn, emit: &impl Fn(Value)) -> Result<()> {
        for &byte in bytes {
            if self.finished {
                break;
            }
            if self.after_cr {
                self.after_cr = false;
                if byte == b'\n' {
                    continue;
                }
            }
            if byte == b'\r' || byte == b'\n' {
                let line = std::mem::take(&mut self.pending);
                self.line(&line, turn, emit)?;
                self.after_cr = byte == b'\r';
            } else {
                self.pending.push(byte);
                if self.pending.len() > 16 * 1024 * 1024 {
                    return Err("Provider stream event exceeds the supported size.".into());
                }
            }
        }
        Ok(())
    }

    fn end(&mut self, turn: &mut ModelTurn, emit: &impl Fn(Value)) -> Result<()> {
        let pending = std::mem::take(&mut self.pending);
        if !pending.is_empty() {
            self.line(&pending, turn, emit)?;
        }
        self.line(&[], turn, emit)
    }
}

pub struct ProviderClient {
    client: reqwest::Client,
}

impl ProviderClient {
    pub fn new(proxy: Option<&str>) -> Result<Self> {
        let mut builder = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(30))
            .pool_idle_timeout(Duration::from_secs(90));
        if let Some(proxy) = proxy.filter(|value| !value.trim().is_empty()) {
            builder = builder.proxy(reqwest::Proxy::all(proxy)?);
        }
        Ok(Self {
            client: builder.build()?,
        })
    }

    pub async fn chat(
        &self,
        model: &Value,
        config: &Value,
        messages: &[Value],
        tools: &[Value],
        cancel: &CancellationToken,
        emit: impl Fn(Value),
    ) -> Result<ModelTurn> {
        let transport = model["provider"].as_str().unwrap_or("openai-chat");
        if !["openai-chat", "openai", "request", "curl"].contains(&transport) {
            return Err(format!("Transport {transport} is not yet migrated.").into());
        }
        let base = model["base_url"]
            .as_str()
            .ok_or("Model base_url is required.")?
            .trim_end_matches('/');
        let endpoint = model["endpoint"]
            .as_str()
            .filter(|endpoint| !endpoint.is_empty())
            .unwrap_or("/chat/completions");
        let address = if endpoint.starts_with("http://") || endpoint.starts_with("https://") {
            endpoint.to_owned()
        } else if base.ends_with(endpoint) {
            base.to_owned()
        } else {
            format!("{base}/{}", endpoint.trim_start_matches('/'))
        };
        let stream = config["stream_responses"].as_bool().unwrap_or(true);
        let mut body = json!({"model":model["model"],"messages":messages,"stream":stream});
        if !tools.is_empty() {
            body["tools"] = json!(tools);
            body["tool_choice"] = json!("auto");
        }
        let mut request = self
            .client
            .post(&address)
            .timeout(Duration::from_secs(
                config["api_timeout"].as_u64().unwrap_or(120).max(1),
            ))
            .json(&body);
        let key = model["api_key"]
            .as_str()
            .filter(|key| !key.trim().is_empty())
            .map(str::to_owned)
            .or_else(|| {
                model["api_key_env"]
                    .as_str()
                    .and_then(|key| std::env::var(key).ok())
            });
        if let Some(key) = key {
            request = request.bearer_auth(key);
        }
        if let Some(headers) = model["custom_headers"].as_object() {
            for (name, value) in headers {
                request = request.header(
                    name,
                    value.as_str().ok_or("Custom header values must be text.")?,
                );
            }
        }
        let mut response = tokio::select! {_ = cancel.cancelled()=>return Err("Run cancelled.".into()),response=request.send()=>response.map_err(|error|format!("Provider request failed: {}",error.without_url()))?};
        if !response.status().is_success() {
            return Err(format!("Provider returned HTTP {}.", response.status()).into());
        }
        let mut turn = ModelTurn::default();
        if !stream
            || !response
                .headers()
                .get("content-type")
                .and_then(|value| value.to_str().ok())
                .is_some_and(|value| value.contains("text/event-stream"))
        {
            let value = tokio::select! {_ = cancel.cancelled()=>return Err("Run cancelled.".into()),result=response.json::<Value>()=>result.map_err(|error|format!("Provider response failed: {}",error.without_url()))?};
            turn.delta(&value, &emit)?;
        } else {
            let mut events = Events::default();
            loop {
                let bytes = tokio::select! {_ = cancel.cancelled()=>return Err("Run cancelled.".into()),result=response.chunk()=>result.map_err(|error|format!("Provider stream failed: {}",error.without_url()))?};
                let Some(bytes) = bytes else {
                    events.end(&mut turn, &emit)?;
                    break;
                };
                events.push(&bytes, &mut turn, &emit)?;
                if events.finished {
                    break;
                }
            }
            if !events.finished && turn.finish_reason.is_none() {
                return Err("Provider stream ended before a completion marker.".into());
            }
        }
        if turn
            .finish_reason
            .as_deref()
            .is_some_and(|reason| ["length", "content_filter"].contains(&reason))
        {
            return Err(format!(
                "Provider could not complete the response: {}.",
                turn.finish_reason.as_deref().unwrap()
            )
            .into());
        }
        for call in turn.tool_calls.values() {
            if call.id.is_empty() || call.name.is_empty() {
                return Err("Provider returned an incomplete tool call.".into());
            }
        }
        if turn.content.is_empty() && turn.tool_calls.is_empty() {
            return Err("Provider returned no response or tool calls.".into());
        }
        Ok(turn)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sse_handles_split_utf8_crlf_comments_and_fragmented_tool_arguments() {
        let input = concat!(
            ":comment\r\n",
            "data: {\"choices\":[{\"delta\":{\"content\":\"中文😀\",\"tool_calls\":[{\"index\":0,\"id\":\"call-1\",\"function\":{\"name\":\"file_ops\",\"arguments\":\"{\\\"path\\\":\"}}]}}]}\r\n\r\n",
            "data: {\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"function\":{\"arguments\":\"\\\"a.txt\\\"}\"}}]}}]}\n\n",
            "data: [DONE]\n\n"
        );
        let mut events = Events::default();
        let mut turn = ModelTurn::default();
        for bytes in input.as_bytes().chunks(1) {
            events.push(bytes, &mut turn, &|_| {}).unwrap();
        }
        assert!(events.finished);
        assert_eq!(turn.content, "中文😀");
        assert_eq!(turn.tool_calls[&0].id, "call-1");
        assert_eq!(
            serde_json::from_str::<Value>(&turn.tool_calls[&0].arguments).unwrap()["path"],
            "a.txt"
        );
        let mut events = Events::default();
        let mut turn = ModelTurn::default();
        for bytes in b"data: {\"choices\":[{\"delta\":{\"content\":\"CR\"}}]}\r\rdata: [DONE]\r\rdata: {\"choices\":[{\"delta\":{\"content\":\"ignored\"}}]}\r\r".chunks(1) {
            events.push(bytes, &mut turn, &|_| {}).unwrap();
        }
        assert!(events.finished);
        assert_eq!(turn.content, "CR");
    }
}
