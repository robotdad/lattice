# M365 Integration Design for Amplifier

**Status**: Design  
**Author**: Zen Architect  
**Date**: 2025-01-16  
**Version**: 1.0.0

---

## Executive Summary

This document defines the architecture for integrating Microsoft 365 services into Amplifier. The design follows Amplifier's kernel philosophy: **mechanism over policy**, **ruthless simplicity**, and **modular composition**.

The integration consists of **two separate modules**:
1. **`tool-m365-auth`** - Authentication mechanism (MSAL, device code flow, token persistence)
2. **`tool-m365-graph`** - Microsoft Graph API tool (authenticated requests)

This separation allows:
- Independent versioning and updates
- Auth mechanism reusable by other M365 tools
- Graph tool replaceable without touching auth
- Clear security boundary around credential handling

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Amplifier Agent                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐          ┌──────────────────────────────────┐ │
│  │  tool-m365-auth  │          │       tool-m365-graph            │ │
│  │                  │          │                                  │ │
│  │  - Device code   │ ◄────────┤  - GET/POST/PATCH/DELETE         │ │
│  │  - Token cache   │  tokens  │  - Resource helpers              │ │
│  │  - Refresh       │          │  - Response formatting           │ │
│  │  - Multi-tenant  │          │                                  │ │
│  └────────┬─────────┘          └──────────────┬───────────────────┘ │
│           │                                    │                     │
└───────────┼────────────────────────────────────┼─────────────────────┘
            │                                    │
            ▼                                    ▼
    ┌───────────────┐                   ┌───────────────┐
    │  Azure AD     │                   │ Microsoft     │
    │  (OAuth2)     │                   │ Graph API     │
    └───────────────┘                   └───────────────┘
```

### Component Interactions

```
User                   Agent                Auth Module           Graph Module         Azure AD         Graph API
  │                      │                      │                      │                  │                │
  │  "List my emails"    │                      │                      │                  │                │
  ├─────────────────────►│                      │                      │                  │                │
  │                      │  graph_request()     │                      │                  │                │
  │                      ├─────────────────────────────────────────────►│                  │                │
  │                      │                      │  get_token()         │                  │                │
  │                      │                      │◄─────────────────────┤                  │                │
  │                      │                      │                      │                  │                │
  │                      │                      │  [cache miss]        │                  │                │
  │                      │                      ├─────────────────────────────────────────►│                │
  │                      │                      │                      │   device_code    │                │
  │                      │                      │◄─────────────────────────────────────────┤                │
  │                      │                      │                      │                  │                │
  │  "Go to URL, enter   │◄─────────────────────┤                      │                  │                │
  │   code: ABCD-1234"   │                      │                      │                  │                │
  ├──────────────────────┼──────────────────────┼──────────────────────┼──────────────────►│                │
  │  [user authenticates in browser]            │                      │                  │                │
  │                      │                      │                      │                  │                │
  │                      │                      │  poll for token      │                  │                │
  │                      │                      ├─────────────────────────────────────────►│                │
  │                      │                      │  access_token        │                  │                │
  │                      │                      │◄─────────────────────────────────────────┤                │
  │                      │                      │                      │                  │                │
  │                      │                      │  [cache token]       │                  │                │
  │                      │                      │                      │                  │                │
  │                      │                      │  token               │                  │                │
  │                      │                      ├─────────────────────►│                  │                │
  │                      │                      │                      │                  │                │
  │                      │                      │                      │  GET /me/messages│                │
  │                      │                      │                      ├─────────────────────────────────►│
  │                      │                      │                      │  emails          │                │
  │                      │                      │                      │◄─────────────────────────────────┤
  │                      │  emails              │                      │                  │                │
  │                      │◄─────────────────────────────────────────────┤                  │                │
  │  "You have 5 emails" │                      │                      │                  │                │
  │◄─────────────────────┤                      │                      │                  │                │
