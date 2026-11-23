#![forbid(unsafe_code)]

mod catalog;
mod parsing;
pub mod scan;
pub mod search;
mod text;

use catalog::Catalog;
pub use scan::Result;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    time::Instant,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Evidence {
    pub file_path: String,
    pub start_line: u32,
    pub end_line: u32,
    pub content: String,
    pub content_hash: String,
    pub revision: i64,
    pub symbol: Option<String>,
    pub score: f64,
    pub sources: Vec<String>,
}

pub struct ContextEngine {
    root: PathBuf,
    catalog: Catalog,
    parsers: parsing::Parsers,
}

impl ContextEngine {
    pub fn from_database(database: &Path) -> Result<Self> {
        let db = catalog::open_readonly(database)?;
        let state = catalog::state(&db)?;
        if state.root.is_empty() {
            return Err("Context database has no indexed workspace.".into());
        }
        Self::open(Path::new(&state.root), database)
    }

    pub fn open(root: &Path, database: &Path) -> Result<Self> {
        let root = root.canonicalize()?;
        if !root.is_dir() {
            return Err("Workspace must be a directory.".into());
        }
        let catalog = Catalog::open(database)?;
        let state = catalog::state(catalog.connection())?;
        if !state.root.is_empty() && state.root != root.to_string_lossy() {
            return Err("Context database belongs to another workspace.".into());
        }
        Ok(Self {
            root,
            catalog,
            parsers: parsing::Parsers::default(),
        })
    }

    pub fn status(&self) -> Result<Value> {
        let db = self.catalog.connection();
        let state = catalog::state(db)?;
        let files: i64 = db.query_row("SELECT count(*) FROM files", [], |row| row.get(0))?;
        let symbols: i64 = db.query_row(
            "SELECT count(*) FROM chunks WHERE kind!='MODULE'",
            [],
            |row| row.get(0),
        )?;
        Ok(
            json!({"ready":state.revision>0,"indexing":false,"files":files,"symbols":symbols,"backend":"rust","revision":state.revision,"progress":if state.revision>0{100}else{0},"label":if state.revision>0{"Ready"}else{"Not indexed"},"automatic_retrieval":true,"available":true,"semantic":{"available":false,"status":"resource_not_installed"}}),
        )
    }

    pub fn index(&mut self, rebuild: bool) -> Result<Value> {
        self.index_with_cancel(rebuild, &|| false)
    }

