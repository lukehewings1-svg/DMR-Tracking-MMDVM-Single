# v16: Emergency acknowledge, gateway admin CRUD, gateway/dispatcher voice WS protocol, voice ACL
import asyncio
import json
import os
import time
import uuid

import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
ADMIN = {"email": "admin@dmrtracker.app", "password": "admin123"}
FIRE_TG, MED_TG = 94, 91
R_FIRE, R_MED = 2359901, 2359902  # TEST radios


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def ctx():
    at = _login(**ADMIN)
    groups = {g["talkgroup_id"]: g["id"] for g in requests.get(f"{BASE_URL}/api/groups", headers=H(at)).json()}
    email = f"test_disp_{uuid.uuid4().hex[:6]}@example.com"
    reg = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "test1234", "callsign": "TEST_DSP"})
    assert reg.status_code == 200, reg.text
    uid = reg.json()["id"]
    assert requests.post(f"{BASE_URL}/api/admin/users/{uid}/approve", headers=H(at)).status_code == 200
    ut = _login(email, "test1234")
    for dmr, tg, cs in ((R_FIRE, FIRE_TG, "TEST_FIRE"), (R_MED, MED_TG, "TEST_MED")):
        r = requests.post(f"{BASE_URL}/api/inject", headers=H(at), json={"dmr_id": dmr, "callsign": cs, "lat": 51.5, "lon": -0.1, "group_id": groups[tg]})
        assert r.status_code == 200
    gw = requests.post(f"{BASE_URL}/api/gateways", headers=H(at), json={"name": "TEST_GW_PY"}).json()
    c = {"at": at, "ut": ut, "uid": uid, "groups": groups, "gw": gw, "emerg": []}
    yield c
    for eid in c["emerg"]:
        requests.post(f"{BASE_URL}/api/emergencies/{eid}/clear", headers=H(at))
    requests.delete(f"{BASE_URL}/api/gateways/{gw['id']}", headers=H(at))
    requests.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=H(at))
    for dmr in (R_FIRE, R_MED):
        requests.delete(f"{BASE_URL}/api/radios/{dmr}", headers=H(at))


async def _recv_until(ws, pred, timeout=4.0):
    """Collect messages until pred(msg) true; returns (match, all)."""
    seen = []
    end = time.time() + timeout
    while time.time() < end:
        try:
            m = await asyncio.wait_for(ws.recv(), timeout=end - time.time())
        except asyncio.TimeoutError:
            break
        m = m if isinstance(m, bytes) else json.loads(m)
        seen.append(m)
        if pred(m):
            return m, seen
    return None, seen


def is_t(t):
    return lambda m: isinstance(m, dict) and m.get("type") == t


def _active_emergency(at, dmr):
    for e in requests.get(f"{BASE_URL}/api/emergencies", headers=H(at)).json():
        if e["dmr_id"] == dmr:
            return e
    return None


