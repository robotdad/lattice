"""M365 authentication tool for Amplifier agents.

This module implements the M365AuthTool class which exposes authentication
operations to AI agents through Amplifier's tool protocol.

Operations:
- login: Start device code authentication flow
- status: Check current authentication status
- logout: Clear cached credentials
- accounts: List authenticated accounts
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .auth import M365AuthProvider
from .errors import (
    AuthenticationCancelledError,
    AuthenticationError,
    AuthenticationTimeoutError,
    NotAuthenticatedError,
)

if TYPE_CHECKING:
    pass

# Module type identifier for Amplifier
__amplifier_module_type__ = "tool"


class M365AuthTool:
    """Tool for M365 authentication operations.

    This tool allows agents to manage Microsoft 365 authentication,
    including initiating login flows, checking status, and managing
    cached credentials.

    The tool uses device code flow which is ideal for agent scenarios
    where the user authenticates in a separate browser session.

    Attributes:
        name: Tool name for registration ("m365_auth").
        description: Human-readable description for agents.
    """

    def __init__(self, auth_provider: M365AuthProvider):
        """Initialize the authentication tool.

        Args:
            auth_provider: The M365AuthProvider instance to use.
        """
        self._auth = auth_provider

    @property
    def name(self) -> str:
        """Get the tool name."""
        return "m365_auth"

    @property
    def description(self) -> str:
        """Get the tool description for agents."""
        return """Authenticate with Microsoft 365 services.

Operations:
- login: Start authentication (device code flow). Returns a URL and code for the user.
- status: Check current authentication status and account info.
- logout: Clear cached credentials. Optionally specify account_id for specific account.
- accounts: List all authenticated accounts with usernames and IDs.

Call 'login' when M365 access is needed and no valid session exists.
The user will authenticate in their browser using a device code."""

    def get_schema(self) -> dict[str, Any]:
        """Get the JSON schema for tool parameters.

        Returns:
            JSON Schema object describing valid inputs.
        """
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["login", "status", "logout", "accounts"],
                    "description": "Authentication operation to perform",
                },
                "account_id": {
                    "type": "string",
                    "description": (
                        "Account ID for logout operation. If not specified, logs out all accounts."
                    ),
                },
                "scopes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "OAuth2 scopes to request for login. "
                        "Defaults to configured scopes if not specified."
                    ),
                },
            },
            "required": ["operation"],
        }

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an authentication operation.

        Args:
            params: Operation parameters matching the schema.

        Returns:
            Result dictionary with operation-specific data.
        """
        operation = params.get("operation")

        if operation == "login":
            return await self._handle_login(params)
        elif operation == "status":
            return await self._handle_status()
        elif operation == "logout":
            return await self._handle_logout(params)
        elif operation == "accounts":
            return await self._handle_accounts()
        else:
            return {
                "success": False,
                "error": {
                    "code": "invalid_operation",
                    "message": f"Unknown operation: {operation}. "
                    "Valid operations: login, status, logout, accounts",
                },
            }

    async def _handle_login(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle the login operation.

        Initiates device code flow and waits for user to complete
        authentication in their browser.

        Args:
            params: May contain 'scopes' for custom scope request.

        Returns:
            Result with authentication outcome.
        """
        scopes = params.get("scopes")

        try:
            # Check if already authenticated
            if self._auth.is_authenticated():
                try:
                    # Try to get a valid token silently
                    token = await self._auth.get_token_silent(scopes)
                    accounts = self._auth.get_accounts()
                    return {
                        "success": True,
                        "already_authenticated": True,
                        "message": "Already authenticated with a valid session.",
                        "account": accounts[0] if accounts else None,
                        "expires_on": token.expires_on,
                    }
                except NotAuthenticatedError:
                    # Token expired, need to re-authenticate
                    pass

            # Initiate device code flow
            device_info = await self._auth.initiate_device_code(scopes)

            # Return device code info for user to complete auth
            # The tool result instructs the user what to do
            return {
                "success": True,
                "requires_user_action": True,
                "message": device_info.message,
                "user_code": device_info.user_code,
                "verification_uri": device_info.verification_uri,
                "expires_in": device_info.expires_in,
                "instructions": (
                    f"Please open {device_info.verification_uri} in your browser "
                    f"and enter the code: {device_info.user_code}"
                ),
            }

        except AuthenticationError as e:
            return {
                "success": False,
                "error": {
                    "code": e.error_code or "authentication_error",
                    "message": str(e),
                },
            }

    async def complete_login(self, timeout: float = 300) -> dict[str, Any]:
        """Complete a pending login operation.

        This method should be called after the user has been shown the
        device code and is expected to complete authentication.

        Args:
            timeout: Maximum seconds to wait for completion.

        Returns:
            Result with authentication outcome.
        """
        try:
            token = await self._auth.complete_device_code(timeout)
            accounts = self._auth.get_accounts()

            return {
                "success": True,
                "message": "Successfully authenticated with Microsoft 365.",
                "account": accounts[0] if accounts else None,
                "expires_on": token.expires_on,
                "scopes": token.scopes,
            }

        except AuthenticationTimeoutError as e:
            return {
                "success": False,
                "error": {
                    "code": "timeout",
                    "message": str(e),
                },
            }
        except AuthenticationCancelledError as e:
            return {
                "success": False,
                "error": {
                    "code": "cancelled",
                    "message": str(e),
                },
            }
        except AuthenticationError as e:
            return {
                "success": False,
                "error": {
                    "code": e.error_code or "authentication_error",
                    "message": str(e),
                },
            }

    async def _handle_status(self) -> dict[str, Any]:
        """Handle the status operation.

        Returns:
            Current authentication status and account info.
        """
        is_authenticated = self._auth.is_authenticated()
        accounts = self._auth.get_accounts()

        if not is_authenticated:
            return {
                "success": True,
                "authenticated": False,
                "message": "Not authenticated. Use 'login' operation to authenticate.",
            }

        # Try to check if token is still valid
        try:
            token = await self._auth.get_token_silent()
            return {
                "success": True,
                "authenticated": True,
                "message": "Authenticated with valid session.",
                "accounts": accounts,
                "active_account": accounts[0] if accounts else None,
                "token_expires_on": token.expires_on,
            }
        except NotAuthenticatedError:
            return {
                "success": True,
                "authenticated": False,
                "message": ("Session expired. Use 'login' operation to re-authenticate."),
                "accounts": accounts,
            }

    async def _handle_logout(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle the logout operation.

        Args:
            params: May contain 'account_id' for specific account logout.

        Returns:
            Logout operation result.
        """
        account_id = params.get("account_id")

        removed = await self._auth.logout(account_id)

        if removed:
            if account_id:
                return {
                    "success": True,
                    "message": f"Successfully logged out account: {account_id}",
                }
            else:
                return {
                    "success": True,
                    "message": "Successfully logged out all accounts.",
                }
        else:
            return {
                "success": True,
                "message": "No accounts to log out.",
            }

    async def _handle_accounts(self) -> dict[str, Any]:
        """Handle the accounts operation.

        Returns:
            List of authenticated accounts.
        """
        accounts = self._auth.get_accounts()

        if not accounts:
            return {
                "success": True,
                "accounts": [],
                "message": "No authenticated accounts.",
            }

        return {
            "success": True,
            "accounts": accounts,
            "count": len(accounts),
        }
