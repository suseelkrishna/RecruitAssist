"""Shared pytest fixtures: a read-only connection to the committed database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "recruiting.db"


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
