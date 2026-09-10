"""A viewport fallback must not advertise a full-page capture."""

import base64

import pytest

from reverie.tools import browser_controler


@pytest.mark.parametrize("fallback", [False, True])
def test_screenshot_metadata_describes_the_actual_capture(tmp_path, monkeypatch, fallback):
    tool = browser_controler.BrowserControlerTool({"project_root": tmp_path})
    monkeypatch.setattr(tool, "_cdp_select_target", lambda *args, **kwargs: {"webSocketDebuggerUrl": "ws://127.0.0.1"})
    requests = []

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call(self, method, params=None, **kwargs):
            if method != "Page.captureScreenshot":
                return {}
            requests.append(dict(params))
            if fallback and len(requests) == 1:
                raise TimeoutError("full page unavailable")
            return {"data": base64.b64encode(b"captured-image").decode()}

    monkeypatch.setattr(browser_controler, "_CdpConnection", Connection)
    result = tool._devtools_screenshot(port=9222, full_page=True)
    assert result.success
    assert result.data["full_page"] is (not fallback)
    assert bool(result.data["fallback_error"]) is fallback
    assert requests[-1]["captureBeyondViewport"] is (not fallback)
