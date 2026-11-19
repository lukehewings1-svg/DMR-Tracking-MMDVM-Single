# DMR Tracker — Hosted Server (VPS) Setup

Run the single-organisation DMR Tracker 24/7 on a cloud server so MMDVMs
anywhere on the internet can connect, and dispatchers can open the dashboard
from any browser.

> **Why a VPS?** MMDVMs connect over **UDP port 62031**. Web-app hosting
> platforms (Emergent deploy, Vercel, Heroku, Render…) only expose HTTP, so the
> MMDVM link would not work there. A plain Linux virtual server (VPS) gives you
> full control of UDP ports.

---

## 1. Pick a server

| Provider | Plan | Approx. cost | Notes |
|---|---|---|---|
| **Hetzner Cloud** *(recommended)* | CX22 — 2 vCPU / 4 GB RAM / 40 GB | ~€4–5 / month | Best value, EU data centres, simple firewall |
| DigitalOcean | Basic Droplet 2 GB / 1 vCPU | ~$12 / month | London data centre (LON1) |
| Vultr / Linode (Akamai) | 2 GB shared | ~$10–12 / month | Many UK/EU/US locations |

Minimum: **2 GB RAM** (4 GB preferred — the frontend build needs memory),
**Ubuntu 24.04 LTS**, 64-bit (x86 or ARM both fine).

Optional: a domain name (e.g. `dmr.yourclub.org`) for HTTPS. Without one you
use the server's IP over plain HTTP.

---

## 2. Create the server (Hetzner example)

1. Sign up at **console.hetzner.cloud** → *New project* → *Add server*.
2. Location: nearest to you (e.g. Nuremberg / Falkenstein / Helsinki).
3. Image: **Ubuntu 24.04**. Type: **CX22**.
4. **SSH key** (recommended): on Windows PowerShell run
   ```powershell
   ssh-keygen -t ed25519
   Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
   ```
   and paste the output into *SSH keys*. (Or skip and use the emailed root password.)
5. **Firewall** → *Create firewall* with these **inbound** rules, attach it to the server:

   | Protocol | Port | Purpose |
   |---|---|---|
   | TCP | 22 | SSH |
   | TCP | 80 | Dashboard (HTTP) |
   | TCP | 443 | Dashboard (HTTPS) |
   | **UDP** | **62031** | MMDVM HomeBrew link |

6. *Create & Buy*. Note the server's **public IPv4** (e.g. `203.0.113.10`).

> DigitalOcean / Vultr: same idea — Ubuntu 24.04, add your SSH key, and create
> a cloud firewall with the four rules above.

---

## 3. (Optional) Point your domain at the server

In your domain's DNS settings add an **A record**:

| Type | Name | Value |
|---|---|---|
| A | `dmr` (→ `dmr.yourclub.org`) | `203.0.113.10` |

Wait a few minutes, then check from PowerShell: `nslookup dmr.yourclub.org`
should return the server IP.

---

## 4. Connect to the server

```powershell
ssh root@203.0.113.10
```
(Type `yes` the first time.)

---

## 5. Install DMR Tracker (one command)

On the server:

```bash
apt-get update && apt-get install -y git
git clone https://github.com/<your-username>/<your-repo>.git /root/dmr-tracker
cd /root/dmr-tracker
```

> Private GitHub repo? Create a token at GitHub → *Settings → Developer
> settings → Personal access tokens*, then clone with
> `https://<token>@github.com/<you>/<repo>.git`.

Run the installer — **change the values in caps**:

**With a domain (HTTPS):**
```bash
sudo DOMAIN=dmr.yourclub.org LE_EMAIL=you@example.com \
     ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='ChooseAStrongPassword' \
     HB_PASSWORD='YourMMDVMPassword' \
     bash install.sh
```

**Without a domain (HTTP on the IP):**
```bash
sudo PUBLIC_HOST=203.0.113.10 \
     ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='ChooseAStrongPassword' \
     HB_PASSWORD='YourMMDVMPassword' \
     bash install.sh
```

