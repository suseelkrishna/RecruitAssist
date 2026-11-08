"""Recruiting Pipeline Assistant: a Streamlit demo of the recruiting-pipeline MCP server.

Every number on screen comes from the real MCP server. The app starts server.py
with the MCP stdio client, lists its tools, hands them to Claude through the
Anthropic Messages API, and sends each tool call Claude makes back through that
same MCP session. Claude never touches the database directly.

Setup: put ANTHROPIC_API_KEY (and optionally ANTHROPIC_MODEL) in .env, then
    streamlit run app.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import altair as alt
import anthropic
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

import recordings
from recordings import STAGES, answer_step, strip_tool_error, tool_steps

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "recruiting.db"
README = ROOT / "README.md"
EVALS_OUT = ROOT / "evals_out"
SCORES_FILE = ROOT / "tests" / "eval_scores.json"

load_dotenv(ROOT / ".env")
MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-opus-5-5"

# Current models that take an explicit effort level, and the subset that accepts
# the server-side refusal fallback. Other models get a plain request.
EFFORT_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5",
                 "claude-sonnet-5-5", "claude-haiku-5-5"}
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
MAX_TOOL_ROUNDS = 6

FOOTER = "Read-only. Synthetic data. Numbers come from the database, not the AI."
BAR_COLOR = "#2a78d6"

# (button label, question sent to Claude)
EXAMPLES = [
    ("Stuck over 10 days", "Which candidates have been stuck in a stage for more than 10 days?"),
    ("Engineering: Technical → Onsite", "What's the Technical to Onsite conversion for Engineering roles?"),
    ("Median time to fill", "What's our median time to fill, and how many jobs are still open?"),
    ("Time to fill for Marketing", "What's the time to fill for the Marketing team?"),
]

SYSTEM_PROMPT = """You answer recruiting questions for a hiring team, using the tools provided.
They read a synthetic (made-up) recruiting database, read-only.

- Always get numbers from the tools. Never estimate or invent a figure.
- If a question needs a simple total across jobs, add up the tool's counts and say you did.
- If a tool returns an error, explain it plainly and say what the valid options are.
- Write for a non-technical reader: short, plain English, no SQL or tool names.
  Use a small table when listing several items. Mention small sample sizes when they matter."""


# --- MCP client ---------------------------------------------------------------

SERVER = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], cwd=str(ROOT))


async def open_session(work):
    """Start server.py over stdio, run `work(session)`, then shut the server down."""
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await work(session)


def unpack(result) -> tuple[Any, bool]:
    """Turn an MCP tool result into (data, is_error)."""
    text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    if result.is_error:
        return strip_tool_error(text), True
    if result.structured_content is not None:
        return result.structured_content, False
    try:
        return json.loads(text), False
    except json.JSONDecodeError:
        return text, False


def call_tools(calls: list[tuple[str, dict]]) -> list[Any]:
    """Run several tool calls in one MCP session. Raises on a tool error."""
    async def work(session):
        out = []
        for name, args in calls:
            data, is_error = unpack(await session.call_tool(name, args))
            if is_error:
                raise RuntimeError(data)
            out.append(data)
        return out
    return asyncio.run(open_session(work))


def root_cause(exc: BaseException) -> BaseException:
    """anyio wraps errors in exception groups; dig out the first real one."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def friendly_error(exc: BaseException) -> str:
    exc = root_cause(exc)
    if isinstance(exc, anthropic.AuthenticationError):
        return "Claude rejected the API key. Check ANTHROPIC_API_KEY in your .env file."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This API key isn't allowed to use that model. Try another ANTHROPIC_MODEL."
    if isinstance(exc, anthropic.NotFoundError):
        return f"Claude doesn't recognize the model “{MODEL}”. Check ANTHROPIC_MODEL in .env."
    if isinstance(exc, anthropic.RateLimitError):
        return "Claude is getting too many requests right now. Wait a minute and try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Couldn't reach Claude. Check your internet connection and try again."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Claude returned an error ({exc.status_code}). Try again in a moment."
    if not DB_PATH.exists():
        return "The recruiting database is missing. Run `uv run python data/generate.py` first."
    if isinstance(exc, OSError):
        return "Couldn't start the recruiting data server (server.py)."
    return "Something went wrong while answering. Try again, or try a different question."


