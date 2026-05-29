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
