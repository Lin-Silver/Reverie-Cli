use crate::catalog::{self, Catalog, Document};
use crate::scan::{self, Result, ScanOptions};
use crate::search;
use rusqlite::{Connection, Transaction};
use serde::Deserialize;
use serde_json::{Value, json, to_value};
use std::io::{self, BufRead, BufWriter, Write};
use std::path::PathBuf;

const PROTOCOL: u32 = 1;

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
enum Request {
    Hello,
    State,
    Scan {
        root: PathBuf,
        options: ScanOptions,
    },
    Changes {
        root: PathBuf,
        options: ScanOptions,
        expected_revision: i64,
    },
    Begin {
        root: String,
        replace: bool,
        expected_revision: i64,
    },
    Apply {
        removed: Vec<String>,
        documents: Vec<Document>,
    },
    Commit,
    Rollback,
    Search {
        weights: Vec<(String, f64)>,
        limit: usize,
        chunks: bool,
        expected_revision: i64,
    },
    Frequencies {
        terms: Vec<String>,
        expected_revision: i64,
    },
    Total {
        expected_revision: i64,
    },
    Paths {
        prefix: String,
        limit: u32,
        expected_revision: i64,
    },
}

fn read_revision(reader: &Connection, expected: i64) -> Result<Transaction<'_>> {
    let transaction = reader.unchecked_transaction()?;
    if catalog::state(&transaction)?.revision != expected {
        return Err("Context index changed since it was loaded".into());
    }
    Ok(transaction)
}

fn respond(request: Request, catalog: &mut Catalog, reader: &Connection) -> Result<Value> {
    let value = match request {
        Request::Hello => json!({"protocol": PROTOCOL, "version": env!("CARGO_PKG_VERSION")}),
        Request::State => to_value(catalog::state(reader)?)?,
        Request::Scan { root, options } => to_value(scan::files(&root, &options)?)?,
        Request::Changes {
            root,
            options,
            expected_revision,
        } => {
            let current = scan::files(&root, &options)?;
            let read = read_revision(reader, expected_revision)?;
            to_value(scan::changes(catalog::files(&read)?, current))?
        }
        Request::Begin {
            root,
            replace,
            expected_revision,
        } => {
            catalog.begin(&root, replace, expected_revision)?;
            Value::Null
        }
        Request::Apply { removed, documents } => {
            catalog.apply(&removed, &documents)?;
            Value::Null
        }
        Request::Commit => to_value(catalog.commit()?)?,
        Request::Rollback => {
            catalog.rollback()?;
            Value::Null
        }
        Request::Search {
            weights,
            limit,
            chunks,
            expected_revision,
        } => {
            let read = read_revision(reader, expected_revision)?;
            to_value(search::ranked(&read, &weights, limit, chunks)?)?
        }
        Request::Frequencies {
            terms,
            expected_revision,
        } => {
            let read = read_revision(reader, expected_revision)?;
            json!({"total": search::total(&read)?, "terms": search::frequencies(&read, &terms)?})
        }
        Request::Total { expected_revision } => {
            let read = read_revision(reader, expected_revision)?;
            to_value(search::total(&read)?)?
        }
        Request::Paths {
            prefix,
            limit,
            expected_revision,
        } => {
            let read = read_revision(reader, expected_revision)?;
            to_value(search::paths(&read, &prefix, limit)?)?
        }
    };
    Ok(value)
}

pub fn serve(path: PathBuf) -> Result<()> {
    let mut catalog = Catalog::open(&path)?;
    let reader = catalog::open_readonly(&path)?;
    let mut output = BufWriter::new(io::stdout().lock());
    for line in io::stdin().lock().lines() {
        let line = line?;
        let response = match serde_json::from_str::<Request>(&line) {
            Ok(request) => {
                let writing = matches!(
                    &request,
                    Request::Begin { .. } | Request::Apply { .. } | Request::Commit
                );
                match respond(request, &mut catalog, &reader) {
                    Ok(value) => json!({"result": value}),
                    Err(error) => {
                        if writing {
                            catalog.rollback()?;
                        }
                        json!({"error": error.to_string()})
                    }
                }
            }
            Err(error) => json!({"error": error.to_string()}),
        };
        serde_json::to_writer(&mut output, &response)?;
        output.write_all(b"\n")?;
        output.flush()?;
    }
    Ok(())
}
