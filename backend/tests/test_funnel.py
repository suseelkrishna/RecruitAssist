"""pipeline_by_job and funnel_dropoff against separate SQL, the answer key, and fixtures."""

from __future__ import annotations

import pytest

import tiny
from app import access
from app.logic import funnel

STAGES = tiny.STAGES


def admin():
    """The admin principal for whichever database is in use."""
    return access.principal_for("USR-1")


def sql_counts(db, job_id: str) -> dict[str, dict[str, int]]:
    """Per stage counts from current_stage and status, without looking at exited_at."""
    reached = dict(db.execute("""SELECT e.stage, COUNT(*) FROM stage_events e
                                 JOIN applications a USING (application_id)
                                 WHERE a.job_id = ? GROUP BY e.stage""", (job_id,)).fetchall())
    in_stage = dict(db.execute("""SELECT current_stage, COUNT(*) FROM applications
                                  WHERE job_id = ? AND (status = 'active' OR current_stage = 'Hired')
                                  GROUP BY current_stage""", (job_id,)).fetchall())
    rejected = dict(db.execute("""SELECT current_stage, COUNT(*) FROM applications
                                  WHERE job_id = ? AND status = 'rejected' GROUP BY current_stage""",
                               (job_id,)).fetchall())
    withdrawn = dict(db.execute("""SELECT current_stage, COUNT(*) FROM applications
                                   WHERE job_id = ? AND status = 'withdrawn' GROUP BY current_stage""",
                                (job_id,)).fetchall())
    return {s: {"reached": reached.get(s, 0), "in_stage": in_stage.get(s, 0),
                "rejected": rejected.get(s, 0), "withdrawn": withdrawn.get(s, 0)} for s in STAGES}


@pytest.mark.parametrize("job_id", [f"JOB-{n}" for n in range(1, 8)])
def test_pipeline_counts_match_sql(db, job_id):
    result = funnel.pipeline_by_job(admin(), job_id)
    expected = sql_counts(db, job_id)
    for row in result["stages"]:
        got = {k: row[k] for k in ("reached", "rejected", "withdrawn")}
        want = {k: expected[row["stage"]][k] for k in ("reached", "rejected", "withdrawn")}
        assert got == want, row["stage"]
        if row["stage"] != "Hired":
            assert row["in_stage"] == expected[row["stage"]]["in_stage"], row["stage"]


def test_conversion_is_reached_over_previous_reached():
    for job in funnel.pipeline_by_job(admin())["jobs"]:
        stages = job["stages"]
        assert stages[0]["conversion_pct"] is None
        for prev, cur in zip(stages, stages[1:]):
            want = None if prev["reached"] == 0 else round(100 * cur["reached"] / prev["reached"], 1)
            assert cur["conversion_pct"] == want


def test_all_jobs_total_is_the_sum_of_jobs():
    result = funnel.pipeline_by_job(admin())
    for i, stage in enumerate(STAGES):
        assert result["all_jobs"][i]["reached"] == sum(j["stages"][i]["reached"] for j in result["jobs"])


def test_dropoff_matches_the_answer_key(answers):
    expected = answers["controls-leak"]
    result = funnel.funnel_dropoff(admin(), expected["job_id"])
    assert result["days_open"] == expected["days_open"]
    by_stage = {s["stage"]: s for s in result["stages"]}
    for want in expected["funnel"]:
        got = by_stage[want["stage"]]
        assert got["entered"] == want["reached"]
        assert got["advanced"] == (want["advanced"] or 0)  # SQL SUM over no exits is NULL
        assert got["pass_rate_pct"] == want["pass_rate_pct"]
    assert by_stage["Onsite"]["median_days_after_last_interview"] == expected["median_days_waiting_after_onsite"]
    assert by_stage["Onsite"]["applications_with_completed_interview"] == \
        expected["applications_with_completed_onsite"]
    leaks = result["leaks"]
    assert leaks[0]["transition"] == expected["main_leak"]
    assert leaks[1]["transition"] == expected["secondary_leak"]
    assert set(expected["withdrew_accepted_another_offer"]) <= set(leaks[0]["evidence"])
    agency = next(s for s in leaks[1]["by_source"] if s["source"] == "Agency")
    want_agency = next(s for s in expected["recruiter_screen_by_source"] if s["source"] == "Agency")
    assert (agency["exited"], agency["pass_rate_pct"]) == (want_agency["exited"], want_agency["pass_rate_pct"])
    reasons = by_stage["Onsite"]["top_outcome_reasons"]
    assert reasons[0]["reason"] == "Accepted another offer"
    assert reasons[0]["application_ids"] == expected["withdrew_accepted_another_offer"]


