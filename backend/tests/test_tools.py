"""Check each server.py tool against its own SQL query on data/recruiting.db.

The reference queries are written differently from the server's on purpose
(for example, "in stage" comes from applications.current_stage here, but from
open stage_events in the server), so a shared mistake is less likely to hide.

Run data/generate.py first if recruiting.db is missing. The db and as_of
fixtures come from conftest.py.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

import pytest

import server
from conftest import DB_PATH
from mcp.server.mcpserver.exceptions import ToolError

FMT = "%Y-%m-%dT%H:%M:%SZ"


def test_server_reads_the_committed_database():
    assert server.DB_PATH == DB_PATH.resolve()


def job_ids(db) -> list[str]:
    """Every job_id, in the order the server lists jobs."""
    return [r[0] for r in db.execute("SELECT job_id FROM jobs ORDER BY job_id")]


def expected_counts(db, job_id: str | None) -> dict[str, tuple[int, int]]:
    """{stage: (reached, in_stage)} computed without looking at exited_at."""
    where = "" if job_id is None else "WHERE a.job_id = ?"
    params = () if job_id is None else (job_id,)
    reached = dict(db.execute(
        f"""SELECT e.stage, COUNT(DISTINCT e.application_id)
            FROM stage_events e JOIN applications a USING (application_id)
            {where} GROUP BY e.stage""", params).fetchall())
    in_stage = dict(db.execute(
        f"""SELECT a.current_stage, COUNT(*) FROM applications a
            {where + (' AND' if where else 'WHERE')} a.status = 'active'
            GROUP BY a.current_stage""", params).fetchall())
    return {s: (reached.get(s, 0), in_stage.get(s, 0)) for s in server.STAGES}


# --- stage counts -----------------------------------------------------------

@pytest.mark.parametrize("job_id", ["JOB-1", "JOB-3", "JOB-7"])
def test_stage_counts_for_one_job(db, job_id):
    result = server.pipeline_by_job(job_id)
    expected = expected_counts(db, job_id)

    job = db.execute(
        """SELECT j.title, t.name AS team, j.status
           FROM jobs j JOIN teams t ON t.team_id = j.team_id WHERE j.job_id = ?""",
        (job_id,)).fetchone()
    assert result["job_id"] == job_id
    assert result["title"] == job["title"]
    assert result["team"] == job["team"]
    assert result["status"] == job["status"]

    assert [s["stage"] for s in result["stages"]] == server.STAGES
    got = {s["stage"]: (s["reached"], s["in_stage"]) for s in result["stages"]}
    assert got == expected


def test_all_jobs_covers_every_job_and_sums(db):
    result = server.pipeline_by_job()
    assert [j["job_id"] for j in result["jobs"]] == job_ids(db)

    got = {s["stage"]: (s["reached"], s["in_stage"]) for s in result["all_jobs"]}
    assert got == expected_counts(db, None)
    # Everyone applied, so the top of the funnel is every application.
    total_apps = db.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    assert got["Applied"][0] == total_apps


# --- conversion % -----------------------------------------------------------

def test_conversion_pct_math_for_every_funnel(db):
    result = server.pipeline_by_job()
    funnels = [result["all_jobs"]] + [j["stages"] for j in result["jobs"]]
    for stages in funnels:
        assert stages[0]["conversion_pct"] is None  # nothing before Applied
        for prev, cur in zip(stages, stages[1:]):
            if prev["reached"] == 0:
                assert cur["conversion_pct"] is None
            else:
                assert cur["conversion_pct"] == round(100 * cur["reached"] / prev["reached"], 1)


def test_conversion_pct_known_values():
    stages = server.funnel({"Applied": (3, 0), "Recruiter Screen": (1, 0)})
    pcts = [s["conversion_pct"] for s in stages]
    # 1/3 -> 33.3, then 0/1 -> 0.0, then 0/0 -> None for the rest.
    assert pcts == [None, 33.3, 0.0, None, None, None]


def test_engineering_technical_to_onsite_matches_sql(db):
    tech, onsite = db.execute(
        """SELECT SUM(e.stage = 'Technical'), SUM(e.stage = 'Onsite')
           FROM stage_events e
           JOIN applications a USING (application_id)
           JOIN jobs j USING (job_id)
           JOIN teams t USING (team_id)
           WHERE t.name = 'Engineering'""").fetchone()
    result = server.pipeline_by_job()
    eng = [j for j in result["jobs"] if j["team"] == "Engineering"]
    got_tech = sum(next(s["reached"] for s in j["stages"] if s["stage"] == "Technical") for j in eng)
    got_onsite = sum(next(s["reached"] for s in j["stages"] if s["stage"] == "Onsite") for j in eng)
    assert (got_tech, got_onsite) == (tech, onsite)


# --- stuck_candidates -------------------------------------------------------

def expected_stuck(db, as_of: datetime, days: int) -> list[int]:
    """Application ids in the stuck list, longest wait first, computed in Python."""
    rows = db.execute(
        """SELECT a.application_id, e.entered_at
           FROM applications a
           JOIN stage_events e ON e.application_id = a.application_id
                              AND e.stage = a.current_stage
           WHERE a.status = 'active'""").fetchall()
    waits = [(as_of - datetime.strptime(r["entered_at"], FMT), r["application_id"]) for r in rows]
    return [app_id for wait, app_id in sorted(waits, reverse=True) if wait > timedelta(days=days)]


@pytest.mark.parametrize("days", [0, 3, 7, 14])
def test_stuck_candidates_matches_sql(db, as_of, days):
    result = server.stuck_candidates(days)

    assert result["as_of"] == as_of
    as_of = datetime.strptime(as_of, FMT)
    assert result["days"] == days
    assert result["count"] == len(result["candidates"])
    assert [c["application_id"] for c in result["candidates"]] == expected_stuck(db, as_of, days)

    waits = [c["days_in_stage"] for c in result["candidates"]]
    assert waits == sorted(waits, reverse=True)
    for c in result["candidates"]:
        row = db.execute(
            """SELECT c.full_name, j.title, a.current_stage, a.status
               FROM applications a JOIN candidates c USING (candidate_id) JOIN jobs j USING (job_id)
               WHERE a.application_id = ?""", (c["application_id"],)).fetchone()
        assert (c["full_name"], c["job_title"], c["stage"]) == (row[0], row[1], row[2])
        assert row["status"] == "active"
        assert c["days_in_stage"] > days or c["days_in_stage"] == round(days, 1)


def test_stuck_threshold_is_strictly_greater_than(db):
    """A candidate exactly `days` days into a stage is not stuck; one second later they are."""
    app_id, entered = db.execute(
        """SELECT a.application_id, e.entered_at
           FROM applications a
           JOIN stage_events e ON e.application_id = a.application_id AND e.stage = a.current_stage
           WHERE a.status = 'active' ORDER BY e.entered_at LIMIT 1""").fetchone()
    entered = datetime.strptime(entered, FMT)

    def stuck_ids(as_of: datetime) -> set[str]:
        result = server.stuck_candidates(7, as_of.strftime(FMT))
        return {c["application_id"] for c in result["candidates"]}

    assert app_id not in stuck_ids(entered + timedelta(days=7))
    assert app_id in stuck_ids(entered + timedelta(days=7, seconds=1))


def test_stuck_candidates_excludes_closed_applications(db):
    result = server.stuck_candidates(0, "2030-01-01T00:00:00Z")  # everyone open is "stuck"
    active = db.execute("SELECT COUNT(*) FROM applications WHERE status = 'active'").fetchone()[0]
    assert result["count"] == active


def test_stuck_candidates_rejects_negative_days():
    with pytest.raises(ToolError, match="days must be 0 or more"):
        server.stuck_candidates(-1)


# --- time_to_fill -----------------------------------------------------------

def expected_fill(db, team: str | None) -> dict:
    """Time-to-fill stats for a team (or all teams), computed in Python from raw rows."""
    rows = db.execute(
        """SELECT t.name AS team, j.status, j.opened_at, j.closed_at
           FROM jobs j JOIN teams t ON t.team_id = j.team_id""").fetchall()
    rows = [r for r in rows if team is None or r["team"] == team]
    days = [(datetime.strptime(r["closed_at"], FMT) - datetime.strptime(r["opened_at"], FMT))
            .total_seconds() / 86400 for r in rows if r["status"] == "filled"]
    return {
        "filled_jobs": len(days),
        "median_days_to_fill": round(statistics.median(days), 1) if days else None,
        "avg_days_to_fill": round(sum(days) / len(days), 1) if days else None,
        "open_jobs": sum(1 for r in rows if r["status"] == "open"),
        "cancelled_jobs": sum(1 for r in rows if r["status"] == "cancelled"),
    }


@pytest.mark.parametrize("team", ["Engineering", "People", "Manufacturing"])
def test_time_to_fill_for_one_team(db, team):
    assert server.time_to_fill(team) == {"team": team, **expected_fill(db, team)}


def test_time_to_fill_team_is_case_insensitive(db):
    assert server.time_to_fill("  engineering ") == server.time_to_fill("Engineering")


def test_time_to_fill_overall_and_by_team(db):
    result = server.time_to_fill()
    assert result["overall"] == expected_fill(db, None)
    teams = [r[0] for r in db.execute("SELECT name FROM teams ORDER BY name")]
    assert [t["team"] for t in result["by_team"]] == teams
    for t in result["by_team"]:
        assert t == {"team": t["team"], **expected_fill(db, t["team"])}


# --- errors -----------------------------------------------------------------

@pytest.mark.parametrize("bad_id", ["JOB-0", "JOB-99", "1"])
def test_unknown_job_id(db, bad_id):
    with pytest.raises(ToolError, match=rf"Unknown job_id '{bad_id}'\. Valid job_ids: JOB-1, JOB-2"):
        server.pipeline_by_job(bad_id)


@pytest.mark.parametrize("bad_team", ["Marketing", "", "Engineering'; DROP TABLE jobs; --"])
def test_unknown_team(db, bad_team):
    with pytest.raises(ToolError, match="Unknown team .* Valid teams: Engineering, Manufacturing"):
        server.time_to_fill(bad_team)
    # The odd input above did nothing to the data.
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 7
