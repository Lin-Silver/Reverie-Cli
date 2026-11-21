use ignore::gitignore::GitignoreBuilder;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashSet};
use std::error::Error;
use std::fs;
use std::path::{Component, Path};
use std::time::{SystemTime, UNIX_EPOCH};
use walkdir::WalkDir;

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

pub fn default_options(root: &Path) -> Result<ScanOptions> {
    let mut rules: Vec<String> = IGNORE_DIRS.iter().map(|name| format!("{name}/")).collect();
    for name in [".gitignore", ".reverieignore"] {
        match fs::read_to_string(root.join(name)) {
            Ok(rules_text) => rules.extend(rules_text.lines().map(str::to_owned)),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
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
    let mut builder = GitignoreBuilder::new(root);
    let mut exceptions = Vec::new();
    for rule in &options.rules {
        builder.add_line(None, rule)?;
        if let Some(exception) = rule.trim_start().strip_prefix('!') {
            let prefix = exception
                .trim()
                .trim_matches('/')
                .split(['*', '?'])
                .next()
                .unwrap_or_default()
                .trim_end_matches('/');
            exceptions.push(prefix.to_owned());
        }
    }
    let ignore = builder.build()?;
    let extensions: HashSet<&str> = options
        .extensions
        .iter()
        .map(|item| item.trim_start_matches('.'))
        .collect();
    let walk = WalkDir::new(root)
        .follow_links(false)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|entry| {
            if entry.depth() == 0 {
                return true;
            }
            let is_dir = entry.file_type().is_dir();
            if !ignore
                .matched_path_or_any_parents(entry.path(), is_dir)
                .is_ignore()
            {
                return true;
            }
            // Reverie's ignore rules allow explicitly re-including paths in an ignored directory.
            is_dir
                && entry
                    .path()
                    .strip_prefix(root)
                    .ok()
                    .and_then(|path| relative_path(path).ok())
                    .is_some_and(|path| {
                        exceptions.iter().any(|prefix| {
                            prefix == &path
                                || prefix
                                    .strip_prefix(&path)
                                    .is_some_and(|tail| tail.starts_with('/'))
                        })
                    })
        });
    let mut files = Vec::new();
    for item in walk {
        let entry = item?;
        if !entry.file_type().is_file() {
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
        });
    }
    Ok(files)
}
