# DMR818 Dispatcher Voice Gateway — Wiring Guide

Lets dispatchers talk (and listen) on DMR **without an AMBE dongle**.
The DMR818 module contains its own vocoder: we feed it ordinary audio, it
transmits real DMR voice. Placed in RF range of one of your MMDVMs, that
MMDVM picks the transmission up and the DMR Tracker server simulcasts it to
every other MMDVM — exactly like a normal radio keying up.

```
Dispatcher browser ──internet──► DMR Tracker server ──Wi-Fi──► Pi Zero 2 W gateway
                                                                ├─ USB sound card ─► DMR818 MIC_IN   (TX audio)
                                                                ├─ USB sound card ◄─ DMR818 LINE_OUT (RX audio)
                                                                └─ UART (GPIO14/15) ◄► DMR818 UART  (call start/stop, talkgroup, caller ID)
DMR818 ))) over the air ((( nearest MMDVM ──► server ──► all MMDVMs simulcast
```

> Sources: NiceRF *DMR818 Digital Mobile Radio Module V1.6* datasheet and
> *DMR818S/DMR828S Protocol*. Always double-check pin numbers against the
> datasheet for your exact module revision before powering up.

---

## 1. Parts list

| Qty | Part | Notes |
|---|---|---|
| 1 | **NiceRF DMR818** (or DMR818S), UHF 400–470 MHz, **AMBE++ vocoder version** | AMBE version = compatible with Motorola/Hytera/most DMR radios. The NVOC version is not. |
| 1 | Raspberry Pi Zero 2 W (+ microSD 16 GB, Raspberry Pi OS Lite 64-bit) | Any Pi works |
| 1 | USB sound card with separate **mic (pink)** and **headphone (green)** 3.5 mm jacks | e.g. generic CM108/C-Media; needs a micro-USB OTG adapter on a Zero |
| 1 | 5 V 3 A power supply | Feeds Pi + buck converter |
| 1 | Adjustable buck converter (e.g. MP1584 / LM2596 module) | **Set to 4.2 V** for the DMR818 |
| 1 | UHF antenna, 50 Ω, SMA/u.FL pigtail to module ANT pin | **Never transmit without an antenna** |
| 2 | 3.5 mm mono/stereo plugs + shielded audio cable | |
| 2 | 1 µF ceramic or film capacitor (non-polarised) | Audio DC blocking |
| 1 | 10 kΩ resistor | TX audio divider |
| 1 | 22 kΩ resistor | RX audio divider |
| 2 | 1 kΩ resistor | Audio dividers |
| 2 | 10 kΩ resistor | PTT / CS pull-ups |
| 1 | 470–1000 µF electrolytic (≥10 V) + 100 nF ceramic | Supply decoupling at the module |
| 2–3 | Clip-on ferrite cores | On USB + audio leads (keeps RF out of audio) |
| — | Stripboard/perfboard, header wire, small project box | |

---

## 2. DMR818 pin-out (module back view, 20 pins)

| Pin | Name | Use in this build |
|---|---|---|
| 1 | MIC_IN | **TX audio in** (from sound card headphone out, via divider) |
| 2 | UART-TX | → Pi GPIO15 (RXD) |
| 3 | UART-RX | ← Pi GPIO14 (TXD) |
| 4 | SWCLK | not connected |
| 5 | SWDIO | not connected |
| 6 | ARM_RST | not connected |
| 7 | ANT | **50 Ω antenna** |
| 8, 9, 10 | GND | Ground |
| 11 | VCC | **+4.2 V** from buck converter (3.3–5.0 V allowed) |
| 12 | EZP_CS | not connected |
| 13 | CS | 10 kΩ pull-up to pin 15 (high = awake) |
| 14 | PTT | 10 kΩ pull-up to pin 15 (we key via UART command, not this pin) |
| 15 | +3.3V | Module's 3.3 V output (max 50 mA) — only for the pull-ups |
| 16 | LINE_OUT | **RX audio out** (to sound card mic in, via divider) |
| 17 | T/R | Optional → Pi GPIO17 (high while transmitting) |
| 18 | SPKEN | Optional → Pi GPIO27 (high while receiving audio) |
| 19, 20 | GND | Ground |

Key specs: VCC 3.3–5.0 V (4.2 V typical) · TX current ~800 mA @ high power ·
MIC_IN 0.1 Vpp typical, **1.6 Vpp max** · LINE_OUT 1.6 Vpp typ, 30 kΩ ·
UART 57600 8N1, 3.3 V logic (directly compatible with Pi GPIO).

---

## 3. Power

```
5 V 3 A PSU ──┬──────────────► Pi Zero 2 W (PWR micro-USB)
              │
              └──► Buck converter IN ──► OUT set to 4.2 V ──┬── DMR818 pin 11 (VCC)
                                                            ├── 470–1000 µF  (+) ─┐
                                                            └── 100 nF ───────────┤
              Common GND ◄──────── Buck GND ── DMR818 pins 8/9/10/19/20 ── Pi GND (pin 6)
```

- **Don't feed the module straight from 5 V USB** — USB supplies are often
  5.1–5.25 V, above the module's 5.0 V maximum. Set the buck to 4.2 V with a
  multimeter *before* connecting the module.
- Put the big capacitor right at the module's VCC/GND pins; TX current surges
  to ~0.8 A.
