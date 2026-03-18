"""Configuration and capability profiles for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml


ENGINE_BRAND = "Reverie Engine"
ENGINE_NAME = "reverie_engine"
ENGINE_COMPAT_NAME = "reverie_engine_lite"
ENGINE_ALIASES = (ENGINE_NAME, ENGINE_COMPAT_NAME)
SUPPORTED_DIMENSIONS = ("2D", "2.5D", "3D")


def _as_list(values: Iterable[str] | None) -> list[str]:
    return [str(item).strip() for item in (values or []) if str(item).strip()]


def normalize_dimension(value: str | None) -> str:
    raw = str(value or "2D").strip().upper().replace(" ", "")
    if raw in {"2.5D", "2_5D", "2-5D", "ISOMETRIC"}:
        return "2.5D"
    if raw == "3D":
        return "3D"
    return "2D"


def normalize_genre(value: str | None) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "vn": "galgame",
        "visual_novel": "galgame",
        "adv": "adventure",
        "towerdefense": "tower_defense",
        "td": "tower_defense",
        "platform": "platformer",
        "arpg": "action_rpg",
    }
    return aliases.get(raw, raw or "sandbox")


def canonical_engine_name(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return ENGINE_NAME if raw in {"", ENGINE_NAME, ENGINE_COMPAT_NAME} else raw


def is_builtin_engine_name(value: str | None) -> bool:
    return canonical_engine_name(value) == ENGINE_NAME


GENRE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "sandbox": {
        "label": "Sandbox",
        "modules": ["scene", "physics", "input", "animation", "audio", "ui", "telemetry", "save_data"],
        "supports_live2d": False,
    },
    "platformer": {
        "label": "Platformer",
        "modules": ["scene", "physics", "input", "animation", "audio", "ui", "quests", "telemetry", "save_data"],
        "supports_live2d": False,
    },
    "adventure": {
        "label": "Adventure",
        "modules": ["scene", "physics", "input", "dialogue", "quests", "ai", "audio", "ui", "telemetry", "save_data"],
        "supports_live2d": False,
    },
    "action_rpg": {
        "label": "Action RPG",
        "modules": ["scene", "physics", "input", "combat", "dialogue", "quests", "ai", "inventory", "audio", "ui", "telemetry", "save_data"],
        "supports_live2d": False,
    },
    "galgame": {
        "label": "Galgame",
        "modules": ["scene", "dialogue", "timeline", "ui", "audio", "localization", "telemetry", "save_data", "live2d"],
        "supports_live2d": True,
    },
    "tower_defense": {
        "label": "Tower Defense",
        "modules": ["scene", "physics", "ai", "tower_defense", "ui", "economy", "audio", "telemetry", "save_data"],
        "supports_live2d": False,
    },
    "arena": {
        "label": "Arena Combat",
        "modules": ["scene", "physics", "input", "combat", "ai", "audio", "ui", "telemetry", "save_data"],
        "supports_live2d": False,
    },
}


SAMPLE_TO_GENRE = {
    "2d_platformer": "platformer",
    "iso_adventure": "adventure",
    "2_5d_exploration": "adventure",
    "3d_arena": "arena",
    "3d_third_person": "arena",
    "topdown_action": "action_rpg",
    "galgame_live2d": "galgame",
    "galgame": "galgame",
    "tower_defense": "tower_defense",
}


@dataclass
class RuntimeSettings:
    entry_scene: str = "data/scenes/main.relscene.json"
    fixed_step: float = 1.0 / 60.0
    target_fps: int = 60
    window_title: str = ENGINE_BRAND
    headless_default: bool = True
    deterministic_smoke_frames: int = 180
    sample_name: str = ""
    genre: str = "sandbox"

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RuntimeSettings":
        data = dict(payload or {})
        return cls(
            entry_scene=str(data.get("entry_scene") or cls.entry_scene),
            fixed_step=float(data.get("fixed_step", cls.fixed_step)),
            target_fps=int(data.get("target_fps", cls.target_fps)),
            window_title=str(data.get("window_title") or cls.window_title),
            headless_default=bool(data.get("headless_default", cls.headless_default)),
            deterministic_smoke_frames=int(data.get("deterministic_smoke_frames", cls.deterministic_smoke_frames)),
            sample_name=str(data.get("sample_name") or ""),
            genre=normalize_genre(data.get("genre")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_scene": self.entry_scene,
            "fixed_step": self.fixed_step,
            "target_fps": self.target_fps,
            "window_title": self.window_title,
            "headless_default": self.headless_default,
            "deterministic_smoke_frames": self.deterministic_smoke_frames,
            "sample_name": self.sample_name,
            "genre": self.genre,
        }


@dataclass
class Live2DSettings:
    enabled: bool = False
    renderer: str = "web"
    sdk_candidates: list[str] = field(default_factory=lambda: [
        "vendor/live2d/live2dcubismcore.min.js",
        "web/vendor/live2d/live2dcubismcore.min.js",
        "live2dcubismcore.min.js",
    ])
    manifest_path: str = "data/live2d/models.yaml"
    models_dir: str = "assets/live2d"

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Live2DSettings":
        data = dict(payload or {})
        return cls(
            enabled=bool(data.get("enabled", cls.enabled)),
            renderer=str(data.get("renderer") or cls.renderer),
            sdk_candidates=_as_list(data.get("sdk_candidates")) or list(cls().sdk_candidates),
            manifest_path=str(data.get("manifest_path") or cls.manifest_path),
            models_dir=str(data.get("models_dir") or cls.models_dir),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "renderer": self.renderer,
            "sdk_candidates": list(self.sdk_candidates),
            "manifest_path": self.manifest_path,
            "models_dir": self.models_dir,
        }


@dataclass
class EngineConfig:
    project_name: str
    dimension: str
    genre: str = "sandbox"
    engine_name: str = ENGINE_NAME
    modules: list[str] = field(default_factory=list)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    live2d: Live2DSettings = field(default_factory=Live2DSettings)
    capabilities: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EngineConfig":
        data = dict(payload or {})
        project = dict(data.get("project") or {})
        runtime = RuntimeSettings.from_dict(data.get("runtime") or {})
        live2d = Live2DSettings.from_dict(data.get("live2d") or {})
        capabilities = dict(data.get("capabilities") or {})
        modules = _as_list(data.get("modules") or capabilities.get("modules"))
        genre = normalize_genre(project.get("genre") or runtime.genre)
        return cls(
            project_name=str(project.get("name") or "Reverie Game"),
            dimension=normalize_dimension(project.get("dimension")),
            genre=genre,
            engine_name=canonical_engine_name(project.get("engine") or ENGINE_NAME),
            modules=modules or default_modules_for_genre(genre),
            runtime=runtime,
            live2d=live2d,
            capabilities=capabilities or build_capabilities(genre, normalize_dimension(project.get("dimension")), live2d.enabled),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project": {
                "name": self.project_name,
                "engine": self.engine_name,
                "dimension": self.dimension,
                "genre": self.genre,
                "brand": ENGINE_BRAND,
            },
            "runtime": self.runtime.to_dict(),
            "modules": list(self.modules),
            "capabilities": dict(self.capabilities),
            "live2d": self.live2d.to_dict(),
        }


def default_modules_for_genre(genre: str) -> list[str]:
    profile = GENRE_LIBRARY.get(normalize_genre(genre), GENRE_LIBRARY["sandbox"])
    return list(profile["modules"])


def build_capabilities(genre: str, dimension: str, live2d_enabled: bool) -> Dict[str, Any]:
    dimension = normalize_dimension(dimension)
    genre_key = normalize_genre(genre)
    profile = GENRE_LIBRARY.get(genre_key, GENRE_LIBRARY["sandbox"])
    supports_3d = dimension == "3D"
    supports_iso = dimension == "2.5D"
    return {
        "modules": list(profile["modules"]),
        "supports_2d": True,
        "supports_2_5d": supports_iso or supports_3d,
        "supports_3d": supports_3d,
        "supports_dialogue": "dialogue" in profile["modules"],
        "supports_quests": "quests" in profile["modules"],
        "supports_tower_defense": "tower_defense" in profile["modules"],
        "supports_live2d": bool(live2d_enabled or profile.get("supports_live2d")),
        "supports_save_data": "save_data" in profile["modules"],
        "supports_ai_agents": "ai" in profile["modules"],
        "supports_ui": "ui" in profile["modules"],
    }


def discover_live2d_sdk(project_root: str | Path, sdk_candidates: Optional[Iterable[str]] = None) -> Optional[Path]:
    root = Path(project_root).resolve()
    candidates = _as_list(sdk_candidates) or list(Live2DSettings().sdk_candidates)
    for raw in candidates:
        path = Path(raw)
        if not path.is_absolute():
            path = (root / path).resolve()
        if path.exists():
            return path

    bundled = Path(__file__).resolve().parent / "vendor/live2d/live2dcubismcore.min.js"
    if bundled.exists():
        return bundled.resolve()

    for parent in [root, *root.parents[:3]]:
        candidate = parent / "live2dcubismcore.min.js"
        if candidate.exists():
            return candidate.resolve()
    return None


def build_engine_config(
    project_name: str,
    dimension: str,
    *,
    sample_name: str | None = None,
    genre: str | None = None,
) -> Dict[str, Any]:
    dimension_key = normalize_dimension(dimension)
    genre_key = normalize_genre(genre or SAMPLE_TO_GENRE.get(str(sample_name or "").strip(), "sandbox"))
    modules = default_modules_for_genre(genre_key)
    live2d_enabled = "live2d" in modules
    runtime = RuntimeSettings(
        window_title=project_name,
        sample_name=str(sample_name or ""),
        genre=genre_key,
    )
    live2d = Live2DSettings(enabled=live2d_enabled)
    config = EngineConfig(
        project_name=project_name,
        dimension=dimension_key,
        genre=genre_key,
        modules=modules,
        runtime=runtime,
        live2d=live2d,
        capabilities=build_capabilities(genre_key, dimension_key, live2d_enabled),
    )
    return config.to_dict()


def load_engine_config(project_root: str | Path) -> EngineConfig:
    root = Path(project_root)
    config_path = root / "data/config/engine.yaml"
    if not config_path.exists():
        return EngineConfig.from_dict(build_engine_config(root.name, "2D"))
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return EngineConfig.from_dict(payload)
