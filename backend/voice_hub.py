"""Live dispatcher voice: browser <-> (AMBE dongle | DMR818 gateway) <-> radios.

Audio everywhere is PCM16LE, 8 kHz mono, 20 ms frames (320 bytes).
TX route: dongle (server injects DMR voice into every MMDVM) or gateway
(DMR818 transmits over the air near an MMDVM). RX comes from the same source.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable, Optional

from fastapi import WebSocket

from ambe_dongle import AmbeDongle
from dmr_voice import FT_DATA_SYNC, FT_VOICE, FT_VOICE_SYNC, DT_VOICE_HEAD, DT_VOICE_TERM, VoiceStreamEncoder, dmrd, extract_ambe49

FRAME = 320
SILENCE = bytes(FRAME)
MAX_TX_SEC = 90
RX_TIMEOUT = 1.2


class Dispatcher:
    def __init__(self, ws: WebSocket, user: dict, allowed_tgs: Optional[set], allowed_groups: Optional[set]):
        self.ws, self.user = ws, user
        self.allowed_tgs, self.allowed_groups = allowed_tgs, allowed_groups  # None = unrestricted

    def may_hear(self, private: bool, dst: Optional[int], src_group: Optional[str]) -> bool:
        if self.allowed_tgs is None:
            return True
        if not private and dst is not None and dst in self.allowed_tgs:
            return True
        return src_group is not None and src_group in self.allowed_groups


class VoiceHub:
    def __init__(self, dongle: AmbeDongle, server_id: int, voice_slot: int, color_code: int,
                 send_dmrd: Callable[[bytes], Awaitable[int]], repeaters_online: Callable[[], int],
                 radio_lookup: Callable[[int], Awaitable[dict]], on_change: Callable[[dict], Awaitable[None]],
                 on_gateway_event: Callable[[dict], Awaitable[None]]):
        self.dongle, self.server_id, self.slot, self.cc = dongle, server_id, voice_slot, color_code
        self.send_dmrd, self.repeaters_online, self.radio_lookup = send_dmrd, repeaters_online, radio_lookup
        self.on_change, self.on_gateway_event = on_change, on_gateway_event
        self.dispatchers: dict[WebSocket, Dispatcher] = {}
        self.gateways: dict[str, dict] = {}
        self.tx: Optional[dict] = None
        self.rx: Optional[dict] = None
        self._rx_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._rx_decoder()), asyncio.create_task(self._watchdog())]

    # ---------------- status ---------------- #
    def route(self) -> Optional[str]:
        if self.dongle.ok and self.repeaters_online() > 0:
            return "dongle"
        return "gateway" if self.gateways else None

    def status(self) -> dict:
        return {
            "route": self.route(),
            "dongle": self.dongle.status(),
            "gateways": [{k: g[k] for k in ("id", "name", "connected_at", "radio_id", "busy")} for g in self.gateways.values()],
            "tx": {k: self.tx[k] for k in ("user", "call_type", "target_id", "route")} if self.tx else None,
            "rx": {k: self.rx[k] for k in ("src_id", "callsign", "dst_id", "private", "source")} if self.rx else None,
            "dispatchers_listening": len(self.dispatchers),
            # legacy field used by older UI
            "ambe_hardware_available": self.route() is not None,
        }

    async def _changed(self) -> None:
        await self.on_change(self.status())
        await self._send_all({"type": "voice_status", "status": self.status()})

    async def _send_all(self, msg: dict) -> None:
        for d in list(self.dispatchers.values()):
            try:
                await d.ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.dispatchers.pop(d.ws, None)

    # ---------------- dispatchers ---------------- #
    async def add_dispatcher(self, d: Dispatcher) -> None:
        self.dispatchers[d.ws] = d
        await d.ws.send_json({"type": "voice_status", "status": self.status()})

    async def remove_dispatcher(self, ws: WebSocket) -> None:
        self.dispatchers.pop(ws, None)
        if self.tx and self.tx["ws"] is ws:
            await self.ptt_end(ws)

    async def ptt_start(self, ws: WebSocket, call_type: str, target_id: int, target_group: Optional[str]) -> None:
        d = self.dispatchers.get(ws)
        private = call_type == "private"
        deny = None
        if d is None:
            deny = "not connected"
        elif d.allowed_tgs is not None and not (
            (not private and target_id in d.allowed_tgs) or (private and target_group in d.allowed_groups)
        ):
            deny = "You're not allowed to talk to that group or radio"
        elif self.tx:
            deny = f"{self.tx['user']} is already transmitting"
        elif self.rx and time.time() - self.rx["last_at"] < RX_TIMEOUT:
            deny = "Channel busy - a radio is talking"
        elif not self.route():
            deny = "no_route"
        if deny:
            await ws.send_json({"type": "ptt_denied", "reason": deny})
            return
        route = self.route()
        name = d.user.get("callsign") or d.user.get("email")
        self.tx = {"ws": ws, "user": name, "call_type": call_type, "target_id": target_id, "route": route,
                   "started": time.time(), "queue": asyncio.Queue(maxsize=400)}
        if route == "dongle":
            self.tx["task"] = asyncio.create_task(self._dongle_tx(self.tx, private, target_id))
        else:
            gw = next(iter(self.gateways.values()))
            self.tx["gateway"] = gw
            await gw["ws"].send_json({"type": "tx_start", "call_type": call_type, "target_id": target_id})
        await ws.send_json({"type": "ptt_granted", "route": route})
        await self._changed()

    async def ptt_audio(self, ws: WebSocket, pcm: bytes) -> None:
        tx = self.tx
        if not tx or tx["ws"] is not ws or len(pcm) != FRAME:
            return
        if time.time() - tx["started"] > MAX_TX_SEC:
            await ws.send_json({"type": "ptt_denied", "reason": f"Transmit limit {MAX_TX_SEC}s reached"})
            await self.ptt_end(ws)
            return
        if tx["route"] == "dongle":
            if not tx["queue"].full():
                tx["queue"].put_nowait(pcm)
        else:
            try:
                await tx["gateway"]["ws"].send_bytes(pcm)
            except Exception:  # noqa: BLE001
                pass

    async def ptt_end(self, ws: WebSocket) -> None:
        tx = self.tx
        if not tx or tx["ws"] is not ws:
            return
        self.tx = None
        if tx["route"] == "dongle":
            tx["queue"].put_nowait(None)
        else:
            try:
                await tx["gateway"]["ws"].send_json({"type": "tx_end"})
            except Exception:  # noqa: BLE001
                pass
        await self._changed()

    async def _dongle_tx(self, tx: dict, private: bool, dst: int) -> None:
        enc = VoiceStreamEncoder(self.server_id, dst, private, self.cc)
        stream_id = random.getrandbits(32)
        seq = 0

        async def send(ftype: int, dtype: int, payload: bytes) -> None:
            nonlocal seq
            await self.send_dmrd(dmrd(seq, self.server_id, dst, self.server_id, self.slot, private, ftype, dtype, stream_id, payload))
            seq += 1

        for _ in range(2):
            await send(FT_DATA_SYNC, DT_VOICE_HEAD, enc.header())
        frames, done = [], False
        while not done:
            pcm = await tx["queue"].get()
            if pcm is None:
                done = True
                if not frames:
                    break
                frames += [SILENCE] * (3 - len(frames))
            else:
                frames.append(pcm)
            if len(frames) == 3:
                try:
                    ambe = [await asyncio.to_thread(self.dongle.encode, f) for f in frames]
                except Exception:  # noqa: BLE001
                    break
                burst, vseq = enc.voice(ambe)
                await send(FT_VOICE_SYNC if vseq == 0 else FT_VOICE, vseq, burst)
                frames = []
        await send(FT_DATA_SYNC, DT_VOICE_TERM, enc.terminator())

    # ---------------- RX ---------------- #
    async def _rx_begin(self, source: str, src: int, dst: Optional[int], private: bool, key) -> None:
        radio = await self.radio_lookup(src) or {}
        self.rx = {"source": source, "key": key, "src_id": src, "dst_id": dst, "private": private,
                   "callsign": radio.get("callsign"), "group_id": radio.get("group_id"), "last_at": time.time()}
        msg = {"type": "rx_start", **{k: self.rx[k] for k in ("src_id", "callsign", "dst_id", "private", "source")}}
        for d in list(self.dispatchers.values()):
            if d.may_hear(private, dst, self.rx["group_id"]):
                try:
                    await d.ws.send_json(msg)
                except Exception:  # noqa: BLE001
                    pass
        await self._changed()

    async def _rx_end(self) -> None:
        if not self.rx:
            return
        self.rx = None
        await self._send_all({"type": "rx_end"})
        await self._changed()

    async def _rx_audio(self, pcm: bytes) -> None:
        rx = self.rx
        if not rx:
            return
        rx["last_at"] = time.time()
        for d in list(self.dispatchers.values()):
            if d.may_hear(rx["private"], rx["dst_id"], rx["group_id"]):
                try:
                    await d.ws.send_bytes(pcm)
                except Exception:  # noqa: BLE001
                    pass

    async def on_network_frame(self, src: int, dst: int, private: bool, bits: int, stream_id: int, payload: bytes) -> None:
        """Every DMRD frame from the MMDVMs - decode voice through the dongle."""
        if not self.dongle.ok or not self.dispatchers or src == self.server_id or self.tx:
            return
        if self.rx and self.rx["key"] != stream_id:
            if time.time() - self.rx["last_at"] < RX_TIMEOUT:
                return
            await self._rx_end()
        ftype, dtype = (bits >> 4) & 3, bits & 0xF
        if ftype == FT_DATA_SYNC and dtype == DT_VOICE_TERM:
            if self.rx and not self._rx_queue.full():
                self._rx_queue.put_nowait(None)  # end after queued audio is decoded
            return
        if ftype == FT_DATA_SYNC and dtype != DT_VOICE_HEAD:
            return
        if not self.rx:
            await self._rx_begin("dongle", src, None if private else dst, private, stream_id)
        self.rx["last_at"] = time.time()
        if ftype in (FT_VOICE, FT_VOICE_SYNC) and not self._rx_queue.full():
            self._rx_queue.put_nowait(payload)

    async def _rx_decoder(self) -> None:
        while True:
            payload = await self._rx_queue.get()
            if payload is None:
                await self._rx_end()
                continue
            try:
                frames = extract_ambe49(payload)
                pcm = b"".join([await asyncio.to_thread(self.dongle.decode, f) for f in frames])
            except Exception:  # noqa: BLE001
                continue
            await self._rx_audio(pcm)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            if self.rx and time.time() - self.rx["last_at"] > RX_TIMEOUT:
                await self._rx_end()

    # ---------------- gateways ---------------- #
    async def add_gateway(self, gw_id: str, name: str, ws: WebSocket) -> None:
        old = self.gateways.get(gw_id)
        if old:
            try:
                await old["ws"].close()
            except Exception:  # noqa: BLE001
                pass
        self.gateways[gw_id] = {"id": gw_id, "name": name, "ws": ws, "radio_id": None, "busy": False,
                                "connected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        await self._changed()

    async def remove_gateway(self, gw_id: str, ws: WebSocket) -> None:
        gw = self.gateways.get(gw_id)
        if not gw or gw["ws"] is not ws:
            return
        self.gateways.pop(gw_id, None)
        if self.tx and self.tx.get("gateway") is gw:
            tx_ws = self.tx["ws"]
            self.tx = None
            try:
                await tx_ws.send_json({"type": "ptt_denied", "reason": "Gateway disconnected"})
            except Exception:  # noqa: BLE001
                pass
        if self.rx and self.rx["source"] == f"gateway:{gw_id}":
            await self._rx_end()
        await self._changed()

    async def gateway_message(self, gw_id: str, msg: dict) -> None:
        gw = self.gateways.get(gw_id)
        if not gw:
            return
        t = msg.get("type")
        if t == "hello":
            gw["radio_id"] = msg.get("radio_id")
            await self._changed()
        elif t == "rx_start" and not self.dongle.ok and not self.tx:
            await self._rx_begin(f"gateway:{gw_id}", int(msg.get("src_id") or 0), msg.get("dst_id"), msg.get("call_type") == "private", gw_id)
        elif t == "rx_end" and self.rx and self.rx["source"] == f"gateway:{gw_id}":
            await self._rx_end()
        elif t == "tx_failed" and self.tx and self.tx.get("gateway") is gw:
            tx_ws = self.tx["ws"]
            self.tx = None
            await tx_ws.send_json({"type": "ptt_denied", "reason": msg.get("reason") or "Radio module refused the call"})
            await self._changed()
        elif t in ("emergency", "call_activity"):
            await self.on_gateway_event({**msg, "gateway_id": gw_id})

    async def gateway_audio(self, gw_id: str, pcm: bytes) -> None:
        if self.rx and self.rx["source"] == f"gateway:{gw_id}":
            for i in range(0, len(pcm) - FRAME + 1, FRAME):
                await self._rx_audio(pcm[i : i + FRAME])
