# DMR Tracker — Setup Guide, Part 2

Part 1 is here: **[SETUP.md](./SETUP.md)**. This half covers day-to-day app
usage, the optional AMBE dongle for web-PTT, troubleshooting and the full
protocol reference.

---

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
 │ operator@... [admin] [Setup] [Users] [Clear All] [Sign out]         │
 ├──────────────────────── Emergency banner ──────────────────────────┤
 │  ⚠ EMERGENCY · 2 ACTIVE   [K7SAR-1] [DL7ABC]  (only if active)     │
 ├──────────┬───────────────────────────────────┬─────────────────────┤
 │  Roster  │              Live map              │    Ops / Msg tabs   │
 │          │        (OpenStreetMap dark)        │                     │
 │          │                                    │  Groups filter      │
 │          │                                    │  Connected MMDVMs   │
 │          │                                    │  Parsers            │
 │          │                                    │  Alerts             │
 │          │                                    │  Geofences          │
 │          ├───────────────────────────────────┤  Injector (test)    │
 │          │           Packet log               │                     │
 └──────────┴───────────────────────────────────┴─────────────────────┘
```

The right column has two tabs:

* **Ops** — groups, repeaters, parsers, alerts, geofences, simulated GPS
  injector.
* **Messages** — DMR text messaging. Pick a Group or a specific Radio, type,
  hit **Send** (or Ctrl+Enter).

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
