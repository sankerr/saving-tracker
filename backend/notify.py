"""Email notifications via Resend HTTP API."""

import os

import requests

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_FROM = os.environ.get("NOTIFY_FROM", "")
RESEND_URL = "https://api.resend.com/emails"


def _period_label(period_yyyymm: int) -> str:
    y, m = divmod(period_yyyymm, 100)
    return f"{y}-{m:02d}"


def send_new_month_email(*, to: str, period_yyyymm: int, synced_at: str) -> bool:
    if not RESEND_API_KEY or not NOTIFY_FROM:
        print(f"notify: skipping email to {to} — RESEND_API_KEY or NOTIFY_FROM not set")
        return False

    period_label = _period_label(period_yyyymm)
    payload = {
        "from": NOTIFY_FROM,
        "to": [to],
        "subject": f"Saving Tracker — new yields for {period_label}",
        "html": (
            f"<p>New monthly fund yields are available for <strong>{period_label}</strong>.</p>"
            f"<p>Your portfolio was synced at {synced_at}.</p>"
            f"<p>Open Saving Tracker to review updated balances and spot-check against your statements.</p>"
        ),
    }
    try:
        r = requests.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=25,
        )
        if r.status_code >= 400:
            print(f"notify: Resend error {r.status_code} for {to}: {r.text}")
            return False
        return True
    except requests.RequestException as ex:
        print(f"notify: failed to send email to {to}: {ex}")
        return False
