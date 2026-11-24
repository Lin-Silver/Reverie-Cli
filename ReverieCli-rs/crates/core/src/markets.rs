use crate::{Result, config};
use reverie_protocol::{
    AddMarketRequest, MarketEntry, MarketKind, MarketRequest, MarketSource, MarketsState,
    SetMarketEnabledRequest,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
    process::Stdio,
};
use tokio::process::Command;
use tokio_util::sync::CancellationToken;
const MAX_MANIFEST_BYTES: u64 = 16 * 1024 * 1024;

#[derive(Serialize, Deserialize)]
struct Store {
    schema: String,
    revision: u64,
    sources: Vec<MarketSource>,
    entries: BTreeMap<String, Vec<MarketEntry>>,
}

fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
fn root(app: &Path) -> PathBuf {
    app.join(".reverie/extensions/markets")
}
fn defaults() -> Store {
    let sources = [
        (
            "anthropic-plugins",
            "Anthropic official plugins",
            MarketKind::Git,
            "https://github.com/anthropics/claude-plugins-official.git",
            ".claude-plugin/marketplace.json",
        ),
        (
            "anthropic-skills",
            "Anthropic Skills",
            MarketKind::Git,
            "https://github.com/anthropics/skills.git",
            ".claude-plugin/marketplace.json",
        ),
        (
            "openai-plugins",
            "OpenAI Plugins",
            MarketKind::Git,
            "https://github.com/openai/plugins.git",
            ".agents/plugins/marketplace.json",
        ),
        (
            "mcp-registry",
            "MCP Registry",
            MarketKind::McpRegistry,
            "https://registry.modelcontextprotocol.io/v0.1/servers",
            "",
        ),
    ]
    .into_iter()
    .map(|(id, name, kind, location, manifest_path)| MarketSource {
        id: id.into(),
        name: name.into(),
        kind,
        location: location.into(),
        manifest_path: manifest_path.into(),
        builtin: true,
        enabled: true,
        status: "not_loaded".into(),
        error: String::new(),
        content_sha256: String::new(),
        source_commit: String::new(),
        entry_count: 0,
        next_cursor: String::new(),
    })
    .collect();
    Store {
        schema: "reverie.markets.v1".into(),
        revision: 0,
        sources,
        entries: BTreeMap::new(),
    }
}
fn load(app: &Path) -> Result<Store> {
    match fs::read(root(app).join("catalog.json")) {
        Ok(bytes) => {
            let store: Store = serde_json::from_slice(&bytes)?;
            if store.schema != "reverie.markets.v1" {
                return Err(
                    "Unsupported marketplace catalog schema; original data was preserved.".into(),
                );
            }
            if store.sources.iter().any(|source| {
                source.id.is_empty()
                    || !source
                        .id
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
            }) {
                return Err(
                    "Invalid marketplace source identity; original catalog was preserved.".into(),
                );
            }
            Ok(store)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(defaults()),
        Err(error) => Err(error.into()),
    }
}
fn change<T>(
    app: &Path,
    expected: Option<u64>,
    edit: impl FnOnce(&mut Store) -> Result<T>,
) -> Result<T> {
    let directory = root(app);
    fs::create_dir_all(&directory)?;
    let lock = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(directory.join("catalog.lock"))?;
    lock.lock()?;
    let mut store = load(app)?;
    if expected.is_some_and(|revision| revision != store.revision) {
        return Err("Marketplace catalog revision changed; reload before retrying.".into());
    }
    let result = edit(&mut store)?;
    store.revision = store
        .revision
        .checked_add(1)
        .ok_or("Marketplace revision overflow.")?;
    config::atomic_json(
        &directory.join("catalog.json"),
        &serde_json::to_value(&store)?,
    )?;
    Ok(result)
}
pub fn state(app: &Path) -> Result<MarketsState> {
    let store = load(app)?;
    Ok(MarketsState {
        revision: store.revision,
        sources: store.sources,
    })
}

fn relative(path: &str) -> Result<&Path> {
    let path = Path::new(path);
    if path.as_os_str().is_empty()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_) | Component::CurDir))
    {
        return Err("Marketplace manifest must be a relative path within its source.".into());
    }
    Ok(path)
}
fn validate_location(kind: MarketKind, location: &str) -> Result<String> {
    if location.is_empty() || location.contains(['\n', '\r', '\0']) || location.starts_with('-') {
        return Err("Supply a valid marketplace source.".into());
    }
    if kind == MarketKind::Directory || kind == MarketKind::Git && Path::new(location).is_dir() {
        let directory = config::canonical_project(Path::new(location))?;
        return Ok(directory.to_string_lossy().into_owned());
    }
    let url = reqwest::Url::parse(location)?;
    if !(matches!(url.scheme(), "http" | "https")
        || kind == MarketKind::Git && url.scheme() == "ssh")
        || url.password().is_some()
        || !(url.username().is_empty() || kind == MarketKind::Git && url.scheme() == "ssh")
    {
        return Err("Use HTTP(S), SSH Git or a local directory without embedded passwords.".into());
    }
    Ok(url.to_string().trim_end_matches('/').to_owned())
}
pub fn add(app: &Path, request: AddMarketRequest) -> Result<Value> {
    let name = request.name.trim();
    if name.is_empty() {
        return Err("Marketplace name is required.".into());
    }
    let location = validate_location(request.kind, request.location.trim())?;
    let path = request.manifest_path.unwrap_or_default();
    if !path.is_empty() {
        relative(&path)?;
    }
    let id = format!(
        "manual-{}",
        &digest(format!("{:?}:{location}:{path}", request.kind).as_bytes())[..16]
    );
    let source = change(app, request.expected_revision, |store| {
        if let Some(source) = store.sources.iter().find(|source| {
            source.kind == request.kind
                && source.location.trim_end_matches('/') == location
                && (path.is_empty() || source.manifest_path == path)
        }) {
            return Ok(source.clone());
        }
        let source = MarketSource {
            id: id.clone(),
            name: name.into(),
            kind: request.kind,
            location: location.clone(),
            manifest_path: path,
            builtin: false,
            enabled: true,
            status: "not_loaded".into(),
            error: String::new(),
            content_sha256: String::new(),
            source_commit: String::new(),
            entry_count: 0,
            next_cursor: String::new(),
        };
        store.sources.push(source.clone());
        Ok(source)
    })?;
    Ok(json!({"source":source,"markets":state(app)?}))
}
pub fn remove(app: &Path, request: MarketRequest) -> Result<Value> {
    change(app, request.expected_revision, |store| {
        let source = store
            .sources
            .iter_mut()
            .find(|source| source.id == request.market_id)
            .ok_or("Marketplace source was not found.")?;
        if source.builtin {
            source.enabled = false;
            source.status = "disabled".into();
            source.entry_count = 0;
            source.next_cursor.clear();
        } else {
            store
                .sources
                .retain(|source| source.id != request.market_id);
        }
        store.entries.remove(&request.market_id);
        Ok(())
    })?;
    Ok(json!({"market_id":request.market_id,"markets":state(app)?}))
}
pub fn set_enabled(app: &Path, request: SetMarketEnabledRequest) -> Result<Value> {
    let source = change(app, request.expected_revision, |store| {
        let source = store
            .sources
            .iter_mut()
            .find(|source| source.id == request.market_id)
            .ok_or("Marketplace source was not found.")?;
        source.enabled = request.enabled;
        source.status = if !request.enabled {
            "disabled"
        } else if source.entry_count > 0 {
            "cached"
        } else {
            "not_loaded"
        }
        .into();
        Ok(source.clone())
    })?;
    Ok(json!({"source":source,"markets":state(app)?}))
}
pub fn entries(app: &Path, request: &MarketRequest) -> Result<Value> {
    let store = load(app)?;
    let source = store
        .sources
        .iter()
        .find(|source| source.id == request.market_id)
        .ok_or("Marketplace source was not found.")?;
    let query = request.query.as_deref().unwrap_or("").trim().to_lowercase();
    let items = store
        .entries
        .get(&request.market_id)
        .into_iter()
        .flatten()
        .filter(|entry| {
            query.is_empty()
                || format!("{} {}", entry.name, entry.description)
                    .to_lowercase()
                    .contains(&query)
        })
        .collect::<Vec<_>>();
    let offset = request.offset.unwrap_or(0);
    let limit = request.limit.unwrap_or(30).clamp(1, 100);
    let next = offset.saturating_add(limit).min(items.len());
    Ok(
        json!({"source":source,"items":items.iter().skip(offset).take(limit).collect::<Vec<_>>(),"total":items.len(),"offset":offset,"next_offset":if next<items.len(){Some(next)}else{None},"markets":{"revision":store.revision,"sources":store.sources}}),
    )
}

