#!/usr/bin/env python3
"""
Download audio file from Google Drive and transcribe via Gemini.
Usage: python3 download_from_gdrive.py <drive_url_or_file_id> [prompt]

Accepts:
  - Google Drive share URL: https://drive.google.com/file/d/FILE_ID/view
  - Direct file ID: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms

Downloads to ~/.openclaw/media/inbound/, then calls parse_voice.py.
Large files are handled automatically via Gemini File API.
"""

import sys, os, re, subprocess, tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_voice import parse_audio

INBOUND_DIR = Path.home() / ".openclaw/media/inbound"
GOG = "gog"


def extract_file_id(url_or_id: str) -> str:
    # Try to extract from Drive URL
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
        r"open\?id=([a-zA-Z0-9_-]+)",
    ]
    for p in patterns:
        m = re.search(p, url_or_id)
        if m:
            return m.group(1)
    # Assume it's already a file ID (alphanumeric + hyphens)
    if re.match(r"^[a-zA-Z0-9_-]{20,}$", url_or_id.strip()):
        return url_or_id.strip()
    raise ValueError(f"Cannot extract Google Drive file ID from: {url_or_id}")


def get_filename(file_id: str) -> str:
    r = subprocess.run(
        [GOG, "drive", "get", file_id, "--plain"],
        capture_output=True, text=True
    )
    # Parse filename from gog output
    for line in r.stdout.splitlines():
        if line.strip():
            # First non-empty field is usually the name
            parts = line.split("\t")
            if parts:
                return parts[0].strip()
    return f"recording_{file_id[:8]}"


def download(file_id: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gdrive_{file_id[:16]}"

    print(f"⬇️  Downloading from Google Drive: {file_id[:20]}...")
    r = subprocess.run(
        [GOG, "drive", "download", file_id, f"--out={out_path}"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        raise RuntimeError(f"gog drive download failed: {r.stderr or r.stdout}")

    # gog may add an extension
    candidates = list(out_dir.glob(f"gdrive_{file_id[:16]}*"))
    if not candidates:
        raise RuntimeError(f"Downloaded file not found in {out_dir}")

    return max(candidates, key=lambda p: p.stat().st_size)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url_or_id = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        file_id = extract_file_id(url_or_id)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    try:
        local_path = download(file_id, INBOUND_DIR)
        print(f"✅ Saved: {local_path} ({local_path.stat().st_size // 1024 // 1024}MB)")
    except Exception as e:
        print(f"❌ Download failed: {e}")
        sys.exit(1)

    result = parse_audio(str(local_path), prompt)
    print(result)


if __name__ == "__main__":
    main()
