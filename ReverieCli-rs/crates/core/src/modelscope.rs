use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{io, sync::LazyLock};

const DEFAULT_URL: &str = "https://api-inference.modelscope.cn/v1";
const DEFAULT_MODEL: &str = "Qwen/Qwen3.8-27B";
static BUILTIN: LazyLock<Vec<Value>> = LazyLock::new(|| {
    serde_json::from_str(include_str!("../../../resources/modelscope-catalog.json"))
        .expect("built-in ModelScope catalog")
});

fn text<'a>(value: &'a Value, key: &str) -> &'a str {
    value[key].as_str().unwrap_or("").trim()
}

pub(super) fn base_url(cfg: &Value) -> String {
    let value = text(cfg, "api_url").trim_end_matches('/');
    if value.is_empty() {
        return DEFAULT_URL.into();
    }
    let mut base = value;
    for suffix in [
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/messages",
        "/messages",
        "/v1",
    ] {
        if base.to_ascii_lowercase().ends_with(suffix) {
            base = &base[..base.len() - suffix.len()];
        }
    }
    if base.contains("://") {
        format!("{base}/v1")
    } else {
        format!("https://{base}/v1")
    }
}

pub(super) fn key(cfg: &Value) -> Option<String> {
    let (source, value) = crate::models::api_key(cfg);
    if source != "none" {
        return value.map(|s| s.trim().to_owned());
    }
    [
        "MODELSCOPE_API_KEY",
        "MODELSCOPE_TOKEN",
        "MODELSCOPE_ACCESS_TOKEN",
    ]
    .into_iter()
    .find_map(|name| {
        std::env::var(name)
            .ok()
            .map(|s| s.trim().to_owned())
            .filter(|s| !s.is_empty())
    })
}

pub(super) fn connection_key(cfg: &Value) -> String {
    inventory_key(&base_url(cfg), &key(cfg).unwrap_or_default())
}

fn inventory_key(url: &str, token: &str) -> String {
    Sha256::digest(format!("{url}/models\0{token}").as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn builtin(id: &str) -> Option<&'static Value> {
    BUILTIN
        .iter()
        .find(|m| text(m, "id").eq_ignore_ascii_case(id))
}

fn catalog(cfg: &Value) -> (&[Value], bool) {
    let cache = &cfg["model_catalog"];
    if cache
        .get("connection_key")
        .or_else(|| cache.get("key"))
        .and_then(Value::as_str)
        == Some(connection_key(cfg).as_str())
        && let Some(rows) = cache["models"].as_array()
    {
        return (rows, true);
    }
    (&BUILTIN, false)
}

fn selected<'a>(cfg: &Value, rows: &'a [Value], live: bool) -> Option<&'a Value> {
    let wanted = text(cfg, "selected_model_id");
    rows.iter()
        .find(|row| text(row, "id").eq_ignore_ascii_case(wanted))
        .or_else(|| rows.iter().find(|row| live || row["deprecated"] != true))
}

