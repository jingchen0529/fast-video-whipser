# Fast Video Whisper

Minimal FastAPI skeleton for file ingestion and future transcription workflows.

## What is included

- Environment-based settings with `pydantic-settings`
- Rotating file and console logging
- Optional static frontend hosting from FastAPI
- Async HTTP client wrapper built on `httpx`
- Media duration probing via `ffprobe`, with a WAV-only local fallback
- Health endpoint and temporary upload endpoint
- SQLite user database with cookie-based JWT sessions
- Role and permission based access control (RBAC)
- HttpOnly access/refresh cookies with CSRF protection
- Login captcha validation and rate limiting
- Unified success/error response envelopes
- Centralized exception handling for validation and runtime errors
- Basic pytest coverage for the app entrypoint

## Project layout

- `main.py`: FastAPI bootstrap entrypoint
- `app/core/application.py`: app assembly and startup
- `app/core/config.py`: runtime settings
- `app/core/http/`: response envelopes and exception handling
- `app/db/`: SQLite initialization and connection helpers
- `app/auth/`: JWT, password hashing, and RBAC services
- `app/api/router.py`: HTTP routes
- `app/http_client/async_http_client.py`: shared async HTTP client
- `app/utils/file_utils.py`: async temp-file utilities
- `scripts/run.py`: unified backend/frontend runner

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && pnpm install && cd ..
```

## Run modes

### Backend only

```bash
python3 main.py
```

Or, with reload:

```bash
python3 scripts/run.py backend
```

Open `http://127.0.0.1:8000/docs` after startup.

### Frontend only

```bash
python3 scripts/run.py frontend
```

This starts Nuxt on `http://127.0.0.1:3000` and proxies `/api/*` requests to the backend at `http://127.0.0.1:8000`.

### Frontend and backend together in development

```bash
python3 scripts/run.py dev
```

This runs:

- FastAPI on `http://127.0.0.1:8000`
- Nuxt on `http://127.0.0.1:3000`

### Build frontend into `static/`

```bash
python3 scripts/run.py build-frontend
```

This runs `nuxt generate` inside `frontend/` and copies the generated output into `./static`.

### Combined single-port mode

```bash
python3 scripts/run.py combined --build
```

After the build finishes, FastAPI serves:

- API routes under `/api/*`
- the generated frontend from `./static`

In this mode, open `http://127.0.0.1:8000`.

`ffprobe` from FFmpeg should be available in `PATH` for general audio or video duration probing.
If it is missing, the project falls back to Python's built-in `wave` module for WAV files only.

## Available endpoints

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/change-password`
- `GET /api/auth/users`
- `POST /api/auth/users`
- `PATCH /api/auth/users/{user_id}`
- `POST /api/auth/users/{user_id}/roles`
- `GET /api/auth/roles`
- `POST /api/auth/roles`
- `PATCH /api/auth/roles/{role_id}`
- `PUT /api/auth/roles/{role_id}/permissions`
- `GET /api/auth/permissions`
- `POST /api/auth/permissions`
- `GET /api/common/captcha`
- `POST /api/common/captcha/verify`
- `POST /api/common/upload`
- `POST /api/tiktok/info`

Legacy non-prefixed routes such as `/health` and `/tiktok/info` are still available for backward compatibility.

## Auth defaults

The backend now initializes a SQLite database automatically on startup using `DATABASE_URL`.

Core auth settings:

- database: `sqlite:///./app.db`
- cookie auth: HttpOnly access/refresh cookies + `auth_csrf_token`
- access token ttl: `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` (default `1440`, 24 hours)
- refresh token ttl: `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` (default `30`)
- public register: `false`
- login captcha: `true`
- login rate limit max attempts: `5`
- initial admin username: `admin`
- initial admin email: `admin@example.com`
- initial admin password: configured by `AUTH_INITIAL_ADMIN_PASSWORD`

The backend reads only the `AUTH_*` settings from `.env`. In production you must change at least:

- `AUTH_JWT_SECRET`
- `AUTH_INITIAL_ADMIN_PASSWORD`
- `AUTH_COOKIE_SECURE=true`

Unsafe write requests made with cookie auth must include `X-CSRF-Token`, and `/api/auth/login` now requires `captcha_id` and `captcha_code`.

## Response format

Successful responses use:

```json
{
  "code": 200,
  "router": "/api/health",
  "params": {},
  "data": {
    "status": "ok"
  }
}
```

Error responses use:

```json
{
  "code": 422,
  "message": "Request validation failed.",
  "time": "2026-03-31 16:45:21",
  "router": "/api/common/upload",
  "params": {},
  "details": []
}
```

## TikTok download request

Use a single `value` field and pass either an aweme_id or a TikTok URL:

```json
{
  "value": "7339393672959757570"
}
```

```json
{
  "value": "https://www.tiktok.com/@angelinazhq/video/7339393672959757570"
}
```

## Run tests

```bash
PYTHONPATH=. pytest
```
