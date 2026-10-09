"""Pooled provider I/O with cancellation during connect, headers and body reads.

The SDKs keep their synchronous interfaces. Only socket I/O runs on one async
loop, so cancelling a future interrupts the socket instead of leaving a blocked
request thread running in the background.
"""
from __future__ import annotations

import asyncio
import atexit
from concurrent.futures import CancelledError
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time
import socket
from urllib.parse import urlsplit
from typing import Any

import httpx
import httpcore
import requests


_control: ContextVar[Any] = ContextVar("provider_run_control", default=None)
_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()
_transports: dict[tuple, httpcore.AsyncConnectionPool] = {}


@contextmanager
def request_scope(control):
    token = _control.set(control)
    try:
        if control is not None:
            control.check_cancel()
        yield
    finally:
        _control.reset(token)


def check_cancel() -> None:
    control = _control.get()
    if control is not None:
        control.check_cancel()


def on_cancel(callback):
    control = _control.get()
    return control.on_cancel(callback) if control is not None else lambda: None


def interruptible_sleep(seconds: float) -> None:
    control = _control.get()
    if control is None:
        time.sleep(seconds)
    else:
        control.cancelled.wait(max(0, seconds))
        control.check_cancel()


def _network_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="provider-io", daemon=True).start()
        return _loop


def _wait(coroutine, control=None):
    future = asyncio.run_coroutine_threadsafe(coroutine, _network_loop())
    release = control.on_cancel(future.cancel) if control is not None else lambda: None
    try:
        value = future.result()
        if control is not None and control.cancelled.is_set() and isinstance(value, httpx.Response):
            _wait(value.aclose())
        if control is not None:
            control.check_cancel()
        return value
    except CancelledError:
        if control is not None:
            control.check_cancel()
        raise
    finally:
        release()


class _NetworkStream(httpcore.AsyncNetworkStream):
    """Keep ownership from the first write until the response is closed."""
    def __init__(self, stream):
        self.stream = stream
        self.control = None
        self.release = lambda: None
        self.bind()

    def bind(self):
        control = _control.get()
        if self.control is not control:
            self.release()
            self.control = control
            self.release = control.on_cancel(self.abort) if control is not None else lambda: None

    def abort(self):
        raw_socket = self.stream.get_extra_info("socket")
        if raw_socket is not None:
            try:
                raw_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        asyncio.run_coroutine_threadsafe(self.aclose(), _network_loop())

    def release_cancel(self):
        self.release()
        self.control = None
        self.release = lambda: None

    async def read(self, max_bytes, timeout=None):
        self.bind()
        return await self.stream.read(max_bytes, timeout)

    async def write(self, buffer, timeout=None):
        self.bind()
        return await self.stream.write(buffer, timeout)

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.stream = await self.stream.start_tls(ssl_context, server_hostname, timeout)
        return self

    async def aclose(self):
        try:
            await self.stream.aclose()
        finally:
            self.release_cancel()

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)


class _NetworkBackend(httpcore.AnyIOBackend):
    async def connect_tcp(self, *args, **kwargs):
        return _NetworkStream(await super().connect_tcp(*args, **kwargs))

    async def connect_unix_socket(self, *args, **kwargs):
        return _NetworkStream(await super().connect_unix_socket(*args, **kwargs))


@contextmanager
def _core_errors():
    try:
        yield
    except (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError, httpcore.ProxyError, httpcore.UnsupportedProtocol) as exc:
        raise getattr(httpx, type(exc).__name__)(str(exc)) from exc


class _CoreStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        with _core_errors():
            async for chunk in self.stream:
                yield chunk

    async def aclose(self):
        with _core_errors():
            await self.stream.aclose()


