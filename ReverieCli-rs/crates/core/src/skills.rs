use crate::Result;
use reverie_protocol::{
    PinnedSkillsState, SkillIssue, SkillLookupOperation, SkillLookupRequest, SkillRecord,
    SkillShadow, SkillsState,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeSet, HashMap},
    fs,
    io::Read,
    path::{Component, Path, PathBuf},
};

pub const MAX_PINNED: usize = 4;
const SKIP: &[&str] = &[
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
];

pub(crate) fn tool_definition() -> Value {
    json!({
        "type":"function",
        "function":{
            "name":"skill_lookup",
            "description":"Discover installed skills, inspect all SKILL.md instruction chunks, and read packaged text references. Pinned skills are mandatory. Read until complete=true using next_body_offset. Resources remain inside the selected package; reading a skill does not authorize or execute scripts.",
            "parameters":{
                "type":"object",
                "properties":{
                    "operation":{"type":"string","enum":["list","search","inspect","read_resource"]},
                    "query":{"type":"string"},
                    "skill_name":{"type":"string"},
                    "resource_path":{"type":"string"},
                    "max_results":{"type":"integer","default":8,"minimum":1,"maximum":20},
                    "max_body_chars":{"type":"integer","default":12000,"minimum":200,"maximum":20000},
                    "body_offset":{"type":"integer","minimum":0,"default":0},
                    "force_refresh":{"type":"boolean","default":false}
                },
                "required":["operation"]
            }
        }
    })
}

struct Root {
    path: PathBuf,
    label: String,
    scope: &'static str,
}
struct Skill {
    row: SkillRecord,
    path: PathBuf,
    metadata: Value,
    hash: String,
}
pub(crate) struct SkillCatalog {
    records: Vec<Skill>,
    errors: Vec<SkillIssue>,
    shadowed: Vec<SkillShadow>,
}

pub(crate) fn normalize(value: &str) -> String {
    let mut key = String::new();
    for ch in value.trim().to_lowercase().chars() {
        if ch.is_ascii_alphanumeric() || "._-".contains(ch) {
            key.push(ch);
        } else if !key.ends_with('-') {
            key.push('-');
        }
    }
    let key = key.trim_matches(['-', '.', '_']).to_owned();
    if key.is_empty() {
        value
            .trim()
            .to_lowercase()
            .trim_matches(['-', '.', '_'])
            .to_owned()
    } else {
        key
    }
}
fn identity(path: &Path) -> String {
    let text = path.to_string_lossy().into_owned();
    if cfg!(windows) {
        text.to_lowercase()
    } else {
        text
    }
}
fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
fn frontmatter(text: &str) -> Result<(Value, &str)> {
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let Some(rest) = text
        .strip_prefix("---\r\n")
        .or_else(|| text.strip_prefix("---\n"))
    else {
        return Ok((json!({}), text));
    };
    let mut offset = 0;
    for line in rest.split_inclusive('\n') {
        if line.trim_end() == "---" {
            let value: Value = serde_saphyr::from_str(&rest[..offset])?;
            let value = if value.is_null() { json!({}) } else { value };
            if !value.is_object() {
                return Err("Skill frontmatter must be a mapping.".into());
            }
            return Ok((value, &rest[offset + line.len()..]));
        }
        offset += line.len();
    }
    Err("Skill frontmatter is missing its closing --- delimiter.".into())
}
fn summary(text: &str) -> String {
    let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if text.chars().count() <= 240 {
        text
    } else {
        format!(
            "{}...",
            text.chars().take(237).collect::<String>().trim_end()
        )
    }
}

