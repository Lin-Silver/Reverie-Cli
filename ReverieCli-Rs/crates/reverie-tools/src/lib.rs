use anyhow::{anyhow, Result};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::process::Command;

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct ToolSpec {
    pub name: String,
    pub description: String,
    pub category: String,
    pub modes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInvocation {
    pub name: String,
    #[serde(default)]
    pub arguments: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub success: bool,
    pub output: Value,
    pub error: Option<String>,
}

pub struct ToolRegistry {
    tools: Vec<ToolSpec>,
}

impl ToolRegistry {
    pub fn builtin() -> Self {
        let all = [
            (
                "codebase-retrieval",
                "Inspect repository files, symbols, and index data.",
                "retrieval",
            ),
            (
                "git-commit-retrieval",
                "Inspect git history and current repository state.",
                "retrieval",
            ),
            (
                "str_replace_editor",
                "Read and precisely edit workspace text files.",
                "editing",
            ),
            ("create_file", "Create a new workspace file.", "editing"),
            (
                "file_ops",
                "Read, list, inspect, or create directories.",
                "workspace",
            ),
            (
                "delete_file",
                "Delete a single workspace file.",
                "workspace",
            ),
            (
                "command_exec",
                "Run audited shell commands in the workspace.",
                "workspace",
            ),
            ("web_search", "Search the web for candidate links.", "web"),
            (
                "web_fetch",
                "Fetch readable content from selected URLs.",
                "web",
            ),
            (
                "tool_catalog",
                "List built-in tools and their mode visibility.",
                "tools",
            ),
            (
                "skill_lookup",
                "Inspect Codex-style SKILL.md instructions.",
                "context",
            ),
            (
                "list_mcp_resources",
                "List MCP resources exposed by connected servers.",
                "mcp",
            ),
            ("read_mcp_resource", "Read an MCP resource.", "mcp"),
            (
                "text_to_image",
                "Prepare or generate raster image assets.",
                "image-generation",
            ),
            ("count_tokens", "Estimate token usage.", "context"),
            (
                "task_manager",
                "Maintain a checklist-first task system.",
                "planning",
            ),
            ("subagent", "Delegate bounded subtasks.", "coordination"),
            ("userInput", "Ask a blocking user question.", "coordination"),
            ("switch_mode", "Switch workflow modes.", "coordination"),
            (
                "game_design_orchestrator",
                "Compile game prompts into durable artifacts.",
                "game-design",
            ),
            (
                "game_gdd_manager",
                "Create and update game design document artifacts.",
                "game-design",
            ),
            (
                "story_design",
                "Create story and narrative design artifacts.",
                "game-design",
            ),
            (
                "level_design",
                "Create level design artifacts.",
                "game-design",
            ),
            (
                "game_project_scaffolder",
                "Create or upgrade game project foundations.",
                "game-scaffold",
            ),
            (
                "reverie_engine",
                "Create, inspect, and validate Reverie Engine projects.",
                "game-runtime",
            ),
            (
                "reverie_engine_lite",
                "Work with the lightweight built-in runtime.",
                "game-runtime",
            ),
            (
                "game_playtest_lab",
                "Generate playtest plans and quality gates.",
                "game-playtest",
            ),
            (
                "game_asset_manager",
                "Manage game asset manifests and notes.",
                "game-assets",
            ),
            (
                "game_asset_packer",
                "Inspect and package game asset directories.",
                "game-assets",
            ),
            (
                "game_config_editor",
                "Read and update game JSON config files.",
                "game-runtime",
            ),
            (
                "game_balance_analyzer",
                "Create balance analysis artifacts.",
                "game-analysis",
            ),
            (
                "game_math_simulator",
                "Create game math simulation artifacts.",
                "game-analysis",
            ),
            (
                "game_stats_analyzer",
                "Create game stats analysis artifacts.",
                "game-analysis",
            ),
            (
                "game_modeling_workbench",
                "Manage game modeling assets.",
                "game-modeling",
            ),
            (
                "blender_modeling_workbench",
                "Control Blender modeling workflows.",
                "game-modeling",
            ),
            (
                "atlas_delivery_orchestrator",
                "Manage Atlas delivery state.",
                "atlas",
            ),
            (
                "ask_clarification",
                "Ask targeted writing brief questions.",
                "writer",
            ),
            (
                "novel_context_manager",
                "Manage long-form writing context.",
                "writer",
            ),
            (
                "consistency_checker",
                "Check narrative continuity.",
                "writer",
            ),
            (
                "plot_analyzer",
                "Analyze plot structure and pacing.",
                "writer",
            ),
            ("task_boundary", "Publish Ant phase updates.", "planning"),
            ("notify_user", "Notify Ant workflow status.", "coordination"),
            (
                "computer_control",
                "Observe and control desktop UI.",
                "desktop",
            ),
        ];
        Self {
            tools: all
                .into_iter()
                .map(|(name, description, category)| ToolSpec {
                    name: name.to_string(),
                    description: description.to_string(),
                    category: category.to_string(),
                    modes: modes_for_tool(name)
                        .into_iter()
                        .map(str::to_string)
                        .collect(),
                })
                .collect(),
        }
    }

    pub fn visible_for_mode(&self, mode: &str) -> Vec<ToolSpec> {
        self.tools
            .iter()
            .filter(|tool| tool.modes.iter().any(|tool_mode| tool_mode == mode))
            .cloned()
            .collect()
    }

    pub fn all(&self) -> &[ToolSpec] {
        &self.tools
    }
}

fn modes_for_tool(name: &str) -> Vec<&'static str> {
    match name {
        "subagent" => vec!["reverie"],
        "task_manager" => vec!["reverie", "reverie-gamer"],
        "game_design_orchestrator"
        | "game_gdd_manager"
        | "story_design"
        | "level_design"
        | "game_project_scaffolder"
        | "reverie_engine"
        | "reverie_engine_lite"
        | "game_playtest_lab"
        | "game_asset_manager"
        | "game_asset_packer"
        | "game_config_editor"
        | "game_balance_analyzer"
        | "game_math_simulator"
        | "game_stats_analyzer" => vec!["reverie-gamer"],
        "game_modeling_workbench" | "blender_modeling_workbench" => {
            vec!["reverie", "reverie-gamer"]
        }
        "atlas_delivery_orchestrator" => vec!["reverie-atlas"],
        "ask_clarification" | "novel_context_manager" | "consistency_checker" | "plot_analyzer" => {
            vec!["writer"]
        }
        "task_boundary" | "notify_user" => vec!["reverie-ant"],
        "computer_control" => vec!["computer-controller"],
        _ => vec![
            "reverie",
            "reverie-atlas",
            "reverie-gamer",
            "reverie-ant",
            "spec-driven",
            "spec-vibe",
            "writer",
            "computer-controller",
        ],
    }
}

