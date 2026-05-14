#!/usr/bin/env python3
"""
Обработчик callback_query от inline-кнопок Telegram.
Работает параллельно с OpenClaw, обрабатывает только callback_query.
Запускается как фоновый процесс.
"""

import json, os, sys, time, urllib.request, urllib.parse
from pathlib import Path

def _load_bot_token():
    with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
        cfg = json.load(f)
    accts = cfg.get('channels', {}).get('telegram', {}).get('accounts', {})
    def_tok = accts.get('default', {}).get('botToken', '')
    return def_tok or os.environ.get('BOT_TOKEN', '')

BOT_TOKEN = _load_bot_token()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
STATE_FILE = os.path.expanduser("~/.openclaw/callback_offset.json")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PANEL_SCRIPT = os.path.join(SCRIPT_DIR, "voice_wizard.py")

def tg(method, data=None):
    url = f"{API}/{method}"
    if data:
        data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def get_offset():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0

def save_offset(offset):
    with open(STATE_FILE, "w") as f:
        json.dump({"offset": offset, "updated": time.time()}, f)

def process_callback(cb):
    """Обработать callback_query."""
    cb_id = cb.get("id")
    data = cb.get("data", "")
    msg = cb.get("message", {})
    msg_id = msg.get("message_id")
    chat_id = msg.get("chat", {}).get("id")

    if not chat_id or not data:
        return False

    print(f"  Callback: {data} (msg_id={msg_id})")

    import subprocess
    result = subprocess.run(
        ["python3", PANEL_SCRIPT, "callback", data, str(msg_id or "")],
        capture_output=True, text=True, timeout=15
    )

    # Отвечаем на callback (убираем часики)
    tg("answerCallbackQuery", {"callback_query_id": cb_id})

    return True

def poll_once(offset):
    """Один цикл polling."""
    params = {
        "offset": offset,
        "timeout": 10,
        "allowed_updates": json.dumps(["callback_query"])
    }
    try:
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(f"{API}/getUpdates", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
    except Exception as e:
        print(f"Poll error: {e}")
        return offset

    if not result.get("ok"):
        return offset

    max_offset = offset
    for update in result.get("result", []):
        upd_id = update.get("update_id", 0)
        if upd_id >= max_offset:
            max_offset = upd_id + 1

        cb = update.get("callback_query")
        if cb:
            process_callback(cb)

    return max_offset

def main():
    print("🔄 Callback handler started")
    offset = get_offset()
    print(f"  Starting offset: {offset}")

    while True:
        try:
            new_offset = poll_once(offset)
            if new_offset != offset:
                save_offset(new_offset)
                offset = new_offset
        except KeyboardInterrupt:
            print("\n⏹️  Stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
