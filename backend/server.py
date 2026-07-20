"""FastAPI server for the DMR radio tracker (multi-tenant edition).

Every domain document has an `org_id`. A user belongs to exactly one org and
sees only their own org's data + any orgs actively linked to them. A
super_admin transcends orgs and can manage every org + link.

Role capabilities:
    super_admin: create/delete orgs, org-links, all admin capabilities across
                 every org.
    admin      : full CRUD inside own org (settings, users, radio metadata,
                 groups, channels, repeaters, geofences, overlays, situational
                 tokens, org-link proposals + approvals for own org, clear
                 emergencies, purge shift log).
    user       : view + message + PTT + (org-toggleable) emergency-ack only.
                 Cannot change any settings.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

import auth
from auth import (
    LoginPayload,
    RegisterPayload,
    RolePayload,
    UserPublic,
    get_current_admin,
    get_current_super_admin,
    get_current_user,
    hash_password,
    login_user,
    register_user,
    to_public,
)
from channels import ChannelStore, RepeaterConfigStore
from dmr_ingest import HBMaster, start_hb_master
from dmr_parsers import parse_gps_payload, parser_names
from geofence import GeofenceEngine
from groups import GroupStore
from messaging import MessageStore
from shift_log import ShiftLogStore, EVENT_TYPES
from overlays import OverlayStore
from situational import (
    SituationalTokenStore,
    public_emergency_projection,
    public_radio_projection,
)
from tenancy import (
    OrganizationStore,
    OrgLinkStore,
    SHARE_KEYS,
    build_org_filter,
    can_dispatch_org,
    visible_org_ids,
)
from voice import VoiceGateway

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("dmr-tracker")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
HB_BIND_HOST = os.environ.get("HB_BIND_HOST", "0.0.0.0")
HB_BIND_PORT = int(os.environ.get("HB_BIND_PORT", "62031"))
HB_PASSWORD = os.environ.get("HB_PASSWORD", "PASSWORD")  # legacy fallback
SERVER_DMR_ID = int(os.environ.get("SERVER_DMR_ID", "9990001"))
DATA_SLOT = int(os.environ.get("DATA_SLOT", "1"))
MAX_PACKETS_BUFFER = 500
MAX_POSITIONS_PER_RADIO = 500

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
auth.bind_db(db)

packet_log: Deque[dict] = deque(maxlen=MAX_PACKETS_BUFFER)
# Authenticated WS clients: each is {"ws": WebSocket, "user": dict}
ws_clients: list[dict] = []
# Public read-only WS viewers keyed by their token document id.
public_ws_clients: list[dict] = []

hb_master: Optional[HBMaster] = None
hb_transport: Optional[asyncio.DatagramTransport] = None
geofence_engine: Optional[GeofenceEngine] = None
group_store: Optional[GroupStore] = None
channel_store: Optional[ChannelStore] = None
repeater_config_store: Optional[RepeaterConfigStore] = None
message_store: Optional[MessageStore] = None
shift_log: Optional[ShiftLogStore] = None
overlay_store: Optional[OverlayStore] = None
situational_store: Optional[SituationalTokenStore] = None
org_store: Optional[OrganizationStore] = None
org_link_store: Optional[OrgLinkStore] = None
voice_gateway = VoiceGateway()

_default_org_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class InjectPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dmr_id: int
    callsign: Optional[str] = None
    lat: float
    lon: float
    format: str = "SIMULATED"
    talkgroup_id: Optional[int] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    rssi: Optional[int] = None
    group_id: Optional[str] = None
    channel: Optional[int] = Field(default=1, ge=1, le=2)


class InjectRawPayload(BaseModel):
    dmr_id: int
    callsign: Optional[str] = None
    hex: str


class RadioMeta(BaseModel):
    callsign: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = None
    group_id: Optional[str] = None


class GeofenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    lat: float
    lon: float
    radius_m: float = Field(gt=0, le=1_000_000)
    alert_on: str = Field(default="both", pattern="^(enter|exit|both)$")


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    talkgroup_id: int = Field(ge=1, le=16777215)
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    talkgroup_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=48)
    description: Optional[str] = None
    color: Optional[str] = None


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    color: Optional[str] = None
    description: Optional[str] = None


class RepeaterConfigBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None
    slot1_channel_id: Optional[str] = None
    slot2_channel_id: Optional[str] = None
    org_id: Optional[str] = None  # super_admin can reassign


class UserGroupsPayload(BaseModel):
    allowed_group_ids: list[str] = Field(default_factory=list)


class UserOrgPayload(BaseModel):
    org_id: str


class MessageSend(BaseModel):
    text: str = Field(min_length=1, max_length=256)
    target_dmr_id: Optional[int] = None
    group_id: Optional[str] = None
    channel: Optional[int] = Field(default=None, ge=1, le=2)


class InboundSMSInject(BaseModel):
    from_dmr_id: int
    text: str
    talkgroup_id: Optional[int] = None
    to_dmr_id: Optional[int] = None


class VoicePttStart(BaseModel):
    target_dmr_id: Optional[int] = None
    group_id: Optional[str] = None


class EmergencyInject(BaseModel):
    dmr_id: int
    talkgroup_id: Optional[int] = None


class SituationalTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    group_id: Optional[str] = None
    expires_at: Optional[str] = None


class OverlayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class OverlayUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    active: Optional[bool] = None


class OverlayShape(BaseModel):
    id: Optional[str] = None
    type: str
    name: Optional[str] = ""
    description: Optional[str] = ""
    color: Optional[str] = "#00f0ff"
    geometry: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)


class OverlayShapesReplace(BaseModel):
    shapes: list[OverlayShape]


class OverlayImageUpdate(BaseModel):
    bounds: Optional[list] = None
    opacity: Optional[float] = None
    name: Optional[str] = None


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    slug: Optional[str] = None
    hb_password: Optional[str] = None
    server_dmr_id: Optional[int] = None
    user_can_ack_emergency: Optional[bool] = True


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    hb_password: Optional[str] = None
    server_dmr_id: Optional[int] = None
    user_can_ack_emergency: Optional[bool] = None


class OrgAdminBootstrap(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    callsign: Optional[str] = None


class OrgLinkCreate(BaseModel):
    from_org_id: str
    to_org_id: str
    permissions: str = Field(default="view", pattern="^(view|view\\+dispatch)$")
    share: Optional[dict] = None
    expires_at: Optional[str] = None
    note: Optional[str] = None


class OrgLinkUpdate(BaseModel):
    share: Optional[dict] = None
    permissions: Optional[str] = Field(default=None, pattern="^(view|view\\+dispatch)$")
    expires_at: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_admin_for_org(user: dict, target_org_id: Optional[str]) -> None:
    """Raise 403 unless user is super_admin, or admin of target_org_id."""
    if user.get("role") == "super_admin":
        return
    if user.get("role") == "admin" and user.get("org_id") == target_org_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized for this organization")


async def _user_visible_orgs(user: dict, resource: str) -> Optional[list[str]]:
    """Returns list of org_ids user can read for the resource, or None for super_admin."""
    if user.get("role") == "super_admin":
        return None
    return await visible_org_ids(user, org_link_store, resource)


async def _fan_out_orgs(primary_org_id: Optional[str], resource: str) -> list[str]:
    """Every org that should see this event (source + all linked-to)."""
    if not primary_org_id or not org_link_store:
        return [primary_org_id] if primary_org_id else []
    return await org_link_store.all_involved_orgs(primary_org_id, resource)


async def _broadcast(message: dict, resource: str = "positions") -> None:
    """Send `message` to every WS client that (a) is super_admin, or (b) has
    the message's org_id inside their visible-orgs for `resource`.
    """
    # Auto-log geofence alerts into the shift log.
    if shift_log and message.get("type") == "alert":
        try:
            visible = await _fan_out_orgs(
                (message.get("alert") or {}).get("org_id"), "geofences"
            )
            await shift_log.log_alert(message["alert"], visible_to_org_ids=visible)
        except Exception:  # noqa: BLE001
            pass

    # Extract the event's originating org_id (best effort)
    payload = (
        message.get("packet")
        or message.get("emergency")
        or message.get("message")
        or message.get("activity")
        or message.get("alert")
        or message.get("overlay")
        or message.get("entry")
        or {}
    )
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        payload = {}
    msg_org_id = message.get("org_id") or payload.get("org_id")

    dead = []
    for wc in list(ws_clients):
        user = wc.get("user") or {}
        try:
            if user.get("role") == "super_admin":
                await wc["ws"].send_json(message)
                continue
            if not msg_org_id:
                # System-wide events (e.g. shift_log_cleared, channels_changed):
                # send to everyone.
                await wc["ws"].send_json(message)
                continue
            allowed = await _user_visible_orgs(user, resource)
            if allowed is not None and msg_org_id not in (allowed or []):
                continue
            await wc["ws"].send_json(message)
        except Exception:  # noqa: BLE001
            dead.append(wc)
    for wc in dead:
        if wc in ws_clients:
            ws_clients.remove(wc)

    # Fan out sanitised subset to any public "situational awareness" viewers
    await _broadcast_public(message)


async def _broadcast_public(message: dict) -> None:
    if not public_ws_clients:
        return
    mtype = message.get("type")
    public_msg: Optional[dict] = None
    filter_group: Optional[str] = None
    filter_org: Optional[str] = None

    if mtype == "packet":
        pkt = message.get("packet") or {}
        radio = {
            "dmr_id": pkt.get("dmr_id"),
            "callsign": pkt.get("callsign"),
            "group_id": pkt.get("group_id"),
            "org_id": pkt.get("org_id"),
            "icon": pkt.get("icon"),
            "color": pkt.get("color"),
            "lat": pkt.get("lat"),
            "lon": pkt.get("lon"),
            "timestamp": pkt.get("timestamp"),
        }
        public_msg = {"type": "position", "radio": public_radio_projection(radio)}
        filter_group = pkt.get("group_id")
        filter_org = pkt.get("org_id")
    elif mtype == "emergency":
        emg = message.get("emergency") or {}
        public_msg = {"type": "emergency", "emergency": public_emergency_projection(emg)}
        filter_group = emg.get("group_id")
        filter_org = emg.get("org_id")
    elif mtype == "emergency_cleared":
        public_msg = {
            "type": "emergency_cleared",
            "emergency_id": message.get("emergency_id"),
            "dmr_id": message.get("dmr_id"),
        }
        filter_org = message.get("org_id")
    elif mtype == "clear":
        public_msg = {"type": "clear"}
    elif mtype == "overlay_upserted":
        overlay = message.get("overlay") or {}
        if overlay.get("active"):
            public_msg = {"type": "overlay_upserted", "overlay": overlay}
        else:
            public_msg = {"type": "overlay_removed", "overlay_id": overlay.get("id")}
        filter_org = overlay.get("org_id")
    elif mtype == "overlay_removed":
        public_msg = {"type": "overlay_removed", "overlay_id": message.get("overlay_id")}
        filter_org = message.get("org_id")
    else:
        return

    dead: list[dict] = []
    for viewer in list(public_ws_clients):
        td = viewer["token_doc"]
        group_scope = td.get("group_id")
        org_scope = td.get("org_id")
        if group_scope and filter_group is not None and group_scope != filter_group:
            continue
        if org_scope and filter_org is not None and org_scope != filter_org:
            continue
        try:
            await viewer["ws"].send_json(public_msg)
        except Exception:  # noqa: BLE001
            dead.append(viewer)
    for v in dead:
        if v in public_ws_clients:
            public_ws_clients.remove(v)


# --------------------------------------------------------------------------- #
# Packet + message + voice sinks (wired into HBMaster)
# --------------------------------------------------------------------------- #
async def record_packet(packet: dict) -> None:
    packet.setdefault("id", str(uuid.uuid4()))
    packet.setdefault("timestamp", _now_iso())

    dmr_id = packet.get("dmr_id")
    if dmr_id is None:
        return

    pkt_org = packet.get("org_id") or _default_org_id
    packet["org_id"] = pkt_org

    packet_log.appendleft(packet)

    existing = await db.radios.find_one({"dmr_id": dmr_id, "org_id": pkt_org}, {"_id": 0})
    callsign = packet.get("callsign") or (existing.get("callsign") if existing else None)
    icon = (existing.get("icon") if existing else None) or "Radio"
    color = (existing.get("color") if existing else None) or "#39ff14"
    group_id = packet.get("group_id") or (existing.get("group_id") if existing else None)

    tg = packet.get("talkgroup_id")
    if not group_id and tg and group_store:
        g = await group_store.get_by_talkgroup(tg, org_id=pkt_org)
        if g:
            group_id = g["id"]
            color = existing.get("color") if existing else g.get("color") or color
            icon = existing.get("icon") if existing else g.get("icon") or icon

    await db.radios.update_one(
        {"dmr_id": dmr_id, "org_id": pkt_org},
        {
            "$set": {
                "dmr_id": dmr_id,
                "org_id": pkt_org,
                "callsign": callsign,
                "icon": icon,
                "color": color,
                "group_id": group_id,
                "last_lat": packet["lat"],
                "last_lon": packet["lon"],
                "last_seen": packet["timestamp"],
                "last_format": packet["format"],
                "last_speed": packet.get("speed"),
                "last_heading": packet.get("heading"),
                "last_rssi": packet.get("rssi"),
                "last_source": packet.get("source", "MMDVM"),
                "last_talkgroup": tg,
                "last_repeater_id": packet.get("repeater_id"),
                "last_channel": packet.get("channel") or 1,
            },
            "$setOnInsert": {"first_seen": packet["timestamp"]},
            "$inc": {"position_count": 1},
        },
        upsert=True,
    )

    await db.positions.insert_one(
        {
            "id": packet["id"],
            "org_id": pkt_org,
            "dmr_id": dmr_id,
            "lat": packet["lat"],
            "lon": packet["lon"],
            "timestamp": packet["timestamp"],
            "format": packet["format"],
            "speed": packet.get("speed"),
            "heading": packet.get("heading"),
            "rssi": packet.get("rssi"),
            "channel": packet.get("channel") or 1,
        }
    )

    count = await db.positions.count_documents({"dmr_id": dmr_id, "org_id": pkt_org})
    if count > MAX_POSITIONS_PER_RADIO:
        excess = count - MAX_POSITIONS_PER_RADIO
        old = await db.positions.find(
            {"dmr_id": dmr_id, "org_id": pkt_org}, {"id": 1}
        ).sort("timestamp", 1).to_list(excess)
        old_ids = [d["id"] for d in old]
        if old_ids:
            await db.positions.delete_many({"id": {"$in": old_ids}})

    packet["callsign"] = callsign
    packet["group_id"] = group_id
    await _broadcast({"type": "packet", "packet": packet}, resource="positions")
    if shift_log:
        visible = await _fan_out_orgs(pkt_org, "positions")
        await shift_log.log_position(packet, org_id=pkt_org, visible_to_org_ids=visible)
    if geofence_engine:
        await geofence_engine.evaluate(packet)


async def on_dmr_sms(inbound: dict) -> None:
    if not message_store:
        return
    org_id = inbound.get("org_id") or _default_org_id
    radio = await db.radios.find_one(
        {"dmr_id": inbound["from_dmr_id"], "org_id": org_id}, {"_id": 0, "callsign": 1}
    )
    visible = await _fan_out_orgs(org_id, "messages")
    msg = await message_store.record_inbound(
        text=inbound["text"],
        from_dmr_id=inbound["from_dmr_id"],
        to_dmr_id=inbound["to_dmr_id"],
        is_private=inbound["is_private"],
        talkgroup_id=inbound.get("talkgroup_id"),
        callsign=(radio or {}).get("callsign"),
        repeater_id=inbound.get("repeater_id"),
        org_id=org_id,
        visible_to_org_ids=visible,
    )
    if shift_log:
        await shift_log.log_message(msg, visible_to_org_ids=visible)


async def on_voice_activity(evt: dict) -> None:
    org_id = evt.get("org_id") or _default_org_id
    radio = await db.radios.find_one(
        {"dmr_id": evt["src_dmr_id"], "org_id": org_id}, {"_id": 0, "callsign": 1}
    )
    tg = evt.get("talkgroup_id")
    voice_gateway.track(
        talkgroup_id=tg or 0,
        src_id=evt["src_dmr_id"],
        callsign=(radio or {}).get("callsign"),
        repeater_id=evt["repeater_id"],
    )
    await _broadcast(
        {"type": "voice_activity", "activity": voice_gateway.active_talkgroups(), "org_id": org_id},
        resource="voice",
    )
    if shift_log:
        visible = await _fan_out_orgs(org_id, "voice")
        evt = {**evt, "callsign": (radio or {}).get("callsign"), "org_id": org_id}
        await shift_log.log_voice(evt, visible_to_org_ids=visible)


async def on_emergency(evt: dict) -> None:
    src_id = evt["src_dmr_id"]
    org_id = evt.get("org_id") or _default_org_id
    radio = await db.radios.find_one({"dmr_id": src_id, "org_id": org_id}, {"_id": 0}) or {}
    ts = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "dmr_id": src_id,
        "callsign": radio.get("callsign"),
        "group_id": radio.get("group_id"),
        "last_lat": radio.get("last_lat"),
        "last_lon": radio.get("last_lon"),
        "talkgroup_id": evt.get("talkgroup_id"),
        "repeater_id": evt.get("repeater_id"),
        "signature": evt.get("signature"),
        "is_private": evt.get("is_private"),
        "status": "active",
        "timestamp": ts,
    }
    await db.emergencies.insert_one(doc)
    await db.radios.update_one(
        {"dmr_id": src_id, "org_id": org_id},
        {"$set": {"in_emergency": True, "emergency_at": ts, "emergency_id": doc["id"]}},
        upsert=True,
    )
    doc.pop("_id", None)
    await _broadcast({"type": "emergency", "emergency": doc}, resource="emergencies")
    if shift_log:
        visible = await _fan_out_orgs(org_id, "emergencies")
        await shift_log.log_emergency(doc, visible_to_org_ids=visible)


async def send_dmrd_broadcast(frame: bytes) -> int:
    if not hb_master:
        return 0
    return await hb_master.broadcast_dmrd(frame)


# --------------------------------------------------------------------------- #
# Migration: backfill org_id on existing docs
# --------------------------------------------------------------------------- #
async def _backfill_org_ids(default_org_id: str) -> None:
    """Stamp org_id on every legacy doc that predates multi-tenant."""
    collections = [
        "users", "radios", "positions", "messages", "shift_log",
        "geofences", "alerts", "fence_state", "emergencies", "overlays",
        "situational_tokens", "channels", "repeater_configs", "groups",
    ]
    for name in collections:
        try:
            await db[name].update_many(
                {"org_id": {"$exists": False}},
                {"$set": {"org_id": default_org_id}},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Backfill failed for %s: %s", name, exc)


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    global hb_master, hb_transport, geofence_engine, group_store, channel_store
    global repeater_config_store, message_store, shift_log, overlay_store
    global situational_store, org_store, org_link_store, _default_org_id

    org_store = OrganizationStore(db)
    await org_store.ensure_indexes()
    org_link_store = OrgLinkStore(db)
    await org_link_store.ensure_indexes()
    default_org = await org_store.ensure_default()
    _default_org_id = default_org["id"]

    # Backfill BEFORE user/index setup so seed_admin can attach admin to Default
    await _backfill_org_ids(_default_org_id)

    await auth.ensure_indexes()
    await auth.seed_admin(default_org_id=_default_org_id)

    geofence_engine = GeofenceEngine(db, _broadcast)
    group_store = GroupStore(db)
    await group_store.ensure_indexes()
    await group_store.seed_defaults(_default_org_id)
    channel_store = ChannelStore(db)
    await channel_store.ensure_indexes()
    await channel_store.seed_defaults(_default_org_id)
    repeater_config_store = RepeaterConfigStore(db)
    await repeater_config_store.ensure_indexes()
    message_store = MessageStore(
        db=db,
        broadcast=_broadcast,
        send_dmrd=send_dmrd_broadcast,
        server_dmr_id=SERVER_DMR_ID,
        data_slot=DATA_SLOT,
    )
    await message_store.ensure_indexes()
    shift_log = ShiftLogStore(db, _broadcast)
    await shift_log.ensure_indexes()
    situational_store = SituationalTokenStore(db)
    await situational_store.ensure_indexes()
    overlay_store = OverlayStore(db)
    await overlay_store.ensure_indexes()

    async def _repeater_org_resolver(repeater_id: int) -> Optional[dict]:
        """Return the org doc that owns this MMDVM (via repeater_configs)."""
        cfg = await repeater_config_store.get(repeater_id)
        if not cfg or not cfg.get("org_id"):
            # Fallback: default org if repeater unregistered
            return default_org
        return await org_store.get(cfg["org_id"])

    try:
        hb_transport, hb_master = await start_hb_master(
            HB_BIND_HOST,
            HB_BIND_PORT,
            HB_PASSWORD,
            record_packet,
            on_dmr_sms,
            on_voice_activity,
            on_emergency,
            channel_router=repeater_config_store,
            org_resolver=_repeater_org_resolver,
        )
    except OSError as exc:
        logger.warning("HB Master could not bind to %s:%s (%s).", HB_BIND_HOST, HB_BIND_PORT, exc)
        hb_transport = None
        hb_master = None
    yield
    if hb_transport is not None:
        hb_transport.close()
    client.close()


app = FastAPI(title="DMR GPS Tracker (Multi-Org)", lifespan=lifespan)
api_router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
# Public + auth
# --------------------------------------------------------------------------- #
@api_router.get("/")
async def root():
    return {"service": "dmr-tracker", "version": "2.0", "mode": "multi-tenant"}


async def _hydrate_user(user: dict) -> dict:
    """Attach org_name for display."""
    if user.get("org_id") and org_store:
        org = await org_store.get(user["org_id"])
        if org:
            user["org_name"] = org.get("name")
    return user


@api_router.get("/status")
async def status(user: dict = Depends(get_current_user)):
    q_radio = build_org_filter(await _user_visible_orgs(user, "positions"))
    q_pos = q_radio
    return {
        "listener": {
            "bind": f"{HB_BIND_HOST}:{HB_BIND_PORT}",
            "running": hb_transport is not None,
            "stats": hb_master.snapshot() if hb_master else None,
        },
        "parsers": parser_names(),
        "voice": voice_gateway.status(),
        "server_dmr_id": SERVER_DMR_ID,
        "radios_tracked": await db.radios.count_documents(q_radio),
        "positions_stored": await db.positions.count_documents(q_pos),
        "packet_buffer": len(packet_log),
        "server_time": _now_iso(),
    }


@api_router.post("/auth/register", response_model=UserPublic)
async def api_register(payload: RegisterPayload):
    # New sign-ups default to the "Default" org and pending status; the org's
    # admin (or super_admin) approves.
    return await register_user(payload, default_org_id=_default_org_id)


@api_router.post("/auth/login")
async def api_login(payload: LoginPayload, request: Request):
    ip = request.client.host if request.client else "unknown"
    result = await login_user(payload, ip)
    result["user"] = await _hydrate_user(result["user"])
    return result


@api_router.get("/auth/me", response_model=UserPublic)
async def api_me(user: dict = Depends(get_current_user)):
    return await _hydrate_user(to_public(user))


@api_router.post("/auth/logout")
async def api_logout(_: dict = Depends(get_current_user)):
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Super-admin: Organizations
# --------------------------------------------------------------------------- #
@api_router.get("/orgs")
async def orgs_list(user: dict = Depends(get_current_user)):
    """super_admin sees every org, everyone else sees only their own."""
    if user.get("role") == "super_admin":
        return await org_store.list()
    if user.get("org_id"):
        org = await org_store.get(user["org_id"])
        return [org] if org else []
    return []


@api_router.post("/orgs")
async def orgs_create(body: OrgCreate, _: dict = Depends(get_current_super_admin)):
    org = await org_store.create(**body.model_dump(exclude_none=True))
    # Seed the new org with its own default channels + groups
    await channel_store.seed_defaults(org["id"])
    await group_store.seed_defaults(org["id"])
    await _broadcast({"type": "org_upserted", "org": org})
    return org


@api_router.patch("/orgs/{org_id}")
async def orgs_update(org_id: str, body: OrgUpdate, user: dict = Depends(get_current_user)):
    # super_admin can edit any field; an org's admin can edit their own org's
    # user_can_ack_emergency + name only.
    _require_admin_for_org(user, org_id)
    patch = body.model_dump(exclude_none=True)
    if user.get("role") != "super_admin":
        patch = {k: v for k, v in patch.items() if k in ("name", "user_can_ack_emergency")}
    updated = await org_store.update(org_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _broadcast({"type": "org_upserted", "org": updated})
    return updated


@api_router.post("/orgs/{org_id}/rotate-hb-password")
async def orgs_rotate_password(org_id: str, _: dict = Depends(get_current_super_admin)):
    updated = await org_store.rotate_hb_password(org_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Organization not found")
    return updated


@api_router.post("/orgs/{org_id}/bootstrap-admin", response_model=UserPublic)
async def orgs_bootstrap_admin(
    org_id: str,
    body: OrgAdminBootstrap,
    _: dict = Depends(get_current_super_admin),
):
    """Create the first admin user for a newly-created org."""
    org = await org_store.get(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(body.password),
        "callsign": body.callsign,
        "role": "admin",
        "status": "approved",
        "org_id": org_id,
        "created_at": _now_iso(),
    }
    await db.users.insert_one(user_doc)
    user_doc.pop("password_hash", None)
    return await _hydrate_user(to_public(user_doc))


@api_router.delete("/orgs/{org_id}")
async def orgs_delete(org_id: str, _: dict = Depends(get_current_super_admin)):
    if org_id == _default_org_id:
        raise HTTPException(status_code=400, detail="Cannot delete the Default organization")
    await org_store.delete(org_id)
    # Cascade: revoke every org-link involving this org
    await db.org_links.delete_many(
        {"$or": [{"from_org_id": org_id}, {"to_org_id": org_id}]}
    )
    await _broadcast({"type": "org_removed", "org_id": org_id})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Org-Links (inter-org resource sharing)
# --------------------------------------------------------------------------- #
@api_router.get("/org-links")
async def org_links_list(user: dict = Depends(get_current_user)):
    if user.get("role") == "super_admin":
        return await org_link_store.list()
    return await org_link_store.list(org_id=user.get("org_id"))


@api_router.post("/org-links")
async def org_links_create(body: OrgLinkCreate, user: dict = Depends(get_current_user)):
    # An org's admin can propose links FROM their org. super_admin can propose
    # anywhere.
    _require_admin_for_org(user, body.from_org_id)
    try:
        link = await org_link_store.propose(
            from_org_id=body.from_org_id,
            to_org_id=body.to_org_id,
            share=body.share,
            permissions=body.permissions,
            proposed_by=user["email"],
            expires_at=body.expires_at,
            note=body.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _broadcast({"type": "org_link_upserted", "link": link})
    return link


@api_router.post("/org-links/{link_id}/approve")
async def org_links_approve(link_id: str, user: dict = Depends(get_current_user)):
    link = await org_link_store.get(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    # The RECIPIENT org's admin approves.
    _require_admin_for_org(user, link["to_org_id"])
    updated = await org_link_store.approve(link_id, user["email"])
    await _broadcast({"type": "org_link_upserted", "link": updated})
    return updated


@api_router.patch("/org-links/{link_id}")
async def org_links_update(link_id: str, body: OrgLinkUpdate, user: dict = Depends(get_current_user)):
    link = await org_link_store.get(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    _require_admin_for_org(user, link["from_org_id"])
    updated = await org_link_store.update(link_id, body.model_dump(exclude_none=True))
    await _broadcast({"type": "org_link_upserted", "link": updated})
    return updated


@api_router.post("/org-links/{link_id}/revoke")
async def org_links_revoke(link_id: str, user: dict = Depends(get_current_user)):
    link = await org_link_store.get(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    # Either side of a link can revoke it.
    if user.get("role") != "super_admin" and user.get("org_id") not in (
        link["from_org_id"], link["to_org_id"]
    ):
        raise HTTPException(status_code=403, detail="Not a party to this link")
    await org_link_store.revoke(link_id)
    updated = await org_link_store.get(link_id)
    await _broadcast({"type": "org_link_upserted", "link": updated})
    return updated


@api_router.delete("/org-links/{link_id}")
async def org_links_delete(link_id: str, _: dict = Depends(get_current_super_admin)):
    await org_link_store.delete(link_id)
    await _broadcast({"type": "org_link_removed", "link_id": link_id})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Admin users (org-scoped for admin, cross-org for super_admin)
# --------------------------------------------------------------------------- #
def _user_query_for_admin(user: dict) -> dict:
    if user.get("role") == "super_admin":
        return {}
    return {"org_id": user.get("org_id")}


@api_router.get("/admin/users", response_model=List[UserPublic])
async def admin_list_users(user: dict = Depends(get_current_admin)):
    q = _user_query_for_admin(user)
    cursor = db.users.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    docs = await cursor.to_list(500)
    return [await _hydrate_user(to_public(d)) for d in docs]


async def _admin_target_user(admin: dict, user_id: str) -> dict:
    tgt = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not tgt:
        raise HTTPException(status_code=404, detail="User not found")
    if admin.get("role") != "super_admin" and tgt.get("org_id") != admin.get("org_id"):
        raise HTTPException(status_code=403, detail="Not in your organization")
    return tgt


@api_router.post("/admin/users/{user_id}/approve", response_model=UserPublic)
async def admin_approve(user_id: str, admin: dict = Depends(get_current_admin)):
    await _admin_target_user(admin, user_id)
    await db.users.update_one({"id": user_id}, {"$set": {"status": "approved"}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return await _hydrate_user(to_public(updated))


@api_router.post("/admin/users/{user_id}/reject", response_model=UserPublic)
async def admin_reject(user_id: str, admin: dict = Depends(get_current_admin)):
    await _admin_target_user(admin, user_id)
    await db.users.update_one({"id": user_id}, {"$set": {"status": "rejected"}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return await _hydrate_user(to_public(updated))


@api_router.post("/admin/users/{user_id}/role", response_model=UserPublic)
async def admin_set_role(user_id: str, body: RolePayload, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"] and body.role != admin.get("role"):
        raise HTTPException(status_code=400, detail="You cannot change your own role")
    await _admin_target_user(admin, user_id)
    # Only super_admin can grant super_admin.
    if body.role == "super_admin" and admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can promote to super_admin")
    await db.users.update_one({"id": user_id}, {"$set": {"role": body.role}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return await _hydrate_user(to_public(updated))


@api_router.post("/admin/users/{user_id}/groups", response_model=UserPublic)
async def admin_set_user_groups(user_id: str, body: UserGroupsPayload, admin: dict = Depends(get_current_admin)):
    await _admin_target_user(admin, user_id)
    await db.users.update_one(
        {"id": user_id}, {"$set": {"allowed_group_ids": body.allowed_group_ids}}
    )
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return await _hydrate_user(to_public(updated))


@api_router.post("/admin/users/{user_id}/org", response_model=UserPublic)
async def admin_set_user_org(user_id: str, body: UserOrgPayload, _: dict = Depends(get_current_super_admin)):
    await db.users.update_one({"id": user_id}, {"$set": {"org_id": body.org_id}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return await _hydrate_user(to_public(updated))


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
    await _admin_target_user(admin, user_id)
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Radios (org-scoped read; admin-only write)
# --------------------------------------------------------------------------- #
@api_router.get("/radios")
async def list_radios(
    group_id: Optional[str] = None,
    channel: Optional[int] = None,
    user: dict = Depends(get_current_user),
):
    q: dict = {}
    visible = await _user_visible_orgs(user, "radios")
    if visible is not None:
        q.update(build_org_filter(visible))
    if group_id:
        q["group_id"] = group_id
    if channel:
        q["last_channel"] = channel
    allowed = user.get("allowed_group_ids") or []
    if user.get("role") == "user" and allowed:
        if not group_id:
            q["group_id"] = {"$in": allowed}
        elif group_id not in allowed:
            q["group_id"] = {"$in": []}
    cursor = db.radios.find(q, {"_id": 0}).sort("last_seen", -1)
    return await cursor.to_list(500)


@api_router.get("/radios/{dmr_id}/positions")
async def radio_positions(dmr_id: int, limit: int = 200, user: dict = Depends(get_current_user)):
    q: dict = {"dmr_id": dmr_id}
    visible = await _user_visible_orgs(user, "positions")
    if visible is not None:
        q.update(build_org_filter(visible))
    cursor = db.positions.find(q, {"_id": 0}).sort("timestamp", 1).limit(min(limit, MAX_POSITIONS_PER_RADIO))
    return await cursor.to_list(MAX_POSITIONS_PER_RADIO)


@api_router.patch("/radios/{dmr_id}")
async def update_radio(dmr_id: int, meta: RadioMeta, user: dict = Depends(get_current_admin)):
    """Radio metadata is a SETTING — admin-only."""
    q: dict = {"dmr_id": dmr_id}
    if user.get("role") != "super_admin":
        q["org_id"] = user.get("org_id")
    updates = {k: v for k, v in meta.model_dump(exclude_unset=True).items() if v is not None or k == "group_id"}
    if not updates:
        return {"ok": True}
    result = await db.radios.update_one(q, {"$set": updates}, upsert=False)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Radio not found")
    radio = await db.radios.find_one(q, {"_id": 0, "org_id": 1})
    org_id = (radio or {}).get("org_id")
    await _broadcast({"type": "radio_update", "dmr_id": dmr_id, "updates": updates, "org_id": org_id})
    if shift_log:
        visible = await _fan_out_orgs(org_id, "radios")
        await shift_log.log_radio_update(dmr_id, updates, user["email"], org_id=org_id, visible_to_org_ids=visible)
    return {"ok": True}


@api_router.delete("/radios/{dmr_id}")
async def delete_radio(dmr_id: int, user: dict = Depends(get_current_admin)):
    q: dict = {"dmr_id": dmr_id}
    if user.get("role") != "super_admin":
        q["org_id"] = user.get("org_id")
    await db.radios.delete_one(q)
    await db.positions.delete_many(q)
    return {"ok": True}


@api_router.delete("/radios")
async def clear_all(user: dict = Depends(get_current_admin)):
    q: dict = {}
    if user.get("role") != "super_admin":
        q["org_id"] = user.get("org_id")
    await db.radios.delete_many(q)
    await db.positions.delete_many(q)
    await db.fence_state.delete_many(q if user.get("role") == "super_admin" else {})
    packet_log.clear()
    await _broadcast({"type": "clear", "org_id": user.get("org_id")})
    return {"ok": True}


@api_router.get("/packets")
async def get_packets(limit: int = 200, user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "positions")
    all_pkts = list(packet_log)
    if visible is not None:
        all_pkts = [p for p in all_pkts if p.get("org_id") in visible]
    return all_pkts[: min(limit, MAX_PACKETS_BUFFER)]


@api_router.post("/inject")
async def inject(payload: InjectPayload, user: dict = Depends(get_current_user)):
    """Simulated packet injection — tag with the user's org."""
    packet = {
        "source": "SIM",
        "source_addr": "simulated",
        "dmr_id": payload.dmr_id,
        "callsign": payload.callsign,
        "org_id": user.get("org_id") or _default_org_id,
        "lat": payload.lat,
        "lon": payload.lon,
        "format": payload.format,
        "speed": payload.speed,
        "heading": payload.heading,
        "rssi": payload.rssi,
        "group_id": payload.group_id,
        "talkgroup_id": payload.talkgroup_id,
        "channel": payload.channel or 1,
    }
    await record_packet(packet)
    return {"ok": True, "id": packet["id"]}


