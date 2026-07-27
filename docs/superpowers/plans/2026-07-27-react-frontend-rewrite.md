# React Frontend Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vanilla `frontend/index.html` monolith with a Vite + React + TypeScript SPA at feature parity, with Playwright E2E-first tests and Vitest for pure logic.

**Architecture:** Big-bang rewrite under `frontend/`. Auth gate + AppShell with scroll sections and pill scrollspy. Portfolio context loads `GET /api/data` and refetches after mutations. API base from `VITE_API_BASE`. Old vanilla sources move to `frontend/legacy/` for reference during the port, then are deleted at cutover.

**Tech Stack:** Vite, React 19, TypeScript, React Router (auth vs app only), Chart.js + react-chartjs-2, Vitest, Playwright, Cloudflare Pages build.

## Global Constraints

- Preserve existing REST API contracts (no backend changes).
- Keep localStorage keys: `st_token`, `st_theme`, `st_lang`, `st_disclaimer_ack`, `saving_what_if_pct`.
- Keep section anchor ids: `dashboard-card`, `funds-card`, `pension-card`, `retirement-simulator-card`, `rsu-card`, `espp-card`, `cash-card`, `settings-card`.
- E2E-first: Playwright journeys mock the API; Vitest only for pure modules.
- `frontend/presentation/` remains available (copy into Vite `public/presentation`).
- Spec: `docs/superpowers/specs/2026-07-27-react-frontend-rewrite-design.md`.

## File structure (target)

```text
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  tsconfig.app.json
  tsconfig.node.json
  index.html
  public/
    presentation/          # copied from existing presentation/
  e2e/
    auth.spec.ts
    dashboard.spec.ts
    holdings.spec.ts
    settings-i18n.spec.ts
    chat-insights.spec.ts
    fixtures/
      portfolio.json
  src/
    main.tsx
    App.tsx
    vite-env.d.ts
    styles/
      tokens.css
      global.css
    api/
      client.ts
      types.ts
      auth.ts
      portfolio.ts
    auth/
      AuthPage.tsx
      token.ts
    i18n/
      index.ts
      en.ts
      he.ts
      I18nProvider.tsx
    theme/
      ThemeProvider.tsx
    portfolio/
      PortfolioProvider.tsx
      types.ts
    shell/
      AppShell.tsx
      TopChrome.tsx
      Disclaimer.tsx
      SectionNav.tsx
      StatusPill.tsx
      ToastStack.tsx
      LoadingBar.tsx
    chat/
      ChatDrawer.tsx
    sections/
      dashboard/
      funds/
      pension/
      retirement/
      rsu/
      espp/
      cash/
      settings/
    lib/
      format.ts
      format.test.ts
  legacy/                  # moved vanilla sources during port; delete at cutover
```

---

### Task 1: Scaffold Vite + React + TS and park legacy sources

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig*.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/vite-env.d.ts`, `frontend/src/styles/tokens.css`, `frontend/src/styles/global.css`
- Move: `frontend/index.html` → `frontend/legacy/index.html` (vanilla), plus `i18n.js`, `config.js`, `pension-retirement-sim.js`
- Copy: `frontend/presentation/` → `frontend/public/presentation/`
- Modify: `README.md` deploy section (Pages build command / output) — can wait until Task 10 if preferred; include a short note in this task’s commit body that deploy docs follow at cutover

**Interfaces:**
- Produces: Vite app that runs `npm run dev` and shows a placeholder “Saving Tracker” shell
- Produces: `import.meta.env.VITE_API_BASE` typed in `vite-env.d.ts`

- [ ] **Step 1: Move vanilla sources into `legacy/` and copy presentation into `public/`**

```bash
cd frontend
mkdir -p legacy public
git mv index.html legacy/index.html
git mv i18n.js legacy/i18n.js
git mv config.js legacy/config.js
git mv pension-retirement-sim.js legacy/pension-retirement-sim.js
cp -R presentation public/presentation
```

- [ ] **Step 2: Create `package.json`**

```json
{
  "name": "saving-tracker-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
  },
  "dependencies": {
    "chart.js": "^4.4.1",
    "react": "^19.1.0",
    "react-chartjs-2": "^5.3.0",
    "react-dom": "^19.1.0",
    "react-router-dom": "^7.6.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.52.0",
    "@types/react": "^19.1.0",
    "@types/react-dom": "^19.1.0",
    "@vitejs/plugin-react": "^4.4.1",
    "jsdom": "^26.1.0",
    "typescript": "~5.8.3",
    "vite": "^6.3.5",
    "vitest": "^3.1.4"
  }
}
```

- [ ] **Step 3: Add Vite/TS config and minimal app**

`vite.config.ts`:

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  preview: { port: 4173 },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
```

