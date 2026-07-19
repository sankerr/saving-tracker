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
- describe_backend_apis: lists REST APIs and what they do.

Future value / profit questions (e.g. "what will my profit be in May 2030?"):
1. If the user gave an annual growth % (year %), call project_portfolio with target_year_month=YYYY-MM and assumed_annual_pct.
2. If they did NOT give a %, ask them for an assumed annual growth % OR offer to project using historical fund averages (call project_portfolio omitting assumed_annual_pct). Prefer asking when they said "profit" and want a what-if.
3. After the tool returns, explain projected total, change vs today, and assumptions. Never invent projected numbers.
4. Say clearly that projections are estimates, not guarantees, and not tax/financial advice.

When asked what the app can do / how to use it:
- Call describe_backend_apis if helpful, then explain in plain language: track gemelnet/provident funds, pension (separate), RSU, ESPP, cash; dashboard projections/what-if; spot-check; sync; AI chat for questions and projections. Keep it short and numbered.

Guidelines:
- Answer using portfolio data + tool results + general public knowledge about Israeli gemel/pension/RSU/ESPP.
- Suggest concrete educational improvements when asked (allocation, concentration, contributions, vesting, growth assumptions). Keep replies concise.
- Management fees: users can now enter their OWN management fees per holding — an annual balance fee (דמי ניהול מצבירה) and a per-deposit fee (דמי ניהול מהפקדה), as effective-dated change points. When set, the app estimates fees paid (see `user_mgmt_fees` in context) and factors them into value/projections. Treat these as USER-ENTERED ESTIMATES ONLY, NOT the actual fees charged by the fund/insurer — whenever you mention them, remind the user to verify against official statements. If no fee is set for a holding, it has no `user_mgmt_fees` and values fall back to the published (usually net-of-fees) yield.
- Match the user's language (Hebrew or English).
- You are NOT a licensed advisor. Do not invent holdings or numbers missing from context/tools.
- This app does not model Israeli tax. Dashboard total excludes pension (tracked separately)."""


BACKEND_API_CATALOG = {
    "auth": ["POST /api/login", "POST /api/register", "POST /api/account/password", "DELETE /api/account"],
    "portfolio": [
        "GET /api/data?horizon=&assumed_annual_pct= — composed holdings + projections/what-if",
        "POST /api/sync — refresh gemelnet/pensia/Yahoo caches then return composed state",
        "GET /api/export / POST /api/import",
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
        "POST /api/chat — this assistant; may call project_portfolio tool",
    ],
    "projection_rules": {
        "what_if_annual_pct": "Compounds funds (and pension what-if) at assumed %; cash+ESPP flat; RSU vesting curve at current price/FX",
        "historical_default": "Without assumed %, funds use historical average monthly return from gemelnet/pensia",
        "horizon_cap_months": HORIZON_CAP_MONTHS,
        "pension": "Excluded from dashboard total; surfaced separately in pension_summary",
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
                "name": "describe_backend_apis",
                "description": "Describe Saving Tracker backend REST APIs and projection rules.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]
    }
]


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
        "total_deposited_ils": _round_or_none(computed.get("total_deposited_ils")),
        "total_employee_ils": _round_or_none(computed.get("total_employee_ils")),
        "total_employer_ils": _round_or_none(computed.get("total_employer_ils")),
        "yield_is_net_of_fees": h.get("yield_is_net_of_fees"),
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
    # User-entered management fees (דמי ניהול מצבירה / מהפקדה). These are the
    # user's OWN estimates, NOT the actual fees charged by the fund/insurer.
    fee_schedule = h.get("fee_schedule") or []
    eff = computed.get("effective_fee") or {}
    cum_mgmt = computed.get("cumulative_mgmt_fee_ils")
    cum_dep = computed.get("cumulative_deposit_fee_ils")
    if fee_schedule or eff or cum_mgmt or cum_dep:
        out["user_mgmt_fees"] = {
            "note": "User-entered estimate — NOT the actual fee charged by the fund/insurer. "
                    "Verify against official statements. When set, the published yield is "
                    "treated as GROSS for this holding (overrides yield_is_net_of_fees).",
            "effective_balance_fee_pct_annual": _round_or_none(eff.get("balance_pct"), 4),
            "effective_deposit_fee_pct": _round_or_none(eff.get("deposit_pct"), 4),
            "estimated_cumulative_balance_fee_ils": _round_or_none(cum_mgmt),
            "estimated_cumulative_deposit_fee_ils": _round_or_none(cum_dep),
            "fee_change_points": len(fee_schedule),
        }
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


def build_portfolio_context(state: dict) -> dict:
    """Compact snapshot for the model — no time series / monthly caches."""
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
        "holdings": {
            "funds": funds,
            "pensions": pensions,
            "rsu": rsus,
            "espp": espps,
            "cash": cash,
        },
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
    if name == "project_portfolio":
        return run_project_portfolio_tool(compose_fn, args or {})
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


DAILY_INSIGHTS_PROMPT = """You write a short daily email insight for a personal Israeli savings tracker.
Use ONLY the portfolio JSON provided. Educational only — not financial, tax, or legal advice.
Focus on allocation, recent returns if present, concentration, vesting/RSU/ESPP, cash buffer, and one optional observation about growth. You may mention a holding's `user_mgmt_fees` only if notable, but state they are the user's own estimates (not the actual fees charged).
Write 3 short bullet points (plain text with leading "- "). Max ~80 words total. Match the language of any Hebrew nicknames if the data is mostly Hebrew; otherwise English."""


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
                            "Write today's portfolio insights from this JSON:\n"
                            f"{context_json}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 280,
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
    "Do not add, remove, reorder, or reinterpret any content. Keep numbers and\n"
    "currency symbols unchanged. Output only the translation, nothing else."
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
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 400},
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
