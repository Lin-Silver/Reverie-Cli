use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs,
    io::{self, Write},
    path::{Component, Path, PathBuf},
};

pub mod command;

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

#[derive(Debug, Serialize, Deserialize)]
pub struct ToolResult {
    pub success: bool,
    pub output: String,
    pub error: Option<String>,
    pub data: Value,
    pub status: String,
}

impl ToolResult {
    pub fn ok(output: impl Into<String>, data: Value) -> Self {
        Self {
            success: true,
            output: output.into(),
            error: None,
            data,
            status: "success".into(),
        }
    }
    pub fn fail(error: impl ToString) -> Self {
        Self {
            success: false,
            output: String::new(),
            error: Some(error.to_string()),
            data: json!({}),
            status: "error".into(),
        }
    }
    pub fn not_started(error: impl ToString) -> Self {
        let mut result = Self::fail(error);
        result.status = "cancelled".into();
        result.data = json!({"delivery":"not_started"});
        result
    }
}

pub fn tools() -> Vec<Value> {
    vec![
        json!({"type":"function","function":{"name":"file_ops","description":"Read, list, inspect or create directories inside the active workspace.","parameters":{"type":"object","properties":{"operation":{"type":"string","enum":["read","list","exists","info","mkdir"]},"path":{"type":"string"},"recursive":{"type":"boolean"},"pattern":{"type":"string"}},"required":["operation","path"]}}}),
        json!({"type":"function","function":{"name":"str_replace_editor","description":"View or edit workspace files. Replacement text must match exactly once. Create will not overwrite existing files.","parameters":{"type":"object","properties":{"command":{"type":"string","enum":["view","str_replace","create","insert"]},"path":{"type":"string"},"old_str":{"type":"string"},"new_str":{"type":"string"},"file_text":{"type":"string"},"view_range":{"type":"array","items":{"type":"integer"}},"insert_line":{"type":"integer"}},"required":["command","path"]}}}),
        json!({"type":"function","function":{"name":"create_file","description":"Create a complete workspace file; explicit overwrite is required when it already exists.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"},"overwrite":{"type":"boolean"}},"required":["path","content"]}}}),
        json!({"type":"function","function":{"name":"command_exec","description":"Execute one audited noninteractive workspace command. Standard input is closed. Native executable arguments are passed directly; PowerShell cmdlet pipelines are supported. Custom environment overrides, inline interpreter code and terminal move/delete operations are disabled. Paths must stay in the workspace except the packaged Motion entry returned by skill_lookup: invoke it as node followed by its quoted absolute path. All permission and approval checks apply. Use delete_file for deletion.","parameters":{"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"},"timeout":{"type":"integer","minimum":1,"default":120},"env":{"type":"object","description":"Custom environment overrides are disabled."}},"required":["command"]}}}),
    ]
}

pub fn is_read_only(name: &str, args: &Value) -> bool {
    [
        "codebase-retrieval",
        "codebase_retrieval",
        "retrieve_codebase",
        "repo_context",
        "skill_lookup",
        "skill_search",
        "skills_help",
    ]
    .contains(&name)
        || (name == "file_ops"
            && matches!(
                args["operation"].as_str(),
                Some("read" | "list" | "exists" | "info")
            ))
        || (name == "str_replace_editor" && args["command"] == "view")
}

pub fn workspace_path(root: &Path, value: &str) -> Result<PathBuf> {
    let root = root.canonicalize()?;
    let input = Path::new(value);
    if input
        .components()
        .any(|piece| matches!(piece, Component::ParentDir))
    {
        return Err("Parent-directory paths are outside the workspace contract.".into());
    }
    let path = if input.is_absolute() {
        input.to_owned()
    } else {
        root.join(input)
    };
    let mut existing = path.clone();
    let mut tail = Vec::new();
    while !existing.exists() {
        if fs::symlink_metadata(&existing).is_ok() {
            return Err("Broken links are not valid workspace paths.".into());
        }
        let name = existing
            .file_name()
            .ok_or("Workspace path has no existing parent.")?
            .to_owned();
        tail.push(name);
        existing = existing
            .parent()
            .ok_or("Workspace path has no parent.")?
            .to_owned();
    }
    let mut resolved = existing.canonicalize()?;
    if !resolved.starts_with(&root) {
        return Err("Path is outside the active workspace.".into());
    }
    for name in tail.into_iter().rev() {
        resolved.push(name);
    }
    Ok(resolved)
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| format!("{key} must be text.").into())
}

