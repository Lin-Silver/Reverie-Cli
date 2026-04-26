"""Blender SDK/runtime plugin for Reverie CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile


PLUGIN_VERSION = "0.3.0"
ARCHIVE_NAME = "blender-5.1.1-windows-x64.zip"
MMD_TOOLS_REPO_URL = "https://github.com/MMD-Blender/blender_mmd_tools.git"
MMD_TOOLS_MODULE = "mmd_tools"
MMD_TOOLS_STATUS_MARKER = "REVERIE_MMD_TOOLS_STATUS="
MMD_IMPORT_STATUS_MARKER = "REVERIE_MMD_IMPORT_RESULT="
MMD_MODEL_EXTENSIONS = {".pmd", ".pmx"}
MMD_MOTION_EXTENSIONS = {".vmd"}
MMD_POSE_EXTENSIONS = {".vpd"}


class ReverieRuntimePluginHost:
    """Small inlined host for Reverie CLI's fixed `-RC` plugin protocol."""

    def build_handshake(self) -> dict[str, Any]:
        raise NotImplementedError

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def write_json(self, payload: dict[str, Any]) -> int:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
        sys.stdout.flush()
        return 0

    def run(self, argv: list[str]) -> int:
        if len(argv) >= 2 and argv[1] == "-RC":
            return self.write_json(self.build_handshake())

        if len(argv) >= 2 and argv[1] == "-RC-CALL":
            if len(argv) < 4:
                return self.write_json(
                    {
                        "success": False,
                        "output": "",
                        "error": "Usage: -RC-CALL <command> <json-payload>",
                        "data": {},
                    }
                )

            command_name = str(argv[2] or "").strip().lower()
            raw_payload = str(argv[3] or "").strip()
            try:
                payload = json.loads(raw_payload) if raw_payload else {}
            except Exception as exc:
                return self.write_json(
                    {
                        "success": False,
                        "output": "",
                        "error": f"Invalid JSON payload: {exc}",
                        "data": {},
                    }
                )

            try:
                result = self.handle_command(command_name, payload)
            except Exception as exc:
                result = {"success": False, "output": "", "error": str(exc), "data": {}}
            if not isinstance(result, dict):
                result = {
                    "success": False,
                    "output": "",
                    "error": "Plugin command handler must return a JSON object.",
                    "data": {},
                }
            result.setdefault("success", False)
            result.setdefault("output", "")
            result.setdefault("error", "")
            result.setdefault("data", {})
            return self.write_json(result)

        sys.stderr.write("This runtime plugin only supports -RC and -RC-CALL.\n")
        return 1


