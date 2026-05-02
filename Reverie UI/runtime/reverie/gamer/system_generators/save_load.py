"""Save/load packet generator."""

from __future__ import annotations

from typing import Any, Dict

from .shared import packet_header, source_systems


def build_save_load_packet(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    packet = packet_header(
        "save_load",
        "Save and Load",
        game_request,
        blueprint,
        runtime_profile,
        source_systems(game_request, ("save_load", "telemetry")),
    )
    packet.update(
        {
            "slice_goal": "Persist the slice state safely enough that iteration and playtests can resume from meaningful progress.",
            "player_fantasy": "Leave the slice and return without losing hard-earned progress or confusing the current objective state.",
            "dependencies": ["quest", "progression"],
            "requirements": [
                "Persist objective progression, player vitals, defeated enemies, and unlocked rewards.",
                "Version the save payload so later content growth does not corrupt early slice saves.",
                "Define checkpoints that protect pacing without trivializing the encounter loop.",
            ],
            "save_schema": {
                "schema_version": 1,
                "fields": [
                    "player_transform",
                    "health",
                    "stamina",
                    "current_objective",
                    "defeated_enemy_ids",
                    "unlocked_rewards",
                    "world_flags",
                ],
            },
            "checkpoint_strategy": [
                "entry_spawn after initial onboarding",
                "post_encounter checkpoint once combat gate clears",
                "completion flag after shrine activation",
            ],
            "migration_rules": [
                "never delete unknown fields during forward migration",
                "default missing reward fields to empty arrays",
                "reconstruct defeated enemy flags from quest completion when possible",
            ],
            "telemetry": [
                "save_started",
                "save_completed",
                "load_started",
                "load_completed",
                "save_migration_applied",
            ],
            "tests": [
                "save and reload preserve current objective and reward state",
                "save created before encounter clear can still load after content tuning changes",
                "completion save does not duplicate rewards on reload",
                "invalid save payload fails safely with recovery path",
            ],
            "primary_outputs": [
                "versioned save schema",
                "checkpoint policy",
                "migration notes",
                "persistence smoke tests",
            ],
            "expansion_hooks": [
                "multi-slot support",
                "cross-device or cloud persistence",
                "chapter and region unlock snapshots",
            ],
        }
    )
    return packet
