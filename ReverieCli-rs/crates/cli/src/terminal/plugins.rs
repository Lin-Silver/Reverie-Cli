use super::{PanelKind, Tui, display_text};
use reverie_core::Result;
use reverie_protocol::Reply;
use serde_json::{Value, json};

impl Tui {
    pub(super) fn start_plugin_operation(&mut self, action: &str, payload: Value) -> Result<()> {
        if self.background.is_some() {
            return Err(
                "A background operation is active. Stop it before changing another extension."
                    .into(),
            );
        }
        let pending = self.host.begin_plugin_operation(action, &payload)?;
        self.background_id = format!("plugin:{}", pending.operation_id);
        let host = self.host.clone();
        let sink = self.sink.clone();
        self.background = Some(tokio::spawn(async move {
            host.complete_plugin_operation(json!("terminal-plugin"), pending, sink)
                .await
        }));
        self.status = format!("Plugin {action} · /plugins stop");
        Ok(())
    }

    pub(super) fn print_plugin_reply(&mut self, reply: &Reply) -> Result<()> {
        let id = reply.fields["plugin_id"].as_str().unwrap_or_default();
        if reply.kind == "plugin.prepared" {
            self.screen.print(&display_text(&format!(
                "Plugin candidate prepared: {id}\n{}\nReview with /plugins activate {id} {}. Activation, trust and enable are separate actions.",
                serde_json::to_string_pretty(&reply.fields["candidate"])?,
                reply.fields["candidate"]["sha256"].as_str().unwrap_or_default()
            )))?;
        } else {
            let record = reply.fields["plugins"]["records"]
                .as_array()
                .and_then(|records| records.iter().find(|record| record["id"] == id));
            self.screen.print(&display_text(&format!(
                "Plugin state updated: {id}\n{}",
                serde_json::to_string_pretty(&record)?
            )))?;
        }
        Ok(())
    }

    async fn review_plugin(
        &mut self,
        operation: &str,
        id: &str,
        requested_hash: Option<&str>,
    ) -> Result<()> {
        let root = self.host.project_root()?.to_string_lossy().into_owned();
        let inspection = self
            .request("inspectPlugin", json!({"pluginId":id,"projectRoot":root}))
            .await?;
        let record = &inspection["record"];
        let hash = match operation {
            "activate" => {
                requested_hash.ok_or("Supply the candidate SHA-256 from /plugins inspect.")?
            }
            "rollback" => record["previous_sha256"]
                .as_str()
                .filter(|value| !value.is_empty())
                .ok_or("No previous version is available.")?,
            "remove" => "",
            _ => record["active_sha256"]
                .as_str()
                .filter(|value| !value.is_empty())
                .ok_or("Activate a verified version before trusting or enabling Hooks.")?,
        };
        let candidate = if operation == "remove" {
            Value::Null
        } else {
            record["candidates"]
                .as_array()
                .and_then(|versions| versions.iter().find(|version| version["sha256"] == hash))
                .or_else(|| {
                    (inspection["active"]["sha256"] == hash).then_some(&inspection["active"])
                })
                .cloned()
                .ok_or("The requested version is not an inspected candidate.")?
        };
        if operation == "hooks"
            && !candidate["components"]
                .as_array()
                .is_some_and(|components| {
                    components
                        .iter()
                        .any(|component| component["kind"] == "hook")
                })
        {
            return Err("This active version has no inspected Hooks.".into());
        }
        self.screen.print(&display_text(&format!(
            "Inspected plugin: {}\n{}",
            record["name"].as_str().unwrap_or(id),
            serde_json::to_string_pretty(if operation == "remove" {
                record
            } else {
                &candidate
            })?
        )))?;
        let changed = record["trusted"] == true
            && candidate["approval_profile_sha256"]
                != inspection["active"]["approval_profile_sha256"];
        if changed && matches!(operation, "activate" | "rollback") {
            self.screen.print(&display_text(&format!(
                "Execution profile changed. Current profile:\n{}\nCandidate profile:\n{}",
                serde_json::to_string_pretty(&inspection["active"]["approval"])?,
                serde_json::to_string_pretty(&candidate["approval"])?
            )))?;
        }
        let mut payload =
            json!({"pluginId":id,"projectRoot":root,"expected_revision":inspection["revision"]});
        let action = match operation {
            "activate" => {
                payload = json!({"plugin_id":id,"projectRoot":root,"candidate_sha256":hash,"expected_revision":inspection["revision"]});
                if candidate["approval_required"] == true {
                    payload["approved_sha256"] = json!(hash);
                }
                if changed {
                    payload["approved_profile_sha256"] =
                        candidate["approval_profile_sha256"].clone();
                }
                "activatePlugin"
            }
            "trust" => {
                payload["trusted"] = json!(true);
                payload["candidate_sha256"] = json!(hash);
                payload["approval_profile_sha256"] = candidate["approval_profile_sha256"].clone();
                "setPluginTrust"
            }
            "hooks" => {
                payload["hooks_enabled"] = json!(true);
                payload["approval_profile_sha256"] = candidate["approval_profile_sha256"].clone();
                "setPluginHooks"
            }
            "rollback" => {
                if changed {
                    payload["approval_profile_sha256"] =
                        candidate["approval_profile_sha256"].clone();
                }
                "rollbackPlugin"
            }
            "remove" => {
                payload["confirmed"] = json!(true);
                "removePlugin"
            }
            _ => return Err("Unknown extension review operation.".into()),
        };
        self.panel(PanelKind::PluginConfirmation, format!("Confirm {operation} for {}?\nApprove only the inspected content, entries and execution profile above.", record["name"].as_str().unwrap_or(id)), vec!["Cancel".into(),"Confirm inspected operation".into()], json!({"action":action,"payload":payload}), false);
        Ok(())
    }

