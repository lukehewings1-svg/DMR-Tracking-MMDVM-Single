#!/usr/bin/env python3
"""DMR Tracker voice gateway for a NiceRF DMR818 module on a Raspberry Pi.

Links the module to the DMR Tracker server:
  * dispatcher voice (server -> USB sound card -> module MIC_IN, keyed via UART 0x06)
  * radio voice      (module LINE_OUT -> USB sound card -> server)
  * caller ID + emergency alarms from the module's UART notifications

Audio is PCM16LE 8 kHz mono in 20 ms frames (320 bytes). ALSA's plughw
device resamples to whatever the sound card supports.

Config: /etc/dmr818-gateway.ini (see gateway.example.ini) or a path given as
the first argument.
"""
from __future__ import annotations

import asyncio
import configparser
import json
import logging
import subprocess
import sys
import threading
import time

import serial
import websockets

FRAME = 320
log = logging.getLogger("dmr818-gw")


# --------------------------------------------------------------------- #
# DMR818 UART protocol: 68 CMD R/W S/R CHK(2) LEN(2) DATA 10
# --------------------------------------------------------------------- #
def checksum(frame: bytes) -> int:
    s = 0
    for i in range(0, len(frame) - 1, 2):
        s += (frame[i] << 8) | frame[i + 1]
    if len(frame) % 2:
        s += frame[-1] << 8
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return s ^ 0xFFFF


def build(cmd: int, rw: int, sr: int, data: bytes = b"") -> bytes:
    f = bytearray([0x68, cmd, rw, sr, 0, 0]) + len(data).to_bytes(2, "big") + data + b"\x10"
    f[4:6] = checksum(bytes(f)).to_bytes(2, "big")
    return bytes(f)


class Module:
    def __init__(self, port: str, baud: int, on_event):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.on_event = on_event
        self.lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()

    def send(self, frame: bytes) -> None:
        with self.lock:
            self.ser.write(frame)

    def call(self, start: bool, call_type: str = "group", target: int = 0) -> None:
        ct = {"private": 0x01, "group": 0x02, "all": 0x04}.get(call_type, 0x02)
        self.send(build(0x06, 0x01, 0x01 if start else 0xFF, bytes([ct]) + target.to_bytes(3, "big")))

    def _reader(self) -> None:
        buf = bytearray()
        while True:
            buf += self.ser.read(64)
            while True:
                i = buf.find(b"\x68")
                if i < 0:
                    buf.clear()
                    break
                del buf[:i]
                if len(buf) < 9:
                    break
                n = int.from_bytes(buf[6:8], "big")
                if len(buf) < 9 + n:
                    break
                frame = bytes(buf[: 9 + n])
                del buf[: 9 + n]
                if frame[-1] == 0x10:
                    self._parse(frame)

    def _parse(self, f: bytes) -> None:
        cmd, rw, sr, data = f[1], f[2], f[3], f[8:-1]
        types = {0x01: "private", 0x02: "group", 0x04: "all"}
        if cmd == 0x06 and rw == 0x02:
            if sr == 0x60 and len(data) >= 4:
                self.on_event({"type": "rx_start", "call_type": types.get(data[0], "group"), "src_id": int.from_bytes(data[1:4], "big")})
            elif sr == 0x6F:
                self.on_event({"type": "rx_end"})
            elif sr == 0x6D:
                self.on_event({"type": "tx_failed", "reason": "Module could not start the call"})
        elif cmd == 0x06 and rw == 0x00 and sr in (0x01, 0x02):
            self.on_event({"type": "tx_failed", "reason": "Module busy or channel error"})
        elif cmd == 0x09 and rw == 0x02 and sr == 0x91 and len(data) >= 3:
            self.on_event({"type": "emergency", "src_id": int.from_bytes(data[0:3], "big")})


