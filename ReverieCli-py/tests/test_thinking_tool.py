"""Coverage for the experimental Thinking Tool and the settings browser it lives in.

The switch touches four surfaces that can drift apart: the tool itself, the
schema gate that decides whether the model ever sees it, the spin guard that
keeps a thinking-only turn from looping forever, and the settings UI that flips
the flag. Each one is exercised here against real objects.
"""

from pathlib import Path
from typing import Any, Dict, List
from unittest import mock
import sys

import pytest
from rich.console import Console

from reverie.agent.agent import ReverieAgent, decode_stream_event, encode_stream_event
from reverie.agent.system_prompt import build_system_prompt
from reverie.agent.tool_executor import ToolExecutor
from reverie.cli.commands import CommandHandler
from reverie.cli.display import DisplayComponents
from reverie.config import Config, ConfigManager
from reverie.settings_catalog import (
    SECURITY_SETTING_KEYS,
    apply_setting_value,
    get_setting_items,
    setting_section_for,
)
from reverie.thinking_tool import (
    THINK_TOOL_TAG,
    clean_think_argument,
    extract_think_tool_text,
    is_think_tool,
)
from reverie.tools.deep_think import DeepThinkTool


THOUGHT = (
    "The failing test asserts on the persisted security block, so the value has to "
    "round-trip through ConfigManager rather than only the in-memory Config."
)


# --------------------------------------------------------------------------- #
# Shared identity helpers
# --------------------------------------------------------------------------- #


def test_think_tool_names_cover_the_aliases_models_actually_emit() -> None:
    for name in ("deep_think", "DEEP_THINK", " think ", "think_tool", "deep_thinking"):
        assert is_think_tool(name), name
    for name in ("", None, "read_file", "thinking_budget", 17):
        assert not is_think_tool(name), name


def test_extract_think_tool_text_builds_one_readable_block() -> None:
    text = extract_think_tool_text(
        {"topic": "Config round-trip", "thought": THOUGHT, "next_step": "read config.py"}
    )
    assert text.startswith("**Config round-trip**")
    assert THOUGHT in text
    assert text.endswith("Next: read config.py")

    # Optional fields drop out instead of leaving empty markup behind.
    assert extract_think_tool_text({"thought": "  just this  "}) == "just this"
    assert extract_think_tool_text({}) == ""
    assert extract_think_tool_text(None) == ""


def test_clean_think_argument_flattens_non_string_arguments() -> None:
    assert clean_think_argument(None) == ""
    assert clean_think_argument("  padded\r\n") == "padded"
    assert clean_think_argument(42) == "42"


# --------------------------------------------------------------------------- #
# The tool
# --------------------------------------------------------------------------- #


def test_deep_think_records_the_reasoning_and_hands_control_back() -> None:
    result = DeepThinkTool().execute(thought=THOUGHT, topic="Config", next_step="read config.py")

    assert result.success
    assert result.data["tag"] == THINK_TOOL_TAG
    assert result.data["thought"] == THOUGHT
    assert result.data["characters"] == len(THOUGHT)
    # The acknowledgement pushes the model to act rather than think again.
    assert "read config.py" in result.output


def test_deep_think_rejects_an_empty_thought() -> None:
    result = DeepThinkTool().execute(thought="   ")
    assert not result.success
    assert "thought" in (result.error or "")


def test_deep_think_flags_a_placeholder_thought_without_failing_the_turn() -> None:
    result = DeepThinkTool().execute(thought="hmm")
    assert result.success
    assert "short" in result.output
    assert result.data["characters"] == 3


def test_deep_think_never_touches_the_workspace() -> None:
    tool = DeepThinkTool()
    assert tool.read_only is True
    assert tool.concurrency_safe is True
    assert tool.workspace_checkpoint is False
    assert "thought" in tool.parameters["required"]


# --------------------------------------------------------------------------- #
# Schema gating
# --------------------------------------------------------------------------- #


