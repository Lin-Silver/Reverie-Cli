use crate::Result;
use serde_json::{Value, json};
use std::{collections::BTreeMap, time::Duration};
use tokio_util::sync::CancellationToken;

mod anthropic;
mod gemini;
mod request;
mod responses;
use request::Transport;

pub fn transport_name(name: &str) -> Result<&'static str> {
    Ok(Transport::parse(name)?.name())
}

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
    pub native: Option<Value>,
    blocks: BTreeMap<usize, Value>,
    finished: bool,
}

impl ModelTurn {
    fn text(&mut self, text: &str, reasoning: bool, emit: &impl Fn(Value)) {
        if text.is_empty() {
            return;
        }
        if reasoning {
            self.reasoning.push_str(text);
        } else {
            self.content.push_str(text);
        }
        emit(json!({"type":if reasoning {"reasoning.delta"} else {"assistant.delta"},"text":text}));
    }

    fn delta(&mut self, transport: Transport, value: &Value, emit: &impl Fn(Value)) -> Result<()> {
        match transport {
            Transport::Chat => self.chat_delta(value, emit),
            Transport::Responses => self.responses_delta(value, emit),
            Transport::Anthropic => self.anthropic_delta(value, emit),
            Transport::Gemini => self.gemini_delta(value, emit),
        }
    }

