"""The LLM interface: both adapters with mocked SDK responses, the model table, and the live guards.

No test calls a real API. The Anthropic adapter is also covered end to end by
test_agent_loop.py, whose request-shape assertions are unchanged from before the
interface existed.
"""

from __future__ import annotations

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app import access, checks, llm, main
from app.agent import loop
from app.llm.anthropic_client import AnthropicClient
from app.llm.openai_client import OpenAIClient
from fake_model import FakeClient, reply, text, tool_use
from fake_openai import FakeOpenAI, call, message, reasoning, response

TOOLS = [{"name": "list_jobs", "description": "List jobs.", "input_schema": {"type": "object", "properties": {}}}]


@pytest.fixture
def anyio_backend():
    """Run the async tests on asyncio."""
    return "asyncio"


async def openai_create(script, **kwargs):
    """One OpenAI adapter call against a scripted SDK. Returns the response and the fake SDK."""
    sdk = FakeOpenAI(script)
    params = {"model": "gpt-6-luna", "system": "SYS", "tools": TOOLS,
              "messages": [{"role": "user", "content": "hi"}], "effort": "low", "max_tokens": 16000}
    response = await OpenAIClient(sdk).create(**{**params, **kwargs})
    return response, sdk


# OpenAI adapter

@pytest.mark.anyio
async def test_openai_request_mirrors_the_anthropic_settings():
    _, sdk = await openai_create([response(message("ok"))])
    params = sdk.requests[0]
    assert params["instructions"] == "SYS" and params["input"] == [{"role": "user", "content": "hi"}]
    assert params["tools"] == [{"type": "function", "name": "list_jobs", "description": "List jobs.",
                                "parameters": {"type": "object", "properties": {}}, "strict": False}]
    assert params["tool_choice"] == "auto"
    assert params["reasoning"] == {"effort": "low"} and params["max_output_tokens"] == 16000
    assert params["store"] is False and params["include"] == ["reasoning.encrypted_content"]
    assert not {"temperature", "top_p", "seed"} & set(params)


@pytest.mark.anyio
async def test_openai_tool_calls_are_parsed_and_reasoning_is_kept_for_the_next_round():
    reply_ = response(reasoning("secret"), call("c1", "list_jobs"), call("c2", "score_candidates", {"job_id": "JOB-1"}))
    result, _ = await openai_create([reply_])
    assert result.stop_reason == "tool_use"
    assert [(c.id, c.name, c.input) for c in result.tool_calls] == [
        ("c1", "list_jobs", {}), ("c2", "score_candidates", {"job_id": "JOB-1"})]
    assert [m["type"] for m in result.messages] == ["reasoning", "function_call", "function_call"]
    assert result.messages[0]["encrypted_content"] == "secret"
    assert result.messages[2]["arguments"] == '{"job_id": "JOB-1"}' and result.messages[2]["call_id"] == "c2"


@pytest.mark.anyio
async def test_openai_invalid_tool_arguments_reach_the_tool_as_a_visible_error():
    result, _ = await openai_create([response(call("c1", "list_jobs", raw="{not json"))])
    assert result.tool_calls[0].input == {"invalid_json_arguments": "{not json"}


@pytest.mark.anyio
@pytest.mark.parametrize("reply_, expected", [
    (response(message("done")), "end_turn"),
    (response(message("partial"), incomplete="max_output_tokens"), "max_tokens"),
    (response(incomplete="content_filter"), "refusal"),
    (response(message(refusal="I can't help with that.")), "refusal"),
    (response(message("x"), call("c1", "list_jobs")), "tool_use"),
])
async def test_openai_stop_reasons_are_normalized(reply_, expected):
    result, _ = await openai_create([reply_])
    assert result.stop_reason == expected


@pytest.mark.anyio
async def test_openai_usage_takes_cached_tokens_out_of_input():
    result, _ = await openai_create([response(message("ok"), prompt=1500, cached=1024, output=300,
                                              reasoning_tokens=120)])
    u = result.usage
    assert (u.input_tokens, u.cache_read_input_tokens, u.cache_creation_input_tokens) == (476, 1024, 0)
    assert u.output_tokens == 300 and u.reasoning_tokens == 120
    assert result.served_by == "fake-gpt" and result.text == "ok"


def test_openai_tool_results_are_one_output_item_each_with_errors_marked():
    client = OpenAIClient(FakeOpenAI([]))
    items = client.tool_results_message([llm.ToolResult("c1", '{"count": 3}'),
                                         llm.ToolResult("c2", "JOB-2 is not in your scope.", is_error=True)])
    assert items == [{"type": "function_call_output", "call_id": "c1", "output": '{"count": 3}'},
                     {"type": "function_call_output", "call_id": "c2", "output": "Error: JOB-2 is not in your scope."}]
    assert client.user_message("q") == [{"role": "user", "content": "q"}]


