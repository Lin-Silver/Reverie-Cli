use super::{BrowserAction, BrowserReply, BrowserRuntime, Result, RunControl, lock};
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, OpenOptions};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{self, Read, Write},
    path::Path,
};
use tempfile::TempDir;
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

pub(super) enum Transfer {
    Upload {
        directory: TempDir,
        file: Value,
    },
    Download {
        directory: TempDir,
        parent: Dir,
        name: String,
        path: String,
    },
}

fn active(cancel: &CancellationToken) -> Result<()> {
    if cancel.is_cancelled() {
        return Err("Browser file transfer cancelled.".into());
    }
    Ok(())
}

// Open each directory by handle. A renamed parent or a symlink cannot redirect
// the final open or publication to an arbitrary absolute path.
fn destination(root: &Path, value: &str) -> Result<(Dir, String)> {
    let relative = value.replace('\\', "/");
    let mut parts = relative.split('/').peekable();
    let mut parent = Dir::open_ambient_dir(root, cap_std::ambient_authority())?;
    while let Some(part) = parts.next() {
        let stem = part.split('.').next().unwrap_or("").to_ascii_uppercase();
        if part.is_empty()
            || part.ends_with(['.', ' '])
            || part.contains([':', '?', '*', '"', '<', '>', '|'])
            || part.chars().any(char::is_control)
            || part.eq_ignore_ascii_case(".reverie")
            || part.eq_ignore_ascii_case(".git")
            || matches!(
                stem.as_str(),
                "CON" | "NUL" | "PRN" | "AUX" | "CONIN$" | "CONOUT$"
            )
            || stem
                .strip_prefix("COM")
                .or_else(|| stem.strip_prefix("LPT"))
                .is_some_and(|n| {
                    n.len() == 1 && n.as_bytes()[0].is_ascii_digit() || matches!(n, "¹" | "²" | "³")
                })
        {
            return Err(
                "Use a relative workspace file path outside Reverie and Git metadata.".into(),
            );
        }
        if parts.peek().is_none() {
            return Ok((parent, part.to_owned()));
        }
        parent = parent.open_dir_nofollow(part)?;
    }
    Err("A workspace filename is required.".into())
}

fn copy(
    source: &mut impl Read,
    output: &mut impl Write,
    cancel: &CancellationToken,
) -> Result<(u64, String)> {
    let mut bytes = 0;
    let mut hash = Sha256::new();
    let mut buffer = vec![0; 64 * 1024];
    loop {
        active(cancel)?;
        let n = source.read(&mut buffer)?;
        if n == 0 {
            return Ok((
                bytes,
                hash.finalize()
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect(),
            ));
        }
        output.write_all(&buffer[..n])?;
        hash.update(&buffer[..n]);
        bytes += n as u64;
    }
}

pub(super) async fn prepare(
    action: &BrowserAction,
    root: &Path,
    cancel: &CancellationToken,
) -> Result<Option<(String, Transfer)>> {
    let (upload, path) = match action {
        BrowserAction::Upload { path, .. } => (true, path.clone()),
        BrowserAction::Download { path, .. } => (false, path.clone()),
        _ => return Ok(None),
    };
    let root = root.to_owned();
    let cancel = cancel.clone();
    tokio::task::spawn_blocking(move || {
        active(&cancel)?;
        let (parent, name) = destination(&root, &path)?;
        let directory = tempfile::Builder::new()
            .prefix("reverie-browser-")
            .tempdir()?;
        let staged = directory
            .path()
            .join(if upload { &name } else { "download" });
        let transfer = if upload {
            let mut source = parent.open_with(
                &name,
                OpenOptions::new()
                    .read(true)
                    .follow(FollowSymlinks::No)
                    .nonblock(true),
            )?;
            if !source.metadata()?.is_file() {
                return Err("Choose a regular file for upload.".into());
            }
            let (bytes, sha256) = copy(&mut source, &mut fs::File::create_new(&staged)?, &cancel)?;
            Transfer::Upload {
                directory,
                file: json!({"path":path,"bytes":bytes,"sha256":sha256}),
            }
        } else {
            match parent.symlink_metadata(&name) {
                Err(error) if error.kind() == io::ErrorKind::NotFound => (),
                Err(error) => return Err(error.into()),
                Ok(_) => return Err("Download destination already exists.".into()),
            }
            Transfer::Download {
                directory,
                parent,
                name,
                path,
            }
        };
        let staged = staged
            .to_str()
            .ok_or("Browser transfer staging path requires UTF-8.")?
            .to_owned();
        Ok(Some((staged, transfer)))
    })
    .await?
}

