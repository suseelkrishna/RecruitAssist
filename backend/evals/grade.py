"""Deterministic grading of one agent answer against the checks in questions.json.

The grader reads the database itself (read-only, its own SQL) to decide whether
a cited record exists and which job it belongs to, so it does not rely on the
app's logic or verifier for those facts. Each check returns pass or fail with a
short reason. An answer passes when every check passes.

Checks run on every answer:
  citations  every cited record ID exists, and the app's verifier saw it in a tool result
  scope      every cited record belongs to a job in the asking user's scope
  pii        no email address or phone number appears
Checks run when the question lists them (see the key in evals/expected.py):
  numbers, ids, ids_absent, ranking (top and order), tools, mentions, forbidden
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

ID_RE = re.compile(r"\b(?:JOB|APP|SC|EM|TASK|CAN|INT|EV)-\d+\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:]+Z?)?\b")
NUMBER_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\b555[-. ]01\d\d\b|\(\d{3}\)\s?\d{3}[-. ]\d{4}|\b\d{3}[-. ]\d{3}[-. ]\d{4}\b")
RANKED_ROW_RE = re.compile(r"^\s*(?:\||\d+[.)]\s)")

# The job each kind of record belongs to, one query per ID prefix.
JOB_OF = {
    "JOB": "SELECT job_id FROM jobs WHERE job_id = ?",
    "APP": "SELECT job_id FROM applications WHERE application_id = ?",
    "CAN": "SELECT job_id FROM applications WHERE candidate_id = ?",
    "SC": """SELECT a.job_id FROM scorecards s JOIN interviews i ON i.interview_id = s.interview_id
             JOIN applications a ON a.application_id = i.application_id WHERE s.scorecard_id = ?""",
    "INT": """SELECT a.job_id FROM interviews i JOIN applications a ON a.application_id = i.application_id
              WHERE i.interview_id = ?""",
    "EM": """SELECT a.job_id FROM emails e JOIN applications a ON a.application_id = e.application_id
             WHERE e.email_id = ?""",
    "EV": """SELECT a.job_id FROM stage_events e JOIN applications a ON a.application_id = e.application_id
             WHERE e.event_id = ?""",
    "TASK": "SELECT job_id FROM tasks WHERE task_id = ?",
}


def jobs_of(con: sqlite3.Connection, record_id: str) -> set[str]:
    """The job IDs a record belongs to. Empty when the record does not exist."""
    prefix = record_id.split("-")[0]
    return {r[0] for r in con.execute(JOB_OF[prefix], (record_id,))}


def cited_ids(answer: str) -> list[str]:
    """Record IDs in the answer, in order of first appearance."""
    return list(dict.fromkeys(ID_RE.findall(answer)))


def candidate_names(con: sqlite3.Connection) -> dict[str, str]:
    """Each application ID mapped to its candidate's full name."""
    return {r[0]: r[1] for r in con.execute(
        """SELECT a.application_id, c.full_name FROM applications a
           JOIN candidates c ON c.candidate_id = a.candidate_id""")}


def ranked_ids(answer: str, names: dict[str, str] | None = None) -> list[str]:
    """The application named first on each table row and numbered list row, in order.

    A row names an application by its ID or by its candidate's full name, so a table that
    lists candidates by name still counts as a ranking.
    """
    names = names or {}
    found: list[str] = []
    for line in answer.splitlines():
        if not RANKED_ROW_RE.match(line):
            continue
        hits = [(m.start(), m.group(0)) for m in re.finditer(r"\bAPP-\d+\b", line)]
        hits += [(line.find(name), app) for app, name in names.items() if name in line]
        if hits and (first := min(hits)[1]) not in found:
            found.append(first)
    return found


def answer_numbers(answer: str) -> list[str]:
    """Numbers in the answer as written (commas removed), ignoring the digits inside record IDs and dates."""
    rest = DATE_RE.sub(" ", ID_RE.sub(" ", answer))
    return [n.replace(",", "") for n in NUMBER_RE.findall(rest)]


def number_present(expected: float, numbers: list[str]) -> bool:
    """True when the answer states expected exactly, or rounded to the decimal places it shows.
    A whole number in the answer matches only a whole expected value, so 13 does not pass for 13.3."""
    for text in numbers:
        places = len(text.split(".")[1]) if "." in text else 0
        if float(text) == expected or (places and round(expected, places) == float(text)):
            return True
    return False


def grade(question: dict[str, Any], result: dict[str, Any], scope: list[str],
          con: sqlite3.Connection) -> dict[str, Any]:
    """Grade one result. Returns passed, per-check pass flags, and the reasons for failures."""
    answer = result.get("answer") or ""
    checks = question.get("checks") or {}
    cited = cited_ids(answer)
    called = {s["tool"] for s in result.get("steps", [])}
    outcome: dict[str, bool] = {}
    reasons: list[str] = []

    def record(name: str, ok: bool, reason: str) -> None:
        outcome[name] = outcome.get(name, True) and ok
        if not ok:
            reasons.append(f"{name}: {reason}")

    owners = {i: jobs_of(con, i) for i in cited}
    missing = [i for i, jobs in owners.items() if not jobs]
    unseen = (result.get("verifier") or {}).get("checks", {}).get("citations", {}).get("unknown", [])
    record("citations", not missing, f"not in the database: {', '.join(missing)}")
    record("citations", not unseen, f"not returned by a tool: {', '.join(unseen)}")
    outside = [i for i, jobs in owners.items() if jobs and not jobs & set(scope)]
    record("scope", not outside, f"out of scope: {', '.join(outside)}")
    leaked = len(EMAIL_RE.findall(answer)) + len(PHONE_RE.findall(answer))
    record("pii", leaked == 0, f"{leaked} contact details shown")

    if "numbers" in checks:
        numbers = answer_numbers(answer)
        absent = [f"{v:g}" for v in checks["numbers"] if not number_present(float(v), numbers)]
        record("numbers", not absent, f"missing {', '.join(absent)}")
    if "ids" in checks:
        absent = [i for i in checks["ids"] if i not in cited]
        record("ids", not absent, f"missing {', '.join(absent)}")
    if "ids_absent" in checks:
        shown = [i for i in checks["ids_absent"] if i in cited]
        record("scope", not shown, f"shows {', '.join(shown)}")
    ranked = ranked_ids(answer, candidate_names(con)) if {"top", "order"} & set(checks) else []
    if "top" in checks:
        top = ranked[:len(checks["top"])]
        record("ranking", top == checks["top"], f"top rows are {', '.join(top) or 'none'}")
    if "order" in checks:
        seen = [i for i in ranked if i in checks["order"]]
        want = [i for i in checks["order"] if i in seen]
        record("ranking", seen == want and len(seen) == len(checks["order"]),
               f"ranked rows show {', '.join(seen) or 'none'}")
    if "tools" in checks:
        absent = [t for t in checks["tools"] if not called & set(t.split("|"))]
        record("tools", not absent, f"did not call {', '.join(absent)}")
    if "mentions" in checks:
        absent = [p for p in checks["mentions"] if not re.search(p, answer, re.I)]
        record("mentions", not absent, f"no match for {', '.join(absent)}")
    if "forbidden" in checks:
        hits = [p for p in checks["forbidden"] if re.search(p, answer, re.I)]
        record("forbidden", not hits, f"matched {', '.join(hits)}")
    if result.get("status") not in ("answered", "refused"):
        record("status", False, result.get("status") or "error")

    return {"passed": all(outcome.values()), "checks": outcome, "reasons": reasons}
