"""Godot runtime adapter and slice scaffold generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import BaseRuntimeAdapter, RuntimeProfile


def _safe_write(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _project_godot(project_name: str) -> str:
    return f"""config_version=5

[application]

config/name="{project_name}"
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.5")

[autoload]

GameState="*res://autoload/game_state.gd"
SaveService="*res://autoload/save_service.gd"

[display]

window/size/viewport_width=1600
window/size/viewport_height=900
window/stretch/mode="canvas_items"
window/stretch/aspect="expand"

[rendering]

renderer/rendering_method="forward_plus"
anti_aliasing/quality/msaa_3d=1
"""


MAIN_TSCN = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1"]

[node name="Main" type="Node3D"]
script = ExtResource("1")
"""


MAIN_GD = """extends Node3D

const PLAYER_SCRIPT := preload("res://scripts/player_controller.gd")
const ENEMY_SCRIPT := preload("res://scripts/enemy_dummy.gd")
const SHRINE_SCRIPT := preload("res://scripts/quest_trigger.gd")
const NPC_ANCHOR_SCRIPT := preload("res://scripts/npc_anchor.gd")
const REGION_GATEWAY_SCRIPT := preload("res://scripts/region_gateway.gd")
const REWARD_CACHE_SCRIPT := preload("res://scripts/reward_cache.gd")
const REGION_OBJECTIVE_SCRIPT := preload("res://scripts/region_objective_site.gd")
const ENCOUNTER_DIRECTOR_SCRIPT := preload("res://scripts/encounter_director.gd")
const REGION_MANAGER_SCRIPT := preload("res://scripts/region_manager.gd")
const HUD_SCRIPT := preload("res://scripts/hud.gd")


func _ready() -> void:
    GameState.ensure_runtime_data()
    GameState.reset_for_slice()
    _build_environment()
    _build_ground()
    _build_landmarks()
    _spawn_npc_beacons()
    _spawn_player(GameState.get_spawn_point())
    for enemy_spec in GameState.get_enemy_specs():
        _spawn_enemy(enemy_spec)
    _spawn_shrine(GameState.get_shrine_position())
    _spawn_region_gateways()
    _spawn_reward_sites()
    _spawn_region_objectives()
    _spawn_encounter_director()
    _spawn_region_manager()
    _spawn_hud()
    if SaveService.has_save():
        GameState.set_hint("Press F9 to load saved slice progress, or continue the fresh run.")


func _build_environment() -> void:
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color(0.78, 0.89, 1.0)
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.78, 0.82, 0.92)
    environment.ambient_light_energy = 1.3
    environment.tonemap_mode = Environment.TONE_MAPPER_ACES
    environment.glow_enabled = true
    var world_environment := WorldEnvironment.new()
    world_environment.environment = environment
    add_child(world_environment)

    var sun := DirectionalLight3D.new()
    sun.light_energy = 3.4
    sun.rotation_degrees = Vector3(-46.0, 25.0, 0.0)
    add_child(sun)


func _build_ground() -> void:
    var ground := StaticBody3D.new()
    ground.name = "Ground"
    add_child(ground)

    var collision := CollisionShape3D.new()
    var box := BoxShape3D.new()
    box.size = Vector3(56.0, 1.0, 56.0)
    collision.shape = box
    collision.position = Vector3(0.0, -0.5, 0.0)
    ground.add_child(collision)

    var visual := MeshInstance3D.new()
    var mesh := PlaneMesh.new()
    mesh.size = Vector2(56.0, 56.0)
    visual.mesh = mesh
    visual.rotation_degrees = Vector3(-90.0, 0.0, 0.0)
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(0.29, 0.40, 0.26)
    material.roughness = 0.95
    visual.material_override = material
    ground.add_child(visual)


func _build_landmarks() -> void:
    for landmark in GameState.get_landmarks():
        _spawn_landmark(landmark)
    for layout in GameState.get_region_layout_specs():
        for landmark in layout.get("preview_landmarks", []):
            var region_landmark := landmark.duplicate(true)
            region_landmark["region_id"] = layout.get("id", GameState.get_root_region_id())
            _spawn_landmark(region_landmark)


func _spawn_landmark(landmark_spec: Dictionary) -> void:
    var body := StaticBody3D.new()
    body.position = _vec3_from_variant(landmark_spec.get("position", []), Vector3.ZERO)
    _attach_region_context(body, str(landmark_spec.get("region_id", GameState.get_root_region_id())))
    add_child(body)

    var collision := CollisionShape3D.new()
    var shape := BoxShape3D.new()
    shape.size = _vec3_from_variant(landmark_spec.get("size", []), Vector3(2.0, 2.0, 2.0))
    collision.shape = shape
    body.add_child(collision)

    var visual := MeshInstance3D.new()
    var mesh := BoxMesh.new()
    mesh.size = shape.size
    visual.mesh = mesh
    var material := StandardMaterial3D.new()
    material.albedo_color = _color_from_variant(landmark_spec.get("color", []), Color(0.4, 0.4, 0.4))
    material.roughness = 0.9
    visual.material_override = material
    body.add_child(visual)


func _spawn_npc_beacons() -> void:
    for npc_spec in GameState.get_npc_anchor_specs():
        _spawn_npc_beacon(npc_spec)


func _spawn_npc_beacon(npc_spec: Dictionary) -> void:
    var anchor := Area3D.new()
    anchor.name = str(npc_spec.get("name", "NPC Anchor"))
    anchor.position = _vec3_from_variant(npc_spec.get("position", []), Vector3.ZERO)
    _attach_region_context(anchor, str(npc_spec.get("region_id", npc_spec.get("home_region", GameState.get_root_region_id()))))
    anchor.set_script(NPC_ANCHOR_SCRIPT)
    anchor.npc_id = str(npc_spec.get("id", "npc_anchor"))
    anchor.display_name = str(npc_spec.get("name", anchor.name))
    anchor.npc_role = str(npc_spec.get("role", "guide"))
    anchor.function_summary = str(npc_spec.get("function", "supports the next expansion beat"))
    anchor.home_region = str(npc_spec.get("home_region", "starter_ruins"))

    var collision := CollisionShape3D.new()
    var shape := CylinderShape3D.new()
    shape.radius = 0.75
    shape.height = 2.4
    collision.shape = shape
    collision.position = Vector3(0.0, 1.2, 0.0)
    anchor.add_child(collision)

    var visual := MeshInstance3D.new()
    var mesh := CylinderMesh.new()
    mesh.top_radius = 0.32
    mesh.bottom_radius = 0.48
    mesh.height = 2.2
    visual.mesh = mesh
    visual.position = Vector3(0.0, 1.1, 0.0)
    var material := StandardMaterial3D.new()
    material.albedo_color = _color_from_variant(npc_spec.get("color", []), Color(0.98, 0.92, 0.54))
    material.emission_enabled = true
    material.emission = material.albedo_color * 0.35
    visual.material_override = material
    anchor.add_child(visual)

    var label := Label3D.new()
    label.text = str(npc_spec.get("name", "NPC"))
    label.position = Vector3(0.0, 2.8, 0.0)
    label.modulate = Color(1.0, 0.98, 0.92)
    anchor.add_child(label)

    add_child(anchor)


func _spawn_player(position: Vector3) -> void:
    var player := CharacterBody3D.new()
    player.name = "Player"
    player.position = position
    player.set_script(PLAYER_SCRIPT)

    var collision := CollisionShape3D.new()
    var shape := CapsuleShape3D.new()
    shape.radius = 0.45
    shape.height = 1.0
    collision.shape = shape
    collision.position = Vector3(0.0, 0.95, 0.0)
    player.add_child(collision)

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := CapsuleMesh.new()
    mesh.radius = 0.45
    mesh.mid_height = 1.0
    visual.mesh = mesh
    visual.position = Vector3(0.0, 0.95, 0.0)
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(0.92, 0.88, 0.72)
    material.roughness = 0.82
    visual.material_override = material
    player.add_child(visual)

    var pivot := Node3D.new()
    pivot.name = "CameraPivot"
    pivot.position = Vector3(0.0, 1.4, 0.0)
    player.add_child(pivot)

    var spring_arm := SpringArm3D.new()
    spring_arm.name = "SpringArm3D"
    spring_arm.spring_length = 5.2
    pivot.add_child(spring_arm)

    var camera := Camera3D.new()
    camera.name = "Camera3D"
    camera.current = true
    spring_arm.add_child(camera)

    add_child(player)


func _spawn_enemy(enemy_spec: Dictionary) -> void:
    var enemy := CharacterBody3D.new()
    enemy.name = str(enemy_spec.get("name", "Sentinel"))
    enemy.position = _vec3_from_variant(enemy_spec.get("position", []), Vector3.ZERO)
    _attach_region_context(enemy, str(enemy_spec.get("region_id", GameState.get_root_region_id())))
    enemy.set_script(ENEMY_SCRIPT)
    enemy.enemy_id = str(enemy_spec.get("id", "sentinel_melee"))
    enemy.display_name = str(enemy_spec.get("name", enemy.name))
    enemy.tint_color = _color_from_variant(enemy_spec.get("color", []), Color(0.96, 0.35, 0.35))
    enemy.max_health = int(enemy_spec.get("max_health", 3))
    enemy.contact_damage = int(enemy_spec.get("contact_damage", 7))
    enemy.move_speed = float(enemy_spec.get("move_speed", 3.8))
    enemy.combat_role = str(enemy_spec.get("combat_role", "melee"))
    enemy.squad_role = str(enemy_spec.get("squad_role", "default"))
    enemy.desired_range = float(enemy_spec.get("desired_range", 2.1))
    enemy.projectile_speed = float(enemy_spec.get("projectile_speed", 13.0))
    enemy.projectile_damage = int(enemy_spec.get("projectile_damage", 6))
    enemy.projectile_cooldown = float(enemy_spec.get("projectile_cooldown", 2.0))
    enemy.projectile_lifetime = float(enemy_spec.get("projectile_lifetime", 3.0))
    enemy.combat_tier = str(enemy_spec.get("combat_tier", "standard"))
    enemy.pattern_profile_id = str(enemy_spec.get("pattern_profile_id", ""))
    enemy.phase_thresholds = enemy_spec.get("phase_thresholds", [])
    enemy.burst_projectile_count = int(enemy_spec.get("burst_projectile_count", 0))
    enemy.burst_projectile_speed = float(enemy_spec.get("burst_projectile_speed", 8.5))
    enemy.burst_projectile_damage = int(enemy_spec.get("burst_projectile_damage", 0))
    enemy.burst_cooldown = float(enemy_spec.get("burst_cooldown", 0.0))
    enemy.max_poise = float(enemy_spec.get("max_poise", 3.0))
    enemy.poise_recovery_per_second = float(enemy_spec.get("poise_recovery_per_second", 1.4))
    enemy.stagger_duration = float(enemy_spec.get("stagger_duration", 0.32))

    var collision := CollisionShape3D.new()
    collision.name = "CollisionShape3D"
    var shape := CapsuleShape3D.new()
    shape.radius = 0.55
    shape.height = 0.8
    collision.shape = shape
    collision.position = Vector3(0.0, 0.95, 0.0)
    enemy.add_child(collision)

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := CylinderMesh.new()
    mesh.top_radius = 0.6
    mesh.bottom_radius = 0.8
    mesh.height = 1.8
    visual.mesh = mesh
    visual.position = Vector3(0.0, 0.9, 0.0)
    enemy.add_child(visual)

    var label := Label3D.new()
    label.name = "StatusLabel"
    label.text = enemy.display_name
    label.position = Vector3(0.0, 2.3, 0.0)
    label.modulate = Color(1.0, 0.98, 0.92)
    enemy.add_child(label)

    add_child(enemy)


func _spawn_shrine(position: Vector3) -> void:
    var shrine := Area3D.new()
    shrine.name = "PurificationShrine"
    shrine.position = position
    _attach_region_context(shrine, GameState.get_root_region_id())
    shrine.set_script(SHRINE_SCRIPT)

    var collision := CollisionShape3D.new()
    var shape := BoxShape3D.new()
    shape.size = Vector3(1.8, 2.2, 1.8)
    collision.shape = shape
    collision.position = Vector3(0.0, 1.1, 0.0)
    shrine.add_child(collision)

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := CylinderMesh.new()
    mesh.top_radius = 0.65
    mesh.bottom_radius = 1.0
    mesh.height = 2.4
    visual.mesh = mesh
    visual.position = Vector3(0.0, 1.2, 0.0)
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(0.58, 0.87, 0.95)
    material.emission_enabled = true
    material.emission = Color(0.18, 0.45, 0.60)
    visual.material_override = material
    shrine.add_child(visual)

    add_child(shrine)


func _spawn_region_gateways() -> void:
    for gateway_spec in GameState.get_region_gateway_specs():
        _spawn_region_gateway(gateway_spec)


func _spawn_region_gateway(gateway_spec: Dictionary) -> void:
    var gateway := Area3D.new()
    gateway.name = str(gateway_spec.get("target_region", "region_gateway"))
    gateway.position = _vec3_from_variant(gateway_spec.get("position", []), Vector3.ZERO)
    _attach_region_context(gateway, str(gateway_spec.get("region_id", GameState.get_root_region_id())))
    gateway.set_script(REGION_GATEWAY_SCRIPT)
    gateway.gateway_id = str(gateway_spec.get("id", "region_gateway"))
    gateway.from_region = str(gateway_spec.get("region_id", GameState.get_root_region_id()))
    gateway.target_region = str(gateway_spec.get("target_region", "next_region"))
    gateway.target_spawn = gateway_spec.get("target_spawn", [0.0, 1.1, 8.0])
    gateway.biome = str(gateway_spec.get("biome", "frontier"))
    gateway.summary = str(gateway_spec.get("summary", "expand the next authored region"))
    gateway.requires_primed = bool(gateway_spec.get("requires_primed", true))

    var collision := CollisionShape3D.new()
    var shape := CylinderShape3D.new()
    shape.radius = 1.15
    shape.height = 2.8
    collision.shape = shape
    collision.position = Vector3(0.0, 1.4, 0.0)
    gateway.add_child(collision)

    var visual := MeshInstance3D.new()
    var mesh := CylinderMesh.new()
    mesh.top_radius = 0.9
    mesh.bottom_radius = 1.15
    mesh.height = 2.6
    visual.mesh = mesh
    visual.position = Vector3(0.0, 1.3, 0.0)
    var material := StandardMaterial3D.new()
    material.albedo_color = _color_from_variant(gateway_spec.get("color", []), Color(0.55, 0.88, 1.0))
    material.emission_enabled = true
    material.emission = material.albedo_color * 0.42
    visual.material_override = material
    gateway.add_child(visual)

    var label := Label3D.new()
    label.text = str(gateway_spec.get("target_region", "next_region")).replace("_", " ").capitalize()
    label.position = Vector3(0.0, 3.0, 0.0)
    label.modulate = Color(0.96, 0.98, 1.0)
    gateway.add_child(label)

    add_child(gateway)


func _spawn_reward_sites() -> void:
    for reward_site in GameState.get_reward_site_specs():
        _spawn_reward_site(reward_site)


func _spawn_reward_site(reward_site: Dictionary) -> void:
    var cache := Area3D.new()
    cache.name = str(reward_site.get("label", "Reward Cache"))
    cache.position = _vec3_from_variant(reward_site.get("position", []), Vector3.ZERO)
    _attach_region_context(cache, str(reward_site.get("region_id", GameState.get_root_region_id())))
    cache.set_script(REWARD_CACHE_SCRIPT)
    cache.site_id = str(reward_site.get("id", "reward_cache"))
    cache.display_label = str(reward_site.get("label", cache.name))
    cache.reward_id = str(reward_site.get("reward_id", "route_sigil"))
    cache.summary = str(reward_site.get("summary", "Optional cache reward."))
    cache.encounter_id = str(reward_site.get("encounter_id", ""))

    var collision := CollisionShape3D.new()
    var shape := CylinderShape3D.new()
    shape.radius = 0.9
    shape.height = 2.0
    collision.shape = shape
    collision.position = Vector3(0.0, 1.0, 0.0)
    cache.add_child(collision)

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := CylinderMesh.new()
    mesh.top_radius = 0.52
    mesh.bottom_radius = 0.74
    mesh.height = 1.8
    visual.mesh = mesh
    visual.position = Vector3(0.0, 0.9, 0.0)
    var material := StandardMaterial3D.new()
    material.albedo_color = _color_from_variant(reward_site.get("color", []), Color(0.96, 0.80, 0.38))
    material.emission_enabled = true
    material.emission = material.albedo_color * 0.36
    visual.material_override = material
    cache.add_child(visual)

    var label := Label3D.new()
    label.text = str(reward_site.get("label", "Reward Cache"))
    label.position = Vector3(0.0, 2.35, 0.0)
    label.modulate = Color(1.0, 0.98, 0.92)
    cache.add_child(label)

    add_child(cache)


func _spawn_region_objectives() -> void:
    for objective_spec in GameState.get_region_objective_specs():
        _spawn_region_objective(objective_spec)


func _spawn_region_objective(objective_spec: Dictionary) -> void:
    var objective := Area3D.new()
    objective.name = str(objective_spec.get("label", "Region Objective"))
    objective.position = _vec3_from_variant(objective_spec.get("position", []), Vector3.ZERO)
    _attach_region_context(objective, str(objective_spec.get("region_id", GameState.get_root_region_id())))
    objective.set_script(REGION_OBJECTIVE_SCRIPT)
    objective.objective_id = str(objective_spec.get("id", "region_objective"))
    objective.region_id = str(objective_spec.get("region_id", GameState.get_root_region_id()))
    objective.display_label = str(objective_spec.get("label", objective.name))
    objective.reward_id = str(objective_spec.get("reward_id", ""))
    objective.encounter_id = str(objective_spec.get("encounter_id", ""))
    objective.summary = str(objective_spec.get("summary", "Advance the regional route."))

    var collision := CollisionShape3D.new()
    var shape := CylinderShape3D.new()
    shape.radius = 1.0
    shape.height = 2.2
    collision.shape = shape
    collision.position = Vector3(0.0, 1.1, 0.0)
    objective.add_child(collision)

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := CylinderMesh.new()
    mesh.top_radius = 0.42
    mesh.bottom_radius = 0.82
    mesh.height = 2.0
    visual.mesh = mesh
    visual.position = Vector3(0.0, 1.0, 0.0)
    var material := StandardMaterial3D.new()
    material.albedo_color = _color_from_variant(objective_spec.get("color", []), Color(0.62, 0.92, 0.80))
    material.emission_enabled = true
    material.emission = material.albedo_color * 0.34
    visual.material_override = material
    objective.add_child(visual)

    var label := Label3D.new()
    label.text = str(objective_spec.get("label", "Region Objective"))
    label.position = Vector3(0.0, 2.6, 0.0)
    label.modulate = Color(0.98, 0.99, 1.0)
    objective.add_child(label)

    add_child(objective)


func _spawn_hud() -> void:
    var hud := CanvasLayer.new()
    hud.name = "HUD"
    hud.set_script(HUD_SCRIPT)
    add_child(hud)


func _spawn_encounter_director() -> void:
    var director := Node.new()
    director.name = "EncounterDirector"
    director.set_script(ENCOUNTER_DIRECTOR_SCRIPT)
    add_child(director)


func _spawn_region_manager() -> void:
    var manager := Node.new()
    manager.name = "RegionManager"
    manager.set_script(REGION_MANAGER_SCRIPT)
    add_child(manager)


func _attach_region_context(node: Node, region_id: String) -> void:
    node.add_to_group("region_content")
    node.set_meta("region_id", region_id)


func _vec3_from_variant(value: Variant, fallback: Vector3) -> Vector3:
    if value is Array and value.size() >= 3:
        return Vector3(float(value[0]), float(value[1]), float(value[2]))
    return fallback


func _color_from_variant(value: Variant, fallback: Color) -> Color:
    if value is Array and value.size() >= 3:
        return Color(float(value[0]), float(value[1]), float(value[2]))
    return fallback
"""


