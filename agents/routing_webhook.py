#!/usr/bin/env python3
"""
Routing Webhook Server for Helping Hand Agents

Features:
- Loads agent definitions from YAML+MD files
- Routes messages based on @mentions, keywords, and probability
- Maintains per-agent conversation history
- Realistic response delays
- Multiple agents can respond to the same message
- Auto-renewal of Graph subscriptions
- Catch-up on missed messages when server restarts
"""

import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import yaml
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import PlainTextResponse
import uvicorn

app = FastAPI(title="Helping Hand Agent Webhook (Routing)")

# Subscription management
current_subscription_id: Optional[str] = None
subscription_renewal_task: Optional[asyncio.Task] = None
SUBSCRIPTION_DURATION_MINUTES = 55  # Renew before 60min expiry
STATE_FILE: Path  # Defined after AGENTS_DIR

# Configuration
AGENTS_DIR = Path(__file__).parent
LOG_FILE = AGENTS_DIR / "webhook.log"
CREDENTIALS_FILE = AGENTS_DIR / "credentials.json"
SESSIONS_DIR = AGENTS_DIR / "sessions"
DEFINITIONS_DIR = AGENTS_DIR / "definitions"

# Ensure directories exist
SESSIONS_DIR.mkdir(exist_ok=True)

# State file for tracking last processed message
STATE_FILE = AGENTS_DIR / ".webhook_state.json"

# Azure AD / Graph config
APP_ID = "760968bf-bbb6-423f-bff0-837057851664"
TENANT_ID = "16f9353b-6b50-4fc6-b228-70870adaf580"

# Anthropic config
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Store for recent notifications (to avoid duplicates)
processed_messages: set[str] = set()

# Loaded agent definitions
agent_definitions: dict[str, dict] = {}


def log(msg: str):
    """Log message to file and stdout."""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_state() -> dict:
    """Load webhook state (last processed message time, subscription info)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: dict):
    """Save webhook state."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_ngrok_url() -> Optional[str]:
    """Get the current ngrok public URL."""
    try:
        import httpx
        response = httpx.get("http://localhost:4040/api/tunnels", timeout=5)
        data = response.json()
        tunnels = data.get("tunnels", [])
        if tunnels:
            return tunnels[0].get("public_url")
    except Exception as e:
        log(f"Could not get ngrok URL: {e}")
    return None


def load_agent_definitions():
    """Load all agent definitions from YAML+MD files."""
    global agent_definitions
    agent_definitions = {}
    
    for def_file in DEFINITIONS_DIR.glob("*.md"):
        agent_key = def_file.stem
        content = def_file.read_text()
        
        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    config = yaml.safe_load(parts[1])
                    persona = parts[2].strip()
                    
                    agent_definitions[agent_key] = {
                        "config": config,
                        "persona": persona,
                        "name": config.get("agent", {}).get("name", agent_key.title()),
                        "email": config.get("agent", {}).get("email", ""),
                        "role": config.get("agent", {}).get("role", ""),
                        "triggers": config.get("triggers", {}),
                        "channels": config.get("channels", {}),
                        "behavior": config.get("behavior", {}),
                    }
                    log(f"Loaded definition for {agent_key}")
                except yaml.YAMLError as e:
                    log(f"Error parsing {def_file}: {e}")
    
    log(f"Loaded {len(agent_definitions)} agent definitions")
    return agent_definitions


def load_credentials() -> dict:
    """Load user credentials from file."""
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text())
    return {}


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


def extract_mentions(text: str) -> list[str]:
    """Extract @mentioned names from message text."""
    # Match @Name patterns
    mentions = re.findall(r'@(\w+)', text, re.IGNORECASE)
    return [m.lower() for m in mentions]


def check_keywords(text: str, keywords: list[str]) -> bool:
    """Check if any keywords appear in the text."""
    text_lower = text.lower()
    for keyword in keywords:
        if keyword.lower() in text_lower:
            return True
    return False


