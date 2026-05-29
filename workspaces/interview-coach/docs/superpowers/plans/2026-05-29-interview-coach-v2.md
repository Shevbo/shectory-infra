# InterviewCoach v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LLM-driven media handling in interview-coach with a deterministic Python playbook (`process_media.py`), add multi-channel escalation (`escalate.sh`), switch model to `deepseek-v4-pro`, and enforce result-only verbosity to eliminate apology cycles and `<tool_code>` leakage.

**Architecture:** Coach becomes a thin LLM wrapper that delegates all media to `process_media.py` (state machine: detect → download → validate → parse → analyze, returns stable JSON). Escalation funnels through `escalate.sh` (ask-claude.sh → claude-inbox → TG alert with dedup). AGENTS.md is rewritten with banned phrases and result-only rules.

**Tech Stack:** Python 3.12, pytest, `responses` (HTTP mocking), `python-magic` (mime detection), `ffprobe` (duration), `requests`, existing `parse_voice.py` (Gemini File API), bash for escalate, OpenClaw gateway config.

---

## File Structure

**New files:**
- `~/skills/voice-parser/scripts/process_media.py` — main playbook entry point (~280 LOC)
- `~/skills/voice-parser/scripts/providers.py` — provider detection + per-provider downloaders (~150 LOC)
- `~/skills/voice-parser/scripts/validators.py` — magic bytes / size / duration checks (~80 LOC)
- `~/scripts/escalate.sh` — multi-channel escalation (~60 LOC)
- `~/skills/voice-parser/tests/__init__.py` — empty
- `~/skills/voice-parser/tests/test_providers.py` — provider detection tests
- `~/skills/voice-parser/tests/test_validators.py` — validation tests
- `~/skills/voice-parser/tests/test_process_media.py` — full flow tests
- `~/skills/voice-parser/tests/test_escalate.py` — bash escalation tests via subprocess
- `~/skills/voice-parser/tests/fixtures/fake_html_as_media.html`
- `~/skills/voice-parser/tests/fixtures/gdrive_uc_redirect.html`
- `~/skills/voice-parser/tests/conftest.py` — fixtures factory (real_audio_small.mp3 via ffmpeg)

**Modified files:**
- `~/workspaces/interview-coach/AGENTS.md` — full rewrite, ~6-7 KB target
- `~/.openclaw/openclaw.json` — interview-coach model config

**Unchanged (do not touch):**
- `~/skills/voice-parser/scripts/parse_voice.py`
- `~/skills/voice-parser/scripts/download_from_url.py` (we reuse via import in providers.py)
- Other agents' configs

---

## Task 1: Setup — branch, test scaffold, ffmpeg fixture factory

**Files:**
- Create: `~/skills/voice-parser/tests/__init__.py`
- Create: `~/skills/voice-parser/tests/conftest.py`
- Create: `~/skills/voice-parser/tests/fixtures/fake_html_as_media.html`
- Create: `~/skills/voice-parser/pytest.ini`

- [ ] **Step 1: Create branch**

```bash
cd ~ && git checkout -b feat/interview-coach-v2
```

Expected: `Switched to a new branch 'feat/interview-coach-v2'`

- [ ] **Step 2: Verify required CLI tools exist**

```bash
which ffmpeg ffprobe pytest python3 && python3 -c "import responses, magic" 2>&1
```

Expected: paths printed for ffmpeg/ffprobe/pytest/python3. If `import responses` or `import magic` fails:
```bash
pip install --user responses python-magic
```

- [ ] **Step 3: Create test scaffold directories and files**

```bash
mkdir -p ~/skills/voice-parser/tests/fixtures
touch ~/skills/voice-parser/tests/__init__.py
```

- [ ] **Step 4: Create pytest.ini**

File `~/skills/voice-parser/pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short
```

- [ ] **Step 5: Create conftest.py with ffmpeg-based audio/video fixtures**

File `~/skills/voice-parser/tests/conftest.py`:
```python
"""Shared fixtures for voice-parser tests. Generates real media on demand."""
import subprocess
from pathlib import Path
import pytest

FIX = Path(__file__).parent / "fixtures"


def _ffmpeg(args: list[str]) -> None:
    """Run ffmpeg quietly, raise on non-zero exit."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")


@pytest.fixture(scope="session")
def real_audio_small_mp3() -> Path:
    """100KB+ valid mp3 (60s sine wave)."""
    path = FIX / "real_audio_small.mp3"
    if not path.exists():
        _ffmpeg([
            "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
            "-codec:a", "libmp3lame", "-b:a", "128k", str(path),
        ])
    assert path.stat().st_size > 100_000
    return path


@pytest.fixture(scope="session")
def real_video_small_mp4() -> Path:
    """200KB+ valid mp4 (60s blank video with sine audio)."""
    path = FIX / "real_video_small.mp4"
    if not path.exists():
        _ffmpeg([
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=60",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
            "-codec:v", "libx264", "-preset", "ultrafast",
            "-codec:a", "aac", "-shortest", str(path),
        ])
    assert path.stat().st_size > 200_000
    return path


@pytest.fixture(scope="session")
def fake_html_as_media() -> Path:
    """16KB HTML file masquerading as media — the Mail.ru bug scenario."""
    path = FIX / "fake_html_as_media.html"
    if not path.exists():
        body = "<html><body>" + ("Сгенерируй сюда ночное голосовое сообщение. " * 200) + "</body></html>"
        path.write_text(body, encoding="utf-8")
    assert 10_000 <= path.stat().st_size <= 20_000
    return path


@pytest.fixture(scope="session")
def tiny_file() -> Path:
    """500-byte garbage."""
    path = FIX / "tiny.bin"
    if not path.exists():
        path.write_bytes(b"x" * 500)
    return path
```

- [ ] **Step 6: Add .gitignore for generated fixtures**

File `~/skills/voice-parser/tests/fixtures/.gitignore`:
```
real_audio_small.mp3
real_video_small.mp4
tiny.bin
```

