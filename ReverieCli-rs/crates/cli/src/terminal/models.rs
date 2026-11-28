use super::*;

fn modelscope_source(reply: &Value) -> Result<&Value> {
    reply["models"]["sources"]
        .as_array()
        .and_then(|sources| sources.iter().find(|s| s["id"] == "modelscope"))
        .ok_or_else(|| "ModelScope is unavailable.".into())
}

fn endpoint_patch(input: &str) -> Value {
    let value = match input.trim().to_ascii_lowercase().as_str() {
        "clear" | "default" | "none" | "off" => "",
        _ => input.trim(),
    };
    json!({"api_url":value})
}

fn key_patch(input: &str) -> Result<Value> {
    let input = input.trim();
    if input.is_empty() {
        return Err("Enter a ModelScope API key or env:VARIABLE_NAME.".into());
    }
    if let Some((prefix, variable)) = input.split_once(':')
        && prefix.eq_ignore_ascii_case("env")
    {
        if variable.trim().is_empty() {
            return Err("An environment variable name is required.".into());
        }
        return Ok(json!({"api_key_env":variable.trim()}));
    }
    Ok(json!({"api_key":input}))
}

impl Tui {
    pub(super) async fn show_model_catalog(&mut self, only: Option<&str>) -> Result<()> {
        let catalog = self
            .request("getModelSources", json!({"sessionId":self.session}))
            .await?;
        let mut rows = Vec::new();
        let mut labels = Vec::new();
        for source in catalog["models"]["sources"]
            .as_array()
            .ok_or("Missing model sources.")?
        {
            let id = source["id"].as_str().ok_or("Invalid model source.")?;
            if only.is_some_and(|wanted| wanted != id) {
                continue;
            }
            for model in source["models"].as_array().into_iter().flatten() {
                let detail = if id == "standard" {
                    model["transport"].as_str().unwrap_or("openai-chat")
                } else {
                    source["display_name"].as_str().unwrap_or(id)
                };
                labels.push(format!(
                    "{} ({detail})",
                    model["display_name"].as_str().unwrap_or_default()
                ));
                rows.push(json!({"source":id,"id":model["id"],"profile_id":model["profile_id"]}));
            }
        }
        if rows.is_empty() {
            return Err("No models available in this catalog.".into());
        }
        self.panel(
            PanelKind::Models,
            "Choose model".into(),
            labels,
            json!(rows),
            false,
        );
        Ok(())
    }

    fn modelscope_key_panel(&mut self, activate: bool) {
        self.panel(
            PanelKind::ModelScopeKey { activate },
            "ModelScope API key or env:VARIABLE_NAME".into(),
            vec!["Cancel".into(), "Save credential".into()],
            Value::Null,
            false,
        );
    }

    async fn save_modelscope(&self, patch: Value) -> Result<Value> {
        self.request(
            "setProviderConfig",
            json!({"source":"modelscope","sessionId":self.session,"patch":patch}),
        )
        .await
    }

    pub(super) async fn submit_modelscope_input(&mut self, cancelled: bool) -> Result<()> {
        let panel = self.panel.take().ok_or("No ModelScope form is open.")?;
        let input = std::mem::replace(&mut self.input, panel.draft);
        if cancelled || panel.selected == 0 {
            return Ok(());
        }
        match panel.kind {
            PanelKind::ModelScopeKey { activate } => {
                let updated = self.save_modelscope(key_patch(&input.text)?).await?;
                if activate {
                    self.activate_modelscope(modelscope_source(&updated)?)
                        .await?;
                } else {
                    self.screen.print("ModelScope credential saved.")?;
                }
            }
            PanelKind::ModelScopeUrl => {
                self.save_modelscope(endpoint_patch(&input.text)).await?;
            }
            _ => return Err("Unexpected ModelScope form.".into()),
        }
        self.refresh().await
    }

