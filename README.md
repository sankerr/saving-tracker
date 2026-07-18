# Saving Tracker (Cloud)

Personal portfolio tracker deployed on the public internet with a free stack:

| Layer | Service | Role |
|-------|---------|------|
| Frontend | [Cloudflare Pages](https://pages.cloudflare.com) | Static HTML/JS CDN |
| Backend | [Render](https://render.com) | Docker Python API |
| Database | [Neon](https://neon.tech) | PostgreSQL (JSONB storage) |

The original local/Kubernetes version lives at [sankerr/saving-tracker](https://github.com/sankerr/saving-tracker).

## Architecture

```
Browser → Cloudflare Pages (frontend)
       → Render API (backend Docker)
       → Neon PostgreSQL
       → data.gov.il + Yahoo Finance (sync)
       → Google Gemini (optional AI chat + in-app insight card + new-yield email insights)
       → Resend (optional new-yield email delivery)
```

Tracks provident/education funds (gemelnet), pension (pensia-net), RSU, ESPP, and cash, with dashboard projections/what-if, a savings goal, a Hebrew/English UI, and an optional AI chat assistant.

## Prerequisites

- GitHub repo connected to Render and Cloudflare Pages
- Neon project with a PostgreSQL database
- Existing portfolio JSON files (optional, for migration)

## 1. Neon — create database

1. Create a project at [neon.tech](https://neon.tech)
2. Copy the **pooled** connection string (`DATABASE_URL`)
3. Tables are created automatically on first backend boot

## 2. Render — deploy backend

1. In Render: **New → Blueprint** (or Web Service → Docker)
2. Connect this GitHub repo
3. If using Blueprint, Render reads [`render.yaml`](render.yaml)
4. Set environment variables:

| Variable | Example | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql://...` | Neon pooled connection string |
| `SESSION_SECRET` | random 32+ chars | JWT signing secret |
| `CORS_ORIGIN` | `https://your-app.pages.dev` | Your Cloudflare Pages URL (no trailing slash) |
| `ADMIN_USERNAME` | `you@example.com` | Valid email; only used on first boot when DB has no users |
| `ADMIN_PASSWORD` | `...` | Strong password |
| `CRON_SECRET` | random 32+ chars | Protects `POST /api/cron/sync` (GitHub Actions daily job) |
| `RESEND_API_KEY` | `re_...` | [Resend](https://resend.com) API key for the new-yield email (optional) |
| `NOTIFY_FROM` | `Saving Tracker <onboarding@resend.dev>` | Verified sender in Resend |
| `CHAT_ENABLED` | `1` | Enable the in-app AI chat assistant (optional; requires `GEMINI_API_KEY`) |
| `GEMINI_API_KEY` | `AIza...` | [Google Gemini](https://ai.google.dev) API key; powers AI chat, the in-app dashboard insight card, and new-yield email insights (optional) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Gemini model override (optional; defaults to `gemini-3.1-flash-lite`) |

5. Deploy and note the public URL, e.g. `https://saving-tracker-api.onrender.com`

**Free tier note:** Backend sleeps after 15 minutes of inactivity. First request takes ~30–50 seconds.

## 3. Cloudflare Pages — deploy frontend

1. **Workers & Pages → Create → Connect to Git**
2. Select this repo
3. Build settings:
   - **Build command:** *(leave empty)*
   - **Build output directory:** `frontend`
4. Deploy
5. Edit [`frontend/config.js`](frontend/config.js) and set your Render URL:

```javascript
window.API_BASE = 'https://saving-tracker-api.onrender.com';
```

6. Commit and push — Pages redeploys automatically
7. Set `CORS_ORIGIN` on Render to your Pages URL (`https://xxx.pages.dev`)

## 4. Migrate existing data (optional)

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

If the user already exists (created by Render on first boot), the script updates their data in place.

## 5. Verify

1. Open your Cloudflare Pages URL
2. Sign in with your username/password
3. Confirm portfolio loads
4. Run **Sync** — may be slow on first request if backend was asleep
5. Add a test holding, refresh, confirm it persists

## Local development

```bash
cd backend
pip install -r requirements.txt

export DATABASE_URL='postgresql://...'
export SESSION_SECRET='dev-secret-change-me'
export CORS_ORIGIN='http://localhost:3000'
export ADMIN_USERNAME='dev'
export ADMIN_PASSWORD='dev'

python3 saving_tracker.py
```

```bash
cd frontend
# Edit config.js: window.API_BASE = 'http://localhost:8000'
python3 -m http.server 3000
```

## API auth

- `POST /api/login` — `{ "username", "password" }` → `{ "token" }` (approved users only; username must be a valid email)
- `POST /api/register` — `{ "username", "password" }` → creates account with `approved=false` (username must be a valid email)
- `POST /api/account/password` — `{ "current_password", "new_password" }` (change password while logged in)
- `DELETE /api/account` — `{ "password" }` (delete account and all portfolio data)
- All other `/api/*` routes require `Authorization: Bearer <token>`
- `GET /api/chat/status` — `{ "enabled": bool }` (whether AI chat is configured)
- `POST /api/chat` — `{ "messages": [...] }` → `{ "reply" }` (AI assistant; `404` when chat is disabled)
- `GET /api/insights` — `{ "insights", "generated_at", "cached" }` for the dashboard AI insight card (`ok:false, error:"insights_disabled"` without `GEMINI_API_KEY`; cached per day **and per language**, `?lang=en|he` picks the output language, `?refresh=1` forces regeneration)
- `GET /api/version` — `{ "version" }`
- `GET /api/health` — no auth (Render health checks)
- `POST /api/cron/sync` — daily sync trigger; requires `Authorization: Bearer <CRON_SECRET>` (returns `202`). Optional `?email=0` (also `false`/`no`/`off`) runs the sync **without** sending emails.
- `GET /api/cron/status` — cron job status; requires `Authorization: Bearer <CRON_SECRET>`

## Daily sync & email alerts

A GitHub Actions workflow (`.github/workflows/daily-sync.yml`) triggers `POST /api/cron/sync` every day at **08:05 Asia/Jerusalem** (05:05 UTC). This works on Render's free tier — the HTTP request wakes the sleeping service and syncs all approved users.

Email is sent **only when a new monthly fund yield is published** — i.e. when `latest_published_period` advances past the last period a user was notified about. On days with no new yield the sync still runs but no email goes out. When a new yield is detected, each approved user is emailed a **dashboard snapshot** (totals, holdings, and short AI insights) and `last_notified_period` is advanced only after a successful send.

**Email toggle:** the `send_email` input on **Actions → Daily sync → Run workflow** controls whether emails are sent for a manual run (default `true`). Scheduled runs always allow email. Internally the workflow passes `?email=0` to the cron endpoint when the toggle is off, so you can trigger a data-only sync without notifying users.

**One-time setup:**

1. Ensure usernames in Neon are valid emails. If your admin account uses a non-email username, update it:
   ```sql
   UPDATE users SET username = 'you@example.com' WHERE username = 'admin';
   ```
2. Create a [Resend](https://resend.com) account, verify a sender domain (or use Resend's test sender), and set `RESEND_API_KEY` + `NOTIFY_FROM` on Render.
3. Set `GEMINI_API_KEY` on Render for AI insights in the email. Without it, sync and email still work — the insights section falls back to a static message. (`CHAT_ENABLED` is only needed for the in-app chat, not the email.)
4. Copy Render's `CRON_SECRET` value into GitHub repo **Settings → Secrets → Actions** as `CRON_SECRET`, and add `RENDER_API_URL` (e.g. `https://saving-tracker-api.onrender.com`).
5. Deploy, then run the workflow manually (**Actions → Daily sync → Run workflow**) to verify.

Emails are sent to each user's username (email). The workflow fails if a **sync error** or a **real notification error** is reported; days where email is simply skipped (no new yield, or `send_email` off) are treated as success. Failures surface in the Actions run and Render logs.

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
- HTTPS everywhere (Render + Cloudflare)
- Passwords stored as bcrypt hashes
- Set a strong `ADMIN_PASSWORD` before first deploy

## Cost

$0/month on free tiers for personal use. Trade-off: Render cold starts after idle periods.
