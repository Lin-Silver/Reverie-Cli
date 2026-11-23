use reverie_context::{ContextEngine, Result};
use serde_json::json;
use std::path::Path;

const HELP: &str = "Usage:\n  reverie --context-engine index <workspace> <database>\n  reverie --context-engine search <database> <query> [limit]\n  reverie --context-engine paths <database> <prefix> [limit]\n  reverie --context-engine lookup <database> <request-json>\n  reverie --context-engine resources-verify <bundle-directory> <manifest-sha256>\n  reverie --context-engine resources-stage <store> <bundle-directory> <manifest-sha256>\n  reverie --context-engine semantic-probe <bundle-directory> <manifest-sha256> [cpu|cuda|direct_ml|core_ml]\n  reverie --context-engine semantic-index <database> <bundle-directory> <manifest-sha256>\n  reverie --context-engine semantic-search <database> <bundle-directory> <manifest-sha256> <query>\n  reverie --context-engine status <database>\n  reverie --context-engine --version\n\nlookup query_type: symbol, file, search, dependencies, outline, explore, task";

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
        [operation, directory, digest, rest @ ..]
            if operation == "semantic-probe" && rest.len() <= 1 =>
        {
            let bundle =
                reverie_context::resources::verify(Path::new(directory), digest, &|| false)?;
            let device = rest
                .first()
                .map(|value| serde_json::from_value(json!(value)))
                .transpose()?
                .unwrap_or_default();
            let models = reverie_context::inference::LocalModels::new(bundle, device, 6)?;
            let result = models.probe()?;
            models.unload()?;
            json!({"probe":result,"after_unload":models.status()?})
        }
        [operation, database, directory, digest] if operation == "semantic-index" => {
            let bundle =
                reverie_context::resources::verify(Path::new(directory), digest, &|| false)?;
            let models =
                reverie_context::inference::LocalModels::new(bundle, Default::default(), 6)?;
            ContextEngine::from_database(Path::new(database))?.index_semantic(
                &models,
                &|| false,
                &|_, _| {},
            )?
        }
        [operation, database, directory, digest, query] if operation == "semantic-search" => {
            let bundle =
                reverie_context::resources::verify(Path::new(directory), digest, &|| false)?;
            let models =
                reverie_context::inference::LocalModels::new(bundle, Default::default(), 6)?;
            let engine = ContextEngine::from_database(Path::new(database))?;
            json!({"results":engine.query_hybrid(&models,query,10,12000,&||false)?,"index":engine.semantic_status()?,"models":models.status()?,"strategy":"hybrid","rerank_candidates":16})
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
