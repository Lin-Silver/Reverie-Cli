use super::metadata::{Issuer, validate_scope};
use crate::{
    Result,
    mcp::{Delivery, Failure},
};
use base64::{
    Engine,
    engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD},
};
use reqwest::{RequestBuilder, Url};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

#[derive(Default, Deserialize)]
pub struct AuthorizationChoice {
    pub issuer: String,
    #[serde(default)]
    pub scopes: Vec<String>,
    pub client_id: Option<String>,
    pub client_secret: Option<String>,
    pub client_auth_method: Option<String>,
    pub redirect_uri: Option<String>,
    pub registration_token: Option<String>,
    #[serde(default)]
    pub confirmed: bool,
}
#[derive(Clone, Serialize, Deserialize)]
pub(super) struct ClientRegistration {
    pub client_id: String,
    pub client_secret: Option<String>,
    pub auth_method: String,
}
#[derive(Clone, Serialize, Deserialize)]
pub(super) struct Token {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub expires_at: Option<i64>,
    pub scopes: Vec<String>,
}
impl Token {
    fn parse(value: &Value, approved: &[String]) -> Result<Self> {
        let access_token = value["access_token"]
            .as_str()
            .filter(|value| !value.is_empty() && value.len() <= 65536)
            .ok_or("OAuth token response has no usable access token.")?;
        if !value["token_type"]
            .as_str()
            .is_some_and(|kind| kind.eq_ignore_ascii_case("bearer"))
        {
            return Err("OAuth token response must use the Bearer token type.".into());
        }
        reqwest::header::HeaderValue::from_str(&format!("Bearer {access_token}"))?;
        let scopes = value.get("scope").map(|value| {
            value.as_str().ok_or("OAuth token scope must be a string.")?.split_ascii_whitespace().map(|scope| {
                validate_scope(scope)?;
                if !approved.iter().any(|approved|approved==scope) {return Err("OAuth token response expands the approved scopes; authorization was not activated.".into());}
                Ok(scope.to_owned())
            }).collect::<Result<Vec<_>>>()
        }).transpose()?.unwrap_or_else(||approved.to_vec());
        let refresh_token = value
            .get("refresh_token")
            .filter(|value| !value.is_null())
            .map(|value| -> Result<String> {
                value
                    .as_str()
                    .filter(|value| !value.is_empty() && value.len() <= 65536)
                    .map(str::to_owned)
                    .ok_or_else(|| "OAuth refresh token is invalid.".into())
            })
            .transpose()?;
        let expires_at = value
            .get("expires_in")
            .map(|value| -> Result<i64> {
                let seconds = value
                    .as_u64()
                    .ok_or("OAuth expiry must be a nonnegative number of seconds.")?;
                chrono::Utc::now()
                    .timestamp()
                    .checked_add(i64::try_from(seconds)?)
                    .ok_or("OAuth token expiry overflow.".into())
            })
            .transpose()?;
        Ok(Self {
            access_token: access_token.to_owned(),
            refresh_token,
            expires_at,
            scopes,
        })
    }
}
pub(super) fn verifier() -> String {
    (0..3)
        .map(|_| Uuid::new_v4().simple().to_string())
        .collect()
}
pub(super) fn challenge(verifier: &str) -> String {
    URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()))
}
fn failure(
    message: impl Into<String>,
    delivery: Delivery,
) -> Box<dyn std::error::Error + Send + Sync> {
    Box::new(Failure {
        message: message.into(),
        delivery,
        authorization: None,
    })
}
async fn send(request: RequestBuilder, cancel: &CancellationToken) -> Result<reqwest::Response> {
    if cancel.is_cancelled() {
        return Err(failure(
            "OAuth request cancelled before transmission.",
            Delivery::NotStarted,
        ));
    }
    tokio::select! {
        _=cancel.cancelled()=>Err(failure("OAuth request interrupted; delivery is uncertain and was not retried.",Delivery::Unknown)),
        result=request.send()=>result.map_err(|error|failure(format!("OAuth request failed; it was not retried: {}",error.without_url()),Delivery::Unknown)),
    }
}
async fn json_response(request: RequestBuilder, cancel: &CancellationToken) -> Result<Value> {
    let mut response = send(request, cancel).await?;
    if !response.status().is_success() {
        return Err(failure(
            format!("OAuth endpoint returned HTTP {}.", response.status()),
            Delivery::Completed,
        ));
    }
    let operation = async {
        let mut bytes = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|error| {
            failure(
                format!("OAuth response interrupted: {}", error.without_url()),
                Delivery::Unknown,
            )
        })? {
            if bytes.len() + chunk.len() > 1024 * 1024 {
                return Err(failure(
                    "OAuth response exceeds 1 MiB.",
                    Delivery::Completed,
                ));
            }
            bytes.extend_from_slice(&chunk);
        }
        let parsed = serde_json::from_slice(&bytes);
        bytes.fill(0);
        let value: Value = parsed
            .map_err(|_| failure("OAuth endpoint returned invalid JSON.", Delivery::Completed))?;
        if !value.is_object() {
            return Err(failure(
                "OAuth endpoint returned a non-object response.",
                Delivery::Completed,
            ));
        }
        Ok(value)
    };
    tokio::select! {_=cancel.cancelled()=>Err(failure("OAuth response interrupted; the request was not retried.",Delivery::Unknown)),result=operation=>result}
}
fn scalar(value: &Value, field: &str) -> Result<String> {
    value[field]
        .as_str()
        .filter(|value| {
            !value.is_empty() && value.len() <= 65536 && !value.contains(['\0', '\r', '\n'])
        })
        .map(str::to_owned)
        .ok_or("OAuth client registration lacks a valid required value.".into())
}
pub(super) async fn registration(
    client: &reqwest::Client,
    issuer: &Issuer,
    choice: &AuthorizationChoice,
    redirect: &str,
    cancel: &CancellationToken,
) -> Result<ClientRegistration> {
    let supported = |method: &str| issuer.auth_methods.iter().any(|value| value == method);
    let method = choice.client_auth_method.clone().unwrap_or_else(|| {
        let dynamic = choice.client_id.as_ref().is_none_or(String::is_empty);
        if choice.client_secret.is_none() && supported("none") {
            "none"
        } else if (choice.client_secret.is_some() || dynamic) && supported("client_secret_basic") {
            "client_secret_basic"
        } else if (choice.client_secret.is_some() || dynamic) && supported("client_secret_post") {
            "client_secret_post"
        } else {
            "none"
        }
        .into()
    });
    if !["none", "client_secret_basic", "client_secret_post"].contains(&method.as_str())
        || !supported(&method)
    {
        return Err("The chosen OAuth client authentication method is not supported.".into());
    }
    if let Some(id) = choice.client_id.as_ref().filter(|id| !id.is_empty()) {
        if id.len() > 65536
            || id.contains(['\0', '\r', '\n'])
            || (method != "none" && choice.client_secret.as_ref().is_none_or(String::is_empty))
        {
            return Err("OAuth preregistration requires a valid client identity and applicable client secret.".into());
        }
        return Ok(ClientRegistration {
            client_id: id.clone(),
            client_secret: choice.client_secret.clone(),
            auth_method: method,
        });
    }
    let endpoint = issuer
        .registration_endpoint
        .as_ref()
        .ok_or("This authorization server requires a preregistered client ID.")?;
    let mut request=client.post(endpoint).json(&json!({"client_name":"Reverie CLI","redirect_uris":[redirect],
        "grant_types":["authorization_code","refresh_token"],"response_types":["code"],"token_endpoint_auth_method":method}));
    if let Some(token) = choice.registration_token.as_ref() {
        request = request.bearer_auth(token);
    }
    let value = json_response(request, cancel).await?;
    let registered = value["token_endpoint_auth_method"]
        .as_str()
        .unwrap_or("client_secret_basic");
    if registered != method {
        return Err(
            "OAuth registration did not preserve the requested client authentication method."
                .into(),
        );
    }
    if value.get("redirect_uris").is_some_and(|uris| {
        !uris
            .as_array()
            .is_some_and(|uris| uris.iter().any(|uri| uri == redirect))
    }) {
        return Err("OAuth registration did not approve this exact callback URI.".into());
    }
    Ok(ClientRegistration {
        client_id: scalar(&value, "client_id")?,
        client_secret: if method == "none" {
            None
        } else {
            Some(scalar(&value, "client_secret")?)
        },
        auth_method: method,
    })
}
fn encoded(value: &str) -> String {
    let mut url = Url::parse("http://127.0.0.1/").expect("constant encoding URL");
    url.query_pairs_mut().append_pair("value", value);
    url.query()
        .expect("encoded query")
        .strip_prefix("value=")
        .expect("encoding field")
        .to_owned()
}
fn authenticated(
    mut request: RequestBuilder,
    client: &ClientRegistration,
    form: &mut Vec<(String, String)>,
) -> Result<RequestBuilder> {
    match client.auth_method.as_str() {
        "none" => form.push(("client_id".into(), client.client_id.clone())),
        "client_secret_post" => {
            form.push(("client_id".into(), client.client_id.clone()));
            form.push((
                "client_secret".into(),
                client
                    .client_secret
                    .clone()
                    .ok_or("OAuth client secret is missing.")?,
            ));
        }
        "client_secret_basic" => {
            let secret = client
                .client_secret
                .as_ref()
                .ok_or("OAuth client secret is missing.")?;
            request = request.header(
                "authorization",
                format!(
                    "Basic {}",
                    STANDARD.encode(format!(
                        "{}:{}",
                        encoded(&client.client_id),
                        encoded(secret)
                    ))
                ),
            );
        }
        _ => return Err("Unsupported stored OAuth authentication method.".into()),
    }
    Ok(request)
}
fn form_request(request: RequestBuilder, values: &[(String, String)]) -> RequestBuilder {
    let body = values
        .iter()
        .map(|(name, value)| format!("{}={}", encoded(name), encoded(value)))
        .collect::<Vec<_>>()
        .join("&");
    request
        .header("content-type", "application/x-www-form-urlencoded")
        .body(body)
}
pub(super) fn authorization_url(
    issuer: &Issuer,
    client: &ClientRegistration,
    resource: &str,
    redirect: &str,
    scopes: &[String],
    state: &str,
    verifier: &str,
) -> Result<String> {
    let mut url = Url::parse(&issuer.authorization_endpoint)?;
    if url.query_pairs().any(|(name, _)| {
        [
            "response_type",
            "client_id",
            "redirect_uri",
            "scope",
            "state",
            "code_challenge",
            "code_challenge_method",
            "resource",
        ]
        .contains(&name.as_ref())
    }) {
        return Err(
            "OAuth authorization endpoint already contains conflicting reserved parameters.".into(),
        );
    }
    let mut query = url.query_pairs_mut();
    query
        .append_pair("response_type", "code")
        .append_pair("client_id", &client.client_id)
        .append_pair("redirect_uri", redirect)
        .append_pair("state", state)
        .append_pair("resource", resource)
        .append_pair("code_challenge", &challenge(verifier))
        .append_pair("code_challenge_method", "S256");
    if !scopes.is_empty() {
        query.append_pair("scope", &scopes.join(" "));
    }
    drop(query);
    Ok(url.to_string())
}
pub(super) struct CodeGrant<'a> {
    pub issuer: &'a Issuer,
    pub registration: &'a ClientRegistration,
    pub resource: &'a str,
    pub redirect: &'a str,
    pub verifier: &'a str,
    pub approved: &'a [String],
}
pub(super) async fn exchange(
    client: &reqwest::Client,
    grant: CodeGrant<'_>,
    code: &str,
    cancel: &CancellationToken,
) -> Result<Token> {
    let mut form = vec![
        ("grant_type".into(), "authorization_code".into()),
        ("code".into(), code.into()),
        ("redirect_uri".into(), grant.redirect.into()),
        ("code_verifier".into(), grant.verifier.into()),
        ("resource".into(), grant.resource.into()),
    ];
    let request = form_request(
        authenticated(
            client.post(&grant.issuer.token_endpoint),
            grant.registration,
            &mut form,
        )?,
        &form,
    );
    Token::parse(&json_response(request, cancel).await?, grant.approved)
}
pub(super) async fn refresh(
    client: &reqwest::Client,
    endpoint: &str,
    registration: &ClientRegistration,
    resource: &str,
    previous: &Token,
    cancel: &CancellationToken,
) -> Result<Token> {
    let refresh = previous
        .refresh_token
        .as_ref()
        .ok_or("The OAuth token has expired and requires authorization again.")?;
    let mut form = vec![
        ("grant_type".into(), "refresh_token".into()),
        ("refresh_token".into(), refresh.clone()),
        ("resource".into(), resource.into()),
    ];
    let request = form_request(
        authenticated(client.post(endpoint), registration, &mut form)?,
        &form,
    );
    let mut token = Token::parse(&json_response(request, cancel).await?, &previous.scopes)?;
    if token.refresh_token.is_none() {
        token.refresh_token = Some(refresh.clone());
    }
    Ok(token)
}
pub(super) async fn revoke(
    client: &reqwest::Client,
    endpoint: &str,
    registration: &ClientRegistration,
    token: &str,
    hint: &str,
    cancel: &CancellationToken,
) -> Result<()> {
    let mut form = vec![
        ("token".into(), token.into()),
        ("token_type_hint".into(), hint.into()),
    ];
    let request = form_request(
        authenticated(client.post(endpoint), registration, &mut form)?,
        &form,
    );
    let response = send(request, cancel).await?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(failure(
            format!("OAuth revocation returned HTTP {}.", response.status()),
            Delivery::Completed,
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pkce_and_token_validation_preserve_the_approved_scope_boundary() {
        assert_eq!(
            challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
        assert_eq!(verifier().len(), 96);
        assert!(
            Token::parse(
                &json!({"access_token":"opaque","token_type":"Bearer","scope":"read"}),
                &["read".into()]
            )
            .is_ok()
        );
        assert!(
            Token::parse(
                &json!({"access_token":"opaque","token_type":"Bearer","scope":"read write"}),
                &["read".into()]
            )
            .is_err()
        );
        assert!(Token::parse(&json!({"access_token":"opaque","token_type":"Other"}), &[]).is_err());
        assert_eq!(encoded("name: a+b"), "name%3A+a%2Bb");
    }
}
