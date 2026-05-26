#!/usr/bin/env python3
"""
One-time interactive Telethon session setup.
Run once — session saved permanently.

Usage: python3 setup_telethon_session.py

Before running:
  1. Go to https://my.telegram.org → API development tools
  2. Create an app, get api_id and api_hash
  3. Create ~/.openclaw/credentials/telethon-config.json:
     {"api_id": 12345, "api_hash": "your_api_hash_here"}
  4. Run this script, enter phone and confirmation code
"""

import asyncio, json, sys
from pathlib import Path

SESSION_PATH = Path.home() / ".openclaw/credentials/telethon-boris.session"
CONFIG_PATH = Path.home() / ".openclaw/credentials/telethon-config.json"


async def setup():
    from telethon import TelegramClient

    if not CONFIG_PATH.exists():
        print(f"❌ Config not found: {CONFIG_PATH}")
        print("Create it with: {\"api_id\": 12345, \"api_hash\": \"...\"}")
        sys.exit(1)

    cfg = json.loads(CONFIG_PATH.read_text())
    api_id = int(cfg["api_id"])
    api_hash = cfg["api_hash"]

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.chmod(0o600) if SESSION_PATH.exists() else None

    print(f"Session will be saved to: {SESSION_PATH}")
    print("You will be asked for your phone number and a confirmation code from Telegram.\n")

    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.start()

    me = await client.get_me()
    print(f"\n✅ Logged in as: {me.first_name} (@{me.username}) id:{me.id}")
    print(f"Session saved: {SESSION_PATH}")

    SESSION_PATH.chmod(0o600)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup())
