use super::*;
use crate::Result;
use serde_json::{Value, json};
use std::{
    fs,
    path::Path,
    sync::{Arc, Mutex},
    time::Duration,
};
use tokio_util::sync::CancellationToken;

#[test]
fn configuration_does_not_grant_trust_and_preserves_plugin_language_ids() -> Result<()> {
    let raw = json!({"command":"typescript-language-server","args":["--stdio","--flag","--flag"],"enabled":true,"trusted":true,
        "extensionToLanguage":{".ts":"typescript",".tsx":"typescriptreact",".js":"javascript",".jsx":"javascriptreact"}});
    let config = ServerConfig::parse("typescript", "plugin:test", &raw)?;
    assert!(!config.enabled && !config.trusted);
    assert_eq!(config.args, vec!["--stdio", "--flag", "--flag"]);
    assert_eq!(
        config.language(Path::new("source.tsx")),
        Some("typescriptreact")
    );
    assert_eq!(config.language(Path::new("source.JS")), Some("javascript"));
    assert!(
        ServerConfig::parse(
            "bad",
            "manual",
            &json!({"command":"node","extensions":[".rs"]})
        )
        .is_err()
    );
    assert!(
        ServerConfig::parse(
            "bad",
            "manual",
            &json!({"command":"node","transport":"tcp"})
        )
        .is_err()
    );
    let missing = ServerConfig::parse("needs-language", "manual", &json!({"command":"node"}))?;
    assert!(missing.extension_to_language.is_empty());
    let builtins = builtin_definitions();
    assert_eq!(builtins.len(), 6);
    assert!(
        builtins
            .iter()
            .all(|config| !config.enabled && !config.trusted)
    );
    Ok(())
}

#[test]
fn utf16_positions_roundtrip_emoji_chinese_and_crlf() -> Result<()> {
    let text = "甲😀b\r\n最后\n";
    let before_b = "甲😀".len();
    assert_eq!(
        Position::from_utf8_offset(text, before_b)?,
        Position {
            line: 0,
            character: 3
        }
    );
    assert_eq!(
        Position {
            line: 0,
            character: 3
        }
        .utf8_offset(text)?,
        before_b
    );
    assert!(
        Position {
            line: 0,
            character: 2
        }
        .utf8_offset(text)
        .is_err()
    );
    assert!(Position::from_utf8_offset(text, before_b + 2).is_err());
    assert_eq!(
        Position::from_utf8_offset(text, text.len())?,
        Position {
            line: 2,
            character: 0
        }
    );
    for offset in (0..=text.len()).filter(|offset| text.is_char_boundary(*offset)) {
        if let Ok(position) = Position::from_utf8_offset(text, offset) {
            assert_eq!(position.utf8_offset(text)?, offset);
        }
    }
    assert!(
        Position {
            line: 3,
            character: 0
        }
        .utf8_offset(text)
        .is_err()
    );
    Ok(())
}

#[test]
fn file_uris_and_symlink_targets_cannot_escape_the_project() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let root = directory.path().join("project");
    fs::create_dir(&root)?;
    let root = crate::config::canonical_project(&root)?;
    fs::write(root.join("空 格#😀.rs"), "fn inside() {}\n")?;
    fs::write(
        directory.path().join("outside.rs"),
        "private outside content",
    )?;
    let input = "空 格#😀.rs";
    let path = super::evidence::checked_path(&root, input, true)?;
    let uri = super::evidence::file_uri(&path)?;
    assert_eq!(super::evidence::checked_path(&root, &uri, true)?, path);
    assert!(super::evidence::checked_path(&root, "../outside.rs", true).is_err());
    assert!(super::evidence::checked_path(&root, &format!("{uri}?secret=value"), true).is_err());
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(directory.path().join("outside.rs"), root.join("escape.rs"))?;
        assert!(super::evidence::checked_path(&root, "escape.rs", true).is_err());
    }
    Ok(())
}

