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
    print("ok")
