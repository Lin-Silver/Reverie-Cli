@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "PYTHON_EXE=python"
for %%I in ("%~dp0.") do set "ROOT_DIR=%%~fI"
for %%I in ("%ROOT_DIR%\..") do set "REPO_ROOT=%%~fI"
cd /d "%ROOT_DIR%"
set "VENV_DIR=%ROOT_DIR%\venv"
set "OUTPUT_DIR=%REPO_ROOT%\dist"
set "BUILD_DIR=%ROOT_DIR%\build"
set "LOCAL_BUILD_ROOT=%ROOT_DIR%\build"
set "LOCAL_TEMP_DIR=%LOCAL_BUILD_ROOT%\temp"
set "LOCAL_PIP_CACHE=%LOCAL_BUILD_ROOT%\pip-cache"
set "PYI_CONFIG_DIR=%LOCAL_BUILD_ROOT%\pyinstaller-config"
set "PYI_WORK_DIR=%BUILD_DIR%\pyinstaller"
set "PYI_DIST_DIR=%OUTPUT_DIR%"
set "PYI_SPEC_DIR=%BUILD_DIR%\pyinstaller-spec"
set "RECREATE_VENV=0"
set "RUN_EXE_TEST=0"
set "USER_FFMPEG_PATH=%REVERIE_FFMPEG_PATH%"
set "REVERIE_FFMPEG_PATH="
set "TMP=%LOCAL_TEMP_DIR%"
set "TEMP=%LOCAL_TEMP_DIR%"
set "TMPDIR=%LOCAL_TEMP_DIR%"
set "PIP_CACHE_DIR=%LOCAL_PIP_CACHE%"
set "PYINSTALLER_CONFIG_DIR=%PYI_CONFIG_DIR%"
set "BUILD_EXIT_CODE=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--recreate-venv" set "RECREATE_VENV=1"
if /I "%~1"=="--reuse-venv" set "RECREATE_VENV=0"
if /I "%~1"=="--test-exe" set "RUN_EXE_TEST=1"
shift
goto parse_args

:args_done

echo.
echo ===============================================================
echo   Reverie Cli Build
echo ===============================================================
echo   Python root: %ROOT_DIR%
echo   Repository root: %REPO_ROOT%

where %PYTHON_EXE% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python executable not found in PATH.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

for /f %%V in ('%PYTHON_EXE% -c "import platform; print(platform.python_version())"') do set "PY_VERSION=%%V"
echo [1/5] Python detected: %PY_VERSION%

echo.
echo [2/5] Preparing virtual environment...
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" >nul 2>&1
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%" >nul 2>&1
if not exist "%LOCAL_BUILD_ROOT%" mkdir "%LOCAL_BUILD_ROOT%" >nul 2>&1
if not exist "%LOCAL_TEMP_DIR%" mkdir "%LOCAL_TEMP_DIR%" >nul 2>&1
if not exist "%LOCAL_PIP_CACHE%" mkdir "%LOCAL_PIP_CACHE%" >nul 2>&1
if not exist "%PYI_CONFIG_DIR%" mkdir "%PYI_CONFIG_DIR%" >nul 2>&1
if exist "%VENV_DIR%\Scripts\activate.bat" (
    if "%RECREATE_VENV%"=="1" (
        echo       Recreating %VENV_DIR%...
        rmdir /s /q "%VENV_DIR%"
        %PYTHON_EXE% -m venv "%VENV_DIR%"
    ) else (
        echo       Using existing %VENV_DIR%
    )
) else (
    echo       Creating %VENV_DIR%...
    %PYTHON_EXE% -m venv "%VENV_DIR%"
)
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3.10+ is required for Reverie build.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

echo.
echo [3/5] Installing build dependencies...
python -m pip install --upgrade pyinstaller pillow
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller or Pillow.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

python -m pip install -e .
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install Reverie into the build environment.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

echo.
echo [4/5] Resolving optional ffmpeg and icon...
if defined USER_FFMPEG_PATH if exist "%USER_FFMPEG_PATH%" set "REVERIE_FFMPEG_PATH=%USER_FFMPEG_PATH%"
if not defined REVERIE_FFMPEG_PATH (
    for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined REVERIE_FFMPEG_PATH set "REVERIE_FFMPEG_PATH=%%F"
)
if not defined REVERIE_FFMPEG_PATH if exist "D:\Program Files\Environment\ffmpeg\bin\ffmpeg.exe" set "REVERIE_FFMPEG_PATH=D:\Program Files\Environment\ffmpeg\bin\ffmpeg.exe"
if not defined REVERIE_FFMPEG_PATH if exist "C:\Program Files\ffmpeg\bin\ffmpeg.exe" set "REVERIE_FFMPEG_PATH=C:\Program Files\ffmpeg\bin\ffmpeg.exe"

