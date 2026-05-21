"""Traversal and locomotion system generator for advanced 3D movement."""

from __future__ import annotations

from typing import Any, Dict, List


def generate_traversal_system(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_id: str = "godot",
) -> Dict[str, Any]:
    """Generate advanced traversal system with climbing, gliding, parkour."""
    
    experience = game_request.get("experience", {})
    movement_model = experience.get("movement_model", "third_person_action")
    
    # Detect traversal features from request
    source_prompt = str(game_request.get("source_prompt", "")).lower()
    has_climbing = any(word in source_prompt for word in ["climb", "climbing", "wall", "ledge"])
    has_gliding = any(word in source_prompt for word in ["glide", "gliding", "fly", "飞行", "滑翔"])
    has_dash = any(word in source_prompt for word in ["dash", "sprint", "冲刺"])
    has_parkour = any(word in source_prompt for word in ["parkour", "跑酷", "wall run"])
    
    traversal_abilities = []
    
    if has_climbing:
        traversal_abilities.append({
            "id": "climbing",
            "name": "Climbing System",
            "description": "Allows player to climb walls and ledges",
            "stamina_cost_per_second": 8.0,
            "climb_speed": 3.5,
            "ledge_grab_range": 1.8,
            "implementation": {
                "godot": _godot_climbing_system(),
                "o3de": _o3de_climbing_system(),
                "reverie_engine": _reverie_climbing_system(),
            }
        })
    
    if has_gliding:
        traversal_abilities.append({
            "id": "gliding",
            "name": "Gliding System",
            "description": "Allows player to glide through the air",
            "stamina_cost_per_second": 5.0,
            "glide_speed": 12.0,
            "descent_rate": 2.5,
            "max_glide_angle": 45.0,
            "implementation": {
                "godot": _godot_gliding_system(),
                "o3de": _o3de_gliding_system(),
                "reverie_engine": _reverie_gliding_system(),
            }
        })
    
    if has_dash:
        traversal_abilities.append({
            "id": "dash",
            "name": "Dash System",
            "description": "Quick burst of speed in any direction",
            "stamina_cost": 20.0,
            "dash_speed": 18.0,
            "dash_duration": 0.3,
            "cooldown": 1.2,
            "iframe_duration": 0.15,
            "implementation": {
                "godot": _godot_dash_system(),
                "o3de": _o3de_dash_system(),
                "reverie_engine": _reverie_dash_system(),
            }
        })
    
    if has_parkour:
        traversal_abilities.append({
            "id": "parkour",
            "name": "Parkour System",
            "description": "Wall running, vaulting, and advanced movement",
            "wall_run_duration": 2.5,
            "wall_run_speed": 7.0,
            "vault_height": 2.0,
            "implementation": {
                "godot": _godot_parkour_system(),
                "o3de": _o3de_parkour_system(),
                "reverie_engine": _reverie_parkour_system(),
            }
        })
    
    return {
        "system_id": "traversal",
        "display_name": "Advanced Traversal System",
        "movement_model": movement_model,
        "abilities": traversal_abilities,
        "base_movement": {
            "walk_speed": 6.0,
            "run_speed": 9.0,
            "sprint_speed": 12.0,
            "jump_height": 2.5,
            "air_control": 0.7,
        },
        "stamina_integration": {
            "max_stamina": 100.0,
            "regen_rate": 15.0,
            "regen_delay": 1.0,
        },
        "telemetry_events": [
            "traversal_ability_used",
            "stamina_depleted",
            "fall_damage_taken",
            "ledge_grabbed",
            "wall_run_started",
        ],
    }


def _godot_climbing_system() -> Dict[str, Any]:
    return {
        "script_template": """
# Climbing System for Godot
extends Node

var is_climbing: bool = false
var climb_normal: Vector3 = Vector3.ZERO

func try_start_climb(player: CharacterBody3D) -> bool:
    var ray_cast = player.get_node_or_null("ClimbRayCast")
    if not ray_cast or not ray_cast.is_colliding():
        return false
    
    var collision_normal = ray_cast.get_collision_normal()
    if abs(collision_normal.y) > 0.3:  # Too steep or flat
        return false
    
    is_climbing = true
    climb_normal = collision_normal
    return true

func process_climbing(player: CharacterBody3D, delta: float, input_dir: Vector2) -> void:
    if not is_climbing:
        return
    
    var up_dir = Vector3.UP
    var right_dir = climb_normal.cross(up_dir).normalized()
    var climb_velocity = (right_dir * input_dir.x + up_dir * input_dir.y) * 3.5
    
    player.velocity = climb_velocity
    player.move_and_slide()
""",
        "required_nodes": ["ClimbRayCast", "ClimbDetector"],
        "input_actions": ["climb_up", "climb_down", "climb_left", "climb_right", "climb_release"],
    }


