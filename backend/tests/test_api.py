"""The HTTP API through TestClient: identity, role scope, reassignment rules, the change log,
and the /api/ask rate limits with their fallback to recordings.

Expected scopes come from SQL written here, separately from app/access.py. The
model is a scripted fake, so no test calls the real API.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import recordings
from fake_model import FakeClient, reply, text, tool_use

USERS = ["USR-1", "USR-2", "USR-3", "USR-4", "USR-5", "USR-6"]


def as_user(user_id: str) -> dict[str, str]:
    """Headers for a request made as this demo user."""
    return {"X-Demo-User": user_id}


@pytest.fixture
def client():
    """A TestClient that reports server errors as responses, with no model configured."""
    main.app.dependency_overrides.clear()
    yield TestClient(main.app, raise_server_exceptions=False)
    main.app.dependency_overrides.clear()


def expected_jobs(db, user_id: str) -> set[str]:
    """The job IDs a user should see, from SQL: all for admin, managed teams for hr_manager,
    assigned jobs for hr_user."""
    role = db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    if role == "admin":
        sql, args = "SELECT job_id FROM jobs", ()
    elif role == "hr_manager":
        sql, args = ("SELECT job_id FROM jobs WHERE team_id IN "
                     "(SELECT team_id FROM manager_teams WHERE user_id = ?)", (user_id,))
    else:
        sql, args = "SELECT job_id FROM job_assignments WHERE recruiter_user_id = ?", (user_id,)
    return {r[0] for r in db.execute(sql, args)}


def use_fake_model(script) -> FakeClient:
    """Make /api/ask use a scripted model."""
    fake = FakeClient(script)
    main.app.dependency_overrides[main.model_client] = lambda: fake
    return fake


def answers_job_count(params):
    """A scripted model: list the jobs, then state how many there are."""
    last = params["messages"][-1]
    if isinstance(last["content"], str):
        return reply(tool_use("t1", "list_jobs"), stop="tool_use")
    count = json.loads(last["content"][0]["content"])["count"]
    return reply(text(f"You can see {count} jobs."))


# Identity

@pytest.mark.parametrize("path", ["/api/me", "/api/catch-up", "/api/dashboard", "/api/jobs", "/api/jobs/JOB-1", "/api/tasks",
                                  "/api/candidates/APP-001", "/api/sources", "/api/changes", "/api/quality"])
def test_missing_user_gets_401(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert "X-Demo-User" in response.json()["error"]


def test_unknown_user_gets_401(client):
    response = client.get("/api/me", headers=as_user("USR-99"))
    assert response.status_code == 401
    assert "Valid users" in response.json()["error"]


def test_missing_user_on_ask_and_assignment_gets_401(client):
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 401
    assert client.post("/api/jobs/JOB-1/assignment", json={"recruiter_user_id": "USR-5"}).status_code == 401


def test_health_and_users_are_public(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and [c["name"] for c in health["checks"]] == ["Database", "Model API", "Store"]
    users = client.get("/api/users").json()["users"]
    assert [u["user_id"] for u in users] == USERS
    assert all(set(u) == {"user_id", "name", "role"} for u in users)


def test_role_sent_by_the_client_is_ignored(client):
    response = client.get("/api/jobs", headers={**as_user("USR-4"), "X-Role": "admin"})
    assert {j["job_id"] for j in response.json()["jobs"]} == {"JOB-1", "JOB-5", "JOB-7"}


# Scope

@pytest.mark.parametrize("user_id", USERS)
def test_each_role_sees_only_its_jobs(client, db, user_id):
    allowed = expected_jobs(db, user_id)
    jobs = client.get("/api/jobs", headers=as_user(user_id)).json()["jobs"]
    assert {j["job_id"] for j in jobs} == allowed
    me = client.get("/api/me", headers=as_user(user_id)).json()
    assert set(me["allowed_job_ids"]) == allowed
    assert {j["job_id"] for j in me["scope"]["jobs"]} == allowed
    tasks = client.get("/api/tasks", headers=as_user(user_id)).json()["tasks"]
    assert {t["job_id"] for t in tasks} <= allowed
    for job_id in sorted({r[0] for r in db.execute("SELECT job_id FROM jobs")}):
        status = client.get(f"/api/jobs/{job_id}", headers=as_user(user_id)).status_code
        assert status == (200 if job_id in allowed else 404)


@pytest.mark.parametrize("user_id", USERS)
def test_candidates_outside_scope_are_404(client, db, user_id):
    allowed = expected_jobs(db, user_id)
    rows = db.execute("SELECT application_id, job_id FROM applications ORDER BY application_id").fetchall()
    inside = next((a for a, j in rows if j in allowed), None)
    outside = next((a for a, j in rows if j not in allowed), None)
    if inside:
        body = client.get(f"/api/candidates/{inside}", headers=as_user(user_id)).json()
        assert body["contact"] == {"email": "[email hidden]", "phone": "[phone hidden]"}
    if outside:
        response = client.get(f"/api/candidates/{outside}", headers=as_user(user_id))
        assert response.status_code == 404
        assert response.json() == {"error": f"{outside} is not in your scope"}
    missing = client.get("/api/candidates/APP-999", headers=as_user(user_id))
    assert missing.status_code == 404 and missing.json() == {"error": "APP-999 is not in your scope"}


def test_dashboard_filters_are_scoped_and_validated(client):
    body = client.get("/api/dashboard?team=TEAM-1", headers=as_user("USR-2")).json()
    assert body["filters"] == {"team_id": "TEAM-1"}
    assert body["recruiter_load"] is not None
    assert client.get("/api/dashboard", headers=as_user("USR-4")).json()["recruiter_load"] is None
    assert client.get("/api/dashboard?job=JOB-3", headers=as_user("USR-2")).status_code == 404
    bad = client.get("/api/dashboard?from=last-week", headers=as_user("USR-1"))
    assert bad.status_code == 422 and bad.json()["details"][0]["field"] == "from"


def test_health_includes_live_checks(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(main.checks, "_model_check", {})
    body = client.get("/api/health").json()
    assert [c["name"] for c in body["checks"]] == ["Database", "Model API", "Store"]
    assert body["checks"][1]["status"] == "not_configured"


def test_sources_are_full_for_admin_summary_for_managers_and_hidden_from_hr_users(client):
    admin = client.get("/api/sources", headers=as_user("USR-1")).json()
    assert admin["integrations_view"] == "full" and "error_rate_24h_pct" in admin["integrations"][0]
    assert admin["source_quality"]["metric"] == "source_quality"
    manager = client.get("/api/sources", headers=as_user("USR-2")).json()
    assert manager["integrations_view"] == "summary"
    assert all(set(i) == {"integration", "status", "last_sync", "mode", "simulated"} for i in manager["integrations"])
    assert client.get("/api/sources", headers=as_user("USR-4")).status_code == 404


def test_errors_are_friendly_json(client, monkeypatch):
    def boom(*_):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(main.scope, "list_jobs", boom)
    response = client.get("/api/jobs", headers=as_user("USR-1"))
    assert response.status_code == 500
    assert "secret" not in response.text and "Traceback" not in response.text


# Reassignment

def test_job_detail_says_who_may_reassign(client):
    admin = client.get("/api/jobs/JOB-3", headers=as_user("USR-1")).json()
    assert admin["can_reassign"] and {o["user_id"] for o in admin["reassign_options"]} == {"USR-4", "USR-5"}
    manager = client.get("/api/jobs/JOB-1", headers=as_user("USR-2")).json()
    assert manager["can_reassign"]
    user = client.get("/api/jobs/JOB-1", headers=as_user("USR-4")).json()
    assert not user["can_reassign"] and user["reassign_options"] == []


def test_admin_reassigns_any_job_and_a_change_is_written(client):
    response = client.post("/api/jobs/JOB-3/assignment", headers=as_user("USR-1"),
                           json={"recruiter_user_id": "USR-4"})
    assert response.status_code == 200
    assert response.json()["recruiter_user_id"] == "USR-4"
    change = client.get("/api/changes", headers=as_user("USR-1")).json()["changes"][0]
    assert {k: change[k] for k in ("change_id", "type", "job_id", "user_id", "from_recruiter_user_id",
                                   "to_recruiter_user_id")} == {
        "change_id": "CHG-001", "type": "reassignment", "job_id": "JOB-3", "user_id": "USR-1",
        "from_recruiter_user_id": "USR-6", "to_recruiter_user_id": "USR-4"}
    assert change["at"].endswith("Z")
    # The new recruiter now sees the job; the old one does not.
    assert client.get("/api/jobs/JOB-3", headers=as_user("USR-4")).status_code == 200
    assert client.get("/api/jobs/JOB-3", headers=as_user("USR-6")).status_code == 404


def test_manager_reassigns_only_own_teams_and_only_to_recruiters(client):
    ok = client.post("/api/jobs/JOB-2/assignment", headers=as_user("USR-2"), json={"recruiter_user_id": "USR-6"})
    assert ok.status_code == 200
    other_team = client.post("/api/jobs/JOB-3/assignment", headers=as_user("USR-2"),
                             json={"recruiter_user_id": "USR-4"})
    assert other_team.status_code == 404
    to_manager = client.post("/api/jobs/JOB-1/assignment", headers=as_user("USR-2"),
                             json={"recruiter_user_id": "USR-3"})
    assert to_manager.status_code == 400 and "Valid recruiters: USR-4, USR-5, USR-6" in to_manager.json()["error"]
    same = client.post("/api/jobs/JOB-2/assignment", headers=as_user("USR-2"), json={"recruiter_user_id": "USR-6"})
    assert same.status_code == 400
    assert [c["job_id"] for c in client.get("/api/changes", headers=as_user("USR-1")).json()["changes"]] == ["JOB-2"]


def test_hr_user_cannot_reassign(client):
    response = client.post("/api/jobs/JOB-1/assignment", headers=as_user("USR-4"),
                           json={"recruiter_user_id": "USR-5"})
    assert response.status_code == 403
    assert client.get("/api/changes", headers=as_user("USR-1")).json()["changes"] == []


def test_assignment_body_is_validated(client):
    extra = client.post("/api/jobs/JOB-1/assignment", headers=as_user("USR-1"),
                        json={"recruiter_user_id": "USR-5", "role": "admin"})
    assert extra.status_code == 422
    assert client.post("/api/jobs/JOB-1/assignment", headers=as_user("USR-1"), json={}).status_code == 422


def test_change_log_is_scoped(client):
    client.post("/api/jobs/JOB-3/assignment", headers=as_user("USR-1"), json={"recruiter_user_id": "USR-5"})
    seen = lambda user: [c["job_id"] for c in client.get("/api/changes", headers=as_user(user)).json()["changes"]]
    assert seen("USR-1") == ["JOB-3"]
    assert seen("USR-3") == ["JOB-3"]    # manages TEAM-3
    assert seen("USR-2") == []           # does not
    # The changes page is for admin and hr_manager; HR Users get a 404.
    assert all(client.get("/api/changes", headers=as_user(u)).status_code == 404 for u in ("USR-4", "USR-5", "USR-6"))



@pytest.mark.parametrize("user_id", USERS)
def test_quality_is_admin_only_with_the_out_of_scope_answer(client, user_id):
    response = client.get("/api/quality", headers=as_user(user_id))
    if user_id == "USR-1":
        assert response.status_code == 200 and "tests_defined" in response.json()
    else:
        # The same 404 shape an out-of-scope job gets.
        job = client.get("/api/jobs/JOB-999", headers=as_user(user_id))
        assert response.status_code == job.status_code == 404
        assert response.json() == {"error": "/api/quality is not in your scope"}
        assert set(response.json()) == set(job.json())


# Ask

def test_ask_runs_the_agent_and_logs_no_question_text(client):
    use_fake_model(answers_job_count)
    response = client.post("/api/ask", headers=as_user("USR-4"), json={"question": "How many jobs can I see?"})
    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == "You can see 3 jobs." and body["source"] == "live" and body["verified"]
    change = client.get("/api/changes", headers=as_user("USR-1")).json()["changes"][0]
    assert change["type"] == "ask" and change["user_id"] == "USR-4" and change["tools"] == ["list_jobs"] and len(change["question_sha256"]) == 64
    assert "How many" not in str(change)


def test_ask_rejects_out_of_scope_job_and_bad_bodies(client):
    use_fake_model(answers_job_count)
    assert client.post("/api/ask", headers=as_user("USR-4"), json={"question": "x", "job_id": "JOB-2"}).status_code == 404
    assert client.post("/api/ask", headers=as_user("USR-4"), json={"question": ""}).status_code == 422
    assert client.post("/api/ask", headers=as_user("USR-4"),
                       json={"question": "x", "history": [{"question": "a", "answer": "b", "tool": "c"}]}
                       ).status_code == 422


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    """Point the recordings at a file in tmp_path holding one answer for USR-4."""
    monkeypatch.setattr(recordings, "RECORDINGS", tmp_path / "recordings.json")
    result = {"answer": "Recorded: 3 jobs.", "steps": [{"tool": "list_jobs"}], "citations": [],
              "verified": True, "source": "live"}
    recordings.save("How many jobs can I see?", "USR-4", None, ["JOB-1", "JOB-5", "JOB-7"], result,
                    "2026-11-09T00:00:00Z")


def test_ip_limit_falls_back_to_a_matching_recording(client, recorded):
    fake = use_fake_model(answers_job_count)
    ask = lambda q: client.post("/api/ask", headers=as_user("USR-4"), json={"question": q})
    assert all(ask("How many jobs can I see?").json()["source"] == "live" for _ in range(10))
    calls = len(fake.requests)
    over = ask("how many jobs can i see")
    assert over.status_code == 200 and over.json()["source"] == "recording"
    assert over.json()["answer"] == "Recorded: 3 jobs." and over.json()["recording_reason"] == "live_limit"
    assert len(fake.requests) == calls
    unrecorded = ask("Which tasks are overdue?")
    assert unrecorded.status_code == 429 and "limit" in unrecorded.json()["error"]


def test_ip_limit_is_per_ip(client):
    use_fake_model(answers_job_count)
    ask = lambda ip: client.post("/api/ask", headers={**as_user("USR-4"), "X-Forwarded-For": ip},
                                 json={"question": "How many jobs can I see?"})
    assert all(ask("203.0.113.1").status_code == 200 for _ in range(10))
    assert ask("203.0.113.1").status_code == 429
    assert ask("203.0.113.2").status_code == 200


def test_daily_cap_falls_back(client, recorded, monkeypatch):
    monkeypatch.setenv("DAILY_LIVE_CAP", "2")
    use_fake_model(answers_job_count)
    ask = lambda ip: client.post("/api/ask", headers={**as_user("USR-4"), "X-Forwarded-For": ip},
                                 json={"question": "How many jobs can I see?"}).json()["source"]
    assert [ask("198.51.100.1"), ask("198.51.100.2"), ask("198.51.100.3")] == ["live", "live", "recording"]


def test_recordings_do_not_cross_users_or_scopes(client, recorded):
    main.app.dependency_overrides[main.model_client] = lambda: None
    ok = client.post("/api/ask", headers=as_user("USR-4"), json={"question": "How many jobs can I see?"})
    assert ok.json()["source"] == "recording"
    other = client.post("/api/ask", headers=as_user("USR-5"), json={"question": "How many jobs can I see?"})
    assert other.status_code == 503
    client.post("/api/jobs/JOB-1/assignment", headers=as_user("USR-1"), json={"recruiter_user_id": "USR-5"})
    moved = client.post("/api/ask", headers=as_user("USR-4"), json={"question": "How many jobs can I see?"})
    assert moved.status_code == 503


INTERNAL_KEYS = {"steps", "usage", "latency_ms", "estimated_cost_usd", "provider", "effort",
                 "served_by", "retried", "verifier"}


def answers_with_a_tool_input(params):
    """A scripted model: call pending_tasks with an owner filter, then answer."""
    last = params["messages"][-1]
    if isinstance(last["content"], str):
        return reply(tool_use("t1", "pending_tasks", {"owner_user_id": "USR-4"}), stop="tool_use")
    return reply(text("Here are your tasks."))


def all_keys(value) -> set[str]:
    """Every dict key anywhere in a JSON value."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in all_keys(v)}
    return set()


