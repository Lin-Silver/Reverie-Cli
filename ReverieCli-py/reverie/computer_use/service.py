"""Python implementation of the Open Computer Use tool contract on Windows.

The public contract follows iFurySt/open-codex-computer-use.  The runtime is
implemented in-process so Reverie does not need an MCP child process, Go
binary, or generated PowerShell script.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import base64
import ctypes
import io
import re
import sys
import time

from ..diagnostics import report_suppressed_exception


class ComputerUseError(RuntimeError):
    """A user-facing desktop automation failure."""


@dataclass
class ElementRecord:
    index: str
    runtime_id: tuple[int, ...]
    automation_id: str
    name: str
    control_type: str
    localized_control_type: str
    class_name: str
    value: str
    process_id: int
    frame: Optional[Dict[str, int]]
    actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "runtime_id": list(self.runtime_id),
            "automation_id": self.automation_id,
            "name": self.name,
            "control_type": self.control_type,
            "localized_control_type": self.localized_control_type,
            "class_name": self.class_name,
            "value": self.value,
            "process_id": self.process_id,
            "frame": self.frame,
            "actions": list(self.actions),
        }


@dataclass
class AppSnapshot:
    query: str
    process_id: int
    process_name: str
    window_title: str
    bounds: Dict[str, int]
    elements: Dict[str, ElementRecord]
    screenshot_path: str
    screenshot_base64: str
    tree_lines: List[str]
    captured_at: float


class OpenComputerUseService:
    """Stateful implementation shared by the nine Computer Use tools."""

    MAX_ELEMENTS = 500
    MAX_DEPTH = 16
    TEXT_LIMIT = 500

    def __init__(self, output_dir: Path):
        if sys.platform != "win32":
            raise ComputerUseError("Embedded Computer Use currently requires Windows.")
        try:
            import uiautomation as automation
            from PIL import ImageGrab
        except ImportError as exc:
            raise ComputerUseError(
                "Embedded Computer Use requires the 'uiautomation' and 'Pillow' packages."
            ) from exc

        self.auto = automation
        self.image_grab = ImageGrab
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots: Dict[str, AppSnapshot] = {}

    @staticmethod
    def _key(value: str) -> str:
        return str(value or "").strip().lower().removesuffix(".exe")

    @staticmethod
    def _safe_text(value: Any, *, full: bool = False) -> str:
        text = str(value or "").strip()
        if not full and len(text) > OpenComputerUseService.TEXT_LIMIT:
            return text[: OpenComputerUseService.TEXT_LIMIT] + "..."
        return text

    @staticmethod
    def _getattr(control: Any, name: str, default: Any = "") -> Any:
        try:
            return getattr(control, name)
        except Exception:
            return default

    def _process_name(self, process_id: int) -> str:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(process_id))
        if not handle:
            return str(process_id)
        try:
            size = ctypes.c_ulong(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return Path(buffer.value).stem
        finally:
            kernel32.CloseHandle(handle)
        return str(process_id)

    def _top_level_windows(self) -> Iterable[Any]:
        try:
            return self.auto.GetRootControl().GetChildren()
        except Exception as exc:
            raise ComputerUseError(f"Unable to enumerate desktop applications: {exc}") from exc

    def list_apps(self) -> List[Dict[str, Any]]:
        apps: List[Dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for control in self._top_level_windows():
            process_id = int(self._getattr(control, "ProcessId", 0) or 0)
            handle = int(self._getattr(control, "NativeWindowHandle", 0) or 0)
            title = self._safe_text(self._getattr(control, "Name", ""), full=True)
            bounds = self._rect(control)
            if process_id <= 0 or not bounds or (process_id, handle) in seen:
                continue
            seen.add((process_id, handle))
            apps.append(
                {
                    "name": self._process_name(process_id),
                    "pid": process_id,
                    "window_title": title or "untitled",
                    "window_handle": handle,
                    "window_bounds": bounds,
                    "status": "running",
                }
            )
        return sorted(apps, key=lambda item: (item["name"].lower(), item["pid"]))

    def _resolve_app(self, query: str) -> Any:
        wanted = self._key(query)
        if not wanted:
            raise ComputerUseError("app is required")
        exact: List[Any] = []
        partial: List[Any] = []
        for control in self._top_level_windows():
            process_id = int(self._getattr(control, "ProcessId", 0) or 0)
            if not self._rect(control):
                continue
            title = self._safe_text(self._getattr(control, "Name", ""), full=True)
            process_name = self._process_name(process_id)
            candidates = {self._key(process_name), self._key(title), str(process_id)}
            if wanted in candidates:
                exact.append(control)
            elif any(wanted in candidate for candidate in candidates if candidate):
                partial.append(control)
        matches = exact or partial
        if not matches:
            raise ComputerUseError(f"App not found or has no accessible window: {query}")
        return matches[0]

    @staticmethod
    def _rect(control: Any) -> Optional[Dict[str, int]]:
        try:
            rect = control.BoundingRectangle
            left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
            if right <= left or bottom <= top:
                return None
            return {"x": left, "y": top, "width": right - left, "height": bottom - top}
        except Exception:
            return None

    @staticmethod
    def _local_frame(frame: Optional[Dict[str, int]], bounds: Dict[str, int]) -> Optional[Dict[str, int]]:
        if not frame:
            return None
        return {
            "x": frame["x"] - bounds["x"],
            "y": frame["y"] - bounds["y"],
            "width": frame["width"],
            "height": frame["height"],
        }

    def _pattern(self, control: Any, pattern_name: str) -> Any:
        pattern_id = getattr(self.auto.PatternId, pattern_name, None)
        if pattern_id is None:
            return None
        try:
            return control.GetPattern(pattern_id)
        except Exception:
            return None

    def _actions(self, control: Any) -> List[str]:
        actions: List[str] = []
        for pattern_name, action in (
            ("InvokePattern", "Invoke"),
            ("TogglePattern", "Toggle"),
            ("SelectionItemPattern", "Select"),
            ("ExpandCollapsePattern", "ExpandCollapse"),
            ("ScrollItemPattern", "ScrollIntoView"),
            ("ScrollPattern", "Scroll"),
            ("ValuePattern", "SetValue"),
        ):
            if self._pattern(control, pattern_name) is not None:
                actions.append(action)
        return actions

    def _value(self, control: Any, *, full: bool) -> str:
        pattern = self._pattern(control, "ValuePattern")
        if pattern is not None:
            try:
                return self._safe_text(pattern.Value, full=full)
            except Exception:
                report_suppressed_exception("read desktop value pattern")
        return ""

    def _record(self, control: Any, index: int, bounds: Dict[str, int], *, full: bool) -> ElementRecord:
        try:
            runtime_id = tuple(int(item) for item in (control.GetRuntimeId() or ()))
        except Exception:
            runtime_id = ()
        return ElementRecord(
            index=str(index),
            runtime_id=runtime_id,
            automation_id=self._safe_text(self._getattr(control, "AutomationId", ""), full=True),
            name=self._safe_text(self._getattr(control, "Name", ""), full=full),
            control_type=self._safe_text(self._getattr(control, "ControlTypeName", ""), full=True),
            localized_control_type=self._safe_text(
                self._getattr(control, "LocalizedControlType", ""), full=True
            ),
            class_name=self._safe_text(self._getattr(control, "ClassName", ""), full=True),
            value=self._value(control, full=full),
            process_id=int(self._getattr(control, "ProcessId", 0) or 0),
            frame=self._local_frame(self._rect(control), bounds),
            actions=self._actions(control),
        )

    def _render_tree(self, root: Any, bounds: Dict[str, int], *, full: bool) -> tuple[Dict[str, ElementRecord], List[str]]:
        records: Dict[str, ElementRecord] = {}
        lines: List[str] = []
        visited: set[tuple[int, ...]] = set()

        def visit(control: Any, depth: int) -> None:
            if len(records) >= self.MAX_ELEMENTS or depth > self.MAX_DEPTH:
                return
            record = self._record(control, len(records), bounds, full=full)
            if record.runtime_id and record.runtime_id in visited:
                return
            if record.runtime_id:
                visited.add(record.runtime_id)
            records[record.index] = record
            role = record.localized_control_type or record.control_type or "control"
            title = record.name or (f"ID: {record.automation_id}" if record.automation_id else "")
            details = []
            if record.value and record.value != title:
                details.append("Value: " + record.value.replace("\r", "\\r").replace("\n", "\\n"))
            if record.actions:
                details.append("Secondary Actions: " + ", ".join(record.actions))
            if record.frame:
                details.append(
                    "Frame: {{x: {x}, y: {y}, width: {width}, height: {height}}}".format(**record.frame)
                )
            suffix = (" " + " ".join(details)) if details else ""
            lines.append("\t" * (depth + 1) + f"{record.index} {role} {title}{suffix}".rstrip())
            try:
                children = control.GetChildren()
            except Exception:
                children = []
            for child in children:
                visit(child, depth + 1)

        visit(root, 0)
        return records, lines

    def _capture(self, bounds: Dict[str, int], app_key: str) -> tuple[str, str]:
        bbox = (
            bounds["x"],
            bounds["y"],
            bounds["x"] + bounds["width"],
            bounds["y"] + bounds["height"],
        )
        image = self.image_grab.grab(bbox=bbox, all_screens=True)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        payload = buffer.getvalue()
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", app_key).strip("-._") or "app"
        path = self.output_dir / f"{safe_name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path.write_bytes(payload)
        return str(path), base64.b64encode(payload).decode("ascii")

    def get_app_state(self, app: str, *, show_full_text: bool = False) -> AppSnapshot:
        root = self._resolve_app(app)
        bounds = self._rect(root)
        if not bounds:
            raise ComputerUseError(f"No visible window bounds are available for {app}")
        process_id = int(self._getattr(root, "ProcessId", 0) or 0)
        records, lines = self._render_tree(root, bounds, full=show_full_text)
        screenshot_path, screenshot_base64 = self._capture(bounds, self._key(app))
        snapshot = AppSnapshot(
            query=app,
            process_id=process_id,
            process_name=self._process_name(process_id),
            window_title=self._safe_text(self._getattr(root, "Name", ""), full=show_full_text),
            bounds=bounds,
            elements=records,
            screenshot_path=screenshot_path,
            screenshot_base64=screenshot_base64,
            tree_lines=lines,
            captured_at=time.time(),
        )
        self._snapshots[self._key(app)] = snapshot
        return snapshot

    def _snapshot(self, app: str) -> AppSnapshot:
        snapshot = self._snapshots.get(self._key(app))
        if snapshot is None:
            raise ComputerUseError(
                f"Call get_app_state(app={app!r}) before using an action tool in this turn."
            )
        return snapshot

    def _all_controls(self, root: Any) -> Iterable[Any]:
        stack = [root]
        count = 0
        while stack and count < self.MAX_ELEMENTS:
            control = stack.pop()
            count += 1
            yield control
            try:
                stack.extend(reversed(control.GetChildren()))
            except Exception:
                continue

    def _resolve_element(self, app: str, index: str) -> Any:
        snapshot = self._snapshot(app)
        record = snapshot.elements.get(str(index))
        if record is None:
            raise ComputerUseError(f"Unknown element_index {index!r}; refresh get_app_state first")
        root = self._resolve_app(app)
        fallback = None
        for control in self._all_controls(root):
            try:
                runtime_id = tuple(int(item) for item in (control.GetRuntimeId() or ()))
            except Exception:
                runtime_id = ()
            if record.runtime_id and runtime_id == record.runtime_id:
                return control
            same_id = record.automation_id and self._getattr(control, "AutomationId", "") == record.automation_id
            same_name = record.name and self._getattr(control, "Name", "") == record.name
            same_type = self._getattr(control, "ControlTypeName", "") == record.control_type
            if fallback is None and same_type and (same_id or same_name):
                fallback = control
        if fallback is not None:
            return fallback
        raise ComputerUseError(f"Element {index!r} is stale; call get_app_state again")

    def _absolute_point(self, snapshot: AppSnapshot, x: Any, y: Any) -> tuple[int, int]:
        try:
            return snapshot.bounds["x"] + int(float(x)), snapshot.bounds["y"] + int(float(y))
        except (TypeError, ValueError) as exc:
            raise ComputerUseError("x and y must be numeric screenshot coordinates") from exc

    def click(
        self,
        app: str,
        *,
        element_index: Optional[str] = None,
        x: Any = None,
        y: Any = None,
        click_count: int = 1,
        mouse_button: str = "left",
    ) -> None:
        snapshot = self._snapshot(app)
        button = str(mouse_button or "left").lower()
        if button not in {"left", "right", "middle"}:
            raise ComputerUseError(f"Invalid mouse_button: {mouse_button}")
        count = max(1, int(click_count or 1))
        if element_index is not None:
            control = self._resolve_element(app, str(element_index))
            for _ in range(count):
                if button == "right":
                    control.RightClick(simulateMove=False)
                elif button == "middle":
                    frame = self._rect(control)
                    if not frame:
                        raise ComputerUseError("The selected element has no clickable bounds")
                    self.auto.MiddleClick(
                        frame["x"] + frame["width"] // 2,
                        frame["y"] + frame["height"] // 2,
                        waitTime=0.05,
                    )
                else:
                    control.Click(simulateMove=False)
            return
        if x is None or y is None:
            raise ComputerUseError("click requires either element_index or x/y")
        absolute_x, absolute_y = self._absolute_point(snapshot, x, y)
        clicker = {
            "left": self.auto.Click,
            "right": self.auto.RightClick,
            "middle": self.auto.MiddleClick,
        }[button]
        for _ in range(count):
            clicker(absolute_x, absolute_y, waitTime=0.05)

    def drag(self, app: str, from_x: Any, from_y: Any, to_x: Any, to_y: Any) -> None:
        snapshot = self._snapshot(app)
        start = self._absolute_point(snapshot, from_x, from_y)
        end = self._absolute_point(snapshot, to_x, to_y)
        self.auto.DragDrop(*start, *end, moveSpeed=0.5)

    def perform_secondary_action(self, app: str, element_index: str, action: str) -> None:
        control = self._resolve_element(app, element_index)
        action_name = str(action or "").strip().lower().replace(" ", "")
        if action_name == "invoke":
            pattern = self._pattern(control, "InvokePattern")
            if pattern:
                pattern.Invoke()
                return
        if action_name == "toggle":
            pattern = self._pattern(control, "TogglePattern")
            if pattern:
                pattern.Toggle()
                return
        if action_name == "select":
            pattern = self._pattern(control, "SelectionItemPattern")
            if pattern:
                pattern.Select()
                return
        if action_name in {"expand", "collapse"}:
            pattern = self._pattern(control, "ExpandCollapsePattern")
            if pattern:
                getattr(pattern, action_name.capitalize())()
                return
        if action_name == "scrollintoview":
            pattern = self._pattern(control, "ScrollItemPattern")
            if pattern:
                pattern.ScrollIntoView()
                return
        raise ComputerUseError(f"Element does not expose secondary action {action!r}")

    def scroll(self, app: str, element_index: str, direction: str, pages: float = 1) -> None:
        control = self._resolve_element(app, element_index)
        direction_name = str(direction or "").strip().lower()
        if direction_name not in {"up", "down", "left", "right"}:
            raise ComputerUseError(f"Invalid scroll direction: {direction}")
        pattern = self._pattern(control, "ScrollPattern")
        steps = max(1, int(round(abs(float(pages or 1)))))
        if pattern is not None:
            horizontal = self.auto.ScrollAmount.NoAmount
            vertical = self.auto.ScrollAmount.NoAmount
            amount = self.auto.ScrollAmount.LargeDecrement if direction_name in {"up", "left"} else self.auto.ScrollAmount.LargeIncrement
            if direction_name in {"left", "right"}:
                horizontal = amount
            else:
                vertical = amount
            for _ in range(steps):
                pattern.Scroll(horizontal, vertical)
            return
        frame = self._rect(control)
        if frame:
            self.auto.MoveTo(frame["x"] + frame["width"] // 2, frame["y"] + frame["height"] // 2, moveSpeed=0)
        wheel_steps = max(1, int(round(abs(float(pages or 1)) * 3)))
        (self.auto.WheelUp if direction_name in {"up", "left"} else self.auto.WheelDown)(wheel_steps)

    def set_value(self, app: str, element_index: str, value: str) -> None:
        control = self._resolve_element(app, element_index)
        pattern = self._pattern(control, "ValuePattern")
        if pattern is not None:
            if bool(getattr(pattern, "IsReadOnly", False)):
                raise ComputerUseError("The selected element is read-only")
            pattern.SetValue(str(value))
            return
        legacy = self._pattern(control, "LegacyIAccessiblePattern")
        if legacy is not None:
            legacy.SetValue(str(value))
            return
        raise ComputerUseError("The selected element does not support SetValue")

    @staticmethod
    def _send_keys_token(key: str) -> str:
        aliases = {
            "return": "ENTER",
            "enter": "ENTER",
            "escape": "ESC",
            "esc": "ESC",
            "backspace": "BACK",
            "delete": "DELETE",
            "space": "SPACE",
            "tab": "TAB",
            "up": "UP",
            "down": "DOWN",
            "left": "LEFT",
            "right": "RIGHT",
            "home": "HOME",
            "end": "END",
            "page_up": "PGUP",
            "page_down": "PGDN",
        }
        normalized = str(key or "").strip()
        mapped = aliases.get(normalized.lower(), normalized.upper())
        if len(normalized) == 1:
            return normalized
        return "{" + mapped + "}"

    def press_key(self, app: str, key: str) -> None:
        self._snapshot(app)
        parts = [part for part in re.split(r"[+]", str(key or "").strip()) if part]
        if not parts:
            raise ComputerUseError("key is required")
        modifiers = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Win", "win": "Win", "meta": "Win"}
        prefix = "".join("{" + modifiers[part.lower()] + "}" for part in parts[:-1] if part.lower() in modifiers)
        self.auto.SendKeys(prefix + self._send_keys_token(parts[-1]), charMode=False)

    def type_text(self, app: str, text: str) -> None:
        self._snapshot(app)
        self.auto.SendKeys(str(text), charMode=True)