pub async fn execute_builtin_tool(
    project_root: &Path,
    invocation: ToolInvocation,
) -> Result<ToolResult> {
    let ToolInvocation { name, arguments } = invocation;
    let tool_name = name.clone();
    let name = name.as_str();
    let result = match name {
        "file_ops" => file_ops(project_root, arguments).await,
        "create_file" => create_file(project_root, arguments).await,
        "delete_file" => delete_file(project_root, arguments).await,
        "str_replace_editor" => str_replace_editor(project_root, arguments).await,
        "command_exec" => command_exec(project_root, arguments).await,
        "codebase-retrieval" => codebase_retrieval(project_root, arguments).await,
        "git-commit-retrieval" => git_commit_retrieval(project_root).await,
        "count_tokens" => count_tokens(arguments).await,
        "switch_mode" => switch_mode(arguments).await,
        "skill_lookup" => skill_lookup(project_root, arguments).await,
        "list_mcp_resources" => list_mcp_resources(project_root, arguments).await,
        "read_mcp_resource" => read_mcp_resource(project_root, arguments).await,
        "text_to_image" => text_to_image(project_root, arguments).await,
        "userInput" => user_input(arguments).await,
        "web_fetch" => web_fetch(arguments).await,
        "web_search" => web_search(arguments).await,
        "task_manager" => task_manager(project_root, arguments).await,
        "tool_catalog" => tool_catalog(arguments).await,
        "reverie_engine" | "reverie_engine_lite" => reverie_engine(project_root, arguments).await,
        "game_design_orchestrator" => game_design_orchestrator(project_root, arguments).await,
        "game_project_scaffolder" => game_project_scaffolder(project_root, arguments).await,
        "game_playtest_lab" => game_playtest_lab(project_root, arguments).await,
        "game_gdd_manager" => game_gdd_manager(project_root, arguments).await,
        "game_asset_manager" => game_asset_manager(project_root, arguments).await,
        "game_config_editor" => game_config_editor(project_root, arguments).await,
        "game_asset_packer" => game_asset_packer(project_root, arguments).await,
        "game_balance_analyzer" | "game_math_simulator" | "game_stats_analyzer" => {
            game_analysis_tool(project_root, name, arguments).await
        }
        "level_design" | "story_design" => {
            design_document_tool(project_root, name, arguments).await
        }
        "atlas_delivery_orchestrator" => atlas_delivery_orchestrator(project_root, arguments).await,
        "ask_clarification" => ask_clarification(arguments).await,
        "novel_context_manager" | "consistency_checker" | "plot_analyzer" => {
            writer_tool(project_root, name, arguments).await
        }
        "task_boundary" | "notify_user" => ant_tool(project_root, name, arguments).await,
        "subagent" => subagent_tool(project_root, arguments).await,
        "computer_control" => computer_control(arguments).await,
        "game_modeling_workbench" | "blender_modeling_workbench" => {
            modeling_workbench(project_root, name, arguments).await
        }
        "tools" => Ok(ToolResult {
            success: true,
            output: json!(ToolRegistry::builtin().all()),
            error: None,
        }),
        other => Ok(ToolResult {
            success: false,
            output: json!(null),
            error: Some(format!("unknown or unavailable built-in tool: {other}")),
        }),
    };
    if let Ok(tool_result) = &result {
        let _ = append_tool_audit(project_root, &tool_name, tool_result);
    }
    result
}

fn append_tool_audit(project_root: &Path, tool_name: &str, result: &ToolResult) -> Result<()> {
    let path = writable_join(project_root, ".reverie/tool_audit.json")?;
    let mut records = if path.is_file() {
        serde_json::from_str::<Vec<Value>>(&std::fs::read_to_string(&path)?)?
    } else {
        Vec::new()
    };
    let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    records.push(json!({
        "tool_name": tool_name,
        "success": result.success,
        "error": result.error.clone(),
        "timestamp": now
    }));
    if records.len() > 500 {
        records = records.split_off(records.len() - 500);
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, serde_json::to_string_pretty(&records)?)?;
    Ok(())
}

async fn create_file(project_root: &Path, args: Value) -> Result<ToolResult> {
    let path = writable_join(
        project_root,
        args.get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| anyhow!("path is required"))?,
    )?;
    let overwrite = args
        .get("overwrite")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if path.exists() && !overwrite {
        return Ok(ToolResult {
            success: false,
            output: json!({"path": path}),
            error: Some("file already exists; set overwrite=true to replace it".to_string()),
        });
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let content = args
        .get("content")
        .and_then(Value::as_str)
        .unwrap_or_default();
    std::fs::write(&path, content)?;
    Ok(ToolResult {
        success: true,
        output: json!({"path": path, "bytes": content.len()}),
        error: None,
    })
}

async fn delete_file(project_root: &Path, args: Value) -> Result<ToolResult> {
    let confirm = args
        .get("confirm_delete")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if !confirm {
        return Ok(ToolResult {
            success: false,
            output: json!(null),
            error: Some("confirm_delete must be true".to_string()),
        });
    }
    let path = safe_join(
        project_root,
        args.get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| anyhow!("path is required"))?,
    )?;
    if !path.is_file() {
        return Ok(ToolResult {
            success: false,
            output: json!({"path": path}),
            error: Some("path is not a file".to_string()),
        });
    }
    std::fs::remove_file(&path)?;
    Ok(ToolResult {
        success: true,
        output: json!({"path": path, "deleted": true}),
        error: None,
    })
}

async fn str_replace_editor(project_root: &Path, args: Value) -> Result<ToolResult> {
    let command = args
        .get("command")
        .and_then(Value::as_str)
        .unwrap_or("view");
    let path_value = args
        .get("path")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("path is required"))?;
    match command {
        "view" => {
            let path = safe_join(project_root, path_value)?;
            let content = std::fs::read_to_string(&path)?;
            Ok(ToolResult {
                success: true,
                output: json!({"path": path, "content": content}),
                error: None,
            })
        }
        "create" => create_file(project_root, args).await,
        "str_replace" => {
            let path = safe_join(project_root, path_value)?;
            let old = args
                .get("old_str")
                .and_then(Value::as_str)
                .ok_or_else(|| anyhow!("old_str is required"))?;
            let new = args
                .get("new_str")
                .and_then(Value::as_str)
                .ok_or_else(|| anyhow!("new_str is required"))?;
            let content = std::fs::read_to_string(&path)?;
            let count = content.matches(old).count();
            if count != 1 {
                return Ok(ToolResult {
                    success: false,
                    output: json!({"matches": count}),
                    error: Some("old_str must match exactly once".to_string()),
                });
            }
            let updated = content.replacen(old, new, 1);
            std::fs::write(&path, updated)?;
            Ok(ToolResult {
                success: true,
                output: json!({"path": path, "replacements": 1}),
                error: None,
            })
        }
        "insert" => {
            let path = safe_join(project_root, path_value)?;
            let insert_line =
                args.get("insert_line")
                    .and_then(Value::as_u64)
                    .ok_or_else(|| anyhow!("insert_line is required"))? as usize;
            let new = args
                .get("new_str")
                .and_then(Value::as_str)
                .ok_or_else(|| anyhow!("new_str is required"))?;
            let content = std::fs::read_to_string(&path)?;
            let mut lines = content.lines().map(str::to_string).collect::<Vec<_>>();
            let index = insert_line.saturating_sub(1).min(lines.len());
            lines.insert(index, new.to_string());
            std::fs::write(&path, format!("{}\n", lines.join("\n")))?;
            Ok(ToolResult {
                success: true,
                output: json!({"path": path, "insert_line": insert_line}),
                error: None,
            })
        }
        _ => Err(anyhow!("unsupported str_replace_editor command: {command}")),
    }
}

