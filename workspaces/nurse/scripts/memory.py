#!/usr/bin/env python3
"""
Compact nurse memory manager — SQLite-backed.

Commands:
  save              — read JSON from stdin, store entry, print ID:<n>
                      JSON: {"role":"user|nurse","chat_id":"...","full_text":"...","summary":"..."}
  context           — print compact context (last 30 entries by default)
    --chat <id>     — filter by chat_id
    --last <n>      — limit to last n entries (default 30)
  get <id>          — print full verbatim text by entry ID
  stats             — print entry count and DB size

Usage in nurse CLAUDE.md:
  # Read context before responding:
  python3 ~/workspaces/nurse/scripts/memory.py context

  # Save after responding (stdin JSON, nurse generates the summary):
  python3 ~/workspaces/nurse/scripts/memory.py save <<'JSON'
  {"role": "user", "chat_id": "36910539", "full_text": "...", "summary": "1 sentence"}
  JSON
"""

import sys
import os
import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/workspaces/nurse/memory/nurse_db.sqlite")


def _db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    NOT NULL,
            role      TEXT    NOT NULL,
            chat_id   TEXT    NOT NULL,
            full_text TEXT    NOT NULL,
            summary   TEXT    NOT NULL
        )
    """)
    db.commit()
    return db


def cmd_save():
    raw = sys.stdin.read().strip()
    data = json.loads(raw)
    role      = data["role"]
    chat_id   = data["chat_id"]
    full_text = data["full_text"]
    summary   = data["summary"]

    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M")
    db = _db()
    cur = db.execute(
        "INSERT INTO entries (ts, role, chat_id, full_text, summary) VALUES (?,?,?,?,?)",
        (ts, role, chat_id, full_text, summary),
    )
    db.commit()
    print(f"ID:{cur.lastrowid}")


def cmd_context(chat_id=None, last=30):
    db = _db()
    if chat_id:
        rows = db.execute(
            "SELECT id, ts, role, summary FROM entries "
            "WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, last),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, ts, role, summary FROM entries ORDER BY id DESC LIMIT ?",
            (last,),
        ).fetchall()

    rows.reverse()
    if not rows:
        print("(нет записей)")
        return

    lines = []
    for entry_id, ts, role, summary in rows:
        label = "Борис" if role == "user" else "Медсестра"
        time_part = ts[11:16] if len(ts) >= 16 else ts
        lines.append(f"[{entry_id}] {time_part} {label}: {summary}")
    print("\n".join(lines))


def cmd_get(entry_id):
    db = _db()
    row = db.execute(
        "SELECT full_text FROM entries WHERE id=?", (entry_id,)
    ).fetchone()
    if row:
        print(row[0])
    else:
        print(f"Запись {entry_id} не найдена", file=sys.stderr)
        sys.exit(1)


def cmd_stats():
    db = _db()
    count = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    print(f"Записей: {count}, Размер БД: {size // 1024}KB")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "save":
        cmd_save()

    elif cmd == "context":
        chat_id = None
        last = 30
        i = 1
        while i < len(args):
            if args[i] == "--chat" and i + 1 < len(args):
                chat_id = args[i + 1]
                i += 2
            elif args[i] == "--last" and i + 1 < len(args):
                last = int(args[i + 1])
                i += 2
            else:
                i += 1
        cmd_context(chat_id, last)

    elif cmd == "get":
        if len(args) < 2:
            print("Использование: memory.py get <id>", file=sys.stderr)
            sys.exit(1)
        cmd_get(int(args[1]))

    elif cmd == "stats":
        cmd_stats()

    else:
        print(f"Неизвестная команда: {cmd}", file=sys.stderr)
        sys.exit(1)