@pytest.mark.anyio
async def test_openai_errors_are_wrapped_with_fatal_set():
    import openai
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    bad_key = openai.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)
    with pytest.raises(llm.LLMAPIError) as fatal:
        await openai_create([bad_key])
    assert fatal.value.fatal and fatal.value.provider == "openai" and fatal.value.kind == "AuthenticationError"
    with pytest.raises(llm.LLMAPIError) as transient:
        await openai_create([openai.APIConnectionError(request=request)])
    assert not transient.value.fatal


@pytest.mark.anyio
async def test_openai_complete_sends_no_tools():
    sdk = FakeOpenAI([response(message('{"faithfulness": 5, "clarity": 4}'))])
    result = await OpenAIClient(sdk).complete(model="gpt-6-luna", system="RUBRIC", prompt="grade this",
                                              effort="low", max_tokens=4000)
    assert result.text.startswith("{") and "tools" not in sdk.requests[0]


@pytest.mark.anyio
async def test_agent_loop_runs_end_to_end_on_the_openai_adapter():
    """The same loop, tools, and verifier with OpenAI-shaped replies."""
    sdk = FakeOpenAI([response(reasoning(), call("c1", "list_jobs"), call("c2", "score_candidates", {"job_id": "JOB-2"})),
                      response(message("You can see 3 jobs: JOB-1, JOB-5, and JOB-7."), cached=1024)])
    result = await loop.run_agent("What jobs can I see?", access.principal_for("USR-4"),
                                  model="gpt-6-luna", client=OpenAIClient(sdk))
    second = sdk.requests[1]["input"]
    assert [m.get("type", m.get("role")) for m in second] == [
        "user", "reasoning", "function_call", "function_call", "function_call_output", "function_call_output"]
    assert second[5]["output"].startswith("Error") and "JOB-2 is not in your scope" in second[5]["output"]
    assert sdk.requests[1]["instructions"] == loop.SYSTEM_PROMPT
    assert result["verified"] and result["provider"] == "openai" and result["served_by"] == "fake-gpt"
    assert result["citations"] == ["JOB-1", "JOB-5", "JOB-7"]
    assert result["usage"]["cache_hits"] == 1 and result["usage"]["cache_read_input_tokens"] == 1024
    # gpt-6-luna at 0.10 in, 0.50 out, 0.01 cache read: (1500 + 476) * 0.10 + 600 * 0.50 + 1024 * 0.01
    # = 507.84 dollars per million tokens, rounded to six places.
    assert result["estimated_cost_usd"] == 0.000508


# Anthropic adapter

@pytest.mark.anyio
async def test_anthropic_adapter_normalizes_a_messages_response():
    sdk = FakeClient([reply(text("Looking."), tool_use("t1", "list_jobs"), stop="tool_use", cache_read=800)])
    response = await AnthropicClient(sdk).create(model="claude-haiku-5-5", system="SYS", tools=TOOLS,
                                                 messages=[{"role": "user", "content": "hi"}],
                                                 effort="low", max_tokens=16000)
    assert response.stop_reason == "tool_use" and response.text == "Looking."
    assert [(c.id, c.name, c.input) for c in response.tool_calls] == [("t1", "list_jobs", {})]
    assert (response.usage.input_tokens, response.usage.cache_read_input_tokens) == (1000, 800)
    assert response.messages[0]["role"] == "assistant" and len(response.messages[0]["content"]) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("stop, expected", [("end_turn", "end_turn"), ("stop_sequence", "end_turn"),
                                            ("max_tokens", "max_tokens"), ("refusal", "refusal"),
                                            ("pause_turn", "pause_turn")])
async def test_anthropic_stop_reasons_are_normalized(stop, expected):
    response = await AnthropicClient(FakeClient([reply(text("x"), stop=stop)])).create(
        model="claude-haiku-5-5", system="S", tools=[], messages=[], effort="low", max_tokens=10)
    assert response.stop_reason == expected


def test_anthropic_tool_results_are_one_user_message():
    message = AnthropicClient(FakeClient([])).tool_results_message(
        [llm.ToolResult("t1", "ok"), llm.ToolResult("t2", "no", is_error=True)])
    assert message == [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False},
        {"type": "tool_result", "tool_use_id": "t2", "content": "no", "is_error": True}]}]


@pytest.mark.anyio
async def test_anthropic_errors_are_wrapped_with_fatal_set():
    import anthropic
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def raises(error):
        def create(params):
            raise error
        return FakeClient(create)

    bad = anthropic.BadRequestError("credit balance is too low", response=httpx.Response(400, request=request),
                                    body=None)
    with pytest.raises(llm.LLMAPIError) as fatal:
        await AnthropicClient(raises(bad)).create(model="claude-haiku-5-5", system="S", tools=[], messages=[],
                                                  effort="low", max_tokens=10)
    assert fatal.value.fatal and "credit balance" in str(fatal.value)
    with pytest.raises(llm.LLMAPIError) as transient:
        await AnthropicClient(raises(anthropic.APIConnectionError(request=request))).create(
            model="claude-haiku-5-5", system="S", tools=[], messages=[], effort="low", max_tokens=10)
    assert not transient.value.fatal


