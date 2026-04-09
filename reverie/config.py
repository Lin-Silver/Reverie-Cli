"""
Configuration Management

Handles loading and saving configuration including:
- API settings (base_url, api_key, model)
- Model presets
- User preferences
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import os
import sys
import hashlib
import re
import shutil
import logging

from .security_utils import write_json_secure
from .geminicli import (
    build_geminicli_runtime_model_data,
    default_geminicli_config,
    normalize_geminicli_config,
)
from .codex import (
    build_codex_runtime_model_data,
    default_codex_config,
    normalize_codex_config,
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
from .web import (
    build_web_runtime_model_data,
    default_web_config,
    normalize_web_config,
    resolve_web_image_model,
)
from .modes import normalize_mode
from .version import CONFIG_VERSION, __version__

EXTERNAL_MODEL_SOURCES = ("qwencode", "geminicli", "codex", "nvidia", "web")
SUPPORTED_ACTIVE_MODEL_SOURCES = ("standard",) + EXTERNAL_MODEL_SOURCES
SUPPORTED_TOOL_OUTPUT_STYLES = ("compact", "condensed", "full")
SUPPORTED_THINKING_OUTPUT_STYLES = ("hidden", "compact", "full")
SUPPORTED_TTI_SOURCES = ("local", "web")


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
            pass

    try:
        source_root = Path(__file__).resolve().parent.parent
        if (source_root / 'reverie').exists():
            return source_root
    except Exception:
        pass

    return Path.cwd()


def get_launcher_root() -> Path:
    """Return the directory that physically launched Reverie."""
    return _resolve_runner_root()


def default_text_to_image_config() -> Dict[str, Any]:
    """Default configuration for text-to-image generation."""
    return {
        "enabled": True,
        "python_executable": "",
        "script_path": "Comfy/generate_image.py",
        "output_dir": ".",
        "active_source": "local",
        "models": [],
        "default_model_display_name": "",
        "web_default_model_id": "",
        "web_default_model_display_name": "",
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
        "supported_engines": ["reverie_engine", "reverie_engine_lite", "custom", "web", "pygame", "love2d", "cocos2d", "godot", "unity", "unreal"],
        "supported_frameworks": [
            "reverie_engine", "reverie_engine_lite", "phaser", "pixijs", "threejs", "pygame", "love2d", "cocos2d", "godot", "unity", "unreal"
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
        "ashfox_server_name": "ashfox",
        "ashfox_endpoint": "http://127.0.0.1:8787/mcp",
        "proactive_mode_switching": True,
        "mandatory_verification_loop": True,
        "playtest_iteration_enabled": True,
        "max_asset_context_window": 10,
        "context_compression_enabled": True,
    }


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


def normalize_tti_models(raw_models: Any, legacy_model_paths: Any = None) -> List[Dict[str, str]]:
    """
    Normalize TTI model configuration into:
    [{"path": "...", "display_name": "...", "introduction": "..."}]
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

        models.append(
            {
                "path": path_value,
                "display_name": display_name,
                "introduction": introduction,
            }
        )

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


def get_app_root() -> Path:
    """
    Get the application root directory.

    Runtime data is stored relative to the physical executable or script entry
    point so packaged builds keep their cache beside the executable, while
    development runs keep their cache beside the source checkout / launcher.
    """
    return get_launcher_root()


def get_computer_controller_data_dir(app_root: Optional[Path] = None) -> Path:
    """Return the dedicated runtime data root for Computer Controller mode."""
    root = Path(app_root).resolve() if app_root is not None else get_app_root()
    return root / ".reverie" / "computer-controller"


def get_legacy_project_data_name(project_path: Path) -> str:
    """
    Generate the legacy project cache folder name.

    This format is human-readable but not collision-safe because path separators
    and literal underscores can normalize to the same value.
    """
    full_path = str(project_path.resolve())
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', full_path)
    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
    return safe_name


def get_project_data_name(project_path: Path) -> str:
    """
    Generate a collision-resistant folder name for a project based on its path.
    """
    full_path = str(project_path.resolve())
    safe_name = get_legacy_project_data_name(project_path)
    path_hash = hashlib.sha1(full_path.encode('utf-8')).hexdigest()[:12]

    if safe_name:
        return f"{safe_name}_{path_hash}"
    return path_hash


def get_project_data_dir(project_path: Path) -> Path:
    """
    Get the project-specific data directory.

    Creates a unique folder under the app's `.reverie/project_caches/`
    directory.
    """
    app_root = get_app_root()
    projects_dir = app_root / '.reverie' / 'project_caches'
    
    # Create unique folder name for this project
    project_name = get_project_data_name(project_path)
    project_data = projects_dir / project_name
    
    return project_data


