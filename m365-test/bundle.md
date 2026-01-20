---
bundle:
  name: m365-test
  version: 0.1.0
  description: M365 integration testing workspace

includes:
  # Base foundation 
  - bundle: foundation

tools:
  # M365 Authentication
  - module: tool-m365-auth
    source: file://../amplifier-module-tool-m365-auth
    config:
      scopes:
        - User.Read
        - Mail.Read
        - Mail.Send
        - Calendars.Read
        - Calendars.ReadWrite
        - Files.Read.All
        - Directory.Read.All
        - offline_access

  # Microsoft Graph API
  - module: tool-m365-graph
    source: file://../amplifier-module-tool-m365-graph
    config:
      api_version: v1.0
---

# M365 Test Environment

Test workspace for M365 integration.

## Tools Available

- `m365_auth` - Authenticate with Microsoft Entra ID
- `m365_graph` - Make Graph API requests
