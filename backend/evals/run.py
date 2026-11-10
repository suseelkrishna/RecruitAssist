"""Run the eval questions through the agent loop for each model and effort, grade, and report.

Every question in questions.json is asked by its demo user through
app/agent/loop.run_agent, the same loop the API uses. Each answer is graded by
evals/grade.py, optionally scored by the LLM judge, and summarized into
evals/results.md and evals/scoreboard.json. Raw results, which hold full answers,
are written to evals_out/ (ignored by git).

Usage (from backend/):
    uv run python evals/run.py --estimate                  measure one question per setting, print the projected cost
    uv run python evals/run.py                              the full matrix (every eval: true model in
                                                            app/llm/models.json x 2 efforts x 3 repeats)
    uv run python evals/run.py --models claude-haiku-5-5 gpt-6-luna      compare models across providers
    uv run python evals/run.py --models claude-haiku-5-5 --repeats 1 --questions process-top3
    uv run python evals/run.py --judge claude-sonnet-5-5   add LLM judge scores for the first repeat
    uv run python evals/run.py --from-runs evals_out/<stamp>/runs.jsonl    regrade and report without API calls
    uv run python evals/run.py --resume evals_out/<stamp>/runs.jsonl       run only the runs that are missing or failed
                                                                            with an API error
    uv run python evals/run.py --resume evals_out/<stamp>/runs.jsonl --judge claude-sonnet-5-5 --judge-missing
                                                            judge kept runs that have no judge scores, without rerunning them
    uv run python evals/run.py --record --models claude-sonnet-5-5 --efforts medium
                                                            record the suggested questions into data/recordings.json
    uv run python evals/run.py --group multi_tool --models claude-haiku-5-5 --efforts low --repeats 1
                                                            the multi-tool questions; writes evals/multi_tool.json
                                                            and its section of results.md, not the scoreboard

Each question has a group. The default group, core, is the one the scoreboard and the
model choice are built from; other groups are reported separately.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


from app import access, llm, store  # noqa: E402
from app.agent import loop, recordings  # noqa: E402
from app.env import load_env_file  # noqa: E402
from evals import expected, grade, judge, report  # noqa: E402

QUESTIONS = BACKEND / "evals" / "questions.json"
SCOREBOARD = BACKEND / "evals" / "scoreboard.json"
RESULTS = BACKEND / "evals" / "results.md"
GROUP_SUMMARY = BACKEND / "evals" / "{group}.json"
DEFAULT_GROUP = "core"
OUT_DIR = BACKEND / "evals_out"
MODELS = llm.eval_models()
EFFORTS = ["low", "medium"]
REPEATS = 3
CONCURRENCY = 6
BUDGET_USD = 20.0
ESTIMATE_QUESTION = "controls-leak"

# The suggested questions on the Ask page for each role (frontend/app/ask/page.tsx).
CHIPS = {
    "hr_user": ["What should I do today?", "Top 3 candidates for my role", "Who is waiting on me?"],
    "hr_manager": ["Where is my team losing candidates?", "Which recruiter is overloaded?",
                   "Which roles are behind target?"],
    "admin": ["Company-wide pipeline health", "Which sources bring the best candidates?",
              "Any integration issues?"],
}
RECORD_ATTEMPTS = 3


def load_questions(only: list[str] | None = None, group: str = DEFAULT_GROUP) -> dict[str, Any]:
    """questions.json, limited to one group and, when any are named, to the given question IDs."""
    data = json.loads(QUESTIONS.read_text())
    groups = {q.get("group", DEFAULT_GROUP) for q in data["questions"]}
    if group not in groups:
        raise SystemExit(f"Unknown group {group!r}. Groups: {', '.join(sorted(groups))}")
    data["questions"] = [q for q in data["questions"] if q.get("group", DEFAULT_GROUP) == group]
    if only:
        unknown = set(only) - {q["id"] for q in data["questions"]}
        if unknown:
            raise SystemExit(f"Unknown question IDs: {', '.join(sorted(unknown))}")
        data["questions"] = [q for q in data["questions"] if q["id"] in only]
    return data


def root_error(error: BaseException) -> BaseException:
    """The first underlying error inside nested exception groups (the MCP client wraps errors in them)."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


