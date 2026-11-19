"""v15: radio group assignment (board filter), emergency clean-up on delete, simulate 404 for unknown radio, admin self-update endpoints."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@dmrtracker.app", "password": "admin123"}
T = 2359950  # TEST radio ids range 2359950..2359959


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def UH(H):
    """Approved non-admin TEST_ user; deleted at teardown."""
    email = f"test_v15_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "testpass123", "name": "TEST_v15"}, timeout=15)
    assert r.status_code in (200, 201), r.text
    uid = next(u["id"] for u in requests.get(f"{API}/admin/users", headers=H, timeout=15).json() if u["email"] == email)
    assert requests.post(f"{API}/admin/users/{uid}/approve", headers=H, timeout=15).status_code == 200
    tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "testpass123"}, timeout=15).json()["token"]
    yield {"Authorization": f"Bearer {tok}"}
    requests.delete(f"{API}/admin/users/{uid}", headers=H, timeout=15)


def _radio(H, dmr):
    return next((r for r in requests.get(f"{API}/radios", headers=H, timeout=15).json() if r["dmr_id"] == dmr), None)


def _active(H, dmr):
    return [e for e in requests.get(f"{API}/emergencies", headers=H, timeout=15).json() if e["dmr_id"] == dmr]


# --- Group assignment used by the board talkgroup filter ---
def test_patch_group_id_and_unassign(H):
    groups = requests.get(f"{API}/groups", headers=H, timeout=15).json()
    gid = groups[0]["id"]
    try:
        requests.post(f"{API}/inject", headers=H, json={"dmr_id": T, "callsign": "TEST_GRP", "lat": 51.51, "lon": -0.1}, timeout=15)
        assert requests.patch(f"{API}/radios/{T}", headers=H, json={"group_id": gid}, timeout=15).status_code == 200
        assert _radio(H, T)["group_id"] == gid
        filtered = requests.get(f"{API}/radios", headers=H, params={"group_id": gid}, timeout=15).json()
        assert any(r["dmr_id"] == T for r in filtered)
        assert requests.patch(f"{API}/radios/{T}", headers=H, json={"group_id": None}, timeout=15).status_code == 200
        assert _radio(H, T).get("group_id") is None
    finally:
        requests.delete(f"{API}/radios/{T}", headers=H, timeout=15)


# --- Simulate emergency: unknown radio -> 404 & no ghost; known -> works ---
def test_simulate_unknown_radio_404_no_ghost(H):
    ghost = T + 9
    requests.delete(f"{API}/radios/{ghost}", headers=H, timeout=15)
    r = requests.post(f"{API}/emergencies/simulate", headers=H, json={"dmr_id": ghost}, timeout=15)
    assert r.status_code == 404
    assert "detail" in r.json()
    assert _radio(H, ghost) is None
    assert _active(H, ghost) == []


def test_simulate_known_then_delete_radio_clears_emergency(H):
    dmr = T + 1
    try:
        requests.post(f"{API}/inject", headers=H, json={"dmr_id": dmr, "callsign": "TEST_EMGDEL", "lat": 51.52, "lon": -0.11}, timeout=15)
        r = requests.post(f"{API}/emergencies/simulate", headers=H, json={"dmr_id": dmr}, timeout=15)
        assert r.status_code == 200 and r.json()["ok"]
        em = _active(H, dmr)
        assert len(em) == 1 and em[0]["status"] == "active"
        assert _radio(H, dmr)["in_emergency"] is True
        assert requests.delete(f"{API}/radios/{dmr}", headers=H, timeout=15).status_code == 200
        assert _radio(H, dmr) is None
        assert _active(H, dmr) == []
        hist = requests.get(f"{API}/emergencies", headers=H, params={"status_filter": "cleared"}, timeout=15).json()
        assert any(e["id"] == em[0]["id"] and e.get("cleared_at") for e in hist)
    finally:
        requests.delete(f"{API}/radios/{dmr}", headers=H, timeout=15)


def test_delete_radio_does_not_clear_other_emergencies(H):
    a, b = T + 2, T + 3
    try:
        for d in (a, b):
            requests.post(f"{API}/inject", headers=H, json={"dmr_id": d, "callsign": f"TEST_E{d}", "lat": 51.5, "lon": -0.1}, timeout=15)
            requests.post(f"{API}/emergencies/simulate", headers=H, json={"dmr_id": d}, timeout=15)
        requests.delete(f"{API}/radios/{a}", headers=H, timeout=15)
        assert _active(H, a) == []
        assert len(_active(H, b)) == 1
    finally:
        for d in (a, b):
            for e in _active(H, d):
                requests.post(f"{API}/emergencies/{e['id']}/clear", headers=H, timeout=15)
            requests.delete(f"{API}/radios/{d}", headers=H, timeout=15)


def test_delete_radio_requires_admin(H, UH):
    assert requests.delete(f"{API}/radios/{T + 4}", headers=UH, timeout=15).status_code == 403
    assert requests.delete(f"{API}/radios", headers=UH, timeout=15).status_code == 403


# --- Self-update endpoints ---
class TestUpdate:
    def test_status_admin_no_remote(self, H):
        r = requests.get(f"{API}/admin/update/status", headers=H, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["available"] is False
        assert isinstance(d["reason"], str) and "remote" in d["reason"].lower()

    def test_non_admin_forbidden(self, UH):
        assert requests.get(f"{API}/admin/update/status", headers=UH, timeout=15).status_code == 403
        assert requests.post(f"{API}/admin/update/apply", headers=UH, timeout=15).status_code == 403
        assert requests.get(f"{API}/admin/update/job", headers=UH, timeout=15).status_code == 403

    def test_unauthenticated_rejected(self):
        assert requests.get(f"{API}/admin/update/status", timeout=15).status_code in (401, 403)

    def test_apply_fails_cleanly_without_remote(self, H):
        r = requests.post(f"{API}/admin/update/apply", headers=H, timeout=15)
        assert r.status_code == 200
        assert r.json()["state"] in ("running", "failed")
        job = None
        for _ in range(30):
            job = requests.get(f"{API}/admin/update/job", headers=H, timeout=15).json()
            if job["state"] != "running":
                break
            time.sleep(1)
        assert job["state"] == "failed", job
        assert any("Update failed" in line for line in job["log"])
        # server still alive, not restarted
        assert requests.get(f"{API}/admin/update/status", headers=H, timeout=60).status_code == 200
