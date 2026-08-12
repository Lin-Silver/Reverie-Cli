"""Executable-local Reverie Agentic Tool-protocol client runtime."""

from __future__ import annotations

import copy
import ctypes
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
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVICE_RE = re.compile(r"^rats-[1-9][0-9]*-[a-z0-9]+$")
_IDENTIFIER_RE = re.compile(r"[^a-z0-9_-]+")
_MAX_DESCRIPTOR_BYTES = 128 * 1024
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_DIAGNOSTIC_BYTES = 2 * 1024 * 1024
_MAX_DIAGNOSTIC_ENTRIES = 240
_MAX_TERMINAL_TASK_HISTORY_PER_SESSION = 64
_DEFAULT_LOADED_TOOLS = ("ping", "version", "get_status", "project.status")
_REVERIE_ENGINE_PRODUCT_NAMES = frozenset({"Reverie Engine", "Reverie Engine (Console)"})
_REVERIE_ENGINE_TERMINAL_PRODUCT_NAME = "Reverie Engine Terminal"
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x00000102
_MAX_WINDOWS_PROCESS_ID = 0xFFFFFFFF
_MAX_WINDOWS_PROCESS_PATH = 32768
_TERMINAL_TASK_STATES = frozenset(
    {
        "cancelled",
        "canceled",
        "completed",
        "error",
        "failed",
        "killed",
        "stopped",
        "succeeded",
        "success",
        "timed_out",
        "timeout",
    }
)


class RatsClientError(RuntimeError):
    """Structured failure returned by or detected around an RTP service."""

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        code: str = "request_failed",
        audit_id: str = "",
        result_sha256: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = int(status)
        self.code = str(code or "request_failed")
        self.audit_id = str(audit_id or "")
        self.result_sha256 = str(result_sha256 or "")
        self.retryable = bool(retryable)


def _record(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_rtp_value_sha256(source: str, field: str) -> str:
    """Hash one canonical top-level value emitted by Engine JSON::stringify.

    Engine hashes ``result`` or ``error`` separately, then embeds that value in
    an envelope using the same compact, sorted serializer. Hashing the exact
    value span preserves Engine-specific float formatting. This is an audit
    consistency check, not an authentication mechanism.
    """
    decoder = json.JSONDecoder()
    length = len(source)
    index = 0
    while index < length and source[index].isspace():
        index += 1
    if index >= length or source[index] != "{":
        return ""
    index += 1
    matched = ""
    while index < length:
        while index < length and source[index].isspace():
            index += 1
        if index < length and source[index] == "}":
            break
        try:
            key, index = decoder.raw_decode(source, index)
        except json.JSONDecodeError:
            return ""
        if not isinstance(key, str):
            return ""
        while index < length and source[index].isspace():
            index += 1
        if index >= length or source[index] != ":":
            return ""
        index += 1
        while index < length and source[index].isspace():
            index += 1
        value_start = index
        try:
            _value, index = decoder.raw_decode(source, index)
        except json.JSONDecodeError:
            return ""
        if key == field:
            matched = source[value_start:index]
        while index < length and source[index].isspace():
            index += 1
        if index < length and source[index] == ",":
            index += 1
            continue
        if index < length and source[index] == "}":
            break
        return ""
    if not matched:
        return ""
    return hashlib.sha256(matched.encode("utf-8")).hexdigest()


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


def _windows_product_names(executable: Path) -> Tuple[str, ...]:
    if os.name != "nt" or not executable.is_file():
        return ()
    try:
        from ctypes import wintypes

        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.UINT),
        ]
        version.VerQueryValueW.restype = wintypes.BOOL

        ignored = wintypes.DWORD()
        size = version.GetFileVersionInfoSizeW(str(executable), ctypes.byref(ignored))
        if not size:
            return ()
        version_info = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(executable), 0, size, version_info):
            return ()

        translation_pointer = ctypes.c_void_p()
        translation_size = wintypes.UINT()
        if not version.VerQueryValueW(
            version_info,
            r"\VarFileInfo\Translation",
            ctypes.byref(translation_pointer),
            ctypes.byref(translation_size),
        ):
            return ()
        if not translation_pointer.value or translation_size.value < 4:
            return ()

        translations = ctypes.cast(translation_pointer, ctypes.POINTER(wintypes.WORD))
        product_names: List[str] = []
        for index in range(translation_size.value // 4):
            language = translations[index * 2]
            code_page = translations[index * 2 + 1]
            product_pointer = ctypes.c_void_p()
            product_length = wintypes.UINT()
            query = f"\\StringFileInfo\\{language:04x}{code_page:04x}\\ProductName"
            if not version.VerQueryValueW(
                version_info,
                query,
                ctypes.byref(product_pointer),
                ctypes.byref(product_length),
            ):
                continue
            if not product_pointer.value or not product_length.value:
                continue
            product_name = ctypes.wstring_at(product_pointer.value, product_length.value).rstrip("\0")
            if product_name and product_name not in product_names:
                product_names.append(product_name)
        return tuple(product_names)
    except (AttributeError, OSError, OverflowError, TypeError, ValueError):
        return ()


def _reverie_engine_executable(executable: Path) -> bool:
    if os.name != "nt":
        return executable.is_file()
    return any(product_name in _REVERIE_ENGINE_PRODUCT_NAMES for product_name in _windows_product_names(executable))


def _identity_executable(executable: Path) -> Path:
    return executable


def _reverie_engine_provider_executable(executable: Path) -> Path:
    candidate = executable.expanduser().resolve(strict=False)
    if os.name != "nt" or not candidate.name.lower().endswith(".terminal.exe"):
        return candidate
    if _REVERIE_ENGINE_TERMINAL_PRODUCT_NAME not in _windows_product_names(candidate):
        return candidate
    provider = candidate.with_name(candidate.name[: -len(".terminal.exe")] + ".exe")
    return provider if _reverie_engine_executable(provider) else candidate


def _windows_process_image_from_handle(process: int) -> Optional[Path]:
    if os.name != "nt" or not process:
        return None
    try:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD

        if kernel32.WaitForSingleObject(process, 0) != _WAIT_TIMEOUT:
            return None
        image = ctypes.create_unicode_buffer(_MAX_WINDOWS_PROCESS_PATH)
        image_length = wintypes.DWORD(len(image))
        if not kernel32.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(image_length)):
            return None
        if kernel32.WaitForSingleObject(process, 0) != _WAIT_TIMEOUT:
            return None
        return Path(image.value).resolve(strict=False)
    except (AttributeError, OSError, OverflowError, TypeError, ValueError):
        return None


