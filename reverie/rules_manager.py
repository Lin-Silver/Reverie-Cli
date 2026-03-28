
"""Rule persistence helpers for workspace and legacy Reverie profiles."""

from pathlib import Path
from typing import List
import json
import logging

from .config import get_app_root, get_project_data_dir


logger = logging.getLogger(__name__)


class RulesManager:
    """Manages user-defined rules stored in rules.txt"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.app_root = get_app_root()
        self.project_data_dir = get_project_data_dir(project_root)
        self.rules_txt_path = self.project_data_dir / 'rules.txt'
        self.rules_json_path = self.project_data_dir / 'rules.json'  # For backward compatibility
        self.legacy_reverie_dir = self.app_root / '.reverie'
        self.legacy_rules_txt_path = self.legacy_reverie_dir / 'rules.txt'
        self.legacy_rules_json_path = self.legacy_reverie_dir / 'rules.json'
        self._rules: List[str] = []
        self._load()

    def _load_rules_text_file(self, path: Path) -> List[str]:
        """Read newline-delimited rules from a text file."""
        with open(path, 'r', encoding='utf-8') as handle:
            return [line.strip() for line in handle if line.strip()]

    def _load_rules_json_file(self, path: Path) -> List[str]:
        """Read the legacy JSON rule list format."""
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            return []
        return [str(rule) for rule in data if str(rule).strip()]
    
    def _load(self) -> None:
        """Load rules from file"""
        # Try to load from rules.txt first
        if self.rules_txt_path.exists():
            try:
                self._rules = self._load_rules_text_file(self.rules_txt_path)
            except Exception:
                logger.warning("Failed to load rules from %s", self.rules_txt_path, exc_info=True)
                self._rules = []
        elif self.legacy_rules_txt_path.exists():
            try:
                self._rules = self._load_rules_text_file(self.legacy_rules_txt_path)
                self.save()
            except Exception:
                logger.warning("Failed to migrate legacy rules from %s", self.legacy_rules_txt_path, exc_info=True)
                self._rules = []
        # Fallback to rules.json for backward compatibility
        elif self.rules_json_path.exists():
            try:
                self._rules = self._load_rules_json_file(self.rules_json_path)
                # Migrate to txt format
                self._migrate_to_txt()
            except Exception:
                logger.warning("Failed to load rules from %s", self.rules_json_path, exc_info=True)
                self._rules = []
        elif self.legacy_rules_json_path.exists():
            try:
                self._rules = self._load_rules_json_file(self.legacy_rules_json_path)
                self._migrate_to_txt()
            except Exception:
                logger.warning("Failed to migrate legacy rules from %s", self.legacy_rules_json_path, exc_info=True)
                self._rules = []
        else:
            self._rules = []
            # Create example rules.txt file
            self._create_example_file()
    
    def _migrate_to_txt(self) -> None:
        """Migrate from json to txt format"""
        try:
            self.save()
            # Optionally remove the old json file
            # self.rules_json_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to migrate rules into %s", self.rules_txt_path, exc_info=True)
    
    def _create_example_file(self) -> None:
        """Create example rules.txt file with comments"""
        try:
            self.project_data_dir.mkdir(parents=True, exist_ok=True)
            example_content = """# Reverie Custom Rules
# Each line is a separate rule that will be added to the system prompt
# Lines starting with # are comments and will be ignored
# Empty lines are also ignored

# Example rules (uncomment to use):
# Always use type hints in function definitions
# Follow PEP 8 style guidelines
# Write docstrings for all public functions
# Use async/await for I/O operations
# Add unit tests for new features
"""
            with open(self.rules_txt_path, 'w', encoding='utf-8') as f:
                f.write(example_content)
        except Exception:
            logger.warning("Failed to create example rules file at %s", self.rules_txt_path, exc_info=True)
            
    def save(self) -> None:
        """Save rules to txt file"""
        self.project_data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.rules_txt_path, 'w', encoding='utf-8') as f:
            for rule in self._rules:
                f.write(rule + '\n')
            
    def get_rules(self) -> List[str]:
        """Get all rules"""
        return self._rules.copy()
        
    def add_rule(self, rule: str) -> None:
        """Add a new rule"""
        if rule and rule not in self._rules:
            self._rules.append(rule)
            self.save()
            
    def remove_rule(self, index: int) -> bool:
        """Remove a rule by index"""
        if 0 <= index < len(self._rules):
            self._rules.pop(index)
            self.save()
            return True
        return False
        
    def get_rules_text(self) -> str:
        """Get rules formatted for the system prompt"""
        if not self._rules:
            return ""
        return "\n".join(self._rules)
    
    def load_from_file(self, file_path: Path) -> None:
        """Load rules from an external txt file"""
        try:
            external_rules = self._load_rules_text_file(file_path)
            if external_rules:
                self._rules = external_rules
                self.save()
        except Exception as exc:
            logger.warning("Failed to load external rules from %s", file_path, exc_info=True)
            raise RuntimeError(f"Failed to load rules from {file_path}: {exc}") from exc