    async fn activate_modelscope(&mut self, source: &Value) -> Result<()> {
        if source["enabled"] == false {
            return Err("ModelScope is disabled.".into());
        }
        if source["api_key_source"] == "none" {
            return Err(
                "ModelScope API key is unavailable. Check the configured environment variable."
                    .into(),
            );
        }
        let model = source["selected_model_id"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or("ModelScope has no available models.")?;
        let selection = json!({"source":"modelscope","modelId":model,
            "reasoning":source["selected_reasoning"]["value"]});
        let mut conversation = selection.clone();
        conversation["sessionId"] = json!(self.session);
        self.request("selectModel", conversation).await?;
        self.request("selectModel",selection).await.map_err(|e|
            format!("ModelScope is active in this conversation. Updating the workspace default failed: {e}"))?;
        self.screen
            .print("ModelScope activated for this conversation and new conversations.")?;
        Ok(())
    }

    async fn modelscope_status(&mut self) -> Result<()> {
        let reply = self
            .request("getModelSources", json!({"sessionId":self.session}))
            .await?;
        let source = modelscope_source(&reply)?;
        let values = &source["config"]["values"];
        let origin = match source["api_key_source"].as_str() {
            Some("config") => "saved key",
            Some("env") => "environment",
            _ => "not set",
        };
        let model = source["selected_model_id"].as_str().unwrap_or("");
        let row = source["models"]
            .as_array()
            .and_then(|rows| rows.iter().find(|r| r["id"] == model));
        let context = row
            .and_then(|r| r["context_length"].as_u64())
            .map(|n| n.to_string())
            .unwrap_or_else(|| "unknown".into());
        self.screen.print(&format!(
            "ModelScope\nActive source: {}\nEnabled: {}\nModel: {model}\nTransport: OpenAI Chat Completions\nContext: {context}\nVision: {}\nReasoning: {}\nAPI key: {origin}\nOpenAI base URL: {}\nMax output tokens: {}",
            reply["models"]["active_source"].as_str().unwrap_or("standard"),source["enabled"]==true,
            row.is_some_and(|r|r["vision"]==true),source["selected_reasoning"]["value"].as_str().unwrap_or(""),
            values["api_url"].as_str().unwrap_or(""),values["max_tokens"]
        ))?;
        Ok(())
    }

    pub(super) async fn modelscope_command(&mut self, args: &[String]) -> Result<()> {
        let action = args
            .first()
            .map(|s| s.to_ascii_lowercase())
            .unwrap_or_default();
        let rest = args.get(1..).unwrap_or_default();
        match (action.as_str(), rest) {
            ("", []) => {
                self.modelscope_status().await?;
                return self.show_model_catalog(Some("modelscope")).await;
            }
            ("status" | "check", []) => return self.modelscope_status().await,
            ("key" | "apikey" | "api-key" | "login", []) => {
                self.modelscope_key_panel(false);
                return Ok(());
            }
            ("activate" | "use", []) => {
                let reply = self.request("getModelSources", json!({"sessionId":self.session})).await?;
                let source = modelscope_source(&reply)?;
                if source["enabled"] != false && source["api_key_source"] == "none" {
                    self.modelscope_key_panel(true);
                    return Ok(());
                }
                self.activate_modelscope(source).await?;
            }
            ("model", []) => return self.show_model_catalog(Some("modelscope")).await,
            ("refresh", []) => {
                let reply = self.request("refreshModelSources", json!({"sessionId":self.session})).await?;
                if let Some(error) = reply["catalog_error"].as_str() {
                    self.screen.print(error)?;
                }
                return self.show_model_catalog(Some("modelscope")).await;
            }
            ("key-env", [name]) => {
                self.save_modelscope(json!({"api_key_env":name})).await?;
            }
            ("url" | "endpoint" | "base-url" | "baseurl", []) => {
                let reply = self.request("getModelSources", json!({"sessionId":self.session})).await?;
                let url = modelscope_source(&reply)?["config"]["values"]["api_url"].as_str().unwrap_or("");
                self.panel(
                    PanelKind::ModelScopeUrl,
                    "ModelScope OpenAI base URL (clear restores the default)".into(),
                    vec!["Cancel".into(), "Save endpoint".into()], Value::Null, false,
                );
                self.input.insert(url);
                self.panel.as_mut().unwrap().selected = 1;
                return Ok(());
            }
            ("url" | "endpoint" | "base-url" | "baseurl", [url]) => {
                self.save_modelscope(endpoint_patch(url)).await?;
            }
            ("model", [model, reasoning @ ..]) if reasoning.len() <= 1 => {
                self.request("selectModel",json!({"sessionId":self.session,"source":"modelscope","modelId":model,"reasoning":reasoning.first()})).await?;
            }
            _ => return Err("Use /modelscope [status | key | activate | model [id [reasoning]] | key-env <variable> | endpoint [URL] | refresh].".into()),
        }
        self.refresh().await
    }
}
