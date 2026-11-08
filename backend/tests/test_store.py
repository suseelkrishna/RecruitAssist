"""The writable store: assignments, the append-only change log, scoped change lists, and rate limits.

Each behavior runs against the in-memory backend and against a fake Upstash
REST endpoint that keeps Redis data in a dict.
"""

from __future__ import annotations

import pytest

from app import access, store


class FakeRedis:
    """Just enough Redis for the store: hashes, lists, counters, expiry, and PING."""

    def __init__(self):
        self.data: dict[str, object] = {}
        self.commands: list[tuple] = []

    def __call__(self, *command):
        """Run one command the way the Upstash REST API would, returning its result."""
        self.commands.append(command)
        name, *args = command
        if name == "HSET":
            self.data.setdefault(args[0], {})[args[1]] = args[2]
            return 1
        if name == "HGETALL":
            return [x for pair in self.data.get(args[0], {}).items() for x in pair]
        if name == "INCR":
            self.data[args[0]] = int(self.data.get(args[0], 0)) + 1
            return self.data[args[0]]
        if name == "RPUSH":
            self.data.setdefault(args[0], []).append(args[1])
            return len(self.data[args[0]])
        if name == "LRANGE":
            return list(self.data.get(args[0], []))
        if name == "EXPIRE":
            return 1
        if name == "PING":
            return "PONG"
        raise AssertionError(f"unexpected command {name}")


@pytest.fixture(params=["memory", "redis"])
def backend(request, monkeypatch):
    """Run the test once per store backend."""
    if request.param == "redis":
        monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example.com")
        monkeypatch.setattr(store, "redis", FakeRedis())
    else:
        monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    return request.param


def test_assignment_overrides_latest_wins(backend):
    assert store.get_assignment_overrides() == {}
    store.set_assignment("JOB-1", "USR-5", "USR-1")
    store.set_assignment("JOB-1", "USR-6", "USR-2")
    store.set_assignment("JOB-2", "USR-4", "USR-1")
    assert store.get_assignment_overrides() == {"JOB-1": "USR-6", "JOB-2": "USR-4"}


def test_changes_get_sequential_ids_and_copies(backend):
    first = store.append_change({"type": "reassignment", "job_id": "JOB-1", "user_id": "USR-1"})
    second = store.append_change({"type": "ask", "job_id": None, "user_id": "USR-4"})
    assert (first["change_id"], second["change_id"]) == ("CHG-001", "CHG-002")
    assert first["at"].endswith("Z")
    listed = store.all_changes()
    listed[0]["job_id"] = "JOB-9"
    assert store.all_changes()[0]["job_id"] == "JOB-1"


def test_store_has_no_way_to_edit_or_delete_changes():
    public = {name for name in dir(store) if not name.startswith("_")}
    assert not {n for n in public if any(w in n for w in ("delete", "remove", "update", "edit", "pop"))}


def test_list_changes_is_scoped_by_role(backend):
    store.append_change({"type": "reassignment", "job_id": "JOB-1", "user_id": "USR-1",
                         "from_recruiter_user_id": "USR-4", "to_recruiter_user_id": "USR-5"})
    store.append_change({"type": "ask", "job_id": "JOB-3", "user_id": "USR-6"})
    store.append_change({"type": "ask", "job_id": None, "user_id": "USR-4"})
    ids = lambda user: [c["change_id"] for c in store.list_changes(access.principal_for(user))]
    assert ids("USR-1") == ["CHG-003", "CHG-002", "CHG-001"]   # admin: everything, newest first
    assert ids("USR-2") == ["CHG-001"]                          # manager of TEAM-1 and TEAM-2
    assert ids("USR-3") == ["CHG-002"]                          # manager of TEAM-3 and TEAM-4
    assert ids("USR-4") == ["CHG-003", "CHG-001"]               # own question, job moved away
    assert ids("USR-6") == ["CHG-002"]                          # own job


def test_rate_limit_counts_hits_per_key(backend):
    assert [store.hit_rate_limit("ip:a", 2, 3600) for _ in range(3)] == [False, False, True]
    assert store.hit_rate_limit("ip:b", 2, 3600) is False


def test_rate_limit_window_resets(backend, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(store.time, "time", lambda: now[0])
    assert [store.hit_rate_limit("k", 1, 60) for _ in range(2)] == [False, True]
    now[0] += 60
    assert store.hit_rate_limit("k", 1, 60) is False


def test_ping_reports_the_backend(backend):
    assert store.ping()["backend"] == backend
    assert store.ping()["status"] == "ok"


def test_redis_rate_limit_sets_expiry_once(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://redis.example.com")
    monkeypatch.setattr(store, "redis", fake)
    store.hit_rate_limit("k", 5, 60)
    store.hit_rate_limit("k", 5, 60)
    assert [c[0] for c in fake.commands] == ["INCR", "EXPIRE", "INCR"]
