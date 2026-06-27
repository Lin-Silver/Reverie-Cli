"""Blender SDK/runtime plugin for Reverie CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile


PLUGIN_VERSION = "0.4.0"
ARCHIVE_NAME = "blender-5.1.1-windows-x64.zip"
MMD_TOOLS_REPO_URL = "https://github.com/MMD-Blender/blender_mmd_tools.git"
MMD_TOOLS_MODULE = "mmd_tools"
MMD_TOOLS_STATUS_MARKER = "REVERIE_MMD_TOOLS_STATUS="
MMD_IMPORT_STATUS_MARKER = "REVERIE_MMD_IMPORT_RESULT="
BLENDER_MCP_REPO_URL = "https://github.com/ahujasid/blender-mcp.git"
BLENDER_MCP_SERVER_NAME = "blender"
BLENDER_MCP_DEFAULT_HOST = "127.0.0.1"
BLENDER_MCP_DEFAULT_PORT = 9876
BLENDER_MCP_START_MARKER = "REVERIE_BLENDER_MCP_START="
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
        self.mcp_root = self.plugin_root / "mcp"
        self.blender_mcp_root = self.mcp_root / "blender-mcp"
        self.blender_mcp_pid_path = self.blender_mcp_root / ".reverie-blender.pid.json"
        self.blender_mcp_log_path = self.blender_mcp_root / "blender-socket.log"

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
                "for PMD/PMX model, VMD motion, VPD pose import, and plugin-local "
                "Blender MCP deployment."
            ),
            "tool_call_hint": (
                "Use rc_blender_ensure_runtime to deploy the embedded portable Blender "
                "environment, then rc_blender_run_script for background asset authoring. "
                "Use rc_blender_ensure_mmd_tools or rc_blender_import_mmd_model when "
                "working with MMD PMD/PMX/VMD/VPD assets. "
                "Use rc_blender_mcp_install, rc_blender_mcp_start, and "
                "rc_blender_mcp_info to expose Blender MCP from this plugin only after "
                "installation and health checks succeed. "
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
                "It can deploy ahujasid/blender-mcp into the plugin's own mcp folder, "
                "copy the Blender MCP addon into the plugin-managed Blender user scripts, "
                "start/stop a background Blender socket server, and report MCP config "
                "only when discovery or static health checks are available. "
                "For AI modeling workflows, combine blender_modeling_workbench for script/"
                "asset planning with rc_blender_ensure_runtime and rc_blender_run_script "
                "for execution."
            ),
            "skills": [
                {
                    "name": "blender-production-runtime",
                    "description": "Execute auditable Blender asset workflows through the portable plugin runtime.",
                    "include_modes": [],
                    "body": (
                        "Use blender_modeling_workbench for plans and generated bpy scripts, then use this plugin for "
                        "runtime deployment and execution. Check runtime_status before direct execution. For PMX/PMD/VMD/VPD "
                        "assets prefer import_mmd_model. Verify exported .blend/.glb/.gltf artifacts before claiming success. "
                        "Only advertise Blender MCP after mcp_info reports a successful tools/list probe."
                    ),
                }
            ],
            "commands": [
                {
                    "name": "mcp_install",
                    "description": "Deploy ahujasid/blender-mcp under the plugin-local mcp folder and install its Blender addon into the plugin-managed Blender user scripts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "force": {"type": "boolean", "description": "Replace an existing plugin-local Blender MCP checkout."},
                            "update": {"type": "boolean", "description": "Update or refresh from a local reference/source checkout when available. Defaults to true."},
                            "source_path": {"type": "string", "description": "Optional local blender-mcp source checkout to copy instead of cloning."},
                            "enable_addon": {"type": "boolean", "description": "Run Blender in background to enable the addon after installing it."},
                            "blender_executable": {"type": "string", "description": "Optional absolute Blender executable path used for addon enablement."},
                            "dry_run": {"type": "boolean", "description": "Report planned install paths without copying, cloning, or running Blender."},
                            "timeout_seconds": {"type": "integer", "description": "Git/copy/Blender probe timeout."}
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Call this before using Blender MCP. It stores MCP files under .reverie/plugins/blender/mcp/blender-mcp/."
                },
                {
                    "name": "mcp_start",
                    "description": "Start the plugin-managed Blender MCP addon socket server in a background Blender process.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "host": {"type": "string", "description": "Blender socket host. Defaults to 127.0.0.1."},
                            "port": {"type": "integer", "description": "Blender socket port. Defaults to 9876."},
                            "auto_install": {"type": "boolean", "description": "Install Blender MCP first when missing. Defaults to true."},
                            "blender_executable": {"type": "string", "description": "Optional absolute Blender executable path."},
                            "timeout_seconds": {"type": "integer", "description": "Startup/socket health timeout."}
                        },
                        "required": []
                    },
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Starts only the Blender-side socket server; use mcp_info to get the MCP stdio command for a client."
                },
                {
                    "name": "mcp_stop",
                    "description": "Stop the plugin-managed Blender MCP background Blender process when Reverie no longer needs it.",
                    "parameters": {"type": "object", "properties": {"force": {"type": "boolean", "description": "Force-kill the process tree on Windows."}}, "required": []},
                    "expose_as_tool": True,
                    "include_modes": []
                },
                {
                    "name": "mcp_status",
                    "description": "Inspect Blender MCP install status, addon path, background process, socket reachability, and MCP command readiness.",
                    "parameters": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer"}, "probe_tools": {"type": "boolean", "description": "Attempt a short MCP initialize/tools/list probe."}}, "required": []},
                    "expose_as_tool": True,
                    "include_modes": []
                },
                {
                    "name": "mcp_info",
                    "description": "Return Blender MCP server name, command, args, cwd, env, static/probed tool list, and health status for MCP registration.",
                    "parameters": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer"}, "probe_tools": {"type": "boolean", "description": "Only marks tools_list_ok true if a real tools/list probe succeeds."}, "timeout_seconds": {"type": "integer"}}, "required": []},
                    "expose_as_tool": True,
                    "include_modes": [],
                    "guidance": "Only add this MCP information to prompts after tools_list_ok is true."
                },
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
        if command_name == "mcp_install":
            return self._mcp_install(payload)

        if command_name == "mcp_start":
            return self._mcp_start(payload)

        if command_name == "mcp_stop":
            return self._mcp_stop(payload)

        if command_name == "mcp_status":
            return self._mcp_status(payload)

        if command_name == "mcp_info":
            return self._mcp_info(payload)

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

    def _blender_mcp_source_candidates(self, payload: dict[str, Any] | None = None) -> list[Path]:
        payload = payload or {}
        candidates: list[Path] = []
        raw_source = str(payload.get("source_path") or "").strip()
        if raw_source:
            candidates.append(Path(raw_source).expanduser())
        try:
            repo_root = Path(__file__).resolve(strict=False).parents[2]
            candidates.append(repo_root / "references" / "blender-mcp")
        except Exception:
            pass
        candidates.extend(
            [
                self.plugin_root / "references" / "blender-mcp",
                self.plugin_root / "source" / "blender-mcp",
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

    def _valid_blender_mcp_source(self, path: Path) -> bool:
        return (
            path.exists()
            and path.is_dir()
            and (path / "pyproject.toml").exists()
            and (path / "addon.py").exists()
            and (path / "src" / "blender_mcp" / "server.py").exists()
        )

    def _blender_mcp_addon_target(self) -> Path:
        return self.scripts_root / "addons" / "blender_mcp.py"

    def _blender_mcp_tools_static(self) -> list[str]:
        server_path = self.blender_mcp_root / "src" / "blender_mcp" / "server.py"
        if not server_path.exists():
            return []
        try:
            text = server_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        tools: list[str] = []
        pattern = re.compile(r"@mcp\.tool\(\)\s*(?:\n\s*@[\w.()\"', ]+\s*)*\n\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.M)
        for match in pattern.finditer(text):
            name = match.group(1)
            if name not in tools:
                tools.append(name)
        return tools

    def _copy_blender_mcp_source(self, source: Path, target: Path, *, force: bool) -> dict[str, Any]:
        if force and target.exists():
            self._safe_remove_tree(self.plugin_root, target)
        target.parent.mkdir(parents=True, exist_ok=True)
        ignore = shutil.ignore_patterns(".git", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache")
        shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore)
        return {"source": str(source), "target": str(target), "copied": True}

    def _mcp_install(self, payload: dict[str, Any]) -> dict[str, Any]:
        force = bool(payload.get("force", False))
        update = payload.get("update", True) is not False
        dry_run = bool(payload.get("dry_run", False))
        timeout = int(payload.get("timeout_seconds") or 900)
        target = self.blender_mcp_root.resolve(strict=False)
        addon_target = self._blender_mcp_addon_target().resolve(strict=False)
        data = self._mcp_status_data(payload)
        data.update(
            {
                "repo_url": BLENDER_MCP_REPO_URL,
                "target": str(target),
                "addon_target": str(addon_target),
                "dry_run": dry_run,
                "planned_commands": [],
            }
        )

        if not self._is_inside(target, self.plugin_root):
            return self._fail("Refusing to install Blender MCP outside the Blender plugin root.", data)
        if not self._is_inside(addon_target, self.plugin_root):
            return self._fail("Refusing to install Blender MCP addon outside the Blender plugin root.", data)

        source = next((candidate for candidate in self._blender_mcp_source_candidates(payload) if self._valid_blender_mcp_source(candidate)), None)
        if source is not None:
            data["planned_commands"].append(f"copy {source} -> {target}")
        elif not self._valid_blender_mcp_source(target):
            data["planned_commands"].append(f"git clone --depth 1 {BLENDER_MCP_REPO_URL} {target}")
        if update and self._valid_blender_mcp_source(target) and (target / ".git").exists():
            data["planned_commands"].append(f"git -C {target} pull --ff-only")
        data["planned_commands"].append(f"copy addon.py -> {addon_target}")
        if payload.get("enable_addon", False):
            data["planned_commands"].append("blender --background --python <enable blender_mcp addon>")

        if dry_run:
            return self._ok("Blender MCP install dry-run completed.", data)

        if source is not None and (force or update or not self._valid_blender_mcp_source(target)):
            try:
                data["copy"] = self._copy_blender_mcp_source(source, target, force=force)
            except Exception as exc:
                return self._fail(f"Blender MCP source copy failed: {exc}", data | self._mcp_status_data(payload))
        elif not self._valid_blender_mcp_source(target):
            git = self._git_executable()
            if not git:
                return self._fail("git was not found on PATH, so Blender MCP cannot be cloned automatically.", data | self._mcp_status_data(payload))
            try:
                if force and target.exists():
                    self._safe_remove_tree(self.plugin_root, target)
                completed = subprocess.run(
                    [git, "clone", "--depth", "1", BLENDER_MCP_REPO_URL, str(target)],
                    cwd=str(self.plugin_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=max(1, timeout),
                    check=False,
                )
            except Exception as exc:
                return self._fail(str(exc), data | self._mcp_status_data(payload))
            data["clone"] = {"exit_code": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}
            if completed.returncode != 0:
                return self._fail("Blender MCP clone failed.", data | self._mcp_status_data(payload))
        elif update and (target / ".git").exists() and self._git_executable():
            completed = subprocess.run(
                [self._git_executable(), "-C", str(target), "pull", "--ff-only"],
                cwd=str(self.plugin_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1, timeout),
                check=False,
            )
            data["update"] = {"exit_code": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}
            if completed.returncode != 0:
                return self._fail("Blender MCP update failed.", data | self._mcp_status_data(payload))

        if not self._valid_blender_mcp_source(target):
            return self._fail("Blender MCP checkout is incomplete after installation.", data | self._mcp_status_data(payload))

        addon_source = target / "addon.py"
        addon_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(addon_source, addon_target)
        data["addon_install"] = {"source": str(addon_source), "target": str(addon_target), "installed": addon_target.exists()}

        if payload.get("enable_addon", False):
            detection, deploy_result = self._ensure_ready_detection(payload)
            data["detected"] = detection
            data["deployment"] = deploy_result
            if not detection["available"]:
                return self._fail("Blender MCP installed, but no Blender executable was detected for addon enablement.", data | self._mcp_status_data(payload))
            data["enable_addon"] = self._enable_blender_mcp_addon(detection["path"], min(timeout, 120))
            if not data["enable_addon"].get("success"):
                return self._fail("Blender MCP installed, but Blender could not enable the addon.", data | self._mcp_status_data(payload))

        return self._ok("Blender MCP is installed in the Blender plugin.", data | self._mcp_status_data(payload))

    def _enable_blender_mcp_addon(self, blender_path: Any, timeout_seconds: int = 60) -> dict[str, Any]:
        script = """
