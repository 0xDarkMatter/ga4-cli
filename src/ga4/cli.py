"""ga4 CLI - Google Analytics 4 reporting and data analysis"""

from __future__ import annotations

import json
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .client import Client

from .config import get_tokens, clear_credentials, get_auth_status


app = typer.Typer(
    name="ga4",
    help="Google Analytics 4 reporting and data analysis",
    no_args_is_help=True,
)

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


def _output_json(data) -> None:
    """Output JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


def _error(
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
        _output_json(error_obj)

    console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(exit_code)


def _require_auth(as_json: bool = False):
    """Check authentication, exit if not authenticated."""

    tokens = get_tokens()
    if not tokens or not tokens.get("access_token"):

        _error(
            "Not authenticated. Run: ga4 auth login",
            "AUTH_REQUIRED",
            EXIT_AUTH_REQUIRED,
            as_json=as_json,
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
):
    """Google Analytics 4 reporting and data analysis"""
    pass


# =============================================================================
# AUTH COMMANDS
# =============================================================================
auth_app = typer.Typer(help="Authentication")
app.add_typer(auth_app, name="auth")


@auth_app.command("login")
def auth_login(

):
    """
    Authenticate with the service.

    Examples:
        ga4 auth login

    """

    # TODO: Implement OAuth2 flow
    console.print("[yellow]OAuth2 flow not implemented yet[/yellow]")
    console.print("Add your OAuth2 authentication logic in cli.py")



@auth_app.command("status")
def auth_status_cmd(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Check authentication status.

    Examples:
        ga4 auth status
        ga4 auth status --json
    """
    status = get_auth_status()

    if json_output:
        _output_json({"data": status})
        return

    if status.get("authenticated"):
        console.print("Authenticated: [green]yes[/green]")
        console.print(f"Source: [cyan]{status.get('source', 'unknown')}[/cyan]")

        if status.get("expired"):
            console.print("[yellow]Token expired - run auth login to refresh[/yellow]")
        elif status.get("expires_at"):
            console.print(f"Expires: {status['expires_at']}")

    else:
        console.print("Authenticated: [red]no[/red]")
        console.print("Run: ga4 auth login")


@auth_app.command("logout")
def auth_logout():
    """
    Clear stored credentials.

    Examples:
        ga4 auth logout
    """

    clear_credentials()

    console.print("[green]Logged out[/green]")


# =============================================================================
# RESOURCE COMMANDS
# =============================================================================



properties_app = typer.Typer(help="Propertie operations")
app.add_typer(properties_app, name="properties")


@properties_app.command("list")
def properties_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List properties.

    Examples:
        ga4 properties list
        ga4 properties list --limit 10
        ga4 properties list --json | jq '.data[0]'
    """
    _require_auth(json_output)

    client = Client()
    items = client.list_properties(limit=limit)

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

    for item in items:
        table.add_row(str(item.get("id", "")), item.get("name", ""))

    console.print(table)


@properties_app.command("get")
def properties_get(
    propertie_id: Annotated[str, typer.Argument(help="Propertie ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get a specific propertie by ID.

    Examples:
        ga4 properties get abc123
        ga4 properties get abc123 --json
    """
    _require_auth(json_output)

    client = Client()
    item = client.get_propertie(propertie_id)

    if item is None:
        _error(
            f"Propertie not found: {propertie_id}",
            "NOT_FOUND",
            EXIT_NOT_FOUND,
            {"propertie_id": propertie_id},
            json_output,
        )

    if json_output:
        _output_json({"data": item})
        return

    console.print(f"[bold]{item.get('name', 'Unknown')}[/bold]")
    console.print(f"  ID: {item.get('id')}")
    for key, value in item.items():
        if key not in ("id", "name"):
            console.print(f"  {key}: {value}")





reports_app = typer.Typer(help="Report operations")
app.add_typer(reports_app, name="reports")


