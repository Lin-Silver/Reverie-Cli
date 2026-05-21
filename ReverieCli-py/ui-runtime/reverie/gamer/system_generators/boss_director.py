"""Boss encounter director and phase system generator."""

from __future__ import annotations

from typing import Any, Dict, List


def generate_boss_system(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_id: str = "godot",
    boss_count: int = 1,
) -> Dict[str, Any]:
    """Generate boss encounter system with phases, patterns, and mechanics."""
    
    source_prompt = str(game_request.get("source_prompt", "")).lower()
    creative = game_request.get("creative_target", {})
    references = creative.get("references", [])
    
    # Detect boss features
    has_phases = any(word in source_prompt for word in ["phase", "阶段", "form", "transformation"])
    has_mechanics = any(word in source_prompt for word in ["mechanic", "gimmick", "机制", "pattern"])
    is_souls_like = any(word in source_prompt for word in ["souls", "elden", "dark souls", "魂"])
    is_action_rpg = "action" in source_prompt or "arpg" in source_prompt
    
    # Generate boss profiles
    bosses = []
    for i in range(boss_count):
        boss = _generate_boss_profile(
            boss_index=i,
            has_phases=has_phases or is_souls_like,
            has_mechanics=has_mechanics,
            is_souls_like=is_souls_like,
            is_action_rpg=is_action_rpg,
        )
        bosses.append(boss)
    
    return {
        "system_id": "boss_encounters",
        "display_name": "Boss Encounter System",
        "bosses": bosses,
        "director_config": {
            "music_transition": True,
            "arena_boundaries": True,
            "checkpoint_before_boss": True,
            "retry_on_death": True,
            "victory_rewards": True,
        },
        "implementation": {
            "godot": _godot_boss_implementation(bosses),
            "o3de": _o3de_boss_implementation(bosses),
            "reverie_engine": _reverie_boss_implementation(bosses),
        },
        "telemetry_events": [
            "boss_encounter_started",
            "boss_phase_changed",
            "boss_mechanic_triggered",
            "boss_defeated",
            "player_death_in_boss",
        ],
    }


def _generate_boss_profile(
    boss_index: int,
    has_phases: bool,
    has_mechanics: bool,
    is_souls_like: bool,
    is_action_rpg: bool,
) -> Dict[str, Any]:
    """Generate a single boss profile."""
    
    boss_names = [
        "Corrupted Guardian",
        "Ancient Sentinel",
        "Void Warden",
        "Crystal Tyrant",
        "Storm Sovereign",
    ]
    
    boss_name = boss_names[boss_index % len(boss_names)]
    
    # Base stats
    base_health = 5000 if is_souls_like else 3000
    base_damage = 150 if is_souls_like else 100
    
    phases = []
    if has_phases:
        phases = [
            {
                "phase": 1,
                "health_threshold": 1.0,
                "behavior": "aggressive_melee",
                "attack_speed": 1.0,
                "move_speed": 4.0,
                "patterns": ["combo_rush", "ground_slam", "charge_attack"],
            },
            {
                "phase": 2,
                "health_threshold": 0.7,
                "behavior": "mixed_range",
                "attack_speed": 1.2,
                "move_speed": 4.5,
                "patterns": ["combo_rush", "projectile_barrage", "area_denial"],
                "phase_transition": {
                    "animation": "roar",
                    "invulnerable": True,
                    "duration": 3.0,
                    "summon_adds": 2,
                },
            },
            {
                "phase": 3,
                "health_threshold": 0.3,
                "behavior": "desperate_fury",
                "attack_speed": 1.5,
                "move_speed": 5.0,
                "patterns": ["ultimate_combo", "rage_mode", "environmental_hazard"],
                "phase_transition": {
                    "animation": "power_up",
                    "invulnerable": True,
                    "duration": 4.0,
                    "arena_change": True,
                },
            },
        ]
    else:
        phases = [
            {
                "phase": 1,
                "health_threshold": 1.0,
                "behavior": "balanced",
                "attack_speed": 1.0,
                "move_speed": 4.0,
                "patterns": ["basic_combo", "special_attack", "defensive_stance"],
            }
        ]
    
    # Attack patterns
    attack_patterns = _generate_attack_patterns(is_souls_like, is_action_rpg)
    
    # Mechanics
    mechanics = []
    if has_mechanics:
        mechanics = [
            {
                "id": "weak_point",
                "name": "Weak Point System",
                "description": "Boss has vulnerable spots that take extra damage",
                "weak_points": [
                    {"location": "head", "damage_multiplier": 2.0},
                    {"location": "core", "damage_multiplier": 3.0, "exposed_at_phase": 2},
                ],
            },
            {
                "id": "counter_window",
                "name": "Counter Attack Window",
                "description": "Perfect timing allows powerful counter attacks",
                "window_duration": 0.5,
                "counter_damage_multiplier": 2.5,
            },
            {
                "id": "environmental",
                "name": "Environmental Hazards",
                "description": "Use arena hazards against the boss",
                "hazards": ["falling_rocks", "lava_pools", "electric_pillars"],
            },
        ]
    
    return {
        "id": f"boss_{boss_index + 1}",
        "name": boss_name,
        "display_name": boss_name,
        "description": f"A powerful {boss_name} that guards the ancient ruins",
        "base_stats": {
            "max_health": base_health,
            "damage": base_damage,
            "defense": 50,
            "poise": 100,
            "move_speed": 4.0,
        },
        "phases": phases,
        "attack_patterns": attack_patterns,
        "mechanics": mechanics,
        "rewards": {
            "experience": 1000,
            "currency": 500,
            "items": ["boss_soul", "legendary_weapon_fragment"],
        },
        "arena": {
            "size": [40.0, 40.0],
            "boundary_type": "invisible_wall",
            "music": "boss_battle_theme",
            "lighting": "dramatic",
        },
    }


