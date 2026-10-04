"""Tests for the omacloud `open` and `logs` subcommands (audit #9 fix).

Closes audit finding #9 from `docs/audit-product-2026-10-02.md` §3.1
("No omacloud open / omacloud logs").

These tests exercise the command handlers in isolation against mocked
HTTP responses, so they don't need a live API. They cover:

* `omacloud open` with explicit and implicit session selection,
  browser-disabled (print-only) and browser-enabled paths.
* `omacloud open` errors cleanly when no running session exists.
* `omacloud logs` resolves a session and renders the lifecycle and
  daily-usage accounting.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


CLI_PATH = Path(__file__).resolve().parent.parent / "omacloud"


@pytest.fixture
def cli():
    """Import the CLI as a module (single-file script)."""
    return SourceFileLoader("omacloud_cli", str(CLI_PATH)).load_module()


@pytest.fixture
def auth_file(tmp_path, monkeypatch, cli):
    """Plant a fake auth.json and redirect the module constants."""
    f = tmp_path / "auth.json"
    monkeypatch.setattr(cli, "AUTH_FILE", f)
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
    return f


def _seed_token(monkeypatch, cli):
    monkeypatch.setattr(cli, "get_stored_token", lambda: "oma_live_test123")


# --------------------------------------------------------------- omacloud open


def test_open_help_lists_session_id():
    """`omacloud open --help` mentions the session_id arg."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "open", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "session_id" in result.stdout
    assert "--print-only" in result.stdout


def test_open_requires_auth(monkeypatch, capsys, cli):
    """`omacloud open` without a token prints the auth hint and exits 1."""
    monkeypatch.setattr(cli, "get_stored_token", lambda: None)
    args = argparse.Namespace(session_id=None, print_only=False)
    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_open(args)
    assert exc_info.value.code == 1
    assert "Not authenticated" in capsys.readouterr().err


def test_open_uses_most_recent_running_session(monkeypatch, capsys, cli, auth_file):
    """When no session_id is given, picks the most-recent RUNNING session."""
    _seed_token(monkeypatch, cli)

    sessions = [
        {"id": "sess_old", "status": "TERMINATED", "name": "old"},
        {"id": "sess_running", "status": "RUNNING", "name": "current"},
    ]
    detail = {
        "id": "sess_running",
        "name": "current",
        "status": "RUNNING",
        "substrate": "docker",
        "profile": "omarchy-quattro",
        "uptime_seconds": 60,
        "max_duration_seconds": 7200,
        "remaining_seconds": 7140,
        "streaming": {
            "web_url": "http://95.216.243.51:32768/vnc.html?autoconnect=true",
            "vnc_endpoint": "95.216.243.51:32770",
            "audio_endpoint": "http://95.216.243.51:8000/audio.mp3",
        },
        "created_at": "2026-10-04T15:30:00+00:00",
        "started_at": "2026-10-04T15:30:10+00:00",
    }

    calls = []

    def mock_request(path, method="GET", data=None, auth_token=None):
        calls.append((path, method))
        if path == "/sessions":
            return sessions
        if path == "/sessions/sess_running":
            return detail
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(cli, "api_request", mock_request)

    # Don't actually open a browser.
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    args = argparse.Namespace(session_id=None, print_only=False)
    cli.cmd_open(args)

    # Two requests: list, then detail.
    assert calls == [("/sessions", "GET"), ("/sessions/sess_running", "GET")]
    assert opened == ["http://95.216.243.51:32768/vnc.html?autoconnect=true"]


def test_open_explicit_session_id(monkeypatch, capsys, cli, auth_file):
    """When session_id is given, picks that exact session even if not running."""
    _seed_token(monkeypatch, cli)

    sessions = [
        {"id": "sess_a", "status": "RUNNING", "name": "a"},
        {"id": "sess_b", "status": "RUNNING", "name": "b"},
    ]
    detail_b = {
        "id": "sess_b",
        "name": "b",
        "status": "RUNNING",
        "substrate": "docker",
        "profile": "omarchy-quattro",
        "uptime_seconds": 60,
        "max_duration_seconds": 7200,
        "remaining_seconds": 7140,
        "streaming": {
            "web_url": "http://example:1234/vnc.html?autoconnect=true",
            "vnc_endpoint": "example:5900",
            "audio_endpoint": "http://example:8000/audio.mp3",
        },
        "created_at": "2026-10-04T15:30:00+00:00",
        "started_at": "2026-10-04T15:30:10+00:00",
    }

    def mock_request(path, method="GET", data=None, auth_token=None):
        if path == "/sessions":
            return sessions
        if path == "/sessions/sess_b":
            return detail_b
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(cli, "api_request", mock_request)
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: True)

    args = argparse.Namespace(session_id="sess_b", print_only=False)
    cli.cmd_open(args)
    # The list endpoint was used to look up sess_b by id, then the
    # detail endpoint fetched the streaming payload.
    captured = capsys.readouterr()
    assert "sess_b" in captured.out
    assert "example:1234" in captured.out


