from __future__ import annotations

import ast
from hashlib import sha256
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import urlopen

import pytest


@pytest.fixture
def build_vocabulary(tmp_path):
    spec = ast.parse((Path(__file__).resolve().parents[1] / "reverie.spec").read_text(encoding="utf-8"))
    block = next(node for node in spec.body if isinstance(node, ast.If) and "read_vocabulary" in ast.unparse(node.test) and "tokenizer_file" in ast.unparse(node.test))
    functions = [node for node in spec.body if isinstance(node, ast.FunctionDef) and node.name == "download_vocabulary"]
    code = compile(ast.Module(body=[*functions, block], type_ignores=[]), "reverie.spec", "exec")
    data = b"verified vocabulary fixture\n"
    digest = sha256(data).hexdigest()
    target = tmp_path / "tokenizers/cl100k_base.tiktoken"

    def read(path):
        if path is None or not path.is_file():
            return None
        content = path.read_bytes()
        return content if sha256(content).hexdigest() == digest else None

    namespace = {
        "tokenizer": {"read_vocabulary": read, "cached_vocabulary_path": lambda: None,
                      "VOCABULARY_URL": "http://127.0.0.1/vocabulary", "VOCABULARY_SHA256": digest},
        "tokenizer_file": target, "sha256": sha256, "urlopen": urlopen,
        "IncompleteRead": IncompleteRead, "URLError": URLError, "os": os,
        "tempfile": tempfile, "Path": Path, "time": SimpleNamespace(sleep=lambda _seconds: None),
    }
    return SimpleNamespace(run=lambda: exec(code, namespace), namespace=namespace, target=target, data=data)


@pytest.mark.parametrize("error", [TimeoutError("read timed out"), URLError("temporary transport failure"), IncompleteRead(b"partial", 12)])
def test_transient_download_failure_retries_before_installing_verified_bytes(build_vocabulary, error):
    calls = []

    def request(url, timeout):
        calls.append((url, timeout))
        if len(calls) == 1:
            raise error
        return BytesIO(build_vocabulary.data)

    build_vocabulary.namespace["urlopen"] = request
    build_vocabulary.run()
    assert len(calls) == 2
    assert build_vocabulary.target.read_bytes() == build_vocabulary.data


def test_repeated_timeout_is_bounded_and_preserves_existing_file(build_vocabulary):
    build_vocabulary.target.parent.mkdir()
    build_vocabulary.target.write_bytes(b"existing incomplete vocabulary")
    calls = []

    def request(_url, timeout):
        calls.append(timeout)
        raise TimeoutError("read timed out")

    build_vocabulary.namespace["urlopen"] = request
    with pytest.raises(TimeoutError):
        build_vocabulary.run()
    assert len(calls) == 3
    assert build_vocabulary.target.read_bytes() == b"existing incomplete vocabulary"


def test_wrong_checksum_is_rejected_without_retry_or_replacing_existing_file(build_vocabulary):
    build_vocabulary.target.parent.mkdir()
    build_vocabulary.target.write_bytes(b"existing incomplete vocabulary")
    calls = []

    def request(_url, timeout):
        calls.append(timeout)
        return BytesIO(b"wrong vocabulary")

    build_vocabulary.namespace["urlopen"] = request
    with pytest.raises(SystemExit, match="checksum mismatch"):
        build_vocabulary.run()
    assert len(calls) == 1
    assert build_vocabulary.target.read_bytes() == b"existing incomplete vocabulary"


def test_verified_existing_vocabulary_needs_no_network_or_write(build_vocabulary):
    build_vocabulary.target.parent.mkdir()
    build_vocabulary.target.write_bytes(build_vocabulary.data)
    modified = build_vocabulary.target.stat().st_mtime_ns
    build_vocabulary.namespace["urlopen"] = lambda *_args, **_kwargs: pytest.fail("Unexpected download")
    build_vocabulary.run()
    assert build_vocabulary.target.stat().st_mtime_ns == modified


def test_failed_atomic_install_preserves_existing_file(build_vocabulary, monkeypatch):
    build_vocabulary.target.parent.mkdir()
    build_vocabulary.target.write_bytes(b"existing incomplete vocabulary")
    build_vocabulary.namespace["urlopen"] = lambda *_args, **_kwargs: BytesIO(build_vocabulary.data)

    def fail_replace(_source, _target):
        raise OSError("atomic switch unavailable")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="atomic switch unavailable"):
        build_vocabulary.run()
    assert build_vocabulary.target.read_bytes() == b"existing incomplete vocabulary"
    assert list(build_vocabulary.target.parent.iterdir()) == [build_vocabulary.target]


@pytest.mark.parametrize("first_response", ["unavailable", "truncated"])
def test_real_http_download_recovers_and_installs_complete_content(build_vocabulary, monkeypatch, first_response):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            calls.append(self.path)
            if len(calls) == 1 and first_response == "unavailable":
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(build_vocabulary.data)))
            self.end_headers()
            self.wfile.write(build_vocabulary.data[:5] if len(calls) == 1 else build_vocabulary.data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    build_vocabulary.namespace["tokenizer"]["VOCABULARY_URL"] = f"http://127.0.0.1:{server.server_port}/vocabulary"
    try:
        build_vocabulary.run()
        assert len(calls) == 2
        assert build_vocabulary.target.read_bytes() == build_vocabulary.data
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