`index.html` (new Vite entry at `frontend/index.html`):

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#F4F5F8" id="meta-theme-color" />
    <title>Saving Tracker</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`src/App.tsx`:

```tsx
export default function App() {
  return (
    <main>
      <h1>Saving Tracker</h1>
      <p>React rewrite in progress.</p>
    </main>
  );
}
```

`src/main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/tokens.css';
import './styles/global.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Extract CSS variables from `legacy/index.html` `:root` / dark theme into `src/styles/tokens.css`. Put base body rules into `src/styles/global.css`.

- [ ] **Step 4: Install and verify build**

```bash
cd frontend && npm install && npm run build
```

Expected: `dist/` created; exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend README.md 2>/dev/null || true
git commit -m "chore: scaffold Vite React TypeScript frontend"
```

---

### Task 2: Vitest + Playwright harness with first green tests

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/e2e/smoke.spec.ts`, `frontend/src/lib/format.ts`, `frontend/src/lib/format.test.ts`
- Modify: `frontend/package.json` (already has scripts), `.github/workflows/frontend-ci.yml`

**Interfaces:**
- Produces: `fmtIls(n: number, lang: 'en' | 'he'): string` and `fmtPct(n: number, digits?: number): string`
- Produces: Playwright config that serves `vite preview` and runs `e2e/`

- [ ] **Step 1: Write failing Vitest for formatters**

`src/lib/format.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { fmtIls, fmtPct } from './format';

describe('fmtIls', () => {
  it('formats ILS with shekel sign', () => {
    expect(fmtIls(1234.5, 'en')).toMatch(/1,234/);
  });
});

describe('fmtPct', () => {
  it('formats percent with fixed digits', () => {
    expect(fmtPct(12.345, 1)).toBe('12.3%');
  });
});
```

- [ ] **Step 2: Run Vitest — expect fail**

```bash
cd frontend && npm test
```

Expected: FAIL — module not found / functions missing.

- [ ] **Step 3: Implement `format.ts` to pass**

Port behavior from `legacy/index.html` `fmt*` helpers (match existing rounding/sign conventions as you port; start with minimal correct implementations, refine when dashboard ports).

- [ ] **Step 4: Add Playwright smoke test**

`playwright.config.ts`:

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
```

`e2e/smoke.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

test('home renders app title', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Saving Tracker' })).toBeVisible();
});
```

- [ ] **Step 5: Install browsers and run E2E**

```bash
cd frontend && npx playwright install chromium && npm run test:e2e
```

Expected: PASS.

- [ ] **Step 6: Add `.github/workflows/frontend-ci.yml`**

```yaml
name: frontend-ci
on:
  pull_request:
    paths: ['frontend/**']
  push:
    branches: [main, feat/react-frontend-rewrite]
    paths: ['frontend/**']
jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm test
      - run: npx playwright install --with-deps chromium
      - run: npm run test:e2e
```

- [ ] **Step 7: Commit**

```bash
git commit -m "test: add Vitest formatters and Playwright smoke harness"
```

---

### Task 3: API client + auth token helpers (unit-tested)

**Files:**
- Create: `frontend/src/api/client.ts`, `frontend/src/api/client.test.ts`, `frontend/src/auth/token.ts`, `frontend/src/auth/token.test.ts`, `frontend/src/api/types.ts`

**Interfaces:**
- Produces:
  - `getToken(): string` / `setToken(token: string): void` using `st_token`
  - `apiUrl(path: string): string` using `import.meta.env.VITE_API_BASE`
  - `api<T>(method, path, body?, opts?): Promise<T & { ok?: boolean; error?: string }>` with Bearer header, 401 → `onUnauthorized`, 5xx retry once after 3s

- [ ] **Step 1: Write token + apiUrl unit tests** (use Vitest; mock `localStorage` / env).
- [ ] **Step 2: Implement until green.**
- [ ] **Step 3: Commit** `feat: add API client and auth token helpers`

---

### Task 4: i18n + theme providers

**Files:**
- Create: `frontend/src/i18n/en.ts`, `he.ts`, `index.ts`, `I18nProvider.tsx`, `frontend/src/theme/ThemeProvider.tsx`
- Port strings from `frontend/legacy/i18n.js` into `en.ts` / `he.ts` (can be a mechanical extract).

**Interfaces:**
- `useT(): (key: string, vars?: Record<string, string | number>) => string`
- `useLang(): { lang: 'en' | 'he'; setLang(lang: 'en' | 'he'): void }`
- Theme: `system | light | dark` in `st_theme`; sets `document.documentElement.dataset.theme` and `colorScheme`

- [ ] **Step 1: Vitest for `t()` interpolation and lang persistence.**
- [ ] **Step 2: Implement providers; wrap app in `main.tsx`.**
- [ ] **Step 3: Commit** `feat: port i18n and theme providers`

