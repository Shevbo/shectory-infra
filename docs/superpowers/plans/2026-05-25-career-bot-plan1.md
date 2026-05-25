# Career Bot — Implementation Plan (MVP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram-бот "Карьера" — единый оркестратор pipeline JobScanner → ResumePro → Apply → Application Browser.

**Architecture:** Бот-мозг на raw httpx (паттерн cc-bot), long polling, без внешних Telegram-библиотек. SQLite pipeline.db — единственный источник правды. Агенты вызываются через federation message API + файловый I/O. Бот polling'ом проверяет результат каждые 30 сек.

**Tech Stack:** Python 3.12, httpx (уже в системе), sqlite3 (stdlib), asyncio, venv для изоляции.

**Scope этого плана (MVP):** Tasks 1–9: scaffold, DB, parser отчётов, бот-core, digest flow, ResumePro integration, approval + snapshot, apply service, application browser.

**Out of scope (Plan 2):** InterviewCoach integration, voice mini-app.

---

## Файловая структура

```
~/workspaces/career-bot/
├── venv/                          # python venv (gitignored)
├── bot.py                         # точка входа, poll loop, dispatch
├── config.py                      # env vars, paths
├── db.py                          # SQLite init + CRUD
├── models.py                      # dataclasses
├── keyboards.py                   # builder inline/reply keyboards
├── scanner.py                     # парсер reports/*.md → DB
├── resume_service.py              # вызов ResumePro, polling результата
├── apply_service.py               # выбор навыка по платформе, вызов VBoris2
├── apply_skills/
│   ├── hh_apply.py                # hh.ru API
│   ├── email_apply.py             # SMTP
│   ├── tg_apply.py                # Telegram DM рекрутёру
│   └── manual_apply.py            # инструкция Борису, ждём подтверждения
├── handlers/
│   ├── digest.py                  # дайджест flow
│   ├── resume.py                  # резюме в работе / согласование
│   └── applications.py            # браузер откликов
├── pipeline.db                    # runtime (gitignored)
├── requirements.txt
├── .env                           # secrets (gitignored)
├── .env.example
└── tests/
    ├── test_db.py
    ├── test_scanner.py
    ├── test_keyboards.py
    └── test_apply_service.py
```

**Модифицируемые файлы агентов:**
- `~/workspaces/resume-editor/AGENTS.md` — добавить секцию CAREER TASK PROTOCOL

---

## Task 1: Scaffold + config + venv

**Files:**
- Create: `~/workspaces/career-bot/config.py`
- Create: `~/workspaces/career-bot/requirements.txt`
- Create: `~/workspaces/career-bot/.env.example`
- Create: `~/workspaces/career-bot/.gitignore`

- [ ] **Создать директорию и venv**

```bash
mkdir -p ~/workspaces/career-bot/tests ~/workspaces/career-bot/handlers ~/workspaces/career-bot/apply_skills
cd ~/workspaces/career-bot
python3 -m venv venv
source venv/bin/activate
pip install httpx pytest
```

- [ ] **Создать requirements.txt**

```
httpx==0.27.0
pytest==8.3.0
```

- [ ] **Создать config.py**

```python
import os
from pathlib import Path

BOT_TOKEN: str = os.environ["CAREER_BOT_TOKEN"]
BORIS_CHAT_ID: int = int(os.environ.get("BORIS_CHAT_ID", "36910539"))
PROXY_URL: str = os.environ.get("PROXY_URL", "http://127.0.0.1:9090")
DB_PATH: str = os.environ.get("CAREER_DB_PATH",
    str(Path.home() / "workspaces/career-bot/pipeline.db"))

JOBSEARCH_REPORTS_DIR = Path.home() / "workspaces/jobsearch/reports"
RESUME_EDITOR_DIR = Path.home() / "workspaces/resume-editor"
RESUME_TASKS_DIR = Path.home() / "workspaces/resume-editor/tasks"
RESUME_VERSIONS_DIR = Path.home() / "workspaces/resume-editor/versions"

FEDERATION_URL = os.environ.get("FEDERATION_URL", "http://127.0.0.1:9090")
AGENT_POLL_INTERVAL = 30   # сек
AGENT_POLL_TIMEOUT = 1800  # 30 мин

VOICE_PARSER = str(Path.home() / "skills/voice-parser/scripts/parse_voice.py")
TTS_FLOW = str(Path.home() / "skills/voice-profiles/scripts/tts_flow.py")
CAREER_VOICE_PROFILE = "career-bot"
```

- [ ] **Создать .env.example**

```bash
CAREER_BOT_TOKEN=<token from @BotFather>
BORIS_CHAT_ID=36910539
PROXY_URL=http://127.0.0.1:9090
FEDERATION_URL=http://127.0.0.1:9090
CAREER_DB_PATH=/home/shectory/workspaces/career-bot/pipeline.db
```

- [ ] **Создать .gitignore**

```
venv/
.env
pipeline.db
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Проверить что httpx импортируется**

```bash
cd ~/workspaces/career-bot && source venv/bin/activate && python3 -c "import httpx; print('ok')"
```
Ожидаемый вывод: `ok`

- [ ] **Инициализировать git и commit**

```bash
cd ~/workspaces/career-bot
git init
git add config.py requirements.txt .env.example .gitignore
git commit -m "feat(career-bot): project scaffold"
```

---

## Task 2: DB layer

**Files:**
- Create: `~/workspaces/career-bot/db.py`
- Create: `~/workspaces/career-bot/models.py`
- Create: `~/workspaces/career-bot/tests/test_db.py`

- [ ] **Создать models.py**

```python
from dataclasses import dataclass, field
from typing import Optional

VALID_STATUSES = [
    'new', 'in_digest', 'selected', 'draft_ready',
    'approved', 'applied', 'response', 'interview_prep', 'closed'
]

@dataclass
class Job:
    id: str
    title: str
    company: str
    score: int
    source: str
    source_url: str
    jd_text: str
    found_at: str = ""

@dataclass
class PipelineEntry:
    job_id: str
    status: str
    updated_at: str = ""
    recruiter_name: Optional[str] = None
    recruiter_contact: Optional[str] = None
    apply_platform: Optional[str] = None
    apply_confirmed_at: Optional[str] = None

@dataclass
class Snapshot:
    job_id: str
    resume_text: str
    cover_text: str
    approved_at: str = ""
```

- [ ] **Написать тест для DB (failing)**

```python
# tests/test_db.py
import os, sys, pytest, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("CAREER_BOT_TOKEN", "test")
    monkeypatch.setenv("CAREER_DB_PATH", db_path)
    import importlib, config
    importlib.reload(config)
    import db
    importlib.reload(db)
    db.init_db()
    return db

