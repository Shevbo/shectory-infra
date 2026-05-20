#!/usr/bin/env python3
"""
Voice Wizard v2 — управление голосом агента через Telegram ReplyKeyboard.
Вызывается агентом через exec. Все вызовы Telegram через Lineman.

Использование:
  voice_wizard.py show <agent_id> <chat_id>         — показать текущие настройки + меню
  voice_wizard.py voices <agent_id> <chat_id>        — показать выбор голоса (ReplyKeyboard)
  voice_wizard.py test <agent_id> <chat_id>          — TTS тест текущего голоса
  voice_wizard.py test_voice <agent_id> <chat_id> <voice_name>  — TTS тест указанного голоса
  voice_wizard.py select <agent_id> <chat_id> <voice_name>     — выбрать и сохранить голос
  voice_wizard.py prompt <agent_id> <chat_id>        — показать текущий промпт + просьба ввести
  voice_wizard.py save_prompt <agent_id> <chat_id> <text...>   — сохранить голосовой промпт
  voice_wizard.py state <agent_id> <chat_id>         — показать текущее состояние визарда
  voice_wizard.py cancel <agent_id> <chat_id>        — отмена визарда, убрать клавиатуру
"""

import json, os, sys, urllib.request, urllib.parse, subprocess, time

LINEMAN   = "http://127.0.0.1:9090"
VOICES_DB = os.path.expanduser("~/.openclaw/voices.json")
OC_CFG    = os.path.expanduser("~/.openclaw/openclaw.json")
STATE_DIR = os.path.expanduser("~/.openclaw/wizard_state")
TTS_SCRIPT = os.path.expanduser("~/skills/voice-profiles/scripts/tts_flow.py")
MEDIA_DIR  = os.path.expanduser("~/.openclaw/media/outbound")

os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# Full Gemini 2.5 TTS voice list (34 voices)
GEMINI_VOICES = {
    "Aoede":       {"gender": "female", "desc": "Мягкий, мелодичный"},
    "Charon":      {"gender": "male",   "desc": "Глубокий, спокойный"},
    "Fenrir":      {"gender": "male",   "desc": "Низкий, уверенный"},
    "Kore":        {"gender": "female", "desc": "Нейтральный, тёплый"},
    "Puck":        {"gender": "male",   "desc": "Энергичный, молодой"},
    "Zephyr":      {"gender": "female", "desc": "Лёгкий, воздушный"},
    "Achernar":    {"gender": "female", "desc": "Яркий, живой"},
    "Gacrux":      {"gender": "female", "desc": "Зрелый, душевный"},
    "Pulchra":     {"gender": "female", "desc": "Красивый, выразительный"},
    "Schedar":     {"gender": "female", "desc": "Мягкий, тихий"},
    "Sulafat":     {"gender": "female", "desc": "Тёплый, успокаивающий"},
    "Callirrhoe":  {"gender": "female", "desc": "Плавный, естественный"},
    "Anthe":       {"gender": "female", "desc": "Нежный, деликатный"},
    "Despina":     {"gender": "female", "desc": "Чёткий, профессиональный"},
    "Erinome":     {"gender": "female", "desc": "Ясный, нейтральный"},
    "Laomedeia":   {"gender": "female", "desc": "Позитивный, дружелюбный"},
    "Vindemiatrix":{"gender": "female", "desc": "Умный, аналитический"},
    "Algieba":     {"gender": "male",   "desc": "Уверенный, повествовательный"},
    "Rasalhague":  {"gender": "male",   "desc": "Авторитетный, серьёзный"},
    "Algol":       {"gender": "male",   "desc": "Деловой, сдержанный"},
    "Arcturus":    {"gender": "male",   "desc": "Командный, решительный"},
    "Alnilam":     {"gender": "male",   "desc": "Сильный, ораторский"},
    "Polaris":     {"gender": "male",   "desc": "Прямой, точный"},
    "Sadachbia":   {"gender": "male",   "desc": "Мудрый, размеренный"},
    "Sadaltager":  {"gender": "male",   "desc": "Спокойный, вдумчивый"},
    "Tarazed":     {"gender": "male",   "desc": "Плавный, мужской"},
    "Umbriel":     {"gender": "male",   "desc": "Тёмный, глубокий"},
    "Diphda":      {"gender": "male",   "desc": "Нейтральный, чёткий"},
    "Elara":       {"gender": "female", "desc": "Дружелюбный, активный"},
    "Isonoe":      {"gender": "female", "desc": "Тихий, задумчивый"},
    "Kalyke":      {"gender": "female", "desc": "Резкий, энергичный"},
    "Navi":        {"gender": "female", "desc": "Чистый, современный"},
    "Stephano":    {"gender": "male",   "desc": "Разговорный, обаятельный"},
    "Tethys":      {"gender": "female", "desc": "Мягкий, мечтательный"},
}