async fn file_ops(project_root: &Path, args: Value) -> Result<ToolResult> {
    let operation = args
        .get("operation")
        .and_then(Value::as_str)
        .unwrap_or("read");
    let path = safe_join(
        project_root,
        args.get("path").and_then(Value::as_str).unwrap_or("."),
    )?;
    let output = match operation {
        "read" => json!({"path": path, "content": std::fs::read_to_string(path)?}),
        "list" => {
            let mut entries = Vec::new();
            for entry in std::fs::read_dir(path)? {
                let entry = entry?;
                entries.push(json!({
                    "name": entry.file_name().to_string_lossy(),
                    "path": entry.path(),
                    "is_dir": entry.path().is_dir()
                }));
            }
            json!({"entries": entries})
        }
        "exists" => json!({"path": path, "exists": path.exists()}),
        "info" => {
            let meta = std::fs::metadata(&path)?;
            json!({"path": path, "is_file": meta.is_file(), "is_dir": meta.is_dir(), "len": meta.len()})
        }
        "mkdir" => {
            std::fs::create_dir_all(&path)?;
            json!({"path": path, "created": true})
        }
        _ => return Err(anyhow!("unsupported file_ops operation: {operation}")),
    };
    Ok(ToolResult {
        success: true,
        output,
        error: None,
    })
}

async fn command_exec(project_root: &Path, args: Value) -> Result<ToolResult> {
    let command = args
        .get("command")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("command is required"))?;
    let working_dir = args
        .get("working_dir")
        .and_then(Value::as_str)
        .map(|path| safe_join(project_root, path))
        .transpose()?
        .unwrap_or_else(|| project_root.to_path_buf());
    let output = if cfg!(windows) {
        Command::new("powershell")
            .arg("-NoProfile")
            .arg("-Command")
            .arg(command)
            .current_dir(working_dir)
            .output()
            .await?
    } else {
        Command::new("sh")
            .arg("-lc")
            .arg(command)
            .current_dir(working_dir)
            .output()
            .await?
    };
    Ok(ToolResult {
        success: output.status.success(),
        output: json!({
            "exit_code": output.status.code(),
            "stdout": String::from_utf8_lossy(&output.stdout),
            "stderr": String::from_utf8_lossy(&output.stderr)
        }),
        error: None,
    })
}

async fn codebase_retrieval(project_root: &Path, args: Value) -> Result<ToolResult> {
    let query_type = args
        .get("query_type")
        .and_then(Value::as_str)
        .unwrap_or("search");
    let query = args
        .get("query")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let index = reverie_context::CodebaseIndexer::new(project_root).full_index()?;
    let output = match query_type {
        "outline" | "symbol" => {
            let symbols = index
                .symbols
                .into_iter()
                .filter(|sym| query.is_empty() || sym.name.contains(query))
                .collect::<Vec<_>>();
            json!({"symbols": symbols})
        }
        _ => json!({"index": index}),
    };
    Ok(ToolResult {
        success: true,
        output,
        error: None,
    })
}

async fn git_commit_retrieval(project_root: &Path) -> Result<ToolResult> {
    let repo = git2::Repository::discover(project_root)?;
    let statuses = repo.statuses(None)?;
    let files = statuses
        .iter()
        .filter_map(|entry| entry.path().map(|path| path.to_string()))
        .collect::<Vec<_>>();
    Ok(ToolResult {
        success: true,
        output: json!({"changed_files": files}),
        error: None,
    })
}

async fn count_tokens(args: Value) -> Result<ToolResult> {
    let text = args.get("text").and_then(Value::as_str).unwrap_or_default();
    let estimate = (text.chars().count() as f64 / 4.0).ceil() as usize;
    Ok(ToolResult {
        success: true,
        output: json!({"tokens": estimate, "method": "chars_div_4"}),
        error: None,
    })
}

async fn switch_mode(args: Value) -> Result<ToolResult> {
    let mode = args
        .get("mode")
        .and_then(Value::as_str)
        .unwrap_or("reverie");
    Ok(ToolResult {
        success: true,
        output: json!({
            "mode": mode,
            "message": format!("Mode switch requested: {mode}")
        }),
        error: None,
    })
}

async fn skill_lookup(project_root: &Path, args: Value) -> Result<ToolResult> {
    let operation = args
        .get("operation")
        .and_then(Value::as_str)
        .unwrap_or("list");
    let query = args
        .get("query")
        .or_else(|| args.get("skill_name"))
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let skills = discover_skills(project_root)?;
    let output = match operation {
        "inspect" => {
            let found = skills.iter().find(|skill| {
                skill["name"]
                    .as_str()
                    .unwrap_or_default()
                    .eq_ignore_ascii_case(&query)
            });
            json!({"skill": found})
        }
        "search" => {
            let filtered = skills
                .into_iter()
                .filter(|skill| skill.to_string().to_ascii_lowercase().contains(&query))
                .collect::<Vec<_>>();
            json!({"skills": filtered})
        }
        _ => json!({"skills": skills}),
    };
    Ok(ToolResult {
        success: true,
        output,
        error: None,
    })
}

fn discover_skills(project_root: &Path) -> Result<Vec<Value>> {
    let roots = [
        project_root.join(".reverie").join("skills"),
        project_root.join("skills"),
    ];
    let mut skills = Vec::new();
    for root in roots {
        if !root.is_dir() {
            continue;
        }
        for entry in walkdir::WalkDir::new(&root)
            .max_depth(3)
            .into_iter()
            .filter_map(|entry| entry.ok())
        {
            if entry.file_name().to_string_lossy() != "SKILL.md" {
                continue;
            }
            let path = entry.path().to_path_buf();
            let content = std::fs::read_to_string(&path).unwrap_or_default();
            let name = path
                .parent()
                .and_then(|p| p.file_name())
                .and_then(|v| v.to_str())
                .unwrap_or("skill")
                .to_string();
            let description = content
                .lines()
                .find(|line| !line.trim().is_empty() && !line.starts_with('#'))
                .unwrap_or_default()
                .trim()
                .to_string();
            skills.push(json!({
                "name": name,
                "description": description,
                "path": path,
                "content": content
            }));
        }
    }
    Ok(skills)
}

