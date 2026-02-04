"""Google Analytics Admin API client.

Handles property and user management via analyticsadmin.googleapis.com.
"""

from typing import Optional

import httpx

from .config import get_tokens, get_google_credentials, refresh_credentials, is_token_expired


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

    def __init__(self):
        self._ensure_valid_token()
        tokens = get_tokens()
        self.token = tokens.get("access_token") if tokens else None

    def _ensure_valid_token(self) -> None:
        """Refresh token if expired."""
        if is_token_expired():
            refresh_credentials()

    def _headers(self) -> dict:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make GET request."""
        response = httpx.get(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            params=params,
            timeout=self.TIMEOUT,
        )
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
        response.raise_for_status()
        return response.json()

    def _delete(self, endpoint: str) -> bool:
        """Make DELETE request."""
        response = httpx.delete(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            timeout=self.TIMEOUT,
        )
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
        response.raise_for_status()
        return response.json()

    def _delete_alpha(self, endpoint: str) -> bool:
        """Make DELETE request to alpha API."""
        response = httpx.delete(
            f"{self.BASE_URL_ALPHA}/{endpoint}",
            headers=self._headers(),
            timeout=self.TIMEOUT,
        )
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
