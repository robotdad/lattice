"""
Agent runner - executes tasks as specific agents using Amplifier.

Each agent has its own persona and can perform actions like creating
documents, posting to Teams, etc.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# Add word skill to path
sys.path.insert(0, str(Path.home() / ".amplifier/skills/word"))


class AgentRunner:
    """Runs tasks as a specific agent persona."""
    
    def __init__(self, agent_name: str, agent_email: str = None):
        self.agent_name = agent_name.lower()
        self.agent_email = agent_email or f"{agent_name}@M365x93789909.onmicrosoft.com"
        
        # Load agent definition
        def_path = Path(__file__).parent / "definitions" / f"{self.agent_name}.md"
        if def_path.exists():
            self.definition = def_path.read_text()
        else:
            self.definition = f"You are {agent_name}."
        
        # Load credentials
        creds_path = Path(__file__).parent / "credentials.json"
        with open(creds_path) as f:
            self.creds = json.load(f)
        
        self.client_id = "760968bf-bbb6-423f-bff0-837057851664"
        self.client_secret = self.creds["_app"]["client_secret"]
        self.tenant_id = "16f9353b-6b50-4fc6-b228-70870adaf580"
    
    def get_token(self) -> str:
        """Get access token for this agent."""
        import httpx
        
        password = self.creds.get(self.agent_name, {}).get("password")
        if not password:
            raise ValueError(f"No password for agent {self.agent_name}")
        
        response = httpx.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "scope": "https://graph.microsoft.com/.default",
                "client_secret": self.client_secret,
                "grant_type": "password",
                "username": self.agent_email,
                "password": password,
            },
        )
        
        data = response.json()
        if "access_token" not in data:
            raise RuntimeError(f"Token failed: {data.get('error_description', data)}")
        
        return data["access_token"]
    
    def create_document(self, title: str, content: list) -> Path:
        """Create a Word document."""
        from scripts import DocumentBuilder
        
        doc = DocumentBuilder()
        
        for item in content:
            item_type = item.get("type", "paragraph")
            
            if item_type == "heading":
                doc.add_heading(item["text"], level=item.get("level", 1))
            elif item_type == "paragraph":
                doc.add_paragraph(
                    item["text"],
                    bold=item.get("bold", False),
                    italic=item.get("italic", False)
                )
            elif item_type == "list":
                doc.add_list(item["items"], numbered=item.get("numbered", False))
            elif item_type == "page_break":
                doc.add_page_break()
        
        # Save to documents folder
        docs_dir = Path(__file__).parent.parent / "documents"
        docs_dir.mkdir(exist_ok=True)
        
        filename = title.replace(" ", "_").replace("'", "") + ".docx"
        output_path = docs_dir / filename
        doc.save(str(output_path), overwrite=True)
        
        return output_path
    
    def upload_to_sharepoint(self, file_path: Path, dest_name: str = None) -> dict:
        """Upload a file to SharePoint."""
        import httpx
        
        token = self.get_token()
        site_id = "m365x93789909.sharepoint.com,334abb14-2b00-49d5-a9ef-b17217dd5ef3,9ffc515a-4013-476f-b6da-9f96e1938d12"
        
        dest_name = dest_name or file_path.name
        content = file_path.read_bytes()
        
        # Determine content type
        if dest_name.endswith(".docx"):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content_type = "application/octet-stream"
        
        response = httpx.put(
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/Shared%20Documents/{dest_name}:/content",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
            },
            content=content,
            timeout=60.0,
        )
        
        result = response.json()
        if "error" in result:
            raise RuntimeError(f"Upload failed: {result['error']['message']}")
        
        # Create sharing link
        item_id = result["id"]
        share_response = httpx.post(
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{item_id}/createLink",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"type": "view", "scope": "organization"},
            timeout=60.0,
        )
        
        share_result = share_response.json()
        share_url = share_result.get("link", {}).get("webUrl", result.get("webUrl"))
        
        return {
            "web_url": result.get("webUrl"),
            "share_url": share_url,
            "id": item_id,
            "name": result.get("name"),
        }
    
    def run_task(self, task_description: str) -> str:
        """
        Run a task as this agent using Amplifier.
        
        The agent's persona and available tools are injected into the prompt.
        """
        # Build the prompt with agent context
        prompt = f"""You are {self.agent_name.title()}, acting in character.

