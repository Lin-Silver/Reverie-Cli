"""Camera system generator for AAA-quality camera control."""

from __future__ import annotations

from typing import Any, Dict, List


def generate_camera_system(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_id: str = "godot",
) -> Dict[str, Any]:
    """Generate advanced camera system with lock-on, dynamic framing, and cinematic modes."""
    
    experience = game_request.get("experience", {})
    camera_model = experience.get("camera_model", "third_person")
    combat_model = experience.get("combat_model", "ability_action")
    
    source_prompt = str(game_request.get("source_prompt", "")).lower()
    
    # Detect camera features
    needs_lock_on = any(word in source_prompt for word in ["lock", "target", "锁定", "combat", "boss"])
    needs_cinematic = any(word in source_prompt for word in ["cinematic", "cutscene", "过场"])
    needs_photo_mode = any(word in source_prompt for word in ["photo", "screenshot", "拍照"])
    is_open_world = any(word in source_prompt for word in ["open world", "开放世界", "exploration"])
    
    camera_features = []
    
    # Base third-person camera
    if camera_model == "third_person":
        camera_features.append({
            "id": "third_person_base",
            "name": "Third Person Camera",
            "description": "Smooth third-person camera with collision avoidance",
            "distance": 5.5,
            "height_offset": 1.4,
            "fov": 75.0,
            "sensitivity": 0.005,
            "smoothing": 8.0,
            "collision_layers": ["world", "obstacles"],
        })
    
    # Lock-on system
    if needs_lock_on or combat_model in ["lock_on_action", "ability_action"]:
        camera_features.append({
            "id": "lock_on",
            "name": "Lock-On System",
            "description": "Target locking for combat encounters",
            "max_lock_distance": 25.0,
            "lock_angle_threshold": 60.0,
            "auto_switch_distance": 8.0,
            "lock_smoothing": 12.0,
            "target_indicator": {
                "type": "reticle",
                "color": [1.0, 0.3, 0.3],
                "size": 0.8,
            },
        })
    
    # Dynamic framing for open world
    if is_open_world:
        camera_features.append({
            "id": "dynamic_framing",
            "name": "Dynamic Framing",
            "description": "Adjusts camera based on movement speed and context",
            "speed_based_distance": True,
            "min_distance": 4.0,
            "max_distance": 12.0,
            "transition_speed": 2.5,
            "look_ahead_factor": 1.8,
        })
    
    # Cinematic camera
    if needs_cinematic:
        camera_features.append({
            "id": "cinematic",
            "name": "Cinematic Camera",
            "description": "Scripted camera paths for cutscenes",
            "supports_spline_paths": True,
            "supports_look_at_targets": True,
            "blend_time": 1.2,
        })
    
    # Photo mode
    if needs_photo_mode:
        camera_features.append({
            "id": "photo_mode",
            "name": "Photo Mode",
            "description": "Free camera for screenshots",
            "free_movement_speed": 8.0,
            "rotation_speed": 2.0,
            "fov_range": [30.0, 120.0],
            "filters": ["none", "vintage", "noir", "vibrant"],
        })
    
    return {
        "system_id": "camera",
        "display_name": "Advanced Camera System",
        "camera_model": camera_model,
        "features": camera_features,
        "implementation": {
            "godot": _godot_camera_implementation(camera_features),
            "o3de": _o3de_camera_implementation(camera_features),
            "reverie_engine": _reverie_camera_implementation(camera_features),
        },
        "telemetry_events": [
            "camera_mode_changed",
            "lock_on_acquired",
            "lock_on_lost",
            "photo_mode_entered",
            "cinematic_started",
        ],
    }


