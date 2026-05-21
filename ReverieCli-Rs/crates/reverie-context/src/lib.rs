use ignore::WalkBuilder;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::time::Instant;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ContextError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("regex error: {0}")]
    Regex(#[from] regex::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

pub type ContextResult<T> = Result<T, ContextError>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SymbolRecord {
    pub name: String,
    pub kind: String,
    pub file: PathBuf,
    pub line: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DependencyRecord {
    pub source: PathBuf,
    pub target: String,
    pub kind: String,
    pub line: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchMatchRecord {
    pub file: PathBuf,
    pub line: usize,
    pub snippet: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexResult {
    pub success: bool,
    pub files_scanned: usize,
    pub files_parsed: usize,
    pub files_skipped: usize,
    pub files_failed: usize,
    pub symbols_extracted: usize,
    pub dependencies_extracted: usize,
    pub total_time_ms: f64,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
    pub symbols: Vec<SymbolRecord>,
    #[serde(default)]
    pub dependencies: Vec<DependencyRecord>,
}

pub struct CodebaseIndexer {
    root: PathBuf,
    cache_dir: Option<PathBuf>,
}

impl CodebaseIndexer {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
            cache_dir: None,
        }
    }

    pub fn with_cache_dir(mut self, cache_dir: impl AsRef<Path>) -> Self {
        self.cache_dir = Some(cache_dir.as_ref().to_path_buf());
        self
    }

    pub fn full_index(&self) -> ContextResult<IndexResult> {
        let started = Instant::now();
        let symbol_re = Regex::new(
            r"^\s*(?:pub\s+)?(?:async\s+)?(?:local\s+)?(?:fn|func|class|def|struct|enum|trait|impl|function)\s+([A-Za-z_][A-Za-z0-9_]*)",
        )?;
        let config_key_re = Regex::new(r#"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*[:=]"#)?;
        let markdown_heading_re = Regex::new(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")?;
        let dep_re = Regex::new(
            r#"^\s*(?:use|import|from|require|mod|extends|class_name)\s+["']?(.+?)["']?[;]?\s*$"#,
        )?;
        let mut files_scanned = 0;
        let mut files_parsed = 0;
        let mut files_skipped = 0;
        let mut files_failed = 0;
        let mut dependencies_extracted = 0;
        let mut warnings = Vec::new();
        let mut errors = Vec::new();
        let mut symbols = Vec::new();
        let mut dependencies = Vec::new();

        for entry in WalkBuilder::new(&self.root)
            .hidden(false)
            .git_ignore(true)
            .git_exclude(true)
            .build()
        {
            let entry = match entry {
                Ok(entry) => entry,
                Err(err) => {
                    warnings.push(err.to_string());
                    continue;
                }
            };
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            files_scanned += 1;
            if !is_indexable(path) {
                files_skipped += 1;
                continue;
            }
            let text = match std::fs::read_to_string(path) {
                Ok(text) => text,
                Err(err) => {
                    files_failed += 1;
                    errors.push(format!("{}: {err}", path.display()));
                    continue;
                }
            };
            files_parsed += 1;
            for (idx, line) in text.lines().enumerate() {
                if let Some(captures) = symbol_re.captures(line) {
                    symbols.push(SymbolRecord {
                        name: captures
                            .get(1)
                            .map(|m| m.as_str().to_string())
                            .unwrap_or_default(),
                        kind: infer_symbol_kind(line),
                        file: path.strip_prefix(&self.root).unwrap_or(path).to_path_buf(),
                        line: idx + 1,
                    });
                } else if is_config_like(path) {
                    if let Some(captures) = config_key_re.captures(line) {
                        symbols.push(SymbolRecord {
                            name: captures
                                .get(1)
                                .map(|m| m.as_str().to_string())
                                .unwrap_or_default(),
                            kind: "config-key".to_string(),
                            file: path.strip_prefix(&self.root).unwrap_or(path).to_path_buf(),
                            line: idx + 1,
                        });
                    }
                } else if is_markdown(path) {
                    if let Some(captures) = markdown_heading_re.captures(line) {
                        symbols.push(SymbolRecord {
                            name: captures
                                .get(1)
                                .map(|m| m.as_str().trim().to_string())
                                .unwrap_or_default(),
                            kind: "heading".to_string(),
                            file: path.strip_prefix(&self.root).unwrap_or(path).to_path_buf(),
                            line: idx + 1,
                        });
                    }
                }
                if let Some(captures) = dep_re.captures(line) {
                    dependencies_extracted += 1;
                    dependencies.push(DependencyRecord {
                        source: path.strip_prefix(&self.root).unwrap_or(path).to_path_buf(),
                        target: captures
                            .get(1)
                            .map(|m| m.as_str().trim().to_string())
                            .unwrap_or_default(),
                        kind: infer_dependency_kind(line),
                        line: idx + 1,
                    });
                }
            }
        }

        let result = IndexResult {
            success: files_failed == 0,
            files_scanned,
            files_parsed,
            files_skipped,
            files_failed,
            symbols_extracted: symbols.len(),
            dependencies_extracted,
            total_time_ms: started.elapsed().as_secs_f64() * 1000.0,
            warnings,
            errors,
            symbols,
            dependencies,
        };
        if let Some(cache_dir) = &self.cache_dir {
            std::fs::create_dir_all(cache_dir)?;
            let payload = serde_json::to_string_pretty(&result)?;
            std::fs::write(cache_dir.join("index.json"), payload)?;
        }
        Ok(result)
    }

    pub fn load_cached_index(&self) -> ContextResult<Option<IndexResult>> {
        let Some(cache_dir) = &self.cache_dir else {
            return Ok(None);
        };
        let path = cache_dir.join("index.json");
        if !path.is_file() {
            return Ok(None);
        }
        let text = std::fs::read_to_string(path)?;
        Ok(Some(serde_json::from_str(&text)?))
    }

    pub fn query(&self, query: ContextQuery) -> ContextResult<ContextQueryResult> {
        let index = match self.load_cached_index()? {
            Some(index) => index,
            None => self.full_index()?,
        };
        let needle = query.query.to_ascii_lowercase();
        let symbols = index
            .symbols
            .iter()
            .filter(|symbol| {
                needle.is_empty()
                    || symbol.name.to_ascii_lowercase().contains(&needle)
                    || symbol
                        .file
                        .to_string_lossy()
                        .to_ascii_lowercase()
                        .contains(&needle)
            })
            .take(query.limit.unwrap_or(50))
            .cloned()
            .collect::<Vec<_>>();
        let matches = if query.query_type == "search" && !needle.is_empty() {
            self.search_text_matches(&needle, query.limit.unwrap_or(50))?
        } else {
            Vec::new()
        };
        Ok(ContextQueryResult {
            query,
            symbols,
            matches,
            index_summary: IndexSummary::from(&index),
        })
    }

    fn search_text_matches(
        &self,
        lowercase_needle: &str,
        limit: usize,
    ) -> ContextResult<Vec<SearchMatchRecord>> {
        let mut matches = Vec::new();
        for entry in WalkBuilder::new(&self.root)
            .hidden(false)
            .git_ignore(true)
            .git_exclude(true)
            .build()
        {
            let entry = match entry {
                Ok(entry) => entry,
                Err(_) => continue,
            };
            let path = entry.path();
            if !path.is_file() || !is_indexable(path) {
                continue;
            }
            let Ok(text) = std::fs::read_to_string(path) else {
                continue;
            };
            for (idx, line) in text.lines().enumerate() {
                if line.to_ascii_lowercase().contains(lowercase_needle) {
                    matches.push(SearchMatchRecord {
                        file: path.strip_prefix(&self.root).unwrap_or(path).to_path_buf(),
                        line: idx + 1,
                        snippet: line.trim().chars().take(240).collect(),
                    });
                    if matches.len() >= limit {
                        return Ok(matches);
                    }
                }
            }
        }
        Ok(matches)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextQuery {
    pub query_type: String,
    pub query: String,
    pub limit: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextQueryResult {
    pub query: ContextQuery,
    pub symbols: Vec<SymbolRecord>,
    #[serde(default)]
    pub matches: Vec<SearchMatchRecord>,
    pub index_summary: IndexSummary,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexSummary {
    pub files_scanned: usize,
    pub files_parsed: usize,
    pub symbols_extracted: usize,
    pub dependencies_extracted: usize,
}

impl From<&IndexResult> for IndexSummary {
    fn from(value: &IndexResult) -> Self {
        Self {
            files_scanned: value.files_scanned,
            files_parsed: value.files_parsed,
            symbols_extracted: value.symbols_extracted,
            dependencies_extracted: value.dependencies_extracted,
        }
    }
}

fn is_indexable(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|ext| ext.to_str())
            .unwrap_or_default(),
        "rs" | "py"
            | "js"
            | "ts"
            | "tsx"
            | "jsx"
            | "cs"
            | "go"
            | "java"
            | "lua"
            | "gd"
            | "json"
            | "toml"
            | "yaml"
            | "yml"
            | "md"
    )
}

fn is_config_like(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|ext| ext.to_str())
            .unwrap_or_default(),
        "json" | "toml" | "yaml" | "yml"
    )
}

fn is_markdown(path: &Path) -> bool {
    path.extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| ext.eq_ignore_ascii_case("md"))
        .unwrap_or(false)
}

fn infer_symbol_kind(line: &str) -> String {
    for kind in [
        "class", "struct", "enum", "trait", "impl", "func", "fn", "def", "function",
    ] {
        if line.contains(kind) {
            return kind.to_string();
        }
    }
    "symbol".to_string()
}

fn infer_dependency_kind(line: &str) -> String {
    let trimmed = line.trim_start();
    trimmed
        .split_whitespace()
        .next()
        .unwrap_or("dependency")
        .trim_end_matches(':')
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn indexes_rust_symbol() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("lib.rs"),
            "pub fn hello() {}\nuse std::fs;\n",
        )
        .unwrap();
        let result = CodebaseIndexer::new(dir.path()).full_index().unwrap();
        assert_eq!(result.files_parsed, 1);
        assert_eq!(result.symbols_extracted, 1);
        assert_eq!(result.dependencies_extracted, 1);
        assert_eq!(result.dependencies[0].target, "std::fs");
    }

    #[test]
    fn indexes_lua_gdscript_markdown_and_search_matches() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("script.lua"),
            "local function build_world()\nend\n",
        )
        .unwrap();
        std::fs::write(
            dir.path().join("player.gd"),
            "extends Node\nfunc move_player():\n    pass\n",
        )
        .unwrap();
        std::fs::write(dir.path().join("README.md"), "# Project Lore\n").unwrap();
        let indexer = CodebaseIndexer::new(dir.path());
        let result = indexer.full_index().unwrap();
        assert!(result
            .symbols
            .iter()
            .any(|symbol| symbol.name == "build_world"));
        assert!(result
            .symbols
            .iter()
            .any(|symbol| symbol.name == "move_player"));
        assert!(result
            .symbols
            .iter()
            .any(|symbol| symbol.name == "Project Lore"));
        assert!(result.dependencies.iter().any(|dep| dep.target == "Node"));
        let query = indexer
            .query(ContextQuery {
                query_type: "search".to_string(),
                query: "lore".to_string(),
                limit: Some(5),
            })
            .unwrap();
        assert_eq!(query.matches[0].file, PathBuf::from("README.md"));
    }
}