```

---

## 2. Module Structure

### 2.1 Why Two Modules (Not One)

| Concern | Single Module | Two Modules |
|---------|--------------|-------------|
| **Security boundary** | Credentials mixed with API logic | Auth isolated, minimal surface |
| **Testing** | Must mock Azure AD for all tests | Auth tests separate, Graph tests mock auth |
| **Reusability** | Graph-specific | Auth reusable for SharePoint, Teams SDKs |
| **Updates** | Graph schema changes force full update | Independent versioning |
| **Complexity** | Hidden coupling | Explicit dependency |

**Decision**: Two modules. The slight overhead of two packages is worth the clean separation.

### 2.2 Module: `tool-m365-auth`

**Purpose**: Provide authenticated tokens for M365 services.

**Responsibilities**:
- Device code flow initiation and completion
- Token caching (memory + disk)
- Automatic refresh of expired tokens
- Multi-tenant/multi-account support
- Secure token storage

**Does NOT**:
- Make Graph API calls
- Parse Graph responses
- Know about specific M365 resources

### 2.3 Module: `tool-m365-graph`

**Purpose**: Make authenticated Microsoft Graph API requests.

**Responsibilities**:
- HTTP requests to Graph API
- Request/response formatting
- Common resource helpers (mail, calendar, files, users)
- Pagination handling
- Error translation

**Depends on**: `tool-m365-auth` for tokens

---

## 3. Key Interfaces and Contracts

### 3.1 Auth Module Interface

```python
# amplifier_module_tool_m365_auth/auth.py

from dataclasses import dataclass
from typing import Protocol


@dataclass
class AuthConfig:
    """Configuration for M365 authentication."""
    client_id: str
    tenant_id: str = "common"  # "common", "organizations", "consumers", or specific tenant
    scopes: list[str] = None  # Default: ["https://graph.microsoft.com/.default"]
    cache_path: str | None = None  # None = ~/.amplifier/m365/token_cache.bin
    authority: str | None = None  # Auto-derived from tenant_id if None


@dataclass  
class TokenResult:
    """Result of token acquisition."""
    access_token: str
    expires_on: int  # Unix timestamp
    scopes: list[str]
    account_id: str | None = None


@dataclass
class DeviceCodeInfo:
    """Information for device code flow."""
    user_code: str
    verification_uri: str
    message: str  # Human-readable instruction
    expires_in: int  # Seconds until code expires


class M365AuthProvider(Protocol):
    """Protocol for M365 authentication providers."""
    
    async def get_token(self, scopes: list[str] | None = None) -> TokenResult:
        """
        Get a valid access token, refreshing if needed.
        
        If no cached token exists, initiates device code flow.
        Returns immediately if valid cached token exists.
        
        Args:
            scopes: Optional override scopes (default: configured scopes)
            
        Returns:
            TokenResult with valid access token
            
        Raises:
            AuthenticationError: If authentication fails
            AuthenticationCancelledError: If user cancels flow
        """
        ...
    
    async def initiate_device_code(
        self, 
        scopes: list[str] | None = None
    ) -> DeviceCodeInfo:
        """
        Start device code flow without blocking.
        
        Use this for custom UI handling of the device code.
        Call complete_device_code() after user authenticates.
        
        Returns:
            DeviceCodeInfo with code and instructions
        """
        ...
    
    async def complete_device_code(self, timeout: float = 300) -> TokenResult:
        """
        Wait for device code flow completion.
        
        Args:
            timeout: Max seconds to wait (default: 5 minutes)
            
        Returns:
            TokenResult on success
            
        Raises:
            TimeoutError: If user doesn't complete in time
            AuthenticationError: If authentication fails
        """
        ...
    
    async def logout(self, account_id: str | None = None) -> None:
        """
        Remove cached tokens for account.
        
        Args:
            account_id: Specific account, or None for all accounts
        """
        ...
    
    def get_accounts(self) -> list[dict]:
        """
        List cached accounts.
        
        Returns:
            List of account info dicts with 'username', 'account_id'
        """
        ...
```

### 3.2 Auth Tool Schema (for Agent Use)

```python
# The auth tool exposed to agents

