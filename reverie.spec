# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
import os

datas = [('README.md', '.')]
binaries = []
hiddenimports = ['rich', 'rich.console', 'rich.panel', 'rich.table', 'rich.syntax', 'rich.markdown', 'rich.progress', 'rich.prompt', 'rich.text', 'click', 'requests', 'openai', 'git', 'duckduckgo_search', 'tqdm', 
                 'reverie.cli.input_handler', 'reverie.cli.commands', 'reverie.cli.display', 'reverie.cli.theme', 'reverie.cli.markdown_formatter', 'reverie.cli.session_ui',
                 'reverie.config', 'reverie.rules_manager', 'reverie.session', 'reverie.agent', 'reverie.context_engine']


def add_data_if_exists(source_path: Path, target_dir: str) -> None:
    if source_path.exists() and source_path.is_file():
        datas.append((str(source_path), target_dir))


# NOTE:
# PyInstaller executes .spec via exec(), where __file__ is not guaranteed.
# Use current working directory as fallback project root.
repo_root = Path(os.getcwd()).resolve()
resource_root = os.environ.get("REVERIE_BUNDLE_RES_DIR", "").strip()
if resource_root:
    comfy_src = Path(resource_root) / "comfy"
else:
    comfy_src = repo_root / "Comfy"

add_data_if_exists(comfy_src / "generate_image.py", "reverie_resources/comfy")
add_data_if_exists(comfy_src / "embedded_comfy.b64", "reverie_resources/comfy")

tmp_ret = collect_all('rich')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('openai')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['reverie\\__main__.py'],
    pathex=[],
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
    icon=['reverie.png'],
)
