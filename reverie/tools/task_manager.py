"""
Task Manager Tool - Organize and track complex work

Provides task management capabilities:
- Add tasks and subtasks
- Update task status
- View task list
- Reorganize tasks
"""

from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import uuid
from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from rich.markup import escape

from .base import BaseTool, ToolResult


class TaskState(Enum):
    NOT_STARTED = "[ ]"
    IN_PROGRESS = "[/]"
    COMPLETED = "[x]"
    CANCELLED = "[-]"


@dataclass
class Task:
    """A task with optional subtasks"""
    id: str
    name: str
    description: str = ""
    state: TaskState = TaskState.NOT_STARTED
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'state': self.state.name,
            'parent_id': self.parent_id,
            'children': self.children,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            state=TaskState[data.get('state', 'NOT_STARTED')],
            parent_id=data.get('parent_id'),
            children=data.get('children', []),
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', '')
        )


class TaskStore:
    """In-memory task storage with JSON persistence"""
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.root_tasks: List[str] = []
        self.file_path: Optional[Path] = None
    
    def configure(self, project_root: Path):
        """Configure persistence path and load data"""
        self.file_path = project_root / 'task_list.json' # Save to project root or .reverie
        self.load()
        
    def save(self):
        """Save tasks to file"""
        if not self.file_path:
            return
            
        data = {
            'tasks': [t.to_dict() for t in self.tasks.values()],
            'root_tasks': self.root_tasks
        }
        
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save tasks: {e}")

    def load(self):
        """Load tasks from file"""
        if not self.file_path or not self.file_path.exists():
            return
            
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.tasks = {}
            self.root_tasks = data.get('root_tasks', [])
            
            for task_data in data.get('tasks', []):
                task = Task.from_dict(task_data)
                self.tasks[task.id] = task
                
        except Exception as e:
            print(f"Failed to load tasks: {e}")

    def find_by_name(self, name: str) -> Optional[Task]:
        """Find a task by name (case-insensitive)"""
        name_lower = name.lower().strip()
        for task in self.tasks.values():
            if task.name.lower().strip() == name_lower:
                return task
        return None

    def add_task(
        self,
        name: str,
        description: str = "",
        parent_id: Optional[str] = None
    ) -> Task:
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        task = Task(
            id=task_id,
            name=name,
            description=description,
            parent_id=parent_id,
            created_at=now,
            updated_at=now
        )
        
        self.tasks[task_id] = task
        
        if parent_id and parent_id in self.tasks:
            self.tasks[parent_id].children.append(task_id)
        else:
            self.root_tasks.append(task_id)
        
        self.save()
        return task
    
    def update_task(
        self,
        task_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        state: Optional[TaskState] = None
    ) -> Optional[Task]:
        
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        if name is not None:
            task.name = name
        if description is not None:
            task.description = description
        if state is not None:
            task.state = state
        
        task.updated_at = datetime.now().isoformat()
        self.save()
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)
    
    def delete_task(self, task_id: str) -> bool:
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        # Delete children first
        for child_id in list(task.children):
            self.delete_task(child_id)
        
        # Remove from parent
        if task.parent_id and task.parent_id in self.tasks:
            parent = self.tasks[task.parent_id]
            if task_id in parent.children:
                parent.children.remove(task_id)
        else:
            if task_id in self.root_tasks:
                self.root_tasks.remove(task_id)
        
        del self.tasks[task_id]
        self.save()
        return True
    
    def to_markdown(self) -> str:
        """Convert task list to markdown with Rich colors"""
        lines = ["[bold underline cyan]Task List[/bold underline cyan]", ""]
        
        def render_task(task_id: str, indent: int = 0):
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            prefix = "  " * indent
            
            # State styling
            if task.state == TaskState.COMPLETED:
                style = "green"
                state_icon = "[x]"
            elif task.state == TaskState.IN_PROGRESS:
                style = "yellow"
                state_icon = "[/]"
            elif task.state == TaskState.CANCELLED:
                style = "dim red"
                state_icon = "[-]"
            else:
                style = "bold white"
                state_icon = "[ ]"
            
            state_str = f"[{style}]{state_icon}[/{style}]"
            name_str = f"[{style}]{escape(task.name)}[/{style}]"
            
            lines.append(f"{prefix}{state_str} {name_str}")
            if task.description:
                lines.append(f"{prefix}  [dim]{escape(task.description)}[/dim]")
            
            for child_id in task.children:
                render_task(child_id, indent + 1)
        
        for task_id in self.root_tasks:
            render_task(task_id)
        
        if not self.root_tasks:
            lines.append("[dim italic]No tasks yet.[/dim italic]")
        
        return '\n'.join(lines)


