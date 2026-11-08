"""Health of the connected data sources, from their sync history.

The integrations are simulated: their sync runs are seeded rows in
source_syncs, so every row is marked simulated: true. The data is not
job-scoped, so this function takes no principal.

Status rules, checked in order:
  Down      the last sync finished more than 6 hours before as_of, or the last 3 runs failed
  Degraded  the last sync finished more than 1 hour before as_of, or more than 5% of the
            runs in the 24 hours before as_of failed or were partial
  Healthy   otherwise
"""

from __future__ import annotations

from typing import Any

from app import db
from app.logic.common import days_between, pct, resolve_as_of

DOWN_AFTER_HOURS = 6
DEGRADED_AFTER_HOURS = 1
MAX_ERROR_RATE_PCT = 5.0
FAILED_RUNS_FOR_DOWN = 3
MODE = "read_only_sync"


def integration_health(as_of: str | None = None) -> dict[str, Any]:
    """One row per integration with status, last sync, records, 24-hour error rate, and last error."""
    as_of = resolve_as_of(as_of)
    runs = db.rows("""SELECT sync_id, integration, started_at, finished_at, status, records, error_message
                      FROM source_syncs WHERE finished_at <= :as_of
                      ORDER BY integration, finished_at DESC, sync_id DESC""", {"as_of": as_of})
    names = sorted({r["integration"] for r in runs})
    return {"as_of": as_of, "integrations": [health_row(name, [r for r in runs if r["integration"] == name], as_of)
                                             for name in names]}


def health_row(name: str, runs: list[dict[str, Any]], as_of: str) -> dict[str, Any]:
    """The health of one integration, from its runs newest first."""
    last = runs[0]
    hours_since = days_between(last["finished_at"], as_of) * 24
    recent = [r for r in runs if days_between(r["finished_at"], as_of) <= 1]
    errors = sum(1 for r in recent if r["status"] != "success")
    error_rate = pct(errors, len(recent)) or 0.0
    last_three_failed = len(runs) >= FAILED_RUNS_FOR_DOWN and all(
        r["status"] == "failed" for r in runs[:FAILED_RUNS_FOR_DOWN])
    last_error = next((r for r in runs if r["error_message"]), None)

    reasons = []
    if hours_since > DOWN_AFTER_HOURS or last_three_failed:
        status = "Down"
        if hours_since > DOWN_AFTER_HOURS:
            reasons.append(f"last sync {hours_since:.1f} hours ago (over {DOWN_AFTER_HOURS})")
        if last_three_failed:
            reasons.append(f"last {FAILED_RUNS_FOR_DOWN} runs failed")
    elif hours_since > DEGRADED_AFTER_HOURS or error_rate > MAX_ERROR_RATE_PCT:
        status = "Degraded"
        if hours_since > DEGRADED_AFTER_HOURS:
            reasons.append(f"last sync {hours_since:.1f} hours ago (over {DEGRADED_AFTER_HOURS})")
        if error_rate > MAX_ERROR_RATE_PCT:
            reasons.append(f"24-hour error rate {error_rate}% (over {MAX_ERROR_RATE_PCT}%)")
    else:
        status = "Healthy"

    return {
        "integration": name,
        "status": status,
        "reasons": reasons,
        "last_sync": last["finished_at"],
        "last_sync_id": last["sync_id"],
        "hours_since_last_sync": round(hours_since, 1),
        "records": last["records"],
        "runs_24h": len(recent),
        "error_rate_24h_pct": error_rate,
        "last_error": None if last_error is None else {
            "sync_id": last_error["sync_id"], "at": last_error["finished_at"],
            "message": {"untrusted_text": last_error["error_message"]}},
        "mode": MODE,
        "simulated": True,
    }
