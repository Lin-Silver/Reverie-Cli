use crate::{ContextEngine, Evidence, Result, catalog};
use rusqlite::{Connection, Row, params};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    fs::File,
    io::Read,
    path::{Component, Path, PathBuf},
};

#[derive(Debug, Clone, Serialize)]
pub struct Symbol {
    pub qualified_name: String,
    pub name: String,
    pub kind: String,
    pub file_path: String,
    pub start_line: u32,
    pub end_line: u32,
    pub language: String,
    pub signature: String,
    pub documentation: String,
    pub parent: Option<String>,
    pub content_hash: String,
}

impl Symbol {
    fn row(row: &Row<'_>) -> rusqlite::Result<Self> {
        Ok(Self {
            qualified_name: row.get(0)?,
            name: row.get(1)?,
            kind: row.get(2)?,
            file_path: row.get(3)?,
            start_line: row.get(4)?,
            end_line: row.get(5)?,
            language: row.get(6)?,
            signature: row.get(7)?,
            documentation: row.get(8)?,
            parent: row.get(9)?,
            content_hash: row.get(10)?,
        })
    }
}

const SYMBOL_FIELDS: &str = "c.symbol,c.name,c.kind,f.path,c.start_line,c.end_line,c.language,c.signature,c.documentation,c.parent_symbol,f.content_hash";

#[derive(Debug, Serialize)]
pub struct Reference {
    pub from_symbol: String,
    pub target_text: String,
    pub to_symbol: Option<String>,
    pub dep_type: String,
    pub file_path: String,
    pub line: u32,
    pub resolution: String,
    pub content_hash: String,
    pub depth: usize,
}

pub(crate) fn verify_file(root: &Path, path: &str, hash: &str) -> Result<()> {
    let path = root.join(path).canonicalize()?;
    if !path.starts_with(root) {
        return Err("Indexed file now resolves outside its workspace.".into());
    }
    let mut bytes = Vec::new();
    File::open(path)?.take(1_048_577).read_to_end(&mut bytes)?;
    if bytes.len() > 1_048_576 || crate::scan::hash_bytes(&bytes) != hash {
        return Err(
            "Context file changed since indexing; refresh the index before using its evidence."
                .into(),
        );
    }
    Ok(())
}

fn symbols(db: &Connection, query: &str, kind: &str, limit: usize) -> Result<Vec<Symbol>> {
    let pattern = format!(
        "%{}%",
        query
            .replace('\\', "\\\\")
            .replace('_', "\\_")
            .replace('%', "\\%")
    );
    let kind = kind.to_ascii_uppercase();
    let sql = format!(
        "SELECT {SYMBOL_FIELDS} FROM chunks c JOIN files f ON f.rowid=c.file_rowid WHERE (c.kind!='MODULE' OR c.signature!='') AND (c.symbol LIKE ?1 ESCAPE '\\' OR c.name LIKE ?1 ESCAPE '\\') AND (?2='ALL' OR c.kind=?2) ORDER BY CASE WHEN c.symbol=?4 THEN 0 WHEN c.name=?4 THEN 1 ELSE 2 END,c.symbol,f.path,c.start_line,c.rowid LIMIT ?3"
    );
    Ok(db
        .prepare(&sql)?
        .query_map(
            params![pattern, kind, limit.clamp(1, 200) as i64, query],
            Symbol::row,
        )?
        .collect::<rusqlite::Result<Vec<_>>>()?)
}

fn select_symbol(db: &Connection, query: &str) -> Result<Symbol> {
    let found = symbols(db, query, "all", 200)?;
    if let Some(symbol) = found.iter().find(|symbol| symbol.qualified_name == query) {
        let identical = found
            .iter()
            .filter(|candidate| candidate.qualified_name == query)
            .count();
        if identical == 1 {
            return Ok(symbol.clone());
        }
    }
    let exact = found
        .iter()
        .filter(|symbol| {
            symbol.qualified_name == query
                || symbol.name == query
                || symbol.qualified_name.ends_with(&format!(".{query}"))
        })
        .cloned()
        .collect::<Vec<_>>();
    let mut candidates = if exact.is_empty() { found } else { exact };
    if candidates.len() != 1 {
        return Err(format!(
            "Symbol selection is {}. Use a qualified name; candidates: {}",
            if candidates.is_empty() {
                "missing"
            } else {
                "ambiguous"
            },
            candidates
                .iter()
                .map(|symbol| format!(
                    "{} ({}:{})",
                    symbol.qualified_name, symbol.file_path, symbol.start_line
                ))
                .collect::<Vec<_>>()
                .join(", ")
        )
        .into());
    }
    Ok(candidates.remove(0))
}

