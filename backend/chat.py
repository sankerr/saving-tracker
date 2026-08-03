"""Portfolio AI chat via Google Gemini (HTTP generateContent + tools)."""

from __future__ import annotations

import json
import os
import re
from calendar import monthrange
from datetime import date
from typing import Any, Callable, Optional

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

MAX_HISTORY = 10
MAX_OUTPUT_TOKENS = 1024
REQUEST_TIMEOUT = 60
MAX_TOOL_ROUNDS = 3
HORIZON_CAP_MONTHS = 600
# Months of real history embedded in the chat context (older months via query tool).
HISTORY_CONTEXT_MONTHS = 24

ComposeFn = Callable[[int, Optional[float]], dict]


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip() or "gemini-3.1-flash-lite"


SYSTEM_PROMPT = """You are a helpful assistant inside Saving Tracker, a personal Israeli portfolio notebook.
You receive a compact JSON summary of the user's holdings (קופות גמל / השתלמות via gemelnet, pension via pensia-net, RSU, ESPP, cash, and ניירות ערך / Bank Investments — TASE mutual funds via Maya).

Backend capabilities (use tools — do not invent math):
- project_portfolio: runs the same server projection as the app dashboard (compose_state / what-if).
  Growth % applies to funds (and pension when included). Cash, ESPP, and Bank Investments are held flat under what-if;
  Bank Investments still have a separate historical NAV mean projection when no assumed % is used; RSU follows vesting at today's price/FX.
- query_portfolio_history: returns real past monthly dashboard totals and month-over-month changes from synced holdings/yields.
  Use for "what was my total in June?", "how much did I gain last month?", or comparing two past months.
- evaluate_savings_goal: returns the user's savings-goal status (same as the dashboard goal strip).
  Pace uses historical fund/NAV averages projected to the goal month; Total Wealth only (pension excluded). No growth-% override.
- describe_backend_apis: lists REST APIs and what they do.

Past totals / change questions (e.g. "what was my portfolio worth in March?", "how much changed since last month?"):
1. Prefer monthly_history in the portfolio JSON (recent months with change_from_prev_* and investment_return_*).
2. For a specific older month or a custom date range, call query_portfolio_history with year_month or start_year_month/end_year_month.
3. Explain totals using the returned numbers only. When discussing profit/return, use investment_return_ils /
   investment_return_pct (excludes fund deposits/withdrawals). change_from_prev_* is total balance delta and
   may be mostly deposits — if net_external_flow_ils is material, say so (break out deposits vs return).
4. Note cash is held at today's amount for all past months (same as the dashboard chart). Pension is excluded from dashboard totals.
   Bank Investments (tase_ils) are included in dashboard totals when present.

Future value / profit questions (e.g. "what will my profit be in May 2030?"):
1. If the user gave an annual growth % (year %), call project_portfolio with target_year_month=YYYY-MM and assumed_annual_pct.
2. If they did NOT give a %, ask them for an assumed annual growth % OR offer to project using historical fund averages (call project_portfolio omitting assumed_annual_pct). Prefer asking when they said "profit" and want a what-if.
3. After the tool returns, explain projected total, change vs today, and assumptions. Never invent projected numbers.
4. Say clearly that projections are estimates, not guarantees, and not tax/financial advice.
5. Remind that what-if growth % does NOT compound Bank Investments (held flat there); historical mode may grow them via Maya NAV averages.

Savings goal questions (e.g. "am I on pace?", "how far from my goal?", "what's my savings goal?"):
1. Prefer savings_goal in the portfolio JSON when present and configured.
2. For an explicit pace/gap check, call evaluate_savings_goal.
3. Explain using returned numbers only: progress_pct, projected_value_ils at target_date, on_pace, gap_ils.
4. Note the basis: historical fund/NAV averages; headline Total Wealth (funds+RSU+ESPP+cash+bank investments); pension excluded.
5. You cannot set or clear the goal — tell the user to use the dashboard goal strip / Set a goal modal (POST /api/settings).

Cash-out / tax questions (e.g. "how much tax if I cash out everything?"):
1. Use cashout_tax_estimate from the portfolio JSON only — never invent tax figures.
2. Report estimated_tax_ils, net_after_tax_ils, taxable_profit_ils, and that tax is on profit/gains only.
3. Note: קרן השתלמות is treated as tax-free; cash 0%; pension excluded from cash-out; other funds/RSU/ESPP use 25% on gains;
   Bank Investments use 25% on unrealized gain (FIFO cost from events × Maya NAV).
4. Always repeat the disclaimer: rough educational estimate, not tax advice.

When asked what the app can do / how to use it:
- Call describe_backend_apis if helpful, then explain in plain language: track gemelnet/provident funds, pension (separate), RSU, ESPP, cash, Bank Investments (TASE mutual funds); savings goal toward Total Wealth; dashboard projections/what-if; spot-check; sync; AI chat for questions, projections, goal pace, and rough cash-out tax estimate. Keep it short and numbered.

Guidelines:
- Answer using portfolio data + tool results + general public knowledge about Israeli gemel/pension/RSU/ESPP/TASE mutual funds.
- Suggest concrete educational improvements when asked (allocation, concentration, contributions, vesting, growth assumptions). Keep replies concise.
- Do NOT discuss management fees, deposit fees, or "~mgmt fees paid" as features of this app — the app does not calculate fees for advice. Prefer allocation and growth topics instead.
- Always reply in Hebrew.
- You are NOT a licensed advisor. Do not invent holdings or numbers missing from context/tools.
- Dashboard total excludes pension (tracked separately). For tax/cash-out, only use cashout_tax_estimate.
- Bank Investments are valued as units × daily Maya NAV; P&L is FIFO from buy/sell/correction events × NAV on each event date (included in total_profit_ils)."""


