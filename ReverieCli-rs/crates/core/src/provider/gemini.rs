use super::*;
use request::{content, image_url, native};

pub(super) fn body(model: &Value, messages: &[Value], tools: &[Value]) -> Result<Value> {
    let mut system = Vec::new();
    let mut history: Vec<Value> = Vec::new();
    for message in messages {
        let role = message["role"].as_str().ok_or("Message role is missing.")?;
        if ["system", "developer"].contains(&role) {
            system.extend(
                content(&message["content"])?
                    .iter()
                    .map(|block| json!({"text":block["text"]})),
            );
            continue;
        }
        let mut parts = if role == "tool" {
            vec![
                json!({"functionResponse":{"id":message["tool_call_id"],"name":message["name"],"response":{"result":message["content"]}}}),
            ]
        } else if let Some(parts) = native(message, "gemini", model) {
            parts.clone()
        } else {
            let mut parts = Vec::new();
            for block in content(&message["content"])? {
                match block["type"].as_str().unwrap_or("") {
                    "text" | "input_text" => parts.push(json!({"text":block["text"]})),
                    "image_url" => {
                        let url = image_url(&block)?;
                        if let Some(data) = url.strip_prefix("data:") {
                            let (mime, data) = data
                                .split_once(";base64,")
                                .ok_or("Image data must use base64.")?;
                            parts.push(json!({"inlineData":{"mimeType":mime,"data":data}}));
                        } else {
                            parts.push(json!({"fileData":{"fileUri":url,"mimeType":block["mime_type"].as_str().unwrap_or("image/jpeg")}}));
                        }
                    }
                    "input_audio" => {
                        let audio = &block["input_audio"];
                        parts.push(json!({"inlineData":{"mimeType":if audio["format"]=="mp3" {"audio/mpeg"} else {"audio/wav"},"data":audio["data"]}}));
                    }
                    kind => return Err(format!("Unsupported Gemini content block: {kind}.").into()),
                }
            }
            if let Some(calls) = message["tool_calls"].as_array() {
                for call in calls {
                    let args = serde_json::from_str::<Value>(
                        call["function"]["arguments"].as_str().unwrap_or("{}"),
                    )?;
                    let mut part = json!({"functionCall":{"id":call["id"],"name":call["function"]["name"],"args":args}});
                    if let Some(signature) = call.get("thought_signature") {
                        part["thoughtSignature"] = signature.clone();
                    }
                    parts.push(part);
                }
            }
            parts
        };
        if parts.is_empty() {
            continue;
        }
        let role = match role {
            "assistant" => "model",
            "user" | "tool" => "user",
            _ => return Err("Unsupported Gemini message role.".into()),
        };
        if let Some(previous) = history
            .last_mut()
            .filter(|previous| previous["role"] == role)
        {
            previous["parts"]
                .as_array_mut()
                .ok_or("Gemini message parts are invalid.")?
                .append(&mut parts);
        } else {
            history.push(json!({"role":role,"parts":parts}));
        }
    }
    let output = model["max_output_tokens"]
        .as_u64()
        .or_else(|| model["max_tokens"].as_u64())
        .unwrap_or(16_384);
    let mut body = json!({"contents":history,"generationConfig":{"maxOutputTokens":output}});
    for (source, target) in [
        ("temperature", "temperature"),
        ("top_p", "topP"),
        ("top_k", "topK"),
        ("stop", "stopSequences"),
    ] {
        if let Some(value) = model.get(source) {
            body["generationConfig"][target] = value.clone();
        }
    }
    if let Some(thinking) = model["thinking"].as_object() {
        body["generationConfig"]["thinkingConfig"] = json!(thinking);
    }
    if !system.is_empty() {
        body["systemInstruction"] = json!({"parts":system});
    }
    if !tools.is_empty() {
        body["tools"] = json!([{"functionDeclarations":tools.iter().map(|tool|json!({"name":tool["function"]["name"],"description":tool["function"]["description"],"parametersJsonSchema":tool["function"]["parameters"]})).collect::<Vec<_>>()}]);
    }
    Ok(body)
}

impl ModelTurn {
    pub(super) fn gemini_delta(&mut self, value: &Value, emit: &impl Fn(Value)) -> Result<()> {
        if value.get("error").is_some() || value["promptFeedback"].get("blockReason").is_some() {
            return Err("Gemini returned a generation error or blocked input.".into());
        }
        if let Some(usage) = value.get("usageMetadata") {
            self.usage = usage.clone();
        }
        if let Some(candidate) = value["candidates"]
            .as_array()
            .and_then(|candidates| candidates.first())
        {
            for part in candidate["content"]["parts"]
                .as_array()
                .into_iter()
                .flatten()
            {
                let mut part = part.clone();
                if let Some(text) = part["text"].as_str() {
                    self.text(text, part["thought"].as_bool().unwrap_or(false), emit);
                }
                if let Some(function) = part.get_mut("functionCall") {
                    if function.get("partialArgs").is_some() {
                        return Err(
                            "Partial Gemini function arguments require their complete call.".into(),
                        );
                    }
                    let index = self.tool_calls.len();
                    let id = function["id"]
                        .as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| format!("call_{}", uuid::Uuid::new_v4().simple()));
                    function["id"] = json!(id);
                    self.tool_calls.insert(
                        index,
                        ToolCall {
                            id,
                            name: function["name"].as_str().unwrap_or("").into(),
                            arguments: serde_json::to_string(
                                function.get("args").unwrap_or(&json!({})),
                            )?,
                        },
                    );
                }
                self.blocks.insert(self.blocks.len(), part);
            }
            if let Some(reason) = candidate["finishReason"].as_str() {
                self.finish_reason = Some(
                    match reason {
                        "STOP" => {
                            if self.tool_calls.is_empty() {
                                "stop"
                            } else {
                                "tool_calls"
                            }
                        }
                        "MAX_TOKENS" => "length",
                        _ => return Err(format!("Gemini generation stopped: {reason}.").into()),
                    }
                    .into(),
                );
                self.finished = true;
                self.native = Some(json!(self.blocks.values().collect::<Vec<_>>()));
            }
        }
        Ok(())
    }
}
