@echo off
setlocal
cd /d "%~dp0"

set "PLUGIN_NAME=reverie-o3de"
set "PYTHON_EXE=python"

if exist "%~dp0..\..\venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0..\..\venv\Scripts\python.exe"
)

"%PYTHON_EXE%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name "%PLUGIN_NAME%" ^
  --specpath build ^
  plugin.py

endlocal & exit /b %ERRORLEVEL%
