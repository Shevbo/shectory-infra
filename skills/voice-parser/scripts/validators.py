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
    except (subprocess.SubprocessError, FileNotFoundError, ValueError):
        return 0.0


def validate_media(path: Path) -> ValidationResult:
    """Validate that the file is a real audio/video file >= 100 KB and >= 30s."""
    if not path.exists():
        return ValidationResult(ok=False, reason=f"file not found: {path}", should_escalate=True)

    if not path.is_file():
        return ValidationResult(ok=False, reason=f"not a regular file: {path}", should_escalate=True)

    size = path.stat().st_size
    mime = magic.from_file(str(path), mime=True) or ""

    # Detect HTML masquerading as media (Mail.ru/GDrive bug, 28.05.2026):
    # error pages may be of any size and must be flagged as non-media before
    # the size check, so the reason makes it clear it is not a real file.
    if mime.startswith("text/html") or mime == "application/xhtml+xml":
        return ValidationResult(
            ok=False, reason=f"downloaded non-media file (mime={mime!r}); likely an HTML error page or wrong URL",
            should_escalate=True, mime=mime, size_bytes=size,
        )

    if size < MIN_SIZE_BYTES:
        return ValidationResult(
            ok=False, reason=f"file too small: {size} bytes (min {MIN_SIZE_BYTES})",
            should_escalate=True, mime=mime, size_bytes=size,
        )

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
