use super::{PanelKind, Tui};
use reverie_core::Result;
use reverie_protocol::Reply;
use serde_json::{Value, json};
use std::{
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

pub(super) struct RunOwner {
    project: PathBuf,
    session: String,
    id: String,
}

impl RunOwner {
    pub(super) fn payload(&self) -> Value {
        json!({"projectRoot":self.project,"sessionId":self.session,"runId":self.id})
    }
    pub(super) fn matches(&self, fields: &serde_json::Map<String, Value>) -> bool {
        fields.get("session_id").and_then(Value::as_str) == Some(self.session.as_str())
            && fields.get("run_id").and_then(Value::as_str) == Some(self.id.as_str())
            && fields
                .get("project_root")
                .and_then(Value::as_str)
                .map(PathBuf::from)
                .as_ref()
                == Some(&self.project)
    }
}

impl Tui {
    pub(super) fn new_run_owner(&self, kind: &str) -> Result<RunOwner> {
        static NEXT_RUN: AtomicU64 = AtomicU64::new(1);
        if self.session.is_empty() {
            return Err("Select a conversation first.".into());
        }
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        Ok(RunOwner {
            project: self.host.project_root()?,
            session: self.session.clone(),
            id: format!(
                "terminal-{kind}-{}-{timestamp}-{}",
                std::process::id(),
                NEXT_RUN.fetch_add(1, Ordering::Relaxed)
            ),
        })
    }
    pub(super) fn start_compaction(&mut self, focus: &str) -> Result<()> {
        if self.active.is_some() || self.background.is_some() {
            return Err("Finish or stop the active operation before compacting context.".into());
        }
        let owner = self.new_run_owner("compact")?;
        let mut payload = owner.payload();
        payload["focus"] = json!(focus);
        let pending = self.host.begin_compaction(&payload)?;
        self.background_id = format!("compact:{}", owner.id);
        self.compaction_owner = Some(owner);
        let host = self.host.clone();
        let sink = self.sink.clone();
        self.background = Some(tokio::spawn(async move {
            host.complete_compaction(json!("terminal-compact"), pending, sink)
                .await
        }));
        self.status = "Compacting context · Ctrl+C or /stop to cancel".into();
        Ok(())
    }
    pub(super) fn start_resume(&mut self) -> Result<()> {
        if self.active.is_some() || self.compaction_owner.is_some() {
            return Err("Finish or stop the active conversation operation before resuming.".into());
        }
        let owner = self.new_run_owner("resume")?;
        let mut payload = owner.payload();
        payload["noIndex"] = json!(self.no_index);
        self.screen.print("\nResuming the saved user request\n")?;
        let pending = self.host.begin_resume(&payload)?;
        self.active_owner = Some(owner);
        self.pending.clear();
        let host = self.host.clone();
        let sink = self.sink.clone();
        self.active = Some(tokio::spawn(async move {
            host.complete_prompt(json!("terminal-resume"), pending, sink)
                .await
        }));
        self.status = "Resuming saved request · Ctrl+C to stop".into();
        Ok(())
    }
    pub(super) fn context_usage_label(&self) -> String {
        if self.context_usage["max_tokens"].as_u64().unwrap_or(0) == 0 {
            return String::new();
        }
        let scope = if self.context_usage["basis"] == "native_next_request_estimate" {
            "Next request"
        } else {
            "Saved context"
        };
        format!(
            "{scope} ~{}/{} tokens ({:.0}% local estimate)",
            self.context_usage["total_tokens"].as_u64().unwrap_or(0),
            self.context_usage["max_tokens"].as_u64().unwrap_or(0),
            self.context_usage["percentage"].as_f64().unwrap_or(0.0)
        )
    }
    pub(super) fn print_compaction_reply(&mut self, reply: &Reply, owner: &RunOwner) -> Result<()> {
        if reply.kind == "error" {
            return self.print_context_reply(reply);
        }
        if reply.kind != "context.compacted" || !owner.matches(&reply.fields) {
            return Err("Compaction reply does not belong to the selected operation.".into());
        }
        self.context_usage = reply.fields.get("usage").cloned().unwrap_or(Value::Null);
        self.screen.print(
            reply
                .fields
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("Context compaction finished without changes."),
        )?;
        let usage = self.context_usage_label();
        if !usage.is_empty() {
            self.screen.print(&usage)?;
        }
        Ok(())
    }
    pub(super) fn start_context_operation(&mut self, action: &str, payload: Value) -> Result<()> {
        if self.background.is_some() {
            return Err("A Context Engine operation is already active; use /context stop.".into());
        }
        let pending = self.host.begin_context_job(action, &payload)?;
        let host = self.host.clone();
        let sink = self.sink.clone();
        self.background_id = pending.operation_id().to_owned();
        self.background = Some(tokio::spawn(async move {
            host.complete_context_job(json!("terminal-context"), pending, sink)
                .await
        }));
        self.status = "Context Engine is working · /context stop".into();
        Ok(())
    }
    pub(super) async fn stop_context_operation(&mut self) -> Result<()> {
        if self
            .background
            .as_ref()
            .is_some_and(|task| !task.is_finished())
        {
            let result = if let Some(owner) = self.compaction_owner.as_ref() {
                self.request("stopPrompt", owner.payload()).await
            } else if let Some(id) = self.background_id.strip_prefix("plugin:") {
                self.request("stopPluginOperation", json!({"operation_id":id}))
                    .await
            } else if let Some(id) = self.background_id.strip_prefix("market:") {
                self.request("stopMarketRefresh", json!({"market_id":id}))
                    .await
            } else {
                self.request(
                    "stopContextOperation",
                    json!({"operationId":self.background_id}),
                )
                .await
            };
            if result.is_err()
                && self
                    .background
                    .as_ref()
                    .is_some_and(|task| !task.is_finished())
            {
                return result.map(|_| ());
            }
            if self.compaction_owner.is_some() {
                self.status = "Stopping context compaction · preserving saved history".into();
            }
        } else {
            let state = self.request("getSemanticResources", json!({})).await?;
            let root = self.host.project_root()?.to_string_lossy().into_owned();
            if let Some(operation) = state["semantic"]["operations"]
                .as_array()
                .and_then(|operations| {
                    operations.iter().find(|operation| {
                        operation["action"] == "watchWorkspace" && operation["project_root"] == root
                    })
                })
                .and_then(|operation| operation["operation_id"].as_str())
            {
                self.request(
                    "stopContextOperation",
                    json!({"operationId":operation,"projectRoot":root}),
                )
                .await?;
            }
        }
        Ok(())
    }
    pub(super) fn print_context_reply(&mut self, reply: &Reply) -> Result<()> {
        if reply.kind == "error" {
            return self
                .screen
                .print(
                    reply
                        .fields
                        .get("error")
                        .and_then(Value::as_str)
                        .unwrap_or("Context operation failed."),
                )
                .map_err(Into::into);
        }
        if let Some(results) = reply.fields.get("results").and_then(Value::as_array) {
            self.screen.print(&format!(
                "Retrieval: {}",
                reply
                    .fields
                    .get("retrieval")
                    .and_then(|value| value["strategy"].as_str())
                    .unwrap_or("basic")
            ))?;
            for hit in results {
                self.screen.print(&format!(
                    "{}:{}-{}\n{}",
                    hit["file_path"].as_str().unwrap_or_default(),
                    hit["start_line"],
                    hit["end_line"],
                    hit["content"].as_str().unwrap_or_default()
                ))?;
            }
        } else if reply.fields.contains_key("semantic") {
            let state = &reply.fields["semantic"];
            self.screen.print(&format!(
                "Semantic resources: {}\n{}",
                state["status"].as_str().unwrap_or("on_demand"),
                serde_json::to_string_pretty(&state)?
            ))?;
            if reply.fields.get("pending_restart").and_then(Value::as_bool) == Some(true) {
                self.screen.print("Resources are disabled; restart the kernel and remove the same digest to finish removing the mapped runtime.")?;
            }
        } else {
            self.screen
                .print(&serde_json::to_string_pretty(&reply.fields)?)?;
        }
        Ok(())
    }
    pub(super) async fn context_command(&mut self, args: &[String]) -> Result<()> {
        match args.first().map(String::as_str) {
            None|Some("status")=>{
                let resources=self.request("getSemanticResources",json!({})).await?;
                self.screen.print(&serde_json::to_string_pretty(&resources)? )?;
            }
            Some("usage")=>{
                self.context_usage=self.request("getContextUsage",json!({"sessionId":self.session})).await?["usage"].clone();
                let usage=self.context_usage_label();
                self.screen.print(if usage.is_empty() {"Context usage is unavailable."} else {&usage})?;
                self.screen.print("This is a local context estimate, not the provider's API usage. Unsent input is excluded.")?;
            }
            Some("compact")=>self.start_compaction(&args[1..].join(" "))?,
            Some("stop"|"cancel")=>self.stop_context_operation().await?,
            Some("watch")=>{
                let enabled=match args.get(1).map(String::as_str) {Some("on")=>true,Some("off")=>false,_=>return Err("Use /context watch on or /context watch off.".into())};
                self.request("setSetting",json!({"key":"auto_index","value":enabled})).await?;
                self.screen.print(if enabled {"Automatic context updates enabled."} else {"Automatic context updates paused."})?;
            }
            Some("help")=>self.screen.print("/context status · usage · index · semantic · warm · unload · rollback · disable · stop\n/compact [focus] · /resume (continues the complete saved request without a new user message)\n/context watch on|off\n/context install <bundle-directory> <manifest-sha256> [cpu|cuda|direct_ml|core_ml]\n/context select <manifest-sha256> [device]\n/context remove <manifest-sha256> (asks before removal)\n/context search <query> (auto hybrid when resources and index are ready)")?,
            Some("index")=>self.start_context_operation("indexWorkspace",json!({}))?,
            Some("semantic")=>self.start_context_operation("indexSemanticWorkspace",json!({}))?,
            Some("warm")=>self.start_context_operation("warmSemanticResources",json!({}))?,
            Some("unload")=>self.start_context_operation("unloadSemanticModels",json!({}))?,
            Some("rollback")=>self.start_context_operation("rollbackSemanticResources",json!({}))?,
            Some("disable")=>self.start_context_operation("disableSemanticResources",json!({}))?,
            Some("install")=>{
                let directory=args.get(1).ok_or("Supply an offline bundle directory and its manifest SHA-256.")?;
                let digest=args.get(2).ok_or("Supply the explicit manifest SHA-256.")?;
                self.start_context_operation("installSemanticResources",json!({"directory":directory,"manifestSha256":digest,"device":args.get(3).map(String::as_str).unwrap_or("cpu")}))?;
            }
            Some("select")=>self.start_context_operation("selectSemanticResources",json!({"manifestSha256":args.get(1).ok_or("Supply a managed manifest SHA-256.")?,"device":args.get(2).map(String::as_str).unwrap_or("cpu")}))?,
            Some("remove")=>{
                if self.active.is_some()||self.background.is_some() {return Err("Finish or stop the active operation before removing semantic resources.".into());}
                let digest=args.get(1).ok_or("Supply a managed manifest SHA-256.")?;
                let state=self.request("getSemanticResources",json!({})).await?;
                self.panel(PanelKind::ContextRemoval,format!("Remove managed resources {digest}?"),vec!["Cancel".into(),"Remove resources after checking task leases".into()],json!({"manifestSha256":digest,"confirmed":true,"expectedRevision":state["semantic"]["revision"]}),false);
            }
            Some("search")=>self.start_context_operation("queryContext",json!({"query":args[1..].join(" "),"strategy":"auto"}))?,
            _=>return Err("Unknown Context Engine command; use /context help.".into()),
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn context_events_require_the_same_project_conversation_and_run() {
        let owner = RunOwner {
            project: PathBuf::from("workspace"),
            session: "conversation".into(),
            id: "compact-1".into(),
        };
        let event =
            json!({"project_root":"workspace","session_id":"conversation","run_id":"compact-1"});
        assert!(owner.matches(event.as_object().unwrap()));
        for (field, value) in [
            ("project_root", "another-workspace"),
            ("session_id", "another-conversation"),
            ("run_id", "compact-2"),
        ] {
            let mut stale = event.clone();
            stale[field] = json!(value);
            assert!(!owner.matches(stale.as_object().unwrap()));
        }
        assert!(!owner.matches(json!({}).as_object().unwrap()));
        assert_eq!(owner.payload()["runId"], "compact-1");
    }
}
