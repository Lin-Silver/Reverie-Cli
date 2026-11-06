"""Session and cancellation regressions without desktop side effects."""
from types import MethodType, SimpleNamespace

import pytest

from reverie.agent.agent import ReverieAgent
from reverie.computer_use.operations import launch
from reverie.computer_use.runtime import ComputerUseRuntime, failure
from reverie.computer_use.service import OpenComputerUseService
from reverie.desktop_control import RunControl
from reverie.tools.computer import COMPUTER_TOOL_CLASSES, runtime_for


def test_switching_sessions_discards_refs_images_and_native_namespace(tmp_path):
    manager = SimpleNamespace(current=SimpleNamespace(id="first"))
    manager.get_current_session = lambda: manager.current
    context = {"project_data_dir": tmp_path, "session_manager": manager}
    first = runtime_for(context)
    first.images["old-image"] = {"model_visible": True}
    first.legacy["old-app"] = {"refs": {"0": "@old:e1"}}
    assert runtime_for(context) is first

    manager.current = SimpleNamespace(id="second")
    second = runtime_for(context)

    assert second.session_id != first.session_id
    assert first.images == first.legacy == {}
    assert second.images == second.legacy == {}


@pytest.mark.parametrize("method", ["set_history", "clear_history"])
def test_restoring_or_clearing_same_session_invalidates_observations(tmp_path, method):
    context = {"project_data_dir": tmp_path}
    first = runtime_for(context)
    first.images["old-image"] = {"model_visible": True}
    first.legacy["old-app"] = {"refs": {"0": "@old:e1"}}
    agent = SimpleNamespace(tool_executor=SimpleNamespace(context=context), messages=[])
    if method == "set_history":
        ReverieAgent.set_history(agent, [{"role": "user", "content": "restore"}])
    else:
        ReverieAgent.clear_history(agent)

    assert first.images == first.legacy == {}
    assert runtime_for(context).session_id != first.session_id


def _shell_runtime(command):
    runtime = SimpleNamespace(
        control=RunControl(lambda event: None), images={"old-image": {}},
        _verify_binary=lambda: None, command=command,
    )
    runtime.check_cancel = MethodType(ComputerUseRuntime.check_cancel, runtime)
    return runtime


def test_cancelled_launch_never_delivers_shell_request(monkeypatch):
    calls = []
    monkeypatch.setattr(OpenComputerUseService, "_shell_execute", lambda *args: calls.append(args) or 33)
    runtime = _shell_runtime(lambda *args, **kwargs: {"data": []})
    runtime.control.stop()

    with pytest.raises(RuntimeError, match="stopped"):
        launch(runtime, {"target": "https://example.invalid"}, 5000)

    assert calls == []


@pytest.mark.parametrize("error", [
    failure("list-windows", "TIMEOUT", "inventory timed out"),
    RuntimeError("Run stopped by user"),
])
def test_delivered_shell_launch_keeps_disposition_when_observation_fails(monkeypatch, error):
    calls = []
    monkeypatch.setattr(OpenComputerUseService, "_shell_execute", lambda *args: calls.append(args) or 33)
    def command(*args, **kwargs):
        raise error
    runtime = _shell_runtime(command)

    result = launch(runtime, {"target": "https://example.invalid"}, 5000)

    assert len(calls) == 1
    assert result["data"]["disposition"] == {"delivery": "delivered_unverified", "retry": "unsafe"}
    assert result["data"]["verification_scope"] == "launch_request_only"
    assert runtime.images == {}


@pytest.mark.parametrize(("name", "arguments"), [
    ("computer_window", {"action": "delete", "window_id": "w1"}),
    ("computer_click", {"ref": "@s:e1", "physical": "false"}),
    ("computer_click", {"ref": "@s:e1", "count": 0}),
    ("computer_click", {"ref": "@s:e1", "count": 4}),
    ("computer_click", {"ref": "@s:e1", "count": True}),
    ("computer_get", {"ref": "@s:e1", "extra": "unadvertised"}),
    ("computer_launch_app", {"target": "test.exe", "arguments": [7]}),
    ("computer_snapshot", {"window_id": "w1", "timeout_ms": 60001}),
    ("computer_screenshot", {"window_id": "w1", "region": {"x": 0}}),
])
def test_invalid_schema_arguments_are_rejected_before_runtime(monkeypatch, name, arguments):
    import reverie.tools.computer as module
    def unexpected_runtime(context):
        pytest.fail("Invalid arguments reached the desktop runtime")
    monkeypatch.setattr(module, "runtime_for", unexpected_runtime)
    tool = next(cls for cls in COMPUTER_TOOL_CLASSES if cls.name == name)({"project_root": "."})

    result = tool.execute(**arguments)

    assert not result.success
    assert result.data["computer_use"]["error"]["code"] == "INVALID_ARGS"
    assert result.data["computer_use"]["error"]["disposition"]["delivery"] == "not_delivered"
