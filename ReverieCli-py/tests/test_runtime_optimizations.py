from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import requests
from rich.console import Console

from reverie.agent.agent import (
    THINKING_END_MARKER,
    THINKING_START_MARKER,
    _StreamingTurnState,
    _should_recover_partial_stream_error,
    parse_tool_arguments,
)
from reverie.agent.tool_executor import ToolExecutor
from reverie.cli.display import DisplayComponents
from reverie.cli.interface import ReverieInterface, _load_task_drawer_snapshot
from reverie.context_engine.dependency_graph import DependencyGraph
from reverie.context_engine.parsers.python_parser import PythonParser
from reverie.context_engine.symbol_table import Symbol, SymbolKind, SymbolTable
from reverie.gamer import reference_intelligence as gamer_reference_intelligence
from reverie.sse import iter_sse_data_strings
from reverie.tools.codebase_retrieval import CodebaseRetrievalTool
from reverie.tools.command_exec import CommandExecTool
from reverie.tools.task_manager import TaskManagerTool, cleanup_completed_task_artifacts
from reverie.tools.web_search import WebFetchTool, WebSearchTool
from reverie.config import Config, ModelConfig


class _FakeStreamingResponse:
    def __init__(self, lines: list[str]):
        self._lines = list(lines)

    def iter_lines(self, decode_unicode: bool = True, chunk_size: int = 0):
        assert decode_unicode is True
        assert chunk_size >= 512
        for line in self._lines:
            yield line


class _BrokenStreamingResponse:
    def __init__(self, lines: list[str], error: Exception):
        self._lines = list(lines)
        self._error = error

    def iter_lines(self, decode_unicode: bool = True, chunk_size: int = 0):
        assert decode_unicode is True
        assert chunk_size >= 512
        for line in self._lines:
            yield line
        raise self._error


class _FakeHTTPResponse:
    def __init__(self, body: str, *, status_code: int = 200, content_type: str = "text/html; charset=utf-8"):
        self.status_code = status_code
        self.text = body
        self.content = body.encode("utf-8")
        self.headers = {"content-type": content_type}


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


def test_iter_sse_data_strings_tolerates_premature_close_after_partial_payload() -> None:
    response = _BrokenStreamingResponse(
        [
            'data: {"type":"content","text":"hello"}',
            "",
        ],
        requests.exceptions.ChunkedEncodingError("peer closed connection without sending complete message body"),
    )

    payloads = list(iter_sse_data_strings(response))

    assert payloads == ['{"type":"content","text":"hello"}']


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


def test_streaming_turn_state_routes_inline_think_tags_to_reasoning() -> None:
    state = _StreamingTurnState()

    chunks = []
    chunks.extend(state.add_content("<thi"))
    chunks.extend(state.add_content("nk>Plan first"))
    chunks.extend(state.add_content("</thi"))
    chunks.extend(state.add_content("nk>\nAnswer //END//"))
    chunks.extend(state.flush())

    assert chunks == [
        THINKING_START_MARKER,
        "Plan first",
        THINKING_END_MARKER,
        "\nAnswer ",
    ]
    assert state.collected_thinking == "Plan first"
    assert state.cleaned_content() == "Answer"


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


def test_parse_tool_arguments_preserves_long_malformed_file_content() -> None:
    body = (
        '# 技术方案 "Vulkan"\n'
        "```json\n"
        '{"path":"demo.md","content":"example","pipeline":"deferred","layers":3}\n'
        "```\n"
        + "长文本段落\n" * 200
    )
    raw = '{"path":"task.md","content":"' + body + '","overwrite":true}'

    args = parse_tool_arguments(raw)

    assert args["path"] == "task.md"
    assert args["content"] == body
    assert args["overwrite"] is True


def test_parse_tool_arguments_salvages_unterminated_long_content() -> None:
    body = "# Draft\n" + ("details\n" * 500)
    raw = '{"path":"task.md","content":"' + body

    args = parse_tool_arguments(raw)

    assert args["path"] == "task.md"
    assert args["content"] == body


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


