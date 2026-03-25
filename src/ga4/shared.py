"""Shared CLI helpers used across cli.py, health_cli.py, and scan_cli.py."""

from __future__ import annotations

import json
import os
import re

import typer
from rich.console import Console

from .config import DEFAULT_PROFILE, get_tokens

# stderr for human output
console = Console(stderr=True)

# Exit codes (Fabric Protocol)
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_AUTH_REQUIRED = 2
EXIT_NOT_FOUND = 3
EXIT_VALIDATION = 4
EXIT_FORBIDDEN = 5
EXIT_RATE_LIMITED = 6
EXIT_CONFLICT = 7

# ---------------------------------------------------------------------------
# Active profile state
# ---------------------------------------------------------------------------

# Module-level mutable state for the active profile.  cli.py's @app.callback
# sets this on every invocation via set_active_profile().  Defaults to the
# GA4_PROFILE env var, falling back to DEFAULT_PROFILE.
_active_profile: str = os.environ.get("GA4_PROFILE", DEFAULT_PROFILE)
_active_fields: str | None = None
_quiet_mode: bool = False


def get_active_profile() -> str:
    """Return the currently active authentication profile."""
    return _active_profile


def set_active_profile(profile: str) -> None:
    """Set the active authentication profile."""
    global _active_profile
    _active_profile = profile


def get_active_fields() -> str | None:
    """Return the active --fields filter."""
    return _active_fields


def set_active_fields(fields: str | None) -> None:
    """Set the active --fields filter from the CLI callback."""
    global _active_fields
    _active_fields = fields


def is_quiet() -> bool:
    """Return whether quiet mode is active."""
    return _quiet_mode


def set_quiet(quiet: bool) -> None:
    """Set quiet mode from the CLI callback."""
    global _quiet_mode
    _quiet_mode = quiet


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def info(message: str) -> None:
    """Print informational message to stderr, suppressed by --quiet."""
    if not _quiet_mode:
        console.print(message)


def output_json(data) -> None:
    """Output JSON to stdout, applying --fields filtering if active."""
    fields = get_active_fields()
    if fields and isinstance(data, dict) and "data" in data:
        data = {**data, "data": filter_fields(data["data"], fields)}
    print(json.dumps(data, indent=2, default=str))


def error(
    message: str,
    code: str = "ERROR",
    exit_code: int = EXIT_ERROR,
    details: dict = None,
    as_json: bool = False,
):
    """Output error and exit."""
    error_obj = {"error": {"code": code, "message": message}}
    if details:
        error_obj["error"]["details"] = details

    if as_json:
        output_json(error_obj)

    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(exit_code)


def require_auth(as_json: bool = False):
    """Check authentication for the active profile, exit if not authenticated."""
    profile = get_active_profile()
    tokens = get_tokens(profile)
    if not tokens or not tokens.get("access_token"):
        msg = "Not authenticated. Run: ga4 auth login"
        if profile != DEFAULT_PROFILE:
            msg = f"Not authenticated for profile '{profile}'. Run: ga4 auth login --profile {profile}"
        error(
            msg,
            "AUTH_REQUIRED",
            EXIT_AUTH_REQUIRED,
            as_json=as_json,
        )


def filter_fields(data, fields: str | None):
    """Filter JSON output to only include specified fields.

    Per Clique Protocol --fields specification. Applies to objects inside data.
    """
    if not fields:
        return data
    keep = {f.strip() for f in fields.split(",")}
    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in keep} for item in data]
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in keep}
    return data


def validate_id(value: str, field_name: str = "ID", as_json: bool = False) -> str:
    """Reject IDs with suspicious characters (agent hallucination defence).

    GA4 property and account IDs are numeric strings. This rejects path
    traversal, query injection, and other suspicious patterns.
    """
    if not value:
        error(f"Missing {field_name}", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=as_json)
    if re.search(r'[?#%&]|\.\.', value):
        error(
            f"Invalid {field_name}: contains prohibited characters",
            "VALIDATION_ERROR", EXIT_VALIDATION,
            {"field": field_name, "value": value}, as_json,
        )
    # GA4 IDs are numeric — warn but don't block non-numeric (some resource IDs aren't)
    return value


def handle_api_error(e: Exception, context: str, as_json: bool = False):
    """Handle API errors with proper exit codes."""
    from .errors import RateLimitError

    if isinstance(e, RateLimitError):
        error(str(e), "RATE_LIMITED", EXIT_RATE_LIMITED, as_json=as_json)
    elif isinstance(e, ValueError):
        error(str(e), "VALIDATION_ERROR", EXIT_VALIDATION, as_json=as_json)
    else:
        error(f"{context}: {e}", "API_ERROR", EXIT_ERROR, as_json=as_json)
