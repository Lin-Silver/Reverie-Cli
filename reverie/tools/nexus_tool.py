"""
Reverie-Nexus Tool - Advanced large-scale project development tool

Reverie-Nexus is a powerful tool designed for developing large-scale projects
with the ability to work continuously for 24+ hours without stopping.

Key Features:
- External context management to bypass token limits
- Persistent task state and progress tracking
- Automatic checkpoint and recovery
- Intelligent context compression and expansion
- Long-running task orchestration
- Multi-phase development workflow
- Self-healing and error recovery
- Progress persistence across sessions

This tool enables the AI to complete complex, multi-day projects
by managing context externally and maintaining state between operations.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
import json
import time
import hashlib
from datetime import datetime
from collections import deque


class NexusPhase(Enum):
    """Phases of Nexus development workflow"""
    INITIALIZATION = auto()
    PLANNING = auto()
    DESIGN = auto()
    IMPLEMENTATION = auto()
    TESTING = auto()
    INTEGRATION = auto()
    DOCUMENTATION = auto()
    VERIFICATION = auto()
    COMPLETION = auto()


class NexusState(Enum):
    """States of a Nexus task"""
    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    WAITING_FOR_INPUT = auto()
    ERROR = auto()
    COMPLETED = auto()
    CANCELLED = auto()


@dataclass
class NexusTask:
    """A task in the Nexus workflow"""
    id: str
    name: str
    description: str
    phase: NexusPhase
    state: NexusState
    
    # Task details
    dependencies: List[str] = field(default_factory=list)
    subtasks: List[str] = field(default_factory=list)
    
    # Progress tracking
    progress: float = 0.0  # 0.0 to 1.0
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    
    # Context management
    context_snapshot: Dict = field(default_factory=dict)
    external_context_refs: List[str] = field(default_factory=list)
    
    # Execution
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Results
    result: Optional[Dict] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'phase': self.phase.name,
            'state': self.state.name,
            'dependencies': self.dependencies,
            'subtasks': self.subtasks,
            'progress': self.progress,
            'estimated_hours': self.estimated_hours,
            'actual_hours': self.actual_hours,
            'context_snapshot': self.context_snapshot,
            'external_context_refs': self.external_context_refs,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'result': self.result,
            'errors': self.errors,
            'warnings': self.warnings
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'NexusTask':
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            phase=NexusPhase[data['phase']],
            state=NexusState[data['state']],
            dependencies=data.get('dependencies', []),
            subtasks=data.get('subtasks', []),
            progress=data.get('progress', 0.0),
            estimated_hours=data.get('estimated_hours', 0.0),
            actual_hours=data.get('actual_hours', 0.0),
            context_snapshot=data.get('context_snapshot', {}),
            external_context_refs=data.get('external_context_refs', []),
            created_at=data.get('created_at', time.time()),
            started_at=data.get('started_at'),
            completed_at=data.get('completed_at'),
            result=data.get('result'),
            errors=data.get('errors', []),
            warnings=data.get('warnings', [])
        )


@dataclass
class NexusContext:
    """External context storage for Nexus"""
    id: str
    task_id: str
    context_type: str  # design, implementation, testing, etc.
    
    # Context data
    data: Dict = field(default_factory=dict)
    files: List[str] = field(default_factory=list)
    decisions: List[Dict] = field(default_factory=list)
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    size_bytes: int = 0
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'task_id': self.task_id,
            'context_type': self.context_type,
            'data': self.data,
            'files': self.files,
            'decisions': self.decisions,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'size_bytes': self.size_bytes
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'NexusContext':
        return cls(
            id=data['id'],
            task_id=data['task_id'],
            context_type=data['context_type'],
            data=data.get('data', {}),
            files=data.get('files', []),
            decisions=data.get('decisions', []),
            created_at=data.get('created_at', time.time()),
            updated_at=data.get('updated_at', time.time()),
            size_bytes=data.get('size_bytes', 0)
        )


class NexusManager:
    """
    Manages Nexus workflow for large-scale project development.
    
    Features:
    - Task orchestration and dependency management
    - External context storage and retrieval
    - Progress tracking and persistence
    - Automatic checkpoint and recovery
    - Long-running task support
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.nexus_dir = project_root / '.reverie' / 'nexus'
        self.nexus_dir.mkdir(parents=True, exist_ok=True)
        
        # Task storage
        self.tasks: Dict[str, NexusTask] = {}
        self.contexts: Dict[str, NexusContext] = {}
        
        # Execution state
        self.current_task_id: Optional[str] = None
        self.execution_log: List[Dict] = []
        
        # Load existing state
        self._load_state()
    
    def create_project(
        self,
        project_name: str,
        description: str,
        requirements: List[str]
    ) -> NexusTask:
        """
        Create a new Nexus project.
        
        This initializes a complete development workflow for a large project.
        """
        project_id = self._generate_id()
        
        # Create main project task
        project_task = NexusTask(
            id=project_id,
            name=project_name,
            description=description,
            phase=NexusPhase.INITIALIZATION,
            state=NexusState.IDLE
        )
        
        # Create subtasks for each phase
        phases = [
            (NexusPhase.PLANNING, "Planning Phase", "Create detailed project plan"),
            (NexusPhase.DESIGN, "Design Phase", "Design system architecture"),
            (NexusPhase.IMPLEMENTATION, "Implementation Phase", "Implement core features"),
            (NexusPhase.TESTING, "Testing Phase", "Test all functionality"),
            (NexusPhase.INTEGRATION, "Integration Phase", "Integrate all components"),
            (NexusPhase.DOCUMENTATION, "Documentation Phase", "Write documentation"),
            (NexusPhase.VERIFICATION, "Verification Phase", "Verify all requirements"),
            (NexusPhase.COMPLETION, "Completion Phase", "Finalize and deliver")
        ]
        
        for i, (phase, name, desc) in enumerate(phases):
            subtask_id = self._generate_id()
            subtask = NexusTask(
                id=subtask_id,
                name=name,
                description=desc,
                phase=phase,
                state=NexusState.IDLE
            )
            
            # Set dependencies
            if i > 0:
                subtask.dependencies = [project_task.subtasks[i-1]]
            
            self.tasks[subtask_id] = subtask
            project_task.subtasks.append(subtask_id)
        
        # Store requirements in context
        context = NexusContext(
            id=self._generate_id(),
            task_id=project_id,
            context_type='requirements',
            data={
                'requirements': requirements,
                'project_name': project_name,
                'description': description
            }
        )
        self.contexts[context.id] = context
        project_task.external_context_refs.append(context.id)
        
        self.tasks[project_id] = project_task
        self._save_state()
        
        return project_task
    
    def start_task(self, task_id: str) -> bool:
        """Start executing a task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        # Check dependencies
        for dep_id in task.dependencies:
            dep_task = self.tasks.get(dep_id)
            if dep_task and dep_task.state != NexusState.COMPLETED:
                return False
        
        task.state = NexusState.RUNNING
        task.started_at = time.time()
        self.current_task_id = task_id
        
        self._log_event(task_id, 'started', {})
        self._save_state()
        
        return True
    
    def update_task_progress(
        self,
        task_id: str,
        progress: float,
        result: Optional[Dict] = None,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None
    ) -> bool:
        """Update task progress"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.progress = max(0.0, min(1.0, progress))
        
        if result is not None:
            task.result = result
        
        if errors:
            task.errors.extend(errors)
        
        if warnings:
            task.warnings.extend(warnings)
        
        # Update actual hours
        if task.started_at:
            task.actual_hours = (time.time() - task.started_at) / 3600
        
        self._log_event(task_id, 'progress_update', {
            'progress': progress,
            'actual_hours': task.actual_hours
        })
        self._save_state()
        
        return True
    
    def complete_task(self, task_id: str, result: Optional[Dict] = None) -> bool:
        """Mark a task as completed"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        task.state = NexusState.COMPLETED
        task.progress = 1.0
        task.completed_at = time.time()
        
        if result:
            task.result = result
        
        # Update actual hours
        if task.started_at:
            task.actual_hours = (task.completed_at - task.started_at) / 3600
        
        self._log_event(task_id, 'completed', {
            'actual_hours': task.actual_hours
        })
        self._save_state()
        
        return True
    
    def pause_task(self, task_id: str) -> bool:
        """Pause a running task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.state == NexusState.RUNNING:
            task.state = NexusState.PAUSED
            self._log_event(task_id, 'paused', {})
            self._save_state()
            return True
        
        return False
    
    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task.state == NexusState.PAUSED:
            task.state = NexusState.RUNNING
            self._log_event(task_id, 'resumed', {})
            self._save_state()
            return True
        
        return False
    
    def save_context(
        self,
        task_id: str,
        context_type: str,
        data: Dict,
        files: Optional[List[str]] = None,
        decisions: Optional[List[Dict]] = None
    ) -> str:
        """Save context for a task"""
        if task_id not in self.tasks:
            return ""
        
        context = NexusContext(
            id=self._generate_id(),
            task_id=task_id,
            context_type=context_type,
            data=data,
            files=files or [],
            decisions=decisions or []
        )
        
        # Calculate size
        context.size_bytes = len(json.dumps(data).encode('utf-8'))
        
        self.contexts[context.id] = context
        self.tasks[task_id].external_context_refs.append(context.id)
        
        self._save_state()
        
        return context.id
    
    def load_context(self, context_id: str) -> Optional[NexusContext]:
        """Load context by ID"""
        return self.contexts.get(context_id)
    
    def get_task_context(self, task_id: str) -> Dict:
        """Get all context for a task"""
        if task_id not in self.tasks:
            return {}
        
        task = self.tasks[task_id]
        contexts = []
        
        for ctx_id in task.external_context_refs:
            if ctx_id in self.contexts:
                contexts.append(self.contexts[ctx_id].to_dict())
        
        return {
            'task': task.to_dict(),
            'contexts': contexts
        }
    
    def get_next_task(self) -> Optional[NexusTask]:
        """Get the next task to execute"""
        # Find tasks that are ready to run
        ready_tasks = []
        
        for task in self.tasks.values():
            if task.state == NexusState.IDLE:
                # Check if all dependencies are completed
                deps_completed = all(
                    self.tasks.get(dep_id, NexusTask(
                        id='', name='', description='',
                        phase=NexusPhase.INITIALIZATION,
                        state=NexusState.COMPLETED
                    )).state == NexusState.COMPLETED
                    for dep_id in task.dependencies
                )
                
                if deps_completed:
                    ready_tasks.append(task)
        
        if not ready_tasks:
            return None
        
        # Return the task with the most dependencies completed
        ready_tasks.sort(key=lambda t: len(t.dependencies), reverse=True)
        return ready_tasks[0]
    
    def get_project_status(self, project_id: str) -> Dict:
        """Get overall project status"""
        if project_id not in self.tasks:
            return {}
        
        project = self.tasks[project_id]
        
        # Calculate overall progress
        total_progress = 0.0
        completed_tasks = 0
        total_tasks = len(project.subtasks)
        
        for subtask_id in project.subtasks:
            subtask = self.tasks.get(subtask_id)
            if subtask:
                total_progress += subtask.progress
                if subtask.state == NexusState.COMPLETED:
                    completed_tasks += 1
        
        overall_progress = total_progress / total_tasks if total_tasks > 0 else 0.0
        
        return {
            'project': project.to_dict(),
            'overall_progress': overall_progress,
            'completed_tasks': completed_tasks,
            'total_tasks': total_tasks,
            'current_phase': self._get_current_phase(project),
            'estimated_completion': self._estimate_completion(project)
        }
    
    def _get_current_phase(self, project: NexusTask) -> str:
        """Get the current phase of the project"""
        for subtask_id in project.subtasks:
            subtask = self.tasks.get(subtask_id)
            if subtask and subtask.state in [NexusState.RUNNING, NexusState.PAUSED]:
                return subtask.phase.name
        
        # If no running task, find the first incomplete task
        for subtask_id in project.subtasks:
            subtask = self.tasks.get(subtask_id)
            if subtask and subtask.state == NexusState.IDLE:
                return subtask.phase.name
        
        return "COMPLETED"
    
    def _estimate_completion(self, project: NexusTask) -> Optional[float]:
        """Estimate completion time"""
        total_estimated = 0.0
        total_actual = 0.0
        
        for subtask_id in project.subtasks:
            subtask = self.tasks.get(subtask_id)
            if subtask:
                if subtask.state == NexusState.COMPLETED:
                    total_actual += subtask.actual_hours
                else:
                    total_estimated += subtask.estimated_hours
        
        if total_estimated == 0:
            return None
        
        return time.time() + (total_estimated * 3600)
    
    def _generate_id(self) -> str:
        """Generate a unique ID"""
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    
    def _log_event(self, task_id: str, event_type: str, data: Dict) -> None:
        """Log an event"""
        self.execution_log.append({
            'timestamp': time.time(),
            'task_id': task_id,
            'event_type': event_type,
            'data': data
        })
    
    def _save_state(self) -> None:
        """Save Nexus state to disk"""
        state_file = self.nexus_dir / 'state.json'
        
        state = {
            'tasks': {tid: task.to_dict() for tid, task in self.tasks.items()},
            'contexts': {cid: ctx.to_dict() for cid, ctx in self.contexts.items()},
            'current_task_id': self.current_task_id,
            'execution_log': self.execution_log
        }
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self) -> None:
        """Load Nexus state from disk"""
        state_file = self.nexus_dir / 'state.json'
        
        if not state_file.exists():
            return
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # Load tasks
            for tid, task_data in state.get('tasks', {}).items():
                self.tasks[tid] = NexusTask.from_dict(task_data)
            
            # Load contexts
            for cid, ctx_data in state.get('contexts', {}).items():
                self.contexts[cid] = NexusContext.from_dict(ctx_data)
            
            self.current_task_id = state.get('current_task_id')
            self.execution_log = state.get('execution_log', [])
            
        except Exception as e:
            print(f"Error loading Nexus state: {e}")
    
    def cleanup_completed(self, days_old: int = 7) -> int:
        """Clean up completed tasks older than specified days"""
        cutoff_time = time.time() - (days_old * 24 * 3600)
        removed = 0
        
        to_remove = []
        for tid, task in self.tasks.items():
            if (task.state == NexusState.COMPLETED and
                task.completed_at and
                task.completed_at < cutoff_time):
                to_remove.append(tid)
        
        for tid in to_remove:
            # Remove associated contexts
            task = self.tasks[tid]
            for ctx_id in task.external_context_refs:
                if ctx_id in self.contexts:
                    del self.contexts[ctx_id]
            
            del self.tasks[tid]
            removed += 1
        
        if removed > 0:
            self._save_state()
        
        return removed