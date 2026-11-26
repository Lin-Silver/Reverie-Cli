use crate::{Result, mcp::Notify};
use reqwest::Url;
use std::{
    collections::BTreeMap,
    net::{IpAddr, Ipv4Addr},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
};
use tokio_util::sync::CancellationToken;

pub(super) struct Callback {
    listener: TcpListener,
    pub redirect_uri: String,
}
impl Callback {
    pub async fn bind(requested: Option<&str>) -> Result<Self> {
        let mut url = Url::parse(requested.unwrap_or("http://127.0.0.1:0/callback"))?;
        let address = match url.host_str().unwrap_or("").trim_matches(['[', ']']) {
            host if host.eq_ignore_ascii_case("localhost") => IpAddr::V4(Ipv4Addr::LOCALHOST),
            host => host
                .parse::<IpAddr>()
                .map_err(|_| "OAuth callbacks must use a loopback address.")?,
        };
        if url.scheme() != "http"
            || !address.is_loopback()
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
        {
            return Err("OAuth callback must be a clean HTTP loopback URI.".into());
        }
        let listener =
            TcpListener::bind((address, url.port_or_known_default().unwrap_or(0))).await?;
        url.set_port(Some(listener.local_addr()?.port()))
            .map_err(|_| "OAuth callback port could not be set.")?;
        Ok(Self {
            listener,
            redirect_uri: url.to_string(),
        })
    }
    pub async fn wait(
        self,
        state: &str,
        issuer: &str,
        require_issuer: bool,
        cancel: &CancellationToken,
        notify: Notify,
    ) -> Result<String> {
        let operation = async {
            let base = Url::parse(&self.redirect_uri)?;
            loop {
                let (mut socket, peer) = self.listener.accept().await?;
                if !peer.ip().is_loopback() {
                    continue;
                }
                let request = tokio::time::timeout(
                    std::time::Duration::from_secs(2),
                    read_request(&mut socket),
                )
                .await;
                let result = match request {
                    Ok(Ok(request)) => validate(&request, &base, state, issuer, require_issuer),
                    _ => None,
                };
                let (status, text) = if result.is_some() {
                    ("200 OK", "Authorization received. Return to Reverie CLI.")
                } else {
                    (
                        "400 Bad Request",
                        "This authorization response could not be accepted.",
                    )
                };
                let bytes = format!(
                    "HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {}\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nContent-Security-Policy: default-src 'none'\r\nConnection: close\r\n\r\n{text}",
                    text.len()
                );
                let _ = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    socket.write_all(bytes.as_bytes()),
                )
                .await;
                if let Some(result) = result {
                    notify(
                        serde_json::json!({"type":"connector.authorization","status":if result.is_ok(){"callback_received"}else{"denied"}}),
                    );
                    return result;
                }
            }
        };
        tokio::select! {
            _=cancel.cancelled()=>Err("Connector authorization cancelled.".into()),
            result=tokio::time::timeout(std::time::Duration::from_secs(600),operation)=>result.unwrap_or_else(|_|Err("Connector authorization expired; start again.".into())),
        }
    }
}
async fn read_request(socket: &mut TcpStream) -> Result<String> {
    let mut bytes = Vec::new();
    let mut chunk = [0; 2048];
    loop {
        let count = socket.read(&mut chunk).await?;
        if count == 0 {
            return Err("OAuth callback request ended before its headers.".into());
        }
        bytes.extend_from_slice(&chunk[..count]);
        if bytes.len() > 16384 {
            return Err("OAuth callback headers exceed 16 KiB.".into());
        }
        if bytes.windows(4).any(|value| value == b"\r\n\r\n") {
            return Ok(String::from_utf8(bytes)?);
        }
    }
}
fn validate(
    request: &str,
    base: &Url,
    state: &str,
    issuer: &str,
    require_issuer: bool,
) -> Option<Result<String>> {
    let mut lines = request.split("\r\n");
    let mut line = lines.next()?.split_ascii_whitespace();
    if line.next()? != "GET" {
        return None;
    }
    let target = line.next()?;
    if !target.starts_with('/') || target.starts_with("//") || line.next()? != "HTTP/1.1" {
        return None;
    }
    let hosts = lines
        .clone()
        .filter_map(|line| line.split_once(':'))
        .filter(|(name, _)| name.eq_ignore_ascii_case("host"))
        .collect::<Vec<_>>();
    let expected_host = format!("{}:{}", base.host_str()?, base.port()?);
    if hosts.len() != 1 || !hosts[0].1.trim().eq_ignore_ascii_case(&expected_host) {
        return None;
    }
    let url = base.join(target).ok()?;
    if url.origin() != base.origin() || url.path() != base.path() || url.fragment().is_some() {
        return None;
    }
    let mut values = BTreeMap::new();
    for (name, value) in url.query_pairs() {
        if values
            .insert(name.into_owned(), value.into_owned())
            .is_some()
        {
            return None;
        }
    }
    if values.get("state").map(String::as_str) != Some(state) {
        return None;
    }
    if values.get("iss").is_some_and(|value| value != issuer)
        || (require_issuer && !values.contains_key("iss"))
    {
        return None;
    }
    if values.contains_key("error") {
        return Some(Err(
            "Authorization was not granted; a new authorization is required.".into(),
        ));
    }
    let code = values.get("code")?;
    if code.is_empty() || code.len() > 4096 || code.contains(['\0', '\r', '\n']) {
        return None;
    }
    Some(Ok(code.clone()))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn binds_callback_to_state_issuer_host_and_path() {
        let base = Url::parse("http://127.0.0.1:32123/callback").unwrap();
        let request = "GET /callback?state=expected&code=opaque&iss=https%3A%2F%2Fissuer.test HTTP/1.1\r\nHost: 127.0.0.1:32123\r\n\r\n";
        assert_eq!(
            validate(request, &base, "expected", "https://issuer.test", true)
                .unwrap()
                .unwrap(),
            "opaque"
        );
        assert!(validate(request, &base, "different", "https://issuer.test", true).is_none());
        assert!(validate(request, &base, "expected", "https://different.test", true).is_none());
        assert!(
            validate(
                &request.replace("Host: 127.0.0.1:32123", "Host: attacker.test"),
                &base,
                "expected",
                "https://issuer.test",
                true
            )
            .is_none()
        );
        assert!(
            validate(
                &request.replace("/callback?", "/other?"),
                &base,
                "expected",
                "https://issuer.test",
                true
            )
            .is_none()
        );
    }
}
