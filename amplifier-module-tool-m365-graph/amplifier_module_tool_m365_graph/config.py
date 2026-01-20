"""Configuration for Microsoft Graph API module."""

from dataclasses import dataclass


@dataclass
class GraphConfig:
    """Configuration for Graph API access.

    Attributes:
        api_version: Graph API version to use ('v1.0' or 'beta').
        base_url: Base URL for Graph API.
        default_page_size: Default number of items per page for paginated requests.
        max_pages: Maximum number of pages to fetch when paginating.
        timeout: HTTP request timeout in seconds.
    """

    api_version: str = "v1.0"
    base_url: str = "https://graph.microsoft.com"
    default_page_size: int = 100
    max_pages: int = 10
    timeout: float = 30.0

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.api_version not in ("v1.0", "beta"):
            raise ValueError(f"Invalid api_version: {self.api_version}. Must be 'v1.0' or 'beta'.")
        if self.default_page_size < 1 or self.default_page_size > 999:
            raise ValueError(
                f"Invalid default_page_size: {self.default_page_size}. Must be between 1 and 999."
            )
        if self.max_pages < 1:
            raise ValueError(f"Invalid max_pages: {self.max_pages}. Must be at least 1.")
        if self.timeout <= 0:
            raise ValueError(f"Invalid timeout: {self.timeout}. Must be positive.")


def load_config(config: dict | None = None) -> GraphConfig:
    """Load GraphConfig from configuration dictionary.

    Args:
        config: Optional configuration dictionary with keys matching GraphConfig fields.

    Returns:
        GraphConfig instance with values from config or defaults.
    """
    config = config or {}

    return GraphConfig(
        api_version=config.get("api_version", "v1.0"),
        base_url=config.get("base_url", "https://graph.microsoft.com"),
        default_page_size=config.get("default_page_size", 100),
        max_pages=config.get("max_pages", 10),
        timeout=config.get("timeout", 30.0),
    )
