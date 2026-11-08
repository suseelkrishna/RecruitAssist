"""Check an answer against the tool outputs of the same turn before the recruiter sees it.

Four checks, each deterministic:
  numbers    every number and date in the answer appears in the tool outputs (or the
             question). Rounding is allowed, a fraction may be stated as a percent, and a
             sentence that declares a sum or a percentage may combine grounded numbers.
  citations  every record ID in the answer was returned by a tool.
  ranking    any ranked list follows the score_candidates order.
  pii        no unmasked email address or phone number appears.
"""

from __future__ import annotations

import re
from itertools import permutations
from typing import Any

from app.logic.evidence import EMAIL_RE, PHONE_RE

ID_RE = re.compile(r"\b(?:(?:JOB|APP|SC|EM|TASK|CAN|INT|EV|USR|TEAM|SYNC|CHG)-\d+"
                   r"|RULE-[A-Z0-9]+(?:-[A-Z0-9]+)*|NB-[A-Z]+-\d+)\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?Z?)?\b")
NUMBER_RE = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")
LIST_MARKER_RE = re.compile(r"(?m)^\s*\d+[.)]\s")
LIST_LINE_RE = re.compile(r"^\s*(?:\||[-*+]\s|\d+[.)]\s)")
SUM_WORDS = re.compile(r"\+|\b(?:sum|summed|add|adding|added|total|totals|combined|together|altogether|in all)\b", re.I)
PERCENT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?%")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def verify(answer: str, tool_results: list[dict[str, Any]], context: Any = None,
           question: str = "") -> dict[str, Any]:
    """Run every check and return a report: passed, per-check details, and failure lines."""
    # Grounding: every tool output, the inputs of calls that succeeded (an accepted job_id is in
    # scope), the scope card, and the question.
    sources = ([r.get("output") for r in tool_results]
               + [r.get("input") for r in tool_results if not r.get("is_error")] + [context, question])
    pool_numbers, pool_dates, pool_ids = set(), set(), set()
    for source in sources:
        collect(source, pool_numbers, pool_dates, pool_ids)
    checks = {
        "numbers": check_numbers(answer, pool_numbers, pool_dates),
        "citations": check_citations(answer, pool_ids),
        "ranking": check_ranking(answer, tool_results),
        "pii": check_pii(answer),
    }
    failures = []
    if checks["numbers"]["unsupported"]:
        failures.append("These numbers or dates do not appear in the tool results: "
                        + ", ".join(checks["numbers"]["unsupported"]) + ".")
    if checks["citations"]["unknown"]:
        failures.append("These IDs were not returned by any tool: " + ", ".join(checks["citations"]["unknown"]) + ".")
    failures += checks["ranking"]["problems"]
    if checks["pii"]["found"]:
        failures.append(f"The answer shows {checks['pii']['found']} unmasked email address or phone number. "
                        "Remove contact details.")
    return {"passed": not failures, "checks": checks, "failures": failures}


def collect(value: Any, numbers: set[float], dates: set[str], ids: set[str]) -> None:
    """Gather every number, date, and record ID found anywhere inside a tool output."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        numbers.add(float(value))
        if 0 < abs(value) <= 1:
            numbers.add(round(float(value) * 100, 4))
    elif isinstance(value, str):
        n, d, i = scan(value)
        numbers.update(n)
        dates.update(d)
        ids.update(i)
    elif isinstance(value, dict):
        for item in value.values():
            collect(item, numbers, dates, ids)
    elif isinstance(value, (list, tuple)):
        numbers.add(float(len(value)))
        for item in value:
            collect(item, numbers, dates, ids)


def scan(text: str) -> tuple[list[float], list[str], list[str]]:
    """The numbers, dates (YYYY-MM-DD), and record IDs in a piece of text. IDs and dates are
    taken out first, so the digits inside APP-014 or 2026-11-09 are not read as numbers."""
    ids = ID_RE.findall(text)
    dates = [d[:10] for d in DATE_RE.findall(text)]
    rest = DATE_RE.sub(" ", ID_RE.sub(" ", text))
    numbers = [float(m.replace(",", "")) for m in NUMBER_RE.findall(rest)]
    return numbers, dates, ids


def matches(value: float, pool: set[float]) -> bool:
    """True when value equals a pool number once that number is rounded to value's precision."""
    text = f"{value}"
    places = len(text.split(".")[1].rstrip("0")) if "." in text else 0
    target = abs(value)
    return any(round(abs(x), places) == target for x in pool)


def check_numbers(answer: str, pool: set[float], dates: set[str]) -> dict[str, Any]:
    """Every number and date in the answer must be grounded in the pool, or be a declared sum or
    simple percentage of grounded numbers in the same sentence."""
    unsupported: list[str] = []
    checked = 0
    for sentence in SENTENCE_RE.split(LIST_MARKER_RE.sub(" ", answer)):
        numbers, found_dates, _ = scan(sentence)
        unsupported += [d for d in found_dates if d not in dates]
        grounded = [n for n in numbers if matches(n, pool)]
        percents = {float(p) for p in PERCENT_RE.findall(ID_RE.sub(" ", DATE_RE.sub(" ", sentence)))}
        for n in numbers:
            checked += 1
            if n in grounded:
                continue
            others = [g for g in grounded if g != n]
            if SUM_WORDS.search(sentence) and others and matches(n, {sum(others)}):
                continue
            if n in percents and any(b and matches(n, {100 * a / b}) for a, b in permutations(others, 2)):
                continue
            unsupported.append(f"{n:g}")
    return {"passed": not unsupported, "checked": checked, "unsupported": sorted(set(unsupported))}


def check_citations(answer: str, pool_ids: set[str]) -> dict[str, Any]:
    """Every record ID mentioned in the answer must have been returned by a tool."""
    cited = sorted(set(ID_RE.findall(answer)))
    unknown = [i for i in cited if i not in pool_ids]
    return {"passed": not unknown, "cited": cited, "unknown": unknown}


def check_ranking(answer: str, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Rows of any list or table that name ranked candidates must keep the score_candidates order.

    A candidate counts as named on a row by application ID or full name. Leaving candidates
    out is allowed (for example, ranking only one stage); swapping them is not.
    """
    problems = []
    lists = [r["output"]["ranked"] for r in tool_results
             if r.get("name") == "score_candidates" and not r.get("is_error")
             and isinstance(r.get("output"), dict) and "ranked" in r["output"]]
    rows = [line for line in answer.splitlines() if LIST_LINE_RE.match(line)]
    for ranked in lists:
        expected = [c["application_id"] for c in ranked]
        found: list[str] = []
        for row in rows:
            hits = []
            for c in ranked:
                spots = [p for p in (row.find(c["application_id"]), row.find(c["full_name"])) if p >= 0]
                if spots:
                    hits.append((min(spots), c["application_id"]))
            if hits and (first := min(hits)[1]) not in found:
                found.append(first)
        order = [i for i in expected if i in found]
        if found != order:
            problems.append(f"The ranked list is out of order: it shows {', '.join(found)} but "
                            f"score_candidates ranks them {', '.join(order)}.")
    return {"passed": not problems, "lists_checked": len(lists), "problems": problems}


def check_pii(answer: str) -> dict[str, Any]:
    """No email address or phone number may appear unmasked. The report gives a count only,
    so the contact details are not copied into logs."""
    found = len(EMAIL_RE.findall(answer)) + len(PHONE_RE.findall(answer))
    return {"passed": found == 0, "found": found}
