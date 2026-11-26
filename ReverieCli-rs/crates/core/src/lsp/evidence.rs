use super::config::{ServerConfig, digest};
use crate::Result;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
};

pub(super) const DOCUMENT_LIMIT: usize = 4 * 1024 * 1024;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Position {
    pub line: u32,
    pub character: u32,
}
impl Position {
    pub fn from_utf8_offset(text: &str, offset: usize) -> Result<Self> {
        if offset > text.len() || !text.is_char_boundary(offset) {
            return Err("LSP position requires a valid UTF-8 character boundary.".into());
        }
        let mut start = 0;
        for (line, raw) in text.split('\n').enumerate() {
            let body = raw.strip_suffix('\r').unwrap_or(raw);
            if offset >= start && offset <= start + body.len() {
                return Ok(Self {
                    line: u32::try_from(line)?,
                    character: u32::try_from(text[start..offset].encode_utf16().count())?,
                });
            }
            start += raw.len() + 1;
        }
        Err("LSP position cannot split a CRLF newline.".into())
    }
    pub fn utf8_offset(self, text: &str) -> Result<usize> {
        let mut start = 0;
        for (line, raw) in text.split('\n').enumerate() {
            if line == self.line as usize {
                let body = raw.strip_suffix('\r').unwrap_or(raw);
                let mut column = 0;
                for (offset, character) in body.char_indices() {
                    if column == self.character {
                        return Ok(start + offset);
                    }
                    column += character.len_utf16() as u32;
                    if column > self.character {
                        return Err("LSP UTF-16 position cannot split a surrogate pair.".into());
                    }
                }
                if column == self.character {
                    return Ok(start + body.len());
                }
                return Err("LSP character position is outside its line.".into());
            }
            start += raw.len() + 1;
        }
        Err("LSP line position is outside its document.".into())
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub(super) struct Range {
    pub start: Position,
    pub end: Position,
}
impl Range {
    pub fn valid(self, text: &str) -> bool {
        self.start <= self.end
            && self.start.utf8_offset(text).is_ok()
            && self.end.utf8_offset(text).is_ok()
    }
}

pub(super) fn normalized(path: PathBuf) -> PathBuf {
    #[cfg(windows)]
    {
        let value = path.to_string_lossy();
        if let Some(value) = value.strip_prefix("\\\\?\\UNC\\") {
            return PathBuf::from(format!("\\\\{value}"));
        }
        if let Some(value) = value.strip_prefix("\\\\?\\") {
            return PathBuf::from(value);
        }
    }
    path
}

pub(super) fn checked_path(project: &Path, input: &str, must_exist: bool) -> Result<PathBuf> {
    if input.is_empty() || input.contains('\0') {
        return Err("Language-service file path is empty or invalid.".into());
    }
    let requested = if input.starts_with("file:") {
        let uri = reqwest::Url::parse(input)?;
        if !uri.username().is_empty()
            || uri.password().is_some()
            || uri.query().is_some()
            || uri.fragment().is_some()
        {
            return Err(
                "Language-service file URIs must not contain credentials, queries or fragments."
                    .into(),
            );
        }
        uri.to_file_path()
            .map_err(|_| "Language-service URI is not a local file path.")?
    } else {
        project.join(input)
    };
    let resolved = match requested.canonicalize() {
        Ok(path) => normalized(path),
        Err(error) if !must_exist && error.kind() == std::io::ErrorKind::NotFound => {
            let parent = requested
                .parent()
                .ok_or("Language-service path has no parent.")?;
            let name = requested
                .file_name()
                .ok_or("Language-service path has no file name.")?;
            normalized(parent.canonicalize()?).join(name)
        }
        Err(error) => return Err(error.into()),
    };
    if !resolved.starts_with(project) || resolved == project {
        return Err("Language-service files must remain inside their approved project.".into());
    }
    if must_exist && !resolved.is_file() {
        return Err("Language-service target must be a regular file.".into());
    }
    Ok(resolved)
}

pub(super) fn file_uri(path: &Path) -> Result<String> {
    reqwest::Url::from_file_path(path)
        .map(|uri| uri.to_string())
        .map_err(|_| "Language-service file cannot be represented as a URI.".into())
}

#[derive(Clone)]
pub(super) struct Document {
    pub uri: String,
    pub relative: String,
    pub text: String,
    pub sha256: String,
    pub version: i32,
    pub opened: bool,
}
impl Document {
    pub fn read(project: &Path, input: &str) -> Result<Self> {
        let path = checked_path(project, input, true)?;
        let mut bytes = Vec::new();
        fs::File::open(&path)?
            .take(DOCUMENT_LIMIT as u64 + 1)
            .read_to_end(&mut bytes)?;
        if bytes.len() > DOCUMENT_LIMIT {
            return Err("Language-service document exceeds 4 MiB.".into());
        }
        let sha256 = digest(&bytes);
        let text = String::from_utf8(bytes)
            .map_err(|_| "Language-service document must be valid UTF-8.")?;
        Ok(Self {
            uri: file_uri(&path)?,
            relative: path
                .strip_prefix(project)?
                .to_string_lossy()
                .replace('\\', "/"),
            text,
            sha256,
            version: 1,
            opened: false,
        })
    }
    pub fn public(&self) -> Value {
        json!({"uri":self.uri,"file_path":self.relative,"content_sha256":self.sha256,
            "document_version":self.opened.then_some(self.version),"local_revision":self.version,
            "position_encoding":"utf-16","document_sync":if self.opened{"open_document"}else{"disk_only"}})
    }
}

fn text(config: &ServerConfig, value: &Value, limit: usize) -> String {
    let value = config.redacted(value.as_str().unwrap_or(""));
    let mut result: String = value
        .chars()
        .filter(|character| !character.is_control() || matches!(character, '\n' | '\t'))
        .take(limit)
        .collect();
    if value.chars().count() > limit {
        result.push_str(" [truncated]");
    }
    result
}

pub(super) fn location(project: &Path, uri: &str, raw_range: &Value) -> Option<Value> {
    if !uri.starts_with("file:") {
        return None;
    }
    let document = Document::read(project, uri).ok()?;
    let range: Range = serde_json::from_value(raw_range.clone()).ok()?;
    if !range.valid(&document.text) {
        return None;
    }
    Some(
        json!({"uri":document.uri,"file_path":document.relative,"range":range,
        "content_sha256":document.sha256,"content_version":"observed_after_response",
        "position_encoding":"utf-16"}),
    )
}

pub(super) fn definitions(
    project: &Path,
    config: &ServerConfig,
    raw: &Value,
    limit: usize,
) -> (Vec<Value>, usize) {
    let candidates: Vec<&Value> = match raw {
        Value::Array(items) => items.iter().collect(),
        Value::Object(_) => vec![raw],
        Value::Null => Vec::new(),
        _ => return (Vec::new(), 1),
    };
    let mut result = Vec::new();
    let mut dropped = 0;
    for item in candidates {
        let uri = item["uri"]
            .as_str()
            .or_else(|| item["targetUri"].as_str())
            .unwrap_or("");
        let range = item
            .get("range")
            .or_else(|| item.get("targetSelectionRange"))
            .unwrap_or(&Value::Null);
        if let Some(mut item) = location(project, uri, range) {
            item["source"] = json!("lsp");
            item["server_id"] = json!(config.id());
            result.push(item);
            if result.len() == limit {
                break;
            }
        } else {
            dropped += 1;
        }
    }
    (result, dropped)
}

pub(super) fn symbols(
    project: &Path,
    config: &ServerConfig,
    raw: &Value,
    document: Option<&Document>,
    limit: usize,
) -> (Vec<Value>, usize) {
    let Some(items) = raw.as_array() else {
        return (Vec::new(), usize::from(!raw.is_null()));
    };
    let mut result = Vec::new();
    let mut dropped = 0;
    let mut pending: Vec<(&Value, Option<String>, usize)> =
        items.iter().rev().map(|item| (item, None, 0)).collect();
    while let Some((item, parent, depth)) = pending.pop() {
        if depth > 64 || result.len() >= limit {
            break;
        }
        let name = text(config, &item["name"], 512);
        let kind = item["kind"]
            .as_u64()
            .filter(|value| (1..=26).contains(value));
        let found = if let Some(uri) = item["location"]["uri"].as_str() {
            location(project, uri, &item["location"]["range"])
        } else if let Some(document) = document {
            let range = item
                .get("selectionRange")
                .or_else(|| item.get("range"))
                .unwrap_or(&Value::Null);
            location(project, &document.uri, range)
        } else {
            None
        };
        if !name.is_empty()
            && kind.is_some()
            && let Some(mut found) = found
        {
            found["name"] = json!(name);
            found["kind"] = json!(kind);
            found["containerName"] = json!(parent.clone().unwrap_or_else(|| text(
                config,
                &item["containerName"],
                512
            )));
            found["source"] = json!("lsp");
            found["server_id"] = json!(config.id());
            result.push(found);
        } else {
            dropped += 1;
        }
        if let Some(children) = item["children"].as_array() {
            for child in children.iter().rev() {
                pending.push((child, Some(name.clone()), depth + 1));
            }
        }
    }
    (result, dropped)
}

pub(super) fn diagnostics(
    project: &Path,
    config: &ServerConfig,
    document: &Document,
    raw: &[Value],
    limit: usize,
) -> (Vec<Value>, usize) {
    let mut result = Vec::new();
    let mut dropped = 0;
    for item in raw {
        let range: Range = match serde_json::from_value::<Range>(item["range"].clone()) {
            Ok(range) if range.valid(&document.text) => range,
            _ => {
                dropped += 1;
                continue;
            }
        };
        let mut diagnostic = json!({"source":"lsp","server_id":config.id(),
            "uri":document.uri,"file_path":document.relative,"range":range,
            "content_sha256":document.sha256,"document_version":document.opened.then_some(document.version),
            "content_version":"observed_when_diagnostic_received",
            "message":text(config,&item["message"],8192),
            "severity":item["severity"].as_u64().filter(|value|(1..=4).contains(value)),
            "diagnostic_source":text(config,&item["source"],512),"position_encoding":"utf-16"});
        if item["code"].is_number() {
            diagnostic["code"] = item["code"].clone();
        } else if item["code"].is_string() {
            diagnostic["code"] = json!(text(config, &item["code"], 512));
        }
        if let Some(related) = item["relatedInformation"].as_array() {
            diagnostic["relatedInformation"] = json!(
                related
                    .iter()
                    .take(32)
                    .filter_map(|item| {
                        let mut found = location(
                            project,
                            item["location"]["uri"].as_str()?,
                            &item["location"]["range"],
                        )?;
                        found["message"] = json!(text(config, &item["message"], 2048));
                        Some(found)
                    })
                    .collect::<Vec<_>>()
            );
        }
        result.push(diagnostic);
        if result.len() == limit {
            break;
        }
    }
    (result, dropped)
}
