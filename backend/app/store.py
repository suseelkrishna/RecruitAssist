"""The only writable storage: recruiter assignment overrides, the change log, and rate limits.

When UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are set, data lives in
Upstash Redis and survives restarts and multiple server instances. Otherwise it
lives in process memory and resets when the process restarts. The read-only
SQLite database is never written; this store sits beside it.

The change log is append-only: there is no function to edit or delete an entry.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.access import Principal

PREFIX = "recruitassist:"
TIMEOUT_SECONDS = 5

_assignments: dict[str, dict[str, Any]] = {}
_changes: list[dict[str, Any]] = []
_hits: dict[str, int] = {}


def backend() -> str:
    """'redis' when the Upstash variables are set, otherwise 'memory'."""
    return "redis" if os.environ.get("UPSTASH_REDIS_REST_URL") else "memory"


def redis(*command: Any) -> Any:
    """Run one Redis command through the Upstash REST API and return its result."""
    request = urllib.request.Request(
        os.environ["UPSTASH_REDIS_REST_URL"],
        data=json.dumps([str(part) for part in command]).encode(),
        headers={"Authorization": f"Bearer {os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read())["result"]


def get_assignment_overrides() -> dict[str, str]:
    """The current recruiter for every job that has been reassigned, keyed by job_id."""
    if backend() == "redis":
        flat = redis("HGETALL", PREFIX + "assignments") or []
        stored = {flat[i]: json.loads(flat[i + 1]) for i in range(0, len(flat), 2)}
    else:
        stored = _assignments
    return {job_id: value["recruiter_user_id"] for job_id, value in stored.items()}


def set_assignment(job_id: str, recruiter_id: str, by_user_id: str) -> None:
    """Make recruiter_id the job's recruiter, replacing the seed assignment and earlier overrides."""
    value = {"recruiter_user_id": recruiter_id, "by_user_id": by_user_id, "at": now()}
    if backend() == "redis":
        redis("HSET", PREFIX + "assignments", job_id, json.dumps(value))
    else:
        _assignments[job_id] = value


def append_change(event: dict[str, Any]) -> dict[str, Any]:
    """Add one event to the change log with the next change_id (CHG-001, ...) and return it."""
    if backend() == "redis":
        number = redis("INCR", PREFIX + "changes:seq")
    else:
        number = len(_changes) + 1
    entry = {"change_id": f"CHG-{number:03d}", "at": now(), **event}
    if backend() == "redis":
        redis("RPUSH", PREFIX + "changes", json.dumps(entry))
    else:
        _changes.append(entry)
    return dict(entry)


def all_changes() -> list[dict[str, Any]]:
    """Every change event, oldest first, as copies so callers cannot edit the log."""
    if backend() == "redis":
        return [json.loads(raw) for raw in redis("LRANGE", PREFIX + "changes", 0, -1) or []]
    return [dict(entry) for entry in _changes]


def list_changes(principal: Principal) -> list[dict[str, Any]]:
    """The change events this principal may see, newest first.

    admin sees every event. Everyone else sees events about jobs in their scope
    (their teams' jobs for hr_manager, their own jobs for hr_user), events they
    made themselves, and reassignments that moved a job to or from them.
    """
    changes = all_changes()
    if principal.role != "admin":
        me = principal.user_id
        changes = [c for c in changes
                   if c.get("job_id") in principal.allowed_job_ids or c.get("user_id") == me
                   or me in (c.get("from_recruiter_user_id"), c.get("to_recruiter_user_id"))]
    return list(reversed(changes))


def hit_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Count one hit for key in the current fixed time window. True when this hit is over the limit."""
    bucket = f"{PREFIX}rate:{key}:{int(time.time() // window_seconds)}"
    if backend() == "redis":
        count = redis("INCR", bucket)
        if count == 1:
            redis("EXPIRE", bucket, window_seconds)
    else:
        count = _hits.get(bucket, 0) + 1
        _hits[bucket] = count
    return count > limit


def ping() -> dict[str, Any]:
    """A live check of the store for the sources page: which backend and whether it answers."""
    if backend() == "memory":
        return {"name": "Store", "status": "ok", "backend": "memory",
                "note": "In-memory store: changes reset when the server restarts."}
    try:
        ok = redis("PING") == "PONG"
    except OSError as error:
        return {"name": "Store", "status": "error", "backend": "redis", "error": type(error).__name__}
    return {"name": "Store", "status": "ok" if ok else "error", "backend": "redis"}


def now() -> str:
    """The current UTC time as a stored timestamp, for example 2026-11-09T17:00:00Z."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clear() -> None:
    """Empty the in-memory store. Tests use this to start from the seed assignments."""
    _assignments.clear()
    _changes.clear()
    _hits.clear()
