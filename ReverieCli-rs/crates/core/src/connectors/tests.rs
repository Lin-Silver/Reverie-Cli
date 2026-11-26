use super::*;
use crate::mcp::{AuthorizationHeaders, McpRuntime};
use std::{fs, path::PathBuf};

async fn audit(client: &reqwest::Client, base: &str) -> Value {
    client
        .get(format!("{base}/audit"))
        .send()
        .await
        .unwrap()
        .json()
        .await
        .unwrap()
}
async fn authorize(
    manager: &ConnectorManager,
    server: &ServerConfig,
    client: &reqwest::Client,
    choice: AuthorizationChoice,
    notify: Notify,
    cancel: &CancellationToken,
) -> Value {
    let discovery = manager.discover(server, cancel).await.unwrap();
    let pending = manager
        .begin_authorization(server, discovery.id(), choice, notify, cancel)
        .await
        .unwrap();
    let response = client
        .get(pending["authorization_url"].as_str().unwrap())
        .send()
        .await
        .unwrap();
    assert_eq!(response.status(), reqwest::StatusCode::FOUND);
    let callback = response.headers()["location"].to_str().unwrap();
    assert_eq!(
        client.get(callback).send().await.unwrap().status(),
        reqwest::StatusCode::OK
    );
    manager
        .complete_authorization(
            server,
            pending["authorization_id"].as_str().unwrap(),
            cancel,
        )
        .await
        .unwrap()
}
fn assert_no_plaintext_credentials(directory: &Path) {
    for entry in fs::read_dir(directory).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            assert_no_plaintext_credentials(&path);
        } else {
            let bytes = fs::read(path).unwrap();
            let text = String::from_utf8_lossy(&bytes);
            for secret in [
                "oauth-initial-",
                "oauth-refreshed-",
                "oauth-refresh-",
                "fixture-client-secret",
                "fixture-api-secret",
            ] {
                assert!(
                    !text.contains(secret),
                    "A credential appeared outside system storage."
                );
            }
        }
    }
}

