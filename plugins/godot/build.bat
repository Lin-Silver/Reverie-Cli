@echo off
setlocal
cd /d "%~dp0"

set "PLUGIN_NAME=reverie-godot"

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name "%PLUGIN_NAME%" ^
  --specpath build ^
  plugin.py

endlocal
