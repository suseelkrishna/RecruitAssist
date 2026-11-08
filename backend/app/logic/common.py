"""Small helpers shared by the logic modules: stage order, time math, and scope checks."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app import db
from app.access import Principal

STAGES = ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer", "Hired"]
FMT = "%Y-%m-%dT%H:%M:%SZ"

# SQL fragment that keeps only rows whose job is in the principal's scope.
# Bind :allowed to db.id_list(principal.allowed_job_ids).
IN_SCOPE = "IN (SELECT value FROM json_each(:allowed))"


def resolve_as_of(as_of: str | None) -> str:
    """The as_of to use: the caller's value, or meta.as_of from the database."""
    return as_of or db.meta_as_of()


def parse_ts(ts: str) -> datetime:
    """Parse a stored UTC timestamp such as 2026-11-09T17:00:00Z."""
    return datetime.strptime(ts, FMT).replace(tzinfo=timezone.utc)


def format_ts(dt: datetime) -> str:
    """Format a datetime as a stored UTC timestamp."""
    return dt.astimezone(timezone.utc).strftime(FMT)


def days_between(start: str, end: str) -> float:
    """Days from start to end as a float (negative when end is earlier)."""
    return (parse_ts(end) - parse_ts(start)).total_seconds() / 86400


def add_business_days(ts: str, days: int) -> str:
    """ts moved forward by `days` weekdays, keeping the time of day. Saturdays and Sundays do not count."""
    dt = parse_ts(ts)
    added = 0
    while added < days:
        dt += timedelta(days=1)
        if dt.weekday() < 5:
            added += 1
    return format_ts(dt)


def median(values: list[float]) -> float | None:
    """The median rounded to one decimal, or None for an empty list."""
    return round(statistics.median(values), 1) if values else None


def pct(part: int, whole: int) -> float | None:
    """part / whole as a percent with one decimal, or None when whole is 0."""
    return round(100 * part / whole, 1) if whole else None


def plural(n: int, word: str) -> str:
    """'1 job' or '3 jobs': a count with its noun, adding s when the count is not 1."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def scope_params(principal: Principal, **extra: Any) -> dict[str, Any]:
    """Named SQL parameters with :allowed set to the principal's job IDs."""
    return {"allowed": db.id_list(principal.allowed_job_ids), **extra}


def out_of_scope(item_id: str) -> ToolError:
    """The one error for an ID the principal may not see. Unknown IDs get the same message,
    so the error never reveals whether the ID exists."""
    return ToolError(f"{item_id} is not in your scope")


def require_job(principal: Principal, job_id: str) -> dict[str, Any]:
    """The job row, or ToolError when the job is not in the principal's scope."""
    job = db.one(f"""SELECT j.*, t.name AS team FROM jobs j JOIN teams t ON t.team_id = j.team_id
                     WHERE j.job_id = :job AND j.job_id {IN_SCOPE}""",
                 scope_params(principal, job=job_id))
    if job is None:
        raise out_of_scope(job_id)
    return job


def require_application(principal: Principal, application_id: str) -> dict[str, Any]:
    """The application row with candidate fields, or ToolError when it is out of scope."""
    app = db.one(f"""SELECT a.*, c.full_name, c.email, c.phone, c.location, c.source,
                            c.years_experience, c.current_title, c.cv_text
                     FROM applications a JOIN candidates c ON c.candidate_id = a.candidate_id
                     WHERE a.application_id = :app AND a.job_id {IN_SCOPE}""",
                 scope_params(principal, app=application_id))
    if app is None:
        raise out_of_scope(application_id)
    return app