def test_upsert_and_get_job(tmp_db):
    tmp_db.upsert_job("j1", "CTO", "ACME", 85, "hh", "https://hh.ru/1", "Senior CTO role")
    job = tmp_db.get_job("j1")
    assert job["title"] == "CTO"
    assert job["score"] == 85

def test_set_and_get_status(tmp_db):
    tmp_db.upsert_job("j2", "CIO", "Corp", 70, "habr", "https://h.ru/2", "CIO role")
    tmp_db.set_status("j2", "selected")
    entry = tmp_db.get_pipeline("j2")
    assert entry["status"] == "selected"

def test_save_and_get_snapshot(tmp_db):
    tmp_db.upsert_job("j3", "CDTO", "Bank", 90, "hh", "https://hh.ru/3", "CDTO role")
    tmp_db.set_status("j3", "approved")
    tmp_db.save_snapshot("j3", "Full resume text here", "Full cover letter here")
    snap = tmp_db.get_snapshot("j3")
    assert snap["resume_text"] == "Full resume text here"
    assert snap["cover_text"] == "Full cover letter here"

def test_get_jobs_by_status(tmp_db):
    tmp_db.upsert_job("j4", "VP Eng", "Tech", 75, "tg", "", "VP role")
    tmp_db.set_status("j4", "applied")
    tmp_db.upsert_job("j5", "Head of AI", "AI Co", 80, "hh", "", "AI role")
    tmp_db.set_status("j5", "applied")
    jobs = tmp_db.get_jobs_by_status("applied")
    ids = [j["job_id"] for j in jobs]
    assert "j4" in ids and "j5" in ids
```

- [ ] **Запустить тест — убедиться что падает**

```bash
cd ~/workspaces/career-bot && source venv/bin/activate && python3 -m pytest tests/test_db.py -v
```
Ожидаемый вывод: `ModuleNotFoundError: No module named 'db'`

- [ ] **Создать db.py**

```python
import sqlite3
from contextlib import contextmanager
from typing import Optional
import config

@contextmanager
def _conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_db() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT,
            score INTEGER,
            source TEXT,
            source_url TEXT,
            jd_text TEXT,
            found_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS pipeline (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'new',
            updated_at TEXT DEFAULT (datetime('now')),
            recruiter_name TEXT,
            recruiter_contact TEXT,
            apply_platform TEXT,
            apply_confirmed_at TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            job_id TEXT PRIMARY KEY,
            resume_text TEXT NOT NULL,
            cover_text TEXT NOT NULL,
            approved_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            coach_session_path TEXT,
            started_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
        """)

def upsert_job(id: str, title: str, company: str, score: int,
               source: str, source_url: str, jd_text: str) -> None:
    with _conn() as c:
        c.execute("""INSERT OR IGNORE INTO jobs
            (id, title, company, score, source, source_url, jd_text)
            VALUES (?,?,?,?,?,?,?)""",
            (id, title, company, score, source, source_url, jd_text))
        c.execute("""INSERT OR IGNORE INTO pipeline (job_id, status)
            VALUES (?, 'new')""", (id,))

def get_job(job_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

def get_pipeline(job_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT p.*, j.title, j.company, j.score, j.source, j.source_url "
            "FROM pipeline p JOIN jobs j ON p.job_id=j.id WHERE p.job_id=?",
            (job_id,)).fetchone()
        return dict(row) if row else None

def set_status(job_id: str, status: str, **kwargs) -> None:
    fields = ["status=?", "updated_at=datetime('now')"]
    values = [status]
    for k, v in kwargs.items():
        fields.append(f"{k}=?")
        values.append(v)
    values.append(job_id)
    with _conn() as c:
        c.execute(f"UPDATE pipeline SET {', '.join(fields)} WHERE job_id=?", values)

def get_jobs_by_status(status: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT p.*, j.title, j.company, j.score, j.source, j.source_url "
            "FROM pipeline p JOIN jobs j ON p.job_id=j.id WHERE p.status=? "
            "ORDER BY j.score DESC",
            (status,)).fetchall()
        return [dict(r) for r in rows]

def get_active_pipeline() -> list[dict]:
    """Все вакансии в активной работе (selected и выше, кроме closed)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT p.*, j.title, j.company, j.score, j.source, j.source_url "
            "FROM pipeline p JOIN jobs j ON p.job_id=j.id "
            "WHERE p.status NOT IN ('new','in_digest','closed') "
            "ORDER BY CASE p.status "
            "  WHEN 'response' THEN 1 WHEN 'draft_ready' THEN 2 "
            "  WHEN 'approved' THEN 3 WHEN 'applied' THEN 4 "
            "  WHEN 'selected' THEN 5 ELSE 6 END",
            ).fetchall()
        return [dict(r) for r in rows]

def save_snapshot(job_id: str, resume_text: str, cover_text: str) -> None:
    with _conn() as c:
        c.execute("""INSERT OR REPLACE INTO snapshots
            (job_id, resume_text, cover_text, approved_at)
            VALUES (?, ?, ?, datetime('now'))""",
            (job_id, resume_text, cover_text))

