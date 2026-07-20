"""Iteration 4 tests: multi-channel model, RepeaterConfig, Dispatcher ACL."""
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


@pytest.fixture(scope="module")
def user_ctx(admin_headers):
    """Create + approve a non-admin user, return auth headers + user id + token."""
    email = f"TEST_it4_{uuid.uuid4().hex[:6]}@example.com"
    pw = "Password!123"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": pw, "callsign": "TIT4"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    ra = requests.post(f"{API}/admin/users/{uid}/approve", headers=admin_headers, timeout=15)
    assert ra.status_code == 200
    rl = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert rl.status_code == 200
    return {
        "headers": {"Authorization": f"Bearer {rl.json()['token']}"},
        "id": uid,
        "email": email,
    }


# ---------- Channels model with id ----------
class TestChannelsModel:
    def test_get_returns_id_field(self, admin_headers):
        r = requests.get(f"{API}/channels", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        chans = r.json()
        ids = [c["id"] for c in chans]
        assert "slot-1" in ids
        assert "slot-2" in ids
        for c in chans:
            assert isinstance(c["id"], str)
            assert "slot" not in c  # legacy numeric slot removed

    def test_requires_auth(self):
        r = requests.get(f"{API}/channels", timeout=15)
        assert r.status_code in (401, 403)

    def test_create_channel_admin(self, admin_headers):
        name = f"TEST_ch_{uuid.uuid4().hex[:5]}"
        r = requests.post(
            f"{API}/channels",
            headers=admin_headers,
            json={"name": name, "color": "#c084fc", "description": "test"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        ch = r.json()
        assert ch["name"] == name
        assert ch["color"] == "#c084fc"
        assert ch["id"] not in ("slot-1", "slot-2")
        # verify visible in list
        rl = requests.get(f"{API}/channels", headers=admin_headers, timeout=15)
        assert any(c["id"] == ch["id"] for c in rl.json())
        # cleanup
        requests.delete(f"{API}/channels/{ch['id']}", headers=admin_headers, timeout=15)

    def test_create_channel_non_admin_forbidden(self, user_ctx):
        r = requests.post(
            f"{API}/channels",
            headers=user_ctx["headers"],
            json={"name": "nope"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_patch_legacy_id_slot_1(self, admin_headers):
        # both "slot-1" string id AND legacy "1" should work
        r1 = requests.patch(
            f"{API}/channels/slot-1",
            headers=admin_headers,
            json={"name": "Channel 1"},
            timeout=15,
        )
        assert r1.status_code == 200
        r2 = requests.patch(
            f"{API}/channels/1",
            headers=admin_headers,
            json={"description": ""},
            timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json()["id"] == "slot-1"

    def test_patch_uuid_channel(self, admin_headers):
        cr = requests.post(
            f"{API}/channels",
            headers=admin_headers,
            json={"name": f"TEST_p_{uuid.uuid4().hex[:5]}"},
            timeout=15,
        )
        cid = cr.json()["id"]
        r = requests.patch(
            f"{API}/channels/{cid}",
            headers=admin_headers,
            json={"name": "Renamed"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"
        requests.delete(f"{API}/channels/{cid}", headers=admin_headers, timeout=15)

    def test_cannot_delete_builtins(self, admin_headers):
        r = requests.delete(f"{API}/channels/slot-1", headers=admin_headers, timeout=15)
        assert r.status_code == 400
        r2 = requests.delete(f"{API}/channels/slot-2", headers=admin_headers, timeout=15)
        assert r2.status_code == 400

    def test_delete_uuid_channel_unbinds_repeater_config(self, admin_headers):
        # create channel
        cr = requests.post(
            f"{API}/channels",
            headers=admin_headers,
            json={"name": f"TEST_del_{uuid.uuid4().hex[:5]}"},
            timeout=15,
        )
        cid = cr.json()["id"]
        # bind to a repeater config
        rid = 9990000 + int(time.time()) % 1000
        ru = requests.put(
            f"{API}/repeater-configs/{rid}",
            headers=admin_headers,
            json={"name": "TEST_MMDVM", "slot1_channel_id": cid, "slot2_channel_id": "slot-2"},
            timeout=15,
        )
        assert ru.status_code == 200
        assert ru.json()["slot1_channel_id"] == cid
        # delete channel -> should unbind
        rd = requests.delete(f"{API}/channels/{cid}", headers=admin_headers, timeout=15)
        assert rd.status_code == 200
        rc = requests.get(f"{API}/repeater-configs", headers=admin_headers, timeout=15)
        entry = [x for x in rc.json() if x["repeater_id"] == rid][0]
        assert entry["slot1_channel_id"] == "slot-1"
        # cleanup
        requests.delete(f"{API}/repeater-configs/{rid}", headers=admin_headers, timeout=15)


# ---------- Repeater configs ----------
class TestRepeaterConfigs:
    def test_list_requires_auth(self):
        r = requests.get(f"{API}/repeater-configs", timeout=15)
        assert r.status_code in (401, 403)

    def test_upsert_admin_only(self, user_ctx):
        r = requests.put(
            f"{API}/repeater-configs/1234567",
            headers=user_ctx["headers"],
            json={"name": "x"},
            timeout=15,
        )
        assert r.status_code == 403

    def test_upsert_and_persist(self, admin_headers):
        rid = 9880000 + int(time.time()) % 1000
        r = requests.put(
            f"{API}/repeater-configs/{rid}",
            headers=admin_headers,
            json={
                "name": "TEST_NorCal",
                "notes": "primary",
                "slot1_channel_id": "slot-1",
                "slot2_channel_id": "slot-2",
            },
            timeout=15,
        )
        assert r.status_code == 200
        doc = r.json()
        assert doc["repeater_id"] == rid
        assert doc["name"] == "TEST_NorCal"
        # verify GET
        rl = requests.get(f"{API}/repeater-configs", headers=admin_headers, timeout=15)
        assert any(x["repeater_id"] == rid for x in rl.json())
        # delete
        rd = requests.delete(f"{API}/repeater-configs/{rid}", headers=admin_headers, timeout=15)
        assert rd.status_code == 200
        rl2 = requests.get(f"{API}/repeater-configs", headers=admin_headers, timeout=15)
        assert not any(x["repeater_id"] == rid for x in rl2.json())


# ---------- User ACL ----------
class TestDispatcherACL:
    def test_me_returns_allowed_group_ids(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert "allowed_group_ids" in r.json()
        assert isinstance(r.json()["allowed_group_ids"], list)

    def test_admin_can_set_user_groups(self, admin_headers, user_ctx):
        # pick any 1 group
        groups = requests.get(f"{API}/groups", headers=admin_headers, timeout=15).json()
        assert groups
        gid = groups[0]["id"]
        r = requests.post(
            f"{API}/admin/users/{user_ctx['id']}/groups",
            headers=admin_headers,
            json={"allowed_group_ids": [gid]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["allowed_group_ids"] == [gid]

    def test_non_admin_cannot_set_groups(self, user_ctx):
        r = requests.post(
            f"{API}/admin/users/{user_ctx['id']}/groups",
            headers=user_ctx["headers"],
            json={"allowed_group_ids": []},
            timeout=15,
        )
        assert r.status_code == 403

    def test_acl_filters_radios(self, admin_headers, user_ctx):
        groups = requests.get(f"{API}/groups", headers=admin_headers, timeout=15).json()
        assert len(groups) >= 2
        g_allowed = groups[0]
        g_denied = groups[1]

        # Inject a radio in each group
        dmr_ok = 6500000 + int(time.time()) % 900
        dmr_no = dmr_ok + 1
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_ok, "callsign": "TEST_OK", "lat": 1, "lon": 2, "group_id": g_allowed["id"]},
            timeout=15,
        )
        requests.post(
            f"{API}/inject",
            headers=admin_headers,
            json={"dmr_id": dmr_no, "callsign": "TEST_NO", "lat": 1, "lon": 2, "group_id": g_denied["id"]},
            timeout=15,
        )

        # Give user access only to g_allowed
        requests.post(
            f"{API}/admin/users/{user_ctx['id']}/groups",
            headers=admin_headers,
            json={"allowed_group_ids": [g_allowed["id"]]},
            timeout=15,
        )
        # login again to refresh token (not required since ACL is looked up per request)
        radios = requests.get(f"{API}/radios", headers=user_ctx["headers"], timeout=15).json()
        ids = [r["dmr_id"] for r in radios]
        assert dmr_ok in ids
        assert dmr_no not in ids
        # admin still sees both
        radios_admin = requests.get(f"{API}/radios", headers=admin_headers, timeout=15).json()
        ids_a = [r["dmr_id"] for r in radios_admin]
        assert dmr_ok in ids_a and dmr_no in ids_a

        # cleanup
        requests.delete(f"{API}/radios/{dmr_ok}", headers=admin_headers, timeout=15)
        requests.delete(f"{API}/radios/{dmr_no}", headers=admin_headers, timeout=15)

    def test_acl_message_send(self, admin_headers, user_ctx):
        groups = requests.get(f"{API}/groups", headers=admin_headers, timeout=15).json()
        g_ok = groups[0]
        g_no = groups[1]
        # Ensure ACL set to only g_ok
        requests.post(
            f"{API}/admin/users/{user_ctx['id']}/groups",
            headers=admin_headers,
            json={"allowed_group_ids": [g_ok["id"]]},
            timeout=15,
        )
        # denied group -> 403
        r_no = requests.post(
            f"{API}/messages",
            headers=user_ctx["headers"],
            json={"text": "TEST_denied", "group_id": g_no["id"]},
            timeout=15,
        )
        assert r_no.status_code == 403
        # allowed group -> success
        r_ok = requests.post(
            f"{API}/messages",
            headers=user_ctx["headers"],
            json={"text": "TEST_allowed", "group_id": g_ok["id"]},
            timeout=15,
        )
        assert r_ok.status_code == 200, r_ok.text

        # reset ACL to empty so subsequent tests unaffected
        requests.post(
            f"{API}/admin/users/{user_ctx['id']}/groups",
            headers=admin_headers,
            json={"allowed_group_ids": []},
            timeout=15,
        )


# ---------- Voice relay code inspection (no MMDVMs in preview) ----------
class TestVoiceRelayCodePath:
    def test_dmr_ingest_uses_channel_router(self):
        src = open("/app/backend/dmr_ingest.py").read()
        assert "channel_router" in src
        assert "channel_for_slot" in src
        assert "slot_for_channel" in src
        # Slot bit rewrite path present
        assert "new_bits" in src or "0x80" in src
