#!/usr/bin/env bash
#
# DMR Tracker — one-shot installer for Raspberry Pi OS (64-bit) / Debian / Ubuntu.
#
# What it does:
#   1. Installs system deps (python3, node.js, yarn, nginx, ufw, docker for mongo).
#   2. Clones / uses this repo at /opt/dmr-tracker.
#   3. Runs MongoDB in a Docker container (survives reboots).
#   4. Generates a secure JWT_SECRET and writes backend/.env + frontend/.env.
#   5. Installs python + node dependencies, builds the frontend.
#   6. Installs a systemd unit for the backend.
#   7. Configures nginx as a reverse proxy on port 80 (serves the built frontend
#      and forwards /api + /api/ws to the backend).
#   8. Opens firewall ports 80/tcp (dashboard) and 62031/udp (MMDVM).
#   9. Prints the dashboard URL and admin login when finished.
#
# Usage (running from a checked-out repo):
#     sudo bash install.sh
#
# Usage (one-liner - repo URL required):
#     curl -fsSL https://<host>/install.sh | sudo REPO_URL=https://github.com/you/dmr-tracker.git bash
#
# Options via env vars:
#     INSTALL_DIR      default /opt/dmr-tracker
#     ADMIN_EMAIL      default admin@dmrtracker.app
#     ADMIN_PASSWORD   default admin123  (CHANGE THIS after first login)
#     HB_PASSWORD      default PASSWORD  (must match MMDVMHost DMR-Network password)
#     HB_BIND_PORT     default 62031
#     SERVER_DMR_ID    default 9990001
#     REPO_URL         if set + INSTALL_DIR is empty, git clones from here
#     DOMAIN           optional public hostname (e.g. dmr.example.com) - enables HTTPS via Let's Encrypt
#     LE_EMAIL         email for Let's Encrypt expiry notices (required with DOMAIN)
#     PUBLIC_HOST      host/IP the browser uses when no DOMAIN (default: first IP of this machine)
#     EMERGENT_LLM_KEY optional - enables overlay image uploads (object storage)
#
set -euo pipefail

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
c_red()  { printf "\033[1;31m%s\033[0m\n" "$*"; }
c_grn()  { printf "\033[1;32m%s\033[0m\n" "$*"; }
c_ylw()  { printf "\033[1;33m%s\033[0m\n" "$*"; }
c_blu()  { printf "\033[1;36m%s\033[0m\n" "$*"; }
step()   { c_blu "===> $*"; }
die()    { c_red "ERROR: $*"; exit 1; }

# --------------------------------------------------------------------------- #
# Pre-flight
# --------------------------------------------------------------------------- #
[[ $EUID -eq 0 ]] || die "Run as root:  sudo bash install.sh"

if [[ ! -f /etc/os-release ]]; then
    die "Cannot detect OS. This installer supports Debian / Raspberry Pi OS / Ubuntu."
fi
. /etc/os-release
case "$ID" in
    debian|raspbian|ubuntu) ;;
    *) c_ylw "Detected $ID - trying to proceed but only Debian/Raspberry Pi OS/Ubuntu are supported." ;;
esac

ARCH=$(uname -m)
case "$ARCH" in
    aarch64|arm64|x86_64|amd64) ;;
    armv7l|armv6l)
        c_ylw "You're on 32-bit ARM ($ARCH). MongoDB 5+ needs 64-bit."
        c_ylw "Consider flashing 64-bit Raspberry Pi OS on a Pi 4/5. Continuing anyway…"
        ;;
    *) c_ylw "Unknown architecture $ARCH - continuing anyway." ;;
esac

INSTALL_DIR="${INSTALL_DIR:-/opt/dmr-tracker}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@dmrtracker.app}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin123}"
HB_PASSWORD="${HB_PASSWORD:-PASSWORD}"
HB_BIND_PORT="${HB_BIND_PORT:-62031}"
SERVER_DMR_ID="${SERVER_DMR_ID:-9990001}"

# Detect the Pi's primary LAN IP so the frontend can talk to itself.
LAN_IP="${PUBLIC_HOST:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
[[ -n "$LAN_IP" ]] || LAN_IP="127.0.0.1"
DOMAIN="${DOMAIN:-}"
LE_EMAIL="${LE_EMAIL:-}"
EMERGENT_LLM_KEY="${EMERGENT_LLM_KEY:-}"
if [[ -n "$DOMAIN" ]]; then
    [[ -n "$LE_EMAIL" ]] || die "LE_EMAIL is required when DOMAIN is set."
    PUBLIC_URL="https://${DOMAIN}"
