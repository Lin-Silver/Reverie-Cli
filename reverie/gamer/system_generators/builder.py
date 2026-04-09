"""Bundle builders for Reverie-Gamer system packets and task graphs."""

from __future__ import annotations

from typing import Any, Dict, List

from .character_controller import build_character_controller_packet
from .combat import build_combat_packet
from .progression import build_progression_packet
from .quest import build_quest_packet
from .save_load import build_save_load_packet
from .shared import project_name, required_systems, target_runtime
from .world_structure import build_world_structure_packet


CORE_PACKET_ORDER = (
    "character_controller",
    "combat",
    "quest",
    "save_load",
    "progression",
    "world_structure",
)

SYSTEM_TO_PACKET = {
    "camera": "character_controller",
    "movement": "character_controller",
    "lock_on": "character_controller",
    "traversal_ability": "character_controller",
    "combat": "combat",
    "enemy_ai": "combat",
    "encounters": "combat",
    "quest": "quest",
    "interaction": "quest",
    "save_load": "save_load",
    "telemetry": "save_load",
    "progression": "progression",
    "ui_hud": "progression",
    "world_slice": "world_structure",
    "asset_pipeline": "world_structure",
}

PACKET_BUILDERS = {
    "character_controller": build_character_controller_packet,
    "combat": build_combat_packet,
    "quest": build_quest_packet,
    "save_load": build_save_load_packet,
    "progression": build_progression_packet,
    "world_structure": build_world_structure_packet,
}


