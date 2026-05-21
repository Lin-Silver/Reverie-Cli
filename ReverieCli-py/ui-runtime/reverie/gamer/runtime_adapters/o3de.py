"""O3DE runtime adapter for large-scale Reverie-Gamer slices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .base import BaseRuntimeAdapter, RuntimeProfile


def _safe_write(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _slug(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in str(value or "ReverieO3DE"))
    text = "_".join(part for part in text.split("_") if part)
    return text or "ReverieO3DE"


def _has_source_checkout(source_root: Path) -> bool:
    if not source_root.exists():
        return False
    for candidate in source_root.iterdir():
        if candidate.is_dir() and (
            (candidate / ".git").exists()
            or (candidate / "cmake").exists()
            or (candidate / "scripts" / "o3de.py").exists()
            or (candidate / "scripts" / "o3de.bat").exists()
        ):
            return True
    return False


def _read_runtime_manifest(manifest_path: Path) -> Dict[str, Any]:
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


class O3DERuntimeAdapter(BaseRuntimeAdapter):
    runtime_id = "o3de"
    display_name = "O3DE"
    external = True
    maturity = "experimental-scaffold"
    capability_tags = (
        "external-runtime",
        "large-scale-3d",
        "streaming",
        "data-heavy",
        "asset-processor-contract",
        "artifact-validation",
    )
    template_support = ("future-large-world", "action_rpg_slice")

    def detect(self, project_root: Path, app_root: Path | None = None) -> RuntimeProfile:
        root = Path(project_root).resolve()
        app = Path(app_root or project_root).resolve()
        runtime_root = root / "engine" / "o3de"
        plugin_root = app / ".reverie" / "plugins" / "o3de"
        plugin_source_root = plugin_root / "source"
        plugin_runtime_root = plugin_root / "runtime"
        manifest_path = plugin_runtime_root / "sdk_manifest.json"
        source_ready = _has_source_checkout(plugin_source_root)
        manifest = _read_runtime_manifest(manifest_path)
        scaffold_exists = (runtime_root / "project.json").exists()
        sdk_ready = source_ready or bool(manifest.get("source_dir"))
        health = "source-sdk-ready" if sdk_ready else ("artifact-validated" if scaffold_exists else "scaffold-ready")
        source = "source-sdk-plugin" if sdk_ready else ("project-scaffold" if scaffold_exists else "built-in-template")
        return RuntimeProfile(
            id=self.runtime_id,
            display_name=self.display_name,
            available=True,
            can_scaffold=True,
            can_validate=True,
            external=self.external,
            maturity=self.maturity,
            source=source,
            version=str(manifest.get("ref") or ""),
            capabilities=list(self.capability_tags) + ["source-sdk"],
            template_support=list(self.template_support),
            health=health,
            notes=[
                "Generates an O3DE-style project envelope with Gem, Asset Processor, registry, and data-contract starter files.",
                "Artifact validation is built in; native O3DE Editor/Asset Processor execution is enabled after the plugin-local source SDK is built.",
                "O3DE source and SDK metadata are expected under `.reverie/plugins/o3de`, not under the repository `references` tree.",
            ],
            paths={
                "runtime_root": str(runtime_root),
                "plugin_root": str(plugin_root),
                "plugin_source_root": str(plugin_source_root),
                "plugin_runtime_manifest": str(manifest_path),
                "source_checkout": str(manifest.get("source_dir") or ""),
            },
        )

    def recommend_template(self, game_request: Dict[str, Any]) -> str:
        return "future-large-world"

    def create_project(
        self,
        output_dir: Path,
        *,
        project_name: str,
        game_request: Dict[str, Any],
        blueprint: Dict[str, Any],
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        runtime_root = Path(output_dir) / "engine" / "o3de"
        project_slug = _slug(project_name)
        runtime_data = {
            "runtime": self.runtime_id,
            "project_name": project_name,
            "target": blueprint.get("meta", {}).get("scope", "vertical_slice"),
            "contracts": [
                "asset_registry",
                "asset_import_profile",
                "world_streaming",
                "combat_slice",
                "save_migration",
            ],
        }
        payloads = {
            runtime_root / "project.json": json.dumps(
                {
                    "project_name": project_slug,
                    "project_id": f"reverie.{project_slug.lower()}",
                    "origin": "Reverie-Gamer O3DE scaffold",
                    "gem_names": ["ReverieSliceGem"],
                },
                indent=2,
            ),
            runtime_root / "Registry" / "asset_registry.json": json.dumps(
                {"runtime": self.runtime_id, "assets_root": "Assets", "models_root": "Assets/Models"},
                indent=2,
            ),
            runtime_root / "Registry" / "asset_import_profile.json": json.dumps(
                {
                    "runtime": self.runtime_id,
                    "preferred_model_formats": [".glb", ".gltf", ".fbx"],
                    "validation": ["asset_processor_contract", "lod_group", "streaming_budget"],
                },
                indent=2,
            ),
            runtime_root / "Registry" / "runtime_contracts.json": json.dumps(runtime_data, indent=2),
            runtime_root / "Gems" / "ReverieSliceGem" / "gem.json": json.dumps(
                {
                    "gem_name": "ReverieSliceGem",
                    "display_name": "Reverie Slice Gem",
                    "version": "0.1.0",
                    "origin": "generated",
                },
                indent=2,
            ),
            runtime_root / "Scripts" / "slice_bootstrap.lua": (
                "-- Reverie-generated O3DE bootstrap marker.\n"
                "local ReverieSlice = {}\n"
                "ReverieSlice.runtime = 'o3de'\n"
                "return ReverieSlice\n"
            ),
            runtime_root / "Assets" / "README.md": (
                "# O3DE Assets\n\n"
                "Promote validated `assets/models/runtime` exports here after registry and budget checks.\n"
            ),
            runtime_root / "README.md": (
                f"# {project_name} O3DE Runtime\n\n"
                "This scaffold keeps O3DE project identity, Gem packaging, asset import contracts, and "
                "large-world data handoffs in-repo before native O3DE tooling is run.\n"
            ),
        }
        files: list[str] = []
        for path, content in payloads.items():
            if _safe_write(path, content, overwrite):
                files.append(str(path))
        return {
            "runtime": self.runtime_id,
            "runtime_root": str(runtime_root),
            "template": self.recommend_template(game_request),
            "directories": [
                str(runtime_root / relative)
                for relative in ("Assets", "Gems/ReverieSliceGem", "Registry", "Scripts")
            ],
            "files": files,
            "notes": [
                "Generated a repository-native O3DE runtime envelope with artifact validation support.",
                "Run native O3DE Editor/Asset Processor checks later when the external O3DE SDK is installed.",
            ],
        }

    def validate_project(self, output_dir: Path) -> Dict[str, Any]:
        runtime_root = Path(output_dir) / "engine" / "o3de"
        checks = [
            {"name": "project_json", "ok": (runtime_root / "project.json").exists()},
            {"name": "gem_manifest", "ok": (runtime_root / "Gems" / "ReverieSliceGem" / "gem.json").exists()},
            {"name": "asset_registry", "ok": (runtime_root / "Registry" / "asset_registry.json").exists()},
            {"name": "asset_import_profile", "ok": (runtime_root / "Registry" / "asset_import_profile.json").exists()},
            {"name": "runtime_contracts", "ok": (runtime_root / "Registry" / "runtime_contracts.json").exists()},
            {"name": "bootstrap_script", "ok": (runtime_root / "Scripts" / "slice_bootstrap.lua").exists()},
        ]
        return {
            "valid": all(item["ok"] for item in checks),
            "checks": checks,
            "project_root": str(runtime_root),
            "validation_mode": "artifact_validation",
            "notes": ["Native O3DE SDK execution is optional and can be layered on top of this scaffold."],
        }
