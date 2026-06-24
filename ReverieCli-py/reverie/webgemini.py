"""WebGemini anonymous Gemini Web source helpers."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple
from urllib.parse import urlencode

from .proxy import resolve_proxy_url_with_source


WEBGEMINI_DEFAULT_MODEL_ID = "gemini-3.5-flash-thinking"
WEBGEMINI_DEFAULT_MODEL_DISPLAY_NAME = "Gemini 3.5 Flash Thinking"
WEBGEMINI_DEFAULT_GEMINI_BL = "boq_assistant-bard-web-server_20260525.09_p0"
WEBGEMINI_DEFAULT_TIMEOUT = 180
WEBGEMINI_DEFAULT_RETRY_ATTEMPTS = 2
WEBGEMINI_DEFAULT_RETRY_DELAY = 1
WEBGEMINI_DEFAULT_CONTEXT_TOKENS = 128_000
WEBGEMINI_DEFAULT_MAX_OUTPUT_TOKENS = 20_000
WEBGEMINI_ORIGIN = "https://gemini.google.com"


def _webgemini_model(
    model_id: str,
    display_name: str,
    description: str,
    *,
    mode: int,
    think: int,
    max_output_tokens: int = 12_000,
    requires_cookie_for_real_routing: bool = False,
) -> Dict[str, Any]:
    return {
        "id": model_id,
        "display_name": display_name,
        "description": description,
        "transport": "webgemini",
        "context_length": WEBGEMINI_DEFAULT_CONTEXT_TOKENS,
        "max_output_tokens": int(max_output_tokens),
        "mode": int(mode),
        "think": int(think),
        "vision": False,
        "tool_calling": True,
        "requires_cookie_for_real_routing": bool(requires_cookie_for_real_routing),
    }


_WEBGEMINI_MODEL_CATALOG: List[Dict[str, Any]] = [
    _webgemini_model(
        "gemini-3.5-flash",
        "Gemini 3.5 Flash",
        "Fast anonymous Gemini Web mode.",
        mode=1,
        think=4,
        max_output_tokens=12_000,
    ),
    _webgemini_model(
        "gemini-3.5-flash-thinking",
        "Gemini 3.5 Flash Thinking",
        "Deep-thinking Gemini Web mode with the longest anonymous text output.",
        mode=2,
        think=0,
        max_output_tokens=20_000,
    ),
    _webgemini_model(
        "gemini-3.5-flash-thinking-lite",
        "Gemini 3.5 Flash Thinking Lite",
        "Adaptive-thinking Gemini Web mode.",
        mode=5,
        think=0,
        max_output_tokens=15_000,
    ),
    _webgemini_model(
        "gemini-3.1-pro",
        "Gemini 3.1 Pro",
        "Gemini Web Pro preference. Anonymous requests may be routed to Flash upstream.",
        mode=3,
        think=4,
        max_output_tokens=12_000,
        requires_cookie_for_real_routing=True,
    ),
    _webgemini_model(
        "gemini-auto",
        "Gemini Auto",
        "Gemini Web automatic model selection mode.",
        mode=4,
        think=4,
        max_output_tokens=12_000,
    ),
    _webgemini_model(
        "gemini-flash-lite",
        "Gemini Flash Lite",
        "Lightweight fast Gemini Web mode.",
        mode=6,
        think=4,
        max_output_tokens=10_000,
    ),
]

_WEBGEMINI_MODEL_METADATA = {
    str(item["id"]).strip().lower(): dict(item) for item in _WEBGEMINI_MODEL_CATALOG
}


def default_webgemini_config() -> Dict[str, Any]:
    """Default WebGemini provider config stored in config.json."""
    return {
        "enabled": True,
        "selected_model_id": WEBGEMINI_DEFAULT_MODEL_ID,
        "selected_model_display_name": WEBGEMINI_DEFAULT_MODEL_DISPLAY_NAME,
        "gemini_bl": WEBGEMINI_DEFAULT_GEMINI_BL,
        "auth_user": "",
        "xsrf_token": "",
        "cookie": "",
        "cookie_file": "",
        "proxy": "",
        "timeout": WEBGEMINI_DEFAULT_TIMEOUT,
        "retry_attempts": WEBGEMINI_DEFAULT_RETRY_ATTEMPTS,
        "retry_delay": WEBGEMINI_DEFAULT_RETRY_DELAY,
        "max_context_tokens": WEBGEMINI_DEFAULT_CONTEXT_TOKENS,
    }


def get_webgemini_model_catalog() -> List[Dict[str, Any]]:
    """Return Gemini Web model modes supported by the anonymous transport."""
    return [dict(item) for item in _WEBGEMINI_MODEL_CATALOG]


def get_webgemini_model_metadata(model_id: Any) -> Optional[Dict[str, Any]]:
    wanted = _strip_think_suffix(str(model_id or "").strip()).lower()
    if not wanted:
        return None
    found = _WEBGEMINI_MODEL_METADATA.get(wanted)
    return dict(found) if found else None


def resolve_webgemini_selected_model(webgemini_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    cfg = default_webgemini_config()
    if isinstance(webgemini_config, dict):
        cfg.update(webgemini_config)

    wanted = str(model_id or cfg.get("selected_model_id", WEBGEMINI_DEFAULT_MODEL_ID) or "").strip()
    matched = get_webgemini_model_metadata(wanted)
    if matched:
        return matched
    return get_webgemini_model_catalog()[0]


def normalize_webgemini_config(raw_webgemini: Any) -> Dict[str, Any]:
    """Normalize WebGemini config for persistence and runtime usage."""
    cfg = default_webgemini_config()
    if isinstance(raw_webgemini, dict):
        cfg.update(raw_webgemini)

    for key in ("selected_model_id", "selected_model_display_name", "gemini_bl", "auth_user", "xsrf_token", "cookie", "cookie_file", "proxy"):
        cfg[key] = str(cfg.get(key, "") or "").strip()

    if not cfg["gemini_bl"]:
        cfg["gemini_bl"] = WEBGEMINI_DEFAULT_GEMINI_BL

    for key, default_value in (
        ("timeout", WEBGEMINI_DEFAULT_TIMEOUT),
        ("retry_attempts", WEBGEMINI_DEFAULT_RETRY_ATTEMPTS),
        ("retry_delay", WEBGEMINI_DEFAULT_RETRY_DELAY),
        ("max_context_tokens", WEBGEMINI_DEFAULT_CONTEXT_TOKENS),
    ):
        try:
            value = int(cfg.get(key, default_value))
        except (TypeError, ValueError):
            value = default_value
        if value <= 0:
            value = default_value
        cfg[key] = value

    selected = resolve_webgemini_selected_model(cfg)
    if selected:
        cfg["selected_model_id"] = str(selected["id"])
        cfg["selected_model_display_name"] = str(selected["display_name"])
        cfg["max_context_tokens"] = int(selected.get("context_length") or WEBGEMINI_DEFAULT_CONTEXT_TOKENS)
    return cfg


def build_webgemini_runtime_model_data(webgemini_config: Any, model_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build runtime model config dict for agent initialization."""
    cfg = normalize_webgemini_config(webgemini_config)
    if not cfg.get("enabled", True):
        return None
    selected = resolve_webgemini_selected_model(cfg, model_id=model_id)
    if not selected:
        return None
    return {
        "model": selected["id"],
        "model_display_name": selected["display_name"],
        "base_url": WEBGEMINI_ORIGIN,
        "api_key": "",
        "max_context_tokens": int(selected.get("context_length") or cfg.get("max_context_tokens", WEBGEMINI_DEFAULT_CONTEXT_TOKENS)),
        "provider": "webgemini",
        "supports_vision": False,
        "thinking_mode": None,
        "endpoint": "",
        "custom_headers": {},
        "vision": False,
    }


