use crate::config::{project_data_dir, project_data_name};
use crate::{ReverieError, ReverieResult};
use chrono::{DateTime, Utc};
use reverie_tools::{execute_builtin_tool, ToolInvocation, ToolRegistry};
use serde_json::{json, Value};
use sha1::{Digest as Sha1Digest, Sha1};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

const REGRESSION_SCHEMA_VERSION: &str = "reverie.agent.regression.v1";

pub fn summarize_totals(project_root: &Path) -> ReverieResult<Value> {
    let data_dir = project_data_dir(project_root);
    let usage = build_dashboard_data(&data_dir, project_root)?;
    Ok(json!({
        "workspace": {
            "name": usage.get("workspace_name").cloned().unwrap_or_else(|| json!(workspace_name(project_root))),
            "path": usage.get("workspace_path").cloned().unwrap_or_else(|| json!(normalize_path(project_root))),
            "cache_dir": data_dir,
        },
        "usage": usage,
        "lifecycle": summarize_lifecycle(&data_dir),
        "regression": latest_agent_regression_summary(&data_dir, project_root),
    }))
}

pub async fn run_agent_regression(project_root: &Path) -> ReverieResult<Value> {
    let data_dir = project_data_dir(project_root);
    let root = data_dir.join("agent_regression");
    let workspace = root.join("workspace");
    let summary_path = root.join("summary.json");
    let results_path = root.join("results.jsonl");

    if workspace.exists() {
        std::fs::remove_dir_all(&workspace)?;
    }
    std::fs::create_dir_all(&workspace)?;
    std::fs::write(
        workspace.join("README.md"),
        "# Regression Workspace\n\nstable-sentinel\n",
    )?;

    let mut results = Vec::new();
    results.push(
        regression_result(
            "workspace-read-roundtrip",
            "Read seeded workspace file through file_ops",
            read_seed_file(&workspace).await,
        )
        .await,
    );
    results.push(
        regression_result(
            "workspace-mkdir-visible",
            "Create a directory and observe it through file_ops",
            mkdir_visible(&workspace).await,
        )
        .await,
    );
    results.push(
        regression_result(
            "workspace-boundary-protection",
            "Reject file access outside the regression workspace",
            boundary_protection(&workspace).await,
        )
        .await,
    );
    results.push(
        regression_result(
            "tool-schema-core-surface",
            "Expose core tool schemas in reverie mode",
            tool_schema_core_surface(),
        )
        .await,
    );

    let passed_count = results
        .iter()
        .filter(|result| {
            result
                .get("passed")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        })
        .count();
    let total = results.len();
    let summary = json!({
        "schema": REGRESSION_SCHEMA_VERSION,
        "generated_at": Utc::now().to_rfc3339(),
        "workspace_root": project_root,
        "sandbox_workspace": workspace,
        "passed": passed_count == total,
        "passed_count": passed_count,
        "failed_count": total - passed_count,
        "total": total,
        "score": if total == 0 { 0 } else { ((passed_count as f64 / total as f64) * 100.0).round() as u64 },
        "results": results,
        "summary_path": summary_path,
        "results_path": results_path,
    });

    std::fs::create_dir_all(&root)?;
    std::fs::write(&summary_path, serde_json::to_string_pretty(&summary)?)?;
    append_jsonl(&results_path, &summary)?;
    append_lifecycle_event(
        &data_dir,
        json!({
            "schema": "reverie.lifecycle.audit.v1",
            "timestamp": Utc::now().to_rfc3339(),
            "phase": "regression_complete",
            "tool": "agent_regression",
            "action": "audit",
            "allowed": true,
            "success": summary.get("passed").cloned().unwrap_or(Value::Bool(false)),
            "result": {
                "passed": summary.get("passed").cloned().unwrap_or(Value::Bool(false)),
                "passed_count": passed_count,
                "total": total,
                "score": summary.get("score").cloned().unwrap_or(Value::Number(0.into())),
            }
        }),
    )?;
    Ok(summary)
}

