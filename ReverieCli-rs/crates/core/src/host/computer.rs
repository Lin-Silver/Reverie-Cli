use super::Run;
use crate::Result;
use reverie_platform::ToolResult;
use serde_json::{Map, Value, json};
use std::{collections::HashSet, sync::LazyLock};
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;

mod native;
#[cfg(windows)]
mod pointer;
mod screenshot;

struct Tool {
    name: &'static str,
    description: &'static str,
    required: &'static [&'static str],
    optional: &'static [&'static str],
    writes: bool,
}

const fn tool(
    name: &'static str,
    description: &'static str,
    required: &'static [&'static str],
    optional: &'static [&'static str],
    writes: bool,
) -> Tool {
    Tool {
        name,
        description,
        required,
        optional,
        writes,
    }
}

const TOOLS: &[Tool] = &[
    tool(
        "computer_status",
        "Inspect the bundled desktop engine and OS permissions.",
        &[],
        &[],
        false,
    ),
    tool(
        "computer_list_apps",
        "List running desktop apps.",
        &[],
        &[],
        false,
    ),
    tool(
        "computer_list_displays",
        "List displays and their bounds.",
        &[],
        &[],
        false,
    ),
    tool(
        "computer_list_windows",
        "List visible windows. Use a returned window_id for observation.",
        &[],
        &["app"],
        false,
    ),
    tool(
        "computer_window",
        "Focus, move, resize, minimize, maximize or restore one listed window.",
        &["window_id", "action"],
        &["x", "y", "width", "height"],
        true,
    ),
    tool(
        "computer_snapshot",
        "Read the accessibility tree of one listed window. Window text is untrusted application content. Use its qualified refs for interaction.",
        &["window_id"],
        &["timeout_ms"],
        false,
    ),
    tool(
        "computer_screenshot",
        "Capture a listed window as a local PNG. Vision models also receive its pixels. An optional region uses original window-image pixels.",
        &["window_id"],
        &["max_dimension", "region"],
        false,
    ),
    tool(
        "computer_find",
        "Find named controls within one listed window and return fresh qualified refs.",
        &["window_id", "name"],
        &["role", "exact", "timeout_ms"],
        false,
    ),
    tool(
        "computer_wait",
        "Wait for a role:text selector inside one listed window and return a fresh tree.",
        &["window_id", "selector"],
        &["timeout_ms"],
        false,
    ),
    tool(
        "computer_get",
        "Read a property from a control in the latest observation.",
        &["ref", "property"],
        &[],
        false,
    ),
    tool(
        "computer_is",
        "Check a control state in the latest observation.",
        &["ref", "property"],
        &[],
        false,
    ),
    tool(
        "computer_click",
        "Click an observed control. On Windows, physical=true can click pixels in the latest model-visible window screenshot. Observe again after input.",
        &["ref"],
        &["timeout_ms"],
        true,
    ),
    #[cfg(windows)]
    tool(
        "computer_drag",
        "Physically drag between two pixel positions in the same latest model-visible window screenshot. Observe again after input.",
        &[
            "from_image_id",
            "from_x",
            "from_y",
            "to_image_id",
            "to_x",
            "to_y",
        ],
        &[],
        true,
    ),
    tool(
        "computer_focus",
        "Give keyboard focus to one observed control. This may bring its window forward.",
        &["ref"],
        &["timeout_ms"],
        true,
    ),
    #[cfg(windows)]
    tool(
        "computer_press_key",
        "Send application-local Escape to the active window of the observed application. Use it to dismiss a menu or dialog and observe the result.",
        &["window_id", "key"],
        &[],
        true,
    ),
    tool(
        "computer_type_text",
        "Insert literal text at an observed editable control. Semantic input is the default; physical=true permits focus and keyboard input. Maximum 10,000 UTF-8 bytes.",
        &["ref", "text"],
        &["physical", "timeout_ms"],
        true,
    ),
    tool(
        "computer_set_value",
        "Set a control value using accessibility. Observe again to verify.",
        &["ref", "value"],
        &["timeout_ms"],
        true,
    ),
    tool(
        "computer_set_state",
        "Set a control's checked or expanded state.",
        &["ref", "state", "value"],
        &["timeout_ms"],
        true,
    ),
    tool(
        "computer_select",
        "Select a named option using accessibility.",
        &["ref", "value"],
        &["timeout_ms"],
        true,
    ),
    tool(
        "computer_scroll",
        "Scroll a control using accessibility.",
        &["ref", "direction"],
        &["amount", "timeout_ms"],
        true,
    ),
    tool(
        "computer_scroll_to",
        "Scroll an observed control into view.",
        &["ref"],
        &["timeout_ms"],
        true,
    ),
];

