"""The catch-up page data: greeting, one-line summary, headline tiles, and the overdue preview.

Expected counts come from SQL written here, separately from app/logic, plus a few
hand-written summary lines.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main


def as_user(user_id: str) -> dict[str, str]:
    """Headers for a request made as this demo user."""
    return {"X-Demo-User": user_id}


@pytest.fixture
def client():
    """A TestClient with no model configured."""
    main.app.dependency_overrides.clear()
    yield TestClient(main.app, raise_server_exceptions=False)
    main.app.dependency_overrides.clear()


def scope_jobs(db, user_id: str) -> list[str]:
    """The job IDs a demo user may see, from SQL: all for admin, team jobs for a manager,
    assigned jobs for an HR user."""
    role = db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    if role == "admin":
        sql, args = "SELECT job_id FROM jobs", ()
    elif role == "hr_manager":
        sql = ("SELECT j.job_id FROM jobs j JOIN manager_teams mt ON mt.team_id = j.team_id "
               "WHERE mt.user_id = ?")
        args = (user_id,)
    else:
        sql, args = "SELECT job_id FROM job_assignments WHERE recruiter_user_id = ?", (user_id,)
    return sorted(r[0] for r in db.execute(sql, args))


def tiles(body: dict) -> dict[str, int]:
    """Tile values by key."""
    return {t["key"]: t["value"] for t in body["tiles"]}


@pytest.mark.parametrize("user_id,first", [("USR-1", "Suseel"), ("USR-2", "Priya"), ("USR-3", "Daniel"),
                                           ("USR-4", "Sam"), ("USR-5", "Alex"), ("USR-6", "Jordan")])
def test_catch_up_greets_by_first_name(client, user_id, first):
    body = client.get("/api/catch-up", headers=as_user(user_id)).json()
    assert body["first_name"] == first


@pytest.mark.parametrize("user_id", ["USR-1", "USR-2", "USR-3", "USR-4", "USR-5", "USR-6"])
def test_catch_up_tiles_match_sql_for_the_users_scope(client, db, as_of, user_id):
    jobs = scope_jobs(db, user_id)
    marks = ",".join("?" * len(jobs))
    active = db.execute(f"SELECT COUNT(*) FROM applications WHERE status = 'active' AND job_id IN ({marks})",
                        jobs).fetchone()[0]
    offers = db.execute(f"SELECT COUNT(*) FROM applications WHERE status = 'active' AND current_stage = 'Offer' "
                        f"AND job_id IN ({marks})", jobs).fetchone()[0]
    past = db.execute(f"SELECT COUNT(*) FROM jobs WHERE status = 'open' AND job_id IN ({marks}) "
                      "AND julianday(?) - julianday(opened_at) > target_fill_days", (*jobs, as_of)).fetchone()[0]
    body = client.get("/api/catch-up", headers=as_user(user_id)).json()
    overdue = client.get("/api/tasks", headers=as_user(user_id)).json()["overdue_count"]
    assert tiles(body) == {"overdue_tasks": overdue, "jobs_past_target": past, "active_candidates": active,
                           "new_applicants_7d": tiles(body)["new_applicants_7d"], "offers_out": offers}
    assert {t["job_id"] for t in body["overdue_tasks"]} <= set(jobs)
    assert len(body["overdue_tasks"]) + body["overdue_more"] == overdue


def test_catch_up_new_applicants_match_sql(client, db, as_of):
    week_ago = db.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', ?, '-7 days')", (as_of,)).fetchone()[0]
    expected = db.execute("SELECT COUNT(*) FROM applications WHERE applied_at > ? AND applied_at <= ?",
                          (week_ago, as_of)).fetchone()[0]
    assert tiles(client.get("/api/catch-up", headers=as_user("USR-1")).json())["new_applicants_7d"] == expected


def test_catch_up_summary_names_the_scope_for_each_role(client):
    lines = {u: client.get("/api/catch-up", headers=as_user(u)).json()["summary"] for u in ("USR-1", "USR-2", "USR-5")}
    assert lines["USR-1"] == "Across all 7 jobs: 8 overdue tasks, 3 jobs past target, and 2 offers waiting on an answer."
    assert lines["USR-2"] == ("On your Engineering and Manufacturing teams (4 jobs): 4 overdue tasks, "
                              "2 jobs past target, and 1 offer waiting on an answer.")
    assert lines["USR-5"] == "On the 2 jobs you recruit for: 1 overdue task and 1 job past target."


def test_catch_up_preview_lists_the_most_overdue_first(client):
    body = client.get("/api/catch-up", headers=as_user("USR-1")).json()
    days = [t["days_overdue"] for t in body["overdue_tasks"]]
    assert len(days) == 5 and days == sorted(days, reverse=True)


def test_catch_up_needs_a_demo_user(client):
    assert client.get("/api/catch-up").status_code == 401
