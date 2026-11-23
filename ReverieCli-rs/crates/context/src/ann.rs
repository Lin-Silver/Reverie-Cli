use crate::{Result, semantic};
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex},
};
use usearch::{Index, IndexOptions, MetricKind, ScalarKind};

pub const FORMAT: i64 = 1;
pub const DIMENSIONS: usize = 384;
pub const SCHEMA: &str = "CREATE TABLE neighbor_graphs(generation INTEGER PRIMARY KEY REFERENCES generations(id) ON DELETE CASCADE,format INTEGER NOT NULL,sha256 TEXT NOT NULL,vectors INTEGER NOT NULL,data BLOB NOT NULL);";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct State {
    pub format: i64,
    pub sha256: String,
    pub vectors: i64,
    pub algorithm: String,
}

pub fn state(db: &Connection, generation: i64) -> Result<Option<State>> {
    if db.pragma_query_value(None, "user_version", |row| row.get::<_, i64>(0))? < 2 {
        return Ok(None);
    }
    Ok(db
        .query_row(
            "SELECT format,sha256,vectors FROM neighbor_graphs WHERE generation=?1",
            [generation],
            |row| {
                Ok(State {
                    format: row.get(0)?,
                    sha256: row.get(1)?,
                    vectors: row.get(2)?,
                    algorithm: "hnsw-cosine-f32".into(),
                })
            },
        )
        .optional()?)
}

pub fn healthy(db: &Connection, generation: i64) -> Result<bool> {
    let Some(state) = state(db, generation)? else {
        return Ok(false);
    };
    let bytes: Vec<u8> = db.query_row(
        "SELECT data FROM neighbor_graphs WHERE generation=?1",
        [generation],
        |row| row.get(0),
    )?;
    Ok(state.format == FORMAT && restore(&bytes, &state.sha256, state.vectors.try_into()?).is_ok())
}

struct Cached {
    generation: i64,
    hash: String,
    index: Arc<Index>,
}

#[derive(Default)]
pub struct Cache {
    graphs: Mutex<BTreeMap<String, Cached>>,
}

impl Cache {
    pub fn load(&self, db: &Connection, generation: i64, resource: &str) -> Result<Arc<Index>> {
        let state = state(db, generation)?
            .ok_or("Semantic neighbor graph is missing; rebuild the semantic index.")?;
        if state.format != FORMAT {
            return Err("Unsupported semantic neighbor graph format.".into());
        }
        let mut graphs = self
            .graphs
            .lock()
            .map_err(|_| "Semantic neighbor cache lock was poisoned.")?;
        if let Some(cached) = graphs.get(resource)
            && cached.generation == generation
            && cached.hash == state.sha256
        {
            return Ok(cached.index.clone());
        }
        let bytes: Vec<u8> = db.query_row(
            "SELECT data FROM neighbor_graphs WHERE generation=?1",
            [generation],
            |row| row.get(0),
        )?;
        let index = Arc::new(restore(&bytes, &state.sha256, state.vectors.try_into()?)?);
        graphs.insert(
            resource.into(),
            Cached {
                generation,
                hash: state.sha256,
                index: index.clone(),
            },
        );
        Ok(index)
    }
}

pub fn build(db: &Connection, generation: i64, cancelled: &impl Fn() -> bool) -> Result<()> {
    let count: i64 = db.query_row(
        "SELECT count(*) FROM vectors WHERE generation=?1",
        [generation],
        |row| row.get(0),
    )?;
    let index = new(count.try_into()?)?;
    let mut statement =
        db.prepare("SELECT id,vector FROM vectors WHERE generation=?1 ORDER BY identity")?;
    let mut rows = statement.query([generation])?;
    while let Some(row) = rows.next()? {
        if cancelled() {
            return Err("Semantic neighbor graph construction cancelled.".into());
        }
        let vector = semantic::decode(&row.get::<_, Vec<u8>>(1)?)?;
        index.add(row.get::<_, i64>(0)?.try_into()?, &vector)?;
    }
    if cancelled() {
        return Err("Semantic neighbor graph construction cancelled before activation.".into());
    }
    let bytes = save(&index)?;
    db.execute("INSERT OR REPLACE INTO neighbor_graphs(generation,format,sha256,vectors,data) VALUES(?1,?2,?3,?4,?5)", params![generation, FORMAT, digest(&bytes), count, bytes])?;
    Ok(())
}

pub fn new(capacity: usize) -> Result<Index> {
    let index = Index::new(&IndexOptions {
        dimensions: DIMENSIONS,
        metric: MetricKind::Cos,
        quantization: ScalarKind::F32,
        connectivity: 16,
        expansion_add: 128,
        expansion_search: 128,
        multi: false,
    })?;
    index.reserve(capacity)?;
    Ok(index)
}

pub fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn save(index: &Index) -> Result<Vec<u8>> {
    let mut bytes = vec![0; index.serialized_length()];
    index.save_to_buffer(&mut bytes)?;
    Ok(bytes)
}

pub fn restore(bytes: &[u8], hash: &str, count: usize) -> Result<Index> {
    if digest(bytes) != hash {
        return Err("Semantic neighbor graph failed its SHA-256 check.".into());
    }
    let metadata = Index::metadata_from_buffer(bytes)?;
    if metadata.dimensions != DIMENSIONS as u64
        || metadata.metric != MetricKind::Cos
        || metadata.quantization != ScalarKind::F32
        || metadata.multi
        || metadata.count_present != count as u64
        || metadata.count_deleted != 0
    {
        return Err("Incompatible semantic neighbor graph metadata.".into());
    }
    let index = new(count)?;
    index.load_from_buffer(bytes)?;
    if index.size() != count {
        return Err("Semantic neighbor graph count does not match its generation.".into());
    }
    Ok(index)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn persisted_graph_restores_actual_neighbors_and_rejects_damage() {
        let index = new(3).unwrap();
        let mut vector = vec![0.0; DIMENSIONS];
        vector[0] = 1.0;
        index.add(91, &vector).unwrap();
        vector[0] = -1.0;
        index.add(42, &vector).unwrap();
        vector[0] = 0.0;
        vector[1] = 1.0;
        index.add(13, &vector).unwrap();
        let bytes = save(&index).unwrap();
        let hash = digest(&bytes);
        let reopened = restore(&bytes, &hash, 3).unwrap();
        let matches = reopened.search(&vector, 3).unwrap();
        assert_eq!(matches.keys[0], 13);
        assert_eq!(matches.distances, [0.0, 1.0, 1.0]);
        let mut remaining = matches.keys[1..].to_vec();
        remaining.sort();
        assert_eq!(remaining, [42, 91]);
        assert!(restore(&bytes, &hash, 2).is_err());
        let mut damaged = bytes;
        damaged.pop();
        assert!(restore(&damaged, &hash, 3).is_err());
    }
}