def get_snapshot(job_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM snapshots WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

def mark_new_jobs_as_seen() -> None:
    """Переводит все 'new' в 'in_digest' — вызывается после показа дайджеста."""
    with _conn() as c:
        c.execute("UPDATE pipeline SET status='in_digest' WHERE status='new'")
```

- [ ] **Запустить тесты — убедиться что проходят**

```bash
cd ~/workspaces/career-bot && source venv/bin/activate && python3 -m pytest tests/test_db.py -v
```
Ожидаемый вывод: `4 passed`

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add db.py models.py tests/test_db.py && git commit -m "feat(career-bot): DB layer with 4 tables and CRUD"
```

---

## Task 3: Scanner — парсер отчётов JobScanner

**Files:**
- Create: `~/workspaces/career-bot/scanner.py`
- Create: `~/workspaces/career-bot/tests/test_scanner.py`

- [ ] **Написать тест (failing)**

```python
# tests/test_scanner.py
import os, sys, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

SAMPLE_REPORT = """
📊 **JOB DIGEST** · 2026-05-25

🔥 **Технический директор (нефтегазовая компания)** · 85/100 · постоянная
🏢 StaffRecruitment
💰 от 800,000 RUR · 📍 Москва
📋 Ищем CTO для крупной нефтегазовой компании. Опыт от 10 лет.
🔗 https://hh.ru/vacancy/131752505

📌 **Chief Technology Officer** · 60/100 · постоянная
🏢 @forchiefs
💰 не указана · 🌍 Remote
📋 CTO for Muse Group, music tech company.
🔗 
"""

def test_parse_report_finds_two_jobs():
    from scanner import parse_report_text
    jobs = parse_report_text(SAMPLE_REPORT)
    assert len(jobs) == 2

def test_parse_report_extracts_fields():
    from scanner import parse_report_text
    jobs = parse_report_text(SAMPLE_REPORT)
    hot = next(j for j in jobs if j["score"] == 85)
    assert hot["title"] == "Технический директор (нефтегазовая компания)"
    assert hot["company"] == "StaffRecruitment"
    assert hot["source_url"] == "https://hh.ru/vacancy/131752505"
    assert hot["source"] == "hh"
    assert "CTO" in hot["jd_text"]

def test_parse_report_derives_source_for_telegram():
    from scanner import parse_report_text
    jobs = parse_report_text(SAMPLE_REPORT)
    tg = next(j for j in jobs if j["score"] == 60)
    assert tg["source"] == "telegram"
    assert tg["company"] == "@forchiefs"

def test_job_id_is_stable():
    from scanner import parse_report_text
    jobs1 = parse_report_text(SAMPLE_REPORT)
    jobs2 = parse_report_text(SAMPLE_REPORT)
    assert jobs1[0]["id"] == jobs2[0]["id"]
```

- [ ] **Запустить — убедиться что падает**

```bash
cd ~/workspaces/career-bot && source venv/bin/activate && python3 -m pytest tests/test_scanner.py -v
```

- [ ] **Создать scanner.py**

```python
import re
import hashlib
from pathlib import Path
from typing import Optional
import config
import db

def _derive_source(url: str, company: str) -> str:
    if "hh.ru" in url:
        return "hh"
    if "habr" in url:
        return "habr"
    if "getmatch" in url:
        return "getmatch"
    if "superjob" in url:
        return "superjob"
    if company.startswith("@"):
        return "telegram"
    if "@" in company:
        return "email"
    return "other"

def _stable_id(url: str, title: str, company: str) -> str:
    key = url if url else f"{title}|{company}"
    return hashlib.md5(key.encode()).hexdigest()[:16]

def parse_report_text(text: str) -> list[dict]:
    """Парсит текст отчёта JobScanner, возвращает список вакансий."""
    jobs = []
    # Каждый блок начинается с 🔥 или 📌
    blocks = re.split(r"(?=(?:🔥|📌)\s+\*\*)", text)
    for block in blocks:
        job = _parse_block(block.strip())
        if job:
            jobs.append(job)
    return jobs

def _parse_block(block: str) -> Optional[dict]:
    m = re.search(r"(?:🔥|📌)\s+\*\*(.+?)\*\*\s+·\s+(\d+)/100", block)
    if not m:
        return None
    title = m.group(1).strip()
    score = int(m.group(2))

    company = ""
    cm = re.search(r"🏢\s+(.+)", block)
    if cm:
        company = cm.group(1).strip()

    source_url = ""
    um = re.search(r"🔗\s*(https?://\S+)", block)
    if um:
        source_url = um.group(1).strip()

    jd_text = ""
    jm = re.search(r"📋\s*(.+?)(?=\n(?:🔗|🏢|💰|━|$))", block, re.DOTALL)
    if jm:
        jd_text = jm.group(1).strip()

    return {
        "id": _stable_id(source_url, title, company),
        "title": title,
        "company": company,
        "score": score,
        "source": _derive_source(source_url, company),
        "source_url": source_url,
        "jd_text": jd_text,
    }

def get_latest_report_path() -> Optional[Path]:
    reports = sorted(config.JOBSEARCH_REPORTS_DIR.glob("*.md"))
    return reports[-1] if reports else None

def import_latest_report() -> int:
    """Читает последний отчёт, импортирует новые вакансии в DB. Возвращает кол-во новых."""
    path = get_latest_report_path()
    if not path:
        return 0
    text = path.read_text(encoding="utf-8")
    jobs = parse_report_text(text)
    count = 0
    for j in jobs:
        if j["score"] < 40:
            continue
        if not db.get_job(j["id"]):
            db.upsert_job(j["id"], j["title"], j["company"], j["score"],
                          j["source"], j["source_url"], j["jd_text"])
            count += 1
    return count
```

- [ ] **Запустить тесты — убедиться что проходят**

```bash
cd ~/workspaces/career-bot && source venv/bin/activate && python3 -m pytest tests/test_scanner.py -v
```
Ожидаемый вывод: `4 passed`

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add scanner.py tests/test_scanner.py && git commit -m "feat(career-bot): JobScanner report parser"
```

---

## Task 4: Bot core — httpx polling loop + reply keyboard

**Files:**
- Create: `~/workspaces/career-bot/bot.py`
- Create: `~/workspaces/career-bot/keyboards.py`
- Create: `~/workspaces/career-bot/handlers/__init__.py`

- [ ] **Создать keyboards.py**

```python
# keyboards.py
# Все клавиатуры бота в одном месте.

MAIN_MENU = {
    "keyboard": [
        ["🔎 Дайджест", "📋 Мои отклики"],
        ["📄 Резюме в работе", "🎯 Интервью"],
    ],
    "resize_keyboard": True,
    "persistent": True,
}

def job_buttons(job_id: str) -> dict:
    """Inline кнопки под вакансией в дайджесте."""
    return {"inline_keyboard": [[
        {"text": "✅ В работу", "callback_data": f"job_take:{job_id}"},
        {"text": "📋 Подробнее", "callback_data": f"job_detail:{job_id}"},
        {"text": "❌ Пропустить", "callback_data": f"job_skip:{job_id}"},
    ]]}

def draft_buttons(job_id: str) -> dict:
    """Inline кнопки при показе чистовика."""
    return {"inline_keyboard": [[
        {"text": "✅ Отправить", "callback_data": f"draft_approve:{job_id}"},
        {"text": "✏️ Правки", "callback_data": f"draft_revise:{job_id}"},
        {"text": "❌ Отложить", "callback_data": f"draft_postpone:{job_id}"},
    ]]}

def app_buttons(job_id: str, has_response: bool = False) -> dict:
    """Inline кнопки в карточке отклика."""
    rows = [[
        {"text": "📝 Полное резюме", "callback_data": f"app_resume:{job_id}"},
        {"text": "✉️ Полное письмо", "callback_data": f"app_cover:{job_id}"},
    ]]
    if has_response:
        rows.append([
            {"text": "🎯 Подготовиться к интервью", "callback_data": f"app_interview:{job_id}"},
        ])
    return {"inline_keyboard": rows}
```

- [ ] **Создать handlers/__init__.py**

```python
# пусто
```

- [ ] **Создать bot.py**

```python
#!/usr/bin/env python3
"""Карьера-бот — оркестратор карьерного pipeline."""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import httpx

# Загружаем .env если есть
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import config
import db
from keyboards import MAIN_MENU, job_buttons, draft_buttons, app_buttons

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("career-bot")

TG_BASE = f"https://api.telegram.org/bot{config.BOT_TOKEN}"

# --- HTTP helpers ---

def _client() -> httpx.AsyncClient:
    if config.PROXY_URL:
        return httpx.AsyncClient(proxy=config.PROXY_URL, timeout=60.0)
    return httpx.AsyncClient(timeout=60.0)

async def tg(method: str, **kwargs) -> dict:
    async with _client() as c:
        r = await c.post(f"{TG_BASE}/{method}", json=kwargs)
        return r.json()

async def send(chat_id: int, text: str, reply_markup: dict = None,
               parse_mode: str = "HTML") -> None:
    params = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
    if reply_markup:
        params["reply_markup"] = reply_markup
    await tg("sendMessage", **params)

async def answer_cb(callback_query_id: str, text: str = "") -> None:
    await tg("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

# --- Handlers (импортируются после определения helpers) ---

async def handle_update(upd: dict) -> None:
    if msg := upd.get("message"):
        await handle_message(msg)
    elif cq := upd.get("callback_query"):
        await handle_callback(cq)

async def handle_message(msg: dict) -> None:
    chat_id: int = msg["chat"]["id"]
    if chat_id != config.BORIS_CHAT_ID:
        return
    text = (msg.get("text") or "").strip()

    if text in ("/start", "/menu"):
        await send(chat_id, "Карьера-бот готов к работе.", reply_markup=MAIN_MENU)
        return

    if text == "🔎 Дайджест":
        from handlers.digest import show_digest
        await show_digest(chat_id)
        return

    if text == "📋 Мои отклики":
        from handlers.applications import show_applications
        await show_applications(chat_id)
        return

    if text == "📄 Резюме в работе":
        from handlers.resume import show_drafts_pending
        await show_drafts_pending(chat_id)
        return

    if text == "🎯 Интервью":
        await send(chat_id, "Интервью-модуль — Plan 2. Скоро.")
        return

    # Голосовой ввод
    if voice := msg.get("voice"):
        await handle_voice(chat_id, voice)
        return

    await send(chat_id, "Используй кнопки меню.", reply_markup=MAIN_MENU)

async def handle_callback(cq: dict) -> None:
    chat_id = cq["from"]["id"]
    data: str = cq.get("data", "")
    await answer_cb(cq["id"])

    if data.startswith("job_take:"):
        from handlers.digest import cb_job_take
        await cb_job_take(chat_id, data.split(":", 1)[1])

    elif data.startswith("job_skip:"):
        from handlers.digest import cb_job_skip
        await cb_job_skip(chat_id, data.split(":", 1)[1])

    elif data.startswith("job_detail:"):
        from handlers.digest import cb_job_detail
        await cb_job_detail(chat_id, data.split(":", 1)[1])

    elif data.startswith("draft_approve:"):
        from handlers.resume import cb_draft_approve
        await cb_draft_approve(chat_id, data.split(":", 1)[1])

    elif data.startswith("draft_revise:"):
        from handlers.resume import cb_draft_revise
        await cb_draft_revise(chat_id, data.split(":", 1)[1])

    elif data.startswith("draft_postpone:"):
        from handlers.resume import cb_draft_postpone
        await cb_draft_postpone(chat_id, data.split(":", 1)[1])

    elif data.startswith("app_resume:"):
        from handlers.applications import cb_app_resume
        await cb_app_resume(chat_id, data.split(":", 1)[1])

    elif data.startswith("app_cover:"):
        from handlers.applications import cb_app_cover
        await cb_app_cover(chat_id, data.split(":", 1)[1])

async def handle_voice(chat_id: int, voice: dict) -> None:
    await send(chat_id, "Голосовой ввод — Plan 2.")

# --- Poll loop ---

async def poll_loop() -> None:
    db.init_db()
    offset = 0
    log.info("career-bot started, chat_id=%s", config.BORIS_CHAT_ID)
    async with _client() as c:
        await c.post(f"{TG_BASE}/deleteWebhook")
    while True:
        try:
            async with _client() as c:
                r = await c.post(f"{TG_BASE}/getUpdates",
                    json={"offset": offset, "timeout": 30,
                          "allowed_updates": ["message", "callback_query"]},
                    timeout=40.0)
            data = r.json()
            if not data.get("ok"):
                log.error("getUpdates: %s", data)
                await asyncio.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                asyncio.create_task(handle_update(upd))
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("poll error: %s", e)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(poll_loop())
```

- [ ] **Создать .env из .env.example, вставить токен**

```bash
cp ~/workspaces/career-bot/.env.example ~/workspaces/career-bot/.env
# Открыть .env и вставить CAREER_BOT_TOKEN (получить от @BotFather)
```

- [ ] **Запустить бота и проверить /start**

```bash
cd ~/workspaces/career-bot && source venv/bin/activate && python3 bot.py
```
Ожидаемый результат: в Telegram @CareeraBot отвечает на /start с main menu.

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add bot.py keyboards.py handlers/__init__.py && git commit -m "feat(career-bot): bot core with poll loop and main menu"
```

---

## Task 5: Digest flow handler

**Files:**
- Create: `~/workspaces/career-bot/handlers/digest.py`

- [ ] **Создать handlers/digest.py**

```python
# handlers/digest.py
import asyncio
import logging
from bot import send
import db
import scanner
from keyboards import job_buttons, MAIN_MENU

log = logging.getLogger("career-bot.digest")

STATUS_EMOJI = {
    "response":      "🔴",
    "draft_ready":   "🔵",
    "approved":      "🟡",
    "applied":       "🟠",
    "selected":      "🟢",
    "interview_prep":"🟣",
}

def _job_card(job: dict, show_buttons: bool = True) -> tuple[str, dict]:
    score = job.get("score", 0)
    icon = "🔥" if score >= 75 else "📌"
    salary = ""  # из jd_text при необходимости
    text = (
        f"{icon} <b>{job['title']}</b> · {score}/100\n"
        f"🏢 {job.get('company','')}\n"
        f"🔗 {job.get('source_url','') or '—'}\n"
        f"<i>{(job.get('jd_text','')[:200] + '…') if job.get('jd_text') else ''}</i>"
    )
    markup = job_buttons(job["id"]) if show_buttons else None
    return text, markup

async def show_digest(chat_id: int) -> None:
    new_count = scanner.import_latest_report()
    hot = db.get_jobs_by_status("new")
    interesting = [j for j in hot if 40 <= j["score"] < 75]
    hot = [j for j in hot if j["score"] >= 75]

    if not hot and not interesting:
        await send(chat_id, "Новых вакансий нет. Следующий скан — по расписанию.")
        return

    await send(chat_id, f"📊 <b>Дайджест</b> · {new_count} новых вакансий\n"
               f"🔥 Горячих: {len(hot)} · 📌 Интересных: {len(interesting)}")

    for job in hot:
        text, markup = _job_card(job)
        await send(chat_id, text, reply_markup=markup)
        await asyncio.sleep(0.3)

    if interesting:
        await send(chat_id, "── 📌 Интересные ──")
        for job in interesting:
            text, markup = _job_card(job)
            await send(chat_id, text, reply_markup=markup)
            await asyncio.sleep(0.3)

    db.mark_new_jobs_as_seen()

async def cb_job_take(chat_id: int, job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        await send(chat_id, "Вакансия не найдена.")
        return
    db.set_status(job_id, "selected")
    await send(chat_id,
        f"✅ Взял в работу: <b>{job['title']}</b> · {job.get('company','')}\n"
        f"Ставлю задачу ResumePro...")
    from resume_service import request_resume
    asyncio.create_task(request_resume(chat_id, job_id))

async def cb_job_skip(chat_id: int, job_id: str) -> None:
    db.set_status(job_id, "closed")
    await send(chat_id, "Вакансия пропущена.")

async def cb_job_detail(chat_id: int, job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        await send(chat_id, "Вакансия не найдена.")
        return
    text = (
        f"<b>{job['title']}</b>\n"
        f"🏢 {job.get('company','')}\n"
        f"🔗 {job.get('source_url','')}\n\n"
        f"{job.get('jd_text','')[:3000]}"
    )
    await send(chat_id, text, reply_markup=job_buttons(job_id))
```

- [ ] **Проверить вручную: открыть бота, нажать "Дайджест"**

Ожидаемый результат: бот присылает вакансии из последнего отчёта с кнопками.

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add handlers/digest.py && git commit -m "feat(career-bot): digest flow with inline job buttons"
```

---

## Task 6: ResumePro integration — task protocol + AGENTS.md update

**Files:**
- Create: `~/workspaces/career-bot/resume_service.py`
- Modify: `~/workspaces/resume-editor/AGENTS.md`

- [ ] **Создать директорию для задач ResumePro**

```bash
mkdir -p ~/workspaces/resume-editor/tasks
```

- [ ] **Добавить CAREER TASK PROTOCOL в resume-editor/AGENTS.md**

Добавить в конец файла `~/workspaces/resume-editor/AGENTS.md`:

```markdown
---

## CAREER TASK PROTOCOL

Когда получаешь сообщение вида `CAREER_TASK {job_id}`:

1. Прочитай файл задания:
   ```bash
   cat ~/workspaces/resume-editor/tasks/{job_id}.json
   ```

2. Выполни адаптацию резюме по алгоритму выше (Шаг 1 — Разбор JD, Шаг 2 — Маппинг, итд).

3. Запиши результат в файл строго в следующем формате:
   ```
   <!-- RESUME -->
   {полный текст адаптированного резюме}
   <!-- COVER -->
   {полный текст сопроводительного письма}
   <!-- END -->
   ```
   Путь: `~/workspaces/resume-editor/versions/{job_id}_draft.md`

4. Не пиши ничего в чат Бориса — бот сам заберёт файл и уведомит его.

Формат task JSON:
```json
{
  "job_id": "...",
  "title": "...",
  "company": "...",
  "source_url": "...",
  "jd_text": "..."
}
```
```

- [ ] **Создать resume_service.py**

```python
# resume_service.py
import asyncio
import json
import logging
import time
from pathlib import Path
import httpx

import config
import db
from bot import send
from keyboards import draft_buttons

log = logging.getLogger("career-bot.resume")

async def _send_federation_message(agent_id: str, message: str) -> bool:
    """Отправить сообщение агенту через federation API."""
    url = f"{config.FEDERATION_URL}/api/agent/{agent_id}/message"
    params = {"from": "career-bot", "message": message}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url, params=params)
            return r.status_code == 200
    except Exception as e:
        log.warning("federation message failed: %s", e)
        return False

def _write_task_file(job: dict) -> Path:
    config.RESUME_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RESUME_TASKS_DIR / f"{job['id']}.json"
    path.write_text(json.dumps({
        "job_id": job["id"],
        "title": job["title"],
        "company": job.get("company", ""),
        "source_url": job.get("source_url", ""),
        "jd_text": job.get("jd_text", ""),
    }, ensure_ascii=False, indent=2))
    return path

def _read_draft(job_id: str) -> tuple[str, str] | None:
    """Читает черновик если готов. Возвращает (resume_text, cover_text) или None."""
    path = config.RESUME_VERSIONS_DIR / f"{job_id}_draft.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if "<!-- RESUME -->" not in text or "<!-- COVER -->" not in text:
        return None
    parts = text.split("<!-- RESUME -->", 1)[1].split("<!-- COVER -->")
    if len(parts) < 2:
        return None
    resume = parts[0].strip()
    cover = parts[1].split("<!-- END -->")[0].strip()
    return resume, cover

async def request_resume(chat_id: int, job_id: str) -> None:
    """Ставит задачу ResumePro и ждёт результат polling'ом."""
    job = db.get_job(job_id)
    if not job:
        log.error("request_resume: job %s not found", job_id)
        return

    # Записать файл задания
    _write_task_file(job)

    # Отправить сигнал агенту
    ok = await _send_federation_message("resume-editor", f"CAREER_TASK {job_id}")
    if not ok:
        await send(chat_id, f"⚠️ Не удалось достучаться до ResumePro. Задание записано в файл — агент заберёт при следующем запуске.")

    # Polling
    deadline = time.time() + config.AGENT_POLL_TIMEOUT
    while time.time() < deadline:
        result = _read_draft(job_id)
        if result:
            resume_text, cover_text = result
            db.set_status(job_id, "draft_ready")
            await _notify_draft_ready(chat_id, job_id, job, resume_text, cover_text)
            return
        await asyncio.sleep(config.AGENT_POLL_INTERVAL)

    await send(chat_id, f"⚠️ ResumePro не ответил за 30 минут по вакансии «{job['title']}».")
    log.warning("request_resume timeout for job_id=%s", job_id)

async def _notify_draft_ready(chat_id: int, job_id: str, job: dict,
                               resume_text: str, cover_text: str) -> None:
    from keyboards import draft_buttons
    await send(chat_id,
        f"📄 <b>ResumePro подготовил чистовик</b>\n"
        f"{job['title']} · {job.get('company','')}\n\n"
        f"Показать для согласования?",
        reply_markup={"inline_keyboard": [[
            {"text": "👁 Посмотреть", "callback_data": f"draft_view:{job_id}"},
        ]]}
    )
```

- [ ] **Добавить обработчик draft_view в bot.py**

В функцию `handle_callback` в bot.py добавить после `elif data.startswith("job_detail:"):`:

```python
    elif data.startswith("draft_view:"):
        from handlers.resume import cb_draft_view
        await cb_draft_view(chat_id, data.split(":", 1)[1])
```

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add resume_service.py && git commit -m "feat(career-bot): ResumePro task protocol and polling"
cd ~/workspaces/resume-editor && git add AGENTS.md && git commit -m "feat(resume-editor): add CAREER TASK PROTOCOL section"
```

---

## Task 7: Approval flow + snapshot

**Files:**
- Create: `~/workspaces/career-bot/handlers/resume.py`

- [ ] **Создать handlers/resume.py**

```python
# handlers/resume.py
import asyncio
import logging
from bot import send
import db
from keyboards import draft_buttons, MAIN_MENU
from resume_service import _read_draft

log = logging.getLogger("career-bot.resume")

# Временное хранилище режима "жду правки" {chat_id: job_id}
_awaiting_revision: dict[int, str] = {}

async def show_drafts_pending(chat_id: int) -> None:
    drafts = db.get_jobs_by_status("draft_ready")
    if not drafts:
        await send(chat_id, "Нет чистовиков, ожидающих согласования.")
        return
    for d in drafts:
        await send(chat_id,
            f"🔵 <b>{d['title']}</b> · {d.get('company','')}\n"
            f"Ожидает согласования.",
            reply_markup={"inline_keyboard": [[
                {"text": "👁 Посмотреть", "callback_data": f"draft_view:{d['job_id']}"},
            ]]}
        )
        await asyncio.sleep(0.2)

async def cb_draft_view(chat_id: int, job_id: str) -> None:
    result = _read_draft(job_id)
    job = db.get_job(job_id)
    if not result or not job:
        await send(chat_id, "Файл чистовика не найден.")
        return
    resume_text, cover_text = result
    # Отправляем дословно — без сокращений
    await send(chat_id, f"<b>РЕЗЮМЕ для {job['company']}:</b>\n\n{resume_text}")
    await asyncio.sleep(0.5)
    await send(chat_id, f"<b>СОПРОВОДИТЕЛЬНОЕ ПИСЬМО:</b>\n\n{cover_text}",
               reply_markup=draft_buttons(job_id))

async def cb_draft_approve(chat_id: int, job_id: str) -> None:
    result = _read_draft(job_id)
    if not result:
        await send(chat_id, "Файл чистовика пропал. Запросить повторно?")
        return
    resume_text, cover_text = result
    # Иммутабельный снапшот — точно то, что пойдёт работодателю
    db.save_snapshot(job_id, resume_text, cover_text)
    db.set_status(job_id, "approved")
    job = db.get_job(job_id)
    await send(chat_id,
        f"✅ Одобрено. Передаю VBoris2 для отклика на {job.get('source','')}.ru...")
    from apply_service import submit_application
    asyncio.create_task(submit_application(chat_id, job_id))

async def cb_draft_revise(chat_id: int, job_id: str) -> None:
    _awaiting_revision[chat_id] = job_id
    await send(chat_id,
        "Напиши правки — что изменить в резюме или письме. "
        "Например: «убери про Servier, добавь про n8n»")

async def cb_draft_postpone(chat_id: int, job_id: str) -> None:
    db.set_status(job_id, "selected")  # возврат на шаг назад
    await send(chat_id, "Отложено. Вернуть можно через «Резюме в работе».")

async def handle_revision_text(chat_id: int, text: str) -> bool:
    """Вызывается из bot.handle_message если есть pending revision.
    Возвращает True если сообщение обработано как правка."""
    job_id = _awaiting_revision.pop(chat_id, None)
    if not job_id:
        return False
    job = db.get_job(job_id)
    from resume_service import _send_federation_message, _write_task_file
    import json, config
    # Дополняем задание правками
    task_path = config.RESUME_TASKS_DIR / f"{job_id}.json"
    if task_path.exists():
        task = json.loads(task_path.read_text())
        task["revision_notes"] = text
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2))
    # Удаляем старый черновик чтобы polling не считал его новым
    draft_path = config.RESUME_VERSIONS_DIR / f"{job_id}_draft.md"
    if draft_path.exists():
        draft_path.unlink()
    db.set_status(job_id, "selected")
    await send(chat_id, f"Правки переданы ResumePro. Жду новый черновик...")
    await _send_federation_message("resume-editor",
        f"CAREER_TASK {job_id} REVISION: {text}")
    from resume_service import request_resume
    asyncio.create_task(request_resume(chat_id, job_id))
    return True
```

- [ ] **Обновить handle_message в bot.py — добавить revision intercept**

В `handle_message`, перед финальным `await send(...)`:

```python
    # Revision intercept
    from handlers.resume import handle_revision_text
    if await handle_revision_text(chat_id, text):
        return
```

- [ ] **Проверить вручную full flow: дайджест → В работу → ждём draft → Посмотреть → Отправить**

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add handlers/resume.py && git commit -m "feat(career-bot): approval flow with immutable snapshot"
```

---

## Task 8: Apply service + навыки по платформам

**Files:**
- Create: `~/workspaces/career-bot/apply_service.py`
- Create: `~/workspaces/career-bot/apply_skills/manual_apply.py`
- Create: `~/workspaces/career-bot/apply_skills/hh_apply.py`
- Create: `~/workspaces/career-bot/apply_skills/tg_apply.py`
- Create: `~/workspaces/career-bot/tests/test_apply_service.py`
- Create: `~/workspaces/career-bot/apply_skills/__init__.py`

- [ ] **Написать тест для apply_service (failing)**

```python
# tests/test_apply_service.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["CAREER_BOT_TOKEN"] = "test"
os.environ["CAREER_DB_PATH"] = "/tmp/test_apply.db"

def test_skill_selection_hh():
    from apply_service import _select_skill
    skill = _select_skill("hh")
    assert skill.__name__ == "hh_apply"

def test_skill_selection_telegram():
    from apply_service import _select_skill
    skill = _select_skill("telegram")
    assert skill.__name__ == "tg_apply"

def test_skill_selection_unknown_falls_back_to_manual():
    from apply_service import _select_skill
    skill = _select_skill("unknown_platform")
    assert skill.__name__ == "manual_apply"
```

- [ ] **Создать apply_skills/__init__.py** (пустой)

- [ ] **Создать apply_skills/manual_apply.py**

```python
# apply_skills/manual_apply.py
"""Для платформ без автоматизации — выдаём инструкцию Борису."""
async def manual_apply(job: dict, snapshot: dict, chat_id: int, send_fn) -> dict:
    source_url = job.get("source_url") or "не указан"
    await send_fn(chat_id,
        f"📋 <b>Ручной отклик</b>\n\n"
        f"Вакансия: {job['title']} · {job.get('company','')}\n"
        f"Ссылка: {source_url}\n\n"
        f"Материалы подготовлены (резюме + письмо в карточке отклика).\n"
        f"После отклика нажми кнопку ниже.",
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Откликнулся", "callback_data": f"applied_confirm:{job['id']}"},
        ]]}
    )
    return {"status": "manual_pending"}
