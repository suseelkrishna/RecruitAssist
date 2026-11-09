"""The agent loop shared by the API, the CLI, and the evals.

One call to run_agent answers one question for one principal:
  1. Set the principal for this request and open an MCP client to app/mcp_server.py over
     the in-memory transport, so tools see the principal without it being an argument.
  2. List the tools, sorted by name, so the request prefix is identical every time.
  3. Call the Messages API: tools, then the frozen system prompt with a cache breakpoint,
     then one user turn holding the scope card, as_of, the selected job, recent history,
     and the question.
  4. Run the tool calls of each round concurrently and return every result in one user
     message, with is_error set on failures.
  5. Stop after MAX_ROUNDS API calls, handling every stop_reason.
  6. Verify the answer. On failure, retry once with the failures listed; if it fails
     again, the answer is marked unverified.
  7. Return the answer with citations, tool steps, token usage, cache hits, latency,
     estimated cost, and the verifier report.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import anthropic
from mcp import Client

from app import access, mcp_server
from app.access import Principal
from app.agent.prompt import SYSTEM_PROMPT
from app.agent.verify import ID_RE, verify
from app.logic import scope

# Chosen by the evals: see evals/results.md for the scores and the rule used to pick it.
DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"
MAX_ROUNDS = 6
MAX_HISTORY_PAIRS = 6
MAX_HISTORY_ANSWER_CHARS = 1500
MAX_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 120
MAX_RETRIES = 3

# Models that accept the server-side refusal fallback ("default" picks the substitute by category).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# US dollars per million tokens: input, output, cache write (5 minutes), cache read.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}

REFUSAL_TEXT = ("I can't help with that request. I can answer questions about the jobs, candidates, "
                "tasks, and sources in your scope.")
ROUND_LIMIT_TEXT = ("I could not finish this answer within the tool-call limit. Try a narrower question, "
                    "for example about one job.")


def model_name() -> str:
    """The model to use: ANTHROPIC_MODEL, or the default."""
    return os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL


def effort_level() -> str:
    """The effort to use: ANTHROPIC_EFFORT, or the default."""
    return os.environ.get("ANTHROPIC_EFFORT") or DEFAULT_EFFORT


def make_client() -> anthropic.AsyncAnthropic:
    """An async Messages API client with a request timeout. The SDK retries 429 and 5xx itself."""
    return anthropic.AsyncAnthropic(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES)


async def run_agent(question: str, principal: Principal, job_id: str | None = None,
                    history: list[dict[str, str]] | None = None, model: str | None = None,
                    client: Any = None, effort: str | None = None) -> dict[str, Any]:
    """Answer one question for one principal and return the full, verified result.

    model and effort default to ANTHROPIC_MODEL and ANTHROPIC_EFFORT. The evals pass both
    explicitly so several settings can run side by side in one process.
    """
    started = time.monotonic()
    model = model or model_name()
    effort = effort or effort_level()
    client = client or make_client()
    run: dict[str, Any] = {"steps": [], "outputs": [], "usage": empty_usage(), "served_by": None}
    token = access.current_principal.set(principal)
    try:
        context = scope.scope_card(principal, job_id)
        async with Client(mcp_server.mcp) as session:
            tools = await tool_specs(session)
            messages: list[dict[str, Any]] = [
                {"role": "user", "content": user_turn(question, context, job_id, history or [])}]
            answer, status = await converse(client, model, effort, tools, messages, session, run)
            report = verify(answer, run["outputs"], context, question)
            retried = False
            if status == "answered" and not report["passed"]:
                retried = True
                messages.append({"role": "user", "content": retry_note(report)})
                answer, status = await converse(client, model, effort, tools, messages, session, run)
                report = verify(answer, run["outputs"], context, question)
    finally:
        access.current_principal.reset(token)
    verified = status == "answered" and report["passed"]
    return {
        "answer": answer,
        "status": status,
        "verified": verified,
        "label": "verified" if verified else "unverified",
        "citations": sorted(set(ID_RE.findall(answer))),
        "steps": run["steps"],
        "usage": run["usage"],
        "latency_ms": round((time.monotonic() - started) * 1000),
        "estimated_cost_usd": estimated_cost(model, run["usage"]),
        "model": model,
        "effort": effort,
        "served_by": run["served_by"],
        "retried": retried,
        "verifier": report,
        "as_of": context["as_of"],
        "job_id": job_id,
        "source": "live",
    }


async def tool_specs(session: Client) -> list[dict[str, Any]]:
    """The MCP tools as Messages API tool definitions, sorted by name for a stable cache prefix."""
    listed = (await session.list_tools()).tools
    return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in sorted(listed, key=lambda t: t.name)]


def user_turn(question: str, context: dict[str, Any], job_id: str | None,
              history: list[dict[str, str]]) -> str:
    """The one user message: scope card, as_of, selected job, recent history, then the question.

    History holds only earlier questions and answers (never raw tool results), at most
    MAX_HISTORY_PAIRS pairs, with long answers cut.
    """
    parts = [
        "Scope card for this user (computed by the tools):",
        json.dumps(context, separators=(",", ":")),
        f"as_of: {context['as_of']}",
        f"Selected job: {job_id or 'none'}",
    ]
    recent = history[-MAX_HISTORY_PAIRS:]
    if recent:
        parts.append("Earlier in this conversation (oldest first). Numbers here are not evidence for "
                     "this turn; call the tools again:")
        for pair in recent:
            parts.append(f"Q: {pair.get('question', '')}\nA: {pair.get('answer', '')[:MAX_HISTORY_ANSWER_CHARS]}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def request(model: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]],
            effort: str = DEFAULT_EFFORT) -> dict[str, Any]:
    """The Messages API arguments for one round.

    The cache breakpoint after the system prompt caches tools and system; the top-level
    cache_control also caches the growing conversation between rounds. Adaptive thinking
    with an explicit effort; no sampling parameters; tool_choice stays auto.
    """
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "tools": tools,
        "tool_choice": {"type": "auto"},
        "messages": messages,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
        "cache_control": {"type": "ephemeral"},
    }
    if model in FALLBACK_MODELS:
        params["betas"] = [FALLBACK_BETA]
        params["fallbacks"] = "default"
    return params


async def converse(client: Any, model: str, effort: str, tools: list[dict[str, Any]],
                   messages: list[dict[str, Any]], session: Client, run: dict[str, Any]) -> tuple[str, str]:
    """Call the model and run its tools until it answers or MAX_ROUNDS calls are used.

    Returns the answer text and a status: answered, truncated (max_tokens), refused, or
    round_limit. Every assistant turn is kept unchanged, thinking blocks included.
    """
    for _ in range(MAX_ROUNDS):
        response = await client.beta.messages.create(**request(model, tools, messages, effort))
        add_usage(run["usage"], response.usage)
        run["served_by"] = getattr(response, "model", model)
        messages.append({"role": "assistant", "content": response.content})
        reason = response.stop_reason
        if reason == "tool_use":
            calls = [b for b in response.content if b.type == "tool_use"]
            ran = await asyncio.gather(*(run_tool(session, call) for call in calls))
            for _, output, step in ran:
                run["outputs"].append(output)
                run["steps"].append(step)
            messages.append({"role": "user", "content": [block for block, _, _ in ran]})
        elif reason == "pause_turn":
            continue
        elif reason == "refusal":
            return REFUSAL_TEXT, "refused"
        elif reason == "max_tokens":
            return text_of(response) + "\n\n(This answer was cut off before it finished.)", "truncated"
        else:
            return text_of(response), "answered"
    return ROUND_LIMIT_TEXT, "round_limit"


async def run_tool(session: Client, call: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run one tool call over MCP. Returns its tool_result block, its output for the verifier,
    and the step record (tool, input, rows, is_error, ms)."""
    started = time.monotonic()
    try:
        result = await session.call_tool(call.name, call.input)
        text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        is_error = bool(result.is_error)
    except Exception as error:  # A failed call goes back to the model as an error result.
        text, is_error = f"The tool call failed: {error}", True
    output: Any = text
    if not is_error:
        try:
            output = json.loads(text)
        except ValueError:
            pass
    block = {"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": is_error}
    record = {"name": call.name, "input": call.input, "output": output, "is_error": is_error}
    step = {"tool": call.name, "input": call.input, "rows": 0 if is_error else row_count(output),
            "is_error": is_error, "ms": round((time.monotonic() - started) * 1000)}
    return block, record, step


