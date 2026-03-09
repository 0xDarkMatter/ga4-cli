"""Shared error types for GA4 CLI."""


class RateLimitError(Exception):
    """Raised when GA4 API returns 429 Too Many Requests."""

    def __init__(self, message: str = "Rate limited by Google Analytics API"):
        super().__init__(message)