class M365AuthTool:
    """Tool for M365 authentication operations."""
    
    @property
    def name(self) -> str:
        return "m365_auth"
    
    @property
    def description(self) -> str:
        return """Authenticate with Microsoft 365 services.

Operations:
- login: Start authentication (device code flow)
- status: Check current authentication status
- logout: Clear cached credentials
- accounts: List authenticated accounts

The agent should call 'login' when M365 access is needed and no 
valid session exists. The user will be prompted to authenticate 
in their browser."""

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["login", "status", "logout", "accounts"],
                    "description": "Authentication operation to perform"
                },
                "account_id": {
                    "type": "string",
                    "description": "Account ID for logout (optional, defaults to all)"
                }
            },
            "required": ["operation"]
        }
```

### 3.3 Graph Module Interface

```python
# amplifier_module_tool_m365_graph/graph.py

from dataclasses import dataclass
from typing import Any


@dataclass
class GraphConfig:
    """Configuration for Graph API access."""
    api_version: str = "v1.0"  # or "beta"
    base_url: str = "https://graph.microsoft.com"
    default_page_size: int = 100
    max_pages: int = 10  # Pagination limit


@dataclass
class GraphResponse:
    """Response from Graph API."""
    success: bool
    status_code: int
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    next_link: str | None = None  # For pagination


class M365GraphClient(Protocol):
    """Protocol for Graph API client."""
    
    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> GraphResponse:
        """
        Make a Graph API request.
        
        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            endpoint: API endpoint (e.g., "/me/messages")
            params: Query parameters
            body: Request body (for POST/PATCH)
            headers: Additional headers
            
        Returns:
            GraphResponse with result or error
        """
        ...
    
    async def get_all(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all items from a paginated endpoint.
        
        Automatically follows @odata.nextLink until exhausted
        or max_pages reached.
        
        Returns:
            List of all items
        """
        ...
```

### 3.4 Graph Tool Schema (for Agent Use)

```python
class M365GraphTool:
    """Tool for Microsoft Graph API requests."""
    
    @property
    def name(self) -> str:
        return "m365_graph"
    
    @property
    def description(self) -> str:
        return """Make requests to Microsoft Graph API.

Use this tool to access M365 data: emails, calendar, files, users, etc.

Common endpoints:
- /me - Current user profile
- /me/messages - User's emails  
- /me/calendar/events - Calendar events
- /me/drive/root/children - OneDrive files
- /users - Directory users (requires admin)

Authentication is handled automatically. If not authenticated,
you'll be prompted to use m365_auth tool first."""

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PATCH", "DELETE"],
                    "default": "GET",
                    "description": "HTTP method"
                },
                "endpoint": {
                    "type": "string",
                    "description": "Graph API endpoint (e.g., '/me/messages')"
                },
                "params": {
                    "type": "object",
                    "description": "Query parameters ($select, $filter, $top, etc.)"
                },
                "body": {
                    "type": "object", 
                    "description": "Request body for POST/PATCH"
                },
                "paginate": {
                    "type": "boolean",
                    "default": False,
                    "description": "Auto-follow pagination links"
                }
            },
            "required": ["endpoint"]
        }
```

---

## 4. Security Considerations

### 4.1 Token Storage

**Threat Model**:
- Tokens on disk could be stolen by malware or other users
- Tokens in memory could be dumped or leaked in logs
- Refresh tokens are long-lived and high-value

**Mitigations**:

| Layer | Protection |
|-------|------------|
| **Disk storage** | MSAL's encrypted token cache + file permissions (600) |
| **Memory** | Tokens not logged, cleared on logout |
| **Scope limitation** | Request minimum required scopes |
| **Token lifetime** | Rely on MSAL's automatic refresh |
| **Multi-user** | Separate cache files per user/tenant |

**Token Cache Location**:
```
~/.amplifier/m365/
├── token_cache_{tenant_hash}.bin  # Encrypted by MSAL
└── config.yaml                    # Non-sensitive config only
```

### 4.2 Credential Configuration

**Principle**: Client ID and Tenant ID are NOT secrets. They can be in config files.

**What goes where**:

| Item | Storage | Rationale |
|------|---------|-----------|
| Client ID | Config file / env var | Public identifier |
| Tenant ID | Config file / env var | Public identifier |
| Access tokens | MSAL cache (encrypted) | Short-lived secrets |
| Refresh tokens | MSAL cache (encrypted) | Long-lived secrets |
| Client secrets | NEVER | Not used in device code flow |

### 4.3 Scope Management

**Default Scopes** (minimal for basic Graph access):
```python
DEFAULT_SCOPES = [
    "User.Read",           # Read own profile
    "Mail.Read",           # Read emails
    "Calendars.Read",      # Read calendar
    "Files.Read.All",      # Read OneDrive files
    "offline_access",      # Enable refresh tokens
]
```

**Scope Escalation Pattern**:
```python
# Start minimal, escalate when needed
async def ensure_scope(self, scope: str) -> None:
    """Request additional scope if not already granted."""
    if scope not in self.current_scopes:
        # This will trigger re-authentication with new scope
        await self.auth.get_token(scopes=[*self.current_scopes, scope])
