//! On-demand system credential storage. Secret values never enter config files.
use crate::Result;
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use std::{
    fs,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

const PART_SIZE: usize = 2000;
const SECRET_LIMIT: usize = 1024 * 1024;
const MAGIC: &[u8] = b"Reverie/vault-parts/v1\0";
#[derive(Clone, Serialize, Deserialize)]
struct Parts {
    generation: String,
    length: usize,
    count: usize,
    sha256: String,
}
impl Parts {
    fn validate(&self) -> Result<()> {
        if self.length > SECRET_LIMIT
            || self.length <= PART_SIZE
            || self.count != self.length.div_ceil(PART_SIZE)
            || uuid::Uuid::parse_str(&self.generation).is_err()
            || self.sha256.len() != 64
            || !self.sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
        {
            return Err("System credential fragment descriptor is invalid; original entries were preserved.".into());
        }
        Ok(())
    }
}
#[derive(Serialize, Deserialize)]
struct Journal {
    previous: Option<Parts>,
    next: Option<Parts>,
    root_sha256: String,
}
fn native(service: &str, account: &str) -> Result<keyring::Entry> {
    Ok(keyring::Entry::new(service, account)?)
}
fn optional(entry: &keyring::Entry) -> Result<Option<Vec<u8>>> {
    match entry.get_secret() {
        Ok(value) => Ok(Some(value)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(format!("System credential storage is unavailable: {error}").into()),
    }
}
fn erase(entry: &keyring::Entry) -> Result<()> {
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(format!("System credential removal failed: {error}").into()),
    }
}
fn descriptor(bytes: &[u8]) -> Result<Option<Parts>> {
    let Some(bytes) = bytes.strip_prefix(MAGIC) else {
        return Ok(None);
    };
    let parts: Parts = serde_json::from_slice(bytes)?;
    parts.validate()?;
    Ok(Some(parts))
}
fn part_account(account: &str, parts: &Parts, index: usize) -> String {
    format!("{account}/part/{}/{index}", parts.generation)
}
fn erase_parts(service: &str, account: &str, parts: &Parts) -> Result<()> {
    parts.validate()?;
    for index in 0..parts.count {
        erase(&native(service, &part_account(account, parts, index))?)?;
    }
    Ok(())
}
fn recover(service: &str, account: &str, entry: &keyring::Entry) -> Result<Option<Vec<u8>>> {
    let root = optional(entry)?;
    let pending = native(service, &format!("{account}/pending-v1"))?;
    let Some(bytes) = optional(&pending)? else {
        return Ok(root);
    };
    let journal: Journal = serde_json::from_slice(&bytes)?;
    if journal.root_sha256.len() != 64
        || !journal
            .root_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err("System credential recovery record is invalid; entries were preserved.".into());
    }
    if let Some(parts) = &journal.previous {
        parts.validate()?;
    }
    if let Some(parts) = &journal.next {
        parts.validate()?;
    }
    let committed = root
        .as_deref()
        .is_some_and(|bytes| crate::mcp::config::hash(bytes) == journal.root_sha256);
    let obsolete = if committed {
        journal.previous
    } else {
        journal.next
    };
    if let Some(parts) = obsolete {
        erase_parts(service, account, &parts)?;
    }
    erase(&pending)?;
    Ok(root)
}
fn lease(directory: &Path, account: &str) -> Result<fs::File> {
    fs::create_dir_all(directory)?;
    let file = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(directory.join(format!("{account}.lock")))?;
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        match file.try_lock() {
            Ok(()) => return Ok(file),
            Err(fs::TryLockError::WouldBlock) if Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(25))
            }
            Err(fs::TryLockError::WouldBlock) => {
                return Err("Another system credential operation still holds this entry.".into());
            }
            Err(fs::TryLockError::Error(error)) => return Err(error.into()),
        }
    }
}
fn put_native(service: &str, account: &str, secret: &[u8]) -> Result<()> {
    if secret.len() > SECRET_LIMIT {
        return Err("Serialized system credential exceeds 1 MiB.".into());
    }
    let entry = native(service, account)?;
    let mut old = recover(service, account, &entry)?;
    let previous = old.as_deref().map(descriptor).transpose()?.flatten();
    if let Some(old) = &mut old {
        old.fill(0);
    }
    let next = (cfg!(windows) && secret.len() > PART_SIZE).then(|| Parts {
        generation: uuid::Uuid::new_v4().to_string(),
        length: secret.len(),
        count: secret.len().div_ceil(PART_SIZE),
        sha256: crate::mcp::config::hash(secret),
    });
    let mut root = if let Some(next) = &next {
        let mut bytes = MAGIC.to_vec();
        bytes.extend_from_slice(&serde_json::to_vec(next)?);
        bytes
    } else {
        secret.to_vec()
    };
    let journal = if previous.is_some() || next.is_some() {
        Some(Journal {
            previous,
            next: next.clone(),
            root_sha256: crate::mcp::config::hash(&root),
        })
    } else {
        None
    };
    if let Some(journal) = &journal {
        native(service, &format!("{account}/pending-v1"))?
            .set_secret(&serde_json::to_vec(journal)?)?;
    }
    let operation = (|| -> Result<()> {
        if let Some(parts) = &next {
            for (index, bytes) in secret.chunks(PART_SIZE).enumerate() {
                native(service, &part_account(account, parts, index))?.set_secret(bytes)?;
            }
        }
        entry
            .set_secret(&root)
            .map_err(|error| format!("System credential storage failed: {error}").into())
    })();
    root.fill(0);
    if let Err(error) = operation {
        let _ = recover(service, account, &entry);
        return Err(error);
    }
    // A failed cleanup remains journaled; the new root already identifies a complete usable value.
    if journal.is_some() {
        let _ = recover(service, account, &entry);
    }
    Ok(())
}
fn get_native(service: &str, account: &str) -> Result<Option<Vec<u8>>> {
    let entry = native(service, account)?;
    let Some(mut root) = recover(service, account, &entry)? else {
        return Ok(None);
    };
    let Some(parts) = descriptor(&root)? else {
        return Ok(Some(root));
    };
    root.fill(0);
    let mut secret = Vec::with_capacity(parts.length);
    for index in 0..parts.count {
        let mut part = optional(&native(service, &part_account(account, &parts, index))?)?
            .ok_or("System credential fragment is missing; authorization must be restored.")?;
        if part.len() > PART_SIZE || secret.len() + part.len() > parts.length {
            part.fill(0);
            secret.fill(0);
            return Err("System credential fragment length is invalid.".into());
        }
        secret.extend_from_slice(&part);
        part.fill(0);
    }
    if secret.len() != parts.length || crate::mcp::config::hash(&secret) != parts.sha256 {
        secret.fill(0);
        return Err("System credential fragments failed integrity verification.".into());
    }
    Ok(Some(secret))
}
fn remove_native(service: &str, account: &str) -> Result<()> {
    let entry = native(service, account)?;
    if let Some(mut root) = recover(service, account, &entry)? {
        if let Some(parts) = descriptor(&root)? {
            erase_parts(service, account, &parts)?;
        }
        root.fill(0);
    }
    erase(&entry)
}

