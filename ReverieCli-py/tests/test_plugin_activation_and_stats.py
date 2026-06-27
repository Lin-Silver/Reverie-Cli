from __future__ import annotations

from io import StringIO
from pathlib import Path
from textwrap import dedent

import pytest
from rich.console import Console

from reverie.agent.tool_executor import ToolExecutor
from reverie.cli.commands import CommandHandler
from reverie.mcp import MCPConfigManager, MCPRuntime
from reverie.plugin.protocol import normalize_runtime_handshake
from reverie.plugin.runtime_manager import RuntimePluginManager
from reverie.session.workspace_stats import WorkspaceStatsManager
from reverie.settings_catalog import get_setting_items
from reverie.skills_manager import SkillsManager
from reverie.tools.registry import get_tool_registrations


def _write_plugin(app_root: Path) -> None:
    install_root = app_root / ".reverie" / "plugins"
    install_root.mkdir(parents=True, exist_ok=True)
    (install_root / "reverie-sample.py").write_text(
        dedent(
            """
            import json
            import sys

            HANDSHAKE = {
                "protocol_version": "1.0",
                "plugin_id": "sample",
                "display_name": "Sample Plugin",
                "runtime_family": "test",
                "system_prompt": "SAMPLE_PLUGIN_PROMPT_MARKER",
                "include_modes": ["reverie-gamer"],
                "skills": [
                    {
                        "name": "sample-plugin-skill",
                        "description": "Sample plugin workflow instructions.",
                        "body": "SAMPLE_PLUGIN_SKILL_MARKER",
                        "include_modes": ["reverie-gamer"]
                    }
                ],
                "commands": [
                    {
                        "name": "status",
                        "description": "Return sample status.",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                        "expose_as_tool": True,
                        "include_modes": ["reverie-gamer"]
                    }
                ],
                "mcp_servers": [
                    {
                        "name": "sample_mcp",
                        "description": "Sample plugin MCP server.",
                        "enabled": True,
                        "type": "stdio",
                        "command": sys.executable,
                        "args": ["-c", "print('not a real mcp server')"],
                        "include_modes": ["reverie-gamer"],
                        "trust": True
                    }
                ]
            }

            if len(sys.argv) >= 2 and sys.argv[1] == "-RC":
                print(json.dumps(HANDSHAKE))
                raise SystemExit(0)
            if len(sys.argv) >= 2 and sys.argv[1] == "-RC-CALL":
                print(json.dumps({"success": True, "output": "sample ok", "error": "", "data": {"ready": True}}))
                raise SystemExit(0)
            raise SystemExit(1)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def test_plugin_enable_disable_controls_tools_prompt_and_skills(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_plugin(app_root)
    manager = RuntimePluginManager(app_root)
    record = manager.get_record("sample", force_refresh=True)

    assert record is not None
    assert record.enabled is True
    assert record.protocol_supported is True
    assert "SAMPLE_PLUGIN_PROMPT_MARKER" in manager.describe_for_prompt("reverie-gamer")
    assert "SAMPLE_PLUGIN_PROMPT_MARKER" not in manager.describe_for_prompt("writer")
    assert manager.get_skill_definitions()[0]["body"] == "SAMPLE_PLUGIN_SKILL_MARKER"

    executor = ToolExecutor(project_root=tmp_path)
    executor.update_context("runtime_plugin_manager", manager)
    assert "rc_sample_status" in {
        schema["function"]["name"] for schema in executor.get_tool_schemas("reverie-gamer")
    }

    manager.set_plugin_enabled("sample", False)
    disabled = manager.get_record("sample")
    assert disabled is not None
    assert disabled.enabled is False
    assert disabled.protocol_status == "disabled"
    assert "SAMPLE_PLUGIN_PROMPT_MARKER" not in manager.describe_for_prompt("reverie-gamer")
    assert manager.get_skill_definitions() == []
    assert "rc_sample_status" not in {
        schema["function"]["name"] for schema in executor.get_tool_schemas("reverie-gamer")
    }
    with pytest.raises(RuntimeError, match="disabled"):
        manager.call_tool("sample", "status", {})

    reloaded = RuntimePluginManager(app_root)
    assert reloaded.get_record("sample", force_refresh=True).enabled is False
    reloaded.set_plugin_enabled("sample", True)
    assert reloaded.get_record("sample").protocol_supported is True


def test_plugin_virtual_skill_respects_mode_and_settings_surface(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_plugin(app_root)
    manager = RuntimePluginManager(app_root)
    manager.scan(force_protocol_refresh=True)
    skills = SkillsManager(tmp_path, app_root, runtime_plugin_manager=manager)

    skills.set_active_mode("reverie")
    assert skills.get_record("sample-plugin-skill", force_refresh=True) is None
    skills.set_active_mode("reverie-gamer")
    record = skills.get_record("sample-plugin-skill", force_refresh=True)
    assert record is not None
    assert record.source_uri == "plugin://sample/skills/sample-plugin-skill"
    assert "SAMPLE_PLUGIN_SKILL_MARKER" in skills.build_explicit_skill_injection([record])

    setting_items = get_setting_items(object(), object(), None, manager)
    plugin_item = next(item for item in setting_items if item.get("key") == "plugin_enabled:sample")
    assert plugin_item["value"] is True


def test_plugin_mcp_definitions_overlay_runtime_servers(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_plugin(app_root)
    plugin_manager = RuntimePluginManager(app_root)
    plugin_manager.scan(force_protocol_refresh=True)

    definitions = plugin_manager.get_mcp_server_definitions()
    assert "sample_mcp" in definitions
    assert definitions["sample_mcp"]["type"] == "stdio"
    assert definitions["sample_mcp"]["trust"] is True

    config_manager = MCPConfigManager(app_root)
    config_manager.ensure_dirs()
    runtime = MCPRuntime(config_manager, project_root=tmp_path, runtime_plugin_manager=plugin_manager)
    runtime.set_active_mode("reverie-gamer")
    with runtime._lock:
        effective = runtime._get_effective_servers_locked()
    assert "sample_mcp" in effective

    runtime.set_active_mode("writer")
    with runtime._lock:
        effective = runtime._get_effective_servers_locked()
    assert "sample_mcp" not in effective


def test_protocol_rejects_incompatible_versions_and_invalid_command_names() -> None:
    incompatible = normalize_runtime_handshake(
        {"protocol_version": "999.0", "plugin_id": "bad", "commands": []},
        fallback_plugin_id="bad",
        fallback_display_name="Bad",
        fallback_runtime_family="test",
    )
    assert incompatible is None

    handshake = normalize_runtime_handshake(
        {
            "protocol_version": "1.0",
            "plugin_id": "sample",
            "commands": [{"description": "missing name", "expose_as_tool": "false"}],
        },
        fallback_plugin_id="sample",
        fallback_display_name="Sample",
        fallback_runtime_family="test",
    )
    assert handshake is not None
    assert handshake.commands == ()


def test_plugin_discovery_does_not_treat_plain_files_as_launchers(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    install_root = app_root / ".reverie" / "plugins"
    install_root.mkdir(parents=True)
    (install_root / "reverie-notes.txt").write_text("not executable", encoding="utf-8")

    snapshot = RuntimePluginManager(app_root).scan(force_protocol_refresh=True)

    assert all(record.plugin_id != "notes" for record in snapshot.records)


def test_workspace_stats_persist_tokens_tools_plugins_and_skills(tmp_path: Path) -> None:
    manager = WorkspaceStatsManager(tmp_path / "cache", project_root=tmp_path)
    manager.record_model_usage(
        provider="openai",
        source="chat",
        model="test-model",
        model_display_name="Test Model",
        request_messages=[{"role": "user", "content": "hello"}],
        assistant_text="world",
        usage={"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
        session_id="session-1",
    )
    manager.record_operation(category="tool", name="file_ops", success=True, duration_ms=20)
    manager.record_operation(
        category="plugin-tool",
        name="rc_sample_status",
        plugin_id="sample",
        success=False,
        duration_ms=30,
    )
    manager.record_operation(category="skill", name="sample-plugin-skill", plugin_id="sample")
    manager.flush()

    dashboard = WorkspaceStatsManager(tmp_path / "cache", project_root=tmp_path).build_dashboard_data()
    assert dashboard["total_input_tokens"] == 12
    assert dashboard["total_output_tokens"] == 7
    assert dashboard["total_tokens"] == 19
    assert dashboard["total_tool_calls"] == 2
    assert dashboard["total_plugin_tool_calls"] == 1
    assert dashboard["total_skill_activations"] == 1
    plugin_row = next(row for row in dashboard["operation_usage"] if row["category"] == "plugin-tool")
    assert plugin_row["failures"] == 1
    assert plugin_row["average_duration_ms"] == 30.0


def test_workspace_stats_discovery_reads_current_projects_directory(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".reverie" / "projects" / "sample-workspace"
    manager = WorkspaceStatsManager(cache_dir, project_root=tmp_path / "workspace")
    manager.record_operation(category="plugin-tool", name="rc_sample_status", plugin_id="sample")
    manager.flush()

    rows = WorkspaceStatsManager.discover_workspaces(tmp_path)

    assert len(rows) == 1
    assert rows[0]["cache_dir"] == str(cache_dir)
    assert rows[0]["total_tool_calls"] == 1
    assert rows[0]["total_plugin_tool_calls"] == 1


def test_total_command_renders_headless_without_prompting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_root = tmp_path / "app"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cache_dir = app_root / ".reverie" / "projects" / "sample-workspace"
    stats = WorkspaceStatsManager(cache_dir, project_root=workspace)
    stats.record_model_usage(
        provider="test",
        source="chat",
        model="test",
        model_display_name="Test Model",
        request_messages=[],
        assistant_text="",
        usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    )
    stats.record_operation(category="skill", name="sample-skill")
    stats.flush()
    monkeypatch.setenv("REVERIE_APP_ROOT", str(app_root))

    output = StringIO()
    handler = CommandHandler(
        Console(file=output, force_terminal=False, color_system=None, width=180),
        {
            "headless": True,
            "workspace_stats_manager": stats,
            "project_data_dir": cache_dir,
            "project_root": workspace,
        },
    )

    assert handler.cmd_total("") is True
    rendered = output.getvalue()
    assert "Total Tokens" in rendered
    assert "Skill Activations" in rendered
    assert "sample-skill" in rendered


def test_tool_executor_records_plugin_tool_usage(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_plugin(app_root)
    plugin_manager = RuntimePluginManager(app_root)
    plugin_manager.scan(force_protocol_refresh=True)
    stats = WorkspaceStatsManager(tmp_path / "cache", project_root=tmp_path)
    executor = ToolExecutor(project_root=tmp_path)
    executor.update_context("workspace_stats_manager", stats)
    executor.update_context("runtime_plugin_manager", plugin_manager)

    result = executor.execute("rc_sample_status", {})
    stats.flush()

    assert result.success is True
    dashboard = stats.build_dashboard_data()
    assert dashboard["total_plugin_tool_calls"] == 1
    row = next(item for item in dashboard["operation_usage"] if item["name"] == "rc_sample_status")
    assert row["plugin_id"] == "sample"
    assert row["successes"] == 1


def test_count_tokens_is_not_exposed_as_an_ai_tool() -> None:
    assert "count_tokens" not in {registration.name for registration in get_tool_registrations(include_hidden=True)}
