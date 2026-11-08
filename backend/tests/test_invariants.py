"""Invariants the generated database must satisfy.

These checks use their own SQL and Python against the committed database and
do not reuse the generator's code, except for regenerating the database to
confirm the output is reproducible.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict

from data import generate

STAGES = ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer", "Hired"]
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Columns that hold a moment in time. tasks.due_at is left out on purpose: an
# open task that is not yet due has a due date after AS_OF.
TIME_COLUMNS = {
    "jobs": ["opened_at", "closed_at"],
    "job_assignments": ["assigned_at"],
    "applications": ["applied_at", "outcome_at"],
    "stage_events": ["entered_at", "exited_at"],
    "interviews": ["scheduled_at", "completed_at"],
    "scorecards": ["submitted_at"],
    "emails": ["sent_at"],
    "tasks": ["created_at", "completed_at"],
    "source_syncs": ["started_at", "finished_at"],
}


def events_by_application(db) -> dict[str, list[sqlite3.Row]]:
    """Every application's stage events, in entry order."""
    grouped = defaultdict(list)
    for row in db.execute("SELECT * FROM stage_events ORDER BY application_id, entered_at"):
        grouped[row["application_id"]].append(row)
    return grouped


def test_stage_events_are_contiguous_and_ordered(db):
    apps = {r["application_id"]: r for r in db.execute("SELECT * FROM applications")}
    events = events_by_application(db)
    assert set(events) == set(apps)
    for app_id, evs in events.items():
        app = apps[app_id]
        assert [e["stage"] for e in evs] == STAGES[: len(evs)], app_id
        assert evs[0]["entered_at"] == app["applied_at"], app_id
        assert evs[-1]["stage"] == app["current_stage"], app_id
        for prev, nxt in zip(evs, evs[1:]):
            assert prev["exited_at"] == nxt["entered_at"], app_id
            assert prev["exit_type"] == "advanced", app_id
        for e in evs:
            assert e["exited_at"] is None or e["entered_at"] <= e["exited_at"], app_id


def test_active_has_one_open_event_and_closed_have_none(db):
    rows = db.execute(
        """SELECT a.application_id, a.status, SUM(e.exited_at IS NULL) AS open_events
           FROM applications a JOIN stage_events e ON e.application_id = a.application_id
           GROUP BY a.application_id""").fetchall()
    for r in rows:
        expected = 1 if r["status"] == "active" else 0
        assert r["open_events"] == expected, r["application_id"]


def test_closed_applications_end_with_their_outcome(db):
    rows = db.execute(
        """SELECT a.application_id, a.status, a.outcome_at, e.stage, e.exited_at, e.exit_type
           FROM applications a
           JOIN stage_events e ON e.application_id = a.application_id
                              AND e.stage = a.current_stage
           WHERE a.status != 'active'""").fetchall()
    assert rows
    for r in rows:
        assert r["exited_at"] == r["outcome_at"], r["application_id"]
        if r["status"] == "hired":
            assert (r["stage"], r["exit_type"]) == ("Hired", None), r["application_id"]
        else:
            assert r["exit_type"] == r["status"], r["application_id"]


def test_no_event_falls_after_outcome(db):
    late = db.execute(
        """SELECT COUNT(*) FROM stage_events e
           JOIN applications a ON a.application_id = e.application_id
           WHERE a.outcome_at IS NOT NULL
             AND (e.entered_at > a.outcome_at OR e.exited_at > a.outcome_at)""").fetchone()[0]
    assert late == 0


def test_scorecards_exist_only_for_completed_interviews(db):
    rows = db.execute(
        """SELECT s.scorecard_id, i.completed_at, s.submitted_at, s.interviewer, i.interviewer
           FROM scorecards s JOIN interviews i ON i.interview_id = s.interview_id""").fetchall()
    assert rows
    for r in rows:
        assert r[1] is not None, r[0]
        assert r[2] >= r[1], r[0]
        assert r[3] == r[4], r[0]


