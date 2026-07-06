from __future__ import annotations

from pathlib import Path

import pytest

from reverie.agent.tool_executor import ToolExecutor
from reverie.agent.agent import _tool_result_history_content
from reverie.computer_use.service import AppSnapshot, ComputerUseError, ElementRecord, OpenComputerUseService
from reverie.tools import open_computer_use as tools_module
from reverie.tools.open_computer_use import COMPUTER_USE_TOOL_CLASSES, ClickTool, GetAppStateTool
from reverie.tools.base import ToolResult


EXPECTED_TOOL_NAMES = {
    "list_apps",
    "get_app_state",
    "click",
    "perform_secondary_action",
    "scroll",
    "drag",
    "type_text",
    "press_key",
    "set_value",
}


class _FakeService:
    def __init__(self) -> None:
        self.calls = []

    def get_app_state(self, app: str, *, show_full_text: bool = False) -> AppSnapshot:
        self.calls.append(("get_app_state", app, show_full_text))
        record = ElementRecord(
            index="0",
            runtime_id=(1, 2),
            automation_id="save",
            name="Save",
            control_type="ButtonControl",
            localized_control_type="button",
            class_name="Button",
            value="",
            process_id=42,
            frame={"x": 5, "y": 8, "width": 90, "height": 24},
            actions=["Invoke"],
        )
        return AppSnapshot(
            query=app,
            process_id=42,
            process_name="Editor",
            window_title="Editor - demo.txt",
            bounds={"x": 100, "y": 80, "width": 800, "height": 600},
            elements={"0": record},
            screenshot_path="C:/tmp/editor.png",
            screenshot_base64="cG5n",
            tree_lines=["\t0 button Save"],
            captured_at=1.0,
        )

    def click(self, app: str, **kwargs) -> None:
        self.calls.append(("click", app, kwargs))


def test_controller_exposes_open_computer_use_contract_instead_of_legacy_tool(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    controller_names = {
        schema["function"]["name"]
        for schema in executor.get_tool_schemas(mode="computer-controller")
    }
    reverie_names = {
        schema["function"]["name"]
        for schema in executor.get_tool_schemas(mode="reverie")
    }

    assert EXPECTED_TOOL_NAMES <= controller_names
    assert "computer_control" not in controller_names
    assert {"str_replace_editor", "file_ops", "delete_file", "command_exec", "create_file"}.isdisjoint(
        controller_names
    )
    assert EXPECTED_TOOL_NAMES.isdisjoint(reverie_names)


def test_embedded_contract_has_exactly_nine_tools() -> None:
    assert {tool_class.name for tool_class in COMPUTER_USE_TOOL_CLASSES} == EXPECTED_TOOL_NAMES


def test_get_app_state_returns_accessibility_tree_and_inline_screenshot(monkeypatch, tmp_path: Path) -> None:
    service = _FakeService()
    monkeypatch.setattr(tools_module, "_service", lambda context: service)

    result = GetAppStateTool({"project_root": tmp_path}).execute("Editor")

    assert result.success
    assert "0 button Save" in result.output
    assert result.data["elements"][0]["automation_id"] == "save"
    assert result.data["message_content"][1]["image_url"]["url"] == "data:image/png;base64,cG5n"


def test_click_forwards_element_target_to_shared_service(monkeypatch, tmp_path: Path) -> None:
    service = _FakeService()
    monkeypatch.setattr(tools_module, "_service", lambda context: service)

    result = ClickTool({"project_root": tmp_path}).execute(
        "Editor", element_index="0", click_count=2, mouse_button="left"
    )

    assert result.success
    assert service.calls == [
        ("click", "Editor", {"element_index": "0", "click_count": 2, "mouse_button": "left"})
    ]


def test_actions_require_a_prior_app_state() -> None:
    service = object.__new__(OpenComputerUseService)
    service._snapshots = {}

    with pytest.raises(ComputerUseError, match="get_app_state"):
        service._snapshot("Editor")


def test_persisted_tool_history_omits_inline_screenshot_data() -> None:
    result = ToolResult.ok(
        "Observed Editor.",
        data={
            "file_path": "C:/tmp/editor.png",
            "message_content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,very-large"}}
            ],
        },
    )

    content = _tool_result_history_content(result)

    assert content == "Observed Editor.\nMedia: C:/tmp/editor.png"
    assert "base64" not in content