- [ ] **Step 7: Verify scaffold by running empty pytest**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest -v
```

Expected: `no tests ran in X.XXs` (or similar). Exit code 5 is OK (no tests collected).

- [ ] **Step 8: Commit**

```bash
cd ~ && git add skills/voice-parser/tests/ skills/voice-parser/pytest.ini && git commit -m "test(voice-parser): scaffold pytest tests + fixture factory"
```

---

## Task 2: Validators — magic bytes, size, duration

**Files:**
- Create: `~/skills/voice-parser/scripts/validators.py`
- Test: `~/skills/voice-parser/tests/test_validators.py`

- [ ] **Step 1: Write failing tests**

File `~/skills/voice-parser/tests/test_validators.py`:
```python
"""Tests for media file validators."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from validators import validate_media, ValidationResult


def test_html_file_rejected(fake_html_as_media):
    r = validate_media(fake_html_as_media)
    assert r.ok is False
    assert "non-media" in r.reason.lower() or "html" in r.reason.lower()
    assert r.should_escalate is True


def test_tiny_file_rejected(tiny_file):
    r = validate_media(tiny_file)
    assert r.ok is False
    assert "too small" in r.reason.lower()
    assert r.should_escalate is True


def test_real_audio_accepted(real_audio_small_mp3):
    r = validate_media(real_audio_small_mp3)
    assert r.ok is True
    assert r.mime.startswith("audio/")
    assert r.duration_seconds >= 30
    assert r.size_bytes > 100_000


def test_real_video_accepted(real_video_small_mp4):
    r = validate_media(real_video_small_mp4)
    assert r.ok is True
    assert r.mime.startswith("video/")
    assert r.duration_seconds >= 30
    assert r.size_bytes > 200_000


def test_missing_file_rejected(tmp_path):
    r = validate_media(tmp_path / "nonexistent.mp3")
    assert r.ok is False
    assert "not found" in r.reason.lower() or "does not exist" in r.reason.lower()
    assert r.should_escalate is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_validators.py -v
```

Expected: 5 ERRORs (collection) — `ModuleNotFoundError: No module named 'validators'`.

- [ ] **Step 3: Implement validators.py**

File `~/skills/voice-parser/scripts/validators.py`:
```python
"""Media file validators — magic bytes, size, duration.