def test_interviews_happen_inside_their_stage(db):
    rows = db.execute(
        """SELECT i.interview_id, i.scheduled_at, i.completed_at, e.entered_at, e.exited_at
           FROM interviews i
           LEFT JOIN stage_events e ON e.application_id = i.application_id
                                   AND e.stage = i.stage""").fetchall()
    for r in rows:
        assert r["entered_at"] is not None, f"{r['interview_id']} is for a stage never reached"
        assert r["entered_at"] <= r["scheduled_at"] <= r["completed_at"], r["interview_id"]
        assert r["exited_at"] is None or r["completed_at"] <= r["exited_at"], r["interview_id"]


def test_all_foreign_keys_are_valid(db):
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_all_timestamps_are_well_formed_and_at_or_before_as_of(db, as_of):
    for table, columns in TIME_COLUMNS.items():
        for column in columns:
            for (value,) in db.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"):
                assert TS_RE.match(value), (table, column, value)
                assert value <= as_of, (table, column, value)
    for (value,) in db.execute("SELECT due_at FROM tasks"):
        assert TS_RE.match(value), value


def test_all_email_addresses_use_example_com(db):
    addresses = [r[0] for r in db.execute(
        "SELECT email FROM candidates UNION ALL SELECT email FROM users "
        "UNION ALL SELECT sender FROM emails")]
    assert addresses
    for address in addresses:
        assert address.endswith("@example.com"), address
    # Any address written inside free text must also be on example.com.
    texts = [r[0] for r in db.execute(
        "SELECT cv_text FROM candidates UNION ALL SELECT body FROM emails")]
    for text in texts:
        for found in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text):
            assert found.endswith("@example.com"), found


def test_phone_numbers_use_555_01xx(db):
    for (phone,) in db.execute("SELECT phone FROM candidates"):
        assert re.fullmatch(r"\+1-\d{3}-555-01\d{2}", phone), phone


def test_every_job_has_one_recruiter(db):
    rows = db.execute(
        """SELECT j.job_id, COUNT(ja.job_id) AS recruiters, MAX(u.role) AS role
           FROM jobs j
           LEFT JOIN job_assignments ja ON ja.job_id = j.job_id
           LEFT JOIN users u ON u.user_id = ja.recruiter_user_id
           GROUP BY j.job_id""").fetchall()
    assert len(rows) == 7
    for r in rows:
        assert (r["recruiters"], r["role"]) == (1, "hr_user"), r["job_id"]


def test_every_team_has_one_manager(db):
    rows = db.execute(
        """SELECT t.name, COUNT(mt.user_id) AS managers, MAX(u.role) AS role
           FROM teams t
           LEFT JOIN manager_teams mt ON mt.team_id = t.team_id
           LEFT JOIN users u ON u.user_id = mt.user_id
           GROUP BY t.team_id""").fetchall()
    for r in rows:
        assert (r["managers"], r["role"]) == (1, "hr_manager"), r["name"]


def test_users_and_roles(db):
    users = {r["name"]: r["role"] for r in db.execute("SELECT name, role FROM users")}
    assert users == {
        "Morgan Lee": "admin", "Priya Raman": "hr_manager", "Daniel Okafor": "hr_manager",
        "Sam Rivera": "hr_user", "Alex Chen": "hr_user", "Jordan Patel": "hr_user",
    }
    teams = {(r[0], r[1]) for r in db.execute(
        """SELECT u.name, t.name FROM manager_teams mt
           JOIN users u ON u.user_id = mt.user_id JOIN teams t ON t.team_id = mt.team_id""")}
    assert teams == {("Priya Raman", "Engineering"), ("Priya Raman", "Manufacturing"),
                     ("Daniel Okafor", "People"), ("Daniel Okafor", "Operations")}


