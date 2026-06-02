"""Browser Controler tool.

Provides a browser-focused automation and diagnostics surface for opening pages,
driving visible browser UI, inspecting page text, opening DevTools, and checking
web/server endpoints without turning the workflow into a static fetch-only pass.
"""

from __future__ import annotations

import os
import base64
import json
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import struct
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseTool, ToolResult
from ..config import get_project_data_dir


IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import ctypes
    import winreg
    from ctypes import wintypes

    ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = ()
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = ()
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = (wintypes.UINT,)
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetActiveWindow.argtypes = (wintypes.HWND,)
    user32.SetActiveWindow.restype = wintypes.HWND
    user32.SetFocus.argtypes = (wintypes.HWND,)
    user32.SetFocus.restype = wintypes.HWND
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = (ENUM_WINDOWS_PROC, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = (
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = ()
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
else:
    ctypes = None  # type: ignore[assignment]
    winreg = None  # type: ignore[assignment]
    wintypes = None  # type: ignore[assignment]
    user32 = None  # type: ignore[assignment]
    kernel32 = None  # type: ignore[assignment]
    ENUM_WINDOWS_PROC = None  # type: ignore[assignment]
    RECT = None  # type: ignore[assignment]


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9

VK_CODES = {
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "menu": 0x12,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "pgup": 0x21,
    "pgdn": 0x22,
}
for _index in range(1, 13):
    VK_CODES[f"f{_index}"] = 0x6F + _index


AI_SERVICE_URLS = {
    "chatgpt": "https://chatgpt.com/",
    "deepseek": "https://chat.deepseek.com/",
    "gemini": "https://gemini.google.com/app",
    "claude": "https://claude.ai/new",
    "kimi": "https://www.kimi.com/",
    "doubao": "https://www.doubao.com/chat/",
    "perplexity": "https://www.perplexity.ai/",
}

BROWSER_PROCESS_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "brave-browser.exe",
    "opera.exe",
    "opera_gx.exe",
    "vivaldi.exe",
    "arc.exe",
    "browser.exe",
}

DEFAULT_CDP_PORT = 9222
CDP_HOST = "127.0.0.1"


class _CdpWebSocket:
    """Small WebSocket client for Chrome DevTools Protocol JSON messages."""

    def __init__(self, websocket_url: str, *, timeout: float = 5.0):
        self.websocket_url = websocket_url
        self.timeout = max(0.5, float(timeout or 5.0))
        self.sock: Optional[socket.socket] = None

    def __enter__(self) -> "_CdpWebSocket":
        self.connect()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def connect(self) -> None:
        parsed = urlparse(self.websocket_url)
        if parsed.scheme not in {"ws", "wss"}:
            raise RuntimeError(f"Unsupported DevTools WebSocket URL: {self.websocket_url}")
        host = parsed.hostname or CDP_HOST
        port = int(parsed.port or (443 if parsed.scheme == "wss" else 80))
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"

        raw_sock = socket.create_connection((host, port), timeout=self.timeout)
        if parsed.scheme == "wss":
            raw_sock = ssl.create_default_context().wrap_socket(raw_sock, server_hostname=host)
        raw_sock.settimeout(self.timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Connection: Upgrade\r\n"
            "Upgrade: websocket\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "\r\n"
        )
        raw_sock.sendall(request.encode("ascii"))

        response = b""
        deadline = time.time() + self.timeout
        while b"\r\n\r\n" not in response:
            if time.time() > deadline:
                raw_sock.close()
                raise RuntimeError("Timed out during DevTools WebSocket handshake")
            chunk = raw_sock.recv(4096)
            if not chunk:
                break
            response += chunk
        first_line = response.split(b"\r\n", 1)[0]
        if b" 101 " not in first_line:
            raw_sock.close()
            preview = response[:300].decode("utf-8", errors="replace")
            raise RuntimeError(f"DevTools WebSocket handshake failed: {preview}")
        self.sock = raw_sock

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        if not sock:
            return
        try:
            self._send_frame(b"", opcode=0x8)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    def send_json(self, payload: Dict[str, Any]) -> None:
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        self._send_frame(text.encode("utf-8"), opcode=0x1)

    def recv_json(self, *, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        payload = self._recv_frame(timeout=timeout)
        if payload is None:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            return {"method": "_rawWebSocketMessage", "params": {"payload": payload.decode("utf-8", errors="replace")}}

    def _send_frame(self, payload: bytes, *, opcode: int = 0x1) -> None:
        if not self.sock:
            raise RuntimeError("DevTools WebSocket is not connected")
        first = 0x80 | int(opcode)
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", first, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", first, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", first, 0x80 | 127, length)
        mask_key = secrets.token_bytes(4)
        masked = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + mask_key + masked)

    def _recv_frame(self, *, timeout: Optional[float] = None) -> Optional[bytes]:
        while True:
            header = self._recv_exact(2, timeout=timeout)
            if not header:
                return None
            first, second = header[0], header[1]
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                extended = self._recv_exact(2, timeout=timeout)
                if not extended:
                    return None
                length = struct.unpack("!H", extended)[0]
            elif length == 127:
                extended = self._recv_exact(8, timeout=timeout)
                if not extended:
                    return None
                length = struct.unpack("!Q", extended)[0]
            mask_key = self._recv_exact(4, timeout=timeout) if masked else b""
            payload = self._recv_exact(length, timeout=timeout) if length else b""
            if payload is None:
                return None
            if masked and mask_key:
                payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                return None
            if opcode == 0x9:
                self._send_frame(payload, opcode=0xA)
                continue
            if opcode == 0xA:
                continue
            if opcode in {0x1, 0x2}:
                return payload

    def _recv_exact(self, count: int, *, timeout: Optional[float] = None) -> Optional[bytes]:
        if not self.sock:
            raise RuntimeError("DevTools WebSocket is not connected")
        old_timeout = self.sock.gettimeout()
        if timeout is not None:
            self.sock.settimeout(max(0.01, float(timeout)))
        try:
            chunks: List[bytes] = []
            remaining = int(count)
            while remaining > 0:
                try:
                    chunk = self.sock.recv(remaining)
                except socket.timeout:
                    return None
                if not chunk:
                    return None
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            if timeout is not None:
                self.sock.settimeout(old_timeout)


class _CdpConnection:
    """Request/response helper for one DevTools Protocol page target."""

    def __init__(self, websocket_url: str, *, timeout: float = 5.0):
        self.websocket_url = websocket_url
        self.timeout = max(0.5, float(timeout or 5.0))
        self.websocket: Optional[_CdpWebSocket] = None
        self.next_id = 1
        self.events: List[Dict[str, Any]] = []

    def __enter__(self) -> "_CdpConnection":
        self.websocket = _CdpWebSocket(self.websocket_url, timeout=self.timeout)
        self.websocket.connect()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        if self.websocket:
            self.websocket.close()

    def call(self, method: str, params: Optional[Dict[str, Any]] = None, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        if not self.websocket:
            raise RuntimeError("DevTools connection is not open")
        message_id = self.next_id
        self.next_id += 1
        self.websocket.send_json({"id": message_id, "method": method, "params": params or {}})
        wait_timeout = max(0.5, float(timeout or self.timeout))
        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            remaining = max(0.01, min(0.5, deadline - time.time()))
            message = self.websocket.recv_json(timeout=remaining)
            if not message:
                continue
            if message.get("id") == message_id:
                if message.get("error"):
                    error = message.get("error") or {}
                    raise RuntimeError(f"{method} failed: {error.get('message') or error}")
                return message.get("result") or {}
            self.events.append(message)
        raise RuntimeError(f"Timed out waiting for DevTools method {method}")

    def collect(self, seconds: float) -> List[Dict[str, Any]]:
        if not self.websocket:
            raise RuntimeError("DevTools connection is not open")
        collected: List[Dict[str, Any]] = []
        deadline = time.time() + max(0.0, float(seconds or 0.0))
        while time.time() < deadline:
            remaining = max(0.01, min(0.5, deadline - time.time()))
            message = self.websocket.recv_json(timeout=remaining)
            if message:
                collected.append(message)
        self.events.extend(collected)
        return collected


class BrowserControlerTool(BaseTool):
    """Control the default browser and extract page information."""

    name = "browser_controler"
    aliases = ("browser_controller", "browser_control", "Browser Controler")
    search_hint = "open control browser devtools inspect page diagnose endpoint server web app"
    tool_category = "browser"
    tool_tags = ("browser", "web", "desktop", "devtools", "diagnostics", "server", "upload")
    max_result_chars = 80_000
    description = (
        "Browser Controler opens the system browser, including private windows when possible, "
        "controls visible browser pages with mouse/keyboard/scroll actions, opens DevTools, talks to "
        "Chromium DevTools Protocol for console/network/DOM inspection, uploads workspace files through "
        "file dialogs, copies or extracts page text, diagnoses page structure, and checks web/server endpoints."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "active_window",
                    "list_browser_windows",
                    "activate_browser",
                    "open_browser",
                    "open_page",
                    "open_debug_page",
                    "open_devtools",
                    "devtools_targets",
                    "devtools_snapshot",
                    "devtools_eval",
                    "devtools_console",
                    "devtools_network",
                    "diagnose_page",
                    "check_endpoint",
                    "open_ai_service",
                    "ai_chat",
                    "close_page",
                    "current_url",
                    "extract_page",
                    "copy_page_text",
                    "observe",
                    "click",
                    "scroll",
                    "type_text",
                    "paste_text",
                    "key_press",
                    "hotkey",
                    "upload_file",
                    "wait",
                ],
                "description": "Browser action to perform.",
            },
            "url": {"type": "string", "description": "URL to open or extract. If omitted for extract_page, the current browser URL is copied from the address bar."},
            "service": {"type": "string", "description": "Optional web service shortcut for open_ai_service/ai_chat."},
            "browser": {"type": "string", "description": "Optional browser hint: default, chrome, edge, firefox, brave."},
            "browser_path": {"type": "string", "description": "Optional explicit browser executable path."},
            "private": {"type": "boolean", "description": "Open a private/incognito window when possible."},
            "new_window": {"type": "boolean", "description": "Open in a new browser window."},
            "port": {"type": "integer", "description": "Chrome DevTools Protocol remote debugging port for open_debug_page/devtools_* actions."},
            "target_id": {"type": "string", "description": "Optional DevTools target id for devtools_* actions."},
            "url_contains": {"type": "string", "description": "Optional target URL/title substring for activate_browser or devtools_* target selection."},
            "expression": {"type": "string", "description": "JavaScript expression to run through DevTools Runtime.evaluate."},
            "await_promise": {"type": "boolean", "description": "For devtools_eval, wait for returned promises."},
            "return_by_value": {"type": "boolean", "description": "For devtools_eval, return JSON-serializable values by value."},
            "include_bodies": {"type": "boolean", "description": "For devtools_network, include response body previews when available."},
            "max_body_chars": {"type": "integer", "description": "For devtools_network, maximum characters per captured response body preview."},
            "max_events": {"type": "integer", "description": "For devtools_console/devtools_network, maximum events/items to render."},
            "reload": {"type": "boolean", "description": "For devtools_network, reload the selected page after enabling Network."},
            "user_data_dir": {"type": "string", "description": "Optional isolated browser profile directory for open_debug_page."},
            "include_all_windows": {"type": "boolean", "description": "For list_browser_windows, include non-browser top-level windows too."},
            "title_contains": {"type": "string", "description": "For activate_browser, choose a browser window whose title contains this text."},
            "window_index": {"type": "integer", "description": "For activate_browser, zero-based index among matching browser windows."},
            "text": {"type": "string", "description": "Text to type or paste into the active browser page."},
            "prompt": {"type": "string", "description": "Prompt text for ai_chat."},
            "send": {"type": "boolean", "description": "Press Enter after pasting text in ai_chat or paste_text."},
            "x": {"type": "integer", "description": "Screen X coordinate for click or upload button."},
            "y": {"type": "integer", "description": "Screen Y coordinate for click or upload button."},
            "button": {"type": "string", "description": "Mouse button: left or right."},
            "delta": {"type": "integer", "description": "Mouse wheel delta. Positive scrolls up, negative scrolls down. One notch is 120."},
            "key": {"type": "string", "description": "Single key for key_press."},
            "keys": {"type": "array", "items": {"type": "string"}, "description": "Key chord for hotkey, e.g. ['ctrl', 'l']."},
            "file_path": {"type": "string", "description": "Workspace-relative file path to upload through the active file dialog."},
            "file_paths": {"type": "array", "items": {"type": "string"}, "description": "Workspace-relative files to upload sequentially."},
            "wait_seconds": {"type": "number", "description": "Delay for wait or after opening pages."},
            "max_chars": {"type": "integer", "description": "Maximum page text characters to include in the tool output."},
            "include_links": {"type": "boolean", "description": "Include links/images/forms when extracting a page."},
            "check_assets": {"type": "boolean", "description": "For diagnose_page, also check scripts, stylesheets, and images with HEAD/GET requests."},
            "method": {"type": "string", "description": "HTTP method for check_endpoint, such as GET, POST, PUT, PATCH, DELETE, OPTIONS, or HEAD."},
            "headers": {"type": "object", "description": "Optional HTTP headers for check_endpoint."},
            "body": {"type": "string", "description": "Optional raw request body for check_endpoint."},
            "json_body": {"type": "object", "description": "Optional JSON request body for check_endpoint."},
            "timeout": {"type": "number", "description": "HTTP timeout in seconds for diagnose_page/check_endpoint."},
            "close_window": {"type": "boolean", "description": "For close_page, close the whole browser window instead of the active tab."},
            "observation_name": {"type": "string", "description": "Optional screenshot file stem for observe."},
            "grid_cols": {"type": "integer", "description": "Optional screenshot grid columns."},
            "grid_rows": {"type": "integer", "description": "Optional screenshot grid rows."},
        },
        "required": ["action"],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = self.get_project_root()
        self.output_dir = get_project_data_dir(self.project_root) / "browser_controler"
        self.pages_dir = self.output_dir / "pages"
        self.observations_dir = self.output_dir / "observations"
        self.debug_profiles_dir = self.output_dir / "debug-profiles"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        self.debug_profiles_dir.mkdir(parents=True, exist_ok=True)

    def get_execution_message(self, action: str, **kwargs) -> str:
        action_name = str(action or "").strip().lower()
        return {
            "active_window": "Inspecting active window",
            "list_browser_windows": "Listing browser windows",
            "activate_browser": "Activating browser window",
            "open_browser": "Opening browser window",
            "open_page": "Opening browser page",
            "open_debug_page": "Opening browser page with DevTools Protocol enabled",
            "open_devtools": "Opening browser developer tools",
            "devtools_targets": "Listing DevTools Protocol page targets",
            "devtools_snapshot": "Reading live DOM text through DevTools Protocol",
            "devtools_eval": "Running JavaScript in the browser through DevTools Protocol",
            "devtools_console": "Reading browser console and log events",
            "devtools_network": "Reading browser network events and responses",
            "diagnose_page": "Diagnosing web page structure and resources",
            "check_endpoint": "Checking web/server endpoint",
            "open_ai_service": "Opening web AI service",
            "ai_chat": "Interacting with web AI service",
            "close_page": "Closing browser page",
            "current_url": "Reading current browser URL",
            "extract_page": "Extracting browser page content",
            "copy_page_text": "Copying visible page text",
            "observe": "Capturing browser observation",
            "click": "Clicking browser surface",
            "scroll": "Scrolling browser surface",
            "type_text": "Typing into browser",
            "paste_text": "Pasting text into browser",
            "key_press": "Pressing browser key",
            "hotkey": "Sending browser hotkey",
            "upload_file": "Uploading file through browser dialog",
            "wait": "Waiting for browser UI",
        }.get(action_name, "Controlling browser")

    def execute(self, action: str, **kwargs) -> ToolResult:
        action_name = str(action or "").strip().lower()
        try:
            if action_name == "active_window":
                return self._active_window()
            if action_name == "list_browser_windows":
                return self._list_browser_windows(include_all=bool(kwargs.get("include_all_windows", False)))
            if action_name == "activate_browser":
                return self._activate_browser(
                    title_contains=str(kwargs.get("title_contains") or ""),
                    window_index=int(kwargs.get("window_index", 0) or 0),
                )
            if action_name in {"open_browser", "open_page"}:
                return self._open_page(**kwargs)
            if action_name == "open_debug_page":
                return self._open_debug_page(**kwargs)
            if action_name == "open_devtools":
                return self._open_devtools(**kwargs)
            if action_name == "devtools_targets":
                return self._devtools_targets(
                    port=int(kwargs.get("port", DEFAULT_CDP_PORT) or DEFAULT_CDP_PORT),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_snapshot":
                return self._devtools_snapshot(
                    port=int(kwargs.get("port", DEFAULT_CDP_PORT) or DEFAULT_CDP_PORT),
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    max_chars=int(kwargs.get("max_chars", 30000) or 30000),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_eval":
                return self._devtools_eval(
                    expression=str(kwargs.get("expression") or ""),
                    port=int(kwargs.get("port", DEFAULT_CDP_PORT) or DEFAULT_CDP_PORT),
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    await_promise=bool(kwargs.get("await_promise", True)),
                    return_by_value=bool(kwargs.get("return_by_value", True)),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_console":
                return self._devtools_console(
                    expression=str(kwargs.get("expression") or ""),
                    port=int(kwargs.get("port", DEFAULT_CDP_PORT) or DEFAULT_CDP_PORT),
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    wait_seconds=float(kwargs.get("wait_seconds", 1.0) or 1.0),
                    max_events=int(kwargs.get("max_events", 80) or 80),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "devtools_network":
                return self._devtools_network(
                    url=kwargs.get("url"),
                    port=int(kwargs.get("port", DEFAULT_CDP_PORT) or DEFAULT_CDP_PORT),
                    target_id=str(kwargs.get("target_id") or ""),
                    url_contains=str(kwargs.get("url_contains") or ""),
                    wait_seconds=float(kwargs.get("wait_seconds", 3.0) or 3.0),
                    include_bodies=bool(kwargs.get("include_bodies", False)),
                    max_body_chars=int(kwargs.get("max_body_chars", 2000) or 2000),
                    max_events=int(kwargs.get("max_events", 120) or 120),
                    reload=bool(kwargs.get("reload", False)),
                    timeout=float(kwargs.get("timeout", 5) or 5),
                )
            if action_name == "diagnose_page":
                return self._diagnose_page(
                    url=kwargs.get("url"),
                    max_chars=int(kwargs.get("max_chars", 20000) or 20000),
                    include_links=bool(kwargs.get("include_links", True)),
                    check_assets=bool(kwargs.get("check_assets", False)),
                    timeout=float(kwargs.get("timeout", 20) or 20),
                )
            if action_name == "check_endpoint":
                return self._check_endpoint(**kwargs)
            if action_name == "open_ai_service":
                service_url = self._resolve_service_url(kwargs.get("service"), kwargs.get("url"))
                return self._open_page(url=service_url, **{k: v for k, v in kwargs.items() if k != "url"})
            if action_name == "ai_chat":
                return self._ai_chat(**kwargs)
            if action_name == "close_page":
                return self._close_page(close_window=bool(kwargs.get("close_window", False)))
            if action_name == "current_url":
                return self._current_url()
            if action_name == "extract_page":
                return self._extract_page(
                    url=kwargs.get("url"),
                    max_chars=int(kwargs.get("max_chars", 20000) or 20000),
                    include_links=bool(kwargs.get("include_links", True)),
                )
            if action_name == "copy_page_text":
                return self._copy_page_text(max_chars=int(kwargs.get("max_chars", 30000) or 30000))
            if action_name == "observe":
                return self._observe(**kwargs)
            if action_name == "click":
                return self._click(kwargs.get("x"), kwargs.get("y"), button=str(kwargs.get("button", "left") or "left"))
            if action_name == "scroll":
                return self._scroll(int(kwargs.get("delta", -360) or -360))
            if action_name == "type_text":
                return self._type_text(str(kwargs.get("text", "") or ""), press_enter=bool(kwargs.get("send", False)))
            if action_name == "paste_text":
                return self._paste_text(str(kwargs.get("text", "") or ""), press_enter=bool(kwargs.get("send", False)))
            if action_name == "key_press":
                return self._key_press(str(kwargs.get("key", "") or ""))
            if action_name == "hotkey":
                return self._hotkey(kwargs.get("keys") or [])
            if action_name == "upload_file":
                return self._upload_file(kwargs.get("file_path"), x=kwargs.get("x"), y=kwargs.get("y"))
            if action_name == "wait":
                return self._wait(float(kwargs.get("wait_seconds", 1.0) or 1.0))
            return ToolResult.fail(f"Unknown browser_controler action: {action_name}")
        except Exception as exc:
            return ToolResult.fail(f"Browser Controler failed: {exc}")

    def _active_window(self) -> ToolResult:
        self._require_windows_desktop()
        info = self._foreground_window_info()
        return ToolResult.ok(self._render_window_info(info, prefix="Active window"), data={"window": info})

    def _list_browser_windows(self, *, include_all: bool = False) -> ToolResult:
        self._require_windows_desktop()
        windows = self._top_level_windows()
        browser_windows = [item for item in windows if item.get("is_browser")]
        selected = windows if include_all else browser_windows
        if not selected:
            return ToolResult.ok(
                "No browser windows were found." if not include_all else "No top-level windows were found.",
                data={"windows": selected, "browser_count": len(browser_windows), "window_count": len(windows)},
            )
        lines = [
            f"Browser windows: {len(browser_windows)}",
            f"Top-level windows: {len(windows)}",
            "",
        ]
        for index, item in enumerate(selected):
            marker = "browser" if item.get("is_browser") else "window"
            lines.append(
                f"[{index}] {marker}: {item.get('title') or '(untitled)'} "
                f"({item.get('process_name') or 'unknown'}, pid={item.get('process_id') or 0})"
            )
        return ToolResult.ok(
            "\n".join(lines).strip(),
            data={"windows": selected, "browser_count": len(browser_windows), "window_count": len(windows)},
        )

    def _activate_browser(self, *, title_contains: str = "", window_index: int = 0) -> ToolResult:
        self._require_windows_desktop()
        browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
        needle = str(title_contains or "").strip().lower()
        if needle:
            browser_windows = [item for item in browser_windows if needle in str(item.get("title") or "").lower()]
        if not browser_windows:
            return ToolResult.fail(
                "No matching browser window found."
                + (f" title_contains={title_contains!r}" if title_contains else "")
            )
        index = max(0, min(int(window_index or 0), len(browser_windows) - 1))
        selected = browser_windows[index]
        hwnd = int(selected.get("handle") or 0)
        if not hwnd:
            return ToolResult.fail("Selected browser window has no handle.")
        activated = self._activate_window_handle(hwnd)
        if not activated:
            active = self._foreground_window_info()
            return ToolResult.fail(
                "Tried to activate the browser window, but Windows kept another foreground window. "
                f"{self._render_window_info(active, prefix='Active window')}"
            )
        return ToolResult.ok(self._render_window_info(selected, prefix="Activated browser window"), data={"window": selected})

    def _activate_first_browser_window(self) -> bool:
        browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
        if not browser_windows:
            return False
        hwnd = int(browser_windows[0].get("handle") or 0)
        if not hwnd:
            return False
        return self._activate_window_handle(hwnd)

    def _open_page(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "about:blank").strip() or "about:blank"
        private = bool(kwargs.get("private", False))
        new_window = bool(kwargs.get("new_window", True))
        browser = str(kwargs.get("browser") or "default").strip()
        browser_path = str(kwargs.get("browser_path") or "").strip()
        wait_seconds = float(kwargs.get("wait_seconds", 0.75) or 0.75)
        before_browser_handles: set[int] = set()
        if IS_WINDOWS:
            try:
                before_browser_handles = {
                    int(item.get("handle") or 0)
                    for item in self._top_level_windows()
                    if item.get("is_browser")
                }
            except Exception:
                before_browser_handles = set()

        if private or browser_path or browser.lower() not in {"", "default", "system"}:
            executable = self._resolve_browser_executable(browser=browser, browser_path=browser_path)
            if not executable:
                if private:
                    return ToolResult.fail("Could not resolve a browser executable for private mode.")
                webbrowser.open_new(url) if new_window else webbrowser.open(url)
            else:
                args = [str(executable)]
                args.extend(self._browser_window_flags(executable, private=private, new_window=new_window))
                args.append(url)
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open_new(url) if new_window else webbrowser.open(url)

        if wait_seconds > 0:
            time.sleep(min(wait_seconds, 10.0))
        activated = False
        if IS_WINDOWS:
            try:
                browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
                new_browser_windows = [
                    item for item in browser_windows
                    if int(item.get("handle") or 0) not in before_browser_handles
                ]
                for candidate in new_browser_windows + browser_windows:
                    handle = int(candidate.get("handle") or 0)
                    if handle and self._activate_window_handle(handle):
                        activated = True
                        break
            except Exception:
                activated = False
        mode = "private " if private else ""
        suffix = " Activated a browser window." if activated else ""
        return ToolResult.ok(f"Opened {mode}browser page: {url}.{suffix}", data={"url": url, "private": private, "activated": activated})

    def _open_devtools(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        if url:
            opened = self._open_page(**kwargs)
            if not opened.success:
                return opened
            time.sleep(float(kwargs.get("wait_seconds", 1.0) or 1.0))
        self._require_windows_desktop()
        self._send_key("f12")
        return ToolResult.ok("Opened DevTools for the active browser page." + (f" Page: {url}" if url else ""))

    def _open_debug_page(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "about:blank").strip() or "about:blank"
        port = self._normalize_cdp_port(kwargs.get("port", DEFAULT_CDP_PORT))
        browser = str(kwargs.get("browser") or "chrome").strip() or "chrome"
        if browser.lower() in {"default", "system"}:
            browser = "chrome"
        browser_path = str(kwargs.get("browser_path") or "").strip()
        executable = self._resolve_browser_executable(browser=browser, browser_path=browser_path)
        if not executable and not browser_path:
            for fallback_browser in ("edge", "brave", "default"):
                if fallback_browser == browser.lower():
                    continue
                candidate = self._resolve_browser_executable(browser=fallback_browser, browser_path="")
                if candidate and "firefox" not in candidate.name.lower():
                    executable = candidate
                    break
        if not executable:
            return ToolResult.fail("Could not resolve Chrome/Edge/Brave for DevTools Protocol browser control.")
        if "firefox" in executable.name.lower():
            return ToolResult.fail("open_debug_page requires a Chromium-based browser for DevTools Protocol.")

        user_data_dir = str(kwargs.get("user_data_dir") or "").strip()
        profile_dir = Path(user_data_dir).expanduser() if user_data_dir else self.debug_profiles_dir / f"port-{port}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        wait_seconds = max(1.0, min(float(kwargs.get("wait_seconds", 3.0) or 3.0), 20.0))
        before_browser_handles: set[int] = set()
        if IS_WINDOWS:
            try:
                before_browser_handles = {
                    int(item.get("handle") or 0)
                    for item in self._top_level_windows()
                    if item.get("is_browser")
                }
            except Exception:
                before_browser_handles = set()

        args = [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
        ]
        for flag in self._browser_window_flags(executable, private=bool(kwargs.get("private", False)), new_window=True):
            if flag not in args:
                args.append(flag)
        if "--new-window" not in args:
            args.append("--new-window")
        args.append(url)

        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        version: Dict[str, Any] = {}
        deadline = time.time() + wait_seconds
        last_error = ""
        while time.time() < deadline:
            try:
                version = self._cdp_version(port, timeout=1.0)
                break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.2)
        if not version:
            return ToolResult.fail(
                f"Opened browser process pid={process.pid}, but DevTools Protocol on port {port} did not respond. {last_error}"
            )

        activated = False
        if IS_WINDOWS:
            try:
                browser_windows = [item for item in self._top_level_windows() if item.get("is_browser")]
                new_browser_windows = [
                    item for item in browser_windows
                    if int(item.get("handle") or 0) not in before_browser_handles
                ]
                for candidate in new_browser_windows + browser_windows:
                    handle = int(candidate.get("handle") or 0)
                    if handle and self._activate_window_handle(handle):
                        activated = True
                        break
            except Exception:
                activated = False

        output = [
            f"Opened DevTools-enabled browser page: {url}",
            f"CDP: http://{CDP_HOST}:{port}",
            f"Profile: {profile_dir}",
            f"Browser: {version.get('Browser') or executable.name}",
        ]
        if activated:
            output.append("Activated a browser window.")
        return ToolResult.ok(
            "\n".join(output),
            data={
                "url": url,
                "port": port,
                "profile_dir": str(profile_dir),
                "browser": str(executable),
                "process_id": process.pid,
                "version": version,
                "activated": activated,
            },
        )

    def _devtools_targets(self, *, port: int, url_contains: str = "", timeout: float = 5.0) -> ToolResult:
        targets = self._cdp_list_targets(port, timeout=timeout)
        needle = str(url_contains or "").strip().lower()
        if needle:
            targets = [
                item for item in targets
                if needle in str(item.get("url") or "").lower() or needle in str(item.get("title") or "").lower()
            ]
        lines = [f"DevTools targets on {CDP_HOST}:{port}: {len(targets)}"]
        for index, item in enumerate(targets[:60]):
            websocket = "yes" if item.get("webSocketDebuggerUrl") else "no"
            lines.append(
                f"[{index}] id={item.get('id')} type={item.get('type')} websocket={websocket}\n"
                f"    title={item.get('title') or '(untitled)'}\n"
                f"    url={item.get('url') or '(empty)'}"
            )
        return ToolResult.ok("\n".join(lines), data={"port": port, "targets": targets})

    def _devtools_snapshot(
        self,
        *,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        max_chars: int = 30000,
        timeout: float = 5.0,
    ) -> ToolResult:
        expression = (
            "(() => ({"
            "url: location.href,"
            "title: document.title,"
            "text: document.body ? document.body.innerText : '',"
            "html: document.documentElement ? document.documentElement.outerHTML : ''"
            "}))()"
        )
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            result = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": True,
                    "returnByValue": True,
                    "userGesture": True,
                },
                timeout=timeout,
            )
        if result.get("exceptionDetails"):
            details = self._format_cdp_exception(result.get("exceptionDetails") or {})
            return ToolResult.partial(f"DevTools DOM snapshot raised an exception:\n{details}", details, data={"target": target})
        value = (result.get("result") or {}).get("value") or {}
        page_url = str(value.get("url") or target.get("url") or "")
        title = str(value.get("title") or target.get("title") or "")
        text = str(value.get("text") or "")
        html = str(value.get("html") or "")
        saved = self._persist_page_artifacts(page_url or "devtools-snapshot", html, text)
        clipped = text[: max(1, int(max_chars))]
        lines = [
            f"URL: {page_url}",
            f"Title: {title or '(missing)'}",
            f"Text chars: {len(text)}",
            f"HTML chars: {len(html)}",
            "",
            "Live DOM Text:",
            clipped,
        ]
        if len(text) > len(clipped):
            lines.append(f"\n[truncated; full text saved to {saved.get('text_path')}]")
        lines.append(f"\nSaved full page text: {saved.get('text_path')}")
        lines.append(f"Saved HTML: {saved.get('html_path')}")
        return ToolResult.ok(
            "\n".join(lines).strip(),
            data={"target": target, "url": page_url, "title": title, "text_chars": len(text), "html_chars": len(html), **saved},
        )

    def _devtools_eval(
        self,
        *,
        expression: str,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        await_promise: bool = True,
        return_by_value: bool = True,
        timeout: float = 5.0,
    ) -> ToolResult:
        if not str(expression or "").strip():
            return ToolResult.fail("expression is required for devtools_eval")
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            result = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": bool(await_promise),
                    "returnByValue": bool(return_by_value),
                    "userGesture": True,
                },
                timeout=timeout,
            )
        remote = result.get("result") or {}
        value = self._format_cdp_remote_object(remote)
        lines = [
            "DevTools Console Evaluation:",
            f"Target: {target.get('title') or '(untitled)'}",
            f"URL: {target.get('url') or '(empty)'}",
            f"Type: {remote.get('type') or 'unknown'}",
            f"Value: {value}",
        ]
        if result.get("exceptionDetails"):
            details = self._format_cdp_exception(result.get("exceptionDetails") or {})
            lines.append("\nException:\n" + details)
            return ToolResult.partial("\n".join(lines), "DevTools expression raised an exception.", data={"target": target, "result": result})
        return ToolResult.ok("\n".join(lines), data={"target": target, "result": result, "value": remote.get("value")})

    def _devtools_console(
        self,
        *,
        expression: str = "",
        port: int,
        target_id: str = "",
        url_contains: str = "",
        wait_seconds: float = 1.0,
        max_events: int = 80,
        timeout: float = 5.0,
    ) -> ToolResult:
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        eval_result: Dict[str, Any] = {}
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Runtime.enable", timeout=timeout)
            self._safe_cdp_call(cdp, "Log.enable", timeout=timeout)
            if expression.strip():
                eval_result = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": expression,
                        "awaitPromise": True,
                        "returnByValue": True,
                        "userGesture": True,
                    },
                    timeout=timeout,
                )
            cdp.collect(max(0.0, min(float(wait_seconds or 0.0), 30.0)))
            events = list(cdp.events)
        lines = [
            f"DevTools console/log events for {target.get('title') or '(untitled)'}",
            f"URL: {target.get('url') or '(empty)'}",
        ]
        if eval_result:
            remote = eval_result.get("result") or {}
            lines.append(f"Evaluation value: {self._format_cdp_remote_object(remote)}")
            if eval_result.get("exceptionDetails"):
                lines.append("Evaluation exception: " + self._format_cdp_exception(eval_result.get("exceptionDetails") or {}))
        rendered = self._render_cdp_console_events(events, max_events=max_events)
        if rendered:
            lines.append("\nEvents:")
            lines.extend(rendered)
        else:
            lines.append("\nNo console/log events were observed after Runtime/Log were enabled.")
        return ToolResult.ok("\n".join(lines), data={"target": target, "events": events, "evaluation": eval_result})

    def _devtools_network(
        self,
        *,
        url: Any = None,
        port: int,
        target_id: str = "",
        url_contains: str = "",
        wait_seconds: float = 3.0,
        include_bodies: bool = False,
        max_body_chars: int = 2000,
        max_events: int = 120,
        reload: bool = False,
        timeout: float = 5.0,
    ) -> ToolResult:
        target = self._cdp_select_target(port, target_id=target_id, url_contains=url_contains, timeout=timeout)
        navigate_url = str(url or "").strip()
        with _CdpConnection(str(target["webSocketDebuggerUrl"]), timeout=timeout) as cdp:
            self._safe_cdp_call(cdp, "Network.enable", timeout=timeout)
            self._safe_cdp_call(cdp, "Page.enable", timeout=timeout)
            if navigate_url:
                cdp.call("Page.navigate", {"url": navigate_url}, timeout=timeout)
            elif reload:
                cdp.call("Page.reload", {"ignoreCache": True}, timeout=timeout)
            cdp.collect(max(0.1, min(float(wait_seconds or 0.0), 60.0)))
            summary = self._summarize_cdp_network_events(cdp.events, max_events=max_events)
            if include_bodies:
                self._attach_cdp_response_bodies(cdp, summary["responses"], max_body_chars=max_body_chars, timeout=min(timeout, 3.0))
        output = self._render_cdp_network_summary(summary, target=target)
        return ToolResult.ok(output, data={"target": target, **summary})

    def _ai_chat(self, **kwargs) -> ToolResult:
        service_url = self._resolve_service_url(kwargs.get("service"), kwargs.get("url"))
        open_result = self._open_page(
            url=service_url,
            private=bool(kwargs.get("private", False)),
            new_window=bool(kwargs.get("new_window", True)),
            browser=kwargs.get("browser") or "default",
            browser_path=kwargs.get("browser_path") or "",
            wait_seconds=float(kwargs.get("wait_seconds", 2.0) or 2.0),
        )
        if not open_result.success:
            return open_result

        uploaded: List[str] = []
        file_paths = list(kwargs.get("file_paths") or [])
        if kwargs.get("file_path"):
            file_paths.insert(0, kwargs.get("file_path"))
        for file_path in file_paths:
            upload_result = self._upload_file(file_path, x=kwargs.get("x"), y=kwargs.get("y"))
            if not upload_result.success:
                return upload_result
            uploaded.append(str(upload_result.data.get("file_path", "")))
            time.sleep(0.5)

        text = str(kwargs.get("prompt") or kwargs.get("text") or "").strip()
        if text:
            paste_result = self._paste_text(text, press_enter=bool(kwargs.get("send", True)))
            if not paste_result.success:
                return paste_result

        details = [f"Opened {service_url}"]
        if uploaded:
            details.append(f"uploaded {len(uploaded)} file(s)")
        if text:
            details.append("submitted prompt" if bool(kwargs.get("send", True)) else "pasted prompt")
        return ToolResult.ok("AI service interaction prepared: " + ", ".join(details), data={"url": service_url, "uploaded": uploaded})

    def _resolve_service_url(self, service: Any, fallback_url: Any = None) -> str:
        fallback = str(fallback_url or "").strip()
        if fallback:
            return fallback
        key = str(service or "deepseek").strip().lower()
        return AI_SERVICE_URLS.get(key, key if key.startswith(("http://", "https://")) else AI_SERVICE_URLS["deepseek"])

    def _close_page(self, *, close_window: bool = False) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        self._send_hotkey(["alt", "f4"] if close_window else ["ctrl", "w"])
        return ToolResult.ok("Closed the active browser window." if close_window else "Closed the active browser tab.")

    def _current_url(self) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        old_clipboard = self._get_clipboard_text()
        try:
            self._send_hotkey(["ctrl", "l"])
            time.sleep(0.1)
            self._send_hotkey(["ctrl", "c"])
            time.sleep(0.1)
            url = self._get_clipboard_text().strip()
            self._send_key("esc")
        finally:
            self._set_clipboard_text(old_clipboard)
        if not url:
            return ToolResult.fail("Could not read the current browser URL from the address bar.")
        return ToolResult.ok(f"Current browser URL: {url}", data={"url": url})

    def _extract_page(self, *, url: Any = None, max_chars: int = 20000, include_links: bool = True) -> ToolResult:
        page_url = str(url or "").strip()
        if not page_url:
            current = self._current_url()
            if not current.success:
                return current
            page_url = str(current.data.get("url", "") or "").strip()
        if not page_url.startswith(("http://", "https://")):
            return ToolResult.fail(f"extract_page requires an http(s) URL, got: {page_url}")

        response = requests.get(
            page_url,
            timeout=20,
            headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
        )
        response.raise_for_status()
        html = response.text
        summary = self._summarize_html(page_url, html, include_links=include_links)
        text = str(summary.get("text", "") or "")
        saved = self._persist_page_artifacts(page_url, html, text)
        output = self._render_page_summary(summary, max_chars=max_chars)
        if saved:
            output += f"\n\nSaved full page text: {saved.get('text_path')}\nSaved HTML: {saved.get('html_path')}"
        return ToolResult.ok(output, data={**summary, **saved, "status_code": response.status_code})

    def _diagnose_page(
        self,
        *,
        url: Any = None,
        max_chars: int = 20000,
        include_links: bool = True,
        check_assets: bool = False,
        timeout: float = 20.0,
    ) -> ToolResult:
        page_url = str(url or "").strip()
        if not page_url:
            current = self._current_url()
            if not current.success:
                return current
            page_url = str(current.data.get("url", "") or "").strip()
        if not page_url.startswith(("http://", "https://")):
            return ToolResult.fail(f"diagnose_page requires an http(s) URL, got: {page_url}")

        response = requests.get(
            page_url,
            timeout=max(1.0, float(timeout)),
            headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
        )
        summary = self._summarize_html(page_url, response.text, include_links=include_links)
        diagnostics = self._build_page_diagnostics(page_url, response, summary)
        if check_assets:
            diagnostics["asset_checks"] = self._check_page_assets(page_url, response.text, timeout=max(1.0, float(timeout)))

        saved = self._persist_page_artifacts(page_url, response.text, str(summary.get("text", "") or ""))
        output = self._render_page_diagnostics(diagnostics, summary, max_chars=max_chars)
        output += f"\n\nSaved full page text: {saved.get('text_path')}\nSaved HTML: {saved.get('html_path')}"
        return ToolResult.ok(output, data={**diagnostics, "summary": summary, **saved})

    def _check_endpoint(self, **kwargs) -> ToolResult:
        url = str(kwargs.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return ToolResult.fail("check_endpoint requires an http(s) url")
        method = str(kwargs.get("method") or "GET").strip().upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
            return ToolResult.fail(f"Unsupported HTTP method: {method}")
        headers = kwargs.get("headers") if isinstance(kwargs.get("headers"), dict) else {}
        timeout = max(1.0, float(kwargs.get("timeout", 20) or 20))
        json_body = kwargs.get("json_body") if isinstance(kwargs.get("json_body"), dict) else None
        body = kwargs.get("body")

        started = time.time()
        response = requests.request(
            method,
            url,
            headers={str(key): str(value) for key, value in (headers or {}).items()},
            data=None if json_body is not None else body,
            json=json_body,
            timeout=timeout,
            allow_redirects=True,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        content_type = response.headers.get("content-type", "")
        text_preview = response.text[:4000] if method != "HEAD" else ""
        result = {
            "url": response.url,
            "requested_url": url,
            "method": method,
            "status_code": response.status_code,
            "ok": 200 <= int(response.status_code) < 400,
            "elapsed_ms": elapsed_ms,
            "content_type": content_type,
            "headers": dict(response.headers),
            "redirected": response.url != url,
            "body_preview": text_preview,
        }
        output = [
            f"Endpoint: {method} {url}",
            f"Status: {response.status_code} {'OK' if result['ok'] else 'FAILED'}",
            f"Final URL: {response.url}",
            f"Elapsed: {elapsed_ms} ms",
            f"Content-Type: {content_type}",
        ]
        if text_preview:
            output.append("\nBody Preview:\n" + text_preview)
        return ToolResult.ok("\n".join(output).strip(), data=result)

    def _copy_page_text(self, *, max_chars: int = 30000) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        old_clipboard = self._get_clipboard_text()
        try:
            self._focus_active_browser_page()
            self._send_hotkey(["ctrl", "a"])
            time.sleep(0.1)
            self._send_hotkey(["ctrl", "c"])
            time.sleep(0.25)
            text = self._get_clipboard_text()
            self._send_key("esc")
        finally:
            self._set_clipboard_text(old_clipboard)
        if not text.strip():
            return ToolResult.fail("No page text was copied. Click the page body and try copy_page_text again.")
        text_path = self._persist_text("copied-page-text", text)
        clipped = text[: max(1, int(max_chars))]
        if len(text) > len(clipped):
            clipped += f"\n\n[truncated; full text saved to {text_path}]"
        return ToolResult.ok(clipped, data={"text_path": str(text_path), "char_count": len(text)})

    def _observe(self, **kwargs) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        try:
            from PIL import ImageDraw, ImageGrab
        except Exception as exc:
            return ToolResult.fail(f"Browser observation requires Pillow ImageGrab support: {exc}")

        image = ImageGrab.grab()
        grid_cols = int(kwargs.get("grid_cols", 0) or 0)
        grid_rows = int(kwargs.get("grid_rows", 0) or 0)
        if grid_cols > 0 and grid_rows > 0:
            draw = ImageDraw.Draw(image)
            width, height = image.size
            for col in range(1, grid_cols):
                x = int(width * col / grid_cols)
                draw.line([(x, 0), (x, height)], fill=(255, 80, 80), width=2)
            for row in range(1, grid_rows):
                y = int(height * row / grid_rows)
                draw.line([(0, y), (width, y)], fill=(255, 80, 80), width=2)

        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(kwargs.get("observation_name") or "browser").strip()).strip("-._") or "browser"
        path = self.observations_dir / f"{stem}-{int(time.time() * 1000)}.png"
        image.save(path)
        return ToolResult.ok(f"Saved browser screenshot: {path}", data={"image_path": str(path), "width": image.size[0], "height": image.size[1]})

    def _click(self, x: Any, y: Any, *, button: str = "left") -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        x_value = int(x)
        y_value = int(y)
        user32.SetCursorPos(x_value, y_value)
        time.sleep(0.05)
        if str(button or "left").lower() == "right":
            down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        else:
            down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(up, 0, 0, 0, 0)
        return ToolResult.ok(f"Clicked browser surface at ({x_value}, {y_value}).")

    def _scroll(self, delta: int) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(delta), 0)
        return ToolResult.ok(f"Scrolled browser surface by {int(delta)}.")

    def _type_text(self, text: str, *, press_enter: bool = False) -> ToolResult:
        return self._paste_text(text, press_enter=press_enter)

    def _paste_text(self, text: str, *, press_enter: bool = False) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        if not text:
            return ToolResult.fail("text is required")
        old_clipboard = self._get_clipboard_text()
        try:
            self._set_clipboard_text(text)
            self._send_hotkey(["ctrl", "v"])
            time.sleep(0.1)
            if press_enter:
                self._send_key("enter")
        finally:
            self._set_clipboard_text(old_clipboard)
        return ToolResult.ok("Pasted text into the active browser page." + (" Pressed Enter." if press_enter else ""))

    def _key_press(self, key: str) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        self._send_key(key)
        return ToolResult.ok(f"Pressed key: {key}")

    def _hotkey(self, keys: Sequence[Any]) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        key_list = [str(key or "").strip() for key in keys if str(key or "").strip()]
        if not key_list:
            return ToolResult.fail("keys is required for hotkey")
        self._send_hotkey(key_list)
        return ToolResult.ok(f"Sent hotkey: {'+'.join(key_list)}")

    def _upload_file(self, file_path: Any, *, x: Any = None, y: Any = None) -> ToolResult:
        self._require_windows_desktop()
        active_error = self._active_browser_error()
        if active_error:
            return active_error
        if not file_path:
            return ToolResult.fail("file_path is required")
        resolved = self.resolve_workspace_path(file_path, purpose="upload browser file")
        if not resolved.exists() or not resolved.is_file():
            return ToolResult.fail(f"Upload file not found: {file_path}")
        if x is not None and y is not None:
            click_result = self._click(x, y)
            if not click_result.success:
                return click_result
            time.sleep(0.7)

        old_clipboard = self._get_clipboard_text()
        try:
            self._set_clipboard_text(str(resolved))
            self._send_hotkey(["ctrl", "v"])
            time.sleep(0.1)
            self._send_key("enter")
        finally:
            self._set_clipboard_text(old_clipboard)
        return ToolResult.ok(f"Uploaded file through active browser dialog: {resolved}", data={"file_path": str(resolved)})

    def _wait(self, seconds: float) -> ToolResult:
        duration = max(0.0, min(float(seconds), 60.0))
        time.sleep(duration)
        return ToolResult.ok(f"Waited {duration:.1f} seconds.")

    def _require_windows_desktop(self) -> None:
        if not IS_WINDOWS or user32 is None:
            raise RuntimeError("desktop browser control currently requires Windows")

    def _active_browser_error(self) -> Optional[ToolResult]:
        active = self._foreground_window_info()
        if active.get("is_browser"):
            return None
        return ToolResult.fail(
            "Active window is not a recognized browser. "
            f"{self._render_window_info(active, prefix='Active window')}. "
            "Use list_browser_windows and activate_browser first."
        )

    def _activate_window_handle(self, hwnd: int) -> bool:
        self._require_windows_desktop()
        hwnd_value = wintypes.HWND(int(hwnd or 0))
        if not hwnd_value:
            return False

        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd_value, None)
        current_thread = kernel32.GetCurrentThreadId()
        attached: List[tuple[int, int]] = []

        for source, target in ((current_thread, target_thread), (current_thread, foreground_thread), (foreground_thread, target_thread)):
            if source and target and source != target:
                if user32.AttachThreadInput(wintypes.DWORD(source), wintypes.DWORD(target), True):
                    attached.append((source, target))
        try:
            user32.ShowWindow(hwnd_value, SW_RESTORE)
            user32.BringWindowToTop(hwnd_value)
            user32.SetActiveWindow(hwnd_value)
            user32.SetFocus(hwnd_value)
            user32.SetForegroundWindow(hwnd_value)
            time.sleep(0.25)
        finally:
            for source, target in reversed(attached):
                user32.AttachThreadInput(wintypes.DWORD(source), wintypes.DWORD(target), False)

        active = self._foreground_window_info()
        return int(active.get("handle") or 0) == int(hwnd or 0) or bool(active.get("is_browser"))

    def _focus_active_browser_page(self) -> None:
        self._send_key("esc")
        time.sleep(0.08)
        hwnd = user32.GetForegroundWindow()
        rect = RECT()
        if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        width = max(1, int(rect.right - rect.left))
        height = max(1, int(rect.bottom - rect.top))
        x = int(rect.left + width * 0.5)
        y = int(rect.top + max(140, height * 0.45))
        user32.SetCursorPos(x, y)
        time.sleep(0.03)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.08)

    def _foreground_window_info(self) -> Dict[str, Any]:
        self._require_windows_desktop()
        hwnd = user32.GetForegroundWindow()
        return self._window_info(hwnd)

    def _top_level_windows(self) -> List[Dict[str, Any]]:
        self._require_windows_desktop()
        windows: List[Dict[str, Any]] = []

        @ENUM_WINDOWS_PROC
        def enum_callback(hwnd: Any, _lparam: Any) -> bool:
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                title = self._window_title(hwnd)
                if not title:
                    return True
                windows.append(self._window_info(hwnd, title=title))
            except Exception:
                return True
            return True

        user32.EnumWindows(enum_callback, 0)
        return windows

    def _window_info(self, hwnd: Any, *, title: Optional[str] = None) -> Dict[str, Any]:
        self._require_windows_desktop()
        hwnd_int = int(hwnd or 0)
        pid_value = 0
        if hwnd_int:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(wintypes.HWND(hwnd_int), ctypes.byref(pid))
            pid_value = int(pid.value or 0)
        process_path = self._process_path(pid_value)
        process_name = Path(process_path).name.lower() if process_path else ""
        return {
            "handle": hwnd_int,
            "title": title if title is not None else self._window_title(hwnd),
            "process_id": pid_value,
            "process_name": process_name,
            "process_path": process_path,
            "is_browser": self._is_browser_process(process_name, process_path),
        }

    @staticmethod
    def _render_window_info(info: Dict[str, Any], *, prefix: str = "Window") -> str:
        title = str(info.get("title") or "(untitled)")
        process_name = str(info.get("process_name") or "unknown")
        pid = int(info.get("process_id") or 0)
        browser_flag = "browser" if info.get("is_browser") else "not-browser"
        return f"{prefix}: {title} ({process_name}, pid={pid}, {browser_flag})"

    def _window_title(self, hwnd: Any) -> str:
        self._require_windows_desktop()
        hwnd_value = wintypes.HWND(int(hwnd or 0))
        length = int(user32.GetWindowTextLengthW(hwnd_value) or 0)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd_value, buffer, length + 1)
        return str(buffer.value or "").strip()

    def _process_path(self, process_id: int) -> str:
        if not process_id:
            return ""
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(process_id))
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return ""
            return str(buffer.value or "")
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _is_browser_process(process_name: str, process_path: str = "") -> bool:
        lowered_name = str(process_name or "").strip().lower()
        if lowered_name in BROWSER_PROCESS_NAMES:
            return True
        lowered_path = str(process_path or "").replace("\\", "/").lower()
        return any(f"/{name[:-4]}/" in lowered_path for name in BROWSER_PROCESS_NAMES if name.endswith(".exe"))

    @staticmethod
    def _normalize_cdp_port(port: Any) -> int:
        value = int(port or DEFAULT_CDP_PORT)
        if value <= 0 or value > 65535:
            raise ValueError(f"Invalid DevTools Protocol port: {port}")
        return value

    @staticmethod
    def _cdp_base_url(port: int) -> str:
        return f"http://{CDP_HOST}:{BrowserControlerTool._normalize_cdp_port(port)}"

    def _cdp_version(self, port: int, *, timeout: float = 5.0) -> Dict[str, Any]:
        response = requests.get(f"{self._cdp_base_url(port)}/json/version", timeout=max(0.5, float(timeout or 5.0)))
        response.raise_for_status()
        return response.json()

    def _cdp_list_targets(self, port: int, *, timeout: float = 5.0) -> List[Dict[str, Any]]:
        response = requests.get(f"{self._cdp_base_url(port)}/json/list", timeout=max(0.5, float(timeout or 5.0)))
        response.raise_for_status()
        targets = response.json()
        if not isinstance(targets, list):
            raise RuntimeError("DevTools /json/list did not return a target list")
        return [item for item in targets if isinstance(item, dict)]

    def _cdp_create_target(self, port: int, url: str, *, timeout: float = 5.0) -> Dict[str, Any]:
        endpoint = f"{self._cdp_base_url(port)}/json/new?{quote(str(url or 'about:blank'), safe=':/?&=%#')}"
        try:
            response = requests.put(endpoint, timeout=max(0.5, float(timeout or 5.0)))
            response.raise_for_status()
            result = response.json()
        except Exception:
            response = requests.get(endpoint, timeout=max(0.5, float(timeout or 5.0)))
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("DevTools target creation did not return a target object")
        return result

    def _cdp_select_target(
        self,
        port: int,
        *,
        target_id: str = "",
        url_contains: str = "",
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        targets = self._cdp_list_targets(port, timeout=timeout)
        if target_id:
            for item in targets:
                if str(item.get("id") or "") == str(target_id):
                    if item.get("webSocketDebuggerUrl"):
                        return item
                    raise RuntimeError(f"DevTools target has no WebSocket URL: {target_id}")
            raise RuntimeError(f"No DevTools target matched id={target_id}")

        pages = [
            item for item in targets
            if item.get("webSocketDebuggerUrl") and str(item.get("type") or "").lower() == "page"
        ]
        needle = str(url_contains or "").strip().lower()
        if needle:
            pages = [
                item for item in pages
                if needle in str(item.get("url") or "").lower() or needle in str(item.get("title") or "").lower()
            ]
        pages = [item for item in pages if not str(item.get("url") or "").startswith("devtools://")] or pages
        pages.sort(key=self._cdp_target_score, reverse=True)
        if not pages:
            raise RuntimeError(
                f"No DevTools page targets were available on {self._cdp_base_url(port)}. "
                "Use open_debug_page first, or pass the correct port."
            )
        return pages[0]

    @staticmethod
    def _cdp_target_score(target: Dict[str, Any]) -> int:
        url = str(target.get("url") or "").strip().lower()
        title = str(target.get("title") or "").strip()
        score = 0
        if url.startswith(("http://", "https://")):
            score += 100
        elif url and url not in {"about:blank", "chrome://newtab/"}:
            score += 30
        if title:
            score += 10
        if str(target.get("type") or "").lower() == "page":
            score += 5
        if target.get("webSocketDebuggerUrl"):
            score += 5
        if url.startswith(("devtools://", "chrome-extension://")):
            score -= 100
        if url in {"about:blank", "chrome://newtab/"}:
            score -= 20
        return score

    @staticmethod
    def _safe_cdp_call(cdp: _CdpConnection, method: str, params: Optional[Dict[str, Any]] = None, *, timeout: float = 5.0) -> Dict[str, Any]:
        try:
            return cdp.call(method, params or {}, timeout=timeout)
        except Exception:
            return {}

    @staticmethod
    def _format_cdp_remote_object(remote: Dict[str, Any]) -> str:
        if not isinstance(remote, dict):
            return str(remote)
        if "unserializableValue" in remote:
            return str(remote.get("unserializableValue"))
        if "value" in remote:
            value = remote.get("value")
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False, indent=2)
            return str(value)
        if remote.get("description"):
            return str(remote.get("description"))
        if remote.get("type"):
            return str(remote.get("type"))
        return ""

    @staticmethod
    def _format_cdp_exception(details: Dict[str, Any]) -> str:
        exception = details.get("exception") if isinstance(details, dict) else None
        if isinstance(exception, dict):
            description = exception.get("description") or exception.get("value")
            if description:
                return str(description)
        text = details.get("text") if isinstance(details, dict) else ""
        line = details.get("lineNumber") if isinstance(details, dict) else None
        column = details.get("columnNumber") if isinstance(details, dict) else None
        suffix = f" at {line}:{column}" if line is not None and column is not None else ""
        return (str(text or "unknown exception") + suffix).strip()

    @classmethod
    def _render_cdp_console_events(cls, events: Sequence[Dict[str, Any]], *, max_events: int = 80) -> List[str]:
        lines: List[str] = []
        limit = max(1, int(max_events or 80))
        for event in events:
            method = str(event.get("method") or "")
            params = event.get("params") or {}
            if method == "Runtime.consoleAPICalled":
                level = str(params.get("type") or "console")
                args = [
                    cls._format_cdp_remote_object(arg)
                    for arg in (params.get("args") or [])
                    if isinstance(arg, dict)
                ]
                lines.append(f"- console.{level}: {' '.join(arg for arg in args if arg)}".rstrip())
            elif method == "Runtime.exceptionThrown":
                lines.append(f"- exception: {cls._format_cdp_exception(params.get('exceptionDetails') or {})}")
            elif method == "Log.entryAdded":
                entry = params.get("entry") or {}
                level = entry.get("level") or "log"
                text = entry.get("text") or entry.get("url") or ""
                source = entry.get("source") or "unknown"
                lines.append(f"- {source}.{level}: {text}")
            if len(lines) >= limit:
                lines.append(f"- [truncated at {limit} rendered console/log events]")
                break
        return lines

    @classmethod
    def _summarize_cdp_network_events(cls, events: Sequence[Dict[str, Any]], *, max_events: int = 120) -> Dict[str, Any]:
        requests_by_id: Dict[str, Dict[str, Any]] = {}
        responses_by_id: Dict[str, Dict[str, Any]] = {}
        failures: List[Dict[str, Any]] = []
        finished: set[str] = set()
        for event in events:
            method = str(event.get("method") or "")
            params = event.get("params") or {}
            request_id = str(params.get("requestId") or "")
            if not request_id:
                continue
            if method == "Network.requestWillBeSent":
                request = params.get("request") or {}
                requests_by_id[request_id] = {
                    "request_id": request_id,
                    "url": request.get("url") or "",
                    "method": request.get("method") or "GET",
                    "resource_type": params.get("type") or "",
                    "document_url": params.get("documentURL") or "",
                }
            elif method == "Network.responseReceived":
                response = params.get("response") or {}
                request = requests_by_id.get(request_id) or {}
                responses_by_id[request_id] = {
                    "request_id": request_id,
                    "url": response.get("url") or request.get("url") or "",
                    "method": request.get("method") or "",
                    "status": int(response.get("status") or 0),
                    "status_text": response.get("statusText") or "",
                    "mime_type": response.get("mimeType") or "",
                    "resource_type": params.get("type") or request.get("resource_type") or "",
                    "headers": response.get("headers") or {},
                }
            elif method == "Network.loadingFailed":
                request = requests_by_id.get(request_id) or {}
                failures.append(
                    {
                        "request_id": request_id,
                        "url": request.get("url") or "",
                        "method": request.get("method") or "",
                        "resource_type": request.get("resource_type") or params.get("type") or "",
                        "error_text": params.get("errorText") or "failed",
                    }
                )
            elif method == "Network.loadingFinished":
                finished.add(request_id)

        responses = list(responses_by_id.values())[: max(1, int(max_events or 120))]
        for item in responses:
            item["finished"] = item.get("request_id") in finished
        return {
            "request_count": len(requests_by_id),
            "response_count": len(responses_by_id),
            "failure_count": len(failures),
            "requests": list(requests_by_id.values())[: max(1, int(max_events or 120))],
            "responses": responses,
            "failures": failures[: max(1, int(max_events or 120))],
            "events": list(events)[: max(1, int(max_events or 120))],
        }

    @classmethod
    def _attach_cdp_response_bodies(
        cls,
        cdp: _CdpConnection,
        responses: List[Dict[str, Any]],
        *,
        max_body_chars: int,
        timeout: float = 3.0,
    ) -> None:
        limit = max(1, int(max_body_chars or 2000))
        for item in responses[:20]:
            request_id = str(item.get("request_id") or "")
            if not request_id:
                continue
            try:
                result = cdp.call("Network.getResponseBody", {"requestId": request_id}, timeout=timeout)
                body = str(result.get("body") or "")
                if result.get("base64Encoded"):
                    try:
                        body = base64.b64decode(body).decode("utf-8", errors="replace")
                    except Exception:
                        body = "[base64 response body omitted]"
                item["body_preview"] = body[:limit]
                item["body_truncated"] = len(body) > limit
            except Exception as exc:
                item["body_error"] = str(exc)

    @staticmethod
    def _render_cdp_network_summary(summary: Dict[str, Any], *, target: Dict[str, Any]) -> str:
        lines = [
            f"DevTools network events for {target.get('title') or '(untitled)'}",
            f"URL: {target.get('url') or '(empty)'}",
            (
                "Counts: "
                f"requests={summary.get('request_count', 0)}, "
                f"responses={summary.get('response_count', 0)}, "
                f"failures={summary.get('failure_count', 0)}"
            ),
        ]
        responses = list(summary.get("responses") or [])
        if responses:
            lines.append("\nResponses:")
            for item in responses[:60]:
                method = item.get("method") or ""
                status = item.get("status") or 0
                resource_type = item.get("resource_type") or ""
                mime_type = item.get("mime_type") or ""
                lines.append(f"- {status} {method} {item.get('url') or ''} [{resource_type} {mime_type}]".strip())
                if item.get("body_preview"):
                    lines.append("  Body Preview:\n" + str(item.get("body_preview")))
                elif item.get("body_error"):
                    lines.append(f"  Body unavailable: {item.get('body_error')}")
        failures = list(summary.get("failures") or [])
        if failures:
            lines.append("\nFailures:")
            for item in failures[:40]:
                lines.append(f"- {item.get('method') or ''} {item.get('url') or ''}: {item.get('error_text') or 'failed'}")
        return "\n".join(lines).strip()

    def _vk_for_key(self, key: Any) -> int:
        text = str(key or "").strip().lower()
        if not text:
            raise ValueError("empty key")
        if text in VK_CODES:
            return int(VK_CODES[text])
        if len(text) == 1:
            char = text.upper()
            if "A" <= char <= "Z" or "0" <= char <= "9":
                return ord(char)
        raise ValueError(f"Unsupported key: {key}")

    def _send_key(self, key: Any) -> None:
        vk = self._vk_for_key(key)
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    def _send_hotkey(self, keys: Sequence[Any]) -> None:
        vks = [self._vk_for_key(key) for key in keys]
        for vk in vks:
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
        for vk in reversed(vks):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

    def _get_clipboard_text(self) -> str:
        self._require_windows_desktop()
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            locked = kernel32.GlobalLock(handle)
            if not locked:
                return ""
            try:
                return ctypes.wstring_at(locked) if ctypes is not None else ""
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def _set_clipboard_text(self, text: str) -> None:
        self._require_windows_desktop()
        data = (str(text or "") + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError("GlobalAlloc failed while setting clipboard text")
        locked = kernel32.GlobalLock(handle)
        if not locked:
            raise RuntimeError("GlobalLock failed while setting clipboard text")
        ctypes.memmove(locked, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(None):
            raise RuntimeError("OpenClipboard failed")
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                raise RuntimeError("SetClipboardData failed")
            handle = None
        finally:
            user32.CloseClipboard()

    def _resolve_browser_executable(self, *, browser: str = "default", browser_path: str = "") -> Optional[Path]:
        explicit = Path(browser_path).expanduser() if browser_path else None
        if explicit and explicit.exists() and explicit.is_file():
            return explicit.resolve()

        browser_key = str(browser or "default").strip().lower()
        if browser_key in {"", "default", "system"}:
            default_path = self._default_windows_browser_path()
            if default_path:
                return default_path

        aliases = {
            "chrome": ["chrome", "chrome.exe"],
            "google": ["chrome", "chrome.exe"],
            "edge": ["msedge", "msedge.exe"],
            "msedge": ["msedge", "msedge.exe"],
            "firefox": ["firefox", "firefox.exe"],
            "brave": ["brave", "brave.exe", "brave-browser"],
        }
        names = aliases.get(browser_key, aliases.get("chrome", []))
        for name in names:
            found = shutil.which(name)
            if found:
                return Path(found).resolve()

        if IS_WINDOWS:
            for candidate in self._common_windows_browser_paths(browser_key):
                if candidate.exists() and candidate.is_file():
                    return candidate.resolve()
        return None

    def _default_windows_browser_path(self) -> Optional[Path]:
        if not IS_WINDOWS or winreg is None:
            return None
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
            ) as key:
                prog_id = str(winreg.QueryValueEx(key, "ProgId")[0] or "").strip()
        except Exception:
            prog_id = ""
        if not prog_id:
            return None

        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"Software\Classes\{prog_id}\shell\open\command") as key:
                    command = str(winreg.QueryValueEx(key, "")[0] or "")
            except Exception:
                continue
            path = self._browser_path_from_command(command)
            if path:
                return path
        return None

    @staticmethod
    def _browser_path_from_command(command: str) -> Optional[Path]:
        text = str(command or "").strip()
        if not text:
            return None
        match = re.search(r'"([^"]+?\.exe)"', text, flags=re.IGNORECASE)
        if not match:
            match = re.search(r"([A-Za-z]:\\[^\"]+?\.exe)", text, flags=re.IGNORECASE)
        if not match:
            return None
        candidate = Path(match.group(1)).expanduser()
        return candidate.resolve() if candidate.exists() and candidate.is_file() else None

    @staticmethod
    def _common_windows_browser_paths(browser_key: str) -> List[Path]:
        program_files = [
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        suffixes = {
            "chrome": [r"Google\Chrome\Application\chrome.exe"],
            "google": [r"Google\Chrome\Application\chrome.exe"],
            "edge": [r"Microsoft\Edge\Application\msedge.exe"],
            "msedge": [r"Microsoft\Edge\Application\msedge.exe"],
            "firefox": [r"Mozilla Firefox\firefox.exe"],
            "brave": [r"BraveSoftware\Brave-Browser\Application\brave.exe"],
            "default": [
                r"Microsoft\Edge\Application\msedge.exe",
                r"Google\Chrome\Application\chrome.exe",
                r"Mozilla Firefox\firefox.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe",
            ],
        }
        selected_suffixes = suffixes.get(browser_key, suffixes["default"])
        candidates: List[Path] = []
        for root in program_files:
            if not root:
                continue
            for suffix in selected_suffixes:
                candidates.append(Path(root) / suffix)
        return candidates

    @staticmethod
    def _browser_window_flags(executable: Path, *, private: bool, new_window: bool) -> List[str]:
        name = executable.name.lower()
        flags: List[str] = []
        if private:
            if "firefox" in name:
                flags.append("-private-window")
            elif "msedge" in name:
                flags.append("--inprivate")
            else:
                flags.append("--incognito")
        if new_window and "firefox" not in name:
            flags.append("--new-window")
        return flags

    def _persist_text(self, stem: str, text: str) -> Path:
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(stem or "page").strip()).strip("-._") or "page"
        path = self.pages_dir / f"{safe_stem}-{int(time.time() * 1000)}.txt"
        path.write_text(str(text or ""), encoding="utf-8")
        return path

    def _persist_page_artifacts(self, url: str, html: str, text: str) -> Dict[str, str]:
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(url or "page")).strip("-._")[:80] or "page"
        timestamp = int(time.time() * 1000)
        html_path = self.pages_dir / f"{stem}-{timestamp}.html"
        text_path = self.pages_dir / f"{stem}-{timestamp}.txt"
        html_path.write_text(str(html or ""), encoding="utf-8")
        text_path.write_text(str(text or ""), encoding="utf-8")
        return {"html_path": str(html_path), "text_path": str(text_path)}

    @staticmethod
    def _summarize_html(url: str, html: str, *, include_links: bool = True) -> Dict[str, Any]:
        soup = BeautifulSoup(html or "", "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        meta_description = ""
        meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if meta and meta.get("content"):
            meta_description = str(meta.get("content") or "").strip()
        headings = []
        for tag in soup.find_all(re.compile("^h[1-6]$"))[:80]:
            text = tag.get_text(" ", strip=True)
            if text:
                headings.append({"level": tag.name.upper(), "text": text})
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        links: List[Dict[str, str]] = []
        images: List[Dict[str, str]] = []
        forms: List[Dict[str, Any]] = []
        if include_links:
            for link in soup.find_all("a", href=True)[:120]:
                label = link.get_text(" ", strip=True)
                href = str(link.get("href") or "").strip()
                if href:
                    links.append({"text": label[:160], "href": href})
            for image in soup.find_all("img")[:80]:
                src = str(image.get("src") or "").strip()
                if src:
                    images.append({"alt": str(image.get("alt") or "").strip()[:160], "src": src})
            for form in soup.find_all("form")[:20]:
                inputs = []
                for field in form.find_all(["input", "textarea", "select"])[:40]:
                    inputs.append(
                        {
                            "tag": field.name,
                            "name": str(field.get("name") or "").strip(),
                            "type": str(field.get("type") or "").strip(),
                        }
                    )
                forms.append(
                    {
                        "method": str(form.get("method") or "get").upper(),
                        "action": str(form.get("action") or "").strip(),
                        "inputs": inputs,
                    }
                )

        return {
            "url": url,
            "title": title,
            "meta_description": meta_description,
            "headings": headings,
            "text": text,
            "links": links,
            "images": images,
            "forms": forms,
        }

    @staticmethod
    def _build_page_diagnostics(url: str, response: requests.Response, summary: Dict[str, Any]) -> Dict[str, Any]:
        headers = dict(getattr(response, "headers", {}) or {})
        status_code = int(getattr(response, "status_code", 0) or 0)
        content_type = headers.get("content-type", headers.get("Content-Type", ""))
        text = str(summary.get("text", "") or "")
        forms = list(summary.get("forms") or [])
        links = list(summary.get("links") or [])
        images = list(summary.get("images") or [])
        warnings: List[str] = []

        if status_code >= 400:
            warnings.append(f"HTTP status is {status_code}.")
        if "text/html" not in str(content_type).lower():
            warnings.append(f"Content-Type is not HTML: {content_type or '(missing)'}.")
        if not str(summary.get("title", "") or "").strip():
            warnings.append("Page title is missing.")
        if not text.strip():
            warnings.append("Extracted page text is empty.")
        if forms:
            missing_actions = [form for form in forms if not str(form.get("action", "") or "").strip()]
            if missing_actions:
                warnings.append(f"{len(missing_actions)} form(s) have no action attribute.")

        return {
            "url": getattr(response, "url", url),
            "requested_url": url,
            "status_code": status_code,
            "ok": 200 <= status_code < 400,
            "content_type": content_type,
            "headers": headers,
            "title": summary.get("title", ""),
            "meta_description": summary.get("meta_description", ""),
            "heading_count": len(summary.get("headings") or []),
            "link_count": len(links),
            "image_count": len(images),
            "form_count": len(forms),
            "text_chars": len(text),
            "warnings": warnings,
        }

    @staticmethod
    def _asset_urls_from_html(page_url: str, html: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html or "", "html.parser")
        assets: List[Dict[str, str]] = []

        def add(kind: str, raw_url: Any) -> None:
            raw = str(raw_url or "").strip()
            if not raw or raw.startswith(("data:", "javascript:", "mailto:", "#")):
                return
            absolute = urljoin(page_url, raw)
            if not absolute.startswith(("http://", "https://")):
                return
            assets.append({"kind": kind, "url": absolute})

        for node in soup.find_all("script", src=True):
            add("script", node.get("src"))
        for node in soup.find_all("link", href=True):
            rel = " ".join(str(part).lower() for part in (node.get("rel") or []))
            kind = "stylesheet" if "stylesheet" in rel else "link"
            add(kind, node.get("href"))
        for node in soup.find_all("img", src=True):
            add("image", node.get("src"))

        deduped: List[Dict[str, str]] = []
        seen: set[str] = set()
        for item in assets:
            key = item["url"]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @classmethod
    def _check_page_assets(cls, page_url: str, html: str, *, timeout: float = 20.0, limit: int = 40) -> Dict[str, Any]:
        assets = cls._asset_urls_from_html(page_url, html)[: max(1, int(limit))]
        checks: List[Dict[str, Any]] = []
        for item in assets:
            asset_url = item["url"]
            try:
                response = requests.head(
                    asset_url,
                    timeout=max(1.0, float(timeout)),
                    allow_redirects=True,
                    headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
                )
                if response.status_code in {405, 501}:
                    response = requests.get(
                        asset_url,
                        timeout=max(1.0, float(timeout)),
                        allow_redirects=True,
                        stream=True,
                        headers={"User-Agent": "ReverieCLI-BrowserControler/1.0"},
                    )
                checks.append(
                    {
                        "kind": item["kind"],
                        "url": asset_url,
                        "status_code": int(response.status_code),
                        "ok": 200 <= int(response.status_code) < 400,
                        "content_type": response.headers.get("content-type", ""),
                    }
                )
            except Exception as exc:
                checks.append(
                    {
                        "kind": item["kind"],
                        "url": asset_url,
                        "status_code": 0,
                        "ok": False,
                        "error": str(exc),
                    }
                )
        broken = [item for item in checks if not item.get("ok")]
        return {
            "checked": len(checks),
            "broken": len(broken),
            "items": checks,
        }

    @staticmethod
    def _render_page_diagnostics(diagnostics: Dict[str, Any], summary: Dict[str, Any], *, max_chars: int) -> str:
        lines = [
            f"URL: {diagnostics.get('url', '')}",
            f"Status: {diagnostics.get('status_code')} {'OK' if diagnostics.get('ok') else 'FAILED'}",
            f"Content-Type: {diagnostics.get('content_type') or '(missing)'}",
            f"Title: {diagnostics.get('title') or '(missing)'}",
            (
                "Counts: "
                f"headings={diagnostics.get('heading_count', 0)}, "
                f"links={diagnostics.get('link_count', 0)}, "
                f"images={diagnostics.get('image_count', 0)}, "
                f"forms={diagnostics.get('form_count', 0)}, "
                f"text_chars={diagnostics.get('text_chars', 0)}"
            ),
        ]
        warnings = list(diagnostics.get("warnings") or [])
        if warnings:
            lines.append("\nWarnings:")
            lines.extend(f"- {item}" for item in warnings)

        asset_checks = diagnostics.get("asset_checks")
        if isinstance(asset_checks, dict):
            lines.append(
                f"\nAsset Checks: checked={asset_checks.get('checked', 0)}, broken={asset_checks.get('broken', 0)}"
            )
            broken_items = [item for item in (asset_checks.get("items") or []) if not item.get("ok")]
            for item in broken_items[:20]:
                status = item.get("status_code") or item.get("error") or "failed"
                lines.append(f"- {item.get('kind')}: {status} {item.get('url')}")

        lines.append("\nPage Summary:")
        lines.append(BrowserControlerTool._render_page_summary(summary, max_chars=max_chars))
        return "\n".join(lines).strip()

    @staticmethod
    def _render_page_summary(summary: Dict[str, Any], *, max_chars: int) -> str:
        lines = [
            f"URL: {summary.get('url', '')}",
            f"Title: {summary.get('title', '')}",
        ]
        if summary.get("meta_description"):
            lines.append(f"Description: {summary.get('meta_description')}")
        headings = summary.get("headings") or []
        if headings:
            lines.append("\nHeadings:")
            for heading in headings[:30]:
                lines.append(f"- {heading.get('level')}: {heading.get('text')}")
        if summary.get("links"):
            lines.append("\nLinks:")
            for link in (summary.get("links") or [])[:40]:
                label = str(link.get("text") or "").strip() or "(no text)"
                lines.append(f"- {label}: {link.get('href')}")
        if summary.get("forms"):
            lines.append("\nForms:")
            for form in (summary.get("forms") or [])[:10]:
                lines.append(f"- {form.get('method')} {form.get('action')} inputs={len(form.get('inputs') or [])}")

        text = str(summary.get("text") or "")
        clipped = text[: max(1, int(max_chars))]
        lines.append("\nPage Text:\n" + clipped)
        if len(text) > len(clipped):
            lines.append("\n[page text truncated in tool output]")
        return "\n".join(lines).strip()
