"""ga4 scan - Multi-property scanning with async concurrency."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Annotated, Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .cache import Cache
from .checks import async_prefetch_context, calculate_score, prefetch_context, run_checks
from .shared import console, get_active_profile, handle_api_error, output_json, require_auth, EXIT_ERROR

scan_app = typer.Typer(help="Multi-property scanning")

DEFAULT_WORKERS = 3


def _format_scan_output(
    all_results: list[dict],
    properties: list[dict],
    account: Optional[str],
    duration_ms: int,
    issues_only: bool,
    json_output: bool,
):
    """Format and display scan results (shared by sync and async paths)."""
    scores = [r["score"] for r in all_results]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    properties_with_issues = sum(
        1 for r in all_results
        if r["summary"].get("warn", 0) + r["summary"].get("fail", 0) + r["summary"].get("error", 0) > 0
    )

    overall = {
        "avg_score": avg_score,
        "total_properties": len(properties),
        "scanned": len(all_results),
        "properties_with_issues": properties_with_issues,
    }

    if json_output:
        output_json({
            "data": {
                "properties": all_results,
                "overall": overall,
            },
            "meta": {
                "account_id": account,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
            },
        })
        return

    # Human output - summary table
    console.print()
    table = Table(title=f"Scan Results ({len(all_results)} properties)")
    table.add_column("Property", min_width=20)
    table.add_column("Score", justify="right")
    table.add_column("Grade")
    table.add_column("Pass", justify="right")
    table.add_column("Warn", justify="right")
    table.add_column("Fail", justify="right")

    for r in sorted(all_results, key=lambda x: x["score"]):
        grade = r["grade"]
        grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "red"}.get(grade, "white")
        s = r["summary"]
        table.add_row(
            f"{r['property_name']} ({r['property_id']})" if r["property_name"] else r["property_id"],
            str(r["score"]),
            f"[{grade_color}]{grade}[/{grade_color}]",
            str(s.get("pass", 0)),
            f"[yellow]{s.get('warn', 0)}[/yellow]" if s.get("warn", 0) else "0",
            f"[red]{s.get('fail', 0)}[/red]" if s.get("fail", 0) else "0",
        )

    console.print(table)

    console.print(
        f"\n[dim]Overall: avg score {avg_score}/100, "
        f"{properties_with_issues}/{len(properties)} properties with issues, "
        f"{duration_ms}ms[/dim]"
    )

    # If issues_only and we have results, show the specific issues
    if issues_only and all_results:
        console.print()
        for r in all_results:
            name = r["property_name"] or r["property_id"]
            for check in r["checks"]:
                status_str = {"warn": "[yellow]WARN[/yellow]", "fail": "[red]FAIL[/red]", "error": "[dim]ERR[/dim]"}.get(
                    check["status"], check["status"]
                )
                console.print(f"  {status_str}  {name}: {check['message']}")


def _build_prop_data(prop_id, prop_name, results, score_info, issues_only):
    """Build a property result dict from check results."""
    prop_data = {
        "property_id": prop_id,
        "property_name": prop_name,
        "score": score_info["score"],
        "grade": score_info["grade"],
        "summary": score_info["summary"],
        "checks": [
            {
                "name": r.name,
                "category": r.category,
                "status": r.status,
                "message": r.message,
                "details": r.details,
            }
            for r in results
        ],
    }

    if issues_only:
        prop_data["checks"] = [
            c for c in prop_data["checks"] if c["status"] in ("warn", "fail", "error")
        ]
        if not prop_data["checks"]:
            return None

    return prop_data


def _build_error_data(prop_id, prop_name, error_msg):
    """Build error result dict for a failed property scan."""
    return {
        "property_id": prop_id,
        "property_name": prop_name,
        "score": 0,
        "grade": "F",
        "summary": {"pass": 0, "warn": 0, "fail": 0, "error": 1},
        "checks": [{"name": "scan_error", "category": "error", "status": "error", "message": error_msg, "details": {}}],
    }


async def _async_scan_property(
    prop: dict,
    admin_client,
    data_client,
    semaphore: asyncio.Semaphore,
    categories: Optional[list[str]],
    issues_only: bool,
    cache: Cache | None = None,
) -> Optional[dict]:
    """Scan a single property using async clients with semaphore limiting."""
    prop_id = prop.get("id", "")
    prop_name = prop.get("name", "")

    async with semaphore:
        try:
            ctx = await async_prefetch_context(prop_id, admin_client, data_client, categories=categories, cache=cache)
            results = run_checks(ctx, categories=categories)
            score_info = calculate_score(results)
            return _build_prop_data(prop_id, prop_name, results, score_info, issues_only)
        except Exception as e:
            return _build_error_data(prop_id, prop_name, str(e))


async def _async_scan_all(
    properties: list[dict],
    categories: Optional[list[str]],
    issues_only: bool,
    workers: int,
    cache: Cache | None = None,
) -> list[dict]:
    """Scan all properties concurrently with worker limit."""
    from .async_client import create_async_clients
    from .shared import get_active_profile

    admin, data = create_async_clients(profile=get_active_profile())
    semaphore = asyncio.Semaphore(workers)

    async with admin, data:
        tasks = [
            _async_scan_property(prop, admin, data, semaphore, categories, issues_only, cache=cache)
            for prop in properties
        ]
        results = await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


def _scan_properties(
    account: Optional[str],
    categories: Optional[list[str]],
    issues_only: bool,
    json_output: bool,
    workers: int = DEFAULT_WORKERS,
    no_cache: bool = False,
):
    """Shared logic for all scan commands. Uses async when workers > 1."""
    require_auth(json_output)

    from .admin_client import AdminClient

    admin = AdminClient(profile=get_active_profile())
    cache = None if no_cache else Cache()

    # Get all properties (sync — single paginated call)
    try:
        properties = admin.list_properties(account_id=account, limit=500)
    except Exception as e:
        handle_api_error(e, "Failed to list properties", as_json=json_output)

    if not properties:
        if json_output:
            output_json({"data": {"properties": [], "overall": {}}, "meta": {}})
        else:
            console.print("[yellow]No properties found[/yellow]")
        return

    start = time.time()

    if workers > 1:
        # Async path: concurrent property scanning
        console.print(f"[dim]Scanning {len(properties)} properties ({workers} workers)...[/dim]")
        all_results = asyncio.run(
            _async_scan_all(properties, categories, issues_only, workers, cache=cache)
        )
    else:
        # Sync path: sequential scanning with progress bar
        all_results = []
        from .client import DataClient
        data = DataClient(profile=get_active_profile())

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Scanning {len(properties)} properties...", total=len(properties)
            )

            for prop in properties:
                prop_id = prop.get("id", "")
                prop_name = prop.get("name", "")
                progress.update(task, description=f"Checking {prop_name or prop_id}...")

                try:
                    ctx = prefetch_context(prop_id, admin, data, categories=categories)
                    results = run_checks(ctx, categories=categories)
                    score_info = calculate_score(results)
                    prop_data = _build_prop_data(prop_id, prop_name, results, score_info, issues_only)
                    if prop_data is not None:
                        all_results.append(prop_data)
                except Exception as e:
                    all_results.append(_build_error_data(prop_id, prop_name, str(e)))

                progress.advance(task)

    duration_ms = round((time.time() - start) * 1000)
    _format_scan_output(all_results, properties, account, duration_ms, issues_only, json_output)


@scan_app.command("all")
def scan_all(
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Filter by account ID")] = None,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Concurrent workers (default 3)")] = DEFAULT_WORKERS,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Health check all properties.

    Runs full health checks across all accessible properties.
    Uses async concurrency with --workers N for faster scanning.

    Examples:
        ga4 scan all
        ga4 scan all --workers 5
        ga4 scan all --account 123456789
        ga4 scan all --json | jq '.data.overall'
        ga4 scan all --no-cache
    """
    _scan_properties(account, categories=None, issues_only=False, json_output=json_output, workers=workers, no_cache=no_cache)


