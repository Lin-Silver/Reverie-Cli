use super::*;
use crate::{config::ConfigStore, modelscope};

pub struct PendingModelRefresh {
    store: ConfigStore,
    config: Value,
}

impl KernelHost {
    pub fn begin_model_refresh(&self, payload: &Value) -> Result<PendingModelRefresh> {
        let mut kernel = lock(&self.kernel)?;
        kernel.configure_assistant(payload)?;
        if let Some(root) = payload["projectRoot"].as_str() {
            kernel.configure_project(root)?;
        }
        Ok(PendingModelRefresh {
            store: ConfigStore::at(kernel.config.path.clone()),
            config: kernel.session_config(
                payload["sessionId"].as_str(),
                crate::models::SelectionUse::Catalog,
            )?,
        })
    }
}

impl PendingModelRefresh {
    async fn fetch(mut self) -> Result<Value> {
        let cfg = &self.config["modelscope"];
        let mut error = None;
        match modelscope::fetch(cfg, self.config["api_proxy"].as_str().unwrap_or("")).await {
            Ok(Some(cache)) => {
                let current = self.store.update_modelscope(false, |section| {
                    if cache["connection_key"] != modelscope::connection_key(section) {
                        return Err(std::io::Error::other(
                            "ModelScope connection changed during refresh.",
                        ));
                    }
                    if section["model_catalog"] == cfg["model_catalog"] {
                        section["model_catalog"] = cache;
                    }
                    Ok(())
                })?;
                self.config["modelscope"]["model_catalog"] = current["model_catalog"].clone();
            }
            Ok(None) => {}
            Err(e) => error = Some(e.to_string()),
        }
        let mut reply = json!({"models":models::sources(&self.config)});
        if let Some(message) = error {
            reply["catalog_error"] = json!(message);
        }
        Ok(reply)
    }

    pub async fn complete(self, id: Value) -> Reply {
        match self.fetch().await {
            Ok(fields) => Reply::new(
                Some(id),
                "models",
                fields.as_object().cloned().unwrap_or_default(),
            ),
            Err(e) => Reply::error(id, e),
        }
    }
}
