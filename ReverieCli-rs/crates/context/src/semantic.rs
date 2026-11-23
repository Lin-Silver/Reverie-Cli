use crate::{Evidence, Result, inference::LocalModels};
use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    cmp::{Ordering, Reverse},
    collections::{BTreeMap, BinaryHeap},
    fs,
    path::Path,
};

const APPLICATION_ID: i64 = 0x52565345;
const CONTRACT_VERSION: i64 = 1;
const SCHEMA:&str="
CREATE TABLE semantic_state(id INTEGER PRIMARY KEY CHECK(id=1),root TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 0);
CREATE TABLE generations(id INTEGER PRIMARY KEY AUTOINCREMENT,revision INTEGER NOT NULL,resource_digest TEXT NOT NULL,contract INTEGER NOT NULL);
CREATE TABLE vectors(id INTEGER PRIMARY KEY AUTOINCREMENT,generation INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,identity TEXT NOT NULL,evidence TEXT NOT NULL,vector BLOB NOT NULL,UNIQUE(generation,identity));
CREATE INDEX vectors_identity ON vectors(identity,generation);
";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexState {
    pub generation: i64,
    pub revision: i64,
    pub resource_digest: String,
    pub vectors: i64,
    pub contract_version: i64,
}

pub struct Store {
    db: Connection,
}

fn state(db: &Connection) -> Result<IndexState> {
    let generation: i64 =
        db.query_row("SELECT active FROM semantic_state WHERE id=1", [], |row| {
            row.get(0)
        })?;
    if generation == 0 {
        return Ok(IndexState {
            generation: 0,
            revision: 0,
            resource_digest: String::new(),
            vectors: 0,
            contract_version: CONTRACT_VERSION,
        });
    }
    Ok(db.query_row("SELECT revision,resource_digest,contract,(SELECT count(*) FROM vectors WHERE generation=?1) FROM generations WHERE id=?1",[generation],|row|Ok(IndexState{generation,revision:row.get(0)?,resource_digest:row.get(1)?,contract_version:row.get(2)?,vectors:row.get(3)?}))?)
}

fn check(db: &Connection, root: &Path) -> Result<()> {
    let application: i64 = db.pragma_query_value(None, "application_id", |row| row.get(0))?;
    let version: i64 = db.pragma_query_value(None, "user_version", |row| row.get(0))?;
    let stored_root: String =
        db.query_row("SELECT root FROM semantic_state WHERE id=1", [], |row| {
            row.get(0)
        })?;
    if application != APPLICATION_ID || version != 1 || stored_root != root.to_string_lossy() {
        return Err("Incompatible semantic index or workspace identity.".into());
    }
    Ok(())
}

pub fn status(path: &Path, root: &Path) -> Result<Option<IndexState>> {
    if !path.exists() {
        return Ok(None);
    }
    let db = Connection::open_with_flags(
        path.canonicalize()?,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
    )?;
    db.busy_timeout(std::time::Duration::from_secs(10))?;
    check(&db, root)?;
    Ok(Some(state(&db)?))
}

impl Store {
    pub fn open(path: &Path, root: &Path) -> Result<Self> {
        let parent = path.parent().ok_or("Semantic index has no parent.")?;
        fs::create_dir_all(parent)?;
        let mut db = Connection::open(
            parent
                .canonicalize()?
                .join(path.file_name().ok_or("Semantic index needs a filename.")?),
        )?;
        db.busy_timeout(std::time::Duration::from_secs(30))?;
        db.pragma_update(None, "foreign_keys", true)?;
        let application: i64 = db.pragma_query_value(None, "application_id", |row| row.get(0))?;
        if application == 0 {
            let transaction = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
            let application: i64 =
                transaction.pragma_query_value(None, "application_id", |row| row.get(0))?;
            if application == 0 {
                let tables: i64 = transaction.query_row(
                    "SELECT count(*) FROM sqlite_schema WHERE type='table'",
                    [],
                    |row| row.get(0),
                )?;
                let version: i64 =
                    transaction.pragma_query_value(None, "user_version", |row| row.get(0))?;
                if tables != 0 || version != 0 {
                    return Err("Refusing to overwrite an unrelated semantic database.".into());
                }
                transaction.execute_batch(SCHEMA)?;
                transaction.execute(
                    "INSERT INTO semantic_state(id,root) VALUES(1,?1)",
                    [root.to_string_lossy().as_ref()],
                )?;
                transaction.pragma_update(None, "application_id", APPLICATION_ID)?;
                transaction.pragma_update(None, "user_version", 1)?;
            }
            transaction.commit()?;
        }
        check(&db, root)?;
        db.pragma_update(None, "journal_mode", "WAL")?;
        db.pragma_update(None, "synchronous", "FULL")?;
        Ok(Self { db })
    }

