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
    json!({"version":1,"model_ref":{"source":config["active_model_source"].as_str().unwrap_or("standard"),"model":model.and_then(|m|m["model"].as_str()).unwrap_or_default(),"profile_id":model.and_then(|m|m["profile_id"].as_str()).unwrap_or_default()},"settings":settings,"provider_settings":{},"model_settings":{},"rules":"","pinned_skills":config.get("pinned_skills").cloned().unwrap_or_else(||json!([])),"plugins":{}})
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
    let pins = snapshot
        .get("pinned_skills")
        .cloned()
        .unwrap_or_else(|| json!([]));
    if pins
        .as_array()
        .is_none_or(|pins| pins.iter().any(|pin| !pin.is_string()))
    {
        return Err("Conversation skill pins must be an array of names.".into());
    }
    config["pinned_skills"] = pins;
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

pub fn assign_setting(
    settings: &mut Map<String, Value>,
    key: &str,
    value: &Value,
) -> std::io::Result<()> {
    let target = if matches!(key, "permission_mode" | "auto_review_fallback") {
        settings
            .entry("security")
            .or_insert_with(|| json!({}))
            .as_object_mut()
            .ok_or_else(|| std::io::Error::other("Invalid security settings."))?
    } else {
        settings
    };
    target.insert(key.to_owned(), value.clone());
    Ok(())
}

pub fn validate_setting(key: &str, value: &Value) -> Result<()> {
    match key {
        "permission_mode"
            if value
                .as_str()
                .is_some_and(|v| crate::permissions::MODES.contains(&v)) =>
        {
            Ok(())
        }
        "auto_review_fallback"
            if value
                .as_str()
                .is_some_and(|v| crate::permissions::FALLBACKS.contains(&v)) =>
        {
            Ok(())
        }
        "mode"
            if value.as_str().is_some_and(|v| {
                [
                    "reverie",
                    "atlas",
                    "reverie-atlas",
                    "writer",
                    "aio",
                    "gamer",
                    "reverie-gamer",
                ]
                .contains(&v)
            }) =>
        {
            Ok(())
        }
        "stream_responses" | "auto_index" if value.is_boolean() => Ok(()),
        "api_timeout" if value.as_u64().is_some_and(|value| value > 0) => Ok(()),
        "api_max_retries" if value.as_u64().is_some() => Ok(()),
        "api_initial_backoff"
            if value
                .as_f64()
                .is_some_and(|value| value.is_finite() && value >= 0.0) =>
        {
            Ok(())
        }
        "api_proxy" if value.is_string() => Ok(()),
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
    let mut items: Vec<Value> = ["mode","stream_responses","auto_index","max_context_tokens","thinking_output_style","tool_output_style","api_timeout","api_max_retries","api_initial_backoff","api_proxy"].iter().map(|key| {
        let value=config.get(*key).cloned().unwrap_or_else(||match *key {"api_timeout"=>json!(60),"api_max_retries"=>json!(5),"api_initial_backoff"=>json!(1.0),"api_proxy"=>json!(""),_=>Value::Null});
        json!({"name":key,"key":key,"kind":if *key=="api_proxy"{"text"}else if *key=="api_initial_backoff"{"float"}else if value.is_boolean(){"bool"}else if value.is_number(){"int"}else{"choice"},"description":"","value":value,"choices":match *key {"mode"=>json!(["reverie","atlas","writer","aio","gamer"]),"thinking_output_style"=>json!(["hidden","compact","full"]),"tool_output_style"=>json!(["minimal","compact","condensed","full"]),_=>Value::Null}})
    }).collect();
    let security = &config["security"];
    items.extend([
        json!({"name":"Permission mode","key":"permission_mode","kind":"choice","value":crate::permissions::mode(security),"choices":crate::permissions::MODES,"labels":{"strict":"Strict","normal":"Normal","auto":"Auto","full_access":"Full Access"},"description":"Approval policy for model tool calls."}),
        json!({"name":"Auto review fallback","key":"auto_review_fallback","kind":"choice","value":crate::permissions::fallback(security),"choices":crate::permissions::FALLBACKS,"labels":{"wait":"Wait for a human","deny":"Deny and continue"},"description":"Wait for human approval or deny the call while independent work continues."})
    ]);
    json!({"items":items,"config_path":path,"workspace_mode":workspace_mode})
}
