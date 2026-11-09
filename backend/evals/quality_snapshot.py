"""Measure the backend's tests and write evals/quality.json for the quality page.

The quality page reads this file instead of running tests per request. The file records
what was measured: the test counts, the RBAC matrix result, and a mutation check, with
the git commit and whether the working tree had changes at the time.

The mutation check plants one known bug at a time in a copy of backend/ (never in the
working tree), runs the tests there, and counts the bug as caught when the tests fail.

Usage (from backend/):
    uv run python evals/quality_snapshot.py                   tests, RBAC, and the mutation check
    uv run python evals/quality_snapshot.py --skip-mutation   tests and RBAC only; keeps the
                                                              previous mutation block as it was
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
OUTPUT = BACKEND / "evals" / "quality.json"
RBAC_TESTS = "tests/test_rbac.py"
COPY_IGNORE = shutil.ignore_patterns(".venv", "evals_out", "__pycache__", ".pytest_cache", ".env*", ".vercel")

# Each planted bug: (id, file, old text, new text, what it breaks). The old text must occur
# exactly once in the file, which tests/test_quality_snapshot.py checks against the current code.
MUTANTS: list[tuple[str, str, str, str, str]] = [
    ("scoring-weights", "app/logic/scoring.py",
     'WEIGHTS = {"scorecards": 0.5, "must_have": 0.3, "stage": 0.2}',
     'WEIGHTS = {"scorecards": 0.3, "must_have": 0.5, "stage": 0.2}',
     "Scorecards and must-have match swap weights in the ranking score."),
    ("scoring-order", "app/logic/scoring.py",
     'scored.sort(key=lambda s: (-s["score"], s["application_id"]))',
     'scored.sort(key=lambda s: (s["score"], s["application_id"]))',
     "Candidates are ranked worst first."),
    ("scoring-scale", "app/logic/scoring.py",
     "scorecard_value = (avg_points - 1) / 3 if cards else 0.0",
     "scorecard_value = avg_points / 4 if cards else 0.0",
     "Scorecard points are scaled from 0.25 instead of 0, so strong_no scores above zero."),
    ("task-scorecard-48h", "app/logic/tasks.py",
     "timedelta(hours=48)",
     "timedelta(hours=24)",
     "A missing scorecard becomes a task after 24 hours instead of 48."),
    ("task-reply-2bd", "app/logic/tasks.py",
     'add_business_days(r["sent_at"], 2)',
     'add_business_days(r["sent_at"], 3)',
     "An unanswered email becomes a task after 3 business days instead of 2."),
    ("task-stage-7d", "app/logic/tasks.py",
     "timedelta(days=7)",
     "timedelta(days=14)",
     "An application counts as stuck after 14 days in a stage instead of 7."),
    ("access-manager-teams", "app/access.py",
     'allowed = {j["job_id"] for j in jobs if j["team_id"] in teams}',
     'allowed = {j["job_id"] for j in jobs}',
     "An HR Manager's allowed_job_ids include jobs on every team."),
    ("access-sql-filter", "app/logic/common.py",
     'IN_SCOPE = "IN (SELECT value FROM json_each(:allowed))"',
     'IN_SCOPE = "IS NOT NULL AND :allowed IS NOT NULL"',
     "SQL queries stop filtering by allowed_job_ids."),
    ("verify-numbers", "app/agent/verify.py",
     'return {"passed": not unsupported, "checked": checked',
     'return {"passed": True, "checked": checked',
     "The verifier passes answers with numbers no tool returned."),
    ("verify-citations", "app/agent/verify.py",
     "unknown = [i for i in cited if i not in pool_ids]",
     "unknown = []",
     "The verifier passes answers that cite record IDs no tool returned."),
    ("verify-ranking", "app/agent/verify.py",
     "if found != order:",
     "if False:",
     "The verifier passes ranked lists in a different order from score_candidates."),
    ("verify-pii", "app/agent/verify.py",
     'return {"passed": found == 0, "found": found}',
     'return {"passed": found >= 0, "found": found}',
     "The verifier passes answers that show an email address or phone number."),
]


def now() -> str:
    """The current UTC time as an ISO 8601 string with a Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(*args: str) -> str:
    """The output of one git command run in backend/, or '' when git is not available."""
    try:
        return subprocess.run(["git", *args], cwd=BACKEND, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def parse_junit(xml_text: str) -> dict[str, Any]:
    """Passed, failed, skipped, total, and duration_s from a pytest JUnit XML report.
    Errors count as failures, because either one means the run did not pass."""
    root = ET.fromstring(xml_text)
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    duration = sum(float(s.get("time", 0)) for s in suites)
    return {"passed": total - failed - skipped, "failed": failed, "skipped": skipped,
            "total": total, "duration_s": round(duration, 2)}


def run_tests(*paths: str) -> dict[str, Any]:
    """Run pytest on the given paths in backend/ and return the counts from its JUnit report.
    The report goes to a temporary folder outside the repo."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "junit.xml"
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        f"--junitxml={report}", *paths], cwd=BACKEND, capture_output=True, text=True)
        return parse_junit(report.read_text())


def rbac_summary() -> dict[str, Any]:
    """The RBAC matrix result: passed and total test cases, pass or fail, and a short description."""
    counts = run_tests(RBAC_TESTS)
    users = len(re.findall(r'"USR-\d+"', re.search(r"USERS = \[(.*?)\]", (BACKEND / RBAC_TESTS).read_text()).group(1)))
    return {"passed": counts["passed"], "total": counts["total"],
            "result": "pass" if counts["failed"] == 0 and counts["total"] > 0 else "fail",
            "description": f"Every logic function run as each of the {users} demo users, against scope from separate SQL."}


def run_mutant(mutant: tuple[str, str, str, str, str]) -> dict[str, Any]:
    """Plant one bug in a temporary copy of backend/, run the tests there, and report whether they failed."""
    mutant_id, file, old, new, breaks = mutant
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "backend"
        shutil.copytree(BACKEND, copy, ignore=COPY_IGNORE)
        target = copy / file
        source = target.read_text()
        assert source.count(old) == 1, f"{mutant_id}: expected the old text once in {file}"
        target.write_text(source.replace(old, new))
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
                                cwd=copy, capture_output=True, text=True)
    return {"id": mutant_id, "file": file, "what_it_breaks": breaks, "caught": result.returncode != 0,
            "duration_s": round(time.monotonic() - started, 1)}


def mutation_check() -> dict[str, Any]:
    """Run every planted bug and return how many the tests caught, with one row per bug."""
    ran_at, started = now(), time.monotonic()
    rows = []
    for mutant in MUTANTS:
        row = run_mutant(mutant)
        print(f"  {row['id']}: {'caught' if row['caught'] else 'SURVIVED'} ({row['duration_s']}s)", flush=True)
        rows.append(row)
    caught = sum(r["caught"] for r in rows)
    return {"caught": caught, "total": len(rows), "score": round(caught / len(rows), 4), "ran_at": ran_at,
            "git_commit": git("rev-parse", "--short", "HEAD"), "duration_s": round(time.monotonic() - started, 1),
            "mutants": rows}


def previous_mutation() -> dict[str, Any] | None:
    """The mutation block from the existing quality.json, or None when there is none."""
    return json.loads(OUTPUT.read_text()).get("mutation") if OUTPUT.exists() else None


def main() -> None:
    """Measure, then write evals/quality.json."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-mutation", action="store_true", help="keep the previous mutation block")
    args = parser.parse_args()
    snapshot = {"generated_at": now(), "git_commit": git("rev-parse", "--short", "HEAD"),
                "git_dirty": bool(git("status", "--porcelain"))}
    print("Running the backend tests", flush=True)
    snapshot["tests"] = run_tests("tests")
    print("Running the RBAC matrix", flush=True)
    snapshot["rbac"] = rbac_summary()
    if args.skip_mutation:
        snapshot["mutation"] = previous_mutation()
    else:
        print(f"Running {len(MUTANTS)} planted bugs", flush=True)
        snapshot["mutation"] = mutation_check()
    OUTPUT.write_text(json.dumps(snapshot, indent=2) + "\n")
    mutation = snapshot["mutation"]
    caught = f"{mutation['caught']} of {mutation['total']} caught" if mutation else "not run"
    print(f"Tests {snapshot['tests']['passed']} of {snapshot['tests']['total']} passed, RBAC {snapshot['rbac']['result']}, "
          f"mutation {caught}. Wrote {OUTPUT.relative_to(BACKEND)}.")


if __name__ == "__main__":
    main()
