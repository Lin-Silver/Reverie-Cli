use crate::scan::{FileEntry, Result, relative_path};
use crate::text::subwords;
use rusqlite::{Connection, OpenFlags, OptionalExtension, TransactionBehavior, params};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::time::Duration;

const SCHEMA_VERSION: i64 = 2;
const APPLICATION_ID: i64 = 0x52564345; // RVCE

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Chunk {
    pub name: String,
    pub symbol: String,
    pub kind: String,
    pub start_line: u32,
    pub end_line: u32,
    #[serde(default)]
    pub signature: String,
    #[serde(default)]
    pub documentation: String,
    #[serde(default)]
    pub body: String,
}

#[derive(Debug, Deserialize)]
pub struct Document {
    #[serde(flatten)]
    pub file: FileEntry,
    #[serde(default)]
    pub body: Option<String>,
    #[serde(default)]
    pub chunks: Vec<Chunk>,
}

#[derive(Debug, Serialize)]
pub struct State {
    pub root: String,
    pub revision: i64,
}

pub struct Catalog {
    db: Connection,
    rebuilding: bool,
}

fn pragma(db: &Connection, key: &str) -> rusqlite::Result<i64> {
    db.pragma_query_value(None, key, |row| row.get(0))
}

fn check_schema(db: &Connection) -> Result<()> {
    if pragma(db, "application_id")? != APPLICATION_ID
        || pragma(db, "user_version")? != SCHEMA_VERSION
    {
        return Err("Incompatible Reverie Context Engine database".into());
    }
    Ok(())
}

pub fn open_readonly(path: &Path) -> Result<Connection> {
    let db = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    db.busy_timeout(Duration::from_secs(10))?;
    check_schema(&db)?;
    Ok(db)
}

pub fn state(db: &Connection) -> rusqlite::Result<State> {
    db.query_row("SELECT root, revision FROM state WHERE id=1", [], |row| {
        Ok(State {
            root: row.get(0)?,
            revision: row.get(1)?,
        })
    })
}

pub fn files(db: &Connection) -> rusqlite::Result<Vec<FileEntry>> {
    db.prepare("SELECT path, size, modified_ns, content_hash FROM files ORDER BY path")?
        .query_map([], |row| {
            Ok(FileEntry {
                path: row.get(0)?,
                size: row.get(1)?,
                modified_ns: row.get(2)?,
                content_hash: row.get(3)?,
            })
        })?
        .collect()
}

