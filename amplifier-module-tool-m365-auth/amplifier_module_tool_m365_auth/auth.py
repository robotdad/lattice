"""M365 authentication provider using MSAL.

This module implements the M365AuthProvider class which wraps Microsoft
Authentication Library (MSAL) for OAuth2 device code flow authentication.

The device code flow is ideal for CLI and agent scenarios where:
- No browser is available on the host machine
- User interaction happens on a separate device
- No client secrets are needed (public client)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import msal

from .cache import TokenCache
from .config import AuthConfig
from .errors import (
    AuthenticationCancelledError,
    AuthenticationError,
    AuthenticationTimeoutError,
    NotAuthenticatedError,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class TokenResult:
    """Result of token acquisition.

    Attributes:
        access_token: The OAuth2 access token for API calls.
        expires_on: Unix timestamp when the token expires.
        scopes: List of scopes granted for this token.
        account_id: Unique identifier for the authenticated account.
    """

    access_token: str
    expires_on: int
    scopes: list[str]
    account_id: str | None = None


@dataclass
class DeviceCodeInfo:
    """Information for device code flow.

    Attributes:
        user_code: The code the user must enter at the verification URL.
        verification_uri: The URL where the user should authenticate.
        message: Human-readable instruction message.
        expires_in: Seconds until the device code expires.
    """

    user_code: str
    verification_uri: str
    message: str
    expires_in: int


class M365AuthProvider:
    """MSAL-based M365 authentication provider.

    This class provides OAuth2 device code flow authentication for
    Microsoft 365 services. It handles:
    - Device code flow initiation and completion
    - Token caching with automatic refresh
    - Multi-account management
    - Secure token persistence

    Example:
        ```python
        config = AuthConfig(client_id="your-client-id")
        provider = M365AuthProvider(config)

        # Get a token (will prompt for device code if needed)
        token = await provider.get_token()
        print(f"Access token: {token.access_token}")
        ```
    """

    def __init__(self, config: AuthConfig):
        """Initialize the authentication provider.

        Args:
            config: Authentication configuration.
        """
        self.config = config
        self._cache = TokenCache(config.cache_path)
        self._app: msal.PublicClientApplication | None = None
        self._pending_flow: dict[str, Any] | None = None
        self._device_code_callback: Callable[[DeviceCodeInfo], None] | None = None

    @property
    def app(self) -> msal.PublicClientApplication:
        """Get or create the MSAL PublicClientApplication.

        The application is lazily initialized on first access.

        Returns:
            MSAL PublicClientApplication instance.
        """
        if self._app is None:
            self._app = msal.PublicClientApplication(
                client_id=self.config.client_id,
                authority=self.config.authority,
                token_cache=self._cache.msal_cache,
            )
        return self._app

    def set_device_code_callback(self, callback: Callable[[DeviceCodeInfo], None] | None) -> None:
        """Set a callback for device code flow notifications.

        The callback is invoked when device code flow is initiated,
        allowing custom handling of user prompts.

        Args:
            callback: Function to call with DeviceCodeInfo, or None to clear.
        """
        self._device_code_callback = callback

    async def get_token(self, scopes: list[str] | None = None) -> TokenResult:
        """Get a valid access token, refreshing if needed.

        This method attempts to acquire a token in the following order:
        1. Return a valid cached token if available
        2. Silently refresh using a refresh token if available
        3. Initiate device code flow if no valid token exists

        Args:
            scopes: OAuth2 scopes to request. Defaults to configured scopes.

        Returns:
            TokenResult with a valid access token.

        Raises:
            AuthenticationError: If authentication fails.
            AuthenticationCancelledError: If user cancels the flow.
        """
        scopes = scopes or self.config.scopes

        # Try silent acquisition first (cached or refresh token)
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(scopes, account=accounts[0])
            if result and "access_token" in result:
                self._cache.save()
                return self._to_token_result(result)

        # Need interactive auth - use device code flow
        device_info = await self.initiate_device_code(scopes)

        # Notify callback if set
        if self._device_code_callback:
            self._device_code_callback(device_info)

        # Complete the flow
        return await self.complete_device_code()

    async def get_token_silent(self, scopes: list[str] | None = None) -> TokenResult:
        """Get a token only from cache, without user interaction.

        Use this method when you want to check if a valid session exists
        without potentially triggering a login flow.

        Args:
            scopes: OAuth2 scopes to request. Defaults to configured scopes.

        Returns:
            TokenResult with a valid access token.

        Raises:
            NotAuthenticatedError: If no valid cached token exists.
        """
        scopes = scopes or self.config.scopes

        accounts = self.app.get_accounts()
        if not accounts:
            raise NotAuthenticatedError()

        result = self.app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            self._cache.save()
            return self._to_token_result(result)

        raise NotAuthenticatedError("Cached token expired and refresh failed.")

    async def initiate_device_code(self, scopes: list[str] | None = None) -> DeviceCodeInfo:
        """Start device code flow without blocking.

        This method initiates the device code flow and returns immediately
        with the information needed for the user to authenticate. Call
        complete_device_code() after the user has authenticated.

        Args:
            scopes: OAuth2 scopes to request. Defaults to configured scopes.

        Returns:
            DeviceCodeInfo with code and instructions for the user.

        Raises:
            AuthenticationError: If device flow cannot be initiated.
        """
        scopes = scopes or self.config.scopes

        flow = self.app.initiate_device_flow(scopes=scopes)

        if "user_code" not in flow:
            error_desc = flow.get("error_description", "Unknown error")
            raise AuthenticationError(
                f"Failed to initiate device code flow: {error_desc}",
                error_code=flow.get("error"),
            )

        self._pending_flow = flow

        return DeviceCodeInfo(
            user_code=flow["user_code"],
            verification_uri=flow["verification_uri"],
            message=flow["message"],
            expires_in=flow.get("expires_in", 900),
        )

    async def complete_device_code(self, timeout: float = 300) -> TokenResult:
        """Wait for device code flow completion.

        This method polls Azure AD waiting for the user to complete
        authentication in their browser.

        Args:
            timeout: Maximum seconds to wait for completion.

        Returns:
            TokenResult with the acquired access token.

        Raises:
            AuthenticationError: If no pending flow or authentication fails.
            AuthenticationTimeoutError: If user doesn't complete in time.
            AuthenticationCancelledError: If user cancels or code expires.
        """
        if not self._pending_flow:
            raise AuthenticationError(
                "No pending device code flow. Call initiate_device_code() first."
            )

        flow = self._pending_flow
        self._pending_flow = None

        # Check if the flow has already expired
        expires_at = flow.get("expires_at", time.time() + 900)
        if time.time() > expires_at:
            raise AuthenticationCancelledError(
                "Device code has expired. Please initiate a new login."
            )

        # MSAL's acquire_token_by_device_flow handles polling internally
        # We can pass exit_condition to implement timeout
        start_time = time.time()

        def check_timeout(flow_dict: dict[str, Any]) -> bool:
            """Return True to abort the flow."""
            return time.time() - start_time > timeout

        result = self.app.acquire_token_by_device_flow(
            flow,
            exit_condition=check_timeout,
        )

        # Check for timeout
        if time.time() - start_time > timeout:
            raise AuthenticationTimeoutError(timeout)

        # Check for errors
        if "access_token" not in result:
            error = result.get("error", "unknown")
            error_desc = result.get("error_description", "Authentication failed")

            if error == "authorization_pending":
                raise AuthenticationTimeoutError(timeout)
            elif error in ("authorization_declined", "expired_token"):
                raise AuthenticationCancelledError(error_desc)
            else:
                raise AuthenticationError(error_desc, error_code=error)

        # Success - save cache and return result
        self._cache.save()
        return self._to_token_result(result)

    async def logout(self, account_id: str | None = None) -> bool:
        """Remove cached tokens for an account.

        Args:
            account_id: Specific account ID to remove, or None to remove all.

        Returns:
            True if any accounts were removed.
        """
        accounts = self.app.get_accounts()
        removed = False

        for account in accounts:
            if account_id is None or account.get("local_account_id") == account_id:
                self.app.remove_account(account)
                removed = True

        if removed:
            self._cache.save()

        return removed

    def get_accounts(self) -> list[dict[str, Any]]:
        """List cached accounts.

        Returns:
            List of account information dictionaries with keys:
            - username: The user's email or UPN
            - account_id: Unique identifier for the account
            - tenant_id: The Azure AD tenant ID
        """
        return [
            {
                "username": acc.get("username", ""),
                "account_id": acc.get("local_account_id", ""),
                "tenant_id": acc.get("realm", ""),
            }
            for acc in self.app.get_accounts()
        ]

    def is_authenticated(self) -> bool:
        """Check if there's an authenticated session.

        Returns:
            True if there are cached accounts with potential valid tokens.
        """
        return len(self.app.get_accounts()) > 0

    async def close(self) -> None:
        """Clean up resources and ensure cache is saved."""
        self._cache.save()
        self._pending_flow = None

    def _to_token_result(self, result: dict[str, Any]) -> TokenResult:
        """Convert MSAL result dictionary to TokenResult.

        Args:
            result: Raw result from MSAL token acquisition.

        Returns:
            Structured TokenResult instance.
        """
        # Calculate expiration timestamp
        expires_in = result.get("expires_in", 3600)
        expires_on = int(time.time()) + expires_in

        # Extract scopes (MSAL returns space-separated string)
        scope_str = result.get("scope", "")
        scopes = scope_str.split() if scope_str else []

        # Get account ID from ID token claims if available
        account_id = None
        id_token_claims = result.get("id_token_claims", {})
        if id_token_claims:
            account_id = id_token_claims.get("oid") or id_token_claims.get("sub")

        return TokenResult(
            access_token=result["access_token"],
            expires_on=expires_on,
            scopes=scopes,
            account_id=account_id,
        )
