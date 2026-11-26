use super::*;
use reverie_protocol::{
    ActivatePluginRequest, PluginControlRequest, PluginSourceKind, PluginSourceRequest,
    PreparePluginRequest,
};
use serde_json::{Value, json};
use std::{fs, path::Path};
use tokio_util::sync::CancellationToken;

fn directory() -> tempfile::TempDir {
    let root = std::env::current_dir()
        .unwrap()
        .join(".runtime/extension-integration-tests");
    fs::create_dir_all(&root).unwrap();
    tempfile::tempdir_in(root).unwrap()
}
fn fixture(path: &Path, content: &str, permission: &str) {
    fs::create_dir_all(path.join("skills/sample")).unwrap();
    fs::create_dir_all(path.join("hooks")).unwrap();
    fs::write(
        path.join("LICENSE"),
        "Fixture source authored for Reverie tests; MIT.\n",
    )
    .unwrap();
    fs::write(
        path.join("plugin.json"),
        serde_json::to_vec(
            &json!({"name":"fixture","version":"1.0.0","license":"MIT","permissions":[permission]}),
        )
        .unwrap(),
    )
    .unwrap();
    fs::write(
        path.join("skills/sample/SKILL.md"),
        format!("---\nname: sample\ndescription: fixture\n---\n{content}\n"),
    )
    .unwrap();
    fs::write(path.join("hooks/hooks.json"),r#"{"hooks":{"PreToolUse":[{"matcher":"Write","hooks":[{"type":"command","command":"echo fixture-hook"}]}]}}"#).unwrap();
}
async fn prepare(store: &PluginStore, app: &Path, source: &Path, id: Option<&str>) -> Value {
    store
        .prepare(
            app,
            PreparePluginRequest {
                source: PluginSourceRequest {
                    kind: PluginSourceKind::Directory,
                    location: Some(source.to_string_lossy().into()),
                    revision: None,
                    subdirectory: None,
                    entry_id: None,
                    sha256: None,
                    signing_key: None,
                    require_signature: None,
                },
                plugin_id: id.map(str::to_owned),
                operation_id: None,
                expected_revision: None,
            },
            &CancellationToken::new(),
        )
        .await
        .unwrap()
}
fn activate(store: &PluginStore, candidate: &Value, profile: Option<&str>) -> crate::Result<Value> {
    store.activate(ActivatePluginRequest {
        plugin_id: candidate["plugin_id"].as_str().unwrap().into(),
        candidate_sha256: candidate["candidate"]["sha256"].as_str().unwrap().into(),
        approved_sha256: Some(candidate["candidate"]["sha256"].as_str().unwrap().into()),
        approved_profile_sha256: profile.map(str::to_owned),
        expected_revision: None,
    })
}
fn control(value: Value) -> PluginControlRequest {
    serde_json::from_value(value).unwrap()
}
fn trust_and_enable(store: &PluginStore, candidate: &Value) {
    let id = &candidate["plugin_id"];
    let hash = &candidate["candidate"]["sha256"];
    let profile = &candidate["candidate"]["approval_profile_sha256"];
    store.control("setPluginTrust",control(json!({"pluginId":id,"trusted":true,"candidate_sha256":hash,"approval_profile_sha256":profile}))).unwrap();
    store
        .control(
            "setPluginEnabled",
            control(json!({"pluginId":id,"enabled":true})),
        )
        .unwrap();
}

#[tokio::test]
async fn local_import_requires_exact_content_and_explicit_trust_and_hooks() {
    let app = directory();
    let source = directory();
    fixture(source.path(), "完整指令 😀", "read");
    let store = PluginStore::new(app.path()).unwrap();
    let candidate = prepare(&store, app.path(), source.path(), None).await;
    let id = candidate["plugin_id"].as_str().unwrap();
    assert!(store.leases(app.path(), &|| false).unwrap().is_empty());
    assert!(
        store
            .activate(ActivatePluginRequest {
                plugin_id: id.into(),
                candidate_sha256: candidate["candidate"]["sha256"].as_str().unwrap().into(),
                approved_sha256: None,
                approved_profile_sha256: None,
                expected_revision: None
            })
            .is_err()
    );
    activate(&store, &candidate, None).unwrap();
    assert!(
        store
            .control(
                "setPluginEnabled",
                control(json!({"pluginId":id,"enabled":true}))
            )
            .is_err()
    );
    assert!(
        store
            .control(
                "setPluginTrust",
                control(json!({"pluginId":id,"trusted":true}))
            )
            .is_err()
    );
    trust_and_enable(&store, &candidate);
    let leases = store.leases(app.path(), &|| false).unwrap();
    assert_eq!(leases.len(), 1);
    assert!(!leases[0].hooks_enabled);
    assert!(
        leases[0]
            .text("skills/sample/SKILL.md")
            .unwrap()
            .contains("完整指令 😀")
    );
    assert!(
        store
            .control(
                "setPluginHooks",
                control(json!({"pluginId":id,"hooks_enabled":true}))
            )
            .is_err()
    );
    store.control("setPluginHooks",control(json!({"pluginId":id,"hooks_enabled":true,"approval_profile_sha256":candidate["candidate"]["approval_profile_sha256"]}))).unwrap();
    assert!(store.leases(app.path(), &|| false).unwrap()[0].hooks_enabled);
    assert!(
        store
            .inspect(id, None)
            .unwrap()
            .to_string()
            .contains("echo fixture-hook")
    );
    let restored = PluginStore::new(app.path()).unwrap();
    assert!(restored.state(None).unwrap().records[0].trusted);
}

#[tokio::test]
async fn atomic_update_pins_old_tasks_and_rollback_checks_actual_content() {
    let app = directory();
    let source = directory();
    fixture(source.path(), "原版本正文", "read");
    let store = PluginStore::new(app.path()).unwrap();
    let first = prepare(&store, app.path(), source.path(), None).await;
    activate(&store, &first, None).unwrap();
    trust_and_enable(&store, &first);
    let old = store.leases(app.path(), &|| false).unwrap().pop().unwrap();
    fixture(source.path(), "新版本正文", "read");
    let second = prepare(&store, app.path(), source.path(), Some(&old.id)).await;
    assert_eq!(
        first["candidate"]["approval_profile_sha256"],
        second["candidate"]["approval_profile_sha256"]
    );
    activate(&store, &second, None).unwrap();
    assert!(
        old.text("skills/sample/SKILL.md")
            .unwrap()
            .contains("原版本正文")
    );
    let new = store.leases(app.path(), &|| false).unwrap().pop().unwrap();
    assert!(
        new.text("skills/sample/SKILL.md")
            .unwrap()
            .contains("新版本正文")
    );
    store
        .control("rollbackPlugin", control(json!({"pluginId":old.id})))
        .unwrap();
    assert_eq!(
        store.state(None).unwrap().records[0].active_sha256,
        old.sha256()
    );
    fs::write(new.root.join("skills/sample/SKILL.md"), "篡改正文").unwrap();
    assert!(
        store
            .control("rollbackPlugin", control(json!({"pluginId":old.id})))
            .is_err()
    );
    assert_eq!(
        store.state(None).unwrap().records[0].active_sha256,
        old.sha256()
    );
    assert!(new.text("skills/sample/SKILL.md").is_err());
}

#[tokio::test]
async fn permission_expansion_pauses_switch_and_workspace_enable_is_independent() {
    let app = directory();
    let source = directory();
    let project = directory();
    fixture(source.path(), "first", "read");
    let store = PluginStore::new(app.path()).unwrap();
    let first = prepare(&store, app.path(), source.path(), None).await;
    activate(&store, &first, None).unwrap();
    trust_and_enable(&store, &first);
    let id = first["plugin_id"].as_str().unwrap();
    store
        .control(
            "setPluginEnabled",
            control(json!({"pluginId":id,"projectRoot":project.path(),"enabled":false})),
        )
        .unwrap();
    assert!(store.leases(project.path(), &|| false).unwrap().is_empty());
    assert_eq!(store.leases(app.path(), &|| false).unwrap().len(), 1);
    fixture(source.path(), "second", "write");
    let second = prepare(&store, app.path(), source.path(), Some(id)).await;
    assert!(activate(&store, &second, None).is_err());
    assert_eq!(
        store.state(None).unwrap().records[0].active_sha256,
        first["candidate"]["sha256"]
    );
    activate(
        &store,
        &second,
        second["candidate"]["approval_profile_sha256"].as_str(),
    )
    .unwrap();
    assert!(!store.state(None).unwrap().records[0].hooks_enabled);
    let revision = store.state(None).unwrap().revision;
    assert!(
        store
            .control(
                "setPluginEnabled",
                control(json!({"pluginId":id,"enabled":false,"expected_revision":revision-1}))
            )
            .is_err()
    );
    assert_eq!(store.state(None).unwrap().revision, revision);
    let bytes = fs::read(store.root().join("active.json")).unwrap();
    fs::write(store.root().join("active.json"), "{\"schema\":\"future\"}").unwrap();
    assert!(store.state(None).is_err());
    assert_eq!(
        fs::read(store.root().join("active.json")).unwrap(),
        b"{\"schema\":\"future\"}"
    );
    fs::write(store.root().join("active.json"), bytes).unwrap();
}

#[tokio::test]
async fn fixed_git_source_is_real_and_archive_stage_does_not_keep_build_cache() {
    let app = directory();
    let source = directory();
    fixture(source.path(), "Git source", "read");
    for arguments in [
        vec!["init"],
        vec!["add", "."],
        vec![
            "-c",
            "user.name=Reverie Fixture",
            "-c",
            "user.email=fixture@invalid.test",
            "commit",
            "-m",
            "fixture",
        ],
    ] {
        assert!(
            std::process::Command::new("git")
                .arg("-C")
                .arg(source.path())
                .args(arguments)
                .output()
                .unwrap()
                .status
                .success()
        );
    }
    let store = PluginStore::new(app.path()).unwrap();
    let result = store
        .prepare(
            app.path(),
            PreparePluginRequest {
                source: PluginSourceRequest {
                    kind: PluginSourceKind::Git,
                    location: Some(source.path().to_string_lossy().into()),
                    revision: None,
                    subdirectory: None,
                    entry_id: None,
                    sha256: None,
                    signing_key: None,
                    require_signature: None,
                },
                plugin_id: None,
                operation_id: None,
                expected_revision: None,
            },
            &CancellationToken::new(),
        )
        .await
        .unwrap();
    assert_eq!(result["candidate"]["verification"], "fixed_git");
    assert_eq!(
        result["candidate"]["source"]["commit"]
            .as_str()
            .unwrap()
            .len(),
        40
    );
    store
        .activate(ActivatePluginRequest {
            plugin_id: result["plugin_id"].as_str().unwrap().into(),
            candidate_sha256: result["candidate"]["sha256"].as_str().unwrap().into(),
            approved_sha256: None,
            approved_profile_sha256: None,
            expected_revision: None,
        })
        .unwrap();
    let install = store.state(None).unwrap().records[0].install_dir.clone();
    assert_eq!(
        fs::read_dir(Path::new(&install).parent().unwrap())
            .unwrap()
            .count(),
        2
    );
    assert!(store.leases(app.path(), &|| false).unwrap().is_empty());
}
