#![forbid(unsafe_code)]

mod catalog;
mod parsing;
mod scan;
mod search;
mod text;
mod worker;

use catalog::Catalog;
use scan::Result;
use serde::Serialize;
use std::ffi::OsString;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Instant;

const HELP: &str = "Usage:\n  reverie-context-engine index <workspace> <database>\n  reverie-context-engine search <database> <query> [limit]\n  reverie-context-engine chunks <database> <query> [limit]\n  reverie-context-engine paths <database> <prefix> [limit]\n  reverie-context-engine status <database>\n  reverie-context-engine --version";

fn json_response(value: impl Serialize) -> Result<()> {
    let mut out = io::stdout().lock();
    serde_json::to_writer(&mut out, &value)?;
    writeln!(out)?;
    Ok(())
}

fn index(root: &Path, database: &Path) -> Result<()> {
    let started = Instant::now();
    let root = root.canonicalize()?;
    if !root.is_dir() {
        return Err("Workspace must be a directory".into());
    }
    let identity = root.to_str().ok_or("Workspace path is not Unicode")?;
    let mut catalog = Catalog::open(database)?;
    let state = catalog::state(catalog.connection())?;
    if !state.root.is_empty() && state.root != identity {
        return Err("Database belongs to a different workspace".into());
    }
    let candidates = scan::files(&root, &scan::default_options(&root)?)?;
    let scanned = candidates.len();
    let (changed, removed) = scan::changes(catalog::files(catalog.connection())?, candidates);
    let mut revision = state.revision;
    let mut indexed = 0;
    let mut skipped = 0;
    if !changed.is_empty() || !removed.is_empty() || revision == 0 {
        catalog.begin(identity, false, revision)?;
        catalog.apply(&removed, &[])?;
        let mut parsers = parsing::Parsers::default();
        for entry in changed {
            let document = parsers.document(&root, entry)?;
            if document.body.is_some() {
                indexed += 1;
            } else {
                skipped += 1;
            }
            catalog.apply(&[], &[document])?;
        }
        revision = catalog.commit()?.revision;
    }
    json_response(serde_json::json!({
        "backend": "rust", "revision": revision, "scanned": scanned, "indexed": indexed,
        "skipped": skipped, "removed": removed.len(), "elapsed_ms": started.elapsed().as_secs_f64() * 1000.0,
    }))
}

fn limit(argument: Option<&OsString>) -> Result<u32> {
    argument.map_or(Ok(80), |value| {
        let value: u32 = value.to_str().ok_or("Invalid limit")?.parse()?;
        if value == 0 {
            return Err("Limit must be positive".into());
        }
        Ok(value)
    })
}

fn run() -> Result<()> {
    let arguments: Vec<_> = std::env::args_os().skip(1).collect();
    let operation = arguments
        .first()
        .and_then(|arg| arg.to_str())
        .unwrap_or("--help");
    match (operation, arguments.as_slice()) {
        ("--version", [_]) => println!("reverie-context-engine {}", env!("CARGO_PKG_VERSION")),
        ("--help" | "-h", [] | [_]) => println!("{HELP}"),
        ("index", [_, root, database]) => index(Path::new(root), Path::new(database))?,
        ("serve", [_, database]) => worker::serve(PathBuf::from(database))?,
        ("status", [_, database]) => json_response(catalog::state(&catalog::open_readonly(
            Path::new(database),
        )?)?)?,
        ("search" | "chunks" | "paths", [_, database, input, extra @ ..]) if extra.len() <= 1 => {
            let db = catalog::open_readonly(Path::new(database))?;
            let input = input.to_str().ok_or("Search input is not Unicode")?;
            let limit = limit(extra.first())?;
            if operation == "paths" {
                json_response(search::paths(&db, input, limit)?)?;
            } else {
                let weights: Vec<_> = input
                    .split_whitespace()
                    .map(|word| (word.to_owned(), 1.0))
                    .collect();
                json_response(search::ranked(
                    &db,
                    &weights,
                    limit as usize,
                    operation == "chunks",
                )?)?;
            }
        }
        _ => return Err(HELP.into()),
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("Context Engine: {error}");
            ExitCode::FAILURE
        }
    }
}
