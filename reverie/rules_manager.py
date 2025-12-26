"""
Rules Manager

Handles loading and saving user-defined rules in .reverie/rules.json
"""

import json
from pathlib import Path
from typing import List

from .config import get_app_root

class RulesManager:
    """Manages user-defined rules stored in rules.json"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.app_root = get_app_root()
        self.reverie_dir = self.app_root / '.reverie'
        self.rules_path = self.reverie_dir / 'rules.json'
        self._rules: List[str] = []
        self._load()
    
    def _load(self) -> None:
        """Load rules from file"""
        if self.rules_path.exists():
            try:
                with open(self.rules_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._rules = [str(r) for r in data]
                    else:
                        self._rules = []
            except Exception:
                self._rules = []
        else:
            self._rules = []
            
    def save(self) -> None:
        """Save rules to file"""
        self.reverie_dir.mkdir(parents=True, exist_ok=True)
        with open(self.rules_path, 'w', encoding='utf-8') as f:
            json.dump(self._rules, f, indent=2, ensure_ascii=False)
            
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
