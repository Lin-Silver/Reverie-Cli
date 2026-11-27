use super::{KernelHost, Run, RunControl, lock};
use crate::{
    Result, approval_review as review, modes, permissions,
    provider::{ProviderClient, ToolCall},
};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    time::{Duration, Instant},
};
use tokio::sync::oneshot;
use uuid::Uuid;

pub(super) struct ToolPolicy {
    call: review::Call,
    key: String,
    generation: Option<String>,
    denial: Option<String>,
}

impl KernelHost {
    fn tool_policy(&self, run: &Run, call: &ToolCall, args: &Value) -> Result<ToolPolicy> {
        if !args.is_object() {
            return Err("Tool arguments must be an object.".into());
        }
        let snapshot = lock(&run.mcp)?.clone();
        let lease = snapshot
            .as_ref()
            .and_then(|snapshot| snapshot.prepare_tool(&call.name).ok());
        let mcp_read_only = lease.as_ref().map(|lease| {
            lease.tool.metadata["annotations"]["readOnlyHint"] == true
                && lease.tool.metadata["annotations"]["destructiveHint"] != true
        });
        let mcp_read = matches!(
            call.name.as_str(),
            "mcp-catalog" | "mcp-resources-read" | "mcp-prompts-get"
        );
        let mode_tool = modes::is_read_only(&call.name, args);
        let mode = run.config["mode"].as_str().unwrap_or("reverie");
        if mode == "writer"
            && mode_tool.is_none()
            && mcp_read_only != Some(true)
            && !mcp_read
            && !["userInput", "skill_lookup", "skill_search", "skills_help"]
                .contains(&call.name.as_str())
        {
            return Err("Writer uses serial_novel for source persistence; general file editors and shell tools belong to Reverie mode.".into());
        }
        if mode_tool.is_some()
            && !modes::definitions(mode).iter().any(|tool| {
                tool["function"]["name"] == call.name
                    || (tool["function"]["name"] == "serial_novel"
                        && ["novel_project", "story_project", "longform_writer"]
                            .contains(&call.name.as_str()))
            })
        {
            return Err("This tool is not available in the active conversation mode.".into());
        }
        let read_only = mode_tool
            .or(mcp_read_only)
            .or(mcp_read.then_some(true))
            .or_else(|| (call.name == "browser").then(|| args["action"] == "list"))
            .unwrap_or_else(|| {
                call.name == "userInput" || reverie_platform::is_read_only(&call.name, args)
            });
        let level = run.config["security"]["permission_level"]
            .as_str()
            .unwrap_or("full_control");
        if !["read_only", "workspace_write", "developer", "full_control"].contains(&level) {
            return Err("Invalid configured permission level.".into());
        }
        let mut described = review::describe_call(
            &call.id,
            &call.name,
            args,
            read_only,
            lease
                .as_ref()
                .is_some_and(|lease| lease.tool.metadata["annotations"]["destructiveHint"] == true),
            lease.is_some(),
        );
        if reverie_platform::command::is_command(&call.name)
            || (call.name == "file_ops" && args["operation"] == "delete")
        {
            described.prior = review::Risk::High;
        }
        let key = match lease.as_ref() {
            Some(lease) => format!(
                "{}:{}:{}",
                call.name,
                lease.configuration().fingerprint()?,
                permissions::fingerprint(&lease.tool.metadata)?
            ),
            None if reverie_platform::command::is_command(&call.name) => {
                permissions::command_key(args)?
            }
            None if call.name == "browser" && args["action"] == "upload" => "browser:upload".into(),
            None if matches!(call.name.as_str(), "mcp-resources-read" | "mcp-prompts-get") => {
                let server = args["server_id"]
                    .as_str()
                    .ok_or("MCP server_id is required.")?;
                let target = snapshot
                    .as_ref()
                    .and_then(|s| s.server_configuration(server))
                    .ok_or("MCP server was not discovered for this task.")?;
                format!("{}:{server}:{}", call.name, target.fingerprint()?)
            }
            None => call.name.clone(),
        };
        Ok(ToolPolicy {
            call: described,
            generation: lease.as_ref().map(|l| l.tool.generation.clone()),
            key,
            denial: (level == "read_only" && !read_only)
                .then(|| "Configured permission level does not allow this write tool.".into()),
        })
    }