impl SkillCatalog {
    pub fn discover(project: &Path, app: &Path, mode: &str) -> Result<Self> {
        let mut roots = Vec::new();
        if let Some(parent) = std::env::current_exe()?.parent() {
            roots.push(Root {
                path: parent.join("builtin_skills"),
                label: "builtin_skills".into(),
                scope: "Built-in",
            });
        }
        if let Some(home) = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")) {
            roots.push(Root {
                path: PathBuf::from(home).join(".agents/skills"),
                label: "~/.agents/skills".into(),
                scope: "User",
            });
        }
        for directory in ["Skills", "skills"] {
            roots.push(Root {
                path: app.join(".reverie").join(directory),
                label: format!(".reverie/{directory} (legacy)"),
                scope: "App",
            });
        }
        let mut ancestors = Vec::new();
        for ancestor in project.ancestors() {
            ancestors.push(ancestor);
            if ancestor.join(".git").exists() {
                break;
            }
        }
        roots.extend(ancestors.into_iter().rev().map(|ancestor| Root {
            path: ancestor.join(".agents/skills"),
            label: ".agents/skills".into(),
            scope: "Workspace",
        }));
        Ok(Self::scan(roots, mode))
    }

    fn scan(roots: Vec<Root>, mode: &str) -> Self {
        let mut catalog = Self {
            records: Vec::new(),
            errors: Vec::new(),
            shadowed: Vec::new(),
        };
        let mut seen_roots = BTreeSet::new();
        let mut seen_files = BTreeSet::new();
        let mut preferred: HashMap<String, SkillRecord> = HashMap::new();
        for root in roots {
            if !root.path.exists() {
                continue;
            }
            let canonical = match root.path.canonicalize() {
                Ok(path) if path.is_dir() => path,
                Ok(_) => {
                    catalog.issue(&root, &root.path, "Skill root must be a directory.");
                    continue;
                }
                Err(error) => {
                    catalog.issue(&root, &root.path, error);
                    continue;
                }
            };
            if !seen_roots.insert(identity(&canonical)) {
                continue;
            }
            let registered = if root.scope == "Built-in" {
                let result = (|| -> Result<BTreeSet<PathBuf>> {
                    let entries: Vec<String> = serde_json::from_slice(&fs::read(
                        canonical.join("reverie-builtin-skills.json"),
                    )?)?;
                    let mut paths = BTreeSet::new();
                    for entry in entries {
                        let path = Path::new(&entry);
                        if path
                            .components()
                            .any(|part| !matches!(part, Component::Normal(_)))
                            || path.file_name() != Some(std::ffi::OsStr::new("SKILL.md"))
                        {
                            return Err("Builtin skill manifest contains an invalid path.".into());
                        }
                        paths.insert(canonical.join(path));
                    }
                    Ok(paths)
                })();
                match result {
                    Ok(paths) => Some(paths),
                    Err(error) => {
                        catalog.issue(&root, &canonical, error);
                        continue;
                    }
                }
            } else {
                None
            };
            let mut walker = walkdir::WalkDir::new(&canonical)
                .follow_links(false)
                .sort_by_file_name()
                .into_iter();
            while let Some(entry) = walker.next() {
                let entry = match entry {
                    Ok(entry) => entry,
                    Err(error) => {
                        catalog.issue(&root, &canonical, error);
                        continue;
                    }
                };
                if !entry.file_type().is_dir() {
                    continue;
                }
                if entry.depth() > 0
                    && SKIP
                        .iter()
                        .any(|name| entry.file_name() == std::ffi::OsStr::new(name))
                {
                    walker.skip_current_dir();
                    continue;
                }
                let file = entry.path().join("SKILL.md");
                if !file.is_file() {
                    continue;
                }
                if registered
                    .as_ref()
                    .is_some_and(|paths| !paths.contains(&file))
                {
                    continue;
                }
                walker.skip_current_dir();
                let result = Self::load(&file, &canonical, &root);
                match result {
                    Ok(skill)
                        if skill.row.scope == "Built-in"
                            && skill.row.key == "reverie-engine"
                            && !["gamer", "reverie-gamer"].contains(&mode) => {}
                    Ok(mut skill) if seen_files.insert(identity(&skill.path)) => {
                        if let Some(winner) = preferred.get(&skill.row.key) {
                            skill.row.shadowed = true;
                            catalog.shadowed.push(SkillShadow {
                                name: skill.row.name.clone(),
                                scope: skill.row.scope.clone(),
                                root: skill.row.root.clone(),
                                path: skill.row.path.clone(),
                                winner_scope: winner.scope.clone(),
                                winner_root: winner.root.clone(),
                                winner_path: winner.path.clone(),
                                message:
                                    "A higher-precedence root already provides this skill name."
                                        .into(),
                            });
                        } else {
                            preferred.insert(skill.row.key.clone(), skill.row.clone());
                        }
                        catalog.records.push(skill);
                    }
                    Ok(_) => {}
                    Err(error) => catalog.issue(&root, &file, error),
                }
            }
        }
        catalog
    }

    fn issue(&mut self, root: &Root, path: &Path, error: impl ToString) {
        self.errors.push(SkillIssue {
            name: path
                .parent()
                .and_then(Path::file_name)
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned(),
            path: path.to_string_lossy().into_owned(),
            scope: root.scope.into(),
            root: root.label.clone(),
            message: error.to_string(),
        });
    }
    fn load(file: &Path, root_path: &Path, root: &Root) -> Result<Skill> {
        let canonical = file.canonicalize()?;
        if !canonical.starts_with(root_path) {
            return Err("Skill file leaves its registered root.".into());
        }
        let bytes = fs::read(&canonical)?;
        let raw = std::str::from_utf8(&bytes)?;
        let (metadata, body) = frontmatter(raw)?;
        let directory = canonical
            .parent()
            .ok_or("Skill package has no directory.")?;
        let fallback = directory.file_name().unwrap_or_default().to_string_lossy();
        let name = metadata["name"]
            .as_str()
            .filter(|name| !name.trim().is_empty())
            .unwrap_or(&fallback)
            .trim()
            .to_owned();
        let description = metadata["description"]
            .as_str()
            .filter(|description| !description.trim().is_empty())
            .or_else(|| {
                metadata["metadata"]["short-description"]
                    .as_str()
                    .filter(|description| !description.trim().is_empty())
            })
            .or_else(|| {
                metadata["metadata"]["short_description"]
                    .as_str()
                    .filter(|description| !description.trim().is_empty())
            })
            .map(str::trim)
            .unwrap_or_else(|| {
                body.lines()
                    .map(str::trim)
                    .find(|line| !line.is_empty() && !line.starts_with('#'))
                    .unwrap_or("No skill description provided.")
            })
            .to_owned();
        let policy = match fs::read_to_string(directory.join("agents/openai.yaml")) {
            Ok(text) => serde_saphyr::from_str::<Value>(&text)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Value::Null,
            Err(error) => return Err(error.into()),
        };
        let implicit = policy["policy"]["allow_implicit_invocation"] != false
            && !policy["policy"]["allow_implicit_invocation"]
                .as_str()
                .is_some_and(|text| text.trim().eq_ignore_ascii_case("false"));
        let key = normalize(&name);
        let key = if key.is_empty() {
            fallback.to_lowercase()
        } else {
            key
        };
        Ok(Skill {
            row: SkillRecord {
                key,
                name,
                summary: summary(&description),
                description,
                path: file.to_string_lossy().into_owned(),
                scope: root.scope.into(),
                root: root.label.clone(),
                plugin_id: String::new(),
                allow_implicit_invocation: implicit,
                pinned: false,
                shadowed: false,
            },
            path: canonical,
            metadata,
            hash: digest(&bytes),
        })
    }

    fn resolve(&self, identifier: &str) -> Option<&Skill> {
        let wanted = identifier.trim().trim_start_matches('$');
        let key = normalize(wanted);
        let canonical = Path::new(wanted).canonicalize().ok();
        self.records.iter().find(|skill| {
            canonical
                .as_ref()
                .is_some_and(|path| identity(path) == identity(&skill.path))
                || skill.row.key == key
                || skill
                    .path
                    .parent()
                    .and_then(Path::file_name)
                    .is_some_and(|name| normalize(&name.to_string_lossy()) == key)
        })
    }
    pub fn name(&self, identifier: &str) -> Option<&str> {
        self.resolve(identifier)
            .map(|skill| skill.row.name.as_str())
    }
    pub fn state(&self, mode: &str, pins: &[String]) -> SkillsState {
        let keys = pins.iter().map(|name| normalize(name)).collect::<Vec<_>>();
        let names = pins
            .iter()
            .filter_map(|name| self.name(name).map(str::to_owned))
            .collect();
        let unresolved = pins
            .iter()
            .filter(|name| self.name(name).is_none())
            .cloned()
            .collect();
        let records = self
            .records
            .iter()
            .map(|skill| {
                let mut row = skill.row.clone();
                row.pinned = keys.contains(&row.key);
                row
            })
            .collect::<Vec<_>>();
        SkillsState {
            mode: Some(mode.into()),
            count: records.len(),
            invalid_count: self.errors.len(),
            shadowed_count: self.shadowed.len(),
            records,
            pinned: PinnedSkillsState {
                max: MAX_PINNED,
                keys,
                names,
                unresolved,
            },
            errors: self.errors.clone(),
            shadowed: self.shadowed.clone(),
        }
    }
    fn body(&self, skill: &Skill) -> Result<String> {
        let bytes = fs::read(&skill.path)?;
        if digest(&bytes) != skill.hash {
            return Err("Skill changed since discovery; refresh before inspecting it.".into());
        }
        let (_, body) = frontmatter(std::str::from_utf8(&bytes)?)?;
        Ok(body.trim().to_owned())
    }
    pub fn inspect(&self, identifier: &str, pins: &[String]) -> Result<Value> {
        let skill = self.resolve(identifier).ok_or("Skill was not found.")?;
        let mut detail = serde_json::to_value(&skill.row)?;
        detail["pinned"] = json!(pins.iter().any(|name| normalize(name) == skill.row.key));
        detail["body"] = json!(self.body(skill)?);
        detail["metadata"] = skill.metadata.clone();
        detail["content_hash"] = json!(skill.hash);
        Ok(detail)
    }
    pub fn read_resource(
        &self,
        identifier: &str,
        relative: &str,
    ) -> Result<(String, PathBuf, String)> {
        let skill = self
            .resolve(identifier)
            .ok_or("A discovered local skill is required.")?;
        let relative = Path::new(relative);
        if relative.as_os_str().is_empty()
            || relative
                .components()
                .any(|part| !matches!(part, Component::Normal(_) | Component::CurDir))
        {
            return Err(
                "resource_path must identify a file inside the selected skill package.".into(),
            );
        }
        let directory = skill
            .path
            .parent()
            .ok_or("Skill package has no directory.")?;
        let target = directory.join(relative).canonicalize()?;
        if !target.starts_with(directory) || !target.is_file() {
            return Err("Resource path leaves the selected skill package.".into());
        }
        let mut bytes = Vec::new();
        fs::File::open(&target)?
            .take(2 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        if bytes.len() > 2 * 1024 * 1024 || bytes.contains(&0) {
            return Err("Skill resources must be UTF-8 text of at most 2 MiB.".into());
        }
        let hash = digest(&bytes);
        let text = String::from_utf8(bytes)?;
        Ok((
            text.strip_prefix('\u{feff}').unwrap_or(&text).to_owned(),
            target,
            hash,
        ))
    }

    pub fn lookup(&self, request: &SkillLookupRequest, pins: &[String]) -> Result<Value> {
        let limit = request.max_results.unwrap_or(8).clamp(1, 20);
        match request.operation {
            SkillLookupOperation::List | SkillLookupOperation::Search => {
                let query = request.query.as_deref().unwrap_or("").trim();
                let search = matches!(request.operation, SkillLookupOperation::Search);
                if search && query.is_empty() {
                    return Err("query is required for skill search.".into());
                }
                let mut rows = Vec::new();
                let mut errors = Vec::new();
                for skill in self.records.iter().filter(|skill| !skill.row.shadowed) {
                    let score = if search {
                        match self.body(skill) {
                            Ok(body) => score(&skill.row, &body, query),
                            Err(error) => {
                                errors.push(error.to_string());
                                continue;
                            }
                        }
                    } else {
                        0
                    };
                    if search && score == 0 {
                        continue;
                    }
                    let mut row = skill.row.clone();
                    row.pinned = pins.iter().any(|name| normalize(name) == row.key);
                    rows.push((score, row));
                }
                rows.sort_by(|(a_score, a), (b_score, b)| {
                    if search {
                        b_score
                            .cmp(a_score)
                            .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
                    } else {
                        b.pinned
                            .cmp(&a.pinned)
                            .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
                    }
                });
                let count = rows.len();
                let items = rows
                    .into_iter()
                    .take(limit)
                    .map(|(_, row)| row)
                    .collect::<Vec<_>>();
                Ok(
                    json!({"operation":request.operation,"query":query,"count":count,"invalid_count":self.errors.len(),"items":items,"pinned":pins,"errors":errors}),
                )
            }
            SkillLookupOperation::Inspect | SkillLookupOperation::ReadResource => {
                let name = request
                    .skill_name
                    .as_deref()
                    .filter(|name| !name.trim().is_empty())
                    .ok_or("skill_name is required.")?;
                let mut detail = self.inspect(name, pins)?;
                let resource = matches!(request.operation, SkillLookupOperation::ReadResource);
                let text = if resource {
                    let (text, path, hash) =
                        self.read_resource(name, request.resource_path.as_deref().unwrap_or(""))?;
                    detail["path"] = json!(path);
                    detail["resource_path"] = json!(request.resource_path);
                    detail["content_hash"] = json!(hash);
                    text
                } else {
                    detail["body"]
                        .as_str()
                        .ok_or("Skill body is missing.")?
                        .to_owned()
                };
                let offset = request.body_offset.unwrap_or(0);
                let maximum = request.max_body_chars.unwrap_or(12000).clamp(200, 20000);
                let body = text.chars().skip(offset).take(maximum).collect::<String>();
                let next = offset.saturating_add(body.chars().count());
                let total = text.chars().count();
                let complete = next >= total;
                detail["operation"] = json!(request.operation);
                detail["body"] = json!(body);
                detail["body_offset"] = json!(offset);
                detail["total_body_chars"] = json!(total);
                detail["complete"] = json!(complete);
                detail["next_body_offset"] = if complete { Value::Null } else { json!(next) };
                Ok(detail)
            }
        }
    }

    pub fn guidance(&self, pins: &[String], prompt: &str) -> Result<(String, Vec<Value>)> {
        let mut blocks = Vec::new();
        let mut loaded = Vec::new();
        for name in pins {
            let skill = self.resolve(name).ok_or_else(|| {
                format!(
                    "Required Skill '{name}' is unavailable. Restore or unpin it before running."
                )
            })?;
            let body = self.body(skill)?;
            if body.is_empty() {
                return Err(format!(
                    "Required Skill '{}' has no instructions. Restore or unpin it before running.",
                    skill.row.name
                )
                .into());
            }
            blocks.push(format!(
                "### Required Skill: {}\nSource: {}\n{body}",
                skill.row.name, skill.row.path
            ));
            loaded.push(json!({"name":skill.row.name,"sha256":digest(body.as_bytes()),"characters":body.chars().count(),"complete":true}));
        }
        let required = if blocks.is_empty() {
            String::new()
        } else {
            format!(
                "## Required Skill instructions loaded by the runtime\nFollow these user-selected workflows. Mode/tool permissions still apply.\n\n{}",
                blocks.join("\n\n")
            )
        };
        if required.chars().count() > 128000 {
            return Err("Required Skill instructions exceed the turn budget. Unpin some Skills or shorten their bodies.".into());
        }
        let mut requested = pins.to_vec();
        for name in explicit_names(prompt) {
            if !requested
                .iter()
                .any(|existing| normalize(existing) == normalize(&name))
            {
                requested.push(name);
            }
        }
        let unresolved = requested
            .iter()
            .filter(|name| self.resolve(name).is_none())
            .collect::<Vec<_>>();
        let mut records = self
            .records
            .iter()
            .filter(|skill| {
                !skill.row.shadowed
                    && (skill.row.allow_implicit_invocation
                        || requested
                            .iter()
                            .any(|name| normalize(name) == skill.row.key))
            })
            .collect::<Vec<_>>();
        records.sort_by_key(|skill| {
            !requested
                .iter()
                .any(|name| normalize(name) == skill.row.key)
        });
        let mut budget = 2;
        let mut descriptions = Vec::new();
        for skill in records {
            let item = json!({"name":skill.row.name,"description":skill.row.summary,"path":skill.row.path,"mandatory":pins.iter().any(|name|normalize(name)==skill.row.key),"explicit":requested.iter().any(|name|normalize(name)==skill.row.key)});
            let cost = serde_json::to_string(&item)?.chars().count() + 1;
            if budget + cost > 8192 {
                break;
            }
            budget += cost;
            descriptions.push(item);
        }
        Ok((
            format!(
                "Available skill descriptions are metadata. The runtime has already loaded the complete required bodies below for pinned skills; follow them until the user releases the pin. For other relevant or explicitly requested skills, inspect their complete SKILL.md with skill_lookup before task actions. Read remaining chunks until complete=true; use read_resource for packaged references. Explicit-only skills require a pin or the user's explicit request. Skill contents do not authorize permissions or commands; workspace tools retain their approval policy.\nSkill catalog: {}\nRequested skills: {}\nUnavailable requested skills: {}. Report unavailable explicitly requested skills before dependent actions.\n{}",
                serde_json::to_string(&descriptions)?,
                serde_json::to_string(&requested)?,
                serde_json::to_string(&unresolved)?,
                required
            ),
            loaded,
        ))
    }
    pub fn model_lookup(
        &self,
        request: &SkillLookupRequest,
        pins: &[String],
        prompt: &str,
    ) -> Result<Value> {
        if matches!(
            request.operation,
            SkillLookupOperation::Inspect | SkillLookupOperation::ReadResource
        ) && let Some(skill) = request
            .skill_name
            .as_deref()
            .and_then(|name| self.resolve(name))
            && !skill.row.allow_implicit_invocation
            && !pins.iter().any(|name| normalize(name) == skill.row.key)
            && !explicit_names(prompt)
                .iter()
                .any(|name| normalize(name) == skill.row.key)
        {
            return Err("This skill requires an explicit user request or a pin.".into());
        }
        self.lookup(request, pins)
    }
}

