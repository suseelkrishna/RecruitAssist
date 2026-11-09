"""The only writable storage: recruiter assignment overrides, the change log, rate limits,
and saved Ask conversations.

When the Upstash REST URL and token are set, data lives in Upstash Redis and
survives restarts and multiple server instances. They are read from
UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN, or from KV_REST_API_URL and
KV_REST_API_TOKEN, the names the Vercel Marketplace integration creates. Otherwise it
lives in process memory and resets when the process restarts. The read-only
SQLite database is never written; this store sits beside it.

The change log is append-only: there is no function to edit or delete an entry.

A conversation is three kinds of keys: its metadata, its turns as a list that only grows
by RPUSH (so two tabs asking at once both keep their turn), and a per-user sorted set of
conversation IDs scored by last update, newest first. Every conversation key expires
CONVERSATION_TTL_DAYS after its last write, and a user keeps at most MAX_CONVERSATIONS.
The rules about who may touch which conversation live in app/conversations.py.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.access import Principal

PREFIX = "recruitassist:"
TIMEOUT_SECONDS = 5

_assignments: dict[str, dict[str, Any]] = {}
_changes: list[dict[str, Any]] = []
_hits: dict[str, int] = {}
# Memory backend for conversations: key -> (expires_at, value), where value is the metadata
# dict, the list of turns, or for an index key a dict of conversation_id -> score.
_conversations: dict[str, tuple[float, Any]] = {}
_last_score = 0.0

CONVERSATION_TTL_DAYS = 30
MAX_CONVERSATIONS = 50


def redis_url() -> str:
    """The Upstash REST URL, from UPSTASH_REDIS_REST_URL or else KV_REST_API_URL, or '' if neither is set."""
    return os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL") or ""


def redis_token() -> str:
    """The Upstash REST token with write access, from UPSTASH_REDIS_REST_TOKEN or else KV_REST_API_TOKEN.
    The read-only token cannot write the change log, so it is never used."""
    return os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN") or ""


def backend() -> str:
    """'redis' when an Upstash REST URL is set, otherwise 'memory'."""
    return "redis" if redis_url() else "memory"


def redis(*command: Any) -> Any:
    """Run one Redis command through the Upstash REST API and return its result."""
    request = urllib.request.Request(
        redis_url(),
        data=json.dumps([str(part) for part in command]).encode(),
        headers={"Authorization": f"Bearer {redis_token()}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read())["result"]


def get_assignment_overrides() -> dict[str, str]:
    """The current recruiter for every job that has been reassigned, keyed by job_id."""
    if backend() == "redis":
        flat = redis("HGETALL", PREFIX + "assignments") or []
        stored = {flat[i]: json.loads(flat[i + 1]) for i in range(0, len(flat), 2)}
    else:
        stored = _assignments
    return {job_id: value["recruiter_user_id"] for job_id, value in stored.items()}


def set_assignment(job_id: str, recruiter_id: str, by_user_id: str) -> None:
    """Make recruiter_id the job's recruiter, replacing the seed assignment and earlier overrides."""
    value = {"recruiter_user_id": recruiter_id, "by_user_id": by_user_id, "at": now()}
    if backend() == "redis":
        redis("HSET", PREFIX + "assignments", job_id, json.dumps(value))
    else:
        _assignments[job_id] = value


def append_change(event: dict[str, Any]) -> dict[str, Any]:
    """Add one event to the change log with the next change_id (CHG-001, ...) and return it."""
    if backend() == "redis":
        number = redis("INCR", PREFIX + "changes:seq")
    else:
        number = len(_changes) + 1
    entry = {"change_id": f"CHG-{number:03d}", "at": now(), **event}
    if backend() == "redis":
        redis("RPUSH", PREFIX + "changes", json.dumps(entry))
    else:
        _changes.append(entry)
    return dict(entry)


def all_changes() -> list[dict[str, Any]]:
    """Every change event, oldest first, as copies so callers cannot edit the log."""
    if backend() == "redis":
        return [json.loads(raw) for raw in redis("LRANGE", PREFIX + "changes", 0, -1) or []]
    return [dict(entry) for entry in _changes]


def list_changes(principal: Principal) -> list[dict[str, Any]]:
    """The change events this principal may see, newest first.

    admin sees every event. Everyone else sees events about jobs in their scope
    (their teams' jobs for hr_manager, their own jobs for hr_user), events they
    made themselves, and reassignments that moved a job to or from them.
    """
    changes = all_changes()
    if principal.role != "admin":
        me = principal.user_id
        changes = [c for c in changes
                   if c.get("job_id") in principal.allowed_job_ids or c.get("user_id") == me
                   or me in (c.get("from_recruiter_user_id"), c.get("to_recruiter_user_id"))]
    return list(reversed(changes))


def hit_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Count one hit for key in the current fixed time window. True when this hit is over the limit."""
    bucket = f"{PREFIX}rate:{key}:{int(time.time() // window_seconds)}"
    if backend() == "redis":
        count = redis("INCR", bucket)
        if count == 1:
            redis("EXPIRE", bucket, window_seconds)
    else:
        count = _hits.get(bucket, 0) + 1
        _hits[bucket] = count
    return count > limit


def conversation_key(user_id: str, conversation_id: str) -> str:
    """The key holding one conversation's metadata."""
    return f"{PREFIX}conv:{user_id}:{conversation_id}"


def turns_key(user_id: str, conversation_id: str) -> str:
    """The key holding one conversation's turns, oldest first."""
    return f"{conversation_key(user_id, conversation_id)}:turns"


def index_key(user_id: str) -> str:
    """The key of a user's conversation index, scored by last update."""
    return f"{PREFIX}convs:{user_id}"


def ttl_seconds() -> int:
    """How long a conversation key lives after its last write."""
    return CONVERSATION_TTL_DAYS * 24 * 3600


