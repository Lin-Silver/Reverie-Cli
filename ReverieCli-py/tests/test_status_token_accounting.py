"""Token accounting behind ``/status``.

``/status`` used to print a single ``Context Usage`` row built from its own
arithmetic: its own context-window lookup, its own numerator, and no guard for a
zero limit. The status line and ``/compact`` each did the same thing slightly
differently, so the same conversation could be reported three ways.

These tests hold the corrected shape in place:

* one counter and one built payload produce the number, and a per-message
  breakdown always reconciles with that number;
* the displayed compaction and rotation gates come from the same constants the
  agent enforces, so they cannot drift apart;
* the context window is read from the active model before the workspace default
  — the previous lookup asked ``Config`` for an ``active_model`` attribute it
  has never had, so every readout silently fell back to 128k;
* the live footer divides by the window the agent resolves rather than a second
  lookup of its own, and recolours at the agent's own gates;
* a zero or missing limit renders instead of raising ``ZeroDivisionError``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from rich.console import Console

from reverie.agent.agent import ReverieAgent
from reverie.cli.commands import CommandHandler
from reverie.session.workspace_stats import WorkspaceStatsManager


def _payload() -> List[Dict[str, Any]]:
    """A request payload with every segment /status attributes tokens to."""
    return [
        {"role": "system", "content": "You are Reverie. " * 40},
        {"role": "system", "content": "[WORKING MEMORY] earlier decisions " * 10},
        {"role": "user", "content": "Explain the indexer."},
        {
            "role": "assistant",
            "content": "Reading the file.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "indexer.py"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "read_file", "content": "def index(): ..." * 30},
    ]


def _agent(*, max_tokens: int = 200_000, payload: List[Dict[str, Any]] | None = None) -> ReverieAgent:
    """A bare agent carrying only what the token accounting reads."""
    agent = ReverieAgent.__new__(ReverieAgent)
    messages = list(payload if payload is not None else _payload())[2:]
    messages.append({"role": "assistant", "content": "Done.", "reasoning_content": "Weighing options. " * 20})
    agent.messages = messages
    agent.system_prompt = "You are Reverie. " * 40
    agent._prompt_history_limit = 60
    agent._token_estimate_cache_key = None
    agent._token_estimate_cache_value = 0
    agent._token_estimate_cache_time = 0.0
    agent.tool_executor = SimpleNamespace(context={})
    built = list(payload if payload is not None else _payload())
    agent._build_messages = lambda *args, **kwargs: [dict(item) for item in built]
    agent._resolve_max_context_tokens = lambda: max_tokens
    return agent


# ---------------------------------------------------------------------------
# the counter
# ---------------------------------------------------------------------------


def test_per_message_costs_sum_to_the_conversation_total() -> None:
    """A breakdown that does not reconcile with the total is a misleading readout.

    ``count_messages_tokens`` is what the compaction thresholds are compared
    against, so the per-message figure /status attributes to each segment has to
    add back up to it — envelope bytes and reply primer included.
    """
    messages = _payload()

    per_message = sum(WorkspaceStatsManager.count_message_tokens(item) for item in messages)

    assert per_message + 2 == WorkspaceStatsManager.count_messages_tokens(messages)


def test_non_dict_messages_cost_nothing_and_do_not_raise() -> None:
    assert WorkspaceStatsManager.count_message_tokens("not a message") == 0
    assert WorkspaceStatsManager.count_messages_tokens([None, "x"]) == 2


def test_tokenizer_disclosure_matches_whether_tiktoken_is_installed() -> None:
    """/status labels its own precision, so the label must track the real counter."""
    tokenizer = WorkspaceStatsManager.describe_tokenizer()

    assert tokenizer["label"]
    assert tokenizer["detail"]
    try:
        import tiktoken  # noqa: F401
    except Exception:
        assert tokenizer["exact"] is False
        assert tokenizer["name"] == "heuristic"
    else:
        assert tokenizer["exact"] is True
        assert tokenizer["name"] == "cl100k_base"


# ---------------------------------------------------------------------------
# the agent's breakdown
# ---------------------------------------------------------------------------


def test_breakdown_reconciles_with_the_number_the_thresholds_use() -> None:
    """Segments plus envelope must equal the total, and the total must equal the estimate.

    If the breakdown were counted separately from ``get_token_estimate`` the two
    could disagree inside one ``/status`` render, which is exactly the imprecision
    this report exists to remove.
    """
    agent = _agent()

    usage = agent.describe_context_usage()

    counted = sum(segment["tokens"] for segment in usage["segments"])
    assert counted + usage["overhead_tokens"] == usage["total_tokens"]
    assert usage["total_tokens"] == agent.get_token_estimate()
    assert usage["total_tokens"] > 0


def test_segments_name_the_prompt_parts_separately() -> None:
    """The system prompt is not lumped in with mid-conversation injected context."""
    agent = _agent()

    usage = agent.describe_context_usage()
    by_key = {segment["key"]: segment for segment in usage["segments"]}

    assert set(by_key) == {"system_prompt", "injected_context", "user", "assistant", "tool"}
    assert by_key["system_prompt"]["messages"] == 1
    assert by_key["injected_context"]["messages"] == 1
    assert by_key["tool"]["tokens"] > 0
    assert abs(sum(segment["share"] for segment in usage["segments"]) - 100.0) < 25.0


def test_gates_are_derived_from_the_ratios_the_agent_enforces() -> None:
    agent = _agent(max_tokens=200_000)

    usage = agent.describe_context_usage()

    assert usage["compaction_tokens"] == int(200_000 * ReverieAgent.CONTEXT_COMPACTION_RATIO)
    assert usage["rotation_tokens"] == int(200_000 * ReverieAgent.CONTEXT_ROTATION_RATIO)
    assert usage["remaining_tokens"] == 200_000 - usage["total_tokens"]
    assert 0.0 < usage["percentage"] < 100.0


def test_a_zero_context_limit_reports_unknown_rather_than_dividing() -> None:
    """A hand-edited ``max_context_tokens: 0`` used to crash the whole command."""
    agent = _agent(max_tokens=0)

    usage = agent.describe_context_usage()

    assert usage["max_tokens"] == 0
    assert usage["percentage"] == 0.0
    assert usage["remaining_tokens"] == 0
    assert usage["compaction_tokens"] == 0


def test_reasoning_kept_in_history_is_reported_apart_from_the_prompt() -> None:
    """Reasoning is stored but stripped from most payloads; it is not prompt cost."""
    payload = _payload()
    agent = _agent(payload=payload)

    usage = agent.describe_context_usage()

    assert usage["reasoning_tokens"] > 0
    assert usage["payload_message_count"] == len(payload)
    assert usage["history_message_count"] == len(agent.messages)
    assert usage["history_limit"] == 60


def test_the_heaviest_message_is_identified_with_a_preview() -> None:
    agent = _agent()

    heaviest = agent.describe_context_usage()["heaviest_message"]

    assert heaviest["tokens"] > 0
    assert heaviest["index"] >= 0
    assert heaviest["role"]
    assert len(heaviest["preview"]) <= 120


def test_the_counter_falls_back_to_the_class_when_the_context_has_none() -> None:
    """Subagents run without a workspace stats manager and still need real counts."""
    agent = _agent()

    assert agent._token_counter() is WorkspaceStatsManager

    recorded: List[Any] = []

    class _Manager:
        @staticmethod
        def count_messages_tokens(messages: Any) -> int:
            recorded.append(messages)
            return 1234

        @staticmethod
        def count_message_tokens(message: Any) -> int:
            return 7

    agent.tool_executor.context["workspace_stats_manager"] = _Manager()

    assert agent.get_token_estimate() == 1234
    assert recorded


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------


class _ConfigManager:
    """Answers the two lookups the context-limit resolver makes."""

    def __init__(self, *, model_limit: int | None, config_limit: int = 128_000) -> None:
        self._model_limit = model_limit
        self._config_limit = config_limit

    def get_active_model(self) -> Any:
        return SimpleNamespace(
            model_display_name="Muse Glimmer",
            base_url="https://example.invalid/v1",
            max_context_tokens=self._model_limit,
        )

    def load(self) -> Any:
        return SimpleNamespace(max_context_tokens=self._config_limit, active_model_source="standard")

    def get_active_config_path(self) -> str:
        return "/tmp/reverie/config.json"


class _StatsManager:
    def __init__(self, dashboard: Dict[str, Any]) -> None:
        self._dashboard = dashboard

    def build_dashboard_data(self) -> Dict[str, Any]:
        return self._dashboard


def _dashboard() -> Dict[str, Any]:
    return {
        "total_input_tokens": 902_111,
        "total_output_tokens": 143_090,
        "total_calls": 512,
        "session_usage": [
            {"session_id": "s-1", "input_tokens": 41_220, "output_tokens": 6_910, "calls": 22},
        ],
        "model_usage": [
            {"model_display_name": "Bulk Reader", "input_tokens": 500_000, "output_tokens": 1_000, "calls": 12},
            {"model_display_name": "Deep Thinker", "input_tokens": 400_000, "output_tokens": 900_000, "calls": 500},
        ],
    }


def _handler(**overrides: Any) -> tuple[CommandHandler, Console]:
    console = Console(record=True, width=200, force_terminal=False, no_color=True)
    context: Dict[str, Any] = {
        "agent": _agent(),
        "config_manager": _ConfigManager(model_limit=1_000_000),
        "session_manager": SimpleNamespace(
            get_current_session=lambda: SimpleNamespace(id="s-1", name="main", messages=[1, 2, 3])
        ),
        "workspace_stats_manager": _StatsManager(_dashboard()),
    }
    context.update(overrides)
    return CommandHandler(console, context), console


def test_the_context_limit_comes_from_the_active_model() -> None:
    """``Config`` has no ``active_model`` attribute, so the old lookup always got 128k."""
    handler, _console = _handler()

    assert handler._resolve_context_limit(_ConfigManager(model_limit=1_000_000)) == 1_000_000
    assert handler._resolve_context_limit(_ConfigManager(model_limit=None)) == 128_000
    assert handler._resolve_context_limit(_ConfigManager(model_limit=None, config_limit=0)) == 128_000
    assert handler._resolve_context_limit(None) == 128_000


def test_the_compact_snapshot_uses_the_model_window_too() -> None:
    handler, _console = _handler()
    agent = _agent()

    snapshot = handler._get_context_usage_snapshot(agent, _ConfigManager(model_limit=32_000))

    assert snapshot["max_tokens"] == 32_000
    assert snapshot["total_tokens"] > 0
    assert snapshot["percentage"] > 0.0


def test_status_prints_the_whole_token_budget() -> None:
    handler, console = _handler()

    assert handler.cmd_status("") is True
    output = console.export_text()

    for label in (
        "Context Usage",
        "Headroom",
        "Counted By",
        "Safety Gates",
        "Prompt Makeup",
        "Prompt Messages",
        "Largest Message",
        "Cached Reasoning",
        "Session Tokens",
        "Workspace Tokens",
        "Top Model",
    ):
        assert label in output, f"/status no longer reports {label!r}"


def test_status_names_the_biggest_spender_by_total_not_by_input() -> None:
    """The dashboard orders by input tokens; the row claims the largest total."""
    handler, console = _handler()

    handler.cmd_status("")
    output = console.export_text()

    assert "Deep Thinker" in output
    assert "Bulk Reader" not in output


def test_status_survives_a_zero_context_limit() -> None:
    handler, console = _handler(
        agent=_agent(max_tokens=0),
        config_manager=_ConfigManager(model_limit=None, config_limit=0),
    )

    assert handler.cmd_status("") is True
    assert "unknown" in console.export_text()


def test_status_still_renders_without_an_agent_or_stats() -> None:
    handler, console = _handler(agent=None, workspace_stats_manager=None)

    assert handler.cmd_status("") is True
    output = console.export_text()
    assert "Context Usage" not in output
    assert "Reverie System Status" in output


# ---------------------------------------------------------------------------
# the live footer
# ---------------------------------------------------------------------------


def _interface(*, max_tokens: int = 200_000):
    """A bare interface carrying only what the footer's context row reads."""
    from reverie.cli.interface import ReverieInterface
    from reverie.cli.theme import DECO, THEME

    interface = ReverieInterface.__new__(ReverieInterface)
    interface.console = Console(record=True, width=140, force_terminal=False, no_color=True)
    interface.theme = THEME
    interface.deco = DECO
    interface.agent = _agent(max_tokens=max_tokens)
    interface.config_manager = SimpleNamespace(
        load=lambda: SimpleNamespace(
            active_model=SimpleNamespace(
                model_display_name="Muse Glimmer",
                provider="openai-chat",
                max_context_tokens=1_000_000,
            ),
            mode="reverie",
            active_model_source="standard",
        )
    )
    interface.project_root = Path("/tmp/reverie")
    interface.total_active_time = 12.0
    interface.current_task_start = None
    return interface