```

### 4.4 Error Handling (No Credential Leaks)

```python
class AuthenticationError(Exception):
    """Authentication failed - safe to display."""
    pass

class GraphError(Exception):
    """Graph API error - safe to display."""
    def __init__(self, status_code: int, error_code: str, message: str):
        # Sanitize: never include tokens or request headers
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(f"Graph API error {status_code}: {error_code} - {message}")
```

---

## 5. Configuration Approach

### 5.1 Configuration Sources (Priority Order)

1. **Mount config** (bundle/mount plan) - highest priority
2. **Environment variables** - deployment overrides
3. **User config file** (`~/.amplifier/m365/config.yaml`) - user defaults
4. **Module defaults** - fallback

### 5.2 Configuration Schema

**Mount Plan (bundle.md or mount plan)**:
```yaml
tools:
  - module: tool-m365-auth
    source: git+https://github.com/microsoft/amplifier-module-tool-m365-auth@v1.0.0
    config:
      client_id: ${M365_CLIENT_ID}  # Can use env var interpolation
      tenant_id: "your-tenant-id"  # Or "common" for multi-tenant
      scopes:
        - User.Read
        - Mail.Read
        - offline_access

  - module: tool-m365-graph
    source: git+https://github.com/microsoft/amplifier-module-tool-m365-graph@v1.0.0
    config:
      api_version: v1.0
      default_page_size: 50
```

**Environment Variables**:
```bash
# Required
M365_CLIENT_ID=your-app-registration-client-id

# Optional
M365_TENANT_ID=your-tenant-id  # Default: "common"
M365_CACHE_PATH=/custom/path/token_cache.bin
M365_API_VERSION=v1.0  # or "beta"
```

**User Config File** (`~/.amplifier/m365/config.yaml`):
```yaml
# User-level defaults (lowest priority)
default_tenant: my-org.onmicrosoft.com
default_scopes:
  - User.Read
  - Mail.ReadWrite
  - Calendars.ReadWrite
```

### 5.3 Configuration Loading

```python
def load_config(mount_config: dict) -> AuthConfig:
    """Load config with priority: mount > env > user file > defaults."""
    
    # Start with defaults
    config = AuthConfig(
        client_id="",
        tenant_id="common",
        scopes=DEFAULT_SCOPES,
    )
    
    # Layer user file
    user_config = _load_user_config()
    if user_config:
        config = _merge(config, user_config)
    
    # Layer environment
    if client_id := os.environ.get("M365_CLIENT_ID"):
        config.client_id = client_id
    if tenant_id := os.environ.get("M365_TENANT_ID"):
        config.tenant_id = tenant_id
    
    # Layer mount config (highest priority)
    if mount_config:
        config = _merge(config, mount_config)
    
    # Validate
    if not config.client_id:
        raise ConfigurationError(
            "M365_CLIENT_ID required. Set via environment variable or mount config."
        )
    
    return config
```

---

## 6. File Structure

### 6.1 Auth Module

```
amplifier-module-tool-m365-auth/
├── README.md
├── LICENSE
├── pyproject.toml
├── amplifier_module_tool_m365_auth/
│   ├── __init__.py          # mount() entry point
│   ├── auth.py              # M365AuthProvider implementation
│   ├── cache.py             # Token cache management
│   ├── config.py            # Configuration loading
│   ├── errors.py            # Exception classes
│   └── tool.py              # M365AuthTool implementation
└── tests/
    ├── __init__.py
    ├── test_auth.py
    ├── test_cache.py
    ├── test_config.py
    └── conftest.py          # Fixtures, mocks
