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
