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
from ctypes import wintypes
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
    window_handle: int = 0
    screenshot_scale: float = 1.0


class OpenComputerUseService:
    """Stateful implementation shared by the embedded Computer Use tools."""

    MAX_ELEMENTS = 500
    MAX_DEPTH = 16
    TEXT_LIMIT = 500
    # Full-resolution grabs of a 4K window cost megabytes of base64 per
    # observation with no readability gain, so shrink the long edge to this.
    MAX_SCREENSHOT_DIMENSION = 1400
    # How long an action waits for the desktop to visibly react before it
    # reports "nothing changed".
    ACTION_SETTLE_SECONDS = 1.2
    LAUNCH_TIMEOUT_SECONDS = 12.0

    # ShellExecuteW returns a value <= 32 to signal failure.
    _SHELL_EXECUTE_ERRORS = {
        0: "the system is out of memory or resources",
        2: "the file was not found",
        3: "the path was not found",
        5: "access was denied",
        8: "there is not enough memory to finish the operation",
        11: "the executable is not a valid Windows application",
        26: "a sharing violation occurred",
        27: "the file name association is incomplete or invalid",
        28: "the DDE transaction timed out",
        29: "the DDE transaction failed",
        30: "other DDE transactions were being processed",
        31: "no application is associated with this file type",
        32: "the required DLL was not found",
    }

    def __init__(self, output_dir: Path):
        if sys.platform != "win32":
            raise ComputerUseError("Embedded Computer Use currently requires Windows.")
        self.auto = None
        self.image_grab = None
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots: Dict[str, AppSnapshot] = {}

    def _ensure_automation(self) -> Any:
        if self.auto is not None:
            return self.auto
        try:
            import uiautomation as automation
        except ImportError as exc:
            raise ComputerUseError(
                "Embedded Computer Use requires the 'uiautomation' package."
            ) from exc
        self._redirect_automation_log(automation)
        self.auto = automation
        return automation

    def _redirect_automation_log(self, automation: Any) -> None:
        """Keep uiautomation's diagnostics out of the user's working directory.

        Left alone, the library writes `@AutomationLog.txt` into the process CWD
        -- which is the workspace the user is editing -- so a desktop action
        silently drops an untracked file into their repository.
        """
        logger = getattr(automation, "Logger", None)
        set_log_file = getattr(logger, "SetLogFile", None)
        if set_log_file is None:
            return
        try:
            set_log_file(str(self.output_dir.parent / "uiautomation.log"))
        except Exception:
            report_suppressed_exception("redirect the uiautomation log file")

    def _ensure_image_grab(self) -> Any:
        if self.image_grab is not None:
            return self.image_grab
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise ComputerUseError("Embedded Computer Use requires the 'Pillow' package.") from exc
        self.image_grab = ImageGrab
        return ImageGrab

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
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
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

    def _native_windows(self) -> List[Dict[str, Any]]:
        """Enumerate top-level windows without querying every UIA provider.

        Some Electron/Chromium accessibility providers can block indefinitely
        while UI Automation walks the desktop root.  Win32 enumeration is
        sufficient for app discovery and gives UIA a single known handle for
        the later, app-scoped observation.
        """
        user32 = ctypes.windll.user32
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL

        windows: List[Dict[str, Any]] = []

        @enum_proc_type
        def visit(handle: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(handle):
                return True
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
            rect = wintypes.RECT()
            if process_id.value <= 0 or not user32.GetWindowRect(handle, ctypes.byref(rect)):
                return True
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width <= 0 or height <= 0:
                return True
            length = max(0, int(user32.GetWindowTextLengthW(handle)))
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, buffer, length + 1)
            windows.append(
                {
                    "name": self._process_name(int(process_id.value)),
                    "pid": int(process_id.value),
                    "window_title": self._safe_text(buffer.value, full=True),
                    "window_handle": int(handle),
                    "window_bounds": {
                        "x": int(rect.left),
                        "y": int(rect.top),
                        "width": width,
                        "height": height,
                    },
                    "status": "minimized" if user32.IsIconic(handle) else "running",
                }
            )
            return True

        if not user32.EnumWindows(visit, 0):
            raise ComputerUseError("Unable to enumerate desktop applications with Win32.")
        return windows

    def _top_level_windows(self) -> Iterable[Any]:
        try:
            return self.auto.GetRootControl().GetChildren()
        except Exception as exc:
            raise ComputerUseError(f"Unable to enumerate desktop applications: {exc}") from exc

    @staticmethod
    def _foreground_window() -> int:
        """Return the handle of the window that currently owns input, or 0."""
        try:
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            return int(user32.GetForegroundWindow() or 0)
        except Exception:
            report_suppressed_exception("read the foreground desktop window")
            return 0

    @staticmethod
    def _window_exists(handle: int) -> bool:
        try:
            user32 = ctypes.windll.user32
            user32.IsWindow.argtypes = [wintypes.HWND]
            user32.IsWindow.restype = wintypes.BOOL
            return bool(user32.IsWindow(int(handle)))
        except Exception:
            report_suppressed_exception("probe a desktop window handle")
            return True

    @staticmethod
    def _restore_window(handle: int) -> bool:
        """Un-minimize a window so it has real bounds again."""
        try:
            user32 = ctypes.windll.user32
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.IsIconic.restype = wintypes.BOOL
            if not user32.IsIconic(int(handle)):
                return False
            SW_RESTORE = 9
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.ShowWindow.restype = wintypes.BOOL
            user32.ShowWindow(int(handle), SW_RESTORE)
            time.sleep(0.35)
            return True
        except Exception:
            report_suppressed_exception("restore a minimized desktop window")
            return False

    def list_apps(self) -> List[Dict[str, Any]]:
        apps = self._native_windows()
        return sorted(apps, key=lambda item: (item["name"].lower(), item["pid"]))

    @staticmethod
    def _window_rank(window: Dict[str, Any], foreground: int) -> tuple:
        """Order candidate windows so the usable one wins.

        A minimized window reports no accessible bounds, so preferring a visible
        window keeps ``get_app_state`` from failing on an app that does have a
        usable window.  Foreground next (that is the one the user is looking
        at), then the largest window, then the handle so the choice is stable.
        """
        bounds = window.get("window_bounds") or {}
        area = int(bounds.get("width") or 0) * int(bounds.get("height") or 0)
        return (
            1 if window.get("status") == "minimized" else 0,
            0 if int(window.get("window_handle") or 0) == foreground else 1,
            -area,
            int(window.get("window_handle") or 0),
        )

    def _resolve_window(self, query: str) -> Dict[str, Any]:
        wanted = self._key(query)
        if not wanted:
            raise ComputerUseError("app is required")
        exact: List[Dict[str, Any]] = []
        partial: List[Dict[str, Any]] = []
        for window in self._native_windows():
            candidates = {
                self._key(window["name"]),
                self._key(window["window_title"]),
                str(window["pid"]),
            }
            if wanted in candidates:
                exact.append(window)
            elif any(wanted in candidate for candidate in candidates if candidate):
                partial.append(window)
        matches = exact or partial
        if not matches:
            raise ComputerUseError(
                f"App not found or has no accessible window: {query}. "
                "Call list_apps to see the running targets, or launch_app to start the program."
            )
        foreground = self._foreground_window()
        return sorted(matches, key=lambda item: self._window_rank(item, foreground))[0]

    def _control_from_handle(self, handle: int) -> Any:
        control = self._ensure_automation().ControlFromHandle(int(handle))
        if control is None:
            raise ComputerUseError(
                f"Window handle {handle} is no longer accessible; call list_apps again."
            )
        return control

    def _resolve_app(self, query: str) -> Any:
        return self._control_from_handle(self._resolve_window(query)["window_handle"])

    def _activate(self, control: Any) -> None:
        """Bring a window forward so mouse and keyboard input reach it."""
        for method in ("SetActive", "SetFocus"):
            action = getattr(control, method, None)
            if action is None:
                continue
            try:
                action()
                return
            except Exception:
                report_suppressed_exception(f"activate a desktop window via {method}")

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
    def _local_frame(
        frame: Optional[Dict[str, int]],
        bounds: Dict[str, int],
        scale: float = 1.0,
    ) -> Optional[Dict[str, int]]:
        """Convert screen coordinates into the observation's screenshot space.

        ``scale`` matches whatever downscaling ``_capture`` applied, so the
        frames in the tree and the x/y coordinates a model reads off the
        screenshot are always the same coordinate system.
        """
        if not frame:
            return None
        factor = float(scale or 1.0)
        return {
            "x": int(round((frame["x"] - bounds["x"]) * factor)),
            "y": int(round((frame["y"] - bounds["y"]) * factor)),
            "width": int(round(frame["width"] * factor)),
            "height": int(round(frame["height"] * factor)),
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

    def _record(
        self,
        control: Any,
        index: int,
        bounds: Dict[str, int],
        *,
        full: bool,
        scale: float = 1.0,
    ) -> ElementRecord:
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
            frame=self._local_frame(self._rect(control), bounds, scale),
            actions=self._actions(control),
        )

    def _render_tree(
        self,
        root: Any,
        bounds: Dict[str, int],
        *,
        full: bool,
        scale: float = 1.0,
    ) -> tuple[Dict[str, ElementRecord], List[str]]:
        records: Dict[str, ElementRecord] = {}
        lines: List[str] = []
        visited: set[tuple[int, ...]] = set()

        def visit(control: Any, depth: int) -> None:
            if len(records) >= self.MAX_ELEMENTS or depth > self.MAX_DEPTH:
                return
            record = self._record(control, len(records), bounds, full=full, scale=scale)
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

    def _capture(self, bounds: Dict[str, int], app_key: str) -> tuple[str, str, float]:
        """Grab the window, shrink oversized captures, and return (path, b64, scale)."""
        bbox = (
            bounds["x"],
            bounds["y"],
            bounds["x"] + bounds["width"],
            bounds["y"] + bounds["height"],
        )
        image = self._ensure_image_grab().grab(bbox=bbox, all_screens=True)
        original_width = int(image.width or 0)
        scale = 1.0
        if original_width and max(image.width, image.height) > self.MAX_SCREENSHOT_DIMENSION:
            # thumbnail() only ever shrinks and preserves the aspect ratio, so
            # one scale factor describes both axes.
            image.thumbnail((self.MAX_SCREENSHOT_DIMENSION, self.MAX_SCREENSHOT_DIMENSION))
            scale = float(image.width) / float(original_width)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        payload = buffer.getvalue()
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", app_key).strip("-._") or "app"
        path = self.output_dir / f"{safe_name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path.write_bytes(payload)
        return str(path), base64.b64encode(payload).decode("ascii"), scale

    def get_app_state(self, app: str, *, show_full_text: bool = False) -> AppSnapshot:
        window = self._resolve_window(app)
        handle = int(window["window_handle"])
        if self._restore_window(handle):
            # A minimized window reports no bounds at all; restoring it first is
            # what makes observing a backgrounded app work instead of failing.
            window = self._resolve_window(app)
            handle = int(window["window_handle"])
        root = self._control_from_handle(handle)
        bounds = self._rect(root)
        if not bounds:
            raise ComputerUseError(
                f"No visible window bounds are available for {app}. "
                "The window may be minimized or hidden; restore it, or pick another target from list_apps."
            )
        process_id = int(self._getattr(root, "ProcessId", 0) or 0)
        screenshot_path, screenshot_base64, scale = self._capture(bounds, self._key(app))
        records, lines = self._render_tree(root, bounds, full=show_full_text, scale=scale)
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
            window_handle=handle,
            screenshot_scale=scale,
        )
        self._snapshots[self._key(app)] = snapshot
        return snapshot

    def _snapshot(self, app: str) -> AppSnapshot:
        snapshot = self._snapshots.get(self._key(app))
        if snapshot is None:
            raise ComputerUseError(
                f"Call get_app_state(app={app!r}) before using an action tool on it."
            )
        if snapshot.window_handle and not self._window_exists(snapshot.window_handle):
            self._snapshots.pop(self._key(app), None)
            raise ComputerUseError(
                f"The window observed for {app!r} has closed. "
                f"Call list_apps, then get_app_state(app=...) on a window that still exists."
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
        """Map a screenshot pixel onto a screen pixel.

        Coordinates arrive in the coordinate space of the screenshot the model
        was shown, which ``_capture`` may have downscaled, so undo that factor
        before adding the window origin.
        """
        factor = float(snapshot.screenshot_scale or 1.0) or 1.0
        try:
            local_x = int(round(float(x) / factor))
            local_y = int(round(float(y) / factor))
        except (TypeError, ValueError) as exc:
            raise ComputerUseError("x and y must be numeric screenshot coordinates") from exc
        return snapshot.bounds["x"] + local_x, snapshot.bounds["y"] + local_y

    # ------------------------------------------------------------------
    # Action verification
    #
    # Every action tool used to report unconditional success, so a click that
    # merely selected a desktop icon read exactly like one that launched an
    # app.  These helpers diff the desktop before and after an action so the
    # tool result states what actually changed.
    # ------------------------------------------------------------------

    def _observe_world(self) -> Dict[str, Any]:
        windows: Dict[int, Dict[str, Any]] = {}
        for window in self._native_windows():
            windows[int(window["window_handle"])] = window
        return {"windows": windows, "foreground": self._foreground_window()}

    @staticmethod
    def _describe_window(window: Dict[str, Any]) -> str:
        title = str(window.get("window_title") or "untitled")
        return f"{window.get('name') or 'unknown'} \"{title}\" (pid={window.get('pid')})"

    @staticmethod
    def _new_windows(before: Dict[str, Any], after: Dict[str, Any]) -> List[Dict[str, Any]]:
        old = before.get("windows") or {}
        return [window for handle, window in (after.get("windows") or {}).items() if handle not in old]

    def _diff_world(self, before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
        old_windows: Dict[int, Dict[str, Any]] = before.get("windows") or {}
        new_windows: Dict[int, Dict[str, Any]] = after.get("windows") or {}
        changes: List[str] = []
        for handle, window in new_windows.items():
            if handle not in old_windows:
                changes.append(f"New window: {self._describe_window(window)}")
        for handle, window in old_windows.items():
            if handle not in new_windows:
                changes.append(f"Window closed: {self._describe_window(window)}")
        for handle, window in new_windows.items():
            previous = old_windows.get(handle)
            if previous is None:
                continue
            if previous.get("window_title") != window.get("window_title"):
                changes.append(
                    f"Title changed: \"{previous.get('window_title')}\" -> \"{window.get('window_title')}\""
                )
            if previous.get("status") != window.get("status"):
                changes.append(
                    f"{window.get('name')} is now {window.get('status')}"
                )
        if before.get("foreground") != after.get("foreground"):
            active = new_windows.get(int(after.get("foreground") or 0))
            changes.append(
                f"Foreground window: {self._describe_window(active)}" if active else "Foreground window changed"
            )
        return changes

    def _await_world_change(
        self,
        before: Dict[str, Any],
        *,
        timeout: float,
        require_new_window: bool = False,
    ) -> List[str]:
        """Poll until the desktop reacts, or the timeout proves it did not."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            after = self._observe_world()
            changes = self._diff_world(before, after)
            satisfied = bool(self._new_windows(before, after)) if require_new_window else bool(changes)
            if satisfied or time.monotonic() >= deadline:
                return changes
            time.sleep(0.15)

    def _focus_report(self) -> str:
        """Describe the element that currently has keyboard focus."""
        try:
            control = self._ensure_automation().GetFocusedControl()
        except Exception:
            report_suppressed_exception("read the focused desktop element")
            return ""
        if control is None:
            return ""
        role = self._safe_text(self._getattr(control, "LocalizedControlType", ""), full=True)
        name = self._safe_text(self._getattr(control, "Name", ""))
        value = self._value(control, full=False)
        label = " ".join(part for part in (role or "control", f'"{name}"' if name else "") if part)
        return f"Focus: {label}" + (f" Value: {value}" if value else "")

    @staticmethod
    def _report(headline: str, details: Iterable[str]) -> str:
        lines = [headline]
        lines.extend(detail for detail in details if detail)
        return "\n".join(lines)

    def _shell_execute(self, target: str, arguments: str) -> int:
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteW.argtypes = [
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            ctypes.c_int,
        ]
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        SW_SHOWNORMAL = 1
        result = shell32.ShellExecuteW(
            None, "open", target, arguments or None, None, SW_SHOWNORMAL
        )
        return int(result or 0)

    def launch_app(
        self,
        target: str,
        *,
        arguments: str = "",
        wait_seconds: Optional[float] = None,
    ) -> str:
        """Start a program, document, or URL and report the window it opened.

        Without this, reaching an app that is not already running means hunting
        for a desktop icon and hoping a click activates it.  ShellExecuteW
        resolves bare executable names through the App Paths registry, so
        ``msedge``, ``notepad`` and ``explorer`` work without a full path.
        """
        wanted = str(target or "").strip().strip('"')
        if not wanted:
            raise ComputerUseError("target is required")
        parameters = str(arguments or "").strip()
        timeout = self.LAUNCH_TIMEOUT_SECONDS if wait_seconds is None else float(wait_seconds)

        attempts = [wanted]
        if not re.search(r"[\\/]", wanted) and "." not in wanted:
            attempts.append(f"{wanted}.exe")

        before = self._observe_world()
        code = 0
        launched = wanted
        for candidate in attempts:
            code = self._shell_execute(candidate, parameters)
            if code > 32:
                launched = candidate
                break
        if code <= 32:
            reason = self._SHELL_EXECUTE_ERRORS.get(code, f"ShellExecute returned {code}")
            raise ComputerUseError(
                f"Unable to launch {target!r}: {reason}. "
                "Pass an executable name such as 'msedge', a full path, or a URL."
            )

        changes = self._await_world_change(before, timeout=timeout, require_new_window=True)
        opened = [
            change for change in changes if change.startswith("New window:")
        ]
        headline = f"Launched {launched!r}" + (f" with arguments {parameters!r}." if parameters else ".")
        if opened:
            return self._report(headline, changes)
        return self._report(
            headline,
            changes
            + [
                f"No new window appeared within {timeout:.0f}s. The app may still be starting, "
                "or it may have handed the request to an already running instance. "
                "Call list_apps to check before assuming this failed.",
            ],
        )

    def click(
        self,
        app: str,
        *,
        element_index: Optional[str] = None,
        x: Any = None,
        y: Any = None,
        click_count: int = 1,
        mouse_button: str = "left",
    ) -> str:
        snapshot = self._snapshot(app)
        button = str(mouse_button or "left").lower()
        if button not in {"left", "right", "middle"}:
            raise ComputerUseError(f"Invalid mouse_button: {mouse_button}")
        count = max(1, int(click_count or 1))
        before = self._observe_world()
        target: Optional[ElementRecord] = None
        if element_index is not None:
            target = snapshot.elements.get(str(element_index))
            control = self._resolve_element(app, str(element_index))
            # A click aimed at a background window is spent activating it, so
            # bring the app forward first and click for real afterwards.
            self._activate(self._control_from_handle(snapshot.window_handle) if snapshot.window_handle else control)
            self._click_control(control, button=button, count=count)
        else:
            if x is None or y is None:
                raise ComputerUseError("click requires either element_index or x/y")
            absolute_x, absolute_y = self._absolute_point(snapshot, x, y)
            if count >= 2 and button == "left":
                self.auto.DoubleClick(absolute_x, absolute_y, waitTime=0.05)
                remaining = count - 2
            else:
                remaining = count
            clicker = {
                "left": self.auto.Click,
                "right": self.auto.RightClick,
                "middle": self.auto.MiddleClick,
            }[button]
            for _ in range(remaining):
                clicker(absolute_x, absolute_y, waitTime=0.05)

        changes = self._await_world_change(before, timeout=self.ACTION_SETTLE_SECONDS)
        headline = f"Clicked {app} ({button}, click_count={count})."
        details = list(changes)
        focus = self._focus_report()
        if focus:
            details.append(focus)
        if not changes:
            details.append(self._no_visible_change_hint(target, button=button, count=count))
        return self._report(headline, details)

    def _click_control(self, control: Any, *, button: str, count: int) -> None:
        if button == "middle":
            frame = self._rect(control)
            if not frame:
                raise ComputerUseError("The selected element has no clickable bounds")
            center = (frame["x"] + frame["width"] // 2, frame["y"] + frame["height"] // 2)
            for _ in range(count):
                self.auto.MiddleClick(*center, waitTime=0.05)
            return
        if button == "right":
            for _ in range(count):
                control.RightClick(simulateMove=False)
            return
        # Two separate Click() calls are half a second apart, which Windows
        # reads as two single clicks, not a double-click - so an icon never
        # opens. DoubleClick sends the pair inside the double-click interval.
        remaining = count
        if remaining >= 2:
            control.DoubleClick(simulateMove=False)
            remaining -= 2
        for _ in range(remaining):
            control.Click(simulateMove=False)

    @staticmethod
    def _no_visible_change_hint(
        target: Optional[ElementRecord],
        *,
        button: str,
        count: int,
    ) -> str:
        hint = "No window, title, or focus change was observed."
        if button != "left" or count > 1:
            return hint + " Re-observe with get_app_state to see whether anything changed inside the window."
        selectable = bool(target and "Select" in target.actions)
        invokable = bool(target and "Invoke" in target.actions)
        if selectable and invokable:
            return (
                hint
                + " A single left click on a list item or icon only selects it."
                " Use perform_secondary_action(action=\"Invoke\") to activate it, or click_count=2."
                " To start a program, launch_app is more reliable than clicking its icon."
            )
        if invokable:
            return hint + " The element exposes Invoke; perform_secondary_action(action=\"Invoke\") is more reliable than a click."
        return hint + " Re-observe with get_app_state to see whether anything changed inside the window."

    def drag(self, app: str, from_x: Any, from_y: Any, to_x: Any, to_y: Any) -> str:
        snapshot = self._snapshot(app)
        start = self._absolute_point(snapshot, from_x, from_y)
        end = self._absolute_point(snapshot, to_x, to_y)
        before = self._observe_world()
        self.auto.DragDrop(*start, *end, moveSpeed=0.5)
        changes = self._await_world_change(before, timeout=self.ACTION_SETTLE_SECONDS)
        return self._report(
            f"Dragged in {app} from {start} to {end} (screen coordinates).",
            changes or ["No window change was observed; re-observe with get_app_state to confirm the drop."],
        )

    def perform_secondary_action(self, app: str, element_index: str, action: str) -> str:
        control = self._resolve_element(app, element_index)
        action_name = str(action or "").strip().lower().replace(" ", "")
        patterns = {
            "invoke": ("InvokePattern", "Invoke"),
            "toggle": ("TogglePattern", "Toggle"),
            "select": ("SelectionItemPattern", "Select"),
            "expand": ("ExpandCollapsePattern", "Expand"),
            "collapse": ("ExpandCollapsePattern", "Collapse"),
            "scrollintoview": ("ScrollItemPattern", "ScrollIntoView"),
        }
        entry = patterns.get(action_name)
        pattern = self._pattern(control, entry[0]) if entry else None
        if entry is None or pattern is None:
            raise ComputerUseError(
                f"Element does not expose secondary action {action!r}. "
                "The tree lists each element's available actions under 'Secondary Actions'."
            )
        before = self._observe_world()
        getattr(pattern, entry[1])()
        changes = self._await_world_change(before, timeout=self.ACTION_SETTLE_SECONDS)
        details = list(changes)
        focus = self._focus_report()
        if focus:
            details.append(focus)
        if not changes:
            details.append(
                "No window or title change was observed; re-observe with get_app_state to confirm the effect."
            )
        return self._report(f"Performed {entry[1]} on element {element_index} of {app}.", details)

    def scroll(self, app: str, element_index: str, direction: str, pages: float = 1) -> str:
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
            axis = "HorizontalScrollPercent" if direction_name in {"left", "right"} else "VerticalScrollPercent"
            start = self._scroll_percent(pattern, axis)
            for _ in range(steps):
                pattern.Scroll(horizontal, vertical)
            end = self._scroll_percent(pattern, axis)
            detail = f"{axis}: {start} -> {end}" if start is not None and end is not None else ""
            if start is not None and end is not None and start == end:
                detail += " (already at the end of the scroll range)"
            return self._report(f"Scrolled {direction_name} in {app} by {steps} page(s).", [detail])
        frame = self._rect(control)
        if frame:
            self.auto.MoveTo(frame["x"] + frame["width"] // 2, frame["y"] + frame["height"] // 2, moveSpeed=0)
        wheel_steps = max(1, int(round(abs(float(pages or 1)) * 3)))
        (self.auto.WheelUp if direction_name in {"up", "left"} else self.auto.WheelDown)(wheel_steps)
        return self._report(
            f"Wheel-scrolled {direction_name} in {app} by {wheel_steps} notch(es).",
            ["The element exposes no scroll pattern, so the result is unverified; re-observe with get_app_state."],
        )

    @staticmethod
    def _scroll_percent(pattern: Any, axis: str) -> Optional[int]:
        try:
            value = getattr(pattern, axis)
        except Exception:
            report_suppressed_exception("read a desktop scroll percentage")
            return None
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    def set_value(self, app: str, element_index: str, value: str) -> str:
        control = self._resolve_element(app, element_index)
        wanted = str(value)
        pattern = self._pattern(control, "ValuePattern")
        if pattern is not None:
            if bool(getattr(pattern, "IsReadOnly", False)):
                raise ComputerUseError("The selected element is read-only")
            pattern.SetValue(wanted)
            return self._verified_value(app, element_index, wanted)
        legacy = self._pattern(control, "LegacyIAccessiblePattern")
        if legacy is not None:
            legacy.SetValue(wanted)
            return self._verified_value(app, element_index, wanted)
        raise ComputerUseError("The selected element does not support SetValue")

    def _verified_value(self, app: str, element_index: str, wanted: str) -> str:
        """Read the value back so a silently rejected write cannot look like success."""
        headline = f"Set element {element_index} of {app}."
        try:
            control = self._resolve_element(app, element_index)
            actual = self._value(control, full=True)
        except ComputerUseError:
            return self._report(headline, ["The value could not be read back for verification."])
        if actual == wanted:
            return self._report(headline, [f"Value is now: {actual}"])
        return self._report(
            headline,
            [
                f"Value reads back as {actual!r}, not {wanted!r}. "
                "The field may reformat, truncate, or reject input; re-observe with get_app_state.",
            ],
        )

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

    def press_key(self, app: str, key: str) -> str:
        self._snapshot(app)
        self._activate(self._resolve_app(app))
        parts = [part for part in re.split(r"[+]", str(key or "").strip()) if part]
        if not parts:
            raise ComputerUseError("key is required")
        modifiers = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "super": "Win", "win": "Win", "meta": "Win"}
        prefix = "".join("{" + modifiers[part.lower()] + "}" for part in parts[:-1] if part.lower() in modifiers)
        before = self._observe_world()
        self.auto.SendKeys(prefix + self._send_keys_token(parts[-1]), charMode=False)
        changes = self._await_world_change(before, timeout=self.ACTION_SETTLE_SECONDS)
        details = list(changes)
        focus = self._focus_report()
        if focus:
            details.append(focus)
        if not changes:
            details.append(
                "No window change was observed; re-observe with get_app_state to confirm the key had an effect."
            )
        return self._report(f"Pressed {key!r} in {app}.", details)

    def type_text(self, app: str, text: str) -> str:
        self._snapshot(app)
        self._activate(self._resolve_app(app))
        payload = str(text)
        before_focus = self._focus_report()
        self.auto.SendKeys(payload, charMode=True)
        after_focus = self._focus_report()
        details = [after_focus or before_focus]
        if not after_focus:
            details.append(
                "No focused element was reported, so the text may not have landed anywhere. "
                "Click or set focus on the target field, then re-observe with get_app_state."
            )
        return self._report(f"Typed {len(payload)} character(s) into {app}.", details)
