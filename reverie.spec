# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('README.md', '.')]
binaries = []
hiddenimports = ['rich', 'rich.console', 'rich.panel', 'rich.table', 'rich.syntax', 'rich.markdown', 'rich.progress', 'rich.prompt', 'rich.text', 'click', 'requests', 'openai', 'git', 'duckduckgo_search', 'tqdm', 
                 'reverie.cli.input_handler', 'reverie.cli.commands', 'reverie.cli.display', 'reverie.cli.theme', 'reverie.cli.markdown_formatter', 'reverie.cli.session_ui',
                 'reverie.config', 'reverie.rules_manager', 'reverie.session', 'reverie.agent', 'reverie.context_engine']
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
