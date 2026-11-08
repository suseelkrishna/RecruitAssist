"""RBAC matrix: every logic function, run as each of the 6 users.

For each user the allowed jobs and applications are computed here with
separate SQL. Every ID that comes back must be in scope, and every
out-of-scope job or application must fail closed with the same message.
"""

from __future__ import annotations

import json
import re

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import access
from app.logic import analytics, evidence, funnel, scope, scoring, tasks
from test_access import expected_jobs

USERS = ["USR-1", "USR-2", "USR-3", "USR-4", "USR-5", "USR-6"]
ALL_JOBS = [f"JOB-{n}" for n in range(1, 8)]
ID_RE = re.compile(r"\b(JOB|APP|TASK)-\d+\b")


def allowed_apps(db, jobs: set[str]) -> set[str]:
    """Application IDs on the given jobs."""
    return {r[0] for r in db.execute("SELECT application_id, job_id FROM applications") if r[1] in jobs}


def ids_in(result) -> dict[str, set[str]]:
    """Every JOB-, APP-, and TASK- ID anywhere in a result, by prefix."""
    found: dict[str, set[str]] = {"JOB": set(), "APP": set(), "TASK": set()}
    for match in ID_RE.finditer(json.dumps(result)):
        found[match.group(1)].add(match.group(0))
    return found


def task_jobs(db) -> dict[str, str]:
    """Each task's job_id."""
    return dict(db.execute("SELECT task_id, job_id FROM tasks").fetchall())


def calls(principal, jobs):
    """One call of every logic function that returns data, using an in-scope job where needed."""
    job = sorted(jobs)[0]
    yield "list_jobs", scope.list_jobs(principal)
    yield "scope_card", scope.scope_card(principal)
    yield "pipeline_by_job", funnel.pipeline_by_job(principal)
    yield "pipeline_by_job(job)", funnel.pipeline_by_job(principal, job)
    yield "funnel_dropoff", funnel.funnel_dropoff(principal, job)
    yield "score_candidates", scoring.score_candidates(principal, job, top_n=50)
    yield "pending_tasks", tasks.pending_tasks(principal)
    for name in ["kpis", "funnel", "days_open_vs_target", "applicants_over_time", "source_quality",
                 "time_in_stage", "withdrawal_reasons", "offer_acceptance"]:
        yield name, getattr(analytics, name)(principal)
    if principal.role != "hr_user":
        yield "recruiter_load", analytics.recruiter_load(principal)


@pytest.mark.parametrize("user_id", USERS)
def test_only_in_scope_ids_come_back(db, user_id):
    principal = access.principal_for(user_id)
    jobs = expected_jobs(db, user_id)
    apps = allowed_apps(db, jobs)
    owners = task_jobs(db)
    for name, result in calls(principal, jobs):
        found = ids_in(result)
        assert found["JOB"] <= jobs, f"{user_id} {name} leaked {found['JOB'] - jobs}"
        assert found["APP"] <= apps, f"{user_id} {name} leaked {found['APP'] - apps}"
        assert {owners[t] for t in found["TASK"]} <= jobs, f"{user_id} {name} leaked a task"


@pytest.mark.parametrize("user_id", USERS)
def test_in_scope_lists_are_complete(db, user_id):
    principal = access.principal_for(user_id)
    jobs = expected_jobs(db, user_id)
    assert {j["job_id"] for j in scope.list_jobs(principal)["jobs"]} == jobs
    assert {j["job_id"] for j in funnel.pipeline_by_job(principal)["jobs"]} == jobs
    total = funnel.pipeline_by_job(principal)["all_jobs"][0]["reached"]
    assert total == len(allowed_apps(db, jobs))


@pytest.mark.parametrize("user_id", USERS)
def test_out_of_scope_jobs_fail_closed(db, user_id):
    principal = access.principal_for(user_id)
    outside = [j for j in ALL_JOBS if j not in expected_jobs(db, user_id)] + ["JOB-99"]
    for job in outside:
        for call in (lambda: funnel.pipeline_by_job(principal, job),
                     lambda: funnel.funnel_dropoff(principal, job),
                     lambda: scoring.score_candidates(principal, job),
                     lambda: tasks.pending_tasks(principal, job_id=job),
                     lambda: scope.scope_card(principal, job),
                     lambda: analytics.kpis(principal, job_id=job),
                     lambda: analytics.source_quality(principal, job_id=job)):
            with pytest.raises(ToolError) as err:
                call()
            assert str(err.value) == f"{job} is not in your scope"


@pytest.mark.parametrize("user_id", USERS)
def test_out_of_scope_applications_fail_closed(db, user_id):
    principal = access.principal_for(user_id)
    inside = allowed_apps(db, expected_jobs(db, user_id))
    outside = sorted({r[0] for r in db.execute("SELECT application_id FROM applications")} - inside)
    for app_id in outside[:10] + ["APP-999"]:
        with pytest.raises(ToolError) as err:
            evidence.get_candidate_evidence(principal, app_id)
        assert str(err.value) == f"{app_id} is not in your scope"
    for app_id in sorted(inside)[:3]:
        assert evidence.get_candidate_evidence(principal, app_id)["application_id"] == app_id


@pytest.mark.parametrize("user_id", ["USR-4", "USR-5", "USR-6"])
def test_recruiter_load_is_closed_to_hr_users(user_id):
    with pytest.raises(ToolError, match="admin and hr_manager roles only"):
        analytics.recruiter_load(access.principal_for(user_id))


def test_a_principal_with_no_jobs_sees_nothing():
    nobody = access.Principal("USR-0", "Nobody", "hr_user", frozenset(), frozenset())
    assert scope.list_jobs(nobody)["jobs"] == []
    assert funnel.pipeline_by_job(nobody)["all_jobs"][0]["reached"] == 0
    assert tasks.pending_tasks(nobody)["tasks"] == []
    assert analytics.kpis(nobody)["active_candidates"] == 0
    with pytest.raises(ToolError, match="JOB-1 is not in your scope"):
        scoring.score_candidates(nobody, "JOB-1")