def _generate_attack_patterns(is_souls_like: bool, is_action_rpg: bool) -> List[Dict[str, Any]]:
    """Generate boss attack patterns."""
    
    patterns = [
        {
            "id": "combo_rush",
            "name": "Combo Rush",
            "type": "melee_combo",
            "hits": 3,
            "damage_per_hit": 80,
            "telegraph_time": 0.8,
            "recovery_time": 1.5,
            "tracking": True,
        },
        {
            "id": "ground_slam",
            "name": "Ground Slam",
            "type": "aoe",
            "damage": 150,
            "radius": 8.0,
            "telegraph_time": 1.2,
            "recovery_time": 2.0,
            "shockwave": True,
        },
        {
            "id": "charge_attack",
            "name": "Charge Attack",
            "type": "charge",
            "damage": 120,
            "speed": 12.0,
            "telegraph_time": 1.0,
            "recovery_time": 2.5,
            "wall_stun": True,
        },
    ]
    
    if is_action_rpg:
        patterns.extend([
            {
                "id": "projectile_barrage",
                "name": "Projectile Barrage",
                "type": "ranged",
                "projectile_count": 5,
                "damage_per_projectile": 60,
                "spread_angle": 45.0,
                "telegraph_time": 0.6,
                "recovery_time": 1.8,
            },
            {
                "id": "area_denial",
                "name": "Area Denial",
                "type": "zone",
                "damage_per_second": 50,
                "duration": 8.0,
                "radius": 6.0,
                "telegraph_time": 1.0,
            },
        ])
    
    if is_souls_like:
        patterns.extend([
            {
                "id": "grab_attack",
                "name": "Grab Attack",
                "type": "grab",
                "damage": 200,
                "range": 3.0,
                "telegraph_time": 1.5,
                "recovery_time": 3.0,
                "unblockable": True,
            },
            {
                "id": "delayed_strike",
                "name": "Delayed Strike",
                "type": "melee",
                "damage": 180,
                "telegraph_time": 2.0,
                "delay_variation": 0.5,
                "recovery_time": 2.0,
            },
        ])
    
    return patterns


