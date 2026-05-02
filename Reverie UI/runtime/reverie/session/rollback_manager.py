"""
Rollback Manager - Advanced rollback functionality

This module provides advanced rollback capabilities:
- Rollback to previous user question
- Rollback to previous tool call
- Rollback to specific checkpoint
- Undo/redo operations
- File state restoration
"""

from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import json
import shutil

from .operation_history import OperationHistory, Operation, OperationType
from .checkpoint import CheckpointManager, Checkpoint


@dataclass
class RollbackResult:
    """Result of a rollback operation"""
    success: bool
    message: str
    restored_files: List[str] = None
    restored_messages: List[Dict] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.restored_files is None:
            self.restored_files = []
        if self.restored_messages is None:
            self.restored_messages = []
        if self.errors is None:
            self.errors = []


class RollbackManager:
    """
    Manages rollback operations with fine-grained control.
    
    This integrates with OperationHistory and CheckpointManager
    to provide comprehensive rollback capabilities.
    """
    
    def __init__(
        self,
        reverie_dir: Path,
        operation_history: Optional[OperationHistory] = None
    ):
        self.reverie_dir = reverie_dir
        self.checkpoint_manager = CheckpointManager(reverie_dir)
        self.operation_history = operation_history or OperationHistory("default")
        
        # Undo/redo stacks
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
        
        # Maximum stack size
        self.max_stack_size = 50
    
    def create_pre_question_checkpoint(
        self,
        session_id: str,
        messages: List[Dict],
        question: str
    ) -> str:
        """
        Create a checkpoint before processing a user question.
        
        Args:
            session_id: Current session ID
            messages: Current message history
            question: The user's question
        
        Returns:
            Checkpoint ID
        """
        checkpoint = self.checkpoint_manager.create_checkpoint(
            session_id=session_id,
            messages=messages,
            description=f"Before question: {question[:50]}..."
        )
        
        # Add to operation history
        self.operation_history.add_checkpoint(
            checkpoint_id=checkpoint.id,
            description=checkpoint.description,
            message_index=len(messages)
        )
        
        return checkpoint.id
    
    def create_pre_tool_checkpoint(
        self,
        session_id: str,
        messages: List[Dict],
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> str:
        """
        Create a checkpoint before executing a tool.
        
        Args:
            session_id: Current session ID
            messages: Current message history
            tool_name: Name of the tool
            arguments: Tool arguments
        
        Returns:
            Checkpoint ID
        """
        checkpoint = self.checkpoint_manager.create_checkpoint(
            session_id=session_id,
            messages=messages,
            description=f"Before tool: {tool_name}"
        )
        
        return checkpoint.id
    
    def rollback_to_previous_question(
        self,
        session_id: str
    ) -> RollbackResult:
        """
        Rollback to the state before the last user question.
        
        This will:
        1. Find the last user question operation
        2. Restore the checkpoint created before that question
        3. Restore all files modified since that checkpoint
        4. Restore message history
        
        Args:
            session_id: Current session ID
        
        Returns:
            RollbackResult with details
        """
        result = RollbackResult(success=False, message="")
        
        # Find the last user question
        last_question = self.operation_history.get_last_user_question()
        
        if not last_question:
            result.message = "No previous question found to rollback to."
            return result
        
        # Get the checkpoint ID
        checkpoint_id = last_question.checkpoint_id
        
        if not checkpoint_id:
            result.message = "No checkpoint found for the last question."
            return result
        
        # Restore checkpoint
        messages = self.checkpoint_manager.restore_checkpoint(checkpoint_id)
        
        if messages is None:
            result.message = f"Failed to restore checkpoint {checkpoint_id}"
            return result
        
        # Get operations since this checkpoint
        operations_since = self.operation_history.get_operations_since(last_question.id)
        
        # Restore files
        restored_files = []
        errors = []
        
        for op in operations_since:
            if op.file_operation:
                file_path = op.file_operation.file_path
                old_content = op.file_operation.old_content
                
                if old_content is not None:
                    try:
                        # Restore old content
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(old_content)
                        restored_files.append(file_path)
                    except Exception as e:
                        errors.append(f"Failed to restore {file_path}: {e}")
        
        # Save state for undo
        self._save_undo_state({
            'type': 'rollback_to_question',
            'checkpoint_id': checkpoint_id,
            'operations': [op.id for op in operations_since]
        })
        
        result.success = True
        result.message = f"Rolled back to question: {last_question.description}"
        result.restored_files = restored_files
        result.restored_messages = messages
        result.errors = errors
        
        return result
    
    def rollback_to_previous_tool_call(
        self,
        session_id: str
    ) -> RollbackResult:
        """
        Rollback to the state before the last tool call.
        
        This will:
        1. Find the last tool call operation
        2. Restore files modified by that tool call
        3. Remove the tool call from message history
        
        Args:
            session_id: Current session ID
        
        Returns:
            RollbackResult with details
        """
        result = RollbackResult(success=False, message="")
        
        # Find the last tool call
        last_tool = self.operation_history.get_last_tool_call()
        
        if not last_tool:
            result.message = "No previous tool call found to rollback to."
            return result
        
        # Get operations since this tool call
        operations_since = self.operation_history.get_operations_since(last_tool.id)
        
        # Restore files
        restored_files = []
        errors = []
        
        for op in operations_since:
            if op.file_operation:
                file_path = op.file_operation.file_path
                old_content = op.file_operation.old_content
                
                if old_content is not None:
                    try:
                        # Restore old content
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(old_content)
                        restored_files.append(file_path)
                    except Exception as e:
                        errors.append(f"Failed to restore {file_path}: {e}")
        
        # Save state for undo
        self._save_undo_state({
            'type': 'rollback_to_tool',
            'tool_id': last_tool.id,
            'operations': [op.id for op in operations_since]
        })
        
        result.success = True
        result.message = f"Rolled back to before tool call: {last_tool.description}"
        result.restored_files = restored_files
        result.errors = errors
        
        return result
    
    def rollback_to_checkpoint(
        self,
        checkpoint_id: str
    ) -> RollbackResult:
        """
        Rollback to a specific checkpoint.
        
        Args:
            checkpoint_id: ID of the checkpoint to rollback to
        
        Returns:
            RollbackResult with details
        """
        result = RollbackResult(success=False, message="")
        
        # Restore checkpoint
        messages = self.checkpoint_manager.restore_checkpoint(checkpoint_id)
        
        if messages is None:
            result.message = f"Failed to restore checkpoint {checkpoint_id}"
            return result
        
        # Find the checkpoint operation
        checkpoint_op = None
        for op in self.operation_history.operations:
            if op.checkpoint_id == checkpoint_id:
                checkpoint_op = op
                break
        
        if not checkpoint_op:
            result.message = f"Checkpoint {checkpoint_id} not found in operation history"
            return result
        
        # Get operations since this checkpoint
        operations_since = self.operation_history.get_operations_since(checkpoint_op.id)
        
        # Restore files
        restored_files = []
        errors = []
        
        for op in operations_since:
            if op.file_operation:
                file_path = op.file_operation.file_path
                old_content = op.file_operation.old_content
                
                if old_content is not None:
                    try:
                        # Restore old content
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(old_content)
                        restored_files.append(file_path)
                    except Exception as e:
                        errors.append(f"Failed to restore {file_path}: {e}")
        
        # Save state for undo
        self._save_undo_state({
            'type': 'rollback_to_checkpoint',
            'checkpoint_id': checkpoint_id,
            'operations': [op.id for op in operations_since]
        })
        
        result.success = True
        result.message = f"Rolled back to checkpoint: {checkpoint_op.description}"
        result.restored_files = restored_files
        result.restored_messages = messages
        result.errors = errors
        
        return result
    
    def undo(self) -> RollbackResult:
        """
        Undo the last rollback operation.
        
        Returns:
            RollbackResult with details
        """
        result = RollbackResult(success=False, message="")
        
        if not self.undo_stack:
            result.message = "Nothing to undo."
            return result
        
        # Pop from undo stack
        undo_state = self.undo_stack.pop()
        
        # Push to redo stack
        self.redo_stack.append(undo_state)
        
        # Limit redo stack size
        if len(self.redo_stack) > self.max_stack_size:
            self.redo_stack.pop(0)
        
        result.success = True
        result.message = "Undo operation completed."
        
        return result
    
    def redo(self) -> RollbackResult:
        """
        Redo the last undone rollback operation.
        
        Returns:
            RollbackResult with details
        """
        result = RollbackResult(success=False, message="")
        
        if not self.redo_stack:
            result.message = "Nothing to redo."
            return result
        
        # Pop from redo stack
        redo_state = self.redo_stack.pop()
        
        # Push to undo stack
        self.undo_stack.append(redo_state)
        
        # Limit undo stack size
        if len(self.undo_stack) > self.max_stack_size:
            self.undo_stack.pop(0)
        
        result.success = True
        result.message = "Redo operation completed."
        
        return result
    
    def get_available_rollback_points(self) -> List[Dict[str, Any]]:
        """
        Get a list of available rollback points.
        
        Returns:
            List of rollback points with descriptions
        """
        points = []
        
        # Get last user question
        last_question = self.operation_history.get_last_user_question()
        if last_question:
            points.append({
                'type': 'question',
                'id': last_question.id,
                'description': last_question.description,
                'timestamp': last_question.timestamp,
                'checkpoint_id': last_question.checkpoint_id
            })
        
        # Get last tool call
        last_tool = self.operation_history.get_last_tool_call()
        if last_tool:
            points.append({
                'type': 'tool',
                'id': last_tool.id,
                'description': last_tool.description,
                'timestamp': last_tool.timestamp
            })
        
        # Get recent checkpoints
        checkpoints = self.checkpoint_manager.list_checkpoints()
        for cp in checkpoints[:5]:  # Last 5 checkpoints
            points.append({
                'type': 'checkpoint',
                'id': cp.id,
                'description': cp.description,
                'timestamp': cp.created_at,
                'message_count': cp.message_count
            })
        
        return points
    
    def _save_undo_state(self, state: Dict[str, Any]) -> None:
        """Save state for undo"""
        self.undo_stack.append(state)
        
        # Limit stack size
        if len(self.undo_stack) > self.max_stack_size:
            self.undo_stack.pop(0)
        
        # Clear redo stack on new action
        self.redo_stack.clear()
    
    def can_undo(self) -> bool:
        """Check if undo is available"""
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Check if redo is available"""
        return len(self.redo_stack) > 0
    
    def get_operation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of operations in the history.
        
        Returns:
            Dictionary with operation statistics
        """
        total_ops = len(self.operation_history.operations)
        
        # Count by type
        type_counts = {}
        for op in self.operation_history.operations:
            op_type = op.operation_type.value
            type_counts[op_type] = type_counts.get(op_type, 0) + 1
        
        # Get file operations
        file_ops = [op for op in self.operation_history.operations 
                   if op.file_operation]
        
        modified_files = set()
        for op in file_ops:
            if op.file_operation:
                modified_files.add(op.file_operation.file_path)
        
        return {
            'total_operations': total_ops,
            'operation_counts': type_counts,
            'modified_files': list(modified_files),
            'can_undo': self.can_undo(),
            'can_redo': self.can_redo(),
            'undo_stack_size': len(self.undo_stack),
            'redo_stack_size': len(self.redo_stack)
        }