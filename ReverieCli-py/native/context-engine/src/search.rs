use rusqlite::{Connection, Row, params};
use serde::Serialize;
use std::collections::{BTreeMap, HashMap};

const CONTENT_QUERY: &str = "SELECT f.rowid,f.path,NULL,NULL,NULL,NULL,\
    bm25(content_search,1.0,0.35) AS relevance \
    FROM content_search JOIN files f ON f.rowid=content_search.rowid \
    WHERE content_search MATCH ?1 ORDER BY relevance,f.path COLLATE NOCASE,f.rowid LIMIT ?2";

const CHUNK_QUERY: &str = "SELECT c.rowid,f.path,c.symbol,c.kind,c.start_line,c.end_line,\
    bm25(chunk_search,5.5,3.0,1.8,1.0,0.6) AS relevance \
    FROM chunk_search JOIN chunks c ON c.rowid=chunk_search.rowid JOIN files f ON f.rowid=c.file_rowid \
    WHERE chunk_search MATCH ?1 ORDER BY relevance,f.path COLLATE NOCASE,c.start_line,c.symbol COLLATE NOCASE,c.rowid LIMIT ?2";

#[derive(Serialize)]
pub struct Hit {
    file_path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    symbol: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    start_line: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    end_line: Option<u32>,
    score: f64,
    terms: Vec<String>,
}

impl Hit {
    fn from_row(row: &Row<'_>) -> rusqlite::Result<Self> {
        Ok(Self {
            file_path: row.get(1)?,
            symbol: row.get(2)?,
            kind: row.get(3)?,
            start_line: row.get(4)?,
            end_line: row.get(5)?,
            score: 0.0,
            terms: Vec::new(),
        })
    }
}

fn phrase(term: &str) -> String {
    format!("\"{}\"", term.replace('"', "\"\""))
}

fn normalize(weights: &[(String, f64)], cap: usize) -> Vec<(String, f64)> {
    let mut max_weights = HashMap::new();
    for (term, weight) in weights {
        let term = term.trim().to_lowercase();
        if !term.is_empty() && weight.is_finite() {
            let value = max_weights.entry(term).or_insert(0.0_f64);
            *value = value.max(*weight);
        }
    }
    let mut normalized: Vec<_> = max_weights.into_iter().collect();
    normalized.sort_unstable_by(|left, right| {
        right
            .1
            .total_cmp(&left.1)
            .then_with(|| left.0.cmp(&right.0))
    });
    normalized.truncate(cap);
    normalized
}

pub fn ranked(
    db: &Connection,
    weights: &[(String, f64)],
    limit: usize,
    chunks: bool,
) -> rusqlite::Result<Vec<Hit>> {
    let (sql, cap, min_rows, max_rows) = if chunks {
        (CHUNK_QUERY, 18, 32, 120)
    } else {
        (CONTENT_QUERY, 16, 24, 96)
    };
    let mut statement = db.prepare_cached(sql)?;
    let mut matches: HashMap<i64, (Hit, Vec<(String, f64)>)> = HashMap::new();
    for (term, weight) in normalize(weights, cap) {
        let mut rows = statement.query(params![
            phrase(&term),
            limit.saturating_mul(2).clamp(min_rows, max_rows) as i64
        ])?;
        let mut rank = 0;
        while let Some(row) = rows.next()? {
            rank += 1;
            let rowid: i64 = row.get(0)?;
            let relevance: f64 = row.get(6)?;
            let mut score = weight * (-relevance).max(0.0).ln_1p() / f64::from(rank).sqrt();
            if score <= 0.0 {
                continue;
            }
            let (hit, terms) = match matches.entry(rowid) {
                std::collections::hash_map::Entry::Occupied(entry) => entry.into_mut(),
                std::collections::hash_map::Entry::Vacant(entry) => {
                    entry.insert((Hit::from_row(row)?, Vec::new()))
                }
            };
            if hit
                .symbol
                .as_ref()
                .is_some_and(|symbol| symbol.to_lowercase().contains(&term))
            {
                score *= 1.25;
            }
            hit.score += score;
            terms.push((term.clone(), score));
        }
    }
    let mut ranked: Vec<_> = matches
        .into_iter()
        .map(|(id, (mut hit, mut terms))| {
            if chunks {
                hit.score *= 1.0 + (terms.len().saturating_sub(1) as f64 * 0.09).min(0.36);
            }
            terms.sort_unstable_by(|left, right| {
                right
                    .1
                    .total_cmp(&left.1)
                    .then_with(|| left.0.cmp(&right.0))
            });
            hit.terms = terms
                .into_iter()
                .take(if chunks { 8 } else { 6 })
                .map(|pair| pair.0)
                .collect();
            let folded_path = hit.file_path.to_lowercase();
            (hit, folded_path, id)
        })
        .collect();
    ranked.sort_unstable_by(|left, right| {
        right
            .0
            .score
            .total_cmp(&left.0.score)
            .then_with(|| left.1.cmp(&right.1))
            .then_with(|| left.0.start_line.cmp(&right.0.start_line))
            .then_with(|| left.2.cmp(&right.2))
    });
    Ok(ranked
        .into_iter()
        .take(limit.max(1))
        .map(|(mut hit, _, _)| {
            hit.score = (hit.score * 10_000.0).round_ties_even() / 10_000.0;
            hit
        })
        .collect())
}

pub fn total(db: &Connection) -> rusqlite::Result<i64> {
    db.query_row("SELECT COUNT(*) FROM content_search", [], |row| row.get(0))
}

pub fn frequencies(db: &Connection, terms: &[String]) -> rusqlite::Result<BTreeMap<String, i64>> {
    let mut query =
        db.prepare_cached("SELECT COUNT(*) FROM content_search WHERE content_search MATCH ?1")?;
    let mut result = BTreeMap::new();
    for term in terms {
        let term = term.trim().to_lowercase();
        if term.is_empty() || result.contains_key(&term) {
            continue;
        }
        let input = format!("body : {}", phrase(&term));
        let count = query.query_row([input], |row| row.get(0))?;
        result.insert(term, count);
    }
    Ok(result)
}

pub fn paths(db: &Connection, prefix: &str, limit: u32) -> rusqlite::Result<Vec<String>> {
    let prefix = prefix
        .replace('\\', "\\\\")
        .replace('_', "\\_")
        .replace('%', "\\%");
    db.prepare_cached("SELECT path FROM files WHERE path LIKE ?1 ESCAPE '\\' ORDER BY path COLLATE NOCASE,path LIMIT ?2")?
        .query_map(params![format!("{prefix}%"), limit], |row| row.get(0))?.collect()
}
