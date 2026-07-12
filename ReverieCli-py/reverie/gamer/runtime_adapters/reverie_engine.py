"""Built-in Reverie Engine adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ...engine import create_project_skeleton, run_project_smoke, supported_game_families, validate_project
from .base import BaseRuntimeAdapter, RuntimeAdapterProfile


class ReverieEngineRuntimeAdapter(BaseRuntimeAdapter):
    runtime_id = "reverie_engine"
    display_name = "Reverie Engine"
    external = False
    maturity = "production-slice"
    capability_tags = (
        "builtin",
        "unified-runtime",
        "rapid-prototype",
        "2d",
        "2.5d",
        "3d",
        "scene-generation",
        "component-entity-patterns",
        "data-driven-content",
        "gltf",
        "renpy-import",
        "godot-migration",
        "o3de-migration",
        "smoke",
        "validation",
    )
    template_support = tuple(item["id"] for item in supported_game_families())

    def detect(self, project_root: Path, app_root: Path | None = None) -> RuntimeAdapterProfile:
        return RuntimeAdapterProfile(
            id=self.runtime_id,
            display_name=self.display_name,
            available=True,
            can_scaffold=True,
            can_validate=True,
            external=self.external,
            maturity=self.maturity,
            source="built-in",
            version="builtin",
            capabilities=list(self.capability_tags),
            template_support=list(self.template_support),
            health="ready",
            notes=[
                "Canonical runtime for every new Reverie-Gamer project.",
                "Godot and O3DE remain architecture/migration references, not selectable runtimes.",
                "Production scope excludes AAA/3A and 3D open-world games.",
            ],
            paths={"project_root": str(Path(project_root).resolve())},
        )

    def recommend_template(self, game_request: Dict[str, Any]) -> str:
        experience = game_request.get("experience", {})
        creative = game_request.get("creative_target", {})
        dimension = str(experience.get("dimension", "3D"))
        genre = str(creative.get("primary_genre", "action_rpg")).strip().lower()
        if genre == "platformer" and dimension == "2D":
            return "2d_platformer"
        if genre == "action_rpg" and dimension == "2D":
            return "topdown_action"
        if genre == "adventure" and dimension == "2.5D":
            return "iso_adventure"
        if genre == "arena" and dimension == "3D":
            return "3d_arena"
        if genre == "galgame" and dimension == "2D":
            return "galgame"
        if genre == "tower_defense" and dimension == "2D":
            return "tower_defense"
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
        output_dir = Path(output_dir).resolve()
        experience = game_request.get("experience", {})
        creative = game_request.get("creative_target", {})
        sample_name = self.recommend_template(game_request)
        genre = str(creative.get("primary_genre", "action_rpg")).strip().lower() or "sandbox"
        seed = create_project_skeleton(
            output_dir,
            project_name=project_name,
            dimension=str(experience.get("dimension", "3D")),
            sample_name=sample_name or None,
            genre=genre,
            overwrite=overwrite,
        )
        return {
            "runtime": self.runtime_id,
            "runtime_root": str(output_dir),
            "template": sample_name or f"{genre}_foundation",
            "directories": seed.get("directories", []),
            "files": seed.get("files", []),
            "notes": ["Foundation materialized with Reverie Engine starter content."],
        }

    def validate_project(self, output_dir: Path) -> Dict[str, Any]:
        output_dir = Path(output_dir).resolve()
        validation = validate_project(output_dir)
        smoke = run_project_smoke(output_dir)
        return {
            "valid": bool(validation.get("valid", False)) and bool(smoke.get("success", False)),
            "validation": validation,
            "smoke": smoke,
            "project_root": str(output_dir),
        }
