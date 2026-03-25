"""ga4 bq - BigQuery export management and GA4-specific queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import typer
from rich.table import Table

from .admin_client import AdminClient
from .shared import (
    console, get_active_profile, handle_api_error, output_json,
    require_auth, validate_id,
)

bq_app = typer.Typer(help="BigQuery export management and GA4 queries")


# ---------------------------------------------------------------------------
# bq status
# ---------------------------------------------------------------------------

@bq_app.command("status")
def bq_status(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Show BigQuery export link status for a property.

    Displays linked GCP project, export types, excluded events, and streams.

    Examples:
        ga4 bq status 123456789
        ga4 bq status 123456789 --json
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)
    admin = AdminClient(profile=get_active_profile())

    try:
        links = admin.list_bigquery_links(property_id)
    except Exception as e:
        handle_api_error(e, "Failed to get BQ links", as_json=json_output)

    if json_output:
        output_json({"data": links, "meta": {"property_id": property_id, "count": len(links)}})
        return

    if not links:
        console.print(f"[yellow]No BigQuery links for property {property_id}[/yellow]")
        console.print("[dim]Use 'ga4 bq link' to create one[/dim]")
        return

    for link in links:
        link_id = link["name"].split("/")[-1]
        console.print(f"\n[bold]BigQuery Link[/bold] ({link_id})")
        console.print(f"  Project:        [cyan]{link['project']}[/cyan]")
        console.print(f"  Dataset:        [cyan]analytics_{property_id}[/cyan]")
        console.print(f"  Location:       {link['dataset_location']}")
        console.print(f"  Daily export:   {'[green]enabled[/green]' if link['daily_export'] else '[red]disabled[/red]'}")
        console.print(f"  Streaming:      {'[green]enabled[/green]' if link['streaming_export'] else '[dim]disabled[/dim]'}")
        console.print(f"  Fresh daily:    {'[green]enabled[/green]' if link['fresh_daily_export'] else '[dim]disabled[/dim]'}")

        if link.get("excluded_events"):
            console.print(f"  Excluded events: {', '.join(link['excluded_events'])}")
        if link.get("export_streams"):
            console.print(f"  Export streams:  {len(link['export_streams'])} stream(s)")


# ---------------------------------------------------------------------------
# bq link
# ---------------------------------------------------------------------------

@bq_app.command("link")
def bq_link(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    project: Annotated[str, typer.Option("--project", "-p", help="GCP project ID")] = "",
    location: Annotated[str, typer.Option("--location", "-l", help="Dataset location")] = "US",
    daily: Annotated[bool, typer.Option("--daily/--no-daily", help="Enable daily export")] = True,
    streaming: Annotated[bool, typer.Option("--streaming/--no-streaming", help="Enable streaming")] = False,
    fresh_daily: Annotated[bool, typer.Option("--fresh-daily/--no-fresh-daily", help="Enable fresh daily")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without creating")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Create a BigQuery export link for a property.

    Examples:
        ga4 bq link 123456789 --project my-gcp-project
        ga4 bq link 123456789 -p my-project --streaming --location us-east1
        ga4 bq link 123456789 -p my-project --dry-run
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)

    if not project:
        if json_output:
            output_json({"error": {"code": "VALIDATION_ERROR", "message": "--project is required"}})
        else:
            console.print("[red]Error: --project is required[/red]")
        raise typer.Exit(code=4)

    if dry_run:
        result = {
            "dry_run": True,
            "action": "create_bigquery_link",
            "would_send": {
                "property_id": property_id,
                "project": project,
                "location": location,
                "daily_export": daily,
                "streaming_export": streaming,
                "fresh_daily_export": fresh_daily,
            },
        }
        if json_output:
            output_json({"data": result})
        else:
            console.print(f"\n[bold yellow]DRY RUN[/bold yellow]")
            console.print(f"  Property:  {property_id}")
            console.print(f"  Project:   {project}")
            console.print(f"  Location:  {location}")
            console.print(f"  Daily:     {daily}")
            console.print(f"  Streaming: {streaming}")
            console.print(f"  Fresh:     {fresh_daily}")
        return

    admin = AdminClient(profile=get_active_profile())
    try:
        result = admin.create_bigquery_link(
            property_id, project,
            dataset_location=location, daily=daily,
            streaming=streaming, fresh_daily=fresh_daily,
        )
    except Exception as e:
        handle_api_error(e, "Failed to create BQ link", as_json=json_output)

    if json_output:
        output_json({"data": result, "meta": {"action": "created"}})
    else:
        console.print(f"\n[green]✓[/green] Created BQ link: {project}")
        console.print(f"  Dataset: analytics_{property_id} ({location})")


# ---------------------------------------------------------------------------
# bq freshness
# ---------------------------------------------------------------------------

@bq_app.command("freshness")
def bq_freshness(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="GCP project (auto-detected from link if omitted)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Check data freshness of GA4 BigQuery export.

    Reports the latest events_ and events_intraday_ table dates and lag.
    Auto-detects the GCP project from the BQ link unless --project is specified.

    Examples:
        ga4 bq freshness 123456789
        ga4 bq freshness 123456789 --project my-gcp-project
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)

    project = _resolve_project(property_id, project, json_output)

    from .bq_client import BQClient, ga4_dataset

    bq = BQClient(profile=get_active_profile())
    dataset = ga4_dataset(property_id)

    try:
        freshness = bq.get_freshness(project, dataset)
    except Exception as e:
        handle_api_error(e, "Failed to check freshness", as_json=json_output)

    if json_output:
        output_json({"data": freshness, "meta": {"property_id": property_id, "project": project}})
        return

    console.print(f"\n[bold]Data Freshness[/bold] — {project}.{dataset}")
    console.print(f"  Tables: {freshness['table_count']}")

    if freshness.get("latest_daily"):
        lag = freshness.get("daily_lag_hours", 0)
        color = "green" if lag < 48 else "yellow" if lag < 72 else "red"
        console.print(f"  Daily:    [{color}]{freshness['latest_daily']}[/{color}] ({lag:.0f}h ago)")
    else:
        console.print("  Daily:    [red]no data[/red]")

    if freshness.get("latest_intraday"):
        lag = freshness.get("intraday_lag_hours", 0)
        color = "green" if lag < 24 else "yellow" if lag < 48 else "red"
        console.print(f"  Intraday: [{color}]{freshness['latest_intraday']}[/{color}] ({lag:.0f}h ago)")
    else:
        console.print("  Intraday: [dim]no data (streaming not enabled?)[/dim]")


# ---------------------------------------------------------------------------
# bq audit
# ---------------------------------------------------------------------------

@bq_app.command("audit")
def bq_audit(
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Account ID")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Audit BigQuery export status across all properties.

    Scans all properties (or those in an account) and reports which have
    BQ links, which export types are enabled, and which are missing.

    Examples:
        ga4 bq audit
        ga4 bq audit --account 123456789
        ga4 bq audit --json
    """
    require_auth(json_output)
    admin = AdminClient(profile=get_active_profile())

    try:
        properties = admin.list_properties(account_id=account)
    except Exception as e:
        handle_api_error(e, "Failed to list properties", as_json=json_output)

    results = []
    for prop in properties:
        pid = prop["id"]
        try:
            links = admin.list_bigquery_links(pid)
        except Exception:
            links = []

        link = links[0] if links else None
        results.append({
            "property_id": pid,
            "property_name": prop["name"],
            "has_bq_link": bool(link),
            "project": link["project"] if link else None,
            "daily_export": link["daily_export"] if link else False,
            "streaming_export": link["streaming_export"] if link else False,
            "fresh_daily_export": link["fresh_daily_export"] if link else False,
            "excluded_events": len(link.get("excluded_events", [])) if link else 0,
        })

    if json_output:
        linked = sum(1 for r in results if r["has_bq_link"])
        output_json({
            "data": results,
            "meta": {
                "total": len(results),
                "linked": linked,
                "unlinked": len(results) - linked,
            },
        })
        return

    table = Table(title="BigQuery Export Audit")
    table.add_column("Property", min_width=20)
    table.add_column("ID", width=12)
    table.add_column("BQ Link", width=8)
    table.add_column("Project", min_width=15)
    table.add_column("Daily", width=6)
    table.add_column("Stream", width=6)
    table.add_column("Fresh", width=6)

    for r in results:
        bq_status = "[green]Yes[/green]" if r["has_bq_link"] else "[red]No[/red]"
        daily = "[green]✓[/green]" if r["daily_export"] else "[dim]—[/dim]"
        streaming = "[green]✓[/green]" if r["streaming_export"] else "[dim]—[/dim]"
        fresh = "[green]✓[/green]" if r["fresh_daily_export"] else "[dim]—[/dim]"
        table.add_row(
            r["property_name"], r["property_id"], bq_status,
            r["project"] or "", daily, streaming, fresh,
        )

    console.print(table)
    linked = sum(1 for r in results if r["has_bq_link"])
    console.print(f"\n[dim]{linked}/{len(results)} properties linked to BigQuery[/dim]")


