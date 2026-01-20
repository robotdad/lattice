---
bundle:
  name: m365-dev
  version: 0.1.0
  description: M365 development workspace - combines amplifier-dev for iteration with M365 integration tools

includes:
  # Amplifier development bundle (includes foundation, python-dev, shadow, recipes)
  - bundle: file://amplifier-foundation/bundles/amplifier-dev.yaml
  
  # M365 integration tools
  - bundle: file://amplifier-bundle-m365
---

# M365 Development Workspace

This workspace is configured for developing and testing Microsoft 365 integration with Amplifier.

## Available Capabilities

### From amplifier-dev
- Full foundation toolset (bash, file ops, web, etc.)
- Python development tools (python_check, LSP)
- Shadow environments for isolated testing
- Recipes for multi-step workflows
- Git operations

### From M365 bundle
- `m365_auth` - Device code authentication with Microsoft Entra ID
- `m365_graph` - Microsoft Graph API requests

## Quick Start

```bash
# Set credentials (or source the env file)
source ai_working/m365_credentials.env

# Run with this bundle
amplifier run --bundle bundle.md
```

## Development Workflow

1. Make changes to modules in `amplifier-module-tool-m365-*`
2. Test in shadow environment
3. Iterate until working
4. Use for real M365 operations

@m365-dev:ai_working/M365_SETUP_STATUS.md