impl Catalog {
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            std::fs::create_dir_all(parent)?;
        }
        let mut db = Connection::open(path)?;
        db.busy_timeout(Duration::from_secs(30))?;
        if pragma(&db, "application_id")? == 0 {
            let transaction = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
            if pragma(&transaction, "application_id")? == 0 {
                let tables: i64 = transaction.query_row(
                    "SELECT count(*) FROM sqlite_schema WHERE type='table'",
                    [],
                    |row| row.get(0),
                )?;
                if tables != 0 || pragma(&transaction, "user_version")? != 0 {
                    return Err("Refusing to overwrite an unrelated SQLite database".into());
                }
                transaction.execute_batch(include_str!("schema.sql"))?;
                transaction.pragma_update(None, "application_id", APPLICATION_ID)?;
                transaction.pragma_update(None, "user_version", SCHEMA_VERSION)?;
            }
            transaction.commit()?;
        }
        check_schema(&db)?;
        let journal: String = db.pragma_query_value(None, "journal_mode", |row| row.get(0))?;
        if journal != "wal" {
            db.pragma_update(None, "journal_mode", "WAL")?;
        }
        db.execute_batch("PRAGMA foreign_keys=ON; PRAGMA synchronous=NORMAL")?;
        Ok(Self {
            db,
            rebuilding: false,
        })
    }

    pub fn connection(&self) -> &Connection {
        &self.db
    }

    pub fn begin(&mut self, root: &str, replace: bool, expected_revision: i64) -> Result<()> {
        self.db.execute_batch("BEGIN IMMEDIATE")?;
        if let Err(error) = self.begin_update(root, replace, expected_revision) {
            self.rollback()?;
            return Err(error);
        }
        self.rebuilding = replace;
        Ok(())
    }

    fn begin_update(&self, root: &str, replace: bool, expected_revision: i64) -> Result<()> {
        let current = state(&self.db)?;
        if current.revision != expected_revision {
            return Err("Context index changed while preparing an update".into());
        }
        if !current.root.is_empty() && current.root != root {
            return Err("Context index is bound to a different workspace".into());
        }
        if replace {
            self.db.execute_batch(
                "DELETE FROM chunk_search; DELETE FROM content_search; DELETE FROM chunks; DELETE FROM files;",
            )?;
        }
        if current.root.is_empty() {
            self.db
                .execute("UPDATE state SET root=?1 WHERE id=1", [root])?;
        }
        Ok(())
    }

    pub fn apply(&self, removed: &[String], documents: &[Document]) -> Result<()> {
        if self.db.is_autocommit() {
            return Err("Context index update has not started".into());
        }
        for path in removed {
            self.remove(path)?;
        }
        for document in documents {
            self.insert(document)?;
        }
        Ok(())
    }

    fn remove(&self, path: &str) -> rusqlite::Result<()> {
        let Some(rowid) = self
            .db
            .prepare_cached("SELECT rowid FROM files WHERE path=?1")?
            .query_row([path], |row| row.get::<_, i64>(0))
            .optional()?
        else {
            return Ok(());
        };
        self.db.prepare_cached("DELETE FROM chunk_search WHERE rowid IN (SELECT rowid FROM chunks WHERE file_rowid=?1)")?.execute([rowid])?;
        self.db
            .prepare_cached("DELETE FROM content_search WHERE rowid=?1")?
            .execute([rowid])?;
        self.db
            .prepare_cached("DELETE FROM chunks WHERE file_rowid=?1")?
            .execute([rowid])?;
        self.db
            .prepare_cached("DELETE FROM files WHERE rowid=?1")?
            .execute([rowid])?;
        Ok(())
    }

    fn insert(&self, document: &Document) -> Result<()> {
        let file = &document.file;
        if relative_path(Path::new(&file.path))? != file.path {
            return Err(format!("Non-canonical index path: {}", file.path).into());
        }
        if !self.rebuilding {
            self.remove(&file.path)?;
        }
        let rowid = self
            .db
            .prepare_cached(
                "INSERT INTO files(path,size,modified_ns,indexed,content_hash,body) VALUES (?1,?2,?3,?4,?5,?6)",
            )?
            .insert(params![
                file.path,
                file.size,
                file.modified_ns,
                document.body.is_some()
                ,file.content_hash,document.body
            ])?;
        let Some(body) = &document.body else {
            return Ok(());
        };
        self.db
            .prepare_cached("INSERT INTO content_search(rowid,body,subwords) VALUES (?1,?2,?3)")?
            .execute(params![rowid, body, subwords(&[body], 768)])?;
        for chunk in document.chunks.iter().take(512) {
            self.insert_chunk(rowid, chunk)?;
        }
        Ok(())
    }

    fn insert_chunk(&self, file_rowid: i64, chunk: &Chunk) -> Result<()> {
        if !matches!(
            chunk.kind.as_str(),
            "CLASS"
                | "ENUM"
                | "FUNCTION"
                | "INTERFACE"
                | "MACRO"
                | "METHOD"
                | "MODULE"
                | "NAMESPACE"
                | "PROPERTY"
                | "STRUCT"
                | "TRAIT"
                | "TYPE_ALIAS"
        ) {
            return Ok(());
        }
        let rowid = self.db.prepare_cached("INSERT INTO chunks(file_rowid,symbol,kind,start_line,end_line,body) VALUES (?1,?2,?3,?4,?5,?6)")?
            .insert(params![file_rowid, chunk.symbol, chunk.kind, chunk.start_line.max(1), chunk.end_line.max(1),chunk.body])?;
        let name = [
            chunk.symbol.as_str(),
            &chunk.name,
            &subwords(&[&chunk.name], 512),
            &chunk.kind.to_ascii_lowercase(),
        ]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
        self.db.prepare_cached("INSERT INTO chunk_search(rowid,name,signature,documentation,body,subwords) VALUES (?1,?2,?3,?4,?5,?6)")?
            .execute(params![rowid, name, chunk.signature, chunk.documentation, chunk.body, subwords(&[&chunk.symbol, &chunk.signature, &chunk.body], 192)])?;
        Ok(())
    }

    pub fn commit(&mut self) -> Result<State> {
        if self.db.is_autocommit() {
            return Err("Context index update has not started".into());
        }
        self.db
            .execute("UPDATE state SET revision=revision+1 WHERE id=1", [])?;
        let current = state(&self.db)?;
        self.db.execute_batch("COMMIT")?;
        self.rebuilding = false;
        Ok(current)
    }

    pub fn rollback(&mut self) -> rusqlite::Result<()> {
        if !self.db.is_autocommit() {
            self.db.execute_batch("ROLLBACK")?;
        }
        self.rebuilding = false;
        Ok(())
    }
}

impl Drop for Catalog {
    fn drop(&mut self) {
        let _ = self.rollback();
    }
}
