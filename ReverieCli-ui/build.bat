@echo off
setlocal
chcp 65001 >nul

set "NO_PAUSE=0"
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"
shift
goto parse_args
:args_done

for %%I in ("%~dp0.") do set "UI_ROOT=%%~fI"
for %%I in ("%UI_ROOT%\..") do set "REPO_ROOT=%%~fI"

where node >nul 2>&1 || (echo [ERROR] Node.js is required. & exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] npm is required. & exit /b 1)

call "%REPO_ROOT%\ReverieCli-py\build.bat" --reuse-venv --test-exe --skip-plugins --no-pause
if not "%ERRORLEVEL%"=="0" exit /b 1

cd /d "%UI_ROOT%"
call npm ci --fetch-retries=0 --fetch-timeout=15000
if not "%ERRORLEVEL%"=="0" (
  echo [WARN] npm ci failed with the current user npm configuration.
  echo [WARN] Retrying without the user-level .npmrc in case a local proxy is unavailable.
  call npm ci --userconfig=NUL
  if errorlevel 1 exit /b 1
)

set "REVERIE_EXTERNAL_KERNEL_PATH=%REPO_ROOT%\dist\reverie.exe"
if not defined ELECTRON_MIRROR set "ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/"
if not defined ELECTRON_BUILDER_BINARIES_MIRROR set "ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/"
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
if "%NO_PAUSE%"=="0" pause
exit /b 0