def _godot_boss_implementation(bosses: List[Dict[str, Any]]) -> Dict[str, Any]:
    script = """# Boss Encounter System for Godot
extends CharacterBody3D

signal phase_changed(new_phase: int)
signal boss_defeated()

@export var boss_id: String = "boss_1"
@export var max_health: float = 5000.0
@export var current_phase: int = 1

var current_health: float
var phase_thresholds: Array = [1.0, 0.7, 0.3]
var is_transitioning: bool = false
var attack_cooldown: float = 0.0
var current_pattern: Dictionary = {}

@onready var player: Node3D = get_tree().get_first_node_in_group("player")


func _ready() -> void:
    current_health = max_health
    add_to_group("boss")
    add_to_group("lockable")
    _start_encounter()


func _process(delta: float) -> void:
    if is_transitioning:
        return
    
    attack_cooldown = max(0.0, attack_cooldown - delta)
    
    if attack_cooldown <= 0.0:
        _execute_attack_pattern()


func _physics_process(delta: float) -> void:
    if is_transitioning or not player:
        return
    
    # Move toward player
    var direction = (player.global_position - global_position).normalized()
    var move_speed = _get_phase_move_speed()
    velocity = direction * move_speed
    move_and_slide()


func apply_damage(amount: int, source: String, hit_reaction: float, poise_damage: float, attack_id: String) -> void:
    if is_transitioning:
        return
    
    current_health -= amount
    
    # Check for phase transition
    var health_percent = current_health / max_health
    for i in range(phase_thresholds.size()):
        if health_percent <= phase_thresholds[i] and current_phase == i:
            _transition_to_phase(i + 1)
            return
    
    if current_health <= 0:
        _on_defeated()


func _transition_to_phase(new_phase: int) -> void:
    is_transitioning = true
    current_phase = new_phase
    emit_signal("phase_changed", new_phase)
    
    # Play transition animation
    await get_tree().create_timer(3.0).timeout
    
    is_transitioning = false


func _execute_attack_pattern() -> void:
    var patterns = _get_phase_patterns()
    if patterns.is_empty():
        return
    
    var pattern = patterns[randi() % patterns.size()]
    current_pattern = pattern
    
    match pattern.get("type", "melee"):
        "melee_combo":
            _execute_melee_combo(pattern)
        "aoe":
            _execute_aoe_attack(pattern)
        "charge":
            _execute_charge_attack(pattern)
        "ranged":
            _execute_ranged_attack(pattern)
    
    attack_cooldown = pattern.get("recovery_time", 2.0)


func _execute_melee_combo(pattern: Dictionary) -> void:
    var hits = pattern.get("hits", 3)
    var damage = pattern.get("damage_per_hit", 80)
    
    for i in range(hits):
        await get_tree().create_timer(0.4).timeout
        _damage_player_in_range(damage, 3.0)


func _execute_aoe_attack(pattern: Dictionary) -> void:
    var radius = pattern.get("radius", 8.0)
    var damage = pattern.get("damage", 150)
    
    await get_tree().create_timer(pattern.get("telegraph_time", 1.2)).timeout
    _damage_player_in_range(damage, radius)


func _execute_charge_attack(pattern: Dictionary) -> void:
    if not player:
        return
    
    var direction = (player.global_position - global_position).normalized()
    var speed = pattern.get("speed", 12.0)
    
    await get_tree().create_timer(pattern.get("telegraph_time", 1.0)).timeout
    
    # Charge forward
    for i in range(20):
        velocity = direction * speed
        move_and_slide()
        _damage_player_in_range(pattern.get("damage", 120), 2.0)
        await get_tree().create_timer(0.05).timeout


func _execute_ranged_attack(pattern: Dictionary) -> void:
    var count = pattern.get("projectile_count", 5)
    var damage = pattern.get("damage_per_projectile", 60)
    
    await get_tree().create_timer(pattern.get("telegraph_time", 0.6)).timeout
    
    for i in range(count):
        _spawn_projectile(damage)
        await get_tree().create_timer(0.2).timeout


func _damage_player_in_range(damage: int, range: float) -> void:
    if not player:
        return
    
    if global_position.distance_to(player.global_position) <= range:
        if player.has_method("take_damage"):
            player.take_damage(damage)


func _spawn_projectile(damage: int) -> void:
    # Spawn projectile toward player
    pass


func _get_phase_move_speed() -> float:
    match current_phase:
        1: return 4.0
        2: return 4.5
        3: return 5.0
        _: return 4.0


func _get_phase_patterns() -> Array:
    # Return attack patterns for current phase
    return []


func _start_encounter() -> void:
    GameState.set_hint("Boss encounter started: " + boss_id)


func _on_defeated() -> void:
    emit_signal("boss_defeated")
    GameState.set_hint("Boss defeated!")
    queue_free()
"""
    
    return {
        "script_template": script,
        "required_nodes": ["BossController", "PhaseManager", "AttackPatternManager"],
        "groups": ["boss", "lockable", "combat_target"],
    }


def _o3de_boss_implementation(bosses: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "component_type": "BossEncounterSystem",
        "required_components": [
            "BossAIComponent",
            "PhaseManagerComponent",
            "AttackPatternComponent",
            "HealthComponent",
        ],
        "script_canvas": "boss_controller.scriptcanvas",
    }


def _reverie_boss_implementation(bosses: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "module": "reverie.boss.encounter",
        "config": "boss_config.json",
        "boss_count": len(bosses),
    }
