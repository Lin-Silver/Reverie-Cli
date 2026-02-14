"""
Reverie Agent - The AI core

This is the main agent class that:
- Manages conversation with the LLM
- Handles tool calls
- Integrates with Context Engine
- Supports both streaming and non-streaming modes
"""

from typing import List, Dict, Any, Optional, Generator, AsyncGenerator
from pathlib import Path
import json
import time
import re
import logging
import uuid
import hmac
import hashlib

from rich.markup import escape as rich_escape

from .system_prompt import build_system_prompt
from .tool_executor import ToolExecutor
from ..tools.base import ToolResult

# Special marker for thinking content (used in streaming)
# This allows the interface to identify and style thinking content differently
THINKING_START_MARKER = "[[THINKING_START]]"
THINKING_END_MARKER = "[[THINKING_END]]"

# Configure logging for debugging
logger = logging.getLogger(__name__)


def validate_and_sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize the API request payload to prevent JSON serialization errors.
    
    This function:
    - Ensures all strings are properly escaped
    - Validates that all values are JSON-serializable
    - Removes or fixes problematic characters
    - Logs any issues found
    
    Args:
        payload: The payload dictionary to validate
        
    Returns:
        A sanitized payload dictionary
        
    Raises:
        ValueError: If the payload cannot be sanitized
    """
    def sanitize_value(value: Any, path: str = "") -> Any:
        """Recursively sanitize a value"""
        if value is None:
            return None
        
        elif isinstance(value, (str, int, float, bool)):
            if isinstance(value, str):
                # Check for unescaped quotes that might break JSON
                # Count quotes to detect potential issues
                quote_count = value.count('"')
                if quote_count % 2 != 0:
                    logger.warning(f"Unbalanced quotes in {path}: {value[:100]}...")
                # Ensure the string doesn't contain control characters
                try:
                    # Test if it can be JSON-encoded
                    json.dumps(value)
                except (TypeError, ValueError) as e:
                    logger.error(f"Failed to encode string at {path}: {e}")
                    # Try to fix by removing problematic characters
                    value = ''.join(char for char in value if ord(char) >= 32 or char in '\n\r\t')
            return value
        
        elif isinstance(value, dict):
            return {k: sanitize_value(v, f"{path}.{k}") for k, v in value.items()}
        
        elif isinstance(value, list):
            return [sanitize_value(item, f"{path}[{i}]") for i, item in enumerate(value)]
        
        else:
            raise ValueError(f"Unsupported type at {path}: {type(value)}")
    
    try:
        # Validate the payload structure
        if not isinstance(payload, dict):
            raise ValueError(f"Payload must be a dict, got {type(payload)}")
        
        # Sanitize the payload
        sanitized = sanitize_value(payload, "payload")
        
        # Test JSON serialization
        try:
            json_str = json.dumps(sanitized, ensure_ascii=False)
            # Verify it can be parsed back
            json.loads(json_str)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization failed: {e}")
            logger.error(f"Payload preview: {str(payload)[:500]}")
            raise ValueError(f"Payload cannot be serialized to JSON: {e}")
        
        return sanitized
    
    except Exception as e:
        logger.error(f"Payload validation failed: {e}")
        raise


def make_api_request_with_retry(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    stream: bool = False,
    timeout: int = 60
) -> Any:
    """
    Make an API request with retry logic and exponential backoff.
    
    Args:
        url: The API endpoint URL
        headers: Request headers
        payload: Request payload (will be validated and sanitized)
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial backoff time in seconds
        stream: Whether to stream the response
        timeout: Request timeout in seconds
        
    Returns:
        The response object
        
    Raises:
        requests.RequestException: If all retries fail
    """
    import requests
    
    # Validate and sanitize payload
    try:
        sanitized_payload = validate_and_sanitize_payload(payload)
    except ValueError as e:
        logger.error(f"Payload validation failed before request: {e}")
        raise
    
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.debug(f"API request attempt {attempt + 1}/{max_retries}")
            
            response = requests.post(
                url,
                headers=headers,
                json=sanitized_payload,
                stream=stream,
                timeout=timeout
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Success - return response
            logger.debug(f"API request succeeded on attempt {attempt + 1}")
            return response
            
        except requests.exceptions.HTTPError as e:
            last_error = e
            status_code = e.response.status_code if e.response is not None else "unknown"
            
            # Don't retry on client errors (4xx) except 429 (rate limit)
            if isinstance(status_code, int) and 400 <= status_code < 500 and status_code != 429:
                logger.error(f"Client error {status_code}, not retrying: {e}")
                # Try to get more details from the response
                if e.response is not None:
                    try:
                        error_detail = e.response.json()
                        logger.error(f"Error details: {error_detail}")
                    except:
                        logger.error(f"Error response: {e.response.text[:500]}")
                raise
            
            # Retry on server errors (5xx) and rate limit (429)
            logger.warning(f"HTTP error {status_code} on attempt {attempt + 1}: {e}")
            
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Request exception on attempt {attempt + 1}: {e}")
        
        # Exponential backoff
        if attempt < max_retries - 1:
            backoff = initial_backoff * (2 ** attempt)
            logger.debug(f"Waiting {backoff}s before retry...")
            time.sleep(backoff)
    
    # All retries failed
    logger.error(f"All {max_retries} retry attempts failed")
    raise last_error or requests.RequestException("All retry attempts failed")


class ReverieAgent:
    """
    The Reverie AI Agent.
    
    Uses OpenAI SDK for API interaction and integrates deeply
    with the Context Engine for reduced hallucinations.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        model_display_name: Optional[str] = None,
        project_root: Optional[Path] = None,
        retriever=None,
        indexer=None,
        git_integration=None,
        additional_rules: str = "",
        mode: str = "reverie",
        provider: str = "openai-sdk",
        thinking_mode: Optional[str] = None,
        operation_history=None,
        rollback_manager=None,
        config=None
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.model_display_name = model_display_name or model
        self.project_root = project_root or Path.cwd()
        self.additional_rules = additional_rules
        self.additional_rules = additional_rules
        self.mode = mode
        self.ant_phase = "PLANNING"
        self.provider = provider
        self.thinking_mode = thinking_mode
        
        # API configuration for stability
        self.api_max_retries = 3
        self.api_initial_backoff = 1.0
        self.api_timeout = 60
        self.api_enable_debug_logging = False
        
        if config:
            self.api_max_retries = getattr(config, 'api_max_retries', 3)
            self.api_initial_backoff = getattr(config, 'api_initial_backoff', 1.0)
            self.api_timeout = getattr(config, 'api_timeout', 60)
            self.api_enable_debug_logging = getattr(config, 'api_enable_debug_logging', False)
        
        # Configure logging level based on config
        if self.api_enable_debug_logging:
            logging.getLogger(__name__).setLevel(logging.DEBUG)
        else:
            logging.getLogger(__name__).setLevel(logging.WARNING)
        
        # Initialize client based on provider
        self._client = None
        self._init_client()
        
        # Initialize tool executor
        self.tool_executor = ToolExecutor(
            project_root=self.project_root,
            retriever=retriever,
            indexer=indexer,
            git_integration=git_integration
        )
        # Inject agent instance into tool context
        self.tool_executor.update_context('agent', self)
        
        # Conversation history
        self.messages: List[Dict] = []
        
        # Operation history and rollback support
        self.operation_history = operation_history
        self.rollback_manager = rollback_manager
        self.current_checkpoint_id: Optional[str] = None
        
        self.system_prompt = build_system_prompt(
            model_name=self.model_display_name,
            additional_rules=additional_rules,
            mode=self.mode,
            ant_phase=self.ant_phase
        )

    def set_ant_phase(self, phase: str) -> None:
        """Update Antigravity phase (PLANNING/EXECUTION)"""
        if phase in ["PLANNING", "EXECUTION", "VERIFICATION"]:
            # Verification shares EXECUTION prompt but might have minor differences in future
            # For now mapping VERIFICATION to EXECUTION for prompt logic if needed,
            # or just keeping the phase state for the tool.
            # System prompt only distinguishes PLANNING vs EXECUTION.
            self.ant_phase = phase
            
            # Map VERIFICATION to EXECUTION for prompt selection if strictly binary
            prompt_phase = "EXECUTION" if phase in ["EXECUTION", "VERIFICATION"] else "PLANNING"
            
            self.system_prompt = build_system_prompt(
                model_name=self.model_display_name,
                additional_rules=self.additional_rules,
                mode=self.mode,
                ant_phase=prompt_phase
            )

    def _check_tool_side_effects(self, tool_name: str, args: Dict[str, Any]) -> None:
        """Check for tools that modify agent state"""
        if tool_name == "task_boundary":
            mode = args.get("Mode")
            if mode and mode in ["PLANNING", "EXECUTION", "VERIFICATION"]:
                if mode != self.ant_phase:
                    self.set_ant_phase(mode)

    def update_mode(self, mode: str) -> None:
        """Update the agent's mode and rebuild the system prompt"""
        self.mode = mode
        self.ant_phase = "PLANNING" # Reset phase on mode switch
        self.system_prompt = build_system_prompt(
            model_name=self.model_display_name,
            additional_rules=self.additional_rules,
            mode=self.mode,
            ant_phase=self.ant_phase
        )
    
    def _init_client(self) -> None:
        """Initialize client based on provider"""
        if self.provider == "openai-sdk":
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key
                )
            except ImportError:
                raise ImportError(
                    "OpenAI SDK not installed. Run: pip install openai"
                )
        elif self.provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self.api_key,
                    base_url=self.base_url if self.base_url else None
                )
            except ImportError:
                raise ImportError(
                    "Anthropic SDK not installed. Run: pip install anthropic"
                )
        elif self.provider == "request":
            # For request provider, we don't need a client object
            # We'll use requests library directly
            self._client = None
        else:
            raise ValueError(
                f"Unknown provider: {self.provider}. "
                f"Supported providers: openai-sdk, request, anthropic"
            )

    def _is_iflow_direct_request(self) -> bool:
        """Whether current request-provider config targets iFlow direct API."""
        if self.provider != "request":
            return False
        base_url = str(self.base_url or "").strip().lower()
        return "apis.iflow.cn" in base_url and "/v1/chat/completions" in base_url

    def _refresh_iflow_api_key_from_local_cache(self) -> None:
        """Refresh iFlow API key from local CLI cache when needed."""
        if self.api_key:
            return
        
        # Direct implementation matching proxy.py's get_iflow_key function
        import os
        import json
        
        IFLOW_ACCOUNTS_FILE = os.path.expanduser("~/.iflow/iflow_accounts.json")
        IFLOW_OAUTH_FILE = os.path.expanduser("~/.iflow/oauth_creds.json")
        
        # Priority 1: ~/.iflow/iflow_accounts.json
        if os.path.exists(IFLOW_ACCOUNTS_FILE):
            try:
                with open(IFLOW_ACCOUNTS_FILE, 'r') as f:
                    data = json.load(f)
                    if data.get("iflowApiKey"):
                        self.api_key = data.get("iflowApiKey")
                        return
            except Exception as e:
                logger.error(f"Error reading iflow_accounts.json: {e}")

        # Priority 2: ~/.iflow/oauth_creds.json
        if os.path.exists(IFLOW_OAUTH_FILE):
            try:
                with open(IFLOW_OAUTH_FILE, 'r') as f:
                    data = json.load(f)
                    if data.get("apiKey"):
                        self.api_key = data.get("apiKey")
                        return
            except Exception as e:
                logger.error(f"Error reading oauth_creds.json: {e}")

    def _generate_iflow_signature(self, api_key: str, user_agent: str, session_id: str, timestamp_ms: int) -> str:
        # Exact copy of proxy.py's generate_signature function
        payload = f"{user_agent}:{session_id}:{timestamp_ms}"
        h = hmac.new(api_key.encode(), payload.encode(), hashlib.sha256)
        return h.hexdigest()

    def _build_request_headers(self, stream: bool) -> Dict[str, str]:
        """Build HTTP headers for request provider (generic + iFlow direct mode)."""
        if not self._is_iflow_direct_request():
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            if stream:
                headers["Accept"] = "text/event-stream"
            return headers

        self._refresh_iflow_api_key_from_local_cache()
        if not self.api_key:
            raise ValueError(
                "iFlow CLI credentials were not found. Please login with iFlow CLI and run /iflow."
            )

        # Use the exact same approach as proxy.py
        user_agent = "iFlow-Cli"
        session_id = f"session-{uuid.uuid4()}"
        timestamp = int(time.time() * 1000)  # Use same variable name as proxy.py
        signature = self._generate_iflow_signature(
            api_key=self.api_key,
            user_agent=user_agent,
            session_id=session_id,
            timestamp_ms=timestamp  # Pass timestamp directly
        )

        # Headers exactly matching proxy.py
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
            "session-id": session_id,
            "x-iflow-timestamp": str(timestamp),
            "x-iflow-signature": signature,
            "Accept": "text/event-stream" if stream else "application/json",
        }

    def _apply_iflow_model_suffix_logic(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mirror iflow-proxy model suffix logic:
        - model(depth) -> model + thinking toggles
        - minimax family uses reasoning_split
        """
        model_name = str(payload.get("model", "")).strip()
        if "(" not in model_name or ")" not in model_name:
            return payload

        base_model = model_name.split("(", 1)[0].strip()
        suffix = model_name.split("(", 1)[1].split(")", 1)[0].strip().lower()
        if not base_model:
            return payload

        thinking_suffixes = {"auto", "low", "medium", "high", "xhigh", "minimal"}
        if suffix in thinking_suffixes or suffix.isdigit():
            payload["model"] = base_model
            is_glm = "glm" in base_model.lower()
            is_minimax = "minimax" in base_model.lower()

            if is_minimax:
                payload["reasoning_split"] = True
            else:
                chat_kwargs = payload.get("chat_template_kwargs")
                if not isinstance(chat_kwargs, dict):
                    chat_kwargs = {}
                    payload["chat_template_kwargs"] = chat_kwargs
                chat_kwargs["enable_thinking"] = True
                if is_glm:
                    chat_kwargs["clear_thinking"] = False
        elif suffix in {"none", "0"}:
            payload["model"] = base_model
            chat_kwargs = payload.get("chat_template_kwargs")
            if isinstance(chat_kwargs, dict):
                chat_kwargs["enable_thinking"] = False

        return payload

    def _prepare_request_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare request-provider payload for generic API or iFlow direct API."""
        prepared = dict(payload)

        if self._is_iflow_direct_request():
            return self._apply_iflow_model_suffix_logic(prepared)

        if self.thinking_mode and self.thinking_mode.lower() in ["true", "false"]:
            chat_kwargs = prepared.get("chat_template_kwargs")
            if not isinstance(chat_kwargs, dict):
                chat_kwargs = {}
                prepared["chat_template_kwargs"] = chat_kwargs
            chat_kwargs["thinking"] = self.thinking_mode.lower() == "true"

        return prepared
    
    def set_context_engine(self, retriever, indexer, git_integration) -> None:
        """Update Context Engine references"""
        self.tool_executor = ToolExecutor(
            project_root=self.project_root,
            retriever=retriever,
            indexer=indexer,
            git_integration=git_integration
        )
    
    def _build_messages(self) -> List[Dict]:
        """Build message list for API call"""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.messages)
        return messages
    
    def process_message(
        self,
        user_message: str,
        stream: bool = True,
        session_id: str = "default"
    ) -> Generator[str, None, None]:
        """
        Process a user message and yield responses.
        
        Args:
            user_message: The user's input
            stream: Whether to stream the response
            session_id: Current session ID for checkpointing
        
        Yields:
            Response chunks (or full response if not streaming)
        """
        # Create checkpoint before processing user question
        if self.rollback_manager:
            self.current_checkpoint_id = self.rollback_manager.create_pre_question_checkpoint(
                session_id=session_id,
                messages=self.messages,
                question=user_message
            )
        
        # Add user message to history
        self.messages.append({
            "role": "user",
            "content": user_message
        })
        
        # Record user question in operation history
        if self.operation_history:
            self.operation_history.add_user_question(
                question=user_message,
                message_index=len(self.messages) - 1,
                checkpoint_id=self.current_checkpoint_id
            )
        
        # Check for context threshold (60%) and trigger compression if needed
        self._check_and_compress_context()
        
        # Call model with tools
        try:
            if stream:
                yield from self._process_streaming(session_id=session_id)
            else:
                response = self._process_non_streaming(session_id=session_id)
                yield response
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            yield error_msg
    
    def _process_streaming(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response"""
        if self.provider == "openai-sdk":
            yield from self._process_streaming_openai_sdk(session_id=session_id)
        elif self.provider == "request":
            yield from self._process_streaming_request(session_id=session_id)
        elif self.provider == "anthropic":
            yield from self._process_streaming_anthropic(session_id=session_id)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _process_streaming_openai_sdk(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response using OpenAI SDK"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        max_continuations = 3  # Safety limit to prevent infinite loops
        continuation_count = 0
        
        while True:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                stream=True
            )
            
            # Collect streamed response
            collected_content = ""
            collected_thinking = ""  # Collect thinking/reasoning content
            collected_tool_calls = []
            finish_reason = None
            
            # Flag to track if we're in thinking mode
            thinking_started = False
            
            # Buffer for handling split tokens (to hide //END//)
            stream_buffer = ""
            token_to_hide = "//END//"
            
            for chunk in response:
                choice = chunk.choices[0] if chunk.choices else None
                
                if choice is None:
                    continue
                
                # Track finish reason
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                
                delta = choice.delta
                if delta is None:
                    continue
                
                # Handle reasoning/thinking content FIRST (for thinking models like o1, DeepSeek-R1, etc.)
                # Check for reasoning_content in delta (OpenAI o1 / DeepSeek style)
                reasoning_content = None
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    reasoning_content = delta.reasoning_content
                elif hasattr(delta, 'thinking') and delta.thinking:
                    # Alternative field name used by some providers
                    reasoning_content = delta.thinking
                
                if reasoning_content:
                    collected_thinking += reasoning_content
                    # Emit thinking content with special markers for the interface
                    if not thinking_started:
                        yield THINKING_START_MARKER
                        thinking_started = True
                    yield reasoning_content
                
                # Content streaming - yield with buffering
                # If we were in thinking mode and now receiving regular content, end thinking first
                if delta.content:
                    # Check if we need to transition from thinking mode to regular content
                    if thinking_started:
                        yield THINKING_END_MARKER
                        thinking_started = False  # Reset so we don't emit again
                    
                    content_piece = delta.content
                    collected_content += content_piece
                    stream_buffer += content_piece
                    
                    if token_to_hide in stream_buffer:
                        # Found the token - split and yield parts
                        parts = stream_buffer.split(token_to_hide)
                        
                        # Yield everything before the first occurrence
                        if parts[0]:
                            yield parts[0]
                        
                        # We suppress the token itself.
                        # Handle text after the token (if any)
                        # Reconstruct remaining text without the token
                        remaining = "".join(parts[1:])
                        stream_buffer = remaining
                        
                    # Check for partial match at the end of buffer to prevent yielding partial token
                    partial_match_len = 0
                    for i in range(1, len(token_to_hide)):
                        if len(stream_buffer) >= i:
                            suffix = stream_buffer[-i:]
                            if token_to_hide.startswith(suffix):
                                partial_match_len = i
                    
                    if partial_match_len > 0:
                        # Yield safe part
                        to_yield = stream_buffer[:-partial_match_len]
                        stream_buffer = stream_buffer[-partial_match_len:]
                        if to_yield:
                            yield to_yield
                    else:
                        # No partial match, yield everything
                        yield stream_buffer
                        stream_buffer = ""
                
                # Tool call streaming
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        if tool_call.index >= len(collected_tool_calls):
                            collected_tool_calls.append({
                                "id": tool_call.id or "",
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name or "" if tool_call.function else "",
                                    "arguments": ""
                                }
                            })
                        
                        if tool_call.function:
                            if tool_call.function.name:
                                collected_tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                            if tool_call.function.arguments:
                                collected_tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                        if tool_call.id:
                            collected_tool_calls[tool_call.index]["id"] = tool_call.id
            
            # If thinking was streamed, emit end marker
            if thinking_started:
                yield THINKING_END_MARKER
            
            # Flush any remaining buffer that isn't the hidden token
            if stream_buffer and token_to_hide not in stream_buffer:
                yield stream_buffer
            
            # Check for tool calls
            if collected_tool_calls:
                # Add assistant message with tool calls
                assistant_message = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                # Execute tools
                for tool_call in collected_tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    
                    # Check side effects
                    self._check_tool_side_effects(tool_name, args)
                    
                    # Create checkpoint before tool execution
                    tool_checkpoint_id = None
                    if self.rollback_manager:
                        tool_checkpoint_id = self.rollback_manager.create_pre_tool_checkpoint(
                            session_id=session_id,
                            messages=self.messages,
                            tool_name=tool_name,
                            arguments=args
                        )
                    
                    # Tool call header - Dreamscape style with sparkle
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    yield f"\n[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]\n"
                    
                    # Execute tool
                    result = self.tool_executor.execute(tool_name, args)
                    
                    # Record tool call in operation history
                    if self.operation_history:
                        parent_id = self.operation_history.get_last_user_question().id if self.operation_history.get_last_user_question() else None
                        self.operation_history.add_tool_call(
                            tool_name=tool_name,
                            arguments=args,
                            result=result.output if result.success else None,
                            success=result.success,
                            error=result.error,
                            parent_id=parent_id
                        )
                    
                    if result.success:
                        output_preview = result.output.strip()
                        if output_preview:
                            preview_lines = output_preview.split('\n')
                            
                            formatted_output = ""
                            for line in preview_lines:
                                formatted_output += f"[#ba68c8]   │[/#ba68c8] [#e0e0e0]{line}[/#e0e0e0]\n"
                            
                            yield formatted_output
                    else:
                        yield f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]\n"
                    
                    # Add tool result to messages
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                # Reset continuation count for tool calls (this is expected looping)
                continuation_count = 0
                continue
            
            # No tool calls - save content and check if we should continue
            if collected_content:
                # Clean up //END// token if present
                clean_content = collected_content.replace("//END//", "").strip()
                
                # Save to messages
                self.messages.append({
                    "role": "assistant",
                    "content": clean_content
                })
                
                # Check if model finished naturally or needs continuation
                if finish_reason in ('stop', 'end_turn', 'end', None) or "//END//" in collected_content:
                    # Model finished - exit loop
                    break
                
                # Model stopped for other reason (length limit) - try to continue
                continuation_count += 1
                if continuation_count >= max_continuations:
                    break
                
                # Rebuild messages for continuation
                messages = self._build_messages()
                continue
            
            # No content at all, just break
            break
    
    def _process_streaming_request(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response using requests library"""
        import requests
        
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        max_continuations = 3  # Safety limit to prevent infinite loops
        continuation_count = 0
        
        while True:
            # Build payload
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": True,
            }
            
            # Add tools if available
            if tools:
                payload["tools"] = tools
            payload = self._prepare_request_payload(payload)
            headers = self._build_request_headers(stream=True)
            
            # Make request with retry logic
            try:
                response = make_api_request_with_retry(
                    url=self.base_url,
                    headers=headers,
                    payload=payload,
                    max_retries=self.api_max_retries,
                    initial_backoff=self.api_initial_backoff,
                    stream=True,
                    timeout=self.api_timeout
                )
            except requests.RequestException as e:
                logger.error(f"Streaming API request failed: {e}")
                raise
            
            # Collect streamed response
            collected_content = ""
            collected_thinking = ""
            collected_tool_calls = []
            finish_reason = None
            
            # Flag to track if we're in thinking mode
            thinking_started = False
            
            # Buffer for handling split tokens (to hide //END//)
            stream_buffer = ""
            token_to_hide = "//END//"
            
            # For iFlow direct API, properly handle SSE with chunk boundaries
            if self._is_iflow_direct_request():
                # Buffer to accumulate incomplete lines across chunk boundaries
                line_buffer = ""
                
                for chunk in response.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                    
                    # Add chunk to buffer
                    line_buffer += chunk.decode("utf-8")
                    
                    # Process complete lines
                    lines = line_buffer.split('\n')
                    
                    # Keep the last potentially incomplete line in the buffer
                    line_buffer = lines[-1]
                    
                    # Process all complete lines
                    for line in lines[:-1]:
                        line = line.rstrip()
                        if not line.strip():
                            continue
                        
                        # SSE format: "data: {...}" or "data:{...}"
                        if not line.startswith("data:"):
                            continue
                        
                        # Handle both "data: {...}" and "data:{...}" formats
                        data_str = line[5:].lstrip()
                        
                        # Check for [DONE] marker
                        if data_str.strip() == "[DONE]":
                            break
                        
                        try:
                            chunk_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        
                        # Extract choice
                        choices = chunk_data.get("choices", [])
                        if not choices:
                            continue
                        
                        choice = choices[0]
                        
                        # Track finish reason
                        if "finish_reason" in choice:
                            finish_reason = choice["finish_reason"]
                        
                        delta = choice.get("delta", {})
                        if not delta:
                            continue
                        
                        # Handle reasoning/thinking content - iFlow uses "reasoning_content"
                        reasoning_content = delta.get("reasoning_content") or delta.get("thinking")
                        
                        if reasoning_content:
                            collected_thinking += reasoning_content
                            if not thinking_started:
                                yield THINKING_START_MARKER
                                thinking_started = True
                            yield reasoning_content
                        
                        # Handle content streaming
                        content = delta.get("content")
                        if content:
                            if thinking_started:
                                yield THINKING_END_MARKER
                                thinking_started = False
                            
                            collected_content += content
                            stream_buffer += content
                            
                            if token_to_hide in stream_buffer:
                                parts = stream_buffer.split(token_to_hide)
                                if parts[0]:
                                    yield parts[0]
                                remaining = "".join(parts[1:])
                                stream_buffer = remaining
                            
                            # Check for partial match
                            partial_match_len = 0
                            for i in range(1, len(token_to_hide)):
                                if len(stream_buffer) >= i:
                                    suffix = stream_buffer[-i:]
                                    if token_to_hide.startswith(suffix):
                                        partial_match_len = i
                            
                            if partial_match_len > 0:
                                to_yield = stream_buffer[:-partial_match_len]
                                stream_buffer = stream_buffer[-partial_match_len:]
                                if to_yield:
                                    yield to_yield
                            else:
                                yield stream_buffer
                                stream_buffer = ""
                        
                        # Handle tool calls
                        tool_calls_delta = delta.get("tool_calls", [])
                        if tool_calls_delta:
                            for tool_call_delta in tool_calls_delta:
                                index = tool_call_delta.get("index", 0)
                                
                                if index >= len(collected_tool_calls):
                                    collected_tool_calls.append({
                                        "id": tool_call_delta.get("id", ""),
                                        "type": "function",
                                        "function": {
                                            "name": "",
                                            "arguments": ""
                                        }
                                    })
                                
                                function_delta = tool_call_delta.get("function", {})
                                if "name" in function_delta:
                                    collected_tool_calls[index]["function"]["name"] = function_delta["name"]
                                if "arguments" in function_delta:
                                    collected_tool_calls[index]["function"]["arguments"] += function_delta["arguments"]
                                if "id" in tool_call_delta:
                                    collected_tool_calls[index]["id"] = tool_call_delta["id"]
                
                # Process any remaining buffered line
                if line_buffer.strip():
                    line = line_buffer.rstrip()
                    if line.startswith("data:"):
                        data_str = line[5:].lstrip()
                        if data_str.strip() != "[DONE]":
                            try:
                                chunk_data = json.loads(data_str)
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    choice = choices[0]
                                    if "finish_reason" in choice:
                                        finish_reason = choice["finish_reason"]
                                    
                                    delta = choice.get("delta", {})
                                    if delta:
                                        reasoning_content = delta.get("reasoning_content") or delta.get("thinking")
                                        if reasoning_content:
                                            collected_thinking += reasoning_content
                                            if not thinking_started:
                                                yield THINKING_START_MARKER
                                                thinking_started = True
                                            yield reasoning_content
                                        
                                        content = delta.get("content")
                                        if content:
                                            if thinking_started:
                                                yield THINKING_END_MARKER
                                                thinking_started = False
                                            collected_content += content
                                            yield content
                            except json.JSONDecodeError:
                                pass
            else:
                # Original parsing logic for non-iFlow APIs
                # Parse SSE stream
                for line in response.iter_lines():
                    if not line:
                        continue
                    
                    line_str = line.decode("utf-8")
                    
                    # SSE format: "data: {...}"
                    if not line_str.startswith("data: "):
                        continue
                    
                    data_str = line_str[6:]  # Remove "data: " prefix
                    
                    # Check for [DONE] marker
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    
                    # Extract choice
                    choices = chunk_data.get("choices", [])
                    if not choices:
                        continue
                    
                    choice = choices[0]
                    
                    # Track finish reason
                    if "finish_reason" in choice:
                        finish_reason = choice["finish_reason"]
                    
                    delta = choice.get("delta", {})
                    if not delta:
                        continue
                    
                    # Handle reasoning/thinking content
                    reasoning_content = delta.get("reasoning_content") or delta.get("thinking")
                    
                    if reasoning_content:
                        collected_thinking += reasoning_content
                        if not thinking_started:
                            yield THINKING_START_MARKER
                            thinking_started = True
                        yield reasoning_content
                    
                    # Handle content streaming
                    content = delta.get("content")
                    if content:
                        if thinking_started:
                            yield THINKING_END_MARKER
                            thinking_started = False
                        
                        collected_content += content
                        stream_buffer += content
                        
                        if token_to_hide in stream_buffer:
                            parts = stream_buffer.split(token_to_hide)
                            if parts[0]:
                                yield parts[0]
                            remaining = "".join(parts[1:])
                            stream_buffer = remaining
                        
                        # Check for partial match
                        partial_match_len = 0
                        for i in range(1, len(token_to_hide)):
                            if len(stream_buffer) >= i:
                                suffix = stream_buffer[-i:]
                                if token_to_hide.startswith(suffix):
                                    partial_match_len = i
                        
                        if partial_match_len > 0:
                            to_yield = stream_buffer[:-partial_match_len]
                            stream_buffer = stream_buffer[-partial_match_len:]
                            if to_yield:
                                yield to_yield
                        else:
                            yield stream_buffer
                            stream_buffer = ""
                    
                    # Handle tool calls
                    tool_calls_delta = delta.get("tool_calls", [])
                    if tool_calls_delta:
                        for tool_call_delta in tool_calls_delta:
                            index = tool_call_delta.get("index", 0)
                            
                            if index >= len(collected_tool_calls):
                                collected_tool_calls.append({
                                    "id": tool_call_delta.get("id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": "",
                                        "arguments": ""
                                    }
                                })
                            
                            function_delta = tool_call_delta.get("function", {})
                            if "name" in function_delta:
                                collected_tool_calls[index]["function"]["name"] = function_delta["name"]
                            if "arguments" in function_delta:
                                collected_tool_calls[index]["function"]["arguments"] += function_delta["arguments"]
                            if "id" in tool_call_delta:
                                collected_tool_calls[index]["id"] = tool_call_delta["id"]
            
            # If thinking was streamed, emit end marker
            if thinking_started:
                yield THINKING_END_MARKER
            
            # Flush remaining buffer
            if stream_buffer and token_to_hide not in stream_buffer:
                yield stream_buffer
            
            # Check for tool calls
            if collected_tool_calls:
                assistant_message = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                # Execute tools
                for tool_call in collected_tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    yield f"\n[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]\n"
                    
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        output_preview = result.output.strip()
                        if output_preview:
                            preview_lines = output_preview.split('\n')
                            formatted_output = ""
                            for line in preview_lines:
                                formatted_output += f"[#ba68c8]   │[/#ba68c8] [#e0e0e0]{line}[/#e0e0e0]\n"
                            yield formatted_output
                    else:
                        yield f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]\n"
                    
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                continuation_count = 0
                continue
            
            # No tool calls - save content and check if we should continue
            if collected_content:
                clean_content = collected_content.replace("//END//", "").strip()
                self.messages.append({
                    "role": "assistant",
                    "content": clean_content
                })
                
                if finish_reason in ('stop', 'end_turn', 'end', None) or "//END//" in collected_content:
                    break
                
                continuation_count += 1
                if continuation_count >= max_continuations:
                    break
                
                messages = self._build_messages()
                continue
            
            break
    
    def _process_streaming_anthropic(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response using Anthropic SDK"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        max_continuations = 3
        continuation_count = 0
        
        # Convert messages to Anthropic format
        anthropic_messages = []
        system_message = None
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        while True:
            # Build kwargs for Anthropic API
            kwargs = {
                "model": self.model,
                "messages": anthropic_messages,
                "max_tokens": 4096,
                "stream": True
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            if tools:
                kwargs["tools"] = tools
            
            # Make request
            with self._client.messages.stream(**kwargs) as stream:
                collected_content = ""
                collected_thinking = ""
                collected_tool_calls = []
                thinking_started = False
                stream_buffer = ""
                token_to_hide = "//END//"
                
                for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event.content_block, 'type') and event.content_block.type == "thinking":
                            thinking_started = True
                            yield THINKING_START_MARKER
                    
                    elif event.type == "content_block_delta":
                        if hasattr(event.delta, 'type'):
                            if event.delta.type == "thinking_delta":
                                if hasattr(event.delta, 'thinking'):
                                    collected_thinking += event.delta.thinking
                                    yield event.delta.thinking
                            elif event.delta.type == "text_delta":
                                if hasattr(event.delta, 'text'):
                                    text = event.delta.text
                                    if thinking_started:
                                        yield THINKING_END_MARKER
                                        thinking_started = False
                                    
                                    collected_content += text
                                    stream_buffer += text
                                    
                                    if token_to_hide in stream_buffer:
                                        parts = stream_buffer.split(token_to_hide)
                                        if parts[0]:
                                            yield parts[0]
                                        remaining = "".join(parts[1:])
                                        stream_buffer = remaining
                                    
                                    partial_match_len = 0
                                    for i in range(1, len(token_to_hide)):
                                        if len(stream_buffer) >= i:
                                            suffix = stream_buffer[-i:]
                                            if token_to_hide.startswith(suffix):
                                                partial_match_len = i
                                    
                                    if partial_match_len > 0:
                                        to_yield = stream_buffer[:-partial_match_len]
                                        stream_buffer = stream_buffer[-partial_match_len:]
                                        if to_yield:
                                            yield to_yield
                                    else:
                                        yield stream_buffer
                                        stream_buffer = ""
                    
                    elif event.type == "content_block_stop":
                        if thinking_started:
                            yield THINKING_END_MARKER
                            thinking_started = False
                    
                    elif event.type == "message_stop":
                        break
                
                # Flush remaining buffer
                if stream_buffer and token_to_hide not in stream_buffer:
                    yield stream_buffer
                
                # Get final message for tool calls
                final_message = stream.get_final_message()
                
                # Check for tool use blocks
                tool_use_blocks = [block for block in final_message.content if block.type == "tool_use"]
                
                if tool_use_blocks:
                    collected_tool_calls = []
                    for block in tool_use_blocks:
                        collected_tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input)
                            }
                        })
                
                # Check for tool calls
                if collected_tool_calls:
                    assistant_message = {
                        "role": "assistant",
                        "content": collected_content or None,
                        "tool_calls": collected_tool_calls
                    }
                    self.messages.append(assistant_message)
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": collected_content or ""
                    })
                    
                    # Execute tools
                    for tool_call in collected_tool_calls:
                        tool_name = tool_call["function"]["name"]
                        tool = self.tool_executor.get_tool(tool_name)
                        
                        try:
                            args = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}
                        
                        self._check_tool_side_effects(tool_name, args)
                        
                        exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                        yield f"\n[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]\n"
                        
                        result = self.tool_executor.execute(tool_name, args)
                        
                        if result.success:
                            output_preview = result.output.strip()
                            if output_preview:
                                preview_lines = output_preview.split('\n')
                                formatted_output = ""
                                for line in preview_lines:
                                    formatted_output += f"[#ba68c8]   │[/#ba68c8] [#e0e0e0]{line}[/#e0e0e0]\n"
                                yield formatted_output
                        else:
                            yield f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]\n"
                        
                        tool_result_message = {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": result.output if result.success else f"Error: {result.error}"
                        }
                        self.messages.append(tool_result_message)
                        anthropic_messages.append({
                            "role": "user",
                            "content": f"Tool result: {result.output if result.success else f'Error: {result.error}'}"
                        })
                    
                    continuation_count = 0
                    continue
                
                # No tool calls - save content and check if we should continue
                if collected_content:
                    clean_content = collected_content.replace("//END//", "").strip()
                    self.messages.append({
                        "role": "assistant",
                        "content": clean_content
                    })
                    
                    if "//END//" in collected_content:
                        break
                    
                    continuation_count += 1
                    if continuation_count >= max_continuations:
                        break
                    
                    anthropic_messages = self._build_messages()
                    continue
            
            break
    
    def _process_non_streaming(self, session_id: str = "default") -> str:
        """Process without streaming"""
        if self.provider == "openai-sdk":
            return self._process_non_streaming_openai_sdk(session_id=session_id)
        elif self.provider == "request":
            return self._process_non_streaming_request(session_id=session_id)
        elif self.provider == "anthropic":
            return self._process_non_streaming_anthropic(session_id=session_id)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _process_non_streaming_openai_sdk(self, session_id: str = "default") -> str:
        """Process without streaming using OpenAI SDK"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        all_content = []
        
        while True:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                stream=False
            )
            
            choice = response.choices[0]
            message = choice.message
            
            # Check for tool calls
            if message.tool_calls:
                # Add assistant message
                assistant_message = {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                if message.content:
                    all_content.append(message.content)
                
                # Execute each tool
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    # Check side effects
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]")
                    
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        all_content.append(f"[bold #66bb6a]   ✔ Success[/bold #66bb6a]")
                    else:
                        all_content.append(f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]")
                    
                    # Add tool result
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                # Continue to get response to tool results
                continue
            
            # No tool calls, final response check
            if message.content:
                content = message.content
                
                if "//END//" in content:
                    clean_content = content.replace("//END//", "").strip()
                    self.messages.append({
                        "role": "assistant",
                        "content": clean_content
                    })
                    all_content.append(clean_content) # Use clean content for return
                    break
                
                # Missing termination token - continue
                if self.messages and self.messages[-1].get("role") == "assistant" and "tool_calls" not in self.messages[-1]:
                    self.messages[-1]["content"] += content
                else:
                    self.messages.append({
                        "role": "assistant",
                        "content": content
                    })
                
                all_content.append(content)
                
                # Rebuild messages for next call
                messages = self._build_messages()
                continue
            
            break
        
        return '\n'.join(all_content)
    
    def _process_non_streaming_request(self, session_id: str = "default") -> str:
        """Process without streaming using requests library"""
        import requests
        
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        all_content = []
        
        while True:
            # Build payload
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
            }
            
            # Add tools if available
            if tools:
                payload["tools"] = tools
            payload = self._prepare_request_payload(payload)
            headers = self._build_request_headers(stream=False)
            
            # Make request with retry logic
            try:
                response = make_api_request_with_retry(
                    url=self.base_url,
                    headers=headers,
                    payload=payload,
                    max_retries=self.api_max_retries,
                    initial_backoff=self.api_initial_backoff,
                    stream=False,
                    timeout=self.api_timeout
                )
            except requests.RequestException as e:
                logger.error(f"API request failed: {e}")
                raise
            
            response_data = response.json()
            
            # Extract choice
            choices = response_data.get("choices", [])
            if not choices:
                break
            
            choice = choices[0]
            message = choice.get("message", {})
            
            # Check for tool calls
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                # Add assistant message
                assistant_message = {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                if message.get("content"):
                    all_content.append(message["content"])
                
                # Execute each tool
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]")
                    
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        all_content.append(f"[bold #66bb6a]   ✔ Success[/bold #66bb6a]")
                    else:
                        all_content.append(f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]")
                    
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    messages.append(tool_result_message)
                
                continue
            
            # No tool calls, final response check
            content = message.get("content")
            if content:
                if "//END//" in content:
                    clean_content = content.replace("//END//", "").strip()
                    self.messages.append({
                        "role": "assistant",
                        "content": clean_content
                    })
                    all_content.append(clean_content)
                    break
                
                if self.messages and self.messages[-1].get("role") == "assistant" and "tool_calls" not in self.messages[-1]:
                    self.messages[-1]["content"] += content
                else:
                    self.messages.append({
                        "role": "assistant",
                        "content": content
                    })
                
                all_content.append(content)
                messages = self._build_messages()
                continue
            
            break
        
        return '\n'.join(all_content)
    
    def _process_non_streaming_anthropic(self, session_id: str = "default") -> str:
        """Process without streaming using Anthropic SDK"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        all_content = []
        
        # Convert messages to Anthropic format
        anthropic_messages = []
        system_message = None
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        while True:
            # Build kwargs for Anthropic API
            kwargs = {
                "model": self.model,
                "messages": anthropic_messages,
                "max_tokens": 4096,
            }
            
            if system_message:
                kwargs["system"] = system_message
            
            if tools:
                kwargs["tools"] = tools
            
            # Make request
            response = self._client.messages.create(**kwargs)
            
            # Extract content
            content_blocks = response.content
            collected_content = ""
            collected_tool_calls = []
            
            for block in content_blocks:
                if block.type == "text":
                    collected_content += block.text
                elif block.type == "tool_use":
                    collected_tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input)
                        }
                    })
            
            # Check for tool calls
            if collected_tool_calls:
                assistant_message = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls
                }
                self.messages.append(assistant_message)
                anthropic_messages.append({
                    "role": "assistant",
                    "content": collected_content or ""
                })
                
                if collected_content:
                    all_content.append(collected_content)
                
                # Execute each tool
                for tool_call in collected_tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool = self.tool_executor.get_tool(tool_name)
                    
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{exec_msg}[/bold #e4b0ff]")
                    
                    result = self.tool_executor.execute(tool_name, args)
                    
                    if result.success:
                        all_content.append(f"[bold #66bb6a]   ✔ Success[/bold #66bb6a]")
                    else:
                        all_content.append(f"[bold #ff5252]   ✘ Failed:[/bold #ff5252] [#ff8a80]{rich_escape(result.error or '')}[/#ff8a80]")
                    
                    tool_result_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result.output if result.success else f"Error: {result.error}"
                    }
                    self.messages.append(tool_result_message)
                    anthropic_messages.append({
                        "role": "user",
                        "content": f"Tool result: {result.output if result.success else f'Error: {result.error}'}"
                    })
                
                continue
            
            # No tool calls, final response check
            if collected_content:
                if "//END//" in collected_content:
                    clean_content = collected_content.replace("//END//", "").strip()
                    self.messages.append({
                        "role": "assistant",
                        "content": clean_content
                    })
                    all_content.append(clean_content)
                    break
                
                if self.messages and self.messages[-1].get("role") == "assistant" and "tool_calls" not in self.messages[-1]:
                    self.messages[-1]["content"] += collected_content
                else:
                    self.messages.append({
                        "role": "assistant",
                        "content": collected_content
                    })
                
                all_content.append(collected_content)
                anthropic_messages = self._build_messages()
                continue
            
            break
        
        return '\n'.join(all_content)
    
    def clear_history(self) -> None:
        """Clear conversation history"""
        self.messages = []
    
    def get_history(self) -> List[Dict]:
        """Get conversation history"""
        return self.messages.copy()
    
    def set_history(self, messages: List[Dict]) -> None:
        """Set conversation history (for session restore)"""
        self.messages = messages.copy()
    
    def _check_and_compress_context(self) -> None:
        """Check if context exceeds 60% threshold and trigger compression if needed"""
        # Get max tokens from config or active model
        max_tokens = 128000
        config_manager = self.tool_executor.context.get('config_manager')
        
        if config_manager:
            model_config = config_manager.get_active_model()
            if model_config and model_config.max_context_tokens:
                max_tokens = model_config.max_context_tokens
            else:
                config = config_manager.load()
                max_tokens = getattr(config, 'max_context_tokens', 128000)
        elif hasattr(self, 'config'):
            max_tokens = getattr(self.config, 'max_context_tokens', 128000)
        
        # Calculate current token estimate
        token_estimate = self.get_token_estimate()
        
        # Check if we've exceeded 60% threshold
        threshold = max_tokens * 0.6
        if token_estimate >= threshold:
            # Import here to avoid circular imports
            from ..context_engine.compressor import ContextCompressor
            from ..config import get_project_data_dir
            
            # Get session ID for checkpointing
            session_manager = self.tool_executor.context.get('session_manager')
            session_id = "default"
            if session_manager and session_manager.get_current_session():
                session_id = session_manager.get_current_session().id
            
            # Initialize compressor
            project_data_dir = get_project_data_dir(self.project_root)
            compressor = ContextCompressor(project_data_dir)
            
            # Build full message list including system prompt
            full_messages = [{"role": "system", "content": self.system_prompt}]
            full_messages.extend(self.messages)
            
            # Compress context
            try:
                compressed_messages = compressor.compress(
                    messages=full_messages,
                    client=self._client,
                    model=self.model,
                    session_id=session_id,
                    provider=self.provider,
                    base_url=self.base_url,
                    api_key=self.api_key
                )
                
                # Update messages (exclude system prompt which is handled separately)
                self.messages = compressed_messages[1:]  # Skip system prompt
                
                # Add a notification about the compression
                compression_note = {
                    "role": "system",
                    "content": f"[Context Engine: Session compressed from {token_estimate:,} to {self.get_token_estimate():,} tokens to maintain memory persistence]"
                }
                self.messages.insert(0, compression_note)
                
            except Exception as e:
                # If compression fails, add a warning but continue
                warning_note = {
                    "role": "system", 
                    "content": f"[Context Engine Warning: Auto-compression failed - {str(e)}]"
                }
                self.messages.insert(0, warning_note)
    
    def get_token_estimate(self) -> int:
        """Estimate tokens in current conversation"""
        total_chars = len(self.system_prompt)
        for msg in self.messages:
            content = msg.get('content', '')
            if content:
                total_chars += len(content)
        
        # Rough estimate: 1 token ≈ 4 characters
        return total_chars // 4
