use super::*;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::{Arc, Mutex},
};
use tokio_util::sync::CancellationToken;

#[tokio::test]
#[ignore = "Requires the Node loopback fixture; run scripts/verification/rust-mcp-smoke.mjs"]
async fn native_protocol_rpc() {
    let root = PathBuf::from(std::env::var_os("REVERIE_MCP_SMOKE_ROOT").expect("smoke root"));
    let repository = crate::config::canonical_project(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.."),
    )
    .unwrap();
    let fixture = repository.join("scripts/verification/rust-mcp-smoke.mjs");
    let node = std::env::var("REVERIE_MCP_NODE").expect("Node executable");
    let base = std::env::var("REVERIE_MCP_FIXTURE_URL").expect("loopback server");
    let project = root.join("工作区");
    fs::create_dir_all(&project).unwrap();
    let events = Arc::new(Mutex::new(Vec::new()));
    let captured = events.clone();
    let notify: Notify = Arc::new(move |value| captured.lock().unwrap().push(value));
    let cancel = CancellationToken::new();
    let mut checks = Vec::new();
    for (transport, raw) in [
        (
            "stdio",
            json!({"type":"stdio","command":node,"args":[fixture,"--serve-stdio","repeat","repeat"],
            "env":{"MCP_FIXTURE_SECRET":"fixture-private-secret","MCP_FIXTURE_AUDIT":root.join("stdio-audit.jsonl")},"timeout":1200}),
        ),
        (
            "http",
            json!({"type":"http","url":format!("{base}/http"),"headers":{"Authorization":"Bearer fixture-private-secret"},"timeout":1200}),
        ),
        (
            "sse",
            json!({"type":"sse","url":format!("{base}/sse"),"headers":{"Authorization":"Bearer fixture-private-secret"},"timeout":1200}),
        ),
    ] {
        let runtime = McpRuntime::new();
        let mut configuration = raw.clone();
        let untrusted = ServerConfig::parse(transport, "manual", &configuration).unwrap();
        let untrusted_snapshot = runtime
            .discover(
                &[untrusted],
                &project,
                &BTreeMap::new(),
                notify.clone(),
                &cancel,
            )
            .await
            .unwrap();
        assert!(untrusted_snapshot.tools.is_empty());
        assert_eq!(untrusted_snapshot.servers[0]["status"], "trust_required");
        if transport == "stdio" {
            assert!(!root.join("stdio-audit.jsonl").exists());
        }
        configuration["trust"] = json!(true);
        let server = ServerConfig::parse(transport, "manual", &configuration).unwrap();
        let snapshot = runtime
            .discover(
                std::slice::from_ref(&server),
                &project,
                &BTreeMap::new(),
                notify.clone(),
                &cancel,
            )
            .await
            .unwrap();
        assert_eq!(
            snapshot.servers[0]["status"],
            "partial",
            "{transport}: {}",
            snapshot.public()
        );
        assert_eq!(snapshot.servers[0]["protocol_version"], "2025-06-18");
        assert!(
            snapshot
                .tools
                .iter()
                .all(|tool| !["app_only", "broken"].contains(&tool.tool_name.as_str()))
        );
        let tool = |name: &str| {
            snapshot
                .tools
                .iter()
                .find(|tool| tool.tool_name == name)
                .unwrap()
                .name
                .clone()
        };
        let echo = snapshot.prepare_tool(&tool("echo")).unwrap();
        let result = echo
            .call_approved(json!({"message":"中文🙂"}), &BTreeMap::new(), &cancel)
            .await;
        assert!(result.success, "{transport}: {result:?}");
        assert!(result.output.contains("中文🙂"));
        assert!(
            !serde_json::to_string(&result)
                .unwrap()
                .contains("fixture-private-secret")
        );
        assert!(!serde_json::to_string(&result).unwrap().contains("_meta"));
        let resource = snapshot
            .read_resource(&server.id(), "fixture://note", &BTreeMap::new(), &cancel)
            .await
            .unwrap();
        assert_eq!(resource["contents"][0]["text"], "fixture resource");
        let prompt = snapshot
            .get_prompt(
                &server.id(),
                "fixture-prompt",
                json!({"name":"reader"}),
                &BTreeMap::new(),
                &cancel,
            )
            .await
            .unwrap();
        assert!(
            prompt["messages"][0]["content"]["text"]
                .as_str()
                .unwrap()
                .contains("reader")
        );
        let failure = snapshot
            .prepare_tool(&tool("fail"))
            .unwrap()
            .call_approved(json!({}), &BTreeMap::new(), &cancel)
            .await;
        assert!(!failure.success);
        assert_eq!(failure.output, "fixture tool failure");
        assert_eq!(failure.data["delivery"], "completed");
        let rpc_failure = snapshot
            .prepare_tool(&tool("rpc_error"))
            .unwrap()
            .call_approved(json!({}), &BTreeMap::new(), &cancel)
            .await;
        assert!(!rpc_failure.success);
        assert_eq!(rpc_failure.data["delivery"], "completed");
        assert!(
            !rpc_failure
                .error
                .unwrap()
                .contains("fixture-private-secret")
        );
        let resource_failure = snapshot
            .read_resource(&server.id(), "fixture://failure", &BTreeMap::new(), &cancel)
            .await
            .unwrap_err();
        assert!(
            !resource_failure
                .to_string()
                .contains("fixture-private-secret")
        );
        for arguments in [json!({}), json!({"message":7})] {
            let invalid = echo
                .call_approved(arguments, &BTreeMap::new(), &cancel)
                .await;
            assert_eq!(invalid.status, "not_started");
            assert_eq!(invalid.data["delivery"], "not_started");
        }
        if transport == "stdio" {
            let calls = fs::read_to_string(root.join("stdio-audit.jsonl"))
                .unwrap()
                .lines()
                .map(|line| serde_json::from_str::<Value>(line).unwrap())
                .filter(|value| value["method"] == "tools/call" && value["tool"] == "echo")
                .count();
            assert_eq!(
                calls, 1,
                "Invalid arguments must not reach the stdio server."
            );
        }
        let progress = snapshot
            .prepare_tool(&tool("progress"))
            .unwrap()
            .call_approved(json!({}), &BTreeMap::new(), &cancel)
            .await;
        assert!(progress.success);
        let event_text = serde_json::to_string(&*events.lock().unwrap()).unwrap();
        assert!(event_text.contains("mcp.progress"));
        assert!(!event_text.contains("fixture-private-secret"));
        let rotation = snapshot
            .prepare_tool(&tool("rotate"))
            .unwrap()
            .call_approved(json!({}), &BTreeMap::new(), &cancel)
            .await;
        assert!(rotation.success);
        let obsolete = echo
            .call_approved(
                json!({"message":"must not execute"}),
                &BTreeMap::new(),
                &cancel,
            )
            .await;
        assert_eq!(obsolete.status, "not_started");
        let next = runtime
            .discover(
                std::slice::from_ref(&server),
                &project,
                &BTreeMap::new(),
                notify.clone(),
                &cancel,
            )
            .await
            .unwrap();
        assert_ne!(
            snapshot.servers[0]["generation"],
            next.servers[0]["generation"]
        );
        let hang = next
            .tools
            .iter()
            .find(|tool| tool.tool_name == "hang")
            .unwrap();
        let cancelled = next
            .prepare_tool(&hang.name)
            .unwrap()
            .call_approved(json!({}), &BTreeMap::new(), &cancel)
            .await;
        assert_eq!(cancelled.status, "unknown");
        assert_eq!(cancelled.data["delivery"], "unknown");
        let after_timeout = next
            .tools
            .iter()
            .find(|tool| tool.tool_name == "echo")
            .unwrap();
        let obsolete = next
            .prepare_tool(&after_timeout.name)
            .unwrap()
            .call_approved(
                json!({"message":"must not replay after timeout"}),
                &BTreeMap::new(),
                &cancel,
            )
            .await;
        assert_eq!(obsolete.status, "not_started");
        runtime.retain_configurations(&project, &[]).unwrap();
        runtime.close().await;
        checks.push(format!("{transport}: real RPC, pagination, roots, resources, prompts, trust, private fields, errors, generation and timeout"));
    }
    fs::write(
        root.join("native-result.json"),
        serde_json::to_vec_pretty(&json!({"checks":checks})).unwrap(),
    )
    .unwrap();
}