def should_agent_respond(
    agent_key: str,
    message_text: str,
    sender_name: str,
    channel_name: str = "General"
) -> tuple[bool, str, float]:
    """
    Determine if an agent should respond to a message.
    
    Returns: (should_respond, reason, delay_seconds)
    """
    if agent_key not in agent_definitions:
        return False, "no definition", 0
    
    definition = agent_definitions[agent_key]
    triggers = definition.get("triggers", {})
    behavior = definition.get("behavior", {})
    channels = definition.get("channels", {})
    
    # Calculate delay range
    delay_min = behavior.get("delay_min_seconds", 15)
    delay_max = behavior.get("delay_max_seconds", 90)
    base_delay = random.uniform(delay_min, delay_max)
    
    # Check @mentions first (highest priority)
    mentions = extract_mentions(message_text)
    agent_name = definition.get("name", "").lower()
    
    if agent_key in mentions or agent_name in mentions:
        if triggers.get("mention") == "always":
            return True, f"@mentioned ({agent_name})", base_delay * 0.5  # Faster for mentions
    
    # Check channel preferences
    ignored_channels = channels.get("ignore", [])
    if any(ch.lower() in channel_name.lower() for ch in ignored_channels):
        return False, f"ignores channel {channel_name}", 0
    
    # Check keywords
    keywords = triggers.get("keywords", [])
    if keywords and check_keywords(message_text, keywords):
        # Roll dice based on direct_question probability
        prob = triggers.get("direct_question", 0.5)
        if random.random() < prob:
            return True, "keyword match", base_delay
    
    # General response probability
    general_prob = triggers.get("general", 0.1)
    
    # Boost probability for preferred channels
    preferred_channels = channels.get("preferred", [])
    if any(ch.lower() in channel_name.lower() for ch in preferred_channels):
        general_prob *= 1.5  # 50% boost for preferred channels
    
    if random.random() < general_prob:
        return True, "general interest", base_delay * 1.5  # Slower for unprompted
    
    return False, "no trigger matched", 0


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


# =============================================================================
# SUBSCRIPTION MANAGEMENT (Auto-renewal)
# =============================================================================

async def create_subscription(ngrok_url: str) -> Optional[str]:
    """Create a new Graph subscription for chat messages."""
    global current_subscription_id
    
    token = await get_app_token()
    if not token:
        log("Cannot create subscription: no app token")
        return None
    
    expiry = datetime.now(timezone.utc) + timedelta(minutes=SUBSCRIPTION_DURATION_MINUTES)
    expiry_str = expiry.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://graph.microsoft.com/v1.0/subscriptions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "changeType": "created",
                "notificationUrl": f"{ngrok_url}/webhook",
                "resource": "/chats/getAllMessages",
                "expirationDateTime": expiry_str,
                "clientState": "helpinghand-agents"
            }
        )
        data = response.json()
        
        if "id" in data:
            current_subscription_id = data["id"]
            log(f"Created subscription {current_subscription_id}, expires {expiry_str}")
            
            # Save to state
            state = load_state()
            state["subscription_id"] = current_subscription_id
            state["subscription_expiry"] = expiry_str
            state["ngrok_url"] = ngrok_url
            save_state(state)
            
            return current_subscription_id
        else:
            log(f"Failed to create subscription: {data.get('error', data)}")
            return None


async def renew_subscription() -> bool:
    """Renew the current subscription."""
    global current_subscription_id
    
    if not current_subscription_id:
        log("No subscription to renew")
        return False
    
    token = await get_app_token()
    if not token:
        return False
    
    expiry = datetime.now(timezone.utc) + timedelta(minutes=SUBSCRIPTION_DURATION_MINUTES)
    expiry_str = expiry.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"https://graph.microsoft.com/v1.0/subscriptions/{current_subscription_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={"expirationDateTime": expiry_str}
        )
        
        if response.status_code == 200:
            log(f"Renewed subscription {current_subscription_id}, new expiry {expiry_str}")
            
            state = load_state()
            state["subscription_expiry"] = expiry_str
            save_state(state)
            return True
        else:
            log(f"Failed to renew subscription: {response.status_code} {response.text[:200]}")
            return False


async def delete_subscription(sub_id: str) -> bool:
    """Delete a subscription."""
    token = await get_app_token()
    if not token:
        return False
    
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"https://graph.microsoft.com/v1.0/subscriptions/{sub_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.status_code in (200, 204)


