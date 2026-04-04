"""Core single-prompt game-compilation pipeline for Reverie-Gamer."""

from .asset_pipeline import build_asset_pipeline_plan, asset_pipeline_markdown
from .expansion_planner import (
    build_content_expansion_plan,
    build_expansion_backlog,
    build_resume_state,
    content_expansion_markdown,
    expansion_backlog_markdown,
    resume_state_markdown,
)
from .production_plan import (
    build_blueprint_from_request,
    build_production_plan,
    build_vertical_slice_plan,
    production_plan_markdown,
    vertical_slice_markdown,
)
from .prompt_compiler import compile_game_prompt
from .runtime_registry import discover_runtime_profiles, select_runtime_profile
from .scope_estimator import estimate_scope
from .system_generators import (
    build_system_packet_bundle,
    build_task_graph,
    system_packet_markdown,
    task_graph_markdown,
)
from .verification import evaluate_slice_score, slice_score_markdown
from .vertical_slice_builder import build_vertical_slice_project

__all__ = [
    "asset_pipeline_markdown",
    "build_asset_pipeline_plan",
    "build_blueprint_from_request",
    "build_content_expansion_plan",
    "build_expansion_backlog",
    "build_production_plan",
    "build_resume_state",
    "build_system_packet_bundle",
    "build_task_graph",
    "build_vertical_slice_plan",
    "build_vertical_slice_project",
    "compile_game_prompt",
    "discover_runtime_profiles",
    "evaluate_slice_score",
    "estimate_scope",
    "content_expansion_markdown",
    "expansion_backlog_markdown",
    "production_plan_markdown",
    "resume_state_markdown",
    "select_runtime_profile",
    "slice_score_markdown",
    "system_packet_markdown",
    "task_graph_markdown",
    "vertical_slice_markdown",
]
