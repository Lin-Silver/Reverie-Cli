import json

import httpx
from openai import OpenAI
import pytest

from reverie.agent.agent import ReverieAgent
from reverie.cli.interface import ReverieInterface
from reverie.config import Config
from reverie.desktop_catalog import build_model_sources_payload
from reverie.nvidia import (
    apply_nvidia_request_defaults,
    build_nvidia_openai_options,
    build_nvidia_request_defaults,
    get_nvidia_model_catalog,
    resolve_nvidia_model_profile_name,
)


SAMPLING = {
    "meta/muse-glimmer-30b": (1.0, 0.95, {"top_k": 64}),
    "nvidia/nemotron-3.5-lightning-30b-a3b": (1.0, 0.95, {}),
    "nvidia/nemotron-3-super-120b-a12b": (1.0, 0.95, {}),
    "nvidia/nemotron-3-ultra-550b-a55b": (1.0, 0.95, {}),
    "poolside/laguna-xs-2.1": (1.0, 1.0, {"top_k": 20, "min_p": 0.0}),
    "nvidia/nemotron-3.5-super-vl-120b-a12b": (1.0, 0.95, {}),
    "deepseek-ai/deepseek-v4.1-flash": (1.0, 0.95, {}),
    "z-ai/glm-5.3-flash": (1.0, 0.95, {}),
    "stepfun-ai/step-5-preview": (1.0, 0.95, {"top_k": 0}),
    "openai/gpt-oss-20b": (1.0, 1.0, {}),
}
SUPER_VL = "nvidia/nemotron-3.5-super-vl-120b-a12b"


def test_all_offline_nvidia_models_have_sampling_profiles():
    assert {model["id"] for model in get_nvidia_model_catalog()} == set(SAMPLING)
    assert all(resolve_nvidia_model_profile_name(model_id) for model_id in SAMPLING)


def test_nvidia_settings_remove_ineffective_sampling_inputs_without_changing_other_sources():
    sources = {source["id"]: source for source in build_model_sources_payload(Config())["sources"]}
    fields = {source_id: {field["key"] for field in source["config_fields"]} for source_id, source in sources.items()}
    assert "temperature" not in fields["nvidia"]
    assert "top_p" not in fields["nvidia"]
    assert {"api_key", "api_url", "timeout", "reasoning_budget"} <= fields["nvidia"]
    assert "temperature" in fields["opencode"]
    assert {"temperature", "top_p"} <= fields["sensenova"]


@pytest.mark.parametrize("model", get_nvidia_model_catalog(), ids=lambda model: model["id"])
def test_nvidia_visual_attachment_gate_uses_capability_not_transport(model):
    config = Config.from_dict({"active_model_source": "nvidia", "nvidia": {"selected_model_id": model["id"], "api_key": "test"}})
    interface = ReverieInterface.__new__(ReverieInterface)
    allowed, reason = interface._can_attach_inline_images(config)
    assert allowed is bool(model["vision"])
    assert bool(reason) is not allowed
    assert interface._current_inline_media_modalities(config) == model["vision_modalities"]


@pytest.mark.parametrize("model_id", SAMPLING)
def test_publisher_sampling_is_not_replaced_by_legacy_shared_config(model_id):
    config = {
        "selected_model_id": model_id,
        "temperature": 0.01,
        "top_p": 0.01,
        "top_k": 999,
        "min_p": 0.9,
        "presence_penalty": 2.0,
        "repetition_penalty": 1.5,
    }
    options = build_nvidia_request_defaults(config) if model_id.startswith("stepfun") else build_nvidia_openai_options(config)
    temperature, top_p, extra = SAMPLING[model_id]
    assert options["temperature"] == temperature
    assert options["top_p"] == top_p
    flattened = {**options, **options.get("extra_body", {})}
    assert {key: flattened[key] for key in extra} == extra
    assert "presence_penalty" not in flattened
    assert "repetition_penalty" not in flattened


@pytest.mark.parametrize("part_type", ["image_url", "video_url"])
def test_super_vl_matches_sampling_to_visual_input_in_conversation_history(part_type):
    config = {"selected_model_id": SUPER_VL, "has_visual_input": False}
    messages = [
        {"role": "user", "content": [{"type": part_type, part_type: {"url": "https://example.test/media"}}]},
        {"role": "assistant", "content": "I can see it."},
        {"role": "user", "content": "Explain it."},
    ]
    assert build_nvidia_openai_options(config, messages=messages)["temperature"] == 0.6
    assert config["has_visual_input"] is False
    assert build_nvidia_openai_options(config)["temperature"] == 1.0
    assert build_nvidia_openai_options({**config, "has_visual_input": True})["temperature"] == 1.0


