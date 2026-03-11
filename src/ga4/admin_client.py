"""Google Analytics Admin API client.

Handles property and user management via analyticsadmin.googleapis.com.
"""

from typing import Optional

import httpx

from .config import DEFAULT_PROFILE, get_tokens, get_google_credentials, refresh_credentials, is_token_expired
from .errors import RateLimitError


# Role mapping: CLI name -> API name
ROLES = {
    "viewer": "predefinedRoles/viewer",
    "analyst": "predefinedRoles/analyst",
    "editor": "predefinedRoles/editor",
    "admin": "predefinedRoles/admin",
}

# Reverse mapping for display
ROLE_DISPLAY = {v: k for k, v in ROLES.items()}


class AdminClient:
    """Google Analytics Admin API client."""

    BASE_URL = "https://analyticsadmin.googleapis.com/v1beta"
    BASE_URL_ALPHA = "https://analyticsadmin.googleapis.com/v1alpha"
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

    def _delete(self, endpoint: str) -> bool:
        """Make DELETE request."""
        response = httpx.delete(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return True

    def _get_alpha(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make GET request to alpha API."""
        response = httpx.get(
            f"{self.BASE_URL_ALPHA}/{endpoint}",
            headers=self._headers(),
            params=params,
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    def _post_alpha(self, endpoint: str, data: dict) -> Optional[dict]:
        """Make POST request to alpha API."""
        response = httpx.post(
            f"{self.BASE_URL_ALPHA}/{endpoint}",
            headers=self._headers(),
            json=data,
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    def _patch(self, endpoint: str, data: dict, params: dict = None) -> Optional[dict]:
        """Make PATCH request."""
        response = httpx.patch(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            json=data,
            params=params,
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    def _patch_alpha(self, endpoint: str, data: dict, params: dict = None) -> Optional[dict]:
        """Make PATCH request to alpha API."""
        response = httpx.patch(
            f"{self.BASE_URL_ALPHA}/{endpoint}",
            headers=self._headers(),
            json=data,
            params=params,
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return response.json()

    def _delete_alpha(self, endpoint: str) -> bool:
        """Make DELETE request to alpha API."""
        response = httpx.delete(
            f"{self.BASE_URL_ALPHA}/{endpoint}",
            headers=self._headers(),
            timeout=self.TIMEOUT,
        )
        self._check_rate_limit(response)
        response.raise_for_status()
        return True

    # --- Account & Property Methods ---

    def list_accounts(self, limit: int = 200) -> list:
        """List all GA4 accounts accessible to the user.

        Handles pagination automatically to fetch all accounts.
        """
        all_accounts = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = self._get("accounts", params)
            accounts = data.get("accounts", [])
            all_accounts.extend(accounts)

            page_token = data.get("nextPageToken")
            if not page_token or len(all_accounts) >= limit:
                break

        return all_accounts[:limit] if limit else all_accounts

    def list_properties(self, account_id: Optional[str] = None, limit: int = 200) -> list:
        """List GA4 properties.

        Args:
            account_id: Filter by account. If not provided, lists properties from all accounts.
            limit: Max results

        Returns:
            List of property dicts
        """
        # If no account specified, get properties from all accounts
        if not account_id:
            all_properties = []
            accounts = self.list_accounts(limit=500)
            for account in accounts:
                acc_id = account.get("name", "")
                if acc_id:
                    props = self.list_properties(account_id=acc_id, limit=200)
                    all_properties.extend(props)
            return all_properties

        # Ensure proper format
        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        # Paginate through all properties
        all_properties = []
        page_token = None

        while True:
            params = {
                "pageSize": min(limit, 200),
                "filter": f"parent:{account_id}",
            }
            if page_token:
                params["pageToken"] = page_token

            data = self._get("properties", params)
            all_properties.extend(data.get("properties", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_properties) >= limit:
                break

        properties = all_properties[:limit]

        # Transform to simpler format
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
            for p in properties
        ]

    def get_property(self, property_id: str) -> Optional[dict]:
        """Get a specific property by ID."""
        # Ensure proper format
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        try:
            data = self._get(property_id)
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

    # --- Property Configuration Methods ---

    def list_data_streams(self, property_id: str, limit: int = 200) -> list:
        """List data streams for a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        all_streams = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = self._get(f"{property_id}/dataStreams", params)
            all_streams.extend(data.get("dataStreams", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_streams) >= limit:
                break

        results = []
        for s in all_streams[:limit]:
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

    def list_key_events(self, property_id: str, limit: int = 200) -> list:
        """List key events (conversions) for a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        all_events = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = self._get(f"{property_id}/keyEvents", params)
            all_events.extend(data.get("keyEvents", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_events) >= limit:
                break

        return [
            {
                "name": e.get("name", ""),
                "event_name": e.get("eventName", ""),
                "create_time": e.get("createTime"),
                "custom": e.get("custom", False),
                "deletable": e.get("deletable", False),
                "counting_method": e.get("countingMethod", ""),
            }
            for e in all_events[:limit]
        ]

    def list_custom_dimensions(self, property_id: str, limit: int = 200) -> list:
        """List custom dimensions for a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        all_dims = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = self._get(f"{property_id}/customDimensions", params)
            all_dims.extend(data.get("customDimensions", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_dims) >= limit:
                break

        return [
            {
                "name": d.get("name", ""),
                "parameter_name": d.get("parameterName", ""),
                "display_name": d.get("displayName", ""),
                "description": d.get("description", ""),
                "scope": d.get("scope", ""),
            }
            for d in all_dims[:limit]
        ]

    def list_custom_metrics(self, property_id: str, limit: int = 200) -> list:
        """List custom metrics for a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        all_metrics = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = self._get(f"{property_id}/customMetrics", params)
            all_metrics.extend(data.get("customMetrics", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_metrics) >= limit:
                break

        return [
            {
                "name": m.get("name", ""),
                "parameter_name": m.get("parameterName", ""),
                "display_name": m.get("displayName", ""),
                "description": m.get("description", ""),
                "scope": m.get("scope", ""),
                "measurement_unit": m.get("measurementUnit", ""),
            }
            for m in all_metrics[:limit]
        ]

    def list_google_ads_links(self, property_id: str) -> list:
        """List Google Ads links for a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        all_links = []
        page_token = None

        while True:
            params = {"pageSize": 200}
            if page_token:
                params["pageToken"] = page_token

            data = self._get(f"{property_id}/googleAdsLinks", params)
            all_links.extend(data.get("googleAdsLinks", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return [
            {
                "name": link.get("name", ""),
                "customer_id": link.get("customerId", ""),
                "can_manage_clients": link.get("canManageClients", False),
                "ads_personalization_enabled": link.get("adsPersonalizationEnabled", False),
                "create_time": link.get("createTime"),
            }
            for link in all_links
        ]

    def list_audiences(self, property_id: str, limit: int = 200) -> list:
        """List audiences for a property (v1alpha)."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        all_audiences = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = self._get_alpha(f"{property_id}/audiences", params)
            all_audiences.extend(data.get("audiences", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_audiences) >= limit:
                break

        return [
            {
                "name": a.get("name", ""),
                "display_name": a.get("displayName", ""),
                "description": a.get("description", ""),
                "membership_duration_days": a.get("membershipDurationDays"),
                "ads_personalization_enabled": a.get("adsPersonalizationEnabled", False),
            }
            for a in all_audiences[:limit]
        ]

    def get_enhanced_measurement(self, property_id: str, stream_id: str) -> dict:
        """Get enhanced measurement settings for a data stream (v1alpha)."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        stream_name = f"{property_id}/dataStreams/{stream_id}"
        try:
            data = self._get_alpha(f"{stream_name}/enhancedMeasurementSettings")
            return {
                "stream_enabled": data.get("streamEnabled", False),
                "scrolls_enabled": data.get("scrollsEnabled", False),
                "outbound_clicks_enabled": data.get("outboundClicksEnabled", False),
                "site_search_enabled": data.get("siteSearchEnabled", False),
                "video_engagement_enabled": data.get("videoEngagementEnabled", False),
                "file_downloads_enabled": data.get("fileDownloadsEnabled", False),
                "page_changes_enabled": data.get("pageChangesEnabled", False),
                "form_interactions_enabled": data.get("formInteractionsEnabled", False),
                "search_query_parameter": data.get("searchQueryParameter", ""),
            }
        except Exception:
            return {}

    def get_data_retention_settings(self, property_id: str) -> dict:
        """Get data retention settings for a property (v1beta)."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"
        try:
            data = self._get(f"{property_id}/dataRetentionSettings")
            return {
                "event_data_retention": data.get("eventDataRetention", ""),
                "user_data_retention": data.get("userDataRetention", ""),
                "reset_on_new_activity": data.get("resetUserDataOnNewActivity", False),
            }
        except Exception:
            return {}

    # --- Schema Create/Update Methods (for schema deploy) ---

    def create_property(
        self, account_id: str, display_name: str, time_zone: str = "Australia/Brisbane",
        currency: str = "AUD", industry_category: str = "TRAVEL",
    ) -> dict:
        """Create a new GA4 property under an account."""
        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        data = self._post("properties", {
            "parent": account_id,
            "displayName": display_name,
            "timeZone": time_zone,
            "currencyCode": currency,
            "industryCategory": industry_category,
        })
        return {
            "id": data.get("name", "").replace("properties/", ""),
            "name": data.get("displayName", ""),
            "account": data.get("account", ""),
        }

    def create_data_stream(
        self, property_id: str, display_name: str, default_uri: str,
    ) -> dict:
        """Create a web data stream on a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        data = self._post(f"{property_id}/dataStreams", {
            "type": "WEB_DATA_STREAM",
            "displayName": display_name,
            "webStreamData": {"defaultUri": default_uri},
        })
        stream_id = data.get("name", "").split("/")[-1]
        measurement_id = data.get("webStreamData", {}).get("measurementId", "")
        return {
            "stream_id": stream_id,
            "name": data.get("name", ""),
            "display_name": data.get("displayName", ""),
            "measurement_id": measurement_id,
            "default_uri": data.get("webStreamData", {}).get("defaultUri", ""),
        }

    def create_custom_dimension(
        self, property_id: str, parameter_name: str, display_name: str,
        scope: str = "EVENT", description: str = "",
    ) -> dict:
        """Create a custom dimension on a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        data = self._post(f"{property_id}/customDimensions", {
            "parameterName": parameter_name,
            "displayName": display_name,
            "scope": scope,
            "description": description,
        })
        return {
            "name": data.get("name", ""),
            "parameter_name": data.get("parameterName", ""),
            "display_name": data.get("displayName", ""),
            "scope": data.get("scope", ""),
        }

    def create_custom_metric(
        self, property_id: str, parameter_name: str, display_name: str,
        scope: str = "EVENT", measurement_unit: str = "STANDARD",
        description: str = "",
    ) -> dict:
        """Create a custom metric on a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        data = self._post(f"{property_id}/customMetrics", {
            "parameterName": parameter_name,
            "displayName": display_name,
            "scope": scope,
            "measurementUnit": measurement_unit,
            "description": description,
        })
        return {
            "name": data.get("name", ""),
            "parameter_name": data.get("parameterName", ""),
            "display_name": data.get("displayName", ""),
        }

    def create_key_event(
        self, property_id: str, event_name: str,
        counting_method: str = "ONCE_PER_EVENT",
    ) -> dict:
        """Create a key event (conversion) on a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        data = self._post(f"{property_id}/keyEvents", {
            "eventName": event_name,
            "countingMethod": counting_method,
        })
        return {
            "name": data.get("name", ""),
            "event_name": data.get("eventName", ""),
            "counting_method": data.get("countingMethod", ""),
        }

    def update_enhanced_measurement(
        self, property_id: str, stream_id: str, settings: dict,
    ) -> dict:
        """Update enhanced measurement settings for a web data stream (v1alpha)."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        stream_name = f"{property_id}/dataStreams/{stream_id}"
        endpoint = f"{stream_name}/enhancedMeasurementSettings"

        # Map our snake_case keys to API camelCase
        api_body = {}
        field_map = {
            "stream_enabled": "streamEnabled",
            "scrolls_enabled": "scrollsEnabled",
            "outbound_clicks_enabled": "outboundClicksEnabled",
            "site_search_enabled": "siteSearchEnabled",
            "video_engagement_enabled": "videoEngagementEnabled",
            "file_downloads_enabled": "fileDownloadsEnabled",
            "page_changes_enabled": "pageChangesEnabled",
            "form_interactions_enabled": "formInteractionsEnabled",
            "search_query_parameter": "searchQueryParameter",
        }
        update_fields = []
        for our_key, api_key in field_map.items():
            if our_key in settings:
                api_body[api_key] = settings[our_key]
                update_fields.append(api_key)

        data = self._patch_alpha(
            endpoint, api_body,
            params={"updateMask": ",".join(update_fields)},
        )
        return data or {}

    def update_data_retention_settings(
        self, property_id: str, event_retention: str, reset_on_new_activity: bool = True,
    ) -> dict:
        """Update data retention settings for a property."""
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        data = self._patch(
            f"{property_id}/dataRetentionSettings",
            {
                "eventDataRetention": event_retention,
                "resetUserDataOnNewActivity": reset_on_new_activity,
            },
            params={"updateMask": "eventDataRetention,resetUserDataOnNewActivity"},
        )
        return data or {}

    # --- Access Binding (User Management) Methods ---

    def list_access_bindings(self, property_id: str, limit: int = 200) -> list:
        """List users with access to a property.

        Args:
            property_id: Property ID (e.g., "123456789")
            limit: Max results

        Returns:
            List of access binding dicts with user, role info
        """
        # Ensure proper format
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        # Paginate through all access bindings
        all_bindings = []
        page_token = None

        while True:
            params = {"pageSize": min(limit, 200)}
            if page_token:
                params["pageToken"] = page_token

            data = self._get_alpha(f"{property_id}/accessBindings", params)
            all_bindings.extend(data.get("accessBindings", []))

            page_token = data.get("nextPageToken")
            if not page_token or len(all_bindings) >= limit:
                break

        bindings = all_bindings[:limit]

        return [
            {
                "id": b.get("name", "").split("/")[-1],
                "user": b.get("user", ""),
                "roles": [ROLE_DISPLAY.get(r, r) for r in b.get("roles", [])],
                "name": b.get("name", ""),
            }
            for b in bindings
        ]

    def create_access_binding(self, property_id: str, email: str, role: str) -> dict:
        """Add a user to a property with specified role.

        Args:
            property_id: Property ID (e.g., "123456789")
            email: User email address
            role: Role name (viewer, analyst, editor, admin)

        Returns:
            Created access binding dict

        Raises:
            ValueError: If invalid role
            httpx.HTTPStatusError: If API error
        """
        # Validate role
        if role.lower() not in ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of: {', '.join(ROLES.keys())}")

        api_role = ROLES[role.lower()]

        # Ensure proper format
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        data = self._post_alpha(
            f"{property_id}/accessBindings",
            {
                "user": email,
                "roles": [api_role],
            },
        )

        return {
            "id": data.get("name", "").split("/")[-1],
            "user": data.get("user", ""),
            "roles": [ROLE_DISPLAY.get(r, r) for r in data.get("roles", [])],
            "name": data.get("name", ""),
        }

    def delete_access_binding(self, property_id: str, email: str) -> bool:
        """Remove a user's access to a property.

        Args:
            property_id: Property ID
            email: User email to remove

        Returns:
            True if deleted

        Raises:
            ValueError: If user not found
        """
        # Find the binding for this user
        bindings = self.list_access_bindings(property_id)
        binding = next((b for b in bindings if b["user"] == email), None)

        if not binding:
            raise ValueError(f"User not found: {email}")

        return self._delete_alpha(binding["name"])

    def batch_create_access_bindings(
        self, property_id: str, users: list[dict]
    ) -> list[dict]:
        """Add multiple users to a property.

        Args:
            property_id: Property ID
            users: List of dicts with 'email' and 'role' keys

        Returns:
            List of created access bindings
        """
        # Ensure proper format
        if not property_id.startswith("properties/"):
            property_id = f"properties/{property_id}"

        requests = []
        for user in users:
            role = user.get("role", "viewer").lower()
            if role not in ROLES:
                raise ValueError(f"Invalid role: {role}")

            requests.append({
                "accessBinding": {
                    "user": user["email"],
                    "roles": [ROLES[role]],
                }
            })

        data = self._post_alpha(
            f"{property_id}/accessBindings:batchCreate",
            {"requests": requests},
        )

        created = data.get("accessBindings", [])
        return [
            {
                "id": b.get("name", "").split("/")[-1],
                "user": b.get("user", ""),
                "roles": [ROLE_DISPLAY.get(r, r) for r in b.get("roles", [])],
            }
            for b in created
        ]

    # --- Account-Level Access Binding Methods ---

    def create_account_access_binding(self, account_id: str, email: str, role: str) -> dict:
        """Add a user to an account with specified role.

        Account-level access cascades to all properties under the account.

        Args:
            account_id: Account ID (e.g., "123456789")
            email: User email address
            role: Role name (viewer, analyst, editor, admin)

        Returns:
            Created access binding dict
        """
        if role.lower() not in ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of: {', '.join(ROLES.keys())}")

        api_role = ROLES[role.lower()]

        # Ensure proper format
        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        data = self._post_alpha(
            f"{account_id}/accessBindings",
            {
                "user": email,
                "roles": [api_role],
            },
        )

        return {
            "id": data.get("name", "").split("/")[-1],
            "user": data.get("user", ""),
            "roles": [ROLE_DISPLAY.get(r, r) for r in data.get("roles", [])],
            "name": data.get("name", ""),
            "account": account_id,
        }

    def list_account_access_bindings(self, account_id: str) -> list:
        """List users with access to an account.

        Args:
            account_id: Account ID (e.g., "123456789")

        Returns:
            List of access binding dicts
        """
        if not account_id.startswith("accounts/"):
            account_id = f"accounts/{account_id}"

        all_bindings = []
        page_token = None

        while True:
            params = {"pageSize": 200}
            if page_token:
                params["pageToken"] = page_token

            data = self._get_alpha(f"{account_id}/accessBindings", params)
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