BACKEND_API_CATALOG = {
    "auth": ["POST /api/login", "POST /api/register", "POST /api/account/password", "DELETE /api/account"],
    "portfolio": [
        "GET /api/data?horizon=&assumed_annual_pct= — composed holdings + projections/what-if + goal_status",
        "POST /api/sync — refresh gemelnet/pensia/Yahoo/Maya caches then return composed state",
        "GET /api/export / POST /api/import",
        "POST /api/settings — patch settings including goal ({target_amount_ils, target_date} or null to clear)",
    ],
    "funds": [
        "GET /api/funds/search",
        "POST /api/funds/{id}/prepare",
        "CRUD /api/fund-holdings (+ events, rules, spot-check)",
    ],
    "pension": [
        "GET /api/pension/search",
        "POST /api/pension/{id}/prepare",
        "CRUD /api/pension-holdings (+ rules, spot-check)",
    ],
    "equity_cash": [
        "GET /api/tickers/search",
        "CRUD /api/rsu-grants (+ sales)",
        "CRUD /api/espp-plans (+ enrollments/purchases/sales)",
        "CRUD /api/cash",
    ],
    "bank_investments": [
        "GET /api/tase-funds/search",
        "CRUD /api/tase-fund-holdings — TASE mutual funds (Maya); units × daily NAV",
        "POST/DELETE /api/tase-fund-holdings/{id}/events — buy/sell/correction of units",
    ],
    "chat": [
        "GET /api/chat/status",
        "POST /api/chat — this assistant; may call project_portfolio, query_portfolio_history, or evaluate_savings_goal",
    ],
    "projection_rules": {
        "what_if_annual_pct": (
            "Compounds funds (and pension what-if) at assumed %; cash+ESPP+Bank Investments flat; "
            "RSU vesting curve at current price/FX"
        ),
        "historical_default": (
            "Without assumed %, funds use historical average monthly return from gemelnet/pensia; "
            "Bank Investments use historical average monthly Maya NAV returns (≥6 months)"
        ),
        "horizon_cap_months": HORIZON_CAP_MONTHS,
        "pension": "Excluded from dashboard total; surfaced separately in pension_summary",
        "savings_goal": (
            "Single target Total Wealth (ILS) by target month; on_pace compares historical projection "
            "at that month to the target; pension excluded; chat evaluates via evaluate_savings_goal (read-only)"
        ),
        "cashout_tax_estimate": (
            "Rough educational estimate if liquidating accessible holdings: 25% on profit/gains only; "
            "קרן השתלמות tax-free; cash 0%; pension excluded; Bank Investments: 25% on unrealized (FIFO); not tax advice"
        ),
    },
}


TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "project_portfolio",
                "description": (
                    "Compute Saving Tracker portfolio projection to a future month using the live backend. "
                    "Use for future value/profit questions. Pass assumed_annual_pct when the user provided a yearly %; "
                    "omit it to use historical fund averages."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_year_month": {
                            "type": "string",
                            "description": "Target month as YYYY-MM, e.g. 2030-05 for May 2030",
                        },
                        "assumed_annual_pct": {
                            "type": "number",
                            "description": "Optional annual growth percent for funds/pension what-if (e.g. 8 for 8%/yr)",
                        },
                        "include_pension": {
                            "type": "boolean",
                            "description": "Include pension projection summary (default true)",
                        },
                    },
                    "required": ["target_year_month"],
                },
            },
            {
                "name": "query_portfolio_history",
                "description": (
                    "Return real historical monthly portfolio totals and month-over-month changes "
                    "(dashboard-style: funds + RSU + ESPP + cash + bank investments; pension excluded). "
                    "Includes change_from_prev_* (balance delta), net_external_flow_ils (fund deposits − withdrawals), "
                    "and investment_return_* (balance delta minus fund flows). "
                    "Use investment_return_* for profit/yield; do not treat deposits as profit."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "year_month": {
                            "type": "string",
                            "description": "Single month YYYY-MM, e.g. 2026-06",
                        },
                        "start_year_month": {
                            "type": "string",
                            "description": "Range start YYYY-MM (inclusive)",
                        },
                        "end_year_month": {
                            "type": "string",
                            "description": "Range end YYYY-MM (inclusive)",
                        },
                    },
                },
            },
            {
                "name": "evaluate_savings_goal",
                "description": (
                    "Return the user's savings-goal status (same as the dashboard goal strip): "
                    "target, progress, projected Total Wealth at the goal month, on_pace, and gap. "
                    "Uses historical fund averages; pension excluded. Call for on-pace / goal questions. "
                    "No parameters. Cannot set or clear the goal."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "describe_backend_apis",
                "description": "Describe Saving Tracker backend REST APIs and projection rules.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]
    }
]

GOAL_BASIS_NOTE = (
    "historical fund/NAV averages; Total Wealth (funds+RSU+ESPP+cash+bank investments); pension excluded"
)


def chat_enabled() -> bool:
    return _truthy_env("CHAT_ENABLED") and bool(_gemini_api_key())


def insights_enabled() -> bool:
    """AI insight card / daily email insights need only a Gemini key,
    independent of CHAT_ENABLED (which gates the interactive chat)."""
    return bool(_gemini_api_key())


def _round_or_none(v: Any, nd: int = 2):
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _holding_summary(h: dict, kind: str) -> dict:
    computed = h.get("computed") or {}
    metrics = computed.get("fund_metrics") or {}
    out = {
        "kind": kind,
        "nickname": h.get("nickname") or h.get("fund_name_snapshot") or "",
        "fund_id": h.get("fund_id"),
        "data_source": h.get("data_source"),
        "archived": bool(h.get("archived")),
        "current_value_ils": _round_or_none(computed.get("current_value_ils")),
        "profit_ils": _round_or_none(computed.get("profit_ils")),
        "profit_pct": _round_or_none(computed.get("profit_pct"), 4),
        "last_month_return_pct": _round_or_none(computed.get("last_month_return_pct"), 4),
        "ytd_return_pct": _round_or_none(computed.get("ytd_return_pct"), 4),
        "twelve_m_return_pct": _round_or_none(computed.get("twelve_m_return_pct"), 4),
        "last_period": computed.get("last_period"),
    }
    if metrics:
        out["specialization"] = metrics.get("specialization")
        out["stock_market_exposure_pct"] = _round_or_none(
            metrics.get("stock_market_exposure_pct"), 2
        )
    rules = h.get("recurring_rules") or []
    if rules:
        out["recurring_rules"] = [
            {
                "amount_ils": _round_or_none(r.get("amount_ils")),
                "employee_ils": _round_or_none(r.get("employee_ils")),
                "employer_ils": _round_or_none(r.get("employer_ils")),
                "start_date": r.get("start_date"),
                "end_date": r.get("end_date"),
            }
            for r in rules
        ]
    return out


def _rsu_summary(g: dict) -> dict:
    computed = g.get("computed") or {}
    return {
        "kind": "rsu",
        "nickname": g.get("nickname") or g.get("ticker"),
        "ticker": g.get("ticker"),
        "archived": bool(g.get("archived")),
        "current_value_ils": _round_or_none(computed.get("current_value_ils")),
        "current_value_usd": _round_or_none(computed.get("current_value_usd")),
        "unvested_shares": _round_or_none(computed.get("unvested_shares"), 4),
        "vested_shares": _round_or_none(computed.get("vested_shares"), 4),
        "grant_date": g.get("grant_date"),
        "analyst_target": g.get("analyst_target"),
    }