PLAYER_CONTROLLER_GD = """extends CharacterBody3D

@export var base_move_speed: float = 6.0
@export var base_jump_velocity: float = 6.2
@export var gravity_force: float = 18.0
@export var attack_range: float = 3.25
@export var base_dash_speed: float = 14.0

var _look_x: float = -0.25
var _attack_cooldown: float = 0.0
var _skill_cooldown: float = 0.0
var _heavy_skill_cooldown: float = 0.0
var _dash_cooldown: float = 0.0
var _interact_cooldown: float = 0.0
var _locked_target_path: NodePath = NodePath("")
var _invulnerable_timer: float = 0.0
var _hit_reaction_timer: float = 0.0
var _combo_window_timer: float = 0.0
var _combo_index: int = 0
var _guarding: bool = false
var _guard_hold_time: float = 0.0

@onready var camera_pivot: Node3D = $CameraPivot

const FEEDBACK_SCRIPT := preload("res://scripts/combat_feedback.gd")


func _ready() -> void:
    add_to_group("player")
    Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
    GameState.bind_player(self)


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventMouseMotion and Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED:
        rotate_y(-event.relative.x * 0.005)
        _look_x = clamp(_look_x - event.relative.y * 0.005, -0.85, 0.35)
        camera_pivot.rotation.x = _look_x
    elif event is InputEventKey and event.pressed and not event.echo:
        match event.keycode:
            KEY_ESCAPE:
                if Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED:
                    Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)
                else:
                    Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
            KEY_TAB:
                _toggle_lock_target()
            KEY_R:
                _try_skill_attack()
            KEY_F:
                _try_heavy_skill_attack()
            KEY_F5:
                SaveService.save_progress("manual")
            KEY_F9:
                SaveService.load_progress()
    elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
        _try_attack()
    elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
        _try_skill_attack()


func _physics_process(delta: float) -> void:
    GameState.restore_stamina(delta)
    _attack_cooldown = max(_attack_cooldown - delta, 0.0)
    _skill_cooldown = max(_skill_cooldown - delta, 0.0)
    _heavy_skill_cooldown = max(_heavy_skill_cooldown - delta, 0.0)
    _dash_cooldown = max(_dash_cooldown - delta, 0.0)
    _interact_cooldown = max(_interact_cooldown - delta, 0.0)
    _invulnerable_timer = max(_invulnerable_timer - delta, 0.0)
    _hit_reaction_timer = max(_hit_reaction_timer - delta, 0.0)
    _combo_window_timer = max(_combo_window_timer - delta, 0.0)
    _update_guard_state(delta)
    _refresh_lock_target()

    if _hit_reaction_timer > 0.0:
        velocity.x = move_toward(velocity.x, 0.0, 32.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, 32.0 * delta)
        if not is_on_floor():
            velocity.y -= gravity_force * delta
        move_and_slide()
        return

    var input_vector := Vector2.ZERO
    if Input.is_physical_key_pressed(KEY_A):
        input_vector.x -= 1.0
    if Input.is_physical_key_pressed(KEY_D):
        input_vector.x += 1.0
    if Input.is_physical_key_pressed(KEY_W):
        input_vector.y += 1.0
    if Input.is_physical_key_pressed(KEY_S):
        input_vector.y -= 1.0
    input_vector = input_vector.normalized()

    var forward := -transform.basis.z
    forward.y = 0.0
    forward = forward.normalized()
    var right := transform.basis.x
    right.y = 0.0
    right = right.normalized()
    var direction := (right * input_vector.x + forward * input_vector.y).normalized()
    var locked_target := _get_locked_target()

    if locked_target != null:
        var lock_direction := locked_target.global_position - global_position
        lock_direction.y = 0.0
        if lock_direction.length() > 0.05:
            var target_yaw := atan2(lock_direction.x, lock_direction.z)
            rotation.y = lerp_angle(rotation.y, target_yaw, delta * 8.0)
    elif direction.length() > 0.001:
        var desired_yaw := atan2(direction.x, direction.z)
        rotation.y = lerp_angle(rotation.y, desired_yaw, delta * 9.0)

    var move_speed := base_move_speed * GameState.get_move_speed_multiplier()
    var dash_speed := base_dash_speed * GameState.get_move_speed_multiplier()
    var target_speed := move_speed
    if Input.is_physical_key_pressed(KEY_SHIFT) and GameState.consume_stamina(14.0 * delta):
        target_speed *= 1.35
    if _guarding:
        target_speed *= 0.52

    if Input.is_physical_key_pressed(KEY_Q) and _dash_cooldown <= 0.0 and GameState.consume_stamina(24.0):
        var dash_direction := direction if direction.length() > 0.001 else -transform.basis.z
        velocity.x = dash_direction.x * dash_speed
        velocity.z = dash_direction.z * dash_speed
        _dash_cooldown = 0.9
        _invulnerable_timer = GameState.get_dash_iframe_seconds()
        _spawn_feedback(global_position + Vector3(0.0, 0.2, 0.0), Color(0.72, 0.90, 1.0), 0.22, 4.5, 0.55)
        GameState.set_hint("Dash used to reposition into or out of combat.")
    else:
        velocity.x = move_toward(velocity.x, direction.x * target_speed, 28.0 * delta)
        velocity.z = move_toward(velocity.z, direction.z * target_speed, 28.0 * delta)

    if not is_on_floor():
        velocity.y -= gravity_force * delta
    elif Input.is_physical_key_pressed(KEY_SPACE):
        velocity.y = base_jump_velocity

    if Input.is_physical_key_pressed(KEY_E) and _interact_cooldown <= 0.0:
        _try_interact()
        _interact_cooldown = 0.25

    move_and_slide()
    GameState.notify_player_position(global_position)


func _try_attack() -> void:
    if _attack_cooldown > 0.0:
        return
    var combo_chain := GameState.get_combo_chain()
    if combo_chain.is_empty():
        return
    if _combo_window_timer <= 0.0:
        _combo_index = 0
    var attack_profile: Dictionary = combo_chain[min(_combo_index, combo_chain.size() - 1)]
    var stamina_cost := float(attack_profile.get("stamina_cost", 0.0))
    if stamina_cost > 0.0 and not GameState.consume_stamina(stamina_cost):
        GameState.set_hint("Not enough stamina to continue the combo chain.")
        return
    _attack_cooldown = float(attack_profile.get("cooldown", 0.45))
    _combo_window_timer = float(attack_profile.get("combo_window_seconds", 0.0))
    var attack_target := _resolve_attack_target(float(attack_profile.get("hit_range", attack_range)))
    if attack_target and attack_target.has_method("apply_damage"):
        attack_target.apply_damage(
            int(attack_profile.get("damage", GameState.get_attack_damage())),
            name,
            float(attack_profile.get("hit_reaction_seconds", 0.16)),
            float(attack_profile.get("poise_damage", 1.0)),
            str(attack_profile.get("id", "light_slash")),
        )
        _spawn_feedback(attack_target.global_position + Vector3(0.0, 1.0, 0.0), Color(1.0, 0.85, 0.35), 0.20, 3.2, 0.28)
        GameState.set_hint("Combo hit: %s. Push toward the shrine objective." % [str(attack_profile.get("id", "light_slash"))])
    else:
        GameState.set_hint("No target in range. Use movement and dash to close the gap.")
    if _combo_window_timer <= 0.0 or _combo_index >= combo_chain.size() - 1:
        _combo_index = 0
    else:
        _combo_index += 1


func _try_skill_attack() -> void:
    if _skill_cooldown > 0.0:
        return
    var skill_profile := GameState.get_primary_skill()
    var stamina_cost := float(skill_profile.get("stamina_cost", GameState.get_skill_stamina_cost()))
    if not GameState.consume_stamina(stamina_cost):
        GameState.set_hint("Not enough stamina for " + GameState.get_skill_name() + ".")
        return
    _skill_cooldown = float(skill_profile.get("cooldown", GameState.get_skill_cooldown()))
    var skill_range := float(skill_profile.get("range", GameState.get_skill_range()))
    var skill_damage := int(skill_profile.get("damage", GameState.get_skill_damage()))
    var hit_reaction_seconds := float(skill_profile.get("hit_reaction_seconds", 0.34))
    var poise_damage := float(skill_profile.get("poise_damage", 3.2))
    var hit_count := 0
    for node in get_tree().get_nodes_in_group("combat_target"):
        if node is Node3D and global_position.distance_to(node.global_position) <= skill_range:
            if node.has_method("apply_damage"):
                node.apply_damage(skill_damage, GameState.get_skill_name(), hit_reaction_seconds, poise_damage, GameState.get_skill_name())
                hit_count += 1
    if hit_count > 0:
        _spawn_feedback(global_position + Vector3(0.0, 1.0, 0.0), Color(0.45, 0.95, 1.0), 0.34, 6.4, 0.42)
        GameState.set_hint(GameState.get_skill_name() + " hit %d target(s)." % [hit_count])
    else:
        GameState.set_hint(GameState.get_skill_name() + " missed. Use lock-on or close more distance.")


func _try_heavy_skill_attack() -> void:
    if _heavy_skill_cooldown > 0.0:
        return
    var heavy_profile := GameState.get_heavy_skill()
    var stamina_cost := float(heavy_profile.get("stamina_cost", 40.0))
    if not GameState.consume_stamina(stamina_cost):
        GameState.set_hint("Not enough stamina for " + GameState.get_heavy_skill_name() + ".")
        return
    _heavy_skill_cooldown = float(heavy_profile.get("cooldown", 4.8))
    var hit_range := float(heavy_profile.get("range", 4.8))
    var damage := int(heavy_profile.get("damage", 5))
    var hit_reaction_seconds := float(heavy_profile.get("hit_reaction_seconds", 0.42))
    var poise_damage := float(heavy_profile.get("poise_damage", 4.8))
    var attack_target := _resolve_attack_target(hit_range)
    if attack_target and attack_target.has_method("apply_damage"):
        attack_target.apply_damage(damage, GameState.get_heavy_skill_name(), hit_reaction_seconds, poise_damage, GameState.get_heavy_skill_name())
        _spawn_feedback(attack_target.global_position + Vector3(0.0, 1.0, 0.0), Color(1.0, 0.62, 0.28), 0.28, 4.6, 0.34)
        GameState.set_hint(GameState.get_heavy_skill_name() + " broke through with a heavy strike.")
    else:
        GameState.set_hint(GameState.get_heavy_skill_name() + " missed. Commit after a safer opening.")


func _try_interact() -> void:
    for node in get_tree().get_nodes_in_group("slice_interactable"):
        if node is Node3D and global_position.distance_to(node.global_position) <= 3.2:
            if node.has_method("try_activate"):
                node.try_activate(self)
                return
    GameState.set_hint("Nothing to interact with here yet.")


func receive_damage(
    amount: int,
    _source: String = "enemy",
    source_enemy_path: String = "",
    projectile_path: String = "",
) -> void:
    if _invulnerable_timer > 0.0:
        GameState.set_hint("Dash i-frames avoided the incoming damage.")
        return
    if _guarding and GameState.is_guard_enabled():
        if _guard_hold_time <= GameState.get_perfect_guard_window_seconds():
            var source_enemy := get_node_or_null(NodePath(source_enemy_path)) if source_enemy_path != "" else null
            var projectile := get_node_or_null(NodePath(projectile_path)) if projectile_path != "" else null
            if projectile != null:
                projectile.queue_free()
            if source_enemy != null and source_enemy.has_method("apply_damage"):
                source_enemy.apply_damage(0, "perfect_guard", 0.26, GameState.get_guard_counter_poise_damage(), "perfect_guard")
            _spawn_feedback(global_position + Vector3(0.0, 1.0, 0.0), Color(0.55, 0.92, 1.0), 0.26, 4.8, 0.38)
            GameState.set_hint("Perfect guard opened the enemy up. Counter before the window closes.")
            _invulnerable_timer = max(_invulnerable_timer, 0.12)
            return
        var reduced_amount := max(1, int(ceil(float(amount) * (1.0 - GameState.get_guard_damage_reduction()))))
        GameState.damage_player(reduced_amount)
        _spawn_feedback(global_position + Vector3(0.0, 1.0, 0.0), Color(0.94, 0.88, 0.42), 0.22, 3.6, 0.30)
        GameState.set_hint("Guard absorbed the brunt of the hit. Re-time it for a perfect guard.")
        return
    GameState.damage_player(amount)
    _hit_reaction_timer = max(_hit_reaction_timer, GameState.get_player_hit_reaction_seconds())
    _spawn_feedback(global_position + Vector3(0.0, 1.0, 0.0), Color(1.0, 0.34, 0.34), 0.24, 4.0, 0.35)
    if GameState.health <= 0:
        global_position = GameState.get_spawn_point()
        velocity = Vector3.ZERO
        _combo_window_timer = 0.0
        _combo_index = 0


func _toggle_lock_target() -> void:
    if not GameState.is_lock_on_enabled():
        return
    var current_target := _get_locked_target()
    if current_target != null:
        _locked_target_path = NodePath("")
        GameState.set_locked_target_name("")
        GameState.set_hint("Lock target cleared.")
        return
    var nearest_target := GameState.get_closest_target(global_position, 14.0)
    if nearest_target != null:
        _locked_target_path = nearest_target.get_path()
        GameState.set_locked_target_name(str(nearest_target.name))
        GameState.set_hint("Locked onto " + str(nearest_target.name) + ".")
    else:
        GameState.set_hint("No lock target in range.")


func _refresh_lock_target() -> void:
    var locked_target := _get_locked_target()
    if locked_target == null:
        if GameState.get_locked_target_name() != "":
            GameState.set_locked_target_name("")
        return
    GameState.set_locked_target_name(str(locked_target.name))


func _get_locked_target() -> Node3D:
    if _locked_target_path.is_empty():
        return null
    var target := get_node_or_null(_locked_target_path)
    if target == null or not is_instance_valid(target) or not target.is_in_group("combat_target"):
        _locked_target_path = NodePath("")
        return null
    return target


func _resolve_attack_target(max_distance: float) -> Node3D:
    var locked_target := _get_locked_target()
    if locked_target != null and global_position.distance_to(locked_target.global_position) <= max_distance:
        return locked_target
    return GameState.get_closest_target(global_position, max_distance)


func get_skill_cooldown_remaining() -> float:
    return _skill_cooldown


func get_heavy_skill_cooldown_remaining() -> float:
    return _heavy_skill_cooldown


func is_guarding() -> bool:
    return _guarding


func get_guard_window_remaining() -> float:
    if not _guarding:
        return 0.0
    return max(GameState.get_perfect_guard_window_seconds() - _guard_hold_time, 0.0)


func _update_guard_state(delta: float) -> void:
    if not GameState.is_guard_enabled():
        _guarding = false
        _guard_hold_time = 0.0
        return
    if Input.is_physical_key_pressed(KEY_C) and GameState.consume_stamina(GameState.get_guard_stamina_drain_per_second() * delta):
        if not _guarding:
            _guard_hold_time = 0.0
        _guarding = true
        _guard_hold_time += delta
        return
    _guarding = false
    _guard_hold_time = 0.0


func _spawn_feedback(position: Vector3, color: Color, radius: float, grow_rate: float, lifetime: float) -> void:
    var fx := Node3D.new()
    fx.position = position
    fx.set_script(FEEDBACK_SCRIPT)
    fx.tint_color = color
    fx.lifetime = lifetime
    fx.grow_rate = grow_rate

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := SphereMesh.new()
    mesh.radius = radius
    mesh.height = radius * 2.0
    visual.mesh = mesh
    fx.add_child(visual)

    get_tree().current_scene.add_child(fx)
"""
ENEMY_DUMMY_GD = """extends CharacterBody3D

@export var enemy_id: String = "sentinel_melee"
@export var display_name: String = "Sentinel"
@export var tint_color: Color = Color(0.96, 0.35, 0.35)
@export var max_health: int = 3
@export var contact_damage: int = 7
@export var move_speed: float = 3.8
@export var combat_role: String = "melee"
@export var squad_role: String = "default"
@export var aggro_range: float = 12.0
@export var attack_range: float = 2.1
@export var desired_range: float = 2.1
@export var leash_distance: float = 18.0
@export var projectile_speed: float = 13.0
@export var projectile_damage: int = 6
@export var projectile_cooldown: float = 2.0
@export var projectile_lifetime: float = 3.0
@export var combat_tier: String = "standard"
@export var pattern_profile_id: String = ""
@export var phase_thresholds: Array = []
@export var burst_projectile_count: int = 0
@export var burst_projectile_speed: float = 8.5
@export var burst_projectile_damage: int = 0
@export var burst_cooldown: float = 0.0
@export var max_poise: float = 3.0
@export var poise_recovery_per_second: float = 1.4
@export var stagger_duration: float = 0.32

var _health: int = 3
var _home_position: Vector3 = Vector3.ZERO
var _attack_cooldown: float = 0.0
var _burst_cooldown: float = 0.0
var _windup: float = 0.0
var _defeated: bool = false
var _current_phase: int = 1
var _phase_gate_index: int = 0
var _current_poise: float = 3.0
var _stagger_timer: float = 0.0
var _pattern_profile: Dictionary = {}
var _base_move_speed: float = 0.0
var _base_contact_damage: int = 0
var _base_projectile_cooldown: float = 0.0
var _base_burst_cooldown: float = 0.0
var _attack_windup_duration: float = 0.45
var _attack_recovery_cooldown: float = 1.25
var _lunge_speed: float = 0.0
var _lunge_distance_threshold: float = 0.0
var _behavior_mode: String = "default"
var _patrol_route_id: String = ""
var _patrol_points: Array = []
var _patrol_index: int = 0
var _patrol_wait_seconds: float = 0.85
var _patrol_wait_timer: float = 0.0
var _alert_network_id: String = ""
var _alert_search_duration: float = 3.0
var _search_timer: float = 0.0
var _last_alert_position: Vector3 = Vector3.ZERO
var _alert_anchor_point: Vector3 = Vector3.ZERO

const PROJECTILE_SCRIPT := preload("res://scripts/enemy_projectile.gd")
const FEEDBACK_SCRIPT := preload("res://scripts/combat_feedback.gd")


func _ready() -> void:
    _base_move_speed = move_speed
    _base_contact_damage = contact_damage
    _base_projectile_cooldown = projectile_cooldown
    _base_burst_cooldown = burst_cooldown
    _health = max_health
    _current_poise = max_poise
    _home_position = global_position
    _configure_patrol_route()
    _configure_alert_network()
    _pattern_profile = GameState.get_enemy_pattern_profile(enemy_id, pattern_profile_id)
    _apply_phase_profile(1, true)
    add_to_group("combat_target")
    _apply_visuals()
    GameState.register_enemy(display_name, enemy_id)
    if GameState.is_enemy_defeated(enemy_id):
        restore_from_save_state(true)
    else:
        var intro_label := display_name + " patrolling"
        if combat_tier == "boss":
            intro_label = display_name + " guarding the shrine"
        _set_label(intro_label)


func _physics_process(delta: float) -> void:
    if _defeated:
        return

    _attack_cooldown = max(_attack_cooldown - delta, 0.0)
    _burst_cooldown = max(_burst_cooldown - delta, 0.0)
    _stagger_timer = max(_stagger_timer - delta, 0.0)
    _patrol_wait_timer = max(_patrol_wait_timer - delta, 0.0)
    _search_timer = max(_search_timer - delta, 0.0)
    _current_poise = min(max_poise, _current_poise + poise_recovery_per_second * delta)
    var player := GameState.get_player()
    if player == null:
        return

    var to_player := player.global_position - global_position
    to_player.y = 0.0
    var distance := to_player.length()
    var player_in_aggro := distance <= aggro_range
    var region_id := str(get_meta("region_id", GameState.get_root_region_id()))

    if player_in_aggro:
        GameState.raise_alert(enemy_id, player.global_position, region_id)

    if _stagger_timer > 0.0:
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 7.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 7.0 * delta)
        _set_label(display_name + " staggered")
        move_and_slide()
        return

    if _windup > 0.0:
        _windup = max(_windup - delta, 0.0)
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 5.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 5.0 * delta)
        if _windup <= 0.0:
            _resolve_attack(player, distance)
        move_and_slide()
        return

    if GameState.is_enemy_alerted(enemy_id):
        _last_alert_position = GameState.get_alert_position_for_enemy(enemy_id)
        _search_timer = _alert_search_duration

    if combat_tier == "boss" and burst_projectile_count > 0 and burst_cooldown > 0.0 and player_in_aggro and _burst_cooldown <= 0.0:
        _launch_burst(player)
        _burst_cooldown = burst_cooldown
        _attack_cooldown = max(_attack_cooldown, 1.4)
        _set_label(display_name + " channeling burst")
    elif combat_role == "ranged" and player_in_aggro:
        _run_ranged_logic(player, distance, to_player, delta)
    elif player_in_aggro and distance <= max(attack_range, _lunge_distance_threshold) and _attack_cooldown <= 0.0:
        _windup = _attack_windup_duration
        _set_label(display_name + " winding up")
        GameState.set_hint(_phase_hint_for_attack())
    elif player_in_aggro:
        var direction := to_player.normalized()
        velocity.x = direction.x * move_speed
        velocity.z = direction.z * move_speed
        look_at(player.global_position, Vector3.UP)
        _set_label(display_name + " pressuring")
    elif GameState.is_enemy_alerted(enemy_id):
        _run_alert_logic(delta)
    elif _search_timer > 0.0:
        _run_search_logic(delta)
    elif _patrol_points.size() > 1:
        _run_patrol_logic(delta)
    elif global_position.distance_to(_home_position) > 0.6:
        var home_direction := (_home_position - global_position).normalized()
        velocity.x = home_direction.x * move_speed * 0.8
        velocity.z = home_direction.z * move_speed * 0.8
        _set_label(display_name + " guarding")
    else:
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 4.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 4.0 * delta)
        _set_label(display_name + " watching")

    if global_position.distance_to(_home_position) > leash_distance:
        global_position = _home_position
        velocity = Vector3.ZERO

    move_and_slide()


func _run_ranged_logic(player: Node3D, distance: float, to_player: Vector3, delta: float) -> void:
    look_at(player.global_position, Vector3.UP)
    var resolved_range := desired_range
    if _behavior_mode == "boss_pattern":
        resolved_range = max(desired_range - 0.4, 3.8)
    if distance <= aggro_range and distance > resolved_range + 0.6:
        var advance_direction := to_player.normalized()
        velocity.x = advance_direction.x * move_speed
        velocity.z = advance_direction.z * move_speed
        _set_label(display_name + " advancing")
    elif distance < resolved_range - 0.8:
        var retreat_direction := (-to_player).normalized()
        velocity.x = retreat_direction.x * move_speed * 0.85
        velocity.z = retreat_direction.z * move_speed * 0.85
        _set_label(display_name + " retreating")
    else:
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 6.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 6.0 * delta)
        if _attack_cooldown <= 0.0 and distance <= aggro_range:
            _launch_projectile(player)
            _attack_cooldown = projectile_cooldown
            _set_label(display_name + " firing")
        else:
            _set_label(display_name + " aiming")


func _run_patrol_logic(delta: float) -> void:
    if _patrol_points.size() <= 1:
        return
    if _patrol_wait_timer > 0.0:
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 5.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 5.0 * delta)
        _set_label(display_name + " patrolling")
        return
    var target := _patrol_points[_patrol_index]
    var to_target := target - global_position
    to_target.y = 0.0
    if to_target.length() <= 0.45:
        if _patrol_index >= _patrol_points.size() - 1:
            _patrol_index = 0
        else:
            _patrol_index += 1
        _patrol_wait_timer = _patrol_wait_seconds
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 6.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 6.0 * delta)
        _set_label(display_name + " sweeping route")
        return
    var direction := to_target.normalized()
    velocity.x = direction.x * move_speed * 0.62
    velocity.z = direction.z * move_speed * 0.62
    look_at(target, Vector3.UP)
    _set_label(display_name + " patrolling")


func _run_alert_logic(delta: float) -> void:
    var alert_position := GameState.get_alert_position_for_enemy(enemy_id)
    var response_point := _resolve_alert_response_point(alert_position)
    var to_alert := response_point - global_position
    to_alert.y = 0.0
    if to_alert.length() <= 1.1:
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 6.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 6.0 * delta)
        look_at(response_point, Vector3.UP)
        _set_label(display_name + " alerted")
        return
    var direction := to_alert.normalized()
    velocity.x = direction.x * move_speed * 0.88
    velocity.z = direction.z * move_speed * 0.88
    look_at(response_point, Vector3.UP)
    _set_label(display_name + " converging")


func _run_search_logic(delta: float) -> void:
    var search_point := _resolve_search_point()
    var to_search := search_point - global_position
    to_search.y = 0.0
    if to_search.length() <= 1.0:
        velocity.x = move_toward(velocity.x, 0.0, move_speed * 5.0 * delta)
        velocity.z = move_toward(velocity.z, 0.0, move_speed * 5.0 * delta)
        look_at(search_point, Vector3.UP)
        _set_label(display_name + " searching")
        return
    var direction := to_search.normalized()
    velocity.x = direction.x * move_speed * 0.72
    velocity.z = direction.z * move_speed * 0.72
    look_at(search_point, Vector3.UP)
    _set_label(display_name + " searching")


func _resolve_attack(player: Node3D, distance: float) -> void:
    _attack_cooldown = _attack_recovery_cooldown
    var resolved_distance := distance
    if _lunge_speed > 0.0 and distance > attack_range and distance <= _lunge_distance_threshold:
        var lunge_direction := player.global_position - global_position
        lunge_direction.y = 0.0
        if lunge_direction.length() > 0.01:
            lunge_direction = lunge_direction.normalized()
            global_position += lunge_direction * min(_lunge_speed * 0.14, max(distance - attack_range + 0.45, 0.45))
            resolved_distance = global_position.distance_to(player.global_position)
            _spawn_feedback(global_position + Vector3(0.0, 0.9, 0.0), Color(1.0, 0.70, 0.28), 0.20, 4.0, 0.24)
    var resolved_damage := contact_damage + max(_current_phase - 1, 0)
    if resolved_distance <= attack_range + 0.5 and player.has_method("receive_damage"):
        player.receive_damage(resolved_damage, enemy_id, str(get_path()), "")
        GameState.set_hint(display_name + " connected. Read the wind-up and punish the recovery.")
    _set_label(display_name + " recovering")


func _launch_projectile(player: Node3D) -> void:
    var direction := (player.global_position + Vector3(0.0, 0.9, 0.0) - global_position).normalized()
    _spawn_projectile(direction, projectile_damage, projectile_speed)
    GameState.set_hint(display_name + " launched a ranged attack. Keep moving and punish the cooldown.")


func _launch_burst(player: Node3D) -> void:
    var base_direction := (player.global_position + Vector3(0.0, 0.9, 0.0) - global_position).normalized()
    if base_direction.length() <= 0.01:
        base_direction = Vector3.FORWARD
    var count := max(burst_projectile_count, 6)
    for index in range(count):
        var angle := TAU * float(index) / float(count)
        var direction := Basis(Vector3.UP, angle) * base_direction
        _spawn_projectile(direction.normalized(), max(burst_projectile_damage, 1), max(burst_projectile_speed, 4.0))
    GameState.set_hint(display_name + " released a burst. Reposition, then counter during the cooldown.")


func _spawn_projectile(direction: Vector3, damage_value: int, speed_value: float) -> void:
    var projectile := Area3D.new()
    projectile.name = display_name + "Projectile"
    projectile.global_position = global_position + Vector3(0.0, 1.1, 0.0)
    projectile.set_script(PROJECTILE_SCRIPT)
    projectile.direction = direction
    projectile.speed = speed_value
    projectile.damage = damage_value
    projectile.lifetime = projectile_lifetime
    projectile.tint_color = tint_color
    projectile.source_enemy_id = enemy_id
    projectile.source_enemy_path = str(get_path())

    var collision := CollisionShape3D.new()
    collision.name = "CollisionShape3D"
    var shape := SphereShape3D.new()
    shape.radius = 0.22
    collision.shape = shape
    projectile.add_child(collision)

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := SphereMesh.new()
    mesh.radius = 0.22
    mesh.height = 0.44
    visual.mesh = mesh
    projectile.add_child(visual)

    get_tree().current_scene.add_child(projectile)


func apply_damage(
    amount: int,
    attacker_name: String = "",
    hit_reaction_seconds: float = 0.16,
    poise_damage: float = 1.0,
    attack_id: String = "",
) -> void:
    if _defeated:
        return
    _health = max(_health - amount, 0)
    _current_poise = max(_current_poise - poise_damage, 0.0)
    var attack_label := attack_id if attack_id != "" else attacker_name
    GameState.set_hint(attack_label + " damaged " + display_name + ".")
    var player := GameState.get_player()
    var alert_position := global_position
    if player != null:
        alert_position = player.global_position
    GameState.raise_alert(enemy_id, alert_position, str(get_meta("region_id", GameState.get_root_region_id())), 5.5)
    _set_label(display_name + " staggered")
    _spawn_feedback(global_position + Vector3(0.0, 1.0, 0.0), Color(1.0, 0.58, 0.24), 0.22, 4.0, 0.30)
    if _current_poise <= 0.0:
        _stagger_timer = max(stagger_duration, hit_reaction_seconds)
        _current_poise = max_poise
        GameState.set_hint(display_name + " was broken open. Pressure the stagger window.")
    _resolve_phase_shift()
    if _health <= 0:
        _set_defeated_state(true)


func restore_from_save_state(saved_defeated: bool) -> void:
    if saved_defeated:
        _set_defeated_state(false)


func _set_defeated_state(report_to_state: bool) -> void:
    if _defeated:
        return
    _defeated = true
    remove_from_group("combat_target")
    velocity = Vector3.ZERO
    if has_node("CollisionShape3D"):
        $CollisionShape3D.disabled = true
    if has_node("Visual"):
        $Visual.visible = false
    _set_label(display_name + " purified")
    if report_to_state:
        GameState.register_enemy_defeat(display_name, enemy_id)


func _apply_visuals() -> void:
    if has_node("Visual"):
        var material := StandardMaterial3D.new()
        material.albedo_color = tint_color
        material.emission_enabled = true
        material.emission = tint_color * (0.26 if combat_tier == "boss" else 0.12)
        $Visual.material_override = material
        if combat_tier == "boss":
            $Visual.scale = Vector3(1.3, 1.3, 1.3)


func _set_label(text: String) -> void:
    if has_node("StatusLabel"):
        $StatusLabel.text = text


func _resolve_phase_shift() -> void:
    if combat_tier != "boss" or _health <= 0:
        return
    if _phase_gate_index >= phase_thresholds.size():
        return
    var ratio := float(_health) / float(max(max_health, 1))
    var threshold := float(phase_thresholds[_phase_gate_index])
    if ratio > threshold:
        return
    _phase_gate_index += 1
    _current_phase += 1
    max_poise += 1.2
    _current_poise = max_poise
    _apply_phase_profile(_current_phase)
    _burst_cooldown = min(_burst_cooldown, 0.8)
    _spawn_feedback(global_position + Vector3(0.0, 1.1, 0.0), Color(1.0, 0.78, 0.30), 0.35, 5.0, 0.42)
    _set_label(display_name + " phase " + str(_current_phase))
    GameState.set_hint(display_name + " entered phase %d. Expect faster pressure and wider bursts." % [_current_phase])


func _apply_phase_profile(phase_number: int, intro: bool = false) -> void:
    var phase_profile := GameState.get_enemy_phase_profile(enemy_id, pattern_profile_id, phase_number)
    if phase_profile.is_empty():
        return
    _behavior_mode = str(phase_profile.get("behavior_mode", _pattern_profile.get("behavior_mode", "default")))
    _attack_windup_duration = float(phase_profile.get("attack_windup_seconds", 0.45))
    _attack_recovery_cooldown = float(phase_profile.get("attack_cooldown", 1.6 if combat_tier == "boss" else 1.25))
    _lunge_speed = float(phase_profile.get("lunge_speed", 0.0))
    _lunge_distance_threshold = float(phase_profile.get("lunge_distance_threshold", attack_range))
    move_speed = _base_move_speed + float(phase_profile.get("move_speed_bonus", 0.0))
    contact_damage = _base_contact_damage + int(phase_profile.get("contact_bonus", 0))
    projectile_cooldown = float(phase_profile.get("projectile_cooldown", _base_projectile_cooldown))
    burst_cooldown = float(phase_profile.get("burst_cooldown", _base_burst_cooldown))
    desired_range = float(phase_profile.get("desired_range", desired_range))
    var phase_label := str(phase_profile.get("label", "Phase %d" % phase_number))
    var phase_hint := str(phase_profile.get("hint", display_name + " changed tempo."))
    if combat_tier == "boss":
        GameState.set_boss_phase(enemy_id, phase_label, phase_hint)
        if intro:
            GameState.set_hint(display_name + ": " + phase_hint)


func _phase_hint_for_attack() -> String:
    if combat_tier == "boss":
        return display_name + " is telegraphing a phase attack. Guard the opener or dash across the angle."
    if combat_role == "ranged":
        return display_name + " is lining up a volley. Keep moving before the shot lands."
    return display_name + " is about to strike. Dash through or away."


func _resolve_alert_response_point(alert_position: Vector3) -> Vector3:
    if squad_role == "suppressor":
        var offset := (_home_position - alert_position)
        offset.y = 0.0
        if offset.length() <= 0.01:
            offset = Vector3(1.0, 0.0, 0.0)
        return alert_position + offset.normalized() * max(desired_range * 0.55, 2.4)
    if squad_role == "anchor":
        return alert_position.lerp(_alert_anchor_point, 0.40) if _alert_anchor_point != Vector3.ZERO else alert_position
    if squad_role == "boss_anchor":
        return _home_position
    return alert_position


func _resolve_search_point() -> Vector3:
    if squad_role == "suppressor":
        return _resolve_alert_response_point(_last_alert_position)
    if squad_role == "anchor" and _alert_anchor_point != Vector3.ZERO:
        return _alert_anchor_point
    if squad_role == "boss_anchor":
        return _home_position
    return _last_alert_position


func _to_vector3(values: Variant, fallback: Vector3) -> Vector3:
    if values is Array and values.size() >= 3:
        return Vector3(float(values[0]), float(values[1]), float(values[2]))
    return fallback


func _spawn_feedback(position: Vector3, color: Color, radius: float, grow_rate: float, lifetime: float) -> void:
    var fx := Node3D.new()
    fx.position = position
    fx.set_script(FEEDBACK_SCRIPT)
    fx.tint_color = color
    fx.lifetime = lifetime
    fx.grow_rate = grow_rate

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := SphereMesh.new()
    mesh.radius = radius
    mesh.height = radius * 2.0
    visual.mesh = mesh
    fx.add_child(visual)

    get_tree().current_scene.add_child(fx)


func _configure_patrol_route() -> void:
    var patrol_route := GameState.get_enemy_patrol_route(enemy_id)
    if patrol_route.is_empty():
        return
    _patrol_route_id = str(patrol_route.get("id", ""))
    _patrol_wait_seconds = float(patrol_route.get("wait_seconds", 0.85))
    _patrol_points = []
    for point in patrol_route.get("path_points", []):
        _patrol_points.append(_to_vector3(point, global_position))
    if not _patrol_points.is_empty():
        _home_position = _patrol_points[0]
        _patrol_index = 0


func _configure_alert_network() -> void:
    var alert_network := GameState.get_enemy_alert_network(enemy_id)
    if alert_network.is_empty():
        return
    _alert_network_id = str(alert_network.get("id", ""))
    _alert_search_duration = float(alert_network.get("search_duration_seconds", 3.0))
    _alert_anchor_point = _to_vector3(alert_network.get("anchor_point", []), Vector3.ZERO)
"""


