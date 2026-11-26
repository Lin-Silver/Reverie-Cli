use crate::{Result, config::atomic_json};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    env, fs,
    io::Read,
    path::{Path, PathBuf},
};

const CONFIG_LIMIT: u64 = 16 * 1024 * 1024;
pub const PROTOCOL_VERSION: &str = "2025-06-18";
pub const DISCOVERY_TIMEOUT_MS: u64 = 15_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Transport {
    Stdio,
    Http,
    Sse,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct ServerConfig {
    pub name: String,
    pub origin: String,
    pub transport: Transport,
    pub enabled: bool,
    pub trusted: bool,
    pub command: String,
    pub args: Vec<String>,
    pub endpoint: String,
    pub cwd: String,
    pub env: BTreeMap<String, String>,
    pub headers: BTreeMap<String, String>,
    pub timeout_ms: u64,
    pub include_tools: Vec<String>,
    pub exclude_tools: Vec<String>,
    pub include_modes: Vec<String>,
    pub exclude_modes: Vec<String>,
    pub credential_ref: Option<String>,
}

pub fn hash(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn strings(value: &Value) -> Result<Vec<String>> {
    match value {
        Value::Null => Ok(Vec::new()),
        Value::Array(items) => items
            .iter()
            .map(|item| {
                let text = item.as_str().ok_or("MCP list entries must be strings.")?;
                if text.contains('\0') {
                    return Err("MCP strings must not contain NUL.".into());
                }
                Ok(text.to_owned())
            })
            .collect(),
        _ => Err("MCP configuration list must be an array.".into()),
    }
}

fn string_map(value: &Value) -> Result<BTreeMap<String, String>> {
    match value {
        Value::Null => Ok(BTreeMap::new()),
        Value::Object(items) => items
            .iter()
            .map(|(key, item)| {
                let text = item
                    .as_str()
                    .ok_or("MCP environment/header values must be strings.")?;
                if key.is_empty() || key.contains(['\0', '\r', '\n']) || text.contains('\0') {
                    return Err("Invalid MCP environment/header entry.".into());
                }
                Ok((key.clone(), text.to_owned()))
            })
            .collect(),
        _ => Err("MCP environment/headers must be an object.".into()),
    }
}

pub fn endpoint(value: &str) -> Result<reqwest::Url> {
    let url = reqwest::Url::parse(value)?;
    if !matches!(url.scheme(), "https" | "http")
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
    {
        return Err(
            "MCP endpoints require HTTP(S), without embedded credentials or fragments.".into(),
        );
    }
    Ok(url)
}

impl ServerConfig {
    pub fn parse(name: &str, origin: &str, raw: &Value) -> Result<Self> {
        if name.trim().is_empty() || name.contains(['\0', '\r', '\n']) || !raw.is_object() {
            return Err("MCP server requires a name and object configuration.".into());
        }
        let command = raw["command"].as_str().unwrap_or("").trim().to_owned();
        let url = raw["url"].as_str().unwrap_or("");
        let http_url = raw["httpUrl"].as_str().unwrap_or("");
        let transport = match raw["type"]
            .as_str()
            .unwrap_or("")
            .to_lowercase()
            .replace('-', "_")
            .as_str()
        {
            "stdio" => Transport::Stdio,
            "http" | "streamable_http" | "streamablehttp" => Transport::Http,
            "sse" | "legacy_sse" | "http_sse" => Transport::Sse,
            "" if !command.is_empty() => Transport::Stdio,
            "" if !http_url.is_empty() => Transport::Http,
            "" if !url.is_empty() => Transport::Sse,
            _ => return Err("Unsupported MCP transport; use stdio, http or sse.".into()),
        };
        let endpoint = if !http_url.is_empty() { http_url } else { url }.to_owned();
        if transport == Transport::Stdio {
            if command.is_empty() || command.contains(['\0', '\r', '\n']) {
                return Err("A stdio MCP server requires an executable command.".into());
            }
        } else {
            self::endpoint(&endpoint)?;
        }
        let timeout_ms = if raw["timeout"].is_null() {
            600_000
        } else {
            raw["timeout"]
                .as_u64()
                .or_else(|| raw["timeout"].as_str().and_then(|value| value.parse().ok()))
                .filter(|value| *value > 0 && *value <= 86_400_000)
                .ok_or("MCP timeout must be between 1 and 86400000 milliseconds.")?
        };
        Ok(Self {
            name: name.trim().into(),
            origin: origin.into(),
            transport,
            enabled: raw["enabled"].as_bool().unwrap_or(true),
            trusted: raw["trust"].as_bool().unwrap_or(false),
            command,
            args: strings(&raw["args"])?,
            endpoint,
            cwd: raw["cwd"].as_str().unwrap_or("").into(),
            env: string_map(&raw["env"])?,
            headers: string_map(&raw["headers"])?,
            timeout_ms,
            include_tools: strings(&raw["includeTools"])?,
            exclude_tools: strings(&raw["excludeTools"])?,
            include_modes: strings(&raw["includeModes"])?,
            exclude_modes: strings(&raw["excludeModes"])?,
            credential_ref: raw["credential_ref"].as_str().map(str::to_owned),
        })
    }
    pub fn id(&self) -> String {
        format!("{}:{}", self.origin, self.name)
    }
    pub fn fingerprint(&self) -> Result<String> {
        Ok(hash(&serde_json::to_vec(self)?))
    }
    pub fn tool_enabled(&self, name: &str) -> bool {
        let matches = |item: &String| item == name || item.starts_with(&format!("{name}("));
        !self.exclude_tools.iter().any(matches)
            && (self.include_tools.is_empty() || self.include_tools.iter().any(matches))
    }
    pub fn visible_in_mode(&self, mode: &str) -> bool {
        let mode = mode.to_lowercase();
        self.enabled
            && !self
                .exclude_modes
                .iter()
                .any(|item| item.eq_ignore_ascii_case(&mode))
            && (mode.is_empty()
                || self.include_modes.is_empty()
                || self
                    .include_modes
                    .iter()
                    .any(|item| item.eq_ignore_ascii_case(&mode)))
    }
    pub fn public(&self) -> Value {
        let public_endpoint = self::endpoint(&self.endpoint)
            .map(|mut url| {
                url.set_query(None);
                url.to_string()
            })
            .unwrap_or_default();
        json!({"id":self.id(),"name":self.name,"origin":self.origin,"type":self.transport,
            "enabled":self.enabled,"trust":self.trusted,"command":self.command,"args_count":self.args.len(),
            "url":public_endpoint,"cwd":self.cwd,"timeout":self.timeout_ms,
            "env_keys":self.env.keys().collect::<Vec<_>>(),"header_keys":self.headers.keys().collect::<Vec<_>>(),
            "credential_configured":self.credential_ref.is_some(),"includeTools":self.include_tools,
            "excludeTools":self.exclude_tools,"includeModes":self.include_modes,"excludeModes":self.exclude_modes})
    }
}

pub fn expand_env(value: &str, variables: &BTreeMap<String, String>) -> String {
    let mut output = String::new();
    let mut remaining = value;
    while !remaining.is_empty() {
        let ch = remaining.chars().next().unwrap();
        if ch == '$' || ch == '%' {
            let tail = &remaining[ch.len_utf8()..];
            let (name, consumed) = if ch == '%' {
                tail.find('%').map(|end| (&tail[..end], end + 2))
            } else if let Some(braced) = tail.strip_prefix('{') {
                braced.find('}').map(|end| (&braced[..end], end + 3))
            } else {
                let length = tail
                    .bytes()
                    .take_while(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
                    .count();
                (length > 0).then_some((&tail[..length], length + 1))
            }
            .unwrap_or(("", 0));
            if consumed > 0 && !name.is_empty() {
                output.push_str(
                    &variables
                        .get(name)
                        .cloned()
                        .or_else(|| env::var(name).ok())
                        .unwrap_or_default(),
                );
                remaining = &remaining[consumed..];
                continue;
            }
        }
        output.push(ch);
        remaining = &remaining[ch.len_utf8()..];
    }
    output
}

pub fn effective_servers(
    raw: &Value,
    plugins: &BTreeMap<String, Value>,
    mode: &str,
) -> Result<Vec<ServerConfig>> {
    let globals = raw
        .get("mcp")
        .filter(|value| value.is_object())
        .unwrap_or(raw);
    if globals["enabled"].as_bool() == Some(false) {
        return Ok(Vec::new());
    }
    let allowed = strings(&globals["allowed"])?;
    let excluded = strings(&globals["excluded"])?;
    let mut servers = Vec::new();
    let mut append = |origin: &str, name: &str, value: &Value| -> Result<()> {
        let server = ServerConfig::parse(name, origin, value)?;
        let named = |item: &String| {
            item.eq_ignore_ascii_case(name) || item.eq_ignore_ascii_case(&server.id())
        };
        if server.visible_in_mode(mode)
            && !excluded.iter().any(named)
            && (allowed.is_empty() || allowed.iter().any(named))
        {
            servers.push(server);
        }
        Ok(())
    };
    if let Some(entries) = raw["mcpServers"].as_object() {
        for (name, value) in entries {
            append("manual", name, value)?;
        }
    }
    for (origin, document) in plugins {
        let entries = document
            .get("mcpServers")
            .unwrap_or(document)
            .as_object()
            .ok_or("Plugin MCP configuration must be an object.")?;
        for (name, value) in entries {
            append(origin, name, value)?;
        }
    }
    Ok(servers)
}

/// Contains private configuration. Only `public` and `diagnostics` are SDK-safe.
#[derive(Clone)]
pub struct ConfigRead {
    pub document: Option<Value>,
    pub servers: Vec<ServerConfig>,
    pub diagnostics: Vec<Value>,
    pub revision: Option<u64>,
}
impl ConfigRead {
    pub fn public(&self) -> Value {
        let mut servers: Vec<_> = self.servers.iter().map(public_server).collect();
        servers.extend(
            self.diagnostics
                .iter()
                .filter(|entry| entry["scope"] == "server")
                .cloned(),
        );
        servers.sort_by(|left, right| left["id"].as_str().cmp(&right["id"].as_str()));
        json!({"revision":self.revision,"servers":servers,"diagnostics":self.diagnostics,"readable":self.document.is_some()})
    }
    /// An explicit override allows the host to apply application MCP settings.
    pub fn effective(mut self, mode: &str, global_override: Option<&Value>) -> Self {
        let Some(document) = self.document.as_ref() else {
            self.servers.clear();
            return self;
        };
        let globals = global_override.unwrap_or_else(|| document.get("mcp").unwrap_or(document));
        if !globals.is_object() {
            self.diagnostics.push(json!({"scope":"global_policy","error":"MCP global policy must be an object; no servers were activated."}));
            self.servers.clear();
            return self;
        }
        let allowed = strings(&globals["allowed"]);
        let excluded = strings(&globals["excluded"]);
        let (allowed, excluded) = match (allowed, excluded) {
            (Ok(allowed), Ok(excluded)) => (allowed, excluded),
            _ => {
                self.diagnostics.push(json!({"scope":"global_policy","error":"MCP allowed/excluded filters must be string arrays; no servers were activated."}));
                self.servers.clear();
                return self;
            }
        };
        if !globals["enabled"].is_null() && !globals["enabled"].is_boolean() {
            self.diagnostics.push(json!({"scope":"global_policy","error":"MCP enabled policy must be a boolean; no servers were activated."}));
            self.servers.clear();
            return self;
        }
        if globals["enabled"].as_bool() == Some(false) {
            self.servers.clear();
            return self;
        }
        self.servers.retain(|server| {
            let named = |item: &String| {
                item.eq_ignore_ascii_case(&server.name) || item.eq_ignore_ascii_case(&server.id())
            };
            server.visible_in_mode(mode)
                && !excluded.iter().any(named)
                && (allowed.is_empty() || allowed.iter().any(named))
        });
        self
    }
}

fn public_server(server: &ServerConfig) -> Value {
    let mut value = server.public();
    value["fingerprint"] = json!(server.fingerprint().ok());
    value["configuration_sha256"] = value["fingerprint"].clone();
    value["valid"] = json!(true);
    value
}

fn invalid_server(name: &str, origin: &str, raw: &Value, error: &str) -> Value {
    // Parser diagnostics do not include raw input. Redact reflected credentials as well.
    let mut message = error.to_owned();
    for values in [raw["env"].as_object(), raw["headers"].as_object()]
        .into_iter()
        .flatten()
    {
        for secret in values
            .values()
            .filter_map(Value::as_str)
            .filter(|secret| !secret.is_empty())
        {
            message = message.replace(secret, "[redacted]");
        }
    }
    for key in ["url", "httpUrl"] {
        if let Some(url) = raw[key].as_str()
            && let Ok(url) = reqwest::Url::parse(url)
        {
            if let Some(query) = url.query() {
                message = message.replace(query, "[redacted]");
            }
            for (_, secret) in url.query_pairs().filter(|(_, value)| !value.is_empty()) {
                message = message.replace(secret.as_ref(), "[redacted]");
            }
        }
    }
    let fingerprint = hash(&serde_json::to_vec(raw).unwrap_or_default());
    json!({"scope":"server","id":format!("{origin}:{name}"),"name":name,"origin":origin,
        "enabled":false,"valid":false,"fingerprint":fingerprint,"configuration_sha256":fingerprint,
        "fingerprint_kind":"raw_entry","error":message})
}

fn collect_configurations(document: &Value, plugins: &BTreeMap<String, Value>) -> ConfigRead {
    let mut result = ConfigRead {
        document: Some(document.clone()),
        servers: Vec::new(),
        diagnostics: Vec::new(),
        revision: Some(McpConfigStore::revision(document)),
    };
    let mut append = |origin: &str, entries: &Value| {
        let Some(entries) = entries.as_object() else {
            result.diagnostics.push(json!({"scope":"source","origin":origin,"error":"MCP server entries must be an object; this source was not activated."}));
            return;
        };
        for (name, raw) in entries {
            match ServerConfig::parse(name, origin, raw) {
                Ok(server) => result.servers.push(server),
                Err(error) => {
                    result
                        .diagnostics
                        .push(invalid_server(name, origin, raw, &error.to_string()))
                }
            }
        }
    };
    if let Some(entries) = document.get("mcpServers") {
        append("manual", entries);
    }
    for (origin, plugin) in plugins {
        append(origin, plugin.get("mcpServers").unwrap_or(plugin));
    }
    result
}

pub struct McpConfigStore {
    app: PathBuf,
}
impl McpConfigStore {
    pub fn new(app: &Path) -> Self {
        Self {
            app: app.to_owned(),
        }
    }
    pub fn path(&self) -> PathBuf {
        self.app.join(".reverie/mcp.json")
    }
    fn existing(&self) -> PathBuf {
        let path = self.path();
        let legacy = self.app.join(".Reverie/MCP.json");
        if !path.exists() && legacy.exists() {
            legacy
        } else {
            path
        }
    }
    fn bytes(&self) -> Result<Option<Vec<u8>>> {
        match fs::File::open(self.existing()) {
            Ok(file) => {
                let mut bytes = Vec::new();
                file.take(CONFIG_LIMIT + 1).read_to_end(&mut bytes)?;
                if bytes.len() as u64 > CONFIG_LIMIT {
                    return Err("MCP configuration exceeds 16 MiB.".into());
                }
                Ok(Some(bytes))
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error.into()),
        }
    }
    fn parse_document(bytes: Option<&[u8]>) -> Result<Value> {
        let Some(bytes) = bytes else {
            return Ok(json!({"mcpServers":{}}));
        };
        let value: Value =
            serde_json::from_slice(bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(bytes))?;
        if !value.is_object() {
            return Err(
                "MCP configuration must be an object; original bytes were preserved.".into(),
            );
        }
        Ok(value)
    }
    pub fn load(&self) -> Result<Value> {
        Self::parse_document(self.bytes()?.as_deref())
    }
    /// Complete management view, including disabled and out-of-mode entries.
    /// Malformed documents/entries are diagnostics, not an empty successful config.
    pub fn read_all(&self, plugins: &BTreeMap<String, Value>) -> Result<ConfigRead> {
        match self.load() {
            Ok(document) => Ok(collect_configurations(&document, plugins)),
            Err(error) => {
                let position = error
                    .downcast_ref::<serde_json::Error>()
                    .map(|error| json!({"line":error.line(),"column":error.column()}));
                Ok(ConfigRead {
                    document: None,
                    servers: Vec::new(),
                    diagnostics: vec![
                        json!({"scope":"document","error":error.to_string(),"position":position,"original_preserved":true}),
                    ],
                    revision: None,
                })
            }
        }
    }
    pub fn read_effective(
        &self,
        plugins: &BTreeMap<String, Value>,
        mode: &str,
    ) -> Result<ConfigRead> {
        Ok(self.read_all(plugins)?.effective(mode, None))
    }
    pub fn revision(value: &Value) -> u64 {
        value["_reverie"]["revision"].as_u64().unwrap_or(0)
    }
    pub fn public(&self, document: &Value) -> Value {
        let mut value = collect_configurations(document, &BTreeMap::new()).public();
        value["path"] = json!(self.existing());
        value
    }
    pub fn public_read(&self, read: &ConfigRead) -> Value {
        let mut value = read.public();
        value["path"] = json!(self.existing());
        value
    }
    pub fn update(
        &self,
        expected: Option<u64>,
        edit: impl FnOnce(&mut Value) -> Result<()>,
    ) -> Result<Value> {
        let directory = self.app.join(".reverie");
        fs::create_dir_all(&directory)?;
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(directory.join("mcp.lock"))?;
        match lock.try_lock() {
            Ok(()) => {}
            Err(fs::TryLockError::WouldBlock) => {
                return Err(
                    "MCP configuration is busy; retry after the active update finishes.".into(),
                );
            }
            Err(fs::TryLockError::Error(error)) => return Err(error.into()),
        }
        let original = self.bytes()?;
        let mut document = Self::parse_document(original.as_deref())?;
        let revision = Self::revision(&document);
        if expected.is_some_and(|expected| expected != revision) {
            return Err("MCP configuration changed; reload before retrying.".into());
        }
        edit(&mut document)?;
        if !document.is_object() {
            return Err("MCP update must preserve the configuration object.".into());
        }
        if self.bytes()? != original {
            return Err("MCP configuration bytes changed; reload before retrying.".into());
        }
        if let Some(bytes) = original {
            let backup = directory.join("backups/mcp");
            fs::create_dir_all(&backup)?;
            let target = backup.join(format!("{}.json", hash(&bytes)));
            if !target.exists() {
                fs::write(target, bytes)?;
            }
        }
        if document["_reverie"].is_null() {
            document["_reverie"] = json!({});
        }
        if !document["_reverie"].is_object() {
            return Err("Unsupported MCP metadata; original bytes were preserved.".into());
        }
        document["_reverie"]["revision"] =
            json!(revision.checked_add(1).ok_or("MCP revision overflow.")?);
        atomic_json(&self.path(), &document)?;
        Ok(document)
    }
    pub fn upsert(&self, name: &str, value: Value, expected: Option<u64>) -> Result<Value> {
        ServerConfig::parse(name, "manual", &value)?;
        self.update(expected, |document| {
            if document.get("mcpServers").is_none() {
                document["mcpServers"] = json!({});
            }
            if !document["mcpServers"].is_object() {
                return Err("MCP server table is invalid; unrelated data was preserved.".into());
            }
            document["mcpServers"][name] = value;
            Ok(())
        })
    }
    pub fn remove(&self, name: &str, expected: Option<u64>) -> Result<Value> {
        self.update(expected, |document| {
            document["mcpServers"]
                .as_object_mut()
                .ok_or("MCP server was not found.")?
                .remove(name)
                .ok_or("MCP server was not found.")?;
            Ok(())
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn management_keeps_all_fingerprints_and_invalid_rows_without_secrets() {
        let directory = tempfile::tempdir().unwrap();
        let store = McpConfigStore::new(directory.path());
        fs::create_dir_all(directory.path().join(".reverie")).unwrap();
        let raw = json!({"mcpServers":{
            "disabled":{"command":"node","enabled":false},
            "writer":{"command":"node","includeModes":["writer"]},
            "invalid":{"type":"unsupported","url":"https://example.invalid/mcp?token=query-private-needle","env":{"TOKEN":"env-private-needle"},"headers":{"authorization":"Bearer header-private-needle"}}
        },"unrelated":{"keep":true}});
        fs::write(store.path(), serde_json::to_vec(&raw).unwrap()).unwrap();
        let all = store.read_all(&BTreeMap::new()).unwrap();
        assert_eq!(all.servers.len(), 2);
        assert_eq!(all.diagnostics.len(), 1);
        let public = store.public_read(&all);
        assert_eq!(public["servers"].as_array().unwrap().len(), 3);
        for row in public["servers"].as_array().unwrap() {
            assert_eq!(row["fingerprint"].as_str().unwrap().len(), 64);
        }
        assert!(!public.to_string().contains("env-private-needle"));
        assert!(!public.to_string().contains("header-private-needle"));
        assert!(!public.to_string().contains("query-private-needle"));
        let effective = store.read_effective(&BTreeMap::new(), "atlas").unwrap();
        assert!(effective.servers.is_empty());
        assert_eq!(effective.diagnostics.len(), 1);
        assert_eq!(
            store
                .read_effective(&BTreeMap::new(), "writer")
                .unwrap()
                .servers
                .len(),
            1
        );
        let blocked = all
            .clone()
            .effective("writer", Some(&json!({"enabled":false})));
        assert!(blocked.servers.is_empty());
        assert_eq!(all.servers.len(), 2);
        let malformed = all.effective("writer", Some(&json!({"allowed":"not-an-array"})));
        assert!(malformed.servers.is_empty());
        assert_eq!(malformed.diagnostics.len(), 2);
    }
    #[test]
    fn a_bad_neighbor_does_not_prevent_targeted_repair_or_removal() {
        let directory = tempfile::tempdir().unwrap();
        let store = McpConfigStore::new(directory.path());
        fs::create_dir_all(directory.path().join(".reverie")).unwrap();
        let bytes=b"{\"mcpServers\":{\"bad\":7,\"another-bad\":{\"type\":\"invalid\"}},\"private-unrelated\":{\"keep\":true}}\n";
        fs::write(store.path(), bytes).unwrap();
        let updated = store
            .upsert("healthy", json!({"command":"node"}), Some(0))
            .unwrap();
        assert_eq!(updated["mcpServers"]["bad"], 7);
        assert_eq!(updated["private-unrelated"]["keep"], true);
        assert_eq!(
            fs::read(
                directory
                    .path()
                    .join(".reverie/backups/mcp")
                    .join(format!("{}.json", hash(bytes)))
            )
            .unwrap(),
            bytes
        );
        let removed = store.remove("bad", Some(1)).unwrap();
        assert!(removed["mcpServers"].get("bad").is_none());
        assert_eq!(removed["mcpServers"]["another-bad"]["type"], "invalid");
        assert_eq!(
            store.read_all(&BTreeMap::new()).unwrap().diagnostics.len(),
            1
        );
    }
    #[test]
    fn whole_document_corruption_and_bad_tables_are_preserved() {
        let directory = tempfile::tempdir().unwrap();
        let store = McpConfigStore::new(directory.path());
        fs::create_dir_all(directory.path().join(".Reverie")).unwrap();
        let legacy = directory.path().join(".Reverie/MCP.json");
        let original = b"{\"mcpServers\":\n";
        fs::write(&legacy, original).unwrap();
        let read = store.read_all(&BTreeMap::new()).unwrap();
        assert!(read.document.is_none());
        assert_eq!(read.revision, None);
        assert!(read.diagnostics[0]["position"]["line"].as_u64().unwrap() > 0);
        assert_eq!(store.public_read(&read)["path"], json!(store.existing()));
        assert!(
            store
                .upsert("new", json!({"command":"node"}), None)
                .is_err()
        );
        assert!(store.remove("new", None).is_err());
        assert_eq!(fs::read(&legacy).unwrap(), original);
        fs::write(&legacy, b"{\"mcpServers\":[\"preserve\"],\"unknown\":true}").unwrap();
        assert!(
            store
                .upsert("new", json!({"command":"node"}), None)
                .is_err()
        );
        assert_eq!(store.load().unwrap()["mcpServers"], json!(["preserve"]));
    }
    #[test]
    fn config_lock_is_busy_immediately_and_external_edits_are_not_overwritten() {
        let directory = tempfile::tempdir().unwrap();
        let store = McpConfigStore::new(directory.path());
        store
            .upsert("fixture", json!({"command":"node"}), None)
            .unwrap();
        let file = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(directory.path().join(".reverie/mcp.lock"))
            .unwrap();
        file.lock().unwrap();
        let start = std::time::Instant::now();
        assert!(
            store
                .remove("fixture", None)
                .unwrap_err()
                .to_string()
                .contains("busy")
        );
        assert!(start.elapsed() < std::time::Duration::from_secs(1));
        drop(file);
        let external = b"{\"mcpServers\":{},\"external\":\"preserved\"}";
        assert!(
            store
                .update(None, |document| {
                    fs::write(store.path(), external)?;
                    document["internal"] = json!(true);
                    Ok(())
                })
                .is_err()
        );
        assert_eq!(fs::read(store.path()).unwrap(), external);
    }
    #[test]
    fn preserves_arguments_filters_namespaces_and_configuration_bytes() {
        let directory = tempfile::tempdir().unwrap();
        let store = McpConfigStore::new(directory.path());
        fs::create_dir_all(directory.path().join(".Reverie")).unwrap();
        let original = b"{\"mcpServers\":{},\"unrelated\":{\"preserve\":true}}\n";
        fs::write(directory.path().join(".Reverie/MCP.json"), original).unwrap();
        let configuration = json!({"command":"node","args":["a","a"],"env":{"MCP_EXAMPLE":"value"},"excludeTools":["delete"],"includeModes":["writer"]});
        let updated = store
            .upsert("fixture", configuration.clone(), Some(0))
            .unwrap();
        let plugins = BTreeMap::from([(
            "plugin:fixture".into(),
            json!({"mcpServers":{"fixture":configuration}}),
        )]);
        let effective = effective_servers(&updated, &plugins, "writer").unwrap();
        assert_eq!(effective.len(), 2);
        assert_ne!(effective[0].id(), effective[1].id());
        assert_eq!(effective[0].args, ["a", "a"]);
        assert!(!effective[0].tool_enabled("delete"));
        assert!(
            effective_servers(&updated, &plugins, "atlas")
                .unwrap()
                .is_empty()
        );
        assert!(store.remove("fixture", Some(0)).is_err());
        assert_eq!(
            fs::read(
                directory
                    .path()
                    .join(".reverie/backups/mcp")
                    .join(format!("{}.json", hash(original)))
            )
            .unwrap(),
            original
        );
        assert!(
            store
                .public(&updated)
                .to_string()
                .find("\"value\"")
                .is_none()
        );
        assert_eq!(
            expand_env(
                "${MCP_EXAMPLE}:%MCP_EXAMPLE%:$MCP_EXAMPLE",
                &BTreeMap::from([("MCP_EXAMPLE".into(), "value".into())])
            ),
            "value:value:value"
        );
    }
}