# --- Claude + MCP: answering a question ----------------------------------------

async def ask_claude(question: str, history: list[dict]) -> tuple[str, list[dict]]:
    """Answer one question. Returns (answer, steps) for the Behind-the-scenes panel."""
    steps = [{"title": "Question received", "detail": f"“{question}”"}]

    async def work(session: ClientSession):
        listed = await session.list_tools()
        tools = [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
                 for t in listed.tools]
        client = anthropic.AsyncAnthropic()
        messages = history + [{"role": "user", "content": question}]
        used_tools = 0

        for _ in range(MAX_TOOL_ROUNDS):
            request = dict(model=MODEL, max_tokens=16000, system=SYSTEM_PROMPT,
                           tools=tools, messages=messages)
            if MODEL in EFFORT_MODELS:
                request["output_config"] = {"effort": "medium"}
            if MODEL in FALLBACK_MODELS:
                response = await client.beta.messages.create(
                    **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                response = await client.messages.create(**request)

            if response.stop_reason == "refusal":
                return "Claude declined to answer that question.", used_tools
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "pause_turn":
                continue
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                text = "".join(b.text for b in response.content if b.type == "text").strip()
                return text or "Claude didn't write an answer.", used_tools

            results = []
            for use in tool_uses:
                used_tools += 1
                # Every tool call goes through the MCP session, never straight to the database.
                data, is_error = unpack(await session.call_tool(use.name, use.input))
                steps.extend(tool_steps(use.name, use.input, data, is_error))
                results.append({"type": "tool_result", "tool_use_id": use.id,
                                "content": data if is_error else json.dumps(data),
                                "is_error": is_error})
            messages.append({"role": "user", "content": results})

        return "Claude kept asking for more data without finishing. Try a narrower question.", used_tools

    answer, used_tools = await open_session(work)
    steps.append(answer_step(used_tools))
    return answer, steps


# --- Small helpers --------------------------------------------------------------

def footer() -> None:
    st.divider()
    st.caption(FOOTER)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plain(text: str, limit: int = 220) -> str:
    """Markdown to a short single line for a table cell."""
    text = re.sub(r"\|[-| ]+\|", " ", text)          # table separator rows
    text = re.sub(r"[*_`#>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --- Tab 1: Ask a question -------------------------------------------------------

def recorded_label(entry: dict) -> str:
    when = datetime.strptime(entry["recorded_at"], recordings.TIME_FMT)
    source = "a live session" if entry["source"] == "live" else entry["source"]
    return f"Replayed · recorded {when:%b %-d, %-I:%M %p} · {entry['model']} · from {source}"


def ask_live(question: str) -> dict:
    """Answer through Claude + MCP, and save the result for Replay."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"question": question, "answer": None, "steps": [],
                "error": "No API key found. Add ANTHROPIC_API_KEY to a .env file next to app.py "
                         "and restart the app, or switch to Replay to use recorded answers."}
    history = []
    for turn in st.session_state.chat:
        if turn["answer"]:
            history += [{"role": "user", "content": turn["question"]},
                        {"role": "assistant", "content": turn["answer"]}]
    with st.spinner("Checking the database…"):
        try:
            answer, steps = asyncio.run(ask_claude(question, history))
        except Exception as exc:  # shown to the viewer in plain words
            print(f"ask_claude failed: {root_cause(exc)!r}", file=sys.stderr)
            return {"question": question, "answer": None, "steps": [], "error": friendly_error(exc)}
    try:
        recordings.save(question, answer, steps, MODEL)
        st.toast("Saved for Replay")
    except OSError as exc:
        print(f"saving recording failed: {exc!r}", file=sys.stderr)
        st.toast("Couldn't save this answer for Replay")
    return {"question": question, "answer": answer, "steps": steps, "error": None}


def ask_replay(question: str) -> dict:
    """Show a recorded answer. No API call, no MCP call."""
    entry = recordings.find(question)
    if not entry:
        return {"question": question, "answer": None, "steps": [], "error": None,
                "notice": "No recording for this question yet. Ask it once in Live mode to save it."}
    return {"question": entry["question"], "answer": entry["answer"], "steps": entry["steps"],
            "error": None, "replay": entry}


def tab_ask() -> None:
    st.session_state.setdefault("chat", [])
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    left, right = st.columns([3, 2], gap="large")

    with left:
        mode = st.segmented_control("Mode", ["Live", "Replay"], key="ask_mode",
                                    default="Live" if has_key else "Replay",
                                    label_visibility="collapsed") or "Live"
        saved = sorted(recordings.load(), key=lambda e: e["recorded_at"], reverse=True)
        if mode == "Live":
            st.caption(f"Live: Claude ({MODEL}) answers from the database through MCP. "
                       "Each answer is saved for Replay.")
        else:
            st.caption(f"Replay: {len(saved)} recorded answers, shown without calling the "
                       "Claude API or the database.")
        history_box = st.container()

        picked = None
        if mode == "Live":
            st.write("**Try an example:**")
            ex_cols = st.columns(2)
            for i, (label, example) in enumerate(EXAMPLES):
                if ex_cols[i % 2].button(label, key=f"ex{i}", help=example, width="stretch"):
                    picked = example
        elif not saved:
            st.info("No recordings yet. Ask questions in Live mode, or import an eval run with "
                    "`python recordings.py import-evals`.")
        else:
            st.write("**Recorded questions:**")
            for i, entry in enumerate(saved):
                if st.button(entry["question"], key=f"rec{i}", width="stretch"):
                    picked = entry["question"]

        typed = st.chat_input("Ask about the hiring pipeline…" if mode == "Live"
                              else "Type a recorded question…")
        question = typed or picked
        if question:
            turn = ask_live(question) if mode == "Live" else ask_replay(question)
            st.session_state.chat.append(turn)

        with history_box:
            if not st.session_state.chat:
                st.info("Ask a question below, or click an example." if mode == "Live"
                        else "Click a recorded question below to replay it.")
            for turn in st.session_state.chat:
                with st.chat_message("user"):
                    st.markdown(turn["question"])
                with st.chat_message("assistant"):
                    if turn["error"]:
                        st.error(turn["error"])
                    elif turn.get("notice"):
                        st.info(turn["notice"])
                    else:
                        st.markdown(turn["answer"])
                        if turn.get("replay"):
                            st.caption(recorded_label(turn["replay"]))
                            if recordings.is_stale(turn["replay"]):
                                st.warning("Recorded before the data was last rebuilt, so the "
                                           "numbers may differ from a live answer.")

        if mode == "Replay" and saved:
            with st.expander(f"Manage recordings ({len(saved)})"):
                for i, entry in enumerate(saved):
                    q_col, del_col = st.columns([5, 1])
                    q_col.caption(f"{entry['question']}  \n{entry['recorded_at']} · {entry['model']}")
                    del_col.button("Delete", key=f"del{i}", on_click=recordings.delete,
                                   args=(entry["question"],), width="stretch")

    with right:
        st.subheader("Behind the scenes")
        answered = [t for t in st.session_state.chat if t["steps"]]
        if not answered:
            st.caption("Each answer's steps show up here: what Claude looked up, and what came back.")
        else:
            index = len(answered) - 1
            if len(answered) > 1:
                index = st.selectbox(
                    "Show steps for", list(reversed(range(len(answered)))),
                    format_func=lambda i: answered[i]["question"]
                    + (" (replay)" if answered[i].get("replay") else ""))
            turn = answered[index]
            if turn.get("replay"):
                st.caption("Recorded steps from when this answer was made. Nothing was re-run.")
            for n, step in enumerate(turn["steps"], start=1):
                with st.container(border=True):
                    st.markdown(f"**{n}. {step['title']}**")
                    if step.get("detail"):
                        st.caption(step["detail"])
                    if "raw" in step:
                        with st.expander("See the raw result"):
                            if step.get("error"):
                                st.code(step["raw"], language=None)
                            else:
                                st.json(step["raw"], expanded=False)


# --- Tab 2: Pipeline snapshot ------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def snapshot(days: int) -> tuple[dict, dict, str]:
    pipeline, stuck = call_tools([("pipeline_by_job", {}), ("stuck_candidates", {"days": days})])
    return pipeline, stuck, datetime.now().strftime("%H:%M")


def text_color() -> str:
    """Primary ink for the current light/dark theme (Vega text defaults to black)."""
    try:
        dark = st.context.theme.type == "dark"
    except AttributeError:
        dark = False
    return "#f0efec" if dark else "#0b0b0b"


def funnel_chart(stages: list[dict]) -> alt.Chart:
    # Build labels from the raw dicts: pandas would turn a missing % into NaN.
    labels = [f"{s['reached']}  ·  {s['conversion_pct']:g}%" if s["conversion_pct"] is not None
              else str(s["reached"]) for s in stages]
    moved_on = [f"{s['conversion_pct']:g}% of the previous stage" if s["conversion_pct"] is not None
                else "Starting point" for s in stages]
    df = pd.DataFrame(stages).assign(label=labels, conversion=moved_on)
    base = alt.Chart(df).encode(
        y=alt.Y("stage:N", sort=STAGES, title=None, axis=alt.Axis(labelLimit=200)),
        x=alt.X("reached:Q", title="Candidates who reached this stage", axis=alt.Axis(tickCount=6),
                scale=alt.Scale(domainMax=max(df["reached"].max() * 1.15, 1))),
        tooltip=[alt.Tooltip("stage:N", title="Stage"),
                 alt.Tooltip("reached:Q", title="Reached"),
                 alt.Tooltip("in_stage:Q", title="There now"),
                 alt.Tooltip("conversion:N", title="Moved on")],
    )
    bars = base.mark_bar(color=BAR_COLOR, cornerRadiusEnd=4, height={"band": 0.7})
    text = base.mark_text(align="left", dx=6, color=text_color()).encode(text="label:N")
    return (bars + text).properties(height=280)


def tab_snapshot() -> None:
    days = st.slider("Count a candidate as stuck after this many days in one stage", 1, 30, 7)
    try:
        pipeline, stuck, at = snapshot(days)
    except Exception as exc:
        print(f"snapshot failed: {root_cause(exc)!r}", file=sys.stderr)
        st.error(friendly_error(exc))
        return

    all_stages = {s["stage"]: s for s in pipeline["all_jobs"]}
    c1, c2, c3 = st.columns(3)
    c1.metric("Applications", all_stages["Applied"]["reached"])
    c2.metric("Hires", all_stages["Hired"]["reached"])
    c3.metric(f"Stuck more than {days} days", stuck["count"])

    st.subheader("Hiring funnel")
    jobs = {f"{j['title']} ({j['team']}, {j['status']})": j for j in pipeline["jobs"]}
    pick = st.selectbox("Job", ["All jobs"] + list(jobs))
    stages = pipeline["all_jobs"] if pick == "All jobs" else jobs[pick]["stages"]
    st.altair_chart(funnel_chart(stages), width="stretch")
    st.caption("Each bar is how many candidates reached that stage. "
               "The % is how many moved on from the stage before.")

    st.subheader(f"Candidates stuck more than {days} days")
    if not stuck["candidates"]:
        st.success("Nobody is stuck that long.")
    else:
        table = pd.DataFrame(stuck["candidates"])[["full_name", "job_title", "stage", "days_in_stage"]]
        table.columns = ["Candidate", "Job", "Stage", "Days in stage"]
        st.dataframe(table, hide_index=True, width="stretch", column_config={
            "Days in stage": st.column_config.NumberColumn(format="%.1f")})
    st.caption(f"Pulled live through the MCP server at {at}. Longest wait first.")


# --- Tab 3: How we know it's right -------------------------------------------------

def readme_sections() -> tuple[str, dict[str, str]]:
    text = re.sub(r"<!--.*?-->", "", README.read_text(), flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # repo links don't work in the app
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    intro = parts[0]
    sections = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}
    return intro, sections


@st.cache_data(ttl=3600, show_spinner=False)
def pytest_counts() -> tuple[int, int] | None:
    """(passed, total) from a quick pytest run, or None if it couldn't run."""
    try:
        out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                             cwd=ROOT, capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    summary = out.strip().splitlines()[-1] if out.strip() else ""
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|error)", summary)}
    if not counts:
        return None
    passed = counts.get("passed", 0)
    return passed, passed + counts.get("failed", 0) + counts.get("error", 0)


def latest_run() -> tuple[Path, dict] | None:
    runs = sorted(p for p in EVALS_OUT.glob("*") if p.is_dir() and (p / "meta.json").exists())
    if not runs:
        return None
    return runs[-1], json.loads((runs[-1] / "meta.json").read_text())


def load_scores(run_name: str) -> tuple[dict, str | None]:
    """Scores for this run, plus a note if the file belongs to another run."""
    if not SCORES_FILE.exists():
        return {}, None
    data = json.loads(SCORES_FILE.read_text())
    if data.get("run") != run_name:
        return {}, (f"The scores in tests/eval_scores.json are for run {data.get('run')}, "
                    f"not this one ({run_name}), so this run shows as not scored yet.")
    return data.get("scores", {}), None


BADGES = {"pass": "✅ Pass", "fail": "❌ Fail"}


def tab_trust() -> None:
    run_evals = load_module("run_evals", ROOT / "tests" / "run_evals.py")

    # Plain-English summary from README.md
    intro, sections = readme_sections()
    first_line = next((l for l in intro.splitlines() if l.strip() and not l.startswith("#")), "")
    st.markdown(f"#### {first_line}")
    s1, s2 = st.columns(2)
    with s1:
        st.markdown("**Design choices**")
        st.markdown(sections.get("Design choices", ""))
    with s2:
        st.markdown("**Testing and evals**")
        st.markdown(sections.get("Testing and evals", "").split("\n\n**Dates")[0])
    with st.expander("Read the full README"):
        st.markdown(re.sub(r"<!--.*?-->", "", README.read_text(), flags=re.S))

    # Headline numbers
    questions = run_evals.load_questions()
    run = latest_run()
    scores, scores_note = load_scores(run[0].name) if run else ({}, None)
    passed_evals = sum(1 for s in scores.values() if s.get("result") == "pass")
    tests = pytest_counts()

    m1, m2, m3 = st.columns(3)
    m1.metric("Automated tests passed",
              f"{tests[0]} of {tests[1]}" if tests else "Couldn't run")
    m2.metric("Mutation test: bugs caught", "5 of 6")
    m3.metric("Eval pass rate", f"{passed_evals}/{len(questions)}" if scores else "Not scored yet")
    st.caption("Test count comes from a live pytest run. Mutation test: 6 deliberate bugs were "
               "injected into server.py and 5 were caught; the 6th changed no output. "
               "Evals are scored manually.")

    # Eval table
    st.subheader("Eval questions")
    if not run:
        st.info("No eval run found. Run `python tests/run_evals.py` in a terminal "
                "(this page never runs evals itself).")
        return
    run_dir, meta = run
    run_time = datetime.strptime(meta["started_at"], "%Y-%m-%d %H:%M:%S")
    st.markdown(f"Latest run: **{run_time:%B %-d, %Y at %-I:%M %p}**, model `{meta.get('model')}`")
    if DB_PATH.exists():
        data_time = datetime.fromtimestamp(DB_PATH.stat().st_mtime)
        if data_time > run_time:
            st.warning(f"The data was rebuilt on {data_time:%B %-d at %-I:%M %p}, after this eval run. "
                       "Claude's answers and the expected answers may no longer match the data. "
                       "Re-run `python tests/run_evals.py` and re-score.")
    if scores_note:
        st.info(scores_note)

    rows, details = [], []
    for n, question, expected in questions:
        path = run_dir / f"q{n:02d}.jsonl"
        if path.exists():
            _, calls, answer = run_evals.summarize(path)
            tools = ", ".join(c for c in calls if not c.startswith("  ->")) or "(none)"
        else:
            tools, answer = "-", "(not in this run)"
        expected_line = re.search(r"\*\*Expected:\*\*(.+?)(?:\n\n|$)", expected, flags=re.S)
        score = scores.get(str(n), {})
        rows.append({
            "#": n,
            "Question": question,
            "Result": BADGES.get(score.get("result", "").lower(), "⏳ Not scored yet"),
            "Tool Claude called": tools,
            "Claude's answer": plain(answer),
            "Expected answer": plain(expected_line.group(1) if expected_line else expected),
            "Note": score.get("note", ""),
        })
        details.append((n, question, answer, expected))

    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"#": st.column_config.NumberColumn(width="small"),
                                "Claude's answer": st.column_config.TextColumn(width="large"),
                                "Expected answer": st.column_config.TextColumn(width="large")})

    st.markdown("**Full answers, side by side**")
    for n, question, answer, expected in details:
        with st.expander(f"Q{n}. {question}"):
            a, b = st.columns(2)
            a.markdown("**Claude's answer**")
            a.markdown(answer)
            b.markdown("**Expected**")
            b.markdown(expected)


