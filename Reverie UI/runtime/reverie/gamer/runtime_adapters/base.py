"""Base runtime adapter interfaces for Reverie-Gamer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class RuntimeProfile:
    """Serializable runtime capability profile."""

    id: str
    display_name: str
    available: bool
    can_scaffold: bool
    can_validate: bool
    external: bool
    maturity: str
    source: str
    version: str = ""
    capabilities: List[str] = field(default_factory=list)
    template_support: List[str] = field(default_factory=list)
    health: str = "ok"
    notes: List[str] = field(default_factory=list)
    paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "available": self.available,
            "can_scaffold": self.can_scaffold,
            "can_validate": self.can_validate,
            "external": self.external,
            "maturity": self.maturity,
            "source": self.source,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "template_support": list(self.template_support),
            "health": self.health,
            "notes": list(self.notes),
            "paths": dict(self.paths),
        }


class BaseRuntimeAdapter:
    """Common runtime adapter contract."""

    runtime_id = "runtime"
    display_name = "Runtime"
    external = False
    maturity = "prototype"
    capability_tags: tuple[str, ...] = ()
    template_support: tuple[str, ...] = ()

    def detect(self, project_root: Path, app_root: Path | None = None) -> RuntimeProfile:
        raise NotImplementedError

    def recommend_template(self, game_request: Dict[str, Any]) -> str:
        return ""

    def create_project(
        self,
        output_dir: Path,
        *,
        project_name: str,
        game_request: Dict[str, Any],
        blueprint: Dict[str, Any],
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def validate_project(self, output_dir: Path) -> Dict[str, Any]:
        return {
            "valid": True,
            "checks": [],
            "warnings": [],
            "notes": ["validation is adapter-defined and may require runtime-native tooling"],
            "project_root": str(Path(output_dir)),
        }
