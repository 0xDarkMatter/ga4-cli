"""Tests for ga4 bq commands."""

import json

from typer.testing import CliRunner

from ga4.cli import app
from ga4.bq_client import QUERY_TEMPLATES, ga4_dataset

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

def test_bq_help():
    """bq --help shows all subcommands."""
    result = runner.invoke(app, ["bq", "--help"])
    assert result.exit_code == 0
    assert "status" in result.output
    assert "link" in result.output
    assert "freshness" in result.output
    assert "audit" in result.output
    assert "query" in result.output
    assert "cost" in result.output
    assert "tables" in result.output
    assert "schema" in result.output
    assert "datasets" in result.output
    assert "templates" in result.output


def test_bq_status_help():
    result = runner.invoke(app, ["bq", "status", "--help"])
    assert result.exit_code == 0
    assert "property" in result.output.lower()


def test_bq_link_help():
    result = runner.invoke(app, ["bq", "link", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.output


def test_bq_query_help():
    result = runner.invoke(app, ["bq", "query", "--help"])
    assert result.exit_code == 0
    assert "--template" in result.output


def test_bq_cost_help():
    result = runner.invoke(app, ["bq", "cost", "--help"])
    assert result.exit_code == 0
    assert "estimate" in result.output.lower()


def test_bq_tables_help():
    result = runner.invoke(app, ["bq", "tables", "--help"])
    assert result.exit_code == 0


def test_bq_schema_help():
    result = runner.invoke(app, ["bq", "schema", "--help"])
    assert result.exit_code == 0


def test_bq_datasets_help():
    result = runner.invoke(app, ["bq", "datasets", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# describe includes bq
# ---------------------------------------------------------------------------

def test_describe_includes_bq():
    """describe --json includes bq resource."""
    result = runner.invoke(app, ["describe", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "bq" in data["data"]["resources"]
    bq_actions = data["data"]["resources"]["bq"]
    assert "status" in bq_actions
    assert "query" in bq_actions
    assert "audit" in bq_actions
    assert "templates" in bq_actions


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_bq_templates():
    """bq templates lists available templates."""
    result = runner.invoke(app, ["bq", "templates"])
    assert result.exit_code == 0
    assert "ai-traffic" in result.output
    assert "sessions" in result.output
    assert "top-pages" in result.output
    assert "events" in result.output
    assert "channels" in result.output


def test_bq_templates_json():
    """bq templates --json outputs valid JSON."""
    result = runner.invoke(app, ["bq", "templates", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "data" in data
    names = {t["name"] for t in data["data"]}
    assert names == set(QUERY_TEMPLATES.keys())


# ---------------------------------------------------------------------------
# ga4_dataset helper
# ---------------------------------------------------------------------------

def test_ga4_dataset():
    """ga4_dataset returns correct naming convention."""
    assert ga4_dataset("123456789") == "analytics_123456789"
    assert ga4_dataset("properties/123456789") == "analytics_123456789"


# ---------------------------------------------------------------------------
# Query templates valid SQL
# ---------------------------------------------------------------------------

def test_query_templates_format():
    """All query templates have required placeholders."""
    for name, tmpl in QUERY_TEMPLATES.items():
        assert "name" in tmpl, f"{name} missing 'name'"
        assert "description" in tmpl, f"{name} missing 'description'"
        assert "sql" in tmpl, f"{name} missing 'sql'"
        # Verify the SQL can be formatted
        formatted = tmpl["sql"].format(
            project="test-project",
            dataset="analytics_123",
            start="20250101",
            end="20250131",
        )
        assert "test-project" in formatted
        assert "analytics_123" in formatted


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------

def test_bq_status_no_auth():
    """bq status fails with exit 2 when not authenticated."""
    result = runner.invoke(app, ["--profile", "__nonexistent__", "bq", "status", "123456"])
    assert result.exit_code == 2


def test_bq_audit_no_auth():
    """bq audit fails with exit 2 when not authenticated."""
    result = runner.invoke(app, ["--profile", "__nonexistent__", "bq", "audit"])
    assert result.exit_code == 2


def test_bq_freshness_no_auth():
    """bq freshness fails with exit 2 when not authenticated."""
    result = runner.invoke(app, ["--profile", "__nonexistent__", "bq", "freshness", "123456"])
    assert result.exit_code == 2
