"""Iteration 5 tests: Shift log timeline + CSV export + ACL."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
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


@pytest.fixture
def restricted_user(admin_headers):
    """Approved non-admin with allowed_group_ids set to first group only."""
    email = f"TEST_it5_{uuid.uuid4().hex[:6]}@example.com"
    pw = "Password!123"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": pw, "callsign": "TIT5"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_headers, timeout=15)
    rl = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    token = rl.json()["token"]

    groups = requests.get(f"{API}/groups", headers=admin_headers, timeout=15).json()
    assert len(groups) >= 1
    gid = groups[0]["id"]
    requests.post(
        f"{API}/admin/users/{uid}/groups",
        headers=admin_headers,
        json={"allowed_group_ids": [gid]},
        timeout=15,
    )
    yield {
        "headers": {"Authorization": f"Bearer {token}"},
        "id": uid,
        "email": email,
        "allowed_group_id": gid,
        "other_group_id": groups[1]["id"] if len(groups) > 1 else None,
    }
    requests.delete(f"{API}/admin/users/{uid}", headers=admin_headers, timeout=15)


def _clear_log(headers):
    requests.delete(f"{API}/shift-log", headers=headers, timeout=15)


class TestShiftLogBasics:
    def test_requires_auth(self):
        r = requests.get(f"{API}/shift-log", timeout=15)
        assert r.status_code in (401, 403)

    def test_get_returns_list(self, admin_headers):
        r = requests.get(f"{API}/shift-log", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_bad_event_type_returns_400(self, admin_headers):
        r = requests.get(
            f"{API}/shift-log?event_type=nonsense", headers=admin_headers, timeout=15
        )
        assert r.status_code == 400

    def test_delete_admin_clears(self, admin_headers):
        r = requests.delete(f"{API}/shift-log", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        rl = requests.get(f"{API}/shift-log", headers=admin_headers, timeout=15)
        assert rl.json() == []


class TestShiftLogHooks:
    def test_position_logged_from_inject(self, admin_headers):
        _clear_log(admin_headers)
        dmr = 6600000 + int(time.time()) % 800
        r = requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr, "callsign": "TEST_POS", "lat": 37.5, "lon": -122.3},
            timeout=15,
        )
        assert r.status_code == 200
        time.sleep(0.5)
        entries = requests.get(
            f"{API}/shift-log?event_type=position", headers=admin_headers, timeout=15
        ).json()
        assert any(e.get("dmr_id") == dmr for e in entries), entries
        requests.delete(f"{API}/radios/{dmr}", headers=admin_headers, timeout=15)

    def test_emergency_and_clear_logged(self, admin_headers):
        _clear_log(admin_headers)
        dmr = 6600000 + int(time.time()) % 800 + 5
        # ensure radio exists
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr, "callsign": "TEST_EMG", "lat": 1, "lon": 2},
            timeout=15,
        )
        rs = requests.post(
            f"{API}/emergencies/simulate",
            headers=admin_headers,
            json={"dmr_id": dmr},
            timeout=15,
        )
        assert rs.status_code == 200, rs.text
        emg_id = rs.json().get("id") or rs.json().get("emergency", {}).get("id")
        time.sleep(0.5)
        e = requests.get(
            f"{API}/shift-log?event_type=emergency", headers=admin_headers, timeout=15
        ).json()
        assert any(x.get("dmr_id") == dmr for x in e), e

        if emg_id:
            rc = requests.post(
                f"{API}/emergencies/{emg_id}/clear", headers=admin_headers, timeout=15
            )
            assert rc.status_code == 200
            time.sleep(0.5)
            cl = requests.get(
                f"{API}/shift-log?event_type=emergency_cleared",
                headers=admin_headers,
                timeout=15,
            ).json()
            assert any(x.get("dmr_id") == dmr for x in cl), cl
            assert any(x.get("actor") == ADMIN_EMAIL for x in cl if x.get("dmr_id") == dmr)

        requests.delete(f"{API}/radios/{dmr}", headers=admin_headers, timeout=15)

    def test_message_out_logged(self, admin_headers):
        _clear_log(admin_headers)
        groups = requests.get(f"{API}/groups", headers=admin_headers, timeout=15).json()
        assert groups
        gid = groups[0]["id"]
        tgid = groups[0].get("talkgroup_id")
        r = requests.post(
            f"{API}/messages",
            headers=admin_headers,
            json={"text": "TEST_out_msg", "group_id": gid},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        time.sleep(0.5)
        entries = requests.get(
            f"{API}/shift-log?event_type=message_out", headers=admin_headers, timeout=15
        ).json()
        assert entries
        matching = [x for x in entries if "TEST_out_msg" in (x.get("summary") or "") or x.get("actor") == ADMIN_EMAIL]
        assert matching
        # summary contains target talkgroup id
        if tgid is not None:
            assert any(f"TG {tgid}" in (x.get("summary") or "") for x in matching), matching

    def test_message_in_logged(self, admin_headers):
        _clear_log(admin_headers)
        dmr = 6700000 + int(time.time()) % 800
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr, "callsign": "TEST_IN", "lat": 1, "lon": 2},
            timeout=15,
        )
        r = requests.post(
            f"{API}/messages/simulate-inbound",
            headers=admin_headers,
            json={"from_dmr_id": dmr, "text": "hi there"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        time.sleep(0.5)
        entries = requests.get(
            f"{API}/shift-log?event_type=message_in", headers=admin_headers, timeout=15
        ).json()
        assert entries
        assert any("TEST_IN" in (x.get("summary") or "") for x in entries), entries
        requests.delete(f"{API}/radios/{dmr}", headers=admin_headers, timeout=15)

    def test_geofence_alert_logged(self, admin_headers):
        _clear_log(admin_headers)
        # Create a fence
        fence_body = {
            "name": f"TEST_fence_{uuid.uuid4().hex[:5]}",
            "lat": 40.0,
            "lon": -74.0,
            "radius_m": 5000,
            "alert_on": "enter",
        }
        rf = requests.post(f"{API}/geofences", headers=admin_headers, json=fence_body, timeout=15)
        if rf.status_code != 200:
            pytest.skip(f"geofence create not supported: {rf.status_code} {rf.text}")
        fence_id = rf.json().get("id")
        dmr = 6800000 + int(time.time()) % 800
        # inject outside first
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr, "callsign": "TEST_GEO", "lat": 50.0, "lon": -74.0},
            timeout=15,
        )
        time.sleep(0.3)
        # inject inside -> enter event
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr, "callsign": "TEST_GEO", "lat": 40.0, "lon": -74.0},
            timeout=15,
        )
        time.sleep(0.7)
        entries = requests.get(
            f"{API}/shift-log?event_type=alert", headers=admin_headers, timeout=15
        ).json()
        assert any(x.get("dmr_id") == dmr for x in entries), entries
        # cleanup
        if fence_id:
            requests.delete(f"{API}/geofences/{fence_id}", headers=admin_headers, timeout=15)
        requests.delete(f"{API}/radios/{dmr}", headers=admin_headers, timeout=15)


class TestShiftLogQuery:
    def test_limit(self, admin_headers):
        _clear_log(admin_headers)
        for i in range(7):
            requests.post(
                f"{API}/inject",
                headers=admin_headers,
                json={"dmr_id": 6900000 + i, "callsign": f"L{i}", "lat": i, "lon": i},
                timeout=15,
            )
        time.sleep(0.5)
        r = requests.get(f"{API}/shift-log?limit=5", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) <= 5
        for i in range(7):
            requests.delete(f"{API}/radios/{6900000+i}", headers=admin_headers, timeout=15)

    def test_dmr_id_filter(self, admin_headers):
        _clear_log(admin_headers)
        dmr_a = 6910001
        dmr_b = 6910002
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_a, "callsign": "A", "lat": 1, "lon": 2},
            timeout=15,
        )
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_b, "callsign": "B", "lat": 1, "lon": 2},
            timeout=15,
        )
        time.sleep(0.5)
        r = requests.get(f"{API}/shift-log?dmr_id={dmr_a}", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        entries = r.json()
        assert entries
        assert all(e.get("dmr_id") == dmr_a for e in entries)
        requests.delete(f"{API}/radios/{dmr_a}", headers=admin_headers, timeout=15)
        requests.delete(f"{API}/radios/{dmr_b}", headers=admin_headers, timeout=15)


class TestShiftLogCsv:
    def test_csv_headers_and_row(self, admin_headers):
        _clear_log(admin_headers)
        dmr = 6920000
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr, "callsign": "CSV1", "lat": 1, "lon": 2},
            timeout=15,
        )
        time.sleep(0.5)
        r = requests.get(f"{API}/shift-log/export.csv", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("Content-Type", "")
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd
        assert "filename" in cd
        body = r.text
        first_line = body.splitlines()[0]
        assert first_line == "timestamp,event_type,summary,dmr_id,callsign,group_id,channel_id,actor,subject"
        assert len(body.splitlines()) >= 2  # header + at least one row
        requests.delete(f"{API}/radios/{dmr}", headers=admin_headers, timeout=15)


class TestShiftLogAcl:
    def test_non_admin_cannot_clear(self, restricted_user):
        r = requests.delete(f"{API}/shift-log", headers=restricted_user["headers"], timeout=15)
        assert r.status_code == 403

    def test_restricted_user_only_sees_own_group_entries(self, admin_headers, restricted_user):
        _clear_log(admin_headers)
        if not restricted_user.get("other_group_id"):
            pytest.skip("Need at least 2 groups")
        ok_gid = restricted_user["allowed_group_id"]
        deny_gid = restricted_user["other_group_id"]
        dmr_ok = 6930001
        dmr_no = 6930002
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_ok, "callsign": "OK", "lat": 1, "lon": 2, "group_id": ok_gid},
            timeout=15,
        )
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_no, "callsign": "NO", "lat": 1, "lon": 2, "group_id": deny_gid},
            timeout=15,
        )
        time.sleep(0.6)
        r = requests.get(
            f"{API}/shift-log?limit=500",
            headers=restricted_user["headers"],
            timeout=15,
        )
        assert r.status_code == 200
        entries = r.json()
        for e in entries:
            # Allowed: matching group or None (system-wide)
            assert e.get("group_id") in (ok_gid, None), e
        # Admin sees both
        radm = requests.get(f"{API}/shift-log?limit=500", headers=admin_headers, timeout=15).json()
        gids = {x.get("group_id") for x in radm}
        assert ok_gid in gids and deny_gid in gids
        requests.delete(f"{API}/radios/{dmr_ok}", headers=admin_headers, timeout=15)
        requests.delete(f"{API}/radios/{dmr_no}", headers=admin_headers, timeout=15)
