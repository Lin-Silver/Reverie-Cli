use crate::Result;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
};
use unicode_normalization::UnicodeNormalization;

pub(crate) mod aio;
mod atlas;
mod writer;
pub(crate) mod wstyle;

pub fn normalize(value: &str) -> Result<&'static str> {
    match value.trim().to_lowercase().as_str() {
        "reverie" | "default" => Ok("reverie"),
        "atlas" | "reverie-atlas" | "deeper" | "reverie deeper" | "reverie-deeper" => {
            Ok("reverie-atlas")
        }
        "writer" => Ok("writer"),
        "aio"
        | "all in one"
        | "computer"
        | "computer-controller"
        | "computer controller"
        | "computer-control"
        | "computer control"
        | "computer-controler"
        | "computer controler" => Ok("aio"),
        "gamer" | "reverie-gamer" => Ok("reverie-gamer"),
        "spec-driven" | "reverie-spec-driven" | "spec driven" => Err(
            "This retired mode was absorbed by reverie-atlas; choose that mode explicitly.".into(),
        ),
        "spec-vibe" | "spec vibe" | "reverie-ant" | "ant" => {
            Err("This retired mode was absorbed by reverie; choose that mode explicitly.".into())
        }
        _ => Err("Unknown Reverie mode.".into()),
    }
}

pub fn definitions(mode: &str) -> Vec<Value> {
    match mode {
        "reverie-atlas" => vec![atlas::definition()],
        "writer" => vec![writer::definition()],
        _ => vec![],
    }
}

pub fn guidance(mode: &str, root: &Path, configuration: &Value) -> Result<String> {
    match mode {
        "reverie" => Ok(String::new()),
        "reverie-atlas" => atlas::guidance(root, configuration),
        "writer" => writer::guidance(root),
        _ => Err("This mode's full workflow has not yet been migrated.".into()),
    }
}

pub fn is_read_only(name: &str, args: &Value) -> Option<bool> {
    match name {
        "atlas_delivery_orchestrator" => Some(args["action"] == "assess_completion"),
        "serial_novel" | "novel_project" | "story_project" | "longform_writer" => {
            Some(["status", "context", "audit", "list_projects"].contains(&text(args, "action")))
        }
        _ => None,
    }
}

pub fn execute(name: &str, args: &Value, root: &Path, wstyle: &Value) -> Result<Option<Value>> {
    match name {
        "atlas_delivery_orchestrator" => atlas::execute(args, root).map(Some),
        "serial_novel" | "novel_project" | "story_project" | "longform_writer" => {
            writer::execute(args, root, wstyle).map(Some)
        }
        _ => Ok(None),
    }
}

pub fn infer_writer_binding(root: &Path) -> Result<Option<Value>> {
    writer::infer_binding(root)
}
pub fn writer_style(
    app: &Path,
    root: &Path,
    configuration: &Value,
    binding: Option<&Value>,
) -> Result<(String, Value)> {
    wstyle::request(app, root, configuration, binding, false)
}
pub fn writer_binding(root: &Path, result: &Value) -> Result<Option<Value>> {
    let state = result.get("project").unwrap_or(result);
    let Some(path) = state["project_dir"].as_str() else {
        return Ok(None);
    };
    Ok(Some(writer::binding_value(
        root,
        &safe_path(root, path)?,
        text(state, "novel_id"),
    )?))
}

fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn safe_path(root: &Path, value: &str) -> Result<PathBuf> {
    let requested = Path::new(value);
    let relative = if requested.is_absolute() {
        requested
            .strip_prefix(root)
            .map_err(|_| "Mode artifact path is outside the workspace.")?
    } else {
        requested
    };
    if relative.as_os_str().is_empty()
        || relative
            .components()
            .any(|part| !matches!(part, Component::Normal(_) | Component::CurDir))
    {
        return Err("Mode artifact paths must be relative and stay within the workspace.".into());
    }
    let mut path = root.to_path_buf();
    for part in relative.components() {
        path.push(part.as_os_str());
        match fs::symlink_metadata(&path) {
            Ok(metadata) => {
                #[cfg(windows)]
                let linked = {
                    use std::os::windows::fs::MetadataExt;
                    metadata.file_attributes() & 0x400 != 0
                };
                #[cfg(not(windows))]
                let linked = metadata.file_type().is_symlink();
                if linked {
                    return Err(
                        "Mode artifact paths cannot traverse links or reparse points.".into(),
                    );
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(path)
}

fn read_bytes(path: &Path, limit: u64) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(limit + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit {
        return Err("Mode artifact exceeds its bounded read budget.".into());
    }
    Ok(bytes)
}

fn read_json(path: &Path) -> Result<Value> {
    let bytes = read_bytes(path, 16 * 1024 * 1024)?;
    let text = std::str::from_utf8(&bytes)?.trim_start_matches('\u{feff}');
    let value: Value = serde_json::from_str(text)?;
    if !value.is_object() {
        return Err("Mode state must be an object; original data was preserved.".into());
    }
    Ok(value)
}

fn write_bytes(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or("Mode artifact has no parent directory.")?;
    fs::create_dir_all(parent)?;
    if path.is_file() {
        let original = fs::read(path)?;
        if original == bytes {
            return Ok(());
        }
        let backup_directory = safe_path(parent, ".reverie-mode-backups")?;
        fs::create_dir_all(&backup_directory)?;
        let backup = safe_path(
            &backup_directory,
            &format!(
                "{}-{}",
                path.file_name().unwrap_or_default().to_string_lossy(),
                digest(&original)
            ),
        )?;
        if !backup.exists() {
            let mut temporary = tempfile::NamedTempFile::new_in(&backup_directory)?;
            temporary.write_all(&original)?;
            temporary.as_file().sync_all()?;
            temporary
                .persist_noclobber(&backup)
                .map_err(|error| error.error)?;
        }
    }
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    temporary.write_all(bytes)?;
    temporary.as_file().sync_all()?;
    if path.is_file() {
        temporary
            .as_file()
            .set_permissions(path.metadata()?.permissions())?;
    }
    temporary.persist(path).map_err(|error| error.error)?;
    Ok(())
}

fn write_json(path: &Path, value: &Value) -> Result<()> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    write_bytes(path, &bytes)
}

fn lock(path: &Path) -> Result<fs::File> {
    fs::create_dir_all(path.parent().ok_or("Mode lock has no parent.")?)?;
    let file = fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;
    file.try_lock()
        .map_err(|error| format!("Mode state is busy or cannot be locked: {error}"))?;
    Ok(file)
}

fn text<'a>(value: &'a Value, key: &str) -> &'a str {
    value[key].as_str().unwrap_or("").trim()
}
fn strings(value: &Value, key: &str) -> Result<Vec<String>> {
    match value.get(key) {
        None | Some(Value::Null) => Ok(vec![]),
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| {
                item.as_str()
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_owned)
                    .ok_or_else(|| "Mode list fields require nonempty strings.".into())
            })
            .collect(),
        _ => Err("Mode list fields require arrays of strings.".into()),
    }
}

fn portable_id(value: &str) -> Result<()> {
    if value.is_empty()
        || value.chars().count() > 80
        || value.nfc().ne(value.chars())
        || value
            .chars()
            .any(|ch| !(ch.is_alphanumeric() || ch == '-' || ch == '_'))
    {
        return Err(
            "Mode identifiers require 1–80 letters, digits, hyphens or underscores.".into(),
        );
    }
    let lower = caseless::default_case_fold_str(value);
    if matches!(lower.as_str(), "con" | "prn" | "aux" | "nul")
        || ["com", "lpt"].iter().any(|prefix| {
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "¹", "²", "³"]
                .iter()
                .any(|suffix| lower == format!("{prefix}{suffix}"))
        })
    {
        return Err("Mode identifier is a reserved Windows filename.".into());
    }
    Ok(())
}

