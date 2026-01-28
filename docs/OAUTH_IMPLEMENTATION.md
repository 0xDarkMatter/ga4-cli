# OAuth2 Implementation Guide for GA4 CLI

Based on Gwark's proven OAuth2 implementation for Google APIs.

## Overview

Google Analytics 4 API requires OAuth2 authentication. We'll implement the same pattern as Gwark, which uses:
- `google-auth-oauthlib` for OAuth flow
- `google-auth` for credential management
- Local server callback for authorization
- Encrypted token storage

## 1. Update Dependencies

```toml
# pyproject.toml
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    "httpx>=0.25.0",
    "keyring>=24.0.0",
    "python-dotenv>=1.0.0",
    # Add Google Auth libraries
    "google-auth>=2.23.0",
    "google-auth-oauthlib>=1.1.0",
    "google-api-python-client>=2.108.0",
]
```

## 2. Get OAuth2 Credentials from Google Cloud

### Steps:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable **Google Analytics Data API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Analytics Data API"
   - Click "Enable"
4. Create OAuth2 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Application type: "Desktop app"
   - Name: "GA4 CLI"
   - Download JSON file
5. Save JSON file as: `X:\Fabric\GA4\.ga4\credentials\oauth2_credentials.json`

### Required Scopes:
```python
SCOPES = [
    'https://www.googleapis.com/auth/analytics.readonly',
]
```

## 3. Implement OAuth2 Manager

Create `src/ga4/auth.py`:

```python
"""OAuth2 authentication for Google Analytics API."""

import json
import sys
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# OAuth2 scopes
SCOPES = [
    'https://www.googleapis.com/auth/analytics.readonly',
]

# File paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
TOKEN_DIR = PROJECT_ROOT / '.ga4' / 'tokens'
CREDS_PATH = PROJECT_ROOT / '.ga4' / 'credentials' / 'oauth2_credentials.json'


def _ensure_directories():
    """Create directories if they don't exist."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_analytics_service():
    """Get authenticated Google Analytics Data API service.

    Returns:
        Authenticated Analytics Data API service

    Raises:
        SystemExit: If credentials file not found or auth fails
    """
    _ensure_directories()

    creds: Optional[Credentials] = None
    token_path = TOKEN_DIR / 'analytics_token.json'

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing access token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
                print("Re-authenticating...")
                creds = None

        if not creds:
            if not CREDS_PATH.exists():
                print(f"\n[ERROR] OAuth2 credentials not found at {CREDS_PATH}")
                print("\nTo set up authentication:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Enable Google Analytics Data API")
                print("3. Create OAuth2 Desktop credentials")
                print("4. Download JSON and save to .ga4/credentials/oauth2_credentials.json")
                sys.exit(2)  # EXIT_AUTH_REQUIRED

            print("Starting OAuth2 authentication flow...")
            print("Your browser will open for Google sign-in.")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS_PATH),
                SCOPES
            )

            creds = flow.run_local_server(
                port=8080,
                access_type='offline',
                prompt='consent',
            )

        # Save credentials for future use
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        print("Credentials saved successfully!")

    # Build and return service
    service = build('analyticsdata', 'v1beta', credentials=creds)
    return service


def get_admin_service():
    """Get authenticated Google Analytics Admin API service.

    For managing properties and accounts.

    Returns:
        Authenticated Analytics Admin API service
    """
    _ensure_directories()

    creds: Optional[Credentials] = None
    token_path = TOKEN_DIR / 'admin_token.json'

    # Admin scopes
    admin_scopes = [
        'https://www.googleapis.com/auth/analytics.readonly',
        'https://www.googleapis.com/auth/analytics.edit',
    ]

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), admin_scopes)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing access token...")
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                print(f"[ERROR] OAuth2 credentials not found at {CREDS_PATH}")
                sys.exit(2)

            print("Starting OAuth2 authentication flow...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS_PATH),
                admin_scopes
            )
            creds = flow.run_local_server(port=8080)

        # Save credentials
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    service = build('analyticsadmin', 'v1beta', credentials=creds)
    return service


def check_auth_status() -> dict:
    """Check if user is authenticated.

    Returns:
        Dict with auth status info
    """
    _ensure_directories()
    token_path = TOKEN_DIR / 'analytics_token.json'

    if not token_path.exists():
        return {
            "authenticated": False,
            "source": "none",
            "reason": "No tokens stored",
        }

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        return {
            "authenticated": True,
            "source": "file",
            "valid": creds.valid,
            "expired": creds.expired,
            "has_refresh_token": bool(creds.refresh_token),
        }
    except Exception:
        return {
            "authenticated": False,
            "source": "file",
            "reason": "Invalid token file",
        }


def clear_credentials():
    """Clear stored credentials."""
    _ensure_directories()
    token_path = TOKEN_DIR / 'analytics_token.json'

    if token_path.exists():
        token_path.unlink()
        return True
    return False
```

## 4. Update CLI Commands

Update `src/ga4/cli.py`:

