# DMR Radio Tracker — PRD

## Original problem statement
Build an app that pulls GPS + messaging data from DMR radios (via MMDVM directly, off-network — no BrandMeister), plots positions on OpenStreetMap, supports multi-brand radios, admin-approved login, per-radio custom icon+callsign, geofence alerts, multi-MMDVM cross-linked voice bridge, editable groups (talk groups), DMR SMS (send/receive), browser PTT with server-side AMBE dongle (SMS fallback), and radio emergency-button detection with visual + audible alarm.

## Architecture
- Backend: FastAPI + Motor (MongoDB). HB Master UDP listener on port 62031. Bearer JWT auth. WebSocket at /api/ws for live push.
- Frontend: React 19 + react-router 7 + Leaflet (OSM CARTO Dark) + Tailwind + shadcn/ui. Dark tactical dashboard.
- HB Master relays voice slot (TS2) between all connected MMDVMs opaquely; DATA slot (TS1) parsed for GPS + SMS + emergency.
- AMBE dongle path scaffolded via /api/voice/*; when unavailable PTT falls back to sending DMR SMS.

## User personas
- Ham radio operator / net control running SAR, security, event ops.
- Dispatcher tracking a fleet of radios across multiple simulcast sites.

## What's been implemented (v1.2 · Feb 2026)
- v1.0: HB Master UDP listener; Motorola LRRP, Hytera, NMEA, APRS GPS parsers; live map with markers + trails; radio detail modal; roster with RSSI; packet log; simulated injector.
- v1.1: JWT auth with admin-approved onboarding; admin users page; radio icon + color customization; geofences + enter/exit alerts.
- v1.2: Multi-MMDVM support with per-repeater status panel; TS2 voice cross-linking between MMDVMs; Groups (talk groups) CRUD + filtering; DMR SMS send + receive (group / private) + conversation view; browser PTT with AMBE dongle detection + SMS fallback; Emergency button detection + red banner + roster/marker highlight + browser siren; comprehensive SETUP.md/SETUP_PART2.md guide for server + MMDVM + per-brand radio programming.

## Test status
Iteration 1: 14/14 backend tests pass, all frontend flows validated. Iteration 2 (v1.2): 28/28 backend, all frontend flows including emergency banner + siren + group filters + messaging + PTT SMS fallback.

## Backlog
- P0: Real AMBE audio pipeline (browser mic → server → DVSI dongle → DMR voice frames). Requires physical hardware for E2E test.
- P1: BPTC(196,96) FEC + proper CSBK header for DMR SMS so Motorola MOTOTRBO SMS interops.
- P1: Talkgroup-selective voice routing (currently relays voice to all MMDVMs; add per-repeater TG whitelists).
- P2: Radio grouping analytics (heatmaps, dwell time per geofence, group-scoped alerts).
- P2: Multi-tenant deployments (organizations, per-org groups + users).
- P2: Mobile-friendly dashboard.

## Next tasks
- Ship as v1.2 release; ask user for a real MMDVM connection test to validate the voice bridge end-to-end.
- Optional: Motorola SMS PDU support if user brings a MOTOTRBO into the net.
- Optional: PWA install + browser push notifications for emergencies.

## v1.4 (Feb 2026): Multi-channel routing + Dispatcher ACL
- Channels are now first-class named entities with uuid ids. Admin can create arbitrary channels beyond the two DMR timeslots via POST /api/channels; slot-1/slot-2 remain as protected built-ins.
- Per-MMDVM slot mapping: PUT /api/repeater-configs/{repeater_id} binds each MMDVM's TS1 and TS2 to any channel. HBMaster resolves the channel per frame, relays voice ONLY to MMDVMs that carry the same channel, and rewrites the DMRD slot bit when the target MMDVM has the channel on the other timeslot.
- Dispatcher ACL: user doc gains allowed_group_ids: List[str]. Non-admin with a non-empty list only sees radios in those groups and can only send messages to those groups. Enforcement in /api/radios and /api/messages. Admin sets via POST /api/admin/users/{id}/groups.
- Frontend additions: RepeaterConfigPanel (admin-only) in Ops tab, ChannelFilter updated for id-based channels, UserGroupsModal per user row in AdminUsers page.
- Test status: iteration_4 = 52/52 backend + 100% frontend flows, 0 issues at any priority.