def _ordered_unique(values: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _select_packet_ids(game_request: Dict[str, Any]) -> List[str]:
    current_experience = game_request.get("experience", {})
    creative = game_request.get("creative_target", {})
    requested = required_systems(game_request)
    packet_ids = [SYSTEM_TO_PACKET[system] for system in requested if system in SYSTEM_TO_PACKET]

    if str(current_experience.get("dimension", "3D")) == "3D":
        packet_ids.extend(["character_controller", "quest", "save_load", "progression", "world_structure"])
    if str(current_experience.get("camera_model", "third_person")) == "third_person":
        packet_ids.append("character_controller")
    if str(creative.get("primary_genre", "action_rpg")) in {"action_rpg", "arena"}:
        packet_ids.append("combat")

    ordered = _ordered_unique(packet_ids)
    return [packet_id for packet_id in CORE_PACKET_ORDER if packet_id in ordered]


def _topological_packet_order(packets: Dict[str, Dict[str, Any]], preferred_order: List[str]) -> List[str]:
    visited: set[str] = set()
    result: List[str] = []

    def visit(packet_id: str) -> None:
        if packet_id in visited or packet_id not in packets:
            return
        visited.add(packet_id)
        for dependency in packets[packet_id].get("dependencies", []):
            visit(str(dependency))
        result.append(packet_id)

    for packet_id in preferred_order:
        visit(packet_id)
    return result


def build_system_packet_bundle(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build deterministic system packets for the current slice."""

    packet_ids = _select_packet_ids(game_request)
    packets = {
        packet_id: PACKET_BUILDERS[packet_id](game_request, blueprint, runtime_profile=runtime_profile)
        for packet_id in packet_ids
    }
    expansion_order = _topological_packet_order(packets, packet_ids)
    coverage = {
        system_name: SYSTEM_TO_PACKET[system_name]
        for system_name in required_systems(game_request)
        if system_name in SYSTEM_TO_PACKET
    }
    return {
        "schema_version": "reverie.system_packets/1",
        "project_name": project_name(game_request, blueprint),
        "runtime": target_runtime(blueprint, runtime_profile),
        "packet_order": packet_ids,
        "expansion_order": expansion_order,
        "coverage": coverage,
        "packets": packets,
    }


def system_packet_markdown(bundle: Dict[str, Any]) -> str:
    lines = [f"# System Packets: {bundle.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {bundle.get('runtime', 'reverie_engine')}")
    lines.append("")
    lines.append("## Packet Order")
    for packet_id in bundle.get("expansion_order", []):
        lines.append(f"- {packet_id}")
    lines.append("")

    for packet_id in bundle.get("packet_order", []):
        packet = bundle.get("packets", {}).get(packet_id, {})
        lines.append(f"## {packet.get('display_name', packet_id)}")
        lines.append(f"- Slice Goal: {packet.get('slice_goal', '')}")
        lines.append(f"- Source Systems: {', '.join(packet.get('source_systems', [])) or 'none'}")
        lines.append(f"- Dependencies: {', '.join(packet.get('dependencies', [])) or 'none'}")
        lines.append("")
        lines.append("### Requirements")
        for item in packet.get("requirements", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### Tests")
        for item in packet.get("tests", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### Expansion Hooks")
        for item in packet.get("expansion_hooks", []):
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def build_task_graph(
    game_request: Dict[str, Any],
    blueprint: Dict[str, Any],
    system_bundle: Dict[str, Any],
    *,
    runtime_profile: Dict[str, Any] | None = None,
    production_plan: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a resumable task graph for prompt-to-slice execution."""

    tasks: List[Dict[str, Any]] = [
        {
            "id": "compile_program",
            "title": "Compile the durable game program and milestone artifacts",
            "lane": "program_compilation",
            "depends_on": [],
            "outputs": [
                "artifacts/game_program.json",
                "artifacts/feature_matrix.json",
                "artifacts/milestone_board.json",
                "artifacts/risk_register.json",
            ],
        },
        {
            "id": "compile_request",
            "title": "Compile the single prompt into a structured request",
            "lane": "request_compilation",
            "depends_on": ["compile_program"],
            "outputs": ["artifacts/game_request.json", "artifacts/game_blueprint.json"],
        },
        {
            "id": "runtime_foundation",
            "title": "Choose runtime and materialize the foundation",
            "lane": "runtime_foundation",
            "depends_on": ["compile_request"],
            "outputs": [
                "artifacts/runtime_registry.json",
                "artifacts/runtime_capability_graph.json",
                "artifacts/runtime_delivery_plan.json",
                "artifacts/production_plan.json",
                "artifacts/system_specs.json",
                "artifacts/task_graph.json",
            ],
        },
        {
            "id": "asset_pipeline_seed",
            "title": "Seed the modeling workspace, asset registry, and first production-ready asset queue",
            "lane": "asset_production",
            "depends_on": ["runtime_foundation"],
            "outputs": [
                "artifacts/asset_pipeline.json",
                "artifacts/character_kits.json",
                "artifacts/environment_kits.json",
                "artifacts/animation_plan.json",
                "artifacts/asset_budget.json",
                "data/models/model_registry.yaml",
                "assets/models/source/*",
                "assets/models/runtime/*",
            ],
        },
    ]

    packet_ids = list(system_bundle.get("expansion_order", []))
    packet_map = dict(system_bundle.get("packets", {}) or {})
    for packet_id in packet_ids:
        packet = packet_map.get(packet_id, {})
        tasks.append(
            {
                "id": f"system_{packet_id}",
                "title": f"Implement {packet.get('display_name', packet_id)}",
                "lane": "systems",
                "depends_on": ["runtime_foundation"]
                + [f"system_{dep}" for dep in packet.get("dependencies", []) if dep in packet_map],
                "outputs": list(packet.get("primary_outputs", [])),
                "acceptance": list(packet.get("tests", [])),
            }
        )

    content_dependencies = [
        f"system_{packet_id}"
        for packet_id in ("world_structure", "quest", "progression", "combat")
        if packet_id in packet_map
    ]
    tasks.append(
        {
            "id": "slice_content_integration",
            "title": "Assemble the world slice, objective chain, encounter pacing, and reward loop",
            "lane": "slice_content",
            "depends_on": _ordered_unique(["runtime_foundation", "asset_pipeline_seed"] + content_dependencies),
            "outputs": [
                "main scene or slice root",
                "encounter content",
                "objective chain",
                "reward integration",
                "artifacts/world_program.json",
                "artifacts/region_kits.json",
                "artifacts/faction_graph.json",
                "artifacts/questline_program.json",
                "artifacts/save_migration_plan.json",
            ],
        }
    )
    tasks.append(
        {
            "id": "verification_loop",
            "title": "Run validation, smoke, telemetry, and slice scoring",
            "lane": "verification",
            "depends_on": _ordered_unique(
                ["slice_content_integration"] + [f"system_{packet_id}" for packet_id in packet_ids]
            ),
            "outputs": [
                "playtest/test_plan.md",
                "playtest/quality_gates.json",
                "playtest/performance_budget.json",
                "playtest/combat_feel_report.json",
                "playtest/slice_score.json",
                "playtest/continuation_recommendations.md",
            ],
        }
    )
    tasks.append(
        {
            "id": "continuity_snapshot",
            "title": "Write the durable expansion plan, backlog, and resume state",
            "lane": "continuity",
            "depends_on": ["verification_loop"],
            "outputs": [
                "artifacts/content_expansion.json",
                "artifacts/expansion_backlog.json",
                "artifacts/resume_state.json",
            ],
        }
    )

    plan_lanes = [lane.get("name") for lane in (production_plan or {}).get("lanes", []) if lane.get("name")]
    return {
        "schema_version": "reverie.task_graph/1",
        "project_name": project_name(game_request, blueprint),
        "runtime": target_runtime(blueprint, runtime_profile),
        "lanes": plan_lanes,
        "resume_order": [task["id"] for task in tasks],
        "critical_path": [
            "compile_program",
            "compile_request",
            "runtime_foundation",
            "asset_pipeline_seed",
            "slice_content_integration",
            "verification_loop",
            "continuity_snapshot",
        ],
        "tasks": tasks,
    }


def task_graph_markdown(graph: Dict[str, Any]) -> str:
    lines = [f"# Task Graph: {graph.get('project_name', 'Untitled Reverie Slice')}", ""]
    lines.append(f"Runtime: {graph.get('runtime', 'reverie_engine')}")
    lines.append("")
    lines.append("## Resume Order")
    for item in graph.get("resume_order", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Tasks")
    for task in graph.get("tasks", []):
        lines.append(f"### {task.get('id', 'task')}")
        lines.append(f"- Title: {task.get('title', '')}")
        lines.append(f"- Lane: {task.get('lane', '')}")
        lines.append(f"- Depends On: {', '.join(task.get('depends_on', [])) or 'none'}")
        outputs = task.get("outputs", [])
        if outputs:
            lines.append(f"- Outputs: {', '.join(outputs)}")
        acceptance = task.get("acceptance", [])
        if acceptance:
            lines.append("- Acceptance:")
            for item in acceptance:
                lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines)
