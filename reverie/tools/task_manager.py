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
    priority: str = "medium"  # low, medium, high, critical
    phase: str = "implementation"  # design, implementation, content, testing, release
    tags: List[str] = field(default_factory=list)
    estimate: Optional[str] = None  # e.g., "2h", "1d", "30m"
    progress: float = 0.0  # 0.0 to 1.0
    due_date: str = ""
    dependencies: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
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
            'priority': self.priority,
            'phase': self.phase,
            'tags': self.tags,
            'estimate': self.estimate,
            'progress': self.progress,
            'due_date': self.due_date,
            'dependencies': self.dependencies,
            'blockers': self.blockers,
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
            priority=data.get('priority', 'medium'),
            phase=data.get('phase', 'implementation'),
            tags=data.get('tags', []) or [],
            estimate=data.get('estimate', data.get('estimate_minutes')),  # Support old format
            progress=float(data.get('progress', 0.0) or 0.0),
            due_date=data.get('due_date', ''),
            dependencies=data.get('dependencies', []) or [],
            blockers=data.get('blockers', []) or [],
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
    
    def validate_dependencies(self, task_id: str, dependencies: List[str]) -> tuple[bool, str]:
        """
        Validate task dependencies.
        
        Returns:
            (is_valid, error_message) - True if valid, False with error message if invalid
        """
        # Check if all dependency tasks exist
        for dep_id in dependencies:
            if dep_id not in self.tasks:
                return False, f"Dependency task not found: {dep_id}"
        
        # Check for circular dependencies
        if self._has_circular_dependency(task_id, dependencies):
            return False, "Circular dependency detected: task cannot depend on itself directly or indirectly"
        
        return True, ""
    
    def _has_circular_dependency(self, task_id: str, new_dependencies: List[str]) -> bool:
        """
        Check if adding these dependencies would create a circular dependency.
        
        Uses depth-first search to detect cycles.
        """
        # Build a temporary dependency graph including the new dependencies
        visited = set()
        rec_stack = set()
        
        def has_cycle(current_id: str) -> bool:
            visited.add(current_id)
            rec_stack.add(current_id)
            
            # Get dependencies for current task
            if current_id == task_id:
                # Use the new dependencies for the task being updated
                deps = new_dependencies
            elif current_id in self.tasks:
                deps = self.tasks[current_id].dependencies
            else:
                deps = []
            
            for dep_id in deps:
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    # Found a back edge - cycle detected
                    return True
            
            rec_stack.remove(current_id)
            return False
        
        return has_cycle(task_id)

    def add_task(
        self,
        name: str,
        description: str = "",
        parent_id: Optional[str] = None,
        priority: str = "medium",
        phase: str = "implementation",
        tags: Optional[List[str]] = None,
        estimate: Optional[str] = None,
        progress: float = 0.0,
        due_date: str = "",
        dependencies: Optional[List[str]] = None,
        blockers: Optional[List[str]] = None
    ) -> Task:
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        
        # Validate dependencies if provided
        if dependencies:
            is_valid, error_msg = self.validate_dependencies(task_id, dependencies)
            if not is_valid:
                raise ValueError(f"Invalid dependencies: {error_msg}")
        
        task = Task(
            id=task_id,
            name=name,
            description=description,
            parent_id=parent_id,
            priority=priority,
            phase=phase,
            tags=tags or [],
            estimate=estimate,
            progress=progress,
            due_date=due_date,
            dependencies=dependencies or [],
            blockers=blockers or [],
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
        state: Optional[TaskState] = None,
        priority: Optional[str] = None,
        phase: Optional[str] = None,
        tags: Optional[List[str]] = None,
        estimate: Optional[str] = None,
        progress: Optional[float] = None,
        due_date: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        blockers: Optional[List[str]] = None
    ) -> Optional[Task]:
        
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        # Validate dependencies if being updated
        if dependencies is not None:
            is_valid, error_msg = self.validate_dependencies(task_id, dependencies)
            if not is_valid:
                raise ValueError(f"Invalid dependencies: {error_msg}")
        
        if name is not None:
            task.name = name
        if description is not None:
            task.description = description
        if state is not None:
            task.state = state
        if priority is not None:
            task.priority = priority
        if phase is not None:
            task.phase = phase
        if tags is not None:
            task.tags = tags
        if estimate is not None:
            task.estimate = estimate
        if progress is not None:
            task.progress = max(0.0, min(1.0, float(progress)))
        if due_date is not None:
            task.due_date = due_date
        if dependencies is not None:
            task.dependencies = dependencies
        if blockers is not None:
            task.blockers = blockers
        
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
            
            meta = []
            if task.priority:
                meta.append(f"prio:{task.priority}")
            if task.phase:
                meta.append(f"phase:{task.phase}")
            if task.progress:
                meta.append(f"{int(task.progress * 100)}%")
            if task.estimate:
                meta.append(f"est:{task.estimate}")
            if task.due_date:
                meta.append(f"due:{task.due_date}")
            meta_str = f" [dim]({' | '.join(meta)})[/dim]" if meta else ""

            lines.append(f"{prefix}{state_str} {name_str}{meta_str}")
            if task.description:
                lines.append(f"{prefix}  [dim]{escape(task.description)}[/dim]")
            if task.tags:
                lines.append(f"{prefix}  [dim]tags: {escape(', '.join(task.tags))}[/dim]")
            if task.dependencies:
                lines.append(f"{prefix}  [dim]deps: {escape(', '.join(task.dependencies))}[/dim]")
            if task.blockers:
                lines.append(f"{prefix}  [dim]blockers: {escape(', '.join(task.blockers))}[/dim]")
            
            for child_id in task.children:
                render_task(child_id, indent + 1)
        
        for task_id in self.root_tasks:
            render_task(task_id)
        
        if not self.root_tasks:
            lines.append("[dim italic]No tasks yet.[/dim italic]")
        
        return '\n'.join(lines)

    def validate_dependencies(self, task_id: str, dependencies: List[str]) -> tuple[bool, str]:
        """
        Validate task dependencies.

        Returns:
            (is_valid, error_message) - True if valid, False with error message if invalid
        """
        # Check if all dependency tasks exist
        for dep_id in dependencies:
            if dep_id not in self.tasks:
                return False, f"Dependency task not found: {dep_id}"

        # Check for circular dependencies
        if self._has_circular_dependency(task_id, dependencies):
            return False, "Circular dependency detected: task cannot depend on itself directly or indirectly"

        return True, ""

    def _has_circular_dependency(self, task_id: str, new_dependencies: List[str]) -> bool:
        """
        Check if adding these dependencies would create a circular dependency.

        Uses depth-first search to detect cycles.
        """
        # Build a temporary dependency graph including the new dependencies
        visited = set()
        rec_stack = set()

        def has_cycle(current_id: str) -> bool:
            visited.add(current_id)
            rec_stack.add(current_id)

            # Get dependencies for current task
            if current_id == task_id:
                # Use the new dependencies for the task being updated
                deps = new_dependencies
            elif current_id in self.tasks:
                deps = self.tasks[current_id].dependencies
            else:
                deps = []

            for dep_id in deps:
                if dep_id not in visited:
                    if has_cycle(dep_id):
                        return True
                elif dep_id in rec_stack:
                    # Found a back edge - cycle detected
                    return True

            rec_stack.remove(current_id)
            return False

        return has_cycle(task_id)


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
- update_tasks: Update task fields or state
- view_tasklist: View all tasks (supports filtering)
- reorganize_tasklist: Reorganize multiple tasks at once

