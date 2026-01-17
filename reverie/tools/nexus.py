"""
Nexus Tool - Interface for AI to use Reverie-Nexus

This tool provides the AI with access to the Nexus workflow system
for large-scale project development.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path

from .base import BaseTool, ToolResult
from .nexus_tool import NexusManager, NexusTask, NexusPhase, NexusState


class NexusTool(BaseTool):
    """
    Tool for managing large-scale project development with Nexus.
    
    Nexus enables the AI to work on complex projects that require
    24+ hours of continuous work by managing context externally
    and maintaining state between operations.
    """
    
    name = "nexus"
    
    description = """Manage large-scale project development with Reverie-Nexus.

Nexus is designed for developing complex projects that require extended work sessions.
It handles context management, progress tracking, and task orchestration to enable
continuous work beyond typical token limits.

Operations:
- create_project: Initialize a new Nexus project with phases
- start_task: Begin executing a task
- update_progress: Update task progress and results
- complete_task: Mark a task as completed
- pause_task: Pause a running task
- resume_task: Resume a paused task
- save_context: Save context data for a task
- load_context: Load context data
- get_status: Get project or task status
- get_next_task: Get the next task to execute

Use Nexus when:
- Developing a complete project from scratch
- Working on multi-phase development workflows
- Need to maintain state across long operations
- Managing complex dependencies between tasks
- Need external context storage to bypass token limits

