"""Pending and overdue work: explicit tasks plus tasks derived from the records.

Derived rules (each fires only once its threshold has passed, so a derived
task is always overdue):
  RULE-SCORECARD-48H  a completed interview has no scorecard more than 48 hours later
  RULE-REPLY-2BD      an inbound email has had no outbound reply for more than 2 business days
  RULE-STAGE-7D       an active application has been in the same stage for more than 7 days
                      (the Offer stage is left to RULE-OFFER-5D, which is stricter)
  RULE-OFFER-5D       an offer has had no inbound response for more than 5 days

When an open explicit task already covers the same application and kind of
work, the derived task is folded into it: the explicit task gains the rule's
evidence IDs and a matched_rule_id, so the same work is never listed twice.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app import db
from app.access import Principal, current_recruiters
from app.logic.common import (IN_SCOPE, add_business_days, days_between, format_ts, parse_ts,
                              require_job, resolve_as_of, scope_params)
from app.logic.sources import degraded_sources

RULES = {
    "RULE-SCORECARD-48H": "A completed interview has no scorecard more than 48 hours later.",
    "RULE-REPLY-2BD": "An inbound email has had no reply for more than 2 business days.",
    "RULE-STAGE-7D": "An active application has been in the same stage for more than 7 days.",
    "RULE-OFFER-5D": "An offer has had no response for more than 5 days.",
}

# The records the task list is built from; a degraded integration feeding any of them is reported.
TASK_RECORDS = {"applications and stages", "scorecards", "interview schedules", "candidate emails"}

# The explicit task type that covers the same work as each rule.
RULE_TASK_TYPE = {"RULE-SCORECARD-48H": "scorecard", "RULE-REPLY-2BD": "reply",
                  "RULE-OFFER-5D": "offer_follow_up"}


def pending_tasks(principal: Principal, owner_user_id: str | None = None, job_id: str | None = None,
                  as_of: str | None = None) -> dict[str, Any]:
    """Open explicit tasks and derived tasks in scope, most overdue first."""
    as_of = resolve_as_of(as_of)
    if job_id is not None:
        require_job(principal, job_id)
    users = {u["user_id"]: u["name"] for u in db.rows("SELECT user_id, name FROM users")}
    if owner_user_id is not None and owner_user_id not in users:
        raise ToolError(f"Unknown owner_user_id {owner_user_id!r}. Valid users: {', '.join(sorted(users))}.")

    params = scope_params(principal, as_of=as_of, job=job_id)
    explicit = [explicit_task(t, as_of) for t in db.rows(f"""
        SELECT t.task_id, t.application_id, t.job_id, t.owner_user_id, t.type, t.title, t.due_at
        FROM tasks t
        WHERE t.job_id {IN_SCOPE} AND (:job IS NULL OR t.job_id = :job)
          AND t.created_at <= :as_of AND (t.completed_at IS NULL OR t.completed_at > :as_of)
        ORDER BY t.task_id""", params)]
    recruiters = current_recruiters()
    derived = (missing_scorecards(params) + unanswered_emails(params)
               + stuck_in_stage(params) + unanswered_offers(params))
    derived = [finish_derived(d, recruiters, as_of) for d in derived]

    items = explicit + [d for d in derived if not fold_into_explicit(d, explicit)]
    if owner_user_id is not None:
        items = [i for i in items if i["owner_user_id"] == owner_user_id]
    for item in items:
        item["owner_name"] = users.get(item["owner_user_id"])
    items.sort(key=lambda i: (-i["days_overdue"], i["due_at"], i.get("task_id") or i["rule_id"],
                              i["evidence"]))
    degraded = degraded_sources(TASK_RECORDS, as_of)
    return {
        "as_of": as_of,
        "count": len(items),
        "overdue_count": sum(1 for i in items if i["status"] == "overdue"),
        "tasks": items,
        "rules": RULES,
        "degraded_sources": degraded,
        "warnings": [d["warning"] for d in degraded],
    }


def explicit_task(task: dict[str, Any], as_of: str) -> dict[str, Any]:
    """One row of the tasks table as a task item with status and days_overdue."""
    late = days_between(task["due_at"], as_of)
    return {
        "task_id": task["task_id"],
        "type": task["type"],
        "title": task["title"],
        "job_id": task["job_id"],
        "application_id": task["application_id"],
        "owner_user_id": task["owner_user_id"],
        "due_at": task["due_at"],
        "status": "overdue" if late > 0 else "pending",
        "days_overdue": round(max(late, 0.0), 1),
        "evidence": [i for i in (task["task_id"], task["application_id"]) if i],
    }


def finish_derived(item: dict[str, Any], recruiters: dict[str, str], as_of: str) -> dict[str, Any]:
    """Fill in the owner (the job's current recruiter), status, and days_overdue of a derived task."""
    return {**item, "owner_user_id": recruiters.get(item["job_id"]), "status": "overdue",
            "days_overdue": round(days_between(item["due_at"], as_of), 1)}


def fold_into_explicit(item: dict[str, Any], explicit: list[dict[str, Any]]) -> bool:
    """Attach a derived task to a matching open explicit task. True when one was found."""
    for task in explicit:
        if (task["application_id"] == item["application_id"]
                and task["type"] == RULE_TASK_TYPE.get(item["rule_id"])):
            task["matched_rule_id"] = item["rule_id"]
            task["evidence"] = sorted(set(task["evidence"]) | set(item["evidence"]))
            return True
    return False


def missing_scorecards(params: dict[str, Any]) -> list[dict[str, Any]]:
    """RULE-SCORECARD-48H: completed interviews on active applications with no scorecard after 48 hours."""
    found = db.rows(f"""
        SELECT i.interview_id, i.application_id, i.stage, i.interviewer, i.completed_at,
               a.job_id, c.full_name
        FROM interviews i
        JOIN applications a ON a.application_id = i.application_id
        JOIN candidates c ON c.candidate_id = a.candidate_id
        LEFT JOIN scorecards s ON s.interview_id = i.interview_id AND s.submitted_at <= :as_of
        WHERE a.job_id {IN_SCOPE} AND (:job IS NULL OR a.job_id = :job) AND a.status = 'active'
          AND i.completed_at IS NOT NULL AND i.completed_at <= :as_of AND s.scorecard_id IS NULL""",
        params)
    items = []
    for r in found:
        due = format_ts(parse_ts(r["completed_at"]) + timedelta(hours=48))
        if due < params["as_of"]:
            items.append(derived("RULE-SCORECARD-48H", r, due, [r["interview_id"], r["application_id"]],
                                 f"Collect {r['stage']} scorecard from {r['interviewer']} for {r['full_name']}"))
    return items


def unanswered_emails(params: dict[str, Any]) -> list[dict[str, Any]]:
    """RULE-REPLY-2BD: the oldest inbound email per active application with no later outbound email."""
    found = db.rows(f"""
        SELECT e.email_id, e.application_id, e.sent_at, a.job_id, c.full_name
        FROM emails e
        JOIN applications a ON a.application_id = e.application_id
        JOIN candidates c ON c.candidate_id = a.candidate_id
        WHERE a.job_id {IN_SCOPE} AND (:job IS NULL OR a.job_id = :job) AND a.status = 'active'
          AND e.direction = 'inbound' AND e.sent_at <= :as_of
          AND NOT EXISTS (SELECT 1 FROM emails r
                          WHERE r.application_id = e.application_id AND r.direction = 'outbound'
                            AND r.sent_at > e.sent_at AND r.sent_at <= :as_of)
        ORDER BY e.application_id, e.sent_at""", params)
    items, seen = [], set()
    for r in found:
        if r["application_id"] in seen:
            continue
        seen.add(r["application_id"])
        due = add_business_days(r["sent_at"], 2)
        if due < params["as_of"]:
            items.append(derived("RULE-REPLY-2BD", r, due, [r["email_id"], r["application_id"]],
                                 f"Reply to {r['full_name']}"))
    return items


def stuck_in_stage(params: dict[str, Any]) -> list[dict[str, Any]]:
    """RULE-STAGE-7D: active applications in the same stage (other than Offer) for more than 7 days."""
    found = db.rows(f"""
        SELECT e.event_id, e.application_id, e.stage, e.entered_at, a.job_id, c.full_name
        FROM stage_events e
        JOIN applications a ON a.application_id = e.application_id
        JOIN candidates c ON c.candidate_id = a.candidate_id
        WHERE a.job_id {IN_SCOPE} AND (:job IS NULL OR a.job_id = :job) AND a.status = 'active'
          AND e.entered_at <= :as_of AND (e.exited_at IS NULL OR e.exited_at > :as_of)
          AND e.stage NOT IN ('Offer', 'Hired')""", params)
    items = []
    for r in found:
        due = format_ts(parse_ts(r["entered_at"]) + timedelta(days=7))
        if due < params["as_of"]:
            items.append(derived("RULE-STAGE-7D", r, due, [r["event_id"], r["application_id"]],
                                 f"Move {r['full_name']} forward from {r['stage']} or close the application"))
    return items


def unanswered_offers(params: dict[str, Any]) -> list[dict[str, Any]]:
    """RULE-OFFER-5D: open offers with no inbound email since the offer stage began, after 5 days."""
    found = db.rows(f"""
        SELECT e.event_id, e.application_id, e.entered_at, a.job_id, c.full_name,
               (SELECT m.email_id FROM emails m
                WHERE m.application_id = e.application_id AND m.direction = 'outbound'
                  AND m.sent_at >= e.entered_at AND m.sent_at <= :as_of
                ORDER BY m.sent_at LIMIT 1) AS offer_email_id
        FROM stage_events e
        JOIN applications a ON a.application_id = e.application_id
        JOIN candidates c ON c.candidate_id = a.candidate_id
        WHERE a.job_id {IN_SCOPE} AND (:job IS NULL OR a.job_id = :job) AND a.status = 'active'
          AND e.stage = 'Offer' AND e.entered_at <= :as_of
          AND (e.exited_at IS NULL OR e.exited_at > :as_of)
          AND NOT EXISTS (SELECT 1 FROM emails r
                          WHERE r.application_id = e.application_id AND r.direction = 'inbound'
                            AND r.sent_at > e.entered_at AND r.sent_at <= :as_of)""", params)
    items = []
    for r in found:
        due = format_ts(parse_ts(r["entered_at"]) + timedelta(days=5))
        if due < params["as_of"]:
            evidence = [i for i in (r["event_id"], r["offer_email_id"], r["application_id"]) if i]
            items.append(derived("RULE-OFFER-5D", r, due, evidence,
                                 f"Follow up with {r['full_name']} on the offer"))
    return items


def derived(rule_id: str, row: dict[str, Any], due_at: str, evidence: list[str], title: str) -> dict[str, Any]:
    """A derived task item before its owner and lateness are filled in."""
    return {"rule_id": rule_id, "title": title, "job_id": row["job_id"],
            "application_id": row["application_id"], "due_at": due_at, "evidence": evidence}


def task_board(principal: Principal, owner_user_id: str | None = None, job_id: str | None = None,
               as_of: str | None = None) -> dict[str, Any]:
    """The tasks page: pending and overdue tasks grouped for the role.

    hr_user sees only tasks they own, in one group. hr_manager sees their teams' tasks grouped
    by owner. admin sees every task grouped by team. Each task says whether it is explicit (a
    row in the tasks table) or derived from a rule, with the rule's text, and each group has
    its own counts so the page does not count.
    """
    if principal.role == "hr_user":
        owner_user_id = principal.user_id
    result = pending_tasks(principal, owner_user_id=owner_user_id, job_id=job_id, as_of=as_of)
    teams = {r["job_id"]: (r["team_id"], r["team"]) for r in db.rows(
        f"""SELECT j.job_id, t.team_id, t.name AS team FROM jobs j JOIN teams t ON t.team_id = j.team_id
            WHERE j.job_id {IN_SCOPE}""", scope_params(principal))}
    for task in result["tasks"]:
        task["team_id"], task["team"] = teams[task["job_id"]]
        rule = task.get("rule_id") or task.get("matched_rule_id")
        task["kind"] = "derived" if task.get("rule_id") else "explicit"
        task["rule_text"] = RULES.get(rule) if rule else None
    group_by = {"admin": "team", "hr_manager": "owner"}.get(principal.role)
    groups: dict[str, dict[str, Any]] = {}
    for task in result["tasks"]:
        if group_by == "team":
            key, label = task["team_id"], task["team"]
        elif group_by == "owner":
            key, label = task["owner_user_id"] or "unassigned", task["owner_name"] or "Unassigned"
        else:
            key, label = "mine", "My tasks"
        group = groups.setdefault(key, {"key": key, "label": label, "count": 0, "overdue_count": 0, "tasks": []})
        group["tasks"].append(task)
        group["count"] += 1
        group["overdue_count"] += task["status"] == "overdue"
    return {**result, "group_by": group_by or "none",
            "groups": sorted(groups.values(), key=lambda g: g["label"])}
