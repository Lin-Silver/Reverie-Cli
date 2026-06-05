from io import StringIO

from rich.console import Console

from reverie.cli.input_handler import InputHandler


ZH_PROMPT = "\u5e2e\u6211\u4f5c\u4e00\u4e2a"
ZH_FIXED_PROMPT = "\u5e2e\u6211\u4f5c\u6210\u4e00\u4e2a"
ZH_BACKSPACED_PROMPT = "\u5e2e\u6211\u4e00\u4e2a"
ZH_DONE = "\u6210"
ZH_FIRST_LINE = "\u7b2c\u4e00\u884c"
ZH_SECOND_LINE = "\u7b2c\u4e8c\u884c"
ZH_FIRST = "\u7b2c\u4e00"
ZH_SECOND = "\u7b2c\u4e8c"


def _handler(width: int = 80) -> InputHandler:
    return InputHandler(Console(file=StringIO(), force_terminal=True, width=width))


def test_prompt_editor_counts_cjk_characters_as_wide_cells() -> None:
    handler = _handler()

    assert handler._display_width(ZH_PROMPT) == 10
    assert handler._display_width(f"a{ZH_DONE}b") == 4


def test_prompt_editor_moves_and_inserts_inside_chinese_text() -> None:
    buffer = ZH_PROMPT
    cursor = len(buffer)

    cursor = InputHandler._move_cursor_left(buffer, cursor)
    cursor = InputHandler._move_cursor_left(buffer, cursor)
    buffer, cursor = InputHandler._insert_text(buffer, cursor, ZH_DONE)

    assert buffer == ZH_FIXED_PROMPT
    assert cursor == len(ZH_FIXED_PROMPT) - 2


def test_prompt_editor_deletes_one_chinese_character() -> None:
    buffer = ZH_PROMPT
    cursor = len(ZH_PROMPT) - 2

    buffer, cursor = InputHandler._delete_backward(buffer, cursor)

    assert buffer == ZH_BACKSPACED_PROMPT
    assert cursor == len(ZH_BACKSPACED_PROMPT) - 2


def test_prompt_editor_tracks_cursor_on_multiline_input() -> None:
    handler = _handler(width=120)
    buffer = f"{ZH_FIRST_LINE}\n{ZH_SECOND_LINE}"
    cursor = len(buffer)

    metrics = handler._input_visual_metrics("Reverie> ", buffer, cursor)

    assert metrics["total_rows"] == 2
    assert metrics["cursor_row"] == 1
    assert metrics["cursor_col"] == (
        handler._display_width(handler._plain_prompt_text("Reverie> ", is_continuation=True))
        + handler._display_width(ZH_SECOND_LINE)
    )


def test_windows_prompt_editor_handles_arrow_insertion(monkeypatch) -> None:
    import msvcrt

    keys = iter([*list(ZH_PROMPT), "\xe0", "K", "\xe0", "K", ZH_DONE, "\r"])
    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keys))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)

    assert _handler()._get_seeded_single_line_input("Reverie> ", "") == ZH_FIXED_PROMPT


def test_windows_prompt_editor_handles_middle_backspace(monkeypatch) -> None:
    import msvcrt

    keys = iter([*list(ZH_PROMPT), "\xe0", "K", "\xe0", "K", "\x08", "\r"])
    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keys))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)

    assert _handler()._get_seeded_single_line_input("Reverie> ", "") == ZH_BACKSPACED_PROMPT


def test_windows_prompt_editor_allows_modified_enter_newline(monkeypatch) -> None:
    import msvcrt

    handler = _handler()
    keys = iter([*list(ZH_FIRST), "\r", *list(ZH_SECOND), "\r"])
    enter_modes = iter([True, False])
    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keys))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)
    monkeypatch.setattr(handler, "_enter_should_insert_newline", lambda: next(enter_modes))

    assert handler._get_seeded_single_line_input("Reverie> ", "") == f"{ZH_FIRST}\n{ZH_SECOND}"
