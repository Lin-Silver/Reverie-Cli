"""Safe live smoke tests for Reverie's first-party model sources."""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .codex import (
    build_codex_request_payload,
    build_codex_runtime_model_data,
    detect_codex_cli_credentials,
    get_codex_request_headers,
    normalize_codex_config,
    parse_codex_sse_event,
    resolve_codex_request_url,
)
from .aihubmix import (
    build_aihubmix_openai_options,
    build_aihubmix_runtime_model_data,
    normalize_aihubmix_config,
)
from .config import Config, get_app_root
from .modelscope import (
    build_modelscope_anthropic_options,
    build_modelscope_runtime_model_data,
    normalize_modelscope_config,
)
from .nvidia import (
    apply_nvidia_request_defaults,
    build_nvidia_openai_options,
    build_nvidia_runtime_model_data,
    normalize_nvidia_config,
    resolve_nvidia_request_url,
)
from .webgemini import (
    build_webgemini_runtime_model_data,
    iter_webgemini_text_deltas,
    normalize_webgemini_config,
)


BUILTIN_PROVIDER_NAMES = ("aihubmix", "modelscope", "nvidia", "codex", "webgemini")


@dataclass
class ProviderSmokeResult:
    provider: str
    model: str = ""
    status: str = "error"
    latency_ms: int = 0
    error_class: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _redact(text: Any) -> str:
    value = str(text or "")
    patterns = [
        r"(?i)\b(sk-[A-Za-z0-9_\-]{12,})\b",
        r"(?i)\b(ms-[A-Za-z0-9_\-]{12,})\b",
        r"(?i)\b(nvapi-[A-Za-z0-9_\-]{12,})\b",
        r"(?i)\b(gh[pousr]_[A-Za-z0-9_]{16,})\b",
        r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]{8,}",
        r"(?i)(Bearer\s+)[A-Za-z0-9._\-]{12,}",
    ]
    for pattern in patterns:
        value = re.sub(pattern, lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED_SECRET]", value)
    return " ".join(value.split())[:500]


def _classify_error(exc: BaseException) -> str:
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    if "credential" in text or "api key" in text or "token" in text:
        return "missing_credentials"
    if "timeout" in name or "timeout" in text or "timed out" in text:
        return "timeout"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        if status == 429:
            return "rate_limited"
        if 400 <= status < 500:
            return f"http_{status}"
        if status >= 500:
            return f"http_{status}"
    if "connection" in name or "connection" in text:
        return "connection_error"
    if "import" in name or "module" in text:
        return "dependency_missing"
    return name or "error"


def _result_from_error(provider: str, model: str, start: float, exc: BaseException) -> ProviderSmokeResult:
    return ProviderSmokeResult(
        provider=provider,
        model=model,
        status="error",
        latency_ms=int((time.perf_counter() - start) * 1000),
        error_class=_classify_error(exc),
        message=_redact(exc),
    )


def _skipped(provider: str, model: str, reason: str) -> ProviderSmokeResult:
    return ProviderSmokeResult(provider=provider, model=model, status="skipped", error_class=reason, message=reason)


def _load_config(config_path: Optional[Path] = None) -> Config:
    path = Path(config_path).expanduser() if config_path is not None else get_app_root() / ".reverie" / "config.json"
    if not path.exists():
        return Config()
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return Config.from_dict(payload if isinstance(payload, dict) else {})


def _iter_sse_data_strings(response: Any, max_events: int = 12) -> Iterable[str]:
    data_lines: List[str] = []
    emitted = 0
    for raw_line in response.iter_lines(decode_unicode=True):
        line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, bytes) else str(raw_line or "")
        if not line:
            if data_lines:
                emitted += 1
                yield "\n".join(data_lines)
                data_lines = []
                if emitted >= max_events:
                    break
            continue
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]":
                data_lines.append(data)
    if data_lines and emitted < max_events:
        yield "\n".join(data_lines)


