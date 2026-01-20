# Repo Man Agent Communication Protocol

## Overview

Multiple Amplifier sessions can collaborate using M365 infrastructure:
- **Email** for task assignments and status updates
- **SharePoint** for shared files and artifacts
- **Group mailbox** (the-lot@) for broadcast announcements

## Agent Identities

| Agent ID | Email | Role |
|----------|-------|------|
| plettschner | Plettschner@M365x93789909.onmicrosoft.com | Orchestrator, task assignment |
| bud | GradyA@M365x93789909.OnMicrosoft.com | Senior reviewer, architecture |
| otto | AlexW@M365x93789909.OnMicrosoft.com | Implementation worker |
| lite | LeeG@M365x93789909.OnMicrosoft.com | Parallel worker |
| miller | NestorW@M365x93789909.OnMicrosoft.com | Research, investigation |
| leila | LidiaH@M365x93789909.OnMicrosoft.com | Documentation, communications |

## Message Protocol

### Task Assignment (Email)

Subject line format: `[TASK:<task_id>] <brief description>`

Body format (JSON in code block):
```json
{
  "protocol": "repo-man-v1",
  "type": "task",
  "task_id": "unique-task-id",
  "from_agent": "plettschner",
  "priority": "normal|high|urgent",
  "task": {
    "description": "What needs to be done",
    "context": "Background information",
    "deliverable": "What to produce",
    "deadline": "ISO timestamp or null"
  },
  "artifacts": {
    "input_files": ["SharePoint paths to input files"],
    "output_folder": "SharePoint path for results"
  }
}
```

### Task Response (Email Reply)

Subject: `RE: [TASK:<task_id>] <brief description>`

Body format:
```json
{
  "protocol": "repo-man-v1",
  "type": "response",
  "task_id": "matching-task-id",
  "from_agent": "otto",
  "status": "completed|failed|blocked",
  "result": {
    "summary": "Brief summary of what was done",
    "details": "Detailed explanation",
    "artifacts_created": ["SharePoint paths to output files"]
  },
  "issues": ["Any problems encountered"]
}
```

### Status Update (Email to Group)

To: the-lot@M365x93789909.onmicrosoft.com
Subject: `[STATUS] <agent_id>: <brief update>`

### File Sharing (SharePoint)

Base URL: `https://m365x93789909.sharepoint.com/sites/the-lot/Shared Documents`

Folder conventions:
- `/Repos/<task_id>/` - Working files for a specific task
- `/Intel/` - Research and investigation findings
- `/Operations/` - Operational documents and procedures
- `/Handoffs/` - Files being passed between agents

## Workflow Example

1. **Plettschner** creates task, uploads input to SharePoint, sends email to **Otto**
2. **Otto** reads task, processes, uploads results to SharePoint
3. **Otto** replies with completion status and artifact locations
4. **Plettschner** reads response, retrieves artifacts, assigns review to **Bud**
5. **Bud** reviews, sends feedback
6. **Plettschner** broadcasts status update to group

## Implementation

The `m365_agent` module provides:
- `send_task(to_agent, task)` - Send a task assignment
- `check_inbox()` - Check for new tasks/responses  
- `respond_to_task(task_id, result)` - Send task response
- `upload_artifact(path, content)` - Upload to SharePoint
- `download_artifact(path)` - Download from SharePoint
- `broadcast(message)` - Send to group mailbox
