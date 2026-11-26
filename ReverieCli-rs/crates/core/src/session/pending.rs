use super::*;

impl SessionStore {
    pub(crate) fn resolve_pending_tool(
        &mut self,
        id: &str,
        event_id: &str,
        previous: &Value,
        result: &Value,
    ) -> Result<()> {
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        replace_message(&tx, id, event_id, previous, result)?;
        tx.commit()?;
        Ok(())
    }
}

// Update the message and its idempotency digest together; only the exact
// provisional payload may be replaced.
fn replace_message(
    tx: &rusqlite::Transaction<'_>,
    id: &str,
    event_id: &str,
    previous: &Value,
    result: &Value,
) -> Result<()> {
    let old = serde_json::to_string(previous)?;
    let new = serde_json::to_string(result)?;
    let batch_digest = |m: &Value| -> Result<String> {
        Ok(digest(&serde_json::to_string(std::slice::from_ref(m))?))
    };
    if tx.execute(
        "UPDATE conversation_events SET digest=? WHERE session_id=? AND id=? AND digest=?",
        params![batch_digest(result)?, id, event_id, batch_digest(previous)?],
    )? != 1
        || tx.execute(
            "UPDATE messages SET payload=?,digest=? WHERE session_id=? AND digest=? AND payload=?",
            params![new, digest(&new), id, digest(&old), old],
        )? != 1
    {
        return Err("Pending tool result changed before the human decision was recorded.".into());
    }
    tx.execute(
        "UPDATE conversations SET revision=revision+1,updated_at=? WHERE id=?",
        params![now(), id],
    )?;
    Ok(())
}

pub(super) fn interrupt(tx: &rusqlite::Transaction<'_>, run: &str) -> Result<()> {
    let session: String = tx.query_row(
        "SELECT session_id FROM task_runs WHERE id=?",
        [run],
        |row| row.get(0),
    )?;
    let prefix = format!("{run}:tool:");
    let candidates=tx.prepare("SELECT payload FROM messages WHERE session_id=? AND json_extract(payload,'$.role')='tool' AND instr(payload,'approval_event')>0")?
        .query_map([&session], |r|r.get::<_,String>(0))?.collect::<rusqlite::Result<Vec<_>>>()?;
    for raw in candidates {
        let previous: Value = serde_json::from_str(&raw)?;
        let Some(content) = previous["content"]
            .as_str()
            .and_then(|s| serde_json::from_str::<Value>(s).ok())
        else {
            continue;
        };
        let Some(event) = content["data"]["approval_event"]
            .as_str()
            .filter(|id| id.starts_with(&prefix))
        else {
            continue;
        };
        let mut closed = match content["status"].as_str() {
            Some("pending_approval") => reverie_platform::ToolResult::not_started(
                "Human approval expired when the run was interrupted.",
            ),
            Some("approval_delivering") => {
                let mut result = reverie_platform::ToolResult::fail(
                    "The run was interrupted after authorization; tool delivery is unknown.",
                );
                result.data = json!({"delivery":"unknown"});
                result
            }
            _ => continue,
        };
        closed.data["approval_id"] = content["data"]["approval_id"].clone();
        let mut message = previous.clone();
        message["content"] = json!(serde_json::to_string(&closed)?);
        replace_message(tx, &session, event, &previous, &message)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn interrupted_approvals_distinguish_unstarted_and_unknown_delivery() {
        let dir = tempfile::tempdir().unwrap();
        let mut store = SessionStore::open(dir.path(), dir.path()).unwrap();
        let configuration = json!({"settings":{},"rules":""});
        let page = store
            .create(
                None,
                Map::from_iter([("runtime_config".into(), configuration.clone())]),
            )
            .unwrap();
        store
            .register_run(
                &page.id,
                "interrupted",
                &configuration,
                page.revision,
                "project",
                &json!({"prompt":"test"}),
            )
            .unwrap();
        store
            .update_run(&page.id, "interrupted", "running", 1, None, None)
            .unwrap();
        for (index, state) in ["pending_approval", "approval_delivering"]
            .into_iter()
            .enumerate()
        {
            let event = format!("interrupted:tool:0:{index}");
            let content =
                json!({"status":state,"data":{"approval_event":event,"approval_id":index}});
            let message = json!({"role":"tool","name":"create_file","tool_call_id":format!("call-{index}"),"content":content.to_string()});
            store.append(&page.id, &event, &[message]).unwrap();
        }
        drop(store);
        let mut recovered = SessionStore::open(dir.path(), dir.path()).unwrap();
        recovered.recover_runs(&[]).unwrap();
        let history = recovered.history(&page.id).unwrap();
        let deliveries:Vec<_>=history.iter().map(|m|serde_json::from_str::<Value>(m["content"].as_str().unwrap()).unwrap()["data"]["delivery"].clone()).collect();
        assert_eq!(deliveries, vec![json!("not_started"), json!("unknown")]);
    }
}
