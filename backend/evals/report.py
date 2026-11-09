"""Summarize graded eval runs per model and effort, pick a default, and write the report files.

scoreboard.json is the machine-readable summary the quality page reads.
results.md is the same summary for people, with per-question results and the
rule used to pick the default model.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

CHECKS = ["numbers", "ids", "tools", "citations", "ranking", "scope", "pii", "mentions", "forbidden"]
# A setting within this many points of the best verified pass rate counts as tied; the cheapest tied one wins.
PASS_RATE_TIE_POINTS = 5.0


def percentile(values: list[float], pct: float) -> float | None:
    """The pct-th percentile by the nearest-rank method, or None for no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered) + 0.5 - 1e-9))
    return ordered[min(rank, len(ordered)) - 1]


def mean(values: list[float]) -> float | None:
    """The mean, or None for no values."""
    return statistics.fmean(values) if values else None


def rounded(value: float | None, places: int) -> float | None:
    """value rounded, keeping None."""
    return None if value is None else round(value, places)


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """The scoreboard row for the runs of one model and effort."""
    by_question: dict[str, list[bool]] = defaultdict(list)
    for r in runs:
        by_question[r["question_id"]].append(r["grade"]["passed"])
    usage = [r["result"].get("usage") or {} for r in runs]
    calls = sum(u.get("api_calls", 0) for u in usage)
    prompt_tokens = sum(u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                        + u.get("cache_read_input_tokens", 0) for u in usage)
    judged = [r["judge"]["scores"] for r in runs if (r.get("judge") or {}).get("scores")]
    costs = [r["result"].get("estimated_cost_usd") or 0.0 for r in runs]
    return {
        "runs": len(runs),
        "questions": len(by_question),
        "repeats": max((len(v) for v in by_question.values()), default=0),
        "passed": sum(r["grade"]["passed"] for r in runs),
        "pass_rate_pct": rounded(100 * mean([r["grade"]["passed"] for r in runs]), 1),
        "verified_pass_rate_pct": rounded(100 * mean([r["grade"]["passed"] and bool(r["result"].get("verified"))
                                                      for r in runs]), 1),
        "check_pass_rate_pct": {
            c: rounded(100 * mean([r["grade"]["checks"][c] for r in runs if c in r["grade"]["checks"]]), 1)
            for c in CHECKS if any(c in r["grade"]["checks"] for r in runs)},
        "citation_validity_pct": rounded(100 * mean([r["grade"]["checks"]["citations"] for r in runs]), 1),
        "verifier_failures": sum(not r["result"].get("verified") for r in runs),
        "verifier_retries": sum(bool(r["result"].get("retried")) for r in runs),
        "errors": sum(r["result"].get("status") == "error" for r in runs),
        "consistency_pct": rounded(100 * mean([len(set(v)) == 1 for v in by_question.values()]), 1),
        "latency_p50_s": rounded(percentile([r["result"].get("latency_ms", 0) / 1000 for r in runs], 50), 1),
        "latency_p95_s": rounded(percentile([r["result"].get("latency_ms", 0) / 1000 for r in runs], 95), 1),
        "tokens_per_question": {k: round(mean([u.get(k, 0) for u in usage]) or 0)
                                for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                          "cache_read_input_tokens")},
        "api_calls_per_question": rounded(calls / len(runs), 1) if runs else None,
        "cache_hit_rate_pct": rounded(100 * sum(u.get("cache_hits", 0) for u in usage) / calls, 1) if calls else None,
        "cache_read_share_pct": rounded(100 * sum(u.get("cache_read_input_tokens", 0) for u in usage)
                                        / prompt_tokens, 1) if prompt_tokens else None,
        "cost_per_question_usd": rounded(mean(costs), 4),
        "total_cost_usd": round(sum(costs), 4),
        "llm_judge": {"judged": len(judged),
                      "faithfulness": rounded(mean([s["faithfulness"] for s in judged]), 2),
                      "clarity": rounded(mean([s["clarity"] for s in judged]), 2)} if judged else None,
        "per_question": {q: {"passed": sum(v), "runs": len(v)} for q, v in sorted(by_question.items())},
    }