def _strip_think_suffix(model_name: str) -> str:
    return str(model_name or "").split("@think=", 1)[0].strip()


def _resolve_model_mode(model_name: str, webgemini_config: Any) -> Tuple[str, int, int]:
    raw_model = str(model_name or "").strip() or WEBGEMINI_DEFAULT_MODEL_ID
    think_override: Optional[int] = None
    if "@think=" in raw_model:
        raw_model, raw_think = raw_model.rsplit("@think=", 1)
        try:
            think_override = max(0, min(4, int(str(raw_think).strip())))
        except (TypeError, ValueError):
            think_override = None
    selected = resolve_webgemini_selected_model(webgemini_config, model_id=raw_model)
    if not selected:
        raise ValueError(f"Unknown WebGemini model: {model_name}")
    think = think_override if think_override is not None else int(selected.get("think", 4))
    return str(selected["id"]), int(selected.get("mode", 1)), think


def _load_cookie(cfg: Dict[str, Any]) -> Tuple[str, str]:
    cookie = str(cfg.get("cookie", "") or "").strip()
    cookie_file = str(cfg.get("cookie_file", "") or "").strip()
    if not cookie and cookie_file:
        path = Path(cookie_file).expanduser()
        if path.exists() and path.is_file():
            try:
                cookie = path.read_text(encoding="utf-8").strip()
            except Exception:
                cookie = ""
    if not cookie:
        return "", ""
    if cookie.startswith("{"):
        try:
            data = json.loads(cookie)
            return str(data.get("cookie", "") or "").strip(), str(data.get("sapisid", "") or "").strip()
        except Exception:
            pass
    pairs: Dict[str, str] = {}
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        pairs[key.strip()] = value.strip()
    return cookie, pairs.get("SAPISID", "")


