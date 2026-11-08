"""Load settings from backend/.env into the environment for local runs.

Hosted deployments set real environment variables, and those always win: a
value already in the environment is never replaced. The file is ignored by git.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Read KEY=VALUE lines from path into os.environ, skipping blanks, comments, and keys already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)
