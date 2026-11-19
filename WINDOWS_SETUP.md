# DMR Tracker — Windows Laptop Setup (single organisation)

Native Windows install (no WSL). Tested layout: code unzipped to `C:\dmr-tracker`.

---

## 1. Install the prerequisites (once)

| Software | Where | Notes |
|---|---|---|
| **Python 3.11 (64-bit)** | `winget install -e --id Python.Python.3.11` or python.org → *Python 3.11.9 Windows installer (64-bit)* | Tick **"Add python.exe to PATH"** |
| **Node.js 20 LTS** | nodejs.org | Defaults |
| **MongoDB Community Server** | mongodb.com/try/download/community | Choose **"Install as a Service"** |
| **Git** (optional) | git-scm.com | Defaults |

> **Use Python 3.11.** Python 3.14 (32-bit) and 3.15 do not have pre-built
> Windows wheels for several dependencies (pydantic-core, bcrypt) and pip will
> fail with "Microsoft Visual C++ required". Installing 3.11 alongside other
> versions is fine — `py -3.11` selects it.

Close and reopen PowerShell, then check:
```powershell
py --list            # should include -V:3.11 ... (64-bit)
py -3.11 --version   # Python 3.11.9
node --version
```

If `py -3.11` says *"No suitable Python runtime found"*: 3.11 isn't installed
yet. If it persists after installing, turn **off** `python.exe` / `python3.exe`
in *Settings → Apps → Advanced app settings → App execution aliases*.

---

## 2. Get the code

```powershell
git clone <your-github-repo-url> C:\dmr-tracker
```
…or download the ZIP from GitHub and unzip it to `C:\dmr-tracker`.
Only `backend\` and `frontend\` are needed (`archive\` holds the unused
multi-organisation edition).

---

## 3. Backend

If PowerShell blocks scripts, run once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

```powershell
cd C:\dmr-tracker\backend
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python --version                         # must say 3.11.x
pip install -r requirements-windows.txt
copy .env.example .env
notepad .env
```

> Do **not** use `requirements.txt` on Windows — it contains cloud/dev
> packages that fail to build on Windows and aren't needed.
> If you created a `venv` with another Python version, delete it first:
> `Remove-Item -Recurse -Force venv`.

Edit `.env`:
- `JWT_SECRET` → output of `python -c "import secrets;print(secrets.token_hex(32))"`
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` → your admin login
- `HB_PASSWORD` → must match the password set in Pi-Star
- `EMERGENT_LLM_KEY` → only needed for uploading overlay **images**
  (Emergent Profile → Universal Key). Leave blank otherwise; everything else works.

Start it:
```powershell
uvicorn server:app --host 0.0.0.0 --port 8001
```
Check http://localhost:8001/api/ → `{"service":"dmr-tracker",...}`. Keep this window open.

---

## 4. Frontend (second PowerShell window)

```powershell
cd C:\dmr-tracker\frontend
npm install -g yarn
copy .env.example .env
yarn install
yarn start
```
Open http://localhost:3000 and log in with the admin credentials from `backend\.env`.

`frontend\.env` must contain only:
```
REACT_APP_BACKEND_URL=http://localhost:8001
```
(Restart `yarn start` after any change to it.)

---

## 5. Windows Firewall (PowerShell **as Administrator**)

```powershell
New-NetFirewallRule -DisplayName "DMR HB Master" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 62031
New-NetFirewallRule -DisplayName "DMR Tracker API" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8001
New-NetFirewallRule -DisplayName "DMR Tracker Web" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000
```
Set the network to **Private**: *Settings → Network & internet → (your network) → Private*.

---

## 6. Point the MMDVM / Pi-Star at the laptop

1. `ipconfig` → note the **IPv4 Address** (e.g. `192.168.1.50`).
2. Pi-Star → *Configuration → Expert → DMR Network* (or MMDVMHost `[DMR Network]`):
   - Address: `192.168.1.50`
   - Port: `62031`
   - Password: same as `HB_PASSWORD`
3. Apply — the MMDVM appears under **Connected MMDVMs** in the app.

Tip: reserve the laptop's IP in your router so it never changes.

---

## 7. Other devices on the LAN (optional)

Set `frontend\.env` to `REACT_APP_BACKEND_URL=http://192.168.1.50:8001`,
restart `yarn start`, then browse to `http://192.168.1.50:3000` from phones/tablets.

---

## 8. Daily start-up

### Desktop shortcut (one-time)
From `C:\dmr-tracker` in PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\create-desktop-shortcut.ps1
```
A **DMR Tracker** icon appears on the Desktop. Double-click it to start
MongoDB (if stopped), the backend and the frontend, then the browser opens at
http://localhost:3000 once the app is ready (first start ≈ 30–60 s).
To stop the app, close the two windows titled *DMR Tracker - Backend* and
*DMR Tracker - Frontend*.

### Manual start
```powershell
# Window 1
cd C:\dmr-tracker\backend; .\venv\Scripts\Activate.ps1; uvicorn server:app --host 0.0.0.0 --port 8001
# Window 2
cd C:\dmr-tracker\frontend; yarn start
```
MongoDB starts automatically as a Windows service.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `py -3.11`: *No suitable Python runtime found* | Install Python 3.11 64-bit (step 1), reopen PowerShell |
| pip: *Microsoft Visual C++ 14.0 required* / *no matching distribution* | Wrong Python (3.14/3.15/32-bit) or used `requirements.txt` — recreate venv with 3.11 and use `requirements-windows.txt` |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `KeyError: 'MONGO_URL'` | `backend\.env` missing or saved as `.env.txt` (enable *View → File name extensions*) |
| `ServerSelectionTimeoutError` (port 27017) | MongoDB not running → `services.msc` → **MongoDB Server** → Start |
| Login page: *Network Error* | Backend not running, or wrong `REACT_APP_BACKEND_URL` (restart `yarn start` after edits) |
| Invalid credentials | Admin is created on first start only. Changed `ADMIN_PASSWORD` later? Delete the `users` collection (MongoDB Compass) and restart backend |
| `HB Master could not bind` | Port 62031 in use — change `HB_BIND_PORT` and the Pi-Star port |
| MMDVM never connects | Firewall rule, network set to Private, matching password, no VPN active |
| `yarn` not recognised | Reopen PowerShell after `npm install -g yarn` |
| Overlay image upload fails | Set `EMERGENT_LLM_KEY` in `backend\.env` and make sure the laptop has internet |
| Stops receiving overnight | *Settings → System → Power → Sleep → Never* (when plugged in) |
