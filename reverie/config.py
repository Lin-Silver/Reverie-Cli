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
import json
import os
import sys
import hashlib
import re
import shutil


# Version info
__version__ = "2.0.0"


def get_app_root() -> Path:
    """
    Get the application root directory.
    
    Strictly follows: wherever the physical executable or script entry point is,
    that is where the .reverie folder must be located.
    """
    # 1. Check if running as a compiled PyInstaller EXE
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    
    # 2. Identify the runner (the shim exe or the script)
    if sys.argv and sys.argv[0]:
        try:
            # os.path.abspath(sys.argv[0]) is the most direct way to find the file
            # that the OS actually executed (the binary shim or the script).
            exec_path = Path(os.path.abspath(sys.argv[0])).resolve()
            
            # If running via 'python -m reverie', it resolves to .../reverie/__main__.py
            if exec_path.name == '__main__.py':
                return exec_path.parent.parent
            
            # For reverie.exe (shim) or direct script, use its immediate parent directory.
            if exec_path.exists() and exec_path.is_file():
                return exec_path.parent
        except Exception:
            pass

    # 3. Development fallback (only if argv[0] is missing or invalid)
    try:
        source_root = Path(__file__).resolve().parent.parent
        if (source_root / 'reverie').exists():
            return source_root
    except Exception:
        pass
        
    # Ultimate fallback to current working directory
    return Path.cwd()


def get_project_data_name(project_path: Path) -> str:
    """
    Generate a unique folder name for a project based on its path.
    """
    full_path = str(project_path.resolve())
    # Replace invalid filesystem characters with underscores
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', full_path)
    # Collapse consecutive underscores for readability
    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
    return safe_name


def get_project_data_dir(project_path: Path) -> Path:
    """
    Get the project-specific data directory.
    
    Creates a unique folder under the app's .reverie/project_caches/ directory.
    """
    app_root = get_app_root()
    reverie_dir = app_root / '.reverie'
    projects_dir = reverie_dir / 'project_caches'
    
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
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModelConfig':
        return cls(
            model=data.get('model', ''),
            model_display_name=data.get('model_display_name', data.get('model', '')),
            base_url=data.get('base_url', ''),
            api_key=data.get('api_key', ''),
            max_context_tokens=data.get('max_context_tokens'),
            provider=data.get('provider', 'openai-sdk'),
            thinking_mode=data.get('thinking_mode')
        )


