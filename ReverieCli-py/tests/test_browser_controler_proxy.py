"""Managed local browser discovery must work when an HTTP proxy is configured."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from reverie.tools.browser_controler import BrowserControlerTool


def test_cdp_http_requests_bypass_host_proxies(tmp_path, monkeypatch):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(("GET", self.path))
            payload = [{"id": "page"}] if self.path == "/json/list" else {"id": "page", "Browser": "audit"}
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self):
            calls.append(("PUT", self.path))
            self.send_error(405)

        def log_message(self, *args):
            pass

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        tool = BrowserControlerTool({"project_root": tmp_path})
        port = server.server_port
        monkeypatch.setattr(tool, "_is_authorized_cdp_port", lambda value: value == port)
        assert tool._cdp_version(port)["Browser"] == "audit"
        assert tool._cdp_list_targets(port) == [{"id": "page"}]
        assert tool._cdp_create_target(port, "about:blank")["id"] == "page"
        assert [method for method, _ in calls] == ["GET", "GET", "PUT", "GET"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
