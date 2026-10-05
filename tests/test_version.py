import subprocess
import sys
from pathlib import Path

CLI_PATH = Path(__file__).resolve().parent.parent / "omacloud"


def test_cli_version_long():
    res = subprocess.run([sys.executable, str(CLI_PATH), "--version"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "omacloud 0.2.0" in (res.stdout + res.stderr)


def test_cli_version_short():
    res = subprocess.run([sys.executable, str(CLI_PATH), "-v"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "omacloud 0.2.0" in (res.stdout + res.stderr)