def _godot_camera_implementation(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    has_lock_on = any(f["id"] == "lock_on" for f in features)
    has_photo_mode = any(f["id"] == "photo_mode" for f in features)
    has_cinematic = any(f["id"] == "cinematic" for f in features)
    
    script = """# Advanced Camera System for Godot
extends Node3D

@export var target: Node3D
@export var base_distance: float = 5.5
@export var height_offset: float = 1.4
@export var camera_smoothing: float = 8.0
@export var collision_mask: int = 1

var current_distance: float = 5.5
var pitch: float = 0.0
var yaw: float = 0.0
var locked_target: Node3D = null
var photo_mode_active: bool = false

@onready var camera: Camera3D = $Camera3D
@onready var spring_arm: SpringArm3D = $SpringArm3D


func _ready() -> void:
    spring_arm.spring_length = base_distance
    spring_arm.collision_mask = collision_mask


func _process(delta: float) -> void:
    if photo_mode_active:
        _process_photo_mode(delta)
        return
    
    if locked_target:
        _process_lock_on(delta)
    else:
        _process_free_camera(delta)


func _process_free_camera(delta: float) -> void:
    if not target:
        return
    
    # Smooth follow target
    var target_pos = target.global_position + Vector3(0, height_offset, 0)
    global_position = global_position.lerp(target_pos, delta * camera_smoothing)
    
    # Apply rotation
    rotation.x = pitch
    rotation.y = yaw


func _process_lock_on(delta: float) -> void:
    if not target or not locked_target:
        return
    
    # Position between player and target
    var player_pos = target.global_position + Vector3(0, height_offset, 0)
    var target_pos = locked_target.global_position + Vector3(0, 1.0, 0)
    var mid_point = (player_pos + target_pos) / 2.0
    
    global_position = global_position.lerp(mid_point, delta * 12.0)
    
    # Look at target
    var look_dir = (target_pos - global_position).normalized()
    var target_rotation = Basis.looking_at(look_dir, Vector3.UP).get_euler()
    rotation.x = lerp_angle(rotation.x, target_rotation.x, delta * 12.0)
    rotation.y = lerp_angle(rotation.y, target_rotation.y, delta * 12.0)


func _process_photo_mode(delta: float) -> void:
    # Free camera movement
    var input_dir = Vector3.ZERO
    if Input.is_key_pressed(KEY_W):
        input_dir -= transform.basis.z
    if Input.is_key_pressed(KEY_S):
        input_dir += transform.basis.z
    if Input.is_key_pressed(KEY_A):
        input_dir -= transform.basis.x
    if Input.is_key_pressed(KEY_D):
        input_dir += transform.basis.x
    if Input.is_key_pressed(KEY_Q):
        input_dir -= Vector3.UP
    if Input.is_key_pressed(KEY_E):
        input_dir += Vector3.UP
    
    global_position += input_dir.normalized() * 8.0 * delta


func try_lock_on() -> bool:
    var potential_targets = get_tree().get_nodes_in_group("lockable")
    if potential_targets.is_empty():
        locked_target = null
        return false
    
    var closest_target: Node3D = null
    var closest_distance: float = 25.0
    
    for potential in potential_targets:
        if not potential is Node3D:
            continue
        var distance = global_position.distance_to(potential.global_position)
        if distance < closest_distance:
            closest_target = potential
            closest_distance = distance
    
    locked_target = closest_target
    return locked_target != null


func release_lock_on() -> void:
    locked_target = null


func toggle_photo_mode() -> void:
    photo_mode_active = not photo_mode_active
    if photo_mode_active:
        Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)
    else:
        Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
"""
    
    return {
        "script_template": script,
        "required_nodes": ["Camera3D", "SpringArm3D"],
        "input_actions": ["camera_lock_on", "camera_photo_mode"] if has_lock_on else [],
        "groups": ["lockable"] if has_lock_on else [],
    }


def _o3de_camera_implementation(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    components = ["CameraComponent", "SpringArmComponent"]
    
    if any(f["id"] == "lock_on" for f in features):
        components.append("LockOnComponent")
    if any(f["id"] == "photo_mode" for f in features):
        components.append("PhotoModeComponent")
    if any(f["id"] == "cinematic" for f in features):
        components.append("CinematicCameraComponent")
    
    return {
        "component_type": "AdvancedCameraRig",
        "required_components": components,
        "script_canvas": "camera_controller.scriptcanvas",
    }


def _reverie_camera_implementation(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "module": "reverie.camera.advanced",
        "config": "camera_config.json",
        "features": [f["id"] for f in features],
    }
