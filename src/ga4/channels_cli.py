"""ga4 channels - Custom channel group management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.table import Table

from .admin_client import AdminClient
from .shared import console, get_active_profile, handle_api_error, output_json, require_auth, validate_id

channels_app = typer.Typer(help="Custom channel group management")


# ---------------------------------------------------------------------------
# AI Traffic channel definition
# ---------------------------------------------------------------------------

# Regex matching known AI platform referral domains.
# Intended for sessionSource PARTIAL_REGEXP to catch AI-originated visits.
#
# NOTE: The GA4 Admin API (as of March 2026) only accepts
# 'eachScopeDefaultChannelGroup' as a filter field — sessionSource is rejected.
# This regex is kept as reference for manual UI channel group creation and for
# future API support. The API template uses eachScopeDefaultChannelGroup instead.
AI_TRAFFIC_REGEX = (
    r"chatgpt\.com|chat\.openai\.com|claude\.ai|perplexity\.ai|pplx\.ai"
    r"|gemini\.google\.com|copilot\.microsoft\.com|edgepilot|edgeservices"
    r"|deepseek\.com|meta\.ai|grok\.com|you\.com|phind\.com|poe\.com"
    r"|chat\.mistral\.ai"
)

# API-compatible AI Traffic channel — uses eachScopeDefaultChannelGroup.
# This matches traffic the system group classifies as "Referral", which
# includes AI platform visits. For source-level filtering (splitting AI
# referrals from regular referrals), use the GA4 UI or apply the regex above.
AI_TRAFFIC_CHANNEL = {
    "displayName": "AI Traffic",
    "expression": {
        "andGroup": {
            "filterExpressions": [
                {
                    "orGroup": {
                        "filterExpressions": [
                            {
                                "filter": {
                                    "fieldName": "eachScopeDefaultChannelGroup",
                                    "stringFilter": {
                                        "matchType": "EXACT",
                                        "value": "Referral",
                                    },
                                }
                            }
                        ]
                    }
                }
            ]
        }
    },
}


def _make_default_channel_rule(channel_name: str) -> dict:
    """Create a channel rule that matches on eachScopeDefaultChannelGroup.

    The GA4 Admin API only accepts 'eachScopeDefaultChannelGroup' as a field
    name in custom channel group filters. Other field names like sessionSource,
    sessionMedium, etc. are rejected with 'unsupported-channel-grouping-field'
    despite being documented — this is a known API limitation (as of March 2026).
    """
    return {
        "displayName": channel_name,
        "expression": {
            "andGroup": {
                "filterExpressions": [
                    {
                        "orGroup": {
                            "filterExpressions": [
                                {
                                    "filter": {
                                        "fieldName": "eachScopeDefaultChannelGroup",
                                        "stringFilter": {
                                            "matchType": "EXACT",
                                            "value": channel_name,
                                        },
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        },
    }


def _build_ai_traffic_group(default_rules: list) -> list:
    """Build channel rules with AI Traffic inserted above Referral.

    Re-expresses each default channel using eachScopeDefaultChannelGroup (the
    only field name the GA4 Admin API accepts for custom channel groups).
    Inserts an AI Traffic rule above Referral.

    NOTE: The API-created AI Traffic channel matches ALL Referral traffic (not
    just AI sources) because sessionSource filtering is unsupported by the API.
    For source-level AI traffic isolation, edit the channel group in the GA4 UI
    after creation, or create the group manually in the UI using the regex in
    AI_TRAFFIC_REGEX.
    """
    # Re-express each default channel with the allowed field name
    rules = [
        _make_default_channel_rule(rule.get("displayName", ""))
        for rule in default_rules
    ]

    # Find the Referral channel index
    referral_idx = None
    for i, rule in enumerate(rules):
        name = rule.get("displayName", "").lower()
        if name in ("referral", "referrals"):
            referral_idx = i
            break

    if referral_idx is not None:
        rules.insert(referral_idx, AI_TRAFFIC_CHANNEL)
    else:
        # Fallback: insert near the top (after Direct if present)
        insert_at = 0
        for i, rule in enumerate(rules):
            if rule.get("displayName", "").lower() == "direct":
                insert_at = i + 1
                break
        rules.insert(insert_at, AI_TRAFFIC_CHANNEL)

    return rules


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@channels_app.command("list")
def channels_list(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List channel groups for a property.

    Shows both system-defined and custom channel groups.

    Examples:
        ga4 channels list 309144142
        ga4 channels list 309144142 --json
    """
    require_auth(json_output)
    admin = AdminClient(profile=get_active_profile())

    try:
        groups = admin.list_channel_groups(property_id)
    except Exception as e:
        handle_api_error(e, "Failed to list channel groups", as_json=json_output)

    groups = groups[:limit]

    if json_output:
        output_json({
            "data": groups,
            "meta": {"property_id": property_id, "count": len(groups)},
        })
        return

    if not groups:
        console.print("[dim]No channel groups found[/dim]")
        return

    table = Table(title=f"Channel Groups — {property_id}")
    table.add_column("Name", min_width=20)
    table.add_column("Type", width=10)
    table.add_column("Primary", width=8)
    table.add_column("Channels", width=8)
    table.add_column("Description")

    for g in groups:
        group_type = "System" if g["system_defined"] else "Custom"
        primary = "Yes" if g["primary"] else ""
        channel_count = str(len(g.get("grouping_rule", [])))
        table.add_row(
            g["display_name"],
            group_type,
            primary,
            channel_count,
            g.get("description", ""),
        )

    console.print(table)
    console.print(f"\n[dim]{len(groups)} channel groups[/dim]")


