"""GA4 property health check engine.

Defines individual checks, pre-fetches shared data, and calculates health scores.
Each check is a pure function: receives CheckContext, returns CheckResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    category: str  # "tracking" | "access" | "config"
    status: str  # "pass" | "warn" | "fail" | "error"
    message: str
    details: dict = field(default_factory=dict)
    weight: float = 1.0


@dataclass
class CheckContext:
    """Pre-fetched data shared across checks to minimize API calls."""

    property_info: dict
    access_bindings: list
    weekly_report: Optional[dict] = None
    realtime_report: Optional[dict] = None
    metadata: Optional[dict] = None
    source_report: Optional[dict] = None  # for (not set) detection
    account_access_bindings: Optional[list] = None  # account-level access
    engagement_report: Optional[dict] = None  # 30-day engagement metrics
    monthly_report: Optional[dict] = None  # 30-day sessions by date for trends
    data_streams: Optional[list] = None  # configured data streams
    key_events: Optional[list] = None  # conversion/key events
    custom_dimensions_config: Optional[list] = None  # Admin API custom dims
    custom_metrics_config: Optional[list] = None  # Admin API custom metrics
    google_ads_links: Optional[list] = None  # Google Ads integrations
    audiences: Optional[list] = None  # configured audiences
    enhanced_measurement: Optional[dict] = None  # enhanced measurement settings
    hostname_report: Optional[dict] = None  # hostnames sending data
    channel_report: Optional[dict] = None  # default channel grouping breakdown
    data_retention: Optional[dict] = None  # data retention settings


async def async_prefetch_context(
    property_id: str,
    admin_client,
    data_client,
    categories: Optional[list[str]] = None,
    cache=None,
) -> CheckContext:
    """Async pre-fetch: runs all API calls concurrently via asyncio.gather.

    Same logic as prefetch_context but uses async clients for parallelism.
    Reduces wall-clock time from ~6 sequential calls to ~1 round-trip.

    When *cache* (a :class:`~ga4.cache.Cache` instance) is provided, admin and
    metadata responses are served from cache when fresh, avoiding redundant API
    calls on repeated health checks.  Reporting data (sessions, traffic) and
    access bindings are never cached.
    """
    import asyncio
    from .cache import TTL_MEDIUM, TTL_LONG

    need_tracking = categories is None or "tracking" in categories
    need_access = categories is None or "access" in categories
    need_config = categories is None or "config" in categories

    def _cache_get(key: str, ttl: int):
        if cache is None:
            return None
        return cache.get("admin", key, ttl)

    def _cache_set(key: str, value) -> None:
        if cache is not None and value is not None:
            cache.set("admin", key, value)

    async def _get_property():
        cache_key = f"property_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.get_property(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return {}

    async def _get_access():
        # Never cache access bindings — security-sensitive
        if not need_access:
            return []
        try:
            return await admin_client.list_access_bindings(property_id)
        except Exception:
            return []

    async def _get_weekly():
        # Never cache reporting data — needs fresh values
        if not need_tracking:
            return None
        try:
            return await data_client.run_report(
                property_id=property_id,
                dimensions=["date"],
                metrics=["sessions", "bounceRate"],
                start_date="7daysAgo",
                end_date="today",
                limit=10,
            )
        except Exception:
            return None

    async def _get_realtime():
        # Never cache realtime data
        if not need_tracking:
            return None
        try:
            return await data_client.run_realtime_report(
                property_id=property_id,
                dimensions=["country"],
                metrics=["activeUsers"],
                limit=10,
            )
        except Exception:
            return None

    async def _get_metadata():
        if not need_config:
            return None
        cache_key = f"metadata_{property_id}"
        cached = _cache_get(cache_key, TTL_LONG)
        if cached is not None:
            return cached
        try:
            result = await data_client.get_metadata(property_id)
            if cache is not None and result is not None:
                cache.set("data", cache_key, result)
            return result
        except Exception:
            return None

    async def _get_source():
        # Never cache reporting data
        if not need_tracking:
            return None
        try:
            return await data_client.run_report(
                property_id=property_id,
                dimensions=["sessionSource"],
                metrics=["sessions"],
                start_date="7daysAgo",
                end_date="today",
                limit=50,
            )
        except Exception:
            return None

    async def _get_account_access():
        # Never cache access bindings
        if not need_access:
            return None
        try:
            prop_info = await admin_client.get_property(property_id)
            account_id = (prop_info or {}).get("account", "")
            if not account_id:
                return None
            return await admin_client.list_account_access_bindings(account_id)
        except Exception:
            return None

    async def _get_engagement():
        # Never cache reporting data
        if not need_tracking:
            return None
        try:
            return await data_client.run_report(
                property_id=property_id,
                dimensions=["date"],
                metrics=["sessions", "engagedSessions", "totalUsers", "eventCount", "screenPageViews"],
                start_date="30daysAgo",
                end_date="today",
                limit=31,
            )
        except Exception:
            return None

    async def _get_data_streams():
        if not need_config:
            return None
        cache_key = f"streams_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.list_data_streams(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _get_key_events():
        if not need_config:
            return None
        cache_key = f"key_events_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.list_key_events(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _get_custom_dims():
        if not need_config:
            return None
        cache_key = f"custom_dims_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.list_custom_dimensions(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _get_custom_metrics():
        if not need_config:
            return None
        cache_key = f"custom_metrics_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.list_custom_metrics(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _get_ads_links():
        if not need_config:
            return None
        cache_key = f"ads_links_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.list_google_ads_links(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _get_audiences():
        if not need_config:
            return None
        cache_key = f"audiences_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.list_audiences(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _get_data_retention():
        if not need_config:
            return None
        cache_key = f"retention_{property_id}"
        cached = _cache_get(cache_key, TTL_MEDIUM)
        if cached is not None:
            return cached
        try:
            result = await admin_client.get_data_retention_settings(property_id)
            _cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _get_hostnames():
        # Never cache reporting data
        if not need_tracking:
            return None
        try:
            return await data_client.run_report(
                property_id=property_id,
                dimensions=["hostName"],
                metrics=["sessions", "eventCount"],
                start_date="30daysAgo",
                end_date="today",
                limit=50,
            )
        except Exception:
            return None

    async def _get_channels():
        # Never cache reporting data
        if not need_tracking:
            return None
        try:
            return await data_client.run_report(
                property_id=property_id,
                dimensions=["sessionDefaultChannelGroup"],
                metrics=["sessions"],
                start_date="30daysAgo",
                end_date="today",
                limit=30,
            )
        except Exception:
            return None

    (
        property_info, access_bindings, weekly_report, realtime_report,
        metadata, source_report, account_access, engagement_report,
        data_streams, key_events, custom_dims, custom_metrics,
        ads_links, audiences, data_retention, hostname_report, channel_report,
    ) = await asyncio.gather(
        _get_property(),
        _get_access(),
        _get_weekly(),
        _get_realtime(),
        _get_metadata(),
        _get_source(),
        _get_account_access(),
        _get_engagement(),
        _get_data_streams(),
        _get_key_events(),
        _get_custom_dims(),
        _get_custom_metrics(),
        _get_ads_links(),
        _get_audiences(),
        _get_data_retention(),
        _get_hostnames(),
        _get_channels(),
    )

    # Fetch enhanced measurement for the first web stream (needs stream ID)
    enhanced = None
    if need_config and data_streams:
        for stream in data_streams:
            if stream.get("type") == "WEB_DATA_STREAM":
                stream_id = stream.get("name", "").split("/")[-1]
                if stream_id:
                    cache_key = f"enhanced_{property_id}_{stream_id}"
                    cached_enhanced = _cache_get(cache_key, TTL_MEDIUM)
                    if cached_enhanced is not None:
                        enhanced = cached_enhanced
                    else:
                        try:
                            enhanced = await admin_client.get_enhanced_measurement(property_id, stream_id)
                            _cache_set(cache_key, enhanced)
                        except Exception:
                            pass
                    break

    return CheckContext(
        property_info=property_info or {},
        access_bindings=access_bindings,
        weekly_report=weekly_report,
        realtime_report=realtime_report,
        metadata=metadata,
        source_report=source_report,
        account_access_bindings=account_access,
        engagement_report=engagement_report,
        data_streams=data_streams,
        key_events=key_events,
        custom_dimensions_config=custom_dims,
        custom_metrics_config=custom_metrics,
        google_ads_links=ads_links,
        audiences=audiences,
        enhanced_measurement=enhanced,
        hostname_report=hostname_report,
        channel_report=channel_report,
        data_retention=data_retention,
    )


def prefetch_context(
    property_id: str,
    admin_client,
    data_client,
    categories: Optional[list[str]] = None,
) -> CheckContext:
    """Pre-fetch data needed for checks.

    When categories is None (full check): 6 API calls.
    When filtered to a single category: only fetches what's needed.
    """
    need_tracking = categories is None or "tracking" in categories
    need_access = categories is None or "access" in categories
    need_config = categories is None or "config" in categories

    # Always fetch property info (used by config checks and for display name)
    property_info = admin_client.get_property(property_id) or {}

    # Access bindings (needed for access checks)
    access_bindings = []
    if need_access:
        try:
            access_bindings = admin_client.list_access_bindings(property_id)
        except Exception:
            pass

    # Weekly report - sessions + bounceRate by date (needed for tracking checks)
    weekly_report = None
    if need_tracking:
        try:
            weekly_report = data_client.run_report(
                property_id=property_id,
                dimensions=["date"],
                metrics=["sessions", "bounceRate"],
                start_date="7daysAgo",
                end_date="today",
                limit=10,
            )
        except Exception:
            pass

    # Realtime report (needed for tracking checks)
    realtime_report = None
    if need_tracking:
        try:
            realtime_report = data_client.run_realtime_report(
                property_id=property_id,
                dimensions=["country"],
                metrics=["activeUsers"],
                limit=10,
            )
        except Exception:
            pass

    # Metadata - dimensions/metrics catalog (needed for config checks)
    metadata = None
    if need_config:
        try:
            metadata = data_client.get_metadata(property_id)
        except Exception:
            pass

    # Source report for (not set) detection (needed for tracking checks)
    source_report = None
    if need_tracking:
        try:
            source_report = data_client.run_report(
                property_id=property_id,
                dimensions=["sessionSource"],
                metrics=["sessions"],
                start_date="7daysAgo",
                end_date="today",
                limit=50,
            )
        except Exception:
            pass

    # Account-level access bindings
    account_access = None
    if need_access:
        try:
            account_id = property_info.get("account", "")
            if account_id:
                account_access = admin_client.list_account_access_bindings(account_id)
        except Exception:
            pass

    # 30-day engagement report
    engagement_report = None
    if need_tracking:
        try:
            engagement_report = data_client.run_report(
                property_id=property_id,
                dimensions=["date"],
                metrics=["sessions", "engagedSessions", "totalUsers", "eventCount", "screenPageViews"],
                start_date="30daysAgo",
                end_date="today",
                limit=31,
            )
        except Exception:
            pass

    # Hostname report for fragmentation detection
    hostname_report = None
    if need_tracking:
        try:
            hostname_report = data_client.run_report(
                property_id=property_id,
                dimensions=["hostName"],
                metrics=["sessions", "eventCount"],
                start_date="30daysAgo",
                end_date="today",
                limit=50,
            )
        except Exception:
            pass

    # Channel grouping report
    channel_report = None
    if need_tracking:
        try:
            channel_report = data_client.run_report(
                property_id=property_id,
                dimensions=["sessionDefaultChannelGroup"],
                metrics=["sessions"],
                start_date="30daysAgo",
                end_date="today",
                limit=30,
            )
        except Exception:
            pass

    # Config data: data streams, key events, custom dims/metrics, ads links, audiences
    data_streams = None
    key_events = None
    custom_dims = None
    custom_metrics = None
    ads_links = None
    audiences = None
    enhanced = None

    if need_config:
        try:
            data_streams = admin_client.list_data_streams(property_id)
        except Exception:
            pass
        try:
            key_events = admin_client.list_key_events(property_id)
        except Exception:
            pass
        try:
            custom_dims = admin_client.list_custom_dimensions(property_id)
        except Exception:
            pass
        try:
            custom_metrics = admin_client.list_custom_metrics(property_id)
        except Exception:
            pass
        try:
            ads_links = admin_client.list_google_ads_links(property_id)
        except Exception:
            pass
        try:
            audiences = admin_client.list_audiences(property_id)
        except Exception:
            pass

        # Enhanced measurement needs stream ID
        if data_streams:
            for stream in data_streams:
                if stream.get("type") == "WEB_DATA_STREAM":
                    stream_id = stream.get("name", "").split("/")[-1]
                    if stream_id:
                        try:
                            enhanced = admin_client.get_enhanced_measurement(property_id, stream_id)
                        except Exception:
                            pass
                        break

    # Data retention settings
    data_retention = None
    if need_config:
        try:
            data_retention = admin_client.get_data_retention_settings(property_id)
        except Exception:
            pass

    return CheckContext(
        property_info=property_info,
        access_bindings=access_bindings,
        weekly_report=weekly_report,
        realtime_report=realtime_report,
        metadata=metadata,
        source_report=source_report,
        account_access_bindings=account_access,
        engagement_report=engagement_report,
        data_streams=data_streams,
        key_events=key_events,
        custom_dimensions_config=custom_dims,
        custom_metrics_config=custom_metrics,
        google_ads_links=ads_links,
        audiences=audiences,
        enhanced_measurement=enhanced,
        hostname_report=hostname_report,
        channel_report=channel_report,
        data_retention=data_retention,
    )


# =============================================================================
# TRACKING CHECKS
# =============================================================================


def check_data_recency(ctx: CheckContext) -> CheckResult:
    """Check if property is receiving data (last event within 48h)."""
    if not ctx.weekly_report or not ctx.weekly_report.get("rows"):
        return CheckResult(
            name="data_recency",
            category="tracking",
            status="fail",
            message="No data received in the last 7 days",
            weight=1.0,
        )

    rows = ctx.weekly_report["rows"]
    # Rows are date-sorted; find the most recent date with data
    dates = sorted([r.get("date", "") for r in rows], reverse=True)
    latest = dates[0] if dates else ""

    if not latest:
        return CheckResult(
            name="data_recency",
            category="tracking",
            status="fail",
            message="No data received in the last 7 days",
            weight=1.0,
        )

    try:
        latest_dt = datetime.strptime(latest, "%Y%m%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hours_ago = (now - latest_dt).total_seconds() / 3600
    except ValueError:
        return CheckResult(
            name="data_recency",
            category="tracking",
            status="error",
            message=f"Could not parse date: {latest}",
            details={"raw_date": latest},
            weight=1.0,
        )

    details = {"last_date": latest, "hours_ago": round(hours_ago, 1)}

    if hours_ago <= 36:  # allow for timezone lag
        return CheckResult(
            name="data_recency",
            category="tracking",
            status="pass",
            message=f"Data received within last {int(hours_ago)} hours",
            details=details,
            weight=1.0,
        )
    elif hours_ago <= 60:
        return CheckResult(
            name="data_recency",
            category="tracking",
            status="warn",
            message=f"Data gap: last data {int(hours_ago)} hours ago",
            details=details,
            weight=1.0,
        )
    else:
        return CheckResult(
            name="data_recency",
            category="tracking",
            status="fail",
            message=f"No recent data: last data {int(hours_ago)} hours ago",
            details=details,
            weight=1.0,
        )


def check_realtime_active(ctx: CheckContext) -> CheckResult:
    """Check if there are any realtime active users."""
    if not ctx.realtime_report:
        return CheckResult(
            name="realtime_active",
            category="tracking",
            status="warn",
            message="Could not fetch realtime data",
            weight=0.3,
        )

    rows = ctx.realtime_report.get("rows", [])
    total_active = sum(int(r.get("activeUsers", 0)) for r in rows)

    if total_active > 0:
        return CheckResult(
            name="realtime_active",
            category="tracking",
            status="pass",
            message=f"{total_active} active users right now",
            details={"active_users": total_active},
            weight=0.3,
        )
    else:
        return CheckResult(
            name="realtime_active",
            category="tracking",
            status="warn",
            message="No active users right now (may be normal for low-traffic sites)",
            details={"active_users": 0},
            weight=0.3,
        )


def check_session_volume(ctx: CheckContext) -> CheckResult:
    """Check if traffic volume is reasonable."""
    if not ctx.weekly_report or not ctx.weekly_report.get("rows"):
        return CheckResult(
            name="session_volume",
            category="tracking",
            status="fail",
            message="No session data available",
            weight=0.7,
        )

    rows = ctx.weekly_report["rows"]
    total_sessions = sum(int(r.get("sessions", 0)) for r in rows)
    days = len(rows) or 1
    avg_daily = total_sessions / days

    details = {
        "total_sessions": total_sessions,
        "days": days,
        "avg_daily": round(avg_daily, 1),
    }

    if avg_daily > 10:
        return CheckResult(
            name="session_volume",
            category="tracking",
            status="pass",
            message=f"Avg {int(avg_daily)} sessions/day ({total_sessions:,} total over {days} days)",
            details=details,
            weight=0.7,
        )
    elif avg_daily > 0:
        return CheckResult(
            name="session_volume",
            category="tracking",
            status="warn",
            message=f"Low traffic: avg {avg_daily:.1f} sessions/day",
            details=details,
            weight=0.7,
        )
    else:
        return CheckResult(
            name="session_volume",
            category="tracking",
            status="fail",
            message="Zero sessions in the last 7 days",
            details=details,
            weight=0.7,
        )


def check_not_set_prevalence(ctx: CheckContext) -> CheckResult:
    """Check for (not set) values in source dimension."""
    if not ctx.source_report or not ctx.source_report.get("rows"):
        return CheckResult(
            name="not_set_prevalence",
            category="tracking",
            status="warn",
            message="Could not check (not set) prevalence",
            weight=0.8,
        )

    rows = ctx.source_report["rows"]
    total = sum(int(r.get("sessions", 0)) for r in rows)
    not_set = sum(
        int(r.get("sessions", 0))
        for r in rows
        if r.get("sessionSource", "").lower() in ("(not set)", "(not provided)")
    )

    if total == 0:
        return CheckResult(
            name="not_set_prevalence",
            category="tracking",
            status="warn",
            message="No session data to check",
            weight=0.8,
        )

    pct = (not_set / total) * 100
    details = {
        "not_set_sessions": not_set,
        "total_sessions": total,
        "percentage": round(pct, 1),
    }

    if pct < 5:
        return CheckResult(
            name="not_set_prevalence",
            category="tracking",
            status="pass",
            message=f"(not set) source: {pct:.1f}% of sessions",
            details=details,
            weight=0.8,
        )
    elif pct < 15:
        return CheckResult(
            name="not_set_prevalence",
            category="tracking",
            status="warn",
            message=f"(not set) source: {pct:.1f}% of sessions — review UTM tagging",
            details=details,
            weight=0.8,
        )
    else:
        return CheckResult(
            name="not_set_prevalence",
            category="tracking",
            status="fail",
            message=f"(not set) source: {pct:.1f}% of sessions — tracking misconfigured",
            details=details,
            weight=0.8,
        )


def check_bounce_rate(ctx: CheckContext) -> CheckResult:
    """Check if bounce rate is anomalously high."""
    if not ctx.weekly_report or not ctx.weekly_report.get("rows"):
        return CheckResult(
            name="bounce_rate",
            category="tracking",
            status="warn",
            message="No data to check bounce rate",
            weight=0.5,
        )

    rows = ctx.weekly_report["rows"]
    bounce_rates = []
    for r in rows:
        br = r.get("bounceRate")
        if br is not None:
            try:
                bounce_rates.append(float(br))
            except (ValueError, TypeError):
                pass

    if not bounce_rates:
        return CheckResult(
            name="bounce_rate",
            category="tracking",
            status="warn",
            message="Bounce rate data not available",
            weight=0.5,
        )

    avg_bounce = sum(bounce_rates) / len(bounce_rates)
    # GA4 bounceRate is returned as a decimal (0.0-1.0)
    if avg_bounce <= 1.0:
        avg_bounce_pct = avg_bounce * 100
    else:
        avg_bounce_pct = avg_bounce

    details = {"avg_bounce_rate": round(avg_bounce_pct, 1)}

    if avg_bounce_pct < 70:
        return CheckResult(
            name="bounce_rate",
            category="tracking",
            status="pass",
            message=f"Bounce rate: {avg_bounce_pct:.1f}%",
            details=details,
            weight=0.5,
        )
    elif avg_bounce_pct < 90:
        return CheckResult(
            name="bounce_rate",
            category="tracking",
            status="warn",
            message=f"High bounce rate: {avg_bounce_pct:.1f}%",
            details=details,
            weight=0.5,
        )
    else:
        return CheckResult(
            name="bounce_rate",
            category="tracking",
            status="fail",
            message=f"Very high bounce rate: {avg_bounce_pct:.1f}% — check tracking setup",
            details=details,
            weight=0.5,
        )


# =============================================================================
# TAG IMPLEMENTATION CHECKS
# =============================================================================


def check_double_tagging(ctx: CheckContext) -> CheckResult:
    """Detect double/triple tagging from data anomalies.

    Classic indicators: bounce rate near 0%, duplicate web streams on same domain,
    events-per-pageview ratio abnormally high.
    """
    issues = []
    details = {}

    # Check 1: Bounce rate near 0% (classic double-tagging symptom)
    if ctx.weekly_report and ctx.weekly_report.get("rows"):
        bounce_rates = []
        for r in ctx.weekly_report["rows"]:
            br = r.get("bounceRate")
            if br is not None:
                try:
                    val = float(br)
                    bounce_rates.append(val * 100 if val <= 1.0 else val)
                except (ValueError, TypeError):
                    pass
        if bounce_rates:
            avg_bounce = sum(bounce_rates) / len(bounce_rates)
            details["avg_bounce_rate"] = round(avg_bounce, 1)
            if avg_bounce < 10:
                issues.append(f"Suspiciously low bounce rate ({avg_bounce:.1f}%) — typical double-tagging symptom")

    # Check 2: Multiple web streams on same domain
    if ctx.data_streams:
        web_streams = [s for s in ctx.data_streams if s.get("type") == "WEB_DATA_STREAM"]
        if len(web_streams) > 1:
            domains = [s.get("default_uri", "").replace("https://", "").replace("http://", "").rstrip("/") for s in web_streams]
            details["web_streams"] = len(web_streams)
            details["stream_domains"] = domains
            # Check for duplicate domains
            unique = set(d.lower() for d in domains if d)
            if len(unique) < len(web_streams):
                issues.append(f"{len(web_streams)} web streams with overlapping domains — possible duplicate tagging")

    # Check 3: Abnormal events-per-pageview ratio
    if ctx.engagement_report and ctx.engagement_report.get("rows"):
        rows = ctx.engagement_report["rows"]
        total_events = sum(int(r.get("eventCount", 0)) for r in rows)
        total_pages = sum(int(r.get("screenPageViews", 0)) for r in rows)
        if total_pages > 0:
            ratio = total_events / total_pages
            details["events_per_pageview"] = round(ratio, 1)
            if ratio > 15:
                issues.append(f"Abnormally high events/pageview ratio ({ratio:.1f}) — may indicate duplicate event firing")

    if issues:
        return CheckResult(
            name="double_tagging",
            category="tracking",
            status="fail" if len(issues) >= 2 else "warn",
            message="; ".join(issues),
            details=details,
            weight=1.0,
        )
    else:
        return CheckResult(
            name="double_tagging",
            category="tracking",
            status="pass",
            message="No double-tagging indicators detected",
            details=details,
            weight=1.0,
        )


def check_self_referrals(ctx: CheckContext) -> CheckResult:
    """Check if the property's own domain appears as a referral source."""
    if not ctx.source_report or not ctx.source_report.get("rows"):
        return CheckResult(
            name="self_referrals",
            category="tracking",
            status="warn",
            message="No source data to check",
            weight=0.6,
        )

    # Get the property's own domain(s) from data streams
    own_domains = set()
    if ctx.data_streams:
        for s in ctx.data_streams:
            uri = s.get("default_uri", "")
            if uri:
                domain = uri.replace("https://", "").replace("http://", "").rstrip("/")
                own_domains.add(domain.lower())
                # Also add without www
                if domain.startswith("www."):
                    own_domains.add(domain[4:].lower())
                else:
                    own_domains.add(f"www.{domain}".lower())

    if not own_domains:
        return CheckResult(
            name="self_referrals",
            category="tracking",
            status="warn",
            message="Could not determine own domains from data streams",
            weight=0.6,
        )

    # Check source report for self-referrals
    self_referrals = []
    for row in ctx.source_report["rows"]:
        source = row.get("sessionSource", "").lower()
        sessions = int(row.get("sessions", 0))
        if source and sessions > 0:
            for domain in own_domains:
                if source == domain or source.endswith(f".{domain}"):
                    self_referrals.append({"source": row.get("sessionSource", ""), "sessions": sessions})
                    break

    details = {"own_domains": list(own_domains), "self_referrals": self_referrals}

    if self_referrals:
        total_self = sum(r["sessions"] for r in self_referrals)
        return CheckResult(
            name="self_referrals",
            category="tracking",
            status="warn",
            message=f"Self-referral detected: {total_self} sessions from own domain(s) — check cross-domain or referral exclusion settings",
            details=details,
            weight=0.6,
        )
    else:
        return CheckResult(
            name="self_referrals",
            category="tracking",
            status="pass",
            message="No self-referrals detected",
            details=details,
            weight=0.6,
        )


