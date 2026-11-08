"""score_candidates against the eval answer key, separate SQL, and hand-computed fixtures."""

from __future__ import annotations

import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import tiny
from app import access
from app.logic import scoring

ADMIN = "USR-1"
POINTS = {"strong_yes": 4, "yes": 3, "no": 2, "strong_no": 1}


def admin():
    """The admin principal for whichever database is in use."""
    return access.principal_for(ADMIN)


def test_top_three_matches_the_answer_key(answers):
    expected = answers["process-top3"]
    result = scoring.score_candidates(admin(), expected["job_id"])
    assert [r["application_id"] for r in result["ranked"]] == [t["application_id"] for t in expected["top_3"]]
    for got, want in zip(result["ranked"], expected["top_3"]):
        assert got["components"]["scorecards"]["evidence"] == want["scorecard_ids"]
        assert got["components"]["scorecards"]["avg_points"] == want["avg_points"]
    assert result["rubric_version"] == "v1"


def test_traps_land_where_expected(answers):
    expected = answers["process-top3"]
    ranked = scoring.score_candidates(admin(), "JOB-2", top_n=50)["ranked"]
    by_id = {r["application_id"]: r for r in ranked}
    glowing = by_id[expected["trap_a_glowing_cv_two_no"]["application_id"]]
    assert glowing["rank"] > 3
    missing = by_id[expected["trap_b_missing_onsite_scorecard"]["application_id"]]
    assert missing["incomplete_evidence"] is True
    assert any("INT-" in m for m in missing["missing"])


def test_score_for_one_application_by_hand(db):
    """APP-068: recompute every component from raw rows with SQL written here."""
    cards = db.execute("""SELECT s.overall, s.ratings_json FROM scorecards s
                          JOIN interviews i ON i.interview_id = s.interview_id
                          WHERE i.application_id = 'APP-068'""").fetchall()
    must = json.loads(db.execute("SELECT must_have_json FROM jobs WHERE job_id = 'JOB-2'").fetchone()[0])
    sc = (sum(POINTS[c[0]] for c in cards) / len(cards) - 1) / 3
    per_skill = [[json.loads(c[1])[m] for c in cards] for m in must]
    mh = sum((sum(r) / len(r) - 1) / 3 for r in per_skill) / len(must)
    stages = [r[0] for r in db.execute("SELECT stage FROM stage_events WHERE application_id = 'APP-068'")]
    st = max(tiny.STAGES.index(s) for s in stages) / 5
    got = next(r for r in scoring.score_candidates(admin(), "JOB-2", top_n=50)["ranked"]
               if r["application_id"] == "APP-068")
    assert got["score"] == round(0.5 * sc + 0.3 * mh + 0.2 * st, 4)


def test_pool_is_active_applications_only(db):
    active = {r[0] for r in db.execute(
        "SELECT application_id FROM applications WHERE job_id = 'JOB-2' AND status = 'active'")}
    result = scoring.score_candidates(admin(), "JOB-2", top_n=50)
    assert result["pool_size"] == len(active)
    assert {r["application_id"] for r in result["ranked"]} == active


def test_ranking_is_sorted_and_ties_break_by_application_id():
    ranked = scoring.score_candidates(admin(), "JOB-2", top_n=50)["ranked"]
    assert [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))
    assert ranked == sorted(ranked, key=lambda r: (-r["score"], r["application_id"]))
    # APP-065 and APP-078 both score 0.72 in the committed data.
    tied = [r["application_id"] for r in ranked if r["score"] == 0.72]
    assert tied == ["APP-065", "APP-078"]


def tiny_job(use_db):
    """JOB-1 with three active applications built for exact scores, plus one rejected one.

    APP-1: Onsite, scorecards yes + yes, ratings 4/4 -> 0.5*2/3 + 0.3*1 + 0.2*0.6 = 0.7533
    APP-2: Onsite, scorecards yes + yes, ratings 4/4 -> the same score as APP-1 (a tie)
    APP-3: Onsite, one yes scorecard and one completed interview with none -> incomplete
    APP-4: rejected, so not in the pool even with a strong_yes
    """
    data = tiny.base()
    for n in (1, 2, 3):
        tiny.add_application(data, f"APP-{n}", "JOB-1", [
            ("Applied", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "advanced"),
            ("Recruiter Screen", "2026-10-02T00:00:00Z", "2026-10-03T00:00:00Z", "advanced"),
            ("Technical", "2026-10-03T00:00:00Z", "2026-10-04T00:00:00Z", "advanced"),
            ("Onsite", "2026-10-04T00:00:00Z", None, None)])
    for n in (1, 2):
        for k in (1, 2):
            tiny.add_interview(data, f"INT-{n}{k}", f"APP-{n}", "Onsite", "2026-10-05T00:00:00Z", "yes",
                               '{"Skill A": 4, "Skill B": 4}')
    tiny.add_interview(data, "INT-31", "APP-3", "Technical", "2026-10-03T12:00:00Z", "yes")
    tiny.add_interview(data, "INT-32", "APP-3", "Onsite", "2026-10-05T00:00:00Z")
    tiny.add_application(data, "APP-4", "JOB-1", [
        ("Applied", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "rejected")], status="rejected",
        reason="Does not meet must-have requirements")
    tiny.add_interview(data, "INT-41", "APP-4", "Technical", "2026-10-01T12:00:00Z", "strong_yes")
    use_db(data)


def test_exact_tie_breaks_by_application_id(use_db):
    tiny_job(use_db)
    ranked = scoring.score_candidates(admin(), "JOB-1", top_n=10)["ranked"]
    assert [(r["application_id"], r["score"]) for r in ranked[:2]] == [("APP-1", 0.7533), ("APP-2", 0.7533)]
    assert "APP-4" not in {r["application_id"] for r in ranked}


def test_missing_scorecard_is_ranked_and_flagged(use_db):
    tiny_job(use_db)
    result = scoring.score_candidates(admin(), "JOB-1", top_n=10)
    app3 = next(r for r in result["ranked"] if r["application_id"] == "APP-3")
    # One yes (3 points) -> 2/3; ratings 3/3 -> 2/3; Onsite -> 0.6.
    assert app3["score"] == round(0.5 * 2 / 3 + 0.3 * 2 / 3 + 0.2 * 0.6, 4)
    assert app3["incomplete_evidence"] is True
    assert app3["missing"] == ["No scorecard for INT-32 (Onsite, completed 2026-10-05T00:00:00Z)"]
    assert any(w.startswith("APP-3 has incomplete evidence") for w in result["warnings"])


def test_no_scorecards_scores_zero_on_that_component(use_db):
    data = tiny.base()
    tiny.add_application(data, "APP-1", "JOB-1", [("Applied", "2026-10-01T00:00:00Z", None, None)])
    use_db(data)
    entry = scoring.score_candidates(admin(), "JOB-1")["ranked"][0]
    assert entry["score"] == 0.0
    assert entry["missing"] == ["No scorecards submitted yet"]


def test_empty_role_returns_an_empty_ranking(use_db):
    use_db(tiny.base())
    result = scoring.score_candidates(admin(), "JOB-3")
    assert result["ranked"] == [] and result["pool_size"] == 0
    assert result["missing"] == ["JOB-3 has no active applications."]


@pytest.mark.parametrize("top_n", [0, -1, 51])
def test_top_n_out_of_range(top_n):
    with pytest.raises(ToolError, match="top_n must be between 1 and 50"):
        scoring.score_candidates(admin(), "JOB-2", top_n=top_n)
