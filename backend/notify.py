"""Email notifications via Resend HTTP API."""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

import chat as portfolio_chat

RESEND_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class NotifyResult:
    ok: bool
    error: Optional[str] = None


def _log(msg: str) -> None:
    print(msg, flush=True)


def _resend_config() -> tuple[str, str]:
    """Read env at send time so redeploys / dashboard edits are picked up."""
    key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("NOTIFY_FROM") or "").strip()
    return key, from_addr


def _period_label(period_yyyymm: int) -> str:
    y, m = divmod(period_yyyymm, 100)
    return f"{y}-{m:02d}"


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _fmt_ils(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"₪{n:,.0f}"


def _holding_rows(state: dict, limit: int = 8) -> list[dict]:
    rows = []
    for h in state.get("fund_holdings") or []:
        if h.get("archived"):
            continue
        c = h.get("computed") or {}
        rows.append(
            {
                "kind": "קופה",
                "name": h.get("nickname") or h.get("fund_name_snapshot") or "קופה",
                "value": c.get("current_value_ils"),
                "profit": c.get("profit_ils"),
            }
        )
    for h in state.get("pension_holdings") or []:
        if h.get("archived"):
            continue
        c = h.get("computed") or {}
        rows.append(
            {
                "kind": "פנסיה",
                "name": h.get("nickname") or h.get("fund_name_snapshot") or "פנסיה",
                "value": c.get("current_value_ils"),
                "profit": c.get("profit_ils"),
            }
        )
    for g in state.get("rsu_grants") or []:
        if g.get("archived"):
            continue
        c = g.get("computed") or {}
        rows.append(
            {
                "kind": "RSU",
                "name": g.get("nickname") or g.get("ticker") or "RSU",
                "value": c.get("current_value_ils"),
                "profit": c.get("profit_ils"),
            }
        )
    for p in state.get("espp_plans") or []:
        if p.get("archived"):
            continue
        c = p.get("computed") or {}
        rows.append(
            {
                "kind": "ESPP",
                "name": p.get("nickname") or p.get("ticker") or "ESPP",
                "value": c.get("current_value_ils"),
                "profit": c.get("profit_ils"),
            }
        )
    for h in state.get("stock_holdings") or []:
        if h.get("archived"):
            continue
        c = h.get("computed") or {}
        rows.append(
            {
                "kind": "מניות",
                "name": h.get("nickname") or h.get("ticker") or "מניות",
                "value": c.get("current_value_ils"),
                "profit": c.get("profit_ils"),
            }
        )
    for csh in state.get("cash_holdings") or []:
        if csh.get("archived"):
            continue
        c = csh.get("computed") or {}
        rows.append(
            {
                "kind": "מזומן",
                "name": csh.get("nickname") or "מזומן",
                "value": c.get("value_ils"),
                "profit": None,
            }
        )
    rows.sort(key=lambda r: float(r.get("value") or 0), reverse=True)
    return rows[:limit]


def _insights_html(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    bullets = []
    for ln in lines:
        if ln.startswith("- ") or ln.startswith("• "):
            bullets.append(ln[2:].strip())
        else:
            bullets.append(ln)
    if not bullets:
        return f"<p>{_esc(text)}</p>"
    items = "".join(f"<li>{_esc(b)}</li>" for b in bullets[:8])
    return f"<ul style=\"margin:0.5rem 0 0;padding-inline-start:1.25rem;\">{items}</ul>"


def _build_dashboard_html(
    *,
    state: dict,
    synced_at: str,
    new_yield_period: Optional[int],
    insights_text: str,
) -> str:
    portfolio = state.get("portfolio") or {}
    pension = state.get("pension_summary") or {}
    cache = state.get("cache_status") or {}

    total = portfolio.get("total_value_ils")
    profit = portfolio.get("total_profit_ils")
    funds = portfolio.get("funds_value_ils")
    rsu = portfolio.get("rsu_value_ils")
    espp = portfolio.get("espp_value_ils")
    stocks = portfolio.get("stocks_value_ils")
    cash = portfolio.get("cash_value_ils")
    pension_total = pension.get("total_value_ils")

    banner = ""
    if new_yield_period:
        banner = (
            "<div style=\"margin:0 0 1rem;padding:0.75rem 1rem;border-radius:8px;"
            "background:#fff8e8;border-left:3px solid #B76E00;color:#2B2B3E;font-size:14px;\">"
            f"<strong>פורסמו תשואות חדשות</strong> עבור {_esc(_period_label(new_yield_period))}."
            "</div>"
        )

    rows_html = []
    for row in _holding_rows(state):
        rows_html.append(
            "<tr>"
            f"<td style=\"padding:6px 8px;border-bottom:1px solid #ECE8DF;\">{_esc(row['kind'])}</td>"
            f"<td style=\"padding:6px 8px;border-bottom:1px solid #ECE8DF;\">{_esc(row['name'])}</td>"
            f"<td style=\"padding:6px 8px;border-bottom:1px solid #ECE8DF;text-align:right;\">{_esc(_fmt_ils(row['value']))}</td>"
            f"<td style=\"padding:6px 8px;border-bottom:1px solid #ECE8DF;text-align:right;\">{_esc(_fmt_ils(row['profit']) if row.get('profit') is not None else '—')}</td>"
            "</tr>"
        )
    if not rows_html:
        rows_html.append(
            "<tr><td colspan=\"4\" style=\"padding:8px;color:#8A8A9C;\">אין עדיין אחזקות.</td></tr>"
        )

    usdils = cache.get("current_usdils")
    usdils_txt = f"{float(usdils):.3f}" if usdils is not None else "—"

    if (insights_text or "").strip():
        insights_body = _insights_html(insights_text)
    else:
        insights_body = '<p style="margin:0;color:#8A8A9C;">אין תובנות בביטחון גבוה להיום.</p>'

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><body style="margin:0;padding:0;background:#FCFBF8;color:#2B2B3E;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:24px 16px;">
    <h1 style="margin:0 0 0.35rem;font-size:22px;color:#1A1A2E;">מעקב חיסכון</h1>
    <p style="margin:0 0 1.25rem;color:#8A8A9C;font-size:13px;">סיכום יומי · סונכרן {_esc(synced_at)} · USDILS {_esc(usdils_txt)}</p>
    {banner}
    <div style="background:#fff;border:1px solid #ECE8DF;border-radius:12px;padding:1rem 1.125rem;margin-bottom:1rem;">
      <div style="font-size:13px;color:#8A8A9C;text-transform:uppercase;letter-spacing:0.06em;">סך התיק</div>
      <div style="font-size:28px;font-weight:700;margin:0.25rem 0;">{_esc(_fmt_ils(total))}</div>
      <div style="font-size:14px;color:#1F8A4C;">רווח {_esc(_fmt_ils(profit))}</div>
      <p style="margin:0.75rem 0 0;font-size:12px;color:#8A8A9C;">פנסיה מנוהלת בנפרד ואינה כלולה בסכום זה.</p>
      <table style="width:100%;border-collapse:collapse;margin-top:0.75rem;font-size:13px;">
        <tr>
          <td style="padding:4px 0;">קופות / גמל</td><td style="text-align:left;">{_esc(_fmt_ils(funds))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">RSU</td><td style="text-align:left;">{_esc(_fmt_ils(rsu))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">ESPP</td><td style="text-align:left;">{_esc(_fmt_ils(espp))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">מניות</td><td style="text-align:left;">{_esc(_fmt_ils(stocks))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">מזומן</td><td style="text-align:left;">{_esc(_fmt_ils(cash))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">פנסיה (לא כלול)</td><td style="text-align:left;">{_esc(_fmt_ils(pension_total))}</td>
        </tr>
      </table>
    </div>

    <div style="background:#fff;border:1px solid #ECE8DF;border-radius:12px;padding:1rem 1.125rem;margin-bottom:1rem;">
      <div style="font-size:15px;font-weight:600;margin-bottom:0.5rem;">צילום אחזקות</div>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="color:#8A8A9C;text-align:right;">
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;">סוג</th>
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;">שם</th>
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;text-align:left;">ערך</th>
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;text-align:left;">רווח</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
    </div>

    <div style="background:#fff;border:1px solid #ECE8DF;border-radius:12px;padding:1rem 1.125rem;margin-bottom:1rem;">
      <div style="font-size:15px;font-weight:600;">תובנות AI</div>
      <div style="font-size:14px;line-height:1.5;color:#2B2B3E;">{insights_body}</div>
      <p style="margin:0.75rem 0 0;font-size:11px;color:#8A8A9C;">
        לצורכי לימוד בלבד — אינו ייעוץ פיננסי, מס או השקעות. אמתו מול דוחות רשמיים.
      </p>
    </div>

    <p style="margin:0;font-size:12px;color:#8A8A9C;">פתחו את מעקב החיסכון לגרפים, בדיקת תשואות או שיחת AI.</p>
  </div>
</body></html>"""


def _send_resend(*, to: str, subject: str, html_body: str) -> NotifyResult:
    api_key, notify_from = _resend_config()
    if not api_key or not notify_from:
        missing = []
        if not api_key:
            missing.append("RESEND_API_KEY")
        if not notify_from:
            missing.append("NOTIFY_FROM")
        err = f"missing env: {', '.join(missing)}"
        _log(f"notify: skipping email to {to} — {err}")
        return NotifyResult(ok=False, error=err)
    try:
        _log(f"notify: sending email to {to} subject={subject!r} from={notify_from!r}")
        r = requests.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": notify_from,
                "to": [to],
                "subject": subject,
                "html": html_body,
            },
            timeout=40,
        )
        if r.status_code >= 400:
            err = f"Resend HTTP {r.status_code}: {r.text[:300]}"
            _log(f"notify: {err} (to={to})")
            return NotifyResult(ok=False, error=err)
        _log(f"notify: sent email to {to} (HTTP {r.status_code})")
        return NotifyResult(ok=True)
    except requests.RequestException as ex:
        err = f"Resend request failed: {ex}"
        _log(f"notify: {err} (to={to})")
        return NotifyResult(ok=False, error=err)


def send_daily_insight_email(
    *,
    to: str,
    state: dict,
    synced_at: str,
    new_yield_period: Optional[int] = None,
) -> NotifyResult:
    """Daily snapshot + Gemini insights. Works with GEMINI_API_KEY (CHAT_ENABLED not required)."""
    try:
        context = portfolio_chat.build_portfolio_context(state)
        try:
            insights = portfolio_chat.generate_daily_insights(context, lang="he")
        except Exception as ex:
            _log(f"notify: Gemini insights failed for {to}: {ex}")
            insights = "התובנות אינן זמינות היום — פתחו את מעקב החיסכון ללוח המלא."

        subject = "מעקב חיסכון — סיכום יומי"
        if new_yield_period:
            subject += f" · תשואות חדשות {_period_label(new_yield_period)}"

        html_body = _build_dashboard_html(
            state=state,
            synced_at=synced_at,
            new_yield_period=new_yield_period,
            insights_text=insights,
        )
        return _send_resend(to=to, subject=subject, html_body=html_body)
    except Exception as ex:
        err = f"daily insight build failed: {ex}"
        _log(f"notify: {err} (to={to})")
        return NotifyResult(ok=False, error=err)


def send_new_month_email(*, to: str, period_yyyymm: int, synced_at: str) -> NotifyResult:
    """Legacy simple new-yield notice (no portfolio snapshot). Prefer send_daily_insight_email."""
    period_label = _period_label(period_yyyymm)
    html_body = (
        f"<p>New monthly fund yields are available for <strong>{_esc(period_label)}</strong>.</p>"
        f"<p>Your portfolio was synced at {_esc(synced_at)}.</p>"
        f"<p>Open Saving Tracker to review updated balances and spot-check against your statements.</p>"
    )
    return _send_resend(
        to=to,
        subject=f"Saving Tracker — new yields for {period_label}",
        html_body=html_body,
    )