def check_hostname_fragmentation(ctx: CheckContext) -> CheckResult:
    """Check for unexpected hostnames sending data."""
    if not ctx.hostname_report or not ctx.hostname_report.get("rows"):
        return CheckResult(
            name="hostname_fragmentation",
            category="tracking",
            status="warn",
            message="No hostname data available",
            weight=0.5,
        )

    rows = ctx.hostname_report["rows"]
    total_sessions = sum(int(r.get("sessions", 0)) for r in rows)
    hostnames = sorted(rows, key=lambda r: int(r.get("sessions", 0)), reverse=True)

    # Get expected domains from data streams
    expected_domains = set()
    if ctx.data_streams:
        for s in ctx.data_streams:
            uri = s.get("default_uri", "")
            if uri:
                domain = uri.replace("https://", "").replace("http://", "").rstrip("/").lower()
                expected_domains.add(domain)
                if domain.startswith("www."):
                    expected_domains.add(domain[4:])
                else:
                    expected_domains.add(f"www.{domain}")

    unexpected = []
    for row in hostnames:
        host = row.get("hostName", "").lower()
        sessions = int(row.get("sessions", 0))
        if host and sessions > 0 and host not in expected_domains:
            # Check if it's a variant of expected domain (e.g., evolution7.com vs evolution7.com.au)
            is_variant = any(host.replace("www.", "") in d or d.replace("www.", "") in host for d in expected_domains)
            unexpected.append({
                "hostname": row.get("hostName", ""),
                "sessions": sessions,
                "events": int(row.get("eventCount", 0)),
                "is_variant": is_variant,
            })

    details = {
        "total_hostnames": len(hostnames),
        "expected_domains": list(expected_domains),
        "unexpected_hostnames": unexpected,
        "all_hostnames": [{"hostname": r.get("hostName", ""), "sessions": int(r.get("sessions", 0))} for r in hostnames[:10]],
    }

    if not unexpected:
        return CheckResult(
            name="hostname_fragmentation",
            category="tracking",
            status="pass",
            message=f"All traffic from expected hostname(s)",
            details=details,
            weight=0.5,
        )

    unexpected_sessions = sum(u["sessions"] for u in unexpected)
    unexpected_pct = (unexpected_sessions / total_sessions * 100) if total_sessions else 0
    variant_hosts = [u for u in unexpected if u["is_variant"]]
    rogue_hosts = [u for u in unexpected if not u["is_variant"]]

    parts = []
    if variant_hosts:
        parts.append(f"{len(variant_hosts)} domain variant(s)")
    if rogue_hosts:
        parts.append(f"{len(rogue_hosts)} unexpected host(s)")

    if rogue_hosts and unexpected_pct > 5:
        status = "warn"
    elif rogue_hosts:
        status = "pass"
    else:
        status = "pass"

    return CheckResult(
        name="hostname_fragmentation",
        category="tracking",
        status=status,
        message=f"{len(unexpected)} extra hostname(s) sending data ({unexpected_pct:.1f}% of sessions): {', '.join(parts)}",
        details=details,
        weight=0.5,
    )


