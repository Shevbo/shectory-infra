#!/usr/bin/env python3
"""
Download media file from ANY URL and transcribe/analyse via Gemini.

Usage:
  python3 download_from_url.py <url> [prompt|mode]

Supported URL types (автоматическое определение):
  Google Drive     https://drive.google.com/file/d/ID/view
  Mail.ru Cloud    https://cloud.mail.ru/public/XXXX/file.mp4
  Yandex.Disk      https://disk.yandex.ru/d/... or https://yadi.sk/d/...
  Dropbox          https://www.dropbox.com/s/.../file.mp4?dl=0
  OneDrive         https://1drv.ms/... or https://onedrive.live.com/...
  Any direct URL   https://example.com/recording.mp4

Named modes для промпта: transcribe | interview | workout | monologue

Файл сохраняется в ~/.openclaw/media/inbound/ и затем парсится через parse_voice.py.
Размер не ограничен — большие файлы идут через Gemini File API.
"""

import sys, os, re, subprocess, urllib.parse, json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_voice import parse_audio

INBOUND_DIR = Path.home() / ".openclaw/media/inbound"
LINEMAN_PROXY = os.environ.get("LINEMAN_URL", "http://127.0.0.1:9090")


# ── Platform detectors ──────────────────────────────────────────────

def is_gdrive(url: str) -> bool:
    return "drive.google.com" in url or "docs.google.com" in url


def is_yadisk(url: str) -> bool:
    return "disk.yandex.ru" in url or "yadi.sk" in url


def is_dropbox(url: str) -> bool:
    return "dropbox.com" in url


def is_onedrive(url: str) -> bool:
    return "1drv.ms" in url or "onedrive.live.com" in url or "sharepoint.com" in url


def is_mailru(url: str) -> bool:
    return "cloud.mail.ru" in url


# ── Per-platform downloaders ────────────────────────────────────────

