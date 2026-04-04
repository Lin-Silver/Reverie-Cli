"""Built-in Reverie Engine adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ...engine import create_project_skeleton, run_project_smoke, validate_project
from .base import BaseRuntimeAdapter, RuntimeProfile


class ReverieEngineRuntimeAdapter(BaseRuntimeAdapter):
    runtime_id = "reverie_engine"
    display_name = "Reverie Engine"
    external = False
    maturity = "production-slice"
    capability_tags = (
        "builtin",
        "rapid-prototype",
        "3d",
        "scene-generation",
        "smoke",
        "validation",
    )
    template_support = (
        "2d_platformer",
        "topdown_action",
        "iso_adventure",
        "3d_third_person",
        "galgame",
        "tower_defense",
    )

    def detect(self, project_root: Path, app_root: Path | None = None) -> RuntimeProfile:
        return RuntimeProfile(
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
            notes=["Best default for fast prompt-to-playable slices inside the current repository."],
            paths={"project_root": str(Path(project_root).resolve())},
        )

    def recommend_template(self, game_request: Dict[str, Any]) -> str:
        experience = game_request.get("experience", {})
        creative = game_request.get("creative_target", {})
        dimension = str(experience.get("dimension", "3D"))
        genre = str(creative.get("primary_genre", "action_rpg"))
        if dimension == "3D":
            return "3d_third_person"
        if dimension == "2.5D":
            return "iso_adventure"
        if genre == "platformer":
            return "2d_platformer"
        return "topdown_action"

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
        seed = create_project_skeleton(
            output_dir,
            project_name=project_name,
            dimension=str(experience.get("dimension", "3D")),
            sample_name=sample_name,
            genre=str(creative.get("primary_genre", "action_rpg")),
            overwrite=overwrite,
        )
        return {
            "runtime": self.runtime_id,
            "runtime_root": str(output_dir),
            "template": sample_name,
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
