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
