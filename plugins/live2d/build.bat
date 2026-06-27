@echo off
setlocal

pushd "%~dp0" >nul
python -m PyInstaller --noconfirm --clean --onefile --name reverie-live2d plugin.py
set "RESULT=%ERRORLEVEL%"
popd >nul

exit /b %RESULT%