```

### 6.2 Graph Module

```
amplifier-module-tool-m365-graph/
├── README.md
├── LICENSE
├── pyproject.toml
├── amplifier_module_tool_m365_graph/
│   ├── __init__.py          # mount() entry point
│   ├── client.py            # M365GraphClient implementation
│   ├── config.py            # Configuration loading
│   ├── errors.py            # Exception classes
│   ├── tool.py              # M365GraphTool implementation
│   └── helpers/             # Optional resource-specific helpers
│       ├── __init__.py
│       ├── mail.py          # Email convenience methods
│       ├── calendar.py      # Calendar convenience methods
│       └── files.py         # OneDrive convenience methods
└── tests/
    ├── __init__.py
    ├── test_client.py
    ├── test_tool.py
    └── conftest.py
```

### 6.3 pyproject.toml Examples

**Auth Module**:
```toml
[project]
name = "amplifier-module-tool-m365-auth"
version = "0.1.0"
description = "Microsoft 365 authentication for Amplifier agents"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "amplifier-core>=0.1.0",
    "msal>=1.24.0",
    "aiofiles>=23.0.0",
]

[project.entry-points."amplifier.modules"]
tool-m365-auth = "amplifier_module_tool_m365_auth:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["amplifier_module_tool_m365_auth"]
```

**Graph Module**:
```toml
[project]
name = "amplifier-module-tool-m365-graph"
version = "0.1.0"
description = "Microsoft Graph API tool for Amplifier agents"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "amplifier-core>=0.1.0",
    "amplifier-module-tool-m365-auth>=0.1.0",
    "httpx>=0.25.0",
]

[project.entry-points."amplifier.modules"]
tool-m365-graph = "amplifier_module_tool_m365_graph:mount"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["amplifier_module_tool_m365_graph"]
```

---

## 7. Implementation Sketches

### 7.1 Auth Module Entry Point

```python
# amplifier_module_tool_m365_auth/__init__.py

from typing import Any, Callable
from amplifier_core.models import ToolResult

from .auth import M365AuthProvider
from .config import load_config, AuthConfig
from .tool import M365AuthTool


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> Callable | None:
    """Mount the M365 auth module."""
    
    # Load configuration
    auth_config = load_config(config or {})
    
    # Create auth provider (shared instance)
    auth_provider = M365AuthProvider(auth_config)
    
    # Create tool
    tool = M365AuthTool(auth_provider)
    
    # Register tool
    await coordinator.mount("tools", tool, name="m365_auth")
    
    # Register auth provider as a shared service for other modules
    coordinator.register_contributor(
        "services.m365_auth",
        "tool-m365-auth", 
        lambda: auth_provider
    )
    
    # Return cleanup function
    async def cleanup():
        await auth_provider.close()
    
    return cleanup
```

### 7.2 Auth Provider Implementation

```python
# amplifier_module_tool_m365_auth/auth.py

import msal
from pathlib import Path
from typing import Any

from .config import AuthConfig
from .cache import TokenCache
from .errors import AuthenticationError, AuthenticationCancelledError


