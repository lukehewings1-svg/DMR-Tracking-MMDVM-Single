#!/usr/bin/env bash
# Installs the DMR818 voice gateway on Raspberry Pi OS (run with sudo).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

apt-get update
apt-get install -y python3-serial python3-websockets alsa-utils

install -m 755 "$DIR/dmr818_gateway.py" /usr/local/bin/dmr818_gateway.py
if [[ ! -f /etc/dmr818-gateway.ini ]]; then
  install -m 600 "$DIR/gateway.example.ini" /etc/dmr818-gateway.ini
  echo ">>> Edit /etc/dmr818-gateway.ini (server_url, gateway_key, radio_id, audio_device)"
fi

cat > /etc/systemd/system/dmr818-gateway.service <<'EOF'
[Unit]
Description=DMR Tracker DMR818 voice gateway
After=network-online.target sound.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/dmr818_gateway.py /etc/dmr818-gateway.ini
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable dmr818-gateway
echo ">>> Start with: sudo systemctl start dmr818-gateway   (logs: journalctl -u dmr818-gateway -f)"
