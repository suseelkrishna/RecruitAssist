"""The command-line entry point: argument errors and a missing API key end with a message, not a traceback."""

from __future__ import annotations

from app.agent import cli


def test_missing_api_key_prints_a_message_and_exits_2(monkeypatch, capsys):
    """Without ANTHROPIC_API_KEY the CLI names the variable and returns 2 before calling the model."""
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["Which tasks are pending or overdue?", "--user", "USR-4"]) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_unknown_user_lists_the_valid_users(monkeypatch, capsys):
    """An unknown --user returns 2 and lists the valid user IDs."""
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    assert cli.main(["Any question", "--user", "USR-99"]) == 2
    err = capsys.readouterr().err
    assert "USR-99" in err and "USR-1, USR-2, USR-3, USR-4, USR-5, USR-6" in err
