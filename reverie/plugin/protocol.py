"""Reverie CLI runtime plugin protocol helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import re

from reverie.modes import normalize_mode


RC_PROTOCOL_VERSION = "1.0"


def sanitize_plugin_identifier(value: Any) -> str:
    """Normalize plugin ids and command names into tool-safe identifiers."""
    text = str(value or "").strip().lower()
    if not text:
        return "plugin"
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "plugin"


def normalize_runtime_parameters(raw_schema: Any) -> dict[str, Any]:
    """Return a safe JSON-schema object for runtime plugin commands."""
    if not isinstance(raw_schema, dict):
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    schema = dict(raw_schema)
    if str(schema.get("type", "") or "").strip() != "object":
        schema["type"] = "object"

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        schema["properties"] = {}

    required = schema.get("required")
    if not isinstance(required, list):
        schema["required"] = []
    else:
        schema["required"] = [str(item).strip() for item in required if str(item).strip()]

    return schema


def normalize_mode_list(raw_modes: Any) -> tuple[str, ...]:
    """Normalize include/exclude mode lists from plugin protocol payloads."""
    if not isinstance(raw_modes, list):
        return tuple()

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_modes:
        text = str(item or "").strip()
        if not text:
            continue
        mode = normalize_mode(text)
        if mode in seen:
            continue
        seen.add(mode)
        normalized.append(mode)
    return tuple(normalized)


@dataclass(frozen=True)
class RuntimePluginCommandSpec:
    """One command exposed by a Reverie CLI runtime plugin."""

    name: str
    description: str
    parameters: dict[str, Any]
    expose_as_tool: bool = True
    include_modes: tuple[str, ...] = ()
    exclude_modes: tuple[str, ...] = ()
    guidance: str = ""
    example: str = ""


@dataclass(frozen=True)
class RuntimePluginHandshake:
    """Normalized response from `<plugin> -RC`."""

    protocol_version: str
    plugin_id: str
    display_name: str
    version: str
    runtime_family: str
    description: str = ""
    tool_call_hint: str = ""
    system_prompt: str = ""
    commands: tuple[RuntimePluginCommandSpec, ...] = ()

    @property
    def tool_commands(self) -> tuple[RuntimePluginCommandSpec, ...]:
        return tuple(command for command in self.commands if command.expose_as_tool)


def normalize_runtime_handshake(
    raw_payload: Any,
    *,
    fallback_plugin_id: str,
    fallback_display_name: str,
    fallback_runtime_family: str,
) -> Optional[RuntimePluginHandshake]:
    """Normalize raw `-RC` JSON output into a protocol object."""
    if not isinstance(raw_payload, dict):
        return None

    plugin_id = sanitize_plugin_identifier(raw_payload.get("plugin_id") or raw_payload.get("id") or fallback_plugin_id)
    display_name = str(
        raw_payload.get("display_name")
        or raw_payload.get("name")
        or fallback_display_name
        or plugin_id
    ).strip() or plugin_id
    version = str(raw_payload.get("version") or "").strip()
    runtime_family = str(
        raw_payload.get("runtime_family")
        or raw_payload.get("kind")
        or fallback_runtime_family
        or "runtime"
    ).strip() or "runtime"
    description = str(raw_payload.get("description") or "").strip()
    tool_call_hint = str(raw_payload.get("tool_call_hint") or "").strip()
    system_prompt = str(raw_payload.get("system_prompt") or "").strip()
    protocol_version = str(raw_payload.get("protocol_version") or RC_PROTOCOL_VERSION).strip() or RC_PROTOCOL_VERSION

    commands: list[RuntimePluginCommandSpec] = []
    for raw_command in raw_payload.get("commands", []) or []:
        if not isinstance(raw_command, dict):
            continue
        command_name = sanitize_plugin_identifier(raw_command.get("name") or raw_command.get("id"))
        if not command_name:
            continue
        commands.append(
            RuntimePluginCommandSpec(
                name=command_name,
                description=str(raw_command.get("description") or "").strip()
                or f"Runtime plugin command `{command_name}` from `{plugin_id}`.",
                parameters=normalize_runtime_parameters(raw_command.get("parameters")),
                expose_as_tool=bool(raw_command.get("expose_as_tool", True)),
                include_modes=normalize_mode_list(raw_command.get("include_modes", [])),
                exclude_modes=normalize_mode_list(raw_command.get("exclude_modes", [])),
                guidance=str(raw_command.get("guidance") or "").strip(),
                example=str(raw_command.get("example") or "").strip(),
            )
        )

    return RuntimePluginHandshake(
        protocol_version=protocol_version,
        plugin_id=plugin_id,
        display_name=display_name,
        version=version,
        runtime_family=runtime_family,
        description=description,
        tool_call_hint=tool_call_hint,
        system_prompt=system_prompt,
        commands=tuple(commands),
    )


def build_runtime_tool_name(
    plugin_id: str,
    command_name: str,
    used_names: Optional[set[str]] = None,
) -> str:
    """Build a unique dynamic tool name for one runtime-plugin command."""
    base = f"rc_{sanitize_plugin_identifier(plugin_id)}_{sanitize_plugin_identifier(command_name)}"
    if used_names is None or base not in used_names:
        return base

    suffix = 2
    candidate = f"{base}_{suffix}"
    while candidate in used_names:
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate
