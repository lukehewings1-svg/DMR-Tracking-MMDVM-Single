"""Read-only, token-locked "situational awareness" view.

Admins can mint a URL like /situational/<token> that shows a live map + active
emergencies to anonymous viewers (command post big-screen, EOC staff, briefings).
Tokens are read-only, cannot see roster metadata, packet log, messaging, admin,
or any write endpoint, and can be scoped to a single group or the whole net.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expired(doc: dict) -> bool:
    expires_at = doc.get("expires_at")
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) < datetime.now(timezone.utc)
    except ValueError:
        return False


class SituationalTokenStore:
    """MongoDB-backed CRUD for situational-awareness tokens."""

    def __init__(self, db) -> None:
        self.db = db
        self.col = db.situational_tokens

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index("token", unique=True)

    async def create(self, *, name: str, group_id: Optional[str], expires_at: Optional[str], created_by: str) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "token": secrets.token_urlsafe(24),
            "name": name.strip(),
            "group_id": group_id,
            "expires_at": expires_at,
            "created_by": created_by,
            "created_at": _now_iso(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list(self) -> list[dict]:
        cur = self.col.find({}, {"_id": 0}).sort("created_at", -1)
        return await cur.to_list(500)

    async def delete(self, token_id: str) -> None:
        await self.col.delete_one({"id": token_id})

    async def get_by_token(self, token: str) -> Optional[dict]:
        doc = await self.col.find_one({"token": token}, {"_id": 0})
        if not doc:
            return None
        if _expired(doc):
            return None
        return doc

    async def snapshot(self, doc: dict, radios_col, emergencies_col) -> dict:
        """Build the initial state payload sent to a public viewer.

        Returns *only* the fields safe to expose: dmr_id, callsign, group_id,
        last position + timestamp, in_emergency flag, icon + color.
        """
        radio_query: dict = {}
        if doc.get("group_id"):
            radio_query["group_id"] = doc["group_id"]
        radios = await radios_col.find(
            radio_query,
            {
                "_id": 0,
                "dmr_id": 1,
                "callsign": 1,
                "group_id": 1,
                "icon": 1,
                "color": 1,
                "last_lat": 1,
                "last_lon": 1,
                "last_seen": 1,
                "in_emergency": 1,
                "emergency_id": 1,
            },
        ).sort("last_seen", -1).to_list(500)

        em_query: dict = {"status": "active"}
        if doc.get("group_id"):
            em_query["group_id"] = doc["group_id"]
        emergencies = await emergencies_col.find(
            em_query,
            {
                "_id": 0,
                "id": 1,
                "dmr_id": 1,
                "callsign": 1,
                "group_id": 1,
                "last_lat": 1,
                "last_lon": 1,
                "timestamp": 1,
            },
        ).sort("timestamp", -1).to_list(100)

        return {
            "view": {
                "name": doc["name"],
                "group_id": doc.get("group_id"),
                "expires_at": doc.get("expires_at"),
                "server_time": _now_iso(),
            },
            "radios": radios,
            "emergencies": emergencies,
        }


def public_radio_projection(radio: dict) -> dict:
    """Trim a radio dict to only the fields safe to broadcast to a public viewer."""
    return {
        "dmr_id": radio.get("dmr_id"),
        "callsign": radio.get("callsign"),
        "group_id": radio.get("group_id"),
        "icon": radio.get("icon"),
        "color": radio.get("color"),
        "last_lat": radio.get("last_lat") if "last_lat" in radio else radio.get("lat"),
        "last_lon": radio.get("last_lon") if "last_lon" in radio else radio.get("lon"),
        "last_seen": radio.get("last_seen") if "last_seen" in radio else radio.get("timestamp"),
        "in_emergency": radio.get("in_emergency", False),
    }


def public_emergency_projection(emg: dict) -> dict:
    return {
        "id": emg.get("id"),
        "dmr_id": emg.get("dmr_id"),
        "callsign": emg.get("callsign"),
        "group_id": emg.get("group_id"),
        "last_lat": emg.get("last_lat"),
        "last_lon": emg.get("last_lon"),
        "timestamp": emg.get("timestamp"),
    }
