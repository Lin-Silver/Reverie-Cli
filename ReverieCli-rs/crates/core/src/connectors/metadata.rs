use crate::{
    Result,
    mcp::{
        ServerConfig, Transport,
        config::{endpoint, hash},
    },
};
use reqwest::Url;
use serde_json::{Value, json};
use std::collections::BTreeMap;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

#[derive(Clone)]
pub(super) struct Issuer {
    pub url: String,
    pub authorization_endpoint: String,
    pub token_endpoint: String,
    pub registration_endpoint: Option<String>,
    pub revocation_endpoint: Option<String>,
    pub auth_methods: Vec<String>,
    pub response_issuer: bool,
}
#[derive(Clone)]
pub struct OAuthDiscovery {
    pub(super) id: String,
    pub(super) server_id: String,
    pub(super) binding: String,
    pub(super) resource: String,
    pub(super) metadata_url: String,
    pub(super) issuers: Vec<Issuer>,
    pub(super) required_scopes: Vec<String>,
    pub(super) supported_scopes: Vec<String>,
    pub(super) created_at: i64,
}
impl OAuthDiscovery {
    pub fn id(&self) -> &str {
        &self.id
    }
    pub fn public(&self) -> Value {
        json!({"discovery_id":self.id,"server_id":self.server_id,"resource":self.resource,
            "metadata_url":public_url(&self.metadata_url),"created_at":self.created_at,
            "expires_at":self.created_at+600,"required_scopes":self.required_scopes,
            "supported_scopes":self.supported_scopes,"authorization_servers":self.issuers.iter().map(|issuer|json!({
                "issuer":issuer.url,"authorization_endpoint":public_url(&issuer.authorization_endpoint),
                "token_endpoint":public_url(&issuer.token_endpoint),"registration_endpoint":issuer.registration_endpoint.as_deref().map(public_url),
                "revocation_endpoint":issuer.revocation_endpoint.as_deref().map(public_url),
                "token_endpoint_auth_methods_supported":issuer.auth_methods,"pkce":"S256"
            })).collect::<Vec<_>>()})
    }
}
pub(super) fn public_url(text: &str) -> String {
    let mut url = Url::parse(text).expect("validated Connector URL");
    url.set_query(None);
    url.to_string()
}
pub(super) fn binding(server: &ServerConfig) -> String {
    hash(
        format!(
            "{}\0{:?}\0{}",
            server.id(),
            server.transport,
            server.endpoint
        )
        .as_bytes(),
    )
}
fn loopback(url: &Url) -> bool {
    url.host_str().is_some_and(|host| {
        host.eq_ignore_ascii_case("localhost")
            || host
                .trim_matches(['[', ']'])
                .parse::<std::net::IpAddr>()
                .is_ok_and(|address| address.is_loopback())
    })
}
pub(super) fn secure_url(text: &str, allow_loopback: bool) -> Result<Url> {
    let url = endpoint(text)?;
    if url.scheme() != "https" && !(allow_loopback && loopback(&url)) {
        return Err(
            "OAuth requires HTTPS, with HTTP allowed only for a configured loopback service."
                .into(),
        );
    }
    Ok(url)
}
fn canonical(url: &Url) -> String {
    if url.path() == "/" && url.query().is_none() {
        url.as_str().trim_end_matches('/').to_owned()
    } else {
        url.to_string()
    }
}
fn scopes(value: &Value) -> Result<Vec<String>> {
    if value.is_null() {
        return Ok(Vec::new());
    }
    value
        .as_array()
        .ok_or("OAuth metadata scopes must be an array.")?
        .iter()
        .map(|entry| {
            let entry = entry
                .as_str()
                .ok_or("OAuth metadata scopes must be strings.")?;
            validate_scope(entry)?;
            Ok(entry.to_owned())
        })
        .collect()
}
pub(super) fn validate_scope(scope: &str) -> Result<()> {
    if scope.is_empty()
        || !scope
            .bytes()
            .all(|byte| matches!(byte, 0x21 | 0x23..=0x5b | 0x5d..=0x7e))
    {
        return Err("OAuth scopes must use valid nonempty scope tokens.".into());
    }
    Ok(())
}
fn attributes(header: &str) -> Result<BTreeMap<String, String>> {
    let mut segments = Vec::new();
    let mut start = 0;
    let mut quoted = false;
    let mut escaped = false;
    for (position, character) in header.char_indices() {
        if escaped {
            escaped = false;
            continue;
        }
        match character {
            '\\' if quoted => escaped = true,
            '"' => quoted = !quoted,
            ',' if !quoted => {
                segments.push(&header[start..position]);
                start = position + 1;
            }
            _ => {}
        }
    }
    if quoted || escaped {
        return Err("Malformed OAuth authentication challenge.".into());
    }
    segments.push(&header[start..]);
    let mut bearer = false;
    let mut values = BTreeMap::new();
    for segment in segments {
        let segment = segment.trim();
        let segment = if segment.len() > 6
            && segment
                .get(..6)
                .is_some_and(|prefix| prefix.eq_ignore_ascii_case("bearer"))
            && segment.as_bytes()[6].is_ascii_whitespace()
        {
            bearer = true;
            segment[6..].trim()
        } else {
            segment
        };
        let Some((name, value)) = segment.split_once('=') else {
            bearer = false;
            continue;
        };
        if name.trim().contains(char::is_whitespace) {
            bearer = false;
            continue;
        }
        if !bearer {
            continue;
        }
        let name = name.trim().to_ascii_lowercase();
        let value = value.trim();
        let value = if let Some(quoted) = value.strip_prefix('"') {
            let quoted = quoted
                .strip_suffix('"')
                .ok_or("Malformed quoted OAuth challenge value.")?;
            let mut result = String::new();
            let mut escaped = false;
            for ch in quoted.chars() {
                if escaped {
                    result.push(ch);
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else {
                    result.push(ch);
                }
            }
            if escaped {
                return Err("Malformed escaped OAuth challenge value.".into());
            }
            result
        } else {
            value.to_owned()
        };
        if values.insert(name, value).is_some() {
            return Err("Ambiguous repeated OAuth challenge attribute.".into());
        }
    }
    Ok(values)
}
fn well_known(base: &Url, prefix: &str) -> Url {
    let mut url = base.clone();
    url.set_query(None);
    url.set_path(&format!(
        "/.well-known/{prefix}{}",
        base.path().trim_end_matches('/')
    ));
    url
}
async fn document(
    client: &reqwest::Client,
    url: Url,
    cancel: &CancellationToken,
) -> Result<Option<Value>> {
    let operation =
        async {
            let mut response = client.get(url).send().await.map_err(|error| {
                format!("OAuth metadata request failed: {}", error.without_url())
            })?;
            if matches!(response.status().as_u16(), 404 | 405) {
                return Ok(None);
            }
            if !response.status().is_success() {
                return Err(format!("OAuth metadata returned HTTP {}.", response.status()).into());
            }
            let mut bytes = Vec::new();
            while let Some(chunk) = response.chunk().await.map_err(|error| {
                format!("OAuth metadata download failed: {}", error.without_url())
            })? {
                if bytes.len() + chunk.len() > 1024 * 1024 {
                    return Err("OAuth metadata exceeds 1 MiB.".into());
                }
                bytes.extend_from_slice(&chunk);
            }
            let value: Value = serde_json::from_slice(&bytes)?;
            if !value.is_object() {
                return Err("OAuth metadata must be an object.".into());
            }
            Ok(Some(value))
        };
    tokio::select! {_=cancel.cancelled()=>Err("OAuth metadata discovery cancelled.".into()),result=operation=>result}
}
fn issuer_metadata(url: &Url, value: &Value, allow_loopback: bool) -> Result<Issuer> {
    let issuer = secure_url(
        value["issuer"]
            .as_str()
            .ok_or("OAuth metadata lacks issuer.")?,
        allow_loopback,
    )?;
    if canonical(&issuer) != canonical(url) || issuer.query().is_some() {
        return Err(
            "OAuth metadata issuer does not match the selected authorization server.".into(),
        );
    }
    if !value["code_challenge_methods_supported"]
        .as_array()
        .is_some_and(|methods| methods.iter().any(|method| method == "S256"))
    {
        return Err(
            "The authorization server does not advertise PKCE S256; authorization cannot continue."
                .into(),
        );
    }
    if !value["response_types_supported"]
        .as_array()
        .is_some_and(|types| types.iter().any(|kind| kind == "code"))
    {
        return Err(
            "The authorization server does not support authorization-code responses.".into(),
        );
    }
    let required = |name: &str| -> Result<String> {
        Ok(secure_url(
            value[name]
                .as_str()
                .ok_or("OAuth metadata lacks a required endpoint.")?,
            allow_loopback,
        )?
        .to_string())
    };
    let optional = |name: &str| -> Result<Option<String>> {
        value
            .get(name)
            .filter(|value| !value.is_null())
            .map(|value| {
                Ok(secure_url(
                    value
                        .as_str()
                        .ok_or("OAuth endpoint must be a URL string.")?,
                    allow_loopback,
                )?
                .to_string())
            })
            .transpose()
    };
    let auth_methods = value
        .get("token_endpoint_auth_methods_supported")
        .map(|value| {
            value
                .as_array()
                .ok_or("OAuth token authentication methods must be an array.")?
                .iter()
                .map(|method| {
                    method
                        .as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| "OAuth token authentication method must be a string.".into())
                })
                .collect::<Result<Vec<_>>>()
        })
        .transpose()?
        .unwrap_or_else(|| vec!["client_secret_basic".into()]);
    Ok(Issuer {
        url: canonical(&issuer),
        authorization_endpoint: required("authorization_endpoint")?,
        token_endpoint: required("token_endpoint")?,
        registration_endpoint: optional("registration_endpoint")?,
        revocation_endpoint: optional("revocation_endpoint")?,
        auth_methods,
        response_issuer: value["authorization_response_iss_parameter_supported"]
            .as_bool()
            .unwrap_or(false),
    })
}
pub(super) async fn discover(
    client: &reqwest::Client,
    server: &ServerConfig,
    previous_challenge: Option<&str>,
    cancel: &CancellationToken,
) -> Result<OAuthDiscovery> {
    if server.transport == Transport::Stdio {
        return Err(
            "Stdio MCP uses environment credentials and has no HTTP OAuth discovery.".into(),
        );
    }
    let mut resource_url = secure_url(&server.endpoint, true)?;
    let allow_loopback = loopback(&resource_url);
    resource_url.set_query(None);
    let response = tokio::select! {_=cancel.cancelled()=>return Err("OAuth metadata discovery cancelled.".into()),result=client.get(resource_url.clone()).send()=>result.map_err(|error|format!("MCP authorization discovery failed: {}",error.without_url()))?};
    let challenge = response
        .headers()
        .get_all("www-authenticate")
        .iter()
        .filter_map(|header| header.to_str().ok())
        .collect::<Vec<_>>()
        .join(", ");
    drop(response);
    let challenge = attributes(previous_challenge.unwrap_or(&challenge))?;
    let mut locations = if let Some(hint) = challenge.get("resource_metadata") {
        vec![secure_url(hint, allow_loopback)?]
    } else {
        let path = well_known(&resource_url, "oauth-protected-resource");
        let mut root = resource_url.clone();
        root.set_path("/.well-known/oauth-protected-resource");
        if path == root {
            vec![path]
        } else {
            vec![path, root]
        }
    };
    let mut found = None;
    for location in locations.drain(..) {
        if let Some(value) = document(client, location.clone(), cancel).await? {
            found = Some((location, value));
            break;
        }
    }
    let (metadata_url, resource_metadata) =
        found.ok_or("The MCP server has no usable protected-resource metadata.")?;
    let resource = secure_url(
        resource_metadata["resource"]
            .as_str()
            .ok_or("Protected-resource metadata lacks its resource identity.")?,
        allow_loopback,
    )?;
    let covered = resource.path() == "/"
        || resource_url.path() == resource.path()
        || resource_url
            .path()
            .starts_with(&format!("{}/", resource.path().trim_end_matches('/')));
    if resource.origin() != resource_url.origin() || resource.query().is_some() || !covered {
        return Err("Protected-resource metadata does not identify this MCP endpoint.".into());
    }
    let urls = resource_metadata["authorization_servers"]
        .as_array()
        .filter(|urls| !urls.is_empty() && urls.len() <= 16)
        .ok_or("Protected-resource metadata must list 1–16 authorization servers.")?;
    let mut issuers = Vec::new();
    for value in urls {
        let url = secure_url(
            value.as_str().ok_or("OAuth issuer must be a URL string.")?,
            allow_loopback,
        )?;
        if url.query().is_some() {
            return Err("OAuth issuer URLs cannot contain a query.".into());
        }
        if issuers
            .iter()
            .any(|issuer: &Issuer| issuer.url == canonical(&url))
        {
            continue;
        }
        let mut candidates = vec![
            well_known(&url, "oauth-authorization-server"),
            well_known(&url, "openid-configuration"),
        ];
        if url.path() != "/" {
            let mut appended = url.clone();
            appended.set_path(&format!(
                "{}/.well-known/openid-configuration",
                url.path().trim_end_matches('/')
            ));
            candidates.push(appended);
        }
        let mut metadata = None;
        for location in candidates {
            if let Some(value) = document(client, location, cancel).await? {
                metadata = Some(value);
                break;
            }
        }
        issuers.push(issuer_metadata(
            &url,
            &metadata.ok_or("No usable OAuth or OpenID Connect issuer metadata was found.")?,
            allow_loopback,
        )?);
    }
    let required_scopes = challenge
        .get("scope")
        .map(|scope| {
            scope
                .split_ascii_whitespace()
                .map(|scope| {
                    validate_scope(scope)?;
                    Ok(scope.to_owned())
                })
                .collect::<Result<Vec<_>>>()
        })
        .transpose()?
        .unwrap_or_default();
    Ok(OAuthDiscovery {
        id: Uuid::new_v4().to_string(),
        server_id: server.id(),
        binding: binding(server),
        resource: canonical(&resource),
        metadata_url: metadata_url.to_string(),
        issuers,
        required_scopes,
        supported_scopes: scopes(&resource_metadata["scopes_supported"])?,
        created_at: chrono::Utc::now().timestamp(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parses_challenges_and_checks_issuer_pkce_and_transport_boundaries() {
        let values=attributes("Basic realm=\"ignored\", Bearer realm=\"a,b\", resource_metadata=\"https://service.test/meta\", scope=\"read write\"").unwrap();
        assert_eq!(values["resource_metadata"], "https://service.test/meta");
        assert_eq!(values["scope"], "read write");
        assert!(attributes("Bearer scope=\"read\",scope=\"write\"").is_err());
        assert!(secure_url("http://service.test/mcp", true).is_err());
        assert!(secure_url("http://127.0.0.1:8123/mcp", true).is_ok());
        assert!(secure_url("http://127.0.0.1:8123/mcp", false).is_err());
        let url = Url::parse("https://identity.test/tenant").unwrap();
        assert_eq!(
            well_known(&url, "oauth-authorization-server").as_str(),
            "https://identity.test/.well-known/oauth-authorization-server/tenant"
        );
        let mut metadata = json!({"issuer":url.as_str(),"authorization_endpoint":"https://identity.test/authorize","token_endpoint":"https://identity.test/token","code_challenge_methods_supported":["S256"],"response_types_supported":["code"]});
        assert!(issuer_metadata(&url, &metadata, false).is_ok());
        metadata["issuer"] = json!("https://different.test");
        assert!(issuer_metadata(&url, &metadata, false).is_err());
        metadata["issuer"] = json!(url.as_str());
        metadata["code_challenge_methods_supported"] = Value::Null;
        assert!(issuer_metadata(&url, &metadata, false).is_err());
    }
}
