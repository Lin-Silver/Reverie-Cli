from reverie.agnes import (
    AGNES_DEFAULT_API_URL,
    build_agnes_openai_options,
    build_agnes_runtime_model_data,
    get_agnes_model_catalog,
    normalize_agnes_config,
    resolve_agnes_sdk_base_url,
)
from reverie.config import Config, EXTERNAL_MODEL_SOURCES
from reverie.media_capabilities import build_media_capabilities
from reverie.provider_smoke import BUILTIN_PROVIDER_NAMES
from reverie.tools.media_generation_capabilities import MediaGenerationCapabilitiesTool
from reverie.tools.text_to_video import TextToVideoTool


def test_agnes_catalog_contains_documented_text_models(monkeypatch) -> None:
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    catalog = get_agnes_model_catalog({"live_model_list": False})
    ids = {item["id"] for item in catalog}

    assert {"agnes-2.0-flash", "agnes-1.5-flash", "agnes-1.5-pro"} <= ids


def test_agnes_catalog_context_lengths_match_model_docs(monkeypatch) -> None:
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    catalog = {item["id"]: item for item in get_agnes_model_catalog({"live_model_list": False})}

    assert catalog["agnes-2.0-flash"]["context_length"] == 256_000
    assert catalog["agnes-2.0-flash"]["max_output_tokens"] == 65_536
    assert catalog["agnes-1.5-flash"]["context_length"] == 256_000
    assert catalog["agnes-1.5-flash"]["max_output_tokens"] == 65_536
    assert catalog["agnes-1.5-pro"]["context_length"] == 256_000
    assert catalog["agnes-1.5-pro"]["max_output_tokens"] == 256_000


def test_agnes_base_url_normalizes_chat_completion_urls() -> None:
    assert resolve_agnes_sdk_base_url("apihub.agnes-ai.com/v1/chat/completions") == AGNES_DEFAULT_API_URL
    assert resolve_agnes_sdk_base_url("https://apihub.agnes-ai.com") == AGNES_DEFAULT_API_URL


def test_agnes_runtime_model_data_uses_env_key(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test")

    runtime = build_agnes_runtime_model_data(
        {
            "selected_model_id": "agnes-1.5-flash",
            "api_url": "https://apihub.agnes-ai.com/v1/chat/completions",
            "live_model_list": False,
        }
    )

    assert runtime is not None
    assert runtime["model"] == "agnes-1.5-flash"
    assert runtime["model_display_name"] == "Agnes 1.5 Flash"
    assert runtime["provider"] == "openai-sdk"
    assert runtime["base_url"] == AGNES_DEFAULT_API_URL
    assert runtime["api_key"] == "agnes-test"


def test_config_active_model_resolves_agnes(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test")
    config = Config(
        active_model_source="agnes",
        agnes=normalize_agnes_config({"selected_model_id": "agnes-2.0-flash", "live_model_list": False}),
    )

    active = config.active_model

    assert "agnes" in EXTERNAL_MODEL_SOURCES
    assert "agnes" in BUILTIN_PROVIDER_NAMES
    assert active is not None
    assert active.model == "agnes-2.0-flash"
    assert active.model_display_name == "Agnes 2.0 Flash"
    assert active.provider == "openai-sdk"
    assert active.supports_vision is True


def test_agnes_openai_options_match_provider_defaults() -> None:
    options = build_agnes_openai_options({"selected_model_id": "agnes-2.0-flash", "live_model_list": False})

    assert options == {
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 65536,
    }


def test_text_to_video_lists_agnes_model(tmp_path) -> None:
    tool = TextToVideoTool({"project_root": tmp_path})

    result = tool.execute(action="list_models")

    assert result.success is True
    assert result.data["source"] == "agnes"
    assert {item["id"] for item in result.data["models"]} == {"agnes-video-v2.0"}
    model = result.data["models"][0]
    assert model["parameter_constraints"]["num_frames"]["rule"] == "8n+1"
    assert model["output_capabilities"]["downloadable_video"] is True


def test_text_to_video_rejects_invalid_frame_count_before_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test")
    tool = TextToVideoTool({"project_root": tmp_path})

    result = tool.execute(action="generate", prompt="a calm ocean wave", num_frames=80)

    assert result.success is False
    assert "8n+1" in (result.error or "")


def test_media_capabilities_report_runtime_image_and_video_profiles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test")
    capabilities = build_media_capabilities(project_root=tmp_path)

    assert capabilities["image"]["tool"] == "text_to_image"
    assert capabilities["video"]["tool"] == "text_to_video"
    assert capabilities["video"]["active_source"] == "agnes"
    assert capabilities["video"]["sources"]["agnes"]["api_key_available"] is True
    assert capabilities["video"]["sources"]["agnes"]["models"][0]["parameter_constraints"]["num_frames"]["rule"] == "8n+1"


def test_media_generation_capabilities_tool_is_read_only(tmp_path) -> None:
    tool = MediaGenerationCapabilitiesTool({"project_root": tmp_path})

    result = tool.execute(detail="summary")

    assert tool.read_only is True
    assert result.success is True
    assert "Runtime Media Capabilities" in result.output
    assert result.data["image"]["tool"] == "text_to_image"
    assert result.data["video"]["tool"] == "text_to_video"
