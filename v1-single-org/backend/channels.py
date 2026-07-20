"""Channels + per-repeater channel-to-slot mapping.

Legacy channels seeded as {id: "slot-1", name: "Channel 1"} and {id: "slot-2",
name: "Channel 2"} to preserve back-compat with earlier iterations. New
channels created via the API get a uuid id.

RepeaterConfig binds a physical MMDVM (identified by its repeater_id) to two
channel_ids - one per timeslot. The HB Master looks these up at ingest time to
know which channel each incoming frame belongs to and where to relay voice.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


DEFAULT_COLORS = ("#39ff14", "#00f0ff", "#ffb800", "#c084fc", "#f472b6", "#ff3b30")


class ChannelStore:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        # Migrate any legacy `slot`-keyed docs to id="slot-N" BEFORE creating
        # the unique index, so old rows without an id field don't collide.
        async for legacy in self.db.channels.find({"id": {"$exists": False}}):
            slot = legacy.get("slot")
            if slot in (1, 2):
                await self.db.channels.update_one(
                    {"_id": legacy["_id"]},
                    {"$set": {"id": f"slot-{slot}"}, "$unset": {"slot": ""}},
                )
            else:
                await self.db.channels.delete_one({"_id": legacy["_id"]})
        await self.db.channels.create_index("id", unique=True)

    async def seed_defaults(self) -> None:
        for i, cid in enumerate(("slot-1", "slot-2")):
            await self.db.channels.update_one(
                {"id": cid},
                {
                    "$setOnInsert": {
                        "id": cid,
                        "name": f"Channel {i + 1}",
                        "color": DEFAULT_COLORS[i],
                        "description": "",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )

    async def list(self) -> list[dict]:
        cursor = self.db.channels.find({}, {"_id": 0}).sort("created_at", 1)
        return await cursor.to_list(200)

    async def get(self, channel_id: str) -> dict | None:
        return await self.db.channels.find_one({"id": channel_id}, {"_id": 0})

    async def create(self, body: dict) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "name": body["name"],
            "color": body.get("color") or "#39ff14",
            "description": body.get("description") or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.channels.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update(self, channel_id: str, body: dict) -> dict | None:
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
            await self.db.channels.update_one({"id": channel_id}, {"$set": updates})
        return await self.get(channel_id)

    async def delete(self, channel_id: str) -> None:
        # Legacy slot-1 / slot-2 are undeletable so filter behavior stays intact.
        if channel_id in ("slot-1", "slot-2"):
            raise ValueError("cannot delete built-in slot channel")
        await self.db.channels.delete_one({"id": channel_id})
        # Unbind from any repeater configs
        await self.db.repeater_configs.update_many(
            {"slot1_channel_id": channel_id}, {"$set": {"slot1_channel_id": "slot-1"}}
        )
        await self.db.repeater_configs.update_many(
            {"slot2_channel_id": channel_id}, {"$set": {"slot2_channel_id": "slot-2"}}
        )


class RepeaterConfigStore:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db.repeater_configs.create_index("repeater_id", unique=True)

    async def list(self) -> list[dict]:
        cursor = self.db.repeater_configs.find({}, {"_id": 0}).sort("repeater_id", 1)
        return await cursor.to_list(200)

    async def get(self, repeater_id: int) -> dict | None:
        return await self.db.repeater_configs.find_one(
            {"repeater_id": int(repeater_id)}, {"_id": 0}
        )

    async def upsert(self, repeater_id: int, body: dict) -> dict:
        rid = int(repeater_id)
        doc = {
            "repeater_id": rid,
            "name": body.get("name") or f"MMDVM {rid}",
            "notes": body.get("notes") or "",
            "slot1_channel_id": body.get("slot1_channel_id") or "slot-1",
            "slot2_channel_id": body.get("slot2_channel_id") or "slot-2",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.repeater_configs.update_one(
            {"repeater_id": rid}, {"$set": doc}, upsert=True
        )
        return await self.get(rid)

    async def delete(self, repeater_id: int) -> None:
        await self.db.repeater_configs.delete_one({"repeater_id": int(repeater_id)})

    async def channel_for_slot(self, repeater_id: int, slot: int) -> str:
        cfg = await self.get(repeater_id)
        if not cfg:
            return f"slot-{slot}"
        return (cfg.get("slot1_channel_id") if slot == 1 else cfg.get("slot2_channel_id")) or f"slot-{slot}"

    async def slot_for_channel(self, repeater_id: int, channel_id: str) -> int | None:
        cfg = await self.get(repeater_id)
        if not cfg:
            if channel_id == "slot-1":
                return 1
            if channel_id == "slot-2":
                return 2
            return None
        if cfg.get("slot1_channel_id") == channel_id:
            return 1
        if cfg.get("slot2_channel_id") == channel_id:
            return 2
        return None
