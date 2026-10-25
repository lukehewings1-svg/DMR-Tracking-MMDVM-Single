"""Iteration 8: Event overlays backend tests.

Covers admin CRUD, RBAC, shapes replacement (with unknown-type filtering),
image upload/patch/delete, cascade-delete file cleanup, WS broadcasts
(private + public), snapshot filter (active-only), and static file serving.
"""
import os
import json
import time
import uuid

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
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

ADMIN_EMAIL = "admin@dmrtracker.app"
ADMIN_PASSWORD = "admin123"


# Minimal 1x1 transparent PNG
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x00\x03\x00\x01\xa1\xd8\xd6\xa1\x00\x00\x00\x00IEND\xaeB`\x82"
)


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
def user_headers(admin_headers):
    email = f"TEST_ov_user_{uuid.uuid4().hex[:8]}@example.com"
    pw = "userpass123"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw})
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    ap = requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_headers)
    assert ap.status_code == 200, ap.text
    login = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert login.status_code == 200
    tok = login.json()["token"]
    yield {"Authorization": f"Bearer {tok}"}
    requests.delete(f"{API}/admin/users/{uid}", headers=admin_headers)


@pytest.fixture
def overlay(admin_headers):
    """Create a fresh overlay per test and clean up."""
    r = requests.post(f"{API}/overlays", json={"name": f"TEST_{uuid.uuid4().hex[:6]}"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    doc = r.json()
    yield doc
    requests.delete(f"{API}/overlays/{doc['id']}", headers=admin_headers)


# ------------------------- auth ------------------------- #
class TestAuth:
    def test_list_requires_auth(self):
        r = requests.get(f"{API}/overlays")
        assert r.status_code in (401, 403)

    def test_admin_list_returns_array(self, admin_headers):
        r = requests.get(f"{API}/overlays", headers=admin_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_non_admin_forbidden_on_writes(self, user_headers, admin_headers):
        # POST forbidden
        r = requests.post(f"{API}/overlays", json={"name": "Nope"}, headers=user_headers)
        assert r.status_code == 403
        # GET allowed
        rg = requests.get(f"{API}/overlays", headers=user_headers)
        assert rg.status_code == 200
        # create as admin, then user can't patch/delete
        c = requests.post(f"{API}/overlays", json={"name": "TEST_rbac"}, headers=admin_headers)
        oid = c.json()["id"]
        try:
            p = requests.patch(f"{API}/overlays/{oid}", json={"active": True}, headers=user_headers)
            assert p.status_code == 403
            d = requests.delete(f"{API}/overlays/{oid}", headers=user_headers)
            assert d.status_code == 403
        finally:
            requests.delete(f"{API}/overlays/{oid}", headers=admin_headers)


# ------------------------- CRUD ------------------------- #
class TestCRUD:
    def test_create_shape(self, admin_headers):
        r = requests.post(f"{API}/overlays", json={"name": "TEST_Halloween"}, headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        try:
            assert d["name"] == "TEST_Halloween"
            assert d["active"] is False
            assert d["shapes"] == []
            assert d["images"] == []
            assert "id" in d and "created_by" in d and "created_at" in d
        finally:
            requests.delete(f"{API}/overlays/{d['id']}", headers=admin_headers)

    def test_patch_active_and_rename(self, overlay, admin_headers):
        oid = overlay["id"]
        r = requests.patch(f"{API}/overlays/{oid}", json={"active": True}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["active"] is True

        r2 = requests.patch(f"{API}/overlays/{oid}", json={"name": "newname"}, headers=admin_headers)
        assert r2.status_code == 200
        assert r2.json()["name"] == "newname"

        # verify persistence
        g = requests.get(f"{API}/overlays/{oid}", headers=admin_headers).json()
        assert g["name"] == "newname" and g["active"] is True

    def test_delete_removes(self, admin_headers):
        c = requests.post(f"{API}/overlays", json={"name": "TEST_del"}, headers=admin_headers).json()
        oid = c["id"]
        d = requests.delete(f"{API}/overlays/{oid}", headers=admin_headers)
        assert d.status_code == 200
        g = requests.get(f"{API}/overlays/{oid}", headers=admin_headers)
        assert g.status_code == 404


# ------------------------- shapes ------------------------- #
class TestShapes:
    def test_replace_persists_and_assigns_id(self, overlay, admin_headers):
        oid = overlay["id"]
        body = {
            "shapes": [
                {"type": "marker", "name": "Aid Station 1", "color": "#39ff14",
                 "geometry": {"lat": 40, "lng": -105}}
            ]
        }
        r = requests.put(f"{API}/overlays/{oid}/shapes", json=body, headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["shapes"]) == 1
        s = d["shapes"][0]
        assert s["type"] == "marker"
        assert s["name"] == "Aid Station 1"
        assert s["color"] == "#39ff14"
        assert s["geometry"]["lat"] == 40 and s["geometry"]["lng"] == -105
        assert s.get("id"), "server should assign id"

    def test_replace_strips_unknown_types(self, overlay, admin_headers):
        oid = overlay["id"]
        body = {
            "shapes": [
                {"type": "marker", "name": "keep", "geometry": {"lat": 1, "lng": 2}},
                {"type": "unknown", "name": "drop", "geometry": {}},
            ]
        }
        r = requests.put(f"{API}/overlays/{oid}/shapes", json=body, headers=admin_headers)
        # pydantic may accept "unknown" as string, backend then strips.
        assert r.status_code == 200, r.text
        types = [s["type"] for s in r.json()["shapes"]]
        assert "unknown" not in types
        assert types == ["marker"]


# ------------------------- images ------------------------- #
class TestImages:
    def _upload(self, overlay_id, headers, bytes_=PNG_BYTES, filename="test.png"):
        files = {"file": (filename, bytes_, "image/png")}
        data = {
            "name": "TEST img",
            "sw_lat": "40.0", "sw_lng": "-105.0",
            "ne_lat": "41.0", "ne_lng": "-104.0",
            "opacity": "0.6",
        }
        return requests.post(
            f"{API}/overlays/{overlay_id}/images",
            files=files, data=data, headers=headers,
        )

    def test_upload_and_serve(self, overlay, admin_headers):
        oid = overlay["id"]
        r = self._upload(oid, admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["images"]) == 1
        img = d["images"][0]
        assert img["url"].startswith("/api/uploads/overlays/")
        assert img["bounds"] == [[40.0, -105.0], [41.0, -104.0]]
        assert img["opacity"] == 0.6
        # serve
        served = requests.get(f"{BASE_URL}{img['url']}")
        assert served.status_code == 200
        assert served.content == PNG_BYTES

    def test_bad_extension(self, overlay, admin_headers):
        oid = overlay["id"]
        r = self._upload(oid, admin_headers, filename="malware.exe")
        assert r.status_code == 400

    def test_patch_image(self, overlay, admin_headers):
        oid = overlay["id"]
        up = self._upload(oid, admin_headers).json()
        img_id = up["images"][0]["id"]
        r = requests.patch(
            f"{API}/overlays/{oid}/images/{img_id}",
            json={"opacity": 0.3, "bounds": [[10, 20], [11, 21]]},
            headers=admin_headers,
        )
        assert r.status_code == 200
        img = next(i for i in r.json()["images"] if i["id"] == img_id)
        assert img["opacity"] == 0.3
        assert img["bounds"] == [[10, 20], [11, 21]]

    def test_delete_image_removes_file(self, overlay, admin_headers):
        oid = overlay["id"]
        up = self._upload(oid, admin_headers).json()
        img = up["images"][0]
        file_url = f"{BASE_URL}{img['url']}"
        assert requests.get(file_url).status_code == 200
        r = requests.delete(
            f"{API}/overlays/{oid}/images/{img['id']}", headers=admin_headers
        )
        assert r.status_code == 200
        assert not any(i["id"] == img["id"] for i in r.json()["images"])
        assert requests.get(file_url).status_code == 404

    def test_cascade_delete_overlay_removes_files(self, admin_headers):
        c = requests.post(f"{API}/overlays", json={"name": "TEST_cascade"}, headers=admin_headers).json()
        oid = c["id"]
        up = TestImages()._upload(oid, admin_headers).json()
        file_url = f"{BASE_URL}{up['images'][0]['url']}"
        assert requests.get(file_url).status_code == 200
        d = requests.delete(f"{API}/overlays/{oid}", headers=admin_headers)
        assert d.status_code == 200
        assert requests.get(file_url).status_code == 404


# ------------------------- WS + snapshot ------------------------- #
class TestWSAndSnapshot:
    def test_private_ws_receives_upsert_and_remove(self, admin_token, admin_headers):
        ws = websocket.create_connection(f"{WS_BASE}/api/ws?token={admin_token}", timeout=8)
        try:
            # drain hello
            ws.settimeout(3)
            try:
                first = json.loads(ws.recv())
                assert first["type"] == "hello"
            except Exception:
                pass

            # create
            c = requests.post(f"{API}/overlays", json={"name": "TEST_ws"}, headers=admin_headers).json()
            oid = c["id"]
            saw_upsert = False
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    m = json.loads(ws.recv())
                except Exception:
                    break
                if m.get("type") == "overlay_upserted" and m["overlay"]["id"] == oid:
                    saw_upsert = True
                    break
            assert saw_upsert, "did not receive overlay_upserted"

            # delete → overlay_removed
            requests.delete(f"{API}/overlays/{oid}", headers=admin_headers)
            saw_remove = False
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    m = json.loads(ws.recv())
                except Exception:
                    break
                if m.get("type") == "overlay_removed" and m.get("overlay_id") == oid:
                    saw_remove = True
                    break
            assert saw_remove, "did not receive overlay_removed"
        finally:
            ws.close()

    def test_snapshot_and_public_ws_only_active(self, admin_headers):
        # create situational token
        tok_body = {"name": f"TEST_ov_tok_{uuid.uuid4().hex[:6]}"}
        tr = requests.post(f"{API}/situational-tokens", json=tok_body, headers=admin_headers)
        assert tr.status_code == 200, tr.text
        token_doc = tr.json()
        token_id = token_doc["id"]
        pub_token = token_doc["token"]

        # Two overlays: one active, one inactive
        active = requests.post(f"{API}/overlays", json={"name": "TEST_active"}, headers=admin_headers).json()
        inactive = requests.post(f"{API}/overlays", json={"name": "TEST_inactive"}, headers=admin_headers).json()
        try:
            requests.patch(f"{API}/overlays/{active['id']}", json={"active": True}, headers=admin_headers)

            # snapshot
            snap = requests.get(f"{API}/situational/{pub_token}/snapshot").json()
            ids = [o["id"] for o in snap.get("overlays", [])]
            assert active["id"] in ids
            assert inactive["id"] not in ids

            # public WS: activate deactivate -> overlay_removed
            ws = websocket.create_connection(f"{WS_BASE}/api/situational/{pub_token}/ws", timeout=8)
            ws.settimeout(3)
            try:
                try:
                    ws.recv()  # hello
                except Exception:
                    pass
                # Deactivate the active overlay → public should see overlay_removed
                requests.patch(f"{API}/overlays/{active['id']}", json={"active": False}, headers=admin_headers)
                got_removed = False
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        m = json.loads(ws.recv())
                    except Exception:
                        break
                    if m.get("type") == "overlay_removed" and m.get("overlay_id") == active["id"]:
                        got_removed = True
                        break
                assert got_removed, "public WS did not get overlay_removed on deactivate"

                # Activate again → public should see overlay_upserted
                requests.patch(f"{API}/overlays/{active['id']}", json={"active": True}, headers=admin_headers)
                got_upsert = False
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        m = json.loads(ws.recv())
                    except Exception:
                        break
                    if m.get("type") == "overlay_upserted" and m["overlay"]["id"] == active["id"]:
                        got_upsert = True
                        break
                assert got_upsert, "public WS did not get overlay_upserted on activate"

                # Public should NOT receive upserts for inactive overlays.
                # Patch the inactive overlay's name (still inactive) - should get overlay_removed sanitised event.
                requests.patch(f"{API}/overlays/{inactive['id']}", json={"name": "still_inactive"}, headers=admin_headers)
                got_upsert_for_inactive = False
                deadline = time.time() + 2
                while time.time() < deadline:
                    try:
                        m = json.loads(ws.recv())
                    except Exception:
                        break
                    if m.get("type") == "overlay_upserted" and m["overlay"]["id"] == inactive["id"]:
                        got_upsert_for_inactive = True
                        break
                assert not got_upsert_for_inactive, "public WS should not receive upsert for inactive overlay"
            finally:
                ws.close()
        finally:
            requests.delete(f"{API}/overlays/{active['id']}", headers=admin_headers)
            requests.delete(f"{API}/overlays/{inactive['id']}", headers=admin_headers)
            requests.delete(f"{API}/situational-tokens/{token_id}", headers=admin_headers)


# ------------------------- regression ------------------------- #
class TestRegression:
    def test_existing_endpoints(self, admin_headers):
        for path in ["/radios", "/groups", "/situational-tokens", "/emergencies", "/shift-log", "/channels"]:
            r = requests.get(f"{API}{path}", headers=admin_headers)
            assert r.status_code == 200, f"{path} => {r.status_code}: {r.text[:120]}"
            # no _id leaked
            payload = r.json()
            if isinstance(payload, list):
                for it in payload[:5]:
                    if isinstance(it, dict):
                        assert "_id" not in it, f"{path} leaks _id"