    pub(super) async fn plugins_command(&mut self, args: &[String]) -> Result<()> {
        match args.first().map(String::as_str).unwrap_or("list") {
            "list"|"refresh" => {
                let action = if args.first().is_some_and(|value| value == "refresh") {"refreshPlugins"} else {"listPlugins"};
                let response = self.request(action,json!({})).await?;
                let records = response["plugins"]["records"].as_array();
                let mut lines = vec![format!("Plugins: {} · revision {}",records.map_or(0,Vec::len),response["plugins"]["revision"])];
                for record in records.into_iter().flatten() {
                    lines.push(format!("{} · {} · {}\n  active {} · trusted {} · enabled {} · Hooks {} · auto-update {}",record["id"].as_str().unwrap_or_default(),record["name"].as_str().unwrap_or_default(),record["status"].as_str().unwrap_or_default(),record["active_sha256"].as_str().unwrap_or_default(),record["trusted"],record["enabled"],record["hooks_enabled"],record["auto_update"]));
                }
                self.screen.print(&display_text(&lines.join("\n")))?;
            }
            "inspect"|"show" => {
                let id = args.get(1).ok_or("Supply a plugin ID from /plugins list.")?;
                let response = self.request("inspectPlugin",json!({"pluginId":id})).await?;
                self.screen.print(&display_text(&serde_json::to_string_pretty(&response)?))?;
            }
            "prepare" => {
                let kind = args.get(1).ok_or("Choose directory, archive, git or market.")?;
                if !["directory","archive","git","market"].contains(&kind.as_str()) {return Err("Choose directory, archive, git or market.".into());}
                let location = args.get(2).ok_or("Supply a quoted source location or market entry ID.")?;
                let mut source = json!({"kind":kind});
                source[if kind == "market" {"entry_id"} else {"location"}] = json!(location);
                let mut index = 3;
                while let Some(flag) = args.get(index) {
                    if flag == "--require-signature" {source["require_signature"] = json!(true);index+=1;continue;}
                    let field = match flag.as_str() {"--sha256"=>"sha256","--revision"=>"revision","--subdirectory"=>"subdirectory","--key"=>"signing_key","--endpoint" if kind == "market"=>"location",_=>return Err("Unknown prepare flag. Use /plugins help.".into())};
                    source[field] = json!(args.get(index+1).ok_or("The prepare flag requires a value.")?);index+=2;
                }
                let state = self.request("listPlugins",json!({})).await?;
                self.start_plugin_operation("preparePlugin",json!({"source":source,"expected_revision":state["plugins"]["revision"]}))?;
            }
            "update" => {
                let id = args.get(1).ok_or("Supply a plugin ID.")?;
                let state = self.request("listPlugins",json!({})).await?;
                self.start_plugin_operation("updatePlugin",json!({"pluginId":id,"expected_revision":state["plugins"]["revision"]}))?;
            }
            "activate"|"trust"|"rollback"|"remove" => {
                let id = args.get(1).ok_or("Supply a plugin ID.")?;
                self.review_plugin(&args[0],id,args.get(2).map(String::as_str)).await?;
            }
            "enable"|"disable"|"untrust"|"auto-update"|"hooks" => {
                let id = args.get(1).ok_or("Supply a plugin ID.")?;
                let enabled = if matches!(args[0].as_str(),"auto-update"|"hooks") {match args.get(2).map(String::as_str) {Some("on")=>true,Some("off")=>false,_=>return Err("Choose on or off.".into())}} else {args[0] == "enable"};
                if args[0] == "hooks" && enabled {self.review_plugin("hooks",id,None).await?;return Ok(());}
                let (action,field) = match args[0].as_str() {"enable"|"disable"=>("setPluginEnabled","enabled"),"untrust"=>("setPluginTrust","trusted"),"auto-update"=>("setPluginAutoUpdate","auto_update"),_=>("setPluginHooks","hooks_enabled")};
                let state = self.request("listPlugins",json!({})).await?;
                let root = self.host.project_root()?.to_string_lossy().into_owned();
                let mut payload=json!({"pluginId":id,"projectRoot":root,"expected_revision":state["plugins"]["revision"]});
                payload[field]=json!(enabled);
                self.start_plugin_operation(action,payload)?;
            }
            "stop" => {
                if !self.background_id.starts_with("plugin:") {return Err("No plugin operation is active in this terminal.".into());}
                self.stop_context_operation().await?;
            }
            "help" => self.screen.print("/plugins list · refresh · inspect <id>\n/plugins prepare <directory|archive|git|market> <location-or-entry>\n  [--sha256 HASH] [--revision REF] [--subdirectory PATH]\n  [--key SIGNING_KEY] [--require-signature] [--endpoint MARKET_REMOTE]\n/plugins update <id> · activate <id> <candidate-sha256>\n/plugins trust <id> · untrust <id> · enable <id> · disable <id>\n/plugins hooks <id> on|off · auto-update <id> on|off\n/plugins rollback <id> · remove <id> · stop\nPreparation never activates or trusts content. Positive trust, Hooks, activation, rollback and removal require the inspected confirmation panel.")?,
            _ => return Err("Unknown plugin command. Use /plugins help.".into()),
        }
        Ok(())
    }
}
