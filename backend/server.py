"""FastAPI server for the DMR radio tracker."""
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
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

import auth
from auth import (
    LoginPayload,
    RegisterPayload,
    RolePayload,
    UserPublic,
    get_current_admin,
    get_current_user,
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
from situational import (
    SituationalTokenStore,
    public_emergency_projection,
    public_radio_projection,
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
HB_PASSWORD = os.environ.get("HB_PASSWORD", "PASSWORD")
SERVER_DMR_ID = int(os.environ.get("SERVER_DMR_ID", "9990001"))
DATA_SLOT = int(os.environ.get("DATA_SLOT", "1"))
MAX_PACKETS_BUFFER = 500
MAX_POSITIONS_PER_RADIO = 500

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
auth.bind_db(db)

packet_log: Deque[dict] = deque(maxlen=MAX_PACKETS_BUFFER)
ws_clients: set[WebSocket] = set()
# Public read-only WebSocket viewers keyed by their token document id.
# Each entry is {"ws": WebSocket, "token_doc": dict}.
public_ws_clients: list[dict] = []

hb_master: Optional[HBMaster] = None
hb_transport: Optional[asyncio.DatagramTransport] = None
geofence_engine: Optional[GeofenceEngine] = None
group_store: Optional[GroupStore] = None
channel_store: Optional[ChannelStore] = None
repeater_config_store: Optional[RepeaterConfigStore] = None
message_store: Optional[MessageStore] = None
shift_log: Optional[ShiftLogStore] = None
situational_store: Optional[SituationalTokenStore] = None
voice_gateway = VoiceGateway()


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


class UserGroupsPayload(BaseModel):
    allowed_group_ids: list[str] = Field(default_factory=list)


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
    expires_at: Optional[str] = None  # ISO 8601, optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _broadcast(message: dict) -> None:
    # Auto-log geofence alerts into the shift log (their engine broadcasts them
    # directly on this channel; we intercept here to persist them).
    if shift_log and message.get("type") == "alert":
        try:
            await shift_log.log_alert(message["alert"])
        except Exception:  # noqa: BLE001
            pass
    dead = []
    for ws in list(ws_clients):
        try:
            await ws.send_json(message)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)

    # Fan out a *sanitised* subset to any public "situational awareness" viewers
    await _broadcast_public(message)


async def _broadcast_public(message: dict) -> None:
    """Send a trimmed subset of events to read-only situational viewers."""
    if not public_ws_clients:
        return
    mtype = message.get("type")
    public_msg: Optional[dict] = None
    filter_group: Optional[str] = None

    if mtype == "packet":
        pkt = message.get("packet") or {}
        radio = {
            "dmr_id": pkt.get("dmr_id"),
            "callsign": pkt.get("callsign"),
            "group_id": pkt.get("group_id"),
            "icon": pkt.get("icon"),
            "color": pkt.get("color"),
            "lat": pkt.get("lat"),
            "lon": pkt.get("lon"),
            "timestamp": pkt.get("timestamp"),
        }
        public_msg = {"type": "position", "radio": public_radio_projection(radio)}
        filter_group = pkt.get("group_id")
    elif mtype == "emergency":
        emg = message.get("emergency") or {}
        public_msg = {"type": "emergency", "emergency": public_emergency_projection(emg)}
        filter_group = emg.get("group_id")
    elif mtype == "emergency_cleared":
        public_msg = {
            "type": "emergency_cleared",
            "emergency_id": message.get("emergency_id"),
            "dmr_id": message.get("dmr_id"),
        }
    elif mtype == "clear":
        public_msg = {"type": "clear"}
    else:
        return

    dead: list[dict] = []
    for viewer in list(public_ws_clients):
        # Enforce per-token group scoping
        scope = viewer["token_doc"].get("group_id")
        if scope and filter_group is not None and scope != filter_group:
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

    packet_log.appendleft(packet)

    existing = await db.radios.find_one({"dmr_id": dmr_id}, {"_id": 0})
    callsign = packet.get("callsign") or (existing.get("callsign") if existing else None)
    icon = (existing.get("icon") if existing else None) or "Radio"
    color = (existing.get("color") if existing else None) or "#39ff14"
    group_id = packet.get("group_id") or (existing.get("group_id") if existing else None)

    # auto-assign group by talkgroup if not set
    tg = packet.get("talkgroup_id")
    if not group_id and tg and group_store:
        g = await group_store.get_by_talkgroup(tg)
        if g:
            group_id = g["id"]
            color = existing.get("color") if existing else g.get("color") or color
            icon = existing.get("icon") if existing else g.get("icon") or icon

    await db.radios.update_one(
        {"dmr_id": dmr_id},
        {
            "$set": {
                "dmr_id": dmr_id,
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

    # prune
    count = await db.positions.count_documents({"dmr_id": dmr_id})
    if count > MAX_POSITIONS_PER_RADIO:
        excess = count - MAX_POSITIONS_PER_RADIO
        old = await db.positions.find({"dmr_id": dmr_id}, {"id": 1}).sort(
            "timestamp", 1
        ).to_list(excess)
        old_ids = [d["id"] for d in old]
        if old_ids:
            await db.positions.delete_many({"id": {"$in": old_ids}})

    packet["callsign"] = callsign
    packet["group_id"] = group_id
    await _broadcast({"type": "packet", "packet": packet})
    if shift_log:
        await shift_log.log_position(packet)
    if geofence_engine:
        await geofence_engine.evaluate(packet)


async def on_dmr_sms(inbound: dict) -> None:
    if not message_store:
        return
    radio = await db.radios.find_one(
        {"dmr_id": inbound["from_dmr_id"]}, {"_id": 0, "callsign": 1}
    )
    msg = await message_store.record_inbound(
        text=inbound["text"],
        from_dmr_id=inbound["from_dmr_id"],
        to_dmr_id=inbound["to_dmr_id"],
        is_private=inbound["is_private"],
        talkgroup_id=inbound.get("talkgroup_id"),
        callsign=(radio or {}).get("callsign"),
        repeater_id=inbound.get("repeater_id"),
    )
    if shift_log:
        await shift_log.log_message(msg)


async def on_voice_activity(evt: dict) -> None:
    radio = await db.radios.find_one(
        {"dmr_id": evt["src_dmr_id"]}, {"_id": 0, "callsign": 1}
    )
    tg = evt.get("talkgroup_id")
    voice_gateway.track(
        talkgroup_id=tg or 0,
        src_id=evt["src_dmr_id"],
        callsign=(radio or {}).get("callsign"),
        repeater_id=evt["repeater_id"],
    )
    await _broadcast({"type": "voice_activity", "activity": voice_gateway.active_talkgroups()})
    if shift_log:
        evt = {**evt, "callsign": (radio or {}).get("callsign")}
        await shift_log.log_voice(evt)


async def on_emergency(evt: dict) -> None:
    """Radio pressed the emergency button - persist + broadcast."""
    src_id = evt["src_dmr_id"]
    radio = await db.radios.find_one({"dmr_id": src_id}, {"_id": 0}) or {}
    ts = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
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
        {"dmr_id": src_id},
        {
            "$set": {
                "in_emergency": True,
                "emergency_at": ts,
                "emergency_id": doc["id"],
            }
        },
        upsert=True,
    )
    doc.pop("_id", None)
    await _broadcast({"type": "emergency", "emergency": doc})
    if shift_log:
        await shift_log.log_emergency(doc)


async def send_dmrd_broadcast(frame: bytes) -> int:
    if not hb_master:
        return 0
    return await hb_master.broadcast_dmrd(frame)


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    global hb_master, hb_transport, geofence_engine, group_store, channel_store, repeater_config_store, message_store, shift_log, situational_store
    await auth.ensure_indexes()
    await auth.seed_admin()
    geofence_engine = GeofenceEngine(db, _broadcast)
    group_store = GroupStore(db)
    await group_store.ensure_indexes()
    await group_store.seed_defaults()
    channel_store = ChannelStore(db)
    await channel_store.ensure_indexes()
    await channel_store.seed_defaults()
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
        )
    except OSError as exc:
        logger.warning("HB Master could not bind to %s:%s (%s).", HB_BIND_HOST, HB_BIND_PORT, exc)
        hb_transport = None
        hb_master = None
    yield
    if hb_transport is not None:
        hb_transport.close()
    client.close()


app = FastAPI(title="DMR GPS Tracker", lifespan=lifespan)
api_router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
# Public + auth
# --------------------------------------------------------------------------- #
@api_router.get("/")
async def root():
    return {"service": "dmr-tracker", "version": "1.2"}


@api_router.get("/status")
async def status(_: dict = Depends(get_current_user)):
    return {
        "listener": {
            "bind": f"{HB_BIND_HOST}:{HB_BIND_PORT}",
            "running": hb_transport is not None,
            "stats": hb_master.snapshot() if hb_master else None,
        },
        "parsers": parser_names(),
        "voice": voice_gateway.status(),
        "server_dmr_id": SERVER_DMR_ID,
        "radios_tracked": await db.radios.count_documents({}),
        "positions_stored": await db.positions.count_documents({}),
        "packet_buffer": len(packet_log),
        "server_time": _now_iso(),
    }


@api_router.post("/auth/register", response_model=UserPublic)
async def api_register(payload: RegisterPayload):
    return await register_user(payload)


@api_router.post("/auth/login")
async def api_login(payload: LoginPayload, request: Request):
    ip = request.client.host if request.client else "unknown"
    return await login_user(payload, ip)


@api_router.get("/auth/me", response_model=UserPublic)
async def api_me(user: dict = Depends(get_current_user)):
    return to_public(user)


@api_router.post("/auth/logout")
async def api_logout(_: dict = Depends(get_current_user)):
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Admin users
# --------------------------------------------------------------------------- #
@api_router.get("/admin/users", response_model=List[UserPublic])
async def admin_list_users(_: dict = Depends(get_current_admin)):
    cursor = db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    docs = await cursor.to_list(500)
    return [to_public(d) for d in docs]


@api_router.post("/admin/users/{user_id}/approve", response_model=UserPublic)
async def admin_approve(user_id: str, _: dict = Depends(get_current_admin)):
    result = await db.users.find_one_and_update(
        {"id": user_id}, {"$set": {"status": "approved"}}
    )
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return to_public(updated)


@api_router.post("/admin/users/{user_id}/reject", response_model=UserPublic)
async def admin_reject(user_id: str, _: dict = Depends(get_current_admin)):
    await db.users.update_one({"id": user_id}, {"$set": {"status": "rejected"}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return to_public(updated)


@api_router.post("/admin/users/{user_id}/role", response_model=UserPublic)
async def admin_set_role(user_id: str, body: RolePayload, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"] and body.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot demote yourself")
    await db.users.update_one({"id": user_id}, {"$set": {"role": body.role}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return to_public(updated)


@api_router.post("/admin/users/{user_id}/groups", response_model=UserPublic)
async def admin_set_user_groups(
    user_id: str, body: UserGroupsPayload, _: dict = Depends(get_current_admin)
):
    await db.users.update_one(
        {"id": user_id}, {"$set": {"allowed_group_ids": body.allowed_group_ids}}
    )
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return to_public(updated)


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Radios
# --------------------------------------------------------------------------- #
@api_router.get("/radios")
async def list_radios(
    group_id: Optional[str] = None,
    channel: Optional[int] = None,
    user: dict = Depends(get_current_user),
):
    q: dict = {}
    if group_id:
        q["group_id"] = group_id
    if channel:
        q["last_channel"] = channel
    # Dispatcher ACL: non-admin with a non-empty allowed_group_ids list only
    # sees radios in those groups (empty list = unrestricted / legacy).
    allowed = user.get("allowed_group_ids") or []
    if user.get("role") != "admin" and allowed:
        q["group_id"] = {"$in": allowed if not group_id else [group_id]} if not group_id or group_id in allowed else {"$in": []}
    cursor = db.radios.find(q, {"_id": 0}).sort("last_seen", -1)
    return await cursor.to_list(500)


@api_router.get("/radios/{dmr_id}/positions")
async def radio_positions(dmr_id: int, limit: int = 200, _: dict = Depends(get_current_user)):
    cursor = (
        db.positions.find({"dmr_id": dmr_id}, {"_id": 0})
        .sort("timestamp", 1)
        .limit(min(limit, MAX_POSITIONS_PER_RADIO))
    )
    return await cursor.to_list(MAX_POSITIONS_PER_RADIO)


@api_router.patch("/radios/{dmr_id}")
async def update_radio(dmr_id: int, meta: RadioMeta, _: dict = Depends(get_current_user)):
    updates = {k: v for k, v in meta.model_dump(exclude_unset=True).items() if v is not None or k == "group_id"}
    if not updates:
        return {"ok": True}
    await db.radios.update_one({"dmr_id": dmr_id}, {"$set": updates}, upsert=False)
    await _broadcast({"type": "radio_update", "dmr_id": dmr_id, "updates": updates})
    return {"ok": True}


@api_router.delete("/radios/{dmr_id}")
async def delete_radio(dmr_id: int, _: dict = Depends(get_current_admin)):
    await db.radios.delete_one({"dmr_id": dmr_id})
    await db.positions.delete_many({"dmr_id": dmr_id})
    return {"ok": True}


@api_router.delete("/radios")
async def clear_all(_: dict = Depends(get_current_admin)):
    await db.radios.delete_many({})
    await db.positions.delete_many({})
    await db.fence_state.delete_many({})
    packet_log.clear()
    await _broadcast({"type": "clear"})
    return {"ok": True}


@api_router.get("/packets")
async def get_packets(limit: int = 200, _: dict = Depends(get_current_user)):
    return list(packet_log)[: min(limit, MAX_PACKETS_BUFFER)]


@api_router.post("/inject")
async def inject(payload: InjectPayload, _: dict = Depends(get_current_user)):
    packet = {
        "source": "SIM",
        "source_addr": "simulated",
        "dmr_id": payload.dmr_id,
        "callsign": payload.callsign,
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
async def inject_raw(payload: InjectRawPayload, _: dict = Depends(get_current_user)):
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
async def list_repeaters(_: dict = Depends(get_current_user)):
    return hb_master.snapshot()["sessions"] if hb_master else []


# --------------------------------------------------------------------------- #
# Channels (talk-net logical channels; slot-1/slot-2 seeded for back-compat)
# --------------------------------------------------------------------------- #
@api_router.get("/channels")
async def api_list_channels(_: dict = Depends(get_current_user)):
    return await channel_store.list()


@api_router.post("/channels")
async def api_create_channel(body: ChannelCreate, _: dict = Depends(get_current_admin)):
    ch = await channel_store.create(body.model_dump())
    await _broadcast({"type": "channels_changed"})
    return ch


@api_router.patch("/channels/{channel_id}")
async def api_update_channel(channel_id: str, body: ChannelUpdate, _: dict = Depends(get_current_admin)):
    # legacy slot=1/2 rename path also supported
    if channel_id in ("1", "2"):
        channel_id = f"slot-{channel_id}"
    ch = await channel_store.update(channel_id, body.model_dump(exclude_unset=True))
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    await _broadcast({"type": "channels_changed"})
    return ch


@api_router.delete("/channels/{channel_id}")
async def api_delete_channel(channel_id: str, _: dict = Depends(get_current_admin)):
    try:
        await channel_store.delete(channel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _broadcast({"type": "channels_changed"})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Repeater configs (per-MMDVM slot->channel binding)
# --------------------------------------------------------------------------- #
@api_router.get("/repeater-configs")
async def api_list_repeater_configs(_: dict = Depends(get_current_user)):
    return await repeater_config_store.list()


@api_router.put("/repeater-configs/{repeater_id}")
async def api_upsert_repeater_config(
    repeater_id: int, body: RepeaterConfigBody, _: dict = Depends(get_current_admin)
):
    cfg = await repeater_config_store.upsert(repeater_id, body.model_dump(exclude_unset=True))
    await _broadcast({"type": "repeater_configs_changed"})
    return cfg


@api_router.delete("/repeater-configs/{repeater_id}")
async def api_delete_repeater_config(repeater_id: int, _: dict = Depends(get_current_admin)):
    await repeater_config_store.delete(repeater_id)
    await _broadcast({"type": "repeater_configs_changed"})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Groups
# --------------------------------------------------------------------------- #
@api_router.get("/groups")
async def api_list_groups(_: dict = Depends(get_current_user)):
    return await group_store.list()


@api_router.post("/groups")
async def api_create_group(body: GroupCreate, _: dict = Depends(get_current_admin)):
    g = await group_store.create(body.model_dump())
    await _broadcast({"type": "groups_changed"})
    return g


@api_router.patch("/groups/{group_id}")
async def api_update_group(group_id: str, body: GroupUpdate, _: dict = Depends(get_current_admin)):
    g = await group_store.update(group_id, body.model_dump(exclude_unset=True))
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    await _broadcast({"type": "groups_changed"})
    return g


@api_router.delete("/groups/{group_id}")
async def api_delete_group(group_id: str, _: dict = Depends(get_current_admin)):
    await group_store.delete(group_id)
    await _broadcast({"type": "groups_changed"})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
@api_router.get("/messages")
async def api_list_messages(limit: int = 200, _: dict = Depends(get_current_user)):
    return await message_store.list(limit=limit)


@api_router.post("/messages")
async def api_send_message(body: MessageSend, user: dict = Depends(get_current_user)):
    if not body.target_dmr_id and not body.group_id:
        raise HTTPException(status_code=400, detail="Provide target_dmr_id or group_id")
    tg = None
    if body.group_id:
        g = await group_store.get(body.group_id)
        if not g:
            raise HTTPException(status_code=404, detail="Group not found")
        allowed = user.get("allowed_group_ids") or []
        if user.get("role") != "admin" and allowed and body.group_id not in allowed:
            raise HTTPException(status_code=403, detail="You do not have access to this group")
        tg = g["talkgroup_id"]
    msg = await message_store.send(
        text=body.text,
        target_dmr_id=body.target_dmr_id,
        talkgroup_id=tg,
        sender_email=user["email"],
    )
    if shift_log:
        await shift_log.log_message(msg)
    return msg


@api_router.post("/messages/simulate-inbound")
async def api_simulate_inbound(body: InboundSMSInject, _: dict = Depends(get_current_user)):
    """Development helper: inject an inbound SMS as if a radio had sent it."""
    await on_dmr_sms(
        {
            "text": body.text,
            "from_dmr_id": body.from_dmr_id,
            "to_dmr_id": body.to_dmr_id or 0,
            "is_private": body.talkgroup_id is None,
            "talkgroup_id": body.talkgroup_id,
            "repeater_id": None,
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
async def api_voice_ptt(body: VoicePttStart, _: dict = Depends(get_current_user)):
    tg = None
    if body.group_id:
        g = await group_store.get(body.group_id)
        if not g:
            raise HTTPException(status_code=404, detail="Group not found")
        tg = g["talkgroup_id"]
    return voice_gateway.transmit_from_browser(body.target_dmr_id, tg)


# --------------------------------------------------------------------------- #
# Emergency
# --------------------------------------------------------------------------- #
@api_router.get("/emergencies")
async def list_emergencies(status_filter: Optional[str] = "active", limit: int = 100, _: dict = Depends(get_current_user)):
    q = {"status": status_filter} if status_filter else {}
    cursor = db.emergencies.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(limit)


@api_router.post("/emergencies/{emergency_id}/clear")
async def clear_emergency(emergency_id: str, admin: dict = Depends(get_current_admin)):
    doc = await db.emergencies.find_one({"id": emergency_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Emergency not found")
    await db.emergencies.update_one(
        {"id": emergency_id},
        {"$set": {"status": "cleared", "cleared_at": _now_iso()}},
    )
    await db.radios.update_one(
        {"dmr_id": doc["dmr_id"]},
        {"$set": {"in_emergency": False}, "$unset": {"emergency_id": ""}},
    )
    await _broadcast({"type": "emergency_cleared", "emergency_id": emergency_id, "dmr_id": doc["dmr_id"]})
    if shift_log:
        await shift_log.log_emergency_cleared(doc["dmr_id"], admin["email"])
    return {"ok": True}


@api_router.post("/emergencies/simulate")
async def simulate_emergency(body: EmergencyInject, _: dict = Depends(get_current_user)):
    """Development helper: fire an emergency as if a radio pressed its panic button."""
    await on_emergency(
        {
            "src_dmr_id": body.dmr_id,
            "talkgroup_id": body.talkgroup_id,
            "repeater_id": 0,
            "is_private": False,
            "signature": "SIMULATED",
        }
    )
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Geofences + alerts
# --------------------------------------------------------------------------- #
@api_router.get("/geofences")
async def list_geofences(_: dict = Depends(get_current_user)):
    return await geofence_engine.list_geofences()


@api_router.post("/geofences")
async def create_geofence(body: GeofenceCreate, _: dict = Depends(get_current_admin)):
    return await geofence_engine.create(body.model_dump())


@api_router.delete("/geofences/{geofence_id}")
async def delete_geofence(geofence_id: str, _: dict = Depends(get_current_admin)):
    await geofence_engine.delete(geofence_id)
    return {"ok": True}


@api_router.get("/alerts")
async def list_alerts(limit: int = 100, _: dict = Depends(get_current_user)):
    return await geofence_engine.alerts(limit=limit)


@api_router.delete("/alerts")
async def clear_alerts(_: dict = Depends(get_current_admin)):
    await geofence_engine.clear_alerts()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Shift log
# --------------------------------------------------------------------------- #
def _shift_log_group_filter(user: dict) -> Optional[list[str]]:
    if user.get("role") == "admin":
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
    )
    filename = f"shift-log-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.delete("/shift-log")
async def api_shift_log_clear(_: dict = Depends(get_current_admin)):
    await shift_log.clear()
    await _broadcast({"type": "shift_log_cleared"})
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Situational awareness (token-locked read-only views)
# --------------------------------------------------------------------------- #
@api_router.get("/situational-tokens")
async def sa_list_tokens(_: dict = Depends(get_current_admin)):
    return await situational_store.list()


@api_router.post("/situational-tokens")
async def sa_create_token(body: SituationalTokenCreate, admin: dict = Depends(get_current_admin)):
    if body.group_id:
        g = await group_store.get(body.group_id)
        if not g:
            raise HTTPException(status_code=404, detail="Group not found")
    return await situational_store.create(
        name=body.name,
        group_id=body.group_id,
        expires_at=body.expires_at,
        created_by=admin["email"],
    )


@api_router.delete("/situational-tokens/{token_id}")
async def sa_delete_token(token_id: str, _: dict = Depends(get_current_admin)):
    await situational_store.delete(token_id)
    return {"ok": True}


@api_router.get("/situational/{token}/snapshot")
async def sa_snapshot(token: str):
    doc = await situational_store.get_by_token(token)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown or expired token")
    return await situational_store.snapshot(doc, db.radios, db.emergencies)


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
# WebSocket (Bearer token via query string)
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
    except Exception:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json({"type": "hello", "server_time": _now_iso()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        ws_clients.discard(websocket)


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