def next_score() -> float:
    """The index score for a write now: the current time, nudged so two writes in the same
    instant still sort in the order they happened."""
    global _last_score
    _last_score = max(time.time(), _last_score + 0.000001)
    return _last_score


def memory_get(key: str, default: Any = None) -> Any:
    """A memory-backend value, or default when it is missing or has expired."""
    entry = _conversations.get(key)
    if entry is None or entry[0] <= time.time():
        _conversations.pop(key, None)
        return default
    return entry[1]


def memory_set(key: str, value: Any) -> None:
    """Store a memory-backend value with a fresh expiry."""
    _conversations[key] = (time.time() + ttl_seconds(), value)


def save_conversation(meta: dict[str, Any]) -> list[str]:
    """Write a conversation's metadata, move it to the top of its user's index, refresh the
    expiry of all its keys, and drop the user's oldest conversations past MAX_CONVERSATIONS.
    Returns the IDs of the conversations dropped."""
    user_id, conversation_id = meta["user_id"], meta["id"]
    score = next_score()
    if backend() == "redis":
        redis("SET", conversation_key(user_id, conversation_id), json.dumps(meta), "EX", ttl_seconds())
        redis("ZADD", index_key(user_id), score, conversation_id)
        redis("EXPIRE", index_key(user_id), ttl_seconds())
        redis("EXPIRE", turns_key(user_id, conversation_id), ttl_seconds())
        extra = int(redis("ZCARD", index_key(user_id))) - MAX_CONVERSATIONS
        dropped = list(redis("ZRANGE", index_key(user_id), 0, extra - 1)) if extra > 0 else []
    else:
        memory_set(conversation_key(user_id, conversation_id), dict(meta))
        index = memory_get(index_key(user_id), {})
        index[conversation_id] = score
        memory_set(index_key(user_id), index)
        turns = memory_get(turns_key(user_id, conversation_id))
        if turns is not None:
            memory_set(turns_key(user_id, conversation_id), turns)
        extra = len(index) - MAX_CONVERSATIONS
        dropped = sorted(index, key=index.get)[:extra] if extra > 0 else []
    for old in dropped:
        delete_conversation(user_id, old)
    return dropped


def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    """One conversation's metadata, or None when it does not exist or has expired."""
    if backend() == "redis":
        raw = redis("GET", conversation_key(user_id, conversation_id))
        return json.loads(raw) if raw else None
    meta = memory_get(conversation_key(user_id, conversation_id))
    return dict(meta) if meta else None


def list_conversations(user_id: str) -> list[dict[str, Any]]:
    """A user's conversation metadata, most recently updated first, read with one MGET on Redis.
    Index entries whose metadata has expired are removed as they are found."""
    if backend() == "redis":
        ids = list(redis("ZREVRANGE", index_key(user_id), 0, -1) or [])
        raw = redis("MGET", *[conversation_key(user_id, i) for i in ids]) if ids else []
        metas = [json.loads(r) if r else None for r in raw]
    else:
        index = memory_get(index_key(user_id), {})
        ids = sorted(index, key=index.get, reverse=True)
        metas = [get_conversation(user_id, i) for i in ids]
    found = []
    for conversation_id, meta in zip(ids, metas):
        if meta is None:
            delete_conversation(user_id, conversation_id)
        else:
            found.append(meta)
    return found


def append_turn(user_id: str, conversation_id: str, turn: dict[str, Any]) -> int:
    """Add one turn to the end of a conversation and return how many turns it now has.
    RPUSH adds without reading the list first, so concurrent appends never overwrite each other."""
    if backend() == "redis":
        count = int(redis("RPUSH", turns_key(user_id, conversation_id), json.dumps(turn)))
        redis("EXPIRE", turns_key(user_id, conversation_id), ttl_seconds())
        return count
    turns = memory_get(turns_key(user_id, conversation_id), [])
    turns.append(dict(turn))
    memory_set(turns_key(user_id, conversation_id), turns)
    return len(turns)


def get_turns(user_id: str, conversation_id: str) -> list[dict[str, Any]]:
    """A conversation's turns, oldest first."""
    if backend() == "redis":
        return [json.loads(raw) for raw in redis("LRANGE", turns_key(user_id, conversation_id), 0, -1) or []]
    return [dict(t) for t in memory_get(turns_key(user_id, conversation_id), [])]


def delete_conversation(user_id: str, conversation_id: str) -> None:
    """Remove a conversation's metadata, its turns, and its index entry."""
    if backend() == "redis":
        redis("DEL", conversation_key(user_id, conversation_id), turns_key(user_id, conversation_id))
        redis("ZREM", index_key(user_id), conversation_id)
        return
    _conversations.pop(conversation_key(user_id, conversation_id), None)
    _conversations.pop(turns_key(user_id, conversation_id), None)
    index = memory_get(index_key(user_id))
    if index is not None:
        index.pop(conversation_id, None)


def ping() -> dict[str, Any]:
    """A live check of the store for the sources page: which backend and whether it answers."""
    if backend() == "memory":
        return {"name": "Store", "status": "ok", "backend": "memory",
                "note": "In-memory store: changes reset when the server restarts."}
    try:
        ok = redis("PING") == "PONG"
    except OSError as error:
        return {"name": "Store", "status": "error", "backend": "redis", "error": type(error).__name__}
    return {"name": "Store", "status": "ok" if ok else "error", "backend": "redis"}


def now() -> str:
    """The current UTC time as a stored timestamp, for example 2026-11-09T17:00:00Z."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clear() -> None:
    """Empty the in-memory store. Tests use this to start from the seed assignments."""
    _assignments.clear()
    _changes.clear()
    _hits.clear()
    _conversations.clear()
