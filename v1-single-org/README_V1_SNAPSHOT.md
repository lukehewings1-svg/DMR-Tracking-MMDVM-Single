# DMR Radio Tracker — v1 (Single-Organization Edition)

This directory is a **frozen snapshot** of the single-organization DMR Tracker.
It is a self-contained project: you can `git init` here and push to its own
GitHub repository, independent of the multi-organization edition that
continues to evolve at `/app/`.

## What's inside
```
v1-single-org/
├── backend/     # FastAPI + Motor + HB Master UDP + JWT auth (single-tenant)
├── frontend/    # React 19 + Leaflet + Tailwind + shadcn/ui
├── memory/      # PRD / test-credentials for v1
├── README.md    # Complete setup guide (server + MMDVM + per-brand radio)
└── README_V1_SNAPSHOT.md   (this file)
```

## Feature summary (frozen at v1.8)
- HB Master UDP listener on port 62031 for direct MMDVM ingest (no BrandMeister).
- Motorola LRRP, Hytera, NMEA, APRS GPS decoders.
- Live map (Leaflet + OSM/Carto) with Satellite / Street / Topo / Dark base
  layers, map rotation, live radio markers, historical trails, active-TX
  green pulsing rings.
- Custom admin-approved JWT auth (single admin account seeded from `.env`).
- Talk-group ("Groups") CRUD + roster/map filtering + DMR SMS + browser PTT
  (SMS fallback when no AMBE dongle).
- Emergency-button detection with red banner + siren + auto shift-log.
- Geofences with enter/exit alerts.
- Multi-MMDVM voice cross-linking (TS2), per-repeater channel binding, and
  Dispatcher ACL (allowed_group_ids).
- Shift Log with CSV export, live WebSocket, and admin purge.
- Event Overlays (Geoman-drawn shapes + image overlays with corner drag +
  opacity slider).
- Situational-Awareness read-only view via token-locked URL.
- Fully responsive (Mobile / Tablet / Desktop / TV) with collapsible +
  pinnable panels.
- In-app Setup Guide + `README.md` for full server/MMDVM/radio setup.

## Quick start
See [`README.md`](./README.md) for the complete setup guide.

Essentials:
```bash
# Backend
cd backend
cp .env.example .env      # edit values (see .env.example)
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend
cd ../frontend
cp .env.example .env      # set REACT_APP_BACKEND_URL
yarn install
yarn start                # runs on :3000
```

Default seeded admin: `admin@dmrtracker.app` / `admin123` (change in `.env`).

## Relationship to the multi-org edition
The multi-org edition lives at the parent workspace `/app/backend/` +
`/app/frontend/` and adds:
- Super-admin creates/manages organizations.
- Every domain object scoped by `org_id` (radios, groups, channels, messages,
  positions, packet log, shift log, overlays, situational tokens, geofences).
- Org-Links: two or more organizations can share resources (view or
  view+dispatch) for multi-agency events with unified situational awareness.
- Role tiers: `super_admin` (cross-org), `admin` (own org settings + users),
  `user` (view + message + PTT only; emergency-ack toggle per org).

The two projects share nothing at runtime — they're intended to be pushed
to two different GitHub repositories and deployed independently.