async def subscription_renewal_loop():
    """Background task to renew subscription before expiry."""
    global current_subscription_id
    
    renewal_interval = (SUBSCRIPTION_DURATION_MINUTES - 5) * 60  # Renew 5 min before expiry
    
    while True:
        await asyncio.sleep(renewal_interval)
        
        if current_subscription_id:
            log("Auto-renewing subscription...")
            success = await renew_subscription()
            
            if not success:
                # Try to recreate
                log("Renewal failed, attempting to recreate subscription...")
                ngrok_url = get_ngrok_url()
                if ngrok_url:
                    await create_subscription(ngrok_url)


async def ensure_subscription():
    """Ensure we have an active subscription, create if needed."""
    global current_subscription_id, subscription_renewal_task
    
    ngrok_url = get_ngrok_url()
    if not ngrok_url:
        log("ERROR: ngrok not running! Cannot create subscription.")
        log("Start ngrok with: ngrok http 8765")
        return False
    
    # Check if we have an existing subscription
    state = load_state()
    existing_id = state.get("subscription_id")
    
    if existing_id:
        # Try to renew existing
        current_subscription_id = existing_id
        if await renew_subscription():
            log(f"Resumed existing subscription {existing_id}")
        else:
            # Create new
            log("Existing subscription invalid, creating new...")
            await create_subscription(ngrok_url)
    else:
        # Create new subscription
        await create_subscription(ngrok_url)
    
    # Start renewal loop if not running
    if subscription_renewal_task is None or subscription_renewal_task.done():
        subscription_renewal_task = asyncio.create_task(subscription_renewal_loop())
        log("Started subscription auto-renewal task")
    
    return current_subscription_id is not None


# =============================================================================
# CATCH-UP ON MISSED MESSAGES
# =============================================================================

async def get_all_chats(token: str) -> list[dict]:
    """Get all chats the app can access."""
    chats = []
    url = "https://graph.microsoft.com/v1.0/chats"
    
    async with httpx.AsyncClient() as client:
        while url:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            data = response.json()
            chats.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            if len(chats) > 100:  # Limit for safety
                break
    
    return chats


async def get_recent_messages(chat_id: str, token: str, since: Optional[str] = None) -> list[dict]:
    """Get recent messages from a chat, optionally filtered by time."""
    messages = []
    
    # Build URL with filter if we have a since timestamp
    url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
    params = {"$top": "50", "$orderby": "createdDateTime desc"}
    
    if since:
        params["$filter"] = f"createdDateTime gt {since}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params
        )
        data = response.json()
        messages = data.get("value", [])
    
    return messages


async def catch_up_on_missed_messages():
    """Check for and process messages that arrived while server was down."""
    log("Checking for missed messages...")
    
    state = load_state()
    last_processed = state.get("last_message_time")
    
    if not last_processed:
        log("No previous state found, skipping catch-up")
        return
    
    token = await get_app_token()
    if not token:
        log("Cannot catch up: no app token")
        return
    
    # Get chats we're part of
    try:
        chats = await get_all_chats(token)
        log(f"Found {len(chats)} chats to check for missed messages")
        
        missed_count = 0
        
        for chat in chats:
            chat_id = chat.get("id")
            if not chat_id:
                continue
            
            # Get messages since last processed
            messages = await get_recent_messages(chat_id, token, since=last_processed)
            
            for message in reversed(messages):  # Process oldest first
                msg_id = message.get("id")
                msg_key = f"{chat_id}:{msg_id}"
                
                # Skip if already processed
                if msg_key in processed_messages:
                    continue
                
                # Skip if from an agent
                sender = message.get("from", {})
                sender_user = sender.get("user", {})
                sender_email = sender_user.get("userPrincipalName", "").lower()
                sender_key = sender_email.split("@")[0].lower() if sender_email else ""
                
                if sender_key in agent_definitions:
                    continue
                
                # Process this missed message
                sender_name = sender_user.get("displayName", "Someone")
                body = message.get("body", {}).get("content", "")
                body_text = re.sub(r'<[^>]+>', '', body).strip()
                
                if body_text:
                    missed_count += 1
                    log(f"Processing missed message from {sender_name}: {body_text[:50]}...")
                    
                    # Mark as processed
                    processed_messages.add(msg_key)
                    
                    # Route to agents (with shorter delays for catch-up)
                    creds = load_credentials()
                    channel_name = message.get("channelIdentity", {}).get("channelName", "Direct")
                    
                    for agent_key in agent_definitions.keys():
                        if agent_key not in creds:
                            continue
                        
                        should_respond, reason, delay = should_agent_respond(
                            agent_key, body_text, sender_name, channel_name
                        )
                        
                        if should_respond:
                            # Shorter delay for catch-up (5-30s)
                            catchup_delay = min(delay * 0.3, 30)
                            asyncio.create_task(
                                delayed_response(agent_key, chat_id, body_text, sender_name, catchup_delay)
                            )
        
        if missed_count > 0:
            log(f"Processed {missed_count} missed messages")
        else:
            log("No missed messages found")
            
    except Exception as e:
        log(f"Error during catch-up: {e}")
        import traceback
        log(traceback.format_exc())


