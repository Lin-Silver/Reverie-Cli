@echo off
setlocal
cd /d "%~dp0"

if not exist "plugin.py" (
    echo [ERROR] Missing plugin.py
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --onefile --name reverie-game-models plugin.py
exit /b %ERRORLEVEL%
