"""Unit tests: stock-holding currency normalization and FIFO cost-basis math."""
from __future__ import annotations

import saving_tracker as st


def test_normalize_native_to_ils_ils_passthrough():
    assert st.normalize_native_to_ils(100.0, "ILS", 3.65) == 100.0


def test_normalize_native_to_ils_ila_agorot_divides_by_100():
    # TASE tickers are quoted by Yahoo in agorot (1/100 ILS) — must divide,
    # not multiply by FX (FX is irrelevant for an ILS-native price).
    assert st.normalize_native_to_ils(1250.0, "ILA", 3.65) == 12.5


def test_normalize_native_to_ils_usd_multiplies_by_fx():
    assert st.normalize_native_to_ils(100.0, "USD", 3.65) == 365.0


def test_normalize_native_to_ils_none_price_passthrough():
    assert st.normalize_native_to_ils(None, "USD", 3.65) is None


def test_normalize_native_to_ils_usd_missing_fx_returns_none():
    assert st.normalize_native_to_ils(100.0, "USD", None) is None


def _reset_market_and_data():
    st.DATA = st.default_data()
    st.MARKET = st.default_market()


def _set_stock_market(ticker, currency, rows):
    st.MARKET.setdefault("stock_daily", {})[ticker] = {"currency": currency, "rows": rows}


def _set_fx_market(rows):
    st.MARKET.setdefault("fx", {})["USDILS"] = {"rows": rows}


def test_value_stock_usa_ticker_fifo_and_currency():
    _reset_market_and_data()
    _set_stock_market("AAPL", "USD", [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-06-01", "close": 150.0},
    ])
    _set_fx_market([
        {"date": "2026-01-01", "close": 3.60},
        {"date": "2026-06-01", "close": 3.70},
    ])
    holding = {
        "ticker": "AAPL",
        "purchases": [
            {"date": "2026-01-01", "shares": 10, "price": 100.0},
            {"date": "2026-02-01", "shares": 5, "price": 120.0},
        ],
        "sales": [
            {"date": "2026-03-01", "shares_sold": 4, "price": 130.0},
        ],
        "manual_price_override": None,
    }
    c = st.value_stock(holding)

    assert c["no_data"] is False
    assert c["native_currency"] == "USD"
    # Real-world native price is the raw Yahoo close unchanged for USD tickers.
    assert c["current_price_native"] == 150.0
    assert c["current_value_native"] == 11 * 150.0  # 15 acquired - 4 sold = 11 held
    assert c["current_value_ils"] == round(11 * 150.0 * 3.70, 2)
    # native_per_ils_rate ~= 1/3.70 (native units per 1 ILS)
    assert abs(c["native_per_ils_rate"] - (1.0 / 3.70)) < 1e-6

    # FIFO: the sale of 4 shares consumes 4 of the 10 lot-1 (@100) shares.
    # Remaining lots: 6 @100 + 5 @120 -> cost basis for 11 held shares.
    assert c["shares_held_now"] == 11.0
    expected_cost_basis_native = 6 * 100.0 + 5 * 120.0
    assert c["cost_basis_total_native"] == expected_cost_basis_native
    assert c["realized_proceeds_native"] == 4 * 130.0
    # Realized gain = proceeds - FIFO cost of the 4 sold shares (@100 lot).
    assert c["realized_gain_native"] == round(4 * 130.0 - 4 * 100.0, 2)


def test_value_stock_tase_ticker_agorot_normalization():
    _reset_market_and_data()
    # Yahoo quotes TASE tickers in ILA (agorot) — 1250 agorot == 12.50 ILS.
    _set_stock_market("TEVA.TA", "ILA", [
        {"date": "2026-01-01", "close": 1000.0},   # 10.00 ILS
        {"date": "2026-06-01", "close": 1250.0},    # 12.50 ILS
    ])
    holding = {
        "ticker": "TEVA.TA",
        "purchases": [
            {"date": "2026-01-01", "shares": 100, "price": 10.0},  # entered in real ILS
        ],
        "sales": [],
        "manual_price_override": None,
    }
    c = st.value_stock(holding)

    assert c["no_data"] is False
    # The bug this guards against: native_currency must be the real-world
    # label ("ILS"), never the raw Yahoo tag ("ILA") — the frontend's ILS/USD
    # formatting and agorot-detection both key off this field.
    assert c["native_currency"] == "ILS"
    # current_price_native must already be divided by 100 (real ILS, not
    # agorot) so it's directly comparable to cost_basis_per_share_native.
    assert c["current_price_native"] == 12.5
    assert c["current_value_native"] == 100 * 12.5
    # For an ILS-native holding, ILS value == native value (no FX applied).
    assert c["current_value_ils"] == c["current_value_native"]
    assert c["cost_basis_per_share_native"] == 10.0
    assert c["unrealized_gain_native"] == round((12.5 - 10.0) * 100, 2)
    assert abs(c["native_per_ils_rate"] - 1.0) < 1e-9

    # Daily time series values must also be in real ILS, not raw agorot.
    last_point = c["time_series"][-1]
    assert last_point["close_native"] == 12.5
    assert last_point["value_native"] == 100 * 12.5


