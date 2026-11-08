"""Recorded answers served when live answers are rate limited or not configured.

data/recordings.json holds full agent results saved with the CLI's --record flag.
A recording matches when the question (ignoring case, spacing, and punctuation),
the user, the selected job, and the user's current job scope are all the same, so
a recording never shows an answer computed for a different scope, for example
after a job was reassigned.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RECORDINGS = Path(__file__).resolve().parent.parent.parent / "data" / "recordings.json"


def normalize(question: str) -> str:
    """The question lowercased with punctuation removed and spaces collapsed."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", question.lower()).split())


def load(path: Path | None = None) -> list[dict[str, Any]]:
    """Every recording in the file, or an empty list when there is no file."""
    path = path or RECORDINGS
    if not path.exists():
        return []
    return json.loads(path.read_text())["recordings"]


def find(question: str, user_id: str, job_id: str | None, scope: list[str],
         path: Path | None = None) -> dict[str, Any] | None:
    """The recorded result for this question, user, job, and scope, marked source: recording, or None."""
    key = normalize(question)
    for rec in load(path):
        if (normalize(rec["question"]) == key and rec["user_id"] == user_id
                and rec.get("job_id") == job_id and rec["scope"] == sorted(scope)):
            return {**rec["result"], "source": "recording", "recorded_at": rec["recorded_at"]}
    return None


def save(question: str, user_id: str, job_id: str | None, scope: list[str], result: dict[str, Any],
         recorded_at: str, path: Path | None = None) -> None:
    """Add or replace the recording for this question, user, and job."""
    key = (normalize(question), user_id, job_id)
    kept = [r for r in load(path) if (normalize(r["question"]), r["user_id"], r.get("job_id")) != key]
    kept.append({"question": question, "user_id": user_id, "job_id": job_id,
                 "scope": sorted(scope), "recorded_at": recorded_at, "result": result})
    kept.sort(key=lambda r: (r["user_id"], r.get("job_id") or "", normalize(r["question"])))
    (path or RECORDINGS).write_text(json.dumps({"recordings": kept}, indent=1) + "\n")