def _espp_summary(p: dict) -> dict:
    computed = p.get("computed") or {}
    return {
        "kind": "espp",
        "nickname": p.get("nickname") or p.get("ticker"),
        "ticker": p.get("ticker"),
        "archived": bool(p.get("archived")),
        "current_value_ils": _round_or_none(computed.get("current_value_ils")),
        "current_value_usd": _round_or_none(computed.get("current_value_usd")),
        "purchase_count": len(p.get("purchases") or []),
        "active_enrollment_count": len(computed.get("enrollments") or []),
        "pending_contribution_ils": _round_or_none(computed.get("pending_contribution_ils")),
    }


def _cash_summary(c: dict) -> dict:
    computed = c.get("computed") or {}
    return {
        "kind": "cash",
        "nickname": c.get("nickname") or "Cash",
        "currency": (c.get("currency") or "ILS").upper(),
        "amount": _round_or_none(c.get("amount")),
        "value_ils": _round_or_none(computed.get("value_ils")),
    }


def _period_key_to_int(period: Any) -> int | None:
    """Parse portfolio period ('YYYY-MM' or YYYYMM) to YYYYMM int."""
    if period is None:
        return None
    if isinstance(period, int):
        return period if period > 0 else None
    s = str(period).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m:
        return int(m.group(1)) * 100 + int(m.group(2))
    m = re.fullmatch(r"(\d{6})", s)
    if m:
        return int(m.group(1))
    return None


def _resolve_latest_published_period(state: dict) -> int | None:
    """Best-effort latest month that has published fund/pension/insurance yields."""
    cache = state.get("cache_status") or {}
    pub = cache.get("latest_published_period")
    try:
        if pub is not None and int(pub) > 0:
            return int(pub)
    except (TypeError, ValueError):
        pass
    latest = 0
    for h in (state.get("fund_holdings") or []) + (state.get("pension_holdings") or []):
        if h.get("archived"):
            continue
        lp = (h.get("computed") or {}).get("last_period")
        try:
            lp = int(lp or 0)
        except (TypeError, ValueError):
            lp = 0
        if lp > latest:
            latest = lp
    return latest if latest > 0 else None


def _fund_net_flows_by_period(state: dict) -> dict[int, float]:
    """Per-period net fund external flow (deposits − withdrawals) in ILS.

    Derived from cumulative deposited_to_date / withdrawn_to_date on each
    non-archived fund holding's time_series. Does not include RSU/ESPP/cash.
    """
    flows: dict[int, float] = {}
    for h in state.get("fund_holdings") or []:
        if h.get("archived"):
            continue
        series = ((h.get("computed") or {}).get("time_series")) or []
        prev_dep = 0.0
        prev_wd = 0.0
        for pt in series:
            period_int = _period_key_to_int(pt.get("period"))
            if period_int is None:
                continue
            try:
                dep = float(pt.get("deposited_to_date") or 0)
            except (TypeError, ValueError):
                dep = prev_dep
            try:
                wd = float(pt.get("withdrawn_to_date") or 0)
            except (TypeError, ValueError):
                wd = prev_wd
            net = (dep - prev_dep) - (wd - prev_wd)
            if abs(net) >= 0.005:
                flows[period_int] = round(flows.get(period_int, 0.0) + net, 2)
            prev_dep, prev_wd = dep, wd
    return flows


def _tase_fund_summary(h: dict) -> dict:
    computed = h.get("computed") or {}
    proj = h.get("projection") or {}
    out = {
        "id": h.get("id"),
        "kind": "bank_investment",
        "fund_id": h.get("fund_id"),
        "name": (h.get("nickname") or h.get("fund_name_snapshot") or h.get("fund_id")),
        "units": computed.get("units", h.get("units")),
        "unit_price_ils": _round_or_none(computed.get("unit_price_ils")),
        "value_ils": _round_or_none(computed.get("value_ils") or computed.get("current_value_ils")),
        "price_date": computed.get("price_date"),
        "last_month_return_pct": _round_or_none(computed.get("last_month_return_pct"), 4),
        "ytd_return_pct": _round_or_none(computed.get("ytd_return_pct"), 4),
        "ytd_year": computed.get("ytd_year"),
        "profit_ils": _round_or_none(computed.get("profit_ils")),
        "profit_pct": _round_or_none(computed.get("profit_pct"), 4),
        "cost_basis_ils": _round_or_none(computed.get("cost_basis_ils")),
        "realized_gain_ils": _round_or_none(computed.get("realized_gain_ils")),
        "last_synced": h.get("last_synced"),
        "note": "units × Maya NAV; FIFO P&L from events × NAV; what-if does not grow this sleeve",
    }
    if proj.get("annual_pct") is not None:
        out["projection_annual_pct"] = _round_or_none(proj.get("annual_pct"), 2)
        out["projection_n_samples"] = proj.get("n_samples")
    return out


