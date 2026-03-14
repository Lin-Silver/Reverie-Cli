from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reverie.agent.tool_descriptions import get_tool_descriptions_for_mode
from reverie.agent.tool_executor import ToolExecutor
from reverie.tools.command_exec import CommandExecTool
from reverie.tools.delete_file import DeleteFileTool
from reverie.tools.file_ops import FileOpsTool


class WorkspaceSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._temp_dir.name)
        self.context = {"project_root": self.workspace}

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_delete_file_removes_workspace_file(self) -> None:
        target = self.workspace / "notes.txt"
        target.write_text("hello", encoding="utf-8")

        tool = DeleteFileTool(self.context)
        result = tool.execute(path="notes.txt", confirm_delete=True)

        self.assertTrue(result.success)
        self.assertFalse(target.exists())

    def test_delete_file_blocks_outside_workspace(self) -> None:
        outside_root = self.workspace.parent
        outside_file = outside_root / "outside-delete.txt"
        outside_file.write_text("do not touch", encoding="utf-8")
        self.addCleanup(lambda: outside_file.unlink(missing_ok=True))

        tool = DeleteFileTool(self.context)
        result = tool.execute(path=str(outside_file), confirm_delete=True)

        self.assertFalse(result.success)
        self.assertTrue(outside_file.exists())

    def test_delete_file_blocks_directory(self) -> None:
        folder = self.workspace / "cache"
        folder.mkdir()

        tool = DeleteFileTool(self.context)
        result = tool.execute(path="cache", confirm_delete=True)

        self.assertFalse(result.success)
        self.assertTrue(folder.exists())

    def test_file_ops_delete_redirects_to_delete_tool(self) -> None:
        target = self.workspace / "old.log"
        target.write_text("x", encoding="utf-8")

        tool = FileOpsTool(self.context)
        result = tool.execute(operation="delete", path="old.log", confirm_delete=True)

        self.assertFalse(result.success)
        self.assertIn("delete_file", result.error)
        self.assertTrue(target.exists())

    @patch("reverie.tools.command_exec.subprocess.run")
    def test_command_exec_allows_python_inline_semicolons(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=["python", "-c", "print(1); print(2)"],
            returncode=0,
            stdout="1\n2\n",
            stderr="",
        )

        tool = CommandExecTool(self.context)
        result = tool.execute(command='python -c "print(1); print(2)"')

        self.assertTrue(result.success)
        self.assertEqual(run_mock.call_count, 1)
        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[0], "python")
        self.assertIn("Exit code: 0", result.output)

    def test_command_exec_blocks_delete_command(self) -> None:
        tool = CommandExecTool(self.context)
        result = tool.execute(command="del notes.txt")

        self.assertFalse(result.success)
        self.assertIn("delete_file", result.error)

    def test_command_exec_blocks_python_delete_api(self) -> None:
        tool = CommandExecTool(self.context)
        result = tool.execute(command='python -c "import os; os.remove(\'x.txt\')"')

        self.assertFalse(result.success)
        self.assertIn("delete_file", result.error)

    def test_tool_executor_exposes_delete_file_schema(self) -> None:
        executor = ToolExecutor(self.workspace)
        schema_names = [schema["function"]["name"] for schema in executor.get_tool_schemas(mode="reverie")]

        self.assertIn("delete_file", schema_names)

    def test_mode_tool_descriptions_are_mode_specific(self) -> None:
        reverie = get_tool_descriptions_for_mode("reverie")
        writer = get_tool_descriptions_for_mode("writer")
        ant = get_tool_descriptions_for_mode("ant")

        self.assertIn("Reverie Mode Tool Workflow", reverie)
        self.assertIn("Writer Mode Tool Workflow", writer)
        self.assertIn("Ant Mode Tool Workflow", ant)
        self.assertIn("Delete File Tool (delete_file)", reverie)
        self.assertNotEqual(reverie, writer)


if __name__ == "__main__":
    unittest.main()
