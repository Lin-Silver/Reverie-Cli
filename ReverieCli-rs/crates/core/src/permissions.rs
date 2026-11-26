use crate::Result;
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{path::Path, time::Duration};

pub(crate) const MODES: [&str; 4] = ["strict", "normal", "auto", "full_access"];
pub(crate) const FALLBACKS: [&str; 2] = ["wait", "deny"];

pub(crate) fn mode(security: &Value) -> &str {
    match security["permission_mode"].as_str().unwrap_or("normal") {
        "default" => "normal",
        "auto_check" => "auto",
        value => value,
    }
}

pub(crate) fn fallback(security: &Value) -> &str {
    security["auto_review_fallback"].as_str().unwrap_or("wait")
}

pub(crate) fn fingerprint(args: &Value) -> Result<String> {
    // Retain every operand and option, including cwd; never persist command text.
    let mut canonical = args.clone();
    canonical.sort_all_objects();
    let digest: String = Sha256::digest(serde_json::to_vec(&canonical)?)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    Ok(digest)
}

pub(crate) fn command_key(args: &Value) -> Result<String> {
    Ok(format!("command_exec:{}", fingerprint(args)?))
}

pub(crate) struct Grants {
    db: Connection,
    project: String,
    session: String,
}

impl Grants {
    pub(crate) fn open(
        app: &Path,
        project: &Path,
        execution: &Path,
        session: &str,
        assistant: bool,
    ) -> Result<Self> {
        let directory = app.join(".reverie/security");
        std::fs::create_dir_all(&directory)?;
        let db = Connection::open(directory.join("approval-grants.sqlite3"))?;
        db.busy_timeout(Duration::from_secs(5))?;
        db.execute_batch(
            "CREATE TABLE IF NOT EXISTS grants(scope TEXT, owner TEXT, capability TEXT,
            PRIMARY KEY(scope,owner,capability)) WITHOUT ROWID",
        )?;
        let project = serde_json::to_string(&json!([assistant, project, execution]))?;
        let session = serde_json::to_string(&json!([project, session]))?;
        Ok(Self {
            db,
            project,
            session,
        })
    }

    pub(crate) fn contains(&self, key: &str) -> Result<bool> {
        Ok(self.db.query_row("SELECT EXISTS(SELECT 1 FROM grants WHERE capability=?1 AND
            ((scope='session' AND owner=?2) OR (scope='project' AND owner=?3) OR (scope='global' AND owner='')))",
            params![key,self.session,self.project], |r| r.get(0))?)
    }

    pub(crate) fn remember(&self, scope: &str, key: &str) -> Result<()> {
        let owner = match scope {
            "session" => self.session.as_str(),
            "project" => self.project.as_str(),
            "global" => "",
            _ => return Err("Invalid persistent approval scope.".into()),
        };
        self.db.execute(
            "INSERT OR IGNORE INTO grants VALUES (?1,?2,?3)",
            params![scope, owner, key],
        )?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_grants_bind_operands_and_options_and_survive_restart_at_the_chosen_scope() {
        let tmp = tempfile::tempdir().unwrap();
        let open =
            |p: &str, s| Grants::open(tmp.path(), Path::new(p), Path::new(p), s, false).unwrap();
        let key = command_key(&json!({"command":"node tool.mjs design","cwd":"a"})).unwrap();
        assert_eq!(
            key,
            command_key(&json!({"cwd":"a","command":"node tool.mjs design"})).unwrap()
        );
        assert_ne!(
            key,
            command_key(&json!({"command":"node tool.mjs export","cwd":"a"})).unwrap()
        );
        assert_ne!(
            key,
            command_key(&json!({"command":"node tool.mjs design","cwd":"b"})).unwrap()
        );
        open("p", "a").remember("session", &key).unwrap();
        assert!(open("p", "a").contains(&key).unwrap());
        assert!(!open("p", "b").contains(&key).unwrap());
        open("p", "a").remember("project", &key).unwrap();
        assert!(open("p", "b").contains(&key).unwrap());
        assert!(!open("q", "a").contains(&key).unwrap());
        assert!(
            !Grants::open(tmp.path(), Path::new("p"), Path::new("q"), "a", false)
                .unwrap()
                .contains(&key)
                .unwrap()
        );
        open("p", "a").remember("global", &key).unwrap();
        assert!(open("q", "b").contains(&key).unwrap());
    }
}