async fn list_mcp_resources(project_root: &Path, _args: Value) -> Result<ToolResult> {
    let cache = project_root.join(".reverie").join("mcp_resources");
    let resources = if cache.is_dir() {
        std::fs::read_dir(&cache)?
            .filter_map(|entry| entry.ok())
            .filter(|entry| entry.path().is_file())
            .map(|entry| {
                json!({
                    "server": "local-cache",
                    "uri": entry.path().to_string_lossy(),
                    "name": entry.file_name().to_string_lossy()
                })
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    Ok(ToolResult {
        success: true,
        output: json!({"resources": resources}),
        error: None,
    })
}

async fn read_mcp_resource(project_root: &Path, args: Value) -> Result<ToolResult> {
    let uri = args
        .get("uri")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("uri is required"))?;
    let path = if let Some(path) = uri.strip_prefix("file://") {
        PathBuf::from(path)
    } else {
        PathBuf::from(uri)
    };
    let path = if path.is_absolute() {
        path
    } else {
        safe_join(project_root, uri)?
    };
    let root = project_root
        .canonicalize()
        .unwrap_or_else(|_| project_root.to_path_buf());
    let resolved = path.canonicalize()?;
    if !resolved.starts_with(root) {
        return Err(anyhow!("resource path escapes workspace"));
    }
    Ok(ToolResult {
        success: true,
        output: json!({"uri": uri, "content": std::fs::read_to_string(resolved)?}),
        error: None,
    })
}

async fn text_to_image(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("diagnose");
    let models_dir = project_root.join(".reverie").join("tti_models");
    let models = if models_dir.is_dir() {
        std::fs::read_dir(&models_dir)?
            .filter_map(|entry| entry.ok())
            .map(|entry| {
                json!({
                    "display_name": entry.file_name().to_string_lossy(),
                    "path": entry.path()
                })
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    match action {
        "diagnose" | "list_models" => Ok(ToolResult {
            success: true,
            output: json!({
                "ready": models_dir.is_dir(),
                "models_dir": models_dir,
                "models": models,
                "runtime": "rust"
            }),
            error: None,
        }),
        "generate" => {
            let prompt = args
                .get("prompt")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .trim();
            if prompt.is_empty() {
                return Ok(ToolResult {
                    success: false,
                    output: json!({"action": action}),
                    error: Some("prompt is required".to_string()),
                });
            }
            let artifact = create_tti_preview_artifact(project_root, prompt, &args, &models)?;
            Ok(ToolResult {
                success: true,
                output: artifact,
                error: None,
            })
        }
        _ => Ok(ToolResult {
            success: false,
            output: json!({"action": action}),
            error: Some("unsupported text_to_image action".to_string()),
        }),
    }
}

async fn user_input(args: Value) -> Result<ToolResult> {
    Ok(ToolResult {
        success: true,
        output: json!({
            "question": args.get("question").and_then(Value::as_str).unwrap_or_default(),
            "status": "not_interactive",
            "message": "Rust headless tool surface cannot prompt directly; caller should ask the user."
        }),
        error: None,
    })
}

async fn web_search(args: Value) -> Result<ToolResult> {
    let query = args
        .get("query")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("query is required"))?;
    if query.starts_with("http://") || query.starts_with("https://") {
        return Ok(ToolResult {
            success: true,
            output: json!({"query": query, "results": [{"title": query, "url": query, "snippet": "Direct URL"}]}),
            error: None,
        });
    }
    let encoded = query.replace(' ', "+");
    Ok(ToolResult {
        success: true,
        output: json!({
            "query": query,
            "results": [
                {
                    "title": format!("Search web for {query}"),
                    "url": format!("https://duckduckgo.com/?q={encoded}"),
                    "snippet": "Rust fallback returns a search URL for the selected query."
                }
            ]
        }),
        error: None,
    })
}

async fn web_fetch(args: Value) -> Result<ToolResult> {
    let url = args
        .get("url")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("url is required"))?;
    let text = reqwest::get(url).await?.text().await?;
    Ok(ToolResult {
        success: true,
        output: json!({"url": url, "content": text}),
        error: None,
    })
}

async fn tool_catalog(args: Value) -> Result<ToolResult> {
    let operation = args
        .get("operation")
        .and_then(Value::as_str)
        .unwrap_or("list");
    let registry = ToolRegistry::builtin();
    let output = match operation {
        "search" => {
            let query = args
                .get("query")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_ascii_lowercase();
            let tools = registry
                .all()
                .iter()
                .filter(|tool| {
                    tool.name.to_ascii_lowercase().contains(&query)
                        || tool.description.to_ascii_lowercase().contains(&query)
                        || tool.category.to_ascii_lowercase().contains(&query)
                })
                .cloned()
                .collect::<Vec<_>>();
            json!({"tools": tools})
        }
        "inspect" => {
            let name = args
                .get("tool_name")
                .or_else(|| args.get("name"))
                .and_then(Value::as_str)
                .unwrap_or_default();
            let tool = registry
                .all()
                .iter()
                .find(|tool| tool.name == name)
                .cloned();
            json!({"tool": tool})
        }
        _ => json!({"tools": registry.all()}),
    };
    Ok(ToolResult {
        success: true,
        output,
        error: None,
    })
}

#[derive(Debug, Clone)]
struct ChecklistTask {
    id: String,
    name: String,
    state: String,
    indent: usize,
}

impl ChecklistTask {
    fn marker(&self) -> &'static str {
        state_to_marker(&self.state)
    }
}

fn create_tti_preview_artifact(
    project_root: &Path,
    prompt: &str,
    args: &Value,
    models: &[Value],
) -> Result<Value> {
    let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let mut hasher = DefaultHasher::new();
    prompt.hash(&mut hasher);
    now.hash(&mut hasher);
    let digest = hasher.finish();
    let request_id = format!("tti-{now}-{digest:016x}");
    let root = writable_join(project_root, "artifacts/tti")?;
    let preview_path = root.join(format!("{request_id}.ppm"));
    let manifest_path = root.join(format!("{request_id}.json"));
    std::fs::create_dir_all(&root)?;

    let color = [
        ((digest >> 16) & 0xff) as u8,
        ((digest >> 8) & 0xff) as u8,
        (digest & 0xff) as u8,
    ];
    let ppm = deterministic_ppm_preview(color);
    std::fs::write(&preview_path, ppm)?;

    let manifest = json!({
        "schema": "reverie.tti.request.v1",
        "request_id": request_id,
        "prompt": prompt,
        "negative_prompt": args.get("negative_prompt").and_then(Value::as_str).unwrap_or_default(),
        "width": args.get("width").and_then(Value::as_u64).unwrap_or(512),
        "height": args.get("height").and_then(Value::as_u64).unwrap_or(512),
        "seed": args.get("seed").cloned().unwrap_or_else(|| json!(digest)),
        "runtime": "rust-preview",
        "status": "preview_generated",
        "models": models,
        "preview_path": preview_path,
    });
    std::fs::write(&manifest_path, serde_json::to_string_pretty(&manifest)?)?;
    Ok(json!({
        "artifact_path": manifest_path,
        "preview_path": preview_path,
        "request": manifest,
        "message": "Generated a deterministic Rust preview artifact. Configure a native model runner to replace preview output with real image synthesis."
    }))
}

fn deterministic_ppm_preview(color: [u8; 3]) -> Vec<u8> {
    let width = 64usize;
    let height = 64usize;
    let mut output = format!("P6\n{width} {height}\n255\n").into_bytes();
    for y in 0..height {
        for x in 0..width {
            let mix = ((x ^ y) as u8).saturating_mul(3);
            output.push(color[0].saturating_add(mix / 4));
            output.push(color[1].saturating_add(mix / 5));
            output.push(color[2].saturating_add(mix / 6));
        }
    }
    output
}

async fn task_manager(project_root: &Path, args: Value) -> Result<ToolResult> {
    let markdown_path = writable_join(project_root, "artifacts/Tasks.md")?;
    let legacy_json_path = writable_join(project_root, ".reverie/tasks.json")?;
    let mut tasks = load_checklist_tasks(&markdown_path, &legacy_json_path)?;
    let action = args
        .get("action")
        .or_else(|| args.get("operation"))
        .and_then(Value::as_str)
        .unwrap_or("list")
        .to_ascii_lowercase();

    match action.as_str() {
        "add" | "create" | "add_task" | "add_tasks" => {
            let new_tasks = task_inputs(&args);
            for input in new_tasks {
                let name = input
                    .get("name")
                    .or_else(|| input.get("title"))
                    .or_else(|| input.get("target"))
                    .and_then(Value::as_str)
                    .unwrap_or("Task")
                    .trim();
                if name.is_empty() {
                    continue;
                }
                let state = input
                    .get("status")
                    .or_else(|| input.get("state"))
                    .and_then(Value::as_str)
                    .map(normalize_task_state)
                    .unwrap_or_else(|| "NOT_STARTED".to_string());
                tasks.push(ChecklistTask {
                    id: format!("task-{}", tasks.len() + 1),
                    name: name.to_string(),
                    state,
                    indent: input.get("indent").and_then(Value::as_u64).unwrap_or(0) as usize,
                });
            }
            save_checklist_tasks(&markdown_path, &legacy_json_path, &tasks)?;
            Ok(ToolResult {
                success: true,
                output: task_manager_output(&markdown_path, &legacy_json_path, &tasks),
                error: None,
            })
        }
        "update" | "update_task" | "update_tasks" => {
            let updates = if args.get("tasks").and_then(Value::as_array).is_some() {
                task_inputs(&args)
            } else {
                vec![args.clone()]
            };
            let mut missing = Vec::new();
            for update in updates {
                let target = update
                    .get("target")
                    .or_else(|| update.get("name"))
                    .or_else(|| update.get("title"))
                    .or_else(|| update.get("task_id"))
                    .or_else(|| update.get("id"))
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .trim();
                if target.is_empty() {
                    missing.push("(empty target)".to_string());
                    continue;
                }
                let Some(task) = find_checklist_task_mut(&mut tasks, target) else {
                    missing.push(target.to_string());
                    continue;
                };
                if let Some(name) = update
                    .get("new_name")
                    .or_else(|| update.get("rename_to"))
                    .and_then(Value::as_str)
                {
                    task.name = name.trim().to_string();
                }
                if let Some(state) = update
                    .get("status")
                    .or_else(|| update.get("state"))
                    .and_then(Value::as_str)
                {
                    task.state = normalize_task_state(state);
                }
            }
            if !missing.is_empty() {
                return Ok(ToolResult {
                    success: false,
                    output: json!({"missing": missing, "tasks": tasks_to_json(&tasks), "path": markdown_path}),
                    error: Some("one or more tasks were not found".to_string()),
                });
            }
            save_checklist_tasks(&markdown_path, &legacy_json_path, &tasks)?;
            Ok(ToolResult {
                success: true,
                output: task_manager_output(&markdown_path, &legacy_json_path, &tasks),
                error: None,
            })
        }
        "clear" => {
            tasks.clear();
            save_checklist_tasks(&markdown_path, &legacy_json_path, &tasks)?;
            Ok(ToolResult {
                success: true,
                output: task_manager_output(&markdown_path, &legacy_json_path, &tasks),
                error: None,
            })
        }
        _ => Ok(ToolResult {
            success: true,
            output: task_manager_output(&markdown_path, &legacy_json_path, &tasks),
            error: None,
        }),
    }
}

fn task_inputs(args: &Value) -> Vec<Value> {
    args.get("tasks")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_else(|| vec![args.clone()])
}

fn load_checklist_tasks(
    markdown_path: &Path,
    legacy_json_path: &Path,
) -> Result<Vec<ChecklistTask>> {
    if markdown_path.is_file() {
        return Ok(parse_checklist_markdown(&std::fs::read_to_string(
            markdown_path,
        )?));
    }
    if legacy_json_path.is_file() {
        let values: Vec<Value> = serde_json::from_str(&std::fs::read_to_string(legacy_json_path)?)?;
        let tasks = values
            .into_iter()
            .enumerate()
            .filter_map(|(index, value)| {
                let name = value
                    .get("name")
                    .or_else(|| value.get("title"))
                    .and_then(Value::as_str)?
                    .trim()
                    .to_string();
                if name.is_empty() {
                    return None;
                }
                Some(ChecklistTask {
                    id: value
                        .get("id")
                        .and_then(Value::as_str)
                        .map(str::to_string)
                        .unwrap_or_else(|| format!("task-{}", index + 1)),
                    name,
                    state: value
                        .get("status")
                        .or_else(|| value.get("state"))
                        .and_then(Value::as_str)
                        .map(normalize_task_state)
                        .unwrap_or_else(|| "NOT_STARTED".to_string()),
                    indent: value.get("indent").and_then(Value::as_u64).unwrap_or(0) as usize,
                })
            })
            .collect::<Vec<_>>();
        save_checklist_tasks(markdown_path, legacy_json_path, &tasks)?;
        return Ok(tasks);
    }
    Ok(Vec::new())
}

fn save_checklist_tasks(
    markdown_path: &Path,
    legacy_json_path: &Path,
    tasks: &[ChecklistTask],
) -> Result<()> {
    if let Some(parent) = markdown_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(markdown_path, checklist_markdown(tasks))?;
    if legacy_json_path.is_file() {
        std::fs::remove_file(legacy_json_path)?;
    }
    Ok(())
}

fn parse_checklist_markdown(text: &str) -> Vec<ChecklistTask> {
    text.lines()
        .enumerate()
        .filter_map(|(index, line)| parse_checklist_line(index, line))
        .collect()
}

fn parse_checklist_line(index: usize, line: &str) -> Option<ChecklistTask> {
    let trimmed_start = line.trim_start_matches([' ', '\t']);
    let indent = line.len().saturating_sub(trimmed_start.len()) / 2;
    let rest = trimmed_start.strip_prefix('[')?;
    let (marker, name) = rest.split_once(']')?;
    let name = name.trim();
    if name.is_empty() {
        return None;
    }
    Some(ChecklistTask {
        id: format!("task-{}", index + 1),
        name: name.to_string(),
        state: marker_to_state(marker),
        indent,
    })
}

fn checklist_markdown(tasks: &[ChecklistTask]) -> String {
    if tasks.is_empty() {
        return String::new();
    }
    let mut output = tasks
        .iter()
        .map(|task| {
            format!(
                "{}{} {}",
                "  ".repeat(task.indent),
                task.marker(),
                task.name
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    output.push('\n');
    output
}

fn find_checklist_task_mut<'a>(
    tasks: &'a mut [ChecklistTask],
    target: &str,
) -> Option<&'a mut ChecklistTask> {
    let target_lower = target.to_ascii_lowercase();
    tasks.iter_mut().find(|task| {
        task.id.eq_ignore_ascii_case(target)
            || task.name == target
            || task.name.to_ascii_lowercase() == target_lower
    })
}

fn marker_to_state(marker: &str) -> String {
    match marker.trim() {
        "x" | "X" => "COMPLETED",
        "/" => "IN_PROGRESS",
        "-" => "CANCELLED",
        _ => "NOT_STARTED",
    }
    .to_string()
}

fn state_to_marker(state: &str) -> &'static str {
    match normalize_task_state(state).as_str() {
        "COMPLETED" => "[x]",
        "IN_PROGRESS" => "[/]",
        "CANCELLED" => "[-]",
        _ => "[ ]",
    }
}

fn normalize_task_state(state: &str) -> String {
    match state.trim().to_ascii_lowercase().as_str() {
        "done" | "complete" | "completed" | "success" | "x" | "[x]" => "COMPLETED",
        "doing" | "in_progress" | "in-progress" | "progress" | "/" | "[/]" => "IN_PROGRESS",
        "cancelled" | "canceled" | "skip" | "skipped" | "-" | "[-]" => "CANCELLED",
        _ => "NOT_STARTED",
    }
    .to_string()
}

fn tasks_to_json(tasks: &[ChecklistTask]) -> Vec<Value> {
    tasks
        .iter()
        .map(|task| {
            json!({
                "id": task.id,
                "name": task.name,
                "state": task.state,
                "marker": task.marker(),
                "indent": task.indent
            })
        })
        .collect()
}

fn task_manager_output(
    markdown_path: &Path,
    legacy_json_path: &Path,
    tasks: &[ChecklistTask],
) -> Value {
    let completed = tasks
        .iter()
        .filter(|task| normalize_task_state(&task.state) == "COMPLETED")
        .count();
    json!({
        "tasks": tasks_to_json(tasks),
        "completed": completed,
        "total": tasks.len(),
        "path": markdown_path,
        "checklist_path": markdown_path,
        "legacy_json_path": legacy_json_path,
        "storage": "markdown"
    })
}

async fn reverie_engine(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("inspect");
    let project_dir = args
        .get("project_dir")
        .or_else(|| args.get("output_dir"))
        .and_then(Value::as_str)
        .unwrap_or("reverie-game");
    let path = writable_join(project_root, project_dir)?;
    match action {
        "create_project" | "create" | "new" => {
            let project_name = args
                .get("project_name")
                .and_then(Value::as_str)
                .or_else(|| args.get("name").and_then(Value::as_str))
                .unwrap_or("Reverie Game");
            let project = reverie_engine_lite::EngineProject::new(project_name);
            project.scaffold_to(&path)?;
            Ok(ToolResult {
                success: true,
                output: json!({"project_dir": path, "project": project, "summary": project.summary()}),
                error: None,
            })
        }
        "validate" | "inspect" => {
            if !path.join("reverie.project.json").is_file() {
                return Ok(ToolResult {
                    success: false,
                    output: json!({"project_dir": path}),
                    error: Some("reverie.project.json not found".to_string()),
                });
            }
            let project = reverie_engine_lite::EngineProject::load_from(&path)?;
            let issues = project.validate();
            Ok(ToolResult {
                success: issues.is_empty(),
                output: json!({"project_dir": path, "project": project, "issues": issues, "summary": project.summary()}),
                error: None,
            })
        }
        "add_scene" => {
            let mut project = reverie_engine_lite::EngineProject::load_from(&path)?;
            let scene_id = args
                .get("scene_id")
                .and_then(Value::as_str)
                .unwrap_or("scene");
            let title = args
                .get("title")
                .and_then(Value::as_str)
                .unwrap_or(scene_id);
            project.add_scene(scene_id, title);
            project.save_to(&path)?;
            Ok(ToolResult {
                success: true,
                output: json!({"project_dir": path, "project": project, "summary": project.summary()}),
                error: None,
            })
        }
        "add_entity" => {
            let mut project = reverie_engine_lite::EngineProject::load_from(&path)?;
            let scene_id = args
                .get("scene_id")
                .and_then(Value::as_str)
                .unwrap_or("main");
            let entity_id = args
                .get("entity_id")
                .and_then(Value::as_str)
                .unwrap_or("entity");
            let kind = args.get("kind").and_then(Value::as_str).unwrap_or("entity");
            let added =
                project.add_entity(scene_id, reverie_engine_lite::Entity::new(entity_id, kind));
            if !added {
                return Ok(ToolResult {
                    success: false,
                    output: json!({"project_dir": path, "scene_id": scene_id}),
                    error: Some("scene not found".to_string()),
                });
            }
            project.save_to(&path)?;
            Ok(ToolResult {
                success: true,
                output: json!({"project_dir": path, "project": project, "summary": project.summary()}),
                error: None,
            })
        }
        "register_asset" => {
            let mut project = reverie_engine_lite::EngineProject::load_from(&path)?;
            let asset = reverie_engine_lite::AssetRef {
                id: args
                    .get("asset_id")
                    .and_then(Value::as_str)
                    .unwrap_or("asset")
                    .to_string(),
                path: PathBuf::from(
                    args.get("path")
                        .and_then(Value::as_str)
                        .unwrap_or("assets/asset.dat"),
                ),
                kind: args
                    .get("kind")
                    .and_then(Value::as_str)
                    .unwrap_or("asset")
                    .to_string(),
            };
            project.register_asset(asset);
            project.save_to(&path)?;
            Ok(ToolResult {
                success: true,
                output: json!({"project_dir": path, "project": project, "summary": project.summary()}),
                error: None,
            })
        }
        _ => Ok(ToolResult {
            success: false,
            output: json!({"action": action}),
            error: Some("unsupported reverie_engine action".to_string()),
        }),
    }
}

async fn game_design_orchestrator(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("compile_request");
    let prompt = args
        .get("prompt")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let project_name = args
        .get("project_name")
        .and_then(Value::as_str)
        .unwrap_or("Untitled Game");
    let artifact = json!({
        "schema": "reverie.game_program.v1",
        "action": action,
        "project_name": project_name,
        "request": prompt,
        "scope": "vertical_slice",
        "runtime_targets": ["reverie_engine", "godot", "o3de"],
        "systems": ["player_controller", "camera", "core_loop", "save_load"],
        "verification": ["smoke", "quality_gate", "slice_score"]
    });
    let path = write_artifact(project_root, "artifacts/game_program.json", &artifact)?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "artifact": artifact}),
        error: None,
    })
}

