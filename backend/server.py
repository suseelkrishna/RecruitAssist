"""recruiting-pipeline: an MCP server for questions about the recruiting funnel.

It reads recruiting.db (built by generate_data.py) strictly read-only and
offers three tools: pipeline_by_job, stuck_candidates and time_to_fill.

Note: this uses mcp 2.x, where the SDK's FastMCP class is called MCPServer
(same decorator API). Runs over stdio:

    python server.py

Set RECRUITING_DB to point at a different database file.
"""

from __future__ import annotations

import os
import sqlite3
import statistics
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

STAGES = ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer", "Hired"]

DB_PATH = Path(os.environ.get("RECRUITING_DB", Path(__file__).with_name("recruiting.db"))).resolve()

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    name="recruiting-pipeline",
    instructions=(
        "Read-only analytics over a synthetic recruiting database: stage funnels per job, "
        "candidates stuck in a stage, and time to fill. Times are in days."
    ),
)


def connect() -> sqlite3.Connection:
    """Open the database read-only. as_uri() escapes spaces in the path."""
    try:
        con = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        raise ToolError(
            f"Cannot open {DB_PATH} read-only ({exc}). Run generate_data.py first."
        ) from exc
    con.row_factory = sqlite3.Row
    return con


def now_str() -> str:
    # Stage times are stored as local time, so compare against local time.
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def funnel(counts: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    """Turn {stage: (reached, in_stage)} into an ordered list with conversion %."""
    rows = []
    prev = None
    for stage in STAGES:
        reached, in_stage = counts.get(stage, (0, 0))
        rows.append({
            "stage": stage,
            "reached": reached,
            "in_stage": in_stage,
            "conversion_pct": None if prev is None else pct(reached, prev),
        })
        prev = reached
    return rows


@mcp.tool(annotations=READ_ONLY)
def pipeline_by_job(job_id: int | None = None) -> dict[str, Any]:
    """Show the hiring funnel per stage, for one job or for every job.

    Stages, in order: Applied, Recruiter Screen, Technical, Onsite, Offer, Hired.
    For each stage you get:
      - reached: applications that got to this stage at some point
      - in_stage: active applications sitting in this stage right now
      - conversion_pct: reached / reached at the previous stage, as a percent
        (null for Applied, or when the previous stage had nobody)

    Args:
        job_id: The job to report on. Leave out to get every job plus an
            all-jobs total.
    """
    with closing(connect()) as con:
        jobs = {r["job_id"]: r for r in con.execute(
            "SELECT job_id, title, team, filled_at FROM jobs ORDER BY job_id")}
        if job_id is not None and job_id not in jobs:
            raise ToolError(
                f"Unknown job_id {job_id}. Valid job_ids: {', '.join(map(str, jobs))}.")

        rows = con.execute(
            """
            SELECT a.job_id, e.stage,
                   COUNT(*) AS reached,
                   SUM(a.status = 'active' AND e.exited_at IS NULL) AS in_stage
            FROM stage_events e
            JOIN applications a ON a.application_id = e.application_id
            WHERE (:job_id IS NULL OR a.job_id = :job_id)
            GROUP BY a.job_id, e.stage
            """,
            {"job_id": job_id},
        ).fetchall()

    per_job: dict[int, dict[str, tuple[int, int]]] = {}
    total: dict[str, list[int]] = {}
    for r in rows:
        per_job.setdefault(r["job_id"], {})[r["stage"]] = (r["reached"], r["in_stage"])
        t = total.setdefault(r["stage"], [0, 0])
        t[0] += r["reached"]
        t[1] += r["in_stage"]

    ids = [job_id] if job_id is not None else list(jobs)
    result_jobs = [{
        "job_id": jid,
        "title": jobs[jid]["title"],
        "team": jobs[jid]["team"],
        "status": "filled" if jobs[jid]["filled_at"] else "open",
        "stages": funnel(per_job.get(jid, {})),
    } for jid in ids]

    if job_id is not None:
        return result_jobs[0]
    return {
        "all_jobs": funnel({s: (v[0], v[1]) for s, v in total.items()}),
        "jobs": result_jobs,
    }


@mcp.tool(annotations=READ_ONLY)
def stuck_candidates(days: int = 7) -> dict[str, Any]:
    """List active applications that have sat in their current stage too long.

    Returns applications with status 'active' whose current stage was entered
    more than `days` days ago, longest wait first. Each row has candidate_id,
    first_name, application_id, job_id, job_title, stage and days_in_stage
    (one decimal).

    Args:
        days: Minimum number of days in the current stage (default 7).
            Must be 0 or more.
    """
    if days < 0:
        raise ToolError(f"days must be 0 or more, got {days}.")
    as_of = now_str()
    with closing(connect()) as con:
        rows = con.execute(
            """
            SELECT c.candidate_id, c.first_name, a.application_id,
                   j.job_id, j.title AS job_title, a.current_stage AS stage,
                   julianday(:as_of) - julianday(e.entered_at) AS age
            FROM applications a
            JOIN candidates c ON c.candidate_id = a.candidate_id
            JOIN jobs j ON j.job_id = a.job_id
            JOIN stage_events e ON e.application_id = a.application_id
                               AND e.stage = a.current_stage
            WHERE a.status = 'active'
              AND e.exited_at IS NULL
              AND julianday(:as_of) - julianday(e.entered_at) > :days
            ORDER BY age DESC
            """,
            {"as_of": as_of, "days": days},
        ).fetchall()

    candidates = []
    for r in rows:
        row = dict(r)
        row["days_in_stage"] = round(row.pop("age"), 1)
        candidates.append(row)
    return {"days": days, "as_of": as_of, "count": len(candidates), "candidates": candidates}


def fill_stats(fill_days: list[float], open_jobs: int) -> dict[str, Any]:
    return {
        "filled_jobs": len(fill_days),
        "median_days_to_fill": round(statistics.median(fill_days), 1) if fill_days else None,
        "avg_days_to_fill": round(statistics.fmean(fill_days), 1) if fill_days else None,
        "open_jobs": open_jobs,
    }


@mcp.tool(annotations=READ_ONLY)
def time_to_fill(team: str | None = None) -> dict[str, Any]:
    """Report how long filled jobs took to fill, and how many jobs are still open.

    Days to fill = filled_at - opened_at, for jobs that have been filled.
    Median and average are rounded to one decimal and are null when no job has
    been filled yet.

    Args:
        team: Limit to one team, e.g. "Engineering", "Fab Operations",
            "People" or "Business Development" (case-insensitive). Leave out to
            get the overall numbers plus a per-team breakdown.
    """
    with closing(connect()) as con:
        teams = [r["team"] for r in con.execute(
            "SELECT DISTINCT team FROM jobs ORDER BY team")]
        if team is not None:
            match = next((t for t in teams if t.lower() == team.strip().lower()), None)
            if match is None:
                raise ToolError(f"Unknown team {team!r}. Valid teams: {', '.join(teams)}.")
            team = match

        rows = con.execute(
            """
            SELECT team,
                   CASE WHEN filled_at IS NOT NULL
                        THEN julianday(filled_at) - julianday(opened_at) END AS fill_days
            FROM jobs
            WHERE (:team IS NULL OR team = :team)
            """,
            {"team": team},
        ).fetchall()

    fill_days: dict[str, list[float]] = {t: [] for t in teams}
    open_jobs: dict[str, int] = {t: 0 for t in teams}
    for r in rows:
        if r["fill_days"] is None:
            open_jobs[r["team"]] += 1
        else:
            fill_days[r["team"]].append(r["fill_days"])

    if team is not None:
        return {"team": team, **fill_stats(fill_days[team], open_jobs[team])}

    return {
        "overall": fill_stats([d for ds in fill_days.values() for d in ds],
                              sum(open_jobs.values())),
        "by_team": [{"team": t, **fill_stats(fill_days[t], open_jobs[t])} for t in teams],
    }


if __name__ == "__main__":
    mcp.run()
