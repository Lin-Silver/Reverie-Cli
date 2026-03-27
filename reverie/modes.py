"""
Mode registry for Reverie.

Centralizes aliases, descriptions, and mode-switching rules so the CLI,
tooling layer, and system prompts stay in sync.
"""

from __future__ import annotations

from typing import Dict, List


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
        "description": "Game-development mode for GDDs, assets, balancing, playtests, and runtime iteration.",
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
    "computer-controler": "computer-controller",
    "computer controler": "computer-controller",
    "computer": "computer-controller",
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
