"""A stand-in for the OpenAI client: Responses API replies are scripted, and every request is recorded.

Only what the OpenAI adapter reads is provided: client.responses.create returning an
object with output items, status, incomplete_details, usage, and model.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable


def call(call_id: str, name: str, args: dict[str, Any] | None = None, raw: str | None = None) -> SimpleNamespace:
    """One function_call output item, with arguments as the JSON string the API returns."""
    return SimpleNamespace(type="function_call", id=f"fc_{call_id}", call_id=call_id, name=name,
                           arguments=raw if raw is not None else json.dumps(args or {}), status="completed")


def reasoning(encrypted: str = "enc") -> SimpleNamespace:
    """One reasoning output item with encrypted content, as returned with store false."""
    return SimpleNamespace(type="reasoning", id="rs_1", summary=[], encrypted_content=encrypted)


def message(text: str | None = None, refusal: str | None = None) -> SimpleNamespace:
    """One assistant message output item holding output text or a refusal."""
    part = (SimpleNamespace(type="refusal", refusal=refusal) if refusal
            else SimpleNamespace(type="output_text", text=text or "", annotations=[]))
    return SimpleNamespace(type="message", id="msg_1", role="assistant", status="completed", content=[part])


def response(*items: SimpleNamespace, incomplete: str | None = None, prompt: int = 1500, cached: int = 0,
             output: int = 300, reasoning_tokens: int = 100) -> SimpleNamespace:
    """One Responses API response. incomplete sets status incomplete with that reason."""
    usage = SimpleNamespace(input_tokens=prompt, output_tokens=output, total_tokens=prompt + output,
                            input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=0),
                            output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens))
    return SimpleNamespace(output=list(items), status="incomplete" if incomplete else "completed",
                           incomplete_details=SimpleNamespace(reason=incomplete) if incomplete else None,
                           usage=usage, model="fake-gpt")


class FakeOpenAI:
    """Returns the scripted responses in order, or calls a function of the request, or raises."""

    def __init__(self, script: list[Any] | Callable[[dict[str, Any]], Any]):
        self.script = script
        self.requests: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self.create)

    async def create(self, **params: Any) -> SimpleNamespace:
        """Record the request (with a copy of the input so far) and return or raise the next item."""
        self.requests.append({**params, "input": list(params["input"])})
        item = self.script(params) if callable(self.script) else self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