@scan_app.command("access")
def scan_access(
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Filter by account ID")] = None,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Concurrent workers (default 3)")] = DEFAULT_WORKERS,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Access audit across all properties.

    Checks user access patterns across all properties.

    Examples:
        ga4 scan access
        ga4 scan access --account 123456789
        ga4 scan access --json
    """
    _scan_properties(account, categories=["access"], issues_only=False, json_output=json_output, workers=workers, no_cache=no_cache)


@scan_app.command("issues")
def scan_issues(
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Filter by account ID")] = None,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Concurrent workers (default 3)")] = DEFAULT_WORKERS,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Show only properties with issues.

    Scans all properties but only shows warnings and failures.

    Examples:
        ga4 scan issues
        ga4 scan issues --workers 5
        ga4 scan issues --json
    """
    _scan_properties(account, categories=None, issues_only=True, json_output=json_output, workers=workers, no_cache=no_cache)


@scan_app.command("report")
def scan_report(
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Filter by account ID")] = None,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Concurrent workers (default 3)")] = DEFAULT_WORKERS,
    output_dir: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = "output",
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Generate markdown reports for all properties.

    Writes a report per property to output/{domain}-{property_id}/report.md.

    Examples:
        ga4 scan report
        ga4 scan report --output reports
        ga4 scan report --account 123456789
        ga4 scan report --no-cache
    """
    require_auth(json_output)

    from .admin_client import AdminClient
    from .report import write_property_report

    admin = AdminClient(profile=get_active_profile())
    cache = None if no_cache else Cache()

    try:
        properties = admin.list_properties(account_id=account, limit=500)
    except Exception as e:
        handle_api_error(e, "Failed to list properties", as_json=json_output)

    if not properties:
        console.print("[yellow]No properties found[/yellow]")
        return

    start = time.time()
    console.print(f"[dim]Generating reports for {len(properties)} properties ({workers} workers)...[/dim]")

    # Use async prefetch for each property
    async def _generate_reports():
        from .async_client import create_async_clients
        from .shared import get_active_profile

        admin_async, data_async = create_async_clients(profile=get_active_profile())
        semaphore = asyncio.Semaphore(workers)
        report_paths = []

        async with admin_async, data_async:
            async def _do_one(prop):
                prop_id = prop.get("id", "")
                prop_name = prop.get("name", "")
                async with semaphore:
                    try:
                        ctx = await async_prefetch_context(
                            prop_id, admin_async, data_async, categories=None, cache=cache
                        )
                        results = run_checks(ctx, categories=None)
                        score_info = calculate_score(results)
                        path = write_property_report(
                            output_dir, prop_id, prop_name, results, score_info, ctx
                        )
                        report_paths.append({
                            "property_id": prop_id,
                            "property_name": prop_name,
                            "score": score_info["score"],
                            "grade": score_info["grade"],
                            "report_path": str(path),
                        })
                    except Exception as e:
                        report_paths.append({
                            "property_id": prop_id,
                            "property_name": prop_name,
                            "score": 0,
                            "grade": "F",
                            "report_path": None,
                            "error": str(e),
                        })

            await asyncio.gather(*[_do_one(p) for p in properties])

        return report_paths

    report_paths = asyncio.run(_generate_reports())
    duration_ms = round((time.time() - start) * 1000)

    if json_output:
        output_json({
            "data": {"reports": report_paths},
            "meta": {
                "account_id": account,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
            },
        })
        return

    console.print()
    for r in sorted(report_paths, key=lambda x: x.get("score", 0)):
        grade = r["grade"]
        grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "red"}.get(grade, "white")
        path = r.get("report_path", "FAILED")
        console.print(
            f"  [{grade_color}]{r['score']:>3}/100 ({grade})[/{grade_color}]  "
            f"{r['property_name'] or r['property_id']}  → {path}"
        )

    console.print(f"\n[dim]{len(report_paths)} reports generated in {duration_ms}ms[/dim]")


@scan_app.command("permissions")
def scan_permissions(
    account: Annotated[Optional[str], typer.Option("--account", "-a", help="Filter by account ID")] = None,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Concurrent workers")] = DEFAULT_WORKERS,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Cross-property permission matrix and inconsistency detection.

    Shows a user × property matrix highlighting:
    - Users with inconsistent roles across properties
    - Users with access to only some properties in an account
    - External users with elevated access
    - Properties with no dedicated admin

    Examples:
        ga4 scan permissions
        ga4 scan permissions --account 123456789
        ga4 scan permissions --json
    """
    require_auth(json_output)

    from .admin_client import AdminClient

    admin = AdminClient(profile=get_active_profile())

    try:
        properties = admin.list_properties(account_id=account, limit=500)
    except Exception as e:
        handle_api_error(e, "Failed to list properties", as_json=json_output)

    if not properties:
        if json_output:
            output_json({"data": {"users": [], "properties": [], "issues": []}, "meta": {}})
        else:
            console.print("[yellow]No properties found[/yellow]")
        return

    start = time.time()
    console.print(f"[dim]Scanning permissions across {len(properties)} properties ({workers} workers)...[/dim]")

    # Fetch access bindings for all properties + account-level
    async def _fetch_all_access():
        from .async_client import create_async_clients
        from .shared import get_active_profile

        admin_async, _ = create_async_clients(profile=get_active_profile())
        semaphore = asyncio.Semaphore(workers)
        prop_access = {}  # property_id -> list of bindings
        account_access = {}  # account_id -> list of bindings

        async with admin_async:
            async def _get_prop_access(prop):
                prop_id = prop.get("id", "")
                async with semaphore:
                    try:
                        bindings = await admin_async.list_access_bindings(prop_id)
                        prop_access[prop_id] = bindings
                    except Exception:
                        prop_access[prop_id] = []

                    # Also fetch account-level if we haven't yet
                    acc_id = prop.get("account", "")
                    if acc_id and acc_id not in account_access:
                        try:
                            account_access[acc_id] = await admin_async.list_account_access_bindings(acc_id)
                        except Exception:
                            account_access[acc_id] = []

            await asyncio.gather(*[_get_prop_access(p) for p in properties])

        return prop_access, account_access

    prop_access, account_access = asyncio.run(_fetch_all_access())

    # Build user → {property_id: roles} mapping
    user_matrix: dict[str, dict[str, list[str]]] = {}  # email -> {prop_id: [roles]}
    user_sources: dict[str, dict[str, str]] = {}  # email -> {prop_id: "property"|"account"}

    # Account-level bindings apply to all properties under that account
    for prop in properties:
        prop_id = prop.get("id", "")
        acc_id = prop.get("account", "")

        # Property-level bindings
        for b in prop_access.get(prop_id, []):
            email = b.get("user", "").lower()
            if not email:
                continue
            user_matrix.setdefault(email, {})[prop_id] = b.get("roles", [])
            user_sources.setdefault(email, {})[prop_id] = "property"

        # Account-level bindings (apply to all properties in that account)
        for b in account_access.get(acc_id, []):
            email = b.get("user", "").lower()
            if not email:
                continue
            if prop_id not in user_matrix.get(email, {}):
                user_matrix.setdefault(email, {})[prop_id] = b.get("roles", [])
                user_sources.setdefault(email, {})[prop_id] = "account"

    # Detect issues
    issues = []
    prop_ids = [p.get("id", "") for p in properties]
    prop_names = {p.get("id", ""): p.get("name", "") for p in properties}

    for email, access in user_matrix.items():
        # Inconsistent roles: user has different roles on different properties
        all_roles = set()
        for roles in access.values():
            all_roles.update(roles)
        if len(all_roles) > 1:
            role_details = {}
            for pid, roles in access.items():
                role_str = ", ".join(roles)
                role_details.setdefault(role_str, []).append(prop_names.get(pid, pid))
            issues.append({
                "type": "inconsistent_roles",
                "user": email,
                "message": f"{email} has inconsistent roles across properties",
                "details": {r: props for r, props in role_details.items()},
            })

        # Partial access: user has access to some but not all properties
        accessible = set(access.keys())
        missing = set(prop_ids) - accessible
        if missing and accessible:
            issues.append({
                "type": "partial_access",
                "user": email,
                "message": f"{email} has access to {len(accessible)}/{len(prop_ids)} properties",
                "details": {
                    "has_access": [prop_names.get(p, p) for p in sorted(accessible)],
                    "missing": [prop_names.get(p, p) for p in sorted(missing)],
                },
            })

    # External domain detection across properties
    domains_per_property: dict[str, set[str]] = {}
    for prop in properties:
        prop_id = prop.get("id", "")
        emails = [e for e in user_matrix if prop_id in user_matrix[e]]
        domains = set()
        for e in emails:
            parts = e.split("@")
            if len(parts) == 2:
                domains.add(parts[1])
        domains_per_property[prop_id] = domains

    # Find the primary domain per property (most common domain)
    for prop_id, domains in domains_per_property.items():
        if len(domains) > 1:
            domain_counts = {}
            for d in domains:
                domain_counts[d] = sum(
                    1 for e in user_matrix if prop_id in user_matrix[e] and e.endswith(f"@{d}")
                )
            primary = max(domain_counts, key=domain_counts.get)
            external = {d for d in domains if d != primary}
            for ext_domain in external:
                ext_users = [
                    e for e in user_matrix
                    if prop_id in user_matrix[e] and e.endswith(f"@{ext_domain}")
                ]
                for eu in ext_users:
                    roles = user_matrix[eu].get(prop_id, [])
                    if any(r in ("admin", "editor") for r in roles):
                        issues.append({
                            "type": "external_elevated",
                            "user": eu,
                            "message": f"{eu} ({ext_domain}) has elevated access on {prop_names.get(prop_id, prop_id)}",
                            "details": {
                                "property": prop_names.get(prop_id, prop_id),
                                "roles": roles,
                                "domain": ext_domain,
                            },
                        })

    duration_ms = round((time.time() - start) * 1000)

    if json_output:
        # Build matrix for JSON output
        matrix_data = []
        for email in sorted(user_matrix.keys()):
            entry = {"user": email, "properties": {}}
            for pid in prop_ids:
                if pid in user_matrix[email]:
                    entry["properties"][pid] = {
                        "roles": user_matrix[email][pid],
                        "source": user_sources.get(email, {}).get(pid, "unknown"),
                    }
            matrix_data.append(entry)

        output_json({
            "data": {
                "users": matrix_data,
                "properties": [{"id": p.get("id"), "name": p.get("name")} for p in properties],
                "issues": issues,
                "summary": {
                    "total_users": len(user_matrix),
                    "total_properties": len(properties),
                    "total_issues": len(issues),
                    "inconsistent_roles": sum(1 for i in issues if i["type"] == "inconsistent_roles"),
                    "partial_access": sum(1 for i in issues if i["type"] == "partial_access"),
                    "external_elevated": sum(1 for i in issues if i["type"] == "external_elevated"),
                },
            },
            "meta": {
                "account_id": account,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
            },
        })
        return

    # Human-readable output: permission matrix table
    console.print()

    # Build compact matrix table
    table = Table(title=f"Permission Matrix ({len(user_matrix)} users × {len(properties)} properties)")
    table.add_column("User", min_width=25)
    for prop in properties:
        # Truncate property names for table headers
        name = prop.get("name", prop.get("id", ""))
        if len(name) > 15:
            name = name[:13] + ".."
        table.add_column(name, justify="center", max_width=15)

    for email in sorted(user_matrix.keys()):
        row = [email]
        for prop in properties:
            pid = prop.get("id", "")
            if pid in user_matrix[email]:
                roles = user_matrix[email][pid]
                source = user_sources.get(email, {}).get(pid, "")
                role_str = ", ".join(roles)
                if source == "account":
                    role_str = f"[dim]{role_str}*[/dim]"
                if "admin" in roles:
                    role_str = f"[bold]{role_str}[/bold]"
                row.append(role_str)
            else:
                row.append("[red]—[/red]")
        table.add_row(*row)

    console.print(table)
    console.print("[dim]  * = inherited from account level[/dim]")

    # Show issues
    if issues:
        console.print(f"\n[bold]Issues Found ({len(issues)}):[/bold]")
        for issue in issues:
            icon = {
                "inconsistent_roles": "[yellow]INCONSISTENT[/yellow]",
                "partial_access": "[cyan]PARTIAL[/cyan]",
                "external_elevated": "[red]EXTERNAL[/red]",
            }.get(issue["type"], issue["type"])
            console.print(f"  {icon}  {issue['message']}")
    else:
        console.print("\n[green]No permission issues detected[/green]")

    console.print(f"\n[dim]{len(user_matrix)} users, {len(properties)} properties, {duration_ms}ms[/dim]")
