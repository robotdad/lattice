"""
M365 Agent Communication Library

Enables Amplifier agents to collaborate via M365 infrastructure:
- Email for task assignments and responses
- SharePoint for file sharing
- Group mailbox for broadcasts
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import msal


@dataclass
class AgentIdentity:
    """An agent's M365 identity."""

    agent_id: str
    email: str
    password: str
    display_name: str
    role: str


@dataclass
class Task:
    """A task assignment between agents."""

    task_id: str
    from_agent: str
    to_agent: str
    description: str
    context: str = ""
    deliverable: str = ""
    priority: str = "normal"
    input_files: list[str] = field(default_factory=list)
    output_folder: str = ""
    deadline: str | None = None


@dataclass
class TaskResponse:
    """Response to a task."""

    task_id: str
    from_agent: str
    status: str  # completed, failed, blocked
    summary: str
    details: str = ""
    artifacts_created: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


class RepoManAgent:
    """
    M365-enabled agent for the Repo Man crew.

    Provides communication primitives for multi-agent collaboration.
    """

    TENANT_ID = "16f9353b-6b50-4fc6-b228-70870adaf580"
    CLIENT_ID = "760968bf-bbb6-423f-bff0-837057851664"
    GROUP_ID = "a7b8e399-b8a2-4af9-9dc3-307703f1f770"
    GROUP_EMAIL = "the-lot@M365x93789909.onmicrosoft.com"
    SHAREPOINT_SITE = "https://m365x93789909.sharepoint.com/sites/the-lot"

    # Agent roster
    AGENTS = {
        "plettschner": AgentIdentity(
            agent_id="plettschner",
            email="Plettschner@M365x93789909.onmicrosoft.com",
            password="",  # Loaded from env
            display_name="Plettschner",
            role="Director of Lot Operations",
        ),
        "bud": AgentIdentity(
            agent_id="bud",
            email="GradyA@M365x93789909.OnMicrosoft.com",
            password="",
            display_name="Bud",
            role="Senior Repo Man",
        ),
        "otto": AgentIdentity(
            agent_id="otto",
            email="AlexW@M365x93789909.OnMicrosoft.com",
            password="",
            display_name="Otto",
            role="Repo Man",
        ),
        "lite": AgentIdentity(
            agent_id="lite",
            email="LeeG@M365x93789909.OnMicrosoft.com",
            password="",
            display_name="Lite",
            role="Repo Man",
        ),
        "miller": AgentIdentity(
            agent_id="miller",
            email="NestorW@M365x93789909.OnMicrosoft.com",
            password="",
            display_name="Miller",
            role="Mechanic",
        ),
        "leila": AgentIdentity(
            agent_id="leila",
            email="LidiaH@M365x93789909.OnMicrosoft.com",
            password="",
            display_name="Leila",
            role="United Fruitcake Outlet",
        ),
    }

    def __init__(self, agent_id: str, credentials_dir: str | Path | None = None):
        """
        Initialize agent with M365 identity.

        Args:
            agent_id: One of the crew (plettschner, bud, otto, lite, miller, leila)
            credentials_dir: Path to directory containing credential env files
        """
        if agent_id not in self.AGENTS:
            raise ValueError(
                f"Unknown agent: {agent_id}. Must be one of {list(self.AGENTS.keys())}"
            )

        self.agent_id = agent_id
        self.identity = self.AGENTS[agent_id]
        self._token: str | None = None
        self._token_expires: datetime | None = None

        # Load credentials
        if credentials_dir:
            self._load_credentials(Path(credentials_dir))
        else:
            # Try default locations
            for path in [Path("ai_working"), Path.home() / ".amplifier" / "m365"]:
                if path.exists():
                    self._load_credentials(path)
                    break

    def _load_credentials(self, creds_dir: Path) -> None:
        """Load credentials from env files."""
        # Load main credentials
        main_creds = creds_dir / "m365_credentials.env"
        if main_creds.exists():
            self._parse_env_file(main_creds)

        # Load Plettschner credentials
        plett_creds = creds_dir / "plettschner_creds.env"
        if plett_creds.exists():
            content = plett_creds.read_text()
            for line in content.splitlines():
                if "PLETTSCHNER_PASSWORD" in line and "=" in line:
                    password = line.split("=", 1)[1].strip().strip('"')
                    self.AGENTS["plettschner"].password = password

        # Load crew credentials
        crew_creds = creds_dir / "repo_man_crew.env"
        if crew_creds.exists():
            content = crew_creds.read_text()
            for line in content.splitlines():
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"')

                    # Map env var to agent
                    if key == "BUD_PASSWORD":
                        self.AGENTS["bud"].password = val
                    elif key == "OTTO_PASSWORD":
                        self.AGENTS["otto"].password = val
                    elif key == "LITE_PASSWORD":
                        self.AGENTS["lite"].password = val
                    elif key == "MILLER_PASSWORD":
                        self.AGENTS["miller"].password = val
                    elif key == "LEILA_PASSWORD":
                        self.AGENTS["leila"].password = val

        # Update our identity with loaded password
        self.identity = self.AGENTS[self.agent_id]

    def _parse_env_file(self, path: Path) -> dict[str, str]:
        """Parse an env file into a dict."""
        result = {}
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                result[key.strip()] = val.strip().strip('"')
        return result

    def _get_token(self, scopes: list[str] | None = None) -> str:
        """Get an access token, refreshing if needed."""
        if scopes is None:
            scopes = [
                "User.Read",
                "Mail.Read",
                "Mail.Send",
                "Files.ReadWrite.All",
                "Sites.ReadWrite.All",
                "Group.ReadWrite.All",
            ]

        authority = f"https://login.microsoftonline.com/{self.TENANT_ID}"
        app = msal.PublicClientApplication(self.CLIENT_ID, authority=authority)

        result = app.acquire_token_by_username_password(
            self.identity.email, self.identity.password, scopes=scopes
        )

        if "access_token" not in result:
            raise RuntimeError(
                f"Authentication failed: {result.get('error_description', 'Unknown error')}"
            )

        return result["access_token"]

    @property
    def token(self) -> str:
        """Get a valid access token."""
        if self._token is None:
            self._token = self._get_token()
        return self._token

    def _graph_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        content: bytes | None = None,
        content_type: str = "application/json",
    ) -> httpx.Response:
        """Make a request to the Graph API."""
        url = f"https://graph.microsoft.com/v1.0{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}"}

        if json_data:
            headers["Content-Type"] = "application/json"
            return httpx.request(method, url, headers=headers, json=json_data)
        elif content:
            headers["Content-Type"] = content_type
            return httpx.request(method, url, headers=headers, content=content)
        else:
            return httpx.request(method, url, headers=headers)

    # ===== Email Operations =====

    def send_task(self, to_agent: str, task: Task) -> bool:
        """
        Send a task assignment to another agent.

        Args:
            to_agent: Agent ID to send to
            task: Task details

        Returns:
            True if sent successfully
        """
        if to_agent not in self.AGENTS:
            raise ValueError(f"Unknown agent: {to_agent}")

        to_email = self.AGENTS[to_agent].email

        # Build the task message
        task_data = {
            "protocol": "repo-man-v1",
            "type": "task",
            "task_id": task.task_id,
            "from_agent": self.agent_id,
            "priority": task.priority,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "task": {
                "description": task.description,
                "context": task.context,
                "deliverable": task.deliverable,
                "deadline": task.deadline,
            },
            "artifacts": {
                "input_files": task.input_files,
                "output_folder": task.output_folder,
            },
        }

        body = f"""Task Assignment from {self.identity.display_name}

{task.description}

Context: {task.context}

Deliverable: {task.deliverable}

Priority: {task.priority}

---
Machine-readable task data:
```json
{json.dumps(task_data, indent=2)}
```
"""

        email = {
            "message": {
                "subject": f"[TASK:{task.task_id}] {task.description[:50]}",
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            },
            "saveToSentItems": "true",
        }

        resp = self._graph_request("POST", "/me/sendMail", json_data=email)
        return resp.status_code == 202

    def respond_to_task(
        self,
        task_id: str,
        response: TaskResponse,
        to_agent: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> bool:
        """
        Send a response to a task.

        Args:
            task_id: The task being responded to
            response: Response details
            to_agent: Agent ID to respond to (skips inbox search)
            reply_to_message_id: Optional message ID to reply to

        Returns:
            True if sent successfully
        """
        to_email = None

        # If to_agent specified, use their email directly
        if to_agent and to_agent in self.AGENTS:
            to_email = self.AGENTS[to_agent].email
        else:
            # Try to find the original task email to get the sender
            messages = self.check_inbox(filter_tasks=True)
            for msg in messages:
                if msg.get("task_id") == task_id:
                    to_email = msg["from_email"]
                    break

        if not to_email:
            raise ValueError(
                f"Could not find recipient for task: {task_id}. Specify to_agent."
            )

        response_data = {
            "protocol": "repo-man-v1",
            "type": "response",
            "task_id": task_id,
            "from_agent": self.agent_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": response.status,
            "result": {
                "summary": response.summary,
                "details": response.details,
                "artifacts_created": response.artifacts_created,
            },
            "issues": response.issues,
        }

        body = f"""Task Response from {self.identity.display_name}

Status: {response.status.upper()}

{response.summary}

{response.details}

Artifacts created: {", ".join(response.artifacts_created) if response.artifacts_created else "None"}

Issues: {", ".join(response.issues) if response.issues else "None"}

---
Machine-readable response:
```json
{json.dumps(response_data, indent=2)}
```
"""

        email = {
            "message": {
                "subject": f"RE: [TASK:{task_id}] Response: {response.status}",
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            },
            "saveToSentItems": "true",
        }

        resp = self._graph_request("POST", "/me/sendMail", json_data=email)
        return resp.status_code == 202

    def check_inbox(
        self, filter_tasks: bool = False, unread_only: bool = False, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Check inbox for messages.

        Args:
            filter_tasks: Only return task-related messages
            unread_only: Only return unread messages
            limit: Maximum messages to return

        Returns:
            List of message dicts with parsed task data if applicable
        """
        params = {
            "$top": str(limit),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,body,receivedDateTime,isRead",
        }

        if unread_only:
            params["$filter"] = "isRead eq false"

        resp = self._graph_request(
            "GET", f"/me/messages?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        )

        if resp.status_code != 200:
            return []

        messages = []
        for msg in resp.json().get("value", []):
            parsed = {
                "id": msg.get("id"),
                "subject": msg.get("subject", ""),
                "from_name": msg.get("from", {})
                .get("emailAddress", {})
                .get("name", ""),
                "from_email": msg.get("from", {})
                .get("emailAddress", {})
                .get("address", ""),
                "received": msg.get("receivedDateTime", ""),
                "is_read": msg.get("isRead", False),
                "body": msg.get("body", {}).get("content", ""),
            }

            # Try to parse task data from body
            subject = parsed["subject"]
            if "[TASK:" in subject:
                # Extract task ID
                start = subject.find("[TASK:") + 6
                end = subject.find("]", start)
                if end > start:
                    parsed["task_id"] = subject[start:end]
                    parsed["is_task"] = True

                    # Try to parse JSON from body
                    body = parsed["body"]
                    if "```json" in body:
                        json_start = body.find("```json") + 7
                        json_end = body.find("```", json_start)
                        if json_end > json_start:
                            try:
                                parsed["task_data"] = json.loads(
                                    body[json_start:json_end]
                                )
                            except json.JSONDecodeError:
                                pass
            else:
                parsed["is_task"] = False

            if filter_tasks and not parsed.get("is_task"):
                continue

            messages.append(parsed)

        return messages

    def broadcast(self, subject: str, message: str) -> bool:
        """
        Send a message to the group mailbox (all crew).

        Args:
            subject: Email subject
            message: Message body

        Returns:
            True if sent successfully
        """
        email = {
            "message": {
                "subject": f"[STATUS] {self.identity.display_name}: {subject}",
                "body": {"contentType": "Text", "content": message},
                "toRecipients": [{"emailAddress": {"address": self.GROUP_EMAIL}}],
            },
            "saveToSentItems": "true",
        }

        resp = self._graph_request("POST", "/me/sendMail", json_data=email)
        return resp.status_code == 202

    # ===== File Operations =====

    def upload_artifact(
        self, path: str, content: str | bytes, content_type: str = "text/plain"
    ) -> str | None:
        """
        Upload a file to the shared SharePoint site.

        Args:
            path: Path within Shared Documents (e.g., "Repos/task-123/output.txt")
            content: File content
            content_type: MIME type

        Returns:
            Web URL of uploaded file, or None on failure
        """
        if isinstance(content, str):
            content = content.encode("utf-8")

        endpoint = f"/groups/{self.GROUP_ID}/drive/root:/{path}:/content"
        resp = self._graph_request(
            "PUT", endpoint, content=content, content_type=content_type
        )

        if resp.status_code in [200, 201]:
            return resp.json().get("webUrl")
        return None

    def download_artifact(self, path: str) -> str | None:
        """
        Download a file from the shared SharePoint site.

        Args:
            path: Path within Shared Documents

        Returns:
            File content as string, or None if not found
        """
        # First get the download URL
        endpoint = f"/groups/{self.GROUP_ID}/drive/root:/{path}"
        resp = self._graph_request("GET", endpoint)

        if resp.status_code != 200:
            return None

        download_url = resp.json().get("@microsoft.graph.downloadUrl")
        if not download_url:
            return None

        # Download the content
        content_resp = httpx.get(download_url)
        if content_resp.status_code == 200:
            return content_resp.text
        return None

    def list_artifacts(self, folder: str = "") -> list[dict[str, Any]]:
        """
        List files in a SharePoint folder.

        Args:
            folder: Folder path within Shared Documents (empty for root)

        Returns:
            List of file/folder info dicts
        """
        if folder:
            endpoint = f"/groups/{self.GROUP_ID}/drive/root:/{folder}:/children"
        else:
            endpoint = f"/groups/{self.GROUP_ID}/drive/root/children"

        resp = self._graph_request("GET", endpoint)

        if resp.status_code != 200:
            return []

        items = []
        for item in resp.json().get("value", []):
            items.append(
                {
                    "name": item.get("name"),
                    "path": f"{folder}/{item.get('name')}"
                    if folder
                    else item.get("name"),
                    "is_folder": "folder" in item,
                    "size": item.get("size", 0),
                    "modified": item.get("lastModifiedDateTime", ""),
                    "web_url": item.get("webUrl", ""),
                }
            )

        return items

    def create_folder(self, path: str) -> bool:
        """
        Create a folder in SharePoint.

        Args:
            path: Folder path to create

        Returns:
            True if created successfully
        """
        # Split path to get parent and folder name
        parts = path.rsplit("/", 1)
        if len(parts) == 2:
            parent, name = parts
            endpoint = f"/groups/{self.GROUP_ID}/drive/root:/{parent}:/children"
        else:
            name = parts[0]
            endpoint = f"/groups/{self.GROUP_ID}/drive/root/children"

        resp = self._graph_request(
            "POST",
            endpoint,
            json_data={
                "name": name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename",
            },
        )

        return resp.status_code == 201

    # ===== Convenience Methods =====

    def create_task(self, description: str, **kwargs) -> Task:
        """Create a new task with a generated ID."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        return Task(
            task_id=task_id,
            from_agent=self.agent_id,
            to_agent=kwargs.get("to_agent", ""),
            description=description,
            **{k: v for k, v in kwargs.items() if k != "to_agent"},
        )

    def whoami(self) -> dict[str, str]:
        """Get info about current agent identity."""
        return {
            "agent_id": self.agent_id,
            "email": self.identity.email,
            "display_name": self.identity.display_name,
            "role": self.identity.role,
        }


def create_agent(agent_id: str) -> RepoManAgent:
    """
    Factory function to create an agent.

    Args:
        agent_id: One of: plettschner, bud, otto, lite, miller, leila

    Returns:
        Configured RepoManAgent
    """
    return RepoManAgent(agent_id)
