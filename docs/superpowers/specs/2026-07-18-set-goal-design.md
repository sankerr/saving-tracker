# Set Goal — Design

**Date:** 2026-07-18
**Status:** Approved (pending implementation plan)

## Overview

Let a user set a **single savings goal**: a **target Total Wealth amount to reach
by a target date** (e.g. "₪1,000,000 by Dec 2030"). The dashboard shows a compact
progress strip directly under the existing "Total Wealth" headline, with an inline
"Set a goal" affordance to create/edit it.

Progress status is **projection-based**: the app projects Total Wealth forward to
the target date (using the existing projection engine) and compares the projected
value to the target to decide whether the user is "on pace," and by how much.

The goal tracks the **headline Total Wealth** number
(`portfolio.total_value_ils` = funds + RSU + ESPP + cash; **pension excluded**),
matching the big number at the top of the dashboard.

## Goals / Non-goals

**Goals**
- Single goal: target amount (ILS) + target date.
- Compact, inline display under the Total Wealth headline: progress bar + one status line.
- Inline, discoverable affordance to set/edit/clear the goal.
- Projection-based "on pace" status, plus the shortfall/surplus vs. target at the date.
- Fully bilingual (English + Hebrew), consistent with the rest of the UI.

**Non-goals (YAGNI)**
- Multiple goals or per-section / per-holding goals.
- Monthly-contribution goals.
- "Required extra monthly contribution to catch up" suggestions.
- Goal history, reminders, or notifications.
- Currency other than ILS (headline is ILS).

## Architecture & approach

**Key decision — compute status on the backend.** The "on pace" assessment
requires projecting Total Wealth to the target date, which may be far beyond the
dashboard's currently selected display horizon. The projection engine
(`compose_portfolio_projection`, per-holding returns + recurring contributions)
already lives in the backend. Computing status client-side would either duplicate
that math or be limited to the visible horizon. Therefore the backend owns the
computation.

### Storage
The goal lives in the existing per-user `settings` blob inside `data_json`
(JSONB) — no schema change or migration required.

```jsonc
// data_json.settings
{
  "yield_is_net_of_fees": true,
  "usdils_rate_override": null,
  "goal": {                      // null (or absent) when no goal is set
    "target_amount_ils": 1000000,
    "target_date": "2030-12-01"  // normalized to the 1st of the target month
  }
}
```

### Write path
Extend `update_settings(patch)` to accept a `goal` key:
- `null` → clears the goal.
- object → validated, then stored:
  - `target_amount_ils`: number > 0.
  - `target_date`: valid `YYYY-MM-DD`; normalized to the first of the month.
- Invalid payloads are rejected with `{ "ok": false, "error": ... }` and leave the
  stored goal unchanged.

The `goal` key is added to the whitelist in `update_settings` alongside
`yield_is_net_of_fees` and `usdils_rate_override`.

### Read path
In `compose_state`, when a goal is set, compute `months_remaining` from the current
month to the target month, project the portfolio to that horizon (capped at
`HORIZON_CAP_MONTHS` = 600), read the mean projected end value, and return a
`goal_status` object in the `/api/data` response.

### `goal_status` response shape

```json
{
  "target_amount_ils": 1000000,
  "target_date": "2030-12-01",
  "current_value_ils": 640000,
  "progress_pct": 64.0,
  "projected_value_ils": 1020000,
  "on_pace": true,
  "gap_ils": 20000,
  "months_remaining": 54
}
```

- `current_value_ils` = `portfolio.total_value_ils`.
- `progress_pct` = `current_value_ils / target_amount_ils * 100` (may exceed 100).
- `projected_value_ils` = mean projection path value at the target month; equals
  `current_value_ils` when no projection is available (no funds/grants).
- `on_pace` = `projected_value_ils >= target_amount_ils`.
- `gap_ils` = `projected_value_ils - target_amount_ils` (positive = surplus,
  negative = shortfall).
- `months_remaining` = whole months from the current month to the target month
  (`0` or negative → target date has passed).

When no goal is set, `goal_status` is `null` (or omitted).

## Frontend (compact, inline under the headline)

Rendered in `renderDashboard()` in a new element placed directly beneath the
`.dash-headline` block.

**States:**
- **No goal set** → a subtle affordance: `🎯 Set a goal`.
- **Goal set — on pace** → thin progress bar + status line, e.g.
  `🎯 ₪1,000,000 by Dec 2030 · 64% · On pace — projected ₪1.02M`.
- **Goal set — behind** → `🎯 ₪1,000,000 by Dec 2030 · 64% · Behind by ~₪80k`.
- **Reached** (current ≥ target) → `🎯 Goal reached! ₪1,000,000`.
- **Target date passed & not reached** → `🎯 Target date passed — reached 64%`.

**Editing:** clicking the strip (or an edit affordance) opens a small editor
(modal or inline) with an **amount** input and a **month/year** picker, plus
**Save** and **Clear** actions. Save calls `POST /api/settings` with a `goal`
object; Clear calls it with `goal: null`. On success the dashboard re-renders from
the refreshed `/api/data`.

**Progress bar:** fills to `min(progress_pct, 100)`; the label may still show the
true percentage when it exceeds 100.

**i18n:** all new strings added to `frontend/i18n.js` under both `en` and `he`,
following existing `dashboard.*` / `dash.*` key conventions. Verify RTL layout for
Hebrew.

## Edge cases
- No holdings / zero value → `progress_pct` 0; projection flat to current value.
- Projection `null` (no funds/grants) → `projected_value_ils = current_value_ils`.
- Target date in the past (`months_remaining <= 0`) → "target date passed" state;
  skip projection, show progress based on current value only.
- Target amount reached regardless of date → "reached" state.
- Progress bar caps visually at 100%; label can display the real percentage.

## Testing
- **Backend unit tests** for goal-status computation: on pace, behind, reached,
  past target date, no goal set, and cleared goal.
- **Backend validation tests** for `update_settings`: reject non-positive amount
  and malformed date; accept a valid goal and accept `null` to clear.
- **Manual QA:** set / edit / clear the goal via the UI in both English and
  Hebrew; confirm RTL layout and that the status matches the projection summary.
