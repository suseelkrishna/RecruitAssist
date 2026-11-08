"""integration_health at each status threshold, with hand-built sync runs."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import tiny
from app.logic import sources


def run(n: int, integration: str, finished: str, status: str = "success", error: str | None = None) -> dict:
    """One source_syncs row. Only finished_at matters to the health rules."""
    return {"sync_id": f"SYNC-{n}", "integration": integration, "started_at": finished,
            "finished_at": finished, "status": status, "records": n, "error_message": error}


def health(use_db, runs: list[dict]) -> dict:
    """The single integration's health row."""
    data = tiny.base()
    data["source_syncs"] = runs
    use_db(data)
    return sources.integration_health()["integrations"][0]


@pytest.mark.parametrize("finished, status", [
    ("2026-11-09T16:30:00Z", "Healthy"),
    ("2026-11-09T16:00:00Z", "Healthy"),     # exactly 1 hour
    ("2026-11-09T15:59:00Z", "Degraded"),
    ("2026-11-09T11:00:00Z", "Degraded"),    # exactly 6 hours
    ("2026-11-09T10:59:00Z", "Down"),
])
def test_status_by_age_of_last_sync(use_db, finished, status):
    row = health(use_db, [run(1, "ATS", finished)])
    assert row["status"] == status
    assert row["simulated"] is True and row["last_sync"] == finished


def every_half_hour(count: int) -> list[dict]:
    """count successful runs, the newest at 16:50 on the as_of day, then every 30 minutes back."""
    newest = datetime(2026, 11, 9, 16, 50)
    return [run(n, "ATS", (newest - timedelta(minutes=30 * n)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            for n in range(count)]


def test_error_rate_above_five_percent_is_degraded(use_db):
    runs = every_half_hour(16)
    runs[5]["status"] = "partial"  # 1 of 16 = 6.25%
    row = health(use_db, runs)
    assert (row["status"], row["error_rate_24h_pct"], row["runs_24h"]) == ("Degraded", 6.2, 16)


def test_error_rate_at_five_percent_is_healthy(use_db):
    runs = every_half_hour(20)
    runs[5]["status"] = "failed"  # 1 of 20 = 5.0%
    row = health(use_db, runs)
    assert (row["status"], row["error_rate_24h_pct"]) == ("Healthy", 5.0)


def test_runs_older_than_24_hours_do_not_count_toward_the_error_rate(use_db):
    runs = every_half_hour(4) + [run(9, "ATS", "2026-11-08T16:59:00Z", "failed", "Old failure")]
    row = health(use_db, runs)
    assert (row["runs_24h"], row["error_rate_24h_pct"], row["status"]) == (4, 0.0, "Healthy")
    assert row["last_error"]["sync_id"] == "SYNC-9"


def test_last_three_failed_is_down(use_db):
    runs = [run(1, "ATS", "2026-11-09T16:40:00Z", "failed", "Timeout"),
            run(2, "ATS", "2026-11-09T16:30:00Z", "failed", "Timeout"),
            run(3, "ATS", "2026-11-09T16:20:00Z", "failed", "Auth error")]
    row = health(use_db, runs)
    assert row["status"] == "Down"
    assert row["last_error"] == {"sync_id": "SYNC-1", "at": "2026-11-09T16:40:00Z",
                                 "message": {"untrusted_text": "Timeout"}}
    assert health(use_db, runs[:2])["status"] == "Degraded"  # two failures are not enough for Down


def test_runs_after_as_of_are_ignored(use_db):
    runs = [run(1, "ATS", "2026-11-09T16:30:00Z"), run(2, "ATS", "2026-11-09T18:00:00Z", "failed")]
    row = health(use_db, runs)
    assert (row["last_sync_id"], row["status"]) == ("SYNC-1", "Healthy")


def test_committed_data_has_only_interview_notes_degraded():
    rows = {r["integration"]: r for r in sources.integration_health()["integrations"]}
    assert {name: r["status"] for name, r in rows.items()} == {
        "Email": "Healthy", "Google Calendar": "Healthy", "Greenhouse (ATS)": "Healthy",
        "Interview notes": "Degraded", "Slack": "Healthy"}
    assert rows["Interview notes"]["reasons"] == ["24-hour error rate 100.0% (over 5.0%)"]
