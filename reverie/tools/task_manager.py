"""
Task Manager Tool - Organize and track complex work.

The canonical human-facing artifact is a checklist-only `artifacts/Tasks.md` file.
Structured metadata is persisted separately in `artifacts/task_list.json`.
"""

from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from .base import BaseTool, ToolResult


CHECKLIST_LINE_RE = re.compile(r"^(?P<indent>\s*)\[(?P<state> |/|x|-)\]\s+(?P<name>.+?)\s*$")
ARTIFACTS_DIR_NAME = "artifacts"


class TaskState(Enum):
    NOT_STARTED = "[ ]"
    IN_PROGRESS = "[/]"
    COMPLETED = "[x]"
    CANCELLED = "[-]"

    @classmethod
    def from_checklist_marker(cls, marker: str) -> "TaskState":
        mapping = {
            " ": cls.NOT_STARTED,
            "/": cls.IN_PROGRESS,
            "x": cls.COMPLETED,
            "-": cls.CANCELLED,
        }
        return mapping[marker]


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
    """In-memory task storage with JSON + checklist persistence."""
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.root_tasks: List[str] = []
        self.file_path: Optional[Path] = None
        self.markdown_path: Optional[Path] = None
    
    def configure(self, project_root: Path):
        """Configure persistence paths and load data."""
        artifacts_dir = project_root / ARTIFACTS_DIR_NAME
        self.file_path = artifacts_dir / "task_list.json"
        self.markdown_path = artifacts_dir / "Tasks.md"
        self.load()
        
    def save(self):
        """Persist tasks to JSON metadata and checklist markdown."""
        data = {
            "tasks": [task.to_dict() for task in self.tasks.values()],
            "root_tasks": self.root_tasks,
        }

        if self.file_path:
            try:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                self.file_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"Failed to save tasks JSON: {e}")

        if self.markdown_path:
            try:
                self.markdown_path.parent.mkdir(parents=True, exist_ok=True)
                self.markdown_path.write_text(self.to_checklist_markdown(), encoding="utf-8")
            except Exception as e:
                print(f"Failed to save tasks markdown: {e}")

    def load(self):
        """Load tasks from JSON metadata or fallback checklist markdown."""
        self.tasks = {}
        self.root_tasks = []

        if self.file_path and self.file_path.exists():
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
                for task_data in data.get("tasks", []):
                    task = Task.from_dict(task_data)
                    self.tasks[task.id] = task
                self.root_tasks = [
                    task_id for task_id in data.get("root_tasks", []) if task_id in self.tasks
                ]
                self._repair_relationships()
                return
            except Exception as e:
                print(f"Failed to load tasks JSON: {e}")

        if self.markdown_path and self.markdown_path.exists():
            try:
                self._load_from_checklist(self.markdown_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Failed to load tasks markdown: {e}")

    def _repair_relationships(self):
        """Normalize parent/child/root relationships after loading."""
        for task in self.tasks.values():
            task.children = [child_id for child_id in task.children if child_id in self.tasks]

        computed_roots: List[str] = []
        for task_id, task in self.tasks.items():
            if task.parent_id and task.parent_id not in self.tasks:
                task.parent_id = None

            if task.parent_id:
                parent = self.tasks[task.parent_id]
                if task_id not in parent.children:
                    parent.children.append(task_id)
            else:
                computed_roots.append(task_id)

        ordered_roots = [task_id for task_id in self.root_tasks if task_id in computed_roots]
        ordered_roots.extend(task_id for task_id in computed_roots if task_id not in ordered_roots)
        self.root_tasks = ordered_roots

    def _load_from_checklist(self, text: str):
        """Hydrate tasks from a checklist-only markdown document."""
        stack: List[str] = []

        for raw_line in text.splitlines():
            if not raw_line.strip():
                continue

            match = CHECKLIST_LINE_RE.match(raw_line)
            if not match:
                continue

            indent_text = match.group("indent").replace("\t", "  ")
            indent_level = max(0, len(indent_text) // 2)
            while len(stack) > indent_level:
                stack.pop()

            parent_id = stack[-1] if stack else None
            now = datetime.now().isoformat()
            task_id = str(uuid.uuid4())[:8]
            task = Task(
                id=task_id,
                name=match.group("name").strip(),
                state=TaskState.from_checklist_marker(match.group("state")),
                parent_id=parent_id,
                created_at=now,
                updated_at=now,
            )
            self.tasks[task_id] = task

            if parent_id and parent_id in self.tasks:
                self.tasks[parent_id].children.append(task_id)
            else:
                self.root_tasks.append(task_id)

            stack.append(task_id)

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

    def iter_tasks(self) -> List[tuple[int, Task]]:
        """Return tasks in display order with indentation level."""
        ordered: List[tuple[int, Task]] = []
        visited = set()

        def walk(task_id: str, indent: int = 0):
            if task_id in visited or task_id not in self.tasks:
                return

            visited.add(task_id)
            task = self.tasks[task_id]
            ordered.append((indent, task))

            for child_id in task.children:
                walk(child_id, indent + 1)

        for task_id in self.root_tasks:
            walk(task_id)

        # Include orphaned tasks so the rendered output always shows the full list.
        for task_id in self.tasks:
            walk(task_id)

        return ordered

    def to_checklist_markdown(self) -> str:
        """Render the canonical checklist-only markdown artifact."""
        lines = []
        for indent, task in self.iter_tasks():
            prefix = "  " * indent
            lines.append(f"{prefix}{task.state.value} {task.name.strip()}")
        return "\n".join(lines).strip()

    def to_markdown(self) -> str:
        """Compatibility wrapper that returns checklist-only markdown."""
        return self.to_checklist_markdown()


# Global task store (shared across tool instances)
_task_store = TaskStore()


class TaskManagerTool(BaseTool):
    """
    Tool for managing tasks during complex work.
    """
    
    name = "task_manager"
    
    description = """Manage project work as a checklist-first task system.

Canonical artifact:
- Always sync tasks to `artifacts/Tasks.md`
- `artifacts/Tasks.md` must contain checklist lines only, such as `[ ] Implement parser`
- Do not add headings, prose, IDs, summaries, metadata blocks, or rich formatting to `artifacts/Tasks.md`

Best use:
- Break large requests into many small, concrete, verifiable tasks
- Keep only one task `IN_PROGRESS` when practical
- Use filters to inspect focused slices of the checklist
- `artifacts/task_list.json` stores metadata while `artifacts/Tasks.md` stays checklist-only

Operations:
- add_tasks
- update_tasks
- view_tasklist
- reorganize_tasklist

Task states:
- NOT_STARTED => [ ]
- IN_PROGRESS => [/]
- COMPLETED => [x]
- CANCELLED => [-]"""
    
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
            return f"Adding {count} task(s) to artifacts/Tasks.md"
        elif operation == "update_tasks":
            task_id = kwargs.get('task_id')
            name = kwargs.get('name')
            target = task_id or name or "tasks"
            return f"Updating task checklist: {target}"
        elif operation == "view_tasklist":
            return "Viewing artifacts/Tasks.md checklist"
        elif operation == "reorganize_tasklist":
            return "Reorganizing artifacts/Tasks.md checklist"
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

    def _matches_filters(self, task: Task, filters: Optional[Dict] = None) -> bool:
        """Return True when a task matches the supplied filters."""
        if not filters:
            return True

        state_filter = filters.get("state")
        phase_filter = filters.get("phase")
        tag_filter = filters.get("tag")
        priority_filter = filters.get("priority")

        if state_filter and task.state.name != state_filter:
            return False
        if phase_filter and task.phase != phase_filter:
            return False
        if tag_filter and tag_filter not in task.tags:
            return False
        if priority_filter and task.priority != priority_filter:
            return False
        return True

    def _collect_task_entries(self, filters: Optional[Dict] = None) -> List[Dict]:
        """Collect task data in display order for text and structured results."""
        entries = []

        for indent, task in _task_store.iter_tasks():
            if not self._matches_filters(task, filters):
                continue

            entry = task.to_dict()
            entry["state_icon"] = task.state.value
            entry["state_label"] = task.state.name.replace("_", " ").title()
            entry["indent"] = indent
            entries.append(entry)

        return entries

    def _build_summary_data(self) -> Dict[str, int]:
        """Build aggregate counts for the full task list."""
        tasks = list(_task_store.tasks.values())
        return {
            "total": len(tasks),
            "not_started": sum(1 for task in tasks if task.state == TaskState.NOT_STARTED),
            "in_progress": sum(1 for task in tasks if task.state == TaskState.IN_PROGRESS),
            "completed": sum(1 for task in tasks if task.state == TaskState.COMPLETED),
            "cancelled": sum(1 for task in tasks if task.state == TaskState.CANCELLED),
        }

    def _render_task_entries(self, entries: List[Dict]) -> str:
        """Render checklist-only task lines."""
        lines = []
        for entry in entries:
            prefix = "  " * entry["indent"]
            lines.append(f"{prefix}{entry['state_icon']} {entry['name']}")
        return "\n".join(lines).strip()

    def _build_task_payload(self, filters: Optional[Dict] = None) -> Dict:
        """Build structured result data for checklist views and metadata."""
        all_entries = self._collect_task_entries()
        filtered_entries = self._collect_task_entries(filters) if filters else all_entries

        return {
            "tasks": all_entries,
            "task_statuses": [
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "state": entry["state"],
                    "state_icon": entry["state_icon"],
                }
                for entry in all_entries
            ],
            "filtered_tasks": filtered_entries,
            "filters": filters or {},
            "summary": self._build_summary_data(),
            "checklist": _task_store.to_checklist_markdown(),
            "filtered_checklist": self._render_task_entries(filtered_entries),
            "task_markdown_path": str(_task_store.markdown_path) if _task_store.markdown_path else "",
            "task_json_path": str(_task_store.file_path) if _task_store.file_path else "",
        }

    def _build_task_result(
        self,
        message: str,
        *,
        filters: Optional[Dict] = None,
        extra_data: Optional[Dict] = None
    ) -> ToolResult:
        """Create a task-manager result whose text body stays checklist-only."""
        payload = self._build_task_payload(filters)
        payload["message"] = message
        if extra_data:
            payload.update(extra_data)

        rendered = payload["filtered_checklist"] if filters else payload["checklist"]
        return ToolResult.ok(rendered, data=payload)
    
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

        return self._build_task_result(
            f"Added {len(added)} task(s)",
            extra_data={
                "added_tasks": [task.to_dict() for task in added],
                "errors": errors,
            }
        )
    
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

        return self._build_task_result(
            "Updated 1 task",
            extra_data={
                "updated_tasks": [task.to_dict()],
            }
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
        
        return self._build_task_result(
            f"Updated {len(updated)} task(s)",
            extra_data={
                "updated_tasks": [task.to_dict() for task in updated],
                "errors": errors,
            }
        )
    
    def _view_tasklist(self, filters: Optional[Dict] = None) -> ToolResult:
        """View all tasks, optionally filtered"""
        message = "Viewing task checklist"
        if filters:
            message = f"Viewing task checklist with filters: {json.dumps(filters, ensure_ascii=False)}"
        return self._build_task_result(message, filters=filters)
    
    def _reorganize(self, tasks: List[Dict]) -> ToolResult:
        """Reorganize tasks (bulk update for reordering)"""
        # For now, this is similar to batch update
        return self._update_batch(tasks)

    def _filtered_markdown(self, filters: Dict) -> str:
        """Render task list with filters"""
        return self._render_task_entries(self._collect_task_entries(filters))