@api_router.post("/inject-raw")
async def inject_raw(payload: InjectRawPayload, user: dict = Depends(get_current_user)):
    try:
        raw = bytes.fromhex(payload.hex.strip().replace(" ", ""))
    except ValueError:
        return {"ok": False, "error": "invalid hex"}
    result = parse_gps_payload(raw)
    if not result:
        return {"ok": False, "error": "no parser matched"}
    packet = {
        "source": "RAW",
        "source_addr": "raw-inject",
        "dmr_id": payload.dmr_id,
        "callsign": payload.callsign,
        "org_id": user.get("org_id") or _default_org_id,
        "lat": result["lat"],
        "lon": result["lon"],
        "format": result["format"],
        "speed": result.get("speed"),
        "heading": result.get("heading"),
        "hex_preview": raw[:24].hex(),
    }
    await record_packet(packet)
    return {"ok": True, "format": result["format"]}


# --------------------------------------------------------------------------- #
# Repeaters (MMDVMs)
# --------------------------------------------------------------------------- #
@api_router.get("/repeaters")
async def list_repeaters(user: dict = Depends(get_current_user)):
    if not hb_master:
        return []
    snap = hb_master.snapshot()
    sessions = snap["sessions"]
    if user.get("role") == "super_admin":
        return sessions
    # Enrich sessions with org_id from repeater_config; filter to user's visible
    visible = await _user_visible_orgs(user, "radios") or []
    out = []
    for s in sessions:
        cfg = await repeater_config_store.get(s["repeater_id"])
        s["org_id"] = cfg.get("org_id") if cfg else None
        if s["org_id"] in visible:
            out.append(s)
    return out


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #
@api_router.get("/channels")
async def api_list_channels(user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "positions")
    return await channel_store.list(org_ids=visible)


