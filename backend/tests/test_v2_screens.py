"""Regression tests for v2 multi-screen split: crew field, inject, emergencies simulate/clear, non-admin ACL."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@dmrtracker.app", "password": "admin123"}
TEST_DMR = 2359901


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _radio(H, dmr):
    return next((r for r in requests.get(f"{API}/radios", headers=H, timeout=15).json() if r["dmr_id"] == dmr), None)


# --- Seeded data sanity ---
def test_seeded_radios_present(H):
    radios = requests.get(f"{API}/radios", headers=H, timeout=15).json()
    ids = {r["dmr_id"] for r in radios}
    assert {2350001, 2350002, 2350003} <= ids
    medic = next(r for r in radios if r["dmr_id"] == 2350001)
    assert medic.get("crew")


# --- Crew field on radios ---
class TestCrew:
    def test_inject_patch_crew_and_clear(self, H):
        try:
            r = requests.post(f"{API}/inject", headers=H, json={"dmr_id": TEST_DMR, "callsign": "TEST_CREW", "lat": 51.51, "lon": -0.1}, timeout=15)
            assert r.status_code == 200 and r.json()["ok"]
            rad = _radio(H, TEST_DMR)
            assert rad and rad["callsign"] == "TEST_CREW" and abs(rad["last_lat"] - 51.51) < 1e-6
            r = requests.patch(f"{API}/radios/{TEST_DMR}", headers=H, json={"crew": "Alice\nBob"}, timeout=15)
            assert r.status_code == 200
            assert _radio(H, TEST_DMR)["crew"] == "Alice\nBob"
            # patching other field leaves crew intact
            requests.patch(f"{API}/radios/{TEST_DMR}", headers=H, json={"notes": "n1"}, timeout=15)
            rad = _radio(H, TEST_DMR)
            assert rad["crew"] == "Alice\nBob" and rad["notes"] == "n1"
            # clear -> null
            r = requests.patch(f"{API}/radios/{TEST_DMR}", headers=H, json={"crew": None}, timeout=15)
            assert r.status_code == 200
            assert _radio(H, TEST_DMR).get("crew") is None
        finally:
            requests.delete(f"{API}/radios/{TEST_DMR}", headers=H, timeout=15)
        assert _radio(H, TEST_DMR) is None

    def test_crew_max_length(self, H):
        r = requests.patch(f"{API}/radios/{TEST_DMR + 1}", headers=H, json={"crew": "x" * 501}, timeout=15)
        assert r.status_code == 422


# --- Emergencies ---
class TestEmergency:
    def test_simulate_and_clear(self, H):
        dmr = TEST_DMR + 2
        try:
            requests.post(f"{API}/inject", headers=H, json={"dmr_id": dmr, "callsign": "TEST_EMG", "lat": 51.52, "lon": -0.11}, timeout=15)
            r = requests.post(f"{API}/emergencies/simulate", headers=H, json={"dmr_id": dmr}, timeout=15)
            assert r.status_code == 200
            em = [e for e in requests.get(f"{API}/emergencies", headers=H, timeout=15).json() if e["dmr_id"] == dmr]
            assert len(em) == 1 and em[0]["callsign"] == "TEST_EMG" and em[0]["status"] == "active"
            assert _radio(H, dmr)["in_emergency"] is True
            r = requests.post(f"{API}/emergencies/{em[0]['id']}/clear", headers=H, timeout=15)
            assert r.status_code == 200
            assert not any(e["dmr_id"] == dmr for e in requests.get(f"{API}/emergencies", headers=H, timeout=15).json())
            assert _radio(H, dmr)["in_emergency"] is False
            # (v15: seed no longer has an active MEDIC-1 emergency, so no assertion on it)
        finally:
            requests.delete(f"{API}/radios/{dmr}", headers=H, timeout=15)

    def test_clear_unknown_404(self, H):
        assert requests.post(f"{API}/emergencies/nope/clear", headers=H, timeout=15).status_code == 404


# --- Non-admin approved user ACL ---
class TestNonAdmin:
    def test_register_approve_acl(self, H):
        email = f"test_user_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "testpass123", "name": "TEST_user"}, timeout=15)
        assert r.status_code in (200, 201), r.text
        users = requests.get(f"{API}/admin/users", headers=H, timeout=15).json()
        uid = next(u["id"] for u in users if u["email"] == email)
        try:
            assert requests.post(f"{API}/admin/users/{uid}/approve", headers=H, timeout=15).status_code == 200
            lr = requests.post(f"{API}/auth/login", json={"email": email, "password": "testpass123"}, timeout=15)
            assert lr.status_code == 200 and lr.json()["user"]["role"] == "user"
            UH = {"Authorization": f"Bearer {lr.json()['token']}"}
            assert requests.get(f"{API}/radios", headers=UH, timeout=15).status_code == 200
            assert requests.get(f"{API}/admin/users", headers=UH, timeout=15).status_code == 403
            assert requests.delete(f"{API}/radios", headers=UH, timeout=15).status_code == 403
            assert requests.post(f"{API}/emergencies/x/clear", headers=UH, timeout=15).status_code == 403
        finally:
            assert requests.delete(f"{API}/admin/users/{uid}", headers=H, timeout=15).status_code in (200, 204)
