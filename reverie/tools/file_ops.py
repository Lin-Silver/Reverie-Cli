"""
File Operations Tool - Basic file system operations

Provides:
- Read file contents
- List directory
- Check file existence
- Get file info
- Delete files (with confirmation)
"""

from typing import Optional, Dict, List
from pathlib import Path
import os
import stat
from datetime import datetime

from .base import BaseTool, ToolResult


class FileOpsTool(BaseTool):
    """
    Tool for basic file system operations.
    """
    
    name = "file_ops"
    
    description = """Perform file system operations.

Operations:
- read: Read entire file content
- list: List directory contents
- exists: Check if file/directory exists
- info: Get file metadata (size, modified time, etc.)
- mkdir: Create directory
- delete: Delete file (requires confirmation in most cases)

Examples:
- Read file: {"operation": "read", "path": "src/config.json"}
- List dir: {"operation": "list", "path": "src/", "recursive": false}
- Check exists: {"operation": "exists", "path": "src/main.py"}
- Get info: {"operation": "info", "path": "src/main.py"}"""
    
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "list", "exists", "info", "mkdir", "delete"],
                "description": "Operation to perform"
            },
            "path": {
                "type": "string",
                "description": "File or directory path"
            },
            "recursive": {
                "type": "boolean",
                "description": "For list: include subdirectories",
                "default": False
            },
            "pattern": {
                "type": "string",
                "description": "For list: filter by pattern (e.g., '*.py')"
            },
            "confirm_delete": {
                "type": "boolean",
                "description": "For delete: confirm deletion",
                "default": False
            }
        },
        "required": ["operation", "path"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._project_root = None
        if context:
            self._project_root = context.get('project_root')
    
    def get_execution_message(self, **kwargs) -> str:
        operation = kwargs.get('operation')
        path = kwargs.get('path', 'unknown path')
        
        ops_map = {
            "read": f"Reading file: {path}",
            "list": f"Listing directory: {path}",
            "exists": f"Checking existence of: {path}",
            "info": f"Getting info for: {path}",
            "mkdir": f"Creating directory: {path}",
            "delete": f"Deleting file: {path}"
        }
        return ops_map.get(operation, f"File operation: {operation} on {path}")

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to project root"""
        p = Path(path)
        if p.is_absolute():
            return p
        if self._project_root:
            return Path(self._project_root) / p
        return p.resolve()
    
    def execute(self, **kwargs) -> ToolResult:
        operation = kwargs.get('operation')
        path = kwargs.get('path')
        
        if not path:
            return ToolResult.fail("Path is required")
        
        file_path = self._resolve_path(path)
        
        try:
            if operation == "read":
                return self._read(file_path)
            elif operation == "list":
                return self._list(
                    file_path,
                    kwargs.get('recursive', False),
                    kwargs.get('pattern')
                )
            elif operation == "exists":
                return self._exists(file_path)
            elif operation == "info":
                return self._info(file_path)
            elif operation == "mkdir":
                return self._mkdir(file_path)
            elif operation == "delete":
                return self._delete(file_path, kwargs.get('confirm_delete', False))
            else:
                return ToolResult.fail(f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult.fail(f"Error: {str(e)}")
    
    def _read(self, file_path: Path) -> ToolResult:
        """Read file contents"""
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {file_path}")
        
        if file_path.is_dir():
            return ToolResult.fail(f"Path is a directory: {file_path}")
        
        # Check file size
        size = file_path.stat().st_size
        if size > 100 * 1024 * 1024:  # 100MB limit
            return ToolResult.fail(
                f"File too large ({size / 1024 / 1024:.1f}MB). "
                f"Use str_replace_editor view command for partial reading."
            )
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception as e:
                return ToolResult.fail(f"Could not read file: {e}")
        
        return ToolResult.ok(content, data={'file': str(file_path), 'size': len(content)})
    
    def _list(self, dir_path: Path, recursive: bool, pattern: Optional[str]) -> ToolResult:
        """List directory contents"""
        if not dir_path.exists():
            return ToolResult.fail(f"Directory not found: {dir_path}")
        
        if not dir_path.is_dir():
            return ToolResult.fail(f"Path is not a directory: {dir_path}")
        
        import fnmatch
        
        items = []
        
        if recursive:
            for root, dirs, files in os.walk(dir_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for f in files:
                    if f.startswith('.'):
                        continue
                    if pattern and not fnmatch.fnmatch(f, pattern):
                        continue
                    
                    rel_path = Path(root).relative_to(dir_path) / f
                    items.append(('file', str(rel_path)))
                
                if len(items) > 500:
                    break
        else:
            for item in sorted(dir_path.iterdir()):
                if item.name.startswith('.'):
                    continue
                if pattern and not fnmatch.fnmatch(item.name, pattern):
                    continue
                
                item_type = 'dir' if item.is_dir() else 'file'
                items.append((item_type, item.name))
        
        output_parts = [f"Directory: {dir_path}", f"Items: {len(items)}", ""]
        
        for item_type, name in items:
            prefix = "[DIR] " if item_type == 'dir' else "[FILE] "
            output_parts.append(f"{prefix}{name}")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _exists(self, file_path: Path) -> ToolResult:
        """Check if path exists"""
        exists = file_path.exists()
        path_type = "directory" if file_path.is_dir() else "file" if file_path.is_file() else "unknown"
        
        return ToolResult.ok(
            f"{'Exists' if exists else 'Does not exist'}: {file_path}" +
            (f" (type: {path_type})" if exists else ""),
            data={'exists': exists, 'type': path_type if exists else None}
        )
    
    def _info(self, file_path: Path) -> ToolResult:
        """Get file/directory metadata"""
        if not file_path.exists():
            return ToolResult.fail(f"Path not found: {file_path}")
        
        try:
            stat_info = file_path.stat()
            
            info = {
                'path': str(file_path),
                'name': file_path.name,
                'type': 'directory' if file_path.is_dir() else 'file',
                'size': stat_info.st_size,
                'modified': datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                'created': datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                'permissions': stat.filemode(stat_info.st_mode)
            }
            
            if file_path.is_file():
                info['extension'] = file_path.suffix
            
            output_parts = [f"# File Info: {file_path}", ""]
            for key, value in info.items():
                if key == 'size':
                    value = f"{value:,} bytes ({value / 1024:.1f} KB)"
                output_parts.append(f"- **{key}**: {value}")
            
            return ToolResult.ok('\n'.join(output_parts), data=info)
        
        except Exception as e:
            return ToolResult.fail(f"Could not get file info: {e}")
    
    def _mkdir(self, dir_path: Path) -> ToolResult:
        """Create directory"""
        if dir_path.exists():
            if dir_path.is_dir():
                return ToolResult.ok(f"Directory already exists: {dir_path}")
            else:
                return ToolResult.fail(f"Path exists and is not a directory: {dir_path}")
        
        dir_path.mkdir(parents=True, exist_ok=True)
        return ToolResult.ok(f"Created directory: {dir_path}")
    
    def _delete(self, file_path: Path, confirmed: bool) -> ToolResult:
        """Delete file (with safety checks)"""
        if not file_path.exists():
            return ToolResult.fail(f"Path not found: {file_path}")
        
        if not confirmed:
            return ToolResult.fail(
                f"Deletion requires confirmation. Call with confirm_delete=true to delete: {file_path}"
            )
        
        if file_path.is_dir():
            return ToolResult.fail(
                "Directory deletion not supported for safety. Use command_exec with rmdir if needed."
            )
        
        file_path.unlink()
        return ToolResult.ok(f"Deleted: {file_path}")