---

### Task 5: Auth page + route gate + Playwright auth journey

**Files:**
- Create: `frontend/src/auth/AuthPage.tsx`, `frontend/src/App.tsx` (routes), `frontend/e2e/auth.spec.ts`, `frontend/e2e/fixtures/handlers.ts`

**Interfaces:**
- Routes: `/login` (unauthenticated), `/` (app shell, requires token)
- `POST /api/login` → `{ ok: true, token }` ; `POST /api/register` → `{ ok: true, message }`

- [ ] **Step 1: Write Playwright auth.spec** with route mocks for login/register; assert login → main, logout → login, register shows toast/message path.
- [ ] **Step 2: Implement AuthPage + gate until E2E passes.**
- [ ] **Step 3: Commit** `feat: add auth page and E2E auth journey`

---

### Task 6: Portfolio provider + AppShell chrome (nav, disclaimer, status, loading)

**Files:**
- Create: `frontend/src/portfolio/PortfolioProvider.tsx`, `frontend/src/shell/*`, `frontend/e2e/dashboard.spec.ts` (initial load + nav smoke), `frontend/e2e/fixtures/portfolio.json`

**Interfaces:**
- `usePortfolio(): { data, status, error, reload, sync, setWhatIfPct }`
- `GET /api/data?horizon=...` mocked in E2E with fixture shaped like current API payload (capture a representative response from legacy usage / backend types if available)

- [ ] **Step 1: Add portfolio fixture + E2E: after login, dashboard heading visible, section pills exist, click Funds scrolls.**
- [ ] **Step 2: Implement provider + shell until E2E passes (section bodies can be placeholders with correct ids).**
- [ ] **Step 3: Commit** `feat: add portfolio provider and app shell`

---

### Task 7: Dashboard section (charts, goal, insight, what-if)

**Files:**
- Create: `frontend/src/sections/dashboard/*`, extend `e2e/dashboard.spec.ts`

Port rendering logic from `legacy/index.html` `renderDashboard`, `renderGoal`, `renderAllocation`, insights loaders. Keep Chart.js behavior.

- [ ] **Step 1: Extend E2E assertions for total wealth, goal strip, insight card (mocked `/api/insights`).**
- [ ] **Step 2: Implement dashboard until E2E passes.**
- [ ] **Step 3: Commit** `feat: port dashboard section`

---

### Task 8: Holdings sections — Funds, Pension, RSU, ESPP, Cash

**Files:**
- Create: `frontend/src/sections/{funds,pension,rsu,espp,cash}/*`, `frontend/e2e/holdings.spec.ts`

Port list/detail/add-panel CRUD. Each mutation calls existing REST paths then `reload()`.

- [ ] **Step 1: Playwright CRUD happy-path per asset class with mocked GET/POST/PUT/DELETE.**
- [ ] **Step 2: Implement sections until E2E passes.**
- [ ] **Step 3: Commit** `feat: port holdings sections`

---

### Task 9: Retirement simulator + Settings + Chat

**Files:**
- Create: `frontend/src/sections/retirement/*` (port `legacy/pension-retirement-sim.js`), `frontend/src/sections/settings/*`, `frontend/src/chat/ChatDrawer.tsx`, `frontend/e2e/settings-i18n.spec.ts`, `frontend/e2e/chat-insights.spec.ts`

- [ ] **Step 1: E2E — theme toggle, lang en↔he (dir=rtl), settings save mocked; chat open/send mocked `/api/chat`.**
- [ ] **Step 2: Implement until E2E passes; Vitest for retirement pure math extracted from sim.**
- [ ] **Step 3: Commit** `feat: port retirement, settings, and AI chat`

---

### Task 10: Cutover — remove legacy, update deploy docs, parity checklist

**Files:**
- Delete: `frontend/legacy/**`
- Modify: `README.md` (Cloudflare build: `cd frontend && npm ci && npm run build`, output `frontend/dist`; document `VITE_API_BASE`)
- Modify: `render.yaml` / CORS notes only if README examples change

- [ ] **Step 1: Run full `npm test && npm run test:e2e && npm run build`.**
- [ ] **Step 2: Remove `legacy/`; ensure `public/presentation` still builds.**
- [ ] **Step 3: Update README; tick parity checklist in the design spec.**
- [ ] **Step 4: Commit** `chore: cut over to React frontend and update deploy docs`

---

## Execution notes

- Prefer porting behavior from `frontend/legacy/` over inventing new UX.
- When API payload types are unclear, define narrow TypeScript interfaces for fields the UI reads; widen as sections land.
- Keep commits frequent per task.
- Do not commit secrets; use `.env.example` with `VITE_API_BASE=https://saving-tracker-qw3n.onrender.com`.
