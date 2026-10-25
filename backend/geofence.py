"""Geofence + alert logic for the DMR tracker.

A geofence is a circle: {name, lat, lon, radius_m, alert_on: enter|exit|both}.
For every incoming packet we compute whether each radio is currently inside a
given fence and emit an alert whenever that state transitions in a direction
the fence cares about.

State transitions are stored per (fence_id, dmr_id) in `fence_state` so alerts
survive backend restarts.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable, List

_EARTH_RADIUS_M = 6371008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


class GeofenceEngine:
    def __init__(self, db, broadcast: Callable[[dict], Awaitable[None]]):
        self.db = db
        self.broadcast = broadcast

    async def list_geofences(self) -> List[dict]:
        cursor = self.db.geofences.find({}, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(200)

    async def create(self, body: dict) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "name": body["name"],
            "lat": float(body["lat"]),
            "lon": float(body["lon"]),
            "radius_m": float(body["radius_m"]),
            "alert_on": body.get("alert_on", "both"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.geofences.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def delete(self, geofence_id: str) -> None:
        await self.db.geofences.delete_one({"id": geofence_id})
        await self.db.fence_state.delete_many({"fence_id": geofence_id})

    async def alerts(self, limit: int = 100) -> List[dict]:
        cursor = self.db.alerts.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(limit)

    async def clear_alerts(self) -> None:
        await self.db.alerts.delete_many({})

    async def evaluate(self, packet: dict) -> None:
        """Called from record_packet with the freshly recorded position."""
        lat, lon = packet.get("lat"), packet.get("lon")
        if lat is None or lon is None:
            return
        dmr_id = packet["dmr_id"]
        fences = await self.db.geofences.find({}, {"_id": 0}).to_list(200)
        for f in fences:
            inside = haversine_m(lat, lon, f["lat"], f["lon"]) <= f["radius_m"]
            state = await self.db.fence_state.find_one(
                {"fence_id": f["id"], "dmr_id": dmr_id}
            )
            prev_inside = state.get("inside", False) if state else False
            event = None
            if inside and not prev_inside:
                event = "enter"
            elif not inside and prev_inside:
                event = "exit"
            await self.db.fence_state.update_one(
                {"fence_id": f["id"], "dmr_id": dmr_id},
                {"$set": {"inside": inside, "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            if event and f.get("alert_on", "both") in (event, "both"):
                alert = {
                    "id": str(uuid.uuid4()),
                    "fence_id": f["id"],
                    "fence_name": f["name"],
                    "dmr_id": dmr_id,
                    "callsign": packet.get("callsign"),
                    "event": event,
                    "lat": lat,
                    "lon": lon,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await self.db.alerts.insert_one(alert)
                alert.pop("_id", None)
                await self.broadcast({"type": "alert", "alert": alert})
