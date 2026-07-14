"""Email notifications via Resend HTTP API."""

from __future__ import annotations

import html
import os
from typing import Any, Optional

import requests

import chat as portfolio_chat

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_FROM = os.environ.get("NOTIFY_FROM", "")
RESEND_URL = "https://api.resend.com/emails"


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
                "kind": "Fund",
                "name": h.get("nickname") or h.get("fund_name_snapshot") or "Fund",
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
                "kind": "Pension",
                "name": h.get("nickname") or h.get("fund_name_snapshot") or "Pension",
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
    for csh in state.get("cash_holdings") or []:
        if csh.get("archived"):
            continue
        c = csh.get("computed") or {}
        rows.append(
            {
                "kind": "Cash",
                "name": csh.get("nickname") or "Cash",
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
    items = "".join(f"<li>{_esc(b)}</li>" for b in bullets[:6])
    return f"<ul style=\"margin:0.5rem 0 0;padding-left:1.25rem;\">{items}</ul>"


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
    cash = portfolio.get("cash_value_ils")
    pension_total = pension.get("total_value_ils")

    banner = ""
    if new_yield_period:
        banner = (
            "<div style=\"margin:0 0 1rem;padding:0.75rem 1rem;border-radius:8px;"
            "background:#fff8e8;border-left:3px solid #B76E00;color:#2B2B3E;font-size:14px;\">"
            f"<strong>New yields published</strong> for {_esc(_period_label(new_yield_period))}."
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
            "<tr><td colspan=\"4\" style=\"padding:8px;color:#8A8A9C;\">No holdings yet.</td></tr>"
        )

    usdils = cache.get("current_usdils")
    usdils_txt = f"{float(usdils):.3f}" if usdils is not None else "—"

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#FCFBF8;color:#2B2B3E;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:24px 16px;">
    <h1 style="margin:0 0 0.35rem;font-size:22px;color:#1A1A2E;">Saving Tracker</h1>
    <p style="margin:0 0 1.25rem;color:#8A8A9C;font-size:13px;">Daily snapshot · synced {_esc(synced_at)} · USDILS {_esc(usdils_txt)}</p>
    {banner}
    <div style="background:#fff;border:1px solid #ECE8DF;border-radius:12px;padding:1rem 1.125rem;margin-bottom:1rem;">
      <div style="font-size:13px;color:#8A8A9C;text-transform:uppercase;letter-spacing:0.06em;">Dashboard total</div>
      <div style="font-size:28px;font-weight:700;margin:0.25rem 0;">{_esc(_fmt_ils(total))}</div>
      <div style="font-size:14px;color:#1F8A4C;">Profit {_esc(_fmt_ils(profit))}</div>
      <p style="margin:0.75rem 0 0;font-size:12px;color:#8A8A9C;">Pension is tracked separately and not included in this total.</p>
      <table style="width:100%;border-collapse:collapse;margin-top:0.75rem;font-size:13px;">
        <tr>
          <td style="padding:4px 0;">Funds</td><td style="text-align:right;">{_esc(_fmt_ils(funds))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">RSU</td><td style="text-align:right;">{_esc(_fmt_ils(rsu))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">ESPP</td><td style="text-align:right;">{_esc(_fmt_ils(espp))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">Cash</td><td style="text-align:right;">{_esc(_fmt_ils(cash))}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;">Pension (excluded)</td><td style="text-align:right;">{_esc(_fmt_ils(pension_total))}</td>
        </tr>
      </table>
    </div>

    <div style="background:#fff;border:1px solid #ECE8DF;border-radius:12px;padding:1rem 1.125rem;margin-bottom:1rem;">
      <div style="font-size:15px;font-weight:600;margin-bottom:0.5rem;">Holdings snapshot</div>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="color:#8A8A9C;text-align:left;">
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;">Type</th>
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;">Name</th>
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;text-align:right;">Value</th>
            <th style="padding:6px 8px;border-bottom:1px solid #ECE8DF;font-weight:500;text-align:right;">Profit</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
    </div>

    <div style="background:#fff;border:1px solid #ECE8DF;border-radius:12px;padding:1rem 1.125rem;margin-bottom:1rem;">
      <div style="font-size:15px;font-weight:600;">AI insights</div>
      <div style="font-size:14px;line-height:1.5;color:#2B2B3E;">{_insights_html(insights_text)}</div>
      <p style="margin:0.75rem 0 0;font-size:11px;color:#8A8A9C;">
        Educational only — not financial, tax, or investment advice. Verify against official statements.
      </p>
    </div>

    <p style="margin:0;font-size:12px;color:#8A8A9C;">Open Saving Tracker to review charts, spot-check yields, or ask the AI chat.</p>
  </div>
</body></html>"""


def _send_resend(*, to: str, subject: str, html_body: str) -> bool:
    if not RESEND_API_KEY or not NOTIFY_FROM:
        print(f"notify: skipping email to {to} — RESEND_API_KEY or NOTIFY_FROM not set")
        return False
    try:
        r = requests.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": NOTIFY_FROM,
                "to": [to],
                "subject": subject,
                "html": html_body,
            },
            timeout=40,
        )
        if r.status_code >= 400:
            print(f"notify: Resend error {r.status_code} for {to}: {r.text}")
            return False
        return True
    except requests.RequestException as ex:
        print(f"notify: failed to send email to {to}: {ex}")
        return False


def send_daily_insight_email(
    *,
    to: str,
    state: dict,
    synced_at: str,
    new_yield_period: Optional[int] = None,
) -> bool:
    """Daily snapshot + Gemini insights. Works with GEMINI_API_KEY (CHAT_ENABLED not required)."""
    context = portfolio_chat.build_portfolio_context(state)
    try:
        insights = portfolio_chat.generate_daily_insights(context)
    except Exception as ex:
        print(f"notify: Gemini insights failed for {to}: {ex}")
        insights = "Insights unavailable today — open Saving Tracker for the full dashboard."

    subject = "Saving Tracker — daily snapshot"
    if new_yield_period:
        subject += f" · new yields {_period_label(new_yield_period)}"

    html_body = _build_dashboard_html(
        state=state,
        synced_at=synced_at,
        new_yield_period=new_yield_period,
        insights_text=insights,
    )
    return _send_resend(to=to, subject=subject, html_body=html_body)


def send_new_month_email(*, to: str, period_yyyymm: int, synced_at: str) -> bool:
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
