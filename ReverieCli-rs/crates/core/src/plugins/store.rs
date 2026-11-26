use super::{manifest, package};
use crate::{Result, config};
use reverie_protocol::{
    ActivatePluginRequest, PluginCandidate, PluginControlRequest, PluginRecord, PluginsState,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::Arc,
};

#[derive(Clone, Serialize, Deserialize)]
pub(super) struct Version {
    pub snapshot: package::Snapshot,
    pub metadata: manifest::Metadata,
    pub source: Value,
    pub source_request: reverie_protocol::PluginSourceRequest,
    pub verification: String,
    pub profile: String,
}

impl Version {
    pub fn public(&self) -> Result<PluginCandidate> {
        Ok(PluginCandidate {
            sha256: self.snapshot.sha256.clone(),
            name: self.metadata.display_name.clone(),
            version: self.metadata.version.clone(),
            source: self.source.clone(),
            bytes: self.snapshot.bytes,
            signing_key: self.snapshot.signing_key.clone(),
            verification: self.verification.clone(),
            approval_profile_sha256: self.profile.clone(),
            approval_required: self.verification == "candidate_approval_required",
            components: self
                .metadata
                .components
                .iter()
                .map(|component| serde_json::from_value(component.public()))
                .collect::<std::result::Result<_, _>>()?,
            license: self.metadata.license.clone(),
            license_files: self.metadata.license_files.clone(),
            approval: json!({"source":self.source,"publisher":self.metadata.approval_profile["publisher"],
                "signing_key":self.snapshot.signing_key,"license":self.metadata.license,
                "license_files":self.metadata.license_files,"permissions":self.metadata.approval_profile["permissions"],
                "dependencies":self.metadata.approval_profile["dependencies"],"terms":self.metadata.approval_profile["terms"],
                "privacy":self.metadata.approval_profile["privacy"],
                "components":self.metadata.components.iter().map(manifest::Component::public).collect::<Vec<_>>()}),
        })
    }
}

#[derive(Clone, Default, Serialize, Deserialize)]
struct Installed {
    name: String,
    current: Option<String>,
    previous: Option<String>,
    versions: BTreeMap<String, String>,
    trusted_profile: Option<String>,
    enabled: bool,
    hooks_enabled: bool,
    auto_update: bool,
}

#[derive(Serialize, Deserialize)]
struct Registry {
    schema: String,
    revision: u64,
    plugins: BTreeMap<String, Installed>,
    projects: BTreeMap<String, BTreeMap<String, bool>>,
}
impl Default for Registry {
    fn default() -> Self {
        Self {
            schema: "reverie.extension-activation.v1".into(),
            revision: 0,
            plugins: BTreeMap::new(),
            projects: BTreeMap::new(),
        }
    }
}

#[derive(Clone)]
pub struct PluginStore {
    root: PathBuf,
}

pub struct PluginLease {
    pub id: String,
    pub root: PathBuf,
    pub(super) version: Version,
    pub hooks_enabled: bool,
    _lease: fs::File,
}
impl PluginLease {
    pub fn metadata(&self) -> &manifest::Metadata {
        &self.version.metadata
    }
    pub fn sha256(&self) -> &str {
        &self.version.snapshot.sha256
    }
    pub fn text(&self, relative: &str) -> Result<String> {
        let bytes = package::bounded_text(
            &package::checked_path(&self.root, relative)?,
            16 * 1024 * 1024,
        )?;
        self.verify_content(relative, &bytes)?;
        Ok(String::from_utf8(bytes)?)
    }
    pub(crate) fn verify_content(&self, relative: &str, bytes: &[u8]) -> Result<()> {
        let expected = self
            .version
            .snapshot
            .files
            .iter()
            .find(|file| file.path == relative)
            .ok_or("File is not part of the approved extension version.")?;
        if bytes.len() as u64 != expected.bytes || package::digest(bytes) != expected.sha256 {
            return Err("Installed extension content changed; execution was refused.".into());
        }
        Ok(())
    }
}