async fn game_project_scaffolder(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args.get("action").and_then(Value::as_str).unwrap_or("plan");
    let output_dir = args
        .get("output_dir")
        .and_then(Value::as_str)
        .unwrap_or("game");
    if matches!(
        action,
        "create" | "generate_vertical_slice" | "upgrade_runtime_project"
    ) {
        let project = reverie_engine_lite::EngineProject::new(
            args.get("project_name")
                .and_then(Value::as_str)
                .unwrap_or("Reverie Game"),
        );
        let path = writable_join(project_root, output_dir)?;
        project.scaffold_to(&path)?;
        return Ok(ToolResult {
            success: true,
            output: json!({"project_dir": path, "project": project, "summary": project.summary()}),
            error: None,
        });
    }
    let plan = json!({
        "schema": "reverie.runtime_delivery_plan.v1",
        "action": action,
        "output_dir": output_dir,
        "steps": ["create_project", "apply_system_packet", "validate", "playtest"]
    });
    let path = write_artifact(project_root, "artifacts/runtime_delivery_plan.json", &plan)?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "plan": plan}),
        error: None,
    })
}

async fn game_playtest_lab(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("create_test_plan");
    let score = json!({
        "schema": "reverie.slice_score.v1",
        "action": action,
        "checks": [
            {"id": "launch", "status": "pending"},
            {"id": "core_loop", "status": "pending"},
            {"id": "performance_budget", "status": "pending"}
        ],
        "score": 0
    });
    let path = write_artifact(project_root, "playtest/slice_score.json", &score)?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "slice_score": score}),
        error: None,
    })
}

