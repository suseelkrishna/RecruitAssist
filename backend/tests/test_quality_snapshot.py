"""The quality snapshot: the JUnit parser, the planted bug list, and the README's mutation sentence."""

from __future__ import annotations

import json
import re
from pathlib import Path

from evals import quality_snapshot

BACKEND = Path(__file__).resolve().parent.parent
README = BACKEND.parent / "README.md"

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="2" skipped="3" tests="20" time="4.567">
<testcase classname="tests.test_a" name="test_one" time="0.01"/>
</testsuite></testsuites>"""


def test_parse_junit_counts_errors_as_failures():
    assert quality_snapshot.parse_junit(JUNIT) == {"passed": 14, "failed": 3, "skipped": 3, "total": 20,
                                                   "duration_s": 4.57}


def test_parse_junit_reads_a_bare_testsuite():
    bare = '<testsuite tests="2" failures="0" errors="0" skipped="0" time="1"></testsuite>'
    assert quality_snapshot.parse_junit(bare)["passed"] == 2


def test_there_are_12_planted_bugs_across_the_four_areas():
    ids = [m[0] for m in quality_snapshot.MUTANTS]
    assert len(ids) == 12 and len(set(ids)) == 12
    assert {i.split("-")[0] for i in ids} == {"scoring", "task", "access", "verify"}
    assert {i for i in ids if i.startswith("verify-")} == {"verify-numbers", "verify-citations",
                                                            "verify-ranking", "verify-pii"}


def test_every_planted_bug_still_matches_the_code_exactly_once():
    for mutant_id, file, old, new, _ in quality_snapshot.MUTANTS:
        assert old != new, mutant_id
        assert (BACKEND / file).read_text().count(old) == 1, f"{mutant_id}: {old!r} in {file}"


def test_readme_mutation_numbers_match_quality_json():
    mutation = json.loads((BACKEND / "evals" / "quality.json").read_text())["mutation"]
    sentences = re.findall(r"(\d+) of (\d+) (?:planted bugs|in the latest run)", README.read_text())
    assert sentences, "README has no 'N of M planted bugs' sentence"
    assert all((int(n), int(m)) == (mutation["caught"], mutation["total"]) for n, m in sentences)