- Do **not** power the module from the Pi's 3.3 V pin.

---

## 4. Control (UART) — Pi GPIO header

| Pi physical pin | Pi function | → | DMR818 pin |
|---|---|---|---|
| 8 | GPIO14 / TXD | → | 3 UART-RX |
| 10 | GPIO15 / RXD | ← | 2 UART-TX |
| 6 | GND | — | 8 GND |
| 11 | GPIO17 (optional) | ← | 17 T/R |
| 13 | GPIO27 (optional) | ← | 18 SPKEN |

Pull-ups on the module side:
```
DMR818 pin 15 (+3.3V) ──10 kΩ── pin 14 (PTT)
DMR818 pin 15 (+3.3V) ──10 kΩ── pin 13 (CS)
```
PTT must stay high/floating while the module boots.

Enable the Pi's serial port: `sudo raspi-config` → *Interface Options →
Serial Port* → login shell **No**, serial hardware **Yes** → reboot.
The port is `/dev/serial0`.

---

## 5. Audio

Cheap USB sound cards: **green** jack = headphone out, **pink** jack = mic in.
Use the plug's **tip** for signal and **sleeve** for ground.

### TX path — dispatcher voice → radio (≈ 11:1 attenuation)
```
Sound card GREEN tip ──┤1 µF├──[10 kΩ]──●────────────► DMR818 pin 1 (MIC_IN)
                                        │
                                      [1 kΩ]
                                        │
Sound card GREEN sleeve ────────────────●────────────► DMR818 GND
```
~1 Vpp from the sound card becomes ~90 mVpp — the module's typical mic level.
Fine-tune with the Pi's `alsamixer` output level and the module's MIC gain
command (0x0B).

### RX path — radio audio → dispatchers (≈ 23:1 attenuation)
```
DMR818 pin 16 (LINE_OUT) ──┤1 µF├──[22 kΩ]──●────────► Sound card PINK tip
                                            │
                                          [1 kΩ]
                                            │
DMR818 GND ─────────────────────────────────●────────► Sound card PINK sleeve
```
1.6 Vpp becomes ~70 mVpp, a safe mic-input level. The capacitor also blocks
the mic socket's bias voltage from reaching the module.

### RF hygiene
- Use shielded audio cable, keep leads short, and clip ferrites on the USB
  and audio leads near the Pi.
- Keep the module's antenna away from the Pi, sound card and audio leads.
- Put everything in a (preferably metal) box with the antenna outside.

---

## 6. Radio settings for working through your MMDVM

Set via the serial protocol (the gateway software will do this from a config
file) or NiceRF's PC software:

| Setting | Simplex hotspot (single freq) | Duplex MMDVM repeater |
|---|---|---|
| RX frequency | Hotspot frequency | Repeater **TX** (output) frequency |
| TX frequency | Hotspot frequency | Repeater **RX** (input) frequency |
| Repeater mode (0x0E) | Off | **On** |
| Colour code (0x31) | Same as MMDVM | Same as MMDVM |
| Timeslot (0x33) | Same slot your channel uses (hotspots: usually TS2) | Slot bound to the channel in *Ops → MMDVM Channel Bindings* |
| Radio ID (0x1B) | A valid DMR ID for the dispatcher console (registered ID if on amateur bands) | same |
| Talkgroup | Chosen per transmission by the dashboard (call command 0x06) | same |
| RX group list (0x29) | Add every talkgroup dispatchers should hear | same |
| TX power (0x17) | **Low (0.5 W)** | Low unless the repeater is far away |

Placement: a few metres from the MMDVM is plenty. Too close at high power can
overload the MMDVM's receiver — use low power, separate them, and/or add an
inline attenuator.

How it flows:
- **Dispatcher → radios:** module transmits → nearest MMDVM receives →
  server relays to every MMDVM (existing simulcast) → all radios hear it.
- **Radios → dispatchers:** traffic arriving from other MMDVMs is
  transmitted by the nearby MMDVM → the module receives it → LINE_OUT →
  gateway streams it to the browser, with the caller ID from the module.

---

## 7. First power-up checklist

1. Buck converter set to **4.2 V** (measure before connecting).
2. Antenna connected. Module set to **low power** and a frequency you're licensed for.
3. Power on; the module plays its boot tone and the Pi boots.
4. Serial test from the Pi:
   ```bash
   sudo apt install -y python3-serial
   python3 - <<'EOF'
   import serial, time
   s = serial.Serial('/dev/serial0', 57600, timeout=1)
   s.write(bytes.fromhex('68 25 01 01 95 C8 00 01 01 10'))  # read firmware version
   time.sleep(0.3); print(s.read(64).hex(' '))
   EOF
   ```
   You should get a reply starting `68 25 00 00 …` containing the firmware name.
5. Audio test: key a handheld on the same channel; `arecord -D plughw:1,0 -f S16_LE -r 8000 test.wav`
   on the Pi should capture it. Play `aplay -D plughw:1,0 test.wav` while sending the call-start
   command (0x06) and listen on the handheld.
6. Watch the DMR Tracker dashboard — the dispatcher's transmission should show
   as voice activity from the MMDVM that heard it.

---

## 8. Licensing

The module defaults to 418–425 MHz, which you're generally **not** permitted
to transmit on in the UK. Program frequencies covered by your licence
(amateur 70 cm with a licence, or your business radio licence) before any
transmit test.
