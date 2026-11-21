"""Reverie's private pipe protocol for the compiled Context Engine."""

import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import RLock, Thread
from typing import Any, Iterable, Optional


class NativeContextError(RuntimeError):
    pass


def executable_name() -> str:
    return "reverie-context-engine.exe" if os.name == "nt" else "reverie-context-engine"


def database_argument(path) -> str:
    """Give SQLite a Windows extended path while keeping stored workspace identities stable."""
    value = os.fspath(path)
    if os.name != "nt" or value == ":memory:":
        return value
    value = os.path.abspath(value)
    if value.startswith("\\\\?\\"):
        return value
    return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value


def find_executable() -> Optional[Path]:
    name = executable_name()
    if getattr(sys, "frozen", False):
        candidate = Path(__file__).resolve().parent / "native" / name
        return candidate if candidate.is_file() else None
    source_root = Path(__file__).resolve().parents[2]
    candidates = (
        source_root / "build" / "context-engine" / "release" / name,
        source_root / "native" / "context-engine" / "target" / "release" / name,
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _read_responses(stream, responses: Queue) -> None:
    try:
        for line in stream:
            responses.put(line)
    finally:
        responses.put(None)


class NativeContext:
    PROTOCOL = 1
    BATCH_CHARACTERS = 2 * 1024 * 1024

    def __init__(self, executable: Path, root: Path, cache_dir: Path):
        self.executable = Path(executable).resolve()
        self.root = root
        self.identity = os.path.normcase(str(root))
        self.database = Path(cache_dir).resolve() / "native-search.sqlite3"
        self.revision: Optional[int] = None
        self._lock = RLock()
        self._process: Optional[subprocess.Popen] = None
        self._responses: Queue = Queue()
        self._closed = False
        self._pending = []
        self._removed = []
        self._pending_characters = 0
        self.writing = False

    def _start(self) -> None:
        self._responses = Queue()
        self._process = subprocess.Popen(
            [str(self.executable), "serve", database_argument(self.database)],
            cwd=self.executable.parent,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        Thread(target=_read_responses, args=(self._process.stdout, self._responses), daemon=True).start()
        hello = self._exchange("hello")
        if hello.get("protocol") != self.PROTOCOL:
            raise NativeContextError("The bundled Context Engine uses an incompatible protocol")

    def _exchange(self, operation: str, **fields) -> Any:
        process = self._process
        try:
            message = json.dumps({"op": operation, **fields}, ensure_ascii=False, separators=(",", ":"))
            process.stdin.write(message + "\n")
            process.stdin.flush()
            line = self._responses.get(timeout=90)
            if line is None:
                raise OSError("worker exited")
            response = json.loads(line)
        except (Empty, OSError, UnicodeError, ValueError) as error:
            self._stop()
            raise NativeContextError(f"Context Engine worker failed during {operation}") from error
        if "error" in response:
            raise NativeContextError(response["error"])
        if "result" not in response:
            self._stop()
            raise NativeContextError("Invalid Context Engine response")
        return response["result"]

    def request(self, operation: str, **fields) -> Any:
        with self._lock:
            if self._closed:
                raise NativeContextError("Context Engine worker has been closed")
            if self._process is None:
                try:
                    self._start()
                except (OSError, NativeContextError) as error:
                    self._stop()
                    raise NativeContextError("Could not start the Rust Context Engine") from error
            return self._exchange(operation, **fields)

    def _stop(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdout.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._stop()

    def attach(self, revision: Optional[int]) -> bool:
        if not revision or not self.database.is_file():
            return False
        state = self.request("state")
        if state != {"root": self.identity, "revision": revision}:
            return False
        self.revision = revision
        return True

    def scan(self, rules: Iterable[str], extensions: Iterable[str], *, incremental: bool) -> tuple:
        fields = {"root": str(self.root), "options": {"extensions": sorted(extensions), "rules": list(rules)}}
        if incremental:
            return self.request("changes", expected_revision=self.revision, **fields)
        return self.request("scan", **fields), []

    def begin(self, *, replace: bool, expected_revision: int) -> None:
        self.request("begin", root=self.identity, replace=replace, expected_revision=expected_revision)
        self.writing = True

    def remove(self, path: Path) -> None:
        if self._closed:
            raise NativeContextError("Context Engine worker has been closed")
        relative = path.relative_to(self.root).as_posix()
        self._removed.append(relative)

    def document(self, path: Path, size: int, modified_ns: int, body: Optional[str], symbols=()) -> None:
        if self._closed:
            raise NativeContextError("Context Engine worker has been closed")
        chunks = []
        cost = len(body or "")
        for symbol in list(symbols)[:512] if body is not None else ():
            signature = str(symbol.signature or "")[:4096]
            documentation = str(symbol.docstring or "")[:8192]
            source = str(symbol.source_code or "")
            if len(source) > 49_152:
                source = source[:36_864] + "\n...\n" + source[-8192:]
            chunks.append({
                "name": symbol.name, "symbol": symbol.qualified_name or symbol.name,
                "kind": symbol.kind.name, "start_line": max(1, symbol.start_line or 1),
                "end_line": max(1, symbol.end_line or symbol.start_line or 1),
                "signature": signature, "documentation": documentation, "body": source,
            })
            cost += len(signature) + len(documentation) + len(source) + 128
        self._pending.append({
            "path": path.relative_to(self.root).as_posix(), "size": size,
            "modified_ns": modified_ns, "body": body, "chunks": chunks,
        })
        self._pending_characters += cost + 128
        if self._pending_characters >= self.BATCH_CHARACTERS:
            self.flush()

    def flush(self) -> None:
        if self._pending or self._removed:
            self.request("apply", removed=self._removed, documents=self._pending)
            self._pending.clear()
            self._removed.clear()
            self._pending_characters = 0

    def commit(self) -> None:
        self.flush()
        state = self.request("commit")
        self.revision = state["revision"]
        self.writing = False

    def rollback(self) -> None:
        self._pending.clear()
        self._removed.clear()
        self._pending_characters = 0
        if self.writing:
            self.writing = False
            if self._process is not None:
                self.request("rollback")

    def hits(self, weights: list, limit: int, *, chunks: bool) -> Optional[list]:
        if not self.revision:
            return None
        hits = self.request("search", weights=weights, limit=max(1, limit), chunks=chunks, expected_revision=self.revision)
        for hit in hits:
            hit["file_path"] = str(self.root / hit["file_path"])
        return hits
