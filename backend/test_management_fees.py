"""Unit tests for user-configured fund/pension management fees."""
from __future__ import annotations

import saving_tracker as st


def _seed_yields(fund_id: str, periods_yields: dict, source: str = "gemelnet"):
    monthly_key = st.SOURCE_CONFIG[source]["monthly_cache_key"]
    rows = [
        {
            "report_period": p,
            "monthly_yield": y,
            "avg_annual_management_fee": 1.2,  # catalog — must NOT drive balance
            "raw": {
                "AVG_ANNUAL_MANAGEMENT_FEE": 1.2,
                "AVG_DEPOSIT_FEE": 0.5,
            },
        }
        for p, y in sorted(periods_yields.items())
    ]
    st.MARKET[monthly_key] = {
        str(fund_id): {"rows": rows, "last_synced": "2026-06-01T00:00:00", "meta": {}}
    }


def _base_holding(**overrides):
    h = {
        "id": "h1",
        "fund_id": 76,
        "anchor_period": 202601,
        "anchor_balance_ils": 12000.0,
        "yield_is_net_of_fees": True,
        "events": [],
        "recurring_rules": [],
    }
    h.update(overrides)
    return h


def test_parse_optional_fee_pct():
    assert st.parse_optional_fee_pct(None, "x") == (None, None)
    assert st.parse_optional_fee_pct("", "x") == (None, None)
    assert st.parse_optional_fee_pct(0, "x") == (0.0, None)
    assert st.parse_optional_fee_pct("1.5", "x") == (1.5, None)
    assert st.parse_optional_fee_pct(-1, "x")[1]


def test_fees_null_no_balance_deduction_ignores_catalog():
    _seed_yields(76, {202601: 0.0, 202602: 0.0, 202603: 0.0})
    holding = _base_holding()
    c = st.value_fund(holding)
    # Flat yields, no user fees → balance stays at anchor
    assert c["current_value_ils"] == 12000.0
    assert c["cumulative_mgmt_fee_ils"] == 0.0
    # Catalog metrics still exposed
    assert c["fund_metrics"]["avg_annual_management_fee_pct"] == 1.2


def test_accumulation_fee_monthly_from_start_balance():
    _seed_yields(76, {202601: 0.0, 202602: 0.0})
    # 1.2% annual → 0.1%/month of start → 12 ILS on 12000
    holding = _base_holding(accumulation_fee_pct_annual=1.2)
    c = st.value_fund(holding)
    assert c["current_value_ils"] == 11988.0
    assert c["cumulative_mgmt_fee_ils"] == 12.0
    row = [r for r in c["time_series"] if r["period"] == 202602][0]
    assert row["accumulation_fee_ils"] == 12.0
    assert row["deposit_fee_ils"] == 0.0


def test_deposit_fee_nets_credit_keeps_gross_deposited():
    _seed_yields(76, {202601: 0.0, 202602: 0.0})
    holding = _base_holding(
        deposit_fee_pct=1.0,
        events=[{
            "id": "e1",
            "date": "2026-02-10",
            "kind": "deposit",
            "amount_ils": 1000,
            "note": "",
            "source": "manual",
        }],
    )
    c = st.value_fund(holding)
    assert c["total_deposited_ils"] == 1000.0
    assert c["current_value_ils"] == 12000.0 + 990.0
    assert c["cumulative_mgmt_fee_ils"] == 10.0


def test_both_fees_with_yield():
    _seed_yields(76, {202601: 0.0, 202602: 1.0})  # +1% yield
    holding = _base_holding(
        deposit_fee_pct=1.0,
        accumulation_fee_pct_annual=1.2,
        events=[{
            "id": "e1",
            "date": "2026-02-15",
            "kind": "deposit",
            "amount_ils": 1000,
            "note": "",
            "source": "manual",
        }],
    )
    c = st.value_fund(holding)
    # start 12000 → yield 12120 → acc fee 12 → 12108 + net deposit 990 = 13098
    assert c["current_value_ils"] == 13098.0
    assert abs(c["cumulative_mgmt_fee_ils"] - 22.0) < 1e-9


def test_recurring_rule_deposit_fee():
    _seed_yields(76, {202601: 0.0, 202602: 0.0})
    holding = _base_holding(
        deposit_fee_pct=2.0,
        recurring_rules=[{
            "id": "r1",
            "start_date": "2026-01-01",
            "end_date": None,
            "employee": 400,
            "employer": 600,
            "day_of_month": 10,
            "note": "",
        }],
    )
    c = st.value_fund(holding)
    assert c["total_deposited_ils"] == 1000.0
    assert c["total_employee_ils"] == 400.0
    assert c["total_employer_ils"] == 600.0
    assert c["current_value_ils"] == 12000.0 + 980.0
    assert c["cumulative_mgmt_fee_ils"] == 20.0


