"""Principal construction: each role's job scope, checked against SQL written here."""

from __future__ import annotations

import pytest

from app import access, store


def expected_jobs(db, user_id: str) -> set[str]:
    """The job IDs a user may see, from one SQL query per role."""
    role = db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    if role == "admin":
        sql, params = "SELECT job_id FROM jobs", ()
    elif role == "hr_manager":
        sql = "SELECT j.job_id FROM jobs j JOIN manager_teams m ON m.team_id = j.team_id WHERE m.user_id = ?"
        params = (user_id,)
    else:
        sql, params = "SELECT job_id FROM job_assignments WHERE recruiter_user_id = ?", (user_id,)
    return {r[0] for r in db.execute(sql, params)}


@pytest.mark.parametrize("user_id", ["USR-1", "USR-2", "USR-3", "USR-4", "USR-5", "USR-6"])
def test_allowed_jobs_match_sql(db, user_id):
    principal = access.principal_for(user_id)
    assert principal.allowed_job_ids == expected_jobs(db, user_id)
    name, role = db.execute("SELECT name, role FROM users WHERE user_id = ?", (user_id,)).fetchone()
    assert (principal.user_id, principal.name, principal.role) == (user_id, name, role)


def test_known_scopes_by_hand():
    assert access.principal_for("USR-1").allowed_job_ids == {f"JOB-{n}" for n in range(1, 8)}
    assert access.principal_for("USR-2").allowed_job_ids == {"JOB-1", "JOB-2", "JOB-4", "JOB-5"}
    assert access.principal_for("USR-3").allowed_job_ids == {"JOB-3", "JOB-6", "JOB-7"}
    assert access.principal_for("USR-4").allowed_job_ids == {"JOB-1", "JOB-5", "JOB-7"}
    assert access.principal_for("USR-2").team_ids == {"TEAM-1", "TEAM-2"}


def test_reassignment_in_store_moves_the_job_between_hr_users():
    store.record_reassignment("JOB-1", "USR-5", changed_by="USR-1", changed_at="2026-11-09T12:00:00Z")
    assert "JOB-1" not in access.principal_for("USR-4").allowed_job_ids
    assert "JOB-1" in access.principal_for("USR-5").allowed_job_ids
    assert access.current_recruiters()["JOB-1"] == "USR-5"
    # Managers and admins keep the same scope: theirs does not depend on assignments.
    assert "JOB-1" in access.principal_for("USR-2").allowed_job_ids


def test_latest_reassignment_wins():
    store.record_reassignment("JOB-1", "USR-5", "USR-1", "2026-11-09T12:00:00Z")
    store.record_reassignment("JOB-1", "USR-6", "USR-1", "2026-11-09T13:00:00Z")
    assert access.current_recruiters()["JOB-1"] == "USR-6"
    assert [c["change_id"] for c in store.change_log()] == ["CHG-001", "CHG-002"]


def test_unknown_user_lists_valid_users():
    with pytest.raises(LookupError, match=r"Unknown user 'USR-99'\. Valid users: USR-1, USR-2"):
        access.principal_for("USR-99")
