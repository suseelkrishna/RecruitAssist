"""Build small hand-written databases for edge-case tests.

base() returns a minimal Northbeam dataset as {table: [row, ...]}. Tests add
rows with the helpers below, then build() writes a real SQLite file from
data/schema.sql so the app reads it exactly like the committed database.
AS_OF is a Monday, which keeps business-day cases easy to reason about.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = Path(__file__).resolve().parent.parent / "data" / "schema.sql"
AS_OF = "2026-11-09T17:00:00Z"
STAGES = ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer", "Hired"]


def job(job_id: str, team_id: str, status: str = "open", must_haves: str = '["Skill A", "Skill B"]',
        opened_at: str = "2026-10-01T17:00:00Z", closed_at: str | None = None, target: int = 30) -> dict:
    """One jobs row with sensible defaults."""
    return {"job_id": job_id, "req_code": f"REQ-{job_id}", "title": f"Title {job_id}", "team_id": team_id,
            "location": "Remote", "opened_at": opened_at, "closed_at": closed_at, "target_fill_days": target,
            "hiring_manager": "Manager", "status": status, "must_have_json": must_haves,
            "nice_to_have_json": "[]"}


def base() -> dict[str, list[dict[str, Any]]]:
    """Two teams, three users (admin, manager of TEAM-1, recruiter), and three open jobs.
    JOB-3 has no applications, so it is the empty role."""
    return {
        "company": [{"company_id": "CO-1", "name": "Northbeam Robotics", "about": "Fictional."}],
        "teams": [{"team_id": "TEAM-1", "name": "Engineering"}, {"team_id": "TEAM-2", "name": "People"}],
        "users": [
            {"user_id": "USR-1", "name": "Ada Admin", "email": "ada@example.com", "role": "admin"},
            {"user_id": "USR-2", "name": "Mo Manager", "email": "mo@example.com", "role": "hr_manager"},
            {"user_id": "USR-3", "name": "Rae Recruiter", "email": "rae@example.com", "role": "hr_user"},
        ],
        "manager_teams": [{"user_id": "USR-2", "team_id": "TEAM-1"}],
        "jobs": [job("JOB-1", "TEAM-1"), job("JOB-2", "TEAM-2"), job("JOB-3", "TEAM-1")],
        "job_assignments": [
            {"job_id": "JOB-1", "recruiter_user_id": "USR-3", "assigned_at": "2026-10-01T17:00:00Z"},
            {"job_id": "JOB-2", "recruiter_user_id": "USR-2", "assigned_at": "2026-10-01T17:00:00Z"},
            {"job_id": "JOB-3", "recruiter_user_id": "USR-3", "assigned_at": "2026-10-01T17:00:00Z"},
        ],
        "candidates": [], "applications": [], "stage_events": [], "interviews": [], "scorecards": [],
        "emails": [], "tasks": [], "source_syncs": [],
        "meta": [{"key": "as_of", "value": AS_OF}, {"key": "seed", "value": "0"}],
    }


def add_application(data: dict, app_id: str, job_id: str, stages: list[tuple[str, str, str | None, str | None]],
                    status: str = "active", reason: str | None = None, source: str = "LinkedIn",
                    cv_text: str = "CV text.") -> None:
    """Add a candidate, an application, and its stage events.

    stages is a list of (stage, entered_at, exited_at, exit_type). The last
    stage becomes current_stage. outcome_at is the last exit time for a
    closed application.
    """
    n = app_id.split("-")[1]
    data["candidates"].append({
        "candidate_id": f"CAN-{n}", "full_name": f"Person {n}", "email": f"person{n}@example.com",
        "phone": "555-0100", "location": "Remote", "source": source, "years_experience": 5,
        "current_title": "Engineer", "cv_text": cv_text})
    closed = None if status == "active" else max(s[2] or s[1] for s in stages)
    data["applications"].append({
        "application_id": app_id, "candidate_id": f"CAN-{n}", "job_id": job_id, "applied_at": stages[0][1],
        "current_stage": stages[-1][0], "status": status, "outcome_reason": reason, "outcome_at": closed})
    for stage, entered, exited, exit_type in stages:
        data["stage_events"].append({
            "event_id": f"EV-{n}-{STAGES.index(stage)}", "application_id": app_id, "stage": stage,
            "entered_at": entered, "exited_at": exited, "exit_type": exit_type})


def add_interview(data: dict, interview_id: str, app_id: str, stage: str, completed_at: str | None,
                  overall: str | None = None, ratings: str = '{"Skill A": 3, "Skill B": 3}',
                  submitted_at: str | None = None) -> None:
    """Add an interview and, when overall is given, its scorecard."""
    data["interviews"].append({"interview_id": interview_id, "application_id": app_id, "stage": stage,
                               "interviewer": "Ivy Interviewer", "scheduled_at": completed_at or AS_OF,
                               "completed_at": completed_at})
    if overall is not None:
        data["scorecards"].append({
            "scorecard_id": "SC-" + interview_id.split("-")[1], "interview_id": interview_id,
            "interviewer": "Ivy Interviewer", "submitted_at": submitted_at or completed_at,
            "overall": overall, "ratings_json": ratings, "notes": "Notes."})


def build(path: Path, data: dict[str, list[dict[str, Any]]]) -> Path:
    """Write data to a new SQLite file at path (replacing any old one), using the real schema."""
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text())
    for table, rows in data.items():
        for row in rows:
            cols = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            con.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
    con.commit()
    con.close()
    return path
