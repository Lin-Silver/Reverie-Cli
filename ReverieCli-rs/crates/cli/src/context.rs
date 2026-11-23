use reverie_context::{ContextEngine, Result};
use serde_json::json;
use std::path::Path;

const HELP: &str = "Usage:\n  reverie --context-engine index <workspace> <database>\n  reverie --context-engine search <database> <query> [limit]\n  reverie --context-engine paths <database> <prefix> [limit]\n  reverie --context-engine lookup <database> <request-json>\n  reverie --context-engine resources-verify <bundle-directory> <manifest-sha256>\n  reverie --context-engine resources-stage <store> <bundle-directory> <manifest-sha256>\n  reverie --context-engine status <database>\n  reverie --context-engine --version\n\nlookup query_type: symbol, file, search, dependencies, outline, explore, task";

pub fn run(args: &[String]) -> Result<()> {
    let output = match args {
        [] => {
            println!("{HELP}");
            return Ok(());
        }
        [option] if option == "--help" || option == "-h" => {
            println!("{HELP}");
            return Ok(());
        }
        [option] if option == "--version" => {
            json!({"version":reverie_protocol::VERSION,"backend":"rust","execution":"in-process"})
        }
        [operation, root, database] if operation == "index" => {
            ContextEngine::open(Path::new(root), Path::new(database))?.index(false)?
        }
        [operation, directory, digest] if operation == "resources-verify" => {
            let bundle =
                reverie_context::resources::verify(Path::new(directory), digest, &|| false)?;
            json!({"verified":true,"activated":false,"directory":bundle.directory,"manifest_sha256":bundle.digest,"manifest":bundle.manifest})
        }
        [operation, store, directory, digest] if operation == "resources-stage" => {
            let bundle = reverie_context::resources::stage(
                Path::new(store),
                Path::new(directory),
                digest,
                &|| false,
            )?;
            json!({"verified":true,"staged":true,"activated":false,"directory":bundle.directory,"manifest_sha256":bundle.digest,"manifest":bundle.manifest})
        }
        [operation, database] if operation == "status" => {
            reverie_context::database_status(Path::new(database))?
        }
        [operation, database, request] if operation == "lookup" => {
            ContextEngine::from_database(Path::new(database))?
                .lookup(&serde_json::from_str(request)?)?
        }
        [operation, database, input, rest @ ..]
            if rest.len() <= 1 && ["search", "chunks", "paths"].contains(&operation.as_str()) =>
        {
            let limit = rest
                .first()
                .map(|limit| limit.parse::<u32>())
                .transpose()?
                .unwrap_or(10)
                .clamp(1, 200);
            let engine = ContextEngine::from_database(Path::new(database))?;
            if operation == "paths" {
                json!(engine.paths(input, limit)?)
            } else {
                json!(engine.query(input, limit as usize, 12000)?)
            }
        }
        _ => return Err(HELP.into()),
    };
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
