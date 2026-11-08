"""pending_tasks against the answer key and hand-built cases at each rule's threshold.

tiny.AS_OF is Monday 2026-11-09 17:00 UTC.
"""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import tiny
from app import access, store
from app.logic import tasks

RECENT = "2026-11-08T17:00:00Z"  # one day before AS_OF: never stuck in stage


def admin():
    """The admin principal for whichever database is in use."""
    return access.principal_for("USR-1")


def found(result, key: str = "rule_id") -> list[str]:
    """The rule_id (or task_id) of every item, in order."""
    return [t.get(key) for t in result["tasks"]]


# --- committed data -----------------------------------------------------------

def test_people_role_matches_the_answer_key(answers):
    expected = answers["people-overdue"]
    result = tasks.pending_tasks(admin(), job_id=expected["job_id"])
    overdue = [t["task_id"] for t in result["tasks"] if t["status"] == "overdue"]
    pending = [t["task_id"] for t in result["tasks"] if t["status"] == "pending"]
    assert sorted(overdue) == sorted(t["task_id"] for t in expected["overdue_tasks"])
    assert sorted(pending) == sorted(t["task_id"] for t in expected["not_yet_due_tasks"])
    evidence = {e for t in result["tasks"] for e in t["evidence"]}
    assert {m["interview_id"] for m in expected["missing_scorecards"]} <= evidence
    assert {o["email_id"] for o in expected["offers_awaiting_response"]} <= evidence


def test_explicit_tasks_match_sql(db, as_of):
    open_tasks = {r[0]: r[1] for r in db.execute(
        "SELECT task_id, due_at FROM tasks WHERE status = 'open'")}
    result = tasks.pending_tasks(admin())
    got = {t["task_id"]: t for t in result["tasks"] if t.get("task_id")}
    assert set(got) == set(open_tasks)
    for task_id, due in open_tasks.items():
        assert got[task_id]["status"] == ("overdue" if due < as_of else "pending")


def test_sorted_by_days_overdue():
    days = [t["days_overdue"] for t in tasks.pending_tasks(admin())["tasks"]]
    assert days == sorted(days, reverse=True)


def test_unknown_owner_lists_valid_users():
    with pytest.raises(ToolError, match=r"Unknown owner_user_id 'USR-9'\. Valid users: USR-1"):
        tasks.pending_tasks(admin(), owner_user_id="USR-9")


# --- thresholds -----------------------------------------------------------------

def onsite_app(data, app_id: str, entered: str = RECENT, job_id: str = "JOB-1") -> None:
    """An active application that entered Onsite at `entered`."""
    tiny.add_application(data, app_id, job_id, [
        ("Applied", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "advanced"),
        ("Onsite", entered, None, None)])


@pytest.mark.parametrize("completed, fires", [
    ("2026-11-07T17:00:00Z", False),   # exactly 48 hours
    ("2026-11-07T16:59:59Z", True),    # one second more
])
def test_missing_scorecard_threshold(use_db, completed, fires):
    data = tiny.base()
    onsite_app(data, "APP-1")
    tiny.add_interview(data, "INT-1", "APP-1", "Onsite", completed)
    use_db(data)
    assert found(tasks.pending_tasks(admin())) == (["RULE-SCORECARD-48H"] if fires else [])


def test_scorecard_submitted_after_as_of_still_counts_as_missing(use_db):
    data = tiny.base()
    onsite_app(data, "APP-1")
    tiny.add_interview(data, "INT-1", "APP-1", "Onsite", "2026-11-01T00:00:00Z", "yes",
                       submitted_at="2026-11-10T00:00:00Z")
    use_db(data)
    item = tasks.pending_tasks(admin())["tasks"][0]
    assert (item["rule_id"], item["evidence"]) == ("RULE-SCORECARD-48H", ["INT-1", "APP-1"])
    assert item["owner_user_id"] == "USR-3"  # the job's recruiter


def inbound(data, email_id: str, app_id: str, sent: str) -> None:
    """An inbound candidate email."""
    data["emails"].append({"email_id": email_id, "application_id": app_id, "direction": "inbound",
                           "sent_at": sent, "sender": "person@example.com", "subject": "Question",
                           "body": "Hello"})


@pytest.mark.parametrize("sent, fires", [
    ("2026-11-05T17:00:00Z", False),   # Thursday: exactly 2 business days before Monday 17:00
    ("2026-11-05T16:59:59Z", True),
    ("2026-11-06T09:00:00Z", False),   # Friday: 3 calendar days, but only 1 business day
])
def test_unanswered_email_threshold_uses_business_days(use_db, sent, fires):
    data = tiny.base()
    onsite_app(data, "APP-1")
    inbound(data, "EM-1", "APP-1", sent)
    use_db(data)
    assert found(tasks.pending_tasks(admin())) == (["RULE-REPLY-2BD"] if fires else [])


def test_a_reply_clears_the_email_rule(use_db):
    data = tiny.base()
    onsite_app(data, "APP-1")
    inbound(data, "EM-1", "APP-1", "2026-11-02T09:00:00Z")
    data["emails"].append({"email_id": "EM-2", "application_id": "APP-1", "direction": "outbound",
                           "sent_at": "2026-11-02T10:00:00Z", "sender": "rae@example.com",
                           "subject": "Re: Question", "body": "Hi"})
    use_db(data)
    assert found(tasks.pending_tasks(admin())) == []


