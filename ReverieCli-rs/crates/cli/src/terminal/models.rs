use super::*;

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

    pub(super) async fn modelscope_command(&mut self, args: &[String]) -> Result<()> {
        match args {
            [] => return self.show_model_catalog(Some("modelscope")).await,
            [arg] if arg == "model" => return self.show_model_catalog(Some("modelscope")).await,
            [arg] if arg == "refresh" => {
                let reply = self.request("refreshModelSources",json!({"sessionId":self.session})).await?;
                if let Some(error) = reply["catalog_error"].as_str() {
                    self.screen.print(error)?;
                }
                return self.show_model_catalog(Some("modelscope")).await;
            }
            [arg, value] if matches!(arg.as_str(),"key-env"|"url"|"endpoint") => {
                let key = if arg == "key-env" { "api_key_env" } else { "api_url" };
                self.request("setProviderConfig",json!({"source":"modelscope","patch":{key:value}})).await?;
            }
            [arg, model, rest @ ..] if arg == "model" && rest.len() <= 1 => {
                self.request("selectModel",json!({"sessionId":self.session,"source":"modelscope","modelId":model,"reasoning":rest.first()})).await?;
            }
            _ => return Err("Use /modelscope [model <id> [reasoning] | key-env <variable> | url <base> | refresh].".into()),
        }
        self.refresh().await
    }
}
