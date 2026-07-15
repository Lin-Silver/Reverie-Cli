#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REPO_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$SCRIPT_DIR/venv"
OUTPUT_DIR="$REPO_ROOT/dist"
BUILD_DIR="$SCRIPT_DIR/build"
SHARED_COMFY_DIR="$REPO_ROOT/comfy"
SHARED_PLUGINS_DIR="$REPO_ROOT/plugins"
BUNDLE_RES_DIR="$BUILD_DIR/bundle_resources"
LOCAL_TEMP_DIR="$BUILD_DIR/temp"
LOCAL_PIP_CACHE="$BUILD_DIR/pip-cache"
PYI_WORK_DIR="$BUILD_DIR/pyinstaller"
EXE_NAME="reverie"

RECREATE_VENV=0
RUN_EXE_TEST=0
FORCE_CLEAN=0
FORCE_DEPS=0
FORCE_BROWSER=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --recreate-venv) RECREATE_VENV=1 ;;
        --reuse-venv)   RECREATE_VENV=0 ;;
        --test-exe)     RUN_EXE_TEST=1 ;;
        --clean)        FORCE_CLEAN=1 ;;
        --reinstall-deps) FORCE_DEPS=1 ;;
        --refresh-browser) FORCE_BROWSER=1 ;;
        --rebuild-plugins) : ;; # Kept for parity with build.bat.
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

echo ""
echo "==============================================================="
echo "  Reverie Cli Build"
echo "==============================================================="
echo "  Python root: $SCRIPT_DIR"
echo "  Repository root: $REPO_ROOT"
echo "  Shared resources: $SHARED_COMFY_DIR, $SHARED_PLUGINS_DIR"

if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python3 not found in PATH."
    exit 1
fi

PY_VERSION=$(python3 -c "import platform; print(platform.python_version())")
echo "[1/6] Python detected: $PY_VERSION"

python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" || {
    echo "[ERROR] Python 3.10+ required."
    exit 1
}

mkdir -p "$OUTPUT_DIR" "$BUILD_DIR" "$LOCAL_TEMP_DIR" "$LOCAL_PIP_CACHE"

echo "[2/6] Preparing virtual environment..."
USE_VENV=true
NEED_DEPS=0
if [ -d "$VENV_DIR" ] && [ "$RECREATE_VENV" = "1" ]; then
    echo "      Recreating $VENV_DIR ..."
    rm -rf "$VENV_DIR"
    NEED_DEPS=1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "      Creating $VENV_DIR ..."
    python3 -m venv "$VENV_DIR" 2>/dev/null || {
        echo "      [WARN] python3-venv not available, installing dependencies system-wide (user mode)."
        USE_VENV=false
    }
    NEED_DEPS=1
fi

if [ "$USE_VENV" = "true" ]; then
    source "$VENV_DIR/bin/activate"
    PIP_CMD="pip"
    PYTHON_CMD="python"
else
    PIP_CMD="pip install --user --break-system-packages"
    PYTHON_CMD="python3"
fi

echo "[3/6] Installing build dependencies..."
DEPS_STAMP="$BUILD_DIR/deps.stamp"
CURRENT_DEPS_STAMP=$($PYTHON_CMD -c "import hashlib,pathlib,sys; h=hashlib.sha256(); [h.update(p.read_bytes()) for p in (pathlib.Path('requirements.txt'),pathlib.Path('setup.py')) if p.exists()]; h.update(sys.version.encode()); print(h.hexdigest())")
if [ "$FORCE_DEPS" = "1" ] || [ ! -s "$DEPS_STAMP" ] || [ "$(<"$DEPS_STAMP")" != "$CURRENT_DEPS_STAMP" ]; then
    NEED_DEPS=1
fi

if [ "$NEED_DEPS" = "1" ]; then
    echo "      Installing or refreshing Python dependencies..."
    if [ "$USE_VENV" = "true" ]; then
        pip install --disable-pip-version-check -e ".[build]" --quiet
    else
        $PIP_CMD -e ".[build]" 2>/dev/null || {
            # glcontext may fail to build without X11 headers; try installing deps manually
            $PIP_CMD -r requirements.txt 2>/dev/null || true
            $PIP_CMD -e ".[build]" 2>/dev/null || true
        }
    fi
    printf '%s\n' "$CURRENT_DEPS_STAMP" > "$DEPS_STAMP"
else
    echo "      Dependencies unchanged; reusing the existing build environment."
fi

echo "[4/6] Preparing bundled resources..."
mkdir -p "$BUNDLE_RES_DIR/comfy" "$BUNDLE_RES_DIR/browser/ms-playwright"

if [ ! -f "$SHARED_COMFY_DIR/generate_image.py" ]; then
    echo "[ERROR] Missing: $SHARED_COMFY_DIR/generate_image.py"
    exit 1
