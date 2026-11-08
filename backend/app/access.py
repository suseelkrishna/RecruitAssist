"""Who the current user is, and which jobs they may see.

The backend turns the X-Demo-User ID into a Principal and stores it in
current_principal for the request. Logic functions filter by allowed_job_ids
in SQL. The principal is never a tool argument.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from app import db, store


@dataclass(frozen=True)
class Principal:
    """A user and the job and team IDs their role lets them see."""

    user_id: str
    name: str
    role: str
    allowed_job_ids: frozenset[str]
    team_ids: frozenset[str]


current_principal: ContextVar[Principal] = ContextVar("current_principal")


def current_recruiters() -> dict[str, str]:
    """Each job's recruiter: the seed assignment, overlaid with reassignments in the store."""
    seed = {r["job_id"]: r["recruiter_user_id"]
            for r in db.rows("SELECT job_id, recruiter_user_id FROM job_assignments")}
    return seed | store.get_assignment_overrides()


def demo_users() -> list[dict[str, str]]:
    """Every demo user for the user switcher: ID, name, and role. No emails."""
    return db.rows("SELECT user_id, name, role FROM users ORDER BY user_id")


def principal_for(user_id: str) -> Principal:
    """Build the Principal for a user ID. admin sees all jobs, hr_manager their teams' jobs,
    hr_user the jobs currently assigned to them."""
    user = db.one("SELECT user_id, name, role FROM users WHERE user_id = ?", (user_id,))
    if user is None:
        valid = ", ".join(r["user_id"] for r in db.rows("SELECT user_id FROM users ORDER BY user_id"))
        raise LookupError(f"Unknown user {user_id!r}. Valid users: {valid}.")
    jobs = db.rows("SELECT job_id, team_id FROM jobs")
    if user["role"] == "admin":
        allowed = {j["job_id"] for j in jobs}
    elif user["role"] == "hr_manager":
        teams = {r["team_id"] for r in db.rows(
            "SELECT team_id FROM manager_teams WHERE user_id = ?", (user_id,))}
        allowed = {j["job_id"] for j in jobs if j["team_id"] in teams}
    else:
        recruiters = current_recruiters()
        allowed = {j["job_id"] for j in jobs if recruiters.get(j["job_id"]) == user_id}
    team_ids = {j["team_id"] for j in jobs if j["job_id"] in allowed}
    if user["role"] == "hr_manager":
        team_ids |= teams
    return Principal(user["user_id"], user["name"], user["role"], frozenset(allowed), frozenset(team_ids))
