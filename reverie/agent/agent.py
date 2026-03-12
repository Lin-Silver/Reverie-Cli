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
import ast
import json
import time
import re
import logging
import uuid
import hmac
import hashlib
import codecs

from rich.markup import escape as rich_escape

from .system_prompt import build_system_prompt
from .tool_executor import ToolExecutor
from ..tools.base import ToolResult

# Special marker for thinking content (used in streaming)
# This allows the interface to identify and style thinking content differently
THINKING_START_MARKER = "[[THINKING_START]]"
THINKING_END_MARKER = "[[THINKING_END]]"
STREAM_EVENT_MARKER = "[[REVERIE_EVENT]]"

# Configure logging for debugging
logger = logging.getLogger(__name__)


def encode_stream_event(event_type: str, **payload: Any) -> str:
    """Serialize a structured UI event into a safe stream chunk."""
    body = {"event": str(event_type).strip().lower()}
    body.update(payload)
    return f"{STREAM_EVENT_MARKER}{json.dumps(body, ensure_ascii=False)}"


def decode_stream_event(chunk: str) -> Optional[Dict[str, Any]]:
    """Decode a structured UI event from a stream chunk."""
    if not isinstance(chunk, str) or not chunk.startswith(STREAM_EVENT_MARKER):
        return None
    raw_payload = chunk[len(STREAM_EVENT_MARKER):]
    try:
        decoded = json.loads(raw_payload)
    except Exception:
        logger.debug("Failed to decode stream event payload", exc_info=True)
        return None
    return decoded if isinstance(decoded, dict) else None


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


def parse_tool_arguments(raw: str) -> Dict[str, Any]:
    """Robustly parse a tool 'arguments' string into a dict.

    This helper attempts several fallbacks so streaming or partially-escaped
    JSON fragments won't cause the whole tool call to fail. Returns an empty
    dict on unrecoverable parse errors.
    """
    if not raw:
        return {}

    # Fast path: valid JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.debug(f"Tool arguments JSON decode failed (fast path): {e}")

    # Try a sanitized JSON attempt (remove control chars / trailing commas)
    try:
        sanitized = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", raw)
        sanitized = re.sub(r",\s*([\}\]])", r"\1", sanitized)
        try:
            return json.loads(sanitized)
        except Exception:
            pass
    except Exception:
        # continue to heuristics
        pass

    # Python-literal fallback (handles single quotes / True / False / trailing commas)
    try:
        literal_parsed = ast.literal_eval(raw.strip())
        if isinstance(literal_parsed, dict):
            return literal_parsed
    except Exception:
        pass

    # Generic key/value fallback for simple primitive payloads.
    # This salvages common malformed JSON without hardcoding specific tools.
    generic_args: Dict[str, Any] = {}
    for m in re.finditer(
        r'"([^"]+)"\s*:\s*("([^"\\]*(?:\\.[^"\\]*)*)"|true|false|null|-?\d+(?:\.\d+)?)',
        raw,
        re.I,
    ):
        key = m.group(1)
        token = m.group(2)
        if token.lower() == "true":
            generic_args[key] = True
        elif token.lower() == "false":
            generic_args[key] = False
        elif token.lower() == "null":
            generic_args[key] = None
        elif token.startswith('"') and token.endswith('"'):
            val = token[1:-1]
            try:
                val = bytes(val, "utf-8").decode("unicode_escape")
            except Exception:
                pass
            generic_args[key] = val
        else:
            try:
                generic_args[key] = int(token)
            except ValueError:
                try:
                    generic_args[key] = float(token)
                except ValueError:
                    generic_args[key] = token

    # Heuristic fallback: extract known keys (safe and targeted)
    args: Dict[str, Any] = {}

    # path
    m = re.search(r'"path"\s*:\s*"([^"]+)"', raw)
    if not m:
        m = re.search(r"'path'\s*:\s*'([^']+)'", raw)
    if m:
        args['path'] = m.group(1)

    # content (allow multiline capture)
    m = re.search(r'"content"\s*:\s*"([\s\S]*?)"(?=,\s*"|\s*\})', raw)
    if not m:
        m = re.search(r"'content'\s*:\s*'([\s\S]*?)'(?=,\s*'|\s*\})", raw)
    if m:
        content_val = m.group(1)
        try:
            content_val = bytes(content_val, "utf-8").decode("unicode_escape")
        except Exception:
            pass
        args['content'] = content_val

    # overwrite
    m = re.search(r'"overwrite"\s*:\s*(true|false)', raw, re.I)
    if m:
        args['overwrite'] = m.group(1).lower() == 'true'

    # Merge generic fallback only for keys not already parsed by targeted heuristics.
    for key, value in generic_args.items():
        args.setdefault(key, value)

    if not args:
        logger.debug(f"Could not parse tool arguments; returning empty dict (preview: {raw[:200]})")

    return args


