"""Portfolio AI chat via Google Gemini (HTTP generateContent)."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

MAX_HISTORY = 10
MAX_OUTPUT_TOKENS = 768
REQUEST_TIMEOUT = 45


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip() or "gemini-3.1-flash-lite"


SYSTEM_PROMPT = """You are a helpful assistant inside Saving Tracker, a personal Israeli portfolio notebook.
You receive a compact JSON summary of the user's holdings (קופות גמל / השתלמות via gemelnet, pension via pensia-net, RSU, ESPP, cash).

Guidelines:
- Answer using the provided portfolio data and general public knowledge about Israeli gemel/pension/RSU/ESPP.
- Suggest concrete, educational improvements when asked (fees, concentration, contribution cadence, vesting, diversification clues). Keep suggestions short and numbered.
- Match the user's language (Hebrew or English).
- Keep replies concise (a few short paragraphs or bullets).
- You are NOT a licensed financial, tax, investment, or legal advisor. Never claim otherwise.
- Figures may be incomplete or stale; remind the user to verify against official statements when decisions matter.
- Do not invent holdings or numbers that are not in the context. If data is missing, say so.
- This app does not model Israeli tax."""


def chat_enabled() -> bool:
    return _truthy_env("CHAT_ENABLED") and bool(_gemini_api_key())


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
        "cumulative_mgmt_fee_ils": _round_or_none(computed.get("cumulative_mgmt_fee_ils")),
        "last_period": computed.get("last_period"),
    }
    if metrics:
        out["avg_annual_management_fee_pct"] = _round_or_none(
            metrics.get("avg_annual_management_fee_pct"), 4
        )
        out["avg_deposit_fee_pct"] = _round_or_none(metrics.get("avg_deposit_fee_pct"), 4)
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


def _extract_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        block = (payload.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise RuntimeError(f"Gemini blocked the prompt ({block})")
        raise RuntimeError("Gemini returned no candidates")
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    texts = [p.get("text") for p in parts if isinstance(p, dict) and p.get("text")]
    if not texts:
        raise RuntimeError("Gemini returned an empty reply")
    return "\n".join(texts).strip()


def call_gemini(*, context: dict, messages: list[dict]) -> str:
    api_key = _gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    model = _gemini_model()
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    contents = _to_gemini_contents(messages)
    if not contents or contents[-1]["role"] != "user":
        raise ValueError("Conversation must end with a user message")

    system_text = (
        f"{SYSTEM_PROMPT}\n\n"
        "Current portfolio summary (JSON). Use this as ground truth for numbers:\n"
        f"{context_json}"
    )

    url = GEMINI_URL.format(model=model)
    body = {
        "systemInstruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
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
        detail = r.text[:500]
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {detail}")
    return _extract_text(r.json())


def run_chat(state: dict, messages_raw: Any) -> dict:
    """Returns {ok, reply} or {ok: False, error}."""
    if not chat_enabled():
        return {"ok": False, "error": "chat_disabled"}

    messages = _normalize_messages(messages_raw)
    if not messages:
        return {"ok": False, "error": "No messages provided"}
    if messages[-1]["role"] != "user":
        return {"ok": False, "error": "Last message must be from the user"}

    context = build_portfolio_context(state)
    try:
        reply = call_gemini(context=context, messages=messages)
    except Exception as ex:
        return {"ok": False, "error": str(ex)}
    return {"ok": True, "reply": reply, "model": _gemini_model()}