class M365AuthProvider:
    """MSAL-based M365 authentication provider."""
    
    def __init__(self, config: AuthConfig):
        self.config = config
        self._cache = TokenCache(config.cache_path)
        self._app: msal.PublicClientApplication | None = None
        self._pending_flow: dict | None = None
    
    @property
    def app(self) -> msal.PublicClientApplication:
        """Lazy-initialize MSAL app."""
        if self._app is None:
            authority = self.config.authority or f"https://login.microsoftonline.com/{self.config.tenant_id}"
            self._app = msal.PublicClientApplication(
                client_id=self.config.client_id,
                authority=authority,
                token_cache=self._cache.msal_cache,
            )
        return self._app
    
    async def get_token(self, scopes: list[str] | None = None) -> dict[str, Any]:
        """Get token, using cache or initiating device code flow."""
        scopes = scopes or self.config.scopes
        
        # Try silent acquisition first
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(scopes, account=accounts[0])
            if result and "access_token" in result:
                return self._to_token_result(result)
        
        # Need interactive auth - use device code flow
        flow = self.app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise AuthenticationError(f"Failed to create device flow: {flow.get('error_description')}")
        
        # Store for potential async completion
        self._pending_flow = flow
        
        # Block and wait for user to complete auth
        result = self.app.acquire_token_by_device_flow(flow)
        
        if "access_token" in result:
            self._cache.save()
            return self._to_token_result(result)
        
        raise AuthenticationError(result.get("error_description", "Authentication failed"))
    
    async def initiate_device_code(self, scopes: list[str] | None = None) -> dict[str, Any]:
        """Start device code flow without blocking."""
        scopes = scopes or self.config.scopes
        
        flow = self.app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise AuthenticationError(f"Failed to create device flow: {flow.get('error_description')}")
        
        self._pending_flow = flow
        
        return {
            "user_code": flow["user_code"],
            "verification_uri": flow["verification_uri"],
            "message": flow["message"],
            "expires_in": flow.get("expires_in", 900),
        }
    
    async def complete_device_code(self, timeout: float = 300) -> dict[str, Any]:
        """Complete pending device code flow."""
        if not self._pending_flow:
            raise AuthenticationError("No pending device code flow")
        
        # MSAL handles polling internally
        result = self.app.acquire_token_by_device_flow(
            self._pending_flow,
            # timeout parameter would need custom implementation
        )
        
        self._pending_flow = None
        
        if "access_token" in result:
            self._cache.save()
            return self._to_token_result(result)
        
        raise AuthenticationError(result.get("error_description", "Authentication failed"))
    
    async def logout(self, account_id: str | None = None) -> None:
        """Remove cached tokens."""
        accounts = self.app.get_accounts()
        
        for account in accounts:
            if account_id is None or account.get("local_account_id") == account_id:
                self.app.remove_account(account)
        
        self._cache.save()
    
    def get_accounts(self) -> list[dict[str, Any]]:
        """List cached accounts."""
        return [
            {
                "username": acc.get("username"),
                "account_id": acc.get("local_account_id"),
                "tenant_id": acc.get("realm"),
            }
            for acc in self.app.get_accounts()
        ]
    
    async def close(self) -> None:
        """Cleanup resources."""
        self._cache.save()
    
    def _to_token_result(self, result: dict) -> dict[str, Any]:
        """Convert MSAL result to our TokenResult format."""
        return {
            "access_token": result["access_token"],
            "expires_on": result.get("expires_in", 3600) + int(time.time()),
            "scopes": result.get("scope", "").split(),
            "account_id": result.get("id_token_claims", {}).get("oid"),
        }
```

### 7.3 Graph Tool Implementation

```python
# amplifier_module_tool_m365_graph/tool.py

from typing import Any
import httpx
from amplifier_core.models import ToolResult

from .config import GraphConfig
from .errors import GraphError


