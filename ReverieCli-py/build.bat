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
set "SHARED_COMFY_DIR=%REPO_ROOT%\comfy"
set "SHARED_PLUGINS_DIR=%REPO_ROOT%\plugins"
set "EXE_NAME=reverie"
set "BUNDLE_RES_DIR=%BUILD_DIR%\bundle_resources"
set "LOCAL_BUILD_ROOT=%ROOT_DIR%\build"
set "LOCAL_TEMP_DIR=%LOCAL_BUILD_ROOT%\temp"
set "LOCAL_PIP_CACHE=%LOCAL_BUILD_ROOT%\pip-cache"
set "PYI_CONFIG_DIR=%LOCAL_BUILD_ROOT%\pyinstaller-config"
set "PYI_WORK_DIR=%BUILD_DIR%\pyinstaller"
set "PYI_DIST_DIR=%OUTPUT_DIR%"
set "PYI_SPEC_DIR=%BUILD_DIR%\pyinstaller-spec"
set "BLENDER_ARCHIVE_NAME=blender-5.1.1-windows-x64.zip"
set "BLENDER_ARCHIVE_SOURCE="
set "RECREATE_VENV=0"
set "RUN_EXE_TEST=0"
set "FORCE_CLEAN=0"
set "FORCE_DEPS=0"
set "FORCE_BROWSER=0"
set "FORCE_PLUGINS=0"
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
if /I "%~1"=="--clean" set "FORCE_CLEAN=1"
if /I "%~1"=="--reinstall-deps" set "FORCE_DEPS=1"
if /I "%~1"=="--refresh-browser" set "FORCE_BROWSER=1"
if /I "%~1"=="--rebuild-plugins" set "FORCE_PLUGINS=1"
shift
goto parse_args

:args_done

echo.
echo ===============================================================
echo   Reverie Cli Build
echo ===============================================================
echo   Python root: %ROOT_DIR%
echo   Repository root: %REPO_ROOT%
echo   Shared resources: %SHARED_COMFY_DIR%, %SHARED_PLUGINS_DIR%

where %PYTHON_EXE% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python executable not found in PATH.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

for /f %%V in ('%PYTHON_EXE% -c "import platform; print(platform.python_version())"') do set "PY_VERSION=%%V"
echo [1/6] Python detected: %PY_VERSION%

echo.
echo [2/6] Preparing virtual environment...
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" >nul 2>&1
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%" >nul 2>&1
if not exist "%LOCAL_BUILD_ROOT%" mkdir "%LOCAL_BUILD_ROOT%" >nul 2>&1
if not exist "%LOCAL_TEMP_DIR%" mkdir "%LOCAL_TEMP_DIR%" >nul 2>&1
if not exist "%LOCAL_PIP_CACHE%" mkdir "%LOCAL_PIP_CACHE%" >nul 2>&1
if not exist "%PYI_CONFIG_DIR%" mkdir "%PYI_CONFIG_DIR%" >nul 2>&1
set "NEED_DEPS=0"
if exist "%VENV_DIR%\Scripts\activate.bat" (
    if "%RECREATE_VENV%"=="1" (
        echo       Recreating %VENV_DIR%...
        rmdir /s /q "%VENV_DIR%"
        %PYTHON_EXE% -m venv "%VENV_DIR%"
        set "NEED_DEPS=1"
    ) else (
        echo       Using existing %VENV_DIR%
    )
) else (
    echo       Creating %VENV_DIR%...
    %PYTHON_EXE% -m venv "%VENV_DIR%"
    set "NEED_DEPS=1"
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
echo [3/6] Installing build dependencies...
set "DEPS_STAMP=%LOCAL_BUILD_ROOT%\deps.stamp"
set "CURRENT_DEPS_STAMP="
for /f "delims=" %%S in ('python -c "import hashlib,pathlib,sys; h=hashlib.sha256(); [h.update(p.read_bytes()) for p in (pathlib.Path('requirements.txt'),pathlib.Path('setup.py')) if p.exists()]; h.update(sys.version.encode()); print(h.hexdigest())"') do set "CURRENT_DEPS_STAMP=%%S"
if "%FORCE_DEPS%"=="1" set "NEED_DEPS=1"
if not defined CURRENT_DEPS_STAMP set "NEED_DEPS=1"
if exist "%DEPS_STAMP%" (
    set "STORED_DEPS_STAMP="
    set /p STORED_DEPS_STAMP=<"%DEPS_STAMP%"
    if not "!CURRENT_DEPS_STAMP!"=="!STORED_DEPS_STAMP!" set "NEED_DEPS=1"
) else (
    set "NEED_DEPS=1"
)
if "%NEED_DEPS%"=="1" (
    echo       Installing or refreshing Python dependencies...
    python -m pip install --disable-pip-version-check --upgrade pyinstaller pillow
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller or Pillow.
        set "BUILD_EXIT_CODE=1"
        goto finish
    )

    python -m pip install --disable-pip-version-check -e .
    if errorlevel 1 (
        echo [ERROR] Failed to install Reverie into the build environment.
        set "BUILD_EXIT_CODE=1"
        goto finish
    )
    >"%DEPS_STAMP%" echo !CURRENT_DEPS_STAMP!
) else (
    echo       Dependencies unchanged; reusing the existing build environment.
)

