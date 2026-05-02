"""Godot runtime plugin for Reverie CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile


PLUGIN_VERSION = "0.3.0"
DEFAULT_GODOT_RELEASES_API = "https://api.github.com/repos/godotengine/godot/releases"
DEFAULT_GODOT_REPOSITORY = "https://github.com/godotengine/godot.git"


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


class GodotRuntimePlugin(ReverieRuntimePluginHost):
    """Protocol wrapper around a locally available Godot editor/runtime."""

    def __init__(self) -> None:
        self.plugin_root = self._resolve_plugin_root()
        self.runtime_root = self.plugin_root / "runtime"
        self.download_root = self.plugin_root / "downloads"
        self.source_root = self.plugin_root / "source"
        self.state_path = self.plugin_root / "state" / "runtime_state.json"
        self.bundle_root = self._resolve_bundle_root()

    def build_handshake(self) -> dict[str, Any]:
        return {
            "protocol_version": "1.0",
            "plugin_id": "godot",
            "display_name": "Godot Runtime Plugin",
            "version": PLUGIN_VERSION,
            "runtime_family": "engine",
            "description": (
                "Godot wrapper plugin for runtime detection, install management, "
                "project scanning, editor launch, and headless validation."
            ),
            "tool_call_hint": (
                "Use rc_godot_runtime_status to inspect the current Godot runtime state, "
                "rc_godot_list_versions to inspect official GitHub releases, "
                "rc_godot_install_runtime or rc_godot_ensure_runtime to download or unpack a plugin-local runtime, "
                "rc_godot_clone_source when source checkout is requested, "
                "rc_godot_scan_project before making Godot-specific assumptions, "
                "and rc_godot_headless_check after generating or updating a Godot project."
            ),
            "system_prompt": (
                "This plugin owns Godot-specific runtime checks, installation, and launch behavior. "
                "Prefer the exposed rc_godot_* tools instead of inventing shell commands for Godot. "
                "Keep downloads, source clones, and runtime installs inside the plugin-local depot."
            ),
            "commands": [
                {
                    "name": "runtime_status",
                    "description": "Inspect the currently registered or installed Godot runtime and report plugin-local runtime folders.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "godot_executable": {
                                "type": "string",
                                "description": "Optional absolute path override for one specific check.",
                            }
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Call this before runtime-sensitive Godot actions to see whether the plugin already has a usable editor/runtime.",
                },
                {
                    "name": "list_versions",
                    "description": "List official Godot GitHub release tags and the selected editor archive for this platform.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum release count to return.",
                            }
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Use this when the user wants to choose a Godot version before installation.",
                },
                {
                    "name": "register_runtime",
                    "description": "Register an existing Godot executable so the plugin can reuse it later without re-downloading.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "godot_executable": {
                                "type": "string",
                                "description": "Absolute path to an existing Godot executable or app bundle.",
                            }
                        },
                        "required": ["godot_executable"],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Use this when Godot is already installed elsewhere on the machine and should become the preferred Reverie runtime.",
                },
                {
                    "name": "install_runtime",
                    "description": "Install a plugin-local Godot runtime from an official release download or a local zip archive.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "version": {
                                "type": "string",
                                "description": "Requested Godot release tag. Use `latest` to resolve the newest official stable release.",
                            },
                            "download_url": {
                                "type": "string",
                                "description": "Optional direct archive URL. When set, the plugin skips official release discovery.",
                            },
                            "archive_path": {
                                "type": "string",
                                "description": "Optional local zip archive path for offline or test installs.",
                            },
                            "force": {
                                "type": "boolean",
                                "description": "When true, replace an existing plugin-local install that uses the same version folder.",
                            },
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Prefer this when the plugin should manage its own Godot runtime under .reverie/plugins/godot/runtime.",
                },
                {
                    "name": "ensure_runtime",
                    "description": "Ensure a plugin-local Godot runtime exists, downloading the latest official release when needed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "version": {
                                "type": "string",
                                "description": "Requested release tag, or `latest` for the latest official stable release.",
                            },
                            "force": {
                                "type": "boolean",
                                "description": "When true, reinstall the selected version even if a runtime already exists.",
                            },
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Use this for `/plugins deploy godot` style setup where the plugin should manage the runtime itself.",
                },
                {
                    "name": "source_status",
                    "description": "Inspect Godot source checkouts stored in the plugin-local source depot.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Use this before cloning or updating Godot source code.",
                },
                {
                    "name": "clone_source",
                    "description": "Clone Godot source from GitHub into the plugin-local source depot.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string", "description": "Release tag, branch, commit, or `latest`."},
                            "repository": {"type": "string", "description": "Optional repository URL override. Defaults to the official Godot GitHub repo."},
                            "target_name": {"type": "string", "description": "Optional folder name under the plugin source depot."},
                            "depth": {"type": "integer", "description": "Shallow clone depth. Defaults to 1."},
                            "with_submodules": {"type": "boolean", "description": "When true, initialize submodules after clone."},
                            "force": {"type": "boolean", "description": "When true, replace an existing target checkout inside the source depot."},
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Use this only when source is needed; official runtime downloads are faster for normal Godot execution.",
                },
                {
                    "name": "detect_runtime",
                    "description": "Find a usable Godot editor/runtime executable from the plugin install tree or environment overrides.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "godot_executable": {
                                "type": "string",
                                "description": "Optional absolute path to a Godot executable or app bundle.",
                            }
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Call this first when the user asks to verify whether Godot is available on the machine.",
                    "example": 'rc_godot_detect_runtime(godot_executable="C:/Tools/Godot_v4.5-stable_win64.exe")',
                },
                {
                    "name": "version",
                    "description": "Return the detected Godot version string by invoking `--version`.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "godot_executable": {
                                "type": "string",
                                "description": "Optional absolute path to a Godot executable or app bundle.",
                            }
                        },
                        "required": [],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                },
                {
                    "name": "scan_project",
                    "description": "Inspect a Godot project directory and summarize scenes, scripts, models, and key folders.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_dir": {
                                "type": "string",
                                "description": "Absolute or relative path to the Godot project root.",
                            }
                        },
                        "required": ["project_dir"],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                },
                {
                    "name": "open_editor",
                    "description": "Launch the Godot editor for a project using `--editor --path <project>`.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_dir": {
                                "type": "string",
                                "description": "Absolute or relative path to the Godot project root.",
                            },
                            "godot_executable": {
                                "type": "string",
                                "description": "Optional absolute path to a Godot executable or app bundle.",
                            },
                            "detached": {
                                "type": "boolean",
                                "description": "When true, spawn the editor and return immediately.",
                            },
                        },
                        "required": ["project_dir"],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Only use this when the user explicitly wants the editor opened or when a visual Godot check is required.",
                },
                {
                    "name": "headless_check",
                    "description": "Run a headless Godot validation/import pass with `--headless --path <project> --quit`.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_dir": {
                                "type": "string",
                                "description": "Absolute or relative path to the Godot project root.",
                            },
                            "godot_executable": {
                                "type": "string",
                                "description": "Optional absolute path to a Godot executable or app bundle.",
                            },
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Maximum seconds to wait for the headless check.",
                            },
                        },
                        "required": ["project_dir"],
                    },
                    "expose_as_tool": True,
                    "include_modes": ["reverie", "reverie-gamer"],
                    "guidance": "Use after generating a Godot scaffold, importing glTF assets, or updating project files.",
                },
            ],
        }

    def handle_command(self, command_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if command_name == "runtime_status":
            return self._cmd_runtime_status(payload)
        if command_name == "list_versions":
            return self._cmd_list_versions(payload)
        if command_name == "register_runtime":
            return self._cmd_register_runtime(payload)
        if command_name == "install_runtime":
            return self._cmd_install_runtime(payload)
        if command_name == "ensure_runtime":
            return self._cmd_ensure_runtime(payload)
        if command_name == "source_status":
            return self._cmd_source_status(payload)
        if command_name == "clone_source":
            return self._cmd_clone_source(payload)
        if command_name == "detect_runtime":
            return self._cmd_detect_runtime(payload)
        if command_name == "version":
            return self._cmd_version(payload)
        if command_name == "scan_project":
            return self._cmd_scan_project(payload)
        if command_name == "open_editor":
            return self._cmd_open_editor(payload)
        if command_name == "headless_check":
            return self._cmd_headless_check(payload)
        return {"success": False, "output": "", "error": f"Unknown command: {command_name}", "data": {}}

    def _cmd_runtime_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        detection = self._detect_runtime(str(payload.get("godot_executable") or "").strip())
        state = self._load_state()
        version_text = self._probe_version(detection["path"]) if detection["path"] else ""
        return {
            "success": True,
            "output": (
                f"Godot runtime available at {detection['path']}"
                if detection["path"]
                else "No usable Godot runtime is registered or installed yet."
            ),
            "error": "",
            "data": {
                "runtime_available": detection["path"] is not None,
                "runtime_path": str(detection["path"]) if detection["path"] else "",
                "runtime_source": detection["source"],
                "version": version_text,
                "checked": detection["checked"],
                "state_backend": self._state_backend_label(),
                "state_location": self._state_location_label(),
                "registered_runtime_path": str(state.get("registered_runtime_path") or ""),
                "installed_runtime_path": str(state.get("installed_runtime_path") or ""),
                "installed_runtime_version": str(state.get("installed_runtime_version") or ""),
                "install_root": str(self.runtime_root),
                "downloads_root": str(self.download_root),
                "source_root": str(self.source_root),
                "bundled_runtime_archive": str(self._find_bundled_runtime_archive() or ""),
                "installed_versions": self._list_installed_runtime_dirs(),
                "source_checkouts": self._list_source_checkouts(),
            },
        }

    def _cmd_list_versions(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            limit = int(payload.get("limit", 8) or 8)
        except (TypeError, ValueError):
            limit = 8
        limit = max(1, min(limit, 30))
        try:
            releases = self._http_get_json_list(DEFAULT_GODOT_RELEASES_API)
        except Exception as exc:
            return {"success": False, "output": "", "error": str(exc), "data": {}}

        rows: list[dict[str, str]] = []
        for release in releases[:limit]:
            if not isinstance(release, dict):
                continue
            asset = self._select_release_asset(list(release.get("assets", []) or []))
            rows.append(
                {
                    "tag": str(release.get("tag_name") or ""),
                    "name": str(release.get("name") or ""),
                    "prerelease": str(bool(release.get("prerelease", False))).lower(),
                    "asset_name": str(asset.get("name") or "") if asset else "",
                    "download_url": str(asset.get("browser_download_url") or "") if asset else "",
                }
            )
        return {
            "success": True,
            "output": "\n".join(f"{row['tag']} :: {row['asset_name']}" for row in rows),
            "error": "",
            "data": {"repository": DEFAULT_GODOT_REPOSITORY, "releases": rows},
        }

    def _cmd_register_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_runtime = str(payload.get("godot_executable") or "").strip()
        if not raw_runtime:
            return {"success": False, "output": "", "error": "godot_executable is required.", "data": {}}

        runtime_path = self._resolve_input_path(raw_runtime)
        if not self._is_runtime_target(runtime_path):
            return {
                "success": False,
                "output": "",
                "error": f"Godot runtime does not exist: {runtime_path}",
                "data": {"path": str(runtime_path)},
            }

        runtime_path = runtime_path.resolve(strict=False)
        state = self._load_state()
        state["registered_runtime_path"] = str(runtime_path)
        state["updated_at"] = self._utc_now()
        self._save_state(state)
        return {
            "success": True,
            "output": f"Registered Godot runtime: {runtime_path}",
            "error": "",
            "data": {
                "path": str(runtime_path),
                "version": self._probe_version(runtime_path),
                "state_backend": self._state_backend_label(),
                "state_location": self._state_location_label(),
            },
        }

    def _cmd_install_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        archive_path_value = str(payload.get("archive_path") or "").strip()
        download_url = str(payload.get("download_url") or "").strip()
        requested_version = str(payload.get("version") or "latest").strip() or "latest"
        force = bool(payload.get("force", False))
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.download_root.mkdir(parents=True, exist_ok=True)

        source_label = ""
        resolved_version = requested_version
        asset_name = ""
        if archive_path_value:
            archive_path = self._resolve_input_path(archive_path_value)
            if not archive_path.exists() or not archive_path.is_file():
                return {
                    "success": False,
                    "output": "",
                    "error": f"Archive path does not exist: {archive_path}",
                    "data": {"archive_path": str(archive_path)},
                }
            source_label = "local-archive"
            asset_name = archive_path.name
        else:
            try:
                release = self._resolve_release_asset(requested_version=requested_version, download_url=download_url)
            except Exception as exc:
                return {
                    "success": False,
                    "output": "",
                    "error": str(exc),
                    "data": {"version": requested_version, "download_url": download_url},
                }
            resolved_version = str(release.get("version") or requested_version)
            asset_name = str(release.get("asset_name") or "godot-runtime.zip")
            download_url = str(release.get("download_url") or download_url)
            source_label = str(release.get("source") or "official-release")
            archive_path = self.download_root / asset_name
            try:
                self._download_file(download_url, archive_path)
            except Exception as exc:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Failed to download Godot runtime: {exc}",
                    "data": {
                        "version": resolved_version,
                        "download_url": download_url,
                        "archive_path": str(archive_path),
                    },
                }

        try:
            install_result = self._install_archive(archive_path, resolved_version, force)
        except Exception as exc:
            return {
                "success": False,
                "output": "",
                "error": str(exc),
                "data": {"archive_path": str(archive_path), "version": resolved_version},
            }

        runtime_path = install_result["runtime_path"]
        state = self._load_state()
        state["installed_runtime_path"] = str(runtime_path)
        state["installed_runtime_version"] = resolved_version
        state["last_install_asset_name"] = asset_name
        state["last_install_source"] = source_label
        state["last_download_url"] = download_url
        state["updated_at"] = self._utc_now()
        if not str(state.get("registered_runtime_path") or "").strip():
            state["registered_runtime_path"] = str(runtime_path)
        self._save_state(state)

        return {
            "success": True,
            "output": f"Installed Godot runtime at {runtime_path}",
            "error": "",
            "data": {
                "runtime_path": str(runtime_path),
                "version": resolved_version,
                "version_output": self._probe_version(runtime_path),
                "install_dir": str(install_result["install_dir"]),
                "archive_path": str(archive_path),
                "asset_name": asset_name,
                "source": source_label,
                "download_url": download_url,
                "state_backend": self._state_backend_label(),
                "state_location": self._state_location_label(),
            },
        }

    def _cmd_ensure_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        force = bool(payload.get("force", False))
        requested_version = str(payload.get("version") or "latest").strip() or "latest"
        detection = self._detect_runtime(str(payload.get("godot_executable") or "").strip())
        if detection["path"] is not None and not force:
            return {
                "success": True,
                "output": f"Godot runtime already available at {detection['path']}",
                "error": "",
                "data": {
                    "deployed": False,
                    "runtime_path": str(detection["path"]),
                    "source": detection["source"],
                    "version": self._probe_version(detection["path"]),
                },
            }

        bundled_archive = self._find_bundled_runtime_archive()
        if bundled_archive is not None:
            result = self._cmd_install_runtime(
                {
                    "archive_path": str(bundled_archive),
                    "version": self._infer_version_from_archive_name(bundled_archive),
                    "force": force,
                }
            )
        else:
            result = self._cmd_install_runtime({"version": requested_version, "force": force})
        if isinstance(result.get("data"), dict):
            result["data"]["deployed"] = bool(result.get("success", False))
        return result

    def _cmd_source_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        checkouts = self._source_checkout_details()
        return {
            "success": True,
            "output": "\n".join(f"{item['name']} :: {item['head']}" for item in checkouts) or "No Godot source checkouts found.",
            "error": "",
            "data": {
                "source_root": str(self.source_root),
                "repository": DEFAULT_GODOT_REPOSITORY,
                "checkouts": checkouts,
            },
        }

    def _cmd_clone_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        repository = str(payload.get("repository") or DEFAULT_GODOT_REPOSITORY).strip()
        requested_version = str(payload.get("version") or "latest").strip() or "latest"
        target_name = str(payload.get("target_name") or "").strip()
        force = bool(payload.get("force", False))
        with_submodules = bool(payload.get("with_submodules", False))
        try:
            depth = int(payload.get("depth", 1) or 1)
        except (TypeError, ValueError):
            depth = 1
        depth = max(1, min(depth, 1000))
        git_exe = shutil.which("git.exe") or shutil.which("git")
        if not git_exe:
            return {"success": False, "output": "", "error": "Git executable not found in PATH.", "data": {}}

        try:
            ref = self._resolve_source_ref(requested_version)
        except Exception as exc:
            return {"success": False, "output": "", "error": str(exc), "data": {"version": requested_version}}
        target = self._source_target_path(target_name or f"godot-{self._sanitize_version_dir_name(ref)}")
        if target.exists():
            if not force:
                return {
                    "success": True,
                    "output": f"Godot source checkout already exists: {target}",
                    "error": "",
                    "data": {"cloned": False, "source_dir": str(target), "ref": ref, "repository": repository},
                }
            self._safe_remove_source_dir(target)

        self.source_root.mkdir(parents=True, exist_ok=True)
        command = self._build_clone_command(git_exe, repository, ref, target, depth, use_http11=False)
        completed = self._run_git_clone(command)
        if completed.returncode != 0 and target.exists():
            self._safe_remove_source_dir(target)
            command = self._build_clone_command(git_exe, repository, ref, target, depth, use_http11=True)
            completed = self._run_git_clone(command)
        if completed.returncode != 0:
            if target.exists():
                self._safe_remove_source_dir(target)
            return {
                "success": False,
                "output": completed.stdout.strip(),
                "error": completed.stderr.strip() or f"git clone failed with exit code {completed.returncode}",
                "data": {"command": command, "source_dir": str(target), "ref": ref, "repository": repository},
            }
        if with_submodules:
            submodule = subprocess.run(
                [git_exe, "submodule", "update", "--init", "--recursive", "--depth", str(depth)],
                cwd=str(target),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=7200,
            )
            if submodule.returncode != 0:
                return {
                    "success": False,
                    "output": completed.stdout.strip() + "\n" + submodule.stdout.strip(),
                    "error": submodule.stderr.strip() or f"git submodule update failed with exit code {submodule.returncode}",
                    "data": {"source_dir": str(target), "ref": ref, "repository": repository},
                }

        state = self._load_state()
        state["source_checkout_path"] = str(target)
        state["source_checkout_ref"] = ref
        state["source_repository"] = repository
        state["updated_at"] = self._utc_now()
        self._save_state(state)
        return {
            "success": True,
            "output": f"Cloned Godot source {ref} into {target}",
            "error": "",
            "data": {"cloned": True, "source_dir": str(target), "ref": ref, "repository": repository},
        }

    def _cmd_detect_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        detection = self._detect_runtime(str(payload.get("godot_executable") or "").strip())
        if detection["path"] is None:
            return {
                "success": False,
                "output": "",
                "error": "Godot runtime not found. Register an existing runtime or install one under the plugin runtime directory.",
                "data": {"checked": detection["checked"], "source": detection["source"]},
            }

        version_text = self._probe_version(detection["path"])
        return {
            "success": True,
            "output": f"Detected Godot runtime at {detection['path']}",
            "error": "",
            "data": {
                "path": str(detection["path"]),
                "source": detection["source"],
                "version": version_text,
                "checked": detection["checked"],
            },
        }

    def _cmd_version(self, payload: dict[str, Any]) -> dict[str, Any]:
        detection = self._detect_runtime(str(payload.get("godot_executable") or "").strip())
        if detection["path"] is None:
            return {
                "success": False,
                "output": "",
                "error": "Godot runtime not found.",
                "data": {"checked": detection["checked"], "source": detection["source"]},
            }
        version_text = self._probe_version(detection["path"])
        return {
            "success": True,
            "output": version_text or f"Godot runtime detected at {detection['path']}",
            "error": "",
            "data": {"path": str(detection["path"]), "source": detection["source"], "version": version_text},
        }

    def _cmd_scan_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._resolve_project_dir(payload.get("project_dir"))
        project_file = project_dir / "project.godot"
        counts = {
            "scenes": 0,
            "scripts": 0,
            "materials": 0,
            "models": 0,
            "textures": 0,
        }
        sample_scenes: list[str] = []

        for path in project_dir.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in {".tscn", ".scn"}:
                counts["scenes"] += 1
                if len(sample_scenes) < 12:
                    sample_scenes.append(str(path.relative_to(project_dir)))
            elif suffix in {".gd", ".cs"}:
                counts["scripts"] += 1
            elif suffix in {".material", ".tres", ".res"}:
                counts["materials"] += 1
            elif suffix in {".glb", ".gltf", ".fbx", ".obj"}:
                counts["models"] += 1
            elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".ktx", ".ktx2"}:
                counts["textures"] += 1

        top_dirs = sorted(
            [
                item.name
                for item in project_dir.iterdir()
                if item.is_dir() and not item.name.startswith(".")
            ]
        )
        summary = [
            f"Project root: {project_dir}",
            f"project.godot: {'present' if project_file.exists() else 'missing'}",
            f"Scenes: {counts['scenes']}",
            f"Scripts: {counts['scripts']}",
            f"Models: {counts['models']}",
            f"Textures: {counts['textures']}",
        ]
        if sample_scenes:
            summary.append(f"Sample scenes: {', '.join(sample_scenes[:6])}")

        return {
            "success": True,
            "output": " | ".join(summary),
            "error": "",
            "data": {
                "project_dir": str(project_dir),
                "project_file_exists": project_file.exists(),
                "counts": counts,
                "top_dirs": top_dirs,
                "sample_scenes": sample_scenes,
            },
        }

    def _cmd_open_editor(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._resolve_project_dir(payload.get("project_dir"))
        self._ensure_project_file(project_dir)

        detection = self._detect_runtime(str(payload.get("godot_executable") or "").strip())
        if detection["path"] is None:
            return {
                "success": False,
                "output": "",
                "error": "Godot runtime not found.",
                "data": {"checked": detection["checked"], "source": detection["source"]},
            }

        detached = bool(payload.get("detached", True))
        command = self._build_runtime_command(detection["path"], ["--editor", "--path", str(project_dir)])

        if detached:
            process = self._spawn_detached(command, cwd=project_dir)
            return {
                "success": True,
                "output": f"Opened Godot editor for {project_dir}",
                "error": "",
                "data": {
                    "pid": int(process.pid),
                    "command": command,
                    "path": str(detection["path"]),
                    "source": detection["source"],
                },
            }

        completed = subprocess.run(
            command,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        success = completed.returncode == 0
        return {
            "success": success,
            "output": completed.stdout.strip() or f"Godot editor exited with code {completed.returncode}",
            "error": "" if success else completed.stderr.strip(),
            "data": {
                "returncode": int(completed.returncode),
                "command": command,
                "path": str(detection["path"]),
                "source": detection["source"],
            },
        }

    def _cmd_headless_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._resolve_project_dir(payload.get("project_dir"))
        self._ensure_project_file(project_dir)

        detection = self._detect_runtime(str(payload.get("godot_executable") or "").strip())
        if detection["path"] is None:
            return {
                "success": False,
                "output": "",
                "error": "Godot runtime not found.",
                "data": {"checked": detection["checked"], "source": detection["source"]},
            }

        timeout_seconds = max(int(payload.get("timeout_seconds", 120) or 120), 5)
        command = self._build_runtime_command(detection["path"], ["--headless", "--path", str(project_dir), "--quit"])
        try:
            completed = subprocess.run(
                command,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "output": "",
                "error": f"Headless Godot check timed out after {timeout_seconds}s.",
                "data": {
                    "command": command,
                    "path": str(detection["path"]),
                    "source": detection["source"],
                    "stdout": str(getattr(exc, "stdout", "") or ""),
                    "stderr": str(getattr(exc, "stderr", "") or ""),
                },
            }

        success = completed.returncode == 0
        output_text = completed.stdout.strip() or completed.stderr.strip() or "Godot headless check completed."
        return {
            "success": success,
            "output": output_text,
            "error": "" if success else output_text,
            "data": {
                "returncode": int(completed.returncode),
                "command": command,
                "path": str(detection["path"]),
                "source": detection["source"],
            },
        }

    def _resolve_project_dir(self, raw_value: Any) -> Path:
        raw = str(raw_value or "").strip()
        if not raw:
            raise RuntimeError("project_dir is required.")
        path = self._resolve_input_path(raw)
        if not path.exists() or not path.is_dir():
            raise RuntimeError(f"Godot project directory does not exist: {path}")
        return path

    def _ensure_project_file(self, project_dir: Path) -> None:
        if not (project_dir / "project.godot").exists():
            raise RuntimeError(f"Missing Godot project file: {project_dir / 'project.godot'}")

    def _detect_runtime(self, candidate: str) -> dict[str, Any]:
        candidates = self._runtime_candidates(candidate)
        checked = [str(path.resolve(strict=False)) for _, path in candidates]
        for source, path in candidates:
            if self._is_runtime_target(path):
                return {"path": path.resolve(strict=False), "source": source, "checked": checked}
        return {"path": None, "source": "missing", "checked": checked}

    def _runtime_candidates(self, candidate: str) -> list[tuple[str, Path]]:
        self._ensure_bundled_runtime_available()
        state = self._load_state()
        values: list[tuple[str, Path]] = []

        if candidate:
            values.append(("explicit", self._resolve_input_path(candidate)))

        registered_runtime = str(state.get("registered_runtime_path") or "").strip()
        if registered_runtime:
            values.append(("registered-state", self._resolve_input_path(registered_runtime)))

        installed_runtime = str(state.get("installed_runtime_path") or "").strip()
        if installed_runtime:
            values.append(("installed-state", self._resolve_input_path(installed_runtime)))

        for env_name in ("REVERIE_GODOT_EXE", "GODOT_EXE"):
            env_value = str(os.environ.get(env_name, "") or "").strip()
            if env_value:
                values.append((f"env:{env_name}", self._resolve_input_path(env_value)))

        for binary_name in ("godot", "godot4", "godot.exe", "godot4.exe", "Godot.exe"):
            resolved = shutil.which(binary_name)
            if resolved:
                values.append((f"path:{binary_name}", Path(resolved)))

        for discovered in self._iter_runtime_tree_candidates(self.runtime_root):
            values.append(("plugin-runtime", discovered))
        for discovered in self._iter_runtime_tree_candidates(self.plugin_root):
            values.append(("plugin-root", discovered))

        seen: set[str] = set()
        deduped: list[tuple[str, Path]] = []
        for source, item in values:
            key = str(item.resolve(strict=False)).lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append((source, item))
        return deduped

    def _iter_runtime_tree_candidates(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        patterns = [
            "Godot*.exe",
            "godot*.exe",
            "Godot*.app",
            "godot*.app",
            "**/Godot*.exe",
            "**/godot*.exe",
            "**/Godot*.app",
            "**/godot*.app",
        ]
        matches: list[Path] = []
        seen: set[str] = set()
        for pattern in patterns:
            for candidate in sorted(root.glob(pattern), key=lambda path: str(path).lower()):
                key = str(candidate.resolve(strict=False)).lower()
                if key in seen:
                    continue
                seen.add(key)
                matches.append(candidate)
        return matches

    def _is_runtime_target(self, path: Path) -> bool:
        if not path.exists():
            return False
        if path.name.lower().endswith(".app"):
            return path.is_dir()
        return path.is_file()

    def _probe_version(self, runtime_path: Optional[Path]) -> str:
        if runtime_path is None:
            return ""
        command = self._build_runtime_command(runtime_path, ["--version"])
        try:
            completed = subprocess.run(
                command,
                cwd=str(runtime_path.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except Exception as exc:
            return f"Version probe failed: {exc}"

        return completed.stdout.strip() or completed.stderr.strip() or f"exit={completed.returncode}"

    def _build_runtime_command(self, runtime_path: Path, args: list[str]) -> list[str]:
        resolved = runtime_path.resolve(strict=False)
        if resolved.name.lower().endswith(".app"):
            macos_dir = resolved / "Contents" / "MacOS"
            if macos_dir.exists():
                binaries = [item for item in macos_dir.iterdir() if item.is_file()]
                if binaries:
                    return [str(binaries[0]), *args]
        return [str(resolved), *args]

    def _spawn_detached(self, command: list[str], *, cwd: Path) -> subprocess.Popen:
        popen_kwargs: dict[str, Any] = {
            "cwd": str(cwd),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform.startswith("win"):
            creationflags = 0
            creationflags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
            creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["start_new_session"] = True
        return subprocess.Popen(command, **popen_kwargs)

    def _state_backend_label(self) -> str:
        return "plugin-local-json"

    def _state_location_label(self) -> str:
        return str(self.state_path)

    def _state_namespace(self) -> str:
        return self._sanitize_version_dir_name(self.plugin_root.name or "godot")

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _save_state(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _list_installed_runtime_dirs(self) -> list[str]:
        if not self.runtime_root.exists():
            return []
        return sorted([item.name for item in self.runtime_root.iterdir() if item.is_dir()])

    def _list_source_checkouts(self) -> list[str]:
        if not self.source_root.exists():
            return []
        return sorted([item.name for item in self.source_root.iterdir() if item.is_dir()])

    def _source_checkout_details(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for item in self._list_source_checkouts():
            path = self.source_root / item
            rows.append({"name": item, "path": str(path), "head": self._git_head(path)})
        return rows

    def _git_head(self, path: Path) -> str:
        git_exe = shutil.which("git.exe") or shutil.which("git")
        if not git_exe or not (path / ".git").exists():
            return ""
        try:
            completed = subprocess.run(
                [git_exe, "rev-parse", "--short", "HEAD"],
                cwd=str(path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        except Exception:
            return ""
        return completed.stdout.strip() if completed.returncode == 0 else ""

    def _source_target_path(self, target_name: str) -> Path:
        safe = self._sanitize_version_dir_name(target_name).replace("/", "_").replace("\\", "_")
        target = (self.source_root / safe).resolve(strict=False)
        root = self.source_root.resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"Refusing to use source target outside plugin source root: {target}") from exc
        return target

    def _build_clone_command(
        self,
        git_exe: str,
        repository: str,
        ref: str,
        target: Path,
        depth: int,
        *,
        use_http11: bool,
    ) -> list[str]:
        prefix = [git_exe]
        if use_http11:
            prefix.extend(["-c", "http.version=HTTP/1.1", "-c", "http.postBuffer=524288000"])
        return [
            *prefix,
            "clone",
            "--depth",
            str(depth),
            "--filter=blob:none",
            "--single-branch",
            "--no-tags",
            "--branch",
            ref,
            repository,
            str(target),
        ]

    def _run_git_clone(self, command: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            cwd=str(self.source_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
        )

    def _resolve_release_asset(self, *, requested_version: str, download_url: str) -> dict[str, str]:
        if download_url:
            return {
                "version": requested_version,
                "asset_name": Path(download_url).name or "godot-runtime.zip",
                "download_url": download_url,
                "source": "direct-url",
            }
        release = self._load_release_metadata(requested_version)
        assets = release.get("assets", [])
        if not isinstance(assets, list) or not assets:
            raise RuntimeError("No downloadable assets were found in the requested Godot release.")
        asset = self._select_release_asset(assets)
        if not asset:
            raise RuntimeError("Could not find a supported Godot editor archive in the requested release.")
        return {
            "version": str(release.get("tag_name") or requested_version).strip() or requested_version,
            "asset_name": str(asset.get("name") or "godot-runtime.zip"),
            "download_url": str(asset.get("browser_download_url") or ""),
            "source": "official-release",
        }

    def _load_release_metadata(self, requested_version: str) -> dict[str, Any]:
        version_text = str(requested_version or "latest").strip().lower()
        if version_text in {"", "latest", "stable", "current"}:
            return self._http_get_json(f"{DEFAULT_GODOT_RELEASES_API}/latest")

        base_version = str(requested_version).strip()
        tags = [base_version]
        if base_version.startswith("v"):
            tags.append(base_version[1:])
        else:
            tags.append(f"v{base_version}")

        errors: list[str] = []
        for tag in tags:
            url = f"{DEFAULT_GODOT_RELEASES_API}/tags/{quote(tag)}"
            try:
                return self._http_get_json(url)
            except Exception as exc:
                errors.append(f"{tag}: {exc}")
        raise RuntimeError(f"Failed to resolve Godot release metadata for `{requested_version}`: {'; '.join(errors)}")

    def _resolve_source_ref(self, requested_version: str) -> str:
        version_text = str(requested_version or "latest").strip()
        if version_text.lower() in {"", "latest", "stable", "current"}:
            release = self._load_release_metadata("latest")
            return str(release.get("tag_name") or "").strip() or "master"
        return version_text

    def _select_release_asset(self, assets: list[Any]) -> Optional[dict[str, Any]]:
        ranked: list[tuple[int, dict[str, Any]]] = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "").strip()
            url = str(asset.get("browser_download_url") or "").strip()
            if not name or not url:
                continue
            score = self._score_release_asset(name)
            if score > 0:
                ranked.append((score, asset))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("name") or "").lower()))
        return ranked[0][1]

    def _score_release_asset(self, asset_name: str) -> int:
        lower = asset_name.lower()
        if not lower.endswith(".zip") or "godot" not in lower:
            return 0
        if "export_templates" in lower or "mono" in lower:
            return 0
        score = 10
        if sys.platform.startswith("win"):
            if "win64" in lower:
                score += 20
            if ".exe.zip" in lower:
                score += 10
        elif sys.platform == "darwin":
            if "macos" in lower or "osx" in lower:
                score += 20
        else:
            if "linux" in lower or "x11" in lower:
                score += 20
            if "x86_64" in lower or "64" in lower:
                score += 5
        return score

    def _http_get_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Reverie-Godot-Plugin/0.3"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} while requesting {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error while requesting {url}: {exc.reason}") from exc

        try:
            data = json.loads(payload)
        except Exception as exc:
            raise RuntimeError(f"Invalid JSON received from {url}: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Release metadata from {url} was not a JSON object.")
        return data

    def _http_get_json_list(self, url: str) -> list[Any]:
        request = Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Reverie-Godot-Plugin/0.3"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} while requesting {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error while requesting {url}: {exc.reason}") from exc

        try:
            data = json.loads(payload)
        except Exception as exc:
            raise RuntimeError(f"Invalid JSON received from {url}: {exc}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"Release metadata from {url} was not a JSON array.")
        return data

    def _download_file(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_name(f"{destination.name}.part")
        if temp_path.exists():
            temp_path.unlink()

        curl_binary = shutil.which("curl.exe") or shutil.which("curl")
        if curl_binary:
            completed = subprocess.run(
                [curl_binary, "-L", "--fail", "--silent", "--show-error", "--output", str(temp_path), url],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
            )
            if completed.returncode == 0 and (
                destination.suffix.lower() != ".zip" or zipfile.is_zipfile(temp_path)
            ):
                if destination.exists():
                    destination.unlink()
                shutil.move(str(temp_path), str(destination))
                return
            if temp_path.exists():
                temp_path.unlink()

        request = Request(url, headers={"User-Agent": "Reverie-Godot-Plugin/0.3"})
        with urlopen(request, timeout=300) as response, open(temp_path, "wb") as handle:
            shutil.copyfileobj(response, handle)
        if destination.suffix.lower() == ".zip" and not zipfile.is_zipfile(temp_path):
            temp_path.unlink(missing_ok=True)
            raise RuntimeError("Downloaded file is not a valid zip archive.")
        if destination.exists():
            destination.unlink()
        shutil.move(str(temp_path), str(destination))

    def _install_archive(self, archive_path: Path, version_label: str, force: bool) -> dict[str, Path]:
        if archive_path.suffix.lower() != ".zip":
            raise RuntimeError("Only .zip Godot archives are supported right now.")
        staging_dir = self.runtime_root / f".staging-{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(staging_dir)
            if self._find_runtime_in_tree(staging_dir) is None:
                raise RuntimeError("The archive did not contain a detectable Godot runtime executable.")

            install_dir = self.runtime_root / self._sanitize_version_dir_name(version_label or archive_path.stem)
            if install_dir.exists():
                existing_runtime = self._find_runtime_in_tree(install_dir)
                if existing_runtime is not None and not force:
                    return {
                        "runtime_path": existing_runtime.resolve(strict=False),
                        "install_dir": install_dir.resolve(strict=False),
                    }
                if not force:
                    raise RuntimeError(f"The install directory already exists: {install_dir}. Pass force=true to replace it.")
                self._safe_remove_dir(install_dir)

            shutil.move(str(staging_dir), str(install_dir))
            runtime_path = self._find_runtime_in_tree(install_dir)
            if runtime_path is None:
                raise RuntimeError("Installed runtime directory was created, but no Godot executable was found.")
            return {"runtime_path": runtime_path.resolve(strict=False), "install_dir": install_dir.resolve(strict=False)}
        finally:
            if staging_dir.exists():
                self._safe_remove_dir(staging_dir)

    def _find_runtime_in_tree(self, root: Path) -> Optional[Path]:
        matches = self._iter_runtime_tree_candidates(root)
        return matches[0] if matches else None

    def _resolve_bundle_root(self) -> Optional[Path]:
        meipass = getattr(sys, "_MEIPASS", "")
        if not meipass:
            return None
        try:
            return Path(str(meipass)).resolve(strict=False)
        except Exception:
            return None

    def _resolve_plugin_root(self) -> Path:
        env_root = os.environ.get("REVERIE_GODOT_PLUGIN_ROOT", "").strip() or os.environ.get("REVERIE_PLUGIN_ROOT", "").strip()
        if env_root:
            return self._normalize_plugin_root(Path(env_root).expanduser().resolve(strict=False))

        if getattr(sys, "frozen", False):
            try:
                executable_dir = Path(sys.executable).resolve(strict=False).parent
                return self._normalize_plugin_root(executable_dir)
            except Exception:
                pass
        return self._normalize_plugin_root(Path(__file__).resolve().parent)

    def _normalize_plugin_root(self, root: Path) -> Path:
        candidate = Path(root).resolve(strict=False)
        if candidate.name.lower() == "dist" and (candidate.parent / "plugin.json").exists():
            return candidate.parent.resolve(strict=False)
        if candidate.name.lower() == "plugins" and candidate.parent.name.lower() == ".reverie":
            return (candidate / "godot").resolve(strict=False)
        return candidate

    def _find_bundled_runtime_archive(self) -> Optional[Path]:
        if self.bundle_root is None:
            return None
        runtime_bundle_dir = self.bundle_root / "bundled_runtime"
        if not runtime_bundle_dir.exists():
            return None
        for candidate in sorted(runtime_bundle_dir.glob("Godot*.zip"), key=lambda path: str(path).lower()):
            if candidate.is_file():
                return candidate.resolve(strict=False)
        return None

    def _infer_version_from_archive_name(self, archive_path: Path) -> str:
        stem = archive_path.name
        if stem.lower().endswith(".zip"):
            stem = stem[:-4]
        stem = stem.replace("Godot_v", "", 1)
        for suffix in ("_win64.exe", "_win64_console.exe", "_linux.x86_64", "_macos.universal", "_macos"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return self._sanitize_version_dir_name(stem or archive_path.stem)

    def _ensure_bundled_runtime_available(self) -> None:
        bundled_archive = self._find_bundled_runtime_archive()
        if bundled_archive is None:
            return

        state = self._load_state()
        installed_runtime_path = self._resolve_input_path(str(state.get("installed_runtime_path") or ""))
        if str(state.get("installed_runtime_path") or "").strip() and self._is_runtime_target(installed_runtime_path):
            return

        existing_runtime = self._find_runtime_in_tree(self.runtime_root)
        if existing_runtime is not None:
            return

        version_label = self._infer_version_from_archive_name(bundled_archive)
        install_result = self._install_archive(bundled_archive, version_label, False)
        runtime_path = install_result["runtime_path"]
        state["installed_runtime_path"] = str(runtime_path)
        state["installed_runtime_version"] = version_label
        state["last_install_asset_name"] = bundled_archive.name
        state["last_install_source"] = "bundled-archive"
        state["last_download_url"] = ""
        state["updated_at"] = self._utc_now()
        if not str(state.get("registered_runtime_path") or "").strip():
            state["registered_runtime_path"] = str(runtime_path)
        self._save_state(state)

    def _safe_remove_dir(self, target: Path) -> None:
        resolved_root = self.runtime_root.resolve(strict=False)
        resolved_target = target.resolve(strict=False)
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError as exc:
            raise RuntimeError(f"Refusing to remove directory outside runtime root: {resolved_target}") from exc
        if resolved_target.exists():
            shutil.rmtree(resolved_target)

    def _safe_remove_source_dir(self, target: Path) -> None:
        resolved_root = self.source_root.resolve(strict=False)
        resolved_target = target.resolve(strict=False)
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError as exc:
            raise RuntimeError(f"Refusing to remove directory outside source root: {resolved_target}") from exc
        if resolved_target.exists():
            shutil.rmtree(resolved_target)

    def _sanitize_version_dir_name(self, raw_value: str) -> str:
        text = str(raw_value or "").strip()
        if not text:
            return "current"
        cleaned = [char if (char.isalnum() or char in {"-", "_", "."}) else "_" for char in text]
        normalized = "".join(cleaned).strip("._-")
        return normalized or "current"

    def _resolve_input_path(self, raw_value: str) -> Path:
        path = Path(str(raw_value or "").strip()).expanduser()
        if path.is_absolute():
            return path.resolve(strict=False)
        return (Path.cwd() / path).resolve(strict=False)

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main(argv: list[str]) -> int:
    return GodotRuntimePlugin().run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