class M365GraphTool:
    """Microsoft Graph API tool for agents."""
    
    def __init__(
        self, 
        config: GraphConfig,
        auth_provider: Any,  # M365AuthProvider from auth module
    ):
        self.config = config
        self.auth = auth_provider
        self._client: httpx.AsyncClient | None = None
    
    @property
    def name(self) -> str:
        return "m365_graph"
    
    @property
    def description(self) -> str:
        return """Make requests to Microsoft Graph API to access M365 data.

Supports: emails, calendar, files, users, groups, and more.
Authentication is handled automatically via device code flow."""
    
    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PATCH", "DELETE"],
                    "default": "GET",
                },
                "endpoint": {
                    "type": "string",
                    "description": "API endpoint, e.g., '/me/messages'",
                },
                "params": {
                    "type": "object",
                    "description": "Query params ($select, $filter, $top)",
                },
                "body": {
                    "type": "object",
                    "description": "Request body for POST/PATCH",
                },
                "paginate": {
                    "type": "boolean",
                    "default": False,
                },
            },
            "required": ["endpoint"],
        }
    
    async def execute(self, input: dict[str, Any]) -> ToolResult:
        """Execute a Graph API request."""
        try:
            # Get authenticated token
            token_result = await self.auth.get_token()
            access_token = token_result["access_token"]
            
            # Build request
            method = input.get("method", "GET").upper()
            endpoint = input["endpoint"]
            params = input.get("params", {})
            body = input.get("body")
            paginate = input.get("paginate", False)
            
            # Ensure endpoint starts with /
            if not endpoint.startswith("/"):
                endpoint = f"/{endpoint}"
            
            url = f"{self.config.base_url}/{self.config.api_version}{endpoint}"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            
            async with httpx.AsyncClient() as client:
                if paginate and method == "GET":
                    # Handle pagination
                    items = await self._get_all_pages(client, url, headers, params)
                    return ToolResult(
                        success=True,
                        output={"items": items, "count": len(items)},
                    )
                else:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=body,
                    )
                    
                    return self._handle_response(response)
        
        except GraphError as e:
            return ToolResult(
                success=False,
                error={"code": e.error_code, "message": str(e)},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"code": "unknown", "message": str(e)},
            )
    
    async def _get_all_pages(
        self, 
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        params: dict,
    ) -> list[dict]:
        """Fetch all pages of results."""
        items = []
        pages = 0
        
        while url and pages < self.config.max_pages:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                raise GraphError(
                    response.status_code,
                    response.json().get("error", {}).get("code", "unknown"),
                    response.json().get("error", {}).get("message", "Request failed"),
                )
            
            data = response.json()
            items.extend(data.get("value", []))
            
            url = data.get("@odata.nextLink")
            params = {}  # nextLink includes params
            pages += 1
        
        return items
    
    def _handle_response(self, response: httpx.Response) -> ToolResult:
        """Convert HTTP response to ToolResult."""
        if response.status_code >= 400:
            error_data = response.json().get("error", {})
            return ToolResult(
                success=False,
                error={
                    "code": error_data.get("code", f"http_{response.status_code}"),
                    "message": error_data.get("message", response.text),
                },
            )
        
        # Success
        if response.status_code == 204:  # No content
            return ToolResult(success=True, output={"status": "success"})
        
        return ToolResult(success=True, output=response.json())
```

---

## 8. Usage Examples

### 8.1 Bundle Configuration

```yaml
# In your bundle.md or mount plan
tools:
  - module: tool-m365-auth
    source: git+https://github.com/microsoft/amplifier-module-tool-m365-auth@v1.0.0
    config:
      client_id: "your-azure-app-client-id"
      tenant_id: "your-tenant.onmicrosoft.com"
      scopes:
        - User.Read
        - Mail.Read
        - Calendars.Read
        - Files.Read.All
        - offline_access

  - module: tool-m365-graph  
    source: git+https://github.com/microsoft/amplifier-module-tool-m365-graph@v1.0.0
```

### 8.2 Agent Interaction

```
User: Show me my unread emails from today

Agent: I'll check your Microsoft 365 emails. First, let me verify authentication.

[Agent calls m365_auth with operation: "status"]

Agent: You're not currently authenticated. I'll start the login process.

[Agent calls m365_auth with operation: "login"]

Agent: Please authenticate using this link:
- Go to: https://microsoft.com/devicelogin
- Enter code: ABCD-1234

[User completes authentication in browser]

Agent: Great, you're now authenticated! Let me fetch your unread emails.

[Agent calls m365_graph with:
  endpoint: "/me/messages"
  params: {
    "$filter": "isRead eq false and receivedDateTime ge 2025-01-16",
    "$select": "subject,from,receivedDateTime",
    "$top": 10
  }
]

Agent: You have 3 unread emails today:
1. "Q1 Planning" from alice@company.com (9:30 AM)
2. "Build Results" from ci@company.com (10:15 AM)  
3. "Lunch?" from bob@company.com (11:45 AM)
```

---

## 9. Testing Strategy

### 9.1 Unit Tests (Mocked)

```python
# tests/test_auth.py

import pytest
from unittest.mock import Mock, patch
from amplifier_module_tool_m365_auth.auth import M365AuthProvider
from amplifier_module_tool_m365_auth.config import AuthConfig


@pytest.fixture
def auth_config():
    return AuthConfig(
        client_id="test-client-id",
        tenant_id="test-tenant",
    )


@pytest.fixture
def mock_msal():
    with patch("msal.PublicClientApplication") as mock:
        yield mock


