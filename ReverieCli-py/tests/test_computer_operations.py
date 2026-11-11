"""Desktop command mapping and preflight checks without sending native input."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import threading

import pytest
from PIL import Image

from reverie.computer_use.legacy import LegacyComputerUse
from reverie.computer_use.operations import execute
from reverie.computer_use.runtime import NativeDesktopError
from reverie.tools.computer import COMPUTER_TOOL_CLASSES


REF = "@captured:e2"


class _Runtime:
    def check_cancel(self, command):
        pass

    def __init__(self, root: Path, *, error: NativeDesktopError | None = None) -> None:
        self.root = root
        self.images = {}
        self.legacy = {}
        self.calls = []
        self._lock = threading.RLock()
        self.error = error
        self.window = {
            "id": "w-10", "app_name": "Editor.exe", "pid": 42,
            "process_instance": "process-42", "title": "Editor",
            "bounds": {"x": 100, "y": 200, "width": 400, "height": 200},
        }

    def command(self, command: str, args=None, **kwargs) -> dict:
        self.calls.append((command, list(args or []), kwargs))
        if self.error:
            raise self.error
        if command == "list-windows":
            data = [deepcopy(self.window)]
        elif command == "snapshot":
            data = {
                "snapshot_id": "captured", "complete": True,
                "tree": {"ref_id": REF, "role": "button", "name": "Save"},
            }
        else:
            data = {"disposition": {"delivery": "delivered_unverified", "retry": "unsafe"}}
        return {"version": "2.6", "ok": True, "command": command, "data": data}


def _tool(name: str, runtime: _Runtime, project_root: Path):
    cls = next(cls for cls in COMPUTER_TOOL_CLASSES if cls.name == name)
    return cls({"project_root": project_root, "computer_use_runtime": runtime})


def _flag(args: list[str], name: str, value: str) -> bool:
    token = "--" + name
    return f"{token}={value}" in args or any(
        args[index:index + 2] == [token, value] for index in range(len(args))
    )


@pytest.mark.parametrize("name,field,command", [
    ("computer_set_value", "value", "set-value"),
    ("computer_type_text", "text", "type"),
    ("computer_clipboard_set", "text", "clipboard-set"),
])
def test_text_is_sent_via_stdin_instead_of_process_arguments(tmp_path: Path, name, field, command) -> None:
    runtime = _Runtime(tmp_path)
    text = "中文\n--headed ; $(literal text)"
    parameters = {field: text}
    if name != "computer_clipboard_set":
        parameters["ref"] = REF

    result = _tool(name, runtime, tmp_path).execute(**parameters)

    assert result.success
    assert len(runtime.calls) == 1
    actual_command, args, options = runtime.calls[0]
    assert actual_command == command
    assert "--stdin" in args
    assert text not in args
    assert options["text"] == text


def test_uncertain_action_is_returned_without_retry_or_fallback(tmp_path: Path) -> None:
    envelope = {
        "version": "2.6", "ok": False, "command": "click",
        "error": {
            "code": "TIMEOUT", "message": "Delivery may already have happened",
            "disposition": {"delivery": "delivery_uncertain", "retry": "unsafe"},
        },
    }
    runtime = _Runtime(tmp_path, error=NativeDesktopError(envelope))

    result = _tool("computer_click", runtime, tmp_path).execute(ref=REF)

    assert not result.success
    assert json.loads(result.error) == envelope
    assert result.data["computer_use"] == envelope
    assert len(runtime.calls) == 1


@pytest.mark.parametrize("physical", [False, True])
def test_ref_click_only_uses_headed_delivery_when_explicit(tmp_path: Path, physical: bool) -> None:
    runtime = _Runtime(tmp_path)

    execute(runtime, "computer_click", {"ref": REF, "physical": physical})

    command, args, options = runtime.calls[0]
    assert command == "click"
    assert REF in args
    assert options["headed"] is physical


@pytest.mark.parametrize('physical', [False, True])
def test_ref_typing_is_semantic_unless_physical_is_explicit(tmp_path, physical):
    runtime = _Runtime(tmp_path)
    arguments = {'ref': REF, 'text': '中文'}
    if physical:
        arguments['physical'] = True
    execute(runtime, 'computer_type_text', arguments)
    command, args, options = runtime.calls[0]
    assert command == 'type'
    assert options['headed'] is physical
    assert options['text'] == '中文'


def test_native_launch_arguments_cannot_be_silently_discarded_by_attach(tmp_path):
    runtime = _Runtime(tmp_path)
    execute(runtime, 'computer_launch_app', {'target': str(tmp_path / 'app.exe'), 'arguments': ['中文 file.txt']})
    command, args, _ = runtime.calls[0]
    assert command == 'launch'
    assert '--no-attach' in args
    assert '--arg=中文 file.txt' in args


def test_directory_launch_uses_shell_then_observes_without_relaunch(tmp_path, monkeypatch):
    from reverie.computer_use.service import OpenComputerUseService
    runtime = _Runtime(tmp_path)
    runtime._verify_binary = lambda: None
    runtime.check_cancel = lambda command: None
    delivered = []
    monkeypatch.setattr(OpenComputerUseService, '_shell_execute', lambda self, target, args: delivered.append((target, args)) or 33)
    result = execute(runtime, 'computer_launch_app', {'target': str(tmp_path)})
    assert delivered == [(str(tmp_path), '')]
    assert [c[0] for c in runtime.calls] == ['list-windows']
    assert result['data']['disposition']['delivery'] == 'delivered_unverified'
    assert result['data']['verification_scope'] == 'launch_request_only'


def test_double_click_requires_explicit_physical_input(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    with pytest.raises(NativeDesktopError):
        execute(runtime, "computer_click", {"ref": REF, "count": 2})

    assert runtime.calls == []


@pytest.mark.parametrize("name", ["computer_click", "computer_scroll", "computer_pointer"])
def test_mixed_ref_and_image_target_is_rejected_before_dispatch(tmp_path: Path, name: str) -> None:
    runtime = _Runtime(tmp_path)

    with pytest.raises(NativeDesktopError):
        execute(runtime, name, {"ref": REF, "image_id": "img-other", "x": 1, "y": 1, "direction": "down"})

    assert runtime.calls == []


def test_drag_rejects_a_mixed_source_endpoint_before_dispatch(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    with pytest.raises(NativeDesktopError):
        execute(runtime, "computer_drag", {"from_ref": REF, "from_x": 1, "to_ref": "@captured:e3"})

    assert runtime.calls == []


@pytest.mark.parametrize("gone", [False, True])
def test_selector_wait_stays_pinned_to_the_requested_window(tmp_path: Path, gone: bool) -> None:
    runtime = _Runtime(tmp_path)

    result = execute(runtime, "computer_wait", {"window_id": "w-10", "selector": "button:Saved", "gone": gone, "timeout_ms": 700})

    command, args, _ = runtime.calls[0]
    assert command == "snapshot"
    assert _flag(args, "window-id", "w-10")
    assert _flag(args, "wait-for-gone" if gone else "wait-for", "button:Saved")
    assert _flag(args, "wait-timeout", "700")
    assert "tree" not in result["data"]
    assert result["data"]["complete"] is True
    assert result["data"]["verification_scope"] == ("selector_absent" if gone else "matched_selector")


def test_window_title_wait_keeps_explicit_identity_with_duplicate_titles(tmp_path: Path, monkeypatch) -> None:
    runtime = _Runtime(tmp_path)
    other = {**runtime.window, "id": "w-other"}
    monkeypatch.setattr(runtime, "command", lambda *args, **kwargs: {
        "version": "2.6", "ok": True, "command": "list-windows", "data": [other, runtime.window],
    })

    result = execute(runtime, "computer_wait", {"window": "Editor", "window_id": "w-10"})

    assert result["data"]["window"]["id"] == "w-10"


def test_window_title_wait_returns_candidates_instead_of_first_match(tmp_path: Path, monkeypatch) -> None:
    runtime = _Runtime(tmp_path)
    other = {**runtime.window, "id": "w-other"}
    monkeypatch.setattr(runtime, "command", lambda *args, **kwargs: {
        "version": "2.6", "ok": True, "command": "list-windows", "data": [other, runtime.window],
    })

    with pytest.raises(NativeDesktopError) as error:
        execute(runtime, "computer_wait", {"window": "Editor"})

    assert error.value.envelope["error"]["code"] == "AMBIGUOUS_TARGET"
    assert len(error.value.envelope["error"]["details"]["candidates"]) == 2


def test_selector_wait_without_an_owner_is_rejected(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    with pytest.raises(NativeDesktopError):
        execute(runtime, "computer_wait", {"selector": "button:Saved"})

    assert runtime.calls == []


def test_window_scoped_text_wait_uses_a_supported_native_scope(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    execute(runtime, "computer_wait", {"window_id": "w-10", "text": "Saved", "timeout_ms": 700})

    command, args, _ = runtime.calls[-1]
    # Native wait's --window-id belongs to event waits, not text waits.
    assert command == "snapshot"
    assert _flag(args, "window-id", "w-10")
    assert _flag(args, "wait-for", ":Saved")


def test_legacy_index_from_another_runtime_namespace_is_not_reused(tmp_path: Path) -> None:
    original = _Runtime(tmp_path / "original")
    LegacyComputerUse(original).get_app_state("Editor")
    assert "0" in original.legacy["Editor"]["refs"]
    resumed = _Runtime(tmp_path / "resumed")

    with pytest.raises(NativeDesktopError):
        LegacyComputerUse(resumed).click("Editor", element_index="0")

    assert resumed.calls == []


def test_open_system_surface_uses_the_native_named_option(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    execute(runtime, "computer_open_system_surface", {"surface": "start-menu"})

    command, args, options = runtime.calls[0]
    assert command == "open-system-surface"
    assert _flag(args, "surface", "start-menu")
    assert options["headed"] is True


def test_close_app_uses_a_positional_app_without_force(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    execute(runtime, "computer_close_app", {"app": "Editor.exe"})

    command, args, _ = runtime.calls[-1]
    assert command == "close-app"
    assert "Editor.exe" in args
    assert not any(arg.startswith(("--app", "--window-id", "--force")) for arg in args)


def test_list_windows_does_not_forward_an_unsupported_window_id_flag(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    result = execute(runtime, "computer_list_windows", {"window_id": "w-10"})

    assert not any(arg.startswith("--window-id") for _, args, _ in runtime.calls for arg in args)
    assert [window["id"] for window in result["data"]] == ["w-10"]


def test_clipboard_image_path_is_resolved_against_the_project(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "image.png"
    Image.new("RGB", (8, 8), "red").save(path)
    runtime = _Runtime(tmp_path / "runtime")

    result = _tool("computer_clipboard_set", runtime, workspace).execute(image_path="image.png")

    assert result.success
    assert len(runtime.calls) == 1
    assert _flag(runtime.calls[0][1], "image", str(path.resolve()))


@pytest.mark.parametrize("kind", ["outside_workspace", "missing", "not_png"])
def test_clipboard_image_is_validated_before_native_dispatch(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime = _Runtime(tmp_path / "runtime")
    if kind == "outside_workspace":
        image_path = tmp_path / "outside.png"
        Image.new("RGB", (8, 8), "red").save(image_path)
    elif kind == "missing":
        image_path = workspace / "missing.png"
    else:
        image_path = workspace / "invalid.png"
        image_path.write_text("This is not a PNG.", encoding="utf-8")

    result = _tool("computer_clipboard_set", runtime, workspace).execute(image_path=str(image_path))

    assert not result.success
    assert runtime.calls == []
