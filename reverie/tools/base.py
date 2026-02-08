"""
Base Tool - Abstract base class for all tools

All tools must implement this interface to be callable by the AI Agent.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum


class ToolResultStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


@dataclass
class ToolResult:
    """Result of a tool execution"""
    success: bool
    output: str
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    
    @classmethod
    def ok(cls, output: str, data: Optional[Dict] = None) -> 'ToolResult':
        return cls(
            success=True,
            output=output,
            data=data or {},
            status=ToolResultStatus.SUCCESS
        )
    
    @classmethod
    def fail(cls, error: str) -> 'ToolResult':
        return cls(
            success=False,
            output="",
            error=error,
            status=ToolResultStatus.ERROR
        )
    
    @classmethod
    def partial(cls, output: str, error: str) -> 'ToolResult':
        return cls(
            success=True,
            output=output,
            error=error,
            status=ToolResultStatus.PARTIAL
        )


class BaseTool(ABC):
    """
    Abstract base class for tools.
    
    Each tool must define:
    - name: Unique identifier
    - description: What the tool does (shown to model)
    - parameters: JSON schema for parameters
    - execute: The actual implementation
    """
    
    # Must be overridden in subclasses
    name: str = "base_tool"
    description: str = "Base tool description"
    
    # Parameter schema in JSON Schema format
    parameters: Dict = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def __init__(self, context: Optional[Dict] = None):
        """
        Initialize tool with optional context.
        
        Context can include:
        - project_root: Path to project
        - context_engine: Reference to Context Engine
        - config: Configuration dict
        """
        self.context = context or {}
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given parameters.
        
        Args:
            **kwargs: Parameters as defined in the parameters schema
        
        Returns:
            ToolResult with success status and output
        """
        pass
    
    def validate_params(self, params: Dict) -> Optional[str]:
        """
        Validate parameters against schema.
        
        Returns error message if invalid, None if valid.
        """
        required = self.parameters.get('required', [])
        properties = self.parameters.get('properties', {})
        
        # Check required parameters
        for req in required:
            if req not in params:
                return f"Missing required parameter: {req}"
        
        # Type checking (basic)
        for key, value in params.items():
            if key in properties:
                expected_type = properties[key].get('type')
                if expected_type == 'string' and not isinstance(value, str):
                    return f"Parameter {key} must be a string"
                elif expected_type == 'integer' and not isinstance(value, int):
                    return f"Parameter {key} must be an integer"
                elif expected_type == 'boolean' and not isinstance(value, bool):
                    return f"Parameter {key} must be a boolean"
                elif expected_type == 'array' and not isinstance(value, list):
                    return f"Parameter {key} must be an array"
        
        return None
    
    def get_schema(self) -> Dict:
        """
        Get tool schema for OpenAI format.
        
        This method ensures that the schema is properly formatted and
        all strings are safe for JSON serialization.
        """
        # Validate that the schema can be serialized
        try:
            import json
            schema = {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters
                }
            }
            # Test serialization
            json.dumps(schema, ensure_ascii=False)
            return schema
        except (TypeError, ValueError) as e:
            # If serialization fails, try to fix the description
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Tool schema serialization failed for {self.name}: {e}")
            
            # Create a safer schema with minimal description
            safe_schema = {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description.split('\n')[0] if self.description else self.name,  # Use first line only
                    "parameters": self.parameters
                }
            }
            
            # Test again
            try:
                json.dumps(safe_schema, ensure_ascii=False)
                return safe_schema
            except (TypeError, ValueError) as e2:
                logger.error(f"Failed to create safe schema for {self.name}: {e2}")
                # Return minimal schema
                return {
                    "type": "function",
                    "function": {
                        "name": self.name,
                        "description": self.name,
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                }
    
    def get_execution_message(self, **kwargs) -> str:
        """
        Return a human-readable English description of what the tool is about to do.
        
        Args:
            **kwargs: Parameters passed to the tool
            
        Returns:
            A concise, human-readable string.
        """
        return f"Executing {self.name}..."

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