@pytest.mark.asyncio
async def test_get_token_from_cache(auth_config, mock_msal):
    """Should return cached token without device flow."""
    mock_app = mock_msal.return_value
    mock_app.get_accounts.return_value = [{"username": "test@test.com"}]
    mock_app.acquire_token_silent.return_value = {
        "access_token": "cached-token",
        "expires_in": 3600,
    }
    
    provider = M365AuthProvider(auth_config)
    result = await provider.get_token()
    
    assert result["access_token"] == "cached-token"
    mock_app.initiate_device_flow.assert_not_called()


@pytest.mark.asyncio  
async def test_device_code_flow(auth_config, mock_msal):
    """Should initiate device code when no cached token."""
    mock_app = mock_msal.return_value
    mock_app.get_accounts.return_value = []
    mock_app.acquire_token_silent.return_value = None
    mock_app.initiate_device_flow.return_value = {
        "user_code": "TEST-CODE",
        "verification_uri": "https://microsoft.com/devicelogin",
        "message": "Go to URL and enter code",
    }
    mock_app.acquire_token_by_device_flow.return_value = {
        "access_token": "new-token",
        "expires_in": 3600,
    }
    
    provider = M365AuthProvider(auth_config)
    result = await provider.get_token()
    
    assert result["access_token"] == "new-token"
    mock_app.initiate_device_flow.assert_called_once()
```

### 9.2 Integration Tests (Real Azure AD)

```python
# tests/integration/test_real_auth.py
# Run with: pytest tests/integration/ --run-integration

import pytest
import os


@pytest.fixture
def real_config():
    """Requires M365_CLIENT_ID and M365_TENANT_ID env vars."""
    client_id = os.environ.get("M365_CLIENT_ID")
    if not client_id:
        pytest.skip("M365_CLIENT_ID not set")
    
    return AuthConfig(
        client_id=client_id,
        tenant_id=os.environ.get("M365_TENANT_ID", "common"),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_device_code_flow(real_config):
    """Manual test - requires human interaction."""
    provider = M365AuthProvider(real_config)
    
    # This will print device code info
    info = await provider.initiate_device_code()
    print(f"\n\nGo to: {info['verification_uri']}")
    print(f"Enter code: {info['user_code']}\n")
    
    # Wait for user to complete
    result = await provider.complete_device_code(timeout=120)
    
    assert "access_token" in result
```

---

## 10. Open Questions & Future Considerations

### 10.1 Deferred Decisions

| Question | Current Decision | Reconsider When |
|----------|-----------------|-----------------|
| Certificate auth? | No - device code only | Enterprise deployment needs |
| Multi-tenant switching? | Single tenant at a time | Multi-org users request it |
| Batch requests? | Not in v1 | Performance issues emerge |
| Webhook support? | Not in v1 | Real-time scenarios needed |

### 10.2 Extension Points

The design allows future modules like:
- `tool-m365-teams` - Teams-specific operations
- `tool-m365-sharepoint` - SharePoint document management
- `hook-m365-audit` - Audit logging for compliance

These would use the same `tool-m365-auth` provider.

---

## Appendix A: Azure App Registration Setup

To use these modules, you need an Azure AD app registration:

1. Go to [Azure Portal](https://portal.azure.com) > Azure Active Directory > App registrations
2. Click "New registration"
3. Configure:
   - Name: "Amplifier M365 Integration"
   - Supported account types: Choose based on your needs
   - Redirect URI: Leave blank (device code flow doesn't need it)
4. After creation, note the **Application (client) ID**
5. Go to "API permissions" > "Add a permission" > "Microsoft Graph"
6. Add delegated permissions: User.Read, Mail.Read, etc.
7. Grant admin consent if required by your organization

**No client secret is needed** - device code flow uses public client authentication.

---

## Appendix B: Related Documents

- [Tool Contract](amplifier-core/docs/contracts/TOOL_CONTRACT.md)
- [Module Development Guide](amplifier/docs/MODULE_DEVELOPMENT.md)
- [Kernel Philosophy](amplifier-foundation/context/KERNEL_PHILOSOPHY.md)
- [MSAL Python Documentation](https://msal-python.readthedocs.io/)
- [Microsoft Graph API Reference](https://learn.microsoft.com/en-us/graph/api/overview)