def _pool(key):
    kwargs = dict(ssl_context=httpx.create_ssl_context(verify=key[1], cert=key[2], trust_env=False),
                  max_connections=32, max_keepalive_connections=16, keepalive_expiry=120,
                  network_backend=_NetworkBackend())
    if not key[0]:
        return httpcore.AsyncConnectionPool(**kwargs)
    proxy = httpx.Proxy(key[0])
    kwargs.update(proxy_url=str(proxy.url), proxy_auth=proxy.raw_auth)
    if proxy.url.scheme in {"socks5", "socks5h"}:
        return httpcore.AsyncSOCKSProxy(**kwargs)
    return httpcore.AsyncHTTPProxy(proxy_headers=proxy.headers.raw, **kwargs)


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, response: httpx.Response, control):
        self.response = response
        self.control = control
        self.closed = False
        self.exhausted = False
        self.iterator = response.stream.__aiter__()

    def __iter__(self):
        try:
            while True:
                try:
                    yield _wait(self.iterator.__anext__(), self.control)
                except StopAsyncIteration:
                    self.exhausted = True
                    break
        finally:
            self.close()

    def close(self):
        if not self.closed:
            self.closed = True

            async def finish():
                # SDKs can stop at an SSE terminal record before HTTP's final
                # framing is consumed. Finish a small buffered tail so a healthy
                # connection can be reused, with a strict bound for stalled peers.
                async def drain():
                    remaining = 64 * 1024
                    async for chunk in self.iterator:
                        remaining -= len(chunk)
                        if remaining <= 0:
                            return
                    self.exhausted = True

                try:
                    if not self.exhausted and not (self.control is not None and self.control.cancelled.is_set()):
                        try:
                            await asyncio.wait_for(drain(), timeout=0.05)
                        except (asyncio.TimeoutError, httpx.HTTPError):
                            self.exhausted = False
                finally:
                    await self.response.aclose()

            try:
                _wait(finish())
            finally:
                network = self.response.extensions.get("network_stream")
                if isinstance(network, _NetworkStream):
                    network.release_cancel()


class ProviderTransport(httpx.BaseTransport):
    def __init__(self, *, proxy=None, verify=True, cert=None):
        self.key = (str(proxy or ""), verify, cert)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        control = _control.get()
        check_cancel()
        body = request.read()

        async def send():
            transport = _transports.get(self.key)
            if transport is None:
                transport = _pool(self.key)
                _transports[self.key] = transport
            with _core_errors():
                core_response = await transport.handle_async_request(httpcore.Request(
                    request.method, str(request.url), headers=request.headers.raw, content=body, extensions=request.extensions,
                ))
            response = httpx.Response(core_response.status, headers=core_response.headers,
                                      stream=_CoreStream(core_response.stream), extensions=core_response.extensions)
            return response

        response = _wait(send(), control)
        return httpx.Response(response.status_code, headers=response.headers,
                              stream=_ResponseStream(response, control), extensions=response.extensions)

    def close(self):
        # A short-lived SDK client does not own the process-wide connection pool.
        pass


def provider_client(*, proxy=None, **kwargs) -> httpx.Client:
    return httpx.Client(transport=ProviderTransport(proxy=proxy), trust_env=False, **kwargs)


class _RequestsBody:
    def __init__(self, response: httpx.Response):
        self.response = response

    def stream(self, _amount, decode_content=True):
        del decode_content
        yield from self.response.iter_bytes()

    def close(self):
        self.response.close()

    def release_conn(self):
        self.close()


class _RequestsAdapter(requests.adapters.BaseAdapter):
    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        proxy = requests.utils.select_proxy(request.url, proxies or {})
        if isinstance(timeout, tuple):
            timeout = httpx.Timeout(timeout[1], connect=timeout[0])
        client = httpx.Client(transport=ProviderTransport(proxy=proxy, verify=verify, cert=cert), trust_env=False)
        try:
            upstream = client.send(httpx.Request(request.method, request.url, headers=dict(request.headers),
                                                 content=request.body or b"",
                                                 extensions={"timeout": httpx.Timeout(timeout).as_dict()}), stream=True)
        except httpx.TimeoutException as exc:
            raise requests.Timeout(str(exc), request=request) from exc
        except httpx.HTTPError as exc:
            raise requests.ConnectionError(str(exc), request=request) from exc
        result = requests.Response()
        result.status_code = upstream.status_code
        result.headers = requests.structures.CaseInsensitiveDict(upstream.headers)
        result.url = str(upstream.url)
        result.request = request
        result.encoding = requests.utils.get_encoding_from_headers(result.headers)
        result.raw = _RequestsBody(upstream)
        if not stream:
            try:
                result.content
            finally:
                upstream.close()
        return result

    def close(self):
        pass


def provider_post(url: str, **kwargs):
    # Session handles request encoding, redirects, cookies and environment proxy
    # rules; the adapter shares sockets with SDK clients on the async I/O loop.
    with requests.Session() as session:
        if urlsplit(url).hostname in {"localhost", "127.0.0.1", "::1"} and not any((kwargs.get("proxies") or {}).values()):
            session.trust_env = False
        adapter = _RequestsAdapter()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session.post(url, **kwargs)


def _shutdown():
    if _loop is None:
        return

    async def close():
        for transport in _transports.values():
            await transport.aclose()
        _transports.clear()

    try:
        asyncio.run_coroutine_threadsafe(close(), _loop).result(timeout=2)
    except Exception:
        from .diagnostics import report_suppressed_exception
        report_suppressed_exception("Provider connection-pool shutdown")
    _loop.call_soon_threadsafe(_loop.stop)


atexit.register(_shutdown)
