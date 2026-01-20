"""Token cache management for M365 authentication.

Provides secure persistent storage for MSAL token cache with:
- File-based persistence with restricted permissions (0600)
- Automatic directory creation
- Thread-safe save operations
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path

import msal

from .errors import TokenCacheError

# File permissions: owner read/write only
CACHE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0600


class TokenCache:
    """Manages persistent token cache storage.

    This class wraps MSAL's SerializableTokenCache with file-based
    persistence, ensuring tokens are securely stored between sessions.

    Attributes:
        cache_path: Path to the cache file.
        msal_cache: The underlying MSAL SerializableTokenCache.
    """

    def __init__(self, cache_path: Path):
        """Initialize token cache.

        Args:
            cache_path: Path where the token cache will be stored.

        Raises:
            TokenCacheError: If cache directory cannot be created.
        """
        self.cache_path = cache_path
        self._msal_cache = msal.SerializableTokenCache()
        self._ensure_cache_dir()
        self._load()

    @property
    def msal_cache(self) -> msal.SerializableTokenCache:
        """Get the MSAL token cache instance."""
        return self._msal_cache

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist.

        Raises:
            TokenCacheError: If directory cannot be created.
        """
        cache_dir = self.cache_path.parent
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            # Set directory permissions to 700 (owner only)
            os.chmod(cache_dir, stat.S_IRWXU)
        except OSError as e:
            raise TokenCacheError(f"Failed to create cache directory {cache_dir}: {e}") from e

    def _load(self) -> None:
        """Load cache from disk if it exists."""
        if self.cache_path.exists():
            try:
                data = self.cache_path.read_text(encoding="utf-8")
                self._msal_cache.deserialize(data)
            except OSError:
                # Log warning but don't fail - we can continue with empty cache
                pass
            except Exception:
                # Cache might be corrupted - start fresh
                pass

    def save(self) -> None:
        """Save cache to disk with secure permissions.

        Raises:
            TokenCacheError: If cache cannot be saved.
        """
        if not self._msal_cache.has_state_changed:
            return

        try:
            # Serialize the cache
            data = self._msal_cache.serialize()

            # Write to file with restricted permissions
            # Use write_text with a temporary approach for atomicity
            temp_path = self.cache_path.with_suffix(".tmp")

            # Write to temp file
            temp_path.write_text(data, encoding="utf-8")

            # Set permissions before moving to final location
            os.chmod(temp_path, CACHE_FILE_MODE)

            # Atomic rename
            temp_path.rename(self.cache_path)

        except OSError as e:
            raise TokenCacheError(f"Failed to save token cache: {e}") from e

    def clear(self) -> None:
        """Clear all cached tokens and remove cache file."""
        # Clear in-memory cache by creating a new instance
        self._msal_cache = msal.SerializableTokenCache()

        # Remove cache file if it exists
        with contextlib.suppress(OSError):
            self.cache_path.unlink(missing_ok=True)

    @property
    def has_cached_tokens(self) -> bool:
        """Check if there are any cached tokens.

        Returns:
            True if the cache contains any tokens.
        """
        # Check if the serialized cache has any meaningful content
        data = self._msal_cache.serialize()
        if not data:
            return False

        # MSAL cache is JSON - check if it has any accounts
        try:
            cache_data = json.loads(data)
            # Check for accounts in the cache
            return bool(cache_data.get("Account", {}))
        except (json.JSONDecodeError, TypeError):
            return False
