from __future__ import annotations

import base64
from pathlib import Path
import json
from types import SimpleNamespace

from reverie.agnes_tti_profiles import agnes_image_21_flash
from reverie.aihubmix_tti_profiles import gemini_31_flash_image_preview_free, gpt_image_2_free
from reverie.pollinations_tti_profiles import flux
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


def test_text_to_image_lists_aihubmix_models(tmp_path: Path) -> None:
    tool = TextToImageTool({"project_root": tmp_path})

    result = tool.execute(action="list_models", source="aihubmix")

    assert result.success is True
    ids = {item["id"] for item in result.data["models"]}
    assert {"gpt-image-2-free", "gemini-3.1-flash-image-preview-free"} <= ids


def test_text_to_image_lists_free_pollinations_models(tmp_path: Path) -> None:
    tool = TextToImageTool({"project_root": tmp_path})

    result = tool.execute(action="list_models", source="pollinations")

    assert result.success is True
    ids = {item["id"] for item in result.data["models"]}
    assert {
        "flux",
        "gptimage",
        "gptimage-large",
        "kontext",
        "zimage",
        "wan-image",
        "qwen-image",
        "klein",
        "nova-canvas",
    } <= ids
    assert "seedream" not in ids
    assert "nanobanana" not in ids


def test_text_to_image_lists_agnes_models(tmp_path: Path) -> None:
    tool = TextToImageTool({"project_root": tmp_path})

    result = tool.execute(action="list_models", source="agnes")

    assert result.success is True
    ids = {item["id"] for item in result.data["models"]}
    assert {"agnes-image-2.0-flash", "agnes-image-2.1-flash"} <= ids


def test_text_to_image_pollinations_diagnose_requires_api_key(tmp_path: Path) -> None:
    tool = TextToImageTool({"project_root": tmp_path})

    result = tool.execute(action="diagnose", source="pollinations")

    assert result.status.value == "partial"
    assert result.data["ready"] is False
    assert any(check["id"] == "api_key" and check["ok"] is False for check in result.data["checks"])


def test_text_to_image_agnes_diagnose_requires_shared_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_TOKEN", raising=False)
    tool = TextToImageTool({"project_root": tmp_path})

    result = tool.execute(action="diagnose", source="agnes")

    assert result.status.value == "partial"
    assert result.data["ready"] is False
    assert any(check["id"] == "api_key" and check["ok"] is False for check in result.data["checks"])


def test_aihubmix_gpt_image_profile_saves_base64_response(tmp_path: Path) -> None:
    image_bytes = b"fake-png-bytes"
    encoded = base64.b64encode(image_bytes).decode("ascii")

    class FakeImages:
        def generate(self, **kwargs):
            assert kwargs["model"] == "gpt-image-2-free"
            assert kwargs["n"] == 1
            assert kwargs["size"] == "auto"
            assert kwargs["quality"] == "auto"
            return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)])

    result = gpt_image_2_free.generate_image(
        SimpleNamespace(images=FakeImages()),
        prompt="flowers",
        output_path=tmp_path / "out",
    )

    saved = Path(result["saved_images"][0])
    assert saved.exists()
    assert saved.read_bytes() == image_bytes


def test_agnes_image_profile_saves_base64_response(tmp_path: Path, monkeypatch) -> None:
    image_bytes = b"fake-agnes-png"
    encoded = base64.b64encode(image_bytes).decode("ascii")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": encoded}]}

    def fake_post(url, headers, json, timeout):
        assert url == "https://apihub.agnes-ai.com/v1/images/generations"
        assert headers["Authorization"] == "Bearer agnes-test"
        assert json["model"] == "agnes-image-2.1-flash"
        assert json["extra_body"]["response_format"] == "b64_json"
        return FakeResponse()

    monkeypatch.setattr("reverie.agnes_tti_profiles.common.requests.post", fake_post)

    result = agnes_image_21_flash.generate_image(
        prompt="flowers",
        output_path=tmp_path / "out",
        base_url="https://apihub.agnes-ai.com/v1",
        api_key="agnes-test",
        n=1,
        size="1024x1024",
        quality="auto",
        response_format="b64_json",
    )

    saved = Path(result["saved_images"][0])
    assert saved.exists()
    assert saved.read_bytes() == image_bytes
    assert result["request"]["response_format"] == "b64_json"


def test_aihubmix_gemini_image_profile_saves_inline_data(tmp_path: Path) -> None:
    image_bytes = b"fake-gemini-png"
    encoded = base64.b64encode(image_bytes).decode("ascii")

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == "gemini-3.1-flash-image-preview-free"
            assert kwargs["messages"][0]["content"] == "aspect_ratio=2:3"
            assert kwargs["modalities"] == ["text", "image"]
            message = SimpleNamespace(
                multi_mod_content=[
                    {"text": "done"},
                    {"inline_data": {"mime_type": "image/png", "data": encoded}},
                ]
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    result = gemini_31_flash_image_preview_free.generate_image(
        client,
        prompt="butterfly",
        output_path=tmp_path / "out",
        aspect_ratio="2:3",
    )

    saved = Path(result["saved_images"][0])
    assert saved.exists()
    assert saved.read_bytes() == image_bytes
    assert result["text_parts"] == ["done"]


def test_pollinations_flux_profile_saves_base64_response(tmp_path: Path, monkeypatch) -> None:
    image_bytes = b"fake-pollinations-png"
    encoded = base64.b64encode(image_bytes).decode("ascii")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": encoded}]}

    def fake_post(url, headers, json, timeout):
        assert url == "https://gen.pollinations.ai/v1/images/generations"
        assert "Authorization" not in headers
        assert json["model"] == "flux"
        assert json["n"] == 1
        assert json["size"] == "1024x1024"
        assert json["quality"] == "medium"
        assert json["response_format"] == "b64_json"
        assert timeout == 30
        return FakeResponse()

    monkeypatch.setattr("reverie.pollinations_tti_profiles.common.requests.post", fake_post)

    result = flux.generate_image(
        prompt="flowers",
        output_path=tmp_path / "out",
        base_url="https://gen.pollinations.ai/v1",
        api_key="",
        timeout=30,
    )

    saved = Path(result["saved_images"][0])
    assert saved.exists()
    assert saved.read_bytes() == image_bytes


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
