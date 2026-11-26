use super::config::{ServerConfig, endpoint, expand_env};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    sync::{Arc, Mutex},
};

#[derive(Clone, Default)]
pub(crate) struct Redactor(Arc<Mutex<Vec<String>>>);

impl Redactor {
    pub(crate) fn for_server(config: &ServerConfig) -> Self {
        let redactor = Self::default();
        for value in config.env.values() {
            redactor.add(&expand_env(value, &config.env));
        }
        let headers = config
            .headers
            .iter()
            .map(|(name, value)| (name.clone(), expand_env(value, &config.env)))
            .collect();
        redactor.headers(&headers);
        if let Ok(url) = endpoint(&config.endpoint) {
            for (_, value) in url.query_pairs() {
                redactor.add(&value);
            }
        }
        redactor
    }
    pub(crate) fn add(&self, value: &str) {
        if value.is_empty() {
            return;
        }
        let mut values = self.0.lock().unwrap_or_else(|error| error.into_inner());
        if !values.iter().any(|existing| existing == value) {
            values.push(value.into());
            values.sort_by_key(|value| std::cmp::Reverse(value.len()));
        }
    }
    pub(crate) fn headers(&self, headers: &BTreeMap<String, String>) {
        for (name, value) in headers {
            self.add(value);
            if name.eq_ignore_ascii_case("authorization")
                && let Some((_, credential)) = value.split_once(' ')
            {
                self.add(credential.trim());
            }
        }
    }
    pub(crate) fn text(&self, text: &str) -> String {
        let values = self.0.lock().unwrap_or_else(|error| error.into_inner());
        values.iter().fold(text.to_owned(), |text, value| {
            text.replace(value, "[redacted]")
        })
    }
    pub(crate) fn value(&self, value: &Value) -> Value {
        match value {
            Value::Object(entries) => Value::Object(
                entries
                    .iter()
                    .filter(|(name, _)| name.as_str() != "_meta")
                    .map(|(name, value)| (self.text(name), self.value(value)))
                    .collect(),
            ),
            Value::Array(entries) => {
                Value::Array(entries.iter().map(|value| self.value(value)).collect())
            }
            Value::String(text) => Value::String(self.text(text)),
            _ => value.clone(),
        }
    }
    pub(crate) fn error(
        &self,
        error: Box<dyn std::error::Error + Send + Sync>,
    ) -> Box<dyn std::error::Error + Send + Sync> {
        if let Some(failure) = error.downcast_ref::<super::transport::Failure>() {
            Box::new(super::transport::Failure {
                message: self.text(&failure.message),
                delivery: failure.delivery,
                authorization: failure.authorization.clone(),
            })
        } else {
            self.text(&error.to_string()).into()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn known_credentials_and_private_metadata_do_not_enter_public_results() {
        let server = ServerConfig::parse(
            "fixture",
            "manual",
            &json!({
                "type":"http", "url":"https://example.test/mcp?key=query-secret",
                "env":{"MCP_API_KEY":"environment-secret"},
                "headers":{"Authorization":"Bearer ${MCP_API_KEY}"}
            }),
        )
        .unwrap();
        let redactor = Redactor::for_server(&server);
        redactor.headers(&BTreeMap::from([(
            "authorization".into(),
            "Bearer refreshed-secret".into(),
        )]));
        let result = redactor.value(
            &json!({"content":[{"text":"environment-secret refreshed-secret query-secret"}],
            "_meta":{"private":"fixture"}, "structuredContent":{"_meta":{}, "allowed":true}}),
        );
        let text = result.to_string();
        assert!(!text.contains("-secret"));
        assert!(!text.contains("_meta"));
        assert_eq!(result["structuredContent"]["allowed"], true);
    }
}