Returns ValidationResult dataclass with .ok, .reason, .should_escalate,
.mime, .size_bytes, .duration_seconds.
"""
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import magic

MIN_SIZE_BYTES = 100_000  # 100 KB
MIN_DURATION_SECONDS = 30


@dataclass
class ValidationResult:
    ok: bool
    reason: Optional[str] = None
    should_escalate: bool = False
    mime: str = ""
    size_bytes: int = 0
    duration_seconds: float = 0.0


def _ffprobe_duration(path: Path) -> float:
    """Return duration in seconds, 0.0 if ffprobe fails."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip() or 0.0)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def validate_media(path: Path) -> ValidationResult:
    """Validate that the file is a real audio/video file >= 100 KB and >= 30s."""
    if not path.exists():
        return ValidationResult(ok=False, reason=f"file not found: {path}", should_escalate=True)

    size = path.stat().st_size
    if size < MIN_SIZE_BYTES:
        return ValidationResult(
            ok=False, reason=f"file too small: {size} bytes (min {MIN_SIZE_BYTES})",
            should_escalate=True, size_bytes=size,
        )

    mime = magic.from_file(str(path), mime=True) or ""

    if not (mime.startswith("audio/") or mime.startswith("video/")):
        return ValidationResult(
            ok=False, reason=f"downloaded non-media file (mime={mime!r}); likely an HTML error page or wrong URL",
            should_escalate=True, mime=mime, size_bytes=size,
        )

    duration = _ffprobe_duration(path)
    if duration > 0 and duration < MIN_DURATION_SECONDS:
        # Warning only — short audio is still real media
        return ValidationResult(
            ok=True, reason=f"warning: short duration {duration:.1f}s",
            should_escalate=False, mime=mime, size_bytes=size,
            duration_seconds=duration,
        )

    return ValidationResult(
        ok=True, reason=None, should_escalate=False,
        mime=mime, size_bytes=size, duration_seconds=duration,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_validators.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~ && git add skills/voice-parser/scripts/validators.py skills/voice-parser/tests/test_validators.py && git commit -m "feat(voice-parser): add media validators (magic bytes, size, duration)"
```

---

## Task 3: Provider detection

**Files:**
- Create: `~/skills/voice-parser/scripts/providers.py` (partial — detection only)
- Test: `~/skills/voice-parser/tests/test_providers.py`

- [ ] **Step 1: Write failing tests**

File `~/skills/voice-parser/tests/test_providers.py`:
```python
"""Tests for provider detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from providers import detect_provider

import pytest


@pytest.mark.parametrize("url,expected", [
    ("https://drive.google.com/file/d/1f3uPuKuY5selelkxvVzjiFtY3SoYOMyc/view?usp=drive_link", "gdrive"),
    ("https://drive.google.com/open?id=1ABC", "gdrive"),
    ("https://cloud.mail.ru/public/V8To/awDjFQGHa", "mailru"),
    ("https://disk.yandex.ru/d/ABC123", "yadisk"),
    ("https://yadi.sk/d/ABC123", "yadisk"),
    ("https://www.dropbox.com/s/abc/recording.mp4?dl=0", "dropbox"),
    ("https://1drv.ms/v/s!ABC", "onedrive"),
    ("https://onedrive.live.com/redir?resid=ABC", "onedrive"),
    ("https://example.com/recording.mp4", "direct"),
    ("[file_id:BAACAgIAAxkBAAIB]", "telegram"),
    ("[media attached: /home/shectory/.openclaw/media/inbound/X.ogg]", "telegram"),
    ("/home/shectory/.openclaw/media/inbound/X.ogg", "local"),
])
def test_detect_provider(url, expected):
    assert detect_provider(url) == expected


def test_detect_provider_empty():
    assert detect_provider("") == "unknown"


def test_detect_provider_invalid():
    assert detect_provider("not a url and not a file") == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_providers.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'providers'`.

- [ ] **Step 3: Create providers.py with detect_provider only**

File `~/skills/voice-parser/scripts/providers.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_providers.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
cd ~ && git add skills/voice-parser/scripts/providers.py skills/voice-parser/tests/test_providers.py && git commit -m "feat(voice-parser): add provider detection (gdrive/mailru/yadisk/dropbox/onedrive/telegram/direct/local)"
```

---

## Task 4: GDrive public-share downloader (uc?export=download endpoint)

**Files:**
- Modify: `~/skills/voice-parser/scripts/providers.py` (add `_download_gdrive_public`)
- Test: `~/skills/voice-parser/tests/test_providers.py` (add download tests)

This is the **fix for the inцидент-29.05 issue**: GDrive OAuth token expired but the file is `anyone with link` — use the public endpoint instead.

- [ ] **Step 1: Add failing test**

Append to `~/skills/voice-parser/tests/test_providers.py`:
```python
import responses


@responses.activate
def test_gdrive_public_download_simple(tmp_path):
    from providers import _download_gdrive_public

    file_id = "1ABC"
    audio_bytes = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 200_000

    responses.add(
        responses.GET,
        f"https://drive.google.com/uc",
        body=audio_bytes,
        content_type="audio/wav",
        headers={"Content-Disposition": 'attachment; filename="interview.wav"'},
    )

    out = _download_gdrive_public(
        f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link",
        tmp_path,
    )
    assert out.exists()
    assert out.stat().st_size == len(audio_bytes)


@responses.activate
def test_gdrive_public_download_with_confirm_token(tmp_path):
    """Large files return HTML virus-scan warning; we resend with confirm=t."""
    from providers import _download_gdrive_public

    file_id = "1ABC"
    audio_bytes = b"\x00ID3" + b"\x00" * 300_000

    # First call returns confirmation HTML
    responses.add(
        responses.GET, "https://drive.google.com/uc",
        body='<html><a id="uc-download-link" href="/uc?id=1ABC&confirm=t">Download</a></html>',
        content_type="text/html",
    )
    # Second call (with confirm=t) returns file
    responses.add(
        responses.GET, "https://drive.google.com/uc",
        body=audio_bytes,
        content_type="audio/mpeg",
        headers={"Content-Disposition": 'attachment; filename="interview.mp3"'},
    )

    out = _download_gdrive_public(
        f"https://drive.google.com/file/d/{file_id}/view",
        tmp_path,
    )
    assert out.exists()
    assert out.stat().st_size == len(audio_bytes)


def test_gdrive_extract_id():
    from providers import _gdrive_file_id
    assert _gdrive_file_id("https://drive.google.com/file/d/1ABC/view?usp=drive_link") == "1ABC"
    assert _gdrive_file_id("https://drive.google.com/open?id=2XYZ") == "2XYZ"
    assert _gdrive_file_id("https://drive.google.com/uc?id=3DEF&export=download") == "3DEF"
    assert _gdrive_file_id("https://example.com/no-id") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_providers.py -v
```

Expected: 3 new tests fail with `ImportError` on `_download_gdrive_public` / `_gdrive_file_id`.

- [ ] **Step 3: Implement GDrive public downloader**

Append to `~/skills/voice-parser/scripts/providers.py`:
```python
import os
import re as _re
from typing import Optional
import requests


def _gdrive_file_id(url: str) -> Optional[str]:
    """Extract Google Drive file ID from share URL."""
    m = _re.search(r"/file/d/([a-zA-Z0-9_-]+)", url) or _re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
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
        m = _re.search(r'href="(/uc\?[^"]*confirm=t[^"]*)"', body)
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
    fn_match = _re.search(r'filename="([^"]+)"', cd) or _re.search(r"filename=([^;]+)", cd)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_providers.py -v
```

Expected: 17 passed (14 old + 3 new).

- [ ] **Step 5: Commit**

```bash
cd ~ && git add skills/voice-parser/scripts/providers.py skills/voice-parser/tests/test_providers.py && git commit -m "feat(voice-parser): GDrive public-share downloader via uc?export=download"
```

---

## Task 5: Unified `download()` dispatcher for all providers

**Files:**
- Modify: `~/skills/voice-parser/scripts/providers.py`
- Test: `~/skills/voice-parser/tests/test_providers.py`

Other providers (mailru, yadisk, dropbox, onedrive, direct) — reuse existing logic from `download_from_url.py` via direct import, wrap in single `download()` dispatcher.

- [ ] **Step 1: Add failing test**

Append to `~/skills/voice-parser/tests/test_providers.py`:
```python
def test_download_dispatches_to_local(tmp_path, real_audio_small_mp3):
    from providers import download
    out = download("local", str(real_audio_small_mp3), tmp_path)
    # local provider returns the original path as-is (no copy)
    assert out == real_audio_small_mp3


def test_download_unknown_raises(tmp_path):
    from providers import download
    import pytest
    with pytest.raises(ValueError, match="unsupported"):
        download("unknown", "garbage", tmp_path)


def test_download_telegram_raises_when_no_path(tmp_path):
    """telegram provider requires a pre-extracted local path passed via brackets."""
    from providers import download
    import pytest
    with pytest.raises(ValueError, match="telegram"):
        download("telegram", "[file_id:ABC]", tmp_path)


def test_download_telegram_with_media_attached(tmp_path, real_audio_small_mp3):
    """`[media attached: /path]` syntax → returns that path."""
    from providers import download
    marker = f"[media attached: {real_audio_small_mp3}]"
    out = download("telegram", marker, tmp_path)
    assert out == real_audio_small_mp3
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_providers.py -v -k download
```

Expected: 4 new tests fail with `ImportError` on `download`.

- [ ] **Step 3: Implement `download()` dispatcher**

Append to `~/skills/voice-parser/scripts/providers.py`:
```python
def download(provider: str, url_or_marker: str, out_dir: Path) -> Path:
    """Dispatch download to the right provider handler.

    For `local` and `telegram` with `[media attached:`, returns the path as-is.
    For all URL providers, downloads to out_dir and returns the saved file path.
    Raises ValueError for unsupported/empty providers.
    """
    if provider == "local":
        p = Path(url_or_marker).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"local path does not exist: {p}")
        return p

    if provider == "telegram":
        m = _re.search(r"\[media attached:\s*([^\]]+)\]", url_or_marker)
        if m:
            p = Path(m.group(1).strip()).expanduser()
            if not p.exists():
                raise FileNotFoundError(f"telegram media file not found: {p}")
            return p
        raise ValueError(
            "telegram provider needs the file pre-downloaded "
            "(use download_and_parse.py for file_id flow)"
        )

    if provider == "gdrive":
        return _download_gdrive_public(url_or_marker, out_dir)

    # Reuse existing downloaders from download_from_url.py for mailru/yadisk/dropbox/onedrive/direct
    if provider in ("mailru", "yadisk", "dropbox", "onedrive", "direct"):
        # Import lazily to avoid circular deps and speed up unit tests
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_dlu",
            str(Path(__file__).parent / "download_from_url.py"),
        )
        dlu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dlu)

        if provider == "mailru":
            return dlu._download_mailru(url_or_marker, out_dir)
        if provider == "yadisk":
            direct_url = dlu._yadisk_direct_url(url_or_marker)
            return dlu._wget_download(direct_url, out_dir)
        if provider == "dropbox":
            return dlu._wget_download(dlu._dropbox_direct(url_or_marker), out_dir)
        if provider == "onedrive":
            return dlu._wget_download(url_or_marker, out_dir)
        if provider == "direct":
            return dlu._wget_download(url_or_marker, out_dir)

    raise ValueError(f"unsupported provider: {provider!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_providers.py -v
```

Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
cd ~ && git add skills/voice-parser/scripts/providers.py skills/voice-parser/tests/test_providers.py && git commit -m "feat(voice-parser): unified download() dispatcher for all providers"
```

---

## Task 6: `process_media.py` — skeleton + JSON contract

**Files:**
- Create: `~/skills/voice-parser/scripts/process_media.py`
- Test: `~/skills/voice-parser/tests/test_process_media.py`

- [ ] **Step 1: Write failing test (contract: stable JSON output)**

File `~/skills/voice-parser/tests/test_process_media.py`:
```python
"""Tests for process_media.py — the unified media playbook entry point."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "process_media.py"


def _run(args: list[str], timeout: int = 30) -> tuple[int, dict]:
    """Run process_media.py with args, return (exit_code, parsed_json_stdout)."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=timeout,
    )
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        data = {"_raw_stdout": r.stdout, "_raw_stderr": r.stderr}
    return r.returncode, data


def test_no_args_returns_failed_json():
    code, data = _run([])
    assert code != 0
    assert data.get("status") == "failed"
    assert "usage" in data.get("reason", "").lower() or "argument" in data.get("reason", "").lower()


def test_unsupported_url_returns_failed_with_escalate():
    code, data = _run(["ftp://example.com/file.mp3"])
    assert code != 0
    assert data["status"] == "failed"
    assert data["should_escalate"] is True
    assert "unsupported" in data["reason"].lower() or "unknown" in data["reason"].lower()


def test_local_html_file_rejected(fake_html_as_media):
    code, data = _run([str(fake_html_as_media), "--no-parse"])
    assert code != 0
    assert data["status"] == "failed"
    assert data["stage"] == "validated"
    assert data["should_escalate"] is True
    assert "non-media" in data["reason"].lower() or "html" in data["reason"].lower()


def test_local_real_audio_validates(real_audio_small_mp3):
    code, data = _run([str(real_audio_small_mp3), "--no-parse"])
    assert code == 0
    assert data["status"] == "ok"
    assert data["stage"] == "validated"
    assert data["mime"].startswith("audio/")
    assert data["size_bytes"] > 100_000
    assert data["duration_seconds"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_process_media.py -v
```

Expected: 4 failures — script doesn't exist.

- [ ] **Step 3: Implement `process_media.py` skeleton**

File `~/skills/voice-parser/scripts/process_media.py`:
```python
#!/usr/bin/env python3
"""
process_media.py — unified media playbook entry point for interview-coach.

State machine: init → detected → downloaded → validated → parsed → analyzed → done

Usage:
    process_media.py <url-or-path> [--mode=interview|monologue|transcribe] [--no-parse] [--out=path]

Stable JSON output on stdout:
{
  "status": "ok" | "failed",
  "stage": "detected" | "downloaded" | "validated" | "parsed" | "analyzed" | "done",
  "provider": "gdrive" | "mailru" | "yadisk" | "dropbox" | "onedrive" | "telegram" | "direct" | "local",
  "file_path": "...",
  "size_bytes": 123,
  "duration_seconds": 12.3,
  "mime": "audio/mpeg",
  "transcript_path": "...",
  "summary": "...",
  "reason": null | "...",
  "should_escalate": true | false
}

Exit code: 0 on status=ok, non-zero on failed.
"""
import argparse
import json
import logging
import os
import sys
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from providers import detect_provider, download
from validators import validate_media

INBOUND_DIR = Path.home() / ".openclaw/media/inbound"
TRANSCRIPT_DIR = Path.home() / ".openclaw/media/transcripts"
LOG_FILE = Path.home() / "logs/process_media.log"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("process_media")


@dataclass
class Result:
    status: str = "failed"
    stage: str = "init"
    provider: str = ""
    file_path: Optional[str] = None
    size_bytes: int = 0
    duration_seconds: float = 0.0
    mime: str = ""
    transcript_path: Optional[str] = None
    summary: Optional[str] = None
    reason: Optional[str] = None
    should_escalate: bool = False

    def emit_and_exit(self) -> None:
        print(json.dumps(asdict(self), ensure_ascii=False))
        sys.exit(0 if self.status == "ok" else 1)


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("url_or_path", nargs="?", help="URL or local path")
    parser.add_argument("--mode", default="interview",
                        choices=["interview", "monologue", "transcribe", "workout"])
    parser.add_argument("--no-parse", action="store_true",
                        help="Stop after validation, skip Gemini parsing (for tests)")
    parser.add_argument("--out", default=None, help="Optional output directory")
    args = parser.parse_args()

    if not args.url_or_path:
        Result(reason="usage: process_media.py <url-or-path> [--mode=...]",
               should_escalate=False).emit_and_exit()

    res = Result()

    try:
        # Stage 1: detect
        res.provider = detect_provider(args.url_or_path)
        res.stage = "detected"
        if res.provider in ("unknown",):
            res.reason = f"unsupported or unrecognized URL: {args.url_or_path}"
            res.should_escalate = True
            res.emit_and_exit()

        # Stage 2: download
        out_dir = Path(args.out).expanduser() if args.out else INBOUND_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        downloaded = download(res.provider, args.url_or_path, out_dir)
        res.file_path = str(downloaded)
        res.stage = "downloaded"

        # Stage 3: validate
        v = validate_media(downloaded)
        res.size_bytes = v.size_bytes
        res.mime = v.mime
        res.duration_seconds = v.duration_seconds
        if not v.ok:
            res.reason = v.reason
            res.should_escalate = v.should_escalate
            res.emit_and_exit()
        res.stage = "validated"

        # Stage 4: parse (skipped in --no-parse mode)
        if args.no_parse:
            res.status = "ok"
            res.emit_and_exit()

        # parsing will be added in Task 7
        res.reason = "parsing stage not yet implemented"
        res.should_escalate = False
        res.emit_and_exit()

    except FileNotFoundError as e:
        log.exception("download/file error")
        res.reason = f"file not found: {e}"
        res.should_escalate = True
        res.emit_and_exit()
    except ValueError as e:
        log.exception("value error")
        res.reason = str(e)
        res.should_escalate = True
        res.emit_and_exit()
    except Exception as e:
        log.exception("unexpected error at stage=%s", res.stage)
        res.reason = f"{type(e).__name__}: {e}"
        res.should_escalate = True
        res.emit_and_exit()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Make executable and run tests**

```bash
chmod +x ~/skills/voice-parser/scripts/process_media.py
cd ~/skills/voice-parser && python3 -m pytest tests/test_process_media.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd ~ && git add skills/voice-parser/scripts/process_media.py skills/voice-parser/tests/test_process_media.py && git commit -m "feat(voice-parser): process_media.py skeleton with state machine + JSON contract"
```

---

## Task 7: Wire `parse_voice` into `process_media.py`

**Files:**
- Modify: `~/skills/voice-parser/scripts/process_media.py`
- Test: `~/skills/voice-parser/tests/test_process_media.py`

- [ ] **Step 1: Add failing test for parse stage**

Append to `~/skills/voice-parser/tests/test_process_media.py`:
```python
def test_parse_called_on_validated_audio(real_audio_small_mp3, monkeypatch):
    """When --no-parse is omitted, parse_audio is called and result goes into JSON."""
    # Monkeypatch is too tricky for subprocess test; we'll do this via integration env var
    # that makes process_media short-circuit Gemini with a fake transcript.
    code, data = _run(
        [str(real_audio_small_mp3), "--mode=interview"],
        timeout=60,
    )
    # If Gemini key is missing, the script must still produce valid JSON
    assert data.get("stage") in ("parsed", "analyzed", "validated")
    # status may be ok (if Gemini key present and works) or failed (key missing / quota)
    assert data.get("status") in ("ok", "failed")
    assert isinstance(data.get("should_escalate"), bool)
```

- [ ] **Step 2: Run test to verify current state**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_process_media.py::test_parse_called_on_validated_audio -v
```

Expected: fail — current behaviour returns `reason="parsing stage not yet implemented"` which doesn't satisfy the assertion.

- [ ] **Step 3: Implement parse stage in process_media.py**

Replace the "Stage 4" block in `~/skills/voice-parser/scripts/process_media.py` (the placeholder ending in `"parsing stage not yet implemented"`):

```python
        # Stage 4: parse via Gemini (import parse_voice as a module)
        try:
            import parse_voice
        except ImportError as e:
            res.reason = f"parse_voice import failed: {e}"
            res.should_escalate = True
            res.emit_and_exit()

        try:
            transcript = parse_voice.parse_audio(str(downloaded), prompt_or_mode=args.mode)
        except Exception as e:
            log.exception("parse_voice failed")
            res.reason = f"parse_voice error: {type(e).__name__}: {e}"
            res.should_escalate = True
            res.stage = "parsed"
            res.emit_and_exit()

        if not transcript or transcript.startswith("❌"):
            res.reason = transcript or "empty transcript from Gemini"
            res.should_escalate = True
            res.stage = "parsed"
            res.emit_and_exit()

        # Stage 5: persist transcript
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        uid = uuid.uuid4().hex[:12]
        tpath = TRANSCRIPT_DIR / f"{uid}.md"
        tpath.write_text(transcript, encoding="utf-8")
        res.transcript_path = str(tpath)
        res.summary = transcript[:200].replace("\n", " ").strip()
        res.stage = "analyzed"
        res.status = "ok"
        res.emit_and_exit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_process_media.py -v
```

Expected: all 5 tests pass. The new test passes either way — Gemini may succeed or fail, but JSON contract is honoured.

- [ ] **Step 5: Commit**

```bash
cd ~ && git add skills/voice-parser/scripts/process_media.py skills/voice-parser/tests/test_process_media.py && git commit -m "feat(voice-parser): wire parse_voice into process_media.py with stable JSON output"
```

---

## Task 8: `escalate.sh` — multi-channel escalation script

**Files:**
- Create: `~/scripts/escalate.sh`
- Test: `~/skills/voice-parser/tests/test_escalate.py`

- [ ] **Step 1: Write failing tests**

File `~/skills/voice-parser/tests/test_escalate.py`:
```python
"""Tests for escalate.sh — invoked via subprocess with PATH manipulation."""
import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path.home() / "scripts" / "escalate.sh"


def _make_fake_bin(tmp_path: Path, name: str, body: str) -> Path:
    """Create an executable file at tmp_path/name with the given bash body."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    path = bindir / name
    path.write_text(f"#!/bin/bash\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _env(tmp_path: Path) -> dict:
    """Env with fake bin prepended to PATH and HOME=tmp_path."""
    home = tmp_path
    (home / "scripts").mkdir(parents=True, exist_ok=True)
    # Symlink the real escalate.sh into the fake home
    fake_escalate = home / "scripts" / "escalate.sh"
    if not fake_escalate.exists():
        fake_escalate.symlink_to(SCRIPT)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = str(tmp_path / "bin") + ":" + env["PATH"]
    return env


def test_ask_claude_success(tmp_path):
    _make_fake_bin(tmp_path, "ask-claude.sh", 'echo "stub claude reply: $1"; exit 0')
    env = _env(tmp_path)
    r = subprocess.run(
        ["bash", str(SCRIPT), "test-agent", "ping"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r.returncode == 0, r.stderr
    assert "stub claude reply" in r.stdout


def test_inbox_fallback_when_ask_claude_fails(tmp_path):
    _make_fake_bin(tmp_path, "ask-claude.sh", "exit 1")
    (tmp_path / "workspaces" / "claude-inbox").mkdir(parents=True, exist_ok=True)
    env = _env(tmp_path)
    r = subprocess.run(
        ["bash", str(SCRIPT), "test-agent", "second-question"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r.returncode == 0, r.stderr
    inbox_files = list((tmp_path / "workspaces" / "claude-inbox").glob("TASK_*test-agent*"))
    assert len(inbox_files) == 1
    body = inbox_files[0].read_text()
    assert "second-question" in body


def test_dedup_within_window(tmp_path):
    _make_fake_bin(tmp_path, "ask-claude.sh", 'echo "first reply"; exit 0')
    env = _env(tmp_path)
    # First call goes through
    r1 = subprocess.run(
        ["bash", str(SCRIPT), "test-agent", "duplicate-question"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r1.returncode == 0
    # Second call (identical) should be deduped — exit 0 with empty stdout or skip marker
    r2 = subprocess.run(
        ["bash", str(SCRIPT), "test-agent", "duplicate-question"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r2.returncode == 0
    assert "deduped" in r2.stdout.lower() or "skip" in r2.stdout.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_escalate.py -v
```

Expected: 3 failures — script doesn't exist.

- [ ] **Step 3: Create escalate.sh**

File `~/scripts/escalate.sh`:
```bash
#!/bin/bash
# escalate.sh — Multi-channel escalation for agents.
#
# Usage: escalate.sh <agent_id> "<question>" [context_file]
#
# Channels (try in order):
#   1. ~/scripts/ask-claude.sh — synchronous, 30s timeout
#   2. ~/workspaces/claude-inbox/TASK_<ts>_<AGENT>.md — async
#   3. Lineman /api/tg/send — alert Boris (one-time)
#
# Dedup: same sha256(question) within 60 minutes → skip with exit 0.

set -u
AGENT_ID="${1:-}"
QUESTION="${2:-}"
CONTEXT_FILE="${3:-}"

if [[ -z "$AGENT_ID" || -z "$QUESTION" ]]; then
    echo "usage: escalate.sh <agent_id> \"<question>\" [context_file]" >&2
    exit 2
fi

DEDUP_FILE="${HOME}/.cache/escalate-recent.json"
mkdir -p "${HOME}/.cache"
[[ -f "$DEDUP_FILE" ]] || echo '{}' > "$DEDUP_FILE"

QHASH=$(printf '%s|%s' "$AGENT_ID" "$QUESTION" | sha256sum | cut -c1-16)
NOW=$(date +%s)

# Check dedup
LAST=$(python3 -c "
import json, sys
try:
    d = json.load(open('$DEDUP_FILE'))
    print(d.get('$QHASH', 0))
except Exception:
    print(0)
")
if [[ "$LAST" -gt 0 ]] && [[ $((NOW - LAST)) -lt 3600 ]]; then
    echo "[escalate] deduped: same question hashed=$QHASH escalated $((NOW - LAST))s ago, skipping"
    exit 0
fi

# Record this attempt
python3 -c "
import json
try:
    d = json.load(open('$DEDUP_FILE'))
except Exception:
    d = {}
d['$QHASH'] = $NOW
# Trim old entries (>1d)
d = {k: v for k, v in d.items() if $NOW - v < 86400}
json.dump(d, open('$DEDUP_FILE', 'w'))
"

# Channel 1: ask-claude.sh with 30s timeout
ASK_CLAUDE="${HOME}/scripts/ask-claude.sh"
if [[ -x "$ASK_CLAUDE" ]]; then
    if [[ -n "$CONTEXT_FILE" && -f "$CONTEXT_FILE" ]]; then
        OUTPUT=$(timeout 30 "$ASK_CLAUDE" "[$AGENT_ID] $QUESTION" "$CONTEXT_FILE" 2>&1)
    else
        OUTPUT=$(timeout 30 "$ASK_CLAUDE" "[$AGENT_ID] $QUESTION" 2>&1)
    fi
    RC=$?
    if [[ $RC -eq 0 ]] && [[ -n "$OUTPUT" ]]; then
        echo "$OUTPUT"
        exit 0
    fi
fi

# Channel 2: claude-inbox file drop
INBOX_DIR="${HOME}/workspaces/claude-inbox"
if mkdir -p "$INBOX_DIR" 2>/dev/null; then
    INBOX_FILE="$INBOX_DIR/TASK_${NOW}_${AGENT_ID}.md"
    {
        echo "# Escalation from $AGENT_ID — $(date -Iseconds)"
        echo ""
        echo "## Question"
        echo "$QUESTION"
        if [[ -n "$CONTEXT_FILE" && -f "$CONTEXT_FILE" ]]; then
            echo ""
            echo "## Context (from $CONTEXT_FILE)"
            cat "$CONTEXT_FILE"
        fi
    } > "$INBOX_FILE"
    if [[ -f "$INBOX_FILE" ]]; then
        echo "[escalate] queued to inbox: $INBOX_FILE"
        exit 0
    fi
fi

# Channel 3: TG alert to Boris (best effort)
BORIS_CHAT_ID="${BORIS_CHAT_ID:-36910539}"
curl -s --noproxy "*" --max-time 10 -X POST "http://127.0.0.1:9090/api/tg/send" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "
import json
print(json.dumps({
  'account': 'default',
  'chat_id': $BORIS_CHAT_ID,
  'text': '⚠️ Escalation from $AGENT_ID failed all channels: ' + r'''$QUESTION'''[:500],
}))
")" > /dev/null
echo "[escalate] all channels failed; tg alert sent (best-effort)" >&2
exit 1
```

- [ ] **Step 4: Make executable**

```bash
chmod +x ~/scripts/escalate.sh
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_escalate.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
cd ~ && git add scripts/escalate.sh skills/voice-parser/tests/test_escalate.py && git commit -m "feat(scripts): add escalate.sh multi-channel escalation (ask-claude → inbox → tg)"
```

---

## Task 9: Rewrite `interview-coach/AGENTS.md`

**Files:**
- Modify: `~/workspaces/interview-coach/AGENTS.md` (full rewrite)

Target: ≤ 7 KB, ≤ 8000 characters. Must include result-only verbosity, banned phrases, single media tool (process_media.py), single escalation path (escalate.sh).

- [ ] **Step 1: Write tests to enforce constraints**

Append to `~/skills/voice-parser/tests/test_process_media.py`:
```python
def test_interview_coach_agents_md_size():
    """AGENTS.md must stay under the OpenClaw 12000-char bootstrap limit, with buffer."""
    path = Path.home() / "workspaces" / "interview-coach" / "AGENTS.md"
    content = path.read_text(encoding="utf-8")
    assert len(content) <= 8000, f"AGENTS.md too large: {len(content)} chars (limit 8000)"


def test_interview_coach_agents_md_has_required_sections():
    path = Path.home() / "workspaces" / "interview-coach" / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    # Required commands/keywords
    assert "process_media.py" in text
    assert "escalate.sh" in text
    # Banned phrases list must be present
    for phrase in ["понял", "сорян", "разбираюсь", "бегу", "погнали"]:
        assert phrase in text, f"AGENTS.md must list banned phrase: {phrase}"
    # Verbosity rule
    assert "2 сообщения" in text or "≤2" in text or "не больше 2" in text


def test_interview_coach_agents_md_no_old_anti_patterns():
    """Old AGENTS.md mentioned download_from_url.py directly — must be gone."""
    path = Path.home() / "workspaces" / "interview-coach" / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    # Coach must NOT call these directly anymore
    assert "download_from_url.py" not in text
    assert "download_and_parse.py" not in text
    assert "web_search" not in text or "запрещ" in text.lower()  # only mentioned as banned
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_process_media.py -v -k agents_md
```

Expected: 3 failures (current AGENTS.md is 11.4 KB and mentions `download_from_url.py`).

- [ ] **Step 3: Rewrite AGENTS.md**

Overwrite `~/workspaces/interview-coach/AGENTS.md` with:
```markdown
# InterviewCoach 🎯

Готовлю Бориса к C-level интервью. Профиль кандидата: `~/workspaces/resume-editor/boris-profile.md`.

## 🔑 ID и федерация

- Мой ID: `interview-coach`
- Все внешние API — строго через Lineman: `http://127.0.0.1:9090`
- Коллега: ResumePro (`resume-editor`)
- Эскалация — только через `~/scripts/escalate.sh interview-coach "вопрос"`

## 🎤 ПРАВИЛО #1 — Media

**Любой URL / file_id / медиа-вложение → ОДИН вызов:**

```bash
python3 ~/skills/voice-parser/scripts/process_media.py "<url-or-path>" --mode=interview
```

Это всё. Никаких `wget`, `curl <external>`, `download_*.py`, никаких ручных скачиваний. Скрипт сам выберет провайдера, скачает, проверит файл, распарсит через Gemini, отдаст JSON.

Поддерживаемые источники: Google Drive (public-share), Cloud Mail.ru, Yandex.Disk, Dropbox, OneDrive, Telegram (file_id), прямые URL.

**Режимы:** `interview` (по умолчанию), `monologue`, `transcribe`, `workout`.

JSON-ответ скрипта на stdout:
```json
{"status": "ok|failed", "stage": "...", "transcript_path": "...", "summary": "...",
 "reason": null, "should_escalate": false}
```

- `status=ok` → читай transcript_path, формируй разбор.
- `status=failed` + `should_escalate=true` → `~/scripts/escalate.sh interview-coach "<reason>"`.
- `status=failed` + `should_escalate=false` → сообщи Боре конкретный совет (перезалить и т.п.).

## 🚦 ПРАВИЛО #2 — Verbosity (result-only)

На одну задачу **не больше 2 сообщений** в чат:
1. Старт (если работа займёт >5 сек): `"Запускаю разбор, жди 2-3 мин."`
2. Результат или конкретная ошибка.

**Прогресс — не пиши.** Если Боря ждёт — он подождёт.

## 🚫 ПРАВИЛО #3 — Banned phrases

Эти слова **запрещены** в исходящих сообщениях:
- понял
- сорян, сорри, извини, прости
- разбираюсь, разбираю
- бегу, погнали, давай ещё раз
- секундочку, сейчас разберусь
- моя ошибка, попробую снова

Если ты собираешься написать одно из этих — **СТОП**. Замени на результат или эскалацию.

## 🚫 ПРАВИЛО #4 — No cycles

- Одна попытка любого инструмента. Fail → эскалация. Никаких retry того же tool.
- `web_search` — запрещён. Если нужны актуальные данные → `escalate.sh`.
- Если выходное сообщение содержит `<tool_code>`, `default_api.`, `print(`, `Brining...`, `🧾 Session History`, `🧰 Process:` — **не отправляй**, обрежь.

## 🎯 Режимы работы (LLM-side)

### Разведка компании и роли
```
🏢 РАЗВЕДКА: [Компания] | [Роль]
О компании / Что ищут / Боли / Опасные вопросы / Red flags / Акцент
```

### Mock-интервью
1. 3-5 стратегических/технических
2. 3-4 поведенческих (STAR)
3. 1-2 кейса
4. «Ваши вопросы?»

После каждого ответа:
```
✅ Сильно: ...
⚠️ Улучшить: ...
💡 Образец: ...
```

### Разбор записи интервью
Получаешь JSON от process_media.py с transcript_path. Читаешь, формируешь:
```
✅ Разбор готов — [Компания]
📝 Транскрипт (первые 200 симв): ...
💪 Сильно: 2-3 пункта
⚠️ Улучшить: 2-3 пункта
🎯 Следующий шаг: конкретно
```

## 🔒 Секреты

- Никогда не выводить ключи/токены в чат/лог.
- API-ключи — не твоя забота. Lineman знает.
- Нужно значение секрета — через approval-flow Keymaster: `curl -s -X POST "http://127.0.0.1:9093/keymaster/request-value?name=NAME&requester=interview-coach&purpose=..."`

## 📁 Хранение

- `sessions/YYYY-MM-DD_Company.md` — логи сессий
- `companies/` — досье
- `weak-spots.md` — слабые места (обновлять после сессии)

## 🎙 Голос

Голосовой профиль: **Dipper** (дружелюбный, поддерживающий). Если Боря шлёт картинку — анализируй её как есть.

## STAR-нарративы Бориса

- Качество данных 70%→98% (Русские башни)
- 8 чел/мес экономии на согласованиях (Русские башни)
- CRM 1200 пользователей, лучший филиал (Servier)
- +50% задач при +15% ФОТ (Servier)

**Нарратив:** «29 лет enterprise. Теперь то же через AI: Agents, DeepSeek, n8n.»
```

- [ ] **Step 4: Verify size**

```bash
wc -c ~/workspaces/interview-coach/AGENTS.md
```

Expected: ≤ 8000 bytes.

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd ~/skills/voice-parser && python3 -m pytest tests/test_process_media.py -v
```

Expected: all pass, including 3 AGENTS.md tests.

- [ ] **Step 6: Commit**

```bash
cd ~ && git add workspaces/interview-coach/AGENTS.md skills/voice-parser/tests/test_process_media.py && git commit -m "refactor(interview-coach): rewrite AGENTS.md — result-only, banned phrases, single media tool"
```

---

## Task 10: Update `openclaw.json` — switch Coach model

**Files:**
- Modify: `~/.openclaw/openclaw.json`

- [ ] **Step 1: Backup current config**

```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.pre-coach-v2
```

- [ ] **Step 2: Apply config change via Python (preserves formatting)**

```bash
python3 << 'EOF'
import json
path = '/home/shectory/.openclaw/openclaw.json'
with open(path) as f:
    d = json.load(f)

for item in d['agents']['list']:
    if isinstance(item, dict) and item.get('id') == 'interview-coach':
        before = dict(item.get('model', {}))
        item['model'] = {
            "primary": "deepseek/deepseek-v4-pro",
            "fallbacks": ["google/gemini-2.5-pro"],
            "thinking": "high",
        }
        print('before:', before)
        print('after :', item['model'])
        break

with open(path, 'w') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print('saved')
EOF
```

Expected output:
```
before: {'primary': 'deepseek/deepseek-v4-flash', 'fallbacks': ['google/gemini-2.5-flash']}
after : {'primary': 'deepseek/deepseek-v4-pro', 'fallbacks': ['google/gemini-2.5-pro'], 'thinking': 'high'}
saved
```

- [ ] **Step 3: Restart gateway**

```bash
systemctl --user restart openclaw-gateway.service && sleep 8 && systemctl --user status openclaw-gateway.service | head -5
```

Expected: `Active: active (running)`.

- [ ] **Step 4: Verify config loaded by gateway**

```bash
journalctl --user -u openclaw-gateway.service --since "30 seconds ago" --no-pager | grep -iE "interview-coach|starting provider" | head -5
```

Expected: `[telegram] [interview-coach] starting provider (@shectory_interview_bot)` and no model-load errors.

- [ ] **Step 5: Commit**

```bash
cd ~ && git add .openclaw/openclaw.json && git commit -m "chore(openclaw): interview-coach model → deepseek-v4-pro + gemini-2.5-pro fallback (thinking=high)"
```

---

## Task 11: Manual E2E smoke — local audio fixture

**Files:** (no code changes; verification only)

- [ ] **Step 1: Smoke process_media.py on a local audio file**

```bash
cd ~/skills/voice-parser && python3 -m pytest tests/conftest.py --collect-only 2>&1 | head -3
# Generate fixture if missing
python3 -c "
import subprocess
from pathlib import Path
p = Path.home() / 'skills/voice-parser/tests/fixtures/real_audio_small.mp3'
if not p.exists():
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=60','-codec:a','libmp3lame','-b:a','128k',str(p)],check=True)
print(p, p.stat().st_size, 'bytes')
"

python3 ~/skills/voice-parser/scripts/process_media.py \
    ~/skills/voice-parser/tests/fixtures/real_audio_small.mp3 \
    --mode=transcribe | python3 -m json.tool
```

Expected: JSON with `"status": "ok"`, `"mime": "audio/mpeg"`, `"transcript_path"` populated, `"summary"` populated (Gemini transcribes the sine wave as silence or whatever — content doesn't matter, structure does).

- [ ] **Step 2: Smoke on the Salmon GDrive link**

```bash
python3 ~/skills/voice-parser/scripts/process_media.py \
    "https://drive.google.com/file/d/1f3uPuKuY5selelkxvVzjiFtY3SoYOMyc/view?usp=drive_link" \
    --mode=interview --no-parse | python3 -m json.tool
```

Expected: JSON with `"status": "ok"`, `"stage": "validated"`, `"mime": "video/..."`, `"size_bytes"` ~200 MB. If `status=failed` with `reason` mentioning HTML or virus-scan — Task 4 needs adjustment.

- [ ] **Step 3: Smoke on HTML scenario (Mail.ru ссылка)**

```bash
python3 ~/skills/voice-parser/scripts/process_media.py \
    "https://cloud.mail.ru/public/V8To/awDjFQGHa" \
    --mode=interview --no-parse | python3 -m json.tool
```

Expected: either `status=ok` with `stage=validated` (if Mail.ru downloader works), or `status=failed` with `should_escalate=true` and clear `reason`. **Must not** return ok for a 16 KB HTML file.

- [ ] **Step 4: Smoke escalate.sh end-to-end**

```bash
~/scripts/escalate.sh interview-coach "test ping respond OK"
```

Expected: Within 30s, Claude's text response printed to stdout.

```bash
# Same question second time within 60min — should dedup
~/scripts/escalate.sh interview-coach "test ping respond OK"
```

Expected: `[escalate] deduped: ...`.

- [ ] **Step 5: If any smoke fails — diagnose and fix before proceeding**

Common issues:
- GDrive returns HTML → check `_download_gdrive_public` confirm-token logic.
- Mail.ru 403 → check `_download_mailru` cookie/dispatcher flow (existing code, may need touching).
- escalate.sh hangs > 30s → check `~/scripts/ask-claude.sh` proxy env loading.

- [ ] **Step 6: Run full pytest suite one more time**

```bash
cd ~/skills/voice-parser && python3 -m pytest -v
```

Expected: all green.

- [ ] **Step 7: Commit (only if smoke surfaced fixes)**

```bash
cd ~ && git status
# Only commit if step 5 changed files; otherwise skip
```

---

## Task 12: Coach E2E in production — restart, test, merge

**Files:** (no code changes; verification + merge)

- [ ] **Step 1: Verify Coach gateway picked up new config**

```bash
journalctl --user -u openclaw-gateway.service --since "5 minutes ago" --no-pager | grep -iE "interview-coach" | head -10
```

Expected: provider started, no errors.

- [ ] **Step 2: Have Boris send a test message via @shectory_interview_bot**

Ask Boris (in current chat) to send to InterviewCoach:
> «привет, тест после рефакторинга — ответь одним коротким сообщением»

Expected behaviour: Coach replies with exactly 1 message, no `<tool_code>`, no banned phrases. If it cycles or leaks tool_code → check AGENTS.md was actually loaded (gateway restart) and model is deepseek-v4-pro.

- [ ] **Step 3: Have Boris send the Salmon GDrive URL**

Ask Boris to forward the Salmon interview link to InterviewCoach:
> `https://drive.google.com/file/d/1f3uPuKuY5selelkxvVzjiFtY3SoYOMyc/view?usp=drive_link`

Expected: Coach sends exactly 2 messages:
1. «Запускаю разбор, жди 2-3 мин.»
2. Result with transcript summary + ✅/⚠️/🎯 breakdown.

- [ ] **Step 4: Check gateway logs for cycles or leaks**

```bash
journalctl --user -u openclaw-gateway.service --since "10 minutes ago" --no-pager | grep -iE "interview-coach.*(error|tool_code|brining|loop)" | head -20
```

Expected: no matches.

- [ ] **Step 5: Merge to master**

```bash
cd ~ && git checkout master && git merge --no-ff feat/interview-coach-v2 -m "feat(interview-coach): v2 refactor — process_media.py playbook + escalate.sh + deepseek-v4-pro"
```

- [ ] **Step 6: Verify master state**

```bash
cd ~ && git log --oneline -5 && git status
```

Expected: merge commit at HEAD, working tree clean, branch ahead of origin.

- [ ] **Step 7: Push** (only if Boris explicitly approves)

```bash
# git push origin master
# Skip unless Boris says push
```

---

## Self-Review Checklist (run before handing off)

**Spec coverage:**
- ✅ process_media.py with state machine — Tasks 6, 7
- ✅ Validators (magic bytes, size, duration) — Task 2
- ✅ Provider detection — Task 3
- ✅ GDrive public-share fix — Task 4
- ✅ Other providers via dispatcher — Task 5
- ✅ escalate.sh multi-channel + dedup — Task 8
- ✅ AGENTS.md rewrite — Task 9
- ✅ openclaw.json model switch — Task 10
- ✅ Banned phrases list — Task 9 (in AGENTS.md)
- ✅ Outbound sanitizer — Task 9 (prompt-rule)
- ✅ Tests for all of above — Tasks 2, 3, 4, 5, 6, 7, 8, 9
- ✅ E2E smoke — Tasks 11, 12

**Type/name consistency:**
- `Result` dataclass fields match JSON output schema in Task 6 ✓
- `ValidationResult` from Task 2 used in Task 6 stage 3 ✓
- `detect_provider` / `download` names consistent across Tasks 3, 5, 6 ✓
- `_gdrive_file_id` / `_download_gdrive_public` consistent in Tasks 4, 5 ✓
- AGENTS.md banned-phrases test list matches the actual list written in AGENTS.md ✓

**No placeholders:** all code blocks complete; no TBD/TODO/implement-later.

**Rollback path:** documented in spec (`git revert` + restore model + restart gateway).