@api_router.post("/channels")
async def api_create_channel(body: ChannelCreate, user: dict = Depends(get_current_admin)):
    org_id = user.get("org_id") or _default_org_id
    ch = await channel_store.create(org_id, body.model_dump())
    await _broadcast({"type": "channels_changed", "org_id": org_id})
    return ch


@api_router.patch("/channels/{channel_id}")
async def api_update_channel(channel_id: str, body: ChannelUpdate, user: dict = Depends(get_current_admin)):
    ch = await channel_store.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    _require_admin_for_org(user, ch.get("org_id"))
    ch = await channel_store.update(channel_id, body.model_dump(exclude_unset=True))
    await _broadcast({"type": "channels_changed", "org_id": ch.get("org_id")})
    return ch


@api_router.delete("/channels/{channel_id}")
async def api_delete_channel(channel_id: str, user: dict = Depends(get_current_admin)):
    ch = await channel_store.get(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    _require_admin_for_org(user, ch.get("org_id"))
    try:
        await channel_store.delete(channel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _broadcast({"type": "channels_changed", "org_id": ch.get("org_id")})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Repeater configs
# --------------------------------------------------------------------------- #
@api_router.get("/repeater-configs")
async def api_list_repeater_configs(user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "radios")
    return await repeater_config_store.list(org_ids=visible)


@api_router.put("/repeater-configs/{repeater_id}")
async def api_upsert_repeater_config(
    repeater_id: int, body: RepeaterConfigBody, user: dict = Depends(get_current_admin)
):
    # An admin can only assign their own org unless super_admin
    body_dict = body.model_dump(exclude_unset=True)
    target_org = body_dict.get("org_id") or user.get("org_id") or _default_org_id
    _require_admin_for_org(user, target_org)
    body_dict.pop("org_id", None)
    cfg = await repeater_config_store.upsert(repeater_id, target_org, body_dict)
    await _broadcast({"type": "repeater_configs_changed", "org_id": target_org})
    return cfg


@api_router.delete("/repeater-configs/{repeater_id}")
async def api_delete_repeater_config(repeater_id: int, user: dict = Depends(get_current_admin)):
    existing = await repeater_config_store.get(repeater_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Repeater config not found")
    _require_admin_for_org(user, existing.get("org_id"))
    await repeater_config_store.delete(repeater_id)
    await _broadcast({"type": "repeater_configs_changed", "org_id": existing.get("org_id")})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Groups
# --------------------------------------------------------------------------- #
@api_router.get("/groups")
async def api_list_groups(user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "positions")
    return await group_store.list(org_ids=visible)


@api_router.post("/groups")
async def api_create_group(body: GroupCreate, user: dict = Depends(get_current_admin)):
    org_id = user.get("org_id") or _default_org_id
    g = await group_store.create(org_id, body.model_dump())
    await _broadcast({"type": "groups_changed", "org_id": org_id})
    return g


@api_router.patch("/groups/{group_id}")
async def api_update_group(group_id: str, body: GroupUpdate, user: dict = Depends(get_current_admin)):
    g = await group_store.get(group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_admin_for_org(user, g.get("org_id"))
    g = await group_store.update(group_id, body.model_dump(exclude_unset=True))
    await _broadcast({"type": "groups_changed", "org_id": g.get("org_id")})
    return g


@api_router.delete("/groups/{group_id}")
async def api_delete_group(group_id: str, user: dict = Depends(get_current_admin)):
    g = await group_store.get(group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_admin_for_org(user, g.get("org_id"))
    await group_store.delete(group_id)
    await _broadcast({"type": "groups_changed", "org_id": g.get("org_id")})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
@api_router.get("/messages")
async def api_list_messages(limit: int = 200, user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "messages")
    return await message_store.list(limit=limit, org_ids=visible)


@api_router.post("/messages")
async def api_send_message(body: MessageSend, user: dict = Depends(get_current_user)):
    if not body.target_dmr_id and not body.group_id:
        raise HTTPException(status_code=400, detail="Provide target_dmr_id or group_id")
    tg = None
    target_org_id = user.get("org_id") or _default_org_id
    if body.group_id:
        g = await group_store.get(body.group_id)
        if not g:
            raise HTTPException(status_code=404, detail="Group not found")
        # Dispatcher-ACL check for regular users
        allowed = user.get("allowed_group_ids") or []
        if user.get("role") == "user" and allowed and body.group_id not in allowed:
            raise HTTPException(status_code=403, detail="You do not have access to this group")
        # Cross-org: verify the user can dispatch into this group's org
        target_org_id = g.get("org_id") or target_org_id
        if not await can_dispatch_org(user, org_link_store, target_org_id, "messages"):
            raise HTTPException(status_code=403, detail="No dispatch permission for target organization")
        tg = g["talkgroup_id"]
    else:
        # Private message: find the target radio's org
        radio = await db.radios.find_one({"dmr_id": body.target_dmr_id}, {"_id": 0, "org_id": 1})
        if radio and radio.get("org_id"):
            target_org_id = radio["org_id"]
            if not await can_dispatch_org(user, org_link_store, target_org_id, "messages"):
                raise HTTPException(status_code=403, detail="No dispatch permission for target radio")
    visible = await _fan_out_orgs(target_org_id, "messages")
    msg = await message_store.send(
        text=body.text,
        target_dmr_id=body.target_dmr_id,
        talkgroup_id=tg,
        sender_email=user["email"],
        org_id=target_org_id,
        visible_to_org_ids=visible,
    )
    if shift_log:
        await shift_log.log_message(msg, visible_to_org_ids=visible)
    return msg


@api_router.post("/messages/simulate-inbound")
async def api_simulate_inbound(body: InboundSMSInject, user: dict = Depends(get_current_user)):
    await on_dmr_sms(
        {
            "text": body.text,
            "from_dmr_id": body.from_dmr_id,
            "to_dmr_id": body.to_dmr_id or 0,
            "is_private": body.talkgroup_id is None,
            "talkgroup_id": body.talkgroup_id,
            "repeater_id": None,
            "org_id": user.get("org_id") or _default_org_id,
        }
    )
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Voice
# --------------------------------------------------------------------------- #
@api_router.get("/voice/status")
async def api_voice_status(_: dict = Depends(get_current_user)):
    return voice_gateway.status()


@api_router.post("/voice/ptt")
async def api_voice_ptt(body: VoicePttStart, user: dict = Depends(get_current_user)):
    tg = None
    target_org_id = user.get("org_id") or _default_org_id
    if body.group_id:
        g = await group_store.get(body.group_id)
        if not g:
            raise HTTPException(status_code=404, detail="Group not found")
        target_org_id = g.get("org_id") or target_org_id
        tg = g["talkgroup_id"]
    if not await can_dispatch_org(user, org_link_store, target_org_id, "voice"):
        raise HTTPException(status_code=403, detail="No voice dispatch permission")
    return voice_gateway.transmit_from_browser(body.target_dmr_id, tg)


# --------------------------------------------------------------------------- #
# Emergency
# --------------------------------------------------------------------------- #
@api_router.get("/emergencies")
async def list_emergencies(
    status_filter: Optional[str] = "active",
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    q: dict = {"status": status_filter} if status_filter else {}
    visible = await _user_visible_orgs(user, "emergencies")
    if visible is not None:
        q.update(build_org_filter(visible))
    cursor = db.emergencies.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(limit)


@api_router.post("/emergencies/{emergency_id}/clear")
async def clear_emergency(emergency_id: str, user: dict = Depends(get_current_user)):
    doc = await db.emergencies.find_one({"id": emergency_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Emergency not found")
    target_org_id = doc.get("org_id")
    # Permission: admin+ OR (user with org.user_can_ack_emergency=True)
    if user.get("role") == "user":
        org = await org_store.get(target_org_id) if target_org_id else None
        if not org or not org.get("user_can_ack_emergency", True):
            raise HTTPException(status_code=403, detail="Emergency acknowledgement disabled for users in this organization")
    if not await can_dispatch_org(user, org_link_store, target_org_id, "emergencies"):
        raise HTTPException(status_code=403, detail="No permission for this organization")
    await db.emergencies.update_one(
        {"id": emergency_id},
        {"$set": {"status": "cleared", "cleared_at": _now_iso(), "cleared_by": user["email"]}},
    )
    await db.radios.update_one(
        {"dmr_id": doc["dmr_id"], "org_id": target_org_id},
        {"$set": {"in_emergency": False}, "$unset": {"emergency_id": ""}},
    )
    await _broadcast({
        "type": "emergency_cleared",
        "emergency_id": emergency_id,
        "dmr_id": doc["dmr_id"],
        "org_id": target_org_id,
    })
    if shift_log:
        visible = await _fan_out_orgs(target_org_id, "emergencies")
        await shift_log.log_emergency_cleared(
            doc["dmr_id"], user["email"], org_id=target_org_id, visible_to_org_ids=visible
        )
    return {"ok": True}


@api_router.post("/emergencies/simulate")
async def simulate_emergency(body: EmergencyInject, user: dict = Depends(get_current_user)):
    await on_emergency(
        {
            "src_dmr_id": body.dmr_id,
            "talkgroup_id": body.talkgroup_id,
            "repeater_id": 0,
            "is_private": False,
            "signature": "SIMULATED",
            "org_id": user.get("org_id") or _default_org_id,
        }
    )
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Geofences + alerts
# --------------------------------------------------------------------------- #
@api_router.get("/geofences")
async def list_geofences(user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "geofences")
    return await geofence_engine.list_geofences(org_ids=visible)


@api_router.post("/geofences")
async def create_geofence(body: GeofenceCreate, user: dict = Depends(get_current_admin)):
    return await geofence_engine.create(
        body.model_dump(), org_id=user.get("org_id") or _default_org_id
    )


@api_router.delete("/geofences/{geofence_id}")
async def delete_geofence(geofence_id: str, user: dict = Depends(get_current_admin)):
    fence = await db.geofences.find_one({"id": geofence_id}, {"_id": 0, "org_id": 1})
    if not fence:
        raise HTTPException(status_code=404, detail="Geofence not found")
    _require_admin_for_org(user, fence.get("org_id"))
    await geofence_engine.delete(geofence_id)
    return {"ok": True}


@api_router.get("/alerts")
async def list_alerts(limit: int = 100, user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "geofences")
    return await geofence_engine.alerts(limit=limit, org_ids=visible)


@api_router.delete("/alerts")
async def clear_alerts(user: dict = Depends(get_current_admin)):
    org_ids = None
    if user.get("role") != "super_admin":
        org_ids = [user.get("org_id")]
    await geofence_engine.clear_alerts(org_ids=org_ids)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Shift log
# --------------------------------------------------------------------------- #
def _shift_log_group_filter(user: dict) -> Optional[list[str]]:
    if user.get("role") != "user":
        return None
    allowed = user.get("allowed_group_ids") or []
    return allowed if allowed else None


@api_router.get("/shift-log")
async def api_shift_log(
    limit: int = 500,
    event_type: Optional[str] = None,
    dmr_id: Optional[int] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if event_type and event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown event_type")
    return await shift_log.query(
        limit=limit,
        event_type=event_type,
        dmr_id=dmr_id,
        group_ids=_shift_log_group_filter(user),
        since=since,
        until=until,
        org_ids=await _user_visible_orgs(user, "positions"),
    )


@api_router.get("/shift-log/export.csv")
async def api_shift_log_csv(
    event_type: Optional[str] = None,
    dmr_id: Optional[int] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    csv_text = await shift_log.export_csv(
        event_type=event_type,
        dmr_id=dmr_id,
        group_ids=_shift_log_group_filter(user),
        since=since,
        until=until,
        org_ids=await _user_visible_orgs(user, "positions"),
    )
    filename = f"shift-log-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.delete("/shift-log")
async def api_shift_log_clear(user: dict = Depends(get_current_admin)):
    q: dict = {}
    if user.get("role") != "super_admin":
        q["$or"] = [
            {"org_id": user.get("org_id")},
            {"visible_to_org_ids": {"$in": [user.get("org_id")]}},
        ]
    await db.shift_log.delete_many(q)
    await _broadcast({"type": "shift_log_cleared", "org_id": user.get("org_id")})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Overlays
# --------------------------------------------------------------------------- #
_UPLOADS_DIR = Path("/app/backend/uploads/overlays")
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}


@api_router.get("/overlays")
async def overlays_list(active: Optional[bool] = None, user: dict = Depends(get_current_user)):
    visible = await _user_visible_orgs(user, "overlays")
    return await overlay_store.list(only_active=(active is True), org_ids=visible)


@api_router.post("/overlays")
async def overlays_create(body: OverlayCreate, admin: dict = Depends(get_current_admin)):
    org_id = admin.get("org_id") or _default_org_id
    doc = await overlay_store.create(org_id=org_id, name=body.name, created_by=admin["email"])
    await _broadcast({"type": "overlay_upserted", "overlay": doc}, resource="overlays")
    return doc


@api_router.get("/overlays/{overlay_id}")
async def overlays_get(overlay_id: str, user: dict = Depends(get_current_user)):
    doc = await overlay_store.get(overlay_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    visible = await _user_visible_orgs(user, "overlays")
    if visible is not None and doc.get("org_id") not in visible:
        raise HTTPException(status_code=404, detail="Overlay not found")
    return doc


def _assert_overlay_admin(admin: dict, doc: dict) -> None:
    _require_admin_for_org(admin, doc.get("org_id"))


@api_router.patch("/overlays/{overlay_id}")
async def overlays_update(overlay_id: str, body: OverlayUpdate, admin: dict = Depends(get_current_admin)):
    doc = await overlay_store.get(overlay_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    _assert_overlay_admin(admin, doc)
    updated = await overlay_store.update(overlay_id, body.model_dump(exclude_none=True))
    await _broadcast({"type": "overlay_upserted", "overlay": updated}, resource="overlays")
    return updated


@api_router.delete("/overlays/{overlay_id}")
async def overlays_delete(overlay_id: str, admin: dict = Depends(get_current_admin)):
    doc = await overlay_store.get(overlay_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    _assert_overlay_admin(admin, doc)
    await overlay_store.delete(overlay_id)
    for img in doc.get("images", []) or []:
        try:
            url = img.get("url", "")
            if url.startswith("/api/uploads/overlays/"):
                fname = url.rsplit("/", 1)[-1]
                (Path(_UPLOADS_DIR) / fname).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    await _broadcast({"type": "overlay_removed", "overlay_id": overlay_id, "org_id": doc.get("org_id")}, resource="overlays")
    return {"ok": True}


@api_router.put("/overlays/{overlay_id}/shapes")
async def overlays_replace_shapes(overlay_id: str, body: OverlayShapesReplace, admin: dict = Depends(get_current_admin)):
    doc = await overlay_store.get(overlay_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    _assert_overlay_admin(admin, doc)
    updated = await overlay_store.replace_shapes(overlay_id, [s.model_dump() for s in body.shapes])
    await _broadcast({"type": "overlay_upserted", "overlay": updated}, resource="overlays")
    return updated


@api_router.post("/overlays/{overlay_id}/images")
async def overlays_add_image(
    overlay_id: str,
    file: UploadFile = File(...),
    name: str = Form(""),
    sw_lat: float = Form(...),
    sw_lng: float = Form(...),
    ne_lat: float = Form(...),
    ne_lng: float = Form(...),
    opacity: float = Form(0.6),
    admin: dict = Depends(get_current_admin),
):
    doc = await overlay_store.get(overlay_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    _assert_overlay_admin(admin, doc)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported image type .{ext}")
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = _UPLOADS_DIR / fname
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 20 MB)")
    fpath.write_bytes(contents)
    url = f"/api/uploads/overlays/{fname}"
    updated = await overlay_store.add_image(
        overlay_id,
        name=name or file.filename or "overlay image",
        url=url,
        bounds=[[sw_lat, sw_lng], [ne_lat, ne_lng]],
        opacity=opacity,
    )
    await _broadcast({"type": "overlay_upserted", "overlay": updated}, resource="overlays")
    return updated


@api_router.patch("/overlays/{overlay_id}/images/{image_id}")
async def overlays_update_image(overlay_id: str, image_id: str, body: OverlayImageUpdate, admin: dict = Depends(get_current_admin)):
    doc = await overlay_store.get(overlay_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    _assert_overlay_admin(admin, doc)
    updated = await overlay_store.update_image(overlay_id, image_id, body.model_dump(exclude_none=True))
    await _broadcast({"type": "overlay_upserted", "overlay": updated}, resource="overlays")
    return updated


@api_router.delete("/overlays/{overlay_id}/images/{image_id}")
async def overlays_delete_image(overlay_id: str, image_id: str, admin: dict = Depends(get_current_admin)):
    doc = await overlay_store.get(overlay_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    _assert_overlay_admin(admin, doc)
    img = next((i for i in doc.get("images", []) if i.get("id") == image_id), None)
    if img:
        url = img.get("url", "")
        if url.startswith("/api/uploads/overlays/"):
            fname = url.rsplit("/", 1)[-1]
            try:
                (_UPLOADS_DIR / fname).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
    updated = await overlay_store.delete_image(overlay_id, image_id)
    await _broadcast({"type": "overlay_upserted", "overlay": updated}, resource="overlays")
    return updated


# --------------------------------------------------------------------------- #
# Situational-awareness tokens (org-scoped)
# --------------------------------------------------------------------------- #
@api_router.get("/situational-tokens")
async def sa_list_tokens(user: dict = Depends(get_current_admin)):
    org_ids = None if user.get("role") == "super_admin" else [user.get("org_id")]
    return await situational_store.list(org_ids=org_ids)


@api_router.post("/situational-tokens")
async def sa_create_token(body: SituationalTokenCreate, admin: dict = Depends(get_current_admin)):
    org_id = admin.get("org_id") or _default_org_id
    if body.group_id:
        g = await group_store.get(body.group_id)
        if not g:
            raise HTTPException(status_code=404, detail="Group not found")
        _require_admin_for_org(admin, g.get("org_id"))
        org_id = g.get("org_id") or org_id
    return await situational_store.create(
        name=body.name,
        group_id=body.group_id,
        expires_at=body.expires_at,
        created_by=admin["email"],
        org_id=org_id,
    )


@api_router.delete("/situational-tokens/{token_id}")
async def sa_delete_token(token_id: str, admin: dict = Depends(get_current_admin)):
    tok = await db.situational_tokens.find_one({"id": token_id}, {"_id": 0, "org_id": 1})
    if not tok:
        raise HTTPException(status_code=404, detail="Token not found")
    _require_admin_for_org(admin, tok.get("org_id"))
    await situational_store.delete(token_id)
    return {"ok": True}


@api_router.get("/situational/{token}/snapshot")
async def sa_snapshot(token: str):
    doc = await situational_store.get_by_token(token)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown or expired token")
    snap = await situational_store.snapshot(doc, db.radios, db.emergencies)
    q_over = {"active": True}
    if doc.get("org_id"):
        q_over["org_id"] = doc["org_id"]
    snap["overlays"] = await db.overlays.find(q_over, {"_id": 0}).to_list(200)
    return snap


@api_router.websocket("/situational/{token}/ws")
async def sa_websocket(websocket: WebSocket, token: str):
    doc = await situational_store.get_by_token(token)
    if not doc:
        await websocket.accept()
        await websocket.close(code=4404)
        return
    await websocket.accept()
    viewer = {"ws": websocket, "token_doc": doc}
    public_ws_clients.append(viewer)
    try:
        await websocket.send_json({"type": "hello", "server_time": _now_iso()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        if viewer in public_ws_clients:
            public_ws_clients.remove(viewer)


# --------------------------------------------------------------------------- #
# Authenticated WebSocket
# --------------------------------------------------------------------------- #
@api_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    import jwt as _jwt
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = _jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user or user.get("status") != "approved":
            await websocket.close(code=4403)
            return
        user.pop("password_hash", None)
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    wc = {"ws": websocket, "user": user}
    ws_clients.append(wc)
    try:
        await websocket.send_json({
            "type": "hello",
            "server_time": _now_iso(),
            "user": to_public(user),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        if wc in ws_clients:
            ws_clients.remove(wc)


app.include_router(api_router)
app.mount(
    "/api/uploads",
    StaticFiles(directory="/app/backend/uploads", check_dir=False),
    name="uploads",
)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
