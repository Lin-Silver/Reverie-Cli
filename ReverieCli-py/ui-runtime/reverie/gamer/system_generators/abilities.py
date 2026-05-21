"""Player ability and skill system generator for action RPGs."""

from __future__ import annotations

from typing import Any, Dict, List


def generate_ability_system(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_id: str = "godot",
) -> Dict[str, Any]:
    """Generate player ability system with skills, elements, and combos."""
    
    source_prompt = str(game_request.get("source_prompt", "")).lower()
    creative = game_request.get("creative_target", {})
    references = creative.get("references", [])
    
    # Detect ability features from prompt and references
    has_elements = any(word in source_prompt for word in ["element", "elemental", "fire", "ice", "electric", "元素", "属性"])
    has_combo = any(word in source_prompt for word in ["combo", "连击", "skill chain"])
    has_ultimate = any(word in source_prompt for word in ["ultimate", "burst", "大招", "必杀"])
    has_character_swap = any(word in source_prompt for word in ["swap", "switch", "切换角色", "party"])
    
    # Genshin/Wuthering-style systems
    is_genshin_like = any(ref in ["Genshin Impact", "Wuthering Waves"] for ref in references)
    if is_genshin_like:
        has_elements = True
        has_ultimate = True
        has_character_swap = True
    
    abilities = []
    
    # Basic attack chain
    abilities.append({
        "id": "basic_attack",
        "name": "Basic Attack",
        "type": "combo_chain",
        "description": "Multi-hit combo attack sequence",
        "combo_chain": [
            {"hit": 1, "damage": 100, "stamina": 0, "speed": 1.0},
            {"hit": 2, "damage": 120, "stamina": 0, "speed": 1.1},
            {"hit": 3, "damage": 150, "stamina": 0, "speed": 1.2},
            {"hit": 4, "damage": 200, "stamina": 10, "speed": 0.9, "finisher": True},
        ],
        "combo_window": 1.5,
    })
    
    # Elemental skills
    if has_elements:
        elements = _generate_elemental_system(source_prompt)
        abilities.append({
            "id": "elemental_skill",
            "name": "Elemental Skill",
            "type": "active_skill",
            "description": "Elemental ability with cooldown",
            "elements": elements,
            "cooldown": 8.0,
            "energy_cost": 0,
            "stamina_cost": 25,
        })
        
        abilities.append({
            "id": "elemental_reactions",
            "name": "Elemental Reactions",
            "type": "passive_system",
            "description": "Combine elements for powerful reactions",
            "reactions": _generate_elemental_reactions(),
        })
    
    # Ultimate ability
    if has_ultimate:
        abilities.append({
            "id": "ultimate",
            "name": "Ultimate Ability",
            "type": "burst",
            "description": "Powerful ultimate ability requiring energy",
            "energy_cost": 80,
            "cooldown": 20.0,
            "duration": 5.0,
            "damage_multiplier": 5.0,
            "iframe_duration": 1.5,
        })
    
    # Character swap system
    if has_character_swap:
        abilities.append({
            "id": "character_swap",
            "name": "Character Swap",
            "type": "system",
            "description": "Switch between party members",
            "max_party_size": 4,
            "swap_cooldown": 1.0,
            "swap_iframe": 0.5,
        })
    
    # Dodge/Parry
    abilities.append({
        "id": "dodge",
        "name": "Dodge",
        "type": "defensive",
        "description": "Evasive maneuver with i-frames",
        "stamina_cost": 20,
        "cooldown": 0.8,
        "iframe_duration": 0.4,
        "perfect_dodge_window": 0.15,
    })
    
    return {
        "system_id": "abilities",
        "display_name": "Player Ability System",
        "abilities": abilities,
        "energy_system": {
            "max_energy": 100,
            "regen_rate": 0,  # Energy gained through combat
            "energy_per_hit": 5,
            "energy_per_skill": 15,
        },
        "implementation": {
            "godot": _godot_ability_implementation(abilities, has_elements),
            "o3de": _o3de_ability_implementation(abilities, has_elements),
            "reverie_engine": _reverie_ability_implementation(abilities, has_elements),
        },
        "telemetry_events": [
            "ability_used",
            "combo_completed",
            "elemental_reaction_triggered",
            "ultimate_activated",
            "perfect_dodge",
            "character_swapped",
        ],
    }


def _generate_elemental_system(prompt: str) -> List[Dict[str, Any]]:
    """Generate elemental system based on prompt."""
    elements = []
    
    element_keywords = {
        "pyro": ["fire", "flame", "burn", "火"],
        "hydro": ["water", "wet", "freeze", "水"],
        "electro": ["electric", "lightning", "shock", "雷"],
        "cryo": ["ice", "cold", "freeze", "冰"],
        "anemo": ["wind", "air", "swirl", "风"],
        "geo": ["earth", "rock", "shield", "岩"],
        "dendro": ["nature", "plant", "poison", "草"],
    }
    
    for element, keywords in element_keywords.items():
        if any(kw in prompt for kw in keywords):
            elements.append({
                "id": element,
                "name": element.capitalize(),
                "color": _get_element_color(element),
                "status_duration": 10.0,
            })
    
    # Default elements if none detected
    if not elements:
        elements = [
            {"id": "physical", "name": "Physical", "color": [0.9, 0.9, 0.9], "status_duration": 0},
            {"id": "energy", "name": "Energy", "color": [0.5, 0.8, 1.0], "status_duration": 8.0},
        ]
    
    return elements


