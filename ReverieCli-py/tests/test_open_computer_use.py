from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from reverie.agent.tool_executor import ToolExecutor
from reverie.agent.agent import _tool_result_history_content
from reverie.computer_use.service import AppSnapshot, ComputerUseError, ElementRecord, OpenComputerUseService
from reverie.tools import open_computer_use as tools_module
from reverie.tools.open_computer_use import COMPUTER_USE_TOOL_CLASSES, ClickTool, GetAppStateTool, LaunchAppTool
from reverie.tools.base import ToolResult


EXPECTED_TOOL_NAMES = {
    "list_apps",
    "launch_app",
    "get_app_state",
    "click",
    "perform_secondary_action",
    "scroll",
    "drag",
    "type_text",
    "press_key",
    "set_value",
}

EMPTY_WORLD = {"windows": {}, "foreground": 0}


def _record(**overrides: Any) -> ElementRecord:
    fields: Dict[str, Any] = {
        "index": "0",
        "runtime_id": (1, 2),
        "automation_id": "save",
        "name": "Save",
        "control_type": "ButtonControl",
        "localized_control_type": "button",
        "class_name": "Button",
        "value": "",
        "process_id": 42,
        "frame": {"x": 5, "y": 8, "width": 90, "height": 24},
        "actions": ["Invoke"],
    }
    fields.update(overrides)
    return ElementRecord(**fields)


def _snapshot(**overrides: Any) -> AppSnapshot:
    fields: Dict[str, Any] = {
        "query": "Editor",
        "process_id": 42,
        "process_name": "Editor",
        "window_title": "Editor - demo.txt",
        "bounds": {"x": 100, "y": 80, "width": 800, "height": 600},
        "elements": {"0": _record()},
        "screenshot_path": "C:/tmp/editor.png",
        "screenshot_base64": "cG5n",
        "tree_lines": ["\t0 button Save"],
        "captured_at": 1.0,
        "window_handle": 0,
        "screenshot_scale": 1.0,
    }
    fields.update(overrides)
    return AppSnapshot(**fields)


def _window(**overrides: Any) -> Dict[str, Any]:
    window = {
        "name": "chrome",
        "pid": 42,
        "window_title": "Demo - Google Chrome",
        "window_handle": 100,
        "window_bounds": {"x": 0, "y": 0, "width": 800, "height": 600},
        "status": "running",
    }
    window.update(overrides)
    return window


def _bare_service(**attributes: Any) -> OpenComputerUseService:
    """Build a service without the Windows-only constructor."""
    service = object.__new__(OpenComputerUseService)
    service._snapshots = {}
    for key, value in attributes.items():
        setattr(service, key, value)
    return service


def _silence_world(monkeypatch, service: OpenComputerUseService, changes: Optional[List[str]] = None) -> None:
    """Make world observation deterministic and instant for unit tests."""
    monkeypatch.setattr(service, "_observe_world", lambda: EMPTY_WORLD)
    monkeypatch.setattr(service, "_await_world_change", lambda before, **kwargs: list(changes or []))
    monkeypatch.setattr(service, "_focus_report", lambda: "")


class _FakeService:
    def __init__(self) -> None:
        self.calls: List[Any] = []
        self.screenshot_scale = 1.0

    def get_app_state(self, app: str, *, show_full_text: bool = False) -> AppSnapshot:
        self.calls.append(("get_app_state", app, show_full_text))
        return _snapshot(query=app, screenshot_scale=self.screenshot_scale)

    def click(self, app: str, **kwargs) -> str:
        self.calls.append(("click", app, kwargs))
        return 'Clicked Editor (left, click_count=1).\nNew window: msedge "YouTube" (pid=7)'

    def launch_app(self, target: str, *, arguments: str = "") -> str:
        self.calls.append(("launch_app", target, arguments))
        return f"Launched {target!r}.\nNew window: msedge \"YouTube\" (pid=7)"


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


def test_embedded_contract_is_the_nine_upstream_tools_plus_launch_app() -> None:
    assert {tool_class.name for tool_class in COMPUTER_USE_TOOL_CLASSES} == EXPECTED_TOOL_NAMES


def test_get_app_state_returns_accessibility_tree_and_inline_screenshot(monkeypatch, tmp_path: Path) -> None:
    service = _FakeService()
    monkeypatch.setattr(tools_module, "_service", lambda context: service)

    result = GetAppStateTool({"project_root": tmp_path}).execute("Editor")

    assert result.success
    assert "0 button Save" in result.output
    assert result.data["elements"][0]["automation_id"] == "save"
    assert result.data["message_content"][1]["image_url"]["url"] == "data:image/png;base64,cG5n"
    assert "Screenshot scaled" not in result.output


