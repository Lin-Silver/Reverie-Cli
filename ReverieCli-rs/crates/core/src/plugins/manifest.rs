use super::package::{Snapshot, bounded_text, checked_path, digest};
use crate::{Result, skills};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Component {
    pub kind: String,
    pub name: String,
    pub path: String,
    pub description: String,
    pub configuration: Value,
}

impl Component {
    pub fn public(&self) -> Value {
        let mut policy = policy(&self.configuration);
        if self.kind == "hook" {
            let rule = &self.configuration["rule"];
            let entries = rule["hooks"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|entry| {
                    json!({"type":entry["type"],"command":entry["command"],"prompt":entry["prompt"],
                    "timeout":entry["timeout"],"permissions":entry["permissions"],
                    "env_keys":entry["env"].as_object().map(|env|env.keys().collect::<Vec<_>>())})
                })
                .collect::<Vec<_>>();
            policy["event"] = self.configuration["event"].clone();
            policy["matcher"] = rule["matcher"].clone();
            policy["entries"] = json!(entries);
        } else if matches!(self.kind.as_str(), "mcp" | "lsp" | "runtime") {
            for key in ["type", "command", "cwd", "protocol", "capabilities"] {
                if let Some(value) = self.configuration.get(key) {
                    policy[key] = value.clone();
                }
            }
            policy["env_keys"] = json!(
                self.configuration["env"]
                    .as_object()
                    .map(|env| env.keys().collect::<Vec<_>>())
            );
            policy["header_keys"] = json!(
                self.configuration["headers"]
                    .as_object()
                    .map(|headers| headers.keys().collect::<Vec<_>>())
            );
            if let Some(url) = self.configuration["url"]
                .as_str()
                .or(self.configuration["httpUrl"].as_str())
                && let Ok(mut url) = crate::mcp::config::endpoint(url)
            {
                url.set_query(None);
                policy["url"] = json!(url.as_str());
            }
        }
        let redactor = crate::mcp::privacy::Redactor::default();
        fn secrets(value: &Value, redactor: &crate::mcp::privacy::Redactor) {
            if let Some(fields) = value.as_object() {
                for (key, value) in fields {
                    if matches!(
                        key.to_ascii_lowercase().as_str(),
                        "env"
                            | "headers"
                            | "authorization"
                            | "password"
                            | "api_key"
                            | "token"
                            | "client_secret"
                    ) {
                        if let Some(text) = value.as_str() {
                            redactor.add(text);
                        }
                        if let Some(values) = value.as_object() {
                            for text in values.values().filter_map(Value::as_str) {
                                redactor.add(text);
                            }
                        }
                    } else {
                        secrets(value, redactor);
                    }
                }
            } else if let Some(items) = value.as_array() {
                for item in items {
                    secrets(item, redactor);
                }
            }
        }
        secrets(&self.configuration, &redactor);
        let policy = redactor.value(&crate::models::without_secrets(&policy));
        json!({"kind":self.kind,"name":self.name,"path":self.path,"description":self.description,"policy":policy,"requires_platform":self.kind=="app"})
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Metadata {
    pub name: String,
    pub display_name: String,
    pub version: String,
    pub family: String,
    pub description: String,
    pub manifest_path: String,
    pub license: String,
    pub license_files: Vec<String>,
    pub components: Vec<Component>,
    pub approval_profile: Value,
}

fn string(value: &Value) -> String {
    value.as_str().unwrap_or_default().to_owned()
}
fn portable_name(value: &str) -> Result<()> {
    if value.trim().is_empty() || value.chars().any(|ch| ch.is_control()) {
        return Err(
            "Extension component needs a non-empty name without control characters.".into(),
        );
    }
    Ok(())
}
fn slash(root: &Path, path: &Path) -> Result<String> {
    Ok(path
        .strip_prefix(root)?
        .to_string_lossy()
        .replace('\\', "/"))
}
pub fn data(root: &Path, path: &str) -> Result<Value> {
    let path = checked_path(root, path)?;
    if !path.is_file() {
        return Err("Extension configuration must name a file.".into());
    }
    let bytes = bounded_text(&path, 16 * 1024 * 1024)?;
    let text = std::str::from_utf8(&bytes)?;
    match path.extension().and_then(|value| value.to_str()) {
        Some("yaml" | "yml") => Ok(serde_saphyr::from_str(text)?),
        Some("toml") => Ok(serde_json::to_value(toml::from_str::<toml::Value>(text)?)?),
        _ => Ok(serde_json::from_slice(&bytes)?),
    }
}
fn policy(configuration: &Value) -> Value {
    let mut result = serde_json::Map::new();
    for key in [
        "allowed-tools",
        "allowed_tools",
        "permissions",
        "dependencies",
        "model",
        "context",
        "include_modes",
        "exclude_modes",
        "read_only",
        "destructive",
        "timeout",
        "timeout_ms",
    ] {
        if let Some(value) = configuration.get(key) {
            result.insert(key.into(), value.clone());
        }
    }
    Value::Object(result)
}
fn markdown(root: &Path, path: &Path, kind: &str) -> Result<Component> {
    let text = String::from_utf8(bounded_text(path, 2 * 1024 * 1024)?)?;
    let (configuration, body) = skills::frontmatter(&text)?;
    if body.trim().is_empty() {
        return Err("Extension Markdown component has an empty body.".into());
    }
    let fallback = if kind == "skill" {
        path.parent().and_then(Path::file_name)
    } else {
        path.file_stem()
    }
    .and_then(|value| value.to_str())
    .unwrap_or("component");
    let name = configuration["name"]
        .as_str()
        .unwrap_or(fallback)
        .to_owned();
    portable_name(&name)?;
    Ok(Component {
        kind: kind.into(),
        name,
        path: slash(root, path)?,
        description: string(&configuration["description"]),
        configuration,
    })
}
fn markdown_paths(
    root: &Path,
    declaration: &Value,
    kind: &str,
    output: &mut Vec<Component>,
) -> Result<()> {
    if let Some(items) = declaration.as_array() {
        for item in items {
            markdown_paths(root, item, kind, output)?;
        }
        return Ok(());
    }
    let path = declaration
        .as_str()
        .or_else(|| declaration["path"].as_str())
        .ok_or("Extension Markdown declaration must name a package path.")?;
    let path = checked_path(root, path)?;
    if path.is_file() {
        output.push(markdown(root, &path, kind)?);
        return Ok(());
    }
    for entry in walkdir::WalkDir::new(path).follow_links(false) {
        let entry = entry?;
        if !entry.file_type().is_file() {
            continue;
        }
        let selected = if kind == "skill" {
            entry.file_name() == "SKILL.md"
        } else {
            entry
                .path()
                .extension()
                .is_some_and(|extension| extension == "md")
        };
        if selected {
            output.push(markdown(root, entry.path(), kind)?);
        }
    }
    Ok(())
}
fn configured(root: &Path, declaration: &Value) -> Result<(Value, String)> {
    if let Some(path) = declaration.as_str() {
        return Ok((data(root, path)?, path.into()));
    }
    if declaration.is_object() {
        return Ok((declaration.clone(), String::new()));
    }
    Err("Extension configuration must be an object or package-relative data file.".into())
}
fn configurations(
    root: &Path,
    declaration: &Value,
    kind: &str,
    output: &mut Vec<Component>,
) -> Result<()> {
    if let Some(items) = declaration.as_array() {
        for item in items {
            configurations(root, item, kind, output)?;
        }
        return Ok(());
    }
    let (document, path) = configured(root, declaration)?;
    match kind {
        "mcp" | "lsp" => {
            let entries = if kind == "mcp" {
                document
                    .get("mcpServers")
                    .or_else(|| document.get("mcp_servers"))
                    .unwrap_or(&document)
            } else {
                document.get("lspServers").unwrap_or(&document)
            };
            let entries = entries
                .as_object()
                .ok_or("Extension server configuration must be a mapping.")?;
            for (name, configuration) in entries {
                portable_name(name)?;
                if !configuration.is_object() {
                    return Err("Extension server definition must be an object.".into());
                }
                output.push(Component {
                    kind: kind.into(),
                    name: name.clone(),
                    path: path.clone(),
                    description: string(&configuration["description"]),
                    configuration: configuration.clone(),
                });
            }
        }
        "hook" => {
            let entries = document
                .get("hooks")
                .unwrap_or(&document)
                .as_object()
                .ok_or("Extension hooks must be an event mapping.")?;
            for (event, rules) in entries {
                let rules = rules
                    .as_array()
                    .ok_or("Extension hook event must contain rules.")?;
                for (index, rule) in rules.iter().enumerate() {
                    if !rule.is_object() {
                        return Err("Extension hook rule must be an object.".into());
                    }
                    output.push(Component {
                        kind: kind.into(),
                        name: format!("{event}:{index}"),
                        path: path.clone(),
                        description: event.clone(),
                        configuration: json!({"event":event,"rule":rule}),
                    });
                }
            }
        }
        _ => output.push(Component {
            kind: kind.into(),
            name: kind.into(),
            path,
            description: String::new(),
            configuration: document,
        }),
    }
    Ok(())
}
fn platform_value(value: &Value) -> Vec<String> {
    let platform = match std::env::consts::OS {
        "macos" => "darwin",
        other => other,
    };
    match value {
        Value::String(value) => vec![value.clone()],
        Value::Array(items) => items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_owned)
            .collect(),
        Value::Object(items) => items
            .get(platform)
            .or_else(|| items.get("default"))
            .map(platform_value)
            .unwrap_or_default(),
        _ => Vec::new(),
    }
}
fn compatibility(manifest: &Value) -> Result<()> {
    let compatibility = &manifest["reverie"];
    if let Some(range) = compatibility["kernel"].as_str() {
        let range = semver::VersionReq::parse(range)?;
        if !range.matches(&semver::Version::parse(reverie_protocol::VERSION)?) {
            return Err("Extension does not support this Reverie kernel version.".into());
        }
    }
    if let Some(protocol) = compatibility["protocol"].as_str()
        && !matches!(protocol, "reverie.kernel.v1" | "sdk-bridge.v1" | "1.0")
    {
        return Err("Extension requires an unsupported kernel protocol.".into());
    }
    for (field, target) in [
        ("platforms", std::env::consts::OS),
        ("architectures", std::env::consts::ARCH),
    ] {
        if let Some(values) = compatibility[field].as_array() {
            let allowed = values.iter().any(|value| {
                value.as_str().is_some_and(|value| {
                    value == target
                        || value == "all"
                        || matches!(
                            (target, value),
                            ("macos", "darwin")
                                | ("windows", "win32")
                                | ("x86_64", "x64")
                                | ("x86_64", "amd64")
                                | ("aarch64", "arm64")
                        )
                })
            });
            if !allowed {
                return Err(
                    "Extension does not support this operating system or architecture.".into(),
                );
            }
        }
    }
    Ok(())
}

pub fn inspect(root: &Path, catalog: Option<&Value>, snapshot: &Snapshot) -> Result<Metadata> {
    let root = root.canonicalize()?;
    let mut manifest_path = String::new();
    let mut manifest = None;
    for path in [
        "reverie.extension.json",
        ".claude-plugin/plugin.json",
        ".codex-plugin/plugin.json",
        ".agents-plugin/plugin.json",
        "plugin.json",
    ] {
        if root.join(path).is_file() {
            manifest = Some(data(&root, path)?);
            manifest_path = path.into();
            break;
        }
    }
    let manifest = match manifest {
        Some(manifest) => manifest,
        None if catalog.is_some_and(|catalog| catalog["strict"] == false) => {
            catalog.unwrap().clone()
        }
        None if root.join("SKILL.md").is_file() => {
            let component = markdown(&root, &root.join("SKILL.md"), "skill")?;
            json!({"name":component.name,"description":component.description,"skills":"SKILL.md"})
        }
        None => {
            return Err(
                "Extension package has no supported manifest or standalone SKILL.md.".into(),
            );
        }
    };
    if !manifest.is_object() {
        return Err("Extension manifest must be an object.".into());
    }
    compatibility(&manifest)?;
    let name = manifest["id"]
        .as_str()
        .or_else(|| manifest["name"].as_str())
        .ok_or("Extension manifest needs a name or id.")?
        .to_owned();
    portable_name(&name)?;
    if let Some(catalog) = catalog
        && catalog["strict"] != false
        && catalog["name"].as_str() != Some(name.as_str())
    {
        return Err("Extension identity does not match its marketplace entry.".into());
    }
    let mut components = Vec::new();
    for (field, kind, default) in [
        ("skills", "skill", "skills"),
        ("commands", "command", "commands"),
        ("agents", "agent", "agents"),
    ] {
        if let Some(declaration) = manifest.get(field) {
            markdown_paths(&root, declaration, kind, &mut components)?;
        } else if root.join(default).is_dir() {
            markdown_paths(&root, &json!(default), kind, &mut components)?;
        }
    }
    if let Some(catalog) = catalog.filter(|catalog| catalog["strict"] == false) {
        for (field, kind) in [
            ("skills", "skill"),
            ("commands", "command"),
            ("agents", "agent"),
        ] {
            if let Some(declaration) = catalog.get(field) {
                components.retain(|component| component.kind != kind);
                markdown_paths(&root, declaration, kind, &mut components)?;
            }
        }
    }
    for (field, kind, default) in [
        ("mcpServers", "mcp", ".mcp.json"),
        ("hooks", "hook", "hooks/hooks.json"),
        ("lspServers", "lsp", ".lsp.json"),
        ("configuration", "configuration", "config.json"),
        ("apps", "app", ".app.json"),
    ] {
        if let Some(declaration) = manifest.get(field) {
            configurations(&root, declaration, kind, &mut components)?;
        } else if root.join(default).is_file() {
            configurations(&root, &json!(default), kind, &mut components)?;
        }
    }
    if let Some(declaration) = manifest.get("components") {
        let declaration = declaration
            .as_array()
            .ok_or("Extension components must be an array.")?;
        for component in declaration {
            let kind = component["kind"]
                .as_str()
                .ok_or("Extension component has no kind.")?;
            match kind {
                "skill" | "command" | "agent" => {
                    markdown_paths(&root, &component["path"], kind, &mut components)?
                }
                "mcp" | "hook" | "lsp" | "configuration" | "app" => configurations(
                    &root,
                    component.get("configuration").unwrap_or(&component["path"]),
                    kind,
                    &mut components,
                )?,
                "runtime" => {
                    let path = component["path"]
                        .as_str()
                        .ok_or("Runtime component needs a package path.")?;
                    checked_path(&root, path)?;
                    components.push(Component {
                        kind: kind.into(),
                        name: component["name"].as_str().unwrap_or(&name).into(),
                        path: path.into(),
                        description: string(&component["description"]),
                        configuration: component.clone(),
                    });
                }
                _ => return Err(format!("Unsupported extension component kind: {kind}").into()),
            }
        }
    }
    let mut entries = Vec::new();
    if manifest["entry"].get("preferred").is_some() {
        entries.extend(platform_value(&manifest["entry"]["preferred"]));
        if manifest["entry"]["allow_source_fallback"] == true {
            entries.extend(platform_value(&manifest["entry"]["fallbacks"]));
        }
    } else {
        entries.extend(platform_value(&manifest["entry"]));
    }
    entries.extend(platform_value(&manifest["packaging"]["compiled"]));
    entries.extend(platform_value(&manifest["executable"]));
    for path in entries {
        let path = checked_path(&root, &path);
        if let Ok(path) = path
            && path.is_file()
        {
            components.push(Component {kind:"runtime".into(),name:name.clone(),path:slash(&root,&path)?,description:string(&manifest["description"]),configuration:json!({"protocol":"1.0","capabilities":manifest["capabilities"],"include_modes":manifest["include_modes"],"exclude_modes":manifest["exclude_modes"]})});
            break;
        }
    }
    let mut identities = BTreeSet::new();
    for component in &components {
        portable_name(&component.name)?;
        if !identities.insert((component.kind.clone(), component.name.clone())) {
            return Err("Extension declares duplicate component identities.".into());
        }
    }
    if components.is_empty() {
        return Err("Extension package has no usable component declarations.".into());
    }
    let license_files = snapshot
        .files
        .iter()
        .filter(|file| {
            let filename = file
                .path
                .rsplit('/')
                .next()
                .unwrap_or_default()
                .to_ascii_uppercase();
            filename.starts_with("LICENSE")
                || filename.starts_with("COPYING")
                || filename.starts_with("NOTICE")
                || filename.starts_with("THIRD-PARTY")
        })
        .map(|file| file.path.clone())
        .collect::<Vec<_>>();
    let license_hashes = snapshot
        .files
        .iter()
        .filter(|file| license_files.contains(&file.path))
        .collect::<Vec<_>>();
    let profile = json!({"name":name,"publisher":manifest["author"],"signing_key":snapshot.signing_key,"components":components.iter().map(|component|json!({"kind":component.kind,"name":component.name,"path":component.path,"policy":policy(&component.configuration),"execution":if matches!(component.kind.as_str(),"mcp"|"lsp"|"hook"|"runtime"|"configuration"){component.configuration.clone()}else{json!({})}})).collect::<Vec<_>>(),"dependencies":manifest["dependencies"],"permissions":manifest["permissions"],"license":manifest["license"],"license_files":license_hashes,"terms":manifest["interface"]["termsOfServiceURL"],"privacy":manifest["interface"]["privacyPolicyURL"]});
    Ok(Metadata {
        name: name.clone(),
        display_name: manifest["display_name"]
            .as_str()
            .or_else(|| manifest["interface"]["displayName"].as_str())
            .unwrap_or(&name)
            .into(),
        version: string(&manifest["version"]),
        family: manifest["runtime_family"]
            .as_str()
            .unwrap_or("extension")
            .into(),
        description: string(&manifest["description"]),
        manifest_path,
        license: string(&manifest["license"]),
        license_files,
        components,
        approval_profile: profile,
    })
}

pub fn approval_digest(metadata: &Metadata) -> Result<String> {
    Ok(digest(&serde_json::to_vec(&metadata.approval_profile)?))
}
pub fn component_directory(root: &Path, component: &Component) -> Result<PathBuf> {
    let path = checked_path(root, &component.path)?;
    if component.kind == "skill" && path.is_file() {
        return path
            .parent()
            .map(Path::to_path_buf)
            .ok_or_else(|| "Skill has no package directory.".into());
    }
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    #[test]
    fn common_layouts_keep_component_scopes_and_hide_server_secrets() {
        let base = std::env::current_dir()
            .unwrap()
            .join(".runtime/plugin-manifest-tests");
        fs::create_dir_all(&base).unwrap();
        let root = tempfile::tempdir_in(&base).unwrap();
        for folder in [
            ".codex-plugin",
            "skills/one",
            "skills/two",
            "commands",
            "agents",
            "hooks",
        ] {
            fs::create_dir_all(root.path().join(folder)).unwrap();
        }
        fs::write(root.path().join(".codex-plugin/plugin.json"),r#"{"name":"fixture","version":"1.0.0","license":"MIT","skills":["skills/one"],"mcpServers":".mcp.json"}"#).unwrap();
        for name in ["one", "two"] {
            fs::write(
                root.path().join(format!("skills/{name}/SKILL.md")),
                format!("---\nname: {name}\ndescription: original\n---\n完整指令\n"),
            )
            .unwrap();
        }
        fs::write(
            root.path().join("commands/review.md"),
            "---\nallowed-tools: Read\n---\nReview $ARGUMENTS",
        )
        .unwrap();
        fs::write(
            root.path().join("agents/reviewer.md"),
            "---\nname: reviewer\n---\nReview only",
        )
        .unwrap();
        fs::write(root.path().join("hooks/hooks.json"),r#"{"hooks":{"PreToolUse":[{"matcher":"Write","hooks":[{"type":"command","command":"echo hook"}]}]}}"#).unwrap();
        fs::write(
            root.path().join(".mcp.json"),
            r#"{"mcpServers":{"fixture":{"command":"fixture","env":{"SECRET":"must-not-leak"}}}}"#,
        )
        .unwrap();
        let snapshot = super::super::package::inspect(root.path(), &|| false).unwrap();
        let metadata = inspect(root.path(), None, &snapshot).unwrap();
        assert_eq!(
            metadata
                .components
                .iter()
                .filter(|component| component.kind == "skill")
                .map(|component| component.name.as_str())
                .collect::<Vec<_>>(),
            ["one"]
        );
        for kind in ["command", "agent", "hook", "mcp"] {
            assert!(
                metadata
                    .components
                    .iter()
                    .any(|component| component.kind == kind)
            );
        }
        assert!(
            !serde_json::to_string(
                &metadata
                    .components
                    .iter()
                    .map(Component::public)
                    .collect::<Vec<_>>()
            )
            .unwrap()
            .contains("must-not-leak")
        );
        let subset = inspect(
            root.path(),
            Some(&json!({"name":"subset","strict":false,"skills":["skills/two"]})),
            &snapshot,
        )
        .unwrap();
        assert_eq!(
            subset
                .components
                .iter()
                .filter(|component| component.kind == "skill")
                .map(|component| component.name.as_str())
                .collect::<Vec<_>>(),
            ["two"]
        );
    }
}