else
    PUBLIC_URL="http://${LAN_IP}"
fi

# --------------------------------------------------------------------------- #
# Locate the source tree
# --------------------------------------------------------------------------- #
step "Preparing source at $INSTALL_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

if [[ -d "$SCRIPT_DIR/backend" && -d "$SCRIPT_DIR/frontend" ]]; then
    # Running from inside the repo - copy it into INSTALL_DIR
    if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
        mkdir -p "$INSTALL_DIR"
        rsync -a --delete --exclude=".git" --exclude="node_modules" \
              --exclude="backend/.env" --exclude="frontend/.env" \
              --exclude="backend/.venv" --exclude="frontend/build" \
              "$SCRIPT_DIR"/ "$INSTALL_DIR"/
    fi
elif [[ -n "${REPO_URL:-}" ]]; then
    apt-get install -y git
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        git -C "$INSTALL_DIR" pull --ff-only
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
else
    die "No source detected in $SCRIPT_DIR and REPO_URL is not set."
fi

# --------------------------------------------------------------------------- #
# System packages
# --------------------------------------------------------------------------- #
step "Installing system packages (python, node, nginx, docker, ufw)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    ca-certificates curl gnupg lsb-release git rsync \
    python3 python3-venv python3-pip \
    nginx ufw

# Node.js 20 (NodeSource) — for both `yarn` and building the frontend
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | cut -c2- | cut -d. -f1)" -lt 18 ]]; then
    step "Installing Node.js 20 via NodeSource…"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

# Yarn 1.x
if ! command -v yarn >/dev/null 2>&1; then
    step "Installing yarn…"
    npm install -g yarn
fi

# Docker (used to run MongoDB reliably on any arch)
if ! command -v docker >/dev/null 2>&1; then
    step "Installing Docker…"
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

# --------------------------------------------------------------------------- #
# MongoDB via Docker
# --------------------------------------------------------------------------- #
step "Starting MongoDB (Docker container 'dmr-mongo')…"
if ! docker ps -a --format '{{.Names}}' | grep -q '^dmr-mongo$'; then
    docker run -d \
        --name dmr-mongo \
        --restart unless-stopped \
        -p 127.0.0.1:27017:27017 \
        -v dmr-mongo-data:/data/db \
        mongo:6
else
    docker start dmr-mongo >/dev/null || true
fi

# Wait for Mongo to accept connections
for i in $(seq 1 30); do
    if docker exec dmr-mongo mongosh --quiet --eval 'db.adminCommand({ ping: 1 }).ok' 2>/dev/null | grep -q 1; then
        break
    fi
    sleep 1
done

# --------------------------------------------------------------------------- #
# Configure .env files
# --------------------------------------------------------------------------- #
step "Writing backend/.env and frontend/.env…"
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

if [[ -f "$INSTALL_DIR/backend/.env" && -z "${RESET_ENV:-}" ]]; then
    c_ylw "Keeping existing backend/.env (set RESET_ENV=1 to regenerate)."
else
cat > "$INSTALL_DIR/backend/.env" <<EOF
MONGO_URL="mongodb://127.0.0.1:27017"
DB_NAME="dmr_tracker"
CORS_ORIGINS="*"
HB_BIND_HOST="0.0.0.0"
HB_BIND_PORT="${HB_BIND_PORT}"
HB_PASSWORD="${HB_PASSWORD}"
JWT_SECRET="${JWT_SECRET}"
ADMIN_EMAIL="${ADMIN_EMAIL}"
ADMIN_PASSWORD="${ADMIN_PASSWORD}"
VOICE_SLOT="2"
DATA_SLOT="1"
SERVER_DMR_ID="${SERVER_DMR_ID}"
AMBE_DEVICE_PATH=""
EMERGENT_LLM_KEY="${EMERGENT_LLM_KEY}"
EOF
fi

# Frontend needs to know how to reach the backend. Since nginx sits in front on
# port 80 and proxies /api to the backend on 127.0.0.1:8001, the browser can
# just use the same origin.
cat > "$INSTALL_DIR/frontend/.env" <<EOF
REACT_APP_BACKEND_URL=${PUBLIC_URL}
EOF

# --------------------------------------------------------------------------- #
# Python venv + deps
# --------------------------------------------------------------------------- #
step "Installing Python dependencies (this can take a few minutes on a Pi)…"
cd "$INSTALL_DIR/backend"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip wheel
# Minimal runtime deps (requirements.txt also holds dev/cloud-only packages)
pip install -r requirements-windows.txt
deactivate

