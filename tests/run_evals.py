"""Ask Claude the questions in eval_questions.md through the recruiting-pipeline server.

Each question runs in its own headless Claude Code session (`claude -p`) that
has only this server's three tools. Built-in tools are turned off, so Claude
can't read the database or this folder. For each question the script prints
the tool calls Claude made, its answer, and the expected answer, so you can
score them by hand.

Each run is saved in its own folder, evals_out/<YYYY-MM-DD_HHMMSS>/ (ignored by
git), with one transcript per question and a meta.json naming the model and
questions. The Streamlit app reads the newest folder.

Usage (from the project folder, after `python generate_data.py`):
    python tests/run_evals.py                 # all questions
    python tests/run_evals.py --only 4 10     # just questions 4 and 10
    python tests/run_evals.py --model opus    # pick the model
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_MD = ROOT / "tests" / "eval_questions.md"
OUT_DIR = ROOT / "evals_out"
SERVER = "recruiting-pipeline"
TOOLS = ["pipeline_by_job", "stuck_candidates", "time_to_fill"]


def load_questions() -> list[tuple[int, str, str]]:
    """Return (number, question, expected section) from eval_questions.md."""
    text = QUESTIONS_MD.read_text()
    parts = re.split(r"^### (\d+)\. (.+)$", text, flags=re.M)
    # parts = [preamble, num, question, body, num, question, body, ...]
    return [(int(parts[i]), parts[i + 1].strip(), parts[i + 2].strip())
            for i in range(1, len(parts), 3)]


def ask(n: int, question: str, workdir: Path, run_dir: Path, model: str | None,
        timeout: int) -> Path:
    cmd = [
        "claude", "-p", question,
        "--mcp-config", str(workdir / "mcp.json"), "--strict-mcp-config",
        "--tools", "",
        "--allowedTools", ",".join(f"mcp__{SERVER}__{t}" for t in TOOLS),
        "--no-session-persistence",
        "--output-format", "stream-json", "--verbose",
    ]
    if model:
        cmd += ["--model", model]
    out = run_dir / f"q{n:02d}.jsonl"
    with out.open("w") as f:
        # Run from an empty folder so no project files or CLAUDE.md are picked up.
        subprocess.run(cmd, cwd=workdir, stdin=subprocess.DEVNULL, stdout=f,
                       stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    return out


def summarize(path: Path) -> tuple[str | None, list[str], str]:
    """Return (model, tool call lines, final answer) from a stream-json transcript."""
    model, calls, answer = None, [], "(no answer: the run failed or timed out)"
    for line in path.read_text().splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = msg.get("type")
        if kind == "system" and msg.get("subtype") == "init":
            model = msg.get("model")
        elif kind == "assistant":
            for c in msg["message"]["content"]:
                if c.get("type") == "tool_use":
                    calls.append(f"{c['name'].split('__')[-1]}({json.dumps(c['input'])})")
        elif kind == "user":
            for c in msg["message"].get("content", []):
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("is_error"):
                    calls.append(f"  -> tool error: {str(c.get('content'))[:160]}")
        elif kind == "result":
            answer = msg.get("result") or answer
    return model, calls, answer


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", type=int, nargs="+", metavar="N", help="question numbers to run")
    p.add_argument("--model", help="model to use (default: Claude Code's default)")
    p.add_argument("--jobs", type=int, default=5, help="questions to run at once (default 5)")
    p.add_argument("--timeout", type=int, default=300, help="seconds per question (default 300)")
    args = p.parse_args()

    if not shutil.which("claude"):
        sys.exit("The `claude` command isn't on your PATH. Install Claude Code first.")
    if not (ROOT / "recruiting.db").exists():
        sys.exit("recruiting.db not found. Run: python generate_data.py")

    questions = load_questions()
    if args.only:
        questions = [q for q in questions if q[0] in args.only]
    started = datetime.now()
    run_dir = OUT_DIR / started.strftime("%Y-%m-%d_%H%M%S")
    run_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        (workdir / "mcp.json").write_text(json.dumps({"mcpServers": {SERVER: {
            "command": sys.executable, "args": [str(ROOT / "server.py")]}}}))

        print(f"Asking {len(questions)} question(s)...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {n: pool.submit(ask, n, q, workdir, run_dir, args.model, args.timeout)
                       for n, q, _ in questions}
            transcripts = {}
            for n, fut in futures.items():
                try:
                    transcripts[n] = fut.result()
                except subprocess.TimeoutExpired:
                    transcripts[n] = None

    models = set()
    for n, question, expected in questions:
        print(f"\n{'=' * 78}\nQ{n}. {question}\n{'=' * 78}")
        if transcripts[n] is None:
            print(f"Timed out after {args.timeout}s.")
            continue
        model, calls, answer = summarize(transcripts[n])
        if model:
            models.add(model)
        print(f"Model: {model}")
        print("Tool calls:\n  " + ("\n  ".join(calls) if calls else "(none)"))
        print(f"\n--- Claude's answer ---\n{answer}")
        print(f"\n--- Expected ---\n{expected}")

    (run_dir / "meta.json").write_text(json.dumps({
        "run": run_dir.name,
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "model": ", ".join(sorted(models)) or args.model,
        "questions": [n for n, _, _ in questions],
    }, indent=2))
    print(f"\nTranscripts saved in {run_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
