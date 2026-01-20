"""Error types for Microsoft Graph API module."""


class GraphError(Exception):
    """Exception raised for Graph API errors.

    This exception provides structured error information from Graph API responses
    while ensuring no sensitive data (tokens, credentials) is exposed.

    Attributes:
        status_code: HTTP status code from the response.
        error_code: Graph API error code (e.g., 'InvalidAuthenticationToken').
        message: Human-readable error message.
    """

    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        """Initialize GraphError.

        Args:
            status_code: HTTP status code from the response.
            error_code: Graph API error code.
            message: Human-readable error message.
        """
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(f"Graph API error {status_code}: {error_code} - {message}")

    def to_dict(self) -> dict:
        """Convert error to dictionary representation.

        Returns:
            Dictionary with error details suitable for tool result.
        """
        return {
            "status_code": self.status_code,
            "error_code": self.error_code,
            "message": self.message,
        }


class AuthProviderNotFoundError(Exception):
    """Exception raised when the M365 auth provider is not available.

    This typically means the tool-m365-auth module is not mounted.
    """

    def __init__(self) -> None:
        """Initialize AuthProviderNotFoundError."""
        super().__init__(
            "M365 auth provider not found. Please ensure 'tool-m365-auth' module is mounted "
            "before 'tool-m365-graph'. Add 'tool-m365-auth' to your bundle configuration."
        )


class AuthenticationRequiredError(Exception):
    """Exception raised when authentication is required but not available.

    This indicates the user needs to authenticate before making Graph API requests.
    """

    def __init__(self, message: str = "Authentication required") -> None:
        """Initialize AuthenticationRequiredError.

        Args:
            message: Error message describing the authentication issue.
        """
        super().__init__(message)
