"""
Dedicated file deletion tool.

This is the only AI tool that is allowed to delete files directly. It performs
strict workspace-boundary checks before deleting a single file.
"""

from __future__ import annotations

from typing import Dict, Optional

from .base import BaseTool, ToolResult
from ..config import get_project_data_dir
from ..workspace_guard import ShadowGitManager


class DeleteFileTool(BaseTool):
    """Delete a single file inside the active workspace."""

    name = "delete_file"
    aliases = ("remove_file",)
    search_hint = "delete one workspace file safely"
    tool_category = "editing"
    tool_tags = ("delete", "remove", "file", "cleanup")
    destructive = True
    MAX_DELETE_BYTES = 1024 ** 3

    description = """Delete a single file inside the active workspace only.

Rules:
- The target path must resolve inside the current workspace
- Directory deletion is not allowed
- `confirm_delete` must be true
- Use this tool instead of terminal delete commands

Example:
- {"path": "logs/debug.txt", "confirm_delete": true}"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative or workspace-absolute file path to delete"
            },
            "confirm_delete": {
                "type": "boolean",
                "description": "Must be true to confirm file deletion",
                "default": False
            }
        },
        "required": ["path", "confirm_delete"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)

    def get_execution_message(self, **kwargs) -> str:
        path = kwargs.get("path", "unknown path")
        return f"Deleting workspace file: {path}"

    def execute(self, **kwargs) -> ToolResult:
        raw_path = kwargs.get("path")
        confirmed = bool(kwargs.get("confirm_delete", False))

        if not raw_path:
            return ToolResult.fail("Path is required")

        try:
            file_path = self.resolve_workspace_path(raw_path, purpose="delete file")
        except Exception as exc:
            self.audit_command_event(
                {
                    "event": "delete_file_blocked",
                    "allowed": False,
                    "path": str(raw_path),
                    "reason": str(exc),
                }
            )
            return ToolResult.fail(str(exc))

        if not confirmed:
            return ToolResult.fail(
                f"Deletion requires confirmation. Call with confirm_delete=true to delete: {file_path}"
            )

        if not file_path.exists():
            return ToolResult.fail(f"Path not found: {file_path}")

        if file_path.is_dir():
            return ToolResult.fail(
                "Directory deletion is disabled. Use dedicated workspace cleanup flows for folders."
            )

        try:
            file_size = file_path.stat().st_size
        except OSError as exc:
            return ToolResult.fail(f"Could not inspect file before deletion: {exc}")
        if file_size > self.MAX_DELETE_BYTES:
            return ToolResult.fail(
                "Deletion refused: the target is larger than 1 GiB. Perform an in-depth review and confirm "
                "that the deletion target is correct before using a separate, user-operated cleanup process."
            )

        guard = self.context.get("shadow_git_manager")
        if not isinstance(guard, ShadowGitManager):
            guard = ShadowGitManager(self.get_project_root(), get_project_data_dir(self.get_project_root()))

        try:
            guard.checkpoint("Before delete_file", force_paths=(file_path,))
            archive_path = guard.archive_for_delete(file_path)
            file_path.unlink()
            checkpoint = guard.checkpoint(f"Delete {file_path.relative_to(self.get_project_root())}")
        except Exception as exc:
            self.audit_command_event(
                {
                    "event": "delete_file_error",
                    "allowed": True,
                    "path": str(file_path),
                    "reason": str(exc),
                }
            )
            return ToolResult.fail(f"Could not archive and delete file: {exc}")

        self.audit_command_event(
            {
                "event": "delete_file_success",
                "allowed": True,
                "path": str(file_path),
                "archive_path": str(archive_path),
                "checkpoint": checkpoint.commit,
            }
        )
        return ToolResult.ok(
            f"Deleted: {file_path}\nBackup: {archive_path}\nCheckpoint: {checkpoint.commit}",
            data={"archive_path": str(archive_path), "checkpoint": checkpoint.commit},
        )