def test_command_exec_allows_toolchain_registry_and_package_references(tmp_path: Path) -> None:
    tool = CommandExecTool({"project_root": tmp_path})

    npm_invocation = tool._build_invocation("npm install @types/node", tmp_path)
    cargo_invocation = tool._build_invocation("cargo add serde/derive", tmp_path)
    docker_invocation = tool._build_invocation("docker pull ghcr.io/example/app:latest", tmp_path)

    assert npm_invocation["executor"] == "subprocess"
    assert cargo_invocation["executor"] == "subprocess"
    assert docker_invocation["executor"] == "subprocess"


def test_command_exec_keeps_workspace_path_guard_for_toolchain_paths(tmp_path: Path) -> None:
    tool = CommandExecTool({"project_root": tmp_path})

    try:
        tool._build_invocation("docker build -f ../Dockerfile .", tmp_path)
    except ValueError as exc:
        assert "parent-directory traversal" in str(exc)
    else:
        raise AssertionError("docker path traversal should be blocked")


def test_command_exec_prefers_workspace_venv_for_python_package_installs(tmp_path: Path) -> None:
    venv = tmp_path / ".venv"
    bin_dir = venv / ("Scripts" if sys.platform == "win32" else "bin")
    bin_dir.mkdir(parents=True)
    tool = CommandExecTool({"project_root": tmp_path})

    invocation = tool._build_invocation("python -m pip install requests", tmp_path)

    env = invocation["env_overrides"]
    assert env["VIRTUAL_ENV"] == str(venv)
    assert env["PATH"].split(";")[0] == str(bin_dir) if sys.platform == "win32" else env["PATH"].split(":")[0] == str(bin_dir)


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
    assert snapshot["hidden"] == 0
    assert [item["name"] for item in snapshot["tasks"]] == [
        "Refactor CLI surface",
        "Compact tool logs",
        "Add todo drawer",
    ]
    assert snapshot["tasks"][1]["indent"] == 1


def test_task_drawer_prefers_markdown_over_stale_json(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    json_path = artifacts_dir / "task_list.json"
    markdown_path = artifacts_dir / "task.md"
    json_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "root",
                        "name": "Wire local repository",
                        "state": "NOT_STARTED",
                        "children": [],
                        "parent_id": None,
                    }
                ],
                "root_tasks": ["root"],
            }
        ),
        encoding="utf-8",
    )
    markdown_path.write_text("[x] Wire local repository\n[ ] Add persistence tests\n", encoding="utf-8")

    snapshot = _load_task_drawer_snapshot(tmp_path)

    assert snapshot["source"] == "markdown"
    assert snapshot["total"] == 2
    assert snapshot["completed"] == 1
    assert [item["state"] for item in snapshot["tasks"]] == ["COMPLETED", "NOT_STARTED"]


def test_task_manager_updates_by_exact_name_and_syncs_checklist(tmp_path: Path) -> None:
    tool = TaskManagerTool({"project_root": tmp_path})

    added = tool.execute(action="add", tasks=["Add DB schema", "Add repository tests"])
    assert added.success is True

    updated = tool.execute(action="update", target="Add DB schema", status="done")

    assert updated.success is True
    checklist = (tmp_path / "artifacts" / "task.md").read_text(encoding="utf-8")
    assert "[x] Add DB schema" in checklist
    assert "[ ] Add repository tests" in checklist
    assert not (tmp_path / "artifacts" / "task_list.json").exists()


