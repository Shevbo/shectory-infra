#!/usr/bin/env python3
"""
Voice Parser — транскрипция и анализ голосовых сообщений через Gemini.
Usage:
  python3 parse_voice.py <audio_path> [prompt]
  python3 parse_voice.py batch <dir_or_glob> [prompt]

Files < 19MB: inline_data via Lineman proxy.
Files >= 19MB: Gemini File API upload (bypasses Lineman 4MB body limit).
"""

import sys, os, base64, json, requests, glob, time, uuid
from datetime import datetime

CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
FILE_SIZE_THRESHOLD = 19 * 1024 * 1024  # 19MB


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


def call_gemini_inline(api_key, b64_data, mime, prompt, model="gemini-2.5-flash"):
    """Call Gemini with inline base64 audio. Uses Lineman proxy (files < 19MB)."""
    models_to_try = [model, "gemini-2.0-flash", "gemini-2.0-flash-001"]
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
    last_error = None

    for m in models_to_try:
        try:
            url = f"http://127.0.0.1:9090/proxy/google/v1beta/models/{m}:generateContent?key={api_key}"
            body = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": b64_data}}
                ]}],
                "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.1}
            }
            r = requests.post(url, json=body, timeout=120)
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
        except Exception as e:
            last_error = f"❌ {m}: {e}"

    return f"Все модели не ответили. Последняя ошибка: {last_error}", models_to_try[-1]


def upload_to_file_api(api_key, proxy_url, audio_path, mime):
    """Upload large audio to Gemini File API. Bypasses Lineman (4MB body limit)."""
    filename = os.path.basename(audio_path)
    upload_url = (
        "https://generativelanguage.googleapis.com"
        f"/upload/v1beta/files?uploadType=multipart&key={api_key}"
    )
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    boundary = uuid.uuid4().hex
    metadata = json.dumps({"file": {"displayName": filename}})
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + audio_data + f"\r\n--{boundary}--".encode()

    r = requests.post(
        upload_url,
        data=body,
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        proxies=proxies,
        timeout=300,
    )
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"File API upload error: {data['error'].get('message', data['error'])}")

    file_uri = data.get("file", {}).get("uri", "")
    file_name = data.get("file", {}).get("name", "")
    if not file_uri:
        raise RuntimeError(f"No file URI in upload response: {data}")

    # Wait for ACTIVE state (usually instant for audio, up to 30s)
    _wait_for_file_active(api_key, proxy_url, file_name)
    return file_uri


def _wait_for_file_active(api_key, proxy_url, file_name, timeout=30):
    """Poll until file state is ACTIVE."""
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
        try:
            r = requests.get(url, proxies=proxies, timeout=10)
            state = r.json().get("file", {}).get("state", "")
            if state == "ACTIVE":
                return
            if state == "FAILED":
                raise RuntimeError("File API processing FAILED")
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"File API: file not ACTIVE after {timeout}s")


def delete_from_file_api(api_key, proxy_url, file_uri):
    """Delete file from File API after transcription (cleanup)."""
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
    try:
        # file_uri: https://generativelanguage.googleapis.com/v1beta/files/xxx
        path = file_uri.split("googleapis.com/")[-1]
        url = f"https://generativelanguage.googleapis.com/{path}?key={api_key}"
        requests.delete(url, proxies=proxies, timeout=15)
    except Exception:
        pass  # Non-critical


def call_gemini_file_uri(api_key, file_uri, mime, prompt, model="gemini-2.5-flash"):
    """Call Gemini using File API URI. JSON body is small — goes via Lineman."""
    models_to_try = [model, "gemini-2.0-flash"]
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]
    last_error = None

    for m in models_to_try:
        try:
            url = f"http://127.0.0.1:9090/proxy/google/v1beta/models/{m}:generateContent?key={api_key}"
            body = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"file_data": {"mime_type": mime, "file_uri": file_uri}}
                ]}],
                "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.1}
            }
            r = requests.post(url, json=body, timeout=120)
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
        except Exception as e:
            last_error = f"❌ {m}: {e}"

    return f"Все модели не ответили. Последняя ошибка: {last_error}", models_to_try[-1]


def parse_audio(audio_path, prompt=None):
    """Parse a single audio file."""
    if not os.path.exists(audio_path):
        return f"❌ File not found: {audio_path}"

    api_key, proxy_url = get_gemini_config()
    if not api_key:
        return "❌ Gemini API key not found in config"

    default_prompt = (
        "Ты — транскрибатор голосовых сообщений. "
        "Прослушай аудио и ВЕРНИ ТОЛЬКО ТРАНСКРИПЦИЮ: "
        "распознай речь слово в слово на том языке, на котором говорят. "
        "Если язык русский — транскрибируй на русском. "
        "Если язык смешанный — транскрибируй как есть. "
        "Если слышна не речь, а другие звуки — опиши их. "
        "Не добавляй комментариев, не исправляй грамматику, не перефразируй."
    )
    prompt = prompt or default_prompt
    mime = get_mime(audio_path)
    file_size = os.path.getsize(audio_path)

    if file_size >= FILE_SIZE_THRESHOLD:
        # Large file: upload via File API (bypasses Lineman 4MB body limit)
        file_uri = None
        try:
            file_uri = upload_to_file_api(api_key, proxy_url, audio_path, mime)
            result, model_used = call_gemini_file_uri(api_key, file_uri, mime, prompt)
        except Exception as e:
            result = f"❌ File API error: {e}"
            model_used = "gemini-2.5-flash"
        finally:
            if file_uri:
                delete_from_file_api(api_key, proxy_url, file_uri)
    else:
        # Small file: inline base64 via Lineman
        with open(audio_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        result, model_used = call_gemini_inline(api_key, b64, mime, prompt)

    via = "FileAPI" if file_size >= FILE_SIZE_THRESHOLD else "inline"
    info = file_info(audio_path)
    header = (
        f"🎙 Голосовое: {info}\n"
        f"🤖 Модель: {model_used} [{via}]\n"
        f"⏱ {datetime.now().strftime('%H:%M:%S')}\n"
        f"{'─'*50}\n"
    )
    return header + result


def parse_batch(pattern, prompt=None):
    """Parse multiple audio files."""
    files = sorted(glob.glob(os.path.expanduser(pattern)))
    if os.path.isdir(pattern):
        exts = ('.ogg', '.mp3', '.wav', '.m4a', '.webm', '.opus')
        files = sorted([
            os.path.join(pattern, f) for f in os.listdir(pattern)
            if f.lower().endswith(exts)
        ])

    if not files:
        return f"❌ No audio files found matching: {pattern}"

    return "\n".join(parse_audio(f, prompt) + "\n" for f in files)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "batch":
        pattern = sys.argv[2] if len(sys.argv) > 2 else "~/.openclaw/media/inbound/"
        prompt = sys.argv[3] if len(sys.argv) > 3 else None
        print(parse_batch(pattern, prompt))
    else:
        audio_path = mode
        prompt = sys.argv[2] if len(sys.argv) > 2 else None
        print(parse_audio(audio_path, prompt))