fn parse(source: &MarketSource, bytes: &[u8]) -> Result<(Vec<MarketEntry>, String)> {
    let document: Value = serde_json::from_slice(bytes)?;
    let hash = digest(bytes);
    let registry = source.kind == MarketKind::McpRegistry;
    let list = document[if registry { "servers" } else { "plugins" }]
        .as_array()
        .ok_or("Marketplace response lacks its plugins or servers array.")?;
    let mut entries = BTreeMap::new();
    for item in list {
        let manifest = if registry { &item["server"] } else { item };
        let name = manifest["name"]
            .as_str()
            .filter(|name| !name.trim().is_empty())
            .ok_or("Marketplace entry has no name.")?;
        let version = manifest["version"].as_str().unwrap_or("");
        let source_kind = if registry {
            "mcp_registry"
        } else if manifest["source"].is_string() {
            "relative"
        } else {
            manifest["source"]["source"]
                .as_str()
                .ok_or("Marketplace entry has no valid source.")?
        };
        if matches!(source_kind, "relative" | "local" | "git-subdir") {
            let path = if source_kind == "relative" {
                manifest["source"].as_str()
            } else {
                manifest["source"]["path"].as_str()
            }
            .ok_or("Marketplace source path is missing.")?;
            relative(path)?;
        }
        let id = if registry {
            format!("{}:{name}@{version}", source.id)
        } else {
            format!("{}:{name}", source.id)
        };
        let entry = MarketEntry {
            id: id.clone(),
            market_id: source.id.clone(),
            name: name.into(),
            description: manifest["description"].as_str().unwrap_or("").into(),
            version: version.into(),
            source_kind: source_kind.into(),
            manifest: manifest.clone(),
            catalog_sha256: hash.clone(),
        };
        if entries.insert(id, entry).is_some() {
            return Err("Marketplace contains duplicate package identities.".into());
        }
    }
    Ok((
        entries.into_values().collect(),
        document["metadata"]["nextCursor"]
            .as_str()
            .unwrap_or("")
            .into(),
    ))
}

