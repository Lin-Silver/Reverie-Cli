"""
Command Execution Tool - audited workspace command execution with blacklist-based
filesystem protections.

This tool allows normal project-local command execution while blocking terminal
driven file move/delete operations. Destructive deletion must go through the
dedicated `delete_file` tool, which performs explicit workspace checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable, Tuple
import locale
import os
import re
import shlex
import subprocess
import sys
import threading
import time

from ..config import get_project_data_dir
from ..security_utils import WorkspaceSecurityError
from .base import BaseTool, ToolResult


class CommandExecTool(BaseTool):
    """
    Tool for executing audited workspace commands.

    The active workspace remains the only allowed working directory. Terminal
    commands are broadly available, but move/delete operations are blocked and
    must go through dedicated workspace-aware tools.
    """

    name = "command_exec"
    aliases = ("shell", "terminal", "run_command")
    search_hint = "run builds tests git and workspace commands"
    tool_category = "workspace"
    tool_tags = ("command", "shell", "terminal", "build", "test", "git", "verify")

    description = """Execute audited commands inside the active workspace.

Security rules:
- Working directory must stay inside the active workspace
- Custom environment overrides are disabled
- Terminal move/delete/rename commands are blocked
- Inline scripts and script files are scanned for file move/delete APIs
- Use `delete_file` for file deletion instead of terminal commands
- Every attempt is logged to the current project cache audit log