def _windows_process_image(pid: int) -> Optional[Path]:
    if os.name != "nt" or pid <= 0 or pid > _MAX_WINDOWS_PROCESS_ID:
        return None
    try:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        process = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, pid)
        if not process:
            return None
        try:
            return _windows_process_image_from_handle(process)
        finally:
            kernel32.CloseHandle(process)
    except (AttributeError, OSError, OverflowError, TypeError, ValueError):
        return None


def _same_executable(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (OSError, ValueError):
        return _path_key(left) == _path_key(right)


def _windows_process_matches_executable(pid: int, executable: Path) -> bool:
    process_image = _windows_process_image(pid)
    return process_image is not None and _same_executable(process_image, executable)


def _reverie_engine_process(pid: int, executable: Path) -> bool:
    if os.name == "nt":
        return _windows_process_matches_executable(pid, executable)
    if pid <= 0 or not executable.is_file():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
    process_validator: Callable[[int, Path], bool] = _reverie_engine_process
    executable_normalizer: Callable[[Path], Path] = _identity_executable

    @property
    def service_kind(self) -> str:
        """Compatibility convenience for providers with one service kind."""
        return self.service_kinds[0] if len(self.service_kinds) == 1 else ""

    def accepts_service_kind(self, value: str) -> bool:
        return _text(value) in self.service_kinds

    def validate_executable(self, executable: Path) -> bool:
        try:
            return bool(self.executable_validator(self.normalize_executable(executable)))
        except (OSError, OverflowError, ValueError, TypeError):
            return False

    def validate_process(self, pid: int, executable: Path) -> bool:
        try:
            return bool(self.process_validator(int(pid), self.normalize_executable(executable)))
        except (OSError, OverflowError, ValueError, TypeError):
            return False

    def discovery_root_for_executable(self, executable: Path | str) -> Path:
        return Path(self.discovery_root_resolver(self.normalize_executable(Path(executable)))).resolve(strict=False)

    def normalize_executable(self, executable: Path | str) -> Path:
        return Path(self.executable_normalizer(Path(executable))).expanduser().resolve(strict=False)


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
            executable_validator=_reverie_engine_executable,
            process_validator=_reverie_engine_process,
            discovery_root_resolver=rats_discovery_root_for_executable,
            permission_classes=RATS_PERMISSIONS,
            label="Reverie Engine",
            tool_tags=("reverie-engine",),
            executable_error="Select an existing Reverie Engine executable.",
            executable_normalizer=_reverie_engine_provider_executable,
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
    io_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)


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
    if not supported.validate_process(pid, resolved_executable):
        return None, "process_executable_mismatch"
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
        self._closed = False
        self._tasks: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        # Lock order: lifecycle -> session I/O -> state. Diagnostics is a leaf lock.
        # Never wait for lifecycle or session I/O while holding the state lock.
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._diagnostics_lock = threading.Lock()

    @staticmethod
    def _validate_deadline(deadline_ms: Optional[int]) -> Optional[int]:
        if deadline_ms is None:
            return None
        if isinstance(deadline_ms, bool) or not isinstance(deadline_ms, int) or deadline_ms < 0 or deadline_ms > 120_000:
            raise ValueError("RTP deadline_ms must be an integer between 0 and 120000.")
        return int(deadline_ms)

    @staticmethod
    def _validate_idempotency_key(value: str) -> str:
        key = _text(value)
        if len(key) > 128 or "\n" in key or "\r" in key:
            raise ValueError("RTP idempotency_key must be at most 128 characters and contain no line breaks.")
        return key

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
        audit_id: str = "",
        result_sha256: str = "",
        task_id: str = "",
        cursor: Optional[int] = None,
        task_state: str = "",
        progress: Optional[float] = None,
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
        if _text(audit_id):
            entry["auditId"] = _text(audit_id)
        if _text(result_sha256):
            entry["resultSha256"] = _text(result_sha256)
        if _text(task_id):
            entry["taskId"] = _text(task_id)
        if cursor is not None:
            entry["cursor"] = max(0, int(cursor))
        if _text(task_state):
            entry["taskState"] = _text(task_state)
        if progress is not None:
            entry["progress"] = max(0.0, min(1.0, float(progress)))
        with self._diagnostics_lock:
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
            path = provider.normalize_executable(executable)
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
        deadline_ms: Optional[int] = None,
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        effective_timeout = float(timeout) if timeout is not None else self.request_timeout
        validated_deadline = self._validate_deadline(deadline_ms)
        validated_idempotency_key = self._validate_idempotency_key(idempotency_key)
        request_object: Dict[str, Any] = {
            "id": f"reverie-cli-{uuid.uuid4().hex}",
            "protocol": RATS_PROTOCOL,
            "op": operation,
            "args": args or {},
        }
        if validated_deadline is not None:
            request_object["deadline_ms"] = validated_deadline
        if validated_idempotency_key:
            request_object["idempotency_key"] = validated_idempotency_key
        body = json.dumps(
            request_object,
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
                task_id=_text((args or {}).get("task_id")) if isinstance(args, dict) else "",
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
            response_text = raw.decode("utf-8")
            payload = _record(json.loads(response_text))
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
        request_task_id = _text((args or {}).get("task_id")) if isinstance(args, dict) else ""

        def reject_response(code: str, message: str) -> None:
            self._log_diagnostic(
                "rtp.request",
                level="error",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                operation=operation,
                reason=code,
                duration_ms=round((time.perf_counter() - started) * 1000),
                task_id=request_task_id,
            )
            raise RatsClientError(message, status=response.status, code=code)

        if payload.get("protocol") != RATS_PROTOCOL:
            reject_response("protocol_mismatch", "RATS protocol response did not match reverie.rtp/1.")
        response_id = payload.get("id")
        if response_id is None or response_id == "":
            reject_response("response_id_missing", "RATS response did not include the request id.")
        if response_id != request_object["id"]:
            reject_response("response_id_mismatch", "RATS response id did not match the request id.")

        response_failed = response.status >= 400 or payload.get("ok") is not True
        result_sha256 = _text(payload.get("result_sha256")).lower()
        if not result_sha256:
            reject_response("result_hash_missing", "RATS response did not include the result SHA-256 audit value.")
        hash_field = "error" if response_failed else "result"
        expected_sha256 = _canonical_rtp_value_sha256(response_text, hash_field)
        if not _SHA256_RE.fullmatch(result_sha256) or not expected_sha256 or result_sha256 != expected_sha256:
            reject_response(
                "result_hash_mismatch",
                f"RATS response {hash_field} did not match its SHA-256 audit value.",
            )

        if response_failed:
            error = _record(payload.get("error"))
            error_code = _text(error.get("code")) or "request_failed"
            audit_id = _text(payload.get("audit_id"))
            self._log_diagnostic(
                "rtp.request",
                level="warning",
                service_id=descriptor.service_id,
                provider_id=descriptor.provider_id,
                operation=operation,
                reason=error_code,
                duration_ms=round((time.perf_counter() - started) * 1000),
                audit_id=audit_id,
                result_sha256=result_sha256,
                task_id=request_task_id,
            )
            raise RatsClientError(
                _text(error.get("message")) or f"RATS request failed with HTTP {response.status}.",
                status=response.status,
                code=error_code,
                audit_id=audit_id,
                result_sha256=result_sha256,
                retryable=bool(error.get("retryable", False)),
            )
        result = _record(payload.get("result"))
        task = _record(result.get("task"))
        task_id = _text(task.get("task_id")) or request_task_id
        next_cursor = result.get("next_cursor")
        self._log_diagnostic(
            "rtp.request",
            service_id=descriptor.service_id,
            provider_id=descriptor.provider_id,
            operation=operation,
            duration_ms=round((time.perf_counter() - started) * 1000),
            audit_id=_text(payload.get("audit_id")),
            result_sha256=result_sha256,
            task_id=task_id,
            cursor=int(next_cursor) if isinstance(next_cursor, int) and not isinstance(next_cursor, bool) else None,
            task_state=_text(result.get("state")),
            progress=float(result.get("progress")) if isinstance(result.get("progress"), (int, float)) else None,
        )
        return result

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
        """Populate a provisional session before it is published in ``_sessions``."""
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
        session = _RatsSession(
            descriptor=descriptor,
            token=token,
            permissions=list(permissions),
        )
        try:
            index = self._request(descriptor, "catalog.index", session_token=token)
            session.compact_tools = _compact_tools(index.get("tools"))
            preload = [
                name
                for name in _DEFAULT_LOADED_TOOLS
                if any(tool.get("name") == name and tool.get("schema") for tool in session.compact_tools)
            ]
            if preload:
                self._describe_into_session(session, preload)
            return session
        except RatsClientError:
            self._close_session(session)
            raise

    def _detach_session(self, session: _RatsSession) -> bool:
        session_key = (session.descriptor.provider_id, session.descriptor.service_id)
        with self._lock:
            if self._sessions.get(session_key) is not session:
                return False
            self._sessions.pop(session_key, None)
            self._drop_tasks_for_session(session)
            self._update_generation()
            return True

    def _service_record(
        self,
        descriptor: RatsDescriptor,
        settings: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        session_key = (descriptor.provider_id, descriptor.service_id)
        locked_session: Optional[_RatsSession] = None
        while True:
            with self._lock:
                session = self._sessions.get(session_key)
            if session is None:
                break
            session.io_lock.acquire()
            with self._lock:
                if self._sessions.get(session_key) is session:
                    locked_session = session
                    break
            session.io_lock.release()

        probe_started = time.perf_counter()
        try:
            try:
                hello = self._request(descriptor, "hello", timeout=self.probe_timeout)
            except RatsClientError:
                if session is not None and self._detach_session(session):
                    self._close_session(session)
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
                if session is not None and self._detach_session(session):
                    self._close_session(session)
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
            if selection is None:
                if session is not None and self._detach_session(session):
                    self._close_session(session)
                return base

            permissions = normalize_rats_permissions(selection.get("permissions"))
            if session is not None and (
                session.permissions != permissions
                or _path_key(session.descriptor.executable) != _path_key(descriptor.executable)
                or session.descriptor.port != descriptor.port
            ):
                if self._detach_session(session):
                    self._close_session(session)
                session = None
            if session is not None:
                try:
                    self._request(descriptor, "status", session_token=session.token)
                except RatsClientError:
                    if self._detach_session(session):
                        self._close_session(session)
                    session = None
            if session is None:
                try:
                    provisional = self._open_session(descriptor, permissions)
                except RatsClientError as exc:
                    with self._lock:
                        if self._sessions.get(session_key) is None:
                            self._drop_tasks_for_key(*session_key)
                    base["error"] = str(exc)
                    return base
                with self._lock:
                    published = not self._closed and self._sessions.get(session_key) is None
                    if published:
                        self._sessions[session_key] = provisional
                        self._update_generation()
                if not published:
                    self._close_session(provisional)
                    base["error"] = "RATS session changed while it was being opened."
                    return base
                session = provisional
            base.update(
                {
                    "connection": "connected",
                    "sessionActive": True,
                    "permissions": list(session.permissions),
                    "tools": list(session.compact_tools),
                    "loadedToolNames": sorted(session.definitions),
                }
            )
            return base
        finally:
            if locked_session is not None:
                locked_session.io_lock.release()

    def _ensure_open(self) -> None:
        with self._lock:
            if self._closed:
                raise RatsClientError("The RATS runtime has been shut down.", code="runtime_closed")

    def _refresh_lifecycle(self) -> Dict[str, Any]:
        self._ensure_open()
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
        with self._lock:
            stale_sessions = [
                session
                for session_key, session in self._sessions.items()
                if session_key not in current_ids
            ]
            for session in stale_sessions:
                self._sessions.pop((session.descriptor.provider_id, session.descriptor.service_id), None)
                self._drop_tasks_for_session(session)
            self._has_refreshed = True
            self._update_generation()
        for session in stale_sessions:
            with session.io_lock:
                self._close_session(session)

        scan_duration_ms = round((time.perf_counter() - started) * 1000)
        self._log_diagnostic(
            "discovery.complete",
            duration_ms=scan_duration_ms,
            count=len(services),
        )
        with self._diagnostics_lock:
            diagnostics = list(self._diagnostics[-160:])
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
            "diagnostics": diagnostics,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def refresh(self) -> Dict[str, Any]:
        with self._lifecycle_lock:
            return self._refresh_lifecycle()

    def _provider(self, provider_id: str) -> RatsProviderSpec:
        normalized = _text(provider_id)
        provider = self.provider_registry.get(normalized)
        if provider is None:
            raise ValueError(f"Unsupported RATS provider: {normalized or 'unknown'}")
        return provider

    def register_provider_executable(self, provider_id: str, executable: Path | str) -> Dict[str, Any]:
        with self._lifecycle_lock:
            self._ensure_open()
            provider = self._provider(provider_id)
            path = provider.normalize_executable(executable)
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
            return self._refresh_lifecycle()

    # Compatibility alias: remove after packaged Desktop clients use ratsRegisterProvider.
    def add_engine(self, executable: Path | str) -> Dict[str, Any]:
        return self.register_provider_executable("reverie.engine", executable)

    def remove_discovery_root(self, root: Path | str) -> Dict[str, Any]:
        with self._lifecycle_lock:
            self._ensure_open()
            key = _path_key(root)
            settings = self._read_settings()
            settings["discoveryRoots"] = [item for item in settings["discoveryRoots"] if _path_key(item) != key]
            self._write_settings(settings)
            return self._refresh_lifecycle()

    def set_provider_enabled(
        self,
        provider_id: str,
        executable: Path | str,
        enabled: bool,
        permissions: Any,
    ) -> Dict[str, Any]:
        with self._lifecycle_lock:
            self._ensure_open()
            provider = self._provider(provider_id)
            path = provider.normalize_executable(executable)
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
            return self._refresh_lifecycle()

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
        requested = list(dict.fromkeys(_text(name) for name in names if _text(name)))[:16]
        if not requested:
            return []
        with self._lock:
            session = self._find_session(service_id, provider_id)
            if session is None:
                raise ValueError("Enable the RATS service before requesting tool definitions.")
        with session.io_lock:
            with self._lock:
                if not self._session_is_current(session):
                    raise ValueError("Enable the RATS service before requesting tool definitions.")
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
                if name and isinstance(definition.get("request_schema"), dict):
                    definitions.append(dict(definition))
            with self._lock:
                if not self._session_is_current(session):
                    raise ValueError("Enable the RATS service before requesting tool definitions.")
                for definition in definitions:
                    session.definitions[_text(definition.get("name"))] = definition
                self._update_generation()
            return definitions

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

    def _session_is_current(self, session: _RatsSession) -> bool:
        key = (session.descriptor.provider_id, session.descriptor.service_id)
        return self._sessions.get(key) is session

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        service_id: str = "",
        provider_id: str = "",
        load: bool = True,
    ) -> List[Dict[str, Any]]:
        wanted = _text(query)
        if not wanted:
            raise ValueError("RATS search requires a non-empty query.")
        with self._lock:
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
        request_limit = min(16, max(1, int(limit)))
        for session in sessions:
            with session.io_lock:
                session_key = (session.descriptor.provider_id, session.descriptor.service_id)
                with self._lock:
                    if self._sessions.get(session_key) is not session:
                        continue
                    compact_tools = list(session.compact_tools)
                result = self._request(
                    session.descriptor,
                    "catalog.search",
                    {"query": wanted, "limit": request_limit},
                    session_token=session.token,
                )
                local = [_record(item) for item in result.get("matches", []) if isinstance(item, dict)]
                definitions: List[Dict[str, Any]] = []
                if load:
                    describable = [
                        _text(item.get("name"))
                        for item in local
                        if any(tool.get("name") == _text(item.get("name")) and tool.get("schema") for tool in compact_tools)
                    ]
                    if describable:
                        described = self._request(
                            session.descriptor,
                            "catalog.describe",
                            {"names": list(dict.fromkeys(describable))[:16]},
                            session_token=session.token,
                        )
                        for item in described.get("tools", []) if isinstance(described.get("tools"), list) else []:
                            definition = _record(item)
                            if _text(definition.get("name")) and isinstance(definition.get("request_schema"), dict):
                                definitions.append(dict(definition))
                with self._lock:
                    if self._sessions.get(session_key) is not session:
                        continue
                    for definition in definitions:
                        session.definitions[_text(definition.get("name"))] = definition
                    if definitions:
                        self._update_generation()
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
        deadline_ms: Optional[int] = None,
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            session = self._find_session(service_id, provider_id)
            if session is None:
                raise RatsClientError("The selected RATS service is not connected.", code="session_unavailable")
        with session.io_lock:
            with self._lock:
                if not self._session_is_current(session):
                    raise RatsClientError("The selected RATS service is not connected.", code="session_unavailable")
            result = self._request(
                session.descriptor,
                "tool.call",
                {"name": _text(tool_name), "arguments": _record(arguments), "dry_run": bool(dry_run)},
                session_token=session.token,
                timeout=self.tool_timeout,
                deadline_ms=deadline_ms,
                idempotency_key=idempotency_key,
            )
            task = _record(result.get("task"))
            if task:
                with self._lock:
                    if self._session_is_current(session):
                        self._remember_task(session, task, result=result)
            return result

    def _task_key(self, session: _RatsSession, task_id: str) -> Tuple[str, str, str]:
        return session.descriptor.provider_id, session.descriptor.service_id, _text(task_id)

    def _remember_task(
        self,
        session: _RatsSession,
        task: Dict[str, Any],
        *,
        result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task_id = _text(task.get("task_id"))
        if not task_id:
            raise RatsClientError("RTP returned a task without task_id.", code="invalid_task")
        key = self._task_key(session, task_id)
        current = self._tasks.get(key, {})
        current.update(
            {
                "provider_id": session.descriptor.provider_id,
                "service_id": session.descriptor.service_id,
                "task_id": task_id,
                "tool": _text(task.get("tool")) or _text(current.get("tool")),
                "status_operation": _text(task.get("status_operation")) or _text(current.get("status_operation")),
                "cancel_operation": _text(task.get("cancel_operation")) or _text(current.get("cancel_operation")),
                "deadline_msec": int(task.get("deadline_msec", current.get("deadline_msec", 0)) or 0),
                "first_event_sequence": int(task.get("first_event_sequence", current.get("first_event_sequence", 0)) or 0),
                "next_event_sequence": int(task.get("next_event_sequence", current.get("next_event_sequence", 0)) or 0),
                "cursor": int(current.get("cursor", 0) or 0),
                "log_cursor": int(current.get("log_cursor", 0) or 0),
                "events": list(current.get("events", [])) if isinstance(current.get("events"), list) else [],
                "error": "",
            }
        )
        if result is not None:
            current["start_result"] = dict(result)
        self._tasks[key] = current
        return dict(current)

    def _find_task(self, service_id: str, task_id: str, provider_id: str = "") -> Tuple[_RatsSession, Dict[str, Any], Tuple[str, str, str]]:
        session = self._find_session(service_id, provider_id)
        if session is None:
            raise RatsClientError("The selected RATS service is not connected.", code="session_unavailable")
        key = self._task_key(session, task_id)
        task = self._tasks.get(key)
        if task is None:
            raise RatsClientError("The task is not registered in this CLI session.", code="task_unavailable")
        return session, task, key

    def _confirm_task_snapshot(
        self,
        session: _RatsSession,
        task: Dict[str, Any],
        key: Tuple[str, str, str],
    ) -> None:
        if not self._session_is_current(session):
            raise RatsClientError("The selected RATS service is not connected.", code="session_unavailable")
        if self._tasks.get(key) is not task:
            raise RatsClientError("The task is not registered in this CLI session.", code="task_unavailable")

    def _drop_tasks_for_session(self, session: _RatsSession) -> None:
        provider_id = session.descriptor.provider_id
        service_id = session.descriptor.service_id
        for key in list(self._tasks):
            if key[0] == provider_id and key[1] == service_id:
                self._tasks.pop(key, None)

    def _drop_tasks_for_key(self, provider_id: str, service_id: str) -> None:
        for key in list(self._tasks):
            if key[0] == provider_id and key[1] == service_id:
                self._tasks.pop(key, None)

    @staticmethod
    def _task_is_terminal(task: Dict[str, Any]) -> bool:
        if bool(task.get("cancelled", False)):
            return True
        status = _record(task.get("status"))
        if status.get("running") is False:
            return True
        return _text(status.get("state")).lower() in _TERMINAL_TASK_STATES

    def _prune_terminal_task_history(self, session: _RatsSession) -> None:
        """Keep the newest terminal history entries; never evict active tasks.

        Callers hold ``self._lock``. Dict insertion order is the deterministic
        first-registration order because updates do not reinsert an existing key.
        """
        session_prefix = (session.descriptor.provider_id, session.descriptor.service_id)
        terminal_keys = [
            key
            for key, task in self._tasks.items()
            if key[:2] == session_prefix and self._task_is_terminal(task)
        ]
        for key in terminal_keys[:-_MAX_TERMINAL_TASK_HISTORY_PER_SESSION]:
            self._tasks.pop(key, None)

    def task_status(
        self,
        service_id: str,
        task_id: str,
        *,
        provider_id: str = "",
        deadline_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            session, task, key = self._find_task(service_id, task_id, provider_id)
        with session.io_lock:
            with self._lock:
                self._confirm_task_snapshot(session, task, key)
            try:
                result = self._request(
                    session.descriptor,
                    "task.status",
                    {"task_id": _text(task_id)},
                    session_token=session.token,
                    timeout=self.tool_timeout,
                    deadline_ms=deadline_ms,
                )
            except (RatsClientError, ValueError) as exc:
                with self._lock:
                    if self._session_is_current(session) and self._tasks.get(key) is task:
                        task["error"] = str(exc)
                raise
            with self._lock:
                if self._session_is_current(session) and self._tasks.get(key) is task:
                    task.update({"status": dict(result), "cursor": int(result.get("next_cursor", task.get("cursor", 0)) or 0), "error": ""})
                    self._prune_terminal_task_history(session)
            return result

    def task_events(
        self,
        service_id: str,
        task_id: str,
        *,
        provider_id: str = "",
        cursor: Optional[int] = None,
        limit: int = 32,
        deadline_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            session, task, key = self._find_task(service_id, task_id, provider_id)
        with session.io_lock:
            with self._lock:
                self._confirm_task_snapshot(session, task, key)
            if cursor is None:
                cursor = int(task.get("cursor", 0) or 0)
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
                raise ValueError("RTP task cursor must be a non-negative integer.")
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 64:
                raise ValueError("RTP task event limit must be an integer between 1 and 64.")
            try:
                result = self._request(
                    session.descriptor,
                    "task.events",
                    {"task_id": _text(task_id), "cursor": cursor, "limit": limit},
                    session_token=session.token,
                    timeout=self.tool_timeout,
                    deadline_ms=deadline_ms,
                )
            except (RatsClientError, ValueError) as exc:
                with self._lock:
                    if self._session_is_current(session) and self._tasks.get(key) is task:
                        task["error"] = str(exc)
                raise
            events = result.get("events") if isinstance(result.get("events"), list) else []
            with self._lock:
                if self._session_is_current(session) and self._tasks.get(key) is task:
                    task["events"] = [*task.get("events", []), *events][-128:]
                    task["cursor"] = int(result.get("next_cursor", cursor) or cursor)
                    task["next_event_sequence"] = max(int(task.get("next_event_sequence", 0) or 0), task["cursor"] + 1)
                    task["truncated"] = bool(result.get("truncated", False))
                    task["error"] = ""
            return result

    def cancel_task(
        self,
        service_id: str,
        task_id: str,
        *,
        provider_id: str = "",
        deadline_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            session, task, key = self._find_task(service_id, task_id, provider_id)
        with session.io_lock:
            with self._lock:
                self._confirm_task_snapshot(session, task, key)
            result = self._request(
                session.descriptor,
                "task.cancel",
                {"task_id": _text(task_id)},
                session_token=session.token,
                timeout=self.tool_timeout,
                deadline_ms=deadline_ms,
            )
            with self._lock:
                if self._session_is_current(session) and self._tasks.get(key) is task:
                    task["status"] = dict(result.get("output", {}))
                    task["cancelled"] = bool(result.get("cancelled", False))
                    task["error"] = ""
                    self._prune_terminal_task_history(session)
            return result

    def task_logs(
        self,
        service_id: str,
        task_id: str,
        *,
        provider_id: str = "",
        cursor: Optional[int] = None,
        limit: int = 65_536,
        deadline_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            session, task, key = self._find_task(service_id, task_id, provider_id)
        with session.io_lock:
            with self._lock:
                self._confirm_task_snapshot(session, task, key)
            if cursor is None:
                cursor = int(task.get("log_cursor", 0) or 0)
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
                raise ValueError("RTP task log cursor must be a non-negative integer.")
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 65_536:
                raise ValueError("RTP task log limit must be an integer between 1 and 65536.")
            result = self._request(
                session.descriptor,
                "tool.call",
                {
                    "name": "logs.read",
                    "arguments": {"task_id": _text(task_id), "cursor": cursor, "limit": limit},
                    "dry_run": False,
                },
                session_token=session.token,
                timeout=self.tool_timeout,
                deadline_ms=deadline_ms,
            )
            output = _record(result.get("output"))
            with self._lock:
                if self._session_is_current(session) and self._tasks.get(key) is task:
                    task["log_cursor"] = int(output.get("next_cursor", cursor) or cursor)
                    task["logs"] = output
                    task["error"] = ""
            return output

    def get_tasks(self, *, service_id: str = "", provider_id: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            tasks = [
                task
                for (task_provider, task_service, _task_id), task in self._tasks.items()
                if (not service_id or task_service == _text(service_id))
                and (not provider_id or task_provider == _text(provider_id))
            ]
            return json.loads(json.dumps(tasks, ensure_ascii=False))

    def sync_tasks(self, *, service_id: str = "", provider_id: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            selected = [
                key
                for key, task in self._tasks.items()
                if (not service_id or task.get("service_id") == _text(service_id))
                and (not provider_id or task.get("provider_id") == _text(provider_id))
                and not self._task_is_terminal(task)
            ]
        for task_provider_id, task_service_id, task_id in selected:
            try:
                self.task_status(task_service_id, task_id, provider_id=task_provider_id)
                self.task_events(task_service_id, task_id, provider_id=task_provider_id)
            except (RatsClientError, ValueError):
                pass
        return self.get_tasks(service_id=service_id, provider_id=provider_id)

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
        _generation, definitions = self.get_tool_definitions_snapshot(force_refresh=force_refresh)
        return definitions

    def get_tool_definitions_snapshot(
        self,
        force_refresh: bool = False,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """Return one generation and its matching independent definition snapshot."""
        with self._lock:
            needs_refresh = force_refresh or not self._has_refreshed
        if needs_refresh:
            self.refresh()
        with self._lock:
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
                            "parameters": copy.deepcopy(source.get("request_schema", {})),
                            "response_schema": copy.deepcopy(source.get("response_schema", {})),
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
            return self._generation, definitions

    def _update_generation(self) -> None:
        material = [
            {
                "provider_id": session.descriptor.provider_id,
                "service_id": session.descriptor.service_id,
                "permissions": sorted(dict.fromkeys(session.permissions)),
                "definitions": {
                    name: session.definitions[name] for name in sorted(session.definitions)
                },
            }
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
        with self._lifecycle_lock:
            with self._lock:
                if self._closed:
                    return
                self._closed = True
                sessions = list(self._sessions.values())
                self._sessions.clear()
                self._tasks.clear()
                self._update_generation()
            for session in sessions:
                with session.io_lock:
                    self._close_session(session)


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
