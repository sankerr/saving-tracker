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
You receive a compact JSON summary of the user's holdings (קופות גמל / השתלמות via gemelnet, pension via pensia-net, RSU, ESPP, cash).

Backend capabilities (use tools — do not invent math):
- project_portfolio: runs the same server projection as the app dashboard (compose_state / what-if).
  Growth % applies to funds (and pension when included). Cash and ESPP are held flat; RSU follows vesting at today's price/FX.
- query_portfolio_history: returns real past monthly dashboard totals and month-over-month changes from synced holdings/yields.
  Use for "what was my total in June?", "how much did I gain last month?", or comparing two past months.
- evaluate_savings_goal: returns the user's savings-goal status (same as the dashboard goal strip).
  Pace uses historical fund averages projected to the goal month; Total Wealth only (pension excluded). No growth-% override.
- describe_backend_apis: lists REST APIs and what they do.

Past totals / change questions (e.g. "what was my portfolio worth in March?", "how much changed since last month?"):
1. Prefer monthly_history in the portfolio JSON (recent months with change_from_prev_ils / change_from_prev_pct).
2. For a specific older month or a custom date range, call query_portfolio_history with year_month or start_year_month/end_year_month.
3. Explain totals using the returned numbers only. Note cash is held at today's amount for all past months (same as the dashboard chart). Pension is excluded from dashboard totals.

Future value / profit questions (e.g. "what will my profit be in May 2030?"):
1. If the user gave an annual growth % (year %), call project_portfolio with target_year_month=YYYY-MM and assumed_annual_pct.
2. If they did NOT give a %, ask them for an assumed annual growth % OR offer to project using historical fund averages (call project_portfolio omitting assumed_annual_pct). Prefer asking when they said "profit" and want a what-if.
3. After the tool returns, explain projected total, change vs today, and assumptions. Never invent projected numbers.
4. Say clearly that projections are estimates, not guarantees, and not tax/financial advice.

Savings goal questions (e.g. "am I on pace?", "how far from my goal?", "what's my savings goal?"):
1. Prefer savings_goal in the portfolio JSON when present and configured.
2. For an explicit pace/gap check, call evaluate_savings_goal.
3. Explain using returned numbers only: progress_pct, projected_value_ils at target_date, on_pace, gap_ils.
4. Note the basis: historical fund averages; headline Total Wealth (funds+RSU+ESPP+cash); pension excluded.
5. You cannot set or clear the goal — tell the user to use the dashboard goal strip / Set a goal modal (POST /api/settings).

Cash-out / tax questions (e.g. "how much tax if I cash out everything?"):
1. Use cashout_tax_estimate from the portfolio JSON only — never invent tax figures.
2. Report estimated_tax_ils, net_after_tax_ils, taxable_profit_ils, and that tax is on profit/gains only.
3. Note: קרן השתלמות is treated as tax-free; cash 0%; pension excluded from cash-out; other funds/RSU/ESPP use 25% on gains.
4. Always repeat the disclaimer: rough educational estimate, not tax advice.

When asked what the app can do / how to use it:
- Call describe_backend_apis if helpful, then explain in plain language: track gemelnet/provident funds, pension (separate), RSU, ESPP, cash; savings goal toward Total Wealth; dashboard projections/what-if; spot-check; sync; AI chat for questions, projections, goal pace, and rough cash-out tax estimate. Keep it short and numbered.

