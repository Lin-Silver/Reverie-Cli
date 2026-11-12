"""Stateless, tool-free auxiliary calls using the Agent's existing adapters."""

from __future__ import annotations

import time
from typing import Any


MAX_INPUT_CHARS = 60_000
MAX_OUTPUT_CHARS = 32_000
MAX_LONG_FORM_INPUT_CHARS = 160_000
MAX_LONG_FORM_OUTPUT_CHARS = 160_000


class IncompleteTextResponse(ValueError):
    """An incomplete response retained for diagnostics, never accepted as finished prose."""

    def __init__(self, message: str, partial_text: str):
        super().__init__(message)
        self.partial_text = partial_text


def complete_configured_text(config: Any, project_root: Any, system: str, user: str, max_tokens: int) -> str:
    """Use a captured runtime config without reconfiguring the conversation executor."""
    from .agent import ReverieAgent

    model = config.active_model
    if model is None:
        raise ValueError("Configure an active model before using WStyle review or extraction.")
    agent = ReverieAgent(model.base_url, model.api_key, model.model, project_root=project_root, config=config,
                          mode="writer", provider=model.provider, endpoint=model.endpoint,
                          thinking_mode=model.thinking_mode, custom_headers=model.custom_headers)
    try:
        return agent.complete_text_only(system, user, max_tokens=max_tokens)
    finally:
        client = getattr(agent, "client", None)
        if client is not None and callable(getattr(client, "close", None)):
            client.close()


def _bounded_payload(payload: dict, token_key: str, max_tokens: int) -> dict:
    from .agent import _strip_tooling_from_payload

    payload = _strip_tooling_from_payload(payload)
    payload[token_key] = min(int(payload.get(token_key) or max_tokens), max_tokens)
    extra = payload.get("extra_body")
    if isinstance(extra, dict):
        extra = _strip_tooling_from_payload(dict(extra))
        for key in ("max_tokens", "max_output_tokens", "max_completion_tokens"):
            if key in extra:
                extra[key] = min(int(extra[key]), max_tokens)
        payload["extra_body"] = extra
    thinking = payload.get("thinking")
    if isinstance(thinking, dict) and thinking.get("budget_tokens"):
        payload["thinking"] = {**thinking, "budget_tokens": min(int(thinking["budget_tokens"]), max_tokens - 1)}
    return payload


def _clean_text_content(text: str) -> tuple[str, bool]:
    from .agent import _StreamingTurnState

    lower = text.lower()
    close, opening = lower.find("</think>"), lower.find("<think>")
    if close >= 0 and (opening < 0 or close < opening):
        text = "<think>" + text
    state = _StreamingTurnState()
    state.add_content(text)
    state.flush()
    return state.cleaned_content(), bool(state.collected_thinking)


def _text_from_result(agent: Any, data: dict, *, anthropic: bool = False, responses: bool = False,
                      max_output_chars: int = MAX_OUTPUT_CHARS, response_trace: dict | None = None) -> str:
    from .agent import _coerce_text_fragments

    if anthropic:
        blocks = data.get("content") or []
        if any(block.get("type") in {"tool_use", "server_tool_use"} for block in blocks):
            raise ValueError("Auxiliary model returned a tool call; nothing was executed.")
        text = "".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        if data.get("stop_reason") == "max_tokens":
            raise IncompleteTextResponse("Auxiliary model output reached its token limit; no complete text was accepted.", text)
    elif responses:
        if any(item.get("type") not in {"message", "reasoning"} for item in data.get("output", [])):
            raise ValueError("Auxiliary model returned a non-text action; nothing was executed.")
        if data.get("status") in {"incomplete", "failed", "cancelled"}:
            partial = "".join(_coerce_text_fragments(item.get("content")) for item in data.get("output", []) if item.get("type") == "message")
            raise IncompleteTextResponse("Auxiliary model did not complete its bounded response.", partial)
        state, _ = agent._responses_result_state(data)
        text = state.cleaned_content()
    else:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        if message.get("tool_calls") or message.get("function_call"):
            raise ValueError("Auxiliary model returned a tool call; nothing was executed.")
        text = _coerce_text_fragments(message.get("content"))
        if choice.get("finish_reason") == "length":
            raise IncompleteTextResponse("Auxiliary model output reached its token limit; no complete text was accepted.", text)
    if not text.strip() or len(text) > max_output_chars:
        raise ValueError("Auxiliary model returned empty or oversized text.")
    cleaned, separated = _clean_text_content(text)
    if response_trace is not None:
        response_trace.update(raw_text=text, separated_reasoning=separated,
                              usage={key: value for key, value in (data.get("usage") or {}).items()
                                     if key in {"input_tokens", "output_tokens", "prompt_tokens", "completion_tokens", "total_tokens"} and type(value) is int})
    if not cleaned:
        raise ValueError("Auxiliary model returned reasoning without completed text.")
    return cleaned


