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
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from .config import get_app_root


RATS_PROTOCOL = "reverie.rtp/1"
RATS_DISCOVERY_SCHEMA = "reverie.rats.discovery/1"
RATS_SETTINGS_VERSION = 2
RATS_STATE_VERSION = 2
RATS_PERMISSIONS = ("read", "project", "edit", "asset", "ai", "run", "build")
_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVICE_RE = re.compile(r"^rats-[1-9][0-9]*-[a-z0-9]+$")
_IDENTIFIER_RE = re.compile(r"[^a-z0-9_-]+")
_MAX_DESCRIPTOR_BYTES = 128 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_DIAGNOSTIC_BYTES = 2 * 1024 * 1024
_MAX_DIAGNOSTIC_ENTRIES = 240
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


def normalize_rats_permissions(value: Any, provider: Optional["RatsProviderSpec"] = None) -> List[str]:
    requested = value if isinstance(value, (list, tuple, set)) else []
    allowed = set(provider.permission_classes if provider else RATS_PERMISSIONS)
    normalized = sorted({_text(item) for item in requested if _text(item) in allowed})
    return normalized or ["read"]


def rats_discovery_root_for_executable(executable: Path | str) -> Path:
    return Path(executable).expanduser().resolve(strict=False).parent / "ReverieLocal" / "RATS" / "Services"


def _existing_executable(executable: Path) -> bool:
    return executable.is_file()


@dataclass(frozen=True)
class RatsProviderSpec:
    """Immutable adapter metadata for one explicitly allowlisted RATS provider."""

    provider_id: str
    product: str
    service_kinds: Tuple[str, ...]
    executable_validator: Callable[[Path], bool]
    discovery_root_resolver: Callable[[Path], Path]
    permission_classes: Tuple[str, ...]
    label: str
    tool_tags: Tuple[str, ...] = ()
    executable_error: str = "Select an existing executable for this RATS provider."

    @property
    def service_kind(self) -> str:
        """Compatibility convenience for providers with one service kind."""
        return self.service_kinds[0] if len(self.service_kinds) == 1 else ""

    def accepts_service_kind(self, value: str) -> bool:
        return _text(value) in self.service_kinds

    def validate_executable(self, executable: Path) -> bool:
        try:
            return bool(self.executable_validator(executable))
        except (OSError, ValueError, TypeError):
            return False

    def discovery_root_for_executable(self, executable: Path | str) -> Path:
        return Path(self.discovery_root_resolver(Path(executable).expanduser().resolve(strict=False))).resolve(strict=False)


@dataclass(frozen=True)
class RatsProviderRegistry:
    """Read-only provider registry; tests may inject an additive fixture registry."""

    providers: Mapping[str, RatsProviderSpec]

    def __post_init__(self) -> None:
        object.__setattr__(self, "providers", MappingProxyType(dict(self.providers)))

    def __getitem__(self, provider_id: str) -> RatsProviderSpec:
        return self.providers[provider_id]

    def get(self, provider_id: str, default: Optional[RatsProviderSpec] = None) -> Optional[RatsProviderSpec]:
        return self.providers.get(provider_id, default)

    def items(self):
        return self.providers.items()

    def values(self):
        return self.providers.values()

    def __iter__(self):
        return iter(self.providers)

    def __len__(self) -> int:
        return len(self.providers)


RATS_SUPPORTED_PROVIDERS = RatsProviderRegistry(
    {
        "reverie.engine": RatsProviderSpec(
            provider_id="reverie.engine",
            product="Reverie Engine",
            service_kinds=("builtin",),
            executable_validator=_existing_executable,
            discovery_root_resolver=rats_discovery_root_for_executable,
            permission_classes=RATS_PERMISSIONS,
            label="Reverie Engine",
            tool_tags=("reverie-engine",),
            executable_error="Select an existing Reverie Engine executable.",
        ),
    }
)
# Canonical name for new integrations; the historical constant remains the public compatibility name.
RATS_PROVIDER_REGISTRY = RATS_SUPPORTED_PROVIDERS


def _safe_identifier(value: Any) -> str:
    normalized = _IDENTIFIER_RE.sub("_", _text(value).lower()).strip("_")
    return normalized or "tool"


@dataclass(frozen=True)
class RatsDescriptor:
    service_id: str
    provider_id: str
    service_kind: str
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