impl Tool {
    fn schema(&self) -> Value {
        #[cfg(windows)]
        if self.name == "computer_click" {
            return json!({"type":"object","properties":{"ref":{"type":"string","minLength":1},"timeout_ms":{"type":"integer","minimum":1,"maximum":60000},
                "image_id":{"type":"string","minLength":1},"x":{"type":"number","minimum":0},"y":{"type":"number","minimum":0},
                "physical":{"type":"boolean"},"button":{"type":"string","enum":["left","right","middle"]},"count":{"type":"integer","minimum":1,"maximum":3}},
                "additionalProperties":false,"oneOf":[{"required":["ref"],"properties":{"physical":{"const":false},"image_id":false,"x":false,"y":false,"button":false,"count":false}},
                {"required":["image_id","x","y","physical"],"properties":{"physical":{"const":true},"ref":false,"timeout_ms":false}}]});
        }
        let mut properties = Map::new();
        for &key in self.required.iter().chain(self.optional) {
            properties.insert(key.into(), match key {
                "timeout_ms" => json!({"type":"integer","minimum":1,"maximum":60000}),
                "exact" | "physical" => json!({"type":"boolean"}),
                "text" => json!({"type":"string","maxLength":10000}),
                "property" if self.name == "computer_get" => json!({"type":"string","enum":["text","value","title","bounds","role","states"]}),
                "property" => json!({"type":"string","enum":["visible","enabled","checked","focused","expanded","selected"]}),
                "state" => json!({"type":"string","enum":["checked","expanded"]}),
                "value" if self.name == "computer_set_state" => json!({"type":"boolean"}),
                "value" => json!({"type":"string","maxLength":65536}),
                "direction" => json!({"type":"string","enum":["up","down","left","right"]}),
                "amount" => json!({"type":"integer","minimum":1,"maximum":100}),
                "key" => json!({"type":"string","enum":["Escape","escape","Esc","esc"]}),
                "action" => json!({"type":"string","enum":["focus","move","resize","minimize","maximize","restore"]}),
                "x"|"y" => json!({"type":"integer","minimum":i32::MIN,"maximum":i32::MAX}),
                "width"|"height" => json!({"type":"integer","minimum":1,"maximum":i32::MAX}),
                "from_x"|"from_y"|"to_x"|"to_y"=>json!({"type":"number","minimum":0}),
                "max_dimension" => json!({"type":"integer","minimum":64,"maximum":2800}),
                "region" => json!({"type":"object","additionalProperties":false,"required":["x","y","width","height"],
                    "properties":{"x":{"type":"integer","minimum":0},"y":{"type":"integer","minimum":0},
                    "width":{"type":"integer","minimum":1},"height":{"type":"integer","minimum":1}}}),
                _ => json!({"type":"string","minLength":1,"maxLength":2048}),
            });
        }
        let mut schema = json!({"type":"object","properties":properties,"required":self.required,"additionalProperties":false});
        if self.name == "computer_window" {
            schema["oneOf"] = json!([
                {"properties":{"action":{"const":"move"},"width":false,"height":false},"required":["x","y"]},
                {"properties":{"action":{"const":"resize"},"x":false,"y":false},"required":["width","height"]},
                {"properties":{"action":{"enum":["focus","minimize","maximize","restore"]},"x":false,"y":false,"width":false,"height":false}}
            ]);
        }
        schema
    }
}

pub(super) fn read_only(name: &str) -> Option<bool> {
    TOOLS.iter().find(|t| t.name == name).map(|t| !t.writes)
}

pub(super) fn full_control(config: &Value) -> bool {
    config["security"]["permission_level"]
        .as_str()
        .unwrap_or("full_control")
        == "full_control"
}

pub(super) fn definitions(mode: &str, config: &Value) -> Vec<Value> {
    if mode == "writer" {
        return Vec::new();
    }
    let installed = full_control(config) && native::binary().is_some_and(|p| p.is_file());
    TOOLS.iter().filter(|t| installed || t.name == "computer_status").map(|t|
        json!({"type":"function","function":{"name":t.name,"description":t.description,"parameters":t.schema()}})
    ).collect()
}