def choose_default(settings: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The cheapest setting whose verified pass rate is within PASS_RATE_TIE_POINTS of the best one.

    The verified pass rate counts a run only when it passes every check and the app's verifier
    also labeled it verified, because an unverified label is what the recruiter sees.
    """
    if not settings:
        return None
    best = max(s["verified_pass_rate_pct"] for s in settings)
    tied = [s for s in settings if s["verified_pass_rate_pct"] >= best - PASS_RATE_TIE_POINTS]
    return min(tied, key=lambda s: (s["cost_per_question_usd"], -s["verified_pass_rate_pct"]))


def scoreboard(runs: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    """The full scoreboard: one row per model and effort, the chosen default, and run metadata."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        groups[(r["model"], r["effort"])].append(r)
    settings = [{"model": m, "effort": e, **summarize(rs)} for (m, e), rs in sorted(groups.items())]
    chosen = choose_default(settings)
    return {
        **meta,
        "grading": "Pass or fail comes from deterministic checks (evals/grade.py). "
                   "llm_judge scores, where present, come from an LLM judge (evals/judge_rubric.md).",
        "default_rule": f"Highest verified pass rate (passes every check and the app's verifier labeled "
                        f"it verified); settings within {PASS_RATE_TIE_POINTS:g} points of it count as tied, "
                        "and the cheapest tied setting wins.",
        "default": {"model": chosen["model"], "effort": chosen["effort"]} if chosen else None,
        "settings": settings,
        "total_cost_usd": round(sum(s["total_cost_usd"] for s in settings), 4),
    }


def fmt(value: Any, suffix: str = "") -> str:
    """A table cell: the value with a suffix, or n/a."""
    return "n/a" if value is None else f"{value}{suffix}"


def results_markdown(board: dict[str, Any], questions: list[dict[str, Any]],
                     failures: list[dict[str, Any]]) -> str:
    """results.md: the summary tables, the default, per-question results, and sample failures."""
    settings = board["settings"]
    names = [f"{s['model'].removeprefix('claude-')} {s['effort']}" for s in settings]
    lines = [
        "# Eval results",
        "",
        f"Generated by `evals/run.py` on {board['generated_at']} against data as of {board['as_of']} "
        f"(data hash `{board['data_hash'][:12]}`).",
        f"{board['questions']} questions, {board['repeats']} repeats each, {len(settings)} model and effort "
        f"settings, {sum(s['runs'] for s in settings)} runs. Estimated cost at list prices: "
        f"${board['total_cost_usd']:.2f}.",
        "",
        board["grading"],
        "",
        "## Default",
        "",
    ]
    if board["default"]:
        lines.append(f"**{board['default']['model']}** at effort **{board['default']['effort']}**. "
                     f"Rule: {board['default_rule']}")
    lines += [
        "",
        "## Summary",
        "",
        "| Setting | Pass rate | Verified pass rate | Citation validity | Verifier failures | Consistency "
        "| p50 latency | p95 latency | Tokens in / out | Cache hit rate | Cost per question |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in zip(names, settings):
        t = s["tokens_per_question"]
        tokens_in = t["input_tokens"] + t["cache_creation_input_tokens"] + t["cache_read_input_tokens"]
        lines.append(
            f"| {name} | {fmt(s['pass_rate_pct'], '%')} ({s['passed']}/{s['runs']}) "
            f"| {fmt(s['verified_pass_rate_pct'], '%')} | {fmt(s['citation_validity_pct'], '%')} | {s['verifier_failures']} of {s['runs']} "
            f"| {fmt(s['consistency_pct'], '%')} | {fmt(s['latency_p50_s'], ' s')} "
            f"| {fmt(s['latency_p95_s'], ' s')} | {tokens_in:,} / {t['output_tokens']:,} "
            f"| {fmt(s['cache_hit_rate_pct'], '%')} | ${s['cost_per_question_usd']:.4f} |")
    lines += [
        "",
        "Pass rate: every deterministic check passed. Verified pass rate: passed and the app's verifier "
        "labeled the answer verified. Citation validity: every cited ID exists and came "
        "from a tool result. Verifier failures: answers the app's own verifier labeled unverified after "
        "its one retry. Consistency: questions where all repeats gave the same pass or fail result. "
        "Tokens are per question; tokens in include cache writes and cache reads. Cache hit rate: API "
        "calls that read from the prompt cache.",
        "",
        "## Checks",
        "",
        "| Setting | " + " | ".join(CHECKS) + " |",
        "|---|" + "---|" * len(CHECKS),
    ]
    for name, s in zip(names, settings):
        lines.append(f"| {name} | " + " | ".join(fmt(s["check_pass_rate_pct"].get(c), "%") for c in CHECKS) + " |")
    if any(s["llm_judge"] for s in settings):
        lines += ["", "## LLM judge scores", "",
                  "These scores come from an LLM judge using `evals/judge_rubric.md`, not from the "
                  "deterministic checks. Scale 1 to 5.", "",
                  "| Setting | Judged answers | Faithfulness | Clarity |", "|---|---|---|---|"]
        for name, s in zip(names, settings):
            j = s["llm_judge"] or {}
            lines.append(f"| {name} | {j.get('judged', 0)} | {fmt(j.get('faithfulness'))} | {fmt(j.get('clarity'))} |")
    lines += ["", "## Per question", "", "Passed runs out of runs for each setting.", "",
              "| Question | User | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for q in questions:
        cells = [f"{s['per_question'].get(q['id'], {}).get('passed', 0)}/"
                 f"{s['per_question'].get(q['id'], {}).get('runs', 0)}" for s in settings]
        lines.append(f"| {q['id']} | {q['user']} | " + " | ".join(cells) + " |")
    if failures:
        lines += ["", "## Failure reasons", "",
                  "The most common reasons a run failed, per question, across all settings.", ""]
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for f in failures:
            for reason in f["reasons"]:
                counts[(f["question_id"], reason)] += 1
        for (qid, reason), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:25]:
            lines.append(f"- {qid}: {reason} ({n} runs)")
    return "\n".join(lines) + "\n"


def write_reports(board: dict[str, Any], questions: list[dict[str, Any]], runs: list[dict[str, Any]],
                  scoreboard_path: Path, results_path: Path) -> None:
    """Write scoreboard.json and results.md."""
    failures = [{"question_id": r["question_id"], "reasons": r["grade"]["reasons"]}
                for r in runs if not r["grade"]["passed"]]
    scoreboard_path.write_text(json.dumps(board, indent=1) + "\n")
    results_path.write_text(results_markdown(board, questions, failures))
