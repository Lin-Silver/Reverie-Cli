"""MCP configuration and runtime support for Reverie CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from urllib.parse import urljoin

import requests

from .config import get_app_root
from .security_utils import write_json_secure
from .version import __version__


logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_DEFAULT_TIMEOUT_MS = 600_000
MCP_DEFAULT_DISCOVERY_TIMEOUT_MS = 15_000
MCP_DEFAULT_SSE_ENDPOINT_TIMEOUT_MS = 15_000
MCP_CONFIG_DIRNAME = ".Reverie"
MCP_CONFIG_FILENAME = "MCP.json"
MCP_SESSION_HEADER = "Mcp-Session-Id"
MCP_CLIENT_INFO = {"name": "Reverie CLI", "version": __version__}

_ENV_VAR_PATTERN = re.compile(r"\$(\w+)|\$\{([^}]+)\}|%([^%]+)%")
_SAFE_IDENTIFIER_PATTERN = re.compile(r"[^a-zA-Z0-9_]+")


def default_mcp_config() -> Dict[str, Any]:
    """Return the canonical MCP configuration structure."""
    return {
        "version": 1,
        "mcp": {
            "enabled": True,
            "allowed": [],
            "excluded": [],
            "serverCommand": "",
            "discovery_timeout_ms": MCP_DEFAULT_DISCOVERY_TIMEOUT_MS,
        },
        "mcpServers": {},
    }


def _stable_json_signature(value: Any) -> str:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        payload = repr(value)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


def _normalize_string_map(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, str] = {}
    for key, raw in value.items():
        text_key = str(key or "").strip()
        if not text_key:
            continue
        normalized[text_key] = str(raw or "")
    return normalized


def normalize_mcp_input_schema(raw_schema: Any) -> Dict[str, Any]:
    """Normalize arbitrary MCP input schemas into a safe JSON-schema object."""
    if not isinstance(raw_schema, dict):
        return {"type": "object", "properties": {}, "required": []}

    schema = dict(raw_schema)
    schema_type = str(schema.get("type", "") or "").strip().lower()
    if not schema_type:
        schema["type"] = "object"
    elif schema_type != "object":
        if isinstance(schema.get("properties"), dict):
            schema["type"] = "object"
        else:
            return {"type": "object", "properties": {}, "required": []}

    if not isinstance(schema.get("properties"), dict):
        schema["properties"] = {}

    required = schema.get("required", [])
    if not isinstance(required, list):
        required = []
    schema["required"] = [str(item) for item in required if str(item or "").strip()]
    return schema


def _normalize_mcp_transport_type(raw_type: Any, *, command: str, http_url: str, url: str) -> str:
    candidate = str(raw_type or "").strip().lower().replace("-", "_")
    aliases = {
        "streamable_http": "http",
        "streamablehttp": "http",
        "legacy_sse": "sse",
        "http_sse": "sse",
    }
    candidate = aliases.get(candidate, candidate)
    if candidate in {"stdio", "http", "sse"}:
        return candidate
    if command:
        return "stdio"
    if http_url:
        return "http"
    if url:
        return "sse"
    return "stdio"


def normalize_mcp_server_config(server_name: str, raw_server: Any) -> Dict[str, Any]:
    """Normalize one MCP server configuration entry."""
    data = dict(raw_server) if isinstance(raw_server, dict) else {}

    command = str(data.get("command", "") or "").strip()
    url = str(data.get("url", "") or "").strip()
    http_url = str(data.get("httpUrl", "") or "").strip()
    server_type = _normalize_mcp_transport_type(
        data.get("type", ""),
        command=command,
        http_url=http_url,
        url=url,
    )

    if server_type == "sse" and not url and http_url:
        url = http_url

    try:
        timeout_ms = int(data.get("timeout", MCP_DEFAULT_TIMEOUT_MS))
    except (TypeError, ValueError):
        timeout_ms = MCP_DEFAULT_TIMEOUT_MS
    if timeout_ms <= 0:
        timeout_ms = MCP_DEFAULT_TIMEOUT_MS

    return {
        "enabled": bool(data.get("enabled", True)),
        "type": server_type,
        "command": command,
        "args": _normalize_string_list(data.get("args", [])),
        "url": url,
        "httpUrl": http_url,
        "headers": _normalize_string_map(data.get("headers", {})),
        "env": _normalize_string_map(data.get("env", {})),
        "cwd": str(data.get("cwd", "") or "").strip(),
        "timeout": timeout_ms,
        "trust": bool(data.get("trust", False)),
        "includeTools": _normalize_string_list(data.get("includeTools", [])),
        "excludeTools": _normalize_string_list(data.get("excludeTools", [])),
        "name": str(server_name or "").strip(),
    }


def normalize_mcp_config(raw_config: Any) -> Dict[str, Any]:
    """Normalize the top-level MCP config file."""
    normalized = default_mcp_config()
    if isinstance(raw_config, dict):
        normalized.update(raw_config)

    mcp_raw = normalized.get("mcp", {})
    mcp = dict(mcp_raw) if isinstance(mcp_raw, dict) else {}
    try:
        discovery_timeout_ms = int(mcp.get("discovery_timeout_ms", MCP_DEFAULT_DISCOVERY_TIMEOUT_MS))
    except (TypeError, ValueError):
        discovery_timeout_ms = MCP_DEFAULT_DISCOVERY_TIMEOUT_MS
    if discovery_timeout_ms <= 0:
        discovery_timeout_ms = MCP_DEFAULT_DISCOVERY_TIMEOUT_MS

    servers_raw = normalized.get("mcpServers", {})
    servers: Dict[str, Dict[str, Any]] = {}
    if isinstance(servers_raw, dict):
        for raw_name, raw_server in servers_raw.items():
            name = str(raw_name or "").strip()
            if not name:
                continue
            servers[name] = normalize_mcp_server_config(name, raw_server)

    return {
        "version": int(normalized.get("version", 1) or 1),
        "mcp": {
            "enabled": bool(mcp.get("enabled", True)),
            "allowed": _normalize_string_list(mcp.get("allowed", [])),
            "excluded": _normalize_string_list(mcp.get("excluded", [])),
            "serverCommand": str(mcp.get("serverCommand", "") or "").strip(),
            "discovery_timeout_ms": discovery_timeout_ms,
        },
        "mcpServers": servers,
    }


def get_effective_mcp_servers(mcp_config: Any) -> Dict[str, Dict[str, Any]]:
    """Return enabled/allowed server configs in priority order."""
    normalized = normalize_mcp_config(mcp_config)
    if not normalized["mcp"].get("enabled", True):
        return {}

    allowed = {item.lower() for item in normalized["mcp"].get("allowed", [])}
    excluded = {item.lower() for item in normalized["mcp"].get("excluded", [])}
    effective: Dict[str, Dict[str, Any]] = {}
    for server_name, server_cfg in normalized["mcpServers"].items():
        lowered = server_name.lower()
        if not server_cfg.get("enabled", True):
            continue
        if allowed and lowered not in allowed:
            continue
        if lowered in excluded:
            continue
        effective[server_name] = dict(server_cfg)
    return effective


def expand_mcp_env_value(value: Any, source_env: Optional[Dict[str, str]] = None) -> str:
    """Expand POSIX and Windows-style environment references."""
    text = str(value or "")
    env = source_env or dict(os.environ)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1) or match.group(2) or match.group(3) or ""
        return str(env.get(key, "") or "")

    return _ENV_VAR_PATTERN.sub(replace, text)


def sanitize_mcp_identifier(value: Any) -> str:
    text = _SAFE_IDENTIFIER_PATTERN.sub("_", str(value or "").strip().lower()).strip("_")
    return text or "item"


def build_mcp_tool_name(server_name: str, tool_name: str, used_names: Optional[set[str]] = None) -> str:
    """Build a model-safe synthetic function name for one MCP tool."""
    base = f"mcp_{sanitize_mcp_identifier(server_name)}_{sanitize_mcp_identifier(tool_name)}"
    digest = hashlib.sha1(f"{server_name}\0{tool_name}".encode("utf-8")).hexdigest()[:10]
    if len(base) > 64:
        prefix = base[:53].rstrip("_")
        base = f"{prefix}_{digest}"

    candidate = base
    if used_names is None:
        return candidate

    suffix_index = 2
    while candidate in used_names:
        suffix = f"_{suffix_index}"
        trimmed = base[: max(1, 64 - len(suffix))]
        candidate = f"{trimmed}{suffix}"
        suffix_index += 1
    return candidate


def is_mcp_tool_enabled(tool_name: str, server_cfg: Dict[str, Any]) -> bool:
    """Apply Gemini-style include/exclude tool filters."""
    name = str(tool_name or "").strip()
    if not name:
        return False

    excludes = server_cfg.get("excludeTools", []) or []
    includes = server_cfg.get("includeTools", []) or []
    if any(item == name or str(item).startswith(f"{name}(") for item in excludes):
        return False
    if not includes:
        return True
    return any(item == name or str(item).startswith(f"{name}(") for item in includes)


def format_mcp_call_result(result: Any) -> Tuple[str, Dict[str, Any], bool]:
    """Convert MCP tool results into a readable transcript payload."""
    if not isinstance(result, dict):
        text = str(result or "").strip()
        return text, {"raw_result": result}, False

    text_parts: List[str] = []
    content = result.get("content", [])
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "") or "").strip().lower()
            if item_type == "text":
                text_value = str(item.get("text", "") or "").strip()
                if text_value:
                    text_parts.append(text_value)
            elif item_type == "resource":
                uri = str(item.get("uri", "") or "").strip()
                mime_type = str(item.get("mimeType", "") or "").strip()
                if uri:
                    label = uri if not mime_type else f"{uri} ({mime_type})"
                    text_parts.append(label)

    structured = result.get("structuredContent")
    output = "\n\n".join(part for part in text_parts if part)
    if not output and structured is not None:
        try:
            output = json.dumps(structured, ensure_ascii=False, indent=2)
        except Exception:
            output = str(structured)
    if not output:
        try:
            output = json.dumps(result, ensure_ascii=False, indent=2)
        except Exception:
            output = str(result)

    is_error = bool(result.get("isError"))
    metadata = {
        "content": content if isinstance(content, list) else [],
        "structured_content": structured,
        "is_error": is_error,
        "raw_result": result,
    }
    return output, metadata, is_error


def _iter_sse_events(line_iter) -> Any:
    """Yield decoded SSE events from an iterable of response lines."""
    event_name = ""
    event_id = ""
    retry_ms: Optional[int] = None
    data_lines: List[str] = []

    for raw_line in line_iter:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", "replace")
        else:
            line = str(raw_line or "")
        line = line.rstrip("\r")

        if line == "":
            if event_name or event_id or data_lines or retry_ms is not None:
                yield {
                    "event": event_name or "message",
                    "id": event_id,
                    "retry": retry_ms,
                    "data": "\n".join(data_lines),
                }
            event_name = ""
            event_id = ""
            retry_ms = None
            data_lines = []
            continue

        if line.startswith(":"):
            continue

        field, _, raw_value = line.partition(":")
        value = raw_value[1:] if raw_value.startswith(" ") else raw_value
        field = field.strip().lower()
        if field == "event":
            event_name = value.strip()
        elif field == "data":
            data_lines.append(value)
        elif field == "id":
            event_id = value.strip()
        elif field == "retry":
            try:
                retry_ms = max(0, int(value.strip()))
            except (TypeError, ValueError):
                continue

    if event_name or event_id or data_lines or retry_ms is not None:
        yield {
            "event": event_name or "message",
            "id": event_id,
            "retry": retry_ms,
            "data": "\n".join(data_lines),
        }


class MCPConfigManager:
    """Persist MCP configuration beside the executable/script root."""

    def __init__(self, app_root: Optional[Path] = None):
        self.app_root = Path(app_root).resolve() if app_root is not None else get_app_root()
        self.config_path = self.app_root / MCP_CONFIG_DIRNAME / MCP_CONFIG_FILENAME
        self._config: Optional[Dict[str, Any]] = None
        self._last_mtime = 0.0

    def ensure_dirs(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                current_mtime = os.path.getmtime(self.config_path)
            except OSError:
                current_mtime = 0.0
            if self._config is None or current_mtime > self._last_mtime:
                try:
                    with open(self.config_path, "r", encoding="utf-8") as handle:
                        data = json.load(handle)
                except Exception:
                    data = {}
                self._config = normalize_mcp_config(data)
                self._last_mtime = current_mtime
        elif self._config is None:
            self._config = normalize_mcp_config({})
        return normalize_mcp_config(self._config)

    def save(self, config: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_dirs()
        normalized = normalize_mcp_config(config)
        write_json_secure(self.config_path, normalized)
        self._config = normalized
        try:
            self._last_mtime = os.path.getmtime(self.config_path)
        except OSError:
            self._last_mtime = 0.0
        return normalized

    def get_config_path(self) -> Path:
        return self.config_path

    def _resolve_server_name(self, name: str, config: Optional[Dict[str, Any]] = None) -> str:
        wanted = str(name or "").strip()
        if not wanted:
            return ""
        current = config or self.load()
        for existing in current.get("mcpServers", {}).keys():
            if existing.lower() == wanted.lower():
                return existing
        return wanted

    def upsert_server(self, name: str, server_config: Dict[str, Any]) -> Dict[str, Any]:
        config = self.load()
        resolved = self._resolve_server_name(name, config=config)
        config.setdefault("mcpServers", {})[resolved] = normalize_mcp_server_config(resolved, server_config)
        return self.save(config)

    def remove_server(self, name: str) -> bool:
        config = self.load()
        resolved = self._resolve_server_name(name, config=config)
        if resolved not in config.get("mcpServers", {}):
            return False
        config["mcpServers"].pop(resolved, None)
        self.save(config)
        return True

    def set_server_enabled(self, name: str, enabled: bool) -> bool:
        config = self.load()
        resolved = self._resolve_server_name(name, config=config)
        entry = config.get("mcpServers", {}).get(resolved)
        if not isinstance(entry, dict):
            return False
        entry["enabled"] = bool(enabled)
        config["mcpServers"][resolved] = normalize_mcp_server_config(resolved, entry)
        self.save(config)
        return True

    def set_server_trust(self, name: str, trusted: bool) -> bool:
        config = self.load()
        resolved = self._resolve_server_name(name, config=config)
        entry = config.get("mcpServers", {}).get(resolved)
        if not isinstance(entry, dict):
            return False
        entry["trust"] = bool(trusted)
        config["mcpServers"][resolved] = normalize_mcp_server_config(resolved, entry)
        self.save(config)
        return True


class MCPClientError(RuntimeError):
    """Raised when an MCP client request fails."""


class BaseMCPClient:
    """Base class for one MCP server connection."""

    def __init__(self, server_name: str, server_config: Dict[str, Any], project_root: Optional[Path] = None):
        self.server_name = str(server_name or "").strip()
        self.server_config = normalize_mcp_server_config(self.server_name, server_config)
        self.project_root = Path(project_root).resolve() if project_root is not None else None
        self._lock = threading.RLock()
        self._initialized = False
        self._catalog_dirty = True
        self._discovery_cache: Optional[Dict[str, Any]] = None
        self._last_error = ""

    @property
    def catalog_dirty(self) -> bool:
        return self._catalog_dirty

    @property
    def last_error(self) -> str:
        return self._last_error

    def set_project_root(self, project_root: Optional[Path]) -> None:
        self.project_root = Path(project_root).resolve() if project_root is not None else None

    def close(self) -> None:
        """Close any underlying transport resources."""

    def _request_timeout_ms(self, timeout_ms: Optional[int] = None) -> int:
        try:
            resolved = int(timeout_ms if timeout_ms is not None else self.server_config.get("timeout", MCP_DEFAULT_TIMEOUT_MS))
        except (TypeError, ValueError):
            resolved = MCP_DEFAULT_TIMEOUT_MS
        if resolved <= 0:
            resolved = MCP_DEFAULT_TIMEOUT_MS
        return resolved

    def _handle_notification(self, message: Dict[str, Any]) -> None:
        method = str(message.get("method", "") or "").strip().lower()
        if method.endswith("list_changed"):
            self._catalog_dirty = True

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout_ms: Optional[int] = None,
        expect_response: bool = True,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.request(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": dict(MCP_CLIENT_INFO),
                },
                expect_response=True,
            )
            self.request("notifications/initialized", {}, expect_response=False)
            self._initialized = True

    def discover(self, force: bool = False, timeout_ms: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            if self._discovery_cache is not None and not force and not self._catalog_dirty:
                return dict(self._discovery_cache)

            self.initialize()
            errors: List[str] = []
            tools: List[Dict[str, Any]] = []
            resources: List[Dict[str, Any]] = []
            prompts: List[Dict[str, Any]] = []

            try:
                tools_result = self.request("tools/list", {}, timeout_ms=timeout_ms, expect_response=True)
                if isinstance(tools_result, dict) and isinstance(tools_result.get("tools"), list):
                    tools = [item for item in tools_result.get("tools", []) if isinstance(item, dict)]
            except Exception as exc:
                errors.append(f"tools/list: {exc}")

            try:
                resources_result = self.request("resources/list", {}, timeout_ms=timeout_ms, expect_response=True)
                if isinstance(resources_result, dict) and isinstance(resources_result.get("resources"), list):
                    resources = [item for item in resources_result.get("resources", []) if isinstance(item, dict)]
            except Exception:
                pass

            try:
                prompts_result = self.request("prompts/list", {}, timeout_ms=timeout_ms, expect_response=True)
                if isinstance(prompts_result, dict) and isinstance(prompts_result.get("prompts"), list):
                    prompts = [item for item in prompts_result.get("prompts", []) if isinstance(item, dict)]
            except Exception:
                pass

            self._last_error = " | ".join(str(item) for item in errors if str(item).strip())
            self._catalog_dirty = False
            self._discovery_cache = {
                "tools": tools,
                "resources": resources,
                "prompts": prompts,
                "error": self._last_error,
                "fetched_at": time.time(),
            }
            return dict(self._discovery_cache)

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.initialize()
        params = {"name": str(tool_name or "").strip(), "arguments": arguments or {}}
        result = self.request("tools/call", params, expect_response=True)
        return result if isinstance(result, dict) else {"content": [{"type": "text", "text": str(result)}]}

    def read_resource(self, uri: str) -> Dict[str, Any]:
        self.initialize()
        result = self.request("resources/read", {"uri": str(uri or "").strip()}, expect_response=True)
        return result if isinstance(result, dict) else {"contents": []}


class UnsupportedTransportMCPClient(BaseMCPClient):
    """Used when the configured transport is intentionally unsupported."""

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout_ms: Optional[int] = None,
        expect_response: bool = True,
    ) -> Dict[str, Any]:
        transport = str(self.server_config.get("type", "") or "unknown").strip()
        raise MCPClientError(f"MCP server '{self.server_name}' uses unsupported transport '{transport}'.")


class StdioMCPClient(BaseMCPClient):
    """Minimal stdio MCP client using newline-delimited JSON."""

    def __init__(self, server_name: str, server_config: Dict[str, Any], project_root: Optional[Path] = None):
        super().__init__(server_name, server_config, project_root=project_root)
        self._process: Optional[subprocess.Popen[str]] = None
        self._request_counter = 0
        self._stdout_queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stderr_tail: List[str] = []

    def close(self) -> None:
        process = self._process
        self._process = None
        if not process:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except Exception:
            pass
        try:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=2.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _next_request_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def _resolve_cwd(self) -> Optional[str]:
        raw_cwd = str(self.server_config.get("cwd", "") or "").strip()
        if not raw_cwd:
            return str(self.project_root) if self.project_root is not None else None

        candidate = Path(expand_mcp_env_value(raw_cwd)).expanduser()
        if not candidate.is_absolute():
            base = self.project_root if self.project_root is not None else Path.cwd()
            candidate = base / candidate
        return str(candidate.resolve(strict=False))

    def _build_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        overlays = self.server_config.get("env", {}) or {}
        for key, raw_value in overlays.items():
            env[str(key)] = expand_mcp_env_value(raw_value, env)
        env.setdefault("REVERIE_CLI", "1")
        return env

    def _append_stderr_line(self, line: str) -> None:
        text = str(line or "").rstrip()
        if not text:
            return
        self._stderr_tail.append(text)
        if len(self._stderr_tail) > 30:
            self._stderr_tail = self._stderr_tail[-30:]

    def _read_stdout_loop(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        while True:
            try:
                raw_line = process.stdout.readline()
            except Exception:
                break
            if raw_line == "":
                break
            line = str(raw_line or "").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                logger.debug("Ignored invalid MCP stdout line from %s: %r", self.server_name, line)
                continue
            if isinstance(payload, dict):
                self._stdout_queue.put(payload)

    def _read_stderr_loop(self) -> None:
        process = self._process
        if not process or not process.stderr:
            return
        while True:
            try:
                raw_line = process.stderr.readline()
            except Exception:
                break
            if raw_line == "":
                break
            self._append_stderr_line(str(raw_line))

    def _ensure_process(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            return

        self.close()
        command = str(self.server_config.get("command", "") or "").strip()
        args = self.server_config.get("args", []) or []
        if not command:
            raise MCPClientError(f"MCP server '{self.server_name}' is missing a stdio command.")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self._process = subprocess.Popen(
                [command, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self._resolve_cwd(),
                env=self._build_env(),
                creationflags=creationflags,
            )
        except Exception as exc:
            raise MCPClientError(f"Failed to start MCP server '{self.server_name}': {exc}") from exc

        self._stdout_queue = queue.Queue()
        self._stderr_tail = []
        self._stdout_thread = threading.Thread(target=self._read_stdout_loop, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr_loop, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _format_stderr_tail(self) -> str:
        if not self._stderr_tail:
            return ""
        return " | ".join(self._stderr_tail[-5:])

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout_ms: Optional[int] = None,
        expect_response: bool = True,
    ) -> Dict[str, Any]:
        with self._lock:
            self._ensure_process()
            process = self._process
            if process is None or process.stdin is None:
                raise MCPClientError(f"MCP server '{self.server_name}' is not running.")
            if process.poll() is not None:
                raise MCPClientError(
                    f"MCP server '{self.server_name}' exited before request {method!r}. "
                    f"{self._format_stderr_tail()}".strip()
                )

            request_id = self._next_request_id() if expect_response else None
            payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": str(method or "").strip()}
            if request_id is not None:
                payload["id"] = request_id
            if isinstance(params, dict):
                payload["params"] = params

            try:
                process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                process.stdin.flush()
            except Exception as exc:
                raise MCPClientError(f"Failed to write to MCP server '{self.server_name}': {exc}") from exc

            if not expect_response:
                return {}

            deadline = time.monotonic() + (self._request_timeout_ms(timeout_ms) / 1000.0)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stderr_tail = self._format_stderr_tail()
                    raise MCPClientError(
                        f"Timed out waiting for MCP server '{self.server_name}' during {method!r}."
                        f"{(' ' + stderr_tail) if stderr_tail else ''}"
                    )
                try:
                    message = self._stdout_queue.get(timeout=remaining)
                except queue.Empty as exc:
                    raise MCPClientError(
                        f"Timed out waiting for MCP server '{self.server_name}' during {method!r}."
                    ) from exc

                if not isinstance(message, dict):
                    continue
                if "method" in message and "id" not in message:
                    self._handle_notification(message)
                    continue
                if message.get("id") != request_id:
                    continue
                if isinstance(message.get("error"), dict):
                    error = message["error"]
                    code = error.get("code")
                    detail = error.get("message") or error.get("data") or "Unknown MCP error"
                    raise MCPClientError(f"MCP server '{self.server_name}' returned {code}: {detail}")
                result = message.get("result", {})
                return result if isinstance(result, dict) else {"result": result}


class HttpMCPClient(BaseMCPClient):
    """Minimal streamable-HTTP MCP client."""

    def __init__(self, server_name: str, server_config: Dict[str, Any], project_root: Optional[Path] = None):
        super().__init__(server_name, server_config, project_root=project_root)
        self._request_counter = 0
        self._session = requests.Session()
        self._session_id = ""

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def _next_request_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def _endpoint(self) -> str:
        http_url = str(self.server_config.get("httpUrl", "") or "").strip()
        if http_url:
            return http_url
        return str(self.server_config.get("url", "") or "").strip()

    def _request_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if self._session_id:
            headers[MCP_SESSION_HEADER] = self._session_id
        for key, value in (self.server_config.get("headers", {}) or {}).items():
            k = str(key or "").strip()
            v = str(value or "").strip()
            if k and v:
                headers[k] = v
        return headers

    def _timeout_seconds(self, timeout_ms: Optional[int]) -> float:
        return max(1.0, self._request_timeout_ms(timeout_ms) / 1000.0)

    def _update_session_id(self, response: requests.Response) -> None:
        session_id = str(response.headers.get(MCP_SESSION_HEADER, "") or "").strip()
        if session_id:
            self._session_id = session_id

    def _parse_sse_message(self, response: requests.Response, request_id: int) -> Dict[str, Any]:
        for event in _iter_sse_events(response.iter_lines(decode_unicode=True)):
            payload_text = str(event.get("data", "") or "").strip()
            if not payload_text:
                continue
            try:
                payload = json.loads(payload_text)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if "method" in payload and "id" not in payload:
                self._handle_notification(payload)
                continue
            if payload.get("id") == request_id:
                return payload
        raise MCPClientError(f"MCP server '{self.server_name}' closed the HTTP stream before replying.")

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout_ms: Optional[int] = None,
        expect_response: bool = True,
    ) -> Dict[str, Any]:
        with self._lock:
            endpoint = self._endpoint()
            if not endpoint:
                raise MCPClientError(f"MCP server '{self.server_name}' is missing a remote URL.")

            request_id = self._next_request_id() if expect_response else None
            payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": str(method or "").strip()}
            if request_id is not None:
                payload["id"] = request_id
            if isinstance(params, dict):
                payload["params"] = params

            try:
                response = self._session.post(
                    endpoint,
                    headers=self._request_headers(),
                    json=payload,
                    timeout=self._timeout_seconds(timeout_ms),
                    stream=bool(expect_response),
                )
            except Exception as exc:
                raise MCPClientError(f"Failed to reach MCP server '{self.server_name}': {exc}") from exc

            self._update_session_id(response)
            if not expect_response:
                try:
                    response.raise_for_status()
                finally:
                    response.close()
                return {}

            try:
                response.raise_for_status()
                content_type = str(response.headers.get("Content-Type", "") or "").lower()
                if "text/event-stream" in content_type:
                    message = self._parse_sse_message(response, request_id or 0)
                else:
                    message = response.json()
            except Exception as exc:
                raise MCPClientError(f"MCP HTTP request to '{self.server_name}' failed: {exc}") from exc
            finally:
                response.close()

            if not isinstance(message, dict):
                raise MCPClientError(f"MCP server '{self.server_name}' returned a non-JSON response.")
            if isinstance(message.get("error"), dict):
                error = message["error"]
                code = error.get("code")
                detail = error.get("message") or error.get("data") or "Unknown MCP error"
                raise MCPClientError(f"MCP server '{self.server_name}' returned {code}: {detail}")
            result = message.get("result", {})
            return result if isinstance(result, dict) else {"result": result}


class SseMCPClient(BaseMCPClient):
    """Legacy HTTP+SSE MCP client compatible with Gemini/Qwen-style `url` configs."""

    def __init__(self, server_name: str, server_config: Dict[str, Any], project_root: Optional[Path] = None):
        super().__init__(server_name, server_config, project_root=project_root)
        self._request_counter = 0
        self._session = requests.Session()
        self._stream_response: Optional[requests.Response] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_generation = 0
        self._stream_stop = threading.Event()
        self._endpoint_ready = threading.Event()
        self._message_endpoint = ""
        self._stream_error = ""
        self._last_event_id = ""
        self._incoming_queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._pending_responses: Dict[Any, Dict[str, Any]] = {}

    def close(self) -> None:
        with self._lock:
            self._close_stream_locked(close_session=True)

    def _next_request_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def _endpoint_wait_seconds(self, timeout_ms: Optional[int] = None) -> float:
        request_seconds = self._request_timeout_ms(timeout_ms) / 1000.0
        return max(3.0, min(request_seconds, MCP_DEFAULT_SSE_ENDPOINT_TIMEOUT_MS / 1000.0))

    def _stream_timeout(self, timeout_ms: Optional[int] = None) -> tuple[float, float]:
        connect_timeout = max(5.0, min(30.0, self._request_timeout_ms(timeout_ms) / 1000.0))
        read_timeout = max(900.0, self._request_timeout_ms(timeout_ms) / 1000.0)
        return connect_timeout, read_timeout

    def _sse_url(self) -> str:
        return str(self.server_config.get("url", "") or "").strip()

    def _event_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self._last_event_id:
            headers["Last-Event-ID"] = self._last_event_id
        for key, value in (self.server_config.get("headers", {}) or {}).items():
            k = str(key or "").strip()
            v = str(value or "").strip()
            if k and v:
                headers[k] = v
        return headers

    def _post_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        for key, value in (self.server_config.get("headers", {}) or {}).items():
            k = str(key or "").strip()
            v = str(value or "").strip()
            if k and v:
                headers[k] = v
        return headers

    def _close_stream_locked(self, *, close_session: bool) -> None:
        self._stream_stop.set()
        response = self._stream_response
        self._stream_response = None
        self._stream_thread = None
        self._stream_generation += 1
        self._message_endpoint = ""
        self._endpoint_ready.clear()
        self._stream_error = ""
        self._incoming_queue = queue.Queue()
        self._pending_responses = {}
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if close_session:
            try:
                self._session.close()
            except Exception:
                pass

    def _handle_stream_payload(self, payload: Dict[str, Any]) -> None:
        if "method" in payload and "id" not in payload:
            self._handle_notification(payload)
            return
        self._incoming_queue.put(payload)

    def _read_stream_loop(self, response: requests.Response, generation: int) -> None:
        try:
            for event in _iter_sse_events(response.iter_lines(decode_unicode=True)):
                if generation != self._stream_generation or self._stream_stop.is_set():
                    return

                event_id = str(event.get("id", "") or "").strip()
                if event_id:
                    self._last_event_id = event_id

                event_name = str(event.get("event", "") or "message").strip().lower()
                event_data = str(event.get("data", "") or "")
                if event_name == "endpoint":
                    endpoint_value = event_data.strip()
                    if endpoint_value:
                        self._message_endpoint = urljoin(self._sse_url(), endpoint_value)
                        self._endpoint_ready.set()
                    continue

                if not event_data.strip():
                    continue

                try:
                    payload = json.loads(event_data)
                except Exception:
                    logger.debug("Ignored invalid MCP SSE payload from %s: %r", self.server_name, event_data)
                    continue

                if isinstance(payload, dict):
                    self._handle_stream_payload(payload)
        except Exception as exc:
            self._stream_error = str(exc)
            self._endpoint_ready.set()
        finally:
            if generation == self._stream_generation:
                self._stream_response = None
                if not self._stream_stop.is_set() and not self._stream_error:
                    self._stream_error = "SSE stream closed unexpectedly."
                self._endpoint_ready.set()

    def _ensure_stream_locked(self, timeout_ms: Optional[int] = None) -> None:
        if self._stream_response is not None and self._stream_thread is not None and self._stream_thread.is_alive():
            if self._message_endpoint:
                return
            if self._endpoint_ready.wait(timeout=self._endpoint_wait_seconds(timeout_ms)):
                if self._message_endpoint:
                    return
                if self._stream_error:
                    raise MCPClientError(
                        f"Failed to establish SSE endpoint for MCP server '{self.server_name}': {self._stream_error}"
                    )

        self._close_stream_locked(close_session=False)
        self._stream_stop = threading.Event()
        self._endpoint_ready = threading.Event()
        self._stream_error = ""
        sse_url = self._sse_url()
        if not sse_url:
            raise MCPClientError(f"MCP server '{self.server_name}' is missing an SSE URL.")

        try:
            response = self._session.get(
                sse_url,
                headers=self._event_headers(),
                stream=True,
                timeout=self._stream_timeout(timeout_ms),
            )
            response.raise_for_status()
        except Exception as exc:
            raise MCPClientError(f"Failed to open SSE stream for MCP server '{self.server_name}': {exc}") from exc

        content_type = str(response.headers.get("Content-Type", "") or "").lower()
        if "text/event-stream" not in content_type:
            response.close()
            raise MCPClientError(
                f"MCP server '{self.server_name}' did not return an SSE stream from {sse_url}."
            )

        self._stream_response = response
        self._stream_generation += 1
        generation = self._stream_generation
        self._stream_thread = threading.Thread(
            target=self._read_stream_loop,
            args=(response, generation),
            daemon=True,
            name=f"reverie-mcp-sse-{sanitize_mcp_identifier(self.server_name)}",
        )
        self._stream_thread.start()

        if not self._endpoint_ready.wait(timeout=self._endpoint_wait_seconds(timeout_ms)):
            self._close_stream_locked(close_session=False)
            raise MCPClientError(
                f"Timed out waiting for the SSE endpoint advertisement from MCP server '{self.server_name}'."
            )
        if not self._message_endpoint:
            error = self._stream_error or "SSE server did not publish an endpoint event."
            self._close_stream_locked(close_session=False)
            raise MCPClientError(f"Failed to establish SSE endpoint for MCP server '{self.server_name}': {error}")

    def _wait_for_response_locked(self, request_id: int, method: str, timeout_ms: Optional[int]) -> Dict[str, Any]:
        if request_id in self._pending_responses:
            return self._pending_responses.pop(request_id)

        deadline = time.monotonic() + (self._request_timeout_ms(timeout_ms) / 1000.0)
        while True:
            if request_id in self._pending_responses:
                return self._pending_responses.pop(request_id)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPClientError(
                    f"Timed out waiting for MCP SSE server '{self.server_name}' during {method!r}."
                )

            if self._stream_error and (self._stream_thread is None or not self._stream_thread.is_alive()):
                raise MCPClientError(
                    f"MCP SSE stream for '{self.server_name}' closed during {method!r}: {self._stream_error}"
                )

            try:
                message = self._incoming_queue.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                continue

            if not isinstance(message, dict):
                continue
            if "method" in message and "id" not in message:
                self._handle_notification(message)
                continue

            message_id = message.get("id")
            if message_id == request_id:
                return message
            if message_id is not None:
                self._pending_responses[message_id] = message

    def _parse_response_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(message.get("error"), dict):
            error = message["error"]
            code = error.get("code")
            detail = error.get("message") or error.get("data") or "Unknown MCP error"
            raise MCPClientError(f"MCP server '{self.server_name}' returned {code}: {detail}")
        result = message.get("result", {})
        return result if isinstance(result, dict) else {"result": result}

    def _parse_inline_sse_response(self, response: requests.Response, request_id: int) -> Optional[Dict[str, Any]]:
        for event in _iter_sse_events(response.iter_lines(decode_unicode=True)):
            event_name = str(event.get("event", "") or "message").strip().lower()
            event_data = str(event.get("data", "") or "").strip()
            if event_name == "endpoint":
                if event_data:
                    self._message_endpoint = urljoin(self._sse_url(), event_data)
                    self._endpoint_ready.set()
                continue
            if not event_data:
                continue
            try:
                payload = json.loads(event_data)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if "method" in payload and "id" not in payload:
                self._handle_notification(payload)
                continue
            if payload.get("id") == request_id:
                return payload
            if payload.get("id") is not None:
                self._pending_responses[payload.get("id")] = payload
        return None

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout_ms: Optional[int] = None,
        expect_response: bool = True,
    ) -> Dict[str, Any]:
        with self._lock:
            self._ensure_stream_locked(timeout_ms=timeout_ms)

            request_id = self._next_request_id() if expect_response else None
            payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": str(method or "").strip()}
            if request_id is not None:
                payload["id"] = request_id
            if isinstance(params, dict):
                payload["params"] = params

            try:
                response = self._session.post(
                    self._message_endpoint,
                    headers=self._post_headers(),
                    json=payload,
                    timeout=max(1.0, self._request_timeout_ms(timeout_ms) / 1000.0),
                    stream=bool(expect_response),
                )
            except Exception as exc:
                raise MCPClientError(
                    f"Failed to POST to MCP SSE endpoint for server '{self.server_name}': {exc}"
                ) from exc

            if not expect_response:
                try:
                    response.raise_for_status()
                finally:
                    response.close()
                return {}

            try:
                response.raise_for_status()
                content_type = str(response.headers.get("Content-Type", "") or "").lower()
                if "text/event-stream" in content_type:
                    inline_message = self._parse_inline_sse_response(response, request_id or 0)
                    if inline_message is not None:
                        return self._parse_response_message(inline_message)
                elif response.content:
                    message = response.json()
                    if isinstance(message, dict):
                        return self._parse_response_message(message)
            except Exception as exc:
                raise MCPClientError(f"MCP SSE request to '{self.server_name}' failed: {exc}") from exc
            finally:
                response.close()

            message = self._wait_for_response_locked(request_id or 0, method, timeout_ms)
            return self._parse_response_message(message)


class MCPRuntime:
    """Load MCP config, discover tools, and execute MCP calls on demand."""

    def __init__(self, config_manager: MCPConfigManager, project_root: Optional[Path] = None):
        self.config_manager = config_manager
        self.project_root = Path(project_root).resolve() if project_root is not None else None
        self._lock = threading.RLock()
        self._config = normalize_mcp_config({})
        self._config_signature = ""
        self._clients: Dict[str, BaseMCPClient] = {}
        self._tool_catalog: List[Dict[str, Any]] = []
        self._tool_lookup: Dict[str, Dict[str, Any]] = {}
        self._catalog_signature = ""
        self._generation = 0
        self._refresh_config_locked(force=True)

    def close(self) -> None:
        with self._lock:
            for client in self._clients.values():
                try:
                    client.close()
                except Exception:
                    pass
            self._clients = {}

    def set_project_root(self, project_root: Optional[Path]) -> None:
        with self._lock:
            self.project_root = Path(project_root).resolve() if project_root is not None else None
            for client in self._clients.values():
                client.set_project_root(self.project_root)

    def _refresh_config_locked(self, force: bool = False) -> bool:
        config = self.config_manager.load()
        signature = _stable_json_signature(config)
        if not force and signature == self._config_signature:
            return False

        for client in self._clients.values():
            try:
                client.close()
            except Exception:
                pass

        self._config = normalize_mcp_config(config)
        self._config_signature = signature
        self._clients = {}
        self._tool_catalog = []
        self._tool_lookup = {}
        self._catalog_signature = ""
        self._generation += 1
        return True

    def reload(self, force: bool = False) -> bool:
        with self._lock:
            return self._refresh_config_locked(force=force)

    def get_generation(self) -> int:
        with self._lock:
            self._refresh_config_locked(force=False)
            return self._generation

    def _get_effective_servers_locked(self) -> Dict[str, Dict[str, Any]]:
        return get_effective_mcp_servers(self._config)

    def _create_client_locked(self, server_name: str, server_cfg: Dict[str, Any]) -> BaseMCPClient:
        server_type = str(server_cfg.get("type", "stdio") or "stdio").strip().lower()
        if server_type == "stdio":
            return StdioMCPClient(server_name, server_cfg, project_root=self.project_root)
        if server_type == "http":
            return HttpMCPClient(server_name, server_cfg, project_root=self.project_root)
        if server_type == "sse":
            return SseMCPClient(server_name, server_cfg, project_root=self.project_root)
        return UnsupportedTransportMCPClient(server_name, server_cfg, project_root=self.project_root)

    def _get_client_locked(self, server_name: str, server_cfg: Dict[str, Any]) -> BaseMCPClient:
        current = self._clients.get(server_name)
        wanted_signature = _stable_json_signature(server_cfg)
        if current is not None:
            current_signature = _stable_json_signature(current.server_config)
            if current_signature == wanted_signature:
                current.set_project_root(self.project_root)
                return current
            try:
                current.close()
            except Exception:
                pass

        client = self._create_client_locked(server_name, server_cfg)
        self._clients[server_name] = client
        return client

    def _rebuild_catalog_locked(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        self._refresh_config_locked(force=False)
        effective_servers = self._get_effective_servers_locked()
        used_names: set[str] = set()
        catalog: List[Dict[str, Any]] = []
        lookup: Dict[str, Dict[str, Any]] = {}
        discovery_timeout_ms = int(self._config.get("mcp", {}).get("discovery_timeout_ms", MCP_DEFAULT_DISCOVERY_TIMEOUT_MS))

        for server_name, server_cfg in effective_servers.items():
            client = self._get_client_locked(server_name, server_cfg)
            try:
                discovery = client.discover(force=force_refresh, timeout_ms=discovery_timeout_ms)
            except Exception as exc:
                logger.debug("MCP discovery failed for %s: %s", server_name, exc, exc_info=True)
                continue
            raw_tools = discovery.get("tools", []) if isinstance(discovery, dict) else []
            for tool in raw_tools:
                if not isinstance(tool, dict):
                    continue
                actual_name = str(tool.get("name", "") or "").strip()
                if not actual_name or not is_mcp_tool_enabled(actual_name, server_cfg):
                    continue

                synthetic_name = build_mcp_tool_name(server_name, actual_name, used_names)
                used_names.add(synthetic_name)
                metadata = {
                    "name": synthetic_name,
                    "server_name": server_name,
                    "tool_name": actual_name,
                    "description": str(tool.get("description", "") or "").strip()
                    or f"MCP tool '{actual_name}' from server '{server_name}'.",
                    "parameters": normalize_mcp_input_schema(tool.get("inputSchema", tool.get("parameters"))),
                    "qualified_name": f"{server_name}.{actual_name}",
                    "transport": str(server_cfg.get("type", "") or "stdio"),
                    "trust": bool(server_cfg.get("trust", False)),
                }
                catalog.append(metadata)
                lookup[synthetic_name] = metadata

        new_signature = _stable_json_signature(catalog)
        if new_signature != self._catalog_signature:
            self._generation += 1
            self._catalog_signature = new_signature
        self._tool_catalog = catalog
        self._tool_lookup = lookup
        return [dict(item) for item in catalog]

    def get_tool_definitions(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            if self._tool_catalog and not force_refresh:
                effective_servers = self._get_effective_servers_locked()
                any_dirty = False
                for server_name, server_cfg in effective_servers.items():
                    client = self._get_client_locked(server_name, server_cfg)
                    if client.catalog_dirty:
                        any_dirty = True
                        break
                if not any_dirty:
                    return [dict(item) for item in self._tool_catalog]
            return self._rebuild_catalog_locked(force_refresh=force_refresh)

    def resolve_tool(self, synthetic_name: str) -> Optional[Dict[str, Any]]:
        wanted = str(synthetic_name or "").strip()
        if not wanted:
            return None
        with self._lock:
            if wanted not in self._tool_lookup:
                self._rebuild_catalog_locked(force_refresh=False)
            found = self._tool_lookup.get(wanted)
            return dict(found) if isinstance(found, dict) else None

    def call_tool(self, server_name: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            self._refresh_config_locked(force=False)
            effective_servers = self._get_effective_servers_locked()
            server_cfg = effective_servers.get(server_name)
            if not isinstance(server_cfg, dict):
                raise MCPClientError(f"MCP server '{server_name}' is not enabled.")
            client = self._get_client_locked(server_name, server_cfg)

        result = client.call_tool(tool_name, arguments or {})
        output, metadata, is_error = format_mcp_call_result(result)
        return {
            "success": not is_error,
            "output": output,
            "result": result,
            "data": metadata,
        }

    def list_server_status(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            self._refresh_config_locked(force=False)
            config = self._config
            effective_servers = self._get_effective_servers_locked()
            allowed = {item.lower() for item in config.get("mcp", {}).get("allowed", [])}
            excluded = {item.lower() for item in config.get("mcp", {}).get("excluded", [])}
            rows: List[Dict[str, Any]] = []

            for server_name, raw_server_cfg in config.get("mcpServers", {}).items():
                server_cfg = normalize_mcp_server_config(server_name, raw_server_cfg)
                lowered = server_name.lower()
                state = "enabled"
                if not config.get("mcp", {}).get("enabled", True):
                    state = "globally-disabled"
                elif not server_cfg.get("enabled", True):
                    state = "disabled"
                elif allowed and lowered not in allowed:
                    state = "not-allowed"
                elif lowered in excluded:
                    state = "excluded"

                entry = {
                    "name": server_name,
                    "type": server_cfg.get("type", "stdio"),
                    "enabled": bool(server_cfg.get("enabled", True)),
                    "state": state,
                    "trust": bool(server_cfg.get("trust", False)),
                    "tools": None,
                    "resources": None,
                    "prompts": None,
                    "error": "",
                }

                if state == "enabled":
                    client = self._get_client_locked(server_name, effective_servers[server_name])
                    try:
                        discovery = client.discover(
                            force=force_refresh,
                            timeout_ms=config.get("mcp", {}).get("discovery_timeout_ms"),
                        )
                        entry["tools"] = len(discovery.get("tools", []) or [])
                        entry["resources"] = len(discovery.get("resources", []) or [])
                        entry["prompts"] = len(discovery.get("prompts", []) or [])
                        entry["error"] = str(discovery.get("error", "") or "")
                    except Exception as exc:
                        entry["error"] = str(exc)
                rows.append(entry)

            rows.sort(key=lambda item: str(item.get("name", "")).lower())
            return rows

    def describe_for_prompt(self) -> str:
        """Return a compact MCP system-prompt addendum without forcing discovery."""
        with self._lock:
            self._refresh_config_locked(force=False)
            config = self._config
            if not config.get("mcp", {}).get("enabled", True):
                return (
                    "## MCP Integration\n"
                    "- MCP support is currently disabled.\n"
                    "- If MCP tools appear later, use their schemas directly instead of guessing parameters."
                )

            effective_servers = self._get_effective_servers_locked()
            lines = [
                "## MCP Integration",
                f"- MCP config file: `{self.config_manager.get_config_path()}`",
                "- Discovered MCP tools are exposed as function names like `mcp_<server>_<tool>`.",
                "- Prefer built-in workspace-safe tools for repository-local files, commands, and edits.",
                "- Use MCP tools when you need capabilities provided by configured external servers.",
            ]
            if not effective_servers:
                lines.append("- Configured MCP servers: (none enabled)")
            else:
                lines.append("- Enabled MCP servers:")
                for server_name, server_cfg in effective_servers.items():
                    trust_label = "trusted" if server_cfg.get("trust", False) else "confirmation-required"
                    lines.append(f"  - {server_name} ({server_cfg.get('type', 'stdio')}, {trust_label})")
            return "\n".join(lines)
