#!/usr/bin/env python3
"""
Управление голосовыми профилями — CRUD, тест, привязка к ролям.
Использование:
  voices.py list                          — список всех профилей
  voices.py show <id>                     — детали профиля
  voices.py create <id> <name> <voice>    — создать (id, отображаемое имя, голос Gemini)
  voices.py set-prompt <id> <prompt>       — установить промпт голоса
  voices.py set-voice <id> <voiceName>     — сменить голос (Kore, Puck, Fenrir...)
  voices.py test <id> [текст]              — тест TTS (отправить голосовое в Telegram)
  voices.py assign <id> <role>            — привязать к роли
  voices.py delete <id>                   — удалить профиль
  voices.py roles                         — список ролей и привязок
"""

import sys, os, json, time, base64, subprocess, io, tempfile
from datetime import datetime

STORAGE = os.path.expanduser("~/.openclaw/voices.json")
CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")

# ─── Загрузка/сохранение ───
def load():
    if os.path.exists(STORAGE):
        with open(STORAGE) as f:
            return json.load(f)
    return {"voices": {}, "roles": {}}

def save(data):
    os.makedirs(os.path.dirname(STORAGE), exist_ok=True)
    with open(STORAGE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_cfg():
    with open(CONFIG) as f:
        return json.load(f)

# ─── Доступные голоса Gemini ───
GEMINI_VOICES = {
    "Kore": "Нейтральный, женский, тёплый",
    "Puck": "Энергичный, молодой",
    "Fenrir": "Низкий, мужской, уверенный",
    "Charon": "Глубокий, спокойный",
    "Aoede": "Мягкий, мелодичный",
    "Algieba": "Уверенный, повествовательный",
    "Dipper": "Дружелюбный, разговорный",
}

# ─── Default профили ───
DEFAULT_VOICES = {
    "medsestra": {
        "name": "Медсестра",
        "description": "Заботливая медсестра психологической поддержки",
        "provider": "google",
        "model": "gemini-2.5-flash-preview-tts",
        "voiceName": "Kore",
        "prompt": "Speak in a calm, caring, soft voice. Warm, empathetic, never clinical. You are a gentle nurse providing psychological support. A warm, trusting evening conversation. Close, confidential contact.",
        "assignedTo": ["nurse"],
        "createdAt": "2026-05-07T00:00:00Z",
        "updatedAt": "2026-05-07T00:00:00Z"
    },
    "developer": {
        "name": "Разработчик",
        "description": "Технический консультант по разработке",
        "provider": "google",
        "model": "gemini-2.5-flash-preview-tts",
        "voiceName": "Fenrir",
        "prompt": "Speak with technical confidence. Clear, precise, professional. A technical standup or code review session. Direct, factual, efficient.",
        "assignedTo": ["developer"],
        "createdAt": "2026-05-07T00:00:00Z",
        "updatedAt": "2026-05-07T00:00:00Z"
    }
}

def init_defaults():
    data = load()
    changed = False
    for vid, v in DEFAULT_VOICES.items():
        if vid not in data["voices"]:
            data["voices"][vid] = v
            changed = True
    if "nurse" not in data["roles"]:
        data["roles"]["nurse"] = {"voiceId": "medsestra", "systemPrompt": "Ты — медсестра психологической поддержки. Мягкая, эмпатичная, без диагнозов."}
        changed = True
    if "developer" not in data["roles"]:
        data["roles"]["developer"] = {"voiceId": "developer", "systemPrompt": "Ты — технический разработчик. Чёткий, профессиональный."}
        changed = True
    if changed:
        save(data)
    return data

# ─── Красивый вывод ───
def fmt_voice(vid, v):
    role = ""
    for r, rv in init_defaults()["roles"].items():
        if rv.get("voiceId") == vid:
            role = f" → роль: {r}"
    return (f"🎤 [{vid}] {v['name']}{role}\n"
            f"   Голос: {v.get('voiceName','?')} ({GEMINI_VOICES.get(v.get('voiceName',''),'?')})\n"
            f"   Провайдер: {v.get('provider','?')} / {v.get('model','?')}\n"
            f"   Промпт: {v.get('prompt','')[:100]}...\n"
            f"   Создан: {v.get('createdAt','?')[:10]}")

def fmt_role(rid, r):
    v = init_defaults()["voices"].get(r.get("voiceId",""), {})
    return f"📌 [{rid}] голос: {v.get('name','?')} ({r.get('voiceId','?')})"

# ─── CRUD ───
def cmd_list():
    init_defaults()
    data = load()
    if not data["voices"]:
        return "Нет голосовых профилей. Используйте `/voices create`."
    lines = ["🎭 **Голосовые профили:**"]
    for vid, v in data["voices"].items():
        lines.append(f"\n{fmt_voice(vid, v)}")
    return "\n".join(lines)

def cmd_show(vid):
    data = load()
    v = data["voices"].get(vid)
    if not v:
        return f"❌ Профиль '{vid}' не найден."
    return fmt_voice(vid, v)

def cmd_create(vid, name, voice="Kore"):
    data = load()
    if vid in data["voices"]:
        return f"❌ Профиль '{vid}' уже существует."
    if voice not in GEMINI_VOICES:
        return f"❌ Голос '{voice}' не найден. Доступны: {', '.join(GEMINI_VOICES.keys())}"
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    data["voices"][vid] = {
        "name": name,
        "description": "",
        "provider": "google",
        "model": "gemini-2.5-flash-preview-tts",
        "voiceName": voice,
        "prompt": "",
        "assignedTo": [],
        "createdAt": now,
        "updatedAt": now
    }
    save(data)
    return f"✅ Создан профиль '{vid}' ({name}, голос {voice})."

def cmd_set_prompt(vid, prompt):
    data = load()
    if vid not in data["voices"]:
        return f"❌ Профиль '{vid}' не найден."
    data["voices"][vid]["prompt"] = prompt
    data["voices"][vid]["updatedAt"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    save(data)
    return f"✅ Промпт для '{vid}' обновлён."

def cmd_set_voice(vid, voice):
    if voice not in GEMINI_VOICES:
        return f"❌ Голос '{voice}' не найден. Доступны: {', '.join(GEMINI_VOICES.keys())}"
    data = load()
    if vid not in data["voices"]:
        return f"❌ Профиль '{vid}' не найден."
    data["voices"][vid]["voiceName"] = voice
    data["voices"][vid]["updatedAt"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    save(data)
    return f"✅ Голос '{vid}' изменён на {voice} ({GEMINI_VOICES[voice]})."

def cmd_assign(vid, role):
    data = load()
    if vid not in data["voices"]:
        return f"❌ Профиль '{vid}' не найден."
    # Создаём роль, если нет
    if role not in data["roles"]:
        data["roles"][role] = {"voiceId": vid, "systemPrompt": ""}
    else:
        data["roles"][role]["voiceId"] = vid
    save(data)
    return f"✅ Голос '{vid}' привязан к роли '{role}'."

def cmd_delete(vid):
    data = load()
    if vid not in data["voices"]:
        return f"❌ Профиль '{vid}' не найден."
    del data["voices"][vid]
    # Отвязываем от ролей
    for r in data["roles"]:
        if data["roles"][r].get("voiceId") == vid:
            data["roles"][r]["voiceId"] = ""
    save(data)
    return f"🗑️ Профиль '{vid}' удалён."

def cmd_roles():
    data = load()
    if not data["roles"]:
        return "Нет назначенных ролей."
    lines = ["📌 **Роли и голоса:**"]
    for rid, r in data["roles"].items():
        lines.append(f"\n{fmt_role(rid, r)}")
        if r.get("systemPrompt"):
            lines.append(f"   Промпт: {r['systemPrompt'][:100]}...")
    return "\n".join(lines)

def cmd_available_voices():
    lines = ["🎤 **Доступные голоса Gemini:**"]
    for v, desc in GEMINI_VOICES.items():
        lines.append(f"\n- **{v}**: {desc}")
    return "\n".join(lines)

# ─── TTS тест ───
def cmd_test(vid, text="Привет. Я голосовой профиль для этого ассистента. Проверка связи."):
    import requests
    
    data = load()
    v = data["voices"].get(vid)
    if not v:
        return f"❌ Профиль '{vid}' не найден."
    
    cfg = load_cfg()
    api_key = cfg["models"]["providers"]["google"]["apiKey"]
    proxy_url = cfg["models"]["providers"]["google"]["request"]["proxy"]["url"]
    proxies = {"https": proxy_url, "http": proxy_url}
    
    # TTS
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v["voiceName"]}}}
        }
    }
    # Промпт влияет на стиль через voiceName, не передаётся в TTS API
    
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{v['model']}:generateContent?key={api_key}",
        json=body, proxies=proxies, timeout=30
    )
    if r.status_code != 200:
        return f"❌ TTS API: HTTP {r.status_code} — {r.text[:200]}"
    
    result = r.json()
    if "candidates" not in result:
        return f"❌ Ответ TTS: {json.dumps(result, ensure_ascii=False)[:200]}"
    
    pcm_data = None
    for p in result["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            pcm_data = base64.b64decode(p["inlineData"]["data"])
            break
    
    if not pcm_data:
        return "❌ Нет аудио в ответе."
    
    # PCM → OGG
    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
        "-c:a", "libopus", "-b:a", "16k", "-vbr", "on", "-application", "voip", "-f", "ogg", "pipe:1"
    ], input=pcm_data, capture_output=True)
    
    # Отправляем в Telegram
    bot_token = cfg["channels"]["telegram"]["botToken"]
    chat_id = cfg["channels"]["telegram"].get("allowFrom", ["?","?"])[0].replace("tg:", "")
    
    r = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendVoice",
        data={"chat_id": chat_id, "caption": f"🎤 Тест: {vid} ({v['voiceName']})"},
        files={"voice": ("voice.ogg", io.BytesIO(proc.stdout), "audio/ogg")},
        proxies=proxies, timeout=30
    )
    result = r.json()
    if result.get("ok"):
        return f"✅ Тест для '{vid}' отправлен (голос {v['voiceName']})."
    return f"❌ Ошибка отправки: {result}"


