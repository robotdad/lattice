#!/usr/bin/env python3
"""Catch-up script to find and process missed messages for agents."""
import json
import requests
import re
from datetime import datetime, timedelta, timezone

# Load credentials
with open('credentials.json') as f:
    creds = json.load(f)

CLIENT_ID = "760968bf-bbb6-423f-bff0-837057851664"
TENANT_ID = "16f9353b-6b50-4fc6-b228-70870adaf580"
CLIENT_SECRET = creds['_app']['client_secret']

# Agent names we're looking for
AGENT_NAMES = ['bud', 'miller', 'otto', 'lite', 'marlene', 'plettschner']

def get_delegated_token(username, password):
    """Get delegated token using ROPC."""
    resp = requests.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
        data={
            "client_id": CLIENT_ID,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": CLIENT_SECRET,
            "grant_type": "password",
            "username": f"{username}@M365x93789909.onmicrosoft.com",
            "password": password
        }
    )
    data = resp.json()
    return data.get('access_token')

def get_chats(token):
    """Get user's chats."""
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me/chats?$top=20",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = resp.json()
    return data.get('value', [])

def get_chat_messages(token, chat_id, since_minutes=60):
    """Get recent messages from a chat."""
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/me/chats/{chat_id}/messages?$top=50&$orderby=createdDateTime desc",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = resp.json()
    return data.get('value', [])

def extract_mentions(message):
    """Extract mentioned users from a message."""
    mentions = message.get('mentions', [])
    mentioned_names = []
    for m in mentions:
        mentioned = m.get('mentioned', {})
        if mentioned:
            user = mentioned.get('user', {})
            if user:
                mentioned_names.append(user.get('displayName', '').lower())
    return mentioned_names

def find_messages_for_agent(messages, agent_name):
    """Find messages that mention or are directed at an agent."""
    results = []
    for msg in messages:
        # Skip if no sender info
        from_info = msg.get('from')
        if not from_info:
            continue
            
        # Skip messages from the agent itself
        sender = from_info.get('user', {})
        if sender and sender.get('displayName', '').lower() == agent_name.lower():
            continue
        
        # Check mentions
        mentions = extract_mentions(msg)
        if agent_name.lower() in [m.lower() for m in mentions]:
            results.append(msg)
            continue
        
        # Check body content for @agent patterns
        body = msg.get('body', {}).get('content', '')
        if f'@{agent_name}' in body.lower() or f'>{agent_name}<' in body.lower():
            results.append(msg)
    
    return results

# Try to get a working token from any licensed user
print("=== Catching up on missed messages ===")
print()

working_token = None
working_user = None

for agent in ['plettschner', 'miller', 'otto']:
    if agent in creds:
        token = get_delegated_token(agent.capitalize(), creds[agent]['password'])
        if token:
            test = requests.get(
                "https://graph.microsoft.com/v1.0/me/chats?$top=1",
                headers={"Authorization": f"Bearer {token}"}
            )
            if 'error' not in test.json():
                working_token = token
                working_user = agent
                print(f"Using {agent}'s token to check chats")
                break

if not working_token:
    print("ERROR: Could not get a working token from any agent")
    exit(1)

# Get all chats
chats = get_chats(working_token)
print(f"Found {len(chats)} chats")
print()

# Check each chat for messages directed at our agents
all_missed = {}
for chat in chats:
    chat_id = chat['id']
    chat_type = chat.get('chatType', 'unknown')
    
    messages = get_chat_messages(working_token, chat_id, since_minutes=120)
    
    for agent in AGENT_NAMES:
        missed = find_messages_for_agent(messages, agent)
        if missed:
            if agent not in all_missed:
                all_missed[agent] = []
            for m in missed:
                from_info = m.get('from', {})
                sender_name = 'Unknown'
                if from_info and from_info.get('user'):
                    sender_name = from_info['user'].get('displayName', 'Unknown')
                
                all_missed[agent].append({
                    'chat_id': chat_id,
                    'message_id': m['id'],
                    'sender': sender_name,
                    'content': m.get('body', {}).get('content', '')[:200],
                    'created': m.get('createdDateTime', ''),
                    'chat_type': chat_type
                })

# Report findings
print("=== Missed Messages by Agent ===")
for agent, messages in all_missed.items():
    print(f"\n{agent.upper()}: {len(messages)} message(s)")
    for m in messages:
        print(f"  [{m['created']}] From: {m['sender']}")
        content = re.sub('<[^>]+>', '', m['content'])
        print(f"    {content[:100]}...")
        print(f"    Chat: {m['chat_id'][:40]}...")

if not all_missed:
    print("\nNo missed messages found for any agent in accessible chats.")
    print("Note: Can only see chats that the scanning user is part of.")

# Save state
with open('.catchup_state.json', 'w') as f:
    json.dump(all_missed, f, indent=2)
print(f"\nSaved state to .catchup_state.json")
