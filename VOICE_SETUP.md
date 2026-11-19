# Live Dispatcher Voice — Setup

Dispatchers hold **Hold to talk** (or the space bar) on the Dispatch screen and
hear radio traffic live with **Listen**. Two ways to connect it to DMR — use
either or both:

| Route | Hardware | How it works |
|---|---|---|
| **AMBE dongle** (preferred when present) | DVSI ThumbDV / DV3000 USB stick on the DMR Tracker computer | Server turns dispatcher audio into DMR voice and sends it straight into **every** MMDVM; decodes radio voice from the MMDVMs for listening |
| **DMR818 gateway** | Raspberry Pi + DMR818 module in RF range of an MMDVM ([wiring](./DMR818_GATEWAY_WIRING.md)) | Module transmits over the air, the nearby MMDVM picks it up and the server simulcasts it; module audio out is streamed back for listening |

If the dongle is connected it is used for talking *and* listening; otherwise
the first online gateway is used. With neither, the talk button sends a
"please call in" DMR text instead.

Talk targets: **Talkgroup** (any group the dispatcher may access) or **One
radio** (private call). Dispatcher group restrictions apply to talking and
listening. Only one dispatcher can transmit at a time, and transmit is refused
while a radio is talking. Each transmission is limited to 90 seconds.

> **Microphone access needs a secure page.** Browsers only allow the mic on
> `http://localhost` or on **HTTPS**. On the laptop running the app that's
> automatic; from other devices use the hosted HTTPS setup (`HOSTED_SETUP.md`).

---

## Route 1 — AMBE dongle (ThumbDV / DV3000)

1. Plug the dongle into the DMR Tracker computer.
2. Find its port:
   - Windows: *Device Manager → Ports (COM & LPT)* — e.g. `COM5`
   - Linux / Pi / VPS: `ls /dev/ttyUSB*` — e.g. `/dev/ttyUSB0`
3. In `backend/.env` set:
   ```
   AMBE_DEVICE_PATH="COM5"
   AMBE_BAUD="460800"
   SERVER_DMR_ID="2340001"
   DMR_COLOR_CODE="1"
   VOICE_SLOT="2"
   ```
   - `SERVER_DMR_ID` is the radio ID dispatcher calls come from — use a
     registered DMR ID on amateur bands.
   - `AMBE_BAUD`: ThumbDV and most DV3000 boards use 460800; some older
     DV3000 boards use 230400.
4. Restart the app (close both windows, double-click the desktop icon).
5. *Admin → Voice* should show **AMBE dongle: connected**.

A hosted VPS can't use a USB dongle — use a gateway there, or run the dongle
on a local machine.

---

## Route 2 — DMR818 gateway (Raspberry Pi)

1. Build the hardware: [`DMR818_GATEWAY_WIRING.md`](./DMR818_GATEWAY_WIRING.md).
   Program the module's frequency, colour code, timeslot, radio ID and RX
   group list for your MMDVM (section 6 of that guide).
2. In DMR Tracker: *Admin → Voice → Add* a gateway (e.g. "Control room
   DMR818"). **Copy the key** — it is shown once.
3. On the Pi (Raspberry Pi OS, internet/LAN access to the DMR Tracker server):
   ```bash
   git clone https://github.com/<you>/<repo>.git ~/dmr-tracker
   cd ~/dmr-tracker/gateway
   sudo bash install-gateway.sh
   sudo nano /etc/dmr818-gateway.ini     # server_url, gateway_key, radio_id, audio_device
   arecord -l                            # find the USB sound card number for audio_device
   sudo systemctl start dmr818-gateway
   journalctl -u dmr818-gateway -f       # should say "connected to …"
   ```
4. *Admin → Voice* shows the gateway **online**; the Dispatch screen voice
   badge shows **DMR818 gateway**.

The gateway also forwards **emergency alarms** the module receives, so they
raise the normal emergency banner and siren.

Tuning: `tx_key_delay` (default 0.3 s) holds the first audio until the module
has keyed up so the start of each transmission isn't clipped; `tx_hang`
(0.25 s) keeps it keyed briefly after release. Set audio levels with
`alsamixer` on the Pi.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Talk button says *Send call-in text* | No route: dongle not detected and no gateway online — check *Admin → Voice* |
| *Microphone blocked by the browser* | Allow the mic in the address bar, and use localhost or HTTPS |
| *Channel busy — a radio is talking* | Wait for the radio to finish (half-duplex) |
| Dongle error in *Admin → Voice* | Wrong `AMBE_DEVICE_PATH`/`AMBE_BAUD`, or another program has the port open |
| Radios hear nothing via dongle | Check `VOICE_SLOT`, `DMR_COLOR_CODE` and that radios have the talkgroup in their RX group list |
| Gateway keeps reconnecting | Wrong `server_url` or `gateway_key`; see `journalctl -u dmr818-gateway -f` |
| Gateway audio distorted or quiet | Adjust `alsamixer` levels and the divider resistors in the wiring guide |
