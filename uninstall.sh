#!/usr/bin/env bash
# Undo what install.sh did. Optionally wipes the Mongo volume with --purge.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run as root: sudo bash uninstall.sh"; exit 1; }

PURGE=0
for a in "$@"; do
    [[ "$a" == "--purge" ]] && PURGE=1
done

INSTALL_DIR="${INSTALL_DIR:-/opt/dmr-tracker}"

echo "==> Stopping services…"
systemctl disable --now dmr-backend.service 2>/dev/null || true
rm -f /etc/systemd/system/dmr-backend.service
systemctl daemon-reload

echo "==> Removing nginx site…"
rm -f /etc/nginx/sites-enabled/dmr-tracker /etc/nginx/sites-available/dmr-tracker
systemctl reload nginx 2>/dev/null || true

echo "==> Stopping MongoDB container…"
docker stop dmr-mongo 2>/dev/null || true
docker rm   dmr-mongo 2>/dev/null || true
if [[ $PURGE -eq 1 ]]; then
    docker volume rm dmr-mongo-data 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
    echo "==> Purged $INSTALL_DIR and Mongo data volume"
else
    echo "    (keeping $INSTALL_DIR and Mongo data - rerun with --purge to wipe)"
fi

echo "==> Firewall rules for 62031/udp + 80/tcp left in place."
echo "Done."
