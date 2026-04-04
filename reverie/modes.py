"""
Mode registry for Reverie.

Centralizes aliases, descriptions, and mode-switching rules so the CLI,
tooling layer, and system prompts stay in sync.
"""

from __future__ import annotations

from typing import Any, Dict, List


MODE_METADATA: Dict[str, Dict[str, object]] = {
    "reverie": {
        "display_name": "Reverie",
        "description": "General-purpose coding mode that uses Context Engine plus the smallest useful toolset for focused fixes and end-to-end delivery.",
        "switchable": True,
    },
    "reverie-atlas": {
        "display_name": "Reverie-Atlas",
        "description": "Document-driven spec development mode for complex systems, pairing deep research with Context Engine and Atlas delivery artifacts.",
        "switchable": True,
    },
    "reverie-gamer": {
        "display_name": "Reverie-Gamer",
        "description": "Game-production mode for compiling prompts into structured requests, runtime-aware blueprints, system packets, continuity artifacts, playable vertical slices, and verification loops.",
        "switchable": True,
    },
    "reverie-ant": {
        "display_name": "Reverie-Ant",
        "description": "Structured long-running execution mode for planning, checkpoints, and verification.",
        "switchable": True,
    },
    "spec-driven": {
        "display_name": "Spec-Driven",
        "description": "Spec authoring mode for requirements, design, and implementation task breakdown.",
        "switchable": True,
    },
    "spec-vibe": {
        "display_name": "Spec-Vibe",
        "description": "Implementation mode for executing approved specs with a lighter workflow.",
        "switchable": True,
    },
    "writer": {
        "display_name": "Writer",
        "description": "Creative writing mode for narrative drafting, continuity, and long-form documentation.",
        "switchable": True,
    },
    "computer-controller": {
        "display_name": "Computer Controller",
        "description": "Pinned NVIDIA desktop-autopilot mode for operating the Windows UI through computer_control.",
        "switchable": False,
        "requires_source": "nvidia",
    },
}


MODE_ALIASES = {
    "reverie": "reverie",
    "default": "reverie",
    "reverie-atlas": "reverie-atlas",
    "atlas": "reverie-atlas",
    "reverie deeper": "reverie-atlas",
    "reverie-deeper": "reverie-atlas",
    "deeper": "reverie-atlas",
    "reverie-gamer": "reverie-gamer",
    "gamer": "reverie-gamer",
    "reverie-spec-driven": "spec-driven",
    "spec-driven": "spec-driven",
    "spec driven": "spec-driven",
    "spec-vibe": "spec-vibe",
    "spec vibe": "spec-vibe",
    "writer": "writer",
    "reverie-ant": "reverie-ant",
    "ant": "reverie-ant",
    "computer-controller": "computer-controller",
    "computer controller": "computer-controller",
    "computer-control": "computer-controller",
    "computer control": "computer-controller",
    "computer": "computer-controller",
}

LEGACY_MODE_ALIASES = {
    # Backward compatibility for historical typo variants.
    "computer-controler": "computer-controller",
    "computer controler": "computer-controller",
}

MODE_ALIASES.update(LEGACY_MODE_ALIASES)


DEFAULT_TOOL_DISCOVERY_PROFILE: Dict[str, tuple[str, ...]] = {
    "focus_categories": tuple(),
    "boost_tools": tuple(),
    "domain_tokens": tuple(),
    "deemphasize_categories": tuple(),
}


