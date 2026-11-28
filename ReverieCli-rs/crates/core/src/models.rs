use crate::Result;
use serde_json::{Map, Value, json};
use std::{env, io, sync::LazyLock};

static ENV_NAME: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"^[A-Za-z_][A-Za-z0-9_]*$").unwrap());

pub fn api_key_environment_names() -> Vec<String> {
    let mut names: Vec<_> = env::vars_os()
        .filter_map(|(name, value)| {
            let name = name.into_string().ok()?;
            let upper = name.to_ascii_uppercase();
            (ENV_NAME.is_match(&name)
                && ["KEY", "TOKEN", "SECRET"]
                    .iter()
                    .any(|part| upper.contains(part))
                && !value.to_str()?.trim().is_empty())
            .then_some(name)
        })
        .collect();
    names.sort_unstable();
    names
}

pub fn normalize_key_edit(model: &mut Map<String, Value>) -> io::Result<()> {
    if let Some(value) = model.get_mut("api_key_env") {
        let name = match value {
            Value::Null => "",
            Value::String(name) => name.trim(),
            _ => {
                return Err(io::Error::other(
                    "API key environment variable must be a name.",
                ));
            }
        };
        if !name.is_empty() && !ENV_NAME.is_match(name) {
            return Err(io::Error::other(
                "Invalid API key environment variable name.",
            ));
        }
        *value = json!(name);
    }
    if model
        .get("api_key_env")
        .and_then(Value::as_str)
        .is_some_and(|name| !name.is_empty())
    {
        model.insert("api_key".into(), json!(""));
    } else if let Some(key) = model.get("api_key") {
        if key.as_str().is_some_and(|key| !key.trim().is_empty()) {
            model.insert("api_key_env".into(), json!(""));
        } else {
            // Desktop edits leave masked keys blank. An explicit clearFields removes the key.
            model.remove("api_key");
        }
    }
    Ok(())
}

pub fn api_key(model: &Value) -> (&'static str, Option<String>) {
    if let Some(literal) = model["api_key"]
        .as_str()
        .map(str::trim)
        .filter(|s| !s.is_empty())
    {
        return ("config", Some(literal.to_owned()));
    }
    let Some(name) = model["api_key_env"].as_str().filter(|s| !s.is_empty()) else {
        return ("none", None);
    };
    let key = env::var(name).ok().filter(|s| !s.trim().is_empty());
    ("env", key)
}

