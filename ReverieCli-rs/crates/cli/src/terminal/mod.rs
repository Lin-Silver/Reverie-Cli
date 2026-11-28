mod connectors;
mod context;
mod cursor_backend;
mod input;
mod input_events;
mod markets;
mod models;
mod plugins;
mod screen;
mod skills;

use crossterm::event::{Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use input::{Input, display_text};
use input_events::InputEvents;
use reverie_core::{
    Kernel, Result,
    host::{EventSink, KernelHost},
};
use reverie_protocol::{Reply, Request, VERSION};
use screen::Screen;
use serde_json::{Value, json};
use std::{
    collections::{HashSet, VecDeque},
    path::PathBuf,
    sync::Arc,
    time::Duration,
};
use tokio::sync::mpsc;

enum PanelKind {
    Question,
    Approval,
    Models,
    ModelRemoval,
    ModelScopeKey { activate: bool },
    ModelScopeUrl,
    Sessions,
    ContextRemoval,
    PluginConfirmation,
    ConnectorChoice,
    ConnectorInput,
    ConnectorSecret,
    ConnectorConfirmation,
}
impl PanelKind {
    fn is_secret(&self) -> bool {
        matches!(self, Self::ConnectorSecret | Self::ModelScopeKey { .. })
    }
    fn is_provider_input(&self) -> bool {
        matches!(self, Self::ModelScopeKey { .. } | Self::ModelScopeUrl)
    }
    fn is_connector(&self) -> bool {
        matches!(
            self,
            Self::ConnectorChoice
                | Self::ConnectorInput
                | Self::ConnectorSecret
                | Self::ConnectorConfirmation
        )
    }
    fn accepts_input(&self) -> bool {
        self.is_provider_input()
            || matches!(
                self,
                Self::Question | Self::Approval | Self::ConnectorInput | Self::ConnectorSecret
            )
    }
}
pub(super) struct Panel {
    title: String,
    options: Vec<String>,
    selected: usize,
    multiple: bool,
    checked: HashSet<usize>,
    kind: PanelKind,
    source: Value,
    draft: Input,
}
struct Tui {
    input_events: InputEvents,
    host: Arc<KernelHost>,
    screen: Screen,
    events: mpsc::UnboundedReceiver<Value>,
    sink: EventSink,
    session: String,
    state: Value,
    input: Input,
    panel: Option<Panel>,
    active: Option<tokio::task::JoinHandle<Reply>>,
    active_owner: Option<context::RunOwner>,
    background: Option<tokio::task::JoinHandle<Reply>>,
    background_id: String,
    compaction_owner: Option<context::RunOwner>,
    context_usage: Value,
    connectors: connectors::ConnectorUiState,
    queue: VecDeque<String>,
    pending: String,
    status: String,
    history: Vec<String>,
    history_cursor: usize,
    history_draft: Input,
    quitting: bool,
    no_index: bool,
}

impl Tui {
    async fn request(&self, action: &str, payload: Value) -> Result<Value> {
        let reply = self
            .host
            .dispatch(
                Request {
                    id: json!("terminal-control"),
                    action: action.into(),
                    payload,
                },
                self.sink.clone(),
            )
            .await;
        if reply.kind == "error" {
            return Err(reply.fields["error"]
                .as_str()
                .unwrap_or("Request failed.")
                .into());
        }
        Ok(json!(reply.fields))
    }
    async fn refresh(&mut self) -> Result<()> {
        self.state = self.request("getState", json!({})).await?["state"].clone();
        if self.active_owner.is_none() && self.compaction_owner.is_none() {
            self.context_usage = self
                .request("getContextUsage", json!({"sessionId":self.session}))
                .await
                .map(|reply| reply["usage"].clone())
                .unwrap_or(Value::Null);
        }
        self.status = format!(
            "Reverie {VERSION} · {} · {}",
            self.state["workspace"]["active_model"]["display_name"]
                .as_str()
                .unwrap_or("Choose a model with /model"),
            self.state["sessions"]["items"]
                .as_array()
                .into_iter()
                .flatten()
                .find(|item| item["id"] == self.session)
                .and_then(|item| item["name"].as_str())
                .unwrap_or("Conversation")
        );
        Ok(())
    }
    async fn show_history(&mut self) -> Result<()> {
        let session = self
            .request("getSession", json!({"sessionId":self.session}))
            .await?["session"]
            .clone();
        self.screen.print(&format!(
            "Conversation: {}",
            session["name"].as_str().unwrap_or_default()
        ))?;
        self.history.clear();
        for message in session["messages"].as_array().into_iter().flatten() {
            if matches!(message["role"].as_str(), Some("user" | "assistant")) {
                self.screen.print(&format!(
                    "{}\n{}",
                    message["role"].as_str().unwrap(),
                    message["content"].as_str().unwrap_or_default()
                ))?;
            }
            if message["role"] == "user"
                && let Some(text) = message["content"].as_str()
            {
                self.history.push(text.into());
            }
        }
        self.history_cursor = self.history.len();
        Ok(())
    }
    fn panel(
        &mut self,
        kind: PanelKind,
        title: String,
        options: Vec<String>,
        source: Value,
        multiple: bool,
    ) {
        let draft = std::mem::take(&mut self.input);
        self.panel = Some(Panel {
            title,
            options,
            selected: 0,
            multiple,
            checked: HashSet::new(),
            kind,
            source,
            draft,
        });
    }
    async fn submit_panel(&mut self, cancelled: bool) -> Result<()> {
        let Some(panel) = &self.panel else {
            return Ok(());
        };
        if panel.kind.is_connector() {
            return self.submit_connector_panel(cancelled).await;
        }
        if panel.kind.is_provider_input() {
            return self.submit_modelscope_input(cancelled).await;
        }
        let index = panel.selected;
        match panel.kind {
            PanelKind::ModelRemoval => {
                let panel = self.panel.take().unwrap();
                self.input = panel.draft;
                if !cancelled && index == 1 {
                    self.request("deleteStandardModel", panel.source).await?;
                    self.screen.print("Standard model profile deleted.")?;
                }
                return self.refresh().await;
            }
            PanelKind::PluginConfirmation => {
                if !cancelled && index == 1 {
                    let action = panel.source["action"]
                        .as_str()
                        .ok_or("Missing inspected plugin action.")?
                        .to_owned();
                    let payload = panel.source["payload"].clone();
                    self.start_plugin_operation(&action, payload)?;
                }
            }
            PanelKind::ContextRemoval => {
                if !cancelled && index == 1 {
                    let payload = panel.source.clone();
                    self.start_context_operation("removeSemanticResources", payload)?;
                }
            }
            PanelKind::Approval => {
                let decision = if cancelled {
                    "deny"
                } else {
                    ["once", "session", "project", "global", "deny", "message"][index]
                };
                self.request("resolveApproval", json!({"approvalId":panel.source["approval_id"],"runId":panel.source["run_id"],"sessionId":panel.source["session_id"],"decision":decision,"message":self.input.text})).await?;
            }
            PanelKind::Question => {
                let custom = index == panel.options.len() - 1;
                let answer = if custom {
                    self.input.text.clone()
                } else if panel.multiple {
                    panel
                        .options
                        .iter()
                        .enumerate()
                        .filter(|(i, _)| panel.checked.contains(i))
                        .map(|(_, label)| label.clone())
                        .collect::<Vec<_>>()
                        .join("\n")
                } else {
                    panel.options[index].clone()
                };
                self.request("resolveUserInput", json!({"questionId":panel.source["question_id"],"runId":panel.source["run_id"],"sessionId":panel.source["session_id"],"answer":answer,"cancelled":cancelled})).await?;
            }
            PanelKind::Models if !cancelled => {
                let row = &panel.source[index];
                self.request("selectModel", json!({"sessionId":self.session,"source":row["source"],"modelId":row["id"],"profileId":row["profile_id"]})).await?;
            }
            PanelKind::Sessions if !cancelled => {
                self.session = panel.source[index]["id"]
                    .as_str()
                    .ok_or("Invalid session identity.")?
                    .into();
                self.show_history().await?;
            }
            _ => {}
        }
        self.input = self.panel.take().unwrap().draft;
        self.refresh().await
    }
    fn start_prompt(&mut self, prompt: String) -> Result<()> {
        if self.active.is_some() || self.compaction_owner.is_some() {
            return Err("Finish or stop the active conversation operation first.".into());
        }
        let owner = self.new_run_owner("prompt")?;
        let mut payload = owner.payload();
        payload["prompt"] = json!(prompt);
        payload["noIndex"] = json!(self.no_index);
        self.screen.print(&format!("\nYou\n{prompt}\n"))?;
        let pending = self.host.begin_prompt(&payload)?;
        self.active_owner = Some(owner);
        self.pending.clear();
        self.status = "Reverie is working · Ctrl+C to stop".into();
        let host = self.host.clone();
        let sink = self.sink.clone();
        self.active = Some(tokio::spawn(async move {
            host.complete_prompt(json!("terminal-prompt"), pending, sink)
                .await
        }));
        Ok(())
    }
    async fn stop(&mut self) -> Result<()> {
        self.queue.clear();
        if self.active.as_ref().is_some_and(|task| !task.is_finished()) {
            let payload = self
                .active_owner
                .as_ref()
                .ok_or("The active run has no owner.")?
                .payload();
            if let Err(error) = self.request("stopPrompt", payload).await
                && self.active.as_ref().is_some_and(|task| !task.is_finished())
            {
                return Err(error);
            }
            self.status = "Stopping · preserving completed work".into();
        }
        if self.connectors.background {
            self.stop_connector_operation().await?;
        } else {
            self.stop_context_operation().await?;
        }
        Ok(())
    }
    async fn command(&mut self, text: &str) -> Result<()> {
        if let Some(focus) = text
            .strip_prefix("/compact")
            .filter(|rest| rest.is_empty() || rest.chars().next().is_some_and(char::is_whitespace))
        {
            return self.start_compaction(focus.trim());
        }
        let args = shlex::split(text).ok_or("Command contains an unclosed quote.")?;
        match args.first().map(String::as_str) {
            Some("/quit" | "/exit" | "/q") => { self.stop().await?; self.quitting = true; }
            Some("/stop" | "/cancel") => self.stop().await?,
            Some("/help" | "/h") => self.screen.print("/model [id] · /model add <id> <base_url> [api_key_env] [--provider <transport>]\n/model delete <number> · /model remove <number>\nTransports: openai-chat (default), openai-responses, anthropic, gemini\n/modelscope [status | key | activate | model [id [reasoning]] | key-env <name> | endpoint [URL] | refresh]\n/session new [name] · /sessions · /settings\n/permission strict|normal|auto|full_access · /permission fallback wait|deny · /context index · /context usage · /compact [focus] · /resume\n/skills help · /markets help · /plugins help · /mcp help · /connectors help · /stop · /quit\nEnter sends; Shift+Enter, Alt+Enter or Ctrl+J inserts a newline. Paste never submits.\nArrow keys edit; Up/Down recalls prompts on one line. Native terminal scrollback and copy remain available.")?,
            Some("/resume") => {
                if args.len() != 1 { return Err("Use /resume without replacement prompt text.".into()); }
                self.start_resume()?;
            }
            Some("/model") if matches!(args.get(1).map(String::as_str), Some("delete" | "remove")) => {
                self.confirm_model_removal(&args[2..]).await?;
            }
            Some("/model") if args.get(1).is_some_and(|value| value == "add") => {
                let (fields, provider) = match args[2..].split_last_chunk::<2>() {
                    Some((fields, [flag, name])) if flag == "--provider" => (fields, reverie_core::provider::transport_name(name)?),
                    _ => (&args[2..], "openai-chat"),
                };
                let (model, base, key) = match fields {
                    [model, base] if !base.starts_with("--") => (model, base, None),
                    [model, base, key] if !base.starts_with("--") && !key.starts_with("--") => (model, base, Some(key)),
                    _ => return Err("Use /model add <id> <base_url> [api_key_env] [--provider <transport>].".into()),
                };
                let added = self.request("addStandardModel", json!({"model":{"model":model,"base_url":base,"provider":provider,"api_key_env":key}})).await?;
                self.request("selectModel", json!({"sessionId":self.session,"source":"standard","modelId":model,"profileId":added["profile_id"]})).await?;
                self.refresh().await?;
            }
            Some("/model") if args.len() > 1 => {
                self.request("selectModel", json!({"sessionId":self.session,"source":"standard","modelId":args[1]})).await?;
                self.refresh().await?;
            }
            Some("/model" | "/models") => self.show_model_catalog(None).await?,
            Some("/modelscope") => self.modelscope_command(&args[1..]).await?,
            Some("/session" | "/new") if args[0] == "/new" || args.get(1).is_some_and(|value| value == "new") => {
                if self.active.is_some() || self.compaction_owner.is_some() { return Err("Stop the active run before switching conversations.".into()); }
                let name = if args[0] == "/new" { &args[1..] } else { &args[2..] };
                let session = self.request("createSession", json!({"name":name.join(" ")})).await?["session"].clone();
                self.session = session["id"].as_str().unwrap().into();
                self.refresh().await?;
            }
            Some("/session" | "/sessions") => {
                if self.active.is_some() || self.compaction_owner.is_some() { return Err("Stop the active run before switching conversations.".into()); }
                let items = self.request("listSessions", json!({})).await?["sessions"]["items"].clone();
                let labels = items.as_array().into_iter().flatten().map(|item|format!("{} · {}",item["name"].as_str().unwrap_or_default(),item["id"].as_str().unwrap_or_default())).collect::<Vec<_>>();
                if !labels.is_empty() { self.panel(PanelKind::Sessions, "Choose conversation".into(), labels, items, false); }
            }
            Some("/settings") => {
                let settings = self.request("listSettings", json!({"sessionId":self.session})).await?;
                self.screen.print(&serde_json::to_string_pretty(&settings["settings"])? )?;
            }
            Some("/browser-profile") => {
                let [_, value] = args.as_slice() else { return Err("Use /browser-profile persistent|ephemeral.".into()); };
                self.request("setSetting", json!({"sessionId":self.session,"key":"browser_profile","value":value})).await?;
                self.screen.print(&format!("Browser profile: {value}"))?;
                self.refresh().await?;
            }
            Some("/permission") => {
                let (key, value) = match args.as_slice() {
                    [_, fallback, value] if fallback == "fallback" => ("auto_review_fallback", value.as_str()),
                    [_, mode] => ("permission_mode", match mode.as_str() { "default"=>"normal", "auto_check"=>"auto", other=>other }),
                    _ => return Err("Use /permission strict|normal|auto|full_access or /permission fallback wait|deny.".into()),
                };
                self.request("setSetting", json!({"sessionId":self.session,"key":key,"value":value})).await?;
                self.screen.print(&format!("{key}: {value}"))?;
                self.refresh().await?;
            }
            Some("/context")=>self.context_command(&args[1..]).await?,
            Some("/skills" | "/skill")=>self.skills_command(&args[1..]).await?,
            Some("/markets" | "/market")=>self.markets_command(&args[1..]).await?,
            Some("/plugins" | "/plugin")=>self.plugins_command(&args[1..]).await?,
            Some("/mcp")=>self.mcp_command(&args[1..]).await?,
            Some("/connectors" | "/connector")=>self.connectors_command(&args[1..]).await?,
            _ => return Err("Unknown command. Use /help.".into()),
        }
        Ok(())
    }
    async fn key(&mut self, key: KeyEvent) -> Result<()> {
        if key.kind == KeyEventKind::Release {
            return Ok(());
        }
        let control = key.modifiers.contains(KeyModifiers::CONTROL);
        match key.code {
            KeyCode::Char('c')
                if control
                    && self.panel.as_ref().is_some_and(|panel| {
                        panel.kind.is_connector() || panel.kind.is_provider_input()
                    }) =>
            {
                self.submit_panel(true).await?
            }
            KeyCode::Char('d')
                if control
                    && self.input.text.is_empty()
                    && self.panel.as_ref().is_some_and(|panel| {
                        panel.kind.is_connector() || panel.kind.is_provider_input()
                    }) =>
            {
                self.submit_panel(true).await?
            }
            KeyCode::Char('c') if control => {
                if self.active.is_some() || self.background.is_some() {
                    self.stop().await?;
                } else {
                    self.quitting = true;
                }
            }
            KeyCode::Char('d') if control && self.input.text.is_empty() => {
                self.stop().await?;
                self.quitting = true;
            }
            KeyCode::Esc if self.panel.is_some() => self.submit_panel(true).await?,
            KeyCode::Enter
                if key.modifiers.intersects(
                    KeyModifiers::SHIFT | KeyModifiers::ALT | KeyModifiers::CONTROL,
                ) =>
            {
                self.input.insert("\n")
            }
            KeyCode::Char('j') if control => self.input.insert("\n"),
            KeyCode::Enter if self.panel.is_some() => self.submit_panel(false).await?,
            KeyCode::Enter => {
                if self.input.text.trim().is_empty() {
                    return Ok(());
                }
                let text = self.input.take();
                let private = connectors::private_command(&text);
                if !private {
                    self.history.push(text.clone());
                    self.history_cursor = self.history.len();
                }
                if text.starts_with('/') || private {
                    if let Err(error) = self.command(&text).await {
                        if !private {
                            self.input = Input {
                                cursor: text.len(),
                                text,
                            };
                        }
                        return Err(error);
                    }
                } else if self.active.is_some() || self.compaction_owner.is_some() {
                    self.queue.push_back(text);
                    self.status = format!(
                        "Working · {} prompt(s) queued · Ctrl+C to stop",
                        self.queue.len()
                    );
                } else {
                    if let Err(error) = self.start_prompt(text.clone()) {
                        self.input = Input {
                            cursor: text.len(),
                            text,
                        };
                        return Err(error);
                    }
                }
            }
            KeyCode::Up | KeyCode::Down if self.panel.is_some() => {
                let panel = self.panel.as_mut().unwrap();
                panel.selected = if key.code == KeyCode::Up {
                    panel.selected.saturating_sub(1)
                } else {
                    (panel.selected + 1).min(panel.options.len() - 1)
                };
            }
            KeyCode::Char(' ')
                if self.panel.as_ref().is_some_and(|panel| {
                    panel.multiple && panel.selected < panel.options.len() - 1
                }) =>
            {
                let panel = self.panel.as_mut().unwrap();
                if !panel.checked.insert(panel.selected) {
                    panel.checked.remove(&panel.selected);
                }
            }
            KeyCode::Up | KeyCode::Down
                if !self.input.text.contains('\n') && !self.history.is_empty() =>
            {
                if self.history_cursor == self.history.len() {
                    self.history_draft = self.input.clone();
                }
                self.history_cursor = if key.code == KeyCode::Up {
                    self.history_cursor.saturating_sub(1)
                } else {
                    (self.history_cursor + 1).min(self.history.len())
                };
                self.input = if self.history_cursor == self.history.len() {
                    self.history_draft.clone()
                } else {
                    let text = self.history[self.history_cursor].clone();
                    Input {
                        cursor: text.len(),
                        text,
                    }
                };
            }
            KeyCode::Up => self.input.vertical(true),
            KeyCode::Down => self.input.vertical(false),
            KeyCode::Left => self.input.left(),
            KeyCode::Right => self.input.right(),
            KeyCode::Backspace => self.input.backspace(),
            KeyCode::Delete => self.input.delete(),
            KeyCode::Home => self.input.home(),
            KeyCode::End => self.input.end(),
            KeyCode::Char('u') if control => {
                let end = self.input.cursor;
                self.input.home();
                self.input.text.replace_range(self.input.cursor..end, "");
            }
            KeyCode::Char(ch) if !control && !key.modifiers.contains(KeyModifiers::ALT) => {
                if let Some(panel) = self.panel.as_mut()
                    && panel.kind.accepts_input()
                {
                    panel.selected = panel.options.len() - 1;
                }
                self.input.insert(&ch.to_string());
            }
            _ => {}
        }
        Ok(())
    }
    async fn event(&mut self, event: Value) -> Result<()> {
        if matches!(
            event["type"].as_str(),
            Some("context.usage" | "context.compaction.started" | "context.compaction.finished")
        ) && !event.as_object().is_some_and(|fields| {
            self.active_owner
                .as_ref()
                .into_iter()
                .chain(self.compaction_owner.as_ref())
                .any(|owner| owner.matches(fields))
        }) {
            return Ok(());
        }
        match event["type"].as_str() {
            Some("context.usage") => self.context_usage = event["usage"].clone(),
            Some("context.compaction.started") => {
                self.status = "Compacting context · Ctrl+C to stop".into()
            }
            Some("context.compaction.finished") => {
                self.status = if self.compaction_owner.is_some() {
                    "Context compaction finished"
                } else {
                    "Context compaction finished · continuing task"
                }
                .into()
            }
            Some("extension.progress")
                if self.connectors.background
                    && self.background_id.strip_prefix("plugin:")
                        == event["operation_id"].as_str() =>
            {
                self.status = format!(
                    "MCP / Connector {} · /connectors stop",
                    event["phase"].as_str().unwrap_or("working")
                );
            }
            Some("mcp.notification")
                if self.active.is_none()
                    && event["authorization_id"].is_string()
                    && matches!(
                        event["status"].as_str(),
                        Some(
                            "awaiting_authorization" | "callback_received" | "denied" | "cancelled"
                        )
                    ) =>
            {
                self.status = format!(
                    "Connector {} · {} · /connectors list",
                    display_text(event["server_id"].as_str().unwrap_or_default()),
                    event["status"].as_str().unwrap()
                );
            }
            Some("context.progress") if event["operation_id"] == self.background_id => {
                self.status = format!(
                    "Context {} · {}/{} · /context stop",
                    event["phase"].as_str().unwrap_or("working"),
                    event["completed"].as_u64().unwrap_or(0),
                    event["total"].as_u64().unwrap_or(0)
                );
            }
            Some("context.progress")
                if event["automatic"] == true
                    && self.active.is_none()
                    && self.background.is_none() =>
            {
                self.status = format!(
                    "Background context {} · /context watch off",
                    event["phase"].as_str().unwrap_or("working")
                );
            }
            Some("assistant.delta") => self.screen.feed(
                &mut self.pending,
                event["text"].as_str().unwrap_or_default(),
            )?,
            Some("approval.request") => {
                self.screen.flush(&mut self.pending)?;
                self.panel(
                    PanelKind::Approval,
                    format!(
                        "Approve {}?  {}",
                        event["tool"].as_str().unwrap_or("tool"),
                        event["arguments"]
                    ),
                    [
                        "Allow once",
                        "Allow for this conversation",
                        "Allow for this project",
                        "Allow globally",
                        "Deny",
                        "Reply with your own instructions",
                    ]
                    .map(str::to_owned)
                    .into(),
                    event,
                    false,
                );
            }
            Some("user.question") => {
                self.screen.flush(&mut self.pending)?;
                let mut options = event["options"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|option| option.as_str().map(str::to_owned))
                    .collect::<Vec<_>>();
                options.push("Write a custom answer".into());
                let multiple = event["multiple"] == true;
                self.panel(
                    PanelKind::Question,
                    event["question"].as_str().unwrap_or_default().into(),
                    options,
                    event,
                    multiple,
                );
            }
            Some("ui.event") if event["event"]["type"] == "tool_start" => {
                self.screen.flush(&mut self.pending)?;
                self.status = format!(
                    "Running {} · Ctrl+C to stop",
                    event["event"]["tool_name"].as_str().unwrap_or("tool")
                );
            }
            Some("ui.event") if event["event"]["type"] == "tool_progress" => {
                self.screen.feed(
                    &mut self.pending,
                    event["event"]["text"].as_str().unwrap_or_default(),
                )?;
            }
            _ => {}
        }
        Ok(())
    }
    async fn loop_events(&mut self) -> Result<()> {
        let mut waiting_dialogs = VecDeque::new();
        loop {
            // A run can request approval while the user is typing a credential.
            // Deliver that dialog after the form closes so its input never becomes a chat draft.
            let editing = self
                .panel
                .as_ref()
                .is_some_and(|p| p.kind.is_secret() || p.kind.is_provider_input());
            if self.panel.is_none()
                && let Some(event) = waiting_dialogs.pop_front()
            {
                self.event(event).await?;
            }
            while let Ok(event) = self.events.try_recv() {
                if editing
                    && matches!(
                        event["type"].as_str(),
                        Some("approval.request" | "user.question")
                    )
                {
                    waiting_dialogs.push_back(event);
                } else {
                    self.event(event).await?;
                }
            }
            if !editing
                && self
                    .background
                    .as_ref()
                    .is_some_and(|task| task.is_finished())
            {
                let reply = self.background.take().unwrap().await?;
                while let Ok(event) = self.events.try_recv() {
                    self.event(event).await?;
                }
                self.background_id.clear();
                if let Some(owner) = self.compaction_owner.take() {
                    self.print_compaction_reply(&reply, &owner)?;
                } else if self.connectors.background {
                    self.print_connector_reply(&reply)?;
                } else if reply.kind == "market.entries" {
                    self.print_market_reply(&reply)?;
                } else if matches!(reply.kind.as_str(), "plugin.prepared" | "plugin.updated") {
                    self.print_plugin_reply(&reply)?;
                } else {
                    self.print_context_reply(&reply)?;
                }
                self.refresh().await?;
            }
            if !editing && self.active.as_ref().is_some_and(|task| task.is_finished()) {
                let reply = self.active.take().unwrap().await?;
                waiting_dialogs.clear();
                while let Ok(event) = self.events.try_recv() {
                    self.event(event).await?;
                }
                self.active_owner = None;
                self.screen.flush(&mut self.pending)?;
                if let Some(panel) = self.panel.take() {
                    self.input = panel.draft;
                }
                if reply.kind == "error" {
                    self.screen
                        .print(reply.fields["error"].as_str().unwrap_or("Run failed."))?;
                } else if reply.fields["result"]["success"] != true {
                    self.screen.print(
                        reply.fields["result"]["error"]
                            .as_str()
                            .unwrap_or("Run failed."),
                    )?;
                }
                self.refresh().await?;
            }
            if !self.quitting
                && self.active.is_none()
                && self.compaction_owner.is_none()
                && let Some(prompt) = self.queue.pop_front()
                && let Err(error) = self.start_prompt(prompt)
            {
                self.screen.print(&error.to_string())?;
            }
            if self.quitting && self.active.is_none() && self.background.is_none() {
                break;
            }
            let usage = self.context_usage_label();
            let status = if usage.is_empty() {
                self.status.clone()
            } else {
                format!("{} · {usage}", self.status)
            };
            self.screen
                .draw(&self.input, &status, &self.pending, self.panel.as_ref())?;
            if let Some(event) = self.input_events.poll(Duration::from_millis(20))? {
                let outcome = match event {
                    Event::Key(key) => self.key(key).await,
                    Event::Paste(text) => {
                        if let Some(panel) = self.panel.as_mut()
                            && panel.kind.accepts_input()
                        {
                            panel.selected = panel.options.len() - 1;
                        }
                        if self
                            .panel
                            .as_ref()
                            .is_some_and(|panel| panel.kind.is_secret())
                        {
                            self.input.insert(&text);
                        } else {
                            self.input.insert(&display_text(
                                &text.replace("\r\n", "\n").replace('\r', "\n"),
                            ));
                        }
                        Ok(())
                    }
                    _ => Ok(()),
                };
                if let Err(error) = outcome {
                    self.status = error.to_string();
                }
            }
        }
        Ok(())
    }
}

pub fn run(project: PathBuf, session: Option<String>, no_index: bool) -> Result<()> {
    let runtime = tokio::runtime::Runtime::new()?;
    runtime.block_on(async {
        let host=Arc::new(KernelHost::for_cli(Kernel::new(project)?));
        let (sender,events)=mpsc::unbounded_channel();
        let sink: EventSink=Arc::new(move |event| { let _=sender.send(event); });
        let screen=Screen::new()?;
        let input_events=InputEvents::new()?;
        let mut tui=Tui { input_events, host, screen, events, sink, session:String::new(), state:Value::Null, input:Input::default(), panel:None, active:None,active_owner:None, background:None,background_id:String::new(),compaction_owner:None,context_usage:Value::Null, connectors:connectors::ConnectorUiState::default(), queue:VecDeque::new(), pending:String::new(), status:String::new(), history:Vec::new(), history_cursor:0, history_draft:Input::default(), quitting:false, no_index };
        let initialized=tui.request("initialize",json!({})).await?["state"].clone();
        let selected=session.filter(|id|!id.is_empty()).or_else(|| initialized["sessions"]["current_session_id"].as_str().filter(|id|!id.is_empty()).map(str::to_owned));
        tui.session=if let Some(session)=selected { tui.request("getSession",json!({"sessionId":session})).await?; session } else { tui.request("createSession",json!({})).await?["session"]["id"].as_str().ok_or("Conversation was not created.")?.into() };
        tui.refresh().await?;
        tui.screen.print(&format!("Reverie CLI {VERSION}\n{}\nUse /help for commands. Conversation history remains in terminal scrollback.",tui.host.project_root()?.display()))?;
        tui.show_history().await?;
        let result=tui.loop_events().await;
        tui.host.cancel_all();
        if let Some(task)=tui.active.take() { let _=task.await; }
        if let Some(task)=tui.background.take() { let _=task.await; }
        tui.host.close_extensions().await;
        result
    })
}
