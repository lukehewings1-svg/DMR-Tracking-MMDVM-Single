"""JWT + bcrypt auth helpers for the DMR tracker.

Adapted from the standard custom-auth playbook. We use Bearer tokens in the
Authorization header (works with CORS="*") instead of httpOnly cookies. Users
self-register into a `pending` state and can only log in after an admin
approves them.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=12)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    callsign: Optional[str] = Field(default=None, max_length=32)


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    callsign: Optional[str] = None
    role: str
    status: str
    created_at: str


class RolePayload(BaseModel):
    role: str = Field(pattern="^(admin|user)$")


# --------------------------------------------------------------------------- #
# Password + JWT
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + ACCESS_TOKEN_TTL,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def to_public(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "callsign": user.get("callsign"),
        "role": user.get("role", "user"),
        "status": user.get("status", "approved"),
        "created_at": user.get("created_at"),
    }


# --------------------------------------------------------------------------- #
# Persistence helpers - db handle injected from server.py to avoid circular imports
# --------------------------------------------------------------------------- #
_DB = {"db": None}


def bind_db(db) -> None:
    _DB["db"] = db


def _db():
    if _DB["db"] is None:
        raise RuntimeError("auth db not bound")
    return _DB["db"]


async def get_user_by_email(email: str) -> Optional[dict]:
    return await _db().users.find_one({"email": email.lower()}, {"_id": 0})


async def get_user_by_id(user_id: str) -> Optional[dict]:
    return await _db().users.find_one({"id": user_id}, {"_id": 0})


# --------------------------------------------------------------------------- #
# Brute force
# --------------------------------------------------------------------------- #
async def _register_failed(identifier: str) -> None:
    now = time.time()
    await _db().login_attempts.update_one(
        {"identifier": identifier},
        {"$inc": {"count": 1}, "$set": {"last_at": now}},
        upsert=True,
    )


async def _clear_failed(identifier: str) -> None:
    await _db().login_attempts.delete_one({"identifier": identifier})


async def check_locked(identifier: str) -> None:
    doc = await _db().login_attempts.find_one({"identifier": identifier})
    if not doc:
        return
    if doc.get("count", 0) >= MAX_ATTEMPTS:
        if time.time() - doc.get("last_at", 0) < LOCKOUT_SECONDS:
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again later.",
            )
        await _clear_failed(identifier)


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #
async def get_current_user(request: Request) -> dict:
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("status") != "approved":
        raise HTTPException(status_code=403, detail="Account not approved yet")
    user.pop("password_hash", None)
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# --------------------------------------------------------------------------- #
# Seed admin
# --------------------------------------------------------------------------- #
async def seed_admin() -> None:
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await _db().users.find_one({"email": email})
    if existing is None:
        await _db().users.insert_one(
            {
                "id": str(uuid.uuid4()),
                "email": email,
                "password_hash": hash_password(password),
                "callsign": "ADMIN",
                "role": "admin",
                "status": "approved",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    else:
        # Rehash if the .env password changed OR was ever stored with an
        # invalid hash. Also ensure the admin is approved.
        needs_pw_reset = not verify_password(password, existing.get("password_hash", ""))
        update = {}
        if needs_pw_reset:
            update["password_hash"] = hash_password(password)
        if existing.get("status") != "approved":
            update["status"] = "approved"
        if existing.get("role") != "admin":
            update["role"] = "admin"
        if update:
            await _db().users.update_one({"email": email}, {"$set": update})


async def ensure_indexes() -> None:
    await _db().users.create_index("email", unique=True)
    await _db().users.create_index("id", unique=True)
    await _db().login_attempts.create_index("identifier")


# --------------------------------------------------------------------------- #
# Endpoint helpers used by server.py
# --------------------------------------------------------------------------- #
async def register_user(body: RegisterPayload) -> dict:
    email = body.email.lower()
    if await get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(body.password),
        "callsign": body.callsign,
        "role": "user",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db().users.insert_one(user)
    user.pop("password_hash", None)
    return to_public(user)


async def login_user(body: LoginPayload, ip: str) -> dict:
    email = body.email.lower()
    ident = f"{ip}:{email}"
    await check_locked(ident)
    user = await get_user_by_email(email)
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        await _register_failed(ident)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.get("status") == "pending":
        raise HTTPException(
            status_code=403,
            detail="Your account is pending admin approval.",
        )
    if user.get("status") == "rejected":
        raise HTTPException(status_code=403, detail="Your account has been rejected.")
    await _clear_failed(ident)
    token = create_access_token(user["id"], user["email"], user.get("role", "user"))
    return {"token": token, "user": to_public(user)}