```

- [ ] **Создать apply_skills/hh_apply.py**

```python
# apply_skills/hh_apply.py
"""Отклик через hh.ru API. Требует HH_ACCESS_TOKEN в keymaster."""
import logging
import subprocess
import json
import httpx

log = logging.getLogger("career-bot.hh_apply")

def _get_hh_token() -> str:
    result = subprocess.run(
        ["python3", "/home/shectory/keymaster/keymaster.py",
         "--requester", "career-bot", "query", "HH_ACCESS_TOKEN"],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()

async def hh_apply(job: dict, snapshot: dict, chat_id: int, send_fn) -> dict:
    vacancy_id = job.get("source_url", "").rstrip("/").split("/")[-1]
    if not vacancy_id.isdigit():
        log.warning("hh_apply: cannot extract vacancy_id from %s", job.get("source_url"))
        from apply_skills.manual_apply import manual_apply
        return await manual_apply(job, snapshot, chat_id, send_fn)

    token = _get_hh_token()
    if not token:
        await send_fn(chat_id, "⚠️ HH_ACCESS_TOKEN не настроен. Откликнись вручную.")
        from apply_skills.manual_apply import manual_apply
        return await manual_apply(job, snapshot, chat_id, send_fn)

    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json",
               "User-Agent": "career-bot/1.0 (bshevelev75@gmail.com)"}
    payload = {"vacancy_id": vacancy_id, "resume_id": None}  # resume_id из hh профиля

    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post("https://api.hh.ru/negotiations",
                             headers=headers, json=payload)
        if r.status_code in (201, 200):
            await send_fn(chat_id,
                f"✅ Откликнулся на hh.ru: {job['title']} · {job.get('company','')}")
            return {"status": "applied", "platform": "hh", "vacancy_id": vacancy_id}
        else:
            log.error("hh_apply error %s: %s", r.status_code, r.text)
            await send_fn(chat_id, f"⚠️ hh.ru вернул {r.status_code}. Откликнись вручную.")
            from apply_skills.manual_apply import manual_apply
            return await manual_apply(job, snapshot, chat_id, send_fn)
    except Exception as e:
        log.error("hh_apply exception: %s", e)
        from apply_skills.manual_apply import manual_apply
        return await manual_apply(job, snapshot, chat_id, send_fn)