static DESKTOP: Mutex<()> = Mutex::const_new(());
static VALIDATORS: LazyLock<Vec<jsonschema::Validator>> = LazyLock::new(|| {
    TOOLS
        .iter()
        .map(|t| jsonschema::validator_for(&t.schema()).expect("built-in desktop tool schema"))
        .collect()
});

pub(super) type RunDesktop = tokio::sync::OnceCell<Mutex<Desktop>>;

pub(super) struct Desktop {
    native: native::Native,
    windows: Vec<Value>,
    window: Option<Value>,
    refs: HashSet<String>,
    screenshots: std::collections::VecDeque<screenshot::Capture>,
    #[cfg(windows)]
    pointer: Option<pointer::Target>,
    #[cfg(windows)]
    escape: Option<tokio_util::task::AbortOnDropHandle<()>>,
}

fn collect_refs(node: &Value, refs: &mut HashSet<String>) {
    if let Some(id) = node["ref_id"].as_str() {
        refs.insert(id.to_owned());
    }
    if let Some(children) = node["children"].as_array() {
        for child in children {
            collect_refs(child, refs);
        }
    }
}

fn same_window(a: &Value, b: &Value) -> bool {
    a["id"].is_string()
        && a["pid"].is_number()
        && a["process_instance"]
            .as_str()
            .is_some_and(|instance| !instance.is_empty())
        && ["id", "pid", "app_name", "process_instance"]
            .iter()
            .all(|k| a[k] == b[k])
}

fn failure(command: &str, code: &str, message: impl ToString, uncertain: bool) -> Value {
    let (delivery, retry) = if uncertain {
        ("unknown", "unsafe")
    } else {
        ("not_delivered", "safe")
    };
    json!({"version":"2.6","command":command,"ok":false,"error":{"code":code,"message":message.to_string(),"disposition":{"delivery":delivery,"retry":retry}}})
}

fn result(envelope: Value) -> ToolResult {
    let text = envelope.to_string();
    if envelope["ok"] == true {
        ToolResult::ok(text, envelope)
    } else {
        let mut r = ToolResult::fail(text);
        r.data = envelope;
        r
    }
}

impl Run {
    pub(super) async fn computer_tool(
        &self,
        name: &str,
        p: &Value,
        control: &super::RunControl,
    ) -> Result<ToolResult> {
        let cancel = &control.cancel;
        let index = TOOLS
            .iter()
            .position(|t| t.name == name)
            .ok_or("Unknown Computer Use operation.")?;
        let tool = &TOOLS[index];
        if let Err(error) = VALIDATORS[index].validate(p) {
            return Ok(result(failure(name, "INVALID_ARGS", error, false)));
        }
        if name == "computer_type_text"
            && p["text"].as_str().is_some_and(|text| text.len() > 10_000)
        {
            return Ok(result(failure(
                name,
                "INVALID_ARGS",
                "Text exceeds 10,000 UTF-8 bytes.",
                false,
            )));
        }
        let _lease = tokio::select! {biased;
            _ = cancel.cancelled() => return Ok(result(failure(name,"CANCELLED","Cancelled before desktop dispatch.",false))),
            guard = DESKTOP.lock() => guard,
        };
        let state = self
            .desktop
            .get_or_try_init(|| async {
                let native = tokio::task::spawn_blocking(native::Native::open).await??;
                Ok::<_, Box<dyn std::error::Error + Send + Sync>>(Mutex::new(Desktop {
                    native,
                    windows: Vec::new(),
                    window: None,
                    refs: HashSet::new(),
                    screenshots: Default::default(),
                    #[cfg(windows)]
                    pointer: None,
                    #[cfg(windows)]
                    escape: None,
                }))
            })
            .await;
        let state = match state {
            Ok(state) => state,
            Err(error) => return Ok(result(failure(name, "ENGINE_UNAVAILABLE", error, false))),
        };
        let mut state = state.lock().await;
        #[cfg(windows)]
        if name != "computer_status" {
            state
                .escape
                .get_or_insert_with(|| pointer::watch_escape(control));
        }
        #[cfg(windows)]
        let _occupation = match reverie_platform::desktop::occupy(cancel, tool.writes).await {
            Ok(lease) => lease,
            Err(error) => {
                return Ok(result(failure(
                    name,
                    error.code,
                    error.message,
                    error.uncertain,
                )));
            }
        };
        if name == "computer_screenshot" {
            return Ok(result(
                state.capture(p, self, control).await.unwrap_or_else(|e| e),
            ));
        }
        #[cfg(windows)]
        if name == "computer_drag" || (name == "computer_click" && p.get("image_id").is_some()) {
            return Ok(result(
                state
                    .pointer_input(name, p, control)
                    .await
                    .unwrap_or_else(|e| e),
            ));
        }
        #[cfg(windows)]
        if tool.writes || name == "computer_list_windows" {
            state.pointer = None;
        }
        Ok(result(state.execute(tool, p, control).await))
    }
}

