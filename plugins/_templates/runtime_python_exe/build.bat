@echo off
setlocal
cd /d "%~dp0"

set "PLUGIN_ID={{plugin_id}}"
set "PLUGIN_NAME=reverie-%PLUGIN_ID%"
set "SDK_PATH=%~dp0..\_sdk"

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name "%PLUGIN_NAME%" ^
  --paths "%SDK_PATH%" ^
  --add-data "%SDK_PATH%;_sdk" ^
  plugin.py

endlocal
