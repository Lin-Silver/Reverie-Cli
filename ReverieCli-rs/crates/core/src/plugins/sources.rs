use super::{PluginStore, manifest, package, store::Version};
use crate::{Result, markets};
use reverie_protocol::{MarketKind, PluginSourceKind, PreparePluginRequest};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
};
use tokio_util::sync::CancellationToken;

fn canonical(path: &str) -> Result<PathBuf> {
    if path.contains('\0') {
        return Err("Extension source path contains NUL.".into());
    }
    Ok(Path::new(path).canonicalize()?)
}
async fn cancelled_lock(path: &Path, cancel: &CancellationToken) -> Result<fs::File> {
    let lock = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(path)?;
    loop {
        match lock.try_lock() {
            Ok(()) => return Ok(lock),
            Err(fs::TryLockError::WouldBlock) => tokio::select! {
                _ = cancel.cancelled() => return Err("Extension source acquisition cancelled.".into()),
                _ = tokio::time::sleep(std::time::Duration::from_millis(20)) => {},
            },
            Err(error) => return Err(error.into()),
        }
    }
}
async fn git_package(
    app: &Path,
    location: &str,
    revision: Option<&str>,
    subdirectory: &str,
    destination: &Path,
    temporary: &Path,
    cancel: &CancellationToken,
) -> Result<String> {
    let location = markets::validate_location(MarketKind::Git, location)?;
    let repository = package::managed_directory(
        app,
        &format!(
            ".reverie/extensions/markets/repos/{}",
            package::digest(location.as_bytes())
        ),
    )?;
    let _lock = cancelled_lock(&repository.join("refresh.lock"), cancel).await?;
    let directory = crate::config::canonical_project(&repository)?
        .to_string_lossy()
        .into_owned();
    if !repository.join("HEAD").is_file() {
        markets::git(&["init".into(), "--bare".into(), directory.clone()], cancel).await?;
    }
    let revision = revision.unwrap_or("HEAD");
    if revision.is_empty() || revision.starts_with('-') || revision.contains(['\0', '\r', '\n']) {
        return Err("Supply a valid Git revision.".into());
    }
    let fixed = revision.len() == 40 && revision.bytes().all(|byte| byte.is_ascii_hexdigit());
    let commit = if fixed
        && markets::git(
            &[
                "-C".into(),
                directory.clone(),
                "cat-file".into(),
                "-e".into(),
                format!("{revision}^{{commit}}"),
            ],
            cancel,
        )
        .await
        .is_ok()
    {
        revision.to_lowercase()
    } else {
        markets::git(
            &[
                "-C".into(),
                directory.clone(),
                "fetch".into(),
                "--depth=1".into(),
                "--no-tags".into(),
                location,
                revision.into(),
            ],
            cancel,
        )
        .await?;
        let commit = String::from_utf8(
            markets::git(
                &[
                    "-C".into(),
                    directory.clone(),
                    "rev-parse".into(),
                    "FETCH_HEAD^{commit}".into(),
                ],
                cancel,
            )
            .await?,
        )?
        .trim()
        .to_lowercase();
        if fixed && commit != revision.to_lowercase() {
            return Err("Git source does not match the requested commit.".into());
        }
        commit
    };
    if commit.len() != 40 || !commit.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("Git did not resolve a fixed content identity.".into());
    }
    let path = package::relative(subdirectory)?;
    let tree = if path.as_os_str().is_empty() {
        commit.clone()
    } else {
        format!("{commit}:{}", path.to_string_lossy().replace('\\', "/"))
    };
    let inventory = markets::git(
        &[
            "-C".into(),
            directory.clone(),
            "ls-tree".into(),
            "-rl".into(),
            tree.clone(),
        ],
        cancel,
    )
    .await?;
    let inventory = std::str::from_utf8(&inventory)?;
    let mut bytes = 0u64;
    let mut count = 0usize;
    for line in inventory.lines() {
        let header = line
            .split('\t')
            .next()
            .unwrap_or_default()
            .split_whitespace()
            .collect::<Vec<_>>();
        if header.get(1) != Some(&"blob") {
            continue;
        }
        bytes = bytes
            .checked_add(
                header
                    .get(3)
                    .ok_or("Git tree has no size.")?
                    .parse::<u64>()?,
            )
            .ok_or("Extension size overflow.")?;
        count += 1;
        if bytes > package::MAX_PACKAGE_BYTES || count > 100_000 {
            return Err("Git extension exceeds the package limit.".into());
        }
    }
    let archive = tempfile::NamedTempFile::new_in(temporary)?.into_temp_path();
    let archive_output = crate::config::canonical_project(temporary)?
        .join(archive.file_name().ok_or("Archive has no file name.")?);
    markets::git(
        &[
            "-C".into(),
            directory,
            "archive".into(),
            "--format=zip".into(),
            format!("--output={}", archive_output.display()),
            tree,
        ],
        cancel,
    )
    .await?;
    let destination = destination.to_owned();
    let token = cancel.clone();
    tokio::task::spawn_blocking(move || {
        package::extract_zip(&archive, &destination, &|| token.is_cancelled())
    })
    .await??;
    Ok(commit)
}
async fn archive_package(
    location: &str,
    expected: Option<&str>,
    destination: &Path,
    temporary: &Path,
    cancel: &CancellationToken,
) -> Result<(String, bool)> {
    let mut downloaded = tempfile::NamedTempFile::new_in(temporary)?;
    let mut hash = Sha256::new();
    let mut size = 0u64;
    if location.starts_with("https://") || location.starts_with("http://") {
        let location = markets::validate_location(MarketKind::Manifest, location)?;
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(1800))
            .build()?;
        let mut response = tokio::select! {_ = cancel.cancelled() => return Err("Extension download cancelled.".into()), result = client.get(location).send() => result?.error_for_status()?};
        if response
            .content_length()
            .is_some_and(|size| size > package::MAX_PACKAGE_BYTES)
        {
            return Err("Extension archive exceeds the download limit.".into());
        }
        loop {
            let chunk = tokio::select! {_ = cancel.cancelled() => return Err("Extension download cancelled.".into()), chunk = response.chunk() => chunk?};
            let Some(chunk) = chunk else {
                break;
            };
            size = size
                .checked_add(chunk.len() as u64)
                .ok_or("Extension size overflow.")?;
            if size > package::MAX_PACKAGE_BYTES {
                return Err("Extension archive exceeds the download limit.".into());
            }
            hash.update(&chunk);
            downloaded.write_all(&chunk)?;
        }
    } else {
        use std::io::Read;
        let mut input = fs::File::open(canonical(location)?)?;
        let mut buffer = [0u8; 65_536];
        loop {
            if cancel.is_cancelled() {
                return Err("Extension archive import cancelled.".into());
            }
            let count = input.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            size += count as u64;
            if size > package::MAX_PACKAGE_BYTES {
                return Err("Extension archive exceeds the import limit.".into());
            }
            hash.update(&buffer[..count]);
            downloaded.write_all(&buffer[..count])?;
        }
    }
    downloaded.as_file().sync_all()?;
    let hash = hash
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    if let Some(expected) = expected
        && (!package::valid_digest(expected) || !hash.eq_ignore_ascii_case(expected))
    {
        return Err("Extension archive SHA-256 does not match its published identity.".into());
    }
    let destination = destination.to_owned();
    let token = cancel.clone();
    tokio::task::spawn_blocking(move || {
        package::extract_zip(downloaded.path(), &destination, &|| token.is_cancelled())
    })
    .await??;
    Ok((hash, expected.is_some()))
}

