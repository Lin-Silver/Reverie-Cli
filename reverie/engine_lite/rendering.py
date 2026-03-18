"""Server-style rendering orchestration for Reverie Engine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, TYPE_CHECKING

try:
    import pyglet
    from pyglet import gl
except ImportError:  # pragma: no cover - optional dependency
    pyglet = None
    gl = None

try:
    import moderngl
except ImportError:  # pragma: no cover - optional dependency
    moderngl = None

from .components import (
    ButtonComponent,
    Camera2DComponent,
    Camera3DComponent,
    ChoiceListComponent,
    DialogueBoxComponent,
    ImageComponent,
    LightComponent,
    MeshComponent,
    ParallaxLayerComponent,
    ParticleSystemComponent,
    PanelComponent,
    ProgressBarComponent,
    ResourceBarComponent,
    SpriteComponent,
    TextLabelComponent,
    TileMapComponent,
    TowerBuildPanelComponent,
    UIControlComponent,
)
from .math3d import Matrix4, Transform, Vector2, Vector3, Vector4

if TYPE_CHECKING:
    from .scene import Node, SceneTree


class RenderMode(Enum):
    """Rendering modes for different game types."""

    RENDER_2D = "2d"
    RENDER_2D_ISOMETRIC = "2.5d"
    RENDER_3D = "3d"


class RenderBackend(Enum):
    """Backends supported by the renderer."""

    HEADLESS = "headless"
    NATIVE = "native"


class BlendMode(Enum):
    """Blend modes for sprite and material rendering."""

    MIX = "mix"
    ADD = "add"
    MULTIPLY = "multiply"
    SUBTRACT = "subtract"


@dataclass
class Viewport:
    """Rendering viewport configuration."""

    width: int = 1280
    height: int = 720
    clear_color: Vector4 = field(default_factory=lambda: Vector4(0.1, 0.1, 0.1, 1.0))
    msaa: int = 0
    hdr: bool = False
    name: str = "main"

    def aspect_ratio(self) -> float:
        return self.width / max(self.height, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "clear_color": self.clear_color.to_list(),
            "msaa": self.msaa,
            "hdr": self.hdr,
        }


@dataclass
class Camera:
    """Base camera class."""

    transform: Transform = field(default_factory=Transform)
    current: bool = True

    def get_projection_matrix(self, viewport: Viewport) -> Matrix4:
        return Matrix4.identity()

    def get_view_matrix(self) -> Matrix4:
        return self.transform.to_matrix().inverse()


@dataclass
class Camera2D(Camera):
    """2D camera with zoom and offset."""

    zoom: Vector2 = field(default_factory=lambda: Vector2(1.0, 1.0))
    offset: Vector2 = field(default_factory=Vector2)
    rotation: float = 0.0
    smoothing_enabled: bool = False
    smoothing_speed: float = 5.0

    def get_projection_matrix(self, viewport: Viewport) -> Matrix4:
        half_width = viewport.width / (2.0 * max(self.zoom.x, 0.0001))
        half_height = viewport.height / (2.0 * max(self.zoom.y, 0.0001))
        return Matrix4.orthographic(-half_width, half_width, -half_height, half_height, -1000, 1000)


@dataclass
class Camera3D(Camera):
    """3D perspective camera."""

    fov: float = 70.0
    near: float = 0.1
    far: float = 1000.0

    def get_projection_matrix(self, viewport: Viewport) -> Matrix4:
        aspect = viewport.aspect_ratio()
        fov_rad = math.radians(self.fov)
        return Matrix4.perspective(fov_rad, aspect, self.near, self.far)


@dataclass
class Material:
    """Material properties for rendering."""

    shader: str = "default"
    albedo_color: Vector4 = field(default_factory=lambda: Vector4(1.0, 1.0, 1.0, 1.0))
    albedo_texture: str = ""
    metallic: float = 0.0
    roughness: float = 1.0
    emission: Vector3 = field(default_factory=Vector3)
    emission_energy: float = 1.0
    blend_mode: BlendMode = BlendMode.MIX
    cull_mode: str = "back"
    depth_test: bool = True
    transparent: bool = False
    unshaded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shader": self.shader,
            "albedo_color": self.albedo_color.to_list(),
            "albedo_texture": self.albedo_texture,
            "metallic": self.metallic,
            "roughness": self.roughness,
            "emission": self.emission.to_list(),
            "emission_energy": self.emission_energy,
            "blend_mode": self.blend_mode.value,
            "cull_mode": self.cull_mode,
            "depth_test": self.depth_test,
            "transparent": self.transparent,
            "unshaded": self.unshaded,
        }


@dataclass
class Light:
    """Base light class."""

    color: Vector3 = field(default_factory=lambda: Vector3(1.0, 1.0, 1.0))
    energy: float = 1.0
    enabled: bool = True
    shadow_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "color": self.color.to_list(),
            "energy": self.energy,
            "enabled": self.enabled,
            "shadow_enabled": self.shadow_enabled,
        }


@dataclass
class DirectionalLight(Light):
    """Directional light (sun/moon)."""

    direction: Vector3 = field(default_factory=lambda: Vector3(0.0, -1.0, 0.0))

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["direction"] = self.direction.to_list()
        return payload


@dataclass
class PointLight(Light):
    """Point light with attenuation."""

    position: Vector3 = field(default_factory=Vector3)
    range: float = 10.0
    attenuation: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["position"] = self.position.to_list()
        payload["range"] = self.range
        payload["attenuation"] = self.attenuation
        return payload


@dataclass
class SpotLight(Light):
    """Spot light with cone."""

    position: Vector3 = field(default_factory=Vector3)
    direction: Vector3 = field(default_factory=lambda: Vector3(0.0, -1.0, 0.0))
    range: float = 10.0
    spot_angle: float = 45.0
    spot_attenuation: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["position"] = self.position.to_list()
        payload["direction"] = self.direction.to_list()
        payload["range"] = self.range
        payload["spot_angle"] = self.spot_angle
        payload["spot_attenuation"] = self.spot_attenuation
        return payload


@dataclass
class RenderCommand:
    """A single render command emitted by the scene sync stage."""

    source_node: str
    primitive: str
    pipeline: str
    mesh_id: str
    material: Material
    transform: Transform
    layer: int = 0
    z_index: int = 0
    sort_key: float = 0.0
    visible: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def sort_tuple(self) -> tuple[Any, ...]:
        transparent = 1 if self.material.transparent else 0
        return (
            self.layer,
            self.z_index,
            transparent,
            round(float(self.sort_key), 6),
            self.source_node,
            self.primitive,
            self.mesh_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_node": self.source_node,
            "primitive": self.primitive,
            "pipeline": self.pipeline,
            "mesh_id": self.mesh_id,
            "layer": self.layer,
            "z_index": self.z_index,
            "sort_key": self.sort_key,
            "visible": self.visible,
            "material": self.material.to_dict(),
            "transform": self.transform.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass
class CanvasLayerState:
    """Collected 2D canvas commands for one layer."""

    layer: int
    commands: List[RenderCommand] = field(default_factory=list)


@dataclass
class World3DState:
    """Collected 3D world instances and lights."""

    commands: List[RenderCommand] = field(default_factory=list)
    lights: List[Light] = field(default_factory=list)


@dataclass
class RenderFrame:
    """Deterministic frame snapshot returned by the rendering server."""

    frame_index: int
    mode: RenderMode
    backend: RenderBackend
    viewport: Viewport
    active_camera: str
    draw_calls: int
    light_count: int
    command_breakdown: Dict[str, int]
    primitive_breakdown: Dict[str, int]
    commands: List[RenderCommand] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "mode": self.mode.value,
            "backend": self.backend.value,
            "viewport": self.viewport.to_dict(),
            "active_camera": self.active_camera,
            "draw_calls": self.draw_calls,
            "light_count": self.light_count,
            "command_breakdown": dict(self.command_breakdown),
            "primitive_breakdown": dict(self.primitive_breakdown),
            "commands": [command.to_dict() for command in self.commands],
        }


class RenderingServer:
    """Godot-inspired rendering server with viewport, canvas, and world layers."""

    def __init__(
        self,
        mode: RenderMode = RenderMode.RENDER_2D,
        *,
        headless: bool = True,
    ) -> None:
        self.mode = mode
        self.viewport = Viewport()
        self.backend = RenderBackend.HEADLESS if headless else RenderBackend.NATIVE
        self.active_camera: Optional[Camera] = None
        self.ctx: Optional[Any] = None
        self._initialized = False
        self._canvas_layers: Dict[int, CanvasLayerState] = {}
        self._ui_commands: List[RenderCommand] = []
        self._world = World3DState()
        self._frame_history: List[RenderFrame] = []

    def initialize(self) -> bool:
        """Initialize the selected backend, falling back to headless when needed."""
        if self._initialized:
            return True

        if self.backend == RenderBackend.HEADLESS:
            self._initialized = True
            return True

        if moderngl is None:
            self.backend = RenderBackend.HEADLESS
            self._initialized = True
            return True

        try:
            self.ctx = moderngl.create_standalone_context()
            self._initialized = True
            return True
        except Exception:
            self.backend = RenderBackend.HEADLESS
            self.ctx = None
            self._initialized = True
            return True

    def begin_frame(self) -> None:
        self._canvas_layers.clear()
        self._ui_commands.clear()
        self._world = World3DState()
        self.active_camera = None

    def set_viewport(self, width: int, height: int, *, name: str | None = None) -> None:
        self.viewport.width = max(int(width), 1)
        self.viewport.height = max(int(height), 1)
        if name:
            self.viewport.name = str(name)

    def set_camera(self, camera: Camera) -> None:
        self.active_camera = camera

    def add_light(self, light: Light) -> None:
        if isinstance(light, Light):
            self._world.lights.append(light)

    def clear_lights(self) -> None:
        self._world.lights.clear()

    def submit(self, command: RenderCommand) -> None:
        pipeline = str(command.pipeline).strip().lower()
        if pipeline == "canvas_2d":
            layer_state = self._canvas_layers.setdefault(command.layer, CanvasLayerState(layer=command.layer))
            layer_state.commands.append(command)
            return
        if pipeline == "ui":
            self._ui_commands.append(command)
            return
        self._world.commands.append(command)

    def pending_commands(self) -> List[RenderCommand]:
        commands: List[RenderCommand] = []
        for layer in sorted(self._canvas_layers):
            commands.extend(self._canvas_layers[layer].commands)
        commands.extend(self._world.commands)
        commands.extend(self._ui_commands)
        return commands

    def last_frame(self) -> Optional[RenderFrame]:
        return self._frame_history[-1] if self._frame_history else None

    def render_frame(self, frame_index: int = 0) -> RenderFrame:
        self.initialize()
        ordered_commands = self._ordered_commands()

        if self.backend == RenderBackend.NATIVE and self.ctx is not None:
            self.ctx.clear(
                self.viewport.clear_color.x,
                self.viewport.clear_color.y,
                self.viewport.clear_color.z,
                self.viewport.clear_color.w,
            )
            projection = (
                self.active_camera.get_projection_matrix(self.viewport)
                if self.active_camera is not None
                else Matrix4.identity()
            )
            view = self.active_camera.get_view_matrix() if self.active_camera is not None else Matrix4.identity()
            for command in ordered_commands:
                self._render_command(command, projection, view)

        command_breakdown: Dict[str, int] = defaultdict(int)
        primitive_breakdown: Dict[str, int] = defaultdict(int)
        for command in ordered_commands:
            command_breakdown[command.pipeline] += 1
            primitive_breakdown[command.primitive] += 1

        frame = RenderFrame(
            frame_index=int(frame_index),
            mode=self.mode,
            backend=self.backend,
            viewport=Viewport(
                width=self.viewport.width,
                height=self.viewport.height,
                clear_color=self.viewport.clear_color,
                msaa=self.viewport.msaa,
                hdr=self.viewport.hdr,
                name=self.viewport.name,
            ),
            active_camera=self.active_camera.__class__.__name__ if self.active_camera else "",
            draw_calls=len(ordered_commands),
            light_count=len(self._world.lights),
            command_breakdown=dict(command_breakdown),
            primitive_breakdown=dict(primitive_breakdown),
            commands=ordered_commands,
        )
        self._frame_history.append(frame)
        if len(self._frame_history) > 120:
            self._frame_history.pop(0)

        self.begin_frame()
        return frame

    def frame_summary(self) -> Dict[str, Any]:
        last = self.last_frame()
        return {
            "initialized": self._initialized,
            "backend": self.backend.value,
            "mode": self.mode.value,
            "frame_count": len(self._frame_history),
            "viewport": self.viewport.to_dict(),
            "last_frame": last.to_dict() if last else {},
        }

    def shutdown(self) -> None:
        if self.ctx is not None:
            self.ctx.release()
            self.ctx = None
        self._initialized = False
        self.begin_frame()

    def _pipeline_order(self, pipeline: str) -> int:
        if self.mode == RenderMode.RENDER_3D:
            order = {"world_3d": 0, "canvas_2d": 1, "ui": 2}
        else:
            order = {"canvas_2d": 0, "world_3d": 1, "ui": 2}
        return order.get(str(pipeline).strip().lower(), 99)

    def _ordered_commands(self) -> List[RenderCommand]:
        canvas_commands: List[RenderCommand] = []
        for layer in sorted(self._canvas_layers):
            canvas_commands.extend(sorted(self._canvas_layers[layer].commands, key=lambda item: item.sort_tuple()))
        world_commands = sorted(self._world.commands, key=lambda item: item.sort_tuple())
        ui_commands = sorted(self._ui_commands, key=lambda item: item.sort_tuple())
        grouped = {
            "canvas_2d": canvas_commands,
            "world_3d": world_commands,
            "ui": ui_commands,
        }
        ordered: List[RenderCommand] = []
        for pipeline in sorted(grouped, key=self._pipeline_order):
            ordered.extend(grouped[pipeline])
        return ordered

    def _render_command(self, command: RenderCommand, projection: Matrix4, view: Matrix4) -> None:
        """Native rendering hook. Left intentionally lightweight for now."""
        _ = (command, projection, view)


@dataclass
class Mesh:
    """Mesh data container."""

    vertices: List[float] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)
    normals: List[float] = field(default_factory=list)
    uvs: List[float] = field(default_factory=list)
    colors: List[float] = field(default_factory=list)

    @staticmethod
    def create_quad(size: Vector2 = Vector2(1.0, 1.0)) -> "Mesh":
        half_w = size.x / 2.0
        half_h = size.y / 2.0
        return Mesh(
            vertices=[
                -half_w,
                -half_h,
                0.0,
                half_w,
                -half_h,
                0.0,
                half_w,
                half_h,
                0.0,
                -half_w,
                half_h,
                0.0,
            ],
            indices=[0, 1, 2, 0, 2, 3],
            uvs=[0, 0, 1, 0, 1, 1, 0, 1],
        )

    @staticmethod
    def create_cube(size: float = 1.0) -> "Mesh":
        s = size / 2.0
        return Mesh(
            vertices=[
                -s, -s, s, s, -s, s, s, s, s, -s, s, s,
                -s, -s, -s, -s, s, -s, s, s, -s, s, -s, -s,
                -s, s, -s, -s, s, s, s, s, s, s, s, -s,
                -s, -s, -s, s, -s, -s, s, -s, s, -s, -s, s,
                s, -s, -s, s, s, -s, s, s, s, s, -s, s,
                -s, -s, -s, -s, -s, s, -s, s, s, -s, s, -s,
            ],
            indices=[
                0, 1, 2, 0, 2, 3,
                4, 5, 6, 4, 6, 7,
                8, 9, 10, 8, 10, 11,
                12, 13, 14, 12, 14, 15,
                16, 17, 18, 16, 18, 19,
                20, 21, 22, 20, 22, 23,
            ],
        )


class MeshLibrary:
    """Manages mesh resources."""

    def __init__(self):
        self._meshes: Dict[str, Mesh] = {}
        self._load_primitives()

    def _load_primitives(self) -> None:
        self._meshes["quad"] = Mesh.create_quad()
        self._meshes["cube"] = Mesh.create_cube()

    def get(self, mesh_id: str) -> Optional[Mesh]:
        return self._meshes.get(mesh_id)

    def register(self, mesh_id: str, mesh: Mesh) -> None:
        self._meshes[mesh_id] = mesh

    def unregister(self, mesh_id: str) -> None:
        self._meshes.pop(mesh_id, None)


class Renderer:
    """High-level renderer that synchronizes a scene tree into a rendering server."""

    def __init__(self, mode: RenderMode = RenderMode.RENDER_2D, *, headless: bool = True):
        self.mode = mode
        self.server = RenderingServer(mode, headless=headless)
        self.viewport = self.server.viewport
        self.mesh_library = MeshLibrary()

    @property
    def active_camera(self) -> Optional[Camera]:
        return self.server.active_camera

    @property
    def lights(self) -> List[Light]:
        return list(self.server._world.lights)

    @property
    def render_queue(self) -> List[RenderCommand]:
        return self.server.pending_commands()

    @property
    def backend(self) -> RenderBackend:
        return self.server.backend

    def initialize(self) -> bool:
        return self.server.initialize()

    def set_viewport(self, width: int, height: int) -> None:
        self.server.set_viewport(width, height)

    def set_camera(self, camera: Camera) -> None:
        self.server.set_camera(camera)

    def add_light(self, light: Light) -> None:
        self.server.add_light(light)

    def clear_lights(self) -> None:
        self.server.clear_lights()

    def submit(self, command: RenderCommand) -> None:
        self.server.submit(command)

    def synchronize_scene(self, scene_source: "SceneTree | Node") -> None:
        self.server.begin_frame()
        selected_camera: Optional[Camera] = None
        for node in self._iter_nodes(scene_source):
            camera = self._camera_from_node(node)
            if camera is not None and (selected_camera is None or camera.current):
                selected_camera = camera

            light = self._light_from_node(node)
            if light is not None:
                self.server.add_light(light)

            for command in self._commands_from_node(node):
                self.server.submit(command)

        if selected_camera is not None:
            self.server.set_camera(selected_camera)

    def render_frame(self, scene_source: "SceneTree | Node | None" = None, *, frame_index: int = 0) -> RenderFrame:
        if scene_source is not None:
            self.synchronize_scene(scene_source)
        return self.server.render_frame(frame_index=frame_index)

    def last_frame(self) -> Optional[RenderFrame]:
        return self.server.last_frame()

    def summary(self) -> Dict[str, Any]:
        return self.server.frame_summary()

    def shutdown(self) -> None:
        self.server.shutdown()

    def _iter_nodes(self, scene_source: "SceneTree | Node"):
        if hasattr(scene_source, "iter_nodes"):
            return scene_source.iter_nodes()
        if hasattr(scene_source, "walk"):
            return scene_source.walk()
        return []

    def _camera_from_node(self, node: "Node") -> Optional[Camera]:
        camera2d = node.get_component("Camera2D")
        if isinstance(camera2d, Camera2DComponent):
            if isinstance(camera2d.viewport, list) and len(camera2d.viewport) >= 2:
                self.server.set_viewport(int(camera2d.viewport[0]), int(camera2d.viewport[1]), name=node.name)
            is_current = bool(node.metadata.get("camera_current", self.server.active_camera is None))
            return Camera2D(
                transform=node.world_transform(),
                current=is_current,
                zoom=Vector2(float(camera2d.zoom), float(camera2d.zoom)),
                smoothing_enabled=bool(camera2d.smoothing > 0),
                smoothing_speed=float(camera2d.smoothing or 0.0),
            )

        camera3d = node.get_component("Camera3D")
        if isinstance(camera3d, Camera3DComponent):
            is_current = bool(node.metadata.get("camera_current", self.server.active_camera is None))
            return Camera3D(
                transform=node.world_transform(),
                current=is_current,
                fov=float(camera3d.fov),
                near=float(camera3d.near),
                far=float(camera3d.far),
            )

        return None

    def _light_from_node(self, node: "Node") -> Optional[Light]:
        light = node.get_component("Light")
        if not isinstance(light, LightComponent):
            return None

        color = Vector3.from_any(light.color)
        direction = self._direction_from_transform(node.world_transform())
        if light.light_type == "directional":
            return DirectionalLight(
                color=color,
                energy=float(light.intensity),
                enabled=bool(light.enabled),
                direction=direction,
            )
        if light.light_type == "spot":
            return SpotLight(
                color=color,
                energy=float(light.intensity),
                enabled=bool(light.enabled),
                position=node.world_transform().position,
                direction=direction,
                range=float(light.range),
            )
        return PointLight(
            color=color,
            energy=float(light.intensity),
            enabled=bool(light.enabled),
            position=node.world_transform().position,
            range=float(light.range),
        )

    def _commands_from_node(self, node: "Node") -> List[RenderCommand]:
        if not node.active:
            return []

        commands: List[RenderCommand] = []
        world_transform = node.world_transform()
        z_index = int(node.metadata.get("z_index", 0) or 0)

        sprite = node.get_component("Sprite")
        parallax = node.get_component("ParallaxLayer")
        if isinstance(sprite, SpriteComponent):
            is_billboard = bool(sprite.billboard) and self.mode == RenderMode.RENDER_3D
            is_parallax = isinstance(parallax, ParallaxLayerComponent)
            commands.append(
                RenderCommand(
                    source_node=node.node_path,
                    primitive="billboard_sprite" if is_billboard else ("parallax_sprite" if is_parallax else "sprite"),
                    pipeline="world_3d" if is_billboard else "canvas_2d",
                    mesh_id="quad",
                    material=Material(
                        shader="billboard_sprite" if is_billboard else ("parallax_sprite" if is_parallax else "sprite"),
                        albedo_texture=sprite.texture,
                        transparent=True,
                        unshaded=True,
                        depth_test=is_billboard,
                    ),
                    transform=world_transform,
                    layer=0 if is_billboard else self._layer_to_index("parallax" if is_parallax else sprite.layer),
                    z_index=z_index,
                    sort_key=float(world_transform.position.z) if is_billboard else self._canvas_sort_key(world_transform.position),
                    metadata={
                        "atlas": sprite.atlas,
                        "frame": sprite.frame,
                        "size": sprite.size.to_list(),
                        "billboard": sprite.billboard,
                        "parallax": isinstance(parallax, ParallaxLayerComponent),
                        "scroll_scale": parallax.scroll_scale.to_list() if isinstance(parallax, ParallaxLayerComponent) else [1.0, 1.0],
                        "offset": parallax.offset.to_list() if isinstance(parallax, ParallaxLayerComponent) else [0.0, 0.0],
                        "repeat": bool(parallax.repeat) if isinstance(parallax, ParallaxLayerComponent) else False,
                    },
                )
            )

        tilemap = node.get_component("TileMap")
        if isinstance(tilemap, TileMapComponent):
            is_parallax = isinstance(parallax, ParallaxLayerComponent)
            commands.append(
                RenderCommand(
                    source_node=node.node_path,
                    primitive="parallax_tilemap" if is_parallax else "tilemap",
                    pipeline="canvas_2d",
                    mesh_id="tilemap",
                    material=Material(
                        shader="parallax_tilemap" if is_parallax else "tilemap",
                        depth_test=False,
                        unshaded=True,
                    ),
                    transform=world_transform,
                    layer=self._layer_to_index("parallax" if is_parallax else node.metadata.get("layer", "world")),
                    z_index=z_index,
                    sort_key=self._canvas_sort_key(world_transform.position),
                    metadata={
                        "tileset": tilemap.tileset,
                        "cell_size": list(tilemap.cell_size),
                        "layers": list(tilemap.layers),
                        "parallax": is_parallax,
                        "scroll_scale": parallax.scroll_scale.to_list() if is_parallax else [1.0, 1.0],
                        "offset": parallax.offset.to_list() if is_parallax else [0.0, 0.0],
                        "repeat": bool(parallax.repeat) if is_parallax else False,
                    },
                )
            )

        mesh = node.get_component("Mesh")
        if isinstance(mesh, MeshComponent):
            if mesh.visible:
                commands.append(
                    RenderCommand(
                        source_node=node.node_path,
                        primitive="mesh",
                        pipeline="world_3d",
                        mesh_id=str(mesh.mesh or "cube"),
                        material=Material(
                            shader=str(mesh.material or "default"),
                            depth_test=True,
                        ),
                        transform=world_transform,
                        layer=0,
                        z_index=z_index,
                        sort_key=float(world_transform.position.z),
                        metadata={
                            "cast_shadow": mesh.cast_shadow,
                            "receive_shadow": mesh.receive_shadow,
                            "visible": mesh.visible,
                        },
                    )
                )

        particles = node.get_component("ParticleSystem")
        if isinstance(particles, ParticleSystemComponent) and particles.emitting:
            commands.append(
                RenderCommand(
                    source_node=node.node_path,
                    primitive="particles",
                    pipeline="world_3d" if self.mode == RenderMode.RENDER_3D else "canvas_2d",
                    mesh_id="quad",
                    material=Material(
                        shader="particles",
                        albedo_color=Vector4.from_any(particles.color),
                        transparent=True,
                        depth_test=self.mode == RenderMode.RENDER_3D,
                        unshaded=True,
                    ),
                    transform=world_transform,
                    layer=self._layer_to_index(node.metadata.get("layer", "effects")),
                    z_index=z_index,
                    sort_key=self._canvas_sort_key(world_transform.position),
                    metadata={
                        "amount": particles.amount,
                        "lifetime": particles.lifetime,
                        "speed": particles.speed,
                        "spread": particles.spread,
                    },
                )
            )

        ui = node.get_component("UIControl")
        label = node.get_component("TextLabel")
        panel = node.get_component("Panel")
        button = node.get_component("Button")
        image = node.get_component("Image")
        progress = node.get_component("ProgressBar")
        dialogue_box = node.get_component("DialogueBox")
        choice_list = node.get_component("ChoiceList")
        resource_bar = node.get_component("ResourceBar")
        build_panel = node.get_component("TowerBuildPanel")
        if any(
            isinstance(component, ComponentType)
            for component, ComponentType in [
                (ui, UIControlComponent),
                (label, TextLabelComponent),
                (panel, PanelComponent),
                (button, ButtonComponent),
                (image, ImageComponent),
                (progress, ProgressBarComponent),
                (dialogue_box, DialogueBoxComponent),
                (choice_list, ChoiceListComponent),
                (resource_bar, ResourceBarComponent),
                (build_panel, TowerBuildPanelComponent),
            ]
        ):
            visible = True if not isinstance(ui, UIControlComponent) else bool(ui.visible)
            if visible:
                rect = self._ui_rect_for_node(node)
                metadata: Dict[str, Any] = {"rect": rect, "clip_content": bool(ui.clip_content) if isinstance(ui, UIControlComponent) else False}
                primitive = "panel"
                if isinstance(label, TextLabelComponent):
                    primitive = "label"
                    metadata.update(
                        {
                            "text": label.text,
                            "font": label.font,
                            "font_size": label.font_size,
                            "align": label.align,
                            "valign": label.valign,
                            "color": list(label.color),
                        }
                    )
                if isinstance(panel, PanelComponent):
                    primitive = "panel"
                    metadata.update(
                        {
                            "style": panel.style,
                            "fill_color": list(panel.fill_color),
                            "border_color": list(panel.border_color),
                            "padding": list(panel.padding),
                        }
                    )
                if isinstance(button, ButtonComponent):
                    primitive = "button"
                    metadata.update(node.metadata.get("ui_button") or {})
                    metadata.setdefault("text", button.text)
                if isinstance(image, ImageComponent):
                    primitive = "image"
                    metadata.update({"texture": image.texture, "tint": list(image.tint), "stretch_mode": image.stretch_mode})
                if isinstance(progress, ProgressBarComponent):
                    primitive = "progress_bar"
                    maximum = max(float(progress.max_value), float(progress.min_value) + 0.00001)
                    ratio = (float(progress.value) - float(progress.min_value)) / (maximum - float(progress.min_value))
                    metadata.update(
                        {
                            "label": progress.label,
                            "min_value": progress.min_value,
                            "max_value": progress.max_value,
                            "value": progress.value,
                            "ratio": max(0.0, min(1.0, ratio)),
                            "fill_color": list(progress.fill_color),
                            "background_color": list(progress.background_color),
                            "show_percentage": progress.show_percentage,
                        }
                    )
                if isinstance(dialogue_box, DialogueBoxComponent):
                    primitive = "dialogue_box"
                    metadata.update(node.metadata.get("ui_dialogue") or {})
                if isinstance(choice_list, ChoiceListComponent):
                    primitive = "choice_list"
                    metadata.update({"choices": list(node.metadata.get("ui_choices") or [])})
                if isinstance(resource_bar, ResourceBarComponent):
                    primitive = "resource_bar"
                    metadata.update(node.metadata.get("ui_resource") or {})
                if isinstance(build_panel, TowerBuildPanelComponent):
                    primitive = "build_panel"
                    metadata.update(node.metadata.get("ui_build_panel") or {})
                commands.append(
                    RenderCommand(
                        source_node=node.node_path,
                        primitive=primitive,
                        pipeline="ui",
                        mesh_id="quad",
                        material=Material(shader="ui", transparent=True, unshaded=True, depth_test=False),
                        transform=world_transform,
                        layer=1000,
                        z_index=z_index,
                        sort_key=float(world_transform.position.z),
                        metadata=metadata,
                    )
                )

        return commands

    def _ui_rect_for_node(self, node: "Node") -> Dict[str, float]:
        ui_system = getattr(getattr(node, "tree", None), "ui_system", None)
        if ui_system is not None:
            rect = ui_system.get_rect(node)
            if rect is not None:
                return rect.to_dict()
        fallback = node.metadata.get("_ui_rect")
        if isinstance(fallback, dict):
            return {str(key): float(value) for key, value in fallback.items() if key in {"x", "y", "width", "height"}}
        return {"x": 0.0, "y": 0.0, "width": 120.0, "height": 40.0}

    def _direction_from_transform(self, transform: Transform) -> Vector3:
        rotation = transform.rotation
        pitch = float(rotation.x)
        yaw = float(rotation.y)
        direction = Vector3(
            math.cos(pitch) * math.sin(yaw),
            -math.sin(pitch),
            -math.cos(pitch) * math.cos(yaw),
        )
        return direction.normalized()

    def _canvas_sort_key(self, position: Vector3) -> float:
        if self.mode == RenderMode.RENDER_2D_ISOMETRIC:
            return float(position.y + position.z * 0.5 + position.x * 0.001)
        return float(position.y)

    def _layer_to_index(self, layer: Any) -> int:
        if isinstance(layer, int):
            return int(layer)
        text = str(layer or "default").strip().lower()
        mapping = {
            "background": -100,
            "parallax": -50,
            "default": 0,
            "world": 0,
            "characters": 50,
            "effects": 100,
            "foreground": 200,
            "ui": 1000,
        }
        return mapping.get(text, 0)
