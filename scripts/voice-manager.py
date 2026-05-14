#!/usr/bin/env python3
"""
Voice Manager — управление голосами агентов прямо в чате.
Вызывается командой /voice

Запуск: python3 ~/scripts/voice-manager.py <action> [args...]

Actions:
  menu <agent_id> <chat_id>   — главное меню
  list-voices                 — список Gemini голосов
  test <agent_id> <chat_id>   — тест голоса (10 слов)
  set-voice <agent> <voice>   — сменить голос агента
  edit-prompt <agent> <text>  — обновить промпт
"""

import json, os, sys, subprocess, tempfile
import requests, base64, time

# === CONFIG ===
CONFIG_PATH = os.path.expanduser('~/.openclaw/openclaw.json')
VOICES_PATH = os.path.expanduser('~/.openclaw/voices.json')

# Secrets — читаются из конфига, НЕ хардкодить!
def _load_secrets():
    with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
        cfg = json.load(f)
    google = cfg.get('models', {}).get('providers', {}).get('google', {})
    api_key = google.get('apiKey', '')
    base_url = google.get('baseUrl', 'https://gemini-proxy-worker.bshevelev75.workers.dev')
    proxy = google.get('request', {}).get('proxy', {}).get('url', '')
    tg = cfg.get('channels', {}).get('telegram', {})
    tg_proxy = tg.get('proxy', '')
    return {
        'api_key': api_key,
        'base_url': base_url,
        'proxy': proxy or tg_proxy,
        'tts_url': f"{base_url}/v1beta/models/gemini-2.5-flash-preview-tts:generateContent",
        'chat_id': '36910539',
    }

# Все известные Gemini голоса
GEMINI_VOICES = {
    "Charon": "Male, weathered, gravelled (architect)",
    "Fenrir": "Male, deep, resonant (developer)",
    "Dipper": "Male, young, friendly (coach)",
    "Puck": "Male, energetic, youthful",
    "Orus": "Male, athletic, commanding (titan)",
    "Kore": "Female, sharp, bold (medsestra)",
    "Athena": "Female, warm, wise",
    "Hera": "Female, mature, elegant",
    "Persephone": "Female, soft, melodic",
    "Zephyr": "Male, smooth, calm",
    "Leda": "Female, energetic, bright",
}

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_voices():
    with open(VOICES_PATH) as f:
        return json.load(f)

def save_voices(vcfg):
    with open(VOICES_PATH, 'w') as f:
        json.dump(vcfg, f, indent=4, ensure_ascii=False)

def get_bot_token(agent_id):
    """Получить токен бота для агента"""
    cfg = load_config()
    accts = cfg.get('channels', {}).get('telegram', {}).get('accounts', {})
    
    # Ищем аккаунт по agentId через bindings
    binds = cfg.get('bindings', [])
    for b in binds:
        if b.get('type') == 'route' and b.get('agentId') == agent_id:
            aid = b.get('match', {}).get('accountId', 'default')
            if aid in accts:
                tok = accts[aid].get('botToken', '')
                if tok: return tok
    
    # Fallback на default
    if 'default' in accts:
        return accts['default'].get('botToken', '')
    
    # По именам файлов
    tf_map = {
        'titan': os.path.expanduser('~/.openclaw/credentials/titan-token'),
        'virtual-boris': os.path.expanduser('~/.openclaw/credentials/virtual-boris-token'),
    }
    if agent_id in tf_map:
        with open(tf_map[agent_id]) as f:
            return f.read().strip()
    
    return None

def get_agent_info(agent_id):
    """Получить информацию об агенте"""
    cfg = load_config()
    for a in cfg.get('agents', {}).get('list', []):
        if a['id'] == agent_id:
            tts = a.get('tts', {})
            return {
                'name': a.get('name', agent_id),
                'persona': tts.get('persona', 'не задана'),
                'auto': tts.get('auto', 'off'),
            }
    return {'name': agent_id, 'persona': 'не задана', 'auto': 'off'}

def get_voice_prompt(agent_id):
    """Получить текущий промпт голоса агента"""
    vcfg = load_voices()
    info = get_agent_info(agent_id)
    persona = info['persona']
    
    for vname, v in vcfg.get('voices', {}).items():
        if agent_id in v.get('assignedTo', []) or vname == persona:
            return {
                'voice_name': v.get('voiceName', '?'),
                'voice_id': vname,
                'prompt': v.get('prompt', ''),
                'provider': v.get('provider', 'google'),
            }
    return {'voice_name': '?', 'voice_id': '?', 'prompt': '', 'provider': 'google'}

