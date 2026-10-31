#!/usr/bin/env bash
set -euo pipefail

# Match the pinned Playwright driver instead of the runner's unrelated browser.
python -m playwright install --with-deps chromium

# Ubuntu restricts user namespaces for downloaded browser binaries. Allow only
# this CI browser to create its sandbox; keep Chromium sandboxing enabled.
# https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md
if [[ -f /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]]; then
  browser_path=$(python -c 'from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print(p.chromium.executable_path); p.stop()')
  sudo tee /etc/apparmor.d/reverie-ci-chromium >/dev/null <<EOF
abi <abi/4.0>,
include <tunables/global>
profile reverie-ci-chromium "$browser_path" flags=(unconfined) {
  userns,
}
EOF
  sudo apparmor_parser -r /etc/apparmor.d/reverie-ci-chromium
fi
