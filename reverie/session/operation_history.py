"""
Operation History - Track all operations for rollback support

This module provides a comprehensive operation history system that tracks:
- User questions/prompts
- Tool calls
- File modifications
- Session state changes

This enables fine-grained rollback to any point in the session.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import uuid


class OperationType(Enum):
    """Types of operations that can be tracked"""
    USER_QUESTION = "user_question"
    TOOL_CALL = "tool_call"
    FILE_MODIFICATION = "file_modification"
    FILE_CREATION = "file_creation"
    FILE_DELETION = "file_deletion"
    SESSION_STATE = "session_state"
    CHECKPOINT = "checkpoint"


@dataclass
class FileOperation:
    """Details of a file operation"""
    file_path: str
    operation: str  # 'modify', 'create', 'delete'
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    line_changes: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> dict:
        return {
            'file_path': self.file_path,
            'operation': self.operation,
            'old_content': self.old_content,
            'new_content': self.new_content,
            'line_changes': self.line_changes
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileOperation':
        return cls(
            file_path=data['file_path'],
            operation=data['operation'],
            old_content=data.get('old_content'),
            new_content=data.get('new_content'),
            line_changes=data.get('line_changes')
        )


@dataclass
class ToolCallOperation:
    """Details of a tool call"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'tool_name': self.tool_name,
            'arguments': self.arguments,
            'result': self.result,
            'success': self.success,
            'error': self.error
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ToolCallOperation':
        return cls(
            tool_name=data['tool_name'],
            arguments=data['arguments'],
            result=data.get('result'),
            success=data.get('success', True),
            error=data.get('error')
        )


@dataclass
class Operation:
    """A single operation in the history"""
    id: str
    operation_type: OperationType
    timestamp: str
    description: str
    
    # Optional details based on operation type
    user_question: Optional[str] = None
    tool_call: Optional[ToolCallOperation] = None
    file_operation: Optional[FileOperation] = None
    session_state: Optional[Dict[str, Any]] = None
    checkpoint_id: Optional[str] = None
    
    # Message index (for rollback to specific message)
    message_index: int = -1
    
    # Parent operation (for nested operations like tool calls within a question)
    parent_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'operation_type': self.operation_type.value,
            'timestamp': self.timestamp,
            'description': self.description,
            'user_question': self.user_question,
            'tool_call': self.tool_call.to_dict() if self.tool_call else None,
            'file_operation': self.file_operation.to_dict() if self.file_operation else None,
            'session_state': self.session_state,
            'checkpoint_id': self.checkpoint_id,
            'message_index': self.message_index,
            'parent_id': self.parent_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Operation':
        return cls(
            id=data['id'],
            operation_type=OperationType(data['operation_type']),
            timestamp=data['timestamp'],
            description=data['description'],
            user_question=data.get('user_question'),
            tool_call=ToolCallOperation.from_dict(data['tool_call']) if data.get('tool_call') else None,
            file_operation=FileOperation.from_dict(data['file_operation']) if data.get('file_operation') else None,
            session_state=data.get('session_state'),
            checkpoint_id=data.get('checkpoint_id'),
            message_index=data.get('message_index', -1),
            parent_id=data.get('parent_id')
        )


