#!/usr/bin/env python3
"""Telegram inline keyboard для управления голосовыми профилями.

Использование:
  python3 voices_bot.py send-panel         — отправить панель управления
  python3 voices_bot.py handle-callback    — обработать callback_query
"""

import json, sys, os, subprocess, time

def _load_bot_token():
    with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
        cfg = json.load(f)
    accts = cfg.get('channels', {}).get('telegram', {}).get('accounts', {})
    # main-sdev or default
    tok = accts.get('main-sdev', {}).get('botToken', '') or \
          accts.get('default', {}).get('botToken', '') or \
          os.environ.get('BOT_TOKEN', '')
    return tok

BOT_TOKEN = _load_bot_token()
VOICES_SCRIPT = os.path.expanduser("~/skills/voice-profiles/scripts/voices.py")
CHAT_ID = "36910539"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
_LINEMAN = "http://127.0.0.1:9090"

def tg(method, data=None):
    """Вызов Telegram Bot API через Lineman прокси."""
    import urllib.request, urllib.parse
    url = f"{API}/{method}"
    if data:
        data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data)
    proxy = urllib.request.ProxyHandler({"http": _LINEMAN, "https": _LINEMAN})
    opener = urllib.request.build_opener(proxy)
    with opener.open(req) as r:
        return json.loads(r.read())

def run_voices(*args):
    """Выполнить voices.py и вернуть результат."""
    result = subprocess.run(
        [VOICES_SCRIPT] + list(args),
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip()

def send_panel():
    """Отправить панель управления голосами."""
    # Получаем список профилей
    voices_out = run_voices("list")
    roles_out = run_voices("roles")

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎤 Список голосов", "callback_data": "voice_list"},
                {"text": "📋 Роли", "callback_data": "voice_roles"},
            ],
            [
                {"text": "🎭 Сменить голос роли", "callback_data": "voice_change"},
                {"text": "🔊 Тест голоса", "callback_data": "voice_test"},
            ],
            [
                {"text": "✏️ Сменить промпт", "callback_data": "voice_prompt"},
                {"text": "🔄 Закрыть", "callback_data": "voice_close"},
            ],
        ]
    }

    text = (
        f"🎤 **Управление голосами**\n\n"
        f"Доступные голоса Gemini:\n"
        f"• Kore — тёплый, женский\n"
        f"• Fenrir — низкий, мужской\n"
        f"• Puck — энергичный\n"
        f"• Charon — глубокий, спокойный\n"
        f"• Aoede — мягкий, мелодичный\n\n"
        f"_Ниже кнопки управления_\n"
        f"Просто нажми — я выполню 🛠️"
    )

    resp = tg("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    })
    return resp

def handle_callback(callback_data):
    """Обработать нажатие кнопки."""
    actions = {
        "voice_list": lambda: f"📋 **Список голосов:**\n\n```\n{run_voices('list')}\n```",
        "voice_roles": lambda: f"📌 **Роли:**\n\n```\n{run_voices('roles')}\n```",
        "voice_test": lambda: "🔊 Напиши **тест <имя_профиля>** — например: `тест medsestra`",
        "voice_change": lambda: "🎭 Напиши **сменить <профиль> <голос>** — например: `сменить medsestra Puck`\n\nДоступные голоса: Kore, Fenrir, Puck, Charon, Aoede, Dipper",
        "voice_prompt": lambda: "✏️ Напиши **промпт <профиль> <текст>** — новый стиль речи",
        "voice_close": lambda: None,
    }

    action = actions.get(callback_data)
    if not action:
        return "❓ Неизвестная кнопка"

    result = action()
    if callback_data == "voice_close":
        tg("deleteMessage", {
            "chat_id": CHAT_ID,
            "message_id": "remove_latest"  # нужно будет подставить
        })
        return None

    return result

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "send-panel":
            send_panel()
        elif cmd == "handle-callback":
            data = sys.argv[2] if len(sys.argv) > 2 else ""
            result = handle_callback(data)
            if result:
                print(result)
        else:
            print(f"Неизвестная команда: {cmd}")
    else:
        send_panel()
