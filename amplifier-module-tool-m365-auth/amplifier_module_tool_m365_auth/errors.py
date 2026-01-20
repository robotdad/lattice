"""Exception classes for M365 authentication module.

All exceptions are designed to be safe to display to users and agents,
with no credential or token information leaked in error messages.
"""

from __future__ import annotations


class M365AuthError(Exception):
    """Base exception for M365 authentication errors."""

    pass


class AuthenticationError(M365AuthError):
    """Authentication failed.

    This exception is raised when:
    - Device code flow fails to complete
    - Token refresh fails
    - MSAL returns an error response

    The message is safe to display to users.
    """

    def __init__(self, message: str, error_code: str | None = None):
        self.error_code = error_code
        super().__init__(message)


class AuthenticationCancelledError(M365AuthError):
    """User cancelled the authentication flow.

    Raised when:
    - User explicitly cancels device code flow
    - Device code expires before user completes authentication
    """

    pass


class AuthenticationTimeoutError(M365AuthError):
    """Authentication timed out waiting for user.

    Raised when the device code flow times out waiting for the user
    to complete authentication in their browser.
    """

    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Authentication timed out after {timeout_seconds} seconds. "
            "Please try again and complete authentication in your browser."
        )


class ConfigurationError(M365AuthError):
    """Configuration is invalid or missing.

    Raised when:
    - Required configuration (like client_id) is missing
    - Configuration values are invalid
    """

    pass


class TokenCacheError(M365AuthError):
    """Token cache operation failed.

    Raised when:
    - Cache file cannot be read or written
    - Cache file permissions cannot be set
    - Cache data is corrupted
    """

    pass


class NotAuthenticatedError(M365AuthError):
    """No authenticated session exists.

    Raised when an operation requires authentication but no valid
    token or account is available in the cache.
    """

    def __init__(self, message: str | None = None):
        super().__init__(
            message or "Not authenticated. Use 'login' operation to authenticate with M365."
        )
