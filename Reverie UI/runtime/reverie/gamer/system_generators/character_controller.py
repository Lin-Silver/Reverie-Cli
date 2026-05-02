"""Character controller packet generator."""

from __future__ import annotations

from typing import Any, Dict

from .shared import experience, packet_header, quality_targets, reference_titles, required_systems, source_systems


def build_character_controller_packet(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    current_experience = experience(game_request)
    targets = quality_targets(game_request)
    requested = required_systems(game_request)
    references = reference_titles(game_request)
    traversal_enabled = "traversal_ability" in requested
    packet = packet_header(
        "character_controller",
        "Character Controller",
        game_request,
        blueprint,
        runtime_profile,
        source_systems(game_request, ("camera", "movement", "lock_on", "traversal_ability")),
    )
    packet.update(
        {
            "slice_goal": "Own the third-person locomotion, orbit camera, target readability, and approach-to-objective flow.",
            "player_fantasy": (
                "Move like a hero action RPG protagonist with immediate response, readable acceleration, and clean camera control."
            ),
            "dependencies": [],
            "requirements": [
                f"Deliver {current_experience.get('movement_model', 'third_person_action')} traversal with consistent grounded and airborne handling.",
                "Support orbit camera plus soft aim focus so encounters remain readable while moving.",
                "Expose one evasive movement option for combat spacing and recovery.",
                "Reach the slice objective without off-game explanation or designer-only shortcuts.",
            ],
            "state_model": [
                "spawned",
                "grounded",
                "airborne",
                "sprint_or_dash",
                "combat_focus",
                "interaction_focus",
            ],
            "input_map": {
                "move": ["keyboard_wasd", "left_stick"],
                "look": ["mouse", "right_stick"],
                "jump": ["space", "south_face_button"],
                "dash": ["shift", "right_shoulder"],
                "interact": ["e", "west_face_button"],
                "attack": ["mouse_left", "right_trigger"],
            },
            "tuning": {
                "walk_speed_mps": 5.8,
                "sprint_multiplier": 1.35,
                "jump_velocity": 6.2,
                "dash_speed_mps": 14.0,
                "camera_distance_m": 5.2,
                "target_fps": targets.get("target_fps", 60),
            },
            "telemetry": [
                "movement_started",
                "dash_used",
                "lock_target_changed",
                "fall_reset",
                "objective_approach_started",
            ],
            "tests": [
                "player can move from slice entry to first landmark using the real controller",
                "camera keeps enemy and objective readable during lateral movement",
                "dash or sprint can reposition without soft-locking the player state",
                "interaction focus can reach the shrine objective inside one smoke run",
            ],
            "primary_outputs": [
                "runtime controller script",
                "camera tuning defaults",
                "input action map",
                "movement smoke path notes",
            ],
            "expansion_hooks": [
                "climb and glide extensions" if traversal_enabled else "contextual traversal extension",
                "animation graph and root motion support",
                "camera collision and lock-on priority tuning",
            ],
            "notes": [
                "References: " + ", ".join(references) if references else "References inferred from genre and camera model.",
                "Favor response and route clarity over full traversal breadth in the first slice.",
            ],
        }
    )
    return packet