MODE_TOOL_DISCOVERY_PROFILES: Dict[str, Dict[str, tuple[str, ...]]] = {
    "reverie": {
        "focus_categories": ("retrieval", "editing", "workspace", "context", "coordination"),
        "boost_tools": (
            "codebase-retrieval",
            "git-commit-retrieval",
            "str_replace_editor",
            "file_ops",
            "command_exec",
            "tool_catalog",
        ),
        "domain_tokens": (
            "bug",
            "build",
            "class",
            "code",
            "file",
            "files",
            "fix",
            "function",
            "repo",
            "repository",
            "refactor",
            "test",
            "verify",
            "workspace",
        ),
        "deemphasize_categories": ("game-design", "game-runtime", "game-modeling", "writer", "atlas", "desktop"),
    },
    "reverie-atlas": {
        "focus_categories": ("atlas", "retrieval", "workspace", "context", "planning"),
        "boost_tools": (
            "atlas_delivery_orchestrator",
            "codebase-retrieval",
            "create_file",
            "command_exec",
            "tool_catalog",
        ),
        "domain_tokens": (
            "appendix",
            "architecture",
            "atlas",
            "charter",
            "contract",
            "delivery",
            "document",
            "documents",
            "handoff",
            "manifest",
            "resume",
            "slice",
            "spec",
            "tracker",
        ),
        "deemphasize_categories": ("game-design", "game-runtime", "game-playtest", "writer", "desktop"),
    },
    "reverie-gamer": {
        "focus_categories": (
            "game-design",
            "game-scaffold",
            "game-runtime",
            "game-playtest",
            "game-data",
            "game-modeling",
            "planning",
            "retrieval",
            "orchestration",
            "image-generation",
        ),
        "boost_tools": (
            "tool_catalog",
            "task_manager",
            "game_design_orchestrator",
            "game_project_scaffolder",
            "reverie_engine",
            "reverie_engine_lite",
            "game_playtest_lab",
            "game_modeling_workbench",
            "game_gdd_manager",
            "game_asset_manager",
            "game_balance_analyzer",
            "game_math_simulator",
            "level_design",
            "story_design",
        ),
        "domain_tokens": (
            "2d",
            "3d",
            "action",
            "asset",
            "balance",
            "blueprint",
            "camera",
            "combat",
            "compiler",
            "controller",
            "economy",
            "engine",
            "first",
            "foundation",
            "gdd",
            "game",
            "godot",
            "hud",
            "level",
            "movement",
            "model",
            "npc",
            "playable",
            "playtest",
            "prototype",
            "production",
            "quest",
            "request",
            "resume",
            "runtime",
            "save",
            "scope",
            "slice",
            "score",
            "expansion",
            "story",
            "system",
            "task",
            "task_graph",
            "telemetry",
            "third",
            "validation",
            "vertical",
            "world",
        ),
        "deemphasize_categories": ("writer", "atlas", "desktop"),
    },
    "reverie-ant": {
        "focus_categories": ("planning", "coordination", "retrieval", "workspace", "context"),
        "boost_tools": (
            "task_boundary",
            "notify_user",
            "task_manager",
            "codebase-retrieval",
            "command_exec",
            "tool_catalog",
        ),
        "domain_tokens": (
            "artifact",
            "checkpoint",
            "phase",
            "plan",
            "planning",
            "progress",
            "review",
            "resume",
            "verification",
            "verify",
        ),
        "deemphasize_categories": ("game-design", "game-runtime", "writer", "desktop"),
    },
    "spec-driven": {
        "focus_categories": ("planning", "retrieval", "editing", "workspace", "context"),
        "boost_tools": (
            "codebase-retrieval",
            "create_file",
            "str_replace_editor",
            "command_exec",
            "tool_catalog",
        ),
        "domain_tokens": (
            "acceptance",
            "architecture",
            "breakdown",
            "design",
            "plan",
            "requirement",
            "spec",
            "task",
        ),
        "deemphasize_categories": ("game-design", "writer", "desktop"),
    },
    "spec-vibe": {
        "focus_categories": ("editing", "workspace", "retrieval", "context"),
        "boost_tools": (
            "codebase-retrieval",
            "str_replace_editor",
            "create_file",
            "command_exec",
            "tool_catalog",
        ),
        "domain_tokens": ("approved", "execute", "implement", "refine", "ship", "spec", "wire"),
        "deemphasize_categories": ("game-design", "writer", "desktop"),
    },
    "writer": {
        "focus_categories": ("writer", "retrieval", "context", "coordination"),
        "boost_tools": (
            "novel_context_manager",
            "consistency_checker",
            "plot_analyzer",
            "ask_clarification",
            "tool_catalog",
        ),
        "domain_tokens": (
            "arc",
            "canon",
            "chapter",
            "character",
            "continuity",
            "dialogue",
            "novel",
            "plot",
            "scene",
            "story",
            "tone",
            "voice",
        ),
        "deemphasize_categories": ("game-design", "game-runtime", "atlas", "desktop"),
    },
    "computer-controller": {
        "focus_categories": ("desktop", "vision", "coordination"),
        "boost_tools": ("computer_control", "vision_upload", "tool_catalog"),
        "domain_tokens": (
            "app",
            "browser",
            "click",
            "cursor",
            "desktop",
            "hotkey",
            "observe",
            "screen",
            "type",
            "ui",
            "window",
        ),
        "deemphasize_categories": ("game-design", "game-runtime", "writer", "atlas", "planning"),
    },
}


def normalize_mode(value: object, default: str = "reverie") -> str:
    """Normalize mode aliases into canonical mode identifiers."""
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return MODE_ALIASES.get(raw, raw)


def get_mode_metadata(mode: object) -> Dict[str, object]:
    """Return metadata for a mode, falling back to Reverie."""
    return MODE_METADATA.get(normalize_mode(mode), MODE_METADATA["reverie"])


def get_mode_description(mode: object) -> str:
    """Return a short user-facing description for a mode."""
    return str(get_mode_metadata(mode).get("description", "")).strip()


def get_mode_display_name(mode: object) -> str:
    """Return display name for a mode."""
    return str(get_mode_metadata(mode).get("display_name", "Reverie")).strip()


def list_modes(include_computer: bool = True, switchable_only: bool = False) -> List[str]:
    """List supported modes in the preferred display order."""
    result: List[str] = []
    for mode_name, meta in MODE_METADATA.items():
        if not include_computer and mode_name == "computer-controller":
            continue
        if switchable_only and not bool(meta.get("switchable", False)):
            continue
        result.append(mode_name)
    return result


def get_mode_tool_discovery_profile(mode: object) -> Dict[str, tuple[str, ...]]:
    """Return the tool-discovery bias profile for the supplied mode."""
    normalized = normalize_mode(mode)
    profile = MODE_TOOL_DISCOVERY_PROFILES.get(normalized, {})
    return {
        key: tuple(str(item).strip() for item in profile.get(key, DEFAULT_TOOL_DISCOVERY_PROFILE[key]) if str(item).strip())
        for key in DEFAULT_TOOL_DISCOVERY_PROFILE
    }
