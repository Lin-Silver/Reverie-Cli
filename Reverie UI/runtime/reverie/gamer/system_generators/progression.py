"""Progression packet generator."""

from __future__ import annotations

from typing import Any, Dict

from .shared import packet_header, source_systems


def build_progression_packet(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    packet = packet_header(
        "progression",
        "Progression and HUD",
        game_request,
        blueprint,
        runtime_profile,
        source_systems(game_request, ("progression", "ui_hud")),
    )
    packet.update(
        {
            "slice_goal": "Turn slice rewards into visible power growth and surface that growth through concise HUD feedback.",
            "player_fantasy": "Earn a reward, spend it immediately, and feel the next attempt become cleaner or more expressive.",
            "dependencies": ["combat", "quest"],
            "requirements": [
                "Expose at least one reward node that changes movement, survivability, or combat expression.",
                "Support one optional detour reward so side-route mastery can pay off before the final shrine clear.",
                "Keep HUD messaging concise enough that combat and navigation stay readable.",
                "Reflect progression state in save data and completion artifacts.",
            ],
            "reward_track": {
                "id": "slice_core",
                "nodes": [
                    {
                        "id": "wind_step",
                        "effect": "improve dash recovery and traversal pacing",
                    },
                    {
                        "id": "focus_strike",
                        "effect": "increase attack consistency against staggered targets",
                    },
                    {
                        "id": "resonant_guard",
                        "effect": "recover stamina faster after successful dodges",
                    },
                ],
            },
            "ui_contracts": [
                "health and stamina summary",
                "objective line with current step",
                "reward or unlock confirmation",
                "slice completion message with next-step guidance",
            ],
            "telemetry": [
                "reward_offered",
                "reward_selected",
                "progression_unlocked",
                "hud_hint_shown",
                "slice_completed",
            ],
            "tests": [
                "reward is granted after the encounter or final objective",
                "selected progression node changes at least one gameplay parameter",
                "HUD remains readable during damage and reward feedback bursts",
                "progression state restores after reload",
            ],
            "primary_outputs": [
                "reward track data",
                "hud contracts",
                "parameter hooks for upgrades",
                "progression smoke cases",
            ],
            "expansion_hooks": [
                "branching build identities",
                "equipment and relic slots",
                "economy sinks beyond the first slice",
            ],
        }
    )
    return packet
