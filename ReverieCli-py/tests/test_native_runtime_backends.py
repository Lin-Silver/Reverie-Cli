from __future__ import annotations

from pathlib import Path

from PIL import Image

from reverie.engine import Material, RenderCommand, RenderMode, RenderingServer, Transform, Vector3, Vector4
from reverie.engine.audio import AudioManager
from reverie.engine.live2d import Live2DManager


def test_native_renderer_draws_to_an_rgba_framebuffer(tmp_path: Path) -> None:
    renderer = RenderingServer(RenderMode.RENDER_3D, headless=False)
    renderer.set_viewport(32, 24)
    assert renderer.initialize() is True

    if renderer.backend.value == "headless":
        summary = renderer.frame_summary()
        assert summary["fallback_reason"]
        assert summary["native_ready"] is False
        return

    renderer.submit(
        RenderCommand(
            source_node="cube",
            primitive="mesh",
            pipeline="world_3d",
            mesh_id="cube",
            material=Material(albedo_color=Vector4(1.0, 0.2, 0.1, 1.0)),
            transform=Transform(position=Vector3(0.0, 0.0, -3.0)),
        )
    )
    renderer.render_frame()
    output = tmp_path / "native-frame.png"
    renderer.save_frame(str(output))

    pixels = renderer.read_pixels()
    assert len(pixels) == 32 * 24 * 4
    clear_pixel = bytes((26, 26, 26, 255))
    assert any(pixels[offset : offset + 4] != clear_pixel for offset in range(0, len(pixels), 4))
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert renderer.frame_summary()["native_draw_calls"] == 1
    assert renderer.frame_summary()["native_errors"] == []
    renderer.shutdown()


def test_audio_backend_reports_real_failure_instead_of_simulated_success(tmp_path: Path) -> None:
    audio = AudioManager(tmp_path)

    assert audio.load_stream("missing", "missing.wav") is False
    assert audio.create_player("missing-player", "missing") is None
    assert audio.play("missing-player") is False
    status = audio.backend_status()
    assert status["installed"] is audio.is_available()
    assert status["mode"] in {"unavailable", "unverified", "playback"}


def test_native_renderer_loads_project_relative_textures(tmp_path: Path) -> None:
    texture_path = tmp_path / "assets" / "textures" / "marker.png"
    texture_path.parent.mkdir(parents=True)
    Image.new("RGBA", (2, 2), (0, 255, 0, 255)).save(texture_path)
    renderer = RenderingServer(RenderMode.RENDER_2D, headless=False, asset_root=tmp_path)
    renderer.set_viewport(32, 32)
    renderer.initialize()
    if renderer.backend.value == "headless":
        assert renderer.frame_summary()["fallback_reason"]
        return

    renderer.submit(
        RenderCommand(
            source_node="textured-quad",
            primitive="sprite",
            pipeline="canvas_2d",
            mesh_id="quad",
            material=Material(albedo_texture="assets/textures/marker.png"),
            transform=Transform(scale=Vector3(20.0, 20.0, 1.0)),
        )
    )
    renderer.render_frame()

    assert renderer.frame_summary()["native_draw_calls"] == 1
    assert renderer.frame_summary()["native_errors"] == []
    assert renderer.frame_summary()["texture_count"] == 1
    assert renderer.frame_summary()["gpu_mesh_count"] == 1
    renderer.shutdown()


def test_live2d_readiness_does_not_claim_runtime_for_an_empty_project(tmp_path: Path) -> None:
    manager = Live2DManager(tmp_path)
    manager.load_manifest().enabled = True

    readiness = manager.readiness_report()

    assert readiness["status"] == "unconfigured"
    assert readiness["native_renderer_implemented"] is False
    assert readiness["assets_valid"] is False