def _build_monthly_history(state: dict, *, max_months: int = HISTORY_CONTEXT_MONTHS) -> dict:
    """Real monthly dashboard totals from portfolio.time_series_ils + cash (flat at today)."""
    portfolio = state.get("portfolio") or {}
    series = portfolio.get("time_series_ils") or []
    cash_now = _round_or_none(portfolio.get("cash_value_ils")) or 0.0
    published_through = _resolve_latest_published_period(state)
    fund_flows = _fund_net_flows_by_period(state)

    rows = []
    prev_total = None
    for s in series:
        period = s.get("period")
        if not period:
            continue
        period_int = _period_key_to_int(period)
        funds = _round_or_none(s.get("funds_ils")) or 0.0
        rsu = _round_or_none(s.get("rsu_ils")) or 0.0
        espp = _round_or_none(s.get("espp_ils")) or 0.0
        tase = _round_or_none(s.get("tase_ils")) or 0.0
        subtotal = _round_or_none(s.get("total_ils"))
        if subtotal is None:
            subtotal = round(funds + rsu + espp + tase, 2)
        total = round(subtotal + cash_now, 2)
        change_ils = round(total - prev_total, 2) if prev_total is not None else None
        change_pct = None
        if prev_total is not None and prev_total != 0 and change_ils is not None:
            change_pct = round(change_ils / prev_total, 4)
        net_flow = None
        investment_return_ils = None
        investment_return_pct = None
        if change_ils is not None and period_int is not None:
            net_flow = round(fund_flows.get(period_int, 0.0), 2)
            investment_return_ils = round(change_ils - net_flow, 2)
            if prev_total is not None and prev_total != 0:
                investment_return_pct = round(investment_return_ils / prev_total, 4)
        has_published_yield = False
        if period_int is not None:
            if published_through is not None:
                has_published_yield = period_int <= published_through
            else:
                # No cache cutoff: never treat the current calendar month as published.
                today = date.today()
                current_ym = today.year * 100 + today.month
                has_published_yield = period_int < current_ym
        rows.append({
            "period": period,
            "period_yyyymm": period_int,
            "total_ils": total,
            "funds_ils": funds,
            "rsu_ils": rsu,
            "espp_ils": espp,
            "tase_ils": tase,
            "cash_ils": cash_now,
            "change_from_prev_ils": change_ils,
            "change_from_prev_pct": change_pct,
            "net_external_flow_ils": net_flow,
            "investment_return_ils": investment_return_ils,
            "investment_return_pct": investment_return_pct,
            "has_published_yield": has_published_yield,
        })
        prev_total = total

    truncated = 0
    if max_months and len(rows) > max_months:
        truncated = len(rows) - max_months
        rows = rows[-max_months:]

    latest = rows[-1] if rows else None
    # Last month that actually has published yields (and a MoM delta when possible).
    # Portfolio series often extends to the calendar month via forward-fill — those
    # pending months must not be used for "last month yield" insights.
    latest_yield_month = None
    for row in reversed(rows):
        if published_through is not None and not row.get("has_published_yield"):
            continue
        if row.get("change_from_prev_ils") is None:
            continue
        latest_yield_month = {
            "period": row["period"],
            "total_ils": row["total_ils"],
            "change_from_prev_ils": row["change_from_prev_ils"],
            "change_from_prev_pct": row["change_from_prev_pct"],
            "net_external_flow_ils": row.get("net_external_flow_ils"),
            "investment_return_ils": row.get("investment_return_ils"),
            "investment_return_pct": row.get("investment_return_pct"),
            "published_through_yyyymm": published_through,
            "note": (
                "Last month with published yield data (and a month-over-month change). "
                "change_from_prev_* is total balance delta (includes deposits/withdrawals). "
                "investment_return_* excludes fund net_external_flow_ils (deposits − withdrawals). "
                "Ignores later calendar months that are only forward-filled without yields."
            ),
        }
        break

    return {
        "months": rows,
        "truncated_earlier_months": truncated,
        "latest_period": latest["period"] if latest else None,
        "published_through_yyyymm": published_through,
        "latest_yield_month": latest_yield_month,
        "note": (
            "Real history from holdings + synced monthly yields/NAV. Matches dashboard total "
            "(funds+RSU+ESPP+cash+bank investments). Cash uses today's amount for all past months. "
            "Pension excluded. change_from_prev_* = total balance MoM delta. "
            "investment_return_* = change_from_prev minus fund net_external_flow_ils "
            "(deposits − withdrawals). Do not call balance growth 'profit' when flows are large. "
            "For 'last month' / recent move, use ONLY latest_yield_month (has_published_yield). "
            "Do not use months after published_through_yyyymm — those lack published yields."
        ),
    }


def build_portfolio_context(state: dict) -> dict:
    """Compact snapshot for the model, including recent monthly history."""
    portfolio = state.get("portfolio") or {}
    pension_summary = state.get("pension_summary") or {}
    settings = state.get("settings") or {}
    cache_status = state.get("cache_status") or {}

    funds = [
        _holding_summary(h, "fund")
        for h in (state.get("fund_holdings") or [])
        if not h.get("archived")
    ]
    pensions = [
        _holding_summary(h, "pension")
        for h in (state.get("pension_holdings") or [])
        if not h.get("archived")
    ]
    rsus = [
        _rsu_summary(g)
        for g in (state.get("rsu_grants") or [])
        if not g.get("archived")
    ]
    espps = [
        _espp_summary(p)
        for p in (state.get("espp_plans") or [])
        if not p.get("archived")
    ]
    cash = [_cash_summary(c) for c in (state.get("cash_holdings") or [])]
    tase = [
        _tase_fund_summary(h)
        for h in (state.get("tase_fund_holdings") or [])
        if not h.get("archived")
    ]

    monthly_history = _build_monthly_history(state)
    return {
        "as_of": state.get("now"),
        "settings": {
            "yield_is_net_of_fees": settings.get("yield_is_net_of_fees"),
            "usdils_rate_override": settings.get("usdils_rate_override"),
        },
        "fx": {
            "current_usdils": cache_status.get("current_usdils"),
            "latest_published_period": cache_status.get("latest_published_period"),
        },
        "portfolio_totals": {
            "total_value_ils": _round_or_none(portfolio.get("total_value_ils")),
            "total_profit_ils": _round_or_none(portfolio.get("total_profit_ils")),
            "total_invested_ils": _round_or_none(portfolio.get("total_invested_ils")),
            "funds_value_ils": _round_or_none(portfolio.get("funds_value_ils")),
            "rsu_value_ils": _round_or_none(portfolio.get("rsu_value_ils")),
            "espp_value_ils": _round_or_none(portfolio.get("espp_value_ils")),
            "cash_value_ils": _round_or_none(portfolio.get("cash_value_ils")),
            "tase_funds_value_ils": _round_or_none(portfolio.get("tase_funds_value_ils")),
            "note": "Dashboard total excludes pension (tracked separately).",
        },
        "pension_summary": {
            "total_value_ils": _round_or_none(pension_summary.get("total_value_ils")),
            "count": pension_summary.get("count"),
            "excluded_from_dashboard_total": True,
        },
        "savings_goal": _savings_goal_context(state.get("goal_status")),
        "cashout_tax_estimate": _cashout_tax_context(state.get("cashout_tax_estimate")),
        "holdings": {
            "funds": funds,
            "pensions": pensions,
            "rsu": rsus,
            "espp": espps,
            "cash": cash,
            "bank_investments": tase,
        },
        "monthly_history": monthly_history,
        "insight_slots_hint": _insight_slots_hint(portfolio, monthly_history, state.get("goal_status")),
    }


