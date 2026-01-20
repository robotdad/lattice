"""Configuration loading for M365 authentication module.

Configuration priority (highest to lowest):
1. Mount config (from bundle or mount plan)
2. Environment variables
3. User config file (~/.amplifier/m365/config.yaml)
4. Module defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

# Default scopes for Microsoft Graph access
# Note: offline_access is automatically added by MSAL, don't include it explicitly
DEFAULT_SCOPES: list[str] = [
    "User.Read",  # Read own profile
    "Mail.Read",  # Read emails
    "Calendars.Read",  # Read calendar
    "Files.Read.All",  # Read OneDrive files
]

# Default cache location
DEFAULT_CACHE_DIR = Path.home() / ".amplifier" / "m365"
DEFAULT_CACHE_PATH = DEFAULT_CACHE_DIR / "token_cache.bin"

# Environment variable names
ENV_CLIENT_ID = "M365_CLIENT_ID"
ENV_TENANT_ID = "M365_TENANT_ID"
ENV_CACHE_PATH = "M365_CACHE_PATH"
ENV_AUTHORITY = "M365_AUTHORITY"


@dataclass
class AuthConfig:
    """Configuration for M365 authentication.

    Attributes:
        client_id: Azure AD application (client) ID. Required.
        tenant_id: Azure AD tenant ID. Use "common" for multi-tenant,
            "organizations" for work/school accounts only,
            "consumers" for personal accounts only,
            or a specific tenant ID/domain.
        scopes: OAuth2 scopes to request. Defaults to basic Graph read access.
        cache_path: Path to token cache file. Defaults to ~/.amplifier/m365/token_cache.bin
        authority: Full authority URL. Auto-derived from tenant_id if not specified.
    """

    client_id: str
    tenant_id: str = "common"
    scopes: list[str] = field(default_factory=lambda: DEFAULT_SCOPES.copy())
    cache_path: Path = DEFAULT_CACHE_PATH
    authority: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.client_id:
            raise ConfigurationError(
                f"M365 client_id is required. Set via {ENV_CLIENT_ID} environment variable "
                "or provide in mount configuration."
            )

        # Convert cache_path to Path if string
        if isinstance(self.cache_path, str):
            self.cache_path = Path(self.cache_path)

        # Derive authority from tenant_id if not explicitly set
        if self.authority is None:
            self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def cache_dir(self) -> Path:
        """Get the directory containing the cache file."""
        return self.cache_path.parent


def load_config(mount_config: dict[str, Any] | None = None) -> AuthConfig:
    """Load configuration with priority: mount > env > defaults.

    Args:
        mount_config: Configuration provided by Amplifier mount system.

    Returns:
        Validated AuthConfig instance.

    Raises:
        ConfigurationError: If required configuration is missing.
    """
    mount_config = mount_config or {}

    # Start building config dict
    config_dict: dict[str, Any] = {}

    # 1. Apply environment variables (lower priority than mount config)
    if env_client_id := os.environ.get(ENV_CLIENT_ID):
        config_dict["client_id"] = env_client_id

    if env_tenant_id := os.environ.get(ENV_TENANT_ID):
        config_dict["tenant_id"] = env_tenant_id

    if env_cache_path := os.environ.get(ENV_CACHE_PATH):
        config_dict["cache_path"] = Path(env_cache_path)

    if env_authority := os.environ.get(ENV_AUTHORITY):
        config_dict["authority"] = env_authority

    # 2. Apply mount config (highest priority)
    if "client_id" in mount_config:
        config_dict["client_id"] = mount_config["client_id"]

    if "tenant_id" in mount_config:
        config_dict["tenant_id"] = mount_config["tenant_id"]

    if "scopes" in mount_config:
        # Mount config scopes replace defaults entirely
        config_dict["scopes"] = list(mount_config["scopes"])

    if "cache_path" in mount_config:
        config_dict["cache_path"] = Path(mount_config["cache_path"])

    if "authority" in mount_config:
        config_dict["authority"] = mount_config["authority"]

    # 3. Ensure client_id exists (required field)
    if "client_id" not in config_dict:
        raise ConfigurationError(
            f"M365 client_id is required. Set the {ENV_CLIENT_ID} environment variable "
            "or provide 'client_id' in the module mount configuration."
        )

    # Create and return validated config
    return AuthConfig(**config_dict)
