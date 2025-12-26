@echo off
REM ============================================================
REM Reverie Cli - Build Script
REM Creates a standalone Windows executable using PyInstaller
REM ============================================================

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

REM Check if virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at %VENV_DIR%
    echo Please run: python -m venv venv
    exit /b 1
)

REM Activate virtual environment
echo [1/5] Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

REM Install/upgrade PyInstaller
echo.
echo [2/5] Installing PyInstaller...
pip install --upgrade pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install PyInstaller
    exit /b 1
)
echo       PyInstaller installed successfully

REM Check dependencies
echo.
echo [3/5] Checking dependencies...
pip install -e . >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Some dependencies may be missing
)

:: Clean previous build
:: echo.
:: echo [4/5] Cleaning previous build...
:: if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%" 2>nul
:: if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%" 2>nul

REM Build with PyInstaller using spec file
echo.
echo [5/5] Building executable with PyInstaller...
echo       This may take a few minutes...
echo.

pyinstaller --noconfirm reverie.spec

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed!
    exit /b 1
)

REM Check if executable was created
if not exist "%OUTPUT_DIR%\%EXE_NAME%.exe" (
    echo.
    echo [ERROR] Executable not found at %OUTPUT_DIR%\%EXE_NAME%.exe
    exit /b 1
)

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
