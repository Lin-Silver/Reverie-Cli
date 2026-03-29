from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json

import pytest

import reverie.engine_lite.video as video_module
from reverie.engine_lite.project import create_project_skeleton
from reverie.engine_lite.video import discover_ffmpeg, export_project_video


def test_discover_ffmpeg_prefers_pyinstaller_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle_root = tmp_path / "_MEIPASS"
    ffmpeg_path = bundle_root / "reverie_resources" / "ffmpeg" / "ffmpeg.exe"
    ffmpeg_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_path.write_bytes(b"fake-ffmpeg")

    monkeypatch.delenv("REVERIE_FFMPEG_PATH", raising=False)
    monkeypatch.setattr(video_module.shutil, "which", lambda _: "")
    monkeypatch.setattr(video_module.sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setattr(video_module.sys, "executable", str(tmp_path / "dist" / "reverie.exe"), raising=False)

    assert discover_ffmpeg() == str(ffmpeg_path.resolve())


def test_export_project_video_frames_writes_manifest_and_images() -> None:
    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "video_project"
        create_project_skeleton(
            project_root,
            project_name="Video Test",
            dimension="3D",
            sample_name="3d_arena",
            genre="arena",
            overwrite=True,
        )

        result = export_project_video(project_root, format_name="frames", frames=18, frame_stride=3)

        manifest_path = Path(result["manifest_path"])
        frames_dir = Path(result["frames_dir"])
        assert result["success"] is True
        assert result["frame_count"] == 6
        assert manifest_path.exists()
        assert frames_dir.exists()
        assert len(list(frames_dir.glob("frame_*.png"))) == 6

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["captured_frames"] == 6
        assert manifest["summary"]["event_count"] >= 1


def test_export_project_video_mp4_encodes_when_ffmpeg_is_available() -> None:
    ffmpeg_path = discover_ffmpeg()
    if not ffmpeg_path:
        pytest.skip("ffmpeg is not available in this environment")

    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "video_project"
        create_project_skeleton(
            project_root,
            project_name="Galgame Video Test",
            dimension="2D",
            sample_name="galgame_live2d",
            genre="galgame",
            overwrite=True,
        )

        result = export_project_video(project_root, format_name="mp4", frames=12, frame_stride=2)

        assert result["success"] is True
        assert result["encoded"] is True
        assert Path(result["output_path"]).exists()
        assert str(result["ffmpeg_path"]).lower().endswith("ffmpeg.exe") or str(result["ffmpeg_path"]).lower().endswith("ffmpeg")
