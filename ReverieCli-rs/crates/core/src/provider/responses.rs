use super::*;
use request::{content, image_url, native};

pub(super) fn body(
    model: &Value,
    messages: &[Value],
    tools: &[Value],
    stream: bool,
) -> Result<Value> {
    let mut input = Vec::new();
    for message in messages {
        if message["role"] == "tool" {
            input.push(json!({"type":"function_call_output","call_id":message["tool_call_id"],"output":message["content"]}));
            continue;
        }
        if let Some(items) = native(message, "openai-responses", model) {
            input.extend(items.clone());
            continue;
        }
        let mut blocks = Vec::new();
        for block in content(&message["content"])? {
            match block["type"].as_str().unwrap_or("") {
                "text" | "input_text" | "output_text" => blocks.push(json!({"type":"input_text","text":block["text"]})),
                "image_url" => blocks.push(json!({"type":"input_image","image_url":image_url(&block)?,"detail":block["image_url"]["detail"].as_str().unwrap_or("auto")})),
                "input_image" | "input_file" => blocks.push(block),
                kind => return Err(format!("Unsupported Responses content block: {kind}.").into()),
            }
        }
        if !blocks.is_empty() {
            input.push(json!({"role":message["role"],"content":blocks}));
        }
        if let Some(calls) = message["tool_calls"].as_array() {
            for call in calls {
                input.push(json!({"type":"function_call","call_id":call["id"],"name":call["function"]["name"],"arguments":call["function"]["arguments"]}));
            }
        }
    }
    let mut body = json!({"model":model["model"],"input":input,"stream":stream,"store":false});
    if !tools.is_empty() {
        body["tools"]=json!(tools.iter().map(|tool|json!({"type":"function","name":tool["function"]["name"],"description":tool["function"]["description"],"parameters":tool["function"]["parameters"],"strict":tool["function"]["strict"].as_bool().unwrap_or(false)})).collect::<Vec<_>>());
    }
    Ok(body)
}

impl ModelTurn {
    pub(super) fn responses_delta(&mut self, value: &Value, emit: &impl Fn(Value)) -> Result<()> {
        let kind = value["type"].as_str().unwrap_or("");
        let index = value["output_index"].as_u64().unwrap_or(0) as usize;
        match kind {
            "response.output_text.delta" | "response.refusal.delta" => self.text(
                value["delta"]
                    .as_str()
                    .ok_or("Response text delta is missing.")?,
                false,
                emit,
            ),
            "response.reasoning_summary_text.delta" | "response.reasoning_text.delta" => {
                self.text(value["delta"].as_str().unwrap_or(""), true, emit)
            }
            "response.output_item.added" | "response.output_item.done" => {
                self.response_item(index, &value["item"])?;
            }
            "response.function_call_arguments.delta" => {
                let call = self
                    .tool_calls
                    .get_mut(&index)
                    .ok_or("Response tool arguments arrived before the tool call.")?;
                call.arguments.push_str(
                    value["delta"]
                        .as_str()
                        .ok_or("Response argument delta is missing.")?,
                );
            }
            "response.function_call_arguments.done" => {
                let call = self
                    .tool_calls
                    .get_mut(&index)
                    .ok_or("Completed tool arguments have no owning call.")?;
                call.arguments = value["arguments"]
                    .as_str()
                    .ok_or("Completed tool arguments are missing.")?
                    .into();
            }
            "response.completed" => self.response_full(&value["response"], emit)?,
            "response" => self.response_full(value, emit)?,
            "response.failed" | "response.incomplete" | "error" => {
                return Err("Responses generation did not complete.".into());
            }
            _ if value.get("output").is_some() => self.response_full(value, emit)?,
            _ if value.get("error").is_some() => {
                return Err("Responses returned a generation error.".into());
            }
            _ => {}
        }
        Ok(())
    }

    fn response_item(&mut self, index: usize, item: &Value) -> Result<()> {
        if item["type"] == "function_call" {
            self.tool_calls.insert(
                index,
                ToolCall {
                    id: item["call_id"].as_str().unwrap_or("").into(),
                    name: item["name"].as_str().unwrap_or("").into(),
                    arguments: item["arguments"].as_str().unwrap_or("").into(),
                },
            );
        }
        self.blocks.insert(index, item.clone());
        Ok(())
    }

    fn response_full(&mut self, value: &Value, emit: &impl Fn(Value)) -> Result<()> {
        if value["status"] != "completed" {
            return Err("Responses generation is incomplete or failed.".into());
        }
        let output = value["output"]
            .as_array()
            .ok_or("Response output is missing.")?;
        let mut text = String::new();
        let mut reasoning = String::new();
        self.blocks.clear();
        self.tool_calls.clear();
        for (index, item) in output.iter().enumerate() {
            self.response_item(index, item)?;
            if item["type"] == "message" {
                for part in item["content"].as_array().into_iter().flatten() {
                    if part["type"] == "output_text" {
                        text.push_str(part["text"].as_str().unwrap_or(""));
                    } else if part["type"] == "refusal" {
                        text.push_str(part["refusal"].as_str().unwrap_or(""));
                    }
                }
            } else if item["type"] == "reasoning" {
                for part in item["summary"].as_array().into_iter().flatten() {
                    reasoning.push_str(part["text"].as_str().unwrap_or(""));
                }
            }
        }
        let suffix = text
            .strip_prefix(&self.content)
            .ok_or("Final response differs from the emitted stream.")?
            .to_owned();
        self.text(&suffix, false, emit);
        if let Some(suffix) = reasoning.strip_prefix(&self.reasoning) {
            self.text(suffix, true, emit);
        }
        self.usage = value["usage"].clone();
        self.finished = true;
        self.finish_reason = Some(
            if self.tool_calls.is_empty() {
                "stop"
            } else {
                "tool_calls"
            }
            .into(),
        );
        self.native = Some(json!(output));
        Ok(())
    }
}
