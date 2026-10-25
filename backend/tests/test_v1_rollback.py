"""Regression tests after rollback to v1 single-org DMR tracker."""
import asyncio
import json
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@dmrtracker.app", "password": "admin123"}


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"]["role"] == "admin"
    return {"Authorization": f"Bearer {d['token']}"}


# --- Multi-org removal ---
@pytest.mark.parametrize("path", ["/orgs", "/events", "/org-links", "/super-admin/orgs"])
def test_multi_org_endpoints_gone(H, path):
    r = requests.get(f"{API}{path}", headers=H, timeout=15)
    assert r.status_code == 404, f"{path} -> {r.status_code}"


def test_root_and_status(H):
    assert requests.get(f"{API}/", timeout=15).json()["service"] == "dmr-tracker"
    r = requests.get(f"{API}/status", headers=H, timeout=15)
    assert r.status_code == 200 and "listener" in r.json()


def test_unauth_rejected():
    assert requests.get(f"{API}/radios", timeout=15).status_code in (401, 403)


# --- Groups CRUD ---
def test_groups_crud(H):
    r = requests.post(f"{API}/groups", headers=H, json={"name": "TEST_grp", "talkgroup_id": 91001, "color": "#ff0000"}, timeout=15)
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["name"] == "TEST_grp" and g["talkgroup_id"] == 91001
    gid = g["id"]
    r = requests.patch(f"{API}/groups/{gid}", headers=H, json={"name": "TEST_grp2"}, timeout=15)
    assert r.status_code == 200 and r.json()["name"] == "TEST_grp2"
    lst = requests.get(f"{API}/groups", headers=H, timeout=15).json()
    assert any(x["id"] == gid and x["name"] == "TEST_grp2" for x in lst)
    assert requests.delete(f"{API}/groups/{gid}", headers=H, timeout=15).status_code == 200
    lst = requests.get(f"{API}/groups", headers=H, timeout=15).json()
    assert not any(x["id"] == gid for x in lst)


# --- Radios via inject ---
def test_radio_inject_patch_delete(H):
    dmr = 9990001
    r = requests.post(f"{API}/inject", headers=H, json={"dmr_id": dmr, "callsign": "TESTRAD", "lat": 51.5, "lon": -0.12}, timeout=15)
    assert r.status_code == 200 and r.json()["ok"]
    radios = requests.get(f"{API}/radios", headers=H, timeout=15).json()
    rad = next((x for x in radios if x["dmr_id"] == dmr), None)
    assert rad and abs(rad["last_lat"] - 51.5) < 1e-6
    assert requests.patch(f"{API}/radios/{dmr}", headers=H, json={"notes": "TEST note"}, timeout=15).status_code == 200
    radios = requests.get(f"{API}/radios", headers=H, timeout=15).json()
    assert next(x for x in radios if x["dmr_id"] == dmr).get("notes") == "TEST note"
    pos = requests.get(f"{API}/radios/{dmr}/positions", headers=H, timeout=15).json()
    assert len(pos) >= 1
    assert requests.delete(f"{API}/radios/{dmr}", headers=H, timeout=15).status_code == 200
    radios = requests.get(f"{API}/radios", headers=H, timeout=15).json()
    assert not any(x["dmr_id"] == dmr for x in radios)


# --- Geofences ---
def test_geofences_crud(H):
    r = requests.post(f"{API}/geofences", headers=H, json={"name": "TEST_fence", "lat": 51.5, "lon": -0.1, "radius_m": 500}, timeout=15)
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    assert any(f["id"] == fid for f in requests.get(f"{API}/geofences", headers=H, timeout=15).json())
    assert requests.delete(f"{API}/geofences/{fid}", headers=H, timeout=15).status_code == 200
    assert not any(f["id"] == fid for f in requests.get(f"{API}/geofences", headers=H, timeout=15).json())
    assert requests.get(f"{API}/alerts", headers=H, timeout=15).status_code == 200