@dataclass
class Config:
    """Main configuration"""
    models: List[ModelConfig] = field(default_factory=list)
    active_model_index: int = 0
    mode: str = "reverie"
    theme: str = "default"
    max_context_tokens: int = 128000
    stream_responses: bool = True
    auto_index: bool = True
    show_status_line: bool = True
    config_version: str = "2.0.0"  # Config file version for migration
    
    # Workspace isolation settings
    use_workspace_config: bool = False  # If True, config is stored in workspace directory
    
    # API call settings for improved stability
    api_max_retries: int = 3
    api_initial_backoff: float = 1.0
    api_timeout: int = 60
    api_enable_debug_logging: bool = False
    
    # Writer mode specific settings
    writer_mode: Dict[str, Any] = field(default_factory=lambda: {
        "memory_system_enabled": True,
        "auto_consistency_check": True,
        "auto_character_tracking": True,
        "max_chapter_context_window": 5,
        "narrative_analysis_enabled": True,
        "emotion_tracking_enabled": True,
        "plot_tracking_enabled": True,
    })

    # Gamer mode specific settings
    gamer_mode: Dict[str, Any] = field(default_factory=lambda: {
        "target_engine": "custom",
        "supported_engines": ["custom", "web", "pygame", "love2d", "cocos2d"],
        "supported_frameworks": [
            "phaser", "pixijs", "threejs", "pygame", "love2d", "cocos2d"
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
        "max_asset_context_window": 10,
        "context_compression_enabled": True,
    })
    
    @property
    def active_model(self) -> Optional[ModelConfig]:
        if 0 <= self.active_model_index < len(self.models):
            return self.models[self.active_model_index]
        return None
    
    def to_dict(self) -> dict:
        return {
            'models': [m.to_dict() for m in self.models],
            'active_model_index': self.active_model_index,
            'mode': self.mode,
            'theme': self.theme,
            'max_context_tokens': self.max_context_tokens,
            'stream_responses': self.stream_responses,
            'auto_index': self.auto_index,
            'show_status_line': self.show_status_line,
            'writer_mode': self.writer_mode,
            'gamer_mode': self.gamer_mode,
            'config_version': self.config_version,
            'use_workspace_config': self.use_workspace_config,
            'api_max_retries': self.api_max_retries,
            'api_initial_backoff': self.api_initial_backoff,
            'api_timeout': self.api_timeout,
            'api_enable_debug_logging': self.api_enable_debug_logging,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        models = [
            ModelConfig.from_dict(m) 
            for m in data.get('models', [])
        ]
        return cls(
            models=models,
            active_model_index=data.get('active_model_index', 0),
            mode=data.get('mode', 'reverie'),
            theme=data.get('theme', 'default'),
            max_context_tokens=data.get('max_context_tokens', 128000),
            stream_responses=data.get('stream_responses', True),
            auto_index=data.get('auto_index', True),
            show_status_line=data.get('show_status_line', True),
            writer_mode=data.get('writer_mode', {
                "memory_system_enabled": True,
                "auto_consistency_check": True,
                "auto_character_tracking": True,
                "max_chapter_context_window": 5,
                "narrative_analysis_enabled": True,
                "emotion_tracking_enabled": True,
                "plot_tracking_enabled": True,
            }),
            gamer_mode=data.get('gamer_mode', {
                "target_engine": "custom",
                "supported_engines": ["custom", "web", "pygame", "love2d", "cocos2d"],
                "supported_frameworks": [
                    "phaser", "pixijs", "threejs", "pygame", "love2d", "cocos2d"
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
                "max_asset_context_window": 10,
                "context_compression_enabled": True,
            }),
            config_version=data.get('config_version', '2.0.0'),
            use_workspace_config=data.get('use_workspace_config', False),
            api_max_retries=data.get('api_max_retries', 3),
            api_initial_backoff=data.get('api_initial_backoff', 1.0),
            api_timeout=data.get('api_timeout', 60),
            api_enable_debug_logging=data.get('api_enable_debug_logging', False)
        )


class ConfigManager:
    """
    Manages configuration persistence with workspace isolation support.
    
    Configuration can be stored in two modes:
    1. Global mode: config.json in app_root/.reverie/ (shared across workspaces)
    2. Workspace mode: config.json in project_root/.reverie/ (isolated per workspace)
    
    Project-specific data is always stored in .reverie/project_caches/[project_path]/.
    """
    
    def __init__(self, project_root: Path, force_workspace_config: bool = False):
        self.project_root = project_root
        
        # Use app root for global config (next to exe file or script directory)
        self.app_root = get_app_root()
        self.reverie_dir = self.app_root / '.reverie'
        self.global_config_path = self.reverie_dir / 'config.json'
        
        # Workspace-specific config directory
        self.workspace_reverie_dir = self.project_root / '.reverie'
        self.workspace_config_path = self.workspace_reverie_dir / 'config.json'
        
        # Project-specific data directory (for context cache, etc.)
        self.project_data_dir = get_project_data_dir(project_root)
        
        self._config: Optional[Config] = None
        self._last_mtime: float = 0
        
        # Determine config path based on setting
        self._use_workspace_config = force_workspace_config
        self._update_config_path()
    
    def _update_config_path(self) -> None:
        """Update config path based on current mode"""
        if self._use_workspace_config:
            self.config_path = self.workspace_config_path
        else:
            self.config_path = self.global_config_path
    
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
    
    def is_workspace_mode(self) -> bool:
        """Check if workspace-local configuration mode is enabled"""
        return self._use_workspace_config
    
    def copy_config_to_workspace(self) -> bool:
        """
        Copy global configuration to workspace configuration.
        
        Returns:
            True if copy was successful, False otherwise
        """
        if not self.global_config_path.exists():
            return False
        
        try:
            # Load global config
            with open(self.global_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update to workspace mode
            data['use_workspace_config'] = True
            
            # Ensure workspace directory exists
            self.workspace_reverie_dir.mkdir(parents=True, exist_ok=True)
            
            # Save to workspace config
            with open(self.workspace_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Clear cache and switch to workspace mode
            self._config = None
            self._last_mtime = 0
            self.set_workspace_mode(True)
            
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to copy config to workspace: {e}")
            return False
    
    def copy_config_to_global(self) -> bool:
        """
        Copy workspace configuration to global configuration.
        
        Returns:
            True if copy was successful, False otherwise
        """
        if not self.workspace_config_path.exists():
            return False
        
        try:
            # Load workspace config
            with open(self.workspace_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update to global mode
            data['use_workspace_config'] = False
            
            # Ensure global directory exists
            self.reverie_dir.mkdir(parents=True, exist_ok=True)
            
            # Save to global config
            with open(self.global_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Clear cache and switch to global mode
            self._config = None
            self._last_mtime = 0
            self.set_workspace_mode(False)
            
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to copy config to global: {e}")
            return False
    
    def has_workspace_config(self) -> bool:
        """Check if workspace configuration file exists"""
        return self.workspace_config_path.exists()
    
    def has_global_config(self) -> bool:
        """Check if global configuration file exists"""
        return self.global_config_path.exists()
    
    def ensure_dirs(self) -> None:
        """Create necessary directories"""
        # Global app directories (always needed)
        self.reverie_dir.mkdir(exist_ok=True)
        (self.reverie_dir / 'project_caches').mkdir(exist_ok=True)
        
        # Workspace-specific directories (if using workspace mode)
        if self._use_workspace_config:
            self.workspace_reverie_dir.mkdir(parents=True, exist_ok=True)
        
        # Project-specific data directories (for context cache, etc.)
        self.project_data_dir.mkdir(parents=True, exist_ok=True)
        (self.project_data_dir / 'context_cache').mkdir(exist_ok=True)
        (self.project_data_dir / 'specs').mkdir(exist_ok=True)
        (self.project_data_dir / 'sessions').mkdir(exist_ok=True)
        (self.project_data_dir / 'archives').mkdir(exist_ok=True)
        (self.project_data_dir / 'checkpoints').mkdir(exist_ok=True)
    
    def load(self) -> Config:
        """Load configuration from file, reloading if file changed"""
        # Check if we need to switch config mode based on loaded config
        if self.config_path.exists():
            current_mtime = os.path.getmtime(self.config_path)
            # Reload if file changed or not loaded yet
            if self._config is None or current_mtime > self._last_mtime:
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._config = Config.from_dict(data)
                    self._last_mtime = current_mtime
                    
                    # Check if config mode changed
                    if self._config.use_workspace_config != self._use_workspace_config:
                        self.set_workspace_mode(self._config.use_workspace_config)
                    
                    # Auto-update config file if it's missing new fields
                    if self._needs_config_update(data):
                        self.save(self._config)
                        # Update mtime after saving to avoid infinite loop
                        self._last_mtime = os.path.getmtime(self.config_path)
                except Exception:
                    # If error reading (e.g., partial write), keep old config if available
                    if self._config is None:
                        self._config = Config()
        else:
            self._config = Config()
        
        return self._config
    
    def _needs_config_update(self, data: dict) -> bool:
        """Check if the loaded config needs to be updated with new fields"""
        needs_update = False
        
        # Check if config_version is missing or outdated
        current_version = data.get('config_version', '0.0.0')
        if current_version != '2.0.0':
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

        # Check if gamer_mode field is missing
        if 'gamer_mode' not in data:
            needs_update = True
        
        return needs_update
    
    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file"""
        if config:
            self._config = config
        
        if self._config is None:
            return
        
        # Update config mode if it changed
        if self._config.use_workspace_config != self._use_workspace_config:
            self.set_workspace_mode(self._config.use_workspace_config)
        
        self.ensure_dirs()
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config.to_dict(), f, indent=2, ensure_ascii=False)
    
    def is_configured(self) -> bool:
        """Check if initial configuration is done"""
        config = self.load()
        # Considered configured if there is at least one model
        # The active_model can be auto-selected if invalid
        return len(config.models) > 0
    
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
            self.save(config)
            return True
        return False
    
    def set_active_model(self, index: int) -> bool:
        """Set the active model by index"""
        config = self.load()
        if 0 <= index < len(config.models):
            config.active_model_index = index
            self.save(config)
            return True
        return False
    
    def get_active_model(self) -> Optional[ModelConfig]:
        """Get the currently active model"""
        config = self.load()
        return config.active_model