def _make_sapisidhash(sapisid: str) -> str:
    timestamp = int(time.time())
    digest = hashlib.sha1(f"{timestamp} {sapisid} {WEBGEMINI_ORIGIN}".encode("utf-8")).hexdigest()
    return f"SAPISIDHASH {timestamp}_{digest}"


def _account_prefix(cfg: Dict[str, Any]) -> str:
    auth_user = str(cfg.get("auth_user", "") or "").strip()
    return f"/u/{auth_user}" if auth_user else ""


def _build_stream_generate_request(prompt: str, model_mode: int, think_mode: int, cfg: Dict[str, Any]) -> Tuple[str, Dict[str, str], str]:
    inner: List[Any] = [None] * 102
    inner[0] = [prompt, 0, None, None, None, None, 0]
    inner[1] = ["en"]
    inner[2] = ["", "", "", None, None, None, None, None, None, ""]
    inner[6] = [0]
    inner[7] = 1
    inner[10] = 1
    inner[11] = 0
    inner[17] = [[think_mode]]
    inner[18] = 0
    inner[27] = 1
    inner[30] = [4]
    inner[41] = [2]
    inner[53] = 0
    inner[59] = str(uuid.uuid4())
    inner[61] = []
    inner[68] = 1
    inner[79] = model_mode

    params: Dict[str, str] = {"f.req": json.dumps([None, json.dumps(inner)])}
    xsrf = str(cfg.get("xsrf_token", "") or "").strip()
    if xsrf:
        params["at"] = xsrf
    prefix = _account_prefix(cfg)
    reqid = int(time.time()) % 1_000_000
    url = (
        f"{WEBGEMINI_ORIGIN}{prefix}/_/BardChatUi/data/"
        "assistant.lamda.BardFrontendService/StreamGenerate"
        f"?bl={cfg.get('gemini_bl') or WEBGEMINI_DEFAULT_GEMINI_BL}&hl=en&_reqid={reqid}&rt=c"
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": WEBGEMINI_ORIGIN,
        "Referer": f"{WEBGEMINI_ORIGIN}{prefix}/app",
        "X-Same-Domain": "1",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if prefix:
        headers["X-Goog-AuthUser"] = str(cfg.get("auth_user", "") or "").strip()
    cookie, sapisid = _load_cookie(cfg)
    if cookie:
        headers["Cookie"] = cookie
    if sapisid:
        headers["Authorization"] = _make_sapisidhash(sapisid)
    return url, headers, urlencode(params)


def clean_webgemini_text(text: str) -> str:
    cleaned = re.sub(
        r"```(?:python|javascript|text)\\?code_(?:reference|stdout)&code_event_index=\d+\n.*?```\n?",
        "",
        str(text or ""),
        flags=re.DOTALL,
    )
    cleaned = re.sub(r"http://googleusercontent\.com/card_content/\d+\n?", "", cleaned)
    return cleaned.strip()


def resolve_webgemini_proxy(webgemini_config: Any) -> Tuple[str, str]:
    """Return the proxy URL/source WebGemini will force onto HTTP clients."""
    cfg = normalize_webgemini_config(webgemini_config)
    return resolve_proxy_url_with_source(cfg.get("proxy", ""), prefer_system=True)


def _webgemini_httpx_client(cfg: Dict[str, Any]):
    import httpx

    proxy, _source = resolve_webgemini_proxy(cfg)
    timeout = httpx.Timeout(
        timeout=float(cfg.get("timeout", WEBGEMINI_DEFAULT_TIMEOUT) or WEBGEMINI_DEFAULT_TIMEOUT),
        connect=10.0,
    )
    transport = httpx.HTTPTransport(proxy=proxy) if proxy else httpx.HTTPTransport()
    return httpx.Client(transport=transport, timeout=timeout, verify=True, trust_env=False)


def _extract_texts_from_web_line(line: str) -> List[str]:
    if '"wrb.fr"' not in line:
        return []
    try:
        arr = json.loads(line)
        inner_str = arr[0][2]
        if not inner_str:
            return []
        inner = json.loads(inner_str)
    except (json.JSONDecodeError, IndexError, TypeError):
        return []

    texts: List[str] = []
    if isinstance(inner, list) and len(inner) > 4 and inner[4]:
        for part in inner[4]:
            if isinstance(part, list) and len(part) > 1 and isinstance(part[1], list):
                texts.extend(t for t in part[1] if isinstance(t, str) and t)
    return texts


def extract_webgemini_response_text(raw: str) -> str:
    error_match = re.search(r"BardErrorInfo\s*\[(\d+)\]", str(raw or ""))
    if error_match:
        raise RuntimeError(f"Gemini upstream rejected request: BardErrorInfo [{error_match.group(1)}]")
    texts: List[str] = []
    for line in str(raw or "").splitlines():
        texts.extend(_extract_texts_from_web_line(line))
    for text in reversed(texts):
        if str(text or "").strip():
            return clean_webgemini_text(text).strip()
    return ""


def messages_to_webgemini_prompt(messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> str:
    """Convert chat messages to the single-prompt shape Gemini Web accepts."""
    parts: List[str] = []
    if tools:
        tool_defs: List[Dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function", tool) if tool.get("type") == "function" else tool
            tool_defs.append(
                {
                    "name": fn.get("name", tool.get("name", "")),
                    "description": fn.get("description", tool.get("description", "")),
                    "parameters": fn.get("parameters", tool.get("parameters", {})),
                }
            )
        if tool_defs:
            parts.append(
                "[System instruction]: You have access to tools. "
                "When a tool is required, respond with exactly one or more blocks in this form:\n"
                '```tool_call\n{"name":"function_name","arguments":{}}\n```\n'
                "Do not use tool_call blocks unless you need a tool.\n\n"
                f"Available tools:\n{json.dumps(tool_defs, ensure_ascii=False, indent=2)}"
            )

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user") or "user").strip().lower()
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(part.get("text", "") or part.get("content", "") or "")
                for part in content
                if isinstance(part, dict) and str(part.get("type", "text")) in ("text", "input_text")
            )
        content_text = str(content or "").strip()
        if role == "system":
            parts.append(f"[System instruction]: {content_text}")
        elif role == "assistant":
            parts.append(f"[Assistant]: {content_text}")
        elif role == "tool":
            parts.append(f"[Tool result for {msg.get('name', '')}]: {content_text}")
        else:
            parts.append(content_text)
    return "\n\n".join(part for part in parts if part)


def parse_webgemini_tool_calls(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    tool_calls: List[Dict[str, Any]] = []
    pattern = r"```tool_call\s*\n(.*?)\n```"
    for match in re.findall(pattern, str(text or ""), flags=re.DOTALL):
        try:
            data = json.loads(match.strip())
        except json.JSONDecodeError:
            continue
        name = str(data.get("name", "") or "").strip()
        if not name:
            continue
        arguments = data.get("arguments", {})
        tool_calls.append(
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments if isinstance(arguments, dict) else {}, ensure_ascii=False),
                },
            }
        )
    clean_text = re.sub(pattern, "", str(text or ""), flags=re.DOTALL).strip()
    return clean_text, tool_calls