fn reasoning(row: &Value, raw: &str) -> Value {
    let control = row["thinking_control"]
        .as_str()
        .unwrap_or(if row["thinking"] == true {
            "fixed"
        } else {
            "none"
        });
    if matches!(control, "none" | "fixed") {
        let value = if control == "fixed" { "fixed" } else { "" };
        return json!({"control":control,"options":[],"value":value});
    }
    let options = row["thinking_options"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or_default();
    let allows = |id: &str| options.iter().any(|opt| opt["id"] == id);
    let value = raw.trim().to_ascii_lowercase().replace('-', "_");
    let value = match value.as_str() {
        "max" | "high" | "extra_high" if allows("xhigh") => "xhigh",
        "on" | "enabled" | "enable" | "high" | "max" if allows("true") => "true",
        "off" | "disabled" | "disable" | "none" if allows("false") => "false",
        "off" | "non_think" => "none",
        "nothink" => "no_think",
        "med" => "medium",
        "extra_high" | "xhigh" if !allows("xhigh") => "max",
        v => v,
    };
    let value = if allows(value) {
        value
    } else if allows(text(row, "default_thinking_choice")) {
        text(row, "default_thinking_choice")
    } else {
        options.first().and_then(|o| o["id"].as_str()).unwrap_or("")
    };
    json!({"control":control,"options":options,"value":value})
}

fn public_row(row: &Value, choice: &str) -> Value {
    let id = text(row, "id");
    json!({"id":id,"display_name":row["display_name"].as_str().unwrap_or(id),"description":text(row,"description"),"transport":"openai-chat",
        "context_length":row["context_length"],"max_output_tokens":row["max_output_tokens"],"vision":row["vision"]==true,
        "tool_calling":row["tool_calling"]!=false,"thinking":row["thinking"]==true,"reasoning":reasoning(row,choice),"deprecated":row["deprecated"]==true})
}

pub(super) fn source(config: &Value) -> Value {
    let cfg = &config["modelscope"];
    let (rows, live) = catalog(cfg);
    let selected = selected(cfg, rows, live);
    let id = selected.map(|row| text(row, "id")).unwrap_or("");
    let choice = text(cfg, "reasoning_effort");
    let models: Vec<_> = rows
        .iter()
        .filter(|row| live || row["deprecated"] != true || text(row, "id") == id)
        .map(|row| public_row(row, if text(row, "id") == id { choice } else { "" }))
        .collect();
    json!({"id":"modelscope","display_name":"ModelScope","active":config["active_model_source"]=="modelscope",
        "selected_model_id":id,"selected_reasoning":selected.map(|row|reasoning(row,choice)).unwrap_or_else(||json!({"control":"none","options":[],"value":""})),
        "models":models,"catalog_live":live,"config_fields":[
            {"key":"api_key","label":"API key","kind":"secret"},{"key":"api_key_env","label":"API key environment variable","kind":"text"},
            {"key":"api_url","label":"API URL","kind":"url"},{"key":"timeout","label":"Timeout (seconds)","kind":"int","min":10,"max":3600}],
        "config":{"values":{"api_key_env":text(cfg,"api_key_env"),"api_url":base_url(cfg),"timeout":positive(cfg,"timeout",300)},
            "configured_secrets":{"api_key":!text(cfg,"api_key").is_empty()}}})
}

pub(super) fn choose(cfg: &mut Value, id: &str, choice: Option<&str>) -> io::Result<()> {
    let (rows, _) = catalog(cfg);
    let row = rows
        .iter()
        .find(|m| text(m, "id").eq_ignore_ascii_case(id))
        .ok_or_else(|| io::Error::other("ModelScope model not found in the current catalog."))?;
    let id = row["id"].clone();
    let display = json!(row["display_name"].as_str().unwrap_or(text(row, "id")));
    let effort =
        reasoning(row, choice.unwrap_or_else(|| text(cfg, "reasoning_effort")))["value"].clone();
    cfg["selected_model_id"] = id;
    cfg["selected_model_display_name"] = display;
    cfg["reasoning_effort"] = effort;
    Ok(())
}

pub(super) fn reference(cfg: &Value) -> Value {
    let (rows, live) = catalog(cfg);
    let id = selected(cfg, rows, live)
        .map(|m| text(m, "id"))
        .unwrap_or("");
    json!({"source":"modelscope","model":id,"profile_id":""})
}

pub(super) fn session_settings(cfg: &Value) -> Value {
    let (rows, live) = catalog(cfg);
    let effort = selected(cfg, rows, live)
        .map(|row| reasoning(row, text(cfg, "reasoning_effort"))["value"].clone())
        .unwrap_or_else(|| json!(""));
    json!({"reasoning_effort":effort,"timeout":positive(cfg,"timeout",300),
        "max_tokens":positive(cfg,"max_tokens",16384)})
}

fn positive(cfg: &Value, name: &str, default: u64) -> u64 {
    cfg[name]
        .as_u64()
        .or_else(|| cfg[name].as_str()?.trim().parse().ok())
        .filter(|n| *n > 0)
        .unwrap_or(default)
}

pub(super) fn apply_session_settings(cfg: &mut Value, settings: &Value) {
    for name in ["reasoning_effort", "max_tokens", "timeout"] {
        if let Some(value) = settings.get(name) {
            cfg[name] = value.clone();
        }
    }
}

pub(super) fn runtime(cfg: &Value) -> Option<Value> {
    if cfg["enabled"] == false {
        return None;
    }
    let (rows, live) = catalog(cfg);
    let row = selected(cfg, rows, live)?;
    let id = text(row, "id");
    let choice = reasoning(row, text(cfg, "reasoning_effort"));
    let effort = text(&choice, "value");
    let cap = row["max_output_tokens"]
        .as_u64()
        .filter(|n| *n > 0)
        .unwrap_or(16384);
    let max = positive(cfg, "max_tokens", 16384).min(cap);
    let mut model = json!({"model":id,"model_display_name":row["display_name"].as_str().unwrap_or(id),"provider":"openai-chat","base_url":base_url(cfg),
        "api_key":key(cfg)?,"max_tokens":max,"request_timeout":positive(cfg,"timeout",300),
        "max_context_tokens":row["context_length"].as_u64().unwrap_or_else(||positive(cfg,"max_context_tokens",262144)),"supports_vision":row["vision"]==true,"tool_calling":row["tool_calling"]!=false,
        "temperature":1.0,"top_p":1.0});
    if matches!(choice["control"].as_str(), Some("none" | "fixed")) {
        return Some(model);
    }
    let kwargs = match builtin(id).map(|row| text(row, "id")).unwrap_or(id) {
        DEFAULT_MODEL => {
            model["top_p"] = json!(0.95);
            if effort != "none" {
                model["reasoning_effort"] = json!(effort);
            }
            json!({"enable_thinking":effort!="none"})
        }
        "stepfun-ai/Step-3.7-Flash" => {
            model["top_p"] = json!(0.95);
            json!({"reasoning_effort":effort})
        }
        "ZhipuAI/GLM-5.2" | "ZhipuAI/GLM-5.3" | "ZhipuAI/GLM-5.3-Flash" => {
            if effort == "none" {
                json!({"enable_thinking":false})
            } else {
                json!({"enable_thinking":true,"reasoning_effort":effort})
            }
        }
        _ if choice["control"] == "effort" && !effort.is_empty() => {
            json!({"reasoning_effort":effort})
        }
        _ if choice["control"] == "toggle" => json!({"reasoning_effort":effort=="true"}),
        _ => Value::Null,
    };
    if !kwargs.is_null() {
        model["extra_body"] = json!({"chat_template_kwargs":kwargs});
    }
    Some(model)
}

pub(super) fn unavailable(cfg: &Value) -> &'static str {
    if cfg["enabled"] == false {
        "ModelScope is disabled in the provider configuration."
    } else if key(cfg).is_none() {
        "Configure a ModelScope API key or its environment variable before running a prompt."
    } else {
        "The current ModelScope catalog has no available model."
    }
}