@reports_app.command("list")
def reports_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List reports.

    Examples:
        ga4 reports list
        ga4 reports list --limit 10
        ga4 reports list --json | jq '.data[0]'
    """
    _require_auth(json_output)

    client = Client()
    items = client.list_reports(limit=limit)

    if json_output:
        _output_json({
            "data": items,
            "meta": {"count": len(items)},
        })
        return

    if not items:
        console.print("[yellow]No reports found[/yellow]")
        return

    table = Table(title="Reports")
    table.add_column("ID")
    table.add_column("Name")

    for item in items:
        table.add_row(str(item.get("id", "")), item.get("name", ""))

    console.print(table)


@reports_app.command("get")
def reports_get(
    report_id: Annotated[str, typer.Argument(help="Report ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get a specific report by ID.

    Examples:
        ga4 reports get abc123
        ga4 reports get abc123 --json
    """
    _require_auth(json_output)

    client = Client()
    item = client.get_report(report_id)

    if item is None:
        _error(
            f"Report not found: {report_id}",
            "NOT_FOUND",
            EXIT_NOT_FOUND,
            {"report_id": report_id},
            json_output,
        )

    if json_output:
        _output_json({"data": item})
        return

    console.print(f"[bold]{item.get('name', 'Unknown')}[/bold]")
    console.print(f"  ID: {item.get('id')}")
    for key, value in item.items():
        if key not in ("id", "name"):
            console.print(f"  {key}: {value}")





dimensions_app = typer.Typer(help="Dimension operations")
app.add_typer(dimensions_app, name="dimensions")


@dimensions_app.command("list")
def dimensions_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List dimensions.

    Examples:
        ga4 dimensions list
        ga4 dimensions list --limit 10
        ga4 dimensions list --json | jq '.data[0]'
    """
    _require_auth(json_output)

    client = Client()
    items = client.list_dimensions(limit=limit)

    if json_output:
        _output_json({
            "data": items,
            "meta": {"count": len(items)},
        })
        return

    if not items:
        console.print("[yellow]No dimensions found[/yellow]")
        return

    table = Table(title="Dimensions")
    table.add_column("ID")
    table.add_column("Name")

    for item in items:
        table.add_row(str(item.get("id", "")), item.get("name", ""))

    console.print(table)


@dimensions_app.command("get")
def dimensions_get(
    dimension_id: Annotated[str, typer.Argument(help="Dimension ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get a specific dimension by ID.

    Examples:
        ga4 dimensions get abc123
        ga4 dimensions get abc123 --json
    """
    _require_auth(json_output)

    client = Client()
    item = client.get_dimension(dimension_id)

    if item is None:
        _error(
            f"Dimension not found: {dimension_id}",
            "NOT_FOUND",
            EXIT_NOT_FOUND,
            {"dimension_id": dimension_id},
            json_output,
        )

    if json_output:
        _output_json({"data": item})
        return

    console.print(f"[bold]{item.get('name', 'Unknown')}[/bold]")
    console.print(f"  ID: {item.get('id')}")
    for key, value in item.items():
        if key not in ("id", "name"):
            console.print(f"  {key}: {value}")





metrics_app = typer.Typer(help="Metric operations")
app.add_typer(metrics_app, name="metrics")


@metrics_app.command("list")
def metrics_list(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List metrics.

    Examples:
        ga4 metrics list
        ga4 metrics list --limit 10
        ga4 metrics list --json | jq '.data[0]'
    """
    _require_auth(json_output)

    client = Client()
    items = client.list_metrics(limit=limit)

    if json_output:
        _output_json({
            "data": items,
            "meta": {"count": len(items)},
        })
        return

    if not items:
        console.print("[yellow]No metrics found[/yellow]")
        return

    table = Table(title="Metrics")
    table.add_column("ID")
    table.add_column("Name")

    for item in items:
        table.add_row(str(item.get("id", "")), item.get("name", ""))

    console.print(table)


@metrics_app.command("get")
def metrics_get(
    metric_id: Annotated[str, typer.Argument(help="Metric ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get a specific metric by ID.

    Examples:
        ga4 metrics get abc123
        ga4 metrics get abc123 --json
    """
    _require_auth(json_output)

    client = Client()
    item = client.get_metric(metric_id)

    if item is None:
        _error(
            f"Metric not found: {metric_id}",
            "NOT_FOUND",
            EXIT_NOT_FOUND,
            {"metric_id": metric_id},
            json_output,
        )

    if json_output:
        _output_json({"data": item})
        return

    console.print(f"[bold]{item.get('name', 'Unknown')}[/bold]")
    console.print(f"  ID: {item.get('id')}")
    for key, value in item.items():
        if key not in ("id", "name"):
            console.print(f"  {key}: {value}")



if __name__ == "__main__":
    app()