#[tokio::test]
#[ignore = "Requires Node loopback OAuth and an available OS credential vault; run scripts/verification/rust-oauth-smoke.mjs"]
async fn native_oauth_authorization_and_vault() {
    let root = PathBuf::from(std::env::var_os("REVERIE_OAUTH_SMOKE_ROOT").expect("smoke root"));
    let base = std::env::var("REVERIE_OAUTH_FIXTURE_URL").expect("loopback fixture");
    let app = root.join("application");
    let project = root.join("工作区");
    fs::create_dir_all(&app).unwrap();
    fs::create_dir_all(&project).unwrap();
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .retry(reqwest::retry::never())
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .unwrap();
    let config = json!({"type":"http","url":format!("{base}/mcp"),"trust":true,"headers":{"X-Configuration-Secret":"fixture-config-secret"}});
    let server = ServerConfig::parse("oauth-fixture", "manual", &config).unwrap();
    let cancel = CancellationToken::new();
    let events = Arc::new(Mutex::new(Vec::new()));
    let captured = events.clone();
    let notify: Notify = Arc::new(move |event| captured.lock().unwrap().push(event));
    let mut manager = ConnectorManager::new(&app).unwrap();
    let mut checks = Vec::new();
    let large = json!({"payload":"fixture-vault-long-secret".repeat(800)});
    manager
        .credentials
        .put("large-vault-fixture", &large)
        .await
        .unwrap();
    assert_eq!(
        manager
            .credentials
            .get::<Value>("large-vault-fixture")
            .await
            .unwrap(),
        Some(large.clone())
    );
    manager
        .credentials
        .put("large-vault-fixture", &json!({"payload":"small"}))
        .await
        .unwrap();
    manager
        .credentials
        .put("large-vault-fixture", &large)
        .await
        .unwrap();
    manager
        .credentials
        .remove("large-vault-fixture")
        .await
        .unwrap();
    assert!(
        manager
            .credentials
            .get::<Value>("large-vault-fixture")
            .await
            .unwrap()
            .is_none()
    );
    checks.push(
        "Actual OS vault handles a 16+ KiB credential, large/small replacement and removal".into(),
    );
    let discovery = manager.discover(&server, &cancel).await.unwrap();
    assert_eq!(
        discovery.public()["authorization_servers"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    assert_eq!(audit(&client, &base).await["registrations"], 0);
    let choice = AuthorizationChoice {
        issuer: format!("{base}/issuer-primary"),
        scopes: vec!["files:read".into()],
        ..Default::default()
    };
    assert!(
        manager
            .begin_authorization(&server, discovery.id(), choice, notify.clone(), &cancel)
            .await
            .is_err()
    );
    assert_eq!(audit(&client, &base).await["registrations"], 0);
    let pending = manager
        .begin_authorization(
            &server,
            discovery.id(),
            AuthorizationChoice {
                issuer: format!("{base}/issuer-primary"),
                scopes: vec!["files:read".into()],
                confirmed: true,
                ..Default::default()
            },
            notify.clone(),
            &cancel,
        )
        .await
        .unwrap();
    let authorization = client
        .get(pending["authorization_url"].as_str().unwrap())
        .send()
        .await
        .unwrap();
    let callback = authorization.headers()["location"].to_str().unwrap();
    let mut invalid = reqwest::Url::parse(callback).unwrap();
    let query = invalid
        .query_pairs()
        .map(|(name, value)| {
            if name == "state" {
                (name.into_owned(), "invalid".into())
            } else {
                (name.into_owned(), value.into_owned())
            }
        })
        .collect::<Vec<_>>();
    invalid.set_query(None);
    invalid.query_pairs_mut().extend_pairs(query);
    assert_eq!(
        client.get(invalid).send().await.unwrap().status(),
        reqwest::StatusCode::BAD_REQUEST
    );
    assert_eq!(
        client.get(callback).send().await.unwrap().status(),
        reqwest::StatusCode::OK
    );
    let authorized = manager
        .complete_authorization(
            &server,
            pending["authorization_id"].as_str().unwrap(),
            &cancel,
        )
        .await
        .unwrap();
    assert_eq!(authorized["status"], "authorized");
    assert!(
        manager
            .complete_authorization(
                &server,
                pending["authorization_id"].as_str().unwrap(),
                &cancel
            )
            .await
            .is_err()
    );
    checks.push("Public metadata, OAuth/OIDC discovery, explicit issuer/scopes, PKCE, dynamic registration, real loopback callback, one-time exchange".to_owned());
    let headers = manager.headers(&server, &cancel).await.unwrap();
    assert!(headers["authorization"].starts_with("Bearer oauth-refreshed-"));
    assert_eq!(audit(&client, &base).await["refreshes"], 1);
    let runtime = McpRuntime::new();
    let auth = AuthorizationHeaders::from([(server.id(), headers.clone())]);
    let snapshot = runtime
        .discover(
            std::slice::from_ref(&server),
            &project,
            &auth,
            notify.clone(),
            &cancel,
        )
        .await
        .unwrap();
    assert_eq!(
        snapshot.servers[0]["status"],
        "ready",
        "{}",
        snapshot.public()
    );
    let result = snapshot
        .prepare_tool(&snapshot.tools[0].name)
        .unwrap()
        .call_approved(json!({"message":"authenticated RPC"}), &headers, &cancel)
        .await;
    assert!(result.success);
    assert!(
        !serde_json::to_string(&result)
            .unwrap()
            .contains("oauth-refreshed-")
    );
    let needs_write = snapshot
        .tools
        .iter()
        .find(|tool| tool.tool_name == "needs-write")
        .unwrap();
    let scope_failure = snapshot
        .prepare_tool(&needs_write.name)
        .unwrap()
        .call_approved(json!({}), &headers, &cancel)
        .await;
    assert_eq!(scope_failure.status, "not_started");
    assert_eq!(scope_failure.data["authorization_required"], true);
    assert!(
        !serde_json::to_string(&scope_failure)
            .unwrap()
            .contains("private-needle")
    );
    let challenge = runtime
        .authorization_challenge(&project, &server.id())
        .unwrap()
        .unwrap();
    let step_up = manager
        .discover_with_challenge(&server, Some(&challenge), &cancel)
        .await
        .unwrap();
    assert_eq!(step_up.public()["required_scopes"], json!(["files:write"]));
    assert!(!step_up.public().to_string().contains("private-needle"));
    let registrations = audit(&client, &base).await["registrations"].clone();
    assert!(
        manager
            .begin_authorization(
                &server,
                step_up.id(),
                AuthorizationChoice {
                    issuer: format!("{base}/issuer-primary"),
                    scopes: vec!["files:read".into()],
                    confirmed: true,
                    ..Default::default()
                },
                notify.clone(),
                &cancel
            )
            .await
            .is_err()
    );
    assert_eq!(audit(&client, &base).await["registrations"], registrations);
    assert_eq!(
        manager.status(&server).unwrap()["scopes"],
        json!(["files:read"])
    );
    checks.push("403 scope challenge is private, uses its actual required scope and cannot silently expand the saved grant".into());
    runtime.close().await;
    let record = manager.store.get(&server.id()).unwrap().unwrap();
    manager.close().await;
    manager = ConnectorManager::new(&app).unwrap();
    assert_eq!(manager.headers(&server, &cancel).await.unwrap(), headers);
    assert_eq!(audit(&client, &base).await["refreshes"], 1);
    checks.push(format!("Actual {} OS vault write/read, token refresh/rotation, authenticated MCP tool, restart restoration and credential redaction",std::env::consts::OS));
    let changed = ServerConfig::parse(
        "oauth-fixture",
        "manual",
        &json!({"type":"http","url":format!("{base}/another-mcp"),"trust":true}),
    )
    .unwrap();
    assert_eq!(
        manager.status(&changed).unwrap()["status"],
        "target_changed"
    );
    assert!(manager.headers(&changed, &cancel).await.is_err());
    let revoked = manager.revoke(&server, &cancel).await.unwrap();
    assert_eq!(revoked["server_revocation"], "accepted");
    assert_eq!(revoked["pending_credential_cleanup"], 0);
    assert!(
        manager
            .credentials
            .get::<StoredCredential>(&record.credential_id)
            .await
            .unwrap()
            .is_none()
    );
    let rejected = client
        .post(format!("{base}/mcp"))
        .header("authorization", &headers["authorization"])
        .json(&json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}))
        .send()
        .await
        .unwrap();
    assert_eq!(rejected.status(), reqwest::StatusCode::UNAUTHORIZED);
    checks.push("Target change blocks credential reuse; HTTP token revocation, rejected revoked token and local vault removal".into());
    let api = ServerConfig::parse("api-fixture", "manual", &config).unwrap();
    assert!(
        manager
            .set_api_key(
                &api,
                "authorization",
                "Bearer fixture-api-secret",
                false,
                &cancel
            )
            .await
            .is_err()
    );
    manager
        .set_api_key(
            &api,
            "authorization",
            "Bearer fixture-api-secret",
            true,
            &cancel,
        )
        .await
        .unwrap();
    assert_eq!(
        manager.headers(&api, &cancel).await.unwrap()["authorization"],
        "Bearer fixture-api-secret"
    );
    manager.revoke(&api, &cancel).await.unwrap();
    checks.push("API key confirmation, secure save/read and local removal".into());
    let preconfigured = ServerConfig::parse("preconfigured-fixture", "manual", &config).unwrap();
    let registrations = audit(&client, &base).await["registrations"].clone();
    authorize(
        &manager,
        &preconfigured,
        &client,
        AuthorizationChoice {
            issuer: format!("{base}/issuer-alternate"),
            scopes: vec!["files:read".into()],
            client_id: Some("preconfigured: a+b".into()),
            client_secret: Some("fixture-client-secret".into()),
            client_auth_method: Some("client_secret_basic".into()),
            confirmed: true,
            ..Default::default()
        },
        notify.clone(),
        &cancel,
    )
    .await;
    manager.headers(&preconfigured, &cancel).await.unwrap();
    manager.revoke(&preconfigured, &cancel).await.unwrap();
    assert_eq!(audit(&client, &base).await["registrations"], registrations);
    checks.push("Preregistered confidential OAuth client uses percent-encoded Basic authentication for exchange, refresh and revocation".into());
    let uncertain = ServerConfig::parse("uncertain-fixture", "manual", &config).unwrap();
    authorize(
        &manager,
        &uncertain,
        &client,
        AuthorizationChoice {
            issuer: format!("{base}/issuer-primary"),
            scopes: vec!["files:read".into()],
            confirmed: true,
            ..Default::default()
        },
        notify.clone(),
        &cancel,
    )
    .await;
    client
        .post(format!("{base}/fixture-control"))
        .json(&json!({"disconnect_refresh":true}))
        .send()
        .await
        .unwrap();
    assert!(manager.headers(&uncertain, &cancel).await.is_err());
    let refreshes = audit(&client, &base).await["refreshes"].clone();
    assert_eq!(
        manager.status(&uncertain).unwrap()["status"],
        "refresh_uncertain"
    );
    assert!(manager.headers(&uncertain, &cancel).await.is_err());
    assert_eq!(audit(&client, &base).await["refreshes"], refreshes);
    manager.revoke(&uncertain, &cancel).await.unwrap();
    checks.push(
        "Disconnected refresh is recorded as uncertain and is never automatically replayed".into(),
    );
    let cancel_server = ServerConfig::parse("cancel-fixture", "manual", &config).unwrap();
    let manager = Arc::new(manager);
    let discovery = manager.discover(&cancel_server, &cancel).await.unwrap();
    let pending = manager
        .begin_authorization(
            &cancel_server,
            discovery.id(),
            AuthorizationChoice {
                issuer: format!("{base}/issuer-primary"),
                scopes: vec!["files:read".into()],
                confirmed: true,
                ..Default::default()
            },
            notify.clone(),
            &cancel,
        )
        .await
        .unwrap();
    let id = pending["authorization_id"].as_str().unwrap().to_owned();
    let worker = manager.clone();
    let worker_server = cancel_server.clone();
    let worker_id = id.clone();
    let worker_cancel = cancel.clone();
    let completion = tokio::spawn(async move {
        worker
            .complete_authorization(&worker_server, &worker_id, &worker_cancel)
            .await
    });
    tokio::time::timeout(std::time::Duration::from_secs(2), async {
        loop {
            if manager
                .pending
                .lock()
                .unwrap()
                .get(&id)
                .unwrap()
                .claimed
                .load(Ordering::Acquire)
            {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    manager.cancel_authorization(&id).unwrap();
    assert!(
        tokio::time::timeout(std::time::Duration::from_secs(2), completion)
            .await
            .unwrap()
            .unwrap()
            .is_err()
    );
    let local = ServerConfig::parse("local-clear-fixture", "manual", &config).unwrap();
    manager
        .set_api_key(
            &local,
            "authorization",
            "Bearer fixture-api-secret-local",
            true,
            &cancel,
        )
        .await
        .unwrap();
    let local_record = manager.store.get(&local.id()).unwrap().unwrap();
    assert_eq!(manager.status(&local).unwrap()["status"], "authorized");
    let mut disabled = local.clone();
    disabled.enabled = false;
    assert_eq!(
        manager.list_configured(&[disabled]).unwrap()["connectors"]
            .as_array()
            .unwrap()
            .iter()
            .find(|record| record["server_id"] == local.id())
            .unwrap()["status"],
        "disabled"
    );
    let mut changed = local.clone();
    changed.endpoint = format!("{base}/mcp?different_target=1");
    assert_eq!(
        manager.status(&changed).unwrap()["status"],
        "target_changed"
    );
    assert_eq!(
        manager.list_configured(&[]).unwrap()["connectors"]
            .as_array()
            .unwrap()
            .iter()
            .find(|record| record["server_id"] == local.id())
            .unwrap()["status"],
        "configuration_missing"
    );
    checks.push("Connector listing binds current configuration and reports disabled, changed or removed targets instead of old authorization".into());
    let discovery = manager.discover(&local, &cancel).await.unwrap();
    let pending = manager
        .begin_authorization(
            &local,
            discovery.id(),
            AuthorizationChoice {
                issuer: format!("{base}/issuer-primary"),
                scopes: vec!["files:read".into()],
                confirmed: true,
                ..AuthorizationChoice::default()
            },
            notify.clone(),
            &cancel,
        )
        .await
        .unwrap();
    let pending_id = pending["authorization_id"].as_str().unwrap();
    let before_clear = audit(&client, &base).await;
    assert!(
        manager
            .clear_local_credentials(&local.id(), false, &cancel)
            .await
            .is_err()
    );
    assert!(manager.store.get(&local.id()).unwrap().is_some());
    assert!(manager.pending.lock().unwrap().contains_key(pending_id));
    let cleared = manager
        .clear_local_credentials(&local.id(), true, &cancel)
        .await
        .unwrap();
    assert_eq!(cleared["server_revocation"], "not_attempted_local_only");
    assert_eq!(cleared["cancelled_authorizations"], 1);
    assert_eq!(cleared["credentials_cleared"], true);
    assert!(manager.store.get(&local.id()).unwrap().is_none());
    assert!(
        manager
            .credentials
            .get::<StoredCredential>(&local_record.credential_id)
            .await
            .unwrap()
            .is_none()
    );
    assert!(!manager.pending.lock().unwrap().contains_key(pending_id));
    assert!(
        manager
            .complete_authorization(&local, pending_id, &cancel)
            .await
            .is_err()
    );
    let repeated = manager
        .clear_local_credentials(&local.id(), true, &cancel)
        .await
        .unwrap();
    assert_eq!(repeated["record_removed"], false);
    assert_eq!(before_clear, audit(&client, &base).await);
    checks.push("Confirmed server_id-only local cleanup cancels pending authorization and removes real OS-vault credentials without any remote request".into());
    assert_no_plaintext_credentials(&app.join(".reverie"));
    let event_text = serde_json::to_string(&*events.lock().unwrap()).unwrap();
    assert!(
        !event_text.contains("oauth-initial-")
            && !event_text.contains("oauth-refresh-")
            && !event_text.contains("fixture-client-secret")
    );
    assert_eq!(manager.list().unwrap()["pending_credential_cleanup"], 0);
    manager.close().await;
    checks.push("Cancellation stops an awaiting completion; metadata/backups/events contain no token or client-secret values".into());
    fs::write(
        root.join("native-result.json"),
        serde_json::to_vec_pretty(&json!({"checks":checks})).unwrap(),
    )
    .unwrap();
}

fn metadata_record(server: &ServerConfig) -> store::Record {
    store::Record {
        server_id: server.id(),
        binding: metadata::binding(server),
        credential_id: "metadata-only-test-identity".into(),
        kind: "api_key".into(),
        resource: metadata::public_url(&server.endpoint),
        issuer: None,
        client_id: None,
        auth_method: None,
        token_endpoint: None,
        revocation_endpoint: None,
        scopes: Vec::new(),
        expires_at: None,
        approved_at: 0,
        api_header: Some("authorization".into()),
        state: "authorized".into(),
    }
}

#[test]
fn configured_connector_listing_does_not_inherit_an_old_target() {
    let directory = tempfile::tempdir().unwrap();
    let manager = ConnectorManager::new(directory.path()).unwrap();
    let server = ServerConfig::parse(
        "fixture",
        "manual",
        &json!({"type":"http","url":"http://127.0.0.1:9/mcp?private_query=needle","trust":true}),
    )
    .unwrap();
    manager.store.put(&metadata_record(&server)).unwrap();
    assert_eq!(
        manager.list().unwrap()["connectors"][0]["status"],
        "configuration_unverified"
    );
    assert_eq!(
        manager
            .list_configured(std::slice::from_ref(&server))
            .unwrap()["connectors"][0]["status"],
        "authorized"
    );
    let mut disabled = server.clone();
    disabled.enabled = false;
    assert_eq!(
        manager.list_configured(&[disabled]).unwrap()["connectors"][0]["status"],
        "disabled"
    );
    let mut untrusted = server.clone();
    untrusted.trusted = false;
    assert_eq!(
        manager.list_configured(&[untrusted]).unwrap()["connectors"][0]["status"],
        "untrusted"
    );
    let mut changed = server;
    changed.endpoint = "http://127.0.0.1:10/mcp".into();
    let projected = manager.list_configured(&[changed]).unwrap();
    assert_eq!(projected["connectors"][0]["status"], "target_changed");
    assert_eq!(projected["connectors"][0]["configuration_current"], false);
    assert_eq!(
        manager.list_configured(&[]).unwrap()["connectors"][0]["status"],
        "configuration_missing"
    );
    assert!(!projected.to_string().contains("private_query"));
}

#[test]
fn credential_retirement_intents_and_metadata_lock_remain_recoverable() {
    let directory = tempfile::tempdir().unwrap();
    let manager = ConnectorManager::new(directory.path()).unwrap();
    let server = ServerConfig::parse(
        "fixture",
        "manual",
        &json!({"type":"http","url":"http://127.0.0.1:9/mcp","trust":true}),
    )
    .unwrap();
    let record = metadata_record(&server);
    manager
        .store
        .prepare_credential(&record.credential_id)
        .unwrap();
    assert!(
        manager
            .store
            .retired()
            .unwrap()
            .contains(&record.credential_id)
    );
    manager.store.put(&record).unwrap();
    assert!(manager.store.retired().unwrap().is_empty());
    manager.store.remove(&server.id()).unwrap();
    assert!(
        manager
            .store
            .retired()
            .unwrap()
            .contains(&record.credential_id)
    );
    let file = fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open(directory.path().join(".reverie/connectors.lock"))
        .unwrap();
    file.lock().unwrap();
    let start = std::time::Instant::now();
    assert!(
        manager
            .store
            .prepare_credential("another-identity")
            .unwrap_err()
            .to_string()
            .contains("busy")
    );
    assert!(start.elapsed() < std::time::Duration::from_secs(1));
}
