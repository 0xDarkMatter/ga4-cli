"""ga4 schema - Export and deploy GA4 property schemas."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.table import Table

from .admin_client import AdminClient
from .shared import console, get_active_profile, handle_api_error, output_json, require_auth

schema_app = typer.Typer(help="Export and deploy property schemas")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _export_schema(property_id: str, admin: AdminClient) -> dict:
    """Read all schema resources from a property and return as a dict."""
    prop = admin.get_property(property_id)
    if not prop:
        raise typer.BadParameter(f"Property not found: {property_id}")

    streams = admin.list_data_streams(property_id)
    custom_dims = admin.list_custom_dimensions(property_id)
    custom_metrics = admin.list_custom_metrics(property_id)
    key_events = admin.list_key_events(property_id)
    audiences = admin.list_audiences(property_id)
    channel_groups = admin.list_channel_groups(property_id)
    retention = admin.get_data_retention_settings(property_id)

    # Enhanced measurement from first web stream
    enhanced = {}
    for s in streams:
        if s.get("type") == "WEB_DATA_STREAM":
            stream_id = s["name"].split("/")[-1]
            enhanced = admin.get_enhanced_measurement(property_id, stream_id)
            break

    # Only keep custom key events (skip built-ins like first_open, purchase)
    custom_key_events = [
        {
            "event_name": e["event_name"],
            "counting_method": e.get("counting_method", "ONCE_PER_EVENT"),
        }
        for e in key_events
        if e.get("custom", False)
    ]

    # Clean custom dimensions for export
    export_dims = [
        {
            "parameter_name": d["parameter_name"],
            "display_name": d["display_name"],
            "scope": d["scope"],
            "description": d.get("description", ""),
        }
        for d in custom_dims
    ]

    # Clean custom metrics for export
    export_metrics = [
        {
            "parameter_name": m["parameter_name"],
            "display_name": m["display_name"],
            "scope": m["scope"],
            "measurement_unit": m.get("measurement_unit", "STANDARD"),
            "description": m.get("description", ""),
        }
        for m in custom_metrics
    ]

    # Clean audiences — skip system defaults (All Users, Purchasers)
    system_audiences = {"All Users", "Purchasers"}
    export_audiences = [
        {
            "display_name": a["display_name"],
            "description": a.get("description", ""),
            "membership_duration_days": a.get("membership_duration_days"),
        }
        for a in audiences
        if a["display_name"] not in system_audiences
    ]

    # Custom channel groups only (skip system-defined)
    export_channel_groups = [
        {
            "display_name": g["display_name"],
            "description": g.get("description", ""),
            "primary": g.get("primary", False),
            "grouping_rule": g.get("grouping_rule", []),
        }
        for g in channel_groups
        if not g.get("system_defined", False)
    ]

    return {
        "schema_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_property": {
            "id": property_id,
            "name": prop.get("name", ""),
            "account": prop.get("account", ""),
            "time_zone": prop.get("time_zone", ""),
            "currency": prop.get("currency", ""),
            "industry_category": prop.get("industry_category", ""),
        },
        "custom_dimensions": export_dims,
        "custom_metrics": export_metrics,
        "key_events": custom_key_events,
        "audiences": export_audiences,
        "channel_groups": export_channel_groups,
        "enhanced_measurement": enhanced,
        "data_retention": retention,
    }


@schema_app.command("export")
def schema_export(
    property_id: Annotated[str, typer.Argument(help="Source property ID")],
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output file path")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON to stdout")] = False,
):
    """
    Export a property's schema to a JSON file.

    Captures custom dimensions, custom metrics, key events, audiences,
    enhanced measurement settings, and data retention. Use with
    `ga4 schema deploy` to replicate on new properties.

    Examples:
        ga4 schema export 309144142 -o roam-schema.json
        ga4 schema export 309144142 --json
        ga4 schema export 309144142 --json | jq '.custom_dimensions'
    """
    require_auth(json_output)

    admin = AdminClient(profile=get_active_profile())

    if not json_output:
        console.print(f"[dim]Exporting schema from property {property_id}...[/dim]")

    try:
        schema = _export_schema(property_id, admin)
    except Exception as e:
        handle_api_error(e, "Schema export failed", as_json=json_output)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(schema, indent=2))
        if not json_output:
            console.print(f"[green]Schema exported to {output}[/green]")
            _print_schema_summary(schema)
        return

    if json_output:
        output_json({"data": schema, "meta": {"property_id": property_id}})
    else:
        console.print(json.dumps(schema, indent=2))


def _print_schema_summary(schema: dict):
    """Print a human-readable summary of the schema."""
    src = schema.get("source_property", {})
    console.print(f"\n[bold]Schema: {src.get('name', '')} ({src.get('id', '')})[/bold]")

    table = Table()
    table.add_column("Resource", min_width=20)
    table.add_column("Count")
    table.add_column("Details")

    dims = schema.get("custom_dimensions", [])
    table.add_row("Custom Dimensions", str(len(dims)),
                  ", ".join(d["parameter_name"] for d in dims) if dims else "—")

    metrics = schema.get("custom_metrics", [])
    table.add_row("Custom Metrics", str(len(metrics)),
                  ", ".join(m["parameter_name"] for m in metrics) if metrics else "—")

    events = schema.get("key_events", [])
    table.add_row("Key Events", str(len(events)),
                  ", ".join(e["event_name"] for e in events) if events else "—")

    audiences = schema.get("audiences", [])
    table.add_row("Audiences", str(len(audiences)),
                  ", ".join(a["display_name"] for a in audiences) if audiences else "—")

    cgroups = schema.get("channel_groups", [])
    table.add_row("Channel Groups", str(len(cgroups)),
                  ", ".join(g["display_name"] for g in cgroups) if cgroups else "—")

    em = schema.get("enhanced_measurement", {})
    enabled = [k.replace("_enabled", "") for k, v in em.items()
               if k.endswith("_enabled") and v is True]
    table.add_row("Enhanced Measurement", str(len(enabled)),
                  ", ".join(enabled) if enabled else "—")

    ret = schema.get("data_retention", {})
    table.add_row("Data Retention", "",
                  ret.get("event_data_retention", "unknown"))

    console.print(table)


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

@schema_app.command("deploy")
def schema_deploy(
    schema_file: Annotated[Path, typer.Argument(help="Path to schema JSON file")],
    property_id: Annotated[Optional[str], typer.Option("--property", "-p", help="Deploy to existing property")] = None,
    account_id: Annotated[Optional[str], typer.Option("--account", "-a", help="Account for new property")] = None,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Display name for new property")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Website URL for new data stream")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created without making changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Deploy a schema to a new or existing GA4 property.

    Create a new property:
        ga4 schema deploy roam-schema.json --account 16621930 --name "newsite.com.au - GA4" --url https://www.newsite.com.au

    Apply to existing property:
        ga4 schema deploy roam-schema.json --property 123456789

    Dry run (preview only):
        ga4 schema deploy roam-schema.json --account 16621930 --name "test" --url https://test.com --dry-run
    """
    require_auth(json_output)

    if not schema_file.exists():
        _error_exit(f"Schema file not found: {schema_file}", json_output)

    schema = json.loads(schema_file.read_text())

    if schema.get("schema_version") != "1.0":
        _error_exit(f"Unsupported schema version: {schema.get('schema_version')}", json_output)

    # Validate arguments
    creating_new = property_id is None
    if creating_new:
        if not account_id:
            _error_exit("--account required when creating a new property", json_output)
        if not name:
            _error_exit("--name required when creating a new property", json_output)
        if not url:
            _error_exit("--url required when creating a new property (web data stream)", json_output)

    admin = AdminClient(profile=get_active_profile())
    src = schema.get("source_property", {})

    # Build the deploy plan
    plan = _build_deploy_plan(schema, property_id, account_id, name, url, creating_new)

    if dry_run:
        _print_dry_run(plan, schema, json_output)
        return

    if not json_output:
        console.print(f"[dim]Deploying schema from {src.get('name', 'unknown')}...[/dim]")

    results = _execute_deploy(admin, plan, schema, json_output)

    if json_output:
        output_json({
            "data": results,
            "meta": {
                "schema_source": src.get("id", ""),
                "deployed_at": datetime.now(timezone.utc).isoformat(),
            },
        })
    else:
        _print_deploy_results(results)


