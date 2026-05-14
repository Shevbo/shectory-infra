#!/usr/bin/env python3
"""
Premium Screenshot Reader v2
Анализирует изображения через Gemini Flash с прокси-обходом.
Поддерживает одиночные и batch-запросы, fallback модели.
Usage: 
  python3 analyze_screenshot.py <image_path> [prompt]
  python3 analyze_screenshot.py batch <dir_or_glob> [prompt]
"""

import sys, os, base64, json, requests, re, glob
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
CACHE_DIR = os.path.expanduser("~/.openclaw/canvas/")

def get_gemini_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    google = cfg.get("models", {}).get("providers", {}).get("google", {})
    api_key = google.get("apiKey", "")
    proxy_url = google.get("request", {}).get("proxy", {}).get("url", "")
    return api_key, proxy_url

def get_mime(path):
    ext = os.path.splitext(path)[1].lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp"}
    return mime_map.get(ext, "image/jpeg")

def file_info(path):
    size = os.path.getsize(path)
    w, h = "?", "?"
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
    except:
        pass
    name = os.path.basename(path)
    return f"{name} ({w}x{h}, {size/1024:.0f}KB)"

def call_gemini(api_key, proxy_url, b64_data, mime, prompt, model="gemini-2.5-flash"):
    """Call Gemini with fallback chain."""
    models_to_try = [model, "gemini-2.0-flash", "gemini-2.0-flash-001"]
    
    # Deduplicate preserving order
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
                    "maxOutputTokens": 4096,
                    "temperature": 0.1
                }
            }
            r = requests.post(url, json=body, proxies=proxies, timeout=90)
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
            last_error = f"❌ {m}: Timeout (90s)"
            continue
        except requests.exceptions.ProxyError as e:
            last_error = f"❌ {m}: Proxy error: {e}"
            continue
        except Exception as e:
            last_error = f"❌ {m}: {e}"
            continue

    return f"Все модели не ответили. Последняя ошибка: {last_error}", models_to_try[-1]

def analyze_image(image_path, prompt=None):
    """Analyze a single image."""
    if not os.path.exists(image_path):
        return f"❌ File not found: {image_path}", None

    api_key, proxy_url = get_gemini_config()
    if not api_key:
        return "❌ Gemini API key not found in config", None

    default_prompt = ("Ты — премиум анализатор скриншотов. Опиши что на изображении максимально подробно: "
                      "все тексты, UI-элементы, кнопки, цены, ошибки, диалоги, ссылки. "
                      "Если это скриншот с текстом — прочитай весь текст дословно. "
                      "Если это UI/веб-страница — опиши структуру и все интерактивные элементы.")
    prompt = prompt or default_prompt

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    mime = get_mime(image_path)
    result, model_used = call_gemini(api_key, proxy_url, b64, mime, prompt)
    
    # Add header
    info = file_info(image_path)
    header = f"📷 Анализ: {info}\n🤖 Модель: {model_used}\n⏱ {datetime.now().strftime('%H:%M:%S')}\n{'─'*50}\n"
    
    return header + result, model_used

def analyze_batch(pattern, prompt=None):
    """Analyze multiple images."""
    files = sorted(glob.glob(os.path.expanduser(pattern)))
    # Also support directory
    if os.path.isdir(pattern):
        exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        files = sorted([os.path.join(pattern, f) for f in os.listdir(pattern) 
                       if f.lower().endswith(exts)])
    
    if not files:
        return f"❌ No image files found matching: {pattern}"
    
    results = []
    for f in files:
        result, _ = analyze_image(f, prompt)
        results.append(result + "\n")
    
    return "\n".join(results)

def save_result(text, image_path):
    """Save analysis result to cache."""
    name = os.path.splitext(os.path.basename(image_path))[0]
    out_path = os.path.join(CACHE_DIR, f"analysis_{name}.txt")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(text)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    
    if mode == "batch":
        pattern = sys.argv[2] if len(sys.argv) > 2 else "~/.openclaw/media/inbound/*.png"
        prompt = sys.argv[3] if len(sys.argv) > 3 else None
        result = analyze_batch(pattern, prompt)
    else:
        image_path = mode
        prompt = sys.argv[2] if len(sys.argv) > 2 else None
        result, _ = analyze_image(image_path, prompt)
        # Save to cache
        saved = save_result(result, image_path)
        print(f"💾 Сохранено: {saved}")
    
    print(result)
