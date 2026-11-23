use crate::{ContextEngine, Evidence, Result, catalog, inference::LocalModels, inspect, semantic};
use serde_json::{Value, json};
use std::collections::BTreeSet;

impl ContextEngine {
    pub fn semantic_status(&self) -> Result<Option<semantic::IndexState>> {
        semantic::status(&self.semantic_path, &self.root)
    }

    pub fn semantic_status_for(&self, digest: &str) -> Result<Option<semantic::IndexState>> {
        semantic::status_for(&self.semantic_path, &self.root, digest)
    }

    pub fn index_semantic(
        &self,
        models: &LocalModels,
        cancelled: &impl Fn() -> bool,
        progress: &impl Fn(usize, usize),
    ) -> Result<Value> {
        let started = std::time::Instant::now();
        let database = self.catalog.connection().unchecked_transaction()?;
        let state = catalog::state(&database)?;
        if state.revision == 0 {
            return Err("Build the structural index before semantic indexing.".into());
        }
        let mut statement=database.prepare("SELECT path,body,content_hash,rowid FROM files WHERE indexed=1 AND body IS NOT NULL ORDER BY path")?;
        let mut rows = statement.query([])?;
        let mut evidence = Vec::new();
        let mut sources = Vec::new();
        while let Some(row) = rows.next()? {
            if cancelled() {
                return Err("Semantic indexing cancelled.".into());
            }
            let path: String = row.get(0)?;
            let body: String = row.get(1)?;
            let hash: String = row.get(2)?;
            let id: i64 = row.get(3)?;
            inspect::verify_file(&self.root, &path, &hash)?;
            sources.push((path.clone(), hash.clone()));
            let lines = body.lines().collect::<Vec<_>>();
            let mut seen = BTreeSet::new();
            let chunks=database.prepare("SELECT start_line,end_line,symbol FROM chunks WHERE file_rowid=?1 ORDER BY CASE WHEN kind='MODULE' THEN 1 ELSE 0 END,start_line,end_line,symbol")?
                .query_map([id],|row|Ok((row.get::<_,u32>(0)?,row.get::<_,u32>(1)?,row.get::<_,String>(2)?)))?.collect::<rusqlite::Result<Vec<_>>>()?;
            for (start, end, symbol) in chunks {
                let end = end.min(start.saturating_add(71)).min(lines.len() as u32);
                if start == 0 || end < start || !seen.insert((start, end)) {
                    continue;
                }
                let content = lines[(start - 1) as usize..end as usize].join("\n");
                if content.trim().is_empty() {
                    continue;
                }
                evidence.push(Evidence {
                    file_path: path.clone(),
                    start_line: start,
                    end_line: end,
                    content,
                    content_hash: hash.clone(),
                    revision: state.revision,
                    symbol: Some(symbol),
                    score: 0.0,
                    sources: vec!["semantic".into()],
                });
            }
        }
        let mut store = semantic::Store::open(&self.semantic_path, &self.root)?;
        let index = store.update(state.revision, &evidence, models, cancelled, progress, &|| {
            let latest = catalog::open_readonly(&self.database_path)?;
            if catalog::state(&latest)?.revision != state.revision {
                return Err("Structural index changed during semantic indexing; retry before activating a generation.".into());
            }
            for (path, hash) in &sources {
                if cancelled() {
                    return Err("Semantic indexing cancelled before activation.".into());
                }
                inspect::verify_file(&self.root, path, hash)?;
            }
            Ok(())
        })?;
        Ok(
            json!({"backend":"rust","index":index,"elapsed_ms":started.elapsed().as_secs_f64()*1000.0,"models":models.status()?}),
        )
    }

    pub fn query_hybrid(
        &self,
        models: &LocalModels,
        input: &str,
        limit: usize,
        estimated_tokens: usize,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Vec<Evidence>> {
        if cancelled() {
            return Err("Hybrid retrieval cancelled.".into());
        }
        if input.trim().is_empty() {
            return Ok(Vec::new());
        }
        let limit = limit.clamp(1, 200);
        let candidates = limit.max(16);
        let vector = models.embed(&[input.to_owned()], true, cancelled)?;
        let store = semantic::Store::open(&self.semantic_path, &self.root)?;
        let semantic = store.query(
            &vector[0],
            &models.bundle.digest,
            (candidates * 4).min(200),
            cancelled,
        )?;
        let database = self.catalog.connection().unchecked_transaction()?;
        let revision = catalog::state(&database)?.revision;
        let lexical =
            self.query_snapshot(&database, input, (candidates * 4).min(200), usize::MAX)?;
        let mut current = Vec::new();
        for mut hit in semantic {
            use rusqlite::OptionalExtension;
            let hash: Option<String> = database
                .query_row(
                    "SELECT content_hash FROM files WHERE path=?1 AND indexed=1",
                    [&hit.file_path],
                    |row| row.get(0),
                )
                .optional()?;
            if hash.as_ref() != Some(&hit.content_hash) {
                continue;
            }
            inspect::verify_file(&self.root, &hit.file_path, &hit.content_hash)?;
            hit.revision = revision;
            current.push(hit);
        }
        let mut fused = semantic::fuse(lexical, current);
        fused.truncate(candidates);
        let documents = fused
            .iter()
            .map(|hit| {
                format!(
                    "{}:{}\n{}\n{}",
                    hit.file_path,
                    hit.start_line,
                    hit.symbol.as_deref().unwrap_or_default(),
                    hit.content
                )
            })
            .collect::<Vec<_>>();
        let reranked = models.rerank(input, &documents, cancelled)?;
        let mut remaining = estimated_tokens;
        let mut results = Vec::new();
        for (index, score) in reranked {
            let mut hit = fused[index].clone();
            let cost = hit.content.chars().count() / 4;
            if cost > remaining {
                continue;
            }
            remaining -= cost;
            hit.score = score as f64;
            hit.sources.push("neural_rerank".into());
            results.push(hit);
            if results.len() >= limit {
                break;
            }
        }
        for hit in &results {
            if cancelled() {
                return Err("Hybrid retrieval cancelled before delivering evidence.".into());
            }
            inspect::verify_file(&self.root, &hit.file_path, &hit.content_hash)?;
        }
        Ok(results)
    }
}