    pub(super) async fn review_tools(
        &self,
        run: &Run,
        control: &RunControl,
        calls: &BTreeMap<usize, ToolCall>,
        client: &ProviderClient,
    ) -> Result<Option<review::ReviewOutcome>> {
        if permissions::mode(&run.config["security"]) != "auto" {
            return Ok(None);
        }
        let configuration = review::ReviewConfig {
            review_read_only: true,
            ..review::ReviewConfig::from_security(&run.config["security"])
        };
        let descriptions = calls
            .values()
            .filter_map(|call| {
                serde_json::from_str(&call.arguments)
                    .ok()
                    .and_then(|args| self.tool_policy(run, call, &args).ok())
                    .map(|policy| policy.call)
            })
            .collect::<Vec<_>>();
        let mut combined: Option<review::ReviewOutcome> = None;
        for batch in descriptions.chunks(review::MAX_BATCH_CALLS) {
            let next = self
                .review_batch(run, control, client, batch, &configuration)
                .await?;
            if let Some(first) = &mut combined {
                first.verdicts.extend(next.verdicts);
                first.batch_risk = first.batch_risk.max(next.batch_risk);
                first.elapsed_ms = first.elapsed_ms.saturating_add(next.elapsed_ms);
                first.ok &= next.ok;
                first.cancelled |= next.cancelled;
                if !next.error.is_empty() && !first.error.contains(&next.error) {
                    if !first.error.is_empty() {
                        first.error.push(' ');
                    }
                    first.error.push_str(&next.error);
                }
            } else {
                combined = Some(next);
            }
            if control.cancel.is_cancelled() {
                break;
            }
        }
        Ok(combined)
    }

    async fn review_batch(
        &self,
        run: &Run,
        control: &RunControl,
        client: &ProviderClient,
        batch: &[review::Call],
        configuration: &review::ReviewConfig,
    ) -> Result<review::ReviewOutcome> {
        let request = review::prepare(
            batch,
            &run.execution_root.to_string_lossy(),
            run.config["security"]["permission_level"]
                .as_str()
                .unwrap_or("full_control"),
            configuration,
        );
        // Nonstandard catalogs resolve through the ordinary model migration; until
        // available, the reviewer explicitly follows the actual executing model.
        let selection = review::select_model(&run.config, &run.model, configuration, None);
        let started = Instant::now();
        let cancel = control.cancel.child_token();
        let mut outcome = match selection.request_model(configuration) {
            Some(model) => {
                let settings = configuration.request_configuration(&run.config);
                let query =
                    client.chat(&model, &settings, &request.messages, &[], &cancel, &|_| {});
                tokio::select! {
                    _ = control.cancel.cancelled() => review::complete(&request, review::ReviewResult::Cancelled, review::ResponsePolicy::StrictIds),
                    result = tokio::time::timeout(Duration::from_secs(configuration.timeout), query) => match result {
                        Ok(Ok(turn)) if turn.tool_calls.is_empty() => review::complete(&request, review::ReviewResult::Text(&turn.content), review::ResponsePolicy::StrictIds),
                        Ok(Ok(_)) => review::complete(&request, review::ReviewResult::Failed("Reviewer attempted to use execution tools."), review::ResponsePolicy::StrictIds),
                        Ok(Err(_)) => review::complete(&request, review::ReviewResult::Failed("Reviewer request failed; using the configured static fallback."), review::ResponsePolicy::StrictIds),
                        Err(_) => review::complete(&request, review::ReviewResult::Failed("Reviewer request timed out; using the configured static fallback."), review::ResponsePolicy::StrictIds),
                    }
                }
            }
            None => review::complete(
                &request,
                review::ReviewResult::Failed(
                    "No available reviewer model; using the configured static fallback.",
                ),
                review::ResponsePolicy::StrictIds,
            ),
        };
        cancel.cancel();
        outcome.model_display_name = selection.display_name;
        outcome.elapsed_ms = started.elapsed().as_millis().try_into().unwrap_or(u64::MAX);
        if !selection.note.is_empty() {
            outcome.error = [outcome.error.as_str(), selection.note.as_str()]
                .into_iter()
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>()
                .join(" ");
        }
        Ok(outcome)
    }

    pub(super) fn approval(
        &self,
        run: &Run,
        control: &RunControl,
        call: &ToolCall,
        args: &Value,
        outcome: Option<&review::ReviewOutcome>,
    ) -> Result<Option<Approval>> {
        let policy = self.tool_policy(run, call, args)?;
        if control.cancel.is_cancelled() {
            return Err("Run cancelled before tool execution.".into());
        }
        if let Some(reason) = policy.denial {
            return Err(reason.into());
        }
        let mode = permissions::mode(&run.config["security"]);
        let mut risk = policy.call.prior;
        let mut source = review::VerdictSource::Policy;
        let mut concerns = Vec::new();
        let upload = call.name == "browser" && args["action"] == "upload";
        let upload_reason = || {
            format!(
                "Allow {} to receive the workspace file {}?",
                args["origin"], args["path"]
            )
        };
        let reason = match mode {
            "full_access" => return Ok(None),
            "normal" | "strict" if upload => upload_reason(),
            "normal" if !reverie_platform::command::is_command(&call.name) => return Ok(None),
            "normal" => "Normal mode requires approval for terminal commands.".to_owned(),
            "strict" => "Strict mode requires explicit approval.".to_owned(),
            "auto" => {
                let verdict = outcome.and_then(|o| o.verdicts.get(&call.id));
                if let Some(v) = verdict {
                    risk = v.risk;
                    source = v.source;
                    concerns = v.concerns.clone();
                }
                let reviewed = source == review::VerdictSource::Reviewer;
                let config = review::ReviewConfig::from_security(&run.config["security"]);
                if reviewed
                    && !verdict.is_some_and(|v| v.denied)
                    && !risk.requires_approval(config.approve_risk_at)
                {
                    if !upload {
                        return Ok(None);
                    }
                    upload_reason()
                } else {
                    let reason = verdict
                        .map(|v| v.reason.clone())
                        .filter(|s| !s.is_empty())
                        .unwrap_or_else(|| "No valid review was returned for this call.".into());
                    match permissions::fallback(&run.config["security"]) {
                        "deny" => {
                            return Err(format!("Auto review denied this call: {reason}").into());
                        }
                        "wait" => reason,
                        _ => return Err("Invalid Auto review fallback.".into()),
                    }
                }
            }
            _ => return Err("Invalid configured permission mode.".into()),
        };
        if run.has_grant(&policy.key)? {
            return Ok(None);
        }
        let id = Uuid::new_v4().simple().to_string();
        let event = json!({"type":"approval.request","approval_id":id,"tool_call_id":call.id,
            "tool":call.name,"arguments":args,"command":args["command"],"cwd":run.command_cwd(args),"execution_root":run.execution_root,
            "read_only":policy.call.read_only,"permission_mode":mode,"scopes":["once","session","project","global"],
            "paths":[args["path"]],"risk":risk,"message":reason,"concerns":concerns,"review_source":source,
            "hard_denial":false,"background":mode=="auto"});
        Ok(Some(Approval {
            id,
            key: policy.key,
            generation: policy.generation,
            event,
            receiver: None,
        }))
    }