# ---------------- Emergency ack ----------------
class TestEmergencyAck:
    def test_ack_by_non_admin_and_admin_clear(self, ctx):
        at, ut = ctx["at"], ctx["ut"]
        assert requests.post(f"{BASE_URL}/api/emergencies/simulate", headers=H(at), json={"dmr_id": R_FIRE}).status_code == 200
        time.sleep(0.5)
        e = _active_emergency(at, R_FIRE)
        assert e and not e.get("acknowledged_at")
        ctx["emerg"].append(e["id"])

        async def run():
            async with websockets.connect(f"{WS_BASE}/api/ws?token={at}") as ws:
                await asyncio.sleep(0.5)
                r = await asyncio.to_thread(requests.post, f"{BASE_URL}/api/emergencies/{e['id']}/ack", headers=H(ut))
                m, _ = await _recv_until(ws, is_t("emergency_ack"))
                return r, m

        r, m = asyncio.run(run())
        assert r.status_code == 200
        d = r.json()
        assert d["acknowledged_by"] == "TEST_DSP" and d["acknowledged_at"] and d["status"] == "active"
        assert m and m["emergency"]["id"] == e["id"]
        # idempotent - admin ack keeps original acker
        r2 = requests.post(f"{BASE_URL}/api/emergencies/{e['id']}/ack", headers=H(at))
        assert r2.status_code == 200 and r2.json()["acknowledged_by"] == "TEST_DSP" and r2.json()["acknowledged_at"] == d["acknowledged_at"]
        # still active
        assert _active_emergency(at, R_FIRE)["acknowledged_by"] == "TEST_DSP"
        # shift log entry (exactly one)
        logs = requests.get(f"{BASE_URL}/api/shift-log", headers=H(at), params={"dmr_id": R_FIRE}).json()
        assert len([l for l in logs if l["event_type"] == "emergency_ack" and l["actor"] == "TEST_DSP"]) == 1
        # shift-log filter by event_type=emergency_ack should be supported
        assert requests.get(f"{BASE_URL}/api/shift-log", headers=H(at), params={"event_type": "emergency_ack"}).status_code == 200
        # non-admin clear forbidden
        assert requests.post(f"{BASE_URL}/api/emergencies/{e['id']}/clear", headers=H(ut)).status_code == 403
        assert requests.post(f"{BASE_URL}/api/emergencies/{e['id']}/clear", headers=H(at)).status_code == 200
        assert _active_emergency(at, R_FIRE) is None
        # ack after clear -> 404
        assert requests.post(f"{BASE_URL}/api/emergencies/{e['id']}/ack", headers=H(ut)).status_code == 404

    def test_ack_unknown_404_and_unauth(self, ctx):
        assert requests.post(f"{BASE_URL}/api/emergencies/nope/ack", headers=H(ctx["ut"])).status_code == 404
        assert requests.post(f"{BASE_URL}/api/emergencies/nope/ack").status_code in (401, 403)


# ---------------- Gateways CRUD ----------------
class TestGatewaysAdmin:
    def test_list_contains_new_gateway_without_key(self, ctx):
        gw = ctx["gw"]
        assert isinstance(gw["key"], str) and len(gw["key"]) > 20
        lst = requests.get(f"{BASE_URL}/api/gateways", headers=H(ctx["at"])).json()
        mine = [g for g in lst if g["id"] == gw["id"]]
        assert mine and mine[0]["online"] is False and "key" not in mine[0] and "key_hash" not in mine[0]

    def test_non_admin_forbidden(self, ctx):
        ut = ctx["ut"]
        assert requests.get(f"{BASE_URL}/api/gateways", headers=H(ut)).status_code == 403
        assert requests.post(f"{BASE_URL}/api/gateways", headers=H(ut), json={"name": "TEST_x"}).status_code == 403
        assert requests.delete(f"{BASE_URL}/api/gateways/{ctx['gw']['id']}", headers=H(ut)).status_code == 403

    def test_create_validation(self, ctx):
        assert requests.post(f"{BASE_URL}/api/gateways", headers=H(ctx["at"]), json={"name": ""}).status_code == 422

    def test_create_delete(self, ctx):
        at = ctx["at"]
        g = requests.post(f"{BASE_URL}/api/gateways", headers=H(at), json={"name": "TEST_GW_DEL"}).json()
        assert requests.delete(f"{BASE_URL}/api/gateways/{g['id']}", headers=H(at)).status_code == 200
        assert all(x["id"] != g["id"] for x in requests.get(f"{BASE_URL}/api/gateways", headers=H(at)).json())


