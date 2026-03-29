from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json

from reverie.engine_lite.procedural_assets import create_primitive_model
from reverie.engine_lite.project import create_project_skeleton


def test_create_primitive_model_writes_runtime_preview_and_registry() -> None:
    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "primitive_project"
        create_project_skeleton(project_root, project_name="Primitive Test", dimension="3D", overwrite=True)

        result = create_primitive_model(project_root, "hero_crate", primitive="box", size=1.5, overwrite=True)

        runtime_path = Path(result["runtime_path"])
        preview_path = Path(result["preview_path"])
        registry_path = Path(result["registry"]["registry_path"])

        assert runtime_path.exists()
        assert preview_path.exists()
        assert registry_path.exists()

        gltf_payload = json.loads(runtime_path.read_text(encoding="utf-8"))
        assert gltf_payload["asset"]["version"] == "2.0"
        assert gltf_payload["meshes"][0]["primitives"][0]["mode"] == 4
        assert result["mesh_summary"]["triangle_count"] == 12

        registry_models = result["registry"]["registry"]["models"]
        assert any(model["name"] == "hero_crate" for model in registry_models)
