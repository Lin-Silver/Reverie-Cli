"""Executable-local Reverie Agentic Tool-protocol client runtime."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import get_app_root


RATS_PROTOCOL = "reverie.rtp/1"
RATS_DISCOVERY_SCHEMA = "reverie.rats.discovery/1"
RATS_PERMISSIONS = ("read", "project", "edit", "asset", "ai", "run", "build")
_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVICE_RE = re.compile(r"^rats-[1-9][0-9]*-[a-z0-9]+$")
_IDENTIFIER_RE = re.compile(r"[^a-z0-9_-]+")
_MAX_DESCRIPTOR_BYTES = 128 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024
_DEFAULT_LOADED_TOOLS = ("ping", "version", "get_status", "project.status")


class RatsClientError(RuntimeError):
    """Structured failure returned by or detected around an RTP service."""

    def __init__(self, message: str, *, status: int = 0, code: str = "request_failed") -> None:
        super().__init__(message)
        self.status = int(status)
        self.code = str(code or "request_failed")


def _record(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _path_key(value: Path | str) -> str:
    resolved = str(Path(value).expanduser().resolve(strict=False))
    return os.path.normcase(resolved)


def _unique_paths(values: Iterable[Any]) -> List[Path]:
    output: List[Path] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text:
            continue
        path = Path(text).expanduser().resolve(strict=False)
        key = _path_key(path)
        if key in seen:
            continue
        seen.add(key)
        output.append(path)
    return output


def normalize_rats_permissions(value: Any) -> List[str]:
    requested = value if isinstance(value, (list, tuple, set)) else []
    allowed = set(RATS_PERMISSIONS)
    normalized = sorted({_text(item) for item in requested if _text(item) in allowed})
    return normalized or ["read"]


def rats_discovery_root_for_executable(executable: Path | str) -> Path:
    return Path(executable).expanduser().resolve(strict=False).parent / "ReverieLocal" / "RATS" / "Services"


def _safe_identifier(value: Any) -> str:
    normalized = _IDENTIFIER_RE.sub("_", _text(value).lower()).strip("_")
    return normalized or "tool"


@dataclass(frozen=True)
class RatsDescriptor:
    service_id: str
    product: str
    product_version: str
    executable: Path
    pid: int
    port: int
    endpoint: str
    descriptor_path: Path
    catalog_revision: str
    native_tool_count: int
    started_utc: str
    control_token: str = field(repr=False)


@dataclass
class _RatsSession:
    descriptor: RatsDescriptor
    token: str = field(repr=False)
    permissions: List[str] = field(default_factory=list)
    compact_tools: List[Dict[str, Any]] = field(default_factory=list)
    definitions: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def parse_rats_descriptor(value: Any, descriptor_path: Path | str) -> Optional[RatsDescriptor]:
    source = _record(value)
    try:
        executable = Path(_text(source.get("executable"))).expanduser()
        service_id = _text(source.get("service_id"))
        pid = int(source.get("pid", 0))
        port = int(source.get("port", 0))
    except (TypeError, ValueError, OSError):
        return None
    endpoint = _text(source.get("endpoint"))
    control_token = _text(source.get("control_token")).lower()
    if (
        source.get("schema") != RATS_DISCOVERY_SCHEMA
        or source.get("protocol") != RATS_PROTOCOL
        or _text(source.get("bind_address")) != "127.0.0.1"
        or not _SERVICE_RE.fullmatch(service_id)
        or not executable.is_absolute()
        or pid <= 0
        or port <= 0
        or port > 65535
        or endpoint != f"http://127.0.0.1:{port}/rtp"
        or not _TOKEN_RE.fullmatch(control_token)
    ):
        return None
    return RatsDescriptor(
        service_id=service_id,
        product=_text(source.get("product")) or "Reverie Engine",
        product_version=_text(source.get("product_version")),
        executable=executable.resolve(strict=False),
        pid=pid,
        port=port,
        endpoint=endpoint,
        descriptor_path=Path(descriptor_path).resolve(strict=False),
        catalog_revision=_text(source.get("catalog_revision")),
        native_tool_count=max(0, int(source.get("native_tool_count", 0) or 0)),
        started_utc=_text(source.get("started_utc")),
        control_token=control_token,
    )


def discover_rats_descriptors(roots: Iterable[Path | str]) -> List[RatsDescriptor]:
    descriptors: Dict[tuple[str, str], RatsDescriptor] = {}
    for root in _unique_paths(roots):
        try:
            candidates = sorted(root.glob("rats-*.json"), key=lambda item: item.name.lower())
        except OSError:
            continue
        for candidate in candidates:
            try:
                if not candidate.is_file() or candidate.stat().st_size > _MAX_DESCRIPTOR_BYTES:
                    continue
                descriptor = parse_rats_descriptor(json.loads(candidate.read_text(encoding="utf-8")), candidate)
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if descriptor is not None:
                descriptors[(descriptor.service_id, _path_key(descriptor.descriptor_path))] = descriptor
    return sorted(descriptors.values(), key=lambda item: item.service_id)


def _compact_tools(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    tools: List[Dict[str, Any]] = []
    for item in value:
        source = _record(item)
        name = _text(source.get("name"))
        if not name:
            continue
        tools.append(
            {
                "key": _text(source.get("key")),
                "name": name,
                "category": _text(source.get("category")) or "system",
                "summary": _text(source.get("summary")),
                "permission": _text(source.get("permission")),
                "flags": [_text(flag) for flag in source.get("flags", []) if _text(flag)]
                if isinstance(source.get("flags"), list)
                else [],
                "schema": _text(source.get("schema")) or None,
            }
        )
    return tools


class RatsRuntime:
    """Own all RATS sessions for one long-lived Reverie CLI process."""

    def __init__(self, app_root: Optional[Path] = None, *, request_timeout: float = 3.0) -> None:
        self.app_root = Path(app_root or get_app_root()).resolve(strict=False)
        self.state_dir = self.app_root / ".reverie" / "rats"
        self.settings_path = self.state_dir / "settings.json"
        self.request_timeout = min(10.0, max(0.25, float(request_timeout)))
        self._sessions: Dict[str, _RatsSession] = {}
        self._generation = 0
        self._definition_signature = ""
        self._has_refreshed = False
        self._lock = threading.RLock()

    def _read_settings(self) -> Dict[str, Any]:
        try:
            source = _record(json.loads(self.settings_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError):
            source = {}
        enabled: Dict[str, Dict[str, Any]] = {}
        for item in source.get("enabledEngines", []) if isinstance(source.get("enabledEngines"), list) else []:
            record = _record(item)
            executable = _text(record.get("executable"))
            if not executable:
                continue
            path = Path(executable).expanduser().resolve(strict=False)
            enabled[_path_key(path)] = {
                "executable": str(path),
                "permissions": normalize_rats_permissions(record.get("permissions")),
            }
        return {
            "discoveryRoots": [str(path) for path in _unique_paths(source.get("discoveryRoots", []))],
            "enabledEngines": sorted(enabled.values(), key=lambda item: item["executable"].lower()),
        }

    def _write_settings(self, settings: Dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(f".tmp-{uuid.uuid4().hex}")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.settings_path)

    def _roots(self, settings: Dict[str, Any]) -> List[Path]:
        environment = _text(os.getenv("REVERIE_RATS_DISCOVERY_ROOTS"))
        environment_roots = environment.split(os.pathsep) if environment else []
        return _unique_paths([*environment_roots, *settings.get("discoveryRoots", [])])

    def _request(
        self,
        descriptor: RatsDescriptor,
        operation: str,
        args: Optional[Dict[str, Any]] = None,
        *,
        control_token: str = "",
        session_token: str = "",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        body = json.dumps(
            {"id": f"reverie-cli-{uuid.uuid4().hex}", "protocol": RATS_PROTOCOL, "op": operation, "args": args or {}},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body))}
        if control_token:
            headers["X-Reverie-RATS-Control"] = control_token
        if session_token:
            headers["X-Reverie-RTP-Session"] = session_token
        connection = http.client.HTTPConnection("127.0.0.1", descriptor.port, timeout=timeout or self.request_timeout)
        try:
            connection.request("POST", "/rtp", body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise RatsClientError(f"RATS {operation} failed: {exc}", code="transport_error") from exc
        finally:
            connection.close()
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise RatsClientError("RATS response exceeded the 1 MiB client limit.", code="response_too_large")
        try:
            payload = _record(json.loads(raw.decode("utf-8")))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RatsClientError("RATS returned malformed JSON.", status=response.status, code="malformed_response") from exc
        if payload.get("protocol") != RATS_PROTOCOL:
            raise RatsClientError("RATS protocol response did not match reverie.rtp/1.", status=response.status, code="protocol_mismatch")
        if response.status >= 400 or payload.get("ok") is not True:
            error = _record(payload.get("error"))
            raise RatsClientError(
                _text(error.get("message")) or f"RATS request failed with HTTP {response.status}.",
                status=response.status,
                code=_text(error.get("code")) or "request_failed",
            )
        return _record(payload.get("result"))

    def _selection(self, settings: Dict[str, Any], executable: Path | str) -> Optional[Dict[str, Any]]:
        key = _path_key(executable)
        return next((item for item in settings.get("enabledEngines", []) if _path_key(item.get("executable", "")) == key), None)

    def _close_session(self, session: _RatsSession, *, timeout: float = 0.75) -> None:
        try:
            self._request(session.descriptor, "session.close", session_token=session.token, timeout=timeout)
        except RatsClientError:
            pass

    def _describe_into_session(self, session: _RatsSession, names: Iterable[Any]) -> List[Dict[str, Any]]:
        requested = list(dict.fromkeys(_text(name) for name in names if _text(name)))[:16]
        if not requested:
            return []
        result = self._request(
            session.descriptor,
            "catalog.describe",
            {"names": requested},
            session_token=session.token,
        )
        definitions: List[Dict[str, Any]] = []
        for item in result.get("tools", []) if isinstance(result.get("tools"), list) else []:
            definition = _record(item)
            name = _text(definition.get("name"))
            request_schema = definition.get("request_schema")
            if name and isinstance(request_schema, dict):
                session.definitions[name] = definition
                definitions.append(dict(definition))
        self._update_generation()
        return definitions

    def _open_session(self, descriptor: RatsDescriptor, permissions: List[str]) -> _RatsSession:
        opened = self._request(
            descriptor,
            "session.open",
            {"client": "reverie-cli", "permissions": permissions},
            control_token=descriptor.control_token,
        )
        token = _text(opened.get("session_token")).lower()
        if not _TOKEN_RE.fullmatch(token):
            raise RatsClientError("RATS did not return a valid 256-bit session token.", code="invalid_session_token")
        index = self._request(descriptor, "catalog.index", session_token=token)
        session = _RatsSession(
            descriptor=descriptor,
            token=token,
            permissions=list(permissions),
            compact_tools=_compact_tools(index.get("tools")),
        )
        preload = [
            name
            for name in _DEFAULT_LOADED_TOOLS
            if any(tool.get("name") == name and tool.get("schema") for tool in session.compact_tools)
        ]
        if preload:
            self._describe_into_session(session, preload)
        return session

    def _service_record(
        self,
        descriptor: RatsDescriptor,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        selection = self._selection(settings, descriptor.executable)
        base = {
            "serviceId": descriptor.service_id,
            "product": descriptor.product,
            "productVersion": descriptor.product_version,
            "executable": str(descriptor.executable),
            "pid": descriptor.pid,
            "endpoint": descriptor.endpoint,
            "protocol": RATS_PROTOCOL,
            "descriptorPath": str(descriptor.descriptor_path),
            "catalogRevision": descriptor.catalog_revision,
            "nativeToolCount": descriptor.native_tool_count,
            "startedUtc": descriptor.started_utc,
            "enabled": selection is not None,
            "connection": "unreachable",
            "sessionActive": False,
            "permissions": normalize_rats_permissions(selection.get("permissions")) if selection else ["read"],
            "tools": [],
            "loadedToolNames": [],
            "error": "",
        }
        try:
            hello = self._request(descriptor, "hello")
            if hello.get("service_id") != descriptor.service_id or hello.get("protocol") != RATS_PROTOCOL:
                raise RatsClientError("RATS hello did not match its executable-local descriptor.", code="descriptor_mismatch")
            base["connection"] = "available"
            session = self._sessions.get(descriptor.service_id)
            if selection is None:
                if session is not None:
                    self._close_session(session)
                    self._sessions.pop(descriptor.service_id, None)
                    self._update_generation()
                return base
            permissions = normalize_rats_permissions(selection.get("permissions"))
            if session is not None and (
                session.permissions != permissions
                or _path_key(session.descriptor.executable) != _path_key(descriptor.executable)
                or session.descriptor.port != descriptor.port
            ):
                self._close_session(session)
                self._sessions.pop(descriptor.service_id, None)
                session = None
            if session is not None:
                try:
                    self._request(descriptor, "status", session_token=session.token)
                except RatsClientError:
                    self._sessions.pop(descriptor.service_id, None)
                    session = None
            if session is None:
                session = self._open_session(descriptor, permissions)
                self._sessions[descriptor.service_id] = session
                self._update_generation()
            base.update(
                {
                    "connection": "connected",
                    "sessionActive": True,
                    "permissions": list(session.permissions),
                    "tools": list(session.compact_tools),
                    "loadedToolNames": sorted(session.definitions),
                }
            )
        except RatsClientError as exc:
            self._sessions.pop(descriptor.service_id, None)
            base["error"] = str(exc)
            self._update_generation()
        return base

    def refresh(self) -> Dict[str, Any]:
        with self._lock:
            settings = self._read_settings()
            roots = self._roots(settings)
            descriptors = discover_rats_descriptors(roots)
            current_ids = {descriptor.service_id for descriptor in descriptors}
            for service_id in list(self._sessions):
                if service_id not in current_ids:
                    self._sessions.pop(service_id, None)
            services = [self._service_record(descriptor, settings) for descriptor in descriptors]
            self._has_refreshed = True
            self._update_generation()
            return {
                "protocol": RATS_PROTOCOL,
                "statePath": str(self.settings_path),
                "discoveryRoots": [str(path) for path in roots],
                "configuredDiscoveryRoots": list(settings["discoveryRoots"]),
                "enabledEngines": list(settings["enabledEngines"]),
                "services": services,
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    def add_engine(self, executable: Path | str) -> Dict[str, Any]:
        with self._lock:
            path = Path(executable).expanduser().resolve(strict=False)
            if not path.is_file():
                raise ValueError("Select an existing Reverie Engine executable.")
            settings = self._read_settings()
            settings["discoveryRoots"] = [
                str(item)
                for item in _unique_paths([*settings["discoveryRoots"], rats_discovery_root_for_executable(path)])
            ]
            self._write_settings(settings)
            return self.refresh()

    def remove_discovery_root(self, root: Path | str) -> Dict[str, Any]:
        with self._lock:
            key = _path_key(root)
            settings = self._read_settings()
            settings["discoveryRoots"] = [item for item in settings["discoveryRoots"] if _path_key(item) != key]
            self._write_settings(settings)
            return self.refresh()

    def set_engine_enabled(self, executable: Path | str, enabled: bool, permissions: Any) -> Dict[str, Any]:
        with self._lock:
            path = Path(executable).expanduser().resolve(strict=False)
            settings = self._read_settings()
            key = _path_key(path)
            settings["enabledEngines"] = [
                item for item in settings["enabledEngines"] if _path_key(item.get("executable", "")) != key
            ]
            if enabled:
                settings["enabledEngines"].append(
                    {"executable": str(path), "permissions": normalize_rats_permissions(permissions)}
                )
                settings["enabledEngines"].sort(key=lambda item: item["executable"].lower())
            self._write_settings(settings)
            return self.refresh()

    def describe(self, service_id: str, names: Iterable[Any]) -> List[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(_text(service_id))
            if session is None:
                raise ValueError("Enable the RATS service before requesting tool definitions.")
            return self._describe_into_session(session, names)

    def search(self, query: str, *, limit: int = 5, service_id: str = "", load: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            wanted = _text(query)
            if not wanted:
                raise ValueError("RATS search requires a non-empty query.")
            sessions = [self._sessions[service_id]] if service_id in self._sessions else list(self._sessions.values())
            matches: List[Dict[str, Any]] = []
            for session in sessions:
                result = self._request(
                    session.descriptor,
                    "catalog.search",
                    {"query": wanted, "limit": min(16, max(1, int(limit)))},
                    session_token=session.token,
                )
                local = [_record(item) for item in result.get("matches", []) if isinstance(item, dict)]
                if load:
                    describable = [
                        _text(item.get("name"))
                        for item in local
                        if any(tool.get("name") == _text(item.get("name")) and tool.get("schema") for tool in session.compact_tools)
                    ]
                    if describable:
                        self._describe_into_session(session, describable)
                for item in local:
                    item["serviceId"] = session.descriptor.service_id
                    item["executable"] = str(session.descriptor.executable)
                    matches.append(item)
            return sorted(matches, key=lambda item: (-int(item.get("score", 0) or 0), _text(item.get("name"))))[: max(1, int(limit))]

    def call_tool(self, service_id: str, tool_name: str, arguments: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
        with self._lock:
            session = self._sessions.get(_text(service_id))
            if session is None:
                raise RatsClientError("The selected RATS service is not connected.", code="session_unavailable")
            return self._request(
                session.descriptor,
                "tool.call",
                {"name": _text(tool_name), "arguments": _record(arguments), "dry_run": bool(dry_run)},
                session_token=session.token,
            )

    def compact_catalog(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows: List[Dict[str, Any]] = []
            for session in self._sessions.values():
                for tool in session.compact_tools:
                    rows.append(
                        {
                            **tool,
                            "serviceId": session.descriptor.service_id,
                            "product": session.descriptor.product,
                            "executable": str(session.descriptor.executable),
                            "loaded": tool.get("name") in session.definitions,
                        }
                    )
            return rows

    def _dynamic_name(self, session: _RatsSession, tool_name: str, used: set[str]) -> str:
        product = _safe_identifier(session.descriptor.product)
        base = f"rats_{product}_{_safe_identifier(tool_name)}"
        if len(base) > 64:
            digest = hashlib.sha1(f"{session.descriptor.executable}\0{tool_name}".encode("utf-8")).hexdigest()[:10]
            base = f"{base[:53].rstrip('_')}_{digest}"
        candidate = base
        if candidate in used:
            digest = hashlib.sha1(str(session.descriptor.executable).encode("utf-8")).hexdigest()[:8]
            candidate = f"{base[:55].rstrip('_')}_{digest}"
        return candidate

    def get_tool_definitions(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            if force_refresh or not self._has_refreshed:
                self.refresh()
            definitions: List[Dict[str, Any]] = []
            used: set[str] = set()
            for session in sorted(self._sessions.values(), key=lambda item: _path_key(item.descriptor.executable)):
                for tool_name, source in sorted(session.definitions.items()):
                    synthetic_name = self._dynamic_name(session, tool_name, used)
                    used.add(synthetic_name)
                    permission = _text(source.get("permission"))
                    definitions.append(
                        {
                            "name": synthetic_name,
                            "service_id": session.descriptor.service_id,
                            "engine_tool_name": tool_name,
                            "qualified_name": f"{session.descriptor.product}.{tool_name}",
                            "description": _text(source.get("summary")) or f"Native Reverie Engine tool {tool_name}.",
                            "parameters": dict(source.get("request_schema", {})),
                            "response_schema": dict(source.get("response_schema", {})),
                            "category": _text(source.get("category")) or "rats",
                            "tags": list(source.get("tags", [])) if isinstance(source.get("tags"), list) else [],
                            "permission": permission,
                            "read_only": permission in {"none", "read"},
                            "concurrency_safe": not bool(source.get("main_thread", False)),
                            "destructive": permission in {"edit", "asset", "run", "build"},
                            "supports_dry_run": bool(source.get("dry_run", False)),
                            "service_executable": str(session.descriptor.executable),
                        }
                    )
            return definitions

    def _update_generation(self) -> None:
        material = [
            (session.descriptor.service_id, sorted(session.definitions), session.permissions)
            for session in sorted(self._sessions.values(), key=lambda item: item.descriptor.service_id)
        ]
        signature = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if signature != self._definition_signature:
            self._definition_signature = signature
            self._generation += 1

    def get_generation(self) -> int:
        with self._lock:
            return self._generation

    def has_connected_services(self) -> bool:
        with self._lock:
            return bool(self._sessions)

    def shutdown(self) -> None:
        with self._lock:
            for session in list(self._sessions.values()):
                self._close_session(session)
            self._sessions.clear()
            self._update_generation()


__all__ = [
    "RATS_DISCOVERY_SCHEMA",
    "RATS_PERMISSIONS",
    "RATS_PROTOCOL",
    "RatsClientError",
    "RatsDescriptor",
    "RatsRuntime",
    "discover_rats_descriptors",
    "normalize_rats_permissions",
    "parse_rats_descriptor",
    "rats_discovery_root_for_executable",
]
