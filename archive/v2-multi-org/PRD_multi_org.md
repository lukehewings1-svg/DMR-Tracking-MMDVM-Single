# DMR Radio Tracker — Multi-Org Edition PRD

## Original problem statement (verbatim)
User wanted an app that pulls data from DMR radios via an MMDVM (or standalone
radio) and plots location data on a map. As of Feb 2026 the user asked to:
1. Preserve the finished single-org app as a completely separate project so
   it can be pushed to its own GitHub repository.
2. Continue development of a new, separate **multi-organization** service
   that will live in a different GitHub repository.
3. Multi-org rules:
   - A **super_admin** creates new organizations (no self-serve org signup).
   - Organizations can **link** with other organizations to share resources
     for large multi-agency events (unified situational awareness +
     dispatching).
   - When multiple orgs are linked, **all get the same info in the logs**.
   - Only an **admin** can change settings, radio user info, and setup.
     Regular **users** can view, send messages, transmit voice, see history +
     logs, and (per-org toggle) acknowledge emergencies.

## Repository layout
- `/app/v1-single-org/` — frozen single-org snapshot (repo #1). Independent
  backend + frontend + README + `.env.example` + `.gitignore`.
- `/app/` — active multi-org service (repo #2). This is the running preview.

## Roles matrix
| Capability                                | super_admin | admin | user |
|-------------------------------------------|-------------|-------|------|
| Manage orgs & inter-org links              | ✅          | ❌    | ❌   |
| Radio metadata / delete radio              | ✅          | ✅    | ❌   |
| Groups / channels / geofences / overlays  | ✅          | ✅    | ❌   |
| Repeater configs / situational tokens      | ✅          | ✅    | ❌   |
| Approve/reject/edit users                  | (all orgs) | (own) | ❌   |
| View map, roster, history, logs            | ✅          | ✅    | ✅   |
| Send DMR SMS / PTT / voice                 | ✅          | ✅    | ✅   |
| Clear shift log                            | ✅          | ✅    | ❌   |
| CSV export shift log                       | ✅          | ✅    | ✅   |
| Clear emergency                            | ✅          | ✅    | per-org toggle |

## Data model (added collections)
- `organizations`: `{id, name, slug, active, hb_password, server_dmr_id,
   user_can_ack_emergency, created_at, updated_at}`
- `org_links`: `{id, from_org_id, to_org_id, status:
   pending|active|revoked, share: {radios, positions, messages, voice,
   overlays, geofences, emergencies}, permissions: view|view+dispatch,
   proposed_by, approved_by, expires_at, note, created_at, updated_at}`

Every domain collection now has `org_id`. Shift log & messages additionally
carry `visible_to_org_ids` (list of orgs that should see the event via
active links) so a single write is visible in every linked org's log.

## Isolation strategy
Row-level tenancy. Every read query resolves the user's `visible_org_ids`
(own org + all orgs actively linked to them for that resource type) and
filters with `{org_id: {$in: [...]}}`. Writes are restricted to the user's
own org (or an org actively linked with `view+dispatch`).

DMR UDP (HB Master) looks up each repeater's org from `repeater_configs`
and authenticates against **that org's** HB password. Voice cross-linking
respects both org boundaries and active org-links (`share.voice=true`).

WebSockets are per-user; each broadcast checks the event's `org_id`
against the recipient user's visible orgs for that resource type.

## Implemented (v2.0 — 2026-02)
- [x] Snapshot v1 to `/app/v1-single-org/` (backend + frontend + README +
      `.env.example` + `.gitignore` + `README_V1_SNAPSHOT.md`).
- [x] `tenancy.py`: `OrganizationStore`, `OrgLinkStore`, visibility resolver.
- [x] Auth: JWT carries `org_id` + role; `super_admin` role introduced;
      seeded admin auto-elevated to super_admin on first boot.
- [x] All stores refactored: `GroupStore`, `ChannelStore`,
      `RepeaterConfigStore`, `MessageStore`, `ShiftLogStore`, `OverlayStore`,
      `SituationalTokenStore`, `GeofenceEngine` — every read/write is
      org-scoped. New store method signatures take `org_id` explicitly.
- [x] Server: every endpoint filters reads via `_user_visible_orgs()`.
      New `/api/orgs`, `/api/orgs/{id}/bootstrap-admin`,
      `/api/orgs/{id}/rotate-hb-password`, `/api/org-links`,
      `/api/org-links/{id}/approve`, `/api/org-links/{id}/revoke`.
      Users cannot access any settings endpoint (admin-only guard).
- [x] DMR HB Master: per-org auth via `org_resolver`, packets stamped
      `org_id`, voice relays never cross org boundaries.
- [x] Migration: on-boot backfill of `org_id` on legacy docs → Default org.
- [x] Frontend: `SuperAdminOrgs` page + `OrgLinksPanel` component +
      org badge in top bar + role-gated UI + `admin/orgs` route.

## Implemented (v2.1 — 2026-02 — Event Sessions)
- [x] `events` collection + `EventStore` with planned/active/ended lifecycle.
- [x] `/api/events` full CRUD + `/participants`, `/overlays`, `/start`, `/end`.
- [x] On start(): fully-connected org-links (N*(N-1) directional) auto-created
      and immediately approved, tagged with `event_id` + note "Event: <name>".
- [x] On end() (manual or auto-end from background loop): those links revoked;
      attached overlays deactivated.
- [x] event_started + event_ended shift-log entries fan out to every
      participant org's log.
- [x] `EventsPanel.jsx` frontend UI on `/admin/orgs` — open to all admins.
- [x] Verified: 17/17 events pytest cases + 26/26 multi-org regression pass.

## Verification (backend curl smoke test)
- Super_admin creates org "Test Rescue", bootstraps its admin, admin logs in.
- Rescue admin sees only their 4 default groups + 0 radios initially.
- After injecting a radio into Rescue: Rescue sees 1 radio, Default admin
  (super) sees ALL 15 radios (his own 14 legacy + Rescue's 1).
- Rescue admin proposes view+dispatch link → Default approves → Default
  now visibly aggregates Rescue's radio through the link.

## Backlog
- P1: Native Sepura LIP (Location Information Protocol) decoding for GPS.
- P2: Motorola SMS protocol decoding.
- P2: Per-org branding (logo upload).
- P2: Billing/quotas.

## Test credentials
See `/app/memory/test_credentials.md`.
