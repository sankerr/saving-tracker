# Saving Tracker

Personal portfolio tracker for Israeli savings/investment vehicles: provident/pension funds, RSU/ESPP equity compensation, cash, and (new) bank-held mutual funds.

## Language

**Fund (Provident Fund)**:
A gemel/pension/insurance savings product sourced from data.gov.il (gemelnet / pensia-net / ביטוח-נט), valued via monthly reported yields. UI section: "Funds" (קופות).
_Avoid_: Mutual fund, investment fund, Bank Investment

**Bank Investment**:
A TASE-listed mutual fund (קרן נאמנות) held directly through a bank brokerage account, identified by its Maya/TASE security ID (e.g. 5123898), valued daily as Units × NAV via the Maya public API. UI section: "Bank Investments".
_Avoid_: Stock, TASE fund, "mutual fund" as a UI label

**Units**:
Quantity of a Bank Investment fund held. User-editable directly; not derived from buy/sell lot history in v1.
_Avoid_: Shares (reserved for RSU/ESPP equity holdings)

**NAV (Net Asset Value)**:
Daily unit price of a Bank Investment fund, in ILS, fetched from Maya.
_Avoid_: Price (used generically elsewhere in the app), Rate

**Bank Investment projection**:
Forward value path from the mean of ≥6 month-end Maya NAV returns (same `project_returns` engine as gemelnet Funds). The dashboard what-if growth % does **not** compound Bank Investments — they stay flat there (like cash/ESPP).
_Avoid_: Analyst target (RSU/ESPP only)

**Enrolment (ESPP)**:
A user’s commitment to one ESPP offering window: period start/end dates plus a monthly NIS contribution. Unsettled enrolments contribute **pending contributions** to the portfolio; they settle into a Purchase when the offering period ends.
_Avoid_: Cycle, offering (as the stored entity name)

**Purchase (ESPP)**:
Settled lot of shares bought via ESPP for one offering period (contribution USD, period prices, purchase price after discount/lookback, share count). Created by settling an Enrolment or legacy manual API.
_Avoid_: Enrolment

**Offering period**:
The start→end date range on an Enrolment during which payroll contributions accrue and lookback prices are measured.
_Avoid_: Enrolment (the offering period is an attribute, not a separate entity)

**Lookback**:
ESPP rule that applies the plan discount to the lower of period-start and period-end stock price (when enabled on the plan).
_Avoid_: Discount (discount is the percentage; lookback chooses which price it applies to)

**Pending contributions**:
Accumulated NIS from unsettled Enrolments (months whose contribution date is ≤ today). Included in the ESPP/portfolio total; estimated share FMV is detail-only.
_Avoid_: Held shares, cost basis

## Relationships

- A **Bank Investment** holding references exactly one TASE mutual fund via `fund_id`
- A **Bank Investment** holding's value = **Units** x latest **NAV**
- **Bank Investment** is a distinct concept from **Fund (Provident Fund)**, despite the shared English word "fund"
- An ESPP **Plan** has many **Enrolments** and many **Purchases**
- An **Enrolment** settles into at most one **Purchase**
- Unsettled **Enrolment** value in the portfolio = **Pending contributions** (NIS), not estimated share FMV

## Example dialogue

> **Dev:** "Should the new section be called 'Funds' too, since it's also a fund?"
> **User:** "No — call it 'Bank Investments' to avoid clashing with the existing gemel/pension 'Funds' section."

> **Dev:** "For an active ESPP offering, do we add estimated shares × current price to the dashboard?"
> **User:** "No — only pending contributions (NIS already paid in). Estimates stay in the ESPP detail."

## Flagged ambiguities

- The user's original phrasing was "stocks," but Maya IDs like 5123898 are TASE **mutual funds** (קרנות נאמנות), valued as Units x NAV, not individual equities (shares x market price). Resolution: modeled as **Bank Investment** with mutual-fund valuation semantics, confirmed with the user.
- "Bank Investments" is a generic-sounding UI label, but the v1 data model is strictly mutual-fund-shaped (`fund_id` + `units`), not a polymorphic instrument type. Resolution: deferred generalization; the label may outlive the narrower v1 schema and would need extension if individual TASE stocks are added later.
- TASE mutual fund NAV: Maya history returns unit prices in **Agorot** (e.g. 1189.82 for מיטב כספית). ILS value = units × price / 100. Confirmed against Bizportal display of the same number and conventional TASE mutual-fund quoting.
- "Enrolment" vs "offering" / "cycle": resolved as **Enrolment** for the stored object; **offering period** is its date range attribute.
