mod builtin;
mod policy;
mod process_tree;

use crate::{Result, ToolResult, workspace_path};
use builtin::MOTION_ENTRY;
pub use builtin::motion_entry;
use policy::Invocation;
pub use process_tree::ProcessTree;
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{ExitStatus, Stdio},
    sync::Mutex,
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncRead, AsyncReadExt},
    process::Command,
};
use tokio_util::sync::CancellationToken;

const OUTPUT_LIMIT: usize = 50_000;
static AUDIT_LOCK: Mutex<()> = Mutex::new(());

pub fn is_command(name: &str) -> bool {
    matches!(name, "command_exec" | "shell" | "terminal" | "run_command")
}

#[derive(Default)]
struct Capture {
    output: String,
    pending: Vec<u8>,
    characters: usize,
    displayed: usize,
    error: Option<String>,
}

impl Capture {
    fn append(&mut self, text: &str, emit: &impl Fn(&str)) {
        let available = OUTPUT_LIMIT.saturating_sub(self.displayed);
        let shown: String = text.chars().take(available).collect();
        self.characters = self.characters.saturating_add(text.chars().count());
        self.displayed += shown.chars().count();
        self.output.push_str(&shown);
        if !shown.is_empty() {
            emit(&shown);
        }
    }
    fn decode(&mut self, bytes: &[u8], eof: bool, emit: &impl Fn(&str)) {
        self.pending.extend_from_slice(bytes);
        loop {
            match std::str::from_utf8(&self.pending) {
                Ok(text) => {
                    let text = text.to_owned();
                    self.pending.clear();
                    self.append(&text, emit);
                    break;
                }
                Err(error) => {
                    let valid = error.valid_up_to();
                    let text = std::str::from_utf8(&self.pending[..valid])
                        .unwrap()
                        .to_owned();
                    self.append(&text, emit);
                    self.pending.drain(..valid);
                    if let Some(length) = error.error_len() {
                        self.pending.drain(..length);
                        self.append("\u{fffd}", emit);
                    } else {
                        if eof {
                            self.pending.clear();
                            self.append("\u{fffd}", emit);
                        }
                        break;
                    }
                }
            }
        }
    }
    fn finish(&mut self) {
        if self.characters > OUTPUT_LIMIT {
            self.output.push_str(&format!(
                "\n...[truncated {} characters]",
                self.characters - OUTPUT_LIMIT
            ));
        }
    }
}

async fn capture(mut pipe: impl AsyncRead + Unpin, result: &mut Capture, emit: impl Fn(&str)) {
    let mut bytes = [0; 8192];
    loop {
        match pipe.read(&mut bytes).await {
            Ok(0) => {
                result.decode(&[], true, &emit);
                break;
            }
            Ok(count) => result.decode(&bytes[..count], false, &emit),
            Err(error) => {
                result.error = Some(error.to_string());
                break;
            }
        }
    }
}

