use super::{
    tests::{fixture, ready, resume_input},
    *,
};
use std::cell::Cell;

#[cfg(windows)]
#[test]
fn long_windows_checkpoint_publishes_and_verifies_without_changing_its_managed_path() {
    use std::os::windows::ffi::OsStrExt;

    let directory = tempfile::Builder::new()
        .prefix("context-long-")
        .tempdir_in(env!("CARGO_MANIFEST_DIR"))
        .unwrap();
    let units = directory.path().as_os_str().encode_wide().count();
    let base = directory
        .path()
        .join("x".repeat(210usize.saturating_sub(units + 1).max(16)));
    let mut store = SessionStore::open(&base, directory.path()).unwrap();
    let session = store.create(Some("原生长路径😀"), Map::new()).unwrap();
    store
        .append(
            &session.id,
            "long-path-source",
            &[json!({"role":"user","content":"完整原文\r\n第二行😀\n","attachment":{"path":"原文.png"}})],
        )
        .unwrap();
    let snapshot = store.context_snapshot(&session.id).unwrap();
    let expected_path = store.checkpoint_path(&snapshot.source);
    assert!(expected_path.as_os_str().encode_wide().count() > 260);
    let checkpoint = store.checkpoint_context(&snapshot).unwrap();
    assert_eq!(checkpoint.path, expected_path);
    store
        .verify_context_checkpoint(&snapshot, &checkpoint)
        .unwrap();
    let saved: CheckpointDocument =
        serde_json::from_slice(&fs::read(&checkpoint.path).unwrap()).unwrap();
    assert_eq!(saved, checkpoint_document(&snapshot));
    assert_eq!(store.checkpoint_context(&snapshot).unwrap(), checkpoint);
    assert_eq!(
        store.context_snapshot(&session.id).unwrap().source,
        snapshot.source
    );
}

#[test]
fn rejected_commit_guard_rolls_back_the_entire_context_switch() {
    let (_directory, mut store, id) = fixture();
    let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Compression);
    let invoked = Cell::new(0);
    let error = store
        .segment_context_checked(
            &snapshot,
            &checkpoint,
            &prepared,
            "cancelled-before-commit",
            None,
            || -> Result<()> {
                invoked.set(invoked.get() + 1);
                Err("Cancelled before COMMIT.".into())
            },
        )
        .unwrap_err();
    assert!(error.to_string().contains("Cancelled before COMMIT"));
    assert_eq!(invoked.get(), 1);
    let after = store.context_snapshot(&id).unwrap();
    assert_eq!(after.source, snapshot.source);
    assert_eq!(after.records, snapshot.records);
    assert_eq!(after.messages(), snapshot.messages());
    assert_eq!(after.metadata, snapshot.metadata);
    assert_eq!(
        store
            .db
            .query_row(
                "SELECT count(*) FROM conversation_events WHERE id='cancelled-before-commit'",
                [],
                |row| row.get::<_, i64>(0),
            )
            .unwrap(),
        0
    );
    store
        .verify_context_checkpoint(&snapshot, &checkpoint)
        .unwrap();
}

#[test]
fn commit_permission_is_not_released_until_sqlite_commit_is_visible() {
    struct CommitObservation<'a> {
        reader: &'a Connection,
        observed: &'a Cell<bool>,
    }
    impl Drop for CommitObservation<'_> {
        fn drop(&mut self) {
            self.observed.set(
                self.reader
                    .query_row(
                        "SELECT EXISTS(SELECT 1 FROM conversation_events WHERE id='guarded-commit')",
                        [],
                        |row| row.get::<_, bool>(0),
                    )
                    .unwrap(),
            );
        }
    }

    let (_directory, mut store, id) = fixture();
    let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Compression);
    let reader = Connection::open(&store.database_path).unwrap();
    let observed = Cell::new(false);
    store
        .segment_context_checked(
            &snapshot,
            &checkpoint,
            &prepared,
            "guarded-commit",
            None,
            || {
                assert!(
                    !reader
                        .query_row(
                            "SELECT EXISTS(SELECT 1 FROM conversation_events WHERE id='guarded-commit')",
                            [],
                            |row| row.get::<_, bool>(0),
                        )
                        .unwrap()
                );
                Ok(CommitObservation {
                    reader: &reader,
                    observed: &observed,
                })
            },
        )
        .unwrap();
    assert!(
        observed.get(),
        "The permission must still be held during COMMIT"
    );
}