    pub fn update(
        &mut self,
        revision: i64,
        evidence: &[Evidence],
        models: &LocalModels,
        cancelled: &impl Fn() -> bool,
        progress: &impl Fn(usize, usize),
        before_activate: &impl Fn() -> Result<()>,
    ) -> Result<IndexState> {
        if cancelled() {
            return Err("Semantic indexing cancelled.".into());
        }
        let transaction = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let previous = state(&transaction)?;
        if previous.generation > 0
            && previous.revision == revision
            && previous.resource_digest == models.bundle.digest
            && previous.contract_version == CONTRACT_VERSION
        {
            before_activate()?;
            progress(evidence.len(), evidence.len());
            return Ok(previous);
        }
        transaction.execute(
            "INSERT INTO generations(revision,resource_digest,contract) VALUES(?1,?2,?3)",
            params![revision, models.bundle.digest, CONTRACT_VERSION],
        )?;
        let generation = transaction.last_insert_rowid();
        let mut done = 0;
        for batch in evidence.chunks(8) {
            if cancelled() {
                return Err(
                    "Semantic indexing cancelled; the previous generation remains active.".into(),
                );
            }
            let mut missing = Vec::new();
            let mut reused = Vec::new();
            for hit in batch {
                let identity = identity(hit, &models.bundle.digest)?;
                let cached: Option<Vec<u8>> = transaction
                    .query_row(
                        "SELECT vector FROM vectors WHERE generation=?1 AND identity=?2",
                        params![previous.generation, identity],
                        |row| row.get(0),
                    )
                    .optional()?;
                if let Some(vector) = cached {
                    decode(&vector)?;
                    reused.push((hit, identity, vector));
                } else {
                    missing.push((hit, identity));
                }
            }
            let inputs = missing
                .iter()
                .map(|(hit, _)| {
                    format!(
                        "{}:{}\n{}\n{}",
                        hit.file_path,
                        hit.start_line,
                        hit.symbol.as_deref().unwrap_or_default(),
                        hit.content
                    )
                })
                .collect::<Vec<_>>();
            let vectors = models.embed(&inputs, false, cancelled)?;
            for ((hit, identity), vector) in missing.into_iter().zip(vectors) {
                insert(&transaction, generation, &identity, hit, &encode(&vector)?)?;
            }
            for (hit, identity, vector) in reused {
                insert(&transaction, generation, &identity, hit, &vector)?;
            }
            done += batch.len();
            progress(done, evidence.len());
        }
        if cancelled() {
            return Err(
                "Semantic indexing cancelled; the previous generation remains active.".into(),
            );
        }
        before_activate()?;
        transaction.execute(
            "UPDATE semantic_state SET active=?1 WHERE id=1",
            [generation],
        )?;
        transaction.execute(
            "DELETE FROM generations WHERE id!=?1 AND id!=?2 AND id NOT IN (SELECT max(id) FROM generations GROUP BY resource_digest)",
            params![generation, previous.generation],
        )?;
        transaction.commit()?;
        state(&self.db)
    }