class OperationHistory:
    """
    Manages the operation history for a session.
    
    This tracks all operations and provides rollback capabilities.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.operations: List[Operation] = []
        self.current_index = -1  # Current position in history
    
    def add_user_question(
        self,
        question: str,
        message_index: int,
        checkpoint_id: Optional[str] = None
    ) -> Operation:
        """
        Add a user question to the history.
        
        Args:
            question: The user's question/prompt
            message_index: Index in the message history
            checkpoint_id: Optional checkpoint ID created before this question
        
        Returns:
            The created operation
        """
        operation = Operation(
            id=str(uuid.uuid4())[:8],
            operation_type=OperationType.USER_QUESTION,
            timestamp=datetime.now().isoformat(),
            description=f"User question: {question[:50]}{'...' if len(question) > 50 else ''}",
            user_question=question,
            message_index=message_index,
            checkpoint_id=checkpoint_id
        )
        
        self.operations.append(operation)
        self.current_index = len(self.operations) - 1
        return operation
    
    def add_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Optional[str],
        success: bool,
        error: Optional[str],
        parent_id: Optional[str] = None
    ) -> Operation:
        """
        Add a tool call to the history.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            result: Tool result
            success: Whether the tool call succeeded
            error: Error message if failed
            parent_id: ID of the parent operation (e.g., user question)
        
        Returns:
            The created operation
        """
        tool_call = ToolCallOperation(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            error=error
        )
        
        operation = Operation(
            id=str(uuid.uuid4())[:8],
            operation_type=OperationType.TOOL_CALL,
            timestamp=datetime.now().isoformat(),
            description=f"Tool call: {tool_name}",
            tool_call=tool_call,
            parent_id=parent_id
        )
        
        self.operations.append(operation)
        self.current_index = len(self.operations) - 1
        return operation
    
    def add_file_operation(
        self,
        file_path: str,
        operation: str,
        old_content: Optional[str],
        new_content: Optional[str],
        parent_id: Optional[str] = None
    ) -> Operation:
        """
        Add a file operation to the history.
        
        Args:
            file_path: Path to the file
            operation: Type of operation ('modify', 'create', 'delete')
            old_content: Old file content (for modifications)
            new_content: New file content
            parent_id: ID of the parent operation (e.g., tool call)
        
        Returns:
            The created operation
        """
        file_op = FileOperation(
            file_path=file_path,
            operation=operation,
            old_content=old_content,
            new_content=new_content
        )
        
        operation = Operation(
            id=str(uuid.uuid4())[:8],
            operation_type=OperationType.FILE_MODIFICATION,
            timestamp=datetime.now().isoformat(),
            description=f"File {operation}: {file_path}",
            file_operation=file_op,
            parent_id=parent_id
        )
        
        self.operations.append(operation)
        self.current_index = len(self.operations) - 1
        return operation
    
    def add_checkpoint(
        self,
        checkpoint_id: str,
        description: str,
        message_index: int
    ) -> Operation:
        """
        Add a checkpoint to the history.
        
        Args:
            checkpoint_id: ID of the checkpoint
            description: Checkpoint description
            message_index: Index in the message history
        
        Returns:
            The created operation
        """
        operation = Operation(
            id=str(uuid.uuid4())[:8],
            operation_type=OperationType.CHECKPOINT,
            timestamp=datetime.now().isoformat(),
            description=description,
            checkpoint_id=checkpoint_id,
            message_index=message_index
        )
        
        self.operations.append(operation)
        self.current_index = len(self.operations) - 1
        return operation
    
    def get_operations(
        self,
        operation_type: Optional[OperationType] = None,
        limit: Optional[int] = None
    ) -> List[Operation]:
        """
        Get operations from history.
        
        Args:
            operation_type: Filter by operation type
            limit: Maximum number of operations to return
        
        Returns:
            List of operations
        """
        ops = self.operations
        
        if operation_type:
            ops = [op for op in ops if op.operation_type == operation_type]
        
        if limit:
            ops = ops[-limit:]
        
        return ops
    
    def get_operation(self, operation_id: str) -> Optional[Operation]:
        """Get an operation by ID"""
        for op in self.operations:
            if op.id == operation_id:
                return op
        return None
    
    def get_last_user_question(self) -> Optional[Operation]:
        """Get the last user question operation"""
        for op in reversed(self.operations):
            if op.operation_type == OperationType.USER_QUESTION:
                return op
        return None
    
    def get_last_tool_call(self) -> Optional[Operation]:
        """Get the last tool call operation"""
        for op in reversed(self.operations):
            if op.operation_type == OperationType.TOOL_CALL:
                return op
        return None
    
    def get_operations_since(self, operation_id: str) -> List[Operation]:
        """
        Get all operations after a specific operation.
        
        Args:
            operation_id: ID of the operation to start from
        
        Returns:
            List of operations after the specified one
        """
        found = False
        result = []
        
        for op in self.operations:
            if found:
                result.append(op)
            elif op.id == operation_id:
                found = True
        
        return result
    
    def get_rollback_point(self, target_type: str) -> Optional[Operation]:
        """
        Find the best rollback point based on target type.
        
        Args:
            target_type: 'question' or 'tool'
        
        Returns:
            The operation to rollback to, or None if not found
        """
        if target_type == 'question':
            # Find the last user question
            return self.get_last_user_question()
        elif target_type == 'tool':
            # Find the last tool call
            return self.get_last_tool_call()
        return None
    
    def clear(self) -> None:
        """Clear all operations"""
        self.operations.clear()
        self.current_index = -1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'session_id': self.session_id,
            'operations': [op.to_dict() for op in self.operations],
            'current_index': self.current_index
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'OperationHistory':
        """Create from dictionary"""
        history = cls(data['session_id'])
        history.operations = [Operation.from_dict(op) for op in data.get('operations', [])]
        history.current_index = data.get('current_index', -1)
        return history
    
    def save(self, file_path: Path) -> None:
        """Save to file"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, file_path: Path) -> Optional['OperationHistory']:
        """Load from file"""
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return None