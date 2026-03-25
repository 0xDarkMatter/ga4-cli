"""ga4 configuration with OAuth2 token storage.

Follows Fabric Protocol credential patterns:
- Environment variables (highest priority, override all profiles)
- OS Keyring (encrypted, per-profile)
- .env file (fallback)

Multi-profile support:
- Default profile uses keyring entry '__oauth_tokens__' (backward compatible)
- Named profiles use '__oauth_tokens__{profile}__'
- Profile manifest stored at {config_dir}/profiles.json
- GA4_PROFILE env var sets the active profile
"""

import json
import os
from datetime import datetime, timezone
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

# Default profile name
DEFAULT_PROFILE = "default"

# Environment variable names
ENV_ACCESS_TOKEN = f"{TOOL_NAME.upper()}_ACCESS_TOKEN"
ENV_REFRESH_TOKEN = f"{TOOL_NAME.upper()}_REFRESH_TOKEN"

# OAuth2 scopes for GA4
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.edit",
    "https://www.googleapis.com/auth/analytics.manage.users",
]

# Default credentials path
DEFAULT_CREDENTIALS_PATH = Path(__file__).parent.parent.parent / ".ga4" / "credentials" / "oauth2_credentials.json"

# Config directory for the profiles manifest
_CONFIG_DIR = DEFAULT_CREDENTIALS_PATH.parent


def get_credentials_path() -> Path:
    """Get OAuth2 credentials file path."""
    env_path = os.getenv("GA4_CREDENTIALS_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_CREDENTIALS_PATH


# ---------------------------------------------------------------------------
# Keyring entry naming
# ---------------------------------------------------------------------------

def _keyring_entry(profile: str = DEFAULT_PROFILE) -> str:
    """Return the keyring entry name for a profile.

    The default profile uses the legacy entry name for backward compatibility.
    """
    if profile == DEFAULT_PROFILE:
        return "__oauth_tokens__"
    return f"__oauth_tokens__{profile}__"


# ---------------------------------------------------------------------------
# Profiles manifest (needed because keyring has no list-entries API)
# ---------------------------------------------------------------------------

def _profiles_manifest_path() -> Path:
    """Return the path to the profiles manifest JSON file."""
    return _CONFIG_DIR / "profiles.json"


def _load_manifest() -> list[str]:
    """Load profile names from the manifest. Returns list of profile names."""
    path = _profiles_manifest_path()
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return data.get("profiles", [])
    except Exception:
        pass
    return []


def _save_manifest(profiles: list[str]) -> None:
    """Persist profile names to the manifest."""
    path = _profiles_manifest_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"profiles": profiles}, indent=2))
    except Exception:
        pass


def _register_profile(profile: str) -> None:
    """Add profile to the manifest if not already present."""
    profiles = _load_manifest()
    if profile not in profiles:
        profiles.append(profile)
        _save_manifest(profiles)


def _unregister_profile(profile: str) -> None:
    """Remove profile from manifest."""
    profiles = _load_manifest()
    if profile in profiles:
        profiles.remove(profile)
        _save_manifest(profiles)


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

def get_tokens(profile: str = DEFAULT_PROFILE) -> Optional[dict]:
    """Get OAuth2 tokens from storage.

    Priority: environment variables (override all profiles) -> keyring -> None

    Args:
        profile: Profile name. Ignored when env vars are set.

    Returns:
        Token dict with at minimum 'access_token', or None.
    """
    # Environment variables override every profile
    access_token = os.getenv(ENV_ACCESS_TOKEN)
    if access_token:
        return {
            "access_token": access_token,
            "refresh_token": os.getenv(ENV_REFRESH_TOKEN),
            "source": "environment",
        }

    # Try keyring for the requested profile
    try:
        tokens_json = keyring.get_password(f"clique-{TOOL_NAME}", _keyring_entry(profile))
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
    profile: str = DEFAULT_PROFILE,
) -> None:
    """Save OAuth2 tokens to keyring for a profile.

    Args:
        access_token: OAuth2 access token.
        refresh_token: OAuth2 refresh token.
        expires_at: ISO 8601 expiry timestamp.
        client_id: OAuth2 client ID.
        client_secret: OAuth2 client secret.
        profile: Profile to save tokens under.
    """
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
            f"clique-{TOOL_NAME}",
            _keyring_entry(profile),
            json.dumps(tokens, separators=(",", ":")),
        )
        _register_profile(profile)
    except Exception as e:
        print(f"Warning: Could not save to keyring: {e}")


def clear_credentials(profile: str = DEFAULT_PROFILE) -> None:
    """Clear stored OAuth tokens for a profile.

    Args:
        profile: Profile name to clear, or '*' to clear all known profiles.
    """
    if profile == "*":
        # Clear all profiles in the manifest plus the default
        all_profiles = list(set(_load_manifest() + [DEFAULT_PROFILE]))
        for p in all_profiles:
            _clear_one_profile(p)
        # Wipe the manifest
        _save_manifest([])
    else:
        _clear_one_profile(profile)
        _unregister_profile(profile)


