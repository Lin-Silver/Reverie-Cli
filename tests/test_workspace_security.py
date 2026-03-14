import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

from reverie.cli.commands import CommandHandler
from reverie.security_utils import purge_workspace_state
from reverie.tools.command_exec import CommandExecTool


class WorkspaceSecurityTests(unittest.TestCase):
    def test_command_exec_allows_workspace_dotnet_scaffolding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            tool = CommandExecTool({"project_root": workspace})

            with patch("reverie.tools.command_exec.subprocess.run") as mock_run:
                mock_run.return_value = subprocess.CompletedProcess(
                    args=["dotnet", "new", "sln", "-n", "Reverie.Downloader"],
                    returncode=0,
                    stdout="ok",
                    stderr="",
                )
                result = tool.execute(command="dotnet new sln -n Reverie.Downloader")

            self.assertTrue(result.success, result.error)
            run_kwargs = mock_run.call_args.kwargs
            env = run_kwargs["env"]
            sandbox_root = workspace / ".reverie" / "runtime_sandbox" / "dotnet"
            self.assertEqual(run_kwargs["cwd"], str(workspace))
            self.assertEqual(env["DOTNET_CLI_HOME"], str(sandbox_root / "home"))
            self.assertEqual(env["NUGET_PACKAGES"], str(sandbox_root / "nuget" / "packages"))
            self.assertEqual(env["TMP"], str(sandbox_root / "tmp"))
            self.assertEqual(env["HOME"], str(sandbox_root / "home"))
            self.assertTrue((workspace / ".reverie" / "security" / "command_audit.jsonl").exists())

    def test_command_exec_blocks_dotnet_build(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            tool = CommandExecTool({"project_root": workspace})

            with patch("reverie.tools.command_exec.subprocess.run") as mock_run:
                result = tool.execute(command="dotnet build")

            self.assertFalse(result.success)
            self.assertIn("Blocked dotnet subcommand 'build'", result.error)
            mock_run.assert_not_called()

    def test_command_exec_blocks_dotnet_template_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            tool = CommandExecTool({"project_root": workspace})

            with patch("reverie.tools.command_exec.subprocess.run") as mock_run:
                result = tool.execute(command="dotnet new install Microsoft.DotNet.Web.ProjectTemplates.9.0")

            self.assertFalse(result.success)
            self.assertIn("Blocked dotnet new action 'install'", result.error)
            mock_run.assert_not_called()

    def test_purge_workspace_state_removes_only_current_workspace_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as cache_root:
            workspace = Path(workspace_dir)
            project_data_dir = Path(cache_root) / "current_project_cache"
            other_project_cache = Path(cache_root) / "other_project_cache"

            (project_data_dir / "sessions").mkdir(parents=True)
            (project_data_dir / "sessions" / "current.json").write_text("{}", encoding="utf-8")
            (workspace / ".reverie" / "context_cache").mkdir(parents=True)
            (workspace / ".reverie" / "context_cache" / "index.json").write_text("{}", encoding="utf-8")
            (workspace / ".reverie" / "security").mkdir(parents=True)
            (workspace / ".reverie" / "security" / "command_audit.jsonl").write_text("{}", encoding="utf-8")
            (workspace / ".reverie" / "config.json").write_text("{}", encoding="utf-8")
            other_project_cache.mkdir(parents=True)
            (other_project_cache / "keep.txt").write_text("keep", encoding="utf-8")

            result = purge_workspace_state(workspace, project_data_dir)

            self.assertFalse(result["errors"])
            self.assertFalse(project_data_dir.exists())
            self.assertFalse((workspace / ".reverie" / "context_cache").exists())
            self.assertFalse((workspace / ".reverie" / "security").exists())
            self.assertTrue((workspace / ".reverie" / "config.json").exists())
            self.assertTrue(other_project_cache.exists())

    def test_clean_command_dispatches_force_mode(self) -> None:
        calls = []

        def clean_workspace_state() -> dict:
            calls.append("called")
            return {
                "success": True,
                "deleted": [],
                "missing": [],
                "session_name": "Session 2026-03-14 12:00:00",
            }

        console = Console(file=io.StringIO(), force_terminal=False, width=120)
        handler = CommandHandler(
            console,
            {
                "clean_workspace_state": clean_workspace_state,
                "config_manager": SimpleNamespace(
                    project_root=Path("G:/Workspace/Demo"),
                    project_data_dir=Path("G:/Caches/Demo"),
                ),
            },
        )

        self.assertTrue(handler.handle("/Clean force"))
        self.assertEqual(calls, ["called"])


if __name__ == "__main__":
    unittest.main()
