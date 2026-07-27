"""Unit tests: MoM investment return excludes fund deposits/withdrawals."""
from __future__ import annotations

import chat as portfolio_chat


def _holding_with_flows(series_pts):
    return {
        "archived": False,
        "computed": {
            "time_series": [
                {
                    "period": p,
                    "deposited_to_date": dep,
                    "withdrawn_to_date": wd,
                    "value_ils": val,
                }
                for p, dep, wd, val in series_pts
            ]
        },
    }


def test_fund_net_flows_by_period():
    state = {
        "fund_holdings": [
            _holding_with_flows([
                (202605, 0, 0, 100_000),
                (202606, 100_000, 0, 234_783),  # +100k deposit in June
            ])
        ]
    }
    flows = portfolio_chat._fund_net_flows_by_period(state)
    assert flows[202606] == 100_000.0
    assert 202605 not in flows or flows.get(202605, 0) == 0


def test_investment_return_excludes_deposits():
    state = {
        "cache_status": {"latest_published_period": 202606},
        "fund_holdings": [
            _holding_with_flows([
                (202605, 0, 0, 880_000),
                (202606, 100_000, 0, 1_014_783),
            ])
        ],
        "portfolio": {
            "cash_value_ils": 0,
            "time_series_ils": [
                {"period": "2026-05", "funds_ils": 880_000, "rsu_ils": 0, "espp_ils": 0, "total_ils": 880_000},
                {"period": "2026-06", "funds_ils": 1_014_783, "rsu_ils": 0, "espp_ils": 0, "total_ils": 1_014_783},
            ],
        },
    }
    hist = portfolio_chat._build_monthly_history(state, max_months=0)
    june = next(m for m in hist["months"] if m["period"] == "2026-06")
    assert june["change_from_prev_ils"] == 134_783.0
    assert june["net_external_flow_ils"] == 100_000.0
    assert june["investment_return_ils"] == 34_783.0
    assert june["investment_return_pct"] == round(34_783.0 / 880_000.0, 4)

    latest = hist["latest_yield_month"]
    assert latest["period"] == "2026-06"
    assert latest["investment_return_ils"] == 34_783.0
    assert latest["net_external_flow_ils"] == 100_000.0


if __name__ == "__main__":
    test_fund_net_flows_by_period()
    test_investment_return_excludes_deposits()
    print("ok")