def _godot_gliding_system() -> Dict[str, Any]:
    return {
        "script_template": """
# Gliding System for Godot
extends Node

var is_gliding: bool = false
var glide_velocity: Vector3 = Vector3.ZERO

func try_start_glide(player: CharacterBody3D) -> bool:
    if player.is_on_floor():
        return false
    if player.velocity.y > -1.0:  # Not falling fast enough
        return false
    
    is_gliding = true
    return true

func process_gliding(player: CharacterBody3D, delta: float, input_dir: Vector2) -> void:
    if not is_gliding:
        return
    
    var forward = -player.transform.basis.z
    var right = player.transform.basis.x
    var direction = (forward * input_dir.y + right * input_dir.x).normalized()
    
    glide_velocity.x = lerp(glide_velocity.x, direction.x * 12.0, delta * 2.0)
    glide_velocity.z = lerp(glide_velocity.z, direction.z * 12.0, delta * 2.0)
    glide_velocity.y = max(glide_velocity.y - 2.5 * delta, -8.0)
    
    player.velocity = glide_velocity
    player.move_and_slide()
    
    if player.is_on_floor():
        is_gliding = false
""",
        "required_nodes": ["GlideWings", "GlideParticles"],
        "input_actions": ["glide_toggle"],
    }


def _godot_dash_system() -> Dict[str, Any]:
    return {
        "script_template": """
# Dash System for Godot
extends Node

var dash_cooldown: float = 0.0
var is_dashing: bool = false
var dash_timer: float = 0.0
var dash_direction: Vector3 = Vector3.ZERO

func try_dash(player: CharacterBody3D, direction: Vector3) -> bool:
    if dash_cooldown > 0.0 or is_dashing:
        return false
    
    is_dashing = true
    dash_timer = 0.3
    dash_direction = direction.normalized()
    dash_cooldown = 1.2
    return true

func process_dash(player: CharacterBody3D, delta: float) -> void:
    dash_cooldown = max(0.0, dash_cooldown - delta)
    
    if is_dashing:
        dash_timer -= delta
        if dash_timer <= 0.0:
            is_dashing = false
        else:
            player.velocity = dash_direction * 18.0
            player.move_and_slide()
""",
        "required_nodes": ["DashTrail", "DashParticles"],
        "input_actions": ["dash"],
    }


def _godot_parkour_system() -> Dict[str, Any]:
    return {
        "script_template": """
# Parkour System for Godot
extends Node

var is_wall_running: bool = false
var wall_run_timer: float = 0.0
var wall_normal: Vector3 = Vector3.ZERO

func try_wall_run(player: CharacterBody3D) -> bool:
    if player.is_on_floor():
        return false
    
    var left_ray = player.get_node_or_null("WallRunLeftRay")
    var right_ray = player.get_node_or_null("WallRunRightRay")
    
    if left_ray and left_ray.is_colliding():
        wall_normal = left_ray.get_collision_normal()
        is_wall_running = true
        wall_run_timer = 2.5
        return true
    elif right_ray and right_ray.is_colliding():
        wall_normal = right_ray.get_collision_normal()
        is_wall_running = true
        wall_run_timer = 2.5
        return true
    
    return false

func process_wall_run(player: CharacterBody3D, delta: float) -> void:
    if not is_wall_running:
        return
    
    wall_run_timer -= delta
    if wall_run_timer <= 0.0:
        is_wall_running = false
        return
    
    var forward = wall_normal.cross(Vector3.UP).normalized()
    player.velocity = forward * 7.0 + Vector3.UP * 0.5
    player.move_and_slide()
""",
        "required_nodes": ["WallRunLeftRay", "WallRunRightRay", "WallRunParticles"],
        "input_actions": ["wall_run"],
    }


def _o3de_climbing_system() -> Dict[str, Any]:
    return {
        "component_type": "ClimbingComponent",
        "script_canvas": "climbing_logic.scriptcanvas",
        "required_components": ["CharacterController", "RayCast", "AnimationController"],
    }


def _o3de_gliding_system() -> Dict[str, Any]:
    return {
        "component_type": "GlidingComponent",
        "script_canvas": "gliding_logic.scriptcanvas",
        "required_components": ["CharacterController", "ParticleEmitter", "AnimationController"],
    }


def _o3de_dash_system() -> Dict[str, Any]:
    return {
        "component_type": "DashComponent",
        "script_canvas": "dash_logic.scriptcanvas",
        "required_components": ["CharacterController", "TrailRenderer"],
    }


def _o3de_parkour_system() -> Dict[str, Any]:
    return {
        "component_type": "ParkourComponent",
        "script_canvas": "parkour_logic.scriptcanvas",
        "required_components": ["CharacterController", "MultiRayCast", "AnimationController"],
    }


def _reverie_climbing_system() -> Dict[str, Any]:
    return {"module": "reverie.traversal.climbing", "config": "climbing_config.json"}


def _reverie_gliding_system() -> Dict[str, Any]:
    return {"module": "reverie.traversal.gliding", "config": "gliding_config.json"}


def _reverie_dash_system() -> Dict[str, Any]:
    return {"module": "reverie.traversal.dash", "config": "dash_config.json"}


def _reverie_parkour_system() -> Dict[str, Any]:
    return {"module": "reverie.traversal.parkour", "config": "parkour_config.json"}