@channels_app.command("get")
def channels_get(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    channel_group_id: Annotated[str, typer.Argument(help="Channel group ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Get details of a specific channel group.

    Examples:
        ga4 channels get 309144142 12345678
        ga4 channels get 309144142 12345678 --json
    """
    require_auth(json_output)
    admin = AdminClient(profile=get_active_profile())

    try:
        group = admin.get_channel_group(property_id, channel_group_id)
    except Exception as e:
        handle_api_error(e, "Failed to get channel group", as_json=json_output)

    if json_output:
        output_json({"data": group, "meta": {"property_id": property_id}})
        return

    console.print(f"\n[bold]{group['display_name']}[/bold]")
    console.print(f"  Type: {'System' if group['system_defined'] else 'Custom'}")
    console.print(f"  Primary: {'Yes' if group['primary'] else 'No'}")
    if group.get("description"):
        console.print(f"  Description: {group['description']}")

    rules = group.get("grouping_rule", [])
    if rules:
        console.print(f"\n  [bold]Channels ({len(rules)}):[/bold]")
        for rule in rules:
            console.print(f"    • {rule.get('displayName', 'unnamed')}")


@channels_app.command("create")
def channels_create(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Channel group name")] = None,
    template: Annotated[Optional[str], typer.Option("--template", "-t", help="Template: ai-traffic")] = None,
    from_file: Annotated[Optional[Path], typer.Option("--from-file", "-f", help="Load definition from JSON file")] = None,
    description: Annotated[str, typer.Option("--desc", help="Description")] = "",
    primary: Annotated[bool, typer.Option("--primary", help="Set as default for reports")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without creating")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Create a custom channel group.

    Use --template for built-in templates, --from-file for JSON definitions,
    or --name for an empty group. Standard properties support max 2 custom
    channel groups.

    Templates:
        ai-traffic — Clones the property's default channel group and inserts
                      an "AI Traffic" channel above Referral. Via API, this
                      matches all Referral traffic. For source-level filtering
                      (AI domains only), edit the group in the GA4 UI after
                      creation using the regex from `ga4 channels templates`.

    Examples:
        ga4 channels create 309144142 --template ai-traffic
        ga4 channels create 309144142 --template ai-traffic --primary --dry-run
        ga4 channels create 309144142 --from-file my-channels.json
    """
    validate_id(property_id, "property_id", json_output)
    require_auth(json_output)

    if not template and not name and not from_file:
        _error_exit("Provide --template, --from-file, or --name", json_output)

    admin = AdminClient(profile=get_active_profile())

    if template == "ai-traffic":
        display_name = name or "Default + AI Traffic"
        description = description or "Default channels with AI Traffic inserted above Referral"

        # Fetch the property's default (system) channel group
        if not json_output:
            console.print("[dim]Fetching default channel group...[/dim]")
        try:
            groups = admin.list_channel_groups(property_id)
        except Exception as e:
            handle_api_error(e, "Failed to list channel groups", as_json=json_output)

        default_group = next(
            (g for g in groups if g.get("system_defined") and g.get("primary")),
            None,
        )
        if not default_group:
            _error_exit("No system-defined primary channel group found", json_output)

        default_rules = default_group.get("grouping_rule", [])
        grouping_rule = _build_ai_traffic_group(default_rules)

    elif template:
        _error_exit(f"Unknown template: {template}. Available: ai-traffic", json_output)
    elif from_file:
        if not from_file.exists():
            _error_exit(f"File not found: {from_file}", json_output)
        defn = json.loads(from_file.read_text())
        display_name = name or defn.get("display_name", defn.get("displayName", ""))
        grouping_rule = defn.get("grouping_rule", defn.get("groupingRule", []))
        description = description or defn.get("description", "")
        if not display_name:
            _error_exit("JSON file must contain display_name", json_output)
    else:
        display_name = name
        grouping_rule = []
        if not description:
            description = ""

    if dry_run:
        if json_output:
            output_json({
                "data": {
                    "dry_run": True,
                    "display_name": display_name,
                    "description": description,
                    "primary": primary,
                    "channels": [r.get("displayName", "") for r in grouping_rule],
                },
            })
        else:
            console.print(f"\n[bold yellow]DRY RUN — no changes will be made[/bold yellow]\n")
            console.print(f"  Channel group: [cyan]{display_name}[/cyan]")
            console.print(f"  Description: {description}")
            console.print(f"  Primary: {'Yes' if primary else 'No'}")
            console.print(f"  Channels ({len(grouping_rule)}):")
            for i, rule in enumerate(grouping_rule, 1):
                marker = " [green]← NEW[/green]" if rule.get("displayName") == "AI Traffic" else ""
                console.print(f"    {i:2d}. {rule.get('displayName', 'unnamed')}{marker}")
        return

    try:
        result = admin.create_channel_group(
            property_id, display_name, grouping_rule,
            description=description, primary=primary,
        )
    except Exception as e:
        handle_api_error(e, "Failed to create channel group", as_json=json_output)

    if json_output:
        output_json({"data": result, "meta": {"property_id": property_id}})
        return

    console.print(f"\n[green]✓[/green] Created channel group: [cyan]{result['display_name']}[/cyan]")
    group_id = result["name"].split("/")[-1]
    console.print(f"  ID: {group_id}")
    console.print(f"  Channels: {len(result.get('grouping_rule', []))}")
    if primary:
        console.print("  [bold]Set as primary[/bold] — this group is now the default for reports")


@channels_app.command("export")
def channels_export(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    channel_group_id: Annotated[str, typer.Argument(help="Channel group ID")],
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output file path")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON to stdout")] = False,
):
    """
    Export a channel group to a reusable JSON file.

    The exported file can be used with `ga4 channels create --from-file`.

    Examples:
        ga4 channels export 309144142 12345678 -o ai-agents.json
        ga4 channels export 309144142 12345678 --json
    """
    require_auth(json_output)
    admin = AdminClient(profile=get_active_profile())

    try:
        group = admin.get_channel_group(property_id, channel_group_id)
    except Exception as e:
        handle_api_error(e, "Failed to get channel group", as_json=json_output)

    export = {
        "display_name": group["display_name"],
        "description": group.get("description", ""),
        "grouping_rule": group.get("grouping_rule", []),
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(export, indent=2))
        if not json_output:
            channels = len(export["grouping_rule"])
            console.print(f"[green]✓[/green] Exported '{export['display_name']}' ({channels} channels) to {output}")
        return

    if json_output:
        output_json({"data": export, "meta": {"property_id": property_id}})
    else:
        print(json.dumps(export, indent=2))


@channels_app.command("update")
def channels_update(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    channel_group_id: Annotated[str, typer.Argument(help="Channel group ID")],
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="New display name")] = None,
    from_file: Annotated[Optional[Path], typer.Option("--from-file", "-f", help="Update channels from JSON file")] = None,
    template: Annotated[Optional[str], typer.Option("--template", "-t", help="Update channels from template")] = None,
    description: Annotated[Optional[str], typer.Option("--desc", help="New description")] = None,
    primary: Annotated[Optional[bool], typer.Option("--primary/--no-primary", help="Set/unset as default")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without updating")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Update an existing custom channel group.

    Update channels from a template, JSON file, or change name/description.

    Examples:
        ga4 channels update 309144142 12345678 --template ai-traffic
        ga4 channels update 309144142 12345678 --from-file updated.json
        ga4 channels update 309144142 12345678 --name "New Name" --desc "New desc"
        ga4 channels update 309144142 12345678 --primary
    """
    require_auth(json_output)
    admin = AdminClient(profile=get_active_profile())

    # Resolve grouping_rule from file or template if provided
    grouping_rule = None
    if from_file:
        if not from_file.exists():
            _error_exit(f"File not found: {from_file}", json_output)
        defn = json.loads(from_file.read_text())
        grouping_rule = defn.get("grouping_rule", defn.get("groupingRule"))
        if name is None:
            name = defn.get("display_name", defn.get("displayName"))
        if description is None:
            description = defn.get("description")
    elif template == "ai-traffic":
        # Fetch default group and rebuild with AI Traffic
        try:
            groups = admin.list_channel_groups(property_id)
        except Exception as e:
            handle_api_error(e, "Failed to list channel groups", as_json=json_output)
        default_group = next(
            (g for g in groups if g.get("system_defined") and g.get("primary")), None,
        )
        if not default_group:
            _error_exit("No system-defined primary channel group found", json_output)
        grouping_rule = _build_ai_traffic_group(default_group.get("grouping_rule", []))
        if name is None:
            name = "Default + AI Traffic"
        if description is None:
            description = "Default channels with AI Traffic inserted above Referral"
    elif template:
        _error_exit(f"Unknown template: {template}. Available: ai-traffic", json_output)

    if name is None and grouping_rule is None and description is None and primary is None:
        _error_exit("Nothing to update. Provide --name, --template, --from-file, --desc, or --primary", json_output)

    if dry_run:
        changes = {}
        if name is not None:
            changes["display_name"] = name
        if description is not None:
            changes["description"] = description
        if primary is not None:
            changes["primary"] = primary
        if grouping_rule is not None:
            changes["channels"] = len(grouping_rule)

        if json_output:
            output_json({"data": {"dry_run": True, "changes": changes}})
        else:
            console.print("\n[bold yellow]DRY RUN — no changes will be made[/bold yellow]\n")
            for k, v in changes.items():
                console.print(f"  {k}: {v}")
        return

    try:
        result = admin.update_channel_group(
            property_id, channel_group_id,
            display_name=name, grouping_rule=grouping_rule,
            description=description, primary=primary,
        )
    except Exception as e:
        handle_api_error(e, "Failed to update channel group", as_json=json_output)

    if json_output:
        output_json({"data": result, "meta": {"property_id": property_id}})
        return

    console.print(f"\n[green]✓[/green] Updated channel group: [cyan]{result['display_name']}[/cyan]")
    console.print(f"  Channels: {len(result.get('grouping_rule', []))}")


@channels_app.command("delete")
def channels_delete(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    channel_group_id: Annotated[str, typer.Argument(help="Channel group ID")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without deleting")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Delete a custom channel group.

    System-defined channel groups cannot be deleted.

    Examples:
        ga4 channels delete 309144142 12345678
        ga4 channels delete 309144142 12345678 --dry-run
    """
    require_auth(json_output)
    admin = AdminClient(profile=get_active_profile())

    # Fetch to confirm it exists and show name
    try:
        group = admin.get_channel_group(property_id, channel_group_id)
    except Exception as e:
        handle_api_error(e, "Channel group not found", as_json=json_output)

    if group.get("system_defined"):
        _error_exit("Cannot delete system-defined channel groups", json_output)

    if dry_run:
        if json_output:
            output_json({"data": {"dry_run": True, "would_delete": group["display_name"]}})
        else:
            console.print(f"\n[bold yellow]DRY RUN[/bold yellow] — would delete: {group['display_name']}")
        return

    try:
        admin.delete_channel_group(property_id, channel_group_id)
    except Exception as e:
        handle_api_error(e, "Failed to delete channel group", as_json=json_output)

    if json_output:
        output_json({"data": {"deleted": True, "display_name": group["display_name"]}})
    else:
        console.print(f"\n[green]✓[/green] Deleted channel group: {group['display_name']}")


@channels_app.command("templates")
def channels_templates(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    List available built-in channel group templates.

    Examples:
        ga4 channels templates
        ga4 channels templates --json
    """
    templates = [
        {
            "name": "ai-traffic",
            "display_name": "Default + AI Traffic",
            "description": (
                "Clones the property's default channel group and inserts an "
                "'AI Traffic' channel above Referral. Via API, matches all "
                "Referral traffic. Edit in GA4 UI to apply source-level regex."
            ),
            "ai_domains_regex": AI_TRAFFIC_REGEX,
            "api_limitation": (
                "The GA4 Admin API only supports eachScopeDefaultChannelGroup "
                "as a filter field. To filter by AI domains specifically, edit "
                "the channel group in GA4 UI using the regex below."
            ),
        },
    ]

    if json_output:
        output_json({"data": templates})
        return

    for t in templates:
        console.print(f"\n[bold]{t['name']}[/bold] — {t['display_name']}")
        console.print(f"  {t['description']}")
        if t.get("api_limitation"):
            console.print(f"\n  [yellow]API limitation:[/yellow] {t['api_limitation']}")
        console.print(f"\n  [dim]Source regex (for GA4 UI):[/dim]")
        console.print(f"  [cyan]{t['ai_domains_regex']}[/cyan]")


def _error_exit(msg: str, json_output: bool):
    """Print error and exit."""
    if json_output:
        output_json({"error": {"message": msg}})
    else:
        console.print(f"[red]Error: {msg}[/red]")
    raise typer.Exit(code=1)