    fn chat_delta(&mut self, value: &Value, emit: &impl Fn(Value)) -> Result<()> {
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
    fn line(
        &mut self,
        line: &[u8],
        transport: Transport,
        turn: &mut ModelTurn,
        emit: &impl Fn(Value),
    ) -> Result<()> {
        let line = std::str::from_utf8(line)?.trim_end_matches('\r');
        if line.is_empty() {
            if !self.data.is_empty() {
                let data = self.data.join("\n");
                self.data.clear();
                self.data_bytes = 0;
                if data.trim() == "[DONE]" {
                    self.finished = true;
                } else {
                    turn.delta(transport, &serde_json::from_str::<Value>(&data)?, emit)?;
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

    fn push(
        &mut self,
        bytes: &[u8],
        transport: Transport,
        turn: &mut ModelTurn,
        emit: &impl Fn(Value),
    ) -> Result<()> {
        for &byte in bytes {
            if self.finished || turn.finished {
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
                self.line(&line, transport, turn, emit)?;
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

    fn end(
        &mut self,
        transport: Transport,
        turn: &mut ModelTurn,
        emit: &impl Fn(Value),
    ) -> Result<()> {
        let pending = std::mem::take(&mut self.pending);
        if !pending.is_empty() {
            self.line(&pending, transport, turn, emit)?;
        }
        self.line(&[], transport, turn, emit)
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
        let transport = Transport::parse(model["provider"].as_str().unwrap_or("openai-chat"))?;
        let stream = config["stream_responses"].as_bool().unwrap_or(true);
        let address = transport.address(model, stream)?;
        let body = transport.body(model, messages, tools, stream)?;
        let mut request = self
            .client
            .post(address)
            .timeout(Duration::from_secs(
                model["request_timeout"]
                    .as_u64()
                    .or(config["api_timeout"].as_u64())
                    .unwrap_or(60)
                    .max(1),
            ))
            .json(&body);
        request = transport.authenticate(request, model)?;
        if let Some(headers) = model["custom_headers"].as_object() {
            for (name, value) in headers {
                request = request.header(
                    name,
                    value.as_str().ok_or("Custom header values must be text.")?,
                );
            }
        }
        let mut response = self.send(request, config, cancel, &emit).await?;
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
            turn.delta(transport, &value, &emit)?;
            if transport != Transport::Chat && !turn.finished {
                return Err("Provider response has no completed generation record.".into());
            }
        } else {
            let mut events = Events::default();
            loop {
                let bytes = tokio::select! {_ = cancel.cancelled()=>return Err("Run cancelled.".into()),result=response.chunk()=>result.map_err(|error|format!("Provider stream failed: {}",error.without_url()))?};
                let Some(bytes) = bytes else {
                    events.end(transport, &mut turn, &emit)?;
                    break;
                };
                events.push(&bytes, transport, &mut turn, &emit)?;
                if events.finished || turn.finished {
                    break;
                }
            }
            let completed = if transport == Transport::Chat {
                events.finished || turn.finish_reason.is_some()
            } else {
                turn.finished
            };
            if !completed {
                return Err("Provider stream ended before a completion marker.".into());
            }
        }
        if turn.finish_reason.as_deref().is_some_and(|reason| {
            ["length", "content_filter", "max_tokens", "pause_turn"].contains(&reason)
        }) {
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
        if let Some(native) = turn.native.take() {
            turn.native =
                Some(json!({"transport":transport.name(),"model":model["model"],"content":native}));
        }
        Ok(turn)
    }

    async fn send(
        &self,
        request: reqwest::RequestBuilder,
        config: &Value,
        cancel: &CancellationToken,
        emit: &impl Fn(Value),
    ) -> Result<reqwest::Response> {
        let retries = config["api_max_retries"].as_u64().unwrap_or(5);
        let initial = config["api_initial_backoff"].as_f64().unwrap_or(1.0);
        if !initial.is_finite() || initial < 0.0 {
            return Err("API retry backoff must be finite and nonnegative.".into());
        }
        for attempt in 0..=retries {
            let next = request
                .try_clone()
                .ok_or("Provider request cannot be retried.")?;
            let response = tokio::select! { _ = cancel.cancelled()=>return Err("Run cancelled.".into()), response=next.send()=>response };
            let mut cooldown = 0.0;
            let retry = match &response {
                Ok(response) => {
                    if let Some(value) = response
                        .headers()
                        .get("retry-after")
                        .and_then(|value| value.to_str().ok())
                    {
                        cooldown = value
                            .parse::<f64>()
                            .ok()
                            .filter(|value| value.is_finite())
                            .unwrap_or_else(|| {
                                chrono::DateTime::parse_from_rfc2822(value)
                                    .map(|time| {
                                        (time.timestamp() - chrono::Utc::now().timestamp()) as f64
                                    })
                                    .unwrap_or(0.0)
                            });
                    }
                    response.status().as_u16() == 429
                        || response.status().is_server_error()
                        || response.status().as_u16() == 402
                            && response.headers().contains_key("retry-after")
                }
                Err(error) => {
                    error.is_connect()
                        || error.is_timeout()
                        || error.is_body()
                        || error.is_request()
                }
            };
            if !retry || attempt == retries {
                return response.map_err(|error| {
                    format!("Provider request failed: {}", error.without_url()).into()
                });
            }
            drop(response);
            let delays = [1.0, 3.0, 5.0, 7.0, 15.0];
            let delay = (delays[attempt.min(4) as usize] * initial)
                .max(cooldown)
                .max(0.0);
            let delay = Duration::try_from_secs_f64(delay)?;
            emit(
                json!({"type":"model.retry","attempt":attempt+1,"delay_seconds":delay.as_secs_f64()}),
            );
            tokio::select! { _ = cancel.cancelled()=>return Err("Run cancelled.".into()), _ = tokio::time::sleep(delay)=>{} }
        }
        unreachable!("a finite retry loop always returns")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stream(transport: Transport, records: &[Value]) -> ModelTurn {
        let mut events = Events::default();
        let mut turn = ModelTurn::default();
        for record in records {
            let bytes = format!("data: {}\r\n\r\n", serde_json::to_string(record).unwrap());
            for byte in bytes.as_bytes().chunks(1) {
                events.push(byte, transport, &mut turn, &|_| {}).unwrap();
            }
        }
        turn
    }

    #[test]
    fn anthropic_signed_thinking_and_fragmented_tool_input_round_trip_without_duplication() {
        let records = vec![
            json!({"type":"message_start","message":{"usage":{"input_tokens":9}}}),
            json!({"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":"","signature":""}}),
            json!({"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"中文😀"}}),
            json!({"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"opaque-"}}),
            json!({"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"signature"}}),
            json!({"type":"content_block_stop","index":0}),
            json!({"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"call-native","name":"list_files","input":{}}}),
            json!({"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"path\":"}}),
            json!({"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"\".\"}"}}),
            json!({"type":"content_block_stop","index":1}),
            json!({"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":6}}),
            json!({"type":"message_stop"}),
        ];
        let turn = stream(Transport::Anthropic, &records);
        assert!(turn.finished);
        assert_eq!(turn.reasoning, "中文😀");
        assert_eq!(turn.usage, json!({"input_tokens":9,"output_tokens":6}));
        let model =
            json!({"model":"native","provider":"anthropic","base_url":"https://example.test/v1"});
        let native =
            json!({"transport":"anthropic","model":"native","content":turn.native.unwrap()});
        let history = vec![
            json!({"role":"assistant","content":"","tool_calls":[{"id":"call-native","function":{"name":"list_files","arguments":"{}"}}],"provider_content":native}),
            json!({"role":"tool","tool_call_id":"call-native","content":"exact result"}),
        ];
        let body = Transport::Anthropic
            .body(&model, &history, &[], true)
            .unwrap();
        assert_eq!(body["messages"][0]["content"].as_array().unwrap().len(), 2);
        assert_eq!(
            body["messages"][0]["content"][0]["signature"],
            "opaque-signature"
        );
        assert_eq!(body["messages"][0]["content"][1]["input"]["path"], ".");
        assert_eq!(
            body["messages"][1]["content"][0]["tool_use_id"],
            "call-native"
        );
        let mut turn = ModelTurn::default();
        turn.anthropic_delta(&json!({"type":"message","stop_reason":"tool_use","usage":{},"content":[{"type":"tool_use","id":"empty","name":"list_files","input":{}}]}),&|_|{}).unwrap();
        assert_eq!(turn.tool_calls[&0].arguments, "{}");
    }

    #[test]
    fn responses_preserve_encrypted_reasoning_and_complete_calls_after_argument_deltas() {
        let call = json!({"type":"function_call","id":"fc","call_id":"call-response","name":"list_files","arguments":"{}","status":"completed"});
        let reasoning = json!({"type":"reasoning","id":"rs","encrypted_content":"opaque-reasoning","summary":[{"type":"summary_text","text":"thought"}]});
        let records = vec![
            json!({"type":"response.reasoning_summary_text.delta","delta":"thought"}),
            json!({"type":"response.output_item.added","output_index":1,"item":{"type":"function_call","call_id":"call-response","name":"list_files","arguments":""}}),
            json!({"type":"response.function_call_arguments.delta","output_index":1,"delta":"{"}),
            json!({"type":"response.function_call_arguments.delta","output_index":1,"delta":"}"}),
            json!({"type":"response.function_call_arguments.done","output_index":1,"arguments":"{}"}),
            json!({"type":"response.output_item.done","output_index":1,"item":call}),
            json!({"type":"response.completed","response":{"status":"completed","output":[reasoning,call],"usage":{}}}),
        ];
        let turn = stream(Transport::Responses, &records);
        assert!(turn.finished);
        assert_eq!(turn.reasoning, "thought");
        assert_eq!(turn.tool_calls[&1].arguments, "{}");
        let model = json!({"model":"native","provider":"openai-responses","base_url":"https://example.test/v1"});
        let history = vec![
            json!({"role":"assistant","content":"","provider_content":{"transport":"openai-responses","model":"native","content":turn.native.unwrap()}}),
            json!({"role":"tool","tool_call_id":"call-response","content":"exact result"}),
        ];
        let body = Transport::Responses
            .body(&model, &history, &[], true)
            .unwrap();
        assert_eq!(body["input"].as_array().unwrap().len(), 3);
        assert_eq!(body["input"][0]["encrypted_content"], "opaque-reasoning");
        assert_eq!(body["input"][2]["call_id"], "call-response");
    }

    #[test]
    fn gemini_keeps_signatures_on_their_original_parts_and_requires_a_finish_record() {
        let records = vec![
            json!({"candidates":[{"content":{"parts":[{"text":"中文😀","thought":true},{"functionCall":{"name":"list_files","args":{}},"thoughtSignature":"opaque-signature"}]}}]}),
            json!({"candidates":[{"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":9}}),
        ];
        let turn = stream(Transport::Gemini, &records);
        assert!(turn.finished);
        assert_eq!(turn.reasoning, "中文😀");
        let id = turn.tool_calls[&0].id.clone();
        let model = json!({"model":"native","provider":"gemini","base_url":"https://example.test"});
        let history = vec![
            json!({"role":"assistant","content":"","provider_content":{"transport":"gemini","model":"native","content":turn.native.unwrap()}}),
            json!({"role":"tool","tool_call_id":id,"name":"list_files","content":"exact result"}),
        ];
        let body = Transport::Gemini.body(&model, &history, &[], true).unwrap();
        assert_eq!(body["contents"][0]["parts"].as_array().unwrap().len(), 2);
        assert_eq!(
            body["contents"][0]["parts"][1]["thoughtSignature"],
            "opaque-signature"
        );
        assert_eq!(
            body["contents"][1]["parts"][0]["functionResponse"]["id"],
            id
        );
        assert_eq!(
            Transport::Gemini.address(&model, true).unwrap().path(),
            "/v1beta/models/native:streamGenerateContent"
        );
        assert!(!stream(Transport::Gemini, &records[..1]).finished);
    }

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
            events
                .push(bytes, Transport::Chat, &mut turn, &|_| {})
                .unwrap();
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
            events.push(bytes, Transport::Chat, &mut turn, &|_| {}).unwrap();
        }
        assert!(events.finished);
        assert_eq!(turn.content, "CR");
    }
}
