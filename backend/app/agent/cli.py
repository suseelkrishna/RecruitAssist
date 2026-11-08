"""Ask the agent one question from the command line, as one demo user.

    python -m app.agent.cli "Which tasks are pending or overdue?" --user USR-4 [--job JOB-2]
        [--model claude-sonnet-5-5] [--json] [--record]

Prints the answer, the verifier report, the tool steps, and the token, cache,
and cost numbers. --record saves the result to data/recordings.json so the API
can serve it when live answers are rate limited. Reads ANTHROPIC_API_KEY from
the environment or from backend/.env.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app import access, store
from app.agent import loop, recordings
from app.env import load_env_file


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments, run the agent, and print the result. Returns the exit code."""
    parser = argparse.ArgumentParser(description="Ask RecruitAssist one question.")
    parser.add_argument("question")
    parser.add_argument("--user", default="USR-1", help="Demo user ID, such as USR-4. Default USR-1 (admin).")
    parser.add_argument("--job", default=None, help="Selected job ID, such as JOB-2.")
    parser.add_argument("--model", default=None, help=f"Model ID. Default ANTHROPIC_MODEL or {loop.DEFAULT_MODEL}.")
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON.")
    parser.add_argument("--record", action="store_true", help="Save the result to data/recordings.json.")
    args = parser.parse_args(argv)
    load_env_file()
    try:
        principal = access.principal_for(args.user)
    except LookupError as error:
        print(error, file=sys.stderr)
        return 2
    result = asyncio.run(loop.run_agent(args.question, principal, job_id=args.job, model=args.model))
    if args.record:
        recordings.save(args.question, args.user, args.job, sorted(principal.allowed_job_ids), result, store.now())
    print(json.dumps(result, indent=2) if args.json else summary(result, principal))
    return 0


def summary(result: dict, principal: access.Principal) -> str:
    """A readable report: who asked, the answer, the verifier, the tool steps, and the usage."""
    usage = result["usage"]
    report = result["verifier"]
    lines = [
        f"User: {principal.user_id} {principal.name} ({principal.role})   Model: {result['model']}"
        f" (served by {result['served_by']})",
        "",
        result["answer"],
        "",
        f"Status: {result['status']}   Label: {result['label']}   Retried: {result['retried']}",
        "Verifier: " + ", ".join(f"{name} {'pass' if check['passed'] else 'FAIL'}"
                                 for name, check in report["checks"].items()),
    ]
    lines += [f"  - {failure}" for failure in report["failures"]]
    lines.append("Tool steps:")
    lines += [f"  {s['tool']}({json.dumps(s['input'])}) rows={s['rows']}{' ERROR' if s['is_error'] else ''}"
              for s in result["steps"]] or ["  (none)"]
    lines.append(f"Tokens: input {usage['input_tokens']}, output {usage['output_tokens']}, "
                 f"cache write {usage['cache_creation_input_tokens']}, cache read {usage['cache_read_input_tokens']}")
    lines.append(f"API calls: {usage['api_calls']}, cache hits: {usage['cache_hits']}, "
                 f"latency: {result['latency_ms']} ms, estimated cost: ${result['estimated_cost_usd']}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