fn object_result(value: Value) -> Result<Value> {
    Ok(json!({"success":true,"output":serde_json::to_string_pretty(&value)?,"data":value}))
}

struct StrictValue(Value);

impl<'de> serde::Deserialize<'de> for StrictValue {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = StrictValue;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("JSON-compatible data with unique string mapping keys")
            }
            fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }
            fn visit_bool<E: serde::de::Error>(
                self,
                value: bool,
            ) -> std::result::Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_i64<E: serde::de::Error>(
                self,
                value: i64,
            ) -> std::result::Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_u64<E: serde::de::Error>(
                self,
                value: u64,
            ) -> std::result::Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_f64<E: serde::de::Error>(
                self,
                value: f64,
            ) -> std::result::Result<Self::Value, E> {
                serde_json::Number::from_f64(value)
                    .map(|number| StrictValue(Value::Number(number)))
                    .ok_or_else(|| E::custom("Nonfinite numbers are not supported."))
            }
            fn visit_str<E: serde::de::Error>(
                self,
                value: &str,
            ) -> std::result::Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_string<E: serde::de::Error>(
                self,
                value: String,
            ) -> std::result::Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut sequence: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut values = vec![];
                while let Some(StrictValue(value)) = sequence.next_element()? {
                    values.push(value);
                }
                Ok(StrictValue(json!(values)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut mapping: A,
            ) -> std::result::Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some(StrictValue(key)) = mapping.next_key()? {
                    let key = key
                        .as_str()
                        .ok_or_else(|| serde::de::Error::custom("Mapping keys must be strings."))?;
                    if values.contains_key(key) {
                        return Err(serde::de::Error::custom("Duplicate mapping key."));
                    }
                    let StrictValue(value) = mapping.next_value()?;
                    values.insert(key.to_owned(), value);
                }
                Ok(StrictValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(Visitor)
    }
}

fn strict_json(value: &str) -> Result<Value> {
    Ok(serde_json::from_str::<StrictValue>(value)?.0)
}

fn bounded_yaml(value: &str) -> Result<Value> {
    let mut budget = serde_saphyr::Budget::default();
    budget.max_aliases = 0;
    budget.max_events = 4096;
    budget.max_depth = 16;
    let mut options = serde_saphyr::Options::default();
    options.budget = Some(budget);
    options.duplicate_keys = serde_saphyr::DuplicateKeyPolicy::Error;
    options.reject_unsupported_tags = true;
    Ok(serde_saphyr::from_str_with_options::<StrictValue>(value, options)?.0)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mode_lock_reports_busy_and_can_be_reacquired_after_release() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("native.lock");
        let held = lock(&path).unwrap();
        assert!(lock(&path).unwrap_err().to_string().contains("busy"));
        drop(held);
        lock(&path).unwrap();
    }

    #[test]
    fn aliases_paths_and_original_bytes_are_preserved() {
        assert_eq!(normalize("Computer Controler").unwrap(), "aio");
        assert_eq!(normalize("reverie deeper").unwrap(), "reverie-atlas");
        assert!(normalize("ant").is_err());
        let root = tempfile::tempdir().unwrap();
        assert!(safe_path(root.path(), "../outside").is_err());
        let path = safe_path(root.path(), "artifacts/test.txt").unwrap();
        write_bytes(&path, b"original\r\n").unwrap();
        write_bytes(&path, b"new\n").unwrap();
        let backup = path.parent().unwrap().join(".reverie-mode-backups");
        assert_eq!(
            fs::read(
                fs::read_dir(backup)
                    .unwrap()
                    .next()
                    .unwrap()
                    .unwrap()
                    .path()
            )
            .unwrap(),
            b"original\r\n"
        );
    }
}
