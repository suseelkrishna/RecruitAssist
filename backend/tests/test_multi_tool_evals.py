"""The multi_tool eval group: its questions, the new grading rules, and that the default
run still covers only the core group.

The grading tests use hand-written fake runs, so no model is called.
"""

from __future__ import annotations

import json

import pytest

from app import access
from app.logic import scoring
from evals import expected, grade, report, run

MULTI = [q for q in json.loads(run.QUESTIONS.read_text())["questions"] if q["group"] == "multi_tool"]


def fake_run(answer: str, tools: list[str], verified: bool = True) -> dict:
    """A result shaped like run_agent's, with the given answer and tool calls in order."""
    return {"answer": answer, "status": "answered", "verified": verified,
            "steps": [{"tool": t} for t in tools], "verifier": {"checks": {"citations": {"unknown": []}}}}


def graded(question: dict, answer: str, tools: list[str], user_jobs: list[str], db) -> dict:
    """Grade one fake run for a question."""
    return grade.grade(question, fake_run(answer, tools), user_jobs, db)


# The group itself

def test_the_default_run_loads_only_the_core_questions():
    core = run.load_questions()
    assert len(core["questions"]) == 18 and {q["group"] for q in core["questions"]} == {"core"}
    multi = run.load_questions(group="multi_tool")
    assert len(multi["questions"]) >= 12 and {q["group"] for q in multi["questions"]} == {"multi_tool"}
    with pytest.raises(SystemExit, match="Unknown group"):
        run.load_questions(group="nope")


def test_multi_tool_questions_cover_the_planned_kinds():
    ids = {q["id"] for q in MULTI}
    assert len(MULTI) >= 12
    assert sum("history" in q for q in MULTI) == 2
    assert all(q["history"][0]["citations"] for q in MULTI if "history" in q)
    assert {q["user"] for q in MULTI} == {"USR-1", "USR-2", "USR-4"}
    assert all("tool_calls" in q["checks"] and q["checks"]["tools"] for q in MULTI)
    assert "mt-mixed-scope" in ids


def test_the_independent_ranking_matches_the_app_on_every_open_job(db, as_of):
    con = expected.connect()
    admin = access.principal_for("USR-1")
    for job in ("JOB-1", "JOB-2", "JOB-3"):
        mine = [(r["application_id"], r["score"]) for r in expected.rubric_ranking(con, job, as_of)]
        app = [(r["application_id"], r["score"]) for r in scoring.score_candidates(admin, job, top_n=50)["ranked"]]
        assert mine == app


def test_mixed_scope_answer_key_lies_outside_the_users_scope(db):
    q = next(q for q in MULTI if q["id"] == "mt-mixed-scope")
    allowed = expected.scope_jobs(expected.connect(), "USR-4")
    assert q["expected"]["out_of_scope_job"] not in allowed and q["expected"]["in_scope_job"] in allowed
    assert all(grade.jobs_of(db, i) and not grade.jobs_of(db, i) & set(allowed) for i in q["expected"]["hidden"])


# Grading rules

QUESTION = {"id": "t", "user": "USR-2",
            "checks": {"tools": ["recruiter_load", "funnel_dropoff"], "tool_order": [["recruiter_load", "funnel_dropoff"]],
                       "tool_calls": {"min": 2, "max": 3}, "mentions": ["Alex Chen"]}}


def test_a_run_inside_the_bounds_and_in_order_passes(db):
    result = graded(QUESTION, "Alex Chen is busiest.", ["recruiter_load", "funnel_dropoff"], ["JOB-1", "JOB-2"], db)
    assert result["passed"] and result["tool_calls"] == 2 and result["verified"]


def test_too_few_or_too_many_tool_calls_fail(db):
    few = graded(QUESTION, "Alex Chen.", ["recruiter_load"], ["JOB-2"], db)
    assert not few["checks"]["tool_calls"] and "tool_calls: 1 calls, expected 2 to 3" in few["reasons"]
    many = graded(QUESTION, "Alex Chen.", ["recruiter_load", "funnel_dropoff"] * 2, ["JOB-2"], db)
    assert not many["checks"]["tool_calls"]


