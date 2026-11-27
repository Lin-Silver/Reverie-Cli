use crate::{Result, browser::*, host::EventSink};
use serde_json::{Value, json};
use std::{
    env,
    path::{Path, PathBuf},
    process::Stdio,
    sync::Arc,
    time::Duration,
};
use tokio::{
    io::{AsyncBufRead, AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader, Lines},
    net::{TcpListener, TcpStream, tcp::OwnedWriteHalf},
    process::Command,
    sync::mpsc,
    task::JoinHandle,
};
use tokio_util::sync::CancellationToken;

pub(super) fn locate() -> Option<PathBuf> {
    let name = if cfg!(windows) {
        "ReverieUI.exe"
    } else {
        "ReverieUI"
    };
    let path = match env::var_os("REVERIE_BROWSER_COMPONENT") {
        Some(value) => PathBuf::from(value),
        None => {
            let binary = env::current_exe().ok()?;
            let dir = binary.parent()?;
            if cfg!(target_os = "macos") {
                dir.join("MacOS").join(name)
            } else {
                dir.join(name)
            }
        }
    };
    (path.is_absolute() && path.file_name()? == name && path.is_file()).then_some(path)
}

pub(in crate::host) struct Component {
    pub(super) runtime: BrowserRuntime,
    pub(super) key: AdapterKey,
    pub(super) sink: EventSink,
    stop: CancellationToken,
    worker: JoinHandle<()>,
}

async fn send(pipe: &mut OwnedWriteHalf, value: &Value) -> Result<()> {
    let mut line = serde_json::to_vec(value)?;
    line.push(b'\n');
    pipe.write_all(&line).await?;
    Ok(())
}

async fn accept_component(listener: &TcpListener, token: &[u8; 32]) -> Result<TcpStream> {
    loop {
        let (mut socket, _) = listener.accept().await?;
        let mut proof = [0; 32];
        if matches!(
            tokio::time::timeout(Duration::from_secs(1), socket.read_exact(&mut proof)).await,
            Ok(Ok(_))
        ) && proof == *token
        {
            return Ok(socket);
        }
    }
}

async fn next_message(input: &mut Lines<impl AsyncBufRead + Unpin>) -> Result<Option<Value>> {
    while let Some(line) = input.next_line().await? {
        if !line.trim().is_empty() {
            return Ok(Some(serde_json::from_str(&line)?));
        }
    }
    Ok(None)
}