def check_channel_grouping(ctx: CheckContext) -> CheckResult:
    """Check for (not set) or Unassigned in default channel grouping."""
    if not ctx.channel_report or not ctx.channel_report.get("rows"):
        return CheckResult(
            name="channel_grouping",
            category="tracking",
            status="warn",
            message="No channel grouping data available",
            weight=0.5,
        )

    rows = ctx.channel_report["rows"]
    total_sessions = sum(int(r.get("sessions", 0)) for r in rows)

    problem_channels = []
    for row in rows:
        channel = row.get("sessionDefaultChannelGroup", "")
        sessions = int(row.get("sessions", 0))
        if channel.lower() in ("(not set)", "unassigned", "(other)") and sessions > 0:
            problem_channels.append({"channel": channel, "sessions": sessions})

    problem_sessions = sum(c["sessions"] for c in problem_channels)
    problem_pct = (problem_sessions / total_sessions * 100) if total_sessions else 0

    details = {
        "channels": [{"channel": r.get("sessionDefaultChannelGroup", ""), "sessions": int(r.get("sessions", 0))} for r in rows],
        "problem_channels": problem_channels,
        "problem_pct": round(problem_pct, 1),
    }

    if not problem_channels:
        return CheckResult(
            name="channel_grouping",
            category="tracking",
            status="pass",
            message="All sessions assigned to known channels",
            details=details,
            weight=0.5,
        )
    elif problem_pct < 5:
        return CheckResult(
            name="channel_grouping",
            category="tracking",
            status="pass",
            message=f"{problem_pct:.1f}% sessions in {', '.join(c['channel'] for c in problem_channels)} (acceptable)",
            details=details,
            weight=0.5,
        )
    elif problem_pct < 15:
        return CheckResult(
            name="channel_grouping",
            category="tracking",
            status="warn",
            message=f"{problem_pct:.1f}% sessions unassigned/not-set — review UTM tagging or channel definitions",
            details=details,
            weight=0.5,
        )
    else:
        return CheckResult(
            name="channel_grouping",
            category="tracking",
            status="fail",
            message=f"{problem_pct:.1f}% sessions unassigned/not-set — significant channel attribution issue",
            details=details,
            weight=0.5,
        )


