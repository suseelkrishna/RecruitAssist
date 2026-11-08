"""Saved answers for the app's Replay mode.

Every successful live answer is stored in recordings/answers.json with its
Behind the scenes steps, including the raw tool results. Replay mode shows a
stored answer without calling the Claude API or the MCP server.

Recordings can also be imported from an eval run (tests/run_evals.py
transcripts), so Replay has answers before any live question is asked:

    python recordings.py import-evals            # newest run in evals_out/
    python recordings.py import-evals <run dir>  # a specific run
    python recordings.py list
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RECORDINGS_FILE = ROOT / "recordings" / "answers.json"
DB_PATH = ROOT / "recruiting.db"
EVALS_OUT = ROOT / "evals_out"
TIME_FMT = "%Y-%m-%d %H:%M:%S"

STAGES = ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer", "Hired"]

TOOL_LABELS = {
    "pipeline_by_job": "Pipeline by job",
    "stuck_candidates": "Stuck candidates",
    "time_to_fill": "Time to fill",
}


# --- Behind the scenes steps (shared by live answers and imports) ---------------

def describe_inputs(args: dict) -> str:
    if not args:
        return "no filters (everything)"
    parts = []
    for key, value in args.items():
        if key == "days":
            parts.append(f"more than {value} days")
        elif key == "job_id":
            parts.append(f"job #{value}")
        elif key == "team":
            parts.append(f"team “{value}”")
        else:
            parts.append(f"{key} = {value}")
    return ", ".join(parts)


def describe_result(name: str, data: Any) -> str:
    if name == "stuck_candidates":
        return f"{data['count']} rows, one per stuck candidate"
    if name == "pipeline_by_job":
        if "jobs" in data:
            return (f"{len(data['jobs']) * len(STAGES)} rows: {len(STAGES)} stages for each of "
                    f"{len(data['jobs'])} jobs, plus a total")
        return f"{len(STAGES)} rows, one per stage of {data['title']}"
    if name == "time_to_fill":
        if "by_team" in data:
            return f"{len(data['by_team'])} rows, one per team, plus an overall total"
        return f"1 row for {data['team']}"
    return "a result"


def tool_steps(name: str, args: dict, data: Any, is_error: bool) -> list[dict]:
    """The two trace steps for one tool call: the choice, and what came back."""
    chose = {"title": f"Claude chose the tool “{TOOL_LABELS.get(name, name)}”",
             "detail": f"With: {describe_inputs(args)}"}
    if is_error:
        return [chose, {"title": "Database returned an error", "detail": data,
                        "raw": data, "error": True}]
    return [chose, {"title": "Database returned " + describe_result(name, data),
                    "raw": data, "error": False}]


def answer_step(used_tools: int) -> dict:
    if used_tools:
        return {"title": "Claude wrote the answer",
                "detail": "From the database results above, in plain English."}
    return {"title": "Claude wrote the answer",
            "detail": "Without checking the database. Treat any numbers in it with care."}


def strip_tool_error(text: str) -> str:
    return re.sub(r"^Error executing tool \w+: ", "", text)


# --- Storage --------------------------------------------------------------------

def key(question: str) -> str:
    """Match questions loosely: case, spacing and trailing punctuation don't matter."""
    return re.sub(r"\s+", " ", question).strip().lower().rstrip("?.! ")


