"""Microsoft Graph API tool module for Amplifier.

This module provides a tool for making authenticated requests to the
Microsoft Graph API, enabling agents to access M365 data like emails,
calendar events, files, and more.

Dependencies:
    - tool-m365-auth: Required for authentication. Must be mounted before this module.

Example bundle configuration:
    ```yaml
    tools:
      - module: tool-m365-auth
        config:
          client_id: ${M365_CLIENT_ID}
          tenant_id: "your-tenant-id"

      - module: tool-m365-graph
        config:
          api_version: v1.0
          default_page_size: 50
    ```
"""

from typing import Any

from .config import GraphConfig, load_config
from .errors import AuthProviderNotFoundError, GraphError
from .tool import M365GraphTool

# Module type marker for Amplifier module discovery
__amplifier_module_type__ = "tool"

__all__ = [
    "GraphConfig",
    "GraphError",
    "M365GraphTool",
    "mount",
]


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> Any:
    """Mount the M365 Graph tool module.

    This function is the entry point called by Amplifier when loading the module.
    It retrieves the auth provider from the coordinator's services and creates
    the Graph tool instance.

    Args:
        coordinator: Amplifier module coordinator providing infrastructure context.
        config: Optional configuration dictionary with keys:
            - api_version: Graph API version ('v1.0' or 'beta', default: 'v1.0')
            - base_url: Graph API base URL (default: 'https://graph.microsoft.com')
            - default_page_size: Items per page (default: 100)
            - max_pages: Max pages for pagination (default: 10)
            - timeout: Request timeout in seconds (default: 30.0)

    Returns:
        Cleanup function to be called when module is unmounted.

    Raises:
        AuthProviderNotFoundError: If tool-m365-auth is not mounted.

    Example:
        ```python
        # Typically called by Amplifier's module loader, not directly
        cleanup = await mount(coordinator, {"api_version": "beta"})
        ```
    """
    # Load configuration
    graph_config = load_config(config)

    # Get auth provider from coordinator services
    # The auth module registers itself as a contributor on the services.m365_auth channel
    auth_provider = _get_auth_provider(coordinator)

    if auth_provider is None:
        raise AuthProviderNotFoundError()

    # Create tool instance
    tool = M365GraphTool(graph_config, auth_provider)

    # Register tool with coordinator
    await coordinator.mount("tools", tool, name="m365_graph")

    # Return cleanup function
    async def cleanup() -> None:
        """Clean up resources when module is unmounted."""
        await tool.close()

    return cleanup


def _get_auth_provider(coordinator: Any) -> Any | None:
    """Get the M365 auth provider from the coordinator.

    The auth provider is registered by tool-m365-auth module as a service
    contributor. This function attempts to retrieve it using both the
    capability system and the contribution channel system.

    Args:
        coordinator: Amplifier module coordinator.

    Returns:
        The auth provider instance, or None if not found.
    """
    # Try capability system first (simpler, direct access)
    auth_provider = coordinator.get_capability("services.m365_auth")
    if auth_provider is not None:
        return auth_provider

    # Fall back to contribution channel (async collection)
    # This requires collecting contributions, which returns a list
    # We need to handle this synchronously during mount, so we check
    # if there are any registered contributors
    if hasattr(coordinator, "channels"):
        channel = coordinator.channels.get("services.m365_auth", [])
        if channel:
            # Get the first contributor's callback and invoke it
            contributor = channel[0]
            callback = contributor.get("callback")
            if callback:
                result = callback()
                # Handle if callback returns the provider directly
                if result is not None:
                    return result

    return None
