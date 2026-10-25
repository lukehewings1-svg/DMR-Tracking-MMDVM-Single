"""DMR text-messaging store + best-effort transmit path.

Sending a text message to a real DMR radio requires per-brand encoding (Motorola
TMS, Hytera HTM, ETSI UDT/UTF-16LE) plus BPTC(196,96) FEC on the payload burst.
A production implementation typically wraps a battle-tested library (e.g.
DMRGateway's PDU code). For this MVP we:

  * Persist every message (in-app source of truth).
  * Broadcast outbound messages to every authenticated repeater as a best-effort
    stream of DMRD data frames on the configured DATA_SLOT so any brand that
    accepts UDT-Data payloads will attempt delivery.
  * On the receive side, attempt to extract UTF-16LE / ASCII text from the
    reassembled data buffer whenever the GPS parser doesn't match.

Real-world interop with specific radio brands is expected to require additional
brand-specific PDU work. The store, endpoints and UI are ready for that.
"""
from __future__ import annotations

import re
import struct
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, List, Optional


# --------------------------------------------------------------------------- #
# Text parsing (inbound)
# --------------------------------------------------------------------------- #
_MIN_TEXT_LEN = 3
_ASCII_RE = re.compile(rb"[\x20-\x7e]{%d,}" % _MIN_TEXT_LEN)


def parse_dmr_sms(payload: bytes) -> Optional[dict]:
    """Best-effort SMS extraction from a reassembled DMR data buffer.

    Tries UTF-16LE first (ETSI DMR SMS standard), falls back to ASCII spans.
    Returns {"text": str} or None. Skips buffers that look like NMEA/APRS/LRRP.
    """
    if not payload:
        return None
    # Ignore payloads that look like GPS - those are handled by GPS parsers.
    if b"$GP" in payload or b"$GN" in payload or b"!" in payload[:4]:
        return None

    # Try UTF-16LE with printable char check
    try:
        text = payload.decode("utf-16-le", errors="ignore")
        text = "".join(c for c in text if c.isprintable() or c in "\n\t").strip()
        if len(text) >= _MIN_TEXT_LEN and any(c.isalpha() for c in text):
            return {"text": text[:256]}
    except UnicodeDecodeError:
        pass

    # Fallback: longest printable-ASCII run
    spans = _ASCII_RE.findall(payload)
    if spans:
        longest = max(spans, key=len).decode("ascii", errors="ignore").strip()
        if any(c.isalpha() for c in longest) and len(longest) >= _MIN_TEXT_LEN:
            return {"text": longest[:256]}
    return None


# --------------------------------------------------------------------------- #
# Outbound - best-effort DMR data burst builder
# --------------------------------------------------------------------------- #
def build_sms_dmrd_frames(
    src_id: int,
    dst_id: int,
    is_private: bool,
    slot: int,
    text: str,
    repeater_id: int,
) -> List[bytes]:
    """Produce a stream of DMRD packets carrying a UTF-16LE encoded SMS payload.

    Each DMRD packet is 55 bytes:
        b"DMRD" + seq(1) + src(3) + dst(3) + rpt(4) + bits(1) + stream(4) + payload(33)

    The payload here is a raw UTF-16LE slice of the text (not BPTC-encoded).
    Real DMR radios will not always accept this - it is intended for our own
    receive path and any brand tooling that already handles unencoded UDT data
    (Anytone, some Hytera profiles).
    """
    payload_bytes = text.encode("utf-16-le")
    # pad to multiple of 33
    while len(payload_bytes) % 33:
        payload_bytes += b"\x00"

    stream_id = int.from_bytes(uuid.uuid4().bytes[:4], "big")
    bits = 0
    if slot == 2:
        bits |= 0x80
    if is_private:
        bits |= 0x40
    # frame type = data-sync (bits 5-4 = 10)
    bits |= 0x20

    frames: List[bytes] = []
    total = len(payload_bytes) // 33
    for seq, i in enumerate(range(0, len(payload_bytes), 33)):
        chunk = payload_bytes[i : i + 33]
        header = (
            b"DMRD"
            + bytes([seq & 0xFF])
            + src_id.to_bytes(3, "big")
            + dst_id.to_bytes(3, "big")
            + repeater_id.to_bytes(4, "big")
            + bytes([bits])
            + stream_id.to_bytes(4, "big")
        )
        frames.append(header + chunk)
    return frames


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
class MessageStore:
    def __init__(
        self,
        db,
        broadcast: Callable[[dict], Awaitable[None]],
        send_dmrd: Callable[[bytes], Awaitable[int]],
        server_dmr_id: int,
        data_slot: int,
    ):
        self.db = db
        self.broadcast = broadcast
        self.send_dmrd = send_dmrd
        self.server_dmr_id = server_dmr_id
        self.data_slot = data_slot

    async def ensure_indexes(self) -> None:
        await self.db.messages.create_index("timestamp")
        await self.db.messages.create_index("id", unique=True)
        await self.db.messages.create_index("org_id")

    async def list(self, limit: int = 200, org_ids: list[str] | None = None) -> List[dict]:
        q: dict = {}
        if org_ids is not None:
            q["org_id"] = {"$in": org_ids} if org_ids else "__none__"
        cursor = self.db.messages.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(limit)

    async def record_inbound(
        self,
        text: str,
        from_dmr_id: int,
        to_dmr_id: int,
        is_private: bool,
        talkgroup_id: Optional[int],
        callsign: Optional[str],
        repeater_id: Optional[int],
        org_id: Optional[str] = None,
        visible_to_org_ids: Optional[list] = None,
    ) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "visible_to_org_ids": visible_to_org_ids or ([org_id] if org_id else []),
            "direction": "in",
            "text": text,
            "from_dmr_id": from_dmr_id,
            "to_dmr_id": to_dmr_id if is_private else None,
            "talkgroup_id": talkgroup_id if not is_private else None,
            "callsign": callsign,
            "is_private": is_private,
            "repeater_id": repeater_id,
            "delivery_status": "received",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.messages.insert_one(doc)
        doc.pop("_id", None)
        await self.broadcast({"type": "message", "message": doc})
        return doc

    async def send(
        self,
        text: str,
        target_dmr_id: Optional[int],
        talkgroup_id: Optional[int],
        sender_email: str,
        org_id: Optional[str] = None,
        visible_to_org_ids: Optional[list] = None,
    ) -> dict:
        is_private = target_dmr_id is not None
        dst_id = target_dmr_id if is_private else (talkgroup_id or 0)
        frames = build_sms_dmrd_frames(
            src_id=self.server_dmr_id,
            dst_id=dst_id,
            is_private=is_private,
            slot=self.data_slot,
            text=text,
            repeater_id=self.server_dmr_id,
        )
        sent_to = 0
        for f in frames:
            sent_to = max(sent_to, await self.send_dmrd(f))

        doc = {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "visible_to_org_ids": visible_to_org_ids or ([org_id] if org_id else []),
            "direction": "out",
            "text": text,
            "from_dmr_id": self.server_dmr_id,
            "to_dmr_id": target_dmr_id,
            "talkgroup_id": talkgroup_id,
            "is_private": is_private,
            "sender": sender_email,
            "delivery_status": "sent" if sent_to > 0 else "queued",
            "reached_repeaters": sent_to,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.messages.insert_one(doc)
        doc.pop("_id", None)
        await self.broadcast({"type": "message", "message": doc})
        return doc
