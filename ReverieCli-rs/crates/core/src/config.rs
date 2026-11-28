use serde_json::{Map, Value, json};
use sha1::{Digest, Sha1};
use std::{
    env, fs,
    io::{self, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicBool, Ordering},
};
use uuid::Uuid;

pub fn canonical_project(path: &Path) -> io::Result<PathBuf> {
    let path = path.canonicalize()?;
    if !path.is_dir() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "Project path must be a directory.",
        ));
    }
    #[cfg(windows)]
    {
        let text = path.to_string_lossy();
        if let Some(value) = text.strip_prefix("\\\\?\\UNC\\") {
            return Ok(PathBuf::from(format!("\\\\{value}")));
        }
        if let Some(value) = text.strip_prefix("\\\\?\\") {
            return Ok(PathBuf::from(value));
        }
    }
    Ok(path)
}

pub fn app_root() -> io::Result<PathBuf> {
    if let Some(value) = env::var_os("REVERIE_APP_ROOT") {
        return Ok(PathBuf::from(value));
    }
    env::current_exe()?
        .parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| io::Error::other("Executable has no parent directory."))
}

pub fn project_name(project: &Path) -> String {
    let mut value = String::new();
    for ch in project.to_string_lossy().trim().chars() {
        let ch = if ch < ' ' || "<>:\"/\\|?*".contains(ch) {
            '_'
        } else {
            ch
        };
        if (ch == '_' && value.ends_with('_')) || (ch.is_whitespace() && value.ends_with(' ')) {
            continue;
        }
        value.push(if ch.is_whitespace() { ' ' } else { ch });
    }
    let value: String = value
        .trim_matches([' ', '.', '_'])
        .chars()
        .take(120)
        .collect();
    let reserved = matches!(value.to_uppercase().as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (1..=9).any(|number| {
            value.eq_ignore_ascii_case(&format!("COM{number}"))
                || value.eq_ignore_ascii_case(&format!("LPT{number}"))
        });
    if value.is_empty() || reserved {
        "workspace".into()
    } else {
        value
    }
}

pub fn workspace_metadata(project: &Path) -> Value {
    let normalized = project
        .to_string_lossy()
        .replace('\\', "/")
        .trim_end_matches('/')
        .to_lowercase();
    let digest: String = Sha1::digest(normalized.as_bytes())[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    json!({"workspace_id": digest, "workspace_path": project})
}

pub fn atomic_json(path: &Path, value: &Value) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::other("Configuration path has no parent."))?;
    fs::create_dir_all(parent)?;
    let mut file = tempfile::NamedTempFile::new_in(parent)?;
    serde_json::to_writer_pretty(&mut file, value)?;
    file.write_all(b"\n")?;
    file.as_file().sync_all()?;
    // A Windows reader that omitted FILE_SHARE_DELETE temporarily prevents replacement.
    #[cfg(windows)]
    for ms in [10, 20, 40, 80, 160] {
        match file.persist(path) {
            Ok(_) => return Ok(()),
            Err(error) if matches!(error.error.raw_os_error(), Some(5 | 32 | 33)) => {
                file = error.file;
                std::thread::sleep(std::time::Duration::from_millis(ms));
            }
            Err(error) => return Err(error.error),
        }
    }
    file.persist(path).map(|_| ()).map_err(|error| error.error)
}

pub struct ConfigStore {
    pub path: PathBuf,
    backup_taken: AtomicBool,
}

// Once both replacements have committed, the main index remains editable by older clients.
// During a split-file write the newer inventory carries the index that belongs to its rows.
fn pending_standard_index(
    root: &Map<String, Value>,
    profile: &Map<String, Value>,
) -> Option<usize> {
    let revision = profile.get("selection_revision")?.as_str()?;
    if root
        .get("standard_selection_revision")
        .and_then(Value::as_str)
        == Some(revision)
    {
        return None;
    }
    profile
        .get("active_model_index")?
        .as_u64()
        .map(|index| index as usize)
}

impl ConfigStore {
    pub fn new(app: &Path) -> Self {
        Self::at(app.join(".reverie/config.json"))
    }

    pub fn at(path: PathBuf) -> Self {
        Self {
            path,
            backup_taken: AtomicBool::new(false),
        }
    }