# ---------------- Gateway + dispatcher voice protocol ----------------
class TestVoiceProtocol:
    def test_bad_key_closes_4401(self):
        async def run():
            try:
                async with websockets.connect(f"{WS_BASE}/api/gateway/ws?key=bad") as ws:
                    await ws.recv()
            except websockets.exceptions.ConnectionClosed as e:
                return e.rcvd.code if e.rcvd else None
            except websockets.exceptions.InvalidStatus as e:
                return f"http {e.response.status_code}"
        assert asyncio.run(run()) in (4401, "http 403")  # close-before-accept => HTTP 403 handshake reject

    def test_bad_token_voice_ws_closes(self):
        async def run():
            try:
                async with websockets.connect(f"{WS_BASE}/api/voice/ws?token=bad") as ws:
                    await ws.recv()
            except websockets.exceptions.ConnectionClosed as e:
                return e.rcvd.code if e.rcvd else None
            except websockets.exceptions.InvalidStatus as e:
                return f"http {e.response.status_code}"
        assert asyncio.run(run()) in (4401, "http 403")  # close-before-accept => HTTP 403 handshake reject

    def test_full_tx_rx_floor_control(self, ctx):
        at, key = ctx["at"], ctx["gw"]["key"]

        async def run():
            res = {}
            async with websockets.connect(f"{WS_BASE}/api/gateway/ws?key={key}") as gw:
                await gw.send(json.dumps({"type": "hello", "radio_id": 2359999}))
                await asyncio.sleep(0.5)
                async with websockets.connect(f"{WS_BASE}/api/voice/ws?token={at}") as d1, \
                        websockets.connect(f"{WS_BASE}/api/voice/ws?token={ctx['ut']}") as d2:
                    m, _ = await _recv_until(d1, is_t("voice_status"))
                    res["status"] = m["status"]
                    await _recv_until(d2, is_t("voice_status"), 1)
                    # TX group
                    await d1.send(json.dumps({"type": "ptt_start", "call_type": "group", "target_id": FIRE_TG}))
                    res["granted"], _ = await _recv_until(d1, is_t("ptt_granted"))
                    res["tx_start"], _ = await _recv_until(gw, is_t("tx_start"))
                    # floor control
                    await d2.send(json.dumps({"type": "ptt_start", "call_type": "group", "target_id": FIRE_TG}))
                    res["floor"], _ = await _recv_until(d2, is_t("ptt_denied"))
                    for _i in range(5):
                        await d1.send(bytes(320))
                    await d1.send(bytes(100))  # wrong size, dropped
                    frames = 0
                    end = time.time() + 3
                    while frames < 5 and time.time() < end:
                        try:
                            x = await asyncio.wait_for(gw.recv(), 1)
                        except asyncio.TimeoutError:
                            break
                        if isinstance(x, bytes):
                            assert len(x) == 320
                            frames += 1
                    res["frames"] = frames
                    await d1.send(json.dumps({"type": "ptt_end"}))
                    res["tx_end"], _ = await _recv_until(gw, is_t("tx_end"))
                    # RX
                    await gw.send(json.dumps({"type": "rx_start", "call_type": "group", "src_id": R_FIRE, "dst_id": FIRE_TG}))
                    res["rx_start"], _ = await _recv_until(d1, is_t("rx_start"))
                    await gw.send(bytes(640))
                    b, _ = await _recv_until(d1, lambda m: isinstance(m, bytes))
                    res["rx_bytes"] = len(b) if b else 0
                    await d1.send(json.dumps({"type": "ptt_start", "call_type": "group", "target_id": FIRE_TG}))
                    res["busy"], _ = await _recv_until(d1, is_t("ptt_denied"))
                    await gw.send(json.dumps({"type": "rx_end"}))
                    res["rx_end"], _ = await _recv_until(d1, is_t("rx_end"))
                    # Gateway disconnect during TX
                    await asyncio.sleep(0.3)
                    await d1.send(json.dumps({"type": "ptt_start", "call_type": "private", "target_id": R_FIRE}))
                    res["granted2"], _ = await _recv_until(d1, is_t("ptt_granted"))
                    res["tx_start2"], _ = await _recv_until(gw, is_t("tx_start"))
                    await gw.close()
                    res["gw_gone"], _ = await _recv_until(d1, is_t("ptt_denied"))
                    m, _ = await _recv_until(d1, lambda m: is_t("voice_status")(m) and m["status"]["route"] is None)
                    res["route_after"] = m
            return res

        r = asyncio.run(run())
        assert r["status"]["route"] == "gateway"
        assert any(g["name"] == "TEST_GW_PY" for g in r["status"]["gateways"])
        assert r["granted"] and r["granted"]["route"] == "gateway"
        assert r["tx_start"] == {"type": "tx_start", "call_type": "group", "target_id": FIRE_TG}
        assert r["floor"] and "already transmitting" in r["floor"]["reason"]
        assert r["frames"] == 5
        assert r["tx_end"]
        assert r["rx_start"] and r["rx_start"]["callsign"] == "TEST_FIRE" and r["rx_start"]["src_id"] == R_FIRE
        assert r["rx_bytes"] == 320
        assert r["busy"] and "Channel busy" in r["busy"]["reason"]
        assert r["rx_end"]
        assert r["granted2"] and r["tx_start2"]["call_type"] == "private" and r["tx_start2"]["target_id"] == R_FIRE
        assert r["gw_gone"] and r["gw_gone"]["reason"] == "Gateway disconnected"
        assert r["route_after"] is not None

    def test_gateway_emergency(self, ctx):
        at, key = ctx["at"], ctx["gw"]["key"]

        async def run():
            async with websockets.connect(f"{WS_BASE}/api/gateway/ws?key={key}") as gw:
                await gw.send(json.dumps({"type": "hello", "radio_id": 2359999}))
                await gw.send(json.dumps({"type": "emergency", "src_id": R_MED}))
                await asyncio.sleep(1.5)
        asyncio.run(run())
        e = _active_emergency(at, R_MED)
        assert e is not None and e["signature"] == "dmr818-alarm"
        ctx["emerg"].append(e["id"])


