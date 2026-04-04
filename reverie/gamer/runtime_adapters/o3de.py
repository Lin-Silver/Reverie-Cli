"""Experimental O3DE adapter metadata for future large-scale runtime work."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from .base import BaseRuntimeAdapter, RuntimeProfile


class O3DERuntimeAdapter(BaseRuntimeAdapter):
    runtime_id = "o3de"
    display_name = "O3DE"
    external = True
    maturity = "experimental"
    capability_tags = (
        "external-runtime",
        "large-scale-3d",
        "streaming",
        "data-heavy",
    )
    template_support = ("future-large-world",)

    def detect(self, project_root: Path, app_root: Path | None = None) -> RuntimeProfile:
        references_root = (Path(app_root or project_root) / "references" / "o3de").resolve()
        return RuntimeProfile(
            id=self.runtime_id,
            display_name=self.display_name,
            available=references_root.exists(),
            can_scaffold=False,
            can_validate=False,
            external=self.external,
            maturity=self.maturity,
            source="references" if references_root.exists() else "not-configured",
            version="",
            capabilities=list(self.capability_tags),
            template_support=list(self.template_support),
            health="research-only",
            notes=[
                "Kept in the registry for future-scale 3D production planning.",
                "Not used as the default slice runtime until repository-native scaffolding is implemented.",
            ],
            paths={"references_root": str(references_root)},
        )

    def create_project(
        self,
        output_dir: Path,
        *,
        project_name: str,
        game_request: Dict[str, Any],
        blueprint: Dict[str, Any],
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        raise NotImplementedError("O3DE scaffolding is not implemented yet.")
