"""Text-to-video tool backed by Agnes."""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import requests

from .base import BaseTool, ToolResult
from ..agnes import (
    AGNES_DEFAULT_API_URL,
    resolve_agnes_api_key,
    resolve_agnes_api_root,
    resolve_agnes_sdk_base_url,
    normalize_agnes_config,
)
from ..config import default_text_to_video_config, normalize_ttv_source, sanitize_tti_path
from ..agnes_ttv_profiles.common import is_valid_num_frames, num_frames_error
from ..agnes_ttv_profiles.registry import get_agnes_ttv_model_catalog, resolve_agnes_ttv_model


_SUCCESS_STATUSES = {"completed", "complete", "succeeded", "success", "done"}
_FAILURE_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}


class TextToVideoTool(BaseTool):
    """Generate videos through Agnes asynchronous video generation APIs."""

    name = "text_to_video"
    aliases = ("generate_video", "ttv")
    search_hint = "generate video assets from text prompts"
    tool_category = "video-generation"
    tool_tags = ("video", "generate", "asset", "prompt", "agnes")
    max_result_chars = 40_000

    description = """Generate videos from text prompts using the configured text-to-video backend.

The tool uses provider profiles from the text-to-video registry:
- generate creates a video task, optionally waits for completion, then saves the video URL to disk
- status retrieves an existing task by video_id or task_id and can download completed output
- list_models lists available text-to-video models and provider parameter constraints
- diagnose checks video configuration, default profile, and API key readiness"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "status", "list_models", "diagnose"],
                "description": "Operation to perform",
                "default": "generate",
            },
            "source": {
                "type": "string",
                "description": "Source override. Use list_models or media_generation_capabilities for available sources.",
                "default": "agnes",
            },
            "prompt": {"type": "string", "description": "Prompt for video generation"},
            "model": {"type": "string", "description": "Video model id/display name from the active source profile registry"},
            "video_id": {"type": "string", "description": "Agnes video_id returned by generate"},
            "task_id": {"type": "string", "description": "Legacy Agnes task id returned by generate"},
            "image": {
                "description": "Optional image URL/base64 string, or an array of image URLs for image-to-video/keyframes.",
            },
            "images": {
                "type": "array",
                "description": "Optional image URL/base64 list for multi-image or keyframe video.",
                "items": {"type": "string"},
            },
            "mode": {
                "type": "string",
                "description": "Optional Agnes video mode, e.g. keyframes for keyframe animation.",
            },
            "width": {"type": "integer", "description": "Video width"},
            "height": {"type": "integer", "description": "Video height"},
            "num_frames": {"type": "integer", "description": "Frame count. Provider-specific constraints are returned by list_models or media_generation_capabilities."},
            "frame_rate": {"type": "integer", "description": "Frame rate, 1-60"},
            "seed": {"type": "integer", "description": "Optional seed"},
            "negative_prompt": {"type": "string", "description": "Optional negative prompt"},
            "wait_for_completion": {
                "type": "boolean",
                "description": "When true, poll until the task completes or times out.",
                "default": True,
            },
            "poll_interval": {"type": "integer", "description": "Seconds between polling attempts"},
            "max_poll_seconds": {"type": "integer", "description": "Maximum seconds to wait for completion"},
            "download": {
                "type": "boolean",
                "description": "For status action, download the video when completed.",
                "default": False,
            },
            "output_path": {
                "type": "string",
                "description": "Relative output directory or file path. Relative to Reverie CLI project root.",
            },
            "timeout_seconds": {"type": "integer", "description": "HTTP request timeout in seconds"},
        },
        "required": [],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        action = str(kwargs.get("action", "generate") or "generate").strip().lower()
        source = str(kwargs.get("source", "agnes") or "agnes").strip().lower()
        if source != "agnes":
            return ToolResult.fail("text_to_video currently supports only source='agnes'.")
        if action == "list_models":
            return self._list_models()
        if action == "diagnose":
            return self._diagnose()
        if action == "status":
            return self._status(kwargs)
        if action != "generate":
            return ToolResult.fail(f"Unsupported action: {action}")
        return self._generate(kwargs)

    def _load_config(self) -> Dict[str, Any]:
        cfg = default_text_to_video_config()
        manager = self.context.get("config_manager")
        if manager is None:
            return cfg
        try:
            loaded = manager.load()
            loaded_cfg = getattr(loaded, "text_to_video", None)
            if isinstance(loaded_cfg, dict):
                cfg.update(loaded_cfg)
                if isinstance(loaded_cfg.get("agnes"), dict):
                    nested = dict(default_text_to_video_config().get("agnes", {}))
                    nested.update(loaded_cfg.get("agnes", {}))
                    cfg["agnes"] = nested
        except Exception:
            pass
        if not isinstance(cfg.get("agnes"), dict):
            cfg["agnes"] = dict(default_text_to_video_config().get("agnes", {}))
        cfg["active_source"] = normalize_ttv_source(cfg.get("active_source", "agnes"))
        output_dir = sanitize_tti_path(cfg.get("output_dir", "."))
        cfg["output_dir"] = output_dir or "."
        return cfg

    def _runtime_config(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cfg = config if isinstance(config, dict) else self._load_config()
        defaults = default_text_to_video_config().get("agnes", {})
        ttv_cfg = dict(defaults)
        if isinstance(cfg.get("agnes"), dict):
            ttv_cfg.update(cfg.get("agnes", {}))

        provider_cfg: Dict[str, Any] = {}
        manager = self.context.get("config_manager")
        if manager is not None:
            try:
                loaded = manager.load()
                provider_cfg = normalize_agnes_config(getattr(loaded, "agnes", {}))
            except Exception:
                provider_cfg = {}
        else:
            provider_cfg = normalize_agnes_config({})

        def _int_field(name: str, default: int, minimum: int = 1) -> int:
            try:
                value = int(ttv_cfg.get(name, default) or default)
            except (TypeError, ValueError):
                value = default
            return max(minimum, value)

        base_url = str(
            ttv_cfg.get("base_url")
            or ttv_cfg.get("api_url")
            or provider_cfg.get("api_url")
            or AGNES_DEFAULT_API_URL
        ).strip()

        return {
            "enabled": bool(ttv_cfg.get("enabled", True)),
            "api_key": resolve_agnes_api_key(provider_cfg),
            "base_url": resolve_agnes_sdk_base_url(base_url),
            "default_model": str(ttv_cfg.get("default_model", "") or "").strip(),
            "timeout": _int_field("timeout", 300),
            "default_width": _int_field("default_width", 1152),
            "default_height": _int_field("default_height", 768),
            "default_num_frames": _int_field("default_num_frames", 121),
            "default_frame_rate": _int_field("default_frame_rate", 24),
            "default_poll_interval": _int_field("default_poll_interval", 5),
            "default_max_poll_seconds": _int_field("default_max_poll_seconds", 600),
        }

    def _list_models(self) -> ToolResult:
        models = get_agnes_ttv_model_catalog()
        runtime_cfg = self._runtime_config()
        default_model = str(runtime_cfg.get("default_model", "") or "").strip().lower()
        rows = []
        data_rows = []
        for idx, item in enumerate(models):
            marker = "*" if str(item.get("id", "")).lower() == default_model else " "
            rows.append(f"{marker}[{idx}] {item['display_name']} | {item['id']} | {item.get('api', '')}")
            data_rows.append({**item, "index": idx, "is_default": str(item.get("id", "")).lower() == default_model})
        return ToolResult.ok(
            "Agnes text-to-video models:\n" + "\n".join(rows),
            data={"models": data_rows, "source": "agnes", "default_model": runtime_cfg.get("default_model", "")},
        )

    def _diagnose(self) -> ToolResult:
        cfg = self._load_config()
        runtime_cfg = self._runtime_config(cfg)
        default_model = resolve_agnes_ttv_model(runtime_cfg.get("default_model"))
        checks = [
            {"id": "enabled", "ok": bool(cfg.get("enabled", True)), "detail": "text_to_video.enabled"},
            {"id": "source", "ok": str(cfg.get("active_source", "agnes")).lower() == "agnes", "detail": "active source: agnes"},
            {"id": "agnes_enabled", "ok": bool(runtime_cfg.get("enabled", True)), "detail": "text_to_video.agnes.enabled"},
            {"id": "api_key", "ok": bool(runtime_cfg.get("api_key")), "detail": "agnes.api_key, AGNES_API_KEY, or AGNES_TOKEN"},
            {"id": "base_url", "ok": bool(runtime_cfg.get("base_url")), "detail": runtime_cfg.get("base_url", "")},
            {"id": "default_model", "ok": bool(default_model), "detail": runtime_cfg.get("default_model", "")},
            {
                "id": "num_frames",
                "ok": bool(default_model) and is_valid_num_frames(runtime_cfg.get("default_num_frames"), default_model),
                "detail": (default_model or {}).get("parameter_constraints", {}).get("num_frames", {}),
            },
        ]
        ready = all(item["ok"] for item in checks)
        output = "Text-to-video Agnes diagnosis\n"
        output += f"Ready: {'yes' if ready else 'no'}\n"
        for check in checks:
            output += f"- {check['id']}: {'ok' if check['ok'] else 'missing'} | {check['detail']}\n"
        payload = {"ready": ready, "checks": checks, "models": get_agnes_ttv_model_catalog(), "source": "agnes"}
        if ready:
            return ToolResult.ok(output, payload)
        return ToolResult.partial(output, "Agnes TTV is not ready; configure the missing API key or defaults.", payload)

    def _generate(self, kwargs: Dict[str, Any]) -> ToolResult:
        cfg = self._load_config()
        runtime_cfg = self._runtime_config(cfg)
        if not cfg.get("enabled", True):
            return ToolResult.fail("text_to_video is disabled in config.json (text_to_video.enabled=false)")
        if not runtime_cfg.get("enabled", True):
            return ToolResult.fail("text_to_video.agnes.enabled=false")
        if not runtime_cfg.get("api_key"):
            return ToolResult.fail("Agnes API key is required. Set agnes.api_key in config.json, or set AGNES_API_KEY/AGNES_TOKEN.")

        prompt = str(kwargs.get("prompt", "") or "").strip()
        if not prompt:
            return ToolResult.fail("Parameter 'prompt' is required for generate action")

        selected = resolve_agnes_ttv_model(kwargs.get("model") or runtime_cfg.get("default_model"))
        if not selected:
            available = ", ".join(item.get("id", "") for item in get_agnes_ttv_model_catalog())
            return ToolResult.fail(f"Unknown Agnes TTV model '{kwargs.get('model')}'. Available models: {available}")

        try:
            generation = self._build_generation_payload(prompt, selected["id"], runtime_cfg, kwargs)
            output_path = self._resolve_output_path(kwargs.get("output_path"), str(cfg.get("output_dir", ".")))
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        try:
            response_json = self._post_video_task(runtime_cfg, generation["payload"], timeout_seconds=generation["timeout"])
        except Exception as exc:
            return ToolResult.fail(f"Agnes TTV task creation failed: {exc}")

        task_info = self._extract_task_info(response_json)
        task_info["model"] = selected["id"]
        task_info["source"] = "agnes"

        wait_for_completion = bool(kwargs.get("wait_for_completion", True))
        if not wait_for_completion:
            return ToolResult.ok(self._format_task_output("Agnes text-to-video task created", task_info), task_info)

        poll_interval = self._positive_int(kwargs.get("poll_interval"), runtime_cfg.get("default_poll_interval", 5))
        max_poll_seconds = self._positive_int(kwargs.get("max_poll_seconds"), runtime_cfg.get("default_max_poll_seconds", 600))
        final_info = self._poll_until_complete(runtime_cfg, task_info, selected["id"], poll_interval, max_poll_seconds)
        saved_video = ""
        video_url = self._extract_video_url(final_info)
        if self._is_success_status(final_info.get("status")) and video_url:
            try:
                saved_video = self._download_video(video_url, output_path, selected["id"])
                final_info["saved_video"] = saved_video
            except Exception as exc:
                return ToolResult.partial(
                    self._format_task_output("Agnes text-to-video task completed but download failed", final_info),
                    f"Could not download video: {exc}",
                    final_info,
                )

        title = "Agnes text-to-video task completed" if self._is_success_status(final_info.get("status")) else "Agnes text-to-video task status"
        if self._is_failure_status(final_info.get("status")):
            return ToolResult.partial(self._format_task_output(title, final_info), "Agnes video generation failed.", final_info)
        if self._is_success_status(final_info.get("status")) and saved_video:
            return ToolResult.ok(self._format_task_output(title, final_info), final_info)
        return ToolResult.partial(
            self._format_task_output(title, final_info),
            "Agnes video generation did not finish before the polling timeout or returned no video_url.",
            final_info,
        )

    def _status(self, kwargs: Dict[str, Any]) -> ToolResult:
        cfg = self._load_config()
        runtime_cfg = self._runtime_config(cfg)
        if not runtime_cfg.get("api_key"):
            return ToolResult.fail("Agnes API key is required. Set agnes.api_key in config.json, or set AGNES_API_KEY/AGNES_TOKEN.")
        selected = resolve_agnes_ttv_model(kwargs.get("model") or runtime_cfg.get("default_model"))
        if not selected:
            available = ", ".join(item.get("id", "") for item in get_agnes_ttv_model_catalog())
            return ToolResult.fail(f"Unknown Agnes TTV model '{kwargs.get('model')}'. Available models: {available}")
        task_info = {
            "video_id": str(kwargs.get("video_id", "") or "").strip(),
            "task_id": str(kwargs.get("task_id", "") or "").strip(),
        }
        if not task_info["video_id"] and not task_info["task_id"]:
            return ToolResult.fail("status action requires video_id or task_id")
        try:
            final_info = self._fetch_status(runtime_cfg, task_info, selected["id"])
        except Exception as exc:
            return ToolResult.fail(f"Agnes TTV status retrieval failed: {exc}")

        video_url = self._extract_video_url(final_info)
        if bool(kwargs.get("download", False)) and self._is_success_status(final_info.get("status")) and video_url:
            try:
                output_path = self._resolve_output_path(kwargs.get("output_path"), str(cfg.get("output_dir", ".")))
                final_info["saved_video"] = self._download_video(video_url, output_path, selected["id"])
            except Exception as exc:
                return ToolResult.partial(self._format_task_output("Agnes text-to-video status", final_info), f"Could not download video: {exc}", final_info)
        return ToolResult.ok(self._format_task_output("Agnes text-to-video status", final_info), final_info)

    def _build_generation_payload(
        self,
        prompt: str,
        model_id: str,
        runtime_cfg: Dict[str, Any],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        width = self._positive_int(kwargs.get("width"), runtime_cfg.get("default_width", 1152))
        height = self._positive_int(kwargs.get("height"), runtime_cfg.get("default_height", 768))
        num_frames = self._positive_int(kwargs.get("num_frames"), runtime_cfg.get("default_num_frames", 121))
        profile = resolve_agnes_ttv_model(model_id)
        if not profile or not is_valid_num_frames(num_frames, profile):
            raise ValueError(num_frames_error(profile or {}))
        frame_rate = self._positive_int(kwargs.get("frame_rate"), runtime_cfg.get("default_frame_rate", 24))
        if frame_rate > 60:
            raise ValueError("frame_rate must be between 1 and 60.")

        payload: Dict[str, Any] = {
            "model": model_id,
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }
        if kwargs.get("seed") is not None:
            try:
                payload["seed"] = int(kwargs.get("seed"))
            except (TypeError, ValueError):
                raise ValueError("seed must be an integer")
        negative_prompt = str(kwargs.get("negative_prompt", "") or "").strip()
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        images = self._collect_images(kwargs)
        image_value = kwargs.get("image")
        if images:
            payload["image"] = images[0] if len(images) == 1 else images
            payload["extra_body"] = {"image": images}
        elif isinstance(image_value, str) and image_value.strip():
            payload["image"] = image_value.strip()

        mode = str(kwargs.get("mode", "") or "").strip()
        if mode:
            extra_body = payload.setdefault("extra_body", {})
            extra_body["mode"] = mode

        timeout_seconds = self._positive_int(kwargs.get("timeout_seconds"), runtime_cfg.get("timeout", 300))
        return {"payload": payload, "timeout": timeout_seconds}

    def _post_video_task(self, runtime_cfg: Dict[str, Any], payload: Dict[str, Any], *, timeout_seconds: int) -> Dict[str, Any]:
        response = requests.post(
            f"{runtime_cfg['base_url']}/videos",
            headers=self._headers(runtime_cfg),
            json=payload,
            timeout=timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
        data = response.json()
        return data if isinstance(data, dict) else {"raw": data}

    def _fetch_status(self, runtime_cfg: Dict[str, Any], task_info: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        video_id = str(task_info.get("video_id", "") or "").strip()
        task_id = str(task_info.get("task_id", "") or "").strip()
        errors: List[str] = []
        if video_id:
            url = (
                f"{resolve_agnes_api_root(runtime_cfg['base_url'])}/agnesapi"
                f"?video_id={quote(video_id)}&model_name={quote(model_id)}"
            )
            try:
                response = requests.get(url, headers=self._headers(runtime_cfg), timeout=runtime_cfg.get("timeout", 300))
                if response.status_code < 400:
                    data = response.json()
                    return self._extract_task_info(data)
                errors.append(f"video_id lookup HTTP {response.status_code}: {response.text[:500]}")
            except Exception as exc:
                errors.append(str(exc))
        if task_id:
            url = f"{runtime_cfg['base_url']}/videos/{quote(task_id)}"
            response = requests.get(url, headers=self._headers(runtime_cfg), timeout=runtime_cfg.get("timeout", 300))
            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
            data = response.json()
            return self._extract_task_info(data)
        raise RuntimeError("; ".join(errors) or "No video_id or task_id available for status lookup")

    def _poll_until_complete(
        self,
        runtime_cfg: Dict[str, Any],
        task_info: Dict[str, Any],
        model_id: str,
        poll_interval: int,
        max_poll_seconds: int,
    ) -> Dict[str, Any]:
        current = dict(task_info)
        if self._is_success_status(current.get("status")) or self._is_failure_status(current.get("status")):
            return current
        deadline = time.time() + max_poll_seconds
        while time.time() < deadline:
            time.sleep(max(1, poll_interval))
            fetched = self._fetch_status(runtime_cfg, current, model_id)
            for key in ("video_id", "task_id"):
                if not fetched.get(key) and current.get(key):
                    fetched[key] = current.get(key)
            current = fetched
            if self._is_success_status(current.get("status")) or self._is_failure_status(current.get("status")):
                return current
        current["poll_timed_out"] = True
        current["max_poll_seconds"] = max_poll_seconds
        return current

    def _extract_task_info(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, dict):
            raw = dict(data)
            nested = raw.get("data")
            if isinstance(nested, dict):
                raw.update({k: v for k, v in nested.items() if k not in raw or not raw.get(k)})
        else:
            raw = {"raw": data}
        return {
            **raw,
            "id": str(raw.get("id", "") or "").strip(),
            "task_id": str(raw.get("task_id") or raw.get("id") or "").strip(),
            "video_id": str(raw.get("video_id", "") or "").strip(),
            "status": str(raw.get("status") or raw.get("state") or raw.get("task_status") or "").strip().lower(),
            "progress": raw.get("progress"),
            "video_url": self._extract_video_url(raw),
        }

    def _extract_video_url(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        for key in ("video_url", "url", "output_url", "remixed_from_video_id"):
            value = data.get(key)
            if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
                return value.strip()
        for key in ("output", "result", "data"):
            nested = data.get(key)
            if isinstance(nested, dict):
                found = self._extract_video_url(nested)
                if found:
                    return found
            if isinstance(nested, list):
                for item in nested:
                    found = self._extract_video_url(item)
                    if found:
                        return found
        return ""

    def _download_video(self, video_url: str, output_path: Path, model_id: str) -> str:
        response = requests.get(video_url, headers={"User-Agent": "ReverieCLI-Agnes-TTV/1.0"}, timeout=300)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        content_type = response.headers.get("Content-Type", "")
        suffix = self._video_suffix(video_url, content_type)
        if output_path.suffix:
            target = output_path
        else:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            target = output_path / f"agnes_{model_id.replace('-', '_')}_{timestamp}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return str(target)

    def _resolve_output_path(self, output_override: Any, configured_output: str) -> Path:
        raw_output = output_override if output_override is not None else configured_output
        normalized = sanitize_tti_path(raw_output)
        if not normalized:
            return self.get_project_root()

        normalized = os.path.expandvars(normalized)
        out_path = Path(normalized).expanduser()
        if output_override is not None and self._looks_like_absolute_path(normalized):
            raise ValueError("output_path must be a relative path, for example: 'videos/agnes' or './outputs'.")
        return self.resolve_workspace_path(out_path, purpose="write generated videos")

    @staticmethod
    def _collect_images(kwargs: Dict[str, Any]) -> List[str]:
        images: List[str] = []
        raw_images = kwargs.get("images")
        if isinstance(raw_images, list):
            images.extend(str(item).strip() for item in raw_images if str(item or "").strip())
        raw_image = kwargs.get("image")
        if isinstance(raw_image, list):
            images.extend(str(item).strip() for item in raw_image if str(item or "").strip())
        return images

    @staticmethod
    def _headers(runtime_cfg: Dict[str, Any]) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {runtime_cfg.get('api_key', '')}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ReverieCLI-Agnes-TTV/1.0",
        }

    @staticmethod
    def _positive_int(value: Any, default: Any, minimum: int = 1) -> int:
        try:
            number = int(value if value is not None else default)
        except (TypeError, ValueError):
            number = int(default)
        return max(minimum, number)

    @staticmethod
    def _is_success_status(status: Any) -> bool:
        return str(status or "").strip().lower() in _SUCCESS_STATUSES

    @staticmethod
    def _is_failure_status(status: Any) -> bool:
        return str(status or "").strip().lower() in _FAILURE_STATUSES

    @staticmethod
    def _video_suffix(video_url: str, content_type: str) -> str:
        guessed = mimetypes.guess_extension(str(content_type or "").split(";")[0].strip())
        if guessed:
            return ".mp4" if guessed == ".mp4v" else guessed
        parsed = urlparse(video_url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix in {".mp4", ".webm", ".mov", ".mkv"}:
            return suffix
        return ".mp4"

    @staticmethod
    def _format_task_output(title: str, info: Dict[str, Any]) -> str:
        lines = [title]
        for key in ("status", "progress", "video_id", "task_id", "video_url", "saved_video"):
            value = info.get(key)
            if value not in (None, ""):
                lines.append(f"{key}: {value}")
        if info.get("poll_timed_out"):
            lines.append(f"poll_timed_out: true ({info.get('max_poll_seconds')}s)")
        return "\n".join(lines)

    @staticmethod
    def _looks_like_absolute_path(path_text: str) -> bool:
        if not path_text:
            return False
        if path_text.startswith(("\\\\", "//")):
            return True
        return bool(Path(path_text).is_absolute() or (len(path_text) >= 3 and path_text[1:3] in (":\\", ":/")))