import addon_utils
import json
import traceback
result = {"success": False, "available": False, "enabled": False, "error": ""}
try:
    addon_utils.enable("blender_mcp", default_set=True, persistent=True)
    available, enabled = addon_utils.check("blender_mcp")
    result["available"] = bool(available)
    result["enabled"] = bool(enabled)
    result["success"] = bool(enabled)
except Exception as exc:
    result["error"] = str(exc)
    result["traceback"] = traceback.format_exc()[-4000:]
print("REVERIE_BLENDER_MCP_ENABLE=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
if not result["success"]:
    raise SystemExit(25)
""".strip()
        completed = self._run_blender_python(blender_path, script, timeout_seconds)
        probe = self._extract_marker_json(f"{completed.get('stdout', '')}\n{completed.get('stderr', '')}", "REVERIE_BLENDER_MCP_ENABLE=")
        return {
            "success": bool(completed.get("exit_code") == 0 and probe.get("success")),
            "probe": probe,
            "command": completed.get("command", []),
            "exit_code": completed.get("exit_code"),
            "stdout": str(completed.get("stdout", ""))[-3000:],
            "stderr": str(completed.get("stderr", ""))[-3000:],
        }

    def _normalize_mcp_host_port(self, payload: dict[str, Any] | None = None) -> tuple[str, int]:
        payload = payload or {}
        host = str(payload.get("host") or os.environ.get("BLENDER_HOST") or BLENDER_MCP_DEFAULT_HOST).strip() or BLENDER_MCP_DEFAULT_HOST
        try:
            port = int(payload.get("port") or os.environ.get("BLENDER_PORT") or BLENDER_MCP_DEFAULT_PORT)
        except (TypeError, ValueError):
            port = BLENDER_MCP_DEFAULT_PORT
        return host, max(1024, min(65535, port))

    def _probe_tcp(self, host: str, port: int, timeout_seconds: float = 0.5) -> bool:
        try:
            with socket.create_connection((host, int(port)), timeout=max(0.1, timeout_seconds)):
                return True
        except Exception:
            return False

    def _read_mcp_pid(self) -> dict[str, Any]:
        if not self.blender_mcp_pid_path.exists():
            return {}
        try:
            payload = json.loads(self.blender_mcp_pid_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _pid_running(self, pid: Any) -> bool:
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            return False
        if pid_int <= 0:
            return False
        try:
            os.kill(pid_int, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False

    def _blender_mcp_command(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        host, port = self._normalize_mcp_host_port(payload)
        uv = shutil.which("uv")
        env = {"BLENDER_HOST": host, "BLENDER_PORT": str(port)}
        if uv:
            return {
                "server_name": BLENDER_MCP_SERVER_NAME,
                "command": uv,
                "args": ["run", "--directory", str(self.blender_mcp_root), "blender-mcp"],
                "cwd": str(self.blender_mcp_root),
                "env": env,
                "transport": "stdio",
            }
        source_path = self.blender_mcp_root / "src"
        env["PYTHONPATH"] = str(source_path)
        return {
            "server_name": BLENDER_MCP_SERVER_NAME,
            "command": sys.executable,
            "args": ["-m", "blender_mcp.server"],
            "cwd": str(self.blender_mcp_root),
            "env": env,
            "transport": "stdio",
        }

    def _write_blender_mcp_launcher_script(self, host: str, port: int) -> Path:
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        script = f"""
import importlib
import json
import time
import traceback

result = {{"success": False, "host": {json.dumps(host)}, "port": {int(port)}, "error": ""}}
try:
    import addon_utils
    import bpy
    addon_utils.enable("blender_mcp", default_set=True, persistent=True)
    module = importlib.import_module("blender_mcp")
    if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
        try:
            bpy.types.blendermcp_server.stop()
        except Exception:
            pass
    bpy.types.blendermcp_server = module.BlenderMCPServer(host={json.dumps(host)}, port={int(port)})
    bpy.types.blendermcp_server.start()
    bpy.context.scene.blendermcp_port = {int(port)}
    bpy.context.scene.blendermcp_server_running = True
    result["success"] = True
except Exception as exc:
    result["error"] = str(exc)
    result["traceback"] = traceback.format_exc()[-4000:]
print({json.dumps(BLENDER_MCP_START_MARKER)} + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
if not result["success"]:
    raise SystemExit(26)
while True:
    time.sleep(1.0)
""".strip()
        path = self.tmp_root / "reverie_blender_mcp_socket_server.py"
        path.write_text(script, encoding="utf-8")
        return path

    def _mcp_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("auto_install", True) is not False and not self._valid_blender_mcp_source(self.blender_mcp_root):
            install = self._mcp_install({"force": False, "update": False, "enable_addon": False, "timeout_seconds": payload.get("timeout_seconds")})
            if not install.get("success"):
                return self._fail("Blender MCP auto-install failed.", {"install": install, **self._mcp_status_data(payload)})
        elif not self._valid_blender_mcp_source(self.blender_mcp_root):
            return self._fail("Blender MCP is not installed. Run mcp_install first.", self._mcp_status_data(payload))

        detection, deploy_result = self._ensure_ready_detection(payload)
        if not detection["available"]:
            return self._fail("No Blender executable detected for Blender MCP.", {"detected": detection, "deployment": deploy_result, **self._mcp_status_data(payload)})

        addon_target = self._blender_mcp_addon_target()
        if not addon_target.exists():
            install = self._mcp_install({"force": False, "update": False, "enable_addon": False})
            if not install.get("success"):
                return self._fail("Blender MCP addon install failed.", {"install": install, **self._mcp_status_data(payload)})

        host, port = self._normalize_mcp_host_port(payload)
        status = self._mcp_status_data({"host": host, "port": port})
        if status.get("socket_reachable") and status.get("process_running"):
            return self._ok("Blender MCP socket server is already running.", status)

        script_path = self._write_blender_mcp_launcher_script(host, port)
        command = [detection["path"], "--background", "--python", str(script_path)]
        self.blender_mcp_root.mkdir(parents=True, exist_ok=True)
        log_handle = self.blender_mcp_log_path.open("a", encoding="utf-8", errors="replace")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=str(Path(detection["path"]).parent),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                shell=False,
                env=self._blender_env(),
                creationflags=creationflags,
            )
        except Exception as exc:
            log_handle.close()
            return self._fail(str(exc), {"command": command, **self._mcp_status_data({"host": host, "port": port})})
        finally:
            try:
                log_handle.close()
            except Exception:
                pass

        pid_payload = {
            "pid": int(process.pid),
            "host": host,
            "port": port,
            "command": command,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "log_path": str(self.blender_mcp_log_path),
        }
        self.blender_mcp_pid_path.write_text(json.dumps(pid_payload, indent=2), encoding="utf-8")

        timeout = max(2, int(payload.get("timeout_seconds") or 20))
        reachable = False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if process.poll() is not None:
                break
            if self._probe_tcp(host, port, timeout_seconds=0.4):
                reachable = True
                break
            time.sleep(0.25)

        data = {"detected": detection, "deployment": deploy_result, "pid": int(process.pid), **self._mcp_status_data({"host": host, "port": port})}
        if reachable:
            return self._ok("Blender MCP socket server started.", data)
        return self._fail("Blender MCP process started but the socket did not become reachable before timeout.", data)

    def _mcp_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        pid_data = self._read_mcp_pid()
        pid = pid_data.get("pid")
        data = {"pid_file": str(self.blender_mcp_pid_path), "pid_data": pid_data}
        if not pid:
            return self._ok("No Blender MCP background process is recorded.", data | self._mcp_status_data(payload))
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            return self._fail("Recorded Blender MCP pid is invalid.", data | self._mcp_status_data(payload))

        if os.name == "nt" and bool(payload.get("force", True)):
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid_int), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            data["taskkill"] = {"exit_code": completed.returncode, "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]}
        else:
            try:
                os.kill(pid_int, 15)
                data["terminated"] = True
            except Exception as exc:
                data["terminated"] = False
                data["error"] = str(exc)

        try:
            self.blender_mcp_pid_path.unlink(missing_ok=True)
        except Exception:
            pass
        return self._ok("Blender MCP background process stop requested.", data | self._mcp_status_data(payload))

    def _mcp_status_data(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        host, port = self._normalize_mcp_host_port(payload)
        pid_data = self._read_mcp_pid()
        pid = pid_data.get("pid")
        process_running = self._pid_running(pid)
        socket_reachable = self._probe_tcp(host, port, timeout_seconds=0.25)
        command = self._blender_mcp_command({"host": host, "port": port})
        addon_target = self._blender_mcp_addon_target()
        return {
            "repo_url": BLENDER_MCP_REPO_URL,
            "installed": self._valid_blender_mcp_source(self.blender_mcp_root),
            "source_dir": str(self.blender_mcp_root),
            "addon_path": str(addon_target),
            "addon_installed": addon_target.exists(),
            "host": host,
            "port": port,
            "pid": int(pid) if str(pid or "").isdigit() else None,
            "pid_file": str(self.blender_mcp_pid_path),
            "process_running": process_running,
            "socket_reachable": socket_reachable,
            "log_path": str(self.blender_mcp_log_path),
            "mcp": command,
            "static_tools": self._blender_mcp_tools_static(),
            "uv_available": bool(shutil.which("uv")),
            "storage_policy": "plugin-local",
        }

    def _mcp_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._mcp_status_data(payload)
        if bool(payload.get("probe_tools", False)):
            data["tools_probe"] = self._probe_mcp_tools_list(payload)
            data["tools_list_ok"] = bool(data["tools_probe"].get("success") and data["tools_probe"].get("tools"))
        message = "Blender MCP is installed." if data["installed"] else "Blender MCP is not installed."
        return self._ok(message, data)

    def _mcp_info(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._mcp_status_data(payload)
        data["server_name"] = BLENDER_MCP_SERVER_NAME
        data["command"] = data["mcp"].get("command", "")
        data["args"] = data["mcp"].get("args", [])
        data["cwd"] = data["mcp"].get("cwd", "")
        data["env"] = data["mcp"].get("env", {})
        data["tools"] = [{"name": name} for name in data.get("static_tools", [])]
        data["tools_list_ok"] = False
        if bool(payload.get("probe_tools", False)):
            probe = self._probe_mcp_tools_list(payload)
            data["tools_probe"] = probe
            if probe.get("success") and probe.get("tools"):
                data["tools"] = probe["tools"]
                data["tools_list_ok"] = True
        message = "Blender MCP info is available." if data["installed"] else "Blender MCP is not installed."
        return self._ok(message, data) if data["installed"] else self._fail(message, data)

    def _probe_mcp_tools_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._valid_blender_mcp_source(self.blender_mcp_root):
            return {"success": False, "error": "Blender MCP is not installed.", "tools": []}
        command_data = self._blender_mcp_command(payload)
        timeout = max(3, int(payload.get("timeout_seconds") or 12))
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in command_data.get("env", {}).items()})
        command = [command_data["command"], *command_data.get("args", [])]
        try:
            process = subprocess.Popen(
                command,
                cwd=command_data.get("cwd") or str(self.blender_mcp_root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc), "tools": [], "command": command}

        stdout_queue: queue.Queue[str] = queue.Queue()
        stderr_queue: queue.Queue[str] = queue.Queue()

        def _reader(stream: Any, out_queue: queue.Queue[str]) -> None:
            try:
                for line in stream:
                    out_queue.put(line)
            except Exception:
                pass

        threading.Thread(target=_reader, args=(process.stdout, stdout_queue), daemon=True).start()
        threading.Thread(target=_reader, args=(process.stderr, stderr_queue), daemon=True).start()
        try:
            assert process.stdin is not None
            for message in (
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "reverie-blender-plugin", "version": PLUGIN_VERSION}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ):
                process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
                process.stdin.flush()

            deadline = time.time() + timeout
            seen_stdout: list[str] = []
            while time.time() < deadline:
                try:
                    line = stdout_queue.get(timeout=0.15)
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                seen_stdout.append(stripped)
                if not stripped.startswith("{"):
                    continue
                try:
                    payload_obj = json.loads(stripped)
                except Exception:
                    continue
                if payload_obj.get("id") == 2:
                    result = payload_obj.get("result") if isinstance(payload_obj, dict) else {}
                    tools = result.get("tools", []) if isinstance(result, dict) else []
                    return {"success": bool(tools), "tools": tools if isinstance(tools, list) else [], "command": command, "stdout": seen_stdout[-10:]}
            stderr_lines: list[str] = []
            while not stderr_queue.empty() and len(stderr_lines) < 10:
                stderr_lines.append(stderr_queue.get_nowait().strip())
            return {"success": False, "error": "tools/list probe timed out or returned no tools", "tools": [], "command": command, "stdout": seen_stdout[-10:], "stderr": stderr_lines}
        finally:
            try:
                process.terminate()
            except Exception:
                pass
            try:
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

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
