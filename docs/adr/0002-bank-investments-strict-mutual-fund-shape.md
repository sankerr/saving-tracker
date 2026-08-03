---
status: accepted
---

# "Bank Investments" v1 data model is strictly mutual-fund-shaped

The new "Bank Investments" UI section is named generically, which could suggest it holds any bank-brokerage instrument (stocks, bonds, ETFs). We chose to keep the v1 schema narrow and specific — `tase_fund_holdings[]` with `fund_id` + `units`, no `instrument_type` discriminator — rather than generalizing upfront for instrument types that don't exist yet.

Trade-off: if individual TASE stocks or other instrument types are added later, this will require a schema migration (new holding array or an `instrument_type` field) rather than just a new row shape. Accepted because YAGNI outweighs speculative generality, and the existing codebase already prefers one array per holding type (funds, pension, RSU, ESPP, cash) over a polymorphic model.
