/** Types for GET /api/data (fields the UI reads). */

export type HoldingComputed = {
  current_value_ils?: number;
  profit_ils?: number;
  profit_pct?: number;
  last_period?: number;
  last_month_return_pct?: number;
  ytd_return_pct?: number;
  ytd_year?: number;
  total_deposited_ils?: number;
  value_ils?: number;
  value_usd?: number;
  time_series?: Array<{ period?: number; date?: string; value_ils?: number }>;
};

export type FundHolding = {
  id: string;
  fund_id: number;
  fund_name_snapshot?: string;
  managing_corporation_snapshot?: string;
  nickname?: string;
  archived?: boolean;
  included_in_dashboard?: boolean;
  data_source?: string;
  anchor_period?: number;
  anchor_balance_ils?: number;
  computed?: HoldingComputed;
  last_synced?: string;
};

export type PensionHolding = FundHolding;

export type RsuGrant = {
  id: string;
  ticker: string;
  nickname?: string;
  archived?: boolean;
  grant_date?: string;
  computed?: HoldingComputed & { shares_remaining?: number };
  last_synced?: string;
};

export type EsppPlan = {
  id: string;
  ticker: string;
  nickname?: string;
  archived?: boolean;
  computed?: HoldingComputed;
  last_synced?: string;
};

export type CashHolding = {
  id: string;
  nickname?: string;
  currency?: string;
  amount?: number;
  note?: string;
  computed?: { value_ils?: number; value_native?: number };
};

export type GoalStatus = {
  target_amount_ils: number;
  target_date: string;
  on_pace?: boolean;
  projected_amount_ils?: number;
  shortfall_ils?: number;
  surplus_ils?: number;
  progress_pct?: number;
} | null;

export type Portfolio = {
  total_value_ils?: number;
  total_profit_ils?: number;
  total_invested_ils?: number;
  funds_value_ils?: number;
  rsu_value_ils?: number;
  rsu_value_usd?: number;
  espp_value_ils?: number;
  espp_value_usd?: number;
  cash_value_ils?: number;
  time_series_ils?: Array<{
    label?: string;
    period?: number;
    funds_ils?: number;
    rsu_ils?: number;
    espp_ils?: number;
    cash_ils?: number;
    total_ils?: number;
  }>;
  what_if?: {
    annual_pct?: number;
    horizon_months?: number;
    current_value_ils?: number;
    end_value_ils?: number;
  } | null;
  projection?: {
    horizon_months?: number;
    paths?: { mean?: number[] };
    funds_includes_recurring?: boolean;
  } | null;
};

export type AppData = {
  ok?: boolean;
  now?: string;
  horizon_months?: number;
  settings?: {
    yield_is_net_of_fees?: boolean;
    usdils_rate_override?: number | null;
    goal?: { target_amount_ils: number; target_date: string } | null;
  };
  goal_status?: GoalStatus;
  fund_holdings?: FundHolding[];
  pension_holdings?: PensionHolding[];
  rsu_grants?: RsuGrant[];
  espp_plans?: EsppPlan[];
  cash_holdings?: CashHolding[];
  portfolio?: Portfolio;
  pension_summary?: {
    total_value_ils?: number;
    count?: number;
    excluded_from_total?: boolean;
  };
  cache_status?: {
    current_usdils?: number;
    usdils_override?: number | null;
    last_full_sync_at?: string;
    latest_published_period?: number;
  };
};
