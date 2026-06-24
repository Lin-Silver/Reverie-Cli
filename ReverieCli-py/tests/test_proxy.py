import reverie.proxy as proxy
from reverie.proxy import _proxy_from_windows_proxy_server, normalize_proxy_url


def test_proxy_url_normalization_adds_http_scheme() -> None:
    assert normalize_proxy_url("127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert normalize_proxy_url("socks5://127.0.0.1:7891") == "socks5://127.0.0.1:7891"
    assert normalize_proxy_url("clear") == ""


def test_windows_proxy_server_parser_prefers_https_then_http() -> None:
    assert _proxy_from_windows_proxy_server("127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert _proxy_from_windows_proxy_server("http=127.0.0.1:7890;https=127.0.0.1:7891") == "http://127.0.0.1:7891"
    assert _proxy_from_windows_proxy_server("socks=127.0.0.1:7892") == "socks5://127.0.0.1:7892"


def test_proxy_resolution_can_prefer_windows_system_proxy(monkeypatch) -> None:
    monkeypatch.setattr(proxy, "_windows_system_proxy_url", lambda: "http://system.example:7890")
    monkeypatch.setattr(proxy, "_environment_proxy_url", lambda: "http://env.example:7890")

    assert proxy.resolve_proxy_url_with_source("", prefer_system=True) == ("http://system.example:7890", "system")
    assert proxy.resolve_proxy_url_with_source("", prefer_system=False) == ("http://env.example:7890", "environment")
