"""Game auxiliary model plugin for Reverie CLI.

The plugin manages optional local model packages for Reverie-Gamer. It is a
deployment/control layer: it prepares a plugin-local Python environment,
downloads or registers model snapshots, and writes manifests that other tools
can consume. Heavy research models are never executed by default.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import re
import shutil
import subprocess
import sys
import venv


PLUGIN_VERSION = "0.2.0"
PLUGIN_ID = "game_models"


MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "id": "stable-fast-3d",
        "display_name": "Stable Fast 3D",
        "repo_id": "stabilityai/stable-fast-3d",
        "task": "image_to_3d_asset",
        "license_family": "open-source-model",
        "recommended_for_8gb_vram": True,
        "min_ram_gb": 16,
        "min_vram_gb": 6,
        "default_profile": "low_vram",
        "memory_profiles": [
            {
                "id": "low_vram",
                "label": "8GB low-VRAM image-to-3D",
                "min_ram_gb": 16,
                "min_vram_gb": 6,
                "notes": "Use for fast concept-image-to-mesh candidates before Blender cleanup.",
            }
        ],
        "deployment": "huggingface_snapshot",
        "default_enabled": True,
        "pipeline_role": "Generate mesh-ready 3D asset candidates from concept images produced by the TTI pipeline.",
    },
    {
        "id": "tripo-sr",
        "display_name": "TripoSR",
        "repo_id": "stabilityai/TripoSR",
        "task": "image_to_3d_asset",
        "license_family": "open-source-model",
        "recommended_for_8gb_vram": True,
        "min_ram_gb": 16,
        "min_vram_gb": 8,
        "default_profile": "low_vram",
        "memory_profiles": [
            {
                "id": "low_vram",
                "label": "8GB image-to-3D fallback",
                "min_ram_gb": 16,
                "min_vram_gb": 8,
                "notes": "Use when the user has an 8GB GPU and wants a local reconstruction fallback.",
            }
        ],
        "deployment": "huggingface_snapshot",
        "default_enabled": True,
        "pipeline_role": "Fallback image-to-3D reconstruction model for local asset ideation on smaller GPUs.",
    },
    {
        "id": "hunyuan3d-2mini",
        "display_name": "Hunyuan3D 2 Mini",
        "repo_id": "tencent/Hunyuan3D-2mini",
        "task": "image_to_3d_asset",
        "license_family": "tencent-hunyuan-community",
        "recommended_for_8gb_vram": True,
        "min_ram_gb": 24,
        "min_vram_gb": 8,
        "default_profile": "low_vram",
        "memory_profiles": [
            {
                "id": "low_vram",
                "label": "8GB image-to-3D mini",
                "min_ram_gb": 24,
                "min_vram_gb": 8,
                "notes": "Small Hunyuan3D image-to-3D lane; use lower chunk/resolution settings in the eventual runner.",
            }
        ],
        "deployment": "huggingface_snapshot",
        "default_enabled": True,
        "pipeline_role": "Image-to-3D candidate model for higher-quality mesh ideation after local TTI concept generation.",
    },
    {
        "id": "trellis-text-xlarge",
        "display_name": "TRELLIS Text XLarge",
        "repo_id": "microsoft/TRELLIS-text-xlarge",
        "task": "text_to_3d_asset",
        "license_family": "open-source-research-model",
        "recommended_for_8gb_vram": True,
        "min_ram_gb": 24,
        "min_vram_gb": 8,
        "default_profile": "low_vram",
        "memory_profiles": [
            {
                "id": "low_vram",
                "label": "8GB low-VRAM text-to-3D",
                "min_ram_gb": 24,
                "min_vram_gb": 8,
                "notes": "8GB attempt profile; prefer smaller generation counts, offload-friendly execution, and Blender cleanup after export.",
            },
            {
                "id": "balanced",
                "label": "12GB balanced text-to-3D",
                "min_ram_gb": 24,
                "min_vram_gb": 12,
                "notes": "Balanced local profile for higher fidelity sampling while keeping workstation pressure moderate.",
            },
            {
                "id": "quality",
                "label": "16GB quality text-to-3D",
                "min_ram_gb": 32,
                "min_vram_gb": 16,
                "notes": "Closer to published/research guidance; use when available for fewer low-memory compromises.",
            },
        ],
        "deployment": "huggingface_snapshot",
        "default_enabled": True,
        "requires_allow_heavy": False,
        "pipeline_role": "Primary local text-to-3D candidate for 8GB VRAM workstations; generate a candidate mesh, then pass through Blender cleanup, retopo, materials, and rig validation.",
    },
    {
        "id": "hy-motion-1.0",
        "display_name": "HY-Motion 1.0",
        "repo_id": "tencent/HY-Motion-1.0",
        "task": "human_motion_generation",
        "license_family": "open-source-research-model",
        "recommended_for_8gb_vram": False,
        "min_ram_gb": 32,
        "min_vram_gb": 16,
        "default_profile": "research",
        "memory_profiles": [
            {
                "id": "research",
                "label": "research motion-generation",
                "min_ram_gb": 32,
                "min_vram_gb": 16,
                "requires_allow_heavy": True,
                "notes": "Use as an optional motion lane after the playable character skeleton is stable.",
            }
        ],
        "deployment": "huggingface_snapshot",
        "default_enabled": False,
        "requires_allow_heavy": True,
        "pipeline_role": "Human motion auxiliary model; useful for animation ideation but too heavy for the default 8GB VRAM profile.",
    },
]


class ReverieRuntimePluginHost:
    """Small inlined host for Reverie CLI's fixed `-RC` plugin protocol."""

    def build_handshake(self) -> dict[str, Any]:
        raise NotImplementedError

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def write_json(self, payload: dict[str, Any]) -> int:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
        sys.stdout.flush()
        return 0

    def run(self, argv: list[str]) -> int:
        if len(argv) >= 2 and argv[1] == "-RC":
            return self.write_json(self.build_handshake())

        if len(argv) >= 2 and argv[1] == "-RC-CALL":
            if len(argv) < 4:
                return self.write_json(
                    {"success": False, "output": "", "error": "Usage: -RC-CALL <command> <json-payload>", "data": {}}
                )
            command_name = str(argv[2] or "").strip().lower()
            raw_payload = str(argv[3] or "").strip()
            try:
                payload = json.loads(raw_payload) if raw_payload else {}
            except Exception as exc:
                return self.write_json({"success": False, "output": "", "error": f"Invalid JSON payload: {exc}", "data": {}})
            try:
                result = self.handle_command(command_name, payload)
            except Exception as exc:
                result = {"success": False, "output": "", "error": str(exc), "data": {}}
            if not isinstance(result, dict):
                result = {"success": False, "output": "", "error": "Plugin command handler must return a JSON object.", "data": {}}
            result.setdefault("success", False)
            result.setdefault("output", "")
            result.setdefault("error", "")
            result.setdefault("data", {})
            return self.write_json(result)

        sys.stderr.write("This runtime plugin only supports -RC and -RC-CALL.\n")
        return 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "model"


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _memory_profiles(model: dict[str, Any]) -> list[dict[str, Any]]:
    raw_profiles = model.get("memory_profiles", [])
    if not isinstance(raw_profiles, list) or not raw_profiles:
        return [
            {
                "id": str(model.get("default_profile") or "default"),
                "label": "default",
                "min_ram_gb": int(model.get("min_ram_gb", 0) or 0),
                "min_vram_gb": int(model.get("min_vram_gb", 0) or 0),
                "notes": "Default hardware profile.",
            }
        ]
    profiles: list[dict[str, Any]] = []
    for profile in raw_profiles:
        if isinstance(profile, dict):
            profiles.append(dict(profile))
    return profiles