    pub fn index_with_cancel(
        &mut self,
        rebuild: bool,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Value> {
        let started = Instant::now();
        let candidates =
            scan::files_with_cancel(&self.root, &scan::default_options(&self.root)?, cancelled)?;
        let scanned = candidates.len();
        let state = catalog::state(self.catalog.connection())?;
        let (changed, removed) = if rebuild {
            (candidates, Vec::new())
        } else {
            scan::changes(catalog::files(self.catalog.connection())?, candidates)
        };
        let mut indexed = 0;
        let mut skipped = 0;
        let mut revision = state.revision;
        if !changed.is_empty() || !removed.is_empty() || revision == 0 || rebuild {
            self.catalog.begin(
                self.root
                    .to_str()
                    .ok_or("Workspace path must be Unicode.")?,
                rebuild,
                revision,
            )?;
            let update = (|| {
                self.catalog.apply(&removed, &[])?;
                for file in changed {
                    if cancelled() {
                        return Err("Context indexing cancelled.".into());
                    }
                    let document = self.parsers.document(&self.root, file)?;
                    if document.body.is_some() {
                        indexed += 1;
                    } else {
                        skipped += 1;
                    }
                    self.catalog.apply(&[], &[document])?;
                }
                if cancelled() {
                    return Err("Context indexing cancelled.".into());
                }
                Ok::<_, Box<dyn std::error::Error + Send + Sync>>(self.catalog.commit()?.revision)
            })();
            match update {
                Ok(value) => revision = value,
                Err(error) => {
                    self.catalog.rollback()?;
                    return Err(error);
                }
            }
        }
        Ok(
            json!({"backend":"rust","revision":revision,"scanned":scanned,"indexed":indexed,"skipped":skipped,"removed":removed.len(),"elapsed_ms":started.elapsed().as_secs_f64()*1000.0}),
        )
    }

    pub fn paths(&self, prefix: &str, limit: u32) -> Result<Vec<String>> {
        Ok(search::paths(
            self.catalog.connection(),
            prefix,
            limit.clamp(1, 200),
        )?)
    }

    pub fn query(
        &self,
        input: &str,
        limit: usize,
        estimated_tokens: usize,
    ) -> Result<Vec<Evidence>> {
        let input = input.trim();
        if input.is_empty() {
            return Ok(Vec::new());
        }
        let db = self.catalog.connection().unchecked_transaction()?;
        let state = catalog::state(&db)?;
        if state.revision == 0 {
            return Err("Context Engine is not indexed. Run index first.".into());
        }
        let weights: Vec<(String, f64)> = input
            .split_whitespace()
            .map(|word| (word.to_owned(), 1.0))
            .collect();
        let mut hits = search::ranked(&db, &weights, limit.clamp(1, 200) * 3, true)?;
        hits.extend(search::literal(&db, input, limit.clamp(1, 200) * 3)?);
        hits.sort_by(|left, right| {
            right
                .score
                .total_cmp(&left.score)
                .then_with(|| left.file_path.cmp(&right.file_path))
                .then_with(|| left.start_line.cmp(&right.start_line))
        });
        let mut evidence = Vec::new();
        let mut remaining = estimated_tokens;
        for hit in hits {
            let (body, hash): (String, String) = db.query_row(
                "SELECT body,content_hash FROM files WHERE path=? AND indexed=1",
                [&hit.file_path],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )?;
            let bytes = std::fs::read(self.root.join(&hit.file_path))?;
            if scan::hash_bytes(&bytes) != hash {
                return Err(
                    format!("Context file changed since indexing: {}", hit.file_path).into(),
                );
            }
            let start = hit.start_line.unwrap_or(1);
            let lines: Vec<&str> = body.lines().collect();
            let end = hit
                .end_line
                .unwrap_or(start + 71)
                .min(start.saturating_add(71))
                .min(lines.len() as u32);
            if start == 0 || end < start {
                continue;
            }
            let content = lines[(start - 1) as usize..end as usize].join("\n");
            if evidence.iter().any(|previous: &Evidence| {
                previous.file_path == hit.file_path
                    && previous.start_line == start
                    && previous.end_line == end
            }) {
                continue;
            }
            let cost = content.chars().count() / 4;
            if cost > remaining {
                continue;
            }
            remaining -= cost;
            evidence.push(Evidence {
                file_path: hit.file_path,
                start_line: start,
                end_line: end,
                content,
                content_hash: hash,
                revision: state.revision,
                symbol: hit.symbol,
                score: hit.score,
                sources: vec!["lexical".into()],
            });
            if evidence.len() >= limit.clamp(1, 200) {
                break;
            }
        }
        Ok(evidence)
    }
}

pub fn database_status(database: &Path) -> Result<Value> {
    let db = catalog::open_readonly(database)?;
    let state = catalog::state(&db)?;
    Ok(
        json!({"backend":"rust","root":state.root,"revision":state.revision,"ready":state.revision>0,"files":db.query_row("SELECT count(*) FROM files",[],|row|row.get::<_,i64>(0))?,"symbols":db.query_row("SELECT count(*) FROM chunks WHERE kind!='MODULE'",[],|row|row.get::<_,i64>(0))?}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn directory() -> tempfile::TempDir {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/context-tests");
        fs::create_dir_all(&root).unwrap();
        tempfile::tempdir_in(root).unwrap()
    }

    #[test]
    fn cancelled_incremental_update_rolls_back_partial_catalog_changes() {
        let dir = directory();
        let project = dir.path().join("project");
        fs::create_dir_all(&project).unwrap();
        fs::write(project.join("a.txt"), "original a").unwrap();
        fs::write(project.join("b.txt"), "original b").unwrap();
        let database = dir.path().join("context.sqlite3");
        let mut engine = ContextEngine::open(&project, &database).unwrap();
        let revision = engine.index(false).unwrap()["revision"].clone();
        fs::write(project.join("a.txt"), "changed a").unwrap();
        fs::write(project.join("b.txt"), "changed b").unwrap();
        let checks = std::cell::Cell::new(0);
        assert!(
            engine
                .index_with_cancel(false, &|| {
                    checks.set(checks.get() + 1);
                    checks.get() >= 5
                })
                .is_err()
        );
        assert_eq!(engine.status().unwrap()["revision"], revision);
        fs::write(project.join("a.txt"), "original a").unwrap();
        fs::write(project.join("b.txt"), "original b").unwrap();
        assert_eq!(
            engine.query("original a", 10, 12000).unwrap()[0].content,
            "original a"
        );
        drop(engine);
        let mut engine = ContextEngine::open(&project, &database).unwrap();
        fs::write(project.join("b.txt"), "successful retry").unwrap();
        assert!(
            engine.index(false).unwrap()["revision"].as_i64().unwrap() > revision.as_i64().unwrap()
        );
        assert_eq!(
            engine.query("successful retry", 10, 12000).unwrap()[0].content,
            "successful retry"
        );
    }

    #[test]
    fn persists_evidence_and_updates_changed_renamed_deleted_and_stale_files() {
        let dir = directory();
        let project = dir.path().join("project");
        fs::create_dir_all(&project).unwrap();
        fs::write(
            project.join("logic.rs"),
            "pub fn save_game() {\n    println!(\"quest_marker\");\n}\n",
        )
        .unwrap();
        let narrative = (0..130)
            .map(|line| {
                if line == 92 {
                    "飞船失去动力，必须修复燃料阀门。".into()
                } else {
                    format!("narrative line {line}")
                }
            })
            .collect::<Vec<_>>()
            .join("\n");
        fs::write(project.join("chapter.txt"), narrative).unwrap();
        let database = dir.path().join("index.sqlite3");
        let mut engine = ContextEngine::open(&project, &database).unwrap();
        assert_eq!(engine.index(false).unwrap()["scanned"], 2);
        let query = engine.query("save_game", 10, 12000).unwrap();
        assert!(!query.is_empty());
        assert!(query[0].content.contains("save_game"));
        let query = engine.query("飞船失去动力", 10, 12000).unwrap();
        assert!(!query.is_empty());
        assert!(query.iter().any(|hit| hit.content.contains("飞船失去动力")));
        assert!(query.iter().all(|hit| hit.end_line - hit.start_line < 72));
        let revision = engine.status().unwrap()["revision"].clone();
        drop(engine);
        let mut engine = ContextEngine::open(&project, &database).unwrap();
        assert_eq!(engine.index(false).unwrap()["indexed"], 0);
        assert_eq!(engine.status().unwrap()["revision"], revision);
        fs::write(
            project.join("logic.rs"),
            "pub fn save_game() { println!(\"changed_game\"); }",
        )
        .unwrap();
        assert!(engine.query("save_game", 10, 12000).is_err());
        assert_eq!(engine.index(false).unwrap()["indexed"], 1);
        assert!(
            engine.query("changed_game", 10, 12000).unwrap()[0]
                .content
                .contains("changed_game")
        );
        fs::rename(project.join("logic.rs"), project.join("renamed.rs")).unwrap();
        assert_eq!(engine.index(false).unwrap()["removed"], 1);
        assert_eq!(engine.paths("logic", 10).unwrap().len(), 0);
        assert_eq!(engine.paths("renamed", 10).unwrap().len(), 1);
        fs::remove_file(project.join("renamed.rs")).unwrap();
        assert_eq!(engine.index(false).unwrap()["removed"], 1);
        assert!(engine.query("save_game", 10, 12000).unwrap().is_empty());
        assert!(engine.query("飞船失去动力", 10, 0).unwrap().is_empty());
    }

    #[test]
    fn git_parent_exclusion_and_nested_negation_follow_git_directory_semantics() {
        let dir = directory();
        for path in ["ignored", "nested"] {
            fs::create_dir_all(dir.path().join(path)).unwrap();
        }
        fs::write(dir.path().join("ignored/keep.rs"), "pub fn inside() {}\n").unwrap();
        fs::write(dir.path().join("nested/keep.rs"), "pub fn kept() {}\n").unwrap();
        fs::write(
            dir.path().join("nested/remove.rs"),
            "pub fn excluded() {}\n",
        )
        .unwrap();
        fs::write(
            dir.path().join(".gitignore"),
            "ignored/\n!ignored/keep.rs\n*.rs\n",
        )
        .unwrap();
        fs::write(dir.path().join("nested/.gitignore"), "!keep.rs\n").unwrap();
        let paths = scan::files(dir.path(), &scan::default_options(dir.path()).unwrap())
            .unwrap()
            .into_iter()
            .map(|file| file.path)
            .collect::<Vec<_>>();
        assert_eq!(paths, vec!["nested/keep.rs"]);
        fs::write(
            dir.path().join(".gitignore"),
            "ignored/*\n!ignored/\n!ignored/keep.rs\n*.rs\n!ignored/keep.rs\n",
        )
        .unwrap();
        let paths = scan::files(dir.path(), &scan::default_options(dir.path()).unwrap())
            .unwrap()
            .into_iter()
            .map(|file| file.path)
            .collect::<Vec<_>>();
        assert_eq!(paths, vec!["ignored/keep.rs", "nested/keep.rs"]);
    }
}
