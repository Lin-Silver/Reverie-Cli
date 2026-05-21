from __future__ import annotations

from pathlib import Path
import json

from reverie.tools.game_asset_manager import GameAssetManagerTool
from reverie.tools.game_modeling_workbench import GameModelingWorkbenchTool
from reverie.tools.text_to_image import TextToImageTool


def test_game_modeling_workbench_headless_bbmodel_export(tmp_path: Path) -> None:
    tool = GameModelingWorkbenchTool({"project_root": tmp_path})
    source = tmp_path / "assets" / "models" / "source" / "hero_block.bbmodel"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        json.dumps(
            {
                "meta": {"format_version": "5.0", "model_format": "free"},
                "name": "Hero Block",
                "elements": [{"name": "body", "from": [4, 0, 4], "to": [12, 16, 12]}],
                "outliner": [],
                "textures": [],
                "animations": [],
            }
        ),
        encoding="utf-8",
    )

    validation = tool.execute(action="validate_blockbench_model", bbmodel_path=str(source.relative_to(tmp_path)))
    exported = tool.execute(
        action="export_blockbench_model",
        bbmodel_path=str(source.relative_to(tmp_path)),
        dest_name="hero_block",
        overwrite=True,
    )

    assert validation.success is True
    assert exported.success is True
    assert (tmp_path / "assets" / "models" / "runtime" / "hero_block.gltf").exists()
    assert exported.data["exporter"] == "reverie_headless_bbmodel_exporter"


def test_game_asset_manager_atlas_uses_real_png_dimensions_without_placeholder_fallback(tmp_path: Path) -> None:
    sprites = tmp_path / "assets" / "sprites"
    sprites.mkdir(parents=True)
    png = sprites / "hero.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + (128).to_bytes(4, "big")
        + (32).to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )

    tool = GameAssetManagerTool({"project_root": tmp_path})
    result = tool.execute(action="build_atlas_plan", asset_dir="assets", atlas_max_size=256)

    assert result.success is True
    sprite = result.data["atlases"][0]["sprites"][0]
    assert sprite["width"] == 128
    assert sprite["height"] == 32
    assert sprite["area"] == 4096
    assert sprite["dimension_source"] in {"pillow", "png_header"}
    assert result.data["unmeasured_sprites"] == []


def test_game_asset_manager_atlas_reports_unmeasured_images_instead_of_64_fallback(tmp_path: Path) -> None:
    sprites = tmp_path / "assets" / "sprites"
    sprites.mkdir(parents=True)
    (sprites / "broken.png").write_bytes(b"not an image")

    tool = GameAssetManagerTool({"project_root": tmp_path})
    result = tool.execute(action="build_atlas_plan", asset_dir="assets", atlas_max_size=256)

    assert result.success is False
    assert "No measurable sprites" in (result.error or "")


def test_text_to_image_diagnose_reports_local_runtime_readiness(tmp_path: Path) -> None:
    tool = TextToImageTool({"project_root": tmp_path})

    result = tool.execute(action="diagnose")

    assert result.status.value == "partial"
    assert result.data["ready"] is False
    assert any(check["id"] == "models" for check in result.data["checks"])


def test_text_to_image_gguf_model_metadata_tracks_auxiliary_models(tmp_path: Path) -> None:
    model = tmp_path / "ernie-image-turbo-Q4_K_S.gguf"
    clip = tmp_path / "models" / "text_encoders" / "ministral-3-3b.safetensors"
    vae = tmp_path / "models" / "vae" / "flux2-vae.safetensors"
    model.write_bytes(b"GGUF")
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"clip")

    tool = TextToImageTool({"project_root": tmp_path})
    entry = {
        "path": str(model),
        "display_name": "ernie-turbo-gguf",
        "format": "gguf",
        "clip_model": str(clip),
        "vae_model": str(vae),
        "recommended_steps": 8,
        "recommended_cfg": 1.0,
    }

    assert tool._infer_model_format(entry, model) == "gguf"
    aux = tool._summarize_auxiliary_models(entry)
    assert aux[0]["kind"] == "clip"
    assert aux[0]["exists"] is True
    assert aux[1]["kind"] == "vae"
    assert aux[1]["exists"] is False

    args = tool._build_auxiliary_model_args(entry)
    assert "--clip-model" in args
    assert "--vae-model" in args


def test_text_to_image_folder_model_package_auto_detects_ernie_files(tmp_path: Path) -> None:
    package = tmp_path / "ernie-image"
    package.mkdir()
    (package / "ernie-image-turbo-Q4_K_S.gguf").write_bytes(b"GGUF")
    (package / "ministral-3-3b.safetensors").write_bytes(b"clip")
    (package / "flux2-vae.safetensors").write_bytes(b"vae")

    tool = TextToImageTool({"project_root": tmp_path})
    entry = {
        "path": str(package),
        "display_name": "ernie-folder",
        "format": "auto",
    }

    resolved = tool._resolve_model_package(entry)

    assert resolved["format"] == "gguf"
    assert resolved["model_path"] == package / "ernie-image-turbo-Q4_K_S.gguf"
    assert resolved["auxiliary"]["clip"] == package / "ministral-3-3b.safetensors"
    assert resolved["auxiliary"]["vae"] == package / "flux2-vae.safetensors"


def test_text_to_image_folder_model_package_auto_detects_standard_subfolders(tmp_path: Path) -> None:
    package = tmp_path / "ernie-image"
    (package / "text_encoders").mkdir(parents=True)
    (package / "vae").mkdir()
    (package / "ernie-image-turbo-Q4_K_S.gguf").write_bytes(b"GGUF")
    (package / "text_encoders" / "ministral-3-3b.safetensors").write_bytes(b"clip")
    (package / "vae" / "flux2-vae.safetensors").write_bytes(b"vae")

    tool = TextToImageTool({"project_root": tmp_path})
    entry = {
        "path": str(package),
        "display_name": "ernie-folder",
        "format": "auto",
    }

    resolved = tool._resolve_model_package(entry)
    args = tool._build_auxiliary_model_args(entry, model_package=resolved)

    assert resolved["format"] == "gguf"
    assert resolved["model_path"] == package / "ernie-image-turbo-Q4_K_S.gguf"
    assert resolved["auxiliary"]["clip"] == package / "text_encoders" / "ministral-3-3b.safetensors"
    assert resolved["auxiliary"]["vae"] == package / "vae" / "flux2-vae.safetensors"
    assert args == [
        "--clip-model",
        str(package / "text_encoders" / "ministral-3-3b.safetensors"),
        "--vae-model",
        str(package / "vae" / "flux2-vae.safetensors"),
    ]


def test_text_to_image_prepare_models_reports_app_local_depot(tmp_path: Path, monkeypatch) -> None:
    app_root = tmp_path / "app"
    monkeypatch.setattr("reverie.tools.text_to_image.get_app_root", lambda: app_root)
    tool = TextToImageTool({"project_root": tmp_path})

    result = tool.execute(action="prepare_models", package="ernie-image-turbo-gguf", download=False)

    assert result.status.value == "partial"
    assert result.data["root"] == str(app_root / ".reverie" / "plugins" / "Packages" / "comfyui" / "models")
    assert result.data["required_ready"] is False
    assert all(str(app_root) in item["target"] for item in result.data["files"])
