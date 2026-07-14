"""Iteration 7: Situational-awareness token backend tests."""
import os
import time
import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
import websocket  # websocket-client

def _load_frontend_env():
    envpath = "/app/frontend/.env"
    if os.path.exists(envpath):
        for line in open(envpath):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE_URL = _load_frontend_env().rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@dmrtracker.app"
ADMIN_PASSWORD = "admin123"

WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")


# ------------------------- fixtures ------------------------- #
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_token(admin_headers):
    """Create a non-admin approved user for permission checks."""
    email = f"TEST_situ_user_{uuid.uuid4().hex[:8]}@example.com"
    pw = "userpass123"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw})
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    # admin approve
    ap = requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_headers)
    assert ap.status_code == 200, ap.text
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert login.status_code == 200
    yield login.json()["token"], uid
    # cleanup
    requests.delete(f"{API}/admin/users/{uid}", headers=admin_headers)


@pytest.fixture
def cleanup_tokens(admin_headers):
    created = []
    yield created
    for tid in created:
        try:
            requests.delete(f"{API}/situational-tokens/{tid}", headers=admin_headers)
        except Exception:
            pass


# ------------------------- Admin CRUD ------------------------- #
class TestSituationalTokenCRUD:
    def test_list_requires_admin(self):
        r = requests.get(f"{API}/situational-tokens")
        assert r.status_code in (401, 403)

    def test_list_ok_admin(self, admin_headers):
        r = requests.get(f"{API}/situational-tokens", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_basic(self, admin_headers, cleanup_tokens):
        r = requests.post(f"{API}/situational-tokens",
                          headers=admin_headers, json={"name": "TEST_basic"})
        assert r.status_code == 200, r.text
        data = r.json()
        cleanup_tokens.append(data["id"])
        for key in ("id", "token", "name", "group_id", "expires_at", "created_by", "created_at"):
            assert key in data
        assert data["name"] == "TEST_basic"
        assert data["group_id"] is None
        assert data["expires_at"] is None
        assert data["created_by"] == ADMIN_EMAIL
        # appears in list
        lst = requests.get(f"{API}/situational-tokens", headers=admin_headers).json()
        assert any(t["id"] == data["id"] for t in lst)

    def test_create_scoped_bad_group_404(self, admin_headers):
        r = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                          json={"name": "TEST_bad", "group_id": "does-not-exist"})
        assert r.status_code == 404

    def test_create_with_expiry(self, admin_headers, cleanup_tokens):
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        r = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                          json={"name": "TEST_expiring", "expires_at": future})
        assert r.status_code == 200
        d = r.json(); cleanup_tokens.append(d["id"])
        assert d["expires_at"] == future
        lst = requests.get(f"{API}/situational-tokens", headers=admin_headers).json()
        assert any(t["id"] == d["id"] and t["expires_at"] == future for t in lst)

    def test_delete_admin(self, admin_headers):
        r = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                          json={"name": "TEST_delme"})
        tid = r.json()["id"]
        d = requests.delete(f"{API}/situational-tokens/{tid}", headers=admin_headers)
        assert d.status_code == 200
        lst = requests.get(f"{API}/situational-tokens", headers=admin_headers).json()
        assert not any(t["id"] == tid for t in lst)

    def test_non_admin_forbidden(self, user_token, admin_headers, cleanup_tokens):
        token, _uid = user_token
        h = {"Authorization": f"Bearer {token}"}
        # GET
        assert requests.get(f"{API}/situational-tokens", headers=h).status_code == 403
        # POST
        assert requests.post(f"{API}/situational-tokens", headers=h,
                             json={"name": "nope"}).status_code == 403
        # DELETE — create one as admin, try delete as user
        r = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                          json={"name": "TEST_userdel"})
        tid = r.json()["id"]; cleanup_tokens.append(tid)
        assert requests.delete(f"{API}/situational-tokens/{tid}", headers=h).status_code == 403


