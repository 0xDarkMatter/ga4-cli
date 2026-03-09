"""Google Analytics Data API client.

Handles report generation and metadata via analyticsdata.googleapis.com.
"""

from typing import Optional

import httpx

from .config import DEFAULT_PROFILE, get_tokens, is_token_expired, refresh_credentials
from .errors import RateLimitError


class DataClient:
    """Google Analytics Data API client."""

    BASE_URL = "https://analyticsdata.googleapis.com/v1beta"
    TIMEOUT = 30

    def __init__(self, profile: str = DEFAULT_PROFILE):
        self._profile = profile
        self._ensure_valid_token()
        tokens = get_tokens(profile)
        self.token = tokens.get("access_token") if tokens else None

    def _ensure_valid_token(self) -> None:
        """Refresh token if expired."""
        if is_token_expired(profile=self._profile):
            refresh_credentials(profile=self._profile)

    def _headers(self) -> dict:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """Raise RateLimitError if response is 429."""
        if response.status_code == 429:
            raise RateLimitError()

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make GET request."""
        response = httpx.get(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            params=params,
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        """Make POST request."""
        response = httpx.post(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            json=data,
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    # --- Metadata Methods ---

    def get_metadata(self, property_id: str) -> dict:
        """Get all available dimensions and metrics for a property.

        Args:
            property_id: Property ID (e.g., "123456789")

        Returns:
            Dict with 'dimensions' and 'metrics' lists
        """
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        data = self._get(f"{property_id}/metadata")
        return data

    def list_dimensions(self, property_id: str, limit: int = 200) -> list:
        """List available dimensions for a property.

        Args:
            property_id: Property ID
            limit: Max results

        Returns:
            List of dimension dicts
        """
        metadata = self.get_metadata(property_id)
        dimensions = metadata.get("dimensions", [])

        return [
            {
                "api_name": d.get("apiName", ""),
                "name": d.get("uiName", ""),
                "description": d.get("description", ""),
                "category": d.get("category", ""),
                "deprecated": d.get("deprecatedApiNames", []),
            }
            for d in dimensions[:limit]
        ]

    def list_metrics(self, property_id: str, limit: int = 200) -> list:
        """List available metrics for a property.

        Args:
            property_id: Property ID
            limit: Max results

        Returns:
            List of metric dicts
        """
        metadata = self.get_metadata(property_id)
        metrics = metadata.get("metrics", [])

        return [
            {
                "api_name": m.get("apiName", ""),
                "name": m.get("uiName", ""),
                "description": m.get("description", ""),
                "category": m.get("category", ""),
                "type": m.get("type", ""),
                "expression": m.get("expression", ""),
                "deprecated": m.get("deprecatedApiNames", []),
            }
            for m in metrics[:limit]
        ]

    def get_dimension(self, property_id: str, api_name: str) -> Optional[dict]:
        """Get a specific dimension by API name.

        Args:
            property_id: Property ID
            api_name: Dimension API name (e.g., "city", "date")

        Returns:
            Dimension dict or None if not found
        """
        dimensions = self.list_dimensions(property_id, limit=500)
        return next((d for d in dimensions if d["api_name"] == api_name), None)

    def get_metric(self, property_id: str, api_name: str) -> Optional[dict]:
        """Get a specific metric by API name.

        Args:
            property_id: Property ID
            api_name: Metric API name (e.g., "activeUsers", "sessions")

        Returns:
            Metric dict or None if not found
        """
        metrics = self.list_metrics(property_id, limit=500)
        return next((m for m in metrics if m["api_name"] == api_name), None)

    # --- Report Methods ---

    def run_report(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        start_date: str = "30daysAgo",
        end_date: str = "today",
        limit: int = 10000,
        offset: int = 0,
        order_by: Optional[str] = None,
        descending: bool = True,
        dimension_filter: Optional[dict] = None,
        metric_filter: Optional[dict] = None,
    ) -> dict:
        """Run a report with specified dimensions and metrics.

        Args:
            property_id: Property ID (e.g., "123456789")
            dimensions: List of dimension API names (e.g., ["date", "city"])
            metrics: List of metric API names (e.g., ["activeUsers", "sessions"])
            start_date: Start date (YYYY-MM-DD or relative like "30daysAgo")
            end_date: End date (YYYY-MM-DD or relative like "today")
            limit: Max rows to return
            offset: Row offset for pagination
            order_by: Dimension or metric to sort by
            descending: Sort descending (default True)
            dimension_filter: Optional dimension filter
            metric_filter: Optional metric filter

        Returns:
            Report data dict with 'rows', 'dimension_headers', 'metric_headers'
        """
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        request_body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "offset": offset,
        }

        # Add ordering if specified
        if order_by:
            order_type = "METRIC" if order_by in metrics else "DIMENSION"
            request_body["orderBys"] = [
                {
                    order_type.lower(): {"metricName" if order_type == "METRIC" else "dimensionName": order_by},
                    "desc": descending,
                }
            ]

        # Add filters if specified
        if dimension_filter:
            request_body["dimensionFilter"] = dimension_filter
        if metric_filter:
            request_body["metricFilter"] = metric_filter

        data = self._post(f"{property_id}:runReport", request_body)

        # Transform response to simpler format
        dimension_headers = [h.get("name", "") for h in data.get("dimensionHeaders", [])]
        metric_headers = [h.get("name", "") for h in data.get("metricHeaders", [])]

        rows = []
        for row in data.get("rows", []):
            row_data = {}

            # Add dimension values
            for i, dim_value in enumerate(row.get("dimensionValues", [])):
                if i < len(dimension_headers):
                    row_data[dimension_headers[i]] = dim_value.get("value", "")

            # Add metric values
            for i, metric_value in enumerate(row.get("metricValues", [])):
                if i < len(metric_headers):
                    row_data[metric_headers[i]] = metric_value.get("value", "")

            rows.append(row_data)

        return {
            "rows": rows,
            "dimension_headers": dimension_headers,
            "metric_headers": metric_headers,
            "row_count": data.get("rowCount", len(rows)),
            "metadata": data.get("metadata", {}),
        }

    def run_realtime_report(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        limit: int = 10000,
    ) -> dict:
        """Run a realtime report.

        Args:
            property_id: Property ID
            dimensions: List of dimension API names
            metrics: List of metric API names
            limit: Max rows

        Returns:
            Report data dict
        """
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        request_body = {
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
        }

        data = self._post(f"{property_id}:runRealtimeReport", request_body)

        # Transform response (same format as run_report)
        dimension_headers = [h.get("name", "") for h in data.get("dimensionHeaders", [])]
        metric_headers = [h.get("name", "") for h in data.get("metricHeaders", [])]

        rows = []
        for row in data.get("rows", []):
            row_data = {}
            for i, dim_value in enumerate(row.get("dimensionValues", [])):
                if i < len(dimension_headers):
                    row_data[dimension_headers[i]] = dim_value.get("value", "")
            for i, metric_value in enumerate(row.get("metricValues", [])):
                if i < len(metric_headers):
                    row_data[metric_headers[i]] = metric_value.get("value", "")
            rows.append(row_data)

        return {
            "rows": rows,
            "dimension_headers": dimension_headers,
            "metric_headers": metric_headers,
            "row_count": data.get("rowCount", len(rows)),
        }


# Backwards compatibility alias
Client = DataClient