# =============================================================================
# CONFIG CHECKS
# =============================================================================


def check_property_config(ctx: CheckContext) -> CheckResult:
    """Check if property has timezone, currency, and industry set."""
    info = ctx.property_info
    if not info:
        return CheckResult(
            name="property_config",
            category="config",
            status="error",
            message="Could not fetch property info",
            weight=0.4,
        )

    missing = []
    if not info.get("time_zone"):
        missing.append("time_zone")
    if not info.get("currency"):
        missing.append("currency")
    if not info.get("industry_category") or info.get("industry_category") == "INDUSTRY_CATEGORY_UNSPECIFIED":
        missing.append("industry_category")

    details = {
        "time_zone": info.get("time_zone", ""),
        "currency": info.get("currency", ""),
        "industry_category": info.get("industry_category", ""),
        "missing": missing,
    }

    if not missing:
        return CheckResult(
            name="property_config",
            category="config",
            status="pass",
            message="All property settings configured",
            details=details,
            weight=0.4,
        )
    elif "time_zone" in missing or "currency" in missing:
        return CheckResult(
            name="property_config",
            category="config",
            status="warn",
            message=f"Missing property settings: {', '.join(missing)}",
            details=details,
            weight=0.4,
        )
    else:
        return CheckResult(
            name="property_config",
            category="config",
            status="warn",
            message=f"Optional setting not configured: {', '.join(missing)}",
            details=details,
            weight=0.4,
        )


