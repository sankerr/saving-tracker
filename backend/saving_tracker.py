#!/usr/bin/env python3
"""
Saving Tracker - single-file local web UI.

Tracks long-term savings:
  - Israeli pension/provident/study funds (קופות גמל / קרנות פנסיה /
    קרנות השתלמות) via the public gemelnet dataset on data.gov.il
  - RSU grants priced from Yahoo Finance (stock + USDILS), with vesting
    schedules, optional FMV cost-basis override, and dated sale events
  - Cash / non-invested balances (ILS or USD with auto-FX conversion)

Cloud deployment — portfolio data in PostgreSQL (Neon), simple JWT auth.

Env:
    DATABASE_URL       PostgreSQL connection string (required)
    SESSION_SECRET     JWT signing secret (required)
    CORS_ORIGIN        Frontend origin, e.g. https://your-app.pages.dev
    ADMIN_USERNAME     Seed user on first boot (optional if user exists)
    ADMIN_PASSWORD     Seed password on first boot
    CHAT_ENABLED       Set true to enable portfolio AI chat (requires GEMINI_API_KEY)
    GEMINI_API_KEY     Google AI Studio API key for Gemini chat
    GEMINI_MODEL       Optional model id (default: gemini-3.1-flash-lite)

Usage:
    ./saving-tracker.py           # or: python3 saving-tracker.py
The browser opens automatically. Ctrl+C in the terminal stops the server.

Key behavior:
  - Deposits / rule contributions / withdrawals apply at END of their period
    (they don't earn or lose the same month's yield).
  - gemelnet's MONTHLY_YIELD is typically already NET OF FEES; the default
    "yield_is_net_of_fees" toggle reflects that. ~Mgmt fees paid is shown
    informationally per holding (not double-deducted).
  - Hard delete with confirm-modal — no archive flow.
  - Past performance is not indicative of future results.
  - This app is informational only and does NOT compute Israeli tax.
"""

import http.server
import json
import math
import os
import secrets
import statistics
import sys
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

import auth
import chat as portfolio_chat
import db
import notify


# ── Config ───────────────────────────────────────────────────────────────────
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "").rstrip("/")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
ACTIVE_USER_ID: int | None = None

GEMELNET_PACKAGE_ID = "gemelnet"
PENSIA_PACKAGE_ID = "pensia-net"
INSURANCE_PACKAGE_ID = "insurance"
GEMELNET_ACTION = "https://data.gov.il/api/3/action"

# Per-source config for the gemelnet/pensia/insurance datasets (same CKAN host + schema).
SOURCE_CONFIG = {
    "gemelnet": {
        "package_id": GEMELNET_PACKAGE_ID,
        "package_cache_key": "package_show",
        "monthly_cache_key": "fund_monthly",
    },
    "pensia": {
        "package_id": PENSIA_PACKAGE_ID,
        "package_cache_key": "pensia_package_show",
        "monthly_cache_key": "pensia_monthly",
    },
    "insurance": {
        "package_id": INSURANCE_PACKAGE_ID,
        "package_cache_key": "insurance_package_show",
        "monthly_cache_key": "insurance_monthly",
    },
}
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
YAHOO_QUOTE_SUMMARY = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
ANALYST_TARGET_TTL_SECONDS = 24 * 3600
PACKAGE_SHOW_TTL = 24 * 3600
SYNC_PAGE_PAUSE = 0.2
HTTP_TIMEOUT = 25
HORIZON_CAP_MONTHS = 600  # 50 years — covers any retirement horizon the picker might ask for

USER_AGENT = "Mozilla/5.0 (saving-tracker; local app)"

# Upstream column names (the misspelling 'WITHDRAWLS' is preserved as-is).
COL_FUND_ID = "FUND_ID"
COL_FUND_NAME = "FUND_NAME"
COL_MANAGING_CORP = "MANAGING_CORPORATION"
COL_PARENT_COMPANY = "PARENT_COMPANY_NAME"
COL_CONTROLLING_CORP = "CONTROLLING_CORPORATION"
COL_CLASSIFICATION = "FUND_CLASSIFICATION"
COL_SPECIALIZATION = "SPECIALIZATION"
COL_SUB_SPEC = "SUB_SPECIALIZATION"
COL_TARGET_POP = "TARGET_POPULATION"
COL_REPORT_PERIOD = "REPORT_PERIOD"
COL_TOTAL_ASSETS = "TOTAL_ASSETS"
COL_AVG_FEE = "AVG_ANNUAL_MANAGEMENT_FEE"
COL_DEPOSIT_FEE = "AVG_DEPOSIT_FEE"
COL_MONTHLY_YIELD = "MONTHLY_YIELD"
COL_YTD_YIELD = "YEAR_TO_DATE_YIELD"
COL_3Y_YIELD = "YIELD_TRAILING_3_YRS"
COL_5Y_YIELD = "YIELD_TRAILING_5_YRS"


# ── Default state factories ──────────────────────────────────────────────────
def default_data() -> dict:
    return {
        "version": 1,
        "settings": {
            "yield_is_net_of_fees": True,
            "usdils_rate_override": None,
        },
        "fund_holdings": [],
        "pension_holdings": [],
        "rsu_grants": [],
        "cash_holdings": [],
        "espp_plans": [],
    }


def default_market() -> dict:
    """Shared, public market data — identical for every user.

    Keyed by fund_id / ticker (or global), so it lives in a single shared row
    rather than being duplicated in every user's cache blob.
    """
    return {
        "version": 1,
        "package_show": None,
        "fund_monthly": {},
        "pensia_package_show": None,
        "pensia_monthly": {},
        "insurance_package_show": None,
        "insurance_monthly": {},
        "stock_daily": {},
        "fx": {},
        "analyst_targets": {},
    }


def default_user_cache() -> dict:
    """Per-user cache metadata (small, user-specific)."""
    return {
        "version": 1,
        "last_full_sync_at": None,
        "last_full_sync_ts": None,
        "last_notified_period": None,
    }


# ── Locks & in-process state ─────────────────────────────────────────────────
_data_lock = threading.RLock()
_cache_lock = threading.RLock()
_market_lock = threading.RLock()
_user_ctx_lock = threading.RLock()
_sync_lock = threading.Lock()
_search_cache: dict = {}     # {query_key: (ts, [hits])}
_sync_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "ok_at": None,
    "error": None,
    "step": None,
}
_cron_job_lock = threading.Lock()
_cron_status = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "results": None,
}


# ── JSON I/O (atomic) ────────────────────────────────────────────────────────
def _load_json(path: Path, default_factory):
    if not path.exists():
        return default_factory()
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict) or "version" not in payload:
            return default_factory()
        return payload
    except (json.JSONDecodeError, OSError):
        try:
            backup = path.with_suffix(path.suffix + f".broken-{int(time.time())}")
            path.rename(backup)
        except OSError:
            pass
        return default_factory()


def _save_json(path: Path, payload: dict):
    # Process-unique tmp filename so concurrent writers can't truncate each
    # other's mid-flight file (defense-in-depth on top of the singleton lock).
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)




DATA: dict = default_data()
CACHE: dict = default_user_cache()
MARKET: dict = default_market()


def _migrate_state_payload() -> None:
    """Forward-migrate missing keys for the active user's DATA + per-user CACHE."""
    for _k, _v in default_data().items():
        DATA.setdefault(_k, _v if not isinstance(_v, (list, dict)) else type(_v)())
        if isinstance(_v, list) and not isinstance(DATA.get(_k), list):
            DATA[_k] = []
    for _k, _v in default_user_cache().items():
        CACHE.setdefault(_k, _v)
    # Legacy per-user caches carried the shared market keys; they now live in
    # MARKET. Drop them here so the next save_cache() writes the slim blob.
    for _k in default_market():
        if _k != "version":
            CACHE.pop(_k, None)


def _migrate_market_payload() -> None:
    """Forward-migrate missing keys in the shared MARKET blob."""
    for _k, _v in default_market().items():
        if isinstance(_v, dict):
            MARKET.setdefault(_k, {})
        elif _v is None:
            MARKET.setdefault(_k, None)
        else:
            MARKET.setdefault(_k, _v)


def save_data():
    with _data_lock:
        if ACTIVE_USER_ID is not None:
            db.save_data_state(ACTIVE_USER_ID, DATA)


def save_cache():
    with _cache_lock:
        if ACTIVE_USER_ID is not None:
            db.save_cache_state(ACTIVE_USER_ID, CACHE)


def save_market():
    with _market_lock:
        db.save_shared_cache(MARKET)


def bootstrap_storage() -> None:
    global MARKET
    if not db.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")
    if not auth.SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET is required")

    db.init_schema()

    # Load the shared market cache once. When it doesn't exist yet, seed it from
    # the most-recently-synced user's cache blob so the first cron isn't a full
    # cold refetch; otherwise start blank and repopulate on first sync.
    loaded_market = db.load_shared_cache()
    seeded = False
    if not loaded_market:
        loaded_market = db.load_seed_cache_from_users()
        seeded = bool(loaded_market)
    with _market_lock:
        MARKET = default_market()
        for _k in default_market():
            if _k != "version" and _k in loaded_market:
                MARKET[_k] = loaded_market[_k]
        _migrate_market_payload()
    db.save_shared_cache(MARKET)
    if seeded:
        print("bootstrap: seeded shared market cache from an existing user's cache")

    if db.user_count() == 0:
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not username or not password:
            raise RuntimeError(
                "No users in database. Set ADMIN_USERNAME and ADMIN_PASSWORD for first boot."
            )
        if not auth.is_valid_email(username):
            raise RuntimeError("ADMIN_USERNAME must be a valid email address")
        user_id = db.create_user(username, auth.hash_password(password), approved=True)
        print(f"Created admin user: {username} (id={user_id}, approved=true)")


def _activate_user(user_id: int) -> None:
    global DATA, CACHE, ACTIVE_USER_ID
    if ACTIVE_USER_ID == user_id:
        return
    loaded_data, loaded_cache = db.load_state(user_id)
    with _data_lock:
        DATA = loaded_data if loaded_data else default_data()
        CACHE = loaded_cache if loaded_cache else default_user_cache()
        _migrate_state_payload()
        ACTIVE_USER_ID = user_id
    if not loaded_data:
        db.save_data_state(user_id, DATA)
    if not loaded_cache:
        db.save_cache_state(user_id, CACHE)


def _validate_username(username: str) -> str | None:
    if not auth.is_valid_email(username):
        return "Username must be a valid email address"
    return None


def _validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters"
    return None


# ── Date / period helpers ────────────────────────────────────────────────────
def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def synced_today() -> bool:
    ts = CACHE.get("last_full_sync_ts")
    if not ts:
        return False
    return datetime.fromtimestamp(ts).date() == date.today()


def _ts_is_today(ts) -> bool:
    """True when a Unix timestamp falls on the current local date."""
    if not ts:
        return False
    try:
        return datetime.fromtimestamp(float(ts)).date() == date.today()
    except (TypeError, ValueError, OSError):
        return False


def latest_published_period() -> int | None:
    """Latest REPORT_PERIOD present in any synced fund/pension/insurance cache."""
    latest = 0
    for key in ("fund_monthly", "pensia_monthly", "insurance_monthly"):
        for entry in (MARKET.get(key) or {}).values():
            lp = int(entry.get("last_seen_period") or 0)
            if lp > latest:
                latest = lp
    return latest if latest > 0 else None


def period_iter(start: int, end: int):
    """Yield YYYYMM ints from start..end inclusive."""
    if end < start:
        return
    y, m = divmod(start, 100)
    while True:
        yield y * 100 + m
        if y * 100 + m == end:
            return
        m += 1
        if m > 12:
            m = 1
            y += 1


def date_period(d: date) -> int:
    return d.year * 100 + d.month


def current_period() -> int:
    return date_period(date.today())


def period_to_yyyymm(period: int) -> str:
    return f"{period // 100:04d}-{period % 100:02d}"


# ── HTTP helper with retry/backoff ───────────────────────────────────────────
def http_get(url, *, params=None, timeout=HTTP_TIMEOUT, max_retries=3, headers=None):
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    last_err = None
    delay = 0.5
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
            if 500 <= r.status_code < 600:
                last_err = RuntimeError(f"HTTP {r.status_code}")
                time.sleep(delay)
                delay *= 3
                continue
            r.raise_for_status()
            return r
        except (requests.exceptions.RequestException, RuntimeError) as ex:
            last_err = ex
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 3
    raise last_err if last_err else RuntimeError("HTTP failed")


def _to_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Gemelnet / Pensia client ─────────────────────────────────────────────────
def get_resource_ids(force=False, source: str = "gemelnet") -> dict:
    cfg = SOURCE_CONFIG[source]
    pkg_key = cfg["package_cache_key"]
    with _market_lock:
        ps = MARKET.get(pkg_key)
        if (not force) and ps and (time.time() - ps.get("fetched_at_ts", 0) < PACKAGE_SHOW_TTL):
            return ps["resources"]
    r = http_get(f"{GEMELNET_ACTION}/package_show", params={"id": cfg["package_id"]})
    pkg = r.json()
    if not pkg.get("success"):
        raise RuntimeError(f"package_show failed for {source}")
    out = {}
    for entry in pkg["result"].get("resources", []):
        rid = entry.get("id")
        name = entry.get("name", "")
        if not rid or not entry.get("datastore_active"):
            continue
        if "1999" in name and "2022" in name:
            out["1999_2022"] = rid
        elif "2023" in name:
            out["2023"] = rid
        elif "2024" in name or "היום" in name:
            out["current"] = rid
    if "current" not in out:
        raise RuntimeError(f"Could not locate current {source} resource")
    with _market_lock:
        MARKET[pkg_key] = {
            "fetched_at": now_iso(),
            "fetched_at_ts": time.time(),
            "resources": out,
        }
        save_market()
    return out


def fund_holding_source(holding: dict) -> str:
    """Upstream dataset key for a fund holding (gemelnet or insurance)."""
    src = (holding.get("data_source") or "gemelnet").strip()
    return src if src in SOURCE_CONFIG else "gemelnet"


def _search_hit_from_row(row: dict, period: int, source: str) -> dict:
    if source == "insurance":
        manager = (row.get(COL_PARENT_COMPANY) or "").strip()
    else:
        manager = (row.get(COL_MANAGING_CORP) or "").strip()
    return {
        "fund_id": int(row.get(COL_FUND_ID)),
        "fund_name": (row.get(COL_FUND_NAME) or "").strip(),
        "managing_corporation": manager,
        "classification": (row.get(COL_CLASSIFICATION) or "").strip(),
        "specialization": (row.get(COL_SPECIALIZATION) or "").strip(),
        "sub_specialization": (row.get(COL_SUB_SPEC) or "").strip(),
        "target_population": (row.get(COL_TARGET_POP) or "").strip(),
        "last_period": period,
        "data_source": source,
    }


def gemelnet_search(q: str, limit: int = 20, source: str = "gemelnet") -> list:
    """Free-text or FUND_ID search on the current resource of `source`."""
    q = (q or "").strip()
    if not q:
        return []
    cache_key = f"search:{source}:{q}:{limit}"
    now = time.time()
    cached = _search_cache.get(cache_key)
    if cached and now - cached[0] < 120:
        return cached[1]
    res_ids = get_resource_ids(source=source)
    params = {"resource_id": res_ids["current"], "limit": min(limit * 5, 200)}
    if q.isdigit():
        params["filters"] = json.dumps({"FUND_ID": int(q)})
    else:
        params["q"] = q
    r = http_get(f"{GEMELNET_ACTION}/datastore_search", params=params)
    body = r.json()
    if not body.get("success"):
        return []
    records = body["result"].get("records", [])
    seen = {}
    for row in records:
        try:
            fid = int(row.get(COL_FUND_ID))
        except (TypeError, ValueError):
            continue
        period = int(row.get(COL_REPORT_PERIOD) or 0)
        if fid not in seen or period > seen[fid][0]:
            seen[fid] = (period, row)
    out = []
    for fid, (period, row) in seen.items():
        out.append(_search_hit_from_row(row, period, source))
    out.sort(key=lambda x: x["fund_name"])
    out = out[:limit]
    _search_cache[cache_key] = (now, out)
    return out


def funds_search(q: str, limit: int = 20) -> list:
    """Search gemelnet + insurance (ביטוח-נט / פוליסות חיסכון) for the Add Fund UI."""
    q = (q or "").strip()
    if not q:
        return []
    per_source = max(limit, 10)
    gemel_hits = gemelnet_search(q, limit=per_source, source="gemelnet")
    insurance_hits = gemelnet_search(q, limit=per_source, source="insurance")
    merged = gemel_hits + insurance_hits
    merged.sort(key=lambda x: (x["fund_name"], x["data_source"]))
    return merged[:limit]


def gemelnet_fetch_history(fund_id: int, *, full=False, source: str = "gemelnet"):
    """Pull all monthly rows for fund_id from `source` and merge into cache."""
    cfg = SOURCE_CONFIG[source]
    monthly_key = cfg["monthly_cache_key"]
    res_ids = get_resource_ids(source=source)
    with _market_lock:
        existing = MARKET[monthly_key].get(str(fund_id))
        last_seen = (existing or {}).get("last_seen_period", 0)
    # Shared cache: if another user already refreshed this fund today, reuse it
    # instead of hitting data.gov.il again.
    if not full and existing and _ts_is_today(existing.get("last_synced_ts")):
        return existing.get("rows", [])
    if full or not last_seen:
        resources_to_pull = ["1999_2022", "2023", "current"]
    elif last_seen < 202301:
        resources_to_pull = ["2023", "current"]
    elif last_seen < 202401:
        resources_to_pull = ["2023", "current"]
    else:
        resources_to_pull = ["current"]
    rows_by_period = {}
    if existing:
        for r in existing.get("rows", []):
            rows_by_period[int(r["report_period"])] = r
    for resource_key in resources_to_pull:
        rid = res_ids.get(resource_key)
        if not rid:
            continue
        offset = 0
        while True:
            r = http_get(
                f"{GEMELNET_ACTION}/datastore_search",
                params={
                    "resource_id": rid,
                    "filters": json.dumps({"FUND_ID": fund_id}),
                    "limit": 32000,
                    "offset": offset,
                    "sort": "REPORT_PERIOD asc",
                },
            )
            body = r.json()
            if not body.get("success"):
                break
            recs = body["result"].get("records", [])
            for raw in recs:
                period = int(raw.get(COL_REPORT_PERIOD) or 0)
                if not period:
                    continue
                rows_by_period[period] = {
                    "report_period": period,
                    "monthly_yield": _to_float(raw.get(COL_MONTHLY_YIELD)),
                    "ytd_yield": _to_float(raw.get(COL_YTD_YIELD)),
                    "avg_annual_management_fee": _to_float(raw.get(COL_AVG_FEE)),
                    "total_assets": _to_float(raw.get(COL_TOTAL_ASSETS)),
                    "raw": raw,
                }
            if len(recs) < 32000:
                break
            offset += 32000
            time.sleep(SYNC_PAGE_PAUSE)
    rows_sorted = sorted(rows_by_period.values(), key=lambda r: r["report_period"])
    last_period = rows_sorted[-1]["report_period"] if rows_sorted else 0
    fund_meta = None
    if rows_sorted:
        last_raw = rows_sorted[-1]["raw"]
        if source == "insurance":
            manager = (last_raw.get(COL_PARENT_COMPANY) or "").strip()
        else:
            manager = (last_raw.get(COL_MANAGING_CORP) or "").strip()
        fund_meta = {
            "fund_name": (last_raw.get(COL_FUND_NAME) or "").strip(),
            "managing_corporation": manager,
            "classification": (last_raw.get(COL_CLASSIFICATION) or "").strip(),
            "specialization": (last_raw.get(COL_SPECIALIZATION) or "").strip(),
            "sub_specialization": (last_raw.get(COL_SUB_SPEC) or "").strip(),
            "target_population": (last_raw.get(COL_TARGET_POP) or "").strip(),
        }
    with _market_lock:
        MARKET[monthly_key][str(fund_id)] = {
            "last_synced": now_iso(),
            "last_synced_ts": time.time(),
            "last_seen_period": last_period,
            "meta": fund_meta,
            "rows": rows_sorted,
        }
        save_market()
    return rows_sorted


# ── Yahoo client ─────────────────────────────────────────────────────────────
def yahoo_chart(ticker: str, *, period1: int, period2: int, interval="1d") -> dict:
    url = YAHOO_CHART.format(ticker=ticker)
    r = http_get(
        url,
        params={"period1": period1, "period2": period2, "interval": interval, "events": "history"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    body = r.json()
    chart = body.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(f"Yahoo error: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo: no data for {ticker}")
    res = results[0]
    timestamps = res.get("timestamp") or []
    quote_block = res.get("indicators", {}).get("quote") or [{}]
    closes = quote_block[0].get("close") or []
    rows = []
    for ts, c in zip(timestamps, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        rows.append({"date": d, "close": float(c)})
    rows.sort(key=lambda x: x["date"])
    currency = (res.get("meta") or {}).get("currency", "USD")
    return {"rows": rows, "currency": currency}


def yahoo_search_ticker(q: str, limit: int = 10) -> list:
    """Symbol-search via Yahoo's autocomplete endpoint."""
    q = (q or "").strip()
    if not q:
        return []
    cache_key = f"yahoo_search:{q}:{limit}"
    now = time.time()
    cached = _search_cache.get(cache_key)
    if cached and now - cached[0] < 120:
        return cached[1]
    r = http_get(
        "https://query2.finance.yahoo.com/v1/finance/search",
        params={"q": q, "quotesCount": min(limit * 2, 20), "newsCount": 0},
        headers={"User-Agent": USER_AGENT},
    )
    body = r.json()
    quotes = body.get("quotes") or []
    out = []
    for qd in quotes:
        sym = qd.get("symbol")
        if not sym:
            continue
        out.append({
            "symbol": sym,
            "name": qd.get("shortname") or qd.get("longname") or "",
            "exchange": qd.get("exchange") or "",
            "type": qd.get("quoteType") or "",
        })
    # Prefer EQUITY on common US exchanges
    def rank(item):
        is_equity = item["type"] == "EQUITY"
        is_us = item["exchange"] in ("NMS", "NYQ", "NGM", "ASE", "PCX", "NCM")
        return (-int(is_equity), -int(is_us))
    out.sort(key=rank)
    out = out[:limit]
    _search_cache[cache_key] = (now, out)
    return out


def yahoo_fetch_stock(ticker: str, since_iso: str, *, force: bool = False):
    # Pull at least 13 months back so the per-RSU "stock price (last 12
    # months)" mini-chart on the dashboard always has a full year of data,
    # even for a same-day or weekend grant. 13 months gives a small buffer
    # so weekends/holidays at the edge don't truncate the view.
    since_d = datetime.fromisoformat(since_iso)
    min_back = datetime.now() - timedelta(days=395)
    if since_d > min_back:
        since_d = min_back
    # Shared cache: reuse another user's same-day fetch, but only when it already
    # covers the requested start date (different users may need different history).
    want_from = since_d.date().isoformat()
    with _market_lock:
        existing = MARKET["stock_daily"].get(ticker)
    if not force and existing and _ts_is_today(existing.get("last_synced_ts")):
        rows = existing.get("rows") or []
        covered_from = rows[0]["date"] if rows else None
        if covered_from and covered_from <= want_from:
            return rows
    period1 = int(since_d.timestamp())
    period2 = int(time.time())
    out = yahoo_chart(ticker, period1=period1, period2=period2, interval="1d")
    with _market_lock:
        MARKET["stock_daily"][ticker] = {
            "last_synced": now_iso(),
            "last_synced_ts": time.time(),
            "currency": out["currency"],
            "rows": out["rows"],
        }
        save_market()
    return out["rows"]


_yahoo_session = None
_yahoo_crumb = None


def _yahoo_ensure_crumb():
    """Yahoo's quoteSummary endpoint requires a session cookie + 'crumb' token.
    Lazy-initialized and cached for the process lifetime; on 401 the caller
    should invalidate (`_yahoo_crumb = None`) and retry once.
    Returns (session, crumb) or (None, None) on failure."""
    global _yahoo_session, _yahoo_crumb
    if _yahoo_session is None:
        _yahoo_session = requests.Session()
        _yahoo_session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
        })
    if _yahoo_crumb:
        return _yahoo_session, _yahoo_crumb
    try:
        # Hit fc.yahoo.com to get session cookies (A1, A3, etc.)
        _yahoo_session.get("https://fc.yahoo.com/", timeout=HTTP_TIMEOUT)
        # Trade cookies for a crumb token
        r = _yahoo_session.get(
            "https://query2.finance.yahoo.com/v1/test/getcrumb",
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code == 200 and r.text and r.text.strip():
            _yahoo_crumb = r.text.strip()
            return _yahoo_session, _yahoo_crumb
    except Exception:
        pass
    return None, None


def yahoo_fetch_analyst_target(ticker: str) -> dict:
    """Fetch sell-side analyst 12-month price target consensus for `ticker`.
    Returns the cached dict on success or None on any failure / no coverage.
    Cached in MARKET['analyst_targets'][TICKER] for ANALYST_TARGET_TTL_SECONDS.
    Best-effort: tickers with no analyst coverage (small/recent IPOs) and any
    network/HTTP error all yield None without raising. Uses Yahoo's
    cookie+crumb session flow because the v10 quoteSummary endpoint requires
    it (returns 401 'Invalid Crumb' otherwise)."""
    global _yahoo_crumb
    tk = ticker.upper().strip()
    body = None
    for attempt in range(2):
        session, crumb = _yahoo_ensure_crumb()
        if not session or not crumb:
            return None
        try:
            r = session.get(
                YAHOO_QUOTE_SUMMARY.format(ticker=tk),
                params={"modules": "financialData", "crumb": crumb},
                timeout=HTTP_TIMEOUT,
            )
            if r.status_code == 401:
                # Crumb expired — invalidate and retry once.
                _yahoo_crumb = None
                continue
            if r.status_code != 200:
                return None
            body = r.json()
            break
        except Exception:
            return None
    if not body:
        return None
    qs = body.get("quoteSummary") or {}
    if qs.get("error"):
        return None
    results = qs.get("result") or []
    if not results:
        return None
    fd = results[0].get("financialData") or {}

    def _raw(key):
        v = fd.get(key)
        if isinstance(v, dict):
            return v.get("raw")
        return v

    target_mean = _raw("targetMeanPrice")
    if target_mean is None:
        return None
    out = {
        "target_mean": float(target_mean),
        "target_median": float(_raw("targetMedianPrice")) if _raw("targetMedianPrice") is not None else None,
        "target_high": float(_raw("targetHighPrice")) if _raw("targetHighPrice") is not None else None,
        "target_low": float(_raw("targetLowPrice")) if _raw("targetLowPrice") is not None else None,
        "num_analysts": int(_raw("numberOfAnalystOpinions") or 0) or None,
        "currency": _raw("financialCurrency") or "USD",
        "fetched_at": now_iso(),
        "fetched_at_ts": time.time(),
    }
    with _market_lock:
        MARKET.setdefault("analyst_targets", {})[tk] = out
        save_market()
    return out


def yahoo_fetch_fx_usdils(since_iso: str = None, *, force: bool = False):
    if since_iso is None:
        since_iso = (date.today() - timedelta(days=365 * 5)).isoformat()
    want_from = datetime.fromisoformat(since_iso).date().isoformat()
    # Shared cache: reuse a same-day FX fetch that already covers the range.
    with _market_lock:
        existing = MARKET["fx"].get("USDILS")
    if not force and existing and _ts_is_today(existing.get("last_synced_ts")):
        rows = existing.get("rows") or []
        covered_from = rows[0]["date"] if rows else None
        if covered_from and covered_from <= want_from:
            return
    period1 = int(datetime.fromisoformat(since_iso).timestamp())
    period2 = int(time.time())
    out = yahoo_chart("ILS=X", period1=period1, period2=period2, interval="1d")
    with _market_lock:
        MARKET["fx"]["USDILS"] = {
            "last_synced": now_iso(),
            "last_synced_ts": time.time(),
            "rows": out["rows"],
        }
        save_market()
    return out["rows"]


# ── Sync orchestrator ────────────────────────────────────────────────────────
def run_sync(*, force=False) -> dict:
    if not _sync_lock.acquire(blocking=False):
        return {"ok": False, "error": "Sync already running"}
    try:
        _sync_status.update({
            "running": True,
            "started_at": now_iso(),
            "finished_at": None,
            "error": None,
            "step": "package_show",
        })
        get_resource_ids(force=force)

        with _data_lock:
            fund_ids = sorted({h["fund_id"] for h in DATA["fund_holdings"] if not h.get("archived")})
            fund_ids_by_source = {}
            for h in DATA["fund_holdings"]:
                if h.get("archived"):
                    continue
                src = fund_holding_source(h)
                fund_ids_by_source.setdefault(src, set()).add(h["fund_id"])
            pension_ids = sorted({h["fund_id"] for h in DATA.get("pension_holdings", []) or [] if not h.get("archived")})
            grants_active = [g for g in DATA["rsu_grants"] if not g.get("archived")]
            espp_active = [p for p in DATA.get("espp_plans", []) or [] if not p.get("archived")]
            # Tickers & earliest-known dates from BOTH RSU grants and ESPP plans.
            grants_by_ticker = {}
            for g in grants_active:
                grants_by_ticker.setdefault(g["ticker"].upper(), []).append(g["grant_date"])
            for plan in espp_active:
                tk = plan["ticker"].upper()
                purchases = plan.get("purchases", []) or []
                earliest_p = min((p["date"] for p in purchases), default=None)
                if earliest_p:
                    grants_by_ticker.setdefault(tk, []).append(earliest_p)
                else:
                    # No purchases yet — at least fetch the last ~year so the plan
                    # has a price to show.
                    grants_by_ticker.setdefault(tk, []).append(
                        (date.today() - timedelta(days=400)).isoformat()
                    )
            tickers = sorted(grants_by_ticker.keys())

        for src, ids in fund_ids_by_source.items():
            if src != "gemelnet":
                _sync_status["step"] = f"{src}_package_show"
                try:
                    get_resource_ids(force=force, source=src)
                except Exception as ex:
                    _sync_status["error"] = f"{src} package_show: {ex}"
            for fid in sorted(ids):
                _sync_status["step"] = f"fund {fid} ({src})"
                try:
                    gemelnet_fetch_history(fid, full=force, source=src)
                except Exception as ex:
                    _sync_status["error"] = f"fund {fid} ({src}): {ex}"
                time.sleep(SYNC_PAGE_PAUSE)

        if pension_ids:
            _sync_status["step"] = "pensia_package_show"
            try:
                get_resource_ids(force=force, source="pensia")
            except Exception as ex:
                _sync_status["error"] = f"pensia package_show: {ex}"
            for fid in pension_ids:
                _sync_status["step"] = f"pension {fid}"
                try:
                    gemelnet_fetch_history(fid, full=force, source="pensia")
                except Exception as ex:
                    _sync_status["error"] = f"pension {fid}: {ex}"
                time.sleep(SYNC_PAGE_PAUSE)

        for tk in tickers:
            _sync_status["step"] = f"ticker {tk}"
            try:
                earliest = min(grants_by_ticker[tk])
                yahoo_fetch_stock(tk, earliest, force=force)
            except Exception as ex:
                _sync_status["error"] = f"ticker {tk}: {ex}"
            # Best-effort analyst target — never fails the sync. TTL 24h.
            cached_at = ((MARKET.get("analyst_targets") or {}).get(tk) or {}).get("fetched_at_ts") or 0
            if force or (time.time() - cached_at) > ANALYST_TARGET_TTL_SECONDS:
                yahoo_fetch_analyst_target(tk)
            time.sleep(SYNC_PAGE_PAUSE)

        # Always refresh FX so cash USD entries (and future RSU grants) have a rate.
        with _data_lock:
            has_usd_cash = any(
                (c.get("currency") or "ILS").upper() == "USD" and not c.get("archived")
                for c in DATA.get("cash_holdings", []) or []
            )
        if tickers or has_usd_cash:
            _sync_status["step"] = "USDILS"
            try:
                if tickers:
                    earliest_grant = min(min(d) for d in grants_by_ticker.values())
                    buffered = (date.fromisoformat(earliest_grant) - timedelta(days=365)).isoformat()
                    yahoo_fetch_fx_usdils(buffered, force=force)
                else:
                    yahoo_fetch_fx_usdils(force=force)
            except Exception as ex:
                _sync_status["error"] = f"USDILS: {ex}"

        ok_at = now_iso()
        _sync_status["ok_at"] = ok_at
        with _cache_lock:
            CACHE["last_full_sync_at"] = ok_at
            CACHE["last_full_sync_ts"] = time.time()
        save_cache()
        return {"ok": True}
    except Exception as ex:
        _sync_status["error"] = str(ex)
        return {"ok": False, "error": str(ex)}
    finally:
        _sync_status["running"] = False
        _sync_status["finished_at"] = now_iso()
        _sync_status["step"] = None
        _sync_lock.release()


def run_scheduled_sync_for_all_users(send_email: bool = True) -> dict:
    results = []
    users = db.list_approved_users()
    print(f"cron sync: {len(users)} approved user(s) (send_email={send_email})")
    for user in users:
        user_id = user["id"]
        to_email = user["username"]
        print(f"cron sync: starting user_id={user_id}")
        entry = {
            "user_id": user_id,
            "before": None,
            "after": None,
            "new_yield": None,
            "notified": False,
            "notify_error": None,
            "email_skipped": None,
            "sync_error": None,
        }
        try:
            with _user_ctx_lock:
                _activate_user(user_id)
            before = latest_published_period()
            entry["before"] = before
            sync_result = run_sync()
            if not sync_result.get("ok"):
                entry["sync_error"] = sync_result.get("error")
                results.append(entry)
                continue
            after = latest_published_period()
            entry["after"] = after
            last_notified = int(CACHE.get("last_notified_period") or 0)
            new_yield = after if (after and after > last_notified and after > (before or 0)) else None
            entry["new_yield"] = new_yield

            # Email only when a new monthly yield was published, and only when
            # email is enabled for this run. Advance last_notified_period only
            # after a successful send, so a disabled run (or a send failure)
            # doesn't permanently suppress the next new-yield email.
            if not new_yield:
                entry["email_skipped"] = "no new yield"
            elif not send_email:
                entry["email_skipped"] = "email disabled"
            else:
                synced_at = CACHE.get("last_full_sync_at") or now_iso()
                try:
                    state = compose_state(24, None)
                except Exception as ex:
                    entry["sync_error"] = f"compose_state failed: {ex}"
                    results.append(entry)
                    print(f"cron sync: compose failed user_id={user_id}: {ex}")
                    continue

                notify_result = notify.send_daily_insight_email(
                    to=to_email,
                    state=state,
                    synced_at=synced_at,
                    new_yield_period=new_yield,
                )
                entry["notified"] = notify_result.ok
                entry["notify_error"] = notify_result.error
                if notify_result.ok:
                    with _cache_lock:
                        CACHE["last_notified_period"] = after
                    save_cache()

            print(
                f"cron sync: finished user_id={user_id} before={entry['before']} "
                f"after={entry['after']} new_yield={new_yield} notified={entry['notified']} "
                f"email_skipped={entry['email_skipped']} "
                f"notify_error={entry['notify_error']} sync_error={entry['sync_error']}",
                flush=True,
            )
        except Exception as ex:
            entry["sync_error"] = str(ex)
            print(f"cron sync: failed user_id={user_id}: {ex}")
        results.append(entry)
    print(f"cron sync: complete for {len(results)} user(s)")
    return {"ok": True, "users": results}


def _run_cron_job(send_email: bool = True) -> None:
    global _cron_status
    print(f"cron sync: job started at {now_iso()}")
    try:
        result = run_scheduled_sync_for_all_users(send_email=send_email)
        _cron_status["results"] = result
        print(f"cron sync: job succeeded at {now_iso()}")
    except Exception as ex:
        _cron_status["error"] = str(ex)
        print(f"cron sync: job failed at {now_iso()}: {ex}")
    finally:
        _cron_status["running"] = False
        _cron_status["finished_at"] = now_iso()
        _cron_job_lock.release()


# ── Vesting calculator ───────────────────────────────────────────────────────
def vested_shares(grant: dict, on_date_iso: str) -> int:
    d = date.fromisoformat(on_date_iso)
    vs = date.fromisoformat(grant["vesting_start"])
    if d < vs:
        return 0
    months = (d.year - vs.year) * 12 + (d.month - vs.month)
    if d.day < vs.day:
        months -= 1
    months = max(0, months)
    cliff = int(grant.get("cliff_months") or 0)
    total = float(grant["total_shares"])
    period = int(grant["vesting_months"])
    if period <= 0:
        return int(round(total))
    if months < cliff:
        return 0
    cadence = grant.get("vesting_cadence", "monthly")
    if cadence == "quarterly":
        quarters = months // 3
        total_q = max(1, period // 3)
        v = total * min(1.0, quarters / total_q)
    else:
        v = total * min(1.0, months / period)
    return int(round(v))


# ── Recurring rule helpers ───────────────────────────────────────────────────
def _period_first_day(period: int) -> date:
    return date(period // 100, period % 100, 1)


def _period_last_day(period: int) -> date:
    y, m = divmod(period, 100)
    if m == 12:
        nxt = date(y + 1, 1, 1)
    else:
        nxt = date(y, m + 1, 1)
    return nxt - timedelta(days=1)


def applicable_rule_for_period(rules: list, period: int):
    """Return the rule whose date range covers any part of `period`, or None.

    Rules are expected to be non-overlapping. If multiple match (data inconsistency),
    the one with the latest start_date wins.
    """
    if not rules:
        return None
    p_start = _period_first_day(period)
    p_end = _period_last_day(period)
    candidates = []
    for r in rules:
        try:
            rstart = date.fromisoformat(r["start_date"])
        except (KeyError, ValueError, TypeError):
            continue
        rend = None
        if r.get("end_date"):
            try:
                rend = date.fromisoformat(r["end_date"])
            except ValueError:
                rend = None
        if rstart > p_end:
            continue
        if rend and rend < p_start:
            continue
        candidates.append((rstart, r))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def expand_rule_for_period(rule: dict, period: int) -> dict:
    """Synthesize a virtual deposit event for `period` from `rule`."""
    employee = float(rule.get("employee") or 0)
    employer = float(rule.get("employer") or 0)
    total = employee + employer
    last_day = _period_last_day(period)
    dom = int(rule.get("day_of_month") or 1)
    dom = max(1, min(dom, last_day.day))
    ev_date = date(period // 100, period % 100, dom).isoformat()
    return {
        "id": f"rule:{rule['id']}:{period}",
        "date": ev_date,
        "kind": "deposit",
        "amount_ils": total,
        "employee": employee,
        "employer": employer,
        "note": rule.get("note") or "",
        "source": f"rule:{rule['id']}",
        "synthetic": True,
    }


# ── Fund valuation ───────────────────────────────────────────────────────────
def value_fund(holding: dict, source: str = "gemelnet") -> dict:
    fund_id = str(holding["fund_id"])
    monthly_key = SOURCE_CONFIG[source]["monthly_cache_key"]
    rows = MARKET.get(monthly_key, {}).get(fund_id, {}).get("rows", [])
    rows_by_period = {int(r["report_period"]): r for r in rows}
    anchor_period = int(holding["anchor_period"])
    anchor_balance = float(holding["anchor_balance_ils"])
    yield_is_net = holding.get("yield_is_net_of_fees", DATA["settings"].get("yield_is_net_of_fees", True))
    rules = holding.get("recurring_rules", []) or []

    last_actual = max(rows_by_period.keys()) if rows_by_period else 0
    # Only walk months that have published yield data; periods beyond that are "pending".
    last_period = max(anchor_period, last_actual)

    manual_by_period = {}
    for ev in holding.get("events", []):
        try:
            p = date_period(date.fromisoformat(ev["date"]))
        except (TypeError, ValueError):
            continue
        manual_by_period.setdefault(p, []).append(ev)

    series = [{
        "period": anchor_period,
        "value_ils": round(anchor_balance, 2),
        "deposited_to_date": 0.0,
        "withdrawn_to_date": 0.0,
        "yield_pct": None,
        "is_anchor": True,
        "is_pending": False,
        "events": [],
    }]
    v = anchor_balance
    deposited = 0.0
    withdrawn = 0.0
    employee_total = 0.0
    employer_total = 0.0
    cumulative_mgmt_fee = 0.0   # estimated דמי ניהול מצבירה paid over the holding
    expanded_events_all = []  # for UI

    for period in period_iter(anchor_period, last_period):
        if period == anchor_period:
            continue
        # Deposits/withdrawals join AT THE END of the period — they do not earn
        # (or lose) the same month's yield, since a monthly yield can't apply
        # to days before the deposit date. This matches "I deposited mid-month;
        # the deposit only starts compounding from next month onward."
        delta_post = 0.0
        correction = None
        period_events = []

        # Rule-generated event (employee/employer split tracked here only).
        rule = applicable_rule_for_period(rules, period)
        if rule:
            ve = expand_rule_for_period(rule, period)
            if ve["amount_ils"] != 0:
                delta_post += ve["amount_ils"]
                deposited += ve["amount_ils"]
                employee_total += ve["employee"]
                employer_total += ve["employer"]
                period_events.append(ve)

        # Manual events — flat total.
        for ev in manual_by_period.get(period, []):
            kind = ev.get("kind")
            amt = float(ev.get("amount_ils") or 0)
            if kind == "deposit":
                delta_post += amt
                deposited += amt
            elif kind == "withdrawal":
                delta_post -= amt
                withdrawn += amt
            elif kind == "correction":
                correction = ev
            period_events.append({**ev, "synthetic": False})

        start_balance = v
        row = rows_by_period.get(period)
        yield_pct = (row or {}).get("monthly_yield")
        fee_pct = (row or {}).get("avg_annual_management_fee")
        is_pending = yield_pct is None
        # Estimated management fee for this period (always tracked,
        # regardless of yield_is_net_of_fees — when net, fees are already baked
        # into yield_pct, but the absolute ₪ figure is still informative).
        period_fee = 0.0
        if fee_pct is not None and start_balance > 0:
            period_fee = start_balance * (fee_pct / 100.0) / 12.0
            cumulative_mgmt_fee += period_fee
        if yield_pct is not None:
            v = start_balance * (1 + yield_pct / 100.0)
            if (not yield_is_net) and (fee_pct is not None):
                v -= period_fee
        else:
            v = start_balance
        # Apply deposits/withdrawals AFTER compounding (end-of-period semantics).
        v += delta_post
        # Corrections still override the balance entirely.
        if correction:
            try:
                v = float(correction["amount_ils"])
            except (TypeError, ValueError):
                pass
        series.append({
            "period": period,
            "value_ils": round(v, 2),
            "deposited_to_date": round(deposited, 2),
            "withdrawn_to_date": round(withdrawn, 2),
            "yield_pct": yield_pct,
            "mgmt_fee_pct_annual": fee_pct,
            "mgmt_fee_ils": round(period_fee, 2),
            "is_anchor": False,
            "is_pending": is_pending,
            "events": period_events,
        })
        expanded_events_all.extend(period_events)

    current_value = series[-1]["value_ils"]
    total_in = anchor_balance + deposited - withdrawn
    profit = current_value - total_in
    profit_pct = (profit / total_in) if total_in else 0.0

    sorted_periods = sorted(rows_by_period.keys())

    def _chained_return(n_months: int):
        if len(sorted_periods) < n_months:
            return None
        chained = 1.0
        for p in sorted_periods[-n_months:]:
            y = rows_by_period[p].get("monthly_yield")
            if y is None:
                return None
            chained *= (1 + y / 100.0)
        return chained - 1.0

    three_m = _chained_return(3)
    six_m = _chained_return(6)
    twelve_m = _chained_return(12)
    twentyfour_m = _chained_return(24)
    thirtysix_m = _chained_return(36)
    sixty_m = _chained_return(60)
    annualized_3y = ((1 + thirtysix_m) ** (1 / 3) - 1) if thirtysix_m is not None else None
    annualized_5y = ((1 + sixty_m) ** (1 / 5) - 1) if sixty_m is not None else None

    # Latest fund metadata from upstream raw row (alpha, sharpe, std dev, fees, etc.)
    latest_raw = (rows_by_period.get(last_actual) or {}).get("raw") or {} if last_actual else {}
    fund_metrics = {
        "avg_annual_management_fee_pct": _to_float(latest_raw.get("AVG_ANNUAL_MANAGEMENT_FEE")),
        "avg_deposit_fee_pct": _to_float(latest_raw.get("AVG_DEPOSIT_FEE")),
        "std_deviation_pct": _to_float(latest_raw.get("STANDARD_DEVIATION")),
        "alpha": _to_float(latest_raw.get("ALPHA")),
        "sharpe_ratio": _to_float(latest_raw.get("SHARPE_RATIO")),
        "total_assets_m_ils": _to_float(latest_raw.get("TOTAL_ASSETS")),
        "stock_market_exposure_pct": _to_float(latest_raw.get("STOCK_MARKET_EXPOSURE")),
        "foreign_exposure_pct": _to_float(latest_raw.get("FOREIGN_EXPOSURE")),
        "foreign_currency_exposure_pct": _to_float(latest_raw.get("FOREIGN_CURRENCY_EXPOSURE")),
        "liquid_assets_pct": _to_float(latest_raw.get("LIQUID_ASSETS_PERCENT")),
        "inception_date": latest_raw.get("INCEPTION_DATE") or None,
        "target_population": latest_raw.get("TARGET_POPULATION") or None,
        "specialization": latest_raw.get("SPECIALIZATION") or None,
        "sub_specialization": latest_raw.get("SUB_SPECIALIZATION") or None,
        # Upstream-published trailing yields (cumulative %, raw 1.0=1%)
        "upstream_3y_cumulative_pct": _to_float(latest_raw.get("YIELD_TRAILING_3_YRS")),
        "upstream_5y_cumulative_pct": _to_float(latest_raw.get("YIELD_TRAILING_5_YRS")),
        "upstream_3y_annualized_pct": _to_float(latest_raw.get("AVG_ANNUAL_YIELD_TRAILING_3YRS")),
        "upstream_5y_annualized_pct": _to_float(latest_raw.get("AVG_ANNUAL_YIELD_TRAILING_5YRS")),
    }

    # Year-to-date: chain monthly yields from January of the latest published year.
    ytd = None
    ytd_year = None
    if last_actual:
        ytd_year = last_actual // 100
        jan = ytd_year * 100 + 1
        chained = 1.0
        ok = True
        any_seen = False
        for p in period_iter(jan, last_actual):
            r = rows_by_period.get(p)
            if r is None or r.get("monthly_yield") is None:
                ok = False
                break
            chained *= (1 + r["monthly_yield"] / 100.0)
            any_seen = True
        ytd = (chained - 1.0) if (ok and any_seen) else None

    last_month_yield = (rows_by_period.get(last_actual) or {}).get("monthly_yield") if last_actual else None
    is_pending_current = (last_actual or 0) < current_period()

    return {
        "last_period": last_actual or anchor_period,
        "is_pending_current_month": is_pending_current,
        "current_value_ils": round(current_value, 2),
        "total_deposited_ils": round(deposited, 2),
        "total_withdrawn_ils": round(withdrawn, 2),
        "total_employee_ils": round(employee_total, 2),
        "total_employer_ils": round(employer_total, 2),
        "cumulative_mgmt_fee_ils": round(cumulative_mgmt_fee, 2),
        "profit_ils": round(profit, 2),
        "profit_pct": profit_pct,
        "three_m_return_pct": three_m,
        "six_m_return_pct": six_m,
        "twelve_m_return_pct": twelve_m,
        "twentyfour_m_return_pct": twentyfour_m,
        "thirtysix_m_return_pct": thirtysix_m,
        "sixty_m_return_pct": sixty_m,
        "annualized_3y_return_pct": annualized_3y,
        "annualized_5y_return_pct": annualized_5y,
        "ytd_return_pct": ytd,
        "ytd_year": ytd_year,
        "last_month_return_pct": last_month_yield,
        "fund_metrics": fund_metrics,
        "time_series": series,
        "expanded_events": expanded_events_all,
    }


# ── Spot-check yield (non-persisting "actual vs Gemelnet" comparison) ────────
def compute_spot_check_yields(holding: dict, new_balance_ils, new_period,
                              source: str = "gemelnet") -> dict:
    """Compare a user-reported actual balance at `new_period` against what the
    Gemelnet/pensia monthly yields imply. The comparison base is the
    Gemelnet-projected value at (new_period − 1) — i.e. the dashboard's
    current value, NOT the saved anchor. That way the "implied yield" the
    popup shows is the per-month yield for new_period, matching the user's
    mental model. Pure read — touches neither DATA nor disk."""
    try:
        anchor_period = int(holding["anchor_period"])
        anchor_balance = float(holding["anchor_balance_ils"])
        new_period = int(new_period)
        new_balance = float(new_balance_ils)
    except (KeyError, TypeError, ValueError) as ex:
        return {"ok": False, "error": f"Invalid input: {ex}"}

    if new_period <= anchor_period:
        return {"ok": False, "error": "New period must be after anchor period."}
    if anchor_balance <= 0:
        return {"ok": False,
                "error": "Anchor balance is zero — can't compute an implied yield."}

    monthly_key = SOURCE_CONFIG[source]["monthly_cache_key"]
    fund_id = str(holding["fund_id"])
    rows = MARKET.get(monthly_key, {}).get(fund_id, {}).get("rows", [])
    rows_by_period = {int(r["report_period"]): r for r in rows}

    # Comparison base: the value at the period right before new_period
    # (clamped to [anchor_period, last_actual]) per value_fund's time_series.
    valued = value_fund(holding, source=source)
    series_by_period = {int(s["period"]): s for s in (valued.get("time_series") or [])}
    last_actual = int(valued.get("last_period") or anchor_period)

    py, pm = divmod(new_period, 100)
    pm -= 1
    if pm < 1:
        pm = 12; py -= 1
    desired_prev = py * 100 + pm
    previous_period = max(anchor_period, min(desired_prev, last_actual))

    prev_entry = series_by_period.get(previous_period)
    if prev_entry is None:
        return {"ok": False,
                "error": f"Can't find a projected value at {previous_period}."}
    previous_value = float(prev_entry["value_ils"])
    if previous_value <= 0:
        return {"ok": False,
                "error": "Projected previous-month value is zero — can't compute an implied yield."}

    gap_periods = [p for p in period_iter(previous_period, new_period)
                   if p > previous_period]
    gap_months = len(gap_periods)
    gap_set = set(gap_periods)
    implied_total = new_balance / previous_value - 1.0
    implied_monthly = (1.0 + implied_total) ** (1.0 / gap_months) - 1.0

    # Gemelnet expected over the gap (previous_period → new_period) requires
    # ALL gap months to be published. If any are pending (typical when the
    # user has next-month data before Gemelnet does), surface N/A instead of
    # refusing.
    gap_yields = []
    all_gap_published = True
    for p in gap_periods:
        row = rows_by_period.get(p)
        y = row.get("monthly_yield") if row else None
        if y is None:
            all_gap_published = False
            break
        gap_yields.append(y)
    if all_gap_published:
        chained = 1.0
        for y in gap_yields:
            chained *= (1 + y / 100.0)
        gemelnet_chained_yield = (chained - 1.0) * 100.0
        gemelnet_expected = round(previous_value * chained, 2)
        tracking_gap_ils = round(new_balance - previous_value * chained, 2)
        tracking_gap_pp = implied_total * 100.0 - gemelnet_chained_yield
    else:
        gemelnet_chained_yield = None
        gemelnet_expected = None
        tracking_gap_ils = None
        tracking_gap_pp = None

    # Updated chained returns: window ENDS at new_period. Gap months use the
    # implied monthly yield; non-gap months use Gemelnet (must be published —
    # they are, by definition, before the gap). The Gemelnet column shows the
    # same window with the gap month replaced by its published yield instead;
    # if any gap month lacks a published yield, the Gemelnet column is None.
    def _window_ending(n):
        out = []
        y, m = divmod(new_period, 100)
        for _ in range(n):
            out.append(y * 100 + m)
            m -= 1
            if m < 1:
                m = 12
                y -= 1
        return list(reversed(out))

    def _ytd_window():
        year = new_period // 100
        return list(period_iter(year * 100 + 1, new_period))

    def _chain(periods):
        gem = 1.0
        imp = 1.0
        gem_ok = True
        for p in periods:
            row = rows_by_period.get(p)
            y_gem = row.get("monthly_yield") if row else None
            if p in gap_set:
                imp *= (1 + implied_monthly)
                if y_gem is None:
                    gem_ok = False
                elif gem_ok:
                    gem *= (1 + y_gem / 100.0)
            else:
                if y_gem is None:
                    return None, None
                imp *= (1 + y_gem / 100.0)
                if gem_ok:
                    gem *= (1 + y_gem / 100.0)
        return ((gem - 1.0) * 100.0 if gem_ok else None,
                (imp - 1.0) * 100.0)

    updated_returns = {}
    for label, n in (("three_m", 3), ("six_m", 6), ("twelve_m", 12)):
        gem, imp = _chain(_window_ending(n))
        updated_returns[label] = {"gemelnet_pct": gem, "implied_pct": imp}
    ytd_window = _ytd_window()
    if ytd_window:
        gem, imp = _chain(ytd_window)
        updated_returns["ytd"] = {"gemelnet_pct": gem, "implied_pct": imp,
                                  "year": new_period // 100}
    else:
        updated_returns["ytd"] = {"gemelnet_pct": None, "implied_pct": None,
                                  "year": new_period // 100}

    mixed_with_events = False
    for ev in (holding.get("events") or []):
        try:
            p_ev = date_period(date.fromisoformat(ev["date"]))
        except (TypeError, ValueError):
            continue
        if previous_period < p_ev <= new_period:
            mixed_with_events = True
            break
    if not mixed_with_events:
        rules = holding.get("recurring_rules") or []
        for p in gap_periods:
            if applicable_rule_for_period(rules, p):
                mixed_with_events = True
                break

    return {
        "ok": True,
        # Anchor is informational only — the comparison runs against the
        # projected previous-period value, not the anchor.
        "anchor_period": anchor_period,
        "anchor_balance_ils": anchor_balance,
        "previous_period": previous_period,
        "previous_value_ils": round(previous_value, 2),
        "new_period": new_period,
        "new_balance_ils": new_balance,
        "gap_months": gap_months,
        # Gemelnet-side fields are None when any gap month is unpublished.
        "gemelnet_expected_value_ils": gemelnet_expected,
        "gemelnet_chained_yield_pct": gemelnet_chained_yield,
        "tracking_gap_ils": tracking_gap_ils,
        "tracking_gap_pp": tracking_gap_pp,
        # Implied always computable from previous_value + new balance.
        "implied_total_yield_pct": implied_total * 100.0,
        "implied_monthly_yield_pct": implied_monthly * 100.0,
        "updated_returns": updated_returns,
        "mixed_with_events": mixed_with_events,
    }


def spot_check_fund(holding_id: str, payload: dict) -> dict:
    """Endpoint glue for fund holdings. NEVER writes to disk."""
    h = None
    for x in DATA.get("fund_holdings", []) or []:
        if x["id"] == holding_id:
            h = x
            break
    if not h:
        return {"ok": False, "error": "Holding not found"}
    return compute_spot_check_yields(h, payload.get("new_balance_ils"),
                                     payload.get("new_period"),
                                     source=fund_holding_source(h))


def spot_check_pension(holding_id: str, payload: dict) -> dict:
    """Endpoint glue for pension holdings. NEVER writes to disk."""
    h = None
    for x in DATA.get("pension_holdings", []) or []:
        if x["id"] == holding_id:
            h = x
            break
    if not h:
        return {"ok": False, "error": "Holding not found"}
    return compute_spot_check_yields(h, payload.get("new_balance_ils"),
                                     payload.get("new_period"),
                                     source="pensia")


# ── RSU valuation ────────────────────────────────────────────────────────────
def value_rsu(grant: dict) -> dict:
    ticker = grant["ticker"].upper()
    grant_date_iso = grant["grant_date"]
    stock = MARKET.get("stock_daily", {}).get(ticker, {})
    fx = MARKET.get("fx", {}).get("USDILS", {})
    stock_rows = stock.get("rows", [])
    fx_rows = fx.get("rows", [])
    stock_by_date = {r["date"]: r["close"] for r in stock_rows}
    fx_by_date = {r["date"]: r["close"] for r in fx_rows}

    override = DATA["settings"].get("usdils_rate_override")
    series = []
    if not stock_rows:
        return {
            "vested_shares_now": vested_shares(grant, today_iso()),
            "unvested_shares": int(grant["total_shares"]) - vested_shares(grant, today_iso()),
            "current_price_usd": None,
            "current_usdils": None,
            "current_value_usd": 0,
            "current_value_ils": 0,
            "profit_usd": 0,
            "profit_ils": 0,
            "grant_close_usd": None,
            "grant_usdils": None,
            "time_series": [],
            "future_at_current_price": [],
            "potential_full_vest_usd": 0,
            "potential_full_vest_ils": 0,
            "full_vest_date": None,
            "no_data": True,
        }

    # Initialize last_close / last_fx by looking BACKWARD from grant_date for
    # the most recent published trading day. Without this, a grant made on a
    # weekend or today (before Yahoo updates) would have no value at all.
    grant_d = date.fromisoformat(grant_date_iso)
    last_close = None
    last_fx = None
    for r in reversed(stock_rows):
        if r["date"] <= grant_date_iso:
            last_close = r["close"]
            break
    for r in reversed(fx_rows):
        if r["date"] <= grant_date_iso:
            last_fx = r["close"]
            break

    sales = sorted(grant.get("sales", []) or [], key=lambda s: s["date"])

    end = date.today()
    d = grant_d
    while d <= end:
        d_iso = d.isoformat()
        c = stock_by_date.get(d_iso)
        if c is not None:
            last_close = c
        fxv = fx_by_date.get(d_iso)
        if fxv is not None:
            last_fx = fxv
        effective_fx = override if override else last_fx
        if last_close is not None and effective_fx is not None:
            vested = vested_shares(grant, d_iso)
            sold_to_d = sum(int(s["shares_sold"]) for s in sales if s["date"] <= d_iso)
            held = vested - sold_to_d
            value_usd = held * last_close
            value_ils = value_usd * effective_fx
            series.append({
                "date": d_iso,
                "vested": vested,
                "sold_to_date": sold_to_d,
                "held": held,
                "close_usd": last_close,
                "usdils": effective_fx,
                "value_usd": round(value_usd, 2),
                "value_ils": round(value_ils, 2),
            })
        d += timedelta(days=1)

    if not series:
        return {
            "vested_shares_now": 0,
            "shares_sold_total": 0,
            "shares_held_now": 0,
            "unvested_shares": int(grant["total_shares"]),
            "current_price_usd": None,
            "current_usdils": None,
            "current_value_usd": 0,
            "current_value_ils": 0,
            "profit_usd": 0,
            "profit_ils": 0,
            "realized_gain_usd": 0,
            "realized_gain_ils": 0,
            "realized_proceeds_usd": 0,
            "realized_proceeds_ils": 0,
            "unrealized_gain_usd": 0,
            "unrealized_gain_ils": 0,
            "grant_close_usd": None,
            "grant_usdils": None,
            "time_series": [],
            "future_at_current_price": [],
            "potential_full_vest_usd": 0,
            "potential_full_vest_ils": 0,
            "full_vest_date": None,
            "no_data": True,
        }

    last = series[-1]
    market_grant_close = series[0]["close_usd"]
    grant_fx = series[0]["usdils"]
    override_price = grant.get("grant_price_override_usd")
    cost_basis_per_share_usd = float(override_price) if override_price else market_grant_close
    vested_now = last["vested"]
    total_sold = sum(int(s["shares_sold"]) for s in sales)
    held_now = vested_now - total_sold

    # Realized: sum across sales using sale-date FX (forward-fill from cache).
    realized_proceeds_usd = 0.0
    realized_proceeds_ils = 0.0
    realized_cost_usd = 0.0
    realized_cost_ils = 0.0
    for s in sales:
        s_shares = int(s["shares_sold"])
        s_price = float(s["sale_price_usd"])
        s_date = s["date"]
        # FX on (or before) sale date — forward-filled
        s_fx = None
        for r in reversed(fx_rows):
            if r["date"] <= s_date:
                s_fx = r["close"]
                break
        if override:
            s_fx = override
        if s_fx is None:
            s_fx = last["usdils"]
        realized_proceeds_usd += s_shares * s_price
        realized_proceeds_ils += s_shares * s_price * s_fx
        realized_cost_usd += s_shares * cost_basis_per_share_usd
        realized_cost_ils += s_shares * cost_basis_per_share_usd * s_fx

    realized_gain_usd = realized_proceeds_usd - realized_cost_usd
    realized_gain_ils = realized_proceeds_ils - realized_cost_ils

    # Unrealized: on shares still held
    cost_basis_held_usd = held_now * cost_basis_per_share_usd
    cost_basis_held_ils = cost_basis_held_usd * grant_fx
    unrealized_gain_usd = (last["close_usd"] - cost_basis_per_share_usd) * held_now
    unrealized_gain_ils = last["value_ils"] - cost_basis_held_ils

    # Backwards-compat aggregate (was profit_usd / profit_ils on pre-sale logic)
    profit_usd = realized_gain_usd + unrealized_gain_usd
    profit_ils = realized_gain_ils + unrealized_gain_ils

    cost_basis_total_usd = cost_basis_held_usd
    cost_basis_total_ils = cost_basis_held_ils

    # Future timeline: month-end values from today through full vesting,
    # holding price + FX constant at the latest known levels. Pure vesting
    # schedule, no price-growth assumption.
    total_shares = int(grant["total_shares"])
    vesting_start_d = date.fromisoformat(grant["vesting_start"])
    vesting_months = int(grant["vesting_months"])
    full_vest_date = vesting_start_d + timedelta(days=vesting_months * 31)
    # Anchor full-vest precisely (handle month arithmetic)
    fv_year = vesting_start_d.year + (vesting_start_d.month - 1 + vesting_months) // 12
    fv_month = (vesting_start_d.month - 1 + vesting_months) % 12 + 1
    fv_day = min(vesting_start_d.day, _period_last_day(fv_year * 100 + fv_month).day)
    full_vest_date = date(fv_year, fv_month, fv_day)

    future_series = []
    today_d = date.today()
    cur_close = last["close_usd"]
    cur_fx = last["usdils"]
    walker = today_d
    seen_months = set()
    # Cap the walker at full_vest_date + 1 month so the chart shows the
    # plateau after full vesting.
    end_walker = full_vest_date + timedelta(days=31)
    while walker <= end_walker:
        ym = (walker.year, walker.month)
        last_day_of_month = _period_last_day(walker.year * 100 + walker.month)
        candidate = last_day_of_month if last_day_of_month <= end_walker else walker
        if ym not in seen_months and candidate >= today_d:
            vested_at_d = vested_shares(grant, candidate.isoformat())
            held_at_d = max(0, vested_at_d - total_sold)
            value_usd = held_at_d * cur_close
            value_ils = value_usd * cur_fx
            future_series.append({
                "date": candidate.isoformat(),
                "vested": vested_at_d,
                "held": held_at_d,
                "value_usd": round(value_usd, 2),
                "value_ils": round(value_ils, 2),
            })
            seen_months.add(ym)
        walker = (last_day_of_month + timedelta(days=1))

    potential_remaining_shares = total_shares - total_sold
    potential_full_vest_usd = potential_remaining_shares * cur_close
    potential_full_vest_ils = potential_full_vest_usd * cur_fx

    return {
        "vested_shares_now": vested_now,
        "shares_sold_total": total_sold,
        "shares_held_now": held_now,
        "unvested_shares": total_shares - vested_now,
        "current_price_usd": last["close_usd"],
        "current_usdils": last["usdils"],
        "current_value_usd": last["value_usd"],
        "current_value_ils": last["value_ils"],
        "profit_usd": round(profit_usd, 2),
        "profit_ils": round(profit_ils, 2),
        "realized_gain_usd": round(realized_gain_usd, 2),
        "realized_gain_ils": round(realized_gain_ils, 2),
        "realized_proceeds_usd": round(realized_proceeds_usd, 2),
        "realized_proceeds_ils": round(realized_proceeds_ils, 2),
        "unrealized_gain_usd": round(unrealized_gain_usd, 2),
        "unrealized_gain_ils": round(unrealized_gain_ils, 2),
        "grant_close_usd": market_grant_close,
        "grant_usdils": grant_fx,
        "cost_basis_per_share_usd": round(cost_basis_per_share_usd, 4),
        "cost_basis_total_usd": round(cost_basis_total_usd, 2),
        "cost_basis_total_ils": round(cost_basis_total_ils, 2),
        "uses_override_price": bool(override_price),
        "time_series": series,
        "future_at_current_price": future_series,
        "potential_full_vest_usd": round(potential_full_vest_usd, 2),
        "potential_full_vest_ils": round(potential_full_vest_ils, 2),
        "full_vest_date": full_vest_date.isoformat(),
        "no_data": False,
    }


# ── Projection (deterministic mean) ──────────────────────────────────────────
def project_returns(returns: list, current: float, horizon_months: int,
                    contributions_per_month: list = None) -> dict:
    """Project the mean monthly-return path. If contributions_per_month is
    provided (length must equal horizon_months), each future month adds that
    contribution BEFORE compounding — i.e. dollar-cost-averaging math."""
    if not returns or len(returns) < 6:
        return None
    mu = statistics.mean(returns)
    sigma = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
    contribs = contributions_per_month or [0.0] * horizon_months
    if len(contribs) < horizon_months:
        contribs = list(contribs) + [0.0] * (horizon_months - len(contribs))

    paths = {"mean": []}
    cur_mean = current
    total_contrib = 0.0
    for t in range(horizon_months):
        c = float(contribs[t] or 0.0)
        total_contrib += c
        cur_mean = (cur_mean + c) * (1 + mu)
        paths["mean"].append(round(cur_mean, 2))
    annual_pct = round(((1 + mu) ** 12 - 1) * 100.0, 2) if returns else None
    return {
        "mu_monthly": mu,
        "annual_pct": annual_pct,
        "sigma_monthly": sigma,
        "n_samples": len(returns),
        "paths": paths,
        "total_projected_contribution_ils": round(total_contrib, 2),
        "includes_recurring": any(c > 0 for c in contribs),
    }


def _project_fund_contributions(holding: dict, computed: dict, horizon_months: int) -> list:
    """For each future period (last_period+1 ... +horizon), look up the rule
    that's active and return employee+employer as the contribution. Periods
    where no rule applies contribute 0."""
    rules = holding.get("recurring_rules", []) or []
    if not rules:
        return [0.0] * horizon_months
    last_period = int(computed.get("last_period") or holding["anchor_period"])
    contribs = []
    p = last_period
    for _ in range(horizon_months):
        y, m = divmod(p, 100)
        m += 1
        if m > 12:
            m = 1
            y += 1
        p = y * 100 + m
        rule = applicable_rule_for_period(rules, p)
        if rule:
            c = float(rule.get("employee") or 0) + float(rule.get("employer") or 0)
        else:
            c = 0.0
        contribs.append(c)
    return contribs


def project_fund(holding: dict, computed: dict, horizon_months: int, source: str = "gemelnet") -> dict:
    monthly_key = SOURCE_CONFIG[source]["monthly_cache_key"]
    rows = MARKET.get(monthly_key, {}).get(str(holding["fund_id"]), {}).get("rows", [])
    returns = [r["monthly_yield"] / 100.0 for r in rows if r.get("monthly_yield") is not None]
    contribs = _project_fund_contributions(holding, computed, horizon_months)
    return project_returns(returns, computed["current_value_ils"], horizon_months, contribs)


def what_if_fund(holding: dict, computed: dict, annual_pct, horizon_months: int) -> dict:
    """Per-fund what-if: deterministic compounding at annual_pct/year with the
    holding's recurring contributions added each month."""
    if annual_pct is None:
        return None
    contribs = _project_fund_contributions(holding, computed, horizon_months)
    return compose_portfolio_what_if(
        computed.get("current_value_ils") or 0.0,
        annual_pct,
        horizon_months,
        contribs,
    )


# ── Pension valuation (thin wrappers — same math, pensia-net cache) ──────────
def value_pension(holding: dict) -> dict:
    return value_fund(holding, source="pensia")


def project_pension(holding: dict, computed: dict, horizon_months: int) -> dict:
    return project_fund(holding, computed, horizon_months, source="pensia")


def what_if_pension(holding: dict, computed: dict, annual_pct, horizon_months: int) -> dict:
    """Per-pension what-if: same deterministic compounding as funds.
    Pension v1 has no recurring contributions, so _project_fund_contributions
    will return [] and the math reduces to compound-only growth."""
    return what_if_fund(holding, computed, annual_pct, horizon_months)


def what_if_rsu(grant: dict, computed: dict, annual_pct, horizon_months: int) -> dict:
    """Per-RSU what-if: vesting schedule (deterministic) × stock price growing
    at annual_pct/year × current FX. ILS values use current FX held constant."""
    if annual_pct is None:
        return None
    try:
        annual_pct = float(annual_pct)
    except (TypeError, ValueError):
        return None
    annual = annual_pct / 100.0
    if 1 + annual <= 0:
        return None
    monthly = (1 + annual) ** (1 / 12) - 1

    cur_close = computed.get("current_price_usd")
    cur_fx = computed.get("current_usdils")
    if cur_close is None or cur_fx is None:
        return None
    total_sold = int(computed.get("shares_sold_total") or 0)

    today_d = date.today()
    paths_usd = []
    paths_ils = []
    labels = []
    walker = today_d
    seen = set()
    for _ in range(horizon_months + 12):
        last_day_of_month = _period_last_day(walker.year * 100 + walker.month)
        ym = (walker.year, walker.month)
        if ym not in seen:
            t = (last_day_of_month.year - today_d.year) * 12 + (last_day_of_month.month - today_d.month)
            if t >= 1 and t <= horizon_months:
                vested_at = vested_shares(grant, last_day_of_month.isoformat())
                held_at = max(0, vested_at - total_sold)
                price_at = cur_close * ((1 + monthly) ** t)
                v_usd = held_at * price_at
                v_ils = v_usd * cur_fx
                paths_usd.append(round(v_usd, 2))
                paths_ils.append(round(v_ils, 2))
                labels.append(last_day_of_month.isoformat())
            seen.add(ym)
        walker = last_day_of_month + timedelta(days=1)
        if len(paths_usd) >= horizon_months:
            break
    return {
        "annual_pct": annual_pct,
        "monthly_rate": monthly,
        "horizon_months": horizon_months,
        "paths_usd": paths_usd,
        "paths_ils": paths_ils,
        "labels": labels,
        "end_value_usd": paths_usd[-1] if paths_usd else None,
        "end_value_ils": paths_ils[-1] if paths_ils else None,
    }


def project_rsu(grant: dict, computed: dict, horizon_months: int) -> dict:
    # Vesting-aware projection: hold price + FX flat at today's value and let
    # the vesting schedule drive future value. Deterministic — no variance
    # band.
    if computed.get("no_data") or computed.get("current_price_usd") is None:
        return None
    fap = computed.get("future_at_current_price") or []
    by_month = {entry["date"][:7]: entry["value_ils"] for entry in fap}

    today_d = date.today()
    path = []
    # Seed with today's value so a fully-vested grant (whose
    # future_at_current_price is empty because full_vest_date is in the past)
    # plateaus correctly across the horizon.
    last_seen = float(computed.get("current_value_ils") or 0.0)
    for i in range(horizon_months):
        # Target the (i+1)-th calendar month after today, matching the
        # "paths[i] = month i+1 from now" convention used by project_returns.
        m_idx = today_d.month - 1 + (i + 1)
        target_year = today_d.year + m_idx // 12
        target_month = m_idx % 12 + 1
        ym = f"{target_year:04d}-{target_month:02d}"
        if ym in by_month:
            last_seen = by_month[ym]
        path.append(round(last_seen, 2))
    return {
        "paths": {"mean": path},
        "horizon_months": horizon_months,
    }


# ── ESPP valuation ───────────────────────────────────────────────────────────
def _espp_purchase_breakdown(plan: dict, contribution_usd: float,
                             period_start_price_usd: float,
                             period_end_price_usd: float) -> dict:
    """Compute purchase_price, shares, and discount components for one cycle.

    purchase_price = (1 - discount/100) × min(start,end)  if has_lookback else end
    shares         = contribution / purchase_price
    discount_captured = end_price × shares − contribution  (full value vs. paid)
    lookback_bonus = max(0, (end−start) × shares)          (lookback portion only)
    """
    discount = float(plan.get("discount_pct") or 15.0) / 100.0
    has_lookback = bool(plan.get("has_lookback"))
    start_p = float(period_start_price_usd)
    end_p = float(period_end_price_usd)
    if start_p <= 0 or end_p <= 0:
        raise ValueError("period prices must be > 0")
    base_p = min(start_p, end_p) if has_lookback else end_p
    purchase_price = base_p * (1.0 - discount)
    if purchase_price <= 0:
        raise ValueError("computed purchase_price <= 0 (discount too large?)")
    contribution = float(contribution_usd)
    if contribution <= 0:
        raise ValueError("contribution_usd must be > 0")
    shares = contribution / purchase_price
    discount_captured = end_p * shares - contribution
    lookback_bonus = max(0.0, (end_p - start_p) * shares) if has_lookback else 0.0
    return {
        "purchase_price_usd": round(purchase_price, 4),
        "shares": shares,
        "discount_captured_usd": discount_captured,
        "lookback_bonus_usd": lookback_bonus,
    }


def value_espp(plan: dict) -> dict:
    """Compute current ESPP plan state: holdings, value, gains, discount captured."""
    ticker = plan["ticker"].upper()
    stock = MARKET.get("stock_daily", {}).get(ticker, {})
    fx = MARKET.get("fx", {}).get("USDILS", {})
    stock_rows = stock.get("rows", []) or []
    fx_rows = fx.get("rows", []) or []
    stock_by_date = {r["date"]: r["close"] for r in stock_rows}
    fx_by_date = {r["date"]: r["close"] for r in fx_rows}

    purchases = sorted(plan.get("purchases", []) or [], key=lambda p: p["date"])
    sales = sorted(plan.get("sales", []) or [], key=lambda s: s["date"])
    override = DATA["settings"].get("usdils_rate_override")

    shares_acquired = sum(float(p.get("shares") or 0) for p in purchases)
    shares_sold = sum(float(s.get("shares_sold") or 0) for s in sales)
    shares_held = max(0.0, shares_acquired - shares_sold)
    total_contributed_usd = sum(float(p.get("contribution_usd") or 0) for p in purchases)

    discount_captured_total = 0.0
    lookback_bonus_total = 0.0
    has_lookback = bool(plan.get("has_lookback"))
    for p in purchases:
        end_price = float(p.get("period_end_price_usd") or 0)
        start_price = float(p.get("period_start_price_usd") or 0)
        sh = float(p.get("shares") or 0)
        contrib = float(p.get("contribution_usd") or 0)
        if sh > 0 and end_price > 0:
            discount_captured_total += end_price * sh - contrib
            if has_lookback:
                lookback_bonus_total += max(0.0, (end_price - start_price) * sh)

    # FIFO walk: build remaining lots after subtracting cumulative sold shares.
    remaining_to_drop = shares_sold
    remaining_lots = []  # list of (shares_left, purchase_price_usd)
    for p in purchases:
        sh = float(p.get("shares") or 0)
        pp = float(p.get("purchase_price_usd") or 0)
        if remaining_to_drop >= sh:
            remaining_to_drop -= sh
            continue
        if remaining_to_drop > 0:
            sh -= remaining_to_drop
            remaining_to_drop = 0
        if sh > 0:
            remaining_lots.append((sh, pp))
    cost_basis_held_usd = sum(s * pp for s, pp in remaining_lots)
    cost_basis_per_share_usd = (cost_basis_held_usd / shares_held) if shares_held > 0 else 0.0

    current_price_usd = stock_rows[-1]["close"] if stock_rows else None
    fx_now = fx_rows[-1]["close"] if fx_rows else None
    current_fx = override if override else fx_now

    if current_price_usd is None or current_fx is None or not purchases:
        return {
            "shares_acquired_total": round(shares_acquired, 4),
            "shares_sold_total": round(shares_sold, 4),
            "shares_held_now": round(shares_held, 4),
            "current_price_usd": current_price_usd,
            "current_usdils": current_fx,
            "current_value_usd": 0,
            "current_value_ils": 0,
            "total_contributed_usd": round(total_contributed_usd, 2),
            "total_contributed_ils": 0,
            "cost_basis_per_share_usd": round(cost_basis_per_share_usd, 4),
            "cost_basis_total_usd": round(cost_basis_held_usd, 2),
            "cost_basis_total_ils": 0,
            "discount_captured_usd_total": round(discount_captured_total, 2),
            "lookback_bonus_usd_total": round(lookback_bonus_total, 2),
            "realized_proceeds_usd": 0,
            "realized_proceeds_ils": 0,
            "realized_gain_usd": 0,
            "realized_gain_ils": 0,
            "unrealized_gain_usd": 0,
            "unrealized_gain_ils": 0,
            "profit_usd": 0,
            "profit_ils": 0,
            "time_series": [],
            "no_data": True,
        }

    current_value_usd = shares_held * current_price_usd
    current_value_ils = current_value_usd * current_fx
    cost_basis_total_ils = cost_basis_held_usd * current_fx
    total_contributed_ils = total_contributed_usd * current_fx

    # Realized gains via FIFO lot consumption per sale, FX from sale date.
    lot_pool = [[float(p.get("shares") or 0), float(p.get("purchase_price_usd") or 0)] for p in purchases]
    realized_proceeds_usd = 0.0
    realized_proceeds_ils = 0.0
    realized_cost_usd = 0.0
    realized_cost_ils = 0.0
    for s in sales:
        s_shares = float(s.get("shares_sold") or 0)
        s_price = float(s.get("sale_price_usd") or 0)
        s_date = s["date"]
        s_fx = override
        if not s_fx:
            for r in reversed(fx_rows):
                if r["date"] <= s_date:
                    s_fx = r["close"]
                    break
        if s_fx is None:
            s_fx = current_fx
        rem = s_shares
        cost_for_sale_usd = 0.0
        for lot in lot_pool:
            if rem <= 0:
                break
            if lot[0] <= 0:
                continue
            take = min(rem, lot[0])
            cost_for_sale_usd += take * lot[1]
            lot[0] -= take
            rem -= take
        realized_proceeds_usd += s_shares * s_price
        realized_proceeds_ils += s_shares * s_price * s_fx
        realized_cost_usd += cost_for_sale_usd
        realized_cost_ils += cost_for_sale_usd * s_fx

    realized_gain_usd = realized_proceeds_usd - realized_cost_usd
    realized_gain_ils = realized_proceeds_ils - realized_cost_ils
    if shares_held > 0:
        unrealized_gain_usd = (current_price_usd - cost_basis_per_share_usd) * shares_held
    else:
        unrealized_gain_usd = 0.0
    unrealized_gain_ils = unrealized_gain_usd * current_fx

    # Daily time series from first purchase → today.
    series = []
    first_d = date.fromisoformat(purchases[0]["date"])
    end_d = date.today()
    last_close = None
    last_fx = None
    # Seed last_close/last_fx from rows on or before first_d so the series can
    # start cleanly even if the first purchase fell on a non-trading day.
    for r in reversed(stock_rows):
        if r["date"] <= purchases[0]["date"]:
            last_close = r["close"]
            break
    for r in reversed(fx_rows):
        if r["date"] <= purchases[0]["date"]:
            last_fx = r["close"]
            break
    d = first_d
    while d <= end_d:
        d_iso = d.isoformat()
        c = stock_by_date.get(d_iso)
        if c is not None:
            last_close = c
        fxv = fx_by_date.get(d_iso)
        if fxv is not None:
            last_fx = fxv
        effective_fx = override if override else last_fx
        sh_acq = sum(float(p.get("shares") or 0) for p in purchases if p["date"] <= d_iso)
        sh_sld = sum(float(s.get("shares_sold") or 0) for s in sales if s["date"] <= d_iso)
        held_at_d = max(0.0, sh_acq - sh_sld)
        if last_close is not None and effective_fx is not None:
            v_usd = held_at_d * last_close
            v_ils = v_usd * effective_fx
            series.append({
                "date": d_iso,
                "shares_acquired": round(sh_acq, 4),
                "shares_sold": round(sh_sld, 4),
                "shares_held": round(held_at_d, 4),
                "close_usd": last_close,
                "usdils": effective_fx,
                "value_usd": round(v_usd, 2),
                "value_ils": round(v_ils, 2),
            })
        d += timedelta(days=1)

    return {
        "shares_acquired_total": round(shares_acquired, 4),
        "shares_sold_total": round(shares_sold, 4),
        "shares_held_now": round(shares_held, 4),
        "current_price_usd": current_price_usd,
        "current_usdils": current_fx,
        "current_value_usd": round(current_value_usd, 2),
        "current_value_ils": round(current_value_ils, 2),
        "total_contributed_usd": round(total_contributed_usd, 2),
        "total_contributed_ils": round(total_contributed_ils, 2),
        "cost_basis_per_share_usd": round(cost_basis_per_share_usd, 4),
        "cost_basis_total_usd": round(cost_basis_held_usd, 2),
        "cost_basis_total_ils": round(cost_basis_total_ils, 2),
        "discount_captured_usd_total": round(discount_captured_total, 2),
        "lookback_bonus_usd_total": round(lookback_bonus_total, 2),
        "realized_proceeds_usd": round(realized_proceeds_usd, 2),
        "realized_proceeds_ils": round(realized_proceeds_ils, 2),
        "realized_gain_usd": round(realized_gain_usd, 2),
        "realized_gain_ils": round(realized_gain_ils, 2),
        "unrealized_gain_usd": round(unrealized_gain_usd, 2),
        "unrealized_gain_ils": round(unrealized_gain_ils, 2),
        "profit_usd": round(realized_gain_usd + unrealized_gain_usd, 2),
        "profit_ils": round(realized_gain_ils + unrealized_gain_ils, 2),
        "time_series": series,
        "no_data": False,
    }


def project_espp(plan: dict, computed: dict, horizon_months: int) -> dict:
    """Forward projection — Option A: hold ESPP value flat at current_value_ils."""
    if computed.get("no_data") or computed.get("current_price_usd") is None:
        return None
    cur = float(computed.get("current_value_ils") or 0.0)
    return {
        "paths": {"mean": [round(cur, 2)] * horizon_months},
        "horizon_months": horizon_months,
    }


# ── /api/data composer ───────────────────────────────────────────────────────
def compose_state(horizon_months: int = 24, assumed_annual_pct=None) -> dict:
    with _data_lock, _cache_lock, _market_lock:
        fund_holdings_out = []
        for h in DATA["fund_holdings"]:
            src = fund_holding_source(h)
            computed = value_fund(h, source=src)
            archived = h.get("archived")
            projection = project_fund(h, computed, horizon_months, source=src) if not archived else None
            wf = what_if_fund(h, computed, assumed_annual_pct, horizon_months) if not archived else None
            monthly_key = SOURCE_CONFIG[src]["monthly_cache_key"]
            cache_entry = MARKET.get(monthly_key, {}).get(str(h["fund_id"]), {})
            out = dict(h)
            out["computed"] = computed
            out["projection"] = projection
            out["what_if"] = wf
            out["cache_meta"] = cache_entry.get("meta")
            out["last_synced"] = cache_entry.get("last_synced")
            fund_holdings_out.append(out)

        pension_holdings_out = []
        for h in DATA.get("pension_holdings", []) or []:
            computed = value_pension(h)
            archived = h.get("archived")
            projection = project_pension(h, computed, horizon_months) if not archived else None
            wf = what_if_pension(h, computed, assumed_annual_pct, horizon_months) if not archived else None
            cache_entry = MARKET.get("pensia_monthly", {}).get(str(h["fund_id"]), {})
            out = dict(h)
            out["computed"] = computed
            out["projection"] = projection
            out["what_if"] = wf
            out["cache_meta"] = cache_entry.get("meta")
            out["last_synced"] = cache_entry.get("last_synced")
            pension_holdings_out.append(out)

        rsu_grants_out = []
        cutoff_6m = (date.today() - timedelta(days=180)).isoformat()
        analyst_targets_cache = MARKET.get("analyst_targets") or {}
        for g in DATA["rsu_grants"]:
            computed = value_rsu(g)
            archived = g.get("archived")
            projection = project_rsu(g, computed, horizon_months) if not archived else None
            tk = g["ticker"].upper()
            ticker_cache = MARKET["stock_daily"].get(tk, {})
            stock_rows = ticker_cache.get("rows", []) or []
            # Window is "last 6 months" OR "back to grant date", whichever is
            # earlier — so users can always see where the grant landed on the
            # price curve, even if the grant is older than 6 months.
            cutoff = min(cutoff_6m, g.get("grant_date") or cutoff_6m)
            stock_history = [
                {"date": r["date"], "close": r["close"]}
                for r in stock_rows if r.get("date", "") >= cutoff
            ]
            out = dict(g)
            out["computed"] = computed
            out["projection"] = projection
            # No per-grant what-if for RSU: with the flat-price assumption it
            # equals the cone, so the dotted line was redundant.
            out["what_if"] = None
            out["stock_history"] = stock_history
            out["analyst_target"] = analyst_targets_cache.get(tk)
            out["last_synced"] = ticker_cache.get("last_synced")
            rsu_grants_out.append(out)

        # ESPP plans — same stock/FX cache, plan-level purchases & sales.
        espp_plans_out = []
        for plan in DATA.get("espp_plans", []) or []:
            computed = value_espp(plan)
            archived = plan.get("archived")
            projection = project_espp(plan, computed, horizon_months) if not archived else None
            tk = plan["ticker"].upper()
            ticker_cache = MARKET["stock_daily"].get(tk, {})
            stock_rows = ticker_cache.get("rows", []) or []
            purchases_sorted = sorted(plan.get("purchases", []) or [], key=lambda p: p["date"])
            earliest_purchase = purchases_sorted[0]["date"] if purchases_sorted else None
            cutoff = min(cutoff_6m, earliest_purchase) if earliest_purchase else cutoff_6m
            stock_history = [
                {"date": r["date"], "close": r["close"]}
                for r in stock_rows if r.get("date", "") >= cutoff
            ]
            out = dict(plan)
            out["computed"] = computed
            out["projection"] = projection
            out["stock_history"] = stock_history
            out["analyst_target"] = analyst_targets_cache.get(tk)
            out["last_synced"] = ticker_cache.get("last_synced")
            espp_plans_out.append(out)

        # Cash holdings — flat ILS-equivalent values; no historical/projection math.
        cash_holdings_out = []
        fx_now = (MARKET.get("fx", {}).get("USDILS", {}).get("rows") or [{}])[-1].get("close") if MARKET.get("fx", {}).get("USDILS") else None
        override = DATA["settings"].get("usdils_rate_override")
        effective_fx = override if override else fx_now
        for c in DATA.get("cash_holdings", []) or []:
            ccy = (c.get("currency") or "ILS").upper()
            amt = float(c.get("amount") or 0)
            if ccy == "USD" and effective_fx:
                ils_value = amt * effective_fx
            else:
                ils_value = amt
            out = dict(c)
            out["computed"] = {
                "value_ils": round(ils_value, 2),
                "value_native": amt,
                "fx_used": effective_fx if ccy == "USD" else None,
            }
            cash_holdings_out.append(out)

        # Portfolio aggregation (monthly resolution).
        portfolio = compose_portfolio(fund_holdings_out, rsu_grants_out, horizon_months,
                                      assumed_annual_pct, cash_holdings_out, espp_plans_out)

        # cache freshness
        fx_entry = MARKET["fx"].get("USDILS", {})
        ps = MARKET.get("package_show") or {}
        ps_pensia = MARKET.get("pensia_package_show") or {}

        # Pension subtotal — surfaced for the UI but deliberately NOT folded
        # into portfolio.total_value_ils (pension is excluded from the
        # dashboard total per product requirement).
        pension_total_ils = sum(
            float((p.get("computed") or {}).get("current_value_ils") or 0)
            for p in pension_holdings_out
            if not p.get("archived")
        )

        # Aggregate the per-pension what-if into a section-level summary so
        # the UI can show "If funds grow X%/year for N months → ₪Y" without
        # the user expanding individual rows. Element-wise sum across paths.
        pension_what_if = None
        active_pension_wfs = [
            (p.get("what_if") or {}) for p in pension_holdings_out
            if not p.get("archived") and (p.get("what_if") or {}).get("end_value_ils") is not None
        ]
        if active_pension_wfs:
            ref = active_pension_wfs[0]
            n = ref.get("horizon_months") or len(ref.get("paths") or [])
            agg_paths = [0.0] * n
            for wf in active_pension_wfs:
                paths = wf.get("paths") or []
                for i, v in enumerate(paths[:n]):
                    agg_paths[i] += float(v or 0)
            pension_what_if = {
                "annual_pct": ref.get("annual_pct"),
                "monthly_rate": ref.get("monthly_rate"),
                "horizon_months": n,
                "current_value_ils": round(sum(
                    float((wf.get("current_value_ils") or 0)) for wf in active_pension_wfs
                ), 2),
                "paths": [round(v, 2) for v in agg_paths],
                "end_value_ils": round(agg_paths[-1], 2) if agg_paths else None,
                "total_projected_contribution_ils": round(sum(
                    float(wf.get("total_projected_contribution_ils") or 0) for wf in active_pension_wfs
                ), 2),
                "includes_recurring": any(wf.get("includes_recurring") for wf in active_pension_wfs),
            }

        return {
            "ok": True,
            "now": now_iso(),
            "horizon_months": horizon_months,
            "settings": dict(DATA["settings"]),
            "fund_holdings": fund_holdings_out,
            "pension_holdings": pension_holdings_out,
            "rsu_grants": rsu_grants_out,
            "espp_plans": espp_plans_out,
            "cash_holdings": cash_holdings_out,
            "portfolio": portfolio,
            "pension_summary": {
                "total_value_ils": round(pension_total_ils, 2),
                "count": len([p for p in pension_holdings_out if not p.get("archived")]),
                "excluded_from_total": True,
                "what_if": pension_what_if,
            },
            "sync_status": dict(_sync_status),
            "cache_status": {
                "package_show_age_seconds": int(time.time() - ps.get("fetched_at_ts", 0)) if ps else None,
                "pensia_package_show_age_seconds": int(time.time() - ps_pensia.get("fetched_at_ts", 0)) if ps_pensia else None,
                "usdils_age_seconds": int(time.time() - fx_entry.get("last_synced_ts", 0)) if fx_entry else None,
                "current_usdils": (fx_entry.get("rows") or [{}])[-1].get("close") if fx_entry.get("rows") else None,
                "usdils_override": DATA["settings"].get("usdils_rate_override"),
                "last_full_sync_at": CACHE.get("last_full_sync_at"),
                "synced_today": synced_today(),
                "latest_published_period": latest_published_period(),
            },
        }


def compose_portfolio_what_if(current_total: float, annual_pct: float, horizon_months: int,
                              monthly_recurring: list = None,
                              deterministic_per_month: list = None) -> dict:
    """Deterministic what-if compounding at annual_pct/year on `current_total`,
    with optional per-month recurring contributions added before each month's
    compounding, plus an optional deterministic per-month addition that bypasses
    growth (used to fold RSU vesting into the line without applying the growth
    rate to it). All list params should be length horizon_months; missing
    entries treated as 0."""
    if annual_pct is None:
        return None
    try:
        annual_pct = float(annual_pct)
    except (TypeError, ValueError):
        return None
    annual = annual_pct / 100.0
    if 1 + annual <= 0:
        return None
    monthly = (1 + annual) ** (1 / 12) - 1
    contribs = monthly_recurring or [0.0] * horizon_months
    if len(contribs) < horizon_months:
        contribs = list(contribs) + [0.0] * (horizon_months - len(contribs))
    deterministic = deterministic_per_month or [0.0] * horizon_months
    if len(deterministic) < horizon_months:
        deterministic = list(deterministic) + [0.0] * (horizon_months - len(deterministic))
    paths = []
    cur = current_total
    total_contrib = 0.0
    for t in range(horizon_months):
        c = float(contribs[t] or 0.0)
        total_contrib += c
        cur = (cur + c) * (1 + monthly)
        paths.append(round(cur + float(deterministic[t] or 0.0), 2))
    return {
        "annual_pct": annual_pct,
        "monthly_rate": monthly,
        "horizon_months": horizon_months,
        "current_value_ils": round(current_total, 2),
        "paths": paths,
        "end_value_ils": paths[-1] if paths else None,
        "total_projected_contribution_ils": round(total_contrib, 2),
        "includes_recurring": any(c > 0 for c in contribs),
        "includes_deterministic": any(d > 0 for d in deterministic),
    }


def compose_portfolio(funds: list, grants: list, horizon_months: int, assumed_annual_pct=None, cash: list = None, espp: list = None) -> dict:
    espp = espp or []
    # Funds toggled off from the dashboard are excluded from the headline total,
    # the historical stack, the projection cone, and the what-if line. They stay
    # visible in the Funds section. Missing flag means included (default on).
    funds = [h for h in (funds or []) if h.get("included_in_dashboard", True)]
    # Build a unified monthly axis from earliest holding/grant/plan to today.
    if not funds and not grants and not espp:
        return {
            "total_value_ils": 0,
            "funds_value_ils": 0,
            "rsu_value_ils": 0,
            "espp_value_ils": 0,
            "espp_value_usd": 0,
            "total_invested_ils": 0,
            "total_profit_ils": 0,
            "time_series_ils": [],
            "projection": None,
            "rsu_value_usd": 0,
        }
    starts = []
    for h in funds:
        if h.get("archived"):
            continue
        starts.append(int(h["anchor_period"]))
    for g in grants:
        if g.get("archived"):
            continue
        sd = date.fromisoformat(g["grant_date"])
        starts.append(date_period(sd))
    for plan in espp:
        if plan.get("archived"):
            continue
        purchases = plan.get("purchases", []) or []
        if purchases:
            first_p = min(p["date"] for p in purchases)
            starts.append(date_period(date.fromisoformat(first_p)))
    if not starts:
        return {
            "total_value_ils": 0,
            "funds_value_ils": 0,
            "rsu_value_ils": 0,
            "espp_value_ils": 0,
            "espp_value_usd": 0,
            "total_invested_ils": 0,
            "total_profit_ils": 0,
            "time_series_ils": [],
            "projection": None,
            "rsu_value_usd": 0,
        }
    start_p = min(starts)
    end_p = current_period()

    # Per-period fund value: take series value at that period (or last known)
    fund_series_by_holding = []
    for h in funds:
        if h.get("archived"):
            continue
        ts = h["computed"]["time_series"]
        by_period = {pt["period"]: pt["value_ils"] for pt in ts}
        fund_series_by_holding.append((h, by_period))

    # Per-period RSU month-end ILS value (use month-end day's ILS value)
    rsu_month_end = []
    for g in grants:
        if g.get("archived"):
            continue
        ts = g["computed"].get("time_series") or []
        if not ts:
            continue
        last_per_month = {}
        for s in ts:
            ym = s["date"][:7]
            last_per_month[ym] = s
        rsu_month_end.append((g, last_per_month))

    # Per-period ESPP month-end ILS value (parallel to RSU's pattern).
    espp_month_end = []
    for plan in espp:
        if plan.get("archived"):
            continue
        ts = (plan.get("computed") or {}).get("time_series") or []
        if not ts:
            continue
        last_per_month = {}
        for s in ts:
            ym = s["date"][:7]
            last_per_month[ym] = s
        espp_month_end.append((plan, last_per_month))

    series = []
    for period in period_iter(start_p, end_p):
        ym = period_to_yyyymm(period)
        funds_val = 0.0
        rsu_val_ils = 0.0
        rsu_val_usd = 0.0
        espp_val_ils = 0.0
        espp_val_usd = 0.0
        for h, by_period in fund_series_by_holding:
            v = by_period.get(period)
            if v is None:
                # forward-fill from last available period <= period
                latest_p = None
                for p in by_period.keys():
                    if p <= period and (latest_p is None or p > latest_p):
                        latest_p = p
                v = by_period.get(latest_p, 0)
            funds_val += v or 0
        for g, last_per_month in rsu_month_end:
            v = last_per_month.get(ym)
            if v is None:
                # forward-fill
                latest_ym = None
                for k in last_per_month.keys():
                    if k <= ym and (latest_ym is None or k > latest_ym):
                        latest_ym = k
                v = last_per_month.get(latest_ym)
            if v:
                rsu_val_ils += v.get("value_ils") or 0
                rsu_val_usd += v.get("value_usd") or 0
        for plan, last_per_month in espp_month_end:
            v = last_per_month.get(ym)
            if v is None:
                latest_ym = None
                for k in last_per_month.keys():
                    if k <= ym and (latest_ym is None or k > latest_ym):
                        latest_ym = k
                v = last_per_month.get(latest_ym)
            if v:
                espp_val_ils += v.get("value_ils") or 0
                espp_val_usd += v.get("value_usd") or 0
        total = funds_val + rsu_val_ils + espp_val_ils
        series.append({
            "period": ym,
            "funds_ils": round(funds_val, 2),
            "rsu_ils": round(rsu_val_ils, 2),
            "rsu_usd": round(rsu_val_usd, 2),
            "espp_ils": round(espp_val_ils, 2),
            "espp_usd": round(espp_val_usd, 2),
            "total_ils": round(total, 2),
        })

    funds_now = sum(h["computed"]["current_value_ils"] for h in funds if not h.get("archived"))
    rsu_now_ils = sum(g["computed"]["current_value_ils"] for g in grants if not g.get("archived"))
    rsu_now_usd = sum(g["computed"]["current_value_usd"] for g in grants if not g.get("archived"))
    espp_now_ils = sum(p["computed"]["current_value_ils"] for p in espp if not p.get("archived"))
    espp_now_usd = sum(p["computed"]["current_value_usd"] for p in espp if not p.get("archived"))
    cash_now = sum((c.get("computed") or {}).get("value_ils", 0) for c in (cash or []) if not c.get("archived"))
    total_now = funds_now + rsu_now_ils + espp_now_ils + cash_now

    funds_invested = sum(
        float(h["anchor_balance_ils"]) + h["computed"]["total_deposited_ils"] - h["computed"]["total_withdrawn_ils"]
        for h in funds if not h.get("archived")
    )
    funds_profit = sum(h["computed"]["profit_ils"] for h in funds if not h.get("archived"))
    rsu_profit_ils = sum(g["computed"]["profit_ils"] for g in grants if not g.get("archived"))
    espp_profit_ils = sum(p["computed"]["profit_ils"] for p in espp if not p.get("archived"))

    employee_total = sum(h["computed"].get("total_employee_ils", 0) for h in funds if not h.get("archived"))
    employer_total = sum(h["computed"].get("total_employer_ils", 0) for h in funds if not h.get("archived"))

    # Portfolio projection — sum per-holding cones at each horizon step.
    proj = compose_portfolio_projection(funds, grants, horizon_months, espp, cash_now)

    # Aggregate recurring contributions across all active fund holdings, per
    # future month, so the what-if line picks them up too.
    monthly_recurring = [0.0] * horizon_months
    for h in funds:
        if h.get("archived"):
            continue
        contribs = _project_fund_contributions(h, h.get("computed") or {}, horizon_months)
        for i, c in enumerate(contribs):
            monthly_recurring[i] += c

    # What-if: growth rate applies to funds only. Cash + ESPP added flat at every
    # future point (cash sits in bank; ESPP held flat at current value per Option A).
    # RSU contribution is deterministic (vesting × current price × FX), folded in
    # per month so the line reflects the same vesting curve the cone uses.
    rsu_per_month = (proj or {}).get("paths", {}).get("rsu_mean") or [0.0] * horizon_months
    espp_per_month = (proj or {}).get("paths", {}).get("espp_mean") or [espp_now_ils] * horizon_months
    deterministic_per_month = [r + cash_now + e for r, e in zip(rsu_per_month, espp_per_month)]
    what_if = compose_portfolio_what_if(
        funds_now,
        assumed_annual_pct,
        horizon_months,
        monthly_recurring,
        deterministic_per_month=deterministic_per_month,
    )
    if what_if:
        # Keep the displayed "today" baseline as the actual portfolio total so
        # the dashboard's "+delta from today" stays accurate.
        what_if["current_value_ils"] = round(total_now, 2)

    return {
        "total_value_ils": round(total_now, 2),
        "funds_value_ils": round(funds_now, 2),
        "rsu_value_ils": round(rsu_now_ils, 2),
        "rsu_value_usd": round(rsu_now_usd, 2),
        "espp_value_ils": round(espp_now_ils, 2),
        "espp_value_usd": round(espp_now_usd, 2),
        "cash_value_ils": round(cash_now, 2),
        "total_invested_ils": round(funds_invested, 2),
        "funds_profit_ils": round(funds_profit, 2),
        "rsu_profit_ils": round(rsu_profit_ils, 2),
        "espp_profit_ils": round(espp_profit_ils, 2),
        "total_profit_ils": round(funds_profit + rsu_profit_ils + espp_profit_ils, 2),
        "total_employee_ils": round(employee_total, 2),
        "total_employer_ils": round(employer_total, 2),
        "time_series_ils": series,
        "projection": proj,
        "what_if": what_if,
    }


def compose_portfolio_projection(funds: list, grants: list, horizon_months: int,
                                 espp: list = None, cash_now_ils: float = 0.0) -> dict:
    espp = espp or []
    mean_path = [0.0] * horizon_months
    funds_mean = [0.0] * horizon_months
    rsu_mean = [0.0] * horizon_months
    espp_mean = [0.0] * horizon_months
    cash_mean = [round(cash_now_ils, 2)] * horizon_months
    any_data = False
    funds_weight_total = 0.0
    funds_weighted_annual = 0.0
    funds_includes_recurring = False
    for h in funds:
        if h.get("archived"):
            continue
        p = h.get("projection")
        if not p:
            continue
        any_data = True
        if p.get("includes_recurring"):
            funds_includes_recurring = True
        annual_pct = p.get("annual_pct")
        if annual_pct is not None:
            val = float((h.get("computed") or {}).get("current_value_ils") or 0)
            if val > 0:
                funds_weight_total += val
                funds_weighted_annual += val * float(annual_pct)
        for i in range(horizon_months):
            mean_path[i] += p["paths"]["mean"][i]
            funds_mean[i] += p["paths"]["mean"][i]
    for g in grants:
        if g.get("archived"):
            continue
        p = g.get("projection")
        if not p:
            continue
        any_data = True
        for i in range(horizon_months):
            mean_path[i] += p["paths"]["mean"][i]
            rsu_mean[i] += p["paths"]["mean"][i]
    for plan in espp:
        if plan.get("archived"):
            continue
        p = plan.get("projection")
        if not p:
            continue
        any_data = True
        for i in range(horizon_months):
            mean_path[i] += p["paths"]["mean"][i]
            espp_mean[i] += p["paths"]["mean"][i]
    # Cash always contributes if non-zero (even with no funds/RSU/ESPP).
    if cash_now_ils > 0:
        any_data = True
        for i in range(horizon_months):
            mean_path[i] += cash_now_ils
    if not any_data:
        return None
    return {
        "paths": {
            "mean": [round(v, 2) for v in mean_path],
            "funds_mean": [round(v, 2) for v in funds_mean],
            "rsu_mean": [round(v, 2) for v in rsu_mean],
            "espp_mean": [round(v, 2) for v in espp_mean],
            "cash_mean": cash_mean,
        },
        "horizon_months": horizon_months,
        "funds_annual_pct": round(funds_weighted_annual / funds_weight_total, 2)
        if funds_weight_total > 0 else None,
        "funds_includes_recurring": funds_includes_recurring,
    }


# ── Mutating actions on DATA ─────────────────────────────────────────────────
def prepare_fund(fund_id: int, source: str = "gemelnet") -> dict:
    """Sync history for a fund (if needed) and return available periods + meta.

    Used by the Add Fund flow so the user can pick which period their reported
    balance is actually as of.
    """
    if source not in SOURCE_CONFIG:
        return {"ok": False, "error": f"Unknown data source: {source}"}
    monthly_key = SOURCE_CONFIG[source]["monthly_cache_key"]
    cache_entry = MARKET[monthly_key].get(str(fund_id))
    if not cache_entry or not cache_entry.get("rows"):
        try:
            gemelnet_fetch_history(fund_id, full=True, source=source)
            cache_entry = MARKET[monthly_key].get(str(fund_id), {})
        except Exception as ex:
            return {"ok": False, "error": f"Failed to sync fund {fund_id}: {ex}"}
    rows = cache_entry.get("rows", [])
    if not rows:
        return {"ok": False, "error": f"No data found for FUND_ID {fund_id}"}
    periods = sorted({int(r["report_period"]) for r in rows}, reverse=True)
    meta = cache_entry.get("meta") or {}
    return {"ok": True, "periods": periods, "meta": meta, "data_source": source}


def add_fund_holding(payload: dict) -> dict:
    fund_id = int(payload["fund_id"])
    source = (payload.get("data_source") or "gemelnet").strip()
    if source not in ("gemelnet", "insurance"):
        return {"ok": False, "error": f"Unsupported data_source: {source}"}
    nickname = (payload.get("nickname") or "").strip()
    anchor_balance = float(payload.get("anchor_balance_ils") or 0)
    yield_is_net = bool(payload.get("yield_is_net_of_fees", DATA["settings"]["yield_is_net_of_fees"]))
    requested_period = payload.get("anchor_period")

    monthly_key = SOURCE_CONFIG[source]["monthly_cache_key"]
    cache_entry = MARKET[monthly_key].get(str(fund_id))
    if not cache_entry or not cache_entry.get("rows"):
        try:
            gemelnet_fetch_history(fund_id, full=True, source=source)
            cache_entry = MARKET[monthly_key].get(str(fund_id), {})
        except Exception as ex:
            return {"ok": False, "error": f"Failed to sync fund {fund_id}: {ex}"}

    rows = cache_entry.get("rows", [])
    if not rows:
        return {"ok": False, "error": f"No data found for FUND_ID {fund_id}"}
    available_periods = sorted({int(r["report_period"]) for r in rows})
    last_period = available_periods[-1]

    if requested_period is not None and requested_period != "":
        try:
            requested_period = int(requested_period)
        except (TypeError, ValueError):
            return {"ok": False, "error": "anchor_period must be YYYYMM integer"}
        if requested_period not in available_periods:
            return {
                "ok": False,
                "error": f"No data for period {requested_period}. Available: {available_periods[-12:]}",
            }
        anchor_period = requested_period
    else:
        anchor_period = last_period

    meta = cache_entry.get("meta") or {}

    holding = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "fund_id": fund_id,
        "data_source": source,
        "fund_name_snapshot": meta.get("fund_name", ""),
        "managing_corporation_snapshot": meta.get("managing_corporation", ""),
        "classification_snapshot": meta.get("classification", ""),
        "nickname": nickname or meta.get("fund_name", str(fund_id)),
        "yield_is_net_of_fees": yield_is_net,
        "anchor_period": anchor_period,
        "anchor_balance_ils": anchor_balance,
        "events": [],
        "recurring_rules": [],
        "archived": False,
        "included_in_dashboard": True,
    }
    with _data_lock:
        DATA["fund_holdings"].append(holding)
        save_data()
    return {"ok": True, "holding_id": holding["id"], "anchor_period": anchor_period}


def _validate_rule_payload(payload: dict) -> tuple:
    """Return (cleaned_dict, error_string_or_None)."""
    try:
        start = payload["start_date"]
        date.fromisoformat(start)
    except (KeyError, ValueError, TypeError):
        return None, "start_date (YYYY-MM-DD) is required"
    end = payload.get("end_date")
    if end:
        try:
            ed = date.fromisoformat(end)
            sd = date.fromisoformat(start)
            if ed < sd:
                return None, "end_date is before start_date"
        except (ValueError, TypeError):
            return None, "Invalid end_date"
    employee = float(payload.get("employee") or 0)
    employer = float(payload.get("employer") or 0)
    if employee < 0 or employer < 0:
        return None, "Amounts cannot be negative"
    if employee + employer == 0:
        return None, "At least one of employee/employer must be > 0"
    dom = int(payload.get("day_of_month") or 1)
    if dom < 1 or dom > 28:
        return None, "day_of_month must be 1..28"
    cleaned = {
        "start_date": start,
        "end_date": end or None,
        "employee": employee,
        "employer": employer,
        "day_of_month": dom,
        "note": (payload.get("note") or "").strip(),
    }
    return cleaned, None


def _find_holding(holding_id: str) -> dict:
    """Look up a holding by id in BOTH fund_holdings and pension_holdings.
    Rule CRUD uses this so the same code path handles both. UUIDs make
    collisions impossible."""
    for h in DATA["fund_holdings"]:
        if h["id"] == holding_id:
            return h
    for h in DATA.get("pension_holdings", []) or []:
        if h["id"] == holding_id:
            return h
    return None


def add_rule(holding_id: str, payload: dict) -> dict:
    cleaned, err = _validate_rule_payload(payload)
    if err:
        return {"ok": False, "error": err}
    new_start = date.fromisoformat(cleaned["start_date"])
    rule = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        **cleaned,
    }
    with _data_lock:
        h = _find_holding(holding_id)
        if not h:
            return {"ok": False, "error": "Holding not found"}
        rules = h.setdefault("recurring_rules", [])
        # Auto-close any prior open-ended rule that overlaps.
        for r in rules:
            if r.get("end_date"):
                continue
            r_start = date.fromisoformat(r["start_date"])
            if r_start < new_start:
                r["end_date"] = (new_start - timedelta(days=1)).isoformat()
        # Reject obvious overlaps with closed rules
        for r in rules:
            if r["id"] == rule["id"]:
                continue
            r_start = date.fromisoformat(r["start_date"])
            r_end = date.fromisoformat(r["end_date"]) if r.get("end_date") else None
            new_end = date.fromisoformat(rule["end_date"]) if rule.get("end_date") else None
            if r_end is None or new_end is None:
                continue
            if r_start <= new_end and new_start <= r_end:
                return {"ok": False, "error": f"Overlaps an existing rule ({r['start_date']} → {r.get('end_date') or 'open'})"}
        rules.append(rule)
        rules.sort(key=lambda x: x["start_date"])
        save_data()
    return {"ok": True, "rule_id": rule["id"]}


def update_rule(holding_id: str, rule_id: str, patch: dict) -> dict:
    with _data_lock:
        h = _find_holding(holding_id)
        if not h:
            return {"ok": False, "error": "Holding not found"}
        rules = h.get("recurring_rules", [])
        r = next((x for x in rules if x["id"] == rule_id), None)
        if not r:
            return {"ok": False, "error": "Rule not found"}
        # Build merged payload then validate
        merged = {**r, **{k: v for k, v in patch.items() if k in ("start_date","end_date","employee","employer","day_of_month","note")}}
        cleaned, err = _validate_rule_payload(merged)
        if err:
            return {"ok": False, "error": err}
        for k, v in cleaned.items():
            r[k] = v
        rules.sort(key=lambda x: x["start_date"])
        save_data()
    return {"ok": True}


def delete_rule(holding_id: str, rule_id: str) -> dict:
    with _data_lock:
        h = _find_holding(holding_id)
        if not h:
            return {"ok": False, "error": "Holding not found"}
        rules = h.get("recurring_rules", [])
        before = len(rules)
        h["recurring_rules"] = [r for r in rules if r["id"] != rule_id]
        if len(h["recurring_rules"]) == before:
            return {"ok": False, "error": "Rule not found"}
        save_data()
    return {"ok": True}


def update_fund_holding(holding_id: str, patch: dict) -> dict:
    with _data_lock:
        for h in DATA["fund_holdings"]:
            if h["id"] == holding_id:
                for k in ("nickname", "anchor_balance_ils", "yield_is_net_of_fees", "archived", "included_in_dashboard"):
                    if k in patch:
                        h[k] = patch[k]
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Holding not found"}


def delete_fund_holding(holding_id: str) -> dict:
    with _data_lock:
        for i, h in enumerate(DATA["fund_holdings"]):
            if h["id"] == holding_id:
                DATA["fund_holdings"].pop(i)
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Holding not found"}


# ── Pension CRUD (mirrors fund handlers, sourced from pensia-net) ────────────
def prepare_pension(fund_id: int) -> dict:
    """Sync pensia-net history for fund_id and return available periods + meta."""
    cache_entry = MARKET["pensia_monthly"].get(str(fund_id))
    if not cache_entry or not cache_entry.get("rows"):
        try:
            gemelnet_fetch_history(fund_id, full=True, source="pensia")
            cache_entry = MARKET["pensia_monthly"].get(str(fund_id), {})
        except Exception as ex:
            return {"ok": False, "error": f"Failed to sync pension fund {fund_id}: {ex}"}
    rows = cache_entry.get("rows", [])
    if not rows:
        return {"ok": False, "error": f"No data found for FUND_ID {fund_id}"}
    periods = sorted({int(r["report_period"]) for r in rows}, reverse=True)
    meta = cache_entry.get("meta") or {}
    return {"ok": True, "periods": periods, "meta": meta}


def add_pension_holding(payload: dict) -> dict:
    fund_id = int(payload["fund_id"])
    nickname = (payload.get("nickname") or "").strip()
    anchor_balance = float(payload.get("anchor_balance_ils") or 0)
    yield_is_net = bool(payload.get("yield_is_net_of_fees", DATA["settings"]["yield_is_net_of_fees"]))
    requested_period = payload.get("anchor_period")

    cache_entry = MARKET["pensia_monthly"].get(str(fund_id))
    if not cache_entry or not cache_entry.get("rows"):
        try:
            gemelnet_fetch_history(fund_id, full=True, source="pensia")
            cache_entry = MARKET["pensia_monthly"].get(str(fund_id), {})
        except Exception as ex:
            return {"ok": False, "error": f"Failed to sync pension fund {fund_id}: {ex}"}

    rows = cache_entry.get("rows", [])
    if not rows:
        return {"ok": False, "error": f"No data found for FUND_ID {fund_id}"}
    available_periods = sorted({int(r["report_period"]) for r in rows})
    last_period = available_periods[-1]

    if requested_period is not None and requested_period != "":
        try:
            requested_period = int(requested_period)
        except (TypeError, ValueError):
            return {"ok": False, "error": "anchor_period must be YYYYMM integer"}
        if requested_period not in available_periods:
            return {
                "ok": False,
                "error": f"No data for period {requested_period}. Available: {available_periods[-12:]}",
            }
        anchor_period = requested_period
    else:
        anchor_period = last_period

    meta = cache_entry.get("meta") or {}
    holding = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "fund_id": fund_id,
        "fund_name_snapshot": meta.get("fund_name", ""),
        "managing_corporation_snapshot": meta.get("managing_corporation", ""),
        "classification_snapshot": meta.get("classification", ""),
        "nickname": nickname or meta.get("fund_name", str(fund_id)),
        "yield_is_net_of_fees": yield_is_net,
        "anchor_period": anchor_period,
        "anchor_balance_ils": anchor_balance,
        "events": [],
        "recurring_rules": [],
        "archived": False,
    }
    with _data_lock:
        DATA["pension_holdings"].append(holding)
        save_data()
    return {"ok": True, "holding_id": holding["id"], "anchor_period": anchor_period}


def update_pension_holding(holding_id: str, patch: dict) -> dict:
    with _data_lock:
        for h in DATA["pension_holdings"]:
            if h["id"] == holding_id:
                for k in ("nickname", "anchor_balance_ils", "yield_is_net_of_fees", "archived"):
                    if k in patch:
                        h[k] = patch[k]
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Pension holding not found"}


def delete_pension_holding(holding_id: str) -> dict:
    with _data_lock:
        for i, h in enumerate(DATA["pension_holdings"]):
            if h["id"] == holding_id:
                DATA["pension_holdings"].pop(i)
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Pension holding not found"}


def add_event(holding_id: str, payload: dict) -> dict:
    kind = payload.get("kind")
    if kind not in ("deposit", "withdrawal", "correction"):
        return {"ok": False, "error": "kind must be deposit/withdrawal/correction"}
    try:
        ev_date = payload.get("date")
        date.fromisoformat(ev_date)
    except (ValueError, TypeError):
        return {"ok": False, "error": "Invalid date"}
    amount = float(payload.get("amount_ils") or 0)
    if amount <= 0 and kind != "correction":
        return {"ok": False, "error": "Amount must be > 0"}
    event = {
        "id": str(uuid.uuid4()),
        "date": ev_date,
        "kind": kind,
        "amount_ils": amount,
        "note": (payload.get("note") or "").strip(),
        "source": "manual",
    }
    with _data_lock:
        for h in DATA["fund_holdings"]:
            if h["id"] == holding_id:
                h.setdefault("events", []).append(event)
                h["events"].sort(key=lambda e: e["date"])
                save_data()
                return {"ok": True, "event_id": event["id"]}
    return {"ok": False, "error": "Holding not found"}


def delete_event(holding_id: str, event_id: str) -> dict:
    with _data_lock:
        for h in DATA["fund_holdings"]:
            if h["id"] == holding_id:
                before = len(h.get("events", []))
                h["events"] = [e for e in h.get("events", []) if e["id"] != event_id]
                if len(h["events"]) == before:
                    return {"ok": False, "error": "Event not found"}
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Holding not found"}


def add_rsu_grant(payload: dict) -> dict:
    try:
        override = payload.get("grant_price_override_usd")
        if override in ("", None):
            override = None
        else:
            override = float(override)
            if override <= 0:
                return {"ok": False, "error": "grant_price_override_usd must be > 0"}
        grant = {
            "id": str(uuid.uuid4()),
            "created_at": now_iso(),
            "ticker": payload["ticker"].upper().strip(),
            "nickname": (payload.get("nickname") or "").strip() or payload["ticker"].upper(),
            "grant_date": payload["grant_date"],
            "total_shares": int(payload["total_shares"]),
            "vesting_start": payload.get("vesting_start") or payload["grant_date"],
            "vesting_months": int(payload.get("vesting_months") or 48),
            "cliff_months": int(payload.get("cliff_months") or 12),
            "vesting_cadence": payload.get("vesting_cadence") or "monthly",
            "grant_price_override_usd": override,
            "sales": [],
            "archived": False,
        }
        date.fromisoformat(grant["grant_date"])
        date.fromisoformat(grant["vesting_start"])
    except (KeyError, ValueError, TypeError) as ex:
        return {"ok": False, "error": f"Invalid grant: {ex}"}
    # Sync prices for ticker since grant_date.
    try:
        yahoo_fetch_stock(grant["ticker"], grant["grant_date"])
        if not MARKET["fx"].get("USDILS"):
            yahoo_fetch_fx_usdils(grant["grant_date"])
    except Exception as ex:
        return {"ok": False, "error": f"Could not fetch prices for {grant['ticker']}: {ex}"}
    # Best-effort: fetch analyst target for the new ticker. None on failure
    # or no analyst coverage; the rest of the flow continues either way.
    yahoo_fetch_analyst_target(grant["ticker"])
    with _data_lock:
        DATA["rsu_grants"].append(grant)
        save_data()
    return {"ok": True, "grant_id": grant["id"]}


def update_rsu_grant(grant_id: str, patch: dict) -> dict:
    with _data_lock:
        for g in DATA["rsu_grants"]:
            if g["id"] == grant_id:
                for k in ("nickname", "total_shares", "vesting_start", "vesting_months",
                          "cliff_months", "vesting_cadence", "archived"):
                    if k in patch:
                        g[k] = patch[k]
                if "grant_price_override_usd" in patch:
                    v = patch["grant_price_override_usd"]
                    if v in ("", None):
                        g["grant_price_override_usd"] = None
                    else:
                        try:
                            fv = float(v)
                            if fv <= 0:
                                return {"ok": False, "error": "grant_price_override_usd must be > 0"}
                            g["grant_price_override_usd"] = fv
                        except (TypeError, ValueError):
                            return {"ok": False, "error": "Invalid grant_price_override_usd"}
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Grant not found"}


def delete_rsu_grant(grant_id: str) -> dict:
    with _data_lock:
        for i, g in enumerate(DATA["rsu_grants"]):
            if g["id"] == grant_id:
                DATA["rsu_grants"].pop(i)
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Grant not found"}


def add_rsu_sale(grant_id: str, payload: dict) -> dict:
    try:
        sale_date = payload["date"]
        date.fromisoformat(sale_date)
        shares = int(payload["shares_sold"])
        if shares <= 0:
            return {"ok": False, "error": "shares_sold must be > 0"}
        sale_price = float(payload["sale_price_usd"])
        if sale_price <= 0:
            return {"ok": False, "error": "sale_price_usd must be > 0"}
    except (KeyError, ValueError, TypeError) as ex:
        return {"ok": False, "error": f"Invalid sale: {ex}"}

    with _data_lock:
        g = next((x for x in DATA["rsu_grants"] if x["id"] == grant_id), None)
        if not g:
            return {"ok": False, "error": "Grant not found"}

        # Validate: cannot sell more than vested-minus-already-sold on the sale date
        vested_at_sale = vested_shares(g, sale_date)
        already_sold_on_or_before = sum(
            int(s["shares_sold"]) for s in g.get("sales", [])
            if s["date"] <= sale_date
        )
        available = vested_at_sale - already_sold_on_or_before
        if shares > available:
            return {
                "ok": False,
                "error": f"Cannot sell {shares} shares on {sale_date}: only {available} were available "
                         f"(vested {vested_at_sale}, already sold {already_sold_on_or_before}).",
            }

        sale = {
            "id": str(uuid.uuid4()),
            "date": sale_date,
            "shares_sold": shares,
            "sale_price_usd": sale_price,
            "note": (payload.get("note") or "").strip(),
        }
        g.setdefault("sales", []).append(sale)
        g["sales"].sort(key=lambda s: s["date"])
        save_data()
    return {"ok": True, "sale_id": sale["id"]}


def delete_rsu_sale(grant_id: str, sale_id: str) -> dict:
    with _data_lock:
        g = next((x for x in DATA["rsu_grants"] if x["id"] == grant_id), None)
        if not g:
            return {"ok": False, "error": "Grant not found"}
        before = len(g.get("sales", []))
        g["sales"] = [s for s in g.get("sales", []) if s["id"] != sale_id]
        if len(g["sales"]) == before:
            return {"ok": False, "error": "Sale not found"}
        save_data()
    return {"ok": True}


# ── ESPP plans / purchases / sales ───────────────────────────────────────────
def add_espp_plan(payload: dict) -> dict:
    try:
        ticker = payload["ticker"].upper().strip()
        if not ticker:
            return {"ok": False, "error": "ticker required"}
        discount_pct = float(payload.get("discount_pct") or 15.0)
        if discount_pct < 0 or discount_pct >= 100:
            return {"ok": False, "error": "discount_pct must be in [0, 100)"}
        offering_months = int(payload.get("offering_months") or 6)
        if offering_months <= 0:
            return {"ok": False, "error": "offering_months must be > 0"}
        plan = {
            "id": str(uuid.uuid4()),
            "created_at": now_iso(),
            "ticker": ticker,
            "nickname": (payload.get("nickname") or "").strip() or ticker,
            "discount_pct": discount_pct,
            "has_lookback": bool(payload.get("has_lookback", True)),
            "offering_months": offering_months,
            "purchases": [],
            "sales": [],
            "archived": False,
        }
    except (KeyError, ValueError, TypeError) as ex:
        return {"ok": False, "error": f"Invalid plan: {ex}"}
    # Best-effort price + analyst sync (~last 6m or so; first purchase will
    # extend the window when logged).
    try:
        since = (date.today() - timedelta(days=400)).isoformat()
        yahoo_fetch_stock(ticker, since)
        if not MARKET["fx"].get("USDILS"):
            yahoo_fetch_fx_usdils(since)
    except Exception as ex:
        return {"ok": False, "error": f"Could not fetch prices for {ticker}: {ex}"}
    yahoo_fetch_analyst_target(ticker)
    with _data_lock:
        DATA.setdefault("espp_plans", []).append(plan)
        save_data()
    return {"ok": True, "plan_id": plan["id"]}


def update_espp_plan(plan_id: str, patch: dict) -> dict:
    with _data_lock:
        plan = next((p for p in DATA.get("espp_plans", []) or [] if p["id"] == plan_id), None)
        if not plan:
            return {"ok": False, "error": "Plan not found"}
        if "nickname" in patch:
            plan["nickname"] = (patch["nickname"] or "").strip() or plan["ticker"]
        if "discount_pct" in patch:
            try:
                v = float(patch["discount_pct"])
                if v < 0 or v >= 100:
                    return {"ok": False, "error": "discount_pct must be in [0, 100)"}
                plan["discount_pct"] = v
            except (TypeError, ValueError):
                return {"ok": False, "error": "Invalid discount_pct"}
        if "has_lookback" in patch:
            plan["has_lookback"] = bool(patch["has_lookback"])
        if "offering_months" in patch:
            try:
                v = int(patch["offering_months"])
                if v <= 0:
                    return {"ok": False, "error": "offering_months must be > 0"}
                plan["offering_months"] = v
            except (TypeError, ValueError):
                return {"ok": False, "error": "Invalid offering_months"}
        if "archived" in patch:
            plan["archived"] = bool(patch["archived"])
        save_data()
    return {"ok": True}


def delete_espp_plan(plan_id: str) -> dict:
    with _data_lock:
        plans = DATA.get("espp_plans", []) or []
        for i, p in enumerate(plans):
            if p["id"] == plan_id:
                plans.pop(i)
                DATA["espp_plans"] = plans
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Plan not found"}


def add_espp_purchase(plan_id: str, payload: dict) -> dict:
    try:
        purchase_date = payload["date"]
        date.fromisoformat(purchase_date)
        contribution = float(payload["contribution_usd"])
        period_start = float(payload["period_start_price_usd"])
        period_end = float(payload["period_end_price_usd"])
        sell_immediately = bool(payload.get("sell_immediately", False))
        note = (payload.get("note") or "").strip()
    except (KeyError, ValueError, TypeError) as ex:
        return {"ok": False, "error": f"Invalid purchase: {ex}"}

    with _data_lock:
        plan = next((p for p in DATA.get("espp_plans", []) or [] if p["id"] == plan_id), None)
        if not plan:
            return {"ok": False, "error": "Plan not found"}
        try:
            br = _espp_purchase_breakdown(plan, contribution, period_start, period_end)
        except ValueError as ex:
            return {"ok": False, "error": str(ex)}
        purchase = {
            "id": str(uuid.uuid4()),
            "date": purchase_date,
            "contribution_usd": contribution,
            "period_start_price_usd": period_start,
            "period_end_price_usd": period_end,
            "purchase_price_usd": br["purchase_price_usd"],
            "shares": round(br["shares"], 4),
            "note": note,
        }
        plan.setdefault("purchases", []).append(purchase)
        plan["purchases"].sort(key=lambda p: p["date"])

        sale_id = None
        if sell_immediately:
            sale = {
                "id": str(uuid.uuid4()),
                "date": purchase_date,
                "shares_sold": round(br["shares"], 4),
                "sale_price_usd": period_end,
                "purchase_id": purchase["id"],
                "note": note or "auto-fill at period end",
            }
            plan.setdefault("sales", []).append(sale)
            plan["sales"].sort(key=lambda s: s["date"])
            sale_id = sale["id"]
        save_data()

    # Best-effort: extend stock history back to the purchase date if needed.
    try:
        yahoo_fetch_stock(plan["ticker"], purchase_date)
    except Exception:
        pass
    return {
        "ok": True,
        "purchase_id": purchase["id"],
        "sale_id": sale_id,
        "shares": purchase["shares"],
        "purchase_price_usd": purchase["purchase_price_usd"],
        "discount_captured_usd": round(br["discount_captured_usd"], 2),
        "lookback_bonus_usd": round(br["lookback_bonus_usd"], 2),
    }


def delete_espp_purchase(plan_id: str, purchase_id: str) -> dict:
    with _data_lock:
        plan = next((p for p in DATA.get("espp_plans", []) or [] if p["id"] == plan_id), None)
        if not plan:
            return {"ok": False, "error": "Plan not found"}
        before = len(plan.get("purchases", []))
        plan["purchases"] = [p for p in plan.get("purchases", []) if p["id"] != purchase_id]
        if len(plan["purchases"]) == before:
            return {"ok": False, "error": "Purchase not found"}
        # Cascade: drop any auto-fill sale tied to this purchase.
        plan["sales"] = [s for s in plan.get("sales", []) if s.get("purchase_id") != purchase_id]
        save_data()
    return {"ok": True}


def add_espp_sale(plan_id: str, payload: dict) -> dict:
    try:
        sale_date = payload["date"]
        date.fromisoformat(sale_date)
        shares = float(payload["shares_sold"])
        if shares <= 0:
            return {"ok": False, "error": "shares_sold must be > 0"}
        sale_price = float(payload["sale_price_usd"])
        if sale_price <= 0:
            return {"ok": False, "error": "sale_price_usd must be > 0"}
    except (KeyError, ValueError, TypeError) as ex:
        return {"ok": False, "error": f"Invalid sale: {ex}"}

    with _data_lock:
        plan = next((p for p in DATA.get("espp_plans", []) or [] if p["id"] == plan_id), None)
        if not plan:
            return {"ok": False, "error": "Plan not found"}
        # Validate against held shares on sale date.
        purchased_to_date = sum(
            float(p.get("shares") or 0) for p in plan.get("purchases", []) or []
            if p["date"] <= sale_date
        )
        sold_to_date = sum(
            float(s.get("shares_sold") or 0) for s in plan.get("sales", []) or []
            if s["date"] <= sale_date
        )
        available = purchased_to_date - sold_to_date
        if shares > available + 1e-6:  # tiny float slack
            return {
                "ok": False,
                "error": f"Cannot sell {shares} on {sale_date}: only {round(available, 4)} available "
                         f"(purchased {round(purchased_to_date, 4)}, already sold {round(sold_to_date, 4)}).",
            }
        sale = {
            "id": str(uuid.uuid4()),
            "date": sale_date,
            "shares_sold": shares,
            "sale_price_usd": sale_price,
            "note": (payload.get("note") or "").strip(),
        }
        plan.setdefault("sales", []).append(sale)
        plan["sales"].sort(key=lambda s: s["date"])
        save_data()
    return {"ok": True, "sale_id": sale["id"]}


def delete_espp_sale(plan_id: str, sale_id: str) -> dict:
    with _data_lock:
        plan = next((p for p in DATA.get("espp_plans", []) or [] if p["id"] == plan_id), None)
        if not plan:
            return {"ok": False, "error": "Plan not found"}
        before = len(plan.get("sales", []))
        plan["sales"] = [s for s in plan.get("sales", []) if s["id"] != sale_id]
        if len(plan["sales"]) == before:
            return {"ok": False, "error": "Sale not found"}
        save_data()
    return {"ok": True}


# ── Cash / non-invested holdings ─────────────────────────────────────────────
_VALID_CASH_CCY = ("ILS", "USD")


def add_cash_holding(payload: dict) -> dict:
    nickname = (payload.get("nickname") or "").strip()
    try:
        amount = float(payload.get("amount") or 0)
    except (TypeError, ValueError):
        return {"ok": False, "error": "amount must be a number"}
    if amount < 0:
        return {"ok": False, "error": "amount cannot be negative"}
    currency = (payload.get("currency") or "ILS").upper()
    if currency not in _VALID_CASH_CCY:
        return {"ok": False, "error": f"currency must be {' or '.join(_VALID_CASH_CCY)}"}
    if not nickname:
        return {"ok": False, "error": "nickname is required"}
    # If USD and no FX cached, pull USDILS so the ILS conversion works.
    if currency == "USD":
        with _cache_lock:
            fx_rows = (MARKET.get("fx", {}).get("USDILS", {}) or {}).get("rows") or []
        if not fx_rows:
            try:
                yahoo_fetch_fx_usdils()
            except Exception as ex:
                return {"ok": False, "error": f"Could not fetch USDILS rate: {ex}"}
    item = {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "nickname": nickname,
        "amount": amount,
        "currency": currency,
        "note": (payload.get("note") or "").strip(),
        "archived": False,
    }
    with _data_lock:
        DATA.setdefault("cash_holdings", []).append(item)
        save_data()
    return {"ok": True, "id": item["id"]}


def update_cash_holding(cash_id: str, patch: dict) -> dict:
    with _data_lock:
        items = DATA.setdefault("cash_holdings", [])
        c = next((x for x in items if x["id"] == cash_id), None)
        if not c:
            return {"ok": False, "error": "Cash holding not found"}
        if "nickname" in patch:
            v = (patch["nickname"] or "").strip()
            if not v:
                return {"ok": False, "error": "nickname cannot be empty"}
            c["nickname"] = v
        if "amount" in patch:
            try:
                v = float(patch["amount"])
            except (TypeError, ValueError):
                return {"ok": False, "error": "amount must be a number"}
            if v < 0:
                return {"ok": False, "error": "amount cannot be negative"}
            c["amount"] = v
        if "currency" in patch:
            v = (patch["currency"] or "ILS").upper()
            if v not in _VALID_CASH_CCY:
                return {"ok": False, "error": f"currency must be {' or '.join(_VALID_CASH_CCY)}"}
            c["currency"] = v
        if "note" in patch:
            c["note"] = (patch["note"] or "").strip()
        if "archived" in patch:
            c["archived"] = bool(patch["archived"])
        save_data()
    return {"ok": True}


def delete_cash_holding(cash_id: str) -> dict:
    with _data_lock:
        items = DATA.setdefault("cash_holdings", [])
        for i, c in enumerate(items):
            if c["id"] == cash_id:
                items.pop(i)
                save_data()
                return {"ok": True}
    return {"ok": False, "error": "Cash holding not found"}


def update_settings(patch: dict) -> dict:
    with _data_lock:
        for k in ("yield_is_net_of_fees", "usdils_rate_override"):
            if k in patch:
                DATA["settings"][k] = patch[k]
        save_data()
    return {"ok": True, "settings": dict(DATA["settings"])}


def import_data(payload: dict) -> dict:
    if not isinstance(payload, dict) or "version" not in payload:
        return {"ok": False, "error": "Not a valid saving-tracker export"}
    if not all(k in payload for k in ("settings", "fund_holdings", "rsu_grants")):
        return {"ok": False, "error": "Missing required keys"}
    global DATA
    with _data_lock:
        DATA = payload
        _migrate_state_payload()
        save_data()
    return {"ok": True}


def delete_account(user_id: int, password: str) -> dict:
    user = db.get_user_by_id(user_id)
    if not user:
        return {"ok": False, "error": "User not found"}
    if not auth.verify_password(password, user["password_hash"]):
        return {"ok": False, "error": "Incorrect password"}
    if not db.delete_user(user_id):
        return {"ok": False, "error": "Could not delete account"}
    global DATA, CACHE, ACTIVE_USER_ID
    with _user_ctx_lock:
        if ACTIVE_USER_ID == user_id:
            ACTIVE_USER_ID = None
            DATA = default_data()
            CACHE = default_user_cache()
    return {"ok": True, "message": "Account deleted"}


def change_password(user_id: int, current_password: str, new_password: str) -> dict:
    user = db.get_user_by_id(user_id)
    if not user:
        return {"ok": False, "error": "User not found"}
    if not auth.verify_password(current_password, user["password_hash"]):
        return {"ok": False, "error": "Current password is incorrect"}
    err = _validate_password(new_password)
    if err:
        return {"ok": False, "error": err}
    if auth.verify_password(new_password, user["password_hash"]):
        return {"ok": False, "error": "New password must be different from current password"}
    if not db.update_password_hash(user_id, auth.hash_password(new_password)):
        return {"ok": False, "error": "Could not update password"}
    return {"ok": True, "message": "Password updated"}


# ── HTTP server ──────────────────────────────────────────────────────────────
PUBLIC_PATHS = {"/api/login", "/api/register", "/api/health", "/api/version"}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors_headers(self) -> dict:
        if not CORS_ORIGIN:
            return {}
        return {
            "Access-Control-Allow-Origin": CORS_ORIGIN,
            "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Max-Age": "86400",
        }

    def _bearer_token(self) -> str | None:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:].strip()
        return None

    def _verify_cron_secret(self) -> bool:
        if not CRON_SECRET:
            print("cron auth: rejected — CRON_SECRET not configured on server")
            self._json(503, {"ok": False, "error": "Cron not configured"})
            return False
        token = self._bearer_token()
        if not token or not secrets.compare_digest(token, CRON_SECRET):
            print("cron auth: rejected — invalid or missing bearer token")
            self._json(401, {"ok": False, "error": "Unauthorized"})
            return False
        return True

    def _auth_user_id(self) -> int | None:
        token = self._bearer_token()
        if not token:
            return None
        payload = auth.decode_token(token)
        if not payload:
            return None
        try:
            return int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            return None

    def _require_auth(self, path: str) -> int | None:
        if path in PUBLIC_PATHS:
            return 0
        user_id = self._auth_user_id()
        if user_id is None:
            self._json(401, {"ok": False, "error": "Unauthorized"})
            return None
        return user_id

    def do_OPTIONS(self):
        self._write(204, "text/plain", b"", extra_headers=self._cors_headers())

    def _write(self, code: int, ctype: str, body: bytes, extra_headers: dict = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        headers = dict(self._cors_headers())
        if extra_headers:
            headers.update(extra_headers)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._write(code, "application/json; charset=utf-8", body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    # ── GET ─────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query or "")

        if path == "/api/health":
            self._json(200, {"ok": True, "status": "healthy"})
            return

        if path == "/api/cron/status":
            if not self._verify_cron_secret():
                return
            self._json(200, {"ok": True, "status": dict(_cron_status)})
            return

        user_id = self._require_auth(path)
        if user_id is None:
            return
        if user_id == 0:
            self.send_error(404)
            return

        with _user_ctx_lock:
            _activate_user(user_id)

        if path == "/api/version":
            self._write(200, "application/json", json.dumps({"version": "0.0.2"}).encode())
            return

        if path == "/api/data":
            try:
                horizon = int((qs.get("horizon") or ["24"])[0])
                horizon = max(1, min(HORIZON_CAP_MONTHS, horizon))
            except ValueError:
                horizon = 24
            assumed_pct = None
            raw = (qs.get("assumed_annual_pct") or [""])[0]
            if raw:
                try:
                    assumed_pct = float(raw)
                except ValueError:
                    assumed_pct = None
            try:
                self._json(200, compose_state(horizon, assumed_pct))
            except Exception as ex:
                self._json(500, {"ok": False, "error": str(ex)})
            return

        if path == "/api/funds/search":
            q = (qs.get("q") or [""])[0]
            limit = int((qs.get("limit") or ["20"])[0])
            try:
                hits = funds_search(q, limit=limit)
                self._json(200, {"ok": True, "results": hits})
            except Exception as ex:
                self._json(200, {"ok": False, "error": str(ex)})
            return

        if path == "/api/pension/search":
            q = (qs.get("q") or [""])[0]
            limit = int((qs.get("limit") or ["20"])[0])
            try:
                hits = gemelnet_search(q, limit=limit, source="pensia")
                self._json(200, {"ok": True, "results": hits})
            except Exception as ex:
                self._json(200, {"ok": False, "error": str(ex)})
            return

        if path == "/api/tickers/search":
            q = (qs.get("q") or [""])[0]
            limit = int((qs.get("limit") or ["10"])[0])
            try:
                hits = yahoo_search_ticker(q, limit=limit)
                self._json(200, {"ok": True, "results": hits})
            except Exception as ex:
                self._json(200, {"ok": False, "error": str(ex)})
            return

        if path == "/api/sync/status":
            self._json(200, {"ok": True, "status": dict(_sync_status)})
            return

        if path == "/api/chat/status":
            self._json(200, {
                "ok": True,
                "enabled": portfolio_chat.chat_enabled(),
            })
            return

        if path == "/api/insights":
            if not portfolio_chat.insights_enabled():
                self._json(200, {"ok": False, "error": "insights_disabled"})
                return
            refresh = (qs.get("refresh") or ["0"])[0] in ("1", "true", "yes")
            lang = (qs.get("lang") or ["en"])[0].lower()
            if lang not in ("en", "he"):
                lang = "en"
            today = date.today().isoformat()
            # Insights are cached per user per day AND per language, so a
            # language switch serves/generates the right copy without a call on
            # every dashboard load.
            with _cache_lock:
                by_lang = dict(CACHE.get("insights") or {})
                cached = dict(by_lang.get(lang) or {})
            def _all_today(by):
                # Both language copies cached for today, so the client can swap
                # languages instantly without another request.
                return {
                    lg: (e or {}).get("text")
                    for lg, e in by.items()
                    if (e or {}).get("text") and (e or {}).get("date") == today
                }

            if not refresh and cached.get("text") and cached.get("date") == today:
                self._json(200, {
                    "ok": True, "insights": cached["text"],
                    "insights_all": _all_today(by_lang),
                    "generated_at": cached.get("generated_at"), "cached": True,
                })
                return
            try:
                state = compose_state(24, None)
                context = portfolio_chat.build_portfolio_context(state)
                # Generate all languages together (EN generated, HE translated)
                # so both convey identical content, each in its own language.
                texts = portfolio_chat.generate_daily_insights_bilingual(context)
            except Exception as ex:
                if cached.get("text"):
                    self._json(200, {
                        "ok": True, "insights": cached["text"],
                        "insights_all": _all_today(by_lang),
                        "generated_at": cached.get("generated_at"),
                        "cached": True, "stale": True,
                    })
                    return
                self._json(200, {"ok": False, "error": str(ex)})
                return
            gen_at = now_iso()
            with _cache_lock:
                store = CACHE.get("insights")
                # Migrate away from the pre-i18n flat shape ({text,date,...}).
                if not isinstance(store, dict) or "text" in store:
                    store = {}
                for lg, txt in texts.items():
                    store[lg] = {"text": txt, "date": today, "generated_at": gen_at}
                CACHE["insights"] = store
            save_cache()
            text = texts.get(lang) or next(iter(texts.values()))
            self._json(200, {
                "ok": True, "insights": text, "insights_all": dict(texts),
                "generated_at": gen_at, "cached": False,
            })
            return

        if path == "/api/export":
            with _data_lock:
                body = json.dumps(DATA, ensure_ascii=False, indent=2).encode("utf-8")
            self._write(
                200,
                "application/json; charset=utf-8",
                body,
                extra_headers={
                    "Content-Disposition": f'attachment; filename="saving-tracker-data-{date.today().isoformat()}.json"'
                },
            )
            return

        self.send_error(404)

    # ── POST/PATCH/DELETE ───────────────────────────────────────────
    def do_POST(self):
        return self._do_mutating("POST")

    def do_PATCH(self):
        return self._do_mutating("PATCH")

    def do_DELETE(self):
        return self._do_mutating("DELETE")

    def _do_mutating(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body() if method in ("POST", "PATCH", "DELETE") else {}

        if method == "POST" and path == "/api/cron/sync":
            if not self._verify_cron_secret():
                return
            # ?email=0 / false / no disables the new-yield email for this run.
            email_qs = (parse_qs(parsed.query).get("email", ["1"])[0] or "").strip().lower()
            send_email = email_qs not in ("0", "false", "no", "off")
            if not _cron_job_lock.acquire(blocking=False):
                print("cron sync: rejected — job already running")
                self._json(409, {"ok": False, "error": "Cron sync already running"})
                return
            print(f"cron sync: accepted at {now_iso()} (send_email={send_email})")
            _cron_status.update({
                "running": True,
                "started_at": now_iso(),
                "finished_at": None,
                "error": None,
                "results": None,
            })
            threading.Thread(target=_run_cron_job, args=(send_email,), daemon=True).start()
            self._json(202, {"ok": True, "status": "started"})
            return

        if method == "POST" and path == "/api/login":
            username = (body.get("username") or "").strip()
            password = body.get("password") or ""
            user = db.get_user_by_username(username)
            if not user or not auth.verify_password(password, user["password_hash"]):
                self._json(401, {"ok": False, "error": "Invalid username or password"})
                return
            if not user.get("approved"):
                self._json(403, {
                    "ok": False,
                    "error": "Account pending approval. An admin must approve your account before you can sign in.",
                })
                return
            token = auth.create_token(user["id"], user["username"])
            self._json(200, {"ok": True, "token": token, "username": user["username"]})
            return

        if method == "POST" and path == "/api/register":
            username = (body.get("username") or "").strip()
            password = body.get("password") or ""
            err = _validate_username(username)
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            err = _validate_password(password)
            if err:
                self._json(400, {"ok": False, "error": err})
                return
            if db.get_user_by_username(username):
                self._json(409, {"ok": False, "error": "Username already taken"})
                return
            db.create_user(username, auth.hash_password(password), approved=False)
            self._json(200, {
                "ok": True,
                "message": "Account created. An admin must approve your account before you can sign in.",
            })
            return

        user_id = self._require_auth(path)
        if user_id is None:
            return
        if user_id == 0:
            self.send_error(404)
            return

        with _user_ctx_lock:
            _activate_user(user_id)

        try:
            if method == "POST" and path == "/api/chat":
                if not portfolio_chat.chat_enabled():
                    self._json(404, {"ok": False, "error": "chat_disabled"})
                    return
                try:
                    state = compose_state(24, None)
                    result = portfolio_chat.run_chat(
                        state,
                        body.get("messages"),
                        compose_fn=compose_state,
                    )
                except Exception as ex:
                    self._json(500, {"ok": False, "error": str(ex)})
                    return
                if not result.get("ok"):
                    code = 404 if result.get("error") == "chat_disabled" else 400
                    self._json(code, result)
                    return
                self._json(200, result)
                return

            if method == "POST" and path == "/api/sync":
                # Run sync synchronously in a worker thread; the request waits.
                # Simpler than streaming for v1.
                t = threading.Thread(target=run_sync, kwargs={"force": bool(body.get("force"))}, daemon=True)
                t.start()
                t.join(timeout=300)
                if t.is_alive():
                    self._json(200, {"ok": False, "error": "Sync timed out (still running in background)"})
                    return
                qs = parse_qs(parsed.query or "")
                try:
                    horizon = int((qs.get("horizon") or ["24"])[0])
                except ValueError:
                    horizon = 24
                assumed_pct = None
                raw = (qs.get("assumed_annual_pct") or [""])[0]
                if raw:
                    try:
                        assumed_pct = float(raw)
                    except ValueError:
                        assumed_pct = None
                self._json(200, compose_state(horizon, assumed_pct))
                return

            if method == "POST" and path == "/api/fund-holdings":
                self._json(200, add_fund_holding(body))
                return
            if method == "POST" and path.startswith("/api/funds/") and path.endswith("/prepare"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    try:
                        fid = int(parts[2])
                    except ValueError:
                        self._json(400, {"ok": False, "error": "Invalid fund_id"})
                        return
                    source = (body.get("data_source") or "gemelnet").strip()
                    self._json(200, prepare_fund(fid, source=source))
                    return
            if method == "POST" and path.startswith("/api/fund-holdings/") and path.endswith("/spot-check"):
                parts = path.strip("/").split("/")
                # /api/fund-holdings/{hid}/spot-check
                if len(parts) == 4:
                    self._json(200, spot_check_fund(parts[2], body))
                    return
            if method == "PATCH" and path.startswith("/api/fund-holdings/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    self._json(200, update_fund_holding(parts[2], body))
                    return
            if method == "DELETE" and path.startswith("/api/fund-holdings/"):
                # Two shapes: /api/fund-holdings/{id} or /api/fund-holdings/{id}/events/{eid}
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    self._json(200, delete_fund_holding(parts[2]))
                    return
                if len(parts) == 5 and parts[3] == "events":
                    self._json(200, delete_event(parts[2], parts[4]))
                    return

            # Pension (mirrors fund-holdings)
            if method == "POST" and path == "/api/pension-holdings":
                self._json(200, add_pension_holding(body))
                return
            if method == "POST" and path.startswith("/api/pension/") and path.endswith("/prepare"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    try:
                        fid = int(parts[2])
                    except ValueError:
                        self._json(400, {"ok": False, "error": "Invalid fund_id"})
                        return
                    self._json(200, prepare_pension(fid))
                    return
            # Pension recurring rules — same code path as fund rules, since
            # add_rule/update_rule/delete_rule look up the holding in either
            # fund_holdings or pension_holdings.
            if method == "POST" and path.startswith("/api/pension-holdings/") and path.endswith("/rules"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    self._json(200, add_rule(parts[2], body))
                    return
            if method == "PATCH" and "/rules/" in path and path.startswith("/api/pension-holdings/"):
                parts = path.strip("/").split("/")
                if len(parts) == 5 and parts[3] == "rules":
                    self._json(200, update_rule(parts[2], parts[4], body))
                    return
            if method == "DELETE" and "/rules/" in path and path.startswith("/api/pension-holdings/"):
                parts = path.strip("/").split("/")
                if len(parts) == 5 and parts[3] == "rules":
                    self._json(200, delete_rule(parts[2], parts[4]))
                    return
            if method == "POST" and path.startswith("/api/pension-holdings/") and path.endswith("/spot-check"):
                parts = path.strip("/").split("/")
                # /api/pension-holdings/{hid}/spot-check
                if len(parts) == 4:
                    self._json(200, spot_check_pension(parts[2], body))
                    return
            if method == "PATCH" and path.startswith("/api/pension-holdings/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    self._json(200, update_pension_holding(parts[2], body))
                    return
            if method == "DELETE" and path.startswith("/api/pension-holdings/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    self._json(200, delete_pension_holding(parts[2]))
                    return
            if method == "POST" and path.startswith("/api/fund-holdings/") and path.endswith("/events"):
                hid = path.split("/")[3]
                self._json(200, add_event(hid, body))
                return

            # Recurring rules
            if method == "POST" and path.startswith("/api/fund-holdings/") and path.endswith("/rules"):
                hid = path.split("/")[3]
                self._json(200, add_rule(hid, body))
                return
            if method == "PATCH" and "/rules/" in path:
                parts = path.strip("/").split("/")
                # /api/fund-holdings/{hid}/rules/{rid}
                if len(parts) == 5 and parts[3] == "rules":
                    self._json(200, update_rule(parts[2], parts[4], body))
                    return
            if method == "DELETE" and "/rules/" in path:
                parts = path.strip("/").split("/")
                if len(parts) == 5 and parts[3] == "rules":
                    self._json(200, delete_rule(parts[2], parts[4]))
                    return

            if method == "POST" and path == "/api/rsu-grants":
                self._json(200, add_rsu_grant(body))
                return
            if method == "PATCH" and path.startswith("/api/rsu-grants/"):
                gid = path.rsplit("/", 1)[-1]
                self._json(200, update_rsu_grant(gid, body))
                return
            if method == "POST" and path.startswith("/api/rsu-grants/") and path.endswith("/sales"):
                gid = path.split("/")[3]
                self._json(200, add_rsu_sale(gid, body))
                return
            if method == "DELETE" and path.startswith("/api/rsu-grants/") and "/sales/" in path:
                parts = path.strip("/").split("/")
                if len(parts) == 5 and parts[3] == "sales":
                    self._json(200, delete_rsu_sale(parts[2], parts[4]))
                    return
            if method == "DELETE" and path.startswith("/api/rsu-grants/"):
                gid = path.rsplit("/", 1)[-1]
                self._json(200, delete_rsu_grant(gid))
                return

            # ESPP plans
            if method == "POST" and path == "/api/espp-plans":
                self._json(200, add_espp_plan(body))
                return
            if method == "PATCH" and path.startswith("/api/espp-plans/") and "/" not in path[len("/api/espp-plans/"):]:
                pid = path.rsplit("/", 1)[-1]
                self._json(200, update_espp_plan(pid, body))
                return
            if method == "POST" and path.startswith("/api/espp-plans/") and path.endswith("/purchases"):
                pid = path.split("/")[3]
                self._json(200, add_espp_purchase(pid, body))
                return
            if method == "DELETE" and path.startswith("/api/espp-plans/") and "/purchases/" in path:
                parts = path.strip("/").split("/")
                if len(parts) == 5 and parts[3] == "purchases":
                    self._json(200, delete_espp_purchase(parts[2], parts[4]))
                    return
            if method == "POST" and path.startswith("/api/espp-plans/") and path.endswith("/sales"):
                pid = path.split("/")[3]
                self._json(200, add_espp_sale(pid, body))
                return
            if method == "DELETE" and path.startswith("/api/espp-plans/") and "/sales/" in path:
                parts = path.strip("/").split("/")
                if len(parts) == 5 and parts[3] == "sales":
                    self._json(200, delete_espp_sale(parts[2], parts[4]))
                    return
            if method == "DELETE" and path.startswith("/api/espp-plans/"):
                pid = path.rsplit("/", 1)[-1]
                self._json(200, delete_espp_plan(pid))
                return

            if method == "POST" and path == "/api/settings":
                self._json(200, update_settings(body))
                return

            if method == "POST" and path == "/api/cash":
                self._json(200, add_cash_holding(body))
                return
            if method == "PATCH" and path.startswith("/api/cash/"):
                cid = path.rsplit("/", 1)[-1]
                self._json(200, update_cash_holding(cid, body))
                return
            if method == "DELETE" and path.startswith("/api/cash/"):
                cid = path.rsplit("/", 1)[-1]
                self._json(200, delete_cash_holding(cid))
                return

            if method == "POST" and path == "/api/import":
                self._json(200, import_data(body))
                return

            if method == "POST" and path == "/api/cache/clear":
                # Market data is now shared across all users; clearing it forces
                # a fresh refetch for everyone on the next sync.
                global MARKET
                with _market_lock:
                    MARKET = default_market()
                    save_market()
                self._json(200, {
                    "ok": True,
                    "shared": True,
                    "message": "Shared market cache cleared for all users; data refetches on next sync.",
                })
                return

            if method == "DELETE" and path == "/api/account":
                password = body.get("password") or ""
                if not password:
                    self._json(400, {"ok": False, "error": "Password is required"})
                    return
                self._json(200, delete_account(user_id, password))
                return

            if method == "POST" and path == "/api/account/password":
                current = body.get("current_password") or ""
                new_pw = body.get("new_password") or ""
                if not current or not new_pw:
                    self._json(400, {"ok": False, "error": "Current and new password are required"})
                    return
                self._json(200, change_password(user_id, current, new_pw))
                return

            self.send_error(404)
        except Exception as ex:
            self._json(500, {"ok": False, "error": str(ex)})


def main():
    bootstrap_storage()
    port = int(os.environ.get("PORT", "8000"))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("=" * 60)
    print("Saving Tracker (cloud)")
    print("=" * 60)
    print(f"  Server:     http://0.0.0.0:{port}/")
    print(f"  User ID:    {ACTIVE_USER_ID}")
    print(f"  CORS:       {CORS_ORIGIN or '(not set)'}")
    print(f"  PID:        {os.getpid()}")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()



if __name__ == "__main__":
    main()
