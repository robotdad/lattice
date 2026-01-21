#!/usr/bin/env python3
"""
Webhook server for Microsoft Graph notifications.
Receives Teams chat message notifications and auto-responds as agent users.

Helping Hand Acceptance Corporation - "The life of a repo man is always intense."
"""

import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn

# Add agents directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent_definitions import AGENTS, detect_requested_action, can_agent_do
from capabilities import create_word_document, upload_to_sharepoint

app = FastAPI(title="Helping Hand Agent Webhook")

# Configuration
AGENTS_DIR = Path(__file__).parent
LOG_FILE = AGENTS_DIR / "webhook.log"
CREDENTIALS_FILE = AGENTS_DIR / "credentials.json"

# Azure AD / Graph config
APP_ID = "760968bf-bbb6-423f-bff0-837057851664"
TENANT_ID = "16f9353b-6b50-4fc6-b228-70870adaf580"

# Store for recent notifications (to avoid duplicates)
processed_messages = set()


def log(msg: str):
    """Log message to file and stdout."""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_credentials() -> dict:
    """Load user credentials from file."""
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text())
    return {}


async def get_app_token() -> str | None:
    """Get app-only access token for reading messages."""
    creds = load_credentials()
    client_secret = creds.get("_app", {}).get("client_secret")
    
    if not client_secret:
        log("No app client secret configured")
        return None
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": APP_ID,
                "scope": "https://graph.microsoft.com/.default",
                "client_secret": client_secret,
                "grant_type": "client_credentials"
            }
        )
        data = response.json()
        return data.get("access_token")


async def get_user_token_for_agent(agent_key: str, scopes: str = "Chat.ReadWrite") -> str | None:
    """Get access token for an agent user via ROPC flow."""
    creds = load_credentials()
    
    if agent_key not in creds:
        log(f"No credentials for agent: {agent_key}")
        return None
    
    agent = AGENTS.get(agent_key)
    if not agent:
        return None
        
    password = creds[agent_key]["password"]
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": APP_ID,
                "scope": scopes,
                "username": agent["email"],
                "password": password,
                "grant_type": "password"
            }
        )
        data = response.json()
        
        if "access_token" in data:
            return data["access_token"]
        else:
            log(f"Token error for {agent_key}: {data.get('error_description', 'unknown')[:100]}")
            return None


async def fetch_message(chat_id: str, message_id: str, token: str) -> dict:
    """Fetch the actual message content from Graph API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()


async def send_reply(chat_id: str, content: str, user_token: str) -> dict:
    """Send a reply message to the chat as the user."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers={
                "Authorization": f"Bearer {user_token}",
                "Content-Type": "application/json"
            },
            json={"body": {"content": content}}
        )
        return response.json()


def generate_response(agent_key: str, incoming_message: str, sender_name: str) -> tuple[str, str | None]:
    """
    Generate a response based on agent personality and detected action.
    
    Returns:
        Tuple of (response_text, action_to_perform)
    """
    agent = AGENTS.get(agent_key)
    if not agent:
        return "I'm not sure how to respond to that.", None
    
    message_lower = incoming_message.lower()
    
    # Detect if user is requesting an action
    action, keywords = detect_requested_action(incoming_message)
    
    # Check for document creation request
    if action == "document_writing" and can_agent_do(agent_key, "document_writing"):
        # They want us to write something
        if "share" in message_lower or "sharepoint" in message_lower:
            return (
                f"Alright, I'll write that up and put it on SharePoint. Give me a minute.",
                "create_and_share_document"
            )
        else:
            return (
                f"I'll draft that document for you. What specifically do you need in it?",
                "prepare_document"
            )
    
    # Check for vehicle/repair topics
    if action == "vehicle_repair" and agent_key == "miller":
        return (
            f"Bring it by the shop. {random.choice(agent['sample_responses'])}",
            None
        )
    
    # Check for repo work
    if action == "repo_work" and can_agent_do(agent_key, "repo_work"):
        responses = [
            "A repo job? {random.choice(agent['sample_responses'])}",
            "I'm on it. {random.choice(agent['sample_responses'])}",
            "Consider it done. {random.choice(agent['sample_responses'])}"
        ]
        return random.choice(responses), None
    
    # Default conversational response
    if "?" in incoming_message:
        # It's a question
        return f"{random.choice(agent['sample_responses'])} What else do you need?", None
    
    # Generic response with personality
    return random.choice(agent["sample_responses"]), None


