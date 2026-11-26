use crate::Result;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    any::Any,
    collections::BTreeMap,
    env, fs,
    io::Read,
    path::{Path, PathBuf},
    sync::Arc,
};

#[derive(Clone)]
pub struct ServerConfig {
    pub name: String,
    pub origin: String,
    /// Approved plugin/content revision; an empty value uses the configuration hash.
    pub source_version: String,
    pub enabled: bool,
    pub trusted: bool,
    pub command: String,
    pub args: Vec<String>,
    pub cwd: String,
    pub env: BTreeMap<String, String>,
    pub extension_to_language: BTreeMap<String, String>,
    pub initialization_options: Value,
    pub settings: Value,
    pub startup_timeout_ms: u64,
    pub request_timeout_ms: u64,
    pub shutdown_timeout_ms: u64,
    /// The host can retain its PluginLease here without coupling the LSP adapter to it.
    pub owner: Option<Arc<dyn Any + Send + Sync>>,
}

pub(super) fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn strings(raw: &Value) -> Result<Vec<String>> {
    if raw.is_null() {
        return Ok(Vec::new());
    }
    raw.as_array()
        .ok_or("Language-server arguments must be an array.")?
        .iter()
        .map(|item| {
            let value = item
                .as_str()
                .ok_or("Language-server arguments must be strings.")?;
            if value.contains('\0') {
                return Err("Language-server arguments must not contain NUL.".into());
            }
            Ok(value.into())
        })
        .collect()
}

fn string_map(raw: &Value) -> Result<BTreeMap<String, String>> {
    if raw.is_null() {
        return Ok(BTreeMap::new());
    }
    raw.as_object()
        .ok_or("Language-server environment must be an object.")?
        .iter()
        .map(|(name, item)| {
            let value = item
                .as_str()
                .ok_or("Language-server environment values must be strings.")?;
            if name.is_empty() || name.contains(['\0', '\r', '\n', '=']) || value.contains('\0') {
                return Err("Invalid language-server environment entry.".into());
            }
            Ok((name.clone(), value.into()))
        })
        .collect()
}

fn duration(raw: &Value, key: &str, default: u64) -> Result<u64> {
    if raw[key].is_null() {
        return Ok(default);
    }
    raw[key]
        .as_u64()
        .filter(|value| *value > 0 && *value <= 120_000)
        .ok_or_else(|| "Language-server timeouts must be 1..120000 milliseconds.".into())
}

fn language_map(raw: &Value) -> Result<BTreeMap<String, String>> {
    let mut result = BTreeMap::new();
    if let Some(mapping) = raw
        .get("extensionToLanguage")
        .filter(|value| !value.is_null())
    {
        for (extension, value) in mapping
            .as_object()
            .ok_or("extensionToLanguage must be an object.")?
        {
            result.insert(
                extension.to_lowercase(),
                value
                    .as_str()
                    .ok_or("Language IDs must be strings.")?
                    .to_owned(),
            );
        }
    }
    if !raw["extensions"].is_null() {
        let language = raw["language_id"]
            .as_str()
            .or_else(|| raw["languageId"].as_str())
            .ok_or("An extensions list requires an explicit language_id.")?;
        for extension in strings(&raw["extensions"])? {
            let extension = extension.to_lowercase();
            if result
                .get(&extension)
                .is_some_and(|existing| existing != language)
            {
                return Err("Conflicting language IDs for the same extension.".into());
            }
            result.insert(extension, language.into());
        }
    }
    if result.iter().any(|(extension, language)| {
        !extension.starts_with('.')
            || extension.len() < 2
            || extension.len() > 64
            || extension.contains(['/', '\\', '\0', '*', '?', ':'])
            || language.trim().is_empty()
            || language.contains(['\0', '\r', '\n'])
    }) {
        return Err(
            "Language mappings require literal dot extensions and nonempty language IDs.".into(),
        );
    }
    Ok(result)
}

