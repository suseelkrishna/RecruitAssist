"""Dashboard metrics. Each takes the principal and the same filters, and returns its numbers
plus a one-line takeaway built from those numbers by a fixed template.

Filters: team_id, job_id, recruiter_user_id (the job's current recruiter), and
date_from / date_to (YYYY-MM-DD or a full UTC timestamp, inclusive). The date
range limits applications by applied_at. Job-level numbers (open jobs, days
open, time to fill) use every job that passes the other filters. Application
status (active, hired, withdrawn) is the status stored in the database.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app import db
from app.access import Principal, current_recruiters
from app.logic.common import (IN_SCOPE, days_between, format_ts, median, parse_ts, pct, plural,
                              require_job, resolve_as_of, scope_params)
from app.logic.funnel import stage_counts, stage_events
from app.logic.tasks import pending_tasks

FILTERS = ["team_id", "job_id", "recruiter_user_id", "date_from", "date_to", "as_of"]


def jobs_in_view(principal: Principal, team_id: str | None, job_id: str | None,
                 recruiter_user_id: str | None) -> list[dict[str, Any]]:
    """In-scope job rows that pass the team, job, and recruiter filters."""
    if job_id is not None:
        require_job(principal, job_id)
    teams = [t["team_id"] for t in db.rows("SELECT team_id FROM teams ORDER BY team_id")]
    if team_id is not None and team_id not in teams:
        raise ToolError(f"Unknown team_id {team_id!r}. Valid teams: {', '.join(teams)}.")
    users = [u["user_id"] for u in db.rows("SELECT user_id FROM users ORDER BY user_id")]
    if recruiter_user_id is not None and recruiter_user_id not in users:
        raise ToolError(f"Unknown recruiter_user_id {recruiter_user_id!r}. Valid users: {', '.join(users)}.")
    jobs = db.rows(f"""SELECT j.*, t.name AS team FROM jobs j JOIN teams t ON t.team_id = j.team_id
                       WHERE j.job_id {IN_SCOPE} AND (:team IS NULL OR j.team_id = :team)
                         AND (:job IS NULL OR j.job_id = :job)
                       ORDER BY j.job_id""", scope_params(principal, team=team_id, job=job_id))
    recruiters = current_recruiters()
    for job in jobs:
        job["recruiter_user_id"] = recruiters.get(job["job_id"])
    return [j for j in jobs if recruiter_user_id is None or j["recruiter_user_id"] == recruiter_user_id]


def date_bounds(date_from: str | None, date_to: str | None) -> tuple[str | None, str | None]:
    """Turn YYYY-MM-DD bounds into inclusive UTC timestamps. Full timestamps pass through."""
    start = f"{date_from}T00:00:00Z" if date_from and len(date_from) == 10 else date_from
    end = f"{date_to}T23:59:59Z" if date_to and len(date_to) == 10 else date_to
    for value in (start, end):
        if value is not None:
            try:
                parse_ts(value)
            except ValueError:
                raise ToolError(f"Dates must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ, got {value!r}.") from None
    return start, end


def view(principal: Principal, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str | None, str | None]:
    """Jobs in view, as_of, and the applied_at bounds for one metric call."""
    unknown = sorted(set(filters) - set(FILTERS))
    if unknown:
        raise ToolError(f"Unknown filters {unknown}. Valid filters: {', '.join(FILTERS)}.")
    jobs = jobs_in_view(principal, filters.get("team_id"), filters.get("job_id"),
                        filters.get("recruiter_user_id"))
    start, end = date_bounds(filters.get("date_from"), filters.get("date_to"))
    return jobs, resolve_as_of(filters.get("as_of")), start, end


def applications(principal: Principal, job_ids: list[str], as_of: str, start: str | None,
                 end: str | None) -> list[dict[str, Any]]:
    """Applications on the given in-scope jobs, applied by as_of and within the date range."""
    return db.rows(f"""
        SELECT a.application_id, a.job_id, a.applied_at, a.current_stage, a.status,
               a.outcome_reason, a.outcome_at, c.source,
               (SELECT h.entered_at FROM stage_events h
                WHERE h.application_id = a.application_id AND h.stage = 'Hired') AS hired_at,
               EXISTS (SELECT 1 FROM stage_events o WHERE o.application_id = a.application_id
                       AND o.stage = 'Onsite' AND o.entered_at <= :as_of) AS reached_onsite,
               EXISTS (SELECT 1 FROM stage_events f WHERE f.application_id = a.application_id
                       AND f.stage = 'Offer' AND f.entered_at <= :as_of) AS reached_offer
        FROM applications a JOIN candidates c ON c.candidate_id = a.candidate_id
        WHERE a.job_id {IN_SCOPE} AND a.job_id IN (SELECT value FROM json_each(:jobs))
          AND a.applied_at <= :as_of
          AND (:start IS NULL OR a.applied_at >= :start) AND (:end IS NULL OR a.applied_at <= :end)
        ORDER BY a.application_id""",
        scope_params(principal, jobs=db.id_list(job_ids), as_of=as_of, start=start, end=end))


def ids(jobs: list[dict[str, Any]]) -> list[str]:
    """The job_id of each job row."""
    return [j["job_id"] for j in jobs]


def kpis(principal: Principal, **filters: Any) -> dict[str, Any]:
    """Headline numbers: open jobs, active candidates, new applicants (7 days), offers out,
    median time to fill for filled roles, and overdue tasks."""
    jobs, as_of, start, end = view(principal, filters)
    apps = applications(principal, ids(jobs), as_of, start, end)
    week_ago = format_ts(parse_ts(as_of) - timedelta(days=7))
    filled = [days_between(j["opened_at"], j["closed_at"]) for j in jobs
              if j["status"] == "filled" and j["closed_at"] <= as_of]
    tasks = pending_tasks(principal, as_of=as_of)["tasks"]
    in_view = set(ids(jobs))
    result = {
        "open_jobs": sum(1 for j in jobs if j["status"] == "open"),
        "active_candidates": sum(1 for a in apps if a["status"] == "active"),
        "new_applicants_7d": sum(1 for a in apps if a["applied_at"] > week_ago),
        "offers_out": sum(1 for a in apps if a["status"] == "active" and a["current_stage"] == "Offer"),
        "median_days_to_fill": median(filled),
        "filled_jobs": len(filled),
        "overdue_tasks": sum(1 for t in tasks if t["status"] == "overdue" and t["job_id"] in in_view),
    }
    fill = "no filled roles yet" if result["median_days_to_fill"] is None else \
        f"a median of {result['median_days_to_fill']} days to fill"
    result["takeaway"] = (f"{plural(result['open_jobs'], 'open job')}, "
                          f"{plural(result['active_candidates'], 'active candidate')}, "
                          f"{plural(result['offers_out'], 'offer')} out, "
                          f"{plural(result['overdue_tasks'], 'overdue task')}, and {fill}.")
    return {"metric": "kpis", "as_of": as_of, **result}


def funnel(principal: Principal, **filters: Any) -> dict[str, Any]:
    """Stage counts and conversion across the jobs in view."""
    jobs, as_of, start, end = view(principal, filters)
    stages = stage_counts(stage_events(principal, ids(jobs), as_of, start, end))
    worst = min((s for s in stages[1:] if s["conversion_pct"] is not None),
                key=lambda s: s["conversion_pct"], default=None)
    takeaway = ("No applications match these filters." if not stages[0]["reached"] else
                f"{plural(stages[0]['reached'], 'application')}; the lowest conversion is into {worst['stage']} "
                f"at {worst['conversion_pct']}%.")
    return {"metric": "funnel", "as_of": as_of, "stages": stages, "takeaway": takeaway}


def days_open_vs_target(principal: Principal, **filters: Any) -> dict[str, Any]:
    """For each open job in view: days open, target days, and days over target."""
    jobs, as_of, _, _ = view(principal, filters)
    rows = []
    for j in jobs:
        if j["status"] != "open":
            continue
        days_open = round(days_between(j["opened_at"], as_of), 1)
        rows.append({"job_id": j["job_id"], "title": j["title"], "days_open": days_open,
                     "target_days": j["target_fill_days"],
                     "days_over_target": round(days_open - j["target_fill_days"], 1),
                     "over_target": days_open > j["target_fill_days"]})
    over = [r for r in rows if r["over_target"]]
    takeaway = (f"{len(over)} of {plural(len(rows), 'open job')} past target"
                + (f"; {max(over, key=lambda r: r['days_over_target'])['job_id']} is furthest over." if over else "."))
    return {"metric": "days_open_vs_target", "as_of": as_of, "jobs": rows, "takeaway": takeaway}


def applicants_over_time(principal: Principal, by_source: bool = False, **filters: Any) -> dict[str, Any]:
    """New applications per week (weeks start on Monday), optionally split by source."""
    jobs, as_of, start, end = view(principal, filters)
    counts: Counter[tuple[str, str | None]] = Counter()
    for a in applications(principal, ids(jobs), as_of, start, end):
        day = parse_ts(a["applied_at"])
        week = (day - timedelta(days=day.weekday())).strftime("%Y-%m-%d")
        counts[(week, a["source"] if by_source else None)] += 1
    weeks = [{"week_start": w, **({"source": s} if by_source else {}), "applicants": n}
             for (w, s), n in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))]
    totals = Counter()
    for w in weeks:
        totals[w["week_start"]] += w["applicants"]
    busiest = max(totals.items(), key=lambda kv: (kv[1], kv[0]), default=None)
    takeaway = ("No applications match these filters." if busiest is None else
                f"{plural(sum(totals.values()), 'application')} over {plural(len(totals), 'week')}; the busiest week "
                f"started {busiest[0]} with {busiest[1]}.")
    return {"metric": "applicants_over_time", "as_of": as_of, "by_source": by_source,
            "weeks": weeks, "takeaway": takeaway}


def source_quality(principal: Principal, **filters: Any) -> dict[str, Any]:
    """Per source: applicants, share reaching Onsite, hires, and median days from application to hire."""
    jobs, as_of, start, end = view(principal, filters)
    apps = applications(principal, ids(jobs), as_of, start, end)
    rows = []
    for source in sorted({a["source"] for a in apps}):
        mine = [a for a in apps if a["source"] == source]
        hires = [a for a in mine if a["hired_at"] is not None and a["hired_at"] <= as_of]
        rows.append({"source": source, "applicants": len(mine),
                     "reached_onsite": sum(a["reached_onsite"] for a in mine),
                     "onsite_rate_pct": pct(sum(a["reached_onsite"] for a in mine), len(mine)),
                     "hires": len(hires),
                     "median_days_to_hire": median([days_between(a["applied_at"], a["hired_at"]) for a in hires]),
                     "evidence": [a["application_id"] for a in hires]})
    best = max(rows, key=lambda r: (r["onsite_rate_pct"] or 0, r["source"]), default=None)
    takeaway = ("No applications match these filters." if best is None else
                f"{best['source']} has the highest share reaching Onsite at {best['onsite_rate_pct']}% "
                f"of {plural(best['applicants'], 'applicant')}.")
    return {"metric": "source_quality", "as_of": as_of, "sources": rows, "takeaway": takeaway}


def time_in_stage(principal: Principal, **filters: Any) -> dict[str, Any]:
    """Median days spent in each stage, over stays that have ended."""
    jobs, as_of, start, end = view(principal, filters)
    events = [e for e in stage_events(principal, ids(jobs), as_of, start, end) if e["exited_at"]]
    stages = []
    for stage in ["Applied", "Recruiter Screen", "Technical", "Onsite", "Offer"]:
        stays = [days_between(e["entered_at"], e["exited_at"]) for e in events if e["stage"] == stage]
        stages.append({"stage": stage, "median_days": median(stays), "stays": len(stays)})
    slowest = max((s for s in stages if s["median_days"] is not None), key=lambda s: s["median_days"], default=None)
    takeaway = ("No completed stage stays match these filters." if slowest is None else
                f"Candidates spend longest in {slowest['stage']}, a median of {slowest['median_days']} days.")
    return {"metric": "time_in_stage", "as_of": as_of, "stages": stages, "takeaway": takeaway}


def withdrawal_reasons(principal: Principal, **filters: Any) -> dict[str, Any]:
    """Why candidates withdrew, most common first, with the applications behind each reason."""
    jobs, as_of, start, end = view(principal, filters)
    withdrawn = [a for a in applications(principal, ids(jobs), as_of, start, end)
                 if a["status"] == "withdrawn" and a["outcome_at"] <= as_of]
    reasons = Counter(a["outcome_reason"] for a in withdrawn)
    rows = [{"reason": r, "count": n,
             "evidence": [a["application_id"] for a in withdrawn if a["outcome_reason"] == r]}
            for r, n in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))]
    takeaway = ("No withdrawals match these filters." if not rows else
                f"{plural(len(withdrawn), 'withdrawal')}; the most common reason is \"{rows[0]['reason']}\" "
                f"({rows[0]['count']}).")
    return {"metric": "withdrawal_reasons", "as_of": as_of, "reasons": rows, "takeaway": takeaway}


def recruiter_load(principal: Principal, **filters: Any) -> dict[str, Any]:
    """Per recruiter: open jobs, active candidates, and overdue tasks. admin and hr_manager only."""
    if principal.role not in ("admin", "hr_manager"):
        raise ToolError("recruiter_load is available to the admin and hr_manager roles only.")
    jobs, as_of, start, end = view(principal, filters)
    apps = applications(principal, ids(jobs), as_of, start, end)
    tasks = [t for t in pending_tasks(principal, as_of=as_of)["tasks"] if t["status"] == "overdue"]
    users = {u["user_id"]: u["name"] for u in db.rows("SELECT user_id, name FROM users")}
    rows = []
    for recruiter in sorted({j["recruiter_user_id"] for j in jobs}):
        mine = [j["job_id"] for j in jobs if j["recruiter_user_id"] == recruiter]
        rows.append({"recruiter_user_id": recruiter, "name": users.get(recruiter),
                     "open_jobs": sum(1 for j in jobs if j["job_id"] in mine and j["status"] == "open"),
                     "active_candidates": sum(1 for a in apps if a["job_id"] in mine and a["status"] == "active"),
                     "overdue_tasks": sum(1 for t in tasks if t["job_id"] in mine),
                     "job_ids": mine})
    busiest = max(rows, key=lambda r: (r["active_candidates"], r["recruiter_user_id"]), default=None)
    takeaway = ("No recruiters match these filters." if busiest is None else
                f"{busiest['name']} carries the most active candidates ({busiest['active_candidates']}) "
                f"across {plural(busiest['open_jobs'], 'open job')}.")
    return {"metric": "recruiter_load", "as_of": as_of, "recruiters": rows, "takeaway": takeaway}


def offer_acceptance(principal: Principal, **filters: Any) -> dict[str, Any]:
    """Offers made, accepted, declined, withdrawn, and pending, with the acceptance rate of decided offers."""
    jobs, as_of, start, end = view(principal, filters)
    offers = [a for a in applications(principal, ids(jobs), as_of, start, end) if a["reached_offer"]]

    def decided(status: str) -> list[str]:
        """Application IDs of offers that ended with this status by as_of."""
        return [a["application_id"] for a in offers if a["status"] == status and a["outcome_at"] <= as_of]

    accepted, declined, withdrawn = decided("hired"), decided("offer_declined"), decided("withdrawn")
    pending = [a["application_id"] for a in offers
               if a["application_id"] not in accepted + declined + withdrawn]
    rate = pct(len(accepted), len(accepted) + len(declined) + len(withdrawn))
    takeaway = ("No offers match these filters." if not offers else
                f"{len(accepted)} of {plural(len(accepted) + len(declined) + len(withdrawn), 'decided offer')} "
                f"accepted ({rate}%), with {len(pending)} still pending.")
    return {"metric": "offer_acceptance", "as_of": as_of, "offers": len(offers),
            "accepted": accepted, "declined": declined, "withdrawn": withdrawn, "pending": pending,
            "acceptance_rate_pct": rate, "takeaway": takeaway}
