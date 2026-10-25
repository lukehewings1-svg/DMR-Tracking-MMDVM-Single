"""Groups (talk groups) - each group binds a set of radios to a DMR talkgroup ID.

Radios inherit their group by DMR-ID assignment (admin sets radio.group_id).
UI filters roster/map by group_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List


class GroupStore:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db.groups.create_index("id", unique=True)
        await self.db.groups.create_index("talkgroup_id")

    async def seed_defaults(self) -> None:
        if await self.db.groups.count_documents({}) > 0:
            return
        defaults = [
            {"name": "Medical", "talkgroup_id": 91, "color": "#ff3b30", "icon": "Ambulance"},
            {"name": "Security", "talkgroup_id": 92, "color": "#00f0ff", "icon": "Shield"},
            {"name": "Ops", "talkgroup_id": 93, "color": "#39ff14", "icon": "Cog"},
            {"name": "Fire", "talkgroup_id": 94, "color": "#ffb800", "icon": "Flame"},
        ]
        for d in defaults:
            await self.create(d)

    async def list(self) -> List[dict]:
        cursor = self.db.groups.find({}, {"_id": 0}).sort("name", 1)
        return await cursor.to_list(500)

    async def get(self, group_id: str) -> dict | None:
        return await self.db.groups.find_one({"id": group_id}, {"_id": 0})

    async def get_by_talkgroup(self, tg: int) -> dict | None:
        return await self.db.groups.find_one({"talkgroup_id": int(tg)}, {"_id": 0})

    async def create(self, body: dict) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "name": body["name"],
            "talkgroup_id": int(body.get("talkgroup_id") or 0),
            "color": body.get("color") or "#39ff14",
            "icon": body.get("icon") or "Users",
            "description": body.get("description") or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.groups.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update(self, group_id: str, body: dict) -> dict | None:
        updates = {
            k: v
            for k, v in {
                "name": body.get("name"),
                "talkgroup_id": int(body["talkgroup_id"])
                if body.get("talkgroup_id") is not None
                else None,
                "color": body.get("color"),
                "icon": body.get("icon"),
                "description": body.get("description"),
            }.items()
            if v is not None
        }
        if not updates:
            return await self.get(group_id)
        await self.db.groups.update_one({"id": group_id}, {"$set": updates})
        return await self.get(group_id)

    async def delete(self, group_id: str) -> None:
        await self.db.groups.delete_one({"id": group_id})
        # unassign radios that were on this group
        await self.db.radios.update_many(
            {"group_id": group_id}, {"$unset": {"group_id": ""}}
        )
