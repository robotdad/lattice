---
bundle:
  name: m365
  version: 0.1.0
  description: Microsoft 365 integration for Amplifier agents

tools:
  # M365 Authentication - Device code flow, token management
  - module: tool-m365-auth
    source: file://../amplifier-module-tool-m365-auth
    config:
      # Client ID from Azure App Registration - set via M365_CLIENT_ID env var
      # Tenant ID - set via M365_TENANT_ID env var (optional, defaults to "common")
      scopes:
        - User.Read
        - Mail.Read
        - Mail.Send
        - Calendars.Read
        - Calendars.ReadWrite
        - Files.Read.All
        - Directory.Read.All
        - offline_access

  # Microsoft Graph API - Make authenticated requests
  - module: tool-m365-graph
    source: file://../amplifier-module-tool-m365-graph
    config:
      api_version: v1.0
      default_page_size: 50
      max_pages: 10
---

# Microsoft 365 Integration

This bundle provides tools to authenticate with and interact with Microsoft 365 services via the Microsoft Graph API.

## Available Tools

### m365_auth

Manage authentication with Microsoft 365:

| Operation | Description |
|-----------|-------------|
| `login` | Start device code authentication flow |
| `status` | Check current authentication status |
| `logout` | Clear cached credentials |
| `accounts` | List authenticated accounts |

### m365_graph

Make requests to Microsoft Graph API:

| Parameter | Description |
|-----------|-------------|
| `endpoint` | Graph API endpoint (e.g., `/me`, `/me/messages`) |
| `method` | HTTP method: GET, POST, PATCH, DELETE |
| `params` | Query parameters ($select, $filter, $top, etc.) |
| `body` | Request body for POST/PATCH |
| `paginate` | Auto-follow pagination (default: false) |

## Quick Start

1. **Set environment variables**:
   ```bash
   export M365_CLIENT_ID=your-azure-app-client-id
   export M365_TENANT_ID=your-tenant-id  # optional
   ```

2. **Authenticate** - The agent will prompt you to log in when M365 access is needed

3. **Use M365 services** - Ask the agent to read emails, check calendar, etc.

@m365:context/m365-instructions.md
