from pathlib import Path

from reverie.inline_images import (
    parse_inline_media_mentions,
    resolve_inline_image_content_for_request,
    supported_inline_media_extensions,
)


def test_supported_inline_media_extensions_follow_modalities():
    assert ".png" in supported_inline_media_extensions(["image"])
    assert ".mp4" not in supported_inline_media_extensions(["image"])
    assert ".png" in supported_inline_media_extensions(["image", "video"])
    assert ".mp4" in supported_inline_media_extensions(["image", "video"])


def test_parse_inline_media_mentions_allows_video_when_model_supports_video(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-video")
    image = tmp_path / "frame.png"
    image.write_bytes(b"fake-image")

    parsed = parse_inline_media_mentions(
        "compare @clip.mp4 and @frame.png",
        tmp_path,
        modalities=["image", "video"],
    )

    assert parsed["clean_text"] == "compare and"
    assert [item["type"] for item in parsed["attachments"]] == ["local_video", "local_image"]

    resolved = resolve_inline_image_content_for_request(
        [{"type": "text", "text": parsed["clean_text"]}] + parsed["attachments"],
        tmp_path,
    )
    assert resolved[1]["type"] == "video_url"
    assert resolved[1]["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert resolved[2]["type"] == "image_url"
    assert resolved[2]["image_url"]["url"].startswith("data:image/png;base64,")


def test_parse_inline_media_mentions_ignores_video_for_image_only_models(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-video")

    parsed = parse_inline_media_mentions("inspect @clip.mp4", tmp_path, modalities=["image"])

    assert parsed["clean_text"] == "inspect @clip.mp4"
    assert parsed["attachments"] == []
