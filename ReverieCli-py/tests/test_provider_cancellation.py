from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import select
import threading
import time

import httpx
import pytest

from reverie.desktop_control import RunControl
from reverie.provider_transport import _wait, provider_client, provider_post, request_scope, interruptible_sleep


@pytest.fixture
def server():
    entered, disconnected, release = threading.Event(), threading.Event(), threading.Event()
    connections = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            connections.append(self.connection)

        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path in {"/events-length", "/events-chunked"}:
                data = b'data: {"choices": []}\n\ndata: [DONE]\n\n'
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length" if self.path.endswith("length") else "Transfer-Encoding", str(len(data)) if self.path.endswith("length") else "chunked")
                self.end_headers()
                self.wfile.write(data if self.path.endswith("length") else f"{len(data):x}\r\n".encode() + data + b"\r\n0\r\n\r\n")
                self.wfile.flush()
                return
            if self.path == "/quick":
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            if self.path != "/headers":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", "10000")
                self.end_headers()
                if self.path == "/stream":
                    self.wfile.write(b'data: {"choices": []}\n\n')
                    self.wfile.flush()
            entered.set()
            while not release.is_set():
                if select.select([self.connection], [], [], 0.05)[0]:
                    try:
                        closed = not self.connection.recv(1)
                    except ConnectionResetError:
                        closed = True
                    if closed:
                        disconnected.set()
                        break
            self.close_connection = True

    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    service.daemon_threads = True
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{service.server_port}", entered, disconnected, connections
    release.set()
    service.shutdown()
    service.server_close()
    thread.join(2)


@pytest.mark.parametrize("trial", range(3))
@pytest.mark.parametrize("transport", ["requests", "httpx", "openai", "anthropic", "curl"])
@pytest.mark.parametrize("phase", ["headers", "body", "stream"])
def test_stop_aborts_real_socket_before_headers_and_during_body(server, transport, phase, trial, record_property):
    url, entered, disconnected, _ = server
    control = RunControl(lambda _event: None)
    if transport == "curl":
        from reverie.agent.agent import _invoke_system_curl

    def request():
        with request_scope(control):
            if transport == "requests":
                response = provider_post(f"{url}/{phase}", json={}, stream=phase != "body", timeout=30, proxies={"http": None, "https": None})
                try:
                    if phase != "body":
                        list(response.iter_lines())
                finally:
                    response.close()
            elif transport == "httpx":
                with provider_client() as client, client.stream("POST", f"{url}/{phase}", json={}, timeout=30) as response:
                    list(response.iter_bytes())
            elif transport == "openai":
                from openai import OpenAI, Stream
                from openai.types.chat import ChatCompletionChunk
                with OpenAI(base_url=url, api_key="fixture", http_client=provider_client(), max_retries=0) as client:
                    response = client.post(f"/{phase}", cast_to=ChatCompletionChunk, body={}, stream=phase != "body", stream_cls=Stream[ChatCompletionChunk] if phase != "body" else None)
                    if phase != "body":
                        list(response)
            elif transport == "anthropic":
                from anthropic import Anthropic, Stream
                with Anthropic(base_url=url, api_key="fixture", http_client=provider_client(), max_retries=0) as client:
                    response = client.post(f"/{phase}", cast_to=dict, body={}, stream=phase != "body", stream_cls=Stream[dict] if phase != "body" else None)
                    if phase != "body":
                        list(response)
            else:
                response = _invoke_system_curl(url=f"{url}/{phase}", headers={}, payload={}, stream=phase != "body", timeout=30)
                try:
                    if phase != "body":
                        list(response.iter_lines())
                finally:
                    response.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(request)
        assert entered.wait(5)
        before = time.perf_counter()
        control.stop()
        with pytest.raises(Exception) as failure:
            future.result(timeout=1)
        assert time.perf_counter() - before < 1
        assert disconnected.wait(1), f"Stop must close the upstream socket: {failure.value!r}, callbacks={control._cancel_callbacks}"
        record_property("stop_and_disconnect_ms", round((time.perf_counter() - before) * 1000, 2))
    assert not control._cancel_callbacks


@pytest.mark.parametrize("transport", ["requests", "httpx"])
def test_new_client_objects_reuse_upstream_connection(server, transport):
    url, _, _, connections = server
    for _ in range(3):
        if transport == "requests":
            with provider_post(f"{url}/quick", json={}) as response:
                assert response.json() == {}
        else:
            with provider_client() as client:
                assert client.post(f"{url}/quick", json={}).json() == {}
    assert len(connections) == 1