# ---------------------------------------------------------------------------
# bq query
# ---------------------------------------------------------------------------

@bq_app.command("query")
def bq_query(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    template: Annotated[Optional[str], typer.Option("--template", "-t", help="Query template name")] = None,
    sql: Annotated[Optional[str], typer.Option("--sql", help="Raw SQL query")] = None,
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="GCP project")] = None,
    date_from: Annotated[str, typer.Option("--from", help="Start date (YYYY-MM-DD)")] = "",
    date_to: Annotated[str, typer.Option("--to", help="End date (YYYY-MM-DD)")] = "",
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Run a pre-built or custom query against GA4 BigQuery export.

    Templates: ai-traffic, sessions, top-pages, events, channels

    Examples:
        ga4 bq query 123456789 --template sessions
        ga4 bq query 123456789 -t ai-traffic --from 2025-01-01 --to 2025-01-31
        ga4 bq query 123456789 --sql "SELECT event_name, COUNT(*) FROM ..."
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)

    if not template and not sql:
        _bq_error("Provide --template or --sql", json_output)

    from .bq_client import BQClient, QUERY_TEMPLATES, ga4_dataset

    if template and template not in QUERY_TEMPLATES:
        names = ", ".join(QUERY_TEMPLATES.keys())
        _bq_error(f"Unknown template: {template}. Available: {names}", json_output)

    project = _resolve_project(property_id, project, json_output)
    dataset = ga4_dataset(property_id)
    start, end = _resolve_dates(date_from, date_to)

    if template:
        query_sql = QUERY_TEMPLATES[template]["sql"].format(
            project=project, dataset=dataset, start=start, end=end,
        )
    else:
        query_sql = sql

    bq = BQClient(profile=get_active_profile())
    try:
        result = bq.run_query(project, query_sql)
    except Exception as e:
        handle_api_error(e, "Query failed", as_json=json_output)

    if json_output:
        output_json({
            "data": result["rows"],
            "meta": {
                "total_rows": result["total_rows"],
                "total_bytes": result["total_bytes"],
                "cache_hit": result["cache_hit"],
                "template": template,
            },
        })
        return

    rows = result["rows"]
    if not rows:
        console.print("[yellow]No results[/yellow]")
        return

    table = Table(title=QUERY_TEMPLATES[template]["name"] if template else "Query Results")
    for col in rows[0].keys():
        table.add_column(col)
    for row in rows[:100]:
        table.add_row(*[str(v) for v in row.values()])
    console.print(table)
    console.print(f"\n[dim]{result['total_rows']} rows, {result['total_bytes']:,} bytes processed[/dim]")


