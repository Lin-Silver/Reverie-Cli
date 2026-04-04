"""Combat packet generator."""

from __future__ import annotations

from typing import Any, Dict

from .shared import experience, packet_header, production, reference_titles, source_systems


def build_combat_packet(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    current_experience = experience(game_request)
    content_scale = production(game_request).get("content_scale", {})
    references = reference_titles(game_request)
    packet = packet_header(
        "combat",
        "Combat",
        game_request,
        blueprint,
        runtime_profile,
        source_systems(game_request, ("combat", "enemy_ai", "encounters", "lock_on")),
    )
    packet.update(
        {
            "slice_goal": "Ship one readable offensive and defensive loop with layered pressures, a guardian-style finale, and one clear reward beat.",
            "player_fantasy": "Read an opening, commit to timing, dodge pressure, and feel meaningfully stronger after winning the encounter.",
            "dependencies": ["character_controller"],
            "requirements": [
                f"Anchor combat around {current_experience.get('combat_model', 'ability_action')} with one light chain and one cooldown or utility button.",
                "Support enemy wind-up, hit reaction, and defeat feedback that remain legible under third-person camera motion.",
                "Connect encounter clear to quest advancement and progression reward payout.",
                "Cover at least one melee pressure unit and one ranged or space-control unit.",
                "Include one elite or boss-like guardian that closes the slice with a stronger telegraph and pressure pattern.",
            ],
            "combat_loop": [
                "acquire or approach a target",
                "create an opening with movement, dodge, or spacing",
                "land one or more attacks and confirm readable hit feedback",
                "survive retaliation and convert the win into objective progress",
            ],
            "state_model": [
                "neutral",
                "windup",
                "active",
                "recovery",
                "hit_reaction",
                "defeated",
            ],
            "encounter_budget": {
                "enemy_families": int(content_scale.get("enemy_families", 1)),
                "boss_encounters": max(1, int(content_scale.get("boss_encounters", 0))),
                "elite_encounters": max(1, int(content_scale.get("elite_encounters", 0))),
                "minimum_targets_in_slice": 3,
            },
            "enemy_archetypes": [
                {
                    "id": "sentinel_melee",
                    "role": "close pressure",
                    "readable_window": "0.6s windup before strike",
                },
                {
                    "id": "sentinel_ranged",
                    "role": "space denial",
                    "readable_window": "projectile tell before release",
                },
                {
                    "id": "sentinel_elite",
                    "role": "detour elite",
                    "readable_window": "heavy lunge tell before a punishable commitment",
                },
                {
                    "id": "shrine_warden",
                    "role": "guardian boss",
                    "readable_window": "phase shift tell before a radial projectile burst",
                },
            ],
            "reward_hooks": [
                "encounter clear advances the shrine objective",
                "defeated enemies drop power or currency reward",
                "elite detour unlocks one optional reward cache or side-route payoff",
                "guardian defeat confirms the slice finale and unlock beat",
                "completion unlocks one progression node for the next run",
            ],
            "telemetry": [
                "target_acquired",
                "attack_landed",
                "player_hit",
                "enemy_defeated",
                "encounter_cleared",
            ],
            "tests": [
                "player can damage and defeat every slice enemy",
                "enemy pressure can damage the player without causing unwinnable stun loops",
                "guardian or boss telegraphs remain readable before burst attacks",
                "combat clear unlocks the next objective state",
                "combat readability remains stable during movement and dash use",
            ],
            "primary_outputs": [
                "combat tuning table",
                "enemy archetype definitions",
                "encounter pacing rules",
                "reward hook contracts",
            ],
            "expansion_hooks": [
                "combo chain branching",
                "element or attribute reactions",
                "elite modifiers and encounter mutators",
                "boss phase authoring",
            ],
            "notes": [
                "References: " + ", ".join(references) if references else "Build combat around high-readability action RPG norms.",
                "Prioritize a trustworthy hit-confirm loop before adding large move lists.",
            ],
        }
    )
    return packet