```python
# At top, replace config imports
from .auth import get_analytics_service, check_auth_status, clear_credentials

# Update auth_login command
@auth_app.command("login")
def auth_login():
    """
    Authenticate with Google Analytics.

    Opens browser for OAuth2 flow. Credentials are saved for future use.

    Examples:
        ga4 auth login
    """
    try:
        console.print("[cyan]Starting authentication...[/cyan]")
        service = get_analytics_service()  # This will trigger OAuth flow
        console.print("[green]✓ Successfully authenticated![/green]")
    except SystemExit:
        # Auth error already printed
        raise
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        raise typer.Exit(EXIT_ERROR)


# Update auth_status command
@auth_app.command("status")
def auth_status_cmd(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """
    Check authentication status.

    Examples:
        ga4 auth status
        ga4 auth status --json
    """
    status = check_auth_status()

    if json_output:
        _output_json({"data": status})
        return

    if status.get("authenticated"):
        console.print("Authenticated: [green]yes[/green]")
        console.print(f"Source: [cyan]{status.get('source')}[/cyan]")

        if status.get("expired"):
            console.print("[yellow]Token expired - will auto-refresh on next use[/yellow]")
        elif not status.get("valid"):
            console.print("[yellow]Token invalid - run 'ga4 auth login'[/yellow]")
    else:
        console.print("Authenticated: [red]no[/red]")
        console.print("Run: [cyan]ga4 auth login[/cyan]")


# Update auth_logout command
@auth_app.command("logout")
def auth_logout():
    """
    Clear stored credentials.

    Examples:
        ga4 auth logout
    """
    if clear_credentials():
        console.print("[green]Logged out successfully[/green]")
    else:
        console.print("[yellow]No credentials to clear[/yellow]")


# Update _require_auth helper
def _require_auth(as_json: bool = False):
    """Check authentication, exit if not authenticated."""
    status = check_auth_status()

    if not status.get("authenticated"):
        _error(
            "Not authenticated. Run: ga4 auth login",
            "AUTH_REQUIRED",
            EXIT_AUTH_REQUIRED,
            as_json=as_json,
        )
```

## 5. Implement Real API Calls

Update `src/ga4/client.py`:

```python
"""GA4 API client."""

from typing import Optional
from .auth import get_analytics_service, get_admin_service


class Client:
    """API client for Google Analytics 4."""

    def __init__(self):
        self.analytics_service = None
        self.admin_service = None

    def _get_analytics_service(self):
        """Get or create Analytics Data API service."""
        if not self.analytics_service:
            self.analytics_service = get_analytics_service()
        return self.analytics_service

    def _get_admin_service(self):
        """Get or create Analytics Admin API service."""
        if not self.admin_service:
            self.admin_service = get_admin_service()
        return self.admin_service

    def list_properties(self, limit: int = 20) -> list:
        """List GA4 properties."""
        service = self._get_admin_service()

        # List all accounts
        accounts = service.accountSummaries().list().execute()

        properties = []
        for account in accounts.get('accountSummaries', [])[:limit]:
            for prop_summary in account.get('propertySummaries', []):
                properties.append({
                    'id': prop_summary['property'],
                    'name': prop_summary['displayName'],
                    'account': account.get('displayName', ''),
                })

        return properties[:limit]

    def run_report(
        self,
        property_id: str,
        dimensions: list,
        metrics: list,
        date_from: str,
        date_to: str,
    ) -> dict:
        """Run a report on a property.

        Args:
            property_id: GA4 property ID (e.g., "properties/123456")
            dimensions: List of dimension names (e.g., ["city", "date"])
            metrics: List of metric names (e.g., ["activeUsers"])
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
        """
        service = self._get_analytics_service()

        request = {
            'dimensions': [{'name': d} for d in dimensions],
            'metrics': [{'name': m} for m in metrics],
            'dateRanges': [{
                'startDate': date_from,
                'endDate': date_to,
            }],
        }

        response = service.properties().runReport(
            property=property_id,
            body=request
        ).execute()

        return response
```

## 6. Testing

```bash
# Install updated dependencies
cd X:\Fabric\GA4
uv pip install -e .

# Test auth flow
ga4 auth login
# Browser opens, sign in with Google account that has GA4 access

# Check status
ga4 auth status
ga4 auth status --json

# Test API calls
ga4 properties list --json

# Logout
ga4 auth logout
```

## 7. Credential Storage

Tokens are stored at:
```
X:\Fabric\GA4\.ga4\tokens\analytics_token.json
```

This file contains:
- Access token (short-lived)
- Refresh token (long-lived)
- Token expiry
- Scopes

**Security:**
- Tokens are stored in JSON format (not encrypted by default)
- File permissions should be restricted
- Never commit `.ga4/` directory to git

## 8. Error Handling

| Scenario | Exit Code | Handling |
|----------|-----------|----------|
| No credentials file | 2 (AUTH_REQUIRED) | Print setup instructions |
| Token expired | Auto-refresh | Silent refresh using refresh_token |
| Invalid token | 2 (AUTH_REQUIRED) | Prompt re-authentication |
| Network error | 1 (ERROR) | Display error message |

## 9. Environment Variable Override

For CI/CD or testing, support service account credentials:

```python
# In auth.py, add at top of get_analytics_service():
if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
    # Use service account
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
        scopes=SCOPES
    )
    return build('analyticsdata', 'v1beta', credentials=creds)
```

## 10. Next Steps

1. ✅ Add `google-auth-oauthlib` to dependencies
2. ✅ Create `src/ga4/auth.py` with OAuth2 flow
3. ✅ Update CLI auth commands to use new auth module
4. ✅ Implement real API calls in `client.py`
5. ⬜ Add `reports run` command for custom reports
6. ⬜ Add dimension/metric metadata commands
7. ⬜ Test with real GA4 property
8. ⬜ Update documentation

## References

- [Google Analytics Data API](https://developers.google.com/analytics/devguides/reporting/data/v1)
- [OAuth2 for Installed Apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Google Auth Python](https://google-auth.readthedocs.io/)
- [Gwark Implementation](X:\Fabric\Gwark\src\gmail_mcp\auth\oauth.py)
