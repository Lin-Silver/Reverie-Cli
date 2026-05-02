"""
Text-to-Image Tool

Generate images from text prompts using the local Comfy runtime.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List
from pathlib import Path
import subprocess
import sys
import shutil
import os
import re
import time
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .base import BaseTool, ToolResult
from ..config import (
    default_text_to_image_config,
    get_app_root,
    normalize_tti_models,
    normalize_tti_source,
    resolve_tti_default_display_name,
    sanitize_tti_path,
)
from ..security_utils import is_path_within_workspace


class TextToImageTool(BaseTool):
    """Generate images via the local Comfy runtime."""

    name = "text_to_image"
    aliases = ("generate_image", "tti")
    search_hint = "generate image assets from text prompts"
    tool_category = "image-generation"
    tool_tags = ("image", "generate", "art", "asset", "comfy", "prompt")

    description = """Generate images from text prompts using configured local models.

Supports:
- List configured text-to-image models from config.json
- Generate images by selecting configured model display name
- Local Comfy parameter tuning

Examples:
- List models: {"action": "list_models"}
- Generate with default model: {"action": "generate", "prompt": "a cyberpunk city at dusk"}
- Generate with model display name: {"action": "generate", "prompt": "anime portrait", "model": "anime-xl"}"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "list_models", "diagnose", "prepare_models"],
                "description": "Operation to perform",
                "default": "generate",
            },
            "package": {
                "type": "string",
                "description": "Model package id for prepare_models, e.g. ernie-image-turbo-gguf.",
            },
            "download": {
                "type": "boolean",
                "description": "When true, prepare_models downloads missing package files into the app-local depot.",
            },
            "include_optional": {
                "type": "boolean",
                "description": "When true, prepare_models also downloads optional package files.",
            },
            "max_download_seconds": {
                "type": "integer",
                "description": "Maximum wall-clock seconds for prepare_models download work before returning partial state.",
            },
            "max_files": {
                "type": "integer",
                "description": "Maximum number of package files to process in one prepare_models call.",
            },
            "source": {
                "type": "string",
                "description": "Optional source override. Only local is supported.",
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
            "model_format": {
                "type": "string",
                "description": "Optional format override: auto, checkpoint, or gguf.",
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

    MODULE_TO_PIP_PACKAGE = {
        "gguf": "gguf>=0.18.0",
        "av": "av",
        "yaml": "PyYAML",
        "PIL": "Pillow",
        "cv2": "opencv-python",
        "bs4": "beautifulsoup4",
        "skimage": "scikit-image",
        "comfy_kitchen": "comfy-kitchen",
        "onnxruntime_gpu": "onnxruntime-gpu",
        "google.protobuf": "protobuf",
    }
    AUTO_INSTALLABLE_MODULE_ROOTS = {
        "einops",
        "numpy",
        "scipy",
        "requests",
        "safetensors",
        "transformers",
        "diffusers",
        "accelerate",
        "torch",
        "torchaudio",
        "torchvision",
        "xformers",
        "modelscope",
        "librosa",
        "soundfile",
        "onnx",
        "onnxruntime",
        "gguf",
        "av",
    }
    AUTO_INSTALL_TIMEOUT_SECONDS = 20 * 60
    AUTO_INSTALL_MAX_ATTEMPTS_DEFAULT = 6
    MIN_TORCH_SEED = -(1 << 63)
    MAX_TORCH_SEED = (1 << 64) - 1
    MODEL_PACKAGES = {
        "ernie-image-turbo-gguf": {
            "display_name": "ERNIE-Image-Turbo GGUF",
            "source": "Comfy-Org/ERNIE-Image + unsloth/ERNIE-Image-Turbo-GGUF",
            "files": [
                {
                    "kind": "clip",
                    "relative_path": "text_encoders/ministral-3-3b.safetensors",
                    "url": "https://huggingface.co/Comfy-Org/ERNIE-Image/resolve/main/text_encoders/ministral-3-3b.safetensors",
                    "required": True,
                    "size_bytes": 7717637511,
                },
                {
                    "kind": "vae",
                    "relative_path": "vae/flux2-vae.safetensors",
                    "url": "https://huggingface.co/Comfy-Org/ERNIE-Image/resolve/main/vae/flux2-vae.safetensors",
                    "required": True,
                    "size_bytes": 336213556,
                },
                {
                    "kind": "prompt_enhancer",
                    "relative_path": "text_encoders/ernie-image-prompt-enhancer.safetensors",
                    "url": "https://huggingface.co/Comfy-Org/ERNIE-Image/resolve/main/text_encoders/ernie-image-prompt-enhancer.safetensors",
                    "required": False,
                    "size_bytes": 6877439999,
                },
            ],
        }
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self._project_root = Path(context.get("project_root", Path.cwd())) if context else Path.cwd()

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "generate")
        source = normalize_tti_source(kwargs.get("source"), default="local")
        if action == "list_models":
            return f"Listing {source} text-to-image models"
        if action == "diagnose":
            return f"Diagnosing {source} text-to-image runtime"
        if action == "prepare_models":
            return "Preparing app-local text-to-image model package"
        return "Generating image with local text-to-image model"

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "generate")
        config = self._get_t2i_config()
        source = normalize_tti_source(kwargs.get("source", config.get("active_source", "local")))
        if action == "list_models":
            return self._list_models(source=source)
        if action == "diagnose":
            return self._diagnose(source=source)
        if action == "prepare_models":
            try:
                max_download_seconds = int(kwargs.get("max_download_seconds", 10 * 60) or 0)
                max_files = int(kwargs.get("max_files", 0) or 0)
            except (TypeError, ValueError):
                return ToolResult.fail("max_download_seconds and max_files must be integers")
            return self._prepare_model_package(
                package_id=str(kwargs.get("package") or "ernie-image-turbo-gguf"),
                download=bool(kwargs.get("download", False)),
                include_optional=bool(kwargs.get("include_optional", False)),
                max_download_seconds=max_download_seconds,
                max_files=max_files,
            )
        if action != "generate":
            return ToolResult.fail(f"Unsupported action: {action}")

        if kwargs.get("script_path"):
            return ToolResult.fail("script_path override is disabled in secure mode.")
        if kwargs.get("extra_args"):
            return ToolResult.fail("extra_args is disabled in secure mode.")
        if kwargs.get("extra_options"):
            return ToolResult.fail("extra_options is disabled in secure mode.")

        prompt = kwargs.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail("Parameter 'prompt' is required for generate action")

        if not config.get("enabled", True):
            return ToolResult.fail("text_to_image is disabled in config.json (text_to_image.enabled=false)")

        script_path = self._resolve_script_path(config=config, script_override=None)
        if not script_path.exists():
            return ToolResult.fail(
                f"Text-to-image script not found: {script_path}. "
                "Please check text_to_image.script_path in config.json or bundled resources."
            )
        if not self._is_trusted_runtime_script(script_path):
            return ToolResult.fail(
                "text_to_image generation is disabled in secure workspace mode unless Reverie is "
                "using its bundled immutable runtime resources."
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
        model_package = self._resolve_model_package(selected_model, format_override=kwargs.get("model_format"))
        model_path = model_package["model_path"]
        model_display_name = selected_model["display_name"]
        if model_path is None or not model_path.exists():
            return ToolResult.fail(
                f"Model file not found for display name '{model_display_name}'. "
                f"Configured path: {selected_model.get('path', '')}"
            )
        model_format = model_package["format"]

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
            width = int(kwargs.get("width", selected_model.get("recommended_width", config.get("default_width", 512))))
            height = int(kwargs.get("height", selected_model.get("recommended_height", config.get("default_height", 512))))
            steps = int(kwargs.get("steps", selected_model.get("recommended_steps", config.get("default_steps", 20))))
            cfg = float(kwargs.get("cfg", selected_model.get("recommended_cfg", config.get("default_cfg", 8.0))))
            batch_size = int(kwargs.get("batch_size", 1))
        except (TypeError, ValueError):
            return ToolResult.fail("width/height/steps/cfg/batch_size must be valid numeric values")
        sampler = str(kwargs.get("sampler", selected_model.get("recommended_sampler", config.get("default_sampler", "euler"))))
        scheduler = str(kwargs.get("scheduler", selected_model.get("recommended_scheduler", config.get("default_scheduler", "normal"))))
        seed = kwargs.get("seed", None)
        if seed is not None:
            try:
                seed = int(seed)
            except (TypeError, ValueError):
                return ToolResult.fail("seed must be an integer")
            if seed < self.MIN_TORCH_SEED or seed > self.MAX_TORCH_SEED:
                return ToolResult.fail(
                    f"seed must be between {self.MIN_TORCH_SEED} and {self.MAX_TORCH_SEED}"
                )

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
            "--model-format",
            model_format,
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
        aux_args = self._build_auxiliary_model_args(selected_model, model_package=model_package)
        cmd.extend(aux_args)
        if seed is not None:
            cmd.extend(["--seed", str(seed)])
        if use_cpu:
            cmd.append("--cpu")

        timeout_seconds = kwargs.get("timeout_seconds", 60 * 60)
        try:
            timeout_seconds = int(timeout_seconds)
        except (TypeError, ValueError):
            return ToolResult.fail("timeout_seconds must be an integer")
        if timeout_seconds <= 0:
            return ToolResult.fail("timeout_seconds must be a positive integer")

        auto_install_reports: List[Dict[str, Any]] = []
        run_cwd = self._project_root
        result = None
        run_error = None
        auto_install_enabled = self._is_truthy(
            selected_model.get("auto_install_missing_deps"),
            default=self._is_truthy(config.get("auto_install_missing_deps"), default=False),
        )
        max_attempts = self._coerce_positive_int(
            config.get("auto_install_max_missing_deps"),
            self.AUTO_INSTALL_MAX_ATTEMPTS_DEFAULT,
            self.AUTO_INSTALL_MAX_ATTEMPTS_DEFAULT,
        )
        attempted_modules = set()

        for _attempt in range(max_attempts + 1):
            result, run_error = self._run_process(cmd=cmd, cwd=run_cwd, timeout_seconds=timeout_seconds)
            if run_error:
                return ToolResult.fail(run_error)
            if result is None:
                return ToolResult.fail("Text-to-image generation did not return a process result")
            missing_module = self._extract_missing_module_name(result.stdout or "", result.stderr or "")
            if result.returncode == 0 or not auto_install_enabled or not missing_module:
                break
            if missing_module in attempted_modules:
                break
            attempted_modules.add(missing_module)
            install_report = self._install_missing_module(python_exe=python_exe, module_name=missing_module)
            auto_install_reports.append(install_report)
            if not install_report.get("installed"):
                break

        if result is None:
            return ToolResult.fail("Text-to-image generation did not return a process result")

        saved_images = self._parse_saved_images(result.stdout or "")
        output_lines = [
            f"Command exit code: {result.returncode}",
            f"Model display name: {model_display_name}",
            f"Model path: {model_path}",
            f"Model format: {model_format}",
            f"Output target: {output_path}",
        ]

        if saved_images:
            output_lines.append("Generated images:")
            output_lines.extend(f"- {p}" for p in saved_images)
        if auto_install_reports:
            output_lines.append("\n--- AUTO INSTALL ---")
            for idx, report in enumerate(auto_install_reports, start=1):
                module_name = report.get("module") or "<unknown>"
                package_name = report.get("package") or "<unknown>"
                status = "success" if report.get("installed") else "failed"
                output_lines.append(f"[{idx}] {module_name} -> {package_name} ({status})")
                log_text = str(report.get("log", "") or "").strip()
                if log_text:
                    output_lines.append(log_text)
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
                    "model_format": model_format,
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
        cfg["active_source"] = normalize_tti_source(cfg.get("active_source", "local"))
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

    def _list_models(self, source: str = "local") -> ToolResult:
        config = self._get_t2i_config()
        source = normalize_tti_source(source or config.get("active_source", "local"))
        models = config.get("models", [])
        default_display_name = str(config.get("default_model_display_name", "")).strip()

        if not models:
            return ToolResult.ok(
                "No text-to-image models configured.\n"
                "Set text_to_image.models in config.json with one or more model entries.",
                data={"models": [], "source": "local"},
            )

        rows = []
        data_rows = []
        for idx, item in enumerate(models):
            display_name = item["display_name"]
            configured_path = item["path"]
            introduction = item.get("introduction", "")
            package_info = self._resolve_model_package(item)
            resolved = package_info["configured_path"]
            model_path = package_info["model_path"]
            exists = bool(model_path and model_path.exists())
            model_format = package_info["format"]
            aux_status = self._summarize_auxiliary_models(item, package_info=package_info) if model_format == "gguf" else []
            marker = "*" if display_name.lower() == default_display_name.lower() else " "
            intro_text = f" | intro: {introduction}" if introduction else ""
            format_text = f" | format: {model_format}"
            aux_text = ""
            if aux_status:
                present = sum(1 for aux in aux_status if aux["exists"])
                aux_text = f" | aux: {present}/{len(aux_status)}"
            rows.append(
                f"{marker}[{idx}] {display_name} | {configured_path} -> {resolved} "
                f"({'OK' if exists else 'NOT FOUND'}){format_text}{aux_text}{intro_text}"
            )
            data_rows.append(
                {
                    "index": idx,
                    "display_name": display_name,
                    "configured_path": configured_path,
                    "resolved_path": str(resolved),
                    "model_path": str(model_path or ""),
                    "package_root": str(package_info.get("package_root") or ""),
                    "exists": exists,
                    "format": model_format,
                    "auxiliary_models": aux_status,
                    "is_default": display_name.lower() == default_display_name.lower(),
                    "introduction": introduction,
                }
            )

        return ToolResult.ok(
            "Configured text-to-image models:\n" + "\n".join(rows),
            data={"models": data_rows, "source": "local"},
        )

    def _model_package_root(self) -> Path:
        return get_app_root() / ".reverie" / "plugins" / "Packages" / "comfyui" / "models"

    def _prepare_model_package(
        self,
        package_id: str,
        download: bool = False,
        include_optional: bool = False,
        max_download_seconds: int = 10 * 60,
        max_files: int = 0,
    ) -> ToolResult:
        package_key = str(package_id or "").strip().lower()
        package = self.MODEL_PACKAGES.get(package_key)
        if package is None:
            available = ", ".join(sorted(self.MODEL_PACKAGES))
            return ToolResult.fail(f"Unknown model package '{package_id}'. Available packages: {available}")

        root = self._model_package_root()
        records: List[Dict[str, Any]] = []
        failures: List[str] = []
        started = time.monotonic()
        deadline = started + max(1, max_download_seconds) if max_download_seconds > 0 else None
        processed_downloads = 0
        for file_spec in package["files"]:
            if not bool(file_spec.get("required", False)) and not include_optional:
                skipped_target = (root / Path(str(file_spec["relative_path"]))).resolve()
                records.append(
                    {
                        "kind": file_spec["kind"],
                        "required": False,
                        "target": str(skipped_target),
                        "url": file_spec["url"],
                        "size_bytes": int(file_spec.get("size_bytes", 0) or 0),
                        "exists": skipped_target.exists(),
                        "downloaded": False,
                        "skipped_optional": True,
                    }
                )
                continue
            relative = Path(str(file_spec["relative_path"]))
            target = (root / relative).resolve()
            exists_before = target.exists()
            downloaded = False
            if download and not exists_before:
                if max_files > 0 and processed_downloads >= max_files:
                    failures.append(f"{relative}: skipped because max_files={max_files} was reached")
                elif deadline is not None and time.monotonic() >= deadline:
                    failures.append(f"{relative}: skipped because max_download_seconds={max_download_seconds} was reached")
                else:
                    processed_downloads += 1
                    remaining_seconds = None if deadline is None else max(1, int(deadline - time.monotonic()))
                    try:
                        self._download_file(
                            str(file_spec["url"]),
                            target,
                            package_root=root,
                            max_duration_seconds=remaining_seconds,
                        )
                        downloaded = True
                    except Exception as exc:
                        failures.append(f"{relative}: {exc}")
            records.append(
                {
                    "kind": file_spec["kind"],
                    "required": bool(file_spec.get("required", False)),
                    "target": str(target),
                    "url": file_spec["url"],
                    "size_bytes": int(file_spec.get("size_bytes", 0) or 0),
                    "exists": target.exists(),
                    "downloaded": downloaded,
                    "skipped_optional": False,
                }
            )

        required_ready = all(item["exists"] for item in records if item["required"])
        lines = [
            f"Model package: {package['display_name']}",
            f"Depot: {root}",
            f"Download: {'yes' if download else 'no'}",
        ]
        for record in records:
            size_gb = record["size_bytes"] / (1024 ** 3) if record["size_bytes"] else 0
            lines.append(
                f"- {record['kind']}: {'OK' if record['exists'] else 'MISSING'} | "
                f"{size_gb:.2f} GiB | {record['target']}"
                + (" | optional skipped" if record.get("skipped_optional") else "")
            )

        payload = {
            "package": package_key,
            "root": str(root),
            "files": records,
            "required_ready": required_ready,
            "failures": failures,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "max_download_seconds": max_download_seconds,
            "max_files": max_files,
        }
        if failures:
            return ToolResult.partial("\n".join(lines), "\n".join(failures), payload)
        if required_ready:
            return ToolResult.ok("\n".join(lines), payload)
        return ToolResult.partial(
            "\n".join(lines),
            "Required model package files are missing. Re-run with download=true or place them at the listed paths.",
            payload,
        )

    def _download_file(
        self,
        url: str,
        target: Path,
        *,
        package_root: Path | None = None,
        max_duration_seconds: Optional[int] = None,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if max_duration_seconds is None and self._download_huggingface_file(url, target, package_root=package_root):
            return

        temp_path = target.with_suffix(target.suffix + ".part")
        resume_from = temp_path.stat().st_size if temp_path.exists() else 0
        deadline = time.monotonic() + max(1, int(max_duration_seconds)) if max_duration_seconds else None
        headers = {"User-Agent": "ReverieCLI/ComfyModelPackage"}
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
        request = Request(url, headers=headers)
        mode = "ab" if resume_from > 0 else "wb"
        with urlopen(request, timeout=600) as response:
            if resume_from > 0 and getattr(response, "status", 200) == 200:
                mode = "wb"
            with temp_path.open(mode) as handle:
                while True:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError(
                            "download time budget reached; partial file was kept and the next call can resume"
                        )
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        temp_path.replace(target)

    def _download_huggingface_file(self, url: str, target: Path, *, package_root: Path | None = None) -> bool:
        parsed = self._parse_huggingface_resolve_url(url)
        if parsed is None:
            return False
        try:
            from huggingface_hub import hf_hub_download
        except Exception:
            return False

        root = Path(package_root or target.parent).resolve()
        cache_dir = root / ".cache" / "huggingface"
        try:
            downloaded = hf_hub_download(
                repo_id=parsed["repo_id"],
                filename=parsed["filename"],
                revision=parsed["revision"],
                local_dir=str(root),
                cache_dir=str(cache_dir),
                etag_timeout=60,
            )
        except Exception:
            return False

        downloaded_path = Path(downloaded)
        if not target.exists() and downloaded_path.exists() and downloaded_path.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(downloaded_path, target)
        return target.exists()

    @staticmethod
    def _parse_huggingface_resolve_url(url: str) -> Optional[Dict[str, str]]:
        parsed = urlparse(str(url or ""))
        host = parsed.netloc.lower()
        if host != "huggingface.co":
            return None
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if "resolve" not in parts:
            return None
        resolve_index = parts.index("resolve")
        if resolve_index < 1 or len(parts) <= resolve_index + 2:
            return None
        repo_id = "/".join(parts[:resolve_index])
        revision = parts[resolve_index + 1]
        filename = "/".join(parts[resolve_index + 2 :])
        if not repo_id or not revision or not filename:
            return None
        return {"repo_id": repo_id, "revision": revision, "filename": filename}

    def _diagnose(self, source: str = "local") -> ToolResult:
        config = self._get_t2i_config()
        source = normalize_tti_source(source or config.get("active_source", "local"))
        script_path = self._resolve_script_path(config=config, script_override=None)
        python_exe = self._select_python_executable(config=config, script_path=script_path)
        models = []
        for item in config.get("models", []):
            package_info = self._resolve_model_package(item)
            resolved = package_info["configured_path"]
            model_path = package_info["model_path"]
            model_format = package_info["format"]
            aux_status = self._summarize_auxiliary_models(item, package_info=package_info) if model_format == "gguf" else []
            models.append(
                {
                    "display_name": item.get("display_name", ""),
                    "configured_path": item.get("path", ""),
                    "resolved_path": str(resolved),
                    "model_path": str(model_path or ""),
                    "package_root": str(package_info.get("package_root") or ""),
                    "exists": bool(model_path and model_path.exists()),
                    "format": model_format,
                    "auxiliary_models": aux_status,
                }
            )
        has_gguf_model = any(item.get("format") == "gguf" for item in models if item.get("exists"))
        gguf_aux_ready = all(
            all(aux.get("exists") for aux in item.get("auxiliary_models", []))
            and bool(item.get("auxiliary_models"))
            for item in models
            if item.get("exists") and item.get("format") == "gguf"
        )
        module_checks = []
        if python_exe is not None and python_exe.exists():
            module_checks.append({"module": "torch", **self._probe_python_module(python_exe, "torch")})
            module_checks.append({"module": "PIL", **self._probe_python_module(python_exe, "PIL")})
            if has_gguf_model:
                module_checks.append({"module": "gguf", **self._probe_python_module(python_exe, "gguf")})
        modules_ready = all(item.get("ok") for item in module_checks) if module_checks else False
        checks = [
            {"id": "enabled", "ok": bool(config.get("enabled", True)), "detail": "text_to_image.enabled"},
            {"id": "source", "ok": source == "local", "detail": f"active source: {source}"},
            {"id": "script", "ok": script_path.exists(), "detail": str(script_path)},
            {"id": "trusted_script", "ok": script_path.exists() and self._is_trusted_runtime_script(script_path), "detail": "bundled immutable runtime resource required"},
            {"id": "python", "ok": python_exe is not None and python_exe.exists(), "detail": str(python_exe or "")},
            {"id": "python_modules", "ok": modules_ready, "detail": ", ".join(f"{m['module']}={'ok' if m['ok'] else 'missing'}" for m in module_checks) if module_checks else "not checked"},
            {"id": "models", "ok": any(item["exists"] for item in models), "detail": f"{sum(1 for item in models if item['exists'])}/{len(models)} configured model files exist"},
            {"id": "gguf_auxiliary", "ok": (not has_gguf_model) or gguf_aux_ready, "detail": "GGUF diffusion models require text encoder and VAE paths"},
        ]
        ready = all(item["ok"] for item in checks)
        output = "Text-to-image local runtime diagnosis\n"
        output += f"Ready: {'yes' if ready else 'no'}\n"
        for check in checks:
            output += f"- {check['id']}: {'ok' if check['ok'] else 'missing'} | {check['detail']}\n"
        if not models:
            output += "No models are configured under text_to_image.models.\n"
        else:
            for model in models:
                output += (
                    f"Model {model.get('display_name')}: {model.get('format')} | "
                    f"{'OK' if model.get('exists') else 'NOT FOUND'} | {model.get('resolved_path')}\n"
                )
                for aux in model.get("auxiliary_models", []):
                    output += (
                        f"  aux {aux['kind']}: {'OK' if aux['exists'] else 'MISSING'} | "
                        f"{aux['resolved_path']}\n"
                    )
        payload = {"ready": ready, "checks": checks, "models": models, "source": source, "module_checks": module_checks}
        return (
            ToolResult.ok(output, payload)
            if ready
            else ToolResult.partial(
                output,
                "Local text_to_image is not ready; configure the missing script, Python runtime, or model files.",
                payload,
            )
        )

    def _infer_model_format(
        self,
        model: Dict[str, Any],
        model_path: Path,
        override: Any = None,
    ) -> str:
        raw = override
        if raw is None:
            raw = model.get("model_format", model.get("format", "auto"))
        candidate = str(raw or "auto").strip().lower()
        if candidate in {"checkpoint", "ckpt", "safetensors"}:
            return "checkpoint"
        if candidate == "gguf":
            return "gguf"
        if model_path.is_dir():
            detected = self._find_first_existing(
                model_path,
                [
                    "*ernie*image*turbo*.gguf",
                    "*.gguf",
                    "diffusion_models/*.safetensors",
                    "*.safetensors",
                    "*.ckpt",
                ],
            )
            if detected:
                return "gguf" if detected.suffix.lower() == ".gguf" else "checkpoint"
        return "gguf" if str(model_path).lower().endswith(".gguf") else "checkpoint"

    def _resolve_model_package(
        self,
        model: Dict[str, Any],
        *,
        format_override: Any = None,
    ) -> Dict[str, Any]:
        configured_path = self._resolve_path(str(model.get("path", "")))
        package_root = configured_path if configured_path.is_dir() else configured_path.parent
        explicit_model = model.get("model_file") or model.get("main_model") or model.get("diffusion_model")
        model_path: Optional[Path] = None

        if explicit_model:
            model_path = self._resolve_package_relative_path(str(explicit_model), package_root)
        elif configured_path.is_file():
            model_path = configured_path
        elif configured_path.is_dir():
            model_path = self._find_first_existing(
                configured_path,
                [
                    "*ernie*image*turbo*.gguf",
                    "*.gguf",
                    "diffusion_models/*ernie*image*turbo*.safetensors",
                    "diffusion_models/*.safetensors",
                    "*.safetensors",
                    "*.ckpt",
                ],
            )

        if model_path is not None:
            package_root = configured_path if configured_path.is_dir() else model_path.parent

        model_format = self._infer_model_format(
            model,
            model_path or configured_path,
            override=format_override,
        )
        aux = {
            "clip": self._resolve_auxiliary_path(
                model,
                package_root,
                keys=("clip_model", "text_encoder"),
                patterns=(
                    "text_encoders/ministral-3-3b.safetensors",
                    "ministral-3-3b.safetensors",
                    "text_encoders/*ministral*.safetensors",
                    "**/ministral-3-3b.safetensors",
                    "**/*ministral*.safetensors",
                ),
            ),
            "vae": self._resolve_auxiliary_path(
                model,
                package_root,
                keys=("vae_model", "vae"),
                patterns=(
                    "vae/flux2-vae.safetensors",
                    "flux2-vae.safetensors",
                    "vae/*vae*.safetensors",
                    "**/flux2-vae.safetensors",
                    "**/*vae*.safetensors",
                ),
            ),
            "prompt_enhancer": self._resolve_auxiliary_path(
                model,
                package_root,
                keys=("prompt_enhancer_model",),
                patterns=(
                    "text_encoders/ernie-image-prompt-enhancer.safetensors",
                    "ernie-image-prompt-enhancer.safetensors",
                    "**/*prompt*enhancer*.safetensors",
                ),
            ),
        }
        return {
            "configured_path": configured_path,
            "package_root": package_root,
            "model_path": model_path,
            "format": model_format,
            "auxiliary": aux,
        }

    def _resolve_package_relative_path(self, raw_path: str, package_root: Path) -> Path:
        sanitized = sanitize_tti_path(raw_path)
        candidate = Path(os.path.expandvars(sanitized)).expanduser()
        if candidate.is_absolute() or self._looks_like_absolute_path(sanitized):
            return candidate
        package_candidate = (package_root / candidate).resolve()
        if package_candidate.exists():
            return package_candidate
        return self._resolve_path(sanitized)

    def _resolve_auxiliary_path(
        self,
        model: Dict[str, Any],
        package_root: Path,
        *,
        keys: tuple[str, ...],
        patterns: tuple[str, ...],
    ) -> Optional[Path]:
        for key in keys:
            raw = model.get(key)
            if raw is None:
                continue
            resolved = self._resolve_package_relative_path(str(raw), package_root)
            if resolved.exists():
                return resolved
            return resolved
        return self._find_first_existing(package_root, list(patterns))

    def _find_first_existing(self, root: Path, patterns: List[str]) -> Optional[Path]:
        if not root or not root.exists() or not root.is_dir():
            return None
        for pattern in patterns:
            direct = root / pattern
            if not any(ch in pattern for ch in "*?[]") and direct.exists():
                return direct.resolve()
            matches = sorted(
                (path for path in root.glob(pattern) if path.is_file()),
                key=lambda path: (len(path.parts), str(path).lower()),
            )
            if matches:
                return matches[0].resolve()
        return None

    def _build_auxiliary_model_args(self, model: Dict[str, Any], *, model_package: Optional[Dict[str, Any]] = None) -> List[str]:
        args: List[str] = []
        package = model_package or self._resolve_model_package(model)
        aux_map = {
            "clip": "--clip-model",
            "vae": "--vae-model",
            "prompt_enhancer": "--prompt-enhancer-model",
        }
        for kind, flag in aux_map.items():
            resolved = (package.get("auxiliary") or {}).get(kind)
            if resolved is None:
                continue
            args.extend([flag, str(resolved)])

        clip_type = str(model.get("clip_type", "") or "").strip()
        if clip_type:
            args.extend(["--clip-type", clip_type])
        return args

    def _summarize_auxiliary_models(
        self,
        model: Dict[str, Any],
        *,
        package_info: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        package = package_info or self._resolve_model_package(model)
        summaries: List[Dict[str, Any]] = []
        for kind in ("clip", "vae", "prompt_enhancer"):
            resolved = (package.get("auxiliary") or {}).get(kind)
            configured = {
                "clip": model.get("clip_model") or model.get("text_encoder"),
                "vae": model.get("vae_model") or model.get("vae"),
                "prompt_enhancer": model.get("prompt_enhancer_model"),
            }.get(kind)
            if resolved is None:
                if kind in {"clip", "vae"}:
                    summaries.append(
                        {
                            "kind": kind,
                            "configured_path": str(configured or ""),
                            "resolved_path": "",
                            "exists": False,
                            "required": True,
                            "source": "missing",
                        }
                    )
                continue
            summaries.append(
                {
                    "kind": kind,
                    "configured_path": str(configured or ""),
                    "resolved_path": str(resolved),
                    "exists": resolved.exists(),
                    "required": kind in {"clip", "vae"},
                    "source": "explicit" if configured else "auto",
                }
            )
        return summaries

    def _probe_python_module(self, python_exe: Path, module_name: str) -> Dict[str, Any]:
        cmd = [
            str(python_exe),
            "-c",
            (
                "import importlib.util, sys; "
                f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
            ),
        ]
        result, error = self._run_process(cmd=cmd, cwd=self._project_root, timeout_seconds=30)
        if error:
            return {"ok": False, "detail": error}
        return {
            "ok": bool(result and result.returncode == 0),
            "detail": (result.stderr or result.stdout or "").strip() if result else "",
        }

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
            return self.resolve_workspace_path(out_path, purpose="write generated images")

        return self.resolve_workspace_path(out_path, purpose="write generated images")

    def _is_trusted_runtime_script(self, script_path: Path) -> bool:
        bundled_dir = self._get_bundled_comfy_dir()
        if not bundled_dir:
            return False
        bundled_root = bundled_dir.resolve()
        script_resolved = script_path.resolve()
        return (
            script_resolved == bundled_root
            or bundled_root in script_resolved.parents
        ) and not is_path_within_workspace(script_resolved, self._project_root)

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

    def _run_process(
        self,
        cmd: List[str],
        cwd: Path,
        timeout_seconds: int,
    ) -> tuple[Optional[subprocess.CompletedProcess[str]], Optional[str]]:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            return result, None
        except subprocess.TimeoutExpired:
            return None, f"Image generation timed out after {timeout_seconds} seconds"
        except Exception as exc:
            return None, f"Failed to launch text-to-image generation: {exc}"

    def _install_missing_module(self, python_exe: Path, module_name: str) -> Dict[str, Any]:
        package_name = self._resolve_package_for_module(module_name)
        if not package_name:
            return {
                "attempted": False,
                "installed": False,
                "module": module_name,
                "package": "",
                "log": f"Cannot auto-install unknown module '{module_name}'.",
            }

        cmd = [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            package_name,
        ]
        result, error = self._run_process(
            cmd=cmd,
            cwd=self._project_root,
            timeout_seconds=self.AUTO_INSTALL_TIMEOUT_SECONDS,
        )
        if error:
            return {
                "attempted": True,
                "installed": False,
                "module": module_name,
                "package": package_name,
                "log": error,
            }

        install_log = ""
        if result and result.stdout:
            install_log += result.stdout.strip()
        if result and result.stderr:
            install_log += ("\n" if install_log else "") + result.stderr.strip()

        return {
            "attempted": True,
            "installed": bool(result and result.returncode == 0),
            "module": module_name,
            "package": package_name,
            "log": install_log,
        }

    def _resolve_package_for_module(self, module_name: str) -> Optional[str]:
        raw = str(module_name or "").strip()
        if not raw:
            return None

        if raw in self.MODULE_TO_PIP_PACKAGE:
            return self.MODULE_TO_PIP_PACKAGE[raw]

        root = raw.split(".", 1)[0].strip()
        if not root:
            return None

        if root in self.MODULE_TO_PIP_PACKAGE:
            return self.MODULE_TO_PIP_PACKAGE[root]

        if root in self.AUTO_INSTALLABLE_MODULE_ROOTS:
            return root

        return None

    @staticmethod
    def _is_truthy(value: Any, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    @staticmethod
    def _coerce_positive_int(value: Any, default: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        if parsed <= 0:
            parsed = default
        return min(parsed, max_value)

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
