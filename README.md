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
```

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
| `ADMIN_USERNAME` | `you` | Only used on first boot when DB has no users |
| `ADMIN_PASSWORD` | `...` | Strong password |

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
export ADMIN_USERNAME='you'
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

- `POST /api/login` — `{ "username", "password" }` → `{ "token" }`
- All other `/api/*` routes require `Authorization: Bearer <token>`
- `GET /api/health` — no auth (Render health checks)

## Security

- Single-user personal app — no public registration
- HTTPS everywhere (Render + Cloudflare)
- Passwords stored as bcrypt hashes
- Set a strong `ADMIN_PASSWORD` before first deploy

## Cost

$0/month on free tiers for personal use. Trade-off: Render cold starts after idle periods.
