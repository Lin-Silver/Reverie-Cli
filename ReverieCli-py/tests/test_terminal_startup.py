"""Terminal startup must not create an optional engine graphics context."""

import os
from pathlib import Path
import subprocess
import sys


def test_terminal_runtime_imports_do_not_initialize_pyglet_window():
    script = """
import sys
from reverie.cli.interface import ReverieInterface
from reverie.cli.commands import CommandHandler
from reverie.agent import ReverieAgent
from reverie.engine import runtime_capabilities
assert 'pyglet.window' not in sys.modules
assert 'pyglet.gl' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_engine_input_still_loads_native_default_bindings_on_use():
    from reverie.engine.input import InputAction, InputMap
    from pyglet.window import key, mouse

    inputs = InputMap()
    assert inputs.get_action(key.W) == InputAction.MOVE_UP.value
    assert inputs.get_action(key.ESCAPE) == InputAction.PAUSE.value
    assert inputs.get_action(mouse.LEFT, is_mouse=True) == InputAction.ATTACK.value
    assert inputs.get_action(mouse.RIGHT, is_mouse=True) == InputAction.INTERACT.value
