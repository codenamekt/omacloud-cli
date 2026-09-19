"""Tests for OmaCloud CLI signup command."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
import pytest


def test_cli_signup_help():
    """Test omacloud signup --help output."""
    cli_path = Path(__file__).resolve().parent.parent / "omacloud"
    result = subprocess.run(
        [sys.executable, str(cli_path), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "signup" in result.stdout
    assert "Sign up for a free OmaCloud account" in result.stdout

    result_sub = subprocess.run(
        [sys.executable, str(cli_path), "signup", "--help"],
        capture_output=True,
        text=True,
    )
    assert result_sub.returncode == 0
    assert "--email" in result_sub.stdout


def test_cli_rate_limit_handling(monkeypatch, capsys):
    """Test that CLI cleanly prints rate limit message on 429."""
    import io
    import urllib.error
    import urllib.request
    from importlib.machinery import SourceFileLoader

    cli_path = Path(__file__).resolve().parent.parent / "omacloud"
    cli = SourceFileLoader("omacloud_cli", str(cli_path)).load_module()

    def mock_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="http://127.0.0.1:8080/v1/auth/signup",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=io.BytesIO(b'{"detail":"Rate limit exceeded: maximum 10 signups per 60 seconds."}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    import argparse
    args = argparse.Namespace(email="test@example.com")

    with pytest.raises(SystemExit) as exc_info:
        cli.cmd_signup(args)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Rate-limited, retry in 60s" in captured.err


def test_cli_save_and_status(tmp_path, monkeypatch):
    """Test save_stored_auth and get_stored_token functions."""
    from importlib.machinery import SourceFileLoader

    cli_path = Path(__file__).resolve().parent.parent / "omacloud"
    cli = SourceFileLoader("omacloud_cli", str(cli_path)).load_module()

    auth_file = tmp_path / "auth.json"
    monkeypatch.setattr(cli, "AUTH_FILE", auth_file)
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)

    cli.save_stored_auth("oma_live_test123", "alice@example.com", "free")
    assert auth_file.is_file()

    token = cli.get_stored_token()
    assert token == "oma_live_test123"

    data = json.loads(auth_file.read_text())
    assert data["email"] == "alice@example.com"
    assert data["tier"] == "free"


def test_cli_signup_simulated_flow(tmp_path, monkeypatch):
    """Simulate complete CLI signup execution against mocked responses."""
    from importlib.machinery import SourceFileLoader

    cli_path = Path(__file__).resolve().parent.parent / "omacloud"
    cli = SourceFileLoader("omacloud_cli", str(cli_path)).load_module()

    auth_file = tmp_path / "auth.json"
    monkeypatch.setattr(cli, "AUTH_FILE", auth_file)
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)

    # Disable webbrowser
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url: True)

    poll_count = [0]

    def mock_api_request(path, method="GET", data=None, auth_token=None):
        if path == "/auth/signup":
            return {
                "signup_id": "signup_abc123",
                "poll_url": "/v1/auth/signup/poll/signup_abc123",
                "existing_user": False,
                "magic_link_url": "https://auth.omacloud.org/m/mocktoken",
            }
        elif path == "/auth/signup/poll/signup_abc123":
            poll_count[0] += 1
            if poll_count[0] == 1:
                return {"status": "pending"}
            return {
                "status": "ok",
                "api_token": "oma_live_tok999",
                "email": "charlie@example.com",
                "tier": "free",
            }
        raise ValueError(f"Unexpected path: {path}")

    monkeypatch.setattr(cli, "api_request", mock_api_request)

    import argparse
    args = argparse.Namespace(email="charlie@example.com")
    cli.cmd_signup(args)

    assert auth_file.is_file()
    auth_data = json.loads(auth_file.read_text())
    assert auth_data["api_token"] == "oma_live_tok999"
    assert auth_data["email"] == "charlie@example.com"
    assert auth_data["tier"] == "free"