def _error_exit(msg: str, json_output: bool):
    """Print error and exit."""
    if json_output:
        output_json({"error": {"message": msg}})
    else:
        console.print(f"[red]Error: {msg}[/red]")
    raise typer.Exit(code=1)


def _build_deploy_plan(
    schema: dict, property_id: str | None, account_id: str | None,
    name: str | None, url: str | None, creating_new: bool,
) -> dict:
    """Build a plan of what will be created/updated."""
    src = schema.get("source_property", {})

    plan = {
        "creating_new": creating_new,
        "property_id": property_id,
        "account_id": account_id,
        "name": name,
        "url": url,
        "time_zone": src.get("time_zone", "Australia/Brisbane"),
        "currency": src.get("currency", "AUD"),
        "industry_category": src.get("industry_category", "TRAVEL"),
        "steps": [],
    }

    if creating_new:
        plan["steps"].append({"action": "create_property", "detail": name})
        plan["steps"].append({"action": "create_data_stream", "detail": url})

    for d in schema.get("custom_dimensions", []):
        plan["steps"].append({
            "action": "create_custom_dimension",
            "detail": f"{d['parameter_name']} ({d['scope']})",
        })

    for m in schema.get("custom_metrics", []):
        plan["steps"].append({
            "action": "create_custom_metric",
            "detail": f"{m['parameter_name']} ({m.get('measurement_unit', 'STANDARD')})",
        })

    for e in schema.get("key_events", []):
        plan["steps"].append({
            "action": "create_key_event",
            "detail": e["event_name"],
        })

    if schema.get("enhanced_measurement"):
        plan["steps"].append({
            "action": "update_enhanced_measurement",
            "detail": "Apply enhanced measurement settings",
        })

    if schema.get("data_retention"):
        plan["steps"].append({
            "action": "update_data_retention",
            "detail": schema["data_retention"].get("event_data_retention", ""),
        })

    for g in schema.get("channel_groups", []):
        plan["steps"].append({
            "action": "create_channel_group",
            "detail": f"{g['display_name']} ({len(g.get('grouping_rule', []))} channels)",
        })

    return plan


