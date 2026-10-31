import pytest
from types import SimpleNamespace
from reverie.engine import create_project_skeleton
from reverie.engine.app import EngineRuntimeProfile, ReverieEngineApp, load_project_scene
from reverie.engine.input import InputManager
from reverie.engine.window import NativeWindow


def test_input_defaults_need_no_display_or_graphics_context():
    import os
    import subprocess
    import sys

    env = {key: value for key, value in os.environ.items() if key not in {"DISPLAY", "WAYLAND_DISPLAY", "PYGLET_HEADLESS"}}
    result = subprocess.run([sys.executable, "-c", """
import sys
from reverie.engine.input import InputMap
inputs = InputMap()
assert inputs.keyboard_map and inputs.mouse_map
assert 'pyglet.window' not in sys.modules
"""], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_input_defaults_match_native_pyglet_symbols_in_an_isolated_process():
    import os
    import subprocess
    import sys

    # Import the real window constants without changing the parent runtime's
    # renderer mode; only Linux uses Pyglet's EGL headless backend.
    result = subprocess.run([sys.executable, "-c", """
from reverie.engine.input import InputMap
from pyglet.window import key, mouse
inputs = InputMap()
for symbol, action in [(key.W, 'move_up'), (key.S, 'move_down'), (key.A, 'move_left'),
                       (key.D, 'move_right'), (key.SPACE, 'jump'), (key.E, 'interact'),
                       (key.ESCAPE, 'pause'), (key.UP, 'move_up'), (key.DOWN, 'move_down'),
                       (key.LEFT, 'move_left'), (key.RIGHT, 'move_right')]:
    assert inputs.get_action(symbol) == action
assert inputs.get_action(mouse.LEFT, is_mouse=True) == 'attack'
assert inputs.get_action(mouse.RIGHT, is_mouse=True) == 'interact'
"""], env={**os.environ, "PYGLET_HEADLESS": "true" if sys.platform == "linux" else "false"}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_audio_bus_setup_needs_no_display_or_playback_device(tmp_path):
    import os
    import subprocess
    import sys

    env = {key: value for key, value in os.environ.items() if key not in {"DISPLAY", "WAYLAND_DISPLAY", "PYGLET_HEADLESS"}}
    result = subprocess.run([sys.executable, "-c", """
import sys
from pathlib import Path
from reverie.engine.audio import AudioManager
audio = AudioManager(Path(sys.argv[1]))
audio.create_bus('Dialogue', parent='Master')
assert audio.get_bus('Dialogue') is not None
assert not audio.backend_status()['operational']
assert not audio.load_stream('missing', 'missing.wav')
assert 'pyglet.media' not in sys.modules
assert 'pyglet.window' not in sys.modules
""", str(tmp_path)], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_headless_runtime_cleans_up_renderer_after_observer_failure(tmp_path):
    project=tmp_path / "game"
    create_project_skeleton(project, project_name="Lifecycle", dimension="2D", genre="platformer")
    tree, _, config=load_project_scene(project)
    app=ReverieEngineApp(tree, EngineRuntimeProfile(headless=True), config=config)
    assert tree.input_manager is app.input_manager
    assert app.window is None
    def fail(*args):
        raise RuntimeError("observer failure")
    with pytest.raises(RuntimeError, match="observer failure"):
        app.run_with_observer(frames=2,frame_observer=fail)
    assert app.renderer.server._initialized is False


def test_native_pump_exposes_mouse_delta_in_the_current_frame():
    inputs=InputManager()
    window=NativeWindow.__new__(NativeWindow)
    window.inputs=inputs
    window.closed=False
    window.window=SimpleNamespace(switch_to=lambda:None,dispatch_events=lambda:inputs.on_mouse_motion(30,20))
    inputs.update()
    assert window.pump()
    assert inputs.mouse_delta==(30,20)
    inputs.update()
    window.pump()
    assert inputs.mouse_delta==(0,0)
