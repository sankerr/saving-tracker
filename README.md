# Saving Tracker (Cloud)

Personal portfolio tracker deployed on the public internet with a free stack:

| Layer | Service | Role |
|-------|---------|------|
| Frontend | Vercel (static) | `frontend/` (served via `outputDirectory`) |
| Backend | Vercel Functions | `api/index.py` wraps `backend/saving_tracker.py` |
| Database | [Neon](https://neon.tech) | PostgreSQL (JSONB storage) |

The original local/Kubernetes version lives at [sankerr/saving-tracker](https://github.com/sankerr/saving-tracker).

## Architecture

```
Browser → Vercel (frontend static + Python function)
       → Neon PostgreSQL
       → data.gov.il + Yahoo Finance (sync)
       → Google Gemini (optional AI chat + in-app insight card + new-yield email insights)
       → Resend (optional new-yield email delivery)
```

Tracks provident/education funds (gemelnet), pension (pensia-net), RSU, ESPP, and cash, with dashboard projections/what-if, a savings goal, a Hebrew UI, and an optional AI chat assistant.

## Prerequisites

- GitHub repo connected to Vercel
- Neon project with a PostgreSQL database
- Existing portfolio JSON files (optional, for migration)

## 1. Neon — create database

1. Create a project at [neon.tech](https://neon.tech)
2. Copy the **pooled** connection string (`DATABASE_URL`)
3. Tables are created automatically on first backend boot

## 2. Vercel — deploy frontend + backend (one Hobby project)

1. In Vercel: **Add New → Project**, import this repo.
   `vercel.json` already sets **Output Directory** to `frontend` and routes
   `/api/*` to the Python function in `api/index.py`. Set the function region
   next to your Neon database (e.g. `fra1` for a Frankfurt DB).
2. Set environment variables (Project → Settings → Environment Variables):

| Variable | Example | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql://...` | Neon pooled connection string |
| `SESSION_SECRET` | random 32+ chars | JWT signing secret (`openssl rand -hex 32`) |
| `ADMIN_USERNAME` | `you@example.com` | Valid email; only used on first boot when DB has no users |
| `ADMIN_PASSWORD` | `...` | Strong password |
| `CRON_SECRET` | random 32+ chars | Protects `POST /api/cron/sync` (GitHub Actions daily job) |
| `RESEND_API_KEY` | `re_...` | [Resend](https://resend.com) API key for the new-yield email (optional) |
| `NOTIFY_FROM` | `Saving Tracker <onboarding@resend.dev>` | Verified sender in Resend |
| `CHAT_ENABLED` | `1` | Enable the in-app AI chat assistant (optional; requires `GEMINI_API_KEY`) |
| `GEMINI_API_KEY` | `AIza...` | [Google Gemini](https://ai.google.dev) API key; powers AI chat, the in-app dashboard insight card, and new-yield email insights (optional) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Gemini model override (optional; defaults to `gemini-3.1-flash-lite`) |

3. Deploy and note the public URL, e.g. `https://saving-tracker.vercel.app`.
   `CORS_ORIGIN` stays empty — frontend and API share one domain.
4. Health check: `GET https://<you>.vercel.app/api/health` → `{"ok":true,...}`.
   First boot seeds the admin from `ADMIN_USERNAME`/`ADMIN_PASSWORD`.

**Hobby notes:** one serverless function (`maxDuration` 300 s — the daily cron
sync runs inline and can take minutes), ~4.5 MB request cap, cold starts of a
few seconds, no sleep. Data stays in Neon — nothing to migrate DB-side.

## 3. Migrate existing data (optional)

If you have portfolio data from the local app:

```bash
cd backend
pip install -r requirements.txt

export DATABASE_URL='postgresql://...'
export ADMIN_USERNAME='you@example.com'
export ADMIN_PASSWORD='your-password'

python ../scripts/migrate_json_to_pg.py \
  --data /path/to/saving-tracker-data.json \
  --cache /path/to/saving-tracker-cache.json
```

If the user already exists (created by Vercel on first boot), the script updates their data in place.

## 4. Verify

1. Open your Vercel URL
2. Sign in with your username/password
3. Confirm portfolio loads
4. Run **Sync**
5. Add a test holding, refresh, confirm it persists

## Local development

For local dev you don't need Neon/Postgres. When `DATABASE_URL` is **empty**, the
backend uses an embedded **SQLite** database (an "H2-style" local DB) stored in a
single file at `backend/local.db` — created automatically, nothing to install or
run. On first boot in this mode it also seeds a ready-to-use dev login.

### Quick start (zero setup, auto-created init user)

```bash
cd backend
pip install -r requirements.txt   # psycopg2 is only needed for the Postgres backend

python3 saving_tracker.py
```

That's it. On first run you'll see:

```
storage: local SQLite at .../backend/local.db
Seeding local dev admin: dev@example.com / devpass123
```

The init user is created automatically:

| Field | Value |
|-------|-------|
| Username | `dev@example.com` |
| Password | `devpass123` |

`SESSION_SECRET` defaults to an insecure dev value in SQLite mode, so no env vars
are required. To choose your own init user instead, set `ADMIN_USERNAME` (must be
a valid email) and `ADMIN_PASSWORD` before the first run.

Then serve the frontend and log in with the credentials above:

```bash
cd frontend
# Edit config.js: window.API_BASE = 'http://localhost:8000'
python3 -m http.server 3000
```

Open http://localhost:3000 and sign in.

To reset local data, delete the DB file: `rm backend/local.db`.

### Local dev against real Postgres (optional)

Set `DATABASE_URL` to a Postgres connection string to use the production backend
locally instead of SQLite:

```bash
cd backend
pip install -r requirements.txt

export DATABASE_URL='postgresql://...'
export SESSION_SECRET='dev-secret-change-me'
export CORS_ORIGIN='http://localhost:3000'
export ADMIN_USERNAME='you@example.com'
export ADMIN_PASSWORD='dev'

python3 saving_tracker.py
```

> The SQLite backend is for local development only. Production runs on PostgreSQL
> (Neon); a custom SQLite file path can be set with `LOCAL_DB_PATH` or
> `DATABASE_URL='sqlite:////absolute/path.db'`.

## API auth

- `POST /api/login` — `{ "username", "password" }` → `{ "token" }` (approved users only; username must be a valid email)
- `POST /api/register` — `{ "username", "password" }` → creates account with `approved=false` (username must be a valid email)
- `POST /api/account/password` — `{ "current_password", "new_password" }` (change password while logged in)
- `DELETE /api/account` — `{ "password" }` (delete account and all portfolio data)
- All other `/api/*` routes require `Authorization: Bearer <token>`
- `GET /api/chat/status` — `{ "enabled": bool }` (whether AI chat is configured)
- `POST /api/chat` — `{ "messages": [...] }` → `{ "reply" }` (AI assistant; `404` when chat is disabled)
- `GET /api/insights` — `{ "insights", "generated_at", "cached" }` for the dashboard AI insight card (`ok:false, error:"insights_disabled"` without `GEMINI_API_KEY`; Hebrew only, cached per day; `?refresh=1` forces regeneration)
- `GET /api/version` — `{ "version" }`
- `GET /api/health` — no auth
- `POST /api/cron/sync` — daily sync trigger; requires `Authorization: Bearer <CRON_SECRET>`. Runs **inline** and returns `200` with full per-user results (serverless has no background threads, so the old 202 + poll contract is gone). Optional `?email=0` (also `false`/`no`/`off`) runs the sync **without** sending emails.
- `GET /api/cron/status` — last cron job status snapshot; requires `Authorization: Bearer <CRON_SECRET>`

## Daily sync & email alerts

A GitHub Actions workflow (`.github/workflows/daily-sync.yml`) triggers `POST /api/cron/sync` every day at **08:05 Asia/Jerusalem** (05:05 UTC). The endpoint runs the sync inline (up to the function's 300 s limit) and the workflow validates the returned per-user results.

Email is sent **only when a new monthly fund yield is published** — i.e. when `latest_published_period` advances past the last period a user was notified about. On days with no new yield the sync still runs but no email goes out. When a new yield is detected, each approved user is emailed a **dashboard snapshot** (totals, holdings, and short AI insights) and `last_notified_period` is advanced only after a successful send.

**Email toggle:** the `send_email` input on **Actions → Daily sync → Run workflow** controls whether emails are sent for a manual run (default `true`). Scheduled runs always allow email. Internally the workflow passes `?email=0` to the cron endpoint when the toggle is off, so you can trigger a data-only sync without notifying users.

**One-time setup:**

1. Ensure usernames in Neon are valid emails. If your admin account uses a non-email username, update it:
   ```sql
   UPDATE users SET username = 'you@example.com' WHERE username = 'admin';
   ```
2. Create a [Resend](https://resend.com) account, verify a sender domain (or use Resend's test sender), and set `RESEND_API_KEY` + `NOTIFY_FROM` on Vercel.
3. Set `GEMINI_API_KEY` on Vercel for AI insights in the email. Without it, sync and email still work — the insights section falls back to a static message. (`CHAT_ENABLED` is only needed for the in-app chat, not the email.)
4. Copy Vercel's `CRON_SECRET` value into GitHub repo **Settings → Secrets → Actions** as `CRON_SECRET`, and add `API_URL` (e.g. `https://saving-tracker.vercel.app`).
5. Deploy, then run the workflow manually (**Actions → Daily sync → Run workflow**) to verify.

Emails are sent to each user's username (email). The workflow fails if a **sync error** or a **real notification error** is reported; days where email is simply skipped (no new yield, or `send_email` off) are treated as success. Failures surface in the Actions run and Vercel logs.

## User registration & approval

New users can register from the login screen. Accounts are created with **`approved = false`** and cannot sign in until approved.

There is **no API to approve users** — approval is DB-only by design. In the Neon SQL editor:

```sql
-- List pending users
SELECT id, username, approved, created_at FROM users ORDER BY created_at;

-- Approve a user
UPDATE users SET approved = true WHERE username = 'their@example.com';
```

The first admin user (created from `ADMIN_USERNAME` / `ADMIN_PASSWORD` on first deploy) is auto-approved. `ADMIN_USERNAME` must be a valid email address.

**Forgot password?** There is no email reset. Logged-in users can change password in **Settings → Change password**. Otherwise an admin can set a new bcrypt hash directly in Neon (contact admin).

## Security

- No public self-approval — admin must run SQL in Neon
- HTTPS everywhere (Vercel)
- Passwords stored as bcrypt hashes
- Set a strong `ADMIN_PASSWORD` before first deploy

## Cost

$0/month on free tiers for personal use.
