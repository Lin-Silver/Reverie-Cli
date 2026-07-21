@echo off
setlocal
chcp 65001 >nul

for %%I in ("%~dp0.") do set "UI_ROOT=%%~fI"
for %%I in ("%UI_ROOT%\..") do set "REPO_ROOT=%%~fI"

where node >nul 2>&1 || (echo [ERROR] Node.js is required. & exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] npm is required. & exit /b 1)

call "%REPO_ROOT%\ReverieCli-py\build.bat" --reuse-venv --test-exe --skip-plugins --no-pause
if not "%ERRORLEVEL%"=="0" exit /b 1

cd /d "%UI_ROOT%"
call npm ci
if not "%ERRORLEVEL%"=="0" exit /b 1

set "REVERIE_EXTERNAL_KERNEL_PATH=%REPO_ROOT%\dist\reverie.exe"
call npm run dist:win
if not "%ERRORLEVEL%"=="0" exit /b 1

for /f "delims=" %%V in ('node -p "require('./package.json').version"') do set "VERSION=%%V"
if not exist "%UI_ROOT%\release\Reverie-Setup-%VERSION%-x64.exe" (
  echo [ERROR] Windows installer was not produced.
  exit /b 1
)
if not exist "%REPO_ROOT%\dist\Reverie-Portable-%VERSION%-x64.exe" (
  echo [ERROR] Windows portable executable was not produced.
  exit /b 1
)

echo [OK] Reverie %VERSION% Windows CLI, installer, and portable GUI are ready.
pause
exit /b 0
