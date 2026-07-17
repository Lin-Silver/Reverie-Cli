#!/bin/sh
set -eu
if [ "$(readlink /usr/bin/reverie 2>/dev/null || true)" = "/opt/Reverie/reverie" ]; then
  rm -f /usr/bin/reverie
fi
if [ "$(readlink /usr/bin/reverieui 2>/dev/null || true)" = "/opt/Reverie/reverieui" ]; then
  rm -f /usr/bin/reverieui
fi
