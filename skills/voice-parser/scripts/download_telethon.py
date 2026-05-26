#!/usr/bin/env python3
"""
Download Telegram media via Telethon userbot (no 20MB limit).
Usage: python3 download_telethon.py --message-id=<id> --bot-id=<bot_user_id>

Requires session: ~/.openclaw/credentials/telethon-boris.session
Requires config:  ~/.openclaw/credentials/telethon-config.json
  {"api_id": 12345, "api_hash": "abcdef..."}

Run once to create session: python3 setup_telethon_session.py
"""

import sys, os, json, asyncio, argparse
from pathlib import Path

SESSION_PATH = Path.home() / ".openclaw/credentials/telethon-boris.session"
CONFIG_PATH = Path.home() / ".openclaw/credentials/telethon-config.json"
INBOUND_DIR = Path.home() / ".openclaw/media/inbound"


def load_config():
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Telethon config not found: {CONFIG_PATH}\n"
            "Create it: {\"api_id\": 12345, \"api_hash\": \"...\"}"
        )
    cfg = json.loads(CONFIG_PATH.read_text())
    return int(cfg["api_id"]), cfg["api_hash"]


async def _download(api_id, api_hash, bot_id, message_id):
    from telethon import TelegramClient

    async with TelegramClient(str(SESSION_PATH), api_id, api_hash) as client:
        bot = await client.get_entity(int(bot_id))
        msg = await client.get_messages(bot, ids=int(message_id))

        if not msg:
            raise RuntimeError(f"Message {message_id} not found in dialog with bot {bot_id}")
        if not msg.media:
            raise RuntimeError(f"Message {message_id} has no media")

        INBOUND_DIR.mkdir(parents=True, exist_ok=True)
        out_prefix = str(INBOUND_DIR / f"tg_telethon_{message_id}")
        downloaded = await client.download_media(msg, file=out_prefix)
        return downloaded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-id", required=True)
    parser.add_argument("--bot-id", required=True, help="Bot's Telegram user ID (numeric)")
    args = parser.parse_args()

    if not SESSION_PATH.exists():
        print(f"❌ Telethon session not found: {SESSION_PATH}")
        print("   Run: python3 /home/shectory/skills/voice-parser/scripts/setup_telethon_session.py")
        sys.exit(1)

    api_id, api_hash = load_config()

    print(f"⬇️  Downloading via Telethon: message_id={args.message_id} bot_id={args.bot_id}")
    try:
        path = asyncio.run(_download(api_id, api_hash, args.bot_id, args.message_id))
        print(path)
    except Exception as e:
        print(f"❌ Telethon download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
