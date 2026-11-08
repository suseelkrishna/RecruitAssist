"""Stage funnels: how many applications reach each stage, and where they drop out.

An application "reached" a stage when it has a stage_events row for it. A
stage's pass rate is advanced exits divided by all exits, so applications still
sitting in the stage do not count against it.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app import db
from app.access import Principal
from app.logic.common import (IN_SCOPE, STAGES, days_between, median, pct, require_job,
                              resolve_as_of, scope_params)

EXIT_TYPES = ["advanced", "rejected", "withdrawn", "offer_declined"]


def stage_events(principal: Principal, job_ids: list[str] | None, as_of: str,
                 applied_from: str | None = None, applied_to: str | None = None) -> list[dict[str, Any]]:
    """Stage events for in-scope jobs (optionally only job_ids), as they stood at as_of.

    An exit after as_of is treated as not having happened yet. applied_from and
    applied_to limit the applications by applied_at, inclusive.
    """
    selected = None if job_ids is None else db.id_list(job_ids)
    return db.rows(f"""
        SELECT e.event_id, e.application_id, e.stage, e.entered_at,
               CASE WHEN e.exited_at <= :as_of THEN e.exited_at END AS exited_at,
               CASE WHEN e.exited_at <= :as_of THEN e.exit_type END AS exit_type,
               a.job_id, a.status, a.outcome_reason, c.source
        FROM stage_events e
        JOIN applications a ON a.application_id = e.application_id
        JOIN candidates c ON c.candidate_id = a.candidate_id
        WHERE a.job_id {IN_SCOPE}
          AND (:selected IS NULL OR a.job_id IN (SELECT value FROM json_each(:selected)))
          AND e.entered_at <= :as_of
          AND (:applied_from IS NULL OR a.applied_at >= :applied_from)
          AND (:applied_to IS NULL OR a.applied_at <= :applied_to)
        ORDER BY e.event_id""",
        scope_params(principal, selected=selected, as_of=as_of,
                     applied_from=applied_from, applied_to=applied_to))


def stage_counts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per stage, in order: reached, in_stage, exits by type, and conversion from the stage before."""
    result = []
    previous = None
    for stage in STAGES:
        rows = [e for e in events if e["stage"] == stage]
        exits = Counter(e["exit_type"] for e in rows)
        reached = len(rows)
        result.append({
            "stage": stage,
            "reached": reached,
            "in_stage": sum(1 for e in rows if e["exited_at"] is None),
            "rejected": exits["rejected"],
            "withdrawn": exits["withdrawn"],
            "offer_declined": exits["offer_declined"],
            "conversion_pct": None if previous is None else pct(reached, previous),
        })
        previous = reached
    return result


def pipeline_by_job(principal: Principal, job_id: str | None = None,
                    as_of: str | None = None) -> dict[str, Any]:
    """The funnel for one in-scope job, or for every in-scope job plus a total."""
    as_of = resolve_as_of(as_of)
    if job_id is not None:
        job = require_job(principal, job_id)
        return {"as_of": as_of, **job_summary(job),
                "stages": stage_counts(stage_events(principal, [job_id], as_of))}

    jobs = db.rows(f"""SELECT j.job_id, j.title, j.status, t.name AS team
                       FROM jobs j JOIN teams t ON t.team_id = j.team_id
                       WHERE j.job_id {IN_SCOPE} ORDER BY j.job_id""", scope_params(principal))
    events = stage_events(principal, None, as_of)
    return {
        "as_of": as_of,
        "all_jobs": stage_counts(events),
        "jobs": [{**job_summary(j), "stages": stage_counts([e for e in events if e["job_id"] == j["job_id"]])}
                 for j in jobs],
    }


def job_summary(job: dict[str, Any]) -> dict[str, Any]:
    """The identifying fields of a job row."""
    return {"job_id": job["job_id"], "title": job["title"], "team": job["team"], "status": job["status"]}


