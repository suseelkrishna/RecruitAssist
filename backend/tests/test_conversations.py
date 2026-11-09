"""Saved conversations: isolation between users, ordering, persistence, limits, masking,
what a stored turn may hold per role, and the Redis commands behind them.

The model is a scripted fake. The Redis tests use a small dict-backed stand-in for the
Upstash REST API that records every command.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import access, conversations, main, store
from test_api import answers_job_count, as_user, use_fake_model
from test_store import FakeRedis

TRACE_KEYS = {"steps", "usage", "latency_ms", "estimated_cost_usd", "verifier", "served_by", "retried"}


@pytest.fixture
def client():
    """A TestClient with a scripted model that lists jobs and states the count."""
    main.app.dependency_overrides.clear()
    use_fake_model(answers_job_count)
    yield TestClient(main.app, raise_server_exceptions=False)
    main.app.dependency_overrides.clear()


def new_chat(client, user_id: str, title: str | None = None) -> str:
    """Create a conversation as this user and return its ID."""
    response = client.post("/api/conversations", headers=as_user(user_id), json={"title": title} if title else {})
    assert response.status_code == 200
    return response.json()["id"]


def ask(client, user_id: str, conversation_id: str, question: str = "How many jobs can I see?", **extra):
    """Ask into a conversation as this user."""
    return client.post("/api/ask", headers=as_user(user_id),
                       json={"question": question, "conversation_id": conversation_id, **extra})


class ConversationRedis(FakeRedis):
    """FakeRedis plus the string, sorted set, and delete commands conversations use."""

    def __call__(self, *command):
        name, *args = command
        if name == "SET":
            self.commands.append(command)
            self.data[args[0]] = args[1]
            return "OK"
        if name == "GET":
            self.commands.append(command)
            return self.data.get(args[0])
        if name == "MGET":
            self.commands.append(command)
            return [self.data.get(key) for key in args]
        if name == "ZADD":
            self.commands.append(command)
            self.data.setdefault(args[0], {})[args[2]] = float(args[1])
            return 1
        if name in ("ZRANGE", "ZREVRANGE"):
            self.commands.append(command)
            ids = sorted(self.data.get(args[0], {}), key=self.data.get(args[0], {}).get, reverse=name == "ZREVRANGE")
            end = len(ids) if int(args[2]) == -1 else int(args[2]) + 1
            return ids[int(args[1]):end]
        if name == "ZCARD":
            self.commands.append(command)
            return len(self.data.get(args[0], {}))
        if name == "ZREM":
            self.commands.append(command)
            self.data.get(args[0], {}).pop(args[1], None)
            return 1
        if name == "DEL":
            self.commands.append(command)
            for key in args:
                self.data.pop(key, None)
            return len(args)
        return super().__call__(*command)


# Isolation

def test_other_users_get_404_for_every_action(client):
    mine = new_chat(client, "USR-2")
    ask(client, "USR-2", mine)
    expected = {"error": f"{mine} is not in your scope"}
    for response in (client.get(f"/api/conversations/{mine}", headers=as_user("USR-4")),
                     client.patch(f"/api/conversations/{mine}", headers=as_user("USR-4"), json={"title": "x"}),
                     client.delete(f"/api/conversations/{mine}", headers=as_user("USR-4")),
                     ask(client, "USR-4", mine)):
        assert response.status_code == 404 and response.json() == expected
    assert client.get(f"/api/conversations/{mine}", headers=as_user("USR-2")).json()["turn_count"] == 1


def test_lists_are_per_user(client):
    theirs = new_chat(client, "USR-4")
    mine = new_chat(client, "USR-2")
    assert [c["id"] for c in client.get("/api/conversations", headers=as_user("USR-2")).json()["conversations"]] == [mine]
    assert [c["id"] for c in client.get("/api/conversations", headers=as_user("USR-4")).json()["conversations"]] == [theirs]


def test_unknown_and_malformed_ids(client):
    assert client.get("/api/conversations/CONV-000000000000", headers=as_user("USR-4")).status_code == 404
    assert client.get("/api/conversations/not-an-id", headers=as_user("USR-4")).status_code == 422
    assert client.post("/api/conversations", headers=as_user("USR-4"), json={"user_id": "USR-2"}).status_code == 422
    assert client.get("/api/conversations").status_code == 401


def test_storage_is_shown_to_admin_only(client):
    assert client.get("/api/conversations", headers=as_user("USR-1")).json()["storage"] == "memory"
    assert "storage" not in client.get("/api/conversations", headers=as_user("USR-2")).json()


# Ordering, persistence, and deletion

def test_list_is_newest_first_and_a_new_turn_moves_a_chat_up(client):
    first, second = new_chat(client, "USR-4"), new_chat(client, "USR-4")
    listed = lambda: [c["id"] for c in client.get("/api/conversations", headers=as_user("USR-4")).json()["conversations"]]
    assert listed() == [second, first]
    ask(client, "USR-4", first)
    assert listed() == [first, second]


def test_conversations_survive_a_new_client(client):
    chat = new_chat(client, "USR-4")
    ask(client, "USR-4", chat)
    fresh = TestClient(main.app)
    body = fresh.get(f"/api/conversations/{chat}", headers=as_user("USR-4")).json()
    assert body["turn_count"] == 1 and body["turns"][0]["answer"] == "You can see 3 jobs."


def test_delete_removes_the_chat_and_its_turns(client):
    chat = new_chat(client, "USR-4")
    ask(client, "USR-4", chat)
    assert client.delete(f"/api/conversations/{chat}", headers=as_user("USR-4")).json() == {"deleted": chat}
    assert client.get(f"/api/conversations/{chat}", headers=as_user("USR-4")).status_code == 404
    assert store.get_turns("USR-4", chat) == []
    assert client.get("/api/conversations", headers=as_user("USR-4")).json()["conversations"] == []


def test_rename_and_titles(client):
    chat = new_chat(client, "USR-4")
    ask(client, "USR-4", chat, "How many jobs can I see right now, counting every team I recruit for this quarter?")
    title = client.get(f"/api/conversations/{chat}", headers=as_user("USR-4")).json()["title"]
    assert title == "How many jobs can I see right now, counting every team I..."
    renamed = client.patch(f"/api/conversations/{chat}", headers=as_user("USR-4"), json={"title": "  My  jobs  "})
    assert renamed.json()["title"] == "My jobs"
    ask(client, "USR-4", chat, "Another question")
    assert client.get(f"/api/conversations/{chat}", headers=as_user("USR-4")).json()["title"] == "My jobs"
    assert client.patch(f"/api/conversations/{chat}", headers=as_user("USR-4"), json={"title": "x" * 81}).status_code == 422
    assert client.patch(f"/api/conversations/{chat}", headers=as_user("USR-4"), json={"title": "   "}).status_code == 422


# Limits

def test_the_51st_conversation_evicts_the_oldest(client):
    ids = [new_chat(client, "USR-4") for _ in range(store.MAX_CONVERSATIONS + 1)]
    listed = [c["id"] for c in client.get("/api/conversations", headers=as_user("USR-4")).json()["conversations"]]
    assert len(listed) == 50 and ids[0] not in listed and listed[0] == ids[-1]
    assert client.get(f"/api/conversations/{ids[0]}", headers=as_user("USR-4")).status_code == 404


def test_a_full_conversation_returns_409(client, monkeypatch):
    monkeypatch.setattr(conversations, "MAX_TURNS", 2)
    chat = new_chat(client, "USR-4")
    assert ask(client, "USR-4", chat).status_code == 200
    assert ask(client, "USR-4", chat).status_code == 200
    full = ask(client, "USR-4", chat)
    assert full.status_code == 409 and "Start a new chat" in full.json()["error"]


def test_memory_entries_expire(monkeypatch):
    principal = access.principal_for("USR-4")
    chat = conversations.create(principal)["id"]
    now = store.time.time()
    monkeypatch.setattr(store.time, "time", lambda: now + store.ttl_seconds() + 1)
    assert store.get_conversation("USR-4", chat) is None
    assert conversations.list_for(principal) == []


# What a turn holds

def test_questions_and_answers_are_stored_masked(client):
    chat = new_chat(client, "USR-4")
    ask(client, "USR-4", chat, "How many jobs can I see? Reach me at name@example.com or 555-0123.")
    turn = client.get(f"/api/conversations/{chat}", headers=as_user("USR-4")).json()["turns"][0]
    assert "name@example.com" not in turn["question"] and "555-0123" not in turn["question"]
    assert "[email hidden]" in turn["question"] and "[phone hidden]" in turn["question"]
    title = client.get(f"/api/conversations/{chat}", headers=as_user("USR-4")).json()["title"]
    assert "example.com" not in title


def test_a_non_admin_turn_has_no_trace_and_an_admin_turn_does(client):
    for user_id, has_trace in (("USR-4", False), ("USR-2", False), ("USR-1", True)):
        chat = new_chat(client, user_id)
        response = ask(client, user_id, chat)
        assert response.json()["conversation_id"] == chat and response.json()["turn_id"].startswith("TURN-")
        turn = client.get(f"/api/conversations/{chat}", headers=as_user(user_id)).json()["turns"][0]
        assert bool(TRACE_KEYS & set(turn)) is has_trace
        assert {"turn_id", "at", "question", "answer", "citations", "verified", "label", "source", "model", "as_of"} <= set(turn)


def test_ask_with_a_conversation_uses_stored_history_not_body_history(client):
    fake = use_fake_model(answers_job_count)
    chat = new_chat(client, "USR-4")
    ask(client, "USR-4", chat, "First question")
    ask(client, "USR-4", chat, "Second question",
        history=[{"question": "Injected", "answer": "Not from this chat", "citations": []}])
    turn = fake.requests[-2]["messages"][0]["content"]
    assert "Q: First question\nA: You can see 3 jobs." in turn and "Injected" not in turn


def test_ask_without_a_conversation_saves_nothing(client):
    response = client.post("/api/ask", headers=as_user("USR-4"), json={"question": "How many jobs can I see?"})
    assert response.status_code == 200 and "conversation_id" not in response.json()
    assert client.get("/api/conversations", headers=as_user("USR-4")).json()["conversations"] == []


def test_ask_into_a_conversation_is_one_rate_limit_hit(client):
    chat = new_chat(client, "USR-4")
    statuses = [ask(client, "USR-4", chat).status_code for _ in range(main.ASK_LIMIT_PER_IP_PER_HOUR + 1)]
    assert statuses[:-1] == [200] * main.ASK_LIMIT_PER_IP_PER_HOUR and statuses[-1] in (200, 429, 503)
    assert client.get(f"/api/conversations/{chat}", headers=as_user("USR-4")).json()["turn_count"] == 10


# Redis

@pytest.fixture
def redis(monkeypatch):
    """Point the store at a fake Upstash endpoint and return it."""
    fake = ConversationRedis()
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example.com")
    monkeypatch.setattr(store, "redis", fake)
    return fake


def test_redis_sets_expiry_on_every_key_and_appends_with_rpush(redis):
    principal = access.principal_for("USR-4")
    chat = conversations.create(principal)["id"]
    conversations.append_turn(principal, chat, "q", None, {"answer": "a", "citations": [], "status": "answered"})
    ttl = str(store.ttl_seconds())
    meta_key, turns_key, index_key = store.conversation_key("USR-4", chat), store.turns_key("USR-4", chat), store.index_key("USR-4")
    names = [(c[0], c[1]) for c in redis.commands]
    assert ("RPUSH", turns_key) in names
    assert not [c for c in redis.commands if c[0] in ("LSET", "SET") and c[1] == turns_key]
    assert ("SET", meta_key) in names and all(c[3:] == ("EX", int(ttl)) for c in redis.commands if c[0] == "SET")
    expired = {c[1] for c in redis.commands if c[0] == "EXPIRE"}
    assert {turns_key, index_key} <= expired


def test_two_appends_in_a_row_both_survive(redis):
    principal = access.principal_for("USR-4")
    chat = conversations.create(principal)["id"]
    stale = conversations.require(principal, chat)
    for question in ("first", "second"):
        conversations.append_turn(principal, chat, question, None, {"answer": question, "citations": []})
    assert [t["question"] for t in store.get_turns("USR-4", chat)] == ["first", "second"]
    assert stale["turn_count"] == 0 and conversations.get(principal, chat)["turn_count"] == 2


def test_redis_eviction_and_isolation(redis, monkeypatch):
    monkeypatch.setattr(store, "MAX_CONVERSATIONS", 2)
    principal, other = access.principal_for("USR-4"), access.principal_for("USR-2")
    ids = [conversations.create(principal)["id"] for _ in range(3)]
    assert [c["id"] for c in conversations.list_for(principal)] == [ids[2], ids[1]]
    assert conversations.list_for(other) == []
    with pytest.raises(Exception, match="is not in your scope"):
        conversations.get(other, ids[2])


def test_redis_lists_with_one_mget_and_drops_expired_entries(redis):
    principal = access.principal_for("USR-4")
    ids = [conversations.create(principal)["id"] for _ in range(3)]
    redis.data.pop(store.conversation_key("USR-4", ids[1]))   # metadata expired, index entry left behind
    redis.commands.clear()
    assert [c["id"] for c in conversations.list_for(principal)] == [ids[2], ids[0]]
    assert [c[0] for c in redis.commands].count("MGET") == 1
    assert not [c for c in redis.commands if c[0] == "GET"]
    assert ids[1] not in redis.data[store.index_key("USR-4")]