```

- [ ] **Создать apply_skills/tg_apply.py**

```python
# apply_skills/tg_apply.py
"""Для вакансий из Telegram-каналов — показываем инструкцию написать рекрутёру."""
async def tg_apply(job: dict, snapshot: dict, chat_id: int, send_fn) -> dict:
    company = job.get("company", "")
    await send_fn(chat_id,
        f"📱 <b>Отклик через Telegram</b>\n\n"
        f"Вакансия из канала {company}.\n"
        f"Напиши напрямую в канал или рекрутёру, приложи резюме из карточки отклика.\n\n"
        f"После отклика нажми кнопку:",
        reply_markup={"inline_keyboard": [[
            {"text": "✅ Написал рекрутёру", "callback_data": f"applied_confirm:{job['id']}"},
        ]]}
    )
    return {"status": "manual_pending", "platform": "telegram"}
```

- [ ] **Создать apply_service.py**

```python
# apply_service.py
import logging
from bot import send
import db

log = logging.getLogger("career-bot.apply")

def _select_skill(source: str):
    if source == "hh":
        from apply_skills.hh_apply import hh_apply
        return hh_apply
    if source == "telegram":
        from apply_skills.tg_apply import tg_apply
        return tg_apply
    if source == "email":
        # TODO Sprint 2: email_apply
        from apply_skills.manual_apply import manual_apply
        return manual_apply
    from apply_skills.manual_apply import manual_apply
    return manual_apply

