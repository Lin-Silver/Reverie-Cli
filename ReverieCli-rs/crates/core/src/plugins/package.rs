use crate::Result;
use base64::{Engine, engine::general_purpose::STANDARD};
use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
};
use unicode_normalization::UnicodeNormalization;

pub const MAX_PACKAGE_BYTES: u64 = 8 * 1024 * 1024 * 1024;
const MAX_FILES: usize = 100_000;
const INTEGRITY: &str = "reverie.integrity.json";
const SIGNATURE: &str = "reverie.integrity.sig";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileDigest {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snapshot {
    pub sha256: String,
    pub bytes: u64,
    pub files: Vec<FileDigest>,
    pub signing_key: Option<String>,
}

pub fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn valid_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

pub fn relative(value: &str) -> Result<PathBuf> {
    let mut path = PathBuf::new();
    if value.starts_with(['/', '\\']) || value.chars().any(|ch| ch.is_control()) {
        return Err("Extension paths must stay inside the package.".into());
    }
    for part in value.split(['/', '\\']) {
        if part.is_empty() || part == "." {
            continue;
        }
        let stem = part
            .split('.')
            .next()
            .unwrap_or_default()
            .to_ascii_uppercase();
        if part == ".."
            || part.contains([':', '<', '>', '"', '|', '?', '*'])
            || part.ends_with(['.', ' '])
            || matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
            || (1..=9).any(|index| stem == format!("COM{index}") || stem == format!("LPT{index}"))
        {
            return Err(
                "Extension path is unsafe or incompatible with the target file systems.".into(),
            );
        }
        path.push(part);
    }
    Ok(path)
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

pub fn managed_directory(base: &Path, suffix: &str) -> Result<PathBuf> {
    let canonical = base.canonicalize()?;
    if !canonical.is_dir() {
        return Err("Extension store root must be a directory.".into());
    }
    let mut current = canonical.clone();
    for part in relative(suffix)?.components() {
        current.push(part.as_os_str());
        match fs::symlink_metadata(&current) {
            Ok(metadata) if linked(&metadata) || !metadata.is_dir() => {
                return Err(
                    "Extension store contains a link or non-directory; it was preserved.".into(),
                );
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => fs::create_dir(&current)?,
            Err(error) => return Err(error.into()),
        }
        if !current.canonicalize()?.starts_with(&canonical) {
            return Err("Extension store path escaped its root.".into());
        }
    }
    Ok(current)
}

pub fn checked_path(root: &Path, value: &str) -> Result<PathBuf> {
    let root = root.canonicalize()?;
    let path = root.join(relative(value)?);
    let resolved = path.canonicalize()?;
    if !resolved.starts_with(&root) {
        return Err("Extension component escapes its package.".into());
    }
    let mut current = root;
    let suffix = path.strip_prefix(&current)?.to_path_buf();
    for part in suffix.components() {
        current.push(part.as_os_str());
        if linked(&fs::symlink_metadata(&current)?) {
            return Err("Extension links require a materialized package before activation.".into());
        }
    }
    Ok(resolved)
}

fn executable(metadata: &fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        let _ = metadata;
        false
    }
}

fn hash_file(path: &Path, maximum: u64, cancelled: &impl Fn() -> bool) -> Result<(String, u64)> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 65_536];
    let mut bytes = 0u64;
    loop {
        if cancelled() {
            return Err("Extension verification cancelled.".into());
        }
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes = bytes
            .checked_add(count as u64)
            .ok_or("Extension size overflow.")?;
        if bytes > maximum {
            return Err("Extension package exceeds the size limit.".into());
        }
        hasher.update(&buffer[..count]);
    }
    Ok((
        hasher
            .finalize()
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect(),
        bytes,
    ))
}

