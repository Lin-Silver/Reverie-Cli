#!/bin/sh
set -eu
ln -sfn /opt/Reverie/reverie /usr/bin/reverie
ln -sfn /opt/Reverie/reverieui /usr/bin/reverieui
chown root:root /opt/Reverie/chrome-sandbox
chmod 4755 /opt/Reverie/chrome-sandbox
