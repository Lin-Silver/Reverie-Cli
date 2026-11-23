"""Physical screenshot points must survive Windows thread DPI virtualization."""
from types import SimpleNamespace
from unittest.mock import Mock

import ctypes
import pytest

from reverie.computer_use.images import receives_point
from reverie.computer_use.runtime import NativeDesktopError


@pytest.fixture
def hit_test_user32(monkeypatch):
    state = {"context": -1, "scale": 1.25, "occluded": False}

    def set_context(value):
        previous = state["context"]
        state["context"] = value
        return previous

    def window_at(point):
        scale = 1 if state["context"] == -4 else state["scale"]
        x, y = point.x * scale, point.y * scale
        return 15 if not state["occluded"] and 1100 <= x < 1200 and 500 <= y < 600 else 20

    api = SimpleNamespace(
        WindowFromPoint=Mock(side_effect=window_at),
        GetAncestor=Mock(side_effect=lambda handle, _: 10 if handle == 15 else handle),
        SetThreadDpiAwarenessContext=Mock(side_effect=set_context),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    return api, state


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_physical_point_hits_its_window_at_each_system_scale(hit_test_user32, scale):
    _, state = hit_test_user32
    state["scale"] = scale

    assert receives_point("w-10", 1159, 544)
    assert state["context"] == -1


@pytest.mark.parametrize("original_context", [-2, -3, 0x100000001])
def test_hit_test_restores_the_callers_original_context(hit_test_user32, original_context):
    _, state = hit_test_user32
    state["context"] = original_context

    assert receives_point("w-10", 1159, 544)
    assert state["context"] == original_context


def test_actual_occlusion_is_still_rejected(hit_test_user32):
    _, state = hit_test_user32
    state["occluded"] = True

    assert not receives_point("w-10", 1159, 544)
    assert state["context"] == -1


def test_missing_window_is_rejected_and_context_restored(hit_test_user32):
    api, state = hit_test_user32
    api.WindowFromPoint.side_effect = lambda _: None

    assert not receives_point("w-10", 1159, 544)
    assert state["context"] == -1
    api.GetAncestor.assert_not_called()


def test_lookup_error_restores_context(hit_test_user32):
    api, state = hit_test_user32
    api.WindowFromPoint.side_effect = OSError("hit test failed")

    with pytest.raises(OSError, match="hit test failed"):
        receives_point("w-10", 1159, 544)
    assert state["context"] == -1


def test_unavailable_physical_context_refuses_input(hit_test_user32):
    api, state = hit_test_user32
    api.SetThreadDpiAwarenessContext.side_effect = lambda _: None

    with pytest.raises(NativeDesktopError) as error:
        receives_point("w-10", 1159, 544)
    assert error.value.envelope["error"]["code"] == "GEOMETRY_UNPROVEN"
    assert error.value.envelope["error"]["disposition"]["delivery"] == "not_delivered"
    assert state["context"] == -1
    api.WindowFromPoint.assert_not_called()


def test_failed_context_restore_refuses_input(hit_test_user32):
    api, _ = hit_test_user32
    api.SetThreadDpiAwarenessContext.side_effect = [-1, None]

    with pytest.raises(NativeDesktopError) as error:
        receives_point("w-10", 1159, 544)
    assert error.value.envelope["error"]["code"] == "GEOMETRY_UNPROVEN"
    assert error.value.envelope["error"]["disposition"]["delivery"] == "not_delivered"
