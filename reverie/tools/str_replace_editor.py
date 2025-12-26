"""
str_replace_editor Tool - File editing tool

This is the primary tool for making code changes.
Supports:
- Viewing files with line numbers
- String replacement editing
- Creating new files
- Inserting text at specific lines
"""

from typing import Optional, Dict
from pathlib import Path
import os
import difflib

from .base import BaseTool, ToolResult


class StrReplaceEditorTool(BaseTool):
    """
    File editing tool using string replacement.
    
    This approach is more reliable than line-based editing because:
    - It requires the model to specify exact text to replace
    - Reduces risk of off-by-one errors
    - Makes diffs clearer
    """
    
    name = "str_replace_editor"
    
    description = """Edit files by viewing, creating, or replacing specific text.

Commands:
- view: View file contents with line numbers
- str_replace: Replace old_str with new_str in the file
- create: Create a new file with specified content
- insert: Insert text at a specific line

IMPORTANT: 
- For str_replace, old_str must match EXACTLY (including whitespace)
- Always use codebase-retrieval first to understand the code before editing
- The old_str must be unique in the file to avoid ambiguous replacements

Examples:
- View file: {"command": "view", "path": "src/main.py"}
- View lines: {"command": "view", "path": "src/main.py", "view_range": [10, 30]}
- Replace: {"command": "str_replace", "path": "src/main.py", "old_str": "def old():", "new_str": "def new():"}
- Create: {"command": "create", "path": "src/new_file.py", "file_text": "# New file\\n"}
- Insert: {"command": "insert", "path": "src/main.py", "insert_line": 5, "new_str": "# Comment\\n"}"""
    
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["view", "str_replace", "create", "insert"],
                "description": "The edit command to execute"
            },
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file"
            },
            "old_str": {
                "type": "string",
                "description": "For str_replace: The exact string to find and replace"
            },
            "new_str": {
                "type": "string",
                "description": "For str_replace/insert: The new string to insert"
            },
            "file_text": {
                "type": "string",
                "description": "For create: The content for the new file"
            },
            "insert_line": {
                "type": "integer",
                "description": "For insert: Line number to insert before (1-indexed)"
            },
            "view_range": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "For view: [start_line, end_line] (1-indexed, inclusive)"
            }
        },
        "required": ["command", "path"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._project_root = None
        if context:
            self._project_root = context.get('project_root')
    
    def get_execution_message(self, **kwargs) -> str:
        command = kwargs.get('command')
        path = kwargs.get('path', 'unknown path')
        
        if command == "view":
            return f"Viewing file: {path}"
        elif command == "str_replace":
            return f"Replacing text in: {path}"
        elif command == "create":
            return f"Creating new file: {path}"
        elif command == "insert":
            return f"Inserting text into: {path}"
        return f"Editing file: {path} ({command})"

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to project root if needed"""
        p = Path(path)
        if p.is_absolute():
            return p
        if self._project_root:
            return Path(self._project_root) / p
        return p.resolve()
    
    def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get('command')
        path = kwargs.get('path')
        
        if not path:
            return ToolResult.fail("Path is required")
        
        file_path = self._resolve_path(path)
        
        try:
            if command == "view":
                return self._view(file_path, kwargs.get('view_range'))
            
            elif command == "str_replace":
                old_str = kwargs.get('old_str')
                new_str = kwargs.get('new_str')
                if not old_str:
                    return ToolResult.fail("old_str is required for str_replace")
                if new_str is None:
                    return ToolResult.fail("new_str is required for str_replace")
                return self._str_replace(file_path, old_str, new_str)
            
            elif command == "create":
                file_text = kwargs.get('file_text', '')
                return self._create(file_path, file_text)
            
            elif command == "insert":
                insert_line = kwargs.get('insert_line')
                new_str = kwargs.get('new_str')
                if not insert_line:
                    return ToolResult.fail("insert_line is required for insert")
                if new_str is None:
                    return ToolResult.fail("new_str is required for insert")
                return self._insert(file_path, insert_line, new_str)
            
            else:
                return ToolResult.fail(f"Unknown command: {command}")
        
        except PermissionError:
            return ToolResult.fail(f"Permission denied: {file_path}")
        except Exception as e:
            return ToolResult.fail(f"Error: {str(e)}")
    
    def _view(self, file_path: Path, view_range: Optional[list]) -> ToolResult:
        """View file contents with line numbers"""
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    lines = f.readlines()
            except Exception as e:
                return ToolResult.fail(f"Could not read file: {e}")
        
        total_lines = len(lines)
        
        # Handle view range
        if view_range and len(view_range) >= 2:
            start = max(1, view_range[0])
            end = min(total_lines, view_range[1])
            # For explicit view ranges, don't apply the 20-line limit
            is_range_view = True
        else:
            start = 1
            end = total_lines
            is_range_view = False
        
        # Apply 20-line limit for single file views (not range views) when file has > 200 lines
        if not is_range_view and total_lines > 200:
            end = start + 19  # Show exactly 20 lines
            should_skip_message = True
        else:
            should_skip_message = False
        
        output_parts = []
        output_parts.append(f"File: {file_path}")
        output_parts.append(f"Total lines: {total_lines}")
        output_parts.append(f"Showing lines {start}-{end}")
        output_parts.append("")
        
        for i in range(start - 1, min(end, total_lines)):
            line_num = i + 1
            line_content = lines[i].rstrip('\n\r')
            output_parts.append(f"{line_num:4d} | {line_content}")
        
        # Add skip message if content was truncated
        if should_skip_message and end < total_lines:
            skipped_lines = total_lines - 200
            output_parts.append(f"Skip {skipped_lines} lines of code")
        
        return ToolResult.ok(
            '\n'.join(output_parts),
            data={
                'file': str(file_path),
                'total_lines': total_lines,
                'shown_start': start,
                'shown_end': end
            }
        )
    
    def _str_replace(self, file_path: Path, old_str: str, new_str: str) -> ToolResult:
        """Replace exact string in file"""
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
        
        # Check if old_str exists
        count = content.count(old_str)
        
        if count == 0:
            # Provide helpful error
            return ToolResult.fail(
                f"String not found in file. The old_str must match exactly, "
                f"including whitespace and indentation.\n\n"
                f"Looking for:\n```\n{old_str}\n```\n\n"
                f"Tip: Use the 'view' command to see the exact file contents."
            )
        
        if count > 1:
            return ToolResult.fail(
                f"String found {count} times. Please provide a more unique string "
                f"to avoid ambiguous replacements."
            )
        
        # Perform replacement
        new_content = content.replace(old_str, new_str, 1)
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # Generate diff for display
        diff = self._generate_diff(content, new_content, str(file_path))
        
        # Trigger context engine update if available
        if self.context and self.context.get('indexer'):
            self.context['indexer'].update_file(file_path)
        
        return ToolResult.ok(
            f"Successfully replaced text in {file_path}\n\n{diff}",
            data={
                'file': str(file_path),
                'replacements': 1
            }
        )
    
    def _create(self, file_path: Path, content: str) -> ToolResult:
        """Create a new file"""
        if file_path.exists():
            return ToolResult.fail(
                f"File already exists: {file_path}. "
                f"Use str_replace to modify existing files."
            )
        
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        line_count = content.count('\n') + (1 if content and not content.endswith('\n') else 0)
        
        # Trigger context engine update
        if self.context and self.context.get('indexer'):
            self.context['indexer'].update_file(file_path)
        
        return ToolResult.ok(
            f"Created file: {file_path}\n"
            f"Lines: {line_count}",
            data={
                'file': str(file_path),
                'lines': line_count
            }
        )
    
    def _insert(self, file_path: Path, insert_line: int, new_str: str) -> ToolResult:
        """Insert text at a specific line"""
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if insert_line < 1 or insert_line > len(lines) + 1:
            return ToolResult.fail(
                f"Invalid line number: {insert_line}. "
                f"File has {len(lines)} lines."
            )
        
        # Insert at the specified line
        old_content = ''.join(lines)
        
        # Ensure new_str ends with newline for clean insertion
        if new_str and not new_str.endswith('\n'):
            new_str += '\n'
        
        lines.insert(insert_line - 1, new_str)
        new_content = ''.join(lines)
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # Generate diff
        diff = self._generate_diff(old_content, new_content, str(file_path))
        
        # Trigger context engine update
        if self.context and self.context.get('indexer'):
            self.context['indexer'].update_file(file_path)
        
        return ToolResult.ok(
            f"Inserted text at line {insert_line} in {file_path}\n\n{diff}",
            data={
                'file': str(file_path),
                'insert_line': insert_line
            }
        )
    
    def _generate_diff(self, old: str, new: str, filename: str) -> str:
        """Generate unified diff between old and new content"""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=''
        )
        
        diff_str = ''.join(diff)
        
        # No diff truncation
        
        return f"```diff\n{diff_str}\n```"