pub fn execute(name: &str, args: &Value, root: &Path, backups: &Path) -> ToolResult {
    match execute_checked(name, args, root, backups) {
        Ok(result) => result,
        Err(error) => ToolResult::fail(error),
    }
}

fn execute_checked(name: &str, args: &Value, root: &Path, backups: &Path) -> Result<ToolResult> {
    if !args.is_object() {
        return Err("Tool arguments must be an object.".into());
    }
    let path = workspace_path(root, text(args, "path")?)?;
    match name {
        "file_ops" => match text(args, "operation")? {
            "read" => Ok(ToolResult::ok(
                fs::read_to_string(&path)?,
                json!({"path":path}),
            )),
            "exists" => Ok(ToolResult::ok(
                path.exists().to_string(),
                json!({"path":path,"exists":path.exists()}),
            )),
            "info" => {
                let info = path.metadata()?;
                Ok(ToolResult::ok(
                    serde_json::to_string(
                        &json!({"path":path,"size":info.len(),"is_file":info.is_file(),"is_dir":info.is_dir()}),
                    )?,
                    json!({"path":path,"size":info.len()}),
                ))
            }
            "mkdir" => {
                fs::create_dir_all(&path)?;
                Ok(ToolResult::ok(
                    format!("Created directory: {}", path.display()),
                    json!({"path":path}),
                ))
            }
            "list" => {
                let depth = if args["recursive"].as_bool().unwrap_or(false) {
                    usize::MAX
                } else {
                    1
                };
                let matcher = args["pattern"]
                    .as_str()
                    .map(globset::Glob::new)
                    .transpose()?
                    .map(|glob| glob.compile_matcher());
                let mut entries = Vec::new();
                for entry in walkdir::WalkDir::new(&path)
                    .follow_links(false)
                    .min_depth(1)
                    .max_depth(depth)
                    .sort_by_file_name()
                {
                    let entry = entry?;
                    if matcher
                        .as_ref()
                        .is_some_and(|matcher| !matcher.is_match(entry.file_name()))
                    {
                        continue;
                    }
                    entries.push(json!({"path":entry.path().strip_prefix(&path)?.to_string_lossy(),"directory":entry.file_type().is_dir(),"symlink":entry.file_type().is_symlink()}));
                }
                Ok(ToolResult::ok(
                    serde_json::to_string(&entries)?,
                    json!({"entries":entries}),
                ))
            }
            _ => Err("Unknown file operation.".into()),
        },
        "create_file" => {
            save(
                root,
                &path,
                text(args, "content")?,
                args["overwrite"].as_bool().unwrap_or(false),
                backups,
            )?;
            Ok(ToolResult::ok(
                format!("Created file: {}", path.display()),
                json!({"path":path,"modified":true}),
            ))
        }
        "str_replace_editor" => match text(args, "command")? {
            "view" => {
                let body = fs::read_to_string(&path)?;
                let range = args["view_range"].as_array();
                let start = range
                    .and_then(|r| r.first())
                    .and_then(Value::as_u64)
                    .unwrap_or(1)
                    .max(1);
                let end = range
                    .and_then(|r| r.get(1))
                    .and_then(Value::as_i64)
                    .filter(|end| *end > 0)
                    .map(|end| end as u64)
                    .unwrap_or(u64::MAX);
                let selected = body
                    .lines()
                    .enumerate()
                    .filter(|(i, _)| (*i as u64 + 1) >= start && (*i as u64 + 1) <= end)
                    .map(|(i, line)| format!("{}\t{line}", i + 1))
                    .collect::<Vec<_>>()
                    .join("\n");
                Ok(ToolResult::ok(selected, json!({"path":path})))
            }
            "create" => {
                save(root, &path, text(args, "file_text")?, false, backups)?;
                Ok(ToolResult::ok(
                    format!("Created file: {}", path.display()),
                    json!({"path":path,"modified":true}),
                ))
            }
            "str_replace" => {
                let before = fs::read_to_string(&path)?;
                let old = text(args, "old_str")?;
                if old.is_empty() || before.match_indices(old).count() != 1 {
                    return Err(
                        "Replacement must match exactly once; provide unique surrounding text."
                            .into(),
                    );
                }
                let after = before.replacen(old, text(args, "new_str")?, 1);
                save(root, &path, &after, true, backups)?;
                Ok(ToolResult::ok(
                    format!("Updated file: {}", path.display()),
                    json!({"path":path,"modified":true}),
                ))
            }
            "insert" => {
                let before = fs::read_to_string(&path)?;
                let line = args["insert_line"]
                    .as_u64()
                    .ok_or("insert_line must be a non-negative integer.")?
                    as usize;
                let parts = before.split_inclusive('\n').collect::<Vec<_>>();
                if line > parts.len() {
                    return Err("insert_line is outside the file.".into());
                }
                let offset = parts
                    .iter()
                    .take(line)
                    .map(|line| line.len())
                    .sum::<usize>();
                let newline = if before.contains("\r\n") {
                    "\r\n"
                } else {
                    "\n"
                };
                let inserted = text(args, "new_str")?;
                let separator = if offset > 0 && !before[..offset].ends_with('\n') {
                    newline
                } else {
                    ""
                };
                let ending = if inserted.ends_with('\n') {
                    ""
                } else {
                    newline
                };
                let after = format!(
                    "{}{}{}{}{}",
                    &before[..offset],
                    separator,
                    inserted,
                    ending,
                    &before[offset..]
                );
                save(root, &path, &after, true, backups)?;
                Ok(ToolResult::ok(
                    format!("Inserted text: {}", path.display()),
                    json!({"path":path,"modified":true}),
                ))
            }
            _ => Err("Unknown editor command.".into()),
        },
        _ => Err(format!("Unknown workspace tool: {name}").into()),
    }
}

