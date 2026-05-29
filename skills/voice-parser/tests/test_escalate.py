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
