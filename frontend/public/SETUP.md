# DMR Tracker — Full Setup Guide

This document walks you end-to-end through standing up your own DMR tracker
network. Everything runs **off-network** — no BrandMeister, no ham-radio public
servers involved. Your MMDVMs talk directly to a server you control.

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
6. [App usage — Groups, Messaging, Tracking, Emergencies](./SETUP_PART2.md#6-app-usage)
7. [Optional AMBE dongle for web PTT](./SETUP_PART2.md#7-ambe-dongle-for-web-ptt)
8. [Troubleshooting](./SETUP_PART2.md#8-troubleshooting)
9. [Reference — full port + protocol summary](./SETUP_PART2.md#9-reference)

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

* Every radio's GPS is decoded on-server and plotted on OpenStreetMap.
* **Each DMR timeslot is a full independent channel** carrying voice + GPS +
  SMS + emergencies. So a single MMDVM carries **two channels at once** (one
  per timeslot).
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

# Slot layout - each timeslot is a full independent channel carrying voice
# + GPS + SMS + emergencies. Voice frames on both slots are relayed opaquely
# across every connected MMDVM.
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

### 5.1 Universal channel plan

Regardless of brand you'll create the following channels (values are examples —
frequencies must match what your MMDVM is TX/RX-ing on):

| Channel name | Frequency (RX/TX) | TS | TG | Purpose |
|---|---|---|---|---|
| MED-VOICE | 438.500 MHz | 2 (voice slot) | 91 (Medical group) | Talk on the Medical group |
| MED-DATA  | 438.500 MHz | 1 (data slot)  | 91 (Medical group) | GPS + messaging for Medical |
| SEC-VOICE | 438.500 MHz | 2 | 92 (Security) | Voice for Security |
| SEC-DATA  | 438.500 MHz | 1 | 92 (Security) | Data for Security |
| OPS-VOICE | 438.500 MHz | 2 | 93 (Ops) | Voice for Ops |
| OPS-DATA  | 438.500 MHz | 1 | 93 (Ops) | Data for Ops |

Every radio only needs the channels for the group(s) it belongs to.

Also configure **each radio with a unique DMR ID** (any 7-digit number,
consistent across your network — the app will pick that up as the radio's
identity).

### 5.2 Motorola MOTOTRBO (XPR/DP-series) via CPS 16 / CPS 2.0

1. **General settings**
   * Radio Name / Radio ID → set the radio's DMR ID and callsign.
2. **Channels** (one per row from the plan in 5.1)
   * Repeater Slot = 1 for DATA channels, 2 for VOICE
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
     * Destination = the DATA channel above (TS 1, matching TG).
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
   * Assign the emergency to the **VOICE** channel of the group the radio
     belongs to.
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
3. **Channel → Digital Channel**
   * TX/RX Frequency matching MMDVM
   * Colour Code = whatever your MMDVM is set to (default 1)
   * Repeater Slot = 1 (DATA) or 2 (VOICE)
   * TX Group List = the group contact for this TG
4. **GPS / Radio Location Services**
   * Enable GPS.
   * Create a **GPS Trigger**: Time = 30 s, Distance = 100 m.
   * **Report Channel = the DATA channel** you created (TS1).
   * **Reporting Method = "Data"** (not Compact BS Location).
5. **Emergency**
   * `Common Menu → Emergency` → tick **Enable Emergency**.
   * Set **Emergency Type** = "Alarm + Call".
   * Bind the top orange button in **Menu → PF Program Key** to
     `Emergency On`.
   * Emergency channel = the VOICE channel for the radio's group.
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
3. **Channel Information**
   * Create paired channels (DATA on TS1, VOICE on TS2) as per 5.1.
   * Set **TX Contact** to the correct group.
   * Set **Colour Code** = MMDVM colour code.
4. **APRS / GPS**
   * Enable GPS in **Optional Setting → GPS**.
   * Under **APRS → Digital APRS**:
     * Manual TX interval = 30 s.
     * **APRS TG** = the group TG (e.g. 91).
     * **Slot** = 1 (DATA slot).
     * **Report Channel** = "Selected Channel" or specify DATA channel.
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
3. **Channel Information**
   * DATA channels on Repeater Slot 1, VOICE on Slot 2.
   * TX Contact Name = matching group.
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
3. Channels — DATA on TS1, VOICE on TS2.
4. GPS + Emergency handling depend on firmware; OpenGD77 firmware is
   recommended for full feature coverage. Emergency button binding is under
   the OpenGD77 firmware menu.

---

Continue in **[SETUP_PART2.md](./SETUP_PART2.md)** for:
* Detailed app usage (Groups, Messaging, Tracking, Emergencies)
* AMBE dongle setup for web-PTT
* Troubleshooting checklist
* Full port + protocol reference
