"""Serializable components for Reverie Engine Lite."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Dict, Type

from .math3d import Transform, Vector2, Vector3


def _serialize_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "to_list"):
        return value.to_list()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    return value


@dataclass
class Component:
    enabled: bool = True

    @property
    def component_type(self) -> str:
        return self.__class__.__name__.replace("Component", "")

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"type": self.component_type}
        for field_info in fields(self):
            payload[field_info.name] = _serialize_value(getattr(self, field_info.name))
        return payload


@dataclass
class TransformComponent(Component):
    transform: Transform = field(default_factory=Transform)

    @property
    def position(self) -> Vector3:
        return self.transform.position

    @position.setter
    def position(self, value: Any) -> None:
        self.transform.position = Vector3.from_any(value)


@dataclass
class SpriteComponent(Component):
    texture: str = ""
    atlas: str = ""
    frame: str = ""
    size: Vector2 = field(default_factory=lambda: Vector2(1.0, 1.0))
    billboard: bool = False
    layer: str = "default"


@dataclass
class Camera2DComponent(Component):
    zoom: float = 1.0
    follow_target: str = ""
    smoothing: float = 0.15
    viewport: list[int] = field(default_factory=lambda: [1280, 720])


@dataclass
class Camera3DComponent(Component):
    fov: float = 70.0
    near: float = 0.1
    far: float = 500.0
    mode: str = "third_person"


@dataclass
class LightComponent(Component):
    light_type: str = "directional"
    intensity: float = 1.0
    color: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    range: float = 24.0


@dataclass
class ColliderComponent(Component):
    shape: str = "box"
    size: Vector3 = field(default_factory=lambda: Vector3(1.0, 1.0, 1.0))
    radius: float = 0.5
    is_trigger: bool = False
    layer: str = "world"
    mask: list[str] = field(default_factory=lambda: ["world", "player", "enemy"])


@dataclass
class KinematicBodyComponent(Component):
    speed: float = 4.0
    acceleration: float = 12.0
    gravity: float = 0.0
    friction: float = 8.0


@dataclass
class AudioSourceComponent(Component):
    clip: str = ""
    loop: bool = False
    volume: float = 1.0


@dataclass
class AnimatorComponent(Component):
    current_state: str = "idle"
    state_machine: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptBehaviourComponent(Component):
    script: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthComponent(Component):
    max_health: float = 100.0
    current_health: float = 100.0
    armor: float = 0.0
    faction: str = "neutral"
    invulnerable: bool = False


@dataclass
class InventoryComponent(Component):
    capacity: int = 32
    items: Dict[str, int] = field(default_factory=dict)
    currencies: Dict[str, int] = field(default_factory=dict)


@dataclass
class DialogueComponent(Component):
    conversation_id: str = ""
    auto_start: bool = False
    speaker: str = ""
    portrait: str = ""


@dataclass
class NavigationAgentComponent(Component):
    path_id: str = ""
    speed: float = 2.0
    waypoint_index: int = 0
    loop: bool = False
    stopping_distance: float = 0.1


@dataclass
class TowerDefenseComponent(Component):
    role: str = "tower"
    range: float = 4.0
    damage: float = 1.0
    cadence_frames: int = 30
    projectile_speed: float = 6.0
    tower_id: str = ""
    target_priority: str = "nearest"
    upgrade_level: int = 1
    sell_value: int = 0
    path_id: str = ""
    wave_id: str = ""
    cost: int = 0
    reward: int = 0


@dataclass
class Live2DComponent(Component):
    model_id: str = ""
    idle_motion: str = "idle"
    expression_map: Dict[str, str] = field(default_factory=dict)
    canvas_size: list[int] = field(default_factory=lambda: [1280, 720])
    anchor: str = "center"
    scale_factor: float = 1.0


@dataclass
class StatBlockComponent(Component):
    stats: Dict[str, float] = field(default_factory=dict)


@dataclass
class StateMachineComponent(Component):
    current_state: str = "idle"
    states: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TileMapComponent(Component):
    tileset: str = ""
    cell_size: list[int] = field(default_factory=lambda: [64, 64])
    layers: list[str] = field(default_factory=list)


@dataclass
class ParallaxLayerComponent(Component):
    scroll_scale: Vector2 = field(default_factory=lambda: Vector2(0.5, 0.5))
    repeat: bool = True
    offset: Vector2 = field(default_factory=Vector2)

    def __post_init__(self) -> None:
        self.scroll_scale = Vector2.from_any(self.scroll_scale)
        self.offset = Vector2.from_any(self.offset)


@dataclass
class MeshComponent(Component):
    """3D mesh rendering component."""
    mesh: str = "cube"  # mesh resource ID
    material: str = "default"
    cast_shadow: bool = True
    receive_shadow: bool = True
    visible: bool = True


@dataclass
class RigidBodyComponent(Component):
    """Physics rigid body component."""
    mass: float = 1.0
    velocity: Vector3 = field(default_factory=Vector3.zero)
    angular_velocity: Vector3 = field(default_factory=Vector3.zero)
    gravity_scale: float = 1.0
    linear_damp: float = 0.0
    angular_damp: float = 0.0
    is_kinematic: bool = False
    freeze_rotation: bool = False


@dataclass
class ParticleSystemComponent(Component):
    """Particle system for effects."""
    emitting: bool = True
    amount: int = 100
    lifetime: float = 1.0
    speed: float = 5.0
    spread: float = 45.0
    gravity: Vector3 = field(default_factory=lambda: Vector3(0, -9.8, 0))
    color: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])


@dataclass
class UIControlComponent(Component):
    """Base UI control component."""
    anchor_left: float = 0.0
    anchor_top: float = 0.0
    anchor_right: float = 0.0
    anchor_bottom: float = 0.0
    margin_left: float = 0.0
    margin_top: float = 0.0
    margin_right: float = 0.0
    margin_bottom: float = 0.0
    min_size: Vector2 = field(default_factory=lambda: Vector2(120.0, 40.0))
    custom_size: Vector2 = field(default_factory=Vector2)
    clip_content: bool = False
    visible: bool = True


@dataclass
class TextLabelComponent(Component):
    """Text rendering component."""
    text: str = ""
    font: str = "default"
    font_size: int = 16
    color: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    align: str = "left"  # left, center, right
    valign: str = "top"  # top, center, bottom


@dataclass
class PanelComponent(Component):
    style: str = "panel"
    fill_color: list[float] = field(default_factory=lambda: [0.08, 0.12, 0.18, 0.92])
    border_color: list[float] = field(default_factory=lambda: [0.24, 0.34, 0.45, 1.0])
    padding: list[float] = field(default_factory=lambda: [12.0, 12.0, 12.0, 12.0])


@dataclass
class ButtonComponent(Component):
    text: str = ""
    action: str = ""
    pressed: bool = False
    disabled: bool = False
    variant: str = "primary"


@dataclass
class ImageComponent(Component):
    texture: str = ""
    tint: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    stretch_mode: str = "fit"


@dataclass
class ProgressBarComponent(Component):
    min_value: float = 0.0
    max_value: float = 100.0
    value: float = 0.0
    fill_color: list[float] = field(default_factory=lambda: [0.36, 0.77, 0.46, 1.0])
    background_color: list[float] = field(default_factory=lambda: [0.14, 0.18, 0.24, 1.0])
    show_percentage: bool = True
    label: str = ""


@dataclass
class DialogueBoxComponent(Component):
    conversation_binding: str = "active"
    speaker_prefix: str = ""
    empty_text: str = ""


@dataclass
class ChoiceListComponent(Component):
    choice_prefix: str = ""
    max_visible_choices: int = 4
    selected_index: int = 0


@dataclass
class ResourceBarComponent(Component):
    resource_id: str = ""
    label: str = ""
    max_value: float = 100.0
    display_mode: str = "value"


@dataclass
class TowerBuildPanelComponent(Component):
    title: str = "Build"
    blueprint_ids: list[str] = field(default_factory=list)
    auto_populate: bool = True


COMPONENT_REGISTRY: Dict[str, Type[Component]] = {
    "Transform": TransformComponent,
    "Sprite": SpriteComponent,
    "Camera2D": Camera2DComponent,
    "Camera3D": Camera3DComponent,
    "Light": LightComponent,
    "Collider": ColliderComponent,
    "KinematicBody": KinematicBodyComponent,
    "AudioSource": AudioSourceComponent,
    "Animator": AnimatorComponent,
    "ScriptBehaviour": ScriptBehaviourComponent,
    "Health": HealthComponent,
    "Inventory": InventoryComponent,
    "Dialogue": DialogueComponent,
    "NavigationAgent": NavigationAgentComponent,
    "TowerDefense": TowerDefenseComponent,
    "Live2D": Live2DComponent,
    "StatBlock": StatBlockComponent,
    "StateMachine": StateMachineComponent,
    "TileMap": TileMapComponent,
    "ParallaxLayer": ParallaxLayerComponent,
    "Mesh": MeshComponent,
    "RigidBody": RigidBodyComponent,
    "ParticleSystem": ParticleSystemComponent,
    "UIControl": UIControlComponent,
    "TextLabel": TextLabelComponent,
    "Panel": PanelComponent,
    "Button": ButtonComponent,
    "Image": ImageComponent,
    "ProgressBar": ProgressBarComponent,
    "DialogueBox": DialogueBoxComponent,
    "ChoiceList": ChoiceListComponent,
    "ResourceBar": ResourceBarComponent,
    "TowerBuildPanel": TowerBuildPanelComponent,
}


def component_from_dict(payload: Dict[str, Any]) -> Component:
    payload = dict(payload or {})
    component_type = str(payload.pop("type", "ScriptBehaviour")).strip()
    component_class = COMPONENT_REGISTRY.get(component_type, ScriptBehaviourComponent)

    if component_class is TransformComponent:
        return TransformComponent(
            enabled=bool(payload.get("enabled", True)),
            transform=Transform.from_any(payload.get("transform") or payload),
        )

    if component_class is SpriteComponent:
        payload["size"] = Vector2.from_any(payload.get("size"))
    if component_class is ParallaxLayerComponent:
        payload["scroll_scale"] = Vector2.from_any(payload.get("scroll_scale") or [0.5, 0.5])
        payload["offset"] = Vector2.from_any(payload.get("offset") or [0.0, 0.0])
    if component_class is UIControlComponent:
        payload["min_size"] = Vector2.from_any(payload.get("min_size") or [120.0, 40.0])
        payload["custom_size"] = Vector2.from_any(payload.get("custom_size") or [0.0, 0.0])
    if component_class is ColliderComponent:
        payload["size"] = Vector3.from_any(payload.get("size") or [1.0, 1.0, 1.0])
    if component_class is HealthComponent:
        payload["max_health"] = float(payload.get("max_health", 100.0))
        payload["current_health"] = float(payload.get("current_health", payload["max_health"]))
    if component_class is RigidBodyComponent:
        payload["velocity"] = Vector3.from_any(payload.get("velocity") or [0.0, 0.0, 0.0])
        payload["angular_velocity"] = Vector3.from_any(payload.get("angular_velocity") or [0.0, 0.0, 0.0])
    if component_class is ParticleSystemComponent:
        payload["gravity"] = Vector3.from_any(payload.get("gravity") or [0.0, -9.8, 0.0])
    if component_class is Live2DComponent and "scale" in payload and "scale_factor" not in payload:
        payload["scale_factor"] = float(payload.get("scale", 1.0))

    accepted = {field_info.name for field_info in fields(component_class)}
    init_kwargs = {key: value for key, value in payload.items() if key in accepted}
    return component_class(**init_kwargs)
