"""Unit tests for TASE mutual fund (Bank Investment) valuation helpers."""
from __future__ import annotations

import saving_tracker as st


def _seed_monthly_nav(fund_id: str, closes_by_ym: dict):
    """Build daily rows with one close per month (on the 28th)."""
    rows = []
    for ym in sorted(closes_by_ym.keys()):
        rows.append({"date": f"{ym}-28", "close": closes_by_ym[ym]})
    st.MARKET["tase_fund_daily"] = {
        fund_id: {"rows": rows, "last_synced": "2026-07-31T00:00:00"}
    }


def test_normalize_tase_fund_id_strips_leading_zeros():
    assert st._normalize_tase_fund_id("05123898") == "5123898"
    assert st._normalize_tase_fund_id(5123898) == "5123898"


def test_agorot_to_ils():
    assert st._agorot_to_ils(1189.82) == 11.8982
    assert st._agorot_to_ils(None) is None


def test_parse_maya_history_rows_prefers_sell_price():
    rows = st._parse_maya_history_rows([
        {
            "tradeDate": "2026-07-31T00:00:00",
            "purchasePrice": 1200.0,
            "sellPrice": 1189.82,
        },
        {
            "tradeDate": "2026-07-30T00:00:00",
            "purchasePrice": 1188.0,
            "sellPrice": None,
        },
    ])
    assert rows[0]["date"] == "2026-07-30"
    assert rows[0]["close"] == 11.88
    assert rows[1]["date"] == "2026-07-31"
    assert rows[1]["close"] == 11.8982


def test_value_tase_fund_uses_latest_nav(monkeypatch=None):
    holding = {"fund_id": "5123898", "units": 1000}
    st.MARKET["tase_fund_daily"] = {
        "5123898": {
            "rows": [
                {"date": "2026-07-30", "close": 11.88},
                {"date": "2026-07-31", "close": 11.8982},
            ]
        }
    }
    computed = st.value_tase_fund(holding)
    assert computed["unit_price_ils"] == 11.8982
    assert computed["price_date"] == "2026-07-31"
    assert computed["value_ils"] == 11898.2
    assert computed["has_price"] is True


def test_tase_monthly_returns_from_daily_rows():
    _seed_monthly_nav("5123898", {
        "2026-01": 10.0,
        "2026-02": 10.5,
        "2026-03": 10.0,
    })
    returns = st._tase_monthly_returns("5123898")
    assert len(returns) == 2
    assert abs(returns[0] - 0.05) < 1e-9
    assert abs(returns[1] - (-0.5 / 10.5)) < 1e-9


def test_project_tase_fund_requires_six_months():
    closes = {f"2026-{m:02d}": 10.0 + m * 0.1 for m in range(1, 6)}  # 5 months → 4 returns
    _seed_monthly_nav("5123898", closes)
    holding = {"fund_id": "5123898", "units": 100}
    computed = st.value_tase_fund(holding)
    assert st.project_tase_fund(holding, computed, 12) is None

    closes = {f"2025-{m:02d}": 10.0 + m * 0.05 for m in range(1, 8)}  # 7 months → 6 returns
    _seed_monthly_nav("5123898", closes)
    computed = st.value_tase_fund(holding)
    proj = st.project_tase_fund(holding, computed, 6)
    assert proj is not None
    assert proj["n_samples"] == 6
    assert len(proj["paths"]["mean"]) == 6
    assert proj["annual_pct"] is not None


def test_compose_portfolio_includes_tase_flat():
    tase = [{
        "id": "t1",
        "fund_id": "5123898",
        "units": 100,
        "archived": False,
        "included_in_dashboard": True,
        "created_at": "2026-01-15T00:00:00",
        "computed": {"value_ils": 1189.82, "unit_price_ils": 11.8982},
        "nav_history": [
            {"date": "2026-01-15", "close": 11.5},
            {"date": "2026-02-15", "close": 11.7},
        ],
    }]
    port = st.compose_portfolio([], [], 3, None, [], [], tase)
    assert port["tase_funds_value_ils"] == 1189.82
    assert port["total_value_ils"] == 1189.82
    assert port["cash_value_ils"] == 0
    # Historical series should carry tase_ils
    assert any((pt.get("tase_ils") or 0) > 0 for pt in port["time_series_ils"])