def test_get_app_state_states_the_scale_when_the_capture_was_shrunk(monkeypatch, tmp_path: Path) -> None:
    service = _FakeService()
    service.screenshot_scale = 0.5
    monkeypatch.setattr(tools_module, "_service", lambda context: service)

    result = GetAppStateTool({"project_root": tmp_path}).execute("Editor")

    assert "Screenshot scaled to 0.500" in result.output
    assert result.data["screenshot_scale"] == 0.5


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


def test_action_tools_surface_the_observed_change_not_a_canned_success(monkeypatch, tmp_path: Path) -> None:
    service = _FakeService()
    monkeypatch.setattr(tools_module, "_service", lambda context: service)

    result = ClickTool({"project_root": tmp_path}).execute("Editor", element_index="0")

    assert 'New window: msedge "YouTube" (pid=7)' in result.output
    assert result.data["observed_change"].startswith("Clicked Editor")
    assert "Refresh get_app_state" in result.output


def test_launch_app_tool_reports_the_window_it_opened(monkeypatch, tmp_path: Path) -> None:
    service = _FakeService()
    monkeypatch.setattr(tools_module, "_service", lambda context: service)

    result = LaunchAppTool({"project_root": tmp_path}).execute(
        "msedge", arguments="https://www.youtube.com"
    )

    assert result.success
    assert service.calls == [("launch_app", "msedge", "https://www.youtube.com")]
    assert "New window: msedge" in result.output
    assert "get_app_state" in result.output


def test_actions_require_a_prior_app_state() -> None:
    service = _bare_service()

    with pytest.raises(ComputerUseError, match="get_app_state"):
        service._snapshot("Editor")


def test_action_on_a_closed_window_demands_a_fresh_observation(monkeypatch) -> None:
    service = _bare_service()
    service._snapshots = {"editor": _snapshot(window_handle=4242)}
    monkeypatch.setattr(service, "_window_exists", lambda handle: False)

    with pytest.raises(ComputerUseError, match="has closed"):
        service._snapshot("editor")
    assert service._snapshots == {}, "the dead observation must not be reusable"


def test_list_apps_uses_native_window_enumeration(monkeypatch) -> None:
    service = _bare_service()
    windows = [_window()]
    monkeypatch.setattr(service, "_native_windows", lambda: windows)
    monkeypatch.setattr(
        service,
        "_top_level_windows",
        lambda: pytest.fail("desktop-wide UI Automation enumeration must not be used"),
    )

    assert service.list_apps() == windows


def test_resolve_app_binds_uia_to_the_matched_native_handle(monkeypatch) -> None:
    class _Automation:
        def __init__(self) -> None:
            self.handles: List[int] = []

        def ControlFromHandle(self, handle):
            self.handles.append(handle)
            return "bound-control"

    service = _bare_service(auto=_Automation())
    monkeypatch.setattr(service, "_native_windows", lambda: [_window()])
    monkeypatch.setattr(service, "_foreground_window", lambda: 0)

    assert service._resolve_app("Demo - Google Chrome") == "bound-control"
    assert service.auto.handles == [100]


def test_resolve_window_prefers_a_visible_window_over_a_bigger_minimized_one(monkeypatch) -> None:
    """A minimized window reports no bounds, so picking it fails the observation."""
    service = _bare_service()
    minimized = _window(
        window_handle=1,
        status="minimized",
        window_bounds={"x": 0, "y": 0, "width": 1920, "height": 1080},
    )
    visible = _window(window_handle=2, window_bounds={"x": 0, "y": 0, "width": 400, "height": 300})
    monkeypatch.setattr(service, "_native_windows", lambda: [minimized, visible])
    monkeypatch.setattr(service, "_foreground_window", lambda: 0)

    assert service._resolve_window("chrome")["window_handle"] == 2


def test_resolve_window_prefers_the_foreground_window_among_visible_ones(monkeypatch) -> None:
    service = _bare_service()
    background = _window(window_handle=1, window_bounds={"x": 0, "y": 0, "width": 1920, "height": 1080})
    foreground = _window(window_handle=2, window_bounds={"x": 0, "y": 0, "width": 400, "height": 300})
    monkeypatch.setattr(service, "_native_windows", lambda: [background, foreground])
    monkeypatch.setattr(service, "_foreground_window", lambda: 2)

    assert service._resolve_window("chrome")["window_handle"] == 2