ENEMY_PROJECTILE_GD = """extends Area3D

@export var direction: Vector3 = Vector3.FORWARD
@export var speed: float = 13.0
@export var damage: int = 6
@export var lifetime: float = 3.0
@export var tint_color: Color = Color(0.35, 0.80, 1.0)
@export var source_enemy_id: String = "sentinel_ranged"
@export var source_enemy_path: String = ""

const FEEDBACK_SCRIPT := preload("res://scripts/combat_feedback.gd")


func _ready() -> void:
    if has_node("Visual"):
        var material := StandardMaterial3D.new()
        material.albedo_color = tint_color
        material.emission_enabled = true
        material.emission = tint_color * 0.18
        $Visual.material_override = material


func _physics_process(delta: float) -> void:
    lifetime -= delta
    if lifetime <= 0.0:
        queue_free()
        return

    global_position += direction.normalized() * speed * delta
    var player := GameState.get_player()
    if player != null and global_position.distance_to(player.global_position + Vector3(0.0, 0.9, 0.0)) <= 0.9:
        if player.has_method("receive_damage"):
            player.receive_damage(damage, source_enemy_id, source_enemy_path, str(get_path()))
        _spawn_feedback(global_position, tint_color, 0.18, 3.5, 0.24)
        GameState.set_hint("A ranged shot connected. Close distance or strafe before the next volley.")
        queue_free()


func _spawn_feedback(position: Vector3, color: Color, radius: float, grow_rate: float, lifetime_seconds: float) -> void:
    var fx := Node3D.new()
    fx.position = position
    fx.set_script(FEEDBACK_SCRIPT)
    fx.tint_color = color
    fx.lifetime = lifetime_seconds
    fx.grow_rate = grow_rate

    var visual := MeshInstance3D.new()
    visual.name = "Visual"
    var mesh := SphereMesh.new()
    mesh.radius = radius
    mesh.height = radius * 2.0
    visual.mesh = mesh
    fx.add_child(visual)

    get_tree().current_scene.add_child(fx)
"""


COMBAT_FEEDBACK_GD = """extends Node3D

@export var lifetime: float = 0.35
@export var grow_rate: float = 4.0
@export var tint_color: Color = Color(1.0, 0.85, 0.35)

var _elapsed: float = 0.0


func _ready() -> void:
    if has_node("Visual"):
        var material := StandardMaterial3D.new()
        material.albedo_color = tint_color
        material.emission_enabled = true
        material.emission = tint_color * 0.22
        material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
        material.albedo_color.a = 0.8
        $Visual.material_override = material


func _process(delta: float) -> void:
    _elapsed += delta
    scale += Vector3.ONE * grow_rate * delta
    if has_node("Visual") and $Visual.material_override is StandardMaterial3D:
        var material: StandardMaterial3D = $Visual.material_override
        var t := clamp(_elapsed / max(lifetime, 0.001), 0.0, 1.0)
        var color := tint_color
        color.a = lerp(0.8, 0.0, t)
        material.albedo_color = color
        material.emission = tint_color * lerp(0.22, 0.02, t)
    if _elapsed >= lifetime:
        queue_free()
"""


QUEST_TRIGGER_GD = """extends Area3D

var _activated: bool = false


func _ready() -> void:
    add_to_group("slice_interactable")
    body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
    if body.is_in_group("player"):
        try_activate(body)


func try_activate(_body: Node) -> void:
    if _activated:
        return
    if GameState.can_activate_goal("activate_shrine"):
        _activated = true
        GameState.complete_slice()
    else:
        GameState.set_hint(GameState.get_goal_hint())
"""


NPC_ANCHOR_GD = """extends Area3D

@export var npc_id: String = "keeper_aeris"
@export var display_name: String = "Keeper Aeris"
@export var npc_role: String = "guide"
@export var function_summary: String = "Supports the next quest branch."
@export var home_region: String = "starter_ruins"


func _ready() -> void:
    add_to_group("slice_interactable")
    body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
    if body.is_in_group("player"):
        GameState.set_hint("%s (%s): %s" % [display_name, npc_role, function_summary])


func try_activate(_body: Node) -> void:
    GameState.register_npc_interaction(
        npc_id,
        display_name,
        npc_role,
        function_summary,
        home_region,
    )
"""


