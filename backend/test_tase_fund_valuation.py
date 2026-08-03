"""Unit tests for TASE mutual fund (Bank Investment) valuation helpers."""
from __future__ import annotations

import saving_tracker as st


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


if __name__ == "__main__":
    test_normalize_tase_fund_id_strips_leading_zeros()
    test_agorot_to_ils()
    test_parse_maya_history_rows_prefers_sell_price()
    test_value_tase_fund_uses_latest_nav()
    test_compose_portfolio_includes_tase_flat()
    print("ok")