def _insight_slots_hint(portfolio: dict, monthly_history: dict, goal_status: Any) -> dict:
    """Compact facts for the five fixed insight slots (deterministic helpers)."""
    total = float(portfolio.get("total_value_ils") or 0)
    sleeves = [
        ("funds", float(portfolio.get("funds_value_ils") or 0)),
        ("rsu", float(portfolio.get("rsu_value_ils") or 0)),
        ("espp", float(portfolio.get("espp_value_ils") or 0)),
        ("cash", float(portfolio.get("cash_value_ils") or 0)),
        ("bank_investments", float(portfolio.get("tase_funds_value_ils") or 0)),
    ]
    sleeves = [(k, v) for k, v in sleeves if v > 0]
    top = max(sleeves, key=lambda x: x[1]) if sleeves else None
    latest = monthly_history.get("latest_yield_month") if isinstance(monthly_history, dict) else None
    goal = _savings_goal_context(goal_status)
    return {
        "slot1_recent_move": latest,
        "slot2_allocation": (
            {
                "top_sleeve": top[0],
                "top_sleeve_value_ils": _round_or_none(top[1]),
                "top_sleeve_share_pct": _round_or_none(top[1] / total * 100, 1) if total > 0 else None,
                "total_value_ils": _round_or_none(total),
            }
            if top and total > 0
            else None
        ),
        "slot3_goal_or_lifetime_pl": {
            "goal": goal if goal.get("configured") else None,
            "lifetime_profit_ils": _round_or_none(portfolio.get("total_profit_ils")),
            "total_invested_ils": _round_or_none(portfolio.get("total_invested_ils")),
        },
        "notes": {
            "last_month_means": (
                "Use monthly_history.latest_yield_month only — the last month with "
                "has_published_yield=true (at or before published_through_yyyymm). "
                "Never cite later forward-filled months without yields. "
                "Break out net_external_flow_ils (deposits) vs investment_return_* — "
                "do not call change_from_prev_* 'profit' when flows dominate."
            ),
        },
    }


def _savings_goal_context(goal_status: Any) -> dict:
    """Compact savings-goal snapshot for the model (dashboard goal_status)."""
    if not isinstance(goal_status, dict):
        return {"configured": False}
    return {
        "configured": True,
        "target_amount_ils": _round_or_none(goal_status.get("target_amount_ils")),
        "target_date": goal_status.get("target_date"),
        "current_value_ils": _round_or_none(goal_status.get("current_value_ils")),
        "progress_pct": _round_or_none(goal_status.get("progress_pct"), 1),
        "projected_value_ils": _round_or_none(goal_status.get("projected_value_ils")),
        "on_pace": bool(goal_status.get("on_pace")),
        "gap_ils": _round_or_none(goal_status.get("gap_ils")),
        "months_remaining": goal_status.get("months_remaining"),
        "basis": GOAL_BASIS_NOTE,
    }


def _cashout_tax_context(est: Any) -> dict:
    """Compact cash-out tax estimate for insights/chat (deterministic backend)."""
    if not isinstance(est, dict):
        return {"available": False}
    return {
        "available": True,
        "accessible_value_ils": _round_or_none(est.get("accessible_value_ils")),
        "tax_free_value_ils": _round_or_none(est.get("tax_free_value_ils")),
        "taxable_profit_ils": _round_or_none(est.get("taxable_profit_ils")),
        "estimated_tax_ils": _round_or_none(est.get("estimated_tax_ils")),
        "net_after_tax_ils": _round_or_none(est.get("net_after_tax_ils")),
        "capital_gains_rate": est.get("capital_gains_rate"),
        "pension_excluded_value_ils": _round_or_none(est.get("pension_excluded_value_ils")),
        "assumptions": est.get("assumptions") or [],
        "disclaimer": est.get("disclaimer"),
        "by_holding": [
            {
                "kind": row.get("kind"),
                "label": row.get("label"),
                "value_ils": _round_or_none(row.get("value_ils")),
                "taxable_profit_ils": _round_or_none(row.get("taxable_profit_ils")),
                "estimated_tax_ils": _round_or_none(row.get("estimated_tax_ils")),
                "rate": row.get("rate"),
                "note": row.get("note"),
            }
            for row in (est.get("by_holding") or [])[:40]
        ],
    }