REGION_GATEWAY_GD = """extends Area3D

@export var gateway_id: String = "cloudstep_basin_gateway"
@export var from_region: String = "starter_ruins"
@export var target_region: String = "cloudstep_basin"
@export var target_spawn: Array = [72.0, 1.1, 8.0]
@export var biome: String = "tiered canyon wetlands"
@export var summary: String = "Expand the next authored region."
@export var requires_primed: bool = true


func _ready() -> void:
    add_to_group("slice_interactable")
    body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
    if body.is_in_group("player"):
        if GameState.can_travel_gateway(gateway_id):
            GameState.set_hint("Gateway ready for %s. Interact to travel into the next region slice." % [target_region])
        else:
            GameState.set_hint("Gateway seeded for %s. Finish the current shrine route before expanding." % [target_region])


func try_activate(_body: Node) -> void:
    if GameState.travel_to_region(gateway_id, target_region, target_spawn):
        GameState.set_hint("Traveling to %s. %s" % [target_region, summary])
        return
    if requires_primed:
        GameState.set_hint("Current slice first, then expand into %s." % [target_region])
    else:
        GameState.set_hint("%s is not reachable yet." % [target_region])
"""


REWARD_CACHE_GD = """extends Area3D

@export var site_id: String = "overlook_cache"
@export var display_label: String = "Overlook Cache"
@export var reward_id: String = "route_sigil"
@export var summary: String = "Optional cache reward."
@export var encounter_id: String = "overlook_elite_detour"


func _ready() -> void:
    add_to_group("slice_interactable")
    body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
    if not body.is_in_group("player"):
        return
    if GameState.is_reward_site_claimed(site_id):
        GameState.set_hint(display_label + " already claimed. Keep pushing deeper into the slice.")
    elif GameState.is_reward_site_ready(site_id):
        GameState.set_hint(display_label + " is open. Claim " + reward_id + " when you're ready.")
    else:
        GameState.set_hint(display_label + " is sealed. Clear the detour encounter first.")


func try_activate(_body: Node) -> void:
    GameState.claim_reward_site(site_id, reward_id, display_label, summary, encounter_id)
"""


REGION_OBJECTIVE_SITE_GD = """extends Area3D

@export var objective_id: String = "cloudstep_relay"
@export var region_id: String = "cloudstep_basin"
@export var display_label: String = "Stabilize the Survey Relay"
@export var reward_id: String = "basin_insight"
@export var encounter_id: String = ""
@export var summary: String = "Activate the current regional objective."


func _ready() -> void:
    add_to_group("slice_interactable")
    body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
    if not body.is_in_group("player"):
        return
    if GameState.is_region_objective_complete(objective_id):
        GameState.set_hint(display_label + " already secured. Return to the shrine route or keep scouting.")
    elif not GameState.is_region_objective_ready(objective_id):
        GameState.set_hint(display_label + " is contested. Clear the local encounter first.")
    else:
        GameState.set_hint(display_label + " ready. Interact to secure " + reward_id + ".")


func try_activate(_body: Node) -> void:
    GameState.complete_region_objective(objective_id, reward_id, display_label, summary, region_id, encounter_id)
"""


ENCOUNTER_DIRECTOR_GD = """extends Node

var _encounters: Array = []
var _started: Dictionary = {}
var _completed: Dictionary = {}


func _ready() -> void:
    _encounters = GameState.get_encounter_specs()
    for encounter in _encounters:
        if encounter is Dictionary:
            var encounter_id := str(encounter.get("id", ""))
            if encounter_id != "" and GameState.is_encounter_complete(encounter_id):
                _completed[encounter_id] = true


func _process(_delta: float) -> void:
    var player := GameState.get_player()
    if player == null:
        return

    for encounter in _encounters:
        if encounter is Dictionary:
            var encounter_id := str(encounter.get("id", ""))
            if encounter_id == "" or _completed.has(encounter_id):
                continue
            if str(encounter.get("region_id", GameState.get_root_region_id())) != GameState.get_current_region_id():
                continue
            if not _started.has(encounter_id):
                var start_position := _to_vector3(encounter.get("start_position", [0.0, 0.0, 0.0]), Vector3.ZERO)
                var activation_radius := float(encounter.get("activation_radius", 8.0))
                if player.global_position.distance_to(start_position) <= activation_radius:
                    _started[encounter_id] = true
                    GameState.set_active_encounter(
                        encounter_id,
                        str(encounter.get("label", encounter_id)),
                        str(encounter.get("hint", "Encounter started.")),
                    )
            if _started.has(encounter_id) and _all_enemy_ids_defeated(encounter.get("enemy_ids", [])):
                _completed[encounter_id] = true
                GameState.complete_encounter(encounter_id)


func _all_enemy_ids_defeated(enemy_ids: Array) -> bool:
    if enemy_ids.is_empty():
        return false
    for enemy_id in enemy_ids:
        if not GameState.is_enemy_defeated(str(enemy_id)):
            return false
    return true


func _to_vector3(values: Variant, fallback: Vector3) -> Vector3:
    if values is Array and values.size() >= 3:
        return Vector3(float(values[0]), float(values[1]), float(values[2]))
    return fallback
"""


REGION_MANAGER_GD = """extends Node


func _ready() -> void:
    if not GameState.region_changed.is_connected(_on_region_changed):
        GameState.region_changed.connect(_on_region_changed)
    _apply_region(GameState.get_current_region_id())


func _on_region_changed(region_id: String) -> void:
    _apply_region(region_id)


func _apply_region(region_id: String) -> void:
    for node in get_tree().get_nodes_in_group("region_content"):
        var node_region := str(node.get_meta("region_id", GameState.get_root_region_id()))
        var active := node_region == region_id
        _set_node_active(node, active)


func _set_node_active(node: Node, active: bool) -> void:
    if node is Node3D:
        node.visible = active
    if node.has_method("set_process"):
        node.set_process(active)
    if node.has_method("set_physics_process"):
        node.set_physics_process(active)
    if node.has_method("set_process_input"):
        node.set_process_input(active)
    if node.has_method("set_process_unhandled_input"):
        node.set_process_unhandled_input(active)
    for child in node.get_children():
        if child is CollisionShape3D:
            child.disabled = not active
"""