def _footer_text(interface) -> str:
    interface.console.print(interface._get_status_line())
    return interface.console.export_text()


def _ansi(color: str) -> str:
    """The truecolor escape Rich writes for one theme hex value."""
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    return f"\x1b[38;2;{red};{green};{blue}m"


def test_the_footer_divides_by_the_same_window_the_gates_use() -> None:
    """The footer used to read ``active_model.max_context_tokens`` on its own.

    The agent resolves the window itself, and that resolution is what the
    compaction gate compares against, so a footer with its own lookup could show
    a comfortable percentage while the agent was already compacting.
    """
    interface = _interface(max_tokens=200_000)

    output = _footer_text(interface)

    # 1M is the model record's own figure; 200K is what the agent enforces.
    assert "/200K" in output
    assert "/1M" not in output


def test_the_footer_turns_amber_at_the_compaction_gate_not_at_a_hand_picked_70() -> None:
    from reverie.cli.theme import THEME

    calm = _interface(max_tokens=200_000)
    calm.console.print(calm._get_status_line())
    assert _ansi(THEME.AMBER_GLOW) not in calm.console.export_text(styles=True)

    crowded = _interface(max_tokens=200_000)
    ratio = ReverieAgent.CONTEXT_COMPACTION_RATIO
    # Shrink the window until the live payload sits exactly on the compaction gate.
    crowded.agent._resolve_max_context_tokens = lambda: int(
        crowded.agent.get_token_estimate() / ratio
    )

    crowded.console.print(crowded._get_status_line())

    assert _ansi(THEME.AMBER_GLOW) in crowded.console.export_text(styles=True)


def test_the_footer_renders_a_zero_window_without_dividing() -> None:
    interface = _interface(max_tokens=0)

    output = _footer_text(interface)

    assert "/?" in output
    assert "(0%)" not in output