@dataclass
class ModelConfig:
    """Configuration for a single model"""
    model: str
    model_display_name: str
    base_url: str
    api_key: str = ""
    max_context_tokens: Optional[int] = None
    provider: str = "openai-sdk"  # Options: openai-sdk, request, anthropic
    thinking_mode: Optional[str] = None  # For request provider: true, false, or None
    endpoint: str = ""  # Optional custom endpoint path/url for OpenAI-compatible providers
    custom_headers: Dict[str, str] = field(default_factory=dict)  # Optional request headers
    
    def to_dict(self) -> dict:
        return asdict(self)
    
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
            provider=data.get('provider', 'openai-sdk'),
            thinking_mode=data.get('thinking_mode'),
            endpoint=str(data.get('endpoint', '') or '').strip(),
            custom_headers=custom_headers
        )


@dataclass
class Config:
    """Main configuration"""
    models: List[ModelConfig] = field(default_factory=list)
    active_model_index: int = 0
    active_model_source: str = "standard"  # standard | qwencode | geminicli | codex | nvidia | web
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
    
    # API call settings for improved stability
    api_max_retries: int = 3
    api_initial_backoff: float = 1.0
    api_timeout: int = 60
    api_enable_debug_logging: bool = False
    
    # Text-to-image settings
    text_to_image: Dict[str, Any] = field(default_factory=default_text_to_image_config)
    qwencode: Dict[str, Any] = field(default_factory=dict)
    geminicli: Dict[str, Any] = field(default_factory=dict)
    codex: Dict[str, Any] = field(default_factory=dict)
    nvidia: Dict[str, Any] = field(default_factory=default_nvidia_config)
    web: Dict[str, Any] = field(default_factory=default_web_config)
    atlas_mode: Dict[str, Any] = field(default_factory=default_atlas_mode_config)
    
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

        if source == "qwencode":
            from .qwencode import build_qwencode_runtime_model_data
            runtime_qwencode_model = build_qwencode_runtime_model_data(self.qwencode)
            if runtime_qwencode_model:
                return ModelConfig.from_dict(runtime_qwencode_model)

        if source == "geminicli":
            runtime_geminicli_model = build_geminicli_runtime_model_data(self.geminicli)
            if runtime_geminicli_model:
                return ModelConfig.from_dict(runtime_geminicli_model)

        if source == "codex":
            runtime_codex_model = build_codex_runtime_model_data(self.codex)
            if runtime_codex_model:
                return ModelConfig.from_dict(runtime_codex_model)

        if source == "nvidia":
            runtime_nvidia_model = build_nvidia_runtime_model_data(runtime_nvidia_config)
            if runtime_nvidia_model:
                return ModelConfig.from_dict(runtime_nvidia_model)

        if source == "web":
            runtime_web_model = build_web_runtime_model_data(self.web)
            if runtime_web_model:
                return ModelConfig.from_dict(runtime_web_model)

        if 0 <= self.active_model_index < len(self.models):
            return self.models[self.active_model_index]
        return None
    
    def to_dict(self) -> dict:
        text_to_image = dict(self.text_to_image) if isinstance(self.text_to_image, dict) else default_text_to_image_config()
        text_to_image['active_source'] = normalize_tti_source(text_to_image.get('active_source', 'local'))
        text_to_image['models'] = normalize_tti_models(
            text_to_image.get('models', []),
            legacy_model_paths=text_to_image.get('model_paths', [])
        )
        text_to_image['default_model_display_name'] = resolve_tti_default_display_name(text_to_image)
        text_to_image['web_default_model_id'] = str(text_to_image.get('web_default_model_id', '') or '').strip()
        text_to_image['web_default_model_display_name'] = str(text_to_image.get('web_default_model_display_name', '') or '').strip()
        text_to_image.pop('model_paths', None)
        text_to_image.pop('default_model_index', None)
        tti_models = text_to_image['models']
        from .qwencode import normalize_qwencode_config
        qwencode = normalize_qwencode_config(self.qwencode)
        geminicli = normalize_geminicli_config(self.geminicli)
        codex = normalize_codex_config(self.codex)
        nvidia = normalize_nvidia_config(self.nvidia)
        web = normalize_web_config(self.web)
        atlas_mode = normalize_atlas_mode_config(self.atlas_mode)
        selected_web_image = resolve_web_image_model(web, text_to_image)
        if selected_web_image:
            text_to_image['web_default_model_id'] = selected_web_image['id']
            text_to_image['web_default_model_display_name'] = selected_web_image['display_name']
        active_model_source = self.active_model_source.lower()
        if active_model_source not in SUPPORTED_ACTIVE_MODEL_SOURCES:
            active_model_source = "standard"

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
            'api_max_retries': self.api_max_retries,
            'api_initial_backoff': self.api_initial_backoff,
            'api_timeout': self.api_timeout,
            'api_enable_debug_logging': self.api_enable_debug_logging,
            'text_to_image': text_to_image,
            'qwencode': qwencode,
            'geminicli': geminicli,
            'codex': codex,
            'nvidia': nvidia,
            'web': web,
            'atlas_mode': atlas_mode,
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
        top_level_tti_models = data.get('tti-models', None)
        if top_level_tti_models is not None:
            text_to_image['models'] = top_level_tti_models
        text_to_image['models'] = normalize_tti_models(
            text_to_image.get('models', []),
            legacy_model_paths=text_to_image.get('model_paths', [])
        )
        text_to_image['active_source'] = normalize_tti_source(text_to_image.get('active_source', 'local'))
        text_to_image['default_model_display_name'] = resolve_tti_default_display_name(text_to_image)
        text_to_image['web_default_model_id'] = str(text_to_image.get('web_default_model_id', '') or '').strip()
        text_to_image['web_default_model_display_name'] = str(text_to_image.get('web_default_model_display_name', '') or '').strip()
        text_to_image.pop('model_paths', None)
        text_to_image.pop('default_model_index', None)
        raw_qwencode = data.get('qwencode', {})
        from .qwencode import normalize_qwencode_config
        qwencode = normalize_qwencode_config(raw_qwencode)
        raw_geminicli = data.get('geminicli', {})
        geminicli = normalize_geminicli_config(raw_geminicli)
        raw_codex = data.get('codex', {})
        codex = normalize_codex_config(raw_codex)
        raw_nvidia = data.get('nvidia', {})
        nvidia = normalize_nvidia_config(raw_nvidia)
        raw_web = data.get('web', {})
        web = normalize_web_config(raw_web)
        raw_atlas_mode = data.get('atlas_mode', {})
        atlas_mode = normalize_atlas_mode_config(raw_atlas_mode)
        selected_web_image = resolve_web_image_model(web, text_to_image)
        if selected_web_image:
            text_to_image['web_default_model_id'] = selected_web_image['id']
            text_to_image['web_default_model_display_name'] = selected_web_image['display_name']
        active_model_source = str(data.get('active_model_source', 'standard')).strip().lower()
        if active_model_source not in SUPPORTED_ACTIVE_MODEL_SOURCES:
            active_model_source = 'standard'

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
            api_max_retries=data.get('api_max_retries', 3),
            api_initial_backoff=data.get('api_initial_backoff', 1.0),
            api_timeout=data.get('api_timeout', 60),
            api_enable_debug_logging=data.get('api_enable_debug_logging', False),
            text_to_image=text_to_image,
            qwencode=qwencode,
            geminicli=geminicli,
            codex=codex,
            nvidia=nvidia,
            web=web,
            atlas_mode=atlas_mode,
        )


