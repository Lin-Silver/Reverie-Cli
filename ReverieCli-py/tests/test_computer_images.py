"""Screenshot coordinates must remain bound to the image the model observed."""
from __future__ import annotations

import base64
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from reverie.computer_use.images import capture, point
from reverie.computer_use.runtime import NativeDesktopError


@pytest.fixture(autouse=True)
def isolated_window_hit_test(monkeypatch):
    # All window IDs in these tests are fixtures, never actual desktop handles.
    monkeypatch.setattr("reverie.computer_use.images.receives_point", lambda *args: True)


class _Runtime:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.images = {}
        self.window = {
            "id": "w-10", "pid": 42, "process_instance": "process-original",
            "title": "Coordinate fixture", "is_focused": True,
            "bounds": {"x": 100, "y": 200, "width": 400, "height": 200},
        }
        self.windows = [self.window]
        self.commands = []
        image = Image.new("RGB", (400, 200), "#3572aa")
        encoded = BytesIO()
        image.save(encoded, format="PNG")
        self.png = base64.b64encode(encoded.getvalue()).decode("ascii")

    def command(self, command: str, args=None, **kwargs) -> dict:
        self.commands.append(command)
        if command == "list-windows":
            data = deepcopy(self.windows)
        elif command == "screenshot":
            data = {
                "data": self.png, "format": "png", "width": 400,
                "height": 200, "scale_factor": 1,
            }
        else:
            raise AssertionError(f"Unexpected desktop operation: {command}")
        return {"version": "2.6", "ok": True, "command": command, "data": data}


def _capture(runtime: _Runtime, **parameters) -> dict:
    return capture(runtime, {"window_id": "w-10", **parameters})["data"]


def test_capture_saves_a_png_and_returns_a_coordinate_binding(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    data = _capture(runtime)

    assert data["image_id"] in runtime.images
    assert (data["width"], data["height"]) == (400, 200)
    saved = Path(data["path"])
    assert saved.is_file()
    assert saved.resolve().is_relative_to(tmp_path.resolve())
    with Image.open(saved) as image:
        assert image.format == "PNG"
        assert image.size == (400, 200)
    assert point(runtime, data["image_id"], 15, 25, vision=True) == (115, 225)


def test_cropped_and_resized_coordinates_map_back_to_the_original_screen(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)

    data = _capture(
        runtime, region={"x": 50, "y": 20, "width": 200, "height": 100}, max_dimension=100,
    )

    assert (data["width"], data["height"]) == (100, 50)
    with Image.open(data["path"]) as image:
        assert image.size == (100, 50)
    assert point(runtime, data["image_id"], 25, 10, vision=True) == (200, 240)


def test_text_model_cannot_act_on_screenshot_coordinates(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)

    with pytest.raises(NativeDesktopError):
        point(runtime, data["image_id"], 10, 10, vision=False)


def test_occluding_window_prevents_coordinate_delivery(tmp_path: Path, monkeypatch) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)
    monkeypatch.setattr("reverie.computer_use.images.receives_point", lambda *args: False)

    with pytest.raises(NativeDesktopError) as error:
        point(runtime, data["image_id"], 10, 10, vision=True)

    assert error.value.envelope["error"]["code"] == "TARGET_OCCLUDED"
    assert error.value.envelope["error"]["disposition"]["delivery"] == "not_delivered"


def test_unknown_image_cannot_supply_coordinates(tmp_path: Path) -> None:
    with pytest.raises(NativeDesktopError):
        point(_Runtime(tmp_path), "image-from-another-session", 10, 10, vision=True)


def test_expired_image_requires_a_new_observation(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)
    runtime.images[data["image_id"]]["captured_at"] -= 3600

    with pytest.raises(NativeDesktopError):
        point(runtime, data["image_id"], 10, 10, vision=True)


@pytest.mark.parametrize("field,changed", [("x", 110), ("y", 210), ("width", 500), ("height", 250)])
def test_window_geometry_change_invalidates_image(tmp_path: Path, field: str, changed: int) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)
    runtime.window["bounds"][field] = changed

    with pytest.raises(NativeDesktopError):
        point(runtime, data["image_id"], 10, 10, vision=True)


@pytest.mark.parametrize("field,changed", [("pid", 43), ("process_instance", "process-restarted")])
def test_reused_window_handle_does_not_retarget_image(tmp_path: Path, field: str, changed) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)
    runtime.window[field] = changed

    with pytest.raises(NativeDesktopError):
        point(runtime, data["image_id"], 10, 10, vision=True)


def test_closed_window_invalidates_image(tmp_path: Path) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)
    runtime.windows = []

    with pytest.raises(NativeDesktopError):
        point(runtime, data["image_id"], 10, 10, vision=True)


@pytest.mark.parametrize("x,y", [(-1, 0), (0, -1), (400, 0), (0, 200)])
def test_pixel_outside_observed_image_is_rejected(tmp_path: Path, x: float, y: float) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)

    with pytest.raises(NativeDesktopError):
        point(runtime, data["image_id"], x, y, vision=True)


@pytest.mark.parametrize("x,y", [(float("nan"), 0), (float("inf"), 0), (0, float("-inf"))])
def test_nonfinite_coordinates_are_rejected(tmp_path: Path, x: float, y: float) -> None:
    runtime = _Runtime(tmp_path)
    data = _capture(runtime)

    with pytest.raises(NativeDesktopError):
        point(runtime, data["image_id"], x, y, vision=True)


def test_visible_frame_origin_excludes_invisible_resize_borders(tmp_path, monkeypatch):
    runtime = _Runtime(tmp_path)
    runtime.window['bounds'] = {'x': 93, 'y': 200, 'width': 414, 'height': 207}
    visible = {'x': 100, 'y': 200, 'width': 400, 'height': 200}
    monkeypatch.setattr('reverie.computer_use.images.frame_bounds', lambda _: visible)
    data = _capture(runtime)
    assert data['capture_bounds'] == visible
    assert point(runtime, data['image_id'], 0, 0) == (100, 200)
    assert point(runtime, data['image_id'], 399.9, 199.9) == (499, 399)


def test_unproven_capture_geometry_is_viewable_but_cannot_control_pointer(tmp_path, monkeypatch):
    runtime = _Runtime(tmp_path)
    runtime.window['bounds']['width'] = 500
    monkeypatch.setattr('reverie.computer_use.images.frame_bounds', lambda _: None)
    data = _capture(runtime)
    assert Path(data['path']).is_file()
    assert data['coordinate_available'] is False
    with pytest.raises(NativeDesktopError) as error:
        point(runtime, data['image_id'], 0, 0)
    assert error.value.envelope['error']['code'] == 'GEOMETRY_UNPROVEN'
