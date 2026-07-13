"""
Configuration Management

Handles loading and saving configuration including:
- API settings (base_url, api_key, model)
- Model presets
- User preferences
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import sys
import hashlib
import re
import logging

from .diagnostics import report_suppressed_exception
from .security_utils import write_json_secure
from .security_policy import normalize_permission_level
from .storage import (
    ProjectStorageResolver,
    sanitize_project_name,
)
from .codex import (
    build_codex_runtime_model_data,
    default_codex_config,
    normalize_codex_config,
)
from .aihubmix import (
    build_aihubmix_runtime_model_data,
    default_aihubmix_config,
    normalize_aihubmix_config,
)
from .opencode import (
    build_opencode_runtime_model_data,
    default_opencode_config,
    normalize_opencode_config,
)
from .agnes import (
    build_agnes_runtime_model_data,
    default_agnes_config,
    normalize_agnes_config,
)
from .atlas import (
    default_atlas_mode_config,
    normalize_atlas_mode_config,
)
from .nvidia import (
    build_nvidia_computer_controller_runtime_model_data,
    build_nvidia_runtime_model_data,
    default_nvidia_config,
    is_nvidia_api_url,
    normalize_nvidia_config,
    resolve_nvidia_api_key,
)
from .sensenova import (
    build_sensenova_runtime_model_data,
    default_sensenova_config,
    normalize_sensenova_config,
)
from .unlimitedsurf import (
    build_unlimitedsurf_runtime_model_data,
    default_unlimitedsurf_config,
    normalize_unlimitedsurf_config,
)
from .modelscope import (
    build_modelscope_runtime_model_data,
    default_modelscope_config,
    normalize_modelscope_config,
)
from .webgemini import (
    build_webgemini_runtime_model_data,
    default_webgemini_config,
    normalize_webgemini_config,
)
from .modes import normalize_mode
from .version import CONFIG_VERSION, __version__

EXTERNAL_MODEL_SOURCES = ("codex", "aihubmix", "agnes", "sensenova", "unlimitedsurf", "nvidia", "modelscope", "webgemini", "opencode")
SUPPORTED_ACTIVE_MODEL_SOURCES = ("standard",) + EXTERNAL_MODEL_SOURCES
MODEL_SOURCE_DISPLAY_NAMES = {
    "standard": "Custom Provider",
    "codex": "Codex",
    "aihubmix": "AIhubMix",
    "agnes": "Agnes",
    "sensenova": "SenseNova",
    "unlimitedsurf": "unlimited.surf",
    "nvidia": "NVIDIA",
    "modelscope": "ModelScope",
    "webgemini": "WebGemini",
    "opencode": "Opencode",
}
SUPPORTED_TOOL_OUTPUT_STYLES = ("minimal", "compact", "condensed", "full")
SUPPORTED_THINKING_OUTPUT_STYLES = ("hidden", "compact", "full")
SUPPORTED_TTI_SOURCES = ("local", "aihubmix", "pollinations", "agnes", "sensenova")
SUPPORTED_TTV_SOURCES = ("agnes",)
SUPPORTED_MODEL_PROVIDERS = (
    "request",
    "anthropic",
    "openai-chat",
    "openai-responses",
    "curl",
    "codex",
    "webgemini",
)


def normalize_model_provider(value: Any, default: str = "openai-chat") -> str:
    """Normalize persisted model transport names to one stable spelling."""
    candidate = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "openai": "openai-chat",
        "openai-old": "openai-chat",
        "openai-sdk": "openai-chat",
        "openai-chat.completions": "openai-chat",
        "openai-chat-completions": "openai-chat",
        "chat.completions": "openai-chat",
        "chat-completions": "openai-chat",
        "openai-res": "openai-responses",
        "openai-response": "openai-responses",
        "responses": "openai-responses",
    }
    candidate = aliases.get(candidate, candidate)
    if candidate in SUPPORTED_MODEL_PROVIDERS:
        return candidate
    return default


def is_config_version_older(value: Any, target: str = CONFIG_VERSION) -> bool:
    """Return whether a dotted config version predates the target version."""
    def parts(raw: Any) -> tuple[int, ...]:
        numbers = [int(piece) for piece in re.findall(r"\d+", str(raw or ""))[:3]]
        return tuple((numbers + [0, 0, 0])[:3])

    return parts(value) < parts(target)


def normalize_active_model_source(value: Any, default: str = "standard") -> str:
    """Normalize the persisted chat model source selector."""
    candidate = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "us": "unlimitedsurf",
        "unlimited.surf": "unlimitedsurf",
        "unlimited_surf": "unlimitedsurf",
        "unlimitedsurf": "unlimitedsurf",
        "oc": "opencode",
    }
    candidate = aliases.get(candidate, candidate)
    if candidate in SUPPORTED_ACTIVE_MODEL_SOURCES:
        return candidate
    return default


def model_source_display_name(value: Any) -> str:
    """Return the canonical user-facing name for a model source."""
    source = normalize_active_model_source(value)
    return MODEL_SOURCE_DISPLAY_NAMES[source]


def normalize_tool_output_style(value: Any, default: str = "compact") -> str:
    """Normalize persisted tool-result display preference."""
    candidate = str(value or "").strip().lower()
    if candidate in SUPPORTED_TOOL_OUTPUT_STYLES:
        return candidate
    return default


def normalize_thinking_output_style(value: Any, default: str = "full") -> str:
    """Normalize persisted reasoning/think-trace display preference."""
    candidate = str(value or "").strip().lower()
    if candidate in SUPPORTED_THINKING_OUTPUT_STYLES:
        return candidate
    return default


def _escape_invalid_json_string_control_chars(raw: str) -> tuple[str, bool]:
    """Escape literal control characters that appear inside JSON strings."""
    if not raw:
        return "", False

    replacements = {
        "\b": r"\b",
        "\f": r"\f",
        "\n": r"\n",
        "\r": r"\r",
        "\t": r"\t",
    }

    pieces: List[str] = []
    in_string = False
    escaped = False
    changed = False

    for ch in raw:
        if in_string:
            if escaped:
                pieces.append(ch)
                escaped = False
                continue

            if ch == "\\":
                pieces.append(ch)
                escaped = True
                continue

            if ch == '"':
                pieces.append(ch)
                in_string = False
                continue

            if ord(ch) < 0x20:
                pieces.append(replacements.get(ch, f"\\u{ord(ch):04x}"))
                changed = True
                continue

            pieces.append(ch)
            continue

        pieces.append(ch)
        if ch == '"':
            in_string = True

    return "".join(pieces), changed


def _resolve_runner_root() -> Path:
    """Return the physical launcher root: exe dir, script dir, or source root."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent

    if sys.argv and sys.argv[0]:
        try:
            exec_path = Path(os.path.abspath(sys.argv[0])).resolve()
            if exec_path.name == '__main__.py':
                return exec_path.parent.parent
            if exec_path.exists() and exec_path.is_file():
                return exec_path.parent
        except Exception:
            report_suppressed_exception("resolve launcher path from argv")

    try:
        source_root = Path(__file__).resolve().parent.parent
        if (source_root / 'reverie').exists():
            return source_root
    except Exception:
        report_suppressed_exception("resolve launcher source root")

    return Path.cwd()


def get_launcher_root() -> Path:
    """Return the directory that physically launched Reverie."""
    return _resolve_runner_root()


def default_text_to_image_config() -> Dict[str, Any]:
    """Default configuration for text-to-image generation."""
    return {
        "enabled": True,
        "python_executable": "",
        "script_path": "comfy/generate_image.py",
        "output_dir": ".",
        "active_source": "local",
        "models": [],
        "default_model_display_name": "",
        "default_width": 512,
        "default_height": 512,
        "default_steps": 20,
        "default_cfg": 8.0,
        "default_sampler": "euler",
        "default_scheduler": "normal",
        "default_negative_prompt": "",
        "force_cpu": False,
        "auto_install_missing_deps": False,
        "auto_install_max_missing_deps": 6,
        "aihubmix": {
            "enabled": True,
            "api_key": "",
            "base_url": "https://aihubmix.com/v1",
            "default_model": "gpt-image-2-free",
            "timeout": 300,
            "default_size": "auto",
            "default_quality": "auto",
            "default_aspect_ratio": "1:1",
        },
        "pollinations": {
            "enabled": True,
            "api_key": "",
            "base_url": "https://gen.pollinations.ai/v1",
            "default_model": "flux",
            "timeout": 300,
            "default_size": "1024x1024",
            "default_quality": "medium",
            "response_format": "b64_json",
            "safe": "",
        },
        "agnes": {
            "enabled": True,
            "base_url": "https://apihub.agnes-ai.com/v1",
            "default_model": "agnes-image-2.1-flash",
            "timeout": 300,
            "default_size": "1024x1024",
            "default_quality": "auto",
            "response_format": "b64_json",
        },
        "sensenova": {
            "enabled": True,
            "base_url": "https://token.sensenova.cn/v1",
            "default_model": "sensenova-u1-fast",
            "timeout": 300,
            "default_size": "2752x1536",
        },
    }


