"""The change log as the changes page shows it: each entry with who made it, their role, and a
one-line description, newest first.

The log itself lives in app/store.py and is append-only. This file only reads it and adds
names. Question entries keep only a hash of the question, the tools used, the record IDs
touched, and the verifier result, so no candidate text is ever shown or stored.
"""

from __future__ import annotations

from typing import Any

from app import db, store
from app.access import Principal

QUESTION_HASH_CHARS = 12


def change_log(principal: Principal) -> dict[str, Any]:
    """The entries this principal may see, newest first, with names, roles, and a summary."""
    users = {u["user_id"]: u for u in db.rows("SELECT user_id, name, role FROM users")}
    name = lambda user_id: users[user_id]["name"] if user_id in users else (user_id or "nobody")
    entries = []
    for change in store.list_changes(principal):
        who = users.get(change.get("user_id"), {})
        entry = {**change, "user_name": who.get("name"), "user_role": who.get("role")}
        if change["type"] == "reassignment":
            entry["summary"] = (f"{change['job_id']} recruiter: {name(change.get('from_recruiter_user_id'))} "
                                f"to {name(change.get('to_recruiter_user_id'))}")
        else:
            entry["question_hash"] = change["question_sha256"][:QUESTION_HASH_CHARS]
            entry["summary"] = f"Question {entry['question_hash']}"
        entries.append(entry)
    return {"changes": entries}
