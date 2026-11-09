"""Rank a job's active applications by a fixed, published rubric.

score = 50% scorecards + 30% must-have match + 20% furthest stage reached.
Must-have match comes from interviewer ratings on scorecards, not from CV text,
because CV text is written by the candidate and is treated as untrusted. Every
component lists the evidence IDs it came from, and an application whose
evidence is incomplete is still ranked but flagged.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from app import db
from app.access import Principal
from app.logic.common import IN_SCOPE, STAGES, require_job, resolve_as_of, scope_params
from app.logic.sources import degraded_sources

RUBRIC_VERSION = "v1"
WEIGHTS = {"scorecards": 0.5, "must_have": 0.3, "stage": 0.2}
POINTS = {"strong_yes": 4, "yes": 3, "no": 2, "strong_no": 1}
MAX_TOP_N = 50

RUBRIC = {
    "rubric_version": RUBRIC_VERSION,
    "weights": WEIGHTS,
    "components": {
        "scorecards": "Average scorecard points (strong_yes 4, yes 3, no 2, strong_no 1), "
                      "scaled to 0..1 as (average - 1) / 3. 0 when there are no scorecards.",
        "must_have": "Interviewer ratings (1 to 4) of each must-have skill on the scorecards, "
                     "averaged per skill, scaled to 0..1 as (rating - 1) / 3, then averaged over "
                     "the job's must-haves. A must-have no scorecard rated counts as 0. "
                     "CV text is candidate-supplied and does not affect the score.",
        "stage": "Furthest stage reached, as its position from Applied (0) to Hired (1).",
    },
    "pool": "Active applications only.",
    "ties": "Equal scores are ordered by application_id.",
    "incomplete_evidence": "Set when an interview was completed but has no scorecard, "
                           "or when no scorecard exists yet.",
}


def score_candidates(principal: Principal, job_id: str, top_n: int = 3,
                     as_of: str | None = None) -> dict[str, Any]:
    """The top_n active applications for a job, best first, with a per-component breakdown."""
    job = require_job(principal, job_id)
    if not 1 <= top_n <= MAX_TOP_N:
        raise ToolError(f"top_n must be between 1 and {MAX_TOP_N}, got {top_n}.")
    as_of = resolve_as_of(as_of)
    params = scope_params(principal, job=job_id, as_of=as_of)
    apps = db.rows(f"""
        SELECT a.application_id, a.candidate_id, c.full_name, a.current_stage
        FROM applications a JOIN candidates c ON c.candidate_id = a.candidate_id
        WHERE a.job_id = :job AND a.job_id {IN_SCOPE}
          AND a.status = 'active' AND a.applied_at <= :as_of
        ORDER BY a.application_id""", params)
    interviews = db.rows(f"""
        SELECT i.application_id, i.interview_id, i.stage, i.completed_at,
               s.scorecard_id, s.overall, s.ratings_json
        FROM interviews i
        JOIN applications a ON a.application_id = i.application_id
        LEFT JOIN scorecards s ON s.interview_id = i.interview_id AND s.submitted_at <= :as_of
        WHERE a.job_id = :job AND a.job_id {IN_SCOPE}
          AND i.completed_at IS NOT NULL AND i.completed_at <= :as_of
        ORDER BY i.interview_id""", params)
    events = db.rows(f"""
        SELECT e.application_id, e.event_id, e.stage
        FROM stage_events e JOIN applications a ON a.application_id = e.application_id
        WHERE a.job_id = :job AND a.job_id {IN_SCOPE} AND e.entered_at <= :as_of""", params)

    must_haves = json.loads(job["must_have_json"])
    scored = [score_one(app, must_haves,
                        [i for i in interviews if i["application_id"] == app["application_id"]],
                        [e for e in events if e["application_id"] == app["application_id"]])
              for app in apps]
    scored.sort(key=lambda s: (-s["score"], s["application_id"]))
    scored = [{"rank": rank, **entry} for rank, entry in enumerate(scored, start=1)]
    top = scored[:top_n]

    degraded = degraded_sources({"applications and stages", "scorecards"}, as_of)
    return {
        "job_id": job_id,
        "title": job["title"],
        "rubric_version": RUBRIC_VERSION,
        "weights": WEIGHTS,
        "as_of": as_of,
        "pool_size": len(scored),
        "ranked": top,
        "warnings": [f"{s['application_id']} has incomplete evidence: {'; '.join(s['missing'])}"
                     for s in top if s["incomplete_evidence"]] + [d["warning"] for d in degraded],
        "missing": [] if scored else [f"{job_id} has no active applications."],
        "degraded_sources": degraded,
    }


def score_one(app: dict[str, Any], must_haves: list[str], interviews: list[dict[str, Any]],
              events: list[dict[str, Any]]) -> dict[str, Any]:
    """The score and its breakdown for one application, from its own rows only."""
    cards = [i for i in interviews if i["scorecard_id"] is not None]
    missing = [f"No scorecard for {i['interview_id']} ({i['stage']}, completed {i['completed_at']})"
               for i in interviews if i["scorecard_id"] is None]
    if not cards:
        missing.append("No scorecards submitted yet")
    avg_points = sum(POINTS[c["overall"]] for c in cards) / len(cards) if cards else None
    scorecard_value = (avg_points - 1) / 3 if cards else 0.0

    ratings: dict[str, list[int]] = {m: [] for m in must_haves}
    for card in cards:
        for skill, rating in json.loads(card["ratings_json"]).items():
            if skill in ratings:
                ratings[skill].append(rating)
    per_skill = {m: sum(r) / len(r) if r else None for m, r in ratings.items()}
    unrated = [m for m, avg in per_skill.items() if avg is None]
    if cards and unrated:
        missing.append(f"No rating for must-have {', '.join(unrated)}")
    must_value = (sum((avg - 1) / 3 for avg in per_skill.values() if avg is not None) / len(must_haves)
                  if must_haves else 0.0)

    furthest = max(events, key=lambda e: STAGES.index(e["stage"]))
    stage_value = STAGES.index(furthest["stage"]) / (len(STAGES) - 1)

    score = (WEIGHTS["scorecards"] * scorecard_value + WEIGHTS["must_have"] * must_value
             + WEIGHTS["stage"] * stage_value)
    return {
        "application_id": app["application_id"],
        "candidate_id": app["candidate_id"],
        "full_name": app["full_name"],
        "current_stage": app["current_stage"],
        "score": round(score, 4),
        "components": {
            "scorecards": {
                "value": round(scorecard_value, 4),
                "weighted": round(WEIGHTS["scorecards"] * scorecard_value, 4),
                "count": len(cards),
                "avg_points": round(avg_points, 2) if avg_points is not None else None,
                "evidence": sorted(c["scorecard_id"] for c in cards),
            },
            "must_have": {
                "value": round(must_value, 4),
                "weighted": round(WEIGHTS["must_have"] * must_value, 4),
                "avg_rating_by_skill": {m: None if avg is None else round(avg, 2)
                                        for m, avg in per_skill.items()},
                "evidence": sorted(c["scorecard_id"] for c in cards),
            },
            "stage": {
                "value": round(stage_value, 4),
                "weighted": round(WEIGHTS["stage"] * stage_value, 4),
                "furthest_stage": furthest["stage"],
                "evidence": [furthest["event_id"]],
            },
        },
        "incomplete_evidence": bool(missing),
        "missing": missing,
    }