Task states:
- NOT_STARTED: [ ] - Task not begun
- IN_PROGRESS: [/] - Currently working on
- COMPLETED: [x] - Finished
- CANCELLED: [-] - No longer needed

Task phases:
- design: Design and planning phase
- implementation: Implementation phase
- content: Content creation phase
- testing: Testing phase
- release: Release phase

Task priorities:
- low: Low priority
- medium: Medium priority (default)
- high: High priority
- critical: Critical priority

Examples:
- Add task: {"operation": "add_tasks", "tasks": [{"name": "Implement feature X", "phase": "implementation", "priority": "high", "estimate": "2h"}]}
- Update: {"operation": "update_tasks", "task_id": "abc123", "state": "COMPLETED", "progress": 1.0} (You can also use 'name' instead of 'task_id' if unsure of ID)
- View: {"operation": "view_tasklist"}
- View with filter: {"operation": "view_tasklist", "filter": {"state": "IN_PROGRESS", "phase": "design"}}"""
    
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
                        "parent_id": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "phase": {"type": "string", "enum": ["design", "implementation", "content", "testing", "release"]},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "estimate": {"type": "string", "description": "Time estimate (e.g., '2h', '1d', '30m')"},
                        "progress": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Progress from 0.0 to 1.0"},
                        "due_date": {"type": "string"},
                        "dependencies": {"type": "array", "items": {"type": "string"}, "description": "List of task IDs this task depends on"},
                        "blockers": {"type": "array", "items": {"type": "string"}, "description": "List of blocking issues"}
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
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"]
            },
            "phase": {
                "type": "string",
                "enum": ["design", "implementation", "content", "testing", "release"]
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "estimate": {"type": "string", "description": "Time estimate (e.g., '2h', '1d', '30m')"},
            "progress": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Progress from 0.0 to 1.0"},
            "due_date": {"type": "string"},
            "dependencies": {"type": "array", "items": {"type": "string"}, "description": "List of task IDs this task depends on"},
            "blockers": {"type": "array", "items": {"type": "string"}, "description": "List of blocking issues"},
            "filter": {
                "type": "object",
                "properties": {
                    "state": {"type": "string"},
                    "phase": {"type": "string"},
                    "tag": {"type": "string"},
                    "priority": {"type": "string"}
                }
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
                    kwargs.get('state'),
                    kwargs.get('priority'),
                    kwargs.get('phase'),
                    kwargs.get('tags'),
                    kwargs.get('estimate'),
                    kwargs.get('progress'),
                    kwargs.get('due_date'),
                    kwargs.get('dependencies'),
                    kwargs.get('blockers')
                )
            elif tasks:
                # Batch update
                return self._update_batch(tasks)
            else:
                return ToolResult.fail("Either task_id or tasks array/name is required")
        
        elif operation == "view_tasklist":
            return self._view_tasklist(kwargs.get('filter'))
        
        elif operation == "reorganize_tasklist":
            return self._reorganize(kwargs.get('tasks', []))
        
        else:
            return ToolResult.fail(f"Unknown operation: {operation}")
    
    def _add_tasks(self, tasks: List[Dict]) -> ToolResult:
        """Add new tasks"""
        if not tasks:
            return ToolResult.fail("No tasks provided")
        
        added = []
        errors = []
        
        for task_data in tasks:
            try:
                task = _task_store.add_task(
                    name=task_data.get('name', 'Unnamed task'),
                    description=task_data.get('description', ''),
                    parent_id=task_data.get('parent_id'),
                    priority=task_data.get('priority', 'medium'),
                    phase=task_data.get('phase', 'implementation'),
                    tags=task_data.get('tags', []),
                    estimate=task_data.get('estimate'),
                    progress=task_data.get('progress', 0.0),
                    due_date=task_data.get('due_date', ''),
                    dependencies=task_data.get('dependencies', []),
                    blockers=task_data.get('blockers', [])
                )
                added.append(task)
            except ValueError as e:
                errors.append(f"Failed to add task '{task_data.get('name', 'Unnamed')}': {str(e)}")
        
        if not added and errors:
            return ToolResult.fail('\n'.join(errors))
        
        output_parts = [f"Added {len(added)} task(s):", ""]
        for task in added:
            output_parts.append(f"- {escape(task.state.value)} {escape(task.name)}")
        
        if errors:
            output_parts.append("\nErrors:")
            output_parts.extend(errors)
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _update_single(
        self,
        task_id: Optional[str],
        name: Optional[str],
        description: Optional[str],
        state: Optional[str],
        priority: Optional[str],
        phase: Optional[str],
        tags: Optional[List[str]],
        estimate: Optional[str],
        progress: Optional[float],
        due_date: Optional[str],
        dependencies: Optional[List[str]],
        blockers: Optional[List[str]]
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

        try:
            task = _task_store.update_task(
                target_task.id,
                name=name,
                description=description,
                state=task_state,
                priority=priority,
                phase=phase,
                tags=tags,
                estimate=estimate,
                progress=progress,
                due_date=due_date,
                dependencies=dependencies,
                blockers=blockers
            )
        except ValueError as e:
            return ToolResult.fail(f"Update failed: {str(e)}")
        
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
            
            try:
                updated_task = _task_store.update_task(
                    target_task.id,
                    name=new_name, 
                    description=task_data.get('description'),
                    state=task_state,
                    priority=task_data.get('priority'),
                    phase=task_data.get('phase'),
                    tags=task_data.get('tags'),
                    estimate=task_data.get('estimate'),
                    progress=task_data.get('progress'),
                    due_date=task_data.get('due_date'),
                    dependencies=task_data.get('dependencies'),
                    blockers=task_data.get('blockers')
                )
                
                if updated_task:
                    updated.append(updated_task)
                else:
                    errors.append(f"Update failed for {target_task.name}")
            except ValueError as e:
                errors.append(f"Update failed for {target_task.name}: {str(e)}")
        
        output_parts = [f"Updated {len(updated)} task(s)"]
        for task in updated:
            output_parts.append(f"- {escape(task.state.value)} {escape(task.name)}")
        
        if errors:
            output_parts.append(f"\nErrors: {', '.join(errors)}")
        
        return ToolResult.ok('\n'.join(output_parts))
    
    def _view_tasklist(self, filters: Optional[Dict] = None) -> ToolResult:
        """View all tasks, optionally filtered"""
        if not filters:
            markdown = _task_store.to_markdown()
        else:
            markdown = self._filtered_markdown(filters)
        
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

    def _filtered_markdown(self, filters: Dict) -> str:
        """Render task list with filters"""
        state_filter = filters.get("state")
        phase_filter = filters.get("phase")
        tag_filter = filters.get("tag")
        priority_filter = filters.get("priority")

        lines = ["[bold underline cyan]Task List (Filtered)[/bold underline cyan]", ""]

        def include(task: Task) -> bool:
            if state_filter and task.state.name != state_filter:
                return False
            if phase_filter and task.phase != phase_filter:
                return False
            if tag_filter and tag_filter not in task.tags:
                return False
            if priority_filter and task.priority != priority_filter:
                return False
            return True

        def render_task(task_id: str, indent: int = 0):
            if task_id not in _task_store.tasks:
                return
            task = _task_store.tasks[task_id]
            if not include(task):
                for child_id in task.children:
                    render_task(child_id, indent + 1)
                return
            prefix = "  " * indent
            state_icon = task.state.value
            name_str = escape(task.name)
            lines.append(f"{prefix}{state_icon} {name_str}")
            for child_id in task.children:
                render_task(child_id, indent + 1)

        for task_id in _task_store.root_tasks:
            render_task(task_id)

        if len(lines) <= 2:
            lines.append("[dim italic]No tasks match filters.[/dim italic]")

        return "\n".join(lines)