# --------------------------------------------------------------------- #
class Gateway:
    def __init__(self, cfg: configparser.ConfigParser):
        g = cfg["gateway"]
        self.url = g["server_url"].rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + "/api/gateway/ws"
        self.key = g["gateway_key"]
        self.device = g.get("audio_device", "plughw:1,0")
        self.key_delay = g.getfloat("tx_key_delay", 0.3)
        self.hang = g.getfloat("tx_hang", 0.25)
        self.radio_id = g.getint("radio_id", 0)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.events: asyncio.Queue = asyncio.Queue()
        self.ws = None
        self.rx_active = False
        self.tx_active = False
        self.tx_buffer: list[bytes] = []
        self.tx_open_at = 0.0
        self.module = Module(g.get("serial_port", "/dev/serial0"), g.getint("serial_baud", 57600), self._from_module)
        self.player = subprocess.Popen(["aplay", "-q", "-D", self.device, "-t", "raw", "-f", "S16_LE", "-r", "8000", "-c", "1", "--buffer-time=200000"],
                                       stdin=subprocess.PIPE)
        self.recorder = subprocess.Popen(["arecord", "-q", "-D", self.device, "-t", "raw", "-f", "S16_LE", "-r", "8000", "-c", "1"],
                                         stdout=subprocess.PIPE)

    def _from_module(self, evt: dict) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(self.events.put_nowait, evt)

    async def _module_events(self) -> None:
        while True:
            evt = await self.events.get()
            log.info("module: %s", evt)
            if evt["type"] == "rx_start":
                self.rx_active = True
            elif evt["type"] == "rx_end":
                self.rx_active = False
            if self.ws:
                try:
                    await self.ws.send(json.dumps(evt))
                except Exception:  # noqa: BLE001
                    pass

    async def _capture(self) -> None:
        while True:
            chunk = await asyncio.to_thread(self.recorder.stdout.read, FRAME)
            if not chunk:
                await asyncio.sleep(0.5)
                continue
            if self.rx_active and not self.tx_active and self.ws:
                try:
                    await self.ws.send(chunk)
                except Exception:  # noqa: BLE001
                    pass

    def _play(self, pcm: bytes) -> None:
        try:
            self.player.stdin.write(pcm)
            self.player.stdin.flush()
        except BrokenPipeError:
            log.error("aplay stopped - check audio_device")

    async def _handle(self, msg) -> None:
        if isinstance(msg, bytes):
            if not self.tx_active:
                return
            if time.time() < self.tx_open_at:
                self.tx_buffer.append(msg)  # hold audio until the module has keyed up
                return
            for b in self.tx_buffer:
                self._play(b)
            self.tx_buffer.clear()
            self._play(msg)
            return
        data = json.loads(msg)
        if data.get("type") == "tx_start":
            self.tx_active = True
            self.tx_buffer.clear()
            self.tx_open_at = time.time() + self.key_delay
            await asyncio.to_thread(self.module.call, True, data.get("call_type", "group"), int(data.get("target_id") or 0))
        elif data.get("type") == "tx_end":
            for b in self.tx_buffer:
                self._play(b)
            self.tx_buffer.clear()
            await asyncio.sleep(self.hang)
            await asyncio.to_thread(self.module.call, False)
            self.tx_active = False

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        asyncio.create_task(self._module_events())
        asyncio.create_task(self._capture())
        while True:
            try:
                async with websockets.connect(f"{self.url}?key={self.key}", max_size=2**20, ping_interval=20) as ws:
                    self.ws = ws
                    log.info("connected to %s", self.url)
                    await ws.send(json.dumps({"type": "hello", "radio_id": self.radio_id}))
                    async for msg in ws:
                        await self._handle(msg)
            except Exception as exc:  # noqa: BLE001
                log.warning("server connection lost (%s) - retrying in 5 s", exc)
            self.ws = None
            if self.tx_active:
                await asyncio.to_thread(self.module.call, False)
                self.tx_active = False
            await asyncio.sleep(5)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = configparser.ConfigParser()
    path = sys.argv[1] if len(sys.argv) > 1 else "/etc/dmr818-gateway.ini"
    if not cfg.read(path):
        sys.exit(f"Config file not found: {path}")
    asyncio.run(Gateway(cfg).run())


if __name__ == "__main__":
    main()