pub fn inspect(root: &Path, cancelled: &impl Fn() -> bool) -> Result<Snapshot> {
    let root = root.canonicalize()?;
    let mut files = Vec::new();
    let mut aliases = BTreeSet::new();
    let mut total = 0u64;
    for entry in walkdir::WalkDir::new(&root)
        .follow_links(false)
        .into_iter()
        .filter_entry(|entry| !matches!(entry.file_name().to_str(), Some(".git" | ".hg" | ".svn")))
    {
        if cancelled() {
            return Err("Extension verification cancelled.".into());
        }
        let entry = entry?;
        if entry.path() == root {
            continue;
        }
        let path = entry
            .path()
            .strip_prefix(&root)?
            .to_string_lossy()
            .replace('\\', "/");
        relative(&path)?;
        let metadata = fs::symlink_metadata(entry.path())?;
        if linked(&metadata) {
            return Err("Extension package contains a link; materialize its in-package target before import.".into());
        }
        if metadata.is_dir() {
            continue;
        }
        if !metadata.is_file() {
            return Err("Extension package contains a special file.".into());
        }
        let alias = caseless::default_case_fold_str(&path.nfc().collect::<String>());
        if !aliases.insert(alias) {
            return Err("Extension paths collide on a supported file system.".into());
        }
        if files.len() >= MAX_FILES {
            return Err("Extension package contains too many files.".into());
        }
        let (sha256, bytes) = hash_file(entry.path(), MAX_PACKAGE_BYTES - total, cancelled)?;
        total += bytes;
        files.push(FileDigest {
            path,
            bytes,
            sha256,
        });
    }
    if files.is_empty() {
        return Err("Extension package is empty.".into());
    }
    files.sort_by(|a, b| a.path.cmp(&b.path));
    let signing_key = signature(&root, &files)?;
    let sha256 = digest(&serde_json::to_vec(&files)?);
    Ok(Snapshot {
        sha256,
        bytes: total,
        files,
        signing_key,
    })
}

fn signature(root: &Path, files: &[FileDigest]) -> Result<Option<String>> {
    let expected = files
        .iter()
        .filter(|file| !matches!(file.path.as_str(), INTEGRITY | SIGNATURE))
        .cloned()
        .collect::<Vec<_>>();
    if !root.join(INTEGRITY).exists() {
        if root.join(SIGNATURE).exists() {
            return Err("Extension signature has no content manifest.".into());
        }
        return Ok(None);
    }
    let bytes = bounded_text(&root.join(INTEGRITY), 16 * 1024 * 1024)?;
    let manifest: serde_json::Value = serde_json::from_slice(&bytes)?;
    if manifest["schema"] != "reverie.extension-integrity.v1" {
        return Err("Unsupported extension integrity schema.".into());
    }
    let declared: Vec<FileDigest> = serde_json::from_value(manifest["files"].clone())?;
    if declared != expected {
        return Err(
            "Extension file hashes, sizes or inventory do not match their integrity manifest."
                .into(),
        );
    }
    if !root.join(SIGNATURE).exists() {
        return Ok(None);
    }
    let signature: serde_json::Value =
        serde_json::from_slice(&bounded_text(&root.join(SIGNATURE), 65_536)?)?;
    if signature["schema"] != "reverie.extension-signature.v1"
        || signature["algorithm"] != "ed25519"
    {
        return Err("Unsupported publisher signature; verification cannot be downgraded.".into());
    }
    let key = STANDARD.decode(
        signature["public_key"]
            .as_str()
            .ok_or("Publisher public key is missing.")?,
    )?;
    let key: [u8; 32] = key
        .try_into()
        .map_err(|_| "Publisher key must be 32 bytes.")?;
    let value = STANDARD.decode(
        signature["signature"]
            .as_str()
            .ok_or("Publisher signature is missing.")?,
    )?;
    let value =
        Signature::from_slice(&value).map_err(|_| "Publisher signature must be 64 bytes.")?;
    VerifyingKey::from_bytes(&key)
        .map_err(|_| "Invalid publisher key.")?
        .verify_strict(&bytes, &value)
        .map_err(|_| "Invalid publisher signature; extension was rejected.")?;
    Ok(Some(STANDARD.encode(key)))
}