# ---------------------------------------------------------------------------
# bq cost
# ---------------------------------------------------------------------------

@bq_app.command("cost")
def bq_cost(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    template: Annotated[Optional[str], typer.Option("--template", "-t", help="Query template name")] = None,
    sql: Annotated[Optional[str], typer.Option("--sql", help="Raw SQL query")] = None,
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="GCP project")] = None,
    date_from: Annotated[str, typer.Option("--from", help="Start date")] = "",
    date_to: Annotated[str, typer.Option("--to", help="End date")] = "",
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Estimate query cost without executing.

    Dry-runs the query and reports estimated bytes scanned and cost.

    Examples:
        ga4 bq cost 123456789 --template sessions
        ga4 bq cost 123456789 -t ai-traffic --from 2025-01-01 --to 2025-12-31
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)

    if not template and not sql:
        _bq_error("Provide --template or --sql", json_output)

    from .bq_client import BQClient, QUERY_TEMPLATES, ga4_dataset

    if template and template not in QUERY_TEMPLATES:
        names = ", ".join(QUERY_TEMPLATES.keys())
        _bq_error(f"Unknown template: {template}. Available: {names}", json_output)

    project = _resolve_project(property_id, project, json_output)
    dataset = ga4_dataset(property_id)
    start, end = _resolve_dates(date_from, date_to)

    if template:
        query_sql = QUERY_TEMPLATES[template]["sql"].format(
            project=project, dataset=dataset, start=start, end=end,
        )
    else:
        query_sql = sql

    bq = BQClient(profile=get_active_profile())
    try:
        result = bq.run_query(project, query_sql, dry_run=True)
    except Exception as e:
        handle_api_error(e, "Cost estimation failed", as_json=json_output)

    if json_output:
        output_json({"data": result, "meta": {"template": template, "property_id": property_id}})
        return

    console.print(f"\n[bold]Cost Estimate[/bold]")
    console.print(f"  Bytes:    {result['total_bytes']:,} ({result['total_mb']} MB)")
    console.print(f"  Cost:     ~${result['estimated_cost_usd']:.4f} USD")
    console.print(f"  [dim]Based on $6.25/TB on-demand pricing[/dim]")