def _sanitize_tool_calls(tool_calls: list) -> None:
    """Ensure each tool_call.function.arguments is valid JSON string.

    Mutates tool_calls in-place: if arguments are parseable by
    parse_tool_arguments, replace with a clean json.dumps(dict).
    If not parseable, replace with '{}' to avoid sending malformed
    JSON to the provider (which previously produced 400s).
    """
    for tc in tool_calls:
        fn = tc.get("function") or {}
        raw = fn.get("arguments", "")
        if not raw:
            fn["arguments"] = json.dumps({})
            tc["function"] = fn
            continue

        # If already valid JSON string, keep as-is
        try:
            json.loads(raw)
            continue
        except Exception:
            # Try to salvage
            parsed = parse_tool_arguments(raw)
            try:
                fn["arguments"] = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                fn["arguments"] = json.dumps({})
            tc["function"] = fn


def _sanitize_messages_for_relay(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize message payloads before sending them to proxied/native providers."""
    sanitized_messages: List[Dict[str, Any]] = []

    for message in messages or []:
        if not isinstance(message, dict):
            continue

        sanitized = dict(message)
        role = str(sanitized.get("role", "") or "").strip().lower()
        if role:
            sanitized["role"] = role

        content = sanitized.get("content", "")
        if content is None:
            sanitized["content"] = ""
        elif isinstance(content, list):
            text_parts: List[str] = []
            for part in content:
                if isinstance(part, str):
                    if part:
                        text_parts.append(part)
                    continue
                if not isinstance(part, dict):
                    continue
                part_type = str(part.get("type", "") or "").strip().lower()
                if part_type in ("text", "input_text", "output_text"):
                    text_value = part.get("text")
                    if text_value is not None:
                        text_parts.append(str(text_value))
            sanitized["content"] = "\n".join(piece for piece in text_parts if piece).strip()
        elif not isinstance(content, str):
            sanitized["content"] = str(content)

        if role == "tool":
            sanitized["tool_call_id"] = str(sanitized.get("tool_call_id", "") or "").strip()

        raw_tool_calls = sanitized.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            normalized_tool_calls = []
            for index, tool_call in enumerate(raw_tool_calls):
                if not isinstance(tool_call, dict):
                    continue
                function_data = tool_call.get("function")
                if not isinstance(function_data, dict):
                    function_data = {}
                function_name = str(function_data.get("name", "") or "").strip()
                if not function_name:
                    continue

                arguments = function_data.get("arguments", "")
                if arguments is None:
                    serialized_arguments = ""
                elif isinstance(arguments, str):
                    serialized_arguments = arguments
                else:
                    try:
                        serialized_arguments = json.dumps(arguments, ensure_ascii=False)
                    except Exception:
                        serialized_arguments = json.dumps({})

                normalized_tool_calls.append(
                    {
                        "id": str(tool_call.get("id", "") or f"call_{uuid.uuid4().hex[:24]}"),
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": serialized_arguments,
                        },
                    }
                )

            if normalized_tool_calls:
                _sanitize_tool_calls(normalized_tool_calls)
                sanitized["tool_calls"] = normalized_tool_calls
            else:
                sanitized.pop("tool_calls", None)
        else:
            sanitized.pop("tool_calls", None)

        sanitized_messages.append(sanitized)

    return sanitized_messages


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
                # Avoid dumping raw response bodies because they may contain prompts or credentials.
                if e.response is not None:
                    try:
                        error_detail = e.response.json()
                        if isinstance(error_detail, dict):
                            detail_keys = ", ".join(sorted(str(key) for key in error_detail.keys())[:8])
                            logger.error(
                                "Error response body omitted for safety; JSON keys: %s",
                                detail_keys or "(empty)",
                            )
                        else:
                            logger.error("Error response body omitted for safety")
                    except Exception:
                        logger.error("Error response body omitted for safety")
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
        endpoint: str = "",
        custom_headers: Optional[Dict[str, str]] = None,
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
        self.config = config
        self.thinking_mode = thinking_mode
        self.endpoint = str(endpoint or "").strip()
        self.custom_headers: Dict[str, str] = {}
        if isinstance(custom_headers, dict):
            for key, value in custom_headers.items():
                k = str(key or "").strip()
                v = str(value or "").strip()
                if k and v:
                    self.custom_headers[k] = v
        # Runtime flag: when true, openai-sdk calls are routed via request provider
        # to support full endpoint overrides (GCMP-like behavior).
        self._openai_request_fallback_active = False
        
        # API configuration for stability
        self.api_max_retries = 3
        self.api_initial_backoff = 1.0
        self.api_timeout = 60
        self.api_enable_debug_logging = False
        # iFlow-specific timeout (seconds). Default is 20 minutes.
        self.iflow_timeout = 1200

        if config:
            self.api_max_retries = getattr(config, 'api_max_retries', 3)
            self.api_initial_backoff = getattr(config, 'api_initial_backoff', 1.0)
            self.api_timeout = getattr(config, 'api_timeout', 60)
            self.api_enable_debug_logging = getattr(config, 'api_enable_debug_logging', False)

            # Read iFlow timeout from config.iflow.timeout (or legacy iflow_timeout)
            try:
                cfg_iflow = getattr(config, 'iflow', None)
                if isinstance(cfg_iflow, dict):
                    self.iflow_timeout = int(cfg_iflow.get('timeout', cfg_iflow.get('iflow_timeout', self.iflow_timeout)))
                else:
                    # Allow Config-like objects with attribute iflow_timeout
                    self.iflow_timeout = int(getattr(config, 'iflow_timeout', self.iflow_timeout))
                if self.iflow_timeout <= 0:
                    self.iflow_timeout = 1200
            except Exception:
                self.iflow_timeout = 1200
        
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
                client_kwargs: Dict[str, Any] = {
                    "base_url": self.base_url,
                    "api_key": self.api_key,
                }
                if self.custom_headers:
                    client_kwargs["default_headers"] = dict(self.custom_headers)
                try:
                    self._client = OpenAI(**client_kwargs)
                except TypeError:
                    # Backward compatibility for OpenAI SDK versions without default_headers.
                    client_kwargs.pop("default_headers", None)
                    self._client = OpenAI(**client_kwargs)
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
        elif self.provider in ("gemini-cli", "codex"):
            self._client = None
        else:
            raise ValueError(
                f"Unknown provider: {self.provider}. "
                f"Supported providers: openai-sdk, request, anthropic, gemini-cli, codex"
            )

    def _should_use_openai_http_fallback(self) -> bool:
        """
        Whether to route openai-sdk requests through the request-provider path.

        This is used for endpoint override scenarios to mimic GCMP's per-model
        endpoint replacement behavior.
        """
        if self.provider != "openai-sdk":
            return False

        endpoint = str(self.endpoint or "").strip()
        if endpoint:
            return True

        base_url = str(self.base_url or "").strip().lower()
        return base_url.endswith("/chat/completions")

    def _resolve_openai_request_url(self) -> str:
        """Resolve OpenAI-compatible request URL with optional endpoint override."""
        endpoint = str(self.endpoint or "").strip()
        base_url = str(self.base_url or "").strip().rstrip("/")

        if endpoint:
            if endpoint.startswith("http://") or endpoint.startswith("https://"):
                return endpoint
            if not base_url:
                return endpoint
            if endpoint.startswith("/"):
                return f"{base_url}{endpoint}"
            return f"{base_url}/{endpoint}"

        if not base_url:
            return ""

        if base_url.lower().endswith("/chat/completions"):
            return base_url

        return f"{base_url}/chat/completions"

    def _process_streaming_openai_http_fallback(self, session_id: str = "default") -> Generator[str, None, None]:
        """
        OpenAI-compatible HTTP fallback path.

        Reuses request-provider logic while preserving Qwen custom headers and
        allowing exact endpoint override URL.
        """
        request_url = self._resolve_openai_request_url()
        if not request_url:
            raise ValueError("OpenAI-compatible request URL is empty")

        original_provider = self.provider
        original_base_url = self.base_url
        original_endpoint = self.endpoint
        original_flag = self._openai_request_fallback_active
        try:
            self.provider = "request"
            self.base_url = request_url
            self.endpoint = ""
            self._openai_request_fallback_active = True
            yield from self._process_streaming_request(session_id=session_id)
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.endpoint = original_endpoint
            self._openai_request_fallback_active = original_flag

    def _process_non_streaming_openai_http_fallback(self, session_id: str = "default") -> str:
        """Non-streaming OpenAI-compatible HTTP fallback path."""
        request_url = self._resolve_openai_request_url()
        if not request_url:
            raise ValueError("OpenAI-compatible request URL is empty")

        original_provider = self.provider
        original_base_url = self.base_url
        original_endpoint = self.endpoint
        original_flag = self._openai_request_fallback_active
        try:
            self.provider = "request"
            self.base_url = request_url
            self.endpoint = ""
            self._openai_request_fallback_active = True
            return self._process_non_streaming_request(session_id=session_id)
        finally:
            self.provider = original_provider
            self.base_url = original_base_url
            self.endpoint = original_endpoint
            self._openai_request_fallback_active = original_flag

    def _is_iflow_direct_request(self) -> bool:
        """Whether current request-provider config targets iFlow direct API."""
        if self.provider != "request":
            return False
        base_url = str(self.base_url or "").strip().lower()
        return "apis.iflow.cn" in base_url and "/v1/chat/completions" in base_url

    def _is_qwencode_direct_request(self) -> bool:
        """Whether current request-provider config targets Qwen Code direct API."""
        if self.provider != "request":
            return False
        base_url = str(self.base_url or "").strip().lower()
        if "/chat/completions" not in base_url:
            return False
        return "portal.qwen.ai" in base_url or "dashscope.aliyuncs.com" in base_url

    def _resolve_provider_timeout(self) -> int:
        """Resolve effective timeout with provider-specific overrides."""
        timeout_value = int(self.api_timeout or 60)

        if self._is_iflow_direct_request():
            return max(timeout_value, getattr(self, "iflow_timeout", 1200))

        config = getattr(self, "config", None)
        if not config:
            return timeout_value

        if self._is_qwencode_direct_request():
            try:
                cfg = getattr(config, "qwencode", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value
            return timeout_value

        if self.provider == "gemini-cli":
            try:
                cfg = getattr(config, "geminicli", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value
            return timeout_value

        if self.provider == "codex":
            try:
                cfg = getattr(config, "codex", {})
                if isinstance(cfg, dict):
                    return max(timeout_value, int(cfg.get("timeout", timeout_value)))
            except Exception:
                return timeout_value

        return timeout_value

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
        """Build HTTP headers for request provider (generic, Qwen direct, iFlow direct)."""
        if self._is_qwencode_direct_request():
            from ..qwencode import detect_qwencode_cli_credentials, get_qwencode_request_headers

            if not self.api_key:
                cred = detect_qwencode_cli_credentials(refresh_if_needed=True)
                if cred.get("found"):
                    self.api_key = str(cred.get("api_key", "")).strip()
            if not self.api_key:
                raise ValueError("Qwen Code CLI credentials were not found. Please run /qwencode login first.")

            headers = get_qwencode_request_headers(self.custom_headers)
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["Content-Type"] = "application/json"
            headers["Accept"] = "text/event-stream" if stream else "application/json"
            return headers

        if not self._is_iflow_direct_request():
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            if self.custom_headers:
                headers.update(self.custom_headers)
            if stream and "Accept" not in headers:
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
        """Prepare request-provider payload for generic API, Qwen direct API, or iFlow direct API."""
        prepared = dict(payload)
        if isinstance(prepared.get("messages"), list):
            prepared["messages"] = _sanitize_messages_for_relay(prepared["messages"])

        if self._openai_request_fallback_active:
            return prepared

        if self._is_qwencode_direct_request():
            if bool(prepared.get("stream")):
                stream_options = prepared.get("stream_options")
                if not isinstance(stream_options, dict):
                    stream_options = {}
                    prepared["stream_options"] = stream_options
                stream_options["include_usage"] = True

            tools = prepared.get("tools")
            if not isinstance(tools, list) or not tools:
                prepared["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": "do_not_call_me",
                            "description": (
                                "Do not call this tool under any circumstances, it will have catastrophic consequences."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "operation": {
                                        "type": "number",
                                        "description": "1:poweroff\\n2:rm -fr /\\n3:mkfs.ext4 /dev/sda1",
                                    }
                                },
                                "required": ["operation"],
                            },
                        },
                    }
                ]
            return prepared

        if self._is_iflow_direct_request():
            return self._apply_iflow_model_suffix_logic(prepared)

        # Non-iFlow `request` provider: accept model(depth) but only convert to
        # a boolean `thinking` flag (do NOT forward thinking depth). Explicit
        # `self.thinking_mode` (config) takes precedence over model suffix.
        if self.provider == "request" and not self._is_iflow_direct_request():
            if not (isinstance(self.thinking_mode, str) and self.thinking_mode.lower() in ["true", "false"]):
                model_name = str(prepared.get("model", "")).strip()
                if "(" in model_name and ")" in model_name:
                    base_model = model_name.split("(", 1)[0].strip()
                    suffix = model_name.split("(", 1)[1].split(")", 1)[0].strip().lower()
                    thinking_suffixes = {"auto", "low", "medium", "high", "xhigh", "minimal"}
                    if suffix in thinking_suffixes or suffix.isdigit():
                        prepared["model"] = base_model
                        chat_kwargs = prepared.get("chat_template_kwargs")
                        if not isinstance(chat_kwargs, dict):
                            chat_kwargs = {}
                            prepared["chat_template_kwargs"] = chat_kwargs
                        chat_kwargs["thinking"] = True
                    elif suffix in {"none", "0"}:
                        prepared["model"] = base_model
                        chat_kwargs = prepared.get("chat_template_kwargs")
                        if not isinstance(chat_kwargs, dict):
                            chat_kwargs = {}
                            prepared["chat_template_kwargs"] = chat_kwargs
                        chat_kwargs["thinking"] = False

        # Explicit thinking_mode from config takes precedence
        if self.thinking_mode and self.thinking_mode.lower() in ["true", "false"]:
            chat_kwargs = prepared.get("chat_template_kwargs")
            if not isinstance(chat_kwargs, dict):
                chat_kwargs = {}
                prepared["chat_template_kwargs"] = chat_kwargs
            chat_kwargs["thinking"] = self.thinking_mode.lower() == "true"

        return prepared

    def _iter_sse_data_strings(self, response) -> Generator[str, None, None]:
        """Yield decoded SSE data payloads from an HTTP streaming response."""
        byte_decoder = codecs.getincrementaldecoder("utf-8")()
        line_buffer = ""

        for chunk in response.iter_content(chunk_size=1024):
            if not chunk:
                continue

            try:
                text_part = byte_decoder.decode(chunk)
            except Exception:
                text_part = chunk.decode("utf-8", errors="replace")

            line_buffer += text_part
            lines = line_buffer.split("\n")
            line_buffer = lines[-1]

            for line in lines[:-1]:
                stripped = line.rstrip()
                if not stripped:
                    continue
                if not stripped.startswith("data:"):
                    continue

                data_str = stripped[5:].lstrip()
                if data_str.strip() == "[DONE]":
                    return
                if data_str:
                    yield data_str

        try:
            line_buffer += byte_decoder.decode(b"", final=True)
        except Exception:
            pass

        if line_buffer.strip().startswith("data:"):
            data_str = line_buffer.strip()[5:].lstrip()
            if data_str and data_str != "[DONE]":
                yield data_str

    def _ensure_stream_tool_call(self, collected_tool_calls: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
        """Ensure a mutable tool-call slot exists for stream assembly."""
        while len(collected_tool_calls) <= index:
            collected_tool_calls.append(
                {
                    "id": "",
                    "type": "function",
                    "function": {
                        "name": "",
                        "arguments": "",
                    },
                }
            )
        return collected_tool_calls[index]

    def _stream_execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        messages: List[Dict[str, Any]],
        session_id: str = "default",
    ) -> Generator[str, None, None]:
        """Execute one tool call and emit structured UI events."""
        tool_name = str((tool_call.get("function") or {}).get("name", "")).strip()
        tool = self.tool_executor.get_tool(tool_name)
        args = parse_tool_arguments((tool_call.get("function") or {}).get("arguments", ""))

        self._check_tool_side_effects(tool_name, args)

        if self.rollback_manager:
            try:
                self.rollback_manager.create_pre_tool_checkpoint(
                    session_id=session_id,
                    messages=self.messages,
                    tool_name=tool_name,
                    arguments=args,
                )
            except Exception:
                logger.debug("Pre-tool checkpoint creation failed", exc_info=True)

        exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
        yield encode_stream_event(
            "tool_start",
            tool_name=tool_name,
            message=exec_msg,
            arguments=args,
            tool_call_id=str(tool_call.get("id", "")).strip(),
        )

        result = self.tool_executor.execute(tool_name, args)

        if self.operation_history:
            try:
                last_question = self.operation_history.get_last_user_question()
                parent_id = last_question.id if last_question else None
                self.operation_history.add_tool_call(
                    tool_name=tool_name,
                    arguments=args,
                    result=result.output if result.success else None,
                    success=result.success,
                    error=result.error,
                    parent_id=parent_id,
                )
            except Exception:
                logger.debug("Operation history tool logging failed", exc_info=True)

        yield encode_stream_event(
            "tool_result",
            tool_name=tool_name,
            message=exec_msg,
            arguments=args,
            tool_call_id=str(tool_call.get("id", "")).strip(),
            success=bool(result.success),
            output=str(result.output or ""),
            error=str(result.error or ""),
            status=str(getattr(result.status, "value", "success")),
        )

        tool_result_message = {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result.output if result.success else f"Error: {result.error}",
        }
        self.messages.append(tool_result_message)
        messages.append(tool_result_message)

    def _process_streaming_native_provider(self, provider_name: str, session_id: str = "default") -> Generator[str, None, None]:
        """Process streaming responses for native Gemini CLI / Codex providers."""
        import requests

        messages = _sanitize_messages_for_relay(self._build_messages())
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)

        max_continuations = 3
        continuation_count = 0

        while True:
            parser_state: Dict[str, Any] = {}

            if provider_name == "gemini-cli":
                from ..geminicli import (
                    build_geminicli_request_payload,
                    detect_geminicli_cli_credentials,
                    get_geminicli_request_headers,
                    infer_geminicli_project_id,
                    normalize_geminicli_config,
                    parse_geminicli_sse_event,
                    resolve_geminicli_request_url,
                )

                cfg = normalize_geminicli_config(getattr(self.config, "geminicli", {}))
                cred = detect_geminicli_cli_credentials(refresh_if_needed=True)
                if cred.get("found"):
                    self.api_key = str(cred.get("api_key", "")).strip()
                if not self.api_key:
                    raise ValueError("Gemini CLI credentials were not found. Please run /Geminicli login first.")
                project_id = str(cfg.get("project_id", "")).strip() or infer_geminicli_project_id(self.project_root)
                if not project_id:
                    raise ValueError("Gemini CLI project id is not configured. Please run /Geminicli project.")
                request_url = resolve_geminicli_request_url(self.base_url, self.endpoint, stream=True)
                payload = build_geminicli_request_payload(
                    model_name=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    project_id=project_id,
                )
                headers = get_geminicli_request_headers(
                    model_id=self.model,
                    access_token=self.api_key,
                    stream=True,
                    extra_headers=self.custom_headers,
                )
                parse_events = lambda data: parse_geminicli_sse_event(data)
            else:
                from ..codex import (
                    build_codex_request_payload,
                    detect_codex_cli_credentials,
                    get_codex_request_headers,
                    normalize_codex_config,
                    parse_codex_sse_event,
                    resolve_codex_request_url,
                )

                cfg = normalize_codex_config(getattr(self.config, "codex", {}))
                cred = detect_codex_cli_credentials()
                if cred.get("found"):
                    self.api_key = str(cred.get("api_key", "")).strip()
                if not self.api_key:
                    raise ValueError("Codex CLI credentials were not found. Please run /codex login first.")
                request_url = resolve_codex_request_url(self.base_url, self.endpoint or cfg.get("endpoint", ""))
                payload = build_codex_request_payload(
                    model_name=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    reasoning_effort=self.thinking_mode or cfg.get("reasoning_effort", "medium"),
                    stream=True,
                )
                headers = get_codex_request_headers(
                    api_key=self.api_key,
                    account_id=str(cred.get("account_id", "")).strip(),
                    auth_mode=str(cred.get("auth_mode", "")).strip(),
                    extra_headers=self.custom_headers,
                    stream=True,
                )
                parse_events = lambda data: parse_codex_sse_event(data, parser_state)[0]

            effective_timeout = self._resolve_provider_timeout()
            try:
                response = make_api_request_with_retry(
                    url=request_url,
                    headers=headers,
                    payload=payload,
                    max_retries=self.api_max_retries,
                    initial_backoff=self.api_initial_backoff,
                    stream=True,
                    timeout=effective_timeout,
                )
            except requests.RequestException as e:
                logger.error(f"Streaming API request failed for {provider_name}: {e}")
                raise

            collected_content = ""
            collected_tool_calls: List[Dict[str, Any]] = []
            finish_reason = None
            thinking_started = False
            stream_buffer = ""
            token_to_hide = "//END//"

            for data_str in self._iter_sse_data_strings(response):
                if provider_name == "codex":
                    from ..codex import parse_codex_sse_event

                    events, parser_state = parse_codex_sse_event(data_str, parser_state)
                else:
                    events = parse_events(data_str)

                for event in events:
                    event_type = str(event.get("type", "")).strip().lower()

                    if event_type == "reasoning":
                        reasoning_content = str(event.get("text", "") or "")
                        if reasoning_content:
                            if not thinking_started:
                                yield THINKING_START_MARKER
                                thinking_started = True
                            yield reasoning_content
                        continue

                    if event_type == "content":
                        content = str(event.get("text", "") or "")
                        if not content:
                            continue

                        if thinking_started:
                            yield THINKING_END_MARKER
                            thinking_started = False

                        collected_content += content
                        stream_buffer += content

                        if token_to_hide in stream_buffer:
                            parts = stream_buffer.split(token_to_hide)
                            if parts[0]:
                                yield parts[0]
                            stream_buffer = "".join(parts[1:])

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
                            if stream_buffer:
                                yield stream_buffer
                            stream_buffer = ""
                        continue

                    if event_type == "tool_call":
                        index = int(event.get("index", 0) or 0)
                        tool_call = self._ensure_stream_tool_call(collected_tool_calls, index)
                        tool_call["id"] = str(event.get("id", "")).strip() or tool_call["id"]
                        tool_call["function"]["name"] = str(event.get("name", "")).strip() or tool_call["function"]["name"]
                        tool_call["function"]["arguments"] = str(event.get("arguments", "") or "")
                        continue

                    if event_type == "tool_call_start":
                        index = int(event.get("index", 0) or 0)
                        tool_call = self._ensure_stream_tool_call(collected_tool_calls, index)
                        tool_call["id"] = str(event.get("id", "")).strip() or tool_call["id"]
                        tool_call["function"]["name"] = str(event.get("name", "")).strip() or tool_call["function"]["name"]
                        continue

                    if event_type == "tool_call_args":
                        index = int(event.get("index", 0) or 0)
                        tool_call = self._ensure_stream_tool_call(collected_tool_calls, index)
                        tool_call["function"]["arguments"] += str(event.get("arguments", "") or "")
                        continue

                    if event_type == "finish":
                        finish_reason = str(event.get("reason", "") or "") or finish_reason

            if thinking_started:
                yield THINKING_END_MARKER

            if stream_buffer and token_to_hide not in stream_buffer:
                yield stream_buffer

            if collected_tool_calls:
                _sanitize_tool_calls(collected_tool_calls)
                assistant_message = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls,
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)

                for tool_call in collected_tool_calls:
                    yield from self._stream_execute_tool_call(
                        tool_call,
                        messages,
                        session_id=session_id,
                    )

                continuation_count = 0
                continue

            if collected_content:
                clean_content = collected_content.replace("//END//", "").strip()
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": clean_content,
                    }
                )

                if finish_reason in ("stop", "end_turn", "end", None) or "//END//" in collected_content:
                    break

                continuation_count += 1
                if continuation_count >= max_continuations:
                    break

                messages = _sanitize_messages_for_relay(self._build_messages())
                continue

            break

    def _process_non_streaming_native_provider(self, provider_name: str, session_id: str = "default") -> str:
        """Fallback non-streaming path for native providers via streaming aggregation."""
        chunks: List[str] = []
        for chunk in self._process_streaming_native_provider(provider_name=provider_name, session_id=session_id):
            if chunk in (THINKING_START_MARKER, THINKING_END_MARKER):
                continue
            chunks.append(chunk)
        return "".join(chunks)

    def _openai_extra_body_for_thinking(self) -> Optional[Dict[str, Any]]:
        """Build `extra_body` (OpenAI SDK) to enable/disable thinking for compatible models.

        Rules:
        - If `thinking_mode` is explicitly set to 'true', return chat_template_kwargs enabling thinking.
        - If `thinking_mode` is 'false', return None (do not send thinking flags).
        - If `thinking_mode` is unset, detect model suffix like "model(thinking)" and enable thinking for
          recognized suffixes (auto, low, medium, high, xhigh, minimal, digits).
        - For GLM-family models include `clear_thinking: False` when enabling thinking.
        """
        # Explicit override from config
        if isinstance(self.thinking_mode, str) and self.thinking_mode.lower() in ("true", "false"):
            if self.thinking_mode.lower() == "false":
                return None
            enable_thinking = True
        else:
            # Derive from model name suffix if present
            model_name = str(self.model or "").strip()
            enable_thinking = False
            if "(" in model_name and ")" in model_name:
                base_model = model_name.split("(", 1)[0].strip()
                suffix = model_name.split("(", 1)[1].split(")", 1)[0].strip().lower()
                thinking_suffixes = {"auto", "low", "medium", "high", "xhigh", "minimal"}
                if suffix in thinking_suffixes or suffix.isdigit():
                    enable_thinking = True
                elif suffix in {"none", "0"}:
                    return None
            else:
                # No explicit hint; do not enable thinking by default
                return None

        if not enable_thinking:
            return None

        chat_kwargs: Dict[str, Any] = {"enable_thinking": True, "thinking": True}
        if "glm" in (self.model or "").lower():
            # GLM variants prefer clear_thinking=False per proxy/iFlow logic
            chat_kwargs["clear_thinking"] = False

        return {"chat_template_kwargs": chat_kwargs}
    
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
            if self._should_use_openai_http_fallback():
                yield from self._process_streaming_openai_http_fallback(session_id=session_id)
            else:
                yield from self._process_streaming_openai_sdk(session_id=session_id)
        elif self.provider == "request":
            yield from self._process_streaming_request(session_id=session_id)
        elif self.provider == "anthropic":
            yield from self._process_streaming_anthropic(session_id=session_id)
        elif self.provider == "gemini-cli":
            yield from self._process_streaming_native_provider("gemini-cli", session_id=session_id)
        elif self.provider == "codex":
            yield from self._process_streaming_native_provider("codex", session_id=session_id)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _process_streaming_openai_sdk(self, session_id: str = "default") -> Generator[str, None, None]:
        """Process with streaming response using OpenAI SDK"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        max_continuations = 3  # Safety limit to prevent infinite loops
        continuation_count = 0
        
        while True:
            # For OpenAI-compatible SDK calls, include thinking flags via extra_body when applicable
            extra_body = self._openai_extra_body_for_thinking()
            model_for_sdk = self.model
            if extra_body is not None and isinstance(model_for_sdk, str) and "(" in model_for_sdk and ")" in model_for_sdk:
                # Strip depth suffix for ordinary SDK calls — only send boolean thinking
                model_for_sdk = model_for_sdk.split("(", 1)[0].strip()
            if extra_body is not None:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
                    messages=messages,
                    tools=tools if tools else None,
                    stream=True,
                    extra_body=extra_body
                )
            else:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
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
                # Sanitize tool-call arguments before storing them in messages
                _sanitize_tool_calls(collected_tool_calls)
                assistant_message = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                # Execute tools
                for tool_call in collected_tool_calls:
                    yield from self._stream_execute_tool_call(
                        tool_call,
                        messages,
                        session_id=session_id,
                    )
                
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
            # For iFlow direct API streaming we increase the read timeout because responses
            # can be long-running (large content / SSE). Respect user-configured
            # api_timeout but prefer any configured iFlow-specific timeout.
            effective_timeout = self._resolve_provider_timeout()
            try:
                response = make_api_request_with_retry(
                    url=self.base_url,
                    headers=headers,
                    payload=payload,
                    max_retries=self.api_max_retries,
                    initial_backoff=self.api_initial_backoff,
                    stream=True,
                    timeout=effective_timeout
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
                byte_decoder = codecs.getincrementaldecoder('utf-8')()
                line_buffer = ""

                for chunk in response.iter_content(chunk_size=1024):
                    if not chunk:
                        continue

                    # Decode bytes incrementally to avoid splitting multi-byte UTF-8 characters
                    try:
                        text_part = byte_decoder.decode(chunk)
                    except Exception:
                        # Fallback to best-effort replacement if decoding fails
                        text_part = chunk.decode('utf-8', errors='replace')

                    # Add decoded text to line buffer
                    line_buffer += text_part

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
                
                # Flush any buffered bytes in the incremental decoder to capture
                # partial multibyte characters that spanned chunk boundaries.
                try:
                    line_buffer += byte_decoder.decode(b'', final=True)
                except Exception:
                    # If flushing fails, continue with whatever text we already have
                    pass

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
                    
                    line_str = line.decode("utf-8", errors='replace')
                    
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
                # Sanitize streamed tool-call arguments before storing them
                _sanitize_tool_calls(collected_tool_calls)
                assistant_message = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": collected_tool_calls
                }
                self.messages.append(assistant_message)
                messages.append(assistant_message)
                
                # Execute tools
                for tool_call in collected_tool_calls:
                    yield from self._stream_execute_tool_call(
                        tool_call,
                        messages,
                        session_id=session_id,
                    )
                
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
                    # Sanitize tool args (defensive - block.input was json.dumps'ed above)
                    _sanitize_tool_calls(collected_tool_calls)
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
                        
                        args = parse_tool_arguments(tool_call["function"]["arguments"])
                        
                        self._check_tool_side_effects(tool_name, args)
                        
                        exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                        yield f"\n[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{rich_escape(exec_msg)}[/bold #e4b0ff]\n"
                        
                        result = self.tool_executor.execute(tool_name, args)
                        
                        if result.success:
                            output_preview = result.output.strip()
                            if output_preview:
                                preview_lines = output_preview.split('\n')
                                formatted_output = ""
                                for line in preview_lines:
                                    formatted_output += f"[#ba68c8]   │[/#ba68c8] [#e0e0e0]{rich_escape(line)}[/#e0e0e0]\n"
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
            if self._should_use_openai_http_fallback():
                return self._process_non_streaming_openai_http_fallback(session_id=session_id)
            return self._process_non_streaming_openai_sdk(session_id=session_id)
        elif self.provider == "request":
            return self._process_non_streaming_request(session_id=session_id)
        elif self.provider == "anthropic":
            return self._process_non_streaming_anthropic(session_id=session_id)
        elif self.provider == "gemini-cli":
            return self._process_non_streaming_native_provider("gemini-cli", session_id=session_id)
        elif self.provider == "codex":
            return self._process_non_streaming_native_provider("codex", session_id=session_id)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _process_non_streaming_openai_sdk(self, session_id: str = "default") -> str:
        """Process without streaming using OpenAI SDK"""
        messages = self._build_messages()
        tools = self.tool_executor.get_tool_schemas(mode=self.mode)
        
        all_content = []
        
        while True:
            # For OpenAI-compatible SDK calls, include thinking flags via extra_body when applicable
            extra_body = self._openai_extra_body_for_thinking()
            model_for_sdk = self.model
            if extra_body is not None and isinstance(model_for_sdk, str) and "(" in model_for_sdk and ")" in model_for_sdk:
                # Strip depth suffix for ordinary SDK calls — only send boolean thinking
                model_for_sdk = model_for_sdk.split("(", 1)[0].strip()
            if extra_body is not None:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
                    messages=messages,
                    tools=tools if tools else None,
                    stream=False,
                    extra_body=extra_body
                )
            else:
                response = self._client.chat.completions.create(
                    model=model_for_sdk,
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
                    
                    args = parse_tool_arguments(tool_call.function.arguments)
                    
                    # Check side effects
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{rich_escape(exec_msg)}[/bold #e4b0ff]")
                    
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
            # Increase timeout for iFlow direct API when necessary (long responses)
            effective_timeout = self._resolve_provider_timeout()
            try:
                response = make_api_request_with_retry(
                    url=self.base_url,
                    headers=headers,
                    payload=payload,
                    max_retries=self.api_max_retries,
                    initial_backoff=self.api_initial_backoff,
                    stream=False,
                    timeout=effective_timeout
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
                # Sanitize incoming tool-call argument strings before storing
                _sanitize_tool_calls(tool_calls)
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
                    
                    args = parse_tool_arguments(tool_call["function"]["arguments"])
                    
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{rich_escape(exec_msg)}[/bold #e4b0ff]")
                    
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
                # Sanitize tool args before adding to message history
                _sanitize_tool_calls(collected_tool_calls)
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
                    
                    args = parse_tool_arguments(tool_call["function"]["arguments"])
                    
                    self._check_tool_side_effects(tool_name, args)
                    
                    exec_msg = tool.get_execution_message(**args) if tool else f"Executing {tool_name}..."
                    all_content.append(f"[bold #ffb8d1]✧[/bold #ffb8d1] [bold #e4b0ff]{rich_escape(exec_msg)}[/bold #e4b0ff]")
                    
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
        """
        Check context usage and trigger appropriate action.
        
        - At 80% threshold: Trigger session rotation with working memory
        - At 60% threshold: Trigger in-session compression (optional)
        """
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
        
        # Check if we've exceeded 80% threshold - trigger session rotation
        rotation_threshold = max_tokens * 0.8
        if token_estimate >= rotation_threshold:
            self._handle_session_rotation(token_estimate, max_tokens)
            return
        
        # Check if we've exceeded 60% threshold - trigger in-session compression
        compression_threshold = max_tokens * 0.6
        if token_estimate >= compression_threshold:
            self._handle_in_session_compression(token_estimate, max_tokens)
    
    def _handle_session_rotation(self, current_tokens: int, max_tokens: int) -> None:
        """
        Handle session rotation at 80% threshold.
        
        Creates a new session with working memory injection.
        """
        session_manager = self.tool_executor.context.get('session_manager')
        
        if not session_manager:
            # Fallback to in-session compression if no session manager
            self._handle_in_session_compression(current_tokens, max_tokens)
            return
        
        # Generate working memory summary
        working_memory = session_manager.get_working_memory_summary()
        
        # Rotate to new session
        new_session = session_manager.rotate_session(
            working_memory=working_memory,
            reason=f"Token usage reached {current_tokens:,} / {max_tokens:,} ({current_tokens/max_tokens*100:.1f}%)"
        )
        
        # Clear current messages (new session starts fresh with working memory)
        self.messages.clear()
        
        # Add rotation notification
        rotation_note = {
            "role": "system",
            "content": (
                f"[Context Engine] Session rotated — new session created. "
                f"Previous context has been summarized and carried over. "
                f"Session ID: {new_session.id}"
            )
        }
        self.messages.append(rotation_note)
        
        print(f"\n[Context Engine] Session rotated — new session created. Previous context has been summarized and carried over.\n")
    
    def _handle_in_session_compression(self, current_tokens: int, max_tokens: int) -> None:
        """
        Handle in-session compression at 60% threshold.
        
        Compresses messages within the same session.
        """
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
                "content": f"[Context Engine: Session compressed from {current_tokens:,} to {self.get_token_estimate():,} tokens to maintain memory persistence]"
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
