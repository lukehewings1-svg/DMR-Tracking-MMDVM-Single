"""Event overlays.

An admin creates named "overlay sets" (one per event/deployment). Each set can
contain:

* Drawn annotations: markers, polylines, polygons and circles with a name,
  colour and description. Persisted as raw geometry (leaflet-geoman-friendly
  dicts) so the frontend can round-trip them without conversion.
* Image overlays: an uploaded PNG/JPG pinned to a lat/lon bounding box.
  Rendered by Leaflet's imageOverlay with adjustable opacity.

Only overlay sets flagged `active` show up on dispatcher + situational views.
Every logged-in user (and any situational-awareness token) can *read* active
overlays; only admins can create, edit, activate or delete them.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OverlayStore:
    """MongoDB-backed CRUD for event overlay sets."""

    def __init__(self, db, uploads_url_prefix: str = "/api/uploads/overlays") -> None:
        self.db = db
        self.col = db.overlays
        self.uploads_url_prefix = uploads_url_prefix.rstrip("/")

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index("active")

    def _new_doc(self, name: str, created_by: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "active": False,
            "shapes": [],
            "images": [],
            "created_by": created_by,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }

    async def create(self, *, name: str, created_by: str) -> dict:
        doc = self._new_doc(name, created_by)
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list(self, *, only_active: bool = False) -> list[dict]:
        q = {"active": True} if only_active else {}
        cur = self.col.find(q, {"_id": 0}).sort("created_at", -1)
        return await cur.to_list(200)

    async def get(self, overlay_id: str) -> Optional[dict]:
        return await self.col.find_one({"id": overlay_id}, {"_id": 0})

    async def update(self, overlay_id: str, patch: dict) -> Optional[dict]:
        patch = {k: v for k, v in patch.items() if k in {"name", "active"}}
        if not patch:
            return await self.get(overlay_id)
        patch["updated_at"] = _now_iso()
        await self.col.update_one({"id": overlay_id}, {"$set": patch})
        return await self.get(overlay_id)

    async def delete(self, overlay_id: str) -> Optional[dict]:
        doc = await self.get(overlay_id)
        if not doc:
            return None
        await self.col.delete_one({"id": overlay_id})
        return doc

    async def replace_shapes(self, overlay_id: str, shapes: list[dict]) -> Optional[dict]:
        """Wholesale replacement — geoman fires many small events per drag/edit,
        the frontend batches and PUTs the full array."""
        clean: list[dict] = []
        for s in shapes:
            if not isinstance(s, dict):
                continue
            stype = s.get("type")
            if stype not in {"marker", "polyline", "polygon", "circle", "rectangle"}:
                continue
            clean.append(
                {
                    "id": s.get("id") or str(uuid.uuid4()),
                    "type": stype,
                    "name": (s.get("name") or "").strip()[:64],
                    "description": (s.get("description") or "").strip()[:500],
                    "color": s.get("color") or "#00f0ff",
                    "geometry": s.get("geometry") or {},
                    "style": s.get("style") or {},
                }
            )
        await self.col.update_one(
            {"id": overlay_id},
            {"$set": {"shapes": clean, "updated_at": _now_iso()}},
        )
        return await self.get(overlay_id)

    async def add_image(
        self,
        overlay_id: str,
        *,
        name: str,
        url: str,
        bounds: list,
        opacity: float,
    ) -> Optional[dict]:
        image = {
            "id": str(uuid.uuid4()),
            "name": name.strip()[:64] or "Overlay image",
            "url": url,
            "bounds": bounds,
            "opacity": max(0.0, min(1.0, float(opacity))),
        }
        await self.col.update_one(
            {"id": overlay_id},
            {
                "$push": {"images": image},
                "$set": {"updated_at": _now_iso()},
            },
        )
        return await self.get(overlay_id)

    async def update_image(
        self,
        overlay_id: str,
        image_id: str,
        patch: dict,
    ) -> Optional[dict]:
        set_ops: dict[str, Any] = {"updated_at": _now_iso()}
        if "bounds" in patch and patch["bounds"]:
            set_ops["images.$.bounds"] = patch["bounds"]
        if "opacity" in patch and patch["opacity"] is not None:
            set_ops["images.$.opacity"] = max(0.0, min(1.0, float(patch["opacity"])))
        if "name" in patch and patch["name"]:
            set_ops["images.$.name"] = str(patch["name"]).strip()[:64]
        await self.col.update_one(
            {"id": overlay_id, "images.id": image_id},
            {"$set": set_ops},
        )
        return await self.get(overlay_id)

    async def delete_image(self, overlay_id: str, image_id: str) -> Optional[dict]:
        await self.col.update_one(
            {"id": overlay_id},
            {
                "$pull": {"images": {"id": image_id}},
                "$set": {"updated_at": _now_iso()},
            },
        )
        return await self.get(overlay_id)
