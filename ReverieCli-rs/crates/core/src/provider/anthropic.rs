use super::*;
use request::{content, image_url, native};

pub(super) fn body(
    model: &Value,
    messages: &[Value],
    tools: &[Value],
    stream: bool,
) -> Result<Value> {
    let mut system = Vec::new();
    let mut history: Vec<Value> = Vec::new();
    for message in messages {
        let role = message["role"].as_str().ok_or("Message role is missing.")?;
        if ["system", "developer"].contains(&role) {
            system.extend(content(&message["content"])?);
            continue;
        }
        let mut blocks = if role == "tool" {
            vec![
                json!({"type":"tool_result","tool_use_id":message["tool_call_id"],"content":message["content"]}),
            ]
        } else if let Some(blocks) = native(message, "anthropic", model) {
            blocks.clone()
        } else {
            let mut blocks = Vec::new();
            for block in content(&message["content"])? {
                match block["type"].as_str().unwrap_or("") {
                    "text" | "input_text" => {
                        blocks.push(json!({"type":"text","text":block["text"]}))
                    }
                    "image_url" | "input_image" => {
                        let url = if block["type"] == "input_image" {
                            block["image_url"].as_str().ok_or("Image URL is missing.")?
                        } else {
                            image_url(&block)?
                        };
                        let source = if let Some(data) = url.strip_prefix("data:") {
                            let (mime, data) = data
                                .split_once(";base64,")
                                .ok_or("Image data must use base64.")?;
                            json!({"type":"base64","media_type":mime,"data":data})
                        } else {
                            json!({"type":"url","url":url})
                        };
                        blocks.push(json!({"type":"image","source":source}));
                    }
                    "image" | "document" => blocks.push(block),
                    kind => {
                        return Err(format!("Unsupported Anthropic content block: {kind}.").into());
                    }
                }
            }
            if let Some(calls) = message["tool_calls"].as_array() {
                for call in calls {
                    let input = serde_json::from_str::<Value>(
                        call["function"]["arguments"].as_str().unwrap_or("{}"),
                    )?;
                    blocks.push(json!({"type":"tool_use","id":call["id"],"name":call["function"]["name"],"input":input}));
                }
            }
            blocks
        };
        if blocks.is_empty() {
            continue;
        }
        let role = if role == "tool" { "user" } else { role };
        if !["assistant", "user"].contains(&role) {
            return Err("Unsupported Anthropic message role.".into());
        }
        if let Some(previous) = history
            .last_mut()
            .filter(|previous| previous["role"] == role)
        {
            previous["content"]
                .as_array_mut()
                .ok_or("Message content is invalid.")?
                .append(&mut blocks);
        } else {
            history.push(json!({"role":role,"content":blocks}));
        }
    }
    let mut body =
        json!({"model":model["model"],"messages":history,"stream":stream,"max_tokens":16_384});
    if !system.is_empty() {
        body["system"] = json!(system);
    }
    if !tools.is_empty() {
        body["tools"]=json!(tools.iter().map(|tool|json!({"name":tool["function"]["name"],"description":tool["function"]["description"],"input_schema":tool["function"]["parameters"]})).collect::<Vec<_>>());
    }
    Ok(body)
}