@pytest.mark.parametrize("user_id", ["USR-2", "USR-4"])
def test_ask_hides_behind_the_scenes_from_non_admins(client, user_id):
    use_fake_model(answers_with_a_tool_input)
    response = client.post("/api/ask", headers=as_user(user_id), json={"question": "What is pending?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Here are your tasks." and body["source"] == "live" and "verified" in body
    assert not all_keys(body) & INTERNAL_KEYS
    assert "owner_user_id" not in response.text and "USR-4" not in response.text
    # The change log still records the tools used from the full result.
    change = client.get("/api/changes", headers=as_user("USR-1")).json()["changes"][0]
    assert change["tools"] == ["pending_tasks"]


def test_ask_shows_behind_the_scenes_to_admin(client):
    use_fake_model(answers_with_a_tool_input)
    body = client.post("/api/ask", headers=as_user("USR-1"), json={"question": "What is pending?"}).json()
    assert body["steps"][0]["tool"] == "pending_tasks"
    assert body["steps"][0]["input"] == {"owner_user_id": "USR-4"}
    assert body["usage"]["api_calls"] == 2 and "verifier" in body


def test_recorded_answers_are_redacted_for_non_admins(client, recorded):
    main.app.dependency_overrides[main.model_client] = lambda: None
    body = client.post("/api/ask", headers=as_user("USR-4"), json={"question": "How many jobs can I see?"}).json()
    assert body["source"] == "recording" and body["recorded_at"] == "2026-11-09T00:00:00Z"
    assert body["recording_reason"] == "live_unavailable" and "steps" not in body


def test_ask_accepts_history_citations_and_rejects_bad_ones(client):
    fake = use_fake_model(answers_job_count)
    turn = {"question": "How many jobs?", "answer": "3 jobs.", "citations": ["JOB-1", "APP-062"]}
    ok = client.post("/api/ask", headers=as_user("USR-4"), json={"question": "And now?", "history": [turn]})
    assert ok.status_code == 200
    assert "Records cited: JOB-1, APP-062" in fake.requests[0]["messages"][0]["content"]
    bad = {**turn, "citations": ["not an id"]}
    assert client.post("/api/ask", headers=as_user("USR-4"),
                       json={"question": "x", "history": [bad]}).status_code == 422
    too_many = {**turn, "citations": [f"APP-{n:03d}" for n in range(51)]}
    assert client.post("/api/ask", headers=as_user("USR-4"),
                       json={"question": "x", "history": [too_many]}).status_code == 422