Example workflow:
1. Create project: {"operation": "create_project", "name": "MyApp", "description": "...", "requirements": [...]}
2. Start task: {"operation": "start_task", "task_id": "..."}
3. Update progress: {"operation": "update_progress", "task_id": "...", "progress": 0.5}
4. Save context: {"operation": "save_context", "task_id": "...", "context_type": "design", "data": {...}}
5. Complete task: {"operation": "complete_task", "task_id": "...", "result": {...}}"""
    
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "create_project",
                    "start_task",
                    "update_progress",
                    "complete_task",
                    "pause_task",
                    "resume_task",
                    "save_context",
                    "load_context",
                    "get_status",
                    "get_next_task"
                ],
                "description": "The Nexus operation to perform"
            },
            "task_id": {
                "type": "string",
                "description": "Task ID (required for most operations)"
            },
            "name": {
                "type": "string",
                "description": "Project name (for create_project)"
            },
            "description": {
                "type": "string",
                "description": "Project description (for create_project)"
            },
            "requirements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Project requirements (for create_project)"
            },
            "progress": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Progress value 0.0 to 1.0 (for update_progress)"
            },
            "result": {
                "type": "object",
                "description": "Task result data (for complete_task, update_progress)"
            },
            "errors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Error messages (for update_progress)"
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Warning messages (for update_progress)"
            },
            "context_type": {
                "type": "string",
                "description": "Type of context (for save_context)"
            },
            "context_data": {
                "type": "object",
                "description": "Context data (for save_context)"
            },
            "context_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files related to context (for save_context)"
            },
            "context_decisions": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Decisions made (for save_context)"
            },
            "context_id": {
                "type": "string",
                "description": "Context ID (for load_context)"
            }
        },
        "required": ["operation"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._nexus_manager = None
    
    def _get_nexus_manager(self) -> NexusManager:
        """Get or create Nexus manager"""
        if self._nexus_manager is None and self.context:
            project_root = self.context.get('project_root')
            if project_root:
                self._nexus_manager = NexusManager(Path(project_root))
        
        if self._nexus_manager is None:
            self._nexus_manager = NexusManager(Path.cwd())
        
        return self._nexus_manager
    
    def execute(self, **kwargs) -> ToolResult:
        operation = kwargs.get('operation')
        
        if not operation:
            return ToolResult.fail("Operation is required")
        
        try:
            if operation == "create_project":
                return self._create_project(kwargs)
            elif operation == "start_task":
                return self._start_task(kwargs)
            elif operation == "update_progress":
                return self._update_progress(kwargs)
            elif operation == "complete_task":
                return self._complete_task(kwargs)
            elif operation == "pause_task":
                return self._pause_task(kwargs)
            elif operation == "resume_task":
                return self._resume_task(kwargs)
            elif operation == "save_context":
                return self._save_context(kwargs)
            elif operation == "load_context":
                return self._load_context(kwargs)
            elif operation == "get_status":
                return self._get_status(kwargs)
            elif operation == "get_next_task":
                return self._get_next_task(kwargs)
            else:
                return ToolResult.fail(f"Unknown operation: {operation}")
        
        except Exception as e:
            return ToolResult.fail(f"Error executing Nexus operation: {str(e)}")
    
    def _create_project(self, kwargs: Dict) -> ToolResult:
        """Create a new Nexus project"""
        name = kwargs.get('name')
        description = kwargs.get('description', '')
        requirements = kwargs.get('requirements', [])
        
        if not name:
            return ToolResult.fail("Project name is required")
        
        manager = self._get_nexus_manager()
        task = manager.create_project(name, description, requirements)
        
        return ToolResult.success({
            'project_id': task.id,
            'project_name': task.name,
            'description': task.description,
            'phases': task.subtasks,
            'message': f"Created Nexus project '{name}' with {len(task.subtasks)} phases"
        })
    
    def _start_task(self, kwargs: Dict) -> ToolResult:
        """Start executing a task"""
        task_id = kwargs.get('task_id')
        
        if not task_id:
            return ToolResult.fail("Task ID is required")
        
        manager = self._get_nexus_manager()
        success = manager.start_task(task_id)
        
        if not success:
            return ToolResult.fail(f"Failed to start task {task_id}. Check dependencies.")
        
        return ToolResult.success({
            'task_id': task_id,
            'message': f"Started task {task_id}"
        })
    
    def _update_progress(self, kwargs: Dict) -> ToolResult:
        """Update task progress"""
        task_id = kwargs.get('task_id')
        progress = kwargs.get('progress', 0.0)
        result = kwargs.get('result')
        errors = kwargs.get('errors')
        warnings = kwargs.get('warnings')
        
        if not task_id:
            return ToolResult.fail("Task ID is required")
        
        manager = self._get_nexus_manager()
        success = manager.update_task_progress(
            task_id, progress, result, errors, warnings
        )
        
        if not success:
            return ToolResult.fail(f"Failed to update task {task_id}")
        
        return ToolResult.success({
            'task_id': task_id,
            'progress': progress,
            'message': f"Updated task {task_id} progress to {progress:.1%}"
        })
    
    def _complete_task(self, kwargs: Dict) -> ToolResult:
        """Complete a task"""
        task_id = kwargs.get('task_id')
        result = kwargs.get('result')
        
        if not task_id:
            return ToolResult.fail("Task ID is required")
        
        manager = self._get_nexus_manager()
        success = manager.complete_task(task_id, result)
        
        if not success:
            return ToolResult.fail(f"Failed to complete task {task_id}")
        
        return ToolResult.success({
            'task_id': task_id,
            'result': result,
            'message': f"Completed task {task_id}"
        })
    
    def _pause_task(self, kwargs: Dict) -> ToolResult:
        """Pause a running task"""
        task_id = kwargs.get('task_id')
        
        if not task_id:
            return ToolResult.fail("Task ID is required")
        
        manager = self._get_nexus_manager()
        success = manager.pause_task(task_id)
        
        if not success:
            return ToolResult.fail(f"Failed to pause task {task_id}")
        
        return ToolResult.success({
            'task_id': task_id,
            'message': f"Paused task {task_id}"
        })
    
    def _resume_task(self, kwargs: Dict) -> ToolResult:
        """Resume a paused task"""
        task_id = kwargs.get('task_id')
        
        if not task_id:
            return ToolResult.fail("Task ID is required")
        
        manager = self._get_nexus_manager()
        success = manager.resume_task(task_id)
        
        if not success:
            return ToolResult.fail(f"Failed to resume task {task_id}")
        
        return ToolResult.success({
            'task_id': task_id,
            'message': f"Resumed task {task_id}"
        })
    
    def _save_context(self, kwargs: Dict) -> ToolResult:
        """Save context for a task"""
        task_id = kwargs.get('task_id')
        context_type = kwargs.get('context_type')
        context_data = kwargs.get('context_data', {})
        context_files = kwargs.get('context_files')
        context_decisions = kwargs.get('context_decisions')
        
        if not task_id or not context_type:
            return ToolResult.fail("Task ID and context_type are required")
        
        manager = self._get_nexus_manager()
        context_id = manager.save_context(
            task_id, context_type, context_data, context_files, context_decisions
        )
        
        return ToolResult.success({
            'context_id': context_id,
            'task_id': task_id,
            'context_type': context_type,
            'message': f"Saved context {context_id} for task {task_id}"
        })
    
    def _load_context(self, kwargs: Dict) -> ToolResult:
        """Load context by ID"""
        context_id = kwargs.get('context_id')
        
        if not context_id:
            return ToolResult.fail("Context ID is required")
        
        manager = self._get_nexus_manager()
        context = manager.load_context(context_id)
        
        if not context:
            return ToolResult.fail(f"Context {context_id} not found")
        
        return ToolResult.success({
            'context_id': context_id,
            'context': context.to_dict()
        })
    
    def _get_status(self, kwargs: Dict) -> ToolResult:
        """Get project or task status"""
        task_id = kwargs.get('task_id')
        
        manager = self._get_nexus_manager()
        
        if task_id:
            # Get task status
            if task_id not in manager.tasks:
                return ToolResult.fail(f"Task {task_id} not found")
            
            task = manager.tasks[task_id]
            return ToolResult.success({
                'task': task.to_dict(),
                'context': manager.get_task_context(task_id)
            })
        else:
            # Get overall status (if there's a current project)
            if manager.current_task_id:
                status = manager.get_project_status(manager.current_task_id)
                return ToolResult.success(status)
            else:
                return ToolResult.success({
                    'message': 'No active project. Use create_project to start.'
                })
    
    def _get_next_task(self, kwargs: Dict) -> ToolResult:
        """Get the next task to execute"""
        manager = self._get_nexus_manager()
        next_task = manager.get_next_task()
        
        if not next_task:
            return ToolResult.success({
                'message': 'No tasks ready to execute'
            })
        
        return ToolResult.success({
            'task': next_task.to_dict(),
            'message': f"Next task: {next_task.name}"
        })