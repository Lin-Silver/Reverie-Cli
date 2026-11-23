//! Offline semantic bundles. Staging does not activate or run a candidate.
use crate::Result;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::{Read, Seek, SeekFrom, Write},
    path::{Component, Path, PathBuf},
};

pub const E5_REVISION: &str = "614241f622f53c4eeff9890bdc4f31cfecc418b3";
pub const BGE_REVISION: &str = "2cfc18c9415c912f9d8155881c133215df768a70";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Asset {
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Model {
    pub id: String,
    pub revision: String,
    pub onnx: String,
    pub tokenizer_directory: String,
    pub max_length: usize,
    pub precision: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Runtime {
    pub version: String,
    pub api_version: u32,
    pub library: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: String,
    pub version: String,
    pub platform: String,
    pub architecture: String,
    pub dimensions: usize,
    pub runtime: Runtime,
    pub embedding: Model,
    pub reranker: Model,
    pub files: BTreeMap<String, Asset>,
    pub licenses: Vec<String>,
    pub provenance: serde_json::Value,
}

#[derive(Debug, Clone)]
pub struct VerifiedBundle {
    pub directory: PathBuf,
    pub digest: String,
    pub manifest: Manifest,
}

pub fn hash_file(path: &Path) -> Result<String> {
    let mut file = File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|ch| ch.is_ascii_hexdigit() && !ch.is_ascii_uppercase())
}

fn linked(metadata: &fs::Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return true;
        }
    }
    false
}

fn relative(name: &str) -> Result<&Path> {
    if name.is_empty()
        || name.contains(['\\', ':', '\0'])
        || name.split('/').any(|part| {
            part.is_empty() || part == "." || part == ".." || part.ends_with([' ', '.'])
        })
        || Path::new(name)
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(format!("Invalid resource path: {name}").into());
    }
    Ok(Path::new(name))
}

pub fn asset_path(directory: &Path, name: &str) -> Result<PathBuf> {
    let relative = relative(name)?;
    let mut current = directory.to_owned();
    for component in relative.components() {
        current.push(component.as_os_str());
        if linked(&fs::symlink_metadata(&current)?) {
            return Err(format!("Resource link is not allowed: {name}").into());
        }
    }
    if !current.is_file()
        || !current
            .canonicalize()?
            .starts_with(directory.canonicalize()?)
    {
        return Err(format!("Resource is not a contained file: {name}").into());
    }
    Ok(current)
}

fn validate_manifest(manifest: &Manifest) -> Result<()> {
    if manifest.schema != "reverie.semantic-resource.v1"
        || manifest.version.trim().is_empty()
        || manifest.platform != std::env::consts::OS
        || manifest.architecture != std::env::consts::ARCH
        || manifest.dimensions != 384
        || manifest.runtime.version != "1.31.0"
        || manifest.runtime.api_version != 24
    {
        return Err(
            "Semantic resource schema, platform, model dimensions or ORT version is incompatible."
                .into(),
        );
    }
    let mut required = vec![manifest.runtime.library.clone()];
    for (model, id, revision) in [
        (
            &manifest.embedding,
            "intfloat/multilingual-e5-small",
            E5_REVISION,
        ),
        (&manifest.reranker, "BAAI/bge-reranker-base", BGE_REVISION),
    ] {
        if model.id != id
            || model.revision != revision
            || model.max_length == 0
            || model.max_length > 512
            || !matches!(model.precision.as_str(), "fp32" | "dynamic-int8")
        {
            return Err(format!("Unsupported semantic model contract: {}", model.id).into());
        }
        required.push(model.onnx.clone());
        relative(&model.tokenizer_directory)?;
        for file in [
            "tokenizer.json",
            "config.json",
            "special_tokens_map.json",
            "tokenizer_config.json",
        ] {
            required.push(format!("{}/{file}", model.tokenizer_directory));
        }
    }
    if manifest.licenses.is_empty() || !manifest.provenance.is_object() {
        return Err(
            "Semantic resources require license assets and source/production provenance.".into(),
        );
    }
    required.extend(manifest.licenses.iter().cloned());
    if required
        .iter()
        .any(|name| !manifest.files.contains_key(name))
    {
        return Err(
            "Semantic resource manifest omits required model, tokenizer, runtime or license files."
                .into(),
        );
    }
    let mut names = BTreeSet::new();
    for (name, asset) in &manifest.files {
        relative(name)?;
        if name.eq_ignore_ascii_case("manifest.json")
            || !names.insert(name.to_lowercase())
            || asset.bytes == 0
            || !valid_digest(&asset.sha256)
        {
            return Err(format!("Invalid or colliding semantic asset: {name}").into());
        }
    }
    Ok(())
}

