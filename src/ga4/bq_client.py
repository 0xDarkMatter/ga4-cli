"""BigQuery client for GA4 export datasets.

Queries GA4 BigQuery export tables (events_, events_intraday_) using the
BigQuery REST API via httpx. Does NOT require google-cloud-bigquery — uses
the same OAuth tokens as the rest of the tool.
"""

from __future__ import annotations

from typing import Optional

import httpx

from .config import DEFAULT_PROFILE, get_tokens, is_token_expired, refresh_credentials


# GA4 BQ export dataset naming convention
def ga4_dataset(property_id: str) -> str:
    """Return the GA4 BQ export dataset name for a property."""
    pid = property_id.replace("properties/", "")
    return f"analytics_{pid}"


# Pre-built query templates for GA4 BQ exports
QUERY_TEMPLATES = {
    "ai-traffic": {
        "name": "AI Traffic",
        "description": "Sessions from AI platforms (ChatGPT, Claude, Gemini, etc.)",
        "sql": """
SELECT
  event_date,
  traffic_source.source AS source,
  traffic_source.medium AS medium,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNT(*) AS events
FROM `{project}.{dataset}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
  AND REGEXP_CONTAINS(
    traffic_source.source,
    r'chatgpt\\.com|chat\\.openai\\.com|claude\\.ai|perplexity\\.ai|pplx\\.ai'
    r'|gemini\\.google\\.com|copilot\\.microsoft\\.com|edgepilot|edgeservices'
    r'|deepseek\\.com|meta\\.ai|grok\\.com|you\\.com|phind\\.com|poe\\.com'
    r'|chat\\.mistral\\.ai'
  )
GROUP BY 1, 2, 3
ORDER BY event_date DESC, users DESC
""",
    },
    "sessions": {
        "name": "Daily Sessions",
        "description": "Session count and users by day",
        "sql": """
SELECT
  event_date,
  COUNT(DISTINCT CONCAT(user_pseudo_id, CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING))) AS sessions,
  COUNT(DISTINCT user_pseudo_id) AS users
FROM `{project}.{dataset}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
  AND event_name = 'session_start'
GROUP BY 1
ORDER BY 1 DESC
""",
    },
    "top-pages": {
        "name": "Top Pages",
        "description": "Most viewed pages by pageview count",
        "sql": """
SELECT
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location') AS page,
  COUNT(*) AS pageviews,
  COUNT(DISTINCT user_pseudo_id) AS users
FROM `{project}.{dataset}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
  AND event_name = 'page_view'
GROUP BY 1
ORDER BY pageviews DESC
LIMIT 50
""",
    },
    "events": {
        "name": "Event Counts",
        "description": "Event frequency breakdown",
        "sql": """
SELECT
  event_name,
  COUNT(*) AS event_count,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNT(DISTINCT event_date) AS days_active
FROM `{project}.{dataset}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
GROUP BY 1
ORDER BY event_count DESC
LIMIT 50
""",
    },
    "channels": {
        "name": "Channel Breakdown",
        "description": "Traffic by source/medium with session counts",
        "sql": """
SELECT
  traffic_source.source AS source,
  traffic_source.medium AS medium,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNT(DISTINCT CONCAT(user_pseudo_id, CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING))) AS sessions
FROM `{project}.{dataset}.events_*`
WHERE _TABLE_SUFFIX BETWEEN '{start}' AND '{end}'
  AND event_name = 'session_start'
GROUP BY 1, 2
ORDER BY sessions DESC
LIMIT 50
""",
    },
}


