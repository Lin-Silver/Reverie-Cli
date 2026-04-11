from __future__ import annotations

import json
import threading
from pathlib import Path

from rich.console import Console

from reverie.agent.agent import (
    THINKING_END_MARKER,
    THINKING_START_MARKER,
    _StreamingTurnState,
)
from reverie.cli.display import DisplayComponents
from reverie.cli.interface import ReverieInterface, _load_task_drawer_snapshot
from reverie.context_engine.parsers.python_parser import PythonParser
from reverie.context_engine.symbol_table import Symbol, SymbolKind, SymbolTable
from reverie.gamer import reference_intelligence as gamer_reference_intelligence
from reverie.sse import iter_sse_data_strings
from reverie.tools.command_exec import CommandExecTool


class _FakeStreamingResponse:
    def __init__(self, lines: list[str]):
        self._lines = list(lines)

    def iter_lines(self, decode_unicode: bool = True, chunk_size: int = 0):
        assert decode_unicode is True
        assert chunk_size >= 512
        for line in self._lines:
            yield line


def _symbol(name: str, qualified_name: str, file_path: str, line: int) -> Symbol:
    return Symbol(
        name=name,
        qualified_name=qualified_name,
        kind=SymbolKind.FUNCTION,
        file_path=file_path,
        start_line=line,
        end_line=line + 1,
        language="python",
    )


def test_python_parser_handles_utf8_bom(tmp_path: Path) -> None:
    target = tmp_path / "bom_module.py"
    target.write_text("\ufeffdef greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8")

    parser = PythonParser(tmp_path)
    result = parser.parse_file(target)

    assert result.success is True
    assert any(symbol.name == "greet" for symbol in result.symbols)


def test_symbol_table_search_respects_limit(tmp_path: Path) -> None:
    table = SymbolTable()
    table.add_symbol(_symbol("SearchThing", "pkg.SearchThing", str(tmp_path / "a.py"), 1))
    table.add_symbol(_symbol("SearchTools", "pkg.SearchTools", str(tmp_path / "b.py"), 10))
    table.add_symbol(_symbol("SearchState", "pkg.SearchState", str(tmp_path / "c.py"), 20))

    results = table.search("search", limit=2)

    assert len(results) == 2
    assert all("search" in symbol.name.lower() for symbol in results)


def test_iter_sse_data_strings_handles_multiline_events_and_raw_json() -> None:
    response = _FakeStreamingResponse(
        [
            "event: message",
            'data: {"type":"content","text":"hello"}',
            'data: {"type":"content","text":" world"}',
            "",
            '{"choices":[{"delta":{"content":"tail"}}]}',
            "data: [DONE]",
            "",
        ]
    )

    payloads = list(iter_sse_data_strings(response))

    assert payloads == [
        '{"type":"content","text":"hello"}\n{"type":"content","text":" world"}',
        '{"choices":[{"delta":{"content":"tail"}}]}',
    ]


def test_streaming_turn_state_hides_end_token_and_closes_thinking() -> None:
    state = _StreamingTurnState()

    chunks = []
    chunks.extend(state.add_reasoning("Planning"))
    chunks.extend(state.add_content("Hello //EN"))
    chunks.extend(state.add_content("D//world"))
    chunks.extend(state.flush())

    assert chunks == [
        THINKING_START_MARKER,
        "Planning",
        THINKING_END_MARKER,
        "Hello ",
        "world",
    ]
    assert state.cleaned_content() == "Hello world"


def test_streaming_turn_state_accumulates_tool_call_arguments() -> None:
    state = _StreamingTurnState()

    state.update_tool_call(0, tool_call_id="call_1", name="shell")
    state.update_tool_call(0, arguments='{"command":"pw', append_arguments=True)
    state.update_tool_call(0, arguments='sh"}', append_arguments=True, thought_signature="sig-1")

    assert state.tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "thought_signature": "sig-1",
            "function": {
                "name": "shell",
                "arguments": '{"command":"pwsh"}',
            },
        }
    ]