HUD_GD = """extends CanvasLayer

var _status_label: Label
var _objective_label: Label
var _hint_label: Label
var _reward_label: Label
var _target_label: Label
var _combat_label: Label
var _expansion_label: Label


func _ready() -> void:
    var root := MarginContainer.new()
    root.anchor_right = 1.0
    root.anchor_bottom = 1.0
    root.add_theme_constant_override("margin_left", 20)
    root.add_theme_constant_override("margin_top", 20)
    root.add_theme_constant_override("margin_right", 20)
    root.add_theme_constant_override("margin_bottom", 20)
    add_child(root)

    var panel := PanelContainer.new()
    panel.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    root.add_child(panel)

    var content := VBoxContainer.new()
    content.custom_minimum_size = Vector2(520.0, 210.0)
    panel.add_child(content)

    _status_label = Label.new()
    _status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(_status_label)

    _objective_label = Label.new()
    _objective_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(_objective_label)

    _hint_label = Label.new()
    _hint_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(_hint_label)

    _reward_label = Label.new()
    _reward_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(_reward_label)

    _target_label = Label.new()
    _target_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(_target_label)

    _combat_label = Label.new()
    _combat_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(_combat_label)

    _expansion_label = Label.new()
    _expansion_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(_expansion_label)


func _process(_delta: float) -> void:
    _status_label.text = "HP %d/%d   ST %.0f/%.0f   Purified %d/%d" % [
        GameState.health,
        GameState.max_health,
        GameState.stamina,
        GameState.max_stamina,
        GameState.get_current_region_purification_count(),
        GameState.get_current_region_purification_total(),
    ]
    _objective_label.text = "Objective: " + GameState.objective_text
    _hint_label.text = "Hint: " + GameState.status_hint
    _reward_label.text = "Rewards: %s   Detours: %s   Region Goals: %s   Save: %s" % [
        GameState.get_reward_summary(),
        GameState.get_reward_site_progress_text(),
        GameState.get_region_objective_progress_text(),
        "ready" if SaveService.has_save() else "none",
    ]
    _target_label.text = "Lock: %s   Skill: %s   Heavy: %s" % [
        GameState.get_locked_target_name() if GameState.get_locked_target_name() != "" else "none",
        GameState.get_skill_name(),
        GameState.get_heavy_skill_name(),
    ]
    var player := GameState.get_player()
    var cooldown_text := "ready"
    var heavy_cooldown_text := "ready"
    var guard_text := "off"
    if player != null and player.has_method("get_skill_cooldown_remaining"):
        var remaining := player.get_skill_cooldown_remaining()
        cooldown_text = "%.1fs" % [remaining] if remaining > 0.01 else "ready"
    if player != null and player.has_method("get_heavy_skill_cooldown_remaining"):
        var heavy_remaining := player.get_heavy_skill_cooldown_remaining()
        heavy_cooldown_text = "%.1fs" % [heavy_remaining] if heavy_remaining > 0.01 else "ready"
    if player != null and player.has_method("is_guarding") and player.is_guarding():
        var perfect_window := 0.0
        if player.has_method("get_guard_window_remaining"):
            perfect_window = player.get_guard_window_remaining()
        guard_text = "perfect %.2fs" % [perfect_window] if perfect_window > 0.01 else "holding"
    _combat_label.text = "Skill CD: %s   Heavy CD: %s   Guard: %s   Encounter: %s   Dash I-Frames: %.2fs" % [
        cooldown_text,
        heavy_cooldown_text,
        guard_text,
        GameState.get_active_encounter_summary(),
        GameState.get_dash_iframe_seconds(),
    ]
    _expansion_label.text = "Region: %s (%d)   Arc: %s   Goal: %s   Party: %s   Affinity: %s   Stream: %s   Commissions: %s" % [
        GameState.get_current_region_title(),
        GameState.get_discovered_region_count(),
        GameState.get_active_arc_title() + " (" + GameState.get_active_arc_progress_text() + ")",
        GameState.get_current_region_objective_summary(),
        GameState.get_party_summary_text(),
        GameState.get_affinity_summary_text(),
        GameState.get_streaming_summary_text(),
        GameState.get_commission_summary_text(),
    ]
"""
GAME_STATE_GD = """extends Node

signal slice_completed
signal region_changed(region_id)

const COMBAT_PATH := "res://data/combat.json"
const QUEST_FLOW_PATH := "res://data/quest_flow.json"
const PROGRESSION_PATH := "res://data/progression.json"
const WORLD_SLICE_PATH := "res://data/world_slice.json"
const SAVE_SCHEMA_PATH := "res://data/save_schema.json"
const SLICE_MANIFEST_PATH := "res://data/slice_manifest.json"
const REGION_SEEDS_PATH := "res://data/region_seeds.json"
const REGION_LAYOUTS_PATH := "res://data/region_layouts.json"
const REGION_OBJECTIVES_PATH := "res://data/region_objectives.json"
const PATROL_ROUTES_PATH := "res://data/patrol_routes.json"
const ALERT_NETWORKS_PATH := "res://data/alert_networks.json"
const WORLD_GRAPH_PATH := "res://data/world_graph.json"
const NPC_ROSTER_PATH := "res://data/npc_roster.json"
const QUEST_ARCS_PATH := "res://data/quest_arcs.json"
const PARTY_ROSTER_PATH := "res://data/party_roster.json"
const ELEMENTAL_MATRIX_PATH := "res://data/elemental_matrix.json"
const WORLD_STREAMING_PATH := "res://data/world_streaming.json"
const COMMISSION_BOARD_PATH := "res://data/commission_board.json"

var max_health: int = 100
var health: int = 100
var max_stamina: float = 100.0
var stamina: float = 100.0
var enemy_total: int = 0
var enemy_defeated: int = 0
var objective_text: String = ""
var status_hint: String = ""
var slice_complete: bool = false
var player_path: NodePath = NodePath("")

var save_schema: Dictionary = {}
var combat_config: Dictionary = {}
var reward_track: Dictionary = {}
var quest_steps: Array = []
var unlocked_rewards: Array = []
var landmark_specs: Array = []
var enemy_specs: Array = []
var npc_anchor_specs: Array = []
var region_gateway_specs: Array = []
var encounter_specs: Array = []
var reward_site_specs: Array = []
var region_seeds: Array = []
var region_layout_specs: Array = []
var region_objective_specs: Array = []
var patrol_route_specs: Array = []
var alert_network_specs: Array = []
var world_graph: Dictionary = {}
var npc_roster: Array = []
var quest_arcs: Array = []
var party_roster_config: Dictionary = {}
var elemental_matrix: Dictionary = {}
var world_streaming_plan: Dictionary = {}
var commission_board: Dictionary = {}
var active_arc: Dictionary = {}
var player_spawn_point: Vector3 = Vector3(0.0, 1.1, 8.0)
var shrine_position: Vector3 = Vector3(0.0, 0.0, -12.0)
var current_region_id: String = "starter_ruins"
var current_step_index: int = 0
var runtime_data_loaded: bool = false

var _enemy_registry: Dictionary = {}
var _defeated_enemy_ids: Dictionary = {}
var _pending_player_position: Vector3 = Vector3.ZERO
var _has_pending_player_position: bool = false
var _locked_target_name: String = ""
var _spoken_npc_ids: Dictionary = {}
var _primed_gateway_ids: Dictionary = {}
var _completed_encounter_ids: Dictionary = {}
var _claimed_reward_site_ids: Dictionary = {}
var _discovered_region_ids: Dictionary = {}
var _completed_region_objective_ids: Dictionary = {}
var _active_alerts: Dictionary = {}
var _arc_stage_index: int = 0
var _active_encounter_id: String = ""
var _active_encounter_label: String = ""
var _active_encounter_hint: String = ""
var _boss_phase_label: String = ""


func _ready() -> void:
    ensure_runtime_data()
    set_process(true)


func _process(delta: float) -> void:
    var expired: Array = []
    for network_id in _active_alerts.keys():
        var payload := _active_alerts.get(network_id, {})
        var ttl := max(float(payload.get("ttl", 0.0)) - delta, 0.0)
        if ttl <= 0.0:
            expired.append(network_id)
            continue
        payload["ttl"] = ttl
        _active_alerts[network_id] = payload
    for network_id in expired:
        _active_alerts.erase(network_id)


func ensure_runtime_data() -> void:
    if runtime_data_loaded:
        return

    var combat := _load_json_resource(COMBAT_PATH, _default_combat())
    var quest_flow := _load_json_resource(QUEST_FLOW_PATH, _default_quest_flow())
    var progression := _load_json_resource(PROGRESSION_PATH, _default_progression())
    var world_slice := _load_json_resource(WORLD_SLICE_PATH, _default_world_slice())
    var manifest := _load_json_resource(SLICE_MANIFEST_PATH, _default_manifest())
    var regions_payload := _load_json_resource(REGION_SEEDS_PATH, _default_region_seeds())
    var region_layout_payload := _load_json_resource(REGION_LAYOUTS_PATH, _default_region_layouts())
    var region_objective_payload := _load_json_resource(REGION_OBJECTIVES_PATH, _default_region_objectives())
    var patrol_route_payload := _load_json_resource(PATROL_ROUTES_PATH, _default_patrol_routes())
    var alert_network_payload := _load_json_resource(ALERT_NETWORKS_PATH, _default_alert_networks())
    var world_graph_payload := _load_json_resource(WORLD_GRAPH_PATH, _default_world_graph())
    var npc_payload := _load_json_resource(NPC_ROSTER_PATH, _default_npc_roster())
    var quest_arc_payload := _load_json_resource(QUEST_ARCS_PATH, _default_quest_arcs())
    var party_roster_payload := _load_json_resource(PARTY_ROSTER_PATH, _default_party_roster())
    var elemental_matrix_payload := _load_json_resource(ELEMENTAL_MATRIX_PATH, _default_elemental_matrix())
    var world_streaming_payload := _load_json_resource(WORLD_STREAMING_PATH, _default_world_streaming())
    var commission_board_payload := _load_json_resource(COMMISSION_BOARD_PATH, _default_commission_board())
    save_schema = _load_json_resource(SAVE_SCHEMA_PATH, _default_save_schema())

    combat_config = combat
    quest_steps = quest_flow.get("objectives", _default_quest_flow().get("objectives", []))
    reward_track = progression
    landmark_specs = manifest.get("landmarks", [])
    enemy_specs = _merge_enemy_specs(manifest.get("enemies", []), combat.get("enemy_defaults", []))
    npc_anchor_specs = manifest.get("npc_beacons", [])
    region_gateway_specs = manifest.get("region_gateways", [])
    encounter_specs = manifest.get("encounters", combat.get("encounter_templates", []))
    reward_site_specs = manifest.get("reward_sites", [])
    active_arc = manifest.get("active_arc", {})
    region_seeds = regions_payload.get("regions", _default_region_seeds().get("regions", []))
    region_layout_specs = region_layout_payload.get("regions", manifest.get("region_layouts", _default_region_layouts().get("regions", [])))
    region_objective_specs = region_objective_payload.get("objectives", manifest.get("region_objectives", _default_region_objectives().get("objectives", [])))
    patrol_route_specs = patrol_route_payload.get("routes", manifest.get("patrol_routes", _default_patrol_routes().get("routes", [])))
    alert_network_specs = alert_network_payload.get("networks", manifest.get("alert_networks", _default_alert_networks().get("networks", [])))
    world_graph = world_graph_payload
    npc_roster = npc_payload.get("npcs", _default_npc_roster().get("npcs", []))
    quest_arcs = quest_arc_payload.get("quest_arcs", _default_quest_arcs().get("quest_arcs", []))
    party_roster_config = party_roster_payload
    elemental_matrix = elemental_matrix_payload
    world_streaming_plan = world_streaming_payload
    commission_board = commission_board_payload
    if landmark_specs.is_empty():
        landmark_specs = _default_manifest().get("landmarks", [])
    if enemy_specs.is_empty():
        enemy_specs = _merge_enemy_specs(_default_manifest().get("enemies", []), _default_combat().get("enemy_defaults", []))
    if npc_anchor_specs.is_empty():
        npc_anchor_specs = _default_manifest().get("npc_beacons", [])
    if region_gateway_specs.is_empty():
        region_gateway_specs = _default_manifest().get("region_gateways", [])
    if encounter_specs.is_empty():
        encounter_specs = _default_manifest().get("encounters", [])
    if reward_site_specs.is_empty():
        reward_site_specs = _default_manifest().get("reward_sites", [])
    if region_layout_specs.is_empty():
        region_layout_specs = _default_region_layouts().get("regions", [])
    if region_objective_specs.is_empty():
        region_objective_specs = manifest.get("region_objectives", _default_region_objectives().get("objectives", []))
    if patrol_route_specs.is_empty():
        patrol_route_specs = manifest.get("patrol_routes", _default_patrol_routes().get("routes", []))
    if alert_network_specs.is_empty():
        alert_network_specs = manifest.get("alert_networks", _default_alert_networks().get("networks", []))
    if world_graph.is_empty():
        world_graph = manifest.get("world_graph", _default_world_graph())
    if active_arc.is_empty():
        active_arc = _default_manifest().get("active_arc", {})
    if region_seeds.is_empty():
        region_seeds = _default_region_seeds().get("regions", [])
    if npc_roster.is_empty():
        npc_roster = _default_npc_roster().get("npcs", [])
    if quest_arcs.is_empty():
        quest_arcs = _default_quest_arcs().get("quest_arcs", [])
    if party_roster_config.is_empty():
        party_roster_config = manifest.get("party_roster", _default_party_roster())
    if elemental_matrix.is_empty():
        elemental_matrix = manifest.get("elemental_matrix", _default_elemental_matrix())
    if world_streaming_plan.is_empty():
        world_streaming_plan = manifest.get("world_streaming", _default_world_streaming())
    if commission_board.is_empty():
        commission_board = manifest.get("commission_board", _default_commission_board())

    player_spawn_point = _to_vector3(manifest.get("spawn_point", [0.0, 1.1, 8.0]), Vector3(0.0, 1.1, 8.0))
    shrine_position = _to_vector3(manifest.get("shrine_position", [0.0, 0.0, -12.0]), Vector3(0.0, 0.0, -12.0))
    current_region_id = str(region_layout_payload.get("active_region_id", manifest.get("active_region_id", get_root_region_id())))
    if world_slice.has("landmarks") and not world_slice.get("landmarks", []).is_empty():
        status_hint = "Landmarks loaded: %s" % [", ".join(world_slice.get("landmarks", []))]
    if not region_seeds.is_empty():
        status_hint = "Expansion seed ready: %s" % [region_seeds[0].get("id", "starter_ruins")]

    runtime_data_loaded = true


func reset_for_slice() -> void:
    ensure_runtime_data()
    health = max_health
    stamina = max_stamina
    _defeated_enemy_ids.clear()
    _spoken_npc_ids.clear()
    _primed_gateway_ids.clear()
    _completed_encounter_ids.clear()
    _claimed_reward_site_ids.clear()
    _discovered_region_ids.clear()
    _completed_region_objective_ids.clear()
    _active_alerts.clear()
    current_region_id = get_root_region_id()
    _discovered_region_ids[current_region_id] = true
    _arc_stage_index = 0
    enemy_total = 0
    enemy_defeated = _defeated_enemy_ids.size()
    slice_complete = false
    player_path = NodePath("")
    _enemy_registry.clear()
    current_step_index = 0
    _active_encounter_id = ""
    _active_encounter_label = ""
    _active_encounter_hint = ""
    _boss_phase_label = ""
    player_spawn_point = get_region_spawn_point(current_region_id)
    status_hint = "Use WASD + mouse. LMB attack, C guard, Shift sprint, Q dash, E interact, F5 save, F9 load."
    _locked_target_name = ""
    _has_pending_player_position = false
    _pending_player_position = Vector3.ZERO
    _refresh_objective()


func bind_player(player: Node) -> void:
    player_path = player.get_path()
    if _has_pending_player_position and player is Node3D:
        player.global_position = _pending_player_position
        _has_pending_player_position = false
    var next_region := "starter_ruins"
    if not region_seeds.is_empty():
        next_region = region_seeds[0].get("id", "starter_ruins")
    set_hint("Player ready in %s. Speak to the guide beacon, then enter the ruins. Expansion path: %s." % [get_current_region_title(), next_region])


func get_player() -> Node3D:
    if player_path.is_empty():
        return null
    return get_node_or_null(player_path)


func get_spawn_point() -> Vector3:
    return player_spawn_point


func get_shrine_position() -> Vector3:
    return shrine_position


func get_enemy_specs() -> Array:
    return enemy_specs


func get_landmarks() -> Array:
    return landmark_specs


func get_npc_anchor_specs() -> Array:
    return npc_anchor_specs


func get_region_gateway_specs() -> Array:
    return region_gateway_specs


func get_reward_site_specs() -> Array:
    return reward_site_specs


func get_region_seeds() -> Array:
    return region_seeds


func get_region_layout_specs() -> Array:
    return region_layout_specs


func get_region_objective_specs() -> Array:
    return region_objective_specs


func get_patrol_route_specs() -> Array:
    return patrol_route_specs


func get_alert_network_specs() -> Array:
    return alert_network_specs


func get_world_graph() -> Dictionary:
    return world_graph


func get_root_region_id() -> String:
    if not region_seeds.is_empty():
        return str(region_seeds[0].get("id", "starter_ruins"))
    if not region_layout_specs.is_empty():
        return str(region_layout_specs[0].get("id", "starter_ruins"))
    return "starter_ruins"


func get_current_region_id() -> String:
    return current_region_id


func get_current_region_title() -> String:
    var layout := get_region_layout(current_region_id)
    if not layout.is_empty():
        return str(layout.get("display_name", current_region_id.replace("_", " ").title()))
    return current_region_id.replace("_", " ").title()


func get_discovered_region_count() -> int:
    return _discovered_region_ids.size()


func get_npc_roster() -> Array:
    return npc_roster


func get_quest_arcs() -> Array:
    return quest_arcs


func get_party_roster() -> Dictionary:
    return party_roster_config


func get_active_party_slot_ids() -> Array:
    return party_roster_config.get("active_party_slot_ids", [])


func get_party_summary_text() -> String:
    var active_slot_ids := get_active_party_slot_ids()
    var labels: Array = []
    for slot in party_roster_config.get("party_slots", []):
        if str(slot.get("slot_id", "")) in active_slot_ids:
            labels.append(str(slot.get("display_name", slot.get("hero_id", "Hero"))))
    if labels.is_empty():
        labels.append("Solo Lead")
    return ", ".join(labels)


func get_elemental_matrix() -> Dictionary:
    return elemental_matrix


func get_affinity_summary_text() -> String:
    var affinities := elemental_matrix.get("starter_affinities", [])
    if affinities.is_empty():
        affinities = elemental_matrix.get("affinity_order", [])
    if affinities.is_empty():
        return "steel"
    return ", ".join(affinities)


func get_world_streaming_plan() -> Dictionary:
    return world_streaming_plan


func get_streaming_summary_text() -> String:
    var loaded_regions := world_streaming_plan.get("loaded_region_ids", [get_root_region_id()])
    return "%s / %s" % [
        str(world_streaming_plan.get("strategy", "single_slice_lane")),
        ", ".join(loaded_regions),
    ]


func get_commission_board() -> Dictionary:
    return commission_board


func get_commission_summary_text() -> String:
    var active_commissions := commission_board.get("active_commission_ids", [])
    if active_commissions.is_empty():
        return "no active commissions"
    return "%d active / %s" % [
        active_commissions.size(),
        str(commission_board.get("service_model", "boxed_release_plus_expansions")),
    ]


func get_encounter_specs() -> Array:
    return encounter_specs


func get_active_arc() -> Dictionary:
    return active_arc


func get_active_arc_title() -> String:
    return str(active_arc.get("title", "Purification Path"))


func get_active_arc_progress_text() -> String:
    var beat_total := max(int(active_arc.get("beat_count", 4)), 1)
    return "%d/%d" % [min(_arc_stage_index + 1, beat_total), beat_total]


func get_current_region_purification_total() -> int:
    var count := 0
    for enemy_spec in enemy_specs:
        if str(enemy_spec.get("region_id", get_root_region_id())) != current_region_id:
            continue
        if not _is_boss_enemy_id(str(enemy_spec.get("id", ""))) and bool(enemy_spec.get("critical_path", true)):
            count += 1
    return count


func get_current_region_purification_count() -> int:
    var count := 0
    for enemy_spec in enemy_specs:
        var enemy_id := str(enemy_spec.get("id", ""))
        if str(enemy_spec.get("region_id", get_root_region_id())) != current_region_id:
            continue
        if enemy_id != "" and not _is_boss_enemy_id(enemy_id) and bool(enemy_spec.get("critical_path", true)) and is_enemy_defeated(enemy_id):
            count += 1
    return count


func get_enemy_patrol_route(enemy_id: String) -> Dictionary:
    for route in patrol_route_specs:
        if enemy_id in route.get("assigned_enemy_ids", []):
            return route
    return {}


func get_enemy_alert_network(enemy_id: String) -> Dictionary:
    for network in alert_network_specs:
        if enemy_id in network.get("assigned_enemy_ids", []):
            return network
    return {}


func is_enemy_alerted(enemy_id: String) -> bool:
    var network := get_enemy_alert_network(enemy_id)
    if network.is_empty():
        return false
    var network_id := str(network.get("id", ""))
    if network_id == "" or not _active_alerts.has(network_id):
        return false
    return str(_active_alerts[network_id].get("region_id", "")) == str(network.get("region_id", ""))


func get_alert_position_for_enemy(enemy_id: String) -> Vector3:
    var network := get_enemy_alert_network(enemy_id)
    if network.is_empty():
        return Vector3.ZERO
    var network_id := str(network.get("id", ""))
    if network_id == "" or not _active_alerts.has(network_id):
        return Vector3.ZERO
    return _to_vector3(_active_alerts[network_id].get("position", []), Vector3.ZERO)


func get_region_layout(region_id: String) -> Dictionary:
    for layout in region_layout_specs:
        if str(layout.get("id", "")) == region_id:
            return layout
    return {}


func get_region_spawn_point(region_id: String) -> Vector3:
    var layout := get_region_layout(region_id)
    if not layout.is_empty():
        return _to_vector3(layout.get("spawn_point", [0.0, 1.1, 8.0]), Vector3(0.0, 1.1, 8.0))
    return Vector3(0.0, 1.1, 8.0)


func get_region_objective(region_id: String) -> Dictionary:
    var layout := get_region_layout(region_id)
    var expected_id := str(layout.get("region_objective_id", ""))
    for objective in region_objective_specs:
        var objective_id := str(objective.get("id", ""))
        if expected_id != "" and objective_id == expected_id:
            return objective
        if str(objective.get("region_id", "")) == region_id:
            return objective
    return {}


func get_current_region_objective() -> Dictionary:
    return get_region_objective(current_region_id)


func is_region_objective_complete(objective_id: String) -> bool:
    return objective_id != "" and _completed_region_objective_ids.has(objective_id)


func get_region_objective_progress_text() -> String:
    return "%d/%d" % [_completed_region_objective_ids.size(), region_objective_specs.size()]


func get_current_region_objective_summary() -> String:
    var objective := get_current_region_objective()
    if objective.is_empty():
        return "main shrine route" if current_region_id == get_root_region_id() else "free scouting"
    var label := str(objective.get("label", "Regional Objective"))
    if is_region_objective_complete(str(objective.get("id", ""))):
        return label + " complete"
    if not is_region_objective_ready(str(objective.get("id", ""))):
        return label + " contested"
    return label


func is_region_objective_ready(objective_id: String) -> bool:
    for objective in region_objective_specs:
        if str(objective.get("id", "")) == objective_id:
            var encounter_id := str(objective.get("encounter_id", ""))
            return encounter_id == "" or is_encounter_complete(encounter_id)
    return true


func get_next_region_name() -> String:
    for gateway in region_gateway_specs:
        if str(gateway.get("region_id", "")) == current_region_id:
            return str(gateway.get("target_region", "cloudstep_basin"))
    if region_seeds.size() > 1:
        return str(region_seeds[1].get("id", "cloudstep_basin"))
    return "cloudstep_basin"


func has_spoken_to_npc(npc_id: String) -> bool:
    return _spoken_npc_ids.has(npc_id)


func get_active_encounter_summary() -> String:
    var encounter_label := _active_encounter_label if _active_encounter_label != "" else "roaming"
    if _boss_phase_label != "":
        return encounter_label + " / " + _boss_phase_label
    return encounter_label


func get_reward_site_progress_text() -> String:
    var total := reward_site_specs.size()
    return "%d/%d" % [_claimed_reward_site_ids.size(), total]


func get_closest_target(origin: Vector3, max_distance: float = 999.0) -> Node3D:
    var nearest: Node3D = null
    var nearest_distance := max_distance
    for node in get_tree().get_nodes_in_group("combat_target"):
        if node is Node3D:
            if str(node.get_meta("region_id", current_region_id)) != current_region_id:
                continue
            var distance := origin.distance_to(node.global_position)
            if distance <= nearest_distance:
                nearest = node
                nearest_distance = distance
    return nearest


func notify_player_position(position: Vector3) -> void:
    if current_region_id != get_root_region_id():
        return
    if current_step_id() == "reach_ruins" and position.z <= 0.0:
        current_step_index = _step_index_for("purify_sentinels")
        _advance_arc_stage(1)
        _refresh_objective()
        set_hint("The ruins are ahead. Purify the sentinels to wake the shrine.")


func restore_stamina(delta: float) -> void:
    if slice_complete:
        return
    stamina = min(max_stamina, stamina + delta * get_stamina_restore_rate())


func consume_stamina(amount: float) -> bool:
    if stamina < amount:
        return false
    stamina -= amount
    return true


func damage_player(amount: int) -> void:
    health = max(health - amount, 0)
    if health <= 0:
        status_hint = "Player down. Respawning at the entry marker keeps the slice loop fast."


func register_enemy(enemy_name: String, enemy_id: String = "") -> void:
    var resolved_id := enemy_id if enemy_id != "" else enemy_name.to_lower().replace(" ", "_")
    _enemy_registry[resolved_id] = enemy_name
    enemy_total = _enemy_registry.size()
    enemy_defeated = _defeated_enemy_ids.size()
    _refresh_objective()


func register_enemy_defeat(enemy_name: String, enemy_id: String = "") -> void:
    var resolved_id := enemy_id if enemy_id != "" else enemy_name.to_lower().replace(" ", "_")
    _defeated_enemy_ids[resolved_id] = true
    enemy_defeated = _defeated_enemy_ids.size()
    if _is_boss_enemy_id(resolved_id):
        current_step_index = _step_index_for("activate_shrine")
        _advance_arc_stage(3)
        status_hint = enemy_name + " fell. The shrine is ready."
        _prime_all_gateways()
        SaveService.save_progress("guardian_clear")
    elif _all_regular_enemies_defeated():
        current_step_index = _step_index_for("defeat_warden")
        _advance_arc_stage(2)
        status_hint = enemy_name + " purified. The guardian has awakened near the shrine."
        SaveService.save_progress("combat_clear")
    else:
        status_hint = enemy_name + " purified. Push deeper toward the shrine."
    _refresh_objective()


func is_enemy_defeated(enemy_id: String) -> bool:
    return _defeated_enemy_ids.has(enemy_id)


func can_complete_slice() -> bool:
    return _is_boss_enemy_id("shrine_warden") and is_enemy_defeated("shrine_warden")


func can_activate_goal(goal_id: String) -> bool:
    return goal_id == "activate_shrine" and current_step_id() == "activate_shrine" and can_complete_slice()


func complete_slice() -> void:
    if slice_complete:
        return
    slice_complete = true
    current_step_index = _step_index_for("activate_shrine")
    var reward_id := _unlock_next_reward()
    var next_region := "cloudstep_basin"
    if region_seeds.size() > 1:
        next_region = region_seeds[1].get("id", "cloudstep_basin")
    objective_text = "Slice complete. Expand from this verified base with more authored zones and systems."
    status_hint = "Unlocked %s. Press F5 to save this run, then grow toward %s from the task graph." % [reward_id, next_region]
    emit_signal("slice_completed")


func get_goal_hint() -> String:
    if current_region_id != get_root_region_id():
        var regional_objective := get_current_region_objective()
        if regional_objective.is_empty():
            return "Scout %s and return to the shrine route when you're ready." % [get_current_region_title()]
        if is_region_objective_complete(str(regional_objective.get("id", ""))):
            return "%s complete. Return to the shrine route or keep mapping the frontier." % [str(regional_objective.get("label", "Regional Objective"))]
        if not is_region_objective_ready(str(regional_objective.get("id", ""))):
            return "Clear the defenders around %s before trying to secure it." % [str(regional_objective.get("label", "the regional objective"))]
        var travel_hint := str(regional_objective.get("travel_hint", ""))
        if travel_hint != "":
            return travel_hint
        return str(regional_objective.get("summary", "Secure the current regional objective."))
    if current_step_id() == "meet_guide":
        return "Speak to Keeper Aeris before entering the ruins."
    if current_step_id() == "reach_ruins":
        return "Move forward into the ruins until the combat pocket wakes up."
    if current_step_id() == "purify_sentinels":
        return "Defeat the sentinel escort to reveal the shrine guardian."
    if current_step_id() == "defeat_warden":
        return "The guardian blocks the shrine. Dodge the burst patterns and finish the fight."
    if current_step_id() == "activate_shrine":
        return "The shrine is ready now that the guardian has fallen."
    return "Keep extending the slice from this verified state."


func get_reward_summary() -> String:
    if unlocked_rewards.is_empty():
        return "none yet"
    return ", ".join(unlocked_rewards)


func get_locked_target_name() -> String:
    return _locked_target_name


func set_locked_target_name(value: String) -> void:
    _locked_target_name = value


func is_lock_on_enabled() -> bool:
    return bool(combat_config.get("player_actions", {}).get("lock_on_enabled", true))


func get_move_speed_multiplier() -> float:
    var multiplier := 1.15 if unlocked_rewards.has("wind_step") else 1.0
    if unlocked_rewards.has("route_sigil"):
        multiplier += 0.04
    if unlocked_rewards.has("basin_insight"):
        multiplier += 0.05
    if unlocked_rewards.has("watch_resonance"):
        multiplier += 0.03
    return multiplier


func get_combo_chain() -> Array:
    return combat_config.get("player_actions", {}).get("combo_chain", _default_combat().get("player_actions", {}).get("combo_chain", []))


func get_primary_skill() -> Dictionary:
    var actions := combat_config.get("player_actions", {})
    var primary := actions.get("skill_loadout", {}).get(
        "primary",
        _default_combat().get("player_actions", {}).get("skill_loadout", {}).get("primary", {}),
    )
    if primary.is_empty():
        return {
            "id": str(actions.get("skill_name", "focus_burst")),
            "name": str(actions.get("skill_name", "focus_burst")),
            "damage": int(actions.get("skill_damage", 3)),
            "range": float(actions.get("skill_range", 5.6)),
            "stamina_cost": float(actions.get("skill_stamina_cost", 32.0)),
            "cooldown": float(actions.get("skill_cooldown", 2.2)),
            "hit_reaction_seconds": 0.34,
            "poise_damage": 3.2,
        }
    return primary


func get_heavy_skill() -> Dictionary:
    return combat_config.get("player_actions", {}).get("skill_loadout", {}).get(
        "heavy",
        _default_combat().get("player_actions", {}).get("skill_loadout", {}).get("heavy", {}),
    )


func get_guard_profile() -> Dictionary:
    return combat_config.get("player_actions", {}).get(
        "guard",
        _default_combat().get("player_actions", {}).get("guard", {}),
    )


func get_pattern_library() -> Dictionary:
    return combat_config.get("pattern_library", _default_combat().get("pattern_library", {}))


func get_enemy_pattern_profile(enemy_id: String, pattern_id: String = "") -> Dictionary:
    var pattern_library := get_pattern_library()
    var resolved_pattern_id := pattern_id
    if resolved_pattern_id == "":
        for enemy_spec in enemy_specs:
            if str(enemy_spec.get("id", "")) == enemy_id:
                resolved_pattern_id = str(enemy_spec.get("pattern_profile_id", ""))
                break
    if resolved_pattern_id == "":
        return {}
    return pattern_library.get(resolved_pattern_id, {})


func get_enemy_phase_profile(enemy_id: String, pattern_id: String = "", phase_number: int = 1) -> Dictionary:
    var profile := get_enemy_pattern_profile(enemy_id, pattern_id)
    for phase_profile in profile.get("phase_profiles", []):
        if int(phase_profile.get("phase", 1)) == phase_number:
            var resolved := {}
            resolved.merge(profile, true)
            resolved.merge(phase_profile, true)
            return resolved
    return {}


func get_attack_damage() -> int:
    var combo_chain := get_combo_chain()
    var base_damage := int(combat_config.get("player_actions", {}).get("basic_attack_damage", 1))
    if not combo_chain.is_empty():
        base_damage = int(combo_chain[0].get("damage", base_damage))
    return base_damage + 1 if unlocked_rewards.has("focus_strike") else base_damage


func get_skill_damage() -> int:
    return int(get_primary_skill().get("damage", 3))


func get_skill_range() -> float:
    var range_value := float(get_primary_skill().get("range", 5.6))
    if unlocked_rewards.has("basin_insight"):
        range_value += 0.9
    return range_value


func get_skill_stamina_cost() -> float:
    return float(get_primary_skill().get("stamina_cost", 32.0))


func get_skill_cooldown() -> float:
    var cooldown := float(get_primary_skill().get("cooldown", 2.2))
    if unlocked_rewards.has("watch_resonance"):
        cooldown = max(0.8, cooldown - 0.35)
    return cooldown


func get_skill_name() -> String:
    return str(get_primary_skill().get("name", "focus_burst"))


func get_heavy_skill_name() -> String:
    return str(get_heavy_skill().get("name", "skybreak"))


func get_heavy_skill_cooldown() -> float:
    var cooldown := float(get_heavy_skill().get("cooldown", 4.8))
    if unlocked_rewards.has("watch_resonance"):
        cooldown = max(1.6, cooldown - 0.7)
    return cooldown


func get_player_hit_reaction_seconds() -> float:
    return float(combat_config.get("player_actions", {}).get("player_hurt_reaction_seconds", 0.24))


func is_guard_enabled() -> bool:
    return bool(get_guard_profile().get("enabled", true))


func get_guard_stamina_drain_per_second() -> float:
    return float(get_guard_profile().get("stamina_drain_per_second", 12.0))


func get_guard_damage_reduction() -> float:
    var reduction := float(get_guard_profile().get("damage_reduction", 0.72))
    if unlocked_rewards.has("route_sigil"):
        reduction += 0.06
    return min(reduction, 0.9)


func get_perfect_guard_window_seconds() -> float:
    var timing := float(get_guard_profile().get("perfect_guard_window_seconds", 0.18))
    if unlocked_rewards.has("route_sigil"):
        timing += 0.04
    return timing


func get_guard_counter_poise_damage() -> float:
    return float(get_guard_profile().get("counter_poise_damage", 3.6))


func get_dash_iframe_seconds() -> float:
    var iframe_seconds := float(combat_config.get("player_actions", {}).get("dash_i_frames_seconds", 0.22))
    if unlocked_rewards.has("basin_insight"):
        iframe_seconds += 0.03
    return iframe_seconds


func get_stamina_restore_rate() -> float:
    var rate := 22.0 if unlocked_rewards.has("resonant_guard") else 18.0
    if unlocked_rewards.has("route_sigil"):
        rate += 3.0
    if unlocked_rewards.has("basin_insight"):
        rate += 1.5
    if unlocked_rewards.has("watch_resonance"):
        rate += 2.0
    return rate


func register_npc_interaction(npc_id: String, display_name: String, npc_role: String, function_summary: String, home_region: String) -> void:
    _spoken_npc_ids[npc_id] = true
    if npc_id == "keeper_aeris" and current_step_id() == "meet_guide":
        current_step_index = _step_index_for("reach_ruins")
        _advance_arc_stage(0)
        status_hint = "%s (%s): %s Route locked for %s." % [display_name, npc_role, function_summary, home_region]
        _refresh_objective()
        return
    status_hint = "%s (%s): %s" % [display_name, npc_role, function_summary]


func _is_boss_enemy_id(enemy_id: String) -> bool:
    for enemy_spec in enemy_specs:
        if str(enemy_spec.get("id", "")) == enemy_id:
            return str(enemy_spec.get("combat_tier", "standard")) == "boss"
    return enemy_id == "shrine_warden"


func _regular_enemy_total() -> int:
    var count := 0
    for enemy_spec in enemy_specs:
        if str(enemy_spec.get("region_id", get_root_region_id())) != get_root_region_id():
            continue
        if not _is_boss_enemy_id(str(enemy_spec.get("id", ""))) and bool(enemy_spec.get("critical_path", true)):
            count += 1
    return count


func _regular_enemy_defeated_count() -> int:
    var count := 0
    for enemy_spec in enemy_specs:
        var enemy_id := str(enemy_spec.get("id", ""))
        if str(enemy_spec.get("region_id", get_root_region_id())) != get_root_region_id():
            continue
        if enemy_id != "" and not _is_boss_enemy_id(enemy_id) and bool(enemy_spec.get("critical_path", true)) and is_enemy_defeated(enemy_id):
            count += 1
    return count


func _all_regular_enemies_defeated() -> bool:
    return _regular_enemy_total() > 0 and _regular_enemy_defeated_count() >= _regular_enemy_total()


func _advance_arc_stage(target_index: int) -> void:
    _arc_stage_index = max(_arc_stage_index, target_index)


func _prime_all_gateways() -> void:
    for gateway_spec in region_gateway_specs:
        var gateway_id := str(gateway_spec.get("id", ""))
        if gateway_id != "" and bool(gateway_spec.get("requires_primed", true)):
            _primed_gateway_ids[gateway_id] = true


func is_gateway_primed(gateway_id: String) -> bool:
    return _primed_gateway_ids.has(gateway_id)


func can_travel_gateway(gateway_id: String) -> bool:
    for gateway_spec in region_gateway_specs:
        if str(gateway_spec.get("id", "")) == gateway_id:
            if not bool(gateway_spec.get("requires_primed", true)):
                return true
            return slice_complete or is_gateway_primed(gateway_id)
    return slice_complete or is_gateway_primed(gateway_id)


func travel_to_region(gateway_id: String, target_region: String, target_spawn: Array = []) -> bool:
    if target_region == "":
        return false
    if not can_travel_gateway(gateway_id):
        return false
    current_region_id = target_region
    _discovered_region_ids[target_region] = true
    var destination := get_region_spawn_point(target_region)
    if target_spawn is Array and target_spawn.size() >= 3:
        destination = _to_vector3(target_spawn, destination)
    player_spawn_point = destination
    var player := get_player()
    if player != null:
        player.global_position = destination
        if player.has_method("set"):
            player.set("velocity", Vector3.ZERO)
    else:
        _pending_player_position = destination
        _has_pending_player_position = true
    _active_encounter_id = ""
    _active_encounter_label = ""
    _boss_phase_label = ""
    _active_alerts.clear()
    _refresh_objective()
    var travel_hint := get_goal_hint()
    status_hint = travel_hint
    emit_signal("region_changed", current_region_id)
    SaveService.save_progress("region_travel")
    status_hint = travel_hint
    return true


func raise_alert(enemy_id: String, position: Vector3, region_id: String, duration_seconds: float = 4.5) -> void:
    var network := get_enemy_alert_network(enemy_id)
    if network.is_empty():
        return
    var network_id := str(network.get("id", ""))
    if network_id == "":
        return
    var resolved_duration := max(duration_seconds, float(network.get("duration_seconds", duration_seconds)))
    var existing := _active_alerts.get(network_id, {})
    var previous_position := _to_vector3(existing.get("position", []), position)
    var previous_region := str(existing.get("region_id", ""))
    var should_announce := previous_region != region_id or previous_position.distance_to(position) > 2.5 or float(existing.get("ttl", 0.0)) <= 0.1
    _active_alerts[network_id] = {
        "region_id": region_id,
        "position": _vector3_to_array(position),
        "ttl": resolved_duration,
        "label": str(network.get("label", network_id)),
    }
    if should_announce and current_region_id == region_id:
        status_hint = "%s triggered. Nearby defenders are converging." % [str(network.get("label", "Regional Alert"))]


func is_encounter_complete(encounter_id: String) -> bool:
    return _completed_encounter_ids.has(encounter_id)


func is_reward_site_claimed(site_id: String) -> bool:
    return _claimed_reward_site_ids.has(site_id)


func is_reward_site_ready(site_id: String) -> bool:
    for reward_site in reward_site_specs:
        if str(reward_site.get("id", "")) == site_id:
            var encounter_id := str(reward_site.get("encounter_id", ""))
            return encounter_id == "" or is_encounter_complete(encounter_id)
    return false


func capture_save_state(reason: String = "manual") -> Dictionary:
    var payload := {
        "schema_version": int(save_schema.get("schema_version", 1)),
        "reason": reason,
        "health": health,
        "stamina": stamina,
        "current_step_index": current_step_index,
        "slice_complete": slice_complete,
        "defeated_enemy_ids": _defeated_enemy_ids.keys(),
        "spoken_npc_ids": _spoken_npc_ids.keys(),
        "primed_gateway_ids": _primed_gateway_ids.keys(),
        "completed_encounter_ids": _completed_encounter_ids.keys(),
        "claimed_reward_site_ids": _claimed_reward_site_ids.keys(),
        "completed_region_objective_ids": _completed_region_objective_ids.keys(),
        "arc_stage_index": _arc_stage_index,
        "unlocked_rewards": unlocked_rewards,
        "objective_text": objective_text,
        "active_encounter_id": _active_encounter_id,
        "active_encounter_label": _active_encounter_label,
        "boss_phase_label": _boss_phase_label,
        "current_region_id": current_region_id,
        "discovered_region_ids": _discovered_region_ids.keys(),
    }
    var player := get_player()
    if player != null:
        payload["player_transform"] = _vector3_to_array(player.global_position)
    return payload


func apply_save_state(payload: Dictionary) -> void:
    ensure_runtime_data()
    health = clamp(int(payload.get("health", max_health)), 0, max_health)
    stamina = clamp(float(payload.get("stamina", max_stamina)), 0.0, max_stamina)
    current_step_index = clamp(int(payload.get("current_step_index", 0)), 0, max(quest_steps.size() - 1, 0))
    slice_complete = bool(payload.get("slice_complete", false))
    unlocked_rewards = []
    for reward_id in payload.get("unlocked_rewards", []):
        unlocked_rewards.append(str(reward_id))
    _defeated_enemy_ids.clear()
    for enemy_id in payload.get("defeated_enemy_ids", []):
        _defeated_enemy_ids[str(enemy_id)] = true
    _spoken_npc_ids.clear()
    for npc_id in payload.get("spoken_npc_ids", []):
        _spoken_npc_ids[str(npc_id)] = true
    _primed_gateway_ids.clear()
    for gateway_id in payload.get("primed_gateway_ids", []):
        _primed_gateway_ids[str(gateway_id)] = true
    _completed_encounter_ids.clear()
    for encounter_id in payload.get("completed_encounter_ids", []):
        _completed_encounter_ids[str(encounter_id)] = true
    _claimed_reward_site_ids.clear()
    for site_id in payload.get("claimed_reward_site_ids", []):
        _claimed_reward_site_ids[str(site_id)] = true
    _completed_region_objective_ids.clear()
    for objective_id in payload.get("completed_region_objective_ids", []):
        _completed_region_objective_ids[str(objective_id)] = true
    _discovered_region_ids.clear()
    for region_id in payload.get("discovered_region_ids", []):
        _discovered_region_ids[str(region_id)] = true
    _arc_stage_index = int(payload.get("arc_stage_index", 0))
    _active_encounter_id = str(payload.get("active_encounter_id", ""))
    _active_encounter_label = str(payload.get("active_encounter_label", ""))
    _boss_phase_label = str(payload.get("boss_phase_label", ""))
    _active_alerts.clear()
    current_region_id = str(payload.get("current_region_id", get_root_region_id()))
    enemy_defeated = _defeated_enemy_ids.size()

    if _discovered_region_ids.is_empty():
        _discovered_region_ids[current_region_id] = true
    player_spawn_point = get_region_spawn_point(current_region_id)
    var player_position := _to_vector3(payload.get("player_transform", _vector3_to_array(player_spawn_point)), player_spawn_point)
    var player := get_player()
    if player != null:
        player.global_position = player_position
    else:
        _pending_player_position = player_position
        _has_pending_player_position = true

    for node in get_tree().get_nodes_in_group("combat_target"):
        var node_enemy_id := str(node.get("enemy_id"))
        if node.has_method("restore_from_save_state"):
            node.restore_from_save_state(is_enemy_defeated(node_enemy_id))

    _refresh_objective()
    emit_signal("region_changed", current_region_id)
    status_hint = "Loaded saved slice progress. Finish the current step or push for completion."


func current_step_id() -> String:
    if quest_steps.is_empty():
        return "activate_shrine"
    return str(quest_steps[min(current_step_index, quest_steps.size() - 1)].get("id", "activate_shrine"))


func set_hint(text: String) -> void:
    status_hint = text


func set_active_encounter(encounter_id: String, label: String, hint: String = "") -> void:
    if encounter_id == "":
        return
    _active_encounter_id = encounter_id
    _active_encounter_label = label
    if hint != "":
        _active_encounter_hint = hint
        status_hint = hint


func complete_encounter(encounter_id: String) -> void:
    if encounter_id == "":
        return
    if _completed_encounter_ids.has(encounter_id):
        return
    _completed_encounter_ids[encounter_id] = true
    if encounter_id == _active_encounter_id:
        _active_encounter_label = _active_encounter_label + " cleared"
        status_hint = "Encounter cleared: %s. Keep pushing the arc forward." % [_active_encounter_label]
    for reward_site in reward_site_specs:
        if str(reward_site.get("encounter_id", "")) == encounter_id:
            status_hint = "Encounter cleared: %s. %s is now ready." % [
                _active_encounter_label if _active_encounter_label != "" else encounter_id,
                str(reward_site.get("label", "Reward Cache")),
            ]
    if encounter_id == "shrine_guardian_finale":
        _boss_phase_label = ""


func set_boss_phase(enemy_id: String, phase_label: String, hint: String = "") -> void:
    if not _is_boss_enemy_id(enemy_id):
        return
    _boss_phase_label = phase_label
    if hint != "":
        status_hint = hint


func claim_reward_site(site_id: String, reward_id: String, label: String, summary: String, encounter_id: String = "") -> bool:
    if site_id == "":
        return false
    if is_reward_site_claimed(site_id):
        status_hint = label + " already claimed."
        return false
    if encounter_id != "" and not is_encounter_complete(encounter_id):
        status_hint = label + " is still sealed. Clear the detour first."
        return false
    _claimed_reward_site_ids[site_id] = true
    if reward_id != "" and not unlocked_rewards.has(reward_id):
        unlocked_rewards.append(reward_id)
    status_hint = "%s opened. %s unlocked." % [label, reward_id if reward_id != "" else summary]
    SaveService.save_progress("detour_reward")
    return true


func complete_region_objective(objective_id: String, reward_id: String, label: String, summary: String, region_id: String, encounter_id: String = "") -> bool:
    if objective_id == "":
        return false
    if is_region_objective_complete(objective_id):
        status_hint = label + " already secured."
        return false
    if encounter_id != "" and not is_encounter_complete(encounter_id):
        status_hint = label + " is still contested. Clear the regional encounter first."
        return false
    _completed_region_objective_ids[objective_id] = true
    if reward_id != "" and not unlocked_rewards.has(reward_id):
        unlocked_rewards.append(reward_id)
    _refresh_objective()
    var reward_summary := reward_id if reward_id != "" else summary
    status_hint = "%s secured in %s. %s unlocked for future passes." % [
        label,
        region_id.replace("_", " ").title(),
        reward_summary,
    ]
    SaveService.save_progress("region_objective")
    status_hint = "%s secured in %s. %s unlocked for future passes." % [
        label,
        region_id.replace("_", " ").title(),
        reward_summary,
    ]
    return true


func _refresh_objective() -> void:
    if current_region_id != get_root_region_id():
        objective_text = _objective_text_for_region(current_region_id)
        return
    if slice_complete:
        objective_text = "Slice complete. Expand from this verified base with more authored zones and systems."
        return
    objective_text = _objective_text_for_step(current_step_index)


func _objective_text_for_region(region_id: String) -> String:
    var layout := get_region_layout(region_id)
    var region_title := str(layout.get("display_name", region_id.replace("_", " ").title()))
    var objective := get_region_objective(region_id)
    if objective.is_empty():
        return "Scout %s and record future slice hooks." % [region_title]
    var objective_id := str(objective.get("id", ""))
    var label := str(objective.get("label", "Regional Objective"))
    if is_region_objective_complete(objective_id):
        return "%s complete. Return to the shrine route or continue frontier scouting." % [label]
    var reward_id := str(objective.get("reward_id", "frontier_data"))
    return "%s in %s to unlock %s." % [label, region_title, reward_id]


func _objective_text_for_step(step_index: int) -> String:
    var step_id := "activate_shrine"
    if not quest_steps.is_empty():
        step_id = str(quest_steps[min(step_index, quest_steps.size() - 1)].get("id", "activate_shrine"))
    if step_id == "meet_guide":
        return "Speak to Keeper Aeris to lock the first route and begin the arc."
    if step_id == "reach_ruins":
        return "Reach the ruins and locate the corrupted sentinels."
    if step_id == "purify_sentinels":
        return "Purify the sentinel escort (%d/%d) and reveal the shrine guardian." % [_regular_enemy_defeated_count(), _regular_enemy_total()]
    if step_id == "defeat_warden":
        return "Defeat the Shrine Warden to unlock the shrine."
    if can_complete_slice():
        return "Guardian defeated. Activate the shrine to complete the slice."
    return "The shrine is dormant. Clear the route and defeat the guardian first."


func _unlock_next_reward() -> String:
    var nodes := reward_track.get("nodes", [])
    for node in nodes:
        var reward_id := str(node.get("id", "reward"))
        if not unlocked_rewards.has(reward_id):
            unlocked_rewards.append(reward_id)
            return reward_id
    return "slice_core"


func _step_index_for(step_id: String) -> int:
    for index in range(quest_steps.size()):
        if str(quest_steps[index].get("id", "")) == step_id:
            return index
    return max(quest_steps.size() - 1, 0)


func _merge_enemy_specs(base_specs: Array, default_specs: Array) -> Array:
    var default_map := {}
    for item in default_specs:
        if item is Dictionary:
            default_map[str(item.get("id", ""))] = item

    var merged: Array = []
    for item in base_specs:
        if item is Dictionary:
            var enemy_id := str(item.get("id", ""))
            var archetype_id := str(item.get("archetype_id", enemy_id))
            var resolved := {}
            if default_map.has(archetype_id):
                resolved.merge(default_map[archetype_id], true)
            elif default_map.has(enemy_id):
                resolved.merge(default_map[enemy_id], true)
            resolved.merge(item, true)
            merged.append(resolved)
    return merged


func _load_json_resource(path: String, fallback: Variant) -> Variant:
    if not FileAccess.file_exists(path):
        return fallback
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:
        return fallback
    var parsed := JSON.parse_string(file.get_as_text())
    if parsed == null:
        return fallback
    return parsed


func _to_vector3(values: Variant, fallback: Vector3) -> Vector3:
    if values is Array and values.size() >= 3:
        return Vector3(float(values[0]), float(values[1]), float(values[2]))
    return fallback


func _vector3_to_array(value: Vector3) -> Array:
    return [value.x, value.y, value.z]


func _default_quest_flow() -> Dictionary:
    return {
        "objectives": [
            {"id": "meet_guide", "goal": "Speak to Keeper Aeris"},
            {"id": "reach_ruins", "goal": "Enter the combat-ready space"},
            {"id": "purify_sentinels", "goal": "Defeat the sentinel escort"},
            {"id": "defeat_warden", "goal": "Defeat the shrine guardian"},
            {"id": "activate_shrine", "goal": "Activate the shrine"},
        ]
    }


func _default_combat() -> Dictionary:
    return {
        "player_actions": {
            "lock_on_enabled": true,
            "basic_attack_damage": 1,
            "combo_chain": [
                {"id": "light_slash_1", "damage": 1, "cooldown": 0.42, "stamina_cost": 0.0, "hit_range": 3.2, "combo_window_seconds": 0.68, "hit_reaction_seconds": 0.16, "poise_damage": 1.0},
                {"id": "light_slash_2", "damage": 2, "cooldown": 0.38, "stamina_cost": 6.0, "hit_range": 3.35, "combo_window_seconds": 0.62, "hit_reaction_seconds": 0.20, "poise_damage": 1.4},
                {"id": "light_slash_finisher", "damage": 3, "cooldown": 0.58, "stamina_cost": 10.0, "hit_range": 3.8, "combo_window_seconds": 0.0, "hit_reaction_seconds": 0.28, "poise_damage": 2.6},
            ],
            "skill_loadout": {
                "primary": {"id": "focus_burst", "name": "focus_burst", "damage": 3, "range": 5.6, "stamina_cost": 32.0, "cooldown": 2.2, "hit_reaction_seconds": 0.34, "poise_damage": 3.2},
                "heavy": {"id": "skybreak", "name": "skybreak", "damage": 5, "range": 4.8, "stamina_cost": 40.0, "cooldown": 4.8, "hit_reaction_seconds": 0.42, "poise_damage": 4.8},
            },
            "skill_name": "focus_burst",
            "skill_damage": 3,
            "skill_range": 5.6,
            "skill_stamina_cost": 32.0,
            "skill_cooldown": 2.2,
            "guard": {"enabled": true, "stamina_drain_per_second": 12.0, "damage_reduction": 0.72, "perfect_guard_window_seconds": 0.18, "counter_poise_damage": 3.6},
            "player_hurt_reaction_seconds": 0.24,
            "dash_i_frames_seconds": 0.22,
        },
        "enemy_defaults": [
            {
                "id": "sentinel_melee",
                "pattern_profile_id": "sentinel_duelist",
                "combat_role": "melee",
                "combat_tier": "standard",
                "desired_range": 1.9,
                "projectile_speed": 0.0,
                "projectile_damage": 0,
                "projectile_cooldown": 0.0,
                "projectile_lifetime": 0.0,
                "max_poise": 3.0,
                "poise_recovery_per_second": 1.4,
                "stagger_duration": 0.32,
            },
            {
                "id": "sentinel_ranged",
                "pattern_profile_id": "sentinel_volley",
                "combat_role": "ranged",
                "combat_tier": "standard",
                "desired_range": 7.5,
                "projectile_speed": 13.0,
                "projectile_damage": 6,
                "projectile_cooldown": 2.0,
                "projectile_lifetime": 3.0,
                "max_poise": 2.6,
                "poise_recovery_per_second": 1.6,
                "stagger_duration": 0.28,
            },
            {
                "id": "sentinel_elite",
                "pattern_profile_id": "elite_vanguard",
                "combat_role": "elite",
                "combat_tier": "elite",
                "desired_range": 2.7,
                "projectile_speed": 0.0,
                "projectile_damage": 0,
                "projectile_cooldown": 0.0,
                "projectile_lifetime": 0.0,
                "max_poise": 5.4,
                "poise_recovery_per_second": 1.2,
                "stagger_duration": 0.36,
            },
            {
                "id": "shrine_warden",
                "pattern_profile_id": "shrine_guardian",
                "combat_role": "boss",
                "combat_tier": "boss",
                "desired_range": 5.0,
                "projectile_speed": 11.5,
                "projectile_damage": 9,
                "projectile_cooldown": 2.6,
                "projectile_lifetime": 3.2,
                "max_poise": 8.0,
                "poise_recovery_per_second": 1.1,
                "stagger_duration": 0.40,
            },
        ],
        "pattern_library": {
            "sentinel_duelist": {
                "id": "sentinel_duelist",
                "label": "Sentinel Duelist",
                "behavior_mode": "duelist",
                "phase_profiles": [
                    {"phase": 1, "label": "Pressure Advance", "attack_windup_seconds": 0.40, "attack_cooldown": 1.05, "move_speed_bonus": 0.0, "contact_bonus": 0, "lunge_speed": 0.0, "lunge_distance_threshold": 0.0, "hint": "The melee sentinel pins the lane for the volley unit."},
                ],
            },
            "sentinel_volley": {
                "id": "sentinel_volley",
                "label": "Sentinel Volley",
                "behavior_mode": "kite_and_volley",
                "phase_profiles": [
                    {"phase": 1, "label": "Volley Spacing", "attack_windup_seconds": 0.0, "attack_cooldown": 1.85, "projectile_cooldown": 1.9, "desired_range": 7.8, "move_speed_bonus": 0.0, "contact_bonus": 0, "hint": "The ranged sentinel backs off to keep the lane covered."},
                ],
            },
            "elite_vanguard": {
                "id": "elite_vanguard",
                "label": "Elite Vanguard",
                "behavior_mode": "elite_brutalizer",
                "phase_profiles": [
                    {"phase": 1, "label": "Detour Keeper", "attack_windup_seconds": 0.46, "attack_cooldown": 1.18, "desired_range": 2.7, "move_speed_bonus": 0.15, "contact_bonus": 1, "lunge_speed": 9.0, "lunge_distance_threshold": 4.2, "hint": "The elite guards the cache route with heavier pressure."},
                    {"phase": 2, "label": "Cache Breaker", "attack_windup_seconds": 0.36, "attack_cooldown": 0.96, "desired_range": 2.4, "move_speed_bonus": 0.38, "contact_bonus": 3, "lunge_speed": 10.4, "lunge_distance_threshold": 4.8, "hint": "The elite rushes harder once wounded."},
                ],
            },
            "shrine_guardian": {
                "id": "shrine_guardian",
                "label": "Shrine Guardian",
                "behavior_mode": "boss_pattern",
                "phase_profiles": [
                    {"phase": 1, "label": "Survey Burst", "attack_windup_seconds": 0.54, "attack_cooldown": 1.55, "projectile_cooldown": 2.5, "burst_cooldown": 4.2, "desired_range": 5.2, "move_speed_bonus": 0.0, "contact_bonus": 0, "lunge_speed": 8.5, "lunge_distance_threshold": 4.8, "hint": "Survey Burst tests the first defensive read."},
                    {"phase": 2, "label": "Resonant Chase", "attack_windup_seconds": 0.46, "attack_cooldown": 1.25, "projectile_cooldown": 2.0, "burst_cooldown": 3.3, "desired_range": 4.5, "move_speed_bonus": 0.35, "contact_bonus": 2, "lunge_speed": 10.0, "lunge_distance_threshold": 5.4, "hint": "Resonant Chase compresses punish windows."},
                    {"phase": 3, "label": "Final Breaker", "attack_windup_seconds": 0.36, "attack_cooldown": 0.95, "projectile_cooldown": 1.65, "burst_cooldown": 2.6, "desired_range": 4.0, "move_speed_bonus": 0.7, "contact_bonus": 4, "lunge_speed": 11.5, "lunge_distance_threshold": 6.0, "hint": "Final Breaker demands disciplined guard and stagger timing."},
                ],
            },
        },
    }


func _default_progression() -> Dictionary:
    return {
        "id": "slice_core",
        "nodes": [
            {"id": "wind_step"},
            {"id": "focus_strike"},
            {"id": "resonant_guard"},
            {"id": "basin_insight"},
            {"id": "watch_resonance"},
        ],
    }


func _default_world_slice() -> Dictionary:
    return {
        "landmarks": ["entry_arch", "combat_pocket", "purification_shrine"],
        "patrol_route_ids": ["starter_watch_loop", "cloudstep_relay_arc", "echo_spire_sweep"],
        "alert_network_ids": ["starter_intro_alert", "cloudstep_relay_alert", "echo_spire_alert"],
    }


func _default_save_schema() -> Dictionary:
    return {
        "schema_version": 1,
        "fields": [
            "player_transform",
            "health",
            "stamina",
            "current_step_index",
            "defeated_enemy_ids",
            "completed_encounter_ids",
            "claimed_reward_site_ids",
            "completed_region_objective_ids",
            "current_region_id",
            "discovered_region_ids",
            "unlocked_rewards",
        ],
    }


func _default_region_seeds() -> Dictionary:
    return {
        "regions": [
            {"id": "starter_ruins", "biome": "wind-carved ruins", "purpose": "onboard traversal and shrine combat"},
            {"id": "cloudstep_basin", "biome": "tiered canyon wetlands", "purpose": "teach vertical routing and ranged pressure"},
            {"id": "echo_watch", "biome": "highland observatory frontier", "purpose": "seed elite encounters and stronger story beats"},
        ],
    }


func _default_region_layouts() -> Dictionary:
    return {
        "active_region_id": "starter_ruins",
        "regions": [
            {"id": "starter_ruins", "display_name": "Starter Ruins", "summary": "The onboarding shrine district.", "spawn_point": [0.0, 1.1, 8.0], "center": [0.0, 0.0, 0.0], "region_objective_id": "", "preview_landmarks": []},
            {
                "id": "cloudstep_basin",
                "display_name": "Cloudstep Basin",
                "summary": "A wider traversal basin that previews ranged pressure.",
                "spawn_point": [72.0, 1.1, 8.0],
                "center": [72.0, 0.0, 0.0],
                "region_objective_id": "cloudstep_relay",
                "preview_landmarks": [
                    {"id": "cloudstep_basin_watchtower", "position": [68.0, 1.3, -10.0], "size": [3.0, 3.0, 3.0], "color": [0.42, 0.55, 0.44]},
                    {"id": "cloudstep_basin_relay", "position": [81.0, 1.1, -14.0], "size": [2.4, 2.2, 2.4], "color": [0.32, 0.62, 0.58]},
                ],
            },
            {
                "id": "echo_watch",
                "display_name": "Echo Watch",
                "summary": "A frontier observatory region for elite escalation.",
                "spawn_point": [-72.0, 1.1, 8.0],
                "center": [-72.0, 0.0, 0.0],
                "region_objective_id": "echo_spire",
                "preview_landmarks": [
                    {"id": "echo_watch_spire", "position": [-76.0, 1.4, -11.0], "size": [3.4, 3.6, 3.4], "color": [0.44, 0.42, 0.62]},
                    {"id": "echo_watch_signal", "position": [-63.0, 1.0, -13.0], "size": [2.6, 2.1, 2.6], "color": [0.58, 0.44, 0.66]},
                ],
            },
        ],
}


func _default_region_objectives() -> Dictionary:
    return {
        "objectives": [
            {
                "id": "cloudstep_relay",
                "region_id": "cloudstep_basin",
                "label": "Stabilize the Survey Relay",
                "summary": "Activate the basin relay and secure a cleaner route for future expansion passes.",
                "reward_id": "basin_insight",
                "encounter_id": "cloudstep_relay_push",
                "position": [81.0, 0.0, -14.0],
                "color": [0.44, 0.86, 0.78],
                "travel_hint": "Head toward the basin relay and stabilize the route.",
            },
            {
                "id": "echo_spire",
                "region_id": "echo_watch",
                "label": "Calibrate the Echo Spire",
                "summary": "Re-tune the observatory spire to reveal stronger frontier signals.",
                "reward_id": "watch_resonance",
                "encounter_id": "echo_spire_hold",
                "position": [-76.0, 0.0, -11.0],
                "color": [0.86, 0.74, 1.0],
                "travel_hint": "Climb to the spire and restore the observatory signal.",
            },
        ],
    }


func _default_patrol_routes() -> Dictionary:
    return {
        "routes": [
            {
                "id": "starter_watch_loop",
                "region_id": "starter_ruins",
                "label": "Starter Watch Loop",
                "assigned_enemy_ids": ["sentinel_melee", "sentinel_ranged"],
                "loop": true,
                "wait_seconds": 0.85,
                "path_points": [[-4.0, 0.0, -1.5], [1.5, 0.0, -5.5], [6.0, 0.0, -8.5]],
                "purpose": "keep the shrine approach under light pressure",
            },
            {
                "id": "cloudstep_relay_arc",
                "region_id": "cloudstep_basin",
                "label": "Cloudstep Relay Arc",
                "assigned_enemy_ids": ["cloudstep_basin_sentinel_melee", "cloudstep_basin_sentinel_ranged"],
                "loop": true,
                "wait_seconds": 0.9,
                "path_points": [[73.5, 0.0, -4.5], [78.0, 0.0, -9.5], [82.0, 0.0, -13.0]],
                "purpose": "sweep the basin approach before the relay objective",
            },
            {
                "id": "echo_spire_sweep",
                "region_id": "echo_watch",
                "label": "Echo Spire Sweep",
                "assigned_enemy_ids": ["echo_watch_sentinel_ranged", "echo_watch_sentinel_elite"],
                "loop": true,
                "wait_seconds": 1.0,
                "path_points": [[-68.0, 0.0, -4.0], [-72.5, 0.0, -8.5], [-76.0, 0.0, -12.0]],
                "purpose": "hold the observatory lane before the spire can be reclaimed",
            },
        ],
    }


func _default_alert_networks() -> Dictionary:
    return {
        "networks": [
            {
                "id": "starter_intro_alert",
                "region_id": "starter_ruins",
                "label": "Starter Intro Alert",
                "assigned_enemy_ids": ["sentinel_melee", "sentinel_ranged"],
                "duration_seconds": 4.5,
                "search_duration_seconds": 3.0,
                "response_radius": 12.0,
                "anchor_point": [1.0, 0.0, -5.0],
                "purpose": "let shrine sentinels reinforce each other during the first route push",
            },
            {
                "id": "cloudstep_relay_alert",
                "region_id": "cloudstep_basin",
                "label": "Cloudstep Relay Alert",
                "assigned_enemy_ids": ["cloudstep_basin_sentinel_melee", "cloudstep_basin_sentinel_ranged"],
                "duration_seconds": 5.0,
                "search_duration_seconds": 3.4,
                "response_radius": 14.0,
                "anchor_point": [79.0, 0.0, -10.0],
                "purpose": "let relay defenders collapse toward the basin alert lane",
            },
            {
                "id": "echo_spire_alert",
                "region_id": "echo_watch",
                "label": "Echo Spire Alert",
                "assigned_enemy_ids": ["echo_watch_sentinel_ranged", "echo_watch_sentinel_elite"],
                "duration_seconds": 5.5,
                "search_duration_seconds": 3.8,
                "response_radius": 14.0,
                "anchor_point": [-73.0, 0.0, -9.5],
                "purpose": "let observatory defenders reinforce the spire approach",
            },
        ],
    }


func _default_world_graph() -> Dictionary:
    return {
        "nodes": [
            {"id": "starter_ruins", "display_name": "Starter Ruins", "summary": "The onboarding shrine district.", "region_objective_id": ""},
            {"id": "cloudstep_basin", "display_name": "Cloudstep Basin", "summary": "The first expansion basin.", "region_objective_id": "cloudstep_relay"},
            {"id": "echo_watch", "display_name": "Echo Watch", "summary": "The observatory frontier.", "region_objective_id": "echo_spire"},
        ],
        "routes": [
            {"id": "cloudstep_basin_gateway", "from_region": "starter_ruins", "to_region": "cloudstep_basin", "requires_primed": true},
            {"id": "echo_watch_gateway", "from_region": "starter_ruins", "to_region": "echo_watch", "requires_primed": true},
            {"id": "return_to_starter_ruins_from_cloudstep_basin", "from_region": "cloudstep_basin", "to_region": "starter_ruins", "requires_primed": false},
            {"id": "return_to_starter_ruins_from_echo_watch", "from_region": "echo_watch", "to_region": "starter_ruins", "requires_primed": false},
        ],
        "regional_goals": [
            {"region_id": "cloudstep_basin", "objective_id": "cloudstep_relay", "reward_id": "basin_insight"},
            {"region_id": "echo_watch", "objective_id": "echo_spire", "reward_id": "watch_resonance"},
        ],
        "patrol_lanes": [
            {"region_id": "starter_ruins", "route_id": "starter_watch_loop", "assigned_enemy_ids": ["sentinel_melee", "sentinel_ranged"]},
            {"region_id": "cloudstep_basin", "route_id": "cloudstep_relay_arc", "assigned_enemy_ids": ["cloudstep_basin_sentinel_melee", "cloudstep_basin_sentinel_ranged"]},
            {"region_id": "echo_watch", "route_id": "echo_spire_sweep", "assigned_enemy_ids": ["echo_watch_sentinel_ranged", "echo_watch_sentinel_elite"]},
        ],
        "guard_networks": [
            {"region_id": "starter_ruins", "network_id": "starter_intro_alert", "assigned_enemy_ids": ["sentinel_melee", "sentinel_ranged"], "search_duration_seconds": 3.0, "anchor_point": [0.0, 1.0, -6.0]},
            {"region_id": "cloudstep_basin", "network_id": "cloudstep_relay_alert", "assigned_enemy_ids": ["cloudstep_basin_sentinel_melee", "cloudstep_basin_sentinel_ranged"], "search_duration_seconds": 3.4, "anchor_point": [80.5, 1.0, -10.5]},
            {"region_id": "echo_watch", "network_id": "echo_spire_alert", "assigned_enemy_ids": ["echo_watch_sentinel_ranged", "echo_watch_sentinel_elite"], "search_duration_seconds": 3.8, "anchor_point": [-74.5, 1.0, -8.0]},
        ],
    }


func _default_npc_roster() -> Dictionary:
    return {
        "npcs": [
            {"id": "keeper_aeris", "role": "guide", "home_region": "starter_ruins"},
            {"id": "marshal_toren", "role": "combat_trainer", "home_region": "cloudstep_basin"},
            {"id": "scribe_ves", "role": "historian", "home_region": "echo_watch"},
        ],
    }


func _default_quest_arcs() -> Dictionary:
    return {
        "quest_arcs": [
            {"id": "purification_path", "title": "Purification Path", "beat_count": 4},
            {"id": "watchtower_resonance", "title": "Watchtower Resonance", "beat_count": 5},
        ],
    }


func _default_party_roster() -> Dictionary:
    return {
        "party_model": "single_hero_focus",
        "swap_style": "single_hero_mastery",
        "starter_party_size": 1,
        "active_party_slot_ids": ["slot_01"],
        "party_slots": [
            {
                "slot_id": "slot_01",
                "hero_id": "player_avatar",
                "display_name": "Player Avatar",
                "combat_role": "vanguard",
                "combat_affinity": "steel",
                "release_window": "launch",
                "signature_job": "hold the default mastery lane",
            },
        ],
    }


func _default_elemental_matrix() -> Dictionary:
    return {
        "system_enabled": false,
        "affinity_order": ["steel", "arc", "guard", "rush"],
        "starter_affinities": ["steel"],
        "reaction_rules": [
            {"input": ["steel", "guard"], "result": "break_guard", "combat_use": "open a short punish window on armored targets"},
            {"input": ["rush", "arc"], "result": "tempo_surge", "combat_use": "reward aggressive routing with faster cooldown cycling"},
        ],
    }


func _default_world_streaming() -> Dictionary:
    return {
        "strategy": "single_slice_lane",
        "launch_region_target": 1,
        "active_region_id": "starter_ruins",
        "loaded_region_ids": ["starter_ruins"],
        "stream_cells": [
            {
                "cell_id": "starter_ruins_cell",
                "region_id": "starter_ruins",
                "load_priority": "critical",
                "stream_budget_class": "slice_core",
                "entry_gateway_ids": [],
            },
        ],
    }


func _default_commission_board() -> Dictionary:
    return {
        "service_model": "boxed_release_plus_expansions",
        "content_cadence": "major_expansion_packs",
        "active_commission_ids": ["starter_route_clear"],
        "commission_slots": [
            {
                "id": "starter_route_clear",
                "region_id": "starter_ruins",
                "title": "Clear the Starter Route",
                "goal": "Re-run the shrine route and stabilize the onboarding lane.",
                "reward_type": "upgrade_materials",
            },
        ],
    }


func _default_manifest() -> Dictionary:
    return {
        "spawn_point": [0.0, 1.1, 8.0],
        "shrine_position": [0.0, 0.0, -12.0],
        "landmarks": [
            {"id": "entry_arch", "region_id": "starter_ruins", "position": [-8.0, 1.0, -9.0], "size": [2.5, 2.0, 2.5], "color": [0.35, 0.36, 0.41]},
            {"id": "combat_pocket", "region_id": "starter_ruins", "position": [8.5, 1.25, -9.5], "size": [2.0, 2.5, 2.0], "color": [0.45, 0.34, 0.28]},
            {"id": "purification_shrine", "region_id": "starter_ruins", "position": [0.0, 0.75, -18.0], "size": [6.0, 1.5, 2.5], "color": [0.30, 0.32, 0.37]},
        ],
        "enemies": [
            {"id": "sentinel_melee", "name": "Sentinel Alpha", "pattern_profile_id": "sentinel_duelist", "region_id": "starter_ruins", "position": [-3.0, 1.0, -3.0], "color": [0.96, 0.35, 0.35], "max_health": 3, "contact_damage": 7, "move_speed": 3.8, "combat_role": "melee", "squad_role": "vanguard", "critical_path": true},
            {"id": "sentinel_ranged", "name": "Sentinel Beta", "pattern_profile_id": "sentinel_volley", "region_id": "starter_ruins", "position": [3.5, 1.0, -6.0], "color": [0.35, 0.80, 1.0], "max_health": 4, "contact_damage": 8, "move_speed": 3.2, "combat_role": "ranged", "squad_role": "suppressor", "critical_path": true},
            {"id": "sentinel_elite", "name": "Sentinel Vanguard", "pattern_profile_id": "elite_vanguard", "region_id": "starter_ruins", "position": [10.5, 1.0, -8.5], "color": [0.88, 0.40, 0.88], "max_health": 7, "contact_damage": 10, "move_speed": 4.1, "combat_role": "elite", "combat_tier": "elite", "squad_role": "anchor", "critical_path": false, "phase_thresholds": [0.5]},
            {"id": "shrine_warden", "name": "Shrine Warden", "pattern_profile_id": "shrine_guardian", "region_id": "starter_ruins", "position": [0.0, 1.0, -13.5], "color": [0.92, 0.62, 0.24], "max_health": 10, "contact_damage": 12, "move_speed": 3.1, "combat_role": "boss", "combat_tier": "boss", "squad_role": "boss_anchor", "critical_path": true, "phase_thresholds": [0.66, 0.33], "burst_projectile_count": 8, "burst_projectile_speed": 8.5, "burst_projectile_damage": 5, "burst_cooldown": 4.4},
            {"id": "cloudstep_basin_sentinel_melee", "archetype_id": "sentinel_melee", "name": "Cloudstep Reaver", "pattern_profile_id": "sentinel_duelist", "region_id": "cloudstep_basin", "position": [76.5, 1.0, -9.0], "color": [0.62, 0.88, 0.70], "max_health": 4, "contact_damage": 8, "move_speed": 4.0, "combat_role": "melee", "squad_role": "vanguard", "critical_path": true},
            {"id": "cloudstep_basin_sentinel_ranged", "archetype_id": "sentinel_ranged", "name": "Cloudstep Spotter", "pattern_profile_id": "sentinel_volley", "region_id": "cloudstep_basin", "position": [82.5, 1.0, -9.5], "color": [0.42, 0.90, 0.92], "max_health": 4, "contact_damage": 7, "move_speed": 3.4, "combat_role": "ranged", "squad_role": "suppressor", "critical_path": true, "desired_range": 8.0, "projectile_speed": 13.8, "projectile_damage": 6, "projectile_cooldown": 1.9, "projectile_lifetime": 3.2},
            {"id": "echo_watch_sentinel_ranged", "archetype_id": "sentinel_ranged", "name": "Echo Watch Sniper", "pattern_profile_id": "sentinel_volley", "region_id": "echo_watch", "position": [-69.0, 1.0, -8.5], "color": [0.70, 0.76, 1.0], "max_health": 5, "contact_damage": 8, "move_speed": 3.5, "combat_role": "ranged", "squad_role": "suppressor", "critical_path": true, "desired_range": 8.4, "projectile_speed": 14.4, "projectile_damage": 7, "projectile_cooldown": 1.8, "projectile_lifetime": 3.3},
            {"id": "echo_watch_sentinel_elite", "archetype_id": "sentinel_elite", "name": "Echo Watch Vanguard", "pattern_profile_id": "elite_vanguard", "region_id": "echo_watch", "position": [-77.0, 1.0, -8.0], "color": [0.92, 0.58, 1.0], "max_health": 8, "contact_damage": 11, "move_speed": 4.2, "combat_role": "elite", "combat_tier": "elite", "squad_role": "anchor", "critical_path": true, "phase_thresholds": [0.55]},
        ],
        "npc_beacons": [
            {"id": "keeper_aeris", "name": "Keeper Aeris", "role": "guide", "function": "Anchors the first shrine route and future region handoff.", "home_region": "starter_ruins", "region_id": "starter_ruins", "position": [-10.0, 0.0, 6.0], "color": [0.98, 0.92, 0.54]},
            {"id": "marshal_toren", "name": "Marshal Toren", "role": "combat_trainer", "function": "Unlocks stronger encounter and rematch pressure.", "home_region": "cloudstep_basin", "region_id": "cloudstep_basin", "position": [72.0, 0.0, 10.0], "color": [0.60, 0.98, 0.74]},
            {"id": "scribe_ves", "name": "Scribe Ves", "role": "historian", "function": "Feeds quest-arc context for the next region.", "home_region": "echo_watch", "region_id": "echo_watch", "position": [-72.0, 0.0, 6.0], "color": [0.92, 0.78, 1.0]},
        ],
        "region_gateways": [
            {"id": "cloudstep_basin_gateway", "region_id": "starter_ruins", "target_region": "cloudstep_basin", "target_spawn": [72.0, 1.1, 8.0], "biome": "tiered canyon wetlands", "summary": "Teach vertical routing and ranged pressure.", "position": [-12.0, 0.0, -17.0], "color": [0.55, 0.88, 1.0], "requires_primed": true},
            {"id": "echo_watch_gateway", "region_id": "starter_ruins", "target_region": "echo_watch", "target_spawn": [-72.0, 1.1, 8.0], "biome": "highland observatory frontier", "summary": "Seed elite encounters and story escalation.", "position": [12.0, 0.0, -17.0], "color": [0.98, 0.66, 0.32], "requires_primed": true},
            {"id": "return_to_starter_ruins_from_cloudstep_basin", "region_id": "cloudstep_basin", "target_region": "starter_ruins", "target_spawn": [0.0, 1.1, 8.0], "biome": "return route", "summary": "Return to the shrine district and continue the main arc.", "position": [60.0, 0.0, -17.0], "color": [0.74, 0.92, 0.96], "requires_primed": false},
            {"id": "return_to_starter_ruins_from_echo_watch", "region_id": "echo_watch", "target_region": "starter_ruins", "target_spawn": [0.0, 1.1, 8.0], "biome": "return route", "summary": "Return to the shrine district and continue the main arc.", "position": [-60.0, 0.0, -17.0], "color": [0.92, 0.82, 1.0], "requires_primed": false},
        ],
        "reward_sites": [
            {"id": "overlook_cache", "label": "Overlook Cache", "reward_id": "route_sigil", "summary": "Optional detour reward that boosts guard timing and stamina recovery.", "encounter_id": "overlook_elite_detour", "region_id": "starter_ruins", "position": [13.0, 0.0, -12.5], "color": [0.96, 0.80, 0.38]},
        ],
        "active_arc": {"id": "purification_path", "title": "Purification Path", "beat_count": 4},
        "active_region_id": "starter_ruins",
        "region_layouts": _default_region_layouts().get("regions", []),
        "region_objectives": _default_region_objectives().get("objectives", []),
        "patrol_routes": _default_patrol_routes().get("routes", []),
        "alert_networks": _default_alert_networks().get("networks", []),
        "world_graph": _default_world_graph(),
        "party_roster": _default_party_roster(),
        "elemental_matrix": _default_elemental_matrix(),
        "world_streaming": _default_world_streaming(),
        "commission_board": _default_commission_board(),
        "encounters": [
            {"id": "ruin_intro_skirmish", "region_id": "starter_ruins", "label": "Intro Skirmish", "enemy_ids": ["sentinel_melee", "sentinel_ranged"], "start_position": [0.0, 1.0, -1.5], "activation_radius": 8.5, "hint": "Lock on, break the ranged line, and stabilize the route."},
            {"id": "overlook_elite_detour", "region_id": "starter_ruins", "label": "Overlook Elite Detour", "enemy_ids": ["sentinel_elite"], "start_position": [9.5, 1.0, -7.5], "activation_radius": 6.8, "hint": "Break the elite and claim the optional cache.", "reward_site_id": "overlook_cache"},
            {"id": "shrine_guardian_finale", "region_id": "starter_ruins", "label": "Shrine Guardian Finale", "enemy_ids": ["shrine_warden"], "start_position": [0.0, 1.0, -11.0], "activation_radius": 7.5, "hint": "Read the guardian pattern, then counter through the stagger window.", "boss_enemy_id": "shrine_warden"},
            {"id": "cloudstep_relay_push", "region_id": "cloudstep_basin", "label": "Cloudstep Relay Push", "enemy_ids": ["cloudstep_basin_sentinel_melee", "cloudstep_basin_sentinel_ranged"], "start_position": [79.5, 1.0, -10.5], "activation_radius": 7.2, "hint": "Break the basin defenders and stabilize the relay."},
            {"id": "echo_spire_hold", "region_id": "echo_watch", "label": "Echo Spire Hold", "enemy_ids": ["echo_watch_sentinel_ranged", "echo_watch_sentinel_elite"], "start_position": [-73.5, 1.0, -9.0], "activation_radius": 7.0, "hint": "Clear the observatory defenders before calibrating the spire."},
        ],
    }
"""