# ---------------------------------------------------------------------------
# bq tables
# ---------------------------------------------------------------------------

@bq_app.command("tables")
def bq_tables(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="GCP project")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max tables to show")] = 30,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List tables in the GA4 BigQuery export dataset.

    Shows events_, events_intraday_, pseudonymous_users_, and other tables.

    Examples:
        ga4 bq tables 123456789
        ga4 bq tables 123456789 -n 10 --json
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)

    project = _resolve_project(property_id, project, json_output)

    from .bq_client import BQClient, ga4_dataset

    bq = BQClient(profile=get_active_profile())
    dataset = ga4_dataset(property_id)

    try:
        tables = bq.list_tables(project, dataset)
    except Exception as e:
        handle_api_error(e, "Failed to list tables", as_json=json_output)

    # Sort by table_id descending (most recent first)
    tables.sort(key=lambda t: t["table_id"], reverse=True)
    tables = tables[:limit]

    if json_output:
        output_json({"data": tables, "meta": {"project": project, "dataset": dataset}})
        return

    table = Table(title=f"{project}.{dataset}")
    table.add_column("Table")
    table.add_column("Type", width=10)
    table.add_column("Rows", justify="right")

    for t in tables:
        table.add_row(t["table_id"], t["type"], str(t.get("row_count", "")))

    console.print(table)
    console.print(f"\n[dim]Showing {len(tables)} tables[/dim]")


# ---------------------------------------------------------------------------
# bq schema
# ---------------------------------------------------------------------------