class BQClient:
    """BigQuery REST API client using GA4 OAuth tokens."""

    BASE_URL = "https://bigquery.googleapis.com/bigquery/v2"
    TIMEOUT = 60

    def __init__(self, profile: str = DEFAULT_PROFILE):
        self._profile = profile
        self._ensure_valid_token()
        tokens = get_tokens(profile)
        self.token = tokens.get("access_token") if tokens else None

    def _ensure_valid_token(self) -> None:
        if is_token_expired(profile=self._profile):
            refresh_credentials(profile=self._profile)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def list_tables(self, project: str, dataset: str) -> list:
        """List tables in a BQ dataset."""
        url = f"{self.BASE_URL}/projects/{project}/datasets/{dataset}/tables"
        all_tables = []
        page_token = None

        while True:
            params = {"maxResults": 1000}
            if page_token:
                params["pageToken"] = page_token

            resp = httpx.get(url, headers=self._headers(), params=params, timeout=self.TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            for t in data.get("tables", []):
                ref = t.get("tableReference", {})
                all_tables.append({
                    "table_id": ref.get("tableId", ""),
                    "type": t.get("type", ""),
                    "creation_time": t.get("creationTime"),
                    "row_count": t.get("numRows"),
                    "size_bytes": t.get("numBytes"),
                })

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return all_tables

    def get_table_schema(self, project: str, dataset: str, table: str) -> dict:
        """Get schema for a BQ table."""
        url = f"{self.BASE_URL}/projects/{project}/datasets/{dataset}/tables/{table}"
        resp = httpx.get(url, headers=self._headers(), timeout=self.TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        fields = data.get("schema", {}).get("fields", [])
        return {
            "table_id": data.get("tableReference", {}).get("tableId", ""),
            "row_count": data.get("numRows"),
            "size_bytes": data.get("numBytes"),
            "fields": [
                {
                    "name": f.get("name", ""),
                    "type": f.get("type", ""),
                    "mode": f.get("mode", ""),
                    "description": f.get("description", ""),
                }
                for f in fields
            ],
        }

    def run_query(self, project: str, sql: str, dry_run: bool = False) -> dict:
        """Run a BQ query or dry-run for cost estimation.

        Args:
            project: GCP project ID
            sql: SQL query string
            dry_run: If True, only estimate bytes without executing

        Returns:
            Dict with rows (or bytes estimate for dry run)
        """
        url = f"{self.BASE_URL}/projects/{project}/queries"
        body = {
            "query": sql,
            "useLegacySql": False,
            "dryRun": dry_run,
        }

        resp = httpx.post(url, headers=self._headers(), json=body, timeout=self.TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if dry_run:
            total_bytes = int(data.get("totalBytesProcessed", 0))
            return {
                "dry_run": True,
                "total_bytes": total_bytes,
                "total_mb": round(total_bytes / (1024 * 1024), 2),
                "total_gb": round(total_bytes / (1024 * 1024 * 1024), 4),
                "estimated_cost_usd": round(total_bytes / (1024**4) * 6.25, 4),
            }

        # Parse query results
        schema_fields = [f.get("name", "") for f in data.get("schema", {}).get("fields", [])]
        rows = []
        for row in data.get("rows", []):
            values = [cell.get("v") for cell in row.get("f", [])]
            rows.append(dict(zip(schema_fields, values)))

        return {
            "rows": rows,
            "total_rows": int(data.get("totalRows", 0)),
            "total_bytes": int(data.get("totalBytesProcessed", 0)),
            "cache_hit": data.get("cacheHit", False),
        }

    def check_dataset_exists(self, project: str, dataset: str) -> bool:
        """Check if a dataset exists."""
        url = f"{self.BASE_URL}/projects/{project}/datasets/{dataset}"
        try:
            resp = httpx.get(url, headers=self._headers(), timeout=self.TIMEOUT)
            return resp.status_code == 200
        except Exception:
            return False

    def get_freshness(self, project: str, dataset: str) -> dict:
        """Check data freshness by finding latest event tables.

        Returns dict with latest daily/intraday table dates and lag.
        """
        from datetime import datetime, timezone

        tables = self.list_tables(project, dataset)

        latest_daily = None
        latest_intraday = None

        for t in tables:
            tid = t["table_id"]
            if tid.startswith("events_") and not tid.startswith("events_intraday_"):
                date_part = tid.replace("events_", "")
                if date_part.isdigit() and len(date_part) == 8:
                    if latest_daily is None or date_part > latest_daily:
                        latest_daily = date_part
            elif tid.startswith("events_intraday_"):
                date_part = tid.replace("events_intraday_", "")
                if date_part.isdigit() and len(date_part) == 8:
                    if latest_intraday is None or date_part > latest_intraday:
                        latest_intraday = date_part

        now = datetime.now(timezone.utc)
        result = {
            "latest_daily": latest_daily,
            "latest_intraday": latest_intraday,
            "table_count": len(tables),
        }

        if latest_daily:
            daily_dt = datetime.strptime(latest_daily, "%Y%m%d").replace(tzinfo=timezone.utc)
            result["daily_lag_hours"] = round((now - daily_dt).total_seconds() / 3600, 1)

        if latest_intraday:
            intraday_dt = datetime.strptime(latest_intraday, "%Y%m%d").replace(tzinfo=timezone.utc)
            result["intraday_lag_hours"] = round((now - intraday_dt).total_seconds() / 3600, 1)

        return result

    def list_datasets(self, project: str) -> list:
        """List datasets in a project, filtering for GA4 analytics_ datasets."""
        url = f"{self.BASE_URL}/projects/{project}/datasets"
        all_datasets = []
        page_token = None

        while True:
            params = {"maxResults": 1000}
            if page_token:
                params["pageToken"] = page_token

            resp = httpx.get(url, headers=self._headers(), params=params, timeout=self.TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            for ds in data.get("datasets", []):
                ref = ds.get("datasetReference", {})
                all_datasets.append({
                    "dataset_id": ref.get("datasetId", ""),
                    "project": ref.get("projectId", ""),
                    "location": ds.get("location", ""),
                    "is_ga4": ref.get("datasetId", "").startswith("analytics_"),
                })

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return all_datasets
