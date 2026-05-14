#!/usr/bin/env python3
"""
ASR (Speech-to-Text) через Gemini API.
Принимает Telegram voice file_id или локальный .ogg, скачивает, распознаёт.
Использование:
  python3 asr_gemini.py --file-id <tg_file_id>
  python3 asr_gemini.py --file /path/to/voice.ogg
"""

import sys, os, json, base64, subprocess, tempfile, argparse
import requests

OPENCLAW_CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")

def load_config():
    with open(OPENCLAW_CONFIG) as f:
        d = json.load(f)
    google = d["models"]["providers"]["google"]
    proxy = google.get("request", {}).get("proxy", {})
    return {
        "bot_token": d["channels"]["telegram"]["botToken"],
        "api_key": google["apiKey"],
        "proxy_url": proxy.get("url"),
        "api_base": "https://generativelanguage.googleapis.com",
    }

def download_voice(file_id, bot_token, proxy_url=None):
    """Скачать голосовое из Telegram по file_id."""
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
    
    # Получить file_path
    r = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getFile",
        params={"file_id": file_id}, proxies=proxies, timeout=30
    )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API: {data}")
    
    file_path = data["result"]["file_path"]
    
    # Скачать файл
    r = requests.get(
        f"https://api.telegram.org/file/bot{bot_token}/{file_path}",
        proxies=proxies, timeout=60
    )
    return r.content

def convert_to_pcm(input_path, output_path):
    """OGG → PCM L16 24kHz mono."""
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_path,
        "-f", "s16le", "-ar", "24000", "-ac", "1",
        output_path
    ], check=True)
    return output_path

def transcribe_gemini(ogg_path, api_key, proxy_url=None, api_base="https://generativelanguage.googleapis.com"):
    """OGG аудио → Gemini 2.5 Flash → текст."""
    
    with open(ogg_path, "rb") as f:
        ogg_data = f.read()
    
    audio_b64 = base64.b64encode(ogg_data).decode("ascii")
    
    body = {
        "contents": [{
            "parts": [{
                "inlineData": {
                    "mimeType": "audio/ogg",
                    "data": audio_b64,
                }
            }]
        }],
        "systemInstruction": {
            "parts": [{"text": "Transcribe this Russian speech to text. Output ONLY the transcribed text with no additional commentary."}]
        }
    }
    
    url = f"{api_base}/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
    
    r = requests.post(url, json=body, proxies=proxies, timeout=60)
    r.raise_for_status()
    result = r.json()
    
    if "candidates" in result:
        parts = result["candidates"][0]["content"]["parts"]
        texts = [p["text"] for p in parts if "text" in p]
        return " ".join(texts).strip()
    
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASR через Gemini")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file-id", help="Telegram file_id голосового")
    group.add_argument("--file", help="Путь к локальному .ogg")
    parser.add_argument("--keep-pcm", help="Сохранить PCM", metavar="PATH")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    cfg = load_config()
    
    if args.verbose:
        print(f"Proxy: {cfg['proxy_url']}", file=sys.stderr)
    
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=True) as tmp_ogg:
        if args.file_id:
            if args.verbose:
                print(f"Скачиваю file_id={args.file_id}...", file=sys.stderr)
            audio = download_voice(args.file_id, cfg["bot_token"], cfg["proxy_url"])
            tmp_ogg.write(audio)
            tmp_ogg.flush()
            ogg_path = tmp_ogg.name
        else:
            ogg_path = args.file
        
        if args.verbose:
            print(f"OGG: {os.path.getsize(ogg_path)} bytes, распознаю...", file=sys.stderr)
        
        text = transcribe_gemini(ogg_path, cfg["api_key"], cfg["proxy_url"], cfg["api_base"])
            print(text)
