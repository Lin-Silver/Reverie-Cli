# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
import os
import shutil

datas = [('README.md', '.')]
binaries = []
hiddenimports = ['rich', 'rich.console', 'rich.panel', 'rich.table', 'rich.syntax', 'rich.markdown', 'rich.progress', 'rich.prompt', 'rich.text', 'click', 'requests', 'openai', 'git', 'ddgs', 'bs4', 'yaml', 'tqdm', 
                 'pyglet', 'moderngl', 'glcontext',
                 'reverie.cli.input_handler', 'reverie.cli.commands', 'reverie.cli.display', 'reverie.cli.theme', 'reverie.cli.markdown_formatter', 'reverie.cli.session_ui',
                 'reverie.config', 'reverie.rules_manager', 'reverie.session', 'reverie.agent', 'reverie.context_engine',
                 'reverie.engine_lite', 'reverie.engine_lite.video', 'reverie.engine_lite.renpy_import', 'reverie.engine_lite.procedural_assets',
                 'reverie.tools.registry', 'reverie.tools.reverie_engine', 'reverie.tools.reverie_engine_lite', 'reverie.tools.game_modeling_workbench']


def add_data_if_exists(source_path: Path, target_dir: str) -> None:
    if source_path.exists() and source_path.is_file():
        datas.append((str(source_path), target_dir))


def add_binary_if_exists(source_path: Path, target_dir: str) -> None:
    if source_path.exists() and source_path.is_file():
        binaries.append((str(source_path), target_dir))


def resolve_ffmpeg_binary() -> Path | None:
    candidates = []
    ffmpeg_env = os.environ.get("REVERIE_FFMPEG_PATH", "").strip()
    if ffmpeg_env:
        env_path = Path(ffmpeg_env)
        if env_path.is_dir():
            candidates.extend([env_path / "ffmpeg.exe", env_path / "ffmpeg"])
        else:
            candidates.append(env_path)

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        candidates.append(Path(which_ffmpeg))

    candidates.extend(
        [
            Path("D:/Program Files/Environment/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


# NOTE:
# PyInstaller executes .spec via exec(), where __file__ is not guaranteed.
# Use current working directory as fallback project root.
repo_root = Path(os.getcwd()).resolve()
legacy_entry = repo_root / "run_reverie.py"
package_entry = repo_root / "reverie" / "__main__.py"
entry_script = legacy_entry if legacy_entry.exists() else package_entry
resource_root = os.environ.get("REVERIE_BUNDLE_RES_DIR", "").strip()
if resource_root:
    comfy_src = Path(resource_root) / "comfy"
else:
    comfy_src = repo_root / "Comfy"

icon_path_env = os.environ.get("REVERIE_ICON_PATH", "").strip()
resolved_icon = None
if icon_path_env:
    candidate = Path(icon_path_env)
    if candidate.exists():
        resolved_icon = candidate
if resolved_icon is None:
    for fallback_icon in (repo_root / "reverie.ico", repo_root / "reverie.png"):
        if fallback_icon.exists():
            resolved_icon = fallback_icon
            break

add_data_if_exists(comfy_src / "generate_image.py", "reverie_resources/comfy")
add_data_if_exists(comfy_src / "embedded_comfy.b64", "reverie_resources/comfy")
add_data_if_exists(repo_root / "reverie" / "engine_lite" / "vendor" / "live2d" / "live2dcubismcore.min.js", "reverie/engine_lite/vendor/live2d")

ffmpeg_binary = resolve_ffmpeg_binary()
if ffmpeg_binary is not None:
    add_binary_if_exists(ffmpeg_binary, "reverie_resources/ffmpeg")

for package_name in ('rich', 'bs4', 'pyglet', 'moderngl', 'glcontext'):
    try:
        tmp_ret = collect_all(package_name)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass


a = Analysis(
    [str(entry_script)],
    pathex=[str(repo_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tensorboard', 'torch.utils.tensorboard'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='reverie',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(resolved_icon)] if resolved_icon else None,
)