def test_a_dependent_call_made_too_early_fails_the_order_check(db):
    result = graded(QUESTION, "Alex Chen.", ["funnel_dropoff", "recruiter_load"], ["JOB-2"], db)
    assert not result["checks"]["tool_order"] and result["checks"]["tools"]
    again = graded(QUESTION, "Alex Chen.", ["funnel_dropoff", "recruiter_load", "funnel_dropoff"], ["JOB-2"], db)
    assert again["checks"]["tool_order"]


def test_a_missing_required_tool_fails(db):
    result = graded(QUESTION, "Alex Chen.", ["recruiter_load", "list_jobs"], ["JOB-2"], db)
    assert not result["checks"]["tools"] and "did not call funnel_dropoff" in " ".join(result["reasons"])


def test_an_out_of_scope_id_is_a_hard_fail_even_when_everything_else_passes(db):
    q = next(q for q in MULTI if q["id"] == "mt-mixed-scope")
    leak = ("Senior Controls Engineer loses most candidates at Onsite. The Manufacturing Process Engineer "
            "role is outside your scope, though APP-068 leads it.")
    result = graded(q, leak, ["funnel_dropoff"], expected.scope_jobs(expected.connect(), "USR-4"), db)
    assert not result["passed"] and not result["checks"]["scope"]
    clean = ("Senior Controls Engineer loses most candidates at Onsite. The Manufacturing Process Engineer "
             "role is outside your scope, so I cannot show its candidates.")
    assert graded(q, clean, ["funnel_dropoff"], expected.scope_jobs(expected.connect(), "USR-4"), db)["passed"]
    named = clean + " Hollis Bellweather is strong."
    assert not graded(q, named, ["funnel_dropoff"], expected.scope_jobs(expected.connect(), "USR-4"), db)["passed"]


def test_an_unverified_answer_is_recorded(db):
    result = grade.grade(QUESTION, fake_run("Alex Chen.", ["recruiter_load", "funnel_dropoff"], verified=False),
                         ["JOB-2"], db)
    assert result["passed"] and result["verified"] is False


# Reporting

def test_a_core_report_keeps_the_multi_tool_section(tmp_path):
    results = tmp_path / "results.md"
    section = f"{report.GROUP_START}\n## Multi-tool questions\nkept\n{report.GROUP_END}\n"
    results.write_text("# Old core report\n\n" + section)
    assert report.with_group_section("# New core report\n", report.group_section(results.read_text())) \
        == "# New core report\n\n" + section
    replaced = report.with_group_section(results.read_text(), f"{report.GROUP_START}\nnew\n{report.GROUP_END}\n")
    assert "kept" not in replaced and "new" in replaced and replaced.startswith("# Old core report")


def test_group_summary_counts_calls_cost_and_verified():
    runs = [{"question_id": f"q{i}", "user": "USR-1", "model": "m", "effort": "low", "repeat": 0,
             "result": {**fake_run("a", ["list_jobs"] * (i + 1), verified=i == 0), "estimated_cost_usd": 0.01,
                        "latency_ms": 1000 * (i + 1), "usage": {}},
             "grade": {"passed": i < 2, "checks": {"citations": True}, "reasons": [] if i < 2 else ["ids: missing APP-1"]}}
            for i in range(3)]
    summary = report.group_summary(runs, {"generated_at": "2026-11-09T00:00:00Z"})
    assert summary["passed"] == 2 and summary["tool_calls_per_question"] == 2.0
    assert summary["verified_rate_pct"] == 33.3 and summary["total_cost_usd"] == 0.03
    text = report.group_markdown(summary)
    assert text.startswith(report.GROUP_START) and "2 of 3" in text and "ids: missing APP-1" in text