async fn git(arguments: &[String], cancel: &CancellationToken) -> Result<Vec<u8>> {
    let mut command = Command::new("git");
    command
        .args(["-c", "protocol.ext.allow=never", "-c", "core.hooksPath="])
        .args(arguments)
        .env("GIT_TERMINAL_PROMPT", "0")
        .stdin(Stdio::null())
        .kill_on_drop(true);
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let output = tokio::select! {_=cancel.cancelled()=>return Err("Marketplace refresh cancelled.".into()),output=command.output()=>output?};
    if !output.status.success() {
        return Err(format!(
            "Git marketplace read failed: {}",
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }
    Ok(output.stdout)
}
async fn read_source(
    app: &Path,
    source: &MarketSource,
    request: &MarketRequest,
    cancel: &CancellationToken,
) -> Result<(Vec<u8>, String)> {
    validate_location(source.kind, &source.location)?;
    match source.kind {
        MarketKind::Git => {
            let repository = root(app)
                .join("repos")
                .join(digest(source.location.as_bytes()));
            fs::create_dir_all(&repository)?;
            let repository_lock = fs::OpenOptions::new()
                .create(true)
                .truncate(false)
                .read(true)
                .write(true)
                .open(repository.join("refresh.lock"))?;
            loop {
                match repository_lock.try_lock() {
                    Ok(()) => break,
                    Err(fs::TryLockError::WouldBlock) => {
                        tokio::select! {_=cancel.cancelled()=>return Err("Marketplace refresh cancelled while waiting for Git.".into()),_=tokio::time::sleep(std::time::Duration::from_millis(20))=>{}}
                    }
                    Err(error) => return Err(error.into()),
                }
            }
            let directory = repository.to_string_lossy().into_owned();
            if !repository.join("HEAD").exists() {
                git(&["init".into(), "--bare".into(), directory.clone()], cancel).await?;
            }
            git(
                &[
                    "-C".into(),
                    directory.clone(),
                    "fetch".into(),
                    "--depth=1".into(),
                    "--no-tags".into(),
                    source.location.clone(),
                    "HEAD".into(),
                ],
                cancel,
            )
            .await?;
            let commit = String::from_utf8(
                git(
                    &[
                        "-C".into(),
                        directory.clone(),
                        "rev-parse".into(),
                        "FETCH_HEAD".into(),
                    ],
                    cancel,
                )
                .await?,
            )?
            .trim()
            .to_owned();
            if commit.len() != 40 || !commit.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                return Err("Git marketplace did not provide a fixed commit identity.".into());
            }
            let paths = if source.manifest_path.is_empty() {
                vec![
                    ".claude-plugin/marketplace.json",
                    ".agents/plugins/marketplace.json",
                    "marketplace.json",
                ]
            } else {
                vec![source.manifest_path.as_str()]
            };
            for path in paths {
                relative(path)?;
                if cancel.is_cancelled() {
                    return Err("Marketplace refresh cancelled.".into());
                }
                if let Ok(size) = git(
                    &[
                        "-C".into(),
                        directory.clone(),
                        "cat-file".into(),
                        "-s".into(),
                        format!("{commit}:{path}"),
                    ],
                    cancel,
                )
                .await
                {
                    if String::from_utf8(size)?.trim().parse::<u64>()? > MAX_MANIFEST_BYTES {
                        return Err("Marketplace manifest exceeds 16 MiB.".into());
                    }
                } else {
                    continue;
                }
                if let Ok(bytes) = git(
                    &[
                        "-C".into(),
                        directory.clone(),
                        "show".into(),
                        format!("{commit}:{path}"),
                    ],
                    cancel,
                )
                .await
                {
                    return Ok((bytes, commit));
                }
            }
            Err("No supported marketplace manifest exists in the selected Git source.".into())
        }
        MarketKind::Directory => {
            let directory = Path::new(&source.location).canonicalize()?;
            let paths = if source.manifest_path.is_empty() {
                vec![
                    ".claude-plugin/marketplace.json",
                    ".agents/plugins/marketplace.json",
                    "marketplace.json",
                ]
            } else {
                vec![source.manifest_path.as_str()]
            };
            for path in paths {
                let target = directory.join(relative(path)?);
                if !target.is_file() {
                    continue;
                }
                let target = target.canonicalize()?;
                if !target.starts_with(&directory) {
                    return Err("Marketplace manifest escapes its source directory.".into());
                }
                use std::io::Read;
                let mut bytes = Vec::new();
                fs::File::open(target)?
                    .take(MAX_MANIFEST_BYTES + 1)
                    .read_to_end(&mut bytes)?;
                if bytes.len() as u64 > MAX_MANIFEST_BYTES {
                    return Err("Marketplace manifest exceeds 16 MiB.".into());
                }
                return Ok((bytes, String::new()));
            }
            Err("No supported marketplace manifest exists in the local directory.".into())
        }
        MarketKind::Manifest | MarketKind::McpRegistry => {
            let mut url = reqwest::Url::parse(&source.location)?;
            if source.kind == MarketKind::McpRegistry {
                let mut parameters = url.query_pairs_mut();
                parameters.append_pair("limit", "100");
                if let Some(cursor) = request
                    .cursor
                    .as_deref()
                    .filter(|cursor| !cursor.is_empty())
                {
                    parameters.append_pair("cursor", cursor);
                }
            }
            let client = reqwest::Client::builder()
                .user_agent(format!("Reverie/{}", reverie_protocol::VERSION))
                .timeout(std::time::Duration::from_secs(30))
                .build()?;
            let read = async {
                let mut response = client.get(url).send().await?.error_for_status()?;
                let mut bytes = Vec::new();
                while let Some(chunk) = response.chunk().await? {
                    if bytes.len() as u64 + chunk.len() as u64 > MAX_MANIFEST_BYTES {
                        return Err("Marketplace manifest exceeds 16 MiB.".into());
                    }
                    bytes.extend_from_slice(&chunk);
                }
                Ok::<_, Box<dyn std::error::Error + Send + Sync>>(bytes)
            };
            let bytes = tokio::select! {_=cancel.cancelled()=>return Err("Marketplace refresh cancelled.".into()),bytes=read=>bytes?};
            Ok((bytes, String::new()))
        }
    }
}

pub async fn refresh(
    app: &Path,
    request: MarketRequest,
    cancel: &CancellationToken,
) -> Result<Value> {
    let initial = load(app)?;
    if request
        .expected_revision
        .is_some_and(|revision| revision != initial.revision)
    {
        return Err("Marketplace catalog revision changed; reload before retrying.".into());
    }
    let source = initial
        .sources
        .iter()
        .find(|source| source.id == request.market_id && source.enabled)
        .ok_or("An enabled marketplace source is required.")?
        .clone();
    if let Some(cursor) = request
        .cursor
        .as_deref()
        .filter(|cursor| !cursor.is_empty())
        && (source.kind != MarketKind::McpRegistry || source.next_cursor != cursor)
    {
        return Err("Use the next cursor from this marketplace's current catalog.".into());
    }
    let refreshed = async {
        let (bytes, commit) = read_source(app, &source, &request, cancel).await?;
        let (entries, cursor) = parse(&source, &bytes)?;
        Ok::<_, Box<dyn std::error::Error + Send + Sync>>((entries, cursor, digest(&bytes), commit))
    }
    .await;
    match refreshed {
        Ok((items, cursor, hash, commit)) => {
            if cancel.is_cancelled() {
                return Err("Marketplace refresh cancelled before cache commit.".into());
            }
            change(app, None, |store| {
                if store
                    .sources
                    .iter()
                    .find(|item| item.id == request.market_id)
                    != Some(&source)
                {
                    return Err(
                        "Marketplace source changed during refresh; reload before retrying.".into(),
                    );
                }
                let source = store
                    .sources
                    .iter_mut()
                    .find(|item| item.id == request.market_id)
                    .ok_or("Marketplace source was removed during refresh.")?;
                source.status = "ready".into();
                source.error.clear();
                source.content_sha256 = hash;
                source.source_commit = commit;
                source.next_cursor = cursor;
                let entries = store.entries.entry(source.id.clone()).or_default();
                if request.cursor.as_deref().unwrap_or("").is_empty() {
                    entries.clear();
                }
                for item in items {
                    if let Some(previous) = entries.iter_mut().find(|entry| entry.id == item.id) {
                        *previous = item;
                    } else {
                        entries.push(item);
                    }
                }
                entries.sort_by(|a, b| a.name.cmp(&b.name).then_with(|| a.version.cmp(&b.version)));
                source.entry_count = entries.len();
                Ok(())
            })?;
            entries(app, &request)
        }
        Err(error) => {
            if !cancel.is_cancelled() {
                let message = error.to_string();
                change(app, None, |store| {
                    if store
                        .sources
                        .iter()
                        .find(|item| item.id == request.market_id)
                        != Some(&source)
                    {
                        return Err(
                            "Marketplace source changed during refresh; reload before retrying."
                                .into(),
                        );
                    }
                    if let Some(source) = store
                        .sources
                        .iter_mut()
                        .find(|source| source.id == request.market_id)
                    {
                        source.status = if store
                            .entries
                            .get(&source.id)
                            .is_some_and(|items| !items.is_empty())
                        {
                            "cached_error"
                        } else {
                            "error"
                        }
                        .into();
                        source.error = message.clone();
                    }
                    Ok(())
                })?;
            }
            Err(error)
        }
    }
}
