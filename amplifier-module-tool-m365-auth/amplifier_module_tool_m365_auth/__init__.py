"""M365 Authentication module for Amplifier.

This module provides Microsoft 365 authentication capabilities for Amplifier
agents using OAuth2 device code flow via MSAL (Microsoft Authentication Library).

Features:
- Device code flow authentication (no browser required on host)
- Persistent token cache with secure file permissions
- Automatic token refresh
- Multi-account support

Usage:
    The module is loaded via Amplifier's module system. Configure in your
    bundle or mount plan:

    ```yaml
    tools:
      - module: tool-m365-auth
        config:
          client_id: "your-azure-app-client-id"
          tenant_id: "your-tenant-id"  # or "common" for multi-tenant
    ```

    Or set environment variables:
    - M365_CLIENT_ID: Azure AD application client ID (required)
    - M365_TENANT_ID: Azure AD tenant ID (optional, defaults to "common")

Exports:
    mount: Module entry point for Amplifier
    M365AuthProvider: Authentication provider class
    M365AuthTool: Tool implementation for agents
    AuthConfig: Configuration dataclass
    TokenResult: Token acquisition result
    DeviceCodeInfo: Device code flow information
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .auth import DeviceCodeInfo, M365AuthProvider, TokenResult
from .config import AuthConfig, load_config
from .errors import (
    AuthenticationCancelledError,
    AuthenticationError,
    AuthenticationTimeoutError,
    ConfigurationError,
    M365AuthError,
    NotAuthenticatedError,
    TokenCacheError,
)
from .tool import M365AuthTool

if TYPE_CHECKING:
    from collections.abc import Callable

# Module type identifier for Amplifier
__amplifier_module_type__ = "tool"

__all__ = [
    # Main exports
    "mount",
    "M365AuthProvider",
    "M365AuthTool",
    # Configuration
    "AuthConfig",
    "load_config",
    # Data classes
    "TokenResult",
    "DeviceCodeInfo",
    # Exceptions
    "M365AuthError",
    "AuthenticationError",
    "AuthenticationCancelledError",
    "AuthenticationTimeoutError",
    "ConfigurationError",
    "TokenCacheError",
    "NotAuthenticatedError",
]


async def mount(
    coordinator: Any,
    config: dict[str, Any] | None = None,
) -> Callable[[], Any] | None:
    """Mount the M365 auth module into Amplifier.

    This is the entry point called by Amplifier's module loader. It:
    1. Loads and validates configuration
    2. Creates the authentication provider
    3. Creates and registers the authentication tool
    4. Registers the auth provider as a shared service for other modules

    Args:
        coordinator: Amplifier coordinator instance for registering tools/services.
        config: Optional configuration dictionary from mount plan.

    Returns:
        Cleanup function to call on unmount, or None.

    Raises:
        ConfigurationError: If required configuration is missing.

    Example mount configuration:
        ```yaml
        tools:
          - module: tool-m365-auth
            config:
              client_id: "your-client-id"
              tenant_id: "your-tenant-id"
              scopes:
                - User.Read
                - Mail.Read
                - offline_access
        ```
    """
    # Load configuration with priority: mount config > env vars > defaults
    auth_config = load_config(config)

    # Create shared auth provider instance
    auth_provider = M365AuthProvider(auth_config)

    # Create the tool
    tool = M365AuthTool(auth_provider)

    # Register the tool with the coordinator
    # The coordinator.mount() method registers tools for agent use
    if hasattr(coordinator, "mount"):
        await coordinator.mount("tools", tool, name="m365_auth")

    # Register auth provider as a shared service for other modules
    # This allows tool-m365-graph to get tokens without re-implementing auth
    if hasattr(coordinator, "register_contributor"):
        coordinator.register_contributor(
            "services.m365_auth",
            "tool-m365-auth",
            lambda: auth_provider,
        )

    # Return cleanup function
    async def cleanup() -> None:
        """Clean up resources on module unmount."""
        await auth_provider.close()

    return cleanup