pub fn bounded_text(path: &Path, maximum: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(maximum + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > maximum {
        return Err("Extension manifest exceeds its size limit.".into());
    }
    Ok(bytes)
}

pub fn copy_directory(
    source: &Path,
    destination: &Path,
    cancelled: &impl Fn() -> bool,
) -> Result<Snapshot> {
    let source = source.canonicalize()?;
    let before = inspect(&source, cancelled)?;
    for item in &before.files {
        if cancelled() {
            return Err("Extension import cancelled.".into());
        }
        let source_path = checked_path(&source, &item.path)?;
        let target = destination.join(relative(&item.path)?);
        let parent = target.parent().ok_or("Extension file has no parent.")?;
        managed_directory(
            destination,
            &parent.strip_prefix(destination)?.to_string_lossy(),
        )?;
        let mut input = fs::File::open(source_path)?;
        let source_executable = executable(&input.metadata()?);
        let mut output = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&target)?;
        let mut buffer = [0u8; 65_536];
        let mut copied = 0u64;
        loop {
            if cancelled() {
                return Err("Extension import cancelled.".into());
            }
            let count = input.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            copied += count as u64;
            if copied > item.bytes {
                return Err(
                    "Extension source grew during import; no version was activated.".into(),
                );
            }
            output.write_all(&buffer[..count])?;
        }
        output.sync_all()?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(
                &target,
                fs::Permissions::from_mode(if source_executable { 0o755 } else { 0o644 }),
            )?;
        }
        #[cfg(not(unix))]
        let _ = source_executable;
    }
    let after = inspect(destination, cancelled)?;
    if before.sha256 != after.sha256 || before.sha256 != inspect(&source, cancelled)?.sha256 {
        return Err("Extension source changed during import; no version was activated.".into());
    }
    Ok(after)
}

