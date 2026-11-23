use super::{PanelKind, Tui};
use reverie_core::Result;
use reverie_protocol::Reply;
use serde_json::{Value, json};

impl Tui {
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
            let result = self
                .request(
                    "stopContextOperation",
                    json!({"operationId":self.background_id}),
                )
                .await;
            if result.is_err()
                && self
                    .background
                    .as_ref()
                    .is_some_and(|task| !task.is_finished())
            {
                return result.map(|_| ());
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
            Some("stop"|"cancel")=>self.stop_context_operation().await?,
            Some("watch")=>{
                let enabled=match args.get(1).map(String::as_str) {Some("on")=>true,Some("off")=>false,_=>return Err("Use /context watch on or /context watch off.".into())};
                self.request("setSetting",json!({"key":"auto_index","value":enabled})).await?;
                self.screen.print(if enabled {"Automatic context updates enabled."} else {"Automatic context updates paused."})?;
            }
            Some("help")=>self.screen.print("/context status · index · semantic · warm · unload · rollback · disable · stop\n/context watch on|off\n/context install <bundle-directory> <manifest-sha256> [cpu|cuda|direct_ml|core_ml]\n/context select <manifest-sha256> [device]\n/context remove <manifest-sha256> (asks before removal)\n/context search <query> (auto hybrid when resources and index are ready)")?,
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