echo.
echo [4/6] Preparing bundled resources...
if not exist "%SHARED_COMFY_DIR%\generate_image.py" (
    echo [ERROR] Missing required file: %SHARED_COMFY_DIR%\generate_image.py
    set "BUILD_EXIT_CODE=1"
    goto finish
)
if not exist "%SHARED_COMFY_DIR%\embedded_comfy.b64" (
    echo [ERROR] Missing required file: %SHARED_COMFY_DIR%\embedded_comfy.b64
    set "BUILD_EXIT_CODE=1"
    goto finish
)

if not exist "%BUNDLE_RES_DIR%\comfy" mkdir "%BUNDLE_RES_DIR%\comfy" >nul 2>&1
if not exist "%BUNDLE_RES_DIR%\browser\ms-playwright" mkdir "%BUNDLE_RES_DIR%\browser\ms-playwright" >nul 2>&1
xcopy /D /Y "%SHARED_COMFY_DIR%\generate_image.py" "%BUNDLE_RES_DIR%\comfy\generate_image.py" >nul
xcopy /D /Y "%SHARED_COMFY_DIR%\embedded_comfy.b64" "%BUNDLE_RES_DIR%\comfy\embedded_comfy.b64" >nul
set "PLAYWRIGHT_BROWSERS_PATH=%BUNDLE_RES_DIR%\browser\ms-playwright"
set "NEED_BROWSER=0"
if "%FORCE_BROWSER%"=="1" set "NEED_BROWSER=1"
if "%NEED_BROWSER%"=="0" python -c "from pathlib import Path; raise SystemExit(0 if any(Path(r'%PLAYWRIGHT_BROWSERS_PATH%').rglob('chrome.exe')) else 1)" >nul 2>&1
if errorlevel 1 set "NEED_BROWSER=1"
if "%NEED_BROWSER%"=="1" python -m playwright install chromium --no-shell
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install embedded Chromium for Browser Controler.
    set "BUILD_EXIT_CODE=1"
    goto finish
)
python -c "from pathlib import Path; raise SystemExit(0 if any(Path(r'%PLAYWRIGHT_BROWSERS_PATH%').rglob('chrome.exe')) else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Embedded Chromium install did not produce chrome.exe.
    set "BUILD_EXIT_CODE=1"
    goto finish
)
set "REVERIE_BUNDLE_RES_DIR=%BUNDLE_RES_DIR%"
echo       Bundled resources: %REVERIE_BUNDLE_RES_DIR%\comfy, %REVERIE_BUNDLE_RES_DIR%\browser
if exist "%REPO_ROOT%\%BLENDER_ARCHIVE_NAME%" set "BLENDER_ARCHIVE_SOURCE=%REPO_ROOT%\%BLENDER_ARCHIVE_NAME%"
if not defined BLENDER_ARCHIVE_SOURCE if exist "%ROOT_DIR%\%BLENDER_ARCHIVE_NAME%" set "BLENDER_ARCHIVE_SOURCE=%ROOT_DIR%\%BLENDER_ARCHIVE_NAME%"
if not defined BLENDER_ARCHIVE_SOURCE if exist "%SHARED_PLUGINS_DIR%\blender\%BLENDER_ARCHIVE_NAME%" set "BLENDER_ARCHIVE_SOURCE=%SHARED_PLUGINS_DIR%\blender\%BLENDER_ARCHIVE_NAME%"
if defined BLENDER_ARCHIVE_SOURCE (
    echo       Blender portable archive build input: %BLENDER_ARCHIVE_SOURCE%
    set "BUILD_BLENDER_PLUGIN=0"
    if "%FORCE_PLUGINS%"=="1" set "BUILD_BLENDER_PLUGIN=1"
    if "%BUILD_BLENDER_PLUGIN%"=="0" python -c "from pathlib import Path; o=Path(r'%SHARED_PLUGINS_DIR%\blender\dist\reverie-blender.exe'); i=[Path(r'%SHARED_PLUGINS_DIR%\blender\plugin.py'),Path(r'%SHARED_PLUGINS_DIR%\blender\plugin.json'),Path(r'%BLENDER_ARCHIVE_SOURCE%')]; raise SystemExit(0 if o.is_file() and all(not p.is_file() or o.stat().st_mtime >= p.stat().st_mtime for p in i) else 1)" >nul 2>&1
    if errorlevel 1 set "BUILD_BLENDER_PLUGIN=1"
    if "%BUILD_BLENDER_PLUGIN%"=="1" (
        echo       Building official Blender plugin with embedded portable archive...
        call "%SHARED_PLUGINS_DIR%\blender\build.bat"
        if errorlevel 1 (
            echo [ERROR] Failed to build Blender plugin executable.
            set "BUILD_EXIT_CODE=1"
            goto finish
        )
    ) else (
        echo       Reusing up-to-date Blender plugin executable.
    )
    python -c "from reverie.config import get_app_root; from reverie.plugin.runtime_manager import RuntimePluginManager; manager=RuntimePluginManager(get_app_root()); result=manager.install_source_plugin('blender', overwrite=True); location=result.get('target_path') or result.get('target_dir'); mode=result.get('install_mode') or 'directory-sync'; print(f'      Blender plugin installed ({mode}): {location}'); raise SystemExit(0 if result.get('success') else 1)"
    if errorlevel 1 (
        echo [ERROR] Failed to install Blender plugin into dist runtime depot.
        set "BUILD_EXIT_CODE=1"
        goto finish
    )
) else (
    echo       Blender portable archive not found. Official Blender plugin build skipped.
)

