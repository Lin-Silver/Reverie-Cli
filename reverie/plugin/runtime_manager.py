"""Plugin-style external runtime discovery for Reverie."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
import json
import platform
import subprocess
import sys
import time

from .protocol import (
    RuntimePluginCommandSpec,
    RuntimePluginHandshake,
    build_runtime_tool_name,
    normalize_runtime_handshake,
)


def _platform_key() -> str:
    mapping = {
        "Windows": "windows",
        "Linux": "linux",
        "Darwin": "darwin",
    }
    return mapping.get(platform.system(), "windows")


def _stable_json_signature(payload: Any) -> str:
    """Return a stable signature for dynamic-catalog change detection."""
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return repr(payload)


@dataclass(frozen=True)
class RuntimePluginSpec:
    """Built-in catalog entry for a supported external runtime plugin."""

    plugin_id: str
    display_name: str
    runtime_family: str
    description: str
    source_repo_hint: str = ""
    delivery: str = "plugin-exe"
    capabilities: tuple[str, ...] = ()
    entry_candidates: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimePluginRecord:
    """One detected or planned runtime plugin."""

    plugin_id: str
    display_name: str
    runtime_family: str
    status: str
    install_dir: Path
    source: str
    detail: str = ""
    description: str = ""
    version: str = ""
    manifest_path: Optional[Path] = None
    entry_path: Optional[Path] = None
    delivery: str = "plugin-exe"
    source_repo_hint: str = ""
    capabilities: tuple[str, ...] = ()
    catalog_managed: bool = False
    protocol_status: str = "no-entry"
    protocol_error: str = ""
    protocol: Optional[RuntimePluginHandshake] = None

    @property
    def is_ready(self) -> bool:
        return self.status == "ready" and self.entry_path is not None

    @property
    def is_installed(self) -> bool:
        return self.status != "not-installed"

    @property
    def protocol_supported(self) -> bool:
        return self.protocol_status == "supported" and self.protocol is not None

    @property
    def status_label(self) -> str:
        labels = {
            "ready": "Ready",
            "entry-missing": "Entry Missing",
            "invalid-manifest": "Invalid Manifest",
            "not-installed": "Not Installed",
        }
        return labels.get(self.status, self.status.replace("-", " ").title())

    @property
    def protocol_label(self) -> str:
        labels = {
            "supported": "RC Ready",
            "unsupported": "No RC",
            "invalid-json": "RC Invalid",
            "error": "RC Error",
            "timeout": "RC Timeout",
            "no-entry": "No Entry",
        }
        return labels.get(self.protocol_status, self.protocol_status.replace("-", " ").title())

    @property
    def protocol_tool_count(self) -> int:
        if not self.protocol:
            return 0
        return len(self.protocol.tool_commands)

    @property
    def protocol_command_count(self) -> int:
        if not self.protocol:
            return 0
        return len(self.protocol.commands)

    @property
    def entry_display(self) -> str:
        if not self.entry_path:
            return "-"
        try:
            return str(self.entry_path.relative_to(self.install_dir))
        except ValueError:
            return str(self.entry_path)

    @property
    def install_display(self) -> str:
        return str(self.install_dir)

    @property
    def source_label(self) -> str:
        labels = {
            "catalog": "Known Type",
            "manifest": "Manifest",
            "manifest+catalog": "Manifest+Hint",
            "auto-detect": "Known Type",
            "directory": "Directory",
        }
        return labels.get(self.source, self.source.title())


@dataclass(frozen=True)
class RuntimePluginSnapshot:
    """Cached plugin scan result."""

    install_root: Path
    catalog_root: Path
    scanned_at: float
    records: tuple[RuntimePluginRecord, ...]
    catalog_count: int

    @property
    def detected_count(self) -> int:
        return len(self.records)

    @property
    def ready_count(self) -> int:
        return sum(1 for record in self.records if record.is_ready)

    @property
    def installed_count(self) -> int:
        return sum(1 for record in self.records if record.is_installed)

    @property
    def missing_count(self) -> int:
        return sum(1 for record in self.records if record.status == "not-installed")

    @property
    def invalid_count(self) -> int:
        return sum(1 for record in self.records if record.status == "invalid-manifest")

    @property
    def protocol_ready_count(self) -> int:
        return sum(1 for record in self.records if record.protocol_supported)

    @property
    def noncompliant_count(self) -> int:
        return sum(1 for record in self.records if not record.protocol_supported)

    @property
    def tool_count(self) -> int:
        return sum(record.protocol_tool_count for record in self.records)

    def summary_label(self) -> str:
        return (
            f"{self.detected_count} detected | "
            f"{self.ready_count} ready | "
            f"{self.protocol_ready_count} rc | "
            f"{self.tool_count} tools"
        )

    def ready_names(self, limit: int = 3) -> str:
        names = [record.display_name for record in self.records if record.is_ready]
        if not names:
            return ""
        visible = names[:limit]
        if len(names) > limit:
            visible.append(f"+{len(names) - limit} more")
        return ", ".join(visible)

    def protocol_names(self, limit: int = 3) -> str:
        names = [record.display_name for record in self.records if record.protocol_supported]
        if not names:
            return ""
        visible = names[:limit]
        if len(names) > limit:
            visible.append(f"+{len(names) - limit} more")
        return ", ".join(visible)


DEFAULT_RUNTIME_PLUGIN_CATALOG: tuple[RuntimePluginSpec, ...] = (
        RuntimePluginSpec(
            plugin_id="godot",
            display_name="Godot Editor",
            runtime_family="engine",
            description="Primary 3D runtime/editor target for the first plugin-delivered pipeline.",
            source_repo_hint="references/godot",
            capabilities=("editor", "3d", "scene-import", "gltf"),
            entry_candidates={
                "windows": ("reverie-godot*.exe", "godot.exe", "godot*.exe", "Godot*.exe", "bin/Godot*.exe"),
                "linux": ("Godot*", "godot*", "bin/Godot*"),
                "darwin": ("Godot*.app", "Godot*", "bin/Godot*"),
            },
        ),
    RuntimePluginSpec(
        plugin_id="blender",
        display_name="Blender",
        runtime_family="dcc",
        description="Authoring/runtime-adjacent DCC for mesh processing, baking, and export automation.",
        source_repo_hint="references/blender",
        capabilities=("mesh", "rigging", "bake", "export"),
        entry_candidates={
            "windows": ("blender.exe", "Blender.exe", "bin/blender.exe"),
            "linux": ("blender", "bin/blender"),
            "darwin": ("Blender.app", "Blender*.app"),
        },
    ),
    RuntimePluginSpec(
        plugin_id="blockbench",
        display_name="Blockbench",
        runtime_family="dcc",
        description="Lightweight companion editor for fast modeling, previews, and MCP-assisted workflows.",
        source_repo_hint="references/blockbench",
        capabilities=("modeling", "preview", "mcp"),
        entry_candidates={
            "windows": ("Blockbench.exe", "blockbench.exe", "bin/Blockbench.exe"),
            "linux": ("Blockbench", "blockbench", "bin/Blockbench"),
            "darwin": ("Blockbench.app", "Blockbench*.app"),
        },
    ),
    RuntimePluginSpec(
        plugin_id="gltf-validator",
        display_name="glTF Validator",
        runtime_family="validator",
        description="Validation/runtime health tool for imported glTF assets before downstream engine ingestion.",
        source_repo_hint="references/gltf-validator",
        capabilities=("validation", "gltf"),
        entry_candidates={
            "windows": (
                "gltf-validator.exe",
                "gltf-validator.cmd",
                "gltf-validator.bat",
                "bin/gltf-validator.exe",
            ),
            "linux": ("gltf-validator", "bin/gltf-validator"),
            "darwin": ("gltf-validator", "bin/gltf-validator"),
        },
    ),
)


class RuntimePluginManager:
    """Discover Reverie CLI runtime plugins installed under `.reverie/plugins`."""

    # One-file plugin wrappers can spend noticeable time self-extracting before
    # they emit the lightweight `-RC` handshake.
    PROTOCOL_TIMEOUT_SECONDS = 30.0
    TOOL_TIMEOUT_SECONDS = 1200.0

    def __init__(self, app_root: Path, *, catalog: Iterable[RuntimePluginSpec] | None = None) -> None:
        self.app_root = Path(app_root).resolve()
        self.install_root = self.app_root / ".reverie" / "plugins"
        self.catalog_root = Path(__file__).resolve().parent
        self._platform = _platform_key()
        catalog_items = tuple(catalog or DEFAULT_RUNTIME_PLUGIN_CATALOG)
        self.catalog = {item.plugin_id: item for item in catalog_items}
        self._snapshot: Optional[RuntimePluginSnapshot] = None
        self._tool_catalog: list[dict[str, Any]] = []
        self._tool_lookup: dict[str, dict[str, Any]] = {}
        self._tool_signature = ""
        self._generation = 0
        self.ensure_install_root()

    def ensure_install_root(self) -> None:
        """Create the plugin install directory if needed."""
        self.install_root.mkdir(parents=True, exist_ok=True)

    def get_snapshot(self, *, force_refresh: bool = False) -> RuntimePluginSnapshot:
        """Return the cached scan result, rescanning when requested."""
        if force_refresh or self._snapshot is None:
            return self.scan()
        return self._snapshot

    def get_generation(self) -> int:
        """Return the current dynamic-tool generation counter."""
        return int(self._generation)

    def get_tool_definitions(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Return dynamic tool metadata synthesized from `-RC` plugin handshakes."""
        if force_refresh or self._snapshot is None:
            self.scan()
        return [dict(item) for item in self._tool_catalog]

    def resolve_tool(self, synthetic_name: str) -> Optional[dict[str, Any]]:
        """Resolve one synthetic `rc_*` tool name back to its plugin metadata."""
        wanted = str(synthetic_name or "").strip()
        if not wanted:
            return None
        if wanted not in self._tool_lookup and self._snapshot is None:
            self.scan()
        found = self._tool_lookup.get(wanted)
        return dict(found) if isinstance(found, dict) else None

    def get_record(self, plugin_id: str, *, force_refresh: bool = False) -> Optional[RuntimePluginRecord]:
        """Return one plugin record by id."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        wanted = str(plugin_id or "").strip().lower()
        for record in snapshot.records:
            if record.plugin_id.lower() == wanted:
                return record
        return None

    def scan(self) -> RuntimePluginSnapshot:
        """Rescan the install root and rebuild the runtime plugin snapshot."""
        self.ensure_install_root()

        records_by_id: dict[str, RuntimePluginRecord] = {}
        install_dirs = sorted(
            [
                candidate
                for candidate in self.install_root.iterdir()
                if candidate.is_dir() and not candidate.name.startswith(("_", "."))
            ],
            key=lambda path: path.name.lower(),
        )

        for install_dir in install_dirs:
            manifest_path = install_dir / "plugin.json"
            if manifest_path.is_file():
                record = self._record_from_manifest(install_dir, manifest_path)
            else:
                spec = self.catalog.get(install_dir.name.strip().lower())
                if spec is not None:
                    record = self._record_from_catalog_dir(spec, install_dir)
                else:
                    record = self._record_from_generic_directory(install_dir)
            records_by_id[record.plugin_id] = record

        base_records = tuple(sorted(records_by_id.values(), key=self._sort_key))
        records = tuple(self._attach_protocol(record) for record in base_records)
        snapshot = RuntimePluginSnapshot(
            install_root=self.install_root,
            catalog_root=self.catalog_root,
            scanned_at=time.time(),
            records=records,
            catalog_count=len(base_records),
        )
        self._snapshot = snapshot
        self._rebuild_tool_catalog(records)
        return snapshot

    def get_status_summary(self, *, force_refresh: bool = False) -> dict[str, Any]:
        """Build a small summary payload for UI surfaces."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        return {
            "install_root": snapshot.install_root,
            "catalog_root": snapshot.catalog_root,
            "detected_count": snapshot.detected_count,
            "catalog_count": snapshot.catalog_count,
            "ready_count": snapshot.ready_count,
            "installed_count": snapshot.installed_count,
            "invalid_count": snapshot.invalid_count,
            "protocol_ready_count": snapshot.protocol_ready_count,
            "noncompliant_count": snapshot.noncompliant_count,
            "tool_count": snapshot.tool_count,
            "summary_label": snapshot.summary_label(),
            "ready_names": snapshot.ready_names(),
            "protocol_names": snapshot.protocol_names(),
        }

    def list_display_rows(self, *, force_refresh: bool = False) -> list[dict[str, str]]:
        """Return normalized rows for CLI rendering."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        rows: list[dict[str, str]] = []
        for record in snapshot.records:
            notes = record.detail.strip()
            if record.protocol_error:
                notes = record.protocol_error
            elif not notes and record.version:
                notes = f"Version {record.version}"
            elif not notes and record.source_repo_hint:
                notes = record.source_repo_hint
            rows.append(
                {
                    "id": record.plugin_id,
                    "name": record.display_name,
                    "family": record.runtime_family,
                    "status": record.status,
                    "status_label": record.status_label,
                    "protocol_status": record.protocol_status,
                    "protocol_label": record.protocol_label,
                    "source": record.source_label,
                    "entry": record.entry_display,
                    "install_dir": record.install_display,
                    "notes": notes,
                    "tool_count": str(record.protocol_tool_count),
                    "command_count": str(record.protocol_command_count),
                }
            )
        return rows

    def describe_for_prompt(self) -> str:
        """Return a compact system-prompt addendum for runtime-plugin tools."""
        snapshot = self.get_snapshot(force_refresh=False)
        lines = [
            "## Runtime Plugins",
            "- Reverie may expose dynamic runtime-plugin tools whose names begin with `rc_`.",
            "- These tools come from plugin executables installed under `.reverie/plugins`.",
            "- Only currently detected plugin directories are shown; there are no fixed required slots.",
            "- Prefer calling the exposed `rc_*` tool directly when a plugin advertises the capability.",
            "- Do not invent plugin commands. Use only the discovered `rc_*` tools and their schemas.",
        ]

        if not snapshot.records:
            lines.append("- No plugin directories are currently detected under `.reverie/plugins`.")
            return "\n".join(lines)

        ready_protocol_plugins = [record for record in snapshot.records if record.protocol_supported]
        if not ready_protocol_plugins:
            lines.append("- Plugins were detected, but none are Reverie CLI protocol-ready yet.")
            return "\n".join(lines)

        lines.append(f"- Ready protocol plugins: {', '.join(record.display_name for record in ready_protocol_plugins[:4])}")
        if len(ready_protocol_plugins) > 4:
            lines.append(f"- Additional protocol plugins not shown: {len(ready_protocol_plugins) - 4}")

        for record in ready_protocol_plugins[:4]:
            protocol = record.protocol
            if protocol is None:
                continue
            tool_names = [
                metadata["name"]
                for metadata in self._tool_catalog
                if str(metadata.get("plugin_id", "")).strip() == record.plugin_id
            ]
            lines.append(f"- Plugin `{record.plugin_id}` ({record.display_name})")
            if protocol.system_prompt:
                lines.append(f"  Guidance: {protocol.system_prompt}")
            elif record.description:
                lines.append(f"  Guidance: {record.description}")
            if protocol.tool_call_hint:
                lines.append(f"  Tool call hint: {protocol.tool_call_hint}")
            if tool_names:
                lines.append(f"  Exposed tools: {', '.join(tool_names[:6])}")
            else:
                lines.append("  Exposed tools: (none)")

        return "\n".join(lines)

    def call_tool(self, plugin_id: str, command_name: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Call one Reverie CLI runtime-plugin command."""
        record = self.get_record(plugin_id, force_refresh=False)
        if record is None:
            raise RuntimeError(f"Runtime plugin '{plugin_id}' is not currently detected.")
        if not record.protocol_supported or record.protocol is None:
            raise RuntimeError(f"Runtime plugin '{plugin_id}' does not support the Reverie CLI protocol.")

        command = self._find_protocol_command(record, command_name)
        if command is None:
            raise RuntimeError(f"Runtime plugin '{plugin_id}' does not expose command '{command_name}'.")
        if record.entry_path is None:
            raise RuntimeError(f"Runtime plugin '{plugin_id}' has no runnable entry.")

        payload_text = json.dumps(arguments or {}, ensure_ascii=False)
        result = self._run_plugin_process(
            record.entry_path,
            ["-RC-CALL", command.name, payload_text],
            timeout_seconds=self.TOOL_TIMEOUT_SECONDS,
        )
        if result.get("timed_out"):
            return {
                "success": False,
                "output": "",
                "error": f"Runtime plugin '{plugin_id}' timed out while running '{command.name}'.",
                "data": {},
            }
        if result.get("error"):
            return {
                "success": False,
                "output": "",
                "error": str(result.get("error")),
                "data": {},
            }

        stdout = str(result.get("stdout", "") or "").strip()
        stderr = str(result.get("stderr", "") or "").strip()
        parsed = self._parse_json_object(stdout)
        if isinstance(parsed, dict):
            success = bool(parsed.get("success", result.get("returncode", 1) == 0))
            output = str(parsed.get("output") or parsed.get("message") or stdout).strip()
            data = parsed.get("data", {})
            if not isinstance(data, dict):
                data = {}
            error = str(parsed.get("error") or "").strip()
            if not success and not error and stderr:
                error = stderr
            return {
                "success": success,
                "output": output,
                "error": error,
                "data": data,
            }

        success = int(result.get("returncode", 1) or 0) == 0
        return {
            "success": success,
            "output": stdout or stderr,
            "error": "" if success else (stderr or stdout or f"Runtime plugin '{plugin_id}' failed."),
            "data": {},
        }

    def _record_from_manifest(self, install_dir: Path, manifest_path: Path) -> RuntimePluginRecord:
        fallback_id = install_dir.name.strip() or "runtime-plugin"
        raw_manifest, error = self._load_manifest(manifest_path)
        if raw_manifest is None:
            spec = self.catalog.get(fallback_id)
            return RuntimePluginRecord(
                plugin_id=fallback_id,
                display_name=spec.display_name if spec else fallback_id,
                runtime_family=spec.runtime_family if spec else "runtime",
                status="invalid-manifest",
                install_dir=install_dir,
                source="manifest",
                detail=f"plugin.json could not be parsed: {error}",
                description=spec.description if spec else "",
                manifest_path=manifest_path,
                delivery=spec.delivery if spec else "plugin-exe",
                source_repo_hint=spec.source_repo_hint if spec else "",
                capabilities=spec.capabilities if spec else tuple(),
                catalog_managed=spec is not None,
            )

        plugin_id = str(raw_manifest.get("id") or fallback_id).strip() or fallback_id
        spec = self.catalog.get(plugin_id)
        display_name = str(raw_manifest.get("display_name") or raw_manifest.get("name") or "").strip()
        runtime_family = str(raw_manifest.get("runtime_family") or raw_manifest.get("kind") or "").strip()
        description = str(raw_manifest.get("description") or "").strip()
        delivery = str(raw_manifest.get("delivery") or raw_manifest.get("distribution") or "").strip() or "plugin-exe"
        version = str(raw_manifest.get("version") or "").strip()
        source_repo_hint = str(raw_manifest.get("source_repo_hint") or "").strip()
        capabilities = self._normalize_capabilities(raw_manifest.get("capabilities"))

        entry_path = self._resolve_manifest_entry(raw_manifest, install_dir)
        source = "manifest"
        if entry_path is None and spec is not None:
            entry_path = self._resolve_from_candidates(install_dir, spec.entry_candidates)
            if entry_path is not None:
                source = "manifest+catalog"

        status = "ready" if entry_path is not None else "entry-missing"
        detail = "Entry executable detected." if status == "ready" else "plugin.json exists but no valid entry executable was found."

        return RuntimePluginRecord(
            plugin_id=plugin_id,
            display_name=display_name or (spec.display_name if spec else plugin_id),
            runtime_family=runtime_family or (spec.runtime_family if spec else "runtime"),
            status=status,
            install_dir=install_dir,
            source=source,
            detail=detail,
            description=description or (spec.description if spec else ""),
            version=version,
            manifest_path=manifest_path,
            entry_path=entry_path,
            delivery=delivery or (spec.delivery if spec else "plugin-exe"),
            source_repo_hint=source_repo_hint or (spec.source_repo_hint if spec else ""),
            capabilities=capabilities or (spec.capabilities if spec else tuple()),
            catalog_managed=spec is not None,
        )

    def _record_from_catalog_dir(self, spec: RuntimePluginSpec, install_dir: Path) -> RuntimePluginRecord:
        entry_path = self._resolve_from_candidates(install_dir, spec.entry_candidates)
        if entry_path is not None:
            status = "ready"
            detail = "Known plugin type entry auto-detected from the install directory."
            source = "auto-detect"
        else:
            status = "entry-missing"
            detail = "Directory exists, but no known plugin entry was found yet."
            source = "catalog"

        return RuntimePluginRecord(
            plugin_id=spec.plugin_id,
            display_name=spec.display_name,
            runtime_family=spec.runtime_family,
            status=status,
            install_dir=install_dir,
            source=source,
            detail=detail,
            description=spec.description,
            entry_path=entry_path,
            delivery=spec.delivery,
            source_repo_hint=spec.source_repo_hint,
            capabilities=spec.capabilities,
            catalog_managed=True,
        )

    def _record_from_generic_directory(self, install_dir: Path) -> RuntimePluginRecord:
        entry_path = self._resolve_from_candidates(
            install_dir,
            {
                "windows": (
                    "*.exe",
                    "*.cmd",
                    "*.bat",
                    "*.py",
                    "bin/*.exe",
                    "bin/*.cmd",
                    "bin/*.bat",
                    "bin/*.py",
                ),
                "linux": ("*", "bin/*"),
                "darwin": ("*.app", "*", "bin/*"),
            },
        )
        status = "ready" if entry_path is not None else "entry-missing"
        detail = (
            "Detected without plugin.json; probing it as a pluggable runtime entry."
            if entry_path is not None
            else "Unknown plugin directory. Add plugin.json or a runnable plugin entry to make it compliant."
        )
        return RuntimePluginRecord(
            plugin_id=install_dir.name,
            display_name=install_dir.name,
            runtime_family="runtime",
            status=status,
            install_dir=install_dir,
            source="directory",
            detail=detail,
            entry_path=entry_path,
            delivery="plugin-exe",
        )

    def _merge_catalog_defaults(self, record: RuntimePluginRecord, spec: RuntimePluginSpec) -> RuntimePluginRecord:
        if record.entry_path is None:
            detected_entry = self._resolve_from_candidates(record.install_dir, spec.entry_candidates)
            if detected_entry is not None:
                return RuntimePluginRecord(
                    plugin_id=record.plugin_id,
                    display_name=record.display_name or spec.display_name,
                    runtime_family=record.runtime_family or spec.runtime_family,
                    status="ready",
                    install_dir=record.install_dir,
                    source="manifest+catalog" if record.source == "manifest" else "auto-detect",
                    detail="Entry executable detected.",
                    description=record.description or spec.description,
                    version=record.version,
                    manifest_path=record.manifest_path,
                    entry_path=detected_entry,
                    delivery=record.delivery or spec.delivery,
                    source_repo_hint=record.source_repo_hint or spec.source_repo_hint,
                    capabilities=record.capabilities or spec.capabilities,
                    catalog_managed=True,
                    protocol_status=record.protocol_status,
                    protocol_error=record.protocol_error,
                    protocol=record.protocol,
                )

        return RuntimePluginRecord(
            plugin_id=record.plugin_id,
            display_name=record.display_name or spec.display_name,
            runtime_family=record.runtime_family or spec.runtime_family,
            status=record.status,
            install_dir=record.install_dir,
            source=record.source,
            detail=record.detail or spec.description,
            description=record.description or spec.description,
            version=record.version,
            manifest_path=record.manifest_path,
            entry_path=record.entry_path,
            delivery=record.delivery or spec.delivery,
            source_repo_hint=record.source_repo_hint or spec.source_repo_hint,
            capabilities=record.capabilities or spec.capabilities,
            catalog_managed=True,
            protocol_status=record.protocol_status,
            protocol_error=record.protocol_error,
            protocol=record.protocol,
        )

    def _attach_protocol(self, record: RuntimePluginRecord) -> RuntimePluginRecord:
        if not record.is_ready or record.entry_path is None:
            return RuntimePluginRecord(
                plugin_id=record.plugin_id,
                display_name=record.display_name,
                runtime_family=record.runtime_family,
                status=record.status,
                install_dir=record.install_dir,
                source=record.source,
                detail=record.detail,
                description=record.description,
                version=record.version,
                manifest_path=record.manifest_path,
                entry_path=record.entry_path,
                delivery=record.delivery,
                source_repo_hint=record.source_repo_hint,
                capabilities=record.capabilities,
                catalog_managed=record.catalog_managed,
                protocol_status="no-entry",
            )

        probe = self._probe_runtime_protocol(record)
        protocol = probe.get("protocol")
        display_name = record.display_name
        runtime_family = record.runtime_family
        description = record.description
        version = record.version
        if isinstance(protocol, RuntimePluginHandshake):
            if protocol.display_name:
                display_name = protocol.display_name
            if protocol.runtime_family:
                runtime_family = protocol.runtime_family
            if protocol.description:
                description = protocol.description
            if protocol.version:
                version = protocol.version
        return RuntimePluginRecord(
            plugin_id=record.plugin_id,
            display_name=display_name,
            runtime_family=runtime_family,
            status=record.status,
            install_dir=record.install_dir,
            source=record.source,
            detail=record.detail,
            description=description,
            version=version,
            manifest_path=record.manifest_path,
            entry_path=record.entry_path,
            delivery=record.delivery,
            source_repo_hint=record.source_repo_hint,
            capabilities=record.capabilities,
            catalog_managed=record.catalog_managed,
            protocol_status=str(probe.get("status", "unsupported")),
            protocol_error=str(probe.get("error", "") or "").strip(),
            protocol=protocol,
        )

    def _probe_runtime_protocol(self, record: RuntimePluginRecord) -> dict[str, Any]:
        if record.entry_path is None:
            return {"status": "no-entry", "error": "", "protocol": None}

        result = self._run_plugin_process(record.entry_path, ["-RC"], timeout_seconds=self.PROTOCOL_TIMEOUT_SECONDS)
        if result.get("timed_out"):
            return {"status": "timeout", "error": "Timed out while probing `-RC`.", "protocol": None}
        if result.get("error"):
            return {"status": "error", "error": str(result.get("error")), "protocol": None}

        stdout = str(result.get("stdout", "") or "").strip()
        stderr = str(result.get("stderr", "") or "").strip()
        parsed = self._parse_json_object(stdout)
        if isinstance(parsed, dict):
            protocol = normalize_runtime_handshake(
                parsed,
                fallback_plugin_id=record.plugin_id,
                fallback_display_name=record.display_name,
                fallback_runtime_family=record.runtime_family,
            )
            if protocol is None:
                return {
                    "status": "invalid-json",
                    "error": "The `-RC` payload was not a valid Reverie CLI JSON object.",
                    "protocol": None,
                }
            return {"status": "supported", "error": "", "protocol": protocol}

        returncode = int(result.get("returncode", 1) or 0)
        if stdout:
            error_text = stdout
        elif stderr:
            error_text = stderr
        elif returncode != 0:
            error_text = f"Exit code {returncode}"
        else:
            error_text = ""

        if stdout:
            return {"status": "invalid-json", "error": error_text[:240], "protocol": None}
        return {"status": "unsupported", "error": error_text[:240], "protocol": None}

    def _rebuild_tool_catalog(self, records: tuple[RuntimePluginRecord, ...]) -> None:
        used_names: set[str] = set()
        catalog: list[dict[str, Any]] = []
        lookup: dict[str, dict[str, Any]] = {}

        for record in records:
            if not record.protocol_supported or record.protocol is None:
                continue

            for command in record.protocol.tool_commands:
                synthetic_name = build_runtime_tool_name(record.plugin_id, command.name, used_names)
                used_names.add(synthetic_name)
                metadata = {
                    "name": synthetic_name,
                    "plugin_id": record.plugin_id,
                    "plugin_display_name": record.display_name,
                    "runtime_family": record.runtime_family,
                    "command_name": command.name,
                    "description": (
                        f"{command.description} "
                        f"[plugin={record.plugin_id}, runtime={record.display_name}, protocol=RC]"
                    ).strip(),
                    "parameters": dict(command.parameters),
                    "qualified_name": f"{record.plugin_id}.{command.name}",
                    "include_modes": list(command.include_modes or ("reverie-gamer",)),
                    "exclude_modes": list(command.exclude_modes),
                    "guidance": command.guidance,
                    "example": command.example,
                }
                catalog.append(metadata)
                lookup[synthetic_name] = metadata

        signature = _stable_json_signature(catalog)
        if signature != self._tool_signature:
            self._generation += 1
            self._tool_signature = signature
        self._tool_catalog = catalog
        self._tool_lookup = lookup

    def _find_protocol_command(self, record: RuntimePluginRecord, command_name: str) -> Optional[RuntimePluginCommandSpec]:
        if record.protocol is None:
            return None
        wanted = str(command_name or "").strip().lower()
        for command in record.protocol.commands:
            if command.name.lower() == wanted:
                return command
        return None

    def _run_plugin_process(self, entry_path: Path, extra_args: list[str], *, timeout_seconds: float) -> dict[str, Any]:
        command = self._build_launch_command(entry_path, extra_args)
        startupinfo = None
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            startupinfo.wShowWindow = 0

        try:
            completed = subprocess.run(
                command,
                cwd=str(entry_path.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                startupinfo=startupinfo,
                creationflags=creationflags,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "timed_out": True,
                "stdout": str(getattr(exc, "stdout", "") or ""),
                "stderr": str(getattr(exc, "stderr", "") or ""),
            }
        except Exception as exc:
            return {
                "timed_out": False,
                "error": str(exc),
                "stdout": "",
                "stderr": "",
            }

        return {
            "timed_out": False,
            "returncode": int(completed.returncode),
            "stdout": str(completed.stdout or ""),
            "stderr": str(completed.stderr or ""),
        }

    def _build_launch_command(self, entry_path: Path, extra_args: list[str]) -> list[str]:
        suffix = entry_path.suffix.lower()
        if suffix in {".cmd", ".bat"}:
            return ["cmd.exe", "/d", "/c", str(entry_path), *extra_args]
        if suffix == ".ps1":
            return [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(entry_path),
                *extra_args,
            ]
        if suffix == ".py":
            return [sys.executable, str(entry_path), *extra_args]
        return [str(entry_path), *extra_args]

    def _parse_json_object(self, text: str) -> Optional[dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else None
        except Exception:
            pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(raw[start : end + 1])
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _load_manifest(self, manifest_path: Path) -> tuple[Optional[dict[str, Any]], str]:
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            return None, str(exc)
        if not isinstance(data, dict):
            return None, "Manifest root must be a JSON object."
        return data, ""

    def _resolve_manifest_entry(self, raw_manifest: dict[str, Any], install_dir: Path) -> Optional[Path]:
        entry = raw_manifest.get("entry")
        if isinstance(entry, dict):
            candidate = entry.get(self._platform) or entry.get("default")
            resolved = self._resolve_relative_entry(install_dir, candidate)
            if resolved is not None:
                return resolved
        elif isinstance(entry, str):
            resolved = self._resolve_relative_entry(install_dir, entry)
            if resolved is not None:
                return resolved

        executable = raw_manifest.get("executable")
        if isinstance(executable, str):
            resolved = self._resolve_relative_entry(install_dir, executable)
            if resolved is not None:
                return resolved
        return None

    def _resolve_relative_entry(self, install_dir: Path, candidate: Any) -> Optional[Path]:
        raw = str(candidate or "").strip()
        if not raw:
            return None
        path = Path(raw)
        resolved = path if path.is_absolute() else install_dir / path
        try:
            resolved = resolved.resolve(strict=False)
        except Exception:
            resolved = resolved.absolute()
        return resolved if self._is_launch_target(resolved) else None

    def _resolve_from_candidates(self, install_dir: Path, entry_candidates: dict[str, tuple[str, ...]]) -> Optional[Path]:
        if not install_dir.exists():
            return None
        patterns = list(entry_candidates.get(self._platform, ()))
        patterns.extend(pattern for pattern in entry_candidates.get("default", ()) if pattern not in patterns)
        for pattern in patterns:
            for match in self._iter_candidate_matches(install_dir, pattern):
                if self._is_launch_target(match):
                    return match.resolve(strict=False)
        return None

    def _iter_candidate_matches(self, install_dir: Path, pattern: str) -> Iterable[Path]:
        normalized = str(pattern or "").strip()
        if not normalized:
            return []
        return sorted(install_dir.glob(normalized), key=lambda path: str(path).lower())

    def _normalize_capabilities(self, raw_value: Any) -> tuple[str, ...]:
        if not isinstance(raw_value, list):
            return tuple()
        values: list[str] = []
        for item in raw_value:
            text = str(item or "").strip()
            if text:
                values.append(text)
        return tuple(values)

    def _is_launch_target(self, path: Path) -> bool:
        if not path.exists():
            return False
        return path.is_file() or path.name.lower().endswith(".app")

    def _sort_key(self, record: RuntimePluginRecord) -> tuple[int, str, str]:
        status_priority = {
            "ready": 0,
            "entry-missing": 1,
            "invalid-manifest": 2,
        }
        return (
            status_priority.get(record.status, 9),
            record.display_name.lower(),
            record.plugin_id.lower(),
        )
