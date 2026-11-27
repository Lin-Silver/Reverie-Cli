use super::failure;
use crate::Result;
use serde_json::Value;
use std::{fs, io::Read, path::PathBuf, process::Stdio, time::Duration};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    process::Command,
};
use tokio_util::sync::CancellationToken;

const MANIFEST: &str = include_str!("../../../../../resources/computer-use/manifest.json");
const BINARY: &str = if cfg!(windows) {
    "agent-desktop.exe"
} else {
    "agent-desktop"
};

pub(super) fn binary() -> Option<PathBuf> {
    Some(
        std::env::current_exe()
            .ok()?
            .parent()?
            .join("computer-use")
            .join(BINARY),
    )
}

pub(super) struct Native {
    directory: tempfile::TempDir,
    session: String,
}

impl Native {
    pub(super) fn scratch(&self) -> &std::path::Path {
        self.directory.path()
    }

    pub(super) fn open() -> Result<Self> {
        let manifest: Value = serde_json::from_str(MANIFEST)?;
        let platform = format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH);
        let files = manifest["platforms"][platform]["files"]
            .as_object()
            .ok_or("Unsupported desktop engine platform.")?;
        let executable = binary()
            .filter(|p| p.is_file())
            .ok_or("Install the packaged Computer Use component alongside the kernel.")?;
        let directory = tempfile::Builder::new()
            .prefix("reverie-computer-")
            .tempdir()?;
        // Execute only the bytes verified against the kernel's embedded pins, including native helpers.
        for (name, expected) in files {
            let mut bytes = Vec::new();
            fs::File::open(executable.with_file_name(name))?
                .take(32 * 1024 * 1024)
                .read_to_end(&mut bytes)?;
            if expected.as_str() != Some(&crate::plugins::package::digest(&bytes)) {
                return Err(format!("Bundled desktop component checksum mismatch: {name}").into());
            }
            let file = directory.path().join(name);
            fs::write(&file, bytes)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&file, fs::Permissions::from_mode(0o700))?;
            }
        }
        Ok(Self {
            directory,
            session: format!("reverie-{}", uuid::Uuid::new_v4().simple()),
        })
    }

    pub(super) async fn invoke(
        &self,
        name: &str,
        args: &[String],
        input: Option<&str>,
        timeout_ms: u64,
        writes: bool,
        cancel: &CancellationToken,
    ) -> Value {
        let mut command = Command::new(self.directory.path().join(BINARY));
        for (key, _) in std::env::vars_os() {
            let name = key.to_string_lossy().to_ascii_uppercase();
            if name.starts_with("AGENT_DESKTOP_")
                || name.starts_with("DYLD_")
                || name.starts_with("LD_")
            {
                command.env_remove(key);
            }
        }
        command
            .current_dir(self.directory.path())
            .env("AGENT_DESKTOP_HOME", self.directory.path().join("state"))
            .args(["--session", &self.session, name])
            .args(args)
            .stdin(if input.is_some() {
                Stdio::piped()
            } else {
                Stdio::null()
            })
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x0800_0000);
        if cancel.is_cancelled() {
            return failure(
                name,
                "CANCELLED",
                "Cancelled before desktop dispatch.",
                false,
            );
        }
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(e) => return failure(name, "ENGINE_UNAVAILABLE", e, false),
        };
        let stdin = child.stdin.take();
        let mut stdout = child
            .stdout
            .take()
            .expect("piped desktop stdout")
            .take(8 * 1024 * 1024 + 1);
        let native = async {
            let write = async {
                if let (Some(mut pipe), Some(text)) = (stdin, input) {
                    pipe.write_all(text.as_bytes()).await?;
                }
                Ok::<_, std::io::Error>(())
            };
            let mut bytes = Vec::new();
            tokio::try_join!(write, stdout.read_to_end(&mut bytes))?;
            if bytes.len() > 8 * 1024 * 1024 {
                return Err(std::io::Error::other("Desktop result exceeds 8 MiB."));
            }
            Ok((child.wait().await?, bytes))
        };
        let deadline = Duration::from_millis(timeout_ms + 2000);
        let outcome = tokio::select! {biased;
            _ = cancel.cancelled() => Err(("CANCELLED","Desktop operation cancelled after dispatch.".to_owned())),
            result = tokio::time::timeout(deadline,native) => match result {
                Ok(Ok(output)) => Ok(output),
                Ok(Err(e)) => Err(("NATIVE_EXIT",e.to_string())),
                Err(_) => Err(("TIMEOUT","Desktop operation exceeded its deadline.".to_owned())),
            }
        };
        let (status, bytes) = match outcome {
            Ok(output) => output,
            Err((code, message)) => {
                let _ = child.kill().await;
                return failure(name, code, message, writes);
            }
        };
        if let Ok(reply) = serde_json::from_slice::<Value>(&bytes)
            && reply["version"] == "2.6"
            && reply["command"] == name
            && ((reply["ok"] == true
                && status.success()
                && (reply["data"].is_object() || reply["data"].is_array()))
                || (reply["ok"] == false && reply["error"].is_object()))
        {
            return reply;
        }
        failure(
            name,
            "INVALID_RESPONSE",
            format!("Invalid protocol 2.6 result from desktop process ({status})."),
            writes,
        )
    }
}
