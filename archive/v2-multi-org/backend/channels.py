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
        await self.db.channels.create_index("org_id")

    async def seed_defaults(self, org_id: str) -> None:
        for i, cid_suffix in enumerate(("slot-1", "slot-2")):
            # Legacy default rows (no org_id) get promoted to the Default org
            # so we don't create duplicate slot-1/slot-2 rows.
            existing = await self.db.channels.find_one({"id": cid_suffix, "org_id": {"$in": [None, org_id]}})
            if existing:
                if not existing.get("org_id"):
                    await self.db.channels.update_one(
                        {"_id": existing["_id"]}, {"$set": {"org_id": org_id}}
                    )
                continue
            org_cid = f"{cid_suffix}-{org_id[:8]}"
            await self.db.channels.update_one(
                {"id": org_cid},
                {
                    "$setOnInsert": {
                        "id": org_cid,
                        "org_id": org_id,
                        "builtin_slot": i + 1,
                        "name": f"Channel {i + 1}",
                        "color": DEFAULT_COLORS[i],
                        "description": "",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )

    async def list(self, org_ids: list[str] | None = None) -> list[dict]:
        q: dict = {}
        if org_ids is not None:
            q["org_id"] = {"$in": org_ids} if org_ids else "__none__"
        cursor = self.db.channels.find(q, {"_id": 0}).sort("created_at", 1)
        return await cursor.to_list(200)

    async def get(self, channel_id: str) -> dict | None:
        return await self.db.channels.find_one({"id": channel_id}, {"_id": 0})

    async def create(self, org_id: str, body: dict) -> dict:
        doc = {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
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
        # Built-in slot channels are undeletable.
        ch = await self.get(channel_id)
        if ch and ch.get("builtin_slot") in (1, 2):
            raise ValueError("cannot delete built-in slot channel")
        await self.db.channels.delete_one({"id": channel_id})
        # Unbind from any repeater configs
        await self.db.repeater_configs.update_many(
            {"slot1_channel_id": channel_id}, {"$unset": {"slot1_channel_id": ""}}
        )
        await self.db.repeater_configs.update_many(
            {"slot2_channel_id": channel_id}, {"$unset": {"slot2_channel_id": ""}}
        )

    async def default_for_org(self, org_id: str, slot: int) -> str | None:
        """Look up the org's built-in channel id for a given slot (1 or 2)."""
        ch = await self.db.channels.find_one(
            {"org_id": org_id, "builtin_slot": slot}, {"_id": 0, "id": 1}
        )
        return ch["id"] if ch else None


class RepeaterConfigStore:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        await self.db.repeater_configs.create_index("repeater_id", unique=True)
        await self.db.repeater_configs.create_index("org_id")

    async def list(self, org_ids: list[str] | None = None) -> list[dict]:
        q: dict = {}
        if org_ids is not None:
            q["org_id"] = {"$in": org_ids} if org_ids else "__none__"
        cursor = self.db.repeater_configs.find(q, {"_id": 0}).sort("repeater_id", 1)
        return await cursor.to_list(200)

    async def get(self, repeater_id: int) -> dict | None:
        return await self.db.repeater_configs.find_one(
            {"repeater_id": int(repeater_id)}, {"_id": 0}
        )

    async def upsert(self, repeater_id: int, org_id: str, body: dict) -> dict:
        rid = int(repeater_id)
        doc = {
            "repeater_id": rid,
            "org_id": org_id,
            "name": body.get("name") or f"MMDVM {rid}",
            "notes": body.get("notes") or "",
            "slot1_channel_id": body.get("slot1_channel_id"),
            "slot2_channel_id": body.get("slot2_channel_id"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.repeater_configs.update_one(
            {"repeater_id": rid}, {"$set": doc}, upsert=True
        )
        return await self.get(rid)

    async def delete(self, repeater_id: int) -> None:
        await self.db.repeater_configs.delete_one({"repeater_id": int(repeater_id)})

    async def channel_for_slot(self, repeater_id: int, slot: int) -> str | None:
        cfg = await self.get(repeater_id)
        if not cfg:
            return None
        return cfg.get("slot1_channel_id") if slot == 1 else cfg.get("slot2_channel_id")

    async def slot_for_channel(self, repeater_id: int, channel_id: str) -> int | None:
        cfg = await self.get(repeater_id)
        if not cfg:
            return None
        if cfg.get("slot1_channel_id") == channel_id:
            return 1
        if cfg.get("slot2_channel_id") == channel_id:
            return 2
        return None

    async def org_for_repeater(self, repeater_id: int) -> str | None:
        cfg = await self.get(repeater_id)
        return cfg.get("org_id") if cfg else None
