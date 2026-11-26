use super::{KernelHost, Run, RunControl, approval::Approval, lock};
use crate::{Result, approval_review::ReviewOutcome, permissions, provider::ToolCall};
use reverie_platform::ToolResult;
use serde_json::{Value, json};
use std::collections::VecDeque;

pub(super) struct PendingCall {
    approval: Approval,
    call: ToolCall,
    args: Value,
    pub(super) event_id: String,
    pub(super) message: Value,
}

impl PendingCall {
    pub(super) fn approval_id(&self) -> String {
        self.approval.id.clone()
    }
    pub(super) fn call(&self) -> &ToolCall {
        &self.call
    }
}

impl KernelHost {
    #[allow(clippy::too_many_arguments)]
    pub(super) async fn start_tool(
        &self,
        run: &Run,
        control: &RunControl,
        call: &ToolCall,
        args: &Value,
        review: Option<&ReviewOutcome>,
        pending: &mut VecDeque<PendingCall>,
        emit: &impl Fn(Value),
    ) -> Result<ToolResult> {
        if pending.iter().any(|p| {
            p.args == *args
                && (p.call.name == call.name
                    || reverie_platform::command::is_command(&p.call.name)
                        && reverie_platform::command::is_command(&call.name))
        }) {
            return Err("An identical tool call is already awaiting a human decision. Continue independent work.".into());
        }
        if let Some(mut approval) = self.approval(run, control, call, args, review)? {
            if permissions::mode(&run.config["security"]) == "auto" {
                if pending.is_empty() {
                    approval.present(control, emit)?;
                }
                let mut result = ToolResult::not_started(
                    "Awaiting human approval. Continue independent work without repeating this call. Its actual result will replace this pending status.",
                );
                result.status = "pending_approval".into();
                result.data["approval_id"] = json!(approval.id);
                pending.push_back(PendingCall {
                    approval,
                    call: call.clone(),
                    args: args.clone(),
                    event_id: String::new(),
                    message: Value::Null,
                });
                return Ok(result);
            }
            approval.present(control, emit)?;
            let answer = approval
                .answer(run, control, true)
                .await?
                .ok_or("Missing human decision.")?;
            emit(json!({"type":"run.control","state":"running"}));
            self.validate_pending(run, call, args, &approval)?;
            approval.apply(run, control, &answer)?;
        }
        self.tool(run, control, call, args, emit).await
    }

    pub(super) async fn advance_approvals(
        &self,
        run: &mut Run,
        control: &RunControl,
        pending: &mut VecDeque<PendingCall>,
        wait: bool,
        emit: &impl Fn(Value),
    ) -> Result<()> {
        while let Some(front) = pending.front_mut() {
            let approval = &mut front.approval;
            let decision = if !approval.presented() && run.has_grant(&approval.key)? {
                Ok(())
            } else {
                approval.present(control, emit)?;
                match approval.answer(run, control, wait).await? {
                    Some(answer) => self
                        .validate_pending(run, &front.call, &front.args, approval)
                        .and_then(|()| approval.apply(run, control, &answer)),
                    None => break,
                }
            };
            let mut current = pending.pop_front().unwrap();
            let index = run
                .messages
                .iter()
                .position(|m| *m == current.message)
                .ok_or("Pending tool result is missing from the active turn.")?;
            let result = match decision.and_then(|()| {
                self.validate_pending(run, &current.call, &current.args, &current.approval)
            }) {
                Ok(()) => {
                    let mut executing = current.message.clone();
                    let mut content: ToolResult = serde_json::from_str(
                        executing["content"]
                            .as_str()
                            .ok_or("Missing pending content.")?,
                    )?;
                    content.status = "approval_delivering".into();
                    content.data["delivery"] = json!("unknown");
                    content.error = None;
                    executing["content"] = json!(serde_json::to_string(&content)?);
                    lock(&run.store)?.resolve_pending_tool(
                        &run.session,
                        &current.event_id,
                        &current.message,
                        &executing,
                    )?;
                    current.message = executing;
                    self.tool(run, control, &current.call, &current.args, emit)
                        .await
                }
                Err(e) => Err(e),
            };
            let (message, activity) = Self::tool_message(run, control, &current.call, result)?;
            lock(&run.store)?.resolve_pending_tool(
                &run.session,
                &current.event_id,
                &current.message,
                &message,
            )?;
            run.messages[index] = message;
            run.tool_activity(activity, emit);
            emit(json!({"type":"run.control","state":"running","approval_id":current.approval.id}));
        }
        Ok(())
    }

    pub(super) fn tool_message(
        run: &mut Run,
        control: &RunControl,
        call: &ToolCall,
        result: Result<ToolResult>,
    ) -> Result<(Value, Value)> {
        let mut result = match result {
            Ok(result) => result,
            Err(error) if control.cancel.is_cancelled() => ToolResult::not_started(error),
            Err(error) => ToolResult::fail(error),
        };
        if reverie_platform::command::is_command(&call.name)
            && result.status != "pending_approval"
            && (result.data["delivery"].is_null()
                || result.status == "cancelled" && result.data["delivery"] == "not_started")
        {
            result.data["delivery"] = json!("not_started");
            let arguments = serde_json::from_str::<Value>(&call.arguments).unwrap_or(Value::Null);
            if let Err(error) = reverie_platform::command::audit(
                &run.data,
                json!({"event":"command_blocked","allowed":false,"command":arguments["command"],"cwd":arguments["cwd"],"run_id":run.id,"session_id":run.session,"reason":result.error,"delivery":"not_started"}),
            ) {
                result.data["audit_error"] = json!(error.to_string());
            }
        }
        let activity = json!({"event":"tool_result","type":"tool_result","tool_name":call.name,"tool_call_id":call.id,"success":result.success,"output":result.output,"error":result.error,"status":result.status,"data":result.data});
        Ok((
            json!({"role":"tool","tool_call_id":call.id,"name":call.name,"content":serde_json::to_string(&result)?}),
            activity,
        ))
    }
}

impl Run {
    pub(super) fn tool_activity(&mut self, activity: Value, emit: &impl Fn(Value)) {
        emit(json!({"type":"ui.event","event":activity}));
        self.activities.push(activity);
    }
}
