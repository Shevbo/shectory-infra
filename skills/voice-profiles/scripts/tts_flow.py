#!/usr/bin/env python3
"""
TTS Flow v2 — генерация голоса через Gemini TTS.
Вывод аудиофайла для отправки через OpenClaw MEDIA.

Использование:
  tts_flow.py generate <persona> <text>
"""

import sys, os, json, base64, subprocess, io, requests, tempfile

CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")
VOICES_DB = os.path.expanduser("~/.openclaw/voices.json")
OUTPUT_DIR = os.path.expanduser("~/.openclaw/media/tts/")

def load_cfg():
    with open(CONFIG) as f:
        return json.load(f)

def load_voices():
    if os.path.exists(VOICES_DB):
        with open(VOICES_DB) as f:
            return json.load(f)
    return {"voices": {}, "roles": {}}

def get_voice_config(persona):
    """Get voice config for a persona/agent role."""
    data = load_voices()
    roles = data.get("roles", {})
    voices = data.get("voices", {})
    
    role = roles.get(persona)
    if role:
        voice_id = role.get("voiceId", "")
        v = voices.get(voice_id, {})
        return {
            "voiceName": v.get("voiceName", role.get("voice", "Kore")),
            "model": v.get("model", "gemini-2.5-flash-preview-tts"),
            "prompt": v.get("prompt", ""),
            "system_prompt": role.get("systemPrompt", "")
        }
    return {"voiceName": "Kore", "model": "gemini-2.5-flash-preview-tts", "prompt": "", "system_prompt": ""}

def generate_tts(text, voice_cfg, api_key):
    """Gemini TTS → PCM → OGG file. Returns path to .ogg file."""
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_cfg["voiceName"]}}}
        }
    }
    
    # Try direct Google API (no proxy for TTS)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{voice_cfg['model']}:generateContent?key={api_key}"
    
    try:
        r = requests.post(url, json=body, timeout=30)
        r.raise_for_status()
        result = r.json()
    except requests.exceptions.ConnectionError:
        # Try via local proxy
        proxy_url = "http://127.0.0.1:9090"
        proxies = {"https": proxy_url, "http": proxy_url}
        r = requests.post(url, json=body, proxies=proxies, timeout=30)
        r.raise_for_status()
        result = r.json()
    
    audio_data = None
    for p in result["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            audio_data = base64.b64decode(p["inlineData"]["data"])
            break
    
    if not audio_data:
        raise RuntimeError("No audio in TTS response")
    
    # Convert PCM L16 24kHz → OGG Opus
    proc = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
        "-c:a", "libopus", "-b:a", "20k", "-vbr", "on", "-application", "voip",
        "-f", "ogg", "pipe:1"
    ], input=audio_data, capture_output=True)
    
    if proc.returncode:
        raise RuntimeError(f"ffmpeg: {proc.stderr.decode()[:200]}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = int(__import__('time').time() * 1000)
    out_path = os.path.join(OUTPUT_DIR, f"tts_{ts}.ogg")
    
    with open(out_path, "wb") as f:
        f.write(proc.stdout)
    
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: tts_flow.py generate <persona> <text>")
        print("  persona: main, developer, nurse, titan, interview-coach, jobsearch, etc.")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "generate" and len(sys.argv) >= 4:
        persona = sys.argv[2]
        text = sys.argv[3]
        
        cfg = load_cfg()
        api_key = cfg["models"]["providers"]["google"]["apiKey"]
        voice_cfg = get_voice_config(persona)
        
        out_path = generate_tts(text, voice_cfg, api_key)
        print(f"MEDIA:{out_path}[[audio_as_voice]]")
    else:
        print("Неизвестная команда")
        sys.exit(1)
