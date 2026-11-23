mod cursor_backend;
mod input;
mod input_events;
mod screen;

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
    Sessions,
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
        let index = panel.selected;
        match panel.kind {
            PanelKind::Approval => {
                let decision = if cancelled {
                    "deny"
                } else {
                    ["once", "session", "deny", "message"][index]
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
                self.request("selectModel", json!({"sessionId":self.session,"source":"standard","modelId":panel.source[index]["id"]})).await?;
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
        self.screen.print(&format!("\nYou\n{prompt}\n"))?;
        let pending = self.host.begin_prompt(
            &json!({"sessionId":self.session,"prompt":prompt,"noIndex":self.no_index}),
        )?;
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
            if let Err(error) = self
                .request("stopPrompt", json!({"sessionId":self.session}))
                .await
                && self.active.as_ref().is_some_and(|task| !task.is_finished())
            {
                return Err(error);
            }
            self.status = "Stopping · preserving completed work".into();
        }
        Ok(())
    }
    async fn command(&mut self, text: &str) -> Result<()> {
        let args = shlex::split(text).ok_or("Command contains an unclosed quote.")?;
        match args.first().map(String::as_str) {
            Some("/quit" | "/exit" | "/q") => { self.stop().await?; self.quitting = true; }
            Some("/stop" | "/cancel") => self.stop().await?,
            Some("/help" | "/h") => self.screen.print("/model [id] · /model add <id> <base_url> [api_key_env]\n/session new [name] · /sessions · /settings\n/permission default|strict|auto_check · /context index\n/stop · /quit\nEnter sends; Shift+Enter, Alt+Enter or Ctrl+J inserts a newline. Paste never submits.\nArrow keys edit; Up/Down recalls prompts on one line. Native terminal scrollback and copy remain available.")?,
            Some("/model") if args.get(1).is_some_and(|value| value == "add") => {
                let model = args.get(2).ok_or("Supply a model id and base URL.")?;
                let base = args.get(3).ok_or("Supply a model base URL.")?;
                self.request("addStandardModel", json!({"model":{"model":model,"base_url":base,"provider":"openai-chat","api_key_env":args.get(4)}})).await?;
                self.request("selectModel", json!({"sessionId":self.session,"source":"standard","modelId":model})).await?;
                self.refresh().await?;
            }
            Some("/model") if args.len() > 1 => {
                self.request("selectModel", json!({"sessionId":self.session,"source":"standard","modelId":args[1]})).await?;
                self.refresh().await?;
            }
            Some("/model" | "/models") => {
                let models = self.request("getModelSources", json!({"sessionId":self.session})).await?["models"]["sources"][0]["models"].clone();
                let labels = models.as_array().into_iter().flatten().map(|model| model["display_name"].as_str().unwrap_or_default().into()).collect::<Vec<_>>();
                if labels.is_empty() { return Err("No models configured. Use /model add <id> <base_url> [api_key_env].".into()); }
                self.panel(PanelKind::Models, "Choose model".into(), labels, models, false);
            }
            Some("/session" | "/new") if args.first().is_some_and(|value| value == "/new") || args.get(1).is_some_and(|value| value == "new") => {
                if self.active.is_some() { return Err("Stop the active run before switching conversations.".into()); }
                let session = self.request("createSession", json!({"name":args.iter().skip(2).cloned().collect::<Vec<_>>().join(" ")})).await?["session"].clone();
                self.session = session["id"].as_str().unwrap().into();
                self.refresh().await?;
            }
            Some("/session" | "/sessions") => {
                if self.active.is_some() { return Err("Stop the active run before switching conversations.".into()); }
                let items = self.request("listSessions", json!({})).await?["sessions"]["items"].clone();
                let labels = items.as_array().into_iter().flatten().map(|item|format!("{} · {}",item["name"].as_str().unwrap_or_default(),item["id"].as_str().unwrap_or_default())).collect::<Vec<_>>();
                if !labels.is_empty() { self.panel(PanelKind::Sessions, "Choose conversation".into(), labels, items, false); }
            }
            Some("/settings") => {
                let settings = self.request("listSettings", json!({"sessionId":self.session})).await?;
                self.screen.print(&serde_json::to_string_pretty(&settings["settings"])? )?;
            }
            Some("/permission") => {
                let mode = args.get(1).ok_or("Choose default, strict or auto_check.")?;
                if !["default","strict","auto_check"].contains(&mode.as_str()) { return Err("Choose default, strict or auto_check.".into()); }
                let saved = self.request("getConversationConfig", json!({"sessionId":self.session})).await?;
                let mut configuration = saved["configuration"].clone();
                if !configuration["settings"]["security"].is_object() { configuration["settings"]["security"] = json!({"permission_level":"full_control"}); }
                configuration["settings"]["security"]["permission_mode"] = json!(mode);
                self.request("getConversationConfig", json!({"sessionId":self.session,"configuration":configuration,"revision":saved["revision"]})).await?;
                self.screen.print(&format!("Approval mode: {mode}"))?;
                self.refresh().await?;
            }
            Some("/context") if args.get(1).is_some_and(|value|value == "index") => {
                let result = self.request("indexWorkspace", json!({})).await?;
                self.screen.print(&serde_json::to_string_pretty(&result["result"])? )?;
            }
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
            KeyCode::Char('c') if control => {
                if self.active.is_some() {
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
                self.history.push(text.clone());
                self.history_cursor = self.history.len();
                if text.starts_with('/') {
                    if let Err(error) = self.command(&text).await {
                        self.input = Input {
                            cursor: text.len(),
                            text,
                        };
                        return Err(error);
                    }
                } else if self.active.is_some() {
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
                    && matches!(panel.kind, PanelKind::Question | PanelKind::Approval)
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
        match event["type"].as_str() {
            Some("assistant.delta") => self.screen.feed(
                &mut self.pending,
                event["text"].as_str().unwrap_or_default(),
            )?,
            Some("approval.request") => {
                self.screen.flush(&mut self.pending)?;
                self.panel(
                    PanelKind::Approval,
                    format!("Approve {}?", event["tool"].as_str().unwrap_or("tool")),
                    [
                        "Allow once",
                        "Allow for this conversation",
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
        loop {
            while let Ok(event) = self.events.try_recv() {
                self.event(event).await?;
            }
            if self.active.as_ref().is_some_and(|task| task.is_finished()) {
                let reply = self.active.take().unwrap().await?;
                while let Ok(event) = self.events.try_recv() {
                    self.event(event).await?;
                }
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
                if !self.quitting
                    && let Some(prompt) = self.queue.pop_front()
                    && let Err(error) = self.start_prompt(prompt)
                {
                    self.screen.print(&error.to_string())?;
                }
            }
            if self.quitting && self.active.is_none() {
                break;
            }
            self.screen.draw(
                &self.input,
                &self.status,
                &self.pending,
                self.panel.as_ref(),
            )?;
            if let Some(event) = self.input_events.poll(Duration::from_millis(20))? {
                let outcome = match event {
                    Event::Key(key) => self.key(key).await,
                    Event::Paste(text) => {
                        if let Some(panel) = self.panel.as_mut()
                            && matches!(panel.kind, PanelKind::Question | PanelKind::Approval)
                        {
                            panel.selected = panel.options.len() - 1;
                        }
                        self.input.insert(&display_text(
                            &text.replace("\r\n", "\n").replace('\r', "\n"),
                        ));
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
        let host=Arc::new(KernelHost::new(Kernel::new(project)?));
        let (sender,events)=mpsc::unbounded_channel();
        let sink: EventSink=Arc::new(move |event| { let _=sender.send(event); });
        let screen=Screen::new()?;
        let input_events=InputEvents::new()?;
        let mut tui=Tui { input_events, host, screen, events, sink, session:String::new(), state:Value::Null, input:Input::default(), panel:None, active:None, queue:VecDeque::new(), pending:String::new(), status:String::new(), history:Vec::new(), history_cursor:0, history_draft:Input::default(), quitting:false, no_index };
        let initialized=tui.request("initialize",json!({})).await?["state"].clone();
        let selected=session.filter(|id|!id.is_empty()).or_else(|| initialized["sessions"]["current_session_id"].as_str().filter(|id|!id.is_empty()).map(str::to_owned));
        tui.session=if let Some(session)=selected { tui.request("getSession",json!({"sessionId":session})).await?; session } else { tui.request("createSession",json!({})).await?["session"]["id"].as_str().ok_or("Conversation was not created.")?.into() };
        tui.refresh().await?;
        tui.screen.print(&format!("Reverie CLI {VERSION}\n{}\nUse /help for commands. Conversation history remains in terminal scrollback.",tui.host.project_root()?.display()))?;
        tui.show_history().await?;
        let result=tui.loop_events().await;
        tui.host.cancel_all();
        if let Some(task)=tui.active.take() { let _=task.await; }
        result
    })
}
