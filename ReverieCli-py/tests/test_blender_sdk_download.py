"""Pinned SDK retrieval is atomic and rejects incorrect data before packaging."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
from threading import Thread

import pytest


@pytest.fixture
def builder():
    path = Path(__file__).resolve().parents[2] / "plugins" / "blender" / "build_plugin.py"
    spec = importlib.util.spec_from_file_location("blender_sdk_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source(builder, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    payload = b"SDK fixture with license materials"
    builder.ARCHIVE_SIZE = len(payload)
    builder.ARCHIVE_SHA256 = hashlib.sha256(payload).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        data = payload
        length = len(payload)

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(self.length))
            self.end_headers()
            self.wfile.write(self.data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    builder.ARCHIVE_URL = f"http://127.0.0.1:{server.server_port}/sdk.zip"
    yield Handler, payload
    server.shutdown()
    server.server_close()
    thread.join()


def test_sdk_download_validates_and_installs_one_complete_archive(tmp_path, builder, source):
    _, payload = source
    target = tmp_path / "sdk" / "blender.zip"
    assert builder.ensure_archive(target) == target
    assert target.read_bytes() == payload
    assert list(target.parent.iterdir()) == [target]
    assert builder.ensure_archive(target) == target


@pytest.mark.parametrize("failure", ["hash", "truncated", "oversized"])
def test_invalid_sdk_candidate_never_becomes_the_archive(tmp_path, builder, source, failure):
    handler, payload = source
    if failure == "hash":
        handler.data = b"X" * len(payload)
    elif failure == "truncated":
        handler.data = payload[:-3]
    else:
        handler.data = payload + b"too large"
        handler.length = len(handler.data)
    target = tmp_path / "sdk" / "blender.zip"
    message = {"hash": "SHA-256 mismatch", "truncated": "size mismatch", "oversized": "Content-Length mismatch"}[failure]
    with pytest.raises(ValueError, match=message):
        builder.ensure_archive(target)
    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_invalid_existing_sdk_is_retained_and_rejected(tmp_path, builder, source):
    target = tmp_path / "blender.zip"
    target.write_bytes(b"retain this existing file")
    with pytest.raises(ValueError):
        builder.ensure_archive(target)
    assert target.read_bytes() == b"retain this existing file"