fn file_path(root: &Path, query: &str) -> Result<String> {
    let input = Path::new(query);
    let relative = if input.is_absolute() {
        input.canonicalize()?.strip_prefix(root)?.to_owned()
    } else {
        input
            .components()
            .try_fold(PathBuf::new(), |mut path, component| {
                match component {
                    Component::CurDir => {}
                    Component::Normal(part) => path.push(part),
                    _ => return Err("Context paths cannot traverse outside their workspace."),
                }
                Ok(path)
            })?
    };
    crate::scan::relative_path(&relative)
}

fn source(
    db: &Connection,
    root: &Path,
    path: &str,
    start: u32,
    end: u32,
    symbol: Option<String>,
) -> Result<Evidence> {
    let (body, hash): (String, String) = db.query_row(
        "SELECT body,content_hash FROM files WHERE path=?1 AND indexed=1",
        [path],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    verify_file(root, path, &hash)?;
    let lines = body.lines().collect::<Vec<_>>();
    let end = end.min(start.saturating_add(71)).min(lines.len() as u32);
    if start == 0 || end < start {
        return Err("The indexed source range is empty or invalid.".into());
    }
    Ok(Evidence {
        file_path: path.into(),
        start_line: start,
        end_line: end,
        content: lines[(start - 1) as usize..end as usize].join("\n"),
        content_hash: hash,
        revision: catalog::state(db)?.revision,
        symbol,
        score: 1.0,
        sources: vec!["structure".into()],
    })
}

fn references(
    db: &Connection,
    symbol: &str,
    direction: &str,
    depth: usize,
    limit: usize,
) -> Result<Vec<Reference>> {
    if !["incoming", "outgoing", "both"].contains(&direction) {
        return Err("Dependency direction must be incoming, outgoing or both.".into());
    }
    let mut result = Vec::new();
    let mut visited = BTreeSet::new();
    let mut seen_rows = BTreeSet::new();
    let mut queue = VecDeque::from([(symbol.to_owned(), 0)]);
    while let Some((current, level)) = queue.pop_front() {
        if level >= depth || !visited.insert(current.clone()) {
            continue;
        }
        let sql = "SELECT r.rowid,r.source_symbol,r.target_text,r.target_symbol,r.kind,f.path,r.line,r.resolution,f.content_hash FROM symbol_references r JOIN files f ON f.rowid=r.file_rowid WHERE (?1!='incoming' AND r.source_symbol=?2) OR (?1!='outgoing' AND r.target_symbol=?2) ORDER BY f.path,r.line,r.rowid";
        for reference in db
            .prepare_cached(sql)?
            .query_map(params![direction, current], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    Reference {
                        from_symbol: row.get(1)?,
                        target_text: row.get(2)?,
                        to_symbol: row.get(3)?,
                        dep_type: row.get(4)?,
                        file_path: row.get(5)?,
                        line: row.get(6)?,
                        resolution: row.get(7)?,
                        content_hash: row.get(8)?,
                        depth: level + 1,
                    },
                ))
            })?
        {
            let (id, reference) = reference?;
            if !seen_rows.insert(id) {
                continue;
            }
            if reference.from_symbol == current {
                if let Some(next) = &reference.to_symbol {
                    queue.push_back((next.clone(), level + 1));
                }
            } else {
                queue.push_back((reference.from_symbol.clone(), level + 1));
            }
            result.push(reference);
            if result.len() >= limit.clamp(1, 200) {
                return Ok(result);
            }
        }
    }
    Ok(result)
}

fn verify_references(db: &Connection, root: &Path, references: &[Reference]) -> Result<()> {
    let mut files = BTreeMap::new();
    let mut targets = BTreeSet::new();
    for reference in references {
        files.insert(reference.file_path.clone(), reference.content_hash.clone());
        if let Some(target) = &reference.to_symbol {
            targets.insert(target);
        }
    }
    let mut statement = db.prepare_cached("SELECT f.path,f.content_hash FROM chunks c JOIN files f ON f.rowid=c.file_rowid WHERE c.symbol=?1")?;
    for target in targets {
        for file in statement.query_map([target], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })? {
            let (path, hash) = file?;
            files.insert(path, hash);
        }
    }
    for (path, hash) in files {
        verify_file(root, &path, &hash)?;
    }
    Ok(())
}