def test_each_recruiter_sees_a_different_set_of_jobs(db):
    scopes = defaultdict(set)
    for user, job in db.execute("SELECT recruiter_user_id, job_id FROM job_assignments"):
        scopes[user].add(job)
    assert len(scopes) == 3
    assert len({frozenset(s) for s in scopes.values()}) == 3


def test_data_size_matches_the_spec(db):
    active = dict(db.execute(
        """SELECT j.title, COUNT(*) FROM applications a JOIN jobs j ON j.job_id = a.job_id
           WHERE a.status = 'active' GROUP BY j.title""").fetchall())
    assert active == {"Senior Controls Engineer": 15, "Manufacturing Process Engineer": 18,
                      "People Operations Partner": 12}
    statuses = Counter(r[0] for r in db.execute("SELECT status FROM jobs"))
    assert statuses["open"] == 3
    assert statuses["filled"] + statuses["cancelled"] in (3, 4)
    past = db.execute(
        """SELECT COUNT(*) FROM applications a JOIN jobs j ON j.job_id = a.job_id
           WHERE j.status != 'open'""").fetchone()[0]
    assert 35 <= past <= 45
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("scorecards", "emails", "tasks")}
    assert 55 <= counts["scorecards"] <= 80
    assert 60 <= counts["emails"] <= 80
    assert counts["tasks"] == 20


def test_one_candidate_applied_to_two_roles(db):
    rows = db.execute(
        """SELECT candidate_id, COUNT(DISTINCT job_id) FROM applications
           GROUP BY candidate_id HAVING COUNT(*) > 1""").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == 2


def test_sources_and_integrations(db, as_of):
    sources = {r[0] for r in db.execute("SELECT DISTINCT source FROM candidates")}
    assert sources == {"LinkedIn", "Careers site", "Referral", "Job board", "Agency"}
    latest = dict(db.execute(
        """SELECT s.integration, s.status FROM source_syncs s
           WHERE s.started_at = (SELECT MAX(started_at) FROM source_syncs
                                 WHERE integration = s.integration)""").fetchall())
    assert latest == {"Greenhouse (ATS)": "success", "Google Calendar": "success",
                      "Interview notes": "partial", "Email": "success", "Slack": "success"}
    first = db.execute("SELECT MIN(started_at) FROM source_syncs").fetchone()[0]
    span = db.execute("SELECT julianday(?) - julianday(?)", (as_of, first)).fetchone()[0]
    assert 13.9 <= span <= 14.0


def test_meta_records_how_the_data_was_made(db):
    meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
    assert set(meta) == {"as_of", "seed", "generator_version", "data_hash"}
    assert meta["as_of"] == "2026-11-09T17:00:00Z"
    assert meta["seed"] == "42"
    assert re.fullmatch(r"[0-9a-f]{64}", meta["data_hash"])


def test_regenerating_gives_the_same_data_hash_and_rows(db, tmp_path):
    out = tmp_path / "regenerated.db"
    generate.build(out)
    fresh = sqlite3.connect(out)
    try:
        committed_hash = db.execute("SELECT value FROM meta WHERE key = 'data_hash'").fetchone()[0]
        fresh_hash = fresh.execute("SELECT value FROM meta WHERE key = 'data_hash'").fetchone()[0]
        assert fresh_hash == committed_hash
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        for table in tables:
            committed_rows = [tuple(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY 1, 2")]
            fresh_rows = fresh.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            assert fresh_rows == committed_rows, table
    finally:
        fresh.close()


def test_as_of_override_shifts_every_time(tmp_path):
    out = tmp_path / "shifted.db"
    generate.build(out, "2026-12-09T17:00:00Z")
    con = sqlite3.connect(out)
    try:
        assert con.execute("SELECT value FROM meta WHERE key = 'as_of'").fetchone()[0] == \
            "2026-12-09T17:00:00Z"
        latest = con.execute("SELECT MAX(entered_at) FROM stage_events").fetchone()[0]
        assert "2026-12-01" < latest <= "2026-12-09T17:00:00Z"
    finally:
        con.close()
