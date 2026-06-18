from collections import deque
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
    assert metrics["cursor_col"] == handler._display_width(ZH_SECOND_LINE)


def test_prompt_editor_renders_newline_without_continuation_prefix() -> None:
    handler = _handler(width=120)
    render_state = {"rendered": False, "cursor_row": 0, "total_rows": 1}

    handler._redraw_windows_input("Reverie> ", f"{ZH_FIRST_LINE}\n{ZH_SECOND_LINE}", 0, render_state)

    rendered = handler._output_stream().getvalue()
    assert "continue" not in rendered
    assert f"\n{ZH_SECOND_LINE}" in rendered


def test_prompt_editor_prompt_width_matches_visible_prompt() -> None:
    handler = _handler(width=120)
    render_state = {"rendered": False, "cursor_row": 0, "total_rows": 1}

    handler._redraw_windows_input("Reverie> ", "", 0, render_state)

    rendered = handler._output_stream().getvalue()
    assert "\x1b[" in rendered
    assert "ready" not in rendered
    assert render_state["cursor_col"] == handler._display_width(
        handler._plain_prompt_text("Reverie> ")
    )


def test_prompt_editor_clears_previous_wrapped_rows_before_redraw() -> None:
    handler = _handler(width=30)
    render_state = {"rendered": False, "cursor_row": 0, "total_rows": 1}

    handler._redraw_windows_input("Reverie> ", "x" * 90, 90, render_state)
    assert render_state["rendered_rows"] > 1

    handler._redraw_windows_input("Reverie> ", "ok", 2, render_state)

    rendered = handler._output_stream().getvalue()
    assert "\x1b[2K" in rendered
    assert render_state["rendered_rows"] == 1


def test_windows_get_input_uses_key_editor_for_empty_input(monkeypatch) -> None:
    import msvcrt

    handler = _handler()
    keys = iter([*list(ZH_FIRST), "\n", *list(ZH_SECOND), "\r"])
    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keys))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)

    assert handler.get_input("Reverie> ") == f"{ZH_FIRST}\n{ZH_SECOND}"


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


def test_windows_prompt_editor_clears_rendered_input_on_ctrl_c(monkeypatch) -> None:
    import msvcrt

    handler = _handler(width=30)
    keys = iter([*"x" * 90, "\x03"])
    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keys))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)

    assert handler._get_seeded_single_line_input("Reverie> ", "") is None
    assert "\x1b[2K" in handler._output_stream().getvalue()


def test_windows_prompt_editor_allows_modified_enter_newline(monkeypatch) -> None:
    import msvcrt

    handler = _handler()
    keys = iter([*list(ZH_FIRST), "\r", *list(ZH_SECOND), "\r"])
    enter_modes = iter([True, False])
    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keys))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)
    monkeypatch.setattr(handler, "_enter_should_insert_newline", lambda: next(enter_modes))

    assert handler._get_seeded_single_line_input("Reverie> ", "") == f"{ZH_FIRST}\n{ZH_SECOND}"


def test_windows_prompt_editor_paste_preserves_single_newline(monkeypatch) -> None:
    import msvcrt

    handler = _handler()
    # Simulate pasting "第一行\r\n第二行" (no trailing newline) then user presses Enter
    keys = deque([*list(ZH_FIRST_LINE), "\r", "\n", *list(ZH_SECOND_LINE), "\r"])
    monkeypatch.setattr(msvcrt, "getwch", lambda: keys.popleft())
    monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(keys))

    result = handler._get_seeded_single_line_input("Reverie> ", "")
    assert result == f"{ZH_FIRST_LINE}\n{ZH_SECOND_LINE}"


def test_windows_prompt_editor_right_at_end_does_not_redraw(monkeypatch) -> None:
    import msvcrt

    handler = _handler(width=80)
    prompt_width = handler._display_width(handler._plain_prompt_text("Reverie> "))
    initial = "x" * (80 - prompt_width)
    keys = iter(["\xe0", "M", "\r"])
    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keys))
    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)

    assert handler._get_seeded_single_line_input("Reverie> ", initial) == initial
    assert "\x1b[2K" not in handler._output_stream().getvalue()


def test_windows_prompt_editor_batches_printable_paste_redraw(monkeypatch) -> None:
    import msvcrt

    handler = _handler()
    keys = deque([*"pasted text", "\r"])
    monkeypatch.setattr(msvcrt, "getwch", lambda: keys.popleft())
    monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(keys))

    assert handler._get_seeded_single_line_input("Reverie> ", "") == "pasted text"
    assert handler._output_stream().getvalue().count("\x1b[2K") == 1


def test_line_visual_rows_exact_width() -> None:
    handler = _handler(width=80)
    prompt_width = handler._display_width(handler._plain_prompt_text("Reverie> "))
    # Fill exactly one terminal line
    filler = "x" * (80 - prompt_width)
    assert handler._line_visual_rows(prompt_width, filler) == 1
    # One extra character should wrap to second line
    assert handler._line_visual_rows(prompt_width, filler + "x") == 2


def test_line_visual_rows_empty_line() -> None:
    handler = _handler(width=80)
    assert handler._line_visual_rows(0, "") == 1
    assert handler._line_visual_rows(10, "") == 1


def test_cursor_position_at_exact_line_boundary() -> None:
    handler = _handler(width=80)
    prompt_width = handler._display_width(handler._plain_prompt_text("Reverie> "))
    # Fill exactly one terminal line so cursor lands at the start of the next visual line
    filler = "x" * (80 - prompt_width)
    buffer = filler
    cursor = len(buffer)
    metrics = handler._input_visual_metrics("Reverie> ", buffer, cursor)
    # cursor should be on the second visual line (row 1) at column 0
    assert metrics["cursor_row"] == 1
    assert metrics["cursor_col"] == 0
    assert metrics["text_rows"] == 1
    assert metrics["total_rows"] == 2
    assert metrics["needs_trailing_cursor_row"] is True


def test_prompt_editor_materializes_exact_boundary_cursor_row() -> None:
    handler = _handler(width=80)
    prompt_width = handler._display_width(handler._plain_prompt_text("Reverie> "))
    buffer = "x" * (80 - prompt_width)
    render_state = {"rendered": False, "cursor_row": 0, "total_rows": 1}

    handler._redraw_windows_input("Reverie> ", buffer, len(buffer), render_state)

    assert render_state["text_rows"] == 1
    assert render_state["rendered_rows"] == 2
    assert handler._output_stream().getvalue().endswith("\n\r")


def test_cursor_boundary_inside_wrapped_text_uses_existing_row() -> None:
    handler = _handler(width=80)
    prompt_width = handler._display_width(handler._plain_prompt_text("Reverie> "))
    boundary_prefix = "x" * (80 - prompt_width)
    buffer = f"{boundary_prefix}next"

    metrics = handler._input_visual_metrics("Reverie> ", buffer, len(boundary_prefix))

    assert metrics["text_rows"] == 2
    assert metrics["total_rows"] == 2
    assert metrics["cursor_row"] == 1
    assert metrics["cursor_col"] == 0
    assert metrics["needs_trailing_cursor_row"] is False
