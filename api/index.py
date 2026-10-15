"""Vercel serverless entrypoint for saving-tracker.

Reuses backend/saving_tracker.py's Handler wholesale: Vercel still supports
the ``handler(BaseHTTPRequestHandler)`` shape for files under /api when no
Python framework preset is detected (our deps contain no FastAPI/Flask/
Django), so all /api/* routes run in one function. vercel.json rewrites
/api/:path* to /api and the handler dispatches on self.path exactly like the
long-running server did.

Stateless notes:
- No listening socket / PORT: Vercel invokes do_GET/POST/... per request.
- Storage bootstrap (previously in main()) runs lazily via _ensure_ready(),
  once per function instance. Per-request user state keeps working because
  every request activates its own user context from Neon.
- Production storage must be Neon Postgres (DATABASE_URL). SQLite is only for
  local dev; the serverless filesystem is ephemeral.
- POST /api/cron/sync runs inline and returns the full results (200). The old
  202 + background-thread + poll contract cannot work on serverless: function
  instances freeze after the response and status is per-instance.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import saving_tracker as app_mod

_BOOTSTRAPPED = False


def _ensure_ready() -> None:
    """Run bootstrap_storage() once per function instance (idempotent)."""
    global _BOOTSTRAPPED
    if app_mod.db.IS_SQLITE and os.environ.get("VERCEL_ENV") in ("production", "preview"):
        raise RuntimeError("DATABASE_URL is not configured (SQLite has no persistent storage on Vercel)")
    if not _BOOTSTRAPPED:
        app_mod.bootstrap_storage()
        _BOOTSTRAPPED = True


class handler(app_mod.Handler):
    """Function class Vercel loads; per-request init, then existing routing."""

    def _ready_or_500(self) -> bool:
        try:
            _ensure_ready()
        except RuntimeError as e:
            try:
                self._json(500, {"ok": False, "error": str(e)})
            except Exception:
                pass
            return False
        return True

    def do_GET(self):
        if not self._ready_or_500():
            return
        return super().do_GET()

    def do_POST(self):
        if not self._ready_or_500():
            return
        return super().do_POST()

    def do_PATCH(self):
        if not self._ready_or_500():
            return
        return super().do_PATCH()

    def do_PUT(self):
        if not self._ready_or_500():
            return
        return super().do_PUT()

    def do_DELETE(self):
        if not self._ready_or_500():
            return
        return super().do_DELETE()

    def do_OPTIONS(self):
        # CORS preflight needs no DB work.
        return super().do_OPTIONS()
