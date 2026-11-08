"""The small writable store that sits beside the read-only database.

It holds the append-only change log of recruiter reassignments. Entries live in
process memory, so they reset when the process restarts.
"""

from __future__ import annotations

from typing import Any

_change_log: list[dict[str, Any]] = []


def record_reassignment(job_id: str, recruiter_user_id: str, changed_by: str, changed_at: str) -> dict[str, Any]:
    """Append one reassignment to the change log and return the new entry."""
    entry = {
        "change_id": f"CHG-{len(_change_log) + 1:03d}",
        "job_id": job_id,
        "recruiter_user_id": recruiter_user_id,
        "changed_by": changed_by,
        "changed_at": changed_at,
    }
    _change_log.append(entry)
    return dict(entry)


def change_log() -> list[dict[str, Any]]:
    """Every change, oldest first, as copies so callers cannot edit the log."""
    return [dict(e) for e in _change_log]


def assignment_overrides() -> dict[str, str]:
    """The latest recruiter for each job that has been reassigned, keyed by job_id."""
    return {e["job_id"]: e["recruiter_user_id"] for e in _change_log}


def clear() -> None:
    """Empty the change log. Tests use this to start from the seed assignments."""
    _change_log.clear()
