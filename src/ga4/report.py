"""Markdown report generator for GA4 health checks."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .checks import CheckContext, CheckResult
from .spider import SpiderResult


def _domain_from_name(property_name: str) -> str:
    """Extract domain slug from property name for directory naming."""
    name = property_name.lower()
    # Strip common suffixes
    name = re.sub(r"\s*-\s*ga4\s*$", "", name, flags=re.IGNORECASE)
    # Extract domain if URL-like
    match = re.search(r"(?:https?://)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})", name)
    if match:
        return match.group(1).replace(".", "-")
    # Fall back to slugified name
    slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return slug or "unknown"


def property_dir_name(property_name: str, property_id: str) -> str:
    """Generate directory name: {domain}-{property_id}."""
    domain = _domain_from_name(property_name)
    return f"{domain}-{property_id}"


def generate_report(
    property_id: str,
    property_name: str,
    results: list[CheckResult],
    score_info: dict,
    ctx: CheckContext,
    duration_ms: int = 0,
    spider_result: SpiderResult | None = None,
) -> str:
    """Generate a full markdown health report for a property."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    grade = score_info["grade"]
    score = score_info["score"]
    summary = score_info["summary"]

    lines = []
    lines.append(f"# Health Report: {property_name or property_id}")
    lines.append("")
    lines.append(f"**Property ID:** {property_id}  ")
    lines.append(f"**Generated:** {now}  ")
    if duration_ms:
        lines.append(f"**Scan Duration:** {duration_ms}ms  ")
    lines.append("")

    # Score banner
    lines.append("## Score")
    lines.append("")
    lines.append(f"**{score}/100 ({grade})**")
    lines.append("")
    lines.append(f"| Pass | Warn | Fail | Error |")
    lines.append(f"|------|------|------|-------|")
    lines.append(f"| {summary['pass']} | {summary['warn']} | {summary['fail']} | {summary['error']} |")
    lines.append("")

    # Property info
    info = ctx.property_info
    if info:
        lines.append("## Property Configuration")
        lines.append("")
        lines.append("| Setting | Value |")
        lines.append("|---------|-------|")
        lines.append(f"| Account | {info.get('account', 'N/A')} |")
        lines.append(f"| Time Zone | {info.get('time_zone', 'Not set')} |")
        lines.append(f"| Currency | {info.get('currency', 'Not set')} |")
        lines.append(f"| Industry | {info.get('industry_category', 'Not set')} |")
        lines.append(f"| Created | {info.get('create_time', 'N/A')} |")
        lines.append(f"| Updated | {info.get('update_time', 'N/A')} |")
        lines.append("")

    # Check results grouped by category
    categories = {"tracking": "Tracking & Data Quality", "config": "Configuration", "access": "Access & Security"}
    for cat_key, cat_title in categories.items():
        cat_results = [r for r in results if r.category == cat_key]
        if not cat_results:
            continue

        lines.append(f"## {cat_title}")
        lines.append("")
        lines.append("| Status | Check | Message |")
        lines.append("|--------|-------|---------|")
        for r in cat_results:
            status_icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "error": "ERR"}.get(r.status, r.status)
            lines.append(f"| {status_icon} | {r.name} | {r.message} |")
        lines.append("")

        # Add details for non-pass checks
        detail_checks = [r for r in cat_results if r.status != "pass" and r.details]
        if detail_checks:
            lines.append("### Details")
            lines.append("")
            for r in detail_checks:
                lines.append(f"**{r.name}** ({r.status.upper()}): {r.message}")
                lines.append("")
                for k, v in r.details.items():
                    if isinstance(v, list) and len(v) > 5:
                        lines.append(f"- {k}: {len(v)} items")
                    else:
                        lines.append(f"- {k}: {v}")
                lines.append("")

    # Raw data summary
    lines.append("## Raw Data Summary")
    lines.append("")

    # Weekly traffic
    if ctx.weekly_report and ctx.weekly_report.get("rows"):
        lines.append("### 7-Day Traffic")
        lines.append("")
        lines.append("| Date | Sessions | Bounce Rate |")
        lines.append("|------|----------|-------------|")
        for row in sorted(ctx.weekly_report["rows"], key=lambda r: r.get("date", "")):
            date = row.get("date", "")
            sessions = row.get("sessions", "0")
            bounce = row.get("bounceRate", "")
            if bounce:
                try:
                    br = float(bounce)
                    bounce_str = f"{br * 100:.1f}%" if br <= 1.0 else f"{br:.1f}%"
                except (ValueError, TypeError):
                    bounce_str = bounce
            else:
                bounce_str = "N/A"
            lines.append(f"| {date} | {sessions} | {bounce_str} |")
        lines.append("")

    # 30-day engagement
    if ctx.engagement_report and ctx.engagement_report.get("rows"):
        rows = sorted(ctx.engagement_report["rows"], key=lambda r: r.get("date", ""))
        total_sessions = sum(int(r.get("sessions", 0)) for r in rows)
        total_engaged = sum(int(r.get("engagedSessions", 0)) for r in rows)
        total_users = sum(int(r.get("totalUsers", 0)) for r in rows)
        total_events = sum(int(r.get("eventCount", 0)) for r in rows)
        total_pages = sum(int(r.get("screenPageViews", 0)) for r in rows)

        lines.append("### 30-Day Engagement Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Sessions | {total_sessions:,} |")
        lines.append(f"| Engaged Sessions | {total_engaged:,} |")
        eng_rate = (total_engaged / total_sessions * 100) if total_sessions else 0
        lines.append(f"| Engagement Rate | {eng_rate:.1f}% |")
        lines.append(f"| Total Users | {total_users:,} |")
        lines.append(f"| Total Events | {total_events:,} |")
        lines.append(f"| Total Pageviews | {total_pages:,} |")
        if total_sessions:
            lines.append(f"| Events/Session | {total_events / total_sessions:.1f} |")
            lines.append(f"| Pages/Session | {total_pages / total_sessions:.1f} |")
        lines.append("")

    # Source breakdown
    if ctx.source_report and ctx.source_report.get("rows"):
        lines.append("### Traffic Sources (7 days)")
        lines.append("")
        lines.append("| Source | Sessions |")
        lines.append("|--------|----------|")
        sorted_sources = sorted(
            ctx.source_report["rows"],
            key=lambda r: int(r.get("sessions", 0)),
            reverse=True,
        )
        for row in sorted_sources[:15]:
            source = row.get("sessionSource", "(unknown)")
            sessions = row.get("sessions", "0")
            lines.append(f"| {source} | {sessions} |")
        lines.append("")

    # Channel grouping
    if ctx.channel_report and ctx.channel_report.get("rows"):
        lines.append("### Channel Grouping (30 days)")
        lines.append("")
        lines.append("| Channel | Sessions |")
        lines.append("|---------|----------|")
        sorted_channels = sorted(
            ctx.channel_report["rows"],
            key=lambda r: int(r.get("sessions", 0)),
            reverse=True,
        )
        for row in sorted_channels:
            channel = row.get("sessionDefaultChannelGroup", "(unknown)")
            sessions = row.get("sessions", "0")
            lines.append(f"| {channel} | {sessions} |")
        lines.append("")

    # Hostname breakdown
    if ctx.hostname_report and ctx.hostname_report.get("rows"):
        lines.append("### Hostnames (30 days)")
        lines.append("")
        lines.append("| Hostname | Sessions | Events |")
        lines.append("|----------|----------|--------|")
        sorted_hosts = sorted(
            ctx.hostname_report["rows"],
            key=lambda r: int(r.get("sessions", 0)),
            reverse=True,
        )
        for row in sorted_hosts[:15]:
            host = row.get("hostName", "(unknown)")
            sessions = row.get("sessions", "0")
            events = row.get("eventCount", "0")
            lines.append(f"| {host} | {sessions} | {events} |")
        lines.append("")

    # Realtime
    if ctx.realtime_report and ctx.realtime_report.get("rows"):
        total_active = sum(int(r.get("activeUsers", 0)) for r in ctx.realtime_report["rows"])
        lines.append(f"### Realtime: {total_active} active user(s)")
        lines.append("")

    # Access bindings
    bindings = ctx.access_bindings
    scope = "Property-Level"
    if not bindings and ctx.account_access_bindings:
        bindings = ctx.account_access_bindings
        scope = "Account-Level"

    if bindings:
        lines.append(f"### Users ({scope})")
        lines.append("")
        lines.append("| User | Roles |")
        lines.append("|------|-------|")
        for b in bindings:
            user = b.get("user", "")
            roles = ", ".join(b.get("roles", []))
            lines.append(f"| {user} | {roles} |")
        lines.append("")

    # Data streams
    if ctx.data_streams:
        lines.append("### Data Streams")
        lines.append("")
        lines.append("| Type | Name | Measurement ID | URL |")
        lines.append("|------|------|----------------|-----|")
        for s in ctx.data_streams:
            stype = s.get("type", "").replace("_DATA_STREAM", "")
            name = s.get("display_name", "")
            mid = s.get("measurement_id", s.get("package_name", s.get("bundle_id", "")))
            uri = s.get("default_uri", "")
            lines.append(f"| {stype} | {name} | {mid} | {uri} |")
        lines.append("")

    # Key events (conversions)
    if ctx.key_events:
        lines.append("### Key Events (Conversions)")
        lines.append("")
        lines.append("| Event Name | Custom | Counting Method |")
        lines.append("|------------|--------|-----------------|")
        for e in ctx.key_events:
            custom = "Yes" if e.get("custom") else "No"
            method = e.get("counting_method", "").replace("COUNTING_METHOD_", "")
            lines.append(f"| {e.get('event_name', '')} | {custom} | {method} |")
        lines.append("")

    # Enhanced measurement
    if ctx.enhanced_measurement:
        em = ctx.enhanced_measurement
        lines.append("### Enhanced Measurement")
        lines.append("")
        features = {
            "Scrolls": em.get("scrolls_enabled"),
            "Outbound Clicks": em.get("outbound_clicks_enabled"),
            "Site Search": em.get("site_search_enabled"),
            "Video Engagement": em.get("video_engagement_enabled"),
            "File Downloads": em.get("file_downloads_enabled"),
            "Page Changes": em.get("page_changes_enabled"),
            "Form Interactions": em.get("form_interactions_enabled"),
        }
        lines.append("| Feature | Enabled |")
        lines.append("|---------|---------|")
        for feat, enabled in features.items():
            status = "Yes" if enabled else "No"
            lines.append(f"| {feat} | {status} |")
        lines.append("")

    # Custom dimensions (Admin API)
    if ctx.custom_dimensions_config:
        lines.append("### Custom Dimensions")
        lines.append("")
        lines.append("| Parameter | Display Name | Scope |")
        lines.append("|-----------|-------------|-------|")
        for d in ctx.custom_dimensions_config:
            lines.append(f"| `{d.get('parameter_name', '')}` | {d.get('display_name', '')} | {d.get('scope', '')} |")
        lines.append("")

    # Custom metrics (Admin API)
    if ctx.custom_metrics_config:
        lines.append("### Custom Metrics")
        lines.append("")
        lines.append("| Parameter | Display Name | Unit |")
        lines.append("|-----------|-------------|------|")
        for m in ctx.custom_metrics_config:
            lines.append(f"| `{m.get('parameter_name', '')}` | {m.get('display_name', '')} | {m.get('measurement_unit', '')} |")
        lines.append("")

    # Audiences
    if ctx.audiences:
        lines.append("### Audiences")
        lines.append("")
        lines.append("| Name | Duration (days) |")
        lines.append("|------|-----------------|")
        for a in ctx.audiences:
            days = a.get("membership_duration_days", "N/A")
            lines.append(f"| {a.get('display_name', '')} | {days} |")
        lines.append("")

    # Google Ads links
    if ctx.google_ads_links:
        lines.append("### Google Ads Links")
        lines.append("")
        lines.append("| Customer ID | Personalization |")
        lines.append("|-------------|-----------------|")
        for link in ctx.google_ads_links:
            personalization = "Yes" if link.get("ads_personalization_enabled") else "No"
            lines.append(f"| {link.get('customer_id', '')} | {personalization} |")
        lines.append("")

    # Data retention settings
    if ctx.data_retention:
        retention_display = {
            "TWO_MONTHS": "2 months",
            "FOURTEEN_MONTHS": "14 months",
            "TWENTY_SIX_MONTHS": "26 months",
            "THIRTY_EIGHT_MONTHS": "38 months",
            "FIFTY_MONTHS": "50 months",
        }
        lines.append("### Data Retention")
        lines.append("")
        lines.append("| Setting | Value |")
        lines.append("|---------|-------|")
        evt = ctx.data_retention.get("event_data_retention", "")
        usr = ctx.data_retention.get("user_data_retention", "")
        reset = "Yes" if ctx.data_retention.get("reset_on_new_activity") else "No"
        lines.append(f"| Event Data | {retention_display.get(evt, evt)} |")
        lines.append(f"| User Data | {retention_display.get(usr, usr)} |")
        lines.append(f"| Reset on New Activity | {reset} |")
        lines.append("")

    # Metadata summary
    if ctx.metadata:
        dims = ctx.metadata.get("dimensions", [])
        metrics = ctx.metadata.get("metrics", [])
        lines.append("### API Metadata")
        lines.append("")
        lines.append(f"- **Available dimensions:** {len(dims)}")
        lines.append(f"- **Available metrics:** {len(metrics)}")
        lines.append("")

    # Site spider results
    if spider_result:
        lines.append("## Site Tag Coverage")
        lines.append("")
        lines.append(f"**Site:** {spider_result.site_url}  ")
        lines.append(f"**Pages Crawled:** {spider_result.pages_crawled}  ")
        lines.append(f"**Pages with GA4:** {spider_result.pages_with_ga4}  ")
        lines.append(f"**Pages without GA4:** {spider_result.pages_without_ga4}  ")
        if spider_result.pages_with_errors:
            lines.append(f"**Pages with Errors:** {spider_result.pages_with_errors}  ")
        lines.append("")

        # Summary table
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| GTM Containers | {', '.join(spider_result.gtm_containers) or 'None'} |")
        lines.append(f"| Measurement IDs (gtag) | {', '.join(spider_result.measurement_ids) or 'None (loaded via GTM)' } |")
        lines.append(f"| Server-Side GTM | {'Yes' if spider_result.has_server_side_gtm else 'No'} |")
        lines.append(f"| Pages with GTM | {spider_result.pages_with_gtm}/{spider_result.pages_crawled} |")
        coverage = (spider_result.pages_with_ga4 / spider_result.pages_crawled * 100) if spider_result.pages_crawled else 0
        lines.append(f"| GA4 Coverage | {coverage:.0f}% |")
        lines.append("")

        if spider_result.double_tagging_pages:
            lines.append("### Double-Tagged Pages")
            lines.append("")
            for url in spider_result.double_tagging_pages:
                lines.append(f"- {url}")
            lines.append("")

        if spider_result.untagged_pages:
            lines.append("### Untagged Pages")
            lines.append("")
            for url in spider_result.untagged_pages:
                lines.append(f"- {url}")
            lines.append("")

        # Per-page detail table
        lines.append("### Page Details")
        lines.append("")
        lines.append("| URL | Status | Tag | GTM ID | Notes |")
        lines.append("|-----|--------|-----|--------|-------|")
        for p in spider_result.page_results:
            tag_type = []
            if p.has_gtm:
                tag_type.append("GTM")
            if p.has_gtag:
                tag_type.append("gtag")
            if p.has_server_side_gtm:
                tag_type.append("sGTM")
            tag_str = "+".join(tag_type) or "None"
            gtm_str = ", ".join(p.gtm_containers) or "-"
            notes = []
            if p.error:
                notes.append(p.error)
            if p.ga4_config_calls > 1:
                notes.append(f"{p.ga4_config_calls} config calls")
            if len(p.gtag_ids) > 1:
                notes.append(f"Multiple IDs: {', '.join(p.gtag_ids)}")
            notes_str = "; ".join(notes) or "-"
            # Truncate URL for readability
            display_url = p.url.replace(spider_result.site_url, "")
            if not display_url:
                display_url = "/"
            lines.append(f"| {display_url} | {p.status_code} | {tag_str} | {gtm_str} | {notes_str} |")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by ga4 health check at {now}*")
    lines.append("")

    return "\n".join(lines)


def write_property_report(
    output_dir: str | Path,
    property_id: str,
    property_name: str,
    results: list[CheckResult],
    score_info: dict,
    ctx: CheckContext,
    duration_ms: int = 0,
    spider_result: SpiderResult | None = None,
) -> Path:
    """Write a markdown report to output/{domain}-{property_id}/report.md."""
    output_dir = Path(output_dir)
    dir_name = property_dir_name(property_name, property_id)
    prop_dir = output_dir / dir_name
    prop_dir.mkdir(parents=True, exist_ok=True)

    report = generate_report(
        property_id, property_name, results, score_info, ctx, duration_ms,
        spider_result=spider_result,
    )
    report_path = prop_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")

    return report_path
