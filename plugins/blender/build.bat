@echo off
setlocal
cd /d "%~dp0"

set "PLUGIN_NAME=reverie-blender"
set "ARCHIVE_NAME=blender-5.1.1-windows-x64.zip"
set "ARCHIVE_SOURCE="
set "PYTHON_EXE=python"

if exist "%~dp0..\..\venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0..\..\venv\Scripts\python.exe"
)

if exist "%~dp0%ARCHIVE_NAME%" set "ARCHIVE_SOURCE=%~dp0%ARCHIVE_NAME%"
if not defined ARCHIVE_SOURCE if exist "%~dp0..\..\dist\.reverie\plugins\blender\%ARCHIVE_NAME%" set "ARCHIVE_SOURCE=%~dp0..\..\dist\.reverie\plugins\blender\%ARCHIVE_NAME%"
if not defined ARCHIVE_SOURCE if exist "%~dp0..\..\%ARCHIVE_NAME%" set "ARCHIVE_SOURCE=%~dp0..\..\%ARCHIVE_NAME%"

if not defined ARCHIVE_SOURCE (
  echo Blender archive not found. Expected %ARCHIVE_NAME% beside this plugin, in dist\.reverie\plugins\blender, or at the repository root.
  exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name "%PLUGIN_NAME%" ^
  --specpath build ^
  --add-data "%ARCHIVE_SOURCE%;." ^
  plugin.py

endlocal
