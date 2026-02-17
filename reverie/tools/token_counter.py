"""
Token Counter - Accurate token counting for context management

Provides accurate token counting using tiktoken library.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path

from .base import BaseTool, ToolResult


class TokenCounterTool(BaseTool):
    """Tool for counting tokens in messages and text"""
    
    name = "count_tokens"
    description = "Count tokens in text or current conversation"
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = context.get('project_root') if context else Path.cwd()
        self._tiktoken = None
        self._encoding = None
    
    def _get_encoding(self):
        """Lazy load tiktoken encoding"""
        if self._encoding is None:
            try:
                import tiktoken
                self._tiktoken = tiktoken
                # Use cl100k_base encoding (used by GPT-4, GPT-3.5-turbo, etc.)
                self._encoding = tiktoken.get_encoding("cl100k_base")
            except ImportError:
                # Fallback to estimation if tiktoken not available
                self._encoding = None
        return self._encoding
    
    def _estimate_tokens(self, text: str) -> int:
        """Fallback estimation when tiktoken is not available"""
        # Rough estimation: ~1 token per 4 characters for English text
        # This is a conservative estimate
        return len(text) // 4 + 1
    
    def _count_tokens_in_text(self, text: str) -> int:
        """Count tokens in a text string"""
        encoding = self._get_encoding()
        if encoding:
            return len(encoding.encode(text))
        else:
            return self._estimate_tokens(text)
    
    def _count_tokens_in_messages(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count tokens in a list of messages.
        
        Based on OpenAI's token counting methodology:
        https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
        """
        encoding = self._get_encoding()
        
        if not encoding:
            # Fallback estimation
            total = 0
            for message in messages:
                total += 4  # Every message has overhead
                for key, value in message.items():
                    if isinstance(value, str):
                        total += self._estimate_tokens(value)
                    elif isinstance(value, list):
                        # Handle tool_calls or other list fields
                        for item in value:
                            if isinstance(item, dict):
                                for k, v in item.items():
                                    if isinstance(v, str):
                                        total += self._estimate_tokens(v)
            return total
        
        # Accurate counting with tiktoken
        num_tokens = 0
        
        for message in messages:
            # Every message follows <im_start>{role/name}\n{content}<im_end>\n
            num_tokens += 4
            
            for key, value in message.items():
                if isinstance(value, str):
                    num_tokens += len(encoding.encode(value))
                elif isinstance(value, list):
                    # Handle tool_calls
                    for item in value:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                if isinstance(v, str):
                                    num_tokens += len(encoding.encode(v))
                                elif isinstance(v, dict):
                                    # Nested dict (e.g., function in tool_call)
                                    for kk, vv in v.items():
                                        if isinstance(vv, str):
                                            num_tokens += len(encoding.encode(vv))
                
                if key == "name":  # If there's a name, the role is omitted
                    num_tokens -= 1  # Role is always 1 token
        
        num_tokens += 2  # Every reply is primed with <im_start>assistant
        
        return num_tokens
    
    def get_spec(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "count_tokens",
                "description": "Count the number of tokens in text or messages. Use this to check context usage and manage token limits. Returns accurate token counts using tiktoken library.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to count tokens in (optional if checking current conversation)"
                        },
                        "check_current_conversation": {
                            "type": "boolean",
                            "description": "If true, count tokens in the current conversation messages"
                        }
                    },
                    "required": []
                }
            }
        }
    
    def execute(self, text: str = None, check_current_conversation: bool = False) -> ToolResult:
        """
        Count tokens in text or current conversation.
        
        Args:
            text: Optional text to count tokens in
            check_current_conversation: If True, count tokens in current conversation
            
        Returns:
            ToolResult with token count information
        """
        try:
            # Check if tiktoken is available
            encoding = self._get_encoding()
            method = "tiktoken (accurate)" if encoding else "estimation (approximate)"
            
            output_lines = []
            
            # Count tokens in provided text
            if text:
                token_count = self._count_tokens_in_text(text)
                output_lines.append(f"Token count for provided text: {token_count:,}")
                output_lines.append(f"Method: {method}")
                output_lines.append(f"Text length: {len(text):,} characters")
            
            # Count tokens in current conversation
            if check_current_conversation:
                agent = self.context.get('agent')
                if agent and hasattr(agent, 'messages'):
                    messages = agent.messages
                    system_prompt = agent.system_prompt
                    
                    # Count system prompt
                    system_tokens = self._count_tokens_in_text(system_prompt)
                    
                    # Count messages
                    messages_tokens = self._count_tokens_in_messages(messages)
                    
                    # Total
                    total_tokens = system_tokens + messages_tokens
                    
                    # Get max context from config
                    max_tokens = 128000  # Default
                    config_manager = self.context.get('config_manager')
                    if config_manager:
                        model_config = config_manager.get_active_model()
                        if model_config and model_config.max_context_tokens:
                            max_tokens = model_config.max_context_tokens
                    
                    # Calculate percentage
                    percentage = (total_tokens / max_tokens) * 100
                    
                    output_lines.append("")
                    output_lines.append("Current Conversation Token Usage:")
                    output_lines.append(f"  System prompt: {system_tokens:,} tokens")
                    output_lines.append(f"  Messages: {messages_tokens:,} tokens ({len(messages)} messages)")
                    output_lines.append(f"  Total: {total_tokens:,} tokens")
                    output_lines.append(f"  Max context: {max_tokens:,} tokens")
                    output_lines.append(f"  Usage: {percentage:.1f}%")
                    output_lines.append(f"  Method: {method}")
                    
                    # Warning if approaching limit
                    if percentage >= 80:
                        output_lines.append("")
                        output_lines.append("⚠️  WARNING: Context usage is high (>80%)")
                        output_lines.append("Consider using context compression or starting a new conversation.")
                    elif percentage >= 60:
                        output_lines.append("")
                        output_lines.append("ℹ️  INFO: Context usage is moderate (>60%)")
                        output_lines.append("You may want to consider context management soon.")
                    
                    metadata = {
                        "system_tokens": system_tokens,
                        "messages_tokens": messages_tokens,
                        "total_tokens": total_tokens,
                        "max_tokens": max_tokens,
                        "percentage": percentage,
                        "message_count": len(messages)
                    }
                else:
                    output_lines.append("No active conversation found.")
                    metadata = {}
            else:
                metadata = {}
            
            if not output_lines:
                output_lines.append("No text provided and check_current_conversation not enabled.")
                output_lines.append("Usage: count_tokens(text='...') or count_tokens(check_current_conversation=True)")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data=metadata
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to count tokens: {str(e)}"
            )
    
    def get_execution_message(self, text: str = None, check_current_conversation: bool = False) -> str:
        """Get message to display when tool is being executed"""
        if check_current_conversation:
            return "Counting tokens in current conversation"
        elif text:
            return f"Counting tokens in text ({len(text)} characters)"
        return "Counting tokens"