if defined REVERIE_FFMPEG_PATH (
    echo       ffmpeg: %REVERIE_FFMPEG_PATH%
) else (
    echo       ffmpeg not found. Runtime will use external ffmpeg if needed.
)

set "ICON_ICO=%ROOT_DIR%\reverie.ico"
set "ICON_PNG=%ROOT_DIR%\reverie.png"
set "REVERIE_ICON_PATH="

if exist "%ICON_PNG%" (
    python "%ROOT_DIR%\scripts\generate_reverie_icons.py" --source "%ICON_PNG%" "%ICON_ICO%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to generate icons from %ICON_PNG%.
        set "BUILD_EXIT_CODE=1"
        goto finish
    )
    set "REVERIE_ICON_PATH=%ICON_ICO%"
) else if exist "%ICON_ICO%" (
    echo       reverie.png not found. Falling back to existing ico.
    set "REVERIE_ICON_PATH=%ICON_ICO%"
)

if defined REVERIE_ICON_PATH (
    echo       icon: %REVERIE_ICON_PATH%
) else (
    echo       icon not found. Build will continue without a custom icon.
)

echo.
echo [5/5] Building executable...
if exist "%PYI_WORK_DIR%" rmdir /s /q "%PYI_WORK_DIR%"
if exist "%PYI_SPEC_DIR%" rmdir /s /q "%PYI_SPEC_DIR%"
if exist "%PYI_DIST_DIR%\reverie.exe" del /f /q "%PYI_DIST_DIR%\reverie.exe" >nul 2>&1
set "PYI_PYTHONWARNINGS=ignore:Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.:UserWarning"
set "PYTHONWARNINGS=%PYI_PYTHONWARNINGS%"
pyinstaller --noconfirm --clean --distpath "%PYI_DIST_DIR%" --workpath "%PYI_WORK_DIR%" --specpath "%PYI_SPEC_DIR%" --name "reverie" --onefile --windowed --icon "%REVERIE_ICON_PATH%" --add-data "%ROOT_DIR%\reverie;reverie" --hidden-import=msvcrt --hidden-import=ctypes --collect-all=rich --collect-all=pyglet --collect-all=moderngl --collect-all=glcontext --copy-metadata=rich --copy-metadata=pyglet --copy-metadata=moderngl --copy-metadata=glcontext --exclude-module=playwright --exclude-module=playwright.sync_api --exclude-module=playwright.async_api --exclude-module=comfy --exclude-module=comfyui --exclude-module=blender --exclude-module=godot --exclude-module=o3de --exclude-module=game_models --exclude-module=PluginManager --exclude-module=blender_plugin --exclude-module=godot_plugin --exclude-module=o3de_plugin --exclude-module=game_models_plugin -c "import sys; sys.exit(0 if __import__('reverie').__name__ else 1)" "reverie/__main__.py"
set "PYTHONWARNINGS="
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

if not exist "%PYI_DIST_DIR%\reverie.exe" (
    echo [ERROR] Executable not found at %PYI_DIST_DIR%\reverie.exe
    set "BUILD_EXIT_CODE=1"
    goto finish
)

for %%A in ("%PYI_DIST_DIR%\reverie.exe") do set "SIZE=%%~zA"
set /a "SIZE_MB=SIZE/1048576"

echo.
echo ===============================================================
echo   BUILD SUCCESSFUL
echo ===============================================================
echo   Output: %PYI_DIST_DIR%\reverie.exe
echo   Work:   %PYI_WORK_DIR%
echo   Temp:   %LOCAL_TEMP_DIR%
echo   Size:   ~%SIZE_MB% MB

if "%RUN_EXE_TEST%"=="1" (
    echo.
    echo Running executable sanity check...
    "%PYI_DIST_DIR%\reverie.exe" --version
    if %ERRORLEVEL% neq 0 echo [WARNING] Executable sanity check returned a non-zero exit code.
)

:finish
pause
exit /b %BUILD_EXIT_CODE%
