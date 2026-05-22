use crate::ReverieResult;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionRecord {
    pub id: String,
    pub title: String,
    pub project_root: PathBuf,
    pub mode: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionMessage {
    pub role: String,
    pub content: serde_json::Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tool_calls: Vec<serde_json::Value>,
    pub created_at: DateTime<Utc>,
}

impl SessionMessage {
    pub fn new(role: impl Into<String>, content: serde_json::Value) -> Self {
        Self {
            role: role.into(),
            content,
            tool_call_id: None,
            tool_calls: Vec::new(),
            created_at: Utc::now(),
        }
    }

    pub fn with_tool_calls(
        role: impl Into<String>,
        content: serde_json::Value,
        tool_calls: Vec<serde_json::Value>,
    ) -> Self {
        Self {
            role: role.into(),
            content,
            tool_call_id: None,
            tool_calls,
            created_at: Utc::now(),
        }
    }

    pub fn tool_result(tool_call_id: impl Into<String>, content: serde_json::Value) -> Self {
        Self {
            role: "tool".to_string(),
            content,
            tool_call_id: Some(tool_call_id.into()),
            tool_calls: Vec::new(),
            created_at: Utc::now(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionTranscript {
    pub id: String,
    pub record: SessionRecord,
    #[serde(default)]
    pub messages: Vec<SessionMessage>,
    #[serde(default)]
    pub events: Vec<serde_json::Value>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileCheckpoint {
    pub relative_path: PathBuf,
    pub sha256: String,
    pub size: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Checkpoint {
    pub id: String,
    pub label: String,
    pub project_root: PathBuf,
    pub created_at: DateTime<Utc>,
    pub files: Vec<FileCheckpoint>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OperationRecord {
    pub id: String,
    pub operation_type: String,
    pub description: String,
    pub timestamp: DateTime<Utc>,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptRunResult {
    pub success: bool,
    pub output_text: String,
    pub error: Option<String>,
    pub mode: String,
    pub project_root: PathBuf,
    pub events: Vec<serde_json::Value>,
}

impl PromptRunResult {
    pub fn to_json_value(&self) -> serde_json::Value {
        serde_json::json!({
            "success": self.success,
            "output_text": self.output_text,
            "error": self.error,
            "mode": self.mode,
            "project_root": self.project_root,
            "events": self.events,
        })
    }
}

#[derive(Debug, Clone)]
pub struct SessionStore {
    root: PathBuf,
}

impl SessionStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn list(&self) -> ReverieResult<Vec<SessionRecord>> {
        let index_path = self.root.join("sessions.json");
        if !index_path.is_file() {
            return Ok(Vec::new());
        }
        let text = std::fs::read_to_string(index_path)?;
        Ok(serde_json::from_str(&text)?)
    }

    pub fn save_index(&self, records: &[SessionRecord]) -> ReverieResult<()> {
        std::fs::create_dir_all(&self.root)?;
        std::fs::write(
            self.root.join("sessions.json"),
            serde_json::to_string_pretty(records)?,
        )?;
        Ok(())
    }

    pub fn create(
        &self,
        title: impl Into<String>,
        project_root: PathBuf,
        mode: String,
    ) -> ReverieResult<SessionRecord> {
        let mut records = self.list()?;
        let now = Utc::now();
        let record = SessionRecord {
            id: format!("session-{}", now.timestamp_millis()),
            title: title.into(),
            project_root,
            mode,
            created_at: now,
            updated_at: now,
        };
        records.push(record.clone());
        self.save_index(&records)?;
        self.save_transcript(&SessionTranscript {
            id: record.id.clone(),
            record: record.clone(),
            messages: Vec::new(),
            events: Vec::new(),
            updated_at: now,
        })?;
        Ok(record)
    }

    pub fn ensure_active(
        &self,
        title: impl Into<String>,
        project_root: PathBuf,
        mode: impl Into<String>,
    ) -> ReverieResult<SessionRecord> {
        if let Some(id) = self.active_id()? {
            if let Some(record) = self.find(&id)? {
                return Ok(record);
            }
        }
        let record = self.create(title, project_root, mode.into())?;
        self.set_active(&record.id)?;
        Ok(record)
    }

    pub fn find(&self, id: &str) -> ReverieResult<Option<SessionRecord>> {
        Ok(self.list()?.into_iter().find(|record| record.id == id))
    }

    pub fn rename(&self, id: &str, title: impl Into<String>) -> ReverieResult<SessionRecord> {
        let mut records = self.list()?;
        let title = title.into();
        let mut renamed = None;
        for record in &mut records {
            if record.id == id {
                record.title = title.clone();
                record.updated_at = Utc::now();
                renamed = Some(record.clone());
                break;
            }
        }
        let record = renamed
            .ok_or_else(|| crate::ReverieError::InvalidInput(format!("session not found: {id}")))?;
        self.save_index(&records)?;
        Ok(record)
    }

    pub fn delete(&self, id: &str) -> ReverieResult<bool> {
        let mut records = self.list()?;
        let before = records.len();
        records.retain(|record| record.id != id);
        let removed = records.len() != before;
        if removed {
            self.save_index(&records)?;
            let session_file = self.root.join(format!("{id}.json"));
            if session_file.is_file() {
                std::fs::remove_file(session_file)?;
            }
            let transcript_file = self.transcript_path(id);
            if transcript_file.is_file() {
                std::fs::remove_file(transcript_file)?;
            }
        }
        Ok(removed)
    }

    pub fn clear(&self, id: &str) -> ReverieResult<SessionRecord> {
        let mut records = self.list()?;
        let mut cleared = None;
        for record in &mut records {
            if record.id == id {
                record.updated_at = Utc::now();
                cleared = Some(record.clone());
                break;
            }
        }
        let record = cleared
            .ok_or_else(|| crate::ReverieError::InvalidInput(format!("session not found: {id}")))?;
        self.save_index(&records)?;
        let session_file = self.root.join(format!("{id}.json"));
        let now = Utc::now();
        std::fs::write(
            session_file,
            serde_json::to_string_pretty(&serde_json::json!({
                "id": id,
                "messages": [],
                "updated_at": now
            }))?,
        )?;
        self.save_transcript(&SessionTranscript {
            id: id.to_string(),
            record: record.clone(),
            messages: Vec::new(),
            events: Vec::new(),
            updated_at: now,
        })?;
        Ok(record)
    }

    pub fn set_active(&self, id: &str) -> ReverieResult<SessionRecord> {
        let record = self
            .find(id)?
            .ok_or_else(|| crate::ReverieError::InvalidInput(format!("session not found: {id}")))?;
        std::fs::create_dir_all(&self.root)?;
        std::fs::write(
            self.root.join("active_session.json"),
            serde_json::to_string_pretty(&serde_json::json!({
                "id": record.id,
                "updated_at": Utc::now()
            }))?,
        )?;
        Ok(record)
    }

    pub fn active_id(&self) -> ReverieResult<Option<String>> {
        let path = self.root.join("active_session.json");
        if !path.is_file() {
            return Ok(None);
        }
        let value: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(path)?)?;
        Ok(value
            .get("id")
            .and_then(serde_json::Value::as_str)
            .map(str::to_string))
    }

    pub fn load_transcript(&self, id: &str) -> ReverieResult<Option<SessionTranscript>> {
        let path = self.transcript_path(id);
        if path.is_file() {
            return Ok(Some(serde_json::from_str(&std::fs::read_to_string(path)?)?));
        }
        let Some(record) = self.find(id)? else {
            return Ok(None);
        };
        let legacy_path = self.root.join(format!("{id}.json"));
        let messages = if legacy_path.is_file() {
            let value: serde_json::Value =
                serde_json::from_str(&std::fs::read_to_string(legacy_path)?)?;
            value
                .get("messages")
                .and_then(serde_json::Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(session_message_from_value)
                .collect()
        } else {
            Vec::new()
        };
        Ok(Some(SessionTranscript {
            id: id.to_string(),
            record,
            messages,
            events: Vec::new(),
            updated_at: Utc::now(),
        }))
    }

    pub fn load_active_transcript(&self) -> ReverieResult<Option<SessionTranscript>> {
        let Some(id) = self.active_id()? else {
            return Ok(None);
        };
        self.load_transcript(&id)
    }

    pub fn append_messages(
        &self,
        id: &str,
        messages: &[SessionMessage],
        events: &[serde_json::Value],
    ) -> ReverieResult<SessionTranscript> {
        let Some(mut transcript) = self.load_transcript(id)? else {
            return Err(crate::ReverieError::InvalidInput(format!(
                "session not found: {id}"
            )));
        };
        transcript.messages.extend_from_slice(messages);
        transcript.events.extend_from_slice(events);
        transcript.updated_at = Utc::now();
        transcript.record.updated_at = transcript.updated_at;

        let mut records = self.list()?;
        for record in &mut records {
            if record.id == id {
                record.updated_at = transcript.updated_at;
                break;
            }
        }
        self.save_index(&records)?;
        self.save_transcript(&transcript)?;
        Ok(transcript)
    }

    pub fn compacted_messages_for_context(
        &self,
        id: &str,
        max_messages: usize,
    ) -> ReverieResult<Vec<SessionMessage>> {
        let Some(transcript) = self.load_transcript(id)? else {
            return Ok(Vec::new());
        };
        if transcript.messages.len() <= max_messages {
            return Ok(transcript.messages);
        }
        let keep = max_messages.max(1);
        Ok(transcript
            .messages
            .into_iter()
            .rev()
            .take(keep)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect())
    }

    fn transcript_path(&self, id: &str) -> PathBuf {
        self.root.join(format!("{id}.transcript.json"))
    }

    fn save_transcript(&self, transcript: &SessionTranscript) -> ReverieResult<()> {
        std::fs::create_dir_all(&self.root)?;
        std::fs::write(
            self.transcript_path(&transcript.id),
            serde_json::to_string_pretty(transcript)?,
        )?;
        Ok(())
    }
}

fn session_message_from_value(value: &serde_json::Value) -> Option<SessionMessage> {
    let role = value.get("role").and_then(serde_json::Value::as_str)?;
    let content = value
        .get("content")
        .cloned()
        .unwrap_or_else(|| serde_json::Value::String(String::new()));
    Some(SessionMessage {
        role: role.to_string(),
        content,
        tool_call_id: value
            .get("tool_call_id")
            .and_then(serde_json::Value::as_str)
            .map(str::to_string),
        tool_calls: value
            .get("tool_calls")
            .and_then(serde_json::Value::as_array)
            .cloned()
            .unwrap_or_default(),
        created_at: Utc::now(),
    })
}

#[derive(Debug, Clone)]
pub struct CheckpointStore {
    root: PathBuf,
}

impl CheckpointStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn list(&self) -> ReverieResult<Vec<Checkpoint>> {
        let index_path = self.root.join("checkpoints.json");
        if !index_path.is_file() {
            return Ok(Vec::new());
        }
        Ok(serde_json::from_str(&std::fs::read_to_string(index_path)?)?)
    }

    pub fn create(
        &self,
        project_root: impl AsRef<Path>,
        label: impl Into<String>,
        requested_paths: &[PathBuf],
    ) -> ReverieResult<Checkpoint> {
        let project_root = project_root.as_ref().to_path_buf();
        let now = Utc::now();
        let checkpoint_id = format!("checkpoint-{}", now.timestamp_millis());
        let checkpoint_dir = self.root.join(&checkpoint_id).join("files");
        std::fs::create_dir_all(&checkpoint_dir)?;

        let paths = if requested_paths.is_empty() {
            collect_workspace_files(&project_root)?
        } else {
            requested_paths
                .iter()
                .map(|path| project_root.join(path))
                .collect::<Vec<_>>()
        };

        let mut files = Vec::new();
        for source in paths {
            if !source.is_file() {
                continue;
            }
            let relative = source
                .strip_prefix(&project_root)
                .unwrap_or(&source)
                .to_path_buf();
            let target = checkpoint_dir.join(&relative);
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::copy(&source, &target)?;
            let data = std::fs::read(&source)?;
            let sha256 = format!("{:x}", Sha256::digest(&data));
            files.push(FileCheckpoint {
                relative_path: relative,
                sha256,
                size: data.len() as u64,
            });
        }

        let checkpoint = Checkpoint {
            id: checkpoint_id,
            label: label.into(),
            project_root,
            created_at: now,
            files,
        };
        let mut all = self.list()?;
        all.push(checkpoint.clone());
        self.save_index(&all)?;
        std::fs::write(
            self.root.join(&checkpoint.id).join("checkpoint.json"),
            serde_json::to_string_pretty(&checkpoint)?,
        )?;
        Ok(checkpoint)
    }

    pub fn restore(
        &self,
        project_root: impl AsRef<Path>,
        checkpoint_id: &str,
    ) -> ReverieResult<Checkpoint> {
        let project_root = project_root.as_ref();
        let checkpoint_path = self.root.join(checkpoint_id).join("checkpoint.json");
        let checkpoint: Checkpoint =
            serde_json::from_str(&std::fs::read_to_string(&checkpoint_path)?)?;
        let files_root = self.root.join(checkpoint_id).join("files");
        for file in &checkpoint.files {
            let source = files_root.join(&file.relative_path);
            let target = project_root.join(&file.relative_path);
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::copy(source, target)?;
        }
        Ok(checkpoint)
    }

    fn save_index(&self, records: &[Checkpoint]) -> ReverieResult<()> {
        std::fs::create_dir_all(&self.root)?;
        std::fs::write(
            self.root.join("checkpoints.json"),
            serde_json::to_string_pretty(records)?,
        )?;
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct OperationStore {
    root: PathBuf,
}

impl OperationStore {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    pub fn list(&self) -> ReverieResult<Vec<OperationRecord>> {
        let path = self.root.join("operations.json");
        if !path.is_file() {
            return Ok(Vec::new());
        }
        Ok(serde_json::from_str(&std::fs::read_to_string(path)?)?)
    }

    pub fn append(
        &self,
        operation_type: impl Into<String>,
        description: impl Into<String>,
        metadata: serde_json::Value,
    ) -> ReverieResult<OperationRecord> {
        let mut records = self.list()?;
        let now = Utc::now();
        let record = OperationRecord {
            id: format!("operation-{}", now.timestamp_millis()),
            operation_type: operation_type.into(),
            description: description.into(),
            timestamp: now,
            metadata,
        };
        records.push(record.clone());
        std::fs::create_dir_all(&self.root)?;
        std::fs::write(
            self.root.join("operations.json"),
            serde_json::to_string_pretty(&records)?,
        )?;
        Ok(record)
    }
}

fn collect_workspace_files(root: &Path) -> ReverieResult<Vec<PathBuf>> {
    fn visit(acc: &mut Vec<PathBuf>, root: &Path, current: &Path) -> ReverieResult<()> {
        for entry in std::fs::read_dir(current)? {
            let entry = entry?;
            let path = entry.path();
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if name == ".git" || name == "target" || name == ".reverie" {
                continue;
            }
            if path.is_dir() {
                visit(acc, root, &path)?;
            } else if path.is_file() {
                acc.push(path.strip_prefix(root).unwrap_or(&path).to_path_buf());
            }
        }
        Ok(())
    }
    let mut relative_paths = Vec::new();
    visit(&mut relative_paths, root, root)?;
    Ok(relative_paths
        .into_iter()
        .map(|path| root.join(path))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempfile::TempDir;

    #[test]
    fn transcript_round_trips_and_context_compaction_keeps_full_history() {
        let temp = TempDir::new().unwrap();
        let project = temp.path().join("project");
        std::fs::create_dir_all(&project).unwrap();
        let store = SessionStore::new(temp.path().join("sessions"));

        let record = store
            .create("Test session", project, "reverie".to_string())
            .unwrap();
        store.set_active(&record.id).unwrap();

        store
            .append_messages(
                &record.id,
                &[
                    SessionMessage::new("user", json!("first")),
                    SessionMessage::new("assistant", json!("second")),
                    SessionMessage::new("user", json!("third")),
                ],
                &[json!({"type": "stream", "content": "second"})],
            )
            .unwrap();

        let active = store.load_active_transcript().unwrap().unwrap();
        assert_eq!(active.id, record.id);
        assert_eq!(active.messages.len(), 3);
        assert_eq!(active.events.len(), 1);

        let compacted = store.compacted_messages_for_context(&record.id, 2).unwrap();
        assert_eq!(compacted.len(), 2);
        assert_eq!(compacted[0].content, json!("second"));
        assert_eq!(compacted[1].content, json!("third"));

        let full = store.load_transcript(&record.id).unwrap().unwrap();
        assert_eq!(full.messages.len(), 3);
    }
}
