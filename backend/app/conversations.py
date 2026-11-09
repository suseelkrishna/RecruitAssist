"""Saved Ask conversations: who may read and change them, and what a stored turn holds.

Every function takes the Principal and only reads or writes that principal's own keys, so
a conversation ID that belongs to someone else gets the same 404 as one that does not
exist. Questions and answers are stored with email addresses and phone numbers masked.
A non-admin turn is stored through redact.public_result, so it never holds the tools
called, token usage, cost, or the verifier report. Storage itself is in app/store.py.
"""

from __future__ import annotations

import secrets
from typing import Any

from app import store
from app.access import Principal
from app.agent.redact import public_result
from app.logic.common import out_of_scope
from app.logic.evidence import mask_contacts

MAX_TURNS = 30
HISTORY_TURNS = 6
TITLE_FROM_QUESTION_CHARS = 60
MAX_TITLE_CHARS = 80
NEW_TITLE = "New chat"

# Fields every stored turn keeps (when the result has them). Admin turns also keep TRACE_FIELDS.
TURN_FIELDS = ("question", "job_id", "answer", "citations", "status", "verified", "label", "source",
               "recording_reason", "recorded_at", "model", "as_of")
TRACE_FIELDS = ("steps", "usage", "latency_ms", "estimated_cost_usd", "verifier", "served_by", "retried")


def new_id() -> str:
    """A random conversation ID such as CONV-3f9a0c1b2d4e."""
    return f"CONV-{secrets.token_hex(6)}"


def title_from(question: str) -> str:
    """A title from the first question: masked, at most TITLE_FROM_QUESTION_CHARS, cut at a word."""
    text = " ".join(mask_contacts(question).split())
    if len(text) <= TITLE_FROM_QUESTION_CHARS:
        return text or NEW_TITLE
    cut = text[:TITLE_FROM_QUESTION_CHARS]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,.;:") + "..."


def clean_title(title: str) -> str:
    """A title as the person typed it, masked, with spaces collapsed. ValueError when empty or too long."""
    text = " ".join(mask_contacts(title).split())
    if not text or len(text) > MAX_TITLE_CHARS:
        raise ValueError(f"A title needs 1 to {MAX_TITLE_CHARS} characters.")
    return text


def require(principal: Principal, conversation_id: str) -> dict[str, Any]:
    """The principal's conversation metadata, or the out-of-scope error (a 404)."""
    meta = store.get_conversation(principal.user_id, conversation_id)
    if meta is None:
        raise out_of_scope(conversation_id)
    return meta


def create(principal: Principal, title: str | None = None) -> dict[str, Any]:
    """Start an empty conversation for the principal. Without a title it is named from its first question."""
    at = store.now()
    meta = {"id": new_id(), "user_id": principal.user_id, "title": clean_title(title) if title else NEW_TITLE,
            "titled": bool(title), "created_at": at, "updated_at": at, "turn_count": 0}
    store.save_conversation(meta)
    return meta


def list_for(principal: Principal) -> list[dict[str, Any]]:
    """The principal's conversations, most recently updated first, without their turns."""
    return store.list_conversations(principal.user_id)


def get(principal: Principal, conversation_id: str) -> dict[str, Any]:
    """One of the principal's conversations with all its turns, oldest first."""
    meta = require(principal, conversation_id)
    turns = store.get_turns(principal.user_id, conversation_id)
    return {**meta, "turn_count": len(turns), "turns": turns}


def rename(principal: Principal, conversation_id: str, title: str) -> dict[str, Any]:
    """Give one of the principal's conversations a new title."""
    meta = {**require(principal, conversation_id), "title": clean_title(title), "titled": True,
            "updated_at": store.now()}
    store.save_conversation(meta)
    return meta


def delete(principal: Principal, conversation_id: str) -> None:
    """Remove one of the principal's conversations and its turns."""
    require(principal, conversation_id)
    store.delete_conversation(principal.user_id, conversation_id)


def is_full(meta: dict[str, Any]) -> bool:
    """True when the conversation already has MAX_TURNS turns."""
    return meta.get("turn_count", 0) >= MAX_TURNS


def stored_turn(principal: Principal, question: str, job_id: str | None, result: dict[str, Any]) -> dict[str, Any]:
    """The turn as it is saved: the public answer fields for everyone, plus the trace for admin,
    with contact details masked in the question and the answer."""
    shown = public_result(result, principal.role)
    fields = TURN_FIELDS + (TRACE_FIELDS if principal.role == "admin" else ())
    turn = {"turn_id": f"TURN-{secrets.token_hex(6)}", "at": store.now()}
    turn |= {key: shown[key] for key in fields if key in shown}
    turn["question"] = mask_contacts(question)
    turn["job_id"] = job_id
    turn["answer"] = mask_contacts(shown.get("answer", ""))
    return turn


def append_turn(principal: Principal, conversation_id: str, question: str, job_id: str | None,
                result: dict[str, Any]) -> dict[str, Any]:
    """Save one answered question at the end of the principal's conversation and return the stored turn.
    The first question names a conversation that has no title of its own yet."""
    meta = require(principal, conversation_id)
    turn = stored_turn(principal, question, job_id, result)
    count = store.append_turn(principal.user_id, conversation_id, turn)
    meta |= {"turn_count": count, "updated_at": turn["at"]}
    if not meta.get("titled") and meta["title"] == NEW_TITLE:
        meta["title"] = title_from(question)
    store.save_conversation(meta)
    return turn


def history_for(principal: Principal, conversation_id: str) -> list[dict[str, Any]]:
    """The last HISTORY_TURNS answered turns of a conversation as {question, answer, citations},
    the history the agent gets with a follow-up question."""
    turns = [t for t in store.get_turns(principal.user_id, conversation_id) if t.get("status", "answered") == "answered"]
    return [{"question": t["question"], "answer": t.get("answer", ""), "citations": t.get("citations", [])}
            for t in turns[-HISTORY_TURNS:]]