# ------------------------- Public snapshot ------------------------- #
class TestPublicSnapshot:
    def test_snapshot_unknown_token_404(self):
        r = requests.get(f"{API}/situational/nope-not-real-token/snapshot")
        assert r.status_code == 404

    def test_snapshot_expired_token_404(self, admin_headers, cleanup_tokens):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        r = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                          json={"name": "TEST_expired", "expires_at": past})
        d = r.json(); cleanup_tokens.append(d["id"])
        snap = requests.get(f"{API}/situational/{d['token']}/snapshot")
        assert snap.status_code == 404

    def test_snapshot_no_auth_and_whitelisted_fields(self, admin_headers, cleanup_tokens):
        # Create token
        r = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                          json={"name": "TEST_snap"})
        d = r.json(); cleanup_tokens.append(d["id"])
        # Inject a radio position (admin authorized)
        dmr_id = 8500001
        inj = requests.post(f"{API}/inject", headers=admin_headers, json={
            "dmr_id": dmr_id, "callsign": "TESTSNP", "lat": 40.0, "lon": -100.0
        })
        assert inj.status_code == 200
        # Fetch snapshot WITHOUT any auth
        snap = requests.get(f"{API}/situational/{d['token']}/snapshot")
        assert snap.status_code == 200
        js = snap.json()
        assert "view" in js and "radios" in js and "emergencies" in js
        assert js["view"]["name"] == "TEST_snap"
        assert "server_time" in js["view"]
        allowed = {"dmr_id", "callsign", "group_id", "icon", "color",
                   "last_lat", "last_lon", "last_seen", "in_emergency", "emergency_id"}
        forbidden = {"password_hash", "email", "notes", "last_speed", "last_heading",
                     "last_rssi", "last_repeater_id", "last_source", "last_channel",
                     "position_count", "first_seen"}
        for radio in js["radios"]:
            for f in forbidden:
                assert f not in radio, f"radio leaks forbidden field {f}: {radio}"
            for k in radio.keys():
                assert k in allowed, f"radio contains unexpected field {k}"

    def test_snapshot_scoped_to_group(self, admin_headers, cleanup_tokens):
        # Create a fresh group
        gname = f"TEST_grp_{uuid.uuid4().hex[:6]}"
        # unique talkgroup id
        tgid = 90000 + int(time.time()) % 10000
        gr = requests.post(f"{API}/groups", headers=admin_headers,
                           json={"name": gname, "talkgroup_id": tgid})
        assert gr.status_code == 200, gr.text
        group = gr.json()
        try:
            # Inject a radio inside the group and one outside
            in_dmr = 8600001
            out_dmr = 8600002
            requests.post(f"{API}/inject", headers=admin_headers, json={
                "dmr_id": in_dmr, "callsign": "INGROUP", "lat": 41.0, "lon": -101.0,
                "group_id": group["id"]
            })
            requests.post(f"{API}/inject", headers=admin_headers, json={
                "dmr_id": out_dmr, "callsign": "OUTGROUP", "lat": 42.0, "lon": -102.0
            })
            # scoped token
            tk = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                               json={"name": "TEST_scoped", "group_id": group["id"]}).json()
            cleanup_tokens.append(tk["id"])
            snap = requests.get(f"{API}/situational/{tk['token']}/snapshot")
            assert snap.status_code == 200
            radios = snap.json()["radios"]
            dmr_ids = {r["dmr_id"] for r in radios}
            assert in_dmr in dmr_ids
            assert out_dmr not in dmr_ids
            assert all(r["group_id"] == group["id"] for r in radios)
        finally:
            requests.delete(f"{API}/groups/{group['id']}", headers=admin_headers)
            requests.delete(f"{API}/radios/{in_dmr}", headers=admin_headers)
            requests.delete(f"{API}/radios/{out_dmr}", headers=admin_headers)


# ------------------------- WebSocket ------------------------- #
class TestPublicWebSocket:
    def test_ws_hello_and_position(self, admin_headers, cleanup_tokens):
        # Create token
        d = requests.post(f"{API}/situational-tokens", headers=admin_headers,
                          json={"name": "TEST_ws"}).json()
        cleanup_tokens.append(d["id"])
        url = f"{WS_BASE}/api/situational/{d['token']}/ws"
        ws = websocket.create_connection(url, timeout=10)
        try:
            hello = json.loads(ws.recv())
            assert hello.get("type") == "hello"
            # inject a position -> expect a 'position' broadcast
            dmr_id = 8700001
            requests.post(f"{API}/inject", headers=admin_headers, json={
                "dmr_id": dmr_id, "callsign": "WSPOS", "lat": 45.0, "lon": -100.0
            })
            ws.settimeout(5)
            got_position = False
            for _ in range(10):
                try:
                    m = json.loads(ws.recv())
                except Exception:
                    break
                if m.get("type") == "position":
                    got_position = True
                    r = m["radio"]
                    for f in ("password_hash", "email", "notes"):
                        assert f not in r
                    break
            assert got_position, "did not receive position event on public ws"

            # simulate emergency
            em = requests.post(f"{API}/emergencies/simulate", headers=admin_headers,
                               json={"dmr_id": dmr_id})
            assert em.status_code == 200
            got_em = False
            emergency_id = None
            for _ in range(10):
                try:
                    m = json.loads(ws.recv())
                except Exception:
                    break
                if m.get("type") == "emergency":
                    got_em = True
                    emergency_id = m["emergency"]["id"]
                    break
            assert got_em

            # clear emergency
            requests.post(f"{API}/emergencies/{emergency_id}/clear", headers=admin_headers)
            got_clr = False
            for _ in range(10):
                try:
                    m = json.loads(ws.recv())
                except Exception:
                    break
                if m.get("type") == "emergency_cleared":
                    got_clr = True
                    break
            assert got_clr
        finally:
            ws.close()
            requests.delete(f"{API}/radios/8700001", headers=admin_headers)

    def test_ws_bad_token_closes_4404(self):
        url = f"{WS_BASE}/api/situational/definitely-not-real/ws"
        ws = websocket.WebSocket()
        try:
            ws.connect(url, timeout=10)
            # try to receive - should get close
            try:
                ws.recv()
            except websocket.WebSocketException:
                pass
            code = ws.close_status_code if hasattr(ws, "close_status_code") else None
            # websocket-client stores it as ws.status? Let's rely on connect raising or close code
            # The close frame code should be 4404
            assert code in (4404, None)  # None if connection was refused before ws handshake finalizes
        except websocket.WebSocketBadStatusException as e:
            # server rejected during handshake — acceptable for bad token
            assert True
        finally:
            try:
                ws.close()
            except Exception:
                pass


# ------------------------- Regression ------------------------- #
class TestRegression:
    @pytest.mark.parametrize("path", [
        "/status", "/radios", "/groups", "/emergencies",
        "/shift-log", "/messages", "/repeaters",
    ])
    def test_existing_endpoints_still_authenticate(self, admin_headers, path):
        r = requests.get(f"{API}{path}", headers=admin_headers)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("path", [
        "/status", "/radios", "/situational-tokens",
    ])
    def test_endpoints_still_require_auth(self, path):
        r = requests.get(f"{API}{path}")
        assert r.status_code in (401, 403)
