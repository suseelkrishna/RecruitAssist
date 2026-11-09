"""Tools that read data fed by an integration report that integration when it is not Healthy.

Which integration is degraded is worked out here from source_syncs with SQL written in this
file, separately from app/logic/sources.py.
"""

from __future__ import annotations

from app.access import principal_for
from app.logic.evidence import get_candidate_evidence
from app.logic.scope import list_jobs, scope_card
from app.logic.scoring import score_candidates
from app.logic.sources import degraded_sources
from app.logic.tasks import pending_tasks

WARNING = "The Interview notes integration is degraded, so some scorecards may be missing or out of date."


def interview_notes_error_rate(db, as_of: str) -> float:
    """Percent of Interview notes runs in the 24 hours before as_of that did not succeed."""
    rows = [r[0] for r in db.execute(
        """SELECT status FROM source_syncs WHERE integration = 'Interview notes'
           AND finished_at <= ? AND julianday(?) - julianday(finished_at) <= 1""", (as_of, as_of))]
    return 100 * sum(1 for s in rows if s != "success") / len(rows)


def test_the_seed_data_has_interview_notes_degraded(db, as_of):
    assert interview_notes_error_rate(db, as_of) > 5


def test_only_tools_reading_scorecards_get_the_warning():
    assert [d["integration"] for d in degraded_sources({"scorecards"})] == ["Interview notes"]
    assert degraded_sources({"applications and stages", "candidate emails"}) == []


def test_pending_tasks_returns_the_warning_with_the_tasks():
    for user in ("USR-1", "USR-2", "USR-6"):
        result = pending_tasks(principal_for(user))
        assert result["warnings"] == [WARNING]
        assert result["degraded_sources"][0] == {
            "integration": "Interview notes", "status": "Degraded", "affects": "scorecards",
            "last_sync": result["degraded_sources"][0]["last_sync"], "warning": WARNING}


def test_the_warning_leaves_out_error_rates_and_messages():
    entry = pending_tasks(principal_for("USR-4"))["degraded_sources"][0]
    assert set(entry) == {"integration", "status", "affects", "last_sync", "warning"}


def test_score_candidates_and_evidence_carry_the_warning():
    user = principal_for("USR-1")
    assert WARNING in score_candidates(user, "JOB-3")["warnings"]
    assert get_candidate_evidence(user, "APP-079", ["scorecards"])["warnings"] == [WARNING]
    assert get_candidate_evidence(user, "APP-079", ["cv"])["warnings"] == []


def test_job_list_and_scope_card_return_the_active_total(db):
    user = principal_for("USR-2")
    expected = db.execute("""SELECT COUNT(*) FROM applications a JOIN jobs j ON j.job_id = a.job_id
                             JOIN manager_teams mt ON mt.team_id = j.team_id
                             WHERE mt.user_id = 'USR-2' AND a.status = 'active'""").fetchone()[0]
    assert expected == 33
    assert list_jobs(user)["active_applications_total"] == expected
    assert scope_card(user)["active_candidates_total"] == expected
