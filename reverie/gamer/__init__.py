"""Core single-prompt game-compilation pipeline for Reverie-Gamer."""

from .animation_pipeline import build_animation_plan
from .asset_pipeline import build_asset_pipeline_plan, asset_pipeline_markdown
from .asset_budgeting import build_asset_budget
from .character_factory import build_character_kits
from .content_lattice import build_content_matrix
from .continuation_director import (
    build_continuation_recommendations,
    continuation_recommendations_markdown,
)
from .environment_factory import build_environment_kits
from .expansion_planner import (
    build_content_expansion_plan,
    build_expansion_backlog,
    build_resume_state,
    content_expansion_markdown,
    expansion_backlog_markdown,
    resume_state_markdown,
)
from .faction_graph import build_enemy_faction_packet, build_faction_graph
from .gameplay_factory import build_boss_arc, build_gameplay_factory
from .milestone_planner import build_feature_matrix, build_milestone_board, build_risk_register
from .production_plan import (
    build_blueprint_from_request,
    build_production_plan,
    build_vertical_slice_plan,
    production_plan_markdown,
    vertical_slice_markdown,
)
from .program_compiler import build_game_program, game_bible_markdown
from .prompt_compiler import compile_game_prompt
from .reference_intelligence import build_reference_intelligence, scan_reference_catalog
from .region_expander import build_region_expansion_plan, build_region_kits
from .runtime_capability_graph import build_runtime_capability_graph
from .runtime_delivery import build_runtime_delivery_plan
from .runtime_registry import discover_runtime_profiles, select_runtime_profile
from .save_migration import build_save_migration_plan
from .scope_estimator import estimate_scope
from .system_generators import (
    build_system_packet_bundle,
    build_task_graph,
    system_packet_markdown,
    task_graph_markdown,
)
from .verification import (
    build_combat_feel_report,
    build_performance_budget,
    build_quality_gate_report,
    evaluate_slice_score,
    slice_score_markdown,
)
from .vertical_slice_builder import build_vertical_slice_project
from .world_program import build_questline_program, build_world_program

__all__ = [
    "build_animation_plan",
    "asset_pipeline_markdown",
    "build_asset_budget",
    "build_asset_pipeline_plan",
    "build_blueprint_from_request",
    "build_boss_arc",
    "build_character_kits",
    "build_combat_feel_report",
    "build_content_expansion_plan",
    "build_content_matrix",
    "build_continuation_recommendations",
    "build_enemy_faction_packet",
    "build_environment_kits",
    "build_expansion_backlog",
    "build_feature_matrix",
    "build_faction_graph",
    "build_game_program",
    "build_gameplay_factory",
    "build_milestone_board",
    "build_performance_budget",
    "build_production_plan",
    "build_quality_gate_report",
    "build_questline_program",
    "build_reference_intelligence",
    "build_region_expansion_plan",
    "build_region_kits",
    "build_risk_register",
    "build_resume_state",
    "build_runtime_capability_graph",
    "build_runtime_delivery_plan",
    "build_save_migration_plan",
    "build_system_packet_bundle",
    "build_task_graph",
    "build_vertical_slice_plan",
    "build_vertical_slice_project",
    "build_world_program",
    "compile_game_prompt",
    "discover_runtime_profiles",
    "evaluate_slice_score",
    "estimate_scope",
    "continuation_recommendations_markdown",
    "content_expansion_markdown",
    "expansion_backlog_markdown",
    "game_bible_markdown",
    "production_plan_markdown",
    "resume_state_markdown",
    "scan_reference_catalog",
    "select_runtime_profile",
    "slice_score_markdown",
    "system_packet_markdown",
    "task_graph_markdown",
    "vertical_slice_markdown",
]
