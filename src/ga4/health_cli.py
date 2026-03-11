"""ga4 health - Property health diagnostics with async prefetch."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Annotated

import typer
from rich.table import Table

from .cache import Cache
from .checks import CheckResult, async_prefetch_context, calculate_score, run_checks
from .shared import console, handle_api_error, output_json, require_auth

health_app = typer.Typer(help="Property health diagnostics")


def _build_result_data(
    property_id: str,
    property_name: str,
    results: list[CheckResult],
    score_info: dict,
) -> dict:
    """Build the data portion of health check output."""
    return {
        "property_id": property_id,
        "property_name": property_name,
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


def _print_results_table(
    property_id: str,
    property_name: str,
    results: list[CheckResult],
    score_info: dict,
):
    """Print health check results as a Rich table."""
    title = f"Health Check: {property_name} ({property_id})" if property_name else f"Health Check: {property_id}"
    console.print(f"\n[bold]{title}[/bold]")

    score = score_info["score"]
    grade = score_info["grade"]
    grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "red"}.get(grade, "white")
    console.print(f"Score: [{grade_color}]{score}/100 ({grade})[/{grade_color}]")
    console.print()

    table = Table()
    table.add_column("Status", width=6)
    table.add_column("Check", min_width=20)
    table.add_column("Message")

    status_styles = {
        "pass": "[green]PASS[/green]",
        "warn": "[yellow]WARN[/yellow]",
        "fail": "[red]FAIL[/red]",
        "error": "[dim]ERR [/dim]",
    }

    for r in results:
        table.add_row(
            status_styles.get(r.status, r.status),
            r.name,
            r.message,
        )

    console.print(table)

    s = score_info["summary"]
    console.print(
        f"\n[dim]Summary: {s['pass']} pass, {s['warn']} warn, {s['fail']} fail, {s['error']} error[/dim]"
    )


async def _async_health_check(
    property_id: str,
    categories: list[str] | None,
    cache: Cache | None = None,
):
    """Run health check with async prefetch for concurrent API calls."""
    from .async_client import create_async_clients
    from .shared import get_active_profile

    admin, data = create_async_clients(profile=get_active_profile())
    async with admin, data:
        ctx = await async_prefetch_context(property_id, admin, data, categories=categories, cache=cache)
    results = run_checks(ctx, categories=categories)
    score_info = calculate_score(results)
    return ctx, results, score_info


def _run_health_check(
    property_id: str,
    categories: list[str] | None,
    json_output: bool,
    no_cache: bool = False,
):
    """Shared logic for all health commands. Uses async prefetch."""
    require_auth(json_output)

    cache = None if no_cache else Cache()
    start = time.time()
    if not json_output:
        console.print(f"[dim]Checking property {property_id}...[/dim]")

    try:
        ctx, results, score_info = asyncio.run(
            _async_health_check(property_id, categories, cache=cache)
        )
    except Exception as e:
        handle_api_error(e, "Health check failed", as_json=json_output)

    duration_ms = round((time.time() - start) * 1000)
    property_name = ctx.property_info.get("name", "")

    if json_output:
        output_json({
            "data": _build_result_data(property_id, property_name, results, score_info),
            "meta": {
                "property_id": property_id,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "check_count": len(results),
                "duration_ms": duration_ms,
            },
        })
        return

    _print_results_table(property_id, property_name, results, score_info)


@health_app.command("check")
def health_check(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Run full health check on a property.

    Checks tracking, access, and configuration using concurrent API calls.

    Examples:
        ga4 health check 123456789
        ga4 health check 123456789 --json
        ga4 health check 123456789 --json | jq '.data.score'
        ga4 health check 123456789 --no-cache
    """
    _run_health_check(property_id, categories=None, json_output=json_output, no_cache=no_cache)