def _download_gdrive(url: str, out_dir: Path) -> Path:
    """Google Drive — через gog (обходит ограничение 'слишком большой файл')."""
    m = (
        re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
        or re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    )
    if not m:
        raise ValueError(f"Cannot extract Google Drive file ID from: {url}")
    file_id = m.group(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_stem = out_dir / f"gdrive_{file_id[:16]}"
    print(f"⬇️  Google Drive: {file_id[:20]}... (via gog)")
    r = subprocess.run(
        ["gog", "drive", "download", file_id, f"--out={out_stem}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gog drive download failed: {r.stderr or r.stdout}")
    candidates = list(out_dir.glob(f"gdrive_{file_id[:16]}*"))
    if not candidates:
        raise RuntimeError(f"Downloaded file not found in {out_dir}")
    return max(candidates, key=lambda p: p.stat().st_size)


def _mailru_direct_url(public_url: str) -> str:
    """Получаем прямую ссылку на файл через Mail.ru Cloud public API."""
    import requests
    proxies = {"http": LINEMAN_PROXY, "https": LINEMAN_PROXY}

    # Извлечь public key из URL вида:
    #   https://cloud.mail.ru/public/XXXX/filename.mp4
    m = re.search(r"cloud\.mail\.ru/public/([^?#]+)", public_url)
    if not m:
        raise ValueError(f"Cannot extract Mail.ru Cloud public path from: {public_url}")
    public_path = "/" + m.group(1)  # e.g. /AbCd/interview.mp4

    # Шаг 1: получить dispatcher (список серверов для скачивания)
    disp = requests.get(
        "https://cloud.mail.ru/api/v2/dispatcher",
        params={"api": "2"},
        proxies=proxies,
        timeout=15,
        headers={"Referer": public_url},
    )
    disp.raise_for_status()
    servers = disp.json().get("body", {}).get("get", [])
    if not servers:
        raise RuntimeError("Mail.ru dispatcher returned no download servers")
    base_url = servers[0].get("url", "").rstrip("/")

    # Шаг 2: получить метаданные файла (размер, хэш)
    meta = requests.get(
        "https://cloud.mail.ru/api/v2/file",
        params={"home": public_path, "api": "2", "access_token": ""},
        proxies=proxies,
        timeout=15,
        headers={"Referer": public_url},
    )
    meta.raise_for_status()
    body = meta.json().get("body", {})
    file_hash = body.get("hash", "")
    if not file_hash:
        # Попробуем без токена через публичный weblink
        # Fallback: direct URL как base_url + weblink
        weblink = body.get("weblink", public_path.lstrip("/"))
        return f"{base_url}/{weblink}?key="

    return f"{base_url}/{file_hash}?key="


def _yadisk_direct_url(public_url: str) -> str:
    """Получаем прямую ссылку через Yandex.Disk public API."""
    import requests
    api = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    r = requests.get(
        api,
        params={"public_key": public_url},
        proxies={"http": LINEMAN_PROXY, "https": LINEMAN_PROXY},
        timeout=15,
    )
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Yandex.Disk API error: {data.get('message', data['error'])}")
    return data["href"]


def _wget_download(url: str, out_dir: Path, hint_name: str = "") -> Path:
    """Универсальная загрузка через wget."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "wget",
        "--no-check-certificate",
        "--content-disposition",   # уважать filename из заголовков
        "-q", "--show-progress",
        # Прокси для wget должен быть задан через переменные окружения (http_proxy/https_proxy) или не использоваться вовсе.
        # Explicit --proxy=URL приводит к ошибке 'Invalid boolean'.
        "--tries=3",
        "--timeout=120",
        "-P", str(out_dir),
    ]
    if hint_name:
        cmd += ["-O", str(out_dir / hint_name)]
    cmd.append(url)

    print(f"⬇️  wget: {url[:80]}...")
    r = subprocess.run(cmd, capture_output=False)
    if r.returncode != 0:
        raise RuntimeError(f"wget failed (code {r.returncode})")

    # Find most recently modified file in out_dir
    files = sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    media_exts = {".ogg",".mp3",".wav",".m4a",".webm",".opus",
                  ".mp4",".mov",".mkv",".avi",".3gp",".aac",".flac"}
    for f in files:
        if f.suffix.lower() in media_exts:
            return f
    if files:
        return files[0]
    raise RuntimeError(f"No file found in {out_dir} after wget")


def _dropbox_direct(url: str) -> str:
    """Dropbox: заменить dl=0 на dl=1 в URL."""
    url = re.sub(r"[?&]dl=0", "", url)
    sep = "&" if "?" in url else "?"
    return url + sep + "dl=1"


def download(url: str, out_dir: Path) -> Path:
    """Скачать файл по URL (любой хостинг) в out_dir. Вернуть путь."""
    if is_gdrive(url):
        return _download_gdrive(url, out_dir)

    if is_dropbox(url):
        direct = _dropbox_direct(url)
        print(f"⬇️  Dropbox → direct download")
        return _wget_download(direct, out_dir)

    if is_mailru(url):
        print(f"⬇️  Mail.ru Cloud → resolving direct URL...")
        direct = _mailru_direct_url(url)
        return _wget_download(direct, out_dir)

    if is_yadisk(url):
        print(f"⬇️  Yandex.Disk → resolving direct URL...")
        direct = _yadisk_direct_url(url)
        return _wget_download(direct, out_dir)

    # OneDrive, WeTransfer, любой прямой URL — wget справится
    print(f"⬇️  Generic URL download")
    return _wget_download(url, out_dir)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else None

    INBOUND_DIR.mkdir(parents=True, exist_ok=True)

    try:
        local_path = download(url, INBOUND_DIR)
        size_mb = local_path.stat().st_size / 1024 / 1024
        print(f"✅ Сохранён: {local_path.name} ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        sys.exit(1)

    result = parse_audio(str(local_path), prompt)
    print(result)


if __name__ == "__main__":
    main()
