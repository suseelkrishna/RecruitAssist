"""One job's detail page data and the only write in the app: reassigning a job's recruiter.

The backend decides who may reassign, so the UI only shows what can_reassign
and reassign_options say. admin may reassign any job. An hr_manager may
reassign jobs on the teams they manage. hr_user may not reassign. A job can
only be given to a recruiter (a user with the hr_user role). Every
reassignment is recorded in the append-only change log.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app import db, store
from app.access import Principal, current_recruiters
from app.logic.common import NotAllowedError, require_job
from app.logic.scope import list_jobs


def recruiters() -> list[dict[str, Any]]:
    """Every user a job may be assigned to: the hr_user role, by user_id."""
    return db.rows("SELECT user_id, name FROM users WHERE role = 'hr_user' ORDER BY user_id")


def can_reassign(principal: Principal, team_id: str) -> bool:
    """True when the principal may reassign jobs on this team."""
    if principal.role == "admin":
        return True
    if principal.role == "hr_manager":
        return db.one("SELECT 1 AS ok FROM manager_teams WHERE user_id = ? AND team_id = ?",
                      (principal.user_id, team_id)) is not None
    return False


def job_detail(principal: Principal, job_id: str, as_of: str | None = None) -> dict[str, Any]:
    """One in-scope job with its recruiter, must-haves, whether the principal may reassign it,
    and the recruiters it may be reassigned to."""
    job = require_job(principal, job_id)
    listed = next(j for j in list_jobs(principal, as_of)["jobs"] if j["job_id"] == job_id)
    allowed = can_reassign(principal, job["team_id"])
    options = [r for r in recruiters() if r["user_id"] != listed["recruiter_user_id"]] if allowed else []
    return {
        **listed,
        "hiring_manager": job["hiring_manager"],
        "must_haves": json.loads(job["must_have_json"]),
        "nice_to_haves": json.loads(job["nice_to_have_json"]),
        "can_reassign": allowed,
        "reassign_options": options,
    }


def reassign(principal: Principal, job_id: str, recruiter_user_id: str) -> dict[str, Any]:
    """Give the job to another recruiter, log who changed it and from whom to whom, and
    return the updated job detail."""
    job = require_job(principal, job_id)
    if not can_reassign(principal, job["team_id"]):
        raise NotAllowedError(f"Your role cannot reassign {job_id}. admin can reassign any job; "
                              "an HR Manager can reassign jobs on their own teams.")
    valid = [r["user_id"] for r in recruiters()]
    if recruiter_user_id not in valid:
        raise ToolError(f"{recruiter_user_id} is not a recruiter. Valid recruiters: {', '.join(valid)}.")
    previous = current_recruiters().get(job_id)
    if previous == recruiter_user_id:
        raise ToolError(f"{job_id} is already assigned to {recruiter_user_id}.")
    store.set_assignment(job_id, recruiter_user_id, principal.user_id)
    store.append_change({"type": "reassignment", "job_id": job_id, "user_id": principal.user_id,
                         "from_recruiter_user_id": previous, "to_recruiter_user_id": recruiter_user_id})
    return job_detail(principal, job_id)
