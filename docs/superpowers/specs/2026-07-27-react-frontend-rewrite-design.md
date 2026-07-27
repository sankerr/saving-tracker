# React Frontend Rewrite — Design

**Date:** 2026-07-27  
**Status:** Approved  
**Scope:** Frontend only. Backend API, Neon, Render, Resend, Gemini stay as-is. `frontend/presentation/` stays a separate static page (out of scope).

## Overview

Replace the monolithic vanilla `frontend/index.html` (~7k lines of CSS/markup/JS) with a **Vite + React + TypeScript** SPA that preserves today’s product and UX: a vertical-scroll personal portfolio tracker with sticky chrome, section pill-nav, **Hebrew-only RTL UI**, theme, holdings CRUD, goal, AI chat, and insights.

Drivers: editing pain in the mega-file, and a maintainable base for more of the same UI work (widgets, holdings flows, charts, chat polish) — not a multi-app platform.

## Goals / Non-goals

**Goals**
- Feature parity with the current SPA (auth, dashboard, funds, pension, retirement sim, RSU, ESPP, cash, settings, goal, chat, insights, theme, sync/loading), with all UI copy in Hebrew.
- Clear module/component boundaries so day-to-day edits touch small files.
- Cloudflare Pages deploy with a Vite build (`API_BASE` via env).
- **E2E-first test strategy** (Playwright journeys + Vitest for pure logic only).

**Non-goals**
- Backend changes, new API shapes, or schema migrations.
- English UI, language toggle, or LTR layout support.
- Visual redesign or new product features beyond parity.
- Hard line-coverage % gate, visual regression, or full component-test suite for every widget.
- Converting section nav into a multi-route tabbed SPA (keep scroll + scrollspy).
- Rewriting `frontend/presentation/`.
- Redux/Zustand or a heavy state framework for v1.

## Architecture

```text
Browser
  └─ React app (auth gate)
       ├─ Login / Register
       └─ AppShell (chrome, disclaimer, section nav, chat drawer)
            └─ scroll sections: Dashboard → Funds → Pension → Retirement
               → RSU → ESPP → Cash → Settings
                 └─ API client → existing Render backend
```

**Stack**
- Vite + React 19 + TypeScript
- React Router only for auth vs app shell (not per-section routes)
- Portfolio data via React context + refetch after mutations (mirrors today’s `fetch /api/data` → `renderAll`)
- Chart.js via `react-chartjs-2`
- **Locale: Hebrew only.** `html lang="he" dir="rtl"` always. Copy lives in a single `src/copy/he.ts` (or inline in components where local); no language toggle, no `st_lang`, no English dictionary.
- Theme: `st_theme` (`system` | `light` | `dark`) applied to `data-theme` before paint where practical
- Auth token: `localStorage` key `st_token` (same as today)
- Config: `import.meta.env.VITE_API_BASE` (replaces hand-edited `config.js`)
- API `lang` query params (insights/chat) always send `he`

**Deploy**
- Vite root: `frontend/`
- Cloudflare Pages: build `npm ci && npm run build`, output `frontend/dist` (or Pages root = `frontend` with output `dist`)
- Update README deploy instructions accordingly
- CORS on Render still points at the Pages URL

**Migration**
- Big-bang rewrite to parity, then cut over. No long dual-stack period.
- Keep the old `index.html` / `i18n.js` in git history; remove from the live Pages output once React app is the entry.

## Components

| Area | Responsibility |
|------|----------------|
| `api/` | `apiUrl`, `api()`, auth helpers, typed fetch wrappers for existing endpoints |
| `auth/` | Login/register forms, token gate, logout, change-password |
| `copy/` | Hebrew UI strings module (optional `t()` helper for interpolation only) |
| `theme/` | Preference + apply theme |
| `portfolio/` | `PortfolioProvider`, load/sync, derived selectors used by sections |
| `shell/` | Top chrome, status pill, disclaimer, section pill-nav (scrollspy), toasts, loading indicator |
| `chat/` | Drawer UI, thread, send/clear (API mocked in E2E) |
| `sections/dashboard/` | Totals, allocation, charts, goal strip, AI insight card, what-if |
| `sections/funds/` | List, detail, add/edit/delete, search |
| `sections/pension/` | Same pattern + retirement note |
| `sections/retirement/` | Port of `pension-retirement-sim.js` |
| `sections/rsu/`, `espp/`, `cash/` | List + detail + CRUD panels |
| `sections/settings/` | Yield/fees, FX override, import/export, account, cache clear |
| `lib/format/` | Money/pct/date formatters (unit-tested) |
| `lib/math/` | Pure portfolio/display helpers extracted where logic is non-trivial |

