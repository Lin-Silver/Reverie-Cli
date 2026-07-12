"""Runtime loop and smoke execution for Reverie Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional
import json
import time
import uuid

try:
    import pyglet  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pyglet = None

try:
    import moderngl  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    moderngl = None

try:
    import glcontext  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    glcontext = None

from .components import ColliderComponent, RigidBodyComponent
from .config import ENGINE_NAME, load_engine_config, discover_live2d_sdk, supported_game_families
from .live2d import Live2DManager
from .math3d import Vector2, Vector3
from .modeling import detect_modeling_stack
from .physics import collect_overlaps, move_kinematic, raycast, PhysicsWorld
from .resources import ResourceManager
from .scene import SceneTree
from .serialization import load_scene
from .systems import GameplayDirector
from .telemetry import TelemetryRecorder
from .input import InputManager
from .audio import AudioManager
from .animation import SequenceDirector
from .localization import LocalizationManager
from .rendering import Renderer, RenderMode
from .save_data import SaveDataManager
from .ui import UISystem


@dataclass
class EngineRuntimeProfile:
    title: str = "Reverie Engine"
    width: int = 1280
    height: int = 720
    target_fps: int = 60
    headless: bool = True
    fixed_step: float = 1.0 / 60.0


# Compatibility alias for integrations written before the domain-specific name.
RuntimeProfile = EngineRuntimeProfile


def runtime_capabilities(project_root: str | Path | None = None) -> Dict[str, Any]:
    from .video import discover_ffmpeg

    sdk_path = discover_live2d_sdk(project_root or Path.cwd())
    modeling_stack = detect_modeling_stack(project_root or Path.cwd())
    ashfox = modeling_stack["ashfox"]
    blockbench = modeling_stack["blockbench"]
    ffmpeg_path = discover_ffmpeg()
    native_render_dependencies = moderngl is not None and glcontext is not None
    return {
        "engine": ENGINE_NAME,
        "unified_runtime": True,
        "maturity": "alpha",
        "dimensions": ["2D", "2.5D", "3D"],
        "game_families": [item["id"] for item in supported_game_families()],
        "scope_exclusions": ["AAA/3A production", "3D open-world games"],
        "systems": [
            "scene_graph",
            "components",
            "signals",
            "2d_and_3d_rendering",
            "physics_and_queries",
            "navigation",
            "input",
            "animation_and_timeline",
            "audio",
            "ui",
            "localization",
            "save_data",
            "telemetry",
            "live2d",
            "asset_pipeline",
            "headless_verification",
        ],
        "capability_levels": {
            "scene_graph": "runtime",
            "physics_and_queries": "runtime",
            "navigation": "runtime",
            "input": "runtime",
            "animation_and_timeline": "runtime",
            "save_data": "runtime",
            "headless_verification": "runtime",
            "native_rendering": "available" if native_render_dependencies else "dependency-missing",
            "audio": "installed-unverified" if pyglet is not None else "dependency-missing",
            "live2d": "browser-bridge" if sdk_path is not None else "asset-contract-only",
            "game_production": "work-in-progress",
        },
        "pyglet": pyglet is not None,
        "moderngl": moderngl is not None,
        "glcontext": glcontext is not None,
        "live2d_sdk": sdk_path is not None,
        "blockbench_installed": bool(blockbench.get("installed", False)),
        "blockbench_available": bool(blockbench.get("available", False)),
        "ashfox_available": bool(ashfox.get("available", False)),
        "ashfox_connected": bool(ashfox.get("reachable", False)),
        "ashfox_tool_count": int(ashfox.get("tool_count", 0)),
        "ffmpeg_available": bool(ffmpeg_path),
        "ffmpeg_path": ffmpeg_path,
    }


@dataclass
class ReverieEngineApp:
    scene_tree: SceneTree
    profile: EngineRuntimeProfile = field(default_factory=EngineRuntimeProfile)
    telemetry: TelemetryRecorder = field(
        default_factory=lambda: TelemetryRecorder(session_id=f"engine-{uuid.uuid4().hex[:8]}")
    )
    physics_world: PhysicsWorld = field(default_factory=PhysicsWorld)
    input_manager: InputManager = field(default_factory=InputManager)
    config: Optional[Dict[str, Any]] = None
    audio_manager: Optional[AudioManager] = None
    renderer: Optional[Renderer] = None
    live2d_manager: Optional[Live2DManager] = None
    gameplay: Optional[GameplayDirector] = None
    sequence_director: Optional[SequenceDirector] = None
    ui_system: Optional[UISystem] = None
    localization_manager: Optional[LocalizationManager] = None
    save_data_manager: Optional[SaveDataManager] = None

    def __post_init__(self) -> None:
        self.scene_tree.telemetry = self.telemetry
        self.scene_tree.config = self.config or self.scene_tree.config

        # Initialize audio if available
        if hasattr(self.scene_tree, "resource_manager") and self.scene_tree.resource_manager:
            self.audio_manager = AudioManager(self.scene_tree.resource_manager.project_root)
            self.localization_manager = LocalizationManager(self.scene_tree.resource_manager.project_root)
            self.save_data_manager = SaveDataManager(self.scene_tree.resource_manager.project_root)
            self.scene_tree.localization_manager = self.localization_manager
            self.scene_tree.save_data_manager = self.save_data_manager

        if hasattr(self.scene_tree, "resource_manager") and self.scene_tree.resource_manager:
            self.live2d_manager = Live2DManager(self.scene_tree.resource_manager.project_root)
            self.gameplay = GameplayDirector(
                self.scene_tree,
                self.scene_tree.resource_manager,
                self.telemetry,
                config=self.config or {},
                live2d=self.live2d_manager,
                localization=self.localization_manager,
                audio_manager=self.audio_manager,
            )
        self.sequence_director = SequenceDirector(self.scene_tree, self.telemetry, gameplay=self.gameplay)
        self.ui_system = UISystem(self.scene_tree, gameplay=self.gameplay)
        self.scene_tree.ui_system = self.ui_system

        # Initialize renderer for both headless smoke runs and native sessions.
        dimension = str(
            (self.config or {}).get("project", {}).get("dimension")
            or self.scene_tree.root.metadata.get("dimension")
            or "2D"
        )
        render_mode = (
            RenderMode.RENDER_3D
            if dimension == "3D"
            else (RenderMode.RENDER_2D_ISOMETRIC if dimension == "2.5D" else RenderMode.RENDER_2D)
        )
        resource_manager = getattr(self.scene_tree, "resource_manager", None)
        asset_root = resource_manager.project_root if resource_manager else None
        self.renderer = Renderer(render_mode, headless=self.profile.headless, asset_root=asset_root)
        self.renderer.initialize()

        # Add rigid bodies to physics world
        for node in self.scene_tree.iter_nodes():
            rb = node.get_component("RigidBody")
            if isinstance(rb, RigidBodyComponent):
                self.physics_world.add_body(node)

    def run(self, *, frames: int = 180, input_script: Optional[list[dict]] = None) -> Dict[str, Any]:
        return self.run_with_observer(frames=frames, input_script=input_script, frame_observer=None)

    def run_with_observer(
        self,
        *,
        frames: int = 180,
        input_script: Optional[list[dict]] = None,
        frame_observer: Optional[Callable[[int, Any, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        renderer = self.renderer.backend.value if self.renderer else ("native" if (not self.profile.headless and pyglet is not None) else "headless")
        self.telemetry.log_event(
            "session_start",
            entry_point=self.scene_tree.root.scene_id,
            renderer=renderer,
            genre=(self.config or {}).get("project", {}).get("genre", ""),
        )

        if self.gameplay:
            self.gameplay.bootstrap()
        if self.sequence_director:
            self.sequence_director.bootstrap()
        if self.ui_system:
            self.ui_system.update(Vector2(self.profile.width, self.profile.height), frame_index=0)

        loop_started_at = time.perf_counter()
        for frame_index in range(frames):
            delta = 1.0 / self.profile.target_fps

            # Update input
            self.input_manager.update()
            self._apply_input(frame_index, input_script or [])

            # Update scene tree
            self.scene_tree.step(delta, frame_index=frame_index)

            # Physics simulation
            self.physics_world.step(delta)
            collisions = self.physics_world.resolve_collisions()
            for collision in collisions:
                self.telemetry.log_event(
                    "physics_collision",
                    collision_type="physics",
                    target=collision.node_name,
                    layer=collision.layer,
                    depth=collision.depth
                )

            # Process game logic
            self._process_builtin_interactions(frame_index)
            if self.gameplay:
                self.gameplay.update(frame_index, delta)
            if self.sequence_director:
                self.sequence_director.update(delta, frame_index)

            if self.ui_system:
                self.ui_system.update(Vector2(self.profile.width, self.profile.height), frame_index=frame_index)

            # Update audio
            if self.audio_manager:
                self.audio_manager.update(delta)

            # Render frame
            if self.renderer:
                frame_snapshot = self.renderer.render_frame(self.scene_tree, frame_index=frame_index)
                if frame_observer is not None:
                    payload = {
                        "dialogue": self.gameplay.get_active_dialogue_view() if self.gameplay else {},
                        "world_state": self.gameplay.state.summary() if self.gameplay else {},
                        "telemetry_events": len(self.telemetry.events),
                    }
                    frame_observer(frame_index, frame_snapshot, payload)

            # Checkpoints
            if frame_index in {0, frames // 2, frames - 1}:
                self.telemetry.log_event(
                    "checkpoint",
                    checkpoint_id=f"frame_{frame_index}",
                    elapsed_seconds=frame_index / self.profile.target_fps,
                )

        elapsed_seconds = max(0.0, time.perf_counter() - loop_started_at)
        self.telemetry.increment("frames_executed", frames)
        self.telemetry.metrics["frame_time_ms_average"] = (
            (elapsed_seconds * 1000.0) / frames if frames > 0 else 0.0
        )
        self.telemetry.metrics["runtime_elapsed_seconds"] = elapsed_seconds

        if self.save_data_manager and self.profile.headless:
            save_path = self.save_data_manager.save_slot(
                "smoke_autosave",
                self.scene_tree,
                gameplay=self.gameplay,
                localization=self.localization_manager,
                metadata={"purpose": "deterministic_smoke", "frames": frames},
            )
            self.telemetry.log_event("save_written", slot="smoke_autosave", path=str(save_path))
            loaded_save = self.save_data_manager.load_slot("smoke_autosave")
            if int(loaded_save.get("version", 0) or 0) != 1:
                raise RuntimeError("Smoke save round-trip returned an unsupported save version")
            self.telemetry.log_event(
                "save_roundtrip_verified",
                slot="smoke_autosave",
                frame_index=int(loaded_save.get("frame_index", 0) or 0),
            )

        self.telemetry.log_event(
            "session_end",
            duration_seconds=frames / self.profile.target_fps,
            result="completed",
            quit_reason="smoke_finished",
        )

        rendering_summary = self.renderer.summary() if self.renderer else {}
        audio_summary = self.audio_manager.summary() if self.audio_manager else {}

        # Cleanup
        if self.renderer:
            self.renderer.shutdown()
        if self.audio_manager:
            self.audio_manager.cleanup()

        summary = self.telemetry.summary()
        if self.gameplay:
            summary["world_state"] = self.gameplay.state.summary()
        if rendering_summary:
            summary["rendering"] = rendering_summary
        if self.sequence_director:
            summary["sequencing"] = self.sequence_director.summary()
        if self.ui_system:
            summary["ui"] = self.ui_system.summary()
        if self.localization_manager:
            summary["localization"] = self.localization_manager.summary()
        if self.save_data_manager:
            summary["save_data"] = {"slots": self.save_data_manager.list_slots()}
        if audio_summary:
            summary["audio"] = audio_summary
        return summary

    def _apply_input(self, frame_index: int, script: Iterable[dict]) -> None:
        for action in script:
            start = int(action.get("from_frame", action.get("frame", -1)))
            end = int(action.get("to_frame", start))
            if frame_index < start or frame_index > end:
                continue
            node_name = str(action.get("node", "")).strip()
            node = self.scene_tree.find(node_name) if node_name else None

            if "move" in action and node is not None:
                move = Vector3.from_any(action.get("move"))
                blockers = [
                    candidate
                    for candidate in self.scene_tree.iter_nodes()
                    if candidate is not node and isinstance(candidate.get_component("Collider"), ColliderComponent)
                ]
                collisions = move_kinematic(node, move, blockers)
                for collision in collisions:
                    self.telemetry.log_event(
                        "collision",
                        node=node.name,
                        target=collision.node_name,
                        layer=collision.layer,
                        is_trigger=collision.is_trigger,
                    )
                    if self.gameplay:
                        target_node = self.scene_tree.find(collision.node_name)
                        if target_node:
                            self.gameplay.handle_overlap(node, target_node, source="move")

            if str(action.get("action", "")).strip() == "interact" and node is not None:
                direction = Vector3.from_any(action.get("direction") or [1, 0, 0])
                result = raycast(self.scene_tree.iter_nodes(), node.world_transform().position, direction)
                if result:
                    self.telemetry.log_event("ray_interact", node=node.name, target=result.node_name, layer=result.layer)
                    if self.gameplay:
                        self.gameplay.handle_interaction(node, self.scene_tree.find(result.node_name))
            elif self.gameplay and str(action.get("action", "")).strip():
                self.gameplay.handle_input_action(action, frame_index)

    def _process_builtin_interactions(self, frame_index: int) -> None:
        players = [node for node in self.scene_tree.iter_nodes() if "player" in node.tags]
        collidable_nodes = [
            node
            for node in self.scene_tree.iter_nodes()
            if isinstance(node.get_component("Collider"), ColliderComponent)
        ]
        for player in players:
            overlaps = collect_overlaps(player, collidable_nodes)
            for collision in overlaps:
                target = self.scene_tree.find(collision.node_name)
                if self.gameplay and target:
                    self.gameplay.handle_overlap(player, target, source=f"frame:{frame_index}")
                if collision.layer == "enemy":
                    self.telemetry.log_event("encounter_started", player=player.name, target=collision.node_name)


def load_project_scene(project_root: Path, scene_path: str | Path | None = None) -> tuple[SceneTree, ResourceManager, Dict[str, Any]]:
    project_root = Path(project_root)
    target_scene = Path(scene_path) if scene_path else project_root / "data/scenes/main.relscene.json"
    if not target_scene.is_absolute():
        target_scene = project_root / target_scene
    config = load_engine_config(project_root).to_dict()
    scene = load_scene(target_scene)
    resources = ResourceManager(project_root)
    tree = SceneTree(root=scene, resource_manager=resources, config=config)
    return tree, resources, config


def run_project(
    project_root: Path,
    *,
    scene_path: str | Path | None = None,
    headless: bool = True,
    frames: int = 180,
    input_script: Optional[list[dict]] = None,
    output_log: str | Path | None = None,
    frame_observer: Optional[Callable[[int, Any, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    tree, resources, config = load_project_scene(project_root, scene_path)
    runtime = dict(config.get("runtime") or {})
    profile = EngineRuntimeProfile(
        title=str(runtime.get("window_title") or "Reverie Engine"),
        target_fps=int(runtime.get("target_fps", 60)),
        headless=headless,
        fixed_step=float(runtime.get("fixed_step", 1.0 / 60.0)),
    )
    app = ReverieEngineApp(tree, profile=profile, config=config)
    summary = app.run_with_observer(frames=frames, input_script=input_script, frame_observer=frame_observer)
    log_path = None
    if output_log:
        log_path = app.telemetry.flush(output_log)
    return {
        "success": True,
        "summary": summary,
        "log_path": str(log_path) if log_path else "",
        "resources": resources.summary(),
        "capabilities": runtime_capabilities(project_root),
        "engine_config": config,
    }


def run_project_smoke(project_root: Path, *, scene_path: str | Path | None = None, output_log: str | Path | None = None) -> Dict[str, Any]:
    project_root = Path(project_root)
    config = load_engine_config(project_root)
    input_path = project_root / "playtest/logs/input_script.json"
    inputs: list[dict] = []
    if input_path.exists():
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("inputs"), list):
            inputs = [item for item in payload["inputs"] if isinstance(item, dict)]
    log_path = output_log or (project_root / "playtest/logs/engine_smoke.json")
    return run_project(
        project_root,
        scene_path=scene_path,
        headless=True,
        frames=config.runtime.deterministic_smoke_frames,
        input_script=inputs,
        output_log=log_path,
    )
