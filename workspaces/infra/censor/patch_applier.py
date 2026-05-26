"""
patch_applier.py — reads investigation JSON from stdin, applies patches, commits, notifies.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FIXES_LOG = Path.home() / "logs" / "censor" / "fixes.jsonl"
REPO_DIR = Path.home()
BORIS_CHAT_ID = "36910539"
LINEMAN_TG_URL = "http://localhost:9090/api/tg/send"
PM2_BIN = "/home/shectory/.npm/_npx/5f7878ce38f1eb13/node_modules/pm2/bin/pm2"


def send_tg(text: str) -> None:
    payload = json.dumps({"chat_id": BORIS_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(
        LINEMAN_TG_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        print(f"[patch_applier] TG failed: {exc}", file=sys.stderr)


def backup_file(path: Path, ts: str) -> Path:
    backup = Path(f"{path}.censor-backup-{ts}")
    shutil.copy2(path, backup)
    return backup


def replace_in_dict(obj, old_val, new_val) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(v) == str(old_val):
                obj[k] = new_val
                return True
            if isinstance(v, (dict, list)) and replace_in_dict(v, old_val, new_val):
                return True
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if str(item) == str(old_val):
                obj[i] = new_val
                return True
            if isinstance(item, (dict, list)) and replace_in_dict(item, old_val, new_val):
                return True
    return False


def apply_json_key(path: Path, old_val, new_val) -> None:
    text = path.read_text()
    d = json.loads(text)
    if not replace_in_dict(d, old_val, new_val):
        raise ValueError(f"Value '{old_val}' not found in {path}")
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False))


def apply_text_replace(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise ValueError(f"String '{old[:50]}' not found in {path}")
    path.write_text(text.replace(old, new, 1))


def apply_file_append(path: Path, content: str) -> None:
    with open(path, "a") as f:
        f.write(content if content.endswith("\n") else content + "\n")


def apply_patch(patch: dict, ts: str) -> Path:
    fpath = Path(patch["file"])
    if not fpath.exists():
        raise FileNotFoundError(f"Patch target not found: {fpath}")
    backup = backup_file(fpath, ts)
    ptype = patch["type"]
    old = patch.get("old", "")
    new = patch.get("new", "")
    try:
        if ptype == "json_key":
            apply_json_key(fpath, old, new)
            json.loads(fpath.read_text())  # validate JSON
        elif ptype == "text_replace":
            apply_text_replace(fpath, old, new)
        elif ptype == "file_append":
            apply_file_append(fpath, new)
        else:
            raise ValueError(f"Unknown patch type: {ptype}")
    except Exception:
        shutil.copy2(backup, fpath)
        backup.unlink(missing_ok=True)
        raise
    return fpath


def git_commit(files: list[Path], agent: str, root_cause: str, expected: str) -> str:
    short = root_cause[:60].replace("\n", " ")
    msg = f"censor-autopilot: fix {agent} — {short}\n\nExpected: {expected}"
    for f in files:
        subprocess.run(["git", "-C", str(REPO_DIR), "add", str(f)], check=True)
    result = subprocess.run(
        ["git", "-C", str(REPO_DIR), "commit", "-m", msg],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr}")
    h = subprocess.run(
        ["git", "-C", str(REPO_DIR), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return h.stdout.strip()


def restart_pm2(processes: list[str]) -> None:
    for name in processes:
        result = subprocess.run([PM2_BIN, "restart", name], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[patch_applier] pm2 restart {name} failed: {result.stderr}", file=sys.stderr)


def log_fix(entry: dict) -> None:
    FIXES_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXES_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    data = json.loads(sys.stdin.read())
    agent = data["agent"]
    since = data["since"]
    analysis = data["analysis"]
    patches = analysis.get("patches", [])
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    changed_files: list[Path] = []
    for patch in patches:
        try:
            changed_files.append(apply_patch(patch, ts))
            print(f"[patch_applier] patched {patch['file']}")
        except Exception as exc:
            print(f"[patch_applier] patch failed: {exc}", file=sys.stderr)

    if not changed_files:
        send_tg(
            f"[Autopilot] Аномалия: {agent}\n"
            f"Root cause: {analysis.get('root_cause')}\n"
            f"Все патчи провалились."
        )
        return

    commit = ""
    try:
        commit = git_commit(
            changed_files, agent,
            analysis.get("root_cause", ""),
            analysis.get("expected_improvement", ""),
        )
    except Exception as exc:
        print(f"[patch_applier] git commit failed: {exc}", file=sys.stderr)

    restart_pm2(analysis.get("restart_pm2", []))

    log_fix({
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent, "since": since,
        "root_cause": analysis.get("root_cause"),
        "severity": analysis.get("severity"),
        "patches_applied": len(changed_files),
        "files_changed": [str(f) for f in changed_files],
        "commit": commit,
        "metrics_before": None, "metrics_after": None,
        "expected_improvement": analysis.get("expected_improvement"),
    })

    patch_lines = "".join(
        f"  {p['file']}\n    {p.get('old', '')} → {p.get('new', '')}\n"
        for p in patches
    )
    send_tg(
        f"[Autopilot] Аномалия: {agent}\n"
        f"Root cause: {analysis.get('root_cause', '?')}\n"
        f"Исправил:\n{patch_lines}"
        f"Коммит: {commit}\n"
        f"Ожидаемо: {analysis.get('expected_improvement', '?')}"
    )
    print(f"[patch_applier] done. commit={commit}")


if __name__ == "__main__":
    main()
