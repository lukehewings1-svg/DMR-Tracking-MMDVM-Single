"""Tests for v1.2 features: groups, messages, voice, emergencies, repeaters, static setup files."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://gps-radio-dashboard.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@dmrtracker.app"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------- Status voice fields ----------
class TestStatusVoice:
    def test_status_has_voice_hardware_false(self, admin_headers):
        r = requests.get(f"{API}/status", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "voice" in data
        v = data["voice"]
        assert v["ambe_hardware_available"] is False
        # reason should reference the dongle
        reason = (v.get("reason") or "").lower()
        assert "ambe" in reason or "dongle" in reason or "dv3000" in reason or "thumbdv" in reason


# ---------- Repeaters ----------
class TestRepeaters:
    def test_list_requires_auth(self):
        r = requests.get(f"{API}/repeaters", timeout=15)
        assert r.status_code in (401, 403)

    def test_list_ok_empty(self, admin_headers):
        r = requests.get(f"{API}/repeaters", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Groups CRUD ----------
class TestGroups:
    def test_seeded_defaults(self, admin_headers):
        r = requests.get(f"{API}/groups", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        groups = r.json()
        by_tg = {g["talkgroup_id"]: g for g in groups}
        for tg, name in [(91, "Medical"), (92, "Security"), (93, "Ops"), (94, "Fire")]:
            assert tg in by_tg, f"missing seed group TG{tg}"
            assert by_tg[tg]["name"] == name

    def test_create_patch_delete_group(self, admin_headers):
        name = f"TEST_Ambulance_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/groups",
            headers=admin_headers,
            json={"name": name, "talkgroup_id": 95, "color": "#ff8800", "icon": "Ambulance", "description": "TEST"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        g = r.json()
        assert g["talkgroup_id"] == 95
        gid = g["id"]

        # patch
        rp = requests.patch(
            f"{API}/groups/{gid}",
            headers=admin_headers,
            json={"description": "Patched", "color": "#123456"},
            timeout=15,
        )
        assert rp.status_code == 200
        assert rp.json()["description"] == "Patched"
        assert rp.json()["color"] == "#123456"

        # assign a radio to the group then delete group and verify unassign
        dmr_id = 4110000 + int(time.time()) % 10000
        ri = requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_id, "callsign": "TEST-GRP", "lat": 1.0, "lon": 1.0, "format": "SIMULATED"},
            timeout=15,
        )
        assert ri.status_code == 200
        rp2 = requests.patch(f"{API}/radios/{dmr_id}", headers=admin_headers, json={"group_id": gid}, timeout=15)
        assert rp2.status_code == 200

        # filter radios by group_id
        rf = requests.get(f"{API}/radios?group_id={gid}", headers=admin_headers, timeout=15)
        assert rf.status_code == 200
        assert any(x["dmr_id"] == dmr_id for x in rf.json())

        # delete group
        rd = requests.delete(f"{API}/groups/{gid}", headers=admin_headers, timeout=15)
        assert rd.status_code == 200

        # radio's group_id should be unset
        rr = requests.get(f"{API}/radios", headers=admin_headers, timeout=15)
        row = [x for x in rr.json() if x["dmr_id"] == dmr_id][0]
        assert not row.get("group_id"), f"radio still bound to deleted group: {row.get('group_id')}"

        # cleanup radio
        requests.delete(f"{API}/radios/{dmr_id}", headers=admin_headers, timeout=15)


# ---------- Auto-assign group by talkgroup ----------
class TestAutoAssign:
    def test_inject_with_talkgroup_assigns_group(self, admin_headers):
        # Find the Medical group id (TG91)
        rg = requests.get(f"{API}/groups", headers=admin_headers, timeout=15).json()
        medical = [g for g in rg if g["talkgroup_id"] == 91][0]

        # inject a packet whose talkgroup is 91. /inject payload does not carry talkgroup
        # but we can set group_id explicitly to test the metadata inheritance path OR
        # rely on the parser layer. Use record_packet via /inject with group_id=None
        # and trigger via the DMR-injection helper /inject-raw is GPS-only.
        # Simulate by patching the radio - not the same code path. Use /messages/simulate-inbound
        # will not touch radios. Best bet: create a radio then patch group and verify meta.
        # For the auto-assign path via talkgroup, use the emergency simulator which passes
        # talkgroup_id into on_emergency (no radio creation there). Skip talkgroup-driven
        # auto-assign here since /inject does not accept talkgroup_id.
        pytest.skip("/inject payload does not accept talkgroup_id; auto-assign is exercised via HBMaster ingest path (needs real UDP).")


# ---------- Messages ----------
class TestMessages:
    def test_send_to_group_and_list(self, admin_headers):
        rg = requests.get(f"{API}/groups", headers=admin_headers, timeout=15).json()
        gid = [g for g in rg if g["talkgroup_id"] == 91][0]["id"]

        text = f"TEST_grp_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/messages",
            headers=admin_headers,
            json={"text": text, "group_id": gid},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["text"] == text
        assert doc["direction"] == "out"
        assert doc["is_private"] is False
        assert "delivery_status" in doc

        # list
        rl = requests.get(f"{API}/messages", headers=admin_headers, timeout=15)
        assert rl.status_code == 200
        assert any(m["text"] == text for m in rl.json())

    def test_send_private(self, admin_headers):
        text = f"TEST_priv_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/messages",
            headers=admin_headers,
            json={"text": text, "target_dmr_id": 3110123},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["is_private"] is True
        assert doc["to_dmr_id"] == 3110123

    def test_send_missing_target(self, admin_headers):
        r = requests.post(f"{API}/messages", headers=admin_headers, json={"text": "no-target"}, timeout=15)
        assert r.status_code == 400

    def test_simulate_inbound(self, admin_headers):
        text = f"TEST_in_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/messages/simulate-inbound",
            headers=admin_headers,
            json={"from_dmr_id": 3110999, "text": text, "talkgroup_id": 91},
            timeout=15,
        )
        assert r.status_code == 200
        doc = r.json()
        assert doc["direction"] == "in"
        assert doc["text"] == text
        assert doc["talkgroup_id"] == 91


# ---------- Voice ----------
class TestVoice:
    def test_voice_status(self, admin_headers):
        r = requests.get(f"{API}/voice/status", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ambe_hardware_available"] is False
        assert d.get("reason")

    def test_voice_ptt_no_hardware(self, admin_headers):
        r = requests.post(f"{API}/voice/ptt", headers=admin_headers, json={"target_dmr_id": 3110001}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert d["reason"] == "ambe_hardware_missing"


# ---------- Emergencies ----------
class TestEmergencies:
    def test_simulate_list_clear(self, admin_headers):
        dmr_id = 5110000 + int(time.time()) % 10000
        # first create a radio so we can verify in_emergency flip
        ri = requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_id, "callsign": "TEST-EMG", "lat": 10.0, "lon": 20.0, "format": "SIMULATED"},
            timeout=15,
        )
        assert ri.status_code == 200

        # simulate emergency
        rs = requests.post(
            f"{API}/emergencies/simulate",
            headers=admin_headers,
            json={"dmr_id": dmr_id, "talkgroup_id": 91},
            timeout=15,
        )
        assert rs.status_code == 200

        # list active
        rl = requests.get(f"{API}/emergencies?status_filter=active", headers=admin_headers, timeout=15)
        assert rl.status_code == 200
        active = rl.json()
        mine = [e for e in active if e["dmr_id"] == dmr_id]
        assert mine, f"emergency not found for dmr_id={dmr_id}"
        emg_id = mine[0]["id"]
        assert mine[0]["status"] == "active"

        # radio has in_emergency=True
        rr = requests.get(f"{API}/radios", headers=admin_headers, timeout=15)
        row = [x for x in rr.json() if x["dmr_id"] == dmr_id][0]
        assert row.get("in_emergency") is True

        # clear
        rc = requests.post(f"{API}/emergencies/{emg_id}/clear", headers=admin_headers, timeout=15)
        assert rc.status_code == 200

        # radio in_emergency flipped
        rr2 = requests.get(f"{API}/radios", headers=admin_headers, timeout=15)
        row2 = [x for x in rr2.json() if x["dmr_id"] == dmr_id][0]
        assert row2.get("in_emergency") is False

        # list cleared
        rlc = requests.get(f"{API}/emergencies?status_filter=cleared", headers=admin_headers, timeout=15)
        assert rlc.status_code == 200
        assert any(e["id"] == emg_id for e in rlc.json())

        # cleanup
        requests.delete(f"{API}/radios/{dmr_id}", headers=admin_headers, timeout=15)


# ---------- Setup static files ----------
class TestSetupStatic:
    def test_setup_md_public(self):
        r = requests.get(f"{BASE_URL}/SETUP.md", timeout=15)
        assert r.status_code == 200, f"SETUP.md not reachable: {r.status_code}"
        assert len(r.text) > 100

    def test_setup_part2_public(self):
        r = requests.get(f"{BASE_URL}/SETUP_PART2.md", timeout=15)
        assert r.status_code == 200
        assert len(r.text) > 100
