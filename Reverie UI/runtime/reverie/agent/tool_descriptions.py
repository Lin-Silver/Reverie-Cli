"""JSON-backed prompt-side tool guidance.

Runtime tool schemas remain authoritative. This module only renders the
human-readable tool playbook that is injected into mode system prompts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Iterable, List

from ..modes import normalize_mode


MANIFEST_RESOURCE = "tool_manifest.json"


def _normalize_manifest_mode(mode: Any) -> str:
    normalized = normalize_mode(str(mode or "reverie"))
    if normalized == "reverie-ant":
        return "ant"
    return normalized


@lru_cache(maxsize=1)
def get_tool_manifest() -> Dict[str, Any]:
    """Load the prompt-facing tool manifest from package data."""
    with resources.files(__package__).joinpath(MANIFEST_RESOURCE).open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError(f"{MANIFEST_RESOURCE} must contain a JSON object")
    return manifest


def _format_list(items: Iterable[Any]) -> List[str]:
    return [str(item).strip() for item in items if str(item or "").strip()]


def _render_parameters(parameters: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for name, description in (parameters or {}).items():
        lines.append(f"- `{name}`: {description}")
    return lines


def _render_examples(examples: Iterable[Any]) -> List[str]:
    rendered = []
    for example in _format_list(examples):
        rendered.append(f"```text\n{example}\n```")
    return rendered


def _render_tool_entry(tool_name: str, tool_data: Dict[str, Any]) -> str:
    lines = [f"### `{tool_name}`"]
    purpose = str(tool_data.get("purpose", "") or "").strip()
    use_when = str(tool_data.get("use_when", "") or "").strip()
    if purpose:
        lines.append(f"- Purpose: {purpose}")
    if use_when:
        lines.append(f"- Use when: {use_when}")

    parameter_lines = _render_parameters(tool_data.get("parameters", {}) if isinstance(tool_data.get("parameters"), dict) else {})
    if parameter_lines:
        lines.append("- Parameters:")
        lines.extend(parameter_lines)

    example_lines = _render_examples(tool_data.get("examples", []) or [])
    if example_lines:
        lines.append("- Example calls:")
        lines.extend(example_lines)

    return "\n".join(lines)


def get_tool_names_for_mode(mode: Any) -> List[str]:
    """Return tool names declared for a mode in the JSON manifest."""
    manifest = get_tool_manifest()
    mode_key = _normalize_manifest_mode(mode)
    profile = (manifest.get("mode_profiles") or {}).get(mode_key) or (manifest.get("mode_profiles") or {}).get("reverie", {})
    return _format_list(profile.get("tools", []) or [])


def get_tool_descriptions_for_mode(mode: str) -> str:
    """Render the JSON-defined tool guidance for the active mode."""
    manifest = get_tool_manifest()
    mode_key = _normalize_manifest_mode(mode)
    profiles = manifest.get("mode_profiles") or {}
    profile = profiles.get(mode_key) or profiles.get("reverie", {})
    tools = manifest.get("tools") or {}

    lines: List[str] = [
        "## Tool Manifest",
        f"- Source: `reverie/agent/{MANIFEST_RESOURCE}`",
        "- Runtime schemas are authoritative; this manifest defines prompt-side tool selection and calling guidance.",
        "",
        f"## {profile.get('title') or 'Mode Tool Surface'}",
    ]

    for workflow_item in _format_list(profile.get("workflow", []) or []):
        lines.append(f"- {workflow_item}")

    lines.extend(["", "## Tool Discovery"])
    for item in _format_list(manifest.get("discovery_rules", []) or []):
        lines.append(f"- {item}")

    lines.extend(["", "## Tool Calling Rules"])
    for item in _format_list(manifest.get("calling_rules", []) or []):
        lines.append(f"- {item}")

    lines.extend(["", "## Available Tools"])
    missing_tools: List[str] = []
    for tool_name in get_tool_names_for_mode(mode_key):
        tool_data = tools.get(tool_name)
        if isinstance(tool_data, dict):
            lines.append(_render_tool_entry(tool_name, tool_data))
        else:
            missing_tools.append(tool_name)

    dynamic_tools = manifest.get("dynamic_tools", []) or []
    if dynamic_tools:
        lines.extend(["", "## Dynamic Tools"])
        for item in dynamic_tools:
            if not isinstance(item, dict):
                continue
            pattern = str(item.get("pattern", "") or "").strip()
            purpose = str(item.get("purpose", "") or "").strip()
            calling_method = str(item.get("calling_method", "") or "").strip()
            if pattern:
                lines.append(f"- `{pattern}`: {purpose} {calling_method}".strip())

    if missing_tools:
        lines.extend(["", "## Manifest Warnings"])
        lines.append(f"- Missing tool definitions: {', '.join(missing_tools)}")

    return "\n".join(line for line in lines if line is not None).strip()


def get_all_tool_descriptions() -> str:
    """Render all JSON-defined tool entries for diagnostics and tests."""
    manifest = get_tool_manifest()
    tools = manifest.get("tools") or {}
    lines = ["## All Tool Definitions"]
    for tool_name in sorted(tools):
        tool_data = tools.get(tool_name)
        if isinstance(tool_data, dict):
            lines.append(_render_tool_entry(tool_name, tool_data))
    return "\n\n".join(lines)