pub fn extract_zip(
    archive: &Path,
    destination: &Path,
    cancelled: &impl Fn() -> bool,
) -> Result<Snapshot> {
    let mut archive = zip::ZipArchive::new(fs::File::open(archive)?)?;
    if archive.len() > MAX_FILES {
        return Err("Extension archive contains too many entries.".into());
    }
    let mut total = 0u64;
    for index in 0..archive.len() {
        if cancelled() {
            return Err("Extension extraction cancelled.".into());
        }
        let mut entry = archive.by_index(index)?;
        let path = relative(entry.name())?;
        if entry.is_symlink() {
            return Err(
                "Extension archive contains a link; import materialized in-package files.".into(),
            );
        }
        if entry.is_dir() {
            managed_directory(destination, &path.to_string_lossy())?;
            continue;
        }
        if path.as_os_str().is_empty() {
            return Err("Extension archive has an empty file path.".into());
        }
        let target = destination.join(path);
        managed_directory(
            destination,
            &target
                .parent()
                .ok_or("Extension archive file has no parent.")?
                .strip_prefix(destination)?
                .to_string_lossy(),
        )?;
        let mut output = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&target)?;
        let mut buffer = [0u8; 65_536];
        loop {
            if cancelled() {
                return Err("Extension extraction cancelled.".into());
            }
            let count = entry.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            total = total
                .checked_add(count as u64)
                .ok_or("Extension size overflow.")?;
            if total > MAX_PACKAGE_BYTES {
                return Err("Extension archive exceeds the expansion limit.".into());
            }
            output.write_all(&buffer[..count])?;
        }
        output.sync_all()?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(
                &target,
                fs::Permissions::from_mode(if entry.unix_mode().unwrap_or(0) & 0o111 != 0 {
                    0o755
                } else {
                    0o644
                }),
            )?;
        }
    }
    inspect(destination, cancelled)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};
    use serde_json::json;
    fn temporary() -> tempfile::TempDir {
        let directory = std::env::current_dir()
            .unwrap()
            .join(".runtime/plugin-tests");
        fs::create_dir_all(&directory).unwrap();
        tempfile::tempdir_in(directory).unwrap()
    }
    #[test]
    fn paths_inventory_and_copy_preserve_package_bytes_and_reject_aliases() {
        for path in [
            "../outside",
            "C:/outside",
            "a\\..\\b",
            "/root",
            "a:stream",
            "CON",
            "x/NUL.txt",
        ] {
            assert!(relative(path).is_err(), "{path}");
        }
        let source = temporary();
        let target = temporary();
        fs::write(source.path().join("SKILL.md"), "许可明确的原文\r\n").unwrap();
        let snapshot = copy_directory(source.path(), target.path(), &|| false).unwrap();
        assert_eq!(snapshot.files.len(), 1);
        assert_eq!(
            fs::read(source.path().join("SKILL.md")).unwrap(),
            fs::read(target.path().join("SKILL.md")).unwrap()
        );
        assert!(inspect(target.path(), &|| true).is_err());
        assert_eq!(
            caseless::default_case_fold_str("SKILL.md"),
            caseless::default_case_fold_str("skill.MD")
        );
    }
    #[test]
    fn publisher_signature_binds_complete_inventory_and_rejects_tampering() {
        let root = temporary();
        fs::write(root.path().join("plugin.json"), r#"{"name":"fixture"}"#).unwrap();
        let files = inspect(root.path(), &|| false).unwrap().files;
        let bytes =
            serde_json::to_vec(&json!({"schema":"reverie.extension-integrity.v1","files":files}))
                .unwrap();
        fs::write(root.path().join(INTEGRITY), &bytes).unwrap();
        let key = SigningKey::from_bytes(&[19; 32]);
        let signature = key.sign(&bytes);
        fs::write(root.path().join(SIGNATURE),serde_json::to_vec(&json!({"schema":"reverie.extension-signature.v1","algorithm":"ed25519","public_key":STANDARD.encode(key.verifying_key().as_bytes()),"signature":STANDARD.encode(signature.to_bytes())})).unwrap()).unwrap();
        assert_eq!(
            inspect(root.path(), &|| false).unwrap().signing_key,
            Some(STANDARD.encode(key.verifying_key().as_bytes()))
        );
        fs::write(root.path().join("plugin.json"), r#"{"name":"changed"}"#).unwrap();
        assert!(inspect(root.path(), &|| false).is_err());
        fs::write(root.path().join("plugin.json"), r#"{"name":"fixture"}"#).unwrap();
        let mut altered = signature.to_bytes();
        altered[63] ^= 1;
        fs::write(root.path().join(SIGNATURE),serde_json::to_vec(&json!({"schema":"reverie.extension-signature.v1","algorithm":"ed25519","public_key":STANDARD.encode(key.verifying_key().as_bytes()),"signature":STANDARD.encode(altered)})).unwrap()).unwrap();
        assert!(
            inspect(root.path(), &|| false)
                .unwrap_err()
                .to_string()
                .contains("Invalid publisher signature")
        );
    }
    #[test]
    fn real_zip_extraction_preserves_bytes_and_rejects_traversal_and_aliases() {
        let root = temporary();
        for (label, names, rejected) in [
            ("valid", vec!["skills/read/SKILL.md"], false),
            ("traversal", vec!["../outside"], true),
            ("alias", vec!["SKILL.md", "skill.MD"], true),
        ] {
            let archive = root.path().join(format!("{label}.zip"));
            let mut writer = zip::ZipWriter::new(fs::File::create(&archive).unwrap());
            for name in names {
                writer
                    .start_file(name, zip::write::SimpleFileOptions::default())
                    .unwrap();
                writer.write_all("真实导入\r\n".as_bytes()).unwrap();
            }
            writer.finish().unwrap();
            let target = temporary();
            let result = extract_zip(&archive, target.path(), &|| false);
            assert_eq!(result.is_err(), rejected, "{label}");
            if !rejected {
                assert_eq!(
                    fs::read(target.path().join("skills/read/SKILL.md")).unwrap(),
                    "真实导入\r\n".as_bytes()
                );
            }
            assert!(!root.path().join("outside").exists());
        }
    }
}
