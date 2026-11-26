use super::*;
use regex::Regex;
use sha1::Sha1;

pub(super) struct MemoryStore {
    db: Connection,
}

fn kind(raw: &str) -> String {
    let name = raw.trim().to_lowercase().replace('-', "_");
    let name = match name.as_str() {
        "decision" => "project_decision",
        "failure" => "failure_experience",
        "success" | "workflow" => "success_workflow",
        "correction" => "user_correction",
        "guidance" => "tool_guidance",
        value => value,
    };
    if [
        "instruction",
        "fact",
        "project_decision",
        "goal",
        "commitment",
        "preference",
        "relationship",
        "context",
        "event",
        "learning",
        "observation",
        "artifact",
        "error",
        "failure_experience",
        "success_workflow",
        "procedure",
        "user_correction",
        "tool_guidance",
        "retrieval_ranking",
        "prompt_digest",
        "feedback",
    ]
    .contains(&name)
    {
        name.into()
    } else {
        "fact".into()
    }
}

fn fingerprint(content: &str, kind: &str) -> String {
    let normalized = content
        .to_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    Sha1::digest(format!("assistant\n{kind}\n{normalized}").as_bytes())
        .iter()
        .take(12)
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn redact(raw: &str) -> Result<String> {
    let mut result = raw.to_owned();
    for pattern in [
        r"(?i)\b(?:sk-|ms-|nvapi-)[A-Za-z0-9_\-]{16,}\b",
        r"(?i)\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
    ] {
        result = Regex::new(pattern)?
            .replace_all(&result, "[REDACTED_SECRET]")
            .into_owned();
    }
    result = Regex::new(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}")?
        .replace_all(&result, "${1}[REDACTED]")
        .into_owned();
    result=Regex::new(r#"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password)\s*([:=])\s*['"]?[^'"\s,;]{8,}"#)?.replace_all(&result,"${1}${2}[REDACTED]").into_owned();
    for pattern in [
        r"(?i)\b([A-Z]:\\Users\\)[^\\\s]+",
        r"(?i)(/home/)[^/\s]+",
        r"(?i)(/Users/)[^/\s]+",
    ] {
        result = Regex::new(pattern)?
            .replace_all(&result, "${1}[USER]")
            .into_owned();
    }
    Ok(result.trim().into())
}

fn terms(body: &str) -> Result<Vec<String>> {
    let token = Regex::new(r"[A-Za-z_][A-Za-z0-9_]{1,}|\d+|[\u{4e00}-\u{9fff}]{2,}")?;
    let mut result = vec![];
    for word in token.find_iter(&body.to_lowercase()) {
        let word = word.as_str();
        if !result.iter().any(|item| item == word) {
            result.push(word.to_owned());
        }
        let characters = word.chars().collect::<Vec<_>>();
        if characters
            .iter()
            .all(|ch| matches!(ch, '\u{4e00}'..='\u{9fff}'))
        {
            for pair in characters.windows(2) {
                let value = pair.iter().collect::<String>();
                if !result.contains(&value) {
                    result.push(value);
                }
            }
        } else {
            for part in word.split(['_', '-', '.']).filter(|part| part.len() >= 2) {
                if !result.iter().any(|item| item == part) {
                    result.push(part.into());
                }
            }
        }
    }
    Ok(result)
}

impl MemoryStore {
    pub fn open(base: &Path) -> Result<Self> {
        let directory = safe_path(base, "memory")?;
        fs::create_dir_all(&directory)?;
        let path = safe_path(&directory, "memory.sqlite3")?;
        let existed = path.is_file() && path.metadata()?.len() > 0;
        let mut db = Connection::open(&path)?;
        db.busy_timeout(Duration::from_secs(10))?;
        if db.query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_meta')",
            [],
            |row| row.get::<_, bool>(0),
        )? {
            let version = db
                .query_row(
                    "SELECT value FROM memory_meta WHERE key='schema_version'",
                    [],
                    |row| row.get::<_, String>(0),
                )
                .optional()?;
            if version
                .as_deref()
                .map(str::parse::<u64>)
                .transpose()?
                .is_some_and(|version| version > 2)
            {
                return Err(
                    "AiO memory requires a newer Reverie version; original data was preserved."
                        .into(),
                );
            }
        }
        if existed {
            let backup = safe_path(base, "backups/memory.before-rust-3.0.sqlite3")?;
            if !backup.is_file() {
                fs::create_dir_all(backup.parent().unwrap())?;
                let staged = tempfile::NamedTempFile::new_in(backup.parent().unwrap())?;
                db.backup("main", staged.path(), rusqlite::backup::NO_PROGRESS)?;
                staged
                    .persist_noclobber(&backup)
                    .map_err(|error| error.error)?;
            }
            let original =
                Connection::open_with_flags(&backup, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)?;
            if original.query_row("PRAGMA quick_check", [], |row| row.get::<_, String>(0))? != "ok"
            {
                return Err("AiO memory backup failed its integrity check.".into());
            }
        }
        db.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; CREATE TABLE IF NOT EXISTS memory_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,scope TEXT NOT NULL,memory_type TEXT NOT NULL,status TEXT NOT NULL,content TEXT NOT NULL,tags TEXT NOT NULL,confidence REAL NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL); CREATE INDEX IF NOT EXISTS idx_memories_status_updated ON memories(status,updated_at DESC); CREATE INDEX IF NOT EXISTS idx_memories_type_scope ON memories(memory_type,scope); CREATE INDEX IF NOT EXISTS idx_memories_fingerprint ON memories(fingerprint); CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED,search_text,tokenize='unicode61'); CREATE TABLE IF NOT EXISTS assistant_memory_suppressions(fingerprint TEXT PRIMARY KEY); CREATE TABLE IF NOT EXISTS assistant_memory_sources(event_id TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(event_id,kind)); INSERT OR IGNORE INTO memory_meta VALUES ('schema_version','2'); INSERT OR IGNORE INTO memory_meta VALUES ('revision','0');")?;
        let legacy = safe_path(&directory, "memory_items.json")?;
        if legacy.is_file()
            && db.query_row("SELECT count(*) FROM memories", [], |row| {
                row.get::<_, i64>(0)
            })? == 0
        {
            let bytes = read_bytes(&legacy, 16 * 1024 * 1024)?;
            let parsed = strict_json(std::str::from_utf8(&bytes)?.trim_start_matches('\u{feff}'))?;
            let values = parsed
                .as_array()
                .or_else(|| parsed["items"].as_array())
                .ok_or(
                    "Legacy AiO memory must contain an item array; original data was preserved.",
                )?;
            write_bytes(
                &safe_path(base, "backups/memory-items.before-rust-3.0.json")?,
                &bytes,
            )?;
            let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
            for item in values {
                let mut item = item.clone();
                item["scope"] = json!("assistant");
                let content = redact(text(&item, "content"))?;
                let kind = kind(
                    item["type"]
                        .as_str()
                        .or_else(|| item["memory_type"].as_str())
                        .unwrap_or("fact"),
                );
                item["content"] = json!(content);
                item["type"] = json!(kind);
                item["fingerprint"] = json!(fingerprint(&content, &kind));
                if item["id"].as_str().is_none() {
                    item["id"] = json!(format!("mem_{}", uuid::Uuid::new_v4().simple()));
                }
                write(&tx, &item)?;
            }
            tx.commit()?;
        }
        Ok(Self { db })
    }

    pub fn import_suppressions(&mut self, values: &[String]) -> Result<()> {
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        for value in values {
            tx.execute(
                "INSERT OR IGNORE INTO assistant_memory_suppressions VALUES (?)",
                [value],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    pub fn list(&self, query: &str, limit: u64) -> Result<Vec<Value>> {
        let words = terms(query)?;
        let mut payloads = vec![];
        if !words.is_empty() {
            let match_query = words
                .iter()
                .take(32)
                .map(|word| format!("\"{}\"", word.replace('"', "\"\"")))
                .collect::<Vec<_>>()
                .join(" OR ");
            payloads=self.db.prepare("SELECT m.payload FROM memory_fts f JOIN memories m ON m.id=f.id WHERE memory_fts MATCH ? AND m.status='active' ORDER BY bm25(memory_fts),m.updated_at DESC LIMIT ?")?.query_map(params![match_query,limit.min(100)as i64],|row|row.get::<_,String>(0))?.collect::<rusqlite::Result<Vec<_>>>()?;
        }
        if payloads.is_empty() {
            payloads=self.db.prepare("SELECT payload FROM memories WHERE status='active' ORDER BY updated_at DESC,id LIMIT ?")?.query_map([limit.min(100)as i64],|row|row.get::<_,String>(0))?.collect::<rusqlite::Result<Vec<_>>>()?;
        }
        payloads.into_iter().map(|raw| strict_json(&raw)).collect()
    }

    pub fn remember(&mut self, proposal: &Value, event: &str) -> Result<Option<Value>> {
        let content = redact(text(proposal, "content"))?;
        if content.is_empty() {
            return Err("AiO memory proposal requires text.".into());
        }
        let kind = kind(proposal["kind"].as_str().unwrap_or("preference"));
        let fingerprint = fingerprint(&content, &kind);
        let provenance = proposal["provenance"].as_str().unwrap_or("inferred");
        if !["explicit_statement", "observed", "inferred"].contains(&provenance) {
            return Err(
                "AiO memory provenance must distinguish statement, observation and inference."
                    .into(),
            );
        }
        let confidence = proposal["confidence"].as_f64().unwrap_or(0.5);
        if !confidence.is_finite() {
            return Err("AiO memory confidence is not finite.".into());
        }
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        if tx
            .query_row(
                "SELECT 1 FROM assistant_memory_suppressions WHERE fingerprint=?",
                [&fingerprint],
                |_| Ok(()),
            )
            .optional()?
            .is_some()
            || tx
                .query_row(
                    "SELECT 1 FROM assistant_memory_sources WHERE event_id=? AND kind=?",
                    params![event, kind],
                    |_| Ok(()),
                )
                .optional()?
                .is_some()
        {
            return Ok(None);
        }
        if let Some(raw)=tx.query_row("SELECT payload FROM memories WHERE fingerprint=? AND status='active' ORDER BY updated_at DESC LIMIT 1",[&fingerprint],|row|row.get::<_,String>(0)).optional()?{return Ok(Some(strict_json(&raw)?));}
        let now = crate::session::now();
        let item = json!({"id":format!("mem_{}",uuid::Uuid::new_v4().simple()),"scope":"assistant","type":kind,"content":content,"evidence":[{"event_id":event}],"confidence":confidence.clamp(0.0,1.0),"tags":[],"decay":0.02,"created_at":now,"updated_at":now,"source_event_ids":[event],"status":"active","metadata":{},"provenance":provenance,"source":"aio","version":1,"supersedes":[],"superseded_by":"","valid_from":"","valid_to":"","last_accessed_at":"","access_count":0,"fingerprint":fingerprint});
        write(&tx, &item)?;
        tx.commit()?;
        Ok(Some(item))
    }

    pub fn edit(&mut self, id: &str, content: Option<&str>) -> Result<Value> {
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let raw = tx
            .query_row(
                "SELECT payload FROM memories WHERE id=? AND status='active'",
                [id],
                |row| row.get::<_, String>(0),
            )
            .optional()?
            .ok_or("Active AiO memory was not found.")?;
        let mut old = strict_json(&raw)?;
        let fingerprint = text(&old, "fingerprint").to_owned();
        let kind = text(&old, "type").to_owned();
        tx.execute(
            "INSERT OR IGNORE INTO assistant_memory_suppressions VALUES (?)",
            [fingerprint],
        )?;
        for event in strings(&old, "source_event_ids")? {
            tx.execute(
                "INSERT OR IGNORE INTO assistant_memory_sources VALUES (?,?)",
                params![event, kind],
            )?;
        }
        let now = crate::session::now();
        old["updated_at"] = json!(now);
        old["valid_to"] = json!(now);
        if let Some(content) = content {
            let content = redact(content)?;
            if content.is_empty() {
                return Err("Corrected memory must contain text.".into());
            }
            let mut next = old.clone();
            let next_id = format!("mem_{}", uuid::Uuid::new_v4().simple());
            old["status"] = json!("superseded");
            old["superseded_by"] = json!(next_id);
            write(&tx, &old)?;
            next["id"] = json!(next_id);
            next["content"] = json!(content);
            next["fingerprint"] = json!(fingerprint_for_item(&next));
            next["provenance"] = json!("explicit_correction");
            next["version"] = json!(old["version"].as_u64().unwrap_or(1) + 1);
            next["supersedes"] = json!([id]);
            next["superseded_by"] = json!("");
            next["status"] = json!("active");
            next["valid_to"] = json!("");
            next["created_at"] = json!(now);
            write(&tx, &next)?;
            tx.commit()?;
            Ok(next)
        } else {
            old["status"] = json!("deleted");
            write(&tx, &old)?;
            tx.commit()?;
            Ok(old)
        }
    }
}

fn fingerprint_for_item(item: &Value) -> String {
    fingerprint(text(item, "content"), text(item, "type"))
}

fn write(tx: &Transaction<'_>, item: &Value) -> Result<()> {
    let id = text(item, "id");
    let content = text(item, "content");
    let status = item["status"].as_str().unwrap_or("active");
    let kind = item["type"].as_str().unwrap_or("fact");
    tx.execute("INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint,scope=excluded.scope,memory_type=excluded.memory_type,status=excluded.status,content=excluded.content,tags=excluded.tags,confidence=excluded.confidence,updated_at=excluded.updated_at,payload=excluded.payload",params![id,item["fingerprint"].as_str().unwrap_or(""),"assistant",kind,status,content,serde_json::to_string(&item["tags"])? ,item["confidence"].as_f64().unwrap_or(0.5).clamp(0.0,1.0),item["updated_at"].as_str().unwrap_or(""),serde_json::to_string(item)?])?;
    tx.execute("DELETE FROM memory_fts WHERE id=?", [id])?;
    if status == "active" {
        let search = format!("{content} {}", terms(content)?.join(" "));
        tx.execute("INSERT INTO memory_fts VALUES (?,?)", params![id, search])?;
    }
    tx.execute(
        "UPDATE memory_meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'",
        [],
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn future_memory_schema_is_rejected_before_schema_or_journal_changes() {
        let root = tempfile::tempdir().unwrap();
        let directory = root.path().join("memory");
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("memory.sqlite3");
        let db = Connection::open(&path).unwrap();
        db.execute_batch("CREATE TABLE memory_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL); INSERT INTO memory_meta VALUES ('schema_version','99');").unwrap();
        drop(db);
        let before = fs::read(&path).unwrap();
        assert!(
            MemoryStore::open(root.path())
                .err()
                .unwrap()
                .to_string()
                .contains("newer")
        );
        assert_eq!(fs::read(&path).unwrap(), before);
        let db = Connection::open(&path).unwrap();
        assert_eq!(
            db.query_row(
                "SELECT count(*) FROM sqlite_master WHERE name='memories'",
                [],
                |row| row.get::<_, i64>(0)
            )
            .unwrap(),
            0
        );
        assert_eq!(
            db.query_row("PRAGMA journal_mode", [], |row| row.get::<_, String>(0))
                .unwrap(),
            "delete"
        );
    }

    #[test]
    fn corrections_deletions_tombstones_and_redaction_survive_restart() {
        let root = tempfile::tempdir().unwrap();
        let mut store = MemoryStore::open(root.path()).unwrap();
        let proposal = json!({"content":"喜欢保持完整小说正文","kind":"preference","provenance":"explicit_statement","confidence":1.0});
        let old = store.remember(&proposal, "event-one").unwrap().unwrap();
        let corrected = store
            .edit(text(&old, "id"), Some("喜欢完整正文和原始版本"))
            .unwrap();
        assert!(store.remember(&proposal, "event-one").unwrap().is_none());
        assert_eq!(
            store.list("原始版本", 10).unwrap()[0]["id"],
            corrected["id"]
        );
        store.edit(text(&corrected, "id"), None).unwrap();
        drop(store);
        let mut store = MemoryStore::open(root.path()).unwrap();
        assert!(store.list("", 10).unwrap().is_empty());
        assert!(store.remember(&proposal, "event-new").unwrap().is_none());
        let secret = "api_key=FIXTURE_SECRET_KEY_0123456789 C:\\Users\\Fixture\\project";
        let item = store
            .remember(&json!({"content":secret}), "event-secret")
            .unwrap()
            .unwrap();
        assert!(!text(&item, "content").contains("FIXTURE_SECRET"));
        assert!(!text(&item, "content").contains("Users\\Fixture"));
    }
}
