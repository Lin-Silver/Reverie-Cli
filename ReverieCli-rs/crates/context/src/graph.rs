use crate::Result;
use rusqlite::{Connection, params};
use std::collections::{BTreeMap, BTreeSet};

pub fn resolve(db: &Connection) -> Result<()> {
    let mut by_name = BTreeMap::<String, BTreeSet<String>>::new();
    let mut counts = BTreeMap::<String, usize>::new();
    let mut statement = db.prepare(
        "SELECT name,symbol FROM chunks WHERE kind!='MODULE' OR signature!='' ORDER BY symbol",
    )?;
    for pair in statement.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
    })? {
        let (name, symbol) = pair?;
        *counts.entry(symbol.clone()).or_default() += 1;
        by_name.entry(name).or_default().insert(symbol);
    }
    let symbols = counts
        .into_iter()
        .filter(|(_, count)| *count == 1)
        .map(|(name, _)| name)
        .collect::<BTreeSet<_>>();
    let references = db
        .prepare("SELECT rowid,source_symbol,target_text FROM symbol_references ORDER BY rowid")?
        .query_map([], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let mut update = db.prepare_cached(
        "UPDATE symbol_references SET target_symbol=?1,resolution=?2 WHERE rowid=?3",
    )?;
    for (rowid, source, target) in references {
        let mut name = target.replace(':', ".").replace("..", ".");
        let receiver = ["self.", "this.", "Self."]
            .iter()
            .find(|prefix| name.starts_with(**prefix));
        let receiver_scope = receiver.is_some();
        if let Some(receiver) = receiver {
            name = name[receiver.len()..].to_owned();
        }
        let mut selected = symbols.get(&name).cloned();
        let mut resolution = if receiver_scope {
            "inferred_receiver_scope"
        } else {
            "lexical"
        };
        if selected.is_none() {
            let mut scope = source.as_str();
            loop {
                if symbols.contains(&format!("{scope}.{name}")) {
                    selected = Some(format!("{scope}.{name}"));
                    break;
                }
                let Some((parent, _)) = scope.rsplit_once('.') else {
                    break;
                };
                scope = parent;
            }
        }
        if selected.is_none() {
            let leaf = name.rsplit('.').next().unwrap_or(&name);
            if let Some(candidates) = by_name.get(leaf) {
                if candidates.len() == 1
                    && candidates
                        .first()
                        .is_some_and(|name| symbols.contains(name))
                {
                    selected = candidates.first().cloned();
                    resolution = "inferred_unique_name";
                } else {
                    resolution = "ambiguous";
                }
            } else {
                resolution = "unresolved";
            }
        }
        update.execute(params![selected, resolution, rowid])?;
    }
    Ok(())
}
