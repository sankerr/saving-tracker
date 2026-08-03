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

## Relationships

- A **Bank Investment** holding references exactly one TASE mutual fund via `fund_id`
- A **Bank Investment** holding's value = **Units** x latest **NAV**
- **Bank Investment** is a distinct concept from **Fund (Provident Fund)**, despite the shared English word "fund"

## Example dialogue

> **Dev:** "Should the new section be called 'Funds' too, since it's also a fund?"
> **User:** "No — call it 'Bank Investments' to avoid clashing with the existing gemel/pension 'Funds' section."

## Flagged ambiguities

- The user's original phrasing was "stocks," but Maya IDs like 5123898 are TASE **mutual funds** (קרנות נאמנות), valued as Units x NAV, not individual equities (shares x market price). Resolution: modeled as **Bank Investment** with mutual-fund valuation semantics, confirmed with the user.
- "Bank Investments" is a generic-sounding UI label, but the v1 data model is strictly mutual-fund-shaped (`fund_id` + `units`), not a polymorphic instrument type. Resolution: deferred generalization; the label may outlive the narrower v1 schema and would need extension if individual TASE stocks are added later.
- TASE mutual fund NAV: Maya history returns unit prices in **Agorot** (e.g. 1189.82 for מיטב כספית). ILS value = units × price / 100. Confirmed against Bizportal display of the same number and conventional TASE mutual-fund quoting.
