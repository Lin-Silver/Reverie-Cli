from pathlib import Path

from reverie.agnes_tti_profiles import common


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [{"url": "https://example.test/image.png"}]}


def test_agnes_tti_omits_openai_style_defaults(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(common.requests, "post", fake_post)
    monkeypatch.setattr(common, "save_url_image", lambda *args, **kwargs: str(Path(tmp_path) / "image.png"))

    result = common.generate_agnes_image(
        model_id="agnes-image-2.1-flash",
        display_name="Agnes Image 2.1 Flash",
        prompt="library background",
        output_path=tmp_path,
        base_url="https://apihub.agnes-ai.com/v1",
        api_key="test-key",
        n=1,
        size="1024x1024",
        quality="auto",
        response_format="b64_json",
    )

    assert captured["payload"] == {
        "model": "agnes-image-2.1-flash",
        "prompt": "library background",
    }
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert result["saved_images"] == [str(Path(tmp_path) / "image.png")]


def test_agnes_tti_keeps_explicit_non_default_options(monkeypatch, tmp_path):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return _FakeResponse()

    monkeypatch.setattr(common.requests, "post", fake_post)
    monkeypatch.setattr(common, "save_url_image", lambda *args, **kwargs: str(Path(tmp_path) / "image.png"))

    common.generate_agnes_image(
        model_id="agnes-image-2.1-flash",
        display_name="Agnes Image 2.1 Flash",
        prompt="library background",
        output_path=tmp_path,
        base_url="https://apihub.agnes-ai.com/v1",
        api_key="test-key",
        n=2,
        size="768x1024",
        quality="low",
        response_format="url",
        seed=123,
        extra_body={"mode": "reference", "ignored": None},
    )

    assert captured["payload"] == {
        "model": "agnes-image-2.1-flash",
        "prompt": "library background",
        "n": 2,
        "size": "768x1024",
        "quality": "low",
        "response_format": "url",
        "extra_body": {"mode": "reference"},
        "seed": 123,
    }