@pytest.mark.parametrize("entered, fires", [
    ("2026-11-02T17:00:00Z", False),   # exactly 7 days
    ("2026-11-02T16:59:59Z", True),
])
def test_stuck_in_stage_threshold(use_db, entered, fires):
    data = tiny.base()
    onsite_app(data, "APP-1", entered=entered)
    use_db(data)
    assert found(tasks.pending_tasks(admin())) == (["RULE-STAGE-7D"] if fires else [])


def offer_app(data, entered: str) -> None:
    """An active application that entered Offer at `entered`, with the offer email an hour later."""
    tiny.add_application(data, "APP-1", "JOB-1", [
        ("Applied", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "advanced"),
        ("Offer", entered, None, None)])
    data["emails"].append({"email_id": "EM-1", "application_id": "APP-1", "direction": "outbound",
                           "sent_at": entered.replace("T17:", "T18:"), "sender": "rae@example.com",
                           "subject": "Your offer", "body": "Offer attached."})


@pytest.mark.parametrize("entered, fires", [
    ("2026-11-04T17:00:00Z", False),   # exactly 5 days
    ("2026-11-04T16:59:59Z", True),
])
def test_unanswered_offer_threshold(use_db, entered, fires):
    data = tiny.base()
    offer_app(data, entered)
    use_db(data)
    assert found(tasks.pending_tasks(admin())) == (["RULE-OFFER-5D"] if fires else [])


def test_offer_with_a_reply_is_not_flagged_and_offer_is_not_stuck(use_db):
    data = tiny.base()
    offer_app(data, "2026-10-20T17:00:00Z")  # 20 days in Offer
    inbound(data, "EM-2", "APP-1", "2026-10-21T09:00:00Z")
    data["emails"].append({"email_id": "EM-3", "application_id": "APP-1", "direction": "outbound",
                           "sent_at": "2026-10-21T10:00:00Z", "sender": "rae@example.com",
                           "subject": "Re", "body": "Thanks"})
    use_db(data)
    assert found(tasks.pending_tasks(admin())) == []


# --- explicit tasks ---------------------------------------------------------------

def task(task_id: str, due: str, app_id: str | None = "APP-1", type_: str = "review",
         created: str = "2026-11-01T00:00:00Z", completed: str | None = None, owner: str = "USR-3") -> dict:
    """One tasks row."""
    return {"task_id": task_id, "application_id": app_id, "job_id": "JOB-1", "owner_user_id": owner,
            "type": type_, "title": f"Task {task_id}", "due_at": due,
            "status": "done" if completed else "open", "created_at": created, "completed_at": completed}


def test_explicit_task_status_at_the_due_time(use_db):
    data = tiny.base()
    onsite_app(data, "APP-1")
    data["tasks"] += [task("TASK-1", tiny.AS_OF), task("TASK-2", "2026-11-08T17:00:00Z"),
                      task("TASK-3", "2026-11-01T00:00:00Z", created="2026-11-10T00:00:00Z"),
                      task("TASK-4", "2026-11-07T17:00:00Z", completed="2026-11-10T00:00:00Z"),
                      task("TASK-5", "2026-11-07T17:00:00Z", completed="2026-11-09T00:00:00Z")]
    use_db(data)
    items = {t["task_id"]: t for t in tasks.pending_tasks(admin())["tasks"]}
    assert set(items) == {"TASK-1", "TASK-2", "TASK-4"}  # TASK-3 not created yet, TASK-5 already done
    assert (items["TASK-1"]["status"], items["TASK-1"]["days_overdue"]) == ("pending", 0.0)
    assert (items["TASK-2"]["status"], items["TASK-2"]["days_overdue"]) == ("overdue", 1.0)
    assert (items["TASK-4"]["status"], items["TASK-4"]["days_overdue"]) == ("overdue", 2.0)
    assert found(tasks.pending_tasks(admin()), "task_id") == ["TASK-4", "TASK-2", "TASK-1"]


def test_derived_task_folds_into_a_matching_explicit_task(use_db):
    data = tiny.base()
    onsite_app(data, "APP-1")
    tiny.add_interview(data, "INT-1", "APP-1", "Onsite", "2026-11-01T00:00:00Z")
    data["tasks"].append(task("TASK-1", "2026-11-03T00:00:00Z", type_="scorecard"))
    use_db(data)
    result = tasks.pending_tasks(admin())
    assert result["count"] == 1
    item = result["tasks"][0]
    assert (item["task_id"], item["matched_rule_id"]) == ("TASK-1", "RULE-SCORECARD-48H")
    assert item["evidence"] == ["APP-1", "INT-1", "TASK-1"]


def test_owner_filter_and_reassigned_recruiter(use_db):
    data = tiny.base()
    onsite_app(data, "APP-1", entered="2026-10-20T00:00:00Z")
    data["tasks"].append(task("TASK-1", "2026-11-01T00:00:00Z", owner="USR-1"))
    use_db(data)
    assert found(tasks.pending_tasks(admin(), owner_user_id="USR-3")) == ["RULE-STAGE-7D"]
    assert found(tasks.pending_tasks(admin(), owner_user_id="USR-1"), "task_id") == ["TASK-1"]
    store.set_assignment("JOB-1", "USR-2", "USR-1")
    assert found(tasks.pending_tasks(admin(), owner_user_id="USR-2")) == ["RULE-STAGE-7D"]


def test_empty_role_has_no_tasks(use_db):
    use_db(tiny.base())
    assert tasks.pending_tasks(admin(), job_id="JOB-3")["tasks"] == []
