"""ga4 configuration with OAuth2 token storage.

Credentials priority: env vars -> keyring -> .env file
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import keyring
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Tool name for keyring namespace
TOOL_NAME = "ga4"

# Environment variable names
ENV_ACCESS_TOKEN = f"{TOOL_NAME.upper()}_ACCESS_TOKEN"
ENV_REFRESH_TOKEN = f"{TOOL_NAME.upper()}_REFRESH_TOKEN"


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
        tokens_json = keyring.get_password(TOOL_NAME, "oauth_tokens")
        if tokens_json:
            tokens = json.loads(tokens_json)
            tokens["source"] = "keyring"
            return tokens
    except Exception:
        pass

    return None


def save_tokens(tokens: dict) -> None:
    """Save OAuth2 tokens to keyring.

    Args:
        tokens: Dict with access_token, refresh_token, expires_at, etc.
    """
    # Store in keyring
    try:
        tokens_copy = {
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": tokens.get("expires_at"),
            "token_type": tokens.get("token_type", "Bearer"),
            "scope": tokens.get("scope"),
        }

        # Convert expires_in to expires_at if present
        if "expires_in" in tokens and not tokens_copy.get("expires_at"):
            expires_in = int(tokens["expires_in"])
            expires_at = datetime.now(timezone.utc).timestamp() + expires_in
            tokens_copy["expires_at"] = datetime.fromtimestamp(
                expires_at, tz=timezone.utc
            ).isoformat()

        keyring.set_password(TOOL_NAME, "oauth_tokens", json.dumps(tokens_copy))
    except Exception as e:
        # Keyring might not be available
        print(f"Warning: Could not save to keyring: {e}")


def clear_credentials() -> None:
    """Clear stored OAuth tokens."""
    try:
        keyring.delete_password(TOOL_NAME, "oauth_tokens")
    except Exception:
        pass


def is_token_expired(buffer_seconds: int = 60) -> bool:
    """Check if access token is expired or about to expire."""
    tokens = get_tokens()
    if not tokens or not tokens.get("expires_at"):
        return True

    try:
        expires_at_str = tokens["expires_at"]
        if isinstance(expires_at_str, str):
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        else:
            expires_at = datetime.fromtimestamp(expires_at_str, tz=timezone.utc)

        now = datetime.now(timezone.utc)
        return (expires_at - now).total_seconds() < buffer_seconds
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