async def get_user_token(agent_key: str, scopes: str = "Chat.ReadWrite") -> Optional[str]:
    """Get access token for an agent user via ROPC flow."""
    creds = load_credentials()
    
    if agent_key not in creds:
        log(f"No credentials for agent: {agent_key}")
        return None
    
    if agent_key not in agent_definitions:
        return None
    
    definition = agent_definitions[agent_key]
    email = definition.get("email", "")
    password = creds[agent_key].get("password", "")
    
    if not email or not password:
        return None
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": APP_ID,
                "scope": scopes,
                "username": email,
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
    """Get a response from Claude with conversation history and persona."""
    
    if not ANTHROPIC_API_KEY:
        log("No ANTHROPIC_API_KEY set!")
        return get_fallback_response(agent_key)
    
    if agent_key not in agent_definitions:
        return get_fallback_response(agent_key)
    
    definition = agent_definitions[agent_key]
    persona = definition.get("persona", "")
    agent_name = definition.get("name", agent_key.title())
    
    # Build system prompt
    system_prompt = f"""{persona}

## Response Guidelines for Teams Chat

- You're responding to Teams messages from colleagues at Helping Hand Acceptance Corporation
- Keep responses conversational and in character as {agent_name}
- Reference past conversations if relevant - you remember what people have told you
- Be authentic to your personality
- Never break character or mention that you're an AI
- Keep responses relatively brief (1-4 sentences usually, unless the topic warrants more)"""

    # Load conversation history
    history = load_session_history(agent_key)
    
    # Add new user message
    user_message = f"[{sender_name}]: {message}"
    history.append({"role": "user", "content": user_message})
    
    try:
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
                
                return assistant_message
            else:
                log(f"Unexpected API response: {data}")
                return get_fallback_response(agent_key)
                
    except Exception as e:
        log(f"API error for {agent_key}: {e}")
        return get_fallback_response(agent_key)


def get_fallback_response(agent_key: str) -> str:
    """Simple fallback response if LLM fails."""
    fallbacks = {
        "plettschner": "Let's GO already!",
        "bud": "Credit is a sacred trust.",
        "miller": "A lot of people don't realize what's really going on.",
        "otto": "I'm still figuring this out.",
        "lite": "Yeah.",
        "marlene": "I'll make a note of that."
    }
    return fallbacks.get(agent_key, "*acknowledges*")


