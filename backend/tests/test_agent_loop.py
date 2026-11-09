"""The agent loop with a scripted model: tool rounds, stop reasons, verifier retry, and the request shape.

Tools run for real over the in-memory MCP transport against the committed
database; only the model is faked.
"""

from __future__ import annotations

import pytest

from app import access
from app.agent import loop
from fake_model import FakeClient, reply, text, tool_use

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    """Run the async tests on asyncio."""
    return "asyncio"


def ask(script, user="USR-4", **kwargs):
    """Run the loop for one demo user with a scripted model. Returns the result and the fake client."""
    client = FakeClient(script)
    return loop.run_agent(kwargs.pop("question", "What jobs can I see?"), access.principal_for(user),
                          client=client, **kwargs), client


async def test_parallel_tool_calls_return_in_one_message_with_errors_flagged():
    run, client = ask([
        reply(tool_use("t1", "list_jobs"), tool_use("t2", "score_candidates", {"job_id": "JOB-2"}), stop="tool_use"),
        reply(text("You can see 3 jobs: JOB-1, JOB-5, and JOB-7.")),
    ])
    result = await run
    results = client.requests[1]["messages"][-1]
    assert results["role"] == "user"
    assert [r["tool_use_id"] for r in results["content"]] == ["t1", "t2"]
    assert [r["is_error"] for r in results["content"]] == [False, True]
    assert "JOB-2 is not in your scope" in results["content"][1]["content"]
    assert [(s["tool"], s["rows"], s["is_error"]) for s in result["steps"]] == [
        ("list_jobs", 3, False), ("score_candidates", 0, True)]
    assert result["verified"] and result["label"] == "verified"
    assert result["citations"] == ["JOB-1", "JOB-5", "JOB-7"]


async def test_usage_cache_hits_and_cost_are_summed():
    run, _ = ask([reply(tool_use("t1", "list_jobs"), stop="tool_use"),
                  reply(text("You can see 3 jobs."), cache_read=800)], model="claude-opus-5-5")
    result = await run
    assert result["usage"] == {"api_calls": 2, "input_tokens": 2000, "output_tokens": 400,
                               "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 800,
                               "cache_hits": 1}
    # 2000 * 4 + 400 * 20 + 1000 * 5 + 800 * 0.2 dollars per million tokens.
    assert result["estimated_cost_usd"] == pytest.approx(0.02116)
    assert result["source"] == "live" and result["served_by"] == "fake-model"


async def test_failed_check_retries_once_with_the_failures_listed():
    run, client = ask([reply(tool_use("t1", "list_jobs"), stop="tool_use"),
                       reply(text("You can see 9999 jobs.")),
                       reply(text("You can see 3 jobs."))])
    result = await run
    note = client.requests[2]["messages"][-1]["content"]
    assert "do not appear in the tool results: 9999" in note
    assert result["retried"] and result["verified"]
    assert result["answer"] == "You can see 3 jobs."


async def test_second_failure_is_marked_unverified():
    run, _ = ask([reply(tool_use("t1", "list_jobs"), stop="tool_use"),
                  reply(text("You can see 3 jobs [JOB-9].")),
                  reply(text("You can see 3 jobs [JOB-9]."))])
    result = await run
    assert result["retried"] and not result["verified"]
    assert result["label"] == "unverified"
    assert result["verifier"]["checks"]["citations"]["unknown"] == ["JOB-9"]


async def test_pause_turn_continues_without_a_new_user_message():
    run, client = ask([reply(text("Working."), stop="pause_turn"), reply(text("No numbers here."))])
    result = await run
    assert client.requests[1]["messages"][-1]["role"] == "assistant"
    assert result["status"] == "answered"


async def test_refusal_returns_a_plain_message():
    result = await ask([reply(stop="refusal")])[0]
    assert result["status"] == "refused" and not result["verified"]
    assert result["answer"] == loop.REFUSAL_TEXT


async def test_max_tokens_is_marked_truncated():
    result = await ask([reply(text("Partial answer"), stop="max_tokens")])[0]
    assert result["status"] == "truncated" and "cut off" in result["answer"]
    assert not result["verified"]


async def test_round_limit_stops_after_six_calls():
    run, client = ask(lambda params: reply(tool_use(f"t{len(params['messages'])}", "list_jobs"), stop="tool_use"))
    result = await run
    assert len(client.requests) == loop.MAX_ROUNDS
    assert result["status"] == "round_limit" and not result["verified"]


async def test_request_shape_caching_thinking_and_no_sampling():
    run, client = ask([reply(text("Nothing to count."))], user="USR-1", job_id="JOB-2",
                      history=[{"question": f"q{i}", "answer": f"a{i}"} for i in range(8)],
                      model="claude-opus-5-5")
    await run
    params = client.requests[0]
    assert [t["name"] for t in params["tools"]] == sorted(t["name"] for t in params["tools"])
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["system"][0]["text"] == loop.SYSTEM_PROMPT
    assert params["thinking"] == {"type": "adaptive"}
    assert params["output_config"]["effort"] in ("low", "medium", "high", "xhigh", "max")
    assert params["tool_choice"] == {"type": "auto"}
    assert params["fallbacks"] == "default" and params["betas"] == [loop.FALLBACK_BETA]
    assert not {"temperature", "top_p", "top_k"} & set(params)
    turn = params["messages"][0]["content"]
    assert "Selected job: JOB-2" in turn and '"job_id":"JOB-2"' in turn
    assert "q1\n" not in turn and "Q: q2\n" in turn and "Q: q7\n" in turn   # last 6 pairs only
    assert turn.endswith("Question: What jobs can I see?")


async def test_effort_argument_is_sent_on_every_round_and_reported(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EFFORT", "high")
    run, client = ask([reply(tool_use("t1", "list_jobs"), stop="tool_use"), reply(text("Done."))],
                      effort="low")
    result = await run
    assert [r["output_config"]["effort"] for r in client.requests] == ["low", "low"]
    assert result["effort"] == "low"


async def test_effort_defaults_to_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_EFFORT", "high")
    run, client = ask([reply(text("Done."))])
    result = await run
    assert client.requests[0]["output_config"]["effort"] == "high" and result["effort"] == "high"


async def test_no_fallback_for_models_without_it():
    run, client = ask([reply(text("Fine."))], model="claude-haiku-5-5")
    await run
    assert "fallbacks" not in client.requests[0] and "betas" not in client.requests[0]


async def test_out_of_scope_job_fails_before_any_model_call():
    run, client = ask([], job_id="JOB-2")
    with pytest.raises(Exception, match="JOB-2 is not in your scope"):
        await run
    assert client.requests == []
