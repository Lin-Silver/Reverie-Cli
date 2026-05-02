"""World-structure packet generator."""

from __future__ import annotations

from typing import Any, Dict

from .shared import packet_header, production, quality_targets, source_systems


def build_world_structure_packet(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    targets = quality_targets(game_request)
    content_scale = production(game_request).get("content_scale", {})
    packet = packet_header(
        "world_structure",
        "World Slice and Asset Contracts",
        game_request,
        blueprint,
        runtime_profile,
        source_systems(game_request, ("world_slice", "asset_pipeline", "interaction")),
    )
    packet.update(
        {
            "slice_goal": "Package one authored zone with route guidance, landmarking, encounter pocket, reward beat, and a finish state.",
            "player_fantasy": "Step into a believable world slice that feels like the first district of a much larger action RPG.",
            "dependencies": ["character_controller", "combat"],
            "requirements": [
                f"Deliver {max(int(content_scale.get('slice_spaces', 1)), 1)} readable playable spaces with a strong landmark silhouette.",
                "Place one encounter pocket between the entry route and the final shrine or objective beat.",
                "Include one optional side-route or overlook reward beat so the slice teaches detour value, not only critical path flow.",
                "Define at least one patrol or guard route per active region so enemies feel stationed in a world, not dropped in as static props.",
                f"Respect the target load-time budget of {targets.get('target_load_time_seconds', 12)} seconds or less for the slice root.",
                "Keep asset contracts and naming rules explicit even when the runtime uses primitive placeholder visuals.",
            ],
            "zone_layout": [
                {
                    "space_id": "entry_ridge",
                    "purpose": "teach movement and orient the camera",
                },
                {
                    "space_id": "combat_pocket",
                    "purpose": "introduce enemy pressure and the main reward gate",
                },
                {
                    "space_id": "purification_shrine",
                    "purpose": "deliver objective completion and expansion hook",
                },
                {
                    "space_id": "overlook_detour",
                    "purpose": "teach optional elite pressure and side-route reward payoff",
                },
            ],
            "landmarks": ["entry_arch", "ruined_watchtower", "purification_shrine"],
            "route_guidance": [
                "major landmark visible from spawn",
                "combat pocket centered on the intended route",
                "shrine readable as the final goal from mid-slice",
            ],
            "asset_contracts": {
                "source_roots": ["assets/raw", "assets/models/source", "design"],
                "runtime_roots": ["assets/processed", "assets/models/runtime"],
                "import_rules": ["naming", "dependencies", "budgets", "smoke_import"],
                "budget_notes": {
                    "hero_proxy_count": 1,
                    "enemy_proxy_count": 2,
                    "landmark_kit_count": 3,
                    "vfx_budget": "one attack hit, one shrine completion effect",
                },
            },
            "telemetry": [
                "landmark_reached",
                "encounter_space_entered",
                "objective_space_entered",
                "patrol_lane_entered",
                "slice_completed",
            ],
            "tests": [
                "player can navigate from spawn to shrine without leaving the intended slice bounds",
                "landmarks communicate route direction during first-time play",
                "asset import notes and runtime folders stay aligned",
                "completion state motivates the next authored expansion step",
            ],
            "primary_outputs": [
                "world slice layout",
                "landmark list",
                "patrol route contracts",
                "asset import contract",
                "content budget notes",
            ],
            "expansion_hooks": [
                "second encounter pocket and side-route reward",
                "streaming-friendly region boundaries",
                "regional patrol populations and local event layers",
                "authored traversal and narrative collectibles",
            ],
        }
    )
    return packet