def test_open_print_only_skips_browser(monkeypatch, capsys, cli, auth_file):
    """`--print-only` prints the URL but does not invoke webbrowser.open."""
    _seed_token(monkeypatch, cli)

    sessions = [{"id": "sess_run", "status": "RUNNING", "name": "x"}]
    detail = {
        "id": "sess_run",
        "name": "x",
        "status": "RUNNING",
        "substrate": "docker",
        "profile": "omarchy-quattro",
        "uptime_seconds": 1,
        "max_duration_seconds": 7200,
        "remaining_seconds": 7199,
        "streaming": {
            "web_url": "http://print-only.example/vnc.html",
            "vnc_endpoint": "print-only.example:5900",
            "audio_endpoint": "http://print-only.example/audio.mp3",
        },
        "created_at": "2026-10-04T15:30:00+00:00",
        "started_at": "2026-10-04T15:30:10+00:00",
    }

    def mock_request(path, method="GET", data=None, auth_token=None):
        if path == "/sessions":
            return sessions
        if path == "/sessions/sess_run":
            return detail
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(cli, "api_request", mock_request)

    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    args = argparse.Namespace(session_id=None, print_only=True)
    cli.cmd_open(args)
    assert opened == []  # no browser was launched
    captured = capsys.readouterr()
    assert "print-only.example" in captured.out


def test_open_no_running_session_errors(monkeypatch, capsys, cli, auth_file):
    """When only TERMINATED sessions exist and no id is given, exit 1 with a clear message."""
    _seed_token(monkeypatch, cli)

    sessions = [
        {"id": "sess_old", "status": "TERMINATED", "name": "old"},
    ]

    monkeypatch.setattr(cli, "api_request", lambda *a, **kw: sessions)

    args = argparse.Namespace(session_id=None, print_only=False)
    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_open(args)
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "No running sessions" in err
    assert "TERMINATED" in err


# --------------------------------------------------------------- omacloud logs


def test_logs_help_lists_session_id():
    """`omacloud logs --help` mentions the session_id arg."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "logs", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "session_id" in result.stdout


def test_logs_renders_duration_accounting(monkeypatch, capsys, cli, auth_file):
    """`omacloud logs` prints session lifecycle + daily usage accounting."""
    _seed_token(monkeypatch, cli)

    sessions = [
        {"id": "sess_x", "status": "RUNNING", "name": "x"},
    ]
    detail = {
        "id": "sess_x",
        "name": "x",
        "status": "RUNNING",
        "substrate": "docker",
        "profile": "omarchy-quattro",
        "uptime_seconds": 3725,        # 1h 02m 05s
        "max_duration_seconds": 7200,
        "remaining_seconds": 3475,      # 57m 55s
        "streaming": {
            "web_url": "http://x/vnc.html",
            "vnc_endpoint": "x:5900",
            "audio_endpoint": "http://x/audio.mp3",
        },
        "created_at": "2026-10-04T15:30:00+00:00",
        "started_at": "2026-10-04T15:30:10+00:00",
    }
    profile = {
        "email": "alice@omacloud.org",
        "tier": "PRO",
        "daily_usage_seconds": 1800,
        "remaining_daily_seconds": 5400,
    }

    def mock_request(path, method="GET", data=None, auth_token=None):
        if path == "/sessions":
            return sessions
        if path == "/sessions/sess_x":
            return detail
        if path == "/user/me":
            return profile
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(cli, "api_request", mock_request)

    args = argparse.Namespace(session_id=None)
    cli.cmd_logs(args)

    out = capsys.readouterr().out
    assert "sess_x" in out
    assert "RUNNING" in out
    assert "docker" in out
    assert "alice@omacloud.org" in out
    assert "PRO" in out
    assert "1h02m05s" in out    # uptime
    assert "57m55s" in out      # remaining
    assert "30m00s" in out      # daily usage (1800s)
    assert "2h00m00s" in out    # daily cap (7200s)


def test_logs_explicit_session_id(monkeypatch, capsys, cli, auth_file):
    """`omacloud logs sess_y` targets that session by ID."""
    _seed_token(monkeypatch, cli)

    sessions = [
        {"id": "sess_a", "status": "RUNNING", "name": "a"},
        {"id": "sess_y", "status": "TERMINATED", "name": "y"},
    ]
    detail = {
        "id": "sess_y",
        "name": "y",
        "status": "TERMINATED",
        "substrate": "qemu",
        "profile": "omarchy-quattro",
        "uptime_seconds": 7200,
        "max_duration_seconds": 7200,
        "remaining_seconds": 0,
        "streaming": {
            "web_url": "http://y/vnc.html",
            "vnc_endpoint": "y:5900",
            "audio_endpoint": "http://y/audio.mp3",
        },
        "created_at": "2026-10-04T15:30:00+00:00",
        "started_at": "2026-10-04T15:30:10+00:00",
    }
    profile = {
        "email": "alice@omacloud.org",
        "tier": "PRO",
        "daily_usage_seconds": 7200,
        "remaining_daily_seconds": 0,
    }

    def mock_request(path, method="GET", data=None, auth_token=None):
        if path == "/sessions":
            return sessions
        if path == "/sessions/sess_y":
            return detail
        if path == "/user/me":
            return profile
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(cli, "api_request", mock_request)

    args = argparse.Namespace(session_id="sess_y")
    cli.cmd_logs(args)
    out = capsys.readouterr().out
    assert "sess_y" in out
    assert "TERMINATED" in out
    assert "qemu" in out


def test_logs_unknown_session_id_errors(monkeypatch, capsys, cli, auth_file):
    """Explicit session_id with no match exits 1 with a clear message."""
    _seed_token(monkeypatch, cli)
    sessions = [{"id": "sess_a", "status": "RUNNING", "name": "a"}]

    def mock_request(path, method="GET", data=None, auth_token=None):
        if path == "/sessions":
            return sessions
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(cli, "api_request", mock_request)
    args = argparse.Namespace(session_id="nope")
    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_logs(args)
    assert exc_info.value.code == 1
    assert "nope" in capsys.readouterr().err