Preserve existing section card ids (or equivalent anchors) so pill-nav targets stay stable: `dashboard-card`, `funds-card`, `pension-card`, `retirement-simulator-card`, `rsu-card`, `espp-card`, `cash-card`, `settings-card`.

## Data flow

1. Boot → read `st_token`. Missing → login screen.
2. Authenticated → `GET /api/data?...` (same query params as today) → store portfolio payload in context → render sections.
3. Mutations (CRUD, settings, goal, sync) → call existing REST endpoints → refetch `/api/data` (or patch context only where today’s code already does optimistic local updates; prefer refetch for parity simplicity unless UX requires otherwise).
4. Chat / insights → separate endpoints; failures do not wipe portfolio state.
5. Client prefs in `localStorage`: `st_token`, `st_theme`, `st_disclaimer_ack`, `saving_what_if_pct` (no `st_lang`).

## Error handling

- **401** from API → clear token, return to login, toast if appropriate.
- **Network / 5xx / cold-start** → status pill + prominent loading (existing “Waking server…” behavior); retries as today’s `api()` does.
- **Validation / 4xx** on forms → inline or toast with server message.
- **Chat / insights** → soft-fail in-panel error; rest of app usable.
- **E2E** → Playwright route mocks for API so CI never depends on Render/Neon/Gemini.

## Testing (E2E-first)

**Playwright** (`frontend/e2e/`)
- Against Vite preview build; PR CI blocking once suite is established.
- Must-cover journeys: auth (login/register/logout/change password); cold load/sync + dashboard totals; section nav + scrollspy (RTL); CRUD for funds/pension/RSU/ESPP/cash; goal set/edit/clear; settings theme/export-import; AI chat open/send (mocked); insights load/refresh (mocked).
- Mock APIs via Playwright network interception for v1 CI.
- Assert `document.documentElement` has `lang=he` and `dir=rtl`.

**Vitest** (`frontend/src/**/*.test.ts`)
- Pure modules only: formatters (Hebrew/`he-IL` locale), retirement sim math, API mappers/parsers.
- No requirement to unit-test every React component.

**Not in v1:** coverage % gate, Percy/visual regression, Testing Library suite for every widget.

## Parity checklist (cutover gate)

- [x] Login / register / logout / change password
- [x] Dashboard totals, allocation, charts, what-if, goal, insight card
- [x] Funds / pension / RSU / ESPP / cash CRUD + search/detail
- [x] Retirement simulator
- [x] Settings (yield net of fees, FX override, import/export, cache)
- [x] Sync + cold-start loading UX
- [x] Hebrew-only RTL (`lang=he` `dir=rtl`), theme system/light/dark
- [x] Section pill-nav + scrollspy
- [x] AI chat drawer
- [x] Disclaimer ack
- [x] Playwright journeys green in CI; Vitest pure-logic suite green
- [x] Cloudflare Pages build docs updated

## Decisions log

| Decision | Choice |
|----------|--------|
| Framework | React 19 + TypeScript + Vite |
| Migration style | Big-bang rewrite to parity |
| In-app nav | Keep scroll + pill scrollspy (not route-per-section) |
| Global state | Context + refetch; no Redux/Zustand v1 |
| Charts | Chart.js + react-chartjs-2 |
| Tests | E2E-first Playwright; Vitest for pure logic only |
| Config | `VITE_API_BASE` env |
| Presentation site | Out of scope |
| UI language | Hebrew only (no English / no lang toggle) |


## Remaining known thin areas (acceptable vs legacy polish)

- Dashboard chart range drag-select / month-range inputs (horizon chips + what-if present)
- Chat markdown rendering is plain text (API replies still shown)
- Some fund metrics / sparklines / analyst-target polish from legacy are simplified in React charts