class _Agent:
    """Minimal stand-in for the parts of the agent the executor reads."""

    mode = "reverie"

    def __init__(self, thinking_tool: bool = False) -> None:
        self.config = Config(
            thinking_tool=thinking_tool,
            security={"permission_level": "workspace_write"},
        )


def _schema_names(executor: ToolExecutor) -> set:
    return {
        str(((schema or {}).get("function") or {}).get("name") or "")
        for schema in executor.get_tool_schemas(mode="reverie")
    }


def test_deep_think_is_hidden_until_the_switch_is_on(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    agent = _Agent(thinking_tool=False)
    executor.update_context("agent", agent)

    assert "deep_think" not in _schema_names(executor)

    agent.config.thinking_tool = True
    # No explicit invalidation: the flag is part of the schema cache key, so the
    # very next request has to recompute instead of serving a stale list.
    assert "deep_think" in _schema_names(executor)

    agent.config.thinking_tool = False
    assert "deep_think" not in _schema_names(executor)


def test_invalidate_schema_cache_is_available_for_live_toggles(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    agent = _Agent(thinking_tool=True)
    executor.update_context("agent", agent)

    assert "deep_think" in _schema_names(executor)
    executor.invalidate_schema_cache()
    assert "deep_think" in _schema_names(executor)


def test_deep_think_is_blocked_at_execution_time_when_the_switch_is_off(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("agent", _Agent(thinking_tool=False))

    assert not executor._tool_is_visible("deep_think", DeepThinkTool(), "reverie")

    executor.update_context("agent", _Agent(thinking_tool=True))
    assert executor._tool_is_visible("deep_think", DeepThinkTool(), "reverie")


def test_system_prompt_only_explains_the_tool_when_it_is_offered() -> None:
    off = build_system_prompt(config=Config(thinking_tool=False))
    on = build_system_prompt(config=Config(thinking_tool=True))

    assert "deep_think" not in off
    assert "deep_think" in on


def test_the_guidance_asks_for_a_call_every_turn_not_only_for_hard_steps() -> None:
    """The switch exists to make reasoning visible, so opting out must not be offered.

    The first cut told the model to "skip it entirely for trivial work", which a
    model obeys -- the user enabled the feature and saw nothing at all.
    """
    prompt = build_system_prompt(config=Config(thinking_tool=True))

    assert "Start every turn with exactly one `deep_think` call" in prompt
    assert "skip it entirely" not in prompt.lower()
    # The tool description is what many providers weight most, so it has to agree.
    assert "at the start of every turn" in DeepThinkTool.description


# --------------------------------------------------------------------------- #
# Loop safety
# --------------------------------------------------------------------------- #


class _SdkToolCall:
    """Shape of a provider SDK tool call: attributes, not dict keys."""

    class _Function:
        def __init__(self, name: str) -> None:
            self.name = name
            self.arguments = "{}"

    def __init__(self, name: str) -> None:
        self.id = f"call_{name}"
        self.type = "function"
        self.function = self._Function(name)


class _GuardHost:
    """Exercise the real spin guard without building a whole agent."""

    THINK_TOOL_NUDGE_AT = ReverieAgent.THINK_TOOL_NUDGE_AT
    THINK_TOOL_HARD_LIMIT = ReverieAgent.THINK_TOOL_HARD_LIMIT
    _reset_think_tool_budget = ReverieAgent._reset_think_tool_budget
    _think_tool_budget_state = ReverieAgent._think_tool_budget_state
    _guard_think_tool_spin = ReverieAgent._guard_think_tool_spin

    def __init__(self) -> None:
        self._consecutive_think_only_batches = 0
        self._think_tool_suppressed = False
        self.messages: List[Dict[str, Any]] = []

    def _append_internal_system_message(self, messages: List[Dict[str, Any]], content: str) -> None:
        messages.append({"role": "system", "content": str(content)})


def _dict_call(name: str) -> Dict[str, Any]:
    return {"id": f"call_{name}", "type": "function", "function": {"name": name, "arguments": "{}"}}


@pytest.mark.parametrize("make_call", [_dict_call, _SdkToolCall])
def test_thinking_only_batches_first_earn_a_nudge_then_lose_the_tool(make_call) -> None:
    host = _GuardHost()
    messages: List[Dict[str, Any]] = []

    # First thought-only batch: real progress, nothing to say.
    host._guard_think_tool_spin([make_call("deep_think")], messages)
    assert host._think_tool_budget_state() == (1, False)
    assert messages == []

    host._guard_think_tool_spin([make_call("deep_think")], messages)
    assert host._think_tool_budget_state() == (2, False)
    assert len(messages) == 1 and "deep_think" in messages[-1]["content"]

    host._guard_think_tool_spin([make_call("deep_think")], messages)
    host._guard_think_tool_spin([make_call("deep_think")], messages)
    count, suppressed = host._think_tool_budget_state()
    assert count >= ReverieAgent.THINK_TOOL_HARD_LIMIT
    assert suppressed is True
    assert "unavailable" in messages[-1]["content"]


def test_any_real_work_in_the_batch_clears_the_spin_budget() -> None:
    host = _GuardHost()
    messages: List[Dict[str, Any]] = []

    host._guard_think_tool_spin([_dict_call("deep_think")], messages)
    host._guard_think_tool_spin([_dict_call("deep_think")], messages)
    assert host._think_tool_budget_state()[0] == 2

    host._guard_think_tool_spin([_dict_call("deep_think"), _dict_call("read_file")], messages)
    assert host._think_tool_budget_state() == (0, False)


def test_an_empty_tool_batch_neither_counts_nor_clears() -> None:
    host = _GuardHost()
    messages: List[Dict[str, Any]] = []

    host._guard_think_tool_spin([_dict_call("deep_think")], messages)
    host._guard_think_tool_spin([], messages)
    host._guard_think_tool_spin([{"function": {"name": "   "}}], messages)

    assert host._think_tool_budget_state() == (1, False)
    assert messages == []


class _SchemaHost:
    """Exercise the real schema filter used by every request path."""

    mode = "reverie"
    model = "test-model"
    get_visible_tool_schemas = ReverieAgent.get_visible_tool_schemas

    def __init__(self, executor: ToolExecutor, suppressed: bool) -> None:
        self.tool_executor = executor
        self._think_tool_suppressed = suppressed

    def _is_active_model_source(self, source: str) -> bool:
        return False

    def _is_nvidia_request(self) -> bool:
        return False


def test_a_suppressed_turn_stops_advertising_the_tool(tmp_path: Path) -> None:
    executor = ToolExecutor(tmp_path)
    executor.update_context("agent", _Agent(thinking_tool=True))

    visible = _SchemaHost(executor, suppressed=False).get_visible_tool_schemas()
    assert any(is_think_tool(schema["function"]["name"]) for schema in visible)

    suppressed = _SchemaHost(executor, suppressed=True).get_visible_tool_schemas()
    assert suppressed, "only the thinking tool should be withheld"
    assert not any(is_think_tool(schema["function"]["name"]) for schema in suppressed)


# --------------------------------------------------------------------------- #
# Terminal rendering
# --------------------------------------------------------------------------- #


def _display() -> tuple:
    console = Console(record=True, width=120, no_color=True, legacy_windows=False)
    return DisplayComponents(console), console


def test_a_think_tool_call_renders_as_thinking_under_its_own_tag() -> None:
    display, console = _display()

    display.show_tool_invocation(
        "deep_think",
        "Thinking it through",
        {"topic": "Config round-trip", "thought": THOUGHT},
        tool_call_id="call_1",
    )

    rendered = console.export_text()
    assert "think_tool" in rendered
    assert "thinking" in rendered
    assert "Config round-trip" in rendered


def test_the_streamed_event_the_agent_emits_reaches_the_thinking_renderer() -> None:
    """Cover the real path: the agent's encoded tool_start, not the renderer alone.

    Every other display test calls the renderer directly, which cannot catch a
    break between the wire format and the transcript.
    """
    display, console = _display()
    frame = encode_stream_event(
        "tool_start",
        tool_name="deep_think",
        message="Thinking through Config round-trip",
        arguments={"topic": "Config round-trip", "thought": THOUGHT, "next_step": "Read the loader."},
        tool_call_id="call_stream",
        agent_id="",
        agent_color="",
    )
    event = decode_stream_event(frame)
    assert event is not None

    assert display.show_stream_event(event) is True

    rendered = console.export_text()
    assert "think_tool" in rendered
    assert "Config round-trip" in rendered
    assert "Next: Read the loader." in rendered
    # The acknowledgement row must not follow the thinking block.
    display.show_stream_event(
        decode_stream_event(
            encode_stream_event(
                "tool_result",
                tool_name="deep_think",
                success=True,
                output="Thought recorded. Now act on it: Read the loader.",
                arguments={},
                tool_call_id="call_stream",
            )
        )
    )
    assert "Thought recorded" not in console.export_text()


def test_the_terminal_never_shows_raw_markdown_from_the_think_tool() -> None:
    """The shared extractor emits light markdown for the GUI; the TUI styles it."""
    display, console = _display()

    display.show_think_tool_block(
        {
            "topic": "Config round-trip",
            "thought": "The **ranker** and the reranker both score channels.",
            "next_step": "Read the entry point.",
        }
    )

    rendered = console.export_text()
    assert "**" not in rendered
    assert "Config round-trip" in rendered
    assert "ranker" in rendered


def test_the_think_tool_acknowledgement_is_not_printed_twice() -> None:
    display, console = _display()

    display.show_tool_invocation(
        "deep_think",
        "Thinking it through",
        {"thought": THOUGHT},
        tool_call_id="call_1",
    )
    # export_text() drains the recording, so what follows is only new output.
    assert "think_tool" in console.export_text()

    display.show_tool_result_card(
        "deep_think",
        True,
        output="Thought recorded. Now act on it.",
        arguments={"thought": THOUGHT},
        tool_call_id="call_1",
    )

    # The thinking block already carried everything worth seeing; a successful
    # acknowledgement would just be a duplicate row.
    assert console.export_text().strip() == ""


def test_hidden_thinking_output_also_hides_the_think_tool_block() -> None:
    display, console = _display()
    display.set_thinking_output_style("hidden")

    display.show_think_tool_block({"thought": THOUGHT})

    assert console.export_text().strip() == ""


def test_a_failed_think_tool_call_is_still_reported() -> None:
    display, console = _display()

    display.show_tool_result_card(
        "deep_think",
        False,
        error="No reasoning was supplied.",
        arguments={},
        tool_call_id="missing",
    )

    rendered = console.export_text()
    # Failures keep the think_tool tag so the row reads like the thinking block.
    assert "think_tool" in rendered
    assert "No reasoning was supplied." in rendered


def test_a_blank_think_tool_failure_still_renders_a_row() -> None:
    """A whitespace-only error must not crash the renderer on splitlines()[0]."""
    display, console = _display()

    display.show_tool_result_card("deep_think", False, error="   ", arguments={}, tool_call_id="blank")

    assert "Thinking Tool call failed" in console.export_text()


# --------------------------------------------------------------------------- #
# Settings catalog
# --------------------------------------------------------------------------- #


def _config_manager(tmp_path: Path) -> ConfigManager:
    manager = ConfigManager(tmp_path / "config.json")
    manager.save(manager.load())
    return manager


def test_the_thinking_tool_item_is_experimental_and_lives_under_reasoning(tmp_path: Path) -> None:
    manager = _config_manager(tmp_path)
    items = {
        str(item.get("key")): item
        for item in get_setting_items(manager.load(), manager, None)
    }

    item = items["thinking_tool"]
    assert item["kind"] == "bool"
    assert item["experimental"] is True
    assert item["section"] == "Reasoning"
    assert "/setting thinking-tool" in item["command"]


def test_every_setting_item_carries_a_section(tmp_path: Path) -> None:
    manager = _config_manager(tmp_path)
    items = get_setting_items(manager.load(), manager, None)

    assert items
    assert all(str(item.get("section") or "").strip() for item in items)
    assert setting_section_for("thinking_tool") == "Reasoning"
    assert setting_section_for("anything", "plugin-bool") == "Plugins"
    assert setting_section_for("not-a-real-key") == "Session"


def test_toggling_the_thinking_tool_asks_for_an_agent_rebuild(tmp_path: Path) -> None:
    manager = _config_manager(tmp_path)
    config = manager.load()

    ok, message, reinit = apply_setting_value(config, manager, None, "thinking_tool", "on")
    assert ok and reinit is True
    assert config.thinking_tool is True
    assert "on" in message.lower()

    ok, _message, reinit = apply_setting_value(config, manager, None, "thinking_tool", "off")
    assert ok and reinit is True
    assert config.thinking_tool is False

    # A purely cosmetic boolean must not force a rebuild.
    ok, _message, reinit = apply_setting_value(config, manager, None, "show_status_line", "off")
    assert ok and reinit is False


def test_the_thinking_tool_flag_round_trips_through_the_config_file(tmp_path: Path) -> None:
    manager = _config_manager(tmp_path)
    config = manager.load()
    config.thinking_tool = True
    manager.save(config)

    assert manager.load().thinking_tool is True
    assert Config.from_dict(config.to_dict()).thinking_tool is True


def test_the_desktop_pane_reads_security_settings_out_of_the_security_block(tmp_path: Path) -> None:
    """Only permission_level/mode have Config properties; the rest need the block."""
    from reverie.sdk_bridge import ReverieSdkBridge

    manager = _config_manager(tmp_path)
    config = manager.load()
    config.security["strict_allow_read_only"] = True
    read = ReverieSdkBridge._setting_value

    for item in get_setting_items(config, manager, None):
        if item.get("kind") in {"plugin-bool", "workspace", "rules"}:
            continue  # These read from the live interface, not from Config.
        # A None here is what renders as "(empty)" in the desktop settings pane.
        assert read(None, item, config, None) is not None, item["key"]

    strict = next(i for i in get_setting_items(config, manager, None) if i["key"] == "strict_allow_read_only")
    assert read(None, strict, config, None) is True


# --------------------------------------------------------------------------- #
# Settings browser
# --------------------------------------------------------------------------- #


def _handler(tmp_path: Path) -> tuple:
    manager = _config_manager(tmp_path)
    console = Console(record=True, width=160, no_color=True, legacy_windows=False)
    reinits: List[str] = []
    handler = CommandHandler(
        console,
        {
            "project_root": tmp_path,
            "config_manager": manager,
            "rules_manager": None,
            "reinit_agent": lambda: reinits.append("reinit"),
        },
    )
    return handler, console, manager, reinits


def _item(handler: CommandHandler, manager: ConfigManager, key: str) -> Dict[str, Any]:
    for item in handler._get_setting_items(manager.load(), manager, None):
        if str(item.get("key")) == key:
            return item
    raise AssertionError(f"missing setting item: {key}")


def test_setting_command_toggles_the_thinking_tool(tmp_path: Path) -> None:
    handler, console, manager, _reinits = _handler(tmp_path)

    assert handler.handle("/setting thinking-tool on") is True
    assert manager.load().thinking_tool is True
    assert "think_tool" in console.export_text()

    assert handler.handle("/setting think-tool off") is True
    assert manager.load().thinking_tool is False


def test_clamping_survives_an_empty_or_shrinking_item_list() -> None:
    clamp = CommandHandler._setting_clamp_index
    assert clamp(0, 0) == 0
    assert clamp(9, 0) == 0
    assert clamp(9, 3) == 2
    assert clamp(-4, 3) == 0
    assert clamp("2", 5) == 2
    assert clamp(None, 5) == 0


def test_choice_lookup_tolerates_type_and_case_drift() -> None:
    index = CommandHandler._setting_choice_index
    assert index(["full", "compact", "hidden"], "compact") == 1
    assert index(["full", "compact", "hidden"], "COMPACT") == 1
    assert index(["full", "compact", "hidden"], "nonsense") == 0
    assert index([0, 1, 2], 2) == 2
    assert index(["none", "low"], None) == 0


def test_sections_are_ordered_and_filterable(tmp_path: Path) -> None:
    handler, _console, manager, _reinits = _handler(tmp_path)
    items = handler._get_setting_items(manager.load(), manager, None)

    sections = handler._setting_sections(items)
    assert sections[0] == "All"
    assert "Reasoning" in sections
    assert sections.index("Session") < sections.index("Security")

    assert handler._setting_filtered_items(items, "All") == items
    reasoning = handler._setting_filtered_items(items, "Reasoning")
    assert reasoning and reasoning is not items
    assert {str(item.get("key")) for item in reasoning} >= {"thinking_tool", "thinking_output_style"}
    assert handler._setting_filtered_items(items, "No Such Section") == []


def test_reading_a_current_value_works_for_every_catalog_item(tmp_path: Path) -> None:
    handler, _console, manager, _reinits = _handler(tmp_path)
    config = manager.load()

    for item in handler._get_setting_items(config, manager, None):
        # Security settings live inside config.security; a plain getattr used to
        # raise AttributeError here and take the whole browser down.
        handler._setting_current_value(item, config, manager)

    level = handler._setting_current_value(_item(handler, manager, "permission_level"), config, manager)
    assert isinstance(level, str) and level
    assert "permission_level" in SECURITY_SETTING_KEYS


def test_stepping_the_thinking_tool_row_saves_and_requests_a_rebuild(tmp_path: Path) -> None:
    handler, _console, manager, _reinits = _handler(tmp_path)
    config = manager.load()
    item = _item(handler, manager, "thinking_tool")

    assert handler._setting_step_item(item, config, manager, None, 1) is True
    assert config.thinking_tool is True
    assert handler._setting_ui_needs_reinit is True
    assert "Thinking Tool" in handler._setting_ui_message

    assert handler._setting_step_item(item, config, manager, None, -1) is True
    assert config.thinking_tool is False


def test_stepping_a_security_choice_row_updates_the_security_block(tmp_path: Path) -> None:
    handler, _console, manager, _reinits = _handler(tmp_path)
    config = manager.load()
    item = _item(handler, manager, "permission_level")
    before = handler._setting_current_value(item, config, manager)

    assert handler._setting_step_item(item, config, manager, None, 1) is True
    after = handler._setting_current_value(item, config, manager)

    assert after != before
    assert config.security["permission_level"] == after


def test_stepping_a_bounded_int_row_stops_at_its_limit(tmp_path: Path) -> None:
    handler, _console, manager, _reinits = _handler(tmp_path)
    config = manager.load()
    item = _item(handler, manager, "api_timeout")
    minimum = int(item.get("min", 0) or 0)
    config.api_timeout = minimum

    assert handler._setting_step_item(item, config, manager, None, -1) is False
    assert config.api_timeout == minimum
    assert "minimum" in handler._setting_ui_message

    assert handler._setting_step_item(item, config, manager, None, 1) is True
    assert config.api_timeout > minimum


def test_stepping_a_readonly_row_changes_nothing(tmp_path: Path) -> None:
    handler, _console, manager, _reinits = _handler(tmp_path)
    config = manager.load()
    item = _item(handler, manager, "active_model_source")

    assert handler._setting_step_item(item, config, manager, None, 1) is False


def test_the_settings_view_renders_a_section_and_flags_the_experiment(tmp_path: Path) -> None:
    handler, console, manager, _reinits = _handler(tmp_path)
    config = manager.load()
    items = handler._get_setting_items(config, manager, None)
    sections = handler._setting_sections(items)
    reasoning = handler._setting_filtered_items(items, "Reasoning")
    # The detail panel describes the selected row, so select the experiment.
    selected_idx = next(
        index for index, item in enumerate(reasoning) if item.get("key") == "thinking_tool"
    )

    console.print(
        handler._render_setting_ui(
            selected_idx,
            0,
            config,
            manager,
            None,
            changed=False,
            active_section="Reasoning",
            sections=sections,
        )
    )

    rendered = console.export_text()
    assert "Reasoning" in rendered
    assert "Thinking Tool" in rendered
    assert "Experimental" in rendered
    assert "Tab" in rendered


def test_the_settings_view_survives_an_unknown_section(tmp_path: Path) -> None:
    handler, console, manager, _reinits = _handler(tmp_path)
    config = manager.load()

    console.print(
        handler._render_setting_ui(
            42,
            17,
            config,
            manager,
            None,
            changed=True,
            active_section="No Such Section",
            sections=["No Such Section"],
        )
    )

    rendered = console.export_text()
    assert "no settings" in rendered.lower()


# --------------------------------------------------------------------------- #
# Section tabs and key decoding
# --------------------------------------------------------------------------- #


class _ScriptedKeyboard:
    """Stand-in for msvcrt that replays a fixed byte script."""

    def __init__(self, *keys: bytes) -> None:
        self._keys = list(keys)

    def kbhit(self) -> bool:
        return bool(self._keys)

    def getch(self) -> bytes:
        return self._keys.pop(0)


@pytest.mark.parametrize(
    "keys, expected",
    [
        ((b"\x00", b"H"), "up"),
        ((b"\xe0", b"P"), "down"),
        ((b"\xe0", b"K"), "left"),
        ((b"\xe0", b"M"), "right"),
        ((b"\x00", b"I"), "pgup"),
        ((b"\x00", b"Q"), "pgdn"),
        ((b"\x00", b"G"), "home"),
        ((b"\x00", b"O"), "end"),
        ((b"\x00", b"\x0f"), "shift-tab"),
        ((b"\t",), "tab"),
        ((b"[",), "shift-tab"),
        ((b"]",), "tab"),
        ((b"\r",), "enter"),
        ((b"\x1b",), "escape"),
        ((b" ",), "right"),
        ((b"k",), "up"),
        ((b"J",), "down"),
        ((b"H",), "left"),
        ((b"L",), "right"),
        ((b"3",), "digit:3"),
        ((b"0",), "digit:0"),
        ((b"z",), ""),
        ((b"\x00", b"\x99"), ""),
    ],
)
def test_key_decoding_names_the_action_instead_of_comparing_bytes(
    tmp_path: Path, keys: tuple, expected: str
) -> None:
    """An extended-key `b"H"` is Up; a typed `b"H"` is left. One reader, one answer."""
    handler, _console, _manager, _reinits = _handler(tmp_path)

    assert handler._read_semantic_key(_ScriptedKeyboard(*keys)) == expected


def test_a_truncated_extended_key_does_not_hang_the_browser(tmp_path: Path) -> None:
    """A lead byte with no scan code behind it must resolve, not block."""
    handler, _console, _manager, _reinits = _handler(tmp_path)

    class _Truncated:
        def getch(self) -> bytes:
            raise OSError("console closed")

    assert handler._read_semantic_key(_Truncated()) == "escape"


def test_number_keys_select_the_tab_they_are_printed_with(tmp_path: Path) -> None:
    handler, _console, _manager, _reinits = _handler(tmp_path)
    sections = ["All", "Session", "Model", "Reasoning"]

    assert handler._setting_section_for_digit(sections, "1") == 0
    assert handler._setting_section_for_digit(sections, "4") == 3
    # Beyond the strip, and the non-digits the decoder never emits anyway.
    assert handler._setting_section_for_digit(sections, "5") == -1
    assert handler._setting_section_for_digit(sections, "0") == -1
    assert handler._setting_section_for_digit(sections, "") == -1
    assert handler._setting_section_for_digit([], "1") == -1
    # A tenth tab is reachable with the 0 key, matching the printed hotkey.
    assert handler._setting_section_for_digit(list("abcdefghij"), "0") == 9


def test_the_tab_strip_prints_the_key_that_selects_each_section(tmp_path: Path) -> None:
    """The strip is where a reader learns the tabs are switchable at all."""
    handler, console, _manager, _reinits = _handler(tmp_path)
    sections = ["All", "Session", "Model", "Reasoning"]

    console.print(handler._build_setting_tabs_line(sections, "Model"))

    rendered = console.export_text()
    for index, section in enumerate(sections):
        assert f"{handler._setting_section_hotkey(index)} {section}" in rendered


def test_the_tab_strip_stops_offering_keys_past_the_tenth_section(tmp_path: Path) -> None:
    handler, _console, _manager, _reinits = _handler(tmp_path)

    assert handler._setting_section_hotkey(0) == "1"
    assert handler._setting_section_hotkey(8) == "9"
    assert handler._setting_section_hotkey(9) == "0"
    assert handler._setting_section_hotkey(10) == ""


def test_tab_and_number_keys_both_change_the_rendered_section(tmp_path: Path) -> None:
    """End-to-end through the real key loop: the tabs are not decoration."""
    handler, _console, manager, _reinits = _handler(tmp_path)
    sections = handler._setting_sections(handler._get_setting_items(manager.load(), manager, None))
    assert len(sections) >= 4, sections

    seen: List[str] = []
    original = handler._render_setting_ui

    def spy(selected_idx, scroll_offset, *args, **kwargs):
        seen.append(str(kwargs.get("active_section")))
        return original(selected_idx, scroll_offset, *args, **kwargs)

    handler._render_setting_ui = spy
    # The browser drains queued keys on entry, which would eat the whole script.
    handler._drain_msvcrt_keyboard_buffer = lambda *_a, **_k: 0
    keyboard = _ScriptedKeyboard(b"\t", b"4", b"\x00", b"\x0f", b"1", b"\x1b")
    with mock.patch.dict(sys.modules, {"msvcrt": keyboard}):
        assert handler._cmd_setting_ui() is True

    # Initial view, Tab forward, digit jump, Shift+Tab back, digit home.
    assert seen[0] == sections[0]
    assert seen[1] == sections[1]
    assert seen[2] == sections[3]
    assert seen[3] == sections[2]
    assert seen[4] == sections[0]


def test_an_unassigned_number_key_says_so_instead_of_moving(tmp_path: Path) -> None:
    handler, _console, manager, _reinits = _handler(tmp_path)
    sections = handler._setting_sections(handler._get_setting_items(manager.load(), manager, None))
    assert len(sections) < 10, "this test needs an unassigned 0 key"

    seen: List[tuple] = []
    original = handler._render_setting_ui

    def spy(selected_idx, scroll_offset, *args, **kwargs):
        # The feedback line is retired on the next keypress, so read it here.
        seen.append((str(kwargs.get("active_section")), handler._setting_ui_message))
        return original(selected_idx, scroll_offset, *args, **kwargs)

    handler._render_setting_ui = spy
    handler._drain_msvcrt_keyboard_buffer = lambda *_a, **_k: 0
    with mock.patch.dict(sys.modules, {"msvcrt": _ScriptedKeyboard(b"0", b"\x1b")}):
        assert handler._cmd_setting_ui() is True

    assert [entry[0] for entry in seen] == [sections[0], sections[0]]
    assert seen[-1][1] == "No section 0."


def test_setting_status_lists_the_whole_catalog(tmp_path: Path) -> None:
    handler, console, manager, _reinits = _handler(tmp_path)

    assert handler.handle("/setting status") is True

    rendered = console.export_text()
    keys = [
        str(item.get("name"))
        for item in handler._get_setting_items(manager.load(), manager, None)
    ]
    missing = [name for name in keys if name not in rendered]
    assert not missing, f"settings hidden from /setting status: {missing}"
