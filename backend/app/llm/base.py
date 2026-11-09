"""The provider-neutral types every LLM adapter returns.

The agent loop, the evals, and the health check only see these types. Each adapter
turns its provider's response into an LLMResponse:

- stop_reason is one of STOP_REASONS, whatever the provider calls it.
- tool_calls are ToolCall(id, name, input) with input already parsed into a dict.
- usage is a Usage with the same four token counters for every provider. input_tokens
  never includes cached tokens, so cost is always tokens times the matching price.
- messages are the provider-native turns to append to the conversation, kept exactly
  as returned (thinking blocks included) so the next model call sends them back unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# end_turn: the model answered. tool_use: it wants tools run. max_tokens: cut off.
# refusal: the provider or model declined. pause_turn: call again without a new message.
STOP_REASONS = ("end_turn", "tool_use", "max_tokens", "refusal", "pause_turn")


@dataclass(frozen=True)
class ToolCall:
    """One tool call the model asked for."""
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The result of one tool call, to send back to the model."""
    call_id: str
    content: str
    is_error: bool = False


@dataclass
class Usage:
    """Token counts for one API call. input_tokens excludes cache writes and cache reads."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    reasoning_tokens: int = 0  # Already counted in output_tokens; reported for information only.


@dataclass
class LLMResponse:
    """One normalized model response."""
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    usage: Usage
    served_by: str
    messages: list[dict[str, Any]] = field(default_factory=list)


class LLMAPIError(Exception):
    """A provider API error after the SDK's own retries. fatal: retrying cannot fix it (bad key,
    bad request, no credit), so an eval matrix should stop instead of trying more runs."""

    def __init__(self, provider: str, kind: str, message: str, fatal: bool):
        super().__init__(f"{kind}: {message}")
        self.provider = provider
        self.kind = kind
        self.fatal = fatal


@runtime_checkable
class LLMClient(Protocol):
    """What the agent loop and the evals need from a model provider."""

    provider: str

    async def create(self, *, model: str, system: str, tools: list[dict[str, Any]],
                     messages: list[dict[str, Any]], effort: str, max_tokens: int) -> LLMResponse:
        """One model call with tool_choice auto, no sampling parameters, and the given effort.
        tools use the neutral shape {name, description, input_schema}."""
        ...

    def user_message(self, text: str) -> list[dict[str, Any]]:
        """The native message(s) for one user turn of plain text."""
        ...

    def tool_results_message(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        """The native message(s) that return every tool result of one round."""
        ...

    async def complete(self, *, model: str, system: str, prompt: str, effort: str,
                       max_tokens: int) -> LLMResponse:
        """A single text completion with no tools, used by the LLM judge."""
        ...