async def submit_application(chat_id: int, job_id: str) -> None:
    job = db.get_job(job_id)
    snapshot = db.get_snapshot(job_id)
    if not job or not snapshot:
        await send(chat_id, "⚠️ Снапшот не найден. Согласуй чистовик повторно.")
        return

    skill_fn = _select_skill(job.get("source", "other"))
    result = await skill_fn(job, snapshot, chat_id, send)

    if result.get("status") == "applied":
        db.set_status(job_id, "applied",
                      apply_platform=result.get("platform", job.get("source")),
                      apply_confirmed_at="datetime('now')")
        log.info("applied job_id=%s via %s", job_id, result.get("platform"))

async def confirm_manual_apply(chat_id: int, job_id: str) -> None:
    """Борис нажал 'Откликнулся' для ручного отклика."""
    job = db.get_job(job_id)
    db.set_status(job_id, "applied",
                  apply_platform="manual",
                  apply_confirmed_at="datetime('now')")
    await send(chat_id,
        f"✅ Зафиксировал отклик: <b>{job['title']}</b> · {job.get('company','')}\n"
        f"Буду отслеживать ответ работодателя.")
```

- [ ] **Добавить applied_confirm callback в bot.py**

В `handle_callback`:
```python
    elif data.startswith("applied_confirm:"):
        from apply_service import confirm_manual_apply
        await confirm_manual_apply(chat_id, data.split(":", 1)[1])
