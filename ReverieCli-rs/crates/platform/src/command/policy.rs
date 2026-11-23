use crate::{Result, workspace_path};
use regex::Regex;
use std::{
    fs,
    path::{Path, PathBuf},
    sync::LazyLock,
};

pub struct Invocation {
    pub argv: Vec<String>,
    pub executor: &'static str,
    pub cwd: PathBuf,
}

struct Token {
    text: String,
    operator: bool,
}

// These are the final Python command tool's destructive-operation checks.
// They are heuristics for reviewed scripts, not an operating-system sandbox.
static CATASTROPHIC: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
    r"(?i)\b(?:format(?:\.com)?\s+[a-z]:|mkfs(?:\.[a-z0-9]+)?\s+|diskpart\b|clear-disk\b|shutdown\b|restart-computer\b|stop-computer\b|bcdedit\b|bootrec\b)|\bdd\b[^\n]*\bof=(?:/dev/|\\\\\.\\physicaldrive)"
).unwrap()
});
static DELETION: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
    r"(?im)(?:^|[;&|]\s*)(?:rm|mv|rmdir|unlink|del|erase|move|ren|rename|rd|remove-item|move-item|rename-item)\b|(?:^|[;&|]\s*)git\s+(?:rm|mv|clean)\b|\bos\.(?:remove|unlink|rename|replace)\s*\(|\bshutil\.(?:move|rmtree)\s*\(|\b(?:pathlib\.)?Path\s*\([^)]*\)\s*\.\s*(?:unlink|rename|replace)\s*\(|\bSystem\.IO\.(?:File|Directory)\.(?:Delete|Move)\s*\(|\bfs(?:\.promises)?\.(?:rm|rmdir|unlink|rename)\s*\(|\b(?:rmSync|rmdirSync|unlinkSync|renameSync)\s*\("
).unwrap()
});
static CMDLET: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[A-Za-z][A-Za-z0-9]*-[A-Za-z][A-Za-z0-9-]*$").unwrap());
static PACKAGE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^@?[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)?(?:@[A-Za-z0-9._~^<>=*-]+)?$").unwrap()
});
static REGISTRY: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[A-Za-z0-9][A-Za-z0-9._~+:/@=-]*$").unwrap());

pub fn executable_key(value: &str) -> String {
    let key = value
        .rsplit(['/', '\\'])
        .next()
        .unwrap_or(value)
        .to_ascii_lowercase();
    key.strip_suffix(".exe").unwrap_or(&key).to_owned()
}

fn tokenize(command: &str) -> Result<Vec<Token>> {
    let mut tokens = Vec::new();
    let mut word = String::new();
    let mut quote = None;
    let mut active = false;
    let mut chars = command.chars().peekable();
    while let Some(ch) = chars.next() {
        if let Some(delimiter) = quote {
            if ch == delimiter {
                quote = None;
            } else if ch == '\\' && delimiter == '"' && chars.peek() == Some(&'"') {
                word.push(chars.next().unwrap());
            } else {
                word.push(ch);
            }
            continue;
        }
        match ch {
            '\'' | '"' => {
                quote = Some(ch);
                active = true;
            }
            '\\' if !cfg!(windows) => {
                word.push(chars.next().ok_or("Trailing command escape.")?);
                active = true;
            }
            ch if ch.is_whitespace() || matches!(ch, ';' | '&' | '|' | '<' | '>') => {
                if active {
                    tokens.push(Token {
                        text: std::mem::take(&mut word),
                        operator: false,
                    });
                    active = false;
                }
                if !ch.is_whitespace() {
                    let mut text = ch.to_string();
                    if chars.peek() == Some(&ch) {
                        text.push(chars.next().unwrap());
                    }
                    tokens.push(Token {
                        text,
                        operator: true,
                    });
                }
            }
            _ => {
                word.push(ch);
                active = true;
            }
        }
    }
    if quote.is_some() {
        return Err("Unclosed command quote.".into());
    }
    if active {
        tokens.push(Token {
            text: word,
            operator: false,
        });
    }
    Ok(tokens)
}

fn option(token: &str) -> bool {
    token.starts_with('-')
        || (cfg!(windows) && token.starts_with('/') && !token[1..].contains(['/', '\\']))
}

fn path_like(token: &str) -> bool {
    !token.contains("://")
        && (token.starts_with(['.', '~', '$', '%'])
            || token.contains(['/', '\\'])
            || [
                ".sln", ".csproj", ".fsproj", ".vbproj", ".props", ".targets", ".json", ".config",
                ".py", ".ps1", ".cmd", ".bat", ".sh", ".js", ".mjs", ".cjs", ".ts", ".zip",
            ]
            .iter()
            .any(|suffix| token.to_ascii_lowercase().ends_with(suffix)))
}