def test_value_stock_tase_manual_override_is_real_ils_not_agorot():
    _reset_market_and_data()
    _set_stock_market("ICL.TA", "ILA", [{"date": "2026-01-01", "close": 500.0}])
    holding = {
        "ticker": "ICL.TA",
        "purchases": [{"date": "2026-01-01", "shares": 50, "price": 5.0}],
        "sales": [],
        "manual_price_override": 6.0,  # entered in real ILS, per the UI contract
    }
    c = st.value_stock(holding)
    assert c["current_price_native"] == 6.0
    assert c["current_value_native"] == 50 * 6.0
    assert c["current_value_ils"] == 50 * 6.0


def test_value_stock_usd_manual_override_converts_to_ils_via_fx():
    _reset_market_and_data()
    _set_stock_market("AAPL", "USD", [{"date": "2026-01-01", "close": 100.0}])
    _set_fx_market([{"date": "2026-01-01", "close": 3.7}])
    holding = {
        "ticker": "AAPL",
        "purchases": [{"date": "2026-01-01", "shares": 10, "price": 90.0}],
        "sales": [],
        "manual_price_override": 200.0,
    }
    c = st.value_stock(holding)
    assert c["current_price_native"] == 200.0
    assert c["current_value_native"] == 10 * 200.0
    # Regression guard: before the fix, a USD override's ILS value was set
    # equal to the raw override (identity), skipping the FX multiply.
    assert c["current_value_ils"] == round(10 * 200.0 * 3.7, 2)


def test_value_stock_no_purchases_returns_no_data():
    _reset_market_and_data()
    _set_stock_market("AAPL", "USD", [{"date": "2026-01-01", "close": 100.0}])
    holding = {"ticker": "AAPL", "purchases": [], "sales": [], "manual_price_override": None}
    c = st.value_stock(holding)
    assert c["no_data"] is True
    assert c["current_value_ils"] == 0


def test_add_stock_sale_rejects_overselling():
    _reset_market_and_data()
    holding = {
        "id": "h1",
        "ticker": "AAPL",
        "purchases": [{"id": "p1", "date": "2026-01-01", "shares": 10, "price": 100.0}],
        "sales": [],
        "manual_price_override": None,
        "archived": False,
    }
    st.DATA.setdefault("stock_holdings", []).append(holding)

    ok = st.add_stock_sale("h1", {"date": "2026-02-01", "shares_sold": 5, "price": 110.0})
    assert ok["ok"] is True

    # Only 5 shares remain (10 - 5 sold) — selling 6 more must be rejected.
    rejected = st.add_stock_sale("h1", {"date": "2026-03-01", "shares_sold": 6, "price": 120.0})
    assert rejected["ok"] is False
    assert "only" in rejected["error"].lower()

    # Selling exactly the remaining 5 is fine.
    ok2 = st.add_stock_sale("h1", {"date": "2026-03-01", "shares_sold": 5, "price": 120.0})
    assert ok2["ok"] is True


if __name__ == "__main__":
    test_normalize_native_to_ils_ils_passthrough()
    test_normalize_native_to_ils_ila_agorot_divides_by_100()
    test_normalize_native_to_ils_usd_multiplies_by_fx()
    test_normalize_native_to_ils_none_price_passthrough()
    test_normalize_native_to_ils_usd_missing_fx_returns_none()
    test_value_stock_usa_ticker_fifo_and_currency()
    test_value_stock_tase_ticker_agorot_normalization()
    test_value_stock_tase_manual_override_is_real_ils_not_agorot()
    test_value_stock_usd_manual_override_converts_to_ils_via_fx()
    test_value_stock_no_purchases_returns_no_data()
    test_add_stock_sale_rejects_overselling()
    print("ok")