pub fn audit(directory: &Path, mut event: Value) -> Result<()> {
    let _guard = AUDIT_LOCK
        .lock()
        .map_err(|_| "Command audit lock was poisoned.")?;
    event["timestamp"] = json!(chrono::Utc::now().to_rfc3339());
    event["tool"] = json!("command_exec");
    let directory = directory.join("security");
    fs::create_dir_all(&directory)?;
    let mut options = fs::OpenOptions::new();
    options.append(true).create(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(directory.join("command_audit.jsonl"))?;
    let mut line = serde_json::to_vec(&event)?;
    line.push(b'\n');
    file.write_all(&line)?;
    file.sync_data()?;
    Ok(())
}

fn environment(
    command: &mut Command,
    invocation: &Invocation,
    root: &Path,
    data: &Path,
) -> Result<()> {
    let key = policy::executable_key(&invocation.argv[0]);
    if key == "dotnet" {
        let base = data.join("runtime_sandbox/dotnet");
        for (key, path) in [
            ("DOTNET_CLI_HOME", "home"),
            ("NUGET_PACKAGES", "nuget/packages"),
            ("NUGET_HTTP_CACHE_PATH", "nuget/http-cache"),
            ("NUGET_SCRATCH", "nuget/scratch"),
            ("TMP", "tmp"),
            ("TEMP", "tmp"),
            ("HOME", "home"),
            ("USERPROFILE", "home"),
            ("APPDATA", "appdata"),
            ("LOCALAPPDATA", "localappdata"),
            ("XDG_CACHE_HOME", "xdg/cache"),
            ("XDG_CONFIG_HOME", "xdg/config"),
            ("XDG_DATA_HOME", "xdg/data"),
        ] {
            let directory = base.join(path);
            fs::create_dir_all(&directory)?;
            command.env(key, directory);
        }
        for (key, value) in [
            ("DOTNET_SKIP_FIRST_TIME_EXPERIENCE", "1"),
            ("DOTNET_CLI_TELEMETRY_OPTOUT", "1"),
            ("DOTNET_NOLOGO", "1"),
            ("DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE", "1"),
            ("DOTNET_ADD_GLOBAL_TOOLS_TO_PATH", "0"),
            ("DOTNET_GENERATE_ASPNET_CERTIFICATE", "false"),
            ("MSBUILDDISABLENODEREUSE", "1"),
        ] {
            command.env(key, value);
        }
    }
    if ["pip", "pip3", "pip.exe", "pip3.exe", "uv", "poetry"].contains(&key.as_str())
        || (["python", "py"].contains(&key.as_str())
            && invocation.argv.get(1).is_some_and(|arg| arg == "-m")
            && invocation
                .argv
                .get(2)
                .is_some_and(|arg| ["pip", "pip3"].contains(&arg.as_str())))
    {
        command.env("PIP_DISABLE_PIP_VERSION_CHECK", "1");
        for base in [&invocation.cwd, root] {
            let venv = [".venv", "venv"]
                .into_iter()
                .map(|name| base.join(name))
                .find(|path| path.is_dir());
            if let Some(venv) = venv {
                let venv = workspace_path(
                    root,
                    venv.to_str()
                        .ok_or("Virtual environment path must be Unicode.")?,
                )?;
                let bin = venv.join(if cfg!(windows) { "Scripts" } else { "bin" });
                if bin.is_dir() {
                    let paths = std::iter::once(bin)
                        .chain(std::env::split_paths(
                            &std::env::var_os("PATH").unwrap_or_default(),
                        ))
                        .collect::<Vec<PathBuf>>();
                    command.env("PATH", std::env::join_paths(paths)?);
                }
                command.env("VIRTUAL_ENV", venv);
                break;
            }
        }
    }
    Ok(())
}

pub async fn execute(
    args: &Value,
    root: &Path,
    data: &Path,
    cancel: &CancellationToken,
    emit: &impl Fn(&str, &str),
) -> ToolResult {
    let command = args["command"].as_str().unwrap_or_default().trim();
    let cwd = args["cwd"].as_str().unwrap_or(".");
    let prepared = (|| -> Result<(Invocation, u64)> {
        if !args.is_object() {
            return Err("Command arguments must be an object.".into());
        }
        if args["env"].as_object().is_some_and(|env| !env.is_empty())
            || (!args["env"].is_null() && !args["env"].is_object())
        {
            return Err("Custom environment overrides are disabled in secure command mode.".into());
        }
        let timeout = if args["timeout"].is_null() {
            120
        } else {
            args["timeout"]
                .as_u64()
                .filter(|seconds| *seconds > 0)
                .ok_or("Timeout must be a positive integer in seconds.")?
        };
        tokio::time::Instant::now()
            .checked_add(Duration::from_secs(timeout))
            .ok_or("Command timeout exceeds the supported clock range.")?;
        Ok((policy::prepare(command, root, cwd)?, timeout))
    })();
    let (invocation, timeout) = match prepared {
        Ok(value) => value,
        Err(error) => {
            let event = json!({"event":"command_blocked","allowed":false,"command":command,"cwd":cwd,"reason":error.to_string(),"delivery":"not_started"});
            let audited = audit(data, event);
            let mut result = ToolResult::fail(match audited {
                Ok(()) => error.to_string(),
                Err(audit_error) => format!("{error}; audit failed: {audit_error}"),
            });
            result.data = json!({"delivery":"not_started"});
            return result;
        }
    };
    if cancel.is_cancelled() {
        return ToolResult::not_started("Command cancelled before execution.");
    }
    match execute_prepared(command, &invocation, timeout, root, data, cancel, emit).await {
        Ok(result) => result,
        Err(error) => {
            let delivery = if error
                .downcast_ref::<process_tree::AssignmentError>()
                .is_some()
            {
                "uncertain"
            } else {
                "not_started"
            };
            let mut result = ToolResult::fail(error);
            result.data = json!({"delivery":delivery});
            if let Err(audit_error) = audit(
                data,
                json!({"event":"command_start_failed","allowed":true,"command":command,"cwd":invocation.cwd,"delivery":delivery,"reason":result.error}),
            ) {
                result.error = Some(format!(
                    "{}; audit failed: {audit_error}",
                    result.error.as_deref().unwrap_or_default()
                ));
            }
            result
        }
    }
}

async fn execute_prepared(
    command_text: &str,
    invocation: &Invocation,
    timeout: u64,
    root: &Path,
    data: &Path,
    cancel: &CancellationToken,
    emit: &impl Fn(&str, &str),
) -> Result<ToolResult> {
    audit(
        data,
        json!({"event":"command_attempt","allowed":true,"command":command_text,"argv":invocation.argv,"executor":invocation.executor,"policy":"workspace_blacklist","cwd":invocation.cwd,"timeout_seconds":timeout,"delivery":"not_started"}),
    )?;
    let mut command = Command::new(&invocation.argv[0]);
    command
        .args(&invocation.argv[1..])
        .current_dir(&invocation.cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    environment(&mut command, invocation, root, data)?;
    if invocation.executor == "builtin_motion" {
        command
            .env_remove("NODE_OPTIONS")
            .env_remove("NODE_PATH")
            .env("REVERIE_BUILTIN_WORKSPACE", root.canonicalize()?);
    }
    if cancel.is_cancelled() {
        return Ok(ToolResult::not_started(
            "Command cancelled before execution.",
        ));
    }
    let started = Instant::now();
    let (mut child, mut tree) = ProcessTree::spawn(&mut command)?;
    let pid = child.id();
    let mut stdout = Capture::default();
    let mut stderr = Capture::default();
    let deadline = tokio::time::sleep(Duration::from_secs(timeout));
    tokio::pin!(deadline);
    let mut cleanup_error = None;
    let outcome;
    let stdout_pipe = child.stdout.take().unwrap();
    let stderr_pipe = child.stderr.take().unwrap();
    {
        let readers = async {
            tokio::join!(
                capture(stdout_pipe, &mut stdout, |text| emit("stdout", text)),
                capture(stderr_pipe, &mut stderr, |text| emit("stderr", text))
            );
        };
        tokio::pin!(readers);
        let mut readers_done = false;
        outcome = tokio::select! {
            biased;
            _=cancel.cancelled()=>Err("Command stopped by user."),
            _=&mut deadline=>Err("Command timed out."),
            result=child.wait()=>Ok(result),
            _=&mut readers=> {
                readers_done=true;
                tokio::select! {
                    biased;
                    _=cancel.cancelled()=>Err("Command stopped by user."),
                    _=&mut deadline=>Err("Command timed out."),
                    result=child.wait()=>Ok(result),
                }
            }
        };
        if let Err(error) = tree.stop() {
            cleanup_error = Some(error.to_string());
        }
        if !readers_done
            && tokio::time::timeout(Duration::from_secs(2), &mut readers)
                .await
                .is_err()
        {
            cleanup_error =
                Some("Command output pipes did not close after process-tree cleanup.".into());
        }
    }
    let (status, reason, exit) = match outcome {
        Ok(Ok(exit)) => (
            if exit.success() { "success" } else { "partial" },
            None,
            Some(exit),
        ),
        Ok(Err(error)) => ("error", Some(error.to_string()), None),
        Err(reason) => {
            let exit = tokio::time::timeout(Duration::from_secs(2), child.wait())
                .await
                .ok()
                .and_then(|result| result.ok());
            (
                if cancel.is_cancelled() {
                    "cancelled"
                } else {
                    "timeout"
                },
                Some(reason.to_owned()),
                exit,
            )
        }
    };
    stdout.finish();
    stderr.finish();
    let duration = started.elapsed().as_millis();
    let exit_code = exit.as_ref().and_then(ExitStatus::code);
    let error = cleanup_error
        .or(stdout.error)
        .or(stderr.error)
        .or(reason)
        .or_else(|| {
            (status == "partial").then(|| format!("Command exited with code {exit_code:?}."))
        });
    let success = status == "success" && error.is_none();
    let mut result = ToolResult::ok(
        format!(
            "$ {command_text}\nWorking directory: {}\nExecutor: {}\nPolicy: workspace_blacklist\nExit code: {exit_code:?}\nDuration: {duration}ms\n\n--- STDOUT ---\n{}\n\n--- STDERR ---\n{}",
            invocation.cwd.display(),
            invocation.executor,
            stdout.output,
            stderr.output
        ),
        json!({"exit_code":exit_code,"success":success,"duration_ms":duration,"pid":pid,"delivery":"executed","stdout":stdout.output,"stderr":stderr.output,"stdout_characters":stdout.characters,"stderr_characters":stderr.characters}),
    );
    result.success = success;
    result.error = error;
    result.status = if status == "success" && !success {
        "error"
    } else {
        status
    }
    .into();
    if let Err(error) = audit(
        data,
        json!({"event":"command_result","allowed":true,"command":command_text,"executor":invocation.executor,"cwd":invocation.cwd,"timeout_seconds":timeout,"duration_ms":duration,"pid":pid,"exit_code":exit_code,"status":result.status,"delivery":"executed"}),
    ) {
        result.success = false;
        result.status = "partial".into();
        result.error = Some(format!(
            "Command executed, but its final audit could not be saved: {error}"
        ));
    }
    Ok(result)
}
