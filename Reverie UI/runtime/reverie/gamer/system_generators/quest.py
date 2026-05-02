"""Quest packet generator."""

from __future__ import annotations

from typing import Any, Dict

from .shared import packet_header, production, source_systems


def build_quest_packet(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    content_scale = production(game_request).get("content_scale", {})
    packet = packet_header(
        "quest",
        "Quest and Objective Flow",
        game_request,
        blueprint,
        runtime_profile,
        source_systems(game_request, ("quest", "interaction", "ui_hud")),
    )
    packet.update(
        {
            "slice_goal": "Define one complete objective chain from onboarding and guide contact to encounter clear, guardian defeat, and shrine activation.",
            "player_fantasy": "Always know the next meaningful goal and feel the world respond when each objective state advances.",
            "dependencies": ["combat", "world_structure"],
            "requirements": [
                "Track objective progression through explicit state rather than hidden one-off logic.",
                "Expose failure, retry, reward, and completion messages through the HUD or equivalent feedback layer.",
                "Use at least one NPC interaction or guide beat so the slice teaches the player where the authored route begins.",
                f"Keep the first slice within {max(int(content_scale.get('quest_count', 1)), 1)} authored quest line.",
            ],
            "state_machine": [
                "not_started",
                "guide_contact_active",
                "intro_active",
                "combat_gate_active",
                "guardian_gate_active",
                "goal_available",
                "completed",
            ],
            "slice_objectives": [
                {
                    "id": "meet_guide",
                    "goal": "speak to the guide beacon before entering the ruins",
                    "completion_signal": "guide NPC interaction succeeds",
                },
                {
                    "id": "reach_ruins",
                    "goal": "enter the authored combat-ready space",
                    "completion_signal": "player reaches the ruin landmark volume",
                },
                {
                    "id": "purify_sentinels",
                    "goal": "defeat the sentinel escort and reveal the shrine guardian",
                    "completion_signal": "all non-boss encounter targets marked defeated",
                },
                {
                    "id": "defeat_warden",
                    "goal": "defeat the shrine guardian",
                    "completion_signal": "guardian boss target marked defeated",
                },
                {
                    "id": "activate_shrine",
                    "goal": "interact with the final shrine and complete the slice",
                    "completion_signal": "goal interaction succeeds after guardian gate clears",
                },
            ],
            "reward_contract": {
                "completion_rewards": ["perk:wind_step", "currency:50", "story_flag:shrine_purified"],
                "quest_log_fields": ["quest_id", "state", "current_step", "rewards_claimed", "guide_contacts", "guardian_defeated"],
            },
            "telemetry": [
                "guide_contacted",
                "objective_started",
                "objective_updated",
                "objective_failed",
                "objective_completed",
                "reward_claimed",
            ],
            "tests": [
                "every quest step is reachable in one clean playthrough",
                "combat gate cannot be skipped before the shrine activation step",
                "guardian defeat happens before shrine activation becomes available",
                "completion rewards are granted exactly once",
                "quest state survives save and reload",
            ],
            "primary_outputs": [
                "quest state schema",
                "objective chain data",
                "reward tables",
                "HUD objective copy",
            ],
            "expansion_hooks": [
                "branching quest conditions",
                "faction or affinity gates",
                "multi-zone objective routing",
            ],
        }
    )
    return packet