    pub fn load(&self) -> io::Result<Value> {
        match fs::read(&self.path) {
            Ok(bytes) => {
                let value: Value = serde_json::from_slice(
                    bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&bytes),
                )?;
                if !value.is_object() {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "Configuration must be a JSON object.",
                    ));
                }
                Ok(value)
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(
                json!({"models":[], "active_model_index":0, "active_model_source":"standard", "mode":"reverie", "auto_index":true, "stream_responses":true, "max_context_tokens":128000}),
            ),
            Err(error) => Err(error),
        }
    }

    pub fn update(
        &self,
        edit: impl FnOnce(&mut Map<String, Value>) -> io::Result<()>,
    ) -> io::Result<Value> {
        self.update_if(|fields| {
            edit(fields)?;
            Ok(true)
        })
    }

    fn update_if(
        &self,
        edit: impl FnOnce(&mut Map<String, Value>) -> io::Result<bool>,
    ) -> io::Result<Value> {
        let parent = self
            .path
            .parent()
            .ok_or_else(|| io::Error::other("Missing configuration parent."))?;
        fs::create_dir_all(parent)?;
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(parent.join("config.lock"))?;
        lock.lock()?;
        let mut value = self.load()?;
        if !edit(
            value
                .as_object_mut()
                .expect("load validates the configuration object"),
        )? {
            return Ok(value);
        }
        if self.path.exists() && !self.backup_taken.load(Ordering::Acquire) {
            let backup = parent.join("backups");
            fs::create_dir_all(&backup)?;
            let bytes = fs::read(&self.path)?;
            let file = backup.join(format!(
                "config.before-rust-3.0-{}.json",
                Uuid::new_v4().simple()
            ));
            let mut output = fs::OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(file)?;
            output.write_all(&bytes)?;
            output.sync_all()?;
            self.backup_taken.store(true, Ordering::Release);
        }
        atomic_json(&self.path, &value)?;
        Ok(value)
    }

    fn provider_path(&self, filename: &Value) -> io::Result<PathBuf> {
        let filename = filename
            .as_str()
            .ok_or_else(|| io::Error::other("Provider profile filename must be text."))?;
        if !filename.ends_with(".json")
            || filename.contains(['/', '\\', ':'])
            || filename.starts_with('.')
        {
            return Err(io::Error::other("Invalid provider profile filename."));
        }
        Ok(self.path.parent().unwrap().join("Providers").join(filename))
    }

    pub(crate) fn update_modelscope(
        &self,
        activate: bool,
        edit: impl FnOnce(&mut Value) -> io::Result<()>,
    ) -> io::Result<Value> {
        let mut selected = Value::Null;
        self.update_if(|root| {
            let apply = |section: &mut Value| {
                if section.is_null() {
                    *section = json!({});
                }
                if !section.is_object() {
                    return Err(io::Error::other("Invalid ModelScope configuration."));
                }
                let previous = section.clone();
                edit(section)?;
                selected = section.clone();
                Ok(previous != *section)
            };
            let changed = if let Some(file) = root
                .get("provider_files")
                .and_then(|files| files.get("modelscope"))
            {
                Self::at(self.provider_path(file)?).update_if(|profile| {
                    if profile.get("provider_id").and_then(Value::as_str) != Some("modelscope") {
                        return Err(io::Error::other("Provider profile identity mismatch."));
                    }
                    apply(profile.entry("chat").or_insert_with(|| json!({})))
                })?;
                false
            } else {
                apply(root.entry("modelscope").or_insert_with(|| json!({})))?
            };
            let switched = activate
                && root.get("active_model_source").and_then(Value::as_str) != Some("modelscope");
            if switched {
                root.insert("active_model_source".into(), json!("modelscope"));
            }
            Ok(changed || switched)
        })?;
        Ok(selected)
    }

    pub fn update_standard_models(
        &self,
        edit: impl FnOnce(&mut Vec<Value>, &mut usize) -> io::Result<()>,
    ) -> io::Result<()> {
        self.update(|root| {
            let mut active = root
                .get("active_model_index")
                .and_then(Value::as_u64)
                .unwrap_or(0) as usize;
            let apply = |fields: &mut Map<String, Value>, active: &mut usize| {
                let items = fields
                    .entry("models")
                    .or_insert_with(|| json!([]))
                    .as_array_mut()
                    .ok_or_else(|| io::Error::other("Models must be an array."))?;
                crate::models::fill_profile_ids(items);
                edit(items, active)
            };
            if let Some(file) = root
                .get("provider_files")
                .and_then(|files| files.get("standard"))
            {
                let store = Self::at(self.provider_path(file)?);
                let revision = Uuid::new_v4().simple().to_string();
                store.update(|profile| {
                    if profile.get("provider_id") != Some(&json!("standard"))
                        || !profile.get("models").is_some_and(Value::is_array)
                    {
                        return Err(io::Error::other("Invalid standard provider inventory."));
                    }
                    if let Some(saved) = pending_standard_index(root, profile) {
                        active = saved;
                    }
                    apply(profile, &mut active)?;
                    // The inventory and its index must survive a process exit between file replacements.
                    profile.insert("active_model_index".into(), json!(active));
                    profile.insert("selection_revision".into(), json!(revision));
                    Ok(())
                })?;
                root.insert("standard_selection_revision".into(), json!(revision));
            } else {
                apply(root, &mut active)?;
            }
            root.insert("active_model_index".into(), json!(active));
            Ok(())
        })?;
        Ok(())
    }

    pub fn effective(&self) -> io::Result<Value> {
        let mut value = self.load()?;
        let files = value
            .get("provider_files")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        for (source, filename) in files {
            let path = self.provider_path(&filename)?;
            let bytes = fs::read(path)?;
            let profile: Value =
                serde_json::from_slice(bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&bytes))?;
            if profile["provider_id"] != source {
                return Err(io::Error::other("Provider profile identity mismatch."));
            }
            if source == "standard" {
                if !profile["models"].is_array() {
                    return Err(io::Error::other("Provider inventory must be an array."));
                }
                value["models"] = profile["models"].clone();
                if let Some(index) =
                    pending_standard_index(value.as_object().unwrap(), profile.as_object().unwrap())
                {
                    value["active_model_index"] = json!(index);
                    value["standard_selection_revision"] = profile["selection_revision"].clone();
                }
            } else if let Some(chat) = profile.get("chat") {
                value[&source] = chat.clone();
            }
        }
        if let Some(items) = value["models"].as_array_mut() {
            crate::models::fill_profile_ids(items);
        }
        if !value["modelscope"].is_null() && !value["modelscope"].is_object() {
            return Err(io::Error::other("Invalid ModelScope configuration."));
        }
        Ok(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_inventory_recovers_its_index_until_the_main_file_is_committed() {
        let dir = tempfile::tempdir().unwrap();
        let store = ConfigStore::new(dir.path());
        let mut root = json!({"active_model_index":0, "standard_selection_revision":"old", "provider_files":{"standard":"manual.json"}});
        atomic_json(&store.path, &root).unwrap();
        atomic_json(
            &store.provider_path(&json!("manual.json")).unwrap(),
            &json!({
                "provider_id":"standard", "models":[{"model":"one"},{"model":"two"}],
                "active_model_index":1, "selection_revision":"new"
            }),
        )
        .unwrap();
        assert_eq!(store.effective().unwrap()["active_model_index"], 1);
        root["standard_selection_revision"] = json!("new");
        atomic_json(&store.path, &root).unwrap();
        assert_eq!(store.effective().unwrap()["active_model_index"], 0);
    }

    #[test]
    fn updates_preserve_unknown_configuration_and_backup_original_bytes() {
        let dir = tempfile::tempdir().unwrap();
        let store = ConfigStore::new(dir.path());
        let before = json!({"models":[], "extension_private":{"token":"keep locally", "nested":["中文", "😀"]}});
        atomic_json(&store.path, &before).unwrap();
        let original = fs::read(&store.path).unwrap();
        let updated = store
            .update(|fields| {
                fields.insert("mode".into(), json!("writer"));
                Ok(())
            })
            .unwrap();
        assert_eq!(updated["extension_private"], before["extension_private"]);
        let backup = fs::read_dir(dir.path().join(".reverie/backups"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        assert_eq!(fs::read(backup).unwrap(), original);
        assert_eq!(store.load().unwrap()["mode"], "writer");
    }

    #[test]
    fn failed_edits_leave_the_existing_configuration_unchanged() {
        let dir = tempfile::tempdir().unwrap();
        let store = ConfigStore::new(dir.path());
        atomic_json(&store.path, &json!({"mode":"reverie"})).unwrap();
        let before = fs::read(&store.path).unwrap();
        assert!(
            store
                .update(|fields| {
                    fields.insert("mode".into(), json!("gamer"));
                    Err(io::Error::other("reject invalid setting"))
                })
                .is_err()
        );
        assert_eq!(fs::read(&store.path).unwrap(), before);
    }

    #[cfg(windows)]
    #[test]
    fn atomic_replacement_survives_a_short_lived_windows_reader() {
        use std::{os::windows::fs::OpenOptionsExt, thread, time::Duration};
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("catalog.json");
        atomic_json(&path, &json!({"revision":1})).unwrap();
        let reader = fs::OpenOptions::new()
            .read(true)
            .share_mode(1)
            .open(&path)
            .unwrap();
        let finish = thread::spawn(move || {
            thread::sleep(Duration::from_millis(90));
            drop(reader);
        });
        let result = atomic_json(&path, &json!({"revision":2}));
        finish.join().unwrap();
        result.unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&fs::read(path).unwrap()).unwrap(),
            json!({"revision":2})
        );
    }
}