def check_custom_dimensions(ctx: CheckContext) -> CheckResult:
    """Check if custom dimensions/metrics are configured (from Admin API)."""
    dims = ctx.custom_dimensions_config
    metrics = ctx.custom_metrics_config

    if dims is None and metrics is None:
        # Fall back to metadata API
        if not ctx.metadata:
            return CheckResult(
                name="custom_dimensions",
                category="config",
                status="warn",
                message="Could not fetch custom dimension data",
                weight=0.3,
            )
        all_dims = ctx.metadata.get("dimensions", [])
        all_metrics = ctx.metadata.get("metrics", [])
        custom_d = [d for d in all_dims if d.get("apiName", "").startswith("customEvent:")]
        custom_m = [m for m in all_metrics if m.get("apiName", "").startswith("customEvent:")]
        dim_count, metric_count = len(custom_d), len(custom_m)
        dim_details, metric_details = [], []
    else:
        dims = dims or []
        metrics = metrics or []
        dim_count, metric_count = len(dims), len(metrics)
        dim_details = [
            {"parameter": d.get("parameter_name", ""), "name": d.get("display_name", ""), "scope": d.get("scope", "")}
            for d in dims
        ]
        metric_details = [
            {"parameter": m.get("parameter_name", ""), "name": m.get("display_name", ""), "unit": m.get("measurement_unit", "")}
            for m in metrics
        ]

    details = {
        "custom_dimensions": dim_count,
        "custom_metrics": metric_count,
        "dimensions": dim_details if dim_details else None,
        "metrics": metric_details if metric_details else None,
    }
    # Remove None values
    details = {k: v for k, v in details.items() if v is not None}

    if dim_count or metric_count:
        return CheckResult(
            name="custom_dimensions",
            category="config",
            status="pass",
            message=f"{dim_count} custom dimensions, {metric_count} custom metrics",
            details=details,
            weight=0.3,
        )
    else:
        return CheckResult(
            name="custom_dimensions",
            category="config",
            status="warn",
            message="No custom dimensions or metrics configured",
            details=details,
            weight=0.3,
        )


def check_key_events(ctx: CheckContext) -> CheckResult:
    """Check if key events (conversions) are configured."""
    events = ctx.key_events
    if events is None:
        return CheckResult(
            name="key_events",
            category="config",
            status="warn",
            message="Could not fetch key events",
            weight=0.7,
        )

    custom_events = [e for e in events if e.get("custom", False)]
    builtin_events = [e for e in events if not e.get("custom", False)]

    details = {
        "total_key_events": len(events),
        "custom_key_events": len(custom_events),
        "builtin_key_events": len(builtin_events),
        "events": [e.get("event_name", "") for e in events],
    }

    if len(events) >= 3:
        return CheckResult(
            name="key_events",
            category="config",
            status="pass",
            message=f"{len(events)} key events configured ({len(custom_events)} custom)",
            details=details,
            weight=0.7,
        )
    elif len(events) >= 1:
        return CheckResult(
            name="key_events",
            category="config",
            status="warn",
            message=f"Only {len(events)} key event(s) — consider adding more conversion tracking",
            details=details,
            weight=0.7,
        )
    else:
        return CheckResult(
            name="key_events",
            category="config",
            status="fail",
            message="No key events configured — conversion tracking not set up",
            details=details,
            weight=0.7,
        )


