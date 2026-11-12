"""Gemini Developer API and compatible gateways through Google's Gen AI SDK."""

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from typing import Any, Dict, List
from urllib.parse import urlsplit

from .api_keys import normalize_api_key_env
from .diagnostics import report_suppressed_exception
from .model_catalog_cache import model_catalog_key, remember_model_catalog, remembered_model_catalog
from .provider_transport import check_cancel


GEMINI_DEFAULT_API_URL = "https://generativelanguage.googleapis.com"
GEMINI_DEFAULT_MODEL_ID = "gemini-3.8-flash"
_MODEL_CACHE: Dict[str, Dict[str, Any]] = {}


def gemini_environment_name() -> str:
    return next((name for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY") if os.getenv(name, "").strip()), "")


def default_gemini_config() -> Dict[str, Any]:
    return {
        "enabled": True, "api_key": "", "api_key_env": gemini_environment_name(),
        "api_url": GEMINI_DEFAULT_API_URL, "selected_model_id": GEMINI_DEFAULT_MODEL_ID,
        "selected_model_display_name": "Gemini 3.8 Flash", "timeout": 180,
        "max_context_tokens": 1_048_576, "max_tokens": 16_384,
    }


def normalize_gemini_config(raw: Any) -> Dict[str, Any]:
    cfg = default_gemini_config()
    if isinstance(raw, dict):
        cfg.update(raw)
    for key in ("api_key", "api_url", "selected_model_id", "selected_model_display_name"):
        cfg[key] = str(cfg.get(key) or "").strip()
    cfg["api_url"] = cfg["api_url"].rstrip("/") or GEMINI_DEFAULT_API_URL
    cfg["api_key_env"] = normalize_api_key_env(cfg.get("api_key_env"))
    if not cfg["api_key"] and not cfg["api_key_env"]:
        cfg["api_key_env"] = gemini_environment_name()
    for key, default in (("timeout", 180), ("max_context_tokens", 1_048_576), ("max_tokens", 16_384)):
        try:
            cfg[key] = max(1, int(cfg[key]))
        except (TypeError, ValueError):
            cfg[key] = default
    return cfg


def resolve_gemini_api_key(raw: Any) -> str:
    cfg = normalize_gemini_config(raw)
    return cfg["api_key"] or os.getenv(cfg["api_key_env"], "").strip()


def gemini_http_options(base_url: str, timeout: int, headers=None, http_client=None):
    from google.genai import types

    base = str(base_url or GEMINI_DEFAULT_API_URL).rstrip("/")
    match = re.search(r"/(v\d+(?:beta\d*|alpha\d*)?)$", base)
    version = match.group(1) if match else "v1beta"
    if match:
        base = base[:match.start()]
    return types.HttpOptions(base_url=base, api_version=version, timeout=timeout * 1000,
                             headers=headers or {}, httpx_client=http_client,
                             retry_options=types.HttpRetryOptions(attempts=1))


def create_gemini_client(base_url: str, api_key: str, timeout: int = 180, *, headers=None, http_client=None):
    from google import genai

    if not api_key:
        raise ValueError("Configure a Gemini API key or select GOOGLE_API_KEY / GEMINI_API_KEY.")
    return genai.Client(api_key=api_key, vertexai=False,
                        http_options=gemini_http_options(base_url, timeout, headers, http_client))


def fetch_gemini_models(base_url: str, api_key: str, timeout: int = 10, *, headers=None, proxy: str = "") -> List[Dict[str, Any]]:
    from .provider_transport import provider_client
    from .proxy import resolve_proxy_url

    proxy_url = None if not proxy and urlsplit(base_url).hostname in {"localhost", "127.0.0.1", "::1"} else resolve_proxy_url(proxy)
    http_client = provider_client(proxy=proxy_url, timeout=timeout)
    with create_gemini_client(base_url, api_key, timeout, headers=headers, http_client=http_client) as client:
        models = []
        for model in client.models.list():
            actions = model.supported_actions or []
            if actions and "generateContent" not in actions:
                continue
            model_id = str(model.name or "").removeprefix("models/")
            if not model_id:
                continue
            models.append({"id": model_id, "display_name": model.display_name or model_id,
                           "description": model.description or "", "transport": "gemini",
                           "context_length": model.input_token_limit,
                           "max_output_tokens": model.output_token_limit,
                           "vision": model_id.startswith("gemini-"), "tool_calling": True,
                           "catalog_source": "api"})
        return models


def get_gemini_model_catalog(raw: Any = None, *, fetch_live: bool = False, force_refresh: bool = False,
                            proxy: str = "") -> List[Dict[str, Any]]:
    cfg = normalize_gemini_config(raw)
    api_key = resolve_gemini_api_key(cfg)
    key = model_catalog_key(cfg["api_url"], api_key, "gemini")
    current = _MODEL_CACHE.get(key)
    if fetch_live and api_key and (force_refresh or not current or current["expires_at"] <= time.monotonic()):
        try:
            models = fetch_gemini_models(cfg["api_url"], api_key, proxy=proxy)
            current = {"key": key, "models": models, "expires_at": time.monotonic() + 300}
            _MODEL_CACHE[key] = current
            remember_model_catalog(raw, key, models)
            return models
        except Exception:
            report_suppressed_exception("fetch Gemini live model catalog")
    cached = remembered_model_catalog(cfg, key, current)
    if cached is not None:
        return cached
    return [{"id": cfg["selected_model_id"] or GEMINI_DEFAULT_MODEL_ID,
             "display_name": cfg["selected_model_display_name"] or cfg["selected_model_id"],
             "transport": "gemini", "context_length": cfg["max_context_tokens"],
             "max_output_tokens": cfg["max_tokens"], "vision": True, "tool_calling": True,
             "catalog_source": "builtin"}]


def build_gemini_runtime_model_data(raw: Any, model_id: str = "") -> Dict[str, Any] | None:
    cfg = normalize_gemini_config(raw)
    key = resolve_gemini_api_key(cfg)
    if not cfg["enabled"] or not key:
        return None
    wanted = model_id or cfg["selected_model_id"] or GEMINI_DEFAULT_MODEL_ID
    catalog = get_gemini_model_catalog(cfg)
    selected = next((item for item in catalog if item["id"] == wanted), None)
    if selected is None:
        if not catalog:
            return None
        selected = catalog[0]
        wanted = selected["id"]
    return {"model": wanted, "model_display_name": selected.get("display_name") or wanted,
            "base_url": cfg["api_url"], "api_key": key, "provider": "gemini",
            "max_context_tokens": selected.get("context_length") or cfg["max_context_tokens"],
            "supports_vision": True, "endpoint": "", "custom_headers": {}}


def gemini_request(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] | None = None,
                   *, max_tokens: int = 16_384, thinking: str = "") -> Dict[str, Any]:
    """Convert Reverie's canonical history, retaining function-call signatures."""
    from google.genai import types

    system = []
    contents = []
    names = {call.get("id"): call.get("function", {}).get("name", "")
             for message in messages for call in message.get("tool_calls", [])}
    for message in messages:
        role = message.get("role", "user")
        value = message.get("content") or ""
        if role == "system":
            system.append(str(value))
            continue
        parts = []
        if role == "tool":
            parts.append(types.Part(function_response=types.FunctionResponse(
                id=message.get("tool_call_id"), name=message.get("name") or names.get(message.get("tool_call_id")) or "tool",
                response={"result": value})))
        else:
            for block in value if isinstance(value, list) else ([{"type": "text", "text": str(value)}] if value else []):
                if block.get("type") in ("text", "input_text"):
                    parts.append(types.Part.from_text(text=str(block.get("text") or "")))
                elif block.get("type") == "image_url":
                    url = block.get("image_url") or {}
                    url = url.get("url", "") if isinstance(url, dict) else url
                    if url.startswith("data:"):
                        mime, data = url[5:].split(";base64,", 1)
                        parts.append(types.Part.from_bytes(data=base64.b64decode(data, validate=True), mime_type=mime))
                    else:
                        parts.append(types.Part.from_uri(file_uri=url, mime_type="image/jpeg"))
                elif block.get("type") == "input_audio":
                    audio = block.get("input_audio") or {}
                    fmt = audio.get("format", "wav")
                    parts.append(types.Part.from_bytes(data=base64.b64decode(audio.get("data", ""), validate=True),
                                                        mime_type="audio/mpeg" if fmt == "mp3" else "audio/wav"))
                else:
                    raise ValueError(f"Unsupported Gemini content block: {block.get('type')}")
            for call in message.get("tool_calls", []):
                fn = call.get("function") or {}
                args = fn.get("arguments") or "{}"
                part = types.Part(function_call=types.FunctionCall(id=call.get("id"), name=fn.get("name"),
                                       args=json.loads(args) if isinstance(args, str) else args))
                signature = call.get("thought_signature")
                if signature:
                    part.thought_signature = base64.b64decode(signature)
                parts.append(part)
        if parts:
            contents.append(types.Content(role="model" if role == "assistant" else "user", parts=parts))
    declarations = [types.FunctionDeclaration(name=tool["function"]["name"],
                    description=tool["function"].get("description"),
                    parameters_json_schema=tool["function"].get("parameters")) for tool in tools or []]
    config = types.GenerateContentConfig(system_instruction="\n\n".join(system) or None,
                max_output_tokens=max_tokens, tools=[types.Tool(function_declarations=declarations)] if declarations else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    # Leave model-specific thinking at Google's default unless explicitly selected.
    level = str(thinking or "").lower()
    if level in ("minimal", "low", "medium", "high"):
        config.thinking_config = types.ThinkingConfig(thinking_level=level.upper(), include_thoughts=True)
    return {"contents": contents, "config": config}


def iter_gemini_events(client, model: str, request: Dict[str, Any]):
    """Map SDK responses onto the Agent's canonical stream events."""
    stream = client.models.generate_content_stream(model=model.removeprefix("models/"), **request)
    completed = False
    saw_tool_call = False
    tool_index = 0
    try:
        for response in stream:
            check_cancel()
            if response.usage_metadata is not None:
                yield {"type": "usage", "usage": response.usage_metadata.model_dump(exclude_none=True)}
            for candidate in response.candidates or []:
                for part in (candidate.content.parts if candidate.content else []) or []:
                    if part.text:
                        yield {"type": "reasoning" if part.thought else "content", "text": part.text}
                    if part.function_call:
                        fn = part.function_call
                        call = {"type": "tool_call", "index": tool_index, "id": fn.id or f"call_{uuid.uuid4().hex}",
                                "name": fn.name, "arguments": json.dumps(fn.args or {}, ensure_ascii=False)}
                        if part.thought_signature:
                            call["thought_signature"] = base64.b64encode(part.thought_signature).decode("ascii")
                        yield call
                        tool_index += 1
                        saw_tool_call = True
                if candidate.finish_reason:
                    completed = True
                    reason = str(candidate.finish_reason.value)
                    if reason not in ("STOP", "MAX_TOKENS"):
                        raise ValueError(f"Gemini generation stopped: {reason}")
                    yield {"type": "finish", "reason": "length" if reason == "MAX_TOKENS" else "tool_calls" if saw_tool_call else "stop"}
        if not completed:
            raise ValueError("Gemini stream ended before a completion record.")
    finally:
        stream.close()
