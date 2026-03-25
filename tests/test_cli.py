"""Tests for ga4 CLI."""

import json

from typer.testing import CliRunner

from ga4.cli import app
from ga4.shared import filter_fields, validate_id

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help & version
# ---------------------------------------------------------------------------

def test_help():
    """--help shows usage."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ga4" in result.stdout


def test_version():
    """--version shows version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.stdout


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_auth_status():
    """auth status works."""
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0


def test_auth_status_json():
    """auth status --json outputs valid JSON."""
    result = runner.invoke(app, ["auth", "status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "data" in data or "authenticated" in data


def test_auth_list():
    """auth list works."""
    result = runner.invoke(app, ["auth", "list"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Describe (introspection)
# ---------------------------------------------------------------------------

def test_describe():
    """describe lists resources."""
    result = runner.invoke(app, ["describe"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "properties" in result.output


def test_describe_json():
    """describe --json returns valid JSON with expected shape."""
    result = runner.invoke(app, ["describe", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "data" in data
    assert data["data"]["tool"] == "ga4"
    assert "version" in data["data"]
    assert "resources" in data["data"]
    resources = data["data"]["resources"]
    assert "auth" in resources
    assert "properties" in resources
    assert "users" in resources
    assert "channels" in resources
    assert "schema" in resources
    assert "health" in resources
    assert "scan" in resources


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_cache_status():
    """cache status works."""
    result = runner.invoke(app, ["cache", "status"])
    assert result.exit_code == 0


def test_cache_status_json():
    """cache status --json returns valid JSON."""
    result = runner.invoke(app, ["cache", "status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "data" in data
    assert "entries" in data["data"]


# ---------------------------------------------------------------------------
# Unauthenticated errors
# ---------------------------------------------------------------------------

def test_accounts_list_no_auth():
    """accounts list fails with exit 2 when not authenticated."""
    result = runner.invoke(app, ["--profile", "__nonexistent__", "accounts", "list"])
    assert result.exit_code == 2


def test_properties_list_no_auth():
    """properties list fails with exit 2 when not authenticated."""
    result = runner.invoke(app, ["--profile", "__nonexistent__", "properties", "list"])
    assert result.exit_code == 2


def test_users_list_no_auth():
    """users list fails with exit 2 when not authenticated."""
    result = runner.invoke(app, ["--profile", "__nonexistent__", "users", "list", "123456"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# ID validation
# ---------------------------------------------------------------------------

def test_validate_id_rejects_query_chars():
    """validate_id rejects IDs with ? # % & characters."""
    import pytest
    from typer import Exit

    with pytest.raises(Exit):
        validate_id("123?456", "test_id")

    with pytest.raises(Exit):
        validate_id("123#456", "test_id")

    with pytest.raises(Exit):
        validate_id("123%456", "test_id")

    with pytest.raises(Exit):
        validate_id("123&456", "test_id")

    with pytest.raises(Exit):
        validate_id("../etc/passwd", "test_id")


def test_validate_id_accepts_valid():
    """validate_id accepts normal IDs."""
    assert validate_id("123456789", "property_id") == "123456789"
    assert validate_id("abc-def_123", "resource_id") == "abc-def_123"


# ---------------------------------------------------------------------------
# Field filtering
# ---------------------------------------------------------------------------

def test_filter_fields_list():
    """filter_fields filters list of dicts."""
    data = [
        {"id": "1", "name": "A", "extra": "x"},
        {"id": "2", "name": "B", "extra": "y"},
    ]
    result = filter_fields(data, "id,name")
    assert result == [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]


def test_filter_fields_dict():
    """filter_fields filters a single dict."""
    data = {"id": "1", "name": "A", "extra": "x"}
    result = filter_fields(data, "id,name")
    assert result == {"id": "1", "name": "A"}


def test_filter_fields_none():
    """filter_fields with None returns data unchanged."""
    data = [{"id": "1", "name": "A"}]
    result = filter_fields(data, None)
    assert result == data


def test_fields_global_flag():
    """--fields flag filters JSON output."""
    result = runner.invoke(app, ["--fields", "tool,version", "describe", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "data" in data
    # describe returns tool/version/protocol/resources — only tool,version should remain
    assert "tool" in data["data"]
    assert "version" in data["data"]
    assert "resources" not in data["data"]


# ---------------------------------------------------------------------------
# Global flags
# ---------------------------------------------------------------------------

def test_quiet_flag():
    """--quiet suppresses stderr output."""
    result = runner.invoke(app, ["--quiet", "describe"])
    assert result.exit_code == 0


def test_subcommand_help():
    """Subcommand --help works for key resources."""
    for cmd in ["auth", "accounts", "properties", "users", "channels", "health", "scan", "schema"]:
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed"
