"""Backend tests for DMR radio tracker."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://gps-radio-dashboard.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@dmrtracker.app"
ADMIN_PASSWORD = "admin123"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def pending_user():
    # Unique-per-run pending user
    email = f"TEST_pending_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Password!123"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw, "callsign": "TESTPEND"}, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["status"] == "pending"
    return {"email": email, "password": pw, "id": body["id"]}


# ---------- Auth ----------
class TestAuth:
    def test_login_success(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-pw"}, timeout=15)
        assert r.status_code in (400, 401)

    def test_auth_me(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        u = r.json()
        assert u["email"] == ADMIN_EMAIL
        assert u["role"] == "admin"
        assert u["status"] == "approved"

    def test_pending_user_cannot_login(self, pending_user):
        r = requests.post(f"{API}/auth/login", json={"email": pending_user["email"], "password": pending_user["password"]}, timeout=15)
        assert r.status_code in (400, 401, 403), f"expected reject, got {r.status_code}: {r.text}"
        assert "approv" in r.text.lower() or "pending" in r.text.lower()


# ---------- Admin flow ----------
class TestAdmin:
    def test_list_users_requires_admin(self, admin_headers):
        r = requests.get(f"{API}/admin/users", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_approve_and_login(self, admin_headers, pending_user):
        r = requests.post(f"{API}/admin/users/{pending_user['id']}/approve", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # login now works
        r2 = requests.post(f"{API}/auth/login", json={"email": pending_user["email"], "password": pending_user["password"]}, timeout=15)
        assert r2.status_code == 200
        user_token = r2.json()["token"]

        # non-admin cannot access admin routes
        r3 = requests.get(f"{API}/admin/users", headers={"Authorization": f"Bearer {user_token}"}, timeout=15)
        assert r3.status_code == 403

        # non-admin cannot create geofence
        r4 = requests.post(
            f"{API}/geofences",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"name": "TEST_gf", "lat": 0, "lon": 0, "radius_m": 100},
            timeout=15,
        )
        assert r4.status_code == 403


# ---------- Protection ----------
class TestAuthProtection:
    def test_status_requires_auth(self):
        r = requests.get(f"{API}/status", timeout=15)
        assert r.status_code in (401, 403)

    def test_radios_requires_auth(self):
        r = requests.get(f"{API}/radios", timeout=15)
        assert r.status_code in (401, 403)

    def test_bad_token_rejected(self):
        r = requests.get(f"{API}/status", headers={"Authorization": "Bearer garbage"}, timeout=15)
        assert r.status_code in (401, 403)


# ---------- Status / core ----------
class TestStatus:
    def test_status(self, admin_headers):
        r = requests.get(f"{API}/status", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "listener" in data and "parsers" in data
        parsers = " ".join(data["parsers"]).lower()
        for name in ["lrrp", "hytera", "nmea", "aprs"]:
            assert name in parsers, f"missing parser: {name}"


# ---------- Inject / radios ----------
class TestInject:
    def test_inject_simulated(self, admin_headers):
        dmr_id = 3110000 + int(time.time()) % 100000
        r = requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_id, "callsign": "TEST-INJ", "lat": 12.34, "lon": 56.78, "format": "SIMULATED"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # radio should exist
        r2 = requests.get(f"{API}/radios", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        radios = r2.json()
        found = [x for x in radios if x["dmr_id"] == dmr_id]
        assert found, "injected radio not found in /radios"
        assert found[0]["callsign"] == "TEST-INJ"

        # positions endpoint returns at least the new one
        r3 = requests.get(f"{API}/radios/{dmr_id}/positions", headers=admin_headers, timeout=15)
        assert r3.status_code == 200
        positions = r3.json()
        assert len(positions) >= 1
        assert abs(positions[-1]["lat"] - 12.34) < 1e-6

        # patch callsign
        r4 = requests.patch(f"{API}/radios/{dmr_id}", headers=admin_headers, json={"callsign": "TEST-CS", "icon": "Truck", "color": "#ff00ff"}, timeout=15)
        assert r4.status_code == 200

        r5 = requests.get(f"{API}/radios", headers=admin_headers, timeout=15)
        row = [x for x in r5.json() if x["dmr_id"] == dmr_id][0]
        assert row["callsign"] == "TEST-CS"
        assert row["icon"] == "Truck"

        # delete radio (admin only)
        rd = requests.delete(f"{API}/radios/{dmr_id}", headers=admin_headers, timeout=15)
        assert rd.status_code == 200


# ---------- Raw hex parsers ----------
RAW_SAMPLES = {
    # From dmr_parsers unit signatures. Try what dmr_parsers accepts.
    # LRRP known-prefix Motorola-ish
    "LRRP":   "0d200000005a0f10ac2a0b1b26e4",  # placeholder - may or may not match
    "NMEA":   "2447505247474134383037332e35342c4e2c30313230392e30352c452c322c30322c312e302c352e352c4d2c342e372c4d2c2c2a35460d0a",
    "APRS":   "213437313732372e30304e2f303132323038302e3030452e3132322f34352f",
    "HYTERA": "7e0a01aabb00112233440000000000000000000000000000000000000000000000000000000000000000",
}


class TestRawParsers:
    def test_raw_nmea(self, admin_headers):
        # $GPRMC style ASCII
        nmea = b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n"
        r = requests.post(
            f"{API}/inject-raw",
            headers=admin_headers,
            json={"dmr_id": 999901, "callsign": "NMEA-TEST", "hex": nmea.hex()},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True, f"NMEA parse failed: {body}"

    def test_raw_invalid_hex(self, admin_headers):
        r = requests.post(
            f"{API}/inject-raw",
            headers=admin_headers,
            json={"dmr_id": 999902, "hex": "ZZZZZZ"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is False


# ---------- Geofences / alerts ----------
class TestGeofences:
    def test_crud_and_alert(self, admin_headers):
        # very large radius so any point is inside
        r = requests.post(
            f"{API}/geofences",
            headers=admin_headers,
            json={"name": "TEST_worldwide", "lat": 0.0, "lon": 0.0, "radius_m": 1_000_000, "alert_on": "both"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        gf = r.json()
        gf_id = gf.get("id") or gf.get("_id") or gf.get("geofence_id")
        assert gf_id, f"geofence id missing: {gf}"

        # list
        rl = requests.get(f"{API}/geofences", headers=admin_headers, timeout=15)
        assert rl.status_code == 200
        assert any((x.get("id") == gf_id) for x in rl.json())

        # inject inside fence -> should create alert
        dmr_id = 8110000 + int(time.time()) % 10000
        ri = requests.post(f"{API}/inject", headers=admin_headers, json={"dmr_id": dmr_id, "lat": 0.001, "lon": 0.001, "format": "SIMULATED"}, timeout=15)
        assert ri.status_code == 200
        time.sleep(0.5)

        ra = requests.get(f"{API}/alerts", headers=admin_headers, timeout=15)
        assert ra.status_code == 200
        alerts = ra.json()
        # find enter alert for our dmr_id
        matching = [a for a in alerts if a.get("dmr_id") == dmr_id and str(a.get("event", "")).upper() == "ENTER"]
        assert matching, f"no ENTER alert found for dmr_id={dmr_id}. alerts={alerts[:5]}"

        # delete geofence
        rd = requests.delete(f"{API}/geofences/{gf_id}", headers=admin_headers, timeout=15)
        assert rd.status_code == 200

        rl2 = requests.get(f"{API}/geofences", headers=admin_headers, timeout=15)
        assert not any((x.get("id") == gf_id) for x in rl2.json())

        # cleanup radio
        requests.delete(f"{API}/radios/{dmr_id}", headers=admin_headers, timeout=15)
