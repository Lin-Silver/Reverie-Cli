import base64
import io
import json
import os
import pathlib
import subprocess
import zipfile


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def resolve_source_root() -> pathlib.Path:
    env_source = os.environ.get("REVERIE_COMFYUI_SOURCE", "").strip()
    candidates = [
        pathlib.Path(env_source) if env_source else None,
        REPO_ROOT / "references" / "ComfyUI",
        SCRIPT_DIR / "ComfyUI-master",
        SCRIPT_DIR / "add-on" / "ComfyUI-master",
    ]
    for candidate in candidates:
        if candidate and (candidate / "comfy").exists() and (candidate / "nodes.py").exists():
            return candidate.resolve()
    raise SystemExit(
        "No ComfyUI source tree found. Clone ComfyUI into references/ComfyUI "
        "or set REVERIE_COMFYUI_SOURCE."
    )


def resolve_gguf_node_root() -> pathlib.Path | None:
    env_source = os.environ.get("REVERIE_COMFYUI_GGUF_SOURCE", "").strip()
    candidates = [
        pathlib.Path(env_source) if env_source else None,
        SCRIPT_DIR / "add-on" / "ComfyUI-GGUF",
        REPO_ROOT / "references" / "ComfyUI-GGUF",
    ]
    for candidate in candidates:
        if candidate and (candidate / "__init__.py").exists() and (candidate / "nodes.py").exists():
            return candidate.resolve()
    return None


def git_revision(path: pathlib.Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def should_skip(path: pathlib.Path) -> bool:
    parts = set(path.parts)
    skip_names = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
    }
    if parts & skip_names:
        return True
    return path.name in {".gitignore", ".gitattributes"}


def write_tree(zf: zipfile.ZipFile, root: pathlib.Path, prefix: str = "") -> set[pathlib.Path]:
    dirs: set[pathlib.Path] = set()
    for dirpath, dirnames, files in os.walk(root):
        dirpath = pathlib.Path(dirpath)
        if should_skip(dirpath):
            continue
        rel_dir = dirpath.relative_to(root)
        if str(rel_dir) != ".":
            dirs.add(rel_dir)
        dirnames[:] = [d for d in dirnames if not should_skip(dirpath / d)]
        for filename in files:
            full = dirpath / filename
            if should_skip(full):
                continue
            rel = full.relative_to(root)
            arc = pathlib.PurePosixPath(prefix) / pathlib.PurePosixPath(str(rel).replace("\\", "/"))
            zf.write(full, arcname=str(arc))
    return dirs


def main() -> None:
    root = resolve_source_root()
    gguf_root = resolve_gguf_node_root()
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        dirs = write_tree(zf, root)

        if gguf_root:
            write_tree(zf, gguf_root, "custom_nodes/ComfyUI-GGUF")

        names = set(zf.namelist())
        for directory in dirs:
            if not directory.parts or directory.parts[0] != "comfy":
                continue
            init_path = directory / "__init__.py"
            arc = str(init_path).replace("\\", "/")
            if arc not in names:
                zf.writestr(arc, "")
                names.add(arc)

        if "comfy/__init__.py" not in names:
            zf.writestr("comfy/__init__.py", "")
            names.add("comfy/__init__.py")

        manifest = {
            "comfyui_source": str(root),
            "comfyui_revision": git_revision(root),
            "comfyui_gguf_source": str(gguf_root or ""),
            "comfyui_gguf_revision": git_revision(gguf_root) if gguf_root else "",
            "contains_custom_nodes": ["ComfyUI-GGUF"] if gguf_root else [],
            "entry_count": len(zf.namelist()),
        }
        zf.writestr("reverie_embedded_manifest.json", json.dumps(manifest, indent=2))

    output = SCRIPT_DIR / "embedded_comfy.b64"
    output.write_text(base64.b64encode(mem.getvalue()).decode(), encoding="utf-8")
    print(
        "rebuilt embedded_comfy.b64",
        f"entries={manifest['entry_count']}",
        f"comfyui={manifest['comfyui_revision']}",
        f"gguf={manifest['comfyui_gguf_revision']}",
    )


if __name__ == "__main__":
    main()