# ---------------- Voice ACL ----------------
class TestVoiceACL:
    def test_restricted_dispatcher(self, ctx):
        at, ut, key = ctx["at"], ctx["ut"], ctx["gw"]["key"]
        r = requests.post(f"{BASE_URL}/api/admin/users/{ctx['uid']}/groups", headers=H(at), json={"allowed_group_ids": [ctx["groups"][FIRE_TG]]})
        assert r.status_code == 200

        async def run():
            res = {}
            async with websockets.connect(f"{WS_BASE}/api/gateway/ws?key={key}") as gw:
                await asyncio.sleep(0.4)
                async with websockets.connect(f"{WS_BASE}/api/voice/ws?token={ut}") as d:
                    await _recv_until(d, is_t("voice_status"))
                    await d.send(json.dumps({"type": "ptt_start", "call_type": "group", "target_id": MED_TG}))
                    res["deny_tg"], _ = await _recv_until(d, lambda m: is_t("ptt_denied")(m) or is_t("ptt_granted")(m))
                    await d.send(json.dumps({"type": "ptt_start", "call_type": "private", "target_id": R_MED}))
                    res["deny_radio"], _ = await _recv_until(d, lambda m: is_t("ptt_denied")(m) or is_t("ptt_granted")(m))
                    await d.send(json.dumps({"type": "ptt_start", "call_type": "group", "target_id": FIRE_TG}))
                    res["ok_tg"], _ = await _recv_until(d, lambda m: is_t("ptt_denied")(m) or is_t("ptt_granted")(m))
                    await d.send(json.dumps({"type": "ptt_end"}))
                    await _recv_until(gw, is_t("tx_end"))
                    await asyncio.sleep(0.3)
                    # RX from a Medical radio (outside groups) on Medical TG
                    await gw.send(json.dumps({"type": "rx_start", "call_type": "group", "src_id": R_MED, "dst_id": MED_TG}))
                    await gw.send(bytes(320))
                    m, seen = await _recv_until(d, lambda m: isinstance(m, bytes) or is_t("rx_start")(m), 2)
                    res["med_rx"] = m
                    await gw.send(json.dumps({"type": "rx_end"}))
                    await asyncio.sleep(0.5)
                    # RX from Fire radio -> heard
                    await gw.send(json.dumps({"type": "rx_start", "call_type": "group", "src_id": R_FIRE, "dst_id": FIRE_TG}))
                    res["fire_rx"], _ = await _recv_until(d, is_t("rx_start"), 2)
                    await gw.send(json.dumps({"type": "rx_end"}))
            return res

        r = asyncio.run(run())
        assert r["deny_tg"]["type"] == "ptt_denied" and "not allowed" in r["deny_tg"]["reason"]
        assert r["deny_radio"]["type"] == "ptt_denied" and "not allowed" in r["deny_radio"]["reason"]
        assert r["ok_tg"]["type"] == "ptt_granted"
        assert r["med_rx"] is None
        assert r["fire_rx"] is not None
