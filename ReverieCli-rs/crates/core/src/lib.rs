use reverie_protocol::{Reply, Request, VERSION, kernel_info};
use serde_json::{Map, Value, json};
use std::{
    collections::HashMap,
    io,
    path::PathBuf,
    sync::{Arc, Mutex, MutexGuard, TryLockError},
};

pub mod config;
pub mod host;
pub mod models;
pub mod provider;
pub mod session;

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

pub struct Kernel {
    pub project_root: PathBuf,
    pub app_root: PathBuf,
    pub project_data_dir: PathBuf,
    config: config::ConfigStore,
    sessions: Option<session::SessionStore>,
    contexts: HashMap<PathBuf, Arc<Mutex<reverie_context::ContextEngine>>>,
    view_session: Option<String>,
    workspace_mode: bool,
}

pub const ACTIONS: &[&str] = &[
    "hello",
    "initialize",
    "getState",
    "getContextStatus",
    "indexWorkspace",
    "queryContext",
    "workspaceMentions",
    "runPrompt",
    "stopPrompt",
    "resolveApproval",
    "resolveUserInput",
    "listTools",
    "getModelSources",
    "selectModel",
    "addStandardModel",
    "updateStandardModel",
    "deleteStandardModel",
    "listSettings",
    "setSetting",
    "listSessions",
    "createSession",
    "getSession",
    "renameSession",
    "archiveSession",
    "deleteSession",
    "deleteSessions",
    "getConversationConfig",
    "getWorkspaceConfig",
    "queueConversationRun",
    "updateConversationRun",
    "listConversationRuns",
    "recoverConversationRuns",
    "shutdown",
];

impl Kernel {
    pub fn new(project_root: PathBuf) -> io::Result<Self> {
        Self::with_app_root(project_root, config::app_root()?)
    }

    pub fn with_app_root(project_root: PathBuf, app_root: PathBuf) -> io::Result<Self> {
        let project_root = config::canonical_project(&project_root)?;
        let project_data_dir = app_root
            .join(".reverie/projects")
            .join(config::project_name(&project_root));
        let config = config::ConfigStore::new(&app_root);
        Ok(Self {
            project_root,
            app_root,
            project_data_dir,
            config,
            sessions: None,
            contexts: HashMap::new(),
            view_session: None,
            workspace_mode: false,
        })
    }

    pub fn session_store(&mut self) -> Result<&mut session::SessionStore> {
        if self.sessions.is_none() {
            self.sessions = Some(session::SessionStore::open(
                &self.project_data_dir,
                &self.project_root,
            )?);
        }
        Ok(self.sessions.as_mut().unwrap())
    }

    pub fn effective_config(&mut self, id: Option<&str>) -> Result<Value> {
        let defaults = self.config.effective()?;
        let Some(id) = id else {
            return Ok(defaults);
        };
        let page = self.session_store()?.page(id, None, 1)?;
        match page.metadata.get("runtime_config") {
            Some(snapshot) => models::resolve(&defaults, snapshot),
            None => Ok(defaults),
        }
    }

    pub fn context_status(&self) -> Value {
        match self.contexts.get(&self.project_data_dir) {
            Some(context) => match context.try_lock() {
                Ok(context) => context.status().unwrap_or_else(|error|json!({"ready":false,"available":true,"backend":"rust","error":error.to_string()})),
                Err(TryLockError::WouldBlock) => {
                    let mut status = reverie_context::database_status(&self.project_data_dir.join("context/rust-3.0.sqlite3"))
                        .unwrap_or_else(|_| json!({"ready":false,"backend":"rust","files":0,"symbols":0}));
                    status["indexing"] = json!(true);
                    status["available"] = json!(true);
                    status["label"] = json!("Indexing");
                    status
                }
                Err(error) => json!({"ready":false,"available":true,"backend":"rust","error":error.to_string()}),
            },
            None => json!({"ready":false,"indexing":false,"files":0,"symbols":0,"backend":"rust","progress":0.0,"label":"On demand","automatic_retrieval":true,"available":true,"semantic":{"available":false,"status":"resource_not_installed"}}),
        }
    }

