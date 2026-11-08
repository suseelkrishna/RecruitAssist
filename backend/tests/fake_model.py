"""A stand-in for the Anthropic client: replies are scripted, and every request is recorded.

Only the attributes the agent loop reads are provided: client.beta.messages.create
returning an object with content, stop_reason, usage, and model.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable


def text(body: str) -> SimpleNamespace:
    """A text content block."""
    return SimpleNamespace(type="text", text=body)


def tool_use(call_id: str, name: str, args: dict[str, Any] | None = None) -> SimpleNamespace:
    """A tool_use content block."""
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=args or {})


def reply(*blocks: SimpleNamespace, stop: str = "end_turn", cache_read: int = 0) -> SimpleNamespace:
    """One Messages API response with fixed token usage."""
    usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=500,
                            cache_read_input_tokens=cache_read)
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=usage, model="fake-model")


class FakeClient:
    """Returns the scripted replies in order, or calls a function of the request for each one."""

    def __init__(self, script: list[SimpleNamespace] | Callable[[dict[str, Any]], SimpleNamespace]):
        self.script = script
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **params: Any) -> SimpleNamespace:
        """Record the request (with a copy of the messages so far) and return the next reply."""
        self.requests.append({**params, "messages": list(params["messages"])})
        if callable(self.script):
            return self.script(params)
        return self.script.pop(0)
