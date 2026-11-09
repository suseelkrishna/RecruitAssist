"""The OpenAI adapter: the Responses API behind the LLMClient interface. Used for eval runs only.

It mirrors the Anthropic request as closely as the API allows: the same system
prompt (as instructions), the same tools, tool_choice auto, the same effort (as
reasoning.effort), the same output token limit, and no sampling parameters. The
Responses API is used because newer OpenAI models do not accept function tools
together with a reasoning effort on Chat Completions.

Nothing is stored at OpenAI (store false). Reasoning items come back encrypted
and are sent back unchanged on the next model call, the same way the Anthropic
adapter keeps thinking blocks. prompt_cache_key keeps the agent's requests on
the same prompt cache.

Normalization:
- any function_call item is tool_use; status incomplete for max_output_tokens is
  max_tokens; incomplete for content_filter, or a refusal part, is refusal;
  anything else is end_turn.
- input_tokens includes cached tokens, so input_tokens = input - cached - cache writes.
- function_call_output has no error flag, so failed results start with "Error".

The openai package is an eval-only dependency, so it is imported when a client is made.
"""

from __future__ import annotations

import json
from typing import Any

from app.llm.base import LLMAPIError, LLMResponse, ToolCall, ToolResult, Usage

REQUEST_TIMEOUT_SECONDS = 120
MAX_RETRIES = 3
PROMPT_CACHE_KEY = "recruitassist-agent"
FATAL_ERROR_NAMES = ("BadRequestError", "AuthenticationError", "PermissionDeniedError", "NotFoundError")
# A 429 with one of these codes means the account is out of credit or quota, which retrying cannot fix.
FATAL_RATE_LIMIT_CODES = ("insufficient_quota", "credit_balance_exhausted")


def tool_spec(tool: dict[str, Any]) -> dict[str, Any]:
    """A neutral tool definition as a Responses API function tool (not strict, like the Anthropic tools)."""
    return {"type": "function", "name": tool["name"], "description": tool.get("description", ""),
            "parameters": tool["input_schema"], "strict": False}


def request(model: str, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]],
            effort: str, max_tokens: int) -> dict[str, Any]:
    """The Responses API arguments for one round."""
    params: dict[str, Any] = {
        "model": model,
        "instructions": system,
        "input": messages,
        "reasoning": {"effort": effort},
        "max_output_tokens": max_tokens,
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "prompt_cache_key": PROMPT_CACHE_KEY,
    }
    if tools:
        params["tools"] = [tool_spec(t) for t in tools]
        params["tool_choice"] = "auto"
    return params


def usage_of(usage: Any) -> Usage:
    """The neutral token counts, with cached and cache-write tokens taken out of input_tokens."""
    if usage is None:
        return Usage()
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    written = getattr(details, "cache_write_tokens", 0) or 0
    output_details = getattr(usage, "output_tokens_details", None)
    return Usage(input_tokens=max(0, (usage.input_tokens or 0) - cached - written),
                 output_tokens=usage.output_tokens or 0,
                 cache_creation_input_tokens=written,
                 cache_read_input_tokens=cached,
                 reasoning_tokens=getattr(output_details, "reasoning_tokens", 0) or 0)


def parse_arguments(raw: str | None) -> dict[str, Any]:
    """Tool call arguments as a dict. Invalid JSON is passed through so the tool call fails visibly."""
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {"invalid_json_arguments": raw}
    return value if isinstance(value, dict) else {"arguments": value}


def as_input(item: Any) -> Any:
    """An output item as a plain dict to send back as input on the next model call, unchanged."""
    if hasattr(item, "model_dump"):
        return item.model_dump(exclude_none=True, mode="json")
    if isinstance(item, list):
        return [as_input(i) for i in item]
    if hasattr(item, "__dict__"):
        return {k: as_input(v) for k, v in vars(item).items() if v is not None}
    return item


def normalize(response: Any, model: str) -> LLMResponse:
    """An LLMResponse from a Responses API response."""
    items = list(response.output or [])
    texts, refused = [], False
    for item in items:
        if item.type == "message":
            for part in item.content or []:
                if part.type == "output_text":
                    texts.append(part.text)
                elif part.type == "refusal":
                    refused = True
    calls = [ToolCall(i.call_id, i.name, parse_arguments(i.arguments)) for i in items if i.type == "function_call"]
    incomplete = getattr(getattr(response, "incomplete_details", None), "reason", None)
    if refused or incomplete == "content_filter":
        reason = "refusal"
    elif calls:
        reason = "tool_use"
    elif incomplete == "max_output_tokens":
        reason = "max_tokens"
    else:
        reason = "end_turn"
    return LLMResponse(text="".join(texts).strip(), tool_calls=calls, stop_reason=reason,
                       usage=usage_of(response.usage), served_by=getattr(response, "model", None) or model,
                       messages=[as_input(i) for i in items])


def wrap_error(error: Exception) -> LLMAPIError:
    """The neutral error for an SDK error."""
    kind = type(error).__name__
    out_of_credit = kind == "RateLimitError" and (
        getattr(error, "code", None) in FATAL_RATE_LIMIT_CODES
        or any(code in str(error) for code in FATAL_RATE_LIMIT_CODES))
    return LLMAPIError("openai", kind, str(error), kind in FATAL_ERROR_NAMES or out_of_credit)


class OpenAIClient:
    """LLMClient over an AsyncOpenAI client (or any object with responses.create)."""

    provider = "openai"

    def __init__(self, sdk: Any = None):
        if sdk is None:
            import openai
            sdk = openai.AsyncOpenAI(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
        self.sdk = sdk

    async def _call(self, params: dict[str, Any], model: str) -> LLMResponse:
        try:
            response = await self.sdk.responses.create(**params)
        except Exception as error:
            if _is_api_error(error):
                raise wrap_error(error) from error
            raise
        return normalize(response, model)

    async def create(self, *, model: str, system: str, tools: list[dict[str, Any]],
                     messages: list[dict[str, Any]], effort: str, max_tokens: int) -> LLMResponse:
        return await self._call(request(model, system, tools, messages, effort, max_tokens), model)

    def user_message(self, text: str) -> list[dict[str, Any]]:
        return [{"role": "user", "content": text}]

    def tool_results_message(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        return [{"type": "function_call_output", "call_id": r.call_id,
                 "output": r.content if not r.is_error or r.content.startswith("Error") else f"Error: {r.content}"}
                for r in results]

    async def complete(self, *, model: str, system: str, prompt: str, effort: str,
                       max_tokens: int) -> LLMResponse:
        return await self._call(request(model, system, [], [{"role": "user", "content": prompt}],
                                        effort, max_tokens), model)


def _is_api_error(error: Exception) -> bool:
    """True for errors raised by the openai SDK (checked by module so the SDK stays optional)."""
    try:
        import openai
    except ImportError:
        return False
    return isinstance(error, openai.APIError)
