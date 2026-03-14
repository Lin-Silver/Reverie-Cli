"""
Command Execution Tool - audited, workspace-bound diagnostic commands only.

This tool no longer exposes arbitrary shell execution. It is intentionally
restricted to a small set of read-only commands that stay inside the active
workspace and are logged to `.reverie/security/command_audit.jsonl`.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from pathlib import Path
import os
import shlex
import subprocess
import sys
import time

from ..security_utils import WorkspaceSecurityError
from .base import BaseTool, ToolResult


class CommandExecTool(BaseTool):
    """
    Tool for executing audited read-only workspace commands.

    The security goal here is strict: the AI must not be able to use shell
    access to modify or reach outside the active Reverie workspace.
    """

    name = "command_exec"

    description = """Execute audited read-only commands inside the active workspace.

Security restrictions:
- Only a small set of diagnostic commands is allowed
- Working directory must stay inside the active workspace
- Absolute paths and `..` traversal are blocked
- Custom environment overrides are disabled
- Every attempt is logged to `.reverie/security/command_audit.jsonl`

Allowed examples:
- Git status: {"command": "git status"}
- Search text: {"command": "rg TODO reverie"}
- List files: {"command": "dir reverie"}
- Read a file: {"command": "type README.md"}"""

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "A read-only diagnostic command to execute"
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
            invocation = self._build_invocation(command)
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
                env=os.environ.copy(),
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

    def _build_invocation(self, command: str) -> Dict[str, Any]:
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

        if executable_lower == "git":
            return self._build_git_invocation(tokens)

        if executable in self.POWERSHELL_READONLY_COMMANDS:
            return self._build_powershell_invocation(tokens)

        if executable_lower in self.ALLOWED_EXTERNAL_COMMANDS:
            self._validate_generic_tokens(tokens[1:], command_name=executable)
            if executable_lower == "rg":
                self._validate_rg_tokens(tokens[1:])
            return {
                "argv": tokens,
                "executor": "subprocess",
                "display": " ".join(tokens),
            }

        raise ValueError(
            f"Blocked command '{executable}': only audited read-only workspace commands are allowed."
        )

    def _build_git_invocation(self, tokens: List[str]) -> Dict[str, Any]:
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

        self._validate_generic_tokens(tokens[2:], command_name="git")
        return {
            "argv": tokens,
            "executor": "subprocess",
            "display": " ".join(tokens),
        }

    def _build_powershell_invocation(self, tokens: List[str]) -> Dict[str, Any]:
        self._validate_generic_tokens(tokens[1:], command_name=tokens[0])
        ps_command = " ".join(self._quote_powershell_token(token) for token in tokens)
        executable = "powershell.exe" if sys.platform == "win32" else "pwsh"
        return {
            "argv": [executable, "-NoProfile", "-Command", ps_command],
            "executor": "powershell",
            "display": ps_command,
        }

    def _validate_command_text(self, command: str) -> None:
        for blocked in self.BLOCKED_SUBSTRINGS:
            if blocked in command:
                raise ValueError(
                    f"Blocked command: shell control operator '{blocked}' is not allowed in secure mode."
                )

    def _validate_generic_tokens(self, tokens: List[str], command_name: str) -> None:
        for token in tokens:
            self._validate_token(token, command_name=command_name)

    def _validate_rg_tokens(self, tokens: List[str]) -> None:
        for token in tokens:
            lowered = token.lower()
            if lowered in self.BLOCKED_RG_FLAGS or any(lowered.startswith(flag + "=") for flag in self.BLOCKED_RG_FLAGS):
                raise ValueError(f"Blocked rg flag '{token}': command pre-processors are disabled.")

    def _validate_token(self, token: str, *, command_name: str) -> None:
        text = str(token or "").strip()
        if not text:
            return

        if self._is_absolute_path_token(text):
            resolved = self.resolve_workspace_path(text, purpose=f"validate {command_name} path")
            self.ensure_workspace_path(resolved, purpose=f"validate {command_name} path")
            return

        if self._is_option_token(text):
            return

        if self._has_parent_traversal(text):
            raise ValueError(
                f"Blocked {command_name} argument '{text}': parent-directory traversal is not allowed."
            )

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
