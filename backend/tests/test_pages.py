"""The page data the recruiter UI reads: the jobs board, the job detail extras, the dashboard
filter choices, the day range, stage candidates, and the reassignment reason.

Expected values come from SQL written here or from hand-computed dates, separately from
app/logic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import recordings


def as_user(user_id: str) -> dict[str, str]:
    """Headers for a request made as this demo user."""
    return {"X-Demo-User": user_id}


@pytest.fixture
def client():
    """A TestClient with no model configured."""
    main.app.dependency_overrides.clear()
    yield TestClient(main.app, raise_server_exceptions=False)
    main.app.dependency_overrides.clear()


def active_by_job_and_stage(db, job_id: str) -> dict[str, int]:
    """Active applications on one job per current stage, from SQL."""
    rows = db.execute("SELECT current_stage, COUNT(*) FROM applications WHERE job_id = ? AND status = 'active' "
                      "GROUP BY current_stage", (job_id,))
    return {stage: n for stage, n in rows}


# Jobs board

def test_job_board_adds_hiring_manager_mini_funnel_and_overdue(client, db):
    body = client.get("/api/jobs", headers=as_user("USR-1")).json()
    assert body["count"] == db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    tasks = client.get("/api/tasks", headers=as_user("USR-1")).json()
    for job in body["jobs"]:
        manager = db.execute("SELECT hiring_manager FROM jobs WHERE job_id = ?", (job["job_id"],)).fetchone()[0]
        assert job["hiring_manager"] == manager
        counts = {s["stage"]: s["count"] for s in job["active_by_stage"] if s["count"]}
        assert counts == active_by_job_and_stage(db, job["job_id"])
        assert job["overdue_tasks"] == sum(1 for t in tasks["tasks"]
                                           if t["job_id"] == job["job_id"] and t["status"] == "overdue")
    assert sum(j["overdue_tasks"] for j in body["jobs"]) == tasks["overdue_count"]
    assert [t["team_id"] for t in body["teams"]] == sorted({j["team_id"] for j in body["jobs"]})


def test_job_board_marks_over_target_only_for_open_jobs(client, db):
    for job in client.get("/api/jobs", headers=as_user("USR-1")).json()["jobs"]:
        expected = job["status"] == "open" and job["days_open"] > job["target_fill_days"]
        assert job["over_target"] is expected


# Job detail

def test_job_detail_lists_every_active_candidate_ranked(client, db):
    body = client.get("/api/jobs/JOB-2", headers=as_user("USR-1")).json()
    active = db.execute("SELECT COUNT(*) FROM applications WHERE job_id = 'JOB-2' AND status = 'active'").fetchone()[0]
    assert body["candidate_pool"] == active == len(body["candidates"])
    assert [c["rank"] for c in body["candidates"]] == list(range(1, active + 1))
    scores = [c["score"] for c in body["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert [c["application_id"] for c in body["top_3"]] == [c["application_id"] for c in body["candidates"][:3]]
    assert set(body["top_3"][0]["components"]) == {"scorecards", "must_have", "stage"}


def test_job_detail_funnel_and_tasks_are_for_that_job(client, db):
    body = client.get("/api/jobs/JOB-3", headers=as_user("USR-1")).json()
    applied = db.execute("SELECT COUNT(*) FROM applications WHERE job_id = 'JOB-3'").fetchone()[0]
    assert body["funnel"][0]["stage"] == "Applied" and body["funnel"][0]["reached"] == applied
    assert body["tasks"] and all(t["job_id"] == "JOB-3" for t in body["tasks"])


def test_closed_job_has_no_candidates(client):
    body = client.get("/api/jobs/JOB-4", headers=as_user("USR-1")).json()
    assert body["candidates"] == [] and body["top_3"] == [] and body["candidate_pool"] == 0
    assert body["over_target"] is False


def test_job_detail_over_target_matches_the_board(client):
    board = {j["job_id"]: j["over_target"] for j in client.get("/api/jobs", headers=as_user("USR-1")).json()["jobs"]}
    for job_id, over in board.items():
        assert client.get(f"/api/jobs/{job_id}", headers=as_user("USR-1")).json()["over_target"] is over
    # JOB-1 opened 2026-07-07 with a 60 day target, so by 2026-11-09 it is over target.
    assert board["JOB-1"] is True


# Dashboard

def test_dashboard_day_range_sets_the_from_date(client):
    body = client.get("/api/dashboard?days=30", headers=as_user("USR-1")).json()
    # as_of is 2026-11-09T17:00:00Z; 30 days earlier is 2026-10-10.
    assert body["filters"] == {"days": 30, "date_from": "2026-10-10"}
    everything = client.get("/api/dashboard", headers=as_user("USR-1")).json()
    assert body["funnel"]["stages"][0]["reached"] < everything["funnel"]["stages"][0]["reached"]


def test_dashboard_day_range_rejects_other_values(client):
    assert client.get("/api/dashboard?days=45", headers=as_user("USR-1")).status_code == 400
    both = client.get("/api/dashboard?days=30&from=2026-01-01", headers=as_user("USR-1"))
    assert both.status_code == 400


def test_dashboard_options_follow_the_role(client, db):
    manager = client.get("/api/dashboard", headers=as_user("USR-2")).json()["options"]
    teams = {r[0] for r in db.execute("SELECT team_id FROM manager_teams WHERE user_id = 'USR-2'")}
    assert {t["team_id"] for t in manager["teams"]} == teams
    assert manager["recruiters"] and manager["range_days"] == [30, 90, 180]
    user = client.get("/api/dashboard", headers=as_user("USR-4")).json()["options"]
    assert user["recruiters"] == []
    assert {j["job_id"] for j in user["jobs"]} == {
        r[0] for r in db.execute("SELECT job_id FROM job_assignments WHERE recruiter_user_id = 'USR-4'")}


def test_dashboard_stage_candidates_match_active_applications(client, db):
    body = client.get("/api/dashboard", headers=as_user("USR-1")).json()
    rows = db.execute("SELECT current_stage, COUNT(*) FROM applications WHERE status = 'active' "
                      "GROUP BY current_stage")
    assert {s: len(c) for s, c in body["stage_candidates"].items()} == {s: n for s, n in rows}
    totals = {w["week_start"]: w["applicants"] for w in body["applicants_total"]["weeks"]}
    assert sum(totals.values()) == db.execute("SELECT COUNT(*) FROM applications").fetchone()[0]


# Reassignment reason and recording reason

def test_reassignment_records_the_reason(client):
    response = client.post("/api/jobs/JOB-2/assignment", headers=as_user("USR-1"),
                           json={"recruiter_user_id": "USR-4", "reason": "  Balancing load  "})
    assert response.status_code == 200
    change = client.get("/api/changes", headers=as_user("USR-1")).json()["changes"][0]
    assert change["reason"] == "Balancing load"
    long = client.post("/api/jobs/JOB-2/assignment", headers=as_user("USR-1"),
                       json={"recruiter_user_id": "USR-5", "reason": "x" * 301})
    assert long.status_code == 422


def test_reassignment_without_a_reason_stores_none(client):
    client.post("/api/jobs/JOB-2/assignment", headers=as_user("USR-1"), json={"recruiter_user_id": "USR-6"})
    assert client.get("/api/changes", headers=as_user("USR-1")).json()["changes"][0]["reason"] is None


def test_recorded_answer_says_why_it_was_used(client, tmp_path, monkeypatch):
    monkeypatch.setattr(recordings, "RECORDINGS", tmp_path / "recordings.json")
    recordings.save("How many jobs can I see?", "USR-4", None, ["JOB-1", "JOB-5", "JOB-7"],
                    {"answer": "Recorded.", "steps": [], "citations": [], "verified": True, "source": "live"},
                    "2026-11-09T00:00:00Z")
    main.app.dependency_overrides[main.model_client] = lambda: None
    body = client.post("/api/ask", headers=as_user("USR-4"), json={"question": "How many jobs can I see?"}).json()
    assert body["source"] == "recording" and body["recording_reason"] == "live_unavailable"


# Scope header

@pytest.mark.parametrize("user_id", ["USR-1", "USR-2", "USR-4"])
def test_me_summary_counts_jobs_candidates_and_overdue(client, db, user_id):
    body = client.get("/api/me", headers=as_user(user_id)).json()
    jobs = body["allowed_job_ids"]
    marks = ",".join("?" * len(jobs))
    active = db.execute(f"SELECT COUNT(*) FROM applications WHERE status = 'active' AND job_id IN ({marks})",
                        jobs).fetchone()[0]
    overdue = client.get("/api/tasks", headers=as_user(user_id)).json()["overdue_count"]
    assert body["summary"] == {"jobs": len(jobs), "active_candidates": active, "overdue_tasks": overdue}
