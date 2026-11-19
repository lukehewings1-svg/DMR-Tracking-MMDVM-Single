# Iteration 17: MMDVM connection settings, per-MMDVM passwords, HomeBrew UDP auth enforcement, admin-only access
import hashlib
import os
import socket
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@dmrtracker.app", "password": "admin123"}
DEFAULTS = {"public_host": "", "local_host": "", "hb_port": 62031, "shared_password": "PASSWORD",
            "server_dmr_id": 9990001, "color_code": 1, "voice_slot": 2, "data_slot": 1}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    return r


@pytest.fixture(scope="module")
def admin():
    r = _login(**ADMIN)
    if r.status_code != 200:
        pytest.skip("admin login failed")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    yield s
    # restore + cleanup any TEST_ mmdvms created by this module (by id)
    s.put(f"{BASE_URL}/api/admin/connection", json=DEFAULTS)
    for mid in CREATED:
        s.delete(f"{BASE_URL}/api/mmdvms/{mid}")


CREATED: list = []


def hb_login(rpt_id: int, password: str) -> bytes:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)
    try:
        sock.sendto(b"RPTL" + rpt_id.to_bytes(4, "big"), ("127.0.0.1", 62031))
        data, _ = sock.recvfrom(1024)
        assert data.startswith(b"RPTACK")
        salt = data[6:10]
        sock.sendto(b"RPTK" + rpt_id.to_bytes(4, "big") + hashlib.sha256(salt + password.encode()).digest(), ("127.0.0.1", 62031))
        data, _ = sock.recvfrom(1024)
        # close session politely
        sock.sendto(b"RPTCL" + rpt_id.to_bytes(4, "big"), ("127.0.0.1", 62031))
        return data
    finally:
        sock.close()


# --- Connection settings ---
class TestConnection:
    def test_get_connection_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/connection")
        assert r.status_code == 200
        d = r.json()
        for k in ("saved", "running", "pending_restart", "local_ips", "hostname", "listening", "rejected_logins", "per_mmdvm_passwords"):
            assert k in d
        assert d["listening"] is True
        assert d["running"]["hb_port"] == 62031
        assert isinstance(d["local_ips"], list)

    def test_address_change_not_pending(self, admin):
        r = admin.put(f"{BASE_URL}/api/admin/connection", json={**DEFAULTS, "public_host": "  TEST.dmr.example.org ", "local_host": "192.168.1.77"})
        assert r.status_code == 200
        d = r.json()
        assert d["saved"]["public_host"] == "TEST.dmr.example.org"
        assert d["saved"]["local_host"] == "192.168.1.77"
        assert d["pending_restart"] is False
        g = admin.get(f"{BASE_URL}/api/admin/connection").json()
        assert g["saved"]["public_host"] == "TEST.dmr.example.org"

    def test_port_change_pending(self, admin):
        r = admin.put(f"{BASE_URL}/api/admin/connection", json={**DEFAULTS, "hb_port": 62035, "color_code": 3})
        assert r.status_code == 200
        d = r.json()
        assert d["pending_restart"] is True
        assert d["running"]["hb_port"] == 62031
        assert d["saved"]["hb_port"] == 62035

    @pytest.mark.parametrize("bad", [{"hb_port": 80}, {"color_code": 16}, {"voice_slot": 3}, {"shared_password": ""}, {"server_dmr_id": 0}])
    def test_validation(self, admin, bad):
        r = admin.put(f"{BASE_URL}/api/admin/connection", json={**DEFAULTS, **bad})
        assert r.status_code == 422

    def test_restore_defaults(self, admin):
        r = admin.put(f"{BASE_URL}/api/admin/connection", json=DEFAULTS)
        assert r.status_code == 200
        assert r.json()["pending_restart"] is False
        assert r.json()["saved"] == DEFAULTS

    def test_public_ip(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/connection/public-ip")
        assert r.status_code in (200, 502)
        if r.status_code == 200:
            assert r.json()["ip"].count(".") == 3 or ":" in r.json()["ip"]


# --- Admin-only enforcement ---
class TestAccess:
    @pytest.mark.parametrize("method,path", [("get", "/api/admin/connection"), ("put", "/api/admin/connection"),
                                             ("get", "/api/admin/connection/public-ip"), ("post", "/api/admin/restart"),
                                             ("get", "/api/mmdvms"), ("post", "/api/mmdvms"),
                                             ("put", "/api/mmdvms/x"), ("delete", "/api/mmdvms/x")])
    def test_no_token(self, method, path):
        r = getattr(requests, method)(f"{BASE_URL}{path}", json={})
        assert r.status_code in (401, 403)

    def test_non_admin_403(self, admin):
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "testpass123", "name": "TEST_user"})
        assert r.status_code in (200, 201), r.text
        users = admin.get(f"{BASE_URL}/api/admin/users").json()
        uid = next(u["id"] for u in users if u["email"] == email)
        try:
            admin.post(f"{BASE_URL}/api/admin/users/{uid}/approve")
            lr = _login(email, "testpass123")
            assert lr.status_code == 200
            h = {"Authorization": f"Bearer {lr.json()['token']}"}
            for m, p in [("get", "/api/admin/connection"), ("put", "/api/admin/connection"), ("get", "/api/admin/connection/public-ip"),
                         ("post", "/api/admin/restart"), ("get", "/api/mmdvms"), ("post", "/api/mmdvms"), ("delete", "/api/mmdvms/x")]:
                rr = getattr(requests, m)(f"{BASE_URL}{p}", headers=h, json=DEFAULTS if m == "put" else {})
                assert rr.status_code == 403, f"{m} {p} -> {rr.status_code}"
        finally:
            admin.delete(f"{BASE_URL}/api/admin/users/{uid}")


