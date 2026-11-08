"""The numbers on the quality page, read from report files instead of being run per request.

evals/quality.json holds the latest test counts, mutation score, and RBAC
result. evals/scoreboard.json holds the eval scoreboard. A value whose file is
not there yet is null and named in missing. The number of test functions is
counted from the tests folder each time.
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


def read_json(path: Path) -> dict[str, Any] | None:
    """The parsed file, or None when it does not exist."""
    return json.loads(path.read_text()) if path.exists() else None


def tests_defined() -> int:
    """How many test functions the tests folder defines."""
    return sum(len(re.findall(r"(?m)^(?:async )?def test_", f.read_text())) for f in TESTS.glob("test_*.py"))


def quality_report() -> dict[str, Any]:
    """Test counts, mutation score, RBAC result, and the eval scoreboard, with missing parts listed."""
    quality = read_json(QUALITY) or {}
    scoreboard = read_json(SCOREBOARD)
    missing = [f"{name} (no {path.relative_to(BACKEND)} yet)"
               for name, path, value in [("tests", QUALITY, quality.get("tests")),
                                         ("mutation_score", QUALITY, quality.get("mutation_score")),
                                         ("rbac", QUALITY, quality.get("rbac")),
                                         ("scoreboard", SCOREBOARD, scoreboard)]
               if value is None]
    return {
        "tests_defined": tests_defined(),
        "tests": quality.get("tests"),
        "mutation_score": quality.get("mutation_score"),
        "rbac": quality.get("rbac"),
        "scoreboard": scoreboard,
        "generated_at": quality.get("generated_at"),
        "missing": missing,
    }
