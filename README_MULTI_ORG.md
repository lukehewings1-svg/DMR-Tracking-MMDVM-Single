# DMR Radio Tracker — Multi-Org Edition

**Live preview:** the current running app (this repo → future GitHub-repo #2).

The frozen **single-org edition** lives at `/app/v1-single-org/` as a
self-contained project — push that to your first GitHub repo without touching
anything at `/app/`.

## What this edition adds
- **Organizations** — a super_admin creates orgs (agencies, teams, event
  operators). Every radio/group/message/overlay/geofence/situational-token
  lives inside an org. No data leaks between orgs.
- **Roles**
  - `super_admin`: cross-org; creates/deletes orgs + inter-org links.
  - `admin`: full control of a single org (settings, users, radio metadata,
    groups, channels, repeaters, geofences, overlays, situational tokens).
  - `user`: view + send SMS + PTT + view history/logs. Emergency
    acknowledgement is a per-org toggle (`user_can_ack_emergency`).
- **Inter-Org Links** — for multi-agency events. An admin proposes a
  one-directional link to another org, choosing which resources to share
  (radios, positions, messages, voice, overlays, geofences, emergencies) and
  whether the recipient gets **view** or **view+dispatch**. The recipient's
  admin approves. Events on shared resources are logged in every linked
  org's shift log so all sides see the same timeline.
- **Per-Repeater org binding** — each MMDVM is pre-registered on the
  Organizations page and authenticates with **its org's** HB password. Voice
  cross-linking respects org boundaries and active org-links.

## Quick start
Same as v1 — see `README.md`. On first boot the seeded admin becomes
`super_admin` and is attached to the auto-created **Default** organization.

```
Email:    admin@dmrtracker.app
Password: admin123   (change via ADMIN_EMAIL/ADMIN_PASSWORD in backend/.env)
```

## Onboarding a new organization (super_admin)
1. Log in and go to **Orgs** (top nav) → **New Organization**.
2. Set a name and (optionally) a custom MMDVM server DMR ID.
3. Choose whether regular users in that org can acknowledge emergencies.
4. Click the org's *user-plus* icon to create the first admin for it.
5. Hand the generated HB password + server DMR ID to that org's radio ops so
   they can point their MMDVMs at your listener.

## Sharing resources between orgs
Any admin can propose a link **from** their own org **to** another org:
1. Go to **Orgs → Inter-Org Resource Sharing → Propose Link**.
2. Pick the recipient, tick which resources to share, choose view or
   view+dispatch, click Propose.
3. Recipient's admin approves. Both sides now see the shared radios/messages/
   etc. Every event on shared resources is broadcast into both orgs'
   shift logs.

Links can be revoked at any time by either side. Super admin can delete a
link outright.

## Deployment notes
- `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
  `HB_BIND_HOST`, `HB_BIND_PORT`, `HB_PASSWORD` (legacy fallback),
  `SERVER_DMR_ID` still supported in `backend/.env`.
- The **first-time migration is automatic**: on first boot in v2 every
  legacy document is stamped with the **Default** org's id. Existing setups
  keep working with zero reconfig.
- Each new org can override `hb_password` + `server_dmr_id` from the Orgs
  page.
