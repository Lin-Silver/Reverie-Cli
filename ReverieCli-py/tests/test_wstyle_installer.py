"""Exercise the actual Windows cleanup macro without registering an application."""

import ctypes
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _maker():
    if sys.platform != "win32":
        pytest.skip("The native NSIS cleanup regression requires Windows")
    cache = Path(os.environ.get("LOCALAPPDATA", "")) / "electron-builder/Cache"
    candidates = sorted(cache.glob("nsis-*/nsis-*/Bin/makensis.exe"))
    if not candidates:
        pytest.skip("Build the Windows desktop package to populate the NSIS compiler cache")
    return candidates[-1]


def _cleanup_probe(tmp_path):
    installation = tmp_path / "installation"
    installation.mkdir()
    preserved = installation / ".reverie/wstyles/中文卡.md"
    preserved.parent.mkdir(parents=True)
    preserved.write_bytes("用户风格卡，必须完整保留。".encode("utf-8"))
    resources = installation / "resources/app.asar"
    resources.parent.mkdir()
    resources.write_bytes(b"application resource")
    long_file = installation / "reverie-runtime" / ("long-resource-" * 8) / ("nested-resource-" * 8) / "source.md"
    long_file.parent.mkdir(parents=True)
    long_file.write_bytes(b"long packaged source")
    assert len(str(long_file)) > 260
    (installation / "z-busy.dll").write_bytes(b"locked application file")
    stock = (ROOT / "ReverieCli-ui/node_modules/app-builder-lib/templates/nsis/uninstaller.nsh").read_text(encoding="utf-8")
    helpers = stock[stock.index("Function un.atomicRMDir"):stock.index("!ifndef UNINSTALL_SECTION_NAME")]
    script = f'''Unicode true
SilentInstall silent
RequestExecutionLevel user
Name "Reverie WStyle Cleanup Regression"
OutFile "{tmp_path / 'bootstrap.exe'}"
InstallDir "{installation}"
!define UNINSTALL_FILENAME "Uninstall probe.exe"
!define BUILD_UNINSTALLER
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "{ROOT / 'ReverieCli-ui/build/windows/installer.nsh'}"
{helpers}
Section
  SetOutPath $INSTDIR
  WriteUninstaller "$INSTDIR\\${{UNINSTALL_FILENAME}}"
SectionEnd
Section "un.Uninstall"
  InitPluginsDir
  !insertmacro customRemoveFiles
SectionEnd
'''
    source = tmp_path / "probe.nsi"
    source.write_text(script, encoding="utf-8")
    compiled = subprocess.run([str(_maker()), "/V2", str(source)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    subprocess.run([str(tmp_path / "bootstrap.exe"), "/S"], check=True, timeout=30,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    return installation, preserved, resources, long_file


def _uninstall(installation):
    return subprocess.run([str(installation / "Uninstall probe.exe"), "/S", f"_?={installation}"],
                          timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)


def test_wstyle_cleanup_handles_long_resources_and_preserves_user_data(tmp_path):
    _maker()
    installation, preserved, resources, long_file = _cleanup_probe(tmp_path)
    before = set(tmp_path.iterdir())
    result = _uninstall(installation)
    assert result.returncode == 0
    assert preserved.read_bytes() == "用户风格卡，必须完整保留。".encode("utf-8")
    assert not resources.exists() and not long_file.exists()
    assert not (installation / "z-busy.dll").exists()
    assert all(path.name in {".reverie", "Uninstall probe.exe"} for path in installation.iterdir())
    assert set(tmp_path.iterdir()) == before, "Successful cleanup must not leave a staging directory"


def test_wstyle_cleanup_rolls_back_all_application_files_when_one_is_busy(tmp_path):
    _maker()
    installation, preserved, resources, long_file = _cleanup_probe(tmp_path)
    original = {path: path.read_bytes() for path in installation.rglob("*") if path.is_file()}
    before = set(tmp_path.iterdir())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                  ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(installation / "z-busy.dll"), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        assert _uninstall(installation).returncode != 0
        assert all(path.is_file() and path.read_bytes() == content for path, content in original.items())
        assert set(tmp_path.iterdir()) == before, "A complete rollback must remove its empty staging directory"
    finally:
        kernel.CloseHandle(handle)
    assert _uninstall(installation).returncode == 0
    assert preserved.read_bytes() == original[preserved]
    assert not resources.exists() and not long_file.exists()


def _legacy_upgrade_probe(tmp_path, failure=None):
    installation = tmp_path / "installation"
    preserved = installation / ".reverie/wstyles/中文卡.md"
    preserved.parent.mkdir(parents=True)
    preserved.write_bytes("用户风格卡，必须完整保留。".encode("utf-8"))
    (installation / ".reverie/config.json").write_bytes(b'{"writer_wstyles":["original"]}')
    (installation / "old-application.dll").write_bytes(b"old application")
    long_file = installation / "reverie-runtime" / ("long-resource-" * 8) / ("nested-resource-" * 8) / "source.md"
    long_file.parent.mkdir(parents=True)
    long_file.write_bytes(b"old long packaged source")
    (installation / "resources").mkdir()
    (installation / "resources/app.asar").write_bytes(b"old application resource")
    stock = (ROOT / "ReverieCli-ui/node_modules/app-builder-lib/templates/nsis/uninstaller.nsh").read_text(encoding="utf-8")
    helpers = stock[stock.index("Function un.atomicRMDir"):stock.index("!ifndef UNINSTALL_SECTION_NAME")]
    helpers = helpers.replace("un.atomicRMDir", "legacyAtomicRMDir").replace("un.restoreFiles", "legacyRestoreFiles")
    stop = "" if failure is None else f"SetErrorLevel 2\n  {failure}"
    if failure == "Quit":
        stop = '''StrCpy $R0 "2"
  !ifmacrodef customUnInstallCheck
    !insertmacro customUnInstallCheck
  !else
    SetErrorLevel 2
    Quit
  !endif'''
    elif failure == "RestoreConflict":
        stop = '''CreateDirectory "$INSTDIR\\.reverie"
  FileOpen $0 "$INSTDIR\\.reverie\\config.json" w
  FileWrite $0 "new conflicting data"
  FileClose $0'''
    script = f'''Unicode true
SilentInstall silent
RequestExecutionLevel user
Name "Reverie WStyle Legacy Upgrade Regression"
OutFile "{tmp_path / 'upgrade.exe'}"
InstallDir "{installation}"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!define UNINSTALL_FILENAME "Uninstall probe.exe"
Var installMode
Var perUserInstallationFolder
Var perMachineInstallationFolder
!macro IS_POWERSHELL_AVAILABLE
!macroend
!macro _CHECK_APP_RUNNING
  ${{GetProcessInfo}} 0 $pid $1 $2 $3 $4
!macroend
!addincludedir "{ROOT / 'ReverieCli-ui/node_modules/app-builder-lib/templates/nsis/include'}"
!include "{ROOT / 'ReverieCli-ui/build/windows/installer.nsh'}"
!ifmacrodef customHeader
  !insertmacro customHeader
!endif
Function .onInit
  StrCpy $installMode "current"
  StrCpy $perUserInstallationFolder $INSTDIR
FunctionEnd
{helpers}
Section
  InitPluginsDir
  SetOutPath $TEMP
  !ifmacrodef customCheckAppRunning
    !insertmacro customCheckAppRunning
  !endif
  CreateDirectory "$PLUGINSDIR\\old-install"
  Push ""
  Call legacyAtomicRMDir
  Pop $R0
  ${{if}} $R0 != 0
    FileOpen $0 "{tmp_path / 'legacy-error.txt'}" w
    FileWrite $0 "$R0"
    FileClose $0
    Push ""
    Call legacyRestoreFiles
    Pop $R0
    SetErrorLevel 2
    Abort "The stock old uninstaller failed to move a packaged resource."
  ${{endif}}
  RMDir /r "$INSTDIR"
  {stop}
  SetOutPath $INSTDIR
  FileOpen $0 "$INSTDIR\\new-application.dll" w
  FileWrite $0 "new application"
  FileClose $0
  !insertmacro customInstall
SectionEnd
'''
    source = tmp_path / "upgrade.nsi"
    source.write_text(script, encoding="utf-8")
    compiled = subprocess.run([str(_maker()), "/V2", str(source)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    before = set(tmp_path.iterdir())
    result = subprocess.run([str(tmp_path / "upgrade.exe"), "/S"], timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return installation, preserved, result, before


def test_wstyle_upgrade_preserves_data_before_legacy_recursive_removal(tmp_path):
    _maker()
    installation, preserved, result, before = _legacy_upgrade_probe(tmp_path)
    assert result.returncode == 0
    assert preserved.is_file(), "The new installer must protect data from the old uninstaller"
    assert preserved.read_bytes() == "用户风格卡，必须完整保留。".encode("utf-8")
    assert (installation / ".reverie/config.json").read_bytes() == b'{"writer_wstyles":["original"]}'
    assert (installation / "new-application.dll").read_bytes() == b"new application"
    assert not (installation / "reverie-runtime").exists()
    assert not (installation / "resources").exists()
    assert set(tmp_path.iterdir()) == before, "Successful restore must remove the temporary backup"


@pytest.mark.parametrize("failure", ["Abort", "Quit"])
def test_wstyle_failed_legacy_upgrade_restores_user_data(tmp_path, failure):
    _maker()
    installation, preserved, result, before = _legacy_upgrade_probe(tmp_path, failure)
    assert result.returncode != 0
    assert preserved.is_file(), "A failed old uninstaller must not strand or delete user data"
    assert preserved.read_bytes() == "用户风格卡，必须完整保留。".encode("utf-8")
    assert (installation / ".reverie/config.json").read_bytes() == b'{"writer_wstyles":["original"]}'
    assert (installation / "resources/app.asar").read_bytes() == b"old application resource"
    long_files = list((installation / "reverie-runtime").rglob("source.md"))
    assert len(long_files) == 1 and long_files[0].read_bytes() == b"old long packaged source"
    assert set(tmp_path.iterdir()) == before, "Failure recovery must remove the temporary backup"


def test_wstyle_legacy_restore_conflict_preserves_both_versions_and_reports_failure(tmp_path):
    _maker()
    installation, preserved, result, before = _legacy_upgrade_probe(tmp_path, "RestoreConflict")
    assert result.returncode != 0, "An unrestored backup must not be reported as a successful upgrade"
    assert (installation / ".reverie/config.json").read_bytes() == b"new conflicting data"
    backups = set(tmp_path.iterdir()) - before
    assert len(backups) == 1
    backup = backups.pop() / ".reverie"
    assert (backup / "wstyles/中文卡.md").read_bytes() == "用户风格卡，必须完整保留。".encode("utf-8")
    assert (backup / "config.json").read_bytes() == b'{"writer_wstyles":["original"]}'
    assert not preserved.exists(), "Original Cards must remain in the reported backup until the conflict is resolved"
