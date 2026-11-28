use super::*;
use std::collections::BTreeMap;
use std::time::Duration;

pub(crate) async fn fetch(cfg: &Value, proxy: &str) -> crate::Result<Option<Value>> {
    let Some(token) = key(cfg) else {
        return Ok(None);
    };
    if cfg["enabled"] == false {
        return Ok(None);
    }
    let mut client = reqwest::Client::builder().timeout(Duration::from_secs(10));
    if !proxy.trim().is_empty() {
        client = client.proxy(reqwest::Proxy::all(proxy)?);
    }
    let mut response = client
        .build()?
        .get(format!("{}/models", base_url(cfg)))
        .bearer_auth(&token)
        .header("accept", "application/json")
        .send()
        .await
        .map_err(|e| e.without_url())?
        .error_for_status()
        .map_err(|e| e.without_url())?;
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|e| e.without_url())? {
        if bytes.len() + chunk.len() > 16 * 1024 * 1024 {
            return Err("ModelScope catalog response is too large.".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    let models = parse(&serde_json::from_slice(&bytes)?)?;
    let cache_key = inventory_key(&base_url(cfg), &token);
    Ok(Some(json!({"connection_key":cache_key,"models":models})))
}

fn integer(row: &Value, keys: &[&str]) -> Option<u64> {
    keys.iter().find_map(|k| {
        row[*k]
            .as_u64()
            .or_else(|| row[*k].as_str()?.parse().ok())
            .filter(|n| *n > 0)
    })
}

fn flag(row: &Value, names: &[&str]) -> Option<bool> {
    [&row["capabilities"], row]
        .into_iter()
        .find_map(|fields| names.iter().find_map(|name| fields[*name].as_bool()))
}

fn parse(payload: &Value) -> crate::Result<Vec<Value>> {
    let rows = payload
        .as_array()
        .or_else(|| {
            ["data", "models", "results"]
                .iter()
                .find_map(|k| payload[*k].as_array())
        })
        .ok_or("ModelScope response has no model list.")?;
    let mut models = BTreeMap::new();
    for raw in rows {
        let Some(id) = raw
            .as_str()
            .or_else(|| {
                ["id", "model", "name"]
                    .iter()
                    .find_map(|k| raw[*k].as_str().filter(|s| !s.trim().is_empty()))
            })
            .map(str::trim)
            .filter(|s| !s.is_empty())
        else {
            continue;
        };
        if raw["output_modalities"]
            .as_array()
            .is_some_and(|m| !m.is_empty() && !m.iter().any(|v| v == "text"))
        {
            continue;
        }
        let mut row = builtin(id)
            .cloned()
            .unwrap_or_else(|| json!({"id":id,"tool_calling":true}));
        row["id"] = json!(id);
        row["display_name"] = json!(
            raw["display_name"]
                .as_str()
                .or(raw["name"].as_str())
                .filter(|v| !v.trim().is_empty())
                .or(row["display_name"].as_str())
                .unwrap_or(id)
        );
        if let Some(desc) = raw["description"].as_str() {
            row["description"] = json!(desc);
        }
        if let Some(n) = integer(
            raw,
            &[
                "context_length",
                "context_window",
                "max_context_tokens",
                "max_input_tokens",
            ],
        ) {
            row["context_length"] = json!(n);
        }
        if let Some(n) = integer(
            raw,
            &["max_output_tokens", "max_output_length", "max_tokens"],
        ) {
            row["max_output_tokens"] = json!(n);
        }
        if let Some(v) = flag(raw, &["vision", "image", "images"]).or_else(|| {
            [
                &raw["input_modalities"],
                &raw["modalities"],
                &raw["supported_input_modalities"],
                &raw["architecture"]["input_modalities"],
            ]
            .into_iter()
            .filter_map(Value::as_array)
            .find(|m| !m.is_empty())
            .map(|m| {
                m.iter()
                    .any(|v| matches!(v.as_str(), Some("image" | "vision")))
            })
        }) {
            row["vision"] = json!(v);
        }
        if let Some(v) = raw["supported_features"]
            .as_array()
            .map(|m| {
                m.iter()
                    .any(|v| v == "tools" || v == "tool_calling" || v == "function_calling")
            })
            .or_else(|| flag(raw, &["tools", "tool_calling", "function_calling"]))
        {
            row["tool_calling"] = json!(v);
        }
        let thinking = raw["supported_features"]
            .as_array()
            .map(|m| m.iter().any(|v| v == "reasoning" || v == "thinking"))
            .or_else(|| flag(raw, &["reasoning", "thinking"]));
        if let Some(v) = thinking {
            row["thinking"] = json!(v);
            if !v {
                row["thinking_control"] = json!("none");
                row["thinking_options"] = json!([]);
            }
        }
        if thinking != Some(false) {
            if let Some(mode) = raw["thinking_control"]
                .as_str()
                .filter(|m| matches!(*m, "none" | "fixed" | "effort" | "toggle"))
            {
                row["thinking_control"] = json!(mode);
            }
            if let Some(opts) = raw["thinking_options"].as_array() {
                let options = opts
                    .iter()
                    .filter_map(|option| {
                        let id = option["id"].as_str()?;
                        let label = option["label"].as_str().unwrap_or(id);
                        let description = text(option, "description");
                        Some(json!({"id":id, "label":label, "description":description}))
                    })
                    .collect::<Vec<_>>();
                row["thinking_options"] = json!(options);
            }
            if let Some(choice) = raw["default_thinking_choice"].as_str() {
                row["default_thinking_choice"] = json!(choice);
            }
        }
        models.entry(id.to_lowercase()).or_insert(row);
    }
    Ok(models.into_values().collect())
}
