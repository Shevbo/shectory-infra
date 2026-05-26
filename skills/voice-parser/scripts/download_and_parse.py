#!/usr/bin/env python3
"""
Download Telegram voice file by file_id and transcribe via Gemini.
Usage:
  python3 download_and_parse.py <file_id> [prompt]

Gets bot token from openclaw.json (default account).
Downloads to ~/.openclaw/media/inbound/, then calls parse_voice.py.
"""

import sys, os, json, requests
from pathlib import Path
from parse_voice import parse_audio

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
INBOUND_DIR = Path.home() / ".openclaw/media/inbound"
PROXY = "http://127.0.0.1:9090"


def get_bot_token() -> str:
    d = json.loads(Path(CONFIG_PATH).read_text())
    accounts = d.get("channels", {}).get("telegram", {}).get("accounts", {})
    # Try default first, then interview-coach
    for account_id in ("interview-coach", "default"):
        token = accounts.get(account_id, {})
        if isinstance(token, str):
            return token
        if isinstance(token, dict):
            t = token.get("botToken", "")
            if t:
                return t
    return ""


def download_voice(file_id: str, bot_token: str) -> Path:
    proxies = {"https": PROXY, "http": PROXY}

    # Step 1: getFile — get file_path
    url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
    r = requests.get(url, proxies=proxies, timeout=15)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"getFile failed: {data.get('description', data)}")

    file_path = data["result"]["file_path"]
    ext = os.path.splitext(file_path)[1] or ".ogg"

    # Step 2: download
    dl_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    r2 = requests.get(dl_url, proxies=proxies, timeout=30)
    r2.raise_for_status()

    INBOUND_DIR.mkdir(parents=True, exist_ok=True)
    local_path = INBOUND_DIR / f"tg_{file_id[:16]}{ext}"
    local_path.write_bytes(r2.content)
    return local_path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    file_id = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else None

    token = get_bot_token()
    if not token:
        print("❌ Bot token not found in openclaw.json")
        sys.exit(1)

    print(f"⬇️  Downloading file_id: {file_id[:20]}...")
    try:
        local_path = download_voice(file_id, token)
        print(f"✅ Saved: {local_path}")
    except Exception as e:
        print(f"❌ Download failed: {e}")
        sys.exit(1)

    result = parse_audio(str(local_path), prompt)
    print(result)


if __name__ == "__main__":
    main()