def _parse_rats_descriptor(
    value: Any,
    descriptor_path: Path | str,
    registry: RatsProviderRegistry = RATS_SUPPORTED_PROVIDERS,
) -> Tuple[Optional[RatsDescriptor], str]:
    source = _record(value)
    try:
        executable = Path(_text(source.get("executable"))).expanduser()
        service_id = _text(source.get("service_id"))
        pid = int(source.get("pid", 0))
        port = int(source.get("port", 0))
        native_tool_count = max(0, int(source.get("native_tool_count", 0) or 0))
    except (TypeError, ValueError, OSError):
        return None, "invalid_descriptor_fields"
    provider_id = _text(source.get("provider_id"))
    service_kind = _text(source.get("service_kind"))
    supported = registry.get(provider_id)
    endpoint = _text(source.get("endpoint"))
    control_token = _text(source.get("control_token")).lower()
    if source.get("schema") != RATS_DISCOVERY_SCHEMA:
        return None, "unsupported_discovery_schema"
    if source.get("protocol") != RATS_PROTOCOL:
        return None, "unsupported_protocol"
    if supported is None:
        return None, "unsupported_provider"
    if not supported.accepts_service_kind(service_kind):
        return None, "unsupported_service_kind"
    if _text(source.get("product")) != supported.product:
        return None, "provider_product_mismatch"
    if _text(source.get("bind_address")) != "127.0.0.1":
        return None, "non_loopback_endpoint"
    if not _SERVICE_RE.fullmatch(service_id):
        return None, "invalid_service_id"
    if not executable.is_absolute():
        return None, "invalid_executable_path"
    if not supported.validate_executable(executable):
        return None, "executable_validation_failed"
    if pid <= 0:
        return None, "invalid_process_id"
    if port <= 0 or port > 65535 or endpoint != f"http://127.0.0.1:{port}/rtp":
        return None, "invalid_endpoint"
    if not _TOKEN_RE.fullmatch(control_token):
        return None, "invalid_control_token"
    resolved_executable = executable.resolve(strict=False)
    resolved_descriptor = Path(descriptor_path).resolve(strict=False)
    if _path_key(resolved_descriptor.parent) != _path_key(
        supported.discovery_root_for_executable(resolved_executable)
    ):
        return None, "descriptor_outside_provider_root"
    return RatsDescriptor(
        service_id=service_id,
        provider_id=provider_id,
        service_kind=service_kind,
        product=_text(source.get("product")) or supported.product,
        product_version=_text(source.get("product_version")),
        executable=resolved_executable,
        pid=pid,
        port=port,
        endpoint=endpoint,
        descriptor_path=resolved_descriptor,
        catalog_revision=_text(source.get("catalog_revision")),
        native_tool_count=native_tool_count,
        started_utc=_text(source.get("started_utc")),
        control_token=control_token,
    ), ""


def parse_rats_descriptor(
    value: Any,
    descriptor_path: Path | str,
    registry: RatsProviderRegistry = RATS_SUPPORTED_PROVIDERS,
) -> Optional[RatsDescriptor]:
    descriptor, _reason = _parse_rats_descriptor(value, descriptor_path, registry)
    return descriptor