def send_telegram_text(token, text, chat_id=None):
    """Отправить текст через Telegram Bot API"""
    s = _load_secrets()
    cid = chat_id or s['chat_id']
    proxies = {"http": s['proxy'], "https": s['proxy']}
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={'chat_id': cid, 'text': text, 'parse_mode': 'HTML'},
        proxies=proxies, timeout=15
    )
    return r.status_code == 200

def gen_tts(text, voice_prompt):
    """Сгенерировать голосовое через Gemini TTS с Lineman-кэшом"""
    s = _load_secrets()
    
    # Check Lineman cache
    try:
        cr = requests.post('http://127.0.0.1:18888/cache/get',
                          json={'text': text, 'prompt': voice_prompt}, timeout=3)
        if cr.status_code == 200 and cr.json().get('cached'):
            import base64
            cached = base64.b64decode(cr.json()['data'])
            oggfile = tempfile.mktemp(suffix='.ogg')
            with open(oggfile, 'wb') as f:
                f.write(cached)
            return oggfile
    except:
        pass  # Lineman down? Skip cache
    
    # Check rate limit
    try:
        lr = requests.post('http://127.0.0.1:18888/check',
                          json={'model': 'gemini-2.5-flash-preview-tts'}, timeout=3)
        if not lr.json().get('allowed'):
            wait = lr.json().get('wait', 5)
            print(f"Lineman: rate limited, wait {wait:.1f}s", file=sys.stderr)
            if wait < 5:
                time.sleep(wait)
            else:
                return None  # Too long, skip
    except:
        pass
    
    full_text = f'{voice_prompt}\n\nText to speak: {text}'
    payload = {
        "contents": [{"parts": [{"text": full_text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"]}
    }
    proxies = {"http": s['proxy'], "https": s['proxy']}
    r = requests.post(f"{s['tts_url']}?key={s['api_key']}", json=payload,
                       headers={"Content-Type":"application/json"},
                       proxies=proxies, timeout=30)
    if r.status_code != 200:
        return None
    
    for c in r.json().get('candidates', []):
        for p in c.get('content', {}).get('parts', []):
            if 'inlineData' in p:
                raw = base64.b64decode(p['inlineData']['data'])
                # Save to Lineman cache
                try:
                    import base64 as b64
                    requests.post('http://127.0.0.1:18888/cache/put',
                                json={'text': text, 'prompt': voice_prompt,
                                      'data': b64.b64encode(raw).decode()}, timeout=3)
                except:
                    pass
                rawfile = tempfile.mktemp(suffix='.raw')
                oggfile = tempfile.mktemp(suffix='.ogg')
                with open(rawfile, 'wb') as f:
                    f.write(raw)
                subprocess.run(['ffmpeg', '-y', '-f', 's16le', '-ar', '24000', '-ac', '1',
                               '-i', rawfile, '-c:a', 'libopus', '-b:a', '24k', '-ar', '24000',
                               oggfile], capture_output=True)
                os.remove(rawfile)
                return oggfile
    return None

def send_telegram_voice(token, oggfile, chat_id=None):
    """Отправить голосовое сообщение"""
    s = _load_secrets()
    cid = chat_id or s['chat_id']
    proxies = {"http": s['proxy'], "https": s['proxy']}
    with open(oggfile, 'rb') as f:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendVoice",
            files={'voice': ('test.ogg', f, 'audio/ogg')},
            data={'chat_id': cid},
            proxies=proxies, timeout=15
        )
    os.remove(oggfile)
    return r.status_code == 200

def cmd_menu(agent_id, chat_id):
    """Показать главное меню"""
    info = get_agent_info(agent_id)
    voice = get_voice_prompt(agent_id)
    token = get_bot_token(agent_id)
    
    msg = f"🎤 <b>Voice Manager — {info['name']}</b>\n"
    msg += f"Голос: <b>{voice['voice_name']}</b>\n"
    msg += f"Auto: {info['auto']}\n"
    msg += f"\nТекущий промпт:\n<code>{voice['prompt'][:200]}{'…' if len(voice['prompt'])>200 else ''}</code>\n"
    msg += f"\nВыбери действие (напиши номер):\n"
    msg += f"1️⃣ Сменить голос\n"
    msg += f"2️⃣ Редактировать промпт\n"
    msg += f"3️⃣ Тест (10 слов)\n"
    msg += f"\nИли отправь новый текст промпта прямо сейчас."
    
    if token:
        send_telegram_text(token, msg, chat_id)
    return f"🎤 Voice Manager — {info['name']}\n1 — сменить голос\n2 — редактировать промпт\n3 — тест"

def cmd_list_voices(agent_id, chat_id):
    """Показать список голосов"""
    token = get_bot_token(agent_id)
    msg = "<b>Доступные голоса Gemini:</b>\n\n"
    for vname, desc in GEMINI_VOICES.items():
        msg += f"🎤 {vname} — {desc}\n"
    msg += "\nНапиши имя голоса, чтобы установить (например: Charon)"
    if token:
        send_telegram_text(token, msg, chat_id)
    return True

def cmd_test(agent_id, chat_id):
    """Тест голоса — 10 слов"""
    info = get_agent_info(agent_id)
    voice = get_voice_prompt(agent_id)
    token = get_bot_token(agent_id)
    
    if not token:
        return "❌ Нет бота для этого агента"
    
    test_text = f"Привет! Я {info['name']}. Мой новый голос звучит именно так."
    
    send_telegram_text(token, f"🔊 Генерирую тест для {info['name']} ({voice['voice_name']})...", chat_id)
    
    ogg = gen_tts(test_text, voice['prompt'])
    if ogg:
        if send_telegram_voice(token, ogg, chat_id):
            send_telegram_text(token, "✅ Как звучит? Если нужно — измени промпт командой 2", chat_id)
            return True
    send_telegram_text(token, "❌ Ошибка генерации", chat_id)
    return False

def cmd_set_voice(agent_id, new_voice):
    """Сменить голос агента"""
    if new_voice not in GEMINI_VOICES:
        return f"❌ Нет такого голоса. Доступны: {', '.join(GEMINI_VOICES.keys())}"
    
    cfg = load_config()
    vcfg = load_voices()
    
    # Найти текущую persona агента
    info = get_agent_info(agent_id)
    persona_name = info['persona']
    
    # Обновить voiceName в persona
    for pname, p in cfg.get('messages', {}).get('tts', {}).get('personas', {}).items():
        if pname == persona_name:
            if 'providers' not in p:
                p['providers'] = {}
            if 'google' not in p['providers']:
                p['providers']['google'] = {}
            p['providers']['google']['voiceName'] = new_voice
            break
    
    # Обновить в voices.json
    for vname, v in vcfg.get('voices', {}).items():
        if agent_id in v.get('assignedTo', []):
            v['voiceName'] = new_voice
            break
    
    save_config(cfg)
    save_voices(vcfg)
    
    return f"✅ Голос сменён на {new_voice}"

def cmd_edit_prompt(agent_id, new_prompt):
    """Обновить промпт голоса"""
    vcfg = load_voices()
    
    for vname, v in vcfg.get('voices', {}).items():
        if agent_id in v.get('assignedTo', []):
            v['prompt'] = new_prompt
            save_voices(vcfg)
            return f"✅ Промпт обновлён! Напиши 3 для теста."
    
    return "❌ Не нашёл профиль для этого агента"


# === CLI entry ===
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    action = sys.argv[1]
    
    s = _load_secrets()
    if action == 'menu':
        agent_id = sys.argv[2] if len(sys.argv) > 2 else 'main'
        chat_id = sys.argv[3] if len(sys.argv) > 3 else s['chat_id']
        result = cmd_menu(agent_id, chat_id)
        print(result)
    
    elif action == 'list-voices':
        agent_id = sys.argv[2] if len(sys.argv) > 2 else 'main'
        chat_id = sys.argv[3] if len(sys.argv) > 3 else s['chat_id']
        cmd_list_voices(agent_id, chat_id)
    
    elif action == 'test':
        agent_id = sys.argv[2] if len(sys.argv) > 2 else 'main'
        chat_id = sys.argv[3] if len(sys.argv) > 3 else s['chat_id']
        cmd_test(agent_id, chat_id)
    
    elif action == 'set-voice':
        agent_id = sys.argv[2] if len(sys.argv) > 2 else 'main'
        new_voice = sys.argv[3] if len(sys.argv) > 3 else 'Charon'
        result = cmd_set_voice(agent_id, new_voice)
        print(result)
    
    elif action == 'edit-prompt':
        agent_id = sys.argv[2]
        new_prompt = sys.argv[3]
        result = cmd_edit_prompt(agent_id, new_prompt)
        print(result)
    
    else:
        print(f"Unknown action: {action}")