# --- Overlays ---
def test_overlays_crud(H):
    r = requests.post(f"{API}/overlays", headers=H, json={"name": "TEST_ov"}, timeout=15)
    assert r.status_code == 200, r.text
    oid = r.json()["id"]
    r = requests.put(f"{API}/overlays/{oid}/shapes", headers=H, json={"shapes": [{"type": "marker", "geometry": {"lat": 1, "lng": 2}}]}, timeout=15)
    assert r.status_code == 200 and len(r.json()["shapes"]) == 1
    assert any(o["id"] == oid for o in requests.get(f"{API}/overlays", headers=H, timeout=15).json())
    assert requests.delete(f"{API}/overlays/{oid}", headers=H, timeout=15).status_code == 200
    assert requests.get(f"{API}/overlays/{oid}", headers=H, timeout=15).status_code == 404


# --- Shift log ---
def test_shift_log_and_csv(H):
    r = requests.get(f"{API}/shift-log", headers=H, timeout=15)
    assert r.status_code == 200 and isinstance(r.json(), list)
    r = requests.get(f"{API}/shift-log/export.csv", headers=H, timeout=15)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers.get("content-disposition", "")
    assert requests.get(f"{API}/shift-log?event_type=bogus", headers=H, timeout=15).status_code == 400


# --- Situational ---
def test_situational_tokens(H):
    r = requests.post(f"{API}/situational-tokens", headers=H, json={"name": "TEST_sa"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d["token"]
    snap = requests.get(f"{API}/situational/{tok}/snapshot", timeout=15)
    assert snap.status_code == 200 and "radios" in snap.json()
    assert requests.get(f"{API}/situational/badtoken123/snapshot", timeout=15).status_code == 404
    assert requests.delete(f"{API}/situational-tokens/{d['id']}", headers=H, timeout=15).status_code == 200
    assert requests.get(f"{API}/situational/{tok}/snapshot", timeout=15).status_code == 404


# --- Users approve + ACL ---
def test_register_approve_login_acl(H):
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Password!123", "callsign": "TST"}, timeout=15)
    assert r.status_code == 200 and r.json()["status"] == "pending"
    uid = r.json()["id"]
    assert requests.post(f"{API}/auth/login", json={"email": email, "password": "Password!123"}, timeout=15).status_code in (401, 403)
    r = requests.post(f"{API}/admin/users/{uid}/approve", headers=H, timeout=15)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Password!123"}, timeout=15)
    assert r.status_code == 200
    utok = r.json()["token"]
    g = requests.post(f"{API}/groups", headers=H, json={"name": "TEST_acl", "talkgroup_id": 91002}, timeout=15).json()
    r = requests.post(f"{API}/admin/users/{uid}/groups", headers=H, json={"allowed_group_ids": [g["id"]]}, timeout=15)
    assert r.status_code == 200 and r.json()["allowed_group_ids"] == [g["id"]]
    # non-admin cannot list users
    assert requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {utok}"}, timeout=15).status_code == 403
    assert requests.get(f"{API}/radios", headers={"Authorization": f"Bearer {utok}"}, timeout=15).status_code == 200
    requests.delete(f"{API}/groups/{g['id']}", headers=H, timeout=15)
    assert requests.delete(f"{API}/admin/users/{uid}", headers=H, timeout=15).status_code == 200


# --- Messaging ---
def test_messages(H):
    r = requests.post(f"{API}/messages", headers=H, json={"text": "TEST hi", "target_dmr_id": 9990002}, timeout=15)
    assert r.status_code == 200, r.text
    assert requests.post(f"{API}/messages", headers=H, json={"text": "x"}, timeout=15).status_code == 400
    msgs = requests.get(f"{API}/messages", headers=H, timeout=15).json()
    assert any(m.get("text") == "TEST hi" for m in msgs)
    assert requests.post(f"{API}/messages/simulate-inbound", headers=H, json={"from_dmr_id": 9990002, "text": "TEST in"}, timeout=15).status_code == 200


# --- WebSocket ---
def test_websocket(H):
    import websockets
    ws_url = BASE_URL.replace("https://", "wss://") + "/api/ws?token=" + H["Authorization"].split()[1]

    async def go():
        async with websockets.connect(ws_url, open_timeout=15) as ws:
            return json.loads(await asyncio.wait_for(ws.recv(), 10))

    msg = asyncio.run(go())
    assert msg["type"] == "hello"


# --- Lockout ---
def test_bruteforce_lockout():
    email = f"lock_{uuid.uuid4().hex[:6]}@example.com"
    codes = [requests.post(f"{API}/auth/login", json={"email": email, "password": "bad"}, timeout=15).status_code for _ in range(7)]
    assert 429 in codes, codes