TEST_PHRASE = "Привет! Это тестовая фраза. Как звучит мой голос?"


def load_token(account: str) -> str:
    with open(OC_CFG) as f:
        cfg = json.load(f)
    accts = cfg.get("channels", {}).get("telegram", {}).get("accounts", {})
    tok = accts.get(account, {}).get("botToken", "")
    if not tok:
        tok = accts.get("default", {}).get("botToken", "")
    return tok


def tg_call(account: str, method: str, data: dict) -> dict:
    token = load_token(account)
    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = urllib.parse.urlencode(
        {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in data.items()}
    ).encode()
    proxy = urllib.request.ProxyHandler({"https": LINEMAN, "http": LINEMAN})
    opener = urllib.request.build_opener(proxy)
    req = urllib.request.Request(url, data=payload)
    with opener.open(req, timeout=20) as r:
        return json.loads(r.read())


def tg_send_audio(account: str, chat_id: str, audio_path: str, caption: str = "") -> dict:
    token = load_token(account)
    url = f"https://api.telegram.org/bot{token}/sendVoice"
    import mimetypes
    boundary = "----FormBoundary" + str(int(time.time()))
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="voice"; filename="voice.ogg"\r\n'
        f"Content-Type: audio/ogg\r\n\r\n"
    ).encode() + audio_data + (
        f"\r\n--{boundary}--\r\n"
    ).encode()
    if caption:
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
        ).encode() + body[len(f"--{boundary}\r\n".encode()):]

    proxy = urllib.request.ProxyHandler({"https": LINEMAN, "http": LINEMAN})
    opener = urllib.request.build_opener(proxy)
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with opener.open(req, timeout=30) as r:
        return json.loads(r.read())


def load_voices_db() -> dict:
    if os.path.exists(VOICES_DB):
        with open(VOICES_DB) as f:
            return json.load(f)
    return {"voices": {}, "roles": {}}


def save_voices_db(data: dict):
    with open(VOICES_DB, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_agent_voice(agent_id: str) -> str:
    db = load_voices_db()
    roles = db.get("roles", {})
    role = roles.get(agent_id, {})
    vid = role.get("voiceId") or role.get("voice", "")
    if vid:
        v = db.get("voices", {}).get(vid, {})
        return v.get("voiceName", vid)
    # fallback: read from openclaw.json agent tts.persona → voices.json
    with open(OC_CFG) as f:
        cfg = json.load(f)
    for a in cfg.get("agents", {}).get("list", []):
        if a["id"] == agent_id:
            persona = a.get("tts", {}).get("persona", agent_id)
            r = db.get("roles", {}).get(persona, {})
            vid2 = r.get("voiceId") or r.get("voice", "")
            if vid2:
                v = db.get("voices", {}).get(vid2, {})
                return v.get("voiceName", vid2)
    return "Kore"


def get_agent_prompt(agent_id: str) -> str:
    db = load_voices_db()
    roles = db.get("roles", {})
    role = roles.get(agent_id, {})
    return role.get("prompt", "")


def save_agent_voice(agent_id: str, voice_name: str):
    db = load_voices_db()
    roles = db.setdefault("roles", {})
    if agent_id not in roles:
        roles[agent_id] = {}
    roles[agent_id]["voice"] = voice_name
    roles[agent_id]["voiceId"] = voice_name
    save_voices_db(db)


def save_agent_prompt(agent_id: str, prompt: str):
    db = load_voices_db()
    roles = db.setdefault("roles", {})
    if agent_id not in roles:
        roles[agent_id] = {}
    roles[agent_id]["prompt"] = prompt
    save_voices_db(db)


def state_path(agent_id: str, chat_id: str) -> str:
    return os.path.join(STATE_DIR, f"{agent_id}_{chat_id}.json")


def get_state(agent_id: str, chat_id: str) -> dict:
    p = state_path(agent_id, chat_id)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"step": None}