Examples:
- Git status: {"command": "git status"}
- Python inline script: {"command": "python -c \\"print(1); print(2)\\""}
- .NET solution creation: {"command": "dotnet new sln -n Demo"}
- Search text: {"command": "rg TODO reverie"}
- PowerShell pipeline: {"command": "Get-ChildItem reverie -Recurse | Select-Object -First 20"}
- PowerShell cmdlet search: {"command": "Select-String -Path reverie\\\\*.py -Pattern \\"TODO\\""}"""

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command line to execute inside the active workspace"
            },
            "cwd": {
                "type": "string",
                "description": "Workspace-relative working directory (default: project root)"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120)",
                "default": 120
            },
            "env": {
                "type": "object",
                "description": "Disabled in secure mode; custom environment overrides are blocked"
            }
        },
        "required": ["command"]
    }

    DIRECTLY_BLOCKED_EXECUTABLES = {
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
    }

    BLOCKED_SUBCOMMANDS = {
        ("git", "rm"): "git rm deletes tracked files and is disabled.",
        ("git", "mv"): "git mv moves files and is disabled.",
        ("git", "clean"): "git clean deletes files and is disabled.",
    }

    BLOCKED_FLAGS = {
        "robocopy": {"/mov", "/move"},
        "xcopy": {"/move"},
        "rsync": {"--remove-source-files"},
        "tar": {"--remove-files"},
    }

    POWERSHELL_ALIASES = {
        "dir": "Get-ChildItem",
        "ls": "Get-ChildItem",
        "gci": "Get-ChildItem",
        "cat": "Get-Content",
        "type": "Get-Content",
        "gc": "Get-Content",
        "pwd": "Get-Location",
        "gl": "Get-Location",
    }

    POWERSHELL_WRAPPED_COMMANDS = {"Get-ChildItem", "Get-Content", "Get-Location"}
    POWERSHELL_META_TOKENS = {"|", ";", "&&", "||", ">", ">>", "<", "2>", "2>>", "*>", "*>>"}
    POWERSHELL_CMDLET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[A-Za-z][A-Za-z0-9-]*$")

    PYTHON_EXECUTABLES = {"python", "python.exe", "py"}
    NODE_EXECUTABLES = {"node", "node.exe"}
    POWERSHELL_EXECUTABLES = {"powershell", "powershell.exe", "pwsh"}
    CMD_EXECUTABLES = {"cmd", "cmd.exe"}
    SHELL_EXECUTABLES = {"bash", "sh", "zsh"}
    DOTNET_EXECUTABLES = {"dotnet", "dotnet.exe"}
    INLINE_SCRIPT_FLAGS = {"-c", "-command", "--command", "-e", "--eval", "/c", "/k"}
    OPAQUE_SCRIPT_FLAGS = {"-enc", "-encodedcommand"}

    PYTHON_BLOCK_PATTERNS = (
        (re.compile(r"\bos\.(?:remove|unlink|rename|replace)\s*\(", re.IGNORECASE), "Python os file move/delete API"),
        (re.compile(r"\bshutil\.(?:move|rmtree)\s*\(", re.IGNORECASE), "Python shutil file move/delete API"),
        (
            re.compile(
                r"\b(?:pathlib\.)?Path\s*\([^)]*\)\s*\.\s*(?:unlink|rename|replace)\s*\(",
                re.IGNORECASE,
            ),
            "pathlib file move/delete API",
        ),
        (
            re.compile(
                r"\bSystem\.IO\.(?:File|Directory)\.(?:Delete|Move)\s*\(",
                re.IGNORECASE,
            ),
            ".NET file move/delete API",
        ),
    )

    NODE_BLOCK_PATTERNS = (
        (
            re.compile(
                r"\bfs(?:\.promises)?\.(?:rm|rmdir|unlink|rename)\s*\(",
                re.IGNORECASE,
            ),
            "Node fs file move/delete API",
        ),
        (
            re.compile(
                r"\b(?:rmSync|rmdirSync|unlinkSync|renameSync)\s*\(",
                re.IGNORECASE,
            ),
            "Node fs sync file move/delete API",
        ),
    )

    SHELL_BLOCK_PATTERNS = (
        (
            re.compile(
                r"(?i)(?:^|[;&|]\s*|&&\s*|\|\|\s*)(?:rm|mv|rmdir|unlink|del|erase|move|ren|rename|rd|remove-item|move-item|rename-item)\b"
            ),
            "shell move/delete command",
        ),
        (
            re.compile(
                r"(?i)(?:^|[;&|]\s*|&&\s*|\|\|\s*)git\s+(?:rm|mv|clean)\b"
            ),
            "git file move/delete command",
        ),
    )

    def get_execution_message(self, **kwargs) -> str:
        command = kwargs.get("command", "unknown command")
        return f"Executing workspace command: {command}"

    def execute(self, **kwargs) -> ToolResult:
        command = str(kwargs.get("command", "") or "").strip()
        cwd = kwargs.get("cwd")
        timeout = kwargs.get("timeout", 120)
        extra_env = kwargs.get("env", {})

        if not command:
            return ToolResult.fail("Command is required")

        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            return ToolResult.fail("timeout must be an integer")
        if timeout <= 0:
            return ToolResult.fail("timeout must be a positive integer")

        if extra_env:
            return self._blocked_result(
                command=command,
                cwd_value=str(cwd or ""),
                reason="Custom environment overrides are disabled in secure command mode.",
            )

        try:
            work_dir = self.resolve_workspace_path(cwd or ".", purpose="set command working directory")
        except Exception as exc:
            return self._blocked_result(
                command=command,
                cwd_value=str(cwd or ""),
                reason=str(exc),
            )

        if not work_dir.exists():
            return ToolResult.fail(f"Working directory not found: {work_dir}")
        if not work_dir.is_dir():
            return ToolResult.fail(f"Working directory is not a directory: {work_dir}")

        try:
            invocation = self._build_invocation(command, work_dir)
        except (WorkspaceSecurityError, ValueError) as exc:
            return self._blocked_result(
                command=command,
                cwd_value=str(work_dir),
                reason=str(exc),
            )

        start_time = time.monotonic()
        try:
            encoding = locale.getpreferredencoding(False) or "utf-8"
            process = subprocess.Popen(
                invocation["argv"],
                cwd=str(work_dir),
                env=self._build_process_env(invocation),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=encoding,
                errors="replace",
                bufsize=1,
            )

            stdout_lines: List[str] = []
            stderr_lines: List[str] = []
            stdout_thread = threading.Thread(
                target=self._collect_stream_lines,
                args=(process.stdout, stdout_lines),
                kwargs={"stream_name": "stdout", "emit_callback": self._emit_tool_progress},
                daemon=True,
                name="reverie-command-stdout",
            )
            stderr_thread = threading.Thread(
                target=self._collect_stream_lines,
                args=(process.stderr, stderr_lines),
                kwargs={"stream_name": "stderr", "emit_callback": self._emit_tool_progress},
                daemon=True,
                name="reverie-command-stderr",
            )
            stdout_thread.start()
            stderr_thread.start()
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_thread.join(timeout=0.5)
                stderr_thread.join(timeout=0.5)
                raise

            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)
            stdout = self._truncate_output("".join(stdout_lines))
            stderr = self._truncate_output("".join(stderr_lines))
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.audit_command_event(
                {
                    "event": "command_timeout",
                    "allowed": True,
                    "command": command,
                    "normalized_command": invocation["display"],
                    "executor": invocation["executor"],
                    "policy": invocation["policy"],
                    "cwd": str(work_dir),
                    "timeout_seconds": timeout,
                    "duration_ms": duration_ms,
                }
            )
            return ToolResult.fail(f"Command timed out after {timeout} seconds.")
        except FileNotFoundError:
            return ToolResult.fail(
                f"Command executable not found: {invocation['argv'][0] if invocation['argv'] else 'unknown'}"
            )
        except Exception as exc:
            return ToolResult.fail(f"Error executing command: {str(exc)}")

        duration_ms = int((time.monotonic() - start_time) * 1000)

        self.audit_command_event(
            {
                "event": "command_result",
                "allowed": True,
                "command": command,
                "normalized_command": invocation["display"],
                "executor": invocation["executor"],
                "policy": invocation["policy"],
                "cwd": str(work_dir),
                "timeout_seconds": timeout,
                "duration_ms": duration_ms,
                "exit_code": returncode,
            }
        )

        output_parts = [
            f"$ {command}",
            f"Working directory: {work_dir}",
            f"Executor: {invocation['executor']}",
            f"Policy: {invocation['policy']}",
            f"Exit code: {returncode}",
            f"Duration: {duration_ms}ms",
        ]
        if stdout:
            output_parts.extend(["", "--- STDOUT ---", stdout])
        if stderr:
            output_parts.extend(["", "--- STDERR ---", stderr])

        joined_output = "\n".join(output_parts)
        if returncode == 0:
            return ToolResult.ok(
                joined_output,
                data={
                    "exit_code": returncode,
                    "success": True,
                    "duration_ms": duration_ms,
                },
            )
        return ToolResult.partial(joined_output, f"Command exited with code {returncode}")

    def _emit_tool_progress(self, *, stream: str, text: str) -> None:
        """Forward incremental command output to the live TUI when available."""
        handler = self.context.get("ui_event_handler") if self.context else None
        chunk = str(text or "")
        if not callable(handler) or not chunk:
            return

        payload = {
            "kind": "tool_progress",
            "tool_call_id": str(self.context.get("active_tool_call_id", "") or ""),
            "tool_name": str(self.context.get("active_tool_name", self.name) or self.name),
            "stream": str(stream or "stdout").strip().lower() or "stdout",
            "text": chunk,
        }
        try:
            handler(payload)
        except Exception:
            pass

    @classmethod
    def _collect_stream_lines(
        cls,
        pipe: Any,
        sink: List[str],
        *,
        stream_name: str,
        emit_callback: Optional[Any] = None,
    ) -> None:
        """Read one subprocess pipe line-by-line without blocking the other stream."""
        if pipe is None:
            return
        try:
            for line in iter(pipe.readline, ""):
                if not line:
                    break
                sink.append(line)
                if callable(emit_callback):
                    emit_callback(stream=stream_name, text=line)
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _build_invocation(self, command: str, work_dir: Path) -> Dict[str, Any]:
        tokens = self._tokenize(command)
        if not tokens:
            raise ValueError("Command is empty after parsing.")

        tokens = self._normalize_alias(tokens)
        executable = tokens[0]
        executable_lower = executable.lower()

        self._validate_command(tokens, command, work_dir)
        self._validate_argument_tokens(tokens, work_dir)

        if self._should_use_powershell_invocation(executable):
            return self._build_powershell_invocation(tokens, original_command=command)

        env_overrides = self._build_dotnet_sandbox_env() if executable_lower in self.DOTNET_EXECUTABLES else {}
        return {
            "argv": tokens,
            "executor": "subprocess",
            "display": " ".join(tokens),
            "policy": "workspace_blacklist",
            "env_overrides": env_overrides,
        }

    def _validate_command(self, tokens: List[str], command: str, work_dir: Path) -> None:
        executable_lower = tokens[0].lower()

        if executable_lower in self.DIRECTLY_BLOCKED_EXECUTABLES:
            raise ValueError(
                f"Blocked command '{tokens[0]}': terminal move/delete operations are disabled. "
                "Use delete_file for deletions."
            )

        if len(tokens) >= 2:
            reason = self.BLOCKED_SUBCOMMANDS.get((executable_lower, tokens[1].lower()))
            if reason:
                raise ValueError(f"Blocked command '{command}': {reason} Use delete_file for deletions.")

        blocked_flags = self.BLOCKED_FLAGS.get(executable_lower, set())
        for token in tokens[1:]:
            lowered = token.lower()
            if lowered in blocked_flags:
                raise ValueError(
                    f"Blocked command '{command}': flag '{token}' triggers terminal move/delete behavior."
                )

        for token in tokens[1:]:
            if token.lower() in self.OPAQUE_SCRIPT_FLAGS:
                raise ValueError(
                    f"Blocked command '{command}': opaque script flag '{token}' cannot be audited for move/delete safety."
                )

        for runtime, script_text in self._extract_inline_scripts(tokens):
            self._scan_script_text(script_text, runtime=runtime, command=command)

        for runtime, script_path in self._extract_script_files(tokens, work_dir):
            self._scan_script_file(script_path, runtime=runtime, command=command)

    def _validate_argument_tokens(self, tokens: List[str], work_dir: Path) -> None:
        if not tokens:
            return

        executable_lower = tokens[0].lower()
        skip_indices = self._build_skip_indices(tokens, executable_lower)

        for index, token in enumerate(tokens[1:], start=1):
            if index in skip_indices:
                continue
            self._validate_token(token, command_name=tokens[0], work_dir=work_dir)

    def _build_skip_indices(self, tokens: List[str], executable_lower: str) -> set[int]:
        skip_indices: set[int] = set()

        for index, token in enumerate(tokens[1:], start=1):
            lowered = token.lower()
            if lowered not in self.INLINE_SCRIPT_FLAGS:
                continue

            if executable_lower in self.POWERSHELL_EXECUTABLES | self.CMD_EXECUTABLES | self.SHELL_EXECUTABLES:
                skip_indices.update(range(index + 1, len(tokens)))
                break

            if index + 1 < len(tokens):
                skip_indices.add(index + 1)

        return skip_indices

    def _extract_inline_scripts(self, tokens: List[str]) -> List[Tuple[str, str]]:
        if not tokens:
            return []

        executable_lower = tokens[0].lower()
        scripts: List[Tuple[str, str]] = []

        for index, token in enumerate(tokens[1:], start=1):
            lowered = token.lower()
            if lowered not in self.INLINE_SCRIPT_FLAGS:
                continue

            if executable_lower in self.POWERSHELL_EXECUTABLES | self.CMD_EXECUTABLES | self.SHELL_EXECUTABLES:
                script_text = " ".join(tokens[index + 1:]).strip()
                if script_text:
                    scripts.append((self._runtime_for_executable(executable_lower), script_text))
                break

            if index + 1 < len(tokens):
                script_text = str(tokens[index + 1] or "").strip()
                if script_text:
                    scripts.append((self._runtime_for_executable(executable_lower), script_text))

        return scripts

    def _extract_script_files(self, tokens: List[str], work_dir: Path) -> List[Tuple[str, Path]]:
        if not tokens:
            return []

        executable_lower = tokens[0].lower()
        runtime = self._runtime_for_executable(executable_lower)
        script_path = self._detect_script_path(tokens, executable_lower)
        if not script_path:
            return []

        resolved = self._resolve_path_like_token(script_path, command_name=tokens[0], work_dir=work_dir)
        if not resolved.exists() or resolved.is_dir():
            return []
        return [(runtime, resolved)]

    def _detect_script_path(self, tokens: List[str], executable_lower: str) -> Optional[str]:
        if not tokens:
            return None

        executable_token = tokens[0]
        if self._looks_like_script_file(executable_token):
            return executable_token

        if executable_lower in self.PYTHON_EXECUTABLES | self.NODE_EXECUTABLES | self.SHELL_EXECUTABLES:
            for token in tokens[1:]:
                lowered = token.lower()
                if lowered in self.INLINE_SCRIPT_FLAGS or lowered in self.OPAQUE_SCRIPT_FLAGS:
                    return None
                if lowered == "-m":
                    return None
                if self._is_option_token(token):
                    continue
                return token
            return None

        if executable_lower in self.POWERSHELL_EXECUTABLES:
            for index, token in enumerate(tokens[1:], start=1):
                lowered = token.lower()
                if lowered in self.INLINE_SCRIPT_FLAGS or lowered in self.OPAQUE_SCRIPT_FLAGS:
                    return None
                if lowered in {"-file", "-f"} and index + 1 < len(tokens):
                    return tokens[index + 1]
            return None

        if executable_lower in self.CMD_EXECUTABLES:
            for index, token in enumerate(tokens[1:], start=1):
                lowered = token.lower()
                if lowered not in {"/c", "/k"}:
                    continue
                if index + 1 >= len(tokens):
                    return None
                candidate = tokens[index + 1]
                return candidate if self._looks_like_script_file(candidate) else None
            return None

        return None

    def _scan_script_file(self, script_path: Path, *, runtime: str, command: str) -> None:
        try:
            content = script_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = script_path.read_text(encoding="latin-1")
        except Exception as exc:
            raise ValueError(f"Blocked command '{command}': failed to inspect script '{script_path}': {exc}") from exc

        self._scan_script_text(content, runtime=runtime, command=command, script_path=script_path)

    def _scan_script_text(
        self,
        script_text: str,
        *,
        runtime: str,
        command: str,
        script_path: Optional[Path] = None,
    ) -> None:
        for pattern, reason in self._patterns_for_runtime(runtime):
            if pattern.search(script_text):
                location = f" in script '{script_path.name}'" if script_path else ""
                raise ValueError(
                    f"Blocked command '{command}': {reason}{location}. "
                    "Terminal move/delete flows are disabled; use delete_file for deletions."
                )

    def _patterns_for_runtime(self, runtime: str) -> Iterable[Tuple[re.Pattern[str], str]]:
        if runtime == "python":
            return self.PYTHON_BLOCK_PATTERNS
        if runtime == "node":
            return self.NODE_BLOCK_PATTERNS
        if runtime in {"powershell", "cmd", "shell"}:
            return self.SHELL_BLOCK_PATTERNS
        return ()

    def _should_use_powershell_invocation(self, executable: str) -> bool:
        if executable in self.POWERSHELL_WRAPPED_COMMANDS:
            return True
        return self._is_powershell_cmdlet(executable)

    def _build_powershell_invocation(self, tokens: List[str], *, original_command: str) -> Dict[str, Any]:
        ps_command = (
            str(original_command or "").strip()
            if self._requires_raw_powershell_command(tokens, original_command)
            else " ".join(self._quote_powershell_token(token) for token in tokens)
        )
        executable = "powershell.exe" if sys.platform == "win32" else "pwsh"
        return {
            "argv": [executable, "-NoProfile", "-Command", ps_command],
            "executor": "powershell",
            "display": ps_command,
            "policy": "workspace_blacklist",
            "env_overrides": {},
        }

    def _build_dotnet_sandbox_env(self) -> Dict[str, str]:
        workspace_root = self.get_project_root()
        sandbox_root = get_project_data_dir(workspace_root) / "runtime_sandbox" / "dotnet"
        home_dir = sandbox_root / "home"
        temp_dir = sandbox_root / "tmp"
        appdata_dir = sandbox_root / "appdata"
        localappdata_dir = sandbox_root / "localappdata"
        xdg_cache_dir = sandbox_root / "xdg" / "cache"
        xdg_config_dir = sandbox_root / "xdg" / "config"
        xdg_data_dir = sandbox_root / "xdg" / "data"
        nuget_root = sandbox_root / "nuget"
        packages_dir = nuget_root / "packages"
        http_cache_dir = nuget_root / "http-cache"
        scratch_dir = nuget_root / "scratch"

        for path in (
            home_dir,
            temp_dir,
            appdata_dir,
            localappdata_dir,
            xdg_cache_dir,
            xdg_config_dir,
            xdg_data_dir,
            packages_dir,
            http_cache_dir,
            scratch_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

        return {
            "DOTNET_CLI_HOME": str(home_dir),
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1",
            "DOTNET_ADD_GLOBAL_TOOLS_TO_PATH": "0",
            "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false",
            "NUGET_PACKAGES": str(packages_dir),
            "NUGET_HTTP_CACHE_PATH": str(http_cache_dir),
            "NUGET_SCRATCH": str(scratch_dir),
            "TMP": str(temp_dir),
            "TEMP": str(temp_dir),
            "HOME": str(home_dir),
            "USERPROFILE": str(home_dir),
            "APPDATA": str(appdata_dir),
            "LOCALAPPDATA": str(localappdata_dir),
            "XDG_CACHE_HOME": str(xdg_cache_dir),
            "XDG_CONFIG_HOME": str(xdg_config_dir),
            "XDG_DATA_HOME": str(xdg_data_dir),
            "MSBUILDDISABLENODEREUSE": "1",
        }

    def _validate_token(self, token: str, *, command_name: str, work_dir: Path) -> None:
        text = str(token or "").strip()
        if not text:
            return

        if self._is_absolute_path_token(text):
            self._validate_workspace_path_token(text, command_name=command_name, work_dir=work_dir)
            return

        if self._is_option_token(text):
            return

        if self._has_parent_traversal(text):
            raise ValueError(
                f"Blocked {command_name} argument '{text}': parent-directory traversal is not allowed."
            )

        if self._looks_like_path_token(text):
            self._validate_workspace_path_token(text, command_name=command_name, work_dir=work_dir)

    def _resolve_path_like_token(self, token: str, *, command_name: str, work_dir: Path) -> Path:
        text = str(token or "").strip()
        if not text:
            raise ValueError(f"Blocked {command_name} argument: path is required.")
        if self._has_parent_traversal(text):
            raise ValueError(
                f"Blocked {command_name} argument '{text}': parent-directory traversal is not allowed."
            )
        expanded = os.path.expandvars(text)
        candidate = Path(expanded).expanduser()
        if not candidate.is_absolute():
            candidate = work_dir / candidate
        try:
            return self.ensure_workspace_path(candidate, purpose=f"validate {command_name} path")
        except WorkspaceSecurityError as exc:
            raise ValueError(str(exc)) from exc

    def _validate_workspace_path_token(self, token: str, *, command_name: str, work_dir: Path) -> None:
        self._resolve_path_like_token(token, command_name=command_name, work_dir=work_dir)

    def _tokenize(self, command: str) -> List[str]:
        tokens = shlex.split(command, posix=(sys.platform != "win32"))
        normalized: List[str] = []
        for token in tokens:
            text = str(token or "")
            if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
                text = text[1:-1]
            normalized.append(text)
        return normalized

    def _normalize_alias(self, tokens: List[str]) -> List[str]:
        if not tokens:
            return tokens
        alias = self.POWERSHELL_ALIASES.get(tokens[0].lower())
        if not alias:
            return tokens
        return [alias, *tokens[1:]]

    def _requires_raw_powershell_command(self, tokens: List[str], command: str) -> bool:
        if any(token in self.POWERSHELL_META_TOKENS for token in tokens):
            return True
        command_text = str(command or "")
        return any(marker in command_text for marker in ("|", ";", "&&", "||", ">", "<"))

    def _is_powershell_cmdlet(self, token: str) -> bool:
        text = str(token or "").strip()
        if not text or self._looks_like_script_file(text) or self._is_absolute_path_token(text):
            return False
        return bool(self.POWERSHELL_CMDLET_RE.match(text))

    @staticmethod
    def _quote_powershell_token(token: str) -> str:
        if token and all(ch.isalnum() or ch in "._-/:\\" for ch in token):
            return token
        return "'" + token.replace("'", "''") + "'"

    @staticmethod
    def _runtime_for_executable(executable_lower: str) -> str:
        if executable_lower in CommandExecTool.PYTHON_EXECUTABLES:
            return "python"
        if executable_lower in CommandExecTool.NODE_EXECUTABLES:
            return "node"
        if executable_lower in CommandExecTool.POWERSHELL_EXECUTABLES:
            return "powershell"
        if executable_lower in CommandExecTool.CMD_EXECUTABLES:
            return "cmd"
        if executable_lower in CommandExecTool.SHELL_EXECUTABLES:
            return "shell"
        return "generic"

    @staticmethod
    def _looks_like_script_file(token: str) -> bool:
        text = str(token or "").strip().lower()
        return text.endswith((".py", ".ps1", ".cmd", ".bat", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs"))

    @staticmethod
    def _is_option_token(token: str) -> bool:
        if not token:
            return False
        if token == "--":
            return False
        if token.startswith("-"):
            return True
        if sys.platform == "win32" and token.startswith("/"):
            return "/" not in token[1:] and "\\" not in token[1:]
        return False

    @staticmethod
    def _has_parent_traversal(token: str) -> bool:
        normalized = token.replace("\\", "/")
        return (
            normalized == ".."
            or normalized.startswith("../")
            or normalized.startswith("..\\")
            or "/../" in normalized
            or normalized.endswith("/..")
        )

    @staticmethod
    def _is_absolute_path_token(token: str) -> bool:
        expanded = os.path.expandvars(token)
        if expanded.startswith("~"):
            return True
        if expanded.startswith(("\\\\", "//", "\\")):
            return True
        if expanded.startswith("/"):
            if sys.platform != "win32":
                return True
            return "/" in expanded[1:] or "\\" in expanded[1:]
        return len(expanded) >= 3 and expanded[1] == ":" and expanded[0].isalpha() and expanded[2] in ("\\", "/")

    @staticmethod
    def _looks_like_path_token(token: str) -> bool:
        text = str(token or "").strip()
        lowered = text.lower()
        if not text or "://" in lowered:
            return False
        if text.startswith((".", "~")):
            return True
        if "/" in text or "\\" in text:
            return True
        return lowered.endswith(
            (
                ".sln",
                ".csproj",
                ".fsproj",
                ".vbproj",
                ".props",
                ".targets",
                ".json",
                ".config",
                ".py",
                ".ps1",
                ".cmd",
                ".bat",
                ".sh",
                ".js",
                ".ts",
                ".zip",
            )
        )

    @staticmethod
    def _build_process_env(invocation: Dict[str, Any]) -> Dict[str, str]:
        env = os.environ.copy()
        env.update(invocation.get("env_overrides", {}) or {})
        return env

    @staticmethod
    def _truncate_output(text: str, limit: int = 50_000) -> str:
        raw = str(text or "")
        if len(raw) <= limit:
            return raw
        return raw[:limit] + f"\n...[truncated {len(raw) - limit} characters]"

    @staticmethod
    def _decode_capture_bytes(data: bytes) -> str:
        encoding = locale.getpreferredencoding(False) or "utf-8"
        try:
            return data.decode(encoding, errors="replace")
        except LookupError:
            return data.decode("utf-8", errors="replace")

    @classmethod
    def _read_truncated_capture(cls, handle: Any, limit: int = 50_000) -> str:
        handle.flush()
        handle.seek(0, os.SEEK_END)
        byte_count = int(handle.tell() or 0)
        handle.seek(0)
        data = handle.read(limit + 1)

        if isinstance(data, str):
            return cls._truncate_output(data, limit=limit)

        preview = cls._decode_capture_bytes(bytes(data[:limit]))
        if byte_count <= limit:
            return preview
        return preview + f"\n...[truncated {max(byte_count - limit, 0)} bytes]"

    def _blocked_result(self, *, command: str, cwd_value: str, reason: str) -> ToolResult:
        self.audit_command_event(
            {
                "event": "command_blocked",
                "allowed": False,
                "command": command,
                "cwd": cwd_value,
                "reason": reason,
            }
        )
        return ToolResult.fail(reason)
