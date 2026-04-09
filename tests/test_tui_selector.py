from rich.console import Console

from reverie.cli.tui_selector import SelectorAction, SelectorItem, TUISelector


def test_selector_uses_cropped_live_screen(monkeypatch) -> None:
    selector = TUISelector(
        console=Console(force_terminal=True, width=120, height=40),
        title="Select Model",
        items=[SelectorItem(id="one", title="One", description="first item")],
    )

    captured: dict[str, object] = {}

    class FakeLive:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, *args, **kwargs):
            return None

    import msvcrt
    import rich.live

    monkeypatch.setattr(rich.live, "Live", FakeLive)
    monkeypatch.setattr(msvcrt, "kbhit", lambda: True)
    monkeypatch.setattr(msvcrt, "getch", lambda: b"\r")

    result = selector.run()

    assert result.action == SelectorAction.SELECT
    assert result.selected_item is not None
    assert captured["screen"] is True
    assert captured["transient"] is True
    assert captured["vertical_overflow"] == "crop"
