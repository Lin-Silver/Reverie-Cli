"""Shared SSE helpers for provider and relay streaming."""

from __future__ import annotations

from typing import Generator
import logging


logger = logging.getLogger(__name__)

DEFAULT_SSE_CHUNK_SIZE = 16_384
_KNOWN_SSE_FIELDS = ("data:", "event:", "id:", "retry:")


def iter_sse_data_strings(response, *, chunk_size: int = DEFAULT_SSE_CHUNK_SIZE) -> Generator[str, None, None]:
    """
    Yield decoded SSE `data:` payloads from an HTTP streaming response.

    This helper is tolerant of:
    - standard SSE frames with one or more `data:` lines
    - comments and metadata fields (`event:`, `id:`, `retry:`)
    - providers that return raw JSON lines instead of formal SSE frames
    - streams that close after partial output has already been received
    """
    import requests

    saw_payload = False
    pending_data: list[str] = []
    in_sse_event = False

    try:
        for raw_line in response.iter_lines(decode_unicode=True, chunk_size=max(512, int(chunk_size or DEFAULT_SSE_CHUNK_SIZE))):
            if raw_line is None:
                continue

            line = str(raw_line or "").rstrip("\r")
            stripped = line.strip()

            if line == "":
                if pending_data:
                    payload = "\n".join(pending_data).strip()
                    pending_data = []
                    in_sse_event = False
                    if not payload:
                        continue
                    if payload == "[DONE]":
                        return
                    saw_payload = True
                    yield payload
                else:
                    in_sse_event = False
                continue

            if stripped.startswith(":"):
                in_sse_event = True
                continue

            lowered = stripped.lower()
            if lowered.startswith("data:"):
                in_sse_event = True
                pending_data.append(stripped[5:].lstrip())
                continue

            if any(lowered.startswith(prefix) for prefix in _KNOWN_SSE_FIELDS[1:]):
                in_sse_event = True
                continue

            if in_sse_event:
                if pending_data:
                    pending_data.append(stripped)
                continue

            if stripped == "[DONE]":
                return
            saw_payload = True
            yield stripped

        if pending_data:
            payload = "\n".join(pending_data).strip()
            if payload:
                if payload == "[DONE]":
                    return
                saw_payload = True
                yield payload
    except requests.exceptions.RequestException as exc:
        if saw_payload:
            logger.warning("Streaming response ended prematurely after partial payload: %s", exc)
            return
        raise