if __name__ == "__main__":
    init_defaults()
    
    if len(sys.argv) < 2:
        print("Использование: voices.py <command> [args...]")
        print("  list, show, create, set-prompt, set-voice, assign, delete, roles, voices, test")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "list":
        print(cmd_list())
    elif cmd == "show" and len(sys.argv) >= 3:
        print(cmd_show(sys.argv[2]))
    elif cmd == "create" and len(sys.argv) >= 4:
        voice = sys.argv[4] if len(sys.argv) >= 5 else "Kore"
        print(cmd_create(sys.argv[2], sys.argv[3], voice))
    elif cmd == "set-prompt" and len(sys.argv) >= 4:
        print(cmd_set_prompt(sys.argv[2], sys.argv[3]))
    elif cmd == "set-voice" and len(sys.argv) >= 4:
        print(cmd_set_voice(sys.argv[2], sys.argv[3]))
    elif cmd == "assign" and len(sys.argv) >= 4:
        print(cmd_assign(sys.argv[2], sys.argv[3]))
    elif cmd == "delete" and len(sys.argv) >= 3:
        print(cmd_delete(sys.argv[2]))
    elif cmd == "roles":
        print(cmd_roles())
    elif cmd == "voices":
        print(cmd_available_voices())
    elif cmd == "test" and len(sys.argv) >= 3:
        text = sys.argv[3] if len(sys.argv) >= 4 else None
        print(cmd_test(sys.argv[2], text))
    else:
        print("Неизвестная команда.")
        sys.exit(1)
