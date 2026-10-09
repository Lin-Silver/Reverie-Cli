import pytest
from types import SimpleNamespace
from reverie.engine import create_project_skeleton
from reverie.engine.app import EngineRuntimeProfile, ReverieEngineApp, load_project_scene
from reverie.engine.input import InputManager
from reverie.engine.window import NativeWindow


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
