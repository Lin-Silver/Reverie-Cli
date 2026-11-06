"""Session-scoped, bounded access to Reverie's bundled agent-desktop engine."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid


COMMANDS = frozenset('status version permissions list-apps list-windows list-displays list-surfaces snapshot find get is screenshot launch close-app focus-window resize-window move-window minimize maximize restore open-system-surface click double-click triple-click right-click focus set-value clear type select toggle check uncheck expand collapse press scroll scroll-to drag hover mouse-move mouse-click mouse-wheel wait clipboard-get clipboard-set clipboard-clear'.split())
READ_COMMANDS = frozenset('status version permissions list-apps list-windows list-displays list-surfaces snapshot find get is screenshot wait clipboard-get'.split())


class NativeDesktopError(RuntimeError):
    def __init__(self, envelope: dict):
        self.envelope = envelope
        super().__init__(envelope.get('error', {}).get('message', 'Computer Use failed'))


def failure(command: str, code: str, message: str, *, uncertain: bool = False) -> NativeDesktopError:
    return NativeDesktopError({'version': '2.6', 'ok': False, 'command': command, 'error': {
        'code': code, 'message': message,
        'disposition': {'delivery': 'unknown' if uncertain else 'not_delivered',
                        'retry': 'unsafe' if uncertain else 'safe'}}})


class ComputerUseRuntime:
    def __init__(self, data_dir: Path, *, binary: Path | None = None, control: Any = None):
        self.root = Path(data_dir).resolve() / 'computer_use'
        package = Path(__file__).resolve().parent
        self.binary = (binary or package / 'native' / 'windows-x64' / 'agent-desktop.exe').resolve()
        self.session_id = 'reverie-' + uuid.uuid4().hex
        self.control = control
        self.images: dict[str, dict] = {}
        self.legacy: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._verified = False
        self.metrics: list[dict] = []

    @staticmethod
    def decode(raw: str, command: str) -> dict:
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict) or envelope.get('version') != '2.6':
                raise ValueError('Expected JSON protocol 2.6')
            if not isinstance(envelope.get('ok'), bool):
                raise ValueError('Missing operation status')
            payload = envelope.get('data' if envelope['ok'] else 'error')
            if not isinstance(payload, (dict, list) if envelope['ok'] else dict):
                raise ValueError('Missing operation result')
        except (ValueError, TypeError) as exc:
            raise failure(command, 'INVALID_RESPONSE', f'Invalid native desktop response: {exc}', uncertain=command not in READ_COMMANDS) from exc
        if not envelope['ok']:
            raise NativeDesktopError(envelope)
        return envelope

    def _verify_binary(self) -> None:
        if self._verified:
            return
        if sys.platform != 'win32' or not self.binary.is_file():
            raise failure('status', 'ENGINE_UNAVAILABLE', 'Bundled Computer Use requires Windows x64. Build with scripts/prepare_computer_use.py or reinstall the complete Reverie package.')
        receipt_path = self.binary.parent / 'receipt.json'
        try:
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            manifest = json.loads((Path(__file__).parent / 'native_manifest.json').read_text(encoding='utf-8'))
            if (receipt.get('archive_sha256') != manifest['archive_sha256']
                    or hashlib.sha256(self.binary.read_bytes()).hexdigest() != manifest['binary_sha256']):
                raise ValueError('Native binary checksum mismatch')
        except (OSError, ValueError) as exc:
            raise failure('status', 'ENGINE_UNAVAILABLE', f'Native desktop integrity check failed: {exc}') from exc
        self._verified = True

    def command(self, command: str, args: list[str] | None = None, *, text: str | None = None,
                headed: bool = False, timeout_ms: int = 10000) -> dict:
        if command not in COMMANDS:
            raise failure(command, 'INVALID_ARGS', 'This native command is not exposed by Reverie.')
        with self._lock:
            self._verify_binary()
            self.check_cancel(command)
            self.root.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            for key in ('AGENT_DESKTOP_SESSION', 'AGENT_DESKTOP_AGENT_ID', 'AGENT_DESKTOP_HOME'):
                env.pop(key, None)
            env['AGENT_DESKTOP_HOME'] = str(self.root / 'native-state')
            argv = [str(self.binary), '--session', self.session_id]
            if headed:
                argv.append('--headed')
            argv.extend([command, *(args or [])])
            started = time.monotonic()
            try:
                process = subprocess.Popen(argv, cwd=self.root, env=env, stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError as exc:
                raise failure(command, 'ENGINE_UNAVAILABLE', f'Native desktop process could not start: {exc}') from exc
            mutation = command not in READ_COMMANDS
            release = None
            if self.control is not None and not mutation:
                release = self.control.on_cancel(lambda: process.terminate() if process.poll() is None else None)
            try:
                try:
                    stdout, _stderr = process.communicate(None if text is None else text.encode('utf-8'), timeout=max(0.1, timeout_ms / 1000) + 2)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.communicate()
                    raise failure(command, 'TIMEOUT', 'Native operation exceeded its deadline. Observe before another action.', uncertain=mutation) from exc
                if not mutation:
                    self.check_cancel(command)
                if not stdout:
                    raise failure(command, 'NATIVE_EXIT', f'Native process exited without a result (exit {process.returncode}). Observe before retrying.', uncertain=mutation)
                try:
                    raw = stdout.decode('utf-8')
                except UnicodeDecodeError as exc:
                    raise failure(command, 'INVALID_RESPONSE', 'Native desktop output was not valid UTF-8.', uncertain=mutation) from exc
                envelope = self.decode(raw, command)
                if process.returncode:
                    raise failure(command, 'NATIVE_EXIT', f'Native process exited abnormally (exit {process.returncode}). Observe before retrying.', uncertain=mutation)
                return envelope
            finally:
                if mutation:
                    self.images.clear()
                if release:
                    release()
                self.metrics.append({'command': command, 'elapsed_ms': round((time.monotonic() - started) * 1000, 2)})

    def check_cancel(self, command: str) -> None:
        if self.control is not None:
            try:
                self.control.check_cancel()
            except RuntimeError as exc:
                raise failure(command, 'CANCELLED', 'Run stopped before this operation was delivered.') from exc

    def close(self) -> None:
        self.images.clear()
        self.legacy.clear()
