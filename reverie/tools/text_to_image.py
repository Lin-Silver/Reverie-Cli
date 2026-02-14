"""
Text-to-Image Tool

Generate images from text prompts using the local Comfy/generate_image.py script.
Models are read from config.json (text_to_image.models) and selected by
display name instead of raw path.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from pathlib import Path
import subprocess
import sys
import shutil
import os
import re

from .base import BaseTool, ToolResult
from ..config import (
    default_text_to_image_config,
    normalize_tti_models,
    resolve_tti_default_display_name,
    sanitize_tti_path,
)


class TextToImageTool(BaseTool):
    """Generate images via Comfy backend script."""

    name = "text_to_image"

    description = """Generate images from text prompts using configured Comfy models.

Supports:
- List configured text-to-image models from config.json
- Generate images by selecting configured model display name
- Full parameter tuning (size, steps, sampler, scheduler, seed, CPU mode, timeout, extra CLI args)

Examples:
- List models: {"action": "list_models"}
- Generate with default model: {"action": "generate", "prompt": "a cyberpunk city at dusk"}
- Generate with model display name: {"action": "generate", "prompt": "anime portrait", "model": "anime-xl"}"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "list_models"],
                "description": "Operation to perform",
                "default": "generate",
            },
            "prompt": {"type": "string", "description": "Positive prompt for image generation"},
            "negative_prompt": {"type": "string", "description": "Negative prompt override"},
            "model": {
                "type": "string",
                "description": "Configured model display name override from text_to_image.models[].display_name",
            },
            "display_name": {
                "type": "string",
                "description": "Alias of `model`. Uses configured model display name.",
            },
            "model_index": {
                "type": "integer",
                "description": "Optional configured model index override (backward compatibility).",
            },
            "width": {"type": "integer", "description": "Image width"},
            "height": {"type": "integer", "description": "Image height"},
            "steps": {"type": "integer", "description": "Sampling steps"},
            "cfg": {"type": "number", "description": "CFG scale"},
            "seed": {"type": "integer", "description": "Random seed"},
            "sampler": {"type": "string", "description": "Sampler name"},
            "scheduler": {"type": "string", "description": "Scheduler name"},
            "batch_size": {"type": "integer", "description": "Batch size"},
            "use_cpu": {"type": "boolean", "description": "Force CPU mode"},
            "output_path": {
                "type": "string",
                "description": "Relative output directory (or file path). Relative to Reverie CLI project root.",
            },
            "script_path": {
                "type": "string",
                "description": "Generation script path override. Usually not needed.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Command timeout in seconds (default: 3600).",
            },
            "extra_args": {
                "type": "array",
                "description": "Extra raw CLI args appended at the end, for advanced tuning.",
                "items": {"type": "string"},
            },
            "extra_options": {
                "type": "object",
                "description": "Advanced option map converted to CLI flags. Example: {\"clip_skip\": 2, \"tiling\": true}",
            },
        },
        "required": [],
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._project_root = Path(context.get("project_root", Path.cwd())) if context else Path.cwd()

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "generate")
        if action == "list_models":
            return "Listing configured text-to-image models"
        return "Generating image with local text-to-image model"

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "generate")
        if action == "list_models":
            return self._list_models()
        if action != "generate":
            return ToolResult.fail(f"Unsupported action: {action}")

        prompt = kwargs.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail("Parameter 'prompt' is required for generate action")

        config = self._get_t2i_config()
        if not config.get("enabled", True):
            return ToolResult.fail("text_to_image is disabled in config.json (text_to_image.enabled=false)")

        script_path = self._resolve_script_path(config=config, script_override=kwargs.get("script_path"))
        if not script_path.exists():
            return ToolResult.fail(
                f"Text-to-image script not found: {script_path}. "
                "Please check text_to_image.script_path in config.json or bundled resources."
            )

        selected_model = self._select_model(
            config=config,
            model_display_name=kwargs.get("display_name") or kwargs.get("model"),
            model_index=kwargs.get("model_index"),
        )
        if selected_model is None:
            return ToolResult.fail(
                "No model available. Please set text_to_image.models in config.json, "
                "or pass a valid display name via 'model' (or 'display_name')."
            )
        model_path = self._resolve_path(str(selected_model["path"]))
        model_display_name = selected_model["display_name"]
        if not model_path.exists():
            return ToolResult.fail(
                f"Model file not found for display name '{model_display_name}': {model_path}"
            )

        python_exe = self._select_python_executable(config=config, script_path=script_path)
        if python_exe is None:
            return ToolResult.fail(
                "No usable Python interpreter found for text_to_image.\n"
                "Set text_to_image.python_executable in config.json, or install Python and keep it in PATH."
            )
        if not python_exe.exists():
            return ToolResult.fail(
                f"Python executable not found: {python_exe}. "
                "Set text_to_image.python_executable in config.json."
            )

        try:
            width = int(kwargs.get("width", config.get("default_width", 512)))
            height = int(kwargs.get("height", config.get("default_height", 512)))
            steps = int(kwargs.get("steps", config.get("default_steps", 20)))
            cfg = float(kwargs.get("cfg", config.get("default_cfg", 8.0)))
            batch_size = int(kwargs.get("batch_size", 1))
        except (TypeError, ValueError):
            return ToolResult.fail("width/height/steps/cfg/batch_size must be valid numeric values")
        sampler = str(kwargs.get("sampler", config.get("default_sampler", "euler")))
        scheduler = str(kwargs.get("scheduler", config.get("default_scheduler", "normal")))
        seed = kwargs.get("seed", None)
        if seed is not None:
            try:
                seed = int(seed)
            except (TypeError, ValueError):
                return ToolResult.fail("seed must be an integer")

        if width <= 0 or height <= 0:
            return ToolResult.fail("width and height must be positive integers")
        if steps <= 0:
            return ToolResult.fail("steps must be a positive integer")
        if batch_size <= 0:
            return ToolResult.fail("batch_size must be a positive integer")

        negative_prompt = kwargs.get("negative_prompt")
        if negative_prompt is None:
            negative_prompt = str(config.get("default_negative_prompt", ""))

        output_override = kwargs.get("output_path")
        try:
            output_path = self._resolve_output_path(
                output_override=output_override,
                configured_output=str(config.get("output_dir", ".")),
            )
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        use_cpu = bool(kwargs.get("use_cpu", config.get("force_cpu", False)))

        cmd = [
            str(python_exe),
            str(script_path),
            "--model",
            str(model_path),
            "--prompt",
            prompt,
            "--negative-prompt",
            str(negative_prompt),
            "--width",
            str(width),
            "--height",
            str(height),
            "--steps",
            str(steps),
            "--cfg",
            str(cfg),
            "--sampler",
            sampler,
            "--scheduler",
            scheduler,
            "--batch-size",
            str(batch_size),
            "--output",
            str(output_path),
        ]
        if seed is not None:
            cmd.extend(["--seed", str(seed)])
        if use_cpu:
            cmd.append("--cpu")

        extra_options = kwargs.get("extra_options")
        if extra_options is not None:
            if not isinstance(extra_options, dict):
                return ToolResult.fail("extra_options must be an object/dict")
            for key, value in extra_options.items():
                if not isinstance(key, str) or not key.strip():
                    return ToolResult.fail("extra_options keys must be non-empty strings")
                flag = "--" + key.strip().replace("_", "-")
                if value is None:
                    continue
                if isinstance(value, bool):
                    if value:
                        cmd.append(flag)
                    continue
                if isinstance(value, list):
                    for item in value:
                        cmd.extend([flag, str(item)])
                    continue
                cmd.extend([flag, str(value)])

        extra_args = kwargs.get("extra_args")
        if extra_args is not None:
            if not isinstance(extra_args, list) or not all(isinstance(arg, str) for arg in extra_args):
                return ToolResult.fail("extra_args must be an array of strings")
            cmd.extend(extra_args)

        timeout_seconds = kwargs.get("timeout_seconds", 60 * 60)
        try:
            timeout_seconds = int(timeout_seconds)
        except (TypeError, ValueError):
            return ToolResult.fail("timeout_seconds must be an integer")
        if timeout_seconds <= 0:
            return ToolResult.fail("timeout_seconds must be a positive integer")

        run_cwd = self._project_root
        try:
            result = subprocess.run(
                cmd,
                cwd=str(run_cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"Image generation timed out after {timeout_seconds} seconds")
        except Exception as exc:
            return ToolResult.fail(f"Failed to launch text-to-image generation: {exc}")

        saved_images = self._parse_saved_images(result.stdout or "")
        output_lines = [
            f"Command exit code: {result.returncode}",
            f"Model display name: {model_display_name}",
            f"Model path: {model_path}",
            f"Output target: {output_path}",
        ]
        if saved_images:
            output_lines.append("Generated images:")
            output_lines.extend(f"- {p}" for p in saved_images)
        if result.stdout:
            output_lines.append("\n--- STDOUT ---")
            output_lines.append(result.stdout.strip())
        if result.stderr:
            output_lines.append("\n--- STDERR ---")
            output_lines.append(result.stderr.strip())

        if result.returncode == 0:
            return ToolResult.ok(
                "\n".join(output_lines),
                data={
                    "saved_images": saved_images,
                    "model_display_name": model_display_name,
                    "model_path": str(model_path),
                    "output_path": str(output_path),
                    "exit_code": result.returncode,
                },
            )
        error_text = f"Image generation failed with exit code {result.returncode}"
        missing_module = self._extract_missing_module_name(result.stdout or "", result.stderr or "")
        if missing_module:
            error_text = (
                f"TTI runtime is missing Python module '{missing_module}'. "
                "Install optional dependencies with: pip install -r requirements-tti.txt"
            )
        return ToolResult.partial("\n".join(output_lines), error_text)

    def _get_t2i_config(self) -> Dict[str, Any]:
        cfg = default_text_to_image_config()
        manager = self.context.get("config_manager")
        if manager is None:
            cfg["models"] = normalize_tti_models(cfg.get("models", []), legacy_model_paths=cfg.get("model_paths", []))
            cfg["default_model_display_name"] = resolve_tti_default_display_name(cfg)
            return cfg
        try:
            loaded = manager.load()
            loaded_cfg = getattr(loaded, "text_to_image", None)
            if isinstance(loaded_cfg, dict):
                cfg.update(loaded_cfg)
        except Exception:
            pass
        cfg["models"] = normalize_tti_models(
            cfg.get("models", []),
            legacy_model_paths=cfg.get("model_paths", []),
        )
        cfg["default_model_display_name"] = resolve_tti_default_display_name(cfg)
        cfg.pop("model_paths", None)
        cfg.pop("default_model_index", None)
        # Migrate legacy default output dir from old versions.
        output_dir = sanitize_tti_path(cfg.get("output_dir", "."))
        if output_dir.replace("\\", "/").strip().lower() in {"comfy/output", "./comfy/output"}:
            cfg["output_dir"] = "."
        elif output_dir:
            cfg["output_dir"] = output_dir
        else:
            cfg["output_dir"] = "."
        return cfg

    def _list_models(self) -> ToolResult:
        config = self._get_t2i_config()
        models = config.get("models", [])
        default_display_name = str(config.get("default_model_display_name", "")).strip()

        if not models:
            return ToolResult.ok(
                "No text-to-image models configured.\n"
                "Set text_to_image.models in config.json with one or more model entries.",
                data={"models": []},
            )

        rows = []
        data_rows = []
        for idx, item in enumerate(models):
            display_name = item["display_name"]
            configured_path = item["path"]
            introduction = item.get("introduction", "")
            resolved = self._resolve_path(configured_path)
            exists = resolved.exists()
            marker = "*" if display_name.lower() == default_display_name.lower() else " "
            intro_text = f" | intro: {introduction}" if introduction else ""
            rows.append(
                f"{marker}[{idx}] {display_name} | {configured_path} -> {resolved} "
                f"({'OK' if exists else 'NOT FOUND'}){intro_text}"
            )
            data_rows.append(
                {
                    "index": idx,
                    "display_name": display_name,
                    "configured_path": configured_path,
                    "resolved_path": str(resolved),
                    "exists": exists,
                    "is_default": display_name.lower() == default_display_name.lower(),
                    "introduction": introduction,
                }
            )

        return ToolResult.ok(
            "Configured text-to-image models:\n" + "\n".join(rows),
            data={"models": data_rows},
        )

    def _select_model(
        self,
        config: Dict[str, Any],
        model_display_name: Optional[str],
        model_index: Optional[int],
    ) -> Optional[Dict[str, str]]:
        configured = config.get("models", [])
        if not isinstance(configured, list) or not configured:
            return None

        if model_display_name:
            wanted = str(model_display_name).strip().lower()
            if not wanted:
                return None
            for item in configured:
                if item.get("display_name", "").strip().lower() == wanted:
                    return item
            return None

        if model_index is not None:
            try:
                idx = int(model_index)
            except (TypeError, ValueError):
                return None
            if idx < 0 or idx >= len(configured):
                return None
            return configured[idx]

        default_display = str(config.get("default_model_display_name", "")).strip().lower()
        if default_display:
            for item in configured:
                if item.get("display_name", "").strip().lower() == default_display:
                    return item

        return configured[0]

    def _select_python_executable(self, config: Dict[str, Any], script_path: Path) -> Optional[Path]:
        configured = str(config.get("python_executable", "")).strip()
        if configured:
            return self._resolve_path(configured)

        comfy_venv = script_path.parent / ".venv" / "Scripts" / "python.exe"
        if comfy_venv.exists():
            return comfy_venv

        # In frozen exe, sys.executable points to ReverieCli.exe, not python.exe.
        # Prefer discovering a system Python command from PATH.
        if getattr(sys, "frozen", False):
            for cmd in ("python", "python3", "py"):
                discovered = shutil.which(cmd)
                if discovered:
                    return Path(discovered).resolve()
            return None

        return Path(sys.executable).resolve()

    def _resolve_script_path(self, config: Dict[str, Any], script_override: Optional[str] = None) -> Path:
        candidates: List[Path] = []

        if script_override:
            candidates.append(self._resolve_path(script_override))

        bundled_dir = self._get_bundled_comfy_dir()
        # For packaged executable, prefer bundled resources over workspace-relative paths.
        if bundled_dir and getattr(sys, "frozen", False):
            candidates.append((bundled_dir / "generate_image.py").resolve())

        configured = str(config.get("script_path", "Comfy/generate_image.py"))
        if configured:
            candidates.append(self._resolve_path(configured))

        if bundled_dir:
            candidates.append((bundled_dir / "generate_image.py").resolve())

        candidates.append((self._project_root / "Comfy" / "generate_image.py").resolve())

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0]

    def _get_bundled_comfy_dir(self) -> Optional[Path]:
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                bundled = Path(meipass) / "reverie_resources" / "comfy"
                if bundled.exists():
                    return bundled

        # Development fallback if resources are copied beside source.
        local_bundled = self._project_root / "reverie_resources" / "comfy"
        if local_bundled.exists():
            return local_bundled

        return None

    def _resolve_path(self, raw_path: str) -> Path:
        normalized = sanitize_tti_path(raw_path)
        if not normalized:
            return self._project_root

        normalized = os.path.expandvars(normalized)
        path = Path(normalized).expanduser()
        if path.is_absolute() or self._looks_like_absolute_path(normalized):
            return path

        bases: List[Path] = [self._project_root]

        manager = self.context.get("config_manager")
        if manager is not None:
            config_path = getattr(manager, "config_path", None)
            if config_path:
                bases.append(Path(config_path).parent)

        for base in bases:
            candidate = (base / path).resolve()
            if candidate.exists():
                return candidate

        return (bases[0] / path).resolve()

    def _resolve_output_path(self, output_override: Any, configured_output: str) -> Path:
        raw_output = output_override if output_override is not None else configured_output
        normalized = sanitize_tti_path(raw_output)
        if not normalized:
            return self._project_root

        normalized = os.path.expandvars(normalized)
        out_path = Path(normalized).expanduser()

        # Tool-call override must be relative to project root.
        if output_override is not None and (out_path.is_absolute() or self._looks_like_absolute_path(normalized)):
            raise ValueError(
                "output_path must be a relative path (for example: 'images/tti' or './outputs')."
            )

        if out_path.is_absolute() or self._looks_like_absolute_path(normalized):
            return out_path

        return (self._project_root / out_path).resolve()

    @staticmethod
    def _looks_like_absolute_path(path_text: str) -> bool:
        if not path_text:
            return False

        if path_text.startswith(("\\\\", "//")):
            return True

        # Windows drive path, e.g. C:\models\xx.safetensors or D:/models/xx.safetensors
        if len(path_text) >= 3 and path_text[1] == ":" and path_text[0].isalpha():
            if path_text[2] in ("\\", "/"):
                return True

        if path_text.startswith(("\\", "/")):
            return True

        return False

    @staticmethod
    def _extract_missing_module_name(stdout: str, stderr: str) -> Optional[str]:
        merged = "\n".join([stdout or "", stderr or ""])
        match = re.search(r"No module named ['\"]([^'\"]+)['\"]", merged)
        if not match:
            return None
        return match.group(1).strip() or None

    @staticmethod
    def _parse_saved_images(stdout: str) -> List[str]:
        results: List[str] = []
        for line in stdout.splitlines():
            marker = "Saved image to:"
            if marker in line:
                path = line.split(marker, 1)[1].strip()
                if path:
                    results.append(path)
        return results