impl Component {
    pub(super) async fn open(
        path: &Path,
        app: &Path,
        profile: &BrowserProfile,
        cancel: &CancellationToken,
    ) -> Result<Self> {
        let base = app.join(".reverie/browser-component");
        std::fs::create_dir_all(&base)?;
        let temp = match profile.mode {
            ProfileMode::Ephemeral => {
                Some(tempfile::Builder::new().prefix("run-").tempdir_in(&base)?)
            }
            ProfileMode::Persistent => None,
        };
        let persistent = base.join("persistent");
        let directory = temp.as_ref().map_or(persistent.as_path(), |dir| dir.path());
        let listener = TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0)).await?;
        let token = uuid::Uuid::new_v4().simple().to_string();
        let mut child = Command::new(path)
            .arg("--reverie-browser-host")
            .env("REVERIE_BROWSER_DATA", directory)
            .env(
                "REVERIE_BROWSER_PORT",
                listener.local_addr()?.port().to_string(),
            )
            .env("REVERIE_BROWSER_TOKEN", &token)
            .env(
                "REVERIE_BROWSER_ACTIONS",
                serde_json::to_string(ActionKind::ALL)?,
            )
            .env_remove("ELECTRON_RUN_AS_NODE")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn()?;
        let deadline = tokio::time::Instant::now() + Duration::from_secs(20);
        let socket = tokio::select! {
            _ = cancel.cancelled() => return Err("Browser component startup cancelled.".into()),
            status = child.wait() => return Err(format!("Browser component exited before connecting ({}).",status?).into()),
            result = tokio::time::timeout_at(deadline,accept_component(&listener,token.as_bytes().try_into()?)) => result??
        };
        drop(listener);
        let (reader, mut input) = socket.into_split();
        let mut out = BufReader::new(reader).lines();
        let ready = tokio::select! {
            _ = cancel.cancelled() => return Err("Browser component startup cancelled.".into()),
            result = tokio::time::timeout_at(deadline,next_message(&mut out)) => result??
        }
        .ok_or("The browser component exited before startup. Its profile may already be in use.")?;
        if ready["protocol"] != BROWSER_PROTOCOL {
            return Err("Incompatible browser component.".into());
        }
        let runtime = BrowserRuntime::new();
        let key =
            runtime.register_adapter(serde_json::from_value(ready["descriptor"].clone())?, true)?;
        send(
            &mut input,
            &json!({"type":"browser.attach","host":key.host()}),
        )
        .await?;
        let (tx, mut rx) = mpsc::unbounded_channel::<Value>();
        let stop = CancellationToken::new();
        let stopped = stop.clone();
        let active = runtime.clone();
        let bound = key.clone();
        let worker = tokio::spawn(async move {
            loop {
                tokio::select! {
                    biased;
                    _ = stopped.cancelled() => break,
                    item = rx.recv() => match item {
                        Some(event) => if send(&mut input,&event).await.is_err() {break;},
                        None => break,
                    },
                    response = next_message(&mut out) => {
                        let Ok(Some(message)) = response else {break};
                        let result: Result<()> = (|| {
                            match message["type"].as_str() {
                                Some("complete") => active.complete_json(&bound,message["completion"].clone())?,
                                Some("invalidate") => {
                                    let item = &message["invalidation"];
                                    active.update_tab_revision(&bound,&serde_json::from_value(item["scope"].clone())?,
                                        &serde_json::from_value(item["profile"].clone())?,item["tab_id"].as_str().ok_or("Missing tab.")?,
                                        item["revision"].as_u64().ok_or("Missing revision.")?,item["closed"]==true)?;
                                }
                                _ => return Err("Unknown browser component response.".into()),
                            }
                            Ok(())
                        })();
                        if let Err(error) = result {
                            // A cancellation can retire a request just before its completion arrives.
                            if !matches!(error.downcast_ref::<BrowserFailure>(),Some(failure) if failure.code == FailureCode::UnknownRequest) {break;}
                        }
                    }
                }
            }
            let _ = active.unregister_adapter(&bound);
            let _ = input.shutdown().await;
            drop(input);
            if tokio::time::timeout(Duration::from_secs(5), child.wait())
                .await
                .is_err()
            {
                let _ = child.kill().await;
            }
            drop(temp);
        });
        Ok(Self {
            runtime,
            key,
            sink: Arc::new(move |event| {
                let _ = tx.send(event);
            }),
            stop,
            worker,
        })
    }

    pub(in crate::host) async fn close(self) {
        self.stop.cancel();
        let _ = self.worker.await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn reads_component_records_and_rejects_non_json() {
        let mut pipe = BufReader::new(&b"\r\n{\"ready\":true}\r\ninvalid\n"[..]).lines();
        assert_eq!(
            next_message(&mut pipe).await.unwrap(),
            Some(json!({"ready":true}))
        );
        assert!(next_message(&mut pipe).await.is_err());
        assert!(next_message(&mut pipe).await.unwrap().is_none());
    }

    #[tokio::test]
    async fn component_connection_requires_the_launch_token() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let address = listener.local_addr().unwrap();
        let task =
            tokio::spawn(async move { accept_component(&listener, &[7; 32]).await.unwrap() });
        let mut other = TcpStream::connect(address).await.unwrap();
        other.write_all(&[1; 32]).await.unwrap();
        let mut owner = TcpStream::connect(address).await.unwrap();
        owner.write_all(&[7; 32]).await.unwrap();
        assert_eq!(
            task.await.unwrap().peer_addr().unwrap(),
            owner.local_addr().unwrap()
        );
    }
}
