"""
Computer Controller tool.

Provides a single, mode-specific control surface for desktop observation and
interaction on Windows.
"""

from __future__ import annotations

import base64
import ctypes
import json
import subprocess
import time
from pathlib import Path
from ctypes import wintypes
from typing import Any, Dict, List, Optional, Sequence

from .base import BaseTool, ToolResult
from ..config import get_project_data_dir


user32 = ctypes.windll.user32

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_UP = 0x26
VK_DOWN = 0x28
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_F_KEYS = {f"f{index}": 0x6F + index for index in range(1, 13)}
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTUNION),
    ]


try:
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
except Exception:
    pass


class ComputerControlTool(BaseTool):
    aliases = ("computer_control", "desktop_control")
    search_hint = "observe and operate the windows desktop"
    tool_category = "desktop"
    tool_tags = ("desktop", "screen", "window", "mouse", "keyboard", "observe", "ui")
    """Observe and control the local computer from a single tool."""

    name = "computer_control"
    description = (
        "Observe and control the Windows desktop in Computer Controller mode. "
        "Supports screenshot observation, mouse actions, native keyboard text entry, hotkeys, drag, scroll, and wait steps."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "observe",
                    "active_window",
                    "observe_window",
                    "screen_info",
                    "cursor",
                    "move_mouse",
                    "click",
                    "double_click",
                    "right_click",
                    "drag",
                    "scroll",
                    "type_text",
                    "key_press",
                    "hotkey",
                    "wait",
                ],
                "description": "Desktop action to perform.",
            },
            "x": {"type": "integer", "description": "Target X coordinate."},
            "y": {"type": "integer", "description": "Target Y coordinate."},
            "to_x": {"type": "integer", "description": "Drag destination X coordinate."},
            "to_y": {"type": "integer", "description": "Drag destination Y coordinate."},
            "width": {"type": "integer", "description": "Observation region width."},
            "height": {"type": "integer", "description": "Observation region height."},
            "padding": {"type": "integer", "description": "Extra pixels added around a region or active window capture."},
            "grid_cols": {"type": "integer", "description": "Optional observation grid columns for visual targeting."},
            "grid_rows": {"type": "integer", "description": "Optional observation grid rows for visual targeting."},
            "highlight_cursor": {"type": "boolean", "description": "Highlight the current cursor when it falls inside the captured region."},
            "button": {
                "type": "string",
                "description": "Mouse button for click/drag actions.",
            },
            "text": {"type": "string", "description": "Text to type into the active UI."},
            "key": {"type": "string", "description": "Single key to press."},
            "keys": {
                "type": "array",
                "description": "Key chord list for hotkey actions, such as ['ctrl', 's'].",
                "items": {"type": "string"},
            },
            "delta": {"type": "integer", "description": "Scroll delta, in wheel units of 120."},
            "duration_ms": {"type": "integer", "description": "Wait or drag duration in milliseconds."},
            "steps": {"type": "integer", "description": "Interpolation steps for drag movement."},
            "press_enter": {"type": "boolean", "description": "Press Enter after typing text."},
            "observation_name": {"type": "string", "description": "Optional file stem for screenshots."},
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = self.get_project_root()
        self.output_dir = get_project_data_dir(self.project_root) / "computer_control" / "observations"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_execution_message(self, action: str, **kwargs) -> str:
        action_name = str(action or "observe").strip().lower()
        mapping = {
            "observe": "Capturing desktop observation",
            "active_window": "Inspecting the active window",
            "observe_window": "Capturing the active window",
            "screen_info": "Inspecting desktop dimensions",
            "cursor": "Reading cursor position",
            "move_mouse": "Moving mouse cursor",
            "click": "Clicking on desktop target",
            "double_click": "Double-clicking on desktop target",
            "right_click": "Right-clicking on desktop target",
            "drag": "Dragging across desktop target",
            "scroll": "Scrolling active desktop surface",
            "type_text": "Typing text into the active window",
            "key_press": "Pressing a keyboard key",
            "hotkey": "Sending a keyboard shortcut",
            "wait": "Waiting for UI to settle",
        }
        return mapping.get(action_name, "Controlling the desktop")

    def execute(self, action: str, **kwargs) -> ToolResult:
        action_name = str(action or "").strip().lower()
        try:
            if action_name == "observe":
                return self._observe(**kwargs)
            if action_name == "active_window":
                return self._active_window_details()
            if action_name == "observe_window":
                return self._observe_window(**kwargs)
            if action_name == "screen_info":
                return self._screen_info()
            if action_name == "cursor":
                return self._cursor_info()
            if action_name == "move_mouse":
                return self._move_mouse(kwargs.get("x"), kwargs.get("y"))
            if action_name == "click":
                return self._click(kwargs.get("x"), kwargs.get("y"), button=str(kwargs.get("button", "left") or "left"))
            if action_name == "double_click":
                return self._double_click(kwargs.get("x"), kwargs.get("y"))
            if action_name == "right_click":
                return self._click(kwargs.get("x"), kwargs.get("y"), button="right")
            if action_name == "drag":
                return self._drag(
                    kwargs.get("x"),
                    kwargs.get("y"),
                    kwargs.get("to_x"),
                    kwargs.get("to_y"),
                    duration_ms=int(kwargs.get("duration_ms", 600) or 600),
                    steps=int(kwargs.get("steps", 16) or 16),
                )
            if action_name == "scroll":
                return self._scroll(int(kwargs.get("delta", 120) or 120))
            if action_name == "type_text":
                return self._type_text(str(kwargs.get("text", "") or ""), press_enter=bool(kwargs.get("press_enter", False)))
            if action_name == "key_press":
                return self._key_press(str(kwargs.get("key", "") or ""))
            if action_name == "hotkey":
                return self._hotkey(kwargs.get("keys") or [])
            if action_name == "wait":
                return self._wait(int(kwargs.get("duration_ms", 1000) or 1000))
            return ToolResult.fail(f"Unknown computer_control action: {action_name}")
        except Exception as exc:
            return ToolResult.fail(f"Computer control failed: {exc}")

    def _screen_size(self) -> Dict[str, int]:
        return {
            "width": int(user32.GetSystemMetrics(0)),
            "height": int(user32.GetSystemMetrics(1)),
        }

    def _cursor_position(self) -> Dict[str, int]:
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        return {"x": int(point.x), "y": int(point.y)}

    def _active_window_info(self) -> Dict[str, Any]:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            raise RuntimeError("No active window detected")

        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("Failed to read active window bounds")

        title_length = int(user32.GetWindowTextLengthW(hwnd))
        title_buffer = ctypes.create_unicode_buffer(max(1, title_length + 1))
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))

        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))

        bounds = {
            "x": int(rect.left),
            "y": int(rect.top),
            "width": max(1, int(rect.right - rect.left)),
            "height": max(1, int(rect.bottom - rect.top)),
        }
        return {
            "handle": int(hwnd),
            "title": str(title_buffer.value or "").strip(),
            "process_id": int(process_id.value),
            "bounds": bounds,
        }

    def _ensure_int(self, value: Any, name: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} is required and must be an integer")

    def _move_mouse(self, x: Any, y: Any) -> ToolResult:
        target_x = self._ensure_int(x, "x")
        target_y = self._ensure_int(y, "y")
        user32.SetCursorPos(target_x, target_y)
        cursor = self._cursor_position()
        return ToolResult.ok(
            f"Mouse moved to ({cursor['x']}, {cursor['y']}).",
            data={"cursor": cursor, "computer_control_action": "move_mouse"},
        )

    def _mouse_button_flags(self, button: str) -> tuple[int, int]:
        lowered = str(button or "left").strip().lower()
        if lowered == "right":
            return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    def _click(self, x: Any = None, y: Any = None, button: str = "left") -> ToolResult:
        if x is not None and y is not None:
            move_result = self._move_mouse(x, y)
            if not move_result.success:
                return move_result
        down_flag, up_flag = self._mouse_button_flags(button)
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(up_flag, 0, 0, 0, 0)
        cursor = self._cursor_position()
        return ToolResult.ok(
            f"{button.capitalize()} click completed at ({cursor['x']}, {cursor['y']}).",
            data={"cursor": cursor, "computer_control_action": "click", "button": button},
        )

    def _double_click(self, x: Any = None, y: Any = None) -> ToolResult:
        first = self._click(x, y, button="left")
        if not first.success:
            return first
        time.sleep(0.08)
        second = self._click(None, None, button="left")
        if not second.success:
            return second
        cursor = self._cursor_position()
        return ToolResult.ok(
            f"Double click completed at ({cursor['x']}, {cursor['y']}).",
            data={"cursor": cursor, "computer_control_action": "double_click"},
        )

    def _drag(
        self,
        from_x: Any,
        from_y: Any,
        to_x: Any,
        to_y: Any,
        duration_ms: int = 600,
        steps: int = 16,
    ) -> ToolResult:
        start_x = self._ensure_int(from_x, "x")
        start_y = self._ensure_int(from_y, "y")
        end_x = self._ensure_int(to_x, "to_x")
        end_y = self._ensure_int(to_y, "to_y")
        steps = max(2, int(steps or 16))
        total_seconds = max(0.05, float(duration_ms or 600) / 1000.0)

        user32.SetCursorPos(start_x, start_y)
        time.sleep(0.04)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

        for index in range(1, steps + 1):
            progress = index / steps
            cur_x = int(start_x + (end_x - start_x) * progress)
            cur_y = int(start_y + (end_y - start_y) * progress)
            user32.SetCursorPos(cur_x, cur_y)
            time.sleep(total_seconds / steps)

        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        cursor = self._cursor_position()
        return ToolResult.ok(
            f"Dragged from ({start_x}, {start_y}) to ({cursor['x']}, {cursor['y']}).",
            data={
                "cursor": cursor,
                "computer_control_action": "drag",
                "from": {"x": start_x, "y": start_y},
                "to": {"x": end_x, "y": end_y},
            },
        )

    def _scroll(self, delta: int) -> ToolResult:
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(delta), 0)
        return ToolResult.ok(
            f"Scroll event sent with delta {int(delta)}.",
            data={"computer_control_action": "scroll", "delta": int(delta)},
        )

    def _wait(self, duration_ms: int) -> ToolResult:
        duration_ms = max(0, int(duration_ms))
        time.sleep(duration_ms / 1000.0)
        return ToolResult.ok(
            f"Waited for {duration_ms} ms.",
            data={"computer_control_action": "wait", "duration_ms": duration_ms},
        )

    def _screen_info(self) -> ToolResult:
        screen = self._screen_size()
        cursor = self._cursor_position()
        return ToolResult.ok(
            f"Desktop size: {screen['width']} x {screen['height']}\nCursor: ({cursor['x']}, {cursor['y']})",
            data={"screen": screen, "cursor": cursor, "computer_control_action": "screen_info"},
        )

    def _active_window_details(self) -> ToolResult:
        window = self._active_window_info()
        bounds = window["bounds"]
        title = window["title"] or "(untitled window)"
        return ToolResult.ok(
            "\n".join(
                [
                    f"Active window: {title}",
                    f"Bounds: ({bounds['x']}, {bounds['y']}, {bounds['width']}, {bounds['height']})",
                    f"Process ID: {window['process_id']}",
                ]
            ),
            data={
                "computer_control_action": "active_window",
                "window": window,
            },
        )

    def _cursor_info(self) -> ToolResult:
        cursor = self._cursor_position()
        return ToolResult.ok(
            f"Cursor position: ({cursor['x']}, {cursor['y']})",
            data={"cursor": cursor, "computer_control_action": "cursor"},
        )

    def _ps_quote(self, value: str) -> str:
        return "'" + str(value or "").replace("'", "''") + "'"

    def _run_powershell(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def _set_clipboard_text(self, text: str) -> None:
        script = f"Set-Clipboard -Value {self._ps_quote(text)}"
        result = self._run_powershell(script)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(stderr or "Set-Clipboard failed")

    def _build_keyboard_input(self, *, vk_code: int = 0, scan_code: int = 0, flags: int = 0) -> INPUT:
        input_item = INPUT()
        input_item.type = INPUT_KEYBOARD
        input_item.ki = KEYBDINPUT(
            wVk=int(vk_code),
            wScan=int(scan_code),
            dwFlags=int(flags),
            time=0,
            dwExtraInfo=0,
        )
        return input_item

    def _send_input_events(self, inputs: Sequence[INPUT]) -> None:
        if not inputs:
            return

        input_array = (INPUT * len(inputs))(*inputs)
        sent = int(user32.SendInput(len(inputs), input_array, ctypes.sizeof(INPUT)))
        if sent != len(inputs):
            raise RuntimeError(f"SendInput injected {sent}/{len(inputs)} events")

    def _send_unicode_text(self, text: str) -> None:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        inputs: List[INPUT] = []

        for char in normalized:
            if char == "\n":
                inputs.append(self._build_keyboard_input(vk_code=VK_RETURN))
                inputs.append(self._build_keyboard_input(vk_code=VK_RETURN, flags=KEYEVENTF_KEYUP))
                continue
            if char == "\t":
                inputs.append(self._build_keyboard_input(vk_code=VK_TAB))
                inputs.append(self._build_keyboard_input(vk_code=VK_TAB, flags=KEYEVENTF_KEYUP))
                continue

            encoded = char.encode("utf-16-le")
            for index in range(0, len(encoded), 2):
                code_unit = int.from_bytes(encoded[index:index + 2], "little")
                inputs.append(self._build_keyboard_input(scan_code=code_unit, flags=KEYEVENTF_UNICODE))
                inputs.append(self._build_keyboard_input(scan_code=code_unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))

        self._send_input_events(inputs)

    def _normalize_key(self, key: str) -> int:
        lowered = str(key or "").strip().lower()
        aliases = {
            "ctrl": VK_CONTROL,
            "control": VK_CONTROL,
            "alt": VK_MENU,
            "shift": VK_SHIFT,
            "enter": VK_RETURN,
            "return": VK_RETURN,
            "tab": VK_TAB,
            "esc": VK_ESCAPE,
            "escape": VK_ESCAPE,
            "space": VK_SPACE,
            "backspace": VK_BACK,
            "delete": VK_DELETE,
            "up": VK_UP,
            "down": VK_DOWN,
            "left": VK_LEFT,
            "right": VK_RIGHT,
        }
        if lowered in aliases:
            return aliases[lowered]
        if lowered in VK_F_KEYS:
            return VK_F_KEYS[lowered]
        if len(lowered) == 1:
            return ord(lowered.upper())
        raise ValueError(f"Unsupported key: {key}")

    def _press_vk(self, vk_code: int) -> None:
        user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(vk_code, 0, 0x0002, 0)

    def _key_press(self, key: str) -> ToolResult:
        vk_code = self._normalize_key(key)
        self._press_vk(vk_code)
        return ToolResult.ok(
            f"Pressed key: {key}",
            data={"computer_control_action": "key_press", "key": key},
        )

    def _hotkey(self, keys: Sequence[str]) -> ToolResult:
        key_list = [str(item or "").strip() for item in keys if str(item or "").strip()]
        if not key_list:
            return ToolResult.fail("At least one key is required for hotkey")

        vk_codes = [self._normalize_key(item) for item in key_list]
        for vk_code in vk_codes[:-1]:
            user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.02)
        self._press_vk(vk_codes[-1])
        for vk_code in reversed(vk_codes[:-1]):
            user32.keybd_event(vk_code, 0, 0x0002, 0)
            time.sleep(0.01)

        return ToolResult.ok(
            f"Pressed hotkey: {' + '.join(key_list)}",
            data={"computer_control_action": "hotkey", "keys": key_list},
        )

    def _type_text(self, text: str, press_enter: bool = False) -> ToolResult:
        content = str(text or "")
        if not content:
            return ToolResult.fail("Text is required for type_text")

        used_native_keyboard = False
        fallback_reason = ""
        if "\n" not in content and "\r" not in content and "\t" not in content:
            try:
                self._send_unicode_text(content)
                used_native_keyboard = True
            except Exception as exc:
                fallback_reason = str(exc)

        if not used_native_keyboard:
            self._set_clipboard_text(content)
            self._hotkey(["ctrl", "v"])

        if press_enter:
            self._key_press("enter")
        return ToolResult.ok(
            f"Typed {len(content)} characters via {'native keyboard input' if used_native_keyboard else 'clipboard paste'}."
            + (" Pressed Enter afterwards." if press_enter else ""),
            data={
                "computer_control_action": "type_text",
                "characters": len(content),
                "press_enter": bool(press_enter),
                "input_method": "keyboard" if used_native_keyboard else "clipboard",
                **({"fallback_reason": fallback_reason} if fallback_reason and not used_native_keyboard else {}),
            },
        )

    def _capture_screenshot(
        self,
        path: Path,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        grid_cols: int = 0,
        grid_rows: int = 0,
        highlight_cursor: bool = False,
    ) -> None:
        region_script = ""
        if None not in (x, y, width, height):
            region_script = (
                f"$bounds = New-Object System.Drawing.Rectangle({int(x)}, {int(y)}, {int(width)}, {int(height)});"
            )
        else:
            region_script = "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"

        overlay_script = ""
        if int(grid_cols or 0) > 0 and int(grid_rows or 0) > 0:
            overlay_script += (
                f"$gridCols = {int(grid_cols)};"
                f"$gridRows = {int(grid_rows)};"
                "$gridPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(180, 0, 174, 255), 1);"
                "$gridFont = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold);"
                "$gridBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(235, 255, 255, 255));"
                "$gridShadow = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(185, 20, 24, 32));"
                "for($col = 1; $col -lt $gridCols; $col++){"
                "$lineX = [int]([Math]::Round(($bitmap.Width * $col) / $gridCols));"
                "$graphics.DrawLine($gridPen, $lineX, 0, $lineX, $bitmap.Height)"
                "}"
                "for($row = 1; $row -lt $gridRows; $row++){"
                "$lineY = [int]([Math]::Round(($bitmap.Height * $row) / $gridRows));"
                "$graphics.DrawLine($gridPen, 0, $lineY, $bitmap.Width, $lineY)"
                "}"
                "for($col = 0; $col -lt $gridCols; $col++){"
                "for($row = 0; $row -lt $gridRows; $row++){"
                "$label = ('{0},{1}' -f ($col + 1), ($row + 1));"
                "$labelX = [int](($bitmap.Width * $col) / $gridCols) + 6;"
                "$labelY = [int](($bitmap.Height * $row) / $gridRows) + 6;"
                "$graphics.DrawString($label, $gridFont, $gridShadow, $labelX + 1, $labelY + 1);"
                "$graphics.DrawString($label, $gridFont, $gridBrush, $labelX, $labelY)"
                "}"
                "}"
                "$gridPen.Dispose();"
                "$gridFont.Dispose();"
                "$gridBrush.Dispose();"
                "$gridShadow.Dispose();"
            )

        cursor = self._cursor_position()
        local_x = None
        local_y = None
        if highlight_cursor:
            if None not in (x, y, width, height):
                if int(x) <= cursor["x"] < int(x) + int(width) and int(y) <= cursor["y"] < int(y) + int(height):
                    local_x = int(cursor["x"] - int(x))
                    local_y = int(cursor["y"] - int(y))
            else:
                local_x = int(cursor["x"])
                local_y = int(cursor["y"])

        if local_x is not None and local_y is not None:
            overlay_script += (
                f"$cursorX = {local_x};"
                f"$cursorY = {local_y};"
                "$cursorPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(230, 255, 96, 96), 2);"
                "$graphics.DrawLine($cursorPen, [Math]::Max(0, $cursorX - 18), $cursorY, [Math]::Min($bitmap.Width - 1, $cursorX + 18), $cursorY);"
                "$graphics.DrawLine($cursorPen, $cursorX, [Math]::Max(0, $cursorY - 18), $cursorX, [Math]::Min($bitmap.Height - 1, $cursorY + 18));"
                "$graphics.DrawEllipse($cursorPen, [Math]::Max(0, $cursorX - 8), [Math]::Max(0, $cursorY - 8), 16, 16);"
                "$cursorPen.Dispose();"
            )

        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            f"{region_script}"
            "$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height);"
            "$graphics = [System.Drawing.Graphics]::FromImage($bitmap);"
            "$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size);"
            f"{overlay_script}"
            f"$bitmap.Save({self._ps_quote(str(path))}, [System.Drawing.Imaging.ImageFormat]::Png);"
            "$graphics.Dispose();"
            "$bitmap.Dispose();"
        )
        result = self._run_powershell(script)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(stderr or "screenshot capture failed")

    def _normalize_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        padding: int = 0,
    ) -> Dict[str, int]:
        screen = self._screen_size()
        left = max(0, int(x) - max(0, int(padding or 0)))
        top = max(0, int(y) - max(0, int(padding or 0)))
        right = min(screen["width"], int(x) + int(width) + max(0, int(padding or 0)))
        bottom = min(screen["height"], int(y) + int(height) + max(0, int(padding or 0)))
        return {
            "x": left,
            "y": top,
            "width": max(1, right - left),
            "height": max(1, bottom - top),
        }

    def _build_observation_result(
        self,
        *,
        action: str,
        output_path: Path,
        scope_lines: List[str],
        screen: Dict[str, int],
        cursor: Dict[str, int],
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        image_bytes = output_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/png;base64,{image_b64}"
        summary_parts = [
            f"Desktop observation saved to {output_path}.",
            f"Screen size {screen['width']}x{screen['height']}.",
            f"Cursor at ({cursor['x']}, {cursor['y']}).",
        ] + scope_lines

        data = {
            "computer_control_action": action,
            "screen": screen,
            "cursor": cursor,
            "file_path": str(output_path),
            "mime_type": "image/png",
            "base64_image": image_b64,
            "message_content": [
                {"type": "text", "text": " ".join(summary_parts)},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
        if isinstance(extra_data, dict):
            data.update(extra_data)

        return ToolResult.ok(
            "\n".join(
                [
                    "Computer Controller observation captured.",
                    f"Path: {output_path}",
                    f"Desktop: {screen['width']} x {screen['height']}",
                    f"Cursor: ({cursor['x']}, {cursor['y']})",
                    *scope_lines,
                ]
            ),
            data=data,
        )

    def _observe(self, **kwargs) -> ToolResult:
        screen = self._screen_size()
        cursor = self._cursor_position()
        observation_name = str(kwargs.get("observation_name", "") or "").strip()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_stem = observation_name or f"desktop_{timestamp}"
        output_path = self.output_dir / f"{file_stem}.png"
        grid_cols = max(0, int(kwargs.get("grid_cols", 0) or 0))
        grid_rows = max(0, int(kwargs.get("grid_rows", 0) or 0))
        highlight_cursor = bool(kwargs.get("highlight_cursor", False))

        x = kwargs.get("x")
        y = kwargs.get("y")
        width = kwargs.get("width")
        height = kwargs.get("height")
        padding = max(0, int(kwargs.get("padding", 0) or 0))
        if None not in (x, y, width, height):
            region = self._normalize_region(int(x), int(y), int(width), int(height), padding=padding)
            self._capture_screenshot(
                output_path,
                x=region["x"],
                y=region["y"],
                width=region["width"],
                height=region["height"],
                grid_cols=grid_cols,
                grid_rows=grid_rows,
                highlight_cursor=highlight_cursor,
            )
            scope_lines = [
                f"Scope: region=({region['x']}, {region['y']}, {region['width']}, {region['height']})",
            ]
        else:
            self._capture_screenshot(
                output_path,
                grid_cols=grid_cols,
                grid_rows=grid_rows,
                highlight_cursor=highlight_cursor,
            )
            scope_lines = ["Scope: region=full-screen"]

        if grid_cols > 0 and grid_rows > 0:
            scope_lines.append(f"Grid overlay: {grid_cols} x {grid_rows}")
        if highlight_cursor:
            scope_lines.append("Cursor highlight: enabled when cursor is inside the captured region")

        return self._build_observation_result(
            action="observe",
            output_path=output_path,
            scope_lines=scope_lines,
            screen=screen,
            cursor=cursor,
            extra_data={
                "grid_cols": grid_cols,
                "grid_rows": grid_rows,
                "highlight_cursor": highlight_cursor,
            },
        )

    def _observe_window(self, **kwargs) -> ToolResult:
        screen = self._screen_size()
        cursor = self._cursor_position()
        window = self._active_window_info()
        bounds = window["bounds"]
        padding = max(0, int(kwargs.get("padding", 0) or 0))
        grid_cols = max(0, int(kwargs.get("grid_cols", 0) or 0))
        grid_rows = max(0, int(kwargs.get("grid_rows", 0) or 0))
        highlight_cursor = bool(kwargs.get("highlight_cursor", True))
        region = self._normalize_region(
            bounds["x"],
            bounds["y"],
            bounds["width"],
            bounds["height"],
            padding=padding,
        )

        observation_name = str(kwargs.get("observation_name", "") or "").strip()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_stem = observation_name or f"window_{timestamp}"
        output_path = self.output_dir / f"{file_stem}.png"

        self._capture_screenshot(
            output_path,
            x=region["x"],
            y=region["y"],
            width=region["width"],
            height=region["height"],
            grid_cols=grid_cols,
            grid_rows=grid_rows,
            highlight_cursor=highlight_cursor,
        )

        scope_lines = [
            f"Scope: active-window={window['title'] or '(untitled window)'}",
            f"Window bounds: ({bounds['x']}, {bounds['y']}, {bounds['width']}, {bounds['height']})",
            f"Capture bounds: ({region['x']}, {region['y']}, {region['width']}, {region['height']})",
        ]
        if grid_cols > 0 and grid_rows > 0:
            scope_lines.append(f"Grid overlay: {grid_cols} x {grid_rows}")
        if highlight_cursor:
            scope_lines.append("Cursor highlight: enabled when cursor is inside the captured region")

        return self._build_observation_result(
            action="observe_window",
            output_path=output_path,
            scope_lines=scope_lines,
            screen=screen,
            cursor=cursor,
            extra_data={
                "window": window,
                "grid_cols": grid_cols,
                "grid_rows": grid_rows,
                "highlight_cursor": highlight_cursor,
            },
        )
