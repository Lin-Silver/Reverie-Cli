from pathlib import Path

import pytest

from reverie.writer.style_commands import run_wstyle_command
from reverie.writer.style_runtime import WStyleRuntime

from test_wstyles import write_card


def runtime(tmp_path):
    result = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    write_card(result.repository, "a", "用具体动作表现犹豫。")
    write_card(result.repository, "b", "让选择带来新的后果。", layer="narrative")
    return result


def test_management_commands_preserve_order_and_card_files(tmp_path):
    styles = runtime(tmp_path)
    call = lambda args: run_wstyle_command(args, styles, mode="writer")
    assert call("").success
    assert call("list").data["items"][0]["id"] == "a"
    assert "具体动作" in call("show a").output
    assert call("use a b a --global").data["state"]["saved_ids"] == ["a", "b"]
    assert call("add a --global").data["state"]["saved_ids"] == ["a", "b"]
    assert call("remove a --global").data["state"]["saved_ids"] == ["b"]
    assert call("current").data["state"]["cards"][0]["id"] == "b"
    assert call("off --global").data["state"]["saved_ids"] == []
    assert styles.repository.get("a") and styles.repository.get("b")
    assert call("new copied --from a").success
    assert styles.repository.get("copied").body == styles.repository.get("a").body
    assert not call("new a").success
    assert call("new original").success


@pytest.mark.parametrize("args", ["use", "use missing", "show", "show a b", "new ../escape", "new a --from", "off a", "remove absent", "use a --global --novel x", "current --unknown", "review --chapter nope", "extract", "extract generated --sample"])
def test_invalid_parameters_do_not_change_selection(tmp_path, args):
    styles = runtime(tmp_path)
    styles.set_selection(["a"], global_scope=True)
    before = styles.global_config_path.read_bytes()
    result = run_wstyle_command(args, styles, mode="writer")
    assert result.success is False
    assert result.error
    assert styles.global_config_path.read_bytes() == before


def test_non_writer_commands_have_no_filesystem_side_effect(tmp_path):
    styles = WStyleRuntime(tmp_path, app_root=tmp_path / "app")
    result = run_wstyle_command("new nope", styles, mode="reverie")
    assert not result.success
    assert "/mode writer" in result.error
    assert not styles.repository.root.exists()


def test_remove_recovers_a_missing_id_without_losing_other_invalid_ids(tmp_path):
    styles = runtime(tmp_path)
    styles.set_selection(["a", "b"], global_scope=True)
    (styles.repository.root / "a.md").unlink()
    result = run_wstyle_command("remove a --global", styles, mode="writer")
    assert result.success
    assert result.data["state"]["saved_ids"] == ["b"]


def test_terminal_adapter_registers_help_and_live_card_completion(tmp_path):
    from io import StringIO
    from rich.console import Console
    from reverie.cli.commands import CommandHandler
    from reverie.cli.help_catalog import HELP_TOPICS, build_command_completion_map
    from reverie.config import Config
    from types import SimpleNamespace

    styles = runtime(tmp_path)
    stream = StringIO()
    manager = SimpleNamespace(load=lambda: Config(mode="writer"), app_root=styles.app_root)
    handler = CommandHandler(Console(file=stream, width=100), {"config_manager": manager, "project_root": tmp_path,
                                                              "get_wstyle_runtime": lambda: styles})
    assert "wstyle" in handler.commands
    assert handler.handle("/wstyle use a b --global")
    assert "a" in stream.getvalue() and "b" in stream.getvalue()
    assert "wstyle" in HELP_TOPICS
    assert "/wstyle list" in build_command_completion_map()
