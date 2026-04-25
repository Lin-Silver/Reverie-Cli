"""SDK/runtime depot discovery for Reverie plugins."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Optional
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import zipfile

from .protocol import (
    RuntimePluginCommandSpec,
    RuntimePluginHandshake,
    build_runtime_tool_name,
    normalize_runtime_handshake,
    sanitize_plugin_identifier,
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


def _normalize_string_tuple(raw_value: Any) -> tuple[str, ...]:
    if isinstance(raw_value, str):
        value = raw_value.strip()
        return (value,) if value else tuple()
    if not isinstance(raw_value, list):
        return tuple()
    values: list[str] = []
    for item in raw_value:
        text = str(item or "").strip()
        if text:
            values.append(text)
    return tuple(values)


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    results: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(path)
    return results


@dataclass(frozen=True)
class RuntimePluginSpec:
    """Built-in catalog entry for a supported SDK/runtime plugin."""

    plugin_id: str
    display_name: str
    runtime_family: str
    description: str
    source_repo_hint: str = ""
    delivery: str = "plugin-exe"
    capabilities: tuple[str, ...] = ()
    entry_candidates: dict[str, tuple[str, ...]] = field(default_factory=dict)
    sdk_dir_name: str = "runtime"
    sdk_download_page: str = ""
    sdk_archive_hint: str = ""
    sdk_install_hint: str = ""
    bundled_archive_candidates: dict[str, tuple[str, ...]] = field(default_factory=dict)


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
    manifest_schema_version: str = ""
    packaging_format: str = ""
    entry_strategy: str = ""
    template_id: str = ""
    compiled_entry_path: Optional[Path] = None
    source_entry_path: Optional[Path] = None
    build_commands: tuple[str, ...] = ()
    manifest_warnings: tuple[str, ...] = ()

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
            "sdk-only": "SDK Only",
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
    def compiled_entry_display(self) -> str:
        if not self.compiled_entry_path:
            return "-"
        try:
            return str(self.compiled_entry_path.relative_to(self.install_dir))
        except ValueError:
            return str(self.compiled_entry_path)

    @property
    def source_entry_display(self) -> str:
        if not self.source_entry_path:
            return "-"
        try:
            return str(self.source_entry_path.relative_to(self.install_dir))
        except ValueError:
            return str(self.source_entry_path)

    @property
    def delivery_label(self) -> str:
        value = str(self.delivery or "").strip() or "plugin-exe"
        return value.replace("_", "-")

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
        return sum(1 for record in self.records if record.protocol_status not in {"supported", "sdk-only", "no-entry"})

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


@dataclass(frozen=True)
class RuntimePluginTemplateRecord:
    """One local source template for runtime plugin authoring."""

    template_id: str
    display_name: str
    description: str
    delivery: str
    template_dir: Path
    entry_template: str = ""
    manifest_template: str = ""
    build_hint: str = ""


DEFAULT_RUNTIME_PLUGIN_CATALOG: tuple[RuntimePluginSpec, ...] = (
    RuntimePluginSpec(
        plugin_id="godot",
        display_name="Godot Editor",
        runtime_family="engine",
        description="Open-source 3D runtime/editor target with plugin-local GitHub release downloads and source checkout support.",
        source_repo_hint="https://github.com/godotengine/godot",
        delivery="sdk-runtime",
        capabilities=("editor", "3d", "scene-import", "gltf", "github-release", "source-sdk"),
        entry_candidates={
            "windows": ("runtime/reverie-godot*.exe", "runtime/godot.exe", "runtime/Godot*.exe", "runtime/**/*.exe", "runtime/**/Godot*.exe", "runtime/**/godot*.exe", "reverie-godot*.exe", "godot.exe", "godot*.exe", "Godot*.exe", "bin/Godot*.exe"),
            "linux": ("runtime/Godot*", "runtime/godot*", "runtime/**/Godot*", "runtime/**/godot*", "Godot*", "godot*", "bin/Godot*"),
            "darwin": ("runtime/Godot*.app", "runtime/**/Godot*.app", "Godot*.app", "Godot*", "bin/Godot*"),
        },
        sdk_download_page="https://github.com/godotengine/godot/releases",
        sdk_archive_hint="Use `/plugins deploy godot`, `rc_godot_list_versions`, or `rc_godot_install_runtime` to download an official release into `.reverie/plugins/godot/runtime/`.",
        sdk_install_hint="Expected entry: `.reverie/plugins/godot/runtime/<version>/Godot*.exe`; source checkouts live under `.reverie/plugins/godot/source/`.",
    ),
    RuntimePluginSpec(
        plugin_id="o3de",
        display_name="O3DE Source SDK",
        runtime_family="engine",
        description="Open-source O3DE source SDK manager that clones GitHub source and writes plugin-local SDK manifests.",
        source_repo_hint="https://github.com/o3de/o3de",
        delivery="sdk-runtime",
        capabilities=("engine", "large-scale-3d", "source-sdk", "github-release", "asset-processor-contract"),
        entry_candidates={
            "windows": (
                "runtime/sdk_manifest.json",
                "runtime/**/sdk_manifest.json",
                "source/**/scripts/o3de.bat",
                "source/**/scripts/o3de.py",
                "source/**/build/windows/bin/profile/Editor.exe",
            ),
            "linux": ("runtime/sdk_manifest.json", "source/**/scripts/o3de.py", "source/**/build/linux/bin/profile/Editor"),
            "darwin": ("runtime/sdk_manifest.json", "source/**/scripts/o3de.py", "source/**/build/mac/bin/profile/Editor.app"),
        },
        sdk_download_page="https://github.com/o3de/o3de/releases",
        sdk_archive_hint="Use `/plugins deploy o3de`, `rc_o3de_list_versions`, or `rc_o3de_clone_source` to create `.reverie/plugins/o3de/source/` plus a runtime SDK manifest.",
        sdk_install_hint="Expected manifest: `.reverie/plugins/o3de/runtime/sdk_manifest.json`; source checkout stays under `.reverie/plugins/o3de/source/`.",
    ),
    RuntimePluginSpec(
        plugin_id="game_models",
        display_name="Game Auxiliary Models",
        runtime_family="model-depot",
        description="Plugin-local open model package manager for Reverie-Gamer asset production.",
        source_repo_hint="https://huggingface.co/models",
        delivery="sdk-runtime",
        capabilities=("huggingface-models", "text-to-3d", "image-to-3d", "motion-generation", "game-assets", "8gb-vram-profiles", "plugin-local-venv"),
        entry_candidates={
            "windows": ("reverie-game-models*.exe", "dist/reverie-game-models*.exe", "plugin.py", "runtime/model_manifest.json"),
            "linux": ("reverie-game-models*", "dist/reverie-game-models*", "plugin.py", "runtime/model_manifest.json"),
            "darwin": ("reverie-game-models*", "dist/reverie-game-models*", "plugin.py", "runtime/model_manifest.json"),
        },
        sdk_download_page="https://huggingface.co/models",
        sdk_archive_hint="Use `/plugins deploy game_models`, `/plugins models ...`, `rc_game_models_select_model`, and `rc_game_models_download_model` to prepare plugin-local model packages.",
        sdk_install_hint="Model snapshots stay under `.reverie/plugins/game_models/models/`; caches stay under `.reverie/plugins/game_models/cache/`; the virtual environment stays under `.reverie/plugins/game_models/venv/`.",
    ),
    RuntimePluginSpec(
        plugin_id="blender",
        display_name="Blender",
        runtime_family="dcc",
        description="Authoring/runtime-adjacent DCC for mesh processing, baking, and export automation.",
        source_repo_hint="https://projects.blender.org/blender/blender",
        delivery="sdk-runtime",
        capabilities=("mesh", "rigging", "bake", "export"),
        entry_candidates={
            "windows": ("runtime/blender.exe", "runtime/blender/blender.exe", "runtime/**/blender.exe", "blender.exe", "Blender.exe", "bin/blender.exe"),
            "linux": ("runtime/blender", "runtime/blender/blender", "runtime/**/blender", "blender", "bin/blender"),
            "darwin": ("runtime/Blender.app", "runtime/**/Blender.app", "Blender.app", "Blender*.app"),
        },
        sdk_download_page="https://www.blender.org/download/",
        sdk_archive_hint="Unpack Blender Portable/ZIP into `.reverie/plugins/blender/runtime/`.",
        sdk_install_hint="Expected entry: `.reverie/plugins/blender/runtime/blender.exe`.",
        bundled_archive_candidates={
            "windows": ("blender-5.1.1-windows-x64.zip", "blender-*-windows-x64.zip", "plugins/blender/*.zip"),
        },
    ),
    RuntimePluginSpec(
        plugin_id="gltf-validator",
        display_name="glTF Validator",
        runtime_family="validator",
        description="Validation/runtime health tool for imported glTF assets before downstream engine ingestion.",
        source_repo_hint="https://github.com/KhronosGroup/glTF-Validator",
        delivery="sdk-runtime",
        capabilities=("validation", "gltf"),
        entry_candidates={
            "windows": (
                "runtime/gltf-validator.exe",
                "gltf-validator.exe",
                "gltf-validator.cmd",
                "gltf-validator.bat",
                "bin/gltf-validator.exe",
            ),
            "linux": ("runtime/gltf-validator", "gltf-validator", "bin/gltf-validator"),
            "darwin": ("runtime/gltf-validator", "gltf-validator", "bin/gltf-validator"),
        },
        sdk_download_page="https://github.com/KhronosGroup/glTF-Validator/releases",
        sdk_archive_hint="Place the validator binary under `.reverie/plugins/gltf-validator/runtime/`.",
        sdk_install_hint="Expected entry: `.reverie/plugins/gltf-validator/runtime/gltf-validator.exe`.",
    ),
)


class RuntimePluginManager:
    """Discover Reverie CLI runtime plugins installed under `.reverie/plugins`."""

    AI_TOOL_EXPOSURE_ENABLED = True
    # One-file plugin wrappers can spend noticeable time self-extracting before
    # they emit the lightweight `-RC` handshake.
    PROTOCOL_TIMEOUT_SECONDS = 30.0
    TOOL_TIMEOUT_SECONDS = 1200.0
    BUILD_TIMEOUT_SECONDS = 1800.0

    def __init__(self, app_root: Path, *, catalog: Iterable[RuntimePluginSpec] | None = None, source_root: Path | None = None) -> None:
        self.app_root = Path(app_root).resolve()
        self.source_root = Path(source_root).resolve() if source_root is not None else self._resolve_source_root()
        self.install_root = self.app_root / ".reverie" / "plugins"
        self.catalog_root = Path(__file__).resolve().parent
        self.template_root = self.source_root / "_templates"
        self._platform = _platform_key()
        catalog_items = tuple(catalog or DEFAULT_RUNTIME_PLUGIN_CATALOG)
        self.catalog = {item.plugin_id: item for item in catalog_items}
        self._snapshot: Optional[RuntimePluginSnapshot] = None
        self._tool_catalog: list[dict[str, Any]] = []
        self._tool_lookup: dict[str, dict[str, Any]] = {}
        self._tool_signature = ""
        self._generation = 0
        self._template_catalog: tuple[RuntimePluginTemplateRecord, ...] = tuple()

    def _resolve_source_root(self) -> Path:
        """Return the editable source-plugin tree for the current runtime."""
        app_plugins = self.app_root / "plugins"
        if app_plugins.exists():
            return app_plugins

        try:
            repo_root = Path(__file__).resolve().parents[2]
            repo_plugins = repo_root / "plugins"
            if repo_plugins.exists():
                return repo_plugins
        except Exception:
            pass

        return app_plugins

    def ensure_install_root(self) -> None:
        """Create the plugin install directory if needed."""
        self.install_root.mkdir(parents=True, exist_ok=True)

    def ensure_source_root(self) -> None:
        """Create the plugin source directory if needed."""
        self.source_root.mkdir(parents=True, exist_ok=True)

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
        if not self.AI_TOOL_EXPOSURE_ENABLED:
            return []
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
        wanted = sanitize_plugin_identifier(plugin_id or "")
        for record in snapshot.records:
            if sanitize_plugin_identifier(record.plugin_id) == wanted:
                return record
        return None

    def scan(self) -> RuntimePluginSnapshot:
        """Rescan the install root and rebuild the runtime plugin snapshot."""
        records_by_id: dict[str, RuntimePluginRecord] = {}
        install_dirs = []
        if self.install_root.exists():
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
        templates = self.list_templates(force_refresh=force_refresh)
        return {
            "source_root": self.source_root,
            "install_root": snapshot.install_root,
            "sdk_root": snapshot.install_root,
            "catalog_root": snapshot.catalog_root,
            "template_root": self.template_root,
            "detected_count": snapshot.detected_count,
            "catalog_count": snapshot.catalog_count,
            "ready_count": snapshot.ready_count,
            "installed_count": snapshot.installed_count,
            "invalid_count": snapshot.invalid_count,
            "protocol_ready_count": snapshot.protocol_ready_count,
            "noncompliant_count": snapshot.noncompliant_count,
            "tool_count": snapshot.tool_count,
            "template_count": len(templates),
            "summary_label": snapshot.summary_label(),
            "ready_names": snapshot.ready_names(),
            "protocol_names": snapshot.protocol_names(),
        }

    def list_templates(self, *, force_refresh: bool = False) -> tuple[RuntimePluginTemplateRecord, ...]:
        """Return local runtime-plugin source templates."""
        if force_refresh or not self._template_catalog:
            self._template_catalog = self._scan_templates()
        return self._template_catalog

    def get_template(self, template_id: str, *, force_refresh: bool = False) -> Optional[RuntimePluginTemplateRecord]:
        """Return one runtime-plugin template by id."""
        wanted = str(template_id or "").strip().lower()
        if not wanted:
            return None
        for record in self.list_templates(force_refresh=force_refresh):
            if record.template_id.lower() == wanted:
                return record
        return None

    def source_plugin_dir(self, plugin_id: str) -> Path:
        """Return the default source tree path for one plugin."""
        normalized = sanitize_plugin_identifier(plugin_id or "")
        return self.source_root / normalized

    def sdk_package_status(self, plugin_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        """Return SDK depot status for one catalog plugin."""
        normalized = sanitize_plugin_identifier(plugin_id or "")
        spec = self.catalog.get(normalized)
        if spec is None:
            return {
                "success": False,
                "error": f"Unknown SDK plugin id: {plugin_id}",
                "plugin_id": normalized,
            }

        record = self.get_record(normalized, force_refresh=force_refresh)
        install_dir = (record.install_dir if record is not None else self.install_root / normalized).resolve()
        sdk_dir = (install_dir / (spec.sdk_dir_name or "runtime")).resolve()
        manifest_path = install_dir / "sdk_manifest.json"
        entry_path = self._resolve_from_candidates(install_dir, spec.entry_candidates)
        archive_path = self._find_bundled_sdk_archive(spec)
        status = "ready" if entry_path is not None else ("prepared" if manifest_path.exists() or sdk_dir.exists() else "missing")
        return {
            "success": True,
            "error": "",
            "plugin_id": spec.plugin_id,
            "display_name": spec.display_name,
            "runtime_family": spec.runtime_family,
            "delivery": spec.delivery,
            "status": status,
            "entry_path": entry_path,
            "install_dir": install_dir,
            "sdk_dir": sdk_dir,
            "manifest_path": manifest_path,
            "download_page": spec.sdk_download_page,
            "archive_hint": spec.sdk_archive_hint,
            "install_hint": spec.sdk_install_hint,
            "bundled_archive": archive_path,
            "entry_candidates": list(spec.entry_candidates.get(self._platform, ()) or spec.entry_candidates.get("default", ())),
        }

    def list_sdk_package_rows(self, *, force_refresh: bool = False) -> list[dict[str, str]]:
        """Return SDK depot rows for CLI rendering."""
        rows: list[dict[str, str]] = []
        for plugin_id in sorted(self.catalog):
            status = self.sdk_package_status(plugin_id, force_refresh=force_refresh)
            rows.append(
                {
                    "id": str(status.get("plugin_id", plugin_id)),
                    "name": str(status.get("display_name", plugin_id)),
                    "family": str(status.get("runtime_family", "")),
                    "delivery": str(status.get("delivery", "")),
                    "status": str(status.get("status", "missing")),
                    "sdk_dir": str(status.get("sdk_dir", "")),
                    "entry": str(status.get("entry_path") or "-"),
                    "archive": str(status.get("bundled_archive") or ""),
                    "download_page": str(status.get("download_page", "")),
                    "hint": str(status.get("install_hint") or status.get("archive_hint") or ""),
                }
            )
        return rows

    def materialize_sdk_package(self, plugin_id: str, *, overwrite: bool = False) -> dict[str, Any]:
        """Create the `.reverie/plugins/<plugin-id>/runtime` SDK depot skeleton."""
        normalized = sanitize_plugin_identifier(plugin_id or "")
        spec = self.catalog.get(normalized)
        if spec is None:
            return {
                "success": False,
                "error": f"Unknown SDK plugin id: {plugin_id}",
                "plugin_id": normalized,
            }

        self.ensure_install_root()
        install_dir = (self.install_root / normalized).resolve()
        sdk_dir = install_dir / (spec.sdk_dir_name or "runtime")
        manifest_path = install_dir / "sdk_manifest.json"
        install_dir.mkdir(parents=True, exist_ok=True)
        sdk_dir.mkdir(parents=True, exist_ok=True)

        if manifest_path.exists() and not overwrite:
            status = self.sdk_package_status(normalized, force_refresh=True)
            return {
                "success": True,
                "error": "",
                "created": False,
                "manifest_path": manifest_path,
                "sdk_dir": sdk_dir,
                "status": status,
            }

        payload = {
            "schema": "reverie.plugin_sdk_manifest.v1",
            "plugin_id": spec.plugin_id,
            "display_name": spec.display_name,
            "runtime_family": spec.runtime_family,
            "delivery": spec.delivery,
            "role": "portable SDK/runtime depot",
            "sdk_dir": str(sdk_dir),
            "download_page": spec.sdk_download_page,
            "archive_hint": spec.sdk_archive_hint,
            "install_hint": spec.sdk_install_hint,
            "entry_candidates": {
                key: list(value)
                for key, value in spec.entry_candidates.items()
            },
            "capabilities": list(spec.capabilities),
        }
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.scan()
        status = self.sdk_package_status(normalized, force_refresh=False)
        return {
            "success": True,
            "error": "",
            "created": True,
            "manifest_path": manifest_path,
            "sdk_dir": sdk_dir,
            "status": status,
        }

    def deploy_sdk_package(
        self,
        plugin_id: str,
        *,
        archive_path: Any = "",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Extract a bundled portable SDK archive into `.reverie/plugins/<plugin-id>/runtime`."""
        normalized = sanitize_plugin_identifier(plugin_id or "")
        spec = self.catalog.get(normalized)
        if spec is None:
            return {
                "success": False,
                "error": f"Unknown SDK plugin id: {plugin_id}",
                "plugin_id": normalized,
            }

        prepared = self.materialize_sdk_package(normalized, overwrite=False)
        if not prepared.get("success", False):
            return prepared

        status = self.sdk_package_status(normalized, force_refresh=True)
        if status.get("entry_path") is not None and not overwrite:
            return {
                "success": True,
                "error": "",
                "deployed": False,
                "reason": "SDK entry already exists.",
                "status": status,
            }

        archive = self._resolve_sdk_archive(spec, archive_path)
        if archive is None:
            protocol_deploy = self._deploy_sdk_with_plugin_protocol(
                normalized,
                overwrite=overwrite,
                status=status,
            )
            if protocol_deploy is not None:
                return protocol_deploy
            return {
                "success": False,
                "error": f"No bundled archive found for {spec.display_name}. Expected: {', '.join(self._archive_patterns_for_platform(spec)) or '(none)'}",
                "status": status,
            }

        sdk_dir = Path(status["sdk_dir"]).resolve()
        if overwrite and sdk_dir.exists():
            self._safe_remove_tree(Path(status["install_dir"]).resolve(), sdk_dir)
            sdk_dir.mkdir(parents=True, exist_ok=True)

        before_entries = set(str(item.relative_to(sdk_dir)) for item in sdk_dir.rglob("*")) if sdk_dir.exists() else set()
        try:
            extracted_count = self._safe_extract_zip(archive, sdk_dir)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "archive_path": archive,
                "status": status,
            }

        after_entries = set(str(item.relative_to(sdk_dir)) for item in sdk_dir.rglob("*")) if sdk_dir.exists() else set()
        created_entries = sorted(after_entries - before_entries)
        self.scan()
        final_status = self.sdk_package_status(normalized, force_refresh=False)
        return {
            "success": final_status.get("entry_path") is not None,
            "error": "" if final_status.get("entry_path") is not None else "Archive extracted, but no runnable SDK entry was detected.",
            "deployed": True,
            "archive_path": archive,
            "sdk_dir": sdk_dir,
            "extracted_count": extracted_count,
            "created_entries": created_entries[:40],
            "status": final_status,
        }

    def _deploy_sdk_with_plugin_protocol(
        self,
        plugin_id: str,
        *,
        overwrite: bool,
        status: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Let a runtime plugin deploy an SDK/runtime it has embedded in its own executable."""
        record = self.get_record(plugin_id, force_refresh=True)
        if record is None or not record.protocol_supported or record.protocol is None:
            return None
        if self._find_protocol_command(record, "ensure_runtime") is None:
            return None

        try:
            result = self.call_tool(plugin_id, "ensure_runtime", {"force": bool(overwrite)})
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "deployed": False,
                "status": status,
            }

        self.scan()
        final_status = self.sdk_package_status(plugin_id, force_refresh=False)
        success = bool(result.get("success", False)) and final_status.get("entry_path") is not None
        return {
            "success": success,
            "error": "" if success else str(result.get("error") or "Plugin runtime deployment did not produce a runnable SDK entry."),
            "deployed": bool(result.get("data", {}).get("deployed", False)) if isinstance(result.get("data"), dict) else False,
            "reason": str(result.get("data", {}).get("reason", "")) if isinstance(result.get("data"), dict) else "",
            "protocol_result": result,
            "status": final_status,
        }

    def run_sdk_package(
        self,
        plugin_id: str,
        *,
        args: Optional[list[str]] = None,
        deploy_if_missing: bool = True,
    ) -> dict[str, Any]:
        """Launch a portable SDK plugin for the user."""
        normalized = sanitize_plugin_identifier(plugin_id or "")
        if deploy_if_missing:
            deploy_result = self.deploy_sdk_package(normalized, overwrite=False)
            if not deploy_result.get("success", False):
                return deploy_result

        status = self.sdk_package_status(normalized, force_refresh=True)
        entry_path = status.get("entry_path")
        if not isinstance(entry_path, Path):
            return {
                "success": False,
                "error": f"No runnable entry found for SDK plugin: {plugin_id}",
                "status": status,
            }
        if entry_path.suffix.lower() in {".json", ".yaml", ".yml", ".md", ".txt"}:
            return {
                "success": False,
                "error": (
                    f"{plugin_id} is source-managed and has a metadata entry instead of a directly runnable SDK binary. "
                    f"Use the plugin RC tools, such as rc_{normalized}_runtime_status or rc_{normalized}_clone_source."
                ),
                "status": status,
            }

        command = self._build_launch_command(entry_path, list(args or []))
        try:
            process = subprocess.Popen(command, cwd=str(entry_path.parent), shell=False)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "command": command,
                "status": status,
            }
        return {
            "success": True,
            "error": "",
            "command": command,
            "pid": int(process.pid),
            "status": status,
        }

    def scaffold_source_plugin(
        self,
        *,
        template_id: str,
        plugin_id: str,
        display_name: str = "",
        runtime_family: str = "runtime",
        description: str = "",
        command_name: str = "run_task",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a new source plugin tree from a local template."""
        template = self.get_template(template_id, force_refresh=False)
        if template is None:
            return {
                "success": False,
                "error": f"Runtime plugin template not found: {template_id}",
                "source_dir": None,
                "files_created": [],
                "files_overwritten": [],
            }

        normalized_plugin_id = sanitize_plugin_identifier(plugin_id or "")
        if not normalized_plugin_id:
            return {
                "success": False,
                "error": "Plugin id is required.",
                "source_dir": None,
                "files_created": [],
                "files_overwritten": [],
            }

        self.ensure_source_root()
        target_dir = self.source_plugin_dir(normalized_plugin_id)
        replacements = self._template_replacements(
            plugin_id=normalized_plugin_id,
            display_name=display_name,
            runtime_family=runtime_family,
            description=description,
            command_name=command_name,
        )

        template_files = [
            item
            for item in sorted(template.template_dir.rglob("*"), key=lambda path: str(path.relative_to(template.template_dir)).lower())
            if item.is_file() and item.name != "template.json"
        ]
        existing = [target_dir / item.relative_to(template.template_dir) for item in template_files if (target_dir / item.relative_to(template.template_dir)).exists()]
        if existing and not overwrite:
            return {
                "success": False,
                "error": "Target source plugin already exists. Pass overwrite=True to refresh template-managed files.",
                "source_dir": target_dir,
                "files_created": [],
                "files_overwritten": [str(item.relative_to(target_dir)) for item in existing[:12]],
            }

        target_dir.mkdir(parents=True, exist_ok=True)
        files_created: list[str] = []
        files_overwritten: list[str] = []

        for source_path in template_files:
            relative_path = source_path.relative_to(template.template_dir)
            destination = target_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            existed_before = destination.exists()
            self._copy_template_file(source_path, destination, replacements)
            relative_text = str(relative_path)
            if existed_before:
                files_overwritten.append(relative_text)
            else:
                files_created.append(relative_text)

        validation = self.validate_source_plugin(normalized_plugin_id)
        return {
            "success": bool(validation.get("success", False)),
            "error": "" if validation.get("success", False) else "; ".join(validation.get("errors", []) or ["Template scaffold validation failed."]),
            "source_dir": target_dir,
            "template_id": template.template_id,
            "files_created": files_created,
            "files_overwritten": files_overwritten,
            "validation": validation,
        }

    def validate_source_plugin(self, plugin_id: str) -> dict[str, Any]:
        """Validate a source plugin tree under `plugins/<plugin-id>`."""
        source_dir = self.source_plugin_dir(plugin_id)
        return self._validate_source_plugin_dir(source_dir)

    def build_source_plugin(
        self,
        plugin_id: str,
        *,
        install: bool = False,
        overwrite_install: bool = False,
    ) -> dict[str, Any]:
        """Run declared build commands for one source plugin and optionally install it."""
        validation = self.validate_source_plugin(plugin_id)
        if not validation.get("success"):
            return {
                "success": False,
                "error": "; ".join(validation.get("errors", []) or ["Source plugin validation failed."]),
                "validation": validation,
                "commands": [],
            }

        source_dir = validation.get("source_dir")
        if not isinstance(source_dir, Path):
            return {
                "success": False,
                "error": "Source plugin directory could not be resolved.",
                "validation": validation,
                "commands": [],
            }

        build_commands = [str(item).strip() for item in validation.get("build_commands", []) if str(item).strip()]
        if not build_commands:
            return {
                "success": False,
                "error": "This plugin does not declare any build commands.",
                "validation": validation,
                "commands": [],
            }

        command_results: list[dict[str, Any]] = []
        for command_text in build_commands:
            result = self._run_build_command(source_dir, command_text)
            command_results.append(result)
            if not result.get("success", False):
                return {
                    "success": False,
                    "error": str(result.get("error") or f"Build command failed: {command_text}"),
                    "validation": validation,
                    "commands": command_results,
                }

        post_validation = self.validate_source_plugin(plugin_id)
        if post_validation.get("delivery") in {"python-exe", "plugin-exe"} and post_validation.get("compiled_entry_path") is None:
            return {
                "success": False,
                "error": "Build completed, but no packaged entry was produced at the manifest-declared compiled path.",
                "validation": post_validation,
                "commands": command_results,
            }

        install_result: Optional[dict[str, Any]] = None
        if install:
            install_result = self.install_source_plugin(plugin_id, overwrite=overwrite_install)
            if not install_result.get("success", False):
                return {
                    "success": False,
                    "error": str(install_result.get("error") or "Plugin install failed after build."),
                    "validation": post_validation,
                    "commands": command_results,
                    "install_result": install_result,
                }

        return {
            "success": bool(post_validation.get("success", False)),
            "error": "" if post_validation.get("success", False) else "; ".join(post_validation.get("errors", []) or ["Post-build validation failed."]),
            "validation": post_validation,
            "commands": command_results,
            "install_result": install_result,
        }

    def install_source_plugin(self, plugin_id: str, *, overwrite: bool = False) -> dict[str, Any]:
        """Sync one source plugin tree into `.reverie/plugins/<plugin-id>`."""
        validation = self.validate_source_plugin(plugin_id)
        if not validation.get("success"):
            return {
                "success": False,
                "error": "; ".join(validation.get("errors", []) or ["Source plugin validation failed."]),
                "validation": validation,
            }

        source_dir = validation.get("source_dir")
        if not isinstance(source_dir, Path):
            return {"success": False, "error": "Source plugin directory could not be resolved.", "validation": validation}

        normalized_plugin_id = sanitize_plugin_identifier(validation.get("plugin_id") or plugin_id)
        target_dir = (self.install_root / normalized_plugin_id).resolve()
        self.ensure_install_root()

        merge_existing_sdk_depot = target_dir.exists() and normalized_plugin_id in self.catalog and not overwrite
        if target_dir.exists():
            if not overwrite and not merge_existing_sdk_depot:
                return {
                    "success": False,
                    "error": f"Install target already exists: {target_dir}. Pass overwrite=True to replace it.",
                    "target_dir": target_dir,
                    "validation": validation,
                }
            if overwrite:
                self._safe_remove_tree(self.install_root, target_dir)

        ignore_patterns = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.spec", "*.zip", ".pytest_cache", ".mypy_cache", ".ruff_cache", "build")
        if merge_existing_sdk_depot:
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True, ignore=ignore_patterns)
        else:
            shutil.copytree(source_dir, target_dir, ignore=ignore_patterns)

        self.scan()
        installed_record = self.get_record(normalized_plugin_id, force_refresh=False)
        return {
            "success": True,
            "error": "",
            "source_dir": source_dir,
            "target_dir": target_dir,
            "merged": merge_existing_sdk_depot,
            "validation": validation,
            "record": installed_record,
        }

    def list_template_rows(self, *, force_refresh: bool = False) -> list[dict[str, str]]:
        """Return normalized rows for CLI rendering."""
        rows: list[dict[str, str]] = []
        for record in self.list_templates(force_refresh=force_refresh):
            rows.append(
                {
                    "id": record.template_id,
                    "name": record.display_name,
                    "delivery": record.delivery,
                    "entry_template": record.entry_template or "-",
                    "manifest_template": record.manifest_template or "-",
                    "build_hint": record.build_hint or "",
                    "template_dir": str(record.template_dir),
                    "description": record.description,
                }
            )
        return rows

    def list_display_rows(self, *, force_refresh: bool = False) -> list[dict[str, str]]:
        """Return normalized rows for CLI rendering."""
        snapshot = self.get_snapshot(force_refresh=force_refresh)
        rows: list[dict[str, str]] = []
        for record in snapshot.records:
            notes = record.detail.strip()
            if record.protocol_error:
                notes = record.protocol_error
            elif record.manifest_warnings:
                notes = " | ".join(record.manifest_warnings[:2])
            elif not notes and record.version:
                notes = f"Version {record.version}"
            elif not notes and record.source_repo_hint:
                notes = record.source_repo_hint
            rows.append(
                {
                    "id": record.plugin_id,
                    "name": record.display_name,
                    "family": record.runtime_family,
                    "delivery": record.delivery_label,
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
        """Return a compact system-prompt addendum for plugin management."""
        snapshot = self.get_snapshot(force_refresh=False)
        lines = [
            "## Runtime Plugins",
            "- Plugins provide portable, plugin-local SDK/runtime environments under the app data `.reverie/plugins` directory.",
            "- Protocol-ready plugins expose `rc_<plugin>_<command>` tools directly to the model when their command metadata allows the active mode.",
            "- Use plugin tools for environment deployment, executable discovery, software launch, and runtime execution; use built-in authoring tools for planning and content generation.",
            "- The official Blender plugin embeds Blender Portable in its plugin executable; call `rc_blender_ensure_runtime` before `rc_blender_run_script` when direct Blender execution is needed.",
        ]
        if not snapshot.records:
            lines.append("- No plugin directories are currently detected under `.reverie/plugins`.")
        else:
            ready = [record for record in snapshot.records if record.protocol_supported and record.protocol_tool_count]
            if ready:
                preview = ", ".join(f"{record.plugin_id} ({record.protocol_tool_count} tools)" for record in ready[:5])
                if len(ready) > 5:
                    preview = f"{preview}, +{len(ready) - 5} more"
                lines.append(f"- Protocol tool providers detected: {preview}.")
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
        entry_bundle = self._resolve_manifest_entry_bundle(raw_manifest, install_dir)
        entry_path = entry_bundle.get("entry_path")
        source = "manifest"
        if entry_path is None and spec is not None:
            entry_path = self._resolve_from_candidates(install_dir, spec.entry_candidates)
            if entry_path is not None:
                source = "manifest+catalog"

        if source == "manifest+catalog" and entry_bundle.get("compiled_entry_path") is None:
            entry_bundle["compiled_entry_path"] = entry_path

        status = "ready" if entry_path is not None else "entry-missing"
        detail = str(entry_bundle.get("detail") or "").strip()
        if not detail:
            detail = "Entry executable detected." if status == "ready" else "plugin.json exists but no valid manifest entry or fallback was found."

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
            manifest_schema_version=str(entry_bundle.get("manifest_schema_version") or ""),
            packaging_format=str(entry_bundle.get("packaging_format") or delivery),
            entry_strategy=str(entry_bundle.get("entry_strategy") or ""),
            template_id=str(entry_bundle.get("template_id") or ""),
            compiled_entry_path=entry_bundle.get("compiled_entry_path"),
            source_entry_path=entry_bundle.get("source_entry_path"),
            build_commands=tuple(entry_bundle.get("build_commands") or ()),
            manifest_warnings=tuple(entry_bundle.get("manifest_warnings") or ()),
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
            packaging_format=spec.delivery,
            entry_strategy="catalog-auto-detect",
            compiled_entry_path=entry_path,
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
            packaging_format="plugin-exe",
            entry_strategy="directory-auto-detect",
            compiled_entry_path=entry_path,
        )

    def _merge_catalog_defaults(self, record: RuntimePluginRecord, spec: RuntimePluginSpec) -> RuntimePluginRecord:
        if record.entry_path is None:
            detected_entry = self._resolve_from_candidates(record.install_dir, spec.entry_candidates)
            if detected_entry is not None:
                return replace(
                    record,
                    display_name=record.display_name or spec.display_name,
                    runtime_family=record.runtime_family or spec.runtime_family,
                    status="ready",
                    source="manifest+catalog" if record.source == "manifest" else "auto-detect",
                    detail="Entry executable detected.",
                    description=record.description or spec.description,
                    entry_path=detected_entry,
                    delivery=record.delivery or spec.delivery,
                    source_repo_hint=record.source_repo_hint or spec.source_repo_hint,
                    capabilities=record.capabilities or spec.capabilities,
                    catalog_managed=True,
                    packaging_format=record.packaging_format or spec.delivery,
                    entry_strategy=record.entry_strategy or "catalog-auto-detect",
                    compiled_entry_path=record.compiled_entry_path or detected_entry,
                )

        return replace(
            record,
            display_name=record.display_name or spec.display_name,
            runtime_family=record.runtime_family or spec.runtime_family,
            detail=record.detail or spec.description,
            description=record.description or spec.description,
            delivery=record.delivery or spec.delivery,
            source_repo_hint=record.source_repo_hint or spec.source_repo_hint,
            capabilities=record.capabilities or spec.capabilities,
            catalog_managed=True,
            packaging_format=record.packaging_format or spec.delivery,
        )

    def _attach_protocol(self, record: RuntimePluginRecord) -> RuntimePluginRecord:
        if not record.is_ready or record.entry_path is None:
            return replace(record, protocol_status="no-entry", protocol_error="", protocol=None)
        if record.delivery_label == "sdk-runtime" and record.manifest_path is None:
            return replace(record, protocol_status="sdk-only", protocol_error="", protocol=None)

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
        return replace(
            record,
            display_name=display_name,
            runtime_family=runtime_family,
            description=description,
            version=version,
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
                    "include_modes": list(command.include_modes),
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
        plugin_root = entry_path.parent
        if plugin_root.name.lower() == "dist" and (plugin_root.parent / "plugin.json").exists():
            plugin_root = plugin_root.parent
        env = dict(os.environ)
        env.setdefault("REVERIE_PLUGIN_ROOT", str(plugin_root.resolve(strict=False)))
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
                env=env,
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

    def _manifest_entry_candidates(self, raw_value: Any) -> tuple[str, ...]:
        if isinstance(raw_value, str):
            value = raw_value.strip()
            return (value,) if value else tuple()
        if isinstance(raw_value, list):
            return _normalize_string_tuple(raw_value)
        if isinstance(raw_value, dict):
            preferred = raw_value.get(self._platform)
            default = raw_value.get("default")
            candidates = list(_normalize_string_tuple(preferred))
            for item in _normalize_string_tuple(default):
                if item not in candidates:
                    candidates.append(item)
            path_value = str(raw_value.get("path") or "").strip()
            if path_value and path_value not in candidates:
                candidates.append(path_value)
            return tuple(candidates)
        return tuple()

    def _resolve_entry_candidates(self, install_dir: Path, candidates: Iterable[str]) -> Optional[Path]:
        for candidate in candidates:
            resolved = self._resolve_relative_entry(install_dir, candidate)
            if resolved is not None:
                return resolved
        return None

    def _resolve_manifest_entry_bundle(self, raw_manifest: dict[str, Any], install_dir: Path) -> dict[str, Any]:
        entry = raw_manifest.get("entry")
        packaging = raw_manifest.get("packaging") if isinstance(raw_manifest.get("packaging"), dict) else {}
        delivery = str(raw_manifest.get("delivery") or raw_manifest.get("distribution") or "").strip() or "plugin-exe"
        manifest_schema_version = str(raw_manifest.get("schema_version") or "").strip()
        packaging_format = str(packaging.get("format") or delivery).strip() or delivery
        template_id = str(raw_manifest.get("template") or packaging.get("template") or "").strip()

        legacy_entry_candidates: tuple[str, ...] = tuple()
        preferred_candidates: tuple[str, ...] = tuple()
        fallback_candidates: tuple[str, ...] = tuple()
        strategy = str(packaging.get("entry_strategy") or "").strip().lower()
        allow_source_fallback = False

        if isinstance(entry, dict) and any(key in entry for key in ("preferred", "fallbacks", "strategy", "allow_source_fallback")):
            preferred_candidates = self._manifest_entry_candidates(entry.get("preferred"))
            fallback_candidates = self._manifest_entry_candidates(entry.get("fallbacks"))
            strategy = str(entry.get("strategy") or strategy).strip().lower()
            allow_source_fallback = bool(entry.get("allow_source_fallback", False))
        else:
            legacy_entry_candidates = self._manifest_entry_candidates(entry)

        compiled_candidates = list(self._manifest_entry_candidates(packaging.get("compiled")))
        source_candidates = list(self._manifest_entry_candidates(packaging.get("source")))

        executable_candidates = self._manifest_entry_candidates(raw_manifest.get("executable"))
        for candidate in executable_candidates:
            if candidate not in compiled_candidates:
                compiled_candidates.append(candidate)

        if not strategy:
            if delivery in {"python-exe", "plugin-exe"} or compiled_candidates:
                strategy = "prefer-packaged"
            else:
                strategy = "direct"

        if strategy == "direct" and legacy_entry_candidates:
            preferred_runtime_candidates = list(legacy_entry_candidates)
        else:
            preferred_runtime_candidates = list(preferred_candidates)
            for candidate in compiled_candidates:
                if candidate not in preferred_runtime_candidates:
                    preferred_runtime_candidates.append(candidate)
            if strategy == "direct":
                for candidate in legacy_entry_candidates:
                    if candidate not in preferred_runtime_candidates:
                        preferred_runtime_candidates.append(candidate)

        fallback_runtime_candidates = list(fallback_candidates)
        for candidate in source_candidates:
            if candidate not in fallback_runtime_candidates:
                fallback_runtime_candidates.append(candidate)
        if strategy != "direct":
            for candidate in legacy_entry_candidates:
                if candidate not in fallback_runtime_candidates:
                    fallback_runtime_candidates.append(candidate)

        compiled_entry = self._resolve_entry_candidates(install_dir, preferred_runtime_candidates)
        source_entry = self._resolve_entry_candidates(install_dir, fallback_runtime_candidates)
        selected_entry = compiled_entry
        selected_mode = "packaged" if compiled_entry is not None else ""
        detail = "Entry executable detected."
        warnings: list[str] = []

        if selected_entry is None:
            if source_entry is not None and (allow_source_fallback or strategy != "direct" or not preferred_runtime_candidates):
                selected_entry = source_entry
                selected_mode = "source-fallback"
                detail = "Packaged entry missing; using Python/script source fallback."
            elif source_entry is not None and strategy == "direct":
                selected_entry = source_entry
                selected_mode = "source"
                detail = "Manifest entry detected."
        elif source_entry is not None and selected_entry == source_entry and strategy == "direct":
            selected_mode = "source"
            detail = "Manifest entry detected."

        build_commands = tuple(_normalize_string_tuple((packaging.get("build") or {}).get(self._platform) if isinstance(packaging.get("build"), dict) else packaging.get("build")))
        if not build_commands and isinstance(packaging.get("build"), dict):
            build_commands = tuple(_normalize_string_tuple(packaging.get("build", {}).get("default")))

        if delivery == "python-exe" and source_entry is None:
            warnings.append("python-exe plugin has no source fallback entry defined.")
        if delivery == "python-exe" and not build_commands:
            warnings.append("python-exe plugin does not declare build commands in plugin.json packaging.build.")
        if selected_entry is None:
            detail = "plugin.json exists but no valid manifest entry or fallback was found."

        return {
            "entry_path": selected_entry,
            "compiled_entry_path": compiled_entry if selected_mode == "packaged" else None,
            "source_entry_path": source_entry,
            "entry_strategy": strategy or "direct",
            "manifest_schema_version": manifest_schema_version,
            "packaging_format": packaging_format,
            "template_id": template_id,
            "build_commands": build_commands,
            "detail": detail,
            "manifest_warnings": tuple(warnings),
        }

    def _scan_templates(self) -> tuple[RuntimePluginTemplateRecord, ...]:
        root = self.template_root
        if not root.exists():
            return tuple()

        records: list[RuntimePluginTemplateRecord] = []
        for candidate in sorted([item for item in root.iterdir() if item.is_dir()], key=lambda path: path.name.lower()):
            template_json = candidate / "template.json"
            payload: dict[str, Any] = {}
            if template_json.exists():
                loaded, _ = self._load_manifest(template_json)
                if isinstance(loaded, dict):
                    payload = loaded
            template_id = str(payload.get("id") or candidate.name).strip() or candidate.name
            records.append(
                RuntimePluginTemplateRecord(
                    template_id=template_id,
                    display_name=str(payload.get("display_name") or template_id).strip() or template_id,
                    description=str(payload.get("description") or "").strip(),
                    delivery=str(payload.get("delivery") or "plugin-exe").strip() or "plugin-exe",
                    template_dir=candidate,
                    entry_template=str(payload.get("entry_template") or "plugin.py").strip(),
                    manifest_template=str(payload.get("manifest_template") or "plugin.json").strip(),
                    build_hint=str(payload.get("build_hint") or "").strip(),
                )
            )
        return tuple(records)

    def _template_replacements(
        self,
        *,
        plugin_id: str,
        display_name: str,
        runtime_family: str,
        description: str,
        command_name: str,
    ) -> dict[str, str]:
        readable_name = str(display_name or "").strip() or plugin_id.replace("_", " ").replace("-", " ").title()
        normalized_family = str(runtime_family or "runtime").strip() or "runtime"
        normalized_command = sanitize_plugin_identifier(command_name or "run_task")
        normalized_description = str(description or "").strip() or f"Reverie runtime plugin for {readable_name}."
        return {
            "{{plugin_id}}": plugin_id,
            "{{plugin_name}}": readable_name,
            "{{plugin_runtime_family}}": normalized_family,
            "{{plugin_description}}": normalized_description,
            "{{plugin_tool_name}}": normalized_command,
            "{{plugin_binary_name}}": f"reverie-{plugin_id}",
        }

    def _copy_template_file(self, source_path: Path, destination: Path, replacements: dict[str, str]) -> None:
        try:
            content = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            shutil.copy2(source_path, destination)
            return

        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)
        destination.write_text(content, encoding="utf-8")

    def _validate_source_plugin_dir(self, source_dir: Path) -> dict[str, Any]:
        resolved_source_dir = Path(source_dir).resolve()
        errors: list[str] = []
        warnings: list[str] = []
        manifest_path = resolved_source_dir / "plugin.json"

        if not resolved_source_dir.exists() or not resolved_source_dir.is_dir():
            return {
                "success": False,
                "plugin_id": resolved_source_dir.name,
                "source_dir": resolved_source_dir,
                "manifest_path": manifest_path,
                "errors": [f"Source plugin directory not found: {resolved_source_dir}"],
                "warnings": [],
                "build_commands": [],
                "unresolved_tokens": [],
            }

        if not manifest_path.exists():
            errors.append("plugin.json is missing from the source plugin directory.")
            return {
                "success": False,
                "plugin_id": resolved_source_dir.name,
                "source_dir": resolved_source_dir,
                "manifest_path": manifest_path,
                "errors": errors,
                "warnings": warnings,
                "build_commands": [],
                "unresolved_tokens": [],
            }

        record = self._attach_protocol(self._record_from_manifest(resolved_source_dir, manifest_path))
        unresolved_tokens = self._collect_unresolved_tokens(resolved_source_dir)
        if unresolved_tokens:
            errors.append("Unresolved template placeholders remain in the source plugin files.")

        warnings.extend(record.manifest_warnings)
        template_id = record.template_id
        if template_id and self.get_template(template_id, force_refresh=False) is None:
            warnings.append(f"Template `{template_id}` is referenced by plugin.json but is not available under plugins/_templates.")

        build_commands = list(record.build_commands)
        for command_text in build_commands:
            missing_script = self._detect_missing_local_command(command_text, resolved_source_dir)
            if missing_script:
                warnings.append(f"Build helper not found in source tree: {missing_script}")

        if record.delivery in {"python-exe", "plugin-exe"} and not build_commands:
            errors.append("No build commands are declared for this packaged runtime plugin.")
        if record.status == "invalid-manifest":
            errors.append(record.detail or "plugin.json is invalid.")
        if record.entry_path is None:
            errors.append("No valid source or packaged entry could be resolved from plugin.json.")

        return {
            "success": not errors,
            "plugin_id": record.plugin_id,
            "display_name": record.display_name,
            "runtime_family": record.runtime_family,
            "delivery": record.delivery,
            "source_dir": resolved_source_dir,
            "manifest_path": manifest_path,
            "entry_path": record.entry_path,
            "compiled_entry_path": record.compiled_entry_path,
            "source_entry_path": record.source_entry_path,
            "build_commands": build_commands,
            "protocol_status": record.protocol_status,
            "protocol_supported": record.protocol_supported,
            "template_id": template_id,
            "packaging_format": record.packaging_format,
            "entry_strategy": record.entry_strategy,
            "errors": errors,
            "warnings": warnings,
            "unresolved_tokens": unresolved_tokens,
            "record": record,
        }

    def _collect_unresolved_tokens(self, source_dir: Path) -> list[str]:
        token_pattern = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")
        matches: list[str] = []
        for item in sorted(source_dir.rglob("*"), key=lambda path: str(path).lower()):
            if not item.is_file():
                continue
            if item.name == "template.json":
                continue
            if item.suffix.lower() not in {".py", ".json", ".md", ".txt", ".bat", ".cmd", ".sh", ".ps1", ".yaml", ".yml"}:
                continue
            try:
                content = item.read_text(encoding="utf-8")
            except Exception:
                continue
            for token in token_pattern.findall(content):
                matches.append(f"{item.relative_to(source_dir)}: {token}")
                if len(matches) >= 32:
                    return matches
        return matches

    def _detect_missing_local_command(self, command_text: str, working_dir: Path) -> str:
        parts = self._tokenize_command(command_text)
        if not parts:
            return ""
        first = str(parts[0] or "").strip()
        if not first:
            return ""
        candidate = Path(first)
        looks_local = candidate.is_absolute() or any(separator in first for separator in ("/", "\\")) or candidate.suffix.lower() in {".bat", ".cmd", ".ps1", ".py", ".sh"}
        if not looks_local:
            return ""
        resolved = candidate if candidate.is_absolute() else (working_dir / candidate)
        return first if not resolved.exists() else ""

    def _run_build_command(self, working_dir: Path, command_text: str) -> dict[str, Any]:
        command = self._build_external_command(command_text, working_dir)
        if not command:
            return {
                "success": False,
                "command": command_text,
                "stdout": "",
                "stderr": "",
                "returncode": 1,
                "error": "Build command is empty.",
            }

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
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.BUILD_TIMEOUT_SECONDS,
                startupinfo=startupinfo,
                creationflags=creationflags,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "command": command_text,
                "stdout": str(getattr(exc, "stdout", "") or ""),
                "stderr": str(getattr(exc, "stderr", "") or ""),
                "returncode": None,
                "error": "Build command timed out.",
            }
        except Exception as exc:
            return {
                "success": False,
                "command": command_text,
                "stdout": "",
                "stderr": "",
                "returncode": None,
                "error": str(exc),
            }

        stdout = str(completed.stdout or "")
        stderr = str(completed.stderr or "")
        success = int(completed.returncode) == 0
        error = "" if success else (stderr.strip() or stdout.strip() or f"Exit code {completed.returncode}")
        return {
            "success": success,
            "command": command_text,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": int(completed.returncode),
            "error": error,
        }

    def _tokenize_command(self, command_text: str) -> list[str]:
        raw = str(command_text or "").strip()
        if not raw:
            return []
        try:
            return [part for part in shlex.split(raw, posix=not sys.platform.startswith("win")) if str(part).strip()]
        except ValueError:
            return [part for part in raw.split() if str(part).strip()]

    def _build_external_command(self, command_text: str, working_dir: Path) -> list[str]:
        parts = self._tokenize_command(command_text)
        if not parts:
            return []

        raw_program = str(parts[0] or "").strip()
        remaining = parts[1:]
        resolved_program = self._resolve_local_command_path(raw_program, working_dir)
        program = str(resolved_program or raw_program)
        suffix = Path(program).suffix.lower()

        if suffix in {".cmd", ".bat"}:
            return ["cmd.exe", "/d", "/c", program, *remaining]
        if suffix == ".ps1":
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", program, *remaining]
        if suffix == ".py":
            return [sys.executable, program, *remaining]
        return [program, *remaining]

    def _resolve_local_command_path(self, raw_program: str, working_dir: Path) -> Optional[Path]:
        text = str(raw_program or "").strip()
        if not text:
            return None
        candidate = Path(text)
        if candidate.is_absolute():
            return candidate if candidate.exists() else None
        looks_local = any(separator in text for separator in ("/", "\\")) or candidate.suffix.lower() in {".cmd", ".bat", ".ps1", ".py", ".sh"}
        if not looks_local:
            return None
        resolved = (working_dir / candidate).resolve(strict=False)
        return resolved if resolved.exists() else None

    def _safe_remove_tree(self, root_dir: Path, target_dir: Path) -> None:
        resolved_root = Path(root_dir).resolve(strict=False)
        resolved_target = Path(target_dir).resolve(strict=False)
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError as exc:
            raise RuntimeError(f"Refusing to remove a directory outside the intended root: {resolved_target}") from exc
        if resolved_target.exists():
            shutil.rmtree(resolved_target)

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

    def _archive_patterns_for_platform(self, spec: RuntimePluginSpec) -> tuple[str, ...]:
        patterns = list(spec.bundled_archive_candidates.get(self._platform, ()))
        patterns.extend(pattern for pattern in spec.bundled_archive_candidates.get("default", ()) if pattern not in patterns)
        return tuple(patterns)

    def _find_bundled_sdk_archive(self, spec: RuntimePluginSpec) -> Optional[Path]:
        patterns = self._archive_patterns_for_platform(spec)
        if not patterns:
            return None
        roots = _unique_paths(
            [
                self.app_root,
                self.install_root / spec.plugin_id,
                self.install_root,
                self.source_root,
                self.source_root / spec.plugin_id,
                self.app_root / "plugins",
                Path.cwd(),
                Path(sys.executable).resolve().parent,
            ]
        )
        for root in roots:
            if not root.exists():
                continue
            for pattern in patterns:
                for match in sorted(root.glob(pattern), key=lambda path: str(path).lower()):
                    if match.exists() and match.is_file() and match.suffix.lower() == ".zip":
                        return match.resolve(strict=False)
        return None

    def _resolve_sdk_archive(self, spec: RuntimePluginSpec, archive_path: Any = "") -> Optional[Path]:
        raw = str(archive_path or "").strip()
        if raw:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = self.app_root / candidate
            try:
                candidate = candidate.resolve(strict=False)
            except Exception:
                candidate = candidate.absolute()
            return candidate if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".zip" else None
        return self._find_bundled_sdk_archive(spec)

    def _safe_extract_zip(self, archive_path: Path, target_dir: Path) -> int:
        """Extract a zip archive while keeping all paths inside target_dir."""
        target = target_dir.resolve()
        target.mkdir(parents=True, exist_ok=True)
        count = 0
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                name = str(member.filename or "").replace("\\", "/")
                if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                    raise ValueError(f"Unsafe archive member path: {member.filename}")
                destination = (target / name).resolve()
                try:
                    destination.relative_to(target)
                except ValueError as exc:
                    raise ValueError(f"Archive member escapes SDK target: {member.filename}") from exc
                archive.extract(member, target)
                count += 1
        return count

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
