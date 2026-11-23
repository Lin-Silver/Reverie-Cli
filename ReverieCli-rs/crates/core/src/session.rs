use crate::{Result, config};
use chrono::Local;
use reverie_protocol::{SessionInfo, SessionPage};
use rusqlite::{Connection, OpenFlags, OptionalExtension, TransactionBehavior, params};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
    time::Duration,
};
use uuid::Uuid;

mod runs;

pub struct SessionStore {
    db: Connection,
    pub database_path: PathBuf,
    base: PathBuf,
    scope: Value,
}

pub fn now() -> String {
    Local::now()
        .naive_local()
        .format("%Y-%m-%dT%H:%M:%S%.6f")
        .to_string()
}

fn digest(value: &str) -> String {
    Sha256::digest(value.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn stored(message: &Value) -> Value {
    let mut message = message.clone();
    if message["role"] == "assistant" {
        message["role"] = json!("Reverie");
    }
    message
}

fn wire(mut message: Value) -> Value {
    if message["role"] == "Reverie" {
        message["role"] = json!("assistant");
    }
    message
}

fn validate_id(id: &str) -> Result<()> {
    if id.is_empty()
        || id.len() > 128
        || !id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
    {
        return Err("Invalid conversation identifier.".into());
    }
    Ok(())
}

impl SessionStore {
    pub fn open(base: &Path, project: &Path) -> Result<Self> {
        fs::create_dir_all(base)?;
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(base.join("conversations.initialize.lock"))?;
        lock.lock()?;
        let database_path = base.join("conversations.sqlite3");
        let existed = database_path.is_file() && database_path.metadata()?.len() > 0;
        let mut db = Connection::open(&database_path)?;
        db.busy_timeout(Duration::from_secs(10))?;
        let version: u32 = db.query_row("PRAGMA user_version", [], |row| row.get(0))?;
        if version > 7 {
            return Err("Conversation database requires a newer Reverie version.".into());
        }
        if existed {
            let backup = base.join("backups/conversations.before-rust-3.0.sqlite3");
            if !backup.exists() {
                fs::create_dir_all(backup.parent().unwrap())?;
                let staged = tempfile::NamedTempFile::new_in(backup.parent().unwrap())?;
                db.backup("main", staged.path(), rusqlite::backup::NO_PROGRESS)?;
                verify_backup(staged.path())?;
                staged.persist_noclobber(&backup).map_err(|e| e.error)?;
            }
            verify_backup(&backup)?;
        }
        db.execute_batch("PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;")?;
        if db.query_row("PRAGMA journal_mode", [], |row| row.get::<_, String>(0))? != "wal" {
            db.execute_batch("PRAGMA journal_mode=WAL;")?;
        }
        if version != 7 {
            let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
            tx.execute_batch(include_str!("schema.sql"))?;
            let columns: Vec<String> = tx
                .prepare("PRAGMA table_info(task_runs)")?
                .query_map([], |row| row.get(1))?
                .collect::<rusqlite::Result<_>>()?;
            if !columns.iter().any(|name| name == "request") {
                tx.execute_batch(
                    "ALTER TABLE task_runs ADD COLUMN request TEXT NOT NULL DEFAULT '{}';",
                )?;
            }
            tx.execute_batch("INSERT INTO message_search(message_search) VALUES ('rebuild'); INSERT INTO stream_chunks(session_id,run_id,kind,content,updated_at) SELECT session_id,run_id,kind,content,updated_at FROM stream_fragments; DELETE FROM stream_fragments;")?;
            tx.commit()?;
        }
        let mut store = Self {
            db,
            database_path,
            base: base.into(),
            scope: config::workspace_metadata(project),
        };
        store.migrate_legacy()?;
        Ok(store)
    }

    fn migrate_legacy(&mut self) -> Result<()> {
        let directory = self.base.join("sessions");
        if !directory.is_dir() {
            return Ok(());
        }
        let mut paths = fs::read_dir(directory)?
            .map(|entry| entry.map(|e| e.path()))
            .collect::<std::io::Result<Vec<_>>>()?;
        paths.sort();
        for path in paths
            .into_iter()
            .filter(|p| p.extension().is_some_and(|ext| ext == "json"))
        {
            let file_id = path
                .file_stem()
                .and_then(|name| name.to_str())
                .unwrap_or("");
            validate_id(file_id)?;
            if self
                .db
                .query_row("SELECT 1 FROM conversations WHERE id=?", [file_id], |_| {
                    Ok(())
                })
                .optional()?
                .is_some()
            {
                continue;
            }
            let bytes = fs::read(&path)?;
            let data: Value = serde_json::from_slice(&bytes)?;
            let id = data["id"]
                .as_str()
                .ok_or("Legacy conversation is missing its identifier.")?;
            validate_id(id)?;
            if id != file_id {
                return Err("Legacy conversation identity does not match its filename.".into());
            }
            let mut meta = data["metadata"].as_object().cloned().unwrap_or_default();
            if meta
                .get("workspace_id")
                .and_then(Value::as_str)
                .is_some_and(|value| {
                    !value.is_empty() && value != self.scope["workspace_id"].as_str().unwrap()
                })
            {
                continue;
            }
            if let Some(owner) = meta
                .get("workspace_path")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                && config::workspace_metadata(Path::new(owner))["workspace_id"]
                    != self.scope["workspace_id"]
            {
                continue;
            }
            meta.extend(self.scope.as_object().unwrap().clone());
            meta.entry("configuration_origin")
                .or_insert(json!("legacy-workspace-default"));
            let messages = data["messages"]
                .as_array()
                .ok_or("Legacy conversation messages must be an array.")?;
            let tx = self
                .db
                .transaction_with_behavior(TransactionBehavior::Immediate)?;
            let inserted = tx.execute("INSERT OR IGNORE INTO conversations(id,name,created_at,updated_at,metadata,revision,message_count,deleted) VALUES (?,?,?,?,?,1,?,0)", params![id, data["name"].as_str().ok_or("Legacy conversation name is missing.")?,data["created_at"].as_str().ok_or("Legacy creation time is missing.")?,data["updated_at"].as_str().ok_or("Legacy update time is missing.")?,serde_json::to_string(&meta)?,messages.len() as i64])?;
            if inserted != 0 {
                insert_messages(&tx, id, 0, messages)?;
                tx.execute(
                    "INSERT OR IGNORE INTO migrations VALUES (?,?)",
                    params![file_id, digest(&serde_json::to_string(&data)?)],
                )?;
            }
            tx.commit()?;
        }
        Ok(())
    }

    pub fn create(
        &mut self,
        name: Option<&str>,
        metadata: Map<String, Value>,
    ) -> Result<SessionPage> {
        let id = Uuid::new_v4().simple().to_string();
        let time = now();
        let mut metadata = metadata;
        metadata.extend(self.scope.as_object().unwrap().clone());
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        tx.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,1,0,0)",
            params![
                id,
                name.filter(|name| !name.trim().is_empty())
                    .unwrap_or("New conversation"),
                time,
                time,
                serde_json::to_string(&metadata)?
            ],
        )?;
        if let Some(configuration) = metadata.get("runtime_config") {
            tx.execute(
                "INSERT INTO configuration_versions VALUES (?,1,?,?)",
                params![id, serde_json::to_string(configuration)?, time],
            )?;
        }
        tx.execute(
            "INSERT OR REPLACE INTO navigation VALUES ('selected',?)",
            [&id],
        )?;
        tx.commit()?;
        self.page(&id, None, 60)
    }

    pub fn page(&mut self, id: &str, before: Option<i64>, limit: i64) -> Result<SessionPage> {
        validate_id(id)?;
        let tx = self.db.transaction()?;
        let mut page = tx.query_row("SELECT id,name,created_at,updated_at,metadata,revision,message_count FROM conversations WHERE id=? AND deleted=0", [id], |row| {
            Ok((row.get::<_, String>(0)?,row.get::<_, String>(1)?,row.get::<_, String>(2)?,row.get::<_, String>(3)?,row.get::<_, String>(4)?,row.get::<_, i64>(5)?,row.get::<_, i64>(6)?))
        }).optional()?.ok_or("Conversation not found.")?;
        let end = before.unwrap_or(page.6).clamp(0, page.6);
        let start = end.saturating_sub(limit.clamp(1, 200));
        let payloads: Vec<String> = tx.prepare("SELECT payload FROM messages WHERE session_id=? AND sequence>=? AND sequence<? ORDER BY sequence")?.query_map(params![id,start,end], |row| row.get(0))?.collect::<rusqlite::Result<_>>()?;
        let metadata: Map<String, Value> = serde_json::from_str(&page.4)?;
        let messages = payloads
            .into_iter()
            .map(|payload| serde_json::from_str(&payload).map(wire))
            .collect::<serde_json::Result<_>>()?;
        tx.commit()?;
        Ok(SessionPage {
            id: std::mem::take(&mut page.0),
            name: page.1,
            created_at: page.2,
            updated_at: page.3,
            metadata,
            revision: page.5,
            messages,
            total: page.6,
            before: (start > 0).then_some(start),
            interrupted_streams: self.streams(id)?,
        })
    }

    pub fn list(&self) -> Result<Value> {
        let items: Vec<SessionInfo> = self.db.prepare("SELECT id,name,created_at,updated_at,message_count FROM conversations WHERE deleted=0 ORDER BY updated_at DESC,id")?.query_map([], |row| Ok(SessionInfo { id:row.get(0)?, name:row.get(1)?, created_at:row.get(2)?, updated_at:row.get(3)?,message_count:row.get(4)? }))?.collect::<rusqlite::Result<_>>()?;
        let selected: Option<String> = self
            .db
            .query_row(
                "SELECT value FROM navigation WHERE key='selected'",
                [],
                |row| row.get(0),
            )
            .optional()?
            .flatten();
        let mut archive = Map::new();
        let mut owners = Map::new();
        for item in &items {
            let meta: String = self.db.query_row(
                "SELECT metadata FROM conversations WHERE id=?",
                [&item.id],
                |row| row.get(0),
            )?;
            let meta: Value = serde_json::from_str(&meta)?;
            if let Some(value) = meta.get("archived") {
                archive.insert(item.id.clone(), value.clone());
            }
            let mut owner = Map::new();
            for (key, source) in [
                ("assistant_id", "assistant_id"),
                ("workspace", "workspace_path"),
            ] {
                if let Some(value) = meta.get(source) {
                    owner.insert(key.into(), value.clone());
                }
            }
            owners.insert(item.id.clone(), json!(owner));
        }
        let unread: Vec<String> = self.db.prepare("SELECT r.session_id FROM conversation_read_states r JOIN conversations c ON c.id=r.session_id WHERE r.unread=1 AND c.deleted=0")?.query_map([], |row| row.get(0))?.collect::<rusqlite::Result<_>>()?;
        Ok(
            json!({"current_session_id":selected.unwrap_or_default(),"items":items,"archive_states":archive,"owners":owners,"unread_session_ids":unread}),
        )
    }

    pub fn select(&self, id: &str) -> Result<()> {
        if self
            .db
            .query_row(
                "SELECT 1 FROM conversations WHERE id=? AND deleted=0",
                [id],
                |_| Ok(()),
            )
            .optional()?
            .is_none()
        {
            return Err("Conversation not found.".into());
        }
        self.db.execute(
            "INSERT OR REPLACE INTO navigation VALUES ('selected',?)",
            [id],
        )?;
        self.mark_read(id)
    }

    pub fn mark_read(&self, id: &str) -> Result<()> {
        self.db.execute(
            "UPDATE conversation_read_states SET unread=0 WHERE session_id=?",
            [id],
        )?;
        Ok(())
    }

    pub fn update_metadata(
        &mut self,
        id: &str,
        changes: Map<String, Value>,
        expected: i64,
    ) -> Result<i64> {
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let (encoded, revision): (String, i64) = tx.query_row(
            "SELECT metadata,revision FROM conversations WHERE id=? AND deleted=0",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )?;
        if revision != expected {
            return Err(
                "Conversation revision conflict; reload before changing configuration.".into(),
            );
        }
        let mut metadata: Map<String, Value> = serde_json::from_str(&encoded)?;
        metadata.extend(changes.clone());
        metadata.extend(self.scope.as_object().unwrap().clone());
        let time = now();
        tx.execute(
            "UPDATE conversations SET metadata=?,revision=revision+1,updated_at=? WHERE id=?",
            params![serde_json::to_string(&metadata)?, time, id],
        )?;
        if let Some(configuration) = changes.get("runtime_config") {
            tx.execute(
                "INSERT INTO configuration_versions VALUES (?,?,?,?)",
                params![
                    id,
                    revision + 1,
                    serde_json::to_string(configuration)?,
                    time
                ],
            )?;
        }
        tx.commit()?;
        Ok(revision + 1)
    }

    pub fn rename(&self, id: &str, name: &str) -> Result<()> {
        if name.trim().is_empty() {
            return Err("Session name is required.".into());
        }
        if self.db.execute("UPDATE conversations SET name=?,revision=revision+1,updated_at=? WHERE id=? AND deleted=0",params![name.trim(),now(),id])? == 0 { return Err("Conversation not found.".into()); }
        Ok(())
    }

    pub fn append(&mut self, id: &str, event_id: &str, messages: &[Value]) -> Result<()> {
        let encoded = serde_json::to_string(messages)?;
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let previous: Option<(String, String)> = tx
            .query_row(
                "SELECT session_id,digest FROM conversation_events WHERE id=?",
                [event_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        if let Some((owner, hash)) = previous {
            if owner != id || hash != digest(&encoded) {
                return Err("Conversation event identity conflict.".into());
            }
            return Ok(());
        }
        let count: i64 = tx
            .query_row(
                "SELECT message_count FROM conversations WHERE id=? AND deleted=0",
                [id],
                |row| row.get(0),
            )
            .optional()?
            .ok_or("Conversation was deleted; a stale executor cannot restore it.")?;
        insert_messages(&tx, id, count, messages)?;
        tx.execute("UPDATE conversations SET message_count=message_count+?,revision=revision+1,updated_at=? WHERE id=?",params![messages.len() as i64,now(),id])?;
        tx.execute(
            "INSERT INTO conversation_events VALUES (?,?,?)",
            params![event_id, id, digest(&encoded)],
        )?;
        tx.commit()?;
        Ok(())
    }

    pub fn delete(&mut self, id: &str) -> Result<()> {
        if id == "aio-mainline" {
            return Err("The persistent AiO mainline cannot be deleted.".into());
        }
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        if tx.execute(
            "UPDATE conversations SET deleted=1,revision=revision+1 WHERE id=? AND deleted=0",
            [id],
        )? == 0
        {
            return Err("Conversation not found.".into());
        }
        tx.execute(
            "UPDATE navigation SET value=NULL WHERE key='selected' AND value=?",
            [id],
        )?;
        tx.commit()?;
        Ok(())
    }

    pub fn write_stream(&self, id: &str, run_id: &str, kind: &str, content: &str) -> Result<()> {
        self.db.execute("INSERT INTO stream_chunks(session_id,run_id,kind,content,updated_at) VALUES (?,?,?,?,?)",params![id,run_id,kind,content,now()])?;
        Ok(())
    }

    pub fn history(&self, id: &str) -> Result<Vec<Value>> {
        let metadata: String = self
            .db
            .query_row(
                "SELECT metadata FROM conversations WHERE id=? AND deleted=0",
                [id],
                |row| row.get(0),
            )
            .optional()?
            .ok_or("Conversation not found.")?;
        let metadata: Value = serde_json::from_str(&metadata)?;
        let start = metadata["active_context_start"]
            .as_i64()
            .unwrap_or(0)
            .max(0);
        let payloads: Vec<String> = self
            .db
            .prepare(
                "SELECT payload FROM messages WHERE session_id=? AND sequence>=? ORDER BY sequence",
            )?
            .query_map(params![id, start], |row| row.get(0))?
            .collect::<rusqlite::Result<_>>()?;
        Ok(payloads
            .into_iter()
            .map(|payload| serde_json::from_str::<Value>(&payload).map(wire))
            .collect::<serde_json::Result<_>>()?)
    }

    pub fn begin_run(
        &mut self,
        id: &str,
        run_id: &str,
        configuration: &Value,
        configuration_revision: i64,
        request: &Value,
        user: &Value,
    ) -> Result<()> {
        let time = now();
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let count: i64 = tx
            .query_row(
                "SELECT message_count FROM conversations WHERE id=? AND deleted=0",
                [id],
                |row| row.get(0),
            )
            .optional()?
            .ok_or("Conversation not found.")?;
        let existing: Option<(String, String, String, String)> = tx
            .query_row(
                "SELECT session_id,configuration,state,request FROM task_runs WHERE id=?",
                [run_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .optional()?;
        let mut request = request.clone();
        request["_native_started"] = json!(true);
        if let Some((owner, encoded, state, original)) = existing {
            let original: Value = serde_json::from_str(&original)?;
            if owner != id
                || serde_json::from_str::<Value>(&encoded)? != *configuration
                || !["queued", "running"].contains(&state.as_str())
                || original["_native_started"] == true
                || original["prompt"] != user["content"]
            {
                return Err("Task is already started or its queued content differs.".into());
            }
            tx.execute(
                "UPDATE task_runs SET state='running',request=?,updated_at=? WHERE id=?",
                params![serde_json::to_string(&request)?, time, run_id],
            )?;
        } else {
            tx.execute("INSERT INTO task_runs(id,session_id,configuration_revision,configuration,execution_root,state,revision,result,created_at,updated_at,request) VALUES (?,?,?,?,?,'running',1,'{}',?,?,?)",params![run_id,id,configuration_revision,serde_json::to_string(configuration)?,request["executionRoot"].as_str().unwrap_or(self.scope["workspace_path"].as_str().ok_or("Workspace identity is missing.")?),time,time,serde_json::to_string(&request)?])?;
        }
        insert_messages(&tx, id, count, std::slice::from_ref(user))?;
        tx.execute("UPDATE conversations SET message_count=message_count+1,revision=revision+1,updated_at=? WHERE id=?",params![time,id])?;
        tx.commit()?;
        Ok(())
    }

    pub fn finish_run(
        &mut self,
        id: &str,
        run_id: &str,
        state: &str,
        result: &Value,
    ) -> Result<()> {
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let request: String = tx.query_row(
            "SELECT request FROM task_runs WHERE id=? AND session_id=?",
            params![run_id, id],
            |row| row.get(0),
        )?;
        let task_state = if state == "completed"
            && serde_json::from_str::<Value>(&request)?["hostManaged"] == true
        {
            "verifying"
        } else {
            state
        };
        if tx.execute("UPDATE task_runs SET state=?,result=?,revision=revision+1,updated_at=? WHERE id=? AND session_id=? AND state NOT IN ('completed','cancelled','failed')",params![task_state,serde_json::to_string(result)?,now(),run_id,id])? == 0 {return Err("Task is missing or already finalized.".into());}
        tx.execute("INSERT INTO conversation_read_states VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET unread=1",[id])?;
        if state == "completed" {
            tx.execute(
                "DELETE FROM stream_chunks WHERE session_id=? AND run_id=?",
                params![id, run_id],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    pub fn clear_stream(&self, id: &str, run_id: &str) -> Result<()> {
        self.db.execute(
            "DELETE FROM stream_chunks WHERE session_id=? AND run_id=?",
            params![id, run_id],
        )?;
        Ok(())
    }

    fn streams(&self, id: &str) -> Result<Vec<Value>> {
        let rows: Vec<(String,String,String,String)> = self.db.prepare("SELECT run_id,kind,content,updated_at FROM stream_chunks WHERE session_id=? ORDER BY sequence")?.query_map([id], |row| Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?)))?.collect::<rusqlite::Result<_>>()?;
        let mut streams: Vec<Value> = Vec::new();
        for (run, kind, content, time) in rows {
            if let Some(stream) = streams
                .iter_mut()
                .find(|s| s["run_id"] == run && s["kind"] == kind)
            {
                let joined = format!(
                    "{}{}",
                    stream["content"].as_str().unwrap_or_default(),
                    content
                );
                stream["content"] = json!(joined);
                stream["updated_at"] = json!(time);
            } else {
                streams.push(json!({"session_id":id,"run_id":run,"kind":kind,"content":content,"updated_at":time,"interrupted":true}));
            }
        }
        Ok(streams)
    }
}

fn insert_messages(db: &Connection, id: &str, start: i64, messages: &[Value]) -> Result<()> {
    let mut insert = db.prepare("INSERT INTO messages VALUES (?,?,?,?,?)")?;
    for (offset, message) in messages.iter().enumerate() {
        let payload = serde_json::to_string(&stored(message))?;
        insert.execute(params![
            id,
            start + offset as i64,
            Uuid::new_v4().simple().to_string(),
            payload,
            digest(&payload)
        ])?;
    }
    Ok(())
}

fn verify_backup(path: &Path) -> Result<()> {
    let backup = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    if backup.query_row("PRAGMA quick_check", [], |row| row.get::<_, String>(0))? != "ok" {
        return Err("Conversation backup failed integrity validation.".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restart_paging_roles_events_and_deleted_sessions_keep_transcript_integrity() {
        let dir = tempfile::tempdir().unwrap();
        let mut store = SessionStore::open(dir.path(), dir.path()).unwrap();
        let page = store.create(Some("中文😀"), Map::new()).unwrap();
        let messages: Vec<Value> = (0..73).map(|i| json!({"role":"assistant","content":format!("{i}\n正文😀\n"),"unknown":{"nested":true}})).collect();
        store.append(&page.id, "first", &messages).unwrap();
        store.append(&page.id, "first", &messages).unwrap();
        assert!(
            store
                .append(&page.id, "first", &[json!({"content":"conflict"})])
                .is_err()
        );
        let raw: String = store
            .db
            .query_row("SELECT payload FROM messages LIMIT 1", [], |row| row.get(0))
            .unwrap();
        assert_eq!(
            serde_json::from_str::<Value>(&raw).unwrap()["role"],
            "Reverie"
        );
        drop(store);
        let mut store = SessionStore::open(dir.path(), dir.path()).unwrap();
        let tail = store.page(&page.id, None, 60).unwrap();
        assert_eq!(tail.total, 73);
        assert_eq!(tail.before, Some(13));
        assert_eq!(tail.messages, messages[13..]);
        assert_eq!(
            store.page(&page.id, tail.before, 60).unwrap().messages,
            messages[..13]
        );
        let backup = Connection::open(
            dir.path()
                .join("backups/conversations.before-rust-3.0.sqlite3"),
        )
        .unwrap();
        assert_eq!(
            backup
                .query_row("SELECT count(*) FROM messages", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            73
        );
        store.delete(&page.id).unwrap();
        assert!(store.append(&page.id, "stale", &messages).is_err());
        assert!(store.page(&page.id, None, 60).is_err());
    }

    #[test]
    fn metadata_conflicts_and_other_conversations_do_not_rewrite_message_bytes_or_selection() {
        let dir = tempfile::tempdir().unwrap();
        let mut store = SessionStore::open(dir.path(), dir.path()).unwrap();
        let first = store.create(None, Map::new()).unwrap();
        let second = store.create(None, Map::new()).unwrap();
        store
            .append(
                &first.id,
                "append",
                &[json!({"role":"user","content":"A\r\nB\n😀"})],
            )
            .unwrap();
        let before: String = store
            .db
            .query_row(
                "SELECT payload FROM messages WHERE session_id=?",
                [&first.id],
                |row| row.get(0),
            )
            .unwrap();
        let mut other = SessionStore::open(dir.path(), dir.path()).unwrap();
        let revision = store.page(&first.id, None, 1).unwrap().revision;
        store
            .update_metadata(
                &first.id,
                Map::from_iter([(
                    "runtime_config".into(),
                    json!({"mode":"writer","private_extension":[1,2,3]}),
                )]),
                revision,
            )
            .unwrap();
        assert!(
            other
                .update_metadata(&first.id, Map::new(), revision)
                .is_err()
        );
        assert_eq!(store.list().unwrap()["current_session_id"], second.id);
        let after: String = store
            .db
            .query_row(
                "SELECT payload FROM messages WHERE session_id=?",
                [&first.id],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(before, after);
        assert_eq!(
            store
                .page(&second.id, None, 1)
                .unwrap()
                .metadata
                .get("runtime_config"),
            None
        );
    }
}