SAVE_SERVICE_GD = """extends Node

const SAVE_PATH := "user://reverie_slice_save.json"


func _ready() -> void:
    if not GameState.slice_completed.is_connected(_on_slice_completed):
        GameState.slice_completed.connect(_on_slice_completed)


func has_save() -> bool:
    return FileAccess.file_exists(SAVE_PATH)


func save_progress(reason: String = "manual") -> bool:
    var payload := GameState.capture_save_state(reason)
    var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
    if file == null:
        GameState.set_hint("Save failed. The runtime could not open the save path.")
        return false
    file.store_string(JSON.stringify(payload, "\\t"))
    GameState.set_hint("Saved slice progress (%s). Press F9 to restore it later." % [reason])
    return true


func load_progress() -> bool:
    if not has_save():
        GameState.set_hint("No slice save found yet. Press F5 after making progress.")
        return false
    var file := FileAccess.open(SAVE_PATH, FileAccess.READ)
    if file == null:
        GameState.set_hint("Load failed. The save file could not be opened.")
        return false
    var parsed := JSON.parse_string(file.get_as_text())
    if typeof(parsed) != TYPE_DICTIONARY:
        GameState.set_hint("Load failed. The save payload is invalid.")
        return false
    GameState.apply_save_state(parsed)
    return true


func delete_save() -> void:
    if has_save():
        DirAccess.remove_absolute(ProjectSettings.globalize_path(SAVE_PATH))


func _on_slice_completed() -> void:
    save_progress("completion")
"""


