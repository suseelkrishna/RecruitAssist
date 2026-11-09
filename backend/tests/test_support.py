"""Small supporting modules: the .env loader, recording matching, and the quality report."""

from __future__ import annotations

import os

from app import env, quality
from app.agent import recordings


def test_env_file_fills_missing_keys_only(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# comment\nRA_TEST_A=from-file\nRA_TEST_B='quoted'\nRA_TEST_EMPTY=\nnot a pair\n")
    monkeypatch.setenv("RA_TEST_A", "from-env")
    monkeypatch.delenv("RA_TEST_B", raising=False)
    monkeypatch.delenv("RA_TEST_EMPTY", raising=False)
    env.load_env_file(path)
    assert os.environ["RA_TEST_A"] == "from-env"
    assert os.environ.pop("RA_TEST_B") == "quoted"
    assert "RA_TEST_EMPTY" not in os.environ


def test_recordings_match_on_normalized_question(tmp_path):
    path = tmp_path / "recordings.json"
    recordings.save("Who are the TOP 3?", "USR-1", "JOB-2", ["JOB-2"], {"answer": "a"}, "2026-11-09T00:00:00Z", path)
    recordings.save("who are the top 3", "USR-1", "JOB-2", ["JOB-2"], {"answer": "b"}, "2026-11-09T01:00:00Z", path)
    assert len(recordings.load(path)) == 1
    found = recordings.find("  Who are the top 3 ", "USR-1", "JOB-2", ["JOB-2"], path)
    assert found == {"answer": "b", "source": "recording", "recorded_at": "2026-11-09T01:00:00Z"}
    assert recordings.find("Who are the top 3?", "USR-1", None, ["JOB-2"], path) is None


def test_quality_report_lists_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "QUALITY", tmp_path / "quality.json")
    monkeypatch.setattr(quality, "SCOREBOARD", tmp_path / "scoreboard.json")
    report = quality.quality_report()
    assert report["tests"] is None and report["missing"] == ["tests", "rbac", "mutation", "scoreboard"]
    assert all("quality_snapshot.py" in report["reasons"][k] for k in ("tests", "rbac", "mutation"))
    assert "run.py" in report["reasons"]["scoreboard"]
    (tmp_path / "quality.json").write_text(
        '{"generated_at": "2026-11-09T22:00:00Z", "git_commit": "abc1234", "git_dirty": false,'
        ' "tests": {"passed": 5, "total": 5}, "rbac": {"result": "pass"},'
        ' "mutation": {"caught": 11, "total": 12, "ran_at": "2026-11-09T21:00:00Z"}}')
    report = quality.quality_report()
    assert report["mutation"]["ran_at"] == "2026-11-09T21:00:00Z" and report["git_commit"] == "abc1234"
    assert report["missing"] == ["scoreboard"] and list(report["reasons"]) == ["scoreboard"]
    assert report["tests_defined"] > 0