{self.definition}

TASK: {task_description}

You have access to these capabilities:
- create_document(title, content) - Create Word documents
- upload_to_sharepoint(file_path) - Upload to team SharePoint
- The word skill for document creation

Complete the task in character. Be action-oriented, not theatrical."""

        # Run via amplifier
        result = subprocess.run(
            ["amplifier", "run", prompt],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
            timeout=120,
        )
        
        return result.stdout or result.stderr


def run_as_bud():
    """Have Bud create The Repo Code document."""
    print("=== Bud is creating The Repo Code ===\n")
    
    runner = AgentRunner("bud")
    
    # Define the document content
    content = [
        {"type": "heading", "text": "THE REPO CODE", "level": 1},
        {"type": "paragraph", "text": "A Philosophy of the Repossession Business", "italic": True},
        {"type": "paragraph", "text": "By Bud — Veteran Repo Man, Helping Hand Acceptance Corporation", "italic": True},
        {"type": "paragraph", "text": ""},
        
        {"type": "heading", "text": "ARTICLE I: THE NATURE OF CREDIT", "level": 2},
        {"type": "paragraph", "text": "Credit is a sacred trust. It's what separates us from the deadbeats. When someone takes on a debt, they make a promise. When they break that promise, we restore balance."},
        
        {"type": "heading", "text": "ARTICLE II: THE REPO MAN'S CREED", "level": 2},
        {"type": "paragraph", "text": "A repo man's always intense. You have to be. This isn't a job for the ordinary person. It's a calling. You're not just taking back property — you're enforcing the social contract."},
        
        {"type": "heading", "text": "ARTICLE III: PROFESSIONAL CONDUCT", "level": 2},
        {"type": "list", "numbered": True, "items": [
            "Never get out of the car. The car is your office, your sanctuary.",
            "Know your exits. Always know how you're getting out.",
            "The plate of shrimp principle applies to everything.",
            "Trust your instincts. If something feels wrong, it probably is."
        ]},
        
        {"type": "heading", "text": "ARTICLE IV: DEALING WITH DEBTORS", "level": 2},
        {"type": "paragraph", "text": "They'll lie. They'll cry. They'll threaten. That's expected. Your job isn't to judge — it's to repo. Stay professional. Get the vehicle. Move on."},
        
        {"type": "heading", "text": "ARTICLE V: THE BROTHERHOOD", "level": 2},
        {"type": "paragraph", "text": "We look out for each other. Miller keeps the cars running. Lite has your back on stake-outs. Even Plettschner, for all his hot-headedness, is one of us."},
        
        {"type": "heading", "text": "ARTICLE VI: TEACHING THE NEXT GENERATION", "level": 2},
        {"type": "paragraph", "text": "Every rookie needs guidance. Otto's green, but he's learning. The Code isn't just rules — it's a way of seeing the world. You can't teach that from a book. You teach it by doing."},
        
        {"type": "page_break"},
        {"type": "paragraph", "text": ""},
        {"type": "paragraph", "text": '"The life of a repo man is always intense."', "bold": True, "italic": True},
    ]
    
    # Bud creates the document
    print("Bud: I'll put together The Repo Code. Otto needs to understand how we operate.\n")
    
    doc_path = runner.create_document("The Repo Code", content)
    print(f"Bud: Document created at {doc_path}\n")
    
    # Bud uploads to SharePoint
    print("Bud: Uploading to SharePoint so everyone can access it.\n")
    
    result = runner.upload_to_sharepoint(doc_path, "The_Repo_Code.docx")
    
    print(f"Bud: Done. Document's up on SharePoint.")
    print(f"     Share link: {result['share_url']}")
    print(f"\n     Otto, read this. It's everything you need to know.")
    
    return result


if __name__ == "__main__":
    run_as_bud()
