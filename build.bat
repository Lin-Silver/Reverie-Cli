@echo off
REM ============================================================
REM Reverie Cli - Build Script
REM Creates a standalone Windows executable using PyInstaller
REM Python 3.14 compatible build workflow
REM ============================================================

chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ===============================================================
echo   Reverie Cli - Build Script
echo   Building standalone Windows executable
echo ===============================================================
echo.

REM Configuration
set "PYTHON_EXE=python"
set "VENV_DIR=venv"
set "OUTPUT_DIR=dist"
set "BUILD_DIR=build"
set "EXE_NAME=reverie"
set "BUNDLE_RES_DIR=%BUILD_DIR%\bundle_resources"
set "TMP_BUILD_BASE=%TEMP%\reverie_pyi"
set "PYI_WORK_DIR=%TMP_BUILD_BASE%\work_%RANDOM%_%RANDOM%"
set "PYI_DIST_DIR=%TMP_BUILD_BASE%\dist_%RANDOM%_%RANDOM%"
set "RECREATE_VENV=0"

if /I "%~1"=="--recreate-venv" (
    set "RECREATE_VENV=1"
)
if /I "%~1"=="--reuse-venv" (
    set "RECREATE_VENV=0"
)

REM Check Python availability
where %PYTHON_EXE% >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python executable not found in PATH.
    exit /b 1
)

for /f %%V in ('%PYTHON_EXE% -c "import platform; print(platform.python_version())"') do set "PY_VERSION=%%V"
echo [1/8] Python detected: %PY_VERSION%

REM Prepare virtual environment
echo.
echo [2/8] Preparing virtual environment...
if exist "%VENV_DIR%\Scripts\activate.bat" (
    if "%RECREATE_VENV%"=="1" (
        echo       Recreating clean venv...
        rmdir /s /q "%VENV_DIR%"
        %PYTHON_EXE% -m venv "%VENV_DIR%"
        if %ERRORLEVEL% neq 0 (
            echo [ERROR] Failed to create virtual environment.
            exit /b 1
        )
    ) else (
        echo       Using existing venv at %VENV_DIR%
    )
) else (
    echo       venv not found, creating one at %VENV_DIR%...
    %PYTHON_EXE% -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3.10+ is required for Reverie build.
    exit /b 1
)

REM Upgrade packaging stack
echo.
echo [3/8] Upgrading build tooling...
python -m pip install --upgrade pip setuptools wheel
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to upgrade pip/setuptools/wheel.
    exit /b 1
)

REM Install PyInstaller and project dependencies
echo.
echo [4/8] Installing PyInstaller and project dependencies...
python -m pip install --upgrade pyinstaller pillow
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller/Pillow.
    exit /b 1
)

python -m pip install --upgrade -e .
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install project dependencies.
    exit /b 1
)

python -m pip check
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Dependency resolution check failed.
    exit /b 1
)

REM Dependency health check (catches cp311/cp314 mismatch early)
echo.
echo [5/8] Running dependency health check...
python -c "import PIL._imaging, requests, bs4, openai, ddgs, yaml, pydantic_core._pydantic_core, pyglet, moderngl, glcontext; print('dependency_check_ok')"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Dependency health check failed.
    echo         Try deleting venv and re-running build.bat.
    exit /b 1
)

if not exist "%TMP_BUILD_BASE%" mkdir "%TMP_BUILD_BASE%" >nul 2>&1

REM Prepare bundled Comfy resources
echo.
echo [6/8] Preparing bundled Comfy resources...
if not exist "Comfy\generate_image.py" (
    echo [ERROR] Missing required file: Comfy\generate_image.py
    exit /b 1
)
if not exist "Comfy\embedded_comfy.b64" (
    echo [ERROR] Missing required file: Comfy\embedded_comfy.b64
    exit /b 1
)

if not exist "%BUNDLE_RES_DIR%\comfy" mkdir "%BUNDLE_RES_DIR%\comfy" >nul 2>&1
copy /Y "Comfy\generate_image.py" "%BUNDLE_RES_DIR%\comfy\generate_image.py" >nul
copy /Y "Comfy\embedded_comfy.b64" "%BUNDLE_RES_DIR%\comfy\embedded_comfy.b64" >nul
set "REVERIE_BUNDLE_RES_DIR=%cd%\%BUNDLE_RES_DIR%"
echo       Bundled resources: %REVERIE_BUNDLE_RES_DIR%\comfy

REM Prepare icon path for PyInstaller (prefer ico for Windows)
set "ICON_ICO=%cd%\reverie.ico"
set "ICON_PNG=%cd%\reverie.png"
set "GENERATED_ICO=%cd%\build\reverie.generated.ico"

if exist "%ICON_ICO%" (
    set "REVERIE_ICON_PATH=%ICON_ICO%"
) else (
    if exist "%ICON_PNG%" (
        python -c "from PIL import Image; Image.open(r'%ICON_PNG%').save(r'%GENERATED_ICO%', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
        if %ERRORLEVEL% equ 0 (
            set "REVERIE_ICON_PATH=%GENERATED_ICO%"
        ) else (
            echo [WARNING] Failed to convert PNG icon to ICO. Falling back to PNG.
            set "REVERIE_ICON_PATH=%ICON_PNG%"
        )
    )
)

if defined REVERIE_ICON_PATH (
    echo       Icon source: %REVERIE_ICON_PATH%
) else (
    echo [WARNING] No icon file found. Build will continue without a custom icon.
)

REM Build with PyInstaller
echo.
echo [7/8] Building executable with PyInstaller...
echo       This may take a few minutes...
echo       Work path: %PYI_WORK_DIR%
echo       Temp dist: %PYI_DIST_DIR%
echo.

set "PYI_PYTHONWARNINGS=ignore:Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.:UserWarning"
set "PYTHONWARNINGS=%PYI_PYTHONWARNINGS%"
PyInstaller --noconfirm --clean --distpath "%PYI_DIST_DIR%" --workpath "%PYI_WORK_DIR%" reverie.spec
set "PYTHONWARNINGS="
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed!
    exit /b 1
)

if not exist "%PYI_DIST_DIR%\%EXE_NAME%.exe" (
    echo.
    echo [ERROR] Executable not found at %PYI_DIST_DIR%\%EXE_NAME%.exe
    exit /b 1
)

REM Copy to final dist location
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" >nul 2>&1
copy /Y "%PYI_DIST_DIR%\%EXE_NAME%.exe" "%OUTPUT_DIR%\%EXE_NAME%.exe" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo [WARNING] Build succeeded, but failed to overwrite %OUTPUT_DIR%\%EXE_NAME%.exe
    echo          New executable path:
    echo          %PYI_DIST_DIR%\%EXE_NAME%.exe
    exit /b 0
)

echo.
echo [8/8] Build artifact validation...
echo       Executable found: %OUTPUT_DIR%\%EXE_NAME%.exe

for %%A in ("%OUTPUT_DIR%\%EXE_NAME%.exe") do set "SIZE=%%~zA"
set /a "SIZE_MB=SIZE/1048576"

echo.
echo ===============================================================
echo                    BUILD SUCCESSFUL!
echo ===============================================================
echo.
echo   Output: %OUTPUT_DIR%\%EXE_NAME%.exe
echo   Size:   ~%SIZE_MB% MB
echo.
echo   To run: %OUTPUT_DIR%\%EXE_NAME%.exe
echo.

set /p "TEST=Test the executable now? (y/n): "
if /i "%TEST%"=="y" (
    echo.
    echo Testing executable...
    "%OUTPUT_DIR%\%EXE_NAME%.exe" --version
)

echo.
echo Done!
endlocal