@bq_app.command("schema")
def bq_schema(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    table_name: Annotated[str, typer.Option("--table", "-t", help="Table name")] = "",
    project: Annotated[Optional[str], typer.Option("--project", "-p", help="GCP project")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Show schema of a GA4 BigQuery export table.

    Defaults to the latest events_ table if --table is not specified.

    Examples:
        ga4 bq schema 123456789
        ga4 bq schema 123456789 --table events_20250301
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)

    project = _resolve_project(property_id, project, json_output)

    from .bq_client import BQClient, ga4_dataset

    bq = BQClient(profile=get_active_profile())
    dataset = ga4_dataset(property_id)

    # Auto-detect latest events table if not specified
    if not table_name:
        try:
            tables = bq.list_tables(project, dataset)
        except Exception as e:
            handle_api_error(e, "Failed to list tables", as_json=json_output)

        daily_tables = [
            t for t in tables
            if t["table_id"].startswith("events_") and not t["table_id"].startswith("events_intraday_")
        ]
        if not daily_tables:
            _bq_error("No events tables found in dataset", json_output)
        daily_tables.sort(key=lambda t: t["table_id"], reverse=True)
        table_name = daily_tables[0]["table_id"]

    try:
        schema = bq.get_table_schema(project, dataset, table_name)
    except Exception as e:
        handle_api_error(e, "Failed to get schema", as_json=json_output)

    if json_output:
        output_json({"data": schema, "meta": {"project": project, "dataset": dataset}})
        return

    console.print(f"\n[bold]{table_name}[/bold] ({schema.get('row_count', '?')} rows)")

    table = Table()
    table.add_column("Field")
    table.add_column("Type", width=12)
    table.add_column("Mode", width=10)

    for f in schema.get("fields", []):
        table.add_row(f["name"], f["type"], f["mode"])

    console.print(table)


# ---------------------------------------------------------------------------
# bq datasets
# ---------------------------------------------------------------------------

@bq_app.command("datasets")
def bq_datasets(
    project: Annotated[str, typer.Argument(help="GCP project ID")],
    ga4_only: Annotated[bool, typer.Option("--ga4-only", help="Only show GA4 analytics_ datasets")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List datasets in a GCP project.

    Shows all datasets, or filter to GA4 analytics_ datasets only.

    Examples:
        ga4 bq datasets my-gcp-project
        ga4 bq datasets my-gcp-project --ga4-only
    """
    require_auth(json_output)

    from .bq_client import BQClient

    bq = BQClient(profile=get_active_profile())
    try:
        datasets = bq.list_datasets(project)
    except Exception as e:
        handle_api_error(e, "Failed to list datasets", as_json=json_output)

    if ga4_only:
        datasets = [d for d in datasets if d["is_ga4"]]

    if json_output:
        output_json({"data": datasets, "meta": {"project": project, "count": len(datasets)}})
        return

    if not datasets:
        console.print("[yellow]No datasets found[/yellow]")
        return

    table = Table(title=f"Datasets — {project}")
    table.add_column("Dataset")
    table.add_column("Location")
    table.add_column("GA4", width=5)

    for d in datasets:
        ga4_mark = "[green]✓[/green]" if d["is_ga4"] else ""
        table.add_row(d["dataset_id"], d["location"], ga4_mark)

    console.print(table)


# ---------------------------------------------------------------------------
# bq templates
# ---------------------------------------------------------------------------

@bq_app.command("templates")
def bq_templates(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List available query templates.

    Examples:
        ga4 bq templates
        ga4 bq templates --json
    """
    from .bq_client import QUERY_TEMPLATES

    templates = [
        {"name": k, "display_name": v["name"], "description": v["description"]}
        for k, v in QUERY_TEMPLATES.items()
    ]

    if json_output:
        output_json({"data": templates})
        return

    for t in templates:
        console.print(f"  [bold]{t['name']}[/bold] — {t['description']}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_project(
    property_id: str, project: str | None, json_output: bool,
) -> str:
    """Resolve GCP project from explicit flag or BQ link auto-detection."""
    if project:
        return project

    # Auto-detect from BQ link
    admin = AdminClient(profile=get_active_profile())
    try:
        links = admin.list_bigquery_links(property_id)
    except Exception:
        links = []

    if links:
        return links[0]["project"]

    _bq_error(
        "No --project specified and no BQ link found. "
        "Provide --project or create a BQ link first.",
        json_output,
    )
    return ""  # unreachable


def _resolve_dates(date_from: str, date_to: str) -> tuple[str, str]:
    """Resolve date range, defaulting to last 30 days."""
    if date_from and date_to:
        return date_from.replace("-", ""), date_to.replace("-", "")

    now = datetime.now(timezone.utc)
    end = now.strftime("%Y%m%d")
    start = (now - timedelta(days=30)).strftime("%Y%m%d")

    if date_from:
        start = date_from.replace("-", "")
    if date_to:
        end = date_to.replace("-", "")

    return start, end


def _bq_error(msg: str, json_output: bool):
    """Print error and exit."""
    if json_output:
        output_json({"error": {"message": msg}})
    else:
        console.print(f"[red]Error: {msg}[/red]")
    raise typer.Exit(code=1)