def funnel_dropoff(principal: Principal, job_id: str, as_of: str | None = None) -> dict[str, Any]:
    """Where a job's candidates leave the funnel, why, and how that compares with other roles in scope."""
    job = require_job(principal, job_id)
    as_of = resolve_as_of(as_of)
    events = stage_events(principal, None, as_of)
    mine = [e for e in events if e["job_id"] == job_id]
    others = [e for e in events if e["job_id"] != job_id]
    waits = waits_after_last_interview(principal, job_id, as_of)

    stages = []
    for stage in STAGES:
        rows = [e for e in mine if e["stage"] == stage]
        exited = [e for e in rows if e["exit_type"] is not None]
        lost = [e for e in exited if e["exit_type"] != "advanced"]
        reasons = Counter(e["outcome_reason"] for e in lost)
        entry = {
            "stage": stage,
            "entered": len(rows),
            **{t: sum(1 for e in exited if e["exit_type"] == t) for t in EXIT_TYPES},
            "still_active": sum(1 for e in rows if e["exited_at"] is None),
            "pass_rate_pct": pass_rate(rows),
            "median_days_before_exit": median([days_between(e["entered_at"], e["exited_at"]) for e in exited]),
            "top_outcome_reasons": [
                {"reason": reason, "count": n,
                 "application_ids": sorted(e["application_id"] for e in lost if e["outcome_reason"] == reason)}
                for reason, n in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
        }
        if stage in waits:
            entry["median_days_after_last_interview"] = median(list(waits[stage].values()))
            entry["applications_with_completed_interview"] = len(waits[stage])
        stages.append(entry)

    comparison = [{"stage": s, "this_role_pass_rate_pct": pass_rate([e for e in mine if e["stage"] == s]),
                   "other_roles_pass_rate_pct": pass_rate([e for e in others if e["stage"] == s])}
                  for s in STAGES[:-1]]
    return {
        "job_id": job_id,
        "title": job["title"],
        "as_of": as_of,
        "days_open": round(days_between(job["opened_at"], job["closed_at"] or as_of), 1),
        "stages": stages,
        "comparison_with_other_roles": comparison,
        "other_roles_in_scope": sorted({e["job_id"] for e in others}),
        "leaks": rank_leaks(mine, others),
        "warnings": [] if others else ["No other roles are in your scope to compare with."],
        "missing": [] if mine else [f"{job_id} has no applications yet."],
    }


def pass_rate(rows: list[dict[str, Any]]) -> float | None:
    """Advanced exits as a percent of all exits from a stage, or None with no exits."""
    exited = [e for e in rows if e["exit_type"] is not None]
    return pct(sum(1 for e in exited if e["exit_type"] == "advanced"), len(exited))


def rank_leaks(mine: list[dict[str, Any]], others: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stage transitions ordered from lowest pass rate to highest, with the applications lost at each."""
    leaks = []
    for index, stage in enumerate(STAGES[:-1]):
        rows = [e for e in mine if e["stage"] == stage]
        exited = [e for e in rows if e["exit_type"] is not None]
        if not exited:
            continue
        lost = [e for e in exited if e["exit_type"] != "advanced"]
        sources = sorted({e["source"] for e in exited})
        leaks.append({
            "transition": f"{stage} to {STAGES[index + 1]}",
            "stage": stage,
            "pass_rate_pct": pass_rate(rows),
            "exited": len(exited),
            "lost": len(lost),
            "other_roles_pass_rate_pct": pass_rate([e for e in others if e["stage"] == stage]),
            "by_source": [{"source": src,
                           "exited": sum(1 for e in exited if e["source"] == src),
                           "pass_rate_pct": pass_rate([e for e in exited if e["source"] == src])}
                          for src in sources],
            "evidence": sorted(e["application_id"] for e in lost),
        })
    leaks.sort(key=lambda leak: (leak["pass_rate_pct"], STAGES.index(leak["stage"])))
    return [{"rank": rank, **leak} for rank, leak in enumerate(leaks, start=1)]


def waits_after_last_interview(principal: Principal, job_id: str, as_of: str) -> dict[str, dict[str, float]]:
    """Days from each application's last completed Technical or Onsite interview to leaving that
    stage, or to as_of when still there. Keyed by stage, then application_id."""
    found = db.rows(f"""
        SELECT i.stage, i.application_id, MAX(i.completed_at) AS last_done,
               CASE WHEN e.exited_at <= :as_of THEN e.exited_at ELSE :as_of END AS until
        FROM interviews i
        JOIN applications a ON a.application_id = i.application_id
        JOIN stage_events e ON e.application_id = i.application_id AND e.stage = i.stage
        WHERE a.job_id = :job AND a.job_id {IN_SCOPE}
          AND i.completed_at IS NOT NULL AND i.completed_at <= :as_of
        GROUP BY i.stage, i.application_id""", scope_params(principal, job=job_id, as_of=as_of))
    waits: dict[str, dict[str, float]] = {}
    for r in found:
        waits.setdefault(r["stage"], {})[r["application_id"]] = days_between(r["last_done"], r["until"])
    return waits
