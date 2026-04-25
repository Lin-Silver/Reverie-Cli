"""Modeling pipeline helpers for Reverie Engine projects."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import json
import os
import shutil
import urllib.error
import urllib.request

import yaml


ASHFOX_DEFAULT_ENDPOINT = "http://127.0.0.1:8787/mcp"
ASHFOX_MCP_SERVER_NAME = "ashfox"
SOURCE_MODEL_EXTENSIONS = (".bbmodel", ".blend", ".fbx", ".dae", ".obj", ".gltf", ".glb")
RUNTIME_MODEL_EXTENSIONS = (".glb", ".gltf", ".fbx", ".obj", ".dae")
PREVIEW_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
PREFERRED_RUNTIME_EXTENSIONS = (".glb", ".gltf", ".fbx", ".obj", ".dae")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_text(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _relative_to(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or ""))
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "model"


def _preferred_primary(paths: Iterable[Path], preference: Iterable[str]) -> Optional[Path]:
    candidates = list(paths)
    if not candidates:
        return None
    order = {suffix.lower(): index for index, suffix in enumerate(preference)}
    return min(candidates, key=lambda item: (order.get(item.suffix.lower(), 999), item.name.lower()))


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    results: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(path)
    return results


def _blockbench_install_candidates() -> list[Path]:
    candidates: list[Path] = []

    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        program_files = os.environ.get("ProgramFiles", "").strip()
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "").strip()
        if local_appdata:
            candidates.append(Path(local_appdata) / "Programs" / "Blockbench" / "Blockbench.exe")
        if program_files:
            candidates.append(Path(program_files) / "Blockbench" / "Blockbench.exe")
        if program_files_x86:
            candidates.append(Path(program_files_x86) / "Blockbench" / "Blockbench.exe")
    elif os.name == "posix":
        candidates.extend(
            [
                Path("/Applications/Blockbench.app/Contents/MacOS/Blockbench"),
                Path("/usr/bin/blockbench"),
                Path("/usr/local/bin/blockbench"),
                Path("/opt/Blockbench/blockbench"),
            ]
        )

    return _unique_paths(candidates)


def _detect_blockbench_installation() -> Dict[str, Any]:
    candidates = _blockbench_install_candidates()
    executable = next((candidate.resolve() for candidate in candidates if candidate.exists()), None)
    return {
        "installed": executable is not None,
        "available": executable is not None,
        "executable_path": str(executable) if executable else "",
        "candidates": [str(path) for path in candidates],
        "manual_dependency": True,
        "install_hint": "Install Blockbench desktop and keep the Ashfox plugin enabled for Reverie-Gamer modeling workflows.",
    }


def _probe_ashfox_endpoint(endpoint: str, *, timeout_seconds: float = 1.5) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content_type = str(response.headers.get("Content-Type", "") or "").lower()
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        return {
            "available": False,
            "reachable": False,
            "endpoint": endpoint,
            "tool_count": 0,
            "session_id": "",
            "content_type": "",
            "error": f"HTTP {exc.code}: {details[:200]}".strip(),
        }
    except urllib.error.URLError as exc:
        return {
            "available": False,
            "reachable": False,
            "endpoint": endpoint,
            "tool_count": 0,
            "session_id": "",
            "content_type": "",
            "error": str(exc.reason),
        }
    except Exception as exc:
        return {
            "available": False,
            "reachable": False,
            "endpoint": endpoint,
            "tool_count": 0,
            "session_id": "",
            "content_type": "",
            "error": str(exc),
        }

    tool_count = 0
    try:
        response_payload = json.loads(body)
        if isinstance(response_payload, dict):
            result = response_payload.get("result", {})
            if isinstance(result, dict):
                tools = result.get("tools", [])
                if isinstance(tools, list):
                    tool_count = len(tools)
    except Exception:
        # Some MCP servers can stream event payloads; discovery will still happen
        # through the built-in MCP runtime once the endpoint is reachable.
        pass

    return {
        "available": True,
        "reachable": True,
        "endpoint": endpoint,
        "tool_count": tool_count,
        "session_id": headers.get("mcp-session-id", ""),
        "content_type": content_type,
        "error": "",
    }


def project_modeling_paths(project_root: str | Path) -> Dict[str, Path]:
    root = Path(project_root).resolve()
    return {
        "project_root": root,
        "assets_models": root / "assets/models",
        "source_models": root / "assets/models/source",
        "runtime_models": root / "assets/models/runtime",
        "preview_renders": root / "playtest/renders/models",
        "data_models": root / "data/models",
        "pipeline_manifest": root / "data/models/pipeline.yaml",
        "model_registry": root / "data/models/model_registry.yaml",
        "modeling_docs": root / "docs/reverie_modeling_pipeline.md",
    }


def detect_modeling_stack(project_root: str | Path) -> Dict[str, Any]:
    blockbench = _detect_blockbench_installation()
    ashfox = _probe_ashfox_endpoint(ASHFOX_DEFAULT_ENDPOINT)
    blockbench_available = bool(blockbench["installed"] or ashfox["reachable"])

    return {
        "mode": "reverie-gamer",
        "integration": "built_in_headless_modeling_with_optional_ashfox_mcp",
        "headless_blockbench": {
            "available": True,
            "can_validate": True,
            "can_export_simple_cuboids": True,
            "formats": [".bbmodel", ".gltf"],
            "notes": "Reverie can validate simple `.bbmodel` files and export cuboid elements to glTF without launching Blockbench.",
        },
        "blockbench": {
            **blockbench,
            "available": blockbench_available,
        },
        "ashfox": {
            "available": bool(ashfox["reachable"]),
            "reachable": bool(ashfox["reachable"]),
            "endpoint": ASHFOX_DEFAULT_ENDPOINT,
            "server_name": ASHFOX_MCP_SERVER_NAME,
            "tool_count": int(ashfox.get("tool_count", 0)),
            "session_id": str(ashfox.get("session_id", "") or ""),
            "error": str(ashfox.get("error", "") or ""),
            "manual_dependency": True,
            "install_hint": "Install the Ashfox plugin inside Blockbench, launch Blockbench, and keep the local MCP endpoint running for live editor automation; headless `.bbmodel` validation/export remains available without it.",
        },
    }


def build_model_pipeline_manifest(project_root: str | Path) -> Dict[str, Any]:
    paths = project_modeling_paths(project_root)
    root = paths["project_root"]
    stack = detect_modeling_stack(root)
    return {
        "version": 1,
        "generated_at": _utc_now(),
        "mode": "reverie-gamer",
        "enabled": True,
        "workspace": {
            "source_models": _relative_to(root, paths["source_models"]),
            "runtime_models": _relative_to(root, paths["runtime_models"]),
            "preview_renders": _relative_to(root, paths["preview_renders"]),
            "registry_path": _relative_to(root, paths["model_registry"]),
        },
        "workflow": {
            "source_of_truth": _relative_to(root, paths["source_models"]),
            "preferred_editor": "Blender",
            "secondary_editor": "Blockbench",
            "automation": "Built-in Blender background scripts",
            "automation_mcp": "Ashfox MCP for Blockbench sessions",
            "ashfox_server_name": ASHFOX_MCP_SERVER_NAME,
            "ashfox_endpoint": ASHFOX_DEFAULT_ENDPOINT,
            "preferred_runtime_formats": list(PREFERRED_RUNTIME_EXTENSIONS),
            "source_extensions": list(SOURCE_MODEL_EXTENSIONS),
            "runtime_extensions": list(RUNTIME_MODEL_EXTENSIONS),
        },
        "stack": stack,
        "notes": [
            "Reverie ships the modeling workflow directly in Reverie-Gamer instead of depending on checked-out Blender, Blockbench, or Ashfox source trees.",
            "Blender authoring runs through built-in workspace-local Python scripts and does not require an external MCP server.",
            "Blockbench desktop and the Ashfox plugin remain optional external installs for live Blockbench authoring and MCP automation; simple `.bbmodel` validation/export has a built-in headless fallback.",
            "When the Ashfox endpoint is reachable, Reverie-Gamer exposes its discovered MCP tools directly in `/tools`.",
            "Use assets/models/source for authoring files and assets/models/runtime for engine-facing imports.",
        ],
    }


def build_blockbench_model_stub(name: str, *, model_format: str = "free") -> Dict[str, Any]:
    model_name = str(name or "New Model").strip() or "New Model"
    return {
        "meta": {
            "format_version": "5.0",
            "model_format": model_format,
            "box_uv": True,
        },
        "name": model_name,
        "resolution": {
            "width": 16,
            "height": 16,
        },
        "elements": [],
        "outliner": [],
        "textures": [],
        "animations": [],
    }


def create_model_stub(
    project_root: str | Path,
    model_name: str,
    *,
    relative_path: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    paths = project_modeling_paths(project_root)
    target = (
        paths["source_models"] / f"{_slugify(model_name)}.bbmodel"
        if relative_path is None
        else paths["project_root"] / Path(relative_path)
    )
    target = target.resolve()
    if target.exists() and not overwrite:
        raise FileExistsError(f"Model stub already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_blockbench_model_stub(model_name)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def _scan_files(root: Path, suffixes: Iterable[str]) -> list[Path]:
    suffix_set = {str(item).lower() for item in suffixes}
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffix_set)


def _summarize_bbmodel(path: Path) -> Dict[str, Any]:
    payload = _read_json(path)
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    resolution = payload.get("resolution", {}) if isinstance(payload.get("resolution"), dict) else {}
    return {
        "format_version": meta.get("format_version"),
        "model_format": meta.get("model_format"),
        "box_uv": bool(meta.get("box_uv", False)),
        "element_count": len(payload.get("elements") or []),
        "outliner_count": len(payload.get("outliner") or []),
        "texture_count": len(payload.get("textures") or []),
        "animation_count": len(payload.get("animations") or []),
        "resolution": {
            "width": resolution.get("width"),
            "height": resolution.get("height"),
        },
    }


def _summarize_gltf(path: Path) -> Dict[str, Any]:
    payload = _read_json(path)
    asset = payload.get("asset", {}) if isinstance(payload.get("asset"), dict) else {}
    return {
        "asset_version": asset.get("version"),
        "generator": asset.get("generator"),
        "scene_count": len(payload.get("scenes") or []),
        "node_count": len(payload.get("nodes") or []),
        "mesh_count": len(payload.get("meshes") or []),
        "material_count": len(payload.get("materials") or []),
        "image_count": len(payload.get("images") or []),
        "animation_count": len(payload.get("animations") or []),
    }


def _summarize_glb(path: Path) -> Dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(12)
    if len(header) < 12:
        return {"binary": True, "valid_header": False}
    magic = header[:4]
    version = int.from_bytes(header[4:8], byteorder="little", signed=False)
    length = int.from_bytes(header[8:12], byteorder="little", signed=False)
    return {
        "binary": True,
        "valid_header": magic == b"glTF",
        "version": version,
        "declared_length": length,
    }


def _summarize_obj(path: Path) -> Dict[str, Any]:
    counts = {"vertices": 0, "uvs": 0, "normals": 0, "faces": 0, "objects": 0, "groups": 0}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith("v "):
                counts["vertices"] += 1
            elif stripped.startswith("vt "):
                counts["uvs"] += 1
            elif stripped.startswith("vn "):
                counts["normals"] += 1
            elif stripped.startswith("f "):
                counts["faces"] += 1
            elif stripped.startswith("o "):
                counts["objects"] += 1
            elif stripped.startswith("g "):
                counts["groups"] += 1
    except Exception:
        return {"parse_error": True}
    return counts


def summarize_model_file(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".bbmodel":
        return _summarize_bbmodel(path)
    if suffix == ".gltf":
        return _summarize_gltf(path)
    if suffix == ".glb":
        return _summarize_glb(path)
    if suffix == ".obj":
        return _summarize_obj(path)
    return {}


def build_model_registry(project_root: str | Path) -> Dict[str, Any]:
    paths = project_modeling_paths(project_root)
    root = paths["project_root"]
    source_files = _scan_files(paths["source_models"], SOURCE_MODEL_EXTENSIONS)
    runtime_files = _scan_files(paths["runtime_models"], RUNTIME_MODEL_EXTENSIONS)
    preview_files = _scan_files(paths["preview_renders"], PREVIEW_EXTENSIONS)
    buckets: Dict[str, Dict[str, list[Path]]] = {}

    for path in source_files:
        buckets.setdefault(path.stem, {"source": [], "runtime": [], "preview": []})["source"].append(path)
    for path in runtime_files:
        buckets.setdefault(path.stem, {"source": [], "runtime": [], "preview": []})["runtime"].append(path)
    for path in preview_files:
        buckets.setdefault(path.stem, {"source": [], "runtime": [], "preview": []})["preview"].append(path)

    models: list[Dict[str, Any]] = []
    for stem in sorted(buckets.keys()):
        groups = buckets[stem]
        primary_source = _preferred_primary(groups["source"], [".bbmodel", ".blend", ".fbx", ".dae", ".obj", ".gltf", ".glb"])
        primary_runtime = _preferred_primary(groups["runtime"], PREFERRED_RUNTIME_EXTENSIONS)
        primary_preview = _preferred_primary(groups["preview"], PREVIEW_EXTENSIONS)
        models.append(
            {
                "id": _slugify(stem),
                "name": stem,
                "primary_source": _relative_to(root, primary_source) if primary_source else "",
                "primary_runtime": _relative_to(root, primary_runtime) if primary_runtime else "",
                "primary_preview": _relative_to(root, primary_preview) if primary_preview else "",
                "source_files": [_relative_to(root, item) for item in groups["source"]],
                "runtime_files": [_relative_to(root, item) for item in groups["runtime"]],
                "preview_files": [_relative_to(root, item) for item in groups["preview"]],
                "source_summary": summarize_model_file(primary_source) if primary_source else {},
                "runtime_summary": summarize_model_file(primary_runtime) if primary_runtime else {},
            }
        )

    return {
        "version": 1,
        "generated_at": _utc_now(),
        "workspace": {
            "source_models": _relative_to(root, paths["source_models"]),
            "runtime_models": _relative_to(root, paths["runtime_models"]),
            "preview_renders": _relative_to(root, paths["preview_renders"]),
        },
        "counts": {
            "models": len(models),
            "source_models": len(source_files),
            "runtime_models": len(runtime_files),
            "previews": len(preview_files),
        },
        "models": models,
    }


def sync_model_registry(project_root: str | Path, *, overwrite: bool = True) -> Dict[str, Any]:
    paths = project_modeling_paths(project_root)
    registry = build_model_registry(paths["project_root"])
    changed = _write_text(
        paths["model_registry"],
        yaml.safe_dump(registry, sort_keys=False, allow_unicode=True),
        overwrite,
    )
    return {
        "changed": changed,
        "registry_path": str(paths["model_registry"]),
        "registry": registry,
    }


def build_modeling_project_doc() -> str:
    return (
        "# Reverie Modeling Pipeline\n\n"
        "This project uses a Reverie-Gamer-only modeling workflow.\n\n"
        "## Source Of Truth\n"
        "- `assets/models/source/` stores authoring files such as `.bbmodel`.\n"
        "- `assets/models/source/blender/` stores generated Blender plans and Python authoring scripts.\n"
        "- `assets/models/runtime/` stores engine-facing exports such as `.glb` and `.gltf`.\n"
        "- `playtest/renders/models/` stores previews and review snapshots.\n"
        "- `data/models/model_registry.yaml` is generated by the modeling workbench.\n\n"
        "## Optional External Apps\n"
        "- Install Blender desktop manually for direct Blender execution.\n"
        "- Use Blockbench desktop only for optional visual `.bbmodel` editing.\n"
        "- Enable the Ashfox plugin inside Blockbench only for optional live MCP automation.\n"
        "- Keep Blockbench running only when using live Ashfox MCP tools through Reverie-Gamer.\n"
        "- Without Blockbench/Ashfox, Reverie can still validate simple `.bbmodel` files and export cuboid elements to `.gltf`.\n\n"
        "## Built-In Reverie Integration\n"
        "- `blender_modeling_workbench` generates Blender scripts, can run Blender in background mode, exports `.glb`, and renders previews.\n"
        "- `game_modeling_workbench` can validate `.bbmodel` files and export simple Blockbench cuboid models through a headless fallback.\n"
        "- Reverie-Gamer exposes the Ashfox MCP server as built-in dynamic tools when the endpoint is reachable.\n"
        "- `/modeling` manages stubs, imports, registry sync, and stack inspection without local helper scripts.\n\n"
        "## Recommended Flow\n"
        "1. Author or revise the `.bbmodel` source in Blockbench.\n"
        "2. Use Ashfox MCP tools from Reverie-Gamer to validate, preview, and export runtime geometry.\n"
        "3. Import the exported runtime model into `assets/models/runtime/`.\n"
        "4. Run the registry sync step so Reverie Engine can discover the updated model set.\n"
    )


def materialize_modeling_workspace(project_root: str | Path, *, overwrite: bool = False) -> Dict[str, Any]:
    paths = project_modeling_paths(project_root)
    created_directories: list[str] = []
    written_files: list[str] = []

    for key in ("assets_models", "source_models", "runtime_models", "preview_renders", "data_models"):
        target = paths[key]
        target.mkdir(parents=True, exist_ok=True)
        created_directories.append(str(target))

    files_to_write = {
        paths["pipeline_manifest"]: yaml.safe_dump(
            build_model_pipeline_manifest(paths["project_root"]),
            sort_keys=False,
            allow_unicode=True,
        ),
        paths["modeling_docs"]: build_modeling_project_doc(),
        paths["source_models"] / "README.md": (
            "# Source Models\n\n"
            "Store `.bbmodel` authoring files here. Reverie treats these as the editable source-of-truth for Blockbench workflows.\n"
        ),
        paths["runtime_models"] / "README.md": (
            "# Runtime Models\n\n"
            "Store engine-facing exports here, preferably `.glb` or `.gltf`, then sync the registry after imports.\n"
        ),
    }

    for file_path, content in files_to_write.items():
        if _write_text(file_path, content, overwrite):
            written_files.append(str(file_path))

    registry_result = sync_model_registry(paths["project_root"], overwrite=True)
    written_files.append(str(paths["model_registry"]))
    return {
        "directories": created_directories,
        "files": sorted(set(written_files)),
        "registry": registry_result["registry"],
        "stack": detect_modeling_stack(paths["project_root"]),
    }


def copy_imported_model(
    project_root: str | Path,
    runtime_source: str | Path,
    *,
    source_model: str | Path | None = None,
    preview_image: str | Path | None = None,
    dest_name: str | None = None,
    overwrite: bool = False,
) -> Dict[str, str]:
    paths = project_modeling_paths(project_root)
    root = paths["project_root"]
    runtime_path = Path(runtime_source)
    if not runtime_path.is_absolute():
        runtime_path = (root / runtime_path).resolve()
    if not runtime_path.exists():
        raise FileNotFoundError(f"Runtime model not found: {runtime_path}")

    base_name = _slugify(dest_name or runtime_path.stem)
    copied: Dict[str, str] = {}
    targets = {
        "runtime": paths["runtime_models"] / f"{base_name}{runtime_path.suffix.lower()}",
    }

    if source_model:
        source_path = Path(source_model)
        if not source_path.is_absolute():
            source_path = (root / source_path).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Source model not found: {source_path}")
        targets["source"] = paths["source_models"] / f"{base_name}{source_path.suffix.lower()}"
    else:
        source_path = None

    if preview_image:
        preview_path = Path(preview_image)
        if not preview_path.is_absolute():
            preview_path = (root / preview_path).resolve()
        if not preview_path.exists():
            raise FileNotFoundError(f"Preview image not found: {preview_path}")
        targets["preview"] = paths["preview_renders"] / f"{base_name}{preview_path.suffix.lower()}"
    else:
        preview_path = None

    items_to_copy = [("runtime", runtime_path), ("source", source_path), ("preview", preview_path)]
    for label, source in items_to_copy:
        if source is None or label not in targets:
            continue
        target = targets[label]
        if target.exists() and not overwrite:
            raise FileExistsError(f"Target already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        copied[f"{label}_path"] = _relative_to(root, target)

    return copied


def inspect_modeling_workspace(project_root: str | Path) -> Dict[str, Any]:
    paths = project_modeling_paths(project_root)
    stack = detect_modeling_stack(paths["project_root"])
    registry = build_model_registry(paths["project_root"])
    counts = registry.get("counts", {})
    return {
        "project_root": str(paths["project_root"]),
        "pipeline_exists": paths["pipeline_manifest"].exists(),
        "registry_exists": paths["model_registry"].exists(),
        "stack_ready": bool(stack["blockbench"]["available"] and stack["ashfox"]["reachable"]),
        "source_model_count": int(counts.get("source_models", 0)),
        "runtime_model_count": int(counts.get("runtime_models", 0)),
        "preview_count": int(counts.get("previews", 0)),
        "model_count": int(counts.get("models", 0)),
        "stack": stack,
        "registry": registry,
    }


__all__ = [
    "ASHFOX_DEFAULT_ENDPOINT",
    "ASHFOX_MCP_SERVER_NAME",
    "PREFERRED_RUNTIME_EXTENSIONS",
    "PREVIEW_EXTENSIONS",
    "RUNTIME_MODEL_EXTENSIONS",
    "SOURCE_MODEL_EXTENSIONS",
    "build_blockbench_model_stub",
    "build_model_pipeline_manifest",
    "build_model_registry",
    "copy_imported_model",
    "create_model_stub",
    "detect_modeling_stack",
    "inspect_modeling_workspace",
    "materialize_modeling_workspace",
    "project_modeling_paths",
    "summarize_model_file",
    "sync_model_registry",
]