def default_text_to_video_config() -> Dict[str, Any]:
    """Default configuration for text-to-video generation."""
    return {
        "enabled": True,
        "output_dir": ".",
        "active_source": "agnes",
        "agnes": {
            "enabled": True,
            "base_url": "https://apihub.agnes-ai.com/v1",
            "default_model": "agnes-video-v2.0",
            "timeout": 300,
            "default_width": 1152,
            "default_height": 768,
            "default_num_frames": 121,
            "default_frame_rate": 24,
            "default_poll_interval": 5,
            "default_max_poll_seconds": 600,
        },
    }

def default_writer_mode_config() -> Dict[str, Any]:
    """Default configuration for writer mode."""
    return {
        "memory_system_enabled": True,
        "auto_consistency_check": True,
        "auto_character_tracking": True,
        "max_chapter_context_window": 5,
        "narrative_analysis_enabled": True,
        "emotion_tracking_enabled": True,
        "plot_tracking_enabled": True,
    }


def default_gamer_mode_config() -> Dict[str, Any]:
    """Default configuration for gamer mode."""
    return {
        "target_engine": "reverie_engine",
        "supported_dimensions": ["2D", "2.5D", "3D"],
        "supported_engines": ["reverie_engine", "custom", "web", "pygame", "love2d", "cocos2d", "godot", "o3de"],
        "supported_frameworks": [
            "reverie_engine", "phaser", "pixijs", "threejs", "pygame", "love2d", "cocos2d", "godot", "o3de"
        ],
        "asset_tracking_enabled": True,
        "asset_packaging_enabled": True,
        "game_balance_analysis": True,
        "math_simulation_enabled": True,
        "statistics_tools_enabled": True,
        "gdd_required": True,
        "story_design_enabled": True,
        "rpg_focus_enabled": True,
        "level_design_assistant": True,
        "config_editing_enabled": True,
        "modeling_pipeline_enabled": True,
        "modeling_tools_enabled": True,
        "blender_modeling_enabled": True,
        "blender_path": "",
        "blender_default_export_format": "glb",
        "blender_timeout_seconds": 240,
        "ashfox_server_name": "ashfox",
        "ashfox_endpoint": "http://127.0.0.1:8787/mcp",
        "proactive_mode_switching": True,
        "mandatory_verification_loop": True,
        "playtest_iteration_enabled": True,
        "max_asset_context_window": 10,
        "context_compression_enabled": True,
    }


_SUBAGENT_COLOR_PALETTE = (
    "#ff8a80",
    "#82b1ff",
    "#b9f6ca",
    "#ffd180",
    "#ea80fc",
    "#80deea",
    "#ffff8d",
    "#cf93d9",
)


def default_subagent_config() -> Dict[str, Any]:
    """Default configuration for base Reverie subagents."""
    return {
        "schema_version": 2,
        "enabled": True,
        "agents": [],
    }


def _subagent_color_for_id(subagent_id: str) -> str:
    """Return a stable display color for a subagent ID."""
    normalized_id = str(subagent_id or "").strip() or "subagent"
    digest = hashlib.sha1(normalized_id.encode("utf-8")).hexdigest()
    return _SUBAGENT_COLOR_PALETTE[int(digest[:8], 16) % len(_SUBAGENT_COLOR_PALETTE)]


def normalize_subagent_config(raw_config: Any) -> Dict[str, Any]:
    """Normalize persisted subagent config into the canonical shape."""
    defaults = default_subagent_config()
    if not isinstance(raw_config, dict):
        return defaults

    normalized = dict(defaults)
    normalized["enabled"] = bool(raw_config.get("enabled", defaults["enabled"]))

    raw_agents = raw_config.get("agents", [])
    if isinstance(raw_agents, dict):
        raw_agents = [
            {"id": agent_id, **(agent_data if isinstance(agent_data, dict) else {})}
            for agent_id, agent_data in raw_agents.items()
        ]
    if not isinstance(raw_agents, list):
        raw_agents = []

    seen_ids: set[str] = set()
    agents: List[Dict[str, Any]] = []
    for index, raw_agent in enumerate(raw_agents, start=1):
        if not isinstance(raw_agent, dict):
            continue

        subagent_id = str(raw_agent.get("id") or raw_agent.get("name") or f"subagent-{index:03d}").strip()
        if not subagent_id:
            subagent_id = f"subagent-{index:03d}"
        base_id = subagent_id
        suffix = 2
        while subagent_id in seen_ids:
            subagent_id = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(subagent_id)

        raw_model_ref = raw_agent.get("model_ref", {})
        model_ref = raw_model_ref if isinstance(raw_model_ref, dict) else {}
        source = normalize_active_model_source(model_ref.get("source", "standard"))
        try:
            model_index = int(model_ref.get("index", 0))
        except (TypeError, ValueError):
            model_index = 0

        subagent_mode = normalize_mode(raw_agent.get("mode", "reverie"))
        if subagent_mode == "computer-controller":
            subagent_mode = "reverie"

        agents.append(
            {
                "id": subagent_id,
                "name": str(raw_agent.get("name") or subagent_id).strip() or subagent_id,
                "enabled": bool(raw_agent.get("enabled", True)),
                "color": str(raw_agent.get("color") or _subagent_color_for_id(subagent_id)).strip(),
                "created_at": str(raw_agent.get("created_at") or "").strip(),
                "updated_at": str(raw_agent.get("updated_at") or "").strip(),
                "mode": subagent_mode,
                "model_ref": {
                    "source": source,
                    "index": max(0, model_index),
                    "model": str(model_ref.get("model") or "").strip(),
                    "display_name": str(model_ref.get("display_name") or "").strip(),
                },
            }
        )

    normalized["agents"] = agents
    return normalized


