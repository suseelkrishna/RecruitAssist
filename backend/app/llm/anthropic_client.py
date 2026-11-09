"""The Anthropic adapter: the Messages API behind the LLMClient interface.

Each request sends the tools, then the frozen system prompt with a cache breakpoint,
a top-level cache_control that also caches the growing conversation between rounds,
adaptive thinking with an explicit effort, tool_choice auto, and no sampling
parameters. tests/test_agent_loop.py pins this shape.
"""

from __future__ import annotations

from typing import Any

import anthropic

from app.llm.base import LLMAPIError, LLMResponse, ToolCall, ToolResult, Usage

REQUEST_TIMEOUT_SECONDS = 120
MAX_RETRIES = 3

# Models that accept the server-side refusal fallback ("default" picks the substitute by category).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Errors that retrying cannot fix, such as an exhausted credit balance or a bad key.
FATAL_ERRORS = (anthropic.BadRequestError, anthropic.AuthenticationError, anthropic.PermissionDeniedError)


def request(model: str, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]],
            effort: str, max_tokens: int) -> dict[str, Any]:
    """The Messages API arguments for one round."""
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
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


def usage_of(usage: Any) -> Usage:
    """The neutral token counts. Anthropic already reports input_tokens without cached tokens."""
    return Usage(input_tokens=getattr(usage, "input_tokens", 0) or 0,
                 output_tokens=getattr(usage, "output_tokens", 0) or 0,
                 cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                 cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0)


def normalize(response: Any, model: str) -> LLMResponse:
    """An LLMResponse from a Messages API response. The assistant turn keeps every block unchanged."""
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    calls = [ToolCall(b.id, b.name, b.input) for b in response.content if b.type == "tool_use"]
    reason = response.stop_reason if response.stop_reason in ("tool_use", "max_tokens", "refusal",
                                                               "pause_turn") else "end_turn"
    return LLMResponse(text=text, tool_calls=calls, stop_reason=reason, usage=usage_of(response.usage),
                       served_by=getattr(response, "model", model),
                       messages=[{"role": "assistant", "content": response.content}])


def wrap_error(error: anthropic.APIError) -> LLMAPIError:
    """The neutral error for an SDK error."""
    return LLMAPIError("anthropic", type(error).__name__, str(error), isinstance(error, FATAL_ERRORS))


class AnthropicClient:
    """LLMClient over an AsyncAnthropic client (or any object with the same create methods)."""

    provider = "anthropic"

    def __init__(self, sdk: Any = None):
        self.sdk = sdk or anthropic.AsyncAnthropic(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES)

    async def create(self, *, model: str, system: str, tools: list[dict[str, Any]],
                     messages: list[dict[str, Any]], effort: str, max_tokens: int) -> LLMResponse:
        try:
            response = await self.sdk.beta.messages.create(
                **request(model, system, tools, messages, effort, max_tokens))
        except anthropic.APIError as error:
            raise wrap_error(error) from error
        return normalize(response, model)

    def user_message(self, text: str) -> list[dict[str, Any]]:
        return [{"role": "user", "content": text}]

    def tool_results_message(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        return [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": r.is_error}
            for r in results]}]

    async def complete(self, *, model: str, system: str, prompt: str, effort: str,
                       max_tokens: int) -> LLMResponse:
        try:
            response = await self.sdk.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"}, output_config={"effort": effort})
        except anthropic.APIError as error:
            raise wrap_error(error) from error
        return normalize(response, model)


def lookup_model(model: str, timeout: float) -> str:
    """The model ID the Models API reports for model. Raises LLMAPIError on failure."""
    try:
        return anthropic.Anthropic(timeout=timeout, max_retries=0).models.retrieve(model).id
    except anthropic.APIError as error:
        raise wrap_error(error) from error
