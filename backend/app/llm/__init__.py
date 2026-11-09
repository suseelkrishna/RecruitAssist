"""A thin LLM client interface with Anthropic and OpenAI adapters.

The agent loop, the evals, and the health check call models only through this
package. Models are selected by ID; app/llm/models.json maps each ID to its
provider and list prices. IDs not in the table fall back to a prefix rule:
claude-* is Anthropic, gpt-* and o<digit>* are OpenAI.

The fields of each entry in models.json:
  prices        US dollars per million tokens: input (uncached), output (includes any
                reasoning or thinking tokens), cache_write, and cache_read. The evals
                multiply these by the token counts each provider reports, so the cost
                columns in evals/results.md are only as good as these numbers. OpenAI
                does not charge extra to write the prompt cache, so its cache_write
                equals input.
  confirm       true when the price came from a third-party tracker rather than the
                provider's own price page; check it before relying on the cost columns.
  production    true when the app may use the model live (ANTHROPIC_MODEL). The default
                model the evals pick is chosen only from these. false means eval runs
                only; the app refuses it unless ALLOW_OPENAI_LIVE=1.
  eval          true when evals/run.py runs it without --models; false lists it in the
                report as not run, with skip_reason.

OpenAI models are for eval runs. make_client(model) refuses them for the app
unless ALLOW_OPENAI_LIVE=1, so production keeps using a Claude model.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.llm.base import (STOP_REASONS, LLMAPIError, LLMClient, LLMResponse, ToolCall, ToolResult,
                          Usage)

__all__ = ["STOP_REASONS", "LLMAPIError", "LLMClient", "LLMResponse", "ToolCall", "ToolResult", "Usage",
           "models", "provider_for", "prices", "estimated_cost", "make_client", "as_client",
           "eval_models", "skipped_models", "is_production", "api_key_env", "lookup_model",
           "OpenAINotAllowed"]

MODELS_FILE = Path(__file__).resolve().parent / "models.json"
API_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


class OpenAINotAllowed(ValueError):
    """An OpenAI model was configured for the app without ALLOW_OPENAI_LIVE=1."""


@lru_cache(maxsize=1)
def models() -> dict[str, dict[str, Any]]:
    """The model table from models.json."""
    return json.loads(MODELS_FILE.read_text())["models"]


def provider_for(model: str) -> str:
    """anthropic or openai for a model ID. Raises ValueError for an ID neither can serve."""
    entry = models().get(model)
    if entry:
        return entry["provider"]
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gpt-") or re.match(r"o\d", model):
        return "openai"
    raise ValueError(f"Unknown model {model!r}. Add it to app/llm/models.json with its provider.")


def api_key_env(model: str) -> str:
    """The environment variable that holds the API key for this model's provider."""
    return API_KEY_ENV[provider_for(model)]


def prices(model: str) -> tuple[float, float, float, float] | None:
    """(input, output, cache_write, cache_read) dollars per million tokens, or None if unpriced."""
    entry = models().get(model)
    if not entry or not entry.get("prices"):
        return None
    p = entry["prices"]
    return (p["input"], p["output"], p["cache_write"], p["cache_read"])


def estimated_cost(model: str, usage: dict[str, int]) -> float | None:
    """Estimated US dollars for the summed usage of one run, or None if the model is unpriced."""
    p = prices(model)
    if p is None:
        return None
    tokens = (usage["input_tokens"], usage["output_tokens"],
              usage["cache_creation_input_tokens"], usage["cache_read_input_tokens"])
    return round(sum(n * price for n, price in zip(tokens, p)) / 1_000_000, 6)


def is_production(model: str) -> bool:
    """True when the app may use this model live by default (only Anthropic models today)."""
    entry = models().get(model)
    if entry is not None:
        return bool(entry.get("production"))
    return provider_for(model) == "anthropic"


def eval_models() -> list[str]:
    """The models evals/run.py runs by default, in table order."""
    return [m for m, e in models().items() if e.get("eval")]


def skipped_models() -> dict[str, str]:
    """Models listed in the table but not run, with the reason, for the report."""
    return {m: e.get("skip_reason", "Not run.") for m, e in models().items() if not e.get("eval")}


def make_client(model: str, purpose: str = "app") -> LLMClient:
    """A client for the model's provider.

    purpose "app" is the live web app and CLI: an OpenAI model is refused unless
    ALLOW_OPENAI_LIVE=1. purpose "eval" is evals/run.py, which may use any provider.
    """
    provider = provider_for(model)
    if provider == "openai":
        if purpose != "eval" and os.environ.get("ALLOW_OPENAI_LIVE") != "1":
            raise OpenAINotAllowed(f"{model} is an OpenAI model, which is used for eval runs only. "
                                   "Set ALLOW_OPENAI_LIVE=1 to use it in the app.")
        from app.llm.openai_client import OpenAIClient
        return OpenAIClient()
    from app.llm.anthropic_client import AnthropicClient
    return AnthropicClient()


def as_client(client: Any) -> LLMClient:
    """client if it already implements LLMClient, else an Anthropic SDK client (or a test double
    shaped like one) wrapped in the Anthropic adapter."""
    if isinstance(client, LLMClient):
        return client
    from app.llm.anthropic_client import AnthropicClient
    return AnthropicClient(client)


def lookup_model(model: str, timeout: float) -> str:
    """The model ID the provider's Models API reports. Raises LLMAPIError on failure."""
    if provider_for(model) == "openai":
        import openai
        try:
            return openai.OpenAI(timeout=timeout, max_retries=0).models.retrieve(model).id
        except openai.APIError as error:
            from app.llm.openai_client import wrap_error
            raise wrap_error(error) from error
    from app.llm.anthropic_client import lookup_model as anthropic_lookup
    return anthropic_lookup(model, timeout)
