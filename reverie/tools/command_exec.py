"""
Command Execution Tool - audited, workspace-bound command execution.

This tool intentionally exposes only a very small set of trusted command
profiles that stay inside the active workspace and are logged to
`.reverie/security/command_audit.jsonl`.

Most allowed commands are read-only diagnostics. A small curated subset of
`dotnet` scaffolding and solution-management flows is also allowed, but only
inside a workspace-local runtime sandbox.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List
import os
import shlex
import subprocess
import sys
import time

from ..security_utils import WorkspaceSecurityError
from .base import BaseTool, ToolResult


class CommandExecTool(BaseTool):
    """
    Tool for executing audited workspace commands.

    The security goal here is strict: the AI must not be able to use command
    execution to modify or reach outside the active Reverie workspace.
    """

    name = "command_exec"

    description = """Execute audited workspace commands inside the active workspace.

Security restrictions:
- Only a small audited command set is allowed
- Working directory must stay inside the active workspace
- Absolute paths and `..` traversal are blocked
- Custom environment overrides are disabled
- `dotnet` is limited to workspace-local scaffolding and solution/project management
- Every attempt is logged to `.reverie/security/command_audit.jsonl`

Allowed examples:
- Git status: {"command": "git status"}
- Search text: {"command": "rg TODO reverie"}
- List files: {"command": "dir reverie"}
- Read a file: {"command": "type README.md"}
- Create a .NET solution in-workspace: {"command": "dotnet new sln -n Demo"}"""

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "An audited workspace command to execute"
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

    BLOCKED_SUBSTRINGS = (
        "&&",
        "||",
        "|",
        ";",
        ">",
        "<",
        "`",
        "\n",
        "\r",
    )
    LEGACY_DANGEROUS_PATTERNS = (
        "rm -rf",
        "rm -r",
        "rmdir",
        "del /s",
        "rd /s",
        "format",
        "mkfs",
        "dd if=",
        "curl | sh",
        "wget | sh",
        ":(){:|:&};:",
    )
    BLOCKED_EXECUTABLES = {
        "powershell",
        "powershell.exe",
        "pwsh",
        "cmd",
        "cmd.exe",
        "python",
        "python.exe",
        "py",
        "node",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "pip",
        "pip3",
        "uv",
        "bash",
        "sh",
        "curl",
        "wget",
        "scp",
        "robocopy",
        "xcopy",
        "copy",
        "move",
        "ren",
        "rename",
        "del",
        "erase",
        "remove-item",
        "move-item",
        "copy-item",
        "new-item",
        "set-content",
        "add-content",
        "out-file",
    }
    ALLOWED_GIT_SUBCOMMANDS = {
        "status",
        "diff",
        "log",
        "show",
        "branch",
        "rev-parse",
        "ls-files",
        "remote",
        "grep",
    }
    BLOCKED_GIT_FLAGS = {
        "-c",
        "-C",
        "--git-dir",
        "--work-tree",
        "--file",
        "--global",
        "--system",
        "--local",
        "--no-index",
        "--output",
    }
    ALLOWED_EXTERNAL_COMMANDS = {"rg", "findstr", "tree", "where"}
    BLOCKED_RG_FLAGS = {"--pre", "--pre-glob"}
    ALLOWED_DOTNET_EXECUTABLES = {"dotnet", "dotnet.exe"}
    ALLOWED_DOTNET_TOPLEVEL_COMMANDS = {"new", "sln", "add", "remove", "list"}
    BLOCKED_DOTNET_TOPLEVEL_COMMANDS = {
        "build",
        "clean",
        "dev-certs",
        "format",
        "msbuild",
        "nuget",
        "pack",
        "publish",
        "restore",
        "run",
        "test",
        "tool",
        "vstest",
        "workload",
    }
    BLOCKED_DOTNET_NEW_ACTIONS = {"install", "uninstall", "update", "search"}
    BLOCKED_DOTNET_FLAGS = {"-g", "--global", "--tool-path", "--install", "--uninstall", "--update-check"}
    DOTNET_REQUIRED_PATH_FLAGS = {
        "-o",
        "--output",
        "--project",
        "--solution",
        "--file",
        "--manifest",
        "--packages",
        "--package-directory",
        "--results-directory",
        "--artifacts-path",
        "--configfile",
    }
    DOTNET_OPTIONAL_PATH_FLAGS = {"--source", "--add-source"}
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
    POWERSHELL_READONLY_COMMANDS = {"Get-ChildItem", "Get-Content", "Get-Location"}

    def get_execution_message(self, **kwargs) -> str:
        command = kwargs.get("command", "unknown command")
        return f"Executing audited workspace command: {command}"

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

        for pattern in self.LEGACY_DANGEROUS_PATTERNS:
            if pattern in command.lower():
                return self._blocked_result(
                    command=command,
                    cwd_value=str(work_dir),
                    reason=f"Blocked command pattern: '{pattern}'.",
                )

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
            result = subprocess.run(
                invocation["argv"],
                cwd=str(work_dir),
                env=self._build_process_env(invocation),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
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
        stdout = self._truncate_output(result.stdout)
        stderr = self._truncate_output(result.stderr)

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
                "exit_code": result.returncode,
            }
        )

        output_parts = [
            f"$ {command}",
            f"Working directory: {work_dir}",
            f"Executor: {invocation['executor']}",
            f"Policy: {invocation['policy']}",
            f"Exit code: {result.returncode}",
            f"Duration: {duration_ms}ms",
        ]
        if stdout:
            output_parts.extend(["", "--- STDOUT ---", stdout])
        if stderr:
            output_parts.extend(["", "--- STDERR ---", stderr])

        joined_output = "\n".join(output_parts)
        if result.returncode == 0:
            return ToolResult.ok(
                joined_output,
                data={
                    "exit_code": result.returncode,
                    "success": True,
                    "duration_ms": duration_ms,
                },
            )
        return ToolResult.partial(joined_output, f"Command exited with code {result.returncode}")

    def _build_invocation(self, command: str, work_dir: Path) -> Dict[str, Any]:
        self._validate_command_text(command)
        tokens = self._tokenize(command)
        if not tokens:
            raise ValueError("Command is empty after parsing.")

        tokens = self._normalize_alias(tokens)
        executable = tokens[0]
        executable_lower = executable.lower()

        if executable_lower in self.BLOCKED_EXECUTABLES:
            raise ValueError(
                f"Blocked command '{executable}': arbitrary shells, interpreters, and write-capable tools are disabled."
            )

        if executable_lower in self.ALLOWED_DOTNET_EXECUTABLES:
            return self._build_dotnet_invocation(tokens, work_dir)

        if executable_lower == "git":
            return self._build_git_invocation(tokens, work_dir)

        if executable in self.POWERSHELL_READONLY_COMMANDS:
            return self._build_powershell_invocation(tokens, work_dir)

        if executable_lower in self.ALLOWED_EXTERNAL_COMMANDS:
            self._validate_generic_tokens(tokens[1:], command_name=executable, work_dir=work_dir)
            if executable_lower == "rg":
                self._validate_rg_tokens(tokens[1:])
            return {
                "argv": tokens,
                "executor": "subprocess",
                "display": " ".join(tokens),
                "policy": "readonly",
                "env_overrides": {},
            }

        raise ValueError(
            f"Blocked command '{executable}': only audited workspace commands are allowed."
        )

    def _build_git_invocation(self, tokens: List[str], work_dir: Path) -> Dict[str, Any]:
        if len(tokens) < 2:
            raise ValueError("Blocked git command: a read-only subcommand is required.")

        subcommand = tokens[1].lower()
        if subcommand not in self.ALLOWED_GIT_SUBCOMMANDS:
            raise ValueError(
                f"Blocked git subcommand '{tokens[1]}': only read-only git diagnostics are allowed."
            )

        for token in tokens[2:]:
            lowered = token.lower()
            if lowered in self.BLOCKED_GIT_FLAGS:
                raise ValueError(f"Blocked git flag '{token}': repository/worktree redirection is disabled.")
            if any(lowered.startswith(flag + "=") for flag in self.BLOCKED_GIT_FLAGS):
                raise ValueError(f"Blocked git flag '{token}': repository/worktree redirection is disabled.")

        self._validate_generic_tokens(tokens[2:], command_name="git", work_dir=work_dir)
        return {
            "argv": tokens,
            "executor": "subprocess",
            "display": " ".join(tokens),
            "policy": "readonly",
            "env_overrides": {},
        }

    def _build_powershell_invocation(self, tokens: List[str], work_dir: Path) -> Dict[str, Any]:
        self._validate_generic_tokens(tokens[1:], command_name=tokens[0], work_dir=work_dir)
        ps_command = " ".join(self._quote_powershell_token(token) for token in tokens)
        executable = "powershell.exe" if sys.platform == "win32" else "pwsh"
        return {
            "argv": [executable, "-NoProfile", "-Command", ps_command],
            "executor": "powershell",
            "display": ps_command,
            "policy": "readonly",
            "env_overrides": {},
        }

    def _build_dotnet_invocation(self, tokens: List[str], work_dir: Path) -> Dict[str, Any]:
        if len(tokens) < 2:
            raise ValueError(
                "Blocked dotnet command: a supported workspace-local subcommand is required."
            )

        subcommand = tokens[1].lower()
        if subcommand in self.BLOCKED_DOTNET_TOPLEVEL_COMMANDS:
            raise ValueError(
                f"Blocked dotnet subcommand '{tokens[1]}': build/run/test/publish/global SDK flows are disabled "
                "because they can escape the strict workspace boundary."
            )

        if subcommand not in self.ALLOWED_DOTNET_TOPLEVEL_COMMANDS:
            raise ValueError(
                f"Blocked dotnet subcommand '{tokens[1]}': only workspace-local scaffolding, "
                "solution management, and project reference/package management are allowed."
            )

        self._validate_dotnet_tokens(tokens, work_dir)
        return {
            "argv": tokens,
            "executor": "subprocess",
            "display": " ".join(tokens),
            "policy": "workspace_write",
            "env_overrides": self._build_dotnet_sandbox_env(),
        }

    def _validate_command_text(self, command: str) -> None:
        for blocked in self.BLOCKED_SUBSTRINGS:
            if blocked in command:
                raise ValueError(
                    f"Blocked command: shell control operator '{blocked}' is not allowed in secure mode."
                )

    def _validate_generic_tokens(self, tokens: List[str], command_name: str, work_dir: Path) -> None:
        for token in tokens:
            self._validate_token(token, command_name=command_name, work_dir=work_dir)

    def _validate_rg_tokens(self, tokens: List[str]) -> None:
        for token in tokens:
            lowered = token.lower()
            if lowered in self.BLOCKED_RG_FLAGS or any(lowered.startswith(flag + "=") for flag in self.BLOCKED_RG_FLAGS):
                raise ValueError(f"Blocked rg flag '{token}': command pre-processors are disabled.")

    def _validate_dotnet_tokens(self, tokens: List[str], work_dir: Path) -> None:
        subcommand = tokens[1].lower()
        remaining = tokens[2:]

        if subcommand == "new":
            self._validate_dotnet_new_tokens(remaining)

        pending_flag: Optional[str] = None
        pending_required = False

        for token in remaining:
            lowered = token.lower()

            if pending_flag is not None:
                self._validate_path_value(
                    token,
                    command_name="dotnet",
                    option_name=pending_flag,
                    required=pending_required,
                    work_dir=work_dir,
                )
                pending_flag = None
                pending_required = False
                continue

            if lowered in self.BLOCKED_DOTNET_FLAGS:
                raise ValueError(
                    f"Blocked dotnet flag '{token}': global template/tool state changes are disabled."
                )

            flag_name, attached_value = self._split_option_assignment(token)
            lowered_flag = flag_name.lower()

            if lowered_flag in self.BLOCKED_DOTNET_FLAGS:
                raise ValueError(
                    f"Blocked dotnet flag '{flag_name}': global template/tool state changes are disabled."
                )

            if lowered_flag in self.DOTNET_REQUIRED_PATH_FLAGS:
                if attached_value is not None:
                    self._validate_path_value(
                        attached_value,
                        command_name="dotnet",
                        option_name=flag_name,
                        required=True,
                        work_dir=work_dir,
                    )
                else:
                    pending_flag = flag_name
                    pending_required = True
                continue

            if lowered_flag in self.DOTNET_OPTIONAL_PATH_FLAGS:
                if attached_value is not None:
                    self._validate_path_value(
                        attached_value,
                        command_name="dotnet",
                        option_name=flag_name,
                        required=False,
                        work_dir=work_dir,
                    )
                else:
                    pending_flag = flag_name
                    pending_required = False
                continue

            self._validate_token(token, command_name="dotnet", work_dir=work_dir)

        if pending_flag is not None:
            raise ValueError(
                f"Blocked dotnet command: option '{pending_flag}' requires a workspace-local path value."
            )

    def _validate_dotnet_new_tokens(self, tokens: List[str]) -> None:
        for token in tokens:
            if self._is_option_token(token):
                lowered = token.lower()
                if lowered in self.BLOCKED_DOTNET_FLAGS:
                    raise ValueError(
                        f"Blocked dotnet flag '{token}': global template/tool state changes are disabled."
                    )
                continue

            lowered = token.lower()
            if lowered in self.BLOCKED_DOTNET_NEW_ACTIONS:
                raise ValueError(
                    f"Blocked dotnet new action '{token}': template installation/update flows are disabled."
                )
            return

    def _validate_path_value(
        self,
        value: str,
        *,
        command_name: str,
        option_name: str,
        required: bool,
        work_dir: Path,
    ) -> None:
        text = str(value or "").strip()
        if not text:
            raise ValueError(
                f"Blocked {command_name} option '{option_name}': a path value is required."
            )

        if not required:
            if self._is_url_like(text):
                return
            if not self._looks_like_path_token(text):
                return

        self._validate_workspace_path_token(text, command_name=command_name, work_dir=work_dir)

    def _build_dotnet_sandbox_env(self) -> Dict[str, str]:
        workspace_root = self.get_project_root()
        sandbox_root = workspace_root / ".reverie" / "runtime_sandbox" / "dotnet"
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

    def _validate_workspace_path_token(self, token: str, *, command_name: str, work_dir: Path) -> None:
        text = str(token or "").strip()
        if not text:
            return
        if self._has_parent_traversal(text):
            raise ValueError(
                f"Blocked {command_name} argument '{text}': parent-directory traversal is not allowed."
            )

        expanded = os.path.expandvars(text)
        candidate = Path(expanded).expanduser()
        if not candidate.is_absolute():
            candidate = work_dir / candidate

        try:
            self.ensure_workspace_path(candidate, purpose=f"validate {command_name} path")
        except WorkspaceSecurityError as exc:
            raise ValueError(str(exc)) from exc

    def _tokenize(self, command: str) -> List[str]:
        return shlex.split(command, posix=(sys.platform != "win32"))

    def _normalize_alias(self, tokens: List[str]) -> List[str]:
        if not tokens:
            return tokens
        alias = self.POWERSHELL_ALIASES.get(tokens[0].lower())
        if not alias:
            return tokens
        return [alias, *tokens[1:]]

    @staticmethod
    def _quote_powershell_token(token: str) -> str:
        if token and all(ch.isalnum() or ch in "._-/:\\" for ch in token):
            return token
        return "'" + token.replace("'", "''") + "'"

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
    def _is_url_like(token: str) -> bool:
        text = str(token or "").strip().lower()
        return "://" in text or text.startswith("git@")

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
            )
        )

    @staticmethod
    def _split_option_assignment(token: str) -> tuple[str, Optional[str]]:
        text = str(token or "")
        if not text or not text.startswith("-"):
            return text, None
        if "=" not in text:
            return text, None
        flag_name, value = text.split("=", 1)
        return flag_name, value

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
