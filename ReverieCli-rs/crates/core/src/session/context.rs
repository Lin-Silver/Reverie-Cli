//! An active context is a projection of immutable transcript rows, not a replacement transcript.

use super::{SessionStore, digest, insert_messages, now, validate_id, wire};
use crate::{
    Result,
    compaction::{CompactionKind, PreparedContext},
    models,
};
use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::Write,
    path::PathBuf,
};

const PROJECTION_KEY: &str = "native_context_projection";
const CHECKPOINT_SCHEMA: u32 = 1;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ContextSource {
    pub session_id: String,
    pub revision: i64,
    pub message_count: i64,
    pub sha256: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ContextRecord {
    pub sequence: i64,
    pub id: String,
    /// Exactly the stored JSON string, including original content escapes and unknown fields.
    pub payload: String,
    pub digest: String,
}

#[derive(Clone, Debug)]
pub struct ContextEntry {
    pub sequence: i64,
    pub message: Value,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct ConversationRecord {
    id: String,
    name: String,
    created_at: String,
    updated_at: String,
    metadata: String,
    revision: i64,
    message_count: i64,
}

#[derive(Clone, Debug)]
pub struct ContextSnapshot {
    pub source: ContextSource,
    pub metadata: Map<String, Value>,
    pub records: Vec<ContextRecord>,
    pub active: Vec<ContextEntry>,
    conversation: ConversationRecord,
}

impl ContextSnapshot {
    pub fn messages(&self) -> Vec<Value> {
        self.active
            .iter()
            .map(|entry| entry.message.clone())
            .collect()
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct ContextCheckpoint {
    pub path: PathBuf,
    pub sha256: String,
    pub source: ContextSource,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct CheckpointDocument {
    schema_version: u32,
    source: ContextSource,
    conversation: ConversationRecord,
    records: Vec<ContextRecord>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ContextProjection {
    schema_version: u32,
    boundary_sequence: i64,
    prefix_sequences: Vec<i64>,
    tail_sequences: Vec<i64>,
    source: ContextSource,
    checkpoint: ContextCheckpoint,
    kind: CompactionKind,
    event_id: String,
}

impl SessionStore {
    pub fn context_snapshot(&self, id: &str) -> Result<ContextSnapshot> {
        validate_id(id)?;
        let tx = self.db.unchecked_transaction()?;
        let snapshot = load_snapshot(&tx, id)?;
        tx.commit()?;
        Ok(snapshot)
    }

    /// Start a new ordinary run from one exact saved user row, without appending it again.
    pub fn begin_resumed_run(
        &mut self,
        source: &ContextSource,
        user_sequence: i64,
        run_id: &str,
        configuration: &Value,
        request: &Value,
        user: &Value,
    ) -> Result<()> {
        validate_id(&source.session_id)?;
        validate_id(run_id)?;
        if self.scope["assistant_id"] == "aio" {
            return Err(
                "Application-level AiO tasks must use their existing saved-prompt contract.".into(),
            );
        }
        if !request.is_object() || !configuration.is_object() {
            return Err("A resumed run requires an object request and configuration.".into());
        }
        let execution_root = request["executionRoot"]
            .as_str()
            .or_else(|| self.scope["workspace_path"].as_str())
            .ok_or("A resumed run requires its executionRoot.")?
            .to_owned();
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let current = load_snapshot(&tx, &source.session_id)?;
        if current.source != *source {
            return Err(
                "Conversation revision or source digest conflict; no resumed run was started."
                    .into(),
            );
        }
        if let Some(workspace) = self.scope.get("workspace_id")
            && current.metadata.get("workspace_id") != Some(workspace)
        {
            return Err("The resumed conversation belongs to a different workspace.".into());
        }
        let latest = current
            .active
            .iter()
            .rfind(|entry| {
                entry.message["role"]
                    .as_str()
                    .is_some_and(|role| role.eq_ignore_ascii_case("user"))
            })
            .ok_or("The active conversation has no saved user request to resume.")?;
        if latest.sequence != user_sequence || latest.message != *user {
            return Err(
                "The resumed user sequence or complete original payload does not match.".into(),
            );
        }
        validate_resumed_request(request, user)?;
        if let Some(saved) = current.metadata.get("runtime_config")
            && models::without_secrets(saved) != *configuration
        {
            return Err(
                "The resumed configuration differs from the source conversation snapshot.".into(),
            );
        }
        if let Some(requested) = request.get("configuration")
            && models::without_secrets(requested) != *configuration
        {
            return Err("The resumed request and execution configuration do not match.".into());
        }
        if tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM task_runs WHERE id=?)",
            [run_id],
            |row| row.get::<_, bool>(0),
        )? {
            return Err("This resumed run identity already exists; recover its status before another execution.".into());
        }
        ensure_reduction_run_in(&tx, &source.session_id, None)?;
        let original = &current.records[user_sequence as usize];
        let mut saved_request = models::without_secrets(request);
        saved_request["executionRoot"] = json!(execution_root);
        saved_request["_native_started"] = json!(true);
        saved_request["_native_context_resume"] = json!({"source":source,"user_sequence":user_sequence,"user_id":original.id,"user_digest":original.digest});
        let time = now();
        tx.execute("INSERT INTO task_runs(id,session_id,configuration_revision,configuration,execution_root,state,revision,result,created_at,updated_at,request) VALUES (?,?,?,?,?,'running',1,'{}',?,?,?)",
            params![run_id,source.session_id,source.revision,serde_json::to_string(configuration)?,execution_root,time,time,serde_json::to_string(&saved_request)?])?;
        tx.execute(
            "UPDATE conversations SET revision=revision+1,updated_at=? WHERE id=? AND deleted=0",
            params![time, source.session_id],
        )?;
        tx.commit()?;
        Ok(())
    }

    pub(crate) fn ensure_reduction_run(&self, id: &str, allowed_run: Option<&str>) -> Result<()> {
        ensure_reduction_run_in(&self.db, id, allowed_run)
    }

    /// Persist an inferred Writer binding only against the exact source selected for resume.
    pub(crate) fn bind_resumed_writer(
        &mut self,
        source: &ContextSource,
        binding: &Value,
    ) -> Result<ContextSnapshot> {
        validate_id(&source.session_id)?;
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let current = load_snapshot(&tx, &source.session_id)?;
        if current.source != *source {
            return Err("Conversation revision or source digest conflict; the Writer binding was not changed.".into());
        }
        ensure_reduction_run_in(&tx, &source.session_id, None)?;
        if current.metadata.get("writer_project") == Some(binding) {
            tx.commit()?;
            return Ok(current);
        }
        let mut metadata = current.metadata.clone();
        metadata.insert("writer_project".into(), binding.clone());
        tx.execute(
            "UPDATE conversations SET metadata=?,revision=revision+1,updated_at=? WHERE id=? AND deleted=0",
            params![serde_json::to_string(&metadata)?, now(), source.session_id],
        )?;
        let updated = load_snapshot(&tx, &source.session_id)?;
        tx.commit()?;
        Ok(updated)
    }

    /// Write, fsync, publish without overwrite, then read back the full source checkpoint.
    pub fn checkpoint_context(&self, snapshot: &ContextSnapshot) -> Result<ContextCheckpoint> {
        let path = self.checkpoint_path(&snapshot.source);
        fs::create_dir_all(
            path.parent()
                .ok_or("Context checkpoint directory is missing.")?,
        )?;
        let document = checkpoint_document(snapshot);
        let encoded = serde_json::to_vec(&document)?;
        if !path.exists() {
            // tempfile's Windows publication calls need a verbatim path beyond MAX_PATH.
            let io_parent = fs::canonicalize(path.parent().unwrap())?;
            let io_path = io_parent.join(path.file_name().unwrap());
            let mut staged = tempfile::NamedTempFile::new_in(&io_parent)?;
            staged.write_all(&encoded)?;
            staged.as_file().sync_all()?;
            if let Err(error) = staged.persist_noclobber(&io_path)
                && error.error.kind() != std::io::ErrorKind::AlreadyExists
            {
                return Err(error.error.into());
            }
        }
        let bytes = fs::read(&path)?;
        if serde_json::from_slice::<CheckpointDocument>(&bytes)? != document {
            return Err(
                "Existing context checkpoint content does not match the source snapshot.".into(),
            );
        }
        let checkpoint = ContextCheckpoint {
            path,
            sha256: digest(std::str::from_utf8(&bytes)?),
            source: snapshot.source.clone(),
        };
        self.verify_context_checkpoint(snapshot, &checkpoint)?;
        Ok(checkpoint)
    }

    /// All original rows, configuration versions, task identities and navigation stay unchanged.
    pub fn segment_context(
        &mut self,
        snapshot: &ContextSnapshot,
        checkpoint: &ContextCheckpoint,
        prepared: &PreparedContext,
        event_id: &str,
    ) -> Result<ContextSnapshot> {
        self.segment_context_checked(snapshot, checkpoint, prepared, event_id, None, || Ok(()))
    }

    /// Hold the caller's commit permission until the context transaction finishes committing.
    pub(crate) fn segment_context_checked<F, G>(
        &mut self,
        snapshot: &ContextSnapshot,
        checkpoint: &ContextCheckpoint,
        prepared: &PreparedContext,
        event_id: &str,
        allowed_run: Option<&str>,
        commit_guard: F,
    ) -> Result<ContextSnapshot>
    where
        F: FnOnce() -> Result<G>,
    {
        if prepared.source != snapshot.source
            || checkpoint.source != snapshot.source
            || prepared.checkpoint != *checkpoint
        {
            return Err("Prepared context, checkpoint and source identity do not match.".into());
        }
        let encoded = serde_json::to_string(prepared)?;
        let event_digest = digest(&encoded);
        let checkpoint_path = self.checkpoint_path(&snapshot.source);
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        ensure_reduction_run_in(&tx, &snapshot.source.session_id, allowed_run)?;
        let previous: Option<(String, String)> = tx
            .query_row(
                "SELECT session_id,digest FROM conversation_events WHERE id=?",
                [event_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        if let Some((owner, hash)) = previous {
            if owner != snapshot.source.session_id || hash != event_digest {
                return Err("Context reduction event identity conflict.".into());
            }
            let current = load_snapshot(&tx, &owner)?;
            let permission = commit_guard()?;
            tx.commit()?;
            drop(permission);
            return Ok(current);
        }
        let current = load_snapshot(&tx, &snapshot.source.session_id)?;
        if current.source != snapshot.source {
            return Err(
                "Conversation revision conflict; the source context remains active.".into(),
            );
        }
        verify_checkpoint(snapshot, checkpoint, &checkpoint_path)?;
        validate_retained(snapshot, prepared)?;
        let boundary_sequence = snapshot.source.message_count;
        let projection = ContextProjection {
            schema_version: 1,
            boundary_sequence,
            prefix_sequences: prepared.retained_prefix_sequences.clone(),
            tail_sequences: prepared.retained_tail_sequences.clone(),
            source: snapshot.source.clone(),
            checkpoint: checkpoint.clone(),
            kind: prepared.kind,
            event_id: event_id.into(),
        };
        let boundary = json!({
            "role":"system", "content":prepared.summary, "segment_boundary":true,
            "native_context": {"event_id":event_id,"kind":prepared.kind,"origin":prepared.origin,"fallback_reason":prepared.fallback_reason,"source":snapshot.source,"checkpoint":checkpoint,"model_identity":prepared.model_identity,"usage_before":prepared.usage_before,"usage_after":prepared.usage_after,"handoff":prepared.handoff},
        });
        insert_messages(
            &tx,
            &snapshot.source.session_id,
            boundary_sequence,
            &[boundary],
        )?;
        let mut metadata = snapshot.metadata.clone();
        metadata.insert("active_context_start".into(), json!(boundary_sequence));
        metadata.insert(PROJECTION_KEY.into(), serde_json::to_value(&projection)?);
        tx.execute(
            "UPDATE conversations SET metadata=?,message_count=message_count+1,revision=revision+1,updated_at=? WHERE id=? AND deleted=0",
            params![serde_json::to_string(&metadata)?, now(), snapshot.source.session_id],
        )?;
        tx.execute(
            "INSERT INTO conversation_events VALUES (?,?,?)",
            params![event_id, snapshot.source.session_id, event_digest],
        )?;
        let result = load_snapshot(&tx, &snapshot.source.session_id)?;
        let permission = commit_guard()?;
        tx.commit()?;
        drop(permission);
        Ok(result)
    }

    fn checkpoint_path(&self, source: &ContextSource) -> PathBuf {
        self.base.join("context_checkpoints").join(format!(
            "checkpoint-{}-{}-{}.json",
            source.session_id, source.revision, source.sha256
        ))
    }

    pub fn verify_context_checkpoint(
        &self,
        snapshot: &ContextSnapshot,
        checkpoint: &ContextCheckpoint,
    ) -> Result<()> {
        verify_checkpoint(
            snapshot,
            checkpoint,
            &self.checkpoint_path(&snapshot.source),
        )
    }
}

fn ensure_reduction_run_in(db: &Connection, id: &str, allowed_run: Option<&str>) -> Result<()> {
    validate_id(id)?;
    if let Some(run) = allowed_run {
        validate_id(run)?;
    }
    if db.query_row(
        "SELECT EXISTS(SELECT 1 FROM task_runs WHERE session_id=?1 AND state NOT IN ('completed','cancelled','failed','interrupted') AND (?2 IS NULL OR id<>?2))",
        params![id, allowed_run],
        |row| row.get::<_, bool>(0),
    )? {
        return Err("A run is already active or queued for this conversation.".into());
    }
    Ok(())
}

fn validate_resumed_request(request: &Value, user: &Value) -> Result<()> {
    if request["promptAlreadySaved"] == true {
        return Err("Ordinary resume must use source binding, not AiO promptAlreadySaved.".into());
    }
    let prompt = request
        .get("prompt")
        .filter(|value| !value.is_null())
        .or_else(|| request.get("message").filter(|value| !value.is_null()))
        .ok_or("A resumed run must bind the complete saved prompt.")?;
    if user.get("content") != Some(prompt) {
        return Err("The resumed prompt differs from the complete saved user content.".into());
    }
    if let Some(message) = request.get("message").filter(|value| !value.is_null())
        && message != prompt
    {
        return Err("The resumed prompt and message aliases do not match.".into());
    }
    for key in ["attachment", "attachments"] {
        if let Some(requested) = request.get(key) {
            let matches = match user.get(key) {
                Some(original) => requested == original,
                None => requested.is_null() || requested.as_array().is_some_and(Vec::is_empty),
            };
            if !matches {
                return Err(
                    "The resumed attachments differ from the complete saved user payload.".into(),
                );
            }
        }
    }
    Ok(())
}

fn checkpoint_document(snapshot: &ContextSnapshot) -> CheckpointDocument {
    CheckpointDocument {
        schema_version: CHECKPOINT_SCHEMA,
        source: snapshot.source.clone(),
        conversation: snapshot.conversation.clone(),
        records: snapshot.records.clone(),
    }
}

fn verify_checkpoint(
    snapshot: &ContextSnapshot,
    checkpoint: &ContextCheckpoint,
    expected_path: &PathBuf,
) -> Result<()> {
    if checkpoint.source != snapshot.source || checkpoint.path != *expected_path {
        return Err("Context checkpoint identity or managed path differs from the source.".into());
    }
    let attributes = fs::symlink_metadata(&checkpoint.path)?;
    if !attributes.is_file() || attributes.file_type().is_symlink() {
        return Err("Context checkpoint must be a managed regular file.".into());
    }
    let bytes = fs::read(&checkpoint.path)?;
    if digest(std::str::from_utf8(&bytes)?) != checkpoint.sha256 {
        return Err(
            "Context checkpoint failed SHA-256 verification; the source context remains active."
                .into(),
        );
    }
    if serde_json::from_slice::<CheckpointDocument>(&bytes)? != checkpoint_document(snapshot) {
        return Err("Context checkpoint failed source/payload verification; the source context remains active.".into());
    }
    Ok(())
}

fn load_snapshot(db: &Connection, id: &str) -> Result<ContextSnapshot> {
    let conversation = db.query_row(
        "SELECT id,name,created_at,updated_at,metadata,revision,message_count FROM conversations WHERE id=? AND deleted=0", [id], |row| {
            Ok(ConversationRecord { id: row.get(0)?, name: row.get(1)?, created_at: row.get(2)?, updated_at: row.get(3)?, metadata: row.get(4)?, revision: row.get(5)?, message_count: row.get(6)? })
        },
    ).optional()?.ok_or("Conversation not found.")?;
    let records: Vec<ContextRecord> = db
        .prepare(
            "SELECT sequence,id,payload,digest FROM messages WHERE session_id=? ORDER BY sequence",
        )?
        .query_map([id], |row| {
            Ok(ContextRecord {
                sequence: row.get(0)?,
                id: row.get(1)?,
                payload: row.get(2)?,
                digest: row.get(3)?,
            })
        })?
        .collect::<rusqlite::Result<_>>()?;
    if conversation.message_count < 0 || records.len() as i64 != conversation.message_count {
        return Err("Conversation message count does not match its immutable transcript.".into());
    }
    for (index, record) in records.iter().enumerate() {
        if record.sequence != index as i64 || digest(&record.payload) != record.digest {
            return Err("Conversation sequence or original payload digest is invalid.".into());
        }
    }
    let metadata: Map<String, Value> = serde_json::from_str(&conversation.metadata)?;
    let active = active_entries(&metadata, &records)?;
    let source = ContextSource {
        session_id: id.into(),
        revision: conversation.revision,
        message_count: conversation.message_count,
        sha256: digest(&serde_json::to_string(&(&conversation, &records))?),
    };
    Ok(ContextSnapshot {
        source,
        metadata,
        records,
        active,
        conversation,
    })
}

fn entry(record: &ContextRecord) -> Result<ContextEntry> {
    if digest(&record.payload) != record.digest {
        return Err("Conversation original payload digest is invalid.".into());
    }
    let mut message = wire(serde_json::from_str(&record.payload)?);
    if let Some(fields) = message.as_object_mut() {
        fields.remove("segment_boundary");
        fields.remove("context_replay");
        fields.remove("native_context");
    }
    Ok(ContextEntry {
        sequence: record.sequence,
        message,
    })
}

/// Normal requests read only active rows; full snapshots are for reduction/checkpoints.
pub(super) fn history(store: &SessionStore, id: &str) -> Result<Vec<Value>> {
    validate_id(id)?;
    let tx = store.db.unchecked_transaction()?;
    let (metadata, count): (String, i64) = tx
        .query_row(
            "SELECT metadata,message_count FROM conversations WHERE id=? AND deleted=0",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?
        .ok_or("Conversation not found.")?;
    let metadata: Map<String, Value> = serde_json::from_str(&metadata)?;
    let Some(projection) = decode_projection(&metadata, count)? else {
        let start = metadata
            .get("active_context_start")
            .and_then(Value::as_i64)
            .unwrap_or(0)
            .max(0);
        let records = read_records(&tx, id, start, true)?;
        let history = records
            .iter()
            .map(entry)
            .map(|entry| entry.map(|entry| entry.message))
            .collect::<Result<Vec<_>>>()?;
        tx.commit()?;
        return Ok(history);
    };
    if projection.source.session_id != id {
        return Err("Conversation context projection belongs to another session.".into());
    }
    let mut references = projection.prefix_sequences.clone();
    references.push(projection.boundary_sequence);
    references.extend_from_slice(&projection.tail_sequences);
    let referenced: Vec<ContextRecord> = tx.prepare("SELECT sequence,id,payload,digest FROM messages WHERE session_id=? AND sequence IN (SELECT value FROM json_each(?))")?
        .query_map(params![id,serde_json::to_string(&references)?], |row| Ok(ContextRecord { sequence:row.get(0)?,id:row.get(1)?,payload:row.get(2)?,digest:row.get(3)? }))?.collect::<rusqlite::Result<_>>()?;
    let by_sequence: HashMap<i64, &ContextRecord> = referenced
        .iter()
        .map(|record| (record.sequence, record))
        .collect();
    let boundary = by_sequence
        .get(&projection.boundary_sequence)
        .ok_or("Saved context boundary is missing.")?;
    validate_boundary(boundary, &projection)?;
    let mut seen = HashSet::new();
    let mut history = Vec::with_capacity(references.len());
    for sequence in &projection.prefix_sequences {
        history.push(history_reference(
            &by_sequence,
            &mut seen,
            *sequence,
            projection.boundary_sequence,
        )?);
    }
    history.push(entry(boundary)?.message);
    for sequence in &projection.tail_sequences {
        history.push(history_reference(
            &by_sequence,
            &mut seen,
            *sequence,
            projection.boundary_sequence,
        )?);
    }
    for record in read_records(&tx, id, projection.boundary_sequence, false)? {
        history.push(entry(&record)?.message);
    }
    tx.commit()?;
    Ok(history)
}

fn read_records(
    db: &Connection,
    id: &str,
    sequence: i64,
    inclusive: bool,
) -> Result<Vec<ContextRecord>> {
    let sql = if inclusive {
        "SELECT sequence,id,payload,digest FROM messages WHERE session_id=? AND sequence>=? ORDER BY sequence"
    } else {
        "SELECT sequence,id,payload,digest FROM messages WHERE session_id=? AND sequence>? ORDER BY sequence"
    };
    Ok(db
        .prepare(sql)?
        .query_map(params![id, sequence], |row| {
            Ok(ContextRecord {
                sequence: row.get(0)?,
                id: row.get(1)?,
                payload: row.get(2)?,
                digest: row.get(3)?,
            })
        })?
        .collect::<rusqlite::Result<_>>()?)
}

fn history_reference(
    records: &HashMap<i64, &ContextRecord>,
    seen: &mut HashSet<i64>,
    sequence: i64,
    boundary: i64,
) -> Result<Value> {
    if sequence < 0 || sequence >= boundary || !seen.insert(sequence) {
        return Err("Conversation context reference is out of range or duplicated.".into());
    }
    Ok(entry(
        records
            .get(&sequence)
            .ok_or("Referenced original context row is missing.")?,
    )?
    .message)
}

fn decode_projection(
    metadata: &Map<String, Value>,
    count: i64,
) -> Result<Option<ContextProjection>> {
    let Some(value) = metadata.get(PROJECTION_KEY) else {
        return Ok(None);
    };
    let projection: ContextProjection = serde_json::from_value(value.clone())?;
    if projection.schema_version != 1
        || projection.boundary_sequence < 0
        || projection.boundary_sequence >= count
        || projection.source.message_count != projection.boundary_sequence
    {
        return Err("Conversation context projection requires a supported valid boundary.".into());
    }
    Ok(Some(projection))
}

fn validate_boundary(record: &ContextRecord, projection: &ContextProjection) -> Result<()> {
    let boundary: Value = serde_json::from_str(&record.payload)?;
    if boundary["segment_boundary"] != true
        || boundary["native_context"]["event_id"] != projection.event_id
    {
        return Err("Conversation context projection does not match its saved boundary.".into());
    }
    Ok(())
}

fn active_entries(
    metadata: &Map<String, Value>,
    records: &[ContextRecord],
) -> Result<Vec<ContextEntry>> {
    let Some(projection) = decode_projection(metadata, records.len() as i64)? else {
        let start = metadata
            .get("active_context_start")
            .and_then(Value::as_i64)
            .unwrap_or(0)
            .max(0);
        return records
            .iter()
            .filter(|record| record.sequence >= start)
            .map(entry)
            .collect();
    };
    validate_boundary(&records[projection.boundary_sequence as usize], &projection)?;
    let mut seen = HashSet::new();
    let mut active = Vec::new();
    for sequence in &projection.prefix_sequences {
        push_reference(
            &mut active,
            &mut seen,
            records,
            *sequence,
            projection.boundary_sequence,
        )?;
    }
    active.push(entry(&records[projection.boundary_sequence as usize])?);
    for sequence in &projection.tail_sequences {
        push_reference(
            &mut active,
            &mut seen,
            records,
            *sequence,
            projection.boundary_sequence,
        )?;
    }
    active.extend(
        records
            .iter()
            .skip(projection.boundary_sequence as usize + 1)
            .map(entry)
            .collect::<Result<Vec<_>>>()?,
    );
    Ok(active)
}

fn push_reference(
    active: &mut Vec<ContextEntry>,
    seen: &mut HashSet<i64>,
    records: &[ContextRecord],
    sequence: i64,
    boundary: i64,
) -> Result<()> {
    if sequence < 0 || sequence >= boundary || !seen.insert(sequence) {
        return Err("Conversation context reference is out of range or duplicated.".into());
    }
    active.push(entry(&records[sequence as usize])?);
    Ok(())
}

fn validate_retained(snapshot: &ContextSnapshot, prepared: &PreparedContext) -> Result<()> {
    if prepared.summary.trim().is_empty() {
        return Err("A context boundary requires a non-empty prepared summary.".into());
    }
    let active: HashSet<i64> = snapshot.active.iter().map(|entry| entry.sequence).collect();
    let mut seen = HashSet::new();
    for sequences in [
        &prepared.retained_prefix_sequences,
        &prepared.retained_tail_sequences,
    ] {
        if sequences.windows(2).any(|pair| pair[0] >= pair[1]) {
            return Err("Retained transcript sequences must preserve their original order.".into());
        }
        for sequence in sequences {
            if !active.contains(sequence) || !seen.insert(*sequence) {
                return Err(
                    "Prepared context contains a missing or duplicate original reference.".into(),
                );
            }
        }
    }
    for sequence in &prepared.retained_prefix_sequences {
        let message = snapshot
            .active
            .iter()
            .find(|entry| entry.sequence == *sequence)
            .unwrap();
        if message.message["role"] != "system" {
            return Err("Context prefix can retain only durable system instructions.".into());
        }
    }
    Ok(())
}

#[cfg(test)]
mod checks;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::compaction::{self, CompactionOptions, CompactionOutcome, CompactionResponse};

    pub(super) fn fixture() -> (tempfile::TempDir, SessionStore, String) {
        let directory = tempfile::tempdir().unwrap();
        let mut store = SessionStore::open(directory.path(), directory.path()).unwrap();
        let page = store
            .create(
                Some("原文会话😀"),
                Map::from_iter([
                    (
                        "runtime_config".into(),
                        json!({"mode":"writer","extension":{"value":42}}),
                    ),
                    ("task_id".into(), json!("fixture-task")),
                ]),
            )
            .unwrap();
        let mut messages = vec![
            json!({"role":"system","content":"Durable user constraint: preserve original source and current task."}),
        ];
        messages.extend((0..20).map(|index| json!({"role":if index%2==0 { "user" } else { "assistant" },"content":format!("Original {index}\r\n中文😀\n{}", "Verified design with pending implementation and source evidence. ".repeat(100)),"unknown":{"index":index,"keep":true}})));
        messages.extend([
            json!({"role":"user","content":"Start the final complete interaction"}),
            json!({"role":"assistant","content":null,"tool_calls":[{"id":"a","function":{"name":"read_file","arguments":"{\"path\":\"fixture.txt\"}"}},{"id":"b","function":{"name":"search_files","arguments":"{\"pattern\":\"fixture\"}"}}]}),
            json!({"role":"tool","tool_call_id":"a","name":"read_file","content":"Exact file source\r\n保留😀"}),
            json!({"role":"tool","tool_call_id":"b","name":"search_files","content":"Observed search results"}),
            json!({"role":"assistant","content":"Both read-only calls completed."}),
            json!({"role":"user","content":"CURRENT 原文\r\n第二行😀\n","attachment":{"path":"保留.png","revision":7}}),
        ]);
        store
            .append(&page.id, "fixture-originals", &messages)
            .unwrap();
        (directory, store, page.id)
    }

    pub(super) fn ready(
        store: &SessionStore,
        id: &str,
        kind: CompactionKind,
    ) -> (ContextSnapshot, ContextCheckpoint, PreparedContext) {
        let snapshot = store.context_snapshot(id).unwrap();
        let checkpoint = store.checkpoint_context(&snapshot).unwrap();
        let request = compaction::prepare(
            &snapshot,
            &checkpoint,
            kind,
            &CompactionOptions {
                max_tokens: 131072,
                ..Default::default()
            },
        )
        .unwrap()
        .unwrap();
        let text = if kind == CompactionKind::Compression {
            "Summary:\n1. **Primary Request and Intent:**\n- Preserve original source and continue the active implementation."
        } else {
            "{\"project_goal\":\"Preserve original source\",\"next_actions\":[\"Continue the pending implementation\"]}"
        };
        let CompactionOutcome::Ready(prepared) = compaction::complete(
            &request,
            CompactionResponse::Text(text.into()),
            &json!({"model":"fixture","provider":"openai-chat"}),
        )
        .unwrap() else {
            panic!("fixture summary must reduce this source");
        };
        (snapshot, checkpoint, prepared)
    }

    #[test]
    fn compression_checkpoints_exact_rows_and_recovers_same_id_and_complete_tail() {
        let (directory, mut store, id) = fixture();
        let other = store.create(Some("other"), Map::new()).unwrap();
        let configuration_versions: i64 = store
            .db
            .query_row(
                "SELECT count(*) FROM configuration_versions WHERE session_id=?",
                [&id],
                |row| row.get(0),
            )
            .unwrap();
        let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Compression);
        let encoded: CheckpointDocument =
            serde_json::from_slice(&fs::read(&checkpoint.path).unwrap()).unwrap();
        assert_eq!(encoded.records, snapshot.records);
        assert_eq!(
            encoded.conversation.metadata,
            snapshot.conversation.metadata
        );
        assert_eq!(store.checkpoint_context(&snapshot).unwrap(), checkpoint);
        let result = store
            .segment_context(&snapshot, &checkpoint, &prepared, "segment-event")
            .unwrap();
        assert_eq!(result.source.session_id, id);
        assert_eq!(
            result.source.message_count,
            snapshot.source.message_count + 1
        );
        assert_eq!(&result.records[..snapshot.records.len()], &snapshot.records);
        assert_eq!(
            result.metadata["runtime_config"],
            snapshot.metadata["runtime_config"]
        );
        assert_eq!(result.metadata["task_id"], "fixture-task");
        assert_eq!(store.list().unwrap()["current_session_id"], other.id);
        let history = result.messages();
        assert_eq!(history[0], snapshot.active[0].message);
        assert_eq!(history[1]["content"], prepared.summary);
        let retained: Vec<Value> = prepared
            .retained_tail_sequences
            .iter()
            .map(|sequence| {
                snapshot
                    .active
                    .iter()
                    .find(|entry| entry.sequence == *sequence)
                    .unwrap()
                    .message
                    .clone()
            })
            .collect();
        assert_eq!(&history[2..], &retained);
        assert!(history.iter().any(|message| message["tool_call_id"] == "a"));
        assert!(history.iter().any(|message| message["tool_call_id"] == "b"));
        assert!(
            history
                .iter()
                .all(|message| message.get("native_context").is_none()
                    && message.get("segment_boundary").is_none())
        );
        let original_current: i64 = store.db.query_row("SELECT count(*) FROM messages WHERE session_id=? AND json_extract(payload,'$.role')='user' AND json_extract(payload,'$.content')=?", params![id,"CURRENT 原文\r\n第二行😀\n"],|row|row.get(0)).unwrap();
        assert_eq!(original_current, 1);
        assert_eq!(
            store
                .segment_context(&snapshot, &checkpoint, &prepared, "segment-event")
                .unwrap()
                .source,
            result.source
        );
        assert_eq!(
            store
                .db
                .query_row(
                    "SELECT count(*) FROM configuration_versions WHERE session_id=?",
                    [&id],
                    |row| row.get::<_, i64>(0)
                )
                .unwrap(),
            configuration_versions
        );
        drop(store);
        let mut store = SessionStore::open(directory.path(), directory.path()).unwrap();
        assert_eq!(store.history(&id).unwrap(), history);
        assert_eq!(store.context_snapshot(&id).unwrap().source, result.source);
        store
            .append(
                &id,
                "after-restart",
                &[json!({"role":"assistant","content":"Continue in the same conversation."})],
            )
            .unwrap();
        let continued = store.context_snapshot(&id).unwrap();
        assert_eq!(&continued.messages()[..history.len()], &history);
        assert_eq!(
            continued.messages().last().unwrap()["content"],
            "Continue in the same conversation."
        );
        assert_eq!(
            &continued.records[..snapshot.records.len()],
            &snapshot.records
        );
    }

    #[test]
    fn handoff_references_current_user_once_and_does_not_replay_old_tool_calls() {
        let (_directory, mut store, id) = fixture();
        let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Handoff);
        let result = store
            .segment_context(&snapshot, &checkpoint, &prepared, "handoff-event")
            .unwrap();
        let history = result.messages();
        assert_eq!(history.len(), 3);
        assert_eq!(history[2], snapshot.active.last().unwrap().message);
        assert_eq!(history[2]["content"], "CURRENT 原文\r\n第二行😀\n");
        assert_eq!(history[2]["attachment"]["revision"], 7);
        assert!(
            !history
                .iter()
                .any(|message| message.get("tool_calls").is_some() || message["role"] == "tool")
        );
        assert_eq!(&result.records[..snapshot.records.len()], &snapshot.records);
        assert_eq!(
            result.records.last().unwrap().sequence,
            snapshot.source.message_count
        );
    }

    #[test]
    fn changed_revision_does_not_commit_a_stale_summary_or_rewrite_originals() {
        let (directory, mut store, id) = fixture();
        let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Compression);
        let mut other = SessionStore::open(directory.path(), directory.path()).unwrap();
        other
            .update_metadata(
                &id,
                Map::from_iter([("runtime_config".into(), json!({"mode":"atlas","version":2}))]),
                snapshot.source.revision,
            )
            .unwrap();
        let current = other.context_snapshot(&id).unwrap();
        assert!(
            store
                .segment_context(&snapshot, &checkpoint, &prepared, "stale-event")
                .unwrap_err()
                .to_string()
                .contains("revision conflict")
        );
        let result = store.context_snapshot(&id).unwrap();
        assert_eq!(result.source, current.source);
        assert_eq!(result.records, snapshot.records);
        assert_eq!(result.messages(), snapshot.messages());
        assert!(!result.metadata.contains_key(PROJECTION_KEY));
    }

    #[test]
    fn checkpoint_corruption_and_sql_write_failure_both_leave_the_original_projection() {
        let (_directory, mut store, id) = fixture();
        let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Compression);
        let original = fs::read(&checkpoint.path).unwrap();
        fs::write(&checkpoint.path, b"truncated checkpoint").unwrap();
        assert!(
            store
                .segment_context(&snapshot, &checkpoint, &prepared, "corrupt-event")
                .is_err()
        );
        assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
        fs::write(&checkpoint.path, original).unwrap();
        store.db.execute_batch("CREATE TRIGGER reject_context BEFORE INSERT ON messages WHEN json_extract(new.payload,'$.segment_boundary')=1 BEGIN SELECT RAISE(ABORT,'fixture context write failure'); END;").unwrap();
        assert!(
            store
                .segment_context(&snapshot, &checkpoint, &prepared, "sql-event")
                .unwrap_err()
                .to_string()
                .contains("fixture context write failure")
        );
        let current = store.context_snapshot(&id).unwrap();
        assert_eq!(current.source, snapshot.source);
        assert_eq!(current.records, snapshot.records);
        assert_eq!(current.messages(), snapshot.messages());
        let events: i64 = store.db.query_row("SELECT count(*) FROM conversation_events WHERE id IN ('corrupt-event','sql-event')",[],|row|row.get(0)).unwrap();
        assert_eq!(events, 0);
    }

    #[test]
    fn event_reuse_with_changed_summary_or_another_conversation_is_rejected() {
        let (_directory, mut store, id) = fixture();
        let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Compression);
        let first = store
            .segment_context(&snapshot, &checkpoint, &prepared, "one-intent")
            .unwrap();
        let mut changed = prepared.clone();
        changed.summary.push_str("changed payload");
        assert!(
            store
                .segment_context(&snapshot, &checkpoint, &changed, "one-intent")
                .is_err()
        );
        let other = store.create(None, Map::new()).unwrap();
        store
            .append(&other.id, "other-source", &snapshot.messages())
            .unwrap();
        let (other_snapshot, other_checkpoint, other_prepared) =
            ready(&store, &other.id, CompactionKind::Compression);
        assert!(
            store
                .segment_context(
                    &other_snapshot,
                    &other_checkpoint,
                    &other_prepared,
                    "one-intent"
                )
                .is_err()
        );
        assert_eq!(
            store.context_snapshot(&other.id).unwrap().source,
            other_snapshot.source
        );
        assert_eq!(store.context_snapshot(&id).unwrap().source, first.source);
    }

    #[test]
    fn incomplete_tool_group_and_invalid_projection_never_get_silently_dropped() {
        let (_directory, mut store, id) = fixture();
        store.append(&id, "unfinished-tool", &[json!({"role":"assistant","tool_calls":[{"id":"pending","function":{"name":"create_file","arguments":"{}"}}]})]).unwrap();
        let snapshot = store.context_snapshot(&id).unwrap();
        let checkpoint = store.checkpoint_context(&snapshot).unwrap();
        assert!(
            compaction::prepare(
                &snapshot,
                &checkpoint,
                CompactionKind::Handoff,
                &CompactionOptions {
                    max_tokens: 131072,
                    ..Default::default()
                }
            )
            .unwrap_err()
            .to_string()
            .contains("incomplete")
        );
        assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
        store
            .update_metadata(
                &id,
                Map::from_iter([(PROJECTION_KEY.into(), json!({"schema_version":99}))]),
                snapshot.source.revision,
            )
            .unwrap();
        assert!(store.context_snapshot(&id).is_err());
        assert_eq!(
            store.page(&id, None, 60).unwrap().total,
            snapshot.source.message_count
        );
    }

    pub(super) fn resume_input(
        store: &SessionStore,
        id: &str,
    ) -> (ContextSnapshot, i64, Value, Value, Value) {
        let snapshot = store.context_snapshot(id).unwrap();
        let latest = snapshot
            .active
            .iter()
            .rfind(|entry| entry.message["role"] == "user")
            .unwrap();
        let sequence = latest.sequence;
        let user = latest.message.clone();
        let configuration = models::without_secrets(&snapshot.metadata["runtime_config"]);
        let request = json!({"prompt":user["content"],"attachment":user["attachment"],"attachments":user["attachments"],"configuration":configuration});
        (snapshot, sequence, configuration, request, user)
    }

    #[test]
    fn ordinary_resume_binds_exact_source_user_and_configuration_without_new_message() {
        let (_directory, mut store, id) = fixture();
        let other = store.create(None, Map::new()).unwrap();
        let (snapshot, sequence, configuration, request, user) = resume_input(&store, &id);
        let versions: i64 = store
            .db
            .query_row(
                "SELECT count(*) FROM configuration_versions WHERE session_id=?",
                [&id],
                |row| row.get(0),
            )
            .unwrap();
        store
            .begin_resumed_run(
                &snapshot.source,
                sequence,
                "ordinary-resume",
                &configuration,
                &request,
                &user,
            )
            .unwrap();
        let after = store.context_snapshot(&id).unwrap();
        assert_eq!(after.source.message_count, snapshot.source.message_count);
        assert_eq!(after.source.revision, snapshot.source.revision + 1);
        assert_eq!(after.records, snapshot.records);
        assert_eq!(after.messages(), snapshot.messages());
        assert_eq!(after.metadata, snapshot.metadata);
        assert_eq!(store.list().unwrap()["current_session_id"], other.id);
        assert_eq!(
            store
                .db
                .query_row(
                    "SELECT count(*) FROM configuration_versions WHERE session_id=?",
                    [&id],
                    |row| row.get::<_, i64>(0)
                )
                .unwrap(),
            versions
        );
        let task = &store.list_runs(&id, 60).unwrap()[0];
        assert_eq!(task["state"], "running");
        assert_eq!(task["session_id"], id);
        assert_eq!(task["configuration_revision"], snapshot.source.revision);
        assert_eq!(task["configuration"], configuration);
        assert_eq!(task["request"]["prompt"], "CURRENT 原文\r\n第二行😀\n");
        assert_eq!(
            task["request"]["_native_context_resume"]["user_sequence"],
            sequence
        );
        assert_eq!(
            task["request"]["_native_context_resume"]["user_id"],
            snapshot.records[sequence as usize].id
        );
        assert_eq!(
            task["request"]["_native_context_resume"]["user_digest"],
            snapshot.records[sequence as usize].digest
        );
        assert_eq!(task["request"]["_native_started"], true);
    }

    #[test]
    fn resume_rejects_changed_source_sequence_prompt_attachment_or_unknown_user_field() {
        let (_directory, mut store, id) = fixture();
        let (snapshot, sequence, configuration, request, user) = resume_input(&store, &id);
        let mut bad_source = snapshot.source.clone();
        bad_source.sha256 = "wrong-content-identity".into();
        assert!(
            store
                .begin_resumed_run(
                    &bad_source,
                    sequence,
                    "bad-source",
                    &configuration,
                    &request,
                    &user
                )
                .is_err()
        );
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence - 5,
                    "old-user",
                    &configuration,
                    &request,
                    &user
                )
                .is_err()
        );
        let mut bad_prompt = request.clone();
        bad_prompt["prompt"] = json!("CURRENT 原文\n第二行😀");
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "bad-prompt",
                    &configuration,
                    &bad_prompt,
                    &user
                )
                .is_err()
        );
        let mut bad_attachment = request.clone();
        bad_attachment["attachment"]["revision"] = json!(8);
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "bad-attachment",
                    &configuration,
                    &bad_attachment,
                    &user
                )
                .is_err()
        );
        let mut bad_user = user.clone();
        bad_user.as_object_mut().unwrap().remove("attachment");
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "incomplete-user",
                    &configuration,
                    &request,
                    &bad_user
                )
                .is_err()
        );
        let mut bad_configuration = configuration.clone();
        bad_configuration["mode"] = json!("atlas");
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "bad-configuration",
                    &bad_configuration,
                    &request,
                    &user
                )
                .is_err()
        );
        let mut bad_alias = request.clone();
        bad_alias["message"] = json!("different alias");
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "bad-alias",
                    &configuration,
                    &bad_alias,
                    &user
                )
                .is_err()
        );
        let mut wrong_contract = request.clone();
        wrong_contract["promptAlreadySaved"] = json!(true);
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "aio-flag",
                    &configuration,
                    &wrong_contract,
                    &user
                )
                .is_err()
        );
        assert!(store.list_runs(&id, 60).unwrap().is_empty());
        assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
    }

    #[test]
    fn resume_rejects_all_nonterminal_runs_even_if_source_revision_has_not_changed() {
        let (_directory, mut store, id) = fixture();
        let (snapshot, sequence, configuration, request, user) = resume_input(&store, &id);
        let root = store.scope["workspace_path"].as_str().unwrap().to_owned();
        store
            .register_run(
                &id,
                "active-original",
                &configuration,
                snapshot.source.revision,
                &root,
                &request,
            )
            .unwrap();
        for state in [
            "queued",
            "running",
            "stopping",
            "waiting_pause",
            "paused",
            "waiting_user",
            "verifying",
            "waiting_incorporation",
        ] {
            store
                .db
                .execute(
                    "UPDATE task_runs SET state=? WHERE id='active-original'",
                    [state],
                )
                .unwrap();
            assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
            let error = store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "blocked-resume",
                    &configuration,
                    &request,
                    &user,
                )
                .unwrap_err();
            assert!(error.to_string().contains("active or queued"));
        }
        store
            .db
            .execute(
                "UPDATE task_runs SET state='interrupted' WHERE id='active-original'",
                [],
            )
            .unwrap();
        store
            .begin_resumed_run(
                &snapshot.source,
                sequence,
                "allowed-resume",
                &configuration,
                &request,
                &user,
            )
            .unwrap();
        assert_eq!(
            store.context_snapshot(&id).unwrap().records,
            snapshot.records
        );
        assert_eq!(store.list_runs(&id, 60).unwrap().len(), 2);
    }

    #[test]
    fn competing_resume_connections_and_reused_run_ids_cannot_execute_the_intent_twice() {
        let (directory, mut first, id) = fixture();
        let (snapshot, sequence, configuration, request, user) = resume_input(&first, &id);
        let mut second = SessionStore::open(directory.path(), directory.path()).unwrap();
        first
            .begin_resumed_run(
                &snapshot.source,
                sequence,
                "first-resume",
                &configuration,
                &request,
                &user,
            )
            .unwrap();
        assert!(
            second
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "second-resume",
                    &configuration,
                    &request,
                    &user
                )
                .unwrap_err()
                .to_string()
                .contains("revision or source digest")
        );
        let fresh = second.context_snapshot(&id).unwrap();
        assert!(
            second
                .begin_resumed_run(
                    &fresh.source,
                    sequence,
                    "second-resume",
                    &configuration,
                    &request,
                    &user
                )
                .unwrap_err()
                .to_string()
                .contains("active or queued")
        );
        first
            .finish_run(&id, "first-resume", "completed", &json!({"success":true}))
            .unwrap();
        let fresh = second.context_snapshot(&id).unwrap();
        assert!(
            second
                .begin_resumed_run(
                    &fresh.source,
                    sequence,
                    "first-resume",
                    &configuration,
                    &request,
                    &user
                )
                .unwrap_err()
                .to_string()
                .contains("identity already exists")
        );
        assert_eq!(second.list_runs(&id, 60).unwrap().len(), 1);
        assert_eq!(
            second.context_snapshot(&id).unwrap().records,
            snapshot.records
        );
    }

    #[test]
    fn resume_sql_failure_or_deleted_conversation_cannot_publish_a_run_or_restore_data() {
        let (_directory, mut store, id) = fixture();
        let (snapshot, sequence, configuration, request, user) = resume_input(&store, &id);
        store.db.execute_batch("CREATE TRIGGER reject_resume BEFORE INSERT ON task_runs BEGIN SELECT RAISE(ABORT,'fixture resume write failure'); END;").unwrap();
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "failed-write",
                    &configuration,
                    &request,
                    &user
                )
                .unwrap_err()
                .to_string()
                .contains("fixture resume write failure")
        );
        assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
        assert!(store.list_runs(&id, 60).unwrap().is_empty());
        store
            .db
            .execute_batch("DROP TRIGGER reject_resume;")
            .unwrap();
        store.delete(&id).unwrap();
        assert!(
            store
                .begin_resumed_run(
                    &snapshot.source,
                    sequence,
                    "deleted-source",
                    &configuration,
                    &request,
                    &user
                )
                .is_err()
        );
        assert_eq!(
            store
                .db
                .query_row(
                    "SELECT count(*) FROM task_runs WHERE session_id=?",
                    [&id],
                    |row| row.get::<_, i64>(0)
                )
                .unwrap(),
            0
        );
        assert_eq!(
            store
                .db
                .query_row(
                    "SELECT count(*) FROM messages WHERE session_id=?",
                    [&id],
                    |row| row.get::<_, i64>(0)
                )
                .unwrap(),
            snapshot.source.message_count
        );
    }

    #[test]
    fn multipart_resume_preserves_all_content_parts_attachments_and_unknown_fields() {
        let (_directory, mut store, id) = fixture();
        let multipart = json!({"role":"user","content":[{"type":"input_text","text":"完整正文\r\n😀\n"},{"type":"local_image","file_path":"图像.png","token_estimate":1024}],"attachments":[{"path":"图像.png","mime_type":"image/png","sha256":"fixture-image-identity"}],"unknown":{"nested":["保留",7]}});
        store
            .append(&id, "multipart-original", std::slice::from_ref(&multipart))
            .unwrap();
        let (snapshot, sequence, configuration, request, user) = resume_input(&store, &id);
        store
            .begin_resumed_run(
                &snapshot.source,
                sequence,
                "multipart-resume",
                &configuration,
                &request,
                &user,
            )
            .unwrap();
        let after = store.context_snapshot(&id).unwrap();
        assert_eq!(after.records, snapshot.records);
        assert_eq!(after.active.last().unwrap().message, multipart);
        let mut changed = user.clone();
        changed["content"][1]["file_path"] = json!("other-image.png");
        let latest = after.source;
        assert!(
            store
                .begin_resumed_run(
                    &latest,
                    sequence,
                    "changed-multipart",
                    &configuration,
                    &request,
                    &changed
                )
                .is_err()
        );
    }
}
