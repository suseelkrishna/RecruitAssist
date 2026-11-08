"""The evidence behind one application: CV, scorecards, emails, and stage history.

Contact details are masked everywhere. Free text written by candidates or
interviewers is wrapped as {"untrusted_text": ...} so the model treats it as
data, and long text is cut with a note saying so.
"""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app import db
from app.access import Principal
from app.logic.common import require_application, resolve_as_of

SECTIONS = ["cv", "scorecards", "emails", "history"]
TEXT_LIMITS = {"cv": 1500, "notes": 600, "body": 1000}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Seven-digit numbers such as 555-0123, with an optional area code such as (608) or 608-.
PHONE_RE = re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[-. ])?\b\d{3}[-. ]\d{4}\b")


def mask_contacts(text: str) -> str:
    """Replace every email address and phone number in text with a fixed marker."""
    return PHONE_RE.sub("[phone hidden]", EMAIL_RE.sub("[email hidden]", text))


def untrusted(text: str, limit: int) -> dict[str, Any]:
    """Masked free text wrapped as untrusted_text, cut to `limit` characters with a note if longer."""
    text = mask_contacts(text)
    if len(text) <= limit:
        return {"untrusted_text": text}
    return {"untrusted_text": text[:limit], "truncated": True,
            "note": f"Truncated to {limit} of {len(text)} characters."}


def get_candidate_evidence(principal: Principal, application_id: str, sections: list[str] | None = None,
                           as_of: str | None = None) -> dict[str, Any]:
    """The requested evidence sections for one in-scope application. All sections when sections is None."""
    app = require_application(principal, application_id)
    sections = SECTIONS if sections is None else sections
    unknown = [s for s in sections if s not in SECTIONS]
    if unknown or not sections:
        problem = f"Unknown sections {unknown}." if unknown else "Choose at least one section."
        raise ToolError(f"{problem} Valid sections: {', '.join(SECTIONS)}.")
    as_of = resolve_as_of(as_of)
    params = {"app": application_id, "as_of": as_of}

    result: dict[str, Any] = {
        "application_id": application_id,
        "candidate_id": app["candidate_id"],
        "job_id": app["job_id"],
        "full_name": app["full_name"],
        "current_title": app["current_title"],
        "location": app["location"],
        "source": app["source"],
        "years_experience": app["years_experience"],
        "current_stage": app["current_stage"],
        "status": app["status"],
        "contact": {"email": "[email hidden]", "phone": "[phone hidden]"},
        "as_of": as_of,
        "missing": [],
    }
    if "cv" in sections:
        result["cv"] = untrusted(app["cv_text"], TEXT_LIMITS["cv"])
    if "scorecards" in sections:
        result["scorecards"] = scorecards(params)
        result["missing"] += [f"No scorecard for {i['interview_id']} ({i['stage']}, completed {i['completed_at']})"
                              for i in db.rows("""
            SELECT i.interview_id, i.stage, i.completed_at FROM interviews i
            LEFT JOIN scorecards s ON s.interview_id = i.interview_id AND s.submitted_at <= :as_of
            WHERE i.application_id = :app AND i.completed_at <= :as_of AND s.scorecard_id IS NULL
            ORDER BY i.interview_id""", params)]
    if "emails" in sections:
        result["emails"] = emails(params)
    if "history" in sections:
        result["history"] = history(app, params)
    return result


def scorecards(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Scorecards submitted by as_of, with the interviewer's notes as untrusted text."""
    return [{
        "scorecard_id": r["scorecard_id"],
        "interview_id": r["interview_id"],
        "stage": r["stage"],
        "interviewer": r["interviewer"],
        "submitted_at": r["submitted_at"],
        "overall": r["overall"],
        "ratings": json.loads(r["ratings_json"]),
        "notes": untrusted(r["notes"], TEXT_LIMITS["notes"]),
    } for r in db.rows("""
        SELECT s.scorecard_id, s.interview_id, i.stage, s.interviewer, s.submitted_at,
               s.overall, s.ratings_json, s.notes
        FROM scorecards s JOIN interviews i ON i.interview_id = s.interview_id
        WHERE i.application_id = :app AND s.submitted_at <= :as_of
        ORDER BY s.submitted_at, s.scorecard_id""", params)]


def emails(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Emails sent by as_of. Staff senders are shown by name, candidates as "candidate"."""
    staff = {u["email"]: u["name"] for u in db.rows("SELECT email, name FROM users")}
    return [{
        "email_id": r["email_id"],
        "direction": r["direction"],
        "sent_at": r["sent_at"],
        "sender": staff.get(r["sender"], "candidate"),
        "subject": untrusted(r["subject"], TEXT_LIMITS["body"]),
        "body": untrusted(r["body"], TEXT_LIMITS["body"]),
    } for r in db.rows("""
        SELECT email_id, direction, sent_at, sender, subject, body FROM emails
        WHERE application_id = :app AND sent_at <= :as_of
        ORDER BY sent_at, email_id""", params)]


def history(app: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Stage events and interviews up to as_of, plus the application's outcome if it has one."""
    events = db.rows("""
        SELECT event_id, stage, entered_at,
               CASE WHEN exited_at <= :as_of THEN exited_at END AS exited_at,
               CASE WHEN exited_at <= :as_of THEN exit_type END AS exit_type
        FROM stage_events WHERE application_id = :app AND entered_at <= :as_of
        ORDER BY entered_at, event_id""", params)
    interviews = db.rows("""
        SELECT interview_id, stage, interviewer, scheduled_at,
               CASE WHEN completed_at <= :as_of THEN completed_at END AS completed_at
        FROM interviews WHERE application_id = :app AND scheduled_at <= :as_of
        ORDER BY scheduled_at, interview_id""", params)
    outcome = None
    if app["outcome_at"] is not None and app["outcome_at"] <= params["as_of"]:
        outcome = {"status": app["status"], "reason": app["outcome_reason"], "at": app["outcome_at"]}
    return {"applied_at": app["applied_at"], "stage_events": events, "interviews": interviews,
            "outcome": outcome}
