"""ga4 configuration with OAuth2 token storage.

Follows Fabric Protocol credential patterns:
- Environment variables (highest priority)
- OS Keyring (encrypted)
- .env file (fallback)
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import keyring
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Load .env file if it exists
load_dotenv()

# Tool name for keyring namespace
TOOL_NAME = "ga4"

# Environment variable names
ENV_ACCESS_TOKEN = f"{TOOL_NAME.upper()}_ACCESS_TOKEN"
ENV_REFRESH_TOKEN = f"{TOOL_NAME.upper()}_REFRESH_TOKEN"

# OAuth2 scopes for GA4
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.manage.users",
]

# Default credentials path
DEFAULT_CREDENTIALS_PATH = Path(__file__).parent.parent.parent / ".ga4" / "credentials" / "oauth2_credentials.json"


def get_credentials_path() -> Path:
    """Get OAuth2 credentials file path."""
    env_path = os.getenv("GA4_CREDENTIALS_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_CREDENTIALS_PATH


def get_tokens() -> Optional[dict]:
    """Get OAuth2 tokens from storage.

    Priority: environment -> keyring -> None
    """
    # Try environment variables first
    access_token = os.getenv(ENV_ACCESS_TOKEN)
    if access_token:
        return {
            "access_token": access_token,
            "refresh_token": os.getenv(ENV_REFRESH_TOKEN),
            "source": "environment",
        }

    # Try keyring
    try:
        tokens_json = keyring.get_password(f"fabric-{TOOL_NAME}", "__oauth_tokens__")
        if tokens_json:
            tokens = json.loads(tokens_json)
            tokens["source"] = "keyring"
            return tokens
    except Exception:
        pass

    return None


def save_tokens(
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_at: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> None:
    """Save OAuth2 tokens to keyring."""
    tokens = {
        "access_token": access_token,
        "token_type": "Bearer",
    }
    if refresh_token:
        tokens["refresh_token"] = refresh_token
    if expires_at:
        tokens["expires_at"] = expires_at
    if client_id:
        tokens["client_id"] = client_id
    if client_secret:
        tokens["client_secret"] = client_secret

    try:
        keyring.set_password(
            f"fabric-{TOOL_NAME}",
            "__oauth_tokens__",
            json.dumps(tokens, separators=(",", ":")),
        )
    except Exception as e:
        print(f"Warning: Could not save to keyring: {e}")


def clear_credentials() -> None:
    """Clear stored OAuth tokens."""
    try:
        keyring.delete_password(f"fabric-{TOOL_NAME}", "__oauth_tokens__")
    except Exception:
        pass


def is_token_expired(buffer_seconds: int = 60) -> bool:
    """Check if access token is expired or about to expire."""
    tokens = get_tokens()
    if not tokens:
        return True

    expires_at = tokens.get("expires_at")
    if not expires_at:
        return False  # No expiry info - assume valid

    try:
        if isinstance(expires_at, str):
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        else:
            expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc)

        now = datetime.now(timezone.utc)
        return (expiry - now).total_seconds() < buffer_seconds
    except Exception:
        return True


def get_auth_source() -> str:
    """Get where OAuth tokens are stored.

    Returns:
        'environment', 'keyring', or 'none'
    """
    tokens = get_tokens()
    if not tokens:
        return "none"
    return tokens.get("source", "unknown")


def get_auth_status() -> dict:
    """Get authentication status for CLI display."""
    tokens = get_tokens()
    source = get_auth_source()

    if not tokens or not tokens.get("access_token"):
        return {
            "authenticated": False,
            "source": source,
            "reason": "No tokens stored",
        }

    return {
        "authenticated": True,
        "source": source,
        "expires_at": tokens.get("expires_at"),
        "expired": is_token_expired(),
        "has_refresh_token": bool(tokens.get("refresh_token")),
    }


def get_google_credentials() -> Optional[Credentials]:
    """Get Google OAuth2 Credentials object for API calls.

    Returns:
        Credentials object or None if not authenticated
    """
    tokens = get_tokens()
    if not tokens or not tokens.get("access_token"):
        return None

    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=tokens.get("client_id"),
        client_secret=tokens.get("client_secret"),
        scopes=SCOPES,
    )

    return creds


def refresh_credentials() -> Optional[Credentials]:
    """Refresh expired credentials.

    Returns:
        Refreshed Credentials object or None if refresh failed
    """
    from google.auth.transport.requests import Request

    tokens = get_tokens()
    if not tokens:
        return None

    creds = get_google_credentials()
    if not creds or not creds.refresh_token:
        return None

    try:
        creds.refresh(Request())

        # Save refreshed tokens
        save_tokens(
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            expires_at=creds.expiry.isoformat() if creds.expiry else None,
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
        )

        return creds
    except Exception:
        return None


def run_oauth_flow(port: int = 8080) -> Credentials:
    """Run OAuth2 flow using local server.

    Args:
        port: Port for local callback server

    Returns:
        Credentials object

    Raises:
        FileNotFoundError: If credentials file not found
    """
    creds_path = get_credentials_path()
    if not creds_path.exists():
        raise FileNotFoundError(
            f"OAuth2 credentials file not found: {creds_path}\n"
            "Download from Google Cloud Console and place at this path."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(creds_path),
        scopes=SCOPES,
    )

    creds = flow.run_local_server(
        port=port,
        access_type="offline",
        prompt="consent",
    )

    # Read client credentials from file
    with open(creds_path) as f:
        client_config = json.load(f)
        installed = client_config.get("installed", {})
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret")

    # Save tokens
    save_tokens(
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        expires_at=creds.expiry.isoformat() if creds.expiry else None,
        client_id=client_id,
        client_secret=client_secret,
    )

    return creds