impl ServerConfig {
    /// Parsing is not approval. The caller must assign enabled/trusted separately.
    pub fn parse(name: &str, origin: &str, raw: &Value) -> Result<Self> {
        if name.trim().is_empty()
            || origin.trim().is_empty()
            || name.contains(['\0', '\r', '\n'])
            || origin.contains(['\0', '\r', '\n'])
            || !raw.is_object()
        {
            return Err("Language-server configuration requires a name, origin and object.".into());
        }
        let command = raw["command"].as_str().unwrap_or("").trim();
        if command.is_empty() || command.contains(['\0', '\r', '\n']) {
            return Err("Language server requires an executable command.".into());
        }
        for key in ["transport", "type"] {
            if let Some(value) = raw[key].as_str()
                && !value.eq_ignore_ascii_case("stdio")
            {
                return Err("This language-service adapter supports stdio transport only.".into());
            }
        }
        let cwd = raw["cwd"].as_str().unwrap_or("");
        if cwd.contains('\0') {
            return Err("Language-server working directory must not contain NUL.".into());
        }
        let settings = raw.get("settings").cloned().unwrap_or(Value::Null);
        if !settings.is_null() && !settings.is_object() {
            return Err("Language-server settings must be an object.".into());
        }
        Ok(Self {
            name: name.trim().into(),
            origin: origin.trim().into(),
            source_version: String::new(),
            enabled: false,
            trusted: false,
            command: command.into(),
            args: strings(&raw["args"])?,
            cwd: cwd.into(),
            env: string_map(&raw["env"])?,
            extension_to_language: language_map(raw)?,
            initialization_options: raw
                .get("initializationOptions")
                .cloned()
                .unwrap_or(Value::Null),
            settings,
            startup_timeout_ms: duration(raw, "startup_timeout_ms", 12_000)?,
            request_timeout_ms: duration(raw, "request_timeout_ms", 8_000)?,
            shutdown_timeout_ms: duration(raw, "shutdown_timeout_ms", 2_000)?,
            owner: None,
        })
    }
    pub fn id(&self) -> String {
        format!("{}:{}", self.origin, self.name)
    }
    pub fn fingerprint(&self) -> Result<String> {
        Ok(digest(&serde_json::to_vec(&json!({
            "name":self.name,"origin":self.origin,"source_version":self.source_version,
            "enabled":self.enabled,"trusted":self.trusted,"command":self.command,
            "args":self.args,"cwd":self.cwd,"env":self.env,
            "extensionToLanguage":self.extension_to_language,
            "initializationOptions":self.initialization_options,"settings":self.settings,
            "startup_timeout_ms":self.startup_timeout_ms,
            "request_timeout_ms":self.request_timeout_ms,
            "shutdown_timeout_ms":self.shutdown_timeout_ms
        }))?))
    }
    pub fn language(&self, path: &Path) -> Option<&str> {
        let suffix = format!(".{}", path.extension()?.to_str()?.to_lowercase());
        self.extension_to_language.get(&suffix).map(String::as_str)
    }
    pub(super) fn redacted(&self, text: &str) -> String {
        let mut result = text.to_owned();
        let mut secrets: Vec<_> = self.env.values().filter(|value| value.len() >= 4).collect();
        secrets.sort_by_key(|value| std::cmp::Reverse(value.len()));
        for value in secrets {
            result = result.replace(value, "[redacted]");
        }
        result
    }
    pub(super) fn working_directory(&self, project: &Path) -> Result<PathBuf> {
        if self.cwd.is_empty() {
            return Ok(project.to_owned());
        }
        let configured = PathBuf::from(&self.cwd);
        let directory = crate::config::canonical_project(&project.join(configured))?;
        if !directory.starts_with(project) {
            return Err("Language-server working directory must remain inside its project.".into());
        }
        Ok(directory)
    }
    pub(super) fn executable(&self, project: &Path) -> Result<Option<PathBuf>> {
        let requested = Path::new(&self.command);
        let found = if requested.is_absolute() || requested.components().count() > 1 {
            let path = self.working_directory(project)?.join(requested);
            path.is_file().then_some(path)
        } else {
            let search = self
                .environment("PATH")
                .map(std::ffi::OsString::from)
                .or_else(|| env::var_os("PATH"));
            let mut found = None;
            if let Some(search) = search {
                for directory in env::split_paths(&search) {
                    let directory = self.working_directory(project)?.join(directory);
                    let path = directory.join(requested);
                    if path.is_file() {
                        found = Some(path);
                        break;
                    }
                    #[cfg(windows)]
                    if requested.extension().is_none() {
                        let extensions = self
                            .environment("PATHEXT")
                            .cloned()
                            .or_else(|| env::var("PATHEXT").ok())
                            .unwrap_or(".COM;.EXE;.BAT;.CMD".into());
                        for extension in
                            extensions.split(';').filter(|value| value.starts_with('.'))
                        {
                            let candidate = directory.join(format!("{}{extension}", self.command));
                            if candidate.is_file() {
                                found = Some(candidate);
                                break;
                            }
                        }
                    }
                    if found.is_some() {
                        break;
                    }
                }
            }
            found
        };
        found
            .map(|path| path.canonicalize().map_err(Into::into))
            .transpose()
    }
    fn environment(&self, name: &str) -> Option<&String> {
        self.env
            .iter()
            .find(|(key, _)| {
                if cfg!(windows) {
                    key.eq_ignore_ascii_case(name)
                } else {
                    key.as_str() == name
                }
            })
            .map(|(_, value)| value)
    }
}

pub fn builtin_definitions() -> Vec<ServerConfig> {
    [
        ("python", "python", vec![".py", ".pyi", ".pyw"], vec!["pyright-langserver", "--stdio"]),
        ("python-pylsp", "python", vec![".py", ".pyi", ".pyw"], vec!["pylsp"]),
        ("typescript", "typescript", vec![".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"], vec!["typescript-language-server", "--stdio"]),
        ("go", "go", vec![".go"], vec!["gopls"]),
        ("rust", "rust", vec![".rs"], vec!["rust-analyzer"]),
        ("cpp", "cpp", vec![".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"], vec!["clangd", "--stdio"]),
    ].into_iter().map(|(name, language, extensions, command)| {
        ServerConfig::parse(name, "builtin", &json!({"command":command[0],"args":&command[1..],"extensions":extensions,"language_id":language})).expect("Static language-server definitions are valid.")
    }).collect()
}

/// The caller owns approval and updates. No process is created by this read.
pub fn load_manual(project: &Path) -> Result<Vec<ServerConfig>> {
    let project = crate::config::canonical_project(project)?;
    let path = project.join(".reverie/lsp.json");
    if !path.exists() {
        return Ok(Vec::new());
    }
    let path = super::evidence::checked_path(&project, ".reverie/lsp.json", true)?;
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(4 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 4 * 1024 * 1024 {
        return Err("Language-server configuration exceeds 4 MiB.".into());
    }
    let document: Value = serde_json::from_slice(&bytes)?;
    let entries = document
        .get("lspServers")
        .or_else(|| document.get("lsp_servers"))
        .unwrap_or(&document);
    entries
        .as_object()
        .ok_or("Language-server configuration must be a mapping.")?
        .iter()
        .map(|(name, raw)| ServerConfig::parse(name, "manual", raw))
        .collect()
}