def set_state(agent_id: str, chat_id: str, state: dict):
    p = state_path(agent_id, chat_id)
    with open(p, "w") as f:
        json.dump(state, f)


def clear_state(agent_id: str, chat_id: str):
    p = state_path(agent_id, chat_id)
    if os.path.exists(p):
        os.remove(p)


def remove_keyboard(account: str, chat_id: str, text: str = "Готово."):
    return tg_call(account, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": json.dumps({"remove_keyboard": True}),
    })


def send_voice_info(account: str, chat_id: str, agent_id: str):
    voice = get_agent_voice(agent_id)
    prompt = get_agent_prompt(agent_id)
    vinfo = GEMINI_VOICES.get(voice, {})
    gender = "женский" if vinfo.get("gender") == "female" else "мужской"
    prompt_display = prompt if prompt else "(не задан)"
    text = (
        f"*Настройки голоса — {agent_id}*\n\n"
        f"Голос: *{voice}* ({gender})\n"
        f"Описание: {vinfo.get('desc', '—')}\n\n"
        f"Системный промпт TTS:\n_{prompt_display}_"
    )
    keyboard = {
        "keyboard": [
            ["▶️ Послушать голос", "🎤 Изменить голос"],
            ["✏️ Изменить промпт", "✅ Готово"],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    return tg_call(account, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    })


def send_voices_keyboard(account: str, chat_id: str, agent_id: str):
    current = get_agent_voice(agent_id)
    # Build rows of 3 buttons
    female = [(n, i) for n, i in GEMINI_VOICES.items() if i["gender"] == "female"]
    male   = [(n, i) for n, i in GEMINI_VOICES.items() if i["gender"] == "male"]
    rows = []
    row = []
    for name, info in female:
        mark = "✅" if name == current else ""
        row.append(f"{mark}♀{name}")
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    row = []
    for name, info in male:
        mark = "✅" if name == current else ""
        row.append(f"{mark}♂{name}")
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append(["❌ Отмена"])

    text = (
        f"*Выберите голос* (текущий: *{current}*)\n"
        f"Нажмите — услышите тест. Потом «Выбрать».\n\n"
        f"♀ женские  ♂ мужские"
    )
    keyboard = {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": False}
    set_state(agent_id, chat_id, {"step": "select_voice"})
    return tg_call(account, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    })


def do_tts_test(voice_name: str) -> str | None:
    """Generate TTS for test phrase. Returns path to OGG file or None."""
    try:
        result = subprocess.run(
            ["python3", TTS_SCRIPT, "generate", voice_name, TEST_PHRASE],
            capture_output=True, text=True, timeout=30,
        )
        for line in result.stdout.splitlines():
            if line.startswith("MEDIA:"):
                path = line.replace("MEDIA:", "").split("[[")[0].strip()
                if os.path.exists(path):
                    return path
    except Exception as e:
        print(f"TTS error: {e}", file=sys.stderr)
    return None


# ===== COMMANDS =====

def cmd_show(agent_id, chat_id, account):
    send_voice_info(account, chat_id, agent_id)
    set_state(agent_id, chat_id, {"step": "main"})


def cmd_voices(agent_id, chat_id, account):
    send_voices_keyboard(account, chat_id, agent_id)


def cmd_test(agent_id, chat_id, account):
    voice = get_agent_voice(agent_id)
    tg_call(account, "sendMessage", {
        "chat_id": chat_id, "text": f"Генерирую тест голоса *{voice}*...", "parse_mode": "Markdown",
    })
    path = do_tts_test(voice)
    if path:
        tg_send_audio(account, chat_id, path, caption=f"Голос: {voice}")
    else:
        tg_call(account, "sendMessage", {"chat_id": chat_id, "text": "Ошибка генерации TTS."})


def cmd_test_voice(agent_id, chat_id, account, voice_name):
    tg_call(account, "sendMessage", {
        "chat_id": chat_id, "text": f"Тест голоса *{voice_name}*...", "parse_mode": "Markdown",
    })
    path = do_tts_test(voice_name)
    if path:
        # After test, offer select/cancel
        keyboard = {
            "keyboard": [
                [f"✅ Выбрать {voice_name}", "⬅️ Другой голос"],
                ["❌ Отмена"],
            ],
            "resize_keyboard": True,
        }
        tg_send_audio(account, chat_id, path, caption=f"Голос: {voice_name}")
        tg_call(account, "sendMessage", {
            "chat_id": chat_id,
            "text": f"Нравится голос *{voice_name}*?",
            "parse_mode": "Markdown",
            "reply_markup": json.dumps(keyboard),
        })
        set_state(agent_id, chat_id, {"step": "confirm_voice", "voice": voice_name})
    else:
        tg_call(account, "sendMessage", {"chat_id": chat_id, "text": "Ошибка TTS."})


def cmd_select(agent_id, chat_id, account, voice_name):
    save_agent_voice(agent_id, voice_name)
    remove_keyboard(account, chat_id, f"Голос сохранён: *{voice_name}*")
    clear_state(agent_id, chat_id)


def cmd_prompt(agent_id, chat_id, account):
    current = get_agent_prompt(agent_id)
    display = current if current else "(не задан)"
    keyboard = {
        "keyboard": [["❌ Отмена"]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }
    tg_call(account, "sendMessage", {
        "chat_id": chat_id,
        "text": (
            f"*Системный промпт TTS*\n\n"
            f"Текущий:\n_{display}_\n\n"
            f"Напишите новый промпт следующим сообщением.\n"
            f"Пример: _Говори медленно и с паузами, как терапевт._"
        ),
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    })
    set_state(agent_id, chat_id, {"step": "edit_prompt"})


def cmd_save_prompt(agent_id, chat_id, account, prompt_text):
    save_agent_prompt(agent_id, prompt_text)
    remove_keyboard(account, chat_id, f"Промпт сохранён.")
    clear_state(agent_id, chat_id)


def cmd_state(agent_id, chat_id, account):
    st = get_state(agent_id, chat_id)
    print(json.dumps(st))


def cmd_cancel(agent_id, chat_id, account):
    clear_state(agent_id, chat_id)
    remove_keyboard(account, chat_id, "Настройки голоса закрыты.")


# ===== ENTRY POINT =====

def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print(__doc__)
        sys.exit(1)

    cmd       = args[0]
    agent_id  = args[1]
    chat_id   = args[2]
    account   = agent_id  # account name matches agent_id in openclaw

    if cmd == "show":
        cmd_show(agent_id, chat_id, account)
    elif cmd == "voices":
        cmd_voices(agent_id, chat_id, account)
    elif cmd == "test":
        cmd_test(agent_id, chat_id, account)
    elif cmd == "test_voice" and len(args) >= 4:
        cmd_test_voice(agent_id, chat_id, account, args[3])
    elif cmd == "select" and len(args) >= 4:
        cmd_select(agent_id, chat_id, account, args[3])
    elif cmd == "prompt":
        cmd_prompt(agent_id, chat_id, account)
    elif cmd == "save_prompt" and len(args) >= 4:
        prompt_text = " ".join(args[3:])
        cmd_save_prompt(agent_id, chat_id, account, prompt_text)
    elif cmd == "state":
        cmd_state(agent_id, chat_id, account)
    elif cmd == "cancel":
        cmd_cancel(agent_id, chat_id, account)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
