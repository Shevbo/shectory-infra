#!/usr/bin/env python3
"""
🎭 Визард управления ролями и голосами.
Закреплённое сообщение с иконками ролей.
Клик → пошаговый мастер выбора.
"""

import json, os, sys, subprocess, urllib.request, urllib.parse

def _load_bot_token():
    with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
        cfg = json.load(f)
    accts = cfg.get('channels', {}).get('telegram', {}).get('accounts', {})
    return accts.get('default', {}).get('botToken', os.environ.get('BOT_TOKEN', ''))

BOT_TOKEN = _load_bot_token()
VOICES_JSON = os.path.expanduser("~/.openclaw/voices.json")
CHAT_ID = "36910539"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def tg(method, data=None):
    url = f"{API}/{method}"
    if data:
        data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def tg_send(chat_id: str, text: str, parse_mode: str = "Markdown") -> dict:
    """Send message via Lineman /api/tg/send (rate-limited, 1/15s)."""
    import urllib.request as _ur
    payload = json.dumps({
        "account": "default",
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": parse_mode,
    }).encode()
    req = _ur.Request(
        "http://127.0.0.1:9090/api/tg/send",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = _ur.urlopen(req, timeout=15)
        return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}

def load_data():
    if os.path.exists(VOICES_JSON):
        with open(VOICES_JSON) as f:
            return json.load(f)
    return {"voices": {}, "roles": {}}