def test_comparison_with_other_roles_matches_sql(db):
    rows = db.execute("""SELECT e.stage, SUM(e.exit_type = 'advanced'), SUM(e.exit_type IS NOT NULL)
                         FROM stage_events e JOIN applications a USING (application_id)
                         WHERE a.job_id != 'JOB-1' GROUP BY e.stage""").fetchall()
    want = {r[0]: round(100 * r[1] / r[2], 1) if r[2] else None for r in rows}
    result = funnel.funnel_dropoff(admin(), "JOB-1")
    for row in result["comparison_with_other_roles"]:
        assert row["other_roles_pass_rate_pct"] == want.get(row["stage"]), row["stage"]


def test_comparison_is_limited_to_the_users_scope():
    """USR-4 sees JOB-1, JOB-5, JOB-7: the comparison must use only JOB-5 and JOB-7."""
    result = funnel.funnel_dropoff(access.principal_for("USR-4"), "JOB-1")
    assert result["other_roles_in_scope"] == ["JOB-5", "JOB-7"]


def fixture(use_db):
    """JOB-1 by hand: 4 applied, 3 advance to screen, 1 is rejected at Applied.
    At screen: 1 advances, 1 withdraws, 1 is still there. Exit times give known medians."""
    data = tiny.base()
    tiny.add_application(data, "APP-1", "JOB-1", [
        ("Applied", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "advanced"),
        ("Recruiter Screen", "2026-10-02T00:00:00Z", "2026-10-06T00:00:00Z", "advanced"),
        ("Technical", "2026-10-06T00:00:00Z", None, None)])
    tiny.add_application(data, "APP-2", "JOB-1", [
        ("Applied", "2026-10-01T00:00:00Z", "2026-10-04T00:00:00Z", "advanced"),
        ("Recruiter Screen", "2026-10-04T00:00:00Z", "2026-10-06T00:00:00Z", "withdrawn")],
        status="withdrawn", reason="Accepted another offer")
    tiny.add_application(data, "APP-3", "JOB-1", [
        ("Applied", "2026-10-01T00:00:00Z", "2026-10-03T00:00:00Z", "advanced"),
        ("Recruiter Screen", "2026-10-03T00:00:00Z", None, None)])
    tiny.add_application(data, "APP-4", "JOB-1", [
        ("Applied", "2026-10-01T00:00:00Z", "2026-10-05T00:00:00Z", "rejected")],
        status="rejected", reason="Does not meet must-have requirements")
    use_db(data)


def test_dropoff_by_hand(use_db):
    fixture(use_db)
    result = funnel.funnel_dropoff(admin(), "JOB-1")
    applied, screen = result["stages"][0], result["stages"][1]
    assert (applied["entered"], applied["advanced"], applied["rejected"], applied["still_active"]) == (4, 3, 1, 0)
    assert applied["pass_rate_pct"] == 75.0
    assert applied["median_days_before_exit"] == 2.5  # exits after 1, 2, 3, 4 days
    assert (screen["entered"], screen["advanced"], screen["withdrawn"], screen["still_active"]) == (3, 1, 1, 1)
    assert screen["pass_rate_pct"] == 50.0
    assert screen["median_days_before_exit"] == 3.0  # 4 days and 2 days
    assert screen["top_outcome_reasons"] == [
        {"reason": "Accepted another offer", "count": 1, "application_ids": ["APP-2"]}]
    assert [leak["transition"] for leak in result["leaks"]] == [
        "Recruiter Screen to Technical", "Applied to Recruiter Screen"]
    assert result["leaks"][0]["evidence"] == ["APP-2"]


def test_exits_after_as_of_have_not_happened_yet(use_db):
    fixture(use_db)
    result = funnel.funnel_dropoff(admin(), "JOB-1", as_of="2026-10-03T12:00:00Z")
    applied = result["stages"][0]
    assert (applied["advanced"], applied["rejected"], applied["still_active"]) == (2, 0, 2)


def test_empty_role(use_db):
    use_db(tiny.base())
    result = funnel.funnel_dropoff(admin(), "JOB-3")
    assert all(s["entered"] == 0 for s in result["stages"])
    assert result["leaks"] == []
    assert result["missing"] == ["JOB-3 has no applications yet."]
    pipeline = funnel.pipeline_by_job(admin(), "JOB-3")
    assert [s["conversion_pct"] for s in pipeline["stages"]] == [None] * 6
