"""What the current user can see: the jobs in scope and a compact scope card for the agent."""

from __future__ import annotations

from typing import Any

from app import db
from app.access import Principal, current_recruiters
from app.logic.common import IN_SCOPE, STAGES, days_between, require_job, resolve_as_of, scope_params
from app.logic.tasks import pending_tasks


def list_jobs(principal: Principal, as_of: str | None = None) -> dict[str, Any]:
    """Every job in scope with team, status, recruiter, days open, target, and active applications,
    plus the total of active applications across them, so an answer never has to add them up."""
    as_of = resolve_as_of(as_of)
    jobs = db.rows(f"""
        SELECT j.job_id, j.req_code, j.title, t.team_id, t.name AS team, j.location, j.status,
               j.opened_at, j.closed_at, j.target_fill_days,
               (SELECT COUNT(*) FROM applications a
                WHERE a.job_id = j.job_id AND a.status = 'active') AS active_applications
        FROM jobs j JOIN teams t ON t.team_id = j.team_id
        WHERE j.job_id {IN_SCOPE} ORDER BY j.job_id""", scope_params(principal))
    recruiters = current_recruiters()
    users = {u["user_id"]: u["name"] for u in db.rows("SELECT user_id, name FROM users")}
    for job in jobs:
        job["days_open"] = round(days_between(job["opened_at"], job["closed_at"] or as_of), 1)
        job["recruiter_user_id"] = recruiters.get(job["job_id"])
        job["recruiter_name"] = users.get(job["recruiter_user_id"])
    return {"as_of": as_of, "count": len(jobs), "jobs": jobs,
            "active_applications_total": sum(j["active_applications"] for j in jobs)}


def scope_card(principal: Principal, job_id: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    """A compact summary for the agent's context: jobs in scope with stage counts, active
    candidates per job, and the number of overdue items. Limit to one job with job_id."""
    as_of = resolve_as_of(as_of)
    if job_id is not None:
        require_job(principal, job_id)
    params = scope_params(principal, job=job_id)
    jobs = db.rows(f"""SELECT job_id, title, status, opened_at, closed_at FROM jobs
                       WHERE job_id {IN_SCOPE} AND (:job IS NULL OR job_id = :job)
                       ORDER BY job_id""", params)
    active = db.rows(f"""
        SELECT a.job_id, a.application_id, c.full_name, a.current_stage
        FROM applications a JOIN candidates c ON c.candidate_id = a.candidate_id
        WHERE a.job_id {IN_SCOPE} AND (:job IS NULL OR a.job_id = :job) AND a.status = 'active'
        ORDER BY a.application_id""", params)
    cards = []
    for job in jobs:
        mine = [a for a in active if a["job_id"] == job["job_id"]]
        cards.append({
            "job_id": job["job_id"],
            "title": job["title"],
            "status": job["status"],
            "days_open": round(days_between(job["opened_at"], job["closed_at"] or as_of), 1),
            "active_by_stage": {s: n for s in STAGES if (n := sum(1 for a in mine if a["current_stage"] == s))},
            "active_candidates": [[a["application_id"], a["full_name"]] for a in mine],
        })
    overdue = pending_tasks(principal, job_id=job_id, as_of=as_of)["overdue_count"]
    return {"as_of": as_of, "role": principal.role, "jobs": cards,
            "active_candidates_total": sum(len(c["active_candidates"]) for c in cards), "overdue_items": overdue,
            "note": "active_candidates lists [application_id, name] for active applications only."}


def job_board(principal: Principal, as_of: str | None = None) -> dict[str, Any]:
    """The jobs page: every job in scope with its hiring manager, active candidates per stage
    for the mini funnel, and overdue tasks, plus the team and recruiter choices for its filters.
    The agent's list_jobs tool stays compact; this adds what the table shows."""
    listed = list_jobs(principal, as_of)
    params = scope_params(principal)
    managers = {r["job_id"]: r["hiring_manager"] for r in db.rows(
        f"SELECT job_id, hiring_manager FROM jobs WHERE job_id {IN_SCOPE}", params)}
    stage_rows = db.rows(f"""
        SELECT job_id, current_stage, COUNT(*) AS n FROM applications
        WHERE job_id {IN_SCOPE} AND status = 'active' GROUP BY job_id, current_stage""", params)
    overdue = [t for t in pending_tasks(principal, as_of=listed["as_of"])["tasks"] if t["status"] == "overdue"]
    for job in listed["jobs"]:
        counts = {r["current_stage"]: r["n"] for r in stage_rows if r["job_id"] == job["job_id"]}
        job["hiring_manager"] = managers[job["job_id"]]
        job["active_by_stage"] = [{"stage": s, "count": counts.get(s, 0)} for s in STAGES if s != "Hired"]
        job["overdue_tasks"] = sum(1 for t in overdue if t["job_id"] == job["job_id"])
        job["over_target"] = job["status"] == "open" and job["days_open"] > job["target_fill_days"]
    teams = sorted({(j["team_id"], j["team"]) for j in listed["jobs"]})
    recruiters = sorted({(j["recruiter_user_id"], j["recruiter_name"]) for j in listed["jobs"]
                         if j["recruiter_user_id"]})
    return {**listed,
            "teams": [{"team_id": t, "name": n} for t, n in teams],
            "recruiters": [{"user_id": u, "name": n} for u, n in recruiters]}


def scope_summary(card: dict[str, Any]) -> dict[str, int]:
    """The three counts in the app's scope header, from a scope card: jobs in scope, active
    candidates across them, and overdue tasks."""
    return {"jobs": len(card["jobs"]),
            "active_candidates": sum(len(j["active_candidates"]) for j in card["jobs"]),
            "overdue_tasks": card["overdue_items"]}
