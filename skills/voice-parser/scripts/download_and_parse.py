#!/usr/bin/env python3
"""
Download Telegram voice file by file_id and transcribe via Gemini.
Usage:
  python3 download_and_parse.py <file_id> [--message-id=<id>] [--account-id=<id>] [prompt]

  --message-id  Telegram message ID (from conversation metadata).
                Required for Telethon fallback when file >20MB.
  --account-id  OpenClaw bot account ID (e.g. interview-coach).
                Used to look up bot_id for Telethon dialog.

Gets bot token from openclaw.json (default account).
Downloads to ~/.openclaw/media/inbound/, then calls parse_voice.py.
On "file is too big": falls back to Telethon if --message-id provided.
"""

import sys, os, json, subprocess, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_voice import parse_audio

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
INBOUND_DIR = Path.home() / ".openclaw/media/inbound"
LINEMAN = os.environ.get("LINEMAN_URL", "http://127.0.0.1:9090")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def get_bot_token(account_id: str = None) -> str:
    d = json.loads(Path(CONFIG_PATH).read_text())
    accounts = d.get("channels", {}).get("telegram", {}).get("accounts", {})
    candidates = []
    if account_id:
        candidates.append(account_id)
    candidates += ["interview-coach", "default"]
    for aid in candidates:
        token = accounts.get(aid, {})
        if isinstance(token, str):
            return token
        if isinstance(token, dict):
            t = token.get("botToken", "")
            if t:
                return t
    return ""


def get_bot_id(account_id: str) -> int:
    """Extract numeric bot ID from bot token."""
    d = json.loads(Path(CONFIG_PATH).read_text())
    accounts = d.get("channels", {}).get("telegram", {}).get("accounts", {})
    acc = accounts.get(account_id, {})
    token = acc.get("botToken", "") if isinstance(acc, dict) else str(acc)
    if ":" in token:
        return int(token.split(":")[0])
    raise RuntimeError(f"Cannot get bot_id for account '{account_id}'")


def download_via_bot_api(file_id: str, bot_token: str) -> Path:
    import requests
    proxies = {"https": LINEMAN, "http": LINEMAN}

    url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
    r = requests.get(url, proxies=proxies, timeout=15)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", str(data)))

    file_path = data["result"]["file_path"]
    ext = os.path.splitext(file_path)[1] or ".ogg"

    dl_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    r2 = requests.get(dl_url, proxies=proxies, timeout=30)
    r2.raise_for_status()

    INBOUND_DIR.mkdir(parents=True, exist_ok=True)
    local_path = INBOUND_DIR / f"tg_{file_id[:16]}{ext}"
    local_path.write_bytes(r2.content)
    return local_path


def download_via_telethon(message_id: str, account_id: str) -> Path:
    bot_id = get_bot_id(account_id)
    script = os.path.join(SCRIPTS_DIR, "download_telethon.py")
    r = subprocess.run(
        ["python3", script, f"--message-id={message_id}", f"--bot-id={bot_id}"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        raise RuntimeError(r.stdout.strip() + r.stderr.strip())
    # Last non-empty line is the file path
    lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
    if not lines:
        raise RuntimeError("Telethon returned no output")
    return Path(lines[-1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_id")
    parser.add_argument("--message-id", default=None)
    parser.add_argument("--account-id", default="interview-coach")
    parser.add_argument("prompt", nargs="?", default=None)
    args = parser.parse_args()

    token = get_bot_token(args.account_id)
    if not token:
        print("❌ Bot token not found in openclaw.json")
        sys.exit(1)

    print(f"⬇️  Downloading file_id: {args.file_id[:20]}...")
    local_path = None

    try:
        local_path = download_via_bot_api(args.file_id, token)
        print(f"✅ Saved: {local_path}")
    except RuntimeError as e:
        err = str(e)
        if "file is too big" in err:
            if args.message_id and args.account_id:
                print(f"⚠️  File >20MB — switching to Telethon (message_id={args.message_id})")
                try:
                    local_path = download_via_telethon(args.message_id, args.account_id)
                    print(f"✅ Telethon saved: {local_path}")
                except Exception as te:
                    print(f"❌ Telethon failed: {te}")
                    sys.exit(1)
            else:
                print(
                    "❌ Файл слишком большой для Bot API (лимит 20MB). "
                    "Передай --message-id и --account-id для загрузки через Telethon.\n"
                    "Или записывай голосовые через кнопку микрофона в Telegram."
                )
                sys.exit(1)
        else:
            print(f"❌ Download failed: {err}")
            sys.exit(1)

    result = parse_audio(str(local_path), args.prompt)
    print(result)


if __name__ == "__main__":
    main()
