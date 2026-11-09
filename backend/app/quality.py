"""The numbers on the quality page, read from report files instead of being run per request.

evals/quality.json, written by evals/quality_snapshot.py, holds the latest test counts,
RBAC result, and mutation check, with the git commit they were measured at.
evals/scoreboard.json holds the eval scoreboard. A value whose file or field is not
there yet is null, named in missing, and given a plain reason in reasons. The number of
test functions is counted from the tests folder each time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
QUALITY = BACKEND / "evals" / "quality.json"
SCOREBOARD = BACKEND / "evals" / "scoreboard.json"
TESTS = BACKEND / "tests"

SNAPSHOT_REASON = "Run python evals/quality_snapshot.py from backend/ to produce this."
REASONS = {
    "tests": SNAPSHOT_REASON,
    "rbac": SNAPSHOT_REASON,
    "mutation": "Run python evals/quality_snapshot.py from backend/ without --skip-mutation to produce this.",
    "scoreboard": "Run python evals/run.py from backend/ to produce the eval scoreboard.",
}


def read_json(path: Path) -> dict[str, Any] | None:
    """The parsed file, or None when it does not exist."""
    return json.loads(path.read_text()) if path.exists() else None


def tests_defined() -> int:
    """How many test functions the tests folder defines."""
    return sum(len(re.findall(r"(?m)^(?:async )?def test_", f.read_text())) for f in TESTS.glob("test_*.py"))


def quality_report() -> dict[str, Any]:
    """Test counts, RBAC result, mutation check, and the eval scoreboard, with a reason for each missing part."""
    quality = read_json(QUALITY) or {}
    values = {"tests": quality.get("tests"), "rbac": quality.get("rbac"),
              "mutation": quality.get("mutation"), "scoreboard": read_json(SCOREBOARD)}
    missing = [name for name, value in values.items() if value is None]
    return {
        "tests_defined": tests_defined(),
        **values,
        "generated_at": quality.get("generated_at"),
        "git_commit": quality.get("git_commit"),
        "git_dirty": quality.get("git_dirty"),
        "missing": missing,
        "reasons": {name: REASONS[name] for name in missing},
    }