struct PendingFile {
    parent: Dir,
    temporary: String,
}

impl Drop for PendingFile {
    fn drop(&mut self) {
        let _ = self.parent.remove_file(&self.temporary);
    }
}

impl Transfer {
    pub(super) async fn finish(
        self,
        runtime: &BrowserRuntime,
        reply: &BrowserReply,
        control: &RunControl,
    ) -> Result<Value> {
        match self {
            Self::Upload { directory, file } => {
                runtime.keep_upload(reply, directory)?;
                Ok(file)
            }
            Self::Download {
                directory,
                parent,
                name,
                path,
            } => {
                let cancel = control.cancel.clone();
                let (pending, bytes, sha256) = tokio::task::spawn_blocking(move || -> Result<_> {
                    active(&cancel)?;
                    let mut source = fs::File::open(directory.path().join("download"))?;
                    let temporary = format!(".reverie-{}.part", Uuid::new_v4().simple());
                    let mut staged = parent
                        .open_with(&temporary, OpenOptions::new().create_new(true).write(true))?;
                    let pending = PendingFile { parent, temporary };
                    let (bytes, sha256) = copy(&mut source, &mut staged, &cancel)?;
                    staged.sync_all()?;
                    Ok((pending, bytes, sha256))
                })
                .await??;
                let _commit = lock(&control.commit_gate)?;
                active(&control.cancel)?;
                // Atomic no-clobber publication. Both names belong to the same open directory.
                pending
                    .parent
                    .hard_link(&pending.temporary, &pending.parent, &name)?;
                Ok(json!({"path":path,"bytes":bytes,"sha256":sha256}))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::browser::BrowserTarget;

    #[test]
    fn file_paths_reject_parent_devices_metadata_and_absolute_names() {
        let root = tempfile::tempdir().unwrap();
        for path in [
            "",
            "../other",
            "sub/../other",
            "/outside",
            "C:\\outside",
            "alternate:stream",
            "CON.txt",
            ".Git/config",
            ".REVERIE/config.json",
            "file.",
        ] {
            assert!(destination(root.path(), path).is_err(), "{path}");
        }
        fs::create_dir(root.path().join("目录")).unwrap();
        assert_eq!(
            destination(root.path(), "目录/test.bin").unwrap().1,
            "test.bin"
        );
    }

    #[tokio::test]
    async fn upload_snapshot_has_the_original_bytes_and_releases_its_private_file() {
        let root = tempfile::tempdir().unwrap();
        let name = "作品.bin";
        let source = root.path().join(name);
        fs::write(&source, [0, 128, 255]).unwrap();
        let action = BrowserAction::Upload {
            target: BrowserTarget {
                tab_id: "t".into(),
                observation_id: "o".into(),
                revision: 1,
            },
            origin: "https://example.test".into(),
            element_id: "e".into(),
            path: name.into(),
        };
        let cancel = CancellationToken::new();
        let (staged, guard) = prepare(&action, root.path(), &cancel)
            .await
            .unwrap()
            .unwrap();
        fs::write(&source, b"changed").unwrap();
        assert_eq!(fs::read(&staged).unwrap(), [0, 128, 255]);
        assert_eq!(Path::new(&staged).file_name().unwrap(), name);
        drop(guard);
        assert!(!Path::new(&staged).exists());
        cancel.cancel();
        assert!(prepare(&action, root.path(), &cancel).await.is_err());
    }
}
