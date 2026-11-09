"""public_result: admin gets the ask result unchanged, other roles only the listed answer fields."""

from app.agent.redact import public_result

FULL = {
    "answer": "Two tasks are overdue [TASK-012].", "status": "answered", "verified": True,
    "label": "verified", "citations": ["TASK-012"], "model": "m", "as_of": "2026-11-09T17:00:00Z",
    "job_id": None, "source": "recording", "recording_reason": "live_limit",
    "recorded_at": "2026-11-09T00:00:00Z",
    "steps": [{"tool": "pending_tasks", "input": {"owner_user_id": "USR-4"}}],
    "usage": {"api_calls": 2}, "latency_ms": 900, "estimated_cost_usd": 0.01, "provider": "anthropic",
    "effort": "low", "served_by": "m", "retried": False, "verifier": {"passed": True, "failures": []},
    "a_field_added_later": "internal",
}

PUBLIC = {"answer", "status", "verified", "label", "citations", "model", "as_of", "job_id",
          "source", "recording_reason", "recorded_at"}


def test_admin_gets_everything():
    assert public_result(FULL, "admin") == FULL


def test_other_roles_get_only_the_answer_fields():
    for role in ("hr_manager", "hr_user"):
        shown = public_result(FULL, role)
        assert set(shown) == PUBLIC
        assert all(shown[k] == FULL[k] for k in PUBLIC)


def test_unknown_fields_are_hidden_and_missing_fields_are_skipped():
    shown = public_result({"answer": "a", "a_field_added_later": 1}, "hr_user")
    assert shown == {"answer": "a"}


def test_the_input_is_not_changed():
    copy = dict(FULL)
    public_result(FULL, "hr_user")
    assert FULL == copy
