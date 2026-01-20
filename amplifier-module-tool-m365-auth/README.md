# amplifier-module-tool-m365-auth

Microsoft 365 authentication module for Amplifier agents using MSAL device code flow.

## Features

- Device code authentication flow for M365/Azure AD
- Token caching and refresh
- Support for Microsoft Graph API scopes

## Installation

```bash
uv pip install amplifier-module-tool-m365-auth
```

## Configuration

Set the following environment variables:

- `M365_CLIENT_ID` - Azure AD application (client) ID
- `M365_TENANT_ID` - Azure AD tenant ID

## Usage

```python
from amplifier_module_tool_m365_auth import mount

# Mount registers the authentication tools with the agent
```