    pub fn query(
        &self,
        query: &[f32],
        resource_digest: &str,
        limit: usize,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Vec<Evidence>> {
        encode(query)?;
        let transaction = self.db.unchecked_transaction()?;
        // Old runs retain their model resource. Keep one complete generation per
        // resource digest and read it in the same SQLite snapshot as its vectors.
        let (generation, revision): (i64, i64) = transaction.query_row(
            "SELECT id,revision FROM generations WHERE resource_digest=?1 AND contract=?2 ORDER BY id DESC LIMIT 1",
            params![resource_digest, CONTRACT_VERSION],
            |row| Ok((row.get(0)?, row.get(1)?)),
        ).optional()?.ok_or("Semantic index is missing or belongs to another model resource revision.")?;
        let mut nearest = BinaryHeap::new();
        let limit = limit.clamp(1, 200);
        let mut statement =
            transaction.prepare("SELECT id,vector,identity FROM vectors WHERE generation=?1")?;
        let mut rows = statement.query([generation])?;
        while let Some(row) = rows.next()? {
            if cancelled() {
                return Err("Semantic nearest-neighbor retrieval cancelled.".into());
            }
            let vector = decode(&row.get::<_, Vec<u8>>(1)?)?;
            let score = query
                .iter()
                .zip(vector)
                .map(|(left, right)| left * right)
                .sum::<f32>();
            let neighbor = Neighbor {
                id: row.get(0)?,
                identity: row.get(2)?,
                score,
            };
            nearest.push(Reverse(neighbor));
            if nearest.len() > limit {
                nearest.pop();
            }
        }
        let mut nearest = nearest.into_iter().map(|value| value.0).collect::<Vec<_>>();
        nearest.sort_by(|left, right| right.cmp(left));
        nearest
            .into_iter()
            .map(|neighbor| {
                let text: String = transaction.query_row(
                    "SELECT evidence FROM vectors WHERE id=?1 AND generation=?2",
                    params![neighbor.id, generation],
                    |row| row.get(0),
                )?;
                let mut evidence: Evidence = serde_json::from_str(&text)?;
                evidence.revision = revision;
                evidence.score = neighbor.score as f64;
                evidence.sources = vec!["semantic".into()];
                Ok(evidence)
            })
            .collect()
    }
}

fn insert(
    db: &Connection,
    generation: i64,
    identity: &str,
    evidence: &Evidence,
    vector: &[u8],
) -> Result<()> {
    db.execute(
        "INSERT INTO vectors(generation,identity,evidence,vector) VALUES(?1,?2,?3,?4)",
        params![
            generation,
            identity,
            serde_json::to_string(evidence)?,
            vector
        ],
    )?;
    Ok(())
}
fn identity(evidence: &Evidence, resource_digest: &str) -> Result<String> {
    let input = serde_json::to_vec(&(
        CONTRACT_VERSION,
        resource_digest,
        &evidence.file_path,
        evidence.start_line,
        evidence.end_line,
        &evidence.content_hash,
        &evidence.content,
        &evidence.symbol,
    ))?;
    Ok(Sha256::digest(input)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}
fn encode(vector: &[f32]) -> Result<Vec<u8>> {
    if vector.len() != 384 || vector.iter().any(|value| !value.is_finite()) {
        return Err("Invalid persisted semantic vector.".into());
    }
    let norm = vector.iter().map(|value| value * value).sum::<f32>();
    if (norm - 1.0).abs() > 0.01 {
        return Err("Semantic vectors must be normalized.".into());
    }
    Ok(vector
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect())
}
fn decode(bytes: &[u8]) -> Result<Vec<f32>> {
    if bytes.len() != 384 * 4 {
        return Err("Invalid semantic vector size.".into());
    }
    let vector = bytes
        .chunks_exact(4)
        .map(|value| f32::from_le_bytes(value.try_into().unwrap()))
        .collect::<Vec<_>>();
    encode(&vector)?;
    Ok(vector)
}
#[derive(Debug)]
struct Neighbor {
    id: i64,
    identity: String,
    score: f32,
}
impl PartialEq for Neighbor {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}
impl Eq for Neighbor {}
impl Ord for Neighbor {
    fn cmp(&self, other: &Self) -> Ordering {
        self.score
            .total_cmp(&other.score)
            .then_with(|| other.identity.cmp(&self.identity))
    }
}
impl PartialOrd for Neighbor {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

pub fn fuse(lexical: Vec<Evidence>, semantic: Vec<Evidence>) -> Vec<Evidence> {
    let mut merged = BTreeMap::<(String, u32, u32, String), Evidence>::new();
    for list in [lexical, semantic] {
        let mut seen = std::collections::BTreeSet::new();
        for (rank, mut hit) in list.into_iter().enumerate() {
            let key = (
                hit.file_path.clone(),
                hit.start_line,
                hit.end_line,
                hit.content_hash.clone(),
            );
            if !seen.insert(key.clone()) {
                continue;
            }
            hit.score = 1.0 / (60.0 + rank as f64 + 1.0);
            if let Some(previous) = merged.get_mut(&key) {
                previous.score += hit.score;
                for source in hit.sources {
                    if !previous.sources.contains(&source) {
                        previous.sources.push(source);
                    }
                }
            } else {
                merged.insert(key, hit);
            }
        }
    }
    let mut results = merged.into_values().collect::<Vec<_>>();
    results.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| left.file_path.cmp(&right.file_path))
            .then_with(|| left.start_line.cmp(&right.start_line))
            .then_with(|| left.end_line.cmp(&right.end_line))
    });
    results
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stored_vectors_and_top_k_keep_positive_negative_and_tied_neighbors() {
        let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/context-tests");
        fs::create_dir_all(&parent).unwrap();
        let root = tempfile::tempdir_in(parent).unwrap();
        let database = root.path().join("semantic.sqlite3");
        let store = Store::open(&database, root.path()).unwrap();
        store
            .db
            .execute(
                "INSERT INTO generations(revision,resource_digest,contract) VALUES(3,'model-v1',1)",
                [],
            )
            .unwrap();
        store
            .db
            .execute("UPDATE semantic_state SET active=1", [])
            .unwrap();
        for (name, sign) in [("tied", 1.0), ("negative", -1.0), ("positive", 1.0)] {
            let evidence = Evidence {
                file_path: name.into(),
                start_line: 1,
                end_line: 1,
                content: name.into(),
                content_hash: "fixed".into(),
                revision: 3,
                symbol: None,
                score: 0.0,
                sources: vec!["semantic".into()],
            };
            let mut vector = vec![0.0; 384];
            vector[0] = sign;
            insert(&store.db, 1, name, &evidence, &encode(&vector).unwrap()).unwrap();
        }
        let mut vector = vec![0.0; 384];
        vector[0] = 1.0;
        let results = store.query(&vector, "model-v1", 2, &|| false).unwrap();
        assert_eq!(
            results
                .iter()
                .map(|hit| hit.file_path.as_str())
                .collect::<Vec<_>>(),
            vec!["positive", "tied"]
        );
        assert!(store.query(&vector, "changed-model", 2, &|| false).is_err());
        assert!(store.query(&vector, "model-v1", 2, &|| true).is_err());
        store
            .db
            .execute(
                "INSERT INTO generations(revision,resource_digest,contract) VALUES(4,'model-v2',1)",
                [],
            )
            .unwrap();
        store
            .db
            .execute("UPDATE semantic_state SET active=2", [])
            .unwrap();
        assert_eq!(
            store.query(&vector, "model-v1", 1, &|| false).unwrap()[0].file_path,
            "positive"
        );
        assert!(decode(&[0; 383 * 4]).is_err());
        vector[0] = f32::NAN;
        assert!(encode(&vector).is_err());
        drop(store);
        assert_eq!(
            status(&database, root.path()).unwrap().unwrap().generation,
            2
        );
        let other = root.path().join("unrelated.sqlite3");
        Connection::open(&other)
            .unwrap()
            .pragma_update(None, "user_version", 9)
            .unwrap();
        assert!(Store::open(&other, root.path()).is_err());
        assert_eq!(
            Connection::open(&other)
                .unwrap()
                .pragma_query_value(None, "user_version", |row| row.get::<_, i64>(0))
                .unwrap(),
            9
        );
    }
    #[test]
    fn reciprocal_rank_fusion_merges_sources_without_double_counting_duplicates() {
        let hit = Evidence {
            file_path: "a".into(),
            start_line: 1,
            end_line: 1,
            content: "same".into(),
            content_hash: "fixed".into(),
            revision: 1,
            symbol: None,
            score: 99.0,
            sources: vec!["lexical".into()],
        };
        let mut semantic = hit.clone();
        semantic.sources = vec!["semantic".into()];
        let merged = fuse(vec![hit.clone(), hit], vec![semantic]);
        assert_eq!(merged.len(), 1);
        assert!((merged[0].score - 2.0 / 61.0).abs() < 1e-12);
        assert_eq!(merged[0].sources, vec!["lexical", "semantic"]);
    }
}