impl PluginStore {
    pub async fn prepare(
        &self,
        app: &Path,
        request: PreparePluginRequest,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        let staging_root = package::managed_directory(self.root(), "staging")?;
        let staging = tempfile::tempdir_in(&staging_root)?;
        let destination = staging.path().join("package");
        fs::create_dir(&destination)?;
        let source = &request.source;
        let mut verification = "candidate_approval_required";
        let mut catalog = None;
        let origin;
        let provenance;
        match source.kind {
            PluginSourceKind::Directory => {
                let directory = canonical(
                    source
                        .location
                        .as_deref()
                        .ok_or("A local extension directory is required.")?,
                )?;
                let selected = package::checked_path(
                    &directory,
                    source.subdirectory.as_deref().unwrap_or(""),
                )?;
                let target = destination.clone();
                let token = cancel.clone();
                tokio::task::spawn_blocking(move || {
                    package::copy_directory(&selected, &target, &|| token.is_cancelled())
                })
                .await??;
                origin = json!({"kind":"directory","location":directory});
                provenance = origin.clone();
            }
            PluginSourceKind::Archive => {
                let location = source
                    .location
                    .as_deref()
                    .ok_or("An archive path or URL is required.")?;
                let (hash, verified) = archive_package(
                    location,
                    source.sha256.as_deref(),
                    &destination,
                    staging.path(),
                    cancel,
                )
                .await?;
                if verified {
                    verification = "published_sha256";
                }
                origin = json!({"kind":"archive","location":location});
                provenance = json!({"kind":"archive","location":location,"archive_sha256":hash});
            }
            PluginSourceKind::Git => {
                let location = markets::validate_location(
                    MarketKind::Git,
                    source
                        .location
                        .as_deref()
                        .ok_or("A Git source is required.")?,
                )?;
                let subdirectory = source.subdirectory.as_deref().unwrap_or("");
                let commit = git_package(
                    app,
                    &location,
                    source.revision.as_deref(),
                    subdirectory,
                    &destination,
                    staging.path(),
                    cancel,
                )
                .await?;
                verification = "fixed_git";
                origin = json!({"kind":"git","location":location,"subdirectory":subdirectory});
                provenance = json!({"kind":"git","location":location,"subdirectory":subdirectory,"commit":commit});
            }
            PluginSourceKind::Market => {
                let entry_id = source
                    .entry_id
                    .as_deref()
                    .ok_or("A marketplace entry_id is required.")?;
                let (market, entry) = markets::recorded_entry(app, entry_id)?;
                origin = json!({"kind":"market","market_id":market.id,"location":market.location,"entry_id":entry.id});
                let declaration = &entry.manifest["source"];
                let resolved = match entry.source_kind.as_str() {
                    "relative" | "local" => {
                        let path = declaration
                            .as_str()
                            .or_else(|| declaration["path"].as_str())
                            .ok_or("Marketplace package path is missing.")?;
                        if market.kind == MarketKind::Git {
                            let commit = git_package(
                                app,
                                &market.location,
                                Some(&market.source_commit),
                                path,
                                &destination,
                                staging.path(),
                                cancel,
                            )
                            .await?;
                            verification = "fixed_git";
                            json!({"kind":"git","location":market.location,"subdirectory":path,"commit":commit})
                        } else if market.kind == MarketKind::Directory {
                            let base = canonical(&market.location)?;
                            let selected = package::checked_path(&base, path)?;
                            let target = destination.clone();
                            let token = cancel.clone();
                            tokio::task::spawn_blocking(move || {
                                package::copy_directory(&selected, &target, &|| {
                                    token.is_cancelled()
                                })
                            })
                            .await??;
                            json!({"kind":"directory","location":market.location,"subdirectory":path})
                        } else {
                            return Err(
                                "A relative extension needs a Git or directory marketplace.".into(),
                            );
                        }
                    }
                    "git" | "github" | "git-subdir" => {
                        let location = if entry.source_kind == "github" {
                            format!(
                                "https://github.com/{}.git",
                                declaration["repo"]
                                    .as_str()
                                    .ok_or("GitHub extension needs a repository.")?
                            )
                        } else {
                            declaration["url"]
                                .as_str()
                                .ok_or("Git extension needs a URL.")?
                                .to_owned()
                        };
                        let location = markets::validate_location(MarketKind::Git, &location)?;
                        let subdirectory = declaration["path"].as_str().unwrap_or("");
                        let commit = git_package(
                            app,
                            &location,
                            declaration["sha"]
                                .as_str()
                                .or_else(|| declaration["ref"].as_str()),
                            subdirectory,
                            &destination,
                            staging.path(),
                            cancel,
                        )
                        .await?;
                        verification = "fixed_git";
                        json!({"kind":"git","location":location,"subdirectory":subdirectory,"commit":commit})
                    }
                    "url" | "archive" => {
                        let location = declaration["url"]
                            .as_str()
                            .ok_or("Archive extension needs a URL.")?;
                        let expected = declaration["sha256"].as_str().or(source.sha256.as_deref());
                        let (hash, verified) = archive_package(
                            location,
                            expected,
                            &destination,
                            staging.path(),
                            cancel,
                        )
                        .await?;
                        if verified {
                            verification = "published_sha256";
                        }
                        json!({"kind":"archive","location":location,"archive_sha256":hash})
                    }
                    "mcp_registry" => {
                        let remotes = entry.manifest["remotes"].as_array().ok_or("This MCP registry entry has no remote transport; select and configure its external package runtime before installing.")?;
                        let remote = if let Some(url) = source.location.as_deref() {
                            remotes.iter().find(|remote|remote["url"].as_str()==Some(url)).ok_or("The selected endpoint is absent from the fixed Registry entry.")?
                        } else if remotes.len() == 1 {
                            &remotes[0]
                        } else {
                            return Err("Choose a remote endpoint explicitly for this MCP entry with multiple transports.".into());
                        };
                        let url = remote["url"]
                            .as_str()
                            .ok_or("MCP remote endpoint is missing.")?;
                        crate::mcp::config::endpoint(url)?;
                        let transport = match remote["type"].as_str() {
                            Some("streamable-http" | "streamable_http" | "http") => "http",
                            Some("sse") => "sse",
                            _ => {
                                return Err(
                                    "MCP registry remote uses an unsupported transport.".into()
                                );
                            }
                        };
                        let mut headers = serde_json::Map::new();
                        if let Some(items) = remote["headers"].as_array() {
                            for header in items {
                                let name = header["name"]
                                    .as_str()
                                    .ok_or("MCP remote header has no name.")?;
                                headers.insert(name.into(), json!(format!("${{{name}}}")));
                            }
                        }
                        config_write(
                            &destination.join("plugin.json"),
                            &json!({"name":entry.name,"version":entry.version,"mcpServers":{"registry":{"type":transport,"url":url,"headers":headers,"enabled":true,"trust":false}},"description":entry.description,"reverie":{"protocol":"reverie.kernel.v1"}}),
                        )?;
                        json!({"kind":"mcp_registry","endpoint":url,"version":entry.version})
                    }
                    other => {
                        return Err(format!(
                            "Unsupported marketplace source {other}; no extension was activated."
                        )
                        .into());
                    }
                };
                provenance = json!({"origin":origin,"catalog_sha256":entry.catalog_sha256,"resolved":resolved});
                if entry.source_kind != "mcp_registry" {
                    catalog = Some(entry.manifest);
                }
            }
        }
        if cancel.is_cancelled() {
            return Err("Extension preparation cancelled.".into());
        }
        let target = destination.clone();
        let token = cancel.clone();
        let snapshot = tokio::task::spawn_blocking(move || {
            package::inspect(&target, &|| token.is_cancelled())
        })
        .await??;
        if matches!(source.kind, PluginSourceKind::Directory)
            && let Some(expected) = source.sha256.as_deref()
        {
            if !snapshot.sha256.eq_ignore_ascii_case(expected) {
                return Err(
                    "Extension directory does not match its expected content SHA-256.".into(),
                );
            }
            verification = "published_sha256";
        }
        if source.require_signature == Some(true) && snapshot.signing_key.is_none() {
            return Err(
                "This source requires a publisher signature; unsigned content was rejected.".into(),
            );
        }
        if let Some(expected) = source.signing_key.as_deref()
            && snapshot.signing_key.as_deref() != Some(expected)
        {
            return Err("Extension publisher signature is not bound to the expected key.".into());
        }
        let metadata = manifest::inspect(&destination, catalog.as_ref(), &snapshot)?;
        super::validate_components(&destination, &metadata)?;
        let profile = package::digest(&serde_json::to_vec(
            &json!({"origin":origin,"approval":metadata.approval_profile}),
        )?);
        let id = request.plugin_id.unwrap_or_else(|| {
            package::digest(
                &serde_json::to_vec(&json!({"origin":origin,"name":metadata.name}))
                    .expect("JSON provenance is serializable"),
            )
        });
        let version = Version {
            snapshot,
            metadata,
            source: provenance,
            source_request: request.source,
            verification: verification.into(),
            profile,
        };
        self.register(&id, version, staging, request.expected_revision)
    }
    pub async fn prepare_update(
        &self,
        app: &Path,
        id: &str,
        expected: Option<u64>,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        self.prepare(
            app,
            PreparePluginRequest {
                source: self.source_for_update(id)?,
                plugin_id: Some(id.into()),
                operation_id: None,
                expected_revision: expected,
            },
            cancel,
        )
        .await
    }
}
fn config_write(path: &Path, value: &Value) -> Result<()> {
    crate::config::atomic_json(path, value)?;
    Ok(())
}
