"""ga4 CLI - Google Analytics 4 reporting and data analysis"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .client import Client

from .config import get_tokens, clear_credentials, get_auth_status, run_oauth_flow


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
    port: Annotated[int, typer.Option("--port", "-p", help="Local server port")] = 8080,
):
    """
    Authenticate with Google Analytics.

    Opens browser for OAuth2 authentication flow.

    Examples:
        ga4 auth login
        ga4 auth login --port 9000
    """
    try:
        console.print("Opening browser for authentication...")
        creds = run_oauth_flow(port=port)
        console.print("[green]Authenticated successfully![/green]")
    except FileNotFoundError as e:
        _error(str(e), "CONFIG_ERROR", EXIT_ERROR)
    except Exception as e:
        _error(f"Authentication failed: {e}", "AUTH_ERROR", EXIT_ERROR)



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

    client = AdminClient()
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

    client = AdminClient()
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
    _require_auth(json_output)

    from .admin_client import AdminClient

    client = AdminClient()
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


# =============================================================================
# USERS COMMANDS (Analytics Admin API)
# =============================================================================
users_app = typer.Typer(help="User access management")
app.add_typer(users_app, name="users")


@users_app.command("list")
def users_list(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List users with access to a property.

    Examples:
        ga4 users list 123456789
        ga4 users list 123456789 --json
    """
    _require_auth(json_output)

    from .admin_client import AdminClient

    client = AdminClient()
    try:
        users = client.list_access_bindings(property_id)
    except Exception as e:
        _error(f"Failed to list users: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": users,
            "meta": {"count": len(users), "property_id": property_id},
        })
        return

    if not users:
        console.print(f"[yellow]No users found for property {property_id}[/yellow]")
        return

    table = Table(title=f"Users for Property {property_id}")
    table.add_column("Email")
    table.add_column("Role(s)")

    for user in users:
        table.add_row(user.get("user", ""), ", ".join(user.get("roles", [])))

    console.print(table)


@users_app.command("add")
def users_add(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    email: Annotated[str, typer.Argument(help="User email address")],
    role: Annotated[str, typer.Option("--role", "-r", help="Role: viewer, analyst, editor, admin")] = "analyst",
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Add a user to a property with specified role.

    Examples:
        ga4 users add 123456789 user@example.com --role analyst
        ga4 users add 123456789 user@example.com -r viewer --json
    """
    _require_auth(json_output)

    from .admin_client import AdminClient, ROLES

    # Validate role
    if role.lower() not in ROLES:
        _error(
            f"Invalid role: {role}. Must be one of: {', '.join(ROLES.keys())}",
            "VALIDATION_ERROR",
            EXIT_VALIDATION,
            {"role": role, "valid_roles": list(ROLES.keys())},
            json_output,
        )

    client = AdminClient()
    try:
        binding = client.create_access_binding(property_id, email, role)
    except ValueError as e:
        _error(str(e), "VALIDATION_ERROR", EXIT_VALIDATION, as_json=json_output)
    except Exception as e:
        _error(f"Failed to add user: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": binding,
            "meta": {"action": "created"},
        })
        return

    console.print(f"[green]Added {email} as {role} to property {property_id}[/green]")


@users_app.command("remove")
def users_remove(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    email: Annotated[str, typer.Argument(help="User email address")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Remove a user's access from a property.

    Examples:
        ga4 users remove 123456789 user@example.com
        ga4 users remove 123456789 user@example.com --json
    """
    _require_auth(json_output)

    from .admin_client import AdminClient

    client = AdminClient()
    try:
        client.delete_access_binding(property_id, email)
    except ValueError as e:
        _error(str(e), "NOT_FOUND", EXIT_NOT_FOUND, {"email": email}, json_output)
    except Exception as e:
        _error(f"Failed to remove user: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": {"email": email, "property_id": property_id},
            "meta": {"action": "deleted"},
        })
        return

    console.print(f"[green]Removed {email} from property {property_id}[/green]")