def test_what_if_holds_tase_flat_not_compounded():
    """assumed_annual_pct compounds funds only; tase stays in deterministic flat add-on."""
    closes = {f"2025-{m:02d}": 10.0 for m in range(1, 8)}
    _seed_monthly_nav("5123898", closes)
    holding = {
        "id": "t1",
        "fund_id": "5123898",
        "units": 100,
        "archived": False,
        "computed": {"value_ils": 1000.0, "current_value_ils": 1000.0},
        "projection": None,
        "nav_history": [{"date": f"{ym}-28", "close": 10.0} for ym in sorted(closes.keys())],
    }
    # Attach a real projection so historical cone grows, but what-if must stay flat for tase.
    holding["projection"] = st.project_tase_fund(
        holding, holding["computed"], 6
    )
    port = st.compose_portfolio([], [], 6, 12.0, [], [], [holding])
    wf = port["what_if"]
    assert wf is not None
    # With zero funds, what-if path = flat tase each month (deterministic add-on).
    assert wf["paths"][0] == 1000.0
    assert wf["paths"][-1] == 1000.0
    # Historical projection may still grow (or stay flat if 0% returns).
    proj = port["projection"]
    assert proj is not None
    assert proj["paths"]["tase_mean"][0] is not None


def test_compose_portfolio_projection_sums_tase_paths():
    closes = {f"2025-{m:02d}": 10.0 + m * 0.1 for m in range(1, 8)}
    _seed_monthly_nav("5123898", closes)
    holding = {
        "id": "t1",
        "fund_id": "5123898",
        "units": 100,
        "archived": False,
        "computed": {"value_ils": 1070.0, "current_value_ils": 1070.0},
    }
    holding["projection"] = st.project_tase_fund(holding, holding["computed"], 4)
    assert holding["projection"] is not None
    proj = st.compose_portfolio_projection([], [], 4, [], 0.0, [holding])
    assert proj["paths"]["tase_mean"] == holding["projection"]["paths"]["mean"]
    assert proj["paths"]["mean"] == holding["projection"]["paths"]["mean"]


def test_tase_units_on_date_from_events():
    holding = {
        "units": 0,
        "events": [
            {"id": "1", "date": "2026-01-10", "kind": "buy", "units": 100},
            {"id": "2", "date": "2026-03-05", "kind": "sell", "units": 40},
            {"id": "3", "date": "2026-04-01", "kind": "correction", "units": 80},
        ],
    }
    assert st._tase_units_on_date(holding, "2025-12-31") == 0
    assert st._tase_units_on_date(holding, "2026-01-31") == 100
    assert st._tase_units_on_date(holding, "2026-03-31") == 60
    assert st._tase_units_on_date(holding, "2026-04-30") == 80


def test_value_tase_fund_time_series_respects_events():
    closes = {
        "2026-01": 10.0,
        "2026-02": 10.0,
        "2026-03": 10.0,
        "2026-04": 10.0,
    }
    _seed_monthly_nav("5123898", closes)
    holding = {
        "fund_id": "5123898",
        "units": 80,
        "events": [
            {"id": "1", "date": "2026-01-15", "kind": "buy", "units": 100},
            {"id": "2", "date": "2026-03-10", "kind": "sell", "units": 20},
        ],
    }
    computed = st.value_tase_fund(holding)
    by_period = {p["period"]: p for p in computed["time_series"]}
    assert by_period[202601]["units"] == 100
    assert by_period[202601]["value_ils"] == 1000.0
    assert by_period[202602]["units"] == 100
    assert by_period[202603]["units"] == 80
    assert by_period[202604]["units"] == 80