def _clear_one_profile(profile: str) -> None:
    """Delete the keyring entry for a single profile."""
    try:
        keyring.delete_password(f"clique-{TOOL_NAME}", _keyring_entry(profile))
    except Exception:
        pass


def list_profiles() -> list[dict]:
    """List all known profiles and their auth status.

    Profiles are discovered from the manifest file. The default profile is
    always included even if absent from the manifest.

    Returns:
        List of dicts with 'profile', 'authenticated', 'expired' keys.
    """
    manifest_profiles = _load_manifest()

    # Always include default; deduplicate
    all_profiles: list[str] = []
    seen: set[str] = set()
    for p in [DEFAULT_PROFILE] + manifest_profiles:
        if p not in seen:
            all_profiles.append(p)
            seen.add(p)

    result = []
    for p in all_profiles:
        tokens = get_tokens(p)
        if tokens and tokens.get("source") == "environment":
            # env override - report as env-sourced for all profiles
            result.append({
                "profile": p,
                "authenticated": True,
                "source": "environment",
                "expired": False,
                "active": False,
            })
        elif tokens and tokens.get("access_token"):
            result.append({
                "profile": p,
                "authenticated": True,
                "source": "keyring",
                "expired": is_token_expired(profile=p),
                "expires_at": tokens.get("expires_at"),
                "active": False,
            })
        else:
            result.append({
                "profile": p,
                "authenticated": False,
                "source": "none",
                "expired": None,
                "active": False,
            })
    return result


# ---------------------------------------------------------------------------
# Token state queries
# ---------------------------------------------------------------------------

def is_token_expired(buffer_seconds: int = 60, profile: str = DEFAULT_PROFILE) -> bool:
    """Check if access token for a profile is expired or about to expire.

    Args:
        buffer_seconds: Consider expired if expiry is within this many seconds.
        profile: Profile to check.

    Returns:
        True if expired or no expiry info is available for a token from env.
    """
    tokens = get_tokens(profile)
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


def get_auth_source(profile: str = DEFAULT_PROFILE) -> str:
    """Get where OAuth tokens are stored for a profile.

    Returns:
        'environment', 'keyring', or 'none'
    """
    tokens = get_tokens(profile)
    if not tokens:
        return "none"
    return tokens.get("source", "unknown")


def get_auth_status(profile: str = DEFAULT_PROFILE) -> dict:
    """Get authentication status for CLI display.

    Args:
        profile: Profile to check.

    Returns:
        Status dict with 'authenticated', 'source', 'expires_at', etc.
    """
    tokens = get_tokens(profile)
    source = get_auth_source(profile)

    if not tokens or not tokens.get("access_token"):
        return {
            "authenticated": False,
            "profile": profile,
            "source": source,
            "reason": "No tokens stored",
        }

    return {
        "authenticated": True,
        "profile": profile,
        "source": source,
        "expires_at": tokens.get("expires_at"),
        "expired": is_token_expired(profile=profile),
        "has_refresh_token": bool(tokens.get("refresh_token")),
    }


# ---------------------------------------------------------------------------
# Google Credentials objects
# ---------------------------------------------------------------------------

def get_google_credentials(profile: str = DEFAULT_PROFILE) -> Optional[Credentials]:
    """Get Google OAuth2 Credentials object for API calls.

    Args:
        profile: Profile to use.

    Returns:
        Credentials object or None if not authenticated.
    """
    tokens = get_tokens(profile)
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


def refresh_credentials(profile: str = DEFAULT_PROFILE) -> Optional[Credentials]:
    """Refresh expired credentials for a profile.

    Args:
        profile: Profile whose tokens to refresh.

    Returns:
        Refreshed Credentials object or None if refresh failed.
    """
    from google.auth.transport.requests import Request

    tokens = get_tokens(profile)
    if not tokens:
        return None

    creds = get_google_credentials(profile)
    if not creds or not creds.refresh_token:
        return None

    try:
        creds.refresh(Request())

        # Save refreshed tokens back to the same profile
        save_tokens(
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            expires_at=creds.expiry.isoformat() if creds.expiry else None,
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            profile=profile,
        )

        return creds
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def run_oauth_flow(port: int = 8080, profile: str = DEFAULT_PROFILE) -> Credentials:
    """Run OAuth2 flow using local server and save tokens for a profile.

    The OAuth client secrets file is shared across all profiles (same OAuth app).

    Args:
        port: Port for local callback server.
        profile: Profile to save credentials under.

    Returns:
        Credentials object.

    Raises:
        FileNotFoundError: If credentials file not found.
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

    # Save tokens to the requested profile
    save_tokens(
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        expires_at=creds.expiry.isoformat() if creds.expiry else None,
        client_id=client_id,
        client_secret=client_secret,
        profile=profile,
    )

    return creds
