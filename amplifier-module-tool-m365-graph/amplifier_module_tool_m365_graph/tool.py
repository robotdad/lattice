"""Microsoft Graph API tool for Amplifier agents."""

from typing import Any

from amplifier_core.models import ToolResult

from .client import AuthProvider, GraphClient
from .config import GraphConfig
from .errors import AuthenticationRequiredError, GraphError

# Module type marker for Amplifier
__amplifier_module_type__ = "tool"


class M365GraphTool:
    """Microsoft Graph API tool for agents.

    This tool provides access to Microsoft 365 data through the Graph API,
    including emails, calendar, files, users, and more.

    Authentication is handled automatically via the M365 auth provider.
    If not authenticated, the tool returns an error prompting the user
    to use the m365_auth tool first.

    Example usage by agent:
        ```
        # Get current user profile
        m365_graph(endpoint="/me")

        # List unread emails
        m365_graph(
            endpoint="/me/messages",
            params={"$filter": "isRead eq false", "$top": "10"}
        )

        # Get all calendar events (with pagination)
        m365_graph(endpoint="/me/calendar/events", paginate=True)

        # Create a new event
        m365_graph(
            method="POST",
            endpoint="/me/calendar/events",
            body={
                "subject": "Team Meeting",
                "start": {"dateTime": "2025-01-20T10:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2025-01-20T11:00:00", "timeZone": "UTC"}
            }
        )
        ```
    """

    def __init__(self, config: GraphConfig, auth_provider: AuthProvider) -> None:
        """Initialize the Graph tool.

        Args:
            config: Graph API configuration.
            auth_provider: Authentication provider from tool-m365-auth module.
        """
        self.config = config
        self._client = GraphClient(config, auth_provider)

    @property
    def name(self) -> str:
        """Tool name for invocation."""
        return "m365_graph"

    @property
    def description(self) -> str:
        """Human-readable tool description."""
        return """Make requests to Microsoft Graph API to access Microsoft 365 data.

Use this tool to access M365 data: emails, calendar, files, users, groups, and more.

Common endpoints:
- /me - Current user profile
- /me/messages - User's emails
- /me/calendar/events - Calendar events
- /me/drive/root/children - OneDrive root files
- /me/drive/root:/path/to/file:/content - Get file content
- /users - Directory users (requires admin consent)
- /groups - Directory groups

Query parameters (pass in 'params'):
- $select - Fields to return (e.g., "subject,from,receivedDateTime")
- $filter - Filter results (e.g., "isRead eq false")
- $orderby - Sort results (e.g., "receivedDateTime desc")
- $top - Limit results (e.g., "10")
- $search - Search in content (e.g., "subject:meeting")

Authentication is handled automatically. If not authenticated,
you'll receive an error asking you to use the m365_auth tool first."""

    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PATCH", "DELETE"],
                    "default": "GET",
                    "description": "HTTP method for the request",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Graph API endpoint (e.g., '/me/messages')",
                },
                "params": {
                    "type": "object",
                    "description": "Query parameters ($select, $filter, $top, $orderby, etc.)",
                    "additionalProperties": {"type": "string"},
                },
                "body": {
                    "type": "object",
                    "description": "Request body for POST/PATCH operations",
                },
                "paginate": {
                    "type": "boolean",
                    "default": False,
                    "description": "Auto-follow pagination links to get all results",
                },
            },
            "required": ["endpoint"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        """Execute a Graph API request.

        Args:
            input: Tool input with endpoint, method, params, body, and paginate fields.

        Returns:
            ToolResult with API response or error details.
        """
        try:
            # Extract parameters
            method = input.get("method", "GET").upper()
            endpoint = input.get("endpoint", "")
            params = input.get("params")
            body = input.get("body")
            paginate = input.get("paginate", False)

            # Validate endpoint
            if not endpoint:
                return ToolResult(
                    success=False,
                    error={"code": "missing_endpoint", "message": "Endpoint is required"},
                )

            # Validate method
            if method not in ("GET", "POST", "PATCH", "DELETE"):
                return ToolResult(
                    success=False,
                    error={
                        "code": "invalid_method",
                        "message": (
                            f"Invalid method: {method}. Must be GET, POST, PATCH, or DELETE."
                        ),
                    },
                )

            # Convert params values to strings if needed (Graph API expects string query params)
            if params:
                params = {k: str(v) for k, v in params.items()}

            # Handle paginated requests
            if paginate and method == "GET":
                items = await self._client.get_all(endpoint, params=params)
                return ToolResult(
                    success=True,
                    output={
                        "items": items,
                        "count": len(items),
                        "@odata.context": f"Paginated results from {endpoint}",
                    },
                )

            # Single request
            data = await self._client.request(
                method=method,
                endpoint=endpoint,
                params=params,
                body=body,
            )

            return ToolResult(success=True, output=data)

        except GraphError as e:
            return ToolResult(
                success=False,
                error={
                    "code": e.error_code,
                    "message": e.message,
                    "status_code": e.status_code,
                },
            )

        except AuthenticationRequiredError as e:
            return ToolResult(
                success=False,
                error={
                    "code": "authentication_required",
                    "message": str(e),
                    "action": "Please use the m365_auth tool to authenticate first.",
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error={
                    "code": "unexpected_error",
                    "message": f"Unexpected error: {e}",
                },
            )

    async def close(self) -> None:
        """Clean up resources."""
        await self._client.close()
