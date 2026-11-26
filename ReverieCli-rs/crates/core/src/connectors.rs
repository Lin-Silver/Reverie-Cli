//! MCP authorization uses public metadata and stores credentials only in the OS vault.
mod callback;
mod metadata;
mod oauth;
mod store;
#[cfg(test)]
mod tests;

use crate::{
    Result,
    credentials::CredentialStore,
    mcp::{Notify, ServerConfig},
};
pub use metadata::OAuthDiscovery;
pub use oauth::AuthorizationChoice;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    fs,
    path::Path,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
};
use tokio::{sync::oneshot, task::JoinHandle};
use tokio_util::sync::CancellationToken;

struct Pending {
    id: String,
    server_id: String,
    binding: String,
    resource: String,
    issuer: metadata::Issuer,
    client: oauth::ClientRegistration,
    scopes: Vec<String>,
    required_scopes: Vec<String>,
    verifier: String,
    redirect_uri: String,
    created_at: i64,
    status: Arc<Mutex<String>>,
    receiver: tokio::sync::Mutex<Option<oneshot::Receiver<Result<String>>>>,
    claimed: AtomicBool,
    cancel: CancellationToken,
    callback: JoinHandle<()>,
}
impl Drop for Pending {
    fn drop(&mut self) {
        self.cancel.cancel();
        self.callback.abort();
    }
}
#[derive(Serialize, Deserialize)]
#[serde(tag = "type")]
enum StoredCredential {
    #[serde(rename = "oauth")]
    OAuth {
        binding: String,
        resource: String,
        issuer: String,
        token_endpoint: String,
        revocation_endpoint: Option<String>,
        client: oauth::ClientRegistration,
        token: Box<oauth::Token>,
    },
    #[serde(rename = "api_key")]
    ApiKey {
        binding: String,
        header: String,
        value: String,
    },
}
pub struct ConnectorManager {
    store: store::Store,
    credentials: CredentialStore,
    client: reqwest::Client,
    discoveries: Mutex<HashMap<String, OAuthDiscovery>>,
    pending: Mutex<HashMap<String, Arc<Pending>>>,
    shutdown: CancellationToken,
}
impl Drop for ConnectorManager {
    fn drop(&mut self) {
        self.cancel_all();
    }
}
impl ConnectorManager {
    pub fn new(app: &Path) -> Result<Self> {
        Ok(Self {
            store: store::Store::new(app),
            credentials: CredentialStore::new(app),
            client: reqwest::Client::builder()
                .connect_timeout(std::time::Duration::from_secs(10))
                .timeout(std::time::Duration::from_secs(15))
                .redirect(reqwest::redirect::Policy::none())
                .retry(reqwest::retry::never())
                .build()?,
            discoveries: Mutex::new(HashMap::new()),
            pending: Mutex::new(HashMap::new()),
            shutdown: CancellationToken::new(),
        })
    }
    /// Does not send configured credentials, register a client, or start an MCP server.
    pub async fn discover(
        &self,
        server: &ServerConfig,
        cancel: &CancellationToken,
    ) -> Result<OAuthDiscovery> {
        self.discover_with_challenge(server, None, cancel).await
    }
    /// Only the kernel may supply a captured challenge; user/model strings are not trusted transport evidence.
    pub async fn discover_with_challenge(
        &self,
        server: &ServerConfig,
        challenge: Option<&str>,
        cancel: &CancellationToken,
    ) -> Result<OAuthDiscovery> {
        let discovery = tokio::select! {_=self.shutdown.cancelled()=>return Err("Connector manager is stopping.".into()),result=metadata::discover(&self.client, server, challenge, cancel)=>result?};
        let mut discoveries = self
            .discoveries
            .lock()
            .map_err(|_| "Connector discovery registry lock was poisoned.")?;
        discoveries
            .retain(|_, discovery| discovery.created_at + 600 > chrono::Utc::now().timestamp());
        discoveries.insert(discovery.id.clone(), discovery.clone());
        Ok(discovery)
    }
    pub fn list(&self) -> Result<Value> {
        let now = chrono::Utc::now().timestamp();
        let mut pending = self
            .pending
            .lock()
            .map_err(|_| "Connector authorization registry lock was poisoned.")?;
        pending.retain(|_, pending| {
            let keep = pending.created_at + 600 > now;
            if !keep {
                pending.cancel.cancel();
            }
            keep
        });
        Ok(
            json!({"connectors":self.store.records()?.iter().map(|record| {
                let mut value=record.public();
                value["status"]=json!("configuration_unverified");
                value["configuration_current"]=json!(false);
                value
            }).collect::<Vec<_>>(),
            "pending":pending.values().map(|pending|json!({"authorization_id":pending.id,"server_id":pending.server_id,
                "resource":pending.resource,"issuer":pending.issuer.url,"scopes":pending.scopes,
                "status":pending.status.lock().unwrap_or_else(|error|error.into_inner()).as_str(),"expires_at":pending.created_at+600})).collect::<Vec<_>>(),
            "pending_credential_cleanup":self.store.retired()?.len()}),
        )
    }
    /// Pass all currently valid configurations, including disabled/out-of-mode entries.
    /// Missing or changed configurations never inherit an old authorized status.
    pub fn list_configured(&self, servers: &[ServerConfig]) -> Result<Value> {
        let mut result = self.list()?;
        let records = self.store.records()?;
        let mut connectors = Vec::new();
        let mut current = std::collections::HashSet::new();
        for server in servers {
            if !current.insert(server.id()) {
                continue;
            }
            if server.transport != crate::mcp::Transport::Stdio
                || records.iter().any(|record| record.server_id == server.id())
            {
                connectors.push(self.status(server)?);
            }
        }
        for record in records
            .iter()
            .filter(|record| !current.contains(&record.server_id))
        {
            let mut value = record.public();
            value["status"] = json!("configuration_missing");
            value["configuration_current"] = json!(false);
            value["authorization_required"] = json!(true);
            connectors.push(value);
        }
        result["connectors"] = json!(connectors);
        if let Some(pending) = result["pending"].as_array_mut() {
            let registry = self
                .pending
                .lock()
                .map_err(|_| "Connector authorization registry lock was poisoned.")?;
            for item in pending {
                let id = item["server_id"].as_str().unwrap_or("");
                let matching = servers.iter().find(|server| server.id() == id);
                let authorization = item["authorization_id"]
                    .as_str()
                    .and_then(|id| registry.get(id));
                item["configuration_current"] = json!(matching.is_some_and(|server| {
                    server.enabled
                        && server.trusted
                        && authorization
                            .is_some_and(|pending| pending.binding == metadata::binding(server))
                }));
            }
        }
        Ok(result)
    }
    pub fn status(&self, server: &ServerConfig) -> Result<Value> {
        let record = self.store.get(&server.id())?;
        let changed = record
            .as_ref()
            .is_some_and(|record| record.binding != metadata::binding(server));
        let mut result=record.as_ref().map(store::Record::public).unwrap_or_else(||json!({"server_id":server.id(),"status":"not_authorized","credential_configured":false}));
        result["configuration_current"] = json!(!changed);
        result["enabled"] = json!(server.enabled);
        result["trust"] = json!(server.trusted);
        result["current_target"] = json!(server.public()["url"]);
        if changed {
            result["status"] = json!("target_changed");
            result["authorization_required"] = json!(true);
        } else if !server.enabled {
            result["status"] = json!("disabled");
        } else if !server.trusted {
            result["status"] = json!("untrusted");
        }
        Ok(result)
    }
    async fn mutation_lock(
        &self,
        server: &ServerConfig,
        cancel: &CancellationToken,
    ) -> Result<fs::File> {
        self.mutation_lock_id(&server.id(), cancel).await
    }
    async fn mutation_lock_id(
        &self,
        server_id: &str,
        cancel: &CancellationToken,
    ) -> Result<fs::File> {
        let file = self.store.mutation_lock(server_id)?;
        let operation = async {
            loop {
                match file.try_lock() {
                    Ok(()) => return Ok(file),
                    Err(fs::TryLockError::WouldBlock) => {}
                    Err(fs::TryLockError::Error(error)) => return Err(error.into()),
                }
                tokio::time::sleep(std::time::Duration::from_millis(50)).await;
            }
        };
        tokio::select! {
            _=self.shutdown.cancelled()=>Err("Connector manager is stopping.".into()),
            _=cancel.cancelled()=>Err("Connector operation cancelled before acquiring its credential lease.".into()),
            result=tokio::time::timeout(std::time::Duration::from_secs(15),operation)=>result.unwrap_or_else(|_|Err("Another Connector operation still holds this credential lease.".into())),
        }
    }
    pub async fn begin_authorization(
        &self,
        server: &ServerConfig,
        discovery_id: &str,
        choice: AuthorizationChoice,
        notify: Notify,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        if !choice.confirmed {
            return Err(
                "Confirm the Connector target, issuer, scopes and registration before authorizing."
                    .into(),
            );
        }
        let _lease = self.mutation_lock(server, cancel).await?;
        let now = chrono::Utc::now().timestamp();
        {
            let mut pending = self
                .pending
                .lock()
                .map_err(|_| "Connector authorization registry lock was poisoned.")?;
            pending.retain(|_, pending| {
                let keep = pending.created_at + 600 > now;
                if !keep {
                    pending.cancel.cancel();
                }
                keep
            });
            if pending
                .values()
                .any(|pending| pending.server_id == server.id())
            {
                return Err("This Connector already has a pending authorization; finish or cancel it first.".into());
            }
            if pending.len() >= 32 {
                return Err("Too many Connector authorizations are pending.".into());
            }
        }
        let discovery = self
            .discoveries
            .lock()
            .map_err(|_| "Connector discovery registry lock was poisoned.")?
            .remove(discovery_id)
            .ok_or(
                "Connector discovery is absent or was already used; refresh it before authorizing.",
            )?;
        if discovery.server_id != server.id()
            || discovery.binding != metadata::binding(server)
            || discovery.created_at + 600 <= now
        {
            return Err(
                "Connector target or metadata changed; refresh and confirm it again.".into(),
            );
        }
        let issuer = discovery
            .issuers
            .iter()
            .find(|issuer| issuer.url == choice.issuer)
            .cloned()
            .ok_or("Select an authorization server from this discovery result.")?;
        let mut scopes = Vec::new();
        for scope in &choice.scopes {
            metadata::validate_scope(scope)?;
            if !scopes.contains(scope) {
                scopes.push(scope.clone());
            }
        }
        if !discovery
            .required_scopes
            .iter()
            .all(|required| scopes.contains(required))
        {
            return Err("The confirmed scopes do not satisfy this MCP challenge.".into());
        }
        self.credentials.check().await?;
        let callback = callback::Callback::bind(choice.redirect_uri.as_deref()).await?;
        let client = oauth::registration(
            &self.client,
            &issuer,
            &choice,
            &callback.redirect_uri,
            cancel,
        )
        .await?;
        let verifier = oauth::verifier();
        let state = format!(
            "{}{}",
            uuid::Uuid::new_v4().simple(),
            uuid::Uuid::new_v4().simple()
        );
        let authorization_url = oauth::authorization_url(
            &issuer,
            &client,
            &discovery.resource,
            &callback.redirect_uri,
            &scopes,
            &state,
            &verifier,
        )?;
        let id = uuid::Uuid::new_v4().to_string();
        let cancellation = self.shutdown.child_token();
        let callback_cancel = cancellation.clone();
        let (sender, receiver) = oneshot::channel();
        let status = Arc::new(Mutex::new("awaiting_authorization".into()));
        let callback_status = status.clone();
        let callback_id = id.clone();
        let callback_server = server.id();
        let sink = notify.clone();
        let callback_notify: Notify = Arc::new(move |mut event| {
            *callback_status
                .lock()
                .unwrap_or_else(|error| error.into_inner()) =
                event["status"].as_str().unwrap_or("error").into();
            event["authorization_id"] = json!(callback_id);
            event["server_id"] = json!(callback_server);
            sink(event);
        });
        let redirect_uri = callback.redirect_uri.clone();
        let issuer_url = issuer.url.clone();
        let response_issuer = issuer.response_issuer;
        let task = tokio::spawn(async move {
            let result = callback
                .wait(
                    &state,
                    &issuer_url,
                    response_issuer,
                    &callback_cancel,
                    callback_notify,
                )
                .await;
            let _ = sender.send(result);
        });
        let public = json!({"authorization_id":id,"server_id":server.id(),"authorization_url":authorization_url,
            "resource":discovery.resource,"issuer":issuer.url,"client_id":client.client_id,"scopes":scopes,
            "redirect_uri":redirect_uri,"status":"awaiting_authorization","expires_at":now+600});
        self.pending
            .lock()
            .map_err(|_| "Connector authorization registry lock was poisoned.")?
            .insert(
                id.clone(),
                Arc::new(Pending {
                    id: id.clone(),
                    server_id: server.id(),
                    binding: discovery.binding,
                    resource: discovery.resource,
                    issuer,
                    client,
                    scopes,
                    required_scopes: discovery.required_scopes,
                    verifier,
                    redirect_uri,
                    created_at: now,
                    status,
                    receiver: tokio::sync::Mutex::new(Some(receiver)),
                    claimed: AtomicBool::new(false),
                    cancel: cancellation,
                    callback: task,
                }),
            );
        notify(
            json!({"type":"connector.authorization","authorization_id":id,"server_id":server.id(),"status":"awaiting_authorization"}),
        );
        Ok(public)
    }
    pub fn cancel_authorization(&self, authorization_id: &str) -> Result<Value> {
        let pending = self
            .pending
            .lock()
            .map_err(|_| "Connector authorization registry lock was poisoned.")?
            .remove(authorization_id)
            .ok_or("Connector authorization is no longer pending.")?;
        pending.cancel.cancel();
        Ok(
            json!({"authorization_id":pending.id,"server_id":pending.server_id,"status":"cancelled"}),
        )
    }
    async fn persist(&self, record: &store::Record, credential: &StoredCredential) -> Result<()> {
        // A cancelled vault write may finish in its blocking worker. Keep its identity
        // recoverable before starting it, so local removal can serialize and clean it.
        self.store.prepare_credential(&record.credential_id)?;
        self.credentials
            .put(&record.credential_id, credential)
            .await?;
        if let Err(error) = self.store.put(record) {
            self.credentials.remove(&record.credential_id).await?;
            return Err(error);
        }
        self.cleanup_retired().await?;
        Ok(())
    }
    async fn cleanup_retired(&self) -> Result<()> {
        let active = self
            .store
            .records()?
            .into_iter()
            .map(|record| record.credential_id)
            .collect::<std::collections::HashSet<_>>();
        let mut cleaned = Vec::new();
        for identity in self.store.retired()? {
            if !active.contains(&identity) && self.credentials.remove(&identity).await.is_ok() {
                cleaned.push(identity);
            }
        }
        if !cleaned.is_empty() {
            self.store.cleaned(&cleaned)?;
        }
        Ok(())
    }
    /// The callback and exchange are claimed once; neither an authorization code nor a sent request is replayed.
    pub async fn complete_authorization(
        &self,
        server: &ServerConfig,
        authorization_id: &str,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        let pending = self
            .pending
            .lock()
            .map_err(|_| "Connector authorization registry lock was poisoned.")?
            .get(authorization_id)
            .cloned()
            .ok_or("Connector authorization is no longer pending.")?;
        if pending.server_id != server.id()
            || pending.binding != metadata::binding(server)
            || pending.created_at + 600 <= chrono::Utc::now().timestamp()
        {
            return Err(
                "Connector target changed or authorization expired; refresh and confirm it again."
                    .into(),
            );
        }
        if pending.claimed.swap(true, Ordering::AcqRel) {
            return Err(
                "This Connector authorization is already being completed and will not be replayed."
                    .into(),
            );
        }
        let operation = async {
            let receiver = pending
                .receiver
                .lock()
                .await
                .take()
                .ok_or("Connector callback was already consumed.")?;
            let code = receiver
                .await
                .map_err(|_| "Connector callback closed before an authorization response.")??;
            let _lease = self.mutation_lock(server, cancel).await?;
            *pending
                .status
                .lock()
                .unwrap_or_else(|error| error.into_inner()) = "exchanging_code".into();
            let token = oauth::exchange(
                &self.client,
                oauth::CodeGrant {
                    issuer: &pending.issuer,
                    registration: &pending.client,
                    resource: &pending.resource,
                    redirect: &pending.redirect_uri,
                    verifier: &pending.verifier,
                    approved: &pending.scopes,
                },
                &code,
                cancel,
            )
            .await?;
            if !pending
                .required_scopes
                .iter()
                .all(|scope| token.scopes.contains(scope))
            {
                return Err("The authorization server did not grant all required scopes; the token was not activated.".into());
            }
            let record = store::Record {
                server_id: server.id(),
                binding: pending.binding.clone(),
                credential_id: format!("mcp/{}/{}", pending.binding, uuid::Uuid::new_v4()),
                kind: "oauth".into(),
                resource: pending.resource.clone(),
                issuer: Some(pending.issuer.url.clone()),
                client_id: Some(pending.client.client_id.clone()),
                auth_method: Some(pending.client.auth_method.clone()),
                token_endpoint: Some(pending.issuer.token_endpoint.clone()),
                revocation_endpoint: pending.issuer.revocation_endpoint.clone(),
                scopes: token.scopes.clone(),
                expires_at: token.expires_at,
                approved_at: chrono::Utc::now().timestamp(),
                api_header: None,
                state: "authorized".into(),
            };
            self.persist(
                &record,
                &StoredCredential::OAuth {
                    binding: pending.binding.clone(),
                    resource: pending.resource.clone(),
                    issuer: pending.issuer.url.clone(),
                    token_endpoint: pending.issuer.token_endpoint.clone(),
                    revocation_endpoint: pending.issuer.revocation_endpoint.clone(),
                    client: pending.client.clone(),
                    token: Box::new(token),
                },
            )
            .await?;
            Ok(record.public())
        };
        let result = tokio::select! {
            _=self.shutdown.cancelled()=>Err("Connector manager stopped during authorization; a new authorization is required.".into()),
            _=pending.cancel.cancelled()=>Err("Connector authorization cancelled; a transmitted request was not replayed.".into()),
            _=cancel.cancelled()=>Err("Connector authorization interrupted; a transmitted request was not replayed.".into()),
            result=operation=>result,
        };
        self.pending
            .lock()
            .map_err(|_| "Connector authorization registry lock was poisoned.")?
            .remove(authorization_id);
        result
    }
    pub async fn set_api_key(
        &self,
        server: &ServerConfig,
        header: &str,
        secret: &str,
        confirmed: bool,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        if !confirmed {
            return Err(
                "Confirm the Connector endpoint and credential header before saving an API key."
                    .into(),
            );
        }
        if server.transport == crate::mcp::Transport::Stdio {
            return Err("Stdio MCP credentials belong in its environment configuration.".into());
        }
        let name = reqwest::header::HeaderName::from_bytes(header.as_bytes())?;
        if [
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "accept",
            "content-type",
            "mcp-session-id",
            "mcp-protocol-version",
        ]
        .contains(&name.as_str())
        {
            return Err("The API key cannot replace an HTTP or MCP protocol header.".into());
        }
        if secret.is_empty() || secret.len() > 65536 {
            return Err("A nonempty API credential of at most 65536 bytes is required.".into());
        }
        reqwest::header::HeaderValue::from_str(secret)?;
        metadata::secure_url(&server.endpoint, true)?;
        let _lease = self.mutation_lock(server, cancel).await?;
        let binding = metadata::binding(server);
        let record = store::Record {
            server_id: server.id(),
            binding: binding.clone(),
            credential_id: format!("mcp/{}/{}", binding, uuid::Uuid::new_v4()),
            kind: "api_key".into(),
            resource: metadata::public_url(&server.endpoint),
            issuer: None,
            client_id: None,
            auth_method: None,
            token_endpoint: None,
            revocation_endpoint: None,
            scopes: Vec::new(),
            expires_at: None,
            approved_at: chrono::Utc::now().timestamp(),
            api_header: Some(name.to_string()),
            state: "authorized".into(),
        };
        self.persist(
            &record,
            &StoredCredential::ApiKey {
                binding,
                header: name.to_string(),
                value: secret.into(),
            },
        )
        .await?;
        Ok(record.public())
    }
    /// Returned headers are private transport data. Never serialize them into SDK results or model context.
    pub async fn headers(
        &self,
        server: &ServerConfig,
        cancel: &CancellationToken,
    ) -> Result<std::collections::BTreeMap<String, String>> {
        if !server.enabled || !server.trusted {
            return Ok(std::collections::BTreeMap::new());
        }
        let _lease = self.mutation_lock(server, cancel).await?;
        let Some(mut record) = self.store.get(&server.id())? else {
            return Ok(std::collections::BTreeMap::new());
        };
        if record.binding != metadata::binding(server) {
            return Err("Connector endpoint changed; confirm and authorize its new target.".into());
        }
        if record.state != "authorized" {
            return Err(
                "Connector requires authorization again; its previous request was not replayed."
                    .into(),
            );
        }
        let credential = self
            .credentials
            .get::<StoredCredential>(&record.credential_id)
            .await?
            .ok_or("Connector credential is unavailable in system storage; authorize again.")?;
        match credential {
            StoredCredential::ApiKey {
                binding,
                header,
                value,
            } => {
                if binding != record.binding
                    || record.kind != "api_key"
                    || record.api_header.as_ref() != Some(&header)
                {
                    return Err(
                        "Stored Connector credential does not match its approved binding.".into(),
                    );
                }
                reqwest::header::HeaderName::from_bytes(header.as_bytes())?;
                reqwest::header::HeaderValue::from_str(&value)?;
                Ok(std::collections::BTreeMap::from([(header, value)]))
            }
            StoredCredential::OAuth {
                binding,
                resource,
                issuer,
                token_endpoint,
                revocation_endpoint,
                client,
                mut token,
            } => {
                if binding != record.binding
                    || resource != record.resource
                    || record.kind != "oauth"
                    || record.issuer.as_ref() != Some(&issuer)
                    || record.client_id.as_ref() != Some(&client.client_id)
                    || record.auth_method.as_ref() != Some(&client.auth_method)
                    || record.token_endpoint.as_ref() != Some(&token_endpoint)
                    || record.revocation_endpoint != revocation_endpoint
                {
                    return Err("Stored OAuth credentials or endpoints do not match the approved resource, issuer and client.".into());
                }
                if token
                    .expires_at
                    .is_some_and(|expiry| expiry <= chrono::Utc::now().timestamp() + 30)
                {
                    let refreshed = tokio::select! {
                        _=self.shutdown.cancelled()=>Err(Box::new(crate::mcp::Failure {message:"Connector stopped during refresh; delivery is uncertain.".into(),delivery:crate::mcp::Delivery::Unknown,authorization:None}) as Box<dyn std::error::Error+Send+Sync>),
                        result=oauth::refresh(&self.client,&token_endpoint,&client,&resource,&token,cancel)=>result,
                    };
                    match refreshed {
                        Ok(refreshed) => *token = refreshed,
                        Err(error) => {
                            if !error
                                .downcast_ref::<crate::mcp::Failure>()
                                .is_some_and(|failure| {
                                    failure.delivery == crate::mcp::Delivery::NotStarted
                                })
                            {
                                record.state =
                                    if error.downcast_ref::<crate::mcp::Failure>().is_some_and(
                                        |failure| failure.delivery == crate::mcp::Delivery::Unknown,
                                    ) {
                                        "refresh_uncertain"
                                    } else {
                                        "reauthorization_required"
                                    }
                                    .into();
                                self.store.put(&record)?;
                            }
                            return Err(error);
                        }
                    }
                    record.expires_at = token.expires_at;
                    record.scopes = token.scopes.clone();
                    self.credentials
                        .put(
                            &record.credential_id,
                            &StoredCredential::OAuth {
                                binding: binding.clone(),
                                resource: resource.clone(),
                                issuer: issuer.clone(),
                                token_endpoint: token_endpoint.clone(),
                                revocation_endpoint: revocation_endpoint.clone(),
                                client: client.clone(),
                                token: token.clone(),
                            },
                        )
                        .await?;
                    self.store.put(&record)?;
                }
                reqwest::header::HeaderValue::from_str(&format!("Bearer {}", token.access_token))?;
                Ok(std::collections::BTreeMap::from([(
                    "authorization".into(),
                    format!("Bearer {}", token.access_token),
                )]))
            }
        }
    }
    pub async fn revoke(&self, server: &ServerConfig, cancel: &CancellationToken) -> Result<Value> {
        let _lease = self.mutation_lock(server, cancel).await?;
        let Some(record) = self.store.get(&server.id())? else {
            return Ok(
                json!({"server_id":server.id(),"status":"not_authorized","server_revocation":"not_needed"}),
            );
        };
        let mut remote = "not_applicable";
        let mut warning = None;
        if record.binding == metadata::binding(server) {
            if let Some(StoredCredential::OAuth {
                binding,
                resource,
                issuer,
                token_endpoint,
                revocation_endpoint,
                client,
                token,
            }) = self
                .credentials
                .get::<StoredCredential>(&record.credential_id)
                .await?
            {
                if binding != record.binding
                    || resource != record.resource
                    || record.issuer.as_ref() != Some(&issuer)
                    || record.token_endpoint.as_ref() != Some(&token_endpoint)
                    || record.revocation_endpoint != revocation_endpoint
                    || record.client_id.as_ref() != Some(&client.client_id)
                {
                    return Err(
                        "Stored OAuth revocation binding does not match the approved Connector."
                            .into(),
                    );
                }
                remote = if revocation_endpoint.is_some() {
                    "accepted"
                } else {
                    "unsupported"
                };
                if let Some(endpoint) = revocation_endpoint {
                    let tokens = token
                        .refresh_token
                        .iter()
                        .map(|token| (token.as_str(), "refresh_token"))
                        .chain(std::iter::once((
                            token.access_token.as_str(),
                            "access_token",
                        )));
                    for (token, hint) in tokens {
                        if let Err(error) =
                            oauth::revoke(&self.client, &endpoint, &client, token, hint, cancel)
                                .await
                        {
                            remote = "unverified";
                            warning = Some(error.to_string());
                            break;
                        }
                    }
                }
            }
        } else {
            remote = "not_attempted_target_changed";
        }
        self.store.remove(&server.id())?;
        self.cleanup_retired().await?;
        Ok(
            json!({"server_id":server.id(),"status":"revoked_locally","server_revocation":remote,"warning":warning,
            "pending_credential_cleanup":self.store.retired()?.len()}),
        )
    }
    /// Local cleanup is available even after the source/configuration was removed.
    /// It never contacts an authorization server and does not claim remote revocation.
    pub async fn clear_local_credentials(
        &self,
        server_id: &str,
        confirmed: bool,
        cancel: &CancellationToken,
    ) -> Result<Value> {
        if !confirmed {
            return Err(
                "Explicit confirmation is required to remove local Connector credentials.".into(),
            );
        }
        if server_id.trim().is_empty()
            || server_id.len() > 1024
            || server_id.contains(['\0', '\r', '\n'])
        {
            return Err("A valid Connector server_id is required.".into());
        }
        if cancel.is_cancelled() {
            return Err("Local Connector cleanup was cancelled before it started.".into());
        }
        let cancelled_before = self.cancel_pending_server(server_id)?;
        let _lease = self.mutation_lock_id(server_id, cancel).await?;
        let cancelled_after = self.cancel_pending_server(server_id)?;
        self.discoveries
            .lock()
            .map_err(|_| "Connector discovery registry lock was poisoned.")?
            .retain(|_, discovery| discovery.server_id != server_id);
        let removed = self.store.remove(server_id)?;
        self.cleanup_retired().await?;
        let pending = self.store.retired()?.len();
        Ok(
            json!({"server_id":server_id,"status":if pending==0{"local_credentials_cleared"}else{"local_cleanup_pending"},
            "record_removed":removed.is_some(),"cancelled_authorizations":cancelled_before+cancelled_after,
            "credentials_cleared":pending==0,"pending_credential_cleanup":pending,"server_revocation":"not_attempted_local_only"}),
        )
    }
    fn cancel_pending_server(&self, server_id: &str) -> Result<usize> {
        let mut pending = self
            .pending
            .lock()
            .map_err(|_| "Connector authorization registry lock was poisoned.")?;
        let mut cancelled = 0;
        pending.retain(|_, authorization| {
            if authorization.server_id == server_id {
                authorization.cancel.cancel();
                cancelled += 1;
                false
            } else {
                true
            }
        });
        Ok(cancelled)
    }
    pub fn cancel_all(&self) {
        self.shutdown.cancel();
        if let Ok(mut pending) = self.pending.lock() {
            pending.clear();
        }
    }
    pub async fn close(&self) {
        self.cancel_all();
    }
}
