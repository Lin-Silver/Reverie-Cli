use reverie_protocol::{Reply, Request, kernel_info};
use serde_json::{Map, Value, json};
use std::{io, path::PathBuf};

pub struct Kernel {
    project_root: PathBuf,
}

impl Kernel {
    pub fn new(project_root: PathBuf) -> io::Result<Self> {
        let project_root = project_root.canonicalize()?;
        if !project_root.is_dir() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Project path must be a directory.",
            ));
        }
        Ok(Self { project_root })
    }

    pub fn dispatch(&mut self, request: Request) -> Reply {
        let kind = request.action.trim();
        let fields = match kind {
            "hello" => json!({
                "protocol_version": 1, "project_root": self.project_root,
                "kernel": kernel_info(),
                "capabilities": { "actions": ["hello", "shutdown"] }
            }),
            "shutdown" => Value::Object(Map::new()),
            action => return Reply::error(request.id, format!("Unknown action: {action}")),
        };
        Reply::new(
            Some(request.id),
            if kind == "hello" { "ready" } else { "shutdown" },
            fields.as_object().cloned().unwrap_or_default(),
        )
    }
}
