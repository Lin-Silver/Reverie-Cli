"""Blender SDK/runtime plugin for Reverie CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import shutil
import subprocess
import sys
import zipfile


PLUGIN_VERSION = "0.2.0"
ARCHIVE_NAME = "blender-5.1.1-windows-x64.zip"


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
                "execution, and scene metadata inspection."
            ),
            "tool_call_hint": (
                "Use rc_blender_ensure_runtime to deploy the embedded portable Blender "
                "environment, then rc_blender_run_script for background asset authoring. "
                "Use blender_modeling_workbench to generate production Blender scripts "
                "and this plugin to provide the actual Blender executable."
            ),
            "system_prompt": (
                "This plugin owns the local portable Blender environment. It can unpack the "
                "Blender archive embedded in the plugin executable into the plugin runtime "
                "folder, report readiness, launch Blender, and run generated bpy scripts. "
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
                            }
                        },
                        "required": ["script_path"]
                    },
                    "expose_as_tool": True,
                    "include_modes": []
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
                },
            )

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

        return self._fail(f"Unknown command: {command_name}", {})

    def _resolve_plugin_root(self) -> Path:
        env_root = os.environ.get("REVERIE_BLENDER_PLUGIN_ROOT", "").strip()
        if env_root:
            return Path(env_root).expanduser().resolve(strict=False)

        if getattr(sys, "frozen", False):
            executable_dir = Path(sys.executable).resolve(strict=False).parent
            if executable_dir.name.lower() == "dist":
                return executable_dir.parent
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

    def _ensure_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        force = bool(payload.get("force", False))
        current = self._detect_runtime(payload.get("blender_executable"))
        if current["available"] and not force:
            return self._ok(
                "Portable Blender runtime is already available.",
                {
                    "deployed": False,
                    "reason": "runtime already exists",
                    "detected": current,
                    "archive": self._archive_status(),
                    "runtime_root": str(self.runtime_root),
                },
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
        deploy_result = self._ensure_runtime({"force": False})
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
        blend_path = self._resolve_existing_path(payload.get("blend_path"))
        if blend_path is not None:
            command.append(str(blend_path))
        try:
            process = subprocess.Popen(command, cwd=str(Path(detection["path"]).parent), shell=False)
        except Exception as exc:
            return self._fail(str(exc), {"command": command})
        return self._ok(
            "Blender launched.",
            {"command": command, "pid": int(process.pid), "detected": detection, "deployment": deploy_result},
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
        }
        if completed.returncode == 0:
            return self._ok("Blender script completed.", data)
        return self._fail("Blender script failed.", data)

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