fn build_dashboard_data(data_dir: &Path, project_root: &Path) -> ReverieResult<Value> {
    let stats_path = data_dir.join("workspace_stats.json");
    let raw = read_json_file(&stats_path).unwrap_or_else(|| json!({}));
    let model_rows = object_values(raw.get("model_usage"));
    let session_rows = object_values(raw.get("session_usage"));
    let total_input: u64 = model_rows
        .iter()
        .map(|row| nonnegative_u64(row.get("input_tokens")))
        .sum();
    let total_output: u64 = model_rows
        .iter()
        .map(|row| nonnegative_u64(row.get("output_tokens")))
        .sum();
    let total_calls: u64 = model_rows
        .iter()
        .map(|row| nonnegative_u64(row.get("calls")))
        .sum();

    let mut source_aggregate: BTreeMap<String, SourceBucket> = BTreeMap::new();
    for row in &model_rows {
        let source = clean_string(row.get("source")).unwrap_or_else(|| "standard".to_string());
        let bucket = source_aggregate.entry(source.clone()).or_default();
        bucket.calls += nonnegative_u64(row.get("calls"));
        bucket.input_tokens += nonnegative_u64(row.get("input_tokens"));
        bucket.output_tokens += nonnegative_u64(row.get("output_tokens"));
        if let Some(model) =
            clean_string(row.get("model_display_name")).or_else(|| clean_string(row.get("model")))
        {
            bucket.models.insert(model);
        }
        if let Some(provider) = clean_string(row.get("provider")) {
            bucket.providers.insert(provider);
        }
    }

    let source_rows = source_aggregate
        .into_iter()
        .map(|(source, bucket)| {
            json!({
                "source": source,
                "calls": bucket.calls,
                "input_tokens": bucket.input_tokens,
                "output_tokens": bucket.output_tokens,
                "model_count": bucket.models.len(),
                "provider_count": bucket.providers.len(),
                "models": bucket.models.into_iter().collect::<Vec<_>>(),
                "providers": bucket.providers.into_iter().collect::<Vec<_>>(),
            })
        })
        .collect::<Vec<_>>();

    let workspace_path =
        clean_string(raw.get("workspace_path")).unwrap_or_else(|| normalize_path(project_root));
    let workspace_name =
        clean_string(raw.get("workspace_name")).unwrap_or_else(|| workspace_name(project_root));
    Ok(json!({
        "workspace_id": clean_string(raw.get("workspace_id")).unwrap_or_else(|| workspace_id_for_path(project_root)),
        "workspace_path": workspace_path,
        "workspace_name": workspace_name,
        "created_at": clean_string(raw.get("created_at")).unwrap_or_default(),
        "updated_at": clean_string(raw.get("updated_at")).unwrap_or_default(),
        "total_runtime_seconds": nonnegative_f64(raw.get("total_runtime_seconds")),
        "total_active_seconds": nonnegative_f64(raw.get("total_active_seconds")),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_calls": total_calls,
        "model_usage": model_rows,
        "source_usage": source_rows,
        "session_usage": session_rows,
        "stats_path": stats_path,
    }))
}

fn summarize_lifecycle(data_dir: &Path) -> Value {
    let root = data_dir.join("lifecycle");
    let audit_path = root.join("audit.jsonl");
    let config_path = root.join("hooks.json");
    let records = read_jsonl_tail(&audit_path, 500);
    let denied = records
        .iter()
        .filter(|item| item.get("allowed").and_then(Value::as_bool) == Some(false))
        .count();
    let failures = records
        .iter()
        .filter(|item| item.get("success").and_then(Value::as_bool) == Some(false))
        .count();
    let mut by_tool: BTreeMap<String, u64> = BTreeMap::new();
    let mut by_phase: BTreeMap<String, u64> = BTreeMap::new();
    for item in &records {
        *by_tool
            .entry(clean_string(item.get("tool")).unwrap_or_else(|| "runtime".to_string()))
            .or_default() += 1;
        *by_phase
            .entry(clean_string(item.get("phase")).unwrap_or_else(|| "unknown".to_string()))
            .or_default() += 1;
    }
    let recent = records
        .iter()
        .rev()
        .take(20)
        .cloned()
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<Vec<_>>();
    json!({
        "enabled": true,
        "audit_path": audit_path,
        "config_path": config_path,
        "events": records.len(),
        "denied": denied,
        "failures": failures,
        "by_tool": by_tool,
        "by_phase": by_phase,
        "recent": recent,
        "rules": default_lifecycle_rules(),
    })
}