@health_app.command("access")
def health_access(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Audit user access on a property.

    Checks user count, admin count, external domains, role distribution.

    Examples:
        ga4 health access 123456789
        ga4 health access 123456789 --json
    """
    _run_health_check(property_id, categories=["access"], json_output=json_output, no_cache=no_cache)


@health_app.command("tracking")
def health_tracking(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Check tracking and data quality for a property.

    Checks data recency, session volume, bounce rate, (not set) prevalence.

    Examples:
        ga4 health tracking 123456789
        ga4 health tracking 123456789 --json
    """
    _run_health_check(property_id, categories=["tracking"], json_output=json_output, no_cache=no_cache)


@health_app.command("summary")
def health_summary(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Quick one-line health summary for a property.

    Examples:
        ga4 health summary 123456789
        ga4 health summary 123456789 --json
    """
    require_auth(json_output)

    cache = None if no_cache else Cache()
    start = time.time()

    try:
        ctx, results, score_info = asyncio.run(
            _async_health_check(property_id, categories=None, cache=cache)
        )
    except Exception as e:
        handle_api_error(e, "Health check failed", as_json=json_output)

    property_name = ctx.property_info.get("name", "")

    if json_output:
        output_json({
            "data": {
                "property_id": property_id,
                "property_name": property_name,
                "score": score_info["score"],
                "grade": score_info["grade"],
                "summary": score_info["summary"],
            },
            "meta": {
                "property_id": property_id,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            },
        })
        return

    s = score_info["summary"]
    grade = score_info["grade"]
    score = score_info["score"]
    grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red", "F": "red"}.get(grade, "white")

    name_part = f"  {property_name}" if property_name else ""
    console.print(
        f"{property_id}{name_part}  "
        f"[{grade_color}]{score}/100 ({grade})[/{grade_color}]  "
        f"{s['pass']} pass, {s['warn']} warn, {s['fail']} fail"
    )


async def _async_health_report(property_id: str, spider_pages: int = 20, cache: Cache | None = None):
    """Run health check and site spider concurrently."""
    from .async_client import create_async_clients
    from .shared import get_active_profile
    from .spider import spider_site

    admin, data = create_async_clients(profile=get_active_profile())
    async with admin, data:
        ctx = await async_prefetch_context(property_id, admin, data, categories=None, cache=cache)

    results = run_checks(ctx, categories=None)
    score_info = calculate_score(results)

    # Spider the site if we have a web stream URL
    spider_result = None
    if spider_pages > 0 and ctx.data_streams:
        for stream in ctx.data_streams:
            site_url = stream.get("default_uri", "")
            if site_url and stream.get("type") == "WEB_DATA_STREAM":
                try:
                    spider_result = await spider_site(site_url, max_pages=spider_pages, cache=cache)
                except Exception:
                    pass
                break

    return ctx, results, score_info, spider_result


@health_app.command("report")
def health_report(
    property_id: Annotated[str, typer.Argument(help="Property ID")],
    output_dir: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = "output",
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    spider_pages: Annotated[int, typer.Option("--spider", help="Max pages to spider (0 to skip)")] = 20,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Skip cache, fetch fresh data")] = False,
):
    """
    Generate full markdown report for a property.

    Writes to output/{domain}-{property_id}/report.md with complete
    diagnostics, raw data tables, user listings, and site spider results.

    Examples:
        ga4 health report 123456789
        ga4 health report 123456789 --output reports
        ga4 health report 123456789 --spider 0   # skip spider
        ga4 health report 123456789 --no-cache
    """
    require_auth(json_output)

    cache = None if no_cache else Cache()
    start = time.time()
    if not json_output:
        console.print(f"[dim]Generating report for property {property_id}...[/dim]")

    try:
        ctx, results, score_info, spider_result = asyncio.run(
            _async_health_report(property_id, spider_pages=spider_pages, cache=cache)
        )
    except Exception as e:
        handle_api_error(e, "Report generation failed", as_json=json_output)

    duration_ms = round((time.time() - start) * 1000)
    property_name = ctx.property_info.get("name", "")

    from .report import write_property_report
    report_path = write_property_report(
        output_dir, property_id, property_name, results, score_info, ctx,
        duration_ms, spider_result=spider_result,
    )

    if json_output:
        output_json({
            "data": {
                "report_path": str(report_path),
                "property_id": property_id,
                "property_name": property_name,
                "score": score_info["score"],
                "grade": score_info["grade"],
            },
            "meta": {
                "property_id": property_id,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration_ms,
            },
        })
        return

    console.print(f"[green]Report written to {report_path}[/green]")
    _print_results_table(property_id, property_name, results, score_info)