def row_count(output: Any) -> int:
    """How many records a tool returned: its count field, else the items in its top-level lists."""
    if not isinstance(output, dict):
        return 1
    if isinstance(output.get("count"), int):
        return output["count"]
    lists = [v for v in output.values() if isinstance(v, list)]
    return sum(len(v) for v in lists) if lists else 1


def text_of(response: Any) -> str:
    """The text blocks of a response joined together."""
    return "".join(b.text for b in response.content if b.type == "text").strip()


def retry_note(report: dict[str, Any]) -> str:
    """The follow-up message that asks for a corrected answer, listing what the verifier found."""
    lines = "\n".join(f"- {f}" for f in report["failures"])
    return ("A check of your answer against this turn's tool results failed:\n"
            f"{lines}\n"
            "Rewrite the full answer so every number, date, and ID comes from a tool result, any "
            "ranking follows score_candidates exactly, and no contact details appear. Call tools "
            "again if you need to.")


def empty_usage() -> dict[str, int]:
    """Token counters summed over every API call in one run."""
    return {"api_calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0, "cache_hits": 0}


def add_usage(total: dict[str, int], usage: Any) -> None:
    """Add one response's usage to the running totals. A call that read from the cache is a cache hit."""
    total["api_calls"] += 1
    for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        total[key] += getattr(usage, key, 0) or 0
    if (getattr(usage, "cache_read_input_tokens", 0) or 0) > 0:
        total["cache_hits"] += 1


def estimated_cost(model: str, usage: dict[str, int]) -> float | None:
    """Estimated US dollars for the run at list prices for the requested model, or None if unpriced."""
    prices = PRICES.get(model)
    if prices is None:
        return None
    tokens = (usage["input_tokens"], usage["output_tokens"],
              usage["cache_creation_input_tokens"], usage["cache_read_input_tokens"])
    return round(sum(n * p for n, p in zip(tokens, prices)) / 1_000_000, 6)
