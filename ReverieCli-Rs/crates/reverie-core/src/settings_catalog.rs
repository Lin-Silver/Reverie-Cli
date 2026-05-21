use crate::config::{normalize_thinking_output_style, normalize_tool_output_style, Config};
use crate::modes::normalize_mode;
use crate::{ReverieError, ReverieResult};
use serde::Serialize;
use serde_json::Value;

#[derive(Debug, Clone, Serialize)]
pub struct SettingItem {
    pub id: &'static str,
    pub label: &'static str,
    pub kind: &'static str,
    pub description: &'static str,
    pub options: &'static [&'static str],
}

pub const SETTINGS: &[SettingItem] = &[
    SettingItem {
        id: "mode",
        label: "Mode",
        kind: "choice",
        description: "Default operating mode.",
        options: &[
            "reverie",
            "reverie-atlas",
            "reverie-gamer",
            "reverie-ant",
            "spec-driven",
            "spec-vibe",
            "writer",
        ],
    },
    SettingItem {
        id: "model",
        label: "Model",
        kind: "model",
        description: "Active standard model preset.",
        options: &[],
    },
    SettingItem {
        id: "theme",
        label: "Theme",
        kind: "choice",
        description: "Terminal display theme.",
        options: &["dreamscape", "light", "dark"],
    },
    SettingItem {
        id: "auto_index",
        label: "Auto Index",
        kind: "bool",
        description: "Index workspace automatically on startup.",
        options: &[],
    },
    SettingItem {
        id: "show_status_line",
        label: "Status Line",
        kind: "bool",
        description: "Show terminal status line.",
        options: &[],
    },
    SettingItem {
        id: "stream_responses",
        label: "Stream Responses",
        kind: "bool",
        description: "Stream model output as it arrives.",
        options: &[],
    },
    SettingItem {
        id: "tool_output_style",
        label: "Tool Output",
        kind: "choice",
        description: "How much tool output to render.",
        options: &["compact", "full", "hidden"],
    },
    SettingItem {
        id: "thinking_output_style",
        label: "Thinking Output",
        kind: "choice",
        description: "How much reasoning text to render.",
        options: &["full", "summary", "hidden"],
    },
    SettingItem {
        id: "api_timeout",
        label: "API Timeout",
        kind: "int",
        description: "Model API timeout in seconds.",
        options: &[],
    },
    SettingItem {
        id: "api_max_retries",
        label: "API Retries",
        kind: "int",
        description: "Maximum API retry count.",
        options: &[],
    },
    SettingItem {
        id: "workspace",
        label: "Workspace Config",
        kind: "bool",
        description: "Use workspace-local configuration.",
        options: &[],
    },
];

pub fn setting_items() -> &'static [SettingItem] {
    SETTINGS
}

pub fn parse_bool(value: &Value) -> ReverieResult<bool> {
    if let Some(value) = value.as_bool() {
        return Ok(value);
    }
    match value
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "1" | "true" | "yes" | "on" | "enable" | "enabled" => Ok(true),
        "0" | "false" | "no" | "off" | "disable" | "disabled" => Ok(false),
        _ => Err(ReverieError::InvalidInput(format!(
            "invalid boolean setting value: {value}"
        ))),
    }
}

pub fn apply_setting(config: &mut Config, id: &str, value: Value) -> ReverieResult<()> {
    match id.trim().to_ascii_lowercase().as_str() {
        "mode" => {
            config.active_mode = normalize_mode(value.as_str().unwrap_or_default())
                .canonical()
                .to_string();
        }
        "model" => {
            config.active_model = value.as_str().map(str::to_string);
        }
        "auto_index" => config.auto_index = parse_bool(&value)?,
        "show_status_line" => config.show_status_line = parse_bool(&value)?,
        "stream_responses" => config.stream_responses = parse_bool(&value)?,
        "tool_output_style" => {
            config.tool_output_style =
                normalize_tool_output_style(value.as_str().unwrap_or_default());
        }
        "thinking_output_style" => {
            config.thinking_output_style =
                normalize_thinking_output_style(value.as_str().unwrap_or_default());
        }
        "api_timeout" => {
            config.api_timeout = value
                .as_u64()
                .or_else(|| value.as_str()?.parse::<u64>().ok())
                .ok_or_else(|| {
                    ReverieError::InvalidInput("api_timeout must be an integer".to_string())
                })?
                .clamp(10, 3600);
        }
        "api_max_retries" => {
            config.api_max_retries = value
                .as_u64()
                .or_else(|| value.as_str()?.parse::<u64>().ok())
                .ok_or_else(|| {
                    ReverieError::InvalidInput("api_max_retries must be an integer".to_string())
                })?
                .min(12) as u8;
        }
        "workspace" => config.use_workspace_config = parse_bool(&value)?,
        other => {
            return Err(ReverieError::InvalidInput(format!(
                "unknown setting: {other}"
            )))
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn applies_mode_alias() {
        let mut config = Config::default();
        apply_setting(&mut config, "mode", Value::String("gamer".to_string())).unwrap();
        assert_eq!(config.active_mode, "reverie-gamer");
    }
}
