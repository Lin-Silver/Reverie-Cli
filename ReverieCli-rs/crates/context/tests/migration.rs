use reverie_context::ContextEngine;
use rusqlite::{Connection, OpenFlags, params};
use sha2::{Digest, Sha256};
use std::fs;

#[cfg(windows)]
#[test]
fn nested_execution_database_paths_beyond_max_path_open_and_resume() {
    let dir = tempfile::tempdir().unwrap();
    let project = dir.path().join("project");
    fs::create_dir_all(&project).unwrap();
    fs::write(project.join("logic.py"), "def marker(): return 1\n").unwrap();
    let database = dir
        .path()
        .join("a".repeat(90))
        .join("b".repeat(90))
        .join("c".repeat(90))
        .join("context.sqlite3");
    let mut engine = ContextEngine::open(&project, &database).unwrap();
    engine.index(false).unwrap();
    drop(engine);
    let engine = ContextEngine::from_database(&database).unwrap();
    assert_eq!(
        engine.query("marker", 10, 12000).unwrap()[0].file_path,
        "logic.py"
    );
}

#[test]
fn version_two_migration_backs_up_committed_wal_and_preserves_rebuild_recovery() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("project");
    fs::create_dir_all(&root).unwrap();
    let source = "def marker():\n    return 'original_marker'\n";
    fs::write(root.join("logic.py"), source).unwrap();
    let root = root.canonicalize().unwrap();
    let database = dir.path().join("context.sqlite3");
    let original = Connection::open(&database).unwrap();
    original
        .execute_batch(include_str!("fixtures/rust-schema-v2.sql"))
        .unwrap();
    original.execute_batch("PRAGMA application_id=1381385029; PRAGMA user_version=2; PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0;").unwrap();
    original
        .execute(
            "UPDATE state SET root=?1,revision=7",
            [root.to_string_lossy()],
        )
        .unwrap();
    let hash = Sha256::digest(source)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    original
        .execute(
            "INSERT INTO files VALUES(1,'logic.py',?1,0,1,?2,?3)",
            params![source.len() as i64, hash, source],
        )
        .unwrap();
    original
        .execute(
            "INSERT INTO chunks VALUES(1,1,'logic.marker','FUNCTION',1,2,?1)",
            [source],
        )
        .unwrap();
    original
        .execute(
            "INSERT INTO content_search(rowid,body,subwords) VALUES(1,?1,'marker')",
            [source],
        )
        .unwrap();
    original
        .execute(
            "INSERT INTO chunk_search(rowid,name,body,subwords) VALUES(1,'marker',?1,'marker')",
            [source],
        )
        .unwrap();
    let mut engine = ContextEngine::open(&root, &database).unwrap();
    assert_eq!(engine.status().unwrap()["revision"], 7);
    assert_eq!(engine.status().unwrap()["structure_ready"], false);
    assert_eq!(
        engine.query("original_marker", 10, 12000).unwrap()[0].content,
        source.trim_end()
    );
    let backup = fs::read_dir(dir.path())
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .find(|path| {
            path.file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("rust-context-v2-before-")
        })
        .unwrap();
    let snapshot = Connection::open_with_flags(&backup, OpenFlags::SQLITE_OPEN_READ_ONLY).unwrap();
    assert_eq!(
        snapshot
            .query_row("PRAGMA integrity_check", [], |row| row.get::<_, String>(0))
            .unwrap(),
        "ok"
    );
    assert_eq!(
        snapshot
            .query_row("PRAGMA user_version", [], |row| row.get::<_, i64>(0))
            .unwrap(),
        2
    );
    assert_eq!(
        snapshot
            .query_row("SELECT revision FROM state", [], |row| row.get::<_, i64>(0))
            .unwrap(),
        7
    );
    assert_eq!(
        snapshot
            .query_row("SELECT body FROM files", [], |row| row.get::<_, String>(0))
            .unwrap(),
        source
    );
    assert_eq!(
        snapshot
            .query_row(
                "SELECT count(*) FROM content_search WHERE content_search MATCH 'marker'",
                [],
                |row| row.get::<_, i64>(0)
            )
            .unwrap(),
        1
    );
    assert!(engine.index_with_cancel(false, &|| true).is_err());
    assert_eq!(engine.status().unwrap()["revision"], 7);
    drop(engine);
    let mut engine = ContextEngine::open(&root, &database).unwrap();
    assert_eq!(engine.index(false).unwrap()["revision"], 8);
    assert_eq!(engine.status().unwrap()["structure_ready"], true);
    assert_eq!(
        engine
            .lookup(&serde_json::json!({"query_type":"symbol","query":"marker"}))
            .unwrap()["symbol"]["name"],
        "marker"
    );
    let restored = dir.path().join("restored.sqlite3");
    snapshot
        .backup("main", &restored, None::<fn(rusqlite::backup::Progress)>)
        .unwrap();
    let mut recovery = ContextEngine::open(&root, &restored).unwrap();
    assert_eq!(recovery.status().unwrap()["revision"], 7);
    assert_eq!(
        recovery.query("original_marker", 10, 12000).unwrap()[0].content,
        source.trim_end()
    );
    assert_eq!(recovery.index(false).unwrap()["revision"], 8);
    assert_eq!(recovery.index(false).unwrap()["indexed"], 0);
}