# --- Tab 4: How it works -------------------------------------------------------------

LANES = [("User", "recruiter"), ("Streamlit app", "app.py"), ("Claude", "Messages API"),
         ("MCP server", "server.py"), ("SQLite", "read-only")]

# (from lane, to lane, arrow label, step title, what happens, design note)
FLOW_STEPS = [
    (0, 1, "Question", "User submits a question",
     "A natural-language question, e.g. “Which candidates have been stuck more than 10 days?”",
     "No query language or report builder needed."),
    (1, 3, "list_tools", "App connects to the MCP server",
     "app.py launches server.py over stdio with the MCP Python client and calls list_tools, "
     "which returns three tools with JSON schemas.",
     "The model can only call what the server exposes: three read-only analytics tools."),
    (1, 2, "Question + tools", "App calls the Messages API",
     "The question and the three tool schemas are sent to Claude through the Anthropic Messages API.",
     "The model receives tool descriptions only. No database access, no credentials."),
    (2, 1, "tool_use", "Claude selects a tool",
     "Claude replies with a tool_use block naming the tool and its arguments, e.g. "
     "stuck_candidates(days=10). It requests the call; it cannot execute it.",
     "The chosen tool and arguments are recorded in the Behind the scenes trace."),
    (1, 3, "call_tool", "App executes the call through MCP",
     "app.py forwards the request to the MCP session with call_tool. "
     "Every tool call takes this path.",
     "A single execution path is easy to audit, permission and log."),
    (3, 4, "Read-only SQL", "Server queries SQLite",
     "server.py runs a fixed, parameterized query against data/recruiting.db, "
     "opened with mode=ro.",
     "Writes are rejected at the connection level, and arguments are bound as "
     "parameters, never interpolated into SQL."),
    (4, 3, "Rows", "SQLite returns the matching rows",
     "The matching records come back to the server.",
     "Answers are grounded in records, not model recall."),
    (3, 1, "JSON results", "Server computes the metrics",
     "The server computes counts, conversion %, days in stage and medians, and returns compact "
     "JSON. An unknown job ID or team returns a tool error that lists the valid options.",
     "Metrics come from deterministic code, covered by 25 pytest tests that check each tool "
     "against independent SQL."),
    (1, 2, "tool_result", "App returns the results to Claude",
     "Results go back as tool_result blocks, flagged is_error on failure. Claude can request "
     "another tool, repeating steps 4 to 9, up to 6 rounds.",
     "The model reasons over returned values instead of calculating them."),
    (2, 1, "Answer", "Claude writes the answer",
     "Claude summarizes the results in plain English and notes caveats such as small samples.",
     "The language is generated. Every figure in it comes from a tool result."),
    (1, 0, "Answer + trace", "App shows the answer and its trace",
     "The answer is displayed with a step-by-step trace: tool chosen, inputs, rows returned, "
     "and the raw result.",
     "Every answer can be checked against the data that produced it."),
]