# --------------------------------------------------------------------------- #
# Frontend build
# --------------------------------------------------------------------------- #
step "Installing frontend dependencies + building production bundle…"
cd "$INSTALL_DIR/frontend"

# The upstream package.json includes @emergentbase/visual-edits which is a
# hosted-editor-only devDep and not needed for a self-hosted build. Strip it
# out so we don't depend on the Emergent CDN being reachable.
if grep -q '@emergentbase/visual-edits' package.json; then
    python3 - <<'PY'
import json, pathlib
p = pathlib.Path('package.json')
d = json.loads(p.read_text())
for section in ('dependencies', 'devDependencies'):
    d.get(section, {}).pop('@emergentbase/visual-edits', None)
p.write_text(json.dumps(d, indent=2))
PY
    rm -f yarn.lock
fi

yarn install --frozen-lockfile || yarn install
yarn build

# --------------------------------------------------------------------------- #
# systemd unit for the backend
# --------------------------------------------------------------------------- #
step "Installing systemd unit dmr-backend.service…"
cat > /etc/systemd/system/dmr-backend.service <<EOF
[Unit]
Description=DMR Tracker backend (FastAPI + HB Master UDP listener)
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}/backend
EnvironmentFile=${INSTALL_DIR}/backend/.env
ExecStart=${INSTALL_DIR}/backend/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now dmr-backend.service

# --------------------------------------------------------------------------- #
# nginx reverse proxy
# --------------------------------------------------------------------------- #
step "Configuring nginx…"
cat > /etc/nginx/sites-available/dmr-tracker <<EOF
# DMR Tracker
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${DOMAIN:-_};
    client_max_body_size 25m;

    root ${INSTALL_DIR}/frontend/build;
    index index.html;

    # Static setup docs (allow no-auth read)
    location = /SETUP.md         { try_files \$uri =404; add_header Content-Type text/markdown; }
    location = /SETUP_PART2.md   { try_files \$uri =404; add_header Content-Type text/markdown; }

    # WebSocket - must upgrade
    location /api/ws {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 3600s;
    }

    # REST API
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_read_timeout 3600s;
    }

    # Frontend SPA - fall through to index.html for client-side routes
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/dmr-tracker /etc/nginx/sites-enabled/dmr-tracker
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

if [[ -n "$DOMAIN" ]]; then
    step "Requesting HTTPS certificate for ${DOMAIN}…"
    apt-get install -y certbot python3-certbot-nginx
    ufw allow 443/tcp || true
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$LE_EMAIL" --redirect \
        || c_ylw "Certificate request failed - check the DNS A record points at this server, then run: certbot --nginx -d $DOMAIN"
fi

# --------------------------------------------------------------------------- #
# Firewall
# --------------------------------------------------------------------------- #
step "Opening firewall ports (80/tcp dashboard, ${HB_BIND_PORT}/udp HB master)…"
ufw allow 22/tcp        || true    # keep SSH open
ufw allow 80/tcp        || true
ufw allow 443/tcp       || true
ufw allow "${HB_BIND_PORT}/udp" || true
if ufw status | grep -q inactive; then
    yes | ufw enable || true
fi

# --------------------------------------------------------------------------- #
# Wait for backend + verify
# --------------------------------------------------------------------------- #
step "Verifying backend…"
for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:8001/api/" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #
cat <<EOF

$(c_grn "===============================================================")
$(c_grn " DMR Tracker install complete")
$(c_grn "===============================================================")

  Dashboard URL:    $(c_blu "${PUBLIC_URL}/")
  Admin login:      ${ADMIN_EMAIL}
  Admin password:   $(c_ylw "${ADMIN_PASSWORD}")   ← change from Users page after login
  HB Master UDP:    0.0.0.0:${HB_BIND_PORT}     (point every MMDVM here)
  HB Password:      ${HB_PASSWORD}
  Server DMR ID:    ${SERVER_DMR_ID}

  Config file:      ${INSTALL_DIR}/backend/.env
  Service:          sudo systemctl {status|restart|stop} dmr-backend
  Mongo (docker):   docker logs -f dmr-mongo
  Logs (backend):   journalctl -u dmr-backend -f
  Logs (nginx):     journalctl -u nginx -f

  Point each MMDVMHost DMR-Network at:
     Address = ${DOMAIN:-$LAN_IP}
     Port    = ${HB_BIND_PORT}
     Password= ${HB_PASSWORD}
     Local   = (any free UDP port on the MMDVM)

  Full setup guide (per-brand radio programming + AMBE dongle + FAQ):
     ${PUBLIC_URL}/SETUP.md

$(c_grn "===============================================================")
EOF