def load() -> list[dict]:
    try:
        return json.loads(RECORDINGS_FILE.read_text()).get("answers", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write(answers: list[dict]) -> None:
    RECORDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file and swap it in, so a crash can't leave half a file.
    fd, tmp = tempfile.mkstemp(dir=RECORDINGS_FILE.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump({"version": 1, "answers": answers}, f, indent=2, ensure_ascii=False)
    os.replace(tmp, RECORDINGS_FILE)


def data_as_of() -> str | None:
    """When recruiting.db was last rebuilt, to spot recordings made on older data."""
    if not DB_PATH.exists():
        return None
    return datetime.fromtimestamp(DB_PATH.stat().st_mtime).strftime(TIME_FMT)


def save(question: str, answer: str, steps: list[dict], model: str, source: str = "live",
         recorded_at: str | None = None) -> dict:
    """Store an answer, replacing any earlier recording of the same question."""
    entry = {
        "question": question.strip(),
        "answer": answer,
        "steps": steps,
        "model": model,
        "source": source,
        "recorded_at": recorded_at or datetime.now().strftime(TIME_FMT),
        "data_as_of": data_as_of(),
    }
    answers = [a for a in load() if key(a["question"]) != key(question)]
    answers.append(entry)
    _write(answers)
    return entry


def find(question: str) -> dict | None:
    k = key(question)
    return next((a for a in load() if key(a["question"]) == k), None)


def delete(question: str) -> None:
    _write([a for a in load() if key(a["question"]) != key(question)])


def is_stale(entry: dict) -> bool:
    """True if the database was rebuilt after this answer was recorded."""
    current = data_as_of()
    return bool(current and entry.get("data_as_of") and current > entry["data_as_of"])


# --- Import from an eval run -------------------------------------------------------

def from_transcript(path: Path) -> tuple[str, list[dict], str | None] | None:
    """(answer, steps, model) from a `claude -p --output-format stream-json` transcript."""
    model, answer, steps, used = None, None, [], 0
    pending: dict[str, tuple[str, dict]] = {}  # tool_use id -> (tool name, args)
    for line in path.read_text().splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = msg.get("type")
        if kind == "system" and msg.get("subtype") == "init":
            model = msg.get("model")
        elif kind == "assistant":
            for block in msg["message"]["content"]:
                if block.get("type") == "tool_use":
                    name = block["name"].split("__")[-1]  # mcp__recruiting-pipeline__<tool>
                    pending[block["id"]] = (name, block.get("input") or {})
        elif kind == "user":
            for block in msg["message"].get("content", []):
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                if block["tool_use_id"] not in pending:
                    continue
                name, args = pending.pop(block["tool_use_id"])
                content = block.get("content")
                if isinstance(content, list):
                    content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
                is_error = bool(block.get("is_error"))
                if is_error:
                    data: Any = strip_tool_error(content or "")
                else:
                    try:
                        data = json.loads(content)
                    except (TypeError, json.JSONDecodeError):
                        data = content
                steps += tool_steps(name, args, data, is_error)
                used += 1
        elif kind == "result" and not msg.get("is_error"):
            answer = msg.get("result")
    if not answer:
        return None
    return answer, steps + [answer_step(used)], model


def import_eval_run(run_dir: Path) -> list[str]:
    """Save every answered question of an eval run as a recording. Returns the questions."""
    sys.path.insert(0, str(ROOT / "tests"))
    from run_evals import load_questions  # noqa: E402

    meta = json.loads((run_dir / "meta.json").read_text())
    started = meta.get("started_at")
    imported = []
    for n, question, _expected in load_questions():
        path = run_dir / f"q{n:02d}.jsonl"
        if not path.exists():
            continue
        parsed = from_transcript(path)
        if not parsed:
            continue
        answer, steps, model = parsed
        steps = [{"title": "Question received", "detail": f"“{question}”"}] + steps
        save(question, answer, steps, model or meta.get("model", "unknown"),
             source=f"eval run {run_dir.name}", recorded_at=started)
        imported.append(question)
    # Eval runs were recorded on the data that existed then; keep that as-of time.
    if started:
        answers = load()
        for a in answers:
            if a["source"] == f"eval run {run_dir.name}":
                a["data_as_of"] = min(a["data_as_of"] or started, started)
        _write(answers)
    return imported


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["import-evals"]:
        if len(args) > 1:
            run_dir = Path(args[1])
        else:
            runs = sorted(p for p in EVALS_OUT.glob("*") if (p / "meta.json").exists())
            if not runs:
                sys.exit("No eval runs in evals_out/. Run: python tests/run_evals.py")
            run_dir = runs[-1]
        imported = import_eval_run(run_dir)
        print(f"Imported {len(imported)} answers from {run_dir.name} into {RECORDINGS_FILE}")
    elif args[:1] == ["list"]:
        for a in load():
            print(f"{a['recorded_at']}  {a['model']:<20} {a['source']:<28} {a['question']}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
