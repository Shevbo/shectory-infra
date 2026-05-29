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


import os
from typing import Optional
import requests


def _gdrive_file_id(url: str) -> Optional[str]:
    """Extract Google Drive file ID from share URL."""
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url) or re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None


def _download_gdrive_public(url: str, out_dir: Path) -> Path:
    """Download a public Google Drive file via uc?export=download.

    Works for `anyone with link` shares without OAuth. Handles the large-file
    virus-scan warning by re-requesting with confirm=t.
    """
    fid = _gdrive_file_id(url)
    if not fid:
        raise ValueError(f"Cannot extract Google Drive file ID from: {url}")

    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    # Lineman proxy via env (already set by openclaw); for direct dev runs:
    proxies = None
    if os.environ.get("LINEMAN_PROXY"):
        proxies = {"http": os.environ["LINEMAN_PROXY"], "https": os.environ["LINEMAN_PROXY"]}

    params = {"export": "download", "id": fid}
    r = session.get("https://drive.google.com/uc", params=params, proxies=proxies,
                    stream=True, timeout=120, allow_redirects=True)
    r.raise_for_status()

    # Large files: GDrive returns HTML with a confirmation link
    ctype = r.headers.get("content-type", "")
    if "text/html" in ctype:
        # Re-read body (small) to find confirm token
        body = r.content.decode("utf-8", errors="ignore")
        m = re.search(r'href="(/uc\?[^"]*confirm=t[^"]*)"', body)
        if m:
            confirm_url = "https://drive.google.com" + m.group(1).replace("&amp;", "&")
            r = session.get(confirm_url, proxies=proxies, stream=True, timeout=120, allow_redirects=True)
            r.raise_for_status()
        else:
            raise RuntimeError(
                "GDrive returned HTML without confirm token — file may be private or require login"
            )

    # Determine output filename
    cd = r.headers.get("Content-Disposition", "")
    fn_match = re.search(r'filename="([^"]+)"', cd) or re.search(r"filename=([^;]+)", cd)
    if fn_match:
        filename = fn_match.group(1).strip().strip('"')
    else:
        filename = f"gdrive_{fid[:16]}.bin"

    out_path = out_dir / filename
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    return out_path