#[test]
fn context_switch_checks_other_connections_live_runs_and_allows_only_its_own_run() {
    let (directory, mut store, id) = fixture();
    let (snapshot, checkpoint, prepared) = ready(&store, &id, CompactionKind::Compression);
    store.ensure_reduction_run(&id, None).unwrap();
    let mut other = SessionStore::open(directory.path(), directory.path()).unwrap();
    let configuration = models::without_secrets(&snapshot.metadata["runtime_config"]);
    let root = store.scope["workspace_path"].as_str().unwrap();
    other
        .register_run(
            &id,
            "other-live-run",
            &configuration,
            snapshot.source.revision,
            root,
            &json!({"prompt":"Live task waiting for a model"}),
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
        other
            .db
            .execute(
                "UPDATE task_runs SET state=? WHERE id='other-live-run'",
                [state],
            )
            .unwrap();
        assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
        assert!(store.ensure_reduction_run(&id, None).is_err());
        let guard_called = Cell::new(false);
        assert!(
            store
                .segment_context_checked(
                    &snapshot,
                    &checkpoint,
                    &prepared,
                    "blocked-live-run",
                    None,
                    || {
                        guard_called.set(true);
                        Ok(())
                    },
                )
                .is_err()
        );
        assert!(!guard_called.get());
        assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
        store
            .ensure_reduction_run(&id, Some("other-live-run"))
            .unwrap();
    }
    let tasks = store.list_runs(&id, 60).unwrap();
    let after = store
        .segment_context_checked(
            &snapshot,
            &checkpoint,
            &prepared,
            "allowed-own-run",
            Some("other-live-run"),
            || Ok(()),
        )
        .unwrap();
    assert_eq!(&after.records[..snapshot.records.len()], &snapshot.records);
    assert_eq!(store.list_runs(&id, 60).unwrap(), tasks);
}

#[test]
fn writer_binding_uses_exact_source_and_preserves_originals_configuration_and_selection() {
    let (_directory, mut store, id) = fixture();
    let other = store
        .create(Some("Keep selected conversation"), Map::new())
        .unwrap();
    let (snapshot, sequence, configuration, request, user) = resume_input(&store, &id);
    let versions: Vec<(i64, String, String)> = store
        .db
        .prepare("SELECT revision,payload,created_at FROM configuration_versions WHERE session_id=? ORDER BY revision")
        .unwrap()
        .query_map([&id], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))
        .unwrap()
        .collect::<rusqlite::Result<_>>()
        .unwrap();
    let binding = json!({"novel_id":"same-task","project_dir":"novels/same-task"});
    let bound = store
        .bind_resumed_writer(&snapshot.source, &binding)
        .unwrap();
    assert_eq!(bound.source.session_id, snapshot.source.session_id);
    assert_eq!(bound.source.revision, snapshot.source.revision + 1);
    assert_eq!(bound.source.message_count, snapshot.source.message_count);
    assert_ne!(bound.source.sha256, snapshot.source.sha256);
    assert_eq!(bound.records, snapshot.records);
    assert_eq!(bound.messages(), snapshot.messages());
    let mut expected_metadata = snapshot.metadata.clone();
    expected_metadata.insert("writer_project".into(), binding.clone());
    assert_eq!(bound.metadata, expected_metadata);
    assert_eq!(store.list().unwrap()["current_session_id"], other.id);
    let after_versions: Vec<(i64, String, String)> = store
        .db
        .prepare("SELECT revision,payload,created_at FROM configuration_versions WHERE session_id=? ORDER BY revision")
        .unwrap()
        .query_map([&id], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))
        .unwrap()
        .collect::<rusqlite::Result<_>>()
        .unwrap();
    assert_eq!(after_versions, versions);
    assert!(
        store
            .bind_resumed_writer(
                &snapshot.source,
                &json!({"novel_id":"must-not-overwrite","project_dir":"novels/other"}),
            )
            .is_err()
    );
    assert_eq!(store.context_snapshot(&id).unwrap().source, bound.source);
    assert_eq!(
        store
            .bind_resumed_writer(&bound.source, &binding)
            .unwrap()
            .source,
        bound.source
    );
    store
        .begin_resumed_run(
            &bound.source,
            sequence,
            "bound-writer-resume",
            &configuration,
            &request,
            &user,
        )
        .unwrap();
    assert_eq!(
        store.context_snapshot(&id).unwrap().records,
        snapshot.records
    );
}

#[test]
fn failed_writer_binding_update_rolls_back_without_refreshing_the_source() {
    let (_directory, mut store, id) = fixture();
    let snapshot = store.context_snapshot(&id).unwrap();
    let mut forged = snapshot.source.clone();
    forged.sha256 = "wrong-source-content".into();
    let binding = json!({"novel_id":"same-task","project_dir":"novels/same-task"});
    assert!(store.bind_resumed_writer(&forged, &binding).is_err());
    assert_eq!(store.context_snapshot(&id).unwrap().source, snapshot.source);
    store
        .db
        .execute_batch("CREATE TRIGGER reject_writer_binding BEFORE UPDATE OF metadata ON conversations BEGIN SELECT RAISE(FAIL,'fixture Writer write failure'); END;")
        .unwrap();
    assert!(
        store
            .bind_resumed_writer(&snapshot.source, &binding)
            .is_err()
    );
    let after = store.context_snapshot(&id).unwrap();
    assert_eq!(after.source, snapshot.source);
    assert_eq!(after.records, snapshot.records);
    assert_eq!(after.metadata, snapshot.metadata);
}
