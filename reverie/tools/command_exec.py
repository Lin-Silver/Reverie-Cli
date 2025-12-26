"""
Command Execution Tool - Run shell commands

This tool allows the AI to execute shell commands in the project directory.
Includes safety measures and output capture.
"""

from typing import Optional, Dict
from pathlib import Path
import subprocess
import os
import shlex
import sys

from .base import BaseTool, ToolResult


class CommandExecTool(BaseTool):
    """
    Tool for executing shell commands.
    
    Provides safe command execution with:
    - Working directory control
    - Output capture
    - Timeout handling
    - Environment variable support
    """
    
    name = "command_exec"
    
    description = """Execute shell commands in the project directory.

Use this to:
- Run tests
- Install dependencies
- Execute build commands
- Run scripts

IMPORTANT:
- Commands run in the project directory by default
- Output is captured and returned
- Long-running commands should be avoided
- Destructive commands (rm -rf, etc.) should be used with extreme caution

Examples:
- Run tests: {"command": "pytest tests/ -v"}
- Install package: {"command": "pip install requests"}
- Git status: {"command": "git status"}
- List files: {"command": "ls -la"}"""
    
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: project root)"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120)",
                "default": 120
            },
            "env": {
                "type": "object",
                "description": "Additional environment variables"
            }
        },
        "required": ["command"]
    }
    
    # Dangerous command patterns to warn about
    DANGEROUS_PATTERNS = [
        'rm -rf', 'rm -r', 'rmdir',
        'del /s', 'rd /s',
        'format', 'mkfs',
        'dd if=',
        '> /dev/',
        'chmod -R 777',
        'curl | sh', 'wget | sh',
        ':(){:|:&};:',  # Fork bomb
    ]
    
    def get_execution_message(self, **kwargs) -> str:
        command = kwargs.get('command', 'unknown command')
        return f"Executing command: {command}"

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._project_root = None
        if context:
            self._project_root = context.get('project_root')
    
    def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get('command')
        cwd = kwargs.get('cwd')
        timeout = kwargs.get('timeout', 120)
        extra_env = kwargs.get('env', {})
        
        if not command:
            return ToolResult.fail("Command is required")
        
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in command.lower():
                return ToolResult.fail(
                    f"Potentially dangerous command detected (contains '{pattern}'). "
                    f"Please confirm this is intentional before proceeding."
                )
        
        # Resolve working directory
        if cwd:
            work_dir = Path(cwd)
            if not work_dir.is_absolute() and self._project_root:
                work_dir = Path(self._project_root) / work_dir
        elif self._project_root:
            work_dir = Path(self._project_root)
        else:
            work_dir = Path.cwd()
        
        if not work_dir.exists():
            return ToolResult.fail(f"Working directory not found: {work_dir}")
        
        # Prepare environment
        env = os.environ.copy()
        env.update(extra_env)
        
        # Determine shell based on OS
        if sys.platform == 'win32':
            shell = True
            shell_cmd = command
        else:
            shell = True
            shell_cmd = command
        
        try:
            # Execute command
            result = subprocess.run(
                shell_cmd,
                shell=shell,
                cwd=str(work_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output_parts = []
            output_parts.append(f"$ {command}")
            output_parts.append(f"Working directory: {work_dir}")
            output_parts.append(f"Exit code: {result.returncode}")
            
            if result.stdout:
                stdout = result.stdout
                output_parts.append("\n--- STDOUT ---")
                output_parts.append(stdout)
            
            if result.stderr:
                stderr = result.stderr
                output_parts.append("\n--- STDERR ---")
                output_parts.append(stderr)
            
            if result.returncode == 0:
                return ToolResult.ok(
                    '\n'.join(output_parts),
                    data={
                        'exit_code': result.returncode,
                        'success': True
                    }
                )
            else:
                return ToolResult.partial(
                    '\n'.join(output_parts),
                    f"Command exited with code {result.returncode}"
                )
        
        except subprocess.TimeoutExpired:
            return ToolResult.fail(
                f"Command timed out after {timeout} seconds.\n"
                f"Consider using a longer timeout or running in background."
            )
        
        except FileNotFoundError:
            return ToolResult.fail(
                f"Command not found: {command.split()[0] if command else 'unknown'}"
            )
        
        except Exception as e:
            return ToolResult.fail(f"Error executing command: {str(e)}")
