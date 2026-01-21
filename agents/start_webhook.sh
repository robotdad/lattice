#!/bin/bash
cd /home/robotdad/m365/opus
export ANTHROPIC_API_KEY="$1"
exec agents/.venv/bin/python agents/session_webhook.py
