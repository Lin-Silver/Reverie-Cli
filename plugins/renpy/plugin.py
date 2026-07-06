"""Ren'Py runtime plugin for Reverie CLI.

This optional plugin only manages an external Ren'Py SDK for native lint,
compile, and distribution. Reverie Engine owns project inspection, outlining,
validation, and migration directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile


PLUGIN_ID = "renpy"
PLUGIN_VERSION = "0.2.0"
RENPY_REPOSITORY = "https://github.com/renpy/renpy"
RENPY_CLI_DOCS = "https://www.renpy.org/doc/html/cli.html"
RENPY_LIVE2D_DOCS = "https://www.renpy.org/doc/html/live2d.html"

_LABEL_RE = re.compile(r"^\s*label\s+([A-Za-z0-9_\.]+)\s*:")
_DEFINE_CHARACTER_RE = re.compile(r"^\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*Character\((.+)\)\s*")
_IMAGE_RE = re.compile(r"^\s*image\s+(.+?)\s*=")
_SCREEN_RE = re.compile(r"^\s*screen\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_MENU_RE = re.compile(r"^\s*menu\s*:")
_JUMP_RE = re.compile(r"^\s*(jump|call)\s+([A-Za-z0-9_\.]+)\s*")


def _write_json(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    return 0


def _plugin_root() -> Path:
    return Path(
        os.environ.get("REVERIE_RENPY_PLUGIN_ROOT")
        or os.environ.get("REVERIE_PLUGIN_ROOT")
        or Path(__file__).resolve().parent
    ).resolve()


def _runtime_dir() -> Path:
    return _plugin_root() / "runtime"


def _source_dir() -> Path:
    return _plugin_root() / "source"


def _resolve_input_path(raw_path: Any, project_root: Any = "") -> Path:
    candidate = Path(str(raw_path or "")).expanduser()
    if not candidate.is_absolute():
        root = Path(str(project_root or "")).expanduser() if str(project_root or "").strip() else Path.cwd()
        candidate = root / candidate
    return candidate.resolve(strict=False)


def _relative_or_self(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _under_plugin_root(path: Path) -> bool:
    root = _plugin_root().resolve(strict=False)
    try:
        path.resolve(strict=False).relative_to(root)
        return True
    except ValueError:
        return False


def _quoted_name(fragment: str) -> str:
    match = re.search(r'["\']([^"\']+)["\']', str(fragment or ""))
    return match.group(1) if match else ""


def _copytree_contents(source: Path, target: Path, *, force: bool = False) -> None:
    if not source.exists():
        raise FileNotFoundError(str(source))
    if not _under_plugin_root(target):
        raise RuntimeError(f"Refusing to write outside plugin root: {target}")
    if target.exists() and force:
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            if destination.exists() and force:
                shutil.rmtree(destination)
            shutil.copytree(child, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, destination)


def _renpy_entry_candidates(root: Path | None = None) -> list[Path]:
    base = Path(root or _runtime_dir())
    patterns = [
        "renpy.exe",
        "renpy.sh",
        "renpy.py",
        "renpy/renpy.py",
        "**/renpy.exe",
        "**/renpy.sh",
        "**/renpy.py",
    ]
    found: list[Path] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in base.glob(pattern):
            if not path.is_file():
                continue
            key = str(path.resolve(strict=False)).lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(path.resolve(strict=False))
    return found


def _select_renpy_entry(payload: dict[str, Any] | None = None) -> Path | None:
    payload = payload or {}
    requested = str(payload.get("renpy_executable") or payload.get("runtime_entry") or "").strip()
    if requested:
        path = Path(requested).expanduser()
        if not path.is_absolute():
            path = _runtime_dir() / path
        if path.exists():
            return path.resolve(strict=False)
    candidates = _renpy_entry_candidates()
    return candidates[0] if candidates else None


def _renpy_command(entry: Path, project_root: Path, action: str, extra_args: list[str] | None = None) -> list[str]:
    suffix = entry.suffix.lower()
    if suffix == ".py":
        command = [sys.executable, str(entry), str(project_root), action]
    else:
        command = [str(entry), str(project_root), action]
    command.extend(extra_args or [])
    return command


def _run_command(command: list[str], cwd: Path, timeout_seconds: int = 300) -> dict[str, Any]:
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1, int(timeout_seconds or 300)),
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "duration_seconds": round(time.time() - started, 3),
    }


def _runtime_summary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    runtime = _runtime_dir()
    source = _source_dir()
    entries = _renpy_entry_candidates(runtime)
    selected = _select_renpy_entry(payload)
    archives = [str(path) for path in sorted(runtime.glob("*.zip"))]
    return {
        "plugin_root": str(_plugin_root()),
        "runtime_dir": str(runtime),
        "source_dir": str(source),
        "runtime_present": runtime.exists(),
        "entry_candidates": [str(path) for path in entries[:20]],
        "selected_entry": str(selected) if selected else "",
        "archives": archives,
        "repository": RENPY_REPOSITORY,
        "cli_docs": RENPY_CLI_DOCS,
        "live2d_docs": RENPY_LIVE2D_DOCS,
    }


def _status(payload: dict[str, Any]) -> dict[str, Any]:
    data = _runtime_summary(payload)
    ready = bool(data.get("selected_entry"))
    output = [
        f"Ren'Py plugin ready={'yes' if ready else 'partial'}",
        f"runtime: {data['runtime_dir']}",
        f"entry: {data.get('selected_entry') or '(not installed)'}",
        f"source: {RENPY_REPOSITORY}",
    ]
    return {"success": True, "output": "\n".join(output), "error": "", "data": data}


def _runtime_install(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = _runtime_dir()
    source = _source_dir()
    force = bool(payload.get("force", False))
    dry_run = bool(payload.get("dry_run", False))
    source_path = str(payload.get("source_path") or "").strip()
    archive_path = str(payload.get("archive_path") or payload.get("zip_path") or "").strip()
    planned: list[str] = []

    if source_path:
        src = _resolve_input_path(source_path)
        target = source / src.name
        planned.append(f"copy {src} -> {target}")
        if not dry_run:
            _copytree_contents(src, target, force=force)
    elif archive_path:
        archive = _resolve_input_path(archive_path)
        if not archive.exists():
            return {"success": False, "output": "", "error": f"Archive not found: {archive}", "data": {}}
        target = runtime
        planned.append(f"extract {archive} -> {target}")
        if not dry_run:
            if target.exists() and force:
                if not _under_plugin_root(target):
                    raise RuntimeError(f"Refusing to replace outside plugin root: {target}")
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(target)
    else:
        return {
            "success": False,
            "output": "",
            "error": "Provide source_path or archive_path. Automatic upstream downloads are intentionally not guessed.",
            "data": {"repository": RENPY_REPOSITORY, "runtime_dir": str(runtime), "source_dir": str(source)},
        }

    data = _runtime_summary(payload)
    data["planned"] = planned
    data["dry_run"] = dry_run
    return {
        "success": True,
        "output": ("Ren'Py runtime install dry-run:\n" if dry_run else "Ren'Py runtime install completed:\n") + "\n".join(planned),
        "error": "",
        "data": data,
    }


def _list_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    data = _runtime_summary(payload)
    output = [
        "Ren'Py runtime entries:",
        *(f"- {entry}" for entry in data.get("entry_candidates", [])),
    ]
    if not data.get("entry_candidates"):
        output.append("- (none found; install a runtime archive or source checkout first)")
    return {"success": True, "output": "\n".join(output), "error": "", "data": data}


def _guidance(_payload: dict[str, Any]) -> dict[str, Any]:
    guidance = [
        "Keep Reverie-Gamer focused on route quality, scenario intent, asset contracts, and verification evidence.",
        "Use this plugin for Ren'Py labels, menus, screens, transforms, lint, compile, and distribution workflows.",
        "Use Ren'Py CLI actions from the plugin runtime when installed: lint before packaging, compile before distribution, and keep output under plugin/project folders.",
        "For dynamic CG, Ren'Py can coordinate Live2D motions and expressions, but Cubism Core/model validation belongs to the Live2D plugin.",
    ]
    return {
        "success": True,
        "output": "\n".join(guidance),
        "error": "",
        "data": {"guidance": guidance, "repository": RENPY_REPOSITORY, "cli_docs": RENPY_CLI_DOCS},
    }


def _script_outline(payload: dict[str, Any]) -> dict[str, Any]:
    script_path = _resolve_input_path(payload.get("script_path"), payload.get("project_root"))
    if not script_path.exists() or not script_path.is_file():
        return {"success": False, "output": "", "error": f"Ren'Py script not found: {script_path}", "data": {}}

    labels: list[dict[str, Any]] = []
    characters: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    screens: list[dict[str, Any]] = []
    menus: list[dict[str, Any]] = []
    jumps: list[dict[str, Any]] = []
    warnings: list[str] = []

    for line_number, raw_line in enumerate(script_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if match := _LABEL_RE.match(raw_line):
            labels.append({"name": match.group(1), "line": line_number})
        if match := _DEFINE_CHARACTER_RE.match(raw_line):
            characters.append({"alias": match.group(1), "name": _quoted_name(match.group(2)), "line": line_number})
        if match := _IMAGE_RE.match(raw_line):
            images.append({"name": match.group(1).strip(), "line": line_number})
        if match := _SCREEN_RE.match(raw_line):
            screens.append({"name": match.group(1), "line": line_number})
        if _MENU_RE.match(raw_line):
            menus.append({"line": line_number})
        if match := _JUMP_RE.match(raw_line):
            jumps.append({"kind": match.group(1), "target": match.group(2), "line": line_number})
        stripped = raw_line.strip()
        if stripped.startswith("python:") or stripped.startswith("init python:"):
            warnings.append(f"line {line_number}: embedded Python block needs Ren'Py lint/runtime review")
        if "Live2D(" in raw_line or "live2d" in raw_line.lower():
            warnings.append(f"line {line_number}: Live2D usage should be checked against Ren'Py Live2D docs and Cubism SDK availability")

    output = [
        f"Ren'Py outline: {script_path}",
        f"labels={len(labels)} characters={len(characters)} images={len(images)} screens={len(screens)} menus={len(menus)} jumps={len(jumps)}",
    ]
    if labels:
        output.append("labels: " + ", ".join(item["name"] for item in labels[:20]))
    return {
        "success": True,
        "output": "\n".join(output),
        "error": "",
        "data": {
            "script_path": str(script_path),
            "labels": labels,
            "characters": characters,
            "images": images,
            "screens": screens,
            "menus": menus,
            "jumps": jumps,
            "warnings": warnings,
        },
    }


def _project_inspect(payload: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_input_path(payload.get("project_root") or payload.get("project_dir"))
    if not project_root.exists():
        return {"success": False, "output": "", "error": f"Project root not found: {project_root}", "data": {}}
    game_dir = project_root / "game" if (project_root / "game").is_dir() else project_root
    scripts = sorted(game_dir.glob("**/*.rpy"))
    images = [path for path in game_dir.glob("**/*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".avif"}]
    audio = [path for path in game_dir.glob("**/*") if path.suffix.lower() in {".ogg", ".mp3", ".wav", ".flac"}]
    live2d_refs = []
    for script in scripts[:200]:
        text = script.read_text(encoding="utf-8", errors="replace")
        if "Live2D(" in text or "live2d" in text.lower():
            live2d_refs.append(str(script))
    data = {
        "project_root": str(project_root),
        "game_dir": str(game_dir),
        "script_count": len(scripts),
        "image_count": len(images),
        "audio_count": len(audio),
        "has_options": (game_dir / "options.rpy").exists(),
        "has_script": (game_dir / "script.rpy").exists(),
        "live2d_script_refs": live2d_refs,
        "scripts": [_relative_or_self(path, project_root) for path in scripts[:100]],
    }
    output = [
        f"Ren'Py project: {project_root}",
        f"scripts={data['script_count']} images={data['image_count']} audio={data['audio_count']}",
        f"options.rpy={'yes' if data['has_options'] else 'no'} script.rpy={'yes' if data['has_script'] else 'no'}",
        f"Live2D refs={len(live2d_refs)}",
    ]
    return {"success": True, "output": "\n".join(output), "error": "", "data": data}


def _renpy_action(payload: dict[str, Any], action: str) -> dict[str, Any]:
    project_root = _resolve_input_path(payload.get("project_root") or payload.get("project_dir"))
    if not project_root.exists():
        return {"success": False, "output": "", "error": f"Project root not found: {project_root}", "data": {}}
    entry = _select_renpy_entry(payload)
    if entry is None:
        return {
            "success": False,
            "output": "",
            "error": "No Ren'Py runtime entry found. Run runtime_install with a local archive/source first.",
            "data": _runtime_summary(payload),
        }
    timeout = int(payload.get("timeout_seconds") or 300)
    extra_args = [str(item) for item in payload.get("extra_args", [])] if isinstance(payload.get("extra_args"), list) else []
    if action == "distribute":
        package = str(payload.get("package") or "").strip()
        if package:
            extra_args.extend(["--package", package])
    command = _renpy_command(entry, project_root, action, extra_args)
    dry_run = bool(payload.get("dry_run", False))
    if dry_run:
        return {
            "success": True,
            "output": f"Ren'Py {action} dry-run:\n" + " ".join(command),
            "error": "",
            "data": {"command": command, "cwd": str(_runtime_dir()), "dry_run": True, "action": action},
        }
    try:
        result = _run_command(command, _runtime_dir(), timeout_seconds=timeout)
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": f"Ren'Py {action} timed out after {timeout}s", "data": {"command": command}}
    success = result["returncode"] == 0
    output = f"Ren'Py {action} {'completed' if success else 'failed'} (exit {result['returncode']})"
    if result.get("stdout"):
        output += "\n\nSTDOUT\n" + result["stdout"]
    if result.get("stderr"):
        output += "\n\nSTDERR\n" + result["stderr"]
    return {"success": success, "output": output, "error": "" if success else f"Ren'Py {action} failed.", "data": result}


def _lint(payload: dict[str, Any]) -> dict[str, Any]:
    return _renpy_action(payload, "lint")


def _compile(payload: dict[str, Any]) -> dict[str, Any]:
    return _renpy_action(payload, "compile")


def _distribute(payload: dict[str, Any]) -> dict[str, Any]:
    return _renpy_action(payload, "distribute")


def _command_schema_project() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "description": "Ren'Py project root."},
            "project_dir": {"type": "string", "description": "Alias of project_root."},
            "renpy_executable": {"type": "string", "description": "Optional Ren'Py executable or renpy.py path."},
            "dry_run": {"type": "boolean", "description": "Show the command without running it."},
            "timeout_seconds": {"type": "integer", "description": "Execution timeout."},
            "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra CLI args appended after the action."},
        },
        "required": ["project_root"],
    }


def _build_handshake() -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "plugin_id": PLUGIN_ID,
        "display_name": "Ren'Py Engine Plugin",
        "version": PLUGIN_VERSION,
        "runtime_family": "visual-novel-engine",
        "include_modes": ["reverie-gamer"],
        "description": "Optional Ren'Py SDK management and native lint/compile/distribute support for migrated Galgame projects.",
        "tool_call_hint": "Use reverie_engine for project inspection, outlining, parser validation, and migration; use rc_renpy_lint/compile/distribute only when native Ren'Py SDK verification is required.",
        "system_prompt": (
            "Reverie Engine owns .rpy inspection, labels, menus, conversion, and migration. Use this plugin only "
            "for an optional external Ren'Py SDK and native lint, compile, or distribution checks."
        ),
        "skills": [
            {
                "name": "renpy-galgame-workflow",
                "description": "Author, verify, and package Ren'Py Galgame projects through a plugin-owned workflow.",
                "include_modes": ["reverie-gamer"],
                "body": (
                    "Start by using `reverie_engine` to outline routes, labels, character aliases, CG/background requirements, "
                    "Live2D/static sprite needs, audio cues, persistent variables, and save data. When a plugin-local runtime is "
                    "installed, run `rc_renpy_lint` before claiming script correctness, `rc_renpy_compile` before packaging, and "
                    "`rc_renpy_distribute` for release builds. Coordinate Live2D model checks through the Live2D plugin."
                ),
                "metadata": {"repository": RENPY_REPOSITORY, "cli_docs": RENPY_CLI_DOCS, "live2d_docs": RENPY_LIVE2D_DOCS},
            }
        ],
        "commands": [
            {"name": "status", "description": "Inspect Ren'Py plugin readiness and runtime entry detection.", "parameters": {"type": "object", "properties": {}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {
                "name": "runtime_install",
                "description": "Install a local Ren'Py runtime archive or source checkout into the plugin runtime/source folder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_path": {"type": "string", "description": "Local Ren'Py source/runtime directory to copy."},
                        "archive_path": {"type": "string", "description": "Local Ren'Py runtime zip archive to extract."},
                        "force": {"type": "boolean", "description": "Replace existing plugin-local runtime/source target."},
                        "dry_run": {"type": "boolean", "description": "Report planned copy/extract work without changing files."},
                    },
                    "required": [],
                },
                "expose_as_tool": True,
                "include_modes": ["reverie-gamer"],
            },
            {"name": "list_runtime", "description": "List plugin-local Ren'Py runtime entries and source hints.", "parameters": {"type": "object", "properties": {}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "guidance", "description": "Return Ren'Py-specific production guidance for Galgame work.", "parameters": {"type": "object", "properties": {}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "lint", "description": "Run or dry-run Ren'Py lint for a project using the plugin-local runtime.", "parameters": _command_schema_project(), "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "compile", "description": "Run or dry-run Ren'Py compile for a project using the plugin-local runtime.", "parameters": _command_schema_project(), "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {
                "name": "distribute",
                "description": "Run or dry-run Ren'Py distribute for a project using the plugin-local runtime.",
                "parameters": {**_command_schema_project(), "properties": {**_command_schema_project()["properties"], "package": {"type": "string", "description": "Optional Ren'Py package target."}}},
                "expose_as_tool": True,
                "include_modes": ["reverie-gamer"],
            },
        ],
    }


_COMMANDS = {
    "status": _status,
    "runtime_install": _runtime_install,
    "list_runtime": _list_runtime,
    "guidance": _guidance,
    "lint": _lint,
    "compile": _compile,
    "distribute": _distribute,
}


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "-RC":
        return _write_json(_build_handshake())
    if len(argv) >= 2 and argv[1] == "-RC-CALL":
        if len(argv) < 4:
            return _write_json({"success": False, "output": "", "error": "Usage: -RC-CALL <command> <json-payload>", "data": {}})
        command_name = str(argv[2] or "").strip().lower()
        try:
            payload = json.loads(argv[3]) if str(argv[3] or "").strip() else {}
        except Exception as exc:
            return _write_json({"success": False, "output": "", "error": f"Invalid JSON payload: {exc}", "data": {}})
        handler = _COMMANDS.get(command_name)
        if handler is None:
            return _write_json({"success": False, "output": "", "error": f"Unknown command: {command_name}", "data": {}})
        try:
            result = handler(payload)
        except Exception as exc:
            result = {"success": False, "output": "", "error": str(exc), "data": {}}
        return _write_json(result)
    sys.stderr.write("This runtime plugin supports only -RC and -RC-CALL.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
