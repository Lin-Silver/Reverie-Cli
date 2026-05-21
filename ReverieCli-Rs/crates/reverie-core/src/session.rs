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
        Ok(record)
    }
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