impl ContextEngine {
    pub fn lookup(&self, request: &Value) -> Result<Value> {
        self.lookup_with_hits(request, None)
    }

    pub fn lookup_hybrid(
        &self,
        models: &crate::inference::LocalModels,
        request: &Value,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Value> {
        if !["task", "explore"].contains(&request["query_type"].as_str().unwrap_or_default()) {
            return self.lookup(request);
        }
        let query = request["query"]
            .as_str()
            .ok_or("Context query text is required.")?;
        let limit = request["max_symbols"].as_u64().unwrap_or(12).clamp(1, 200) as usize;
        let budget = request["max_tokens"]
            .as_u64()
            .unwrap_or(12000)
            .try_into()
            .map_err(|_| "Context budget is too large for this platform.")?;
        let hits = self.query_hybrid(models, query, limit, budget, cancelled)?;
        self.lookup_with_hits(request, Some(hits))
    }

    fn lookup_with_hits(&self, request: &Value, supplied: Option<Vec<Evidence>>) -> Result<Value> {
        let kind = request["query_type"]
            .as_str()
            .ok_or("Context query_type is required.")?;
        let query = request["query"]
            .as_str()
            .ok_or("Context query text is required.")?;
        let limit = request["limit"].as_u64().unwrap_or(20).clamp(1, 200) as usize;
        let include_source = request["include_source"].as_bool().unwrap_or(true);
        let max_tokens = request["max_tokens"]
            .as_u64()
            .unwrap_or(12000)
            .try_into()
            .map_err(|_| "Context token budget is too large for this platform.")?;
        if kind == "task" || kind == "explore" {
            let max_files = request["max_files"].as_u64().unwrap_or(6).clamp(1, 200) as usize;
            let max_symbols = request["max_symbols"].as_u64().unwrap_or(12).clamp(1, 200) as usize;
            let hybrid = supplied.is_some();
            let mut hits = match supplied {
                Some(hits) => hits,
                None => self.query(query, 200, max_tokens)?,
            };
            let preferred = request["active_files"]
                .as_array()
                .into_iter()
                .flatten()
                .chain(request["changed_files"].as_array().into_iter().flatten())
                .filter_map(Value::as_str)
                .map(|path| file_path(&self.root, path))
                .collect::<Result<BTreeSet<_>>>()?;
            hits.sort_by(|left, right| {
                preferred
                    .contains(&right.file_path)
                    .cmp(&preferred.contains(&left.file_path))
                    .then_with(|| right.score.total_cmp(&left.score))
                    .then_with(|| left.file_path.cmp(&right.file_path))
                    .then_with(|| left.start_line.cmp(&right.start_line))
            });
            let mut files = BTreeSet::new();
            hits.retain(|hit| {
                files.contains(&hit.file_path)
                    || files.len() < max_files && files.insert(hit.file_path.clone())
            });
            hits.truncate(max_symbols);
            files = hits.iter().map(|hit| hit.file_path.clone()).collect();
            let used = hits
                .iter()
                .map(|hit| hit.content.chars().count() / 4)
                .sum::<usize>();
            let revision = hits
                .first()
                .map(|hit| hit.revision)
                .unwrap_or(catalog::state(self.catalog.connection())?.revision);
            if !include_source {
                hits.clear();
            }
            return Ok(
                json!({"query_type":kind,"query":query,"revision":revision,"files":files,"evidence":hits,"estimated_tokens":used,"max_tokens":max_tokens,"budget_algorithm":"unicode_scalar_count_div_4_floor","components":{"lexical":true,"structure":true,"semantic":hybrid,"neural_rerank":hybrid,"history":false,"memory":false},"unavailable_components":if hybrid{vec!["history","memory"]}else{vec!["semantic","history","memory"]}}),
            );
        }
        let db = self.catalog.connection().unchecked_transaction()?;
        let revision = catalog::state(&db)?.revision;
        if revision == 0 {
            return Err("Context Engine must be indexed before lookup.".into());
        }
        let mut evidence = Vec::new();
        let mut output = match kind {
            "search" => {
                let symbols = symbols(
                    &db,
                    if query == "*" { "" } else { query },
                    request["filter_kind"].as_str().unwrap_or("all"),
                    limit,
                )?;
                for symbol in &symbols {
                    verify_file(&self.root, &symbol.file_path, &symbol.content_hash)?;
                }
                json!({"symbols":symbols})
            }
            "symbol" => {
                let symbol = select_symbol(&db, query)?;
                verify_file(&self.root, &symbol.file_path, &symbol.content_hash)?;
                let parent = if let Some(parent) = &symbol.parent {
                    symbols(&db, parent, "all", 200)?
                        .into_iter()
                        .find(|symbol| symbol.qualified_name == *parent)
                } else {
                    None
                };
                let sql = format!(
                    "SELECT {SYMBOL_FIELDS} FROM chunks c JOIN files f ON f.rowid=c.file_rowid WHERE c.parent_symbol=?1 ORDER BY f.path,c.start_line,c.rowid LIMIT ?2"
                );
                let children = db
                    .prepare(&sql)?
                    .query_map(params![symbol.qualified_name, limit as i64], Symbol::row)?
                    .collect::<rusqlite::Result<Vec<_>>>()?;
                if include_source {
                    evidence.push(source(
                        &db,
                        &self.root,
                        &symbol.file_path,
                        symbol.start_line,
                        symbol.end_line,
                        Some(symbol.qualified_name.clone()),
                    )?);
                }
                let dependencies = if request["include_dependencies"].as_bool().unwrap_or(true) {
                    references(
                        &db,
                        &symbol.qualified_name,
                        "both",
                        request["max_depth"].as_u64().unwrap_or(2) as usize,
                        limit,
                    )?
                } else {
                    Vec::new()
                };
                verify_references(&db, &self.root, &dependencies)?;
                json!({"symbol":symbol,"parent":parent,"children":children,"references":dependencies})
            }
            "file" | "outline" => {
                let path = file_path(&self.root, query)?;
                let sql = format!(
                    "SELECT {SYMBOL_FIELDS} FROM chunks c JOIN files f ON f.rowid=c.file_rowid WHERE f.path=?1 AND (c.kind!='MODULE' OR c.signature!='') ORDER BY c.start_line,c.rowid LIMIT ?2"
                );
                let symbols = db
                    .prepare(&sql)?
                    .query_map(params![path, limit as i64], Symbol::row)?
                    .collect::<rusqlite::Result<Vec<_>>>()?;
                let hash: String = db.query_row(
                    "SELECT content_hash FROM files WHERE path=?1",
                    [&path],
                    |row| row.get(0),
                )?;
                verify_file(&self.root, &path, &hash)?;
                if kind == "file" && include_source {
                    evidence.push(source(&db, &self.root, &path, 1, 72, None)?);
                }
                json!({"file":path,"content_hash":hash,"symbols":symbols})
            }
            "dependencies" => {
                let symbol = select_symbol(&db, query)?;
                verify_file(&self.root, &symbol.file_path, &symbol.content_hash)?;
                let references = references(
                    &db,
                    &symbol.qualified_name,
                    request["direction"].as_str().unwrap_or("outgoing"),
                    request["max_depth"].as_u64().unwrap_or(2) as usize,
                    limit,
                )?;
                verify_references(&db, &self.root, &references)?;
                json!({"symbol":symbol,"references":references,"resolution_contract":"Static lexical matches and explicitly marked unique-name inference; unresolved and ambiguous targets are retained."})
            }
            _ => {
                return Err(format!("Context query type has not yet been migrated: {kind}").into());
            }
        };
        let mut remaining = max_tokens;
        evidence.retain(|hit| {
            let cost = hit.content.chars().count() / 4;
            if cost > remaining {
                false
            } else {
                remaining -= cost;
                true
            }
        });
        output["evidence"] = json!(evidence);
        output["query_type"] = json!(kind);
        output["revision"] = json!(revision);
        output["estimated_tokens"] = json!(max_tokens - remaining);
        output["limit"] = json!(limit);
        output["limit_reached"] = json!(
            output["symbols"]
                .as_array()
                .is_some_and(|items| items.len() == limit)
                || output["references"]
                    .as_array()
                    .is_some_and(|items| items.len() == limit)
        );
        Ok(output)
    }
}