# Global task store (shared across tool instances)
_task_store = TaskStore()


class TaskManagerTool(BaseTool):
    """
    Tool for managing tasks during complex work.
    """
    
    name = "task_manager"
    
    description = """Manage tasks for organizing complex work.

Operations:
- add_tasks: Add new tasks or subtasks
- update_tasks: Update task name, description, or state
- view_tasklist: View all tasks
- reorganize_tasklist: Reorganize multiple tasks at once

Task states:
- NOT_STARTED: [ ] - Task not begun
- IN_PROGRESS: [/] - Currently working on
- COMPLETED: [x] - Finished
- CANCELLED: [-] - No longer needed

Examples:
- Add task: {"operation": "add_tasks", "tasks": [{"name": "Implement feature X"}]}
- Update: {"operation": "update_tasks", "task_id": "abc123", "state": "COMPLETED"} (You can also use 'name' instead of 'task_id' if unsure of ID)
- View: {"operation": "view_tasklist"}"""
    
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["add_tasks", "update_tasks", "view_tasklist", "reorganize_tasklist"],
                "description": "Operation to perform"
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "state": {"type": "string", "enum": ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]},
                        "parent_id": {"type": "string"}
                    }
                },
                "description": "Tasks to add or updates to apply"
            },
            "task_id": {
                "type": "string",
                "description": "Single task ID or EXACT TASK NAME for update"
            },
            "name": {"type": "string"},
            "description": {"type": "string"},
            "state": {
                "type": "string",
                "enum": ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
            }
        },
        "required": ["operation"]
    }
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        if context and 'project_root' in context:
             _task_store.configure(Path(context['project_root']))

    def get_execution_message(self, **kwargs) -> str:
        operation = kwargs.get('operation')
        if operation == "add_tasks":
            tasks = kwargs.get('tasks', [])
            count = len(tasks)
            return f"Adding {count} task(s) to the project"
        elif operation == "update_tasks":
            task_id = kwargs.get('task_id')
            name = kwargs.get('name')
            target = task_id or name or "tasks"
            return f"Updating task: {target}"
        elif operation == "view_tasklist":
            return "Viewing project task list"
        elif operation == "reorganize_tasklist":
            return "Reorganizing project tasks"
        return f"Managing tasks ({operation})"

    def execute(self, **kwargs) -> ToolResult:
        operation = kwargs.get('operation')
        
        if operation == "add_tasks":
            return self._add_tasks(kwargs.get('tasks', []))
        
        elif operation == "update_tasks":
            # Support both single update and batch update
            task_id = kwargs.get('task_id')
            tasks = kwargs.get('tasks', [])
            
            if task_id or (kwargs.get('name') and not tasks):
                # Single update (allow name as fallback for task_id)
                # If we have task_id, use it. If not, and we have name, we might be looking up by name.
                # Actually, check logic in _update_single
                return self._update_single(
                    task_id,
                    kwargs.get('name'),
                    kwargs.get('description'),
                    kwargs.get('state')
                )
            elif tasks:
                # Batch update
                return self._update_batch(tasks)
            else:
                return ToolResult.fail("Either task_id or tasks array/name is required")
        
        elif operation == "view_tasklist":
            return self._view_tasklist()
        
        elif operation == "reorganize_tasklist":
            return self._reorganize(kwargs.get('tasks', []))
        
        else:
            return ToolResult.fail(f"Unknown operation: {operation}")
    
    def _add_tasks(self, tasks: List[Dict]) -> ToolResult:
        """Add new tasks"""
        if not tasks:
            return ToolResult.fail("No tasks provided")
        
        added = []
        for task_data in tasks:
            task = _task_store.add_task(
                name=task_data.get('name', 'Unnamed task'),
                description=task_data.get('description', ''),
                parent_id=task_data.get('parent_id')
            )
            added.append(task)
        
        output_parts = [f"Added {len(added)} task(s):", ""]
        for task in added:
            output_parts.append(f"- {escape(task.state.value)} {escape(task.name)}")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _update_single(
        self,
        task_id: Optional[str],
        name: Optional[str],
        description: Optional[str],
        state: Optional[str]
    ) -> ToolResult:
        """Update a single task"""
        task_state = TaskState[state] if state else None
        
        target_task = None
        if task_id:
            target_task = _task_store.get_task(task_id)
            if not target_task:
                 # Try as name
                 target_task = _task_store.find_by_name(task_id)
        
        # If still not found and we have a name, try to find by name (assuming name is meant as lookup)
        # But caution: if we are trying to RENAME, 'name' argument is the NEW name.
        # So we only rely on 'task_id' argument for lookup.
        
        if not target_task:
             return ToolResult.fail(f"Task not found: {task_id}")

        task = _task_store.update_task(
            target_task.id,
            name=name,
            description=description,
            state=task_state
        )
        
        if not task:
            return ToolResult.fail(f"Task could not be updated: {task_id}")
        
        return ToolResult.ok(
            f"Updated task:\n- {escape(task.state.value)} {escape(task.name)}"
        )
    
    def _update_batch(self, tasks: List[Dict]) -> ToolResult:
        """Update multiple tasks"""
        updated = []
        errors = []
        
        for task_data in tasks:
            task_id = task_data.get('task_id')
            name = task_data.get('name')
            
            target_task = None
            
            # Strategy: 
            # 1. Try task_id as ID
            # 2. Try task_id as Name
            # 3. If task_id is None, try 'name' as identifier? 
            #    No, 'name' in update is usually the *new* name.
            #    However, if model says {name: "foo", state: "COMPLETED"}, it likely means "find task foo and complete it".
            #    But if it says {name: "new name"}, what is it updating?
            #    We will assume: If no task_id, 'name' is the lookup key. 
            #    If task found, and we want to *rename*, we can't express it easily this way without ID. 
            #    But for state updates, this works.
            
            if task_id:
                target_task = _task_store.get_task(task_id)
                if not target_task:
                    target_task = _task_store.find_by_name(task_id)
            elif name: # Fallback: use name as lookup
                 target_task = _task_store.find_by_name(name)
            
            if not target_task:
                errors.append(f"Task not found: {task_id or name}")
                continue
            
            # If we used 'name' for lookup, we shouldn't use it for update unless it was explicitly meant as such?
            # Actually, standard tool usage is: id=Lookup, name=NewValue.
            # If id is missing, we use name=Lookup. But then we can't rename using name=Lookup.
            # That's an acceptable compromise for "Invisible IDs".
            
            state = task_data.get('state')
            task_state = TaskState[state] if state else None
            
            new_name = name if task_id else None # Only update name if we looked up by ID
            
            updated_task = _task_store.update_task(
                target_task.id,
                name=new_name, 
                description=task_data.get('description'),
                state=task_state
            )
            
            if updated_task:
                updated.append(updated_task)
            else:
                 errors.append(f"Update failed for {target_task.name}")
        
        output_parts = [f"Updated {len(updated)} task(s)"]
        for task in updated:
            output_parts.append(f"- {escape(task.state.value)} {escape(task.name)}")
        
        if errors:
            output_parts.append(f"\nErrors: {', '.join(errors)}")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _view_tasklist(self) -> ToolResult:
        """View all tasks"""
        markdown = _task_store.to_markdown()
        
        # Add summary
        total = len(_task_store.tasks)
        completed = sum(1 for t in _task_store.tasks.values() if t.state == TaskState.COMPLETED)
        in_progress = sum(1 for t in _task_store.tasks.values() if t.state == TaskState.IN_PROGRESS)
        
        summary = f"\n\n[dim]{'─' * 40}[/dim]\n[bold]Total:[/bold] {total} | [green]Completed:[/green] {completed} | [yellow]In Progress:[/yellow] {in_progress}"
        
        return ToolResult.ok(markdown + summary)
    
    def _reorganize(self, tasks: List[Dict]) -> ToolResult:
        """Reorganize tasks (bulk update for reordering)"""
        # For now, this is similar to batch update
        return self._update_batch(tasks)
