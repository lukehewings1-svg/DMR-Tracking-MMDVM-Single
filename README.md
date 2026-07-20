# DMR Tracker

**Off-network DMR radio dispatcher console.** Ingest GPS + text + emergency alarms directly from your own MMDVMs, plot everything live on OpenStreetMap, bridge voice across multiple MMDVMs, message individual radios or entire talkgroups, geofence-alert, and export shift logs as CSV. No BrandMeister, no public networks — your radios talk to a server you control.

- Live map (OSM + CARTO Dark) with per-radio trails, callsigns and custom icons
- Multi-MMDVM voice bridge on any timeslot, cross-linked to become one simulcast
- DMR SMS send/receive (private and group) with a conversation view
- Emergency-button detection with red banner + roster highlight + browser siren
- Geofences with enter/exit/both alerts
- Custom-JWT auth with admin-approved onboarding + per-dispatcher group ACL
- Shift log: every position, message, voice TX, geofence + emergency, exportable as CSV
- **Situational-awareness view:** a token-locked, read-only URL for incident command staff
- Raspberry Pi one-command installer

Quick links:
- Fastest possible install → [`§0`](#0-quick-install-on-a-raspberry-pi-one-command)
- Running locally on a laptop (macOS / Windows / Linux) → [`§3.6`](#36-running-locally-on-a-laptop-macos--windows--linux)
- Point your MMDVM at the server → [`§4`](#4-mmdvm-setup)
- Program the radios → [`§5`](#5-radio-programming-by-brand)
- Day-to-day app usage → [`§6`](#6-app-usage)
- AMBE dongle for web PTT → [`§7`](#7-ambe-dongle-for-web-ptt)
- Situational-awareness read-only view → [`§6.11`](#611-situational-awareness-view-read-only)
- Troubleshooting → [`§8`](#8-troubleshooting)

---

## 0. Quick install on a Raspberry Pi (one command)

If you just want to spin up a test node, use the bundled installer. It works on
**Raspberry Pi 4 / 5 with 64-bit Raspberry Pi OS**, and on any Debian 12 or
Ubuntu 22.04+ machine.

**Option A — from a checkout of this repo:**

```bash
git clone <this-repo-url> dmr-tracker
cd dmr-tracker
sudo bash install.sh
```

**Option B — one-liner (if you've published the repo somewhere reachable):**

```bash
curl -fsSL https://<your-host>/install.sh | sudo REPO_URL=https://github.com/<you>/<repo>.git bash
```

The installer will:

1. Install Python 3, Node 20, yarn, nginx, ufw, Docker.
2. Run MongoDB 6 in a Docker container (survives reboots, no host-level Mongo mess).
3. Generate a strong `JWT_SECRET` and write `backend/.env` + `frontend/.env`.
4. Install Python + Node dependencies and build the production frontend.
5. Register a `dmr-backend.service` systemd unit (auto-starts on boot).
6. Configure nginx as a reverse proxy on port 80 (dashboard + `/api` + WebSocket).
7. Open firewall ports **80/tcp** (dashboard) and **62031/udp** (MMDVM).
8. Print the dashboard URL and admin credentials when finished.

You can override any default via env vars before invoking the script:

```bash
sudo ADMIN_EMAIL=me@example.com ADMIN_PASSWORD=changeme \
     HB_PASSWORD=SuperSecret SERVER_DMR_ID=9990001 \
     bash install.sh
```

**Post-install:**

```bash
# Status / logs
sudo systemctl status dmr-backend
journalctl -u dmr-backend -f
docker logs -f dmr-mongo

# Update after a git pull
sudo systemctl restart dmr-backend
cd /opt/dmr-tracker/frontend && sudo yarn build

# Uninstall
sudo bash uninstall.sh           # keeps data
sudo bash uninstall.sh --purge   # wipes /opt/dmr-tracker and the mongo volume
```

Once the installer finishes, open `http://<pi-ip>/` in a browser and log in with
the admin credentials it printed. Then jump straight to [section 4](#4-mmdvm-setup)
to point your first MMDVM at the Pi. The rest of this document is reference /
manual-install / per-brand programming.

---

## Table of contents

1. [What you're building](#1-what-youre-building)
2. [Bill of materials](#2-bill-of-materials)
3. [Server setup](#3-server-setup)
   * 3.1 Requirements
   * 3.2 First-time install (Docker or manual)
   * 3.3 Environment variables
   * 3.4 Firewall rules
   * 3.5 First-login + creating accounts
4. [MMDVM setup](#4-mmdvm-setup)
   * 4.1 Pi-Star / MMDVMHost pointing at your server
   * 4.2 Multiple MMDVMs
   * 4.3 Verifying the connection
5. [Radio programming (by brand)](#5-radio-programming-by-brand)
   * 5.1 Universal channel plan
   * 5.2 Motorola MOTOTRBO (XPR, DP series)
   * 5.3 Hytera (PD / MD series)
   * 5.4 Anytone / BTECH (AT-D878, DMR-6X2, D578)
   * 5.5 TYT / Retevis (MD-380, MD-UV380, RT3S)
   * 5.6 Radioddity (GD-77, GD-88, etc.)
   * 5.7 Sepura DMR (SC20 / SC21 / SBP8000 series)
   * 5.8 Mapping channels to MMDVM timeslots (in the app)
6. [App usage — Groups, Messaging, Tracking, Emergencies](#6-app-usage)
7. [Optional AMBE dongle for web PTT](#7-ambe-dongle-for-web-ptt)
8. [Troubleshooting](#8-troubleshooting)
9. [Reference — full port + protocol summary](#9-reference)

> Part 2 (usage, PTT, troubleshooting): **[SETUP_PART2.md](./SETUP_PART2.md)**

---

## 1. What you're building

```
   Radio A ─RF─┐                                              ┌─RF─ Radio D
               │                                              │
   Radio B ─RF─┤   MMDVM #1  ── UDP 62031 ──┐                 ├─RF─ Radio E
               │                            │                 │
   Radio C ─RF─┘                            │                 └─RF─ Radio F
                                            ▼
                                     ┌──────────────┐
                                     │   Server     │ ← this app
                                     │  (HB Master) │
                                     └──────┬───────┘
                                            │
                                     ┌──────┴────────┐
   Radio G ─RF─┐  MMDVM #2  ── UDP 62031 ──┘         │
               │                                     │
   Radio H ─RF─┤                                     │
                                                     │
                            ...more MMDVMs...        │
                                                     ▼
                                          Web dashboard (browsers)
```

* Every radio's GPS is decoded on-server and plotted on OpenStreetMap (with
  four selectable base layers: Dark / Streets / Satellite / Terrain, plus a
  toggleable street-labels overlay for a hybrid view).
* **Unified channels** — voice, GPS, SMS and emergencies all ride on the
  **same** talkgroup/timeslot. Radios only need ONE channel per group (no
  separate DATA vs. VOICE channels). Which channel sits on TS1 vs. TS2 on each
  MMDVM is configured *in the app*, not at the radio.
* Voice frames on both timeslots are relayed across every connected MMDVM,
  turning the whole set into a distributed simulcast for radios that select
  that talkgroup.
* Emergency button presses trigger visual + audible alarms in the app.
* Text messages (DMR SMS) can be sent from the dashboard to individual radios
  or an entire group.
* Groups (Medical, Security, Ops…) map to DMR talkgroup IDs and let you filter
  the map and roster.
* The dashboard's **Channel filter** lets you show radios on Channel 1 only,
  Channel 2 only, or both. Channels are renameable by an admin.

---

## 2. Bill of materials

**Minimum viable network:**

| Item | Notes |
|------|-------|
| 1 × Server (Linux, x86 or ARM) | Anywhere from a $35 Raspberry Pi 4 to a full VPS. Runs 24/7. |
| 1 × MMDVM board + host Pi | Standard Pi-Star / MMDVMHost stack. Any DMR-capable MMDVM (MMDVM_HS, DVMEGA, ZUMspot, OpenSPOT etc.) works. |
| 2 or more DMR radios | Any brand. GPS-capable models needed if you want position tracking. |
| Internet (optional) | Only needed if the MMDVMs and server aren't on the same LAN. |

**Optional, unlocks more features:**

| Item | Feature it enables |
|------|--------------------|
| DVSI DV3000 or ThumbDV (NW Digital) USB dongle | Web browser → radio PTT. Plug into the **server**, not each dispatcher's PC. Without it the dashboard PTT button falls back to sending a DMR text message. |
| Additional MMDVMs | Wider coverage. All connected MMDVMs form one large simulcast conference on the voice slot. |

---

## 3. Server setup

### 3.1 Requirements

* Linux, macOS or Windows (with WSL2) host
* Python 3.11+, Node 18+, MongoDB 6+
* Public IP **not required**. If your MMDVMs are on the same LAN, a private IP
  is fine.
* UDP port `62031` reachable from every MMDVM
* TCP port `8001` reachable from every browser (or whatever you reverse-proxy
  it to — the app assumes `/api` prefix)

### 3.2 First-time install (manual)

```bash
# 1. Clone
git clone <this repo> dmr-tracker && cd dmr-tracker

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Frontend
cd ../frontend
yarn install
yarn build       # or `yarn start` in dev

# 4. MongoDB
sudo systemctl start mongod
# (or run docker: `docker run -d --name mongo -p 27017:27017 mongo:6`)

# 5. Configure .env - see next section

# 6. Start backend
cd ../backend
uvicorn server:app --host 0.0.0.0 --port 8001

# 7. Serve frontend build (production)
#    Any static file server pointed at frontend/build works.
#    In dev: cd frontend && yarn start
```

### 3.3 Environment variables

The app reads all runtime config from `backend/.env`. Only these keys need
attention on a real deployment:

```ini
# Database
MONGO_URL="mongodb://localhost:27017"
DB_NAME="dmr_tracker"

# HTTP CORS - "*" is fine for LAN, list explicit origins for public deploys
CORS_ORIGINS="*"

# HomeBrew Master (this app's UDP listener the MMDVMs connect to)
HB_BIND_HOST="0.0.0.0"
HB_BIND_PORT="62031"
HB_PASSWORD="PASSWORD"          # match this in each MMDVMHost DMR-Network config

# Slot layout — retained for legacy purposes. In the unified model, voice, GPS,
# SMS and emergencies all ride on the same channel/timeslot as picked by the
# admin per-MMDVM in the app (Ops → MMDVM Channel Bindings). Voice frames on
# either slot are relayed opaquely across every connected MMDVM.
VOICE_SLOT="2"
DATA_SLOT="1"

# Auth
JWT_SECRET="<generate a 64-char random hex string>"
ADMIN_EMAIL="admin@example.com"
ADMIN_PASSWORD="<something-strong>"

# This app's own DMR ID (used as the src_id when sending SMS / voice)
SERVER_DMR_ID="9990001"

# AMBE hardware (optional - see part 2)
AMBE_DEVICE_PATH=""
```

Generate a strong `JWT_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Restart the backend after editing `.env`:

```bash
sudo supervisorctl restart backend
# or
systemctl restart dmr-tracker
```

### 3.4 Firewall rules

| Direction | Protocol | Port | Reason |
|-----------|----------|------|--------|
| MMDVMs → Server | **UDP** | **62031** | HomeBrew master traffic |
| Browsers → Server | TCP | 8001 (or 443 behind a reverse proxy) | REST + WebSocket dashboard |

On Ubuntu:

```bash
sudo ufw allow 62031/udp
sudo ufw allow 8001/tcp
```

### 3.5 First login + creating accounts

1. Open `http://<your-server>:8001/` (or your public URL) in a browser.
2. Sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.
3. Ask each operator to click **Request access** on the login page.
4. Back in the app, click **Users** in the top-right and approve them.
5. Approved users can now log in.

Custom-JWT auth, admin-approved onboarding. Nothing else can talk to the API
without a valid Bearer token.

### 3.6 Running locally on a laptop (macOS / Windows / Linux)

You don't need a Raspberry Pi or a VPS — a laptop on the same LAN as your
MMDVM works perfectly and is the fastest way to try the app.

**Networking picture:**

```
   [Radio]  ⇄  [MMDVM (Pi-Star / OpenSPOT / etc.)]  ─UDP 62031─▶  [Your laptop]
                                                                   running this app
```

Both the MMDVM and the laptop must be on the same LAN (either both wired,
both on Wi-Fi, or a mix — as long as they can reach each other's private IP).

#### macOS

```bash
# 1. Install deps
brew install python@3.11 node@20 mongodb-community git yarn

# 2. Start Mongo as a service
brew services start mongodb-community

# 3. Clone + set up (same as §3.2)
git clone <this repo> ~/dmr-tracker && cd ~/dmr-tracker/backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # edit .env — see §3.3

# 4. Run backend (foreground, easy to Ctrl-C)
uvicorn server:app --host 0.0.0.0 --port 8001

# 5. In a second terminal, run frontend
cd ~/dmr-tracker/frontend
echo 'REACT_APP_BACKEND_URL=http://LAPTOP-LAN-IP:8001' > .env
yarn install && yarn start
```

**Firewall:** macOS's application firewall may prompt on first launch to allow
Python to accept incoming connections — click **Allow**. To confirm inbound
UDP 62031 is reachable:

```bash
# On the laptop:
sudo lsof -iUDP:62031        # should list a Python process bound to *:62031
# Or from another machine:
nc -uz LAPTOP-LAN-IP 62031   # blank line = reachable
```

If UDP is blocked, System Settings → Network → Firewall → Options → set the
Python interpreter to *Allow incoming connections*.

**Finding your laptop's LAN IP:**

```bash
ipconfig getifaddr en0          # Wi-Fi
ipconfig getifaddr en1          # Ethernet dongle (usually)
```

Point every MMDVMHost at that IP in §4.1.

#### Windows

Recommended path is **WSL2** (Ubuntu). Under WSL2, follow the Linux/Raspberry
Pi steps below. The one gotcha:

* WSL2 by default is on a virtual NIC — UDP 62031 will not reach your MMDVM
  without a small port-forward. Open PowerShell **as admin** and run:

  ```powershell
  # Replace 172.20.10.5 with the WSL Ubuntu VM's IP (run `ip addr` inside WSL)
  netsh interface portproxy add v4tov4 listenport=62031 listenaddress=0.0.0.0 `
      connectport=62031 connectaddress=172.20.10.5 protocol=udp

  # And open the Windows firewall for it
  New-NetFirewallRule -DisplayName "DMR HB Master" -Direction Inbound -Action Allow `
      -Protocol UDP -LocalPort 62031
  ```

  Now the MMDVM can point at the **Windows host's** LAN IP and traffic reaches
  the WSL VM.

Native Windows (no WSL) also works: install Python 3.11 from python.org,
Node 20+ LTS, MongoDB Community, then follow the macOS steps verbatim. Add a
Windows Firewall inbound rule for UDP 62031.

#### Linux laptop

Identical to the Raspberry Pi / server install in §3.2. Open the firewall as
in §3.4 and you're done.

#### Common laptop caveats

* **Sleep / lid close:** the app won't receive packets while the laptop is
  asleep. In macOS: `System Settings → Battery → Options → Prevent
  automatic sleeping on power adapter when the display is off`. In Linux:
  `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`.
* **DHCP-reassigned IPs:** if your laptop's IP changes, every MMDVM will
  silently stop connecting. Either pin the laptop's IP with a DHCP
  reservation in your router, or use its mDNS hostname
  (`http://your-laptop.local:8001/` on macOS / most modern Linux).
* **Public Wi-Fi:** doesn't work — most public networks block LAN-to-LAN UDP.
  Use a home / office / hotspot network.
* **VPN split-tunnel gotchas:** if the laptop's default route is through a
  VPN, the MMDVM on your LAN won't be able to reach it. Either disable the
  VPN or configure a route so LAN traffic bypasses it.

---

## 4. MMDVM setup

### 4.1 Pi-Star / MMDVMHost pointing at your server

Log into your Pi-Star (`http://<pi-star-ip>/admin`) → **Configuration** →
**Expert** → **MMDVMHost** → find the `[DMR Network]` block. Set:

```ini
[DMR Network]
Enable=1
Address=<YOUR_SERVER_IP_OR_HOSTNAME>
Port=62031
Local=62032          # any free local UDP port
Password=PASSWORD    # exactly matches HB_PASSWORD in backend/.env
Debug=0
Slot1=1
Slot2=1
Options=
```

Then set the repeater ID under `[General]` → **Id=** to a unique 7-digit
number (this is what the app displays as `RPT id`). Repeaters connected to
public DMR networks already have one — off-network you can pick anything
locally unique.

**Important:** disable **BrandMeister** and any other public DMR network in
Pi-Star's config screen — you want traffic to go **only** to your server. In
Pi-Star's config screen: `DMR Master = None`, then in Expert → MMDVMHost, edit
the `[DMR Network]` block manually as above.

Restart MMDVMHost:

```bash
sudo pistar-mmdvmhost restart
```

### 4.2 Multiple MMDVMs

Repeat 4.1 on every MMDVMHost / Pi-Star you own. **Assign each one a unique
`Id=`.** They can all point at the same server IP + port `62031`. They will
all show up in the dashboard's **Connected MMDVMs** panel.

On the voice time slot, the server relays traffic between all authenticated
MMDVMs — turning your entire set into one distributed simulcast conference on
the chosen talkgroup.

### 4.3 Verifying the connection

* On the server, watch the backend log — you should see:
  ```
  HB Master listening on udp://0.0.0.0:62031
  HB login from repeater <YOUR_RPT_ID> @ <mmdvm-ip>:<local-port>
  ```
* In the web dashboard, the **Connected MMDVMs** panel (right column, Ops tab)
  will list each MMDVM with a green `LIVE` indicator.

---

## 5. Radio programming (by brand)

This section covers the **minimum** you need for each brand. Every brand has
its own CPS (Customer Programming Software) but the concepts map 1:1.

### 5.1 Universal channel plan (unified: one channel per group)

Voice, GPS, SMS and emergencies all ride on the **same** talkgroup/timeslot in
this app — you do **not** need separate DATA and VOICE channels the way older
DMR-network setups required. Radios only need **one channel per group** they
belong to.

Regardless of brand you'll create one channel per group (values are examples —
frequencies must match what your MMDVM is TX/RX-ing on):

| Channel name | Frequency (RX/TX) | TS | TG | Purpose |
|---|---|---|---|---|
| MED  | 438.500 MHz | 1 *(any)* | 91 (Medical) | Voice + GPS + SMS + emergency for Medical |
| SEC  | 438.500 MHz | 1 *(any)* | 92 (Security) | Voice + GPS + SMS + emergency for Security |
| OPS  | 438.500 MHz | 2 *(any)* | 93 (Ops) | Voice + GPS + SMS + emergency for Ops |

**Which timeslot each channel uses on each MMDVM is set inside the app** — go
to **Ops → MMDVM Channel Bindings** (admin only) and drop each of your named
channels onto TS1 or TS2 of every connected MMDVM. Frames arriving on the
"wrong" slot are re-emitted on the target slot automatically when they cross
between MMDVMs, so radios can be programmed however is convenient.

Every radio only needs the channel(s) for the group(s) it belongs to.

Also configure **each radio with a unique DMR ID** (any 7-digit number,
consistent across your network — the app will pick that up as the radio's
identity).

### 5.2 Motorola MOTOTRBO (XPR/DP-series) via CPS 16 / CPS 2.0

1. **General settings**
   * Radio Name / Radio ID → set the radio's DMR ID and callsign.
2. **Channels** — **one channel per group** (voice + GPS + SMS all on the
   same channel)
   * Repeater Slot = 1 or 2 — either is fine; the app's *MMDVM Channel
     Bindings* map your channel to a physical timeslot on each MMDVM.
   * Contact Name = the talkgroup contact you defined
   * TX Contact Name = same
   * Emergency System = "EmerSys-1" (defined below)
3. **Contacts** → **Digital**
   * Create a contact per group (Call Type = **Group Call**, Call ID = TG
     number, e.g. `91`).
   * Also create at least one **Private Call** contact if you want to receive
     private calls from the dashboard (Call Type = Private Call, Call ID = the
     server DMR ID from `SERVER_DMR_ID` in `.env`, e.g. `9990001`).
4. **GNSS / Location** (only if radio supports GPS)
   * Enable **GNSS** on the radio-wide setting.
   * Add a **Location Info Config** entry:
     * Trigger = Distance/Time (e.g. every 30s, or every 100m).
     * Destination = the group's unified channel (same TG as voice).
5. **Text Messages**
   * Under **Menu**, enable **Text Message** so the operator can compose SMS.
   * Ensure **Text Message Alert** is on so incoming SMS from the dashboard
     produce an audible/vibrate alert.
6. **Emergency System**
   * Create an Emergency System called `EmerSys-1`
     * Alarm Type = **Silent w/ Voice** (or your policy)
     * Impolite Retry Interval / Count as you prefer
     * Emergency Call Confirmation = as your policy
   * Under **One-Touch Access**, bind the top orange button to this
     emergency system.
   * Assign the emergency to the **group's unified channel**.
7. Write the codeplug to the radio.

Motorola LRRP position reports and the emergency alarm CSBK the dashboard
watches for are both emitted by default once GNSS + Emergency System are
configured as above.

### 5.3 Hytera PD/MD-series via CPS

1. **Common Menu → Basic Information**
   * Radio ID = the DMR ID
   * Radio Alias = callsign
2. **Digital Common → Digital Contact List**
   * Add a **Group Call** for each talkgroup (91, 92, 93…).
   * Add a **Private Call** contact for the server's `SERVER_DMR_ID` (e.g.
     `9990001`).
3. **Channel → Digital Channel** — one channel per group
   * TX/RX Frequency matching MMDVM
   * Colour Code = whatever your MMDVM is set to (default 1)
   * Repeater Slot = 1 or 2 (either works; the app remaps as needed)
   * TX Group List = the group contact for this TG
4. **GPS / Radio Location Services**
   * Enable GPS.
   * Create a **GPS Trigger**: Time = 30 s, Distance = 100 m.
   * **Report Channel = the group's channel** (same one that carries voice).
   * **Reporting Method = "Data"** (not Compact BS Location).
5. **Emergency**
   * `Common Menu → Emergency` → tick **Enable Emergency**.
   * Set **Emergency Type** = "Alarm + Call".
   * Bind the top orange button in **Menu → PF Program Key** to
     `Emergency On`.
   * Emergency channel = the group's channel.
6. **Message Menu → Enable Short Data Message** so the radio can send/receive
   text SMS.
7. Write the codeplug.

### 5.4 Anytone / BTECH (AT-D878, AT-D578, DMR-6X2) via CPS

1. **Optional Setting → Basic Information**
   * Radio ID = DMR ID
   * Alias = callsign
2. **Talk Groups** (Digital Contact List)
   * Add each group as **Group Call**, e.g. `91 = Medical`.
   * Add one **Private Call** contact with call ID = `SERVER_DMR_ID`.
3. **Channel Information** — one channel per group
   * TS 1 or TS 2 — either works; the app maps channels onto physical slots.
   * Set **TX Contact** to the correct group.
   * Set **Colour Code** = MMDVM colour code.
4. **APRS / GPS**
   * Enable GPS in **Optional Setting → GPS**.
   * Under **APRS → Digital APRS**:
     * Manual TX interval = 30 s.
     * **APRS TG** = the group TG (e.g. 91).
     * **Slot** = same slot as the channel above.
     * **Report Channel** = "Selected Channel" or specify the group's channel.
     * Anytone radios by default emit **APRS text over DMR** — the app's
       APRS parser will pick these up.
5. **DMR Text Messages**
   * Menu → Setting → Local Setting → enable **Text Message Alert** so the
     radio pops incoming SMS.
6. **Emergency**
   * **Optional Setting → Alarm Setting** → set **Alarm Mode = Alarm + Call**.
   * Bind the top button to **Emergency Alarm**.
7. Write the codeplug.

### 5.5 TYT / Retevis (MD-380, MD-UV380, RT3S) via CPS

1. **General Setting**
   * Radio ID = DMR ID, Radio Name = callsign.
2. **Digital Contacts** — add group contacts (TG 91, 92, …) and one Private
   Call to `SERVER_DMR_ID`.
3. **Channel Information** — one channel per group. TS 1 or TS 2 is fine.
   TX Contact Name = matching group.
4. **GPS**
   * Stock TYT firmware has limited GPS support. If you're on OpenGD77 /
     OpenRTX firmware, enable GPS in the firmware menu and set the
     **Beaconing** interval + destination.
   * Reports are emitted as NMEA sentences over DMR data — the app's NMEA
     parser handles them.
5. **Emergency** (varies by model): bind the top button under **Buttons
   Definition** to **Emergency On** if the model supports it.
6. Write the codeplug.

### 5.6 Radioddity GD-77 / GD-88

1. **General Settings** → Radio ID + callsign.
2. Group contacts (TG 91, 92, …) + one Private Call to `SERVER_DMR_ID`.
3. Channels — one per group. TS 1 or TS 2 is fine.
4. GPS + Emergency handling depend on firmware; OpenGD77 firmware is
   recommended for full feature coverage. Emergency button binding is under
   the OpenGD77 firmware menu.

### 5.7 Sepura DMR (SC20 / SC21 / SBP8000 series)

Sepura's DMR line speaks standard ETSI DMR, so **voice, DMR SMS and the
emergency-button CSBK all work end-to-end with this app** — same HomeBrew
master, same talkgroup routing, same emergency banner + siren.

**GPS is the one nuance:** Sepura radios by default report GPS using **LIP**
(ETSI TS 102 361-4 Location Information Protocol), which the app's parsers
don't decode natively yet. Two workarounds that DO work today:

1. **Recommended — emit NMEA over DMR data.** Most Sepura DMR models can be
   configured (via Sepura Radio Manager / Fleet Manager) to send GPS as raw
   **NMEA `$GPRMC` sentences** over the DMR data channel instead of LIP. The
   app's NMEA parser will pick them up automatically.
2. **APRS-over-DMR.** If your Sepura fleet is running firmware / a codeplug
   that supports APRS-style position beacons over the DMR data channel, the
   app's APRS parser handles those too.
3. Native **LIP** parsing is on the roadmap (P1) — capture a sample decrypted
   packet with `tcpdump` on UDP/62031 and open an issue so we can add it.

Programming steps (Sepura Radio Manager / Fleet Manager):

1. **Radio Identity**
   * DMR ID = the radio's 7-digit ID.
   * Radio Alias = callsign.
2. **Contacts / Talkgroups**
   * Add a **Group Call** contact per group (91, 92, 93…).
   * Add a **Private Call** contact for the server's `SERVER_DMR_ID` (e.g.
     `9990001`) so the dashboard can privately message this radio.
3. **Channels** — one channel per group, either TS is fine (the app's
   *MMDVM Channel Bindings* handle the physical slot mapping).
   * TX Contact = the group.
   * Colour Code = matches your MMDVM.
4. **GPS**
   * Enable the internal GPS receiver.
   * Under **Location Reporting** (naming varies by model / SRM version), set
     **Reporting Method = NMEA (RMC)**, **Interval = 30 s**, **Report Channel
     = the group's channel**.
   * If your model only exposes **LIP**, either upgrade to a firmware that
     supports NMEA output, or open an issue so LIP parsing can be added.
5. **Text Messaging (SDS)**
   * Enable **Short Data Service / Text Messages** in the codeplug so incoming
     SMS from the dashboard pop on the radio.
6. **Emergency**
   * Bind the top orange button (SC20/SC21) or the labelled emergency key
     (SBP8000) to **Emergency Alarm + Call**.
   * Emergency channel = the group's channel.
7. Write the codeplug via Sepura Radio Manager.

> **Note on Sepura AVL:** Sepura's *AVL Server* is a proprietary product for
> Sepura-only fleets that decrypts LIP and plots to their own dashboard. This
> app is an off-network, multi-brand alternative that works with any HomeBrew-
> compatible MMDVM. AVL is not required.

### 5.8 Mapping channels to MMDVM timeslots (in the app)

After programming radios and pointing MMDVMs at the server:

1. Sign in as **admin** on the dashboard.
2. In the right column, open **Ops → MMDVM Channel Bindings** → **Configure**.
3. For every MMDVM you plan to run, pick which channel sits on **TS1** and
   which sits on **TS2**. Voice frames arriving on the "wrong" slot are
   re-emitted on the correct slot automatically when they cross between
   MMDVMs, so radios can be programmed however is convenient.
4. Any channel you haven't created yet can be added under **Ops → Channels
   (Timeslots)** — click the pen icon on the built-in `slot-1` / `slot-2`
   channels to rename them, or POST to `/api/channels` to add a new one.

## 6. App usage

### 6.1 Sign in

1. Go to `https://<your-server>/`
2. Sign in as admin (email + password from `backend/.env`).
3. Or click **Request access** to self-register a non-admin operator — an admin
   must then approve you from the **Users** page.

### 6.2 Understanding the layout

```
 ┌───────────────────────────── Top bar ──────────────────────────────┐
 │ LISTENER · REPEATERS · DMR FRAMES · GPS FIXES · RADIOS · LIVE       │
 ├─────────────────────────── Session strip ──────────────────────────┤
 │ operator@... [admin] [Overlays: On] [Setup] [Users] [Clear All]     │
 ├──────────────────────── Emergency banner ──────────────────────────┤
 │  ⚠ EMERGENCY · 2 ACTIVE   [K7SAR-1] [DL7ABC]  (only if active)     │
 ├──────────┬───────────────────────────────────┬─────────────────────┤
 │  Radios  │              Live map              │    Ops / Msg / Log   │
 │  (roster)│      Dark / Streets / Satellite    │                     │
 │          │      / Terrain — pick top-right    │  Event Overlays     │
 │          │      Rotate: compass control       │  Channels           │
 │          │      Two-finger twist on touch     │  MMDVM Bindings     │
 │          │      Shift+drag on desktop         │  Groups             │
 │          │                                    │  Connected MMDVMs   │
 │          │                                    │  Parsers · Alerts   │
 │          │                                    │  Geofences          │
 │          ├───────────────────────────────────┤  Injector (test)    │
 │          │           Packet log               │                     │
 └──────────┴───────────────────────────────────┴─────────────────────┘
```

Every side panel can be **minimised** (chevron buttons on each header and
on the left / right / bottom edges of the map). On phones / tablets the
layout collapses to a full-screen map with a bottom tab bar: **Map /
Radios / Ops / Msg / Log**.

**Rotating the map** — the compass control on the top-left of the map lets
you spin the basemap to any bearing so the event site is oriented the way
you want it (useful when the course, campus or venue isn't aligned with
true north). Click ± to nudge 15°, click the compass to snap back to
north, hold **Shift** and drag on desktop, or **twist two fingers** on a
touch device.

The right column has three tabs:

* **Ops** — event overlays, channels, groups, repeaters, parsers, alerts,
  geofences, simulated GPS injector.
* **Msg** — DMR text messaging. Pick a Group or a specific Radio, type,
  hit **Send** (or Ctrl+Enter).
* **Log** — shift log (all events, filterable, CSV-exportable).

### 6.3 Groups (Talk Groups)

Groups map 1:1 to DMR talkgroup IDs. Radios are auto-assigned to a group the
first time they transmit on a matching TG. You can also manually assign a
group from the radio detail modal.

* **Ops tab → Groups panel → Manage** (admin only): create, rename, recolor,
  change icon, delete groups. Deleting a group unassigns every radio in it —
  the radios themselves are not deleted.
* Click a group chip in the Groups panel to **filter roster + map** by that
  group. Click again to clear the filter.
* Each group can have a distinct icon + color so its radios are visually
  distinct on the map.

### 6.4 Live tracking

* Every GPS fix received on the DATA slot updates the radio's position.
* Trails show the last N positions (default 500, capped per-radio).
* Click a radio's marker on the map (or a row in the roster) to focus it.
* **Double-click** a roster row (or single-click a marker) to open the
  **Radio Detail modal**:
  * Rename callsign
  * Assign group
  * Choose a custom icon + color
  * View position history table (with timestamps + speed)
  * See trail distance and max speed
  * Delete the radio (admin only)

### 6.5 DMR text messaging

Go to the right column **Messages** tab.

* **Group message:** pick GROUP → select the target group → type → Send. The
  server encodes a DMR data burst on the DATA slot and broadcasts it to every
  connected MMDVM. Radios on the group's talkgroup will receive it.
* **Private message:** pick RADIO → select a specific radio → type → Send.
  Encoded as a private call.
* **Inbound:** when a radio sends a DMR SMS the server extracts the text and
  it appears here with a toast notification. In the conversation view your
  outbound messages appear on the right, radio replies on the left.

> **Note on interop:** DMR SMS uses per-brand PDU formatting. The app sends a
> best-effort ETSI UDT-Data burst on the DATA slot that most Anytone / BTECH /
> Hytera radios accept. Motorola MOTOTRBO SMS uses a slightly different
> proprietary encoding — for full Motorola SMS support you may need a
> vendor-specific gateway. Position, voice relay and emergency detection work
> across every brand out of the box.

### 6.6 Voice bridging across MMDVMs

Fully automatic. Nothing to configure inside the app. Any radio keying up on
the VOICE slot (default TS2) of a talkgroup will be simulcast to every other
authenticated MMDVM. You'll see the transmit indicator light up on the
originating MMDVM in the **Connected MMDVMs** panel, and it will highlight the
receiving MMDVMs briefly as they relay the audio out.

### 6.7 Web PTT (talk from the browser to radios)

Open a radio's detail modal → **Voice Contact** section → **Private call** or
**Talk to <group>**. Behavior:

* **If an AMBE dongle is attached to the server** and detected: hold the
  button, the browser captures your microphone, encodes audio via the dongle,
  and injects DMR voice frames into every connected MMDVM.
* **If no dongle**: the button turns amber, labelled **(SMS fallback)**. Press
  it and it automatically sends a DMR text message to the target ("[control]
  requesting voice contact on ...") so the person carrying the radio knows to
  call you back.

See section **7** for dongle setup.

### 6.8 Emergency alarms

When a radio user presses the emergency (orange) button:

* The MMDVM forwards the emergency CSBK/data burst.
* The server detects it via multiple brand signatures (Motorola, Hytera,
  generic "EMERGENCY" tag).
* The dashboard immediately:
  * Renders a red **EMERGENCY BANNER** across the top with the radio callsign.
  * Highlights the radio marker on the map with a pulsing red ring.
  * Highlights the radio row in the roster with a red accent.
  * Plays a **whoop-whoop** siren tone from the browser (Web Audio API — no
    plugin required).
  * Shows a persistent toast notification.
* An admin then opens the radio's detail modal and clicks
  **Acknowledge / Clear Emergency** to remove the alarm. All operators see the
  cleared state live via WebSocket.

You can test the flow at any time from **Groups → group row → orange
Emergency icon** (fires a simulated emergency on that TG).

### 6.9 Geofences

* Create geofences from **Ops tab → Geofences panel → +New** (admin only).
* Provide name, center lat/lon, radius (metres), and whether to alert on
  ENTER, EXIT or BOTH transitions.
* Alerts appear in the **Alerts panel** and via toast.

### 6.10 User administration

Only admins see the **Users** button in the session strip.

* Approve or reject pending registrations.
* Promote a user to admin, or demote back to user.
* Delete a user account.
* You cannot delete or demote yourself.

### 6.11 Situational-awareness view (read-only)

For incident-command staff who need to *watch* — but not touch — the operation
(command post big screen, EOC staff, etc.) an admin can generate a
**token-locked, view-only URL**. Anyone with the link sees a full-screen
OpenStreetMap with every radio's live position + any active emergencies, and
nothing else. No auth prompt, no ability to click through to admin, no
messaging, no PTT, no shift log, no config.

* **Create a token:** *Users* page → **Situational Views** panel → **+ New**.
  Give it a name, choose the group scope (all radios or one group), optionally
  set an expiry.
* Copy the URL — it has the form
  `https://<your-server>/situational/<random-token>`.
* Anyone hitting that URL sees the live map immediately; positions and
  emergencies stream over a token-authenticated WebSocket.
* Tokens can be **revoked** from the same panel at any time; expired tokens
  auto-refuse further requests.
* Tokens are read-only. They cannot see the packet log, roster metadata,
  messaging, PTT, admin, shift log or any other endpoint. Every write endpoint
  and every user-scoped API rejects them.

Perfect for a wall-mounted TV in the ops tent, or for briefing a stakeholder
without giving them a login.

---

## 7. AMBE dongle for web PTT

DMR voice audio uses the AMBE+2 codec, which is patented and requires a
licensed vocoder chip. That means to talk from a browser you need a physical
dongle attached to the **server** (not to each operator's PC — see below).

### 7.1 Compatible hardware

| Product | Notes |
|---------|-------|
| **NW Digital Radio ThumbDV** | USB stick, most common choice, ~$70. |
| **DVSI DV3000U** | Reference DVSI hardware, ~$100. |
| **DV3000 board** | Bare board for makers, needs a UART bridge. |

Any device that speaks the DVSI serial protocol on a UART / USB serial port
works.

### 7.2 Plug it into the server

The dongle goes into the machine that's running this backend — the same box
that's already listening for MMDVM traffic on UDP 62031. Reasons this is
better than one-dongle-per-dispatcher:

* One dongle covers the whole app; every browser client can PTT.
* No per-client USB/WebUSB permission dialogs.
* Same box handles RX audio decoding for playback across all listeners.

### 7.3 Enable it

Confirm the dongle is visible:

```bash
ls /dev/ttyUSB*
# /dev/ttyUSB0
```

Set the path in `backend/.env`:

```ini
AMBE_DEVICE_PATH="/dev/ttyUSB0"
```

Restart the backend:

```bash
sudo supervisorctl restart backend
```

Refresh the dashboard. On the radio detail modal the PTT button will turn
green and the "AMBE dongle not detected" warning will disappear.

> **Full streaming audio implementation is stubbed pending physical hardware.**
> Backend endpoint `/api/voice/status` reports whether the dongle is present.
> The end-to-end audio pipeline (browser MediaRecorder → server → AMBE encoder
> → DMR frames → MMDVM) is scaffolded and completes once you attach a real
> dongle and adjust `voice.py` to open the DVSI serial protocol. The SMS
> fallback works everywhere in the meantime.

---

## 8. Troubleshooting

### 8.1 MMDVM shows as not connected

* Verify the MMDVMHost log (`sudo pistar-watchdog log` or
  `journalctl -u mmdvmhost -f`) says something like:
  `Login response received from the master`.
* Common issues:
  * `HB_PASSWORD` in `backend/.env` ≠ Password in MMDVM.ini → `Auth Failed`
  * Firewall blocks UDP 62031 → nothing appears in backend log
  * MMDVM is still pointed at BrandMeister — disable it in Pi-Star
* On the server, `sudo tcpdump -i any udp port 62031` should show packets
  every ~5 seconds (heartbeats) once configured.

### 8.2 Radios connect but no GPS shows

* Confirm the radio's location report is being sent on the **DATA** slot
  (default TS1) and on the correct talkgroup contact.
* On the dashboard's Parsers panel, watch which parser counter increments as
  the radio TXes a location. If none does, the radio may be sending in a
  proprietary format we don't currently decode — file an issue with a hex
  capture and we can add a parser.
* Anytone radios often need the "GPS APRS" checkbox toggled explicitly per
  channel.

### 8.3 Voice not bridging between MMDVMs

* Voice bridging happens on `VOICE_SLOT` (default 2). Make sure the radios
  are keying up on TS2 — check MMDVMHost log for `slot 2`.
* Only **authenticated** repeaters receive bridged voice. Watch the log for
  each MMDVM completing its `RPTK` handshake.
* If you configured `VOICE_SLOT="1"` in `.env`, flip radio channels to key on
  TS1.

### 8.4 Emergency alarm didn't trigger the alert

* The app matches on `EMER`, `EMERGENCY`, `0xB0…` and `0x24A0` byte
  signatures. Some brands may use custom bytes — you can add signatures in
  `backend/dmr_parsers.py::_EMERGENCY_TAGS`.
* Confirm the radio actually TXes the emergency (its own display should say
  `EMERGENCY`).
* Use the **Groups → orange emergency icon** to simulate an emergency from
  the app itself; if the siren + banner work there, the frontend pipeline is
  fine and the issue is either radio-side or the byte signature.

### 8.5 SMS doesn't reach the radio

* Motorola MOTOTRBO uses a proprietary SMS encoding. Currently the app sends
  ETSI UDT-Data bursts, which Anytone / BTECH / most Hytera radios accept.
  Motorola support requires a vendor-specific PDU gateway not shipped here.
* On the receive path we heuristically extract UTF-16LE / ASCII text from the
  DMR data burst — some brands may need explicit parsing added.

### 8.6 Web PTT button says "SMS fallback"

* That means no AMBE dongle was detected. Follow section 7.
* Verify with `GET /api/voice/status` returning `ambe_hardware_available: true`.

### 8.7 Nothing at all in the dashboard

* Are you actually on `/`? If the URL redirects to `/login`, sign in first.
* Check the browser console — any red errors will explain (usually CORS or
  WebSocket).
* The WebSocket URL is `wss://<host>/api/ws?token=<jwt>` — must be reachable
  by the browser. If you're behind a reverse proxy, make sure it upgrades
  WebSocket connections on the `/api/ws` path.

---

## 9. Reference

### 9.1 Ports

| Port | Proto | Direction | Purpose |
|------|-------|-----------|---------|
| 62031 | UDP | MMDVM → server | HomeBrew master |
| 8001  | TCP | Browser → server | REST + WebSocket (or 443 via reverse proxy) |
| 27017 | TCP | Backend → MongoDB | Database — bind to localhost only |

### 9.2 Backend endpoints (all under `/api`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /auth/register | public | Self-register (pending) |
| POST | /auth/login | public | Login → `{token, user}` |
| GET  | /auth/me | user | Current session user |
| GET  | /admin/users | admin | List users |
| POST | /admin/users/{id}/approve, /reject, /role | admin | Manage users |
| DELETE | /admin/users/{id} | admin | Delete user |
| GET  | /status | user | Listener + parser + voice + stats |
| GET  | /radios (?group_id) | user | List radios (filterable by group) |
| GET  | /radios/{id}/positions | user | Position history |
| PATCH | /radios/{id} | user | Rename / recolor / assign group |
| DELETE | /radios/{id}, /radios | admin | Delete one / all |
| GET  | /packets | user | Recent raw packet log |
| POST | /inject | user | Simulated GPS injection |
| POST | /inject-raw | user | Raw hex payload injection |
| GET  | /repeaters | user | Connected MMDVMs snapshot |
| GET  | /groups | user | List groups |
| POST | /groups, PATCH /{id}, DELETE /{id} | admin | Group CRUD |
| GET  | /messages | user | Recent DMR SMS |
| POST | /messages | user | Send DMR SMS (group or private) |
| POST | /messages/simulate-inbound | user | Testing helper |
| GET  | /voice/status | user | AMBE dongle presence |
| POST | /voice/ptt | user | Begin PTT (server encodes via AMBE if present) |
| GET  | /geofences, POST, DELETE | user/admin | Geofences CRUD |
| GET  | /alerts, DELETE | user/admin | Geofence alert log |
| GET  | /emergencies | user | Active emergencies |
| POST | /emergencies/{id}/clear | admin | Acknowledge emergency |
| POST | /emergencies/simulate | user | Testing helper |
| GET  | /ws (WebSocket) | user (token=query) | Live push: packets, alerts, emergencies, messages, voice activity, group changes |
| GET  | /situational-tokens | admin | List situational-awareness tokens |
| POST | /situational-tokens | admin | Create a token — body `{name, group_id?, expires_at?}` |
| DELETE | /situational-tokens/{id} | admin | Revoke |
| GET  | /situational/{token}/snapshot | public (token) | Radios + active emergencies (view-only) |
| GET  | /situational/{token}/ws (WebSocket) | public (token) | Live push of positions + emergencies for the token's scope |

### 9.3 HomeBrew protocol (summary)

The server acts as the HB master. Handshake, exactly like BrandMeister:

```
MMDVM → Master : RPTL <rpt_id>                  (login request)
Master → MMDVM : RPTACK <4-byte salt>           (challenge)
MMDVM → Master : RPTK <rpt_id> <sha256(salt+pw)>(auth)
Master → MMDVM : RPTACK <rpt_id>                (auth ok)
MMDVM → Master : RPTC <rpt_id> <302 bytes cfg>  (config)
Master → MMDVM : RPTACK <rpt_id>
MMDVM ↔ Master : RPTPING / MSTPONG              (heartbeat every 5s)
MMDVM ↔ Master : DMRD <55 bytes>                (voice + data traffic)
```

DMRD packet layout (55 bytes):

```
offset  size  field
0       4     "DMRD"
4       1     seq
5       3     src_id  (big-endian)
8       3     dst_id  (big-endian)
11      4     repeater_id (big-endian)
15      1     bits (bit 7 = slot, bit 6 = private-call, bits 5-4 = frame type)
16      4     stream_id
20      33    DMR payload (opaque - relayed as-is on voice slot)
```

The server:

* On voice slot: relays the whole 55-byte packet to every other authenticated
  repeater. That's the cross-MMDVM voice bridge.
* On data slot: reassembles per stream_id, tries all GPS parsers, then the
  SMS parser, then the emergency alarm detector.

---

Enjoy your off-network DMR net.