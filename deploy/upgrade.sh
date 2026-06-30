#!/usr/bin/env bash
# Pull latest code and restart the service with zero manual steps.
# Run as root (or a user with sudo access to systemctl).
set -euo pipefail

APP_DIR=/srv/indexcards
APP_USER=indexcards

echo "==> Pulling latest code"
git -C "$APP_DIR" pull

echo "==> Installing/updating Python dependencies"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Fixing ownership"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Restarting service"
systemctl restart indexcards

echo "==> Done. Service status:"
systemctl status indexcards --no-pager -l