# Where each step shows up in the Behind the scenes panel on the first tab.
BEHIND_THE_SCENES = {1: 1, 4: 2, 7: 3, 8: 3, 10: 4}


def flow_svg(active: int) -> str:
    """Sequence diagram of one question. `active` is a step number, or 0 for all steps."""
    dark = text_color() != "#0b0b0b"
    ink, ink2 = ("#f0efec", "#c3c2b7") if dark else ("#0b0b0b", "#52514e")
    rule = "#4a4a46" if dark else "#c9c8c1"
    accent = "#3987e5" if dark else "#2a78d6"
    card = "#22232b" if dark else "#f4f3ef"
    page = "#0e1117" if dark else "#ffffff"  # Streamlit's page background, for text halos

    width, top, gap = 760, 100, 42
    xs = [88 + i * 146 for i in range(len(LANES))]
    height = top + gap * (len(FLOW_STEPS) - 1) + 24
    lit = set(FLOW_STEPS[active - 1][:2]) if active else set(range(len(LANES)))

    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" '
           f'role="img" aria-label="Request flow from the user through the app, Claude and the '
           f'MCP server to SQLite and back" style="font-family:sans-serif;max-width:960px">',
           "<defs>"]
    for name, color in (("on", accent), ("off", rule), ("all", ink2)):
        out.append(f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
                   f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
                   f'fill="{color}"/></marker>')
    out.append("</defs>")

    for i, (name, sub) in enumerate(LANES):
        x = xs[i]
        border = accent if (active and i in lit) else rule
        out.append(f'<line x1="{x}" y1="64" x2="{x}" y2="{height - 4}" stroke="{rule}" '
                   f'stroke-width="1" stroke-dasharray="3 4"/>')
        out.append(f'<rect x="{x - 64}" y="8" width="128" height="54" rx="8" fill="{card}" '
                   f'stroke="{border}" stroke-width="{2 if active and i in lit else 1}"/>')
        out.append(f'<text x="{x}" y="31" text-anchor="middle" font-size="15" font-weight="600" '
                   f'fill="{ink}">{name}</text>')
        out.append(f'<text x="{x}" y="50" text-anchor="middle" font-size="12" fill="{ink2}">{sub}</text>')

    for n, (src, dst, label, *_rest) in enumerate(FLOW_STEPS, start=1):
        y = top + (n - 1) * gap
        state = "all" if not active else ("on" if n == active else "off")
        color = {"on": accent, "off": rule, "all": ink2}[state]
        sign = 1 if dst > src else -1
        x1, x2 = xs[src] + 6 * sign, xs[dst] - 9 * sign
        out.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" '
                   f'stroke-width="{2.5 if state == "on" else 1.5}" marker-end="url(#arrow-{state})"/>')
        text_fill = ink if state != "off" else ink2
        opacity = "0.55" if state == "off" else "1"
        out.append(f'<text x="{(xs[src] + xs[dst]) / 2}" y="{y - 8}" text-anchor="middle" '
                   f'font-size="12.5" font-weight="{700 if state == "on" else 400}" fill="{text_fill}" '
                   f'opacity="{opacity}" stroke="{page}" stroke-width="4" paint-order="stroke">'
                   f'{n} · {label}</text>')
    out.append("</svg>")
    return "".join(out)


