use crate::Result;
use serde_json::{Map, Value, json};

const SETTINGS: &[&str] = &[
    "mode",
    "max_context_tokens",
    "stream_responses",
    "auto_index",
    "thinking_output_style",
    "tool_output_style",
    "thinking_tool",
    "api_compatibility",
    "api_timeout",
    "api_max_retries",
    "api_initial_backoff",
    "api_proxy",
    "security",
    "writer_mode",
    "gamer_mode",
    "atlas_mode",
    "text_to_image",
    "text_to_video",
    "subagents",
];

pub fn without_secrets(value: &Value) -> Value {
    match value {
        Value::Object(fields) => Value::Object(
            fields
                .iter()
                .filter(|(key, _)| {
                    !matches!(
                        key.to_ascii_lowercase().as_str(),
                        "api_key"
                            | "custom_headers"
                            | "authorization"
                            | "password"
                            | "token"
                            | "access_token"
                            | "refresh_token"
                            | "cookie"
                    )
                })
                .map(|(key, value)| {
                    if key.eq_ignore_ascii_case("api_proxy")
                        && let Some((scheme, authority)) =
                            value.as_str().and_then(|s| s.split_once("://"))
                        && let Some((_, address)) = authority.rsplit_once('@')
                    {
                        return (key.clone(), json!(format!("{scheme}://{address}")));
                    }
                    (key.clone(), without_secrets(value))
                })
                .collect(),
        ),
        Value::Array(items) => json!(items.iter().map(without_secrets).collect::<Vec<_>>()),
        _ => value.clone(),
    }
}

pub fn active(config: &Value) -> Option<&Value> {
    if config["active_model_source"].as_str().unwrap_or("standard") != "standard" {
        return None;
    }
    config["models"]
        .as_array()?
        .get(config["active_model_index"].as_u64().unwrap_or(0) as usize)
}

pub fn active_summary(config: &Value) -> Value {
    active(config).map(|model| json!({"id":model["model"],"display_name":model.get("model_display_name").unwrap_or(&model["model"]),"provider":model.get("provider").and_then(Value::as_str).unwrap_or("openai-chat")})).unwrap_or(Value::Null)
}

pub fn sources(config: &Value) -> Value {
    let models: Vec<Value> = config["models"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|model| {
            let key = model["api_key"]
                .as_str()
                .filter(|s| !s.is_empty())
                .map(str::to_owned)
                .or_else(|| {
                    model["api_key_env"]
                        .as_str()
                        .and_then(|key| std::env::var(key).ok())
                });
            let mut safe = without_secrets(model);
            safe["id"] = model["model"].clone();
            safe["display_name"] = model
                .get("model_display_name")
                .unwrap_or(&model["model"])
                .clone();
            safe["description"] = json!(model["description"].as_str().unwrap_or_default());
            safe["transport"] = json!(model["provider"].as_str().unwrap_or("openai-chat"));
            safe["vision"] = json!(model["supports_vision"].as_bool().unwrap_or(false));
            safe["tool_calling"] = json!(true);
            safe["thinking"] = json!(false);
            safe["api_key_configured"] = json!(key.is_some_and(|key| !key.is_empty()));
            safe["reasoning"] = json!({"control":"none","options":[],"value":""});
            safe
        })
        .collect();
    let active = active_summary(config);
    json!({"active_source":config["active_model_source"].as_str().unwrap_or("standard"),"active_model":active,"sources":[{"id":"standard","display_name":"Manual Model","active":config["active_model_source"].as_str().unwrap_or("standard")=="standard","selected_model_id":active["id"],"selected_reasoning":{"control":"none","options":[],"value":""},"models":models,"config_fields":[],"catalog_live":false}]})
}

pub fn capture(config: &Value) -> Value {
    let model = active(config);
    let settings = Map::from_iter(SETTINGS.iter().filter_map(|key| {
        config
            .get(*key)
            .map(|value| (key.to_string(), without_secrets(value)))
    }));
    json!({"version":1,"model_ref":{"source":config["active_model_source"].as_str().unwrap_or("standard"),"model":model.and_then(|m|m["model"].as_str()).unwrap_or_default(),"profile_id":model.and_then(|m|m["profile_id"].as_str()).unwrap_or_default()},"settings":settings,"provider_settings":{},"model_settings":{},"rules":"","pinned_skills":[],"plugins":{}})
}

pub fn resolve(defaults: &Value, snapshot: &Value) -> Result<Value> {
    if snapshot["version"] != 1 || !snapshot["settings"].is_object() {
        return Err("Invalid conversation configuration.".into());
    }
    let source = snapshot["model_ref"]["source"]
        .as_str()
        .unwrap_or("standard");
    if source != "standard" {
        return Err(format!("Provider source {source} has not yet been migrated.").into());
    }
    let mut config = defaults.clone();
    config["active_model_source"] = json!(source);
    let reference = &snapshot["model_ref"];
    if let Some(model) = reference["model"].as_str().filter(|s| !s.is_empty()) {
        let matches: Vec<usize> = config["models"]
            .as_array()
            .ok_or("Model inventory is missing.")?
            .iter()
            .enumerate()
            .filter_map(|(index, item)| {
                (item["model"] == model
                    && (reference["profile_id"]
                        .as_str()
                        .unwrap_or_default()
                        .is_empty()
                        || item["profile_id"] == reference["profile_id"]))
                    .then_some(index)
            })
            .collect();
        if matches.len() != 1 {
            return Err("Saved conversation model profile is unavailable or ambiguous.".into());
        }
        config["active_model_index"] = json!(matches[0]);
    }
    for key in SETTINGS {
        if let Some(value) = snapshot["settings"].get(*key) {
            config[*key] = value.clone();
        }
    }
    Ok(config)
}

pub fn validate_setting(key: &str, value: &Value) -> Result<()> {
    match key {
        "mode"
            if value
                .as_str()
                .is_some_and(|v| ["reverie", "atlas", "writer", "aio", "gamer"].contains(&v)) =>
        {
            Ok(())
        }
        "stream_responses" | "auto_index" if value.is_boolean() => Ok(()),
        "max_context_tokens" if value.as_u64().is_some_and(|v| v > 0) => Ok(()),
        "thinking_output_style"
            if value
                .as_str()
                .is_some_and(|v| ["hidden", "compact", "full"].contains(&v)) =>
        {
            Ok(())
        }
        "tool_output_style"
            if value
                .as_str()
                .is_some_and(|v| ["minimal", "compact", "condensed", "full"].contains(&v)) =>
        {
            Ok(())
        }
        _ => Err(format!("Invalid or not yet migrated setting: {key}").into()),
    }
}

pub fn settings(config: &Value, path: &std::path::Path, workspace_mode: bool) -> Value {
    let items: Vec<Value> = ["mode","stream_responses","auto_index","max_context_tokens","thinking_output_style","tool_output_style"].iter().map(|key| json!({"name":key,"key":key,"kind":if config[*key].is_boolean(){"bool"}else if config[*key].is_number(){"int"}else{"choice"},"description":"","value":config[*key],"choices":if *key=="mode" {json!(["reverie","atlas","writer","aio","gamer"])}else{Value::Null}})).collect();
    json!({"items":items,"config_path":path,"workspace_mode":workspace_mode})
}