impl Desktop {
    async fn live_window(
        &self,
        window: &Value,
        cancel: &CancellationToken,
    ) -> std::result::Result<Value, Value> {
        let rows = self
            .native
            .invoke(
                "list-windows",
                &[format!(
                    "--app={}",
                    window["app_name"].as_str().unwrap_or_default()
                )],
                None,
                5000,
                false,
                cancel,
            )
            .await;
        if rows["ok"] != true {
            return Err(rows);
        }
        if let Some(current) = rows["data"]
            .as_array()
            .and_then(|v| v.iter().find(|w| same_window(window, w)))
        {
            return Ok(current.clone());
        }
        Err(failure(
            "list-windows",
            "STALE_WINDOW",
            "Window identity changed. List windows and observe again.",
            false,
        ))
    }

    async fn execute(&mut self, tool: &Tool, p: &Value, control: &super::RunControl) -> Value {
        let cancel = &control.cancel;
        let name = tool.name.trim_start_matches("computer_");
        let mut command = name.replace('_', "-");
        let mut args = Vec::new();
        let mut stdin = None;
        let timeout = p["timeout_ms"].as_u64().unwrap_or(5000);
        let window = if let Some(id) = p["window_id"].as_str() {
            self.refs.clear();
            self.window = None;
            let Some(window) = self.windows.iter().find(|w| w["id"] == id).cloned() else {
                return failure(
                    name,
                    "UNKNOWN_WINDOW",
                    "Use a window ID from this run's latest window list.",
                    false,
                );
            };
            args.push(format!("--window-id={id}"));
            Some(window)
        } else if let Some(id) = p["ref"].as_str() {
            if !self.refs.contains(id) {
                return failure(
                    name,
                    "STALE_REF",
                    "Use a qualified ref from this run's latest window observation.",
                    false,
                );
            }
            args.push(id.into());
            self.window.clone()
        } else {
            None
        };
        if let Some(window) = &window
            && let Err(error) = self.live_window(window, cancel).await
        {
            self.refs.clear();
            self.window = None;
            return error;
        }
        #[cfg(windows)]
        if name == "press_key" {
            let Some(pid) = window.as_ref().and_then(|w| w["pid"].as_u64()) else {
                return failure(
                    name,
                    "STALE_WINDOW",
                    "Observe the active window again.",
                    false,
                );
            };
            let Ok(_commit) = super::lock(&control.commit_gate) else {
                return failure(name, "INPUT_BUSY", "Desktop input is unavailable.", false);
            };
            if reverie_platform::desktop::escape_down() {
                control.cancel.cancel();
            }
            if cancel.is_cancelled() {
                return failure(name, "CANCELLED", "Cancelled before sending Escape.", false);
            }
            return match reverie_platform::desktop::application_escape(
                p["window_id"].as_str().unwrap_or_default(),
                pid,
            ) {
                Ok(()) => json!({"version":"2.6","ok":true,"command":"press-key","data":{
                    "window_id":p["window_id"],"key":"Escape","verification_scope":"window_message_queue",
                    "disposition":{"delivery":"delivered_unverified","retry":"unsafe"}}}),
                Err(e) => failure(name, e.code, e.message, e.uncertain),
            };
        }
        for flag in ["app", "name", "role", "property", "direction"] {
            if let Some(value) = p[flag].as_str() {
                args.push(format!("--{flag}={value}"));
            }
        }
        if let Some(amount) = p["amount"].as_u64() {
            args.push(format!("--amount={amount}"));
        }
        if p["exact"] == true {
            args.push("--exact".into());
        }
        if tool.optional.contains(&"timeout_ms") {
            args.push(format!("--timeout-ms={timeout}"));
        }
        match name {
            "focus" => args.push("--headed".into()),
            "type_text" => {
                command = "type".into();
                if p["physical"] == true {
                    args.push("--headed".into());
                }
                args.push("--stdin".into());
                stdin = p["text"].as_str();
            }
            "window" => {
                command = match p["action"].as_str().unwrap() {
                    "focus" => "focus-window",
                    "move" => "move-window",
                    "resize" => "resize-window",
                    other => other,
                }
                .into();
                for key in ["x", "y", "width", "height"] {
                    if let Some(n) = p[key].as_i64() {
                        args.push(format!("--{key}={n}"));
                    }
                }
            }
            "wait" => {
                command = "snapshot".into();
                args.extend([
                    "--compact".into(),
                    format!("--wait-for={}", p["selector"].as_str().unwrap()),
                    format!("--wait-timeout={timeout}"),
                ]);
            }
            "snapshot" => args.push("--compact".into()),
            "set_value" => {
                args.push("--stdin".into());
                stdin = p["value"].as_str();
            }
            "select" => args.extend(["--".into(), p["value"].as_str().unwrap().into()]),
            "set_state" => {
                command = match (p["state"].as_str(), p["value"].as_bool()) {
                    (Some("checked"), Some(true)) => "check",
                    (Some("checked"), _) => "uncheck",
                    (_, Some(true)) => "expand",
                    _ => "collapse",
                }
                .into()
            }
            _ => {}
        }
        if tool.writes || name == "list_windows" {
            self.refs.clear();
            self.window = None;
        }
        if name == "list_windows" {
            self.windows.clear();
        }
        let reply = self
            .native
            .invoke(&command, &args, stdin, timeout, tool.writes, cancel)
            .await;
        if reply["ok"] != true {
            return reply;
        }
        if name == "window" {
            return reply;
        }
        let data = &reply["data"];
        if let Some(id) = p["window_id"].as_str() {
            let window = window.unwrap();
            if data["window"]["id"]
                .as_str()
                .is_some_and(|observed| observed != id)
                || (command == "snapshot" && data["window"]["id"] != id)
            {
                return failure(
                    name,
                    "STALE_WINDOW",
                    "Observation returned a different window.",
                    false,
                );
            }
            if let Err(error) = self.live_window(&window, cancel).await {
                return error;
            }
            self.window = Some(window);
            collect_refs(&data["tree"], &mut self.refs);
            if let Some(matches) = data["matches"].as_array() {
                for item in matches {
                    collect_refs(item, &mut self.refs);
                }
            }
        } else if name == "list_windows" {
            self.windows = data.as_array().cloned().unwrap_or_default();
        }
        reply
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(windows)]
    #[test]
    fn application_escape_requires_an_exact_window_and_has_no_global_override() {
        let index = TOOLS
            .iter()
            .position(|tool| tool.name == "computer_press_key")
            .unwrap();
        let schema = &VALIDATORS[index];
        assert_eq!(read_only("computer_press_key"), Some(false));
        assert!(schema.is_valid(&json!({"key":"Escape","window_id":"w-1"})));
        assert!(!schema.is_valid(&json!({"key":"Escape"})));
        assert!(!schema.is_valid(&json!({"key":"Escape","window_id":"w-1","force":true})));
        assert!(!schema.is_valid(&json!({"key":"Alt+Tab","window_id":"w-1"})));
    }