# Model table and guards

def test_models_resolve_to_a_provider_by_table_or_prefix():
    assert llm.provider_for("claude-haiku-5-5") == "anthropic"
    assert llm.provider_for("gpt-6.1-sol") == "openai"
    assert llm.provider_for("claude-future-9") == "anthropic" and llm.provider_for("o5-mini") == "openai"
    with pytest.raises(ValueError, match="models.yaml"):
        llm.provider_for("llama-4")
    assert llm.api_key_env("gpt-6-luna") == "OPENAI_API_KEY"


def test_every_model_is_priced_and_openai_is_eval_only():
    for model, entry in llm.models().items():
        assert set(entry["prices"]) == {"input", "output", "cache_write", "cache_read"}, model
        assert isinstance(entry["confirm"], bool) and entry["price_source"], model
        if entry["provider"] == "openai":
            assert entry["production"] is False and entry["confirm"] is True, model
        if not entry["eval"]:
            assert entry.get("skip_reason"), model
    assert "gpt-6-astra" in llm.skipped_models() and "gpt-6-astra" not in llm.eval_models()
    assert loop.DEFAULT_MODEL in llm.eval_models() and llm.is_production(loop.DEFAULT_MODEL)


def test_claude_cost_uses_the_anthropic_list_prices():
    usage = {"input_tokens": 2000, "output_tokens": 400, "cache_creation_input_tokens": 1000,
             "cache_read_input_tokens": 800}
    assert llm.estimated_cost("claude-opus-5-5", usage) == pytest.approx(0.02116)
    assert llm.estimated_cost("unpriced-model", usage) is None


def test_openai_is_refused_for_the_app_unless_allowed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ALLOW_OPENAI_LIVE", raising=False)
    with pytest.raises(llm.OpenAINotAllowed):
        llm.make_client("gpt-6-luna")
    assert llm.make_client("gpt-6-luna", "eval").provider == "openai"
    monkeypatch.setenv("ALLOW_OPENAI_LIVE", "1")
    assert llm.make_client("gpt-6-luna").provider == "openai"
    assert llm.make_client("claude-haiku-5-5").provider == "anthropic"


def test_app_keeps_answering_from_recordings_when_an_openai_model_is_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ALLOW_OPENAI_LIVE", raising=False)
    assert main.model_client() is None
    checks._model_check.clear()
    assert checks.model_check()["error"] == "EvalOnlyModel"
    checks._model_check.clear()


def test_app_uses_the_anthropic_default_without_any_model_setting(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    client = main.model_client()
    assert client.provider == "anthropic" and loop.model_name() == "claude-haiku-5-5"


def test_daily_live_cap_applies_to_an_openai_client(monkeypatch):
    """The cap is checked before the agent runs, whatever the provider, so OpenAI answers count too."""
    monkeypatch.setenv("DAILY_LIVE_CAP", "2")
    sdk = FakeOpenAI(lambda params: response(call("c1", "list_jobs")) if params["input"][-1].get("role") == "user"
                     else response(message("You can see 3 jobs.")))
    main.app.dependency_overrides[main.model_client] = lambda: OpenAIClient(sdk)
    try:
        api = TestClient(main.app, raise_server_exceptions=False)
        codes = [api.post("/api/ask", headers={"X-Demo-User": "USR-4", "X-Forwarded-For": f"192.0.2.{i}"},
                          json={"question": "Which tasks are overdue?"}).status_code for i in range(3)]
    finally:
        main.app.dependency_overrides.clear()
    assert codes == [200, 200, 429]
    assert len(sdk.requests) == 4   # two answers of two rounds each; the third request never reached the model


@pytest.mark.anyio
async def test_openai_out_of_credit_429_is_fatal_but_a_plain_rate_limit_is_not():
    import openai
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    no_credit = openai.RateLimitError("You have no credits remaining.", response=httpx.Response(429, request=request),
                                      body={"code": "credit_balance_exhausted", "message": "no credits"})
    with pytest.raises(llm.LLMAPIError) as fatal:
        await openai_create([no_credit])
    assert fatal.value.fatal and fatal.value.kind == "RateLimitError"
    busy = openai.RateLimitError("Rate limit reached.", response=httpx.Response(429, request=request),
                                 body={"code": "rate_limit_exceeded", "message": "slow down"})
    with pytest.raises(llm.LLMAPIError) as transient:
        await openai_create([busy])
    assert not transient.value.fatal

