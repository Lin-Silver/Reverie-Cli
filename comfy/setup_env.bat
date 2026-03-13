@echo off

REM Configuration
set "VENV_DIR=.venv"
set "PYTHON_BIN=python"
set "TORCH_VERSION=2.6.0"
set "TORCHAUDIO_VERSION=2.6.0"
set "TORCHVISION_VERSION=0.21.0"
set "CUDA_SUFFIX=cu128"

if not exist "%VENV_DIR%" (
    echo Creating virtual environment in %VENV_DIR%...
    %PYTHON_BIN% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment.& exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

python -m pip install --upgrade pip
pip install --extra-index-url "https://download.pytorch.org/whl/%CUDA_SUFFIX%" ^
    torch==%TORCH_VERSION% ^
    torchvision==%TORCHVISION_VERSION% ^
    torchaudio==%TORCHAUDIO_VERSION%
pip install diffusers>=0.29.0 transformers accelerate safetensors

REM Optional: install xformers only if a compatible wheel is available for your PyTorch/CUDA combo
REM pip install xformers==0.0.27.post2

pip install -r requirements.txt

for /f "delims=" %%i in ('python -c "import platform;print(platform.system().lower())"') do set "OS_NAME=%%i"

set "TTSFRD_DIR=models\vc\CosyVoice-ttsfrd"
set "TTSFRD_DEP=%TTSFRD_DIR%\ttsfrd_dependency-0.1-py3-none-any.whl"
set "TTSFRD_WHL=%TTSFRD_DIR%\ttsfrd-0.4.2-cp310-cp310-linux_x86_64.whl"

if /I "%OS_NAME%"=="windows" (
    echo Detected Windows platform. Installing platform-agnostic ttsfrd dependencies only.
    if exist "%TTSFRD_DEP%" (
        pip install "%TTSFRD_DEP%"
    ) else (
        echo WARNING: ttsfrd dependency wheel not found at %TTSFRD_DEP%.
    )
    echo No Windows-specific ttsfrd wheel provided; skipping ttsfrd core package.
) else (
    echo Detected %OS_NAME% platform. Installing ttsfrd packages for Linux.
    if exist "%TTSFRD_DEP%" (
        pip install "%TTSFRD_DEP%"
    ) else (
        echo WARNING: ttsfrd dependency wheel not found at %TTSFRD_DEP%.
    )
    if exist "%TTSFRD_WHL%" (
        pip install "%TTSFRD_WHL%"
    ) else (
        echo WARNING: ttsfrd wheel not found at %TTSFRD_WHL%.
    )
)

echo.
echo Environment setup complete.
echo To activate later, run: call %VENV_DIR%\Scripts\activate.bat
pause