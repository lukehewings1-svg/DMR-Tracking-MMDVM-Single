"""Event Sessions — bundle orgs + org-links + overlays + geofences into a
named event that can be one-click started/ended.

Life cycle:
    planned  -> start() -> active -> end() -> ended

On start(): create ACTIVE org-links between every pair of participant orgs
(fully connected, N*(N-1) directional links) with the event's `permissions`
+ `share` settings. Attached overlays are marked `active=True`.

On end(): every event-created link is REVOKED. Attached overlays are set
`active=False`. The event's document keeps `created_link_ids` for audit.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from tenancy import SHARE_KEYS, OrgLinkStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventStore:
    def __init__(self, db, org_link_store: OrgLinkStore, overlay_store):
        self.db = db
        self.org_link_store = org_link_store
        self.overlay_store = overlay_store
        self.col = db.events

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index("host_org_id")
        await self.col.create_index("participant_org_ids")
        await self.col.create_index("status")

    async def list(self, viewer_org_ids: Optional[list[str]] = None) -> list[dict]:
        q: dict = {}
        if viewer_org_ids is not None:
            q["$or"] = [
                {"host_org_id": {"$in": viewer_org_ids}},
                {"participant_org_ids": {"$in": viewer_org_ids}},
            ]
        cur = self.col.find(q, {"_id": 0}).sort("created_at", -1)
        return await cur.to_list(500)

    async def get(self, event_id: str) -> Optional[dict]:
        return await self.col.find_one({"id": event_id}, {"_id": 0})

    async def create(
        self,
        *,
        name: str,
        description: str,
        host_org_id: str,
        start_at: Optional[str],
        end_at: Optional[str],
        permissions: str,
        share: Optional[dict],
        created_by: str,
    ) -> dict:
        share_clean = {k: True for k in SHARE_KEYS}
        for k in SHARE_KEYS:
            if share and k in share:
                share_clean[k] = bool(share[k])
        doc = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "description": (description or "").strip(),
            "host_org_id": host_org_id,
            "start_at": start_at,
            "end_at": end_at,
            "status": "planned",
            "permissions": permissions,
            "share": share_clean,
            "participant_org_ids": [host_org_id],
            "overlay_ids": [],
            "geofence_ids": [],
            "created_link_ids": [],
            "started_at": None,
            "ended_at": None,
            "created_by": created_by,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update(self, event_id: str, patch: dict) -> Optional[dict]:
        allowed = {"name", "description", "start_at", "end_at", "permissions", "share"}
        clean = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if not clean:
            return await self.get(event_id)
        clean["updated_at"] = _now_iso()
        await self.col.update_one({"id": event_id}, {"$set": clean})
        return await self.get(event_id)

    async def add_participant(self, event_id: str, org_id: str) -> Optional[dict]:
        await self.col.update_one(
            {"id": event_id}, {"$addToSet": {"participant_org_ids": org_id},
                              "$set": {"updated_at": _now_iso()}}
        )
        return await self.get(event_id)

    async def remove_participant(self, event_id: str, org_id: str) -> Optional[dict]:
        ev = await self.get(event_id)
        if not ev:
            return None
        if ev.get("status") == "active":
            raise ValueError("Cannot remove a participant while the event is active — end the event first")
        if org_id == ev["host_org_id"]:
            raise ValueError("Cannot remove the host org from its own event")
        await self.col.update_one(
            {"id": event_id}, {"$pull": {"participant_org_ids": org_id},
                              "$set": {"updated_at": _now_iso()}}
        )
        return await self.get(event_id)

    async def attach_overlay(self, event_id: str, overlay_id: str) -> Optional[dict]:
        await self.col.update_one(
            {"id": event_id}, {"$addToSet": {"overlay_ids": overlay_id},
                              "$set": {"updated_at": _now_iso()}}
        )
        return await self.get(event_id)

    async def detach_overlay(self, event_id: str, overlay_id: str) -> Optional[dict]:
        await self.col.update_one(
            {"id": event_id}, {"$pull": {"overlay_ids": overlay_id},
                              "$set": {"updated_at": _now_iso()}}
        )
        return await self.get(event_id)

    async def attach_geofence(self, event_id: str, geofence_id: str) -> Optional[dict]:
        await self.col.update_one(
            {"id": event_id}, {"$addToSet": {"geofence_ids": geofence_id},
                              "$set": {"updated_at": _now_iso()}}
        )
        return await self.get(event_id)

    async def detach_geofence(self, event_id: str, geofence_id: str) -> Optional[dict]:
        await self.col.update_one(
            {"id": event_id}, {"$pull": {"geofence_ids": geofence_id},
                              "$set": {"updated_at": _now_iso()}}
        )
        return await self.get(event_id)

    # ----------------------------------------------------------------- #
    # Lifecycle
    # ----------------------------------------------------------------- #
    async def start(self, event_id: str, actor_email: str) -> dict:
        ev = await self.get(event_id)
        if not ev:
            raise ValueError("Event not found")
        if ev["status"] == "active":
            return ev
        if ev["status"] == "ended":
            raise ValueError("Event already ended — clone it instead")

        participants = list(dict.fromkeys(ev.get("participant_org_ids") or []))
        if len(participants) < 2:
            raise ValueError("Add at least one other participant org before starting")

        # Fully-connected: create an ACTIVE org-link from each participant to
        # every other participant, tagged with this event's id so we can
        # revoke exactly the ones we created on end().
        created_link_ids: list[str] = []
        for src in participants:
            for tgt in participants:
                if src == tgt:
                    continue
                link = await self.org_link_store.propose(
                    from_org_id=src,
                    to_org_id=tgt,
                    share=ev["share"],
                    permissions=ev["permissions"],
                    proposed_by=actor_email,
                    expires_at=ev.get("end_at"),
                    note=f"Event: {ev['name']}",
                )
                # Auto-approve immediately (event-authored links skip approval).
                await self.org_link_store.approve(link["id"], actor_email)
                await self.org_link_store.col.update_one(
                    {"id": link["id"]}, {"$set": {"event_id": event_id}}
                )
                created_link_ids.append(link["id"])

        # Activate attached overlays.
        for oid in ev.get("overlay_ids") or []:
            await self.overlay_store.update(oid, {"active": True})

        await self.col.update_one(
            {"id": event_id},
            {"$set": {
                "status": "active",
                "started_at": _now_iso(),
                "created_link_ids": created_link_ids,
                "updated_at": _now_iso(),
            }},
        )
        return await self.get(event_id)

    async def end(self, event_id: str) -> dict:
        ev = await self.get(event_id)
        if not ev:
            raise ValueError("Event not found")
        if ev["status"] != "active":
            raise ValueError(f"Cannot end an event that is {ev['status']}")

        for lid in ev.get("created_link_ids") or []:
            try:
                await self.org_link_store.revoke(lid)
            except Exception:  # noqa: BLE001
                pass

        for oid in ev.get("overlay_ids") or []:
            try:
                await self.overlay_store.update(oid, {"active": False})
            except Exception:  # noqa: BLE001
                pass

        await self.col.update_one(
            {"id": event_id},
            {"$set": {
                "status": "ended",
                "ended_at": _now_iso(),
                "updated_at": _now_iso(),
            }},
        )
        return await self.get(event_id)

    async def delete(self, event_id: str) -> None:
        ev = await self.get(event_id)
        if not ev:
            return
        if ev.get("status") == "active":
            raise ValueError("End the event before deleting it")
        # If ended, links are already revoked; we can safely remove doc.
        # If planned, no links exist yet.
        await self.col.delete_one({"id": event_id})

    async def maybe_auto_end(self) -> list[str]:
        """Called from a periodic task: end any ACTIVE event whose end_at
        has passed. Returns list of event ids that were ended.
        """
        now = datetime.now(timezone.utc).isoformat()
        cur = self.col.find(
            {"status": "active", "end_at": {"$ne": None, "$lte": now}}, {"_id": 0, "id": 1}
        )
        ended: list[str] = []
        async for doc in cur:
            try:
                await self.end(doc["id"])
                ended.append(doc["id"])
            except Exception:  # noqa: BLE001
                pass
        return ended
