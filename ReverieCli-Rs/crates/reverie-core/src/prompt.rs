use crate::{ReverieError, ReverieResult};
use encoding_rs::{GB18030, UTF_16BE, UTF_16LE, UTF_8};
use std::io::Read;
use std::path::{Path, PathBuf};

pub fn decode_prompt_bytes(data: &[u8]) -> String {
    let decoded = if data.starts_with(&[0xff, 0xfe]) {
        let (cow, _, _) = UTF_16LE.decode(&data[2..]);
        cow.into_owned()
    } else if data.starts_with(&[0xfe, 0xff]) {
        let (cow, _, _) = UTF_16BE.decode(&data[2..]);
        cow.into_owned()
    } else {
        let (utf8, _, had_utf8_errors) = UTF_8.decode(data);
        if !had_utf8_errors {
            utf8.into_owned()
        } else {
            let (gb, _, had_gb_errors) = GB18030.decode(data);
            if !had_gb_errors {
                gb.into_owned()
            } else {
                String::from_utf8_lossy(data).into_owned()
            }
        }
    };
    decoded.replace("\r\n", "\n").replace('\r', "\n")
}

pub fn resolve_prompt_file_path(path_value: &str, project_root: &Path) -> PathBuf {
    let raw = PathBuf::from(path_value.trim());
    if raw.is_absolute() {
        return raw;
    }
    let cwd_candidate = std::env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(&raw);
    let project_candidate = project_root.join(&raw);
    if cwd_candidate.exists() || !project_candidate.exists() {
        cwd_candidate
    } else {
        project_candidate
    }
}

pub fn read_prompt_file(path_value: &str, project_root: &Path) -> ReverieResult<String> {
    let path = resolve_prompt_file_path(path_value, project_root);
    let data = std::fs::read(path)?;
    Ok(decode_prompt_bytes(&data))
}

pub fn read_prompt_stdin() -> ReverieResult<String> {
    let mut data = Vec::new();
    std::io::stdin().read_to_end(&mut data)?;
    Ok(decode_prompt_bytes(&data))
}

pub fn resolve_prompt_text(
    prompt: Option<&str>,
    prompt_file: Option<&str>,
    prompt_stdin: bool,
    project_root: &Path,
) -> ReverieResult<Option<String>> {
    if let Some(path) = prompt_file {
        return Ok(Some(read_prompt_file(path, project_root)?));
    }
    if prompt_stdin {
        return Ok(Some(read_prompt_stdin()?));
    }
    let Some(prompt) = prompt else {
        return Ok(None);
    };
    if prompt == "-" {
        return Ok(Some(read_prompt_stdin()?));
    }
    if let Some(file_ref) = prompt.strip_prefix('@') {
        if !file_ref.is_empty() {
            let path = resolve_prompt_file_path(file_ref, project_root);
            if path.is_file() {
                return Ok(Some(decode_prompt_bytes(&std::fs::read(path)?)));
            }
        }
    }
    if prompt.trim().is_empty() {
        return Err(ReverieError::InvalidInput("prompt is empty".to_string()));
    }
    Ok(Some(prompt.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_utf16_and_normalizes_newlines() {
        let bytes = [0xff, 0xfe, b'a', 0, b'\r', 0, b'\n', 0, b'b', 0];
        assert_eq!(decode_prompt_bytes(&bytes), "a\nb");
    }
}
