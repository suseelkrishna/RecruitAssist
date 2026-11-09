"""What an /api/ask result shows to each role.

Admin sees the full result, including the tools called with their inputs, token usage,
latency, cost, and the verifier report. Every other role sees only the answer and the fields
the page needs to show it: the verified label, citations, and the recorded-answer note. This
is an allowlist, so any field the agent loop adds later stays hidden from non-admins until it
is listed here.
"""

from __future__ import annotations

from typing import Any

PUBLIC_FIELDS = ("answer", "status", "verified", "label", "citations", "model", "as_of", "job_id",
                 "source", "recording_reason", "recorded_at")


def public_result(result: dict[str, Any], role: str) -> dict[str, Any]:
    """The ask result as this role may see it: unchanged for admin, the allowlisted fields otherwise."""
    if role == "admin":
        return result
    return {key: result[key] for key in PUBLIC_FIELDS if key in result}