def check_data_streams(ctx: CheckContext) -> CheckResult:
    """Check if data streams are configured."""
    streams = ctx.data_streams
    if streams is None:
        return CheckResult(
            name="data_streams",
            category="config",
            status="warn",
            message="Could not fetch data streams",
            weight=0.8,
        )

    web_streams = [s for s in streams if s.get("type") == "WEB_DATA_STREAM"]
    app_streams = [s for s in streams if s.get("type") in ("ANDROID_APP_DATA_STREAM", "IOS_APP_DATA_STREAM")]

    details = {
        "total_streams": len(streams),
        "web_streams": len(web_streams),
        "app_streams": len(app_streams),
        "streams": [
            {
                "type": s.get("type", ""),
                "name": s.get("display_name", ""),
                "measurement_id": s.get("measurement_id", ""),
                "uri": s.get("default_uri", ""),
            }
            for s in streams
        ],
    }

    if not streams:
        return CheckResult(
            name="data_streams",
            category="config",
            status="fail",
            message="No data streams configured — property cannot collect data",
            details=details,
            weight=0.8,
        )
    else:
        parts = []
        if web_streams:
            parts.append(f"{len(web_streams)} web")
        if app_streams:
            parts.append(f"{len(app_streams)} app")
        return CheckResult(
            name="data_streams",
            category="config",
            status="pass",
            message=f"{len(streams)} data stream(s): {', '.join(parts)}",
            details=details,
            weight=0.8,
        )


def check_enhanced_measurement(ctx: CheckContext) -> CheckResult:
    """Check enhanced measurement settings on web streams."""
    em = ctx.enhanced_measurement
    if not em:
        if ctx.data_streams:
            web = [s for s in ctx.data_streams if s.get("type") == "WEB_DATA_STREAM"]
            if not web:
                return CheckResult(
                    name="enhanced_measurement",
                    category="config",
                    status="warn",
                    message="No web data stream — enhanced measurement N/A",
                    weight=0.5,
                )
        return CheckResult(
            name="enhanced_measurement",
            category="config",
            status="warn",
            message="Could not fetch enhanced measurement settings",
            weight=0.5,
        )

    if not em.get("stream_enabled", False):
        return CheckResult(
            name="enhanced_measurement",
            category="config",
            status="fail",
            message="Enhanced measurement is disabled",
            details=em,
            weight=0.5,
        )

    # Check which features are enabled
    features = {
        "scrolls": em.get("scrolls_enabled", False),
        "outbound_clicks": em.get("outbound_clicks_enabled", False),
        "site_search": em.get("site_search_enabled", False),
        "video": em.get("video_engagement_enabled", False),
        "file_downloads": em.get("file_downloads_enabled", False),
        "page_changes": em.get("page_changes_enabled", False),
        "form_interactions": em.get("form_interactions_enabled", False),
    }
    enabled = [k for k, v in features.items() if v]
    disabled = [k for k, v in features.items() if not v]

    details = {"enabled": enabled, "disabled": disabled, **em}

    if len(disabled) == 0:
        return CheckResult(
            name="enhanced_measurement",
            category="config",
            status="pass",
            message=f"All {len(enabled)} enhanced measurement features enabled",
            details=details,
            weight=0.5,
        )
    elif len(enabled) >= 4:
        return CheckResult(
            name="enhanced_measurement",
            category="config",
            status="pass",
            message=f"{len(enabled)}/7 enhanced features enabled (disabled: {', '.join(disabled)})",
            details=details,
            weight=0.5,
        )
    else:
        return CheckResult(
            name="enhanced_measurement",
            category="config",
            status="warn",
            message=f"Only {len(enabled)}/7 enhanced features enabled — missing: {', '.join(disabled)}",
            details=details,
            weight=0.5,
        )


def check_audiences(ctx: CheckContext) -> CheckResult:
    """Check if audiences are configured."""
    audiences = ctx.audiences
    if audiences is None:
        return CheckResult(
            name="audiences",
            category="config",
            status="warn",
            message="Could not fetch audiences",
            weight=0.3,
        )

    # Filter out default "All Users" and "Purchasers" audiences
    default_names = {"all users", "purchasers"}
    custom = [a for a in audiences if a.get("display_name", "").lower() not in default_names]

    details = {
        "total_audiences": len(audiences),
        "custom_audiences": len(custom),
        "audiences": [a.get("display_name", "") for a in audiences],
    }

    if len(custom) >= 2:
        return CheckResult(
            name="audiences",
            category="config",
            status="pass",
            message=f"{len(custom)} custom audiences configured",
            details=details,
            weight=0.3,
        )
    elif len(custom) >= 1:
        return CheckResult(
            name="audiences",
            category="config",
            status="warn",
            message=f"Only {len(custom)} custom audience — consider building segments",
            details=details,
            weight=0.3,
        )
    else:
        return CheckResult(
            name="audiences",
            category="config",
            status="warn",
            message="No custom audiences configured (only defaults)",
            details=details,
            weight=0.3,
        )


def check_google_ads_link(ctx: CheckContext) -> CheckResult:
    """Check if Google Ads is linked."""
    links = ctx.google_ads_links
    if links is None:
        return CheckResult(
            name="google_ads_link",
            category="config",
            status="warn",
            message="Could not fetch Google Ads links",
            weight=0.2,
        )

    details = {
        "linked_accounts": len(links),
        "accounts": [{"customer_id": l.get("customer_id", ""), "personalization": l.get("ads_personalization_enabled", False)} for l in links],
    }

    if links:
        return CheckResult(
            name="google_ads_link",
            category="config",
            status="pass",
            message=f"{len(links)} Google Ads account(s) linked",
            details=details,
            weight=0.2,
        )
    else:
        return CheckResult(
            name="google_ads_link",
            category="config",
            status="warn",
            message="No Google Ads account linked (OK if not running ads)",
            details=details,
            weight=0.2,
        )


def check_data_retention(ctx: CheckContext) -> CheckResult:
    """Check if data retention is set beyond the 2-month default."""
    if not ctx.data_retention:
        return CheckResult(
            name="data_retention",
            category="config",
            status="warn",
            message="Could not fetch data retention settings",
            weight=0.6,
        )

    event_retention = ctx.data_retention.get("event_data_retention", "")
    reset_on_activity = ctx.data_retention.get("reset_on_new_activity", False)

    # Map API values to display names
    retention_display = {
        "TWO_MONTHS": "2 months",
        "FOURTEEN_MONTHS": "14 months",
        "TWENTY_SIX_MONTHS": "26 months",
        "THIRTY_EIGHT_MONTHS": "38 months",
        "FIFTY_MONTHS": "50 months",
    }
    display = retention_display.get(event_retention, event_retention)

    details = {
        "event_data_retention": display,
        "user_data_retention": ctx.data_retention.get("user_data_retention", ""),
        "reset_on_new_activity": reset_on_activity,
    }

    if event_retention == "TWO_MONTHS":
        return CheckResult(
            name="data_retention",
            category="config",
            status="fail",
            message=f"Data retention at default {display} — set to 14 months",
            details=details,
            weight=0.6,
        )
    elif event_retention == "FOURTEEN_MONTHS":
        return CheckResult(
            name="data_retention",
            category="config",
            status="pass",
            message=f"Data retention: {display}",
            details=details,
            weight=0.6,
        )
    else:
        # 26+ months (GA360)
        return CheckResult(
            name="data_retention",
            category="config",
            status="pass",
            message=f"Data retention: {display} (GA360)",
            details=details,
            weight=0.6,
        )


# =============================================================================
# ACCESS CHECKS
# =============================================================================


def _effective_bindings(ctx: CheckContext) -> tuple[list, str]:
    """Get effective access bindings, falling back to account-level.

    Returns (bindings, scope) where scope is "property" or "account".
    """
    if ctx.access_bindings:
        return ctx.access_bindings, "property"
    if ctx.account_access_bindings:
        return ctx.account_access_bindings, "account"
    return [], "none"


