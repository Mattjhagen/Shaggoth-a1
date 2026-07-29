#!/usr/bin/env bash
# Install Shaggoth on the R510 (Debian/Ubuntu) and register the systemd service.
# Run once as root:  sudo bash scripts/install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_FILE="$REPO_DIR/deploy/shaggoth.service"
DEST="/etc/systemd/system/shaggoth.service"
INSTALL_USER="${SUDO_USER:-matt}"

echo "==> Installing Python dependencies"
pip3 install -e "$REPO_DIR[openai]" --break-system-packages

echo "==> Installing systemd service"
install -m 644 "$SERVICE_FILE" "$DEST"

# Patch the user and paths if this machine's home differs
sed -i "s|User=matt|User=$INSTALL_USER|g" "$DEST"
sed -i "s|/home/matt/Shaggoth-a1|$REPO_DIR|g" "$DEST"

echo "==> Reloading systemd"
systemctl daemon-reload
systemctl enable shaggoth
systemctl restart shaggoth
systemctl status shaggoth --no-pager

echo ""
echo "Done. Logs: journalctl -u shaggoth -f"
echo "Env vars: edit $REPO_DIR/.env and run: systemctl restart shaggoth"
