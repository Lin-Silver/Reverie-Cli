#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[ERROR] build.sh produces the Linux x64 packages and must run on Linux."
  exit 1
fi

command -v node >/dev/null || { echo "[ERROR] Node.js is required."; exit 1; }
command -v npm >/dev/null || { echo "[ERROR] npm is required."; exit 1; }

"$REPO_ROOT/ReverieCli-py/build.sh" --reuse-venv --test-exe
cd "$SCRIPT_DIR"
if ! npm ci --fetch-retries=0 --fetch-timeout=15000; then
  echo "[WARN] npm ci failed with the current user npm configuration." >&2
  echo "[WARN] Retrying without the user-level .npmrc in case a local proxy is unavailable." >&2
  npm ci --userconfig=/dev/null
fi
export REVERIE_EXTERNAL_KERNEL_PATH="$REPO_ROOT/dist/reverie"
export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}"
npm run dist:linux

VERSION="$(node -p "require('./package.json').version")"
test -f "$SCRIPT_DIR/release/Reverie-$VERSION-linux-x64.AppImage"
test -f "$SCRIPT_DIR/release/Reverie-$VERSION-linux-x64.deb"
echo "[OK] Reverie $VERSION Linux CLI, AppImage, and deb are ready."