    pub(super) fn validate_pending(
        &self,
        run: &Run,
        call: &ToolCall,
        args: &Value,
        approval: &Approval,
    ) -> Result<()> {
        let policy = self.tool_policy(run, call, args)?;
        if let Some(reason) = policy.denial {
            return Err(reason.into());
        }
        if policy.key != approval.key || policy.generation != approval.generation {
            return Err("The tool changed while waiting for approval.".into());
        }
        Ok(())
    }
}

impl Run {
    fn with_grants<T>(&self, f: impl FnOnce(&permissions::Grants) -> Result<T>) -> Result<T> {
        let mut grants = lock(&self.grants)?;
        if grants.is_none() {
            *grants = Some(permissions::Grants::open(
                &self.app,
                &self.root,
                &self.execution_root,
                &self.session,
                self.assistant,
            )?);
        }
        f(grants.as_ref().unwrap())
    }
    pub(super) fn has_grant(&self, key: &str) -> Result<bool> {
        self.with_grants(|g| g.contains(key))
    }
}

pub(super) struct Approval {
    pub(super) id: String,
    pub(super) key: String,
    generation: Option<String>,
    event: Value,
    receiver: Option<oneshot::Receiver<Value>>,
}

impl Approval {
    pub(super) fn presented(&self) -> bool {
        self.receiver.is_some()
    }
    pub(super) fn present(&mut self, control: &RunControl, emit: &impl Fn(Value)) -> Result<()> {
        if self.receiver.is_none() {
            let (sender, receiver) = oneshot::channel();
            lock(&control.approvals)?.insert(self.id.clone(), super::Waiter { sender });
            self.receiver = Some(receiver);
            emit(self.event.clone());
        }
        Ok(())
    }

    pub(super) async fn answer(
        &mut self,
        run: &Run,
        control: &RunControl,
        wait: bool,
    ) -> Result<Option<Value>> {
        let receiver = self
            .receiver
            .as_mut()
            .ok_or("Approval has not been presented.")?;
        if !wait {
            return match receiver.try_recv() {
                Ok(answer) => Ok(Some(answer)),
                Err(oneshot::error::TryRecvError::Empty) => Ok(None),
                Err(oneshot::error::TryRecvError::Closed) => {
                    Err("Approval is no longer active.".into())
                }
            };
        }
        lock(&run.store)?.set_running_state(&run.session, &run.id, "waiting_user")?;
        let result = tokio::select! {
            _=control.cancel.cancelled()=>Err("Run cancelled while waiting for approval."),
            answer=receiver=>answer.map_err(|_|"Approval is no longer active."),
        };
        lock(&control.approvals)?.remove(&self.id);
        lock(&run.store)?.set_running_state(&run.session, &run.id, "running")?;
        Ok(Some(result?))
    }

    pub(super) fn apply(&self, run: &Run, control: &RunControl, answer: &Value) -> Result<()> {
        let _commit = lock(&control.commit_gate)?;
        if control.cancel.is_cancelled() {
            return Err("Run cancelled before the approval was applied.".into());
        }
        match answer["decision"].as_str() {
            Some("once") => Ok(()),
            Some(scope @ ("session" | "project" | "global")) => {
                run.with_grants(|g| g.remember(scope, &self.key))
            }
            Some("message") => Err(format!(
                "The user declined this {} call and replied: {}",
                self.event["tool"],
                answer["message"].as_str().unwrap_or_default()
            )
            .into()),
            _ => Err("User denied the tool request.".into()),
        }
    }
}