def test_add_tase_fund_event_updates_units():
    st.DATA["tase_fund_holdings"] = [{
        "id": "t1",
        "fund_id": "5123898",
        "units": 100,
        "events": [
            {"id": "init", "date": "2026-01-01", "kind": "buy", "units": 100, "note": "", "source": "initial"},
        ],
        "archived": False,
    }]
    # Monkeypatch save_data to no-op
    orig = st.save_data
    st.save_data = lambda: None
    try:
        r = st.add_tase_fund_event("t1", {"date": "2026-06-01", "kind": "buy", "units": 50})
        assert r["ok"] is True
        h = st.DATA["tase_fund_holdings"][0]
        assert h["units"] == 150
        assert len(h["events"]) == 2
        bad = st.add_tase_fund_event("t1", {"date": "2026-06-02", "kind": "sell", "units": 999})
        assert bad["ok"] is False
    finally:
        st.save_data = orig


def test_tase_fifo_pnl_buy_then_price_rise():
    st.MARKET["tase_fund_daily"] = {
        "5123898": {
            "rows": [
                {"date": "2026-01-15", "close": 10.0},
                {"date": "2026-07-31", "close": 11.0},
            ]
        }
    }
    holding = {
        "fund_id": "5123898",
        "units": 100,
        "events": [{"id": "1", "date": "2026-01-15", "kind": "buy", "units": 100}],
    }
    c = st.value_tase_fund(holding)
    assert c["value_ils"] == 1100.0
    assert c["cost_basis_ils"] == 1000.0
    assert c["realized_gain_ils"] == 0.0
    assert c["profit_ils"] == 100.0
    assert abs(c["profit_pct"] - 0.1) < 1e-9


def test_tase_fifo_pnl_partial_sell_and_remainder():
    st.MARKET["tase_fund_daily"] = {
        "5123898": {
            "rows": [
                {"date": "2026-01-10", "close": 10.0},
                {"date": "2026-03-10", "close": 12.0},
                {"date": "2026-07-31", "close": 15.0},
            ]
        }
    }
    holding = {
        "fund_id": "5123898",
        "units": 60,
        "events": [
            {"id": "1", "date": "2026-01-10", "kind": "buy", "units": 100},
            {"id": "2", "date": "2026-03-10", "kind": "sell", "units": 40},
        ],
    }
    c = st.value_tase_fund(holding)
    # realized 40*(12-10)=80; remaining cost 60*10=600; value 60*15=900; unrealized 300
    assert c["realized_gain_ils"] == 80.0
    assert c["cost_basis_ils"] == 600.0
    assert c["value_ils"] == 900.0
    assert c["profit_ils"] == 380.0
    assert abs(c["profit_pct"] - (380.0 / 1000.0)) < 1e-9


def test_tase_fifo_pnl_correction_up_and_down():
    st.MARKET["tase_fund_daily"] = {
        "5123898": {
            "rows": [
                {"date": "2026-01-10", "close": 10.0},
                {"date": "2026-02-10", "close": 11.0},
                {"date": "2026-03-10", "close": 12.0},
                {"date": "2026-07-31", "close": 12.0},
            ]
        }
    }
    holding = {
        "fund_id": "5123898",
        "units": 80,
        "events": [
            {"id": "1", "date": "2026-01-10", "kind": "buy", "units": 100},
            {"id": "2", "date": "2026-02-10", "kind": "correction", "units": 120},  # +20 @ 11
            {"id": "3", "date": "2026-03-10", "kind": "correction", "units": 80},   # -40 FIFO
        ],
    }
    c = st.value_tase_fund(holding)
    # After buy 100@10: cost 1000
    # Correction up +20@11: gross 1000+220=1220, lots=[100@10, 20@11]
    # Correction down 40: consume 40@10 → realized (12-10)*40=80; remain 60@10 + 20@11 = 820
    assert c["cost_basis_ils"] == 820.0
    assert c["realized_gain_ils"] == 80.0
    assert c["value_ils"] == 960.0  # 80*12
    assert c["profit_ils"] == round(960.0 - 820.0 + 80.0, 2)