def test_correction_without_seed_keeps_summing():
    _seed_yields(76, {202601: 0.0, 202602: 0.0, 202603: 0.0})
    holding = _base_holding(
        accumulation_fee_pct_annual=1.2,
        events=[{
            "id": "c1",
            "date": "2026-02-28",
            "kind": "correction",
            "amount_ils": 11000,
            "note": "",
            "source": "manual",
        }],
    )
    c = st.value_fund(holding)
    assert c["current_value_ils"] == 11000.0 - 11.0  # Mar fee on 11000
    # Feb: 12 fee (even with correction, no seed → add period fee) + Mar: 11
    assert c["cumulative_mgmt_fee_ils"] == 23.0


def test_correction_with_fee_seed_replaces_cumulative():
    _seed_yields(76, {202601: 0.0, 202602: 0.0, 202603: 0.0})
    holding = _base_holding(
        accumulation_fee_pct_annual=1.2,
        events=[{
            "id": "c1",
            "date": "2026-02-28",
            "kind": "correction",
            "amount_ils": 11000,
            "total_fees_paid_ils": 50,
            "note": "",
            "source": "manual",
        }],
    )
    c = st.value_fund(holding)
    # Seed 50 at Feb (no add of Feb fee), then Mar adds 11
    assert c["cumulative_mgmt_fee_ils"] == 61.0
    assert c["current_value_ils"] == 11000.0 - 11.0


def test_yield_is_net_does_not_gate_user_fees():
    _seed_yields(76, {202601: 0.0, 202602: 0.0})
    holding_net = _base_holding(yield_is_net_of_fees=True, accumulation_fee_pct_annual=1.2)
    holding_gross = _base_holding(yield_is_net_of_fees=False, accumulation_fee_pct_annual=1.2)
    assert st.value_fund(holding_net)["current_value_ils"] == st.value_fund(holding_gross)["current_value_ils"]


def test_holding_fee_fields_from_payload_rejects_negative():
    updates, err = st.holding_fee_fields_from_payload({"deposit_fee_pct": -0.1})
    assert updates is None
    assert err


def test_add_event_rejects_negative_fee_seed():
    st.DATA = st.default_data() if hasattr(st, "default_data") else {
        "settings": {"yield_is_net_of_fees": True},
        "fund_holdings": [_base_holding()],
        "pension_holdings": [],
    }
    # Ensure structure matches app expectations
    if "fund_holdings" not in st.DATA:
        st.DATA["fund_holdings"] = [_base_holding()]
    else:
        st.DATA["fund_holdings"] = [_base_holding()]
    st.DATA.setdefault("pension_holdings", [])

    # Monkeypatch save_data to no-op
    original_save = st.save_data
    st.save_data = lambda: None
    try:
        bad = st.add_event("h1", {
            "date": "2026-02-01",
            "kind": "correction",
            "amount_ils": 1000,
            "total_fees_paid_ils": -5,
        })
        assert bad["ok"] is False
        good = st.add_event("h1", {
            "date": "2026-02-01",
            "kind": "correction",
            "amount_ils": 1000,
            "total_fees_paid_ils": 12.5,
        })
        assert good["ok"] is True
        ev = st.DATA["fund_holdings"][0]["events"][0]
        assert ev["total_fees_paid_ils"] == 12.5
    finally:
        st.save_data = original_save


def test_project_contributions_net_of_deposit_fee():
    holding = _base_holding(
        deposit_fee_pct=10.0,
        recurring_rules=[{
            "id": "r1",
            "start_date": "2026-01-01",
            "end_date": None,
            "employee": 90,
            "employer": 10,
            "day_of_month": 1,
            "note": "",
        }],
    )
    computed = {"last_period": 202601}
    contribs = st._project_fund_contributions(holding, computed, 2)
    assert contribs[0] == 90.0  # 100 * 0.9
    assert contribs[1] == 90.0


def test_project_returns_applies_accumulation_fee():
    returns = [0.0] * 6
    out = st.project_returns(returns, 12000.0, 1, [0.0], accumulation_fee_pct_annual=1.2)
    assert out["paths"]["mean"][0] == 11988.0


def test_zero_fees_allowed():
    _seed_yields(76, {202601: 0.0, 202602: 0.0})
    holding = _base_holding(deposit_fee_pct=0, accumulation_fee_pct_annual=0)
    c = st.value_fund(holding)
    assert c["current_value_ils"] == 12000.0
    assert c["cumulative_mgmt_fee_ils"] == 0.0