async def handle_document_action(
    agent_key: str, 
    chat_id: str, 
    original_message: str,
    action: str
) -> str | None:
    """
    Handle document creation actions.
    
    Returns:
        Status message or None if failed
    """
    agent = AGENTS.get(agent_key)
    creds = load_credentials()
    
    if agent_key not in creds:
        return None
    
    try:
        # Create a simple document based on the request
        # In a full implementation, we'd parse the request more intelligently
        title = "Helping Hand Report"
        if "maintenance" in original_message.lower():
            title = "Vehicle Maintenance Report"
        elif "status" in original_message.lower():
            title = "Status Report"
        elif "inventory" in original_message.lower():
            title = "Inventory Report"
        
        content = [
            {"type": "heading", "text": "Summary", "level": 2},
            {"type": "paragraph", "text": f"Report prepared by {agent['name']} at Helping Hand Acceptance Corporation."},
            {"type": "paragraph", "text": f"Request: {original_message}"},
            {"type": "heading", "text": "Details", "level": 2},
            {"type": "paragraph", "text": "This document was automatically generated in response to a Teams request."},
            {"type": "list", "items": [
                "Document created successfully",
                f"Author: {agent['name']}",
                f"Date: {datetime.now().strftime('%B %d, %Y')}"
            ]}
        ]
        
        # Create the document
        doc_path = create_word_document(title, content, author=agent["name"])
        log(f"Document created: {doc_path}")
        
        if action == "create_and_share_document":
            # Upload to SharePoint
            token = await get_user_token_for_agent(
                agent_key, 
                scopes="Files.ReadWrite.All Sites.ReadWrite.All"
            )
            
            if token:
                result = await upload_to_sharepoint(
                    doc_path,
                    "Shared Documents",
                    token
                )
                
                if result.get("success"):
                    return f"Done. I put it on SharePoint: {result.get('webUrl', 'check Shared Documents')}"
                else:
                    log(f"SharePoint upload failed: {result}")
                    return f"I wrote the document but couldn't upload it. Error: {result.get('error', 'unknown')[:50]}"
            else:
                return "I wrote the document but couldn't get access to SharePoint."
        
        return f"Document ready: {doc_path.name}"
        
    except Exception as e:
        log(f"Document action failed: {e}")
        return None