    #[test]
    fn window_id_reuse_requires_the_same_process_instance() {
        let old =
            json!({"id":"w-42","pid":19,"app_name":"Editor","process_instance":"old","title":"A"});
        let mut live = old.clone();
        live["title"] = json!("B");
        assert!(same_window(&old, &live));
        live["process_instance"] = json!("new");
        assert!(!same_window(&old, &live));
        assert!(!same_window(&Value::Null, &Value::Null));
    }

    #[test]
    fn only_control_nodes_contribute_refs_and_headless_arguments_are_closed() {
        let mut refs = HashSet::new();
        collect_refs(
            &json!({"name":"@text:e1","details":{"ref_id":"@other:e2"},"children":[{"ref_id":"@observed:e3"}]}),
            &mut refs,
        );
        assert_eq!(refs, HashSet::from(["@observed:e3".into()]));
        let click = TOOLS
            .iter()
            .position(|t| t.name == "computer_click")
            .unwrap();
        assert!(VALIDATORS[click].is_valid(&json!({"ref":"@observed:e3"})));
        assert!(!VALIDATORS[click].is_valid(&json!({"ref":"@observed:e3","headed":true})));
        assert!(definitions("writer", &json!({})).is_empty());
        assert_eq!(
            definitions(
                "reverie",
                &json!({"security":{"permission_level":"read_only"}})
            )
            .len(),
            1
        );
    }
}