#[derive(Clone)]
pub struct CredentialStore {
    service: String,
    leases: PathBuf,
}

impl CredentialStore {
    pub fn new(app: &Path) -> Self {
        let identity = app.canonicalize().unwrap_or_else(|_| app.to_owned());
        Self {
            service: format!(
                "Reverie CLI/{}",
                &crate::mcp::config::hash(identity.to_string_lossy().as_bytes())[..20]
            ),
            leases: app.join(".reverie/credential-locks"),
        }
    }
    fn account(id: &str) -> Result<String> {
        if id.is_empty() || id.contains('\0') {
            return Err("Credential identity is required.".into());
        }
        Ok(crate::mcp::config::hash(id.as_bytes()))
    }
    pub async fn put<T: Serialize>(&self, id: &str, value: &T) -> Result<()> {
        let account = Self::account(id)?;
        let service = self.service.clone();
        let directory = self.leases.clone();
        let mut secret = serde_json::to_vec(value)?;
        tokio::task::spawn_blocking(move || -> Result<()> {
            let result = (|| {
                let _lease = lease(&directory, &account)?;
                put_native(&service, &account, &secret)
            })();
            secret.fill(0);
            result
        })
        .await?
    }
    pub async fn get<T: DeserializeOwned + Send + 'static>(&self, id: &str) -> Result<Option<T>> {
        let account = Self::account(id)?;
        let service = self.service.clone();
        let directory = self.leases.clone();
        tokio::task::spawn_blocking(move || -> Result<Option<T>> {
            let _lease = lease(&directory, &account)?;
            let Some(mut secret) = get_native(&service, &account)? else {
                return Ok(None);
            };
            let value = serde_json::from_slice(&secret);
            secret.fill(0);
            Ok(Some(value?))
        })
        .await?
    }
    pub async fn remove(&self, id: &str) -> Result<()> {
        let account = Self::account(id)?;
        let service = self.service.clone();
        let directory = self.leases.clone();
        tokio::task::spawn_blocking(move || -> Result<()> {
            let _lease = lease(&directory, &account)?;
            remove_native(&service, &account)
        })
        .await?
    }
    pub async fn check(&self) -> Result<()> {
        let id = format!("availability/{}", uuid::Uuid::new_v4());
        self.put(&id, &serde_json::json!({"availability":true}))
            .await?;
        self.remove(&id).await
    }
}