def check_user_count(ctx: CheckContext) -> CheckResult:
    """Check number of users with access."""
    bindings, scope = _effective_bindings(ctx)
    count = len(bindings)
    details = {"user_count": count, "access_scope": scope}

    scope_note = f" ({scope}-level)" if scope != "none" else ""

    if 1 <= count <= 20:
        return CheckResult(
            name="user_count",
            category="access",
            status="pass",
            message=f"{count} users with access{scope_note}",
            details=details,
            weight=0.7,
        )
    elif count == 0:
        return CheckResult(
            name="user_count",
            category="access",
            status="warn",
            message="No users found at property or account level",
            details=details,
            weight=0.7,
        )
    else:
        return CheckResult(
            name="user_count",
            category="access",
            status="warn",
            message=f"{count} users with access{scope_note} (consider reviewing)",
            details=details,
            weight=0.7,
        )


def check_admin_count(ctx: CheckContext) -> CheckResult:
    """Check if too many users have admin role."""
    bindings, scope = _effective_bindings(ctx)
    admins = [
        b for b in bindings if "admin" in [r.lower() for r in b.get("roles", [])]
    ]
    admin_emails = [a.get("user", "") for a in admins]
    details = {"admin_count": len(admins), "admins": admin_emails, "access_scope": scope}

    scope_note = f" ({scope}-level)" if scope != "none" else ""

    if len(admins) == 0 and not bindings:
        return CheckResult(
            name="admin_count",
            category="access",
            status="warn",
            message="No access bindings found at any level",
            details=details,
            weight=0.8,
        )
    elif len(admins) == 0:
        return CheckResult(
            name="admin_count",
            category="access",
            status="fail",
            message=f"No admin users found{scope_note}",
            details=details,
            weight=0.8,
        )
    elif len(admins) <= 3:
        return CheckResult(
            name="admin_count",
            category="access",
            status="pass",
            message=f"{len(admins)} admin user(s){scope_note}",
            details=details,
            weight=0.8,
        )
    else:
        return CheckResult(
            name="admin_count",
            category="access",
            status="warn",
            message=f"{len(admins)} admin users{scope_note} (recommended: 1-3)",
            details=details,
            weight=0.8,
        )


def check_external_domains(ctx: CheckContext) -> CheckResult:
    """Check for users from external domains."""
    bindings, scope = _effective_bindings(ctx)
    if not bindings:
        return CheckResult(
            name="external_domains",
            category="access",
            status="warn",
            message="No access bindings found at any level",
            weight=0.6,
        )

    scope_note = f" ({scope}-level)" if scope != "none" else ""

    # Find the most common domain (assumed to be the org domain)
    domains = {}
    for b in bindings:
        email = b.get("user", "")
        if "@" in email:
            domain = email.split("@")[1].lower()
            domains[domain] = domains.get(domain, 0) + 1

    if not domains:
        return CheckResult(
            name="external_domains",
            category="access",
            status="warn",
            message="Could not determine email domains",
            weight=0.6,
        )

    primary_domain = max(domains, key=domains.get)
    external_users = []
    for b in bindings:
        email = b.get("user", "")
        if "@" in email:
            domain = email.split("@")[1].lower()
            if domain != primary_domain:
                external_users.append({
                    "email": email,
                    "domain": domain,
                    "roles": b.get("roles", []),
                })

    details = {
        "primary_domain": primary_domain,
        "external_count": len(external_users),
        "external_users": external_users,
        "access_scope": scope,
    }

    if not external_users:
        return CheckResult(
            name="external_domains",
            category="access",
            status="pass",
            message=f"All users from {primary_domain}{scope_note}",
            details=details,
            weight=0.6,
        )

    # Check if external users have elevated roles
    elevated = [
        u for u in external_users
        if any(r.lower() in ("admin", "editor") for r in u.get("roles", []))
    ]

    if elevated:
        return CheckResult(
            name="external_domains",
            category="access",
            status="warn",
            message=f"{len(external_users)} external user(s), {len(elevated)} with admin/editor access{scope_note}",
            details=details,
            weight=0.6,
        )
    else:
        return CheckResult(
            name="external_domains",
            category="access",
            status="pass",
            message=f"{len(external_users)} external user(s) (viewer only){scope_note}",
            details=details,
            weight=0.6,
        )


def check_role_distribution(ctx: CheckContext) -> CheckResult:
    """Check for healthy role distribution."""
    bindings, scope = _effective_bindings(ctx)
    if not bindings:
        return CheckResult(
            name="role_distribution",
            category="access",
            status="warn",
            message="No access bindings found at any level",
            weight=0.4,
        )

    scope_note = f" ({scope}-level)" if scope != "none" else ""

    role_counts = {}
    for b in bindings:
        for role in b.get("roles", []):
            role = role.lower()
            role_counts[role] = role_counts.get(role, 0) + 1

    details = {"role_counts": role_counts, "total_users": len(bindings), "access_scope": scope}

    if len(role_counts) == 1 and "admin" in role_counts:
        return CheckResult(
            name="role_distribution",
            category="access",
            status="warn",
            message=f"All users have admin role{scope_note} — consider principle of least privilege",
            details=details,
            weight=0.4,
        )
    elif len(role_counts) >= 2:
        return CheckResult(
            name="role_distribution",
            category="access",
            status="pass",
            message=f"Role mix{scope_note}: {', '.join(f'{r}: {c}' for r, c in sorted(role_counts.items()))}",
            details=details,
            weight=0.4,
        )
    else:
        return CheckResult(
            name="role_distribution",
            category="access",
            status="warn",
            message=f"All users have same role{scope_note}: {list(role_counts.keys())[0]}",
            details=details,
            weight=0.4,
        )


# =============================================================================
# ENGAGEMENT CHECKS
# =============================================================================


def check_engagement_rate(ctx: CheckContext) -> CheckResult:
    """Check engagement rate from 30-day data."""
    report = ctx.engagement_report
    if not report or not report.get("rows"):
        return CheckResult(
            name="engagement_rate",
            category="tracking",
            status="warn",
            message="No engagement data available",
            weight=0.6,
        )

    rows = report["rows"]
    total_sessions = sum(int(r.get("sessions", 0)) for r in rows)
    engaged_sessions = sum(int(r.get("engagedSessions", 0)) for r in rows)

    if total_sessions == 0:
        return CheckResult(
            name="engagement_rate",
            category="tracking",
            status="fail",
            message="Zero sessions in 30-day period",
            weight=0.6,
        )

    rate = (engaged_sessions / total_sessions) * 100
    details = {
        "engagement_rate": round(rate, 1),
        "engaged_sessions": engaged_sessions,
        "total_sessions": total_sessions,
        "period": "30 days",
    }

    if rate >= 50:
        return CheckResult(
            name="engagement_rate",
            category="tracking",
            status="pass",
            message=f"Engagement rate: {rate:.1f}% ({engaged_sessions:,}/{total_sessions:,} sessions)",
            details=details,
            weight=0.6,
        )
    elif rate >= 30:
        return CheckResult(
            name="engagement_rate",
            category="tracking",
            status="warn",
            message=f"Low engagement: {rate:.1f}% of sessions engaged",
            details=details,
            weight=0.6,
        )
    else:
        return CheckResult(
            name="engagement_rate",
            category="tracking",
            status="fail",
            message=f"Very low engagement: {rate:.1f}% — check event implementation",
            details=details,
            weight=0.6,
        )