fn latest_agent_regression_summary(data_dir: &Path, project_root: &Path) -> Value {
    let root = data_dir.join("agent_regression");
    let summary_path = root.join("summary.json");
    read_json_file(&summary_path).unwrap_or_else(|| {
        json!({
            "schema": REGRESSION_SCHEMA_VERSION,
            "generated_at": "",
            "workspace_root": project_root,
            "passed": Value::Null,
            "passed_count": 0,
            "failed_count": 0,
            "total": 0,
            "score": 0,
            "results": [],
            "summary_path": summary_path,
        })
    })
}

async fn regression_result(id: &str, title: &str, result: ReverieResult<String>) -> Value {
    let started = std::time::Instant::now();
    let (passed, detail) = match result {
        Ok(detail) => (true, detail),
        Err(err) => (false, err.to_string()),
    };
    json!({
        "id": id,
        "title": title,
        "passed": passed,
        "duration_ms": started.elapsed().as_millis() as u64,
        "detail": detail,
    })
}

async fn read_seed_file(workspace: &Path) -> ReverieResult<String> {
    let result = execute_builtin_tool(
        workspace,
        ToolInvocation {
            name: "file_ops".to_string(),
            arguments: json!({"operation": "read", "path": "README.md"}),
        },
    )
    .await
    .map_err(|err| ReverieError::Unsupported(err.to_string()))?;
    if !result.success {
        return Err(ReverieError::Unsupported(
            result
                .error
                .unwrap_or_else(|| "file_ops read failed".to_string()),
        ));
    }
    let content = result
        .output
        .get("content")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !content.contains("stable-sentinel") {
        return Err(ReverieError::Unsupported(
            "seed file content did not match".to_string(),
        ));
    }
    Ok("Seed file was read and content matched.".to_string())
}

async fn mkdir_visible(workspace: &Path) -> ReverieResult<String> {
    let created = execute_builtin_tool(
        workspace,
        ToolInvocation {
            name: "file_ops".to_string(),
            arguments: json!({"operation": "mkdir", "path": "artifacts"}),
        },
    )
    .await
    .map_err(|err| ReverieError::Unsupported(err.to_string()))?;
    if !created.success {
        return Err(ReverieError::Unsupported(
            created
                .error
                .unwrap_or_else(|| "file_ops mkdir failed".to_string()),
        ));
    }
    let checked = execute_builtin_tool(
        workspace,
        ToolInvocation {
            name: "file_ops".to_string(),
            arguments: json!({"operation": "exists", "path": "artifacts"}),
        },
    )
    .await
    .map_err(|err| ReverieError::Unsupported(err.to_string()))?;
    if checked.output.get("exists").and_then(Value::as_bool) != Some(true) {
        return Err(ReverieError::Unsupported(
            "created directory was not visible".to_string(),
        ));
    }
    Ok("Directory creation remained workspace-confined.".to_string())
}

async fn boundary_protection(workspace: &Path) -> ReverieResult<String> {
    let result = execute_builtin_tool(
        workspace,
        ToolInvocation {
            name: "file_ops".to_string(),
            arguments: json!({"operation": "read", "path": "../outside.txt"}),
        },
    )
    .await;
    if result.is_ok() {
        return Err(ReverieError::Unsupported(
            "outside workspace read unexpectedly succeeded".to_string(),
        ));
    }
    Ok("Workspace boundary rejected parent traversal.".to_string())
}