class ConfigManager:
    """
    Manages configuration persistence with workspace isolation support.

    Configuration can be stored in two modes:
    1. Active/global profile: config.json in
       .reverie/
    2. Workspace profile: config.json in
       .reverie/project_caches/[project_key]/

    Legacy per-project `config.global.json` files are still read for migration,
    but default writes now target the shared `.reverie/config.json` profile
    unless workspace mode is explicitly enabled for the current project.
    """
    
    def __init__(self, project_root: Path, force_workspace_config: bool = False):
        self.project_root = project_root
        self._logger = logging.getLogger(__name__)

        # Use app root for runtime data (next to exe file or script directory).
        self.app_root = get_app_root()
        self.data_root = self.app_root / '.reverie' / 'project_caches'
        self.project_data_dir = get_project_data_dir(project_root)
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

    def _get_legacy_mirror_path(self) -> Path:
        """Return the compatibility config path for the current storage mode."""
        if self._use_workspace_config:
            return self.legacy_workspace_config_path
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
        if workspace_found and not any(path.exists() for path in self._path_candidates_for_mode(False)):
            return True
        return False

    def _sync_legacy_mirror(self, serialized: Dict[str, Any]) -> None:
        """Best-effort compatibility sync for older launchers and visible legacy files."""
        legacy_path = self._get_legacy_mirror_path()
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

        workspace_records = [record for record in records if record.get("workspace_mode")]
        if workspace_records:
            return max(workspace_records, key=_rank)

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
            return [self.workspace_config_path, self.legacy_workspace_config_path]
        return [
            self.global_config_path,
            self.legacy_global_config_path,
            self.legacy_project_global_config_path,
        ]

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
        # Runtime data directories live under the executable's
        # `.reverie/project_caches` root.
        self.data_root.mkdir(parents=True, exist_ok=True)

        # Project-specific data directories (for context cache, etc.)
        self.project_data_dir.mkdir(parents=True, exist_ok=True)
        (self.project_data_dir / 'context_cache').mkdir(exist_ok=True)
        (self.project_data_dir / 'specs').mkdir(exist_ok=True)
        (self.project_data_dir / 'steering').mkdir(exist_ok=True)
        (self.project_data_dir / 'sessions').mkdir(exist_ok=True)
        (self.project_data_dir / 'archives').mkdir(exist_ok=True)
        (self.project_data_dir / 'checkpoints').mkdir(exist_ok=True)
    
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
        if current_version != CONFIG_VERSION:
            needs_update = True
        
        # Check if any model is missing provider field
        models = data.get('models', [])
        for model in models:
            if 'provider' not in model:
                needs_update = True
                break
        
        # Check if any model is missing thinking_mode field (for request provider)
        for model in models:
            if 'thinking_mode' not in model:
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
        active_model_source = str(data.get('active_model_source', '')).strip().lower()
        if active_model_source not in SUPPORTED_ACTIVE_MODEL_SOURCES:
            needs_update = True

        # Check if qwencode section is missing
        if 'qwencode' not in data:
            needs_update = True

        # Check if geminicli section is missing
        if 'geminicli' not in data:
            needs_update = True
        elif not isinstance(data.get('geminicli'), dict):
            needs_update = True
        else:
            for field_name in default_geminicli_config().keys():
                if field_name not in data.get('geminicli', {}):
                    needs_update = True
                    break

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

        # Check if web section is missing
        if 'web' not in data:
            needs_update = True
        elif not isinstance(data.get('web'), dict):
            needs_update = True
        else:
            for field_name in default_web_config().keys():
                if field_name not in data.get('web', {}):
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

        # Canonical config now stores TTI models only under text_to_image.models.
        if 'tti-models' in data:
            needs_update = True

        return needs_update
    
    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file"""
        if config:
            self._config = config
        
        if self._config is None:
            return

        # The manager decides the active destination. The config flag is stored
        # as metadata and must not redirect writes on its own.
        self._config.use_workspace_config = self._use_workspace_config
        
        self.ensure_dirs()

        serialized = self._config.to_dict()
        target_path = self._loaded_config_path or self.config_path
        if self._is_workspace_candidate_path(target_path):
            self._use_workspace_config = True
            self.config_path = self.workspace_config_path
        else:
            self._use_workspace_config = False
            self.config_path = self.global_config_path

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

        from .qwencode import normalize_qwencode_config
        if normalize_qwencode_config(getattr(config, "qwencode", {})).get("selected_model_id"):
            return True
        if normalize_geminicli_config(getattr(config, "geminicli", {})).get("selected_model_id"):
            return True
        if normalize_codex_config(getattr(config, "codex", {})).get("selected_model_id"):
            return True
        if normalize_web_config(getattr(config, "web", {})).get("selected_model_id"):
            return True
        nvidia = normalize_nvidia_config(getattr(config, "nvidia", {}))
        if normalize_mode(getattr(config, "mode", "reverie")) == "computer-controller":
            if build_nvidia_computer_controller_runtime_model_data(nvidia):
                return True
        elif build_nvidia_runtime_model_data(nvidia):
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
                from .qwencode import normalize_qwencode_config

                if normalize_qwencode_config(getattr(config, "qwencode", {})).get("selected_model_id"):
                    config.active_model_source = "qwencode"
                elif normalize_geminicli_config(getattr(config, "geminicli", {})).get("selected_model_id"):
                    config.active_model_source = "geminicli"
                elif normalize_codex_config(getattr(config, "codex", {})).get("selected_model_id"):
                    config.active_model_source = "codex"
                elif build_nvidia_runtime_model_data(getattr(config, "nvidia", {})):
                    config.active_model_source = "nvidia"
                elif normalize_web_config(getattr(config, "web", {})).get("selected_model_id"):
                    config.active_model_source = "web"
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

