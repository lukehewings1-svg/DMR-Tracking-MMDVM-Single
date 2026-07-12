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
from dmr_ingest import HBMaster, start_hb_master
from dmr_parsers import parse_gps_payload, parser_names
from geofence import GeofenceEngine

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("dmr-tracker")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
HB_BIND_HOST = os.environ.get("HB_BIND_HOST", "0.0.0.0")
HB_BIND_PORT = int(os.environ.get("HB_BIND_PORT", "62031"))
HB_PASSWORD = os.environ.get("HB_PASSWORD", "PASSWORD")
MAX_PACKETS_BUFFER = 500
MAX_POSITIONS_PER_RADIO = 500

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
auth.bind_db(db)

packet_log: Deque[dict] = deque(maxlen=MAX_PACKETS_BUFFER)
ws_clients: set[WebSocket] = set()

hb_master: Optional[HBMaster] = None
hb_transport: Optional[asyncio.DatagramTransport] = None
geofence_engine: Optional[GeofenceEngine] = None


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
    speed: Optional[float] = None
    heading: Optional[float] = None
    rssi: Optional[int] = None


class InjectRawPayload(BaseModel):
    dmr_id: int
    callsign: Optional[str] = None
    hex: str


class RadioMeta(BaseModel):
    callsign: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = None


class GeofenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    lat: float
    lon: float
    radius_m: float = Field(gt=0, le=1_000_000)
    alert_on: str = Field(default="both", pattern="^(enter|exit|both)$")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _broadcast(message: dict) -> None:
    dead = []
    for ws in list(ws_clients):
        try:
            await ws.send_json(message)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


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

    await db.radios.update_one(
        {"dmr_id": dmr_id},
        {
            "$set": {
                "dmr_id": dmr_id,
                "callsign": callsign,
                "icon": icon,
                "color": color,
                "last_lat": packet["lat"],
                "last_lon": packet["lon"],
                "last_seen": packet["timestamp"],
                "last_format": packet["format"],
                "last_speed": packet.get("speed"),
                "last_heading": packet.get("heading"),
                "last_rssi": packet.get("rssi"),
                "last_source": packet.get("source", "MMDVM"),
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
        }
    )

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
    await _broadcast({"type": "packet", "packet": packet})
    if geofence_engine:
        await geofence_engine.evaluate(packet)


# --------------------------------------------------------------------------- #
# Lifespan
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    global hb_master, hb_transport, geofence_engine
    await auth.ensure_indexes()
    await auth.seed_admin()
    geofence_engine = GeofenceEngine(db, _broadcast)
    try:
        hb_transport, hb_master = await start_hb_master(
            HB_BIND_HOST, HB_BIND_PORT, HB_PASSWORD, record_packet
        )
    except OSError as exc:
        logger.warning(
            "HB Master could not bind to %s:%s (%s). Simulated injection still works.",
            HB_BIND_HOST, HB_BIND_PORT, exc,
        )
        hb_transport = None
        hb_master = None
    yield
    if hb_transport is not None:
        hb_transport.close()
    client.close()


app = FastAPI(title="DMR GPS Tracker", lifespan=lifespan)
api_router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- #
# Public endpoints
# --------------------------------------------------------------------------- #
@api_router.get("/")
async def root():
    return {"service": "dmr-tracker", "version": "1.1"}


@api_router.get("/status")
async def status(_: dict = Depends(get_current_user)):
    return {
        "listener": {
            "bind": f"{HB_BIND_HOST}:{HB_BIND_PORT}",
            "running": hb_transport is not None,
            "stats": hb_master.snapshot() if hb_master else None,
        },
        "parsers": parser_names(),
        "radios_tracked": await db.radios.count_documents({}),
        "positions_stored": await db.positions.count_documents({}),
        "packet_buffer": len(packet_log),
        "server_time": _now_iso(),
    }


# --------------------------------------------------------------------------- #
# Auth endpoints
# --------------------------------------------------------------------------- #
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
    # Bearer tokens are stateless; client just drops the token.
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Admin endpoints
# --------------------------------------------------------------------------- #
@api_router.get("/admin/users", response_model=List[UserPublic])
async def admin_list_users(_: dict = Depends(get_current_admin)):
    cursor = db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    docs = await cursor.to_list(500)
    return [to_public(d) for d in docs]


@api_router.post("/admin/users/{user_id}/approve", response_model=UserPublic)
async def admin_approve(user_id: str, _: dict = Depends(get_current_admin)):
    result = await db.users.find_one_and_update(
        {"id": user_id}, {"$set": {"status": "approved"}}, return_document=True
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


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Radios / positions
# --------------------------------------------------------------------------- #
@api_router.get("/radios")
async def list_radios(_: dict = Depends(get_current_user)) -> List[dict]:
    cursor = db.radios.find({}, {"_id": 0}).sort("last_seen", -1)
    return await cursor.to_list(500)


@api_router.get("/radios/{dmr_id}/positions")
async def radio_positions(dmr_id: int, limit: int = 200, _: dict = Depends(get_current_user)) -> List[dict]:
    cursor = (
        db.positions.find({"dmr_id": dmr_id}, {"_id": 0})
        .sort("timestamp", 1)
        .limit(min(limit, MAX_POSITIONS_PER_RADIO))
    )
    return await cursor.to_list(MAX_POSITIONS_PER_RADIO)


@api_router.patch("/radios/{dmr_id}")
async def update_radio(dmr_id: int, meta: RadioMeta, _: dict = Depends(get_current_user)):
    updates = {k: v for k, v in meta.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True}
    await db.radios.update_one({"dmr_id": dmr_id}, {"$set": updates})
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
async def get_packets(limit: int = 200, _: dict = Depends(get_current_user)) -> List[dict]:
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
# WebSocket (token in query string since browsers can't send headers on WS)
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
