use crate::{Result, config};
use reverie_context::{
    inference::{Device, LocalModels},
    resources,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    sync::{Arc, Mutex, Weak},
};

pub use reverie_protocol::SemanticSelection as Selection;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Registry {
    schema: String,
    revision: u64,
    current: Option<Selection>,
    previous: Option<Selection>,
    pending_removal: Vec<String>,
}
impl Default for Registry {
    fn default() -> Self {
        Self {
            schema: "reverie.semantic-activation.v1".into(),
            revision: 0,
            current: None,
            previous: None,
            pending_removal: Vec::new(),
        }
    }
}
fn valid_digest(digest: &str) -> bool {
    digest.len() == 64
        && digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}
fn read_registry(store: &Path) -> Result<Registry> {
    let bytes = match fs::read(store.join("active.json")) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(Registry::default());
        }
        Err(error) => return Err(error.into()),
    };
    if bytes.len() > 65536 {
        return Err("Semantic activation record is too large.".into());
    }
    let registry: Registry = serde_json::from_slice(&bytes)?;
    if registry.schema != "reverie.semantic-activation.v1"
        || registry
            .current
            .iter()
            .chain(registry.previous.iter())
            .any(|item| {
                !valid_digest(&item.manifest_sha256)
                    || item.version.trim().is_empty()
                    || !(1..=256).contains(&item.threads)
            })
        || registry
            .pending_removal
            .iter()
            .any(|digest| !valid_digest(digest))
    {
        return Err("Invalid semantic activation record; it has been preserved.".into());
    }
    Ok(registry)
}

pub struct ModelVersion {
    pub selection: Selection,
    directory: PathBuf,
    _lease: fs::File,
    models: Mutex<Option<Arc<LocalModels>>>,
}
impl ModelVersion {
    fn new(store: &Path, selection: Selection) -> Result<Self> {
        if !valid_digest(&selection.manifest_sha256) {
            return Err("Invalid semantic resource identity.".into());
        }
        let leases = store.join("leases");
        checked_directory(store)?;
        checked_directory(&leases)?;
        let directory = store.join("versions").join(&selection.manifest_sha256);
        let manifest = resources::inspect_manifest(&directory, &selection.manifest_sha256)?;
        if manifest.version != selection.version {
            return Err("Selected semantic resource version does not match its manifest.".into());
        }
        let lease = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(leases.join(format!("{}.lock", selection.manifest_sha256)))?;
        lease.try_lock_shared().map_err(
            |_| "Semantic resources are being removed; retry after the operation finishes.",
        )?;
        Ok(Self {
            directory,
            selection,
            _lease: lease,
            models: Mutex::new(None),
        })
    }

    pub fn models(&self, cancelled: &impl Fn() -> bool) -> Result<Arc<LocalModels>> {
        let mut models = self
            .models
            .lock()
            .map_err(|_| "Semantic resource model lock was poisoned.")?;
        if cancelled() {
            return Err("Semantic model loading cancelled.".into());
        }
        if let Some(models) = models.as_ref() {
            return Ok(models.clone());
        }
        let bundle =
            resources::verify(&self.directory, &self.selection.manifest_sha256, cancelled)?;
        let loaded = Arc::new(LocalModels::new(
            bundle,
            self.selection.device,
            self.selection.threads,
        )?);
        *models = Some(loaded.clone());
        Ok(loaded)
    }
    fn status(&self) -> Value {
        match self.models.try_lock() {
            Ok(models)=>models.as_ref().map(|models|models.status().unwrap_or_else(|error|json!({"available":false,"status":"error","error":error.to_string()}))).unwrap_or_else(||json!({"available":true,"status":"on_demand","embedding_loaded":false,"reranker_loaded":false})),
            Err(_)=>json!({"available":true,"status":"verifying"}),
        }
    }
}