class BlenderRuntimePlugin(ReverieRuntimePluginHost):
    """Protocol wrapper around a portable or installed Blender runtime."""

    def __init__(self) -> None:
        self.plugin_root = self._resolve_plugin_root()
        self.runtime_root = self.plugin_root / "runtime"
        self.addons_root = self.plugin_root / "addons"
        self.mmd_tools_root = self.addons_root / "blender_mmd_tools"
        self.config_root = self.plugin_root / "config"
        self.scripts_root = self.plugin_root / "scripts"
        self.datafiles_root = self.plugin_root / "datafiles"
        self.tmp_root = self.plugin_root / "tmp"

    def build_handshake(self) -> dict[str, Any]:
        return {
            "protocol_version": "1.0",
            "plugin_id": "blender",
            "display_name": "Blender SDK Plugin",
            "version": PLUGIN_VERSION,
            "runtime_family": "dcc",
            "description": (
                "Self-contained portable Blender plugin with an embedded Blender archive, "
                "plugin-local deployment, version checks, launch, background bpy script "
                "execution, scene metadata inspection, and plugin-local MMD Tools support "
                "for PMD/PMX model, VMD motion, and VPD pose import."
            ),
            "tool_call_hint": (
                "Use rc_blender_ensure_runtime to deploy the embedded portable Blender "
                "environment, then rc_blender_run_script for background asset authoring. "
                "Use rc_blender_ensure_mmd_tools or rc_blender_import_mmd_model when "
                "working with MMD PMD/PMX/VMD/VPD assets. "
                "Use blender_modeling_workbench to generate production Blender scripts "
                "and this plugin to provide the actual Blender executable."
            ),
            "system_prompt": (
                "This plugin owns the local portable Blender environment. It can unpack the "
                "Blender archive embedded in the plugin executable into the plugin runtime "
                "folder, report readiness, launch Blender, and run generated bpy scripts. "
                "It can also clone/update the open-source MMD Tools Blender add-on into "
                "the plugin-local addons folder, enable it with plugin-local Blender user "
                "config, and import .pmx/.pmd models with optional .vmd motion or .vpd pose. "
                "For AI modeling workflows, combine blender_modeling_workbench for script/"
                "asset planning with rc_blender_ensure_runtime and rc_blender_run_script "
                "for execution."
            ),
            "commands": [
                {
                    "name": "ensure_runtime",
                    "description": "Deploy the Blender archive embedded in this plugin executable into the plugin-local runtime folder.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "force": {
                                "type": "boolean",
                                "description": "When true, replace the existing plugin-local Blender runtime before extracting."
                            },
                            "with_mmd_tools": {
                                "type": "boolean",
                                "description": "Also clone/update MMD Tools into the plugin-local addons folder. Defaults to true."
                            },
                            "enable_mmd_tools": {
                                "type": "boolean",
                                "description": "After deployment, run Blender once in background to verify/enable MMD Tools. Defaults to false."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Call this before direct Blender execution when a portable runtime may not be deployed yet."
                },
                {
                    "name": "runtime_status",
                    "description": "Inspect Blender runtime readiness, embedded archive availability, plugin-local roots, and detected executable.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute path override for this check."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Call this before attempting direct Blender execution."
                },
                {
                    "name": "mmd_tools_status",
                    "description": "Inspect plugin-local MMD Tools checkout, Python import paths, git status, and Blender enablement readiness.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute Blender executable path for an enablement probe."
                            },
                            "probe_blender": {
                                "type": "boolean",
                                "description": "When true, run a short Blender background probe to check that MMD Tools can be enabled."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Use this before importing .pmx/.pmd assets when you need to know whether the add-on is already installed."
                },
                {
                    "name": "ensure_mmd_tools",
                    "description": "Clone or update MMD Tools from GitHub into the plugin-local addons folder and optionally verify it in Blender.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "force": {
                                "type": "boolean",
                                "description": "Replace an existing plugin-local MMD Tools checkout."
                            },
                            "update": {
                                "type": "boolean",
                                "description": "Pull the latest checkout when a git clone already exists. Defaults to true."
                            },
                            "enable": {
                                "type": "boolean",
                                "description": "Run Blender in background to enable/probe the add-on after checkout."
                            },
                            "dry_run": {
                                "type": "boolean",
                                "description": "Report planned paths and commands without cloning or running Blender."
                            },
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute Blender executable path used for enablement."
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Git or Blender probe timeout."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Use this when an MMD asset workflow is requested; files stay under .reverie/plugins/blender/addons/."
                },
                {
                    "name": "detect_runtime",
                    "description": "Find a usable Blender executable from overrides, the plugin depot, PATH, or common install folders.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute Blender executable path."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": []
                },
                {
                    "name": "version",
                    "description": "Return Blender's --version output.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute Blender executable path."
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Version probe timeout."
                            },
                            "auto_prepare": {
                                "type": "boolean",
                                "description": "Automatically deploy the embedded portable runtime if Blender is missing. Defaults to true."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": []
                },
                {
                    "name": "open_blender",
                    "description": "Launch Blender for interactive user work.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "blend_path": {
                                "type": "string",
                                "description": "Optional .blend file to open."
                            },
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute Blender executable path."
                            },
                            "auto_prepare": {
                                "type": "boolean",
                                "description": "Automatically deploy the embedded portable runtime if Blender is missing. Defaults to true."
                            },
                            "with_mmd_tools": {
                                "type": "boolean",
                                "description": "Automatically prepare and enable MMD Tools before launch. Defaults to true."
                            }
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": []
                },
                {
                    "name": "run_script",
                    "description": "Run a Blender Python script in background mode.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "script_path": {
                                "type": "string",
                                "description": "Absolute or working-directory-relative Python script path."
                            },
                            "blend_path": {
                                "type": "string",
                                "description": "Optional .blend file to load before running the script."
                            },
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute Blender executable path."
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Execution timeout."
                            },
                            "auto_prepare": {
                                "type": "boolean",
                                "description": "Automatically deploy the embedded portable runtime if Blender is missing. Defaults to true."
                            },
                            "auto_mmd_tools": {
                                "type": "boolean",
                                "description": "Automatically prepare and enable MMD Tools before running the script. Defaults to false."
                            }
                        },
                        "required": ["script_path"]
                    },
                    "expose_as_tool": True,
                    "include_modes": []
                },
                {
                    "name": "import_mmd_model",
                    "description": "Import an MMD PMD/PMX model through MMD Tools, optionally apply VMD motion or VPD pose, save .blend, and optionally export glTF/GLB.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model_path": {
                                "type": "string",
                                "description": "Absolute or working-directory-relative .pmx or .pmd model path."
                            },
                            "motion_path": {
                                "type": "string",
                                "description": "Optional .vmd motion path to apply after model import."
                            },
                            "pose_path": {
                                "type": "string",
                                "description": "Optional .vpd pose path to apply after model import."
                            },
                            "output_blend_path": {
                                "type": "string",
                                "description": "Optional .blend output path. Defaults to plugin-local imports/<model>.blend when save_blend is true."
                            },
                            "export_path": {
                                "type": "string",
                                "description": "Optional .glb or .gltf output path."
                            },
                            "export_format": {
                                "type": "string",
                                "description": "Optional glb or gltf default export format when export_path is not provided."
                            },
                            "scale": {
                                "type": "number",
                                "description": "MMD import scale. Defaults to MMD Tools' common 0.08 scale."
                            },
                            "save_blend": {
                                "type": "boolean",
                                "description": "Save a .blend source after import. Defaults to true."
                            },
                            "clear_scene": {
                                "type": "boolean",
                                "description": "Clear the default scene before import. Defaults to true."
                            },
                            "blender_executable": {
                                "type": "string",
                                "description": "Optional absolute Blender executable path."
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Import timeout."
                            },
                            "auto_prepare": {
                                "type": "boolean",
                                "description": "Automatically deploy Blender and MMD Tools if missing. Defaults to true."
                            }
                        },
                        "required": ["model_path"]
                    },
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Prefer this command for .pmx/.pmd game-asset ingestion instead of hand-writing add-on bootstrap code."
                }
            ]
        }

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command_name == "ensure_runtime":
            return self._ensure_runtime(payload)

        if command_name == "runtime_status":
            detection = self._detect_runtime(payload.get("blender_executable"))
            version = self._probe_version(detection.get("path"), int(payload.get("timeout_seconds") or 5)) if detection["available"] else {}
            archive = self._archive_status()
            return self._ok(
                "Blender runtime is ready." if detection["available"] else "Blender runtime was not detected.",
                {
                    "plugin_root": str(self.plugin_root),
                    "runtime_root": str(self.runtime_root),
                    "embedded_archive_available": bool(archive["available"]),
                    "archive": archive,
                    "detected": detection,
                    "version": version,
                    "mmd_tools": self._mmd_tools_status_data(),
                },
            )

        if command_name == "mmd_tools_status":
            data = self._mmd_tools_status_data()
            if bool(payload.get("probe_blender", False)):
                detection, deploy_result = self._ensure_ready_detection(payload)
                data["detected"] = detection
                data["deployment"] = deploy_result
                if detection["available"]:
                    data["enable_probe"] = self._enable_mmd_tools(detection["path"], int(payload.get("timeout_seconds") or 60))
            message = "MMD Tools add-on is installed." if data["installed"] else "MMD Tools add-on is not installed."
            return self._ok(message, data)

        if command_name == "ensure_mmd_tools":
            return self._ensure_mmd_tools(payload)

        if command_name == "detect_runtime":
            detection = self._detect_runtime(payload.get("blender_executable"))
            return self._ok("Detected Blender runtime." if detection["available"] else "No Blender runtime detected.", detection)

        if command_name == "version":
            detection, deploy_result = self._ensure_ready_detection(payload)
            if not detection["available"]:
                return self._fail("No Blender executable detected.", {"detected": detection, "deployment": deploy_result})
            version = self._probe_version(detection["path"], int(payload.get("timeout_seconds") or 8))
            version["deployment"] = deploy_result
            return self._ok(version.get("first_line") or "Blender version probe completed.", version)

        if command_name == "open_blender":
            return self._open_blender(payload)

        if command_name == "run_script":
            return self._run_script(payload)

        if command_name == "import_mmd_model":
            return self._import_mmd_model(payload)

        return self._fail(f"Unknown command: {command_name}", {})

    def _resolve_plugin_root(self) -> Path:
        env_root = os.environ.get("REVERIE_BLENDER_PLUGIN_ROOT", "").strip()
        if env_root:
            return Path(env_root).expanduser().resolve(strict=False)

        if getattr(sys, "frozen", False):
            executable_dir = Path(sys.executable).resolve(strict=False).parent
            if executable_dir.name.lower() == "dist":
                return executable_dir.parent
            if executable_dir.name.lower() == "plugins" and executable_dir.parent.name.lower() == ".reverie":
                return (executable_dir / "blender").resolve(strict=False)
            return executable_dir

        here = Path(__file__).resolve(strict=False).parent
        if here.parent.name.lower() == "plugins" and here.parent.parent.name.lower() == ".reverie":
            return here

        cwd = Path.cwd().resolve(strict=False)
        for candidate in (
            cwd / "dist" / ".reverie" / "plugins" / "blender",
            cwd / ".reverie" / "plugins" / "blender",
            here,
        ):
            if candidate.exists():
                return candidate.resolve(strict=False)
        return (cwd / "dist" / ".reverie" / "plugins" / "blender").resolve(strict=False)

    def _bundle_root(self) -> Path:
        bundle_root = getattr(sys, "_MEIPASS", "")
        if bundle_root:
            return Path(str(bundle_root)).resolve(strict=False)
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve(strict=False).parent
        return Path(__file__).resolve(strict=False).parent

    def _archive_candidates(self) -> list[Path]:
        candidates = [
            self._bundle_root() / ARCHIVE_NAME,
            self.plugin_root / ARCHIVE_NAME,
            self.plugin_root / "assets" / ARCHIVE_NAME,
        ]
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).resolve(strict=False).parent / ARCHIVE_NAME)
        else:
            here = Path(__file__).resolve(strict=False).parent
            candidates.extend(
                [
                    here / ARCHIVE_NAME,
                    here.parent / ARCHIVE_NAME,
                    here.parent.parent / "dist" / ".reverie" / "plugins" / "blender" / ARCHIVE_NAME,
                ]
            )

        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=False)
            except Exception:
                resolved = candidate.absolute()
            key = str(resolved).lower()
            if key not in seen:
                unique.append(resolved)
                seen.add(key)
        return unique

    def _find_archive(self) -> Path | None:
        for candidate in self._archive_candidates():
            if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".zip":
                return candidate
        return None

    def _archive_status(self) -> dict[str, Any]:
        archive = self._find_archive()
        candidates = [str(path) for path in self._archive_candidates()]
        if archive is None:
            return {"available": False, "name": ARCHIVE_NAME, "path": "", "source": "", "candidates": candidates}
        bundle_root = self._bundle_root()
        source = "embedded" if self._is_inside(archive, bundle_root) and getattr(sys, "frozen", False) else "plugin-local"
        return {"available": True, "name": archive.name, "path": str(archive), "source": source, "candidates": candidates}

    def _mmd_module_path(self) -> Path | None:
        candidates = [
            self.mmd_tools_root / MMD_TOOLS_MODULE / "__init__.py",
            self.addons_root / MMD_TOOLS_MODULE / "__init__.py",
            self.plugin_root / MMD_TOOLS_MODULE / "__init__.py",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.parent.resolve(strict=False)
        return None

    def _mmd_python_paths(self) -> list[str]:
        candidates: list[Path] = []
        module_path = self._mmd_module_path()
        if module_path is not None:
            candidates.append(module_path.parent)
        candidates.extend([self.mmd_tools_root, self.addons_root])

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=False)
            except Exception:
                resolved = candidate.absolute()
            key = str(resolved).lower()
            if key not in seen and resolved.exists():
                unique.append(str(resolved))
                seen.add(key)
        return unique

    def _git_executable(self) -> str:
        return str(shutil.which("git") or "")

    def _git_output(self, args: list[str], *, cwd: Path | None = None, timeout_seconds: int = 10) -> str:
        git = self._git_executable()
        if not git:
            return ""
        try:
            completed = subprocess.run(
                [git, *args],
                cwd=str(cwd or self.plugin_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1, timeout_seconds),
                check=False,
                env=self._blender_env(),
            )
        except Exception:
            return ""
        if completed.returncode != 0:
            return ""
        return (completed.stdout or "").strip()

    def _mmd_tools_status_data(self) -> dict[str, Any]:
        module_path = self._mmd_module_path()
        git_dir = self.mmd_tools_root / ".git"
        commit = self._git_output(["rev-parse", "--short", "HEAD"], cwd=self.mmd_tools_root) if git_dir.exists() else ""
        branch = self._git_output(["branch", "--show-current"], cwd=self.mmd_tools_root) if git_dir.exists() else ""
        return {
            "repo_url": MMD_TOOLS_REPO_URL,
            "addon_root": str(self.mmd_tools_root),
            "addons_root": str(self.addons_root),
            "module_name": MMD_TOOLS_MODULE,
            "module_path": str(module_path or ""),
            "installed": module_path is not None,
            "checkout_exists": self.mmd_tools_root.exists(),
            "git_available": bool(self._git_executable()),
            "git_commit": commit,
            "git_branch": branch,
            "python_paths": self._mmd_python_paths(),
            "supported_extensions": {
                "model": sorted(MMD_MODEL_EXTENSIONS),
                "motion": sorted(MMD_MOTION_EXTENSIONS),
                "pose": sorted(MMD_POSE_EXTENSIONS),
            },
            "storage_policy": "plugin-local",
        }

    def _blender_env(self, extra_python_paths: list[str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        for env_name, root in (
            ("BLENDER_USER_CONFIG", self.config_root),
            ("BLENDER_USER_SCRIPTS", self.scripts_root),
            ("BLENDER_USER_DATAFILES", self.datafiles_root),
        ):
            root.mkdir(parents=True, exist_ok=True)
            env[env_name] = str(root)

        python_paths: list[str] = []
        for raw_path in extra_python_paths or []:
            if not raw_path:
                continue
            candidate = Path(str(raw_path)).expanduser()
            try:
                resolved = candidate.resolve(strict=False)
            except Exception:
                resolved = candidate.absolute()
            if resolved.exists():
                python_paths.append(str(resolved))

        existing = env.get("PYTHONPATH", "")
        if python_paths:
            env["PYTHONPATH"] = os.pathsep.join([*python_paths, existing] if existing else python_paths)
        return env

    def _mmd_bootstrap_source(self, *, strict: bool, emit_marker: bool) -> str:
        paths_json = json.dumps(self._mmd_python_paths())
        marker_json = json.dumps(MMD_TOOLS_STATUS_MARKER)
        strict_python = repr(bool(strict))
        emit_marker_python = repr(bool(emit_marker))
        return f"""
import importlib
import json
import sys
import traceback

paths = {paths_json}
marker = {marker_json}
strict = {strict_python}
emit_marker = {emit_marker_python}
for path in reversed(paths):
    if path and path not in sys.path:
        sys.path.insert(0, path)

result = {{
    "success": False,
    "module": "{MMD_TOOLS_MODULE}",
    "paths": paths,
    "available": False,
    "enabled": False,
    "module_file": "",
    "error": "",
}}
try:
    import addon_utils
    module = importlib.import_module("{MMD_TOOLS_MODULE}")
    result["module_file"] = str(getattr(module, "__file__", "") or "")
    addon_utils.enable("{MMD_TOOLS_MODULE}", default_set=False, persistent=True)
    available, enabled = addon_utils.check("{MMD_TOOLS_MODULE}")
    result["available"] = bool(available)
    result["enabled"] = bool(enabled)
    result["success"] = bool(enabled)
except Exception as exc:
    result["error"] = str(exc)
    result["traceback"] = traceback.format_exc()[-4000:]

if emit_marker:
    print(marker + json.dumps(result, ensure_ascii=False, sort_keys=True))
if strict and not result["success"]:
    raise SystemExit(23)
""".strip()

    def _write_mmd_bootstrap_script(self, *, strict: bool = False, emit_marker: bool = False) -> Path:
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        script_path = self.tmp_root / ("reverie_mmd_tools_strict.py" if strict else "reverie_mmd_tools_bootstrap.py")
        script_path.write_text(self._mmd_bootstrap_source(strict=strict, emit_marker=emit_marker), encoding="utf-8")
        return script_path

    def _run_blender_python(self, blender_path: Any, script_text: str, timeout_seconds: int, *, extra_python_paths: list[str] | None = None) -> dict[str, Any]:
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="reverie_blender_", dir=self.tmp_root, encoding="utf-8", delete=False) as handle:
                handle.write(script_text)
                temp_path = handle.name
            command = [str(blender_path), "--background", "--python", temp_path]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1, timeout_seconds),
                check=False,
                env=self._blender_env(extra_python_paths),
            )
            return {
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-8000:],
                "script_path": temp_path,
            }
        except Exception as exc:
            return {"command": [str(blender_path), "--background", "--python", temp_path], "exit_code": -1, "stdout": "", "stderr": str(exc), "script_path": temp_path}
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _extract_marker_json(self, text: str, marker: str) -> dict[str, Any]:
        for line in text.splitlines():
            if marker not in line:
                continue
            raw = line.split(marker, 1)[1].strip()
            try:
                value = json.loads(raw)
            except Exception:
                return {}
            return value if isinstance(value, dict) else {}
        return {}

    def _enable_mmd_tools(self, blender_path: Any, timeout_seconds: int = 60) -> dict[str, Any]:
        script_text = self._mmd_bootstrap_source(strict=True, emit_marker=True)
        completed = self._run_blender_python(
            blender_path,
            script_text,
            timeout_seconds,
            extra_python_paths=self._mmd_python_paths(),
        )
        probe = self._extract_marker_json(f"{completed.get('stdout', '')}\n{completed.get('stderr', '')}", MMD_TOOLS_STATUS_MARKER)
        return {
            "success": bool(completed.get("exit_code") == 0 and probe.get("success")),
            "probe": probe,
            "command": completed.get("command", []),
            "exit_code": completed.get("exit_code"),
            "stdout": str(completed.get("stdout", ""))[-4000:],
            "stderr": str(completed.get("stderr", ""))[-4000:],
        }

    def _ensure_mmd_tools(self, payload: dict[str, Any]) -> dict[str, Any]:
        force = bool(payload.get("force", False))
        update = payload.get("update", True) is not False
        enable = bool(payload.get("enable", False))
        dry_run = bool(payload.get("dry_run", False))
        timeout = int(payload.get("timeout_seconds") or 900)
        target = self.mmd_tools_root.resolve(strict=False)

        data = self._mmd_tools_status_data()
        data.update(
            {
                "target": str(target),
                "dry_run": dry_run,
                "planned_commands": [],
            }
        )

        if not self._is_inside(target, self.plugin_root):
            return self._fail("Refusing to place MMD Tools outside the Blender plugin root.", data)

        git = self._git_executable()
        if force and self.mmd_tools_root.exists():
            data["planned_commands"].append(f"remove {self.mmd_tools_root}")
        if not self._mmd_module_path() or force:
            data["planned_commands"].append(f"git clone --depth 1 {MMD_TOOLS_REPO_URL} {self.mmd_tools_root}")
        elif update and (self.mmd_tools_root / ".git").exists():
            data["planned_commands"].append(f"git -C {self.mmd_tools_root} pull --ff-only")
        if enable:
            data["planned_commands"].append("blender --background --python <enable mmd_tools probe>")

        if dry_run:
            return self._ok("MMD Tools deployment dry-run completed.", data)

        self.addons_root.mkdir(parents=True, exist_ok=True)
        if force and self.mmd_tools_root.exists():
            self._safe_remove_tree(self.plugin_root, self.mmd_tools_root)

        module_path = self._mmd_module_path()
        if module_path is None:
            if self.mmd_tools_root.exists() and any(self.mmd_tools_root.iterdir()):
                data = data | self._mmd_tools_status_data()
                return self._fail("MMD Tools target exists but is not a valid checkout; rerun with force=true.", data)
            if not git:
                data = data | self._mmd_tools_status_data()
                return self._fail("git was not found on PATH, so MMD Tools cannot be cloned automatically.", data)
            try:
                completed = subprocess.run(
                    [git, "clone", "--depth", "1", MMD_TOOLS_REPO_URL, str(self.mmd_tools_root)],
                    cwd=str(self.plugin_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=max(1, timeout),
                    check=False,
                )
            except Exception as exc:
                data = data | self._mmd_tools_status_data()
                return self._fail(str(exc), data)
            data["clone"] = {
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
            if completed.returncode != 0:
                data = data | self._mmd_tools_status_data()
                return self._fail("MMD Tools clone failed.", data)
        elif update and (self.mmd_tools_root / ".git").exists() and git:
            try:
                completed = subprocess.run(
                    [git, "-C", str(self.mmd_tools_root), "pull", "--ff-only"],
                    cwd=str(self.plugin_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=max(1, timeout),
                    check=False,
                )
                data["update"] = {
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                }
                if completed.returncode != 0:
                    data = data | self._mmd_tools_status_data()
                    return self._fail("MMD Tools update failed.", data)
            except Exception as exc:
                data = data | self._mmd_tools_status_data()
                return self._fail(str(exc), data)

        data = data | self._mmd_tools_status_data()
        if not data.get("installed"):
            return self._fail("MMD Tools checkout completed but the mmd_tools module was not found.", data)

        if enable:
            detection, deploy_result = self._ensure_ready_detection(
                {
                    "blender_executable": payload.get("blender_executable"),
                    "auto_prepare": payload.get("auto_prepare", True),
                }
            )
            data["detected"] = detection
            data["deployment"] = deploy_result
            if not detection["available"]:
                return self._fail("MMD Tools is installed, but no Blender executable was detected for enablement.", data)
            enable_result = self._enable_mmd_tools(detection["path"], min(timeout, int(payload.get("enable_timeout_seconds") or 120)))
            data["enable"] = enable_result
            if not enable_result["success"]:
                return self._fail("MMD Tools is installed, but Blender could not enable the add-on.", data)

        return self._ok("MMD Tools add-on is ready.", data)

    def _ensure_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        force = bool(payload.get("force", False))
        with_mmd_tools = payload.get("with_mmd_tools", True) is not False
        current = self._detect_runtime(payload.get("blender_executable"))
        if current["available"] and not force:
            data = {
                "deployed": False,
                "reason": "runtime already exists",
                "detected": current,
                "archive": self._archive_status(),
                "runtime_root": str(self.runtime_root),
            }
            if with_mmd_tools:
                data["mmd_tools"] = self._ensure_mmd_tools(
                    {
                        "force": False,
                        "update": payload.get("update_mmd_tools", False),
                        "enable": bool(payload.get("enable_mmd_tools", False)),
                        "blender_executable": current["path"],
                    }
                )
            return self._ok(
                "Portable Blender runtime is already available.",
                data,
            )

        archive = self._find_archive()
        if archive is None:
            return self._fail(
                "Embedded Blender archive was not found in this plugin executable.",
                {"detected": current, "archive": self._archive_status(), "runtime_root": str(self.runtime_root)},
            )

        if force and self.runtime_root.exists():
            self._safe_remove_tree(self.plugin_root, self.runtime_root)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        before_entries = set(str(item.relative_to(self.runtime_root)) for item in self.runtime_root.rglob("*")) if self.runtime_root.exists() else set()
        try:
            extracted_count = self._safe_extract_zip(archive, self.runtime_root)
        except Exception as exc:
            return self._fail(str(exc), {"archive": str(archive), "runtime_root": str(self.runtime_root)})

        after_entries = set(str(item.relative_to(self.runtime_root)) for item in self.runtime_root.rglob("*")) if self.runtime_root.exists() else set()
        detected = self._detect_runtime(payload.get("blender_executable"))
        data = {
            "deployed": True,
            "archive": self._archive_status(),
            "runtime_root": str(self.runtime_root),
            "extracted_count": extracted_count,
            "created_entries": sorted(after_entries - before_entries)[:40],
            "detected": detected,
        }
        if with_mmd_tools:
            data["mmd_tools"] = self._ensure_mmd_tools(
                {
                    "force": False,
                    "update": payload.get("update_mmd_tools", False),
                    "enable": bool(payload.get("enable_mmd_tools", False)),
                    "blender_executable": detected.get("path", ""),
                }
            )
        if detected["available"]:
            return self._ok("Embedded portable Blender runtime deployed.", data)
        return self._fail("Embedded archive extracted, but no Blender executable was detected.", data)

    def _ensure_ready_detection(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        detection = self._detect_runtime(payload.get("blender_executable"))
        if detection["available"]:
            return detection, None
        auto_prepare = payload.get("auto_prepare", True)
        if auto_prepare is False:
            return detection, None
        deploy_result = self._ensure_runtime({"force": False, "with_mmd_tools": False})
        detection = self._detect_runtime(payload.get("blender_executable"))
        return detection, deploy_result

    def _candidate_executables(self, explicit: Any = "") -> list[Path]:
        candidates: list[Path] = []
        raw = str(explicit or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            candidates.append(candidate / "blender.exe" if candidate.is_dir() else candidate)

        for env_name in ("REVERIE_BLENDER_PATH", "BLENDER_PATH"):
            env_value = os.environ.get(env_name, "").strip()
            if env_value:
                candidate = Path(env_value).expanduser()
                candidates.append(candidate / "blender.exe" if candidate.is_dir() else candidate)

        candidates.extend(
            [
                self.runtime_root / "blender.exe",
                self.runtime_root / "blender" / "blender.exe",
                self.plugin_root / "blender.exe",
                self.plugin_root / "bin" / "blender.exe",
            ]
        )
        if self.runtime_root.exists():
            candidates.extend(sorted(self.runtime_root.glob("**/blender.exe"), key=lambda path: str(path).lower()))

        which_blender = shutil.which("blender")
        if which_blender:
            candidates.append(Path(which_blender))

        if os.name == "nt":
            for root_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
                root = os.environ.get(root_name, "").strip()
                if not root:
                    continue
                base = Path(root) / "Blender Foundation"
                if base.exists():
                    candidates.extend(sorted(base.glob("Blender */blender.exe"), reverse=True))
                candidates.append(base / "Blender" / "blender.exe")
        else:
            candidates.extend(
                [
                    Path("/Applications/Blender.app/Contents/MacOS/Blender"),
                    Path("/usr/bin/blender"),
                    Path("/usr/local/bin/blender"),
                    Path("/opt/blender/blender"),
                ]
            )

        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=False)
            except Exception:
                resolved = candidate.absolute()
            key = str(resolved).lower()
            if key not in seen:
                unique.append(resolved)
                seen.add(key)
        return unique

    def _detect_runtime(self, explicit: Any = "") -> dict[str, Any]:
        candidates = self._candidate_executables(explicit)
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return {
                    "available": True,
                    "path": str(candidate),
                    "source": "portable" if self._is_inside(candidate, self.plugin_root) else "external",
                    "candidates": [str(path) for path in candidates],
                }
        return {
            "available": False,
            "path": "",
            "source": "",
            "candidates": [str(path) for path in candidates],
        }

    def _probe_version(self, blender_path: Any, timeout_seconds: int) -> dict[str, Any]:
        if not blender_path:
            return {"success": False, "error": "No Blender path provided."}
        try:
            completed = subprocess.run(
                [str(blender_path), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1, timeout_seconds),
                check=False,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc), "path": str(blender_path)}
        lines = [line.strip() for line in (completed.stdout or completed.stderr or "").splitlines() if line.strip()]
        return {
            "success": completed.returncode == 0,
            "path": str(blender_path),
            "exit_code": completed.returncode,
            "first_line": lines[0] if lines else "",
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }

    def _open_blender(self, payload: dict[str, Any]) -> dict[str, Any]:
        detection, deploy_result = self._ensure_ready_detection(payload)
        if not detection["available"]:
            return self._fail("No Blender executable detected.", {"detected": detection, "deployment": deploy_result})

        command = [detection["path"]]
        mmd_result: dict[str, Any] | None = None
        if payload.get("with_mmd_tools", True) is not False:
            mmd_result = self._ensure_mmd_tools(
                {
                    "force": False,
                    "update": payload.get("update_mmd_tools", False),
                    "enable": False,
                    "auto_prepare": False,
                }
            )
            if mmd_result.get("success"):
                bootstrap = self._write_mmd_bootstrap_script(strict=False, emit_marker=False)
                command.extend(["--python", str(bootstrap)])
        blend_path = self._resolve_existing_path(payload.get("blend_path"))
        if blend_path is not None:
            command.append(str(blend_path))
        try:
            process = subprocess.Popen(
                command,
                cwd=str(Path(detection["path"]).parent),
                shell=False,
                env=self._blender_env(self._mmd_python_paths()),
            )
        except Exception as exc:
            return self._fail(str(exc), {"command": command})
        return self._ok(
            "Blender launched.",
            {"command": command, "pid": int(process.pid), "detected": detection, "deployment": deploy_result, "mmd_tools": mmd_result},
        )

    def _run_script(self, payload: dict[str, Any]) -> dict[str, Any]:
        detection, deploy_result = self._ensure_ready_detection(payload)
        if not detection["available"]:
            return self._fail("No Blender executable detected.", {"detected": detection, "deployment": deploy_result})

        script_path = self._resolve_existing_path(payload.get("script_path"))
        if script_path is None:
            return self._fail("script_path does not exist.", {"script_path": str(payload.get("script_path") or "")})

        blend_path = self._resolve_existing_path(payload.get("blend_path"))
        command = [detection["path"], "--background"]
        if blend_path is not None:
            command.append(str(blend_path))
        mmd_result: dict[str, Any] | None = None
        if bool(payload.get("auto_mmd_tools", False)):
            mmd_result = self._ensure_mmd_tools(
                {
                    "force": False,
                    "update": payload.get("update_mmd_tools", False),
                    "enable": False,
                    "auto_prepare": False,
                }
            )
            if not mmd_result.get("success"):
                return self._fail("MMD Tools could not be prepared before running the Blender script.", {"mmd_tools": mmd_result, "detected": detection, "deployment": deploy_result})
            bootstrap = self._write_mmd_bootstrap_script(strict=True, emit_marker=False)
            command.extend(["--python", str(bootstrap)])
        command.extend(["--python", str(script_path)])

        timeout = int(payload.get("timeout_seconds") or 240)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1, timeout),
                check=False,
                env=self._blender_env(self._mmd_python_paths()),
            )
        except Exception as exc:
            return self._fail(str(exc), {"command": command})
        data = {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-6000:],
            "stderr": completed.stderr[-6000:],
            "detected": detection,
            "deployment": deploy_result,
            "mmd_tools": mmd_result,
        }
        if completed.returncode == 0:
            return self._ok("Blender script completed.", data)
        return self._fail("Blender script failed.", data)

    def _import_mmd_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_path = self._resolve_existing_path(payload.get("model_path"))
        if model_path is None:
            return self._fail("model_path does not exist.", {"model_path": str(payload.get("model_path") or "")})
        if model_path.suffix.lower() not in MMD_MODEL_EXTENSIONS:
            return self._fail("model_path must be a .pmx or .pmd file.", {"model_path": str(model_path)})

        motion_path = self._resolve_existing_path(payload.get("motion_path"))
        if payload.get("motion_path") and motion_path is None:
            return self._fail("motion_path does not exist.", {"motion_path": str(payload.get("motion_path") or "")})
        if motion_path is not None and motion_path.suffix.lower() not in MMD_MOTION_EXTENSIONS:
            return self._fail("motion_path must be a .vmd file.", {"motion_path": str(motion_path)})

        pose_path = self._resolve_existing_path(payload.get("pose_path"))
        if payload.get("pose_path") and pose_path is None:
            return self._fail("pose_path does not exist.", {"pose_path": str(payload.get("pose_path") or "")})
        if pose_path is not None and pose_path.suffix.lower() not in MMD_POSE_EXTENSIONS:
            return self._fail("pose_path must be a .vpd file.", {"pose_path": str(pose_path)})

        save_blend = payload.get("save_blend", True) is not False
        output_blend_path = self._resolve_output_path(payload.get("output_blend_path"))
        if save_blend and output_blend_path is None:
            output_blend_path = (self.plugin_root / "imports" / f"{model_path.stem}.blend").resolve(strict=False)
        if output_blend_path is not None and output_blend_path.suffix.lower() != ".blend":
            return self._fail("output_blend_path must end with .blend.", {"output_blend_path": str(output_blend_path)})

        export_path = self._resolve_output_path(payload.get("export_path"))
        export_format = str(payload.get("export_format") or "").strip().lower().lstrip(".")
        if export_path is None and export_format in {"glb", "gltf"}:
            export_path = (self.plugin_root / "imports" / f"{model_path.stem}.{export_format}").resolve(strict=False)
        if export_path is not None and export_path.suffix.lower() not in {".glb", ".gltf"}:
            return self._fail("export_path must end with .glb or .gltf.", {"export_path": str(export_path)})

        detection, deploy_result = self._ensure_ready_detection(payload)
        if not detection["available"]:
            return self._fail("No Blender executable detected.", {"detected": detection, "deployment": deploy_result})

        mmd_result = self._ensure_mmd_tools(
            {
                "force": bool(payload.get("force_mmd_tools", False)),
                "update": payload.get("update_mmd_tools", False),
                "enable": True,
                "blender_executable": detection["path"],
                "auto_prepare": False,
                "timeout_seconds": int(payload.get("timeout_seconds") or 900),
            }
        )
        if not mmd_result.get("success"):
            return self._fail("MMD Tools could not be prepared for import.", {"mmd_tools": mmd_result, "detected": detection, "deployment": deploy_result})

        for path in (output_blend_path, export_path):
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)

        import_types = payload.get("types") or ["MESH", "ARMATURE", "PHYSICS", "DISPLAY", "MORPHS"]
        if not isinstance(import_types, list):
            import_types = ["MESH", "ARMATURE", "PHYSICS", "DISPLAY", "MORPHS"]
        scale = float(payload.get("scale") or 0.08)
        script_payload = {
            "model_path": str(model_path),
            "motion_path": str(motion_path or ""),
            "pose_path": str(pose_path or ""),
            "output_blend_path": str(output_blend_path or ""),
            "export_path": str(export_path or ""),
            "export_format": "GLB" if (export_path and export_path.suffix.lower() == ".glb") else "GLTF_SEPARATE",
            "scale": scale,
            "types": [str(item).upper() for item in import_types],
            "clear_scene": payload.get("clear_scene", True) is not False,
            "clean_model": payload.get("clean_model", True) is not False,
            "remove_doubles": bool(payload.get("remove_doubles", False)),
            "create_new_action": bool(payload.get("create_new_action", True)),
            "marker": MMD_IMPORT_STATUS_MARKER,
        }
        script_text = self._mmd_import_script(script_payload)
        timeout = int(payload.get("timeout_seconds") or 900)
        completed = self._run_blender_python(
            detection["path"],
            script_text,
            timeout,
            extra_python_paths=self._mmd_python_paths(),
        )
        import_result = self._extract_marker_json(f"{completed.get('stdout', '')}\n{completed.get('stderr', '')}", MMD_IMPORT_STATUS_MARKER)
        data = {
            "detected": detection,
            "deployment": deploy_result,
            "mmd_tools": mmd_result,
            "import": import_result,
            "command": completed.get("command", []),
            "exit_code": completed.get("exit_code"),
            "stdout": str(completed.get("stdout", ""))[-6000:],
            "stderr": str(completed.get("stderr", ""))[-6000:],
            "outputs": {
                "blend": str(output_blend_path or ""),
                "export": str(export_path or ""),
            },
        }
        if completed.get("exit_code") == 0 and import_result.get("success"):
            return self._ok("MMD model imported through Blender.", data)
        return self._fail("MMD model import failed.", data)

    def _mmd_import_script(self, payload: dict[str, Any]) -> str:
        payload_json = json.dumps(payload, ensure_ascii=False)
        payload_source = json.dumps(payload_json, ensure_ascii=False)
        paths_json = json.dumps(self._mmd_python_paths())
        return f"""
import importlib
import json
import sys
import traceback

paths = {paths_json}
payload = json.loads({payload_source})
for path in reversed(paths):
    if path and path not in sys.path:
        sys.path.insert(0, path)

result = {{
    "success": False,
    "model_path": payload.get("model_path", ""),
    "motion_path": payload.get("motion_path", ""),
    "pose_path": payload.get("pose_path", ""),
    "output_blend_path": payload.get("output_blend_path", ""),
    "export_path": payload.get("export_path", ""),
    "imported_objects": [],
    "mesh_count": 0,
    "armature_count": 0,
    "material_count": 0,
    "action_count": 0,
    "shape_key_count": 0,
    "operator_results": {{}},
    "error": "",
}}
try:
    import bpy
    import addon_utils

    importlib.import_module("{MMD_TOOLS_MODULE}")
    addon_utils.enable("{MMD_TOOLS_MODULE}", default_set=False, persistent=True)
    if payload.get("clear_scene", True):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()

    before = set(bpy.data.objects.keys())
    op_result = bpy.ops.mmd_tools.import_model(
        filepath=payload["model_path"],
        types=set(payload.get("types") or ["MESH", "ARMATURE", "PHYSICS", "DISPLAY", "MORPHS"]),
        scale=float(payload.get("scale") or 0.08),
        clean_model=bool(payload.get("clean_model", True)),
        remove_doubles=bool(payload.get("remove_doubles", False)),
    )
    result["operator_results"]["import_model"] = sorted(str(item) for item in op_result)
    imported = [obj for obj in bpy.context.scene.objects if obj.name not in before]
    result["imported_objects"] = [obj.name for obj in imported]
    if not imported:
        raise RuntimeError("MMD Tools import finished without creating scene objects.")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]

    if payload.get("motion_path"):
        vmd_result = bpy.ops.mmd_tools.import_vmd(
            filepath=payload["motion_path"],
            scale=float(payload.get("scale") or 0.08),
            create_new_action=bool(payload.get("create_new_action", True)),
        )
        result["operator_results"]["import_vmd"] = sorted(str(item) for item in vmd_result)

    if payload.get("pose_path"):
        vpd_result = bpy.ops.mmd_tools.import_vpd(
            filepath=payload["pose_path"],
            scale=float(payload.get("scale") or 0.08),
        )
        result["operator_results"]["import_vpd"] = sorted(str(item) for item in vpd_result)

    if payload.get("output_blend_path"):
        bpy.ops.wm.save_as_mainfile(filepath=payload["output_blend_path"])

    if payload.get("export_path"):
        bpy.ops.export_scene.gltf(
            filepath=payload["export_path"],
            export_format=payload.get("export_format") or "GLB",
        )

    result["mesh_count"] = sum(1 for obj in bpy.context.scene.objects if obj.type == "MESH")
    result["armature_count"] = sum(1 for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    result["material_count"] = len(bpy.data.materials)
    result["action_count"] = len(bpy.data.actions)
    result["shape_key_count"] = sum(
        len(obj.data.shape_keys.key_blocks)
        for obj in bpy.context.scene.objects
        if getattr(getattr(obj, "data", None), "shape_keys", None)
    )
    result["success"] = result["mesh_count"] > 0 or result["armature_count"] > 0
except Exception as exc:
    result["error"] = str(exc)
    result["traceback"] = traceback.format_exc()[-6000:]

print(payload.get("marker", "{MMD_IMPORT_STATUS_MARKER}") + json.dumps(result, ensure_ascii=False, sort_keys=True))
if not result["success"]:
    raise SystemExit(24)
""".strip()

    def _resolve_existing_path(self, raw_path: Any) -> Path | None:
        text = str(raw_path or "").strip()
        if not text:
            return None
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        try:
            candidate = candidate.resolve(strict=False)
        except Exception:
            candidate = candidate.absolute()
        return candidate if candidate.exists() else None

    def _resolve_output_path(self, raw_path: Any) -> Path | None:
        text = str(raw_path or "").strip()
        if not text:
            return None
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        try:
            return candidate.resolve(strict=False)
        except Exception:
            return candidate.absolute()

    def _is_inside(self, path: Path, root: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=False))
            return True
        except ValueError:
            return False

    def _safe_remove_tree(self, root: Path, target: Path) -> None:
        resolved_root = root.resolve(strict=False)
        resolved_target = target.resolve(strict=False)
        if resolved_target == resolved_root:
            raise ValueError("Refusing to remove the plugin root.")
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"Refusing to remove path outside plugin root: {resolved_target}") from exc
        if resolved_target.exists():
            shutil.rmtree(resolved_target)

    def _safe_extract_zip(self, archive_path: Path, target_dir: Path) -> int:
        target = target_dir.resolve(strict=False)
        target.mkdir(parents=True, exist_ok=True)
        count = 0
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                name = str(member.filename or "").replace("\\", "/")
                if not name or name.startswith("/") or ":" in name.split("/", 1)[0]:
                    raise ValueError(f"Unsafe archive member path: {member.filename}")
                destination = (target / name).resolve(strict=False)
                try:
                    destination.relative_to(target)
                except ValueError as exc:
                    raise ValueError(f"Archive member escapes runtime target: {member.filename}") from exc
                archive.extract(member, target)
                count += 1
        return count

    def _ok(self, output: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "output": output, "error": "", "data": data}

    def _fail(self, error: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"success": False, "output": "", "error": error, "data": data}


def main(argv: list[str]) -> int:
    return BlenderRuntimePlugin().run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
