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
    let path_value = args.get("path").and_then(Value::as_str).unwrap_or(".");
    let path = if operation == "mkdir" {
        writable_join(project_root, path_value)?
    } else {
        safe_join(project_root, path_value)?
    };
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
    let max_results = args.get("max_results").and_then(Value::as_u64).unwrap_or(5) as usize;

    // Try real DuckDuckGo HTML lite search first
    match ddg_html_search(query, max_results).await {
        Ok(results) if !results.is_empty() => Ok(ToolResult {
            success: true,
            output: json!({"query": query, "results": results, "source": "duckduckgo"}),
            error: None,
        }),
        _ => {
            // Fallback: return a search URL
            let encoded = query.replace(' ', "+");
            Ok(ToolResult {
                success: true,
                output: json!({
                    "query": query,
                    "results": [{
                        "title": format!("Search web for: {query}"),
                        "url": format!("https://duckduckgo.com/?q={encoded}"),
                        "snippet": "Live search unavailable; use this URL to search manually."
                    }],
                    "source": "fallback"
                }),
                error: None,
            })
        }
    }
}

/// Scrape DuckDuckGo HTML lite for search results.
async fn ddg_html_search(query: &str, max_results: usize) -> Result<Vec<Value>> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;
    let response = client
        .post("https://html.duckduckgo.com/html/")
        .header("User-Agent", "Mozilla/5.0 (compatible; Reverie/1.0)")
        .header("Content-Type", "application/x-www-form-urlencoded")
        .body(format!("q={}", urlencoding::form_urlencoded(query)))
        .send()
        .await?;
    if !response.status().is_success() {
        return Ok(Vec::new());
    }
    let html = response.text().await?;
    parse_ddg_html_results(&html, max_results)
}

