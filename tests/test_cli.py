"""Tests for ga4 CLI."""

import json

from typer.testing import CliRunner

from ga4.cli import app

runner = CliRunner()


def test_help():
    """--help shows usage."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ga4" in result.stdout


def test_version():
    """--version shows version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_auth_status():
    """auth status works."""
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0


def test_auth_status_json():
    """auth status --json outputs valid JSON."""
    result = runner.invoke(app, ["auth", "status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "authenticated" in data
