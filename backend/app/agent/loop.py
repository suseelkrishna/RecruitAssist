"""The agent loop shared by the API, the CLI, and the evals.

One call to run_agent answers one question for one principal:
  1. Set the principal for this request and open an MCP client to app/mcp_server.py over
     the in-memory transport, so tools see the principal without it being an argument.
  2. List the tools, sorted by name, so the request prefix is identical every time.
  3. Call the model through the app/llm interface (Anthropic or OpenAI): tools, then the
     frozen system prompt, then one user turn holding the scope card, as_of, the selected
     job, recent history, and the question.
  4. Run the tool calls of each round concurrently and return every result in one round,
     with failures flagged as errors.
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

from mcp import Client

from app import access, llm, mcp_server
from app.access import Principal
from app.agent.prompt import SYSTEM_PROMPT
from app.agent.verify import ID_RE, verify
from app.llm import anthropic_client
from app.logic import scope

# Chosen by the evals: see evals/results.md for the scores and the rule used to pick it.
DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_EFFORT = "low"
MAX_ROUNDS = 6
MAX_HISTORY_PAIRS = 6
MAX_HISTORY_ANSWER_CHARS = 1500
MAX_HISTORY_CHARS = 6000
MAX_TOKENS = 16000

# The Anthropic request details (cache breakpoints, adaptive thinking, the refusal fallback beta)
# live in app/llm/anthropic_client.py; list prices live in app/llm/models.json.
FALLBACK_BETA = anthropic_client.FALLBACK_BETA

REFUSAL_TEXT = ("I can't help with that request. I can answer questions about the jobs, candidates, "
                "tasks, and sources in your scope.")
ROUND_LIMIT_TEXT = ("I could not finish this answer within the tool-call limit. Try a narrower question, "
                    "for example about one job.")


def model_name() -> str:
    """The model to use: ANTHROPIC_MODEL, or the default. Any ID in app/llm/models.json works."""
    return os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL


def effort_level() -> str:
    """The effort to use: ANTHROPIC_EFFORT, or the default."""
    return os.environ.get("ANTHROPIC_EFFORT") or DEFAULT_EFFORT


def make_client(model: str | None = None, purpose: str = "app") -> llm.LLMClient:
    """A client for the model's provider (default: model_name()). The SDKs retry 429 and 5xx
    themselves. For the app, an OpenAI model is refused unless ALLOW_OPENAI_LIVE=1."""
    return llm.make_client(model or model_name(), purpose)


async def run_agent(question: str, principal: Principal, job_id: str | None = None,
                    history: list[dict[str, Any]] | None = None, model: str | None = None,
                    client: Any = None, effort: str | None = None) -> dict[str, Any]:
    """Answer one question for one principal and return the full, verified result.

    model and effort default to ANTHROPIC_MODEL and ANTHROPIC_EFFORT. The evals pass both
    explicitly so several settings can run side by side in one process. client is an
    llm.LLMClient; a raw Anthropic SDK client is wrapped in the Anthropic adapter.
    """
    started = time.monotonic()
    model = model or model_name()
    effort = effort or effort_level()
    client = llm.as_client(client) if client is not None else make_client(model)
    run: dict[str, Any] = {"steps": [], "outputs": [], "usage": empty_usage(), "served_by": None}
    token = access.current_principal.set(principal)
    try:
        context = scope.scope_card(principal, job_id)
        async with Client(mcp_server.mcp) as session:
            tools = await tool_specs(session)
            messages = client.user_message(user_turn(question, context, job_id, history or []))
            answer, status = await converse(client, model, effort, tools, messages, session, run)
            report = verify(answer, run["outputs"], context, question)
            retried = False
            if status == "answered" and not report["passed"]:
                retried = True
                messages.extend(client.user_message(retry_note(report)))
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
        "provider": client.provider,
        "effort": effort,
        "served_by": run["served_by"],
        "retried": retried,
        "verifier": report,
        "as_of": context["as_of"],
        "job_id": job_id,
        "source": "live",
    }


async def tool_specs(session: Client) -> list[dict[str, Any]]:
    """The MCP tools as neutral tool definitions {name, description, input_schema}, sorted by name
    for a stable cache prefix. Each adapter converts them to its provider's shape."""
    listed = (await session.list_tools()).tools
    return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in sorted(listed, key=lambda t: t.name)]


def user_turn(question: str, context: dict[str, Any], job_id: str | None,
              history: list[dict[str, Any]]) -> str:
    """The one user message: scope card, as_of, selected job, recent history, then the question.

    History holds only earlier questions, answers, and the record IDs they cited (never raw
    tool results), at most MAX_HISTORY_PAIRS pairs, with long answers cut and the oldest
    pairs dropped until the history fits in MAX_HISTORY_CHARS.
    """
    parts = [
        "Scope card for this user (computed by the tools):",
        json.dumps(context, separators=(",", ":")),
        f"as_of: {context['as_of']}",
        f"Selected job: {job_id or 'none'}",
    ]
    recent = [history_text(pair) for pair in history[-MAX_HISTORY_PAIRS:]]
    while recent and sum(len(p) for p in recent) > MAX_HISTORY_CHARS:
        recent.pop(0)
    if recent:
        parts.append("Earlier in this conversation (oldest first). Numbers here are not evidence for "
                     "this turn; call the tools again:")
        parts += recent
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def history_text(pair: dict[str, Any]) -> str:
    """One earlier question and answer as text, with the record IDs the answer cited."""
    text = f"Q: {pair.get('question', '')}\nA: {pair.get('answer', '')[:MAX_HISTORY_ANSWER_CHARS]}"
    if pair.get("citations"):
        text += f"\nRecords cited: {', '.join(pair['citations'])}"
    return text


async def converse(client: llm.LLMClient, model: str, effort: str, tools: list[dict[str, Any]],
                   messages: list[dict[str, Any]], session: Client, run: dict[str, Any]) -> tuple[str, str]:
    """Call the model and run its tools until it answers or MAX_ROUNDS calls are used.

    Returns the answer text and a status: answered, truncated (max_tokens), refused, or
    round_limit. Every assistant turn is kept as the provider returned it, thinking blocks included.
    """
    for _ in range(MAX_ROUNDS):
        response = await client.create(model=model, system=SYSTEM_PROMPT, tools=tools, messages=messages,
                                       effort=effort, max_tokens=MAX_TOKENS)
        add_usage(run["usage"], response.usage)
        run["served_by"] = response.served_by
        messages.extend(response.messages)
        reason = response.stop_reason
        if reason == "tool_use":
            ran = await asyncio.gather(*(run_tool(session, call) for call in response.tool_calls))
            for _, output, step in ran:
                run["outputs"].append(output)
                run["steps"].append(step)
            messages.extend(client.tool_results_message([result for result, _, _ in ran]))
        elif reason == "pause_turn":
            continue
        elif reason == "refusal":
            return REFUSAL_TEXT, "refused"
        elif reason == "max_tokens":
            return response.text + "\n\n(This answer was cut off before it finished.)", "truncated"
        else:
            return response.text, "answered"
    return ROUND_LIMIT_TEXT, "round_limit"


async def run_tool(session: Client, call: llm.ToolCall) -> tuple[llm.ToolResult, dict[str, Any], dict[str, Any]]:
    """Run one tool call over MCP. Returns its ToolResult, its output for the verifier,
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
    block = llm.ToolResult(call.id, text, is_error)
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
    """Estimated US dollars for the run at the list prices in app/llm/models.json, or None if unpriced."""
    return llm.estimated_cost(model, usage)
