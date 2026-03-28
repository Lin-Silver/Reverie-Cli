"""
Optional Language Server Protocol integration.

This is a lightweight stdio JSON-RPC bridge that discovers locally installed
language servers and exposes a small set of high-value capabilities for the
Context Engine: workspace symbols, document symbols, go-to-definition, and
diagnostics.
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class LSPServerDefinition:
    """Static language-server launch metadata."""

    key: str
    language_id: str
    extensions: Tuple[str, ...]
    command: Tuple[str, ...]


SERVER_DEFINITIONS: Tuple[LSPServerDefinition, ...] = (
    LSPServerDefinition("python", "python", (".py", ".pyi", ".pyw"), ("pyright-langserver", "--stdio")),
    LSPServerDefinition("python-pylsp", "python", (".py", ".pyi", ".pyw"), ("pylsp",)),
    LSPServerDefinition("typescript", "typescript", (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"), ("typescript-language-server", "--stdio")),
    LSPServerDefinition("go", "go", (".go",), ("gopls",)),
    LSPServerDefinition("rust", "rust", (".rs",), ("rust-analyzer",)),
    LSPServerDefinition("cpp", "cpp", (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"), ("clangd", "--stdio")),
)


class LSPClient:
    """Minimal blocking JSON-RPC client for one language server."""

    @staticmethod
    def _resolve_launch_command(command: Tuple[str, ...]) -> List[str]:
        executable = str(command[0]).strip()
        resolved = shutil.which(executable)
        if resolved:
            return [resolved, *command[1:]]

        executable_path = Path(executable)
        if executable_path.exists():
            return [str(executable_path), *command[1:]]

        raise FileNotFoundError(f"LSP server binary not found: {executable}")

    def __init__(self, project_root: Path, definition: LSPServerDefinition):
        self.project_root = Path(project_root).resolve()
        self.definition = definition
        launch_command = self._resolve_launch_command(definition.command)
        self._process = subprocess.Popen(
            launch_command,
            cwd=str(self.project_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._response_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._pending: Dict[int, "queue.Queue[Dict[str, Any]]"] = {}
        self._diagnostics: Dict[str, List[Dict[str, Any]]] = {}
        self._request_id = 0
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()
        self._opened_versions: Dict[str, int] = {}
        self._opened_mtimes: Dict[str, float] = {}
        self._initialize()

    def _initialize(self) -> None:
        self.request(
            "initialize",
            {
                "processId": None,
                "rootUri": self.project_root.as_uri(),
                "capabilities": {
                    "workspace": {"symbol": {"dynamicRegistration": False}},
                    "textDocument": {
                        "definition": {"dynamicRegistration": False},
                        "documentSymbol": {"dynamicRegistration": False},
                        "publishDiagnostics": {"relatedInformation": True},
                    },
                },
            },
            timeout=12.0,
        )
        self.notify("initialized", {})

    def shutdown(self) -> None:
        """Best-effort shutdown."""
        try:
            self.request("shutdown", None, timeout=2.0)
        except Exception:
            pass
        try:
            self.notify("exit", None)
        except Exception:
            pass
        try:
            self._process.kill()
        except Exception:
            pass

    def _reader_loop(self) -> None:
        stdout = self._process.stdout
        if stdout is None:
            return

        while True:
            headers: Dict[str, str] = {}
            while True:
                line = stdout.readline()
                if not line:
                    return
                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    break
                if ":" in decoded:
                    key, value = decoded.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            try:
                length = int(headers.get("content-length", "0"))
            except ValueError:
                continue
            if length <= 0:
                continue

            payload = stdout.read(length)
            if not payload:
                return

            try:
                message = json.loads(payload.decode("utf-8", errors="replace"))
            except Exception:
                continue

            if not isinstance(message, dict):
                continue

            method = str(message.get("method", "") or "").strip()
            if method == "textDocument/publishDiagnostics":
                params = message.get("params", {})
                if isinstance(params, dict):
                    uri = str(params.get("uri", "") or "").strip()
                    diagnostics = params.get("diagnostics", [])
                    if uri:
                        self._diagnostics[uri] = diagnostics if isinstance(diagnostics, list) else []
                continue

            if "id" in message:
                try:
                    request_id = int(message["id"])
                except (TypeError, ValueError):
                    continue
                with self._pending_lock:
                    pending_queue = self._pending.pop(request_id, None)
                if pending_queue is None:
                    continue
                pending_queue.put(message)

    def _send(self, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        if self._process.stdin is None:
            raise RuntimeError("LSP stdin is unavailable")
        with self._write_lock:
            self._process.stdin.write(header + body)
            self._process.stdin.flush()

    def request(self, method: str, params: Any, timeout: float = 5.0) -> Any:
        waiter: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._request_id += 1
            request_id = self._request_id
            self._pending[request_id] = waiter
        try:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        except Exception:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise
        try:
            response = waiter.get(timeout=timeout)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"LSP request timed out: {method}") from exc
        if "error" in response:
            raise RuntimeError(f"LSP error for {method}: {response['error']}")
        return response.get("result")

    def notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def ensure_document_open(self, file_path: Path) -> None:
        resolved = Path(file_path).resolve()
        uri = resolved.as_uri()
        mtime = resolved.stat().st_mtime
        text = resolved.read_text(encoding="utf-8", errors="ignore")
        version = self._opened_versions.get(uri, 0) + 1

        text_document = {
            "uri": uri,
            "languageId": self.definition.language_id,
            "version": version,
            "text": text,
        }

        if uri not in self._opened_versions:
            self.notify("textDocument/didOpen", {"textDocument": text_document})
        elif self._opened_mtimes.get(uri) != mtime:
            self.notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": text}],
                },
            )

        self._opened_versions[uri] = version
        self._opened_mtimes[uri] = mtime

    def workspace_symbols(self, query: str) -> List[Dict[str, Any]]:
        result = self.request("workspace/symbol", {"query": str(query or "")}, timeout=8.0)
        return result if isinstance(result, list) else []

    def document_symbols(self, file_path: Path) -> List[Dict[str, Any]]:
        self.ensure_document_open(file_path)
        result = self.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": file_path.resolve().as_uri()}},
            timeout=8.0,
        )
        return result if isinstance(result, list) else []

    def definitions(self, file_path: Path, line: int, character: int) -> List[Dict[str, Any]]:
        self.ensure_document_open(file_path)
        result = self.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": file_path.resolve().as_uri()},
                "position": {"line": max(0, int(line)), "character": max(0, int(character))},
            },
            timeout=8.0,
        )
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
        return []

    def diagnostics(self, file_path: Path) -> List[Dict[str, Any]]:
        self.ensure_document_open(file_path)
        uri = file_path.resolve().as_uri()
        for _ in range(10):
            if uri in self._diagnostics:
                break
            time.sleep(0.15)
        return self._diagnostics.get(uri, [])


class LSPManager:
    """Discover and broker optional LSP capabilities for the workspace."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self._definitions = self._discover_definitions()
        self._clients: Dict[str, LSPClient] = {}

    def _create_client(self, definition: LSPServerDefinition) -> Optional[LSPClient]:
        client = self._clients.get(definition.key)
        if client is not None:
            return client
        try:
            client = LSPClient(self.project_root, definition)
        except FileNotFoundError:
            return None
        self._clients[definition.key] = client
        return client

    def _discover_definitions(self) -> Dict[str, LSPServerDefinition]:
        discovered: Dict[str, LSPServerDefinition] = {}
        covered_extensions: set[str] = set()
        for definition in SERVER_DEFINITIONS:
            executable = definition.command[0]
            if not shutil.which(executable):
                continue
            if any(ext in covered_extensions for ext in definition.extensions):
                continue
            discovered[definition.key] = definition
            covered_extensions.update(definition.extensions)
        return discovered

    def available_servers(self) -> List[Dict[str, Any]]:
        """Return available language-server metadata."""
        items: List[Dict[str, Any]] = []
        for definition in self._definitions.values():
            items.append(
                {
                    "key": definition.key,
                    "language_id": definition.language_id,
                    "extensions": list(definition.extensions),
                    "command": list(definition.command),
                }
            )
        return items

    def _definition_for_path(self, file_path: Path) -> Optional[LSPServerDefinition]:
        suffix = file_path.suffix.lower()
        for definition in self._definitions.values():
            if suffix in definition.extensions:
                return definition
        return None

    def _get_client(self, file_path: Path) -> Optional[LSPClient]:
        definition = self._definition_for_path(file_path)
        if not definition:
            return None
        return self._create_client(definition)

    def workspace_symbols(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for definition in self._definitions.values():
            client = self._create_client(definition)
            if client is None:
                continue
            try:
                symbols = client.workspace_symbols(query)
            except Exception:
                continue
            for item in symbols:
                if not isinstance(item, dict):
                    continue
                results.append(item)
                if len(results) >= limit:
                    return results
        return results

    def document_symbols(self, file_path: str) -> List[Dict[str, Any]]:
        path = (self.project_root / file_path).resolve() if not Path(file_path).is_absolute() else Path(file_path).resolve()
        client = self._get_client(path)
        if not client:
            return []
        try:
            return client.document_symbols(path)
        except Exception:
            return []

    def definitions(self, file_path: str, line: int, character: int) -> List[Dict[str, Any]]:
        path = (self.project_root / file_path).resolve() if not Path(file_path).is_absolute() else Path(file_path).resolve()
        client = self._get_client(path)
        if not client:
            return []
        try:
            return client.definitions(path, line, character)
        except Exception:
            return []

    def diagnostics(self, file_path: str) -> List[Dict[str, Any]]:
        path = (self.project_root / file_path).resolve() if not Path(file_path).is_absolute() else Path(file_path).resolve()
        client = self._get_client(path)
        if not client:
            return []
        try:
            return client.diagnostics(path)
        except Exception:
            return []

    def build_status_report(self) -> Dict[str, Any]:
        """Return a compact availability report for UI and retrieval."""
        return {
            "available": bool(self._definitions),
            "servers": self.available_servers(),
        }
