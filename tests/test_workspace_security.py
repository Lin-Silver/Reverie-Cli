from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from reverie.security_utils import WorkspaceSecurityError, resolve_workspace_path
from reverie.tools.command_exec import CommandExecTool
from reverie.tools.create_file import CreateFileTool
from reverie.tools.game_asset_packer import GameAssetPackerTool


class WorkspaceSecurityTests(unittest.TestCase):
    def test_resolve_workspace_path_blocks_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()

            with self.assertRaises(WorkspaceSecurityError) as ctx:
                resolve_workspace_path("../escape.txt", workspace, purpose="test escape")

            self.assertIn("outside the active workspace", str(ctx.exception))

    def test_create_file_tool_blocks_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            tool = CreateFileTool({"project_root": workspace})
            result = tool.execute(path="../escape.txt", content="blocked")

            self.assertFalse(result.success)
            self.assertIn("outside the active workspace", str(result.error))
            self.assertFalse((workspace.parent / "escape.txt").exists())

    def test_command_exec_blocks_interpreters_and_writes_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            tool = CommandExecTool({"project_root": workspace})
            result = tool.execute(command='python -c "print(1)"')

            self.assertFalse(result.success)
            self.assertIn("arbitrary shells, interpreters", str(result.error))

            audit_path = workspace / ".reverie" / "security" / "command_audit.jsonl"
            self.assertTrue(audit_path.exists())

            events = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(events)
            self.assertEqual(events[-1]["event"], "command_blocked")
            self.assertFalse(events[-1]["allowed"])

    def test_command_exec_allows_read_only_workspace_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "README.md").write_text("hello workspace\n", encoding="utf-8")

            tool = CommandExecTool({"project_root": workspace})
            result = tool.execute(command="type README.md", timeout=30)

            self.assertTrue(result.success, result.error)
            self.assertIn("hello workspace", result.output)

    def test_game_asset_packer_blocks_zip_slip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            archive_path = workspace / "payload.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "owned")

            tool = GameAssetPackerTool({"project_root": workspace})
            result = tool.execute(
                action="unpack",
                archive_path=str(archive_path.relative_to(workspace)),
                target_dir="out",
            )

            self.assertFalse(result.success)
            self.assertIn("archive extraction", str(result.error))
            self.assertFalse((workspace.parent / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