async fn game_gdd_manager(project_root: &Path, args: Value) -> Result<ToolResult> {
    let project_name = args
        .get("project_name")
        .and_then(Value::as_str)
        .unwrap_or("Untitled Game");
    let gdd = json!({
        "schema": "reverie.gdd.v1",
        "project_name": project_name,
        "sections": {
            "overview": args.get("content").and_then(Value::as_str).unwrap_or(""),
            "core_loop": "",
            "systems": [],
            "content": []
        }
    });
    let path = write_artifact(project_root, "artifacts/gdd.json", &gdd)?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "gdd": gdd}),
        error: None,
    })
}

async fn game_asset_manager(project_root: &Path, args: Value) -> Result<ToolResult> {
    let manifest = json!({
        "schema": "reverie.assets.v1",
        "assets": args.get("assets").cloned().unwrap_or_else(|| json!([])),
        "notes": args.get("notes").and_then(Value::as_str).unwrap_or("")
    });
    let path = write_artifact(project_root, "artifacts/asset_pipeline.json", &manifest)?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "manifest": manifest}),
        error: None,
    })
}

async fn game_config_editor(project_root: &Path, args: Value) -> Result<ToolResult> {
    let path_value = args
        .get("path")
        .and_then(Value::as_str)
        .unwrap_or("game.config.json");
    let path = writable_join(project_root, path_value)?;
    let action = args.get("action").and_then(Value::as_str).unwrap_or("read");
    match action {
        "write" | "update" => {
            let data = args.get("data").cloned().unwrap_or_else(|| json!({}));
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::write(&path, serde_json::to_string_pretty(&data)?)?;
            Ok(ToolResult {
                success: true,
                output: json!({"path": path, "data": data}),
                error: None,
            })
        }
        _ => {
            let data = if path.is_file() {
                serde_json::from_str::<Value>(&std::fs::read_to_string(&path)?)?
            } else {
                json!({})
            };
            Ok(ToolResult {
                success: true,
                output: json!({"path": path, "data": data}),
                error: None,
            })
        }
    }
}