def save_data(data):
    with open(VOICES_JSON, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

GEMINI_VOICES = {
    "Kore":    {"gender": "female", "desc": "Нейтральный, женский, тёплый"},
    "Puck":    {"gender": "male",   "desc": "Энергичный, молодой"},
    "Fenrir":  {"gender": "male",   "desc": "Низкий, мужской, уверенный"},
    "Charon":  {"gender": "male",   "desc": "Глубокий, спокойный"},
    "Aoede":   {"gender": "female", "desc": "Мягкий, мелодичный"},
    "Algieba": {"gender": "male",   "desc": "Уверенный, повествовательный"},
    "Dipper":  {"gender": "male",   "desc": "Дружелюбный, разговорный"},
}

# ===== КОНФИГУРАЦИЯ РОЛЕЙ =====
ROLE_CONFIG = {
    "nurse": {
        "display": "Медсестра",
        "icon": "🏥",
        "default_voice": "Kore",
        "gender": "female",
        "default_mode": "voice",
    },
    "developer": {
        "display": "Танк (CTO)",
        "icon": "🛠️",
        "default_voice": "Fenrir",
        "gender": "male",
        "default_mode": "text",
    },
    "jobsearch": {
        "display": "Работа",
        "icon": "💼",
        "default_voice": "Puck",
        "gender": "male",
        "default_mode": "text",
    },
}

def get_active_role(data):
    """Вернуть id активной роли."""
    roles = data.get("roles", {})
    for rid, rcfg in roles.items():
        if rcfg.get("active", False):
            return rid
    # fallback
    return "developer"

def get_role_state(data, role_id):
    """Вернуть состояние роли: voice, mode, gender."""
    roles = data.get("roles", {})
    rcfg = roles.get(role_id, {})
    return {
        "voice": rcfg.get("voice", ROLE_CONFIG.get(role_id, {}).get("default_voice", "Kore")),
        "mode": rcfg.get("mode", ROLE_CONFIG.get(role_id, {}).get("default_mode", "text")),
        "gender": rcfg.get("gender", ROLE_CONFIG.get(role_id, {}).get("gender", "male")),
    }

# ===== BUILDERS =====

def build_main_panel(data):
    """Главная панель с иконками ролей."""
    active = get_active_role(data)
    roles = data.get("roles", ROLE_CONFIG)

    lines = ["🎭 **Роли**\n"]
    for rid, rcfg in ROLE_CONFIG.items():
        state = get_role_state(data, rid)
        icon = rcfg["icon"]
        marker = "●" if rid == active else "○"
        vname = state["voice"]
        vinfo = GEMINI_VOICES.get(vname, {})
        gend = "♀" if vinfo.get("gender") == "female" else "♂"
        mode_icon = "🎙️" if state["mode"] == "voice" else "📝"
        lines.append(f"{marker} {icon}  {rcfg['display']}    {mode_icon}  {gend} {vname}")

    # Текущее состояние
    act = ROLE_CONFIG.get(active, {})
    astate = get_role_state(data, active)
    lines.append(f"\n_Сейчас: {act.get('icon','')} {act.get('display','')} • "
                 f"{'🎙️ голосом' if astate['mode']=='voice' else '📝 текстом'} • "
                 f"{astate['voice']}_")

    text = "\n".join(lines)

    # Кнопки — только иконки в одну строку
    kb_row1 = []
    for rid, rcfg in ROLE_CONFIG.items():
        state = get_role_state(data, rid)
        mode_icon = "🎙️" if state["mode"] == "voice" else "📝"
        is_active = (rid == active)
        btn_text = f"{'➡️' if is_active else ''}{rcfg['icon']} {mode_icon}"
        kb_row1.append({"text": btn_text.strip(), "callback_data": f"wiz_click_{rid}"})

    keyboard = [kb_row1]
    return text, keyboard

def build_wizard_step(data, role_id, step):
    """
    Визард: пошаговый мастер.
    step: 'role' | 'voice' | 'prompt'
    """
    rcfg = ROLE_CONFIG.get(role_id, {})
    state = get_role_state(data, role_id)

    if step == "role":
        # Шаг 1: выбор роли
        lines = [f"🎭 **Выбор роли**\n"]
        keyboard = []
        for rid, rcfg2 in ROLE_CONFIG.items():
            s = get_role_state(data, rid)
            marker = "●" if rid == role_id else "○"
            m = "🎙️" if s["mode"] == "voice" else "📝"
            lines.append(f"{marker} {rcfg2['icon']} {rcfg2['display']}  {m}")
            keyboard.append([{
                "text": f"{rcfg2['icon']} {rcfg2['display']}",
                "callback_data": f"wiz_select_{rid}"
            }])
        keyboard.append([{"text": "🔙 На главную", "callback_data": "wiz_main"}])
        return "\n".join(lines), keyboard

    elif step == "voice":
        # Шаг 2: выбор голоса
        lines = [f"🎤 **Выбор голоса**\n"]
        lines.append(f"Роль: {rcfg['icon']} {rcfg['display']}\n")
        keyboard = []
        for vname, vinfo in GEMINI_VOICES.items():
            icon = "♀️" if vinfo["gender"] == "female" else "♂️"
            marker = "✅" if vname == state["voice"] else "  "
            lines.append(f"{marker} {icon} {vname} — {vinfo['desc']}")
            keyboard.append([{
                "text": f"{icon} {vname}",
                "callback_data": f"wiz_voice_{role_id}_{vname}"
            }])
        keyboard.append([{"text": "🔙 К ролям", "callback_data": f"wiz_role_{role_id}"}])
        return "\n".join(lines), keyboard

    elif step == "prompt":
        # Шаг 3: настройка промпта
        vname = state["voice"]
        vinfo = GEMINI_VOICES.get(vname, {})
        gend = "женский" if vinfo.get("gender") == "female" else "мужской"
        lines = [
            f"✏️ **Промпт голоса**",
            f"",
            f"Роль: {rcfg['icon']} {rcfg['display']}",
            f"Голос: {vname} ({gend})",
            f"",
            f"Текущий промпт:",
            f"_{state.get('prompt', 'Не задан')}_",
            f"",
            f"Напиши новый промпт текстом в чат.",
            f"Формат: `промпт {role_id}: твой текст`",
        ]
        keyboard = [
            [{"text": "🔙 К голосам", "callback_data": f"wiz_voice_{role_id}"}],
        ]
        return "\n".join(lines), keyboard

def update_message(msg_id, text, keyboard):
    data = {
        "chat_id": CHAT_ID,
        "message_id": msg_id,
        "parse_mode": "Markdown",
    }
    if text:
        data["text"] = text
    if keyboard:
        data["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    return tg("editMessageText" if text else "editMessageReplyMarkup", data)

# ===== CALLBACK HANDLER =====

def handle(callback_data):
    parts = callback_data.split("_")
    action = parts[0] if parts else ""

    if action == "wiz":
        sub = parts[1] if len(parts) > 1 else ""

        if sub == "main":
            data = load_data()
            text, kb = build_main_panel(data)
            return ("edit", text, kb)

        elif sub == "click":
            # Клик по иконке роли — открываем визард на шаге выбора роли
            role_id = "_".join(parts[2:]) if len(parts) > 2 else "developer"
            data = load_data()
            text, kb = build_wizard_step(data, role_id, "role")
            return ("edit", text, kb)

        elif sub == "select":
            # Выбрали конкретную роль
            role_id = "_".join(parts[2:]) if len(parts) > 2 else "developer"
            data = load_data()
            roles = data.get("roles", {})

            # Активируем только эту роль
            for rid in ROLE_CONFIG:
                if rid in roles:
                    roles[rid]["active"] = (rid == role_id)

            # Инициализируем если нет
            rcfg = ROLE_CONFIG.get(role_id, {})
            if role_id not in roles:
                roles[role_id] = {
                    "voice": rcfg.get("default_voice", "Kore"),
                    "mode": rcfg.get("default_mode", "text"),
                    "gender": rcfg.get("gender", "male"),
                    "active": True,
                }

            save_data(data)

            # Переходим к шагу выбора голоса
            text, kb = build_wizard_step(data, role_id, "voice")
            return ("edit", text, kb)

        elif sub == "voice":
            if len(parts) == 3:
                # Показать список голосов для роли
                role_id = parts[2]
                data = load_data()
                text, kb = build_wizard_step(data, role_id, "voice")
                return ("edit", text, kb)
            else:
                # Выбор конкретного голоса для роли
                role_id = parts[2]
                vname = parts[3]
                data = load_data()
                roles = data.get("roles", {})
                if role_id in roles:
                    roles[role_id]["voice"] = vname
                    vinfo = GEMINI_VOICES.get(vname, {})
                    roles[role_id]["gender"] = vinfo.get("gender", "male")
                    save_data(data)

                # Переходим к шагу промпта
                text, kb = build_wizard_step(data, role_id, "prompt")
                return ("edit", text, kb)

        elif sub == "role":
            # Назад к выбору роли
            role_id = "_".join(parts[2:]) if len(parts) > 2 else "developer"
            data = load_data()
            text, kb = build_wizard_step(data, role_id, "role")
            return ("edit", text, kb)

    return ("ignore", None, None)

# ===== MAIN =====

def send_panel(pin=True):
    data = load_data()
    text, keyboard = build_main_panel(data)
    resp = tg("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps({"inline_keyboard": keyboard}),
    })
    if pin and resp.get("ok"):
        msg_id = resp["result"]["message_id"]
        tg("pinChatMessage", {
            "chat_id": CHAT_ID,
            "message_id": msg_id,
            "disable_notification": True
        })
    return resp

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "send":
        send_panel("--no-pin" not in sys.argv)

    elif cmd == "callback":
        cb_data = sys.argv[2] if len(sys.argv) > 2 else ""
        msg_id = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else None
        action, text, kb = handle(cb_data)
        if action == "edit" and msg_id:
            update_message(msg_id, text, kb)

    else:
        print("send | callback <data> <msg_id>")
