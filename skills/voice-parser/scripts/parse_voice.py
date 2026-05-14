#!/usr/bin/env python3
"""
Voice Parser — транскрипция и анализ голосовых сообщений через Gemini.
Usage:
  python3 parse_voice.py <audio_path> [prompt]
  python3 parse_voice.py batch <dir_or_glob> [prompt]
"""

import sys, os, base64, json, requests, re, glob
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")

def get_gemini_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    google = cfg.get("models", {}).get("providers", {}).get("google", {})
    api_key = google.get("apiKey", "")
    proxy_url = google.get("request", {}).get("proxy", {}).get("url", "")
    return api_key, proxy_url

def get_mime(path):
    ext = os.path.splitext(path)[1].lower()
    mime_map = {".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
                ".m4a": "audio/mp4", ".webm": "audio/webm", ".opus": "audio/ogg"}
    return mime_map.get(ext, "audio/ogg")

def file_info(path):
    size = os.path.getsize(path)
    name = os.path.basename(path)
    return f"{name} ({size/1024:.0f}KB)"

def call_gemini(api_key, proxy_url, b64_data, mime, prompt, model="gemini-2.5-flash"):
    """Call Gemini with the audio data."""
    models_to_try = [model, "gemini-2.0-flash", "gemini-2.0-flash-001"]
    
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
    
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
    last_error = None

    for m in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            body = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": b64_data}}
                    ]
                }],
                "generationConfig": {
                    "maxOutputTokens": 8192,
                    "temperature": 0.1
                }
            }
            r = requests.post(url, json=body, proxies=proxies, timeout=120)
            data = r.json()

            if "error" in data:
                last_error = f"❌ {m}: {data['error'].get('message', str(data['error']))}"
                continue

            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                finish = data.get("candidates", [{}])[0].get("finishReason", "unknown")
                last_error = f"❌ {m}: No text. Finish: {finish}"
                continue

            return text, m

        except requests.exceptions.Timeout:
            last_error = f"❌ {m}: Timeout (120s)"
            continue
        except requests.exceptions.ProxyError as e:
            last_error = f"❌ {m}: Proxy error: {e}"
            continue
        except Exception as e:
            last_error = f"❌ {m}: {e}"
            continue

    return f"Все модели не ответили. Последняя ошибка: {last_error}", models_to_try[-1]

def parse_audio(audio_path, prompt=None):
    """Parse a single audio file."""
    if not os.path.exists(audio_path):
        return f"❌ File not found: {audio_path}"

    api_key, proxy_url = get_gemini_config()
    if not api_key:
        return "❌ Gemini API key not found in config"

    default_prompt = ("Ты — транскрибатор голосовых сообщений. "
                      "Прослушай аудио и ВЕРНИ ТОЛЬКО ТРАНСКРИПЦИЮ: "
                      "распознай речь слово в слово на том языке, на котором говорят. "
                      "Если язык русский — транскрибируй на русском. "
                      "Если язык смешанный — транскрибируй как есть. "
                      "Если слышна не речь, а другие звуки — опиши их. "
                      "Не добавляй комментариев, не исправляй грамматику, не перефразируй.")
    prompt = prompt or default_prompt

    with open(audio_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    mime = get_mime(audio_path)
    result, model_used = call_gemini(api_key, proxy_url, b64, mime, prompt)
    
    info = file_info(audio_path)
    header = f"🎙 Голосовое: {info}\n🤖 Модель: {model_used}\n⏱ {datetime.now().strftime('%H:%M:%S')}\n{'─'*50}\n"
    
    return header + result

def parse_batch(pattern, prompt=None):
    """Parse multiple audio files."""
    files = sorted(glob.glob(os.path.expanduser(pattern)))
    if os.path.isdir(pattern):
        exts = ('.ogg', '.mp3', '.wav', '.m4a', '.webm', '.opus')
        files = sorted([os.path.join(pattern, f) for f in os.listdir(pattern) 
                       if f.lower().endswith(exts)])
    
    if not files:
        return f"❌ No audio files found matching: {pattern}"
    
    results = []
    for f in files:
        result = parse_audio(f, prompt)
        results.append(result + "\n")
    
    return "\n".join(results)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    
    if mode == "batch":
        pattern = sys.argv[2] if len(sys.argv) > 2 else "~/.openclaw/media/inbound/"
        prompt = sys.argv[3] if len(sys.argv) > 3 else None
        result = parse_batch(pattern, prompt)
    else:
        audio_path = mode
        prompt = sys.argv[2] if len(sys.argv) > 2 else None
        result = parse_audio(audio_path, prompt)
    
    print(result)
