"""Multi-tenant primitives: Organizations + Org-Links + visibility resolution.

Every domain document has an `org_id`. A user belongs to exactly ONE org. Two
orgs may establish an "org link" that shares selected resources one-way from
the source org to the target org, either read-only (`view`) or full
(`view+dispatch`, i.e. read + send SMS + PTT + acknowledge on the source
org's radios). Every event that touches shared resources is written into the
shift-log of EVERY org involved in the link, so all sides see the same
timeline.

Roles:
    super_admin - cross-org; manages orgs + links themselves. Not scoped.
    admin       - manages settings + users of their own org.
    user        - view + message + PTT + (org-toggleable) emergency-ack only.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional


SHARE_KEYS = ("radios", "positions", "messages", "voice", "overlays", "geofences", "emergencies")
PERMISSIONS = ("view", "view+dispatch")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Organization store
# --------------------------------------------------------------------------- #
class OrganizationStore:
    def __init__(self, db):
        self.db = db
        self.col = db.organizations

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index("slug", unique=True)

    async def list(self) -> list[dict]:
        return await self.col.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)

    async def get(self, org_id: str) -> Optional[dict]:
        return await self.col.find_one({"id": org_id}, {"_id": 0})

    async def get_by_slug(self, slug: str) -> Optional[dict]:
        return await self.col.find_one({"slug": slug.lower()}, {"_id": 0})

    async def get_by_repeater_password(self, password: str) -> Optional[dict]:
        return await self.col.find_one({"hb_password": password}, {"_id": 0})

    async def create(
        self,
        *,
        name: str,
        slug: Optional[str] = None,
        hb_password: Optional[str] = None,
        server_dmr_id: Optional[int] = None,
        user_can_ack_emergency: bool = True,
    ) -> dict:
        slug = (slug or name).lower().strip().replace(" ", "-")
        # Ensure slug is unique
        if await self.get_by_slug(slug):
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
        doc = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "slug": slug,
            "active": True,
            "hb_password": hb_password or secrets.token_urlsafe(12),
            "server_dmr_id": int(server_dmr_id or 9990001),
            "user_can_ack_emergency": bool(user_can_ack_emergency),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update(self, org_id: str, patch: dict) -> Optional[dict]:
        allowed = {"name", "active", "hb_password", "server_dmr_id", "user_can_ack_emergency"}
        clean = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if not clean:
            return await self.get(org_id)
        clean["updated_at"] = _now_iso()
        await self.col.update_one({"id": org_id}, {"$set": clean})
        return await self.get(org_id)

    async def rotate_hb_password(self, org_id: str) -> Optional[dict]:
        return await self.update(org_id, {"hb_password": secrets.token_urlsafe(12)})

    async def delete(self, org_id: str) -> None:
        await self.col.delete_one({"id": org_id})

    async def ensure_default(self) -> dict:
        """Create the 'Default' org on first startup and return it."""
        existing = await self.col.find_one({"slug": "default"}, {"_id": 0})
        if existing:
            return existing
        return await self.create(name="Default", slug="default")


# --------------------------------------------------------------------------- #
# Org-link store
# --------------------------------------------------------------------------- #
class OrgLinkStore:
    def __init__(self, db):
        self.db = db
        self.col = db.org_links

    async def ensure_indexes(self) -> None:
        await self.col.create_index("id", unique=True)
        await self.col.create_index([("from_org_id", 1), ("to_org_id", 1)])
        await self.col.create_index("to_org_id")

    def _default_share(self) -> dict:
        return {k: True for k in SHARE_KEYS}

    async def list(self, org_id: Optional[str] = None) -> list[dict]:
        q: dict = {}
        if org_id:
            q = {"$or": [{"from_org_id": org_id}, {"to_org_id": org_id}]}
        return await self.col.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

    async def get(self, link_id: str) -> Optional[dict]:
        return await self.col.find_one({"id": link_id}, {"_id": 0})

    async def propose(
        self,
        *,
        from_org_id: str,
        to_org_id: str,
        share: Optional[dict] = None,
        permissions: str = "view",
        proposed_by: str,
        expires_at: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        if from_org_id == to_org_id:
            raise ValueError("Cannot link an organization to itself")
        if permissions not in PERMISSIONS:
            raise ValueError("permissions must be one of: " + ", ".join(PERMISSIONS))
        share_clean = self._default_share()
        for k in SHARE_KEYS:
            if share and k in share:
                share_clean[k] = bool(share[k])
        doc = {
            "id": str(uuid.uuid4()),
            "from_org_id": from_org_id,
            "to_org_id": to_org_id,
            "status": "pending",
            "share": share_clean,
            "permissions": permissions,
            "proposed_by": proposed_by,
            "approved_by": None,
            "expires_at": expires_at,
            "note": note or "",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def approve(self, link_id: str, approver_email: str) -> Optional[dict]:
        await self.col.update_one(
            {"id": link_id},
            {"$set": {"status": "active", "approved_by": approver_email, "updated_at": _now_iso()}},
        )
        return await self.get(link_id)

    async def revoke(self, link_id: str) -> None:
        await self.col.update_one(
            {"id": link_id}, {"$set": {"status": "revoked", "updated_at": _now_iso()}}
        )

    async def delete(self, link_id: str) -> None:
        await self.col.delete_one({"id": link_id})

    async def update(self, link_id: str, patch: dict) -> Optional[dict]:
        allowed = {"share", "permissions", "expires_at", "note"}
        clean = {k: v for k, v in patch.items() if k in allowed and v is not None}
        if not clean:
            return await self.get(link_id)
        clean["updated_at"] = _now_iso()
        await self.col.update_one({"id": link_id}, {"$set": clean})
        return await self.get(link_id)

    def _link_expired(self, link: dict) -> bool:
        exp = link.get("expires_at")
        if not exp:
            return False
        try:
            return datetime.fromisoformat(exp) < datetime.now(timezone.utc)
        except ValueError:
            return False

    async def visible_source_orgs(self, viewer_org_id: str, resource: str) -> list[dict]:
        """Return the list of ACTIVE org-links whose `to_org_id` == viewer_org_id
        and whose `share[resource]` is True and are not expired.

        The viewer's org sees the source org's data for that resource.
        """
        if resource not in SHARE_KEYS:
            return []
        links = await self.col.find(
            {"to_org_id": viewer_org_id, "status": "active", f"share.{resource}": True},
            {"_id": 0},
        ).to_list(500)
        return [ln for ln in links if not self._link_expired(ln)]

    async def dispatch_source_orgs(self, viewer_org_id: str, resource: str) -> list[dict]:
        """Same as visible_source_orgs but only links with view+dispatch permission."""
        links = await self.visible_source_orgs(viewer_org_id, resource)
        return [ln for ln in links if ln.get("permissions") == "view+dispatch"]

    async def all_involved_orgs(self, primary_org_id: str, resource: str) -> list[str]:
        """Return list of every org_id that should see events for `resource` that
        originated in `primary_org_id` — i.e. primary + every org linked TO
        primary for this resource. Used for shift-log fan-out."""
        links = await self.col.find(
            {"from_org_id": primary_org_id, "status": "active", f"share.{resource}": True},
            {"_id": 0, "to_org_id": 1},
        ).to_list(500)
        return [primary_org_id] + [ln["to_org_id"] for ln in links]


# --------------------------------------------------------------------------- #
# Visibility resolver (used by every server.py read endpoint)
# --------------------------------------------------------------------------- #
async def visible_org_ids(user: dict, org_link_store: OrgLinkStore, resource: str) -> list[str]:
    """List of org_ids whose `resource` records the user is allowed to READ.

    - super_admin: unrestricted (returns None — treat as no filter).
    - admin / user: their own org + any org that has actively linked TO them
      with share[resource]=True.
    """
    if user.get("role") == "super_admin":
        return []  # empty sentinel means "no filter"; callers check for role first
    own = user.get("org_id")
    if not own:
        return []
    links = await org_link_store.visible_source_orgs(own, resource)
    return [own] + [ln["from_org_id"] for ln in links]


async def can_dispatch_org(
    user: dict, org_link_store: OrgLinkStore, target_org_id: str, resource: str
) -> bool:
    """Whether the user can WRITE (send / PTT / clear-emergency) to `target_org_id`
    for the given resource.

    - super_admin: always.
    - user/admin of target_org_id: always.
    - user/admin of a different org: only if there is an active link from
      target_org_id -> user's org with view+dispatch and share[resource]=True.
    """
    if user.get("role") == "super_admin":
        return True
    own = user.get("org_id")
    if not own:
        return False
    if own == target_org_id:
        return True
    links = await org_link_store.dispatch_source_orgs(own, resource)
    return any(ln["from_org_id"] == target_org_id for ln in links)


def build_org_filter(visible: list[str] | None) -> dict:
    """Turn a visible-org-ids list into a Mongo query fragment.

    None or empty list from a super_admin (empty sentinel) means "no filter";
    for a regular user with an empty allowed list this yields a match-nothing
    filter to be safe.
    """
    if visible is None:
        return {}
    if not visible:
        return {"org_id": {"$in": ["__none__"]}}  # match nothing
    return {"org_id": {"$in": visible}}
