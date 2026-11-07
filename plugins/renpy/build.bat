@echo off
setlocal

cd /d "%~dp0"
set "PYTHON_EXE=python"

if exist "%~dp0..\..\ReverieCli-py\venv\Scripts\python.exe" (
  "%~dp0..\..\ReverieCli-py\venv\Scripts\python.exe" -c "import sys; print(sys.executable)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_EXE=%~dp0..\..\ReverieCli-py\venv\Scripts\python.exe"
)
if exist "%~dp0..\..\venv\Scripts\python.exe" (
  "%~dp0..\..\venv\Scripts\python.exe" -c "import sys; print(sys.executable)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_EXE=%~dp0..\..\venv\Scripts\python.exe"
)
"%PYTHON_EXE%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo PyInstaller is unavailable for %PYTHON_EXE%.
  exit /b 1
)
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --onefile --name reverie-renpy --specpath build plugin.py
endlocal & exit /b %ERRORLEVEL%
