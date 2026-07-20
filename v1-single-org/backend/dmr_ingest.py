"""HomeBrew (HB) DMR master listener.

Accepts any authenticating MMDVMHost / Pi-Star, then for every DMRD frame:

  * If the frame is on the VOICE_SLOT (default 2), relay it verbatim to every
    other authenticated repeater - turning all connected MMDVMs into a
    distributed simulcast for that talkgroup.
  * If the frame is on the DATA_SLOT (default 1), reassemble by stream and feed
    to the GPS parsers first, then the SMS parser. GPS + SMS both get emitted.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, Optional

from dmr_parsers import parse_gps_payload, parse_emergency
from messaging import parse_dmr_sms

logger = logging.getLogger(__name__)

VOICE_SLOT = int(os.environ.get("VOICE_SLOT", "2"))
DATA_SLOT = int(os.environ.get("DATA_SLOT", "1"))


@dataclass
class RepeaterSession:
    repeater_id: int
    address: tuple
    salt: bytes = b""
    authenticated: bool = False
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    streams: Dict[int, bytearray] = field(default_factory=dict)
    # last talkgroup this repeater was tx'ing on
    last_talkgroup: Optional[int] = None
    packets_relayed_in: int = 0
    packets_relayed_out: int = 0


PacketHandler = Callable[[dict], Awaitable[None]]
MessageHandler = Callable[[dict], Awaitable[None]]
VoiceHandler = Callable[[dict], Awaitable[None]]


class HBMaster(asyncio.DatagramProtocol):
    def __init__(
        self,
        password: str,
        on_gps: PacketHandler,
        on_sms: MessageHandler,
        on_voice: VoiceHandler,
        on_emergency: PacketHandler,
        channel_router=None,
    ):
        self.password = password.encode()
        self.on_gps = on_gps
        self.on_sms = on_sms
        self.on_voice = on_voice
        self.on_emergency = on_emergency
        self.channel_router = channel_router  # RepeaterConfigStore-like
        self.sessions: Dict[int, RepeaterSession] = {}
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.stats = {
            "packets_received": 0,
            "dmr_frames": 0,
            "gps_decoded": 0,
            "sms_decoded": 0,
            "voice_relayed": 0,
            "emergencies": 0,
            "repeaters_online": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        sock = transport.get_extra_info("sockname")
        logger.info("HB Master listening on udp://%s:%s", sock[0], sock[1])

    def datagram_received(self, data: bytes, addr) -> None:
        self.stats["packets_received"] += 1
        asyncio.create_task(self._handle(data, addr))

    def error_received(self, exc: Exception) -> None:
        logger.warning("HB Master socket error: %s", exc)

    async def _handle(self, data: bytes, addr) -> None:
        if data.startswith(b"DMRD") and len(data) >= 55:
            await self._handle_dmrd(data, addr)
        elif data.startswith(b"RPTL") and len(data) >= 8:
            self._handle_login(data, addr)
        elif data.startswith(b"RPTK") and len(data) >= 8:
            self._handle_auth(data, addr)
        elif data.startswith(b"RPTC") and len(data) >= 8:
            self._handle_config(data, addr)
        elif data.startswith(b"RPTPING") and len(data) >= 11:
            rpt_id = int.from_bytes(data[7:11], "big")
            self._send(b"MSTPONG" + rpt_id.to_bytes(4, "big"), addr)
        elif data.startswith(b"RPTCL") and len(data) >= 9:
            rpt_id = int.from_bytes(data[5:9], "big")
            self.sessions.pop(rpt_id, None)
            self._send(b"MSTNAK" + rpt_id.to_bytes(4, "big"), addr)

    def _handle_login(self, data, addr) -> None:
        rpt_id = int.from_bytes(data[4:8], "big")
        salt = os.urandom(4)
        self.sessions[rpt_id] = RepeaterSession(repeater_id=rpt_id, address=addr, salt=salt)
        self._send(b"RPTACK" + salt, addr)
        logger.info("HB login from repeater %s @ %s:%s", rpt_id, addr[0], addr[1])

    def _handle_auth(self, data, addr) -> None:
        rpt_id = int.from_bytes(data[4:8], "big")
        session = self.sessions.get(rpt_id)
        if not session:
            return
        expected = hashlib.sha256(session.salt + self.password).digest()
        if data[8:] == expected:
            session.authenticated = True
            self.stats["repeaters_online"] = sum(
                1 for s in self.sessions.values() if s.authenticated
            )
            self._send(b"RPTACK" + rpt_id.to_bytes(4, "big"), addr)
        else:
            self._send(b"MSTNAK" + rpt_id.to_bytes(4, "big"), addr)

    def _handle_config(self, data, addr) -> None:
        rpt_id = int.from_bytes(data[4:8], "big")
        if rpt_id in self.sessions:
            self._send(b"RPTACK" + rpt_id.to_bytes(4, "big"), addr)

    async def _handle_dmrd(self, data: bytes, addr) -> None:
        self.stats["dmr_frames"] += 1
        src_id = int.from_bytes(data[5:8], "big")
        dst_id = int.from_bytes(data[8:11], "big")
        rpt_id = int.from_bytes(data[11:15], "big")
        bits = data[15]
        stream_id = int.from_bytes(data[16:20], "big")
        payload = data[20:53]
        slot = 2 if (bits & 0x80) else 1
        is_private = bool(bits & 0x40)

        session = self.sessions.get(rpt_id)
        if session:
            session.last_seen = datetime.now(timezone.utc)
            session.packets_relayed_in += 1
            if not is_private:
                session.last_talkgroup = dst_id

        # ---- Cross-repeater relay (channel-aware) ------------------------ #
        # Resolve which channel this frame belongs to for the source repeater.
        src_channel_id = f"slot-{slot}"
        if self.channel_router is not None:
            try:
                src_channel_id = await self.channel_router.channel_for_slot(rpt_id, slot)
            except Exception:  # noqa: BLE001
                pass
        relayed = 0
        for other_id, other in self.sessions.items():
            if other_id == rpt_id or not other.authenticated:
                continue
            target_slot = slot
            if self.channel_router is not None:
                try:
                    tgt = await self.channel_router.slot_for_channel(other_id, src_channel_id)
                except Exception:  # noqa: BLE001
                    tgt = None
                if tgt is None:
                    # This MMDVM does not carry the source channel - skip.
                    continue
                target_slot = tgt
            frame = data
            if target_slot != slot:
                # Rewrite the slot bit in the DMRD packet (bit 7 of byte 15)
                new_bits = (data[15] & ~0x80) | (0x80 if target_slot == 2 else 0)
                frame = data[:15] + bytes([new_bits]) + data[16:]
            self._send(frame, other.address)
            other.packets_relayed_out += 1
            relayed += 1
        self.stats["voice_relayed"] += relayed
        await self.on_voice(
            {
                "src_dmr_id": src_id,
                "dst_id": dst_id,
                "is_private": is_private,
                "talkgroup_id": None if is_private else dst_id,
                "repeater_id": rpt_id,
                "stream_id": stream_id,
                "slot": slot,
                "channel": slot,
                "channel_id": src_channel_id,
                "relayed_to": relayed,
            }
        )

        # ---- Data-payload extraction (runs regardless of slot) ------------ #
        buffer = None
        if session is not None:
            buffer = session.streams.setdefault(stream_id, bytearray())
            buffer.extend(payload)
            if len(buffer) > 2048:
                del buffer[: len(buffer) - 2048]

        emer = parse_emergency(bytes(buffer)) if buffer else parse_emergency(payload)
        if emer:
            self.stats["emergencies"] += 1
            await self.on_emergency(
                {
                    "src_dmr_id": src_id,
                    "dst_id": dst_id,
                    "is_private": is_private,
                    "talkgroup_id": None if is_private else dst_id,
                    "repeater_id": rpt_id,
                    "channel": slot,
                    "signature": emer["signature"],
                    "hex_preview": payload[:24].hex(),
                }
            )

        gps = parse_gps_payload(bytes(buffer)) if buffer else parse_gps_payload(payload)
        if gps:
            self.stats["gps_decoded"] += 1
            packet = {
                "source": "MMDVM",
                "source_addr": f"{addr[0]}:{addr[1]}",
                "repeater_id": rpt_id,
                "dmr_id": src_id,
                "dst_id": dst_id,
                "stream_id": stream_id,
                "slot": slot,
                "channel": slot,
                "is_private": is_private,
                "talkgroup_id": None if is_private else dst_id,
                "format": gps["format"],
                "lat": gps["lat"],
                "lon": gps["lon"],
                "speed": gps["speed"],
                "heading": gps["heading"],
                "extra": gps["extra"],
                "hex_preview": payload[:24].hex(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if session is not None:
                session.streams.pop(stream_id, None)
            await self.on_gps(packet)
            return

        sms = parse_dmr_sms(bytes(buffer)) if buffer else None
        if sms and len(sms["text"]) >= 3:
            self.stats["sms_decoded"] += 1
            if session is not None:
                session.streams.pop(stream_id, None)
            await self.on_sms(
                {
                    "text": sms["text"],
                    "from_dmr_id": src_id,
                    "to_dmr_id": dst_id,
                    "is_private": is_private,
                    "talkgroup_id": None if is_private else dst_id,
                    "repeater_id": rpt_id,
                    "channel": slot,
                }
            )

    def _send(self, data: bytes, addr) -> None:
        if self.transport:
            self.transport.sendto(data, addr)

    # ------------------------------------------------------------------ #
    # Broadcast a DMRD packet to every authenticated repeater.
    # Used by outbound SMS + (future) TTS injection.
    # ------------------------------------------------------------------ #
    async def broadcast_dmrd(self, data: bytes) -> int:
        sent = 0
        for s in self.sessions.values():
            if s.authenticated:
                self._send(data, s.address)
                s.packets_relayed_out += 1
                sent += 1
        return sent

    def snapshot(self) -> dict:
        return {
            **self.stats,
            "voice_slot": VOICE_SLOT,
            "data_slot": DATA_SLOT,
            "repeaters_online": sum(1 for s in self.sessions.values() if s.authenticated),
            "sessions": [
                {
                    "repeater_id": s.repeater_id,
                    "address": f"{s.address[0]}:{s.address[1]}",
                    "authenticated": s.authenticated,
                    "last_seen": s.last_seen.isoformat(),
                    "last_talkgroup": s.last_talkgroup,
                    "packets_in": s.packets_relayed_in,
                    "packets_out": s.packets_relayed_out,
                }
                for s in self.sessions.values()
            ],
        }


async def start_hb_master(
    bind_host: str,
    bind_port: int,
    password: str,
    on_gps: PacketHandler,
    on_sms: MessageHandler,
    on_voice: VoiceHandler,
    on_emergency: PacketHandler,
    channel_router=None,
) -> tuple[asyncio.DatagramTransport, HBMaster]:
    loop = asyncio.get_running_loop()
    protocol = HBMaster(password, on_gps, on_sms, on_voice, on_emergency, channel_router)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol, local_addr=(bind_host, bind_port)
    )
    return transport, protocol