def test_unknown_app_points_at_list_apps_and_launch_app(monkeypatch) -> None:
    service = _bare_service()
    monkeypatch.setattr(service, "_native_windows", lambda: [])
    monkeypatch.setattr(service, "_foreground_window", lambda: 0)

    with pytest.raises(ComputerUseError, match="launch_app"):
        service._resolve_window("msedge")


def test_press_key_focuses_the_observed_target_before_sending(monkeypatch) -> None:
    calls: List[Any] = []

    class _Control:
        def SetFocus(self):
            calls.append("focus")

    class _Automation:
        def SendKeys(self, keys, *, charMode):
            calls.append(("keys", keys, charMode))

    service = _bare_service(auto=_Automation())
    service._snapshots = {"chrome": _snapshot(query="chrome")}
    monkeypatch.setattr(service, "_resolve_app", lambda _app: _Control())
    _silence_world(monkeypatch, service)

    report = service.press_key("chrome", "win+down")

    assert calls == ["focus", ("keys", "{Win}{DOWN}", False)]
    assert "No window change was observed" in report


def test_a_click_that_changes_nothing_says_so_instead_of_reporting_success(monkeypatch) -> None:
    """The regression: clicking a desktop icon reported success and launched nothing."""
    clicks: List[str] = []

    class _Icon:
        def Click(self, **kwargs):
            clicks.append("click")

    service = _bare_service()
    service._snapshots = {
        "explorer": _snapshot(
            query="explorer",
            elements={"6": _record(index="6", name="Microsoft Edge", actions=["Invoke", "Select", "ScrollIntoView"])},
        )
    }
    monkeypatch.setattr(service, "_resolve_element", lambda app, index: _Icon())
    _silence_world(monkeypatch, service)

    report = service.click("explorer", element_index="6")

    assert clicks == ["click"]
    assert "No window, title, or focus change was observed" in report
    assert "perform_secondary_action" in report
    assert "launch_app" in report


def test_a_click_that_opens_a_window_reports_that_window(monkeypatch) -> None:
    class _Icon:
        def Click(self, **kwargs):
            pass

    service = _bare_service()
    service._snapshots = {"explorer": _snapshot(query="explorer", elements={"6": _record(index="6")})}
    monkeypatch.setattr(service, "_resolve_element", lambda app, index: _Icon())
    _silence_world(monkeypatch, service, ['New window: msedge "YouTube" (pid=7)'])

    report = service.click("explorer", element_index="6")

    assert 'New window: msedge "YouTube" (pid=7)' in report
    assert "No window" not in report


def test_two_clicks_are_sent_as_one_double_click(monkeypatch) -> None:
    """Two Click() calls half a second apart are not a double-click, so nothing opens."""
    events: List[str] = []

    class _Icon:
        def Click(self, **kwargs):
            events.append("single")

        def DoubleClick(self, **kwargs):
            events.append("double")

    service = _bare_service()
    service._click_control(_Icon(), button="left", count=2)
    assert events == ["double"]

    events.clear()
    service._click_control(_Icon(), button="left", count=3)
    assert events == ["double", "single"]


def test_coordinates_are_read_in_the_screenshot_space_that_was_shown() -> None:
    service = _bare_service()
    snapshot = _snapshot(
        bounds={"x": 100, "y": 50, "width": 1920, "height": 1080},
        screenshot_scale=0.5,
    )

    assert service._absolute_point(snapshot, 200, 100) == (500, 250)
    # An unscaled capture keeps the original one-to-one mapping.
    assert service._absolute_point(_snapshot(bounds={"x": 100, "y": 50, "width": 8, "height": 8}), 4, 6) == (104, 56)


def test_element_frames_use_the_same_scale_as_the_screenshot() -> None:
    bounds = {"x": 100, "y": 50, "width": 1920, "height": 1080}
    frame = {"x": 300, "y": 150, "width": 80, "height": 40}

    assert OpenComputerUseService._local_frame(frame, bounds, 0.5) == {
        "x": 100,
        "y": 50,
        "width": 40,
        "height": 20,
    }
    assert OpenComputerUseService._local_frame(frame, bounds) == {
        "x": 200,
        "y": 100,
        "width": 80,
        "height": 40,
    }


