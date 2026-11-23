use ignore::WalkBuilder;
use ignore::gitignore::GitignoreBuilder;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet};
use std::error::Error;
use std::fs;
use std::path::{Component, Path};
use std::time::{SystemTime, UNIX_EPOCH};

pub type Result<T> = std::result::Result<T, Box<dyn Error + Send + Sync>>;

const EXTENSIONS: &[&str] = &[
    "py", "pyi", "pyw", "js", "jsx", "mjs", "cjs", "ts", "tsx", "c", "h", "cpp", "cc", "cxx",
    "hpp", "hh", "hxx", "cs", "rs", "go", "java", "zig", "html", "htm", "css", "scss", "sass",
    "less", "lua", "gd", "md", "mdx", "rst", "txt", "json", "yaml", "yml", "xml", "toml", "ini",
    "cfg", "conf", "shader", "glsl", "hlsl", "vert", "frag", "tscn", "tres", "tmx", "gltf", "obj",
    "svg",
];

const IGNORE_DIRS: &[&str] = &[
    ".git",
    ".reverie",
    ".kernel",
    ".runtime",
    ".cache",
    ".vite-cache",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "release",
    "target",
    ".mypy_cache",
    ".pytest_cache",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileEntry {
    pub path: String,
    pub size: i64,
    pub modified_ns: i64,
    #[serde(default)]
    pub content_hash: String,
}

#[derive(Debug, Deserialize)]
pub struct ScanOptions {
    pub extensions: Vec<String>,
    pub rules: Vec<String>,
}

pub fn changes(previous: Vec<FileEntry>, current: Vec<FileEntry>) -> (Vec<FileEntry>, Vec<String>) {
    let mut previous: BTreeMap<_, _> = previous
        .into_iter()
        .map(|entry| (entry.path.clone(), entry))
        .collect();
    let changed = current
        .into_iter()
        .filter(|entry| previous.remove(&entry.path).as_ref() != Some(entry))
        .collect();
    (changed, previous.into_keys().collect())
}

pub fn default_options(_root: &Path) -> Result<ScanOptions> {
    let rules: Vec<String> = IGNORE_DIRS.iter().map(|name| format!("{name}/")).collect();
    Ok(ScanOptions {
        extensions: EXTENSIONS
            .iter()
            .map(|extension| (*extension).to_owned())
            .collect(),
        rules,
    })
}

fn unix_nanos(time: SystemTime) -> i64 {
    match time.duration_since(UNIX_EPOCH) {
        Ok(duration) => i64::try_from(duration.as_nanos()).unwrap_or(i64::MAX),
        Err(error) => -i64::try_from(error.duration().as_nanos()).unwrap_or(i64::MAX),
    }
}

pub fn relative_path(path: &Path) -> Result<String> {
    let pieces: Option<Vec<&str>> = path
        .components()
        .map(|component| match component {
            Component::Normal(piece) => piece.to_str(),
            _ => None,
        })
        .collect();
    pieces
        .filter(|pieces| !pieces.is_empty())
        .map(|pieces| pieces.join("/"))
        .ok_or_else(|| format!("Invalid workspace-relative path: {}", path.display()).into())
}

pub fn files(root: &Path, options: &ScanOptions) -> Result<Vec<FileEntry>> {
    files_with_cancel(root, options, &|| false)
}

pub fn files_with_cancel(
    root: &Path,
    options: &ScanOptions,
    cancelled: &impl Fn() -> bool,
) -> Result<Vec<FileEntry>> {
    let walk = walk(root, options)?;
    let extensions: HashSet<&str> = options
        .extensions
        .iter()
        .map(|item| item.trim_start_matches('.'))
        .collect();
    let mut files = Vec::new();
    for item in walk {
        if cancelled() {
            return Err("Context indexing cancelled.".into());
        }
        let entry = item?;
        if !entry.file_type().is_some_and(|kind| kind.is_file()) {
            continue;
        }
        let path = entry.path();
        let ext = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        if !extensions.contains(ext.as_str()) {
            continue;
        }
        let metadata = match entry.metadata() {
            Ok(metadata) => metadata,
            Err(error)
                if error
                    .io_error()
                    .is_some_and(|error| error.kind() == std::io::ErrorKind::NotFound) =>
            {
                continue;
            }
            Err(error) => return Err(error.into()),
        };
        files.push(FileEntry {
            path: relative_path(path.strip_prefix(root)?)?,
            size: metadata.len().try_into()?,
            modified_ns: unix_nanos(metadata.modified()?),
            content_hash: if metadata.len() <= 1024 * 1024 {
                hash_bytes(&fs::read(path)?)
            } else {
                String::new()
            },
        });
    }
    Ok(files)
}

pub fn watch_directories(
    root: &Path,
    cancelled: &impl Fn() -> bool,
) -> Result<Vec<std::path::PathBuf>> {
    let mut directories = Vec::new();
    for entry in walk(root, &default_options(root)?)? {
        if cancelled() {
            return Err("Context directory discovery cancelled.".into());
        }
        let entry = entry?;
        if entry.file_type().is_some_and(|kind| kind.is_dir()) {
            directories.push(entry.into_path());
        }
    }
    Ok(directories)
}

pub fn watch_event_relevant(root: &Path, path: &Path) -> bool {
    let Ok(relative) = path.strip_prefix(root) else {
        return false;
    };
    !relative.components().any(|component| match component {
        Component::Normal(name) => IGNORE_DIRS
            .iter()
            .any(|ignored| name == std::ffi::OsStr::new(ignored)),
        _ => true,
    })
}

fn walk(root: &Path, options: &ScanOptions) -> Result<ignore::Walk> {
    let mut builder = GitignoreBuilder::new(root);
    for rule in &options.rules {
        builder.add_line(None, rule)?;
    }
    let ignore = builder.build()?;
    Ok(WalkBuilder::new(root)
        .follow_links(false)
        .hidden(false)
        .parents(false)
        .git_global(false)
        .require_git(false)
        .add_custom_ignore_filename(".reverieignore")
        .sort_by_file_name(|a, b| a.cmp(b))
        .filter_entry(move |entry| {
            if entry.depth() == 0 {
                return true;
            }
            let is_dir = entry.file_type().is_some_and(|kind| kind.is_dir());
            !ignore
                .matched_path_or_any_parents(entry.path(), is_dir)
                .is_ignore()
        })
        .build())
}

pub fn hash_bytes(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
