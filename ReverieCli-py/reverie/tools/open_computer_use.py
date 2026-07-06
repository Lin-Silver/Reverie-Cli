"""Nine embedded tools compatible with the Open Computer Use MCP contract."""

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


class _ComputerUseTool(BaseTool):
    tool_category = "desktop"
    tool_tags = ("desktop", "accessibility", "computer-use", "embedded-mcp")
    concurrency_safe = False
    always_load = True

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
                f"{item['name']} -- {item['name']} [running, pid={item['pid']}, window={item['window_title']}]"
                for item in apps
            ]
            return ToolResult.ok("\n".join(lines) or "No accessible desktop apps found.", data={"apps": apps})

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
            header = [
                f"App: {state.process_name} (pid={state.process_id})",
                f"Window: {state.window_title or 'untitled'}",
                "Accessibility tree:",
            ]
            output = "\n".join(header + state.tree_lines)
            data_url = f"data:image/png;base64,{state.screenshot_base64}"
            return ToolResult.ok(
                output,
                data={
                    "app": state.process_name,
                    "pid": state.process_id,
                    "window_title": state.window_title,
                    "window_bounds": state.bounds,
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
    description = "Click an element by index, or pixel coordinates from the latest app screenshot."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {"type": "string"},
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
            service.click(app, **kwargs)
            return ToolResult.ok("Click completed. Refresh get_app_state before the next app action.")

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
            lambda service: (
                service.drag(app, from_x, from_y, to_x, to_y),
                ToolResult.ok("Drag completed. Refresh get_app_state before the next app action."),
            )[1]
        )


class PerformSecondaryActionTool(_ComputerUseTool):
    name = "perform_secondary_action"
    description = "Invoke a secondary accessibility action exposed by an element."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {"type": "string"},
            "action": {"type": "string"},
        },
        "required": ["app", "element_index", "action"],
        "additionalProperties": False,
    }

    def execute(self, app: str, element_index: str, action: str, **kwargs) -> ToolResult:
        return self._run(
            lambda service: (
                service.perform_secondary_action(app, element_index, action),
                ToolResult.ok(f"Secondary action {action!r} completed."),
            )[1]
        )


class ScrollTool(_ComputerUseTool):
    name = "scroll"
    description = "Scroll an accessibility element in a direction by a number of pages."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {"type": "string"},
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
            "pages": {"type": "number", "default": 1},
        },
        "required": ["app", "element_index", "direction"],
        "additionalProperties": False,
    }

    def execute(self, app: str, element_index: str, direction: str, pages: float = 1, **kwargs) -> ToolResult:
        return self._run(
            lambda service: (
                service.scroll(app, element_index, direction, pages),
                ToolResult.ok("Scroll completed. Refresh get_app_state before the next app action."),
            )[1]
        )


class SetValueTool(_ComputerUseTool):
    name = "set_value"
    description = "Set the value of a settable accessibility element."
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "element_index": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["app", "element_index", "value"],
        "additionalProperties": False,
    }

    def execute(self, app: str, element_index: str, value: str, **kwargs) -> ToolResult:
        return self._run(
            lambda service: (
                service.set_value(app, element_index, value),
                ToolResult.ok("Element value updated."),
            )[1]
        )


class TypeTextTool(_ComputerUseTool):
    name = "type_text"
    description = "Type literal text into the focused element of an observed app."
    parameters = {
        "type": "object",
        "properties": {"app": {"type": "string"}, "text": {"type": "string"}},
        "required": ["app", "text"],
        "additionalProperties": False,
    }

    def execute(self, app: str, text: str, **kwargs) -> ToolResult:
        return self._run(
            lambda service: (service.type_text(app, text), ToolResult.ok("Text typed."))[1]
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
            lambda service: (service.press_key(app, key), ToolResult.ok(f"Key {key!r} pressed."))[1]
        )


COMPUTER_USE_TOOL_CLASSES: tuple[Type[BaseTool], ...] = (
    ListAppsTool,
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
    "ListAppsTool",
    "PerformSecondaryActionTool",
    "PressKeyTool",
    "ScrollTool",
    "SetValueTool",
    "TypeTextTool",
]
