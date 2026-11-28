use super::*;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Transport {
    Chat,
    Responses,
    Anthropic,
    Gemini,
}

impl Transport {
    pub fn parse(name: &str) -> Result<Self> {
        match name {
            "openai" | "openai-chat" | "request" | "curl" => Ok(Self::Chat),
            "openai-responses" | "responses" => Ok(Self::Responses),
            "anthropic" | "anthropic-messages" | "claude" => Ok(Self::Anthropic),
            "gemini" => Ok(Self::Gemini),
            name => Err(format!("Transport {name} is not yet migrated.").into()),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Chat => "openai-chat",
            Self::Responses => "openai-responses",
            Self::Anthropic => "anthropic",
            Self::Gemini => "gemini",
        }
    }

    pub fn address(self, model: &Value, stream: bool) -> Result<reqwest::Url> {
        let base = model["base_url"]
            .as_str()
            .ok_or("Model base_url is required.")?
            .trim_end_matches('/');
        let endpoint = model["endpoint"].as_str().filter(|value| !value.is_empty());
        let default = match self {
            Self::Chat => "/chat/completions",
            Self::Responses => "/responses",
            Self::Anthropic => "/messages",
            Self::Gemini => "",
        };
        let mut address = if self == Self::Gemini && endpoint.is_none() {
            let mut address = reqwest::Url::parse(base)?;
            let model = model["model"]
                .as_str()
                .ok_or("Model ID is required.")?
                .trim_start_matches("models/");
            if model.is_empty() {
                return Err("Model ID is required.".into());
            }
            let version = address
                .path()
                .trim_end_matches('/')
                .rsplit('/')
                .next()
                .unwrap_or("");
            let has_version = version.starts_with('v')
                && version.as_bytes().get(1).is_some_and(u8::is_ascii_digit);
            let mut segments = address
                .path_segments_mut()
                .map_err(|_| "Model URL must support path segments.")?;
            segments.pop_if_empty();
            if !has_version {
                segments.push("v1beta");
            }
            segments.push("models").push(&format!(
                "{model}:{}",
                if stream {
                    "streamGenerateContent"
                } else {
                    "generateContent"
                }
            ));
            drop(segments);
            address
        } else {
            let endpoint = endpoint.unwrap_or(default);
            reqwest::Url::parse(&if endpoint.starts_with("http://")
                || endpoint.starts_with("https://")
            {
                endpoint.to_owned()
            } else if base.ends_with(endpoint) {
                base.to_owned()
            } else {
                format!("{base}/{}", endpoint.trim_start_matches('/'))
            })?
        };
        if !["http", "https"].contains(&address.scheme()) {
            return Err("Model endpoint must use HTTP or HTTPS.".into());
        }
        if self == Self::Gemini && stream {
            address.query_pairs_mut().append_pair("alt", "sse");
        }
        Ok(address)
    }

    pub fn authenticate(
        self,
        mut request: reqwest::RequestBuilder,
        model: &Value,
    ) -> Result<reqwest::RequestBuilder> {
        let (_, key) = crate::models::api_key(model);
        if let Some(key) = key {
            request = match self {
                Self::Anthropic => request.header("x-api-key", key),
                Self::Gemini => request.header("x-goog-api-key", key),
                _ => request.bearer_auth(key),
            };
        }
        if self == Self::Anthropic {
            request = request.header("anthropic-version", "2023-06-01");
        }
        Ok(request)
    }

    pub fn body(
        self,
        model: &Value,
        messages: &[Value],
        tools: &[Value],
        stream: bool,
    ) -> Result<Value> {
        let mut body = match self {
            Self::Chat => {
                let messages: Vec<Value> = messages
                    .iter()
                    .map(|message| {
                        let fields = [
                            "role",
                            "content",
                            "tool_calls",
                            "tool_call_id",
                            "name",
                            "reasoning_content",
                            "audio",
                        ];
                        Value::Object(
                            fields
                                .iter()
                                .filter_map(|key| {
                                    message
                                        .get(*key)
                                        .map(|value| (key.to_string(), value.clone()))
                                })
                                .collect(),
                        )
                    })
                    .collect();
                let mut body = json!({"model":model["model"],"messages":messages,"stream":stream});
                if !tools.is_empty() {
                    body["tools"] = json!(tools);
                    body["tool_choice"] = json!("auto");
                }
                body
            }
            Self::Responses => responses::body(model, messages, tools, stream)?,
            Self::Anthropic => anthropic::body(model, messages, tools, stream)?,
            Self::Gemini => gemini::body(model, messages, tools)?,
        };
        if let Some(extra) = model["extra_body"].as_object() {
            for (key, value) in extra {
                if [
                    "model",
                    "messages",
                    "input",
                    "contents",
                    "system",
                    "systemInstruction",
                    "tools",
                    "stream",
                ]
                .contains(&key.as_str())
                {
                    return Err(format!("Extra model parameters cannot replace {key}.").into());
                }
                body[key] = value.clone();
            }
        }
        if self != Self::Gemini {
            let options: &[&str] = match self {
                Self::Chat => &[
                    "temperature",
                    "top_p",
                    "stop",
                    "seed",
                    "presence_penalty",
                    "frequency_penalty",
                    "reasoning_effort",
                    "thinking",
                    "max_completion_tokens",
                ],
                Self::Responses => &[
                    "temperature",
                    "top_p",
                    "reasoning",
                    "include",
                    "parallel_tool_calls",
                ],
                Self::Anthropic => &[
                    "temperature",
                    "top_p",
                    "top_k",
                    "stop_sequences",
                    "thinking",
                    "output_config",
                    "metadata",
                ],
                Self::Gemini => unreachable!(),
            };
            for key in options {
                if let Some(value) = model.get(*key) {
                    body[*key] = value.clone();
                }
            }
            if self == Self::Responses {
                if body["reasoning"].is_null()
                    && let Some(effort) = model["reasoning_effort"].as_str()
                {
                    body["reasoning"] = json!({"effort":effort});
                }
                if body["include"].is_null() {
                    body["include"] = json!(["reasoning.encrypted_content"]);
                }
            }
            let output = model
                .get("max_output_tokens")
                .or_else(|| model.get("max_tokens"));
            if let Some(output) = output {
                body[if self == Self::Responses {
                    "max_output_tokens"
                } else {
                    "max_tokens"
                }] = output.clone();
            }
            if self == Self::Anthropic && body["max_tokens"].is_null() {
                body["max_tokens"] = json!(16_384);
            }
        }
        Ok(body)
    }
}

pub(super) fn native<'a>(
    message: &'a Value,
    transport: &str,
    model: &Value,
) -> Option<&'a Vec<Value>> {
    let native = &message["provider_content"];
    (native["transport"] == transport && native["model"] == model["model"])
        .then(|| native["content"].as_array())
        .flatten()
}

pub(super) fn content(value: &Value) -> Result<Vec<Value>> {
    if value.is_null() {
        return Ok(Vec::new());
    }
    if let Some(text) = value.as_str() {
        return Ok(if text.is_empty() {
            Vec::new()
        } else {
            vec![json!({"type":"text","text":text})]
        });
    }
    value
        .as_array()
        .cloned()
        .ok_or_else(|| "Message content must be text or a content array.".into())
}

pub(super) fn image_url(block: &Value) -> Result<&str> {
    block["image_url"]["url"]
        .as_str()
        .or_else(|| block["image_url"].as_str())
        .or_else(|| block["image_url"].get("image_url").and_then(Value::as_str))
        .ok_or_else(|| "Image URL is missing.".into())
}