def tab_flow() -> None:
    total = len(FLOW_STEPS)
    st.session_state.setdefault("flow_step", 0)

    def move(delta: int) -> None:
        st.session_state.flow_step = min(max(st.session_state.flow_step + delta, 0), total)

    st.markdown("#### Request flow")
    st.caption("One request, end to end. Example: “Which candidates have been stuck more than 10 days?”")
    b1, b2, b3 = st.columns([1, 1, 5])
    b1.button("◀ Back", on_click=move, args=(-1,), disabled=st.session_state.flow_step == 0,
              width="stretch")
    b2.button("Next ▶", on_click=move, args=(1,), disabled=st.session_state.flow_step == total,
              width="stretch")
    b3.select_slider("Step", options=list(range(total + 1)), key="flow_step",
                     format_func=lambda n: "Overview" if n == 0 else f"Step {n}",
                     label_visibility="collapsed")
    step = st.session_state.flow_step

    with st.container(border=True):
        if step == 0:
            st.markdown("**Summary**")
            st.markdown(
                "- **Claude plans.** It chooses which tool to call and with what arguments.\n"
                "- **The MCP server executes.** Fixed, parameterized, read-only queries, plus all "
                "metric calculations.\n"
                "- **The app orchestrates.** It routes every tool call through the MCP session and "
                "records each step.")
            st.caption("The model never holds a database connection.")
        else:
            *_lanes, _label, title, what, note = FLOW_STEPS[step - 1]
            st.markdown(f"**{step}. {title}**")
            st.markdown(what)
            if step == 7:
                try:
                    _, stuck, _ = snapshot(10)
                    st.markdown(f"Live value: **{stuck['count']} candidates** currently match, "
                                "fetched through the MCP server.")
                except Exception as exc:
                    print(f"flow live count failed: {root_cause(exc)!r}", file=sys.stderr)
            st.markdown(f"**Design note:** {note}")
            if step in BEHIND_THE_SCENES:
                st.caption(f"Appears as step {BEHIND_THE_SCENES[step]} in the Behind the scenes "
                           "panel on the Ask a question tab.")

    # st.html drops inline SVG, so render it as markdown with HTML allowed.
    st.markdown(f'<div style="width:100%;margin:8px 0 16px">{flow_svg(step)}</div>',
                unsafe_allow_html=True)

    st.markdown("#### Design guarantees")
    g1, g2, g3 = st.columns(3)
    for col, head, body in (
        (g1, "No direct data access for the model",
         "Claude sees the question, the tool schemas and the tool results. "
         "It never holds a database connection."),
        (g2, "Deterministic metrics",
         "Counts, percentages and medians are computed in server.py and verified by 25 automated tests."),
        (g3, "Auditable answers",
         "Each answer shows the tool called, its inputs and the raw result."),
    ):
        with col.container(border=True):
            st.markdown(f"**{head}**")
            st.caption(body)


# --- Page -------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Recruiting Pipeline Assistant", page_icon="📊", layout="wide")
    st.title("Recruiting Pipeline Assistant (synthetic data)")
    if not DB_PATH.exists():
        st.error("The recruiting database is missing. Run `uv run python data/generate.py`, then refresh.")

    ask, snap, trust, flow = st.tabs(["Ask a question", "Pipeline snapshot",
                                      "How we know it's right", "How it works"])
    for tab, render in ((ask, tab_ask), (snap, tab_snapshot), (trust, tab_trust), (flow, tab_flow)):
        with tab:
            try:
                render()
            except Exception as exc:  # last-resort safety net, logged for the developer
                print(f"{render.__name__} failed: {root_cause(exc)!r}", file=sys.stderr)
                st.error("This tab hit a problem it couldn't recover from. Refresh the page to try again.")
            footer()


if __name__ == "__main__":  # `streamlit run app.py` runs the script as __main__
    main()
