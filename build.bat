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

for %%I in ("%~dp0.") do set "REPO_ROOT=%%~fI"
set "UI_ROOT=%REPO_ROOT%\ReverieCli-ui"
set "REVERIE_PYINSTALLER_MODE=onefile"
set "REVERIE_PYTHON_PATH=%REPO_ROOT%\ReverieCli-py\build\venv\Scripts\python.exe"

where node >nul 2>&1 || (echo [ERROR] Node.js is required. & exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] npm is required. & exit /b 1)
node -e "process.exit(process.platform === 'win32' && process.arch === 'x64' ? 0 : 1)"
if errorlevel 1 (echo [ERROR] Windows x64 Node.js is required. & exit /b 1)

call "%REPO_ROOT%\ReverieCli-py\build.bat" --reuse-venv --test-exe --skip-plugins --no-pause
if not "%ERRORLEVEL%"=="0" exit /b 1

"%REVERIE_PYTHON_PATH%" "%REPO_ROOT%\ReverieCli-py\scripts\smoke_sdk_bridge.py" --executable "%REPO_ROOT%\dist\reverie.exe" --timeout 120
if errorlevel 1 exit /b 1

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
set "PORTABLE_PATH="
for /f "delims=" %%P in ('node -p "const fs=require('fs'),path=require('path');const p=path.resolve(JSON.parse(fs.readFileSync('build/generated/portable-artifact.json','utf8')).path);if(!p.startsWith(path.resolve('../dist')+path.sep))throw Error('Unsafe portable artifact path');p"') do set "PORTABLE_PATH=%%P"
if not defined PORTABLE_PATH exit /b 1
if not exist "%PORTABLE_PATH%" (
  echo [ERROR] Windows portable executable was not produced.
  exit /b 1
)

node scripts/clean-build-staging.mjs
if errorlevel 1 exit /b 1

echo [OK] Reverie %VERSION% Windows CLI, installer, and portable GUI are ready.
echo [OK] Portable GUI: %PORTABLE_PATH%
if "%NO_PAUSE%"=="0" pause
exit /b 0