Guidelines:
- Answer using portfolio data + tool results + general public knowledge about Israeli gemel/pension/RSU/ESPP.
- Suggest concrete educational improvements when asked (allocation, concentration, contributions, vesting, growth assumptions). Keep replies concise.
- Do NOT discuss management fees, deposit fees, or "~mgmt fees paid" as features of this app — the app does not calculate fees for advice. Prefer allocation and growth topics instead.
- Match the user's language (Hebrew or English).
- You are NOT a licensed advisor. Do not invent holdings or numbers missing from context/tools.
- Dashboard total excludes pension (tracked separately). For tax/cash-out, only use cashout_tax_estimate."""


BACKEND_API_CATALOG = {
    "auth": ["POST /api/login", "POST /api/register", "POST /api/account/password", "DELETE /api/account"],
    "portfolio": [
        "GET /api/data?horizon=&assumed_annual_pct= — composed holdings + projections/what-if + goal_status",
        "POST /api/sync — refresh gemelnet/pensia/Yahoo caches then return composed state",
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
        "CRUD /api/espp-plans (+ purchases/sales)",
        "CRUD /api/cash",
    ],
    "chat": [
        "GET /api/chat/status",
        "POST /api/chat — this assistant; may call project_portfolio, query_portfolio_history, or evaluate_savings_goal",
    ],
    "projection_rules": {
        "what_if_annual_pct": "Compounds funds (and pension what-if) at assumed %; cash+ESPP flat; RSU vesting curve at current price/FX",
        "historical_default": "Without assumed %, funds use historical average monthly return from gemelnet/pensia",
        "horizon_cap_months": HORIZON_CAP_MONTHS,
        "pension": "Excluded from dashboard total; surfaced separately in pension_summary",
        "savings_goal": (
            "Single target Total Wealth (ILS) by target month; on_pace compares historical projection "
            "at that month to the target; pension excluded; chat evaluates via evaluate_savings_goal (read-only)"
        ),
        "cashout_tax_estimate": (
            "Rough educational estimate if liquidating accessible holdings: 25% on profit/gains only; "
            "קרן השתלמות tax-free; cash 0%; pension excluded; not tax advice"
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
                    "(dashboard-style: funds + RSU + ESPP + cash; pension excluded). "
                    "Use for past totals or 'what changed' questions."
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
    "historical fund averages; Total Wealth (funds+RSU+ESPP+cash); pension excluded"
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


def _build_monthly_history(state: dict, *, max_months: int = HISTORY_CONTEXT_MONTHS) -> dict:
    """Real monthly dashboard totals from portfolio.time_series_ils + cash (flat at today)."""
    portfolio = state.get("portfolio") or {}
    series = portfolio.get("time_series_ils") or []
    cash_now = _round_or_none(portfolio.get("cash_value_ils")) or 0.0

    rows = []
    prev_total = None
    for s in series:
        period = s.get("period")
        if not period:
            continue
        funds = _round_or_none(s.get("funds_ils")) or 0.0
        rsu = _round_or_none(s.get("rsu_ils")) or 0.0
        espp = _round_or_none(s.get("espp_ils")) or 0.0
        subtotal = _round_or_none(s.get("total_ils"))
        if subtotal is None:
            subtotal = round(funds + rsu + espp, 2)
        total = round(subtotal + cash_now, 2)
        change_ils = round(total - prev_total, 2) if prev_total is not None else None
        change_pct = None
        if prev_total is not None and prev_total != 0 and change_ils is not None:
            change_pct = round(change_ils / prev_total, 4)
        rows.append({
            "period": period,
            "total_ils": total,
            "funds_ils": funds,
            "rsu_ils": rsu,
            "espp_ils": espp,
            "cash_ils": cash_now,
            "change_from_prev_ils": change_ils,
            "change_from_prev_pct": change_pct,
        })
        prev_total = total

    truncated = 0
    if max_months and len(rows) > max_months:
        truncated = len(rows) - max_months
        rows = rows[-max_months:]

    return {
        "months": rows,
        "truncated_earlier_months": truncated,
        "latest_period": rows[-1]["period"] if rows else None,
        "note": (
            "Real history from holdings + synced monthly yields. Matches dashboard total "
            "(funds+RSU+ESPP+cash). Cash uses today's amount for all past months. Pension excluded."
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
        },
        "monthly_history": _build_monthly_history(state),
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
    notes = []

    if assumed_annual_pct is not None:
        wf = portfolio.get("what_if") or {}
        projected_total = _round_or_none(wf.get("end_value_ils"))
        if projected_total is None:
            notes.append("what_if projection unavailable; check holdings/sync.")
        else:
            notes.append(
                f"Funds/pension compounded at {assumed_annual_pct}%/yr; cash+ESPP flat; RSU vesting at current price/FX."
            )
    else:
        proj = portfolio.get("projection") or {}
        paths = (proj.get("paths") or {})
        mean = paths.get("mean") or paths.get("total_mean")
        projected_total = _path_end(mean)
        funds_end = _path_end(paths.get("funds_mean"))
        if projected_total is None:
            # Fallback: today's total + any path components we can find.
            parts = [
                _path_end(paths.get("funds_mean")),
                _path_end(paths.get("rsu_mean")),
                _path_end(paths.get("espp_mean")),
            ]
            cash_now = _round_or_none(portfolio.get("cash_value_ils")) or 0.0
            if any(p is not None for p in parts):
                projected_total = round(
                    sum(p or 0.0 for p in parts) + cash_now,
                    2,
                )
        notes.append(
            "No assumed_annual_pct: funds use historical average monthly returns; cash+ESPP flat; RSU vesting curve."
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
        },
        "projected": {
            "total_value_ils": projected_total,
            "change_from_today_ils": change_from_today,
            "funds_value_ils": funds_end,
            "interpretation": {
                "change_from_today": "Projected portfolio total minus today's dashboard total (excludes pension).",
                "profit_note": (
                    "Accounting 'profit' today is funds/RSU/ESPP profit fields. Future 'profit' usually means "
                    "change_from_today under the stated assumptions — not a tax figure."
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


DAILY_INSIGHTS_PROMPT = """You write a short daily insight for a personal Israeli savings tracker (in-app card and email).
Use ONLY the portfolio JSON provided. Educational only — not financial, tax, or legal advice.
Do NOT discuss management fees or deposit fees.
Do NOT invent tax numbers — only use cashout_tax_estimate when present.

