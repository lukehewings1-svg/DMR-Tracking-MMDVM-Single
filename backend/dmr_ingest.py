"""
HomeBrew (HB) DMR master listener.

MMDVMHost / Pi-Star (and similar MMDVM front-ends) can be pointed at any host
that speaks the HB protocol on UDP. We accept any connecting repeater without
network handshake with BrandMeister or any other public system - the app IS the
"master" for the local MMDVM.

The full BPTC(196,96) forward error correction pipeline is not implemented; we
buffer the 33-byte payloads that follow each DMRD header, then feed the
concatenated bytes for a stream into the multi-brand GPS parsers.

Public API:
    HBMaster(bind_host, bind_port, password, on_packet).start() / stop()
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Awaitable

from dmr_parsers import parse_gps_payload

logger = logging.getLogger(__name__)


@dataclass
class RepeaterSession:
    repeater_id: int
    address: tuple
    salt: bytes = b""
    authenticated: bool = False
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Buffer of DMR payload bytes keyed by streamID
    streams: Dict[int, bytearray] = field(default_factory=dict)


PacketHandler = Callable[[dict], Awaitable[None]]


class HBMaster(asyncio.DatagramProtocol):
    def __init__(self, password: str, on_packet: PacketHandler):
        self.password = password.encode()
        self.on_packet = on_packet
        self.sessions: Dict[int, RepeaterSession] = {}
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.stats = {
            "packets_received": 0,
            "dmr_frames": 0,
            "gps_decoded": 0,
            "repeaters_online": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    # asyncio.DatagramProtocol
    # ------------------------------------------------------------------ #
    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        sock = transport.get_extra_info("sockname")
        logger.info("HB Master listening on udp://%s:%s", sock[0], sock[1])

    def datagram_received(self, data: bytes, addr) -> None:
        self.stats["packets_received"] += 1
        try:
            asyncio.create_task(self._handle(data, addr))
        except Exception:  # noqa: BLE001
            logger.exception("Error scheduling packet handler")

    def error_received(self, exc: Exception) -> None:
        logger.warning("HB Master socket error: %s", exc)

    # ------------------------------------------------------------------ #
    # Protocol handling
    # ------------------------------------------------------------------ #
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

    def _handle_login(self, data: bytes, addr) -> None:
        rpt_id = int.from_bytes(data[4:8], "big")
        salt = os.urandom(4)
        self.sessions[rpt_id] = RepeaterSession(repeater_id=rpt_id, address=addr, salt=salt)
        self._send(b"RPTACK" + salt, addr)
        logger.info("HB login from repeater %s @ %s:%s", rpt_id, addr[0], addr[1])

    def _handle_auth(self, data: bytes, addr) -> None:
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

    def _handle_config(self, data: bytes, addr) -> None:
        rpt_id = int.from_bytes(data[4:8], "big")
        if rpt_id in self.sessions:
            self._send(b"RPTACK" + rpt_id.to_bytes(4, "big"), addr)

    async def _handle_dmrd(self, data: bytes, addr) -> None:
        self.stats["dmr_frames"] += 1
        # DMRD layout: DMRD(4) seq(1) src(3) dst(3) rpt(4) bits(1) stream(4) payload(33)
        src_id = int.from_bytes(data[5:8], "big")
        dst_id = int.from_bytes(data[8:11], "big")
        rpt_id = int.from_bytes(data[11:15], "big")
        bits = data[15]
        stream_id = int.from_bytes(data[16:20], "big")
        payload = data[20:53]
        session = self.sessions.get(rpt_id)
        if session:
            session.last_seen = datetime.now(timezone.utc)

        # Frame type is bits 5-4 of `bits`: 0=voice 1=data-sync 2=voice-sync 3=?
        # We buffer everything and try to decode; incorrect voice frames simply
        # fail every parser and produce no output.
        buffer = None
        if session is not None:
            buffer = session.streams.setdefault(stream_id, bytearray())
            buffer.extend(payload)
            if len(buffer) > 2048:
                del buffer[: len(buffer) - 2048]

        result = parse_gps_payload(bytes(buffer)) if buffer else parse_gps_payload(payload)
        if not result:
            return

        self.stats["gps_decoded"] += 1
        packet = {
            "source": "MMDVM",
            "source_addr": f"{addr[0]}:{addr[1]}",
            "repeater_id": rpt_id,
            "dmr_id": src_id,
            "dst_id": dst_id,
            "stream_id": stream_id,
            "slot": 2 if (bits & 0x80) else 1,
            "format": result["format"],
            "lat": result["lat"],
            "lon": result["lon"],
            "speed": result["speed"],
            "heading": result["heading"],
            "extra": result["extra"],
            "hex_preview": payload[:24].hex(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # clear stream buffer so we only report each fix once
        if session is not None:
            session.streams.pop(stream_id, None)
        await self.on_packet(packet)

    def _send(self, data: bytes, addr) -> None:
        if self.transport:
            self.transport.sendto(data, addr)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict:
        return {
            **self.stats,
            "repeaters_online": sum(1 for s in self.sessions.values() if s.authenticated),
            "sessions": [
                {
                    "repeater_id": s.repeater_id,
                    "address": f"{s.address[0]}:{s.address[1]}",
                    "authenticated": s.authenticated,
                    "last_seen": s.last_seen.isoformat(),
                }
                for s in self.sessions.values()
            ],
        }


async def start_hb_master(
    bind_host: str, bind_port: int, password: str, on_packet: PacketHandler
) -> tuple[asyncio.DatagramTransport, HBMaster]:
    loop = asyncio.get_running_loop()
    protocol = HBMaster(password, on_packet)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol, local_addr=(bind_host, bind_port)
    )
    return transport, protocol