README_MD = """# Godot 3D Vertical Slice Scaffold

This runtime foundation is generated by Reverie-Gamer for ambitious 3D requests.

What it includes:

- a Godot project under `engine/godot/`
- a third-person player controller with dash, guard, jump, lock-on, skill attack, interaction, save, and load support
- enemy chase and wind-up pressure with a small combat state machine
- melee and ranged enemy pressure patterns, including projectile attacks
- encounter director flow and boss phase pattern profiles backed by generated combat data
- optional detour reward caches that unlock after elite encounters
- region travel scaffolding with generated layouts, world routes, and gateway-driven switching
- regional objective sites that turn expansion areas into playable goals with persistent rewards
- frontier-region defender encounters that gate relay/spire objectives instead of leaving expansion zones empty
- patrol-route contracts that let enemies sweep regional lanes instead of waiting at one static spawn point
- alert-network contracts that let nearby defenders converge, search, and split squad response roles when one guard makes contact
- data-driven slice manifests under `engine/godot/data/`
- region, NPC, and quest-arc expansion seeds for continued multi-region growth
- large-scale runtime contracts for party roster, elemental reactions, world streaming, and commission cadence
- interactable NPC anchors and region gateways that preview the next expansion lanes in-runtime
- autoloaded `GameState` and `SaveService` singletons for quest flow, progression, and persistence

Runtime controls:

- `WASD` move
- mouse look
- `LMB` attack
- `RMB` or `R` skill attack
- `F` heavy strike
- `C` guard and perfect guard
- `Tab` lock-on toggle
- `Shift` sprint
- `Q` dash
- `E` interact
- `F5` save
- `F9` load

Recommended next steps:

1. Replace primitive visuals with authored assets and animation state machines.
2. Move combat hitboxes and VFX into authored scenes that consume the generated data contracts.
3. Expand the slice manifest into multiple combat pockets and side-route rewards.
4. If the Godot runtime plugin is installed, use the `rc_godot_*` tools for headless checks and project scans.
"""