# --- MMDVM CRUD + UDP enforcement ---
class TestMmdvms:
    def test_shared_mode_any_id(self, admin):
        assert admin.get(f"{BASE_URL}/api/mmdvms").json() == [], "pre-existing MMDVMs - shared mode not testable"
        assert hb_login(234500101, "PASSWORD").startswith(b"RPTACK")
        assert hb_login(234500102, "wrongpw").startswith(b"MSTNAK")

    def test_crud_and_enforcement(self, admin):
        r = admin.post(f"{BASE_URL}/api/mmdvms", json={"name": "TEST_North", "repeater_id": 234500199, "password": "secret99"})
        assert r.status_code == 200, r.text
        m = r.json()
        CREATED.append(m["id"])
        assert m["repeater_id"] == 234500199 and m["password"] == "secret99" and "_id" not in m
        lst = admin.get(f"{BASE_URL}/api/mmdvms").json()
        assert any(x["id"] == m["id"] for x in lst)
        assert admin.get(f"{BASE_URL}/api/admin/connection").json()["per_mmdvm_passwords"] is True
        # duplicate
        assert admin.post(f"{BASE_URL}/api/mmdvms", json={"name": "TEST_dup", "repeater_id": 234500199, "password": "secret99"}).status_code == 409
        # validation
        assert admin.post(f"{BASE_URL}/api/mmdvms", json={"name": "TEST_x", "repeater_id": 1, "password": "abc"}).status_code == 422
        # UDP: own password OK, shared refused, unregistered refused
        assert hb_login(234500199, "secret99").startswith(b"RPTACK")
        assert hb_login(234500199, "PASSWORD").startswith(b"MSTNAK")
        assert hb_login(234500177, "PASSWORD").startswith(b"MSTNAK")
        rej = {x["repeater_id"]: x["reason"] for x in admin.get(f"{BASE_URL}/api/admin/connection").json()["rejected_logins"]}
        assert rej.get(234500199) == "wrong password"
        assert rej.get(234500177) == "MMDVM ID not registered"
        # update password -> immediate
        u = admin.put(f"{BASE_URL}/api/mmdvms/{m['id']}", json={"name": "TEST_North2", "repeater_id": 234500199, "password": "newsecret"})
        assert u.status_code == 200 and u.json()["name"] == "TEST_North2"
        assert hb_login(234500199, "newsecret").startswith(b"RPTACK")
        assert hb_login(234500199, "secret99").startswith(b"MSTNAK")
        # 404s
        assert admin.put(f"{BASE_URL}/api/mmdvms/nope", json={"name": "TEST_n", "repeater_id": 234500198, "password": "secret99"}).status_code == 404
        assert admin.delete(f"{BASE_URL}/api/mmdvms/nope").status_code == 404
        # delete -> back to shared mode
        assert admin.delete(f"{BASE_URL}/api/mmdvms/{m['id']}").status_code == 200
        CREATED.remove(m["id"])
        assert admin.get(f"{BASE_URL}/api/admin/connection").json()["per_mmdvm_passwords"] is False
        assert hb_login(234500177, "PASSWORD").startswith(b"RPTACK")

    def test_update_clash_409(self, admin):
        a = admin.post(f"{BASE_URL}/api/mmdvms", json={"name": "TEST_A", "repeater_id": 234500301, "password": "secretA1"}).json()
        CREATED.append(a["id"])
        b = admin.post(f"{BASE_URL}/api/mmdvms", json={"name": "TEST_B", "repeater_id": 234500302, "password": "secretB1"}).json()
        CREATED.append(b["id"])
        r = admin.put(f"{BASE_URL}/api/mmdvms/{b['id']}", json={"name": "TEST_B", "repeater_id": 234500301, "password": "secretB1"})
        assert r.status_code == 409
        for x in (a, b):
            assert admin.delete(f"{BASE_URL}/api/mmdvms/{x['id']}").status_code == 200
            CREATED.remove(x["id"])
