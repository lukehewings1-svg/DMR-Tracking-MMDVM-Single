# v16 UI helper: `setup` creates TEST radio+emergency+gateway; `gw` runs a simulated Pi gateway; `cleanup` removes them
import asyncio, json, os, sys, time
import requests, websockets

B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WS = B.replace("https://", "wss://")
CTX = "/tmp/ui_ctx_v16.json"
RID = 2359911


def tok():
    return requests.post(f"{B}/api/auth/login", json={"email": "admin@dmrtracker.app", "password": "admin123"}).json()["token"]


def setup():
    h = {"Authorization": f"Bearer {tok()}"}
    requests.post(f"{B}/api/inject", headers=h, json={"dmr_id": RID, "callsign": "TEST_UI1", "lat": 51.505, "lon": -0.09})
    requests.post(f"{B}/api/emergencies/simulate", headers=h, json={"dmr_id": RID})
    time.sleep(0.5)
    e = [x for x in requests.get(f"{B}/api/emergencies", headers=h).json() if x["dmr_id"] == RID][0]
    gw = requests.post(f"{B}/api/gateways", headers=h, json={"name": "TEST_SIM_PI"}).json()
    json.dump({"emergency_id": e["id"], "gw": gw}, open(CTX, "w"))
    print(json.dumps({"emergency_id": e["id"], "gw_id": gw["id"]}))


async def gw(duration):
    c = json.load(open(CTX))
    log = open("/tmp/gw_sim_v16.log", "a")
    async with websockets.connect(f"{WS}/api/gateway/ws?key={c['gw']['key']}") as ws:
        await ws.send(json.dumps({"type": "hello", "radio_id": 2359998}))
        start = time.time()
        frames = 0
        next_rx = start + 15

        async def reader():
            nonlocal frames
            async for m in ws:
                if isinstance(m, bytes):
                    frames += 1
                    if frames % 25 == 1:
                        log.write(f"{time.time():.1f} audio frames={frames} len={len(m)}\n"); log.flush()
                else:
                    log.write(f"{time.time():.1f} MSG {m} frames_so_far={frames}\n"); log.flush()

        rt = asyncio.create_task(reader())
        while time.time() - start < duration:
            if time.time() >= next_rx:
                await ws.send(json.dumps({"type": "rx_start", "call_type": "group", "src_id": RID, "dst_id": 94}))
                log.write(f"{time.time():.1f} SENT rx_start\n"); log.flush()
                for _ in range(300):  # 6 s of audio
                    await ws.send(bytes(320))
                    await asyncio.sleep(0.02)
                await ws.send(json.dumps({"type": "rx_end"}))
                log.write(f"{time.time():.1f} SENT rx_end\n"); log.flush()
                next_rx = time.time() + 20
            await asyncio.sleep(0.2)
        rt.cancel()


def cleanup():
    h = {"Authorization": f"Bearer {tok()}"}
    c = json.load(open(CTX))
    requests.post(f"{B}/api/emergencies/{c['emergency_id']}/clear", headers=h)
    requests.delete(f"{B}/api/gateways/{c['gw']['id']}", headers=h)
    requests.delete(f"{B}/api/radios/{RID}", headers=h)
    print("cleaned")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "setup":
        setup()
    elif cmd == "gw":
        asyncio.run(gw(float(sys.argv[2])))
    else:
        cleanup()
