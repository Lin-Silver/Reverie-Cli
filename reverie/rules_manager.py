
from pathlib import Path
from typing import List
from .config import get_app_root


class RulesManager:
    """Manages user-defined rules stored in rules.txt"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.app_root = get_app_root()
        self.reverie_dir = self.app_root / '.reverie'
        self.rules_txt_path = self.reverie_dir / 'rules.txt'
        self.rules_json_path = self.reverie_dir / 'rules.json'  # For backward compatibility
        self._rules: List[str] = []
        self._load()
    
    def _load(self) -> None:
        """Load rules from file"""
        # Try to load from rules.txt first
        if self.rules_txt_path.exists():
            try:
                with open(self.rules_txt_path, 'r', encoding='utf-8') as f:
                    # Read all lines, strip whitespace, filter out empty lines
                    self._rules = [line.strip() for line in f.readlines() if line.strip()]
            except Exception:
                self._rules = []
        # Fallback to rules.json for backward compatibility
        elif self.rules_json_path.exists():
            try:
                import json
                with open(self.rules_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._rules = [str(r) for r in data]
                    else:
                        self._rules = []
                # Migrate to txt format
                self._migrate_to_txt()
            except Exception:
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
            pass
    
    def _create_example_file(self) -> None:
        """Create example rules.txt file with comments"""
        try:
            self.reverie_dir.mkdir(parents=True, exist_ok=True)
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
            pass
            
    def save(self) -> None:
        """Save rules to txt file"""
        self.reverie_dir.mkdir(parents=True, exist_ok=True)
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
            with open(file_path, 'r', encoding='utf-8') as f:
                external_rules = [line.strip() for line in f.readlines() if line.strip()]
                if external_rules:
                    self._rules = external_rules
                    self.save()
        except Exception as e:
            raise Exception(f"Failed to load rules from {file_path}: {str(e)}")
