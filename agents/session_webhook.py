#!/usr/bin/env python3
"""
Session-based Webhook Server for Helping Hand Agents

Each agent has their own conversation history stored in JSON files.
Uses Anthropic API directly for reliable, in-character responses.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn

app = FastAPI(title="Helping Hand Agent Webhook (Session-based)")

# Configuration
AGENTS_DIR = Path(__file__).parent
LOG_FILE = AGENTS_DIR / "webhook.log"
CREDENTIALS_FILE = AGENTS_DIR / "credentials.json"
SESSIONS_DIR = AGENTS_DIR / "sessions"
PERSONAS_DIR = AGENTS_DIR / "personas"

# Ensure directories exist
SESSIONS_DIR.mkdir(exist_ok=True)

# Azure AD / Graph config
APP_ID = "760968bf-bbb6-423f-bff0-837057851664"
TENANT_ID = "16f9353b-6b50-4fc6-b228-70870adaf580"

# Anthropic config
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Agent definitions
AGENTS = {
    "plettschner": {
        "name": "Plettschner",
        "email": "Plettschner@M365x93789909.onmicrosoft.com",
        "role": "Senior Repo Man"
    },
    "bud": {
        "name": "Bud",
        "email": "Bud@M365x93789909.onmicrosoft.com",
        "role": "Veteran Repo Man & Mentor"
    },
    "miller": {
        "name": "Miller",
        "email": "Miller@M365x93789909.onmicrosoft.com",
        "role": "Mechanic"
    },
    "otto": {
        "name": "Otto",
        "email": "Otto@M365x93789909.onmicrosoft.com",
        "role": "Junior Repo Man"
    },
    "lite": {
        "name": "Lite",
        "email": "Lite@M365x93789909.onmicrosoft.com",
        "role": "Repo Man"
    },
    "marlene": {
        "name": "Marlene",
        "email": "Marlene@M365x93789909.onmicrosoft.com",
        "role": "Office Manager"
    }
}

# Store for recent notifications (to avoid duplicates)
processed_messages: set[str] = set()


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


def get_persona(agent_key: str) -> str:
    """Load the agent's persona from their markdown file."""
    agent = AGENTS.get(agent_key)
    persona_file = PERSONAS_DIR / f"{agent_key}.md"
    
    if persona_file.exists():
        content = persona_file.read_text()
        # Extract content after YAML frontmatter
        if "---" in content:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content
    
    # Fallback
    return f"""You are {agent['name']}, {agent['role']} at Helping Hand Acceptance Corporation.
You work in the repo business - recovering vehicles from people who haven't paid.
Keep responses conversational and in character."""


def load_session_history(agent_key: str) -> list[dict]:
    """Load conversation history for an agent."""
    session_file = SESSIONS_DIR / f"{agent_key}.json"
    if session_file.exists():
        try:
            data = json.loads(session_file.read_text())
            return data.get("messages", [])
        except Exception:
            pass
    return []


def save_session_history(agent_key: str, messages: list[dict]):
    """Save conversation history for an agent."""
    session_file = SESSIONS_DIR / f"{agent_key}.json"
    # Keep only last 50 messages to avoid context overflow
    trimmed = messages[-50:] if len(messages) > 50 else messages
    session_file.write_text(json.dumps({
        "agent": agent_key,
        "updated": datetime.now().isoformat(),
        "messages": trimmed
    }, indent=2))


async def get_app_token() -> Optional[str]:
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


async def get_user_token(agent_key: str, scopes: str = "Chat.ReadWrite") -> Optional[str]:
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


async def get_llm_response(agent_key: str, message: str, sender_name: str) -> str:
    """Get a response from Claude with conversation history."""
    
    if not ANTHROPIC_API_KEY:
        log("No ANTHROPIC_API_KEY set!")
        return await get_fallback_response(agent_key)
    
    agent = AGENTS.get(agent_key)
    persona = get_persona(agent_key)
    
    # Build system prompt
    system_prompt = f"""{persona}

## Response Guidelines

- You're responding to Teams messages from colleagues at Helping Hand Acceptance Corporation
- Keep responses conversational and relatively brief (1-4 sentences usually)
- Stay in character as {agent['name']}
- Reference past conversations if relevant - you remember what people have told you
- You can ask follow-up questions
- Be helpful but authentic to your personality
- Never break character or mention that you're an AI"""

    # Load conversation history
    history = load_session_history(agent_key)
    
    # Add new user message
    user_message = f"[{sender_name}]: {message}"
    history.append({"role": "user", "content": user_message})
    
    try:
        log(f"Calling Anthropic API for {agent_key}...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 500,
                    "system": system_prompt,
                    "messages": history
                }
            )
            
            data = response.json()
            
            if "content" in data and len(data["content"]) > 0:
                assistant_message = data["content"][0].get("text", "")
                
                # Save to history
                history.append({"role": "assistant", "content": assistant_message})
                save_session_history(agent_key, history)
                
                log(f"Response from {agent['name']}: {assistant_message[:80]}...")
                return assistant_message
            else:
                log(f"Unexpected API response: {data}")
                return await get_fallback_response(agent_key)
                
    except Exception as e:
        log(f"API error: {e}")
        return await get_fallback_response(agent_key)


