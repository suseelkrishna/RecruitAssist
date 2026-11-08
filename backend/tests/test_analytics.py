"""Dashboard metrics against SQL written here and a hand-built fixture."""

from __future__ import annotations

import re
import statistics
from datetime import datetime

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import tiny
from app import access
from app.logic import analytics

FMT = "%Y-%m-%dT%H:%M:%SZ"


def admin():
    """The admin principal for whichever database is in use."""
    return access.principal_for("USR-1")


def days(start: str, end: str) -> float:
    """Days between two stored timestamps."""
    return (datetime.strptime(end, FMT) - datetime.strptime(start, FMT)).total_seconds() / 86400


def test_kpis_match_sql(db, as_of):
    got = analytics.kpis(admin())

    def q(sql: str) -> int:
        """The single number a query returns."""
        return db.execute(sql, {"as_of": as_of}).fetchone()[0]

    assert got["open_jobs"] == q("SELECT COUNT(*) FROM jobs WHERE status = 'open'")
    assert got["active_candidates"] == q("SELECT COUNT(*) FROM applications WHERE status = 'active'")
    assert got["new_applicants_7d"] == q(
        "SELECT COUNT(*) FROM applications WHERE julianday(:as_of) - julianday(applied_at) < 7")
    assert got["offers_out"] == q(
        "SELECT COUNT(*) FROM applications WHERE status = 'active' AND current_stage = 'Offer'")
    fills = [days(r[0], r[1]) for r in db.execute(
        "SELECT opened_at, closed_at FROM jobs WHERE status = 'filled'")]
    assert got["median_days_to_fill"] == round(statistics.median(fills), 1)
    assert str(got["open_jobs"]) in got["takeaway"]


def test_kpis_for_one_team_and_recruiter(db):
    team = analytics.kpis(admin(), team_id="TEAM-1")
    assert team["open_jobs"] == db.execute(
        "SELECT COUNT(*) FROM jobs WHERE status = 'open' AND team_id = 'TEAM-1'").fetchone()[0]
    mine = analytics.kpis(admin(), recruiter_user_id="USR-5")
    assert mine["active_candidates"] == db.execute(
        """SELECT COUNT(*) FROM applications a JOIN job_assignments j USING (job_id)
           WHERE j.recruiter_user_id = 'USR-5' AND a.status = 'active'""").fetchone()[0]


def test_source_quality_matches_sql(db):
    rows = db.execute("""
        SELECT c.source, COUNT(*) AS applicants,
               SUM(EXISTS (SELECT 1 FROM stage_events e WHERE e.application_id = a.application_id
                           AND e.stage = 'Onsite')) AS onsite,
               SUM(a.status = 'hired') AS hires
        FROM applications a JOIN candidates c USING (candidate_id) GROUP BY c.source""").fetchall()
    got = {r["source"]: r for r in analytics.source_quality(admin())["sources"]}
    assert set(got) == {r["source"] for r in rows}
    for r in rows:
        g = got[r["source"]]
        assert (g["applicants"], g["reached_onsite"], g["hires"]) == (r["applicants"], r["onsite"], r["hires"])
        assert g["onsite_rate_pct"] == round(100 * r["onsite"] / r["applicants"], 1)


def test_withdrawal_reasons_match_sql(db):
    want = dict(db.execute("""SELECT outcome_reason, COUNT(*) FROM applications
                              WHERE status = 'withdrawn' GROUP BY 1""").fetchall())
    got = analytics.withdrawal_reasons(admin())["reasons"]
    assert {r["reason"]: r["count"] for r in got} == want
    assert [r["count"] for r in got] == sorted(want.values(), reverse=True)