Write exactly 6 short bullet points (plain text with leading "- "), in this exact order:
1. Overall Total Wealth — state portfolio_totals.total_value_ils in ₪ (dashboard total; pension excluded).
2. Last month profit/loss — use the latest monthly_history month's change_from_prev_ils / change_from_prev_pct (and its period). If missing, say last-month change is not available yet.
3. Goal status — use savings_goal. If configured: progress_pct, on_pace, gap_ils vs target_amount_ils by target_date. If not configured: say no savings goal is set.
4. Suggestion — one concrete educational suggestion (allocation, contributions, vesting, cash buffer, or growth assumptions).
5. Risks — one notable risk (concentration, single-ticker RSU/ESPP, low cash buffer, aggressive horizon, or behind-pace goal).
6. Cash-out tax estimate — from cashout_tax_estimate: estimated_tax_ils and net_after_tax_ils. Note tax is on profit/gains only; קרן השתלמות tax-free; pension excluded. End with "estimate only, not tax advice." If unavailable, say the estimate is not available.

Rules:
- One bullet per line; no numbering prefixes beyond "- "; no intro or closing.
- Use real numbers from the JSON; do not invent holdings or values.
- Keep each bullet to one sentence. Max ~150 words total.
- When a language directive is given below, follow it; otherwise match Hebrew nicknames if the data is mostly Hebrew, else English."""


_INSIGHTS_LANG_DIRECTIVE = {
    "he": "\nWrite the entire response in Hebrew.",
    "en": "\nWrite the entire response in English.",
}


def generate_daily_insights(context: dict, lang: str = None) -> str:
    """One-shot Gemini text for daily email / in-app card.

    Requires GEMINI_API_KEY only (not CHAT_ENABLED). When ``lang`` is 'he' or
    'en' the output is forced to that language; otherwise the model matches the
    data's language (default used by the email path).
    """
    api_key = _gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    model = _gemini_model()
    system_prompt = DAILY_INSIGHTS_PROMPT + _INSIGHTS_LANG_DIRECTIVE.get((lang or "").lower(), "")
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Write today's 6-bullet portfolio insights from this JSON:\n"
                            f"{context_json}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 550,
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
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:400]}")
    parts = _extract_candidate_parts(r.json())
    text = _parts_text(parts)
    if not text:
        raise RuntimeError("Gemini returned empty insights")
    return text


_INSIGHTS_LANG_NAMES = {"he": "Hebrew", "en": "English"}

_TRANSLATE_INSIGHTS_PROMPT = (
    "You are a professional translator. Translate the user's text to {lang_name}.\n"
    "Preserve the exact meaning, order, numbers, and any leading \"- \" bullet markers.\n"
    "Keep exactly 6 bullets in the same order. Do not add, remove, reorder, or\n"
    "reinterpret any content. Keep numbers and currency symbols unchanged.\n"
    "Output only the translation, nothing else."
)


def _translate_insights(text: str, target_lang: str) -> str:
    """Translate an insight string to ``target_lang`` ('he'/'en') preserving
    content, so both language versions convey identical information."""
    api_key = _gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    model = _gemini_model()
    lang_name = _INSIGHTS_LANG_NAMES.get((target_lang or "").lower(), "English")
    system_prompt = _TRANSLATE_INSIGHTS_PROMPT.format(lang_name=lang_name)
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 600},
    }
    r = requests.post(
        GEMINI_URL.format(model=model),
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:400]}")
    translated = _parts_text(_extract_candidate_parts(r.json()))
    if not translated:
        raise RuntimeError("Gemini returned empty translation")
    return translated


def generate_daily_insights_bilingual(context: dict) -> dict:
    """Generate the daily insight once (English) then translate to Hebrew, so
    the two language versions convey the *same content*, each in its own
    language. Returns ``{"en": text, "he": text}``.

    If translation fails, falls back to an independent Hebrew generation so the
    card still works (content may then differ slightly)."""
    en = generate_daily_insights(context, lang="en")
    try:
        he = _translate_insights(en, "he")
    except Exception:
        he = generate_daily_insights(context, lang="he")
    return {"en": en, "he": he}