```

- [ ] **Запустить тесты**

```bash
cd ~/workspaces/career-bot && source venv/bin/activate && python3 -m pytest tests/test_apply_service.py -v
```
Ожидаемый вывод: `3 passed`

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add apply_service.py apply_skills/ tests/test_apply_service.py && git commit -m "feat(career-bot): apply service with hh/telegram/manual skills"
```

---

## Task 9: Application browser — браузер откликов

**Files:**
- Create: `~/workspaces/career-bot/handlers/applications.py`

- [ ] **Создать handlers/applications.py**

```python
# handlers/applications.py
import asyncio
import logging
from bot import send
import db
from keyboards import app_buttons

log = logging.getLogger("career-bot.applications")

STATUS_LABEL = {
    "response":       "🔴 Работодатель ответил!",
    "draft_ready":    "🔵 Готов чистовик",
    "approved":       "🟡 Передаётся VBoris2",
    "applied":        "🟠 Откликнулся, ждём ответа",
    "selected":       "🟢 Резюме в работе",
    "interview_prep": "🟣 Готовимся к интервью",
}

def _app_card_text(entry: dict) -> str:
    status = entry.get("status", "")
    label = STATUS_LABEL.get(status, status)
    recruiter = ""
    if entry.get("recruiter_name"):
        recruiter = f"\n👤 {entry['recruiter_name']}"
        if entry.get("recruiter_contact"):
            recruiter += f" · {entry['recruiter_contact']}"
    return (
        f"{label}\n"
        f"<b>{entry['title']}</b> · {entry.get('company','')}\n"
        f"📍 {entry.get('apply_platform','—')}"
        f"{recruiter}"
    )

async def show_applications(chat_id: int) -> None:
    entries = db.get_active_pipeline()
    if not entries:
        await send(chat_id,
            "Активных откликов нет. Выбери вакансии в дайджесте.")
        return
    await send(chat_id, f"📋 <b>Мои отклики</b> · {len(entries)} активных")
    for entry in entries:
        has_response = entry["status"] == "response"
        snap = db.get_snapshot(entry["job_id"])
        has_snap = snap is not None
        buttons = app_buttons(entry["job_id"], has_response=has_response) if has_snap else None
        await send(chat_id, _app_card_text(entry), reply_markup=buttons)
        await asyncio.sleep(0.2)

async def cb_app_resume(chat_id: int, job_id: str) -> None:
    """Показать полный текст резюме что было отправлено — без сокращений."""
    snap = db.get_snapshot(job_id)
    job = db.get_job(job_id)
    if not snap:
        await send(chat_id, "Снапшот не найден (вакансия ещё не отправлена).")
        return
    company = job.get("company", "") if job else ""
    header = f"<b>РЕЗЮМЕ (отправлено {company}):</b>\n\n"
    # Telegram ограничение 4096 символов — разбиваем если длиннее
    full = header + snap["resume_text"]
    for chunk in _split_text(full, 4000):
        await send(chat_id, chunk)
        await asyncio.sleep(0.3)

async def cb_app_cover(chat_id: int, job_id: str) -> None:
    """Показать полный текст письма — без сокращений."""
    snap = db.get_snapshot(job_id)
    job = db.get_job(job_id)
    if not snap:
        await send(chat_id, "Снапшот не найден.")
        return
    company = job.get("company", "") if job else ""
    header = f"<b>СОПРОВОДИТЕЛЬНОЕ ПИСЬМО (отправлено {company}):</b>\n\n"
    full = header + snap["cover_text"]
    for chunk in _split_text(full, 4000):
        await send(chat_id, chunk)
        await asyncio.sleep(0.3)

def _split_text(text: str, limit: int) -> list[str]:
    """Разбивает длинный текст на части не длиннее limit символов."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks
```

