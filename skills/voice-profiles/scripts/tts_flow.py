#!/usr/bin/env python3
"""
TTS Flow v2 — генерация голоса через Gemini TTS через Lineman прокси.
Вывод: [[audio_as_voice]]\nMEDIA:путь_к_ogg

Использование:
  tts_flow.py generate <persona> <text>
  tts_flow.py list
"""

import sys, os, json, base64, subprocess, requests

CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")
VOICES_DB = os.path.expanduser("~/.openclaw/voices.json")
OUTPUT_DIR = os.path.expanduser("~/.openclaw/media/outbound/")

def load_cfg():
    with open(CONFIG) as f:
        return json.load(f)

def load_voices():
    if os.path.exists(VOICES_DB):
        with open(VOICES_DB) as f:
            return json.load(f)
    return {"voices": {}, "roles": {}}

def get_voice_config(persona):
    data = load_voices()
    roles = data.get("roles", {})
    voices = data.get("voices", {})
    role = roles.get(persona)
    if role:
        vid = role.get("voiceId", "")
        v = voices.get(vid, {})
        return {
            "voiceName": v.get("voiceName", role.get("voice", "Kore")),
            "model": v.get("model", "gemini-3.1-flash-tts-preview"),
            "prompt": v.get("prompt", ""),
        }
    # persona may be a voice ID directly (e.g. "medsestra")
    voice = voices.get(persona)
    if voice:
        return {
            "voiceName": voice.get("voiceName", "Kore"),
            "model": voice.get("model", "gemini-3.1-flash-tts-preview"),
            "prompt": voice.get("prompt", ""),
        }
    return {"voiceName": "Charon", "model": "gemini-3.1-flash-tts-preview", "prompt": ""}

def get_persona_for_agent(agent_id: str) -> str:
    cfg = load_cfg()
    for a in cfg.get("agents", {}).get("list", []):
        if a["id"] == agent_id:
            return a.get("tts", {}).get("persona", agent_id)
    return agent_id

MAX_TTS_WORDS = 30


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def generate_tts(text, voice_cfg, api_key, base_url):
    short_text = _truncate_words(text, MAX_TTS_WORDS)
    body = {
        "contents": [{"parts": [{"text": short_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_cfg["voiceName"]}
                }
            }
        }
    }
    url = f"{base_url}/models/{voice_cfg['model']}:generateContent"
    r = requests.post(url, json=body, params={"key": api_key}, timeout=30,
                      proxies={"https": None, "http": None})
    r.raise_for_status()
    data = r.json()
    for p in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            break
    else:
        raise RuntimeError("No audio in TTS response")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
         "-c:a", "libopus", "-b:a", "20k", "-vbr", "on", "-application", "voip",
         "-f", "ogg", "pipe:1"],
        input=raw, capture_output=True)
    if proc.returncode:
        raise RuntimeError(f"ffmpeg: {proc.stderr.decode()[:200]}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = int(__import__("time").time() * 1000)
    out = os.path.join(OUTPUT_DIR, f"tts_{ts}.ogg")
    with open(out, "wb") as f:
        f.write(proc.stdout)
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("tts_flow.py generate <persona> <text>")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "list":
        v = load_voices()
        for vid, p in v.get("voices", {}).items():
            print(f"  {vid}: {p.get('voiceName','?')} ({p.get('name','?')})")
        sys.exit(0)
    if cmd == "generate" and len(sys.argv) >= 4:
        cfg = load_cfg()
        api_key = cfg["models"]["providers"]["google"]["apiKey"]
        base_url = cfg["models"]["providers"]["google"]["baseUrl"]
        vc = get_voice_config(sys.argv[2])
        path = generate_tts(sys.argv[3], vc, api_key, base_url)
        print(f"[[audio_as_voice]]\nMEDIA:{path}")
        sys.exit(0)
    if cmd == "generate-agent" and len(sys.argv) >= 4:
        cfg = load_cfg()
        api_key = cfg["models"]["providers"]["google"]["apiKey"]
        base_url = cfg["models"]["providers"]["google"]["baseUrl"]
        persona = get_persona_for_agent(sys.argv[2])
        vc = get_voice_config(persona)
        path = generate_tts(sys.argv[3], vc, api_key, base_url)
        print(f"[[audio_as_voice]]\nMEDIA:{path}")
        sys.exit(0)
    if cmd == "test-voice" and len(sys.argv) >= 4:
        cfg = load_cfg()
        api_key = cfg["models"]["providers"]["google"]["apiKey"]
        base_url = cfg["models"]["providers"]["google"]["baseUrl"]
        voice_name = sys.argv[2]
        text = sys.argv[3]
        vc = {"voiceName": voice_name, "model": "gemini-3.1-flash-tts-preview", "prompt": ""}
        path = generate_tts(text, vc, api_key, base_url)
        print(f"[[audio_as_voice]]\nMEDIA:{path}")
        sys.exit(0)
    print("Неизвестная команда")
    sys.exit(1)