def iter_webgemini_text_deltas(
    *,
    messages: List[Dict[str, Any]],
    model: str,
    webgemini_config: Any,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Generator[str, None, None]:
    """Yield text deltas from Gemini Web StreamGenerate."""
    cfg = normalize_webgemini_config(webgemini_config)
    prompt = messages_to_webgemini_prompt(messages, tools=None)
    if not prompt.strip():
        raise ValueError("WebGemini prompt is empty")
    _, model_mode, think_mode = _resolve_model_mode(model, cfg)
    url, headers, body = _build_stream_generate_request(prompt, model_mode, think_mode, cfg)

    attempts = max(1, int(cfg.get("retry_attempts", WEBGEMINI_DEFAULT_RETRY_ATTEMPTS) or WEBGEMINI_DEFAULT_RETRY_ATTEMPTS))
    last_error: Optional[BaseException] = None
    for attempt in range(attempts):
        previous_text = ""
        try:
            with _webgemini_httpx_client(cfg) as client:
                with client.stream("POST", url, content=body, headers=headers) as response:
                    response.raise_for_status()
                    buffer = ""
                    for chunk in response.iter_text():
                        buffer += str(chunk or "")
                        error_match = re.search(r"BardErrorInfo\s*\[(\d+)\]", buffer)
                        if error_match:
                            raise RuntimeError(f"Gemini upstream rejected request: BardErrorInfo [{error_match.group(1)}]")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            for text in _extract_texts_from_web_line(line):
                                if len(text) <= len(previous_text):
                                    continue
                                delta = clean_webgemini_text(text[len(previous_text):])
                                previous_text = text
                                if delta:
                                    yield delta
            return
        except Exception as exc:
            if previous_text:
                raise
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(max(0, int(cfg.get("retry_delay", WEBGEMINI_DEFAULT_RETRY_DELAY) or 0)))
    if last_error:
        raise last_error


def generate_webgemini_message(
    *,
    messages: List[Dict[str, Any]],
    model: str,
    webgemini_config: Any,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generate a full WebGemini message and parse optional tool calls."""
    cfg = normalize_webgemini_config(webgemini_config)
    prompt = messages_to_webgemini_prompt(messages, tools=tools)
    if not prompt.strip():
        raise ValueError("WebGemini prompt is empty")
    _, model_mode, think_mode = _resolve_model_mode(model, cfg)
    url, headers, body = _build_stream_generate_request(prompt, model_mode, think_mode, cfg)

    last_error: Optional[BaseException] = None
    text = ""
    attempts = max(1, int(cfg.get("retry_attempts", WEBGEMINI_DEFAULT_RETRY_ATTEMPTS) or WEBGEMINI_DEFAULT_RETRY_ATTEMPTS))
    for attempt in range(attempts):
        try:
            with _webgemini_httpx_client(cfg) as client:
                response = client.post(url, content=body, headers=headers)
                response.raise_for_status()
                text = extract_webgemini_response_text(response.text)
            if text:
                break
            proxy, source = resolve_webgemini_proxy(cfg)
            last_error = RuntimeError(
                f"Gemini Web response did not contain a text payload; proxy={proxy or 'direct'} ({source})"
            )
        except Exception as exc:
            last_error = exc
        if attempt < attempts - 1:
            time.sleep(max(0, int(cfg.get("retry_delay", WEBGEMINI_DEFAULT_RETRY_DELAY) or 0)))
    if not text and last_error and not isinstance(last_error, RuntimeError):
        raise last_error
    if tools:
        return parse_webgemini_tool_calls(text)
    return text, []


def mask_webgemini_cookie(cookie: str) -> str:
    value = str(cookie or "").strip()
    if not value:
        return "(not set)"
    return f"{value[:4]}...{value[-4:]}" if len(value) > 12 else "***"