def _merge_dict_defaults(raw: Any, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a partially-populated config section onto its canonical defaults."""
    merged = dict(defaults)
    if isinstance(raw, dict):
        merged.update(raw)
    return merged


def normalize_writer_mode_config(raw: Any) -> Dict[str, Any]:
    """Normalize writer-mode config into the canonical shape."""
    return _merge_dict_defaults(raw, default_writer_mode_config())


def normalize_gamer_mode_config(raw: Any) -> Dict[str, Any]:
    """Normalize gamer-mode config into the canonical shape."""
    return _merge_dict_defaults(raw, default_gamer_mode_config())


def sanitize_tti_path(path_value: Any) -> str:
    """Normalize user-provided TTI path text (quotes/whitespace/escaped quotes)."""
    raw = str(path_value or "").strip()
    if not raw:
        return ""

    # Common case from copied JSON/Python literals: \"C:\path\model.safetensors\"
    raw = raw.replace('\\"', '"').replace("\\'", "'")
    # Also handle over-escaped wrappers like \\\"C:\path\\\"
    raw = re.sub(r'^(\\+)(["\'])', r"\2", raw)
    raw = re.sub(r'(\\+)(["\'])$', r"\2", raw)

    # Remove wrapping quotes, including accidentally doubled wrappers.
    for _ in range(3):
        stripped = raw.strip()
        if len(stripped) >= 2 and (
            (stripped[0] == '"' and stripped[-1] == '"')
            or (stripped[0] == "'" and stripped[-1] == "'")
        ):
            raw = stripped[1:-1]
            continue

        if stripped.startswith('"') or stripped.startswith("'"):
            stripped = stripped[1:]
        if stripped.endswith('"') or stripped.endswith("'"):
            stripped = stripped[:-1]
        raw = stripped
        break

    return raw.strip()


def _tti_display_name_from_path(path: str, fallback_index: int) -> str:
    """Build a readable display name from a model path."""
    raw = sanitize_tti_path(path)
    if not raw:
        return f"tti-model-{fallback_index + 1}"

    parsed = Path(raw)
    stem = parsed.stem.strip()
    if stem:
        return stem

    name = parsed.name.strip()
    if name:
        return name

    return f"tti-model-{fallback_index + 1}"


def normalize_tti_models(raw_models: Any, legacy_model_paths: Any = None) -> List[Dict[str, Any]]:
    """
    Normalize TTI model configuration into:
    [{"path": "...", "display_name": "...", "introduction": "...", ...}]
    """
    merged_entries: List[Any] = []

    if isinstance(raw_models, list):
        merged_entries.extend(raw_models)

    if isinstance(legacy_model_paths, list):
        merged_entries.extend(legacy_model_paths)

    models: List[Dict[str, str]] = []
    used_display_names = set()
    seen_path_keys = set()

    for idx, entry in enumerate(merged_entries):
        path_value = ""
        display_name = ""
        introduction = ""

        extra_fields: Dict[str, Any] = {}

        if isinstance(entry, str):
            path_value = sanitize_tti_path(entry)
        elif isinstance(entry, dict):
            raw_path = (
                entry.get("path")
                or entry.get("model_path")
                or entry.get("model")
            )
            if raw_path is not None:
                path_value = sanitize_tti_path(raw_path)

            raw_display = (
                entry.get("display_name")
                or entry.get("DisplayName")
                or entry.get("name")
            )
            if raw_display is not None:
                display_name = str(raw_display).strip()

            raw_intro = entry.get("introduction")
            if raw_intro is None:
                raw_intro = entry.get("intro", "")
            if raw_intro is not None:
                introduction = str(raw_intro)

            path_like_keys = {
                "clip_model",
                "vae_model",
                "prompt_enhancer_model",
                "text_encoder",
                "vae",
                "workflow_path",
                "model_file",
                "main_model",
                "diffusion_model",
            }
            for key in (
                "format",
                "model_format",
                "architecture",
                "family",
                "model_file",
                "main_model",
                "diffusion_model",
                "clip_model",
                "vae_model",
                "prompt_enhancer_model",
                "text_encoder",
                "vae",
                "clip_type",
                "workflow_path",
                "source_url",
                "license",
                "recommended_width",
                "recommended_height",
                "recommended_steps",
                "recommended_cfg",
                "recommended_sampler",
                "recommended_scheduler",
                "requires_auxiliary_models",
                "auto_install_missing_deps",
            ):
                if key not in entry:
                    continue
                value = entry.get(key)
                if value is None:
                    continue
                if key in path_like_keys:
                    value = sanitize_tti_path(value)
                    if not value:
                        continue
                elif isinstance(value, str):
                    value = value.strip()
                    if not value:
                        continue
                extra_fields[key] = value
        else:
            continue

        if not path_value:
            continue

        normalized_path_key = path_value.strip().replace("\\", "/").lower()
        if normalized_path_key in seen_path_keys:
            continue
        seen_path_keys.add(normalized_path_key)

        if not display_name:
            display_name = _tti_display_name_from_path(path_value, idx)

        base_name = display_name
        candidate = base_name
        suffix = 2
        while candidate.lower() in used_display_names:
            candidate = f"{base_name}_{suffix}"
            suffix += 1
        display_name = candidate
        used_display_names.add(display_name.lower())

        normalized_entry: Dict[str, Any] = {
            "path": path_value,
            "display_name": display_name,
            "introduction": introduction,
        }
        normalized_entry.update(extra_fields)
        models.append(normalized_entry)

    return models


def resolve_tti_default_display_name(text_to_image: Dict[str, Any]) -> str:
    """Resolve default model display name from current/legacy fields."""
    models = normalize_tti_models(
        text_to_image.get("models", []),
        legacy_model_paths=text_to_image.get("model_paths", []),
    )
    if not models:
        return ""

    raw_default = text_to_image.get("default_model_display_name", "")
    if raw_default is not None:
        default_name = str(raw_default).strip()
        if default_name:
            for item in models:
                if item["display_name"].lower() == default_name.lower():
                    return item["display_name"]

    legacy_index = text_to_image.get("default_model_index", 0)
    try:
        idx = int(legacy_index)
    except (TypeError, ValueError):
        idx = 0
    if idx < 0 or idx >= len(models):
        idx = 0
    return models[idx]["display_name"]


def normalize_tti_source(value: Any, default: str = "local") -> str:
    """Normalize the persisted text-to-image source selector."""
    candidate = str(value or "").strip().lower()
    if candidate in SUPPORTED_TTI_SOURCES:
        return candidate
    return default


def normalize_ttv_source(value: Any, default: str = "agnes") -> str:
    """Normalize the persisted text-to-video source selector."""
    candidate = str(value or "").strip().lower()
    if candidate in SUPPORTED_TTV_SOURCES:
        return candidate
    return default


def get_app_root() -> Path:
    """
    Get the application root directory.

    Runtime data is stored relative to the physical executable for packaged
    builds. Source-checkout runs use the local `dist/` depot so the repository
    root is not polluted with a top-level `.reverie` directory.
    """
    env_root = os.getenv("REVERIE_APP_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    launcher_root = get_launcher_root().resolve()
    if getattr(sys, "frozen", False):
        return launcher_root

    try:
        source_root = Path(__file__).resolve().parent.parent
        repo_root = source_root
        if source_root.name.lower() == "reveriecli-py" and (source_root.parent / ".git").exists():
            repo_root = source_root.parent
        is_source_checkout = (
            (source_root / "reverie").exists()
            and (
                (source_root / ".git").exists()
                or (source_root.parent / ".git").exists()
                or (source_root / "setup.py").exists()
                or (source_root / "pyproject.toml").exists()
            )
        )
        if is_source_checkout:
            return (repo_root / "dist").resolve()
    except Exception:
        report_suppressed_exception("resolve source-checkout application root")

    return launcher_root


def get_computer_controller_data_dir(app_root: Optional[Path] = None) -> Path:
    """Return the dedicated runtime data root for Computer Controller mode."""
    root = Path(app_root).resolve() if app_root is not None else get_app_root()
    return root / ".reverie" / "computer-controller"


def get_project_data_name(project_path: Path) -> str:
    """
    Generate the canonical portable project data folder name from the full path.

    Example: `G:\\Vtuber` -> `G_Vtuber`.
    """
    return sanitize_project_name(project_path)


def get_project_data_dir(project_path: Path, app_root: Optional[Path] = None) -> Path:
    """
    Get the project-specific data directory.

    Project data lives under the app's `.reverie/projects/` directory.
    """
    return ProjectStorageResolver.for_project(project_path, launcher_root=app_root).project_dir


@dataclass
class ModelConfig:
    """Configuration for a single model"""
    model: str
    model_display_name: str
    base_url: str
    api_key: str = ""
    max_context_tokens: Optional[int] = None
    provider: str = "openai-chat"
    supports_vision: bool = False
    thinking_mode: Optional[str] = None  # Legacy/runtime-only provider option; not persisted for standard models
    endpoint: str = ""  # Optional custom endpoint path/url for OpenAI-compatible providers
    custom_headers: Dict[str, str] = field(default_factory=dict)  # Optional request headers
    
    def to_dict(self) -> dict:
        payload = {
            "model": self.model,
            "model_display_name": self.model_display_name,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "provider": normalize_model_provider(self.provider),
            "supports_vision": bool(self.supports_vision),
            "custom_headers": dict(self.custom_headers or {}),
        }
        if self.max_context_tokens is not None:
            payload["max_context_tokens"] = self.max_context_tokens
        endpoint = str(self.endpoint or "").strip()
        if endpoint:
            payload["endpoint"] = endpoint
        return payload
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModelConfig':
        raw_headers = data.get('custom_headers', data.get('customHeader', {}))
        custom_headers: Dict[str, str] = {}
        if isinstance(raw_headers, dict):
            for key, value in raw_headers.items():
                k = str(key or '').strip()
                v = str(value or '').strip()
                if k and v:
                    custom_headers[k] = v

        return cls(
            model=data.get('model', ''),
            model_display_name=data.get('model_display_name', data.get('model', '')),
            base_url=data.get('base_url', ''),
            api_key=data.get('api_key', ''),
            max_context_tokens=data.get('max_context_tokens'),
            provider=normalize_model_provider(data.get('provider', 'openai-chat')),
            supports_vision=bool(data.get('supports_vision', data.get('vision', False))),
            thinking_mode=data.get('thinking_mode'),
            endpoint=str(data.get('endpoint', '') or '').strip(),
            custom_headers=custom_headers
        )


@dataclass
class Config:
    """Main configuration"""
    models: List[ModelConfig] = field(default_factory=list)
    active_model_index: int = 0
    active_model_source: str = "standard"  # standard | codex | aihubmix | agnes | sensenova | unlimitedsurf | nvidia | modelscope | webgemini | opencode
    mode: str = "reverie"
    theme: str = "default"
    max_context_tokens: int = 128000
    stream_responses: bool = True
    auto_index: bool = True
    show_status_line: bool = True
    tool_output_style: str = "compact"
    thinking_output_style: str = "full"
    config_version: str = CONFIG_VERSION  # Config file version for migration
    
    # Workspace isolation settings
    use_workspace_config: bool = False  # If True, config is stored in workspace directory
    security: Dict[str, Any] = field(default_factory=lambda: {"permission_level": "workspace_write"})
    
    # API call settings for improved stability
    api_max_retries: int = 5
    api_initial_backoff: float = 1.0
    api_timeout: int = 60
    api_enable_debug_logging: bool = False
    
    # Text-to-image settings
    text_to_image: Dict[str, Any] = field(default_factory=default_text_to_image_config)
    text_to_video: Dict[str, Any] = field(default_factory=default_text_to_video_config)
    codex: Dict[str, Any] = field(default_factory=dict)
    aihubmix: Dict[str, Any] = field(default_factory=default_aihubmix_config)
    agnes: Dict[str, Any] = field(default_factory=default_agnes_config)
    sensenova: Dict[str, Any] = field(default_factory=default_sensenova_config)
    unlimitedsurf: Dict[str, Any] = field(default_factory=default_unlimitedsurf_config)
    nvidia: Dict[str, Any] = field(default_factory=default_nvidia_config)
    modelscope: Dict[str, Any] = field(default_factory=default_modelscope_config)
    webgemini: Dict[str, Any] = field(default_factory=default_webgemini_config)
    opencode: Dict[str, Any] = field(default_factory=default_opencode_config)
    atlas_mode: Dict[str, Any] = field(default_factory=default_atlas_mode_config)
    subagents: Dict[str, Any] = field(default_factory=default_subagent_config)
    
    # Writer mode specific settings
    writer_mode: Dict[str, Any] = field(default_factory=default_writer_mode_config)

    # Gamer mode specific settings
    gamer_mode: Dict[str, Any] = field(default_factory=default_gamer_mode_config)

    def _resolved_nvidia_config(self) -> Dict[str, Any]:
        """Return NVIDIA config augmented with fallback credentials from standard models."""
        cfg = normalize_nvidia_config(self.nvidia)
        if resolve_nvidia_api_key(cfg):
            return cfg

        for model in self.models:
            if not isinstance(model, ModelConfig):
                continue
            api_key = str(getattr(model, "api_key", "") or "").strip()
            base_url = str(getattr(model, "base_url", "") or "").strip()
            if api_key and is_nvidia_api_url(base_url):
                cfg["api_key"] = api_key
                break
        return cfg
    
    @property
    def active_model(self) -> Optional[ModelConfig]:
        source = str(self.active_model_source).lower()
        runtime_nvidia_config = self._resolved_nvidia_config()

        if normalize_mode(self.mode) == "computer-controller":
            runtime_nvidia_model = build_nvidia_computer_controller_runtime_model_data(runtime_nvidia_config)
            if runtime_nvidia_model:
                return ModelConfig.from_dict(runtime_nvidia_model)
            return None

        if source == "codex":
            runtime_codex_model = build_codex_runtime_model_data(self.codex)
            return ModelConfig.from_dict(runtime_codex_model) if runtime_codex_model else None

        if source == "aihubmix":
            runtime_aihubmix_model = build_aihubmix_runtime_model_data(self.aihubmix)
            return ModelConfig.from_dict(runtime_aihubmix_model) if runtime_aihubmix_model else None

        if source == "agnes":
            runtime_agnes_model = build_agnes_runtime_model_data(self.agnes)
            return ModelConfig.from_dict(runtime_agnes_model) if runtime_agnes_model else None

        if source == "sensenova":
            runtime_sensenova_model = build_sensenova_runtime_model_data(self.sensenova)
            return ModelConfig.from_dict(runtime_sensenova_model) if runtime_sensenova_model else None

        if source == "unlimitedsurf":
            runtime_unlimitedsurf_model = build_unlimitedsurf_runtime_model_data(self.unlimitedsurf)
            return ModelConfig.from_dict(runtime_unlimitedsurf_model) if runtime_unlimitedsurf_model else None

        if source == "nvidia":
            runtime_nvidia_model = build_nvidia_runtime_model_data(runtime_nvidia_config)
            return ModelConfig.from_dict(runtime_nvidia_model) if runtime_nvidia_model else None

        if source == "modelscope":
            runtime_modelscope_model = build_modelscope_runtime_model_data(self.modelscope)
            return ModelConfig.from_dict(runtime_modelscope_model) if runtime_modelscope_model else None

        if source == "webgemini":
            runtime_webgemini_model = build_webgemini_runtime_model_data(self.webgemini)
            return ModelConfig.from_dict(runtime_webgemini_model) if runtime_webgemini_model else None

        if source == "opencode":
            runtime_opencode_model = build_opencode_runtime_model_data(self.opencode)
            return ModelConfig.from_dict(runtime_opencode_model) if runtime_opencode_model else None

        if 0 <= self.active_model_index < len(self.models):
            return self.models[self.active_model_index]
        return None
    
    def to_dict(self) -> dict:
        text_to_image_defaults = default_text_to_image_config()
        text_to_image = dict(self.text_to_image) if isinstance(self.text_to_image, dict) else dict(text_to_image_defaults)
        for key, value in text_to_image_defaults.items():
            if key not in text_to_image:
                text_to_image[key] = value
        if isinstance(text_to_image.get("aihubmix"), dict):
            nested_aihubmix = dict(text_to_image_defaults["aihubmix"])
            nested_aihubmix.update(text_to_image.get("aihubmix", {}))
            text_to_image["aihubmix"] = nested_aihubmix
        else:
            text_to_image["aihubmix"] = dict(text_to_image_defaults["aihubmix"])
        if isinstance(text_to_image.get("pollinations"), dict):
            nested_pollinations = dict(text_to_image_defaults["pollinations"])
            nested_pollinations.update(text_to_image.get("pollinations", {}))
            text_to_image["pollinations"] = nested_pollinations
        else:
            text_to_image["pollinations"] = dict(text_to_image_defaults["pollinations"])
        if isinstance(text_to_image.get("agnes"), dict):
            nested_agnes_tti = dict(text_to_image_defaults["agnes"])
            nested_agnes_tti.update(text_to_image.get("agnes", {}))
            text_to_image["agnes"] = nested_agnes_tti
        else:
            text_to_image["agnes"] = dict(text_to_image_defaults["agnes"])
        if isinstance(text_to_image.get("sensenova"), dict):
            nested_sensenova_tti = dict(text_to_image_defaults["sensenova"])
            nested_sensenova_tti.update(text_to_image.get("sensenova", {}))
            text_to_image["sensenova"] = nested_sensenova_tti
        else:
            text_to_image["sensenova"] = dict(text_to_image_defaults["sensenova"])
        text_to_image['active_source'] = normalize_tti_source(text_to_image.get('active_source', 'local'))
        text_to_image['models'] = normalize_tti_models(
            text_to_image.get('models', []),
            legacy_model_paths=text_to_image.get('model_paths', [])
        )
        text_to_image['default_model_display_name'] = resolve_tti_default_display_name(text_to_image)
        text_to_image.pop('model_paths', None)
        text_to_image.pop('default_model_index', None)
        tti_models = text_to_image['models']
        text_to_video_defaults = default_text_to_video_config()
        text_to_video = dict(self.text_to_video) if isinstance(self.text_to_video, dict) else dict(text_to_video_defaults)
        for key, value in text_to_video_defaults.items():
            if key not in text_to_video:
                text_to_video[key] = value
        if isinstance(text_to_video.get("agnes"), dict):
            nested_agnes_ttv = dict(text_to_video_defaults["agnes"])
            nested_agnes_ttv.update(text_to_video.get("agnes", {}))
            text_to_video["agnes"] = nested_agnes_ttv
        else:
            text_to_video["agnes"] = dict(text_to_video_defaults["agnes"])
        text_to_video["active_source"] = normalize_ttv_source(text_to_video.get("active_source", "agnes"))
        codex = normalize_codex_config(self.codex)
        aihubmix = normalize_aihubmix_config(self.aihubmix)
        agnes = normalize_agnes_config(self.agnes)
        sensenova = normalize_sensenova_config(self.sensenova)
        unlimitedsurf = normalize_unlimitedsurf_config(self.unlimitedsurf)
        nvidia = normalize_nvidia_config(self.nvidia)
        modelscope = normalize_modelscope_config(self.modelscope)
        webgemini = normalize_webgemini_config(self.webgemini)
        opencode = normalize_opencode_config(self.opencode)
        atlas_mode = normalize_atlas_mode_config(self.atlas_mode)
        subagents = normalize_subagent_config(self.subagents)
        active_model_source = normalize_active_model_source(self.active_model_source)

        return {
            'models': [m.to_dict() for m in self.models],
            'active_model_index': self.active_model_index,
            'active_model_source': active_model_source,
            'mode': self.mode,
            'theme': self.theme,
            'max_context_tokens': self.max_context_tokens,
            'stream_responses': self.stream_responses,
            'auto_index': self.auto_index,
            'show_status_line': self.show_status_line,
            'tool_output_style': normalize_tool_output_style(self.tool_output_style),
            'thinking_output_style': normalize_thinking_output_style(self.thinking_output_style),
            'writer_mode': normalize_writer_mode_config(self.writer_mode),
            'gamer_mode': normalize_gamer_mode_config(self.gamer_mode),
            'config_version': self.config_version,
            'use_workspace_config': self.use_workspace_config,
            'security': {
                'permission_level': normalize_permission_level(
                    (self.security or {}).get('permission_level') if isinstance(self.security, dict) else None
                )
            },
            'api_max_retries': self.api_max_retries,
            'api_initial_backoff': self.api_initial_backoff,
            'api_timeout': self.api_timeout,
            'api_enable_debug_logging': self.api_enable_debug_logging,
            'text_to_image': text_to_image,
            'text_to_video': text_to_video,
            'codex': codex,
            'aihubmix': aihubmix,
            'agnes': agnes,
            'sensenova': sensenova,
            'unlimitedsurf': unlimitedsurf,
            'nvidia': nvidia,
            'modelscope': modelscope,
            'webgemini': webgemini,
            'opencode': opencode,
            'atlas_mode': atlas_mode,
            'subagents': subagents,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        models = [
            ModelConfig.from_dict(m) 
            for m in data.get('models', [])
        ]
        text_to_image = default_text_to_image_config()
        loaded_t2i = data.get('text_to_image', data.get('tti', {}))
        if isinstance(loaded_t2i, dict):
            text_to_image.update(loaded_t2i)
            if isinstance(loaded_t2i.get("aihubmix"), dict):
                nested_aihubmix = dict(default_text_to_image_config()["aihubmix"])
                nested_aihubmix.update(loaded_t2i.get("aihubmix", {}))
                text_to_image["aihubmix"] = nested_aihubmix
            if isinstance(loaded_t2i.get("pollinations"), dict):
                nested_pollinations = dict(default_text_to_image_config()["pollinations"])
                nested_pollinations.update(loaded_t2i.get("pollinations", {}))
                text_to_image["pollinations"] = nested_pollinations
            if isinstance(loaded_t2i.get("agnes"), dict):
                nested_agnes_tti = dict(default_text_to_image_config()["agnes"])
                nested_agnes_tti.update(loaded_t2i.get("agnes", {}))
                text_to_image["agnes"] = nested_agnes_tti
            if isinstance(loaded_t2i.get("sensenova"), dict):
                nested_sensenova_tti = dict(default_text_to_image_config()["sensenova"])
                nested_sensenova_tti.update(loaded_t2i.get("sensenova", {}))
                text_to_image["sensenova"] = nested_sensenova_tti
        top_level_tti_models = data.get('tti-models', None)
        if top_level_tti_models is not None:
            text_to_image['models'] = top_level_tti_models
        text_to_image['models'] = normalize_tti_models(
            text_to_image.get('models', []),
            legacy_model_paths=text_to_image.get('model_paths', [])
        )
        text_to_image['active_source'] = normalize_tti_source(text_to_image.get('active_source', 'local'))
        text_to_image['default_model_display_name'] = resolve_tti_default_display_name(text_to_image)
        text_to_image.pop('model_paths', None)
        text_to_image.pop('default_model_index', None)
        text_to_video = default_text_to_video_config()
        loaded_ttv = data.get('text_to_video', data.get('ttv', {}))
        if isinstance(loaded_ttv, dict):
            text_to_video.update(loaded_ttv)
            if isinstance(loaded_ttv.get("agnes"), dict):
                nested_agnes_ttv = dict(default_text_to_video_config()["agnes"])
                nested_agnes_ttv.update(loaded_ttv.get("agnes", {}))
                text_to_video["agnes"] = nested_agnes_ttv
        text_to_video["active_source"] = normalize_ttv_source(text_to_video.get("active_source", "agnes"))
        raw_codex = data.get('codex', {})
        codex = normalize_codex_config(raw_codex)
        raw_aihubmix = data.get('aihubmix', {})
        aihubmix = normalize_aihubmix_config(raw_aihubmix)
        raw_agnes = data.get('agnes', {})
        agnes = normalize_agnes_config(raw_agnes)
        raw_sensenova = data.get('sensenova', data.get('sense', {}))
        sensenova = normalize_sensenova_config(raw_sensenova)
        if not str(sensenova.get("api_key", "") or "").strip():
            legacy_sensenova_model = next(
                (
                    model
                    for model in models
                    if "token.sensenova.cn" in str(model.base_url or "").lower()
                    and str(model.api_key or "").strip()
                ),
                None,
            )
            if legacy_sensenova_model is not None:
                sensenova["api_key"] = str(legacy_sensenova_model.api_key).strip()
        raw_unlimitedsurf = data.get('unlimitedsurf', data.get('unlimited_surf', data.get('us', {})))
        unlimitedsurf = normalize_unlimitedsurf_config(raw_unlimitedsurf)
        raw_nvidia = data.get('nvidia', {})
        nvidia = normalize_nvidia_config(raw_nvidia)
        raw_modelscope = data.get('modelscope', {})
        modelscope = normalize_modelscope_config(raw_modelscope)
        raw_webgemini = data.get('webgemini', {})
        webgemini = normalize_webgemini_config(raw_webgemini)
        raw_opencode = data.get('opencode', data.get('oc', {}))
        opencode = normalize_opencode_config(raw_opencode)
        raw_atlas_mode = data.get('atlas_mode', {})
        atlas_mode = normalize_atlas_mode_config(raw_atlas_mode)
        raw_subagents = data.get('subagents', {})
        subagents = normalize_subagent_config(raw_subagents)
        active_model_source = normalize_active_model_source(data.get('active_model_source', 'standard'))

        return cls(
            models=models,
            active_model_index=data.get('active_model_index', 0),
            active_model_source=active_model_source,
            mode=data.get('mode', 'reverie'),
            theme=data.get('theme', 'default'),
            max_context_tokens=data.get('max_context_tokens', 128000),
            stream_responses=data.get('stream_responses', True),
            auto_index=data.get('auto_index', True),
            show_status_line=data.get('show_status_line', True),
            tool_output_style=normalize_tool_output_style(data.get('tool_output_style', 'compact')),
            thinking_output_style=normalize_thinking_output_style(data.get('thinking_output_style', 'full')),
            writer_mode=normalize_writer_mode_config(data.get('writer_mode', {})),
            gamer_mode=normalize_gamer_mode_config(data.get('gamer_mode', {})),
            config_version=data.get('config_version', CONFIG_VERSION),
            use_workspace_config=data.get('use_workspace_config', False),
            security=data.get('security', {"permission_level": "workspace_write"}),
            api_max_retries=data.get('api_max_retries', 5),
            api_initial_backoff=data.get('api_initial_backoff', 1.0),
            api_timeout=data.get('api_timeout', 60),
            api_enable_debug_logging=data.get('api_enable_debug_logging', False),
            text_to_image=text_to_image,
            text_to_video=text_to_video,
            codex=codex,
            aihubmix=aihubmix,
            agnes=agnes,
            sensenova=sensenova,
            unlimitedsurf=unlimitedsurf,
            nvidia=nvidia,
            modelscope=modelscope,
            webgemini=webgemini,
            opencode=opencode,
            atlas_mode=atlas_mode,
            subagents=subagents,
        )


class ConfigManager:
    """
    Manages configuration persistence with workspace isolation support.

    Configuration can be stored in two modes:
    1. Active/global profile: config.json in
       <app_root>/.reverie/
    2. Workspace profile: config.json in
       <app_root>/.reverie/projects/[project-path-key]/

    Legacy per-project `config.global.json` files are still read for migration,
    but default writes now target the shared `.reverie/config.json` profile
    unless workspace mode is explicitly enabled for the current project.
    """
    
    def __init__(self, project_root: Path, force_workspace_config: bool = False):
        self.project_root = project_root
        self._logger = logging.getLogger(__name__)

        # Use app root for runtime data (next to exe file or script directory).
        self.app_root = get_app_root()
        self.storage_resolver = ProjectStorageResolver.for_project(project_root, launcher_root=self.app_root)
        self.data_root = self.storage_resolver.projects_root
        self.project_data_dir = self.storage_resolver.project_dir
        self.global_config_path = self.app_root / '.reverie' / 'config.json'
        self.workspace_config_path = self.project_data_dir / 'config.json'

        # Legacy paths kept for migration from older builds.
        self.legacy_reverie_dir = self.app_root / '.reverie'
        self.legacy_global_config_path = self.global_config_path
        self.legacy_project_global_config_path = self.project_data_dir / 'config.global.json'
        self.legacy_workspace_reverie_dir = self.project_root / '.reverie'
        self.legacy_workspace_config_path = self.legacy_workspace_reverie_dir / 'config.json'

        self._config: Optional[Config] = None
        self._last_mtime: float = 0
        self._loaded_config_path: Optional[Path] = None
        self._pending_load_notice: Optional[Dict[str, str]] = None
        self._last_load_notice_key: Optional[tuple[str, str, str]] = None

        # Determine config path based on setting and any persisted workspace state.
        self._use_workspace_config = bool(
            force_workspace_config or self._detect_workspace_mode_from_files()
        )
        self._update_config_path()
    
    def _update_config_path(self) -> None:
        """Update config path based on current mode"""
        if self._use_workspace_config:
            self.config_path = self.workspace_config_path
        else:
            self.config_path = self.global_config_path

    def _get_legacy_mirror_path(self) -> Optional[Path]:
        """Return the compatibility config path for the current storage mode."""
        if self._use_workspace_config:
            return None
        return self.legacy_global_config_path

    def _read_json_dict(self, path: Path) -> Optional[Dict[str, Any]]:
        """Best-effort JSON object reader used for lightweight mode detection."""
        if not path.exists():
            return None
        try:
            data = self._load_json_payload(path, persist_repairs=False, record_notice=False)
            return data if isinstance(data, dict) else None
        except Exception as exc:
            self._logger.debug("Failed to read JSON config candidate %s", path, exc_info=True)
            return None

    def _set_load_notice(
        self,
        *,
        key: tuple[str, str, str],
        title: str,
        detail: str,
        status: str = "warning",
    ) -> None:
        """Queue one user-facing config-load notice for later TUI rendering."""
        if self._last_load_notice_key == key:
            return
        self._last_load_notice_key = key
        self._pending_load_notice = {
            "title": str(title or "").strip(),
            "detail": str(detail or "").strip(),
            "status": str(status or "warning").strip() or "warning",
        }

    def consume_load_notice(self) -> Optional[Dict[str, str]]:
        """Return and clear the latest deferred config-load notice."""
        notice = dict(self._pending_load_notice or {}) if self._pending_load_notice else None
        self._pending_load_notice = None
        return notice

    def _create_invalid_config_backup(self, path: Path, raw_text: str) -> Optional[Path]:
        """Persist the original malformed config beside the repaired one."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = path.with_name(f"{path.name}.invalid-{timestamp}.bak")
            counter = 1
            while backup_path.exists():
                backup_path = path.with_name(f"{path.name}.invalid-{timestamp}-{counter}.bak")
                counter += 1
            backup_path.write_text(raw_text, encoding="utf-8")
            return backup_path
        except Exception:
            self._logger.debug("Failed to write malformed-config backup for %s", path, exc_info=True)
            return None

    def _load_json_payload(
        self,
        path: Path,
        *,
        persist_repairs: bool,
        record_notice: bool,
    ) -> Any:
        """Load JSON with best-effort repair for literal control chars in strings."""
        raw_text = path.read_text(encoding="utf-8-sig")
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            backup_path = self._create_invalid_config_backup(path, raw_text) if persist_repairs else None
            repaired_text, changed = _escape_invalid_json_string_control_chars(raw_text)
            if not changed:
                backup_detail = f" Backup saved to {backup_path}." if backup_path is not None else ""
                raise ValueError(
                    f"Could not automatically repair malformed config at {path}.{backup_detail} Parser error: {exc}"
                ) from exc

            try:
                data = json.loads(repaired_text)
            except json.JSONDecodeError as repair_exc:
                backup_detail = f" Backup saved to {backup_path}." if backup_path is not None else ""
                raise ValueError(
                    f"Could not automatically repair malformed config at {path}.{backup_detail} Parser error: {repair_exc}"
                ) from repair_exc

            if persist_repairs:
                try:
                    write_json_secure(path, data)
                except Exception:
                    self._logger.debug("Failed to persist repaired config at %s", path, exc_info=True)
                if record_notice:
                    repair_signature = hashlib.sha1(raw_text.encode("utf-8", errors="replace")).hexdigest()
                    detail = f"Recovered malformed config at {path}."
                    if backup_path is not None:
                        detail += f"\nBackup saved to {backup_path}."
                    detail += "\nLiteral control characters inside JSON strings were escaped automatically."
                    self._set_load_notice(
                        key=(str(path), repair_signature, "repaired"),
                        title="Recovered malformed config",
                        detail=detail,
                        status="warning",
                    )
            return data

    def _detect_workspace_mode_from_files(self) -> bool:
        """
        Detect whether this project should default to workspace mode.

        Workspace enable/disable is persisted on the workspace config itself.
        Only an explicit `use_workspace_config=true` turns workspace mode on.
        Older workspace configs without the flag no longer override the global
        profile by mere existence.
        """
        workspace_found = False
        for candidate in (self.workspace_config_path, self.legacy_workspace_config_path):
            if not candidate.exists():
                continue
            workspace_found = True
            data = self._read_json_dict(candidate)
            if isinstance(data, dict) and 'use_workspace_config' in data:
                return bool(data.get('use_workspace_config', False))
        return False

    def _sync_legacy_mirror(self, serialized: Dict[str, Any]) -> None:
        """Best-effort compatibility sync for older launchers and visible legacy files."""
        legacy_path = self._get_legacy_mirror_path()
        if legacy_path is None:
            return
        if legacy_path.resolve(strict=False) == self.config_path.resolve(strict=False):
            return
        try:
            write_json_secure(legacy_path, serialized)
        except Exception as exc:
            self._logger.warning(
                "Failed to sync legacy config mirror at %s: %s",
                legacy_path,
                exc,
            )

    def _is_workspace_candidate_path(self, path: Path) -> bool:
        """Return True when the path is one of the workspace-profile candidates."""
        resolved = path.resolve(strict=False)
        return any(
            resolved == candidate.resolve(strict=False)
            for candidate in self._path_candidates_for_mode(True)
        )

    def _candidate_records(self) -> List[Dict[str, Any]]:
        """Inspect existing config candidates with enough metadata to choose a source."""
        records: List[Dict[str, Any]] = []
        seen = set()
        for workspace_mode in (False, True):
            canonical = self.workspace_config_path if workspace_mode else self.global_config_path
            for candidate in self._path_candidates_for_mode(workspace_mode):
                key = str(candidate.resolve(strict=False)).lower()
                if key in seen or not candidate.exists():
                    continue
                seen.add(key)
                data = self._read_json_dict(candidate)
                workspace_flag = None
                if isinstance(data, dict) and 'use_workspace_config' in data:
                    workspace_flag = bool(data.get('use_workspace_config', False))
                try:
                    mtime = os.path.getmtime(candidate)
                except OSError:
                    mtime = 0.0
                records.append(
                    {
                        "path": candidate,
                        "workspace_mode": workspace_mode,
                        "workspace_flag": workspace_flag,
                        "mtime": mtime,
                        "is_canonical": candidate.resolve(strict=False) == canonical.resolve(strict=False),
                    }
                )
        return records

    def _pick_active_record(self) -> Optional[Dict[str, Any]]:
        """Choose the config source record to load from."""
        records = self._candidate_records()
        if not records:
            return None

        def _rank(record: Dict[str, Any]) -> tuple[float, int]:
            return (float(record.get("mtime", 0.0)), 1 if record.get("is_canonical") else 0)

        workspace_enabled = [
            record for record in records
            if record.get("workspace_mode") and record.get("workspace_flag") is True
        ]
        if workspace_enabled:
            return max(workspace_enabled, key=_rank)

        global_records = [record for record in records if not record.get("workspace_mode")]
        if global_records:
            return max(global_records, key=_rank)

        return None

    def get_active_config_path(self) -> Path:
        """Return the currently effective config path for this workspace."""
        if self._loaded_config_path is not None:
            return self._loaded_config_path

        record = self._pick_active_record()
        if record is not None:
            return record["path"]
        return self.config_path

    def _path_candidates_for_mode(self, workspace_mode: bool) -> List[Path]:
        """Return new + legacy config paths for one logical mode."""
        if workspace_mode:
            candidates = [self.workspace_config_path]
            legacy_workspace = self.legacy_workspace_config_path.resolve(strict=False)
            global_config = self.global_config_path.resolve(strict=False)
            workspace_config = self.workspace_config_path.resolve(strict=False)
            if legacy_workspace not in {global_config, workspace_config}:
                candidates.append(self.legacy_workspace_config_path)
            return candidates
        candidates = [
            self.global_config_path,
            self.legacy_global_config_path,
            self.legacy_project_global_config_path,
        ]
        unique: List[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate.resolve(strict=False)).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def _load_path_candidates(self) -> List[Path]:
        """Return config paths in preferred load order."""
        candidates = self._path_candidates_for_mode(self._use_workspace_config)
        candidates.extend(self._path_candidates_for_mode(not self._use_workspace_config))

        unique: List[Path] = []
        seen = set()
        for candidate in candidates:
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def _find_existing_path(self, workspace_mode: bool) -> Optional[Path]:
        """Return the first existing config path for a logical mode."""
        for candidate in self._path_candidates_for_mode(workspace_mode):
            if candidate.exists():
                return candidate
        return None
    
    def set_workspace_mode(self, enabled: bool) -> None:
        """
        Enable or disable workspace-local configuration mode.
        
        Args:
            enabled: If True, config is stored in workspace directory.
                    If False, config is stored in global app directory.
        """
        if self._use_workspace_config != enabled:
            self._use_workspace_config = enabled
            self._update_config_path()
            # Clear cached config to force reload from new location
            self._config = None
            self._last_mtime = 0
            self._loaded_config_path = None
    
    def is_workspace_mode(self) -> bool:
        """Check if workspace-local configuration mode is enabled"""
        return self._use_workspace_config
    
    def copy_config_to_workspace(self) -> bool:
        """
        Copy global configuration to workspace configuration.
        
        Returns:
            True if copy was successful, False otherwise
        """
        source_path = self._find_existing_path(False)
        if source_path is None:
            return False

        try:
            # Load global config
            data = self._load_json_payload(source_path, persist_repairs=True, record_notice=True)

            # Update to workspace mode
            data['use_workspace_config'] = True

            # Ensure project cache directory exists
            self.ensure_dirs()

            # Save to workspace config
            write_json_secure(self.workspace_config_path, data)

            # Clear cache and switch to workspace mode
            self._config = None
            self._last_mtime = 0
            self._loaded_config_path = None
            self.set_workspace_mode(True)
            
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to copy config to workspace: {e}")
            return False

    def set_workspace_config_enabled(self, enabled: bool) -> bool:
        """
        Persist this project's workspace-mode preference on the workspace config.

        This keeps workspace enable/disable state project-local without mutating
        the shared global config.
        """
        source_path = self._find_existing_path(True)
        if source_path is None:
            if not enabled:
                return True
            return False

        data = self._read_json_dict(source_path)
        if data is None:
            try:
                data = self._load_json_payload(source_path, persist_repairs=True, record_notice=True)
            except Exception:
                data = None
        if not isinstance(data, dict):
            data = Config().to_dict()

        data['use_workspace_config'] = bool(enabled)
        self.ensure_dirs()
        write_json_secure(self.workspace_config_path, data)
        return True
    
    def copy_config_to_global(self) -> bool:
        """
        Copy workspace configuration to global configuration.
        
        Returns:
            True if copy was successful, False otherwise
        """
        source_path = self._find_existing_path(True)
        if source_path is None:
            return False

        try:
            # Load workspace config
            data = self._load_json_payload(source_path, persist_repairs=True, record_notice=True)

            # Update to global mode
            data['use_workspace_config'] = False

            # Ensure project cache directory exists
            self.ensure_dirs()

            # Save to global config
            write_json_secure(self.global_config_path, data)
            self.set_workspace_config_enabled(False)

            # Clear cache and switch to global mode
            self._config = None
            self._last_mtime = 0
            self._loaded_config_path = None
            self.set_workspace_mode(False)
            
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to copy config to global: {e}")
            return False
    
    def has_workspace_config(self) -> bool:
        """Check if workspace configuration file exists"""
        return self._find_existing_path(True) is not None
    
    def has_global_config(self) -> bool:
        """Check if global configuration file exists"""
        return self._find_existing_path(False) is not None
    
    def ensure_dirs(self) -> None:
        """Create necessary directories"""
        self.storage_resolver.ensure_project_dir()
    
    def load(self) -> Config:
        """Load configuration from file, reloading if file changed"""
        active_record = self._pick_active_record()
        source_path = active_record["path"] if active_record is not None else None

        # Check if we need to switch config mode based on loaded config
        if source_path is not None:
            self._use_workspace_config = bool(active_record.get("workspace_mode")) if active_record else self._is_workspace_candidate_path(source_path)
            self._update_config_path()
            current_mtime = os.path.getmtime(source_path)
            # Reload if file changed or not loaded yet
            if self._config is None or current_mtime > self._last_mtime:
                try:
                    data = self._load_json_payload(
                        source_path,
                        persist_repairs=True,
                        record_notice=True,
                    )
                    self._config = Config.from_dict(data)
                    try:
                        self._last_mtime = os.path.getmtime(source_path)
                    except OSError:
                        self._last_mtime = current_mtime
                    self._loaded_config_path = source_path

                    # Auto-update config file if it's missing new fields or still
                    # lives in the active canonical location.
                    if self._needs_config_update(data):
                        self.save(self._config)
                        # Update mtime after saving to avoid infinite loop
                        self._last_mtime = os.path.getmtime(self.get_active_config_path())
                    else:
                        if not self._is_workspace_candidate_path(source_path):
                            self._sync_legacy_mirror(self._config.to_dict())
                except Exception as exc:
                    self._logger.debug(
                        "Failed to load or repair config from %s",
                        source_path,
                        exc_info=True,
                    )
                    notice_mtime = current_mtime
                    notice_key = (
                        str(source_path),
                        f"{notice_mtime:.6f}",
                        f"{type(exc).__name__}:{exc}",
                    )
                    self._set_load_notice(
                        key=notice_key,
                        title="Failed to repair config",
                        detail=str(exc),
                        status="error",
                    )
                    self._config = Config()
                    self._loaded_config_path = source_path
                    self._last_mtime = current_mtime
        else:
            self._use_workspace_config = False
            self._update_config_path()
            self._config = Config()
            self._loaded_config_path = self.config_path
            self.ensure_dirs()
            if not self.config_path.exists():
                try:
                    self.save(self._config)
                    self._set_load_notice(
                        key=(str(self.config_path), "created", "default-config"),
                        title="Created default config",
                        detail=f"Default configuration created at {self.config_path}. You can edit this file manually or use /model inside Reverie.",
                        status="info",
                    )
                except Exception:
                    self._logger.debug("Failed to persist default config at %s", self.config_path, exc_info=True)
        
        return self._config
    
    def _needs_config_update(self, data: dict) -> bool:
        """Check if the loaded config needs to be updated with new fields"""
        needs_update = False
        
        # Check if config_version is missing or outdated
        current_version = data.get('config_version', '0.0.0')
        if is_config_version_older(current_version):
            needs_update = True
        
        # Check if any model is missing provider field
        models = data.get('models', [])
        for model in models:
            if 'provider' not in model:
                needs_update = True
                break
            raw_provider = str(model.get('provider', '') or '').strip().lower()
            if normalize_model_provider(raw_provider) != raw_provider:
                needs_update = True
                break
        
        # Migrate standard model entries from legacy thinking_mode to explicit vision capability.
        for model in models:
            if 'supports_vision' not in model:
                needs_update = True
                break
            if 'thinking_mode' in model:
                needs_update = True
                break
            endpoint = str(model.get('endpoint', '') or '').strip() if isinstance(model, dict) else ''
            if isinstance(model, dict) and 'endpoint' in model and not endpoint:
                needs_update = True
                break
        
        # Check if Config is missing any new fields
        if 'config_version' not in data:
            needs_update = True
        
        # Check if use_workspace_config field is missing
        if 'use_workspace_config' not in data:
            needs_update = True
        
        # Check if API settings fields are missing
        api_fields = ['api_max_retries', 'api_initial_backoff', 'api_timeout', 'api_enable_debug_logging']
        for field in api_fields:
            if field not in data:
                needs_update = True
                break

        if 'tool_output_style' not in data:
            needs_update = True
        elif normalize_tool_output_style(data.get('tool_output_style', 'compact')) != str(data.get('tool_output_style', '')).strip().lower():
            needs_update = True

        if 'thinking_output_style' not in data:
            needs_update = True
        elif normalize_thinking_output_style(data.get('thinking_output_style', 'full')) != str(data.get('thinking_output_style', '')).strip().lower():
            needs_update = True

        # Check if active_model_source field is missing/invalid
        active_model_source = normalize_active_model_source(data.get('active_model_source', ''))
        raw_active_model_source = str(data.get('active_model_source', '')).strip().lower().replace("-", "_")
        if active_model_source not in SUPPORTED_ACTIVE_MODEL_SOURCES or raw_active_model_source != active_model_source:
            needs_update = True

        # Gemini CLI reverse-proxy settings are legacy and are removed on the next save.
        if 'geminicli' in data:
            needs_update = True

        # Check if codex section is missing
        if 'codex' not in data:
            needs_update = True
        elif not isinstance(data.get('codex'), dict):
            needs_update = True
        else:
            for field_name in default_codex_config().keys():
                if field_name not in data.get('codex', {}):
                    needs_update = True
                    break

        # Check if aihubmix section is missing
        if 'aihubmix' not in data:
            needs_update = True
        elif not isinstance(data.get('aihubmix'), dict):
            needs_update = True
        else:
            for field_name in default_aihubmix_config().keys():
                if field_name not in data.get('aihubmix', {}):
                    needs_update = True
                    break

        # Check if agnes section is missing
        if 'agnes' not in data:
            needs_update = True
        elif not isinstance(data.get('agnes'), dict):
            needs_update = True
        else:
            for field_name in default_agnes_config().keys():
                if field_name not in data.get('agnes', {}):
                    needs_update = True
                    break

        # Check if sensenova section is missing
        if 'sensenova' not in data:
            needs_update = True
        elif not isinstance(data.get('sensenova'), dict):
            needs_update = True
        else:
            for field_name in default_sensenova_config().keys():
                if field_name not in data.get('sensenova', {}):
                    needs_update = True
                    break

        # Check if unlimitedsurf section is missing
        if 'unlimitedsurf' not in data:
            needs_update = True
        elif not isinstance(data.get('unlimitedsurf'), dict):
            needs_update = True
        else:
            for field_name in default_unlimitedsurf_config().keys():
                if field_name not in data.get('unlimitedsurf', {}):
                    needs_update = True
                    break

        # Check if nvidia section is missing
        if 'nvidia' not in data:
            needs_update = True
        elif not isinstance(data.get('nvidia'), dict):
            needs_update = True
        else:
            for field_name in default_nvidia_config().keys():
                if field_name not in data.get('nvidia', {}):
                    needs_update = True
                    break

        # Check if modelscope section is missing
        if 'modelscope' not in data:
            needs_update = True
        elif not isinstance(data.get('modelscope'), dict):
            needs_update = True
        else:
            for field_name in default_modelscope_config().keys():
                if field_name not in data.get('modelscope', {}):
                    needs_update = True
                    break

        # Check if opencode section is missing
        if 'opencode' not in data:
            needs_update = True
        elif not isinstance(data.get('opencode'), dict):
            needs_update = True
        else:
            for field_name in default_opencode_config().keys():
                if field_name not in data.get('opencode', {}):
                    needs_update = True
                    break

        # Check if atlas_mode section is missing
        if 'atlas_mode' not in data:
            needs_update = True
        elif not isinstance(data.get('atlas_mode'), dict):
            needs_update = True
        else:
            for field_name in default_atlas_mode_config().keys():
                if field_name not in data.get('atlas_mode', {}):
                    needs_update = True
                    break

        if 'subagents' not in data:
            needs_update = True
        elif normalize_subagent_config(data.get('subagents')) != data.get('subagents'):
            needs_update = True

        # Check if gamer_mode field is missing
        if 'gamer_mode' not in data:
            needs_update = True
        elif not isinstance(data.get('gamer_mode'), dict):
            needs_update = True
        else:
            for field_name in default_gamer_mode_config().keys():
                if field_name not in data.get('gamer_mode', {}):
                    needs_update = True
                    break

        if 'writer_mode' not in data:
            needs_update = True
        elif not isinstance(data.get('writer_mode'), dict):
            needs_update = True
        else:
            for field_name in default_writer_mode_config().keys():
                if field_name not in data.get('writer_mode', {}):
                    needs_update = True
                    break
        
        # Check if text_to_image section is missing or incomplete
        if 'text_to_image' not in data:
            needs_update = True
        else:
            text_to_image = data.get('text_to_image')
            if not isinstance(text_to_image, dict):
                needs_update = True
            else:
                for field_name in default_text_to_image_config().keys():
                    if field_name not in text_to_image:
                        needs_update = True
                        break
                tti_aihubmix_defaults = default_text_to_image_config().get("aihubmix", {})
                tti_aihubmix = text_to_image.get("aihubmix", {})
                if not isinstance(tti_aihubmix, dict):
                    needs_update = True
                else:
                    for field_name in tti_aihubmix_defaults.keys():
                        if field_name not in tti_aihubmix:
                            needs_update = True
                            break
                tti_pollinations_defaults = default_text_to_image_config().get("pollinations", {})
                tti_pollinations = text_to_image.get("pollinations", {})
                if not isinstance(tti_pollinations, dict):
                    needs_update = True
                else:
                    for field_name in tti_pollinations_defaults.keys():
                        if field_name not in tti_pollinations:
                            needs_update = True
                            break
                tti_agnes_defaults = default_text_to_image_config().get("agnes", {})
                tti_agnes = text_to_image.get("agnes", {})
                if not isinstance(tti_agnes, dict):
                    needs_update = True
                else:
                    for field_name in tti_agnes_defaults.keys():
                        if field_name not in tti_agnes:
                            needs_update = True
                            break
                tti_sensenova_defaults = default_text_to_image_config().get("sensenova", {})
                tti_sensenova = text_to_image.get("sensenova", {})
                if not isinstance(tti_sensenova, dict):
                    needs_update = True
                else:
                    for field_name in tti_sensenova_defaults.keys():
                        if field_name not in tti_sensenova:
                            needs_update = True
                            break
                models = text_to_image.get('models', [])
                if not isinstance(models, list):
                    needs_update = True
                else:
                    for model_item in models:
                        if not isinstance(model_item, dict):
                            needs_update = True
                            break
                        if 'path' not in model_item or 'display_name' not in model_item or 'introduction' not in model_item:
                            needs_update = True
                            break
                # Old config keys from pre-2.0.1 TTI format should be migrated.
                if 'model_paths' in text_to_image or 'default_model_index' in text_to_image:
                    needs_update = True

        # Check if text_to_video section is missing or incomplete
        if 'text_to_video' not in data:
            needs_update = True
        else:
            text_to_video = data.get('text_to_video')
            if not isinstance(text_to_video, dict):
                needs_update = True
            else:
                for field_name in default_text_to_video_config().keys():
                    if field_name not in text_to_video:
                        needs_update = True
                        break
                ttv_agnes_defaults = default_text_to_video_config().get("agnes", {})
                ttv_agnes = text_to_video.get("agnes", {})
                if not isinstance(ttv_agnes, dict):
                    needs_update = True
                else:
                    for field_name in ttv_agnes_defaults.keys():
                        if field_name not in ttv_agnes:
                            needs_update = True
                            break

        # Canonical config now stores TTI models only under text_to_image.models.
        if 'tti-models' in data:
            needs_update = True
        if 'ttv' in data:
            needs_update = True

        return needs_update
    
    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file"""
        if config:
            self._config = config
        
        if self._config is None:
            return

        self.ensure_dirs()

        target_path = self._loaded_config_path or self.config_path
        if self._is_workspace_candidate_path(target_path):
            self._use_workspace_config = True
            self.config_path = self.workspace_config_path
            target_path = self.workspace_config_path
        else:
            self._use_workspace_config = False
            self.config_path = self.global_config_path
            target_path = self.global_config_path

        # The manager decides the active destination. Store that resolved mode
        # in the file so the next process selects the same config again.
        self._config.use_workspace_config = self._use_workspace_config
        if is_config_version_older(self._config.config_version):
            self._config.config_version = CONFIG_VERSION
        serialized = self._config.to_dict()

        write_json_secure(target_path, serialized)
        self._loaded_config_path = target_path
        try:
            self._last_mtime = os.path.getmtime(target_path)
        except OSError:
            self._last_mtime = 0
        if not self._is_workspace_candidate_path(target_path):
            self._sync_legacy_mirror(serialized)
    
    def is_configured(self) -> bool:
        """Check if initial configuration is done"""
        config = self.load()
        # Considered configured if there is at least one model
        # The active_model can be auto-selected if invalid.
        if len(config.models) > 0:
            return True

        if normalize_codex_config(getattr(config, "codex", {})).get("selected_model_id"):
            return True
        if build_aihubmix_runtime_model_data(getattr(config, "aihubmix", {})):
            return True
        if build_agnes_runtime_model_data(getattr(config, "agnes", {})):
            return True
        if build_sensenova_runtime_model_data(getattr(config, "sensenova", {})):
            return True
        if build_unlimitedsurf_runtime_model_data(getattr(config, "unlimitedsurf", {})):
            return True
        if build_modelscope_runtime_model_data(getattr(config, "modelscope", {})):
            return True
        nvidia = normalize_nvidia_config(getattr(config, "nvidia", {}))
        if normalize_mode(getattr(config, "mode", "reverie")) == "computer-controller":
            if build_nvidia_computer_controller_runtime_model_data(nvidia):
                return True
        elif build_nvidia_runtime_model_data(nvidia):
            return True
        if build_webgemini_runtime_model_data(getattr(config, "webgemini", {})):
            return True
        if build_opencode_runtime_model_data(getattr(config, "opencode", {})):
            return True
        return False
    
    def add_model(self, model_config: ModelConfig) -> None:
        """Add a new model configuration"""
        config = self.load()
        config.models.append(model_config)
        self.save(config)
    
    def remove_model(self, index: int) -> bool:
        """Remove a model configuration by index"""
        config = self.load()
        if 0 <= index < len(config.models):
            config.models.pop(index)
            # Adjust active index if needed
            if config.active_model_index >= len(config.models):
                config.active_model_index = max(0, len(config.models) - 1)
            # If standard models are empty but another external source is selected, keep that source active.
            if not config.models and config.active_model_source == "standard":
                if normalize_codex_config(getattr(config, "codex", {})).get("selected_model_id"):
                    config.active_model_source = "codex"
                elif build_aihubmix_runtime_model_data(getattr(config, "aihubmix", {})):
                    config.active_model_source = "aihubmix"
                elif build_agnes_runtime_model_data(getattr(config, "agnes", {})):
                    config.active_model_source = "agnes"
                elif build_sensenova_runtime_model_data(getattr(config, "sensenova", {})):
                    config.active_model_source = "sensenova"
                elif build_unlimitedsurf_runtime_model_data(getattr(config, "unlimitedsurf", {})):
                    config.active_model_source = "unlimitedsurf"
                elif build_nvidia_runtime_model_data(getattr(config, "nvidia", {})):
                    config.active_model_source = "nvidia"
                elif build_modelscope_runtime_model_data(getattr(config, "modelscope", {})):
                    config.active_model_source = "modelscope"
                elif build_webgemini_runtime_model_data(getattr(config, "webgemini", {})):
                    config.active_model_source = "webgemini"
                elif build_opencode_runtime_model_data(getattr(config, "opencode", {})):
                    config.active_model_source = "opencode"
            self.save(config)
            return True
        return False
    
    def set_active_model(self, index: int) -> bool:
        """Set the active model by index"""
        config = self.load()
        if 0 <= index < len(config.models):
            config.active_model_index = index
            config.active_model_source = "standard"
            self.save(config)
            return True
        return False
    
    def get_active_model(self) -> Optional[ModelConfig]:
        """Get the currently active model"""
        config = self.load()
        return config.active_model