fi
if [ ! -f "$SHARED_COMFY_DIR/embedded_comfy.b64" ]; then
    echo "[ERROR] Missing: $SHARED_COMFY_DIR/embedded_comfy.b64"
    exit 1
fi

cp -u "$SHARED_COMFY_DIR/generate_image.py" "$BUNDLE_RES_DIR/comfy/generate_image.py"
cp -u "$SHARED_COMFY_DIR/embedded_comfy.b64" "$BUNDLE_RES_DIR/comfy/embedded_comfy.b64"
export PLAYWRIGHT_BROWSERS_PATH="$BUNDLE_RES_DIR/browser/ms-playwright"
CHROMIUM_EXE=$(find "$PLAYWRIGHT_BROWSERS_PATH" -type f \( -name chrome -o -name chrome.exe \) -print -quit 2>/dev/null)
NEED_BROWSER=0
if [ "$FORCE_BROWSER" = "1" ] || [ -z "$CHROMIUM_EXE" ]; then
    NEED_BROWSER=1
fi
if [ "$NEED_BROWSER" = "1" ]; then
    $PYTHON_CMD -m playwright install chromium --no-shell 2>/dev/null || true
    CHROMIUM_EXE=$(find "$PLAYWRIGHT_BROWSERS_PATH" -type f \( -name chrome -o -name chrome.exe \) -print -quit 2>/dev/null)
else
    echo "      Reusing embedded Chromium."
fi
if [ -z "$CHROMIUM_EXE" ]; then
    echo "      [WARN] Embedded Chromium install failed. Browser tool may not work at runtime."
fi
export REVERIE_BUNDLE_RES_DIR="$BUNDLE_RES_DIR"
echo "      Bundled resources: $REVERIE_BUNDLE_RES_DIR/comfy"

echo "[5/6] Resolving optional ffmpeg..."
FFMPEG_PATH=""
if [ -n "${REVERIE_FFMPEG_PATH:-}" ] && [ -f "$REVERIE_FFMPEG_PATH" ]; then
    FFMPEG_PATH="$REVERIE_FFMPEG_PATH"
elif command -v ffmpeg &>/dev/null; then
    FFMPEG_PATH=$(command -v ffmpeg)
fi
if [ -n "$FFMPEG_PATH" ]; then
    echo "      ffmpeg: $FFMPEG_PATH"
else
    echo "      ffmpeg not found. Runtime will use external ffmpeg if needed."
fi

ICON_PNG="$SCRIPT_DIR/reverie.png"
if [ -f "$ICON_PNG" ]; then
    $PYTHON_CMD "$SCRIPT_DIR/scripts/generate_reverie_icons.py" --source "$ICON_PNG" "$SCRIPT_DIR/reverie.ico" || true
    echo "      icon: $ICON_PNG"
else
    echo "      icon not found. Build will continue without a custom icon."
fi

echo "[6/6] Building executable..."
PYI_CLEAN_ARG=()
if [ "$FORCE_CLEAN" = "1" ]; then
    rm -rf "$PYI_WORK_DIR"
    PYI_CLEAN_ARG=(--clean)
fi

export TMP="$LOCAL_TEMP_DIR"
export TEMP="$LOCAL_TEMP_DIR"
export TMPDIR="$LOCAL_TEMP_DIR"
export PIP_CACHE_DIR="$LOCAL_PIP_CACHE"
export PYTHONWARNINGS="ignore:Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.:UserWarning"

$PYTHON_CMD -m PyInstaller --noconfirm "${PYI_CLEAN_ARG[@]}" --distpath "$OUTPUT_DIR" --workpath "$PYI_WORK_DIR" reverie.spec

export PYTHONWARNINGS=""

if [ ! -f "$OUTPUT_DIR/$EXE_NAME" ]; then
    echo "[ERROR] Executable not found at $OUTPUT_DIR/$EXE_NAME"
    exit 1
fi

SIZE=$(stat -c%s "$OUTPUT_DIR/$EXE_NAME" 2>/dev/null || stat -f%z "$OUTPUT_DIR/$EXE_NAME" 2>/dev/null)
SIZE_MB=$(( SIZE / 1048576 ))

echo ""
echo "==============================================================="
echo "  BUILD SUCCESSFUL"
echo "==============================================================="
echo "  Output: $OUTPUT_DIR/$EXE_NAME"
echo "  Work:   $PYI_WORK_DIR"
echo "  Temp:   $LOCAL_TEMP_DIR"
echo "  Size:   ~${SIZE_MB}MB"

if [ "$RUN_EXE_TEST" = "1" ]; then
    echo ""
    echo "Running executable sanity check..."
    "$OUTPUT_DIR/$EXE_NAME" --version || echo "[WARNING] Sanity check returned non-zero."
fi
