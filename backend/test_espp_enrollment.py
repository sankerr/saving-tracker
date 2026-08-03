"""Unit tests for ESPP enrolment helpers (months, FX, lookback, settle)."""
from __future__ import annotations

from datetime import date
from unittest import mock

import saving_tracker as st


def _seed_stock(ticker: str, closes_by_date: dict):
    rows = [{"date": d, "close": closes_by_date[d]} for d in sorted(closes_by_date)]
    st.MARKET["stock_daily"] = {
        ticker: {"rows": rows, "last_synced": "2026-07-31T00:00:00"}
    }


def _seed_fx(closes_by_date: dict):
    rows = [{"date": d, "close": closes_by_date[d]} for d in sorted(closes_by_date)]
    st.MARKET["fx"] = {
        "USDILS": {"rows": rows, "last_synced": "2026-07-31T00:00:00"}
    }


def _plan(**kwargs):
    base = {
        "id": "plan-1",
        "ticker": "NVDA",
        "discount_pct": 15.0,
        "has_lookback": True,
        "offering_months": 6,
        "purchases": [],
        "sales": [],
        "enrollments": [],
    }
    base.update(kwargs)
    return base


def _freeze_today(today_d: date):
    """Patch saving_tracker.date so .today() is fixed; constructors still work."""
    real = date

    class _Date(real):
        @classmethod
        def today(cls):
            return today_d

    return mock.patch("saving_tracker.date", _Date)


def test_contribution_months_jan_through_jun():
    dates = st._espp_contribution_dates(date(2026, 1, 1), date(2026, 6, 30))
    assert len(dates) == 6
    assert dates[0] == date(2026, 1, 1)
    assert dates[-1] == date(2026, 6, 1)


def test_contribution_months_clamps_dom():
    dates = st._espp_contribution_dates(date(2026, 1, 31), date(2026, 3, 31))
    assert dates == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]


def test_close_on_or_before_walks_back():
    rows = [
        {"date": "2026-01-02", "close": 100},
        {"date": "2026-01-05", "close": 110},
    ]
    d, c = st._close_on_or_before(rows, date(2026, 1, 4))
    assert d == "2026-01-02"
    assert c == 100


def test_enrollment_breakdown_monthly_fx_and_lookback():
    # Include prior trading day so period_start (New Year) resolves via walk-back.
    _seed_stock("NVDA", {
        "2025-12-31": 100.0,
        "2026-03-31": 120.0,
        "2026-04-01": 121.0,
    })
    _seed_fx({
        "2025-12-31": 3.5,
        "2026-01-01": 3.5,
        "2026-02-01": 3.5,
        "2026-03-01": 3.5,
    })
    plan = _plan()
    enrollment = {
        "id": "e1",
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "monthly_contribution_ils": 3500.0,
        "sell_immediately": True,
        "note": "",
    }
    br = st._espp_enrollment_breakdown(
        plan, enrollment, as_of=date(2026, 2, 15), settle=False
    )
    assert br["months_total"] == 3
    assert br["months_paid"] == 2
    assert br["contribution_ils"] == 7000.0
    assert abs(br["contribution_usd"] - 2000.0) < 1e-6
    assert br["is_estimate"] is True
    assert br["period_start_price_usd"] == 100.0
    assert br["period_end_price_usd"] == 121.0
    assert abs(br["purchase_price_usd"] - 85.0) < 1e-6
    assert abs(br["shares"] - (2000.0 / 85.0)) < 1e-3


def test_enrollment_breakdown_settle_uses_period_end_close():
    _seed_stock("NVDA", {
        "2025-12-31": 100.0,
        "2026-03-31": 120.0,
        "2026-04-01": 130.0,
    })
    _seed_fx({
        "2025-12-31": 3.5,
        "2026-01-01": 3.5,
        "2026-02-01": 3.5,
        "2026-03-01": 3.5,
    })
    plan = _plan()
    enrollment = {
        "id": "e1",
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "monthly_contribution_ils": 3500.0,
    }
    br = st._espp_enrollment_breakdown(
        plan, enrollment, as_of=date(2026, 3, 31), settle=True
    )
    assert br["months_paid"] == 3
    assert br["is_estimate"] is False
    assert br["period_end_price_usd"] == 120.0
    assert abs(br["contribution_usd"] - 3000.0) < 1e-6
    assert abs(br["shares"] - (3000.0 / 85.0)) < 1e-3


