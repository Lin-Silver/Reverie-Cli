"""Input system for Reverie Engine Lite - keyboard, mouse, and gamepad support."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Set, Optional, Tuple

try:
    import pyglet
    from pyglet.window import key, mouse
except ImportError:
    pyglet = None
    key = None
    mouse = None


class InputAction(Enum):
    """Common input actions."""
    MOVE_UP = "move_up"
    MOVE_DOWN = "move_down"
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    JUMP = "jump"
    ATTACK = "attack"
    INTERACT = "interact"
    PAUSE = "pause"
    CANCEL = "cancel"


@dataclass
class InputMap:
    """Maps keys/buttons to actions."""
    keyboard_map: Dict[int, str] = field(default_factory=dict)
    mouse_map: Dict[int, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.keyboard_map and key:
            # Default keyboard mappings
            self.keyboard_map = {
                key.W: InputAction.MOVE_UP.value,
                key.S: InputAction.MOVE_DOWN.value,
                key.A: InputAction.MOVE_LEFT.value,
                key.D: InputAction.MOVE_RIGHT.value,
                key.SPACE: InputAction.JUMP.value,
                key.E: InputAction.INTERACT.value,
                key.ESCAPE: InputAction.PAUSE.value,
                key.UP: InputAction.MOVE_UP.value,
                key.DOWN: InputAction.MOVE_DOWN.value,
                key.LEFT: InputAction.MOVE_LEFT.value,
                key.RIGHT: InputAction.MOVE_RIGHT.value,
            }
        
        if not self.mouse_map and mouse:
            # Default mouse mappings
            self.mouse_map = {
                mouse.LEFT: InputAction.ATTACK.value,
                mouse.RIGHT: InputAction.INTERACT.value,
            }
    
    def get_action(self, key_code: int, is_mouse: bool = False) -> Optional[str]:
        """Get action name for a key/button."""
        if is_mouse:
            return self.mouse_map.get(key_code)
        return self.keyboard_map.get(key_code)
    
    def bind_key(self, key_code: int, action: str) -> None:
        """Bind a keyboard key to an action."""
        self.keyboard_map[key_code] = action
    
    def bind_mouse(self, button: int, action: str) -> None:
        """Bind a mouse button to an action."""
        self.mouse_map[button] = action


class InputManager:
    """Manages input state and events."""
    
    def __init__(self):
        self.input_map = InputMap()
        self.keys_pressed: Set[int] = set()
        self.keys_just_pressed: Set[int] = set()
        self.keys_just_released: Set[int] = set()
        self.mouse_buttons_pressed: Set[int] = set()
        self.mouse_buttons_just_pressed: Set[int] = set()
        self.mouse_buttons_just_released: Set[int] = set()
        self.mouse_position: Tuple[float, float] = (0.0, 0.0)
        self.mouse_delta: Tuple[float, float] = (0.0, 0.0)
        self.mouse_wheel_delta: float = 0.0
        self._last_mouse_position: Tuple[float, float] = (0.0, 0.0)
    
    def update(self) -> None:
        """Update input state - call once per frame."""
        self.keys_just_pressed.clear()
        self.keys_just_released.clear()
        self.mouse_buttons_just_pressed.clear()
        self.mouse_buttons_just_released.clear()
        
        # Update mouse delta
        self.mouse_delta = (
            self.mouse_position[0] - self._last_mouse_position[0],
            self.mouse_position[1] - self._last_mouse_position[1]
        )
        self._last_mouse_position = self.mouse_position
        self.mouse_wheel_delta = 0.0
    
    def on_key_press(self, symbol: int) -> None:
        """Handle key press event."""
        if symbol not in self.keys_pressed:
            self.keys_just_pressed.add(symbol)
        self.keys_pressed.add(symbol)
    
    def on_key_release(self, symbol: int) -> None:
        """Handle key release event."""
        if symbol in self.keys_pressed:
            self.keys_just_released.add(symbol)
            self.keys_pressed.remove(symbol)
    
    def on_mouse_press(self, button: int, x: float, y: float) -> None:
        """Handle mouse button press event."""
        if button not in self.mouse_buttons_pressed:
            self.mouse_buttons_just_pressed.add(button)
        self.mouse_buttons_pressed.add(button)
        self.mouse_position = (x, y)
    
    def on_mouse_release(self, button: int, x: float, y: float) -> None:
        """Handle mouse button release event."""
        if button in self.mouse_buttons_pressed:
            self.mouse_buttons_just_released.add(button)
            self.mouse_buttons_pressed.remove(button)
        self.mouse_position = (x, y)
    
    def on_mouse_motion(self, x: float, y: float) -> None:
        """Handle mouse motion event."""
        self.mouse_position = (x, y)
    
    def on_mouse_scroll(self, scroll_y: float) -> None:
        """Handle mouse wheel scroll event."""
        self.mouse_wheel_delta = scroll_y
    
    def is_key_pressed(self, key_code: int) -> bool:
        """Check if a key is currently pressed."""
        return key_code in self.keys_pressed
    
    def is_key_just_pressed(self, key_code: int) -> bool:
        """Check if a key was just pressed this frame."""
        return key_code in self.keys_just_pressed
    
    def is_key_just_released(self, key_code: int) -> bool:
        """Check if a key was just released this frame."""
        return key_code in self.keys_just_released
    
    def is_action_pressed(self, action: str) -> bool:
        """Check if an action is currently active."""
        for key_code in self.keys_pressed:
            if self.input_map.get_action(key_code) == action:
                return True
        for button in self.mouse_buttons_pressed:
            if self.input_map.get_action(button, is_mouse=True) == action:
                return True
        return False
    
    def is_action_just_pressed(self, action: str) -> bool:
        """Check if an action was just activated this frame."""
        for key_code in self.keys_just_pressed:
            if self.input_map.get_action(key_code) == action:
                return True
        for button in self.mouse_buttons_just_pressed:
            if self.input_map.get_action(button, is_mouse=True) == action:
                return True
        return False
    
    def is_action_just_released(self, action: str) -> bool:
        """Check if an action was just deactivated this frame."""
        for key_code in self.keys_just_released:
            if self.input_map.get_action(key_code) == action:
                return True
        for button in self.mouse_buttons_just_released:
            if self.input_map.get_action(button, is_mouse=True) == action:
                return True
        return False
    
    def get_axis(self, negative_action: str, positive_action: str) -> float:
        """Get axis value (-1.0 to 1.0) from two actions."""
        value = 0.0
        if self.is_action_pressed(negative_action):
            value -= 1.0
        if self.is_action_pressed(positive_action):
            value += 1.0
        return value
    
    def get_vector(self, left: str, right: str, up: str, down: str) -> Tuple[float, float]:
        """Get 2D vector from four directional actions."""
        x = self.get_axis(left, right)
        y = self.get_axis(down, up)
        return (x, y)