fn validate_argument(token: &str, key: &str, cwd: &Path, root: &Path) -> Result<()> {
    let value = token
        .split_once('=')
        .filter(|_| option(token))
        .map_or(token, |(_, value)| value);
    if value.is_empty() || value.contains("://") {
        return Ok(());
    }
    let normalized = value.replace('\\', "/");
    if normalized.split('/').any(|part| part == "..") {
        return Err("Parent-directory command arguments are not allowed.".into());
    }
    if cfg!(windows) && value.as_bytes().get(1) == Some(&b':') && !Path::new(value).is_absolute() {
        return Err("Drive-relative command paths are outside the workspace contract.".into());
    }
    if value.starts_with(['~', '$', '%']) {
        return Err("Use explicit workspace paths instead of environment-expanded paths.".into());
    }
    if option(value) && !Path::new(value).is_absolute() {
        return Ok(());
    }
    let native_path = if cfg!(windows) {
        value.to_owned()
    } else {
        value.replace('\\', "/")
    };
    let candidate = cwd.join(&native_path);
    let package = match key {
        "npm" | "npm.cmd" | "npx" | "npx.cmd" | "pnpm" | "pnpm.cmd" | "yarn" | "yarn.cmd"
        | "corepack" | "corepack.cmd" | "bun" | "deno" => PACKAGE.is_match(value),
        "cargo" | "rustc" | "rustup" | "rustfmt" | "clippy-driver" | "pip" | "pip3" | "uv"
        | "poetry" | "python" | "py" | "docker" | "docker-compose" | "podman" | "nerdctl" => {
            REGISTRY.is_match(value)
        }
        _ => false,
    };
    if package && !candidate.exists() && !Path::new(value).is_absolute() && !value.starts_with('.')
    {
        return Ok(());
    }
    if path_like(value) || candidate.exists() || Path::new(value).is_absolute() {
        workspace_path(
            root,
            candidate.to_str().ok_or("Command paths must be Unicode.")?,
        )?;
    }
    Ok(())
}

fn validate_segment(tokens: &[Token], root: &Path, cwd: &Path) -> Result<()> {
    let first = tokens.first().ok_or("Empty command pipeline stage.")?;
    let key = executable_key(&first.text);
    if [
        "rm",
        "mv",
        "rmdir",
        "unlink",
        "del",
        "erase",
        "move",
        "ren",
        "rename",
        "rd",
        "remove-item",
        "move-item",
        "rename-item",
    ]
    .contains(&key.as_str())
    {
        return Err(
            "Terminal move/delete operations are disabled. Use delete_file for deletions.".into(),
        );
    }
    let mut git_args = tokens.iter().skip(1);
    let git_subcommand = loop {
        let Some(token) = git_args.next() else {
            break None;
        };
        if ["--git-dir", "--work-tree", "--namespace", "--config-env"]
            .contains(&token.text.as_str())
        {
            git_args.next();
            continue;
        }
        if !option(&token.text) {
            break Some(token.text.to_ascii_lowercase());
        }
    };
    if key == "git"
        && git_subcommand
            .as_deref()
            .is_some_and(|subcommand| ["rm", "mv", "clean"].contains(&subcommand))
    {
        return Err(
            "Git move/delete operations are disabled. Use delete_file for deletions.".into(),
        );
    }
    if ["invoke-expression", "invoke-command", "start-process"].contains(&key.as_str()) {
        return Err("Dynamic PowerShell execution is disabled. Invoke a reviewed workspace script directly.".into());
    }
    for token in tokens.iter().skip(1) {
        let lower = token.text.to_ascii_lowercase();
        if [
            "-c",
            "-command",
            "--command",
            "-e",
            "--eval",
            "/c",
            "/k",
            "-enc",
            "-encodedcommand",
        ]
        .contains(&lower.split('=').next().unwrap_or_default())
            || (["node", "python", "py"].contains(&key.as_str())
                && (lower.starts_with("-e")
                    || lower.starts_with("-c")
                    || (key == "node"
                        && (lower.starts_with("-p") || lower.starts_with("--print")))))
        {
            return Err("Inline interpreter or opaque script code is disabled. Use a reviewed workspace script.".into());
        }
        if matches!(
            (key.as_str(), lower.as_str()),
            ("robocopy", "/mov" | "/move")
                | ("xcopy", "/move")
                | ("rsync", "--remove-source-files")
                | ("tar", "--remove-files")
        ) {
            return Err("The command flag performs a terminal move/delete operation.".into());
        }
        validate_argument(&token.text, &key, cwd, root)?;
    }
    let script = if ["python", "py", "node", "bash", "sh", "zsh"].contains(&key.as_str()) {
        if tokens.iter().any(|token| token.text == "-m") {
            None
        } else {
            tokens.iter().skip(1).find(|token| !option(&token.text))
        }
    } else if ["powershell", "pwsh"].contains(&key.as_str()) {
        tokens
            .windows(2)
            .find(|pair| ["-file", "-f"].contains(&pair[0].text.to_ascii_lowercase().as_str()))
            .map(|pair| &pair[1])
    } else if [
        "py", "js", "mjs", "cjs", "ps1", "cmd", "bat", "sh", "bash", "zsh",
    ]
    .iter()
    .any(|extension| {
        first
            .text
            .to_ascii_lowercase()
            .ends_with(&format!(".{extension}"))
    }) {
        Some(first)
    } else {
        None
    };
    if ["powershell", "pwsh"].contains(&key.as_str())
        && script.is_none()
        && !tokens.iter().any(|token| {
            ["-version", "--version"].contains(&token.text.to_ascii_lowercase().as_str())
        })
    {
        return Err("PowerShell must use a reviewed workspace file or the version option.".into());
    }
    if let Some(script) = script {
        let path = workspace_path(
            root,
            cwd.join(&script.text)
                .to_str()
                .ok_or("Script path must be Unicode.")?,
        )?;
        if path.is_file() {
            let bytes = fs::read(path)?;
            let content = String::from_utf8_lossy(&bytes);
            if CATASTROPHIC.is_match(&content) || DELETION.is_match(&content) {
                return Err(
                    "Reviewed workspace script contains a blocked move/delete or host operation."
                        .into(),
                );
            }
        }
    }
    Ok(())
}