class GodotRuntimeAdapter(BaseRuntimeAdapter):
    runtime_id = "godot"
    display_name = "Godot"
    external = True
    maturity = "3d-foundation"
    capability_tags = (
        "external-runtime",
        "3d",
        "scene-import",
        "gltf",
        "third-person-template",
    )
    template_support = ("third_person_action", "action_rpg_slice")

    def _detect_plugin_runtime(self, root: Path) -> tuple[bool, str]:
        plugin_root = root / ".reverie" / "plugins" / "godot"
        if not plugin_root.exists():
            return False, str(plugin_root)
        patterns = (
            "reverie-godot*.exe",
            "godot.exe",
            "godot*.exe",
            "Godot*.exe",
            "bin/Godot*.exe",
        )
        for pattern in patterns:
            if list(plugin_root.glob(pattern)):
                return True, str(plugin_root)
        return False, str(plugin_root)

    def detect(self, project_root: Path, app_root: Path | None = None) -> RuntimeProfile:
        root = Path(app_root or project_root).resolve()
        runtime_ready, plugin_install = self._detect_plugin_runtime(root)
        return RuntimeProfile(
            id=self.runtime_id,
            display_name=self.display_name,
            available=True,
            can_scaffold=True,
            can_validate=runtime_ready,
            external=self.external,
            maturity=self.maturity,
            source="runtime-plugin" if runtime_ready else "scaffold-template",
            version="",
            capabilities=list(self.capability_tags),
            template_support=list(self.template_support),
            health="ready" if runtime_ready else "scaffold-only",
            notes=[
                "Preferred external runtime for extensible third-person 3D slices.",
                "Validation upgrades automatically when the Godot runtime plugin is installed.",
            ],
            paths={
                "plugin_install": plugin_install,
                "project_root": str(Path(project_root).resolve()),
            },
        )

    def recommend_template(self, game_request: Dict[str, Any]) -> str:
        return "action_rpg_slice"

    def create_project(
        self,
        output_dir: Path,
        *,
        project_name: str,
        game_request: Dict[str, Any],
        blueprint: Dict[str, Any],
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        runtime_root = Path(output_dir) / "engine" / "godot"
        files: list[str] = []
        payloads = {
            runtime_root / "project.godot": _project_godot(project_name),
            runtime_root / "scenes/main.tscn": MAIN_TSCN,
            runtime_root / "scripts/main.gd": MAIN_GD,
            runtime_root / "scripts/player_controller.gd": PLAYER_CONTROLLER_GD,
            runtime_root / "scripts/enemy_dummy.gd": ENEMY_DUMMY_GD,
            runtime_root / "scripts/enemy_projectile.gd": ENEMY_PROJECTILE_GD,
            runtime_root / "scripts/combat_feedback.gd": COMBAT_FEEDBACK_GD,
            runtime_root / "scripts/quest_trigger.gd": QUEST_TRIGGER_GD,
            runtime_root / "scripts/npc_anchor.gd": NPC_ANCHOR_GD,
            runtime_root / "scripts/region_gateway.gd": REGION_GATEWAY_GD,
            runtime_root / "scripts/reward_cache.gd": REWARD_CACHE_GD,
            runtime_root / "scripts/region_objective_site.gd": REGION_OBJECTIVE_SITE_GD,
            runtime_root / "scripts/encounter_director.gd": ENCOUNTER_DIRECTOR_GD,
            runtime_root / "scripts/region_manager.gd": REGION_MANAGER_GD,
            runtime_root / "scripts/hud.gd": HUD_GD,
            runtime_root / "autoload/game_state.gd": GAME_STATE_GD,
            runtime_root / "autoload/save_service.gd": SAVE_SERVICE_GD,
            runtime_root / "README.md": README_MD,
            runtime_root / "assets/README.md": "# Assets\\n\\nReplace primitive slice visuals with authored Godot-ready assets here.\\n",
            runtime_root / "data/README.md": "# Data\\n\\nGenerated runtime contracts, system specs, slice manifests, and tuning payloads land here.\\n",
        }
        for path, content in payloads.items():
            if _safe_write(path, content, overwrite):
                files.append(str(path))
        return {
            "runtime": self.runtime_id,
            "runtime_root": str(runtime_root),
            "template": self.recommend_template(game_request),
            "directories": [str(runtime_root / relative) for relative in ("autoload", "assets", "data", "scenes", "scripts")],
            "files": files,
            "notes": ["Generated a runnable Godot third-person action-RPG slice scaffold with data-driven state and save/load support."],
        }

    def validate_project(self, output_dir: Path) -> Dict[str, Any]:
        runtime_root = Path(output_dir) / "engine" / "godot"
        checks = [
            {"name": "project_file", "ok": (runtime_root / "project.godot").exists()},
            {"name": "main_scene", "ok": (runtime_root / "scenes" / "main.tscn").exists()},
            {"name": "autoload_state", "ok": (runtime_root / "autoload" / "game_state.gd").exists()},
            {"name": "save_service", "ok": (runtime_root / "autoload" / "save_service.gd").exists()},
            {"name": "player_controller", "ok": (runtime_root / "scripts" / "player_controller.gd").exists()},
            {"name": "enemy_ai", "ok": (runtime_root / "scripts" / "enemy_dummy.gd").exists()},
            {"name": "enemy_projectile", "ok": (runtime_root / "scripts" / "enemy_projectile.gd").exists()},
            {"name": "combat_feedback", "ok": (runtime_root / "scripts" / "combat_feedback.gd").exists()},
            {"name": "npc_anchor", "ok": (runtime_root / "scripts" / "npc_anchor.gd").exists()},
            {"name": "region_gateway", "ok": (runtime_root / "scripts" / "region_gateway.gd").exists()},
            {"name": "reward_cache", "ok": (runtime_root / "scripts" / "reward_cache.gd").exists()},
            {"name": "region_objective_site", "ok": (runtime_root / "scripts" / "region_objective_site.gd").exists()},
            {"name": "encounter_director", "ok": (runtime_root / "scripts" / "encounter_director.gd").exists()},
            {"name": "region_manager", "ok": (runtime_root / "scripts" / "region_manager.gd").exists()},
            {"name": "slice_manifest", "ok": (runtime_root / "data" / "slice_manifest.json").exists()},
            {"name": "quest_flow", "ok": (runtime_root / "data" / "quest_flow.json").exists()},
            {"name": "progression", "ok": (runtime_root / "data" / "progression.json").exists()},
            {"name": "asset_registry", "ok": (runtime_root / "data" / "asset_registry.json").exists()},
            {"name": "asset_import_profile", "ok": (runtime_root / "data" / "asset_import_profile.json").exists()},
            {"name": "region_seeds", "ok": (runtime_root / "data" / "region_seeds.json").exists()},
            {"name": "region_layouts", "ok": (runtime_root / "data" / "region_layouts.json").exists()},
            {"name": "region_objectives", "ok": (runtime_root / "data" / "region_objectives.json").exists()},
            {"name": "patrol_routes", "ok": (runtime_root / "data" / "patrol_routes.json").exists()},
            {"name": "alert_networks", "ok": (runtime_root / "data" / "alert_networks.json").exists()},
            {"name": "world_graph", "ok": (runtime_root / "data" / "world_graph.json").exists()},
            {"name": "npc_roster", "ok": (runtime_root / "data" / "npc_roster.json").exists()},
            {"name": "quest_arcs", "ok": (runtime_root / "data" / "quest_arcs.json").exists()},
            {"name": "party_roster", "ok": (runtime_root / "data" / "party_roster.json").exists()},
            {"name": "elemental_matrix", "ok": (runtime_root / "data" / "elemental_matrix.json").exists()},
            {"name": "world_streaming", "ok": (runtime_root / "data" / "world_streaming.json").exists()},
            {"name": "commission_board", "ok": (runtime_root / "data" / "commission_board.json").exists()},
        ]
        return {
            "valid": all(item["ok"] for item in checks),
            "checks": checks,
            "project_root": str(runtime_root),
            "notes": ["Headless Godot validation can run through the runtime plugin when available."],
        }
