"""Embedded tools compatible with the Open Computer Use MCP contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Type

from .base import BaseTool, ToolResult
from ..computer_use import ComputerUseError, OpenComputerUseService
from ..config import get_project_data_dir


def _service(context: Dict[str, Any]) -> OpenComputerUseService:
    existing = context.get("open_computer_use_service")
    if isinstance(existing, OpenComputerUseService):
        return existing
    project_data_dir = context.get("project_data_dir")
    if project_data_dir:
        output_dir = Path(project_data_dir) / "computer_use" / "observations"
    else:
        output_dir = get_project_data_dir(context.get("project_root")) / "computer_use" / "observations"
    service = OpenComputerUseService(output_dir)
    context["open_computer_use_service"] = service
    return service


_REFRESH_HINT = "Refresh get_app_state before the next app action."


def _action_result(report: Any, fallback: str) -> ToolResult:
    """Report what the desktop actually did, not just that a call returned.

    The service returns a description of the observed change; older/stubbed
    services return nothing, in which case only the fallback is reported.
    """
    observed = str(report or "").strip()
    output = f"{observed}\n{_REFRESH_HINT}" if observed else f"{fallback} {_REFRESH_HINT}"
    return ToolResult.ok(output, data={"observed_change": observed})


class _ComputerUseTool(BaseTool):
    tool_category = "desktop"
    tool_tags = ("desktop", "accessibility", "computer-use", "embedded-mcp")
    concurrency_safe = False
    always_load = True
    workspace_checkpoint = False

    def _run(self, operation) -> ToolResult:
        try:
            return operation(_service(self.context))
        except ComputerUseError as exc:
            return ToolResult.fail(str(exc))
        except Exception as exc:
            return ToolResult.fail(f"Computer Use failed: {exc}")


class ListAppsTool(_ComputerUseTool):
    name = "list_apps"
    read_only = True
    description = "List currently running desktop apps and their accessible top-level windows."
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, **kwargs) -> ToolResult:
        def operation(service: OpenComputerUseService) -> ToolResult:
            apps = service.list_apps()
            lines = [
                "{name} [{status}, pid={pid}, window={window_title}]".format(
                    name=item["name"],
                    status=item.get("status") or "running",
                    pid=item["pid"],
                    window_title=item["window_title"],
                )
                for item in apps
            ]
            output = "\n".join(lines) or (
                "No accessible desktop apps found. Use launch_app to start the program you need."
            )
            return ToolResult.ok(output, data={"apps": apps})

        return self._run(operation)


class LaunchAppTool(_ComputerUseTool):
    name = "launch_app"
    description = (
        "Start a program, document, or URL that is not running yet, and report the window it opened. "
        "Use this instead of hunting for a desktop or taskbar icon: 'msedge', 'notepad', a full path, "
        "or a https:// URL all work."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Executable name ('msedge', 'notepad'), full path, document path, or URL. "
                    "Bare names are resolved the same way the Run dialog resolves them."
                ),
            },
            "arguments": {
                "type": "string",
                "description": "Command-line arguments, for example the URL to open in a browser.",
            },
        },
        "required": ["target"],
        "additionalProperties": False,
    }

    def get_execution_message(self, **kwargs) -> str:
        return f"Launching {kwargs.get('target', 'an app')}..."

    def execute(self, target: str, arguments: str = "", **kwargs) -> ToolResult:
        def operation(service: OpenComputerUseService) -> ToolResult:
            report = service.launch_app(target, arguments=arguments)
            return ToolResult.ok(
                f"{report}\nCall get_app_state on the new window before acting on it.",
                data={"target": target, "arguments": arguments, "observed_change": report},
            )

        return self._run(operation)


class GetAppStateTool(_ComputerUseTool):
    name = "get_app_state"
    read_only = True
    description = (
        "Get an already running app's screenshot and accessibility tree. Call this once per assistant turn "
        "before interacting with that app; element indexes are scoped to the latest state."
    )
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "App name, window title, executable name, or PID."},
            "show_full_text": {"type": "boolean", "description": "Disable the default 500-character text limit."},
        },
        "required": ["app"],
        "additionalProperties": False,
    }

    def execute(self, app: str, show_full_text: bool = False, **kwargs) -> ToolResult:
        def operation(service: OpenComputerUseService) -> ToolResult:
            state = service.get_app_state(app, show_full_text=bool(show_full_text))
            scale = float(getattr(state, "screenshot_scale", 1.0) or 1.0)
            header = [
                f"App: {state.process_name} (pid={state.process_id})",
                f"Window: {state.window_title or 'untitled'}",
            ]
            if abs(scale - 1.0) > 1e-6:
                header.append(
                    f"Screenshot scaled to {scale:.3f} of the window size; element frames and x/y "
                    "coordinates are both in this screenshot's pixel space."
                )
            header.append("Accessibility tree:")
            output = "\n".join(header + state.tree_lines)
            data_url = f"data:image/png;base64,{state.screenshot_base64}"
            return ToolResult.ok(
                output,
                data={
                    "app": state.process_name,
                    "pid": state.process_id,
                    "window_title": state.window_title,
                    "window_bounds": state.bounds,
                    "screenshot_scale": scale,
                    "elements": [item.to_dict() for item in state.elements.values()],
                    "file_path": state.screenshot_path,
                    "mime_type": "image/png",
                    "base64_image": state.screenshot_base64,
                    "message_content": [
                        {"type": "text", "text": output},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            )

        return self._run(operation)


class ClickTool(_ComputerUseTool):
    name = "click"
    description = (
        "Click an element by index, or pixel coordinates from the latest app screenshot. "
        "A single left click only selects list items and icons; use click_count=2 or "
        "perform_secondary_action(action=\"Invoke\") to activate one."
    )
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {
                "type": "string",
                "description": "Element index from the latest get_app_state tree, for example \"6\".",
            },
            "x": {"type": "number"},
            "y": {"type": "number"},
            "click_count": {"type": "integer", "minimum": 1, "default": 1},
            "mouse_button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
        },
        "required": ["app"],
        "additionalProperties": False,
    }

    def execute(self, app: str, **kwargs) -> ToolResult:
        def operation(service: OpenComputerUseService) -> ToolResult:
            return _action_result(service.click(app, **kwargs), "Click completed.")

        return self._run(operation)


class DragTool(_ComputerUseTool):
    name = "drag"
    description = "Drag between two pixel coordinates from the latest app screenshot."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "from_x": {"type": "number"},
            "from_y": {"type": "number"},
            "to_x": {"type": "number"},
            "to_y": {"type": "number"},
        },
        "required": ["app", "from_x", "from_y", "to_x", "to_y"],
        "additionalProperties": False,
    }

    def execute(self, app: str, from_x: Any, from_y: Any, to_x: Any, to_y: Any, **kwargs) -> ToolResult:
        return self._run(
            lambda service: _action_result(
                service.drag(app, from_x, from_y, to_x, to_y), "Drag completed."
            )
        )


class PerformSecondaryActionTool(_ComputerUseTool):
    name = "perform_secondary_action"
    description = (
        "Invoke a secondary accessibility action exposed by an element. This is the reliable way to "
        "activate icons, list items, and menu entries that a single click would only select."
    )
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {
                "type": "string",
                "description": "Element index from the latest get_app_state tree, for example \"6\".",
            },
            "action": {
                "type": "string",
                "enum": ["Invoke", "Toggle", "Select", "Expand", "Collapse", "ScrollIntoView"],
                "description": "One of the element's listed Secondary Actions.",
            },
        },
        "required": ["app", "element_index", "action"],
        "additionalProperties": False,
    }

    def execute(self, app: str, element_index: str, action: str, **kwargs) -> ToolResult:
        return self._run(
            lambda service: _action_result(
                service.perform_secondary_action(app, element_index, action),
                f"Secondary action {action!r} completed.",
            )
        )


class ScrollTool(_ComputerUseTool):
    name = "scroll"
    description = "Scroll an accessibility element in a direction by a number of pages."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {
                "type": "string",
                "description": "Element index from the latest get_app_state tree, for example \"6\".",
            },
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
            "pages": {"type": "number", "default": 1},
        },
        "required": ["app", "element_index", "direction"],
        "additionalProperties": False,
    }

    def execute(self, app: str, element_index: str, direction: str, pages: float = 1, **kwargs) -> ToolResult:
        return self._run(
            lambda service: _action_result(
                service.scroll(app, element_index, direction, pages), "Scroll completed."
            )
        )


class SetValueTool(_ComputerUseTool):
    name = "set_value"
    description = "Set the value of a settable accessibility element and read it back to confirm."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {
                "type": "string",
                "description": "Element index from the latest get_app_state tree, for example \"6\".",
            },
            "value": {"type": "string"},
        },
        "required": ["app", "element_index", "value"],
        "additionalProperties": False,
    }

    def execute(self, app: str, element_index: str, value: str, **kwargs) -> ToolResult:
        return self._run(
            lambda service: _action_result(
                service.set_value(app, element_index, value), "Element value updated."
            )
        )


class TypeTextTool(_ComputerUseTool):
    name = "type_text"
    description = (
        "Type literal text into the focused element of an observed app. The text is read back and "
        "compared, so a report of 'unverified' means the field does not hold what was sent; prefer "
        "set_value when the target exposes a value and the exact string matters."
    )
    parameters = {
        "type": "object",
        "properties": {"app": {"type": "string"}, "text": {"type": "string"}},
        "required": ["app", "text"],
        "additionalProperties": False,
    }

    def execute(self, app: str, text: str, **kwargs) -> ToolResult:
        return self._run(
            lambda service: _action_result(service.type_text(app, text), "Text typed.")
        )


class PressKeyTool(_ComputerUseTool):
    name = "press_key"
    description = (
        "Press a key or key combination using xdotool-style names, for example Return, Tab, ctrl+c, or super+s."
    )
    parameters = {
        "type": "object",
        "properties": {"app": {"type": "string"}, "key": {"type": "string"}},
        "required": ["app", "key"],
        "additionalProperties": False,
    }

    def execute(self, app: str, key: str, **kwargs) -> ToolResult:
        return self._run(
            lambda service: _action_result(service.press_key(app, key), f"Key {key!r} pressed.")
        )


COMPUTER_USE_TOOL_CLASSES: tuple[Type[BaseTool], ...] = (
    ListAppsTool,
    LaunchAppTool,
    GetAppStateTool,
    ClickTool,
    DragTool,
    PerformSecondaryActionTool,
    ScrollTool,
    SetValueTool,
    TypeTextTool,
    PressKeyTool,
)


__all__ = [
    "COMPUTER_USE_TOOL_CLASSES",
    "ClickTool",
    "DragTool",
    "GetAppStateTool",
    "LaunchAppTool",
    "ListAppsTool",
    "PerformSecondaryActionTool",
    "PressKeyTool",
    "ScrollTool",
    "SetValueTool",
    "TypeTextTool",
]
