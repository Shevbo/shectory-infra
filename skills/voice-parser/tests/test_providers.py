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


@responses.activate
def test_gdrive_public_download_with_form_confirm(tmp_path):
    """Modern GDrive returns a form (not <a>); parse action+inputs and POST."""
    from providers import _download_gdrive_public

    file_id = "1ABC"
    audio_bytes = b"\x00ID3" + b"\x00" * 300_000

    # First call returns HTML with form
    form_html = (
        '<html><body>'
        '<form id="download-form" action="https://drive.usercontent.google.com/download" method="get">'
        f'<input type="hidden" name="id" value="{file_id}">'
        '<input type="hidden" name="export" value="download">'
        '<input type="hidden" name="confirm" value="t">'
        '<input type="hidden" name="uuid" value="abc-uuid">'
        '</form></body></html>'
    )
    responses.add(
        responses.GET, "https://drive.google.com/uc",
        body=form_html, content_type="text/html",
    )
    # Second call to drive.usercontent.google.com returns the actual file
    responses.add(
        responses.GET, "https://drive.usercontent.google.com/download",
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


def test_parse_gdrive_confirm_form():
    from providers import _parse_gdrive_confirm_form
    html = (
        '<form id="download-form" action="https://drive.usercontent.google.com/download" method="get">'
        '<input type="hidden" name="id" value="ABC">'
        '<input type="hidden" name="export" value="download">'
        '<input type="hidden" name="confirm" value="t">'
        '</form>'
    )
    action, params = _parse_gdrive_confirm_form(html)
    assert action == "https://drive.usercontent.google.com/download"
    assert params == {"id": "ABC", "export": "download", "confirm": "t"}


def test_parse_gdrive_confirm_form_missing():
    from providers import _parse_gdrive_confirm_form
    action, params = _parse_gdrive_confirm_form("<html>no form</html>")
    assert action is None
    assert params == {}


def test_gdrive_extract_id():
    from providers import _gdrive_file_id
    assert _gdrive_file_id("https://drive.google.com/file/d/1ABC/view?usp=drive_link") == "1ABC"
    assert _gdrive_file_id("https://drive.google.com/open?id=2XYZ") == "2XYZ"
    assert _gdrive_file_id("https://drive.google.com/uc?id=3DEF&export=download") == "3DEF"
    assert _gdrive_file_id("https://example.com/no-id") is None


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
