# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
from pathlib import Path
import os

build_mode = os.environ.get('REVERIE_PYINSTALLER_MODE', 'onefile').strip().lower()
datas = [('README.md', '.')]
binaries = []
hiddenimports = ['rich', 'rich.console', 'rich.panel', 'rich.table', 'rich.syntax', 'rich.markdown', 'rich.progress', 'rich.prompt', 'rich.text', 'click', 'requests', 'openai', 'git', 'ddgs', 'bs4', 'yaml', 'tqdm', 
                 'pyglet', 'moderngl', 'glcontext', 'uiautomation', 'comtypes',
                 'pyglet.app', 'pyglet.media', 'pyglet.media.codecs', 'pyglet.media.codecs.base', 'pyglet.media.codecs.wave', 'pyglet.media.codecs.wmf', 'pyglet.window', 'pyglet.window.key', 'pyglet.window.mouse', 'pyglet.gl', 'pyglet.gl.wgl', 'comtypes.client',
                 'reverie.cli.input_handler', 'reverie.cli.commands', 'reverie.cli.display', 'reverie.cli.theme', 'reverie.cli.markdown_formatter', 'reverie.cli.session_ui',
                 'reverie.config', 'reverie.sdk_bridge', 'reverie.rules_manager', 'reverie.session', 'reverie.agent', 'reverie.context_engine',
                 'reverie.engine', 'reverie.engine.video', 'reverie.engine.renpy_import', 'reverie.engine.migration', 'reverie.engine.procedural_assets', 'reverie.engine.blender_modeling',
                 'reverie.computer_use', 'reverie.tools.open_computer_use',
                 'reverie.tools.registry', 'reverie.tools.browser_controler', 'reverie.tools.reverie_engine', 'reverie.tools.game_modeling_workbench', 'reverie.tools.blender_modeling_workbench']


def add_data_if_exists(source_path: Path, target_dir: str) -> None:
    if source_path.exists() and source_path.is_file():
        datas.append((str(source_path), target_dir))


def add_tree_if_exists(source_path: Path, target_dir: str) -> None:
    if not source_path.exists() or not source_path.is_dir():
        return
    for path in source_path.rglob("*"):
        if path.is_file():
            relative_parent = path.parent.relative_to(source_path)
            datas.append((str(path), str(Path(target_dir) / relative_parent)))


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
    browser_src = Path(resource_root) / "browser"
    packed_resource_src = Path(os.environ.get("REVERIE_PACKED_RES_DIR", "").strip() or Path(resource_root) / "packed")
else:
    comfy_src = repo_root / "Comfy"
    browser_src = repo_root / "reverie_resources" / "browser"
    packed_resource_src = repo_root / "reverie_resources"

required_bundle_files = [
    comfy_src / "generate_image.py",
    comfy_src / "embedded_comfy.b64",
]
if build_mode != 'ui-onedir':
    required_bundle_files.append(packed_resource_src / "browser.zip")
missing_bundle_files = [str(path) for path in required_bundle_files if not path.is_file()]
playwright_root = browser_src / "ms-playwright"
embedded_browser_candidates = []
if playwright_root.is_dir():
    for browser_name in ("chrome.exe", "chrome", "Chromium", "Google Chrome for Testing"):
        embedded_browser_candidates.extend(playwright_root.rglob(browser_name))
if missing_bundle_files or (build_mode == 'ui-onedir' and not embedded_browser_candidates):
    details = missing_bundle_files
    if not embedded_browser_candidates:
        details.append(str(playwright_root / "chromium-*" / "chrome-*" / "chrome.exe"))
    raise SystemExit(
        "Missing required bundled resources. Run build.bat/build.sh or set "
        "REVERIE_BUNDLE_RES_DIR to a prepared resource directory:\n- "
        + "\n- ".join(details)
    )

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
if build_mode != 'ui-onedir':
    add_data_if_exists(packed_resource_src / "browser.zip", "reverie_resources")
    add_data_if_exists(packed_resource_src / "ffmpeg.zip", "reverie_resources")
add_data_if_exists(repo_root / "reverie" / "agent" / "tool_manifest.json", "reverie/agent")
add_data_if_exists(repo_root / "reverie" / "engine" / "vendor" / "live2d" / "live2dcubismcore.min.js", "reverie/engine/vendor/live2d")
add_tree_if_exists(repo_root / "reverie" / "builtin_skills", "reverie/builtin_skills")
add_data_if_exists(repo_root / "reverie" / "computer_use" / "ATTRIBUTION.md", "reverie/computer_use")

for package_name in ('rich', 'bs4', 'pyglet', 'moderngl', 'glcontext', 'uiautomation', 'comtypes'):
    try:
        datas += collect_data_files(package_name, include_py_files=False)
        binaries += collect_dynamic_libs(package_name)
    except Exception:
        pass

try:
    import certifi

    add_data_if_exists(Path(certifi.where()), "certifi")
    hiddenimports.append("certifi")
except Exception:
    pass


excluded_modules = ['tensorboard', 'torch.utils.tensorboard']
if build_mode == 'ui-onedir':
    excluded_modules.extend(['tkinter', '_tkinter'])

a = Analysis(
    [str(entry_script)],
    pathex=[str(repo_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

common_exe_options = dict(
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

if build_mode in {'onedir', 'ui-onedir'}:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        contents_directory='reverie-runtime' if build_mode == 'ui-onedir' else '.',
        **common_exe_options,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='reverie',
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        **common_exe_options,
    )
