"""Tests for the unified-channel (timeslot) feature."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://gps-radio-dashboard.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@dmrtracker.app"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def user_headers(admin_headers):
    """Approved non-admin user for 403 checks."""
    email = f"TEST_chan_{uuid.uuid4().hex[:6]}@example.com"
    pw = "Password!123"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": pw, "callsign": "TCHAN"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    ra = requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_headers, timeout=15)
    assert ra.status_code == 200
    rl = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert rl.status_code == 200
    return {"Authorization": f"Bearer {rl.json()['token']}", "_id": uid}


# ---------- GET /api/channels ----------
class TestChannelsList:
    def test_requires_auth(self):
        r = requests.get(f"{API}/channels", timeout=15)
        assert r.status_code in (401, 403)

    def test_list_returns_two(self, admin_headers):
        r = requests.get(f"{API}/channels", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        ch = r.json()
        assert isinstance(ch, list)
        assert len(ch) == 2
        slots = sorted([c["slot"] for c in ch])
        assert slots == [1, 2]
        for c in ch:
            assert "name" in c and c["name"]
            assert "color" in c
            assert "description" in c
            assert "created_at" in c
            assert "_id" not in c


# ---------- PATCH /api/channels/{slot} ----------
class TestChannelUpdate:
    def test_admin_rename(self, admin_headers):
        # Rename slot 1
        new_name = f"TEST_Ops_{uuid.uuid4().hex[:5]}"
        r = requests.patch(
            f"{API}/channels/1",
            headers=admin_headers,
            json={"name": new_name, "description": "Primary net"},
            timeout=15,
        )
        assert r.status_code == 200
        ch = r.json()
        assert ch["name"] == new_name
        assert ch["description"] == "Primary net"

        # Verify persistence via GET
        rl = requests.get(f"{API}/channels", headers=admin_headers, timeout=15)
        assert rl.status_code == 200
        one = [c for c in rl.json() if c["slot"] == 1][0]
        assert one["name"] == new_name
        assert one["description"] == "Primary net"

        # restore default-ish
        requests.patch(
            f"{API}/channels/1",
            headers=admin_headers,
            json={"name": "Channel 1", "description": ""},
            timeout=15,
        )

    def test_non_admin_forbidden(self, user_headers):
        h = {"Authorization": user_headers["Authorization"]}
        r = requests.patch(f"{API}/channels/1", headers=h, json={"name": "Nope"}, timeout=15)
        assert r.status_code == 403

    def test_invalid_slot(self, admin_headers):
        r = requests.patch(
            f"{API}/channels/9", headers=admin_headers, json={"name": "X"}, timeout=15
        )
        assert r.status_code == 400


# ---------- POST /api/inject with channel + /api/radios?channel filter ----------
class TestInjectChannel:
    def test_inject_and_filter(self, admin_headers):
        dmr_a = 6210000 + int(time.time()) % 1000
        dmr_b = dmr_a + 1

        # Inject A on CH1
        ra = requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={
                "dmr_id": dmr_a,
                "callsign": "TEST-CH1",
                "lat": 10.0,
                "lon": 20.0,
                "format": "SIMULATED",
                "channel": 1,
            },
            timeout=15,
        )
        assert ra.status_code == 200

        # Inject B on CH2
        rb = requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={
                "dmr_id": dmr_b,
                "callsign": "TEST-CH2",
                "lat": 11.0,
                "lon": 21.0,
                "format": "SIMULATED",
                "channel": 2,
            },
            timeout=15,
        )
        assert rb.status_code == 200

        # radios list without filter has both, with last_channel populated
        rall = requests.get(f"{API}/radios", headers=admin_headers, timeout=15)
        assert rall.status_code == 200
        radios = rall.json()
        a = [x for x in radios if x["dmr_id"] == dmr_a][0]
        b = [x for x in radios if x["dmr_id"] == dmr_b][0]
        assert a["last_channel"] == 1
        assert b["last_channel"] == 2

        # ?channel=1 returns only ch1
        r1 = requests.get(f"{API}/radios?channel=1", headers=admin_headers, timeout=15)
        assert r1.status_code == 200
        ids1 = [x["dmr_id"] for x in r1.json()]
        assert dmr_a in ids1
        assert dmr_b not in ids1
        # all rows in filter must be channel 1
        for row in r1.json():
            assert row.get("last_channel") == 1

        # ?channel=2 returns only ch2
        r2 = requests.get(f"{API}/radios?channel=2", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        ids2 = [x["dmr_id"] for x in r2.json()]
        assert dmr_b in ids2
        assert dmr_a not in ids2
        for row in r2.json():
            assert row.get("last_channel") == 2

        # re-inject radio A on channel 2 -> last_channel flips
        r3 = requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={
                "dmr_id": dmr_a,
                "callsign": "TEST-CH1",
                "lat": 10.1,
                "lon": 20.1,
                "format": "SIMULATED",
                "channel": 2,
            },
            timeout=15,
        )
        assert r3.status_code == 200
        rall2 = requests.get(f"{API}/radios", headers=admin_headers, timeout=15)
        a2 = [x for x in rall2.json() if x["dmr_id"] == dmr_a][0]
        assert a2["last_channel"] == 2

        # positions should carry the channel field
        rp = requests.get(
            f"{API}/radios/{dmr_a}/positions", headers=admin_headers, timeout=15
        )
        assert rp.status_code == 200
        positions = rp.json()
        assert positions, "no positions returned"
        # at least one recent position should have channel field
        assert any("channel" in p for p in positions), positions[-1]

        # cleanup
        requests.delete(f"{API}/radios/{dmr_a}", headers=admin_headers, timeout=15)
        requests.delete(f"{API}/radios/{dmr_b}", headers=admin_headers, timeout=15)


# ---------- Listener stats ----------
class TestListenerStats:
    def test_voice_relayed_counter_present(self, admin_headers):
        r = requests.get(f"{API}/status", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        listener = r.json().get("listener") or {}
        # If HB master bound (running=True) there should be stats with voice_relayed
        if listener.get("running") and listener.get("stats"):
            stats = listener["stats"]
            assert "voice_relayed" in stats
            # No real MMDVMs in preview -> counter stays at 0
            assert stats["voice_relayed"] == 0