- [ ] **Проверить вручную: дайджест → В работу → дождаться draft → Отправить → Мои отклики → Полное резюме**

Ожидаемый результат: бот присылает полный дословный текст резюме что ушёл работодателю.

- [ ] **Commit**

```bash
cd ~/workspaces/career-bot && git add handlers/applications.py && git commit -m "feat(career-bot): application browser with full text retrieval"
```

---

## Task 10: systemd deploy

**Files:**
- Create: `~/.config/systemd/user/career-bot.service`

- [ ] **Создать systemd service**

```bash
cat > ~/.config/systemd/user/career-bot.service << 'EOF'
[Unit]
Description=Career Bot — Telegram career pipeline orchestrator
After=network-online.target openclaw-gateway.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/shectory/workspaces/career-bot
EnvironmentFile=/home/shectory/workspaces/career-bot/.env
ExecStart=/home/shectory/workspaces/career-bot/venv/bin/python3 bot.py
Restart=always
RestartSec=10
KillMode=process
TimeoutStopSec=10
StandardOutput=append:/home/shectory/.openclaw/logs/career-bot.log
StandardError=append:/home/shectory/.openclaw/logs/career-bot.log

[Install]
WantedBy=default.target
EOF
```

- [ ] **Включить и запустить**

```bash
systemctl --user daemon-reload
systemctl --user enable career-bot.service
systemctl --user start career-bot.service
systemctl --user status career-bot.service
```
Ожидаемый вывод: `Active: active (running)`

- [ ] **Проверить логи**

```bash
tail -f ~/.openclaw/logs/career-bot.log
```
Ожидаемый вывод: `career-bot started, chat_id=36910539`

- [ ] **Финальный интеграционный тест**

Проверить весь flow вручную:
1. Нажать "🔎 Дайджест" → получить вакансии с кнопками
2. Нажать "✅ В работу" под горячей вакансией
3. Дождаться draft от ResumePro
4. Нажать "👁 Посмотреть" → увидеть полный текст резюме и письма
5. Нажать "✅ Отправить" → snапшот создан, отклик пошёл
6. Нажать "📋 Мои отклики" → карточка со статусом "Откликнулся"
7. Нажать "📝 Полное резюме" → дословный текст

- [ ] **Commit**

```bash
git -C ~/workspaces/career-bot add -A && git commit -m "feat(career-bot): systemd deploy"
```

---

## Self-review

**Spec coverage:**
- [x] Один бот "Карьера" — Task 4
- [x] Push горячих (>75) — реализован через import_latest_report + scanner, уведомление происходит при первом дайджесте; автопуш при cron — Plan 2
- [x] Inline кнопки под каждой вакансией — Task 5
- [x] ResumePro integration — Task 6
- [x] Approval gate — Task 7
- [x] Immutable snapshot — Task 7 (save_snapshot вызывается только при approve)
- [x] Full text retrieval без сокращений — Task 9, _split_text для длинных текстов
- [x] Apply service + платформенные навыки — Task 8
- [x] Application browser — Task 9
- [x] systemd deploy — Task 10
- [ ] Автоматический push при завершении скана — нужно добавить

**Пропущено: автопуш горячих при новом скане.** Добавить в Task 5 или отдельным шагом — бот должен проверять новые отчёты по расписанию, а не только по запросу "Дайджест".

**Исправление:** добавить в bot.py background task для автопуша:

```python
# В poll_loop() перед while True: добавить:
asyncio.create_task(_auto_digest_watcher())

async def _auto_digest_watcher() -> None:
    """Проверяет каждые 30 мин новые горячие вакансии и пушит Борису."""
    import scanner, db
    last_report: str = ""
    while True:
        await asyncio.sleep(1800)  # 30 мин
        path = scanner.get_latest_report_path()
        if path and str(path) != last_report:
            last_report = str(path)
            count = scanner.import_latest_report()
            hot = db.get_jobs_by_status("new")
            hot = [j for j in hot if j["score"] >= 75]
            if hot:
                await send(config.BORIS_CHAT_ID,
                    f"🔥 Новые горячие вакансии: {len(hot)}\nНажми «Дайджест» чтобы посмотреть.")
```

Добавить этот код в Task 4 при реализации.

**Голос (Plan 2):** STT/TTS и mini-app — отдельный план.
**InterviewCoach (Plan 2):** Отдельный план.