const SETTINGS: &[&str] = &[
    "mode",
    "browser_profile",
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

// Match Python ModelConfig.from_dict's UUIDv5 for inventories predating profile_id.
// Python's json.dumps uses ", " and escapes non-ASCII characters as UTF-16.
pub(crate) fn fill_profile_ids(items: &mut [Value]) {
    for model in items {
        if !model.is_object()
            || model["profile_id"]
                .as_str()
                .is_some_and(|id| !id.is_empty())
        {
            continue;
        }
        let parts = [
            "provider",
            "base_url",
            "endpoint",
            "model",
            "model_display_name",
        ]
        .map(|key| model[key].to_string());
        let mut name = String::new();
        for ch in format!("[{}]", parts.join(", ")).chars() {
            if ch < '\u{7f}' {
                name.push(ch);
            } else {
                for unit in ch.encode_utf16(&mut [0; 2]) {
                    use std::fmt::Write;
                    write!(name, "\\u{unit:04x}").unwrap();
                }
            }
        }
        model["profile_id"] = json!(
            uuid::Uuid::new_v5(&uuid::Uuid::NAMESPACE_URL, name.as_bytes())
                .simple()
                .to_string()
        );
    }
}

pub(crate) fn profile_index(items: &[Value], id: &Value) -> io::Result<usize> {
    let id = id
        .as_str()
        .filter(|id| !id.is_empty())
        .ok_or_else(|| io::Error::other("Invalid model profile id."))?;
    let mut matches = items
        .iter()
        .enumerate()
        .filter(|(_, model)| model["profile_id"] == id);
    let (index, _) = matches
        .next()
        .ok_or_else(|| io::Error::other("Model profile not found."))?;
    if matches.next().is_some() {
        return Err(io::Error::other("Ambiguous model profile id."));
    }
    Ok(index)
}

pub(crate) fn edit_index(items: &[Value], payload: &Value) -> io::Result<usize> {
    if let Some(id) = payload.get("profileId") {
        return profile_index(items, id);
    }
    payload["index"]
        .as_u64()
        .and_then(|i| usize::try_from(i).ok())
        .filter(|i| *i < items.len())
        .ok_or_else(|| io::Error::other("Missing or out-of-range model index."))
}

pub(crate) fn selection_index(items: &[Value], name: &str, profile: &Value) -> io::Result<usize> {
    if !profile.is_null() {
        let index = profile_index(items, profile)?;
        if items[index]["model"] == name {
            return Ok(index);
        }
    } else if let Some(index) = items.iter().position(|m| m["model"] == name) {
        return Ok(index);
    }
    Err(io::Error::other("Model not found."))
}

pub fn active_summary(config: &Value) -> Value {
    active(config).map(|model| json!({"id":model["model"],"profile_id":model["profile_id"],"display_name":model.get("model_display_name").unwrap_or(&model["model"]),"provider":model.get("provider").and_then(Value::as_str).unwrap_or("openai-chat")})).unwrap_or(Value::Null)
}

pub fn sources(config: &Value) -> Value {
    let models: Vec<Value> = config["models"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|model| {
            let mut safe = without_secrets(model);
            safe["id"] = model["model"].clone();
            safe["context_length"] = model["max_context_tokens"].clone();
            safe["display_name"] = model
                .get("model_display_name")
                .unwrap_or(&model["model"])
                .clone();
            safe["description"] = json!(model["description"].as_str().unwrap_or_default());
            safe["transport"] = json!(model["provider"].as_str().unwrap_or("openai-chat"));
            safe["vision"] = json!(model["supports_vision"].as_bool().unwrap_or(false));
            safe["tool_calling"] = json!(true);
            safe["thinking"] = json!(false);
            let (source, key) = api_key(model);
            safe["api_key_configured"] = json!(key.is_some());
            safe["api_key_source"] = json!(source);
            safe["reasoning"] = json!({"control":"none","options":[],"value":""});
            safe
        })
        .collect();
    let active = active_summary(config);
    json!({"active_source":config["active_model_source"].as_str().unwrap_or("standard"),"active_model":active,"sources":[{"id":"standard","display_name":"Manual Model","active":config["active_model_source"].as_str().unwrap_or("standard")=="standard","selected_model_id":active["id"],"selected_profile_id":active["profile_id"],"selected_reasoning":{"control":"none","options":[],"value":""},"models":models,"config_fields":[],"catalog_live":false}]})
}

pub fn capture(config: &Value) -> Value {
    let model = active(config);
    let mut settings = Map::from_iter(SETTINGS.iter().filter_map(|key| {
        config
            .get(*key)
            .map(|value| (key.to_string(), without_secrets(value)))
    }));
    settings
        .entry("browser_profile")
        .or_insert_with(|| json!("persistent"));
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
                let same = match reference["profile_id"].as_str().filter(|id| !id.is_empty()) {
                    Some(id) => item["profile_id"] == id,
                    None => item["model"] == model,
                };
                same.then_some(index)
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
        "browser_profile" if matches!(value.as_str(), Some("persistent" | "ephemeral")) => Ok(()),
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
        json!({"name":"Browser profile","key":"browser_profile","kind":"choice","value":config["browser_profile"].as_str().unwrap_or("persistent"),"choices":["persistent","ephemeral"],"labels":{"persistent":"Dedicated persistent profile","ephemeral":"Temporary run profile"},"description":"Storage for Chrome in Reverie."}),
        json!({"name":"Permission mode","key":"permission_mode","kind":"choice","value":crate::permissions::mode(security),"choices":crate::permissions::MODES,"labels":{"strict":"Strict","normal":"Normal","auto":"Auto","full_access":"Full Access"},"description":"Approval policy for model tool calls."}),
        json!({"name":"Auto review fallback","key":"auto_review_fallback","kind":"choice","value":crate::permissions::fallback(security),"choices":crate::permissions::FALLBACKS,"labels":{"wait":"Wait for a human","deny":"Deny and continue"},"description":"Wait for human approval or deny the call while independent work continues."})
    ]);
    json!({"items":items,"config_path":path,"workspace_mode":workspace_mode})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_profile_identity_matches_python_and_survives_edits() {
        let mut rows = [
            json!({"provider":"openai-chat","base_url":"http://localhost/v1","model":"same","model_display_name":"中文😀"}),
        ];
        fill_profile_ids(&mut rows);
        let expected = "28da62b68cf25fbf933ad8dad118d54e";
        assert_eq!(rows[0]["profile_id"], expected);
        rows[0]["model_display_name"] = json!("edited");
        fill_profile_ids(&mut rows);
        assert_eq!(rows[0]["profile_id"], expected);
    }

    #[test]
    fn explicit_profile_never_falls_back_to_a_name_or_index() {
        let mut rows = [
            json!({"model":"same","profile_id":"a"}),
            json!({"model":"same","profile_id":"b"}),
        ];
        assert_eq!(selection_index(&rows, "same", &json!("b")).unwrap(), 1);
        assert_eq!(
            edit_index(&rows, &json!({"index":0,"profileId":"b"})).unwrap(),
            1
        );
        assert!(edit_index(&rows, &json!({"index":0,"profileId":"gone"})).is_err());
        assert_eq!(edit_index(&rows, &json!({"index":0})).unwrap(), 0);
        rows[0]["profile_id"] = json!("b");
        assert!(selection_index(&rows, "same", &json!("b")).is_err());
        assert!(edit_index(&rows, &json!({"index":0,"profileId":"b"})).is_err());
    }
}