pub fn prepare(command: &str, root: &Path, cwd: &str) -> Result<Invocation> {
    if command.trim().is_empty() || command.contains(['\0', '\n', '\r']) {
        return Err("Use one nonempty command line per call.".into());
    }
    if CATASTROPHIC.is_match(command) {
        return Err(
            "Host destruction, shutdown and boot modification are permanently disabled.".into(),
        );
    }
    let cwd = workspace_path(root, cwd)?;
    if !cwd.is_dir() {
        return Err("Command working directory must be an existing workspace directory.".into());
    }
    let mut tokens = tokenize(command)?;
    let first = tokens
        .first_mut()
        .ok_or("Command is empty after parsing.")?;
    let alias = match first.text.to_ascii_lowercase().as_str() {
        "dir" | "ls" | "gci" => Some("Get-ChildItem"),
        "cat" | "type" | "gc" => Some("Get-Content"),
        "pwd" | "gl" => Some("Get-Location"),
        _ => None,
    };
    if let Some(alias) = alias {
        first.text = alias.into();
    }
    let powershell = CMDLET.is_match(&first.text) && !Path::new(&first.text).is_absolute();
    if tokens
        .iter()
        .any(|token| token.operator && (!powershell || token.text != "|"))
    {
        return Err("Shell operators are not supported. Run each command separately; only PowerShell cmdlet pipelines are supported.".into());
    }
    if powershell && command.contains(['$', '`', '{', '}']) {
        return Err("PowerShell interpolation and script blocks are disabled. Use a reviewed workspace script.".into());
    }
    for segment in tokens.split(|token| token.operator) {
        validate_segment(segment, root, &cwd)?;
    }
    let argv = if powershell {
        let pipeline = tokens
            .iter()
            .map(|token| {
                if token.operator || token.text.starts_with('-') || CMDLET.is_match(&token.text) {
                    token.text.clone()
                } else {
                    format!("'{}'", token.text.replace('\'', "''"))
                }
            })
            .collect::<Vec<_>>()
            .join(" ");
        vec![
            if cfg!(windows) {
                "powershell.exe"
            } else {
                "pwsh"
            }
            .into(),
            "-NoProfile".into(),
            "-NonInteractive".into(),
            "-Command".into(),
            format!(
                "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; {pipeline}"
            ),
        ]
    } else {
        tokens.into_iter().map(|token| token.text).collect()
    };
    Ok(Invocation {
        argv,
        executor: if powershell {
            "powershell"
        } else {
            "subprocess"
        },
        cwd,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn commands_preserve_literal_operators_and_reject_execution_bypasses() {
        let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../target/command-policy-tests");
        fs::create_dir_all(&base).unwrap();
        let directory = tempfile::tempdir_in(base).unwrap();
        let root = directory.path();
        let invocation = prepare("node example.mjs \"literal && text\" \"&&\"", root, ".").unwrap();
        assert_eq!(&invocation.argv[2..], ["literal && text", "&&"]);
        for command in [
            "node a.mjs && node b.mjs",
            "rm keep.txt",
            "git clean -fd",
            "git --no-pager clean -fd",
            "git --git-dir . clean -fd",
            "node --eval=process.exit()",
            "powershell.exe Remove-Item keep.txt",
            "Invoke-Expression 'rm keep.txt'",
            "node -e 'process.exit()'",
            "rg ../outside",
            "node --file=../outside",
            "Get-ChildItem . | Remove-Item",
            "Get-Content $(Get-Location)",
        ] {
            assert!(prepare(command, root, ".").is_err(), "{command}");
        }
        fs::write(
            root.join("unsafe.mjs"),
            "import fs from 'node:fs'; fs.unlinkSync('keep.txt');",
        )
        .unwrap();
        assert!(prepare("node unsafe.mjs", root, ".").is_err());
        assert!(prepare("Get-ChildItem . | Select-Object -First 2", root, ".").is_ok());
    }
}