def discover_rats_descriptors(
    roots: Iterable[Path | str],
    rejections: Optional[List[Dict[str, str]]] = None,
    registry: RatsProviderRegistry = RATS_SUPPORTED_PROVIDERS,
) -> List[RatsDescriptor]:
    descriptors: Dict[tuple[str, str], RatsDescriptor] = {}
    for root in _unique_paths(roots):
        try:
            candidates = sorted(root.glob("rats-*.json"), key=lambda item: item.name.lower())
        except OSError:
            continue
        for candidate in candidates:
            try:
                if not candidate.is_file():
                    continue
                if candidate.stat().st_size > _MAX_DESCRIPTOR_BYTES:
                    if rejections is not None:
                        rejections.append({"path": str(candidate), "reason": "descriptor_too_large"})
                    continue
                descriptor, reason = _parse_rats_descriptor(
                    json.loads(candidate.read_text(encoding="utf-8")),
                    candidate,
                    registry,
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                if rejections is not None:
                    rejections.append({"path": str(candidate), "reason": "descriptor_unreadable"})
                continue
            if descriptor is not None:
                descriptors[(descriptor.service_id, _path_key(descriptor.descriptor_path))] = descriptor
            elif rejections is not None:
                rejections.append({"path": str(candidate), "reason": reason or "descriptor_rejected"})
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

    def __init__(
        self,
        app_root: Optional[Path] = None,
        *,
        provider_registry: RatsProviderRegistry = RATS_SUPPORTED_PROVIDERS,
        request_timeout: float = 1.5,
        probe_timeout: float = 0.35,
        tool_timeout: float = 12.0,
    ) -> None:
        self.app_root = Path(app_root or get_app_root()).resolve(strict=False)
        self.provider_registry = provider_registry
        self.state_dir = self.app_root / ".reverie" / "rats"
        self.settings_path = self.state_dir / "settings.json"
        self.diagnostics_path = self.state_dir / "diagnostics.jsonl"
        self.request_timeout = min(10.0, max(0.25, float(request_timeout)))
        self.probe_timeout = min(1.0, max(0.1, float(probe_timeout)))
        self.tool_timeout = min(60.0, max(1.0, float(tool_timeout)))
        self._sessions: Dict[Tuple[str, str], _RatsSession] = {}
        self._diagnostics: List[Dict[str, Any]] = self._load_diagnostics()
        self._generation = 0
        self._definition_signature = ""
        self._has_refreshed = False
        self._lock = threading.RLock()

    def _load_diagnostics(self) -> List[Dict[str, Any]]:
        try:
            lines = self.diagnostics_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        entries: List[Dict[str, Any]] = []
        for line in lines[-_MAX_DIAGNOSTIC_ENTRIES:]:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                entries.append(dict(value))
        return entries

    def _log_diagnostic(
        self,
        event: str,
        *,
        level: str = "info",
        service_id: str = "",
        provider_id: str = "",
        operation: str = "",
        reason: str = "",
        path: str = "",
        duration_ms: Optional[int] = None,
        count: Optional[int] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "timestampUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level if level in {"info", "warning", "error"} else "info",
            "event": _text(event),
        }
        optional = {
            "serviceId": _text(service_id),
            "providerId": _text(provider_id),
            "operation": _text(operation),
            "reason": _text(reason),
            "path": _text(path),
        }
        entry.update({key: value for key, value in optional.items() if value})
        if duration_ms is not None:
            entry["durationMs"] = max(0, int(duration_ms))
        if count is not None:
            entry["count"] = max(0, int(count))
        self._diagnostics.append(entry)
        self._diagnostics = self._diagnostics[-_MAX_DIAGNOSTIC_ENTRIES:]
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            if self.diagnostics_path.is_file() and self.diagnostics_path.stat().st_size > _MAX_DIAGNOSTIC_BYTES:
                retained = self.diagnostics_path.read_text(encoding="utf-8", errors="replace").splitlines()[-800:]
                temporary = self.diagnostics_path.with_suffix(f".tmp-{uuid.uuid4().hex}")
                temporary.write_text("\n".join(retained) + "\n", encoding="utf-8")
                os.replace(temporary, self.diagnostics_path)
            with self.diagnostics_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass

    def _read_settings(self) -> Dict[str, Any]:
        try:
            source = _record(json.loads(self.settings_path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError):
            source = {}
        raw_roots = source.get("discoveryRoots", [])
        roots = _unique_paths(raw_roots if isinstance(raw_roots, list) else [])
        legacy_items = source.get("enabledEngines") if isinstance(source.get("enabledEngines"), list) else []
        current_items = source.get("enabledProviders") if isinstance(source.get("enabledProviders"), list) else []
        migrating_legacy = bool(legacy_items) and not current_items
        source_items = current_items or legacy_items
        enabled: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for item in source_items:
            record = _record(item)
            executable = _text(record.get("executable"))
            if not executable:
                continue
            path = Path(executable).expanduser().resolve(strict=False)
            provider_id = _text(record.get("providerId") or record.get("provider_id"))
            if migrating_legacy:
                provider_id = "reverie.engine"
            provider = self.provider_registry.get(provider_id)
            if provider is None:
                self._log_diagnostic(
                    "settings.rejected",
                    level="warning",
                    provider_id=provider_id,
                    reason="unsupported_provider",
                )
                continue
            discovery_root = _text(record.get("discoveryRoot"))
            if discovery_root:
                discovery_path = _unique_paths([discovery_root])
                discovery_root = str(discovery_path[0]) if discovery_path else ""
            if not discovery_root:
                discovery_root = str(provider.discovery_root_for_executable(path))
            roots = _unique_paths([*roots, discovery_root])
            selection = {
                "providerId": provider_id,
                "executable": str(path),
                "permissions": normalize_rats_permissions(record.get("permissions"), provider),
                "discoveryRoot": discovery_root,
            }
            enabled[(provider_id, _path_key(path))] = selection
        settings = {
            "schemaVersion": RATS_SETTINGS_VERSION,
            "discoveryRoots": [str(path) for path in roots],
            "enabledProviders": sorted(
                enabled.values(),
                key=lambda item: (item["providerId"], item["executable"].lower()),
            ),
        }
        if source and (
            source.get("schemaVersion") != RATS_SETTINGS_VERSION
            or migrating_legacy
            or "enabledEngines" in source
            or source.get("enabledProviders") != settings["enabledProviders"]
            or source.get("discoveryRoots") != settings["discoveryRoots"]
        ):
            try:
                self._write_settings(settings)
            except OSError:
                pass
        return settings

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
        started = time.perf_counter()
        effective_timeout = float(timeout) if timeout is not None else self.request_timeout
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
        connection = http.client.HTTPConnection("127.0.0.1", descriptor.port, timeout=effective_timeout)
        try:
            connection.request("POST", "/rtp", body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            self._log_diagnostic(
                "rtp.request",
                level="warning",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                operation=operation,
                reason="transport_error",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            raise RatsClientError(f"RATS {operation} failed: {exc}", code="transport_error") from exc
        finally:
            connection.close()
        if len(raw) > _MAX_RESPONSE_BYTES:
            self._log_diagnostic(
                "rtp.request",
                level="error",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                operation=operation,
                reason="response_too_large",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            raise RatsClientError("RATS response exceeded the 1 MiB client limit.", code="response_too_large")
        try:
            payload = _record(json.loads(raw.decode("utf-8")))
        except (UnicodeError, json.JSONDecodeError) as exc:
            self._log_diagnostic(
                "rtp.request",
                level="error",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                operation=operation,
                reason="malformed_response",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            raise RatsClientError("RATS returned malformed JSON.", status=response.status, code="malformed_response") from exc
        if payload.get("protocol") != RATS_PROTOCOL:
            self._log_diagnostic(
                "rtp.request",
                level="error",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                operation=operation,
                reason="protocol_mismatch",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            raise RatsClientError("RATS protocol response did not match reverie.rtp/1.", status=response.status, code="protocol_mismatch")
        if response.status >= 400 or payload.get("ok") is not True:
            error = _record(payload.get("error"))
            error_code = _text(error.get("code")) or "request_failed"
            self._log_diagnostic(
                "rtp.request",
                level="warning",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                operation=operation,
                reason=error_code,
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            raise RatsClientError(
                _text(error.get("message")) or f"RATS request failed with HTTP {response.status}.",
                status=response.status,
                code=error_code,
            )
        self._log_diagnostic(
            "rtp.request",
            service_id=descriptor.service_id,
            provider_id=descriptor.provider_id,
            operation=operation,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return _record(payload.get("result"))

    def _selection(
        self,
        settings: Dict[str, Any],
        provider_id: str,
        executable: Path | str,
    ) -> Optional[Dict[str, Any]]:
        key = _path_key(executable)
        return next(
            (
                item
                for item in settings.get("enabledProviders", [])
                if _text(item.get("providerId")) == provider_id
                and _path_key(item.get("executable", "")) == key
            ),
            None,
        )

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
    ) -> Optional[Dict[str, Any]]:
        probe_started = time.perf_counter()
        try:
            hello = self._request(descriptor, "hello", timeout=self.probe_timeout)
        except RatsClientError:
            session = self._sessions.pop((descriptor.provider_id, descriptor.service_id), None)
            if session is not None:
                self._update_generation()
            return None
        expected_hello = {
            "service_id": descriptor.service_id,
            "protocol": RATS_PROTOCOL,
            "provider_id": descriptor.provider_id,
            "service_kind": descriptor.service_kind,
            "product": descriptor.product,
        }
        mismatched_field = next((key for key, value in expected_hello.items() if hello.get(key) != value), "")
        if mismatched_field:
            self._log_diagnostic(
                "provider.rejected",
                level="warning",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                reason=f"hello_{mismatched_field}_mismatch",
                duration_ms=round((time.perf_counter() - probe_started) * 1000),
            )
            session = self._sessions.pop((descriptor.provider_id, descriptor.service_id), None)
            if session is not None:
                self._update_generation()
            return None

        probe_latency_ms = round((time.perf_counter() - probe_started) * 1000)
        selection = self._selection(settings, descriptor.provider_id, descriptor.executable)
        base = {
            "serviceId": descriptor.service_id,
            "providerId": descriptor.provider_id,
            "serviceKind": descriptor.service_kind,
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
            "probeLatencyMs": probe_latency_ms,
            "enabled": selection is not None,
            "connection": "available",
            "sessionActive": False,
            "permissions": normalize_rats_permissions(selection.get("permissions")) if selection else ["read"],
            "tools": [],
            "loadedToolNames": [],
            "error": "",
        }
        try:
            session_key = (descriptor.provider_id, descriptor.service_id)
            session = self._sessions.get(session_key)
            if selection is None:
                if session is not None:
                    self._close_session(session)
                    self._sessions.pop(session_key, None)
                    self._update_generation()
                return base
            permissions = normalize_rats_permissions(selection.get("permissions"))
            if session is not None and (
                session.permissions != permissions
                or _path_key(session.descriptor.executable) != _path_key(descriptor.executable)
                or session.descriptor.port != descriptor.port
            ):
                self._close_session(session)
                self._sessions.pop(session_key, None)
                session = None
            if session is not None:
                try:
                    self._request(descriptor, "status", session_token=session.token)
                except RatsClientError:
                    self._sessions.pop(session_key, None)
                    session = None
            if session is None:
                session = self._open_session(descriptor, permissions)
                self._sessions[session_key] = session
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
            self._sessions.pop((descriptor.provider_id, descriptor.service_id), None)
            base["error"] = str(exc)
            self._update_generation()
        return base

    def refresh(self) -> Dict[str, Any]:
        with self._lock:
            started = time.perf_counter()
            settings = self._read_settings()
            roots = self._roots(settings)
            rejections: List[Dict[str, str]] = []
            for root in roots:
                if not root.is_dir():
                    self._log_diagnostic(
                        "discovery.root_missing",
                        level="warning",
                        reason="directory_not_found",
                        path=str(root),
                    )
            descriptors = discover_rats_descriptors(roots, rejections, self.provider_registry)
            for rejection in rejections:
                self._log_diagnostic(
                    "discovery.rejected",
                    level="warning",
                    reason=rejection.get("reason", "descriptor_rejected"),
                    path=rejection.get("path", ""),
                )
            services = []
            for descriptor in descriptors:
                service = self._service_record(descriptor, settings)
                if service is not None:
                    services.append(service)
            current_ids = {(service["providerId"], service["serviceId"]) for service in services}
            for session_key in list(self._sessions):
                if session_key not in current_ids:
                    self._sessions.pop(session_key, None)
            self._has_refreshed = True
            self._update_generation()
            scan_duration_ms = round((time.perf_counter() - started) * 1000)
            self._log_diagnostic(
                "discovery.complete",
                duration_ms=scan_duration_ms,
                count=len(services),
            )
            return {
                "protocol": RATS_PROTOCOL,
                "stateVersion": RATS_STATE_VERSION,
                "settingsVersion": RATS_SETTINGS_VERSION,
                "statePath": str(self.settings_path),
                "diagnosticsPath": str(self.diagnostics_path),
                "discoveryRoots": [str(path) for path in roots],
                "configuredDiscoveryRoots": list(settings["discoveryRoots"]),
                "enabledProviders": list(settings["enabledProviders"]),
                # Deprecated compatibility view for packaged Desktop clients.
                "enabledEngines": [
                    {
                        "executable": item["executable"],
                        "permissions": list(item["permissions"]),
                    }
                    for item in settings["enabledProviders"]
                    if item.get("providerId") == "reverie.engine"
                ],
                "supportedProviders": [
                    {
                        "providerId": provider_id,
                        "product": provider.product,
                        "serviceKind": provider.service_kind,
                        "label": provider.label,
                        "permissions": list(provider.permission_classes),
                        "toolTags": list(provider.tool_tags),
                    }
                    for provider_id, provider in sorted(self.provider_registry.items())
                ],
                "services": services,
                "scanDurationMs": scan_duration_ms,
                "rejectedDescriptorCount": len(rejections),
                "diagnostics": list(self._diagnostics[-160:]),
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    def _provider(self, provider_id: str) -> RatsProviderSpec:
        normalized = _text(provider_id)
        provider = self.provider_registry.get(normalized)
        if provider is None:
            raise ValueError(f"Unsupported RATS provider: {normalized or 'unknown'}")
        return provider

    def register_provider_executable(self, provider_id: str, executable: Path | str) -> Dict[str, Any]:
        with self._lock:
            provider = self._provider(provider_id)
            path = Path(executable).expanduser().resolve(strict=False)
            if not provider.validate_executable(path):
                raise ValueError(provider.executable_error)
            settings = self._read_settings()
            settings["discoveryRoots"] = [
                str(item)
                for item in _unique_paths(
                    [*settings["discoveryRoots"], provider.discovery_root_for_executable(path)]
                )
            ]
            self._write_settings(settings)
            return self.refresh()

    # Compatibility alias: remove after packaged Desktop clients use ratsRegisterProvider.
    def add_engine(self, executable: Path | str) -> Dict[str, Any]:
        return self.register_provider_executable("reverie.engine", executable)

    def remove_discovery_root(self, root: Path | str) -> Dict[str, Any]:
        with self._lock:
            key = _path_key(root)
            settings = self._read_settings()
            settings["discoveryRoots"] = [item for item in settings["discoveryRoots"] if _path_key(item) != key]
            self._write_settings(settings)
            return self.refresh()

    def set_provider_enabled(
        self,
        provider_id: str,
        executable: Path | str,
        enabled: bool,
        permissions: Any,
    ) -> Dict[str, Any]:
        with self._lock:
            provider = self._provider(provider_id)
            path = Path(executable).expanduser().resolve(strict=False)
            settings = self._read_settings()
            key = _path_key(path)
            settings["enabledProviders"] = [
                item
                for item in settings["enabledProviders"]
                if not (
                    _text(item.get("providerId")) == provider.provider_id
                    and _path_key(item.get("executable", "")) == key
                )
            ]
            if enabled:
                discovery_root = str(provider.discovery_root_for_executable(path))
                settings["discoveryRoots"] = [
                    str(item) for item in _unique_paths([*settings["discoveryRoots"], discovery_root])
                ]
                settings["enabledProviders"].append(
                    {
                        "providerId": provider.provider_id,
                        "executable": str(path),
                        "permissions": normalize_rats_permissions(permissions, provider),
                        "discoveryRoot": discovery_root,
                    }
                )
                settings["enabledProviders"].sort(
                    key=lambda item: (item["providerId"], item["executable"].lower())
                )
            self._write_settings(settings)
            return self.refresh()

    # Compatibility alias: remove after packaged Desktop clients use ratsSetProviderEnabled.
    def set_engine_enabled(self, executable: Path | str, enabled: bool, permissions: Any) -> Dict[str, Any]:
        return self.set_provider_enabled("reverie.engine", executable, enabled, permissions)

    def describe(
        self,
        service_id: str,
        names: Iterable[Any],
        *,
        provider_id: str = "",
    ) -> List[Dict[str, Any]]:
        with self._lock:
            session = self._find_session(service_id, provider_id)
            if session is None:
                raise ValueError("Enable the RATS service before requesting tool definitions.")
            return self._describe_into_session(session, names)

    def _find_session(self, service_id: str, provider_id: str = "") -> Optional[_RatsSession]:
        normalized_service_id = _text(service_id)
        normalized_provider_id = _text(provider_id)
        if normalized_provider_id:
            return self._sessions.get((normalized_provider_id, normalized_service_id))
        matches = [
            session
            for (session_provider_id, session_key), session in self._sessions.items()
            if session_key == normalized_service_id
        ]
        return matches[0] if len(matches) == 1 else None

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        service_id: str = "",
        provider_id: str = "",
        load: bool = True,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            wanted = _text(query)
            if not wanted:
                raise ValueError("RATS search requires a non-empty query.")
            selected = self._find_session(service_id, provider_id) if service_id else None
            if service_id and selected is None:
                sessions = []
            elif provider_id:
                sessions = [
                    session
                    for (session_provider_id, _service_id), session in self._sessions.items()
                    if session_provider_id == provider_id
                ]
            else:
                sessions = [selected] if selected is not None else list(self._sessions.values())
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
                    item["providerId"] = session.descriptor.provider_id
                    item["serviceId"] = session.descriptor.service_id
                    item["nativeToolName"] = _text(item.get("name"))
                    item["qualifiedName"] = (
                        f"{session.descriptor.provider_id}.{session.descriptor.service_id}.{_text(item.get('name'))}"
                    )
                    item["executable"] = str(session.descriptor.executable)
                    matches.append(item)
            return sorted(matches, key=lambda item: (-int(item.get("score", 0) or 0), _text(item.get("name"))))[: max(1, int(limit))]

    def call_tool(
        self,
        service_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        provider_id: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            session = self._find_session(service_id, provider_id)
            if session is None:
                raise RatsClientError("The selected RATS service is not connected.", code="session_unavailable")
            return self._request(
                session.descriptor,
                "tool.call",
                {"name": _text(tool_name), "arguments": _record(arguments), "dry_run": bool(dry_run)},
                session_token=session.token,
                timeout=self.tool_timeout,
            )

    def compact_catalog(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows: List[Dict[str, Any]] = []
            for session in self._sessions.values():
                for tool in session.compact_tools:
                    rows.append(
                        {
                            **tool,
                            "providerId": session.descriptor.provider_id,
                            "serviceId": session.descriptor.service_id,
                            "nativeToolName": tool.get("name"),
                            "qualifiedName": f"{session.descriptor.provider_id}.{session.descriptor.service_id}.{tool.get('name')}",
                            "product": session.descriptor.product,
                            "executable": str(session.descriptor.executable),
                            "loaded": tool.get("name") in session.definitions,
                        }
                    )
            return rows

    def _dynamic_name(self, session: _RatsSession, tool_name: str, used: set[str]) -> str:
        provider = _safe_identifier(session.descriptor.provider_id)
        base = f"rats_{provider}_{_safe_identifier(tool_name)}"
        if len(base) > 64:
            digest = hashlib.sha1(
                f"{session.descriptor.provider_id}\0{session.descriptor.service_id}\0{tool_name}".encode("utf-8")
            ).hexdigest()[:10]
            base = f"{base[:53].rstrip('_')}_{digest}"
        candidate = base
        if candidate in used:
            digest = hashlib.sha1(
                f"{session.descriptor.provider_id}\0{session.descriptor.service_id}\0{session.descriptor.executable}\0{tool_name}".encode("utf-8")
            ).hexdigest()[:8]
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
                    provider = self.provider_registry.get(session.descriptor.provider_id)
                    provider_tags = list(provider.tool_tags) if provider else []
                    source_tags = list(source.get("tags", [])) if isinstance(source.get("tags"), list) else []
                    tags = list(dict.fromkeys([*source_tags, "rats", "rtp", *provider_tags]))
                    qualified_name = (
                        f"{session.descriptor.provider_id}.{session.descriptor.service_id}.{tool_name}"
                    )
                    definitions.append(
                        {
                            "name": synthetic_name,
                            "provider_id": session.descriptor.provider_id,
                            "service_id": session.descriptor.service_id,
                            "native_tool_name": tool_name,
                            "qualified_name": qualified_name,
                            "description": _text(source.get("summary")) or f"Native RATS provider tool {tool_name}.",
                            "parameters": dict(source.get("request_schema", {})),
                            "response_schema": dict(source.get("response_schema", {})),
                            "category": _text(source.get("category")) or "rats",
                            "tags": tags,
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
            for session in sorted(
                self._sessions.values(),
                key=lambda item: (item.descriptor.provider_id, item.descriptor.service_id),
            )
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
    "RATS_PROVIDER_REGISTRY",
    "RATS_SETTINGS_VERSION",
    "RATS_STATE_VERSION",
    "RATS_SUPPORTED_PROVIDERS",
    "RatsClientError",
    "RatsDescriptor",
    "RatsProviderRegistry",
    "RatsProviderSpec",
    "RatsRuntime",
    "discover_rats_descriptors",
    "normalize_rats_permissions",
    "parse_rats_descriptor",
    "rats_discovery_root_for_executable",
]
