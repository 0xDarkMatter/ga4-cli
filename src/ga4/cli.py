"""ga4 CLI - Google Analytics 4 reporting and data analysis"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.table import Table

from . import __version__
from .cache import Cache
from .client import DataClient
from .config import (
    DEFAULT_PROFILE,
    clear_credentials,
    get_auth_status,
    list_profiles,
    run_oauth_flow,
)
from .health_cli import health_app
from .scan_cli import scan_app
from .bq_cli import bq_app
from .channels_cli import channels_app
from .schema_cli import schema_app
from .shared import (
    EXIT_AUTH_REQUIRED,
    EXIT_CONFLICT,
    EXIT_ERROR,
    EXIT_FORBIDDEN,
    EXIT_NOT_FOUND,
    EXIT_RATE_LIMITED,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    console,
    error as _error,
    filter_fields,
    get_active_profile,
    handle_api_error,
    is_quiet,
    output_json as _output_json,
    require_auth as _require_auth,
    set_active_fields,
    set_active_profile,
    set_quiet,
    validate_id,
)


app = typer.Typer(
    name="ga4",
    help="Google Analytics 4 reporting and data analysis",
    no_args_is_help=True,
)


def version_callback(value: bool):
    if value:
        print(f"ga4 {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", callback=version_callback, is_eager=True),
    ] = None,
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            "-P",
            help="Auth profile to use (env: GA4_PROFILE)",
            show_default=True,
        ),
    ] = os.environ.get("GA4_PROFILE", DEFAULT_PROFILE),
    fields: Annotated[
        Optional[str],
        typer.Option("--fields", help="Comma-separated fields to include in JSON output"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress non-essential stderr output"),
    ] = False,
) -> None:
    """Google Analytics 4 reporting and data analysis"""
    set_active_profile(profile)
    set_active_fields(fields)
    set_quiet(quiet)


# Register health and scan sub-apps
app.add_typer(health_app, name="health")
app.add_typer(scan_app, name="scan")
app.add_typer(schema_app, name="schema")
app.add_typer(channels_app, name="channels")
app.add_typer(bq_app, name="bq")


# =============================================================================
# DESCRIBE COMMAND (Fabric Protocol introspection)
# =============================================================================


@app.command("describe")
def describe(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List all available resources and actions (no auth required).

    Examples:
        ga4 describe
        ga4 describe --json
    """
    resources = {
        "auth": ["login", "status", "logout", "list"],
        "accounts": ["list"],
        "properties": ["list", "get"],
        "reports": ["run", "realtime"],
        "dimensions": ["list", "get"],
        "metrics": ["list", "get"],
        "users": ["list", "add", "remove", "copy", "batch-add"],  # all support --account for account-level
        "health": ["check", "access", "tracking", "summary", "report"],
        "scan": ["all", "issues", "report", "permissions"],
        "schema": ["export", "deploy"],
        "channels": ["list", "get", "create", "update", "export", "delete", "templates"],
        "bq": ["status", "link", "freshness", "audit", "query", "cost", "tables", "schema", "datasets", "templates"],
    }

    if json_output:
        _output_json({
            "data": {
                "tool": "ga4",
                "version": __version__,
                "protocol": "fabric",
                "resources": resources,
            },
        })
        return

    console.print(f"[bold]ga4[/bold] v{__version__}")
    console.print()
    for resource, actions in resources.items():
        console.print(f"  [cyan]{resource}[/cyan]: {', '.join(actions)}")


# =============================================================================
# CACHE COMMAND
# =============================================================================


