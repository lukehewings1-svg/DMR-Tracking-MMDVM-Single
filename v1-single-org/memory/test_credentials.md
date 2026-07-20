# DMR Tracker – Test Credentials

## Admin (seeded on startup from `backend/.env`)

- **Email:** `admin@dmrtracker.app`
- **Password:** `admin123`
- **Role:** `admin`
- **Status:** `approved`

## Auth Endpoints

- `POST /api/auth/register` – self-register (creates `pending` account)
- `POST /api/auth/login` – returns `{token, user}` on success
- `GET  /api/auth/me` – current user (Bearer token in `Authorization` header)
- `POST /api/auth/logout`

## Admin Endpoints (Bearer token, `role=admin`)

- `GET  /api/admin/users`
- `POST /api/admin/users/{id}/approve`
- `POST /api/admin/users/{id}/reject`
- `POST /api/admin/users/{id}/role`   – body `{ "role": "admin" | "user" }`
- `DELETE /api/admin/users/{id}`

Bearer token is stored in `localStorage['dmr_token']` on the frontend and sent
via `Authorization: Bearer <token>` on every request. The WebSocket at
`/api/ws?token=<jwt>` also requires the same token.