    pub fn shared_context(&mut self) -> Result<Arc<Mutex<reverie_context::ContextEngine>>> {
        let root = self.project_root.clone();
        self.shared_context_for(&root)
    }

    fn shared_context_for(
        &mut self,
        root: &std::path::Path,
    ) -> Result<Arc<Mutex<reverie_context::ContextEngine>>> {
        let key = self.context_key_for(root);
        self.shared_context_at(root, &key)
    }

    fn context_key_for(&self, root: &std::path::Path) -> PathBuf {
        if root == self.project_root {
            self.project_data_dir.clone()
        } else {
            self.project_data_dir
                .join("executions")
                .join(config::project_name(root))
        }
    }

    fn shared_context_at(
        &mut self,
        root: &std::path::Path,
        key: &std::path::Path,
    ) -> Result<Arc<Mutex<reverie_context::ContextEngine>>> {
        if !self.contexts.contains_key(key) {
            let context =
                reverie_context::ContextEngine::open(root, &key.join("context/rust-3.0.sqlite3"))?;
            self.contexts
                .insert(key.to_owned(), Arc::new(Mutex::new(context)));
        }
        Ok(self.contexts[key].clone())
    }

    pub fn context_engine(&mut self) -> Result<MutexGuard<'_, reverie_context::ContextEngine>> {
        self.shared_context()?;
        self.contexts[&self.project_data_dir]
            .lock()
            .map_err(|_| "Context Engine lock was poisoned.".into())
    }

    fn workspace(&self, config: &Value) -> Value {
        json!({"project_root":self.project_root,"project_name":self.project_root.file_name().unwrap_or_default().to_string_lossy(),"project_data_dir":self.project_data_dir,"config_path":self.config.path,"mode":config["mode"].as_str().unwrap_or("reverie"),"active_source":config["active_model_source"].as_str().unwrap_or("standard"),"active_model":models::active_summary(config),"index_ready":self.context_status()["ready"],"context_engine":self.context_status()})
    }

    fn state(&mut self) -> Result<Value> {
        let config = self.effective_config(self.view_session.clone().as_deref())?;
        let sessions = self.session_store()?.list()?;
        Ok(
            json!({"protocol_version":1,"core":{"version":VERSION,"interface_version":"1.0","implementation":"rust","release_status":"development"},"workspace":self.workspace(&config),"models":models::sources(&config),"settings":models::settings(&config,&self.config.path,self.workspace_mode),"sessions":sessions,"capabilities":{"actions":ACTIONS},
                "plugins":{"summary":{"available":false,"status":"migration_pending"},"records":[]},
                "skills":{"available":false,"status":"migration_pending","count":0,"invalid_count":0,"shadowed_count":0,"records":[],"pinned":{"max":5,"names":[],"keys":[],"unresolved":[]},"errors":[],"shadowed":[]},
                "commands":{"available":false,"status":"migration_pending","sections":[],"items":[]},
                "recovery":{"available":false,"status":"migration_pending","summary":{"available":false},"operations":[],"checkpoints":[]}}),
        )
    }

    fn configure_project(&mut self, root: &str) -> Result<()> {
        let project = config::canonical_project(std::path::Path::new(root))?;
        if project != self.project_root {
            self.sessions = None;
            self.view_session = None;
            self.project_root = project;
            self.project_data_dir = self
                .app_root
                .join(".reverie/projects")
                .join(config::project_name(&self.project_root));
        }
        let workspace_path = self.project_data_dir.join("config.json");
        self.workspace_mode = if workspace_path.exists() {
            config::ConfigStore::at(workspace_path.clone()).load()?["use_workspace_config"]
                .as_bool()
                .unwrap_or(false)
        } else {
            false
        };
        self.config = if self.workspace_mode {
            config::ConfigStore::at(workspace_path)
        } else {
            config::ConfigStore::new(&self.app_root)
        };
        let database = self.project_data_dir.join("context/rust-3.0.sqlite3");
        if !self.contexts.contains_key(&self.project_data_dir) && database.is_file() {
            self.shared_context()?;
        }
        Ok(())
    }

    fn handle(&mut self, action: &str, payload: &Value) -> Result<(&'static str, Value)> {
        if action == "hello" {
            return Ok((
                "ready",
                json!({"protocol_version":1,"project_root":self.project_root,"kernel":kernel_info(),"capabilities":{"actions":ACTIONS}}),
            ));
        }
        if action == "shutdown" {
            return Ok(("shutdown", json!({})));
        }
        if !ACTIONS.contains(&action) {
            return Err(format!("Unknown action: {action}").into());
        }
        if let Some(root) = payload["projectRoot"].as_str() {
            self.configure_project(root)?;
        }
        match action {
            "initialize" => {
                let root = self.project_root.to_string_lossy().into_owned();
                self.configure_project(&root)?;
                Ok(("state", json!({"state":self.state()?})))
            }
            "getState" => Ok(("state", json!({"state":self.state()?}))),
            "getContextStatus" => Ok((
                "context.status",
                json!({"context_engine":self.context_status()}),
            )),
            "indexWorkspace" => {
                let result = self
                    .context_engine()?
                    .index(payload["force"].as_bool().unwrap_or(false))?;
                let config = self.config.effective()?;
                Ok((
                    "workspace.indexed",
                    json!({"result":result,"workspace":self.workspace(&config)}),
                ))
            }
            "queryContext" => {
                let query = string(payload, "query")?;
                let results = self.context_engine()?.query(
                    query,
                    payload["limit"].as_u64().unwrap_or(10) as usize,
                    payload["estimatedTokens"].as_u64().unwrap_or(12000) as usize,
                )?;
                Ok((
                    "context.results",
                    json!({"results":results,"context_engine":self.context_status()}),
                ))
            }
            "workspaceMentions" => {
                let query = payload["query"].as_str().unwrap_or_default();
                let paths = self
                    .context_engine()?
                    .paths(query, payload["limit"].as_u64().unwrap_or(80) as u32)?;
                let mentions:Vec<Value>=paths.into_iter().map(|path|json!({"name":path.rsplit('/').next().unwrap_or(&path),"path":path,"kind":"file"})).collect();
                Ok((
                    "workspace.mentions",
                    json!({"items":mentions,"mentions":mentions,"context_engine":self.context_status()}),
                ))
            }
            "listSessions" => Ok((
                "sessions",
                json!({"sessions":self.session_store()?.list()?}),
            )),
            "queueConversationRun" => {
                let configuration = models::without_secrets(
                    payload
                        .get("configuration")
                        .ok_or("Task configuration is required.")?,
                );
                models::resolve(&self.config.effective()?, &configuration)?;
                let execution_root = payload["executionRoot"]
                    .as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| self.project_root.to_string_lossy().into_owned());
                let revision = self.session_store()?.register_run(
                    string(payload, "sessionId")?,
                    string(payload, "runId")?,
                    &configuration,
                    payload["configurationRevision"]
                        .as_i64()
                        .ok_or("Configuration revision is required.")?,
                    &execution_root,
                    &models::without_secrets(payload.get("request").unwrap_or(&json!({}))),
                )?;
                Ok(("conversation.run", json!({"revision":revision})))
            }
            "updateConversationRun" => {
                let result = payload.get("result").map(models::without_secrets);
                let revision = self.session_store()?.update_run(
                    string(payload, "sessionId")?,
                    string(payload, "runId")?,
                    string(payload, "state")?,
                    payload["revision"]
                        .as_i64()
                        .ok_or("Task revision is required.")?,
                    payload["executionRoot"].as_str(),
                    result.as_ref(),
                )?;
                Ok(("conversation.run", json!({"revision":revision})))
            }
            "listConversationRuns" => Ok((
                "conversation.runs",
                json!({"runs":self.session_store()?.list_runs(string(payload,"sessionId")?,payload["limit"].as_i64().unwrap_or(60))?}),
            )),
            "recoverConversationRuns" => Ok((
                "conversation.runs",
                json!({"runs":self.session_store()?.recover_runs(&[])?}),
            )),
            "createSession" => {
                let defaults = self.config.effective()?;
                let metadata =
                    Map::from_iter([("runtime_config".into(), models::capture(&defaults))]);
                let page = self
                    .session_store()?
                    .create(payload["name"].as_str(), metadata)?;
                self.view_session = Some(page.id.clone());
                Ok((
                    "session.created",
                    json!({"session":page,"sessions":self.session_store()?.list()?}),
                ))
            }
            "getSession" => {
                let id = string(payload, "sessionId")?.to_owned();
                let page = self.session_store()?.page(
                    &id,
                    payload["before"].as_i64(),
                    payload["limit"].as_i64().unwrap_or(60),
                )?;
                if payload["select"].as_bool().unwrap_or(true) && payload["before"].is_null() {
                    self.session_store()?.select(&id)?;
                    self.view_session = Some(id.clone());
                }
                if payload["markRead"].as_bool().unwrap_or(false) {
                    self.session_store()?.mark_read(&id)?;
                }
                Ok((
                    "session",
                    json!({"session":page,"sessions":self.session_store()?.list()?}),
                ))
            }
            "renameSession" => {
                let id = string(payload, "sessionId")?;
                self.session_store()?.rename(id, string(payload, "name")?)?;
                let page = self.session_store()?.page(id, None, 60)?;
                Ok((
                    "session.updated",
                    json!({"session":page,"sessions":self.session_store()?.list()?}),
                ))
            }
            "archiveSession" => {
                let archived = payload["archived"]
                    .as_bool()
                    .ok_or("archived must be boolean.")?;
                self.session_store()?.update_metadata(
                    string(payload, "sessionId")?,
                    Map::from_iter([("archived".into(), json!(archived))]),
                    payload["revision"]
                        .as_i64()
                        .ok_or("Conversation revision is required.")?,
                )?;
                Ok((
                    "sessions",
                    json!({"sessions":self.session_store()?.list()?}),
                ))
            }
            "deleteSession" | "deleteSessions" => {
                if payload["confirmed"] != true {
                    return Err("Deleting sessions requires confirmed=true.".into());
                }
                let ids = if action == "deleteSession" {
                    vec![string(payload, "sessionId")?.to_owned()]
                } else {
                    payload["sessionIds"]
                        .as_array()
                        .ok_or("sessionIds must be an array.")?
                        .iter()
                        .map(|item| {
                            item.as_str()
                                .map(str::to_owned)
                                .ok_or("Session identifier must be text.")
                        })
                        .collect::<std::result::Result<Vec<_>, _>>()?
                };
                if ids.is_empty() {
                    return Err("At least one session id is required.".into());
                }
                for id in &ids {
                    self.session_store()?.page(id, None, 1)?;
                    if id == "aio-mainline" {
                        return Err("The persistent AiO mainline cannot be deleted.".into());
                    }
                }
                for id in &ids {
                    self.session_store()?.delete(id)?;
                }
                if self
                    .view_session
                    .as_ref()
                    .is_some_and(|id| ids.contains(id))
                {
                    self.view_session = None;
                }
                Ok((
                    if action == "deleteSession" {
                        "session.updated"
                    } else {
                        "sessions.deleted"
                    },
                    json!({"deleted_session_ids":ids,"session":null,"sessions":self.session_store()?.list()?}),
                ))
            }
            "getConversationConfig" => {
                let id = string(payload, "sessionId")?;
                let mut page = self.session_store()?.page(id, None, 1)?;
                let defaults = self.config.effective()?;
                let mut snapshot = page
                    .metadata
                    .get("runtime_config")
                    .cloned()
                    .unwrap_or_else(|| models::capture(&defaults));
                if let Some(replacement) = payload.get("configuration") {
                    models::resolve(&self.config.effective()?, replacement)?;
                    snapshot = models::without_secrets(replacement);
                    page.revision = self.session_store()?.update_metadata(
                        id,
                        Map::from_iter([("runtime_config".into(), snapshot.clone())]),
                        payload["revision"]
                            .as_i64()
                            .ok_or("Conversation revision is required.")?,
                    )?;
                } else if !page.metadata.contains_key("runtime_config") {
                    page.revision = self.session_store()?.update_metadata(
                        id,
                        Map::from_iter([("runtime_config".into(), snapshot.clone())]),
                        page.revision,
                    )?;
                }
                let config = models::resolve(
                    &self.config.effective()?,
                    payload.get("executionConfiguration").unwrap_or(&snapshot),
                )?;
                let fields = json!({"configuration":snapshot,"revision":page.revision,"error":"","ownership":{"assistant_id":page.metadata.get("assistant_id"),"workspace":page.metadata.get("workspace_path"),"session_id":id},"active_model":models::active_summary(&config),"models":models::sources(&config),"workspace":self.workspace(&config),"settings":models::settings(&config,&self.config.path,self.workspace_mode)});
                Ok(("conversation.config", fields))
            }
            "getWorkspaceConfig" => {
                self.view_session = None;
                let config = self.config.effective()?;
                Ok((
                    "workspace.config",
                    json!({"models":models::sources(&config),"workspace":self.workspace(&config),"settings":models::settings(&config,&self.config.path,self.workspace_mode)}),
                ))
            }
            "getModelSources" => {
                let config = self.effective_config(payload["sessionId"].as_str())?;
                Ok(("models", json!({"models":models::sources(&config)})))
            }
            "selectModel" => {
                let source = payload["source"].as_str().unwrap_or("standard");
                if source != "standard" {
                    return Err(
                        format!("Provider source {source} has not yet been migrated.").into(),
                    );
                }
                let mut selected = self.effective_config(payload["sessionId"].as_str())?;
                let model = payload["modelId"]
                    .as_str()
                    .or_else(|| payload["model"].as_str())
                    .ok_or("Model id is required.")?;
                let index = selected["models"]
                    .as_array()
                    .ok_or("Model inventory is missing.")?
                    .iter()
                    .position(|m| m["model"] == model)
                    .ok_or("Model not found.")?;
                selected["active_model_source"] = json!(source);
                selected["active_model_index"] = json!(index);
                if let Some(id) = payload["sessionId"].as_str() {
                    let page = self.session_store()?.page(id, None, 1)?;
                    let mut snapshot = page
                        .metadata
                        .get("runtime_config")
                        .cloned()
                        .unwrap_or_else(|| models::capture(&selected));
                    snapshot["model_ref"] = models::capture(&selected)["model_ref"].clone();
                    self.session_store()?.update_metadata(
                        id,
                        Map::from_iter([("runtime_config".into(), snapshot)]),
                        page.revision,
                    )?;
                } else {
                    self.config.update(|fields| {
                        fields.insert("active_model_source".into(), json!(source));
                        fields.insert("active_model_index".into(), json!(index));
                        Ok(())
                    })?;
                }
                Ok((
                    "model.selected",
                    json!({"models":models::sources(&selected),"selected":models::without_secrets(&selected["models"][index]),"workspace":self.workspace(&selected)}),
                ))
            }
            "addStandardModel" | "updateStandardModel" | "deleteStandardModel" => {
                self.config.effective()?;
                let raw = self.config.load()?;
                let profile = raw["provider_files"]["standard"].as_str().map(|filename| {
                    config::ConfigStore::at(
                        self.config
                            .path
                            .parent()
                            .unwrap()
                            .join("Providers")
                            .join(filename),
                    )
                });
                let store = profile.as_ref().unwrap_or(&self.config);
                let action = action.to_string();
                let mut edited_index = 0;
                store.update(|fields| {
                    let items = fields
                        .entry("models")
                        .or_insert(json!([]))
                        .as_array_mut()
                        .ok_or_else(|| io::Error::other("Models must be an array."))?;
                    if action == "deleteStandardModel" {
                        let index = payload["index"]
                            .as_u64()
                            .ok_or_else(|| io::Error::other("Model index is required."))?
                            as usize;
                        if index >= items.len() {
                            return Err(io::Error::other("Model index is out of range."));
                        }
                        items.remove(index);
                        edited_index = index;
                    } else {
                        let mut model = payload
                            .get("model")
                            .filter(|model| model.is_object())
                            .unwrap_or(payload)
                            .as_object()
                            .cloned()
                            .ok_or_else(|| io::Error::other("Model settings are required."))?;
                        if action == "addStandardModel"
                            && model
                                .get("model")
                                .and_then(Value::as_str)
                                .is_none_or(|m| m.trim().is_empty())
                        {
                            return Err(io::Error::other("Model id is required."));
                        }
                        if action == "addStandardModel" {
                            model
                                .entry("profile_id")
                                .or_insert(json!(uuid::Uuid::new_v4().simple().to_string()));
                            edited_index = items.len();
                            items.push(json!(model));
                        } else {
                            let index = payload["index"]
                                .as_u64()
                                .ok_or_else(|| io::Error::other("Model index is required."))?
                                as usize;
                            let existing = items
                                .get_mut(index)
                                .ok_or_else(|| io::Error::other("Model index is out of range."))?;
                            let profile = existing["profile_id"].clone();
                            edited_index = index;
                            let mut values = existing.as_object().cloned().unwrap_or_default();
                            values.extend(model);
                            if let Some(cleared) = payload["clearFields"].as_array() {
                                for field in cleared.iter().filter_map(Value::as_str) {
                                    values.remove(field);
                                }
                            }
                            if !profile.is_null() {
                                values.insert("profile_id".into(), profile);
                            }
                            *existing = json!(values);
                        }
                    }
                    Ok(())
                })?;
                Ok((
                    "standard-model.updated",
                    json!({"index":edited_index,"models":models::sources(&self.config.effective()?),"workspace":self.workspace(&self.config.effective()?)}),
                ))
            }
            "listSettings" => {
                let config = self.effective_config(payload["sessionId"].as_str())?;
                Ok((
                    "settings",
                    json!({"settings":models::settings(&config,&self.config.path,self.workspace_mode)}),
                ))
            }
            "setSetting" => {
                let key = string(payload, "key")?;
                let value = payload.get("value").ok_or("Setting value is required.")?;
                models::validate_setting(key, value)?;
                let config = if let Some(id) = payload["sessionId"].as_str() {
                    let page = self.session_store()?.page(id, None, 1)?;
                    let defaults = self.config.effective()?;
                    let mut snapshot = page
                        .metadata
                        .get("runtime_config")
                        .cloned()
                        .unwrap_or_else(|| models::capture(&defaults));
                    snapshot["settings"][key] = value.clone();
                    self.session_store()?.update_metadata(
                        id,
                        Map::from_iter([("runtime_config".into(), snapshot)]),
                        page.revision,
                    )?;
                    self.effective_config(Some(id))?
                } else {
                    self.config.update(|fields| {
                        fields.insert(key.into(), value.clone());
                        Ok(())
                    })?;
                    self.config.effective()?
                };
                Ok((
                    "setting.updated",
                    json!({"success":true,"message":"Setting updated.","settings":models::settings(&config,&self.config.path,self.workspace_mode),"workspace":self.workspace(&config)}),
                ))
            }
            _ => Err(format!("Unknown action: {action}").into()),
        }
    }

    pub fn dispatch(&mut self, request: Request) -> Reply {
        match self.handle(request.action.trim(), &request.payload) {
            Ok((kind, fields)) => Reply::new(
                Some(request.id),
                kind,
                fields.as_object().cloned().unwrap_or_default(),
            ),
            Err(error) => Reply::error(request.id, error),
        }
    }
}

fn string<'a>(payload: &'a Value, key: &str) -> Result<&'a str> {
    payload[key]
        .as_str()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{key} is required.").into())
}
