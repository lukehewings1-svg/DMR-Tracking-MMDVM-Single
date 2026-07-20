"""Multi-tenant edition backend tests.

Covers:
- super_admin CRUD on /api/orgs + bootstrap-admin
- org isolation of radios/groups/messages/geofences
- org-link propose -> approve -> revoke flow with cross-org visibility
- RBAC on user (regular) vs admin vs super_admin for POST/PATCH/DELETE
- Emergency ack toggle behavior
- Cross-org dispatch guard
- Shift-log fan-out
- Regression: existing single-org endpoints still work for super_admin
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
# Fallback: read from frontend/.env
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

SUPER_EMAIL = "admin@dmrtracker.app"
SUPER_PW = "admin123"


def _login(session, email, password):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    return r


@pytest.fixture(scope="session")
def super_token():
    s = requests.Session()
    r = _login(s, SUPER_EMAIL, SUPER_PW)
    assert r.status_code == 200, f"super login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def super_client(super_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {super_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def default_org_id(super_client):
    orgs = super_client.get(f"{BASE_URL}/api/orgs").json()
    d = next((o for o in orgs if o.get("slug") == "default"), None)
    assert d, "Default org not found"
    return d["id"]


# Unique test-org names so we don't collide across runs
_RUN_ID = uuid.uuid4().hex[:6]


@pytest.fixture(scope="session")
def org_a(super_client):
    r = super_client.post(f"{BASE_URL}/api/orgs", json={"name": f"TEST_OrgA_{_RUN_ID}"})
    assert r.status_code == 200, r.text
    yield r.json()
    super_client.delete(f"{BASE_URL}/api/orgs/{r.json()['id']}")


@pytest.fixture(scope="session")
def org_b(super_client):
    r = super_client.post(f"{BASE_URL}/api/orgs", json={"name": f"TEST_OrgB_{_RUN_ID}", "user_can_ack_emergency": False})
    assert r.status_code == 200, r.text
    yield r.json()
    super_client.delete(f"{BASE_URL}/api/orgs/{r.json()['id']}")


@pytest.fixture(scope="session")
def admin_a(super_client, org_a):
    email = f"admina_{_RUN_ID}@test.app"
    r = super_client.post(
        f"{BASE_URL}/api/orgs/{org_a['id']}/bootstrap-admin",
        json={"email": email, "password": "pw123456"},
    )
    assert r.status_code == 200, r.text
    s = requests.Session()
    lr = _login(s, email, "pw123456")
    assert lr.status_code == 200, lr.text
    tok = lr.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return {"session": s, "email": email, "user": lr.json()["user"]}


@pytest.fixture(scope="session")
def admin_b(super_client, org_b):
    email = f"adminb_{_RUN_ID}@test.app"
    r = super_client.post(
        f"{BASE_URL}/api/orgs/{org_b['id']}/bootstrap-admin",
        json={"email": email, "password": "pw123456"},
    )
    assert r.status_code == 200, r.text
    s = requests.Session()
    lr = _login(s, email, "pw123456")
    assert lr.status_code == 200
    tok = lr.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return {"session": s, "email": email, "user": lr.json()["user"]}


@pytest.fixture(scope="session")
def user_in_b(super_client, admin_b, org_b):
    # Register a regular user then admin_b approves and demotes to 'user'
    email = f"userb_{_RUN_ID}@test.app"
    reg = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "pw123456"})
    assert reg.status_code == 200, reg.text
    uid = reg.json()["id"]
    # Reassign to org_b then approve
    r1 = super_client.post(f"{BASE_URL}/api/admin/users/{uid}/org", json={"org_id": org_b["id"]})
    assert r1.status_code == 200, r1.text
    r2 = admin_b["session"].post(f"{BASE_URL}/api/admin/users/{uid}/approve")
    assert r2.status_code == 200, r2.text
    r3 = admin_b["session"].post(f"{BASE_URL}/api/admin/users/{uid}/role", json={"role": "user"})
    assert r3.status_code == 200, r3.text
    s = requests.Session()
    lr = _login(s, email, "pw123456")
    assert lr.status_code == 200, lr.text
    tok = lr.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return {"session": s, "email": email, "user": lr.json()["user"], "uid": uid}


# --------------------------------------------------------------------------- #
# 1) Super admin org CRUD + bootstrap-admin
# --------------------------------------------------------------------------- #
class TestOrgCrud:
    def test_list_orgs_as_super(self, super_client):
        r = super_client.get(f"{BASE_URL}/api/orgs")
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) >= 1

    def test_patch_org(self, super_client, org_a):
        r = super_client.patch(
            f"{BASE_URL}/api/orgs/{org_a['id']}", json={"user_can_ack_emergency": False}
        )
        assert r.status_code == 200
        assert r.json()["user_can_ack_emergency"] is False
        # revert
        super_client.patch(f"{BASE_URL}/api/orgs/{org_a['id']}", json={"user_can_ack_emergency": True})

    def test_cannot_delete_default(self, super_client, default_org_id):
        r = super_client.delete(f"{BASE_URL}/api/orgs/{default_org_id}")
        assert r.status_code == 400

    def test_bootstrap_admin_creates_user(self, admin_a, org_a):
        assert admin_a["user"]["org_id"] == org_a["id"]
        assert admin_a["user"]["role"] == "admin"


# --------------------------------------------------------------------------- #
# 2) Org isolation
# --------------------------------------------------------------------------- #
class TestOrgIsolation:
    def test_admin_a_sees_only_its_own_groups(self, admin_a, org_a):
        # create a group in A
        r = admin_a["session"].post(
            f"{BASE_URL}/api/groups",
            json={"name": f"TEST_GA_{_RUN_ID}", "talkgroup_id": 90001},
        )
        assert r.status_code == 200
        # list
        groups = admin_a["session"].get(f"{BASE_URL}/api/groups").json()
        org_ids = {g.get("org_id") for g in groups}
        assert org_ids <= {org_a["id"]}, f"admin A saw other orgs: {org_ids}"

    def test_admin_b_does_not_see_admin_a_group(self, admin_a, admin_b, org_a):
        # ensure A has a group
        admin_a["session"].post(
            f"{BASE_URL}/api/groups",
            json={"name": f"TEST_GA2_{_RUN_ID}", "talkgroup_id": 90002},
        )
        groups_b = admin_b["session"].get(f"{BASE_URL}/api/groups").json()
        for g in groups_b:
            assert g.get("org_id") != org_a["id"]

    def test_admin_a_cannot_see_radios_of_b(self, admin_a, admin_b, super_client, org_b):
        # inject a radio into org_b using super_admin's session but tagged for org_b
        # simplest: admin_b injects (their session is org_b)
        pkt = admin_b["session"].post(
            f"{BASE_URL}/api/inject",
            json={"dmr_id": 8880000 + int(_RUN_ID, 16) % 1000, "lat": 10, "lon": 10},
        )
        assert pkt.status_code == 200
        radios_a = admin_a["session"].get(f"{BASE_URL}/api/radios").json()
        for r in radios_a:
            assert r.get("org_id") != org_b["id"]

    def test_super_sees_all(self, super_client, org_a, org_b):
        radios = super_client.get(f"{BASE_URL}/api/radios").json()
        # Not asserting non-empty here since it depends on state, just that call works
        assert isinstance(radios, list)


# --------------------------------------------------------------------------- #
# 3) Org linking
# --------------------------------------------------------------------------- #
class TestOrgLinking:
    def test_full_link_flow(self, admin_a, admin_b, org_a, org_b):
        # admin_a proposes link A->B with view+dispatch on messages
        r = admin_a["session"].post(
            f"{BASE_URL}/api/org-links",
            json={
                "from_org_id": org_a["id"],
                "to_org_id": org_b["id"],
                "permissions": "view+dispatch",
                "share": {"radios": True, "messages": True, "positions": True, "voice": True,
                          "overlays": True, "geofences": True, "emergencies": True},
            },
        )
        assert r.status_code == 200, r.text
        link = r.json()
        assert link["status"] == "pending"
        link_id = link["id"]

        # admin_b approves
        ap = admin_b["session"].post(f"{BASE_URL}/api/org-links/{link_id}/approve")
        assert ap.status_code == 200, ap.text
        assert ap.json()["status"] == "active"

        # Now admin_b can see admin_a's groups
        # Create a distinct group in A
        gr = admin_a["session"].post(
            f"{BASE_URL}/api/groups",
            json={"name": f"TEST_LINKED_{_RUN_ID}", "talkgroup_id": 90050},
        )
        # (positions share drives group visibility) — check groups list
        # Note: server filters groups by "positions" resource
        groups_b = admin_b["session"].get(f"{BASE_URL}/api/groups").json()
        a_org_groups_visible = [g for g in groups_b if g.get("org_id") == org_a["id"]]
        assert len(a_org_groups_visible) > 0, "linked org's groups should be visible"

        # revoke
        rv = admin_a["session"].post(f"{BASE_URL}/api/org-links/{link_id}/revoke")
        assert rv.status_code == 200

        # After revoke, admin_b should no longer see A's groups
        groups_b2 = admin_b["session"].get(f"{BASE_URL}/api/groups").json()
        a_visible_after = [g for g in groups_b2 if g.get("org_id") == org_a["id"]]
        assert a_visible_after == [], "after revoke, A's groups must not be visible to B"


# --------------------------------------------------------------------------- #
# 4) RBAC — regular user cannot mutate settings
# --------------------------------------------------------------------------- #
class TestUserRBAC:
    def test_user_cannot_create_group(self, user_in_b):
        r = user_in_b["session"].post(
            f"{BASE_URL}/api/groups", json={"name": "X", "talkgroup_id": 91111}
        )
        assert r.status_code == 403, r.status_code

    def test_user_cannot_patch_radio(self, user_in_b):
        r = user_in_b["session"].patch(f"{BASE_URL}/api/radios/1", json={"callsign": "X"})
        assert r.status_code == 403

    def test_user_cannot_create_channel(self, user_in_b):
        r = user_in_b["session"].post(f"{BASE_URL}/api/channels", json={"name": "X"})
        assert r.status_code == 403

    def test_user_cannot_create_geofence(self, user_in_b):
        r = user_in_b["session"].post(
            f"{BASE_URL}/api/geofences",
            json={"name": "X", "lat": 0, "lon": 0, "radius_m": 100},
        )
        assert r.status_code == 403

    def test_user_cannot_create_overlay(self, user_in_b):
        r = user_in_b["session"].post(f"{BASE_URL}/api/overlays", json={"name": "X"})
        assert r.status_code == 403

    def test_user_cannot_put_repeater_config(self, user_in_b):
        r = user_in_b["session"].put(
            f"{BASE_URL}/api/repeater-configs/12345", json={"name": "X"}
        )
        assert r.status_code == 403

    def test_user_can_list_radios(self, user_in_b):
        r = user_in_b["session"].get(f"{BASE_URL}/api/radios")
        assert r.status_code == 200

    def test_user_can_list_groups_channels_geofences_overlays(self, user_in_b):
        for path in ("/api/groups", "/api/channels", "/api/geofences", "/api/overlays", "/api/repeater-configs"):
            r = user_in_b["session"].get(f"{BASE_URL}{path}")
            assert r.status_code == 200, path

    def test_user_can_send_message_to_own_org_group(self, user_in_b, admin_b, org_b):
        # admin_b creates a group in B
        g = admin_b["session"].post(
            f"{BASE_URL}/api/groups",
            json={"name": f"TEST_UB_{_RUN_ID}", "talkgroup_id": 90200},
        ).json()
        r = user_in_b["session"].post(
            f"{BASE_URL}/api/messages", json={"text": "hi", "group_id": g["id"]}
        )
        assert r.status_code == 200, r.text

    def test_user_can_ptt(self, user_in_b):
        r = user_in_b["session"].post(f"{BASE_URL}/api/voice/ptt", json={})
        assert r.status_code == 200


# --------------------------------------------------------------------------- #
# 5) Emergency ack toggle
# --------------------------------------------------------------------------- #
class TestEmergencyAck:
    def test_user_cannot_ack_when_disabled(self, user_in_b, admin_b, super_client, org_b):
        # ensure org_b.user_can_ack_emergency = False
        super_client.patch(f"{BASE_URL}/api/orgs/{org_b['id']}", json={"user_can_ack_emergency": False})
        # trigger an emergency via admin_b (which is in org_b)
        admin_b["session"].post(
            f"{BASE_URL}/api/emergencies/simulate", json={"dmr_id": 7770001}
        )
        # find it
        emgs = admin_b["session"].get(f"{BASE_URL}/api/emergencies?status_filter=active").json()
        target = next((e for e in emgs if e["dmr_id"] == 7770001), None)
        assert target is not None, "emergency not created"
        # user tries to clear
        r = user_in_b["session"].post(f"{BASE_URL}/api/emergencies/{target['id']}/clear")
        assert r.status_code == 403
        # admin can always clear
        ra = admin_b["session"].post(f"{BASE_URL}/api/emergencies/{target['id']}/clear")
        assert ra.status_code == 200

    def test_user_can_ack_when_enabled(self, user_in_b, admin_b, super_client, org_b):
        super_client.patch(f"{BASE_URL}/api/orgs/{org_b['id']}", json={"user_can_ack_emergency": True})
        admin_b["session"].post(f"{BASE_URL}/api/emergencies/simulate", json={"dmr_id": 7770002})
        emgs = admin_b["session"].get(f"{BASE_URL}/api/emergencies?status_filter=active").json()
        target = next((e for e in emgs if e["dmr_id"] == 7770002), None)
        assert target is not None
        r = user_in_b["session"].post(f"{BASE_URL}/api/emergencies/{target['id']}/clear")
        assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# 6) Cross-org dispatch guard on messages
# --------------------------------------------------------------------------- #
class TestCrossOrgDispatch:
    def test_no_link_blocks_cross_org_message(self, admin_a, admin_b, org_a, org_b):
        # admin_b creates a group in B
        g = admin_b["session"].post(
            f"{BASE_URL}/api/groups",
            json={"name": f"TEST_XO_{_RUN_ID}", "talkgroup_id": 90300},
        ).json()
        # admin_a tries to message into B's group without link
        r = admin_a["session"].post(
            f"{BASE_URL}/api/messages", json={"text": "hey", "group_id": g["id"]}
        )
        assert r.status_code == 403

    def test_with_link_dispatch_allowed(self, admin_a, admin_b, org_a, org_b):
        # Create B->A link (so A can dispatch INTO B? actually direction is
        # A wants to write to B; per code can_dispatch_org checks a link
        # from target_org (B) to own (A), so we need B->A with view+dispatch)
        r = admin_b["session"].post(
            f"{BASE_URL}/api/org-links",
            json={
                "from_org_id": org_b["id"],
                "to_org_id": org_a["id"],
                "permissions": "view+dispatch",
            },
        )
        assert r.status_code == 200, r.text
        link_id = r.json()["id"]
        ap = admin_a["session"].post(f"{BASE_URL}/api/org-links/{link_id}/approve")
        assert ap.status_code == 200

        # create group in B, admin_a should now be able to send there
        g = admin_b["session"].post(
            f"{BASE_URL}/api/groups",
            json={"name": f"TEST_XO2_{_RUN_ID}", "talkgroup_id": 90310},
        ).json()
        send = admin_a["session"].post(
            f"{BASE_URL}/api/messages", json={"text": "hi from A", "group_id": g["id"]}
        )
        assert send.status_code == 200, send.text

        # cleanup revoke
        admin_b["session"].post(f"{BASE_URL}/api/org-links/{link_id}/revoke")


# --------------------------------------------------------------------------- #
# 7) Shift-log fan-out
# --------------------------------------------------------------------------- #
class TestShiftLogFanOut:
    def test_event_in_a_reaches_b_via_link(self, admin_a, admin_b, org_a, org_b):
        # Create link A->B with positions share
        r = admin_a["session"].post(
            f"{BASE_URL}/api/org-links",
            json={"from_org_id": org_a["id"], "to_org_id": org_b["id"], "permissions": "view",
                  "share": {"positions": True, "messages": True, "radios": True,
                            "voice": True, "overlays": True, "geofences": True, "emergencies": True}},
        )
        assert r.status_code == 200, r.text
        link_id = r.json()["id"]
        admin_b["session"].post(f"{BASE_URL}/api/org-links/{link_id}/approve")

        # inject a packet in org_a
        unique_id = 6660000 + int(_RUN_ID, 16) % 1000
        admin_a["session"].post(
            f"{BASE_URL}/api/inject",
            json={"dmr_id": unique_id, "lat": 12.34, "lon": 56.78, "callsign": f"TESTA_{_RUN_ID}"},
        )
        # admin_b queries shift-log
        log = admin_b["session"].get(f"{BASE_URL}/api/shift-log?limit=50").json()
        found = any(e.get("dmr_id") == unique_id for e in log)
        assert found, "expected packet event to appear in B's shift log via link"

        admin_a["session"].post(f"{BASE_URL}/api/org-links/{link_id}/revoke")


# --------------------------------------------------------------------------- #
# 8) Regression: super_admin can hit all existing endpoints
# --------------------------------------------------------------------------- #
class TestRegression:
    def test_endpoints_return_200_for_super(self, super_client):
        for path in (
            "/api/radios", "/api/groups", "/api/channels", "/api/geofences",
            "/api/overlays", "/api/messages", "/api/alerts", "/api/emergencies",
            "/api/repeaters", "/api/repeater-configs", "/api/packets",
            "/api/shift-log", "/api/status", "/api/orgs", "/api/org-links",
        ):
            r = super_client.get(f"{BASE_URL}{path}")
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    def test_super_can_create_channel_and_group_and_geofence(self, super_client):
        c = super_client.post(f"{BASE_URL}/api/channels", json={"name": f"TEST_CH_{_RUN_ID}"})
        assert c.status_code == 200
        cid = c.json()["id"]
        upd = super_client.patch(f"{BASE_URL}/api/channels/{cid}", json={"description": "x"})
        assert upd.status_code == 200
        d = super_client.delete(f"{BASE_URL}/api/channels/{cid}")
        assert d.status_code == 200

        g = super_client.post(
            f"{BASE_URL}/api/groups", json={"name": f"TEST_GR_{_RUN_ID}", "talkgroup_id": 92000}
        )
        assert g.status_code == 200
        gid = g.json()["id"]
        d2 = super_client.delete(f"{BASE_URL}/api/groups/{gid}")
        assert d2.status_code == 200

        gf = super_client.post(
            f"{BASE_URL}/api/geofences",
            json={"name": f"TEST_GF_{_RUN_ID}", "lat": 0, "lon": 0, "radius_m": 100},
        )
        assert gf.status_code == 200
        gfid = gf.json()["id"]
        d3 = super_client.delete(f"{BASE_URL}/api/geofences/{gfid}")
        assert d3.status_code == 200