def test_tase_fifo_pnl_weekend_uses_prior_close():
    st.MARKET["tase_fund_daily"] = {
        "5123898": {
            "rows": [
                {"date": "2026-01-09", "close": 10.0},  # Friday
                {"date": "2026-01-12", "close": 10.5},  # Monday
                {"date": "2026-07-31", "close": 11.0},
            ]
        }
    }
    holding = {
        "fund_id": "5123898",
        "units": 100,
        # Saturday — should price at Friday 10.0
        "events": [{"id": "1", "date": "2026-01-10", "kind": "buy", "units": 100}],
    }
    c = st.value_tase_fund(holding)
    assert c["cost_basis_ils"] == 1000.0
    assert c["profit_ils"] == 100.0


def test_tase_fifo_pnl_null_without_nav_or_events():
    st.MARKET["tase_fund_daily"] = {
        "5123898": {"rows": [{"date": "2026-07-31", "close": 11.0}]}
    }
    no_events = st.value_tase_fund({"fund_id": "5123898", "units": 100, "events": []})
    assert no_events["value_ils"] == 1100.0
    assert no_events["profit_ils"] is None
    assert no_events["cost_basis_ils"] is None

    early_buy = st.value_tase_fund({
        "fund_id": "5123898",
        "units": 100,
        "events": [{"id": "1", "date": "2025-01-01", "kind": "buy", "units": 100}],
    })
    assert early_buy["profit_ils"] is None


def test_compose_portfolio_includes_tase_profit_and_invested():
    tase = [{
        "id": "t1",
        "fund_id": "5123898",
        "units": 100,
        "archived": False,
        "included_in_dashboard": True,
        "created_at": "2026-01-15T00:00:00",
        "computed": {
            "value_ils": 1100.0,
            "cost_basis_ils": 1000.0,
            "profit_ils": 100.0,
        },
        "nav_history": [],
    }]
    port = st.compose_portfolio([], [], 3, None, [], [], tase)
    assert port["tase_funds_value_ils"] == 1100.0
    assert port["tase_funds_profit_ils"] == 100.0
    assert port["total_invested_ils"] == 1000.0
    assert port["total_profit_ils"] == 100.0


def test_cashout_tax_uses_tase_unrealized():
    tase = [{
        "id": "t1",
        "fund_id": "5123898",
        "nickname": "כספית",
        "archived": False,
        "included_in_dashboard": True,
        "computed": {
            "value_ils": 1100.0,
            "cost_basis_ils": 1000.0,
            "profit_ils": 100.0,
        },
    }]
    est = st.compute_cashout_tax_estimate([], [], [], [], [], tase)
    assert est["taxable_profit_ils"] == 100.0
    assert est["estimated_tax_ils"] == 25.0
    line = next(x for x in est["by_holding"] if x["kind"] == "tase_fund")
    assert line["taxable_profit_ils"] == 100.0
    assert line["rate"] == 0.25


if __name__ == "__main__":
    test_normalize_tase_fund_id_strips_leading_zeros()
    test_agorot_to_ils()
    test_parse_maya_history_rows_prefers_sell_price()
    test_value_tase_fund_uses_latest_nav()
    test_tase_monthly_returns_from_daily_rows()
    test_project_tase_fund_requires_six_months()
    test_compose_portfolio_includes_tase_flat()
    test_what_if_holds_tase_flat_not_compounded()
    test_compose_portfolio_projection_sums_tase_paths()
    test_tase_units_on_date_from_events()
    test_value_tase_fund_time_series_respects_events()
    test_add_tase_fund_event_updates_units()
    test_tase_fifo_pnl_buy_then_price_rise()
    test_tase_fifo_pnl_partial_sell_and_remainder()
    test_tase_fifo_pnl_correction_up_and_down()
    test_tase_fifo_pnl_weekend_uses_prior_close()
    test_tase_fifo_pnl_null_without_nav_or_events()
    test_compose_portfolio_includes_tase_profit_and_invested()
    test_cashout_tax_uses_tase_unrealized()
    print("ok")