@users_app.command("copy")
def users_copy(
    source_property: Annotated[str, typer.Argument(help="Source property ID")],
    dest_property: Annotated[str, typer.Argument(help="Destination property ID")],
    role: Annotated[Optional[str], typer.Option("--role", "-r", help="Filter by role")] = None,
    exclude: Annotated[Optional[str], typer.Option("--exclude", "-x", help="Emails to exclude (comma-separated)")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without making changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Copy users from one property to another.

    Useful for migrating Looker Studio reports between orgs.

    Examples:
        ga4 users copy 123456789 987654321
        ga4 users copy 123456789 987654321 --role analyst
        ga4 users copy 123456789 987654321 --dry-run
        ga4 users copy 123456789 987654321 --exclude admin@example.com,owner@example.com
    """
    _require_auth(json_output)

    from .admin_client import AdminClient, ROLES

    # Validate role filter if provided
    if role and role.lower() not in ROLES:
        _error(
            f"Invalid role filter: {role}. Must be one of: {', '.join(ROLES.keys())}",
            "VALIDATION_ERROR",
            EXIT_VALIDATION,
            as_json=json_output,
        )

    client = AdminClient()

    # Get users from source property
    try:
        source_users = client.list_access_bindings(source_property)
    except Exception as e:
        _error(f"Failed to list users from source: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if not source_users:
        if json_output:
            _output_json({"data": [], "meta": {"message": "No users found in source property"}})
        else:
            console.print(f"[yellow]No users found in property {source_property}[/yellow]")
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

        # Skip excluded emails
        if email.lower() in excluded_emails:
            continue

        # Filter by role if specified
        if role and role.lower() not in [r.lower() for r in user_roles]:
            continue

        # Use highest role from source
        copy_role = user_roles[0] if user_roles else "viewer"
        users_to_copy.append({"email": email, "role": copy_role})

    if not users_to_copy:
        if json_output:
            _output_json({"data": [], "meta": {"message": "No users match criteria"}})
        else:
            console.print("[yellow]No users match the specified criteria[/yellow]")
        return

    # Dry run - just show what would be copied
    if dry_run:
        if json_output:
            _output_json({
                "data": users_to_copy,
                "meta": {
                    "action": "dry_run",
                    "source_property": source_property,
                    "dest_property": dest_property,
                    "count": len(users_to_copy),
                },
            })
        else:
            console.print(f"[cyan]Would copy {len(users_to_copy)} users from {source_property} to {dest_property}:[/cyan]")
            table = Table()
            table.add_column("Email")
            table.add_column("Role")
            for u in users_to_copy:
                table.add_row(u["email"], u["role"])
            console.print(table)
        return

    # Execute copy
    try:
        created = client.batch_create_access_bindings(dest_property, users_to_copy)
    except Exception as e:
        _error(f"Failed to copy users: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": created,
            "meta": {
                "action": "copied",
                "source_property": source_property,
                "dest_property": dest_property,
                "count": len(created),
            },
        })
    else:
        console.print(f"[green]Copied {len(created)} users from {source_property} to {dest_property}[/green]")


@users_app.command("batch-add")
def users_batch_add(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    file_path: Annotated[Path, typer.Argument(help="JSON or CSV file with users")],
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
        ga4 users batch-add 123456789 users.csv --dry-run
    """
    _require_auth(json_output)

    from .admin_client import AdminClient, ROLES

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

    # Dry run
    if dry_run:
        if json_output:
            _output_json({
                "data": users,
                "meta": {"action": "dry_run", "property_id": property_id, "count": len(users)},
            })
        else:
            console.print(f"[cyan]Would add {len(users)} users to property {property_id}:[/cyan]")
            table = Table()
            table.add_column("Email")
            table.add_column("Role")
            for u in users:
                table.add_row(u["email"], u.get("role", "viewer"))
            console.print(table)
        return

    # Execute batch add
    client = AdminClient()
    try:
        created = client.batch_create_access_bindings(property_id, users)
    except Exception as e:
        _error(f"Failed to add users: {e}", "API_ERROR", EXIT_ERROR, as_json=json_output)

    if json_output:
        _output_json({
            "data": created,
            "meta": {"action": "created", "property_id": property_id, "count": len(created)},
        })
    else:
        console.print(f"[green]Added {len(created)} users to property {property_id}[/green]")


if __name__ == "__main__":
    app()
