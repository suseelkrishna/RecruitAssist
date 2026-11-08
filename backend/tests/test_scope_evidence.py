"""scope_card, list_jobs, and get_candidate_evidence: contents, masking, wrapping, and truncation."""

from __future__ import annotations

import json
import re

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import tiny
from app import access
from app.logic import evidence, scope, tasks


def admin():
    """The admin principal for whichever database is in use."""
    return access.principal_for("USR-1")


def test_scope_card_lists_active_candidates_per_job(db):
    card = scope.scope_card(admin())
    want = {}
    for app_id, job_id, name in db.execute(
            "SELECT a.application_id, a.job_id, c.full_name FROM applications a "
            "JOIN candidates c USING (candidate_id) WHERE a.status = 'active'"):
        want.setdefault(job_id, []).append([app_id, name])
    got = {j["job_id"]: j["active_candidates"] for j in card["jobs"] if j["active_candidates"]}
    assert got == {k: sorted(v) for k, v in want.items()}
    for job in card["jobs"]:
        assert sum(job["active_by_stage"].values()) == len(job["active_candidates"])
    assert card["overdue_items"] == tasks.pending_tasks(admin())["overdue_count"]


def test_scope_card_is_compact():
    """About 1 to 2K tokens: under 8,000 characters of JSON for the widest scope."""
    assert len(json.dumps(scope.scope_card(admin()))) < 8000


def test_scope_card_for_one_job():
    card = scope.scope_card(access.principal_for("USR-6"), "JOB-3")
    assert [j["job_id"] for j in card["jobs"]] == ["JOB-3"]
    assert card["role"] == "hr_user"


def test_list_jobs_recruiter_and_days_open(db, as_of):
    jobs = {j["job_id"]: j for j in scope.list_jobs(admin())["jobs"]}
    for job_id, recruiter in db.execute("SELECT job_id, recruiter_user_id FROM job_assignments"):
        assert jobs[job_id]["recruiter_user_id"] == recruiter
    assert jobs["JOB-1"]["days_open"] == 125.0  # 2026-07-07 17:00 to 2026-11-09 17:00


def test_evidence_masks_contacts_everywhere():
    result = evidence.get_candidate_evidence(admin(), "APP-097")
    text = json.dumps(result)
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    assert not re.search(r"\b555-01\d\d\b", text)
    assert result["contact"] == {"email": "[email hidden]", "phone": "[phone hidden]"}


def test_injected_email_is_wrapped_as_untrusted_text():
    emails = evidence.get_candidate_evidence(admin(), "APP-097", ["emails"])["emails"]
    planted = next(e for e in emails if e["email_id"] == "EM-062")
    assert set(planted["body"]) == {"untrusted_text"}
    assert "SYSTEM:" in planted["body"]["untrusted_text"]
    assert planted["sender"] == "candidate"
    staff = next(e for e in emails if e["direction"] == "outbound")
    assert staff["sender"] == "Sam Rivera"


def test_sections_limit_the_result():
    result = evidence.get_candidate_evidence(admin(), "APP-068", ["scorecards"])
    assert "scorecards" in result and not {"cv", "emails", "history"} & set(result)
    assert all(set(s["notes"]) == {"untrusted_text"} for s in result["scorecards"])


def test_unknown_section_lists_valid_sections():
    with pytest.raises(ToolError, match="Valid sections: cv, scorecards, emails, history"):
        evidence.get_candidate_evidence(admin(), "APP-068", ["salary"])


def test_missing_scorecard_is_reported(answers):
    trap = answers["process-top3"]["trap_b_missing_onsite_scorecard"]["application_id"]
    result = evidence.get_candidate_evidence(admin(), trap, ["scorecards"])
    assert result["missing"] and result["missing"][0].startswith("No scorecard for INT-")


def test_long_cv_is_truncated_with_a_note_and_contacts_in_text_are_masked(use_db):
    data = tiny.base()
    long_cv = "Reach me at person1@example.com or 555-0123. " + "x" * 2000
    tiny.add_application(data, "APP-1", "JOB-1", [("Applied", "2026-10-01T00:00:00Z", None, None)],
                         cv_text=long_cv)
    use_db(data)
    cv = evidence.get_candidate_evidence(admin(), "APP-1", ["cv"])["cv"]
    assert cv["truncated"] is True
    assert len(cv["untrusted_text"]) == evidence.TEXT_LIMITS["cv"]
    assert cv["note"].startswith(f"Truncated to {evidence.TEXT_LIMITS['cv']} of ")
    assert cv["untrusted_text"].startswith("Reach me at [email hidden] or [phone hidden].")


def test_short_text_is_not_marked_truncated():
    assert evidence.untrusted("short", 10) == {"untrusted_text": "short"}
    assert evidence.untrusted("x" * 10, 10) == {"untrusted_text": "x" * 10}  # exactly at the limit
