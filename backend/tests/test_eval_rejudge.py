"""Which kept runs the eval judge scores: runs judged before, or only the never-judged ones.

The runs are hand-written dictionaries, so no model is called.
"""

from __future__ import annotations

from evals import run


def kept(repeat: int, judge: dict | None, answer: str = "An answer.") -> dict:
    """A kept run with the given repeat, judge entry, and answer."""
    row = {"repeat": repeat, "result": {"answer": answer}}
    if judge is not None:
        row["judge"] = judge
    return row


SCORED = {"scores": {"faithfulness": 4, "clarity": 4, "reason": ""}}
FAILED = {"scores": None, "error": "timeout"}


def test_rejudge_targets_only_runs_judged_before():
    """The default keeps the same judged set, so a rubric change rescores like for like."""
    runs = [kept(0, SCORED), kept(0, FAILED), kept(0, None), kept(1, None)]
    assert run.judge_targets(runs, missing_only=False, judge_repeats=1) == [runs[0], runs[1]]


def test_judge_missing_targets_unscored_runs_in_judged_repeats():
    """Missing-only picks first-repeat runs without scores, including a failed judge call."""
    runs = [kept(0, SCORED), kept(0, FAILED), kept(0, None), kept(1, None), kept(0, None, answer="")]
    assert run.judge_targets(runs, missing_only=True, judge_repeats=1) == [runs[1], runs[2]]


def test_judge_missing_respects_judge_repeats():
    """With two judged repeats, unscored second-repeat runs are included too."""
    runs = [kept(0, None), kept(1, None), kept(2, None)]
    assert run.judge_targets(runs, missing_only=True, judge_repeats=2) == [runs[0], runs[1]]