def _resolve_memory_profile(
    model: dict[str, Any],
    requested_profile: Any = "",
    *,
    ram_gb: int | None = None,
    vram_gb: int | None = None,
) -> dict[str, Any]:
    profiles = _memory_profiles(model)
    requested = str(requested_profile or "").strip().lower()
    if requested:
        for profile in profiles:
            if str(profile.get("id", "")).strip().lower() == requested:
                return dict(profile)
    if ram_gb is not None and vram_gb is not None:
        fitting = [
            profile
            for profile in profiles
            if int(profile.get("min_ram_gb", 0) or 0) <= ram_gb
            and int(profile.get("min_vram_gb", 0) or 0) <= vram_gb
        ]
        if fitting:
            return dict(fitting[0])
    default_profile = str(model.get("default_profile") or "").strip().lower()
    for profile in profiles:
        if str(profile.get("id", "")).strip().lower() == default_profile:
            return dict(profile)
    return dict(profiles[0])


class GameModelsPlugin(ReverieRuntimePluginHost):
    """Manage optional local model packages for the Reverie-Gamer asset lane."""

    def __init__(self) -> None:
        self.plugin_root = self._resolve_plugin_root()
        self.model_root = self.plugin_root / "models"
        self.venv_root = self.plugin_root / "venv"
        self.cache_root = self.plugin_root / "cache"
        self.state_path = self.plugin_root / "state" / "model_state.json"

    def _resolve_plugin_root(self) -> Path:
        override = os.getenv("REVERIE_PLUGIN_ROOT")
        if override:
            return Path(override).expanduser().resolve()
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def _ensure_inside_plugin(self, path: Path) -> Path:
        resolved = path.resolve()
        root = self.plugin_root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"Refusing to write outside plugin root: {resolved}")
        return resolved

    def _catalog_by_id(self) -> dict[str, dict[str, Any]]:
        return {str(item["id"]): dict(item) for item in MODEL_CATALOG}

    def _resolve_model(self, model_id: Any = "", repo_id: Any = "") -> dict[str, Any]:
        catalog = self._catalog_by_id()
        requested = str(model_id or "").strip()
        if requested in catalog:
            return dict(catalog[requested])
        requested_repo = str(repo_id or "").strip()
        for item in catalog.values():
            if requested_repo and str(item.get("repo_id", "")).lower() == requested_repo.lower():
                return dict(item)
        if requested_repo:
            return {
                "id": _safe_slug(requested_repo),
                "display_name": requested_repo,
                "repo_id": requested_repo,
                "task": "custom_auxiliary_model",
                "recommended_for_8gb_vram": False,
                "min_ram_gb": 24,
                "min_vram_gb": 8,
                "default_profile": "low_vram",
                "memory_profiles": [
                    {
                        "id": "low_vram",
                        "label": "8GB custom model attempt",
                        "min_ram_gb": 24,
                        "min_vram_gb": 8,
                        "requires_allow_heavy": True,
                        "notes": "Unknown custom model; require explicit opt-in before download.",
                    }
                ],
                "deployment": "huggingface_snapshot",
                "default_enabled": False,
                "requires_allow_heavy": True,
                "pipeline_role": "User-specified auxiliary model.",
            }
        raise ValueError("model_id or repo_id is required.")

    def _python_executable(self) -> Path:
        if os.name == "nt":
            return self.venv_root / "Scripts" / "python.exe"
        return self.venv_root / "bin" / "python"

    def _state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"schema": "reverie.game_models.state.v1", "models": {}, "updated_at": ""}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema": "reverie.game_models.state.v1", "models": {}, "updated_at": ""}

    def _write_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _utc_now()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _model_dir(self, model: dict[str, Any]) -> Path:
        return self._ensure_inside_plugin(self.model_root / _safe_slug(model.get("id")))

    def _subprocess_env(self) -> dict[str, str]:
        """Keep downloader/cache activity inside the plugin depot."""
        cache_root = self._ensure_inside_plugin(self.cache_root)
        hf_home = cache_root / "huggingface"
        pip_cache = cache_root / "pip"
        hf_home.mkdir(parents=True, exist_ok=True)
        pip_cache.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HF_HOME"] = str(hf_home)
        env["HF_HUB_CACHE"] = str(hf_home / "hub")
        env["TRANSFORMERS_CACHE"] = str(hf_home / "transformers")
        env["PIP_CACHE_DIR"] = str(pip_cache)
        env["XDG_CACHE_HOME"] = str(cache_root)
        return env

    def build_handshake(self) -> dict[str, Any]:
        return {
            "protocol_version": "1.0",
            "plugin_id": PLUGIN_ID,
            "display_name": "Game Auxiliary Models",
            "version": PLUGIN_VERSION,
            "runtime_family": "model-depot",
            "description": "Plugin-local deployment manager for open auxiliary game asset models.",
            "tool_call_hint": (
                "Use rc_game_models_list_models to inspect supported models, "
                "rc_game_models_select_model to persist the chosen model/profile, "
                "rc_game_models_prepare_environment to create the plugin-local venv, "
                "rc_game_models_download_model to download a HuggingFace snapshot, and "
                "rc_game_models_model_status before claiming a model is available."
            ),
            "system_prompt": (
                "This plugin manages model packages only inside its plugin-local depot. "
                "Do not download model files to C:\\Users, global cache folders, or system SDK paths. "
                "TRELLIS Text XLarge supports an 8GB low_vram attempt profile; HY-Motion remains guarded by allow_heavy."
            ),
            "commands": [
                {
                    "name": "list_models",
                    "description": "List known auxiliary model packages and their hardware fit.",
                    "parameters": {"type": "object", "properties": {"only_8gb": {"type": "boolean"}}, "required": []},
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
                {
                    "name": "deployment_plan",
                    "description": "Return a recommended local model deployment plan for a RAM/VRAM budget.",
                    "parameters": {
                        "type": "object",
                        "properties": {"ram_gb": {"type": "integer"}, "vram_gb": {"type": "integer"}},
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
                {
                    "name": "prepare_environment",
                    "description": "Create the plugin-local Python venv and optionally install lightweight downloader packages.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "install_packages": {"type": "boolean"},
                            "force": {"type": "boolean"},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
                {
                    "name": "ensure_runtime",
                    "description": "Ensure the plugin-local downloader runtime exists. Alias for prepare_environment.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "install_packages": {"type": "boolean"},
                            "force": {"type": "boolean"},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
                {
                    "name": "model_status",
                    "description": "Inspect one model package directory and manifest.",
                    "parameters": {
                        "type": "object",
                        "properties": {"model_id": {"type": "string"}, "repo_id": {"type": "string"}},
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
                {
                    "name": "select_model",
                    "description": "Persist the preferred auxiliary model/profile and optionally download it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model_id": {"type": "string"},
                            "repo_id": {"type": "string"},
                            "profile": {"type": "string"},
                            "ram_gb": {"type": "integer"},
                            "vram_gb": {"type": "integer"},
                            "download": {"type": "boolean"},
                            "dry_run": {"type": "boolean"},
                            "allow_heavy": {"type": "boolean"},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
                {
                    "name": "download_model",
                    "description": "Download a HuggingFace snapshot into the plugin-local model depot.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model_id": {"type": "string"},
                            "repo_id": {"type": "string"},
                            "revision": {"type": "string"},
                            "profile": {"type": "string"},
                            "ram_gb": {"type": "integer"},
                            "vram_gb": {"type": "integer"},
                            "allow_heavy": {"type": "boolean"},
                            "dry_run": {"type": "boolean"},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
                {
                    "name": "register_model_path",
                    "description": "Register an existing local model directory without copying it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model_id": {"type": "string"},
                            "repo_id": {"type": "string"},
                            "path": {"type": "string"},
                        },
                        "required": ["path"],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                },
            ],
        }

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(command_name or "").strip().lower()
        if command == "list_models":
            return self.list_models(payload)
        if command == "deployment_plan":
            return self.deployment_plan(payload)
        if command == "prepare_environment":
            return self.prepare_environment(payload)
        if command == "ensure_runtime":
            prepared = dict(payload or {})
            prepared.setdefault("install_packages", True)
            return self.prepare_environment(prepared)
        if command == "model_status":
            return self.model_status(payload)
        if command == "select_model":
            return self.select_model(payload)
        if command == "download_model":
            return self.download_model(payload)
        if command == "register_model_path":
            return self.register_model_path(payload)
        return {"success": False, "output": "", "error": f"Unknown command: {command_name}", "data": {}}

    def list_models(self, payload: dict[str, Any]) -> dict[str, Any]:
        only_8gb = _as_bool(payload.get("only_8gb"), False)
        models = [
            dict(item)
            for item in MODEL_CATALOG
            if not only_8gb or bool(item.get("recommended_for_8gb_vram"))
        ]
        return {
            "success": True,
            "output": f"{len(models)} auxiliary model package(s) available.",
            "data": {
                "models": models,
                "plugin_root": str(self.plugin_root),
                "model_root": str(self.model_root),
                "cache_root": str(self.cache_root),
            },
        }

    def deployment_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        ram_gb = _as_int(payload.get("ram_gb", 24), 24)
        vram_gb = _as_int(payload.get("vram_gb", 8), 8)
        requested_profile = str(payload.get("profile", "") or "").strip()
        ready = []
        blocked = []
        for item in MODEL_CATALOG:
            profiles = _memory_profiles(item)
            fitting_profiles = [
                dict(profile)
                for profile in profiles
                if int(profile.get("min_ram_gb", 0) or 0) <= ram_gb
                and int(profile.get("min_vram_gb", 0) or 0) <= vram_gb
            ]
            selected_profile = _resolve_memory_profile(
                item,
                requested_profile,
                ram_gb=ram_gb,
                vram_gb=vram_gb,
            )
            fits = bool(fitting_profiles)
            record = dict(item)
            record["fits_requested_hardware"] = fits
            record["selected_profile"] = selected_profile
            record["fitting_profiles"] = fitting_profiles
            record["profile_policy"] = (
                "ready"
                if fits and not bool(selected_profile.get("requires_allow_heavy"))
                else "requires_allow_heavy"
                if bool(item.get("requires_allow_heavy")) or bool(selected_profile.get("requires_allow_heavy"))
                else "outside_requested_hardware"
            )
            if fits and bool(item.get("recommended_for_8gb_vram")):
                ready.append(record)
            else:
                blocked.append(record)
        return {
            "success": True,
            "output": f"Recommended {len(ready)} model(s) for {ram_gb}GB RAM / {vram_gb}GB VRAM.",
            "data": {
                "hardware": {"ram_gb": ram_gb, "vram_gb": vram_gb},
                "recommended": ready,
                "guarded_or_blocked": blocked,
                "policy": (
                    "TRELLIS Text XLarge is selectable on the 8GB low_vram profile. "
                    "Models/profiles outside the requested hardware require allow_heavy=true. "
                    "All downloads and caches remain plugin-local."
                ),
            },
        }

    def prepare_environment(self, payload: dict[str, Any]) -> dict[str, Any]:
        force = _as_bool(payload.get("force"), False)
        install_packages = _as_bool(payload.get("install_packages"), True)
        self._ensure_inside_plugin(self.venv_root)
        if force and self.venv_root.exists():
            shutil.rmtree(self.venv_root)
        if not self._python_executable().exists():
            self.venv_root.parent.mkdir(parents=True, exist_ok=True)
            venv.EnvBuilder(with_pip=True, clear=False).create(str(self.venv_root))
        installed = False
        if install_packages:
            cmd = [str(self._python_executable()), "-m", "pip", "install", "--upgrade", "huggingface_hub>=0.24.0", "safetensors>=0.4.5"]
            result = subprocess.run(cmd, cwd=str(self.plugin_root), text=True, capture_output=True, timeout=1800, env=self._subprocess_env())
            if result.returncode != 0:
                return {
                    "success": False,
                    "output": result.stdout,
                    "error": result.stderr or "Failed to install model helper packages.",
                    "data": {"venv": str(self.venv_root), "python": str(self._python_executable())},
                }
            installed = True
        state = self._state()
        state["venv"] = {
            "path": str(self.venv_root),
            "python": str(self._python_executable()),
            "packages_installed": installed,
            "cache_root": str(self.cache_root),
        }
        self._write_state(state)
        return {
            "success": True,
            "output": "Game model plugin environment is ready.",
            "data": {
                "venv": str(self.venv_root),
                "python": str(self._python_executable()),
                "packages_installed": installed,
                "cache_root": str(self.cache_root),
            },
        }

    def model_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = self._resolve_model(payload.get("model_id", ""), payload.get("repo_id", ""))
        model_dir = self._model_dir(model)
        manifest_path = model_dir / "model_manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {"error": "manifest could not be parsed"}
        state = self._state()
        profile = _resolve_memory_profile(model, payload.get("profile", ""))
        return {
            "success": True,
            "output": f"{model['id']}: {'ready' if model_dir.exists() else 'missing'}",
            "data": {
                "model": model,
                "path": str(model_dir),
                "exists": model_dir.exists(),
                "manifest_path": str(manifest_path),
                "manifest": manifest,
                "state_record": (state.get("models") or {}).get(str(model["id"]), {}),
                "selected_model": state.get("selected_model", {}),
                "profile": profile,
            },
        }

    def select_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = self._resolve_model(payload.get("model_id", ""), payload.get("repo_id", ""))
        ram_gb = _as_int(payload.get("ram_gb", 24), 24)
        vram_gb = _as_int(payload.get("vram_gb", 8), 8)
        profile = _resolve_memory_profile(
            model,
            payload.get("profile", ""),
            ram_gb=ram_gb,
            vram_gb=vram_gb,
        )
        state = self._state()
        selected = {
            "model": model,
            "profile": profile,
            "hardware": {"ram_gb": ram_gb, "vram_gb": vram_gb},
            "selected_at": _utc_now(),
            "model_root": str(self.model_root),
            "cache_root": str(self.cache_root),
        }
        state["selected_model"] = selected
        state.setdefault("selections", {})[str(model["id"])] = selected
        self._write_state(state)

        if _as_bool(payload.get("download"), False):
            download_payload = dict(payload)
            download_payload["model_id"] = model["id"]
            download_payload["profile"] = profile.get("id", "")
            result = self.download_model(download_payload)
            result.setdefault("data", {})["selected_model"] = selected
            return result

        return {
            "success": True,
            "output": f"Selected {model['display_name']} with profile {profile.get('id', 'default')}.",
            "data": selected,
        }

    def download_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = self._resolve_model(payload.get("model_id", ""), payload.get("repo_id", ""))
        ram_gb = _as_int(payload.get("ram_gb", 24), 24)
        vram_gb = _as_int(payload.get("vram_gb", 8), 8)
        profile = _resolve_memory_profile(
            model,
            payload.get("profile", ""),
            ram_gb=ram_gb,
            vram_gb=vram_gb,
        )
        allow_heavy = _as_bool(payload.get("allow_heavy"), False)
        dry_run = _as_bool(payload.get("dry_run"), False)
        profile_min_ram = int(profile.get("min_ram_gb", model.get("min_ram_gb", 0)) or 0)
        profile_min_vram = int(profile.get("min_vram_gb", model.get("min_vram_gb", 0)) or 0)
        profile_exceeds_hardware = profile_min_ram > ram_gb or profile_min_vram > vram_gb
        requires_heavy = bool(model.get("requires_allow_heavy")) or bool(profile.get("requires_allow_heavy")) or profile_exceeds_hardware
        if requires_heavy and not allow_heavy:
            return {
                "success": False,
                "output": "",
                "error": (
                    f"{model['display_name']} profile {profile.get('id', 'default')} is guarded because it needs about "
                    f"{profile_min_vram}GB VRAM / {profile_min_ram}GB RAM for the requested profile. "
                    "Pass allow_heavy=true to download anyway."
                ),
                "data": {"model": model, "profile": profile, "plugin_root": str(self.plugin_root)},
            }
        target = self._model_dir(model)
        plan = {
            "model": model,
            "profile": profile,
            "hardware": {"ram_gb": ram_gb, "vram_gb": vram_gb},
            "target": str(target),
            "manifest_path": str(target / "model_manifest.json"),
            "plugin_root": str(self.plugin_root),
            "cache_root": str(self.cache_root),
            "dry_run": dry_run,
        }
        if dry_run:
            return {"success": True, "output": "Dry-run: model download plan prepared.", "data": plan}

        if not self._python_executable().exists():
            env_result = self.prepare_environment({"install_packages": True})
            if not env_result.get("success"):
                return env_result

        target.mkdir(parents=True, exist_ok=True)
        revision = str(payload.get("revision", "") or "").strip()
        code = (
            "from huggingface_hub import snapshot_download\n"
            "snapshot_download("
            f"repo_id={json.dumps(str(model['repo_id']))}, "
            f"local_dir={json.dumps(str(target))}, "
            "local_dir_use_symlinks=False"
            + (f", revision={json.dumps(revision)}" if revision else "")
            + ")\n"
        )
        result = subprocess.run(
            [str(self._python_executable()), "-c", code],
            cwd=str(self.plugin_root),
            text=True,
            capture_output=True,
            timeout=7200,
            env=self._subprocess_env(),
        )
        if result.returncode != 0:
            return {
                "success": False,
                "output": result.stdout,
                "error": result.stderr or "HuggingFace snapshot download failed.",
                "data": plan,
            }
        manifest = {
            "schema": "reverie.game_models.model_manifest.v1",
            "downloaded_at": _utc_now(),
            "model": model,
            "path": str(target),
            "source": "huggingface_snapshot",
            "revision": revision or "default",
            "profile": profile,
            "hardware_guard": {
                "recommended_for_8gb_vram": bool(model.get("recommended_for_8gb_vram")),
                "min_ram_gb": profile_min_ram,
                "min_vram_gb": profile_min_vram,
                "requested_ram_gb": ram_gb,
                "requested_vram_gb": vram_gb,
            },
        }
        (target / "model_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        state = self._state()
        state.setdefault("models", {})[str(model["id"])] = manifest
        self._write_state(state)
        return {"success": True, "output": f"Downloaded {model['display_name']} into the plugin-local model depot.", "data": manifest}

    def register_model_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        path_text = str(payload.get("path", "") or "").strip()
        if not path_text:
            return {"success": False, "output": "", "error": "path is required.", "data": {}}
        model = self._resolve_model(payload.get("model_id", ""), payload.get("repo_id", ""))
        path = Path(path_text).expanduser().resolve()
        if not path.exists():
            return {"success": False, "output": "", "error": f"Registered model path does not exist: {path}", "data": {"model": model}}
        manifest = {
            "schema": "reverie.game_models.model_manifest.v1",
            "registered_at": _utc_now(),
            "model": model,
            "path": str(path),
            "source": "external_registered_path",
            "copy_policy": "not_copied",
        }
        state = self._state()
        state.setdefault("models", {})[str(model["id"])] = manifest
        self._write_state(state)
        return {"success": True, "output": f"Registered {model['display_name']} at {path}.", "data": manifest}


def main(argv: list[str]) -> int:
    return GameModelsPlugin().run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