def _requests_post_stream(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    *,
    timeout_seconds: int,
) -> Any:
    import requests

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        stream=True,
        timeout=(min(10, max(1, timeout_seconds)), max(2, timeout_seconds)),
    )
    response.raise_for_status()
    return response


def smoke_modelscope(config: Config, timeout_seconds: int = 45, model_id: str = "") -> ProviderSmokeResult:
    provider = "modelscope"
    cfg = normalize_modelscope_config(config.modelscope)
    if model_id:
        cfg["selected_model_id"] = str(model_id or "").strip()
        cfg = normalize_modelscope_config(cfg)
    runtime = build_modelscope_runtime_model_data(cfg)
    model = str((runtime or {}).get("model") or cfg.get("selected_model_id") or "")
    if not runtime or not runtime.get("api_key"):
        return _skipped(provider, model, "missing_credentials")

    start = time.perf_counter()
    try:
        from anthropic import Anthropic

        client = Anthropic(
            base_url=runtime["base_url"],
            api_key=runtime["api_key"],
            timeout=timeout_seconds,
            max_retries=0,
        )
        options = build_modelscope_anthropic_options(cfg, model_id=model)
        with client.messages.stream(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=min(16, int(options.get("max_tokens") or 16)),
        ) as stream:
            for text in stream.text_stream:
                if str(text or "").strip():
                    break
        return ProviderSmokeResult(provider=provider, model=model, status="ok", latency_ms=int((time.perf_counter() - start) * 1000))
    except Exception as exc:
        return _result_from_error(provider, model, start, exc)


def smoke_aihubmix(config: Config, timeout_seconds: int = 45, model_id: str = "") -> ProviderSmokeResult:
    provider = "aihubmix"
    cfg = normalize_aihubmix_config(config.aihubmix)
    if model_id:
        cfg["selected_model_id"] = str(model_id or "").strip()
        cfg = normalize_aihubmix_config(cfg)
    runtime = build_aihubmix_runtime_model_data(cfg)
    model = str((runtime or {}).get("model") or cfg.get("selected_model_id") or "")
    if not runtime or not runtime.get("api_key"):
        return _skipped(provider, model, "missing_credentials")

    smoke_cfg = {**cfg, "max_tokens": 16}
    start = time.perf_counter()
    stream = None
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=runtime["base_url"],
            api_key=runtime["api_key"],
            timeout=timeout_seconds,
            max_retries=0,
        )
        options = build_aihubmix_openai_options(smoke_cfg, model)
        options["max_tokens"] = min(16, int(options.get("max_tokens") or 16))
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            stream=True,
            **{key: value for key, value in options.items() if value is not None},
        )
        for chunk in stream:
            delta = getattr(getattr(chunk, "choices", [None])[0], "delta", None) if getattr(chunk, "choices", None) else None
            if getattr(delta, "content", None):
                break
        return ProviderSmokeResult(provider=provider, model=model, status="ok", latency_ms=int((time.perf_counter() - start) * 1000))
    except Exception as exc:
        return _result_from_error(provider, model, start, exc)
    finally:
        if stream is not None and hasattr(stream, "close"):
            stream.close()


