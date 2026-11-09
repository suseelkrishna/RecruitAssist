"""The catch-up view: a greeting, one line on what needs attention, and a few headline tiles.

It reuses the dashboard's own functions (kpis, days_open_vs_target) and the task list, so the
catch-up page and the full dashboard always show the same numbers. It covers the user's whole
scope with no filters.
"""

from __future__ import annotations

from typing import Any

from app import db
from app.access import Principal
from app.logic.analytics import days_open_vs_target, kpis
from app.logic.common import plural, resolve_as_of
from app.logic.tasks import pending_tasks

# How many overdue tasks the catch-up page lists before pointing to the tasks page.
OVERDUE_PREVIEW = 5


def join_words(parts: list[str]) -> str:
    """'a', 'a and b', or 'a, b, and c'."""
    if len(parts) <= 1:
        return "".join(parts)
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def scope_phrase(principal: Principal, job_count: int) -> str:
    """Where the summary looks, in the words of the user's role."""
    if principal.role == "admin":
        return f"Across all {plural(job_count, 'job')}"
    if principal.role == "hr_manager":
        names = [r["name"] for r in db.rows(
            f"SELECT name FROM teams WHERE team_id IN ({','.join('?' * len(principal.team_ids))}) ORDER BY name",
            tuple(sorted(principal.team_ids)))] if principal.team_ids else []
        teams = f"{join_words(names)} {'team' if len(names) == 1 else 'teams'}"
        return f"On your {teams} ({plural(job_count, 'job')})"
    return f"On the {plural(job_count, 'job')} you recruit for"


def catch_up(principal: Principal, as_of: str | None = None) -> dict[str, Any]:
    """First name, a one-line summary of what needs attention, headline tiles, and a short
    list of the most overdue tasks, for the user's whole scope."""
    as_of = resolve_as_of(as_of)
    k = kpis(principal, as_of=as_of)
    days = days_open_vs_target(principal, as_of=as_of)
    tasks = pending_tasks(principal, as_of=as_of)
    overdue = [t for t in tasks["tasks"] if t["status"] == "overdue"]
    past_target = sum(1 for j in days["jobs"] if j["over_target"])
    job_count = len(principal.allowed_job_ids)

    if job_count == 0:
        summary = "You have no jobs in your scope right now."
    else:
        parts = []
        if overdue:
            parts.append(plural(len(overdue), "overdue task"))
        if past_target:
            parts.append(f"{plural(past_target, 'job')} past target")
        if k["offers_out"]:
            parts.append(f"{plural(k['offers_out'], 'offer')} waiting on an answer")
        need = join_words(parts) if parts else "nothing is overdue or past target"
        summary = f"{scope_phrase(principal, job_count)}: {need}."

    tiles = [
        {"key": "overdue_tasks", "label": "Overdue tasks", "value": len(overdue),
         "note": f"of {plural(tasks['count'], 'open task')}"},
        {"key": "jobs_past_target", "label": "Jobs past target", "value": past_target,
         "note": f"of {plural(len(days['jobs']), 'open job')}"},
        {"key": "active_candidates", "label": "Active candidates", "value": k["active_candidates"],
         "note": f"across {plural(job_count, 'job')} in your scope"},
        {"key": "new_applicants_7d", "label": "New applicants", "value": k["new_applicants_7d"],
         "note": "in the last 7 days"},
        {"key": "offers_out", "label": "Offers out", "value": k["offers_out"],
         "note": "waiting on an answer"},
    ]
    preview = [{"task_id": t.get("task_id"), "application_id": t.get("application_id"), "job_id": t["job_id"],
                "title": t["title"], "owner_name": t["owner_name"], "days_overdue": t["days_overdue"]}
               for t in overdue[:OVERDUE_PREVIEW]]
    return {
        "as_of": as_of,
        "first_name": principal.name.split()[0],
        "role": principal.role,
        "summary": summary,
        "tiles": tiles,
        "overdue_tasks": preview,
        "overdue_more": max(0, len(overdue) - OVERDUE_PREVIEW),
    }