def test_task_manager_imports_legacy_json_then_saves_markdown_only(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    legacy_json = artifacts_dir / "task_list.json"
    legacy_json.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "root",
                        "name": "Migrate task persistence",
                        "state": "IN_PROGRESS",
                        "children": ["child"],
                        "parent_id": None,
                    },
                    {
                        "id": "child",
                        "name": "Keep checklist editable",
                        "state": "COMPLETED",
                        "children": [],
                        "parent_id": "root",
                    },
                ],
                "root_tasks": ["root"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tool = TaskManagerTool({"project_root": tmp_path})
    result = tool.execute(action="list")

    assert result.success is True
    checklist = (artifacts_dir / "task.md").read_text(encoding="utf-8")
    assert "[/] Migrate task persistence" in checklist
    assert "  [x] Keep checklist editable" in checklist
    assert not legacy_json.exists()


def test_completed_task_artifact_cleanup_removes_finished_checklists(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    canonical = artifacts_dir / "task.md"
    legacy = artifacts_dir / "Tasks.md"
    canonical.write_text("[x] Add task cleanup\n  [X] Verify cleanup\n", encoding="utf-8")
    legacy.write_text("[x]Finish legacy slice\n", encoding="utf-8")

    deleted = cleanup_completed_task_artifacts(tmp_path)

    assert set(path.name for path in deleted) == {"Tasks.md", "task.md"}
    assert not canonical.exists()
    assert not legacy.exists()


def test_completed_task_artifact_cleanup_keeps_incomplete_checklists(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    canonical = artifacts_dir / "task.md"
    atlas = artifacts_dir / "Tasks.md"
    canonical.write_text("[x] Add task cleanup\n[ ] Verify cleanup\n", encoding="utf-8")
    atlas.write_text("Main task\n\nSubgoal 1\n[x]Finish slice\n[/]Run validation\n", encoding="utf-8")

    deleted = cleanup_completed_task_artifacts(tmp_path)

    assert deleted == []
    assert canonical.exists()
    assert atlas.exists()


def test_model_config_omits_null_context_tokens_on_save() -> None:
    payload = ModelConfig(
        model="example-model",
        model_display_name="Example",
        base_url="https://example.invalid/v1",
        max_context_tokens=None,
    ).to_dict()

    assert "max_context_tokens" not in payload


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


def test_web_search_defaults_to_link_discovery_without_fetch(monkeypatch) -> None:
    tool = WebSearchTool()
    tool._available = True

    monkeypatch.setattr(
        tool,
        "_search_ddg",
        lambda *args, **kwargs: [
            {
                "title": "Modrinth API",
                "href": "https://docs.modrinth.com/api/",
                "body": "Official API docs",
                "rank": 1,
            }
        ],
    )
    monkeypatch.setattr(tool, "_search_brave", lambda *args, **kwargs: [])

    def fail_fetch(*args, **kwargs):
        raise AssertionError("web_search should not fetch page content by default")

    monkeypatch.setattr(tool, "_fetch_page_payload", fail_fetch)

    result = tool.execute(query="Modrinth API", max_results=5)

    assert result.success is True
    assert result.data["settings"]["fetch_content"] is False
    assert "https://docs.modrinth.com/api/" in result.output
    assert "Fetch Status" not in result.output


def test_web_fetch_reads_selected_urls(monkeypatch) -> None:
    tool = WebFetchTool()
    tool._available = True

    monkeypatch.setattr(
        tool,
        "_fetch_page_payload",
        lambda url, **kwargs: {
            "fetch_status": "ok",
            "fetched_title": "Modrinth API",
            "fetched_description": "API docs",
            "fetched_content": "Use project versions endpoints for downloads.",
            "outbound_links": ["https://api.modrinth.com/v2/"],
        },
    )

    result = tool.execute(
        urls=["https://docs.modrinth.com/api/", "not-a-url", "https://docs.modrinth.com/api/"],
        max_content_chars=2000,
    )

    assert result.success is True
    assert result.data["count"] == 1
    assert "Use project versions endpoints for downloads." in result.output
    assert result.data["results"][0]["url"] == "https://docs.modrinth.com/api"


def test_web_fetch_extracts_wechat_style_metadata_and_media(monkeypatch) -> None:
    tool = WebFetchTool()
    tool._available = True

    html = """
    <html>
      <head>
        <meta property="og:title" content="AI应用丨周长最短和面积最大问题.html">
        <meta property="og:description" content="应用界面整体显示和动态演示效果">
        <meta property="og:site_name" content="微信公众平台">
        <meta name="author" content="Mr DaBai">
        <meta property="og:image" content="https://mmbiz.qpic.cn/cover/0?wx_fmt=jpeg">
      </head>
      <body>
        <h1 id="activity-name">fallback title</h1>
        <div id="js_content">
          <p>三下人教版教科书题目说明。这里是一段足够长的正文，用来模拟微信公众号文章里的教学应用介绍、界面说明、动态演示和应用获取方式。</p>
          <p>继续补充正文长度，确保主内容节点被选中，并且不会退化成整个 body 的杂乱文本。</p>
          <img data-src="https://mmbiz.qpic.cn/demo/screenshot/640?wx_fmt=png&amp;from=appmsg" data-w="1080" alt="应用完整动态演示效果">
        </div>
      </body>
    </html>
    """

    monkeypatch.setattr(tool, "_request_with_retry", lambda *args, **kwargs: _FakeHTTPResponse(html))

    result = tool.execute(url="https://mp.weixin.qq.com/s/example", max_content_chars=4000)

    assert result.success is True
    fetched = result.data["results"][0]
    assert fetched["fetched_title"] == "AI应用丨周长最短和面积最大问题.html"
    assert fetched["fetched_author"] == "Mr DaBai"
    assert fetched["fetched_site_name"] == "微信公众平台"
    assert len(fetched["media_assets"]) == 2
    assert any(asset["url"].startswith("https://mmbiz.qpic.cn/demo/screenshot/640") for asset in fetched["media_assets"])
    assert "Media Assets" in result.output


def test_web_fetch_marks_verification_pages_as_blocked(monkeypatch) -> None:
    tool = WebFetchTool()
    tool._available = True

    html = """
    <html>
      <head><title>Security Check</title></head>
      <body><main>请完成安全验证后继续访问。This page is checking your browser before access.</main></body>
    </html>
    """
    monkeypatch.setattr(tool, "_request_with_retry", lambda *args, **kwargs: _FakeHTTPResponse(html))

    result = tool.execute(url="https://example.com/protected", max_content_chars=4000)

    assert result.success is True
    fetched = result.data["results"][0]
    assert fetched["fetch_status"] == "blocked"
    assert "verification-gated page" in fetched["fetched_content"]


def test_web_search_treats_direct_url_as_candidate() -> None:
    tool = WebSearchTool()
    tool._available = True

    result = tool.execute(query="https://example.com/docs", max_results=5)

    assert result.success is True
    assert result.data["engine"] == "direct_url"
    assert result.data["results"][0]["href"] == "https://example.com/docs"


def test_vision_upload_is_not_registered_as_builtin_tool(tmp_path: Path) -> None:
    executor = ToolExecutor(project_root=tmp_path)

    schema_names = {
        schema.get("function", {}).get("name")
        for schema in executor.get_tool_schemas(mode="reverie")
    }

    assert "vision_upload" not in schema_names
    assert executor.get_tool("vision_upload") is None


def test_inline_image_vision_gate_accepts_standard_models_marked_vision() -> None:
    interface = ReverieInterface.__new__(ReverieInterface)
    config = Config(
        models=[
            ModelConfig(
                model="vision-model",
                model_display_name="Vision Model",
                base_url="https://example.com/v1",
                supports_vision=True,
            )
        ],
        active_model_index=0,
        active_model_source="standard",
    )

    allowed, detail = interface._can_attach_inline_images(config)

    assert allowed is True
    assert detail == ""


def test_inline_image_vision_gate_rejects_unmarked_standard_models() -> None:
    interface = ReverieInterface.__new__(ReverieInterface)
    config = Config(
        models=[
            ModelConfig(
                model="text-model",
                model_display_name="Text Model",
                base_url="https://example.com/v1",
            )
        ],
        active_model_index=0,
        active_model_source="standard",
    )

    allowed, detail = interface._can_attach_inline_images(config)

    assert allowed is False
    assert "supports_vision=true" in detail


def test_inline_image_vision_gate_accepts_aihubmix_models_marked_vision() -> None:
    interface = ReverieInterface.__new__(ReverieInterface)
    config = Config(
        models=[
            ModelConfig(
                model="aihubmix-vision",
                model_display_name="AIhubMix Vision",
                base_url="https://example.com/v1",
                supports_vision=True,
            )
        ],
        active_model_index=0,
        active_model_source="aihubmix",
    )

    allowed, detail = interface._can_attach_inline_images(config)

    assert allowed is True
    assert detail == ""


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

    script = tmp_path / "stream_output.py"
    script.write_text(
        "import sys\nprint('alpha')\nprint('beta', file=sys.stderr)\n",
        encoding="utf-8",
    )
    result = tool.execute(command="python -u stream_output.py")

    assert result.success is True
    assert any(event.get("kind") == "tool_progress" and "alpha" in event.get("text", "") for event in events)
    assert any(event.get("kind") == "tool_progress" and "beta" in event.get("text", "") for event in events)


def test_reference_catalog_scan_uses_cache_on_repeated_workspace_reads(tmp_path: Path) -> None:
    gamer_reference_intelligence._REFERENCE_SCAN_CACHE.clear()
    gamer_reference_intelligence._REFERENCE_MANIFEST_CACHE.clear()
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
    assert second["summary"]["total_files"] >= 4


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
    first = interface._append_active_tool_progress(payload)
    second = interface._append_active_tool_progress(payload)
    third = interface._append_active_tool_progress({**payload, "text": "beta\n"})

    current = interface._active_tool_details["call_progress"]
    assert first is True
    assert second is False
    assert third is True
    assert current["stdout"] == "alpha\nbeta\n"
    assert current["progress_event_count"] == 2

    summary = interface._clear_active_tool("call_progress")
    assert summary["had_live_progress"] is True


def test_context_engine_cold_index_runs_in_background() -> None:
    calls: list[str] = []

    class FakeIndexer:
        def full_index(self):
            calls.append("full_index")
            return object()

    interface = ReverieInterface.__new__(ReverieInterface)
    interface.indexer = FakeIndexer()
    interface._indexing_thread = None
    interface._indexing_in_progress = False
    interface._show_activity_event = lambda *args, **kwargs: calls.append("event")
    interface._refresh_command_context = lambda: calls.append("refresh")
    interface._sync_agent_context_engine = lambda: calls.append("sync")

    started = interface._start_context_indexing_background()

    assert started is True
    assert interface._indexing_thread is not None
    interface._indexing_thread.join(timeout=2)
    assert not interface._indexing_thread.is_alive()
    assert interface._indexing_in_progress is False
    assert "full_index" in calls
    assert "refresh" in calls
    assert "sync" in calls


def test_silent_context_engine_init_starts_background_without_activity(monkeypatch) -> None:
    calls: list[str] = []

    class FakeIndexer:
        def __init__(self, project_root, cache_dir=None):
            self.project_root = project_root
            self.cache_dir = cache_dir
            self.symbol_table = SymbolTable()
            self.dependency_graph = DependencyGraph()
            self._file_info = {}

        def load_cache(self):
            calls.append("load_cache")
            return False

    monkeypatch.setattr("reverie.cli.interface.CodebaseIndexer", FakeIndexer)

    interface = ReverieInterface.__new__(ReverieInterface)
    interface.project_root = Path.cwd()
    interface.project_data_dir = Path.cwd()
    interface.git_integration = None
    interface.memory_indexer = None
    interface.agent = None
    interface.indexer = None
    interface.retriever = None
    interface._context_engine_ready = False
    interface._indexing_thread = None
    interface._indexing_in_progress = False
    interface._context_engine_init_lock = threading.RLock()
    interface._load_active_runtime_config = lambda: type("FakeConfig", (), {"auto_index": True})()
    interface._show_activity_event = lambda *args, **kwargs: calls.append("activity")
    interface._start_context_indexing_background = lambda: calls.append("start_background") or True
    interface._refresh_command_context = lambda: calls.append("refresh")

    interface._init_context_engine_with_options(announce=False)

    assert "load_cache" in calls
    assert "start_background" in calls
    assert "activity" not in calls
    assert interface.retriever is not None


def test_context_engine_warmup_runs_beside_model_turn() -> None:
    calls: list[dict] = []

    interface = ReverieInterface.__new__(ReverieInterface)
    interface.indexer = None
    interface.retriever = None
    interface._context_engine_ready = False
    interface._context_engine_warmup_thread = None
    interface._load_active_runtime_config = lambda: type("FakeConfig", (), {"auto_index": True})()

    def fake_ensure_context_engine(**kwargs):
        calls.append(kwargs)
        return True

    interface.ensure_context_engine = fake_ensure_context_engine
    interface._show_activity_event = lambda *args, **kwargs: calls.append({"activity": True})

    started = interface._prime_context_engine_background()

    assert started is True
    assert interface._context_engine_warmup_thread is not None
    interface._context_engine_warmup_thread.join(timeout=2)
    assert calls == [{"announce": False, "wait_for_index": False}]


def test_codebase_retrieval_waits_for_background_index_when_invoked() -> None:
    calls: list[dict] = []
    retriever = object()

    def fake_ensure_context_engine(**kwargs):
        calls.append(kwargs)
        return True

    tool = CodebaseRetrievalTool(
        {
            "retriever": retriever,
            "ensure_context_engine": fake_ensure_context_engine,
        }
    )

    assert tool._get_retriever() is retriever
    assert calls == [{"wait_for_index": True}]


def test_streaming_footer_ticker_uses_signature_gated_refresh() -> None:
    interface = ReverieInterface.__new__(ReverieInterface)
    interface._status_live = object()
    calls: list[bool] = []
    stop_event = threading.Event()

    def fake_refresh(*, force: bool = False) -> None:
        calls.append(force)
        stop_event.set()

    interface._refresh_streaming_footer = fake_refresh  # type: ignore[method-assign]

    interface._streaming_footer_ticker_loop(stop_event)

    assert calls == [False]


def test_streaming_footer_signature_tracks_elapsed_timer_and_output_tokens() -> None:
    interface = ReverieInterface.__new__(ReverieInterface)
    interface.console = Console(width=120)
    interface._streaming_footer_config = None
    interface._active_tool_lock = threading.Lock()
    interface._active_tool_details = {}
    interface._stream_input_state = None
    interface._current_content_tokens = 100
    interface._task_drawer_visible = True
    interface._task_drawer_cache_key = ("tasks", 1)
    interface.total_active_time = 10.0
    interface.current_task_start = time.time() - 5

    first = interface._build_streaming_footer_signature()
    interface.total_active_time = 11.0
    interface.current_task_start = None

    assert interface._build_streaming_footer_signature() != first

    first = interface._build_streaming_footer_signature()
    interface._current_content_tokens = 999

    assert interface._build_streaming_footer_signature() != first


def test_streaming_footer_requires_real_tty_stdout() -> None:
    class FakeStream:
        def isatty(self) -> bool:
            return False

    class FakeConsole:
        file = FakeStream()

    interface = ReverieInterface.__new__(ReverieInterface)
    interface.headless = False
    interface.console = FakeConsole()

    assert interface._should_use_streaming_footer() is False


def test_streaming_footer_live_options_crop_overflow() -> None:
    interface = ReverieInterface.__new__(ReverieInterface)
    interface.console = Console(width=120)

    options = interface._streaming_footer_live_options()

    assert options["console"] is interface.console
    assert options["auto_refresh"] is False
    assert options["transient"] is True
    assert options["vertical_overflow"] == "crop"


def test_partial_stream_errors_are_recoverable_only_after_visible_output() -> None:
    state = _StreamingTurnState()
    state.add_content("partial answer")

    assert _should_recover_partial_stream_error(
        state,
        RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)"),
    ) is True

    empty_state = _StreamingTurnState()
    assert _should_recover_partial_stream_error(
        empty_state,
        RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)"),
    ) is False

    tool_state = _StreamingTurnState()
    tool_state.add_content("prefix")
    tool_state.update_tool_call(0, tool_call_id="call_1", name="shell", arguments='{"command":"dir"}')
    assert _should_recover_partial_stream_error(
        tool_state,
        RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)"),
    ) is False