def smoke_nvidia(config: Config, timeout_seconds: int = 45, model_id: str = "") -> ProviderSmokeResult:
    provider = "nvidia"
    cfg = normalize_nvidia_config(config.nvidia)
    if model_id:
        cfg["selected_model_id"] = str(model_id or "").strip()
        cfg = normalize_nvidia_config(cfg)
    runtime = build_nvidia_runtime_model_data(cfg)
    model = str((runtime or {}).get("model") or cfg.get("selected_model_id") or "")
    if not runtime or not runtime.get("api_key"):
        return _skipped(provider, model, "missing_credentials")

    smoke_cfg = {**cfg, "max_tokens": 16, "reasoning_effort": "none", "enable_thinking": False}
    start = time.perf_counter()
    response = None
    stream = None
    try:
        if str(runtime.get("provider") or "").strip().lower() == "openai-sdk":
            from openai import OpenAI

            client = OpenAI(
                base_url=runtime["base_url"],
                api_key=runtime["api_key"],
                timeout=timeout_seconds,
                max_retries=0,
            )
            options = build_nvidia_openai_options(smoke_cfg, model)
            options["max_tokens"] = min(16, int(options.get("max_tokens") or 16))
            option_model = str(options.pop("model", "") or model).strip() or model
            stream = client.chat.completions.create(
                model=option_model,
                messages=[{"role": "user", "content": "Reply with OK."}],
                stream=True,
                **{key: value for key, value in options.items() if value is not None},
            )
            for chunk in stream:
                delta = getattr(getattr(chunk, "choices", [None])[0], "delta", None) if getattr(chunk, "choices", None) else None
                if getattr(delta, "content", None):
                    break
            return ProviderSmokeResult(provider=provider, model=model, status="ok", latency_ms=int((time.perf_counter() - start) * 1000))

        url = resolve_nvidia_request_url(runtime["base_url"], runtime.get("endpoint", ""))
        payload = apply_nvidia_request_defaults(
            {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 16,
                "stream": True,
            },
            smoke_cfg,
        )
        response = _requests_post_stream(
            url,
            {
                "Authorization": f"Bearer {runtime['api_key']}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            payload,
            timeout_seconds=timeout_seconds,
        )
        next(_iter_sse_data_strings(response), "")
        return ProviderSmokeResult(provider=provider, model=model, status="ok", latency_ms=int((time.perf_counter() - start) * 1000))
    except Exception as exc:
        return _result_from_error(provider, model, start, exc)
    finally:
        if stream is not None and hasattr(stream, "close"):
            stream.close()
        if response is not None:
            response.close()


def smoke_codex(config: Config, timeout_seconds: int = 60, model_id: str = "") -> ProviderSmokeResult:
    provider = "codex"
    cfg = normalize_codex_config(config.codex)
    if model_id:
        cfg["selected_model_id"] = str(model_id or "").strip()
        cfg = normalize_codex_config(cfg)
    runtime = build_codex_runtime_model_data(cfg)
    model = str((runtime or {}).get("model") or cfg.get("selected_model_id") or "")
    cred = detect_codex_cli_credentials()
    if not runtime or not cred.get("found"):
        return _skipped(provider, model, "missing_credentials")

    start = time.perf_counter()
    response = None
    try:
        payload = build_codex_request_payload(
            model_name=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            reasoning_effort=str(cfg.get("reasoning_effort") or "medium"),
            stream=True,
        )
        response = _requests_post_stream(
            resolve_codex_request_url(runtime["base_url"], runtime.get("endpoint") or cfg.get("endpoint", "")),
            get_codex_request_headers(
                api_key=str(cred.get("api_key", "") or ""),
                account_id=str(cred.get("account_id", "") or ""),
                auth_mode=str(cred.get("auth_mode", "") or ""),
                stream=True,
            ),
            payload,
            timeout_seconds=timeout_seconds,
        )
        parser_state: Dict[str, Any] = {}
        for data_str in _iter_sse_data_strings(response):
            events, parser_state = parse_codex_sse_event(data_str, parser_state)
            if events:
                break
        return ProviderSmokeResult(provider=provider, model=model, status="ok", latency_ms=int((time.perf_counter() - start) * 1000))
    except Exception as exc:
        return _result_from_error(provider, model, start, exc)
    finally:
        if response is not None:
            response.close()


def smoke_webgemini(config: Config, timeout_seconds: int = 60, model_id: str = "") -> ProviderSmokeResult:
    provider = "webgemini"
    cfg = normalize_webgemini_config(config.webgemini)
    if model_id:
        cfg["selected_model_id"] = str(model_id or "").strip()
        cfg = normalize_webgemini_config(cfg)
    runtime = build_webgemini_runtime_model_data(cfg)
    model = str((runtime or {}).get("model") or cfg.get("selected_model_id") or "")
    if not runtime:
        return _skipped(provider, model, "disabled")

    start = time.perf_counter()
    try:
        for text in iter_webgemini_text_deltas(
            messages=[{"role": "user", "content": "Reply with OK."}],
            model=model,
            webgemini_config={**cfg, "timeout": timeout_seconds},
        ):
            if str(text or "").strip():
                break
        return ProviderSmokeResult(provider=provider, model=model, status="ok", latency_ms=int((time.perf_counter() - start) * 1000))
    except Exception as exc:
        return _result_from_error(provider, model, start, exc)


SMOKE_RUNNERS: Dict[str, Callable[[Config, int, str], ProviderSmokeResult]] = {
    "aihubmix": smoke_aihubmix,
    "modelscope": smoke_modelscope,
    "nvidia": smoke_nvidia,
    "codex": smoke_codex,
    "webgemini": smoke_webgemini,
}


def run_provider_smoke(
    providers: Optional[Iterable[str]] = None,
    *,
    config_path: Optional[Path] = None,
    timeout_seconds: int = 45,
    model_overrides: Optional[Dict[str, Iterable[str]]] = None,
) -> List[ProviderSmokeResult]:
    config = _load_config(config_path)
    wanted = [str(provider or "").strip().lower() for provider in (providers or BUILTIN_PROVIDER_NAMES)]
    overrides = {
        str(provider or "").strip().lower(): [str(model or "").strip() for model in models or [] if str(model or "").strip()]
        for provider, models in (model_overrides or {}).items()
    }
    results: List[ProviderSmokeResult] = []
    for provider in wanted:
        runner = SMOKE_RUNNERS.get(provider)
        if runner is None:
            results.append(_skipped(provider, "", "unknown_provider"))
            continue
        models = overrides.get(provider) or [""]
        for model_id in models:
            results.append(runner(config, timeout_seconds, model_id))
    return results


def parse_model_overrides(raw: str, providers: Iterable[str]) -> Dict[str, List[str]]:
    text = str(raw or "").strip()
    if not text:
        return {}
    provider_list = [str(provider or "").strip().lower() for provider in providers if str(provider or "").strip()]
    overrides: Dict[str, List[str]] = {}
    if ":" not in text and len(provider_list) == 1:
        overrides[provider_list[0]] = [part.strip() for part in text.split(",") if part.strip()]
        return overrides
    for chunk in text.split(","):
        if ":" not in chunk:
            continue
        provider, models = chunk.split(":", 1)
        provider_key = provider.strip().lower()
        if not provider_key:
            continue
        values = [part.strip() for part in re.split(r"[|;]", models) if part.strip()]
        if values:
            overrides[provider_key] = values
    return overrides


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run safe live smoke tests for Reverie's built-in model sources.")
    parser.add_argument("--config", type=Path, default=None, help="Path to .reverie/config.json.")
    parser.add_argument("--providers", default=",".join(BUILTIN_PROVIDER_NAMES), help="Comma-separated provider names.")
    parser.add_argument(
        "--models",
        default="",
        help=(
            "Temporary model override. With one provider, pass comma-separated model ids. "
            "With multiple providers, use provider:model-a|model-b."
        ),
    )
    parser.add_argument("--timeout", type=int, default=45, help="Per-provider read timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a compact table.")
    args = parser.parse_args(argv)

    providers = [part.strip().lower() for part in str(args.providers or "").split(",") if part.strip()]
    results = run_provider_smoke(
        providers,
        config_path=args.config,
        timeout_seconds=max(5, int(args.timeout or 45)),
        model_overrides=parse_model_overrides(args.models, providers),
    )
    if args.json:
        print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(
                f"{result.provider}\t{result.model or '-'}\t{result.status}\t"
                f"{result.latency_ms}ms\t{result.error_class or '-'}\t{result.message or ''}"
            )
    return 0 if all(result.status in {"ok", "skipped"} for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