/// Verify only the manifest identity and contract for lightweight inventory.
/// Asset integrity and native health still require `verify` and model loading.
pub fn inspect_manifest(directory: &Path, expected_digest: &str) -> Result<Manifest> {
    if !valid_digest(expected_digest) || linked(&fs::symlink_metadata(directory)?) {
        return Err("A contained resource directory and explicit SHA-256 are required.".into());
    }
    let path = asset_path(directory, "manifest.json")?;
    if fs::metadata(&path)?.len() > 1_048_576 {
        return Err("Semantic resource manifest is too large.".into());
    }
    let bytes = fs::read(&path)?;
    let actual: String = Sha256::digest(&bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    if actual != expected_digest {
        return Err("Semantic resource manifest SHA-256 mismatch.".into());
    }
    let manifest = serde_json::from_slice(&bytes)?;
    validate_manifest(&manifest)?;
    Ok(manifest)
}

fn verify_architecture(path: &Path) -> Result<()> {
    let mut file = File::open(path)?;
    let mut header = [0u8; 64];
    file.read_exact(&mut header)?;
    let actual = if &header[..2] == b"MZ" {
        let offset = u32::from_le_bytes(header[60..64].try_into()?) as u64;
        file.seek(SeekFrom::Start(offset))?;
        let mut pe = [0u8; 6];
        file.read_exact(&mut pe)?;
        if &pe[..4] != b"PE\0\0" {
            return Err("Invalid PE runtime header.".into());
        }
        match u16::from_le_bytes(pe[4..6].try_into()?) {
            0x8664 => "x86_64",
            0xaa64 => "aarch64",
            _ => "unsupported",
        }
    } else if &header[..4] == b"\x7fELF" && header[4] == 2 && header[5] == 1 {
        match u16::from_le_bytes(header[18..20].try_into()?) {
            62 => "x86_64",
            183 => "aarch64",
            _ => "unsupported",
        }
    } else if &header[..4] == b"\xcf\xfa\xed\xfe" {
        match u32::from_le_bytes(header[4..8].try_into()?) {
            0x01000007 => "x86_64",
            0x0100000c => "aarch64",
            _ => "unsupported",
        }
    } else {
        "unsupported"
    };
    let format_matches = match std::env::consts::OS {
        "windows" => &header[..2] == b"MZ",
        "linux" => &header[..4] == b"\x7fELF",
        "macos" => &header[..4] == b"\xcf\xfa\xed\xfe",
        _ => false,
    };
    if actual != std::env::consts::ARCH || !format_matches {
        return Err("Semantic runtime binary platform or architecture is incompatible.".into());
    }
    Ok(())
}

pub fn verify(
    directory: &Path,
    expected_digest: &str,
    cancelled: &impl Fn() -> bool,
) -> Result<VerifiedBundle> {
    let manifest = inspect_manifest(directory, expected_digest)?;
    let directory = directory.canonicalize()?;
    for (name, asset) in &manifest.files {
        if cancelled() {
            return Err("Semantic resource verification cancelled.".into());
        }
        let path = asset_path(&directory, name)?;
        if fs::metadata(&path)?.len() != asset.bytes || hash_file(&path)? != asset.sha256 {
            return Err(format!("Semantic resource content mismatch: {name}").into());
        }
    }
    verify_architecture(&asset_path(&directory, &manifest.runtime.library)?)?;
    Ok(VerifiedBundle {
        directory,
        digest: expected_digest.into(),
        manifest,
    })
}

pub fn stage(
    store: &Path,
    source: &Path,
    expected_digest: &str,
    cancelled: &impl Fn() -> bool,
) -> Result<VerifiedBundle> {
    let candidate = verify(source, expected_digest, cancelled)?;
    let versions = store.join("versions");
    fs::create_dir_all(&versions)?;
    if linked(&fs::symlink_metadata(&versions)?) {
        return Err("Resource versions cannot be a link.".into());
    }
    let destination = versions.join(expected_digest);
    if destination.exists() {
        return verify(&destination, expected_digest, cancelled);
    }
    let temporary = tempfile::tempdir_in(&versions)?;
    for name in candidate
        .manifest
        .files
        .keys()
        .chain(std::iter::once(&"manifest.json".to_owned()))
    {
        if cancelled() {
            return Err("Semantic resource staging cancelled.".into());
        }
        let source_path = asset_path(&candidate.directory, name)?;
        let target = temporary.path().join(relative(name)?);
        fs::create_dir_all(target.parent().ok_or("Resource has no parent.")?)?;
        let mut input = File::open(source_path)?;
        let mut output = File::create_new(&target)?;
        std::io::copy(&mut input, &mut output)?;
        output.flush()?;
        output.sync_all()?;
    }
    verify(temporary.path(), expected_digest, cancelled)?;
    fs::rename(temporary.path(), &destination)?;
    verify(&destination, expected_digest, cancelled)
}
