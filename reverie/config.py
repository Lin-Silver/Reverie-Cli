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
__version__ = "1.2.5"


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
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModelConfig':
        return cls(
            model=data.get('model', ''),
            model_display_name=data.get('model_display_name', data.get('model', '')),
            base_url=data.get('base_url', ''),
            api_key=data.get('api_key', ''),
            max_context_tokens=data.get('max_context_tokens')
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
            'auto_index': self.auto_index
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
            auto_index=data.get('auto_index', True)
        )


class ConfigManager:
    """
    Manages configuration persistence.
    
    Configuration is stored in the app root's .reverie folder (next to exe file).
    Project-specific data is stored in .reverie/project_caches/[project_path]/.
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        
        # Use app root for config (next to exe file or script directory)
        self.app_root = get_app_root()
        self.reverie_dir = self.app_root / '.reverie'
        self.config_path = self.reverie_dir / 'config.json'
        
        # Project-specific data directory
        self.project_data_dir = get_project_data_dir(project_root)
        
        self._config: Optional[Config] = None
        self._last_mtime: float = 0
    
    def ensure_dirs(self) -> None:
        """Create necessary directories"""
        # Main app directories
        self.reverie_dir.mkdir(exist_ok=True)
        (self.reverie_dir / 'project_caches').mkdir(exist_ok=True)
        
        # Project-specific directories
        self.project_data_dir.mkdir(parents=True, exist_ok=True)
        (self.project_data_dir / 'context_cache').mkdir(exist_ok=True)
        (self.project_data_dir / 'specs').mkdir(exist_ok=True)
        (self.project_data_dir / 'sessions').mkdir(exist_ok=True)
        (self.project_data_dir / 'archives').mkdir(exist_ok=True)
        (self.project_data_dir / 'checkpoints').mkdir(exist_ok=True)
    
    def load(self) -> Config:
        """Load configuration from file, reloading if file changed"""
        if self.config_path.exists():
            current_mtime = os.path.getmtime(self.config_path)
            # Reload if file changed or not loaded yet
            if self._config is None or current_mtime > self._last_mtime:
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._config = Config.from_dict(data)
                    self._last_mtime = current_mtime
                except Exception:
                    # If error reading (e.g., partial write), keep old config if available
                    if self._config is None:
                        self._config = Config()
        else:
            self._config = Config()
        
        return self._config
    
    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file"""
        if config:
            self._config = config
        
        if self._config is None:
            return
        
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