@pytest.mark.parametrize("framing", ["length", "chunked"])
@pytest.mark.parametrize("transport", ["requests", "httpx", "openai"])
def test_stream_terminal_record_retains_keepalive_connection(server, transport, framing):
    url, _, _, connections = server
    for _ in range(3):
        if transport == "requests":
            with provider_post(f"{url}/events-{framing}", json={}, stream=True) as response:
                for line in response.iter_lines():
                    if line == b"data: [DONE]":
                        break
        elif transport == "httpx":
            with provider_client() as client, client.stream("POST", f"{url}/events-{framing}", json={}) as response:
                for line in response.iter_lines():
                    if line == "data: [DONE]":
                        break
        else:
            from openai import OpenAI, Stream
            from openai.types.chat import ChatCompletionChunk
            with OpenAI(base_url=url, api_key="fixture", http_client=provider_client(), max_retries=0) as client:
                response = client.post(f"/events-{framing}", cast_to=ChatCompletionChunk, body={}, stream=True, stream_cls=Stream[ChatCompletionChunk])
                list(response)
    assert len(connections) == 1


def test_early_stream_close_has_a_bound_even_when_peer_keeps_sending_nothing(server):
    url, _, disconnected, _ = server
    response = provider_post(f"{url}/stream", json={}, stream=True)
    iterator = response.iter_content(chunk_size=None)
    next(iterator)
    started = time.perf_counter()
    response.close()
    assert time.perf_counter() - started < 0.25
    assert disconnected.wait(1)


def test_stop_interrupts_retry_delay_and_cancel_registration_race():
    control = RunControl(lambda _event: None)
    control.stop()
    called = []
    release = control.on_cancel(lambda: called.append(True))
    release()
    assert called == [True]
    with request_scope(None):
        with pytest.raises(RuntimeError, match="stopped"):
            with request_scope(control):
                interruptible_sleep(30)


def test_stop_interrupts_an_already_waiting_retry():
    control = RunControl(lambda _event: None)
    entered = threading.Event()
    def sleep():
        with request_scope(control):
            entered.set()
            interruptible_sleep(30)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(sleep)
        assert entered.wait(1)
        control.stop()
        with pytest.raises(RuntimeError, match="stopped"):
            future.result(timeout=1)


@pytest.mark.parametrize("stopped", [False, True])
def test_completed_socket_error_preserves_cancellation_state(stopped):
    control = RunControl(lambda _event: None)

    async def failed_read():
        if stopped:
            # Socket shutdown can complete with an error before the future's
            # cancel callback runs, after stop has already set this event.
            control.cancelled.set()
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    error = RuntimeError if stopped else httpx.RemoteProtocolError
    message = "stopped" if stopped else "Server disconnected"
    with pytest.raises(error, match=message):
        _wait(failed_read(), control)
    assert not control._cancel_callbacks


@pytest.mark.parametrize("operation", ["compression", "codex-refresh", "codex-handoff"])
def test_preflight_provider_requests_also_stop_before_headers(server, operation, monkeypatch):
    url, entered, disconnected, _ = server
    control = RunControl(lambda _event: None)
    def request():
        with request_scope(control):
            if operation == "compression":
                from reverie.context_engine.compressor import make_compression_request_with_retry
                return make_compression_request_with_retry(f"{url}/headers", {}, {"model":"fixture", "messages":[{"role":"user", "content":"summarize"}]})
            if operation == "codex-handoff":
                from reverie.context_engine.handoff import _request_handoff_summary_text
                return _request_handoff_summary_text(client=None, model="fixture", provider="codex", base_url=url, api_key="fixture", session_id="fixture", custom_headers={}, prompt_messages=[{"role":"user", "content":"summarize"}])
            from reverie import codex
            return codex.refresh_codex_access_token("fixture-no-real-account")
    if operation == "codex-refresh":
        monkeypatch.setattr("reverie.codex.CODEX_TOKEN_URL", f"{url}/headers")
    if operation == "codex-handoff":
        monkeypatch.setattr("reverie.codex.detect_codex_cli_credentials", lambda: {})
        monkeypatch.setattr("reverie.codex.resolve_codex_request_url", lambda *_args: f"{url}/headers")
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(request)
        assert entered.wait(5)
        control.stop()
        with pytest.raises(RuntimeError, match="stopped"):
            future.result(timeout=1)
        assert disconnected.wait(1)