if exist "%SHARED_PLUGINS_DIR%\game_models\plugin.py" (
    set "BUILD_GAME_MODELS_PLUGIN=0"
    if "%FORCE_PLUGINS%"=="1" set "BUILD_GAME_MODELS_PLUGIN=1"
    if "%BUILD_GAME_MODELS_PLUGIN%"=="0" python -c "from pathlib import Path; o=Path(r'%SHARED_PLUGINS_DIR%\game_models\dist\reverie-game-models.exe'); i=[Path(r'%SHARED_PLUGINS_DIR%\game_models\plugin.py'),Path(r'%SHARED_PLUGINS_DIR%\game_models\plugin.json')]; raise SystemExit(0 if o.is_file() and all(not p.is_file() or o.stat().st_mtime >= p.stat().st_mtime for p in i) else 1)" >nul 2>&1
    if errorlevel 1 set "BUILD_GAME_MODELS_PLUGIN=1"
    if "%BUILD_GAME_MODELS_PLUGIN%"=="1" (
        echo       Building official Game Models plugin...
        call "%SHARED_PLUGINS_DIR%\game_models\build.bat"
        if errorlevel 1 (
            echo [ERROR] Failed to build Game Models plugin executable.
            set "BUILD_EXIT_CODE=1"
            goto finish
        )
    ) else (
        echo       Reusing up-to-date Game Models plugin executable.
    )
    python -c "from reverie.config import get_app_root; from reverie.plugin.runtime_manager import RuntimePluginManager; manager=RuntimePluginManager(get_app_root()); result=manager.install_source_plugin('game_models', overwrite=True); location=result.get('target_path') or result.get('target_dir'); mode=result.get('install_mode') or 'directory-sync'; print(f'      Game Models plugin installed ({mode}): {location}'); raise SystemExit(0 if result.get('success') else 1)"
    if errorlevel 1 (
        echo [ERROR] Failed to install Game Models plugin into dist runtime depot.
        set "BUILD_EXIT_CODE=1"
        goto finish
    )
)

echo.
echo [5/6] Resolving optional ffmpeg and icon...
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
echo [6/6] Building executable...
set "PYI_CLEAN_ARG="
if "%FORCE_CLEAN%"=="1" (
    set "PYI_CLEAN_ARG=--clean"
    if exist "%PYI_WORK_DIR%" rmdir /s /q "%PYI_WORK_DIR%"
    if exist "%PYI_SPEC_DIR%" rmdir /s /q "%PYI_SPEC_DIR%"
)
if exist "%PYI_DIST_DIR%\%EXE_NAME%.exe" del /f /q "%PYI_DIST_DIR%\%EXE_NAME%.exe" >nul 2>&1
set "PYI_PYTHONWARNINGS=ignore:Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.:UserWarning"
set "PYTHONWARNINGS=%PYI_PYTHONWARNINGS%"
PyInstaller --noconfirm %PYI_CLEAN_ARG% --distpath "%PYI_DIST_DIR%" --workpath "%PYI_WORK_DIR%" reverie.spec
set "PYTHONWARNINGS="
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    set "BUILD_EXIT_CODE=1"
    goto finish
)

if not exist "%PYI_DIST_DIR%\%EXE_NAME%.exe" (
    echo [ERROR] Executable not found at %PYI_DIST_DIR%\%EXE_NAME%.exe
    set "BUILD_EXIT_CODE=1"
    goto finish
)

for %%A in ("%PYI_DIST_DIR%\%EXE_NAME%.exe") do set "SIZE=%%~zA"
set /a "SIZE_MB=SIZE/1048576"

echo.
echo ===============================================================
echo   BUILD SUCCESSFUL
echo ===============================================================
echo   Output: %PYI_DIST_DIR%\%EXE_NAME%.exe
echo   Work:   %PYI_WORK_DIR%
echo   Temp:   %LOCAL_TEMP_DIR%
echo   Size:   ~%SIZE_MB% MB

if "%RUN_EXE_TEST%"=="1" (
    echo.
    echo Running executable sanity check...
    "%PYI_DIST_DIR%\%EXE_NAME%.exe" --version
    if %ERRORLEVEL% neq 0 echo [WARNING] Executable sanity check returned a non-zero exit code.
)

:finish
pause
exit /b %BUILD_EXIT_CODE%