async def ask(client: Any, question: dict[str, Any], model: str, effort: str) -> dict[str, Any]:
    """Run one question as its demo user. An API failure becomes a result with status error."""
    principal = access.principal_for(question["user"])
    started = time.monotonic()
    try:
        return await loop.run_agent(question["question"], principal, job_id=question.get("job_id"),
                                    history=question.get("history"), model=model, effort=effort,
                                    client=client)
    except Exception as group:  # Recorded and graded as a failed run so one error does not stop the matrix.
        error = root_error(group)
        return {"answer": "", "status": "error", "error": f"{type(error).__name__}: {error}",
                "fatal": isinstance(error, llm.LLMAPIError) and error.fatal,
                "verified": False, "steps": [], "usage": loop.empty_usage(), "estimated_cost_usd": 0.0,
                "latency_ms": round((time.monotonic() - started) * 1000), "model": model, "effort": effort,
                "provider": llm.provider_for(model)}


async def run_matrix(questions: list[dict[str, Any]], models: list[str], efforts: list[str], repeats: int,
                     concurrency: int, budget: float, judge_model: str | None, judge_repeats: int,
                     out_file: Path, done: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Run every question for every model, effort, and repeat, grading each run as it finishes.

    Every model gets the same questions, prompts, tools, effort, and output token limit; only
    the provider adapter differs. Runs go out at most `concurrency` at a time. Once the estimated spend reaches the
    budget, or an API error that retrying cannot fix occurs, no new run starts and the
    failing run is not kept. Runs already in `done` are kept and not repeated. Each graded
    run is appended to out_file as one JSON line.
    """
    clients = {m: loop.make_client(m, "eval") for m in models}
    judge_client = loop.make_client(judge_model, "eval") if judge_model else None
    gate = asyncio.Semaphore(concurrency)
    spent = {"usd": 0.0}
    stop: list[str] = []
    graded: list[dict[str, Any]] = list(done or [])
    finished = {(r["question_id"], r["model"], r["effort"], r["repeat"]) for r in graded}
    with closing(expected.connect()) as con:

        async def one(q: dict[str, Any], model: str, effort: str, repeat: int) -> None:
            async with gate:
                if spent["usd"] >= budget or stop or (q["id"], model, effort, repeat) in finished:
                    return
                result = await ask(clients[model], q, model, effort)
                if result.get("fatal"):
                    stop.append(f"{model}: {result['error']}")
                    return
                spent["usd"] += result.get("estimated_cost_usd") or 0.0
                scope = expected.scope_jobs(con, q["user"])
                row = {"question_id": q["id"], "user": q["user"], "model": model,
                       "provider": llm.provider_for(model), "effort": effort,
                       "repeat": repeat, "result": result, "grade": grade.grade(q, result, scope, con)}
                if judge_model and repeat < judge_repeats and result.get("answer"):
                    try:
                        row["judge"] = await judge.judge(judge_client, judge_model, q, result["answer"])
                    except Exception as error:  # A judge failure leaves the run graded without scores.
                        row["judge"] = {"scores": None, "error": str(error)}
                graded.append(row)
                with out_file.open("a") as f:
                    f.write(json.dumps(row, default=str) + "\n")
                mark = "pass" if row["grade"]["passed"] else "FAIL " + "; ".join(row["grade"]["reasons"])
                print(f"[{len(graded)}] {model} {effort} r{repeat} {q['id']}: {mark} "
                      f"(${result.get('estimated_cost_usd') or 0:.4f}, total ${spent['usd']:.2f})", flush=True)

        await asyncio.gather(*(one(q, m, e, r) for r in range(repeats) for m in models for e in efforts
                               for q in questions))
    if spent["usd"] >= budget:
        print(f"Stopped starting new runs at the ${budget:.2f} budget.", flush=True)
    if stop:
        print(f"Stopped on an API error that retrying cannot fix: {stop[0]}", flush=True)
    errors = sum(r["result"].get("status") == "error" for r in graded)
    if errors:
        print(f"{errors} runs failed with an API error. --resume runs them again.", flush=True)
    return graded


def estimate(runs: list[dict[str, Any]], questions: int, repeats: int, judge_model: str | None) -> float | None:
    """Print the projected cost of the full matrix from one measured question per setting.

    Returns None, with the errors printed, when any measured run failed with an API error,
    because a failed run costs nothing and would make the projection look free.
    """
    failed = [r for r in runs if r["result"].get("status") == "error"]
    if failed or not runs:
        print("\nNo projection: these settings failed with an API error.")
        for r in failed:
            print(f"  {r['model']} {r['effort']}: {r['result'].get('error')}")
        return None
    total = 0.0
    print(f"\nProjected cost for {questions} questions x {repeats} repeats:")
    for r in runs:
        cost = r["result"].get("estimated_cost_usd") or 0.0
        projected = cost * questions * repeats
        total += projected
        print(f"  {r['model']} {r['effort']}: ${cost:.4f} for one question -> ${projected:.2f}")
    if judge_model:
        print("  (LLM judge cost not included)")
    print(f"  Total: ${total:.2f}")
    return total


def write_outputs(runs: list[dict[str, Any]], data: dict[str, Any]) -> dict[str, Any]:
    """Build the scoreboard from graded runs and write results.md and scoreboard.json."""
    meta = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "as_of": data["as_of"], "data_hash": data["data_hash"],
            "questions": len({r["question_id"] for r in runs}),
            "repeats": max(r["repeat"] for r in runs) + 1}
    board = report.scoreboard(runs, meta, skipped={m: r for m, r in llm.skipped_models().items()
                                                   if m not in {r["model"] for r in runs}})
    report.write_reports(board, data["questions"], runs, SCOREBOARD, RESULTS)
    print(f"Wrote {RESULTS.relative_to(BACKEND)} and {SCOREBOARD.relative_to(BACKEND)}. "
          f"Default: {board['default']}")
    return board


def write_group_outputs(runs: list[dict[str, Any]], data: dict[str, Any], group: str) -> dict[str, Any]:
    """Write a non-core group's summary to evals/<group>.json and its section of results.md.
    The scoreboard and the rest of results.md are left as they are."""
    meta = {"group": group, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "as_of": data["as_of"], "data_hash": data["data_hash"]}
    summary = report.group_summary(runs, meta)
    path = Path(str(GROUP_SUMMARY).format(group=group))
    path.write_text(json.dumps(summary, indent=1) + "\n")
    RESULTS.write_text(report.with_group_section(RESULTS.read_text() if RESULTS.exists() else "",
                                                 report.group_markdown(summary)))
    print(f"Wrote {path.relative_to(BACKEND)} and the {group} section of {RESULTS.relative_to(BACKEND)}. "
          f"Passed {summary['passed']} of {summary['runs']}, ${summary['total_cost_usd']:.4f}.")
    return summary


def regrade(path: Path, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Graded runs read back from a runs.jsonl file, regraded with the current checks."""
    by_id = {q["id"]: q for q in data["questions"]}
    runs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    with closing(expected.connect()) as con:
        for r in runs:
            q = by_id[r["question_id"]]
            r["grade"] = grade.grade(q, r["result"], expected.scope_jobs(con, q["user"]), con)
    return [r for r in runs if r["question_id"] in by_id]


def judge_targets(runs: list[dict[str, Any]], missing_only: bool, judge_repeats: int) -> list[dict[str, Any]]:
    """The kept runs to send to the judge.

    By default these are the runs judged before, so a rubric change rescores the same set.
    With missing_only, they are the runs in the first judge_repeats repeats that have an
    answer but no judge scores yet, for example a setting that was rerun without --judge.
    """
    answered = [r for r in runs if r["result"].get("answer")]
    if missing_only:
        return [r for r in answered if r["repeat"] < judge_repeats and not (r.get("judge") or {}).get("scores")]
    return [r for r in answered if r.get("judge")]


async def rejudge(runs: list[dict[str, Any]], data: dict[str, Any], judge_model: str,
                  missing_only: bool = False, judge_repeats: int = 1) -> None:
    """Judge kept runs again (after a rubric change) or, with missing_only, judge the ones never judged."""
    client = loop.make_client(judge_model, "eval")
    by_id = {q["id"]: q for q in data["questions"]}
    targets = judge_targets(runs, missing_only, judge_repeats)
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(r: dict[str, Any]) -> None:
        async with gate:
            try:
                r["judge"] = await judge.judge(client, judge_model, by_id[r["question_id"]], r["result"]["answer"])
            except Exception as error:  # Keep the run; it has no judge scores.
                r["judge"] = {"scores": None, "error": str(root_error(error))}

    await asyncio.gather(*(one(r) for r in targets))
    print(f"Judged {len(targets)} kept runs again with {judge_model}.", flush=True)


async def record(model: str, effort: str) -> None:
    """Record verified answers for every suggested question for every demo user, plus every
    question already in recordings.json, into data/recordings.json.

    Each question is tried up to RECORD_ATTEMPTS times until the answer is verified; if none
    is, the last answer is kept and reported, because a labeled unverified recording is
    still a better fallback than no answer. An API error stops recording and leaves the
    recordings saved so far in place.
    """
    client = loop.make_client(model)  # Recordings back the app, so OpenAI is refused here like in the app.
    wanted = {(c, u["user_id"], None) for u in access.demo_users() for c in CHIPS[u["role"]]}
    wanted |= {(r["question"], r["user_id"], r.get("job_id")) for r in recordings.load()}
    total = 0.0
    for question, user_id, job_id in sorted(wanted, key=lambda w: (w[1], w[0])):
        principal = access.principal_for(user_id)
        for attempt in range(1, RECORD_ATTEMPTS + 1):
            result = await ask(client, {"question": question, "user": user_id, "job_id": job_id}, model, effort)
            if result["status"] == "error":
                print(f"Stopped recording on an API error: {result['error']}", flush=True)
                return
            total += result["estimated_cost_usd"] or 0.0
            if result["verified"]:
                break
        recordings.save(question, user_id, job_id, sorted(principal.allowed_job_ids), result, store.now())
        print(f"{user_id} {question!r}: {result['label']} after {attempt} attempt(s), total ${total:.2f}",
              flush=True)


def missing_keys(models: list[str]) -> list[str]:
    """The API key variables the given models need that are not set. Unknown model IDs stop the run."""
    try:
        needed = {llm.api_key_env(m) for m in models}
    except ValueError as error:
        raise SystemExit(str(error)) from None
    return sorted(k for k in needed if not os.environ.get(k))


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run, estimate, regrade, or record."""
    parser = argparse.ArgumentParser(description="Run the RecruitAssist evals.")
    parser.add_argument("--models", nargs="+", default=MODELS)
    parser.add_argument("--efforts", nargs="+", default=EFFORTS)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--questions", nargs="+", help="Question IDs to run. Default: all in the group.")
    parser.add_argument("--group", default=DEFAULT_GROUP,
                        help="Question group to run. Default: core, the group behind the scoreboard.")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--budget", type=float, default=BUDGET_USD, help="Stop starting runs past this spend.")
    parser.add_argument("--judge", metavar="MODEL", help="Add LLM judge scores using this model.")
    parser.add_argument("--judge-repeats", type=int, default=1, help="Judge only the first N repeats.")
    parser.add_argument("--estimate", action="store_true", help="Measure one question per setting and stop.")
    parser.add_argument("--from-runs", type=Path, help="Regrade a runs.jsonl file and write the reports.")
    parser.add_argument("--resume", type=Path, help="Continue a runs.jsonl file, running only the missing runs.")
    parser.add_argument("--rejudge", action="store_true", help="With --resume, judge the kept runs again.")
    parser.add_argument("--judge-missing", action="store_true",
                        help="With --resume and --judge, judge only kept runs that have no judge scores yet.")
    parser.add_argument("--record", action="store_true", help="Record the suggested questions instead.")
    args = parser.parse_args(argv)

    load_env_file()
    missing = missing_keys(args.models + ([args.judge] if args.judge else []))
    if missing and not args.from_runs:
        raise SystemExit("Set these keys in backend/.env first: " + ", ".join(missing))
    # The evals score the seed data, so job assignments must not come from a shared Redis store.
    os.environ.pop("UPSTASH_REDIS_REST_URL", None)
    data = load_questions(args.questions, args.group)
    grouped = args.group != DEFAULT_GROUP
    if grouped and (len(args.models) != 1 or len(args.efforts) != 1):
        raise SystemExit("A group other than core runs one model at one effort: pass one --models and one --efforts.")
    finish = (lambda runs: write_group_outputs(runs, data, args.group)) if grouped else \
        (lambda runs: write_outputs(runs, data))

    if args.from_runs:
        finish(regrade(args.from_runs, data))
        return 0
    if args.record:
        asyncio.run(record(args.models[0], args.efforts[0]))
        return 0

    done: list[dict[str, Any]] = []
    if args.resume:
        out_file = args.resume.resolve()
        done = [r for r in regrade(out_file, data) if r["result"].get("status") != "error"]
        if (args.rejudge or args.judge_missing) and args.judge:
            asyncio.run(rejudge(done, data, args.judge, args.judge_missing, args.judge_repeats))
        out_file.write_text("".join(json.dumps(r, default=str) + "\n" for r in done))
    else:
        out = OUT_DIR / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out.mkdir(parents=True, exist_ok=True)
        out_file = out / "runs.jsonl"
    if args.estimate:
        sample = [q for q in data["questions"] if q["id"] == ESTIMATE_QUESTION] or data["questions"][:1]
        runs = asyncio.run(run_matrix(sample, args.models, args.efforts, 1, args.concurrency, args.budget,
                                      None, 0, out_file))
        projected = estimate(runs, len(load_questions(None, args.group)["questions"]), args.repeats, args.judge)
        return 0 if projected is not None else 1
    runs = asyncio.run(run_matrix(data["questions"], args.models, args.efforts, args.repeats,
                                  args.concurrency, args.budget, args.judge, args.judge_repeats, out_file, done))
    print(f"Raw runs: {out_file.relative_to(BACKEND)}")
    if runs:
        finish(runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
