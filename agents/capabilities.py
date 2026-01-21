#!/usr/bin/env python3
"""
Agent Capabilities Module

Provides document creation, SharePoint upload, and other capabilities
that agents can use to perform real work beyond just chatting.
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime

import httpx

# Add word skill to path
sys.path.insert(0, str(Path(__file__).parent))
from word_skill import DocumentBuilder

# Azure AD / Graph config
APP_ID = "760968bf-bbb6-423f-bff0-837057851664"
TENANT_ID = "16f9353b-6b50-4fc6-b228-70870adaf580"
SHAREPOINT_SITE_ID = "m365x93789909.sharepoint.com,334abb14-2b00-49d5-a9ef-b17217dd5ef3,9ffc515a-4013-476f-b6da-9f96e1938d12"


async def get_user_token(username: str, password: str, scopes: str = "Files.ReadWrite.All Sites.ReadWrite.All") -> str | None:
    """Get access token for a user via ROPC flow."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": APP_ID,
                "scope": scopes,
                "username": username,
                "password": password,
                "grant_type": "password"
            }
        )
        data = response.json()
        return data.get("access_token")


def create_word_document(
    title: str,
    content: list[dict],
    author: str = "Helping Hand Acceptance Corp"
) -> Path:
    """
    Create a Word document with the given content.
    
    Args:
        title: Document title (used for heading and filename)
        content: List of content blocks, each with 'type' and 'text' keys
                 Types: 'heading', 'paragraph', 'list', 'table'
        author: Document author name
        
    Returns:
        Path to the created document
    """
    doc = DocumentBuilder()
    
    # Add title
    doc.add_heading(title, level=1)
    doc.add_paragraph(f"Author: {author}")
    doc.add_paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}")
    doc.add_paragraph("")  # Spacer
    
    # Process content blocks
    for block in content:
        block_type = block.get("type", "paragraph")
        text = block.get("text", "")
        
        if block_type == "heading":
            level = block.get("level", 2)
            doc.add_heading(text, level=level)
        elif block_type == "paragraph":
            bold = block.get("bold", False)
            italic = block.get("italic", False)
            doc.add_paragraph(text, bold=bold, italic=italic)
        elif block_type == "list":
            items = block.get("items", [text] if text else [])
            numbered = block.get("numbered", False)
            doc.add_list(items, numbered=numbered)
        elif block_type == "table":
            data = block.get("data", [])
            headers = block.get("headers", None)
            if data:
                doc.add_table(data, headers=headers)
    
    # Save to temp file
    temp_dir = Path(tempfile.gettempdir())
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    filename = f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    output_path = temp_dir / filename
    
    doc.save(str(output_path), overwrite=True)
    return output_path


async def upload_to_sharepoint(
    file_path: Path,
    folder_path: str,
    token: str,
    filename: str | None = None
) -> dict:
    """
    Upload a file to the team SharePoint site.
    
    Args:
        file_path: Local path to the file
        folder_path: Folder path in SharePoint (e.g., "Shared Documents/Reports")
        token: User access token with Files.ReadWrite.All scope
        filename: Optional filename override
        
    Returns:
        Dict with upload result including webUrl for sharing
    """
    filename = filename or file_path.name
    
    # Read file content
    content = file_path.read_bytes()
    
    # Upload to SharePoint
    # Using the simple upload endpoint (works for files < 4MB)
    upload_url = (
        f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_SITE_ID}"
        f"/drive/root:/{folder_path}/{filename}:/content"
    )
    
    async with httpx.AsyncClient() as client:
        response = await client.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            },
            content=content
        )
        
        if response.status_code in (200, 201):
            result = response.json()
            return {
                "success": True,
                "name": result.get("name"),
                "webUrl": result.get("webUrl"),
                "id": result.get("id"),
                "size": result.get("size")
            }
        else:
            return {
                "success": False,
                "error": response.text,
                "status": response.status_code
            }


async def create_sharing_link(file_id: str, token: str, link_type: str = "view") -> dict:
    """
    Create a sharing link for a file.
    
    Args:
        file_id: The file's Graph ID
        token: User access token
        link_type: "view" or "edit"
        
    Returns:
        Dict with sharing link info
    """
    url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_SITE_ID}/drive/items/{file_id}/createLink"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "type": link_type,
                "scope": "organization"
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "link": result.get("link", {}).get("webUrl"),
                "type": link_type
            }
        else:
            return {
                "success": False,
                "error": response.text
            }


async def send_teams_message(chat_id: str, content: str, token: str) -> dict:
    """Send a message to a Teams chat."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"body": {"content": content}}
        )
        
        if response.status_code == 201:
            return {"success": True, "id": response.json().get("id")}
        else:
            return {"success": False, "error": response.text}


# Action handlers - map action names to functions
ACTION_HANDLERS = {
    "create_document": create_word_document,
    "upload_sharepoint": upload_to_sharepoint,
    "share_link": create_sharing_link,
    "send_message": send_teams_message,
}


async def execute_action(action_name: str, params: dict, credentials: dict) -> dict:
    """
    Execute an agent action.
    
    Args:
        action_name: Name of the action to execute
        params: Parameters for the action
        credentials: Dict with user credentials for auth
        
    Returns:
        Result of the action
    """
    handler = ACTION_HANDLERS.get(action_name)
    if not handler:
        return {"success": False, "error": f"Unknown action: {action_name}"}
    
    try:
        # Get token if needed
        if action_name in ("upload_sharepoint", "share_link", "send_message"):
            token = await get_user_token(
                credentials["email"],
                credentials["password"],
                scopes="Files.ReadWrite.All Sites.ReadWrite.All Chat.ReadWrite"
            )
            if not token:
                return {"success": False, "error": "Could not get access token"}
            params["token"] = token
        
        # Execute
        if action_name == "create_document":
            # Sync function
            result_path = create_word_document(**params)
            return {"success": True, "path": str(result_path)}
        else:
            # Async functions
            result = await handler(**params)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}
