#!/usr/bin/env python3
"""
One-time migration: read existing memory/*.md files → insert into nurse_db.sqlite.

Each .md entry looks like:
  ## HH:MM
  **Борис:** <text>
  **Медсестра:** <text>

The migrated entries use the file date + time from the header.
Full text = original text. Summary = first 80 chars (no LLM needed for migration).
"""

import os
import re
import sys
import sqlite3
import json
from pathlib import Path

DB_PATH = Path("~/workspaces/nurse/memory/nurse_db.sqlite").expanduser()
MEMORY_DIR = Path("~/workspaces/nurse/memory").expanduser()
CHAT_ID = "36910539"


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


def _summarize(text: str, max_chars: int = 80) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def migrate_file(db, date_str: str, path: Path) -> int:
    content = path.read_text(encoding="utf-8")
    # Split on ## HH:MM headers
    blocks = re.split(r"\n## (\d{2}:\d{2})\n", content)
    # blocks: [preamble, time, body, time, body, ...]

    count = 0
    i = 1
    while i < len(blocks) - 1:
        time_str = blocks[i].strip()
        body = blocks[i + 1].strip()
        ts = f"{date_str}T{time_str}"

        # Parse Борис and Медсестра lines from body
        boris_match = re.search(r"\*\*Борис:\*\*\s*(.+?)(?=\n\*\*|\Z)", body, re.DOTALL)
        nurse_match = re.search(r"\*\*Медсестра:\*\*\s*(.+?)(?=\n\*\*|\Z)", body, re.DOTALL)

        if boris_match:
            text = boris_match.group(1).strip()
            if text:
                db.execute(
                    "INSERT INTO entries (ts, role, chat_id, full_text, summary) VALUES (?,?,?,?,?)",
                    (ts, "user", CHAT_ID, text, _summarize(text)),
                )
                count += 1

        if nurse_match:
            text = nurse_match.group(1).strip()
            if text:
                db.execute(
                    "INSERT INTO entries (ts, role, chat_id, full_text, summary) VALUES (?,?,?,?,?)",
                    (ts, "nurse", CHAT_ID, text, _summarize(text)),
                )
                count += 1

        i += 2

    db.commit()
    return count


def main():
    db = _db()

    # Clear test entries (id 1 and 2 from testing)
    # We'll keep them only if real data exists in .md files
    md_files = sorted(MEMORY_DIR.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))

    if not md_files:
        print("Нет .md файлов памяти для миграции.")
        return

    total = 0
    for md_path in md_files:
        date_str = md_path.stem  # e.g. "2026-05-21"
        n = migrate_file(db, date_str, md_path)
        print(f"  {md_path.name}: {n} записей")
        total += n

    print(f"\nИтого мигрировано: {total} записей")

    # Show final stats
    count = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    size = os.path.getsize(DB_PATH)
    print(f"Всего в БД: {count} записей, {size // 1024}KB")


if __name__ == "__main__":
    main()