fn identity(value: &str) -> Result<()> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err("Invalid extension content identity.".into());
    }
    Ok(())
}
fn project_key(project: &Path) -> Result<String> {
    let path = config::canonical_project(project)?
        .to_string_lossy()
        .into_owned();
    Ok(package::digest(
        if cfg!(windows) {
            path.to_lowercase()
        } else {
            path
        }
        .as_bytes(),
    ))
}
impl PluginStore {
    pub fn new(app: &Path) -> Result<Self> {
        fs::create_dir_all(app)?;
        Ok(Self {
            root: package::managed_directory(app, ".reverie/extensions/installations")?,
        })
    }
    pub(super) fn root(&self) -> &Path {
        &self.root
    }
    fn read(&self) -> Result<Registry> {
        let path = self.root.join("active.json");
        if !path.exists() {
            return Ok(Registry::default());
        }
        let registry: Registry =
            serde_json::from_slice(&package::bounded_text(&path, 16 * 1024 * 1024)?)?;
        if registry.schema != "reverie.extension-activation.v1" {
            return Err(
                "Unsupported extension activation schema; the original record was preserved."
                    .into(),
            );
        }
        for (id, installed) in &registry.plugins {
            identity(id)?;
            for (version, descriptor) in &installed.versions {
                identity(version)?;
                identity(descriptor)?;
            }
            for version in installed.current.iter().chain(&installed.previous) {
                if !installed.versions.contains_key(version) {
                    return Err("Extension activation refers to an unregistered version.".into());
                }
            }
        }
        Ok(registry)
    }
    fn change<T>(
        &self,
        expected: Option<u64>,
        edit: impl FnOnce(&mut Registry) -> Result<T>,
    ) -> Result<T> {
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(self.root.join("activation.lock"))?;
        lock.lock()?;
        let mut registry = self.read()?;
        if expected.is_some_and(|expected| expected != registry.revision) {
            return Err("Extension activation changed; reload before retrying.".into());
        }
        let result = edit(&mut registry)?;
        registry.revision = registry
            .revision
            .checked_add(1)
            .ok_or("Extension revision overflow.")?;
        config::atomic_json(
            &self.root.join("active.json"),
            &serde_json::to_value(&registry)?,
        )?;
        Ok(result)
    }
    fn version_root(&self, id: &str, hash: &str) -> Result<PathBuf> {
        identity(id)?;
        identity(hash)?;
        Ok(self.root.join("versions").join(id).join(hash))
    }
    fn version(&self, id: &str, hash: &str, installed: &Installed) -> Result<Version> {
        let expected = installed
            .versions
            .get(hash)
            .ok_or("Extension candidate is not registered.")?;
        let path = self.version_root(id, hash)?;
        let bytes = package::bounded_text(
            &package::checked_path(&path, "version.json")?,
            16 * 1024 * 1024,
        )?;
        if package::digest(&bytes) != *expected {
            return Err("Extension version record changed; original files were preserved.".into());
        }
        let version: Version = serde_json::from_slice(&bytes)?;
        if version.snapshot.sha256 != hash || version.metadata.name != installed.name {
            return Err("Extension version identity does not match its activation record.".into());
        }
        Ok(version)
    }
    fn verify(
        &self,
        id: &str,
        hash: &str,
        installed: &Installed,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Version> {
        let version = self.version(id, hash, installed)?;
        let root = self.version_root(id, hash)?.join("package");
        let snapshot = package::inspect(&root, cancelled)?;
        if snapshot.sha256 != hash || snapshot.signing_key != version.snapshot.signing_key {
            return Err("Extension candidate no longer matches its verified content.".into());
        }
        let metadata = manifest::inspect(&root, None, &snapshot)?;
        // Marketplace component overrides are retained in the signed descriptor;
        // every package file and the descriptor are checked independently.
        if metadata.name != version.metadata.name {
            return Err("Extension manifest identity changed.".into());
        }
        super::validate_components(&root, &version.metadata)?;
        Ok(version)
    }
    pub(super) fn register(
        &self,
        id: &str,
        version: Version,
        staging: tempfile::TempDir,
        expected: Option<u64>,
    ) -> Result<Value> {
        identity(id)?;
        let hash = version.snapshot.sha256.clone();
        let parent = package::managed_directory(&self.root, &format!("versions/{id}"))?;
        let target = parent.join(&hash);
        config::atomic_json(
            &staging.path().join("version.json"),
            &serde_json::to_value(&version)?,
        )?;
        // Hash exactly the bytes persisted by atomic_json, including its newline.
        let descriptor = package::digest(&fs::read(staging.path().join("version.json"))?);
        self.change(expected, |registry| {
            let installed = registry.plugins.entry(id.into()).or_default();
            if !installed.name.is_empty() && installed.name != version.metadata.name { return Err("An update cannot replace the installed plugin identity.".into()); }
            if target.exists() {
                let bytes = package::bounded_text(&package::checked_path(&target, "version.json")?, 16 * 1024 * 1024)?;
                let original: Version = serde_json::from_slice(&bytes)?;
                if original.snapshot.sha256 != hash || original.source != version.source || original.profile != version.profile {
                    return Err("The same extension content was prepared with different provenance; the existing record was preserved.".into());
                }
                installed.versions.insert(hash.clone(), package::digest(&bytes));
            } else {
                fs::rename(staging.path(), &target)?;
                installed.versions.insert(hash.clone(), descriptor);
            }
            installed.name = version.metadata.name.clone();
            Ok(())
        })?;
        Ok(json!({"plugin_id":id,"candidate":version.public()?,"plugins":self.state(None)?}))
    }
    pub fn state(&self, project: Option<&Path>) -> Result<PluginsState> {
        let registry = self.read()?;
        let project = project.map(project_key).transpose()?;
        let mut records = Vec::new();
        for (id, installed) in &registry.plugins {
            let selected = installed
                .current
                .as_ref()
                .or_else(|| installed.versions.keys().next_back());
            let Some(selected) = selected else {
                continue;
            };
            let version = self.version(id, selected, installed)?;
            let trusted = installed.current.is_some()
                && installed.trusted_profile.as_deref() == Some(&version.profile);
            let enabled = project
                .as_ref()
                .and_then(|key| registry.projects.get(key))
                .and_then(|items| items.get(id))
                .copied()
                .unwrap_or(installed.enabled);
            let status = if installed.current.is_none() {
                "candidate"
            } else if !trusted {
                "trust_required"
            } else if enabled {
                "ready"
            } else {
                "disabled"
            };
            records.push(PluginRecord {
                id: id.clone(),
                name: version.metadata.display_name.clone(),
                family: version.metadata.family.clone(),
                version: version.metadata.version.clone(),
                status: status.into(),
                status_label: status.into(),
                enabled,
                trusted,
                protocol_status: "compatible".into(),
                protocol_label: "compatible".into(),
                tool_count: version
                    .metadata
                    .components
                    .iter()
                    .filter(|component| component.kind == "mcp")
                    .count(),
                command_count: version
                    .metadata
                    .components
                    .iter()
                    .filter(|component| component.kind == "command")
                    .count(),
                skill_count: version
                    .metadata
                    .components
                    .iter()
                    .filter(|component| component.kind == "skill")
                    .count(),
                entry_path: version
                    .metadata
                    .components
                    .iter()
                    .find(|component| component.kind == "runtime")
                    .map(|component| component.path.clone())
                    .unwrap_or_default(),
                install_dir: self
                    .version_root(id, selected)?
                    .join("package")
                    .to_string_lossy()
                    .into_owned(),
                active_sha256: installed.current.clone().unwrap_or_default(),
                approval_profile_sha256: version.profile.clone(),
                hooks_enabled: installed.hooks_enabled,
                auto_update: installed.auto_update,
                previous_sha256: installed.previous.clone().unwrap_or_default(),
                source: version.source.clone(),
                candidates: installed
                    .versions
                    .keys()
                    .filter(|hash| installed.current.as_ref() != Some(hash))
                    .map(|hash| self.version(id, hash, installed)?.public())
                    .collect::<Result<_>>()?,
            });
        }
        Ok(PluginsState {
            revision: registry.revision,
            summary: json!({"available":true,"count":records.len(),"status":"ready"}),
            records,
        })
    }
    pub fn inspect(&self, id: &str, project: Option<&Path>) -> Result<Value> {
        let state = self.state(project)?;
        let record = state
            .records
            .iter()
            .find(|record| record.id == id)
            .ok_or("Extension is not installed or prepared.")?;
        let registry = self.read()?;
        let installed = registry
            .plugins
            .get(id)
            .ok_or("Extension was removed during inspection.")?;
        let current = installed
            .current
            .as_ref()
            .map(|hash| self.version(id, hash, installed)?.public())
            .transpose()?;
        Ok(json!({"plugin_id":id,"record":record,"active":current,"revision":state.revision}))
    }
    pub fn activate(&self, request: ActivatePluginRequest) -> Result<Value> {
        self.change(request.expected_revision, |registry| {
            let installed = registry.plugins.get_mut(&request.plugin_id).ok_or("Prepared extension was not found.")?;
            let version = self.verify(&request.plugin_id, &request.candidate_sha256, installed, &|| false)?;
            if version.verification == "candidate_approval_required" && request.approved_sha256.as_deref() != Some(&version.snapshot.sha256) {
                return Err("Approve this exact candidate SHA-256 before activating content without published or fixed Git evidence.".into());
            }
            if installed.trusted_profile.as_ref().is_some_and(|profile| profile != &version.profile) {
                if request.approved_profile_sha256.as_deref() != Some(&version.profile) {
                    return Err("Extension source, execution, permissions, dependencies or terms changed; approve the new profile before switching.".into());
                }
                installed.trusted_profile = Some(version.profile.clone());
                installed.hooks_enabled = false;
            }
            if installed.current.as_deref() != Some(&request.candidate_sha256) {
                installed.previous = installed.current.replace(request.candidate_sha256.clone());
            }
            Ok(())
        })?;
        Ok(json!({"plugin_id":request.plugin_id,"plugins":self.state(None)?}))
    }
    pub fn control(&self, action: &str, request: PluginControlRequest) -> Result<Value> {
        let project = request
            .project_root
            .as_deref()
            .map(Path::new)
            .map(project_key)
            .transpose()?;
        self.change(request.expected_revision, |registry| {
            if action == "removePlugin" {
                if request.confirmed != Some(true) { return Err("Confirm removal of this extension's activation and registration.".into()); }
                registry.plugins.remove(&request.plugin_id).ok_or("Extension was not found.")?;
                for entries in registry.projects.values_mut() { entries.remove(&request.plugin_id); }
                return Ok(());
            }
            let installed = registry.plugins.get_mut(&request.plugin_id).ok_or("Extension was not found.")?;
            let hash = installed.current.as_ref().ok_or("Activate a verified version before enabling or trusting it.")?.clone();
            let version = self.verify(&request.plugin_id, &hash, installed, &|| false)?;
            match action {
                "setPluginTrust" => {
                    let trusted = request.trusted.ok_or("trusted is required.")?;
                    if trusted {
                        if request.candidate_sha256.as_deref() != Some(&hash) || request.approval_profile_sha256.as_deref() != Some(&version.profile) {
                            return Err("Trust must name the inspected content SHA-256 and approval profile.".into());
                        }
                        installed.trusted_profile = Some(version.profile); installed.auto_update = true;
                    } else { installed.trusted_profile = None; installed.hooks_enabled = false; installed.auto_update = false; }
                }
                "setPluginEnabled" => {
                    let enabled = request.enabled.ok_or("enabled is required.")?;
                    if enabled && installed.trusted_profile.as_deref() != Some(&version.profile) { return Err("Trust the extension before enabling its components.".into()); }
                    if let Some(project) = &project { registry.projects.entry(project.clone()).or_default().insert(request.plugin_id.clone(), enabled); }
                    else { installed.enabled = enabled; }
                }
                "setPluginHooks" => {
                    let enabled = request.hooks_enabled.ok_or("hooks_enabled is required.")?;
                    if enabled && (installed.trusted_profile.as_deref() != Some(&version.profile) || request.approval_profile_sha256.as_deref() != Some(&version.profile)) {
                        return Err("Confirm the inspected hook events, entries and permissions before enabling Hooks.".into());
                    }
                    installed.hooks_enabled = enabled;
                }
                "setPluginAutoUpdate" => {
                    let enabled = request.auto_update.ok_or("auto_update is required.")?;
                    if enabled && installed.trusted_profile.as_deref() != Some(&version.profile) { return Err("Only explicitly trusted extensions may update automatically.".into()); }
                    installed.auto_update = enabled;
                }
                "rollbackPlugin" => {
                    let previous = installed.previous.clone().ok_or("No previous extension version is available.")?;
                    let old = self.verify(&request.plugin_id, &previous, installed, &|| false)?;
                    if installed.trusted_profile.as_ref().is_some_and(|profile| profile != &old.profile) {
                        if request.approval_profile_sha256.as_deref() != Some(&old.profile) { return Err("Approve the previous execution profile before rollback.".into()); }
                        installed.trusted_profile = Some(old.profile); installed.hooks_enabled = false;
                    }
                    installed.previous = installed.current.replace(previous);
                }
                _ => return Err("Unsupported extension control action.".into()),
            }
            Ok(())
        })?;
        Ok(
            json!({"plugin_id":request.plugin_id,"retained_versions":action=="removePlugin","plugins":self.state(request.project_root.as_deref().map(Path::new))?}),
        )
    }
    pub fn leases(
        &self,
        project: &Path,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Vec<Arc<PluginLease>>> {
        let registry = self.read()?;
        let project = project_key(project)?;
        let directory = package::managed_directory(&self.root, "leases")?;
        let mut result = Vec::new();
        for (id, installed) in &registry.plugins {
            if !registry
                .projects
                .get(&project)
                .and_then(|items| items.get(id))
                .copied()
                .unwrap_or(installed.enabled)
            {
                continue;
            }
            let Some(hash) = installed.current.as_ref() else {
                continue;
            };
            let lock = fs::OpenOptions::new()
                .create(true)
                .truncate(false)
                .read(true)
                .write(true)
                .open(directory.join(format!("{id}-{hash}.lock")))?;
            lock.try_lock_shared()
                .map_err(|_| "Extension version is being removed; retry when it is available.")?;
            let version = self.verify(id, hash, installed, cancelled)?;
            if installed.trusted_profile.as_deref() != Some(&version.profile) {
                continue;
            }
            result.push(Arc::new(PluginLease {
                id: id.clone(),
                root: self.version_root(id, hash)?.join("package"),
                version,
                hooks_enabled: installed.hooks_enabled,
                _lease: lock,
            }));
        }
        Ok(result)
    }
    pub(super) fn source_for_update(
        &self,
        id: &str,
    ) -> Result<reverie_protocol::PluginSourceRequest> {
        let registry = self.read()?;
        let installed = registry.plugins.get(id).ok_or("Extension was not found.")?;
        let current = installed
            .current
            .as_ref()
            .ok_or("No installed version is available.")?;
        Ok(self.version(id, current, installed)?.source_request)
    }
}
