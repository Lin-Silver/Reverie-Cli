"""Desktop capability contracts shared by Reverie and Computer Controller."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from reverie.agent.tool_executor import ToolExecutor
from reverie.config import Config, ModelConfig
from reverie.security_policy import required_permission_for_tool
from reverie.tools.base import ToolResult


COMPUTER_TOOLS = {
    "computer_status",
    "computer_list_apps",
    "computer_list_windows",
    "computer_list_displays",
    "computer_list_surfaces",
    "computer_snapshot",
    "computer_find",
    "computer_get",
    "computer_is",
    "computer_screenshot",
    "computer_launch_app",
    "computer_close_app",
    "computer_window",
    "computer_open_system_surface",
    "computer_click",
    "computer_focus",
    "computer_set_value",
    "computer_type_text",
    "computer_select",
    "computer_set_state",
    "computer_press_key",
    "computer_scroll",
    "computer_scroll_to",
    "computer_drag",
    "computer_pointer",
    "computer_wait",
    "computer_clipboard_get",
    "computer_clipboard_set",
    "computer_clipboard_clear",
}

LEGACY_COMPUTER_TOOLS = {
    "list_apps", "launch_app", "get_app_state", "click",
    "perform_secondary_action", "scroll", "drag", "type_text",
    "press_key", "set_value",
}


def _names(executor: ToolExecutor, mode: str) -> set[str]:
    return {item["function"]["name"] for item in executor.get_tool_schemas(mode=mode)}


@pytest.mark.parametrize("mode", ["reverie", "computer-controller"])
def test_both_modes_advertise_one_shared_desktop_contract(tmp_path: Path, mode: str) -> None:
    names = _names(ToolExecutor(tmp_path), mode)

    assert COMPUTER_TOOLS <= names
    assert LEGACY_COMPUTER_TOOLS.isdisjoint(names)


def test_writer_does_not_advertise_desktop_tools(tmp_path: Path) -> None:
    names = _names(ToolExecutor(tmp_path), "writer")

    assert (COMPUTER_TOOLS | LEGACY_COMPUTER_TOOLS).isdisjoint(names)


def test_desktop_permissions_are_declared_independently_of_tool_names(monkeypatch, tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    for name in sorted(COMPUTER_TOOLS):
        tool = executor.get_tool(name)
        assert tool is not None, f"Missing built-in tool: {name}"
        expected = "read_only" if name == "computer_status" else "full_control"
        assert required_permission_for_tool(tool) == expected, name
        # The permission belongs to the capability, rather than its spelling.
        monkeypatch.setattr(tool, "name", "neutral_capability_name")
        assert required_permission_for_tool(tool) == expected, name


def test_all_legacy_desktop_entries_require_full_control(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)

    for name in sorted(LEGACY_COMPUTER_TOOLS):
        tool = executor.get_tool(name)
        assert tool is not None, f"Missing compatibility entry: {name}"
        assert required_permission_for_tool(tool) == "full_control", name


@pytest.mark.parametrize("mode", ["reverie", "computer-controller"])
def test_read_only_permission_exposes_only_desktop_status(tmp_path: Path, mode: str) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("security", {"permission_level": "read_only"})

    assert _names(executor, mode) & COMPUTER_TOOLS == {"computer_status"}


@pytest.mark.parametrize("mode", ["reverie", "computer-controller"])
def test_subagents_cannot_inherit_cached_desktop_schemas(tmp_path: Path, mode: str) -> None:
    executor = ToolExecutor(tmp_path)
    assert COMPUTER_TOOLS <= _names(executor, mode)

    executor.update_context("is_subagent", True)
    executor.update_context("subagent_read_scope", [str(tmp_path)])
    executor.update_context("subagent_write_scope", [str(tmp_path)])

    assert (COMPUTER_TOOLS | LEGACY_COMPUTER_TOOLS).isdisjoint(_names(executor, mode))


@pytest.mark.parametrize("tool_names", [COMPUTER_TOOLS, LEGACY_COMPUTER_TOOLS], ids=["current", "legacy"])
def test_subagent_direct_calls_are_denied_even_with_workspace_write_scope(
    monkeypatch, tmp_path: Path, tool_names: set[str],
) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("agent", SimpleNamespace(mode="reverie", config=Config()))
    executor.update_context("is_subagent", True)
    executor.update_context("subagent_read_scope", [str(tmp_path)])
    executor.update_context("subagent_write_scope", [str(tmp_path)])
    dispatched = []

    for name in sorted(tool_names):
        tool = executor.get_tool(name)
        assert tool is not None, f"Missing tool: {name}"
        # Isolate authorization from schema validation and actual desktop I/O.
        monkeypatch.setattr(tool, "validate_params", lambda arguments: None)
        monkeypatch.setattr(
            tool, "execute",
            lambda _name=name, **kwargs: dispatched.append(_name) or ToolResult.ok("dispatched"),
        )
        result = executor.execute(name, {"path": str(tmp_path / "allowed.txt")})

        assert not result.success, f"Subagent dispatched {name}"
        assert "subagent" in str(result.error).lower(), (name, result.error)

    assert dispatched == []


@pytest.mark.parametrize("supports_vision", [False, True], ids=["text", "vision"])
def test_computer_controller_uses_the_selected_standard_model_without_nvidia(
    monkeypatch, supports_vision: bool,
) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    first = ModelConfig("first", "First", "https://example.invalid/v1", api_key="test")
    selected = ModelConfig(
        "selected", "Selected", "https://example.invalid/v1", api_key="test",
        supports_vision=supports_vision,
    )
    config = Config(
        models=[first, selected], active_model_index=1, active_model_source="standard",
        mode="computer-controller", nvidia={"enabled": False, "api_key": ""},
    )

    assert config.active_model is selected
    assert config.active_model.supports_vision is supports_vision
    assert config.active_model_source == "standard"
    assert config.nvidia.get("api_key") == ""
