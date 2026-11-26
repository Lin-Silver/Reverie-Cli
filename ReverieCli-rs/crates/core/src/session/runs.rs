use super::*;
use rusqlite::{Row, types::Type};

fn task(row: &Row<'_>) -> rusqlite::Result<Value> {
    let parse = |index| {
        let text: String = row.get(index)?;
        serde_json::from_str::<Value>(&text).map_err(|error| {
            rusqlite::Error::FromSqlConversionFailure(index, Type::Text, Box::new(error))
        })
    };
    Ok(
        json!({"id":row.get::<_,String>(0)?,"session_id":row.get::<_,String>(1)?,
        "configuration_revision":row.get::<_,i64>(2)?,"configuration":parse(3)?,
        "execution_root":row.get::<_,String>(4)?,"state":row.get::<_,String>(5)?,
        "revision":row.get::<_,i64>(6)?,"result":parse(7)?,"created_at":row.get::<_,String>(8)?,
        "updated_at":row.get::<_,String>(9)?,"request":parse(10)?}),
    )
}

impl SessionStore {
    pub fn register_run(
        &mut self,
        id: &str,
        run_id: &str,
        configuration: &Value,
        configuration_revision: i64,
        execution_root: &str,
        request: &Value,
    ) -> Result<i64> {
        validate_id(id)?;
        validate_id(run_id)?;
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        if let Some(existing) = tx
            .query_row("SELECT * FROM task_runs WHERE id=?", [run_id], task)
            .optional()?
        {
            if existing["session_id"] != id
                || existing["configuration"] != *configuration
                || existing["request"] != *request
            {
                return Err("Task identity was reused with different content.".into());
            }
            return Ok(existing["revision"]
                .as_i64()
                .ok_or("Task revision is missing.")?);
        }
        if !tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM conversations WHERE id=? AND deleted=0)",
            [id],
            |row| row.get::<_, bool>(0),
        )? {
            return Err("Conversation not found.".into());
        }
        let versions: Vec<(i64,String)> = tx.prepare("SELECT revision,payload FROM configuration_versions WHERE session_id=? AND revision<=? ORDER BY revision DESC")?
            .query_map(params![id,configuration_revision], |row| Ok((row.get(0)?,row.get(1)?)))?.collect::<rusqlite::Result<_>>()?;
        let mut saved = None;
        for (revision, payload) in versions {
            if serde_json::from_str::<Value>(&payload)? == *configuration {
                saved = Some(revision);
                break;
            }
        }
        if saved.is_none() {
            let (revision, metadata): (i64, String) = tx.query_row(
                "SELECT revision,metadata FROM conversations WHERE id=? AND deleted=0",
                [id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )?;
            if revision == configuration_revision
                && serde_json::from_str::<Value>(&metadata)?["runtime_config"] == *configuration
            {
                tx.execute(
                    "INSERT OR IGNORE INTO configuration_versions VALUES (?,?,?,?)",
                    params![id, revision, serde_json::to_string(configuration)?, now()],
                )?;
                saved = Some(revision);
            }
        }
        let saved = saved.ok_or("Task configuration has no saved conversation version.")?;
        let time = now();
        tx.execute(
            "INSERT INTO task_runs VALUES (?,?,?,?,?,'queued',1,'{}',?,?,?)",
            params![
                run_id,
                id,
                saved,
                serde_json::to_string(configuration)?,
                execution_root,
                time,
                time,
                serde_json::to_string(request)?
            ],
        )?;
        tx.commit()?;
        Ok(1)
    }

    pub fn update_run(
        &mut self,
        id: &str,
        run_id: &str,
        state: &str,
        expected_revision: i64,
        execution_root: Option<&str>,
        result: Option<&Value>,
    ) -> Result<i64> {
        if ![
            "queued",
            "running",
            "stopping",
            "waiting_pause",
            "paused",
            "waiting_user",
            "verifying",
            "waiting_incorporation",
            "completed",
            "cancelled",
            "failed",
            "interrupted",
        ]
        .contains(&state)
        {
            return Err("Invalid task state.".into());
        }
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let existing = tx.query_row("SELECT t.* FROM task_runs t JOIN conversations c ON c.id=t.session_id WHERE t.id=? AND t.session_id=? AND c.deleted=0", params![run_id,id], task).optional()?.ok_or("Task or conversation not found.")?;
        if existing["revision"] != expected_revision {
            return Err("Task revision or conversation identity conflict.".into());
        }
        if ["completed", "cancelled", "failed"]
            .iter()
            .any(|state| existing["state"] == *state)
            && existing["state"] != state
        {
            return Err("A finalized task cannot return to execution.".into());
        }
        tx.execute("UPDATE task_runs SET state=?,revision=revision+1,execution_root=?,result=?,updated_at=? WHERE id=? AND session_id=?",
            params![state,execution_root.unwrap_or(existing["execution_root"].as_str().ok_or("Execution root is missing.")?),
                serde_json::to_string(result.unwrap_or(&existing["result"]))?,now(),run_id,id])?;
        if [
            "completed",
            "failed",
            "waiting_user",
            "waiting_incorporation",
        ]
        .contains(&state)
        {
            tx.execute("INSERT INTO conversation_read_states VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET unread=1", [id])?;
        }
        tx.commit()?;
        Ok(expected_revision + 1)
    }

    pub fn list_runs(&self, id: &str, limit: i64) -> Result<Vec<Value>> {
        let items = self.db.prepare("SELECT t.* FROM task_runs t JOIN conversations c ON c.id=t.session_id WHERE t.session_id=? AND c.deleted=0 ORDER BY t.created_at DESC,t.id LIMIT ?")?
            .query_map(params![id,limit.clamp(1,200)], task)?.collect::<rusqlite::Result<_>>()?;
        Ok(items)
    }

    pub fn recover_runs(&mut self, active: &[String]) -> Result<Vec<Value>> {
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let executing: Vec<String> = tx.prepare("SELECT id FROM task_runs WHERE state IN ('running','stopping','waiting_pause','paused','waiting_user','verifying')")?
            .query_map([], |row| row.get(0))?.collect::<rusqlite::Result<_>>()?;
        for id in executing.into_iter().filter(|id| !active.contains(id)) {
            super::pending::interrupt(&tx, &id)?;
            tx.execute("UPDATE task_runs SET state='interrupted',revision=revision+1,updated_at=? WHERE id=?", params![now(),id])?;
        }
        let queued = tx.prepare("SELECT t.* FROM task_runs t JOIN conversations c ON c.id=t.session_id WHERE t.state='queued' AND c.deleted=0 ORDER BY t.created_at,t.id")?
            .query_map([], task)?.collect::<rusqlite::Result<_>>()?;
        tx.commit()?;
        Ok(queued)
    }

    pub fn run_revision(&self, id: &str, run_id: &str) -> Result<i64> {
        Ok(self.db.query_row(
            "SELECT revision FROM task_runs WHERE id=? AND session_id=?",
            params![run_id, id],
            |row| row.get(0),
        )?)
    }

    pub fn set_running_state(&mut self, id: &str, run_id: &str, state: &str) -> Result<()> {
        let revision = self.run_revision(id, run_id)?;
        self.update_run(id, run_id, state, revision, None, None)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restart_marks_lost_user_questions_interrupted_without_replaying_them() {
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
                "question",
                &configuration,
                page.revision,
                "project",
                &json!({"prompt":"ask first"}),
            )
            .unwrap();
        store
            .update_run(&page.id, "question", "waiting_user", 1, None, None)
            .unwrap();
        assert!(store.recover_runs(&["question".into()]).unwrap().is_empty());
        assert_eq!(
            store.list_runs(&page.id, 60).unwrap()[0]["state"],
            "waiting_user"
        );
        assert!(store.recover_runs(&[]).unwrap().is_empty());
        assert_eq!(
            store.list_runs(&page.id, 60).unwrap()[0]["state"],
            "interrupted"
        );
    }

    #[test]
    fn queued_runs_preserve_content_revisions_and_resume_only_without_effects() {
        let dir = tempfile::tempdir().unwrap();
        let mut store = SessionStore::open(dir.path(), dir.path()).unwrap();
        let configuration = json!({"settings":{},"rules":"原文\r\n😀"});
        let page = store
            .create(
                None,
                Map::from_iter([("runtime_config".into(), configuration.clone())]),
            )
            .unwrap();
        let request = json!({"prompt":"keep original"});
        assert_eq!(
            store
                .register_run(
                    &page.id,
                    "queued",
                    &configuration,
                    page.revision,
                    "project",
                    &request
                )
                .unwrap(),
            1
        );
        assert_eq!(
            store
                .register_run(
                    &page.id,
                    "queued",
                    &configuration,
                    page.revision,
                    "project",
                    &request
                )
                .unwrap(),
            1
        );
        assert!(
            store
                .register_run(
                    &page.id,
                    "queued",
                    &configuration,
                    page.revision,
                    "project",
                    &json!({"prompt":"different"})
                )
                .is_err()
        );
        assert!(
            store
                .register_run(
                    &page.id,
                    "unsaved",
                    &json!({}),
                    page.revision,
                    "project",
                    &request
                )
                .is_err()
        );
        assert_eq!(
            store
                .update_run(&page.id, "queued", "running", 1, None, None)
                .unwrap(),
            2
        );
        assert!(
            store
                .update_run(&page.id, "queued", "cancelled", 1, None, None)
                .is_err()
        );
        store
            .register_run(
                &page.id,
                "untouched",
                &configuration,
                page.revision,
                "project",
                &request,
            )
            .unwrap();
        assert_eq!(
            store.recover_runs(&["queued".into()]).unwrap()[0]["id"],
            "untouched"
        );
        assert_eq!(
            store
                .list_runs(&page.id, 60)
                .unwrap()
                .iter()
                .find(|run| run["id"] == "queued")
                .unwrap()["state"],
            "running"
        );
        assert_eq!(store.recover_runs(&[]).unwrap().len(), 1);
        assert_eq!(
            store
                .list_runs(&page.id, 60)
                .unwrap()
                .iter()
                .find(|run| run["id"] == "queued")
                .unwrap()["state"],
            "interrupted"
        );
        store
            .update_run(&page.id, "untouched", "cancelled", 1, None, None)
            .unwrap();
        assert!(
            store
                .update_run(&page.id, "untouched", "running", 2, None, None)
                .is_err()
        );
        assert_eq!(store.page(&page.id, None, 60).unwrap().total, 0);
    }
}
