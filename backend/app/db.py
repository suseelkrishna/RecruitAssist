"""The only module that opens the SQLite database, always read-only.

Every query goes through rows() or one() with parameters, so no caller builds
SQL from user input. Set RECRUITING_DB to point at a different database file.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "recruiting.db"
DB_PATH = Path(os.environ.get("RECRUITING_DB", DEFAULT_DB)).resolve()

Params = Sequence[Any] | Mapping[str, Any]


def connect() -> sqlite3.Connection:
    """Open the database read-only (mode=ro), with rows addressable by column name."""
    con = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def rows(sql: str, params: Params = ()) -> list[dict[str, Any]]:
    """Run one parameterized query and return every row as a plain dict."""
    with closing(connect()) as con:
        return [dict(r) for r in con.execute(sql, params)]


def one(sql: str, params: Params = ()) -> dict[str, Any] | None:
    """Run one parameterized query and return the first row, or None."""
    found = rows(sql, params)
    return found[0] if found else None


def meta_as_of() -> str:
    """The as_of time the data was generated for (UTC), from the meta table."""
    return one("SELECT value FROM meta WHERE key = 'as_of'")["value"]


def id_list(ids: Iterable[str]) -> str:
    """Encode IDs as a JSON array for SQL of the form `x IN (SELECT value FROM json_each(?))`."""
    return json.dumps(sorted(ids))