def _generate_elemental_reactions() -> List[Dict[str, Any]]:
    """Generate elemental reaction combinations."""
    return [
        {
            "id": "vaporize",
            "elements": ["pyro", "hydro"],
            "damage_multiplier": 2.0,
            "description": "Pyro + Hydro = Vaporize (2x damage)",
        },
        {
            "id": "melt",
            "elements": ["pyro", "cryo"],
            "damage_multiplier": 2.0,
            "description": "Pyro + Cryo = Melt (2x damage)",
        },
        {
            "id": "overload",
            "elements": ["pyro", "electro"],
            "damage_multiplier": 1.5,
            "aoe_radius": 5.0,
            "description": "Pyro + Electro = Overload (AoE explosion)",
        },
        {
            "id": "superconduct",
            "elements": ["cryo", "electro"],
            "damage_multiplier": 1.2,
            "defense_reduction": 0.4,
            "description": "Cryo + Electro = Superconduct (Reduce defense)",
        },
        {
            "id": "freeze",
            "elements": ["hydro", "cryo"],
            "freeze_duration": 3.0,
            "description": "Hydro + Cryo = Freeze (Immobilize enemy)",
        },
        {
            "id": "electro_charged",
            "elements": ["hydro", "electro"],
            "damage_over_time": 50,
            "duration": 5.0,
            "description": "Hydro + Electro = Electro-Charged (DoT)",
        },
    ]


def _get_element_color(element: str) -> List[float]:
    """Get visual color for element."""
    colors = {
        "pyro": [1.0, 0.3, 0.1],
        "hydro": [0.2, 0.6, 1.0],
        "electro": [0.8, 0.3, 1.0],
        "cryo": [0.5, 0.9, 1.0],
        "anemo": [0.4, 1.0, 0.8],
        "geo": [1.0, 0.8, 0.2],
        "dendro": [0.3, 1.0, 0.3],
        "physical": [0.9, 0.9, 0.9],
        "energy": [0.5, 0.8, 1.0],
    }
    return colors.get(element, [1.0, 1.0, 1.0])


def _godot_ability_implementation(abilities: List[Dict[str, Any]], has_elements: bool) -> Dict[str, Any]:
    script = """# Player Ability System for Godot
extends Node

signal ability_used(ability_id: String)
signal combo_hit(hit_number: int)
signal elemental_reaction(reaction_id: String)

var current_energy: float = 0.0
var max_energy: float = 100.0
var combo_index: int = 0
var combo_timer: float = 0.0
var ability_cooldowns: Dictionary = {}

func _process(delta: float) -> void:
    combo_timer = max(0.0, combo_timer - delta)
    if combo_timer <= 0.0:
        combo_index = 0
    
    for ability_id in ability_cooldowns.keys():
        ability_cooldowns[ability_id] = max(0.0, ability_cooldowns[ability_id] - delta)


func use_basic_attack() -> bool:
    var combo_chain = GameState.get_combo_chain()
    if combo_chain.is_empty():
        return false
    
    var attack = combo_chain[min(combo_index, combo_chain.size() - 1)]
    var stamina_cost = attack.get("stamina", 0)
    
    if stamina_cost > 0 and not GameState.consume_stamina(stamina_cost):
        return false
    
    # Execute attack
    _execute_attack(attack)
    
    combo_timer = 1.5
    combo_index = (combo_index + 1) % combo_chain.size()
    emit_signal("combo_hit", combo_index)
    
    return true


func use_elemental_skill() -> bool:
    if ability_cooldowns.get("elemental_skill", 0.0) > 0.0:
        return false
    
    if not GameState.consume_stamina(25):
        return false
    
    ability_cooldowns["elemental_skill"] = 8.0
    current_energy = min(max_energy, current_energy + 15)
    
    emit_signal("ability_used", "elemental_skill")
    return true


func use_ultimate() -> bool:
    if current_energy < 80:
        return false
    
    if ability_cooldowns.get("ultimate", 0.0) > 0.0:
        return false
    
    current_energy -= 80
    ability_cooldowns["ultimate"] = 20.0
    
    emit_signal("ability_used", "ultimate")
    return true


func _execute_attack(attack: Dictionary) -> void:
    var damage = attack.get("damage", 100)
    var target = _find_attack_target()
    if target and target.has_method("apply_damage"):
        target.apply_damage(damage, "player", 0.2, 1.0, "basic_attack")
        current_energy = min(max_energy, current_energy + 5)
"""
    
    return {
        "script_template": script,
        "required_nodes": ["AbilityManager"],
        "input_actions": ["attack", "skill", "ultimate", "dodge"],
    }


def _o3de_ability_implementation(abilities: List[Dict[str, Any]], has_elements: bool) -> Dict[str, Any]:
    components = ["AbilitySystemComponent", "CombatComponent"]
    if has_elements:
        components.append("ElementalSystemComponent")
    
    return {
        "component_type": "PlayerAbilitySystem",
        "required_components": components,
        "script_canvas": "ability_controller.scriptcanvas",
    }


def _reverie_ability_implementation(abilities: List[Dict[str, Any]], has_elements: bool) -> Dict[str, Any]:
    return {
        "module": "reverie.abilities.player",
        "config": "ability_config.json",
        "has_elements": has_elements,
    }
