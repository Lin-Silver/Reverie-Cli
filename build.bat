@echo off
REM ============================================================
REM Reverie Cli - Build Script
REM Creates a standalone Windows executable using PyInstaller
REM ============================================================

chcp 65001 >nul

setlocal enabledelayedexpansion

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║          Reverie Cli - Build Script                           ║
echo ║          Building standalone Windows executable               ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

REM Configuration
set "VENV_DIR=venv"
set "OUTPUT_DIR=dist"
set "BUILD_DIR=build"
set "EXE_NAME=reverie"
set "BUNDLE_RES_DIR=%BUILD_DIR%\bundle_resources"
set "TMP_BUILD_BASE=%TEMP%\reverie_pyi"
set "PYI_WORK_DIR=%TMP_BUILD_BASE%\work_%RANDOM%_%RANDOM%"
set "PYI_DIST_DIR=%TMP_BUILD_BASE%\dist_%RANDOM%_%RANDOM%"

REM Check if virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at %VENV_DIR%
    echo Please run: python -m venv venv
    exit /b 1
)

REM Activate virtual environment
echo [1/6] Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

REM Install/upgrade PyInstaller
echo.
echo [2/6] Installing PyInstaller and dependencies...
py -m pip install --upgrade pyinstaller pillow >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller
    exit /b 1
)
echo       PyInstaller and Pillow installed successfully

REM Check dependencies
echo.
echo [3/6] Checking dependencies...
py -m pip install -e . >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Some dependencies may be missing
)

if not exist "%TMP_BUILD_BASE%" mkdir "%TMP_BUILD_BASE%" >nul 2>&1

REM Prepare bundled Comfy resources (embedded into exe, no Comfy folder needed beside exe)
echo.
echo [4/6] Preparing bundled Comfy resources...
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

REM Build with PyInstaller using spec file
echo.
echo [5/6] Building executable with PyInstaller...
echo       This may take a few minutes...
echo       Work path: %PYI_WORK_DIR%
echo       Temp dist: %PYI_DIST_DIR%
echo.

py -m PyInstaller --noconfirm --clean --distpath "%PYI_DIST_DIR%" --workpath "%PYI_WORK_DIR%" reverie.spec

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed!
    exit /b 1
)

REM Check if executable was created in temp dist
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
    echo [WARNING] Built successfully, but failed to overwrite %OUTPUT_DIR%\%EXE_NAME%.exe
    echo          Most likely the target exe is running or locked by another process.
    echo          New exe is available at:
    echo          %PYI_DIST_DIR%\%EXE_NAME%.exe
    exit /b 0
)

echo.
echo [6/6] Build artifact validation...
echo       Executable found: %OUTPUT_DIR%\%EXE_NAME%.exe

REM Get file size
for %%A in ("%OUTPUT_DIR%\%EXE_NAME%.exe") do set "SIZE=%%~zA"
set /a "SIZE_MB=SIZE/1048576"

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║                    BUILD SUCCESSFUL!                          ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo   Output: %OUTPUT_DIR%\%EXE_NAME%.exe
echo   Size:   ~%SIZE_MB% MB
echo.
echo   To run: %OUTPUT_DIR%\%EXE_NAME%.exe
echo   Or copy %EXE_NAME%.exe to any directory and run it.
echo.

REM Optional: Test the executable
set /p "TEST=Test the executable now? (y/n): "
if /i "%TEST%"=="y" (
    echo.
    echo Testing executable...
    "%OUTPUT_DIR%\%EXE_NAME%.exe" --version
)

echo.
echo Done!
endlocal