async def get_fallback_response(agent_key: str) -> str:
    """Simple fallback response if LLM fails."""
    agent = AGENTS.get(agent_key)
    fallbacks = {
        "plettschner": "The life of a repo man is always intense.",
        "bud": "Credit is a sacred trust.",
        "miller": "I'll take a look at it.",
        "otto": "I'm still learning the ropes here.",
        "lite": "Got it.",
        "marlene": "I'll make a note of that."
    }
    return fallbacks.get(agent_key, f"*{agent['name']} acknowledges*")


async def process_notification(data: dict):
    """Process a Graph notification and respond."""
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
            sender_name_lower = sender_name.lower()
            
            is_agent_sender = (
                sender_key in AGENTS or
                sender_name_lower in AGENTS or
                any(agent["name"].lower() == sender_name_lower for agent in AGENTS.values())
            )
            
            if is_agent_sender:
                log(f"Message from agent '{sender_name}', ignoring to avoid loop")
                continue
            
            # Get message body
            body = message.get("body", {}).get("content", "")
            body_text = re.sub(r'<[^>]+>', '', body).strip()
            
            if not body_text:
                log("Empty message body, skipping")
                continue
                
            log(f"Message from {sender_name}: {body_text[:100]}")
            
            # Determine which agent should respond
            # Use the first agent we have credentials for
            creds = load_credentials()
            agent_key = None
            
            for key in AGENTS.keys():
                if key in creds:
                    agent_key = key
                    break
            
            if not agent_key:
                log("No agent credentials available")
                continue
            
            agent = AGENTS.get(agent_key)
            log(f"Agent {agent['name']} will respond")
            
            # Get response from LLM with history
            response_text = await get_llm_response(agent_key, body_text, sender_name)
            
            # Get token for the agent user
            user_token = await get_user_token(agent_key)
            if not user_token:
                log(f"Could not get token for {agent['name']}")
                continue
            
            # Send reply
            result = await send_reply(chat_id, response_text, user_token)
            
            if "id" in result:
                log(f"Reply sent: {response_text[:80]}...")
            else:
                log(f"Error sending reply: {result}")
                
    except Exception as e:
        log(f"Error processing notification: {e}")
        import traceback
        log(traceback.format_exc())


@app.get("/")
async def root():
    """Health check endpoint."""
    creds = load_credentials()
    agents_configured = [k for k in creds.keys() if not k.startswith("_")]
    
    # Check for session files
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        sessions.append(f.stem)
    
    return {
        "status": "ok",
        "service": "Helping Hand Agent Webhook (Session-based)",
        "agents_configured": agents_configured,
        "agents_available": list(AGENTS.keys()),
        "active_sessions": sessions,
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
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
    """List all available agents."""
    creds = load_credentials()
    
    agents_info = {}
    for agent_key, agent in AGENTS.items():
        session_file = SESSIONS_DIR / f"{agent_key}.json"
        msg_count = 0
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text())
                msg_count = len(data.get("messages", []))
            except Exception:
                pass
        
        agents_info[agent_key] = {
            "name": agent["name"],
            "role": agent["role"],
            "email": agent["email"],
            "credentials": agent_key in creds,
            "message_count": msg_count
        }
    
    return agents_info


@app.get("/sessions/{agent_key}")
async def get_session(agent_key: str):
    """Get an agent's conversation history."""
    if agent_key not in AGENTS:
        return {"error": "Unknown agent"}
    
    history = load_session_history(agent_key)
    return {
        "agent": agent_key,
        "name": AGENTS[agent_key]["name"],
        "message_count": len(history),
        "messages": history[-20:]  # Last 20 messages
    }


@app.delete("/sessions/{agent_key}")
async def reset_session(agent_key: str):
    """Reset an agent's session (clear history)."""
    session_file = SESSIONS_DIR / f"{agent_key}.json"
    if session_file.exists():
        session_file.unlink()
    
    return {"status": "reset", "agent": agent_key}


@app.get("/logs")
async def get_logs():
    """Get recent logs."""
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().splitlines()[-50:]
        return {"logs": lines}
    return {"logs": []}


if __name__ == "__main__":
    log("=" * 60)
    log("Starting Helping Hand Agent Webhook (Session-based)")
    log("=" * 60)
    log(f"Agents available: {list(AGENTS.keys())}")
    log(f"Anthropic API configured: {bool(ANTHROPIC_API_KEY)}")
    
    creds = load_credentials()
    configured = [k for k in creds.keys() if not k.startswith("_")]
    log(f"Credentials configured for: {configured}")
    
    uvicorn.run(app, host="0.0.0.0", port=8765)