async def process_notification(data: dict):
    """Process a Graph notification with routing logic."""
    log("Processing notification with routing...")
    
    try:
        app_token = await get_app_token()
        if not app_token:
            log("ERROR: Could not get app token")
            return
        
        for notification in data.get("value", []):
            resource = notification.get("resource", "")
            _change_type = notification.get("changeType", "")
            
            # Parse resource path to get chat_id and message_id
            if "/messages(" not in resource and "/messages/" not in resource:
                continue
                
            # Extract IDs
            parts = resource.replace("'", "").replace("(", "/").replace(")", "").split("/")
            chat_id = None
            message_id = None
            
            for i, part in enumerate(parts):
                if part == "chats" and i + 1 < len(parts):
                    chat_id = parts[i + 1]
                elif part == "messages" and i + 1 < len(parts):
                    message_id = parts[i + 1]
            
            if not chat_id or not message_id:
                continue
            
            # Avoid duplicates
            msg_key = f"{chat_id}:{message_id}"
            if msg_key in processed_messages:
                continue
            processed_messages.add(msg_key)
            
            if len(processed_messages) > 500:
                processed_messages.clear()
            
            # Fetch message
            message = await fetch_message(chat_id, message_id, app_token)
            
            if "error" in message:
                log(f"Error fetching message: {message['error']}")
                continue
            
            # Get sender info
            sender = message.get("from", {})
            if not sender:
                continue
                
            sender_user = sender.get("user", {})
            sender_email = sender_user.get("userPrincipalName", "").lower()
            sender_name = sender_user.get("displayName", "Someone")
            
            # Check if sender is one of our agents
            sender_key = sender_email.split("@")[0].lower() if sender_email else ""
            is_agent_sender = sender_key in agent_definitions
            
            if is_agent_sender:
                log(f"Message from agent '{sender_name}', skipping to avoid loops")
                continue
            
            # Get message body
            body = message.get("body", {}).get("content", "")
            body_text = re.sub(r'<[^>]+>', '', body).strip()
            
            if not body_text:
                continue
                
            log(f"Message from {sender_name}: {body_text[:80]}...")
            
            # Update last message time for catch-up feature
            msg_time = message.get("createdDateTime")
            if msg_time:
                state = load_state()
                state["last_message_time"] = msg_time
                save_state(state)
            
            # Determine channel name (for routing)
            # In 1:1 chats, channel_name might be empty or None
            channel_identity = message.get("channelIdentity") or {}
            channel_name = channel_identity.get("channelName", "Direct") or "Direct"
            
            # Route to agents
            creds = load_credentials()
            responding_agents = []
            
            for agent_key in agent_definitions.keys():
                if agent_key not in creds:
                    continue
                    
                should_respond, reason, delay = should_agent_respond(
                    agent_key, body_text, sender_name, channel_name
                )
                
                if should_respond:
                    responding_agents.append((agent_key, reason, delay))
                    log(f"  → {agent_key} WILL respond ({reason}, delay: {delay:.0f}s)")
                else:
                    log(f"  → {agent_key} won't respond ({reason})")
            
            # Process responding agents with delays
            for agent_key, reason, delay in responding_agents:
                # Schedule response with delay
                asyncio.create_task(
                    delayed_response(agent_key, chat_id, body_text, sender_name, delay)
                )
                
    except Exception as e:
        log(f"Error processing notification: {e}")
        import traceback
        log(traceback.format_exc())


async def delayed_response(
    agent_key: str,
    chat_id: str,
    message_text: str,
    sender_name: str,
    delay: float
):
    """Send a response after a delay."""
    agent_name = agent_definitions.get(agent_key, {}).get("name", agent_key)
    
    log(f"[{agent_name}] Waiting {delay:.0f}s before responding...")
    await asyncio.sleep(delay)
    
    log(f"[{agent_name}] Generating response...")
    response_text = await get_llm_response(agent_key, message_text, sender_name)
    
    # Get token
    user_token = await get_user_token(agent_key)
    if not user_token:
        log(f"[{agent_name}] Could not get token")
        return
    
    # Send reply
    result = await send_reply(chat_id, response_text, user_token)
    
    if "id" in result:
        log(f"[{agent_name}] Replied: {response_text[:60]}...")
    else:
        log(f"[{agent_name}] Error sending reply: {result}")


# FastAPI Routes

@app.on_event("startup")
async def startup():
    """Load agent definitions and set up subscriptions on startup."""
    load_agent_definitions()
    
    # Set up subscription with auto-renewal
    log("Setting up Graph subscription...")
    success = await ensure_subscription()
    
    if success:
        # Catch up on any missed messages
        await catch_up_on_missed_messages()
    else:
        log("WARNING: Could not set up subscription. Make sure ngrok is running.")


