"""Setup/teardown TEST radios for v15 UI tests. usage: python ui_seed_v15.py setup|teardown|emg|clearemg"""
import os
import sys
import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "admin@dmrtracker.app", "password": "admin123"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
groups = {g["name"]: g["id"] for g in requests.get(f"{API}/groups", headers=H).json()}
RADIOS = [
    (2359960, "TEST_FIRE", 51.509, -0.130, "Fire"),
    (2359961, "TEST_MED", 51.511, -0.121, "Medical"),
    (2359962, "TEST_NOGRP", 51.507, -0.125, None),
]
cmd = sys.argv[1]
if cmd == "setup":
    for d, cs, la, lo, g in RADIOS:
        requests.post(f"{API}/inject", headers=H, json={"dmr_id": d, "callsign": cs, "lat": la, "lon": lo})
        requests.patch(f"{API}/radios/{d}", headers=H, json={"group_id": groups[g] if g else None, "crew": f"TEST crew {cs}"})
    print(groups)
elif cmd == "emg":
    print(requests.post(f"{API}/emergencies/simulate", headers=H, json={"dmr_id": 2359961}).status_code)
elif cmd == "clearemg":
    for e in requests.get(f"{API}/emergencies", headers=H).json():
        if e["dmr_id"] in [r[0] for r in RADIOS]:
            requests.post(f"{API}/emergencies/{e['id']}/clear", headers=H)
elif cmd == "teardown":
    for d, *_ in RADIOS:
        print(d, requests.delete(f"{API}/radios/{d}", headers=H).status_code)
print("token", tok)