async fn game_asset_packer(project_root: &Path, args: Value) -> Result<ToolResult> {
    let input_dir = args
        .get("input_dir")
        .and_then(Value::as_str)
        .unwrap_or("assets");
    let root = safe_join(project_root, input_dir).unwrap_or_else(|_| project_root.join(input_dir));
    let mut files = Vec::new();
    if root.is_dir() {
        for entry in walkdir::WalkDir::new(&root)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            if entry.path().is_file() {
                files.push(entry.path().to_path_buf());
            }
        }
    }
    Ok(ToolResult {
        success: true,
        output: json!({"input_dir": root, "files": files, "packed": false}),
        error: None,
    })
}

async fn game_analysis_tool(
    project_root: &Path,
    tool_name: &str,
    args: Value,
) -> Result<ToolResult> {
    let artifact = json!({
        "schema": format!("reverie.{tool_name}.v1"),
        "input": args,
        "findings": [],
        "status": "ready_for_data"
    });
    let path = write_artifact(
        project_root,
        &format!("artifacts/{tool_name}.json"),
        &artifact,
    )?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "artifact": artifact}),
        error: None,
    })
}

async fn design_document_tool(
    project_root: &Path,
    tool_name: &str,
    args: Value,
) -> Result<ToolResult> {
    let artifact = json!({
        "schema": format!("reverie.{tool_name}.v1"),
        "action": args.get("action").and_then(Value::as_str).unwrap_or("create"),
        "data": args
    });
    let path = write_artifact(
        project_root,
        &format!("artifacts/{tool_name}.json"),
        &artifact,
    )?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "artifact": artifact}),
        error: None,
    })
}

async fn atlas_delivery_orchestrator(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("status");
    let state_path = writable_join(project_root, "artifacts/atlas_delivery_state.json")?;
    let mut state = if state_path.is_file() {
        serde_json::from_str::<Value>(&std::fs::read_to_string(&state_path)?)?
    } else {
        json!({
            "schema": "reverie.atlas_delivery_state.v1",
            "slices": [],
            "blockers": [],
            "checkpoints": []
        })
    };
    if action != "status" {
        state["last_action"] = json!(action);
        state["last_payload"] = args;
        if let Some(parent) = state_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::write(&state_path, serde_json::to_string_pretty(&state)?)?;
    }
    Ok(ToolResult {
        success: true,
        output: json!({"state_path": state_path, "state": state}),
        error: None,
    })
}

async fn ask_clarification(args: Value) -> Result<ToolResult> {
    Ok(ToolResult {
        success: true,
        output: json!({
            "question": args.get("question").and_then(Value::as_str).unwrap_or("Clarification needed"),
            "context": args.get("context").cloned().unwrap_or(Value::Null),
            "status": "needs_user_answer"
        }),
        error: None,
    })
}