@app.get("/")
async def root():
    """Health check endpoint."""
    creds = load_credentials()
    agents_configured = [k for k in creds.keys() if not k.startswith("_")]
    state = load_state()
    
    return {
        "status": "ok",
        "service": "Helping Hand Agent Webhook (Routing)",
        "agents_defined": list(agent_definitions.keys()),
        "agents_with_credentials": agents_configured,
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "subscription_id": current_subscription_id,
        "subscription_expiry": state.get("subscription_expiry"),
        "last_message_time": state.get("last_message_time"),
        "quote": "A lot of people don't realize what's really going on."
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive Graph webhook notifications."""
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        log("Validation request received")
        return PlainTextResponse(content=validation_token)
    
    try:
        body = await request.json()
        log(f"Webhook received: {len(body.get('value', []))} notification(s)")
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
        return PlainTextResponse(content=validation_token)
    return {"error": "No validation token provided"}


@app.get("/agents")
async def list_agents():
    """List all agents with their configuration."""
    creds = load_credentials()
    
    agents_info = {}
    for agent_key, definition in agent_definitions.items():
        session_file = SESSIONS_DIR / f"{agent_key}.json"
        msg_count = 0
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text())
                msg_count = len(data.get("messages", []))
            except Exception:
                pass
        
        agents_info[agent_key] = {
            "name": definition.get("name"),
            "role": definition.get("role"),
            "credentials": agent_key in creds,
            "message_count": msg_count,
            "triggers": definition.get("triggers", {}),
            "channels": definition.get("channels", {}),
        }
    
    return agents_info


@app.get("/agents/{agent_key}")
async def get_agent(agent_key: str):
    """Get detailed info about an agent."""
    if agent_key not in agent_definitions:
        return {"error": "Unknown agent"}
    
    definition = agent_definitions[agent_key]
    history = load_session_history(agent_key)
    
    return {
        "agent": agent_key,
        "definition": definition.get("config", {}),
        "message_count": len(history),
        "recent_messages": history[-10:]
    }


@app.delete("/sessions/{agent_key}")
async def reset_session(agent_key: str):
    """Reset an agent's conversation history."""
    session_file = SESSIONS_DIR / f"{agent_key}.json"
    if session_file.exists():
        session_file.unlink()
    return {"status": "reset", "agent": agent_key}


@app.post("/reload")
async def reload_definitions():
    """Reload agent definitions from files."""
    load_agent_definitions()
    return {"status": "reloaded", "agents": list(agent_definitions.keys())}


@app.get("/logs")
async def get_logs():
    """Get recent logs."""
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().splitlines()[-100:]
        return {"logs": lines}
    return {"logs": []}


@app.post("/subscription/renew")
async def manual_renew():
    """Manually renew the subscription."""
    if current_subscription_id:
        success = await renew_subscription()
        return {"status": "renewed" if success else "failed", "subscription_id": current_subscription_id}
    else:
        ngrok_url = get_ngrok_url()
        if ngrok_url:
            sub_id = await create_subscription(ngrok_url)
            return {"status": "created" if sub_id else "failed", "subscription_id": sub_id}
        return {"status": "error", "message": "ngrok not running"}


@app.post("/catchup")
async def manual_catchup():
    """Manually trigger catch-up on missed messages."""
    await catch_up_on_missed_messages()
    return {"status": "completed"}


@app.get("/subscription")
async def get_subscription_status():
    """Get current subscription status."""
    state = load_state()
    return {
        "subscription_id": current_subscription_id,
        "expiry": state.get("subscription_expiry"),
        "ngrok_url": state.get("ngrok_url"),
        "last_message_time": state.get("last_message_time"),
        "auto_renewal_active": subscription_renewal_task is not None and not subscription_renewal_task.done()
    }


if __name__ == "__main__":
    log("=" * 60)
    log("Starting Helping Hand Agent Webhook (Routing)")
    log("=" * 60)
    
    load_agent_definitions()
    
    creds = load_credentials()
    configured = [k for k in creds.keys() if not k.startswith("_")]
    log(f"Credentials configured for: {configured}")
    log(f"Anthropic API configured: {bool(ANTHROPIC_API_KEY)}")
    
    uvicorn.run(app, host="0.0.0.0", port=8765)