impl ModelTurn {
    pub(super) fn anthropic_delta(&mut self, value: &Value, emit: &impl Fn(Value)) -> Result<()> {
        let kind = value["type"].as_str().unwrap_or("");
        if kind == "error" || value.get("error").is_some() {
            return Err("Anthropic returned a generation error.".into());
        }
        let index = value["index"].as_u64().unwrap_or(0) as usize;
        match kind {
            "message" => {
                for (index, block) in value["content"]
                    .as_array()
                    .ok_or("Anthropic content is missing.")?
                    .iter()
                    .enumerate()
                {
                    self.anthropic_block(index, block, emit)?;
                }
                self.finish_reason = value["stop_reason"].as_str().map(str::to_owned);
                self.finished = self.finish_reason.is_some();
                self.usage = value["usage"].clone();
                self.anthropic_complete()?;
            }
            "message_start" => {
                self.usage = value["message"]["usage"].clone();
            }
            "content_block_start" => {
                self.anthropic_block(index, &value["content_block"], emit)?;
            }
            "content_block_delta" => {
                let delta = &value["delta"];
                let (field, reasoning) = match delta["type"].as_str().unwrap_or("") {
                    "text_delta" => ("text", Some(false)),
                    "thinking_delta" => ("thinking", Some(true)),
                    "signature_delta" => ("signature", None),
                    "input_json_delta" => {
                        let call = self
                            .tool_calls
                            .get_mut(&index)
                            .ok_or("Tool arguments arrived before their content block.")?;
                        call.arguments.push_str(
                            delta["partial_json"]
                                .as_str()
                                .ok_or("Tool argument delta is missing.")?,
                        );
                        return Ok(());
                    }
                    _ => return Ok(()),
                };
                let text = delta[field]
                    .as_str()
                    .ok_or("Anthropic content delta is missing.")?;
                if let Some(reasoning) = reasoning {
                    self.text(text, reasoning, emit);
                }
                let block = self
                    .blocks
                    .get_mut(&index)
                    .ok_or("Content delta arrived before its block.")?;
                let previous = block[field].as_str().unwrap_or("");
                block[field] = json!(format!("{previous}{text}"));
            }
            "content_block_stop" => {
                if let Some(call) = self.tool_calls.get_mut(&index) {
                    let block = self
                        .blocks
                        .get_mut(&index)
                        .ok_or("Tool block is missing.")?;
                    if call.arguments.is_empty() {
                        call.arguments = serde_json::to_string(&block["input"])?;
                    }
                    block["input"] = serde_json::from_str::<Value>(&call.arguments)?;
                }
            }
            "message_delta" => {
                self.finish_reason = value["delta"]["stop_reason"].as_str().map(str::to_owned);
                if let Some(usage) = value["usage"].as_object() {
                    if !self.usage.is_object() {
                        self.usage = json!({});
                    }
                    for (key, value) in usage {
                        self.usage[key] = value.clone();
                    }
                }
            }
            "message_stop" => {
                self.finished = self.finish_reason.is_some();
                self.anthropic_complete()?;
            }
            _ => {}
        }
        Ok(())
    }

    fn anthropic_block(
        &mut self,
        index: usize,
        block: &Value,
        emit: &impl Fn(Value),
    ) -> Result<()> {
        let kind = block["type"]
            .as_str()
            .ok_or("Anthropic content block type is missing.")?;
        match kind {
            "text" => self.text(block["text"].as_str().unwrap_or(""), false, emit),
            "thinking" => self.text(block["thinking"].as_str().unwrap_or(""), true, emit),
            "tool_use" => {
                self.tool_calls.insert(
                    index,
                    ToolCall {
                        id: block["id"].as_str().unwrap_or("").into(),
                        name: block["name"].as_str().unwrap_or("").into(),
                        arguments: if block["input"]
                            .as_object()
                            .is_some_and(|value| value.is_empty())
                        {
                            String::new()
                        } else {
                            serde_json::to_string(&block["input"])?
                        },
                    },
                );
            }
            _ => {}
        }
        self.blocks.insert(index, block.clone());
        Ok(())
    }

    fn anthropic_complete(&mut self) -> Result<()> {
        for (index, call) in &mut self.tool_calls {
            let block = self.blocks.get_mut(index).ok_or("Tool block is missing.")?;
            if call.arguments.is_empty() {
                call.arguments = serde_json::to_string(&block["input"])?;
            }
            block["input"] = serde_json::from_str::<Value>(&call.arguments)?;
        }
        self.native = Some(json!(self.blocks.values().collect::<Vec<_>>()));
        Ok(())
    }
}