async fn writer_tool(project_root: &Path, tool_name: &str, args: Value) -> Result<ToolResult> {
    let artifact = json!({
        "schema": format!("reverie.writer.{tool_name}.v1"),
        "action": args.get("action").and_then(Value::as_str).unwrap_or("analyze"),
        "content": args.get("content").cloned().unwrap_or_else(|| json!("")),
        "findings": []
    });
    let path = write_artifact(
        project_root,
        &format!("artifacts/writer/{tool_name}.json"),
        &artifact,
    )?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "artifact": artifact}),
        error: None,
    })
}

async fn ant_tool(project_root: &Path, tool_name: &str, args: Value) -> Result<ToolResult> {
    let artifact = json!({
        "schema": "reverie.ant.event.v1",
        "tool": tool_name,
        "payload": args
    });
    let path = write_artifact(project_root, "artifacts/ant_last_event.json", &artifact)?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "event": artifact}),
        error: None,
    })
}

async fn subagent_tool(project_root: &Path, args: Value) -> Result<ToolResult> {
    let prompt = args
        .get("prompt")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let artifact = json!({
        "schema": "reverie.subagent_run.v1",
        "prompt": prompt,
        "status": "queued_for_external_agent",
        "note": "Delegation was recorded for a compatible external runner."
    });
    let path = write_artifact(project_root, "artifacts/subagent_last_run.json", &artifact)?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "run": artifact}),
        error: None,
    })
}

async fn computer_control(args: Value) -> Result<ToolResult> {
    Ok(ToolResult {
        success: false,
        output: json!({
            "action": args.get("action").and_then(Value::as_str).unwrap_or("observe"),
            "runtime": "rust",
            "available": false
        }),
        error: Some("Native desktop control is not enabled in the Rust runtime yet".to_string()),
    })
}

async fn modeling_workbench(
    project_root: &Path,
    tool_name: &str,
    args: Value,
) -> Result<ToolResult> {
    let brief = args
        .get("brief")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let artifact = json!({
        "schema": format!("reverie.{tool_name}.v1"),
        "brief": brief,
        "steps": [
            "prepare_reference",
            "author_model_script",
            "export_glb",
            "audit_artifacts"
        ],
        "status": "planned"
    });
    let path = write_artifact(
        project_root,
        &format!("artifacts/modeling/{tool_name}.json"),
        &artifact,
    )?;
    Ok(ToolResult {
        success: true,
        output: json!({"artifact_path": path, "artifact": artifact}),
        error: None,
    })
}

fn write_artifact(project_root: &Path, relative_path: &str, value: &Value) -> Result<PathBuf> {
    let path = writable_join(project_root, relative_path)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&path, serde_json::to_string_pretty(value)?)?;
    Ok(path)
}

fn safe_join(root: &Path, value: &str) -> Result<PathBuf> {
    let candidate = root.join(value);
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let resolved = candidate.canonicalize().unwrap_or(candidate);
    if resolved.starts_with(&root) {
        Ok(resolved)
    } else {
        Err(anyhow!("path escapes workspace: {}", value))
    }
}

fn writable_join(root: &Path, value: &str) -> Result<PathBuf> {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let candidate = root.join(value);
    let parent = candidate.parent().unwrap_or(&root);
    let parent_resolved = parent
        .canonicalize()
        .unwrap_or_else(|_| parent.to_path_buf());
    if parent_resolved.starts_with(&root) {
        Ok(candidate)
    } else {
        Err(anyhow!("path escapes workspace: {}", value))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_hides_gamer_runtime_from_base_reverie() {
        let registry = ToolRegistry::builtin();
        let base = registry.visible_for_mode("reverie");
        assert!(base
            .iter()
            .any(|tool| tool.name == "blender_modeling_workbench"));
        assert!(!base.iter().any(|tool| tool.name == "reverie_engine"));
    }

    #[tokio::test]
    async fn reverie_engine_tool_creates_and_updates_project() {
        let temp = tempfile::tempdir().unwrap();
        let created = execute_builtin_tool(
            temp.path(),
            ToolInvocation {
                name: "reverie_engine".to_string(),
                arguments: json!({
                    "action": "create",
                    "project_dir": "game",
                    "project_name": "Test Slice"
                }),
            },
        )
        .await
        .unwrap();
        assert!(created.success);
        assert!(temp.path().join("game/runtime/README.md").is_file());

        let updated = execute_builtin_tool(
            temp.path(),
            ToolInvocation {
                name: "reverie_engine".to_string(),
                arguments: json!({
                    "action": "add_entity",
                    "project_dir": "game",
                    "scene_id": "main",
                    "entity_id": "player",
                    "kind": "character"
                }),
            },
        )
        .await
        .unwrap();
        assert!(updated.success);
        assert_eq!(updated.output["summary"]["entity_count"], 1);
    }

    #[tokio::test]
    async fn task_manager_uses_markdown_storage_and_imports_legacy_json() {
        let temp = tempfile::tempdir().unwrap();
        let legacy_path = temp.path().join(".reverie/tasks.json");
        std::fs::create_dir_all(legacy_path.parent().unwrap()).unwrap();
        std::fs::write(
            &legacy_path,
            serde_json::to_string_pretty(&vec![json!({
                "id": "legacy-1",
                "name": "Port task manager",
                "state": "pending"
            })])
            .unwrap(),
        )
        .unwrap();

        let listed = execute_builtin_tool(
            temp.path(),
            ToolInvocation {
                name: "task_manager".to_string(),
                arguments: json!({"action": "list"}),
            },
        )
        .await
        .unwrap();
        assert!(listed.success);
        assert!(temp.path().join("artifacts/Tasks.md").is_file());
        assert!(!legacy_path.exists());

        let updated = execute_builtin_tool(
            temp.path(),
            ToolInvocation {
                name: "task_manager".to_string(),
                arguments: json!({
                    "action": "update",
                    "target": "Port task manager",
                    "status": "done"
                }),
            },
        )
        .await
        .unwrap();
        assert!(updated.success);
        let checklist = std::fs::read_to_string(temp.path().join("artifacts/Tasks.md")).unwrap();
        assert!(checklist.contains("[x] Port task manager"));
    }

    #[tokio::test]
    async fn text_to_image_generate_creates_preview_artifacts() {
        let temp = tempfile::tempdir().unwrap();
        let result = execute_builtin_tool(
            temp.path(),
            ToolInvocation {
                name: "text_to_image".to_string(),
                arguments: json!({"action": "generate", "prompt": "neon terminal"}),
            },
        )
        .await
        .unwrap();
        assert!(result.success);
        let manifest = PathBuf::from(result.output["artifact_path"].as_str().unwrap());
        let preview = PathBuf::from(result.output["preview_path"].as_str().unwrap());
        assert!(manifest.is_file());
        assert!(preview.is_file());
    }
}
