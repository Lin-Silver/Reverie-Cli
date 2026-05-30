#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==============================================================="
echo "  Reverie Cli Install"
echo "==============================================================="

if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python3 is not installed. Please install Python 3.10+ first."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[1/3] Python detected: $PY_VERSION"

if [[ $(echo "$PY_VERSION" | cut -d. -f1) -lt 3 ]] || { [[ $(echo "$PY_VERSION" | cut -d. -f1) -eq 3 ]] && [[ $(echo "$PY_VERSION" | cut -d. -f2) -lt 10 ]]; }; then
    echo "[ERROR] Python 3.10+ is required (found $PY_VERSION)"
    exit 1
fi

echo "[2/3] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[3/3] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "==============================================================="
echo "  INSTALLATION SUCCESSFUL"
echo "==============================================================="
echo "  To activate: source venv/bin/activate"
echo "  To run:      python -m reverie"
echo ""
