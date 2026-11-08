"""Shared pytest fixtures: the committed database, the eval answer key, and small built databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

import tiny
from app import db as app_db
from app import store

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "recruiting.db"
QUESTIONS = Path(__file__).resolve().parent.parent / "evals" / "questions.yaml"


@pytest.fixture(scope="session")
def db():
    """The committed data/recruiting.db, opened read-only."""
    if not DB_PATH.exists():
        pytest.fail(f"{DB_PATH} not found. Run: uv run python data/generate.py")
    con = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    yield con
    con.close()


@pytest.fixture(scope="session")
def as_of(db) -> str:
    """The as_of time stored in the database's meta table."""
    return db.execute("SELECT value FROM meta WHERE key = 'as_of'").fetchone()[0]


@pytest.fixture(scope="session")
def answers() -> dict:
    """Expected answers by question id, computed by SQL in evals/expected.py."""
    return {q["id"]: q["expected"] for q in yaml.safe_load(QUESTIONS.read_text())["questions"]}


@pytest.fixture(autouse=True)
def clean_store():
    """Every test starts from the seed recruiter assignments."""
    store.clear()
    yield
    store.clear()


@pytest.fixture
def use_db(tmp_path, monkeypatch):
    """Return a function that builds a database from tiny.py data and points the app at it."""
    def use(data):
        path = tiny.build(tmp_path / "tiny.db", data)
        monkeypatch.setattr(app_db, "DB_PATH", path)
        return path
    return use
