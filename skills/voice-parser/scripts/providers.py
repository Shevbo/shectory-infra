"""Provider detection + per-provider downloaders.

Public API:
  detect_provider(url_or_path: str) -> str
  download(provider: str, url: str, out_dir: Path) -> Path

Providers: gdrive, mailru, yadisk, dropbox, onedrive, telegram, direct, local, unknown
"""
import re
from pathlib import Path


def detect_provider(url_or_path: str) -> str:
    """Return provider name based on URL pattern or local path."""
    s = url_or_path.strip()
    if not s:
        return "unknown"

    if s.startswith("[file_id:") or s.startswith("[media attached:"):
        return "telegram"

    if s.startswith("/") or s.startswith("~/"):
        return "local"

    if not (s.startswith("http://") or s.startswith("https://")):
        return "unknown"

    if "drive.google.com" in s:
        return "gdrive"
    if "cloud.mail.ru" in s:
        return "mailru"
    if "disk.yandex.ru" in s or "yadi.sk" in s:
        return "yadisk"
    if "dropbox.com" in s:
        return "dropbox"
    if "1drv.ms" in s or "onedrive.live.com" in s:
        return "onedrive"

    return "direct"