def _parse_year_month(raw: str) -> tuple[int, int]:
    s = (raw or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if not m:
        raise ValueError("target_year_month must be YYYY-MM")
    year, month = int(m.group(1)), int(m.group(2))
    if month < 1 or month > 12:
        raise ValueError("month must be 1–12")
    if year < 2000 or year > 2100:
        raise ValueError("year out of supported range")
    return year, month


def _months_until(year: int, month: int, today: Optional[date] = None) -> int:
    today = today or date.today()
    # Inclusive of the target month end relative to current month.
    return (year - today.year) * 12 + (month - today.month)


def _path_end(paths: Any) -> float | None:
    if not isinstance(paths, list) or not paths:
        return None
    return _round_or_none(paths[-1])


def summarize_projection_state(
    state: dict,
    *,
    target_year_month: str,
    assumed_annual_pct: Optional[float],
    include_pension: bool = True,
) -> dict:
    year, month = _parse_year_month(target_year_month)
    horizon = _months_until(year, month)
    if horizon < 1:
        return {
            "ok": False,
            "error": "Target month must be after the current month.",
            "target_year_month": f"{year:04d}-{month:02d}",
        }
    if horizon > HORIZON_CAP_MONTHS:
        return {
            "ok": False,
            "error": f"Horizon exceeds {HORIZON_CAP_MONTHS} months (~50 years).",
            "horizon_months": horizon,
        }

    portfolio = state.get("portfolio") or {}
    today_total = _round_or_none(portfolio.get("total_value_ils")) or 0.0
    today_profit = _round_or_none(portfolio.get("total_profit_ils"))
    today_invested = _round_or_none(portfolio.get("total_invested_ils"))

    mode = "what_if" if assumed_annual_pct is not None else "historical_funds"
    projected_total = None
    funds_end = None
    tase_end = None
    notes = []

    if assumed_annual_pct is not None:
        wf = portfolio.get("what_if") or {}
        projected_total = _round_or_none(wf.get("end_value_ils"))
        tase_end = _round_or_none(portfolio.get("tase_funds_value_ils"))
        if projected_total is None:
            notes.append("what_if projection unavailable; check holdings/sync.")
        else:
            notes.append(
                f"Funds/pension compounded at {assumed_annual_pct}%/yr; "
                "cash+ESPP+Bank Investments flat; RSU vesting at current price/FX."
            )
    else:
        proj = portfolio.get("projection") or {}
        paths = (proj.get("paths") or {})
        mean = paths.get("mean") or paths.get("total_mean")
        projected_total = _path_end(mean)
        funds_end = _path_end(paths.get("funds_mean"))
        tase_end = _path_end(paths.get("tase_mean"))
        if projected_total is None:
            # Fallback: today's total + any path components we can find.
            parts = [
                _path_end(paths.get("funds_mean")),
                _path_end(paths.get("rsu_mean")),
                _path_end(paths.get("espp_mean")),
                _path_end(paths.get("tase_mean")),
            ]
            cash_now = _round_or_none(portfolio.get("cash_value_ils")) or 0.0
            if any(p is not None for p in parts):
                projected_total = round(
                    sum(p or 0.0 for p in parts) + cash_now,
                    2,
                )
        notes.append(
            "No assumed_annual_pct: funds use historical average monthly returns; "
            "Bank Investments use historical Maya NAV monthly averages when available; "
            "cash+ESPP flat; RSU vesting curve."
        )
        if proj.get("funds_annual_pct") is not None:
            notes.append(
                f"Value-weighted historical funds annualized ~{proj.get('funds_annual_pct')}%/yr."
            )

    change_from_today = None
    if projected_total is not None:
        change_from_today = round(projected_total - today_total, 2)

    last_day = monthrange(year, month)[1]
    out = {
        "ok": True,
        "target_year_month": f"{year:04d}-{month:02d}",
        "target_date_approx": f"{year:04d}-{month:02d}-{last_day:02d}",
        "horizon_months": horizon,
        "mode": mode,
        "assumed_annual_pct": assumed_annual_pct,
        "today": {
            "total_value_ils": today_total,
            "total_profit_ils": today_profit,
            "total_invested_ils": today_invested,
            "funds_value_ils": _round_or_none(portfolio.get("funds_value_ils")),
            "rsu_value_ils": _round_or_none(portfolio.get("rsu_value_ils")),
            "espp_value_ils": _round_or_none(portfolio.get("espp_value_ils")),
            "cash_value_ils": _round_or_none(portfolio.get("cash_value_ils")),
            "tase_funds_value_ils": _round_or_none(portfolio.get("tase_funds_value_ils")),
        },
        "projected": {
            "total_value_ils": projected_total,
            "change_from_today_ils": change_from_today,
            "funds_value_ils": funds_end,
            "tase_funds_value_ils": tase_end,
            "interpretation": {
                "change_from_today": "Projected portfolio total minus today's dashboard total (excludes pension).",
                "profit_note": (
                    "Accounting 'profit' today is funds/RSU/ESPP/Bank Investment profit fields. "
                    "Future 'profit' usually means change_from_today under the stated assumptions — not a tax figure."
                ),
            },
        },
        "assumptions": notes,
        "disclaimer": "Estimate only — not a forecast, guarantee, or tax/financial advice.",
    }

    if include_pension:
        ps = state.get("pension_summary") or {}
        pension_today = _round_or_none(ps.get("total_value_ils")) or 0.0
        pension_proj = None
        if assumed_annual_pct is not None:
            pwf = ps.get("what_if") or {}
            pension_proj = _round_or_none(pwf.get("end_value_ils"))
        else:
            # Sum per-holding historical projections when present.
            total = 0.0
            any_p = False
            for h in state.get("pension_holdings") or []:
                if h.get("archived"):
                    continue
                paths = ((h.get("projection") or {}).get("paths") or {}).get("mean") or []
                if paths:
                    any_p = True
                    total += float(paths[-1] or 0)
            pension_proj = round(total, 2) if any_p else None
        out["pension"] = {
            "today_value_ils": pension_today,
            "projected_value_ils": pension_proj,
            "change_from_today_ils": (
                round(pension_proj - pension_today, 2) if pension_proj is not None else None
            ),
            "excluded_from_dashboard_total": True,
        }

    return out


def run_query_portfolio_history_tool(compose_fn: ComposeFn, args: dict) -> dict:
    try:
        state = compose_fn(24, None)
        full = _build_monthly_history(state, max_months=0)
        months = full.get("months") or []
        if not months:
            return {"ok": False, "error": "No monthly history available yet."}

        ym = (args.get("year_month") or "").strip()
        start = (args.get("start_year_month") or "").strip()
        end = (args.get("end_year_month") or "").strip()

        if ym:
            _parse_year_month(ym)
            matched = [m for m in months if m.get("period") == ym]
            if not matched:
                return {
                    "ok": False,
                    "error": f"No data for {ym}.",
                    "available_range": {
                        "earliest": months[0]["period"],
                        "latest": months[-1]["period"],
                    },
                }
            return {"ok": True, "months": matched, "note": full.get("note")}

        if start or end:
            if not start or not end:
                return {"ok": False, "error": "Provide both start_year_month and end_year_month."}
            _parse_year_month(start)
            _parse_year_month(end)
            lo, hi = (start, end) if start <= end else (end, start)
            filtered = [m for m in months if lo <= m.get("period", "") <= hi]
            if not filtered:
                return {
                    "ok": False,
                    "error": f"No data between {lo} and {hi}.",
                    "available_range": {
                        "earliest": months[0]["period"],
                        "latest": months[-1]["period"],
                    },
                }
            return {"ok": True, "months": filtered, "note": full.get("note")}

        # Default: last 12 months of full history.
        tail = months[-12:]
        return {
            "ok": True,
            "months": tail,
            "available_range": {
                "earliest": months[0]["period"],
                "latest": months[-1]["period"],
            },
            "note": full.get("note"),
        }
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


def run_project_portfolio_tool(compose_fn: ComposeFn, args: dict) -> dict:
    try:
        target = str(args.get("target_year_month") or "").strip()
        year, month = _parse_year_month(target)
        horizon = _months_until(year, month)
        if horizon < 1:
            return {"ok": False, "error": "Target month must be after the current month."}
        if horizon > HORIZON_CAP_MONTHS:
            return {
                "ok": False,
                "error": f"Horizon exceeds {HORIZON_CAP_MONTHS} months.",
                "horizon_months": horizon,
            }

        assumed = args.get("assumed_annual_pct", None)
        if assumed is not None and assumed != "":
            assumed = float(assumed)
        else:
            assumed = None

        include_pension = args.get("include_pension")
        if include_pension is None:
            include_pension = True

        state = compose_fn(horizon, assumed)
        return summarize_projection_state(
            state,
            target_year_month=f"{year:04d}-{month:02d}",
            assumed_annual_pct=assumed,
            include_pension=bool(include_pension),
        )
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


def run_evaluate_savings_goal_tool(compose_fn: ComposeFn) -> dict:
    """Return dashboard goal_status (historical projection; pension excluded)."""
    try:
        state = compose_fn(24, None)
        goal_status = state.get("goal_status")
        if not isinstance(goal_status, dict):
            return {
                "ok": True,
                "configured": False,
                "message": (
                    "No savings goal set. User can set target amount + target month "
                    "in the dashboard goal strip (POST /api/settings)."
                ),
            }
        out = _savings_goal_context(goal_status)
        out["ok"] = True
        return out
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


def _normalize_messages(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").strip().lower()
        content = (m.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if len(content) > 4000:
            content = content[:4000]
        out.append({"role": role, "content": content})
    return out[-MAX_HISTORY:]


def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return contents


def _extract_candidate_parts(payload: dict) -> list[dict]:
    candidates = payload.get("candidates") or []
    if not candidates:
        block = (payload.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise RuntimeError(f"Gemini blocked the prompt ({block})")
        raise RuntimeError("Gemini returned no candidates")
    return list(((candidates[0] or {}).get("content") or {}).get("parts") or [])


def _parts_text(parts: list[dict]) -> str:
    texts = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
    return "\n".join(texts).strip()


def _parts_function_calls(parts: list[dict]) -> list[dict]:
    out = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        fc = p.get("functionCall")
        if not fc:
            continue
        # Keep original part so thoughtSignature / id round-trip.
        out.append(p)
    return out


def _execute_tool(name: str, args: dict, compose_fn: ComposeFn) -> dict:
    if name == "describe_backend_apis":
        return {"ok": True, "apis": BACKEND_API_CATALOG}
    if name == "query_portfolio_history":
        return run_query_portfolio_history_tool(compose_fn, args or {})
    if name == "project_portfolio":
        return run_project_portfolio_tool(compose_fn, args or {})
    if name == "evaluate_savings_goal":
        return run_evaluate_savings_goal_tool(compose_fn)
    return {"ok": False, "error": f"Unknown tool: {name}"}


def _gemini_generate(*, contents: list[dict], system_text: str) -> dict:
    api_key = _gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    model = _gemini_model()
    url = GEMINI_URL.format(model=model)
    body = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "tools": TOOLS,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    r = requests.post(
        url,
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:500]}")
    return r.json()


def call_gemini_with_tools(
    *,
    context: dict,
    messages: list[dict],
    compose_fn: ComposeFn,
) -> str:
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    system_text = (
        f"{SYSTEM_PROMPT}\n\n"
        "Current portfolio summary (JSON). Use as ground truth for today's numbers:\n"
        f"{context_json}"
    )
    contents = _to_gemini_contents(messages)
    if not contents or contents[-1]["role"] != "user":
        raise ValueError("Conversation must end with a user message")

    for _ in range(MAX_TOOL_ROUNDS):
        payload = _gemini_generate(contents=contents, system_text=system_text)
        parts = _extract_candidate_parts(payload)
        fc_parts = _parts_function_calls(parts)
        if not fc_parts:
            text = _parts_text(parts)
            if not text:
                raise RuntimeError("Gemini returned an empty reply")
            return text

        # Append model tool-call turn, then user function responses.
        contents.append({"role": "model", "parts": parts})
        response_parts = []
        for part in fc_parts:
            fc = part.get("functionCall") or {}
            name = fc.get("name") or ""
            raw_args = fc.get("args") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}
            result = _execute_tool(name, raw_args if isinstance(raw_args, dict) else {}, compose_fn)
            fr: dict[str, Any] = {
                "name": name,
                "response": result,
            }
            if fc.get("id"):
                fr["id"] = fc["id"]
            # Some models expect the full part echo for signatures; include if present.
            response_part: dict[str, Any] = {"functionResponse": fr}
            if part.get("thoughtSignature"):
                response_part["thoughtSignature"] = part["thoughtSignature"]
            response_parts.append(response_part)
        contents.append({"role": "user", "parts": response_parts})

    # Last resort after tool loop.
    payload = _gemini_generate(contents=contents, system_text=system_text)
    text = _parts_text(_extract_candidate_parts(payload))
    if not text:
        raise RuntimeError("Gemini did not finish after tool calls")
    return text


def run_chat(
    state: dict,
    messages_raw: Any,
    compose_fn: Optional[ComposeFn] = None,
) -> dict:
    """Returns {ok, reply} or {ok: False, error}."""
    if not chat_enabled():
        return {"ok": False, "error": "chat_disabled"}

    messages = _normalize_messages(messages_raw)
    if not messages:
        return {"ok": False, "error": "No messages provided"}
    if messages[-1]["role"] != "user":
        return {"ok": False, "error": "Last message must be from the user"}

    if compose_fn is None:
        # Projection tool unavailable without compose callback.
        def _no_compose(horizon: int, assumed: float | None) -> dict:
            raise RuntimeError("compose_fn not configured")

        compose_fn = _no_compose

    context = build_portfolio_context(state)
    try:
        reply = call_gemini_with_tools(
            context=context,
            messages=messages,
            compose_fn=compose_fn,
        )
    except Exception as ex:
        return {"ok": False, "error": str(ex)}
    return {"ok": True, "reply": reply, "model": _gemini_model()}


DAILY_INSIGHTS_PROMPT = """You write short daily insights for a personal Israeli savings tracker (in-app card and email).
Use ONLY the portfolio JSON provided. Educational only — not financial, tax, or legal advice.
Do NOT discuss management fees or deposit fees. Do NOT invent holdings or numbers missing from the JSON.

Write insights for these FIXED SLOTS in order (skip a slot entirely if data is missing or the observation is weak):
1. recent_move — Latest month with published yield data.
   Use monthly_history.latest_yield_month (or insight_slots_hint.slot1_recent_move) ONLY.
   Name that period (YYYY-MM). Never use a month where has_published_yield is false, or any
   period after published_through_yyyymm — those are forward-filled without yields (often 0% change).
   This may lag the calendar month (e.g. May yields while today is July).
   CRITICAL: change_from_prev_* is total balance delta and INCLUDES deposits/withdrawals.
   Use investment_return_ils / investment_return_pct for true fund/market profit/loss.
   When |net_external_flow_ils| is material vs the balance change, break BOTH out in one sentence
   (total grew by Z, of which deposits W and investment return X / Y%). Never attribute deposits to "profit" or "yield".
   If flows are ~0, you may speak about investment return alone.
2. allocation — Which sleeve (funds/RSU/ESPP/cash/bank_investments) or concentration stands out vs Total Wealth.
   Prefer insight_slots_hint.slot2_allocation when present.
3. goal_or_lifetime_pl — If savings_goal.configured: ONE summary of pace/progress vs target (include progress_pct and gap or projected value — pick one framing, not both). Else: lifetime total_profit_ils vs invested (includes Bank Investment FIFO P&L).
4. risk — A DIFFERENT topic from slots 1–3. Prefer concentration, single-ticker RSU/ESPP, Bank Investment concentration, or cash-buffer size.
   Do NOT restate that the savings goal is on/off pace, the target amount, progress %, gap, or projected value if slot 3 already covered the goal.
5. suggestion — One concrete educational next step grounded in the data. Must not repeat slots 1–4; build on them (e.g. what to review next).

Return ONLY valid JSON (no markdown fences, no prose outside JSON):
{"insights":[{"slot":1,"text":"...","confidence":0.0}]}

Rules:
- At most one insight per slot; at most 5 total. Omit slots you skip.
- "slot" must be 1–5 matching the list above.
- Each "text" is one short sentence (no leading "- ").
- Every insight must cover a distinct topic — no near-duplicates across slots.
- "confidence" is 0–1: how sure the insight is grounded in the provided JSON (not speculation).
- Prefer specific numbers from the JSON over vague wording.
- Round money to whole shekels when speaking (no long decimals) unless precision matters.
- Write every insight text in Hebrew."""

# Only surface insights the model marks as high-confidence.
INSIGHTS_MIN_CONFIDENCE = 0.75
INSIGHTS_MAX_COUNT = 5


def _insight_overlap_key(text: str) -> set[str]:
    """Normalize insight text into tokens used for near-duplicate detection."""
    s = (text or "").lower()
    # Keep digits/amounts and alphabetic/Hebrew tokens; drop tiny words.
    raw = re.findall(r"[0-9]+(?:[.,][0-9]+)?|[a-z\u0590-\u05ff]{3,}", s)
    return {t.replace(",", "") for t in raw}


def _insights_are_near_duplicates(a: str, b: str) -> bool:
    """True when two insights largely repeat the same topic/numbers."""
    ka, kb = _insight_overlap_key(a), _insight_overlap_key(b)
    if not ka or not kb:
        return False
    inter = ka & kb
    if len(inter) < 3:
        return False
    # High Jaccard or many shared numeric tokens → duplicate.
    union = ka | kb
    jaccard = len(inter) / max(len(union), 1)
    shared_nums = {t for t in inter if t[:1].isdigit()}
    return jaccard >= 0.45 or len(shared_nums) >= 2


def _parse_insights_payload(raw: str) -> list[dict]:
    """Parse model JSON into [{slot?, text, confidence}, ...]. Tolerates markdown fences."""
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: treat plain "- " bullets as medium-confidence insights.
        out = []
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("- ") or s.startswith("• ") or s.startswith("* "):
                out.append({"text": s[2:].strip(), "confidence": 0.7, "slot": None})
        return out
    items = data.get("insights") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if isinstance(it, str) and it.strip():
            out.append({"text": it.strip(), "confidence": 0.7, "slot": None})
            continue
        if not isinstance(it, dict):
            continue
        t = (it.get("text") or it.get("insight") or "").strip()
        if not t:
            continue
        try:
            conf = float(it.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        slot = it.get("slot")
        try:
            slot = int(slot) if slot is not None else None
        except (TypeError, ValueError):
            slot = None
        if slot is not None and (slot < 1 or slot > INSIGHTS_MAX_COUNT):
            slot = None
        out.append({"text": t, "confidence": conf, "slot": slot})
    return out


def _select_insight_items(parsed: list[dict]) -> list[dict]:
    """Keep high-confidence insights, one per slot, drop near-duplicates, preserve order."""
    kept = [
        it for it in parsed
        if float(it.get("confidence") or 0) >= INSIGHTS_MIN_CONFIDENCE
        and (it.get("text") or "").strip()
    ]
    by_slot: dict[int, dict] = {}
    unslotted: list[dict] = []
    for it in kept:
        slot = it.get("slot")
        if isinstance(slot, int):
            # First high-confidence hit for each slot wins.
            by_slot.setdefault(slot, it)
        else:
            unslotted.append(it)
    candidates = [by_slot[s] for s in range(1, INSIGHTS_MAX_COUNT + 1) if s in by_slot]
    for it in unslotted:
        candidates.append(it)

    ordered: list[dict] = []
    for it in candidates:
        if len(ordered) >= INSIGHTS_MAX_COUNT:
            break
        text = it.get("text") or ""
        if any(_insights_are_near_duplicates(text, prev.get("text") or "") for prev in ordered):
            continue
        ordered.append(it)
    return ordered


def _format_insights_bullets(items: list[dict]) -> str:
    lines = []
    for it in items:
        t = (it.get("text") or "").strip()
        if t:
            lines.append(f"- {t}")
    return "\n".join(lines)


def generate_daily_insights(context: dict, lang: str = None) -> str:
    """One-shot Gemini text for daily email / in-app card (Hebrew).

    Requires GEMINI_API_KEY only (not CHAT_ENABLED). ``lang`` is ignored
    (kept for call-site compatibility); output is always Hebrew.

    Asks for up to 5 fixed-slot insights with confidence scores; only insights
    at or above INSIGHTS_MIN_CONFIDENCE are returned (may be empty).
    """
    api_key = _gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    model = _gemini_model()
    system_prompt = DAILY_INSIGHTS_PROMPT
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Fill the fixed insight slots from this JSON "
                            "(skip weak/missing slots; last month = latest published yield month; "
                            "Hebrew only; break out deposits vs investment return for slot 1):\n"
                            f"{context_json}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 500,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(
        GEMINI_URL.format(model=model),
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if r.status_code >= 400:
        # Some models reject responseMimeType — retry without it.
        body["generationConfig"].pop("responseMimeType", None)
        r = requests.post(
            GEMINI_URL.format(model=model),
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:400]}")
    parts = _extract_candidate_parts(r.json())
    raw = _parts_text(parts)
    if not raw:
        raise RuntimeError("Gemini returned empty insights")
    parsed = _parse_insights_payload(raw)
    kept = _select_insight_items(parsed)
    return _format_insights_bullets(kept)