#[tokio::test]
async fn content_length_is_bytes_and_bad_frames_are_rejected() -> Result<()> {
    let body = serde_json::to_vec(&json!({"jsonrpc":"2.0","id":1,"result":"中文😀"}))?;
    let mut frame = format!(
        "Content-Length: {}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n",
        body.len()
    )
    .into_bytes();
    frame.extend_from_slice(&body);
    let mut reader = tokio::io::BufReader::new(frame.as_slice());
    assert_eq!(
        super::protocol::read_frame(&mut reader).await?.unwrap()["result"],
        "中文😀"
    );
    for bad in [
        b"Content-Length: 16777217\r\n\r\n".as_slice(),
        b"Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}".as_slice(),
        b"Content-Length: 2\r\nContent-Type: application/vscode-jsonrpc; charset=utf-16\r\n\r\n{}"
            .as_slice(),
        b"Content-Length: 5\r\n\r\n{}".as_slice(),
        b"Content-Length: 2\n\n{}".as_slice(),
    ] {
        assert!(
            super::protocol::read_frame(&mut tokio::io::BufReader::new(bad))
                .await
                .is_err()
        );
    }
    Ok(())
}

fn audit(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap_or_default()
        .lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}
async fn wait_method(path: &Path, method: &str, query: Option<&str>) -> Result<()> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
    loop {
        if audit(path).iter().any(|item| {
            item["method"] == method && query.is_none_or(|query| item["query"] == query)
        }) {
            return Ok(());
        }
        if tokio::time::Instant::now() >= deadline {
            return Err(format!("Fixture did not observe {method}.").into());
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

#[tokio::test]
#[ignore = "Run through scripts/verification/rust-lsp-smoke.mjs with a real Node stdio fixture."]
async fn native_stdio_lifecycle_and_evidence() -> Result<()> {
    let root =
        std::env::var_os("REVERIE_LSP_FIXTURE_ROOT").ok_or("LSP fixture root was not provided.")?;
    let root = crate::config::canonical_project(Path::new(&root))?;
    let node = std::env::var("REVERIE_LSP_FIXTURE_NODE")?;
    let script = std::env::var("REVERIE_LSP_FIXTURE_SCRIPT")?;
    let audit_path = Path::new(&std::env::var("REVERIE_LSP_FIXTURE_AUDIT")?).to_owned();
    let events = Arc::new(Mutex::new(Vec::<Value>::new()));
    let recorded = events.clone();
    let notify: Notify = Arc::new(move |value| {
        recorded.lock().unwrap().push(value);
    });
    let raw = json!({"command":node,"args":[script,"--serve","--duplicate","--duplicate"],
        "extensionToLanguage":{".rs":"rust"},"env":{"LSP_FIXTURE_AUDIT":audit_path,"LSP_FIXTURE_ROOT":root,"LSP_FIXTURE_SECRET":"fixture-private-lsp-secret"},
        "initializationOptions":{"fixture":true},"settings":{"fixture":{"enabled":true}},"request_timeout_ms":800});
    let mut config = ServerConfig::parse("fixture", "manual", &raw)?;
    config.enabled = true;
    config.source_version = "fixture-v1".into();
    let runtime = Arc::new(LspRuntime::new());
    runtime
        .configure(&root, vec![config.clone()], notify.clone())
        .await?;
    assert_eq!(runtime.status(&root)?["servers"][0]["status"], "untrusted");
    let query = |action, query: &str| Query {
        action,
        query: query.into(),
        ..Query::default()
    };
    let token = CancellationToken::new();
    assert!(
        runtime
            .query(&root, query(Action::Diagnostics, "源码 😀.rs"), &token)
            .await
            .is_err()
    );
    assert!(audit(&audit_path).is_empty());
    config.trusted = true;
    runtime
        .configure(&root, vec![config.clone()], notify.clone())
        .await?;
    assert!(
        runtime
            .query(&root, query(Action::Definitions, "../outside.rs"), &token)
            .await
            .is_err()
    );
    let invalid = Query {
        character: 1,
        ..query(Action::Definitions, "源码 😀.rs")
    };
    assert!(runtime.query(&root, invalid, &token).await.is_err());
    assert!(audit(&audit_path).is_empty());

    let diagnostics = runtime
        .query(&root, query(Action::Diagnostics, "源码 😀.rs"), &token)
        .await?;
    assert_eq!(diagnostics["diagnostics"]["received"], true);
    assert_eq!(diagnostics["diagnostics"]["version_verified"], true);
    assert_eq!(diagnostics["document"]["document_version"], 1);
    assert!(diagnostics.to_string().contains("[redacted]"));
    assert!(
        !diagnostics
            .to_string()
            .contains("fixture-private-lsp-secret")
    );
    let symbols = runtime
        .query(&root, query(Action::DocumentSymbols, "源码 😀.rs"), &token)
        .await?;
    assert_eq!(symbols["count"], 2);
    assert_eq!(symbols["document"]["document_version"], 1);
    let definitions = runtime
        .query(
            &root,
            Query {
                character: 5,
                ..query(Action::Definitions, "源码 😀.rs")
            },
            &token,
        )
        .await?;
    assert_eq!(definitions["count"], 1);
    assert_eq!(definitions["items"][0]["range"]["start"]["character"], 5);
    assert_eq!(definitions["static_index_updated"], false);
    let workspace = runtime
        .query(&root, query(Action::WorkspaceSymbols, "symbol"), &token)
        .await?;
    assert_eq!(workspace["count"], 1);
    assert_eq!(workspace["servers"][0]["dropped"], 1);
    assert!(workspace.to_string().contains("language_server_signal"));

    let file = root.join("源码 😀.rs");
    let modified = fs::metadata(&file)?.modified()?;
    fs::write(&file, "😀fn renamed() {}\r\nsecond line\n")?;
    fs::File::options()
        .write(true)
        .open(&file)?
        .set_times(fs::FileTimes::new().set_modified(modified))?;
    let updated = runtime
        .query(&root, query(Action::Diagnostics, "源码 😀.rs"), &token)
        .await?;
    assert_eq!(updated["document"]["document_version"], 2);
    assert_ne!(
        updated["document"]["content_sha256"],
        diagnostics["document"]["content_sha256"]
    );
    tokio::time::sleep(Duration::from_millis(100)).await;
    let updated = runtime
        .query(&root, query(Action::Diagnostics, "源码 😀.rs"), &token)
        .await?;
    assert_eq!(updated["diagnostics"]["version"], 2);
    assert!(
        updated["diagnostics"]["discarded_version_mismatch"]
            .as_u64()
            .unwrap_or(0)
            >= 1
    );
    assert_eq!(
        audit(&audit_path)
            .iter()
            .filter(|item| item["method"] == "textDocument/didOpen")
            .count(),
        1
    );
    assert_eq!(
        audit(&audit_path)
            .iter()
            .filter(|item| item["method"] == "textDocument/didChange")
            .count(),
        1
    );
    wait_method(&audit_path, "client-reply:workspace/applyEdit", None).await?;
    wait_method(&audit_path, "client-reply:client/registerCapability", None).await?;

    let active_runtime = runtime.clone();
    let active_root = root.clone();
    let active = tokio::spawn(async move {
        active_runtime
            .query(
                &active_root,
                Query {
                    query: "delay".into(),
                    ..Query::default()
                },
                &CancellationToken::new(),
            )
            .await
    });
    wait_method(&audit_path, "workspace/symbol", Some("delay")).await?;
    config.source_version = "fixture-v2".into();
    runtime
        .configure(&root, vec![config.clone()], notify.clone())
        .await?;
    let old_result = active.await??;
    assert_eq!(old_result["servers"][0]["source_version"], "fixture-v1");
    let new_result = runtime
        .query(
            &root,
            query(Action::WorkspaceSymbols, "new-version"),
            &token,
        )
        .await?;
    assert_eq!(new_result["servers"][0]["source_version"], "fixture-v2");

    let cancel = CancellationToken::new();
    let cancel_task = cancel.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(80)).await;
        cancel_task.cancel();
    });
    let cancelled = runtime
        .query(&root, query(Action::WorkspaceSymbols, "cancel"), &cancel)
        .await
        .unwrap_err();
    assert_eq!(
        cancelled.downcast_ref::<Failure>().unwrap().kind,
        FailureKind::Cancelled
    );
    assert_eq!(
        cancelled.downcast_ref::<Failure>().unwrap().delivery,
        Delivery::Unknown
    );
    wait_method(&audit_path, "$/cancelRequest", None).await?;
    let failure = runtime
        .query(&root, query(Action::WorkspaceSymbols, "error"), &token)
        .await?;
    assert!(
        failure["errors"][0]["message"]
            .as_str()
            .unwrap()
            .contains("[redacted]")
    );
    assert!(!failure.to_string().contains("fixture-private-lsp-secret"));

    config.source_version = "unversioned".into();
    config
        .env
        .insert("LSP_FIXTURE_UNVERSIONED".into(), "1".into());
    runtime
        .configure(&root, vec![config.clone()], notify.clone())
        .await?;
    let unversioned = runtime
        .query(&root, query(Action::Diagnostics, "源码 😀.rs"), &token)
        .await?;
    assert_eq!(unversioned["diagnostics"]["received"], true);
    assert_eq!(unversioned["diagnostics"]["version_verified"], false);
    fs::remove_file(&file)?;
    runtime.close_document(&root, "源码 😀.rs").await?;
    wait_method(&audit_path, "textDocument/didClose", None).await?;
    fs::write(&file, "😀fn symbol() {}\r\nsecond line\n")?;

    config.source_version = "timeout".into();
    config.request_timeout_ms = 120;
    runtime
        .configure(&root, vec![config.clone()], notify.clone())
        .await?;
    // Wait for this server's fragmented startup exchange before measuring a
    // single intentionally unanswered workspace/symbol request.
    let ready = runtime
        .query(&root, query(Action::Diagnostics, "源码 😀.rs"), &token)
        .await?;
    assert_eq!(ready["diagnostics"]["received"], true);
    let timeout = runtime
        .query(&root, query(Action::WorkspaceSymbols, "hang"), &token)
        .await?;
    assert_eq!(timeout["errors"][0]["delivery"], "unknown");
    assert_eq!(
        audit(&audit_path)
            .iter()
            .filter(|item| item["query"] == "hang")
            .count(),
        1
    );
    runtime.close().await;
    assert!(runtime.status(&root)?["closed"].as_bool().unwrap());
    assert!(
        runtime
            .query(&root, query(Action::WorkspaceSymbols, "closed"), &token)
            .await
            .is_err()
    );
    assert!(
        !events
            .lock()
            .unwrap()
            .iter()
            .any(|event| event.to_string().contains("fixture-private-lsp-secret"))
    );
    fs::write(
        root.join("native-result.json"),
        serde_json::to_vec_pretty(&json!({"status":"passed","checks":[
            "Trust and outside-project/invalid UTF-16 queries cause no process startup",
            "Actual fragmented Content-Length stdio initialization and read-only server request replies",
            "Unicode document/definition/workspace symbols, source hashes and no static-index writes",
            "Hash-based incremental revisions with unchanged mtime and stale diagnostic rejection",
            "Configuration generations retain an in-flight old-version query",
            "Cancellation and timeout send cancelRequest and never automatically replay",
            "Errors, diagnostics and events omit known environment secrets and private server data",
            "Unversioned diagnostics stay unverified; deleted documents close; shutdown reclaims the process tree"
        ]}))?,
    )?;
    Ok(())
}