struct State {
    registry: Registry,
    active: Option<Arc<ModelVersion>>,
    versions: HashMap<String, Weak<ModelVersion>>,
    error: String,
}
pub struct SemanticResources {
    store: PathBuf,
    state: Mutex<State>,
}
impl SemanticResources {
    pub fn new(store: PathBuf) -> Self {
        let (registry, error) = match read_registry(&store) {
            Ok(registry) => (registry, String::new()),
            Err(error) => (Registry::default(), error.to_string()),
        };
        Self {
            store,
            state: Mutex::new(State {
                registry,
                active: None,
                versions: HashMap::new(),
                error,
            }),
        }
    }
    pub fn revision(&self) -> Result<u64> {
        self.refresh()?;
        let state = self
            .state
            .lock()
            .map_err(|_| "Semantic resource state lock was poisoned.")?;
        if !state.error.is_empty() {
            return Err(state.error.clone().into());
        }
        Ok(state.registry.revision)
    }
    pub fn capture(&self) -> Result<Option<Arc<ModelVersion>>> {
        self.refresh()?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| "Semantic resource state lock was poisoned.")?;
        if !state.error.is_empty() {
            return Err(state.error.clone().into());
        }
        let Some(selection) = state.registry.current.clone() else {
            return Ok(None);
        };
        if let Some(version) = state.active.as_ref() {
            return Ok(Some(version.clone()));
        }
        let key = serde_json::to_string(&selection)?;
        let version = match state.versions.get(&key).and_then(Weak::upgrade) {
            Some(version) => version,
            None => Arc::new(ModelVersion::new(&self.store, selection)?),
        };
        state.versions.insert(key, Arc::downgrade(&version));
        state.active = Some(version.clone());
        Ok(Some(version))
    }
    pub fn status(&self) -> Value {
        let state = match self.state.try_lock() {
            Ok(state) => state,
            Err(_) => {
                return json!({"available":false,"status":"busy","active":null,"previous":null,"models":{},"error":"","pending_restart":[]});
            }
        };
        let models = state
            .active
            .as_ref()
            .map(|version| version.status())
            .unwrap_or_else(
                || json!({"embedding_loaded":false,"reranker_loaded":false,"status":"on_demand"}),
            );
        json!({"available":state.error.is_empty()&&state.registry.current.is_some(),"status":if !state.error.is_empty(){"error"}else if state.registry.current.is_some(){models["status"].as_str().unwrap_or("on_demand")}else{"resource_not_installed"},
            "revision":state.registry.revision,"active":state.registry.current,"previous":state.registry.previous,"models":models,"error":state.error,"pending_restart":state.registry.pending_removal})
    }

    fn refresh(&self) -> Result<()> {
        let registry = read_registry(&self.store);
        let mut state = self
            .state
            .lock()
            .map_err(|_| "Semantic resource state lock was poisoned.")?;
        match registry {
            Ok(registry) => {
                if registry != state.registry {
                    state.registry = registry;
                    state.active = None;
                }
                state.error.clear();
                Ok(())
            }
            Err(error) => {
                state.error = error.to_string();
                Err(error)
            }
        }
    }

    pub fn inventory(&self) -> Value {
        let _ = self.refresh();
        let mut records = Vec::new();
        let mut errors = Vec::new();
        let status = self.status();
        match fs::read_dir(self.store.join("versions")) {
            Ok(entries) => {
                for entry in entries {
                    let result = (|| -> Result<Value> {
                        let entry = entry?;
                        let digest = entry.file_name().to_string_lossy().into_owned();
                        if !valid_digest(&digest) {
                            return Err(format!(
                                "Unrecognized managed resource directory: {digest}"
                            )
                            .into());
                        }
                        let manifest = resources::inspect_manifest(&entry.path(), &digest)?;
                        Ok(
                            json!({"manifest_sha256":digest,"version":manifest.version,"platform":manifest.platform,"architecture":manifest.architecture,
                        "bytes":manifest.files.values().map(|file|file.bytes).sum::<u64>(),"active":status["active"]["manifest_sha256"]==digest,
                        "removal_pending":status["pending_restart"].as_array().is_some_and(|items|items.contains(&json!(digest))),"integrity":"manifest_verified"}),
                        )
                    })();
                    match result {
                        Ok(record) => records.push(record),
                        Err(error) => errors.push(error.to_string()),
                    }
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => errors.push(error.to_string()),
        }
        records.sort_by(|left, right| {
            left["manifest_sha256"]
                .as_str()
                .cmp(&right["manifest_sha256"].as_str())
        });
        let mut result = status;
        result["records"] = json!(records);
        result["inventory_errors"] = json!(errors);
        result
    }

    pub fn install(
        &self,
        source: &Path,
        digest: &str,
        device: Device,
        threads: usize,
        expected: u64,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Value> {
        let bundle = resources::stage(&self.store, source, digest, cancelled)?;
        self.activate(
            Selection {
                manifest_sha256: bundle.digest,
                version: bundle.manifest.version,
                device,
                threads,
            },
            expected,
            cancelled,
        )
    }

    pub fn select(
        &self,
        digest: &str,
        device: Device,
        threads: usize,
        expected: u64,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Value> {
        if !valid_digest(digest) {
            return Err("Invalid semantic resource identity.".into());
        }
        let manifest =
            resources::inspect_manifest(&self.store.join("versions").join(digest), digest)?;
        self.activate(
            Selection {
                manifest_sha256: digest.into(),
                version: manifest.version,
                device,
                threads,
            },
            expected,
            cancelled,
        )
    }

    pub fn rollback(&self, expected: u64, cancelled: &impl Fn() -> bool) -> Result<Value> {
        let previous = read_registry(&self.store)?
            .previous
            .ok_or("No previous semantic resource activation is available.")?;
        self.activate(previous, expected, cancelled)
    }

    fn activate(
        &self,
        selection: Selection,
        expected: u64,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Value> {
        if !(1..=256).contains(&selection.threads) {
            return Err("Semantic intra-op threads must be between 1 and 256.".into());
        }
        let version = Arc::new(ModelVersion::new(&self.store, selection.clone())?);
        let models = version.models(cancelled)?;
        let health = models.probe_with_cancel(cancelled)?;
        models.unload()?;
        resources::verify(&version.directory, &selection.manifest_sha256, cancelled)?;
        let _writer = writer_lock(&self.store, cancelled)?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| "Semantic resource state lock was poisoned.")?;
        let mut registry = read_registry(&self.store)?;
        if registry.revision != expected {
            return Err(
                "Semantic activation changed while validating the candidate; refresh and retry."
                    .into(),
            );
        }
        if cancelled() {
            return Err(
                "Semantic resource activation cancelled; the previous version remains selected."
                    .into(),
            );
        }
        registry.revision = registry
            .revision
            .checked_add(1)
            .ok_or("Semantic activation revision exhausted.")?;
        registry.previous = registry.current;
        registry.current = Some(selection.clone());
        registry
            .pending_removal
            .retain(|digest| digest != &selection.manifest_sha256);
        config::atomic_json(
            &self.store.join("active.json"),
            &serde_json::to_value(&registry)?,
        )?;
        state
            .versions
            .insert(serde_json::to_string(&selection)?, Arc::downgrade(&version));
        state.registry = registry;
        state.active = Some(version);
        state.error.clear();
        drop(state);
        Ok(json!({"activated":true,"health":health,"semantic":self.inventory()}))
    }

    pub fn disable(&self, expected: u64, cancelled: &impl Fn() -> bool) -> Result<Value> {
        let _writer = writer_lock(&self.store, cancelled)?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| "Semantic resource state lock was poisoned.")?;
        let mut registry = read_registry(&self.store)?;
        if registry.revision != expected {
            return Err("Semantic activation changed; refresh and retry.".into());
        }
        registry.revision = registry
            .revision
            .checked_add(1)
            .ok_or("Semantic activation revision exhausted.")?;
        registry.previous = registry.current.take();
        if cancelled() {
            return Err("Semantic resource deactivation cancelled.".into());
        }
        config::atomic_json(
            &self.store.join("active.json"),
            &serde_json::to_value(&registry)?,
        )?;
        state.registry = registry;
        state.active = None;
        drop(state);
        Ok(json!({"deactivated":true,"semantic":self.inventory()}))
    }

    pub fn unload(&self) -> Result<Value> {
        let state = self
            .state
            .lock()
            .map_err(|_| "Semantic resource state lock was poisoned.")?;
        if let Some(version) = state.active.as_ref() {
            if Arc::strong_count(version) > 1 {
                return Err(
                    "Semantic models are held by a running operation; wait before unloading."
                        .into(),
                );
            }
            let models = version
                .models
                .lock()
                .map_err(|_| "Semantic resource model lock was poisoned.")?;
            if let Some(models) = models.as_ref() {
                models.unload()?;
            }
        }
        drop(state);
        Ok(json!({"unloaded":true,"semantic":self.inventory()}))
    }

    pub fn remove(
        &self,
        digest: &str,
        expected: u64,
        cancelled: &impl Fn() -> bool,
    ) -> Result<Value> {
        if !valid_digest(digest) {
            return Err("Invalid managed semantic resource identity.".into());
        }
        let _writer = writer_lock(&self.store, cancelled)?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| "Semantic resource state lock was poisoned.")?;
        let mut registry = read_registry(&self.store)?;
        if registry.revision != expected {
            return Err("Semantic activation changed; refresh before removing resources.".into());
        }
        let target = self.store.join("versions").join(digest);
        resources::inspect_manifest(&target, digest)?;
        for version in state.versions.values() {
            if let Some(version) = version.upgrade()
                && version.selection.manifest_sha256 == digest
            {
                let own = state
                    .active
                    .as_ref()
                    .is_some_and(|active| Arc::ptr_eq(active, &version));
                if Arc::strong_count(&version) > 1 + usize::from(own) {
                    return Err(
                        "Semantic resources are held by a running task; wait before removing them."
                            .into(),
                    );
                }
            }
        }
        if state
            .active
            .as_ref()
            .is_some_and(|version| version.selection.manifest_sha256 == digest)
        {
            state.active = None;
        }
        let leases = self.store.join("leases");
        checked_directory(&leases)?;
        let exclusive = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(leases.join(format!("{digest}.lock")))?;
        exclusive.try_lock().map_err(
            |_| "Another process or task holds these semantic resources; retry after it closes.",
        )?;
        let target = target.canonicalize()?;
        let versions = self.store.join("versions").canonicalize()?;
        if target.parent() != Some(versions.as_path()) || linked(&fs::symlink_metadata(&target)?) {
            return Err("Resource removal target is outside managed versions.".into());
        }
        check_tree(&target)?;
        let pinned = reverie_context::inference::runtime_directory()?
            .is_some_and(|directory| directory == target);
        if registry
            .current
            .as_ref()
            .is_some_and(|selection| selection.manifest_sha256 == digest)
        {
            registry.current = None;
        }
        if registry
            .previous
            .as_ref()
            .is_some_and(|selection| selection.manifest_sha256 == digest)
        {
            registry.previous = None;
        }
        registry.pending_removal.retain(|value| value != digest);
        if pinned {
            registry.pending_removal.push(digest.into());
        }
        registry.revision = registry
            .revision
            .checked_add(1)
            .ok_or("Semantic activation revision exhausted.")?;
        if cancelled() {
            return Err("Semantic resource removal cancelled.".into());
        }
        config::atomic_json(
            &self.store.join("active.json"),
            &serde_json::to_value(&registry)?,
        )?;
        state.registry = registry;
        drop(state);
        if !pinned {
            let trash = versions.join(format!("removing-{}", uuid::Uuid::new_v4().simple()));
            fs::rename(&target, &trash)?;
            check_tree(&trash)?;
            fs::remove_dir_all(&trash)?;
        }
        Ok(
            json!({"removed":!pinned,"deactivated":true,"pending_restart":pinned,"semantic":self.inventory()}),
        )
    }
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
fn checked_directory(path: &Path) -> Result<()> {
    fs::create_dir_all(path)?;
    if linked(&fs::symlink_metadata(path)?) || !path.is_dir() {
        return Err("Managed semantic resource directories cannot be links.".into());
    }
    Ok(())
}
fn check_tree(path: &Path) -> Result<()> {
    if linked(&fs::symlink_metadata(path)?) {
        return Err("Managed resource removal encountered a link; files were preserved.".into());
    }
    if path.is_dir() {
        for entry in fs::read_dir(path)? {
            check_tree(&entry?.path())?;
        }
    }
    Ok(())
}
fn writer_lock(store: &Path, cancelled: &impl Fn() -> bool) -> Result<fs::File> {
    checked_directory(store)?;
    let file = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(store.join("registry.lock"))?;
    loop {
        if cancelled() {
            return Err(
                "Semantic resource operation cancelled while waiting for the registry.".into(),
            );
        }
        match file.try_lock() {
            Ok(()) => return Ok(file),
            Err(fs::TryLockError::WouldBlock) => {
                std::thread::sleep(std::time::Duration::from_millis(20))
            }
            Err(error) => return Err(error.into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn corrupted_activation_is_preserved_and_empty_store_is_on_demand() {
        let root = tempfile::tempdir().unwrap();
        let manager = SemanticResources::new(root.path().to_owned());
        assert_eq!(manager.status()["available"], false);
        assert!(manager.capture().unwrap().is_none());
        let bytes = b"{\"schema\":\"unrelated\",\"data\":42}";
        fs::write(root.path().join("active.json"), bytes).unwrap();
        let broken = SemanticResources::new(root.path().to_owned());
        assert_eq!(broken.status()["status"], "error");
        assert!(broken.capture().is_err());
        assert_eq!(fs::read(root.path().join("active.json")).unwrap(), bytes);
    }
    #[test]
    fn deactivation_keeps_existing_task_leases_and_cancelled_changes_preserve_the_record() {
        let root = tempfile::tempdir().unwrap();
        let fixture = root.path().join("fixture");
        fs::create_dir(&fixture).unwrap();
        let mut files = serde_json::Map::new();
        for role in ["embedding", "reranker"] {
            for file in [
                "model.onnx",
                "tokenizer.json",
                "config.json",
                "special_tokens_map.json",
                "tokenizer_config.json",
            ] {
                files.insert(
                    format!("{role}/{file}"),
                    json!({"bytes":1,"sha256":"0".repeat(64)}),
                );
            }
        }
        for file in ["runtime/library", "LICENSE"] {
            files.insert(file.into(), json!({"bytes":1,"sha256":"0".repeat(64)}));
        }
        let model = |role: &str, id: &str, revision: &str| json!({"id":id,"revision":revision,"onnx":format!("{role}/model.onnx"),"tokenizer_directory":role,"max_length":512,"precision":"fp32"});
        let manifest = json!({"schema":"reverie.semantic-resource.v1","version":"lease-fixture","platform":std::env::consts::OS,"architecture":std::env::consts::ARCH,"dimensions":384,
            "runtime":{"version":"1.31.0","api_version":24,"library":"runtime/library"},"embedding":model("embedding","intfloat/multilingual-e5-small",resources::E5_REVISION),"reranker":model("reranker","BAAI/bge-reranker-base",resources::BGE_REVISION),"files":files,"licenses":["LICENSE"],"provenance":{"scope":"Manifest and OS file-lease fixture only, not model health"}});
        fs::write(
            fixture.join("manifest.json"),
            serde_json::to_vec(&manifest).unwrap(),
        )
        .unwrap();
        let digest = resources::hash_file(&fixture.join("manifest.json")).unwrap();
        fs::create_dir(root.path().join("versions")).unwrap();
        fs::rename(&fixture, root.path().join("versions").join(&digest)).unwrap();
        let selection = Selection {
            manifest_sha256: digest.clone(),
            version: "lease-fixture".into(),
            device: Device::Cpu,
            threads: 6,
        };
        let registry = Registry {
            current: Some(selection.clone()),
            ..Default::default()
        };
        config::atomic_json(
            &root.path().join("active.json"),
            &serde_json::to_value(&registry).unwrap(),
        )
        .unwrap();
        let manager = SemanticResources::new(root.path().to_owned());
        let task = manager.capture().unwrap().unwrap();
        assert_eq!(task.selection, selection);
        assert!(manager.unload().is_err());
        manager.disable(0, &|| false).unwrap();
        assert!(manager.capture().unwrap().is_none());
        let exclusive = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.path().join("leases").join(format!("{digest}.lock")))
            .unwrap();
        assert!(exclusive.try_lock().is_err());
        let bytes = fs::read(root.path().join("active.json")).unwrap();
        assert!(manager.disable(1, &|| true).is_err());
        assert_eq!(fs::read(root.path().join("active.json")).unwrap(), bytes);
        drop(task);
        exclusive.try_lock().unwrap();
    }
}
