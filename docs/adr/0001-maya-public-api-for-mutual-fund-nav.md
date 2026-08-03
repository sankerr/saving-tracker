---
status: accepted
---

# Use Maya's public API for daily mutual fund NAV instead of official TASE Data Hub

Daily NAV data for TASE mutual funds is a paid product (~$130+/mo) on the official TASE Data Hub, while fund listings/classifications are free. Since this is a personal tracker, we instead call Maya's public site API (`maya.tase.co.il/api/v1/funds/mutual/{id}/history`) directly — the same undocumented endpoints used by the third-party `pymaya` client — implemented as a small first-party client rather than a dependency.

This is a deliberate deviation from the "official" integration path: the endpoint is unofficial and could change or be rate-limited/blocked without notice, unlike a contracted paid API. If it breaks, the fallback is either the paid Data Hub product or manual price entry.
