"""Template Reverie runtime plugin for Python-to-EXE delivery."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import sys


def _resolve_sdk_dir() -> Path:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(Path(str(bundle_root)).resolve(strict=False) / "_sdk")

    here = Path(__file__).resolve()
    candidates.append(here.parents[1] / "_sdk")
    candidates.append(here.parent / "_sdk")

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists():
            return candidate
    return candidates[0]


_SDK_DIR = _resolve_sdk_dir()
if str(_SDK_DIR) not in sys.path:
    sys.path.insert(0, str(_SDK_DIR))

from runtime_host import ReverieRuntimePluginHost


class TemplateRuntimePlugin(ReverieRuntimePluginHost):
    """Minimal Reverie runtime plugin host template."""

    def build_handshake(self) -> dict[str, Any]:
        return {
            "protocol_version": "1.0",
            "plugin_id": "{{plugin_id}}",
            "display_name": "{{plugin_name}}",
            "version": "0.1.0",
            "runtime_family": "{{plugin_runtime_family}}",
            "description": "{{plugin_description}}",
            "tool_call_hint": (
                "Call rc_{{plugin_id}}_status first to inspect runtime readiness before issuing "
                "runtime-specific commands."
            ),
            "system_prompt": (
                "This plugin is responsible for runtime-specific operations owned by {{plugin_name}}."
            ),
            "commands": [
                {
                    "name": "status",
                    "description": "Report that the plugin is reachable and ready to serve Reverie runtime commands.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"],
                    "guidance": "Use this before other commands if runtime availability is uncertain."
                },
                {
                    "name": "{{plugin_tool_name}}",
                    "description": "Template command for plugin-specific runtime work.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Example payload for the template command."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie-gamer"]
                }
            ]
        }

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command_name == "status":
            return {
                "success": True,
                "output": "{{plugin_name}} is reachable.",
                "error": "",
                "data": {
                    "plugin_id": "{{plugin_id}}",
                    "runtime_family": "{{plugin_runtime_family}}",
                    "cwd": str(Path.cwd()),
                },
            }

        if command_name == "{{plugin_tool_name}}":
            return {
                "success": True,
                "output": "Template command executed.",
                "error": "",
                "data": {
                    "message": str(payload.get("message") or ""),
                },
            }

        return {
            "success": False,
            "output": "",
            "error": f"Unknown command: {command_name}",
            "data": {},
        }


def main(argv: list[str]) -> int:
    return TemplateRuntimePlugin().run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