def test_enrollment_breakdown_missing_fx_raises():
    _seed_stock("NVDA", {"2025-12-31": 100.0, "2026-06-30": 110.0})
    _seed_fx({})
    plan = _plan()
    enrollment = {
        "id": "e1",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "monthly_contribution_ils": 1000.0,
    }
    try:
        st._espp_enrollment_breakdown(plan, enrollment, as_of=date(2026, 6, 30), settle=True)
        assert False, "expected ValueError"
    except ValueError as ex:
        assert "missing FX" in str(ex)


def test_settle_creates_purchase_and_auto_sale():
    _seed_stock("NVDA", {
        "2025-12-31": 100.0,
        "2026-06-30": 120.0,
    })
    _seed_fx({
        "2025-12-31": 3.5,
        "2026-01-01": 3.5,
        "2026-02-01": 3.5,
        "2026-03-01": 3.5,
        "2026-04-01": 3.5,
        "2026-05-01": 3.5,
        "2026-06-01": 3.5,
    })
    enrollment = {
        "id": "e1",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "monthly_contribution_ils": 3500.0,
        "sell_immediately": True,
        "note": "test",
        "settled_purchase_id": None,
    }
    plan = _plan(enrollments=[enrollment])
    with _freeze_today(date(2026, 7, 1)):
        result = st._settle_espp_enrollment(plan, enrollment, fetch=False)
    assert result["ok"] is True
    assert enrollment["settled_purchase_id"]
    assert len(plan["purchases"]) == 1
    assert len(plan["sales"]) == 1
    assert plan["sales"][0]["purchase_id"] == plan["purchases"][0]["id"]


def test_value_espp_pending_contributions_not_fmv():
    _seed_stock("NVDA", {
        "2025-12-31": 100.0,
        "2026-04-15": 200.0,
    })
    _seed_fx({
        "2025-12-31": 3.5,
        "2026-01-01": 3.5,
        "2026-02-01": 3.5,
        "2026-03-01": 3.5,
        "2026-04-01": 3.5,
        "2026-04-15": 3.5,
    })
    st.DATA["settings"] = {"usdils_rate_override": None, "yield_is_net_of_fees": True}
    enrollment = {
        "id": "e1",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "monthly_contribution_ils": 3500.0,
        "sell_immediately": True,
        "note": "",
        "settled_purchase_id": None,
    }
    plan = _plan(enrollments=[enrollment])
    with _freeze_today(date(2026, 4, 15)):
        computed = st.value_espp(plan)
    assert computed["pending_contribution_ils"] == 14000.0
    assert computed["current_value_ils"] == 14000.0
    assert computed["enrollments"]
    en = computed["enrollments"][0]
    assert en["estimated_fmv_usd"] is not None
    assert en["estimated_fmv_usd"] != computed["current_value_usd"]


def test_settled_enrollment_excluded_from_pending():
    _seed_stock("NVDA", {
        "2025-12-31": 100.0,
        "2026-06-30": 120.0,
        "2026-07-01": 121.0,
    })
    _seed_fx({
        "2025-12-31": 3.5,
        "2026-01-01": 3.5, "2026-02-01": 3.5, "2026-03-01": 3.5,
        "2026-04-01": 3.5, "2026-05-01": 3.5, "2026-06-01": 3.5, "2026-07-01": 3.5,
    })
    st.DATA["settings"] = {"usdils_rate_override": None, "yield_is_net_of_fees": True}
    enrollment = {
        "id": "e1",
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "monthly_contribution_ils": 3500.0,
        "sell_immediately": True,
        "settled_purchase_id": "p1",
    }
    purchase = {
        "id": "p1",
        "date": "2026-06-30",
        "contribution_usd": 6000.0,
        "period_start_price_usd": 100.0,
        "period_end_price_usd": 120.0,
        "purchase_price_usd": 85.0,
        "shares": 70.5882,
        "enrollment_id": "e1",
        "note": "",
    }
    sale = {
        "id": "s1",
        "date": "2026-06-30",
        "shares_sold": 70.5882,
        "sale_price_usd": 120.0,
        "purchase_id": "p1",
        "note": "auto",
    }
    plan = _plan(enrollments=[enrollment], purchases=[purchase], sales=[sale])
    with _freeze_today(date(2026, 7, 1)):
        computed = st.value_espp(plan)
    assert computed["pending_contribution_ils"] == 0
    assert computed["enrollments"] == []
    assert computed["shares_held_now"] == 0
