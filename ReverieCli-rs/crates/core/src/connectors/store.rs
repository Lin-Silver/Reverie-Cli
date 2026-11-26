use crate::{Result, config::atomic_json, mcp::config::hash};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
};

#[derive(Clone, Serialize, Deserialize)]
pub(super) struct Record {
    pub server_id: String,
    pub binding: String,
    pub credential_id: String,
    pub kind: String,
    pub resource: String,
    pub issuer: Option<String>,
    pub client_id: Option<String>,
    pub auth_method: Option<String>,
    pub token_endpoint: Option<String>,
    pub revocation_endpoint: Option<String>,
    pub scopes: Vec<String>,
    pub expires_at: Option<i64>,
    pub approved_at: i64,
    pub api_header: Option<String>,
    pub state: String,
}
impl Record {
    pub fn public(&self) -> Value {
        json!({"server_id":self.server_id,"type":self.kind,"resource":self.resource,"issuer":self.issuer,
            "client_id":self.client_id,"scopes":self.scopes,"expires_at":self.expires_at,
            "approved_at":self.approved_at,"api_header":self.api_header,"status":self.state,
            "credential_storage":"system","credential_configured":true})
    }
}
pub(super) struct Store {
    directory: PathBuf,
}
impl Store {
    pub fn new(app: &Path) -> Self {
        Self {
            directory: app.join(".reverie"),
        }
    }
    fn path(&self) -> PathBuf {
        self.directory.join("connectors.json")
    }
    fn load(&self) -> Result<Value> {
        let file = match fs::File::open(self.path()) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(json!({"format":1,"connectors":{},"retired_credentials":[]}));
            }
            Err(error) => return Err(error.into()),
        };
        let mut bytes = Vec::new();
        file.take(4 * 1024 * 1024 + 1).read_to_end(&mut bytes)?;
        if bytes.len() > 4 * 1024 * 1024 {
            return Err("Connector metadata exceeds 4 MiB; original data was preserved.".into());
        }
        let value: Value = serde_json::from_slice(&bytes)?;
        if value["format"] != 1
            || !value["connectors"].is_object()
            || !value["retired_credentials"].is_array()
        {
            return Err("Unsupported Connector metadata; original data was preserved.".into());
        }
        Ok(value)
    }
    pub fn get(&self, server_id: &str) -> Result<Option<Record>> {
        self.load()?["connectors"]
            .get(server_id)
            .map(|value| Ok(serde_json::from_value(value.clone())?))
            .transpose()
    }
    pub fn records(&self) -> Result<Vec<Record>> {
        self.load()?["connectors"]
            .as_object()
            .expect("validated Connector metadata")
            .values()
            .map(|value| Ok(serde_json::from_value(value.clone())?))
            .collect()
    }
    fn update<T>(&self, change: impl FnOnce(&mut Value) -> Result<T>) -> Result<T> {
        fs::create_dir_all(&self.directory)?;
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(self.directory.join("connectors.lock"))?;
        match lock.try_lock() {
            Ok(()) => {}
            Err(fs::TryLockError::WouldBlock) => {
                return Err(
                    "Connector metadata is busy; retry after the active update finishes.".into(),
                );
            }
            Err(fs::TryLockError::Error(error)) => return Err(error.into()),
        }
        let mut document = self.load()?;
        let result = change(&mut document)?;
        if let Ok(bytes) = fs::read(self.path()) {
            let directory = self.directory.join("backups/connectors");
            fs::create_dir_all(&directory)?;
            let backup = directory.join(format!("{}.json", hash(&bytes)));
            if !backup.exists() {
                fs::write(backup, bytes)?;
            }
        }
        atomic_json(&self.path(), &document)?;
        Ok(result)
    }
    pub fn put(&self, record: &Record) -> Result<Option<String>> {
        self.update(|document| {
            let previous = document["connectors"][&record.server_id]["credential_id"]
                .as_str()
                .map(str::to_owned);
            if document["connectors"][&record.server_id].is_null() {
                document["connectors"][&record.server_id] = json!({});
            }
            document["connectors"][&record.server_id]
                .as_object_mut()
                .ok_or("Invalid Connector record.")?
                .extend(
                    serde_json::to_value(record)?
                        .as_object()
                        .expect("serialized Connector record")
                        .clone(),
                );
            document["retired_credentials"]
                .as_array_mut()
                .expect("validated Connector metadata")
                .retain(|value| value.as_str() != Some(record.credential_id.as_str()));
            if let Some(previous) = previous
                .as_ref()
                .filter(|previous| **previous != record.credential_id)
            {
                document["retired_credentials"]
                    .as_array_mut()
                    .expect("validated Connector metadata")
                    .push(json!(previous));
            }
            Ok(previous)
        })
    }
    pub fn prepare_credential(&self, credential_id: &str) -> Result<()> {
        self.update(|document| {
            let retired = document["retired_credentials"]
                .as_array_mut()
                .expect("validated Connector metadata");
            if !retired
                .iter()
                .any(|value| value.as_str() == Some(credential_id))
            {
                retired.push(json!(credential_id));
            }
            Ok(())
        })
    }
    pub fn remove(&self, server_id: &str) -> Result<Option<String>> {
        self.update(|document| {
            let removed = document["connectors"]
                .as_object_mut()
                .expect("validated Connector metadata")
                .remove(server_id);
            let credential =
                removed.and_then(|record| record["credential_id"].as_str().map(str::to_owned));
            if let Some(credential) = &credential {
                document["retired_credentials"]
                    .as_array_mut()
                    .expect("validated Connector metadata")
                    .push(json!(credential));
            }
            Ok(credential)
        })
    }
    pub fn retired(&self) -> Result<Vec<String>> {
        self.load()?["retired_credentials"]
            .as_array()
            .expect("validated Connector metadata")
            .iter()
            .map(|value| {
                value
                    .as_str()
                    .map(str::to_owned)
                    .ok_or("Invalid retired credential identity.".into())
            })
            .collect()
    }
    pub fn cleaned(&self, identities: &[String]) -> Result<()> {
        self.update(|document| {
            document["retired_credentials"]
                .as_array_mut()
                .expect("validated Connector metadata")
                .retain(|value| {
                    !value
                        .as_str()
                        .is_some_and(|value| identities.iter().any(|identity| identity == value))
                });
            Ok(())
        })
    }
    pub fn mutation_lock(&self, binding: &str) -> Result<fs::File> {
        let directory = self.directory.join("connector-locks");
        fs::create_dir_all(&directory)?;
        Ok(fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(directory.join(format!("{}.lock", hash(binding.as_bytes()))))?)
    }
}