pub(super) fn patch(cfg: &mut Value, payload: &Value) -> io::Result<()> {
    let mut fields = payload["patch"]
        .as_object()
        .cloned()
        .ok_or_else(|| io::Error::other("Provider patch must be an object."))?;
    crate::models::normalize_key_edit(&mut fields)?;
    for (name, value) in &fields {
        match name.as_str() {
            "api_key" | "api_key_env" if value.is_string() => {}
            "timeout" if value.as_u64().is_some_and(|n| (10..=3600).contains(&n)) => {}
            "api_url" if value.is_string() => {
                let url = reqwest::Url::parse(&base_url(&json!({"api_url":value})))
                    .map_err(|_| io::Error::other("Invalid ModelScope API URL."))?;
                if !matches!(url.scheme(), "http" | "https")
                    || url.host().is_none()
                    || !url.username().is_empty()
                    || url.password().is_some()
                    || url.fragment().is_some()
                    || url.query().is_some()
                {
                    return Err(io::Error::other("Invalid ModelScope API URL."));
                }
            }
            _ => {
                return Err(io::Error::other(format!(
                    "Invalid ModelScope setting: {name}"
                )));
            }
        }
    }
    if let Some(cleared) = payload["clearFields"].as_array() {
        for field in cleared {
            if field != "api_key" {
                return Err(io::Error::other("Unknown secret field."));
            }
            cfg["api_key"] = json!("");
        }
    }
    if cfg.is_null() {
        *cfg = json!({});
    }
    cfg.as_object_mut()
        .ok_or_else(|| io::Error::other("Invalid ModelScope configuration."))?
        .extend(fields);
    Ok(())
}

mod inventory;
pub(super) use inventory::fetch;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{approval_review as review, models};

    #[test]
    fn session_selection_freezes_limits_without_copying_credentials_or_connections() {
        let mut config = json!({"active_model_source":"modelscope","modelscope":{"api_key":"fixture","api_url":"localhost:1234/v1/messages"}});
        let snapshot = models::capture(&config);
        assert_eq!(
            snapshot["provider_settings"],
            json!({"reasoning_effort":"xhigh","max_tokens":16384,"timeout":300})
        );
        assert!(!snapshot.to_string().contains("fixture"));
        config["modelscope"] = json!({"api_key":"replacement","api_url":"http://localhost:8242/v1/chat/completions/","max_tokens":"256","timeout":22});
        let restored = models::resolve(&config, &snapshot).unwrap();
        let row = models::active(&restored).unwrap();
        assert_eq!(row["max_tokens"], 16384);
        assert_eq!(row["request_timeout"], 300);
        assert_eq!(row["api_key"], "replacement");
        assert_eq!(row["base_url"], "http://localhost:8242/v1");
        assert_eq!(models::active(&config).unwrap()["max_tokens"], 256);
    }

    #[test]
    fn pinned_reviewer_resolves_its_own_model_specific_parameters() {
        let config = json!({"active_model_source":"standard","modelscope":{"api_key":"test","max_tokens":600}});
        let main = json!({"model":"standard-fixture"});
        let review = review::ReviewConfig::from_review(
            &json!({"source":"modelscope","model":"ZhipuAI/GLM-5.3"}),
        );
        let selected = review::select_model(&config, &main, &review, None);
        assert!(selected.note.is_empty());
        let model = selected.request_model(&review).unwrap();
        assert_eq!(model["model"], "ZhipuAI/GLM-5.3");
        assert_eq!(
            model["extra_body"]["chat_template_kwargs"],
            json!({"enable_thinking":true,"reasoning_effort":"max"})
        );
        assert_eq!(model["max_tokens"], 600);
    }
}