fn explicit_names(prompt: &str) -> Vec<String> {
    let mut names = Vec::new();
    let chars = prompt.chars().collect::<Vec<_>>();
    let mut index = 0;
    while index < chars.len() {
        if chars[index] == '$'
            && (index == 0
                || !(chars[index - 1].is_ascii_alphanumeric() || "._-".contains(chars[index - 1])))
        {
            let start = index + 1;
            let mut end = start;
            while end < chars.len()
                && (chars[end].is_ascii_alphanumeric() || "._-".contains(chars[end]))
            {
                end += 1;
            }
            if end > start && chars[start].is_ascii_alphanumeric() {
                let name = chars[start..end].iter().collect::<String>();
                if !names
                    .iter()
                    .any(|existing: &String| normalize(existing) == normalize(&name))
                {
                    names.push(name);
                }
            }
            index = end;
        } else {
            index += 1;
        }
    }
    names
}

fn tokens(text: &str) -> BTreeSet<String> {
    text.split(|ch: char| !(ch.is_ascii_alphanumeric() || "._-+".contains(ch)))
        .filter(|token| !token.is_empty())
        .map(|token| token.trim_matches(['.', '_', '-', '+']).to_lowercase())
        .filter(|token| !token.is_empty())
        .collect()
}
fn score(row: &SkillRecord, body: &str, query: &str) -> usize {
    let query = query.to_lowercase();
    let name = row.name.to_lowercase();
    let description = row.description.to_lowercase();
    let body = body.to_lowercase();
    let requested = tokens(&query);
    let available = tokens(&format!("{name} {description} {body}"));
    let mut score = if name == query {
        200
    } else if name.starts_with(&query) {
        120
    } else if name.contains(&query) {
        80
    } else {
        0
    };
    if description.contains(&query) {
        score += 40;
    }
    if body.contains(&query) {
        score += 8;
    }
    score += requested.intersection(&available).count() * 18;
    if !requested.is_empty() && requested.is_subset(&available) {
        score += 24;
    }
    for token in requested {
        if name.contains(&token) {
            score += 16;
        }
        if description.contains(&token) {
            score += 10;
        }
        if body.contains(&token) {
            score += 4;
        }
    }
    score
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn package_discovery_precedence_yaml_and_bounded_resources_preserve_originals() {
        let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/skill-tests");
        fs::create_dir_all(&parent).unwrap();
        let temporary = tempfile::tempdir_in(parent).unwrap();
        let app = temporary.path().join("app");
        let workspace = temporary.path().join("workspace");
        for path in [
            app.join("fixture/references"),
            app.join("fixture/agents"),
            app.join("fixture/nested"),
            app.join("invalid"),
            workspace.join("fixture"),
        ] {
            fs::create_dir_all(path).unwrap();
        }
        let source = "---\nname: fixture\ndescription: >-\n  Compare scenes and\n  preserve source evidence.\n---\n# Source\n完整正文 😀\n";
        fs::write(app.join("fixture/SKILL.md"), source).unwrap();
        fs::write(
            app.join("fixture/agents/openai.yaml"),
            "policy:\n  allow_implicit_invocation: false\n",
        )
        .unwrap();
        fs::write(
            app.join("fixture/references/guide.md"),
            "原始参考\r\n第二行 😀",
        )
        .unwrap();
        fs::write(app.join("fixture/references/binary.dat"), b"text\0payload").unwrap();
        fs::write(
            app.join("fixture/nested/SKILL.md"),
            "---\nname: nested\n---\nDo not advertise a nested package.",
        )
        .unwrap();
        fs::write(
            app.join("invalid/SKILL.md"),
            "---\nname: [unclosed\n---\nBroken",
        )
        .unwrap();
        fs::write(
            workspace.join("fixture/SKILL.md"),
            "---\nname: fixture\n---\nA lower precedence body",
        )
        .unwrap();
        let roots = || {
            vec![
                Root {
                    path: app.clone(),
                    label: "app".into(),
                    scope: "App",
                },
                Root {
                    path: app.clone(),
                    label: "duplicate-root".into(),
                    scope: "App",
                },
                Root {
                    path: workspace.clone(),
                    label: "workspace".into(),
                    scope: "Workspace",
                },
            ]
        };
        let catalog = SkillCatalog::scan(roots(), "reverie");
        let state = catalog.state("reverie", &["fixture".into(), "missing".into()]);
        assert_eq!(state.count, 2);
        assert_eq!(state.invalid_count, 1);
        assert_eq!(state.shadowed_count, 1);
        assert_eq!(state.pinned.unresolved, ["missing"]);
        assert!(!state.records[0].allow_implicit_invocation);
        assert!(state.records[1].shadowed);
        assert_eq!(
            state.records[0].description,
            "Compare scenes and preserve source evidence."
        );
        assert_eq!(
            catalog.inspect("$fixture", &[]).unwrap()["body"],
            "# Source\n完整正文 😀"
        );
        assert_eq!(
            catalog
                .read_resource("fixture", "references/guide.md")
                .unwrap()
                .0,
            "原始参考\r\n第二行 😀"
        );
        assert!(catalog.read_resource("fixture", "../outside.md").is_err());
        assert!(
            catalog
                .read_resource("fixture", "references/binary.dat")
                .is_err()
        );
        assert_eq!(
            fs::read_to_string(app.join("fixture/SKILL.md")).unwrap(),
            source
        );
        fs::write(app.join("fixture/SKILL.md"), "# Changed\n新的正文").unwrap();
        assert!(
            catalog
                .inspect("fixture", &[])
                .unwrap_err()
                .to_string()
                .contains("changed")
        );
        assert_eq!(
            SkillCatalog::scan(roots(), "reverie")
                .inspect("fixture", &[])
                .unwrap()["body"],
            "# Changed\n新的正文"
        );
    }
}
