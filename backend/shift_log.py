"""Auto-persisted timeline of every noteworthy event on the net.

Feeds from every ingest hook (position, emergency, message, voice activity,
geofence alert) so that post-incident reviews and compliance reporting come
for free. CSV export is a stream response so exports of many-hour shifts stay
memory-friendly.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional


EVENT_TYPES = (
    "position",
    "emergency",
    "emergency_cleared",
    "message_in",
    "message_out",
    "voice",
    "alert",
    "radio_update",
)


class ShiftLogStore:
    def __init__(self, db, broadcast: Callable[[dict], Awaitable[None]]):
        self.db = db
        self.broadcast = broadcast
        self._voice_streams_seen: dict[int, float] = {}  # stream_id -> ts (dedupe voice bursts)

    async def ensure_indexes(self) -> None:
        await self.db.shift_log.create_index("ts")
        await self.db.shift_log.create_index("event_type")
        await self.db.shift_log.create_index("dmr_id")
        await self.db.shift_log.create_index("group_id")

    async def _log(
        self,
        event_type: str,
        summary: str,
        *,
        dmr_id: Optional[int] = None,
        callsign: Optional[str] = None,
        group_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        actor: Optional[str] = None,
        subject: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> None:
        doc = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "summary": summary,
            "dmr_id": dmr_id,
            "callsign": callsign,
            "group_id": group_id,
            "channel_id": channel_id,
            "actor": actor,
            "subject": subject,
            "meta": meta or {},
        }
        await self.db.shift_log.insert_one(doc)
        doc.pop("_id", None)
        await self.broadcast({"type": "shift_log", "entry": doc})

    # ------------- Hooks called from server.py ------------- #
    async def log_position(self, packet: dict) -> None:
        await self._log(
            "position",
            f"{packet.get('callsign') or 'ID '+str(packet['dmr_id'])} @ {packet['lat']:.5f}, {packet['lon']:.5f}",
            dmr_id=packet["dmr_id"],
            callsign=packet.get("callsign"),
            group_id=packet.get("group_id"),
            channel_id=packet.get("channel_id"),
            subject=packet.get("format"),
        )

    async def log_emergency(self, emg: dict) -> None:
        await self._log(
            "emergency",
            f"EMERGENCY from {emg.get('callsign') or 'ID '+str(emg['dmr_id'])}",
            dmr_id=emg.get("dmr_id"),
            callsign=emg.get("callsign"),
            group_id=emg.get("group_id"),
            subject=emg.get("signature"),
            meta={"lat": emg.get("last_lat"), "lon": emg.get("last_lon")},
        )

    async def log_emergency_cleared(self, dmr_id: int, admin_email: str) -> None:
        await self._log(
            "emergency_cleared",
            f"Emergency for ID {dmr_id} cleared by {admin_email}",
            dmr_id=dmr_id,
            actor=admin_email,
        )

    async def log_message(self, msg: dict) -> None:
        direction = msg.get("direction")
        etype = "message_in" if direction == "in" else "message_out"
        if direction == "in":
            summary = f"IN from {msg.get('callsign') or 'ID '+str(msg.get('from_dmr_id'))}: {msg['text'][:80]}"
            dmr_id = msg.get("from_dmr_id")
        else:
            target = (
                f"ID {msg.get('to_dmr_id')}"
                if msg.get("is_private")
                else f"TG {msg.get('talkgroup_id')}"
            )
            summary = f"OUT {msg.get('sender','')} -> {target}: {msg['text'][:80]}"
            dmr_id = msg.get("to_dmr_id")
        await self._log(
            etype,
            summary,
            dmr_id=dmr_id,
            actor=msg.get("sender"),
            subject=str(msg.get("talkgroup_id") or ""),
            meta={"text": msg["text"], "channel": msg.get("channel")},
        )

    async def log_voice(self, evt: dict) -> None:
        """De-duplicate: only log once per (stream_id) per 10-second window."""
        import time
        sid = evt.get("stream_id")
        now = time.time()
        # Prune old
        self._voice_streams_seen = {
            k: v for k, v in self._voice_streams_seen.items() if now - v < 30
        }
        if sid in self._voice_streams_seen:
            return
        self._voice_streams_seen[sid] = now
        tg = evt.get("talkgroup_id")
        callsign = evt.get("callsign")
        await self._log(
            "voice",
            f"Voice TX by {callsign or 'ID '+str(evt.get('src_dmr_id'))} on {'TG ' + str(tg) if tg else 'private'}",
            dmr_id=evt.get("src_dmr_id"),
            callsign=callsign,
            channel_id=evt.get("channel_id"),
            subject=str(tg) if tg else "private",
            meta={"repeater_id": evt.get("repeater_id"), "relayed_to": evt.get("relayed_to")},
        )

    async def log_alert(self, alert: dict) -> None:
        await self._log(
            "alert",
            f"{alert.get('callsign') or 'ID '+str(alert['dmr_id'])} {alert['event']}ed {alert['fence_name']}",
            dmr_id=alert.get("dmr_id"),
            callsign=alert.get("callsign"),
            subject=alert.get("fence_name"),
            meta={"lat": alert.get("lat"), "lon": alert.get("lon"), "event": alert["event"]},
        )

    async def log_radio_update(self, dmr_id: int, updates: dict, actor: str) -> None:
        await self._log(
            "radio_update",
            f"Radio ID {dmr_id} updated ({', '.join(updates.keys())})",
            dmr_id=dmr_id,
            actor=actor,
            meta=updates,
        )

    # ------------- Queries ------------- #
    async def query(
        self,
        limit: int = 500,
        event_type: Optional[str] = None,
        dmr_id: Optional[int] = None,
        group_ids: Optional[list[str]] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> list[dict]:
        q: dict = {}
        if event_type:
            q["event_type"] = event_type
        if dmr_id is not None:
            q["dmr_id"] = dmr_id
        if group_ids is not None:
            # dispatcher ACL: include entries with group_id in allowed OR entries
            # not tied to any group (system-wide events like emergencies without
            # a group_id).
            q["$or"] = [{"group_id": {"$in": group_ids}}, {"group_id": None}]
        if since or until:
            ts_q: dict = {}
            if since:
                ts_q["$gte"] = since
            if until:
                ts_q["$lte"] = until
            q["ts"] = ts_q
        cursor = self.db.shift_log.find(q, {"_id": 0}).sort("ts", -1).limit(min(limit, 5000))
        return await cursor.to_list(min(limit, 5000))

    async def clear(self) -> None:
        await self.db.shift_log.delete_many({})

    # ------------- CSV ------------- #
    async def export_csv(self, **query_kwargs) -> str:
        entries = await self.query(limit=5000, **query_kwargs)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "timestamp",
                "event_type",
                "summary",
                "dmr_id",
                "callsign",
                "group_id",
                "channel_id",
                "actor",
                "subject",
            ]
        )
        for e in entries:
            w.writerow(
                [
                    e.get("ts"),
                    e.get("event_type"),
                    e.get("summary"),
                    e.get("dmr_id"),
                    e.get("callsign"),
                    e.get("group_id"),
                    e.get("channel_id"),
                    e.get("actor"),
                    e.get("subject"),
                ]
            )
        return buf.getvalue()
