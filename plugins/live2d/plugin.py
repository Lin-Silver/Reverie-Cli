"""Live2D/Cubism runtime plugin for Reverie CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile


PLUGIN_ID = "live2d"
PLUGIN_VERSION = "0.2.0"
LIVE2D_MCP_HINT = "https://github.com/Mitscherlich/live2d-mcp"
LIVE2D_DOCS = "https://docs.live2d.com/"
RENPY_LIVE2D_DOCS = "https://www.renpy.org/doc/html/live2d.html"
CORE_RELATIVE_PATH = "vendor/live2d/live2dcubismcore.min.js"
SDK_ZIP_NAME = "CubismSdkForWeb-5-r.5.zip"
SDK_CORE_MEMBER = "CubismSdkForWeb-5-r.5/Core/live2dcubismcore.min.js"


def _write_json(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.flush()
    return 0


def _plugin_root() -> Path:
    return Path(
        os.environ.get("REVERIE_LIVE2D_PLUGIN_ROOT")
        or os.environ.get("REVERIE_PLUGIN_ROOT")
        or Path(__file__).resolve().parent
    ).resolve()


def _runtime_dir() -> Path:
    return _plugin_root() / "runtime"


def _mcp_dir() -> Path:
    return _plugin_root() / "mcp" / "live2d-mcp"


def _resolve_path(raw_path: Any, project_root: Any = "") -> Path:
    candidate = Path(str(raw_path or "")).expanduser()
    if not candidate.is_absolute():
        root = Path(str(project_root or "")).expanduser() if str(project_root or "").strip() else Path.cwd()
        candidate = root / candidate
    return candidate.resolve(strict=False)


def _under_plugin_root(path: Path) -> bool:
    root = _plugin_root().resolve(strict=False)
    try:
        path.resolve(strict=False).relative_to(root)
        return True
    except ValueError:
        return False


def _candidate_roots(extra_root: Any = "") -> list[Path]:
    roots: list[Path] = []
    for raw in (extra_root, os.environ.get("REVERIE_APP_ROOT"), os.environ.get("REVERIE_PROJECT_ROOT"), Path.cwd()):
        text = str(raw or "").strip()
        if text:
            roots.append(Path(text).expanduser().resolve(strict=False))
    root = _plugin_root()
    roots.extend([root, *root.parents])
    unique: list[Path] = []
    seen: set[str] = set()
    for item in roots:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _find_sdk_zip(payload: dict[str, Any]) -> Path | None:
    requested = str(payload.get("sdk_zip") or "").strip()
    if requested:
        candidate = _resolve_path(requested, payload.get("project_root"))
        if candidate.exists():
            return candidate
    for root in _candidate_roots(payload.get("project_root")):
        for candidate in (
            root / SDK_ZIP_NAME,
            root / "downloads" / SDK_ZIP_NAME,
            root / "runtime" / SDK_ZIP_NAME,
        ):
            if candidate.exists():
                return candidate.resolve()
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _core_targets(payload: dict[str, Any]) -> list[Path]:
    targets = [_runtime_dir() / CORE_RELATIVE_PATH]
    project_root = str(payload.get("project_root") or "").strip()
    if project_root:
        root = Path(project_root).expanduser().resolve(strict=False)
        targets.extend(
            [
                root / "vendor/live2d/live2dcubismcore.min.js",
                root / "web/vendor/live2d/live2dcubismcore.min.js",
            ]
        )
    return targets


def _install_cubism_core(payload: dict[str, Any]) -> dict[str, Any]:
    sdk_zip = _find_sdk_zip(payload)
    if sdk_zip is None:
        return {
            "success": False,
            "output": "",
            "error": f"{SDK_ZIP_NAME} was not found. Pass sdk_zip or place it beside the Reverie workspace.",
            "data": {"docs": LIVE2D_DOCS},
        }

    installed: list[dict[str, Any]] = []
    with zipfile.ZipFile(sdk_zip) as archive:
        members = {name.replace("\\", "/"): name for name in archive.namelist()}
        member = members.get(SDK_CORE_MEMBER)
        if member is None:
            matches = [name for key, name in members.items() if key.endswith("/Core/live2dcubismcore.min.js")]
            member = matches[0] if matches else None
        if member is None:
            return {
                "success": False,
                "output": "",
                "error": f"{sdk_zip} does not contain Core/live2dcubismcore.min.js",
                "data": {"sdk_zip": str(sdk_zip)},
            }
        for target in _core_targets(payload):
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as handle:
                shutil.copyfileobj(source, handle)
            installed.append({"path": str(target), "bytes": target.stat().st_size, "sha256": _sha256(target)})

    return {
        "success": True,
        "output": "Cubism Core installed:\n" + "\n".join(f"- {item['path']}" for item in installed),
        "error": "",
        "data": {"sdk_zip": str(sdk_zip), "installed": installed},
    }


def _verify_core(payload: dict[str, Any]) -> dict[str, Any]:
    paths = _core_targets(payload)
    existing = []
    for path in paths:
        if path.exists():
            existing.append({"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)})
    ok = bool(existing)
    return {
        "success": True,
        "output": f"Cubism Core found={'yes' if ok else 'no'}\n" + "\n".join(f"- {item['path']} {item['sha256']}" for item in existing),
        "error": "",
        "data": {"found": ok, "cores": existing},
    }


def _status(payload: dict[str, Any]) -> dict[str, Any]:
    root = _plugin_root()
    sdk_zip = _find_sdk_zip(payload)
    core = _verify_core(payload)["data"]
    mcp_ready = _mcp_dir().exists()
    ready = bool(core.get("found"))
    return {
        "success": True,
        "output": f"Live2D plugin ready={'yes' if ready else 'partial'}; Cubism SDK zip={'found' if sdk_zip else 'missing'}; MCP bridge={'installed' if mcp_ready else 'missing'}",
        "error": "",
        "data": {
            "plugin_root": str(root),
            "runtime_dir": str(_runtime_dir()),
            "sdk_zip": str(sdk_zip) if sdk_zip else "",
            "cores": core.get("cores", []),
            "mcp_dir": str(_mcp_dir()),
            "mcp_installed": mcp_ready,
            "live2d_mcp_hint": LIVE2D_MCP_HINT,
            "docs": LIVE2D_DOCS,
        },
    }


def _load_model3(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "model3.json root must be an object"
    return payload, ""


def _motion_entries(file_refs: dict[str, Any]) -> list[dict[str, str]]:
    motions = file_refs.get("Motions", {})
    entries: list[dict[str, str]] = []
    if isinstance(motions, dict):
        for group, items in motions.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("File"):
                        entries.append({"group": str(group), "file": str(item.get("File"))})
    return entries


def _expression_entries(file_refs: dict[str, Any]) -> list[dict[str, str]]:
    expressions = file_refs.get("Expressions", [])
    entries: list[dict[str, str]] = []
    if isinstance(expressions, list):
        for item in expressions:
            if isinstance(item, dict):
                entries.append({"name": str(item.get("Name") or Path(str(item.get("File") or "")).stem), "file": str(item.get("File") or "")})
    return entries


def _inspect_model3_data(path: Path) -> dict[str, Any]:
    payload, error = _load_model3(path)
    if error:
        return {"model3_path": str(path), "valid_json": False, "error": error}
    file_refs = payload.get("FileReferences", {})
    if not isinstance(file_refs, dict):
        file_refs = {}
    base = path.parent
    dependencies: list[dict[str, Any]] = []

    def add_dep(kind: str, rel: Any, label: str = "") -> None:
        if not str(rel or "").strip():
            return
        dep_path = (base / str(rel)).resolve(strict=False)
        dependencies.append({"kind": kind, "label": label, "path": str(dep_path), "exists": dep_path.exists(), "relative": str(rel)})

    add_dep("moc", file_refs.get("Moc"))
    for texture in file_refs.get("Textures", []) if isinstance(file_refs.get("Textures"), list) else []:
        add_dep("texture", texture)
    for motion in _motion_entries(file_refs):
        add_dep("motion", motion["file"], motion["group"])
    for expression in _expression_entries(file_refs):
        add_dep("expression", expression["file"], expression["name"])
    add_dep("physics", file_refs.get("Physics"))
    add_dep("pose", file_refs.get("Pose"))
    missing = [item for item in dependencies if not item["exists"]]
    return {
        "model3_path": str(path),
        "valid_json": True,
        "version": payload.get("Version"),
        "moc": file_refs.get("Moc", ""),
        "texture_count": len(file_refs.get("Textures", []) if isinstance(file_refs.get("Textures"), list) else []),
        "motion_count": len(_motion_entries(file_refs)),
        "expression_count": len(_expression_entries(file_refs)),
        "has_physics": bool(file_refs.get("Physics")),
        "has_pose": bool(file_refs.get("Pose")),
        "dependencies": dependencies,
        "missing": missing,
        "motions": _motion_entries(file_refs),
        "expressions": _expression_entries(file_refs),
    }


def _inspect_model3(payload: dict[str, Any]) -> dict[str, Any]:
    model3_path = _resolve_path(payload.get("model3_path"), payload.get("project_root"))
    if not model3_path.exists():
        return {"success": False, "output": "", "error": f"model3.json not found: {model3_path}", "data": {}}
    data = _inspect_model3_data(model3_path)
    success = bool(data.get("valid_json"))
    output = [
        f"Live2D model3: {model3_path}",
        f"valid_json={'yes' if data.get('valid_json') else 'no'}",
        f"textures={data.get('texture_count', 0)} motions={data.get('motion_count', 0)} expressions={data.get('expression_count', 0)}",
        f"missing_dependencies={len(data.get('missing', []))}",
    ]
    return {"success": success, "output": "\n".join(output), "error": data.get("error", "") if not success else "", "data": data}


def _validate_model3(payload: dict[str, Any]) -> dict[str, Any]:
    result = _inspect_model3(payload)
    if not result.get("success"):
        return result
    data = result["data"]
    missing = data.get("missing", [])
    ok = not missing and bool(data.get("moc"))
    output = result["output"] + f"\nvalidation={'pass' if ok else 'fail'}"
    return {"success": ok, "output": output, "error": "" if ok else "Live2D model has missing dependencies or no Moc reference.", "data": data}


def _inspect_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    project_root = str(payload.get("project_root") or "").strip()
    manifest_path = str(payload.get("manifest_path") or "data/live2d/models.yaml").strip()
    if not project_root:
        return {"success": False, "output": "", "error": "project_root is required", "data": {}}
    target = Path(project_root).expanduser().resolve(strict=False) / manifest_path
    if not target.exists():
        return {"success": False, "output": "", "error": f"Live2D manifest not found: {target}", "data": {}}
    if target.suffix.lower() == ".json" and target.name.endswith(".model3.json"):
        return _inspect_model3({"model3_path": str(target)})
    text = target.read_text(encoding="utf-8", errors="replace")
    model_lines = [line.strip() for line in text.splitlines() if "model3.json" in line or "placeholder:" in line]
    enabled = any(line.strip().lower().startswith("enabled: true") for line in text.splitlines())
    output = [f"Live2D manifest: {target}", f"enabled={'yes' if enabled else 'no'}", f"model markers={len(model_lines)}"]
    return {
        "success": True,
        "output": "\n".join(output),
        "error": "",
        "data": {"manifest_path": str(target), "enabled": enabled, "model_markers": model_lines},
    }


def _stage_project(payload: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_path(payload.get("project_root"))
    model3_path = _resolve_path(payload.get("model3_path"), payload.get("project_root"))
    if not project_root.exists():
        return {"success": False, "output": "", "error": f"Project root not found: {project_root}", "data": {}}
    if not model3_path.exists():
        return {"success": False, "output": "", "error": f"model3.json not found: {model3_path}", "data": {}}
    model_id = str(payload.get("model_id") or model3_path.stem.replace(".model3", "")).strip() or "live2d_model"
    target_dir = project_root / "data" / "live2d" / model_id
    force = bool(payload.get("force", False))
    dry_run = bool(payload.get("dry_run", False))
    if target_dir.exists() and force and not dry_run:
        shutil.rmtree(target_dir)
    planned = {"source": str(model3_path.parent), "target": str(target_dir), "model_id": model_id, "dry_run": dry_run}
    if not dry_run:
        shutil.copytree(model3_path.parent, target_dir, dirs_exist_ok=True)
    return {
        "success": True,
        "output": ("Live2D stage dry-run" if dry_run else "Live2D model staged") + f": {model3_path.parent} -> {target_dir}",
        "error": "",
        "data": planned,
    }


def _control_plan(payload: dict[str, Any]) -> dict[str, Any]:
    model3_path = _resolve_path(payload.get("model3_path"), payload.get("project_root")) if payload.get("model3_path") else None
    model_data = _inspect_model3_data(model3_path) if model3_path and model3_path.exists() else {}
    expressions = [item.get("name", "") for item in model_data.get("expressions", [])] if model_data else []
    motion_groups = sorted({item.get("group", "") for item in model_data.get("motions", []) if item.get("group")}) if model_data else []
    dialogue_cues = payload.get("dialogue_cues", [])
    if not isinstance(dialogue_cues, list):
        dialogue_cues = []
    plan = {
        "model3_path": str(model3_path) if model3_path else "",
        "expression_aliases": expressions,
        "motion_groups": motion_groups,
        "recommended_events": [
            {"event": "dialogue_start", "action": "set_expression", "target": expressions[0] if expressions else "neutral"},
            {"event": "line_emphasis", "action": "play_motion", "target": motion_groups[0] if motion_groups else "TapBody"},
            {"event": "voice_playback", "action": "lip_sync", "target": "audio amplitude -> mouth parameter"},
            {"event": "pointer_move", "action": "look_at", "target": "cursor or focus position"},
        ],
        "dialogue_cues": dialogue_cues,
    }
    return {"success": True, "output": "Live2D control plan generated.", "error": "", "data": plan}


def _mcp_install(payload: dict[str, Any]) -> dict[str, Any]:
    source_path = str(payload.get("source_path") or "").strip()
    force = bool(payload.get("force", False))
    dry_run = bool(payload.get("dry_run", False))
    target = _mcp_dir()
    if not source_path:
        return {
            "success": False,
            "output": "",
            "error": "Provide source_path for a local live2d-mcp checkout. Automatic clone is not guessed by this plugin.",
            "data": {"repository": LIVE2D_MCP_HINT, "target": str(target)},
        }
    source = _resolve_path(source_path)
    if not source.exists():
        return {"success": False, "output": "", "error": f"Live2D MCP source not found: {source}", "data": {"repository": LIVE2D_MCP_HINT}}
    if dry_run:
        return {"success": True, "output": f"Live2D MCP install dry-run: {source} -> {target}", "error": "", "data": {"source": str(source), "target": str(target), "dry_run": True}}
    if target.exists() and force:
        if not _under_plugin_root(target):
            raise RuntimeError(f"Refusing to replace outside plugin root: {target}")
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return {"success": True, "output": f"Live2D MCP source installed: {target}", "error": "", "data": _mcp_status({})["data"]}


def _mcp_status(_payload: dict[str, Any]) -> dict[str, Any]:
    target = _mcp_dir()
    files = []
    if target.exists():
        files = [str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()][:100]
    data = {"mcp_dir": str(target), "installed": target.exists() and bool(files), "files": files, "repository": LIVE2D_MCP_HINT}
    return {"success": True, "output": f"Live2D MCP bridge installed={'yes' if data['installed'] else 'no'}", "error": "", "data": data}


def _mcp_info(_payload: dict[str, Any]) -> dict[str, Any]:
    target = _mcp_dir()
    installed = target.exists()
    package_json = target / "package.json"
    pyproject = target / "pyproject.toml"
    if package_json.exists():
        command = "node"
        args = ["server.js"]
    elif pyproject.exists():
        command = sys.executable
        args = ["-m", "live2d_mcp"]
    else:
        command = sys.executable
        args = ["-m", "live2d_mcp"]
    data = {
        "server_name": "live2d_control",
        "enabled": False,
        "type": "stdio",
        "command": command,
        "args": args,
        "cwd": str(target),
        "env": {"REVERIE_LIVE2D_RUNTIME": str(_runtime_dir())},
        "includeTools": ["get_model_info", "set_expression", "play_motion", "look_at", "lip_sync"],
        "includeModes": ["reverie-gamer"],
        "tools_list_ok": False,
        "installed": installed,
        "repository": LIVE2D_MCP_HINT,
    }
    return {"success": True, "output": "Live2D MCP integration contract returned; server stays disabled until a bridge is installed and verified.", "error": "", "data": data}


def _guidance(_payload: dict[str, Any]) -> dict[str, Any]:
    guidance = [
        "Use Live2D for reusable interactive character acting: expressions, motions, gaze, lip sync, and dialogue beat reactions.",
        "Validate .model3.json dependencies before wiring scenes: Moc, textures, motions, expressions, physics, and pose files must exist.",
        "Keep Cubism Core and model runtime files in plugin/project vendor folders; keep creative planning in Reverie-Gamer prompts.",
        "Use TTI for still CG/backgrounds and TTV for short ambient/cutscene clips; use Live2D for reusable character performance.",
    ]
    return {"success": True, "output": "\n".join(guidance), "error": "", "data": {"guidance": guidance, "docs": LIVE2D_DOCS}}


def _build_handshake() -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "plugin_id": PLUGIN_ID,
        "display_name": "Live2D Cubism Plugin",
        "version": PLUGIN_VERSION,
        "runtime_family": "interactive-character-runtime",
        "include_modes": ["reverie-gamer"],
        "description": "Cubism Core deployment, Live2D model validation, dynamic CG planning, and MCP bridge contracts for Galgame workflows.",
        "tool_call_hint": "Use rc_live2d_install_cubism_core, rc_live2d_validate_model3, rc_live2d_control_plan, and rc_live2d_mcp_info for dynamic CG work.",
        "system_prompt": (
            "For Live2D Galgame work, keep core Reverie-Gamer focused on creative direction, route planning, "
            "character performance goals, and asset contracts. Use the Live2D plugin for Cubism Core deployment, "
            "model3 dependency checks, expression/motion/lip-sync routing, and MCP-style control concepts. Do not "
            "embed Live2D authoring/control logic directly into the core Reverie CLI package."
        ),
        "mcp_servers": [
            {
                "name": "live2d_control",
                "description": "Disabled placeholder contract for plugin-local Live2D MCP control bridge.",
                "enabled": False,
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "live2d_mcp"],
                "cwd": str(_mcp_dir()),
                "env": {"REVERIE_LIVE2D_RUNTIME": str(_runtime_dir())},
                "includeTools": ["get_model_info", "set_expression", "play_motion", "look_at", "lip_sync"],
                "include_modes": ["reverie-gamer"],
            }
        ],
        "skills": [
            {
                "name": "live2d-dynamic-cg-workflow",
                "description": "Plan, validate, and wire Live2D dynamic CG assets for Galgame projects.",
                "include_modes": ["reverie-gamer"],
                "body": (
                    "Use Live2D when a Galgame needs reusable character acting instead of one-off still CG. Define "
                    "model ids, .model3.json paths, texture/motion/expression contracts, idle motion, emotion aliases, "
                    "fallback still CG, and interaction events. Use `rc_live2d_install_cubism_core` to deploy Cubism Core, "
                    "`rc_live2d_validate_model3` to verify dependencies, `rc_live2d_control_plan` to map dialogue events to "
                    "motions/expressions/lip-sync, and `rc_live2d_mcp_info` when connecting a plugin-local control bridge."
                ),
                "metadata": {"live2d_mcp_hint": LIVE2D_MCP_HINT, "docs": LIVE2D_DOCS, "renpy_live2d_docs": RENPY_LIVE2D_DOCS},
            }
        ],
        "commands": [
            {"name": "status", "description": "Inspect Live2D plugin readiness, Cubism Core availability, and MCP bridge state.", "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}, "sdk_zip": {"type": "string"}}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "install_cubism_core", "description": "Extract Core/live2dcubismcore.min.js from CubismSdkForWeb into plugin runtime and optionally a project.", "parameters": {"type": "object", "properties": {"sdk_zip": {"type": "string"}, "project_root": {"type": "string"}}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "verify_core", "description": "Verify Cubism Core copies and SHA256 hashes.", "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "inspect_manifest", "description": "Inspect a Reverie Live2D manifest or .model3.json file.", "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}, "manifest_path": {"type": "string"}}, "required": ["project_root"]}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "inspect_model3", "description": "Inspect a .model3.json for textures, motions, expressions, physics, and pose references.", "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}, "model3_path": {"type": "string"}}, "required": ["model3_path"]}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "validate_model3", "description": "Validate .model3.json dependencies exist on disk.", "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}, "model3_path": {"type": "string"}}, "required": ["model3_path"]}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "stage_project", "description": "Copy a Live2D model folder into a Reverie project data/live2d/<model_id> folder.", "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}, "model3_path": {"type": "string"}, "model_id": {"type": "string"}, "force": {"type": "boolean"}, "dry_run": {"type": "boolean"}}, "required": ["project_root", "model3_path"]}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "control_plan", "description": "Generate an expression/motion/lip-sync control plan from a model3 file and dialogue cues.", "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}, "model3_path": {"type": "string"}, "dialogue_cues": {"type": "array"}}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "mcp_install", "description": "Install a local live2d-mcp checkout into the plugin mcp folder.", "parameters": {"type": "object", "properties": {"source_path": {"type": "string"}, "force": {"type": "boolean"}, "dry_run": {"type": "boolean"}}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "mcp_status", "description": "Inspect plugin-local Live2D MCP bridge files.", "parameters": {"type": "object", "properties": {}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "mcp_info", "description": "Return the Live2D MCP bridge contract for MCP registration.", "parameters": {"type": "object", "properties": {}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
            {"name": "guidance", "description": "Return Live2D dynamic CG planning guidance.", "parameters": {"type": "object", "properties": {}, "required": []}, "expose_as_tool": True, "include_modes": ["reverie-gamer"]},
        ],
    }


_COMMANDS = {
    "status": _status,
    "install_cubism_core": _install_cubism_core,
    "verify_core": _verify_core,
    "inspect_manifest": _inspect_manifest,
    "inspect_model3": _inspect_model3,
    "validate_model3": _validate_model3,
    "stage_project": _stage_project,
    "control_plan": _control_plan,
    "mcp_install": _mcp_install,
    "mcp_status": _mcp_status,
    "mcp_info": _mcp_info,
    "guidance": _guidance,
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
