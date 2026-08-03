# Bank Investments (ניירות ערך) Profit/Loss — Design

**Date:** 2026-08-03
**Status:** Approved / implemented

## Overview

Show lifetime profit/loss under each **ניירות ערך** (Bank Investment) row in the
same format as Funds:

```
557,772 ₪
+5,571 ₪ (+1.01%)
```

Cost basis is derived automatically from buy/sell/correction events × Maya NAV
on each event date, using **FIFO** lot accounting. The same P&L rolls into the
dashboard `total_profit_ils` / `total_invested_ils` chip.

## Goals / Non-goals

**Goals**
- Per-holding `profit_ils` / `profit_pct` on the row value subline (green/red).
- Cost basis from events × Maya daily NAV (compute-at-read; no new event fields required).
- FIFO for sells (and for correction down-deltas).
- Include Bank Investment P&L in dashboard totals.
- Use remaining cost basis for the educational cash-out tax estimate (25% on positive unrealized gain).
- Update chat/docs copy that currently says “no cost basis / P&L in v1”.

**Non-goals (YAGNI)**
- Manual purchase-price override UI.
- Persisting stamped NAV on events (optional later; v1 looks up Maya history at read time).
- Average-cost accounting.
- Changing buy/sell event form fields beyond what P&L needs.
- Tax advice or Israeli CPI / Section 102 specifics beyond the existing educational estimate.

## Architecture & approach

**Key decision — compute-at-read in `value_tase_fund`.** Maya daily history is
already cached in `MARKET['tase_fund_daily']`. Walking the holding’s event stream
on each portfolio compose avoids schema migration and stays consistent when
history is refreshed. No client-side cost math.

### NAV lookup

For an event date `D`:
1. Prefer the Maya close on `D`.
2. Else nearest prior trading-day close in that fund’s history.
3. If no prior close exists → that holding’s P&L fields are `null` (UI hides the subline; holding still contributes value to totals, but not profit/invested).

### Event → lot rules

Walk `_tase_sorted_events(holding)` chronologically:

| Kind | Behavior |
|------|----------|
| **buy** | Open a FIFO lot: `{units, unit_nav_ils, cost_ils = units × nav}`. |
| **sell** | Consume oldest lots first. Accrue `realized_gain_ils += (sell_nav − lot_nav) × qty`. |
| **correction** | Absolute target units. If target > current units → buy the delta at day’s NAV. If target < current → sell the delta FIFO. If equal → no-op. |

(This matches how corrections already recompute `units`, and how manual unit edits are recorded as corrections.)

Holdings with **no events** keep today’s static `units` for value, but P&L stays
`null` (no dated buy to price). In practice new holdings seed an initial `buy`
on create.

### Computed fields (per holding)

Added to the existing `computed` object from `value_tase_fund`:

| Field | Definition |
|-------|------------|
| `cost_basis_ils` | Sum of remaining FIFO lot costs |
| `realized_gain_ils` | Cumulative FIFO realized from sells / down-corrections |
| `profit_ils` | `(value_ils − cost_basis_ils) + realized_gain_ils` |
| `profit_pct` | `profit_ils / gross_buy_cost_ils` where `gross_buy_cost_ils` is the sum of costs of **all** buy lots ever opened (including fully sold). `null` if gross buy cost is 0 or NAV lookup failed |
| `invested_ils` | Alias of `cost_basis_ils` (remaining) for portfolio aggregation |

Unrealized gain alone is `value_ils − cost_basis_ils` (used by tax estimate).

### Dashboard portfolio totals

In `compute_portfolio` (or equivalent aggregation):

- `total_invested_ils` += sum of Bank Investment `cost_basis_ils` (skip holdings with null P&L).
- `total_profit_ils` += sum of Bank Investment `profit_ils` (same skip).
- Add `tase_funds_profit_ils` alongside existing `funds_profit_ils` / `rsu_profit_ils` / `espp_profit_ils`.

Dashboard chip math stays `profit_pct = total_profit_ils / total_invested_ils`.

### Cash-out tax estimate

Replace the “no cost basis in v1 / treat like cash” branch for Bank Investments:

- Taxable base = `max(0, value_ils − cost_basis_ils)` (unrealized only; realized already cashed).
- Rate 25%, same as other taxable funds / RSU / ESPP unrealized.
- If `cost_basis_ils` is null → keep 0 tax on that line and note missing cost basis.

### Frontend

In `renderBankInvestmentRow`, mirror Funds:

```html
<div class="holding-row__value">…</div>
<div class="holding-row__value-sub" style="color: …">+X ₪ (+Y%)</div>
```

Hide the subline when `profit_ils` is null. No new CSS required.

Detail panel: out of scope for this change (row subline only). Cost/realized can be added later.

### Docs / chat

- `CONTEXT.md`: note that Bank Investment P&L is FIFO from events × Maya NAV; units remain user/event-driven.
- `backend/chat.py` system copy: remove “no cost basis / true P&L in v1”; describe the new fields.
- Help text for ניירות ערך: one sentence that P&L uses event dates × Maya NAV (so wrong buy dates skew cost).

## Error / edge cases

- **Seeded initial buy dated “today”** while units were bought earlier → near-zero P&L until the user edits the buy date or adds real history. Document in help; no auto-guess of purchase date.
- **Weekend/holiday event date** → prior close (see NAV lookup).
- **Sell more than held** — already rejected by `add_tase_fund_event`; FIFO must not go negative.
- **Missing Maya history** → null P&L; value can still show if a later price exists.
- **Archived / excluded holdings** — same dashboard inclusion rules as today (`archived` out; `included_in_dashboard` respected for totals).

## Testing

Backend (`test_tase_fund_valuation.py` or sibling):

1. Single buy then price rise → positive unrealized; `profit_pct` matches.
2. Buy, partial sell above cost, remainder → realized + unrealized sum to `profit_ils`.
3. Correction up/down behaves as buy/sell delta.
4. Event on non-trading day uses prior close.
5. No usable NAV → `profit_ils` is null.
6. Portfolio totals include tase profit/invested.

Frontend: smoke that the subline renders when `computed.profit_ils` is present (manual or existing pattern; no new harness required unless one already covers fund rows).

## Out of scope reminders

- Do not change what-if growth (Bank Investments stay flat there).
- Do not change historical NAV mean projection on the detail chart.