def _print_dry_run(plan: dict, schema: dict, json_output: bool):
    """Print what would happen without executing."""
    if json_output:
        output_json({"data": {"plan": plan, "schema": schema}})
        return

    console.print("\n[bold yellow]DRY RUN — no changes will be made[/bold yellow]\n")

    if plan["creating_new"]:
        console.print(f"  Create property: [cyan]{plan['name']}[/cyan]")
        console.print(f"  Account: {plan['account_id']}")
        console.print(f"  Data stream: {plan['url']}")
        console.print(f"  Timezone: {plan['time_zone']} / Currency: {plan['currency']}")
        console.print()

    table = Table(title="Deploy Steps")
    table.add_column("#", width=4)
    table.add_column("Action", min_width=25)
    table.add_column("Detail")

    for i, step in enumerate(plan["steps"], 1):
        action = step["action"].replace("_", " ").title()
        table.add_row(str(i), action, step["detail"])

    console.print(table)
    console.print(f"\n[dim]Total: {len(plan['steps'])} steps[/dim]")


def _execute_deploy(
    admin: AdminClient, plan: dict, schema: dict, json_output: bool,
) -> dict:
    """Execute the deploy plan step by step."""
    results = {
        "property_id": plan["property_id"],
        "stream_id": None,
        "measurement_id": None,
        "created": [],
        "skipped": [],
        "errors": [],
    }

    # Step 1: Create property if needed
    if plan["creating_new"]:
        try:
            prop = admin.create_property(
                plan["account_id"], plan["name"],
                time_zone=plan["time_zone"],
                currency=plan["currency"],
                industry_category=plan["industry_category"],
            )
            results["property_id"] = prop["id"]
            results["created"].append({"type": "property", "id": prop["id"], "name": prop["name"]})
            if not json_output:
                console.print(f"  [green]✓[/green] Created property: {prop['id']} ({prop['name']})")
        except Exception as e:
            results["errors"].append({"step": "create_property", "error": str(e)})
            if not json_output:
                console.print(f"  [red]✗[/red] Failed to create property: {e}")
            return results  # Can't continue without a property

        # Step 2: Create data stream
        try:
            stream = admin.create_data_stream(
                results["property_id"], plan["name"], plan["url"],
            )
            results["stream_id"] = stream["stream_id"]
            results["measurement_id"] = stream["measurement_id"]
            results["created"].append({
                "type": "data_stream",
                "measurement_id": stream["measurement_id"],
                "url": stream["default_uri"],
            })
            if not json_output:
                console.print(f"  [green]✓[/green] Created data stream: {stream['measurement_id']}")
        except Exception as e:
            results["errors"].append({"step": "create_data_stream", "error": str(e)})
            if not json_output:
                console.print(f"  [red]✗[/red] Failed to create data stream: {e}")
    else:
        # Get existing stream ID for enhanced measurement
        try:
            streams = admin.list_data_streams(results["property_id"])
            for s in streams:
                if s.get("type") == "WEB_DATA_STREAM":
                    results["stream_id"] = s["name"].split("/")[-1]
                    results["measurement_id"] = s.get("measurement_id", "")
                    break
        except Exception:
            pass

    pid = results["property_id"]

    # Custom dimensions
    for d in schema.get("custom_dimensions", []):
        try:
            r = admin.create_custom_dimension(
                pid, d["parameter_name"], d["display_name"],
                scope=d.get("scope", "EVENT"),
                description=d.get("description", ""),
            )
            results["created"].append({"type": "custom_dimension", "parameter": d["parameter_name"]})
            if not json_output:
                console.print(f"  [green]✓[/green] Custom dimension: {d['parameter_name']}")
        except Exception as e:
            err_msg = str(e)
            # Already exists is OK
            if "ALREADY_EXISTS" in err_msg or "409" in err_msg:
                results["skipped"].append({"type": "custom_dimension", "parameter": d["parameter_name"]})
                if not json_output:
                    console.print(f"  [dim]–[/dim] Custom dimension: {d['parameter_name']} (already exists)")
            else:
                results["errors"].append({"step": f"custom_dimension:{d['parameter_name']}", "error": err_msg})
                if not json_output:
                    console.print(f"  [red]✗[/red] Custom dimension {d['parameter_name']}: {err_msg}")

    # Custom metrics
    for m in schema.get("custom_metrics", []):
        try:
            admin.create_custom_metric(
                pid, m["parameter_name"], m["display_name"],
                scope=m.get("scope", "EVENT"),
                measurement_unit=m.get("measurement_unit", "STANDARD"),
                description=m.get("description", ""),
            )
            results["created"].append({"type": "custom_metric", "parameter": m["parameter_name"]})
            if not json_output:
                console.print(f"  [green]✓[/green] Custom metric: {m['parameter_name']}")
        except Exception as e:
            err_msg = str(e)
            if "ALREADY_EXISTS" in err_msg or "409" in err_msg:
                results["skipped"].append({"type": "custom_metric", "parameter": m["parameter_name"]})
                if not json_output:
                    console.print(f"  [dim]–[/dim] Custom metric: {m['parameter_name']} (already exists)")
            else:
                results["errors"].append({"step": f"custom_metric:{m['parameter_name']}", "error": err_msg})
                if not json_output:
                    console.print(f"  [red]✗[/red] Custom metric {m['parameter_name']}: {err_msg}")

    # Key events
    for e in schema.get("key_events", []):
        try:
            admin.create_key_event(
                pid, e["event_name"],
                counting_method=e.get("counting_method", "ONCE_PER_EVENT"),
            )
            results["created"].append({"type": "key_event", "event_name": e["event_name"]})
            if not json_output:
                console.print(f"  [green]✓[/green] Key event: {e['event_name']}")
        except Exception as e_err:
            err_msg = str(e_err)
            if "ALREADY_EXISTS" in err_msg or "409" in err_msg:
                results["skipped"].append({"type": "key_event", "event_name": e["event_name"]})
                if not json_output:
                    console.print(f"  [dim]–[/dim] Key event: {e['event_name']} (already exists)")
            else:
                results["errors"].append({"step": f"key_event:{e['event_name']}", "error": err_msg})
                if not json_output:
                    console.print(f"  [red]✗[/red] Key event {e['event_name']}: {err_msg}")

    # Enhanced measurement
    em = schema.get("enhanced_measurement", {})
    if em and results["stream_id"]:
        try:
            admin.update_enhanced_measurement(pid, results["stream_id"], em)
            results["created"].append({"type": "enhanced_measurement", "applied": True})
            if not json_output:
                console.print("  [green]✓[/green] Enhanced measurement settings applied")
        except Exception as e:
            results["errors"].append({"step": "enhanced_measurement", "error": str(e)})
            if not json_output:
                console.print(f"  [red]✗[/red] Enhanced measurement: {e}")

    # Data retention
    ret = schema.get("data_retention", {})
    if ret and ret.get("event_data_retention"):
        try:
            admin.update_data_retention_settings(
                pid,
                event_retention=ret["event_data_retention"],
                reset_on_new_activity=ret.get("reset_on_new_activity", True),
            )
            results["created"].append({"type": "data_retention", "setting": ret["event_data_retention"]})
            if not json_output:
                console.print(f"  [green]✓[/green] Data retention: {ret['event_data_retention']}")
        except Exception as e:
            results["errors"].append({"step": "data_retention", "error": str(e)})
            if not json_output:
                console.print(f"  [red]✗[/red] Data retention: {e}")

    # Channel groups — deduplicate by display name since the API doesn't
    schema_groups = schema.get("channel_groups", [])
    if schema_groups:
        try:
            existing_groups = admin.list_channel_groups(pid)
            existing_names = {g["display_name"] for g in existing_groups}
        except Exception:
            existing_names = set()

        for g in schema_groups:
            if g["display_name"] in existing_names:
                results["skipped"].append({"type": "channel_group", "name": g["display_name"]})
                if not json_output:
                    console.print(f"  [dim]–[/dim] Channel group: {g['display_name']} (already exists)")
                continue
            try:
                admin.create_channel_group(
                    pid, g["display_name"], g.get("grouping_rule", []),
                    description=g.get("description", ""),
                    primary=g.get("primary", False),
                )
                results["created"].append({"type": "channel_group", "name": g["display_name"]})
                if not json_output:
                    console.print(f"  [green]✓[/green] Channel group: {g['display_name']}")
            except Exception as e:
                err_msg = str(e)
                results["errors"].append({"step": f"channel_group:{g['display_name']}", "error": err_msg})
                if not json_output:
                    console.print(f"  [red]✗[/red] Channel group {g['display_name']}: {err_msg}")

    return results


def _print_deploy_results(results: dict):
    """Print deploy results summary."""
    console.print()
    pid = results["property_id"]
    mid = results.get("measurement_id", "")

    console.print(f"[bold]Deploy Complete: {pid}[/bold]")
    if mid:
        console.print(f"Measurement ID: [cyan]{mid}[/cyan]")

    created = len(results["created"])
    skipped = len(results.get("skipped", []))
    errors = len(results["errors"])

    parts = [f"[green]{created} created[/green]"]
    if skipped:
        parts.append(f"[dim]{skipped} skipped[/dim]")
    if errors:
        parts.append(f"[red]{errors} errors[/red]")
    console.print(f"\n{', '.join(parts)}")
