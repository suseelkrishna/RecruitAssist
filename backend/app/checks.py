"""Live checks for the sources page: the database, the model API, and the writable store.

The model API check makes a real request, so its result is cached for
MODEL_CHECK_TTL_SECONDS and reused by every caller until it expires.
"""

from __future__ import annotations

import os
import time
from typing import Any

import anthropic

from app import db, store
from app.agent.loop import model_name

MODEL_CHECK_TTL_SECONDS = 600
MODEL_CHECK_TIMEOUT_SECONDS = 10

_model_check: dict[str, Any] = {}


def live_checks() -> list[dict[str, Any]]:
    """One row per live dependency with its status."""
    return [database_check(), model_check(), store.ping()]


def database_check() -> dict[str, Any]:
    """Open the read-only database and read its as_of and generator version."""
    try:
        meta = {r["key"]: r["value"] for r in db.rows("SELECT key, value FROM meta")}
    except Exception as error:  # Reported on the page rather than failing the whole request.
        return {"name": "Database", "status": "error", "error": type(error).__name__}
    return {"name": "Database", "status": "ok", "mode": "read-only",
            "as_of": meta.get("as_of"), "generator_version": meta.get("generator_version")}


def model_check() -> dict[str, Any]:
    """Look up the configured model on the Models API, cached for ten minutes."""
    if _model_check and time.monotonic() - _model_check["checked"] < MODEL_CHECK_TTL_SECONDS:
        return _model_check["result"]
    model = model_name()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        result = {"name": "Model API", "status": "not_configured", "model": model,
                  "note": "ANTHROPIC_API_KEY is not set, so answers come from recordings."}
    else:
        try:
            client = anthropic.Anthropic(timeout=MODEL_CHECK_TIMEOUT_SECONDS, max_retries=0)
            found = client.models.retrieve(model)
            result = {"name": "Model API", "status": "ok", "model": found.id}
        except anthropic.APIError as error:
            result = {"name": "Model API", "status": "error", "model": model, "error": type(error).__name__}
    _model_check.update(checked=time.monotonic(), result=result)
    return result