def test_command_exec_builds_powershell_for_pipelines_and_cmdlets(tmp_path: Path) -> None:
    tool = CommandExecTool({"project_root": tmp_path})

    pipeline_invocation = tool._build_invocation(
        "Get-ChildItem . | Select-Object -First 1",
        tmp_path,
    )
    cmdlet_invocation = tool._build_invocation(
        'Select-String -Path *.py -Pattern "TODO"',
        tmp_path,
    )

    assert pipeline_invocation["executor"] == "powershell"
    assert " | " in pipeline_invocation["display"]
    assert "'|'" not in pipeline_invocation["display"]

    assert cmdlet_invocation["executor"] == "powershell"
    assert cmdlet_invocation["argv"][0].lower().endswith(("powershell.exe", "pwsh"))


def test_task_drawer_snapshot_reads_json_artifact_in_display_order(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "task_list.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "root",
                        "name": "Refactor CLI surface",
                        "state": "IN_PROGRESS",
                        "children": ["child"],
                        "parent_id": None,
                    },
                    {
                        "id": "child",
                        "name": "Compact tool logs",
                        "state": "COMPLETED",
                        "children": [],
                        "parent_id": "root",
                    },
                    {
                        "id": "extra",
                        "name": "Add todo drawer",
                        "state": "NOT_STARTED",
                        "children": [],
                        "parent_id": None,
                    },
                ],
                "root_tasks": ["root", "extra"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = _load_task_drawer_snapshot(tmp_path, max_visible=2)

    assert snapshot["total"] == 3
    assert snapshot["completed"] == 1
    assert snapshot["hidden"] == 1
    assert [item["name"] for item in snapshot["tasks"]] == [
        "Refactor CLI surface",
        "Compact tool logs",
    ]
    assert snapshot["tasks"][1]["indent"] == 1


def test_display_compacts_tool_result_into_single_row_with_preview() -> None:
    console = Console(record=True, force_terminal=False, width=120)
    display = DisplayComponents(console)
    display.set_tool_output_style("condensed")

    display.show_tool_invocation(
        tool_name="str_replace_editor",
        message="Viewing file: reverie/cli/interface.py",
        arguments={"command": "view", "path": "reverie/cli/interface.py", "view_range": [50, 60]},
        tool_call_id="call_123",
    )
    assert console.export_text() == ""

    display.show_tool_result_card(
        tool_name="str_replace_editor",
        success=True,
        output=(
            "File: reverie/cli/interface.py\n"
            "Total lines: 2784\n"
            "Showing lines 50-60\n"
            "\n"
            "  50 | class StreamingFooter:\n"
            "  51 |     def __rich__(self):\n"
        ),
        arguments={"command": "view", "path": "reverie/cli/interface.py", "view_range": [50, 60]},
        tool_call_id="call_123",
    )

    rendered = console.export_text()
    assert "ReadFile" in rendered
    assert "Read lines 50-60 of 2784" in rendered
    assert "50 | class StreamingFooter:" in rendered


def test_display_full_tool_output_style_keeps_expanded_result_block() -> None:
    console = Console(record=True, force_terminal=False, width=120)
    display = DisplayComponents(console)
    display.set_tool_output_style("full")

    display.show_tool_result_card(
        tool_name="command_exec",
        success=True,
        output="$ git status\nWorking directory: .\nExecutor: subprocess\nPolicy: workspace_blacklist\nExit code: 0\nDuration: 12ms\n\n--- STDOUT ---\nclean tree",
        arguments={"command": "git status"},
        tool_call_id="call_full",
    )

    rendered = console.export_text()
    assert "command_exec" in rendered.lower()
    assert "clean tree" in rendered
    assert "done" in rendered.lower()


def test_display_condensed_command_result_skips_preview_after_live_progress() -> None:
    console = Console(record=True, force_terminal=False, width=120)
    display = DisplayComponents(console)
    display.set_tool_output_style("condensed")

    display.show_tool_result_card(
        tool_name="command_exec",
        success=True,
        output=(
            "$ git status\n"
            "Working directory: .\n"
            "Executor: subprocess\n"
            "Policy: workspace_blacklist\n"
            "Exit code: 0\n"
            "Duration: 12ms\n\n"
            "--- STDOUT ---\n"
            "clean tree"
        ),
        arguments={"command": "git status"},
        had_live_progress=True,
    )

    rendered = console.export_text()
    assert "Exit 0 in 12ms" in rendered
    assert "clean tree" not in rendered


def test_command_exec_emits_incremental_ui_progress(tmp_path: Path) -> None:
    events = []
    tool = CommandExecTool(
        {
            "project_root": tmp_path,
            "ui_event_handler": events.append,
            "active_tool_call_id": "call_stream",
            "active_tool_name": "command_exec",
        }
    )

    command = 'python -u -c "import sys; print(\'alpha\'); print(\'beta\', file=sys.stderr)"'
    result = tool.execute(command=command)

    assert result.success is True
    assert any(event.get("kind") == "tool_progress" and "alpha" in event.get("text", "") for event in events)
    assert any(event.get("kind") == "tool_progress" and "beta" in event.get("text", "") for event in events)


def test_reference_catalog_scan_uses_cache_on_repeated_workspace_reads(tmp_path: Path) -> None:
    gamer_reference_intelligence._REFERENCE_SCAN_CACHE.clear()
    references_root = tmp_path / "references"
    (references_root / "godot-tps-demo" / "player").mkdir(parents=True, exist_ok=True)
    (references_root / "godot-tps-demo" / "enemies" / "red_robot").mkdir(parents=True, exist_ok=True)
    (references_root / "godot-demo-projects" / "mono" / "squash_the_creeps").mkdir(parents=True, exist_ok=True)

    (references_root / "godot-tps-demo" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (references_root / "godot-tps-demo" / "player" / "player.gd").write_text(
        "extends CharacterBody3D\n",
        encoding="utf-8",
    )
    (references_root / "godot-tps-demo" / "player" / "player_input.gd").write_text(
        "extends MultiplayerSynchronizer\n",
        encoding="utf-8",
    )
    (references_root / "godot-tps-demo" / "enemies" / "red_robot" / "red_robot.gd").write_text(
        "extends CharacterBody3D\n",
        encoding="utf-8",
    )
    (references_root / "godot-demo-projects" / "mono" / "squash_the_creeps" / "project.godot").write_text(
        "config_version=5\n",
        encoding="utf-8",
    )
    (references_root / "godot-demo-projects" / "mono" / "squash_the_creeps" / "Main.tscn").write_text(
        "[gd_scene format=3]\n",
        encoding="utf-8",
    )

    first = gamer_reference_intelligence.scan_reference_catalog(project_root=tmp_path)
    second = gamer_reference_intelligence.scan_reference_catalog(project_root=tmp_path)

    assert first["cache_status"] == "miss"
    assert second["cache_status"] == "hit"
    assert second["summary"]["repository_count"] >= 2


def test_interface_deduplicates_repeated_live_tool_progress_chunks() -> None:
    interface = ReverieInterface.__new__(ReverieInterface)
    interface._active_tool_details = {}
    interface._active_tool_lock = threading.Lock()

    payload = {
        "tool_call_id": "call_progress",
        "tool_name": "command_exec",
        "stream": "stdout",
        "text": "alpha\n",
    }
    interface._append_active_tool_progress(payload)
    interface._append_active_tool_progress(payload)
    interface._append_active_tool_progress({**payload, "text": "beta\n"})

    current = interface._active_tool_details["call_progress"]
    assert current["stdout"] == "alpha\nbeta\n"
    assert current["progress_event_count"] == 2

    summary = interface._clear_active_tool("call_progress")
    assert summary["had_live_progress"] is True