def test_world_diff_names_opened_closed_and_retitled_windows() -> None:
    service = _bare_service()
    before = {
        "windows": {
            1: _window(window_handle=1, name="explorer", window_title="Program Manager"),
            2: _window(window_handle=2, name="notepad", window_title="Untitled - Notepad"),
        },
        "foreground": 1,
    }
    after = {
        "windows": {
            1: _window(window_handle=1, name="explorer", window_title="Program Manager"),
            3: _window(window_handle=3, name="msedge", window_title="YouTube", pid=7),
        },
        "foreground": 3,
    }

    changes = service._diff_world(before, after)

    assert any(change.startswith("New window:") and "msedge" in change for change in changes)
    assert any(change.startswith("Window closed:") and "notepad" in change for change in changes)
    assert any(change.startswith("Foreground window:") and "msedge" in change for change in changes)


def test_world_diff_reports_a_retitled_window() -> None:
    service = _bare_service()
    before = {"windows": {1: _window(window_title="New tab")}, "foreground": 1}
    after = {"windows": {1: _window(window_title="YouTube")}, "foreground": 1}

    assert service._diff_world(before, after) == ['Title changed: "New tab" -> "YouTube"']


def test_launch_app_reports_the_window_that_appeared(monkeypatch) -> None:
    service = _bare_service()
    attempts: List[Any] = []

    def _shell(target: str, arguments: str) -> int:
        attempts.append((target, arguments))
        return 42  # any value above 32 means success

    monkeypatch.setattr(service, "_shell_execute", _shell)
    _silence_world(monkeypatch, service, ['New window: msedge "YouTube" (pid=7)'])

    report = service.launch_app("msedge", arguments="https://www.youtube.com")

    assert attempts == [("msedge", "https://www.youtube.com")]
    assert "Launched 'msedge'" in report
    assert "New window: msedge" in report
    assert "No new window" not in report


def test_launch_app_admits_when_no_window_appeared(monkeypatch) -> None:
    service = _bare_service()
    monkeypatch.setattr(service, "_shell_execute", lambda target, arguments: 42)
    _silence_world(monkeypatch, service)

    report = service.launch_app("msedge", wait_seconds=2)

    assert "No new window appeared within 2s" in report
    assert "list_apps" in report


def test_launch_app_retries_with_an_exe_suffix_then_explains_the_failure(monkeypatch) -> None:
    service = _bare_service()
    tried: List[str] = []

    def _shell(target: str, arguments: str) -> int:
        tried.append(target)
        return 2  # ERROR_FILE_NOT_FOUND

    monkeypatch.setattr(service, "_shell_execute", _shell)
    _silence_world(monkeypatch, service)

    with pytest.raises(ComputerUseError, match="the file was not found"):
        service.launch_app("nosuchapp")

    assert tried == ["nosuchapp", "nosuchapp.exe"]


def test_launch_app_does_not_append_exe_to_a_path_or_url(monkeypatch) -> None:
    service = _bare_service()
    tried: List[str] = []

    def _shell(target: str, arguments: str) -> int:
        tried.append(target)
        return 2

    monkeypatch.setattr(service, "_shell_execute", _shell)
    _silence_world(monkeypatch, service)

    with pytest.raises(ComputerUseError):
        service.launch_app("https://www.youtube.com")

    assert tried == ["https://www.youtube.com"]


def test_set_value_reads_the_value_back(monkeypatch) -> None:
    service = _bare_service()
    monkeypatch.setattr(service, "_resolve_element", lambda app, index: object())
    monkeypatch.setattr(service, "_value", lambda control, *, full: "typed text")

    report = service._verified_value("Editor", "3", "typed text")
    assert "Value is now: typed text" in report

    monkeypatch.setattr(service, "_value", lambda control, *, full: "TYPED TEXT")
    mismatch = service._verified_value("Editor", "3", "typed text")
    assert "reads back as" in mismatch
    assert "get_app_state" in mismatch


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


def test_the_automation_log_is_kept_out_of_the_users_working_directory(tmp_path: Path) -> None:
    """uiautomation writes @AutomationLog.txt into the CWD unless it is redirected."""
    captured: List[str] = []

    class _Logger:
        @staticmethod
        def SetLogFile(path):
            captured.append(str(path))

    service = _bare_service()
    service.output_dir = tmp_path / "data" / "computer_use" / "observations"
    service._redirect_automation_log(SimpleNamespace(Logger=_Logger))

    assert captured == [str(tmp_path / "data" / "computer_use" / "uiautomation.log")]


def test_a_library_without_a_logger_hook_does_not_break_startup(tmp_path: Path) -> None:
    service = _bare_service()
    service.output_dir = tmp_path

    service._redirect_automation_log(SimpleNamespace())
    service._redirect_automation_log(SimpleNamespace(Logger=SimpleNamespace()))