fn tool_schema_core_surface() -> ReverieResult<String> {
    let names = ToolRegistry::builtin()
        .visible_for_mode("reverie")
        .into_iter()
        .map(|tool| tool.name)
        .collect::<BTreeSet<_>>();
    let required = ["file_ops", "command_exec", "str_replace_editor"];
    let missing = required
        .into_iter()
        .filter(|name| !names.contains(*name))
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(ReverieError::Unsupported(format!(
            "missing core tool schemas: {}",
            missing.join(", ")
        )));
    }
    Ok("Core tool schemas are visible in reverie mode.".to_string())
}

#[derive(Default)]
struct SourceBucket {
    calls: u64,
    input_tokens: u64,
    output_tokens: u64,
    models: BTreeSet<String>,
    providers: BTreeSet<String>,
}

fn object_values(value: Option<&Value>) -> Vec<Value> {
    let mut rows = value
        .and_then(Value::as_object)
        .map(|object| object.values().cloned().collect::<Vec<_>>())
        .unwrap_or_default();
    rows.sort_by(|left, right| {
        clean_string(right.get("updated_at"))
            .cmp(&clean_string(left.get("updated_at")))
            .then_with(|| {
                clean_string(left.get("model_display_name"))
                    .cmp(&clean_string(right.get("model_display_name")))
            })
    });
    rows
}

fn read_json_file(path: &Path) -> Option<Value> {
    serde_json::from_str(&std::fs::read_to_string(path).ok()?).ok()
}

fn read_jsonl_tail(path: &Path, limit: usize) -> Vec<Value> {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    raw.lines()
        .rev()
        .take(limit)
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect()
}

fn append_jsonl(path: &Path, value: &Value) -> ReverieResult<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)?;
    use std::io::Write;
    writeln!(file, "{}", serde_json::to_string(value)?)?;
    Ok(())
}

fn append_lifecycle_event(data_dir: &Path, value: Value) -> ReverieResult<()> {
    append_jsonl(&data_dir.join("lifecycle").join("audit.jsonl"), &value)
}

fn default_lifecycle_rules() -> Vec<Value> {
    vec![
        json!({"id": "audit-all-tools", "phase": "*", "tool": "*", "action": "audit", "priority": 1000, "source": "builtin", "message": "Record every lifecycle transition."}),
        json!({"id": "deny-shell-delete", "phase": "pre_tool_use", "tool": "command_exec", "action": "deny", "args_contains": "Remove-Item", "priority": 10, "source": "builtin", "message": "Terminal deletion must use the dedicated delete_file tool."}),
        json!({"id": "warn-write-tools", "phase": "pre_tool_use", "tool": "str_replace_editor", "action": "warn", "priority": 100, "source": "builtin", "message": "Write-capable edit tool invoked."}),
    ]
}

fn clean_string(value: Option<&Value>) -> Option<String> {
    let text = value.and_then(Value::as_str).unwrap_or_default().trim();
    (!text.is_empty()).then(|| text.to_string())
}

fn nonnegative_u64(value: Option<&Value>) -> u64 {
    value.and_then(Value::as_u64).unwrap_or(0)
}

fn nonnegative_f64(value: Option<&Value>) -> f64 {
    value.and_then(Value::as_f64).unwrap_or(0.0).max(0.0)
}

fn normalize_path(path: &Path) -> String {
    path.canonicalize()
        .unwrap_or_else(|_| path.to_path_buf())
        .to_string_lossy()
        .replace('\\', "/")
}

fn workspace_name(path: &Path) -> String {
    path.file_name()
        .and_then(|name| name.to_str())
        .map(str::to_string)
        .unwrap_or_else(|| project_data_name(path))
}

fn workspace_id_for_path(path: &Path) -> String {
    let normalized = normalize_path(path).to_ascii_lowercase();
    let mut hasher = Sha1::new();
    hasher.update(normalized.as_bytes());
    let hash = format!("{:x}", hasher.finalize());
    hash[..16].to_string()
}

#[allow(dead_code)]
fn parse_datetime(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|value| value.with_timezone(&Utc))
}
