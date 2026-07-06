"""Runtime media-generation capability discovery."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agnes import normalize_agnes_config, resolve_agnes_api_key
from .agnes_tti_profiles.registry import get_agnes_tti_model_catalog
from .agnes_ttv_profiles.registry import get_agnes_ttv_model_catalog, resolve_agnes_ttv_model
from .aihubmix import normalize_aihubmix_config, resolve_aihubmix_api_key
from .aihubmix_tti_profiles.registry import get_aihubmix_tti_model_catalog
from .config import (
    default_text_to_image_config,
    default_text_to_video_config,
    normalize_tti_models,
    normalize_tti_source,
    normalize_ttv_source,
    resolve_tti_default_display_name,
    sanitize_tti_path,
)
from .pollinations_tti_profiles.registry import get_pollinations_tti_model_catalog
from .sensenova import normalize_sensenova_config, resolve_sensenova_api_key
from .sensenova_tti_profiles.registry import get_sensenova_tti_model_catalog


def _load_config(config_manager: Any = None, config: Any = None) -> Any:
    if config is not None:
        return config
    if config_manager is not None:
        try:
            return config_manager.load()
        except Exception:
            return None
    return None


def _merge_tti_config(config_obj: Any = None) -> Dict[str, Any]:
    cfg = default_text_to_image_config()
    loaded = getattr(config_obj, "text_to_image", None)
    if isinstance(loaded, dict):
        cfg.update(loaded)
        for source in ("aihubmix", "pollinations", "agnes", "sensenova"):
            defaults = default_text_to_image_config().get(source, {})
            nested = dict(defaults)
            if isinstance(loaded.get(source), dict):
                nested.update(loaded.get(source, {}))
            cfg[source] = nested
    cfg["models"] = normalize_tti_models(cfg.get("models", []), legacy_model_paths=cfg.get("model_paths", []))
    cfg["active_source"] = normalize_tti_source(cfg.get("active_source", "local"))
    cfg["default_model_display_name"] = resolve_tti_default_display_name(cfg)
    return cfg


def _merge_ttv_config(config_obj: Any = None) -> Dict[str, Any]:
    cfg = default_text_to_video_config()
    loaded = getattr(config_obj, "text_to_video", None)
    if isinstance(loaded, dict):
        cfg.update(loaded)
        for source in ("agnes",):
            defaults = default_text_to_video_config().get(source, {})
            nested = dict(defaults)
            if isinstance(loaded.get(source), dict):
                nested.update(loaded.get(source, {}))
            cfg[source] = nested
    cfg["active_source"] = normalize_ttv_source(cfg.get("active_source", "agnes"))
    return cfg


def _resolve_config_path(raw_path: Any, project_root: Path) -> Path:
    normalized = sanitize_tti_path(raw_path)
    if not normalized:
        return project_root
    expanded = Path(os.path.expandvars(normalized)).expanduser()
    if expanded.is_absolute() or _looks_like_absolute_path(normalized):
        return expanded
    return (project_root / expanded).resolve()


def _looks_like_absolute_path(path_text: str) -> bool:
    if not path_text:
        return False
    if path_text.startswith(("\\\\", "//", "\\", "/")):
        return True
    return len(path_text) >= 3 and path_text[1:3] in (":\\", ":/")


def _local_model_status(tti_cfg: Dict[str, Any], project_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in tti_cfg.get("models", []):
        resolved = _resolve_config_path(item.get("path", ""), project_root)
        rows.append(
            {
                "display_name": item.get("display_name", ""),
                "configured_path": item.get("path", ""),
                "resolved_path": str(resolved),
                "exists": resolved.exists(),
                "output_modalities": ["image"],
                "parameters": {
                    "width": item.get("recommended_width", tti_cfg.get("default_width", 512)),
                    "height": item.get("recommended_height", tti_cfg.get("default_height", 512)),
                    "steps": item.get("recommended_steps", tti_cfg.get("default_steps", 20)),
                    "cfg": item.get("recommended_cfg", tti_cfg.get("default_cfg", 8.0)),
                },
            }
        )
    return rows


def _remote_tti_source(
    *,
    source: str,
    cfg: Dict[str, Any],
    models: List[Dict[str, Any]],
    api_key_available: bool,
) -> Dict[str, Any]:
    default_model = str(cfg.get("default_model", "") or "").strip()
    return {
        "source": source,
        "enabled": bool(cfg.get("enabled", True)),
        "default_model": default_model,
        "configured_count": len(models),
        "api_key_available": api_key_available,
        "models": models,
    }


def build_media_capabilities(
    *,
    config_manager: Any = None,
    config: Any = None,
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return current media runtime capabilities without network calls."""
    config_obj = _load_config(config_manager=config_manager, config=config)
    root = Path(project_root or Path.cwd()).resolve()
    tti_cfg = _merge_tti_config(config_obj)
    ttv_cfg = _merge_ttv_config(config_obj)

    agnes_cfg = normalize_agnes_config(getattr(config_obj, "agnes", {}) if config_obj is not None else {})
    aihubmix_cfg = normalize_aihubmix_config(getattr(config_obj, "aihubmix", {}) if config_obj is not None else {})
    sensenova_cfg = normalize_sensenova_config(getattr(config_obj, "sensenova", {}) if config_obj is not None else {})
    agnes_key_available = bool(resolve_agnes_api_key(agnes_cfg))
    aihubmix_key_available = bool(resolve_aihubmix_api_key(aihubmix_cfg))
    sensenova_key_available = bool(resolve_sensenova_api_key(sensenova_cfg))

    local_models = _local_model_status(tti_cfg, root)
    image_sources = {
        "local": {
            "source": "local",
            "enabled": bool(tti_cfg.get("enabled", True)),
            "default_model": str(tti_cfg.get("default_model_display_name", "") or "").strip(),
            "configured_count": len(local_models),
            "local_models_exist": sum(1 for item in local_models if item.get("exists")),
            "models": local_models,
        },
        "aihubmix": _remote_tti_source(
            source="aihubmix",
            cfg=tti_cfg.get("aihubmix", {}),
            models=get_aihubmix_tti_model_catalog(),
            api_key_available=aihubmix_key_available,
        ),
        "pollinations": _remote_tti_source(
            source="pollinations",
            cfg=tti_cfg.get("pollinations", {}),
            models=get_pollinations_tti_model_catalog(),
            api_key_available=bool(str(tti_cfg.get("pollinations", {}).get("api_key", "")).strip() or os.getenv("POLLINATIONS_API_KEY") or os.getenv("POLLINATIONS_TOKEN")),
        ),
        "agnes": _remote_tti_source(
            source="agnes",
            cfg=tti_cfg.get("agnes", {}),
            models=get_agnes_tti_model_catalog(),
            api_key_available=agnes_key_available,
        ),
        "sensenova": _remote_tti_source(
            source="sensenova",
            cfg=tti_cfg.get("sensenova", {}),
            models=get_sensenova_tti_model_catalog(),
            api_key_available=sensenova_key_available,
        ),
    }

    ttv_source = normalize_ttv_source(ttv_cfg.get("active_source", "agnes"))
    ttv_agnes_cfg = ttv_cfg.get("agnes", {}) if isinstance(ttv_cfg.get("agnes"), dict) else {}
    ttv_models = get_agnes_ttv_model_catalog()
    ttv_default = str(ttv_agnes_cfg.get("default_model", "") or "").strip()
    default_ttv_model = resolve_agnes_ttv_model(ttv_default)
    video_sources = {
        "agnes": {
            "source": "agnes",
            "enabled": bool(ttv_cfg.get("enabled", True)) and bool(ttv_agnes_cfg.get("enabled", True)),
            "default_model": ttv_default,
            "configured_count": len(ttv_models),
            "api_key_available": agnes_key_available,
            "models": ttv_models,
            "default_profile": default_ttv_model or {},
        }
    }

    return {
        "image": {
            "enabled": bool(tti_cfg.get("enabled", True)) and bool(image_sources.get(tti_cfg["active_source"], {}).get("enabled", True)),
            "active_source": tti_cfg["active_source"],
            "default_model": image_sources.get(tti_cfg["active_source"], {}).get("default_model", ""),
            "configured_count": image_sources.get(tti_cfg["active_source"], {}).get("configured_count", 0),
            "tool": "text_to_image",
            "sources": image_sources,
        },
        "video": {
            "enabled": bool(ttv_cfg.get("enabled", True)) and bool(video_sources.get(ttv_source, {}).get("enabled", True)),
            "active_source": ttv_source,
            "default_model": video_sources.get(ttv_source, {}).get("default_model", ""),
            "configured_count": video_sources.get(ttv_source, {}).get("configured_count", 0),
            "tool": "text_to_video",
            "sources": video_sources,
        },
    }


def render_runtime_media_capabilities_digest(capabilities: Optional[Dict[str, Any]] = None) -> str:
    """Render the short system-prompt digest for current media capabilities."""
    caps = capabilities or build_media_capabilities()
    image = caps.get("image", {})
    video = caps.get("video", {})

    def line(label: str, item: Dict[str, Any]) -> str:
        enabled = "enabled" if item.get("enabled") else "disabled"
        default_model = str(item.get("default_model", "") or "(none)").strip()
        return (
            f"- {label}: {enabled}; source={item.get('active_source', '')}; "
            f"default={default_model}; configured={item.get('configured_count', 0)}; "
            f"tool=`{item.get('tool', '')}`"
        )

    return "\n".join(
        [
            "## Runtime Media Capabilities",
            line("image", image),
            line("video", video),
            "- Details: call `media_generation_capabilities` before selecting non-default models or provider-specific parameters.",
        ]
    )