/// Parse DuckDuckGo HTML lite response into structured results.
pub fn parse_ddg_html_results(html: &str, max_results: usize) -> Result<Vec<Value>> {
    use regex::Regex;

    let mut results = Vec::new();

    // DuckDuckGo HTML lite wraps each result in a div with class "result".
    // Each result has:
    //   <a class="result__a" href="...">Title</a>
    //   <a class="result__snippet">Snippet text</a>
    //
    // We parse these with regexes since we don't have an HTML DOM parser.

    // Match result blocks — each starts with class="result "
    let result_re = Regex::new(r#"(?is)class="result\s[^"]*"[^>]*>(.*?)</div>\s*</div>"#)?;
    let link_re = Regex::new(r#"(?is)class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>"#)?;
    let snippet_re = Regex::new(r#"(?is)class="result__snippet"[^>]*>(.*?)</a>"#)?;
    let tag_re = Regex::new(r"<[^>]+>")?;

    // Fallback: if the structured extraction finds nothing, try a simpler link+text approach
    for cap in result_re.captures_iter(html) {
        if results.len() >= max_results {
            break;
        }
        let block = &cap[1];

        let url = link_re
            .captures(block)
            .and_then(|c| Some(decode_ddg_url(c.get(1)?.as_str())));
        let title = link_re.captures(block).map(|c| {
            let raw = c.get(2).map(|m| m.as_str()).unwrap_or("");
            tag_re.replace_all(raw, "").trim().to_string()
        });
        let snippet = snippet_re.captures(block).map(|c| {
            let raw = c.get(1).map(|m| m.as_str()).unwrap_or("");
            let text = tag_re.replace_all(raw, "");
            text.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", "\"")
                .replace("&#39;", "'")
                .replace("&nbsp;", " ")
                .trim()
                .to_string()
        });

        if let (Some(url), Some(title)) = (url, title) {
            if !url.is_empty() && !title.is_empty() {
                results.push(json!({
                    "title": title,
                    "url": url,
                    "snippet": snippet.unwrap_or_default()
                }));
            }
        }
    }

    // Simpler fallback if no structured results found
    if results.is_empty() {
        let simple_re = Regex::new(r#"(?is)class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>"#)?;
        for cap in simple_re.captures_iter(html) {
            if results.len() >= max_results {
                break;
            }
            let url = decode_ddg_url(cap.get(1).map(|m| m.as_str()).unwrap_or(""));
            let title = tag_re
                .replace_all(cap.get(2).map(|m| m.as_str()).unwrap_or(""), "")
                .trim()
                .to_string();
            if !url.is_empty() && !title.is_empty() {
                results.push(json!({"title": title, "url": url, "snippet": ""}));
            }
        }
    }

    Ok(results)
}

/// DuckDuckGo wraps outbound URLs in a redirect; extract the real URL.
fn decode_ddg_url(raw: &str) -> String {
    // DDG HTML lite uses //duckduckgo.com/l/?uddg=<encoded_url>&...
    if let Some(rest) = raw
        .strip_prefix("//duckduckgo.com/l/?uddg=")
        .or_else(|| raw.strip_prefix("/l/?uddg="))
    {
        let encoded = rest.split('&').next().unwrap_or(rest);
        urlencoding::decode_url(encoded)
    } else if raw.starts_with("http") {
        raw.to_string()
    } else if raw.starts_with("//") {
        format!("https:{raw}")
    } else {
        raw.to_string()
    }
}

/// Minimal URL encoding/decoding helpers to avoid a new dependency.
mod urlencoding {
    /// Percent-encode a query string value.
    pub fn form_urlencoded(input: &str) -> String {
        let mut out = String::with_capacity(input.len() * 2);
        for byte in input.bytes() {
            match byte {
                b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'*' => {
                    out.push(byte as char);
                }
                b' ' => out.push('+'),
                _ => {
                    out.push('%');
                    out.push_str(&format!("{byte:02X}"));
                }
            }
        }
        out
    }

    /// Percent-decode a URL string.
    pub fn decode_url(input: &str) -> String {
        let mut out = Vec::with_capacity(input.len());
        let bytes = input.as_bytes();
        let mut i = 0;
        while i < bytes.len() {
            if bytes[i] == b'%' && i + 2 < bytes.len() {
                if let Ok(val) = u8::from_str_radix(&input[i + 1..i + 3], 16) {
                    out.push(val);
                    i += 3;
                    continue;
                }
            } else if bytes[i] == b'+' {
                out.push(b' ');
                i += 1;
                continue;
            }
            out.push(bytes[i]);
            i += 1;
        }
        String::from_utf8_lossy(&out).into_owned()
    }
}

async fn web_fetch(args: Value) -> Result<ToolResult> {
    let url = args
        .get("url")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("url is required"))?;
    let raw_html = reqwest::get(url).await?.text().await?;
    let readable = html_to_readable_text(&raw_html);
    Ok(ToolResult {
        success: true,
        output: json!({"url": url, "content": readable, "raw_length": raw_html.len()}),
        error: None,
    })
}

/// Convert raw HTML to readable plain text by stripping noise elements
/// (script, style, nav, header, footer, aside) and HTML tags, then
/// collapsing excess whitespace.
pub fn html_to_readable_text(html: &str) -> String {
    use regex::Regex;

    // Remove content inside noise elements (case-insensitive, non-greedy).
    // Rust regex does not support backreferences, so we match each tag separately.
    let mut cleaned = html.to_string();
    for tag in &[
        "script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "iframe",
    ] {
        let pattern = format!(r"(?is)<{tag}[^>]*>.*?</{tag}>");
        if let Ok(re) = Regex::new(&pattern) {
            cleaned = re.replace_all(&cleaned, "").into_owned();
        }
    }

    // Remove HTML comments
    let comment_re = Regex::new(r"(?s)<!--.*?-->").expect("static regex");
    cleaned = comment_re.replace_all(&cleaned, "").into_owned();

    // Replace block-level tags with newlines for readability
    let block_re = Regex::new(r"(?i)</?(p|div|br|h[1-6]|li|tr|blockquote|section|article)[^>]*>")
        .expect("static regex");
    cleaned = block_re.replace_all(&cleaned, "\n").into_owned();

    // Strip all remaining HTML tags
    let tag_re = Regex::new(r"<[^>]+>").expect("static regex");
    let text = tag_re.replace_all(&cleaned, "");

    // Decode common HTML entities
    let text = text
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&nbsp;", " ");

    // Collapse runs of whitespace and blank lines
    let ws_re = Regex::new(r"[ \t]+").expect("static regex");
    let text = ws_re.replace_all(&text, " ");
    let nl_re = Regex::new(r"\n[ \t]*\n+").expect("static regex");
    let text = nl_re.replace_all(&text, "\n\n");

    text.trim().to_string()
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
    let state_path = writable_join(project_root, "artifacts/game_program.json")?;
    let mut state = if state_path.is_file() {
        serde_json::from_str::<Value>(&std::fs::read_to_string(&state_path)?)?
    } else {
        json!({
            "schema": "reverie.game_program.v2",
            "project_name": project_name,
            "scope": "vertical_slice",
            "runtime_targets": ["reverie_engine", "godot", "o3de"],
            "pipeline_stages": [],
            "systems": {},
            "verification": { "checks": [], "score": 0 },
            "status": "idle"
        })
    };

    match action {
        "compile_request" => {
            state["project_name"] = json!(project_name);
            state["request"] = json!(prompt);
            state["status"] = json!("compiled");
            // Generate a production pipeline with stages
            let stages = json!([
                {"id": "design", "name": "Design Document", "status": "pending", "order": 1},
                {"id": "prototype", "name": "Prototype Systems", "status": "pending", "order": 2},
                {"id": "vertical_slice", "name": "Vertical Slice Build", "status": "pending", "order": 3},
                {"id": "playtest", "name": "Playtest & QA", "status": "pending", "order": 4},
                {"id": "polish", "name": "Polish & Ship", "status": "pending", "order": 5}
            ]);
            state["pipeline_stages"] = stages;
        }
        "add_system" => {
            let system_id = args
                .get("system_id")
                .and_then(Value::as_str)
                .unwrap_or("unnamed");
            let system_def = json!({
                "name": args.get("name").and_then(Value::as_str).unwrap_or(system_id),
                "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                "priority": args.get("priority").and_then(Value::as_str).unwrap_or("medium"),
                "dependencies": args.get("dependencies").cloned().unwrap_or(json!([])),
                "status": "designed",
                "files": []
            });
            state["systems"][system_id] = system_def;
        }
        "advance_stage" => {
            let stage_id = args.get("stage_id").and_then(Value::as_str).unwrap_or("");
            let new_status = args
                .get("status")
                .and_then(Value::as_str)
                .unwrap_or("in_progress");
            if let Some(stages) = state["pipeline_stages"].as_array_mut() {
                if let Some(stage) = stages
                    .iter_mut()
                    .find(|s| s.get("id").and_then(Value::as_str) == Some(stage_id))
                {
                    stage["status"] = json!(new_status);
                    stage["updated_at"] = json!(chrono::Utc::now().to_rfc3339());
                }
            }
        }
        "set_runtime_target" => {
            let target = args
                .get("target")
                .and_then(Value::as_str)
                .unwrap_or("reverie_engine");
            let config = args.get("config").cloned().unwrap_or(json!({}));
            if state.get("runtime_configs").is_none() {
                state["runtime_configs"] = json!({});
            }
            state["runtime_configs"][target] = json!({
                "enabled": true,
                "config": config,
                "updated_at": chrono::Utc::now().to_rfc3339()
            });
        }
        "verify" => {
            let check_id = args
                .get("check_id")
                .and_then(Value::as_str)
                .unwrap_or("smoke");
            let passed = args.get("passed").and_then(Value::as_bool).unwrap_or(false);
            let check = json!({
                "id": check_id,
                "passed": passed,
                "notes": args.get("notes").and_then(Value::as_str).unwrap_or(""),
                "checked_at": chrono::Utc::now().to_rfc3339()
            });
            if let Some(checks) = state["verification"]["checks"].as_array_mut() {
                // Replace existing check or append
                if let Some(pos) = checks
                    .iter()
                    .position(|c| c.get("id").and_then(Value::as_str) == Some(check_id))
                {
                    checks[pos] = check;
                } else {
                    checks.push(check);
                }
                let passed_count = checks
                    .iter()
                    .filter(|c| c.get("passed").and_then(Value::as_bool) == Some(true))
                    .count();
                let total = checks.len();
                state["verification"]["score"] =
                    json!((passed_count * 100).checked_div(total).unwrap_or(0));
            }
        }
        "status" => {
            // No mutation, just return current state
        }
        _ => {
            state["last_action"] = json!(action);
            state["last_payload"] = args;
        }
    }

    if let Some(parent) = state_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&state_path, serde_json::to_string_pretty(&state)?)?;

    // Compute summary
    let stages = state["pipeline_stages"].as_array();
    let total_stages = stages.map(|a| a.len()).unwrap_or(0);
    let done_stages = stages
        .map(|a| {
            a.iter()
                .filter(|s| {
                    matches!(
                        s.get("status").and_then(Value::as_str),
                        Some("done") | Some("completed")
                    )
                })
                .count()
        })
        .unwrap_or(0);
    let system_count = state["systems"].as_object().map(|o| o.len()).unwrap_or(0);

    Ok(ToolResult {
        success: true,
        output: json!({
            "state_path": state_path,
            "state": state,
            "summary": {
                "project_name": state.get("project_name").and_then(Value::as_str).unwrap_or(""),
                "total_stages": total_stages,
                "completed_stages": done_stages,
                "progress_pct": (done_stages * 100).checked_div(total_stages).unwrap_or(0),
                "systems": system_count,
                "verification_score": state["verification"].get("score").and_then(Value::as_u64).unwrap_or(0),
                "status": state.get("status").and_then(Value::as_str).unwrap_or("idle")
            }
        }),
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
        .unwrap_or("status");
    let state_path = writable_join(project_root, "playtest/slice_score.json")?;
    let mut state = if state_path.is_file() {
        serde_json::from_str::<Value>(&std::fs::read_to_string(&state_path)?)?
    } else {
        json!({
            "schema": "reverie.slice_score.v2",
            "test_plans": [],
            "checks": [],
            "quality_gates": [],
            "score": 0,
            "status": "idle"
        })
    };

    match action {
        "create_test_plan" => {
            let plan = json!({
                "id": format!("tp-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()),
                "name": args.get("name").and_then(Value::as_str).unwrap_or("Test Plan"),
                "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                "scenarios": args.get("scenarios").cloned().unwrap_or(json!([])),
                "created_at": chrono::Utc::now().to_rfc3339(),
                "status": "pending"
            });
            if let Some(plans) = state["test_plans"].as_array_mut() {
                plans.push(plan);
            }
            state["status"] = json!("planning");
        }
        "add_check" => {
            let check = json!({
                "id": args.get("check_id").and_then(Value::as_str).unwrap_or("unnamed"),
                "category": args.get("category").and_then(Value::as_str).unwrap_or("functional"),
                "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                "status": "pending",
                "created_at": chrono::Utc::now().to_rfc3339()
            });
            if let Some(checks) = state["checks"].as_array_mut() {
                checks.push(check);
            }
        }
        "run_check" => {
            let check_id = args.get("check_id").and_then(Value::as_str).unwrap_or("");
            let passed = args.get("passed").and_then(Value::as_bool).unwrap_or(false);
            if let Some(checks) = state["checks"].as_array_mut() {
                if let Some(check) = checks
                    .iter_mut()
                    .find(|c| c.get("id").and_then(Value::as_str) == Some(check_id))
                {
                    check["status"] = json!(if passed { "passed" } else { "failed" });
                    check["result"] = json!({
                        "passed": passed,
                        "notes": args.get("notes").and_then(Value::as_str).unwrap_or(""),
                        "run_at": chrono::Utc::now().to_rfc3339()
                    });
                }
            }
            // Recalculate score
            if let Some(checks) = state["checks"].as_array() {
                let total = checks.len();
                let passed_count = checks
                    .iter()
                    .filter(|c| c.get("status").and_then(Value::as_str) == Some("passed"))
                    .count();
                state["score"] = json!((passed_count * 100).checked_div(total).unwrap_or(0));
            }
        }
        "add_quality_gate" => {
            let gate = json!({
                "name": args.get("name").and_then(Value::as_str).unwrap_or("Quality Gate"),
                "min_score": args.get("min_score").and_then(Value::as_u64).unwrap_or(80),
                "required_checks": args.get("required_checks").cloned().unwrap_or(json!([]))
            });
            if let Some(gates) = state["quality_gates"].as_array_mut() {
                gates.push(gate);
            }
        }
        "status" => {
            // No mutation
        }
        _ => {
            state["last_action"] = json!(action);
        }
    }

    if let Some(parent) = state_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&state_path, serde_json::to_string_pretty(&state)?)?;

    Ok(ToolResult {
        success: true,
        output: json!({
            "state_path": state_path,
            "state": state,
            "summary": {
                "test_plans": state["test_plans"].as_array().map(|a| a.len()).unwrap_or(0),
                "total_checks": state["checks"].as_array().map(|a| a.len()).unwrap_or(0),
                "passed_checks": state["checks"].as_array().map(|a| a.iter().filter(|c| c.get("status").and_then(Value::as_str) == Some("passed")).count()).unwrap_or(0),
                "score": state.get("score").and_then(Value::as_u64).unwrap_or(0),
                "quality_gates": state["quality_gates"].as_array().map(|a| a.len()).unwrap_or(0)
            }
        }),
        error: None,
    })
}

async fn game_gdd_manager(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("status");
    let project_name = args
        .get("project_name")
        .and_then(Value::as_str)
        .unwrap_or("Untitled Game");
    let state_path = writable_join(project_root, "artifacts/gdd.json")?;
    let mut gdd = if state_path.is_file() {
        serde_json::from_str::<Value>(&std::fs::read_to_string(&state_path)?)?
    } else {
        json!({
            "schema": "reverie.gdd.v2",
            "project_name": project_name,
            "sections": {
                "overview": "",
                "core_loop": "",
                "target_audience": "",
                "art_style": "",
                "technical_requirements": ""
            },
            "systems": [],
            "content_pillars": [],
            "milestones": [],
            "revision_history": []
        })
    };

    match action {
        "create" | "init" => {
            gdd["project_name"] = json!(project_name);
            if let Some(overview) = args.get("overview").and_then(Value::as_str) {
                gdd["sections"]["overview"] = json!(overview);
            }
            if let Some(core_loop) = args.get("core_loop").and_then(Value::as_str) {
                gdd["sections"]["core_loop"] = json!(core_loop);
            }
            gdd["created_at"] = json!(chrono::Utc::now().to_rfc3339());
        }
        "update_section" => {
            let section = args
                .get("section")
                .and_then(Value::as_str)
                .unwrap_or("overview");
            let content = args.get("content").and_then(Value::as_str).unwrap_or("");
            gdd["sections"][section] = json!(content);
            // Track revision
            let revision = json!({
                "section": section,
                "timestamp": chrono::Utc::now().to_rfc3339(),
                "summary": args.get("summary").and_then(Value::as_str).unwrap_or("Updated")
            });
            if let Some(history) = gdd["revision_history"].as_array_mut() {
                history.push(revision);
            }
        }
        "add_system" => {
            let system = json!({
                "name": args.get("name").and_then(Value::as_str).unwrap_or("unnamed"),
                "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                "priority": args.get("priority").and_then(Value::as_str).unwrap_or("medium"),
                "complexity": args.get("complexity").and_then(Value::as_str).unwrap_or("medium")
            });
            if let Some(systems) = gdd["systems"].as_array_mut() {
                systems.push(system);
            }
        }
        "add_content_pillar" => {
            let pillar = json!({
                "name": args.get("name").and_then(Value::as_str).unwrap_or("unnamed"),
                "description": args.get("description").and_then(Value::as_str).unwrap_or("")
            });
            if let Some(pillars) = gdd["content_pillars"].as_array_mut() {
                pillars.push(pillar);
            }
        }
        "status" => {
            // No mutation
        }
        _ => {
            gdd["last_action"] = json!(action);
        }
    }

    if let Some(parent) = state_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&state_path, serde_json::to_string_pretty(&gdd)?)?;

    let section_count = gdd["sections"]
        .as_object()
        .map(|o| {
            o.values()
                .filter(|v| !v.as_str().unwrap_or("").is_empty())
                .count()
        })
        .unwrap_or(0);
    let system_count = gdd["systems"].as_array().map(|a| a.len()).unwrap_or(0);

    Ok(ToolResult {
        success: true,
        output: json!({
            "state_path": state_path,
            "gdd": gdd,
            "summary": {
                "project_name": gdd.get("project_name").and_then(Value::as_str).unwrap_or(""),
                "sections_filled": section_count,
                "systems_defined": system_count,
                "revisions": gdd["revision_history"].as_array().map(|a| a.len()).unwrap_or(0)
            }
        }),
        error: None,
    })
}

async fn game_asset_manager(project_root: &Path, args: Value) -> Result<ToolResult> {
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("status");
    let state_path = writable_join(project_root, "artifacts/asset_pipeline.json")?;
    let mut state = if state_path.is_file() {
        serde_json::from_str::<Value>(&std::fs::read_to_string(&state_path)?)?
    } else {
        json!({
            "schema": "reverie.assets.v2",
            "assets": [],
            "categories": {},
            "notes": "",
            "stats": {"total": 0, "by_type": {}}
        })
    };

    match action {
        "add" | "register" => {
            let asset = json!({
                "id": args.get("id").and_then(Value::as_str)
                    .unwrap_or(&format!("asset-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis())),
                "name": args.get("name").and_then(Value::as_str).unwrap_or("unnamed"),
                "type": args.get("asset_type").and_then(Value::as_str).unwrap_or("generic"),
                "path": args.get("path").and_then(Value::as_str).unwrap_or(""),
                "tags": args.get("tags").cloned().unwrap_or(json!([])),
                "status": "registered",
                "created_at": chrono::Utc::now().to_rfc3339()
            });
            let asset_type = asset["type"].as_str().unwrap_or("generic").to_string();
            if let Some(assets) = state["assets"].as_array_mut() {
                assets.push(asset);
            }
            // Update type counts
            let count = state["stats"]["by_type"]
                .get(&asset_type)
                .and_then(Value::as_u64)
                .unwrap_or(0);
            state["stats"]["by_type"][&asset_type] = json!(count + 1);
            state["stats"]["total"] =
                json!(state["assets"].as_array().map(|a| a.len()).unwrap_or(0));
        }
        "update" => {
            let asset_id = args.get("id").and_then(Value::as_str).unwrap_or("");
            if let Some(assets) = state["assets"].as_array_mut() {
                if let Some(asset) = assets
                    .iter_mut()
                    .find(|a| a.get("id").and_then(Value::as_str) == Some(asset_id))
                {
                    if let Some(status) = args.get("status").and_then(Value::as_str) {
                        asset["status"] = json!(status);
                    }
                    if let Some(path) = args.get("path").and_then(Value::as_str) {
                        asset["path"] = json!(path);
                    }
                    asset["updated_at"] = json!(chrono::Utc::now().to_rfc3339());
                }
            }
        }
        "list" => {
            let type_filter = args.get("asset_type").and_then(Value::as_str);
            if let Some(filter) = type_filter {
                let filtered: Vec<_> = state["assets"]
                    .as_array()
                    .unwrap_or(&Vec::new())
                    .iter()
                    .filter(|a| a.get("type").and_then(Value::as_str) == Some(filter))
                    .cloned()
                    .collect();
                return Ok(ToolResult {
                    success: true,
                    output: json!({"assets": filtered, "filter": filter, "count": filtered.len()}),
                    error: None,
                });
            }
        }
        "set_notes" => {
            if let Some(notes) = args.get("notes").and_then(Value::as_str) {
                state["notes"] = json!(notes);
            }
        }
        "status" => {}
        _ => {
            state["last_action"] = json!(action);
        }
    }

    if let Some(parent) = state_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&state_path, serde_json::to_string_pretty(&state)?)?;

    Ok(ToolResult {
        success: true,
        output: json!({
            "state_path": state_path,
            "state": state,
            "summary": {
                "total_assets": state["stats"]["total"].as_u64().unwrap_or(0),
                "by_type": state["stats"]["by_type"].clone()
            }
        }),
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
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("analyze");
    let state_path = writable_join(project_root, &format!("artifacts/{tool_name}.json"))?;
    let mut state = if state_path.is_file() {
        serde_json::from_str::<Value>(&std::fs::read_to_string(&state_path)?)?
    } else {
        json!({
            "schema": format!("reverie.{tool_name}.v2"),
            "analyses": [],
            "datasets": {},
            "status": "ready"
        })
    };

    match action {
        "analyze" => {
            let analysis = json!({
                "id": format!("analysis-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()),
                "type": tool_name,
                "input": args.get("input").cloned().unwrap_or(json!({})),
                "parameters": args.get("parameters").cloned().unwrap_or(json!({})),
                "created_at": chrono::Utc::now().to_rfc3339(),
                "status": "completed",
                "findings": [],
                "recommendations": []
            });
            if let Some(analyses) = state["analyses"].as_array_mut() {
                analyses.push(analysis);
            }
        }
        "add_dataset" => {
            let dataset_id = args
                .get("dataset_id")
                .and_then(Value::as_str)
                .unwrap_or("default");
            state["datasets"][dataset_id] = json!({
                "data": args.get("data").cloned().unwrap_or(json!([])),
                "labels": args.get("labels").cloned().unwrap_or(json!({})),
                "added_at": chrono::Utc::now().to_rfc3339()
            });
        }
        "simulate" => {
            let iterations = args
                .get("iterations")
                .and_then(Value::as_u64)
                .unwrap_or(1000);
            let params = args.get("parameters").cloned().unwrap_or(json!({}));
            // Simple simulation result structure
            let simulation = json!({
                "id": format!("sim-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()),
                "iterations": iterations,
                "parameters": params,
                "result": {
                    "mean": 0.0,
                    "std_dev": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "percentiles": {"p50": 0.0, "p90": 0.0, "p99": 0.0}
                },
                "status": "needs_data",
                "note": "Populate datasets first, then run simulate to get real results.",
                "created_at": chrono::Utc::now().to_rfc3339()
            });
            if let Some(analyses) = state["analyses"].as_array_mut() {
                analyses.push(simulation);
            }
        }
        "status" => {}
        _ => {
            state["last_action"] = json!(action);
        }
    }

    if let Some(parent) = state_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&state_path, serde_json::to_string_pretty(&state)?)?;

    Ok(ToolResult {
        success: true,
        output: json!({
            "state_path": state_path,
            "state": state,
            "summary": {
                "tool": tool_name,
                "analyses": state["analyses"].as_array().map(|a| a.len()).unwrap_or(0),
                "datasets": state["datasets"].as_object().map(|o| o.len()).unwrap_or(0)
            }
        }),
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
            "schema": "reverie.atlas_delivery_state.v2",
            "slices": [],
            "blockers": [],
            "checkpoints": [],
            "milestones": [],
            "document_registry": {},
            "delivery_status": "idle"
        })
    };

    match action {
        "status" => {}
        "add_slice" => {
            let slice = json!({
                "id": format!("slice-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()),
                "title": args.get("title").and_then(Value::as_str).unwrap_or("Untitled Slice"),
                "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                "status": "pending",
                "created_at": chrono::Utc::now().to_rfc3339(),
                "dependencies": args.get("dependencies").cloned().unwrap_or(json!([])),
                "assignee": args.get("assignee").and_then(Value::as_str)
            });
            state["slices"]
                .as_array_mut()
                .unwrap_or(&mut Vec::new())
                .push(slice);
            state["delivery_status"] = json!("in_progress");
        }
        "update_slice" => {
            let slice_id = args.get("slice_id").and_then(Value::as_str).unwrap_or("");
            if let Some(slices) = state["slices"].as_array_mut() {
                if let Some(slice) = slices
                    .iter_mut()
                    .find(|s| s.get("id").and_then(Value::as_str) == Some(slice_id))
                {
                    if let Some(status) = args.get("status").and_then(Value::as_str) {
                        slice["status"] = json!(status);
                    }
                    if let Some(notes) = args.get("notes").and_then(Value::as_str) {
                        slice["notes"] = json!(notes);
                    }
                    slice["updated_at"] = json!(chrono::Utc::now().to_rfc3339());
                }
            }
        }
        "add_blocker" => {
            let blocker = json!({
                "id": format!("blocker-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()),
                "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                "severity": args.get("severity").and_then(Value::as_str).unwrap_or("medium"),
                "related_slice": args.get("slice_id").and_then(Value::as_str),
                "status": "open",
                "created_at": chrono::Utc::now().to_rfc3339()
            });
            state["blockers"]
                .as_array_mut()
                .unwrap_or(&mut Vec::new())
                .push(blocker);
        }
        "resolve_blocker" => {
            let blocker_id = args.get("blocker_id").and_then(Value::as_str).unwrap_or("");
            if let Some(blockers) = state["blockers"].as_array_mut() {
                if let Some(blocker) = blockers
                    .iter_mut()
                    .find(|b| b.get("id").and_then(Value::as_str) == Some(blocker_id))
                {
                    blocker["status"] = json!("resolved");
                    blocker["resolved_at"] = json!(chrono::Utc::now().to_rfc3339());
                    blocker["resolution"] =
                        json!(args.get("resolution").and_then(Value::as_str).unwrap_or(""));
                }
            }
        }
        "checkpoint" => {
            let checkpoint = json!({
                "id": format!("cp-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()),
                "label": args.get("label").and_then(Value::as_str).unwrap_or("checkpoint"),
                "created_at": chrono::Utc::now().to_rfc3339(),
                "slice_summary": state["slices"].as_array().map(|s| {
                    let total = s.len();
                    let done = s.iter().filter(|x| x.get("status").and_then(Value::as_str) == Some("done")).count();
                    json!({"total": total, "done": done, "progress_pct": (done * 100).checked_div(total).unwrap_or(0)})
                }).unwrap_or(json!({"total": 0, "done": 0, "progress_pct": 0}))
            });
            state["checkpoints"]
                .as_array_mut()
                .unwrap_or(&mut Vec::new())
                .push(checkpoint);
        }
        "add_milestone" => {
            let milestone = json!({
                "id": format!("ms-{}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()),
                "title": args.get("title").and_then(Value::as_str).unwrap_or("Milestone"),
                "target_date": args.get("target_date").and_then(Value::as_str),
                "status": "upcoming",
                "criteria": args.get("criteria").cloned().unwrap_or(json!([]))
            });
            state["milestones"]
                .as_array_mut()
                .unwrap_or(&mut Vec::new())
                .push(milestone);
        }
        "register_document" => {
            let doc_id = args
                .get("doc_id")
                .and_then(Value::as_str)
                .unwrap_or("unnamed");
            let doc = json!({
                "path": args.get("path").and_then(Value::as_str).unwrap_or(""),
                "type": args.get("doc_type").and_then(Value::as_str).unwrap_or("generic"),
                "version": args.get("version").and_then(Value::as_str).unwrap_or("1.0"),
                "registered_at": chrono::Utc::now().to_rfc3339()
            });
            state["document_registry"][doc_id] = doc;
        }
        _ => {
            state["last_action"] = json!(action);
            state["last_payload"] = args;
        }
    }

    if let Some(parent) = state_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&state_path, serde_json::to_string_pretty(&state)?)?;

    // Compute summary
    let slices = state["slices"].as_array().map(|a| a.len()).unwrap_or(0);
    let done_slices = state["slices"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter(|s| s.get("status").and_then(Value::as_str) == Some("done"))
                .count()
        })
        .unwrap_or(0);
    let open_blockers = state["blockers"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter(|b| b.get("status").and_then(Value::as_str) == Some("open"))
                .count()
        })
        .unwrap_or(0);

    Ok(ToolResult {
        success: true,
        output: json!({
            "state_path": state_path,
            "state": state,
            "summary": {
                "total_slices": slices,
                "done_slices": done_slices,
                "progress_pct": (done_slices * 100).checked_div(slices).unwrap_or(0),
                "open_blockers": open_blockers,
                "delivery_status": state.get("delivery_status").and_then(Value::as_str).unwrap_or("idle")
            }
        }),
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
    let action = args
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("analyze");
    let content = args
        .get("content")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let state_dir = writable_join(project_root, "artifacts/writer")?;
    std::fs::create_dir_all(&state_dir)?;

    match tool_name {
        "novel_context_manager" => {
            let memory_path = state_dir.join("novel_memory.json");
            let mut memory = if memory_path.is_file() {
                serde_json::from_str::<Value>(&std::fs::read_to_string(&memory_path)?)?
            } else {
                json!({
                    "schema": "reverie.writer.novel_memory.v2",
                    "characters": {},
                    "locations": {},
                    "plot_threads": [],
                    "timeline": [],
                    "world_rules": [],
                    "chapters_indexed": 0
                })
            };

            match action {
                "add_character" => {
                    let name = args
                        .get("name")
                        .and_then(Value::as_str)
                        .unwrap_or("Unknown");
                    let character = json!({
                        "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                        "traits": args.get("traits").cloned().unwrap_or(json!([])),
                        "relationships": args.get("relationships").cloned().unwrap_or(json!({})),
                        "first_appearance": args.get("chapter").and_then(Value::as_str),
                        "updated_at": chrono::Utc::now().to_rfc3339()
                    });
                    memory["characters"][name] = character;
                }
                "add_location" => {
                    let name = args
                        .get("name")
                        .and_then(Value::as_str)
                        .unwrap_or("Unknown");
                    let location = json!({
                        "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                        "features": args.get("features").cloned().unwrap_or(json!([])),
                        "connected_to": args.get("connected_to").cloned().unwrap_or(json!([]))
                    });
                    memory["locations"][name] = location;
                }
                "add_plot_thread" => {
                    let thread = json!({
                        "title": args.get("title").and_then(Value::as_str).unwrap_or("Untitled"),
                        "status": args.get("status").and_then(Value::as_str).unwrap_or("open"),
                        "description": args.get("description").and_then(Value::as_str).unwrap_or(""),
                        "related_characters": args.get("characters").cloned().unwrap_or(json!([]))
                    });
                    memory["plot_threads"]
                        .as_array_mut()
                        .unwrap_or(&mut Vec::new())
                        .push(thread);
                }
                "add_timeline_event" => {
                    let event = json!({
                        "chapter": args.get("chapter").and_then(Value::as_str),
                        "event": args.get("event").and_then(Value::as_str).unwrap_or(""),
                        "characters_involved": args.get("characters").cloned().unwrap_or(json!([]))
                    });
                    memory["timeline"]
                        .as_array_mut()
                        .unwrap_or(&mut Vec::new())
                        .push(event);
                }
                "add_world_rule" => {
                    let rule = json!({
                        "rule": args.get("rule").and_then(Value::as_str).unwrap_or(""),
                        "category": args.get("category").and_then(Value::as_str).unwrap_or("general")
                    });
                    memory["world_rules"]
                        .as_array_mut()
                        .unwrap_or(&mut Vec::new())
                        .push(rule);
                }
                "index_chapter" => {
                    if let Some(count) = memory["chapters_indexed"].as_u64() {
                        memory["chapters_indexed"] = json!(count + 1);
                    }
                }
                "query" => {
                    let query_type = args
                        .get("query_type")
                        .and_then(Value::as_str)
                        .unwrap_or("all");
                    let result = match query_type {
                        "characters" => json!({"characters": memory["characters"]}),
                        "locations" => json!({"locations": memory["locations"]}),
                        "plot_threads" => json!({"plot_threads": memory["plot_threads"]}),
                        "timeline" => json!({"timeline": memory["timeline"]}),
                        _ => memory.clone(),
                    };
                    return Ok(ToolResult {
                        success: true,
                        output: result,
                        error: None,
                    });
                }
                _ => {}
            }

            std::fs::write(&memory_path, serde_json::to_string_pretty(&memory)?)?;
            let summary = json!({
                "characters": memory["characters"].as_object().map(|o| o.len()).unwrap_or(0),
                "locations": memory["locations"].as_object().map(|o| o.len()).unwrap_or(0),
                "plot_threads": memory["plot_threads"].as_array().map(|a| a.len()).unwrap_or(0),
                "timeline_events": memory["timeline"].as_array().map(|a| a.len()).unwrap_or(0),
                "world_rules": memory["world_rules"].as_array().map(|a| a.len()).unwrap_or(0),
                "chapters_indexed": memory["chapters_indexed"]
            });
            Ok(ToolResult {
                success: true,
                output: json!({"memory_path": memory_path, "summary": summary, "memory": memory}),
                error: None,
            })
        }
        "consistency_checker" => {
            let memory_path = state_dir.join("novel_memory.json");
            let memory = if memory_path.is_file() {
                serde_json::from_str::<Value>(&std::fs::read_to_string(&memory_path)?)?
            } else {
                json!({"characters": {}, "locations": {}, "plot_threads": [], "timeline": [], "world_rules": []})
            };

            let mut issues = Vec::new();

            // Check for characters mentioned in plot threads but not defined
            if let Some(threads) = memory["plot_threads"].as_array() {
                for thread in threads {
                    if let Some(chars) = thread.get("related_characters").and_then(Value::as_array)
                    {
                        for c in chars {
                            if let Some(name) = c.as_str() {
                                if memory["characters"].get(name).is_none() {
                                    issues.push(json!({
                                        "type": "undefined_character",
                                        "severity": "warning",
                                        "message": format!("Character '{}' referenced in plot thread '{}' but not defined", name, thread.get("title").and_then(Value::as_str).unwrap_or("?"))
                                    }));
                                }
                            }
                        }
                    }
                }
            }

            // Check for open plot threads
            if let Some(threads) = memory["plot_threads"].as_array() {
                let open_count = threads
                    .iter()
                    .filter(|t| t.get("status").and_then(Value::as_str) == Some("open"))
                    .count();
                if open_count > 5 {
                    issues.push(json!({
                        "type": "too_many_open_threads",
                        "severity": "info",
                        "message": format!("{} open plot threads. Consider resolving some.", open_count)
                    }));
                }
            }

            // Check content if provided for inconsistencies with memory
            if !content.is_empty() {
                if let Some(chars) = memory["characters"].as_object() {
                    for (name, _) in chars {
                        if !content.contains(name.as_str()) && content.len() > 500 {
                            issues.push(json!({
                                "type": "missing_character",
                                "severity": "info",
                                "message": format!("Character '{}' not mentioned in provided content", name)
                            }));
                        }
                    }
                }
            }

            Ok(ToolResult {
                success: true,
                output: json!({
                    "issues": issues,
                    "issue_count": issues.len(),
                    "severity_breakdown": {
                        "error": issues.iter().filter(|i| i.get("severity").and_then(Value::as_str) == Some("error")).count(),
                        "warning": issues.iter().filter(|i| i.get("severity").and_then(Value::as_str) == Some("warning")).count(),
                        "info": issues.iter().filter(|i| i.get("severity").and_then(Value::as_str) == Some("info")).count()
                    }
                }),
                error: None,
            })
        }
        "plot_analyzer" => {
            let memory_path = state_dir.join("novel_memory.json");
            let memory = if memory_path.is_file() {
                serde_json::from_str::<Value>(&std::fs::read_to_string(&memory_path)?)?
            } else {
                json!({"characters": {}, "plot_threads": [], "timeline": []})
            };

            let thread_count = memory["plot_threads"]
                .as_array()
                .map(|a| a.len())
                .unwrap_or(0);
            let open_threads = memory["plot_threads"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .filter(|t| t.get("status").and_then(Value::as_str) == Some("open"))
                        .count()
                })
                .unwrap_or(0);
            let resolved_threads = memory["plot_threads"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .filter(|t| {
                            t.get("status").and_then(Value::as_str) == Some("resolved")
                                || t.get("status").and_then(Value::as_str) == Some("closed")
                        })
                        .count()
                })
                .unwrap_or(0);
            let timeline_events = memory["timeline"].as_array().map(|a| a.len()).unwrap_or(0);
            let character_count = memory["characters"]
                .as_object()
                .map(|o| o.len())
                .unwrap_or(0);

            // Analyze pacing from timeline
            let pacing_assessment = if timeline_events == 0 {
                "No timeline data available"
            } else if timeline_events < 5 {
                "Early stage — limited events tracked"
            } else if open_threads as f64 / (thread_count.max(1) as f64) > 0.8 {
                "Many unresolved threads — rising tension"
            } else if resolved_threads > open_threads {
                "Resolution phase — threads are closing"
            } else {
                "Balanced pacing"
            };

            Ok(ToolResult {
                success: true,
                output: json!({
                    "analysis": {
                        "total_plot_threads": thread_count,
                        "open_threads": open_threads,
                        "resolved_threads": resolved_threads,
                        "timeline_events": timeline_events,
                        "character_count": character_count,
                        "pacing_assessment": pacing_assessment,
                        "thread_resolution_rate": (resolved_threads * 100).checked_div(thread_count).map(|r| format!("{}%", r)).unwrap_or_else(|| "N/A".to_string())
                    },
                    "recommendations": writer_plot_recommendations(open_threads, resolved_threads, character_count)
                }),
                error: None,
            })
        }
        _ => {
            // Fallback for unknown writer tools
            let artifact = json!({
                "schema": format!("reverie.writer.{tool_name}.v1"),
                "action": action,
                "content": content,
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
    }
}

fn writer_plot_recommendations(open: usize, resolved: usize, characters: usize) -> Vec<String> {
    let mut recs = Vec::new();
    if open > 10 {
        recs.push("Consider resolving some plot threads before introducing new ones.".to_string());
    }
    if open > 0 && resolved == 0 {
        recs.push(
            "No threads resolved yet. Plan resolution points for narrative satisfaction."
                .to_string(),
        );
    }
    if characters > 15 {
        recs.push("Large cast size. Ensure each character has a distinct role.".to_string());
    }
    if characters < 3 && open > 3 {
        recs.push(
            "Few characters managing many threads. Consider whether complexity matches cast."
                .to_string(),
        );
    }
    if recs.is_empty() {
        recs.push("Story structure looks balanced.".to_string());
    }
    recs
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

    #[test]
    fn html_to_readable_strips_scripts_and_styles() {
        let html = r#"<html><head><style>body{color:red}</style></head>
        <body><script>alert('x')</script><p>Hello world</p></body></html>"#;
        let text = html_to_readable_text(html);
        assert!(!text.contains("alert"));
        assert!(!text.contains("color:red"));
        assert!(text.contains("Hello world"));
    }

    #[test]
    fn html_to_readable_strips_nav_footer_header() {
        let html = r#"<nav><a href="/">Home</a></nav>
        <main><p>Main content here.</p></main>
        <footer>Copyright 2024</footer>"#;
        let text = html_to_readable_text(html);
        assert!(!text.contains("Home"));
        assert!(!text.contains("Copyright"));
        assert!(text.contains("Main content here."));
    }

    #[test]
    fn html_to_readable_decodes_entities() {
        let html = "<p>A &amp; B &lt; C &gt; D &quot;E&quot; &#39;F&#39;</p>";
        let text = html_to_readable_text(html);
        assert!(text.contains("A & B < C > D \"E\" 'F'"));
    }

    #[test]
    fn html_to_readable_collapses_whitespace() {
        let html = "<p>  lots   of   spaces  </p>\n\n\n\n<p>second</p>";
        let text = html_to_readable_text(html);
        assert!(!text.contains("   "));
        assert!(text.contains("lots of spaces"));
        assert!(text.contains("second"));
    }

    #[test]
    fn html_to_readable_empty_input() {
        assert_eq!(html_to_readable_text(""), "");
    }

    #[test]
    fn ddg_url_decode_extracts_real_url() {
        let raw = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc";
        assert_eq!(decode_ddg_url(raw), "https://example.com/page");
    }

    #[test]
    fn ddg_url_decode_passthrough_direct_urls() {
        assert_eq!(
            decode_ddg_url("https://rust-lang.org"),
            "https://rust-lang.org"
        );
    }

    #[test]
    fn parse_ddg_html_extracts_results() {
        let html = r#"
        <div class="result results_links results_links_deep web-result ">
        <div>
            <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.rust-lang.org%2F&amp;rut=abc">Rust Programming Language</a>
            <a class="result__snippet">A language empowering everyone to build reliable and efficient software.</a>
        </div></div>
        <div class="result results_links results_links_deep web-result ">
        <div>
            <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdoc.rust-lang.org%2F&amp;rut=def">Rust Documentation</a>
            <a class="result__snippet">Learn Rust with examples and guides.</a>
        </div></div>
        "#;
        let results = parse_ddg_html_results(html, 5).unwrap();
        assert_eq!(results.len(), 2);
        assert_eq!(results[0]["title"], "Rust Programming Language");
        assert_eq!(results[0]["url"], "https://www.rust-lang.org/");
        assert!(results[0]["snippet"]
            .as_str()
            .unwrap()
            .contains("reliable and efficient"));
        assert_eq!(results[1]["url"], "https://doc.rust-lang.org/");
    }

    #[test]
    fn parse_ddg_html_respects_max_results() {
        let mut html = String::new();
        for i in 0..20 {
            html.push_str(&format!(
                r#"<div class="result results_links web-result "><div>
                <a class="result__a" href="https://example.com/{i}">Result {i}</a>
                <a class="result__snippet">Snippet {i}</a>
                </div></div>"#
            ));
        }
        let results = parse_ddg_html_results(&html, 3).unwrap();
        assert_eq!(results.len(), 3);
    }

    #[test]
    fn parse_ddg_html_empty_returns_empty() {
        let results = parse_ddg_html_results("<html><body>No results</body></html>", 5).unwrap();
        assert!(results.is_empty());
    }

    #[test]
    fn urlencoding_form_roundtrip() {
        let input = "rust programming language";
        let encoded = urlencoding::form_urlencoded(input);
        assert_eq!(encoded, "rust+programming+language");
        let decoded = urlencoding::decode_url(&encoded);
        assert_eq!(decoded, input);
    }

    #[test]
    fn urlencoding_special_chars() {
        let input = "hello world & foo=bar";
        let encoded = urlencoding::form_urlencoded(input);
        assert!(!encoded.contains(' '));
        assert!(!encoded.contains('&'));
        let decoded = urlencoding::decode_url(&encoded);
        assert_eq!(decoded, input);
    }
}
