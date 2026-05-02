"""Playblast-style video export helpers for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import json
import math
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

from .app import EngineLiteApp, RuntimeProfile, load_project_scene
from .config import load_engine_config
from .rendering import RenderCommand, RenderFrame, RenderMode


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "playblast"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_default_input_script(project_root: Path) -> list[dict[str, Any]]:
    input_path = project_root / "playtest/logs/input_script.json"
    if not input_path.exists():
        return []
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, dict) and isinstance(payload.get("inputs"), list):
        return [item for item in payload["inputs"] if isinstance(item, dict)]
    return []


def _iter_ffmpeg_candidates() -> Iterable[Path]:
    seen: set[str] = set()

    def _yield_candidate(candidate: Path | str | None) -> Iterable[Path]:
        if not candidate:
            return []
        candidate_path = Path(candidate)
        if candidate_path.is_dir():
            possible_paths = [
                candidate_path / "ffmpeg.exe",
                candidate_path / "ffmpeg",
            ]
        else:
            possible_paths = [candidate_path]
        unique_paths: list[Path] = []
        for possible_path in possible_paths:
            key = str(possible_path).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_paths.append(possible_path)
        return unique_paths

    env_candidate = str(os.environ.get("REVERIE_FFMPEG_PATH") or "").strip()
    if env_candidate:
        for candidate in _yield_candidate(env_candidate):
            yield candidate

    bundle_roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        bundle_roots.append(Path(meipass))
    try:
        bundle_roots.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass

    for root in bundle_roots:
        for relative_path in (
            Path("reverie_resources/ffmpeg/ffmpeg.exe"),
            Path("reverie_resources/ffmpeg/ffmpeg"),
            Path("ffmpeg.exe"),
            Path("ffmpeg"),
        ):
            for candidate in _yield_candidate(root / relative_path):
                yield candidate

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        for candidate in _yield_candidate(which_ffmpeg):
            yield candidate

    for fallback in (
        Path("D:/Program Files/Environment/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
    ):
        for candidate in _yield_candidate(fallback):
            yield candidate


def discover_ffmpeg() -> str:
    for candidate in _iter_ffmpeg_candidates():
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())
    return ""


@dataclass
class VideoExportSettings:
    format: str = "mp4"
    fps: int = 30
    width: int = 1280
    height: int = 720
    frames: int = 180
    output_path: str = ""
    frame_stride: int = 1


class PlayblastFrameRenderer:
    """Renders a deterministic storyboard frame from engine render commands."""

    def __init__(self, width: int, height: int) -> None:
        self.width = max(320, int(width))
        self.height = max(240, int(height))
        self._font = ImageFont.load_default()

    def render(
        self,
        frame: RenderFrame,
        *,
        title: str,
        dialogue_view: Optional[Dict[str, Any]] = None,
        world_state: Optional[Dict[str, Any]] = None,
        telemetry_events: int = 0,
    ) -> Image.Image:
        image = Image.new("RGBA", (self.width, self.height), (245, 247, 251, 255))
        draw = ImageDraw.Draw(image, "RGBA")
        self._draw_background(draw, frame.mode)
        self._draw_world(draw, frame.commands, frame.mode)
        self._draw_ui(draw, frame.commands)
        self._draw_hud(draw, frame, title=title, telemetry_events=telemetry_events, world_state=world_state or {})
        if dialogue_view and dialogue_view.get("conversation_id"):
            self._draw_dialogue(draw, dialogue_view)
        return image

    def _draw_background(self, draw: ImageDraw.ImageDraw, mode: RenderMode) -> None:
        sky = {
            RenderMode.RENDER_2D: ((245, 244, 238), (226, 233, 244)),
            RenderMode.RENDER_2D_ISOMETRIC: ((237, 244, 239), (214, 229, 239)),
            RenderMode.RENDER_3D: ((229, 238, 246), (208, 221, 238)),
        }.get(mode, ((245, 244, 238), (226, 233, 244)))
        for row in range(self.height):
            mix = row / max(self.height - 1, 1)
            color = tuple(
                int(sky[0][channel] * (1.0 - mix) + sky[1][channel] * mix)
                for channel in range(3)
            )
            draw.line((0, row, self.width, row), fill=color + (255,))
        horizon_y = int(self.height * 0.72)
        draw.rectangle((0, horizon_y, self.width, self.height), fill=(229, 230, 222, 255))
        for column in range(0, self.width, 56):
            draw.line((column, horizon_y, column + 30, self.height), fill=(196, 202, 194, 130), width=1)
        for row in range(horizon_y, self.height, 36):
            draw.line((0, row, self.width, row), fill=(190, 196, 188, 120), width=1)

    def _draw_world(self, draw: ImageDraw.ImageDraw, commands: Iterable[RenderCommand], mode: RenderMode) -> None:
        shapes: list[tuple[float, RenderCommand]] = []
        for command in commands:
            if command.pipeline not in {"world_3d", "canvas_2d"}:
                continue
            position = command.transform.position
            depth = float(position.z if command.pipeline == "world_3d" else position.y)
            shapes.append((depth, command))

        for _, command in sorted(shapes, key=lambda item: item[0]):
            position = command.transform.position
            screen_x, screen_y = self._project(position.x, position.y, position.z, mode, command.pipeline)
            scale_x = max(18.0, float(command.transform.scale.x) * 70.0)
            scale_y = max(18.0, float(command.transform.scale.y) * 70.0)
            metadata = dict(command.metadata or {})

            if command.primitive in {"sprite", "billboard_sprite", "parallax_sprite"}:
                size = metadata.get("size") or [1.0, 1.0]
                scale_x = max(scale_x, _safe_float(size[0], 1.0) * 72.0)
                scale_y = max(scale_y, _safe_float(size[1], 1.0) * 72.0)
                fill = (86, 151, 163, 210) if command.pipeline == "canvas_2d" else (88, 123, 178, 210)
                draw.rounded_rectangle(
                    (screen_x - scale_x / 2, screen_y - scale_y, screen_x + scale_x / 2, screen_y),
                    radius=10,
                    fill=fill,
                    outline=(39, 52, 72, 180),
                    width=2,
                )
            elif command.primitive == "mesh":
                fill = (94, 120, 172, 220)
                if str(command.mesh_id).lower() in {"sphere"}:
                    draw.ellipse(
                        (screen_x - scale_x / 2, screen_y - scale_y / 2, screen_x + scale_x / 2, screen_y + scale_y / 2),
                        fill=fill,
                        outline=(40, 54, 84, 180),
                        width=2,
                    )
                elif str(command.mesh_id).lower() in {"pyramid"}:
                    draw.polygon(
                        (
                            (screen_x, screen_y - scale_y),
                            (screen_x + scale_x / 2, screen_y + scale_y / 3),
                            (screen_x - scale_x / 2, screen_y + scale_y / 3),
                        ),
                        fill=fill,
                        outline=(40, 54, 84, 180),
                    )
                else:
                    draw.rounded_rectangle(
                        (screen_x - scale_x / 2, screen_y - scale_y / 2, screen_x + scale_x / 2, screen_y + scale_y / 2),
                        radius=12,
                        fill=fill,
                        outline=(40, 54, 84, 180),
                        width=2,
                    )
            elif command.primitive == "particles":
                for offset in range(5):
                    particle_x = screen_x + ((offset % 2) * 10) - 5
                    particle_y = screen_y - offset * 7
                    draw.ellipse((particle_x - 5, particle_y - 5, particle_x + 5, particle_y + 5), fill=(244, 154, 76, 180))
            elif command.primitive in {"tilemap", "parallax_tilemap"}:
                draw.rectangle(
                    (screen_x - 100, screen_y - 30, screen_x + 100, screen_y + 30),
                    fill=(128, 168, 132, 160),
                    outline=(54, 86, 58, 160),
                    width=2,
                )
            else:
                draw.rectangle(
                    (screen_x - 22, screen_y - 22, screen_x + 22, screen_y + 22),
                    fill=(132, 146, 164, 180),
                    outline=(48, 58, 76, 180),
                    width=2,
                )

            label = command.source_node.split("/")[-1] if "/" in command.source_node else command.source_node.split("\\")[-1]
            draw.text((screen_x + 8, screen_y - scale_y - 8), label[:28], fill=(22, 26, 34, 255), font=self._font)

    def _draw_ui(self, draw: ImageDraw.ImageDraw, commands: Iterable[RenderCommand]) -> None:
        for command in commands:
            if command.pipeline != "ui":
                continue
            rect = dict(command.metadata.get("rect") or {})
            x = _safe_float(rect.get("x"), 0.0)
            y = _safe_float(rect.get("y"), 0.0)
            width = _safe_float(rect.get("width"), 120.0)
            height = _safe_float(rect.get("height"), 40.0)
            if command.primitive in {"panel", "dialogue_box"}:
                draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill=(28, 34, 46, 185), outline=(245, 245, 248, 150), width=2)
            elif command.primitive == "choice_list":
                draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=(250, 250, 252, 210), outline=(56, 64, 82, 160), width=2)
            elif command.primitive == "button":
                draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=(88, 123, 178, 215), outline=(28, 40, 62, 180), width=2)
                draw.text((x + 12, y + 12), str(command.metadata.get("text") or "Button"), fill=(255, 255, 255, 255), font=self._font)
            elif command.primitive == "progress_bar":
                ratio = max(0.0, min(1.0, _safe_float(command.metadata.get("ratio"), 0.0)))
                draw.rounded_rectangle((x, y, x + width, y + height), radius=10, fill=(42, 48, 60, 150), outline=(255, 255, 255, 110), width=1)
                draw.rounded_rectangle((x + 4, y + 4, x + 4 + (width - 8) * ratio, y + height - 4), radius=8, fill=(132, 207, 151, 220))

    def _draw_hud(
        self,
        draw: ImageDraw.ImageDraw,
        frame: RenderFrame,
        *,
        title: str,
        telemetry_events: int,
        world_state: Dict[str, Any],
    ) -> None:
        draw.rounded_rectangle((28, 28, 440, 156), radius=18, fill=(255, 255, 255, 220), outline=(52, 62, 84, 70), width=2)
        lines = [
            title[:56],
            f"frame {frame.frame_index:04d}  mode {frame.mode.value}  backend {frame.backend.value}",
            f"draw_calls {frame.draw_calls}  lights {frame.light_count}  telemetry {telemetry_events}",
            f"camera {frame.active_camera or 'none'}",
        ]
        flags = sorted((world_state.get("flags") or {}).keys())
        if flags:
            lines.append(f"flags {', '.join(flags[:3])}")
        y = 42
        for line in lines:
            draw.text((46, y), line, fill=(22, 26, 34, 255), font=self._font)
            y += 24

    def _draw_dialogue(self, draw: ImageDraw.ImageDraw, dialogue_view: Dict[str, Any]) -> None:
        box_height = 176
        left = 36
        right = self.width - 36
        top = self.height - box_height - 28
        bottom = self.height - 28
        draw.rounded_rectangle((left, top, right, bottom), radius=24, fill=(24, 27, 35, 228), outline=(255, 255, 255, 92), width=2)
        speaker = str(dialogue_view.get("speaker") or "Narrator")
        text = str(dialogue_view.get("text") or "")
        choices = list(dialogue_view.get("choices") or [])
        draw.text((left + 26, top + 18), speaker[:42], fill=(255, 237, 186, 255), font=self._font)
        for index, line in enumerate(self._wrap_text(text, 88)[:4]):
            draw.text((left + 26, top + 48 + index * 22), line, fill=(244, 245, 247, 255), font=self._font)
        choice_top = top + 48 + min(4, len(self._wrap_text(text, 88))) * 22 + 12
        for index, choice in enumerate(choices[:3]):
            label = f"{index + 1}. {str(choice.get('text') or '')[:60]}"
            draw.rounded_rectangle((right - 360, choice_top + index * 34, right - 28, choice_top + index * 34 + 26), radius=10, fill=(255, 255, 255, 24), outline=(255, 255, 255, 54), width=1)
            draw.text((right - 344, choice_top + 5 + index * 34), label, fill=(220, 226, 236, 255), font=self._font)

    def _wrap_text(self, text: str, max_chars: int) -> list[str]:
        words = str(text or "").split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if len(candidate) <= max_chars:
                current = candidate
                continue
            lines.append(current)
            current = word
        lines.append(current)
        return lines

    def _project(self, x: float, y: float, z: float, mode: RenderMode, pipeline: str) -> tuple[float, float]:
        if pipeline == "canvas_2d" and mode != RenderMode.RENDER_2D_ISOMETRIC:
            return (
                self.width * 0.5 + x * 90.0,
                self.height * 0.62 - y * 90.0,
            )
        if mode == RenderMode.RENDER_2D_ISOMETRIC:
            return (
                self.width * 0.5 + (x - z) * 74.0,
                self.height * 0.62 - y * 74.0 - (x + z) * 20.0,
            )
        if mode == RenderMode.RENDER_3D:
            return (
                self.width * 0.5 + (x - z * 0.7) * 78.0,
                self.height * 0.62 - y * 78.0 - (x + z) * 15.0,
            )
        return (
            self.width * 0.5 + x * 90.0,
            self.height * 0.62 - y * 90.0,
        )


def _encode_video(ffmpeg_path: str, frames_dir: Path, output_path: Path, *, fps: int, format_name: str) -> subprocess.CompletedProcess[str]:
    input_pattern = str((frames_dir / "frame_%05d.png").resolve())
    command = [
        ffmpeg_path,
        "-y",
        "-framerate",
        str(max(1, fps)),
        "-i",
        input_pattern,
    ]
    if format_name == "mp4":
        command.extend(["-pix_fmt", "yuv420p", str(output_path.resolve())])
    elif format_name == "gif":
        command.extend([str(output_path.resolve())])
    else:
        raise ValueError(f"Unsupported video format: {format_name}")
    return subprocess.run(command, capture_output=True, text=True, check=False)


def export_project_video(
    project_root: str | Path,
    *,
    scene_path: str | Path | None = None,
    format_name: str = "mp4",
    output_path: str | Path | None = None,
    fps: int | None = None,
    frames: int | None = None,
    width: int = 1280,
    height: int = 720,
    frame_stride: int = 1,
    input_script: Optional[list[dict[str, Any]]] = None,
) -> Dict[str, Any]:
    project_root = Path(project_root).resolve()
    config = load_engine_config(project_root)
    tree, _, config_dict = load_project_scene(project_root, scene_path)
    runtime = dict(config_dict.get("runtime") or {})
    output_format = str(format_name or "mp4").strip().lower()
    if output_format not in {"mp4", "gif", "frames"}:
        raise ValueError("format_name must be one of: mp4, gif, frames")

    title = str(runtime.get("window_title") or config.project_name or project_root.name)
    run_name = _slugify(title)
    output_root = project_root / "playtest/renders/video"
    output_root.mkdir(parents=True, exist_ok=True)

    if output_path:
        resolved_output = Path(output_path)
        if not resolved_output.is_absolute():
            resolved_output = (project_root / resolved_output).resolve()
    else:
        suffix = ".mp4" if output_format == "mp4" else (".gif" if output_format == "gif" else "")
        resolved_output = (output_root / f"{run_name}{suffix}").resolve() if suffix else (output_root / run_name).resolve()

    frames_dir = (resolved_output.parent / f"{resolved_output.stem}_frames").resolve()
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.glob("frame_*.png"):
        stale.unlink()

    input_events = input_script if input_script is not None else _load_default_input_script(project_root)
    requested_frames = int(frames or config.runtime.deterministic_smoke_frames)
    effective_fps = int(fps or runtime.get("target_fps") or 30)
    effective_stride = max(1, int(frame_stride))
    renderer = PlayblastFrameRenderer(width=width, height=height)
    manifest_frames: list[Dict[str, Any]] = []

    app = EngineLiteApp(
        tree,
        profile=RuntimeProfile(
            title=title,
            width=width,
            height=height,
            target_fps=max(1, effective_fps),
            headless=True,
            fixed_step=float(runtime.get("fixed_step", 1.0 / max(1, effective_fps))),
        ),
        config=config_dict,
    )

    def _capture_frame(frame_index: int, frame: RenderFrame, payload: Dict[str, Any]) -> None:
        if frame_index % effective_stride != 0:
            return
        image = renderer.render(
            frame,
            title=title,
            dialogue_view=dict(payload.get("dialogue") or {}),
            world_state=dict(payload.get("world_state") or {}),
            telemetry_events=_safe_int(payload.get("telemetry_events"), 0),
        )
        frame_path = frames_dir / f"frame_{len(manifest_frames):05d}.png"
        image.save(frame_path, format="PNG")
        manifest_frames.append(
            {
                "frame_index": frame_index,
                "image": str(frame_path),
                "draw_calls": frame.draw_calls,
                "mode": frame.mode.value,
                "active_camera": frame.active_camera,
                "dialogue": dict(payload.get("dialogue") or {}),
            }
        )

    summary = app.run_with_observer(frames=requested_frames, input_script=input_events, frame_observer=_capture_frame)
    telemetry_path = app.telemetry.flush(output_root / f"{run_name}_telemetry.json")

    encoded = False
    ffmpeg_path = discover_ffmpeg()
    ffmpeg_output = ""
    ffmpeg_error = ""
    if output_format in {"mp4", "gif"} and ffmpeg_path:
        result = _encode_video(ffmpeg_path, frames_dir, resolved_output, fps=max(1, effective_fps // effective_stride), format_name=output_format)
        ffmpeg_output = result.stdout.strip()
        ffmpeg_error = result.stderr.strip()
        encoded = result.returncode == 0 and resolved_output.exists()
    elif output_format in {"mp4", "gif"}:
        ffmpeg_error = "ffmpeg was not found; exported frames only"

    manifest_path = output_root / f"{run_name}_manifest.json"
    manifest = {
        "project_root": str(project_root),
        "title": title,
        "format": output_format,
        "fps": effective_fps,
        "frame_stride": effective_stride,
        "requested_frames": requested_frames,
        "captured_frames": len(manifest_frames),
        "frames_dir": str(frames_dir),
        "output_path": str(resolved_output) if output_format in {"mp4", "gif"} else "",
        "telemetry_path": str(telemetry_path),
        "ffmpeg_path": ffmpeg_path,
        "encoded": encoded,
        "summary": summary,
        "frames": manifest_frames,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "success": True,
        "format": output_format,
        "frames_dir": str(frames_dir),
        "frame_count": len(manifest_frames),
        "output_path": str(resolved_output) if output_format in {"mp4", "gif"} else "",
        "telemetry_path": str(telemetry_path),
        "manifest_path": str(manifest_path),
        "ffmpeg_path": ffmpeg_path,
        "encoded": encoded,
        "ffmpeg_output": ffmpeg_output,
        "ffmpeg_error": ffmpeg_error,
        "summary": summary,
    }


__all__ = [
    "PlayblastFrameRenderer",
    "VideoExportSettings",
    "discover_ffmpeg",
    "export_project_video",
]