def complete_text_only(agent: Any, system: str, user: str, *, max_tokens: int, long_form: bool = False,
                       response_trace: dict | None = None) -> str:
    """Send only supplied text. No executor, persistence, automatic repair or retry."""
    from .agent import (_invoke_system_curl, make_api_request_with_retry,
                        normalize_proxy_url, requests_proxy_dict)

    if not isinstance(system, str) or not isinstance(user, str) or not system.strip() or not user.strip():
        raise ValueError("Auxiliary model calls require nonempty system and user text.")
    input_limit = MAX_LONG_FORM_INPUT_CHARS if long_form else MAX_INPUT_CHARS
    output_limit = MAX_LONG_FORM_OUTPUT_CHARS if long_form else MAX_OUTPUT_CHARS
    if not 256 <= max_tokens <= (65_536 if long_form else 8192) or len(system) + len(user) > input_limit:
        raise ValueError("Auxiliary model input or output budget exceeds its limit.")
    upper_bound = len((system + user).encode("utf-8")) + max_tokens + 256
    context_limit = int(getattr(agent.config, "max_context_tokens", 128_000) or 128_000)
    model_limit = getattr(getattr(agent.config, "active_model", None), "max_context_tokens", None)
    if model_limit:
        context_limit = min(context_limit, int(model_limit))
    if upper_bound > context_limit:
        raise ValueError("Auxiliary input exceeds the conservative model context budget; select a smaller excerpt.")
    timeout = max(1, min(300 if long_form else 60, agent._resolve_provider_timeout()))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    provider = agent.provider
    if provider in {"codex", "gemini"}:
        return _complete_native(agent, messages, max_tokens=max_tokens, timeout=timeout, max_output_chars=output_limit,
                                response_trace=response_trace)
    responses = provider == "openai-responses" or provider == "curl" and agent._curl_uses_responses()
    if responses:
        payload = agent._build_openai_responses_payload(stream=False, messages=messages, tools=[])
        token_key = "max_output_tokens"
    elif provider == "anthropic":
        payload = {"model": agent.model, "system": system, "messages": messages[1:], "stream": False,
                   "max_tokens": max_tokens}
        payload = agent._apply_custom_provider_anthropic_options(agent._apply_sensenova_anthropic_options(payload))
        if agent._is_active_model_source("opencode"):
            from ..opencode import build_opencode_request_headers_from_config

            payload["extra_headers"] = build_opencode_request_headers_from_config(getattr(agent.config, "opencode", {}))
        token_key = "max_tokens"
    else:
        payload = agent._build_openai_chat_completion_kwargs(messages=messages, tools=[], stream=False)
        if provider in {"request", "curl"} or agent._should_use_openai_http_fallback():
            payload = agent._prepare_request_payload(payload)
            extra = payload.pop("extra_body", None)
            if isinstance(extra, dict):
                payload.update(extra)
        token_key = "max_completion_tokens" if str(agent.model).startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")) and provider == "openai-chat" else "max_tokens"
        if token_key != "max_tokens":
            payload.pop("max_tokens", None)
    payload = _bounded_payload(payload, token_key, max_tokens)
    if provider in {"request", "curl"} or provider == "openai-chat" and agent._should_use_openai_http_fallback():
        headers = agent._build_request_headers(stream=False)
        if provider == "curl":
            response = _invoke_system_curl(url=agent._resolve_curl_url(), headers=headers, payload=payload, stream=False,
                                          timeout=timeout, proxy=normalize_proxy_url(getattr(agent.config, "api_proxy", "")) or None)
        else:
            url = agent.base_url if provider == "request" else agent._resolve_openai_request_url()
            proxy = normalize_proxy_url(getattr(agent.config, "api_proxy", ""))
            response = make_api_request_with_retry(url=url, headers=headers, payload=payload, stream=False,
                                                  timeout=timeout, max_retries=0,
                                                  proxies=requests_proxy_dict(proxy) if proxy else None)
        try:
            data = response.json()
        finally:
            agent._close_stream_response(response)
    else:
        client = agent._ensure_client().with_options(timeout=timeout, max_retries=0)
        if provider == "anthropic":
            result = client.messages.create(**payload)
        elif responses:
            result = client.responses.create(**payload)
        elif provider == "openai-chat":
            result = client.chat.completions.create(**payload)
        else:
            raise ValueError(f"Unknown auxiliary model provider: {provider}")
        data = result.model_dump()
    return _text_from_result(agent, data, anthropic=provider == "anthropic", responses=responses,
                             max_output_chars=output_limit, response_trace=response_trace)