fn save(root: &Path, path: &Path, content: &str, overwrite: bool, backups: &Path) -> Result<()> {
    let path = workspace_path(
        root,
        path.to_str().ok_or("Workspace path must be Unicode.")?,
    )?;
    let parent = path.parent().ok_or("File path has no parent.")?;
    fs::create_dir_all(parent)?;
    if path.exists() {
        if !overwrite {
            return Err("File already exists; explicit overwrite is required.".into());
        }
        fs::create_dir_all(backups)?;
        let mut backup = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(backups.join(format!("{}.before", uuid::Uuid::new_v4().simple())))?;
        io::copy(&mut fs::File::open(&path)?, &mut backup)?;
        backup.sync_all()?;
    }
    let mut staged = tempfile::NamedTempFile::new_in(parent)?;
    if path.exists() {
        staged
            .as_file()
            .set_permissions(path.metadata()?.permissions())?;
    }
    staged.write_all(content.as_bytes())?;
    staged.as_file().sync_all()?;
    if overwrite {
        staged.persist(path).map_err(|error| error.error)?;
    } else {
        staged
            .persist_noclobber(path)
            .map_err(|error| error.error)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tools_confine_paths_and_preserve_exact_text_on_failed_edits() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("project");
        fs::create_dir_all(&root).unwrap();
        let backups = dir.path().join("backups");
        let before = "unique\r\n中文😀\nrepeat repeat\n";
        assert!(
            execute(
                "create_file",
                &json!({"path":"a.txt","content":before}),
                &root,
                &backups
            )
            .success
        );
        fs::write(root.join("eof.txt"), "last line").unwrap();
        assert!(execute("str_replace_editor", &json!({"command":"insert","path":"eof.txt","insert_line":1,"new_str":"new line\n"}), &root, &backups).success);
        assert_eq!(
            fs::read_to_string(root.join("eof.txt")).unwrap(),
            "last line\nnew line\n"
        );
        assert!(!execute("str_replace_editor",&json!({"command":"str_replace","path":"a.txt","old_str":"repeat","new_str":"broken"}),&root,&backups).success);
        assert_eq!(fs::read_to_string(root.join("a.txt")).unwrap(), before);
        assert!(execute("str_replace_editor",&json!({"command":"str_replace","path":"a.txt","old_str":"unique","new_str":"changed"}),&root,&backups).success);
        let mut originals = fs::read_dir(&backups)
            .unwrap()
            .map(|file| fs::read_to_string(file.unwrap().path()).unwrap())
            .collect::<Vec<_>>();
        originals.sort();
        assert_eq!(originals, ["last line", before]);
        assert!(
            !execute(
                "create_file",
                &json!({"path":"../escape.txt","content":"no"}),
                &root,
                &backups
            )
            .success
        );
        assert!(
            !execute(
                "create_file",
                &json!({"path":"a.txt","content":"no"}),
                &root,
                &backups
            )
            .success
        );
    }
}
