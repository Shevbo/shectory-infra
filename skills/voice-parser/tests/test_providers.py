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
