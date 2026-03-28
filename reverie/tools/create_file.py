"""Tool for creating new workspace files from complete content."""

from typing import Optional, Dict
from pathlib import Path
from .base import BaseTool, ToolResult

class CreateFileTool(BaseTool):
    """
    Tool for creating new files with content.
    """
    name = "create_file"
    description = """Create a new file with the specified content inside the active workspace.
Use this tool to create new files from scratch, including large files.
Do NOT use this for editing existing files.
"""
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative path or an absolute path still inside the project root"
            },
            "content": {
                "type": "string",
                "description": "The full content of the file"
            },
            "overwrite": {
                "type": "boolean",
                "description": "Whether to overwrite if file exists (default: False)",
                "default": False
            }
        },
        "required": ["path", "content"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)

    def execute(self, **kwargs) -> ToolResult:
        path = kwargs.get('path')
        content = kwargs.get('content')
        overwrite = kwargs.get('overwrite', False)

        if not path or content is None:
            return ToolResult.fail("Path and content are required")

        try:
            file_path = self.resolve_workspace_path(path, purpose="create file")
        except Exception as e:
            return ToolResult.fail(str(e))
            
        if file_path.exists() and not overwrite:
            return ToolResult.fail(f"File already exists: {file_path}. Set overwrite=True to replace it.")
             
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            if self.context and self.context.get('indexer'):
                self.context['indexer'].update_file(file_path)
            if self.context and self.context.get('retriever'):
                self.context['retriever'].mark_file_activity(str(file_path), weight=1.5, reason="edit")

            line_count = len(content.splitlines())
            return ToolResult.ok(f"Created file: {file_path} ({line_count} lines)")
        except Exception as e:
            return ToolResult.fail(f"Failed to create file: {e}")