@app.command("cache")
def cache_cmd(
    action: Annotated[str, typer.Argument(help="Action: clear, status")] = "status",
    property_id: Annotated[Optional[str], typer.Argument(help="Property ID to clear (for 'clear' action)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Manage API response cache.

    The cache stores admin and metadata API responses in .cache/ga4/ to speed
    up repeated health checks.  Reporting data is never cached.

    Examples:
        ga4 cache status
        ga4 cache clear
        ga4 cache clear 123456789   # clear one property
        ga4 cache status --json
    """
    cache = Cache()

    if action == "status":
        stats = cache.status()
        if json_output:
            _output_json({"data": stats})
            return
        if stats["entries"] == 0:
            console.print("[dim]Cache is empty[/dim]")
            return
        console.print(f"Cache directory: [cyan]{stats['cache_dir']}[/cyan]")
        console.print(f"Total entries: [bold]{stats['entries']}[/bold]")
        console.print(f"Total size: [dim]{stats['size_bytes']:,} bytes[/dim]")
        if stats["namespaces"]:
            console.print()
            from rich.table import Table
            table = Table(title="Cache Namespaces")
            table.add_column("Namespace")
            table.add_column("Entries", justify="right")
            for ns in stats["namespaces"]:
                table.add_row(ns["name"], str(ns["count"]))
            console.print(table)

    elif action == "clear":
        if property_id:
            count = cache.clear_property(property_id)
            if json_output:
                _output_json({"data": {"cleared": count, "property_id": property_id}})
            else:
                console.print(f"[green]Cleared {count} cache entries for property {property_id}[/green]")
        else:
            count = cache.clear()
            if json_output:
                _output_json({"data": {"cleared": count}})
            else:
                console.print(f"[green]Cleared {count} cache entries[/green]")

    else:
        _error(f"Unknown action: {action!r}. Use 'clear' or 'status'.", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)


# =============================================================================
# AUTH COMMANDS
# =============================================================================
auth_app = typer.Typer(help="Authentication")
app.add_typer(auth_app, name="auth")


@auth_app.command("login")
def auth_login(
    port: Annotated[int, typer.Option("--port", "-p", help="Local server port")] = 8080,
    profile: Annotated[Optional[str], typer.Option("--profile", "-P", help="Profile to authenticate")] = None,
):
    """
    Authenticate with Google Analytics.

    Opens browser for OAuth2 authentication flow.

    Examples:
        ga4 auth login
        ga4 auth login --port 9000
        ga4 auth login --profile work
        ga4 -P work auth login
    """
    active = profile if profile is not None else get_active_profile()
    try:
        if active != DEFAULT_PROFILE:
            console.print(f"Opening browser for authentication (profile: [cyan]{active}[/cyan])...")
        else:
            console.print("Opening browser for authentication...")
        run_oauth_flow(port=port, profile=active)
        if active != DEFAULT_PROFILE:
            console.print(f"[green]Authenticated successfully (profile: {active})![/green]")
        else:
            console.print("[green]Authenticated successfully![/green]")
    except FileNotFoundError as e:
        _error(str(e), "CONFIG_ERROR", EXIT_ERROR)
    except Exception as e:
        _error(f"Authentication failed: {e}", "AUTH_ERROR", EXIT_ERROR)



@auth_app.command("status")
def auth_status_cmd(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    profile: Annotated[Optional[str], typer.Option("--profile", "-P", help="Profile to check")] = None,
):
    """
    Check authentication status.

    Examples:
        ga4 auth status
        ga4 auth status --json
        ga4 auth status --profile work
        ga4 -P work auth status
    """
    active = profile if profile is not None else get_active_profile()
    status = get_auth_status(profile=active)

    if json_output:
        _output_json({"data": status})
        return

    console.print(f"Profile: [cyan]{active}[/cyan]")

    if status.get("authenticated"):
        console.print("Authenticated: [green]yes[/green]")
        console.print(f"Source: [cyan]{status.get('source', 'unknown')}[/cyan]")

        if status.get("expired"):
            if active != DEFAULT_PROFILE:
                console.print(f"[yellow]Token expired - run: ga4 auth login --profile {active}[/yellow]")
            else:
                console.print("[yellow]Token expired - run auth login to refresh[/yellow]")
        elif status.get("expires_at"):
            console.print(f"Expires: {status['expires_at']}")

    else:
        console.print("Authenticated: [red]no[/red]")
        if active != DEFAULT_PROFILE:
            console.print(f"Run: ga4 auth login --profile {active}")
        else:
            console.print("Run: ga4 auth login")


@auth_app.command("logout")
def auth_logout(
    profile: Annotated[Optional[str], typer.Option("--profile", "-P", help="Profile to clear ('*' for all)")] = None,
):
    """
    Clear stored credentials.

    Examples:
        ga4 auth logout
        ga4 auth logout --profile work
        ga4 auth logout --profile '*'
        ga4 -P work auth logout
    """
    active = profile if profile is not None else get_active_profile()
    clear_credentials(profile=active)

    if active == "*":
        console.print("[green]Logged out all profiles[/green]")
    elif active != DEFAULT_PROFILE:
        console.print(f"[green]Logged out (profile: {active})[/green]")
    else:
        console.print("[green]Logged out[/green]")


@auth_app.command("list")
def auth_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List all authentication profiles and their status.

    Examples:
        ga4 auth list
        ga4 auth list --json
    """
    profiles = list_profiles()
    active = get_active_profile()

    # Mark the currently active profile
    for p in profiles:
        p["active"] = p["profile"] == active

    if json_output:
        _output_json({"data": profiles})
        return

    if not profiles:
        console.print("[yellow]No profiles found[/yellow]")
        return

    table = Table(title="Auth Profiles")
    table.add_column("Profile")
    table.add_column("Authenticated")
    table.add_column("Source")
    table.add_column("Expired")
    table.add_column("Active")

    for p in profiles:
        auth_display = "[green]yes[/green]" if p["authenticated"] else "[red]no[/red]"
        expired = p.get("expired")
        if expired is True:
            expired_display = "[yellow]yes[/yellow]"
        elif expired is False:
            expired_display = "no"
        else:
            expired_display = "-"
        active_display = "[cyan]*[/cyan]" if p["active"] else ""

        table.add_row(
            p["profile"],
            auth_display,
            p.get("source", "none"),
            expired_display,
            active_display,
        )

    console.print(table)


# =============================================================================
# ACCOUNTS COMMANDS
# =============================================================================
accounts_app = typer.Typer(help="Account operations")
app.add_typer(accounts_app, name="accounts")


@accounts_app.command("list")
def accounts_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 500,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List GA4 accounts.

    Examples:
        ga4 accounts list
        ga4 accounts list --json
    """
    _require_auth(json_output)

    from .admin_client import AdminClient

    client = AdminClient(profile=get_active_profile())
    try:
        items = client.list_accounts(limit=limit)
    except Exception as e:
        _error(f"Failed to list accounts: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": items,
            "meta": {"count": len(items)},
        })
        return

    if not items:
        console.print("[yellow]No accounts found[/yellow]")
        return

    table = Table(title="Accounts")
    table.add_column("ID")
    table.add_column("Name")

    for item in items:
        account_id = item.get("name", "").replace("accounts/", "")
        table.add_row(account_id, item.get("displayName", ""))

    console.print(table)


# =============================================================================
# PROPERTIES COMMANDS
# =============================================================================
properties_app = typer.Typer(help="Property operations")
app.add_typer(properties_app, name="properties")


@properties_app.command("list")
def properties_list(
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Filter by account ID")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List GA4 properties.

    Examples:
        ga4 properties list
        ga4 properties list --limit 10
        ga4 properties list --account 123456789
        ga4 properties list --json | jq '.data[0]'
    """
    _require_auth(json_output)

    from .admin_client import AdminClient

    client = AdminClient(profile=get_active_profile())
    try:
        items = client.list_properties(account_id=account, limit=limit)
    except Exception as e:
        _error(f"Failed to list properties: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": items,
            "meta": {"count": len(items)},
        })
        return

    if not items:
        console.print("[yellow]No properties found[/yellow]")
        return

    table = Table(title="Properties")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Time Zone")

    for item in items:
        table.add_row(
            str(item.get("id", "")),
            item.get("name", ""),
            item.get("time_zone", ""),
        )

    console.print(table)


@properties_app.command("get")
def properties_get(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get a specific property by ID.

    Examples:
        ga4 properties get 123456789
        ga4 properties get 123456789 --json
    """
    validate_id(property_id, "property_id", json_output)
    _require_auth(json_output)

    from .admin_client import AdminClient

    client = AdminClient(profile=get_active_profile())
    try:
        item = client.get_property(property_id)
    except Exception as e:
        _error(f"Failed to get property: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if item is None:
        _error(
            f"Property not found: {property_id}",
            "NOT_FOUND",
            EXIT_NOT_FOUND,
            {"property_id": property_id},
            json_output,
        )

    if json_output:
        _output_json({"data": item})
        return

    console.print(f"[bold]{item.get('name', 'Unknown')}[/bold]")
    console.print(f"  ID: {item.get('id')}")
    for key, value in item.items():
        if key not in ("id", "name") and value:
            console.print(f"  {key}: {value}")





reports_app = typer.Typer(help="Report operations")
app.add_typer(reports_app, name="reports")


@reports_app.command("run")
def reports_run(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    dimensions: Annotated[str, typer.Option("--dimensions", "-d", help="Dimensions (comma-separated)")] = "date",
    metrics: Annotated[str, typer.Option("--metrics", "-m", help="Metrics (comma-separated)")] = "activeUsers,sessions",
    start_date: Annotated[str, typer.Option("--from", help="Start date (YYYY-MM-DD or relative)")] = "30daysAgo",
    end_date: Annotated[str, typer.Option("--to", help="End date (YYYY-MM-DD or relative)")] = "today",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max rows")] = 100,
    order_by: Annotated[Optional[str], typer.Option("--order-by", "-o", help="Sort by dimension or metric")] = None,
    ascending: Annotated[bool, typer.Option("--asc", help="Sort ascending (default: descending)")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Run a custom report with specified dimensions and metrics.

    Examples:
        ga4 reports run 123456789
        ga4 reports run 123456789 -d date,city -m activeUsers,sessions
        ga4 reports run 123456789 --from 2025-01-01 --to 2025-01-31
        ga4 reports run 123456789 -d date -m sessions --order-by sessions
        ga4 reports run 123456789 --json | jq '.data.rows'
    """
    _require_auth(json_output)

    # Parse comma-separated values
    dim_list = [d.strip() for d in dimensions.split(",") if d.strip()]
    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]

    if not dim_list:
        _error("At least one dimension is required", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    if not metric_list:
        _error("At least one metric is required", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)

    client = DataClient(profile=get_active_profile())
    try:
        report = client.run_report(
            property_id=property_id,
            dimensions=dim_list,
            metrics=metric_list,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            order_by=order_by,
            descending=not ascending,
        )
    except Exception as e:
        _error(f"Failed to run report: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": report,
            "meta": {
                "property_id": property_id,
                "date_range": {"start": start_date, "end": end_date},
            },
        })
        return

    if not report.get("rows"):
        console.print("[yellow]No data found for the specified criteria[/yellow]")
        return

    # Build table with all columns
    table = Table(title=f"Report for Property {property_id}")
    all_headers = report["dimension_headers"] + report["metric_headers"]
    for header in all_headers:
        table.add_column(header)

    for row in report["rows"]:
        table.add_row(*[str(row.get(h, "")) for h in all_headers])

    console.print(table)
    console.print(f"\n[dim]Showing {len(report['rows'])} of {report['row_count']} rows[/dim]")


@reports_app.command("realtime")
def reports_realtime(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    dimensions: Annotated[str, typer.Option("--dimensions", "-d", help="Dimensions (comma-separated)")] = "country",
    metrics: Annotated[str, typer.Option("--metrics", "-m", help="Metrics (comma-separated)")] = "activeUsers",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max rows")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Run a realtime report.

    Examples:
        ga4 reports realtime 123456789
        ga4 reports realtime 123456789 -d country,city -m activeUsers
        ga4 reports realtime 123456789 --json
    """
    _require_auth(json_output)

    dim_list = [d.strip() for d in dimensions.split(",") if d.strip()]
    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]

    client = DataClient(profile=get_active_profile())
    try:
        report = client.run_realtime_report(
            property_id=property_id,
            dimensions=dim_list,
            metrics=metric_list,
            limit=limit,
        )
    except Exception as e:
        _error(f"Failed to run realtime report: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": report,
            "meta": {"property_id": property_id, "realtime": True},
        })
        return

    if not report.get("rows"):
        console.print("[yellow]No realtime data available[/yellow]")
        return

    table = Table(title=f"Realtime Report for Property {property_id}")
    all_headers = report["dimension_headers"] + report["metric_headers"]
    for header in all_headers:
        table.add_column(header)

    for row in report["rows"]:
        table.add_row(*[str(row.get(h, "")) for h in all_headers])

    console.print(table)





dimensions_app = typer.Typer(help="Dimension operations")
app.add_typer(dimensions_app, name="dimensions")


@dimensions_app.command("list")
def dimensions_list(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 50,
    category: Annotated[Optional[str], typer.Option("--category", "-c", help="Filter by category")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List available dimensions for a property.

    Examples:
        ga4 dimensions list 123456789
        ga4 dimensions list 123456789 --limit 100
        ga4 dimensions list 123456789 --category User
        ga4 dimensions list 123456789 --json | jq '.data[0]'
    """
    _require_auth(json_output)

    client = DataClient(profile=get_active_profile())
    try:
        items = client.list_dimensions(property_id, limit=limit)
    except Exception as e:
        _error(f"Failed to list dimensions: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    # Filter by category if specified
    if category:
        items = [i for i in items if category.lower() in i.get("category", "").lower()]

    if json_output:
        _output_json({
            "data": items,
            "meta": {"count": len(items), "property_id": property_id},
        })
        return

    if not items:
        console.print("[yellow]No dimensions found[/yellow]")
        return

    table = Table(title=f"Dimensions for Property {property_id}")
    table.add_column("API Name")
    table.add_column("Display Name")
    table.add_column("Category")

    for item in items:
        table.add_row(
            item.get("api_name", ""),
            item.get("name", ""),
            item.get("category", ""),
        )

    console.print(table)


@dimensions_app.command("get")
def dimensions_get(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    api_name: Annotated[str, typer.Argument(help="Dimension API name (e.g., 'city', 'date')")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get details for a specific dimension.

    Examples:
        ga4 dimensions get 123456789 city
        ga4 dimensions get 123456789 date --json
    """
    _require_auth(json_output)

    client = DataClient(profile=get_active_profile())
    try:
        item = client.get_dimension(property_id, api_name)
    except Exception as e:
        _error(f"Failed to get dimension: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if item is None:
        _error(
            f"Dimension not found: {api_name}",
            "NOT_FOUND",
            EXIT_NOT_FOUND,
            {"api_name": api_name, "property_id": property_id},
            json_output,
        )

    if json_output:
        _output_json({"data": item})
        return

    console.print(f"[bold]{item.get('name', 'Unknown')}[/bold]")
    console.print(f"  API Name: {item.get('api_name')}")
    console.print(f"  Category: {item.get('category', 'N/A')}")
    if item.get("description"):
        console.print(f"  Description: {item.get('description')}")





metrics_app = typer.Typer(help="Metric operations")
app.add_typer(metrics_app, name="metrics")


@metrics_app.command("list")
def metrics_list(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 50,
    category: Annotated[Optional[str], typer.Option("--category", "-c", help="Filter by category")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List available metrics for a property.

    Examples:
        ga4 metrics list 123456789
        ga4 metrics list 123456789 --limit 100
        ga4 metrics list 123456789 --category User
        ga4 metrics list 123456789 --json | jq '.data[0]'
    """
    _require_auth(json_output)

    client = DataClient(profile=get_active_profile())
    try:
        items = client.list_metrics(property_id, limit=limit)
    except Exception as e:
        _error(f"Failed to list metrics: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    # Filter by category if specified
    if category:
        items = [i for i in items if category.lower() in i.get("category", "").lower()]

    if json_output:
        _output_json({
            "data": items,
            "meta": {"count": len(items), "property_id": property_id},
        })
        return

    if not items:
        console.print("[yellow]No metrics found[/yellow]")
        return

    table = Table(title=f"Metrics for Property {property_id}")
    table.add_column("API Name")
    table.add_column("Display Name")
    table.add_column("Category")
    table.add_column("Type")

    for item in items:
        table.add_row(
            item.get("api_name", ""),
            item.get("name", ""),
            item.get("category", ""),
            item.get("type", ""),
        )

    console.print(table)


@metrics_app.command("get")
def metrics_get(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    api_name: Annotated[str, typer.Argument(help="Metric API name (e.g., 'activeUsers', 'sessions')")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get details for a specific metric.

    Examples:
        ga4 metrics get 123456789 activeUsers
        ga4 metrics get 123456789 sessions --json
    """
    _require_auth(json_output)

    client = DataClient(profile=get_active_profile())
    try:
        item = client.get_metric(property_id, api_name)
    except Exception as e:
        _error(f"Failed to get metric: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if item is None:
        _error(
            f"Metric not found: {api_name}",
            "NOT_FOUND",
            EXIT_NOT_FOUND,
            {"api_name": api_name, "property_id": property_id},
            json_output,
        )

    if json_output:
        _output_json({"data": item})
        return

    console.print(f"[bold]{item.get('name', 'Unknown')}[/bold]")
    console.print(f"  API Name: {item.get('api_name')}")
    console.print(f"  Category: {item.get('category', 'N/A')}")
    console.print(f"  Type: {item.get('type', 'N/A')}")
    if item.get("description"):
        console.print(f"  Description: {item.get('description')}")


# =============================================================================
# USERS COMMANDS (Analytics Admin API)
# =============================================================================
users_app = typer.Typer(help="User access management")
app.add_typer(users_app, name="users")


@users_app.command("list")
def users_list(
    property_id: Annotated[Optional[str], typer.Argument(help="Property ID")] = None,
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Account ID (account-level access)")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 200,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List users with access to a property or account.

    Account-level access cascades to all properties under the account.

    Examples:
        ga4 users list 123456789
        ga4 users list --account 123456789
        ga4 users list 123456789 --json
    """
    _require_auth(json_output)

    if not property_id and not account:
        _error("Provide a property ID or --account", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    if property_id and account:
        _error("Provide either a property ID or --account, not both", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)

    from .admin_client import AdminClient

    client = AdminClient(profile=get_active_profile())

    scope_type = "account" if account else "property"
    scope_id = account or property_id

    try:
        if account:
            users = client.list_account_access_bindings(account)
        else:
            users = client.list_access_bindings(property_id, limit=limit)
    except Exception as e:
        _error(f"Failed to list users: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    users = users[:limit]

    if json_output:
        meta = {"count": len(users), f"{scope_type}_id": scope_id}
        _output_json({"data": users, "meta": meta})
        return

    if not users:
        console.print(f"[yellow]No users found for {scope_type} {scope_id}[/yellow]")
        return

    table = Table(title=f"Users for {scope_type.title()} {scope_id}")
    table.add_column("Email")
    table.add_column("Role(s)")

    for user in users:
        table.add_row(user.get("user", ""), ", ".join(user.get("roles", [])))

    console.print(table)


@users_app.command("add")
def users_add(
    property_id: Annotated[Optional[str], typer.Argument(help="Property ID")] = None,
    email: Annotated[Optional[str], typer.Argument(help="User email address")] = None,
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Account ID (account-level access)")] = None,
    role: Annotated[str, typer.Option("--role", "-r", help="Role: viewer, analyst, editor, admin")] = "analyst",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without making changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Add a user to a property or account with specified role.

    Account-level access cascades to all properties under the account.

    Examples:
        ga4 users add 123456789 user@example.com --role analyst
        ga4 users add --account 123456789 user@example.com --role admin
        ga4 users add 123456789 user@example.com --role viewer --dry-run
    """
    _require_auth(json_output)

    # When --account is used, property_id positional slot holds the email
    if account and property_id and not email:
        email = property_id
        property_id = None

    if not email:
        _error("Email address is required", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    if not property_id and not account:
        _error("Provide a property ID or --account", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    if property_id and account:
        _error("Provide either a property ID or --account, not both", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)

    from .admin_client import AdminClient, ROLES

    scope_type = "account" if account else "property"
    scope_id = account or property_id

    # Validate role
    if role.lower() not in ROLES:
        _error(
            f"Invalid role: {role}. Must be one of: {', '.join(ROLES.keys())}",
            "VALIDATION_ERROR",
            EXIT_VALIDATION,
            {"role": role, "valid_roles": list(ROLES.keys())},
            json_output,
        )

    if dry_run:
        result = {
            "dry_run": True,
            "action": "create_access_binding",
            "scope": scope_type,
            "would_send": {
                f"{scope_type}_id": scope_id,
                "email": email,
                "role": role.lower(),
            },
        }
        if json_output:
            _output_json({"data": result})
        else:
            console.print(f"[cyan]Would add {email} as {role} to {scope_type} {scope_id}[/cyan]")
        return

    client = AdminClient(profile=get_active_profile())
    try:
        if account:
            binding = client.create_account_access_binding(account, email, role)
        else:
            binding = client.create_access_binding(property_id, email, role)
    except ValueError as e:
        _error(str(e), "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    except Exception as e:
        _error(f"Failed to add user: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": binding,
            "meta": {"action": "created", "scope": scope_type},
        })
        return

    console.print(f"[green]Added {email} as {role} to {scope_type} {scope_id}[/green]")


@users_app.command("remove")
def users_remove(
    property_id: Annotated[Optional[str], typer.Argument(help="Property ID")] = None,
    email: Annotated[Optional[str], typer.Argument(help="User email address")] = None,
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Account ID (account-level access)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without making changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Remove a user's access from a property or account.

    Examples:
        ga4 users remove 123456789 user@example.com
        ga4 users remove --account 123456789 user@example.com
        ga4 users remove 123456789 user@example.com --dry-run
    """
    _require_auth(json_output)

    # When --account is used, property_id positional slot holds the email
    if account and property_id and not email:
        email = property_id
        property_id = None

    if not email:
        _error("Email address is required", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    if not property_id and not account:
        _error("Provide a property ID or --account", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    if property_id and account:
        _error("Provide either a property ID or --account, not both", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)

    from .admin_client import AdminClient

    scope_type = "account" if account else "property"
    scope_id = account or property_id

    if dry_run:
        client = AdminClient(profile=get_active_profile())
        try:
            if account:
                bindings = client.list_account_access_bindings(account)
            else:
                bindings = client.list_access_bindings(property_id)
            binding = next((b for b in bindings if b["user"] == email), None)
        except Exception as e:
            _error(f"Failed to look up user: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

        if not binding:
            _error(f"User not found: {email}", "NOT_FOUND", EXIT_NOT_FOUND, {"email": email}, json_output)

        result = {
            "dry_run": True,
            "action": "delete_access_binding",
            "scope": scope_type,
            "would_remove": {
                "email": email,
                f"{scope_type}_id": scope_id,
                "roles": binding.get("roles", []),
            },
        }
        if json_output:
            _output_json({"data": result})
        else:
            roles = ", ".join(binding.get("roles", []))
            console.print(f"[cyan]Would remove {email} ({roles}) from {scope_type} {scope_id}[/cyan]")
        return

    client = AdminClient(profile=get_active_profile())
    try:
        if account:
            client.delete_account_access_binding(account, email)
        else:
            client.delete_access_binding(property_id, email)
    except ValueError as e:
        _error(str(e), "NOT_FOUND", EXIT_NOT_FOUND, {"email": email}, json_output)
    except Exception as e:
        _error(f"Failed to remove user: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": {"email": email, f"{scope_type}_id": scope_id},
            "meta": {"action": "deleted", "scope": scope_type},
        })
        return

    console.print(f"[green]Removed {email} from {scope_type} {scope_id}[/green]")


@users_app.command("copy")
def users_copy(
    source: Annotated[str, typer.Argument(help="Source property or account ID")],
    dest: Annotated[str, typer.Argument(help="Destination property or account ID")],
    account: Annotated[bool, typer.Option("--account", "-a", help="Treat IDs as account IDs")] = False,
    role: Annotated[Optional[str], typer.Option("--role", "-r", help="Filter by role")] = None,
    exclude: Annotated[Optional[str], typer.Option("--exclude", "-x", help="Emails to exclude (comma-separated)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without making changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Copy users from one property/account to another.

    Useful for migrating Looker Studio reports between orgs.

    Examples:
        ga4 users copy 123456789 987654321
        ga4 users copy --account 123456789 987654321
        ga4 users copy 123456789 987654321 --role analyst
        ga4 users copy 123456789 987654321 --dry-run
    """
    _require_auth(json_output)

    from .admin_client import AdminClient, ROLES

    scope_type = "account" if account else "property"

    # Validate role filter if provided
    if role and role.lower() not in ROLES:
        _error(
            f"Invalid role filter: {role}. Must be one of: {', '.join(ROLES.keys())}",
            "VALIDATION_ERROR",
            EXIT_VALIDATION,
            as_json=json_output,
        )

    client = AdminClient(profile=get_active_profile())

    # Get users from source
    try:
        if account:
            source_users = client.list_account_access_bindings(source)
        else:
            source_users = client.list_access_bindings(source)
    except Exception as e:
        _error(f"Failed to list users from source: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if not source_users:
        if json_output:
            _output_json({"data": [], "meta": {"message": f"No users found in source {scope_type}"}})
        else:
            console.print(f"[yellow]No users found in {scope_type} {source}[/yellow]")
        return

    # Parse exclusions
    excluded_emails = set()
    if exclude:
        excluded_emails = {e.strip().lower() for e in exclude.split(",")}

    # Filter users
    users_to_copy = []
    for user in source_users:
        email = user.get("user", "")
        user_roles = user.get("roles", [])

        if email.lower() in excluded_emails:
            continue

        if role and role.lower() not in [r.lower() for r in user_roles]:
            continue

        copy_role = user_roles[0] if user_roles else "viewer"
        users_to_copy.append({"email": email, "role": copy_role})

    if not users_to_copy:
        if json_output:
            _output_json({"data": [], "meta": {"message": "No users match criteria"}})
        else:
            console.print("[yellow]No users match the specified criteria[/yellow]")
        return

    if dry_run:
        if json_output:
            _output_json({
                "data": users_to_copy,
                "meta": {
                    "action": "dry_run",
                    "scope": scope_type,
                    f"source_{scope_type}": source,
                    f"dest_{scope_type}": dest,
                    "count": len(users_to_copy),
                },
            })
        else:
            console.print(f"[cyan]Would copy {len(users_to_copy)} users from {scope_type} {source} to {dest}:[/cyan]")
            table = Table()
            table.add_column("Email")
            table.add_column("Role")
            for u in users_to_copy:
                table.add_row(u["email"], u["role"])
            console.print(table)
        return

    # Execute copy
    try:
        if account:
            created = client.batch_create_account_access_bindings(dest, users_to_copy)
        else:
            created = client.batch_create_access_bindings(dest, users_to_copy)
    except Exception as e:
        _error(f"Failed to copy users: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": created,
            "meta": {
                "action": "copied",
                "scope": scope_type,
                f"source_{scope_type}": source,
                f"dest_{scope_type}": dest,
                "count": len(created),
            },
        })
    else:
        console.print(f"[green]Copied {len(created)} users from {scope_type} {source} to {dest}[/green]")


@users_app.command("batch-add")
def users_batch_add(
    target_id: Annotated[str, typer.Argument(help="Property or account ID")],
    file_path: Annotated[Path, typer.Argument(help="JSON or CSV file with users")],
    account: Annotated[bool, typer.Option("--account", "-a", help="Treat ID as account ID")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without making changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Add multiple users from a file.

    JSON format:
        [{"email": "user@example.com", "role": "analyst"}, ...]

    CSV format:
        email,role
        user@example.com,analyst

    Examples:
        ga4 users batch-add 123456789 users.json
        ga4 users batch-add --account 123456789 users.json
        ga4 users batch-add 123456789 users.csv --dry-run
    """
    _require_auth(json_output)

    from .admin_client import AdminClient, ROLES

    scope_type = "account" if account else "property"

    if not file_path.exists():
        _error(f"File not found: {file_path}", "NOT_FOUND", EXIT_NOT_FOUND, as_json=json_output)

    # Parse file based on extension
    users = []
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".json":
            with open(file_path) as f:
                users = json.load(f)
        elif suffix == ".csv":
            with open(file_path, newline="") as f:
                reader = csv.DictReader(f)
                users = [{"email": row["email"], "role": row.get("role", "viewer")} for row in reader]
        else:
            _error(
                f"Unsupported file format: {suffix}. Use .json or .csv",
                "VALIDATION_ERROR",
                EXIT_VALIDATION,
                as_json=json_output,
            )
    except (json.JSONDecodeError, KeyError, csv.Error) as e:
        _error(f"Failed to parse file: {e}", "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)

    if not users:
        if json_output:
            _output_json({"data": [], "meta": {"message": "No users in file"}})
        else:
            console.print("[yellow]No users found in file[/yellow]")
        return

    # Validate all roles
    invalid_roles = [u.get("role", "") for u in users if u.get("role", "").lower() not in ROLES]
    if invalid_roles:
        _error(
            f"Invalid roles found: {', '.join(set(invalid_roles))}. Valid: {', '.join(ROLES.keys())}",
            "VALIDATION_ERROR",
            EXIT_VALIDATION,
            as_json=json_output,
        )

    if dry_run:
        if json_output:
            _output_json({
                "data": users,
                "meta": {"action": "dry_run", "scope": scope_type, f"{scope_type}_id": target_id, "count": len(users)},
            })
        else:
            console.print(f"[cyan]Would add {len(users)} users to {scope_type} {target_id}:[/cyan]")
            table = Table()
            table.add_column("Email")
            table.add_column("Role")
            for u in users:
                table.add_row(u["email"], u.get("role", "viewer"))
            console.print(table)
        return

    client = AdminClient(profile=get_active_profile())
    try:
        if account:
            created = client.batch_create_account_access_bindings(target_id, users)
        else:
            created = client.batch_create_access_bindings(target_id, users)
    except Exception as e:
        _error(f"Failed to add users: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": created,
            "meta": {"action": "created", "scope": scope_type, f"{scope_type}_id": target_id, "count": len(created)},
        })
    else:
        console.print(f"[green]Added {len(created)} users to {scope_type} {target_id}[/green]")


if __name__ == "__main__":
    app()