@pytest.mark.parametrize("messages", [None, [], [{"role": "user", "content": "image_url video_url"}], [
    {"role": "user", "content": [{"type": "text", "text": "Describe an image."}]},
]])
def test_super_vl_text_only_requests_keep_text_sampling(messages):
    assert build_nvidia_openai_options({"selected_model_id": SUPER_VL}, messages=messages)["temperature"] == 1.0


def test_other_nvidia_models_do_not_receive_super_vl_visual_temperature():
    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.test/image"}}]}]
    for model_id in SAMPLING:
        if model_id != SUPER_VL and not model_id.startswith("stepfun"):
            assert build_nvidia_openai_options({"selected_model_id": model_id}, messages=messages)["temperature"] == 1.0


def test_step_raw_request_sends_disabled_top_k_and_preserves_explicit_request_overrides():
    config = {"selected_model_id": "stepfun-ai/step-5-preview"}
    payload = {"model": config["selected_model_id"], "messages": []}
    prepared = apply_nvidia_request_defaults(payload, config)
    assert (prepared["temperature"], prepared["top_p"], prepared["top_k"]) == (1.0, 0.95, 0)
    assert "top_k" not in payload
    assert apply_nvidia_request_defaults({**payload, "max_tokens": 73}, config)["max_tokens"] == 73


@pytest.mark.parametrize("model_id", ["meta/muse-glimmer-30b", "poolside/laguna-xs-2.1", "z-ai/glm-5.3-flash", SUPER_VL])
@pytest.mark.parametrize("stream", [False, True])
def test_agent_serializes_recommended_sampling_through_actual_sdk(monkeypatch, tmp_path, model_id, stream):
    config = Config.from_dict({"active_model_source": "nvidia", "nvidia": {"selected_model_id": model_id, "api_key": "test"}})
    runtime = config.active_model
    agent = ReverieAgent(
        base_url=runtime.base_url, api_key="test", model=model_id,
        provider=runtime.provider, config=config, project_root=tmp_path,
    )
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        if stream:
            data = {"id": "test", "choices": [{"index": 0, "delta": {"content": "OK"}, "finish_reason": "stop"}]}
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=f"data: {json.dumps(data)}\n\ndata: [DONE]\n\n")
        return httpx.Response(200, json={"id": "test", "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]})

    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.test/image"}}]}] if model_id == SUPER_VL else [{"role": "user", "content": "Reply OK."}]
    monkeypatch.setattr(agent, "_build_messages", lambda: messages)
    monkeypatch.setattr(agent, "get_visible_tool_schemas", lambda: [])
    monkeypatch.setattr(agent, "_check_and_compress_context", lambda **kwargs: None)
    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        with OpenAI(api_key="test", base_url=runtime.base_url, http_client=http_client) as client:
            monkeypatch.setattr(agent, "_ensure_client", lambda: client)
            if stream:
                assert "OK" in "".join(agent._process_streaming_openai_sdk())
            else:
                assert agent._process_non_streaming_openai_sdk() == "OK"
    payload = captured[0]
    temperature, top_p, extra = SAMPLING[model_id]
    assert payload["temperature"] == (0.6 if model_id == SUPER_VL else temperature)
    assert payload["top_p"] == top_p
    assert {key: payload[key] for key in extra} == extra
    assert "has_visual_input" not in payload


def test_sdk_fallback_kwargs_use_the_same_visual_sampling(tmp_path):
    config = Config.from_dict({"active_model_source": "nvidia", "nvidia": {"selected_model_id": SUPER_VL, "api_key": "test"}})
    runtime = config.active_model
    agent = ReverieAgent(
        base_url=runtime.base_url, api_key="test", model=SUPER_VL,
        provider=runtime.provider, config=config, project_root=tmp_path,
    )
    payload = agent._build_openai_chat_completion_kwargs(
        messages=[{"role": "user", "content": [{"type": "video_url", "video_url": {"url": "https://example.test/video"}}]}],
        tools=[], stream=False,
    )
    assert (payload["temperature"], payload["top_p"]) == (0.6, 0.95)