async def process_notification(data: dict):
    """Process a Graph notification and auto-respond."""
    log("Processing notification...")
    
    try:
        app_token = await get_app_token()
        if not app_token:
            log("ERROR: Could not get app token")
            return
        
        for notification in data.get("value", []):
            resource = notification.get("resource", "")
            change_type = notification.get("changeType", "")
            
            log(f"Notification: {change_type} on {resource[:80]}...")
            
            # Parse resource path to get chat_id and message_id
            if "/messages(" not in resource and "/messages/" not in resource:
                continue
                
            # Extract IDs from resource path
            parts = resource.replace("'", "").replace("(", "/").replace(")", "").split("/")
            chat_id = None
            message_id = None
            
            for i, part in enumerate(parts):
                if part == "chats" and i + 1 < len(parts):
                    chat_id = parts[i + 1]
                elif part == "messages" and i + 1 < len(parts):
                    message_id = parts[i + 1]
            
            if not chat_id or not message_id:
                log(f"Could not parse chat/message IDs from: {resource}")
                continue
            
            # Avoid processing the same message twice
            msg_key = f"{chat_id}:{message_id}"
            if msg_key in processed_messages:
                log(f"Skipping duplicate: {msg_key}")
                continue
            processed_messages.add(msg_key)
            
            # Keep set bounded
            if len(processed_messages) > 500:
                processed_messages.clear()
            
            # Fetch the actual message
            log(f"Fetching message {message_id}...")
            message = await fetch_message(chat_id, message_id, app_token)
            
            if "error" in message:
                log(f"Error fetching message: {message['error']}")
                continue
            
            # Get sender info
            sender = message.get("from", {})
            if not sender:
                log("No sender info, skipping")
                continue
                
            sender_user = sender.get("user", {})
            sender_email = sender_user.get("userPrincipalName", "").lower()
            sender_name = sender_user.get("displayName", "Someone")
            
            # Check if sender is one of our agents (don't respond to ourselves)
            sender_key = sender_email.split("@")[0].lower() if sender_email else ""
            sender_name_key = sender_name.lower()
            
            is_agent_sender = (
                sender_key in AGENTS or
                sender_name_key in AGENTS or
                any(agent["name"].lower() == sender_name_key for agent in AGENTS.values())
            )
            
            if is_agent_sender:
                log(f"Message from agent '{sender_name}', ignoring to avoid loop")
                continue
            
            # Get message body
            body = message.get("body", {}).get("content", "")
            body_text = re.sub(r'<[^>]+>', '', body).strip()
            
            log(f"Message from {sender_name}: {body_text[:100]}")
            
            # Determine which agent should respond based on chat participants
            # For now, use simple heuristic from chat ID
            agent_key = None
            chat_id_lower = chat_id.lower()
            for key in AGENTS.keys():
                if key in chat_id_lower:
                    agent_key = key
                    break
            
            # Default to checking credentials for who we can respond as
            if not agent_key:
                creds = load_credentials()
                for key in AGENTS.keys():
                    if key in creds:
                        agent_key = key
                        break
            
            if not agent_key:
                log("No agent found for this chat")
                continue
            
            agent = AGENTS.get(agent_key)
            log(f"Agent {agent['name']} will respond")
            
            # Generate response
            response_text, action = generate_response(agent_key, body_text, sender_name)
            log(f"Response: {response_text}")
            if action:
                log(f"Action: {action}")
            
            # Get token for the agent user
            user_token = await get_user_token_for_agent(agent_key)
            if not user_token:
                log(f"Could not get token for {agent['name']}")
                continue
            
            # Send initial reply
            result = await send_reply(chat_id, response_text, user_token)
            
            if "id" in result:
                log("Reply sent successfully!")
            else:
                log(f"Error sending reply: {result}")
                continue
            
            # Handle any action
            if action:
                action_result = await handle_document_action(
                    agent_key, chat_id, body_text, action
                )
                if action_result:
                    # Send follow-up with action result
                    await send_reply(chat_id, action_result, user_token)
                    log(f"Action result sent: {action_result}")
                
    except Exception as e:
        log(f"Error processing notification: {e}")
        import traceback
        log(traceback.format_exc())


@app.get("/")
async def root():
    """Health check endpoint."""
    creds = load_credentials()
    agents_configured = [k for k in creds.keys() if not k.startswith("_")]
    
    return {
        "status": "ok",
        "service": "Helping Hand Agent Webhook",
        "agents_configured": agents_configured,
        "agents_available": list(AGENTS.keys()),
        "quote": "The life of a repo man is always intense."
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Graph webhook notifications."""
    # Check for validation token
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        log("Validation request received")
        return PlainTextResponse(content=validation_token)
    
    # Process notification
    try:
        body = await request.json()
        log(f"Webhook received: {len(body.get('value', []))} notification(s)")
        
        # Process in background to respond quickly
        background_tasks.add_task(process_notification, body)
        
        return Response(status_code=202)
    except Exception as e:
        log(f"Error processing webhook: {e}")
        return Response(status_code=500)


@app.get("/webhook")
async def webhook_validation(request: Request):
    """Handle GET requests for subscription validation."""
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        log("GET Validation request")
        return PlainTextResponse(content=validation_token)
    return {"error": "No validation token provided"}


@app.get("/agents")
async def list_agents():
    """List all available agents and their capabilities."""
    return {
        agent_key: {
            "name": agent["name"],
            "role": agent["role"],
            "capabilities": agent["capabilities"]
        }
        for agent_key, agent in AGENTS.items()
    }


@app.get("/logs")
async def get_logs():
    """Get recent logs."""
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().splitlines()[-50:]
        return {"logs": lines}
    return {"logs": []}


if __name__ == "__main__":
    log("Starting Helping Hand Agent Webhook...")
    log(f"Agents available: {list(AGENTS.keys())}")
    
    creds = load_credentials()
    configured = [k for k in creds.keys() if not k.startswith("_")]
    log(f"Credentials configured for: {configured}")
    
    uvicorn.run(app, host="0.0.0.0", port=8765)
