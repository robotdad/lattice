# Lattice

> "A lot of people don't realize what's really going on. They view life as a bunch of unconnected incidents and things. They don't realize that there's this lattice of coincidence that lies on top of everything."
> 
> — Miller, *Repo Man* (1984)

**Multi-agent collaboration via Microsoft 365 infrastructure.**

---

## ⚠️ Experimental

**This project is experimental and under active development.**

- APIs will change without notice
- Security has not been audited
- Not suitable for production use
- Built for learning and exploration

Use at your own risk. This is a proof-of-concept exploring how AI agents can collaborate using M365 as a communication backbone.

---

## What Is This?

Lattice enables multiple [Amplifier](https://github.com/microsoft/amplifier) AI agent sessions to collaborate using Microsoft 365 services:

- **Email** for task assignments and responses between agents
- **SharePoint** for shared file storage and artifacts
- **Groups** for broadcast communications

Think of it as giving your AI agents their own office—complete with email, shared drives, and the ability to delegate work to each other.

### The Repo Man Crew

The project uses a whimsical theme inspired by the 1984 cult film *Repo Man*. Agents are named after characters:

| Agent | Role | Purpose |
|-------|------|---------|
| Plettschner | Director of Lot Operations | Orchestrator, task assignment |
| Bud | Senior Repo Man | Code review, architecture |
| Otto | Repo Man | Implementation |
| Lite | Repo Man | Parallel tasks |
| Miller | Mechanic | Research, investigation |
| Leila | United Fruitcake Outlet | Documentation |

Each agent has their own M365 identity (email, calendar, OneDrive) and can communicate with other agents programmatically.

---

## Components

```
lattice/
├── amplifier-bundle-m365/       # Amplifier bundle for M365 integration
│   ├── bundle.md                # Bundle definition
│   └── m365_agent.py            # Agent communication library
├── amplifier-module-tool-m365-auth/   # Authentication tool module
├── amplifier-module-tool-m365-graph/  # Graph API tool module
├── ai_working/                  # Working documents and templates
│   ├── AGENT_PROTOCOL.md        # Communication protocol spec
│   └── *.env.template           # Credential templates
└── M365_INTEGRATION_DESIGN.md   # Original design document
```

---

## Prerequisites

- Python 3.11+
- An M365 tenant (test/dev tenant recommended)
- Azure AD app registration with delegated permissions
- [Amplifier](https://github.com/microsoft/amplifier) installed

### Required M365 Permissions

Your app registration needs these **delegated** permissions with admin consent:

- `User.Read`
- `Mail.Read`
- `Mail.Send`
- `Files.ReadWrite.All`
- `Sites.ReadWrite.All`
- `Group.ReadWrite.All`

### Required Tenant Configuration

For programmatic username/password authentication (ROPC flow):

1. Create user accounts for each agent
2. Disable MFA for those accounts (via Conditional Access exclusion)
3. Enable "Allow public client flows" on the app registration

---

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_ORG/lattice.git
cd lattice
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install msal httpx
```

### 3. Configure Credentials

Copy the template files and fill in your values:

```bash
cp ai_working/m365_credentials.env.template ai_working/m365_credentials.env
cp ai_working/repo_man_crew.env.template ai_working/repo_man_crew.env
```

Edit the `.env` files with your tenant details and user passwords.

**Never commit `.env` files!** They are excluded via `.gitignore`.

### 4. Test Authentication

```python
from m365_agent import RepoManAgent

agent = RepoManAgent("plettschner", "ai_working")
print(agent.whoami())
```

---

## Usage

### Basic Agent Communication

```python
from m365_agent import RepoManAgent, Task, TaskResponse

# Create agents
plettschner = RepoManAgent("plettschner", "ai_working")
otto = RepoManAgent("otto", "ai_working")

# Plettschner assigns a task
task = plettschner.create_task(
    description="Investigate the anomaly",
    context="Something weird in sector 7",
    deliverable="Written report"
)
plettschner.send_task("otto", task)

# Otto uploads results and responds
otto.upload_artifact("Reports/investigation.txt", report_content)
otto.respond_to_task(task.task_id, response, to_agent="plettschner")

# Broadcast to all agents
plettschner.broadcast("Status Update", "Investigation complete.")
```

### Available Methods

| Method | Description |
|--------|-------------|
| `create_task()` | Create a new task with generated ID |
| `send_task(to_agent, task)` | Send task assignment via email |
| `respond_to_task(task_id, response)` | Send task response |
| `check_inbox()` | Check for new messages/tasks |
| `broadcast(subject, message)` | Send to group mailbox |
| `upload_artifact(path, content)` | Upload file to SharePoint |
| `download_artifact(path)` | Download file from SharePoint |
| `list_artifacts(folder)` | List files in SharePoint folder |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Amplifier Sessions                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │Plettschner│  │   Bud    │  │   Otto   │  │  Miller  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
└───────┼─────────────┼─────────────┼─────────────┼──────────┘
        │             │             │             │
        ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Microsoft 365 Tenant                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │    Email    │  │ SharePoint  │  │   M365 Group        │ │
│  │  (tasks &   │  │  (shared    │  │  (broadcasts &      │ │
│  │  responses) │  │   files)    │  │   group mail)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Considerations

**This is experimental software. Security has NOT been audited.**

Known concerns:

- Uses ROPC (Resource Owner Password Credentials) flow—not recommended for production
- Passwords stored in local `.env` files
- MFA disabled for agent accounts
- No encryption of inter-agent communications
- Token caching not hardened

For production use, consider:

- Managed identities or certificate-based auth
- Azure Key Vault for secrets
- Conditional Access policies
- Audit logging
- Data Loss Prevention policies

---

## License

MIT License - See LICENSE file.

---

## Acknowledgments

- [Amplifier](https://github.com/microsoft/amplifier) - The AI agent framework
- [Repo Man](https://en.wikipedia.org/wiki/Repo_Man_(film)) - For the inspiration and the philosophy

*"The life of a repo man is always intense."*
