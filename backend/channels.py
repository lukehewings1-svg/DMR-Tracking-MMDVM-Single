"""Channel labels for the two DMR timeslots.

In the unified-channel model each MMDVM timeslot is a full independent channel
carrying voice + GPS + SMS + emergencies. Slot 1 = Channel 1, Slot 2 =
Channel 2. Admins can rename them (e.g. "Ops Net" / "Search Team").
"""
from __future__ import annotations

from datetime import datetime, timezone


class ChannelStore:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db.channels.create_index("slot", unique=True)

    async def seed_defaults(self) -> None:
        for slot in (1, 2):
            await self.db.channels.update_one(
                {"slot": slot},
                {
                    "$setOnInsert": {
                        "slot": slot,
                        "name": f"Channel {slot}",
                        "description": "",
                        "color": "#39ff14" if slot == 1 else "#00f0ff",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )

    async def list(self) -> list[dict]:
        cursor = self.db.channels.find({}, {"_id": 0}).sort("slot", 1)
        return await cursor.to_list(10)

    async def get(self, slot: int) -> dict | None:
        return await self.db.channels.find_one({"slot": slot}, {"_id": 0})

    async def update(self, slot: int, body: dict) -> dict | None:
        updates = {
            k: v
            for k, v in {
                "name": body.get("name"),
                "description": body.get("description"),
                "color": body.get("color"),
            }.items()
            if v is not None
        }
        if updates:
            await self.db.channels.update_one({"slot": slot}, {"$set": updates})
        return await self.get(slot)