def _complete_native(agent: Any, messages: list[dict], *, max_tokens: int, timeout: int, max_output_chars: int,
                     response_trace: dict | None = None) -> str:
    """Native streaming adapters have a local text/deadline cap in addition to the request budget."""
    from .agent import make_api_request_with_retry, normalize_proxy_url, requests_proxy_dict

    deadline = time.monotonic() + timeout
    chunks: list[str] = []
    size = 0
    cap = min(max_output_chars, max_tokens * 4)
    if agent.provider == "gemini":
        from ..gemini import gemini_request, iter_gemini_events

        stream = iter_gemini_events(agent._ensure_client(), agent.model,
                                   gemini_request(messages, max_tokens=max_tokens, thinking=agent.thinking_mode))
        usage = {}
        try:
            for event in stream:
                if event["type"] == "tool_call":
                    raise ValueError("Auxiliary model returned a tool call; nothing was executed.")
                if event["type"] == "usage":
                    usage.update(event["usage"])
                if event["type"] == "finish" and event["reason"] != "stop":
                    raise IncompleteTextResponse("Auxiliary model output reached its token limit; no complete text was accepted.", "".join(chunks))
                if event["type"] != "content":
                    continue
                chunk = event["text"]
                size += len(chunk)
                if size > cap or time.monotonic() > deadline:
                    raise ValueError("Native auxiliary response exceeded its local output/time limit.")
                chunks.append(chunk)
        finally:
            stream.close()
        text = "".join(chunks)
        if response_trace is not None:
            response_trace["usage"] = usage
    else:
        from ..codex import (build_codex_request_payload, get_codex_request_headers, normalize_codex_config,
                             parse_codex_sse_event, resolve_codex_credentials, resolve_codex_request_url,
                             is_codex_api_url)

        cfg = normalize_codex_config(getattr(agent.config, "codex", {}))
        url = resolve_codex_request_url(agent.base_url, agent.endpoint or cfg.get("endpoint", ""))
        credentials = resolve_codex_credentials(cfg, request_url=url)
        if not credentials.get("found"):
            raise ValueError("Configure Codex credentials before using auxiliary model commands.")
        payload = build_codex_request_payload(model_name=agent.model, messages=messages, tools=None,
                                             reasoning_effort=agent.thinking_mode or cfg.get("reasoning_effort"), stream=True)
        if not is_codex_api_url(url):
            payload["max_output_tokens"] = max_tokens
        headers = get_codex_request_headers(api_key=credentials["api_key"], account_id=credentials.get("account_id", ""),
                                           auth_mode=credentials.get("auth_mode", ""), extra_headers=agent.custom_headers,
                                           stream=True, request_url=url)
        proxy = normalize_proxy_url(getattr(agent.config, "api_proxy", ""))
        response = make_api_request_with_retry(url=url, headers=headers, payload=payload, stream=True,
                                              timeout=timeout, max_retries=0,
                                              proxies=requests_proxy_dict(proxy) if proxy else None)
        state = None
        completed = False
        try:
            for raw in agent._iter_sse_data_strings(response):
                if time.monotonic() > deadline:
                    raise ValueError("Native auxiliary response exceeded its time limit.")
                events, state = parse_codex_sse_event(raw, state)
                for event in events:
                    if event.get("type", "").startswith("tool"):
                        raise ValueError("Auxiliary model returned a tool call; nothing was executed.")
                    if event.get("type") == "content":
                        chunk = event.get("text", "")
                        size += len(chunk)
                        if size > cap:
                            raise ValueError("Native auxiliary response exceeded its local output limit.")
                        chunks.append(chunk)
                    if event.get("type") == "error":
                        raise ValueError(event.get("message", "Native auxiliary request failed."))
                    if event.get("type") == "finish" and event.get("reason") != "stop":
                        raise ValueError("Native auxiliary response did not finish as text.")
                    if event.get("type") == "finish":
                        completed = True
            if not completed:
                raise ValueError("Native auxiliary response ended before completion.")
        finally:
            agent._close_stream_response(response)
        text = "".join(chunks)
    if not text.strip():
        raise ValueError("Auxiliary model returned empty text.")
    cleaned, separated = _clean_text_content(text)
    if response_trace is not None:
        response_trace.update(raw_text=text, separated_reasoning=separated)
    if not cleaned:
        raise ValueError("Auxiliary model returned reasoning without completed text.")
    return cleaned
