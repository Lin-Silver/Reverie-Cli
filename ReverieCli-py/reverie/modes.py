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
        "description": "General-purpose coding, automation, and long-running execution mode with Context Engine retrieval, the full core workspace surface, structured task boundaries, Reverie Engine control, and direct Blender/3D modeling capability.",
        "switchable": True,
    },
    "reverie-atlas": {
        "display_name": "Reverie-Atlas",
        "description": "Document-driven spec development mode for complex systems, pairing deep research with Context Engine, spec packages (requirements/design/tasks), and Atlas delivery artifacts.",
        "switchable": True,
    },
    "reverie-gamer": {
        "display_name": "Reverie-Gamer",
        "description": "Work-in-progress game-production mode for compiling prompts into unified Reverie Engine projects, system packets, continuity artifacts, playable vertical slices, legacy-engine migrations, and verification loops.",
        "switchable": True,
    },
    "writer": {
        "display_name": "Writer",
        "description": "Creative writing mode for autonomous, persistent long-form fiction planning, serialized drafting, continuity control, and verified completion.",
        "switchable": True,
    },
    "computer-controller": {
        "display_name": "Computer Controller",
        "description": "Pinned NVIDIA desktop orchestrator using an embedded Open Computer Use-compatible desktop runtime and managed Reverie SubAgents.",
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
    "writer": "writer",
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


# Modes that were removed outright. These are NOT aliases: they no longer
# resolve to anything, so `/mode <name>` must fail loudly. The mapping exists
# only so the CLI can point users at the mode that absorbed the capability.
# Keyed by every spelling a user might still type, valued as
# (replacement mode, what moved where).
RETIRED_MODE_MIGRATIONS: Dict[str, tuple[str, str]] = {
    "spec-driven": (
        "reverie-atlas",
        "Spec authoring (requirements/design/tasks) is now part of reverie-atlas.",
    ),
    "spec-vibe": (
        "reverie",
        "Implementing an approved spec is now handled by the default reverie mode.",
    ),
    "reverie-ant": (
        "reverie",
        "Structured planning, task boundaries, and verification are now built into the default reverie mode.",
    ),
}

# Alternate spellings of a retired mode, mapped to their canonical retired name.
RETIRED_MODE_SPELLINGS: Dict[str, str] = {
    "spec-driven": "spec-driven",
    "reverie-spec-driven": "spec-driven",
    "spec driven": "spec-driven",
    "spec-vibe": "spec-vibe",
    "spec vibe": "spec-vibe",
    "reverie-ant": "reverie-ant",
    "ant": "reverie-ant",
}

RETIRED_MODES: Dict[str, str] = {
    spelling: RETIRED_MODE_MIGRATIONS[canonical][0]
    for spelling, canonical in RETIRED_MODE_SPELLINGS.items()
}


DEFAULT_TOOL_DISCOVERY_PROFILE: Dict[str, tuple[str, ...]] = {
    "focus_categories": tuple(),
    "boost_tools": tuple(),
    "domain_tokens": tuple(),
    "deemphasize_categories": tuple(),
}


MODE_TOOL_DISCOVERY_PROFILES: Dict[str, Dict[str, tuple[str, ...]]] = {
    "reverie": {
        "focus_categories": (
            "retrieval",
            "editing",
            "workspace",
            "context",
            "coordination",
            "planning",
            "game-modeling",
        ),
        # Distinctive capabilities first. `_primary_tool_names_for_mode`
        # (`tools/mode_switch.py:122`) keeps this order and truncates to 8 when
        # listing modes, so anything after the eighth entry is not advertised;
        # a mode listing is only useful if it names what separates the modes,
        # not the editor/shell tools every mode has. Discovery ranking reads
        # this as a set (`tools/tool_catalog.py:321`), so order is display-only.
        "boost_tools": (
            "reverie_engine",
            "blender_modeling_workbench",
            "game_modeling_workbench",
            "task_boundary",
            "task_manager",
            "codebase-retrieval",
            "git-commit-retrieval",
            "str_replace_editor",
            "file_ops",
            "command_exec",
            "notify_user",
        ),
        "domain_tokens": (
            "3d",
            "artifact",
            "asset",
            "blender",
            "bug",
            "build",
            "checkpoint",
            "class",
            "code",
            "execute",
            "file",
            "files",
            "fix",
            "function",
            "game",
            "glb",
            "gltf",
            "godot",
            "implement",
            "mesh",
            "model",
            "modeling",
            "phase",
            "plan",
            "planning",
            "progress",
            "refine",
            "repo",
            "repository",
            "refactor",
            "review",
            "resume",
            "runtime",
            "ship",
            "test",
            "verification",
            "verify",
            "workspace",
        ),
        "deemphasize_categories": ("writer", "atlas", "desktop", "game-design", "game-runtime", "game-scaffold", "game-playtest", "game-data"),
    },
    "reverie-atlas": {
        "focus_categories": ("atlas", "retrieval", "workspace", "context", "planning"),
        "boost_tools": (
            "atlas_delivery_orchestrator",
            "codebase-retrieval",
            "create_file",
            "str_replace_editor",
            "command_exec",
        ),
        "domain_tokens": (
            "acceptance",
            "appendix",
            "architecture",
            "atlas",
            "breakdown",
            "charter",
            "contract",
            "delivery",
            "design",
            "document",
            "documents",
            "handoff",
            "manifest",
            "plan",
            "requirement",
            "resume",
            "slice",
            "spec",
            "task",
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
            "video-generation",
        ),
        "boost_tools": (
            "task_manager",
            "memory_retrieval",
            "memory_manager",
            "game_design_orchestrator",
            "game_project_scaffolder",
            "reverie_engine",
            "text_to_image",
            "text_to_video",
            "game_playtest_lab",
            "game_modeling_workbench",
            "blender_modeling_workbench",
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
            "blender",
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
            "galgame",
            "godot",
            "hud",
            "level",
            "live2d",
            "movement",
            "model",
            "npc",
            "playable",
            "playtest",
            "prototype",
            "production",
            "quest",
            "renpy",
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
    "writer": {
        "focus_categories": ("writer", "retrieval", "context", "coordination"),
        "boost_tools": (
            "serial_novel",
            "novel_context_manager",
            "consistency_checker",
            "plot_analyzer",
            "memory_retrieval",
            "memory_manager",
            "ask_clarification",
        ),
        "domain_tokens": (
            "arc",
            "audience",
            "canon",
            "chapter",
            "character",
            "continuity",
            "dialogue",
            "genre",
            "length",
            "novel",
            "fiction",
            "longform",
            "serialization",
            "serial",
            "pov",
            "plot",
            "scene",
            "style",
            "story",
            "tense",
            "tone",
            "voice",
        ),
        "deemphasize_categories": ("game-design", "game-runtime", "atlas", "desktop"),
    },
    "computer-controller": {
        "focus_categories": ("desktop", "vision", "coordination"),
        "boost_tools": (
            "list_apps",
            "get_app_state",
            "click",
            "perform_secondary_action",
            "scroll",
            "drag",
            "type_text",
            "press_key",
            "set_value",
            "subagent",
        ),
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
    normalized = MODE_ALIASES.get(raw, raw)
    return normalized if normalized in MODE_METADATA else default


def is_known_mode(value: object) -> bool:
    """Whether the supplied name resolves to a real mode (no silent fallback)."""
    raw = str(value or "").strip().lower()
    if not raw:
        return False
    return MODE_ALIASES.get(raw, raw) in MODE_METADATA


def get_retired_mode_replacement(value: object) -> str:
    """Return the mode that absorbed a removed mode, or an empty string."""
    raw = str(value or "").strip().lower()
    return RETIRED_MODES.get(raw, "")


def describe_retired_mode(value: object) -> str:
    """Return migration guidance for a removed mode name, or an empty string."""
    raw = str(value or "").strip().lower()
    canonical = RETIRED_MODE_SPELLINGS.get(raw, "")
    if not canonical:
        return ""
    replacement, note = RETIRED_MODE_MIGRATIONS[canonical]
    return f"Mode '{raw}' has been removed. Use '{replacement}' instead. {note}"


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
