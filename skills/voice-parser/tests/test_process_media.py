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


def test_parse_called_on_validated_audio(real_audio_small_mp3):
    """When --no-parse is omitted, parse_audio is called and result goes into JSON."""
    code, data = _run(
        [str(real_audio_small_mp3), "--mode=interview"],
        timeout=60,
    )
    # Parse stage must actually run (not stop at validated).
    assert data.get("stage") in ("parsed", "analyzed")
    # status may be ok (Gemini worked) or failed (key missing / quota / network).
    assert data.get("status") in ("ok", "failed")
    assert isinstance(data.get("should_escalate"), bool)