def test_offer_acceptance_matches_sql(db):
    got = analytics.offer_acceptance(admin())

    def status(s: str) -> list[str]:
        """Applications that reached Offer and now have status s."""
        return sorted(r[0] for r in db.execute(
            """SELECT a.application_id FROM applications a JOIN stage_events e USING (application_id)
               WHERE e.stage = 'Offer' AND a.status = ?""", (s,)))

    assert got["accepted"] == status("hired")
    assert got["declined"] == status("offer_declined")
    assert sorted(got["pending"]) == status("active")
    decided = len(got["accepted"]) + len(got["declined"]) + len(got["withdrawn"])
    assert got["acceptance_rate_pct"] == round(100 * len(got["accepted"]) / decided, 1)


def test_days_open_vs_target(db, as_of):
    got = {r["job_id"]: r for r in analytics.days_open_vs_target(admin())["jobs"]}
    for job_id, opened, target in db.execute(
            "SELECT job_id, opened_at, target_fill_days FROM jobs WHERE status = 'open'"):
        assert got[job_id]["days_open"] == round(days(opened, as_of), 1)
        assert got[job_id]["over_target"] == (days(opened, as_of) > target)


def test_applicants_over_time_adds_up(db):
    total = db.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    plain = analytics.applicants_over_time(admin())
    split = analytics.applicants_over_time(admin(), by_source=True)
    assert sum(w["applicants"] for w in plain["weeks"]) == total
    assert sum(w["applicants"] for w in split["weeks"]) == total
    assert all(datetime.strptime(w["week_start"], "%Y-%m-%d").weekday() == 0 for w in plain["weeks"])


def test_date_range_is_inclusive(db):
    day = db.execute("SELECT substr(applied_at, 1, 10) FROM applications ORDER BY applied_at LIMIT 1").fetchone()[0]
    n = db.execute("SELECT COUNT(*) FROM applications WHERE substr(applied_at, 1, 10) = ?", (day,)).fetchone()[0]
    one_day = analytics.applicants_over_time(admin(), date_from=day, date_to=day)
    assert sum(w["applicants"] for w in one_day["weeks"]) == n


def test_recruiter_load_for_a_manager_covers_their_teams_only():
    rows = analytics.recruiter_load(access.principal_for("USR-2"))["recruiters"]
    assert {j for r in rows for j in r["job_ids"]} == {"JOB-1", "JOB-2", "JOB-4", "JOB-5"}


@pytest.mark.parametrize("kwargs, message", [
    ({"team_id": "TEAM-9"}, "Unknown team_id 'TEAM-9'. Valid teams: TEAM-1"),
    ({"recruiter_user_id": "USR-9"}, "Unknown recruiter_user_id 'USR-9'. Valid users: USR-1"),
    ({"date_from": "2026/01/01"}, "Dates must be YYYY-MM-DD"),
    ({"team": "Engineering"}, "Unknown filters ['team']. Valid filters: team_id, job_id"),
])
def test_bad_filters_explain_the_valid_options(kwargs, message):
    with pytest.raises(ToolError, match=re.escape(message)):
        analytics.kpis(admin(), **kwargs)


def test_time_in_stage_by_hand(use_db):
    data = tiny.base()
    for n, exit_day in ((1, "02"), (2, "04"), (3, "07")):
        tiny.add_application(data, f"APP-{n}", "JOB-1", [
            ("Applied", "2026-10-01T00:00:00Z", f"2026-10-{exit_day}T00:00:00Z", "advanced"),
            ("Recruiter Screen", f"2026-10-{exit_day}T00:00:00Z", None, None)])
    use_db(data)
    stages = {s["stage"]: s for s in analytics.time_in_stage(admin())["stages"]}
    assert (stages["Applied"]["median_days"], stages["Applied"]["stays"]) == (3.0, 3)  # 1, 3, 6 days
    assert stages["Recruiter Screen"]["median_days"] is None  # nobody has left yet


def test_empty_view_has_takeaways(use_db):
    use_db(tiny.base())
    for name in ["kpis", "funnel", "days_open_vs_target", "applicants_over_time", "source_quality",
                 "time_in_stage", "withdrawal_reasons", "recruiter_load", "offer_acceptance"]:
        result = getattr(analytics, name)(admin(), job_id="JOB-3")
        assert isinstance(result["takeaway"], str) and result["takeaway"]
