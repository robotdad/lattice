"""HTTP client for Microsoft Graph API."""

from typing import Any, Protocol

import httpx

from .config import GraphConfig
from .errors import AuthenticationRequiredError, GraphError


class AuthProvider(Protocol):
    """Protocol for M365 authentication providers.

    This protocol defines the interface expected from the tool-m365-auth module.
    The auth provider is responsible for acquiring and refreshing tokens.
    """

    async def get_token(self, scopes: list[str] | None = None) -> dict[str, Any]:
        """Get a valid access token, refreshing if needed.

        Args:
            scopes: Optional override scopes.

        Returns:
            Dictionary with 'access_token' and other token metadata.

        Raises:
            AuthenticationError: If authentication fails.
        """
        ...


class GraphClient:
    """HTTP client for Microsoft Graph API.

    This client handles authenticated requests to the Graph API,
    including pagination support and error handling.

    Example:
        ```python
        client = GraphClient(config, auth_provider)
        response = await client.request("GET", "/me")
        all_messages = await client.get_all("/me/messages")
        ```
    """

    def __init__(self, config: GraphConfig, auth_provider: AuthProvider) -> None:
        """Initialize the Graph client.

        Args:
            config: Graph API configuration.
            auth_provider: Authentication provider for token acquisition.
        """
        self.config = config
        self.auth = auth_provider
        self._client: httpx.AsyncClient | None = None

    @property
    def _base_url(self) -> str:
        """Get the full base URL including API version."""
        return f"{self.config.base_url}/{self.config.api_version}"

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with current token.

        Returns:
            Headers dictionary with Authorization and Content-Type.

        Raises:
            AuthenticationRequiredError: If no token is available.
        """
        try:
            token_result = await self.auth.get_token()
            access_token = token_result.get("access_token")
            if not access_token:
                raise AuthenticationRequiredError(
                    "No access token returned from auth provider. "
                    "Please authenticate using the m365_auth tool first."
                )
            return {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        except Exception as e:
            # Check if it's already our error type
            if isinstance(e, AuthenticationRequiredError):
                raise
            # Wrap other authentication errors
            raise AuthenticationRequiredError(
                f"Failed to get authentication token: {e}. "
                "Please authenticate using the m365_auth tool first."
            ) from e

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint.

        Args:
            endpoint: API endpoint (e.g., '/me/messages').

        Returns:
            Full URL for the request.
        """
        # Ensure endpoint starts with /
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{self._base_url}{endpoint}"

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a Graph API request.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            endpoint: API endpoint (e.g., '/me/messages').
            params: Query parameters.
            body: Request body (for POST/PATCH).
            headers: Additional headers (merged with auth headers).

        Returns:
            Response data as dictionary. For 204 responses, returns {'status': 'success'}.

        Raises:
            GraphError: If the API returns an error response.
            AuthenticationRequiredError: If authentication fails.
        """
        client = await self._ensure_client()
        auth_headers = await self._get_auth_headers()

        # Merge headers
        request_headers = {**auth_headers}
        if headers:
            request_headers.update(headers)

        url = self._build_url(endpoint)

        response = await client.request(
            method=method.upper(),
            url=url,
            headers=request_headers,
            params=params,
            json=body,
        )

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle HTTP response and convert to result.

        Args:
            response: HTTP response object.

        Returns:
            Response data as dictionary.

        Raises:
            GraphError: If the response indicates an error.
        """
        if response.status_code >= 400:
            # Try to parse error response
            try:
                error_data = response.json().get("error", {})
                error_code = error_data.get("code", f"http_{response.status_code}")
                error_message = error_data.get("message", response.text or "Request failed")
            except Exception:
                error_code = f"http_{response.status_code}"
                error_message = response.text or "Request failed"

            raise GraphError(
                status_code=response.status_code,
                error_code=error_code,
                message=error_message,
            )

        # Handle 204 No Content
        if response.status_code == 204:
            return {"status": "success"}

        # Parse JSON response
        try:
            return response.json()
        except Exception:
            # Return text content if not JSON
            return {"content": response.text, "status_code": response.status_code}

    async def get_all(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all items from a paginated endpoint.

        Automatically follows @odata.nextLink until exhausted or max_pages reached.

        Args:
            endpoint: API endpoint (e.g., '/me/messages').
            params: Query parameters for the initial request.
            max_pages: Maximum pages to fetch (default: config.max_pages).

        Returns:
            List of all items from all pages.

        Raises:
            GraphError: If any request fails.
            AuthenticationRequiredError: If authentication fails.
        """
        client = await self._ensure_client()
        auth_headers = await self._get_auth_headers()

        items: list[dict[str, Any]] = []
        pages = 0
        max_pages = max_pages or self.config.max_pages

        url: str | None = self._build_url(endpoint)
        current_params: dict[str, str] | None = params

        while url and pages < max_pages:
            response = await client.get(
                url,
                headers=auth_headers,
                params=current_params,
            )

            if response.status_code >= 400:
                # Parse error
                try:
                    error_data = response.json().get("error", {})
                    error_code = error_data.get("code", f"http_{response.status_code}")
                    error_message = error_data.get("message", "Request failed")
                except Exception:
                    error_code = f"http_{response.status_code}"
                    error_message = response.text or "Request failed"

                raise GraphError(
                    status_code=response.status_code,
                    error_code=error_code,
                    message=error_message,
                )

            data = response.json()
            items.extend(data.get("value", []))

            # Get next page URL - params are included in nextLink
            url = data.get("@odata.nextLink")
            current_params = None  # nextLink includes all params
            pages += 1

        return items

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
