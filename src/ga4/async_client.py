"""Async Google Analytics API clients.

Provides AsyncAdminClient and AsyncDataClient using httpx.AsyncClient
for concurrent API calls during health checks and scans.
"""

from __future__ import annotations

from typing import Optional

import httpx

from .config import DEFAULT_PROFILE, get_tokens, is_token_expired, refresh_credentials
from .errors import RateLimitError

# Reuse role mappings from sync client
from .admin_client import ROLES, ROLE_DISPLAY


class _AsyncBase:
    """Shared async HTTP methods."""

    TIMEOUT = 30

    def __init__(self, token: str, base_url: str, base_url_alpha: str | None = None):
        self.token = token
        self.base_url = base_url
        self.base_url_alpha = base_url_alpha
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.TIMEOUT)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _check_rate_limit(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise RateLimitError()

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        response = await self._client.get(
            f"{self.base_url}/{endpoint}",
            headers=self._headers(),
            params=params,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    async def _post(self, endpoint: str, data: dict) -> dict:
        response = await self._client.post(
            f"{self.base_url}/{endpoint}",
            headers=self._headers(),
            json=data,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    async def _get_alpha(self, endpoint: str, params: dict = None) -> dict:
        response = await self._client.get(
            f"{self.base_url_alpha}/{endpoint}",
            headers=self._headers(),
            params=params,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    async def _post_alpha(self, endpoint: str, data: dict) -> dict:
        response = await self._client.post(
            f"{self.base_url_alpha}/{endpoint}",
            headers=self._headers(),
            json=data,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()


class AsyncAdminClient(_AsyncBase):
    """Async Google Analytics Admin API client."""

    def __init__(self, token: str):
        super().__init__(
            token=token,
            base_url="https://analyticsadmin.googleapis.com/v1beta",
            base_url_alpha="https://analyticsadmin.googleapis.com/v1alpha",
        )

    async def get_property(self, property_id: str) -> Optional[dict]:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        try:
            data = await self._get(property_id)
            return {
                "id": data.get("name", "").replace("properties/", ""),
                "name": data.get("displayName", ""),
                "account": data.get("account", ""),
                "create_time": data.get("createTime"),
                "update_time": data.get("updateTime"),
                "industry_category": data.get("industryCategory"),
                "time_zone": data.get("timeZone"),
                "currency": data.get("currencyCode"),
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def list_access_bindings(self, property_id: str, limit: int = 200) -> list:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        all_bindings = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = await self._get_alpha(f"{property_id}/accessBindings", params)
            all_bindings.extend(data.get("accessBindings", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_bindings) >= limit:
                break

        return [
            {
                "id": b.get("name", "").split("/")[-1],
                "user": b.get("user", ""),
                "roles": [ROLE_DISPLAY.get(r, r) for r in b.get("roles", [])],
                "name": b.get("name", ""),
            }
            for b in all_bindings[:limit]
        ]

    async def list_accounts(self, limit: int = 200) -> list:
        all_accounts = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("accounts", params)
            all_accounts.extend(data.get("accounts", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_accounts) >= limit:
                break

        return all_accounts[:limit]

    async def list_data_streams(self, property_id: str) -> list:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        data = await self._get(f"{property_id}/dataStreams", {"pageSize": 200})
        results = []
        for s in data.get("dataStreams", []):
            stream = {
                "name": s.get("name", ""),
                "type": s.get("type", ""),
                "display_name": s.get("displayName", ""),
                "create_time": s.get("createTime"),
                "update_time": s.get("updateTime"),
            }
            if s.get("webStreamData"):
                stream["measurement_id"] = s["webStreamData"].get("measurementId", "")
                stream["default_uri"] = s["webStreamData"].get("defaultUri", "")
            if s.get("androidAppStreamData"):
                stream["package_name"] = s["androidAppStreamData"].get("packageName", "")
            if s.get("iosAppStreamData"):
                stream["bundle_id"] = s["iosAppStreamData"].get("bundleId", "")
            results.append(stream)
        return results

    async def list_key_events(self, property_id: str) -> list:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        data = await self._get(f"{property_id}/keyEvents", {"pageSize": 200})
        return [
            {
                "name": e.get("name", ""),
                "event_name": e.get("eventName", ""),
                "create_time": e.get("createTime"),
                "custom": e.get("custom", False),
                "deletable": e.get("deletable", False),
                "counting_method": e.get("countingMethod", ""),
            }
            for e in data.get("keyEvents", [])
        ]

    async def list_custom_dimensions(self, property_id: str) -> list:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        data = await self._get(f"{property_id}/customDimensions", {"pageSize": 200})
        return [
            {
                "name": d.get("name", ""),
                "parameter_name": d.get("parameterName", ""),
                "display_name": d.get("displayName", ""),
                "description": d.get("description", ""),
                "scope": d.get("scope", ""),
            }
            for d in data.get("customDimensions", [])
        ]

    async def list_custom_metrics(self, property_id: str) -> list:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        data = await self._get(f"{property_id}/customMetrics", {"pageSize": 200})
        return [
            {
                "name": m.get("name", ""),
                "parameter_name": m.get("parameterName", ""),
                "display_name": m.get("displayName", ""),
                "description": m.get("description", ""),
                "scope": m.get("scope", ""),
                "measurement_unit": m.get("measurementUnit", ""),
            }
            for m in data.get("customMetrics", [])
        ]

    async def list_google_ads_links(self, property_id: str) -> list:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        data = await self._get(f"{property_id}/googleAdsLinks", {"pageSize": 200})
        return [
            {
                "name": link.get("name", ""),
                "customer_id": link.get("customerId", ""),
                "can_manage_clients": link.get("canManageClients", False),
                "ads_personalization_enabled": link.get("adsPersonalizationEnabled", False),
                "create_time": link.get("createTime"),
            }
            for link in data.get("googleAdsLinks", [])
        ]

    async def list_audiences(self, property_id: str) -> list:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        data = await self._get_alpha(f"{property_id}/audiences", {"pageSize": 200})
        return [
            {
                "name": a.get("name", ""),
                "display_name": a.get("displayName", ""),
                "description": a.get("description", ""),
                "membership_duration_days": a.get("membershipDurationDays"),
            }
            for a in data.get("audiences", [])
        ]

    async def get_enhanced_measurement(self, property_id: str, stream_id: str) -> dict:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        try:
            data = await self._get_alpha(
                f"{property_id}/dataStreams/{stream_id}/enhancedMeasurementSettings"
            )
            return {
                "stream_enabled": data.get("streamEnabled", False),
                "scrolls_enabled": data.get("scrollsEnabled", False),
                "outbound_clicks_enabled": data.get("outboundClicksEnabled", False),
                "site_search_enabled": data.get("siteSearchEnabled", False),
                "video_engagement_enabled": data.get("videoEngagementEnabled", False),
                "file_downloads_enabled": data.get("fileDownloadsEnabled", False),
                "page_changes_enabled": data.get("pageChangesEnabled", False),
                "form_interactions_enabled": data.get("formInteractionsEnabled", False),
            }
        except Exception:
            return {}

    async def get_data_retention_settings(self, property_id: str) -> dict:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        try:
            data = await self._get(f"{property_id}/dataRetentionSettings")
            return {
                "event_data_retention": data.get("eventDataRetention", ""),
                "user_data_retention": data.get("userDataRetention", ""),
                "reset_on_new_activity": data.get("resetUserDataOnNewActivity", False),
            }
        except Exception:
            return {}

    async def list_account_access_bindings(self, account_id: str) -> list:
        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        all_bindings = []
        page_token = None

        while True:
            params = {"pageSize": 200}
            if page_token:
                params["pageToken"] = page_token

            data = await self._get_alpha(f"{account_id}/accessBindings", params)
            all_bindings.extend(data.get("accessBindings", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return [
            {
                "id": b.get("name", "").split("/")[-1],
                "user": b.get("user", ""),
                "roles": [ROLE_DISPLAY.get(r, r) for r in b.get("roles", [])],
                "name": b.get("name", ""),
            }
            for b in all_bindings
        ]

    async def list_properties(self, account_id: Optional[str] = None, limit: int = 200) -> list:
        if not account_id:
            all_properties = []
            accounts = await self.list_accounts(limit=500)
            for account in accounts:
                acc_id = account.get("name", "")
                if acc_id:
                    props = await self.list_properties(account_id=acc_id, limit=200)
                    all_properties.extend(props)
            return all_properties

        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        all_properties = []
        page_token = None

        while True:
            params = {
                "pageSize": min(limit, 200),
                "filter": f"parent:{account_id}",
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("properties", params)
            all_properties.extend(data.get("properties", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_properties) >= limit:
                break

        return [
            {
                "id": p.get("name", "").replace("properties/", ""),
                "name": p.get("displayName", ""),
                "account": p.get("account", ""),
                "create_time": p.get("createTime"),
                "update_time": p.get("updateTime"),
                "industry_category": p.get("industryCategory"),
                "time_zone": p.get("timeZone"),
                "currency": p.get("currencyCode"),
            }
            for p in all_properties[:limit]
        ]


class AsyncDataClient(_AsyncBase):
    """Async Google Analytics Data API client."""

    def __init__(self, token: str):
        super().__init__(
            token=token,
            base_url="https://analyticsdata.googleapis.com/v1beta",
        )

    async def get_metadata(self, property_id: str) -> dict:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        return await self._get(f"{property_id}/metadata")

    async def run_report(
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
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        request_body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
            "offset": offset,
        }

        if order_by:
            order_type = "METRIC" if order_by in metrics else "DIMENSION"
            request_body["orderBys"] = [
                {
                    order_type.lower(): {"metricName" if order_type == "METRIC" else "dimensionName": order_by},
                    "desc": descending,
                }
            ]

        if dimension_filter:
            request_body["dimensionFilter"] = dimension_filter
        if metric_filter:
            request_body["metricFilter"] = metric_filter

        data = await self._post(f"{property_id}:runReport", request_body)
        return self._transform_report(data)

    async def run_realtime_report(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        limit: int = 10000,
    ) -> dict:
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        request_body = {
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics],
            "limit": limit,
        }

        data = await self._post(f"{property_id}:runRealtimeReport", request_body)
        return self._transform_report(data)

    @staticmethod
    def _transform_report(data: dict) -> dict:
        """Transform raw GA4 API response to simplified format."""
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
            "metadata": data.get("metadata", {}),
        }


def _get_token(profile: str = DEFAULT_PROFILE) -> str:
    """Get a valid access token for a profile, refreshing if needed.

    Args:
        profile: Auth profile to use.

    Returns:
        Valid access token string.

    Raises:
        RuntimeError: If not authenticated.
    """
    if is_token_expired(profile=profile):
        refresh_credentials(profile=profile)
    tokens = get_tokens(profile)
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Not authenticated")
    return tokens["access_token"]


def create_async_clients(profile: str = DEFAULT_PROFILE) -> tuple[AsyncAdminClient, AsyncDataClient]:
    """Create async client pair with current token for a profile.

    Args:
        profile: Auth profile to use.

    Returns:
        Tuple of (AsyncAdminClient, AsyncDataClient).
    """
    token = _get_token(profile)
    return AsyncAdminClient(token), AsyncDataClient(token)
