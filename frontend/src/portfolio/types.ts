/** Types for GET /api/data (fields the UI reads). */

export type HoldingEvent = {
  id?: string;
  date?: string;
  kind?: string;
  amount_ils?: number;
  note?: string;
  synthetic?: boolean;
  pending?: boolean;
};

export type RecurringRule = {
  id: string;
  start_date: string;
  end_date?: string | null;
  employee?: number;
  employer?: number;
  day_of_month?: number;
  note?: string;
};

export type HoldingComputed = {
  current_value_ils?: number;
  profit_ils?: number;
  profit_pct?: number;
  last_period?: number;
  last_month_return_pct?: number;
  ytd_return_pct?: number;
  ytd_year?: number;
  total_deposited_ils?: number;
  total_withdrawn_ils?: number;
  cumulative_mgmt_fee_ils?: number;
  total_employee_ils?: number;
  total_employer_ils?: number;
  three_m_return_pct?: number | null;
  six_m_return_pct?: number | null;
  twelve_m_return_pct?: number | null;
  twentyfour_m_return_pct?: number | null;
  annualized_3y_return_pct?: number | null;
  annualized_5y_return_pct?: number | null;
  value_ils?: number;
  value_usd?: number;
  current_value_usd?: number;
  current_price_usd?: number;
  current_usdils?: number;
  cost_basis_per_share_usd?: number;
  cost_basis_total_usd?: number;
  cost_basis_total_ils?: number;
  grant_close_usd?: number;
  grant_usdils?: number;
  full_vest_date?: string;
  shares_held_now?: number;
  vested_shares_now?: number;
  shares_sold_total?: number;
  shares_remaining?: number;
  potential_full_vest_usd?: number;
  potential_full_vest_ils?: number;
  realized_gain_usd?: number;
  realized_gain_ils?: number;
  unrealized_gain_usd?: number;
  unrealized_gain_ils?: number;
  uses_override_price?: boolean;
  profit_usd?: number;
  total_contributed_usd?: number;
  total_contributed_ils?: number;
  shares_acquired_total?: number;
  discount_captured_usd_total?: number;
  lookback_bonus_usd_total?: number;
  no_data?: boolean;
  time_series?: Array<{ period?: number; date?: string; value_ils?: number }>;
  expanded_events?: HoldingEvent[];
  fund_metrics?: Record<string, number | string | null | undefined>;
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
  recurring_rules?: RecurringRule[];
  computed?: HoldingComputed;
  last_synced?: string;
};

export type PensionHolding = FundHolding;

export type RsuSale = {
  id: string;
  date: string;
  shares_sold: number;
  sale_price_usd: number;
  note?: string;
};

export type RsuGrant = {
  id: string;
  ticker: string;
  nickname?: string;
  archived?: boolean;
  grant_date?: string;
  vesting_cadence?: string;
  total_shares?: number;
  vesting_start?: string;
  vesting_months?: number;
  cliff_months?: number;
  sales?: RsuSale[];
  stock_history?: Array<{ date: string; close: number }>;
  computed?: HoldingComputed;
  last_synced?: string;
};

export type EsppPurchase = {
  id: string;
  date: string;
  contribution_usd: number;
  shares: number;
  period_start?: string;
  period_end?: string;
  buy_price_usd?: number;
  period_end_price_usd?: number;
  note?: string;
};

export type EsppSale = {
  id: string;
  date: string;
  shares_sold: number;
  sale_price_usd: number;
  note?: string;
};

export type EsppPlan = {
  id: string;
  ticker: string;
  nickname?: string;
  archived?: boolean;
  discount_pct?: number;
  has_lookback?: boolean;
  offering_months?: number;
  purchases?: EsppPurchase[];
  sales?: EsppSale[];
  stock_history?: Array<{ date: string; close: number }>;
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
    what_if?: {
      annual_pct?: number;
      horizon_months?: number;
      current_value_ils?: number;
      end_value_ils?: number;
      includes_recurring?: boolean;
    } | null;
  };
  cache_status?: {
    current_usdils?: number;
    usdils_override?: number | null;
    last_full_sync_at?: string;
    latest_published_period?: number;
    package_show_age_seconds?: number | null;
  };
};