Optional: add `EMERGENT_LLM_KEY='sk-emergent-…'` to enable overlay image uploads.

The installer (≈5–10 minutes) installs Python, Node, nginx and Docker; runs
MongoDB in Docker (local only, not exposed); builds the frontend; creates the
`dmr-backend` system service (auto-starts on boot); configures nginx; opens the
server firewall (22, 80, 443, UDP 62031); and, with `DOMAIN`, gets a free
Let's Encrypt HTTPS certificate (auto-renews).

When it finishes it prints the dashboard URL and the MMDVM settings.

---

## 6. First login

Open `https://dmr.yourclub.org` (or `http://203.0.113.10`) and log in with the
`ADMIN_EMAIL` / `ADMIN_PASSWORD` you set. Other users self-register and you
approve them on the **Users** page.

---

## 7. Point MMDVMs / Pi-Star at the server

Pi-Star → *Configuration → Expert → DMR Network* (or MMDVMHost `[DMR Network]`):

| Setting | Value |
|---|---|
| Address | `dmr.yourclub.org` or `203.0.113.10` |
| Port | `62031` |
| Password | your `HB_PASSWORD` |
| Local | `62032` (any free UDP port) |

Apply. The MMDVM appears under **Connected MMDVMs** and **REPEATERS** goes to 1.
Hotspots behind home routers work fine — they connect *out* to the server.

---

## 8. Day-to-day commands (on the server)

```bash
systemctl status dmr-backend        # is it running?
systemctl restart dmr-backend       # restart backend
journalctl -u dmr-backend -f        # live backend logs (Ctrl+C to exit)
docker logs -f dmr-mongo            # database logs
nano /opt/dmr-tracker/backend/.env  # change settings, then restart dmr-backend
```

### Updating after changes are saved to GitHub
**Easiest:** Admin screen → *Software update* → *Update to latest*. The server
pulls from GitHub, rebuilds the dashboard and restarts itself.

Manual alternative:
```bash
cd /root/dmr-tracker && git pull
sudo DOMAIN=dmr.yourclub.org LE_EMAIL=you@example.com bash install.sh
```
(Use the same `DOMAIN` / `PUBLIC_HOST` options as the first install. Your
database and `backend/.env` settings are kept; add `RESET_ENV=1` only if you
want to regenerate `.env` from scratch.)

### Backups
```bash
docker exec dmr-mongo mongodump --archive=/data/db/backup.gz --gzip --db dmr_tracker
docker cp dmr-mongo:/data/db/backup.gz ./dmr-backup-$(date +%F).gz
```
Download it to Windows: `scp root@203.0.113.10:/root/dmr-tracker/dmr-backup-*.gz .`
Hetzner also offers automatic server backups (+20 % of server price).

---

## 9. Security checklist

- Use a strong `ADMIN_PASSWORD` and a non-default `HB_PASSWORD`.
- Use a domain + HTTPS if dispatchers log in over the internet.
- Keep the server patched: `apt-get update && apt-get upgrade -y` monthly.
- Only the four firewall ports above should be open; MongoDB is never exposed.

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Browser can't reach the dashboard | Check the provider firewall allows TCP 80/443; `systemctl status nginx` |
| Login says *Network Error* | `frontend/.env` URL wrong — re-run installer with correct `DOMAIN` / `PUBLIC_HOST` |
| HTTPS certificate failed | DNS A record not pointing at the server yet; wait, then `certbot --nginx -d dmr.yourclub.org` |
| MMDVM never connects | Provider firewall must allow **UDP** 62031 (not just TCP); password must match `HB_PASSWORD`; check `journalctl -u dmr-backend -f` while the MMDVM starts |
| Backend won't start | `journalctl -u dmr-backend -n 100` for the error |
| Installer killed during `yarn build` | Server has < 2 GB RAM — resize, or add swap: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