def check_traffic_trend(ctx: CheckContext) -> CheckResult:
    """Check 30-day traffic trend (week-over-week comparison)."""
    report = ctx.engagement_report
    if not report or not report.get("rows") or len(report["rows"]) < 14:
        return CheckResult(
            name="traffic_trend",
            category="tracking",
            status="warn",
            message="Insufficient data for trend analysis (need 14+ days)",
            weight=0.5,
        )

    rows = sorted(report["rows"], key=lambda r: r.get("date", ""))

    # Split into recent 7 days vs prior 7 days
    recent = rows[-7:]
    prior = rows[-14:-7]

    recent_sessions = sum(int(r.get("sessions", 0)) for r in recent)
    prior_sessions = sum(int(r.get("sessions", 0)) for r in prior)

    if prior_sessions == 0:
        if recent_sessions > 0:
            return CheckResult(
                name="traffic_trend",
                category="tracking",
                status="pass",
                message=f"Traffic recovered: {recent_sessions:,} sessions this week (was 0)",
                details={"recent_sessions": recent_sessions, "prior_sessions": 0, "change_pct": None},
                weight=0.5,
            )
        return CheckResult(
            name="traffic_trend",
            category="tracking",
            status="fail",
            message="Zero traffic for 14+ days",
            details={"recent_sessions": 0, "prior_sessions": 0, "change_pct": None},
            weight=0.5,
        )

    change_pct = ((recent_sessions - prior_sessions) / prior_sessions) * 100
    details = {
        "recent_sessions": recent_sessions,
        "prior_sessions": prior_sessions,
        "change_pct": round(change_pct, 1),
    }

    if change_pct >= -20:
        return CheckResult(
            name="traffic_trend",
            category="tracking",
            status="pass",
            message=f"Traffic trend: {change_pct:+.1f}% week-over-week ({prior_sessions:,} → {recent_sessions:,})",
            details=details,
            weight=0.5,
        )
    elif change_pct >= -50:
        return CheckResult(
            name="traffic_trend",
            category="tracking",
            status="warn",
            message=f"Traffic declining: {change_pct:+.1f}% week-over-week ({prior_sessions:,} → {recent_sessions:,})",
            details=details,
            weight=0.5,
        )
    else:
        return CheckResult(
            name="traffic_trend",
            category="tracking",
            status="fail",
            message=f"Traffic dropped {change_pct:+.1f}% week-over-week ({prior_sessions:,} → {recent_sessions:,})",
            details=details,
            weight=0.5,
        )


def check_event_diversity(ctx: CheckContext) -> CheckResult:
    """Check if pageviews and events are being captured beyond sessions."""
    report = ctx.engagement_report
    if not report or not report.get("rows"):
        return CheckResult(
            name="event_diversity",
            category="tracking",
            status="warn",
            message="No event data available",
            weight=0.4,
        )

    rows = report["rows"]
    total_sessions = sum(int(r.get("sessions", 0)) for r in rows)
    total_events = sum(int(r.get("eventCount", 0)) for r in rows)
    total_pageviews = sum(int(r.get("screenPageViews", 0)) for r in rows)

    if total_sessions == 0:
        return CheckResult(
            name="event_diversity",
            category="tracking",
            status="fail",
            message="No session data for event analysis",
            weight=0.4,
        )

    events_per_session = total_events / total_sessions
    pages_per_session = total_pageviews / total_sessions

    details = {
        "events_per_session": round(events_per_session, 1),
        "pages_per_session": round(pages_per_session, 1),
        "total_events": total_events,
        "total_pageviews": total_pageviews,
        "total_sessions": total_sessions,
        "period": "30 days",
    }

    if events_per_session >= 3 and pages_per_session >= 1.5:
        return CheckResult(
            name="event_diversity",
            category="tracking",
            status="pass",
            message=f"{events_per_session:.1f} events/session, {pages_per_session:.1f} pages/session",
            details=details,
            weight=0.4,
        )
    elif events_per_session >= 1:
        return CheckResult(
            name="event_diversity",
            category="tracking",
            status="warn",
            message=f"Low event capture: {events_per_session:.1f} events/session — consider adding custom events",
            details=details,
            weight=0.4,
        )
    else:
        return CheckResult(
            name="event_diversity",
            category="tracking",
            status="fail",
            message=f"Minimal event capture: {events_per_session:.1f} events/session — tracking may be broken",
            details=details,
            weight=0.4,
        )


# =============================================================================
# CHECK REGISTRY AND RUNNER
# =============================================================================

ALL_CHECKS = [
    # Tracking (7-day)
    {"fn": check_data_recency, "category": "tracking"},
    {"fn": check_realtime_active, "category": "tracking"},
    {"fn": check_session_volume, "category": "tracking"},
    {"fn": check_not_set_prevalence, "category": "tracking"},
    {"fn": check_bounce_rate, "category": "tracking"},
    # Tracking (30-day engagement)
    {"fn": check_engagement_rate, "category": "tracking"},
    {"fn": check_traffic_trend, "category": "tracking"},
    {"fn": check_event_diversity, "category": "tracking"},
    # Tag implementation
    {"fn": check_double_tagging, "category": "tracking"},
    {"fn": check_self_referrals, "category": "tracking"},
    {"fn": check_hostname_fragmentation, "category": "tracking"},
    {"fn": check_channel_grouping, "category": "tracking"},
    # Config
    {"fn": check_property_config, "category": "config"},
    {"fn": check_data_streams, "category": "config"},
    {"fn": check_key_events, "category": "config"},
    {"fn": check_custom_dimensions, "category": "config"},
    {"fn": check_enhanced_measurement, "category": "config"},
    {"fn": check_audiences, "category": "config"},
    {"fn": check_google_ads_link, "category": "config"},
    {"fn": check_data_retention, "category": "config"},
    # Access (uses account-level fallback)
    {"fn": check_user_count, "category": "access"},
    {"fn": check_admin_count, "category": "access"},
    {"fn": check_external_domains, "category": "access"},
    {"fn": check_role_distribution, "category": "access"},
]


def run_checks(
    ctx: CheckContext,
    categories: Optional[list[str]] = None,
) -> list[CheckResult]:
    """Run all checks (or filtered by category) against pre-fetched context."""
    results = []
    for check in ALL_CHECKS:
        if categories and check["category"] not in categories:
            continue
        try:
            result = check["fn"](ctx)
            results.append(result)
        except Exception as e:
            results.append(
                CheckResult(
                    name=check["fn"].__name__.replace("check_", ""),
                    category=check["category"],
                    status="error",
                    message=f"Check failed: {e}",
                )
            )
    return results


def calculate_score(results: list[CheckResult]) -> dict:
    """Calculate weighted health score from check results.

    Returns dict with score (0-100), grade (A-F), and summary counts.
    """
    status_counts = {"pass": 0, "warn": 0, "fail": 0, "error": 0}
    earned = 0.0
    possible = 0.0

    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        if r.status == "error":
            continue  # exclude from score
        possible += r.weight
        if r.status == "pass":
            earned += r.weight
        elif r.status == "warn":
            earned += r.weight * 0.5

    score = round((earned / possible) * 100) if possible > 0 else 0

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "summary": status_counts,
    }
